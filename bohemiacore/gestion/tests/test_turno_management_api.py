from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    Auditoria,
    BloqueoAgenda,
    DetalleTurno,
    HorarioLaboral,
    Personal,
    Servicio,
    Turno,
)
from gestion.turno_management_services import cancel_turno, reprogram_turno
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class TurnoManagementApiTests(APITestCase):
    def setUp(self):
        self.reprogram_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='reprogram_any_turno',
        )
        self.cancel_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='cancel_any_turno',
        )
        self.view_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='view_global_agenda',
        )
        self.arrival_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='register_arrival',
        )
        self.original_date = timezone.localdate() + timedelta(days=10)
        self.new_date = timezone.localdate() + timedelta(days=11)
        self.service = Servicio.objects.create(
            nombre='Servicio reprogramación semántica',
            duracion_estimada=60,
            precio_base='5000.00',
            activo=True,
        )
        self.personal = Personal.objects.create(
            nombre='Julia',
            apellido='Díaz',
            rol='asistente',
            activo=True,
        )
        HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=self.new_date.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
            permite_complemento=True,
            permite_diseno_color=True,
        )
        self.client_user, self.client_profile = self.create_client(
            'management-client@test.com'
        )
        self.turno = self.create_turno(
            cliente=self.client_profile,
            fecha=self.original_date,
            hora=time(10, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        self.reprogram_url = reverse('turno-reprogramar', args=[self.turno.pk])
        self.cancel_url = reverse('turno-cancelar', args=[self.turno.pk])

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='ManagementTests!2026',
            first_name='Ana',
            last_name='Pérez',
            **extra_fields,
        )

    def create_client(self, email):
        user = self.create_user(email)
        return user, Cliente.objects.create(usuario=user, activo=True)

    def create_turno(self, *, cliente, fecha, hora, estado, profesional=None):
        turno = Turno.objects.create(
            cliente=cliente,
            profesional=profesional or self.personal,
            fecha=fecha,
            hora_inicio=hora,
            estado=estado,
        )
        DetalleTurno.objects.create(
            turno=turno,
            servicio=self.service,
            precio_historico=self.service.precio_base,
            duracion_minutos=60,
        )
        return turno

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def reprogram_payload(self, **overrides):
        data = {
            'fecha': self.new_date.isoformat(),
            'hora': '11:00',
            'profesional_id': self.personal.pk,
            'motivo': 'Ajuste solicitado por el salón',
        }
        data.update(overrides)
        return data

    @staticmethod
    def cancel_payload(**overrides):
        data = {'motivo': 'El salón no podrá prestar el servicio'}
        data.update(overrides)
        return data

    def assert_reprogram_succeeds(self, actor):
        self.authenticate(actor)
        response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.fecha, self.new_date)
        self.assertEqual(self.turno.hora_inicio, time(11, 0))
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)
        self.assertEqual(self.turno.cambios_realizados, 1)

    def assert_cancel_succeeds(self, actor):
        self.authenticate(actor)
        response = self.client.post(
            self.cancel_url,
            self.cancel_payload(),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.CANCELADO)
        self.assertEqual(self.turno.cancelado_por, actor)

    def test_employee_permissions_allow_each_semantic_action(self):
        reprogram_actor = self.create_user('employee-reprogram@test.com', is_staff=False)
        self.assign_role(reprogram_actor, BusinessRole.EMPLEADO)
        self.assert_reprogram_succeeds(reprogram_actor)

        self.turno.fecha = self.original_date
        self.turno.hora_inicio = time(10, 0)
        self.turno.save(update_fields=['fecha', 'hora_inicio'])
        cancel_actor = self.create_user('employee-cancel@test.com', is_staff=False)
        self.assign_role(cancel_actor, BusinessRole.EMPLEADO)
        self.assert_cancel_succeeds(cancel_actor)

    def test_professional_permissions_allow_reprogram_then_cancel(self):
        actor = self.create_user('management-professional@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.PROFESIONAL)

        self.assert_reprogram_succeeds(actor)
        self.assert_cancel_succeeds(actor)

    def test_administrator_without_staff_flag_uses_effective_permissions(self):
        actor = self.create_user('management-administrator@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.ADMINISTRADOR)

        self.assert_reprogram_succeeds(actor)
        self.assert_cancel_succeeds(actor)

    def test_individual_permissions_are_independent(self):
        reprogram_actor = self.create_user('only-reprogram@test.com')
        reprogram_actor.user_permissions.add(self.reprogram_permission)
        self.authenticate(reprogram_actor)

        reprogram_response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(),
            format='json',
        )
        cancel_response = self.client.post(
            self.cancel_url,
            self.cancel_payload(),
            format='json',
        )

        self.assertEqual(reprogram_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel_response.status_code, status.HTTP_403_FORBIDDEN)

        cancel_actor = self.create_user('only-cancel@test.com')
        cancel_actor.user_permissions.add(self.cancel_permission)
        self.authenticate(cancel_actor)
        cancel_response = self.client.post(
            self.cancel_url,
            self.cancel_payload(),
            format='json',
        )
        reprogram_response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(hora='12:00'),
            format='json',
        )

        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        self.assertEqual(reprogram_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_client_and_unrelated_permissions_cannot_write(self):
        actors = [
            self.create_user('management-staff@test.com', is_staff=True),
            self.client_user,
        ]
        view_only = self.create_user('management-view-only@test.com')
        view_only.user_permissions.add(self.view_permission)
        actors.append(view_only)
        arrival_only = self.create_user('management-arrival-only@test.com')
        arrival_only.user_permissions.add(self.arrival_permission)
        actors.append(arrival_only)

        for actor in actors:
            self.authenticate(actor)
            with self.subTest(actor=actor.email, action='reprogram'):
                response = self.client.post(
                    self.reprogram_url,
                    self.reprogram_payload(),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            with self.subTest(actor=actor.email, action='cancel'):
                response = self.client.post(
                    self.cancel_url,
                    self.cancel_payload(),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reprogram_rejects_final_and_in_progress_states(self):
        actor = self.create_user('reprogram-states@test.com')
        actor.user_permissions.add(self.reprogram_permission)
        self.authenticate(actor)

        for current_state in (
            Turno.Estado.CANCELADO,
            Turno.Estado.REALIZADO,
            Turno.Estado.AUSENTE,
            Turno.Estado.EN_PROCESO,
        ):
            with self.subTest(state=current_state):
                self.turno.estado = current_state
                self.turno.save(update_fields=['estado'])
                response = self.client.post(
                    self.reprogram_url,
                    self.reprogram_payload(),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(
                    str(response.data['code']),
                    'INVALID_RESCHEDULE_TRANSITION',
                )

    def test_reprogram_rejects_occupied_slot(self):
        _, other_client = self.create_client('occupied-management@test.com')
        self.create_turno(
            cliente=other_client,
            fecha=self.new_date,
            hora=time(11, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        actor = self.create_user('occupied-management-actor@test.com')
        actor.user_permissions.add(self.reprogram_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(response.data['code']), 'SLOT_UNAVAILABLE')

    def test_reprogram_rejects_an_identical_assignment(self):
        HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=self.original_date.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
            permite_complemento=True,
            permite_diseno_color=True,
        )
        actor = self.create_user('unchanged-management-actor@test.com')
        actor.user_permissions.add(self.reprogram_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(
                fecha=self.original_date.isoformat(),
                hora='10:00',
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(response.data['code']), 'NO_RESCHEDULE_CHANGE')

    def test_reprogram_rejects_blocked_slot_without_exposing_reason(self):
        BloqueoAgenda.objects.create(
            personal=self.personal,
            fecha_inicio=timezone.make_aware(
                datetime.combine(self.new_date, time(10, 30))
            ),
            fecha_fin=timezone.make_aware(
                datetime.combine(self.new_date, time(12, 30))
            ),
            motivo='Motivo interno sensible',
        )
        actor = self.create_user('blocked-management-actor@test.com')
        actor.user_permissions.add(self.reprogram_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(response.data['code']), 'SLOT_BLOCKED')
        self.assertNotIn('Motivo interno sensible', str(response.data))

    def test_reprogram_requires_total_duration_to_fit_work_schedule(self):
        second_service = Servicio.objects.create(
            nombre='Servicio adicional de duración',
            duracion_estimada=60,
            precio_base='3000.00',
            activo=True,
        )
        DetalleTurno.objects.create(
            turno=self.turno,
            servicio=second_service,
            precio_historico=second_service.precio_base,
            duracion_minutos=60,
        )
        HorarioLaboral.objects.filter(
            personal=self.personal,
            dia_semana=self.new_date.weekday(),
        ).update(hora_fin=time(12, 0))
        actor = self.create_user('total-duration-management@test.com')
        actor.user_permissions.add(self.reprogram_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(response.data['code']), 'OUTSIDE_WORK_SCHEDULE')

    def test_cancel_rejects_realized_and_is_idempotent_when_already_cancelled(self):
        actor = self.create_user('cancel-contract@test.com')
        actor.user_permissions.add(self.cancel_permission)
        self.authenticate(actor)
        self.turno.estado = Turno.Estado.REALIZADO
        self.turno.save(update_fields=['estado'])

        invalid_response = self.client.post(
            self.cancel_url,
            self.cancel_payload(),
            format='json',
        )

        self.assertEqual(invalid_response.status_code, status.HTTP_409_CONFLICT)
        self.turno.estado = Turno.Estado.CONFIRMADO
        self.turno.save(update_fields=['estado'])
        first = self.client.post(self.cancel_url, self.cancel_payload(), format='json')
        second = self.client.post(self.cancel_url, self.cancel_payload(), format='json')

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data['changed'])
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(second.data['changed'])
        self.assertEqual(
            Auditoria.objects.filter(
                tabla='TURN_CANCELLED',
                registro_id=self.turno.pk,
            ).count(),
            1,
        )

    def test_semantic_audits_capture_actor_reason_and_snapshots(self):
        actor = self.create_user('management-audit@test.com')
        actor.user_permissions.add(
            self.reprogram_permission,
            self.cancel_permission,
        )

        reprogram_turno(
            actor=actor,
            turno_id=self.turno.pk,
            fecha=self.new_date,
            hora_inicio=time(11, 0),
            profesional_id=self.personal.pk,
            reason='Cambio operativo',
        )
        cancel_turno(
            actor=actor,
            turno_id=self.turno.pk,
            reason='Cancelación operativa',
        )

        reschedule_audit = Auditoria.objects.get(
            tabla='TURN_RESCHEDULED',
            registro_id=self.turno.pk,
        )
        cancel_audit = Auditoria.objects.get(
            tabla='TURN_CANCELLED',
            registro_id=self.turno.pk,
        )
        self.assertEqual(reschedule_audit.usuario, actor)
        self.assertEqual(reschedule_audit.valor_nuevo['motivo'], 'Cambio operativo')
        self.assertEqual(reschedule_audit.valor_anterior['cliente_id'], self.client_profile.pk)
        self.assertEqual(cancel_audit.usuario, actor)
        self.assertEqual(cancel_audit.valor_anterior['estado'], Turno.Estado.CONFIRMADO)
        self.assertEqual(cancel_audit.valor_nuevo['estado'], Turno.Estado.CANCELADO)

    def test_audit_failure_rolls_back_each_operation(self):
        actor = self.create_user('management-audit-failure@test.com')
        actor.user_permissions.add(
            self.reprogram_permission,
            self.cancel_permission,
        )

        with patch(
            'gestion.turno_management_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                reprogram_turno(
                    actor=actor,
                    turno_id=self.turno.pk,
                    fecha=self.new_date,
                    hora_inicio=time(11, 0),
                    profesional_id=self.personal.pk,
                    reason='Cambio con fallo',
                )
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.fecha, self.original_date)
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)

        with patch(
            'gestion.turno_management_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                cancel_turno(
                    actor=actor,
                    turno_id=self.turno.pk,
                    reason='Cancelación con fallo',
                )
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)

    def test_payloads_are_strict_and_reason_is_required(self):
        actor = self.create_user('management-strict@test.com')
        actor.user_permissions.add(
            self.reprogram_permission,
            self.cancel_permission,
        )
        self.authenticate(actor)

        reprogram_response = self.client.post(
            self.reprogram_url,
            self.reprogram_payload(estado=Turno.Estado.REALIZADO),
            format='json',
        )
        cancel_response = self.client.post(
            self.cancel_url,
            {'estado': Turno.Estado.CANCELADO},
            format='json',
        )

        self.assertEqual(reprogram_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('campos_no_permitidos', reprogram_response.data)
        self.assertEqual(cancel_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)

    def test_client_keeps_owned_endpoints_without_administrative_permissions(self):
        self.authenticate(self.client_user)

        options = self.client.get(
            reverse('turno-opciones-cliente', args=[self.turno.pk])
        )
        reprogram = self.client.post(
            reverse('turno-reprogramar-cliente', args=[self.turno.pk]),
            {
                'fecha': self.new_date.isoformat(),
                'hora_inicio': '11:00',
                'profesional_id': self.personal.pk,
            },
            format='json',
        )
        cancel = self.client.post(
            reverse('turno-cancelar-cliente', args=[self.turno.pk]),
            {'motivo': 'Ya no podré asistir'},
            format='json',
        )

        self.assertEqual(options.status_code, status.HTTP_200_OK)
        self.assertTrue(options.data['puede_reprogramar'])
        self.assertEqual(reprogram.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel.status_code, status.HTTP_200_OK)
        self.assertFalse(self.client_user.has_perm('gestion.reprogram_any_turno'))
        self.assertFalse(self.client_user.has_perm('gestion.cancel_any_turno'))

    def test_legacy_multiplexed_endpoints_are_closed(self):
        actor = self.create_user('legacy-management@test.com')
        actor.user_permissions.add(
            self.reprogram_permission,
            self.cancel_permission,
        )
        self.authenticate(actor)

        for url_name in ('turno-gestionar-cancelacion', 'turno-gestionar-profesional'):
            with self.subTest(url_name=url_name):
                response = self.client.post(
                    reverse(url_name, args=[self.turno.pk]),
                    {'accion': 'CANCELAR'},
                    format='json',
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_405_METHOD_NOT_ALLOWED,
                )
