from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Personal
from gestion.personal_access_services import (
    FULL_WORK_ACCESS_REVOCATION_AUDIT_TABLE,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class FullWorkAccessRevocationActionTests(APITestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.actor = self.create_user('full-revoke-api-actor@test.com')
        self.actor.user_permissions.add(
            self.manage_personal,
            self.manage_users,
        )

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def create_personal(self, suffix, **overrides):
        values = {
            'nombre': f'Nombre {suffix}',
            'apellido': 'Baja Total API',
            'rol': 'asistente',
            'activo': True,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def create_linked_context(
        self,
        suffix,
        role=BusinessRole.EMPLEADO,
        *,
        personal_active=True,
        user_active=True,
        superuser=False,
    ):
        user = self.create_user(
            f'full-revoke-api-{suffix}@test.com',
            is_active=user_active,
            is_staff=superuser,
            is_superuser=superuser,
        )
        user.groups.add(Group.objects.get(name=role))
        client = Cliente.objects.create(usuario=user, zona='Centro')
        personal = self.create_personal(
            suffix,
            usuario=user,
            activo=personal_active,
        )
        return personal, user, client

    def url(self, personal_id):
        return reverse('personal-revocar-acceso-total', args=[personal_id])

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def post(self, personal_id, payload=None):
        if payload is None:
            payload = {'motivo': 'Fin de relacion laboral y acceso digital'}
        return self.client.post(
            self.url(personal_id),
            payload,
            format='json',
        )

    def test_valid_full_revocation_returns_200_and_preserves_role(self):
        personal, user, client = self.create_linked_context(
            'valid',
            BusinessRole.PROFESIONAL,
        )
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['personal_id'], personal.pk)
        self.assertEqual(response.data['usuario_id'], user.pk)
        self.assertTrue(response.data['personal_activo_anterior'])
        self.assertFalse(response.data['personal_activo_actual'])
        self.assertTrue(response.data['usuario_activo_anterior'])
        self.assertFalse(response.data['usuario_activo_actual'])
        self.assertEqual(
            response.data['rol_actual'],
            BusinessRole.PROFESIONAL,
        )

        personal.refresh_from_db()
        user.refresh_from_db()
        client.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertFalse(user.is_active)
        self.assertEqual(personal.usuario, user)
        self.assertEqual(
            get_business_roles(user),
            (BusinessRole.PROFESIONAL,),
        )
        self.assertEqual(client.zona, 'Centro')

    def test_final_state_noop_returns_200_without_audit(self):
        personal, user, _ = self.create_linked_context(
            'noop',
            personal_active=False,
            user_active=False,
        )
        audit_count = Auditoria.objects.count()
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertFalse(response.data['personal_activo_actual'])
        self.assertFalse(response.data['usuario_activo_actual'])
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assertFalse(
            Auditoria.objects.filter(
                tabla=FULL_WORK_ACCESS_REVOCATION_AUDIT_TABLE
            ).exists()
        )
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))

    def test_unauthenticated_request_returns_401(self):
        personal, _, _ = self.create_linked_context('anonymous')

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_actor_requires_both_permissions_without_staff_shortcut(self):
        personal, user, _ = self.create_linked_context('denied')
        permission_sets = (
            (),
            (self.manage_personal,),
            (self.manage_users,),
        )

        for index, permissions in enumerate(permission_sets, start=1):
            with self.subTest(permissions=permissions):
                actor = self.create_user(
                    f'full-revoke-api-denied-{index}@test.com',
                    is_staff=True,
                )
                actor.user_permissions.add(*permissions)
                self.authenticate(actor)

                response = self.post(personal.pk)

                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'PERMISSION_DENIED',
                )

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(user.is_active)

    def test_self_deactivation_returns_stable_403(self):
        self.actor.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        personal = self.create_personal('self-target', usuario=self.actor)
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'SELF_DEACTIVATION_NOT_ALLOWED',
        )
        personal.refresh_from_db()
        self.actor.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(self.actor.is_active)

    def test_last_active_administrator_returns_stable_403(self):
        personal, user, _ = self.create_linked_context(
            'last-admin',
            BusinessRole.ADMINISTRADOR,
        )
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'LAST_ACTIVE_ADMIN',
        )
        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(user.is_active)

    def test_superuser_returns_stable_403(self):
        personal, user, _ = self.create_linked_context(
            'superuser',
            BusinessRole.ADMINISTRADOR,
            superuser=True,
        )
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'PROTECTED_SUPERUSER',
        )
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_nonexistent_personal_returns_stable_404(self):
        self.authenticate()

        response = self.post(999999)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'PERSONAL_NOT_FOUND')

    def test_personal_without_user_returns_stable_409(self):
        personal = self.create_personal('without-user')
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'PERSONAL_HAS_NO_USER',
        )
        personal.refresh_from_db()
        self.assertTrue(personal.activo)

    def test_invalid_reason_and_unexpected_fields_return_stable_400(self):
        personal, user, _ = self.create_linked_context('invalid-payload')
        self.authenticate()

        invalid_reason = self.post(personal.pk, {'motivo': ' '})
        self.assertEqual(
            invalid_reason.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_reason.data['error']['code'],
            'INVALID_REASON',
        )

        payload = {
            'motivo': 'Intento con campos no permitidos',
            'role': BusinessRole.CLIENTE,
            'is_active': False,
            'activo': False,
            'groups': [],
            'password': 'unsafe',
            'usuario': user.pk,
            'skills': [],
        }
        unexpected = self.post(personal.pk, payload)
        self.assertEqual(unexpected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            unexpected.data['error']['code'],
            'INVALID_PAYLOAD',
        )
        self.assertSetEqual(
            set(unexpected.data['error']['fields']),
            set(payload) - {'motivo'},
        )

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(user.is_active)

    def test_multiple_roles_continue_with_warning_and_no_correction(self):
        personal, user, _ = self.create_linked_context('multiple-roles')
        user.groups.add(Group.objects.get(name=BusinessRole.PROFESIONAL))
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertIsNone(response.data['rol_actual'])
        self.assertIn(
            'INCONSISTENT_BUSINESS_ROLES',
            response.data['warnings'],
        )
        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertFalse(user.is_active)
        self.assertSetEqual(
            set(get_business_roles(user)),
            {BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL},
        )

    def test_response_does_not_expose_secrets_or_audit_ids(self):
        personal, _, _ = self.create_linked_context('safe-response')
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        forbidden_fields = {
            'password',
            'token',
            'access',
            'refresh',
            'audit_id',
            'status_audit_id',
            'account_audit_id',
        }
        self.assertTrue(forbidden_fields.isdisjoint(response.data))
