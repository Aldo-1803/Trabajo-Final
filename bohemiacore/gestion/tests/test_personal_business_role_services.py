from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from gestion.models import Auditoria, Personal
from gestion.personal_access_services import (
    PERSONAL_BUSINESS_ROLE_AUDIT_EVENT,
    PERSONAL_BUSINESS_ROLE_AUDIT_TABLE,
    InvalidPersonalBusinessRoleTarget,
    MultiplePersonalBusinessRoles,
    PermissionDeniedForPersonalBusinessRoleChange,
    PersonalBusinessRoleChangeNotAllowed,
    PersonalInactiveForRoleChange,
    PersonalWithoutUserForRoleChange,
    change_personal_business_role,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class PersonalBusinessRoleChangeServiceTests(TestCase):
    reason = 'Incorporación explícita al equipo'

    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('role-change-actor@test.com')
        self.actor.user_permissions.add(
            self.manage_personal,
            self.assign_roles,
        )

    def create_user(self, email, role=None, **extra_fields):
        user = Usuario.objects.create_user(
            email=email,
            password='StrongTestPassword!2026',
            **extra_fields,
        )
        if role is not None:
            user.groups.add(Group.objects.get(name=role))
        return user

    def create_context(self, suffix, role=BusinessRole.CLIENTE, **kwargs):
        user = self.create_user(
            f'role-change-{suffix}@test.com',
            role=role,
            is_staff=kwargs.pop('is_staff', False),
            is_superuser=kwargs.pop('is_superuser', False),
            is_active=kwargs.pop('is_active', True),
        )
        client = Cliente.objects.create(usuario=user, zona='Centro')
        personal = Personal.objects.create(
            usuario=user,
            nombre=f'Nombre {suffix}',
            apellido='Cambio Rol',
            rol='asistente',
            activo=kwargs.pop('personal_active', True),
        )
        return personal, user, client

    def change(self, personal, target_role, actor=None):
        return change_personal_business_role(
            actor=actor or self.actor,
            personal=personal,
            target_role=target_role,
            reason=self.reason,
        )

    def assert_transition(self, source, target, suffix):
        personal, user, client = self.create_context(suffix, source)

        result = self.change(personal, target)

        user.refresh_from_db()
        personal.refresh_from_db()
        client.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(result.previous_role, source)
        self.assertEqual(result.new_role, target)
        self.assertEqual(get_business_roles(user), (target,))
        self.assertEqual(personal.usuario, user)
        self.assertEqual(personal.rol, 'asistente')
        self.assertEqual(client.usuario, user)
        return result, personal, user, client

    def test_cliente_to_empleado_preserves_both_profiles(self):
        result, personal, user, client = self.assert_transition(
            BusinessRole.CLIENTE,
            BusinessRole.EMPLEADO,
            'client-employee',
        )

        self.assertEqual(result.personal_id, personal.pk)
        self.assertEqual(result.user_id, user.pk)
        self.assertEqual(result.client_id, client.pk)

    def test_cliente_to_profesional(self):
        self.assert_transition(
            BusinessRole.CLIENTE,
            BusinessRole.PROFESIONAL,
            'client-professional',
        )

    def test_empleado_to_profesional(self):
        self.assert_transition(
            BusinessRole.EMPLEADO,
            BusinessRole.PROFESIONAL,
            'employee-professional',
        )

    def test_profesional_to_empleado(self):
        self.assert_transition(
            BusinessRole.PROFESIONAL,
            BusinessRole.EMPLEADO,
            'professional-employee',
        )

    def test_same_role_is_noop_without_audit(self):
        personal, user, _ = self.create_context(
            'noop',
            BusinessRole.EMPLEADO,
        )
        audit_count = Auditoria.objects.count()

        result = self.change(personal, BusinessRole.EMPLEADO)

        self.assertFalse(result.changed)
        self.assertIsNone(result.audit_id)
        self.assertIsNone(result.role_audit_id)
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))

    def test_roleless_linked_user_can_receive_labor_role(self):
        personal, user, client = self.create_context('roleless', role=None)

        result = self.change(personal, BusinessRole.PROFESIONAL)

        self.assertTrue(result.changed)
        self.assertIsNone(result.previous_role)
        self.assertEqual(get_business_roles(user), (BusinessRole.PROFESIONAL,))
        self.assertTrue(Cliente.objects.filter(pk=client.pk).exists())
        self.assertTrue(Personal.objects.filter(pk=personal.pk).exists())

    def test_flags_permissions_and_technical_groups_are_unchanged(self):
        personal, user, _ = self.create_context(
            'technical-state',
            BusinessRole.CLIENTE,
            is_staff=True,
        )
        technical_group = Group.objects.create(name='TECHNICAL_TEST_GROUP')
        individual_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='view_audit',
        )
        user.groups.add(technical_group)
        user.user_permissions.add(individual_permission)
        original_flags = (user.is_staff, user.is_superuser, user.is_active)
        original_permissions = set(user.user_permissions.values_list('pk', flat=True))

        self.change(personal, BusinessRole.EMPLEADO)

        user.refresh_from_db()
        self.assertEqual(
            (user.is_staff, user.is_superuser, user.is_active),
            original_flags,
        )
        self.assertEqual(
            set(user.user_permissions.values_list('pk', flat=True)),
            original_permissions,
        )
        self.assertTrue(user.groups.filter(pk=technical_group.pk).exists())

    def test_personal_without_user_is_rejected(self):
        personal = Personal.objects.create(
            nombre='Sin',
            apellido='Usuario',
            rol='asistente',
            activo=True,
        )

        with self.assertRaises(PersonalWithoutUserForRoleChange):
            self.change(personal, BusinessRole.EMPLEADO)

    def test_inactive_personal_is_rejected(self):
        personal, user, _ = self.create_context(
            'inactive',
            BusinessRole.CLIENTE,
            personal_active=False,
        )

        with self.assertRaises(PersonalInactiveForRoleChange):
            self.change(personal, BusinessRole.EMPLEADO)

        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_cliente_and_administrador_targets_are_rejected(self):
        personal, user, _ = self.create_context(
            'invalid-target',
            BusinessRole.CLIENTE,
        )

        for role in (BusinessRole.CLIENTE, BusinessRole.ADMINISTRADOR):
            with self.subTest(role=role):
                with self.assertRaises(InvalidPersonalBusinessRoleTarget):
                    self.change(personal, role)

        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_current_administrator_is_rejected_even_for_superuser_actor(self):
        personal, user, _ = self.create_context(
            'current-admin',
            BusinessRole.ADMINISTRADOR,
        )
        superuser = Usuario.objects.create_superuser(
            email='role-change-superuser@test.com',
            password='StrongTestPassword!2026',
        )

        with self.assertRaises(PersonalBusinessRoleChangeNotAllowed):
            self.change(personal, BusinessRole.EMPLEADO, actor=superuser)

        self.assertEqual(
            get_business_roles(user),
            (BusinessRole.ADMINISTRADOR,),
        )

    def test_multiple_business_roles_are_rejected(self):
        personal, user, _ = self.create_context(
            'multiple',
            BusinessRole.CLIENTE,
        )
        user.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))

        with self.assertRaises(MultiplePersonalBusinessRoles):
            self.change(personal, BusinessRole.PROFESIONAL)

        self.assertEqual(
            set(get_business_roles(user)),
            {BusinessRole.CLIENTE, BusinessRole.EMPLEADO},
        )

    def test_actor_requires_manage_personal_and_assign_roles(self):
        personal, user, _ = self.create_context(
            'permissions',
            BusinessRole.CLIENTE,
        )
        permission_sets = (
            (),
            (self.manage_personal,),
            (self.assign_roles,),
        )

        for index, permissions in enumerate(permission_sets, start=1):
            with self.subTest(permissions=permissions):
                actor = self.create_user(f'denied-role-change-{index}@test.com')
                actor.user_permissions.add(*permissions)
                with self.assertRaises(
                    PermissionDeniedForPersonalBusinessRoleChange
                ):
                    self.change(
                        personal,
                        BusinessRole.EMPLEADO,
                        actor=actor,
                    )

        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_semantic_audit_contains_profiles_and_reason(self):
        result, personal, user, client = self.assert_transition(
            BusinessRole.CLIENTE,
            BusinessRole.PROFESIONAL,
            'audit',
        )

        audit = Auditoria.objects.get(pk=result.audit_id)
        self.assertEqual(audit.tabla, PERSONAL_BUSINESS_ROLE_AUDIT_TABLE)
        self.assertEqual(
            audit.valor_nuevo['event'],
            PERSONAL_BUSINESS_ROLE_AUDIT_EVENT,
        )
        self.assertEqual(audit.valor_nuevo['personal_id'], personal.pk)
        self.assertEqual(audit.valor_nuevo['user_id'], user.pk)
        self.assertEqual(audit.valor_nuevo['client_id'], client.pk)
        self.assertEqual(audit.valor_nuevo['previous_role'], BusinessRole.CLIENTE)
        self.assertEqual(audit.valor_nuevo['new_role'], BusinessRole.PROFESIONAL)
        self.assertEqual(audit.valor_nuevo['reason'], self.reason)
        self.assertTrue(audit.valor_nuevo['client_profile_preserved'])
        self.assertTrue(audit.valor_nuevo['personal_profile_preserved'])

    def test_audit_failure_rolls_back_role_change(self):
        personal, user, client = self.create_context(
            'audit-failure',
            BusinessRole.CLIENTE,
        )

        with patch(
            'gestion.personal_access_services.'
            '_write_personal_business_role_audit',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                self.change(personal, BusinessRole.EMPLEADO)

        user.refresh_from_db()
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertTrue(Cliente.objects.filter(pk=client.pk).exists())
        self.assertTrue(Personal.objects.filter(pk=personal.pk).exists())
        self.assertFalse(
            Auditoria.objects.filter(
                tabla=PERSONAL_BUSINESS_ROLE_AUDIT_TABLE,
                registro_id=personal.pk,
            ).exists()
        )
