from datetime import datetime, time, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    Auditoria,
    Configuracion,
    Equipamiento,
    EvaluacionRiesgoTecnico,
    HorarioLaboral,
    Personal,
    PoliticaRiesgoTecnico,
    RequisitoServicio,
    Servicio,
    SlotHold,
    SlotHoldEquipmentRequirement,
    SlotHoldService,
    SolicitudTecnicaReserva,
    SolicitudTecnicaServicio,
    TechnicalRiskOutcome,
    TipoEquipamiento,
    Turno,
)
from gestion.slot_hold_clock import effective_hold_state
from gestion.slot_hold_services import (
    SLOT_HOLD_CREATED,
    SLOT_HOLD_EXPIRED,
    SLOT_HOLD_RELEASED,
    SlotHoldConflict,
    create_slot_hold,
    expire_slot_hold,
    release_slot_hold,
)
from gestion.turno_creation_services import TurnoAvailabilityService
from usuarios.models import Cliente, Usuario


class SlotHoldFixtureMixin:
    def setUp(self):
        super().setUp()
        self.user = Usuario.objects.create_user(
            email='hold-owner@test.com', password='pass1234'
        )
        self.cliente = Cliente.objects.create(usuario=self.user, activo=True)
        self.other_user = Usuario.objects.create_user(
            email='hold-other@test.com', password='pass1234'
        )
        self.other_cliente = Cliente.objects.create(
            usuario=self.other_user, activo=True
        )
        self.service = Servicio.objects.create(
            nombre='Servicio SlotHold',
            duracion_estimada=60,
            precio_base='1000.00',
            activo=True,
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
        self.policy = PoliticaRiesgoTecnico.objects.create(version='HOLD-T1')
        self.solicitud = self.create_approved_request(
            self.cliente, self.service, self.date
        )
        Configuracion.objects.update_or_create(
            pk=1,
            defaults={'slot_hold_ttl_minutes': 15},
        )

    def create_approved_request(self, cliente, service, date_value, order=0):
        evaluation = EvaluacionRiesgoTecnico.objects.create(
            cliente=cliente,
            politica=self.policy,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            fecha_solicitada=date_value,
            input_snapshot={
                'cliente_id': cliente.pk,
                'servicios': [{'id': service.pk, 'nombre': service.nombre}],
                'fecha_solicitada': date_value.isoformat(),
            },
            result_snapshot={
                'outcome': TechnicalRiskOutcome.APTO,
                'policy_version': self.policy.version,
                'rule_codes': [],
            },
        )
        request = SolicitudTecnicaReserva.objects.create(
            cliente=cliente,
            fecha_preferida=date_value,
            hora_preferida=time(10, 0),
            estado=SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
            evaluacion_vigente=evaluation,
        )
        SolicitudTecnicaServicio.objects.create(
            solicitud=request,
            servicio=service,
            orden=order,
            nombre_snapshot=service.nombre,
        )
        return request

    def create_hold(self, *, key='hold-key-1', solicitud=None, personal=None,
                    starts_at=None, actor=None):
        return create_slot_hold(
            solicitud_id=(solicitud or self.solicitud).pk,
            personal_id=(personal or self.personal).pk,
            starts_at=starts_at or self.starts_at,
            idempotency_key=key,
            actor=actor or self.user,
        ).hold

    def direct_hold(self, *, solicitud=None, personal=None, state='ACTIVE',
                    created_at=None, expires_at=None, starts_at=None, key='direct'):
        starts_at = starts_at or self.starts_at
        created_at = created_at or timezone.now() - timedelta(minutes=2)
        expires_at = expires_at or timezone.now() + timedelta(minutes=10)
        kwargs = {}
        if state == SlotHold.State.EXPIRED:
            kwargs.update(
                expired_at=expires_at,
                release_reason=SlotHold.ReleaseReason.TTL_EXPIRED,
            )
        elif state == SlotHold.State.RELEASED:
            kwargs.update(
                released_at=timezone.now(),
                release_reason=SlotHold.ReleaseReason.CLIENT_CANCELLED,
            )
        return SlotHold.objects.create(
            solicitud=solicitud or self.solicitud,
            evaluacion=(solicitud or self.solicitud).evaluacion_vigente,
            cliente=(solicitud or self.solicitud).cliente,
            personal=personal or self.personal,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=60),
            state=state,
            created_at=created_at,
            expires_at=expires_at,
            created_by=(solicitud or self.solicitud).cliente.usuario,
            idempotency_key=key,
            **kwargs,
        )


