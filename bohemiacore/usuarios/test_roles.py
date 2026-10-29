from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase

from gestion.models import Personal
from usuarios.models import Cliente, Usuario
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    InconsistentBusinessRoleError,
    assign_business_role,
    get_business_role,
    get_business_role_groups,
    get_business_roles,
    has_business_role,
    has_inconsistent_business_roles,
)


EMPLOYEE_PERMISSIONS = {
    'usuarios.create_walkin_client',
    'usuarios.view_clients',
    'gestion.view_global_agenda',
    'gestion.create_turno_for_client',
    'gestion.register_arrival',
    'gestion.reprogram_any_turno',
    'gestion.cancel_any_turno',
    'gestion.register_payment',
    'gestion.view_stock',
}

PROFESSIONAL_PERMISSIONS = (EMPLOYEE_PERMISSIONS - {
    'gestion.register_payment',
}) | {
    'gestion.create_diagnosis',
    'gestion.manage_technical_record',
    'gestion.manage_formulas',
    'gestion.assign_routines',
    'gestion.finalize_service',
    'gestion.review_technical_booking',
}

ALL_BUSINESS_PERMISSIONS = {
    'usuarios.create_walkin_client',
    'usuarios.view_clients',
    'usuarios.manage_users',
    'usuarios.assign_roles',
    'gestion.view_global_agenda',
    'gestion.create_turno_for_client',
    'gestion.register_arrival',
    'gestion.reprogram_any_turno',
    'gestion.cancel_any_turno',
    'gestion.finalize_service',
    'gestion.confirm_deposit',
    'gestion.register_payment',
    'gestion.reconcile_external_payment',
    'gestion.manage_payment_configuration',
    'gestion.create_diagnosis',
    'gestion.manage_technical_record',
    'gestion.manage_formulas',
    'gestion.assign_routines',
    'gestion.manage_products',
    'gestion.view_stock',
    'gestion.manage_stock',
    'gestion.manage_prices',
    'gestion.manage_promotions',
    'gestion.manage_content',
    'gestion.manage_personal',
    'gestion.manage_skills',
    'gestion.view_reports',
    'gestion.view_financial_reports',
    'gestion.view_audit',
    'gestion.revert_audit',
    'gestion.manage_configuration',
    'gestion.review_technical_booking',
    'gestion.manage_technical_risk_policy',
}


