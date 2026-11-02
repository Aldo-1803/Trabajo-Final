from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from gestion.models import Auditoria, Personal
from usuarios.access_services import (
    ACCOUNT_REACTIVATED_EVENT,
    ACCOUNT_REACTIVATION_AUDIT_TABLE,
    ACCOUNT_REACTIVATION_SOURCE,
    InactivePersonal,
    InconsistentBusinessRoleState,
    InvalidAccountReactivationReason,
    MissingClientProfile,
    MissingPersonalProfile,
    PermissionDeniedForAccountReactivation,
    ProtectedSuperuser,
    UserHasNoBusinessRole,
    reactivate_account,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class AccountReactivationServiceTests(TestCase):
    def setUp(self):
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.actor = self.create_user('reactivate-actor@test.com')
        self.actor.user_permissions.add(self.manage_users)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def create_personal(self, user, *, activo=True, rol='asistente'):
        return Personal.objects.create(
            usuario=user,
            nombre='Cuenta',
            apellido='Reactivada',
            rol=rol,
            activo=activo,
            realiza_diagnostico=True,
            realiza_lavado=False,
            realiza_color=True,
        )

    def assign_role(self, user, role):
        user.groups.add(Group.objects.get(name=role))

    def reactivate(self, target, **overrides):
        values = {
            'actor': self.actor,
            'target_user': target,
            'reason': 'Reincorporacion digital aprobada',
        }
        values.update(overrides)
        return reactivate_account(**values)

    def audits(self):
        return Auditoria.objects.filter(
            tabla=ACCOUNT_REACTIVATION_AUDIT_TABLE
        )

    def test_inactive_client_with_profile_is_reactivated(self):
        target = self.create_user('reactivate-client@test.com', is_active=False)
        self.assign_role(target, BusinessRole.CLIENTE)
        client = Cliente.objects.create(
            usuario=target,
            zona='Centro',
            activo=False,
        )

        result = self.reactivate(target)

        target.refresh_from_db()
        client.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertFalse(result.previous_active)
        self.assertTrue(result.current_active)
        self.assertEqual(result.current_role, BusinessRole.CLIENTE)
        self.assertTrue(target.is_active)
        self.assertFalse(client.activo)
        self.assertEqual(client.zona, 'Centro')
        self.assertIn('CLIENT_PROFILE_INACTIVE', result.warnings)
        self.assertIn(
            'PREEXISTING_TOKENS_MAY_REGAIN_VALIDITY',
            result.warnings,
        )

    def test_client_without_profile_is_rejected_without_creation(self):
        target = self.create_user(
            'reactivate-client-missing@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.CLIENTE)

        with self.assertRaises(MissingClientProfile):
            self.reactivate(target)

        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertFalse(Cliente.objects.filter(usuario=target).exists())

    def test_employee_with_active_personal_is_reactivated(self):
        target = self.create_user(
            'reactivate-employee@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.EMPLEADO)
        personal = self.create_personal(target, activo=True)

        result = self.reactivate(target)

        target.refresh_from_db()
        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertTrue(target.is_active)
        self.assertTrue(personal.activo)
        self.assertEqual(result.current_role, BusinessRole.EMPLEADO)

    def test_employee_with_inactive_personal_is_rejected(self):
        target = self.create_user(
            'reactivate-employee-inactive@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.EMPLEADO)
        personal = self.create_personal(target, activo=False)

        with self.assertRaises(InactivePersonal):
            self.reactivate(target)

        target.refresh_from_db()
        personal.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertFalse(personal.activo)

    def test_professional_with_active_personal_is_reactivated(self):
        target = self.create_user(
            'reactivate-professional@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.PROFESIONAL)
        personal = self.create_personal(target, activo=True)

        result = self.reactivate(target)

        target.refresh_from_db()
        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertTrue(target.is_active)
        self.assertTrue(personal.activo)
        self.assertEqual(result.current_role, BusinessRole.PROFESIONAL)

    def test_professional_without_personal_is_rejected(self):
        target = self.create_user(
            'reactivate-professional-missing@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.PROFESIONAL)

        with self.assertRaises(MissingPersonalProfile):
            self.reactivate(target)

        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_administrator_without_personal_is_reactivated(self):
        target = self.create_user('reactivate-admin@test.com', is_active=False)
        self.assign_role(target, BusinessRole.ADMINISTRADOR)

        result = self.reactivate(target)

        target.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertTrue(target.is_active)
        self.assertEqual(result.current_role, BusinessRole.ADMINISTRADOR)
        self.assertFalse(Personal.objects.filter(usuario=target).exists())

    def test_roleless_and_multiple_role_users_are_rejected(self):
        roleless = self.create_user(
            'reactivate-roleless@test.com',
            is_active=False,
        )
        with self.assertRaises(UserHasNoBusinessRole):
            self.reactivate(roleless)

        multiple = self.create_user(
            'reactivate-multiple@test.com',
            is_active=False,
        )
        multiple.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )
        with self.assertRaises(InconsistentBusinessRoleState):
            self.reactivate(multiple)

        roleless.refresh_from_db()
        multiple.refresh_from_db()
        self.assertFalse(roleless.is_active)
        self.assertFalse(multiple.is_active)

    def test_superuser_and_administrative_self_service_are_rejected(self):
        superuser = self.create_user(
            'reactivate-superuser@test.com',
            is_active=False,
            is_staff=True,
            is_superuser=True,
        )
        self.assign_role(superuser, BusinessRole.ADMINISTRADOR)
        with self.assertRaises(ProtectedSuperuser):
            self.reactivate(superuser)

        self.assign_role(self.actor, BusinessRole.ADMINISTRADOR)
        with self.assertRaises(PermissionDeniedForAccountReactivation):
            self.reactivate(self.actor)

        superuser.refresh_from_db()
        self.actor.refresh_from_db()
        self.assertFalse(superuser.is_active)
        self.assertTrue(self.actor.is_active)

    def test_flags_credentials_groups_permissions_and_profiles_are_preserved(self):
        target = self.create_user(
            'reactivate-preservation@test.com',
            is_active=False,
            is_staff=True,
        )
        original_password = target.password
        self.assign_role(target, BusinessRole.EMPLEADO)
        technical_group = Group.objects.create(name='REACTIVATE_TECHNICAL')
        target.groups.add(technical_group)
        individual_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        target.user_permissions.add(individual_permission)
        client = Cliente.objects.create(
            usuario=target,
            zona='Norte',
            activo=False,
        )
        personal = self.create_personal(target, activo=True, rol='colorista')
        group_ids = set(target.groups.values_list('pk', flat=True))
        permission_ids = set(
            target.user_permissions.values_list('pk', flat=True)
        )

        self.reactivate(target)

        target.refresh_from_db()
        client.refresh_from_db()
        personal.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertTrue(target.is_staff)
        self.assertFalse(target.is_superuser)
        self.assertEqual(target.password, original_password)
        self.assertSetEqual(
            set(target.groups.values_list('pk', flat=True)),
            group_ids,
        )
        self.assertSetEqual(
            set(target.user_permissions.values_list('pk', flat=True)),
            permission_ids,
        )
        self.assertFalse(client.activo)
        self.assertEqual(client.zona, 'Norte')
        self.assertTrue(personal.activo)
        self.assertEqual(personal.rol, 'colorista')
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)

    def test_coherent_active_account_is_noop_without_audit(self):
        target = self.create_user('reactivate-noop@test.com', is_active=True)
        self.assign_role(target, BusinessRole.CLIENTE)
        Cliente.objects.create(usuario=target)
        audit_count = Auditoria.objects.count()

        result = self.reactivate(target)

        self.assertFalse(result.changed)
        self.assertTrue(result.previous_active)
        self.assertTrue(result.current_active)
        self.assertIsNone(result.audit_id)
        self.assertEqual(Auditoria.objects.count(), audit_count)

    def test_active_but_incoherent_account_is_rejected(self):
        target = self.create_user(
            'reactivate-active-incoherent@test.com',
            is_active=True,
        )
        self.assign_role(target, BusinessRole.EMPLEADO)
        personal = self.create_personal(target, activo=False)

        with self.assertRaises(InactivePersonal):
            self.reactivate(target)

        target.refresh_from_db()
        personal.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertFalse(personal.activo)
        self.assertFalse(self.audits().exists())

    def test_manage_users_permission_is_required_without_staff_shortcut(self):
        actor = self.create_user(
            'reactivate-denied@test.com',
            is_staff=True,
        )
        target = self.create_user(
            'reactivate-denied-target@test.com',
            is_active=False,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)

        with self.assertRaises(PermissionDeniedForAccountReactivation):
            self.reactivate(target, actor=actor)

        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_audit_is_semantic_and_failure_rolls_back(self):
        target = self.create_user('reactivate-audit@test.com', is_active=False)
        self.assign_role(target, BusinessRole.ADMINISTRADOR)

        result = self.reactivate(target)

        audit = self.audits().get()
        self.assertEqual(audit.pk, result.audit_id)
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.valor_nuevo['event'], ACCOUNT_REACTIVATED_EVENT)
        self.assertEqual(audit.valor_nuevo['source'], ACCOUNT_REACTIVATION_SOURCE)
        self.assertFalse(audit.valor_nuevo['previous_active'])
        self.assertTrue(audit.valor_nuevo['current_active'])
        self.assertEqual(
            audit.valor_nuevo['current_business_role'],
            BusinessRole.ADMINISTRADOR,
        )

        rollback_target = self.create_user(
            'reactivate-rollback@test.com',
            is_active=False,
        )
        self.assign_role(rollback_target, BusinessRole.ADMINISTRADOR)
        with patch(
            'usuarios.access_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                self.reactivate(rollback_target)

        rollback_target.refresh_from_db()
        self.assertFalse(rollback_target.is_active)

    def test_reason_is_required_even_for_noop(self):
        target = self.create_user(
            'reactivate-invalid-reason@test.com',
            is_active=True,
        )
        self.assign_role(target, BusinessRole.ADMINISTRADOR)

        for reason in (None, '', ' ', 'x', 'x' * 501):
            with self.subTest(reason=reason):
                with self.assertRaises(InvalidAccountReactivationReason):
                    reactivate_account(self.actor, target, reason)
