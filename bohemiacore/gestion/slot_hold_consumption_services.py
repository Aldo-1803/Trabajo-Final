"""Consumo canónico interno de SlotHold (BH-058 A2)."""

from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models.functions import Now
from django.utils import timezone

from usuarios.models import Cliente

from .models import (
    Auditoria,
    Notificacion,
    Personal,
    Servicio,
    SlotHold,
    SlotHoldEquipmentRequirement,
    SlotHoldService,
    SolicitudTecnicaReserva,
    TipoEquipamiento,
    Turno,
)
from .slot_hold_clock import database_now
from .slot_hold_services import (
    SLOT_HOLD_RELEASED,
    _audit,
    _expire_locked_hold,
    _key_fingerprint,
    technical_request_is_current_for_hold,
)
from .turno_creation_services import (
    TurnoAvailabilityService,
    TurnoCreationError,
    TurnoCreationService,
    TurnoDetailDraft,
)


SLOT_HOLD_CONSUMED = 'SLOT_HOLD_CONSUMED'
TURN_CONFIRMED_FROM_HOLD = 'TURN_CONFIRMED_FROM_HOLD'


class SlotHoldConsumptionError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(detail)


class SlotHoldConsumptionConflict(SlotHoldConsumptionError):
    pass


class _ConditionalConsumptionLost(Exception):
    pass


@dataclass(frozen=True)
class SlotHoldConsumptionResult:
    hold: SlotHold
    turno: Turno | None
    created: bool
    code: str = ''
    detail: str = ''

    @property
    def succeeded(self):
        return self.turno is not None


@dataclass(frozen=True)
class _LockedHoldResources:
    cliente: Cliente
    personal: Personal
    snapshots: tuple
    services: tuple
    equipment_requirements: dict


def _failure(hold, code, detail):
    return SlotHoldConsumptionResult(
        hold=hold,
        turno=None,
        created=False,
        code=code,
        detail=detail,
    )


def _lock_resources(hold):
    cliente = Cliente.objects.select_for_update().get(pk=hold.cliente_id)

    snapshots = tuple(
        SlotHoldService.objects.filter(hold=hold).order_by('orden', 'pk')
    )
    service_ids = sorted({snapshot.servicio_id for snapshot in snapshots})
    services_by_id = {
        service.pk: service
        for service in Servicio.objects.select_for_update()
        .filter(pk__in=service_ids)
        .prefetch_related('requisitos_habilidad__habilidad')
        .order_by('pk')
    }
    services = tuple(
        services_by_id[snapshot.servicio_id]
        for snapshot in snapshots
        if snapshot.servicio_id in services_by_id
    )

    personal = Personal.objects.select_for_update().get(pk=hold.personal_id)

    requirement_rows = tuple(
        SlotHoldEquipmentRequirement.objects.filter(hold=hold).order_by(
            'tipo_equipamiento_id',
            'pk',
        )
    )
    requirement_type_ids = sorted({
        requirement.tipo_equipamiento_id for requirement in requirement_rows
    })
    locked_type_ids = set(
        TipoEquipamiento.objects.select_for_update()
        .filter(pk__in=requirement_type_ids)
        .order_by('pk')
        .values_list('pk', flat=True)
    )
    equipment_requirements = {
        requirement.tipo_equipamiento_id: requirement.cantidad_snapshot
        for requirement in requirement_rows
        if requirement.tipo_equipamiento_id in locked_type_ids
    }
    return _LockedHoldResources(
        cliente=cliente,
        personal=personal,
        snapshots=snapshots,
        services=services,
        equipment_requirements=equipment_requirements,
    )


def _release_invalidated_hold(
    *,
    hold,
    actor,
    operation_key,
    reason,
    code,
    detail,
):
    previous = hold.state
    now = database_now()
    if hold.expires_at <= now:
        result = _expire_locked_hold(
            hold,
            now=now,
            actor=actor,
            operation_key=operation_key,
        )
        return _failure(
            result.hold,
            'HOLD_EXPIRED',
            'La reserva temporal está vencida.',
        )
    hold.state = SlotHold.State.RELEASED
    hold.released_at = now
    hold.release_reason = reason
    hold.save(update_fields=['state', 'released_at', 'release_reason'])
    _audit(
        hold=hold,
        actor=actor,
        event=SLOT_HOLD_RELEASED,
        previous_state=previous,
        reason=reason,
        operation_key=operation_key,
    )
    return _failure(hold, code, detail)


