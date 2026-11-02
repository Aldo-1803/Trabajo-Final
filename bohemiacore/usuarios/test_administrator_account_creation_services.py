import json
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import TestCase

from gestion.models import Auditoria, Personal
from usuarios.administrator_account_services import (
    ADMINISTRATOR_ACCOUNT_CREATED_EVENT,
    ADMINISTRATOR_ACCOUNT_CREATION_AUDIT_TABLE,
    ADMINISTRATOR_ACCOUNT_CREATION_SOURCE,
    AdministratorAccountCreationConflict,
    AdministratorEmailAlreadyExists,
    InvalidAdministratorAccountPassword,
    PermissionDeniedForAdministratorAccountCreation,
    create_administrator_account,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class AdministratorAccountCreationServiceTests(TestCase):
    password = 'Temporal!Admin2026'
    reason = 'Incorporación como administradora'

    def setUp(self):
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('admin-creator@test.com')
        self.actor.user_permissions.add(
            self.manage_users,
            self.assign_roles,
        )

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='ActorPassword!2026',
            **extra_fields,
        )

    def create_administrator(self, actor=None, **overrides):
        values = {
            'actor': actor or self.actor,
            'email': 'new.admin@example.com',
            'first_name': ' Ana ',
            'last_name': ' Pérez ',
            'raw_password': self.password,
            'reason': self.reason,
        }
        values.update(overrides)
        return create_administrator_account(**values)

    def test_authorized_actor_creates_plain_spa_administrator(self):
        result = self.create_administrator()

        user = Usuario.objects.get(pk=result.user_id)
        self.assertTrue(result.created)
        self.assertEqual(result.email, 'new.admin@example.com')
        self.assertEqual(result.role, BusinessRole.ADMINISTRADOR)
        self.assertTrue(result.user_active)
        self.assertEqual(user.first_name, 'Ana')
        self.assertEqual(user.last_name, 'Pérez')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(
            get_business_roles(user),
            (BusinessRole.ADMINISTRADOR,),
        )
        self.assertEqual(
            tuple(user.groups.values_list('name', flat=True)),
            (BusinessRole.ADMINISTRADOR,),
        )
        self.assertFalse(user.user_permissions.exists())
        self.assertFalse(Cliente.objects.filter(usuario=user).exists())
        self.assertFalse(Personal.objects.filter(usuario=user).exists())

    def test_result_is_immutable(self):
        result = self.create_administrator()

        with self.assertRaises(FrozenInstanceError):
            result.email = 'changed@example.com'

    def test_actor_requires_manage_users_and_assign_roles(self):
        permission_sets = (
            (),
            (self.manage_users,),
            (self.assign_roles,),
        )

        for index, permissions in enumerate(permission_sets, start=1):
            with self.subTest(permissions=permissions):
                actor = self.create_user(f'denied-admin-{index}@test.com')
                actor.user_permissions.add(*permissions)
                with self.assertRaises(
                    PermissionDeniedForAdministratorAccountCreation
                ):
                    self.create_administrator(
                        actor=actor,
                        email=f'not-created-{index}@test.com',
                    )

        self.assertFalse(
            Usuario.objects.filter(email__startswith='not-created-').exists()
        )

    def test_is_staff_without_permissions_is_rejected(self):
        actor = self.create_user('staff-only-admin@test.com', is_staff=True)

        with self.assertRaises(
            PermissionDeniedForAdministratorAccountCreation
        ):
            self.create_administrator(actor=actor)

        self.assertFalse(
            Usuario.objects.filter(email='new.admin@example.com').exists()
        )

    def test_duplicate_email_is_case_insensitive(self):
        self.create_user('Existing.Admin@Example.com')

        with self.assertRaises(AdministratorEmailAlreadyExists):
            self.create_administrator(email='existing.admin@EXAMPLE.COM')

    def test_email_and_names_are_normalized(self):
        result = self.create_administrator(
            email='  New.Admin@EXAMPLE.COM  ',
        )

        user = Usuario.objects.get(pk=result.user_id)
        self.assertEqual(user.email, 'New.Admin@example.com')
        self.assertEqual(result.email, 'New.Admin@example.com')
        self.assertEqual(user.first_name, 'Ana')
        self.assertEqual(user.last_name, 'Pérez')

    def test_weak_password_is_rejected_without_creating_user(self):
        with self.assertRaises(InvalidAdministratorAccountPassword):
            self.create_administrator(raw_password='123')

        self.assertFalse(
            Usuario.objects.filter(email='new.admin@example.com').exists()
        )

    def test_password_is_hashed_and_never_returned(self):
        result = self.create_administrator()

        user = Usuario.objects.get(pk=result.user_id)
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))
        self.assertFalse(hasattr(result, 'password'))
        self.assertFalse(hasattr(result, 'raw_password'))

    def test_role_failure_rolls_back_created_user(self):
        with patch(
            'usuarios.administrator_account_services.assign_business_role',
            side_effect=RuntimeError('role backend unavailable'),
        ):
            with self.assertRaises(AdministratorAccountCreationConflict):
                self.create_administrator()

        self.assertFalse(
            Usuario.objects.filter(email='new.admin@example.com').exists()
        )

    def test_audit_failure_rolls_back_user_and_role(self):
        with patch(
            'usuarios.administrator_account_services.'
            '_write_administrator_account_creation_audit',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(AdministratorAccountCreationConflict):
                self.create_administrator()

        self.assertFalse(
            Usuario.objects.filter(email='new.admin@example.com').exists()
        )
        self.assertFalse(
            Auditoria.objects.filter(
                tabla=ADMINISTRATOR_ACCOUNT_CREATION_AUDIT_TABLE
            ).exists()
        )

    def test_semantic_audit_has_no_credentials(self):
        result = self.create_administrator()

        audit = Auditoria.objects.get(pk=result.audit_id)
        self.assertEqual(
            audit.tabla,
            ADMINISTRATOR_ACCOUNT_CREATION_AUDIT_TABLE,
        )
        self.assertEqual(
            audit.valor_nuevo['event'],
            ADMINISTRATOR_ACCOUNT_CREATED_EVENT,
        )
        self.assertEqual(
            audit.valor_nuevo['source'],
            ADMINISTRATOR_ACCOUNT_CREATION_SOURCE,
        )
        self.assertEqual(audit.valor_nuevo['actor_id'], self.actor.pk)
        self.assertEqual(audit.valor_nuevo['user_id'], result.user_id)
        self.assertEqual(
            audit.valor_nuevo['business_role'],
            BusinessRole.ADMINISTRADOR,
        )
        self.assertEqual(audit.valor_nuevo['reason'], self.reason)
        self.assertTrue(audit.valor_nuevo['is_active'])
        self.assertFalse(audit.valor_nuevo['is_staff'])
        self.assertFalse(audit.valor_nuevo['is_superuser'])
        relevant_audits = Auditoria.objects.filter(
            registro_id=result.user_id,
            tabla__in=(
                'Usuario',
                ADMINISTRATOR_ACCOUNT_CREATION_AUDIT_TABLE,
            ),
        )
        serialized_audit = json.dumps([
            {
                'previous': item.valor_anterior,
                'new': item.valor_nuevo,
            }
            for item in relevant_audits
        ]).lower()
        self.assertNotIn(self.password.lower(), serialized_audit)
        self.assertNotIn('password', serialized_audit)
        self.assertNotIn('token', serialized_audit)