class BusinessRoleInfrastructureTests(TestCase):
    def create_user(self, email='roles@test.com', **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def group_permissions(self, role):
        return {
            f'{permission.content_type.app_label}.{permission.codename}'
            for permission in Group.objects.get(name=role)
            .permissions.select_related('content_type')
        }

    def test_four_business_role_groups_exist(self):
        self.assertSetEqual(
            set(get_business_role_groups().values_list('name', flat=True)),
            set(BusinessRole.ALL),
        )

    def test_groups_have_exact_base_permissions(self):
        expected = {
            BusinessRole.CLIENTE: set(),
            BusinessRole.EMPLEADO: EMPLOYEE_PERMISSIONS,
            BusinessRole.PROFESIONAL: PROFESSIONAL_PERMISSIONS,
            BusinessRole.ADMINISTRADOR: ALL_BUSINESS_PERMISSIONS,
        }

        for role, permissions in expected.items():
            with self.subTest(role=role):
                self.assertSetEqual(self.group_permissions(role), permissions)

    def test_role_seed_is_idempotent(self):
        migration = import_module(
            'gestion.migrations.0020_seed_business_roles'
        )
        schema_editor = SimpleNamespace(connection=connection)

        migration.seed_business_roles(apps, schema_editor)
        first_state = {
            role: self.group_permissions(role) for role in BusinessRole.ALL
        }
        migration.seed_business_roles(apps, schema_editor)
        second_state = {
            role: self.group_permissions(role) for role in BusinessRole.ALL
        }

        self.assertEqual(second_state, first_state)
        self.assertEqual(
            Group.objects.filter(name__in=BusinessRole.ALL).count(),
            len(BusinessRole.ALL),
        )

    def test_employee_has_no_administrative_permissions(self):
        permissions = self.group_permissions(BusinessRole.EMPLEADO)

        self.assertTrue(EMPLOYEE_PERMISSIONS <= permissions)
        self.assertTrue(
            {
                'usuarios.manage_users',
                'usuarios.assign_roles',
                'gestion.manage_prices',
                'gestion.manage_configuration',
            }.isdisjoint(permissions)
        )

    def test_professional_has_technical_but_not_administrative_permissions(self):
        permissions = self.group_permissions(BusinessRole.PROFESIONAL)

        self.assertTrue(
            {
                'gestion.create_diagnosis',
                'gestion.manage_technical_record',
                'gestion.manage_formulas',
                'gestion.assign_routines',
                'gestion.finalize_service',
                'gestion.review_technical_booking',
            }
            <= permissions
        )
        self.assertTrue(
            {
                'gestion.manage_prices',
                'gestion.manage_promotions',
                'gestion.view_reports',
            }.isdisjoint(permissions)
        )

    def test_administrator_has_every_business_permission(self):
        self.assertSetEqual(
            self.group_permissions(BusinessRole.ADMINISTRADOR),
            ALL_BUSINESS_PERMISSIONS,
        )
        self.assertSetEqual(
            set(BusinessPermission.ALL),
            ALL_BUSINESS_PERMISSIONS,
        )

    def test_user_with_one_business_group_returns_role(self):
        user = self.create_user()
        user.groups.add(Group.objects.get(name=BusinessRole.PROFESIONAL))

        self.assertEqual(get_business_roles(user), (BusinessRole.PROFESIONAL,))
        self.assertEqual(get_business_role(user), BusinessRole.PROFESIONAL)
        self.assertTrue(has_business_role(user, BusinessRole.PROFESIONAL))

    def test_user_without_business_group_is_legacy_without_role(self):
        user = self.create_user()

        self.assertEqual(get_business_roles(user), ())
        self.assertIsNone(get_business_role(user))
        self.assertFalse(has_inconsistent_business_roles(user))

    def test_user_with_two_business_groups_is_inconsistent(self):
        user = self.create_user()
        user.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )

        self.assertTrue(has_inconsistent_business_roles(user))
        with self.assertRaises(InconsistentBusinessRoleError):
            get_business_role(user)

    def test_assign_role_replaces_only_business_role(self):
        user = self.create_user(is_staff=True, is_superuser=True)
        technical_group = Group.objects.create(name='TECHNICAL_GROUP')
        user.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.PROFESIONAL),
            technical_group,
        )
        cliente = Cliente.objects.create(usuario=user)
        personal = Personal.objects.create(
            usuario=user,
            nombre='Ana',
            apellido='Prueba',
            rol='colorista',
        )

        assign_business_role(user, BusinessRole.EMPLEADO)

        user.refresh_from_db()
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))
        self.assertSetEqual(
            set(user.groups.values_list('name', flat=True)),
            {BusinessRole.EMPLEADO, technical_group.name},
        )
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(Cliente.objects.filter(pk=cliente.pk, usuario=user).exists())
        self.assertTrue(
            Personal.objects.filter(pk=personal.pk, usuario=user).exists()
        )

    def test_assign_role_invalidates_cached_group_permissions(self):
        user = self.create_user()
        self.assertFalse(
            user.has_perm(BusinessPermission.CREATE_WALKIN_CLIENT)
        )

        assign_business_role(user, BusinessRole.EMPLEADO)

        self.assertTrue(
            user.has_perm(BusinessPermission.CREATE_WALKIN_CLIENT)
        )

    def test_individual_permission_is_recognized_by_has_perm(self):
        user = self.create_user()
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )

        user.user_permissions.add(permission)

        self.assertTrue(user.has_perm(BusinessPermission.MANAGE_PRICES))
