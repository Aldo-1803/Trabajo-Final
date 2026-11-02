import json
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import TestCase

from gestion.models import Auditoria, Personal
from usuarios.access_services import (
    InactivePersonal,
    InconsistentBusinessRoleState,
    InvalidBusinessRole,
    InvalidRoleChangeReason,
    MissingClientProfile,
    MissingPersonalProfile,
    PermissionDeniedForRoleAssignment,
    ProtectedSuperuser,
    ROLE_AUDIT_EVENT,
    ROLE_AUDIT_SOURCE,
    ROLE_AUDIT_TABLE,
    SelfRoleAssignmentNotAllowed,
    assign_validated_business_role,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_role, get_business_roles


class ValidatedBusinessRoleAssignmentTests(TestCase):
    def setUp(self):
        self.actor = self.create_user('actor@test.com')
        self.actor.groups.add(
            Group.objects.get(name=BusinessRole.ADMINISTRADOR)
        )

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def create_personal(self, user, *, activo=True, rol='asistente'):
        return Personal.objects.create(
            usuario=user,
            nombre='Ana',
            apellido='Prueba',
            rol=rol,
            activo=activo,
        )

    def semantic_audits(self):
        return Auditoria.objects.filter(tabla=ROLE_AUDIT_TABLE)

    def test_roleless_user_with_client_can_become_client(self):
        target = self.create_user('client-ok@test.com')
        Cliente.objects.create(usuario=target)

        result = assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.CLIENTE,
            'Alta inicial como cliente',
        )

        self.assertTrue(result.changed)
        self.assertIsNone(result.previous_role)
        self.assertEqual(result.new_role, BusinessRole.CLIENTE)
        self.assertEqual(get_business_role(target), BusinessRole.CLIENTE)

    def test_client_role_without_client_profile_is_rejected(self):
        target = self.create_user('client-missing@test.com')

        with self.assertRaises(MissingClientProfile):
            assign_validated_business_role(
                self.actor,
                target,
                BusinessRole.CLIENTE,
                'Alta como cliente',
            )

        self.assertEqual(get_business_roles(target), ())
        self.assertFalse(self.semantic_audits().exists())

    def test_active_personal_user_can_become_employee(self):
        target = self.create_user('employee-ok@test.com')
        self.create_personal(target)

        result = assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.EMPLEADO,
            'Alta laboral como empleado',
        )

        self.assertTrue(result.changed)
        self.assertEqual(get_business_role(target), BusinessRole.EMPLEADO)

    def test_employee_without_personal_is_rejected(self):
        target = self.create_user('employee-missing@test.com')

        with self.assertRaises(MissingPersonalProfile):
            assign_validated_business_role(
                self.actor,
                target,
                BusinessRole.EMPLEADO,
                'Alta laboral como empleado',
            )

        self.assertEqual(get_business_roles(target), ())

    def test_inactive_personal_rejects_employee_and_professional(self):
        for index, role in enumerate(
            (BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL),
            start=1,
        ):
            with self.subTest(role=role):
                target = self.create_user(f'inactive-{index}@test.com')
                self.create_personal(target, activo=False)

                with self.assertRaises(InactivePersonal):
                    assign_validated_business_role(
                        self.actor,
                        target,
                        role,
                        'Intento con personal inactivo',
                    )

                self.assertEqual(get_business_roles(target), ())

    def test_professional_does_not_depend_on_legacy_personal_role(self):
        target = self.create_user('professional-legacy@test.com')
        personal = self.create_personal(
            target,
            rol='asistente',
        )

        result = assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.PROFESIONAL,
            'Cambio a funcion profesional',
        )

        self.assertTrue(result.changed)
        self.assertEqual(get_business_role(target), BusinessRole.PROFESIONAL)
        personal.refresh_from_db()
        self.assertEqual(personal.rol, 'asistente')

    def test_administrator_does_not_require_personal(self):
        target = self.create_user('administrator@test.com')

        result = assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.ADMINISTRADOR,
            'Alta como administrador',
        )

        self.assertTrue(result.changed)
        self.assertEqual(get_business_role(target), BusinessRole.ADMINISTRADOR)
        self.assertFalse(hasattr(target, 'perfil_profesional'))

    def test_multiple_current_roles_are_rejected_without_correction(self):
        target = self.create_user('inconsistent@test.com')
        cliente_group = Group.objects.get(name=BusinessRole.CLIENTE)
        employee_group = Group.objects.get(name=BusinessRole.EMPLEADO)
        target.groups.add(cliente_group, employee_group)
        Cliente.objects.create(usuario=target)

        with self.assertRaises(InconsistentBusinessRoleState):
            assign_validated_business_role(
                self.actor,
                target,
                BusinessRole.CLIENTE,
                'Correccion no permitida',
            )

        self.assertSetEqual(
            set(target.groups.values_list('name', flat=True)),
            {BusinessRole.CLIENTE, BusinessRole.EMPLEADO},
        )
        self.assertFalse(self.semantic_audits().exists())

    def test_technical_group_is_preserved(self):
        target = self.create_user('technical-group@test.com')
        Cliente.objects.create(usuario=target)
        technical_group = Group.objects.create(name='TECHNICAL_EXTRA')
        target.groups.add(technical_group)

        assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.CLIENTE,
            'Alta conservando grupo tecnico',
        )

        self.assertSetEqual(
            set(target.groups.values_list('name', flat=True)),
            {BusinessRole.CLIENTE, technical_group.name},
        )

    def test_individual_permissions_are_preserved(self):
        target = self.create_user('individual-permission@test.com')
        Cliente.objects.create(usuario=target)
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        target.user_permissions.add(permission)

        assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.CLIENTE,
            'Alta conservando permiso individual',
        )

        self.assertSetEqual(
            set(target.user_permissions.values_list('pk', flat=True)),
            {permission.pk},
        )

    def test_account_flags_are_preserved(self):
        target = self.create_user(
            'flags@test.com',
            is_active=False,
            is_staff=True,
            is_superuser=False,
        )
        original_password = target.password
        self.create_personal(target)

        assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.EMPLEADO,
            'Alta sin modificar flags',
        )

        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertTrue(target.is_staff)
        self.assertFalse(target.is_superuser)
        self.assertEqual(target.password, original_password)

    def test_client_and_personal_profiles_are_preserved(self):
        target = self.create_user('profiles@test.com')
        cliente = Cliente.objects.create(usuario=target, zona='Centro')
        personal = self.create_personal(target, rol='administrador')

        assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.PROFESIONAL,
            'Cambio preservando perfiles',
        )

        cliente.refresh_from_db()
        personal.refresh_from_db()
        self.assertEqual(cliente.usuario, target)
        self.assertEqual(cliente.zona, 'Centro')
        self.assertEqual(personal.usuario, target)
        self.assertTrue(personal.activo)
        self.assertEqual(personal.rol, 'administrador')

    def test_valid_change_creates_exactly_one_semantic_audit(self):
        target = self.create_user('audit-count@test.com')
        Cliente.objects.create(usuario=target)

        result = assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.CLIENTE,
            'Alta auditada como cliente',
        )

        self.assertEqual(self.semantic_audits().count(), 1)
        self.assertEqual(result.audit_id, self.semantic_audits().get().pk)

    def test_audit_contains_actor_roles_reason_and_source(self):
        target = self.create_user('audit-content@test.com')
        Cliente.objects.create(usuario=target)
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        self.create_personal(target)

        assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.EMPLEADO,
            'Promocion laboral aprobada',
        )

        audit = self.semantic_audits().get()
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, target.pk)
        self.assertEqual(audit.valor_nuevo['event'], ROLE_AUDIT_EVENT)
        self.assertEqual(audit.valor_nuevo['source'], ROLE_AUDIT_SOURCE)
        self.assertEqual(audit.valor_nuevo['actor_id'], self.actor.pk)
        self.assertEqual(audit.valor_nuevo['target_user_id'], target.pk)
        self.assertEqual(
            audit.valor_nuevo['previous_role'], BusinessRole.CLIENTE
        )
        self.assertEqual(audit.valor_nuevo['new_role'], BusinessRole.EMPLEADO)
        self.assertEqual(
            audit.valor_nuevo['reason'], 'Promocion laboral aprobada'
        )
        self.assertEqual(
            audit.valor_nuevo['removed_business_groups'],
            [BusinessRole.CLIENTE],
        )
        self.assertEqual(
            audit.valor_nuevo['added_business_group'],
            BusinessRole.EMPLEADO,
        )

    def test_audit_contains_no_password_hash_or_tokens(self):
        target = self.create_user('audit-secrets@test.com')
        Cliente.objects.create(usuario=target)

        assign_validated_business_role(
            self.actor,
            target,
            BusinessRole.CLIENTE,
            'Alta sin datos sensibles',
        )

        audit = self.semantic_audits().get()
        payload = {
            'before': audit.valor_anterior,
            'after': audit.valor_nuevo,
        }
        payload_keys = set(payload['before']) | set(payload['after'])
        for forbidden_key in (
            'password',
            'password_hash',
            'token',
            'refresh_token',
            'access_token',
        ):
            self.assertNotIn(forbidden_key, payload_keys)

        serialized_payload = json.dumps(payload)
        self.assertNotIn(target.password, serialized_payload)
        self.assertNotIn(self.actor.password, serialized_payload)

    def test_audit_failure_rolls_back_group_change(self):
        target = self.create_user('audit-rollback@test.com')
        Cliente.objects.create(usuario=target)

        with patch(
            'usuarios.access_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                assign_validated_business_role(
                    self.actor,
                    target,
                    BusinessRole.CLIENTE,
                    'Alta que debe revertirse',
                )

        self.assertEqual(get_business_roles(target), ())
        self.assertFalse(self.semantic_audits().exists())

    def test_same_role_is_noop_without_audit_or_group_replacement(self):
        target = self.create_user('noop@test.com')
        Cliente.objects.create(usuario=target)
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))

        with patch('usuarios.access_services.assign_business_role') as assign:
            result = assign_validated_business_role(
                self.actor,
                target,
                BusinessRole.CLIENTE,
                'Confirmacion del rol existente',
            )

        self.assertFalse(result.changed)
        self.assertEqual(result.previous_role, BusinessRole.CLIENTE)
        self.assertEqual(result.new_role, BusinessRole.CLIENTE)
        self.assertIsNone(result.audit_id)
        assign.assert_not_called()
        self.assertFalse(self.semantic_audits().exists())

    def test_actor_without_assign_roles_permission_is_rejected(self):
        unauthorized_actor = self.create_user('unauthorized@test.com')
        target = self.create_user('unauthorized-target@test.com')
        Cliente.objects.create(usuario=target)

        with self.assertRaises(PermissionDeniedForRoleAssignment):
            assign_validated_business_role(
                unauthorized_actor,
                target,
                BusinessRole.CLIENTE,
                'Intento no autorizado',
            )

        self.assertEqual(get_business_roles(target), ())

    def test_invalid_actor_is_rejected(self):
        target = self.create_user('anonymous-target@test.com')
        Cliente.objects.create(usuario=target)

        with self.assertRaises(PermissionDeniedForRoleAssignment):
            assign_validated_business_role(
                AnonymousUser(),
                target,
                BusinessRole.CLIENTE,
                'Intento anonimo',
            )

    def test_superuser_target_is_rejected_without_changes(self):
        target = self.create_user(
            'superuser-target@test.com',
            is_staff=True,
            is_superuser=True,
        )

        with self.assertRaises(ProtectedSuperuser):
            assign_validated_business_role(
                self.actor,
                target,
                BusinessRole.ADMINISTRADOR,
                'Intento sobre superusuario',
            )

        target.refresh_from_db()
        self.assertTrue(target.is_staff)
        self.assertTrue(target.is_superuser)
        self.assertEqual(get_business_roles(target), ())

    def test_legacy_roleless_users_can_receive_labor_roles(self):
        for index, role in enumerate(
            (BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL),
            start=1,
        ):
            with self.subTest(role=role):
                target = self.create_user(f'legacy-{index}@test.com')
                self.create_personal(
                    target,
                    rol='administrador',
                )

                result = assign_validated_business_role(
                    self.actor,
                    target,
                    role,
                    'Asignacion inicial a usuario legacy',
                )

                self.assertTrue(result.changed)
                self.assertIsNone(result.previous_role)
                self.assertEqual(get_business_role(target), role)

    def test_actor_cannot_change_own_role(self):
        with self.assertRaises(SelfRoleAssignmentNotAllowed):
            assign_validated_business_role(
                self.actor,
                self.actor,
                BusinessRole.ADMINISTRADOR,
                'Autoasignacion no permitida',
            )

    def test_invalid_role_is_rejected(self):
        target = self.create_user('invalid-role@test.com')

        with self.assertRaises(InvalidBusinessRole):
            assign_validated_business_role(
                self.actor,
                target,
                'UNKNOWN',
                'Rol inexistente',
            )

    def test_reason_is_required_and_bounded(self):
        target = self.create_user('reason@test.com')
        Cliente.objects.create(usuario=target)

        for reason in (None, '', '  ', 'x', 'x' * 501):
            with self.subTest(reason=reason):
                with self.assertRaises(InvalidRoleChangeReason):
                    assign_validated_business_role(
                        self.actor,
                        target,
                        BusinessRole.CLIENTE,
                        reason,
                    )

        self.assertEqual(get_business_roles(target), ())
        self.assertFalse(self.semantic_audits().exists())
