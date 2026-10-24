from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from usuarios.models import Cliente
from usuarios.roles import BusinessPermission

from .models import (
    Auditoria,
    Configuracion,
    Equipamiento,
    Personal,
    RequisitoServicio,
    Turno,
)
from .turno_creation_services import ACTIVE_TURNO_STATES, TurnoAvailabilityService


REPROGRAMMABLE_STATES = (
    Turno.Estado.SOLICITADO,
    Turno.Estado.ESPERANDO_SENA,
    Turno.Estado.CONFIRMADO,
    Turno.Estado.SUGERIDO,
    Turno.Estado.PENDIENTE,
)

CANCELLABLE_STATES = REPROGRAMMABLE_STATES

CLIENT_REPROGRAMMABLE_STATES = (
    Turno.Estado.SOLICITADO,
    Turno.Estado.ESPERANDO_SENA,
    Turno.Estado.CONFIRMADO,
)

CLIENT_CANCELLABLE_STATES = CLIENT_REPROGRAMMABLE_STATES


class PermissionDeniedForTurnoManagement(Exception):
    pass


class TurnoManagementTargetNotFound(Exception):
    pass


class InvalidTurnoManagementTransition(Exception):
    def __init__(self, operation, current_state):
        self.operation = operation
        self.current_state = current_state
        super().__init__(f'{operation} is not valid from {current_state}.')


class TurnoManagementError(Exception):
    def __init__(self, code, detail, field='non_field_errors'):
        self.code = code
        self.detail = detail
        self.field = field
        super().__init__(detail)


@dataclass(frozen=True)
class TurnoRescheduleResult:
    turno: Turno
    previous_date: object
    current_date: object
    previous_time: object
    current_time: object
    previous_professional_id: int | None
    current_professional_id: int | None
    previous_state: str
    current_state: str


@dataclass(frozen=True)
class TurnoCancellationResult:
    turno: Turno
    changed: bool
    previous_state: str
    current_state: str


def _locked_turno(turno_id):
    try:
        return (
            Turno.objects.select_for_update()
            .select_related('cliente', 'cliente__usuario')
            .prefetch_related(
                'detalles__servicio__requisitos_habilidad__habilidad'
            )
            .get(pk=turno_id)
        )
    except Turno.DoesNotExist:
        raise TurnoManagementTargetNotFound


def _locked_owned_turno(actor, turno_id):
    try:
        return (
            Turno.objects.select_for_update()
            .select_related('cliente', 'cliente__usuario')
            .prefetch_related(
                'detalles__servicio__requisitos_habilidad__habilidad'
            )
            .get(pk=turno_id, cliente__usuario=actor)
        )
    except Turno.DoesNotExist:
        raise TurnoManagementTargetNotFound


def _lock_required_equipment(services):
    type_ids = list(
        RequisitoServicio.objects.filter(
            servicio__in=services,
            obligatorio=True,
        ).values_list('tipo_equipamiento_id', flat=True)
    )
    if type_ids:
        list(
            Equipamiento.objects.select_for_update()
            .filter(tipo_id__in=type_ids)
            .values_list('pk', flat=True)
        )


