from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.assisted_slot_hold_services import (
    ASSISTED_SLOT_HOLD_CREATED,
    ASSISTED_SLOT_HOLD_RELEASED,
    AssistedTechnicalBookingError,
    create_assisted_slot_hold,
)
from gestion.models import (
    Auditoria,
    Configuracion,
    Equipamiento,
    EvaluacionRiesgoTecnico,
    Habilidad,
    HorarioLaboral,
    Pago,
    PaymentIntent,
    Personal,
    PersonalHabilidad,
    PoliticaRiesgoTecnico,
    RequisitoServicio,
    Servicio,
    ServicioHabilidad,
    SlotHold,
    SlotHoldService,
    SolicitudTecnicaAsistidaOperacion,
    SolicitudTecnicaReserva,
    SolicitudTecnicaServicio,
    TechnicalRiskOutcome,
    TipoEquipamiento,
    Turno,
)
from usuarios.models import Cliente, Usuario


class AssistedSlotHoldFixtureMixin:
    def setUp(self):
        super().setUp()
        self.permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_turno_for_client',
        )
        self.operator = self.create_operator('primary')
        self.other_operator = self.create_operator('other')
        client_user = Usuario.objects.create_user(
            email='assisted-hold-client@test.com', password='pass1234'
        )
        self.cliente = Cliente.objects.create(usuario=client_user, activo=True)
        self.service = Servicio.objects.create(
            nombre='Color asistido',
            activo=True,
            duracion_estimada=60,
            precio_base='1000.00',
        )
        self.second_service = Servicio.objects.create(
            nombre='Nutrición asistida',
            activo=True,
            duracion_estimada=30,
            precio_base='500.00',
        )
        self.personal = Personal.objects.create(
            nombre='Ada', apellido='Lovelace', rol='colorista', activo=True
        )
        self.date = timezone.localdate() + timedelta(days=3)
        self.starts_at = timezone.make_aware(
            datetime.combine(self.date, time(10, 0)),
            timezone.get_current_timezone(),
        )
        HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=self.date.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
        )
        self.policy = PoliticaRiesgoTecnico.objects.create(
            version='BH063-I3-T1'
        )
        self.solicitud = self.create_assisted_request(
            operator=self.operator,
            cliente=self.cliente,
            services=(self.service, self.second_service),
        )
        Configuracion.objects.update_or_create(
            pk=1,
            defaults={
                'intervalo_turnos': 30,
                'slot_hold_ttl_minutes': 15,
            },
        )

    def create_operator(self, suffix):
        operator = Usuario.objects.create_user(
            email=f'assisted-hold-{suffix}@test.com', password='pass1234'
        )
        operator.user_permissions.add(self.permission)
        return operator

    def create_assisted_request(
        self,
        *,
        operator,
        cliente,
        services,
        date_value=None,
        state=SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
    ):
        date_value = date_value or self.date
        evaluation = EvaluacionRiesgoTecnico.objects.create(
            cliente=cliente,
            politica=self.policy,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            fecha_solicitada=date_value,
            input_snapshot={
                'cliente_id': cliente.pk,
                'servicios': [
                    {'id': service.pk, 'nombre': service.nombre}
                    for service in services
                ],
                'fecha_solicitada': date_value.isoformat(),
            },
            result_snapshot={
                'outcome': TechnicalRiskOutcome.APTO,
                'policy_version': self.policy.version,
                'rule_codes': [],
            },
        )
        solicitud = SolicitudTecnicaReserva.objects.create(
            cliente=cliente,
            fecha_preferida=date_value,
            hora_preferida=time(10),
            estado=state,
            evaluacion_vigente=evaluation,
            medio_solicitud=SolicitudTecnicaReserva.MedioSolicitud.PRESENCIAL,
            operador_registrante=operator,
        )
        SolicitudTecnicaServicio.objects.bulk_create([
            SolicitudTecnicaServicio(
                solicitud=solicitud,
                servicio=service,
                orden=index,
                nombre_snapshot=service.nombre,
            )
            for index, service in enumerate(services)
        ])
        return solicitud

    def hold_payload(self, **overrides):
        payload = {
            'operation_id': str(uuid4()),
            'personal_id': self.personal.pk,
            'starts_at': self.starts_at.isoformat(),
        }
        payload.update(overrides)
        return payload


