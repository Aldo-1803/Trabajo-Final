import json
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import TestCase

from gestion.models import Auditoria, DiagnosticoCapilar, Personal
from usuarios.client_account_services import (
    CLIENT_ACCOUNT_CREATED_BY_STAFF_EVENT,
    CLIENT_ACCOUNT_CREATION_AUDIT_TABLE,
    CLIENT_ACCOUNT_CREATION_SOURCE,
    ClientAccountCreationConflict,
    EmailAlreadyExists,
    InvalidClientAccountPassword,
    PermissionDeniedForClientAccountCreation,
    create_client_account_by_staff,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class ClientAccountCreationServiceTests(TestCase):
    password = 'Temporal!Cliente2026'
    reason = 'Alta presencial en recepción'

    def setUp(self):
        self.permission = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='create_walkin_client',
        )
        self.actor = self.create_user('client-creator@test.com')
        self.actor.user_permissions.add(self.permission)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='ActorPassword!2026',
            **extra_fields,
        )

    def create_account(self, **overrides):
        values = {
            'actor': self.actor,
            'email': 'ana.client@EXAMPLE.COM',
            'first_name': ' Ana ',
            'last_name': ' Pérez ',
            'raw_password': self.password,
            'reason': self.reason,
            'telefono': ' 1122334455 ',
            'zona': ' Centro ',
        }
        values.update(overrides)
        return create_client_account_by_staff(**values)

    def semantic_audits(self):
        return Auditoria.objects.filter(
            tabla=CLIENT_ACCOUNT_CREATION_AUDIT_TABLE
        )

    def test_authorized_actor_creates_complete_client_account(self):
        result = self.create_account()

        user = Usuario.objects.get(pk=result.user_id)
        cliente = Cliente.objects.get(pk=result.cliente_id)
        self.assertTrue(result.created)
        self.assertEqual(result.email, 'ana.client@example.com')
        self.assertEqual(result.role, BusinessRole.CLIENTE)
        self.assertTrue(result.user_active)
        self.assertEqual(user.first_name, 'Ana')
        self.assertEqual(user.last_name, 'Pérez')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertEqual(cliente.usuario, user)
        self.assertEqual(cliente.numero, '1122334455')
        self.assertEqual(cliente.zona, 'Centro')
        self.assertTrue(cliente.activo)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertFalse(Personal.objects.filter(usuario=user).exists())
        self.assertFalse(
            DiagnosticoCapilar.objects.filter(cliente=cliente).exists()
        )

        audit = self.semantic_audits().get()
        self.assertEqual(result.audit_id, audit.pk)
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, user.pk)
        self.assertEqual(
            audit.valor_nuevo['event'],
            CLIENT_ACCOUNT_CREATED_BY_STAFF_EVENT,
        )
        self.assertEqual(
            audit.valor_nuevo['source'],
            CLIENT_ACCOUNT_CREATION_SOURCE,
        )
        self.assertEqual(audit.valor_nuevo['user_id'], user.pk)
        self.assertEqual(audit.valor_nuevo['cliente_id'], cliente.pk)
        self.assertEqual(
            audit.valor_nuevo['business_role'],
            BusinessRole.CLIENTE,
        )
        self.assertEqual(audit.valor_nuevo['reason'], self.reason)
        serialized_audit = json.dumps(audit.valor_nuevo).lower()
        self.assertNotIn('password', serialized_audit)
        self.assertNotIn(self.password.lower(), serialized_audit)
        self.assertNotIn(user.password.lower(), serialized_audit)

        with self.assertRaises(FrozenInstanceError):
            result.created = False

    def test_permission_is_required_without_staff_shortcut(self):
        actors = (
            self.create_user('without-client-permission@test.com'),
            self.create_user(
                'staff-without-client-permission@test.com',
                is_staff=True,
            ),
        )

        for index, actor in enumerate(actors):
            with self.subTest(actor=actor.email):
                with self.assertRaises(
                    PermissionDeniedForClientAccountCreation
                ):
                    self.create_account(
                        actor=actor,
                        email=f'denied-{index}@test.com',
                    )

        self.assertFalse(
            Usuario.objects.filter(email__startswith='denied-').exists()
        )

    def test_duplicate_email_is_rejected_case_insensitively(self):
        existing = self.create_user('Existing.Client@Test.com')
        initial_count = Usuario.objects.count()

        with self.assertRaises(EmailAlreadyExists):
            self.create_account(email='existing.client@test.COM')

        self.assertEqual(Usuario.objects.count(), initial_count)
        self.assertFalse(Cliente.objects.filter(usuario=existing).exists())
        self.assertFalse(self.semantic_audits().exists())

    def test_weak_password_is_rejected_before_any_write(self):
        with self.assertRaises(InvalidClientAccountPassword):
            self.create_account(raw_password='123')

        self.assertFalse(
            Usuario.objects.filter(email__iexact='ana.client@example.com').exists()
        )
        self.assertFalse(self.semantic_audits().exists())

    @patch(
        'usuarios.client_account_services.Cliente.objects.create',
        side_effect=RuntimeError('forced client failure'),
    )
    def test_client_creation_failure_rolls_back_user(self, _create):
        with self.assertRaises(ClientAccountCreationConflict):
            self.create_account()

        self.assertFalse(
            Usuario.objects.filter(email__iexact='ana.client@example.com').exists()
        )
        self.assertFalse(Cliente.objects.exists())
        self.assertFalse(self.semantic_audits().exists())

    @patch(
        'usuarios.client_account_services.assign_business_role',
        side_effect=RuntimeError('forced role failure'),
    )
    def test_role_assignment_failure_rolls_back_user_and_client(self, _assign):
        with self.assertRaises(ClientAccountCreationConflict):
            self.create_account()

        self.assertFalse(
            Usuario.objects.filter(email__iexact='ana.client@example.com').exists()
        )
        self.assertFalse(Cliente.objects.exists())
        self.assertFalse(self.semantic_audits().exists())

    @patch(
        'usuarios.client_account_services.Auditoria.objects.create',
        side_effect=RuntimeError('forced audit failure'),
    )
    def test_audit_failure_rolls_back_complete_operation(self, _audit):
        with self.assertRaises(ClientAccountCreationConflict):
            self.create_account()

        self.assertFalse(
            Usuario.objects.filter(email__iexact='ana.client@example.com').exists()
        )
        self.assertFalse(Cliente.objects.exists())
        self.assertFalse(self.semantic_audits().exists())