class SlotHoldModelAndServiceTests(SlotHoldFixtureMixin, TestCase):
    def test_create_snapshots_ttl_constraints_and_semantic_audit(self):
        equipment_type = TipoEquipamiento.objects.create(nombre='Vaporizador')
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=2,
        )
        for index in range(2):
            Equipamiento.objects.create(
                codigo=f'VAP-{index}',
                nombre=f'Vaporizador {index}',
                tipo=equipment_type,
                estado=Equipamiento.EstadoRecurso.DISPONIBLE,
                is_active=True,
            )

        hold = self.create_hold()

        self.assertEqual(hold.state, SlotHold.State.ACTIVE)
        self.assertEqual(hold.ends_at - hold.starts_at, timedelta(minutes=60))
        self.assertEqual(hold.expires_at - hold.created_at, timedelta(minutes=15))
        snapshot = SlotHoldService.objects.get(hold=hold)
        self.assertEqual(snapshot.nombre_snapshot, self.service.nombre)
        self.assertEqual(snapshot.duracion_minutos_snapshot, 60)
        requirement = SlotHoldEquipmentRequirement.objects.get(hold=hold)
        self.assertEqual(requirement.cantidad_snapshot, 2)
        audit = Auditoria.objects.get(tabla=SLOT_HOLD_CREATED)
        self.assertEqual(audit.usuario, self.user)
        self.assertEqual(audit.valor_nuevo['hold_public_id'], str(hold.public_id))
        self.assertNotIn('hold-key-1', str(audit.valor_nuevo))
        self.assertFalse(Turno.objects.exists())

    def test_effective_state_boundaries_are_semi_open(self):
        hold = self.create_hold()
        expiry = hold.expires_at
        self.assertEqual(
            effective_hold_state(hold, at=expiry - timedelta(microseconds=1)),
            SlotHold.State.ACTIVE,
        )
        self.assertEqual(
            effective_hold_state(hold, at=expiry), SlotHold.State.EXPIRED
        )
        self.assertEqual(
            effective_hold_state(hold, at=expiry + timedelta(microseconds=1)),
            SlotHold.State.EXPIRED,
        )

    def test_idempotency_and_active_hold_conflicts(self):
        first = self.create_hold(key='same-key')
        repeated = self.create_hold(key='same-key')
        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(SlotHold.objects.count(), 1)
        self.assertEqual(Auditoria.objects.filter(tabla=SLOT_HOLD_CREATED).count(), 1)

        with self.assertRaises(SlotHoldConflict) as changed_payload:
            self.create_hold(
                key='same-key', starts_at=self.starts_at + timedelta(hours=1)
            )
        self.assertEqual(changed_payload.exception.code, 'IDEMPOTENCY_KEY_REUSED')
        with self.assertRaises(SlotHoldConflict) as another_key:
            self.create_hold(key='another-key')
        self.assertEqual(another_key.exception.code, 'ACTIVE_HOLD_EXISTS')

    def test_expired_active_is_materialized_and_new_hold_is_allowed(self):
        old = self.direct_hold(
            created_at=timezone.now() - timedelta(minutes=30),
            expires_at=timezone.now() - timedelta(minutes=15),
            key='expired-active',
        )
        new = self.create_hold(key='new-after-expiry')
        old.refresh_from_db()
        self.assertEqual(old.state, SlotHold.State.EXPIRED)
        self.assertIsNotNone(old.expired_at)
        self.assertNotEqual(old.pk, new.pk)

    def test_release_and_expire_are_terminal_idempotent_and_audited(self):
        hold = self.create_hold()
        released = release_slot_hold(public_id=hold.public_id, actor=self.user)
        repeated = release_slot_hold(public_id=hold.public_id, actor=self.user)
        self.assertTrue(released.changed)
        self.assertFalse(repeated.changed)
        self.assertEqual(Auditoria.objects.filter(tabla=SLOT_HOLD_RELEASED).count(), 1)

        request = self.create_approved_request(
            self.other_cliente, self.service, self.date
        )
        expiring = self.direct_hold(
            solicitud=request,
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
            key='expiring',
        )
        result = expire_slot_hold(hold_id=expiring.pk)
        repeated_expiry = expire_slot_hold(hold_id=expiring.pk)
        self.assertTrue(result.changed)
        self.assertFalse(repeated_expiry.changed)
        self.assertEqual(Auditoria.objects.filter(tabla=SLOT_HOLD_EXPIRED).count(), 1)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                SlotHold.objects.filter(pk=hold.pk).update(state=SlotHold.State.ACTIVE)

    def test_expiration_at_exact_deadline_and_no_early_expiration(self):
        hold = self.create_hold()
        with patch(
            'gestion.slot_hold_services.database_now',
            return_value=hold.expires_at - timedelta(microseconds=1),
        ):
            with self.assertRaises(SlotHoldConflict) as early:
                expire_slot_hold(hold_id=hold.pk)
        self.assertEqual(early.exception.code, 'HOLD_NOT_EXPIRED')
        with patch(
            'gestion.slot_hold_services.database_now',
            return_value=hold.expires_at,
        ):
            result = expire_slot_hold(hold_id=hold.pk)
        self.assertTrue(result.changed)


