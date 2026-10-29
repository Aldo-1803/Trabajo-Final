from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Personal
from usuarios.access_services import ACCOUNT_REACTIVATION_AUDIT_TABLE
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class AccountReactivationActionTests(APITestCase):
    def setUp(self):
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.actor = self.create_user('reactivate-api-actor@test.com')
        self.actor.user_permissions.add(self.manage_users)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def assign_role(self, user, role):
        user.groups.add(Group.objects.get(name=role))

    def create_personal(self, user, *, activo=True):
        return Personal.objects.create(
            usuario=user,
            nombre='Cuenta',
            apellido='API',
            rol='asistente',
            activo=activo,
        )

    def url(self, user_id):
        return reverse('admin-usuarios-reactivar-cuenta', args=[user_id])

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def post(self, user_id, payload=None):
        if payload is None:
            payload = {'motivo': 'Reincorporacion digital aprobada'}
        return self.client.post(self.url(user_id), payload, format='json')

    def test_valid_reactivation_returns_200_and_preserves_client(self):
        target = self.create_user(
            'reactivate-api-client@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.CLIENTE)
        client = Cliente.objects.create(
            usuario=target,
            zona='Centro',
            activo=False,
        )
        self.authenticate()

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['usuario_id'], target.pk)
        self.assertFalse(response.data['usuario_activo_anterior'])
        self.assertTrue(response.data['usuario_activo_actual'])
        self.assertEqual(response.data['rol_actual'], BusinessRole.CLIENTE)
        self.assertIn('CLIENT_PROFILE_INACTIVE', response.data['warnings'])
        self.assertIn(
            'PREEXISTING_TOKENS_MAY_REGAIN_VALIDITY',
            response.data['warnings'],
        )
        target.refresh_from_db()
        client.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertFalse(client.activo)
        self.assertEqual(client.zona, 'Centro')
        self.assertEqual(get_business_roles(target), (BusinessRole.CLIENTE,))

    def test_coherent_active_account_returns_200_noop_without_audit(self):
        target = self.create_user(
            'reactivate-api-noop@test.com',
            is_active=True,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        audit_count = Auditoria.objects.count()
        self.authenticate()

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertTrue(response.data['usuario_activo_anterior'])
        self.assertTrue(response.data['usuario_activo_actual'])
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assertFalse(
            Auditoria.objects.filter(
                tabla=ACCOUNT_REACTIVATION_AUDIT_TABLE
            ).exists()
        )

    def test_unauthenticated_request_returns_401(self):
        target = self.create_user(
            'reactivate-api-anonymous@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_manage_users_is_required_without_staff_shortcut(self):
        actor = self.create_user(
            'reactivate-api-denied@test.com',
            is_staff=True,
        )
        target = self.create_user(
            'reactivate-api-denied-target@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.authenticate(actor)

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_administrative_self_service_returns_permission_denied(self):
        self.assign_role(self.actor, BusinessRole.ADMINISTRADOR)
        self.authenticate()

        response = self.post(self.actor.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')

    def test_superuser_returns_stable_403(self):
        target = self.create_user(
            'reactivate-api-superuser@test.com',
            is_active=False,
            is_staff=True,
            is_superuser=True,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.authenticate()

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'PROTECTED_SUPERUSER',
        )
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_nonexistent_user_returns_stable_404(self):
        self.authenticate()

        response = self.post(999999)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'USER_NOT_FOUND')

    def test_role_state_inconsistencies_return_stable_409(self):
        roleless = self.create_user(
            'reactivate-api-roleless@test.com',
            is_active=False,
        )
        multiple = self.create_user(
            'reactivate-api-multiple@test.com',
            is_active=False,
        )
        multiple.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )
        self.authenticate()

        cases = (
            (roleless, 'USER_HAS_NO_BUSINESS_ROLE'),
            (multiple, 'INCONSISTENT_BUSINESS_ROLES'),
        )
        for target, error_code in cases:
            with self.subTest(error_code=error_code):
                response = self.post(target.pk)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_409_CONFLICT,
                )
                self.assertEqual(response.data['error']['code'], error_code)

    def test_profile_inconsistencies_return_stable_409(self):
        client_missing = self.create_user(
            'reactivate-api-client-missing@test.com',
            is_active=False,
        )
        self.assign_role(client_missing, BusinessRole.CLIENTE)

        personal_missing = self.create_user(
            'reactivate-api-personal-missing@test.com',
            is_active=False,
        )
        self.assign_role(personal_missing, BusinessRole.PROFESIONAL)

        personal_inactive = self.create_user(
            'reactivate-api-personal-inactive@test.com',
            is_active=False,
        )
        self.assign_role(personal_inactive, BusinessRole.EMPLEADO)
        linked_personal = self.create_personal(
            personal_inactive,
            activo=False,
        )
        self.authenticate()

        cases = (
            (client_missing, 'CLIENT_PROFILE_REQUIRED'),
            (personal_missing, 'PERSONAL_PROFILE_REQUIRED'),
            (personal_inactive, 'PERSONAL_INACTIVE'),
        )
        for target, error_code in cases:
            with self.subTest(error_code=error_code):
                response = self.post(target.pk)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_409_CONFLICT,
                )
                self.assertEqual(response.data['error']['code'], error_code)
                target.refresh_from_db()
                self.assertFalse(target.is_active)

        linked_personal.refresh_from_db()
        self.assertFalse(linked_personal.activo)

    def test_invalid_reason_and_unexpected_fields_return_stable_400(self):
        target = self.create_user(
            'reactivate-api-invalid-payload@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.authenticate()

        invalid_reason = self.post(target.pk, {'motivo': ' '})
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
            'is_active': True,
            'role': BusinessRole.CLIENTE,
            'groups': [],
            'password': 'unsafe',
            'is_staff': True,
            'is_superuser': True,
        }
        unexpected = self.post(target.pk, payload)
        self.assertEqual(unexpected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            unexpected.data['error']['code'],
            'INVALID_PAYLOAD',
        )
        self.assertSetEqual(
            set(unexpected.data['error']['fields']),
            set(payload) - {'motivo'},
        )
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_response_contains_no_sensitive_or_internal_fields(self):
        target = self.create_user(
            'reactivate-api-safe-response@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.authenticate()

        response = self.post(target.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        forbidden_fields = {
            'password',
            'token',
            'access',
            'refresh',
            'audit_id',
            'groups',
            'user_permissions',
        }
        self.assertTrue(forbidden_fields.isdisjoint(response.data))
