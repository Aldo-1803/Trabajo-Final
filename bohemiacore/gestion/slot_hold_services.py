"""Lifecycle transaccional de reservas temporales de agenda (BH-058 A1)."""

from dataclasses import dataclass
from datetime import timedelta
import hashlib

from django.db import IntegrityError, transaction
from django.utils import timezone

from usuarios.models import Cliente

from .models import (
    Auditoria,
    Configuracion,
    Personal,
    PaymentIntent,
    RequisitoServicio,
    Servicio,
    SlotHold,
    SlotHoldEquipmentRequirement,
    SlotHoldService,
    SolicitudTecnicaReserva,
    TipoEquipamiento,
)
from .slot_hold_clock import database_now
from .turno_creation_services import TurnoAvailabilityService, TurnoCreationError


SLOT_HOLD_CREATED = 'SLOT_HOLD_CREATED'
SLOT_HOLD_RELEASED = 'SLOT_HOLD_RELEASED'
SLOT_HOLD_EXPIRED = 'SLOT_HOLD_EXPIRED'
DEFAULT_SLOT_HOLD_TTL_MINUTES = 15


class SlotHoldError(ValueError):
    def __init__(self, code, detail, field='non_field_errors'):
        self.code = code
        self.detail = detail
        self.field = field
        super().__init__(detail)


class SlotHoldNotFound(SlotHoldError):
    def __init__(self):
        super().__init__('SLOT_HOLD_NOT_FOUND', 'La reserva temporal no existe.')


class SlotHoldConflict(SlotHoldError):
    pass


@dataclass(frozen=True)
class SlotHoldCreateResult:
    hold: SlotHold
    created: bool


@dataclass(frozen=True)
class SlotHoldTransitionResult:
    hold: SlotHold
    changed: bool
    previous_state: str
    current_state: str
    expiration_materialized: bool = False


def technical_request_is_current_for_hold(*, solicitud, hold, snapshots):
    """Precondición técnica compartida por consumidores del HOLD."""
    evaluation = solicitud.evaluacion_vigente
    requested_service_ids = tuple(
        solicitud.servicios_solicitados.order_by('orden', 'pk').values_list(
            'servicio_id',
            flat=True,
        )
    )
    snapshot_service_ids = tuple(
        snapshot.servicio_id for snapshot in snapshots
    )
    evaluation_service_ids = tuple(
        item.get('id')
        for item in (
            evaluation.input_snapshot.get('servicios', [])
            if evaluation is not None
            else []
        )
        if isinstance(item, dict) and item.get('id') is not None
    )
    return bool(
        solicitud.estado
        == SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
        and evaluation is not None
        and evaluation.pk == hold.evaluacion_id
        and evaluation.superseded_by_id is None
        and evaluation.cliente_id == hold.cliente_id
        and evaluation.fecha_solicitada == solicitud.fecha_preferida
        and solicitud.cliente_id == hold.cliente_id
        and solicitud.fecha_preferida == timezone.localtime(hold.starts_at).date()
        and requested_service_ids == snapshot_service_ids
        and evaluation_service_ids == snapshot_service_ids
    )


def _key_fingerprint(key):
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def _audit(
    *,
    hold,
    actor,
    event,
    previous_state,
    reason='',
    operation_key=None,
):
    return Auditoria.objects.create(
        tabla=event,
        registro_id=hold.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='ALTA' if event == SLOT_HOLD_CREATED else 'MODIFICACION',
        valor_anterior=(
            {'state': previous_state} if previous_state is not None else None
        ),
        valor_nuevo={
            'event': event,
            'hold_public_id': str(hold.public_id),
            'solicitud_id': hold.solicitud_id,
            'evaluation_id': hold.evaluacion_id,
            'cliente_id': hold.cliente_id,
            'personal_id': hold.personal_id,
            'starts_at': hold.starts_at.isoformat(),
            'ends_at': hold.ends_at.isoformat(),
            'previous_state': previous_state,
            'current_state': hold.state,
            'reason': reason,
            'actor': getattr(actor, 'pk', None) or 'SYSTEM',
            'event_at': (
                hold.expired_at or hold.released_at or hold.created_at
            ).isoformat(),
            'idempotency_key_sha256': _key_fingerprint(hold.idempotency_key),
            **(
                {'operation_key_sha256': _key_fingerprint(operation_key)}
                if operation_key
                else {}
            ),
        },
    )


