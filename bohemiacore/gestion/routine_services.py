from django.db import transaction

from .models import Rutina, RutinaCliente
from usuarios.models import Cliente


class RoutineAssignmentError(Exception):
    def __init__(self, code, detail, field='non_field_errors'):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.field = field


class RoutineAssignmentInvalid(RoutineAssignmentError):
    pass


class RoutineAssignmentConflict(RoutineAssignmentError):
    pass


@transaction.atomic
def assign_routine_copy(
    *,
    cliente_id,
    rutina_id,
    allow_unpublished=False,
    return_existing=False,
):
    """Crea la copia histórica. La autorización HTTP se valida antes."""
    try:
        cliente = (
            Cliente.objects.select_for_update()
            .select_related('usuario')
            .get(pk=cliente_id)
        )
    except Cliente.DoesNotExist as exc:
        raise RoutineAssignmentInvalid(
            'CLIENT_NOT_FOUND',
            'El Cliente objetivo no existe.',
            'cliente_id',
        ) from exc

    if not cliente.activo or not cliente.usuario.is_active:
        raise RoutineAssignmentInvalid(
            'CLIENT_INACTIVE',
            'El Cliente objetivo no está activo.',
            'cliente_id',
        )

    try:
        rutina = Rutina.objects.select_for_update().get(pk=rutina_id)
    except Rutina.DoesNotExist as exc:
        raise RoutineAssignmentInvalid(
            'ROUTINE_NOT_FOUND',
            'La Rutina no existe.',
            'rutina_id',
        ) from exc

    if not allow_unpublished and rutina.estado != 'publicada':
        raise RoutineAssignmentInvalid(
            'ROUTINE_NOT_PUBLISHED',
            'Sólo se pueden asignar Rutinas publicadas.',
            'rutina_id',
        )

    existing = RutinaCliente.objects.filter(
        cliente=cliente,
        rutina_original=rutina,
    ).first()
    if existing is not None:
        if return_existing:
            return existing, False
        raise RoutineAssignmentConflict(
            'ROUTINE_ALREADY_ASSIGNED',
            'El Cliente ya tiene una copia de esta Rutina.',
            'rutina_id',
        )

    assignment = RutinaCliente.objects.create(
        cliente=cliente,
        rutina_original=rutina,
        nombre=rutina.nombre,
        objetivo=rutina.objetivo,
        descripcion=rutina.descripcion,
        archivo=rutina.archivo,
        version_asignada=rutina.version,
        estado='activa',
    )
    return assignment, True


def ensure_internal_routine_assignment(*, cliente, rutina):
    """Entrada de dominio para CU-11; no representa autoridad de un request."""
    return assign_routine_copy(
        cliente_id=cliente.pk,
        rutina_id=rutina.pk,
        allow_unpublished=True,
        return_existing=True,
    )
