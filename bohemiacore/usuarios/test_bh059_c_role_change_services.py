from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from gestion.models import Auditoria, Personal
from usuarios.access_services import (
    LastActiveAdministratorRoleChange,
    PermissionDeniedForRoleAssignment,
    ResidualAdministrativeCapabilities,
    ROLE_AUDIT_TABLE,
    change_administrative_business_role,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    build_business_role_audit_metadata,
    get_business_role,
)


class AdministrativeBusinessRoleChangeServiceTests(TestCase):
    def setUp(self):
        self.actor = self.create_user('role-manager@test.com')
        self.actor.user_permissions.add(
            self.permission(BusinessPermission.MANAGE_USERS),
            self.permission(BusinessPermission.ASSIGN_ROLES),
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='RoleChange!2026',
            **extra_fields,
        )

    @staticmethod
    def permission(code):
        app_label, codename = code.split('.', 1)
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    @staticmethod
    def create_personal(user, *, active=True):
        return Personal.objects.create(
            usuario=user,
            nombre='Perfil',
            apellido='Laboral',
            rol='asistente',
            activo=active,
        )

    def change(self, target, role, reason='Cambio administrativo aprobado'):
        return change_administrative_business_role(
            actor=self.actor,
            target_user=target,
            target_role=role,
            reason=reason,
        )

    def test_general_change_requires_both_effective_permissions(self):
        target = self.create_user('authority-target@test.com')
        Cliente.objects.create(usuario=target)
        actors = []
        for index, permission in enumerate((
            BusinessPermission.MANAGE_USERS,
            BusinessPermission.ASSIGN_ROLES,
        )):
            actor = self.create_user(f'partial-{index}@test.com')
            actor.user_permissions.add(self.permission(permission))
            actors.append(actor)
        actors.append(self.create_user('staff-only@test.com', is_staff=True))
        inactive_actor = self.create_user(
            'inactive-manager@test.com',
            is_active=False,
        )
        inactive_actor.user_permissions.add(
            self.permission(BusinessPermission.MANAGE_USERS),
            self.permission(BusinessPermission.ASSIGN_ROLES),
        )
        actors.append(inactive_actor)

        for actor in actors:
            with self.subTest(actor=actor.email):
                with self.assertRaises(PermissionDeniedForRoleAssignment):
                    change_administrative_business_role(
                        actor,
                        target,
                        BusinessRole.CLIENTE,
                        'Intento sin autoridad conjunta',
                    )

        self.assertIsNone(get_business_role(target))

    def test_promotion_preserves_profiles_ownership_and_account_flags(self):
        target = self.create_user(
            'promotion-target@test.com',
            is_staff=False,
            is_active=True,
        )
        cliente = Cliente.objects.create(usuario=target, zona='Centro')
        personal = self.create_personal(target)
        self.assign_role(target, BusinessRole.EMPLEADO)

        result = self.change(target, BusinessRole.ADMINISTRADOR)

        target.refresh_from_db()
        cliente.refresh_from_db()
        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(result.previous_role, BusinessRole.EMPLEADO)
        self.assertEqual(get_business_role(target), BusinessRole.ADMINISTRADOR)
        self.assertEqual(cliente.usuario_id, target.pk)
        self.assertEqual(personal.usuario_id, target.pk)
        self.assertEqual(cliente.zona, 'Centro')
        self.assertTrue(personal.activo)
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)
        audit = Auditoria.objects.get(pk=result.audit_id)
        expected_metadata = build_business_role_audit_metadata(
            previous_role=BusinessRole.EMPLEADO,
            new_role=BusinessRole.ADMINISTRADOR,
        )
        for key, value in expected_metadata.items():
            self.assertEqual(audit.valor_nuevo[key], value)

    def test_last_active_administrator_ignores_technical_backups(self):
        target = self.create_user('last-admin@test.com')
        Cliente.objects.create(usuario=target)
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.create_user('staff-backup@test.com', is_staff=True)
        inactive_admin = self.create_user(
            'inactive-admin@test.com',
            is_active=False,
        )
        self.assign_role(inactive_admin, BusinessRole.ADMINISTRADOR)
        superuser = self.create_user(
            'superuser-backup@test.com',
            is_staff=True,
            is_superuser=True,
        )
        self.assign_role(superuser, BusinessRole.ADMINISTRADOR)
        inconsistent_admin = self.create_user(
            'inconsistent-admin-backup@test.com'
        )
        inconsistent_admin.groups.add(
            Group.objects.get(name=BusinessRole.ADMINISTRADOR),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )

        with self.assertRaises(LastActiveAdministratorRoleChange):
            self.change(target, BusinessRole.CLIENTE)

        self.assertEqual(get_business_role(target), BusinessRole.ADMINISTRADOR)
        self.assertFalse(Auditoria.objects.filter(
            tabla=ROLE_AUDIT_TABLE,
            registro_id=target.pk,
        ).exists())

    def test_administrator_degradation_rejects_individual_or_group_authority(self):
        for source in ('individual', 'group'):
            with self.subTest(source=source):
                target = self.create_user(f'residual-{source}@test.com')
                backup = self.create_user(f'backup-{source}@test.com')
                Cliente.objects.create(usuario=target)
                self.assign_role(target, BusinessRole.ADMINISTRADOR)
                self.assign_role(backup, BusinessRole.ADMINISTRADOR)
                permission = self.permission(BusinessPermission.MANAGE_USERS)
                if source == 'individual':
                    target.user_permissions.add(permission)
                else:
                    group = Group.objects.create(
                        name=f'TECHNICAL_RESIDUAL_{source.upper()}'
                    )
                    group.permissions.add(permission)
                    target.groups.add(group)

                with self.assertRaises(
                    ResidualAdministrativeCapabilities
                ) as raised:
                    self.change(target, BusinessRole.CLIENTE)

                self.assertEqual(
                    raised.exception.capabilities[0]['code'],
                    BusinessPermission.MANAGE_USERS,
                )
                self.assertEqual(get_business_role(target), BusinessRole.ADMINISTRADOR)
                self.assertFalse(Auditoria.objects.filter(
                    tabla=ROLE_AUDIT_TABLE,
                    registro_id=target.pk,
                ).exists())

    def test_non_escalating_technical_permissions_are_preserved(self):
        target = self.create_user('legitimate-technical@test.com')
        backup = self.create_user('legitimate-backup@test.com')
        Cliente.objects.create(usuario=target)
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.assign_role(backup, BusinessRole.ADMINISTRADOR)
        group = Group.objects.create(name='TECHNICAL_STOCK_READERS')
        group.permissions.add(self.permission(BusinessPermission.VIEW_STOCK))
        target.groups.add(group)

        result = self.change(target, BusinessRole.CLIENTE)

        target.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(get_business_role(target), BusinessRole.CLIENTE)
        self.assertTrue(target.groups.filter(pk=group.pk).exists())
        self.assertTrue(target.has_perm(BusinessPermission.VIEW_STOCK))
        audit = Auditoria.objects.get(pk=result.audit_id)
        expected_metadata = build_business_role_audit_metadata(
            previous_role=BusinessRole.ADMINISTRADOR,
            new_role=BusinessRole.CLIENTE,
        )
        for key, value in expected_metadata.items():
            self.assertEqual(audit.valor_nuevo[key], value)

    def test_noop_does_not_duplicate_audit(self):
        target = self.create_user('role-noop@test.com')
        Cliente.objects.create(usuario=target)
        self.assign_role(target, BusinessRole.CLIENTE)
        audit_count = Auditoria.objects.count()

        first = self.change(target, BusinessRole.CLIENTE)
        second = self.change(target, BusinessRole.CLIENTE)

        self.assertFalse(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(Auditoria.objects.count(), audit_count)

    def test_audit_failure_rolls_back_transition(self):
        target = self.create_user('role-audit-rollback@test.com')
        Cliente.objects.create(usuario=target)
        self.create_personal(target)
        self.assign_role(target, BusinessRole.EMPLEADO)

        with patch(
            'usuarios.access_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                self.change(target, BusinessRole.CLIENTE)

        self.assertEqual(get_business_role(target), BusinessRole.EMPLEADO)

    def test_permission_cache_on_supplied_target_is_invalidated(self):
        target = self.create_user('role-cache@test.com')
        backup = self.create_user('role-cache-backup@test.com')
        Cliente.objects.create(usuario=target)
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.assign_role(backup, BusinessRole.ADMINISTRADOR)
        self.assertTrue(target.has_perm(BusinessPermission.MANAGE_USERS))
        self.assertIn('_perm_cache', target.__dict__)

        self.change(target, BusinessRole.CLIENTE)

        self.assertNotIn('_perm_cache', target.__dict__)
        self.assertFalse(target.has_perm(BusinessPermission.MANAGE_USERS))