def _expire_locked_hold(hold, *, now, actor=None, operation_key=None):
    previous = hold.state
    if hold.state != SlotHold.State.ACTIVE:
        return SlotHoldTransitionResult(
            hold=hold,
            changed=False,
            previous_state=previous,
            current_state=hold.state,
        )
    if hold.expires_at > now:
        raise SlotHoldConflict(
            'HOLD_NOT_EXPIRED',
            'La reserva temporal todavía está vigente.',
        )
    hold.state = SlotHold.State.EXPIRED
    hold.expired_at = now
    hold.release_reason = SlotHold.ReleaseReason.TTL_EXPIRED
    hold.save(update_fields=['state', 'expired_at', 'release_reason'])
    _audit(
        hold=hold,
        actor=actor,
        event=SLOT_HOLD_EXPIRED,
        previous_state=previous,
        reason=hold.release_reason,
        operation_key=operation_key,
    )
    return SlotHoldTransitionResult(
        hold=hold,
        changed=True,
        previous_state=previous,
        current_state=hold.state,
    )


def _same_create_payload(existing, *, solicitud_id, personal_id, starts_at):
    return (
        existing.solicitud_id == solicitud_id
        and existing.personal_id == personal_id
        and existing.starts_at == starts_at
    )


def _idempotent_existing(*, key, solicitud_id, personal_id, starts_at):
    existing = SlotHold.objects.filter(idempotency_key=key).first()
    if existing is None:
        return None
    if not _same_create_payload(
        existing,
        solicitud_id=solicitud_id,
        personal_id=personal_id,
        starts_at=starts_at,
    ):
        raise SlotHoldConflict(
            'IDEMPOTENCY_KEY_REUSED',
            'La clave de idempotencia ya fue usada con otro payload.',
        )
    return SlotHoldCreateResult(hold=existing, created=False)


