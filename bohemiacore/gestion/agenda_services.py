from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from usuarios.roles import BusinessPermission

from .models import BloqueoAgenda, Personal, SlotHold, Turno
from .turno_creation_services import ACTIVE_TURNO_STATES


class AgendaBlockError(Exception):
    def __init__(self, code, detail, field='non_field_errors'):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.field = field


class AgendaBlockPermissionDenied(AgendaBlockError):
    pass


class AgendaBlockInvalid(AgendaBlockError):
    pass


class AgendaBlockConflict(AgendaBlockError):
    def __init__(self, code, detail, conflicts=None):
        super().__init__(code, detail)
        self.conflicts = tuple(conflicts or ())


def _aware_datetime(value):
    if timezone.is_aware(value):
        return value
    return timezone.make_aware(value, timezone.get_current_timezone())


def _turno_interval(turno):
    start = _aware_datetime(datetime.combine(turno.fecha, turno.hora_inicio))
    if turno.hora_fin_calculada is not None:
        end = _aware_datetime(
            datetime.combine(turno.fecha, turno.hora_fin_calculada)
        )
        if end <= start:
            end += timedelta(days=1)
        return start, end

    duration = sum(
        detail.duracion_minutos for detail in turno.detalles.all()
    ) or 60
    return start, start + timedelta(minutes=duration)


def _turno_conflicts(*, personal, starts_at, ends_at):
    local_start = timezone.localtime(starts_at)
    local_end = timezone.localtime(ends_at)
    turnos = (
        Turno.objects.select_for_update()
        .filter(
            profesional=personal,
            fecha__range=[local_start.date(), local_end.date()],
            estado__in=ACTIVE_TURNO_STATES,
        )
        .prefetch_related('detalles__servicio')
    )
    conflicts = []
    for turno in turnos:
        turno_start, turno_end = _turno_interval(turno)
        if turno_start < ends_at and turno_end > starts_at:
            conflicts.append({
                'turno_id': turno.pk,
                'fecha': turno.fecha.isoformat(),
                'hora_inicio': turno.hora_inicio.strftime('%H:%M'),
                'hora_fin': turno_end.strftime('%H:%M'),
            })
    return conflicts


@transaction.atomic
def create_agenda_block(
    *,
    actor,
    personal_id,
    starts_at,
    ends_at,
    reason,
    blocks_all_day=False,
):
    if not (
        getattr(actor, 'is_active', False)
        and actor.has_perm(BusinessPermission.MANAGE_CONFIGURATION)
    ):
        raise AgendaBlockPermissionDenied(
            'AGENDA_BLOCK_PERMISSION_DENIED',
            'No tiene permisos para modificar la disponibilidad.',
        )

    if ends_at <= starts_at:
        raise AgendaBlockInvalid(
            'INVALID_AGENDA_BLOCK_INTERVAL',
            'La fecha de fin debe ser posterior a la fecha de inicio.',
            'fecha_fin',
        )

    try:
        personal = Personal.objects.select_for_update().get(pk=personal_id)
    except Personal.DoesNotExist as exc:
        raise AgendaBlockInvalid(
            'PERSONAL_NOT_FOUND',
            'El Personal objetivo no existe.',
            'personal_id',
        ) from exc

    if not personal.activo or (
        personal.usuario_id is not None and not personal.usuario.is_active
    ):
        raise AgendaBlockInvalid(
            'PERSONAL_INACTIVE',
            'El Personal objetivo no está activo.',
            'personal_id',
        )

    overlapping_block = (
        BloqueoAgenda.objects.select_for_update()
        .filter(
            Q(personal=personal) | Q(personal__isnull=True),
            fecha_inicio__lt=ends_at,
            fecha_fin__gt=starts_at,
        )
        .exists()
    )
    if overlapping_block:
        raise AgendaBlockConflict(
            'AGENDA_BLOCK_CONFLICT',
            'Ya existe un bloqueo que se superpone con el intervalo solicitado.',
        )

    turno_conflicts = _turno_conflicts(
        personal=personal,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    if turno_conflicts:
        raise AgendaBlockConflict(
            'AGENDA_TURNO_CONFLICT',
            'No se puede bloquear un intervalo con Turnos activos.',
            turno_conflicts,
        )

    hold_conflict = (
        SlotHold.objects.select_for_update()
        .filter(
            personal=personal,
            state=SlotHold.State.ACTIVE,
            expires_at__gt=timezone.now(),
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )
        .exists()
    )
    if hold_conflict:
        raise AgendaBlockConflict(
            'AGENDA_HOLD_CONFLICT',
            'No se puede bloquear un intervalo reservado temporalmente.',
        )

    return BloqueoAgenda.objects.create(
        personal=personal,
        fecha_inicio=starts_at,
        fecha_fin=ends_at,
        motivo=reason,
        bloquea_todo_el_dia=blocks_all_day,
    )
