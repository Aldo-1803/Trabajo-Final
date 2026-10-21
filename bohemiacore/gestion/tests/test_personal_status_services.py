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
    InvalidPersonalStatusReason,
    PERSONAL_DEACTIVATED_EVENT,
    PERSONAL_DEACTIVATED_SOURCE,
    PERSONAL_REACTIVATED_EVENT,
    PERSONAL_REACTIVATED_SOURCE,
    PERSONAL_STATUS_AUDIT_TABLE,
    PermissionDeniedForPersonalStatusChange,
    deactivate_personal,
    reactivate_personal,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class PersonalStatusServiceTests(TestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.actor = self.create_user('status-actor@test.com')
        self.actor.user_permissions.add(self.manage_personal)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def create_personal(self, suffix, **overrides):
        values = {
            'nombre': f'Nombre {suffix}',
            'apellido': 'Estado',
            'rol': 'asistente',
            'activo': True,
            'realiza_diagnostico': False,
            'realiza_lavado': True,
            'realiza_color': False,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def semantic_audits(self):
        return Auditoria.objects.filter(tabla=PERSONAL_STATUS_AUDIT_TABLE)

    def test_active_personal_is_deactivated(self):
        personal = self.create_personal('deactivate')

        result = deactivate_personal(
            self.actor,
            personal,
            'Baja laboral administrativa',
        )

        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertTrue(result.previous_active)
        self.assertFalse(result.current_active)
        self.assertFalse(personal.activo)

    def test_deactivating_inactive_personal_is_noop_without_audit(self):
        personal = self.create_personal('deactivate-noop', activo=False)
        audit_count = Auditoria.objects.count()

        result = deactivate_personal(
            self.actor,
            personal,
            'Confirmacion de baja existente',
        )

        self.assertFalse(result.changed)
        self.assertFalse(result.previous_active)
        self.assertFalse(result.current_active)
        self.assertIsNone(result.audit_id)
        self.assertEqual(Auditoria.objects.count(), audit_count)

    def test_inactive_personal_is_reactivated(self):
        personal = self.create_personal('reactivate', activo=False)

        result = reactivate_personal(
            self.actor,
            personal,
            'Reincorporacion laboral aprobada',
        )

        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertFalse(result.previous_active)
        self.assertTrue(result.current_active)
        self.assertTrue(personal.activo)

    def test_reactivating_active_personal_is_noop_without_audit(self):
        personal = self.create_personal('reactivate-noop')
        audit_count = Auditoria.objects.count()

        result = reactivate_personal(
            self.actor,
            personal,
            'Confirmacion de actividad existente',
        )

        self.assertFalse(result.changed)
        self.assertTrue(result.previous_active)
        self.assertTrue(result.current_active)
        self.assertIsNone(result.audit_id)
        self.assertEqual(Auditoria.objects.count(), audit_count)

    def test_link_user_account_role_and_client_are_preserved(self):
        user = self.create_user(
            'status-linked@test.com',
            is_active=False,
            is_staff=True,
        )
        original_password = user.password
        role_group = Group.objects.get(name=BusinessRole.EMPLEADO)
        technical_group = Group.objects.create(name='STATUS_TECHNICAL')
        individual_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        user.groups.add(role_group, technical_group)
        user.user_permissions.add(individual_permission)
        cliente = Cliente.objects.create(usuario=user, zona='Centro')
        personal = self.create_personal('linked', usuario=user)
        group_ids = set(user.groups.values_list('pk', flat=True))
        permission_ids = set(
            user.user_permissions.values_list('pk', flat=True)
        )

        result = deactivate_personal(
            self.actor,
            personal,
            'Baja preservando identidad y acceso',
        )

        personal.refresh_from_db()
        user.refresh_from_db()
        cliente.refresh_from_db()
        self.assertEqual(personal.usuario, user)
        self.assertFalse(user.is_active)
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
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))
        self.assertEqual(cliente.zona, 'Centro')
        self.assertEqual(result.user_id, user.pk)
        self.assertFalse(result.user_active)
        self.assertEqual(result.current_role, BusinessRole.EMPLEADO)
        self.assertIn('USER_INACTIVE', result.warnings)

    def test_reactivation_does_not_reactivate_linked_user(self):
        user = self.create_user('status-inactive-user@test.com', is_active=False)
        user.groups.add(Group.objects.get(name=BusinessRole.PROFESIONAL))
        personal = self.create_personal(
            'inactive-user',
            usuario=user,
            activo=False,
        )

        result = reactivate_personal(
            self.actor,
            personal,
            'Reactivar perfil laboral solamente',
        )

        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertFalse(user.is_active)
        self.assertFalse(result.user_active)
        self.assertEqual(result.current_role, BusinessRole.PROFESIONAL)

    def test_personal_role_skills_and_relations_are_preserved(self):
        personal = self.create_personal(
            'relations',
            rol='colorista',
            realiza_diagnostico=True,
            realiza_lavado=False,
            realiza_color=True,
        )
        schedule = HorarioLaboral.objects.create(
            personal=personal,
            dia_semana=0,
            hora_inicio=time(9, 0),
            hora_fin=time(17, 0),
        )
        now = timezone.now()
        block = BloqueoAgenda.objects.create(
            personal=personal,
            fecha_inicio=now + timedelta(days=1),
            fecha_fin=now + timedelta(days=2),
            motivo='Vacaciones programadas',
        )
        client_user = self.create_user('status-turn-client@test.com')
        client = Cliente.objects.create(usuario=client_user)
        appointment = Turno.objects.create(
            cliente=client,
            profesional=personal,
            fecha=date.today() + timedelta(days=3),
            hora_inicio=time(10, 0),
        )

        deactivate_personal(
            self.actor,
            personal,
            'Baja preservando relaciones laborales',
        )

        personal.refresh_from_db()
        self.assertEqual(personal.rol, 'colorista')
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)
        self.assertTrue(HorarioLaboral.objects.filter(pk=schedule.pk).exists())
        self.assertTrue(BloqueoAgenda.objects.filter(pk=block.pk).exists())
        self.assertTrue(Turno.objects.filter(pk=appointment.pk).exists())
        appointment.refresh_from_db()
        self.assertEqual(appointment.profesional, personal)

    def test_real_changes_create_one_semantic_audit_each(self):
        personal = self.create_personal('audit')
        total_before = Auditoria.objects.count()

        deactivation = deactivate_personal(
            self.actor,
            personal,
            'Baja laboral auditada',
        )

        self.assertEqual(Auditoria.objects.count(), total_before + 1)
        deactivate_audit = self.semantic_audits().get()
        self.assertEqual(deactivate_audit.pk, deactivation.audit_id)
        self.assertEqual(
            deactivate_audit.valor_nuevo['event'],
            PERSONAL_DEACTIVATED_EVENT,
        )
        self.assertEqual(
            deactivate_audit.valor_nuevo['source'],
            PERSONAL_DEACTIVATED_SOURCE,
        )
        self.assertTrue(deactivate_audit.valor_nuevo['previous_active'])
        self.assertFalse(deactivate_audit.valor_nuevo['current_active'])

        reactivation = reactivate_personal(
            self.actor,
            personal,
            'Reactivacion laboral auditada',
        )

        self.assertEqual(Auditoria.objects.count(), total_before + 2)
        reactivate_audit = self.semantic_audits().get(
            pk=reactivation.audit_id
        )
        self.assertEqual(
            reactivate_audit.valor_nuevo['event'],
            PERSONAL_REACTIVATED_EVENT,
        )
        self.assertEqual(
            reactivate_audit.valor_nuevo['source'],
            PERSONAL_REACTIVATED_SOURCE,
        )
        self.assertFalse(reactivate_audit.valor_nuevo['previous_active'])
        self.assertTrue(reactivate_audit.valor_nuevo['current_active'])

    def test_audit_failure_rolls_back_status_change(self):
        personal = self.create_personal('audit-failure')

        with patch(
            'gestion.personal_access_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                deactivate_personal(
                    self.actor,
                    personal,
                    'Baja que debe revertirse',
                )

        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertFalse(self.semantic_audits().exists())

    def test_actor_without_manage_personal_is_rejected(self):
        actor = self.create_user('status-unauthorized@test.com', is_staff=True)
        personal = self.create_personal('unauthorized')

        with self.assertRaises(PermissionDeniedForPersonalStatusChange):
            deactivate_personal(
                actor,
                personal,
                'Intento sin permiso de negocio',
            )

        personal.refresh_from_db()
        self.assertTrue(personal.activo)

    def test_personal_without_user_changes_status(self):
        personal = self.create_personal('without-user')

        result = deactivate_personal(
            self.actor,
            personal,
            'Baja de personal sin acceso digital',
        )

        self.assertTrue(result.changed)
        self.assertIsNone(result.user_id)
        self.assertIsNone(result.user_active)
        self.assertIsNone(result.current_role)
        self.assertIn('NO_LINKED_USER', result.warnings)

    def test_multiple_business_roles_do_not_block_status_change(self):
        user = self.create_user('status-multiple-roles@test.com')
        user.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )
        personal = self.create_personal('multiple-roles', usuario=user)

        result = deactivate_personal(
            self.actor,
            personal,
            'Baja independiente de roles inconsistentes',
        )

        self.assertTrue(result.changed)
        self.assertIsNone(result.current_role)
        self.assertIn('INCONSISTENT_BUSINESS_ROLES', result.warnings)
        self.assertSetEqual(
            set(get_business_roles(user)),
            {BusinessRole.CLIENTE, BusinessRole.EMPLEADO},
        )

    def test_reason_is_required_even_for_noop(self):
        personal = self.create_personal('invalid-reason', activo=False)

        for reason in (None, '', ' ', 'x', 'x' * 501):
            with self.subTest(reason=reason):
                with self.assertRaises(InvalidPersonalStatusReason):
                    deactivate_personal(self.actor, personal, reason)

        self.assertFalse(self.semantic_audits().exists())