@transaction.atomic
def create_slot_hold(
    *,
    solicitud_id,
    personal_id,
    starts_at,
    idempotency_key,
    actor,
):
    key = (idempotency_key or '').strip()
    if not key or len(key) > 128:
        raise SlotHoldError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
            'idempotency_key',
        )
    if timezone.is_naive(starts_at):
        raise SlotHoldError(
            'NAIVE_STARTS_AT',
            'starts_at debe incluir zona horaria.',
            'starts_at',
        )
    starts_at = starts_at.astimezone(timezone.get_current_timezone())

    try:
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=solicitud_id
        )
    except SolicitudTecnicaReserva.DoesNotExist as exc:
        raise SlotHoldNotFound() from exc

    if solicitud.cliente.usuario_id != getattr(actor, 'pk', None):
        raise SlotHoldNotFound()
    if solicitud.estado != SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE:
        raise SlotHoldConflict(
            'TECHNICAL_REQUEST_NOT_APPROVED',
            'La solicitud no está aprobada técnicamente.',
        )
    evaluation = solicitud.evaluacion_vigente
    if (
        evaluation is None
        or evaluation.superseded_by_id is not None
        or evaluation.cliente_id != solicitud.cliente_id
    ):
        raise SlotHoldConflict(
            'TECHNICAL_EVALUATION_NOT_CURRENT',
            'La evaluación técnica ya no está vigente.',
        )

    cliente = Cliente.objects.select_for_update().select_related('usuario').get(
        pk=solicitud.cliente_id
    )
    if not cliente.activo or not cliente.usuario.is_active:
        raise SlotHoldConflict(
            'INACTIVE_CLIENT',
            'El Cliente ya no está activo.',
        )

    requested_items = list(
        solicitud.servicios_solicitados.order_by('orden', 'pk').values_list(
            'servicio_id', 'orden'
        )
    )
    service_ids = sorted({service_id for service_id, _ in requested_items})
    services_by_id = {
        service.pk: service
        for service in Servicio.objects.select_for_update()
        .filter(pk__in=service_ids)
        .prefetch_related('requisitos_habilidad__habilidad')
        .order_by('pk')
    }
    if not requested_items or set(services_by_id) != set(service_ids):
        raise SlotHoldConflict(
            'INVALID_SERVICES',
            'La solicitud no conserva Servicios válidos.',
        )
    services = [services_by_id[service_id] for service_id, _ in requested_items]

    try:
        personal = Personal.objects.select_for_update().get(pk=personal_id)
    except Personal.DoesNotExist as exc:
        raise SlotHoldConflict(
            'INVALID_PERSONAL',
            'El Personal seleccionado no existe.',
            'personal_id',
        ) from exc

    requirements = {}
    for requirement in RequisitoServicio.objects.filter(
        servicio_id__in=service_ids,
        obligatorio=True,
    ).order_by('tipo_equipamiento_id', 'pk'):
        requirements[requirement.tipo_equipamiento_id] = max(
            requirements.get(requirement.tipo_equipamiento_id, 0),
            requirement.cantidad_minima,
        )
    equipment_types = list(
        TipoEquipamiento.objects.select_for_update()
        .filter(pk__in=sorted(requirements))
        .order_by('pk')
    )
    if len(equipment_types) != len(requirements):
        raise SlotHoldConflict(
            'INVALID_EQUIPMENT_REQUIREMENT',
            'La configuración de equipamiento no es válida.',
        )

    now = database_now()
    if starts_at.date() != solicitud.fecha_preferida:
        raise SlotHoldConflict(
            'SLOT_OUTSIDE_APPROVED_DATE',
            'El slot debe pertenecer a la fecha técnicamente evaluada.',
            'starts_at',
        )

    active_holds = list(
        SlotHold.objects.select_for_update().filter(
            solicitud=solicitud,
            state=SlotHold.State.ACTIVE,
        )
    )
    for active_hold in active_holds:
        if active_hold.expires_at <= now:
            _expire_locked_hold(active_hold, now=now)

    existing_result = _idempotent_existing(
        key=key,
        solicitud_id=solicitud.pk,
        personal_id=personal.pk,
        starts_at=starts_at,
    )
    if existing_result is not None:
        return existing_result

    if SlotHold.objects.filter(
        solicitud=solicitud,
        state=SlotHold.State.ACTIVE,
        expires_at__gt=now,
    ).exists():
        raise SlotHoldConflict(
            'ACTIVE_HOLD_EXISTS',
            'La solicitud ya tiene una reserva temporal vigente.',
        )

    duration_minutes = sum(
        service.duracion_estimada or 60 for service in services
    )
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    config = Configuracion.objects.first()
    ttl_minutes = (
        config.slot_hold_ttl_minutes
        if config is not None
        else DEFAULT_SLOT_HOLD_TTL_MINUTES
    )
    expires_at = min(now + timedelta(minutes=ttl_minutes), starts_at)
    if expires_at <= now:
        raise SlotHoldConflict(
            'INSUFFICIENT_HOLD_WINDOW',
            'El slot está demasiado próximo para crear una reserva temporal.',
            'starts_at',
        )

    if personal.usuario_id and not personal.usuario.is_active:
        raise SlotHoldConflict(
            'INACTIVE_PERSONAL',
            'El Personal seleccionado no está operativo.',
            'personal_id',
        )

    primary_service = services[0]
    try:
        TurnoAvailabilityService.validate_slot(
            fecha=starts_at.date(),
            hora_inicio=starts_at.time().replace(tzinfo=None),
            servicio=primary_service,
            servicios=services,
            duracion_minutos=duration_minutes,
            profesional=personal,
            cliente=cliente,
            now=now,
        )
    except TurnoCreationError as exc:
        raise SlotHoldConflict(exc.code, exc.detail, exc.field) from exc

    try:
        with transaction.atomic():
            hold = SlotHold.objects.create(
                solicitud=solicitud,
                evaluacion=evaluation,
                cliente=cliente,
                personal=personal,
                starts_at=starts_at,
                ends_at=ends_at,
                expires_at=expires_at,
                created_at=now,
                created_by=actor if getattr(actor, 'pk', None) else None,
                idempotency_key=key,
            )
            SlotHoldService.objects.bulk_create([
                SlotHoldService(
                    hold=hold,
                    servicio=service,
                    orden=order,
                    nombre_snapshot=service.nombre,
                    duracion_minutos_snapshot=service.duracion_estimada or 60,
                )
                for (service_id, order), service in zip(requested_items, services)
            ])
            SlotHoldEquipmentRequirement.objects.bulk_create([
                SlotHoldEquipmentRequirement(
                    hold=hold,
                    tipo_equipamiento=equipment_type,
                    cantidad_snapshot=requirements[equipment_type.pk],
                )
                for equipment_type in equipment_types
            ])
            _audit(
                hold=hold,
                actor=actor,
                event=SLOT_HOLD_CREATED,
                previous_state=None,
            )
    except IntegrityError:
        existing_result = _idempotent_existing(
            key=key,
            solicitud_id=solicitud.pk,
            personal_id=personal.pk,
            starts_at=starts_at,
        )
        if existing_result is not None:
            return existing_result
        raise
    return SlotHoldCreateResult(hold=hold, created=True)