class SlotHoldAvailabilityTests(SlotHoldFixtureMixin, TestCase):
    def slot_available(self, *, personal=None, cliente=None, start=None):
        start = start or self.starts_at
        return TurnoAvailabilityService.is_slot_available(
            fecha=start.date(),
            hora_inicio=start.time().replace(tzinfo=None),
            servicio=self.service,
            profesional=personal or self.personal,
            cliente=cliente,
        )

    def test_request_alone_does_not_block_but_effective_hold_does(self):
        self.assertTrue(self.slot_available())
        hold = self.create_hold()
        self.assertFalse(self.slot_available())
        hold.state = SlotHold.State.RELEASED
        hold.released_at = timezone.now()
        hold.release_reason = SlotHold.ReleaseReason.CLIENT_CANCELLED
        hold.save(update_fields=['state', 'released_at', 'release_reason'])
        self.assertTrue(self.slot_available())

    def test_active_expired_job_down_does_not_block(self):
        hold = self.direct_hold(
            created_at=timezone.now() - timedelta(minutes=30),
            expires_at=timezone.now() - timedelta(minutes=1),
            key='job-down',
        )
        self.assertTrue(self.slot_available())
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.ACTIVE)

    def test_semi_open_boundaries_are_available(self):
        hold = self.create_hold()
        before = self.starts_at - timedelta(minutes=60)
        after = hold.ends_at
        self.assertTrue(self.slot_available(start=before))
        self.assertTrue(self.slot_available(start=after))

    def test_client_conflict_applies_across_different_personal(self):
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
        self.create_hold()
        self.assertFalse(
            self.slot_available(personal=other_personal, cliente=self.cliente)
        )

    def test_equipment_capacity_counts_turnos_and_effective_holds(self):
        equipment_type = TipoEquipamiento.objects.create(nombre='Casco térmico')
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        Equipamiento.objects.create(
            codigo='CASCO-1', nombre='Casco 1', tipo=equipment_type,
            estado=Equipamiento.EstadoRecurso.DISPONIBLE, is_active=True,
        )
        self.create_hold()
        other_personal = Personal.objects.create(
            nombre='Katherine', apellido='Johnson', rol='asistente', activo=True
        )
        HorarioLaboral.objects.create(
            personal=other_personal, dia_semana=self.date.weekday(),
            hora_inicio=time(8), hora_fin=time(18), activo=True,
        )
        self.assertFalse(self.slot_available(personal=other_personal))

    def test_turno_blocks_hold_and_hold_blocks_canonical_turno_creation(self):
        turno = Turno.objects.create(
            cliente=self.other_cliente,
            profesional=self.personal,
            fecha=self.date,
            hora_inicio=time(10),
            estado=Turno.Estado.CONFIRMADO,
        )
        turno.detalles.create(
            servicio=self.service,
            precio_historico='1000.00',
            duracion_minutos=60,
        )
        with self.assertRaises(SlotHoldConflict) as occupied:
            self.create_hold()
        self.assertEqual(occupied.exception.code, 'SLOT_UNAVAILABLE')


