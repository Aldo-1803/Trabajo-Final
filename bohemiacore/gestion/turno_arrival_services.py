from dataclasses import dataclass

from django.db import transaction

from usuarios.roles import BusinessPermission

from .models import Auditoria, Turno


class PermissionDeniedForTurnoArrival(Exception):
    pass


class TurnoArrivalTargetNotFound(Exception):
    pass


class InvalidTurnoArrivalTransition(Exception):
    def __init__(self, current_state):
        self.current_state = current_state
        super().__init__(f'No se puede registrar la llegada desde {current_state}.')


@dataclass(frozen=True)
class TurnoArrivalResult:
    turno: Turno
    changed: bool
    previous_state: str
    current_state: str


@transaction.atomic
def register_turno_arrival(*, actor, turno_id):
    if not actor.has_perm(BusinessPermission.REGISTER_ARRIVAL):
        raise PermissionDeniedForTurnoArrival

    try:
        turno = Turno.objects.select_for_update().get(pk=turno_id)
    except Turno.DoesNotExist:
        raise TurnoArrivalTargetNotFound

    if turno.estado == Turno.Estado.EN_PROCESO:
        return TurnoArrivalResult(
            turno=turno,
            changed=False,
            previous_state=turno.estado,
            current_state=turno.estado,
        )

    if turno.estado != Turno.Estado.CONFIRMADO:
        raise InvalidTurnoArrivalTransition(turno.estado)

    previous_state = turno.estado
    turno.estado = Turno.Estado.EN_PROCESO
    turno.save(update_fields=['estado'])

    # Evento semántico obligatorio. Si falla, transaction.atomic revierte
    # también la transición del Turno.
    Auditoria.objects.create(
        tabla='TURN_ARRIVAL_REGISTERED',
        registro_id=turno.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior={'estado': previous_state},
        valor_nuevo={'estado': turno.estado},
    )

    return TurnoArrivalResult(
        turno=turno,
        changed=True,
        previous_state=previous_state,
        current_state=turno.estado,
    )
