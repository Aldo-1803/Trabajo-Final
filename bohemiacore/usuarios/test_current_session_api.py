from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from gestion.middleware import _thread_locals
from gestion.models import Personal
from usuarios.models import Cliente, Usuario
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    ROLE_BASE_PERMISSIONS,
)


class CurrentSessionApiTests(APITestCase):
    def setUp(self):
        self.url = reverse('current-session')

    def tearDown(self):
        # AuditoriaMiddleware keeps the JWT user in thread-local storage.
        _thread_locals.user = None
        _thread_locals.request = None

    def create_user(self, suffix, **extra_fields):
        return Usuario.objects.create_user(
            email=f'{suffix}@test.com',
            password='SessionPassword!2026',
            first_name='Ana',
            last_name='Pérez',
            **extra_fields,
        )

    def assign_role(self, user, role):
        user.groups.add(Group.objects.get(name=role))

    def create_cliente(self, user, *, active=True):
        return Cliente.objects.create(usuario=user, activo=active)

    def create_personal(
        self,
        user,
        *,
        active=True,
        function_role='asistente',
    ):
        return Personal.objects.create(
            usuario=user,
            nombre='Ana',
            apellido='Pérez',
            rol=function_role,
            activo=active,
        )

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def get_session(self, user):
        self.authenticate(user)
        return self.client.get(self.url)

    def expected_permissions(self, role):
        return sorted(ROLE_BASE_PERMISSIONS[role])

    def test_cliente_returns_role_empty_base_permissions_and_profile(self):
        user = self.create_user('cliente')
        cliente = self.create_cliente(user)
        self.assign_role(user, BusinessRole.CLIENTE)

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            'user': {
                'id': user.pk,
                'email': user.email,
                'first_name': 'Ana',
                'last_name': 'Pérez',
                'is_active': True,
            },
            'business_role': BusinessRole.CLIENTE,
            'permissions': [],
            'profiles': {
                'cliente': {
                    'exists': True,
                    'id': cliente.pk,
                    'active': True,
                },
                'personal': {
                    'exists': False,
                    'id': None,
                    'active': None,
                    'function_role': None,
                },
            },
        })
        self.assertNotIn('is_staff', response.data['user'])
        self.assertNotIn('is_superuser', response.data['user'])

    def test_employee_returns_group_base_permissions(self):
        user = self.create_user('employee')
        self.create_personal(user)
        self.assign_role(user, BusinessRole.EMPLEADO)

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['business_role'], BusinessRole.EMPLEADO)
        self.assertEqual(
            response.data['permissions'],
            self.expected_permissions(BusinessRole.EMPLEADO),
        )

    def test_professional_returns_employee_and_technical_permissions(self):
        user = self.create_user('professional')
        self.create_personal(user, function_role='colorista')
        self.assign_role(user, BusinessRole.PROFESIONAL)

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['permissions'],
            self.expected_permissions(BusinessRole.PROFESIONAL),
        )
        self.assertTrue(
            set(ROLE_BASE_PERMISSIONS[BusinessRole.EMPLEADO])
            < set(response.data['permissions'])
        )

    def test_administrator_returns_complete_business_catalog(self):
        user = self.create_user('administrator')
        self.assign_role(user, BusinessRole.ADMINISTRADOR)

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['permissions'],
            sorted(BusinessPermission.ALL),
        )

    def test_individual_permission_is_added_without_changing_role(self):
        user = self.create_user('individual')
        self.create_personal(user)
        self.assign_role(user, BusinessRole.EMPLEADO)
        user.user_permissions.add(self.permission(BusinessPermission.MANAGE_STOCK))

        response = self.get_session(user)

        self.assertEqual(response.data['business_role'], BusinessRole.EMPLEADO)
        self.assertIn(BusinessPermission.MANAGE_STOCK, response.data['permissions'])

    def test_cliente_and_personal_profiles_can_coexist(self):
        user = self.create_user('coexistence')
        cliente = self.create_cliente(user)
        personal = self.create_personal(user, function_role='colorista')
        self.assign_role(user, BusinessRole.PROFESIONAL)

        response = self.get_session(user)

        self.assertEqual(response.data['profiles'], {
            'cliente': {
                'exists': True,
                'id': cliente.pk,
                'active': True,
            },
            'personal': {
                'exists': True,
                'id': personal.pk,
                'active': True,
                'function_role': 'colorista',
            },
        })

    def test_inactive_personal_is_reported_without_hiding_profile(self):
        user = self.create_user('inactive-personal')
        personal = self.create_personal(user, active=False)
        self.assign_role(user, BusinessRole.EMPLEADO)

        response = self.get_session(user)

        self.assertEqual(response.data['profiles']['personal'], {
            'exists': True,
            'id': personal.pk,
            'active': False,
            'function_role': 'asistente',
        })

    def test_inactive_cliente_is_reported_without_hiding_profile(self):
        user = self.create_user('inactive-client')
        cliente = self.create_cliente(user, active=False)
        self.assign_role(user, BusinessRole.CLIENTE)

        response = self.get_session(user)

        self.assertEqual(response.data['profiles']['cliente'], {
            'exists': True,
            'id': cliente.pk,
            'active': False,
        })

    def test_roleless_user_returns_null_role_and_absent_profiles(self):
        user = self.create_user('roleless')

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['business_role'])
        self.assertEqual(response.data['profiles'], {
            'cliente': {
                'exists': False,
                'id': None,
                'active': None,
            },
            'personal': {
                'exists': False,
                'id': None,
                'active': None,
                'function_role': None,
            },
        })

    def test_roleless_user_does_not_infer_role_from_profiles_or_staff(self):
        user = self.create_user('roleless-staff', is_staff=True)
        self.create_cliente(user)
        self.create_personal(user, function_role='administrador')

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['business_role'])

    def test_multiple_business_roles_fail_closed_with_stable_error(self):
        user = self.create_user('multiple')
        user.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data, {
            'error': {
                'code': 'MULTIPLE_BUSINESS_ROLES',
                'detail': 'El Usuario tiene múltiples roles de negocio.',
            }
        })

    def test_superuser_without_role_stays_roleless_and_is_catalog_limited(self):
        user = self.create_user(
            'superuser',
            is_staff=True,
            is_superuser=True,
        )

        response = self.get_session(user)

        self.assertIsNone(response.data['business_role'])
        self.assertEqual(response.data['permissions'], sorted(BusinessPermission.ALL))
        self.assertNotIn('is_superuser', response.data['user'])

    def test_personal_function_role_never_changes_business_role(self):
        user = self.create_user('function-role')
        self.create_personal(user, function_role='administrador')
        self.assign_role(user, BusinessRole.EMPLEADO)

        response = self.get_session(user)

        self.assertEqual(response.data['business_role'], BusinessRole.EMPLEADO)
        self.assertEqual(
            response.data['profiles']['personal']['function_role'],
            'administrador',
        )

    def test_group_and_individual_permissions_are_combined(self):
        user = self.create_user('combined')
        self.create_personal(user)
        self.assign_role(user, BusinessRole.EMPLEADO)
        user.user_permissions.add(self.permission(BusinessPermission.VIEW_REPORTS))

        response = self.get_session(user)

        expected = set(ROLE_BASE_PERMISSIONS[BusinessRole.EMPLEADO])
        expected.add(BusinessPermission.VIEW_REPORTS)
        self.assertEqual(response.data['permissions'], sorted(expected))

    def test_permissions_exclude_non_business_catalog_permissions(self):
        user = self.create_user('filtered')
        self.assign_role(user, BusinessRole.CLIENTE)
        outside_catalog = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='add_usuario',
        )
        user.user_permissions.add(outside_catalog)

        response = self.get_session(user)

        self.assertEqual(response.data['permissions'], [])
        self.assertNotIn('usuarios.add_usuario', response.data['permissions'])

    def test_permissions_are_sorted_deterministically(self):
        user = self.create_user('sorted')
        self.assign_role(user, BusinessRole.CLIENTE)
        permission_labels = (
            BusinessPermission.VIEW_REPORTS,
            BusinessPermission.MANAGE_STOCK,
            BusinessPermission.CREATE_WALKIN_CLIENT,
        )
        user.user_permissions.add(*[
            self.permission(label) for label in permission_labels
        ])

        first_response = self.get_session(user)
        second_response = self.client.get(self.url)

        self.assertEqual(
            first_response.data['permissions'],
            sorted(permission_labels),
        )
        self.assertEqual(
            second_response.data['permissions'],
            first_response.data['permissions'],
        )

    def test_anonymous_request_returns_401(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_jwt_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid-token')

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_mutating_methods_are_not_allowed(self):
        user = self.create_user('methods')
        self.authenticate(user)

        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.url,
                    {},
                    format='json',
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_405_METHOD_NOT_ALLOWED,
                )

    @staticmethod
    def permission(label):
        app_label, codename = label.split('.', 1)
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )
