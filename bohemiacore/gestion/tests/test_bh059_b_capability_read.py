import json

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.middleware import _thread_locals
from gestion.models import Personal
from usuarios.models import Cliente, Usuario
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    ROLE_BASE_PERMISSIONS,
)


class AdministrativeCapabilityReadTests(APITestCase):
    def setUp(self):
        _thread_locals.user = None
        _thread_locals.request = None
        self.manager = self.create_user('capability-manager@test.com')
        self.manager.user_permissions.add(
            self.permission('usuarios', 'manage_users')
        )
        self.staff_only = self.create_user(
            'capability-staff@test.com',
            is_staff=True,
        )

    def tearDown(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().tearDown()

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='CapabilityRead!2026',
            **extra_fields,
        )

    @staticmethod
    def permission(app_label, codename):
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    @staticmethod
    def warning_codes(data):
        return [warning['code'] for warning in data['warnings']]

    def url(self, user):
        return reverse('admin-usuarios-resumen-acceso', args=[user.pk])

    def get_summary(self, user, actor=None):
        self.client.force_authenticate(user=actor or self.manager)
        return self.client.get(self.url(user))

    def test_manage_users_is_required_without_staff_shortcut(self):
        target = self.create_user('capability-auth-target@test.com')

        denied = self.get_summary(target, self.staff_only)
        allowed = self.get_summary(target)

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertFalse(self.manager.is_staff)

    def test_unique_role_and_both_profiles_are_projected_separately(self):
        target = self.create_user('capability-profiles@test.com')
        self.assign_role(target, BusinessRole.PROFESIONAL)
        cliente = Cliente.objects.create(usuario=target, activo=False)
        personal = Personal.objects.create(
            usuario=target,
            nombre='Perfil',
            apellido='Profesional',
            rol='colorista',
            activo=True,
        )

        response = self.get_summary(target)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data['business_role'], BusinessRole.PROFESIONAL)
        self.assertEqual(data['business_roles'], [BusinessRole.PROFESIONAL])
        self.assertEqual(data['role_state'], 'VALID')
        self.assertEqual(data['profiles']['cliente'], {
            'exists': True,
            'id': cliente.pk,
            'active': False,
        })
        self.assertEqual(data['profiles']['personal'], {
            'exists': True,
            'id': personal.pk,
            'active': True,
            'job_role': 'colorista',
        })
        expected_permissions = set(
            ROLE_BASE_PERMISSIONS[BusinessRole.PROFESIONAL]
        )
        expected = [
            code
            for code in BusinessPermission.ALL
            if code in expected_permissions
        ]
        self.assertEqual(data['assigned_capabilities'], expected)
        self.assertEqual(data['effective_capabilities'], expected)
        effective_set = set(data['effective_capabilities'])
        reloaded = Usuario.objects.get(pk=target.pk)
        for permission in BusinessPermission.ALL:
            self.assertEqual(
                permission in effective_set,
                reloaded.has_perm(permission),
            )

    def test_no_role_and_multiple_roles_are_reported_without_repair(self):
        roleless = self.create_user('capability-roleless@test.com')
        multiple = self.create_user('capability-multiple@test.com')
        multiple.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )
        role_ids_before = set(
            multiple.groups.values_list('pk', flat=True)
        )

        roleless_response = self.get_summary(roleless)
        multiple_response = self.get_summary(multiple)

        self.assertEqual(roleless_response.data['role_state'], 'NO_ROLE')
        self.assertIsNone(roleless_response.data['business_role'])
        self.assertIn('NO_ROLE', self.warning_codes(roleless_response.data))
        self.assertEqual(multiple_response.data['role_state'], 'MULTIPLE_ROLES')
        self.assertEqual(
            multiple_response.data['business_roles'],
            [BusinessRole.CLIENTE, BusinessRole.EMPLEADO],
        )
        self.assertIsNone(multiple_response.data['business_role'])
        self.assertIn(
            'MULTIPLE_ROLES',
            self.warning_codes(multiple_response.data),
        )
        self.assertIn(
            'MISSING_CLIENT_PROFILE',
            self.warning_codes(multiple_response.data),
        )
        self.assertIn(
            'MISSING_PERSONAL_PROFILE',
            self.warning_codes(multiple_response.data),
        )
        self.assertSetEqual(
            set(multiple.groups.values_list('pk', flat=True)),
            role_ids_before,
        )

    def test_inactive_account_distinguishes_assignments_from_django_effective(self):
        target = self.create_user('capability-inactive@test.com')
        self.assign_role(target, BusinessRole.EMPLEADO)
        Personal.objects.create(
            usuario=target,
            nombre='Cuenta',
            apellido='Inactiva',
            rol='asistente',
            activo=True,
        )
        target.user_permissions.add(
            self.permission('gestion', 'manage_content')
        )
        self.assertTrue(target.get_all_permissions())
        Usuario.objects.filter(pk=target.pk).update(is_active=False)

        response = self.get_summary(target)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertTrue(data['assigned_capabilities'])
        self.assertEqual(data['effective_capabilities'], [])
        self.assertTrue(all(
            capability['assigned'] and not capability['effective']
            for capability in data['capabilities']
        ))
        self.assertEqual(
            data['technical']['permission_evaluation'],
            'SUPPRESSED_INACTIVE_ACCOUNT',
        )
        self.assertIn(
            'INACTIVE_ACCOUNT_CAPABILITIES_NOT_EFFECTIVE',
            self.warning_codes(data),
        )
        reloaded = Usuario.objects.get(pk=target.pk)
        self.assertEqual(reloaded.get_all_permissions(), set())
        self.assertFalse(reloaded.has_perm(BusinessPermission.VIEW_STOCK))

    def test_active_and_inactive_superuser_follow_django_contract(self):
        target = Usuario.objects.create_superuser(
            email='capability-superuser@test.com',
            password='CapabilitySuperuser!2026',
        )

        active_response = self.get_summary(target)

        self.assertEqual(
            active_response.data['effective_capabilities'],
            list(BusinessPermission.ALL),
        )
        self.assertTrue(all(
            any(origin['type'] == 'SUPERUSER' for origin in capability['origins'])
            for capability in active_response.data['capabilities']
        ))
        self.assertIn(
            'SUPERUSER_ACCOUNT',
            self.warning_codes(active_response.data),
        )

        Usuario.objects.filter(pk=target.pk).update(is_active=False)
        inactive_response = self.get_summary(target)

        self.assertEqual(inactive_response.data['effective_capabilities'], [])
        self.assertEqual(inactive_response.data['capabilities'], [])
        superuser_warning = next(
            warning
            for warning in inactive_response.data['warnings']
            if warning['code'] == 'SUPERUSER_ACCOUNT'
        )
        self.assertFalse(superuser_warning['effective'])

    def test_capability_can_have_role_group_and_individual_origins(self):
        target = self.create_user('capability-origins@test.com')
        self.assign_role(target, BusinessRole.EMPLEADO)
        Personal.objects.create(
            usuario=target,
            nombre='Origen',
            apellido='Múltiple',
            rol='asistente',
            activo=True,
        )
        view_stock = self.permission('gestion', 'view_stock')
        manage_users = self.permission('usuarios', 'manage_users')
        technical_group = Group.objects.create(name='TECHNICAL_ACCESS_REVIEW')
        technical_group.permissions.add(view_stock, manage_users)
        target.groups.add(technical_group)
        target.user_permissions.add(view_stock)

        response = self.get_summary(target)

        capabilities = {
            capability['code']: capability
            for capability in response.data['capabilities']
        }
        self.assertEqual(
            capabilities[BusinessPermission.VIEW_STOCK]['origins'],
            [
                {'type': 'BUSINESS_ROLE', 'identifier': BusinessRole.EMPLEADO},
                {'type': 'TECHNICAL_GROUP', 'identifier': technical_group.name},
                {'type': 'INDIVIDUAL', 'identifier': None},
            ],
        )
        self.assertEqual(
            capabilities[BusinessPermission.MANAGE_USERS]['origins'],
            [{
                'type': 'TECHNICAL_GROUP',
                'identifier': technical_group.name,
            }],
        )
        warning_codes = self.warning_codes(response.data)
        self.assertIn('INDIVIDUAL_BUSINESS_PERMISSIONS', warning_codes)
        self.assertIn('TECHNICAL_GROUP_BUSINESS_PERMISSIONS', warning_codes)
        self.assertIn('ADMIN_CAPABILITIES_OUTSIDE_ROLE', warning_codes)

    def test_read_ignores_stale_permission_caches_on_supplied_instance(self):
        target = self.create_user('capability-stale-cache@test.com')
        self.assign_role(target, BusinessRole.EMPLEADO)
        Personal.objects.create(
            usuario=target,
            nombre='Cache',
            apellido='Obsoleta',
            rol='asistente',
            activo=True,
        )
        self.assertNotIn(
            BusinessPermission.MANAGE_USERS,
            target.get_all_permissions(),
        )
        fresh_target = Usuario.objects.get(pk=target.pk)
        fresh_target.user_permissions.add(
            self.permission('usuarios', 'manage_users')
        )
        self.assertNotIn(
            BusinessPermission.MANAGE_USERS,
            target.get_all_permissions(),
        )

        response = self.get_summary(target)

        self.assertIn(
            BusinessPermission.MANAGE_USERS,
            response.data['effective_capabilities'],
        )
        capability = next(
            item
            for item in response.data['capabilities']
            if item['code'] == BusinessPermission.MANAGE_USERS
        )
        self.assertEqual(
            capability['origins'],
            [{'type': 'INDIVIDUAL', 'identifier': None}],
        )

    def test_profile_anomalies_and_role_drift_are_visible(self):
        missing_profile = self.create_user('capability-missing-profile@test.com')
        self.assign_role(missing_profile, BusinessRole.EMPLEADO)
        inactive_personal = self.create_user('capability-inactive-personal@test.com')
        self.assign_role(inactive_personal, BusinessRole.PROFESIONAL)
        Personal.objects.create(
            usuario=inactive_personal,
            nombre='Personal',
            apellido='Inactivo',
            rol='colorista',
            activo=False,
        )
        employee_group = Group.objects.get(name=BusinessRole.EMPLEADO)
        employee_group.permissions.remove(
            self.permission('gestion', 'view_stock')
        )

        missing_response = self.get_summary(missing_profile)
        inactive_response = self.get_summary(inactive_personal)

        missing_codes = self.warning_codes(missing_response.data)
        self.assertIn('MISSING_PERSONAL_PROFILE', missing_codes)
        self.assertIn('ROLE_CAPABILITY_DRIFT', missing_codes)
        drift = next(
            warning
            for warning in missing_response.data['warnings']
            if warning['code'] == 'ROLE_CAPABILITY_DRIFT'
        )
        self.assertIn(BusinessPermission.VIEW_STOCK, drift['missing'])
        self.assertIn(
            'INACTIVE_PERSONAL_FOR_LABOR_ROLE',
            self.warning_codes(inactive_response.data),
        )

    def test_read_is_deterministic_sensitive_free_and_does_not_mutate(self):
        target = self.create_user('capability-deterministic@test.com')
        self.assign_role(target, BusinessRole.CLIENTE)
        Cliente.objects.create(usuario=target, activo=True)
        direct_permission = self.permission('gestion', 'view_reports')
        outside_catalog = self.permission('auth', 'add_group')
        target.user_permissions.add(direct_permission, outside_catalog)
        groups_before = list(
            target.groups.order_by('pk').values_list('pk', flat=True)
        )
        direct_before = list(
            target.user_permissions.order_by('pk').values_list('pk', flat=True)
        )

        first = self.get_summary(target)
        second = self.get_summary(target)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data, second.data)
        self.assertEqual(
            list(target.groups.order_by('pk').values_list('pk', flat=True)),
            groups_before,
        )
        self.assertEqual(
            list(
                target.user_permissions.order_by('pk')
                .values_list('pk', flat=True)
            ),
            direct_before,
        )
        serialized = json.dumps(first.data).lower()
        for sensitive_name in (
            'password',
            'token',
            'secret',
            'credential',
            'user_permissions',
            'permission_id',
        ):
            self.assertNotIn(sensitive_name, serialized)
        self.assertTrue(all(
            capability['code'] in BusinessPermission.ALL
            for capability in first.data['capabilities']
        ))
        self.assertIn(
            'PERMISSIONS_OUTSIDE_BUSINESS_CATALOG',
            self.warning_codes(first.data),
        )
        self.assertNotIn('auth.add_group', serialized)