def _audit_consumption(*, hold, turno, actor, snapshots, operation_key):
    event_at = hold.consumed_at.isoformat()
    services = [
        {
            'service_id': snapshot.servicio_id,
            'name': snapshot.nombre_snapshot,
            'duration_minutes': snapshot.duracion_minutos_snapshot,
        }
        for snapshot in snapshots
    ]
    payload = {
        'hold_public_id': str(hold.public_id),
        'solicitud_id': hold.solicitud_id,
        'evaluation_id': hold.evaluacion_id,
        'turno_id': turno.pk,
        'cliente_id': hold.cliente_id,
        'personal_id': hold.personal_id,
        'services': services,
        'starts_at': hold.starts_at.isoformat(),
        'ends_at': hold.ends_at.isoformat(),
        'previous_state': SlotHold.State.ACTIVE,
        'current_state': SlotHold.State.CONSUMED,
        'actor': getattr(actor, 'pk', None) or 'SYSTEM',
        'operation_key_sha256': _key_fingerprint(operation_key),
        'event_at': event_at,
    }
    Auditoria.objects.create(
        tabla=SLOT_HOLD_CONSUMED,
        registro_id=hold.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='MODIFICACION',
        valor_anterior={'state': SlotHold.State.ACTIVE},
        valor_nuevo={'event': SLOT_HOLD_CONSUMED, **payload},
    )
    Auditoria.objects.create(
        tabla=TURN_CONFIRMED_FROM_HOLD,
        registro_id=turno.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={'event': TURN_CONFIRMED_FROM_HOLD, **payload},
    )


def _create_confirmation_notification(*, hold, turno, snapshots):
    service_names = ', '.join(
        snapshot.nombre_snapshot for snapshot in snapshots
    )
    Notificacion.objects.get_or_create(
        usuario=hold.cliente.usuario,
        origen_entidad='SlotHold',
        origen_id=hold.pk,
        titulo='Turno confirmado',
        defaults={
            'mensaje': (
                f'Tu turno para {service_names} del {turno.fecha} '
                'está confirmado.'
            ),
            'tipo': 'informativa',
            'canal': 'app',
            'estado': 'pendiente',
            'datos_extra': {
                'event': SLOT_HOLD_CONSUMED,
                'turno_id': turno.pk,
            },
        },
    )