class SlotHoldApiAndCommandTests(SlotHoldFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def create_url(self, request=None):
        return reverse(
            'solicitud-tecnica-hold', args=[(request or self.solicitud).pk]
        )

    def payload(self, **overrides):
        data = {
            'personal_id': self.personal.pk,
            'starts_at': self.starts_at.isoformat(),
        }
        data.update(overrides)
        return data

    def test_create_status_and_release_contract(self):
        missing_key = self.api.post(self.create_url(), self.payload(), format='json')
        self.assertEqual(missing_key.status_code, status.HTTP_400_BAD_REQUEST)
        created = self.api.post(
            self.create_url(), self.payload(), format='json',
            HTTP_IDEMPOTENCY_KEY='api-key',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data['effective_state'], SlotHold.State.ACTIVE)
        self.assertEqual(
            set(created.data),
            {
                'public_id', 'starts_at', 'ends_at', 'expires_at',
                'persisted_state', 'effective_state', 'countdown', 'personal',
            },
        )
        self.assertNotIn('solicitud', created.data)
        public_id = created.data['public_id']
        status_response = self.api.get(reverse('slot-hold-detail', args=[public_id]))
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        released = self.api.post(
            reverse('slot-hold-release', args=[public_id]), {}, format='json'
        )
        self.assertEqual(released.status_code, status.HTTP_200_OK)
        self.assertTrue(released.data['changed'])
        self.assertEqual(released.data['effective_state'], SlotHold.State.RELEASED)

    def test_get_reports_effective_expired_without_mutating(self):
        hold = self.direct_hold(
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
            key='api-expired',
        )
        response = self.api.get(reverse('slot-hold-detail', args=[hold.public_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['persisted_state'], SlotHold.State.ACTIVE)
        self.assertEqual(response.data['effective_state'], SlotHold.State.EXPIRED)
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.ACTIVE)

    def test_ownership_staff_and_foreign_hold_never_bypass_scope(self):
        hold = self.create_hold()
        staff = Usuario.objects.create_user(
            email='staff-no-owner@test.com', password='pass1234', is_staff=True
        )
        self.api.force_authenticate(staff)
        self.assertEqual(
            self.api.get(reverse('slot-hold-detail', args=[hold.public_id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.api.post(self.create_url(), self.payload(), format='json',
                          HTTP_IDEMPOTENCY_KEY='staff-key').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_canonical_availability_and_legacy_alias_hide_effective_hold(self):
        self.create_hold(key='availability-endpoints')
        canonical = self.api.get(
            reverse('turno-consultar-disponibilidad'),
            {
                'servicio_id': self.service.pk,
                'fecha': self.date.isoformat(),
            },
        )
        legacy_alias = self.api.get(
            reverse('disponibilidad-turnos'),
            {
                'servicio_id': self.service.pk,
                'fecha': self.date.isoformat(),
            },
        )
        self.assertEqual(canonical.status_code, status.HTTP_200_OK)
        self.assertEqual(legacy_alias.status_code, status.HTTP_200_OK)
        canonical_times = {
            slot['hora']
            for day in canonical.data['disponibilidad']
            if day['fecha'] == self.date.isoformat()
            for professional in day['profesionales']
            for slot in professional['slots']
        }
        self.assertEqual(
            canonical_times,
            set(legacy_alias.data['horarios_disponibles']),
        )
        self.assertNotIn('10:00', canonical_times)

    def test_unapproved_and_superseded_requests_are_rejected(self):
        self.solicitud.estado = SolicitudTecnicaReserva.Estado.EN_REVISION
        self.solicitud.save(update_fields=['estado'])
        unapproved = self.api.post(
            self.create_url(), self.payload(), format='json',
            HTTP_IDEMPOTENCY_KEY='unapproved',
        )
        self.assertEqual(unapproved.status_code, status.HTTP_409_CONFLICT)
        self.solicitud.estado = SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
        self.solicitud.save(update_fields=['estado'])
        replacement_request = self.create_approved_request(
            self.other_cliente, self.service, self.date
        )
        EvaluacionRiesgoTecnico.objects._set_superseded_by(
            evaluation_id=self.solicitud.evaluacion_vigente_id,
            replacement_id=replacement_request.evaluacion_vigente_id,
        )
        superseded = self.api.post(
            self.create_url(), self.payload(), format='json',
            HTTP_IDEMPOTENCY_KEY='superseded',
        )
        self.assertEqual(superseded.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(superseded.data['code'], 'TECHNICAL_EVALUATION_NOT_CURRENT')

    def test_commands_expire_holds_and_legacy_cleaner_ignores_them(self):
        hold = self.direct_hold(
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
            key='command-expired',
        )
        call_command('limpiar_turnos')
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.ACTIVE)
        output = StringIO()
        call_command('expirar_slot_holds', batch_size=1, stdout=output)
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.EXPIRED)
        self.assertIn('examinados=1', output.getvalue())
        self.assertIn('expirados=1', output.getvalue())
        retry = StringIO()
        call_command('expirar_slot_holds', stdout=retry)
        self.assertIn('expirados=0', retry.getvalue())

    def test_configuration_ttl_only_affects_future_holds(self):
        first = self.create_hold(key='ttl-first')
        release_slot_hold(public_id=first.public_id, actor=self.user)
        config = Configuracion.objects.get(pk=1)
        config.slot_hold_ttl_minutes = 30
        config.save(update_fields=['slot_hold_ttl_minutes'])
        second = self.create_hold(key='ttl-second')
        first.refresh_from_db()
        self.assertEqual(first.expires_at - first.created_at, timedelta(minutes=15))
        self.assertEqual(second.expires_at - second.created_at, timedelta(minutes=30))
