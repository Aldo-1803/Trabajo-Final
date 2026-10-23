from datetime import time
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Turno
from gestion.turno_arrival_services import register_turno_arrival
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class TurnoArrivalApiTests(APITestCase):
    def setUp(self):
        self.arrival_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='register_arrival',
        )
        self.global_agenda_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='view_global_agenda',
        )
        self.client_user = self.create_user('arrival-client@test.com')
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            activo=True,
        )
        self.turno = Turno.objects.create(
            cliente=self.client_profile,
            fecha=timezone.localdate(),
            hora_inicio=time(10, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        self.url = reverse('turno-registrar-llegada', args=[self.turno.pk])

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='ArrivalTests!2026',
            first_name='Ana',
            last_name='Pérez',
            **extra_fields,
        )

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def assert_arrival_succeeds(self, actor):
        self.authenticate(actor)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['estado_anterior'], Turno.Estado.CONFIRMADO)
        self.assertEqual(response.data['estado_actual'], Turno.Estado.EN_PROCESO)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.EN_PROCESO)

    def test_employee_without_staff_flag_registers_arrival(self):
        actor = self.create_user('arrival-employee@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.EMPLEADO)

        self.assert_arrival_succeeds(actor)

    def test_professional_registers_arrival_by_base_permission(self):
        actor = self.create_user('arrival-professional@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.PROFESIONAL)

        self.assert_arrival_succeeds(actor)

    def test_administrator_without_staff_flag_registers_arrival(self):
        actor = self.create_user('arrival-administrator@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.ADMINISTRADOR)

        self.assert_arrival_succeeds(actor)

    def test_individual_permission_registers_arrival_without_global_agenda(self):
        actor = self.create_user('arrival-individual@test.com', is_staff=False)
        actor.user_permissions.add(self.arrival_permission)
        self.assertFalse(actor.has_perm('gestion.view_global_agenda'))

        self.assert_arrival_succeeds(actor)

    def test_staff_without_arrival_permission_is_forbidden(self):
        actor = self.create_user('arrival-staff@test.com', is_staff=True)
        self.authenticate(actor)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)

    def test_client_is_forbidden(self):
        self.authenticate(self.client_user)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_is_unauthorized(self):
        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_global_agenda_permission_alone_is_not_enough(self):
        actor = self.create_user('arrival-agenda-only@test.com')
        actor.user_permissions.add(self.global_agenda_permission)
        self.authenticate(actor)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_arrival_permission_does_not_grant_global_agenda_read(self):
        actor = self.create_user('arrival-without-agenda@test.com')
        actor.user_permissions.add(self.arrival_permission)
        self.authenticate(actor)

        response = self.client.get(reverse('turno-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_permission_is_checked_before_lookup_for_unknown_turno(self):
        actor = self.create_user('arrival-no-enumeration@test.com')
        self.authenticate(actor)
        unknown_url = reverse('turno-registrar-llegada', args=[999999])

        response = self.client.post(unknown_url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_confirmed_turno_can_transition_to_in_progress(self):
        actor = self.create_user('arrival-transitions@test.com')
        actor.user_permissions.add(self.arrival_permission)
        self.authenticate(actor)

        invalid_states = (
            Turno.Estado.SOLICITADO,
            Turno.Estado.ESPERANDO_SENA,
            Turno.Estado.SUGERIDO,
            Turno.Estado.PENDIENTE,
            Turno.Estado.CANCELADO,
            Turno.Estado.REALIZADO,
            Turno.Estado.AUSENTE,
        )
        for invalid_state in invalid_states:
            with self.subTest(state=invalid_state):
                self.turno.estado = invalid_state
                self.turno.save(update_fields=['estado'])

                response = self.client.post(self.url, {}, format='json')

                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(
                    str(response.data['code']),
                    'INVALID_ARRIVAL_TRANSITION',
                )
                self.turno.refresh_from_db()
                self.assertEqual(self.turno.estado, invalid_state)

    def test_repeated_arrival_is_safe_noop_without_duplicate_semantic_audit(self):
        actor = self.create_user('arrival-idempotent@test.com')
        actor.user_permissions.add(self.arrival_permission)
        self.authenticate(actor)

        first_response = self.client.post(self.url, {}, format='json')
        second_response = self.client.post(self.url, {}, format='json')

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertTrue(first_response.data['changed'])
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertFalse(second_response.data['changed'])
        self.assertEqual(
            Auditoria.objects.filter(
                tabla='TURN_ARRIVAL_REGISTERED',
                registro_id=self.turno.pk,
            ).count(),
            1,
        )

    def test_semantic_audit_records_actor_and_transition(self):
        actor = self.create_user('arrival-audit@test.com')
        actor.user_permissions.add(self.arrival_permission)

        result = register_turno_arrival(actor=actor, turno_id=self.turno.pk)

        self.assertTrue(result.changed)
        audit = Auditoria.objects.get(
            tabla='TURN_ARRIVAL_REGISTERED',
            registro_id=self.turno.pk,
        )
        self.assertEqual(audit.usuario, actor)
        self.assertEqual(audit.valor_anterior, {'estado': Turno.Estado.CONFIRMADO})
        self.assertEqual(audit.valor_nuevo, {'estado': Turno.Estado.EN_PROCESO})

    def test_audit_failure_rolls_back_transition(self):
        actor = self.create_user('arrival-audit-failure@test.com')
        actor.user_permissions.add(self.arrival_permission)

        with patch(
            'gestion.turno_arrival_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                register_turno_arrival(actor=actor, turno_id=self.turno.pk)

        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)

    def test_payload_is_empty_and_cannot_choose_state(self):
        actor = self.create_user('arrival-strict-payload@test.com')
        actor.user_permissions.add(self.arrival_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.url,
            {'estado': Turno.Estado.REALIZADO},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('campos_no_permitidos', response.data)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)
