from datetime import timedelta
import time as time_module
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from gestion.models import (
    Auditoria,
    BloqueoAgenda,
    DetalleTurno,
    Equipamiento,
    EvaluacionRiesgoTecnico,
    Habilidad,
    Notificacion,
    Personal,
    PersonalHabilidad,
    RequisitoServicio,
    Servicio,
    ServicioHabilidad,
    SlotHold,
    SlotHoldService,
    SolicitudTecnicaReserva,
    SolicitudTecnicaServicio,
    TechnicalRiskOutcome,
    TipoEquipamiento,
    Turno,
)
from gestion.slot_hold_consumption_services import (
    SLOT_HOLD_CONSUMED,
    TURN_CONFIRMED_FROM_HOLD,
    SlotHoldConsumptionConflict,
    create_confirmed_turno_from_locked_hold,
)
from gestion.slot_hold_services import SLOT_HOLD_RELEASED, release_slot_hold
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin


class SlotHoldConsumptionTests(SlotHoldFixtureMixin, TestCase):
    def consume(self, hold, key='consume-operation-1'):
        return create_confirmed_turno_from_locked_hold(
            hold=hold,
            operation_key=key,
            actor=self.user,
        )

    def add_equipment_requirement(self):
        equipment_type = TipoEquipamiento.objects.create(nombre='A2 equipment')
        requirement = RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        equipment = Equipamiento.objects.create(
            codigo='A2-EQ-1',
            nombre='Equipo A2',
            tipo=equipment_type,
            estado=Equipamiento.EstadoRecurso.DISPONIBLE,
            is_active=True,
        )
        return requirement, equipment

    def test_active_hold_creates_one_confirmed_turno_and_links_consumption(self):
        hold = self.create_hold()
        result = self.consume(hold)

        self.assertTrue(result.succeeded)
        self.assertTrue(result.created)
        self.assertEqual(result.turno.estado, Turno.Estado.CONFIRMADO)
        self.assertEqual(result.turno.cliente, self.cliente)
        self.assertEqual(result.turno.profesional, self.personal)
        self.assertEqual(result.turno.fecha, self.date)
        self.assertEqual(result.turno.hora_inicio, self.starts_at.time())
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(hold.consumed_turno, result.turno)
        self.assertIsNotNone(hold.consumed_at)
        self.assertEqual(
            hold.consumption_idempotency_key,
            'consume-operation-1',
        )
        detail = DetalleTurno.objects.get(turno=result.turno)
        self.assertEqual(detail.servicio, self.service)
        self.assertEqual(detail.duracion_minutos, 60)

    def test_multiservice_details_use_duration_snapshots_and_current_minimum_price(self):
        second = Servicio.objects.create(
            nombre='Segundo servicio A2',
            duracion_estimada=30,
            precio_base='500.00',
            activo=True,
        )
        old_evaluation = self.solicitud.evaluacion_vigente
        replacement = EvaluacionRiesgoTecnico.objects.create(
            cliente=self.cliente,
            politica=self.policy,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            fecha_solicitada=self.date,
            input_snapshot={
                'cliente_id': self.cliente.pk,
                'servicios': [
                    {'id': self.service.pk, 'nombre': self.service.nombre},
                    {'id': second.pk, 'nombre': second.nombre},
                ],
                'fecha_solicitada': self.date.isoformat(),
            },
            result_snapshot={
                'outcome': TechnicalRiskOutcome.APTO,
                'policy_version': self.policy.version,
                'rule_codes': [],
            },
        )
        EvaluacionRiesgoTecnico.objects._set_superseded_by(
            evaluation_id=old_evaluation.pk,
            replacement_id=replacement.pk,
        )
        self.solicitud.evaluacion_vigente = replacement
        self.solicitud.save(update_fields=['evaluacion_vigente'])
        SolicitudTecnicaServicio.objects.create(
            solicitud=self.solicitud,
            servicio=second,
            orden=1,
            nombre_snapshot=second.nombre,
        )
        hold = self.create_hold()
        second.nombre = 'Nombre comercial modificado'
        second.duracion_estimada = 120
        second.precio_base = '750.00'
        second.save(update_fields=['nombre', 'duracion_estimada', 'precio_base'])

        result = self.consume(hold)

        details = list(
            result.turno.detalles.select_related('servicio').order_by('pk')
        )
        self.assertEqual(len(details), 2)
        self.assertEqual([detail.duracion_minutos for detail in details], [60, 30])
        self.assertEqual(str(details[1].precio_historico), '750.00')
        self.assertEqual(
            [snapshot.nombre_snapshot for snapshot in
             SlotHoldService.objects.filter(hold=hold).order_by('orden')],
            ['Servicio SlotHold', 'Segundo servicio A2'],
        )

    def test_retry_same_key_returns_same_turno_without_duplicate_effects(self):
        hold = self.create_hold()
        first = self.consume(hold, key='same-consume-key')
        retry = self.consume(hold, key='same-consume-key')

        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.turno.pk, retry.turno.pk)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(DetalleTurno.objects.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=SLOT_HOLD_CONSUMED).count(),
            1,
        )
        self.assertEqual(
            Auditoria.objects.filter(tabla=TURN_CONFIRMED_FROM_HOLD).count(),
            1,
        )
        self.assertEqual(
            Notificacion.objects.filter(
                origen_entidad='SlotHold',
                origen_id=hold.pk,
            ).count(),
            1,
        )

    def test_consumed_hold_with_another_key_is_a_conflict(self):
        hold = self.create_hold()
        self.consume(hold, key='first-consumption')
        with self.assertRaises(SlotHoldConsumptionConflict) as conflict:
            self.consume(hold, key='other-consumption')
        self.assertEqual(conflict.exception.code, 'HOLD_ALREADY_CONSUMED')
        self.assertEqual(Turno.objects.count(), 1)

    def test_expired_active_hold_is_materialized_without_turno(self):
        hold = self.direct_hold(
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
            key='expired-before-consumption',
        )
        result = self.consume(hold)

        self.assertEqual(result.code, 'HOLD_EXPIRED')
        self.assertFalse(result.succeeded)
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(Turno.objects.exists())

    def test_released_hold_does_not_consume(self):
        hold = self.create_hold()
        release_slot_hold(public_id=hold.public_id, actor=self.user)
        result = self.consume(hold)
        self.assertEqual(result.code, 'HOLD_RELEASED')
        self.assertFalse(Turno.objects.exists())

    def test_invalid_request_or_superseded_evaluation_releases_hold(self):
        for mode in ('request', 'evaluation'):
            with self.subTest(mode=mode):
                hold = self.create_hold(key=f'invalid-{mode}')
                if mode == 'request':
                    self.solicitud.estado = SolicitudTecnicaReserva.Estado.VENCIDA
                    self.solicitud.save(update_fields=['estado'])
                else:
                    replacement_request = self.create_approved_request(
                        self.other_cliente,
                        self.service,
                        self.date,
                    )
                    EvaluacionRiesgoTecnico.objects._set_superseded_by(
                        evaluation_id=self.solicitud.evaluacion_vigente_id,
                        replacement_id=replacement_request.evaluacion_vigente_id,
                    )
                result = self.consume(hold, key=f'consume-invalid-{mode}')
                self.assertEqual(result.code, 'TECHNICAL_REQUEST_INVALIDATED')
                hold.refresh_from_db()
                self.assertEqual(hold.state, SlotHold.State.RELEASED)
                self.assertEqual(
                    hold.release_reason,
                    SlotHold.ReleaseReason.TECHNICAL_REQUEST_INVALIDATED,
                )
                self.assertFalse(Turno.objects.exists())
                self.assertEqual(
                    Auditoria.objects.filter(
                        tabla=SLOT_HOLD_RELEASED,
                        registro_id=hold.pk,
                    ).count(),
                    1,
                )
                if mode == 'request':
                    self.solicitud.estado = (
                        SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
                    )
                    self.solicitud.save(update_fields=['estado'])

    def test_inactive_personal_releases_hold_without_turno(self):
        hold = self.create_hold()
        self.personal.activo = False
        self.personal.save(update_fields=['activo'])
        result = self.consume(hold)
        self.assertEqual(result.code, 'INACTIVE_PERSONAL')
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.RELEASED)
        self.assertEqual(
            hold.release_reason,
            SlotHold.ReleaseReason.RESOURCE_INVALIDATED,
        )
        self.assertFalse(Turno.objects.exists())

    def test_withdrawn_skill_or_new_block_releases_hold(self):
        skill = Habilidad.objects.create(code='A2_SKILL', nombre='A2 skill')
        ServicioHabilidad.objects.create(servicio=self.service, habilidad=skill)
        assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=skill,
            activa=True,
        )
        hold = self.create_hold()
        assignment.activa = False
        assignment.save(update_fields=['activa'])
        result = self.consume(hold, key='withdrawn-skill')
        self.assertEqual(result.code, 'PERSONAL_SKILL_MISMATCH')
        self.assertFalse(Turno.objects.exists())

        assignment.activa = True
        assignment.save(update_fields=['activa'])
        second_request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        second_hold = self.create_hold(
            solicitud=second_request,
            actor=self.other_user,
            key='blocked-hold',
        )
        BloqueoAgenda.objects.create(
            personal=self.personal,
            fecha_inicio=self.starts_at,
            fecha_fin=self.starts_at + timedelta(minutes=60),
            motivo='Bloqueo posterior al HOLD',
        )
        blocked = create_confirmed_turno_from_locked_hold(
            hold=second_hold,
            operation_key='blocked-consumption',
            actor=self.other_user,
        )
        self.assertEqual(blocked.code, 'SLOT_BLOCKED')
        self.assertFalse(Turno.objects.exists())

    def test_equipment_reduction_releases_but_commercial_change_uses_snapshot(self):
        requirement, equipment = self.add_equipment_requirement()
        hold = self.create_hold()
        other_request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        other_hold = self.create_hold(
            solicitud=other_request,
            actor=self.other_user,
            starts_at=self.starts_at + timedelta(hours=2),
            key='equipment-reduced',
        )
        requirement.cantidad_minima = 2
        requirement.save(update_fields=['cantidad_minima'])
        successful = self.consume(hold, key='equipment-snapshot')
        self.assertTrue(successful.succeeded)

        equipment.estado = Equipamiento.EstadoRecurso.MANTENIMIENTO
        equipment.save(update_fields=['estado'])
        reduced = create_confirmed_turno_from_locked_hold(
            hold=other_hold,
            operation_key='equipment-reduced-consume',
            actor=self.other_user,
        )
        self.assertEqual(reduced.code, 'EQUIPMENT_UNAVAILABLE')
        other_hold.refresh_from_db()
        self.assertEqual(other_hold.state, SlotHold.State.RELEASED)

    def test_new_personal_or_client_conflict_prevents_consumption(self):
        for conflict_kind in ('personal', 'client'):
            with self.subTest(conflict_kind=conflict_kind):
                hold = self.create_hold(key=f'hold-{conflict_kind}')
                conflict_personal = self.personal
                conflict_client = self.other_cliente
                if conflict_kind == 'client':
                    conflict_personal = Personal.objects.create(
                        nombre='Other',
                        apellido='Professional',
                        rol='asistente',
                        activo=True,
                    )
                    conflict_client = self.cliente
                turno = Turno.objects.create(
                    cliente=conflict_client,
                    profesional=conflict_personal,
                    fecha=self.date,
                    hora_inicio=self.starts_at.time(),
                    estado=Turno.Estado.CONFIRMADO,
                )
                turno.detalles.create(
                    servicio=self.service,
                    precio_historico=self.service.precio_base,
                    duracion_minutos=60,
                )
                result = self.consume(
                    hold,
                    key=f'consume-conflict-{conflict_kind}',
                )
                expected = (
                    'SLOT_UNAVAILABLE'
                    if conflict_kind == 'personal'
                    else 'CLIENT_UNAVAILABLE'
                )
                self.assertEqual(result.code, expected)
                self.assertEqual(Turno.objects.count(), 1)
                turno.delete()

    def test_consumption_audit_hashes_key_and_confirmation_is_explicit_once(self):
        hold = self.create_hold()
        result = self.consume(hold, key='secret-operation-key')
        audit = Auditoria.objects.get(
            tabla=SLOT_HOLD_CONSUMED,
            registro_id=hold.pk,
        )
        self.assertEqual(audit.valor_nuevo['turno_id'], result.turno.pk)
        self.assertNotIn('secret-operation-key', str(audit.valor_nuevo))
        notification = Notificacion.objects.get(
            origen_entidad='SlotHold',
            origen_id=hold.pk,
        )
        self.assertEqual(notification.datos_extra['turno_id'], result.turno.pk)
        self.assertNotIn('Seña', notification.mensaje)

    def test_consumed_constraint_requires_turno_timestamp_and_operation_key(self):
        hold = self.create_hold()
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                SlotHold.objects.filter(pk=hold.pk).update(
                    state=SlotHold.State.CONSUMED,
                )

    def test_conditional_expiry_after_turno_insert_rolls_back_savepoint(self):
        hold = self.create_hold(key='conditional-expiry')
        deadline = timezone.now() + timedelta(seconds=1)
        SlotHold.objects.filter(pk=hold.pk).update(expires_at=deadline)
        from gestion.turno_creation_services import TurnoCreationService
        original_create = TurnoCreationService._create_from_locked_resources

        def create_then_cross_deadline(*args, **kwargs):
            turno = original_create(*args, **kwargs)
            time_module.sleep(1.2)
            return turno

        with patch.object(
            TurnoCreationService,
            '_create_from_locked_resources',
            side_effect=create_then_cross_deadline,
        ):
            result = self.consume(hold, key='conditional-expiry-operation')

        self.assertEqual(result.code, 'HOLD_EXPIRED')
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(Turno.objects.exists())
        self.assertFalse(DetalleTurno.objects.exists())

    def test_audit_failure_rolls_back_turno_details_hold_and_notification(self):
        hold = self.create_hold(key='atomic-audit-failure')
        with patch(
            'gestion.slot_hold_consumption_services._audit_consumption',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                self.consume(hold, key='atomic-audit-operation')

        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.ACTIVE)
        self.assertIsNone(hold.consumed_turno_id)
        self.assertFalse(Turno.objects.exists())
        self.assertFalse(DetalleTurno.objects.exists())
        self.assertFalse(
            Notificacion.objects.filter(
                origen_entidad='SlotHold',
                origen_id=hold.pk,
            ).exists()
        )