class AssistedSlotHoldTests(AssistedSlotHoldFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.operator)

    def availability_url(self, solicitud=None):
        return reverse(
            'solicitud-tecnica-asistida-disponibilidad',
            args=[(solicitud or self.solicitud).pk],
        )

    def next_url(self, solicitud=None):
        return reverse(
            'solicitud-tecnica-asistida-proximo-intervalo',
            args=[(solicitud or self.solicitud).pk],
        )

    def hold_url(self, solicitud=None):
        return reverse(
            'solicitud-tecnica-asistida-hold',
            args=[(solicitud or self.solicitud).pk],
        )

    def release_url(self, solicitud=None):
        return reverse(
            'solicitud-tecnica-asistida-liberar-hold',
            args=[(solicitud or self.solicitud).pk],
        )

    def create_hold(self, *, key='assisted-hold-key', payload=None,
                    solicitud=None):
        return self.api.post(
            self.hold_url(solicitud),
            payload or self.hold_payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_availability_is_multiservice_minimal_and_authorized(self):
        incompatible = Personal.objects.create(
            nombre='Sin', apellido='Jornada', rol='asistente', activo=True
        )
        response = self.api.get(self.availability_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['duration_minutes'], 90)
        self.assertEqual(response.data['interval_minutes'], 30)
        self.assertEqual(response.data['hold_ttl_minutes'], 15)
        self.assertFalse(response.data['authoritative'])
        self.assertEqual(
            [item['id'] for item in response.data['profesionales']],
            [self.personal.pk],
        )
        professional_ids = {
            item['id'] for item in response.data['profesionales']
        }
        self.assertNotIn(incompatible.pk, professional_ids)
        serialized = str(response.data).lower()
        for forbidden in (
            'cliente', 'evaluacion', 'input_snapshot', 'result_snapshot',
            'formula', 'diagnostico', 'equipamiento',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_next_interval_uses_grid_and_is_strictly_after_database_now(self):
        today = timezone.localdate()
        solicitud = self.create_assisted_request(
            operator=self.operator,
            cliente=self.cliente,
            services=(self.service,),
            date_value=today,
        )
        HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=today.weekday(),
            hora_inicio=time(8),
            hora_fin=time(18),
            activo=True,
        )
        authoritative_now = timezone.make_aware(
            datetime.combine(today, time(10)),
            timezone.get_current_timezone(),
        )
        with patch(
            'gestion.assisted_slot_hold_services.database_now',
            return_value=authoritative_now,
        ):
            response = self.api.get(self.next_url(solicitud))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        starts_at = datetime.fromisoformat(response.data['slot']['starts_at'])
        self.assertEqual(starts_at.time(), time(10, 30))
        self.assertGreater(starts_at, authoritative_now)
        self.assertEqual(response.data['slot']['personal']['id'], self.personal.pk)

    def test_next_interval_can_filter_personal_and_reports_no_availability(self):
        response = self.api.get(
            self.next_url(),
            {'personal_id': self.personal.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        no_slot = self.api.get(self.next_url(), {'personal_id': 999999})
        self.assertEqual(no_slot.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            no_slot.data['error']['code'], 'NO_AVAILABILITY_FOUND'
        )

    def test_create_hold_reuses_canonical_snapshots_ttl_and_audits_actor(self):
        payload = self.hold_payload()
        response = self.create_hold(payload=payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['effective_state'], SlotHold.State.ACTIVE)
        self.assertEqual(
            response.data['next_action']['code'],
            'HOLD_ACTIVE_PENDING_PAYMENT',
        )
        self.assertFalse(response.data['next_action']['can_confirm_turno'])
        self.assertIn('no equivale', response.data['hold_notice'])
        hold = SlotHold.objects.get(public_id=response.data['public_id'])
        self.assertEqual(hold.created_by, self.operator)
        self.assertEqual(hold.cliente, self.cliente)
        self.assertEqual(hold.evaluacion, self.solicitud.evaluacion_vigente)
        self.assertEqual(hold.ends_at - hold.starts_at, timedelta(minutes=90))
        self.assertEqual(hold.expires_at - hold.created_at, timedelta(minutes=15))
        self.assertEqual(
            list(SlotHoldService.objects.filter(hold=hold).values_list(
                'servicio_id', flat=True
            )),
            [self.service.pk, self.second_service.pk],
        )
        operation = SolicitudTecnicaAsistidaOperacion.objects.get(command='HOLD')
        self.assertEqual(operation.hold, hold)
        self.assertEqual(str(operation.operation_id), payload['operation_id'])
        self.assertTrue(Auditoria.objects.filter(
            usuario=self.operator,
            valor_nuevo__event=ASSISTED_SLOT_HOLD_CREATED,
        ).exists())
        self.assertNotIn('assisted-hold-key', str(operation.idempotency_key_digest))
        self.assertEqual(Turno.objects.count(), 0)
        self.assertEqual(PaymentIntent.objects.count(), 0)
        self.assertEqual(Pago.objects.count(), 0)

    def test_create_retry_recovers_same_hold_and_changed_payload_conflicts(self):
        payload = self.hold_payload()
        first = self.create_hold(key='stable-hold', payload=payload)
        repeated = self.create_hold(key='stable-hold', payload=payload)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertTrue(repeated.data['recovered'])
        self.assertEqual(first.data['public_id'], repeated.data['public_id'])
        self.assertEqual(SlotHold.objects.count(), 1)
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.filter(
                command='HOLD'
            ).count(),
            1,
        )
        changed = self.create_hold(
            key='stable-hold',
            payload={
                **payload,
                'starts_at': (
                    self.starts_at + timedelta(minutes=30)
                ).isoformat(),
            },
        )
        self.assertEqual(changed.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(changed.data['error']['code'], 'IDEMPOTENCY_KEY_REUSED')

    def test_expired_retry_reports_effective_state_without_false_availability(self):
        payload = self.hold_payload()
        first = self.create_hold(key='expiring-assisted', payload=payload)
        hold = SlotHold.objects.get(public_id=first.data['public_id'])
        current = timezone.now()
        SlotHold.objects.filter(pk=hold.pk).update(
            created_at=current - timedelta(minutes=20),
            expires_at=current - timedelta(minutes=1),
        )
        repeated = self.create_hold(key='expiring-assisted', payload=payload)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertTrue(repeated.data['recovered'])
        self.assertEqual(repeated.data['effective_state'], SlotHold.State.EXPIRED)
        self.assertEqual(repeated.data['countdown']['seconds_remaining'], 0)
        self.assertEqual(
            repeated.data['next_action']['code'], 'SELECT_NEW_SLOT'
        )

    def test_release_is_operator_causal_scoped_and_idempotent(self):
        created = self.create_hold()
        public_id = created.data['public_id']
        payload = {
            'operation_id': str(uuid4()),
            'public_id': public_id,
        }
        first = self.api.post(
            self.release_url(), payload, format='json',
            HTTP_IDEMPOTENCY_KEY='release-assisted',
        )
        repeated = self.api.post(
            self.release_url(), payload, format='json',
            HTTP_IDEMPOTENCY_KEY='release-assisted',
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data['changed'])
        self.assertFalse(first.data['recovered'])
        self.assertTrue(repeated.data['recovered'])
        hold = SlotHold.objects.get(public_id=public_id)
        self.assertEqual(
            hold.release_reason, SlotHold.ReleaseReason.OPERATOR_CANCELLED
        )
        self.assertNotEqual(
            hold.release_reason, SlotHold.ReleaseReason.CLIENT_CANCELLED
        )
        self.assertTrue(Auditoria.objects.filter(
            usuario=self.operator,
            valor_nuevo__event=ASSISTED_SLOT_HOLD_RELEASED,
        ).exists())
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.filter(
                command='RELEASE'
            ).count(),
            1,
        )

    def test_expired_release_materializes_expiry_without_operator_cancellation(self):
        created = self.create_hold()
        hold = SlotHold.objects.get(public_id=created.data['public_id'])
        current = timezone.now()
        SlotHold.objects.filter(pk=hold.pk).update(
            created_at=current - timedelta(minutes=20),
            expires_at=current - timedelta(minutes=1),
        )
        response = self.api.post(
            self.release_url(),
            {'operation_id': str(uuid4()), 'public_id': str(hold.public_id)},
            format='json',
            HTTP_IDEMPOTENCY_KEY='release-expired-assisted',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertTrue(response.data['expiration_materialized'])
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.EXPIRED)
        self.assertEqual(hold.release_reason, SlotHold.ReleaseReason.TTL_EXPIRED)

    def test_permissions_scope_and_foreign_hold_are_enforced(self):
        no_permission = Usuario.objects.create_user(
            email='assisted-hold-denied@test.com', password='pass1234'
        )
        self.api.force_authenticate(no_permission)
        self.assertEqual(
            self.api.get(self.availability_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.api.force_authenticate(self.other_operator)
        self.assertEqual(
            self.api.get(self.availability_url()).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.create_hold(key='foreign-operator').status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.api.force_authenticate(self.operator)
        created = self.create_hold(key='owned-hold')
        self.api.force_authenticate(self.other_operator)
        foreign_release = self.api.post(
            self.release_url(),
            {
                'operation_id': str(uuid4()),
                'public_id': created.data['public_id'],
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='foreign-release',
        )
        self.assertEqual(foreign_release.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            SlotHold.objects.get().state, SlotHold.State.ACTIVE
        )

    def test_technical_client_service_personal_and_skill_preconditions(self):
        self.solicitud.estado = SolicitudTecnicaReserva.Estado.EN_REVISION
        self.solicitud.save(update_fields=['estado'])
        unapproved = self.create_hold(key='unapproved')
        self.assertEqual(unapproved.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            unapproved.data['error']['code'], 'TECHNICAL_REQUEST_NOT_APPROVED'
        )
        self.solicitud.estado = (
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
        )
        self.solicitud.save(update_fields=['estado'])

        self.second_service.activo = False
        self.second_service.save(update_fields=['activo'])
        inactive_service = self.create_hold(key='inactive-service')
        self.assertEqual(inactive_service.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(inactive_service.data['error']['code'], 'INVALID_SERVICES')
        self.second_service.activo = True
        self.second_service.save(update_fields=['activo'])

        skill = Habilidad.objects.create(
            code='ASSISTED_HOLD_SKILL', nombre='Hold skill', activa=True
        )
        ServicioHabilidad.objects.create(servicio=self.service, habilidad=skill)
        mismatch = self.create_hold(key='skill-mismatch')
        self.assertEqual(mismatch.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            mismatch.data['error']['code'], 'PERSONAL_SKILL_MISMATCH'
        )
        PersonalHabilidad.objects.create(
            personal=self.personal, habilidad=skill, activa=True
        )
        self.personal.activo = False
        self.personal.save(update_fields=['activo'])
        inactive_personal = self.create_hold(key='inactive-personal')
        self.assertEqual(inactive_personal.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            inactive_personal.data['error']['code'], 'INACTIVE_PERSONAL'
        )

    def test_equipment_and_existing_turno_conflicts_delegate_to_canonical_engine(self):
        equipment_type = TipoEquipamiento.objects.create(nombre='Casco asistido')
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        no_equipment = self.create_hold(key='no-equipment')
        self.assertEqual(no_equipment.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            no_equipment.data['error']['code'], 'EQUIPMENT_UNAVAILABLE'
        )
        Equipamiento.objects.create(
            codigo='ASSISTED-CASCO-1',
            nombre='Casco 1',
            tipo=equipment_type,
            estado=Equipamiento.EstadoRecurso.DISPONIBLE,
            is_active=True,
        )
        turno = Turno.objects.create(
            cliente=self.cliente,
            profesional=self.personal,
            fecha=self.date,
            hora_inicio=time(10),
            estado=Turno.Estado.CONFIRMADO,
        )
        turno.detalles.create(
            servicio=self.service,
            precio_historico='1000.00',
            duracion_minutos=90,
        )
        occupied = self.create_hold(key='occupied-by-turno')
        self.assertEqual(occupied.status_code, status.HTTP_409_CONFLICT)
        self.assertIn(
            occupied.data['error']['code'],
            {'SLOT_UNAVAILABLE', 'CLIENT_UNAVAILABLE'},
        )

    def test_assisted_audit_failure_rolls_back_hold_ledger_and_snapshots(self):
        with patch(
            'gestion.assisted_slot_hold_services._audit',
            side_effect=RuntimeError('assisted audit failed'),
        ):
            with self.assertRaises(RuntimeError):
                self.create_hold(key='rollback-hold')
        self.assertEqual(SlotHold.objects.count(), 0)
        self.assertEqual(SlotHoldService.objects.count(), 0)
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.filter(
                command='HOLD'
            ).count(),
            0,
        )

    def test_web_owner_hold_and_release_contract_remains_owner_only(self):
        web_request = self.create_assisted_request(
            operator=self.operator,
            cliente=self.cliente,
            services=(self.service,),
        )
        web_request.medio_solicitud = SolicitudTecnicaReserva.MedioSolicitud.WEB
        web_request.operador_registrante = self.cliente.usuario
        web_request.save(update_fields=[
            'medio_solicitud', 'operador_registrante',
        ])
        self.api.force_authenticate(self.cliente.usuario)
        response = self.api.post(
            reverse('solicitud-tecnica-hold', args=[web_request.pk]),
            {
                'personal_id': self.personal.pk,
                'starts_at': self.starts_at.isoformat(),
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='web-owner-regression',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        released = self.api.post(
            reverse('slot-hold-release', args=[response.data['public_id']]),
            {},
            format='json',
        )
        self.assertEqual(released.status_code, status.HTTP_200_OK)
        self.assertEqual(
            SlotHold.objects.get(public_id=response.data['public_id']).release_reason,
            SlotHold.ReleaseReason.CLIENT_CANCELLED,
        )


class AssistedSlotHoldConcurrencyTests(
    AssistedSlotHoldFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')

    @staticmethod
    def run_workers(*workers):
        barrier = Barrier(len(workers))

        def wrapped(worker):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return worker()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = [executor.submit(wrapped, worker) for worker in workers]
            return [future.result(timeout=30) for future in futures]

    def worker(self, *, solicitud, operator, key, operation_id, personal=None):
        def execute():
            try:
                result = create_assisted_slot_hold(
                    solicitud_id=solicitud.pk,
                    actor=Usuario.objects.get(pk=operator.pk),
                    idempotency_key=key,
                    operation_id=operation_id,
                    personal_id=(personal or self.personal).pk,
                    starts_at=self.starts_at,
                )
                return ('success', result.hold.pk, result.recovered)
            except AssistedTechnicalBookingError as exc:
                return ('conflict', exc.code, False)
        return execute

    def test_two_operators_competing_for_same_personal_have_one_winner(self):
        other_client_user = Usuario.objects.create_user(
            email='assisted-hold-race-client@test.com', password='pass1234'
        )
        other_client = Cliente.objects.create(usuario=other_client_user)
        other_request = self.create_assisted_request(
            operator=self.other_operator,
            cliente=other_client,
            services=(self.service, self.second_service),
        )
        results = self.run_workers(
            self.worker(
                solicitud=self.solicitud,
                operator=self.operator,
                key='operator-race-one',
                operation_id=uuid4(),
            ),
            self.worker(
                solicitud=other_request,
                operator=self.other_operator,
                key='operator-race-two',
                operation_id=uuid4(),
            ),
        )
        self.assertEqual(sum(item[0] == 'success' for item in results), 1)
        self.assertEqual(
            SlotHold.objects.filter(state=SlotHold.State.ACTIVE).count(), 1
        )
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.filter(
                command='HOLD'
            ).count(),
            1,
        )

    def test_concurrent_identical_retry_creates_one_hold_and_operation(self):
        operation_id = uuid4()
        results = self.run_workers(
            self.worker(
                solicitud=self.solicitud,
                operator=self.operator,
                key='identical-race',
                operation_id=operation_id,
            ),
            self.worker(
                solicitud=self.solicitud,
                operator=self.operator,
                key='identical-race',
                operation_id=operation_id,
            ),
        )
        self.assertEqual(sum(item[0] == 'success' for item in results), 2)
        self.assertEqual(sorted(item[2] for item in results), [False, True])
        self.assertEqual(SlotHold.objects.count(), 1)
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.filter(
                command='HOLD'
            ).count(),
            1,
        )
        self.assertEqual(Auditoria.objects.filter(
            valor_nuevo__event=ASSISTED_SLOT_HOLD_CREATED,
        ).count(), 1)

    def test_last_equipment_unit_has_one_assisted_winner(self):
        equipment_type = TipoEquipamiento.objects.create(
            nombre='Equipo asistido concurrente'
        )
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        Equipamiento.objects.create(
            codigo='ASSISTED-RACE-EQ',
            nombre='Equipo único',
            tipo=equipment_type,
            estado=Equipamiento.EstadoRecurso.DISPONIBLE,
            is_active=True,
        )
        other_personal = Personal.objects.create(
            nombre='Grace', apellido='Hopper', rol='asistente', activo=True
        )
        HorarioLaboral.objects.create(
            personal=other_personal,
            dia_semana=self.date.weekday(),
            hora_inicio=time(8),
            hora_fin=time(18),
            activo=True,
        )
        other_client_user = Usuario.objects.create_user(
            email='equipment-race-client@test.com', password='pass1234'
        )
        other_client = Cliente.objects.create(usuario=other_client_user)
        other_request = self.create_assisted_request(
            operator=self.other_operator,
            cliente=other_client,
            services=(self.service, self.second_service),
        )
        results = self.run_workers(
            self.worker(
                solicitud=self.solicitud,
                operator=self.operator,
                key='equipment-assisted-one',
                operation_id=uuid4(),
            ),
            self.worker(
                solicitud=other_request,
                operator=self.other_operator,
                key='equipment-assisted-two',
                operation_id=uuid4(),
                personal=other_personal,
            ),
        )
        self.assertEqual(sum(item[0] == 'success' for item in results), 1)
        self.assertEqual(
            SlotHold.objects.filter(state=SlotHold.State.ACTIVE).count(), 1
        )
