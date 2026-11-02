from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from gestion.models import Auditoria, Personal
from usuarios.access_services import (
    ACCOUNT_DEACTIVATED_EVENT,
    ACCOUNT_DEACTIVATION_AUDIT_TABLE,
    ACCOUNT_DEACTIVATION_SOURCE,
    InvalidAccountDeactivationReason,
    LastActiveAdministrator,
    PermissionDeniedForAccountDeactivation,
    ProtectedSuperuser,
    SelfDeactivationNotAllowed,
    deactivate_account,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class AccountDeactivationServiceTests(TestCase):
    def setUp(self):
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.actor = self.create_user('account-actor@test.com')
        self.actor.user_permissions.add(self.manage_users)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def audits(self):
        return Auditoria.objects.filter(
            tabla=ACCOUNT_DEACTIVATION_AUDIT_TABLE
        )

    def test_active_account_is_deactivated_without_changing_identity(self):
        target = self.create_user(
            'account-target@test.com',
            is_staff=True,
        )
        original_password = target.password
        target.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        technical_group = Group.objects.create(name='ACCOUNT_TECHNICAL')
        target.groups.add(technical_group)
        individual_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        target.user_permissions.add(individual_permission)
        cliente = Cliente.objects.create(
            usuario=target,
            zona='Centro',
            activo=False,
        )
        personal = Personal.objects.create(
            usuario=target,
            nombre='Cuenta',
            apellido='Objetivo',
            rol='colorista',
            activo=True,
        )
        group_ids = set(target.groups.values_list('pk', flat=True))
        permission_ids = set(
            target.user_permissions.values_list('pk', flat=True)
        )

        result = deactivate_account(
            self.actor,
            target,
            'Desactivacion digital aprobada',
        )

        target.refresh_from_db()
        cliente.refresh_from_db()
        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertTrue(result.previous_active)
        self.assertFalse(result.current_active)
        self.assertFalse(target.is_active)
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
        self.assertFalse(cliente.activo)
        self.assertEqual(cliente.zona, 'Centro')
        self.assertTrue(personal.activo)
        self.assertEqual(personal.rol, 'colorista')

    def test_inactive_account_is_noop_without_audit(self):
        target = self.create_user(
            'account-noop@test.com',
            is_active=False,
        )
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        audit_count = Auditoria.objects.count()

        result = deactivate_account(
            self.actor,
            target,
            'Confirmacion de cuenta inactiva',
        )

        self.assertFalse(result.changed)
        self.assertIsNone(result.audit_id)
        self.assertEqual(Auditoria.objects.count(), audit_count)

    def test_multiple_roles_are_preserved_with_warning(self):
        target = self.create_user('account-multiple@test.com')
        target.groups.add(
            Group.objects.get(name=BusinessRole.EMPLEADO),
            Group.objects.get(name=BusinessRole.PROFESIONAL),
        )

        result = deactivate_account(
            self.actor,
            target,
            'Desactivar cuenta con roles inconsistentes',
        )

        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertIsNone(result.current_role)
        self.assertIn('INCONSISTENT_BUSINESS_ROLES', result.warnings)
        self.assertSetEqual(
            set(get_business_roles(target)),
            {BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL},
        )

    def test_last_active_business_administrator_is_protected(self):
        target = self.create_user('account-last-admin@test.com')
        target.groups.add(Group.objects.get(name=BusinessRole.ADMINISTRADOR))

        with self.assertRaises(LastActiveAdministrator):
            deactivate_account(
                self.actor,
                target,
                'Intento sobre ultimo administrador',
            )

        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_administrator_can_be_deactivated_with_active_backup(self):
        target = self.create_user('account-admin-target@test.com')
        backup = self.create_user('account-admin-backup@test.com')
        administrator_group = Group.objects.get(
            name=BusinessRole.ADMINISTRADOR
        )
        target.groups.add(administrator_group)
        backup.groups.add(administrator_group)

        result = deactivate_account(
            self.actor,
            target,
            'Baja con administrador alternativo',
        )

        target.refresh_from_db()
        backup.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertFalse(target.is_active)
        self.assertTrue(backup.is_active)
        self.assertEqual(
            get_business_roles(target),
            (BusinessRole.ADMINISTRADOR,),
        )

    def test_self_deactivation_and_superuser_are_rejected(self):
        with self.assertRaises(SelfDeactivationNotAllowed):
            deactivate_account(
                self.actor,
                self.actor,
                'Auto baja no permitida',
            )

        superuser = self.create_user(
            'account-superuser@test.com',
            is_staff=True,
            is_superuser=True,
        )
        with self.assertRaises(ProtectedSuperuser):
            deactivate_account(
                self.actor,
                superuser,
                'Baja de superusuario no permitida',
            )

        self.actor.refresh_from_db()
        superuser.refresh_from_db()
        self.assertTrue(self.actor.is_active)
        self.assertTrue(superuser.is_active)

    def test_manage_users_permission_is_required_without_staff_shortcut(self):
        actor = self.create_user(
            'account-denied@test.com',
            is_staff=True,
        )
        target = self.create_user('account-denied-target@test.com')

        with self.assertRaises(PermissionDeniedForAccountDeactivation):
            deactivate_account(
                actor,
                target,
                'Intento sin permiso de negocio',
            )

        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_audit_contains_semantic_data_and_failure_rolls_back(self):
        target = self.create_user('account-audit@test.com')
        target.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))

        result = deactivate_account(
            self.actor,
            target,
            'Baja digital auditada',
        )

        audit = self.audits().get()
        self.assertEqual(audit.pk, result.audit_id)
        self.assertEqual(audit.valor_nuevo['event'], ACCOUNT_DEACTIVATED_EVENT)
        self.assertEqual(audit.valor_nuevo['source'], ACCOUNT_DEACTIVATION_SOURCE)
        self.assertTrue(audit.valor_nuevo['previous_active'])
        self.assertFalse(audit.valor_nuevo['current_active'])
        self.assertEqual(
            audit.valor_nuevo['current_business_role'],
            BusinessRole.EMPLEADO,
        )

        rollback_target = self.create_user('account-rollback@test.com')
        with patch(
            'usuarios.access_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                deactivate_account(
                    self.actor,
                    rollback_target,
                    'Baja que debe revertirse',
                )

        rollback_target.refresh_from_db()
        self.assertTrue(rollback_target.is_active)

    def test_reason_is_required_even_for_noop(self):
        target = self.create_user(
            'account-invalid-reason@test.com',
            is_active=False,
        )

        for reason in (None, '', ' ', 'x', 'x' * 501):
            with self.subTest(reason=reason):
                with self.assertRaises(InvalidAccountDeactivationReason):
                    deactivate_account(self.actor, target, reason)
