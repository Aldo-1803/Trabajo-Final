"""Hold y disponibilidad asistidos sobre las garantías canónicas de BH-058."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .assisted_technical_booking_services import (
    AssistedTechnicalBookingConflict,
    AssistedTechnicalBookingError,
    AssistedTechnicalBookingNotFound,
    _advisory_lock,
    _audit,
    _authorized_actor,
    _existing_operation,
    _fingerprint,
    _normalized_key,
    _normalized_operation_id,
    _sha256,
    assisted_request_for_actor,
)
from .models import (
    Configuracion,
    SlotHold,
    SolicitudTecnicaAsistidaOperacion,
    SolicitudTecnicaReserva,
)
from .service_skill_compatibility import service_skill_policy
from .slot_hold_clock import database_now, effective_hold_state
from .slot_hold_services import (
    DEFAULT_SLOT_HOLD_TTL_MINUTES,
    SlotHoldConflict,
    SlotHoldError,
    SlotHoldNotFound,
    _create_slot_hold,
    _release_slot_hold,
)
from .turno_creation_services import TurnoAvailabilityService


ASSISTED_SLOT_HOLD_CREATED = 'ASSISTED_SLOT_HOLD_CREATED'
ASSISTED_SLOT_HOLD_RELEASED = 'ASSISTED_SLOT_HOLD_RELEASED'
NO_AVAILABILITY_FOUND = 'NO_AVAILABILITY_FOUND'


@dataclass(frozen=True)
class AssistedSlotHoldResult:
    hold: SlotHold
    operation_id: str
    recovered: bool


@dataclass(frozen=True)
class AssistedSlotHoldReleaseResult:
    hold: SlotHold
    operation_id: str
    recovered: bool
    changed: bool
    expiration_materialized: bool


def _assisted_internal_key(command, key_digest):
    return f'assisted-{command.lower()}:{key_digest}'


def _lock_operation_identity(command, key_digest, operation_id):
    for lock_value in sorted((
        f'assisted-key:{command}:{key_digest}',
        f'assisted-operation:{operation_id}',
    )):
        _advisory_lock(lock_value)


def _approved_request_components(solicitud):
    evaluation = solicitud.evaluacion_vigente
    if solicitud.estado != SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE:
        raise AssistedTechnicalBookingConflict(
            'TECHNICAL_REQUEST_NOT_APPROVED',
            'La solicitud no está aprobada técnicamente.',
        )
    if (
        evaluation is None
        or evaluation.superseded_by_id is not None
        or evaluation.cliente_id != solicitud.cliente_id
        or evaluation.fecha_solicitada != solicitud.fecha_preferida
    ):
        raise AssistedTechnicalBookingConflict(
            'TECHNICAL_EVALUATION_NOT_CURRENT',
            'La evaluación técnica ya no está vigente.',
        )
    cliente = solicitud.cliente
    if not cliente.activo or not cliente.usuario.is_active:
        raise AssistedTechnicalBookingConflict(
            'INACTIVE_CLIENT',
            'El Cliente ya no está activo.',
        )
    requested = tuple(
        item.servicio
        for item in solicitud.servicios_solicitados.all()
    )
    requested_ids = tuple(service.pk for service in requested)
    evaluation_ids = tuple(
        item.get('id')
        for item in evaluation.input_snapshot.get('servicios', [])
        if isinstance(item, dict) and item.get('id') is not None
    )
    if (
        not requested
        or any(not service.activo for service in requested)
        or requested_ids != evaluation_ids
    ):
        raise AssistedTechnicalBookingConflict(
            'INVALID_SERVICES',
            'La solicitud no conserva Servicios activos y evaluados.',
        )
    return requested


def _availability_projection(solicitud, *, now):
    services = _approved_request_components(solicitud)
    primary_service = services[0]
    duration_minutes = sum(service.duracion_estimada or 60 for service in services)
    config = Configuracion.objects.first()
    interval_minutes = config.intervalo_turnos if config is not None else 30
    if interval_minutes <= 0:
        raise AssistedTechnicalBookingConflict(
            'INVALID_AVAILABILITY_CONFIGURATION',
            'La configuración de intervalos no es válida.',
        )
    ttl_minutes = (
        config.slot_hold_ttl_minutes
        if config is not None
        else DEFAULT_SLOT_HOLD_TTL_MINUTES
    )
    policy = service_skill_policy(services)
    schedules = TurnoAvailabilityService.matching_schedules(
        fecha=solicitud.fecha_preferida,
        servicio=primary_service,
        servicios=services,
        skill_policy=policy,
    ).order_by('hora_inicio', 'personal_id', 'pk')
    by_personal = {}
    seen_slots = set()
    current_timezone = timezone.get_current_timezone()
    for schedule in schedules:
        slots = TurnoAvailabilityService.available_slots_for_schedule(
            fecha=solicitud.fecha_preferida,
            schedule=schedule,
            servicio=primary_service,
            intervalo_minutos=interval_minutes,
            duracion_minutos=duration_minutes,
            servicios=services,
            skill_policy=policy,
            cliente=solicitud.cliente,
            now=now,
        )
        if not slots:
            continue
        personal_entry = by_personal.setdefault(schedule.personal_id, {
            'id': schedule.personal_id,
            'display_name': (
                f'{schedule.personal.nombre} {schedule.personal.apellido}'.strip()
            ),
            'slots': [],
        })
        for slot in slots:
            starts_at = timezone.make_aware(
                datetime.combine(
                    solicitud.fecha_preferida,
                    datetime.strptime(slot['hora'], '%H:%M').time(),
                ),
                current_timezone,
            )
            identity = (schedule.personal_id, starts_at)
            if identity in seen_slots:
                continue
            seen_slots.add(identity)
            personal_entry['slots'].append({
                'starts_at': starts_at.isoformat(),
                'ends_at': (
                    starts_at + timedelta(minutes=duration_minutes)
                ).isoformat(),
            })
    professionals = sorted(
        by_personal.values(),
        key=lambda item: (item['display_name'].casefold(), item['id']),
    )
    for professional in professionals:
        professional['slots'].sort(key=lambda item: item['starts_at'])
    return {
        'solicitud_id': solicitud.pk,
        'fecha': solicitud.fecha_preferida.isoformat(),
        'duration_minutes': duration_minutes,
        'interval_minutes': interval_minutes,
        'hold_ttl_minutes': ttl_minutes,
        'server_now': now.isoformat(),
        'authoritative': False,
        'profesionales': professionals,
    }


@transaction.atomic
def assisted_slot_availability(*, solicitud_id, actor):
    current_actor = _authorized_actor(actor)
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current_actor,
    )
    return _availability_projection(solicitud, now=database_now())


@transaction.atomic
def next_assisted_available_slot(*, solicitud_id, actor, personal_id=None):
    current_actor = _authorized_actor(actor)
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current_actor,
    )
    projection = _availability_projection(solicitud, now=database_now())
    candidates = [
        {
            'personal': {
                'id': professional['id'],
                'display_name': professional['display_name'],
            },
            **slot,
        }
        for professional in projection['profesionales']
        if personal_id is None or professional['id'] == personal_id
        for slot in professional['slots']
    ]
    if not candidates:
        raise AssistedTechnicalBookingConflict(
            NO_AVAILABILITY_FOUND,
            'No se encontró un intervalo futuro disponible.',
        )
    candidate = min(
        candidates,
        key=lambda item: (item['starts_at'], item['personal']['id']),
    )
    return {
        'solicitud_id': solicitud.pk,
        'fecha': projection['fecha'],
        'server_now': projection['server_now'],
        'authoritative': False,
        'slot': candidate,
    }


def _translate_hold_error(exc):
    if isinstance(exc, SlotHoldNotFound):
        return AssistedTechnicalBookingNotFound(
            'HOLD_OR_REQUEST_OUT_OF_SCOPE',
            'El hold o la solicitud no están disponibles en este alcance.',
        )
    if isinstance(exc, SlotHoldConflict):
        return AssistedTechnicalBookingConflict(exc.code, exc.detail, exc.field)
    return AssistedTechnicalBookingError(exc.code, exc.detail, exc.field)


@transaction.atomic
def create_assisted_slot_hold(
    *,
    solicitud_id,
    actor,
    idempotency_key,
    operation_id,
    personal_id,
    starts_at,
):
    key = _normalized_key(idempotency_key)
    normalized_operation_id = _normalized_operation_id(operation_id)
    if timezone.is_naive(starts_at):
        raise AssistedTechnicalBookingError(
            'NAIVE_STARTS_AT',
            'starts_at debe incluir zona horaria.',
            'starts_at',
        )
    normalized_start = starts_at.astimezone(timezone.get_current_timezone())
    key_digest = _sha256(key)
    fingerprint = _fingerprint({
        'actor_id': getattr(actor, 'pk', None),
        'operation_id': str(normalized_operation_id),
        'solicitud_id': solicitud_id,
        'personal_id': personal_id,
        'starts_at': normalized_start.isoformat(),
    })
    command = SolicitudTecnicaAsistidaOperacion.Command.HOLD
    _lock_operation_identity(command, key_digest, normalized_operation_id)
    current_actor = _authorized_actor(actor)
    existing = _existing_operation(
        command=command,
        key_digest=key_digest,
        operation_id=normalized_operation_id,
        actor=current_actor,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return AssistedSlotHoldResult(
            hold=existing.hold,
            operation_id=str(existing.operation_id),
            recovered=True,
        )
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current_actor,
        lock=True,
    )
    _approved_request_components(solicitud)
    internal_key = _assisted_internal_key(command, key_digest)
    try:
        result = _create_slot_hold(
            solicitud_id=solicitud.pk,
            personal_id=personal_id,
            starts_at=normalized_start,
            idempotency_key=internal_key,
            actor=current_actor,
            scope_checker=lambda request, request_actor: (
                request.pk == solicitud.pk
                and request.operador_registrante_id
                == getattr(request_actor, 'pk', None)
                and request.medio_solicitud in {
                    SolicitudTecnicaReserva.MedioSolicitud.TELEFONO,
                    SolicitudTecnicaReserva.MedioSolicitud.PRESENCIAL,
                }
            ),
        )
    except SlotHoldError as exc:
        raise _translate_hold_error(exc) from exc
    operation = SolicitudTecnicaAsistidaOperacion.objects.create(
        operation_id=normalized_operation_id,
        actor=current_actor,
        command=command,
        idempotency_key_digest=key_digest,
        fingerprint=fingerprint,
        solicitud=solicitud,
        hold=result.hold,
    )
    _audit(
        operation=operation,
        event=ASSISTED_SLOT_HOLD_CREATED,
        extra={
            'hold_public_id': str(result.hold.public_id),
            'evaluation_id': result.hold.evaluacion_id,
            'personal_id': result.hold.personal_id,
            'starts_at': result.hold.starts_at.isoformat(),
            'ends_at': result.hold.ends_at.isoformat(),
            'expires_at': result.hold.expires_at.isoformat(),
        },
    )
    return AssistedSlotHoldResult(
        hold=result.hold,
        operation_id=str(operation.operation_id),
        recovered=False,
    )


@transaction.atomic
def assisted_slot_hold_for_actor(*, solicitud_id, actor, public_id=None):
    current_actor = _authorized_actor(actor)
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current_actor,
    )
    operations = (
        SolicitudTecnicaAsistidaOperacion.objects.select_related(
            'hold__personal'
        )
        .filter(
            solicitud=solicitud,
            actor=current_actor,
            command=SolicitudTecnicaAsistidaOperacion.Command.HOLD,
            hold__isnull=False,
        )
        .order_by('-created_at', '-pk')
    )
    if public_id is not None:
        operations = operations.filter(hold__public_id=public_id)
    operation = operations.first()
    if operation is None:
        raise AssistedTechnicalBookingNotFound(
            'ASSISTED_HOLD_NOT_FOUND',
            'El hold asistido no está disponible en este alcance.',
        )
    return operation.hold


@transaction.atomic
def release_assisted_slot_hold(
    *,
    solicitud_id,
    public_id,
    actor,
    idempotency_key,
    operation_id,
):
    key = _normalized_key(idempotency_key)
    normalized_operation_id = _normalized_operation_id(operation_id)
    key_digest = _sha256(key)
    fingerprint = _fingerprint({
        'actor_id': getattr(actor, 'pk', None),
        'operation_id': str(normalized_operation_id),
        'solicitud_id': solicitud_id,
        'hold_public_id': str(public_id),
    })
    command = SolicitudTecnicaAsistidaOperacion.Command.RELEASE
    _lock_operation_identity(command, key_digest, normalized_operation_id)
    current_actor = _authorized_actor(actor)
    existing = _existing_operation(
        command=command,
        key_digest=key_digest,
        operation_id=normalized_operation_id,
        actor=current_actor,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return AssistedSlotHoldReleaseResult(
            hold=existing.hold,
            operation_id=str(existing.operation_id),
            recovered=True,
            changed=False,
            expiration_materialized=False,
        )
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current_actor,
        lock=True,
    )
    hold = assisted_slot_hold_for_actor(
        solicitud_id=solicitud.pk,
        actor=current_actor,
        public_id=public_id,
    )
    internal_key = _assisted_internal_key(command, key_digest)
    try:
        result = _release_slot_hold(
            public_id=hold.public_id,
            actor=current_actor,
            scope_checker=lambda target, release_actor: (
                target.pk == hold.pk
                and target.solicitud_id == solicitud.pk
                and target.created_by_id == getattr(release_actor, 'pk', None)
            ),
            release_reason=SlotHold.ReleaseReason.OPERATOR_CANCELLED,
            operation_key=internal_key,
        )
    except SlotHoldError as exc:
        raise _translate_hold_error(exc) from exc
    operation = SolicitudTecnicaAsistidaOperacion.objects.create(
        operation_id=normalized_operation_id,
        actor=current_actor,
        command=command,
        idempotency_key_digest=key_digest,
        fingerprint=fingerprint,
        solicitud=solicitud,
        hold=result.hold,
    )
    _audit(
        operation=operation,
        event=ASSISTED_SLOT_HOLD_RELEASED,
        extra={
            'hold_public_id': str(result.hold.public_id),
            'previous_state': result.previous_state,
            'current_state': result.current_state,
            'changed': result.changed,
            'expiration_materialized': result.expiration_materialized,
            'release_reason': result.hold.release_reason,
        },
    )
    return AssistedSlotHoldReleaseResult(
        hold=result.hold,
        operation_id=str(operation.operation_id),
        recovered=False,
        changed=result.changed,
        expiration_materialized=result.expiration_materialized,
    )


def assisted_hold_next_action(hold, *, now):
    state = effective_hold_state(hold, at=now)
    if state == SlotHold.State.ACTIVE:
        return {
            'code': 'HOLD_ACTIVE_PENDING_PAYMENT',
            'detail': (
                'La capacidad está retenida temporalmente; pago y confirmación '
                'todavía no están disponibles.'
            ),
            'can_confirm_turno': False,
        }
    if state in {SlotHold.State.EXPIRED, SlotHold.State.RELEASED}:
        return {
            'code': 'SELECT_NEW_SLOT',
            'detail': 'Debe seleccionar y retener un nuevo intervalo.',
            'can_confirm_turno': False,
        }
    return {
        'code': 'HOLD_ALREADY_CONSUMED',
        'detail': 'El hold ya fue consumido por un flujo posterior.',
        'can_confirm_turno': False,
    }