def _reprogram_locked_turno(
    *,
    actor,
    turno,
    fecha,
    hora_inicio,
    profesional_id,
    reason,
    allowed_states,
    client_policy=False,
):
    if turno.estado not in allowed_states:
        raise InvalidTurnoManagementTransition('reprogram', turno.estado)

    # Serializa reservas/reprogramaciones del mismo Cliente para que la regla
    # de no duplicado siga siendo válida ante solicitudes concurrentes.
    Cliente.objects.select_for_update().get(pk=turno.cliente_id)

    details = list(turno.detalles.all())
    if not details:
        raise TurnoManagementError(
            'MISSING_TURNO_SERVICE',
            'El Turno no tiene un Servicio válido para reprogramar.',
        )
    services = [detail.servicio for detail in details]
    primary_service = services[0]

    target_professional_id = profesional_id or turno.profesional_id
    if not target_professional_id:
        raise TurnoManagementError(
            'INVALID_PERSONAL',
            'Debe seleccionar Personal para reprogramar el Turno.',
            'profesional_id',
        )
    try:
        professional = Personal.objects.select_for_update().get(
            pk=target_professional_id
        )
    except Personal.DoesNotExist:
        raise TurnoManagementError(
            'INVALID_PERSONAL',
            'El Personal seleccionado no existe.',
            'profesional_id',
        )

    if (
        turno.fecha == fecha
        and turno.hora_inicio == hora_inicio
        and turno.profesional_id == professional.pk
    ):
        raise TurnoManagementError(
            'NO_RESCHEDULE_CHANGE',
            'Debe seleccionar una fecha, hora o Personal diferente.',
        )

    if client_policy and turno.estado == Turno.Estado.CONFIRMADO:
        config = Configuracion.objects.first() or Configuracion()
        appointment_at = timezone.make_aware(
            datetime.combine(turno.fecha, turno.hora_inicio),
            timezone.get_current_timezone(),
        )
        remaining_hours = (appointment_at - timezone.now()).total_seconds() / 3600
        if remaining_hours < config.horas_limite_cancelacion:
            raise TurnoManagementError(
                'CLIENT_RESCHEDULE_WINDOW_CLOSED',
                'El Turno ya no puede reprogramarse de forma autónoma.',
            )
        if turno.cambios_realizados >= config.max_reprogramaciones:
            raise TurnoManagementError(
                'CLIENT_RESCHEDULE_LIMIT_REACHED',
                'El Turno alcanzó el límite de reprogramaciones.',
            )

    if Turno.objects.filter(
        cliente=turno.cliente,
        fecha=fecha,
        hora_inicio=hora_inicio,
        estado__in=ACTIVE_TURNO_STATES,
    ).exclude(pk=turno.pk).exists():
        raise TurnoManagementError(
            'DUPLICATE_CLIENT_SLOT',
            'El Cliente ya tiene un Turno en esa fecha y hora.',
            'hora',
        )

    _lock_required_equipment(services)
    TurnoAvailabilityService.validate_slot(
        fecha=fecha,
        hora_inicio=hora_inicio,
        servicio=primary_service,
        servicios=services,
        duracion_minutos=sum(detail.duracion_minutos for detail in details) or 60,
        profesional=professional,
        excluir_turno_id=turno.pk,
    )

    previous_date = turno.fecha
    previous_time = turno.hora_inicio
    previous_professional_id = turno.profesional_id
    previous_state = turno.estado

    turno.fecha = fecha
    turno.hora_inicio = hora_inicio
    turno.profesional = professional
    update_fields = ['fecha', 'hora_inicio', 'profesional']
    if turno.estado == Turno.Estado.CONFIRMADO:
        turno.cambios_realizados += 1
        update_fields.append('cambios_realizados')
    elif client_policy and turno.estado == Turno.Estado.ESPERANDO_SENA:
        turno.estado = Turno.Estado.SOLICITADO
        turno.fecha_limite_pago = None
        update_fields.extend(['estado', 'fecha_limite_pago'])
    turno.save(update_fields=update_fields)

    Auditoria.objects.create(
        tabla='TURN_RESCHEDULED',
        registro_id=turno.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior={
            'cliente_id': turno.cliente_id,
            'profesional_id': previous_professional_id,
            'fecha': previous_date.isoformat(),
            'hora': previous_time.strftime('%H:%M'),
            'estado': previous_state,
        },
        valor_nuevo={
            'cliente_id': turno.cliente_id,
            'profesional_id': turno.profesional_id,
            'fecha': turno.fecha.isoformat(),
            'hora': turno.hora_inicio.strftime('%H:%M'),
            'estado': turno.estado,
            'motivo': reason,
        },
    )

    return TurnoRescheduleResult(
        turno=turno,
        previous_date=previous_date,
        current_date=turno.fecha,
        previous_time=previous_time,
        current_time=turno.hora_inicio,
        previous_professional_id=previous_professional_id,
        current_professional_id=turno.profesional_id,
        previous_state=previous_state,
        current_state=turno.estado,
    )