@transaction.atomic
def release_slot_hold(*, public_id, actor):
    try:
        target = SlotHold.objects.only('solicitud_id').get(
            public_id=public_id,
            cliente__usuario=actor,
        )
    except SlotHold.DoesNotExist as exc:
        raise SlotHoldNotFound() from exc
    SolicitudTecnicaReserva.objects.select_for_update().get(
        pk=target.solicitud_id
    )
    try:
        hold = SlotHold.objects.select_for_update().get(
            public_id=public_id,
            cliente__usuario=actor,
        )
    except SlotHold.DoesNotExist as exc:
        raise SlotHoldNotFound() from exc

    if PaymentIntent.objects.select_for_update().filter(
        slot_hold=hold,
        status__in=PaymentIntent.ACTIVE_STATUSES,
    ).exists():
        raise SlotHoldConflict(
            'ACTIVE_PAYMENT_INTENT_EXISTS',
            'Cancele el Intent activo para liberar esta reserva temporal.',
        )

    previous = hold.state
    if hold.state == SlotHold.State.CONSUMED:
        raise SlotHoldConflict(
            'HOLD_ALREADY_CONSUMED',
            'Una reserva temporal consumida no puede liberarse.',
        )
    if hold.state in {SlotHold.State.RELEASED, SlotHold.State.EXPIRED}:
        return SlotHoldTransitionResult(
            hold=hold,
            changed=False,
            previous_state=previous,
            current_state=hold.state,
        )

    now = database_now()
    if hold.expires_at <= now:
        result = _expire_locked_hold(hold, now=now)
        return SlotHoldTransitionResult(
            hold=result.hold,
            changed=False,
            previous_state=previous,
            current_state=result.current_state,
            expiration_materialized=True,
        )

    hold.state = SlotHold.State.RELEASED
    hold.released_at = now
    hold.release_reason = SlotHold.ReleaseReason.CLIENT_CANCELLED
    hold.save(update_fields=['state', 'released_at', 'release_reason'])
    _audit(
        hold=hold,
        actor=actor,
        event=SLOT_HOLD_RELEASED,
        previous_state=previous,
        reason=hold.release_reason,
    )
    return SlotHoldTransitionResult(
        hold=hold,
        changed=True,
        previous_state=previous,
        current_state=hold.state,
    )


@transaction.atomic
def expire_slot_hold(*, hold_id, actor=None):
    try:
        hold = SlotHold.objects.select_for_update().get(pk=hold_id)
    except SlotHold.DoesNotExist as exc:
        raise SlotHoldNotFound() from exc
    return _expire_locked_hold(hold, now=database_now(), actor=actor)
