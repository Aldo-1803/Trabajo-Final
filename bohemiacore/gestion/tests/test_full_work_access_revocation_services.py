from datetime import date, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.utils import timezone

from gestion.models import (
    Auditoria,
    BloqueoAgenda,
    HorarioLaboral,
    Personal,
    Turno,
)
from gestion.personal_access_services import (
    FULL_WORK_ACCESS_REVOCATION_AUDIT_TABLE,
    FULL_WORK_ACCESS_REVOCATION_SOURCE,
    PermissionDeniedForFullWorkAccessRevocation,
    PersonalHasNoUser,
    WORK_ACCESS_REVOKED_ACCOUNT_DISABLED_EVENT,
    revoke_work_access_and_disable_account,
)
from usuarios.access_services import (
    LastActiveAdministrator,
    ProtectedSuperuser,
    SelfDeactivationNotAllowed,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class FullWorkAccessRevocationServiceTests(TestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.actor = self.create_user('full-revoke-actor@test.com')
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
            'apellido': 'Baja Total',
            'rol': 'asistente',
            'activo': True,
            'realiza_diagnostico': False,
            'realiza_lavado': True,
            'realiza_color': False,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def create_linked_context(
        self,
        suffix,
        role,
        *,
        personal_active=True,
        user_active=True,
        with_client=True,
        superuser=False,
    ):
        user = self.create_user(
            f'full-revoke-{suffix}@test.com',
            is_active=user_active,
            is_staff=superuser,
            is_superuser=superuser,
        )
        user.groups.add(Group.objects.get(name=role))
        client = None
        if with_client:
            client = Cliente.objects.create(
                usuario=user,
                zona='Centro',
                activo=False,
            )
        personal = self.create_personal(
            suffix,
            usuario=user,
            activo=personal_active,
        )
        return personal, user, client

    def revoke(self, personal, **overrides):
        values = {
            'actor': self.actor,
            'personal': personal,
            'reason': 'Fin de relacion laboral y acceso digital',
        }
        values.update(overrides)
        return revoke_work_access_and_disable_account(**values)

    def audits(self):
        return Auditoria.objects.filter(
            tabla=FULL_WORK_ACCESS_REVOCATION_AUDIT_TABLE
        )

    def assert_final_state(self, personal, user, role):
        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertFalse(user.is_active)
        self.assertEqual(personal.usuario, user)
        self.assertEqual(get_business_roles(user), (role,))

    def test_employee_and_professional_are_fully_deactivated(self):
        for index, role in enumerate(
            (BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL),
            start=1,
        ):
            with self.subTest(role=role):
                personal, user, _ = self.create_linked_context(
                    f'labor-{index}',
                    role,
                )

                result = self.revoke(personal)

                self.assertTrue(result.changed)
                self.assertEqual(result.current_role, role)
                self.assert_final_state(personal, user, role)

    def test_administrator_can_be_deactivated_with_active_backup(self):
        backup = self.create_user('full-revoke-admin-backup@test.com')
        backup.groups.add(Group.objects.get(name=BusinessRole.ADMINISTRADOR))
        personal, user, _ = self.create_linked_context(
            'administrator',
            BusinessRole.ADMINISTRADOR,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assert_final_state(personal, user, BusinessRole.ADMINISTRADOR)
        backup.refresh_from_db()
        self.assertTrue(backup.is_active)

    def test_last_active_administrator_is_rejected_without_changes(self):
        personal, user, _ = self.create_linked_context(
            'last-administrator',
            BusinessRole.ADMINISTRADOR,
        )

        with self.assertRaises(LastActiveAdministrator):
            self.revoke(personal)

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(user.is_active)

    def test_client_role_is_preserved_while_both_states_are_deactivated(self):
        personal, user, client = self.create_linked_context(
            'client-role',
            BusinessRole.CLIENTE,
        )

        result = self.revoke(personal)

        self.assertEqual(result.current_role, BusinessRole.CLIENTE)
        self.assert_final_state(personal, user, BusinessRole.CLIENTE)
        client.refresh_from_db()
        self.assertFalse(client.activo)
        self.assertEqual(client.zona, 'Centro')

    def test_inactive_personal_only_deactivates_account(self):
        personal, user, _ = self.create_linked_context(
            'personal-inactive',
            BusinessRole.EMPLEADO,
            personal_active=False,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertFalse(result.previous_personal_active)
        self.assertTrue(result.previous_user_active)
        self.assertIsNone(result.status_audit_id)
        self.assertIsNotNone(result.account_audit_id)
        self.assert_final_state(personal, user, BusinessRole.EMPLEADO)

    def test_inactive_account_only_deactivates_personal(self):
        personal, user, _ = self.create_linked_context(
            'account-inactive',
            BusinessRole.PROFESIONAL,
            user_active=False,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertTrue(result.previous_personal_active)
        self.assertFalse(result.previous_user_active)
        self.assertIsNotNone(result.status_audit_id)
        self.assertIsNone(result.account_audit_id)
        self.assert_final_state(personal, user, BusinessRole.PROFESIONAL)

    def test_both_inactive_is_noop_without_audit(self):
        personal, user, _ = self.create_linked_context(
            'noop',
            BusinessRole.EMPLEADO,
            personal_active=False,
            user_active=False,
        )
        audit_count = Auditoria.objects.count()

        result = self.revoke(personal)

        self.assertFalse(result.changed)
        self.assertIsNone(result.audit_id)
        self.assertIsNone(result.status_audit_id)
        self.assertIsNone(result.account_audit_id)
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assert_final_state(personal, user, BusinessRole.EMPLEADO)

    def test_multiple_roles_are_preserved_and_report_warning(self):
        personal, user, _ = self.create_linked_context(
            'multiple-roles',
            BusinessRole.EMPLEADO,
        )
        user.groups.add(Group.objects.get(name=BusinessRole.PROFESIONAL))

        result = self.revoke(personal)

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertIsNone(result.current_role)
        self.assertIn('INCONSISTENT_BUSINESS_ROLES', result.warnings)
        self.assertFalse(personal.activo)
        self.assertFalse(user.is_active)
        self.assertSetEqual(
            set(get_business_roles(user)),
            {BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL},
        )

    def test_credentials_flags_groups_permissions_and_profiles_are_preserved(self):
        personal, user, client = self.create_linked_context(
            'preservation',
            BusinessRole.PROFESIONAL,
        )
        original_password = user.password
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        technical_group = Group.objects.create(name='FULL_REVOKE_TECHNICAL')
        user.groups.add(technical_group)
        individual_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        user.user_permissions.add(individual_permission)
        personal.rol = 'colorista'
        personal.realiza_diagnostico = True
        personal.realiza_lavado = False
        personal.realiza_color = True
        personal.save()
        group_ids = set(user.groups.values_list('pk', flat=True))
        permission_ids = set(
            user.user_permissions.values_list('pk', flat=True)
        )

        self.revoke(personal)

        personal.refresh_from_db()
        user.refresh_from_db()
        client.refresh_from_db()
        self.assertEqual(personal.usuario, user)
        self.assertEqual(personal.rol, 'colorista')
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.password, original_password)
        self.assertSetEqual(
            set(user.groups.values_list('pk', flat=True)),
            group_ids,
        )
        self.assertSetEqual(
            set(user.user_permissions.values_list('pk', flat=True)),
            permission_ids,
        )
        self.assertFalse(client.activo)
        self.assertEqual(client.zona, 'Centro')

    def test_relations_and_history_are_preserved(self):
        personal, user, _ = self.create_linked_context(
            'relations',
            BusinessRole.EMPLEADO,
        )
        schedule = HorarioLaboral.objects.create(
            personal=personal,
            dia_semana=2,
            hora_inicio=time(9, 0),
            hora_fin=time(17, 0),
        )
        now = timezone.now()
        block = BloqueoAgenda.objects.create(
            personal=personal,
            fecha_inicio=now + timedelta(days=1),
            fecha_fin=now + timedelta(days=2),
            motivo='Licencia registrada',
        )
        client_user = self.create_user('full-revoke-turn-client@test.com')
        appointment_client = Cliente.objects.create(usuario=client_user)
        appointment = Turno.objects.create(
            cliente=appointment_client,
            profesional=personal,
            fecha=date.today() + timedelta(days=3),
            hora_inicio=time(11, 0),
        )
        history_count = personal.history.count()

        self.revoke(personal)

        self.assertTrue(HorarioLaboral.objects.filter(pk=schedule.pk).exists())
        self.assertTrue(BloqueoAgenda.objects.filter(pk=block.pk).exists())
        self.assertTrue(Turno.objects.filter(pk=appointment.pk).exists())
        appointment.refresh_from_db()
        self.assertEqual(appointment.profesional, personal)
        self.assertEqual(personal.history.count(), history_count)
        self.assert_final_state(personal, user, BusinessRole.EMPLEADO)

    def test_client_is_not_created_as_side_effect(self):
        personal, user, client = self.create_linked_context(
            'without-client',
            BusinessRole.EMPLEADO,
            with_client=False,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertIsNone(client)
        self.assertFalse(Cliente.objects.filter(usuario=user).exists())
        self.assert_final_state(personal, user, BusinessRole.EMPLEADO)

    def test_personal_without_user_is_rejected(self):
        personal = self.create_personal('without-user')

        with self.assertRaises(PersonalHasNoUser):
            self.revoke(personal)

        personal.refresh_from_db()
        self.assertTrue(personal.activo)

    def test_superuser_and_self_deactivation_are_rejected(self):
        personal, user, _ = self.create_linked_context(
            'superuser',
            BusinessRole.ADMINISTRADOR,
            superuser=True,
        )
        with self.assertRaises(ProtectedSuperuser):
            self.revoke(personal)
        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(user.is_active)

        self.actor.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        actor_personal = self.create_personal(
            'self-target',
            usuario=self.actor,
        )
        with self.assertRaises(SelfDeactivationNotAllowed):
            self.revoke(actor_personal)
        actor_personal.refresh_from_db()
        self.actor.refresh_from_db()
        self.assertTrue(actor_personal.activo)
        self.assertTrue(self.actor.is_active)

    def test_actor_requires_both_permissions_without_staff_shortcut(self):
        personal, user, _ = self.create_linked_context(
            'permissions',
            BusinessRole.EMPLEADO,
        )
        permission_sets = (
            (),
            (self.manage_personal,),
            (self.manage_users,),
        )

        for index, permissions in enumerate(permission_sets, start=1):
            with self.subTest(permissions=permissions):
                actor = self.create_user(
                    f'full-revoke-denied-{index}@test.com',
                    is_staff=True,
                )
                actor.user_permissions.add(*permissions)
                with self.assertRaises(
                    PermissionDeniedForFullWorkAccessRevocation
                ):
                    self.revoke(personal, actor=actor)

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(user.is_active)

    def test_compound_audit_contains_component_ids(self):
        personal, user, _ = self.create_linked_context(
            'audit',
            BusinessRole.EMPLEADO,
        )

        result = self.revoke(personal)

        audit = self.audits().get()
        self.assertEqual(audit.pk, result.audit_id)
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, personal.pk)
        self.assertEqual(
            audit.valor_nuevo['event'],
            WORK_ACCESS_REVOKED_ACCOUNT_DISABLED_EVENT,
        )
        self.assertEqual(
            audit.valor_nuevo['source'],
            FULL_WORK_ACCESS_REVOCATION_SOURCE,
        )
        self.assertEqual(audit.valor_nuevo['user_id'], user.pk)
        self.assertTrue(audit.valor_nuevo['previous_personal_active'])
        self.assertFalse(audit.valor_nuevo['current_personal_active'])
        self.assertTrue(audit.valor_nuevo['previous_user_active'])
        self.assertFalse(audit.valor_nuevo['current_user_active'])
        self.assertEqual(
            audit.valor_nuevo['current_business_role'],
            BusinessRole.EMPLEADO,
        )
        self.assertEqual(
            audit.valor_nuevo['status_audit_id'],
            result.status_audit_id,
        )
        self.assertEqual(
            audit.valor_nuevo['account_audit_id'],
            result.account_audit_id,
        )

    def test_compound_audit_failure_rolls_back_both_states(self):
        personal, user, _ = self.create_linked_context(
            'audit-failure',
            BusinessRole.EMPLEADO,
        )
        real_create = Auditoria.objects.create

        def fail_compound_audit(*args, **kwargs):
            if kwargs.get('tabla') == FULL_WORK_ACCESS_REVOCATION_AUDIT_TABLE:
                raise RuntimeError('audit unavailable')
            return real_create(*args, **kwargs)

        with patch(
            'gestion.personal_access_services.Auditoria.objects.create',
            side_effect=fail_compound_audit,
        ):
            with self.assertRaises(RuntimeError):
                self.revoke(personal)

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertTrue(user.is_active)
        self.assertFalse(self.audits().exists())