@transaction.atomic
def create_confirmed_turno_from_locked_hold(
    *,
    hold,
    operation_key,
    actor=None,
):
    """Consume un HOLD válido. No constituye autorización financiera."""
    key = (operation_key or '').strip()
    if not key or len(key) > 128:
        raise SlotHoldConsumptionError(
            'INVALID_OPERATION_KEY',
            'Debe informar una operation key válida.',
        )
    if hold is None or getattr(hold, 'pk', None) is None:
        raise SlotHoldConsumptionError(
            'SLOT_HOLD_NOT_FOUND',
            'La reserva temporal no existe.',
        )

    try:
        target = SlotHold.objects.only('solicitud_id').get(pk=hold.pk)
    except SlotHold.DoesNotExist as exc:
        raise SlotHoldConsumptionError(
            'SLOT_HOLD_NOT_FOUND',
            'La reserva temporal no existe.',
        ) from exc

    try:
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=target.solicitud_id
        )
        locked_hold = SlotHold.objects.select_for_update().get(pk=hold.pk)
    except (SolicitudTecnicaReserva.DoesNotExist, SlotHold.DoesNotExist) as exc:
        raise SlotHoldConsumptionError(
            'SLOT_HOLD_NOT_FOUND',
            'La reserva temporal no existe.',
        ) from exc

    if locked_hold.state == SlotHold.State.CONSUMED:
        if locked_hold.consumption_idempotency_key != key:
            raise SlotHoldConsumptionConflict(
                'HOLD_ALREADY_CONSUMED',
                'La reserva temporal ya fue consumida por otra operación.',
            )
        resources = _lock_resources(locked_hold)
        turno = Turno.objects.select_for_update().get(
            pk=locked_hold.consumed_turno_id
        )
        return SlotHoldConsumptionResult(
            hold=locked_hold,
            turno=turno,
            created=False,
        )
    if locked_hold.state == SlotHold.State.RELEASED:
        return _failure(
            locked_hold,
            'HOLD_RELEASED',
            'La reserva temporal ya fue liberada.',
        )
    if locked_hold.state == SlotHold.State.EXPIRED:
        return _failure(
            locked_hold,
            'HOLD_EXPIRED',
            'La reserva temporal está vencida.',
        )

    resources = _lock_resources(locked_hold)
    now = database_now()
    if locked_hold.expires_at <= now:
        result = _expire_locked_hold(
            locked_hold,
            now=now,
            actor=actor,
            operation_key=key,
        )
        return _failure(
            result.hold,
            'HOLD_EXPIRED',
            'La reserva temporal está vencida.',
        )

    if not technical_request_is_current_for_hold(
        solicitud=solicitud,
        hold=locked_hold,
        snapshots=resources.snapshots,
    ):
        return _release_invalidated_hold(
            hold=locked_hold,
            actor=actor,
            operation_key=key,
            reason=SlotHold.ReleaseReason.TECHNICAL_REQUEST_INVALIDATED,
            code='TECHNICAL_REQUEST_INVALIDATED',
            detail='La solicitud o evaluación técnica ya no está vigente.',
        )

    if (
        resources.cliente.pk != solicitud.cliente_id
        or not resources.cliente.activo
        or not resources.cliente.usuario.is_active
        or not resources.snapshots
        or len(resources.services) != len(resources.snapshots)
        or any(not service.activo for service in resources.services)
        or len(resources.equipment_requirements)
        != locked_hold.equipment_requirements.count()
    ):
        return _release_invalidated_hold(
            hold=locked_hold,
            actor=actor,
            operation_key=key,
            reason=SlotHold.ReleaseReason.RESOURCE_INVALIDATED,
            code='HOLD_RESOURCE_INVALIDATED',
            detail='Los recursos reservados ya no son válidos.',
        )

    duration_minutes = sum(
        snapshot.duracion_minutos_snapshot
        for snapshot in resources.snapshots
    )
    if (
        duration_minutes < 1
        or locked_hold.ends_at
        != locked_hold.starts_at + timedelta(minutes=duration_minutes)
    ):
        return _release_invalidated_hold(
            hold=locked_hold,
            actor=actor,
            operation_key=key,
            reason=SlotHold.ReleaseReason.RESOURCE_INVALIDATED,
            code='INVALID_HOLD_SNAPSHOT',
            detail='El snapshot de la reserva temporal no es válido.',
        )

    local_start = timezone.localtime(
        locked_hold.starts_at,
        timezone.get_current_timezone(),
    )
    try:
        TurnoAvailabilityService.validate_slot(
            fecha=local_start.date(),
            hora_inicio=local_start.time().replace(tzinfo=None),
            servicio=resources.services[0],
            servicios=resources.services,
            duracion_minutos=duration_minutes,
            profesional=resources.personal,
            cliente=resources.cliente,
            excluir_hold_id=locked_hold.pk,
            now=now,
            equipment_requirements=resources.equipment_requirements,
        )
    except TurnoCreationError as exc:
        return _release_invalidated_hold(
            hold=locked_hold,
            actor=actor,
            operation_key=key,
            reason=SlotHold.ReleaseReason.RESOURCE_INVALIDATED,
            code=exc.code,
            detail=exc.detail,
        )

    if SlotHold.objects.filter(
        consumption_idempotency_key=key
    ).exclude(pk=locked_hold.pk).exists():
        raise SlotHoldConsumptionConflict(
            'OPERATION_KEY_REUSED',
            'La operation key ya fue usada para otro HOLD.',
        )

    try:
        with transaction.atomic():
            turno = TurnoCreationService._create_from_locked_resources(
                cliente=resources.cliente,
                profesional=resources.personal,
                fecha=local_start.date(),
                hora_inicio=local_start.time().replace(tzinfo=None),
                source=Turno.CanalOrigen.WEB,
                estado=Turno.Estado.CONFIRMADO,
                detail_drafts=tuple(
                    TurnoDetailDraft(
                        servicio=service,
                        duracion_minutos=snapshot.duracion_minutos_snapshot,
                    )
                    for snapshot, service in zip(
                        resources.snapshots,
                        resources.services,
                    )
                ),
            )
            consumed_at = database_now()
            updated = SlotHold.objects.filter(
                pk=locked_hold.pk,
                state=SlotHold.State.ACTIVE,
                expires_at__gt=Now(),
                consumed_turno__isnull=True,
                consumption_idempotency_key__isnull=True,
            ).update(
                state=SlotHold.State.CONSUMED,
                consumed_turno=turno,
                consumed_at=consumed_at,
                consumption_idempotency_key=key,
            )
            if updated != 1:
                raise _ConditionalConsumptionLost
            locked_hold.refresh_from_db()
            _audit_consumption(
                hold=locked_hold,
                turno=turno,
                actor=actor,
                snapshots=resources.snapshots,
                operation_key=key,
            )
            _create_confirmation_notification(
                hold=locked_hold,
                turno=turno,
                snapshots=resources.snapshots,
            )
    except _ConditionalConsumptionLost:
        locked_hold.refresh_from_db()
        final_now = database_now()
        if (
            locked_hold.state == SlotHold.State.ACTIVE
            and locked_hold.expires_at <= final_now
        ):
            result = _expire_locked_hold(
                locked_hold,
                now=final_now,
                actor=actor,
                operation_key=key,
            )
            return _failure(
                result.hold,
                'HOLD_EXPIRED',
                'La reserva temporal venció durante el consumo.',
            )
        raise SlotHoldConsumptionConflict(
            'HOLD_CONSUMPTION_CONFLICT',
            'La reserva temporal cambió durante el consumo.',
        )
    except IntegrityError as exc:
        if SlotHold.objects.filter(
            consumption_idempotency_key=key
        ).exclude(pk=locked_hold.pk).exists():
            raise SlotHoldConsumptionConflict(
                'OPERATION_KEY_REUSED',
                'La operation key ya fue usada para otro HOLD.',
            ) from exc
        raise

    return SlotHoldConsumptionResult(
        hold=locked_hold,
        turno=turno,
        created=True,
    )
