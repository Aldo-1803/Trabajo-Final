from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria
from usuarios.access_services import (
    ACCOUNT_DEACTIVATED_EVENT,
    ACCOUNT_DEACTIVATION_AUDIT_TABLE,
    ACCOUNT_DEACTIVATION_SOURCE,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class AccountDeactivationActionTests(APITestCase):
    def setUp(self):
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.actor = self.create_user('deactivate-api-actor@test.com')
        self.actor.user_permissions.add(self.manage_users)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def assign_role(self, user, role):
        user.groups.add(Group.objects.get(name=role))

    def url(self, user_id):
        return reverse('admin-usuarios-desactivar-cuenta', args=[user_id])

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def post(self, user_id, payload=None):
        if payload is None:
            payload = {'motivo': 'Baja administrativa aprobada'}
        return self.client.post(self.url(user_id), payload, format='json')

    def create_client_target(self, email='deactivate-target@test.com'):
        target = self.create_user(email)
        self.assign_role(target, BusinessRole.CLIENTE)
        cliente = Cliente.objects.create(
            usuario=target,
            zona='Centro',
            activo=True,
        )
        return target, cliente

    def test_valid_deactivation_returns_200_and_semantic_audit(self):
        target, cliente = self.create_client_target()
        self.authenticate()

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['usuario_id'], target.pk)
        self.assertTrue(response.data['usuario_activo_anterior'])
        self.assertFalse(response.data['usuario_activo_actual'])
        self.assertEqual(response.data['rol_actual'], BusinessRole.CLIENTE)
        target.refresh_from_db()
        cliente.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertTrue(cliente.activo)

        audit = Auditoria.objects.get(
            tabla=ACCOUNT_DEACTIVATION_AUDIT_TABLE,
            registro_id=target.pk,
        )
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(
            audit.valor_nuevo['event'],
            ACCOUNT_DEACTIVATED_EVENT,
        )
        self.assertEqual(
            audit.valor_nuevo['source'],
            ACCOUNT_DEACTIVATION_SOURCE,
        )
        self.assertEqual(
            audit.valor_nuevo['reason'],
            'Baja administrativa aprobada',
        )

    def test_manage_users_is_required_without_staff_shortcut(self):
        target, _ = self.create_client_target(
            'deactivate-denied-target@test.com'
        )
        actors = (
            self.create_user('deactivate-no-permission@test.com'),
            self.create_user(
                'deactivate-staff-only@test.com',
                is_staff=True,
            ),
        )

        for actor in actors:
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.post(target.pk)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'PERMISSION_DENIED',
                )

        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_self_deactivation_is_rejected(self):
        self.assign_role(self.actor, BusinessRole.CLIENTE)
        Cliente.objects.create(usuario=self.actor)
        self.authenticate()

        response = self.post(self.actor.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'SELF_DEACTIVATION_NOT_ALLOWED',
        )
        self.actor.refresh_from_db()
        self.assertTrue(self.actor.is_active)

    def test_superuser_target_is_rejected(self):
        target = self.create_user(
            'deactivate-superuser@test.com',
            is_staff=True,
            is_superuser=True,
        )
        self.authenticate()

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'PROTECTED_SUPERUSER',
        )
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_last_active_administrator_is_rejected(self):
        target = self.create_user('deactivate-last-admin@test.com')
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.authenticate()

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'LAST_ACTIVE_ADMIN',
        )
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_payload_is_strict(self):
        target, _ = self.create_client_target(
            'deactivate-invalid-payload@test.com'
        )
        self.authenticate()

        unexpected = self.post(
            target.pk,
            {'motivo': 'Baja administrativa', 'is_active': False},
        )
        invalid_reason = self.post(target.pk, {'motivo': ' '})

        self.assertEqual(unexpected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            unexpected.data['error']['code'],
            'INVALID_PAYLOAD',
        )
        self.assertIn('is_active', unexpected.data['error']['fields'])
        self.assertEqual(
            invalid_reason.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_reason.data['error']['code'],
            'INVALID_REASON',
        )
        target.refresh_from_db()
        self.assertTrue(target.is_active)
