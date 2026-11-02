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
    ClientProfileRequired,
    InactiveUserForWorkAccessRevocation,
    PermissionDeniedForWorkAccessRevocation,
    PersonalHasNoUser,
    WORK_ACCESS_REVOKED_KEEP_CLIENT_EVENT,
    WORK_ACCESS_REVOCATION_AUDIT_TABLE,
    WORK_ACCESS_REVOCATION_SOURCE,
    WorkAccessRevocationConflict,
    revoke_work_access_keep_client,
)
from usuarios.access_services import (
    InconsistentBusinessRoleState,
    ProtectedSuperuser,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class WorkAccessRevocationServiceTests(TestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('revoke-actor@test.com')
        self.actor.user_permissions.add(
            self.manage_personal,
            self.assign_roles,
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
            'apellido': 'Revocacion',
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
        superuser=False,
    ):
        user = self.create_user(
            f'revoke-{suffix}@test.com',
            is_active=user_active,
            is_staff=superuser,
            is_superuser=superuser,
        )
        user.groups.add(Group.objects.get(name=role))
        client = Cliente.objects.create(usuario=user, zona='Centro')
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
            'reason': 'Fin de relacion laboral conservando acceso cliente',
        }
        values.update(overrides)
        return revoke_work_access_keep_client(**values)

    def semantic_audits(self):
        return Auditoria.objects.filter(
            tabla=WORK_ACCESS_REVOCATION_AUDIT_TABLE
        )

    def assert_final_client_state(self, personal, user):
        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertEqual(personal.usuario, user)
        self.assertTrue(user.is_active)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_active_employee_is_revoked_to_client(self):
        personal, user, _ = self.create_linked_context(
            'employee',
            BusinessRole.EMPLEADO,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertEqual(result.previous_role, BusinessRole.EMPLEADO)
        self.assert_final_client_state(personal, user)

    def test_active_professional_is_revoked_to_client(self):
        personal, user, _ = self.create_linked_context(
            'professional',
            BusinessRole.PROFESIONAL,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertEqual(result.previous_role, BusinessRole.PROFESIONAL)
        self.assert_final_client_state(personal, user)

    def test_administrator_with_personal_is_revoked_to_client(self):
        personal, user, _ = self.create_linked_context(
            'administrator',
            BusinessRole.ADMINISTRADOR,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertEqual(result.previous_role, BusinessRole.ADMINISTRADOR)
        self.assert_final_client_state(personal, user)

    def test_inactive_personal_with_labor_role_completes_role_change(self):
        personal, user, _ = self.create_linked_context(
            'inactive-labor',
            BusinessRole.EMPLEADO,
            personal_active=False,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertFalse(result.previous_personal_active)
        self.assertIsNone(result.status_audit_id)
        self.assertIsNotNone(result.role_audit_id)
        self.assert_final_client_state(personal, user)

    def test_active_personal_with_client_role_only_deactivates(self):
        personal, user, _ = self.create_linked_context(
            'active-client',
            BusinessRole.CLIENTE,
        )

        result = self.revoke(personal)

        self.assertTrue(result.changed)
        self.assertIsNotNone(result.status_audit_id)
        self.assertIsNone(result.role_audit_id)
        self.assert_final_client_state(personal, user)

    def test_final_state_is_noop_without_any_audit(self):
        personal, user, client = self.create_linked_context(
            'noop',
            BusinessRole.CLIENTE,
            personal_active=False,
        )
        audit_count = Auditoria.objects.count()

        result = self.revoke(personal)

        self.assertFalse(result.changed)
        self.assertIsNone(result.audit_id)
        self.assertIsNone(result.status_audit_id)
        self.assertIsNone(result.role_audit_id)
        self.assertEqual(result.client_id, client.pk)
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assert_final_client_state(personal, user)

    def test_personal_without_user_is_rejected(self):
        personal = self.create_personal('without-user')

        with self.assertRaises(PersonalHasNoUser):
            self.revoke(personal)

        personal.refresh_from_db()
        self.assertTrue(personal.activo)

    def test_user_without_client_is_rejected_without_changes(self):
        user = self.create_user('revoke-without-client@test.com')
        user.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        personal = self.create_personal('without-client', usuario=user)

        with self.assertRaises(ClientProfileRequired):
            self.revoke(personal)

        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))
        self.assertFalse(Cliente.objects.filter(usuario=user).exists())

    def test_inactive_user_is_rejected_without_reactivation(self):
        personal, user, _ = self.create_linked_context(
            'inactive-user',
            BusinessRole.EMPLEADO,
            user_active=False,
        )

        with self.assertRaises(InactiveUserForWorkAccessRevocation):
            self.revoke(personal)

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertFalse(user.is_active)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))

    def test_multiple_business_roles_are_rejected_without_correction(self):
        personal, user, _ = self.create_linked_context(
            'multiple-roles',
            BusinessRole.EMPLEADO,
        )
        user.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))

        with self.assertRaises(InconsistentBusinessRoleState):
            self.revoke(personal)

        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertSetEqual(
            set(get_business_roles(user)),
            {BusinessRole.CLIENTE, BusinessRole.EMPLEADO},
        )

    def test_superuser_target_is_rejected(self):
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
        self.assertTrue(user.is_superuser)

    def test_client_link_account_and_personal_fields_are_preserved(self):
        personal, user, client = self.create_linked_context(
            'preservation',
            BusinessRole.PROFESIONAL,
        )
        original_password = user.password
        user.is_staff = True
        user.save(update_fields=['is_staff'])
        client.activo = False
        client.numero = '1122334455'
        client.save(update_fields=['activo', 'numero'])
        technical_group = Group.objects.create(name='REVOKE_TECHNICAL')
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
        group_ids_before = set(user.groups.values_list('pk', flat=True))
        group_ids_before.remove(
            Group.objects.get(name=BusinessRole.PROFESIONAL).pk
        )
        permission_ids_before = set(
            user.user_permissions.values_list('pk', flat=True)
        )

        result = self.revoke(personal)

        personal.refresh_from_db()
        user.refresh_from_db()
        client.refresh_from_db()
        remaining_non_business_groups = set(
            user.groups.exclude(name__in=BusinessRole.ALL).values_list(
                'pk', flat=True
            )
        )
        self.assertEqual(personal.usuario, user)
        self.assertEqual(result.client_id, client.pk)
        self.assertEqual(client.zona, 'Centro')
        self.assertFalse(client.activo)
        self.assertEqual(client.numero, '1122334455')
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.password, original_password)
        self.assertSetEqual(remaining_non_business_groups, group_ids_before)
        self.assertSetEqual(
            set(user.user_permissions.values_list('pk', flat=True)),
            permission_ids_before,
        )
        self.assertEqual(personal.rol, 'colorista')
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)

    def test_historical_and_operational_relations_are_preserved(self):
        personal, user, _ = self.create_linked_context(
            'relations',
            BusinessRole.EMPLEADO,
        )
        schedule = HorarioLaboral.objects.create(
            personal=personal,
            dia_semana=1,
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
        client_user = self.create_user('revoke-turn-client@test.com')
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
        self.assert_final_client_state(personal, user)

    def test_valid_change_creates_composed_audit_with_component_ids(self):
        personal, user, client = self.create_linked_context(
            'audit',
            BusinessRole.EMPLEADO,
        )

        result = self.revoke(personal)

        audit = self.semantic_audits().get()
        self.assertEqual(audit.pk, result.audit_id)
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, personal.pk)
        self.assertEqual(
            audit.valor_nuevo['event'],
            WORK_ACCESS_REVOKED_KEEP_CLIENT_EVENT,
        )
        self.assertEqual(
            audit.valor_nuevo['source'],
            WORK_ACCESS_REVOCATION_SOURCE,
        )
        self.assertEqual(audit.valor_nuevo['user_id'], user.pk)
        self.assertEqual(audit.valor_nuevo['client_id'], client.pk)
        self.assertEqual(
            audit.valor_nuevo['previous_role'],
            BusinessRole.EMPLEADO,
        )
        self.assertEqual(
            audit.valor_nuevo['current_role'],
            BusinessRole.CLIENTE,
        )
        self.assertTrue(audit.valor_nuevo['user_active'])
        self.assertEqual(
            audit.valor_nuevo['status_audit_id'],
            result.status_audit_id,
        )
        self.assertEqual(
            audit.valor_nuevo['role_audit_id'],
            result.role_audit_id,
        )

    def test_compound_audit_failure_rolls_back_status_and_role(self):
        personal, user, _ = self.create_linked_context(
            'audit-failure',
            BusinessRole.EMPLEADO,
        )
        real_create = Auditoria.objects.create

        def fail_compound_audit(*args, **kwargs):
            if kwargs.get('tabla') == WORK_ACCESS_REVOCATION_AUDIT_TABLE:
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
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))
        self.assertFalse(self.semantic_audits().exists())

    def test_actor_requires_both_permissions(self):
        personal, user, _ = self.create_linked_context(
            'permissions',
            BusinessRole.EMPLEADO,
        )
        permissions = (None, self.manage_personal, self.assign_roles)

        for index, permission in enumerate(permissions, start=1):
            with self.subTest(permission=permission):
                actor = self.create_user(f'revoke-denied-{index}@test.com')
                if permission is not None:
                    actor.user_permissions.add(permission)

                with self.assertRaises(
                    PermissionDeniedForWorkAccessRevocation
                ):
                    self.revoke(personal, actor=actor)

        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))

    def test_self_role_change_is_a_stable_conflict_and_rolls_back(self):
        self.actor.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        Cliente.objects.create(usuario=self.actor, zona='Centro')
        personal = self.create_personal('self-target', usuario=self.actor)

        with self.assertRaises(WorkAccessRevocationConflict):
            self.revoke(personal)

        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertEqual(
            get_business_roles(self.actor),
            (BusinessRole.EMPLEADO,),
        )
        self.assertFalse(self.semantic_audits().exists())