@transaction.atomic
def reprogram_turno(
    *, actor, turno_id, fecha, hora_inicio, profesional_id=None, reason
):
    if not actor.has_perm(BusinessPermission.REPROGRAM_ANY_TURNO):
        raise PermissionDeniedForTurnoManagement
    turno = _locked_turno(turno_id)
    return _reprogram_locked_turno(
        actor=actor,
        turno=turno,
        fecha=fecha,
        hora_inicio=hora_inicio,
        profesional_id=profesional_id,
        reason=reason,
        allowed_states=REPROGRAMMABLE_STATES,
    )


@transaction.atomic
def reprogram_owned_turno(
    *, actor, turno_id, fecha, hora_inicio, profesional_id=None
):
    turno = _locked_owned_turno(actor, turno_id)
    return _reprogram_locked_turno(
        actor=actor,
        turno=turno,
        fecha=fecha,
        hora_inicio=hora_inicio,
        profesional_id=profesional_id,
        reason='Reprogramación solicitada por el Cliente.',
        allowed_states=CLIENT_REPROGRAMMABLE_STATES,
        client_policy=True,
    )


def _cancel_locked_turno(*, actor, turno, reason, allowed_states):
    if turno.estado == Turno.Estado.CANCELADO:
        return TurnoCancellationResult(
            turno=turno,
            changed=False,
            previous_state=turno.estado,
            current_state=turno.estado,
        )
    if turno.estado not in allowed_states:
        raise InvalidTurnoManagementTransition('cancel', turno.estado)

    previous_state = turno.estado
    turno.estado = Turno.Estado.CANCELADO
    turno.cancelado_por = actor
    turno.motivo_cancelacion = reason
    turno.save(update_fields=['estado', 'cancelado_por', 'motivo_cancelacion'])

    Auditoria.objects.create(
        tabla='TURN_CANCELLED',
        registro_id=turno.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior={
            'cliente_id': turno.cliente_id,
            'profesional_id': turno.profesional_id,
            'fecha': turno.fecha.isoformat(),
            'hora': turno.hora_inicio.strftime('%H:%M'),
            'estado': previous_state,
        },
        valor_nuevo={
            'cliente_id': turno.cliente_id,
            'profesional_id': turno.profesional_id,
            'fecha': turno.fecha.isoformat(),
            'hora': turno.hora_inicio.strftime('%H:%M'),
            'estado': turno.estado,
            'motivo': reason,
        },
    )

    return TurnoCancellationResult(
        turno=turno,
        changed=True,
        previous_state=previous_state,
        current_state=turno.estado,
    )


@transaction.atomic
def cancel_turno(*, actor, turno_id, reason):
    if not actor.has_perm(BusinessPermission.CANCEL_ANY_TURNO):
        raise PermissionDeniedForTurnoManagement
    turno = _locked_turno(turno_id)
    return _cancel_locked_turno(
        actor=actor,
        turno=turno,
        reason=reason,
        allowed_states=CANCELLABLE_STATES,
    )


@transaction.atomic
def cancel_owned_turno(*, actor, turno_id, reason):
    turno = _locked_owned_turno(actor, turno_id)
    if turno.estado != Turno.Estado.CANCELADO:
        config = Configuracion.objects.first() or Configuracion()
        appointment_at = timezone.make_aware(
            datetime.combine(turno.fecha, turno.hora_inicio),
            timezone.get_current_timezone(),
        )
        remaining_hours = (appointment_at - timezone.now()).total_seconds() / 3600
        if remaining_hours < config.horas_limite_cancelacion:
            raise TurnoManagementError(
                'CLIENT_CANCELLATION_WINDOW_CLOSED',
                'El Turno ya no puede cancelarse de forma autónoma.',
            )
    return _cancel_locked_turno(
        actor=actor,
        turno=turno,
        reason=reason,
        allowed_states=CLIENT_CANCELLABLE_STATES,
    )
