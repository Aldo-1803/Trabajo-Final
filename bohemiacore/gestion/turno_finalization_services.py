"""Finalización transaccional e idempotente de Turnos."""

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json

from django.db import IntegrityError, transaction
from usuarios.roles import BusinessPermission

from .hair_profile_services import apply_automatic_profile_impact
from .models import (
    AgendaCuidados,
    Auditoria,
    ConfiguracionRetoque,
    FinalizacionTurno,
    Notificacion,
    Promocion,
    ReglaCuidado,
    Turno,
)
from .routine_services import ensure_internal_routine_assignment


TURN_FINALIZED_EVENT = 'TURN_FINALIZED'
FINALIZATION_OPERATION = 'turno.finalize:v1'
MAX_IDEMPOTENCY_KEY_LENGTH = 128


class TurnoFinalizationError(Exception):
    def __init__(self, detail, *, code, field='non_field_errors'):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.field = field


class TurnoFinalizationInvalid(TurnoFinalizationError):
    pass


class TurnoFinalizationConflict(TurnoFinalizationError):
    pass


class TurnoFinalizationNotFound(TurnoFinalizationError):
    pass


class TurnoFinalizationPermissionDenied(TurnoFinalizationError):
    pass


@dataclass(frozen=True)
class TurnoFinalizationResult:
    finalization: FinalizacionTurno
    changed: bool


def _normalize_idempotency_key(value, *, turno_id):
    key = str(value or '').strip()
    if not key:
        # Compatibilidad con consumidores anteriores al contrato del header.
        key = f'legacy-turno-finalization:{turno_id}'
    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise TurnoFinalizationInvalid(
            'Idempotency-Key no puede superar 128 caracteres.',
            code='INVALID_IDEMPOTENCY_KEY',
            field='Idempotency-Key',
        )
    return key


def _fingerprint(*, turno_id, actor_id):
    payload = {
        'operation': FINALIZATION_OPERATION,
        'turno_id': turno_id,
        'actor_id': actor_id,
    }
    return hashlib.sha256(json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    ).encode('utf-8')).hexdigest()


def _require_finalizer(actor):
    if not getattr(actor, 'is_active', False):
        raise TurnoFinalizationPermissionDenied(
            'La cuenta debe estar activa.',
            code='INACTIVE_ACCOUNT',
        )
    if not actor.has_perm(BusinessPermission.FINALIZE_SERVICE):
        raise TurnoFinalizationPermissionDenied(
            'No tiene permisos para finalizar Servicios.',
            code='FINALIZE_SERVICE_PERMISSION_REQUIRED',
        )
    personal = getattr(actor, 'perfil_profesional', None)
    if personal is None or not personal.activo:
        raise TurnoFinalizationPermissionDenied(
            'Se requiere un perfil de Personal activo.',
            code='ACTIVE_PERSONAL_REQUIRED',
        )
    return personal


def _service_impacts(details):
    return [
        {
            'detalle_turno_id': detail.pk,
            'servicio_id': detail.servicio_id,
            'impacto_porosidad_id': detail.servicio.impacto_porosidad_id,
            'impacto_estado_id': detail.servicio.impacto_estado_id,
        }
        for detail in details
    ]


def _apply_profile_impact(turno, details, actor):
    impacts = _service_impacts(details)
    if len(details) != 1:
        return {
            'applied': False,
            'reason': (
                'NO_SERVICE'
                if not details
                else 'MULTISERVICE_POLICY_PENDING'
            ),
            'updated_fields': [],
            'service_impacts': impacts,
        }

    service = details[0].servicio
    explicit_values = {}
    if service.impacto_porosidad_id is not None:
        explicit_values['porosidad_cabello'] = service.impacto_porosidad_id
    if service.impacto_estado_id is not None:
        explicit_values['estado_general'] = service.impacto_estado_id
    synchronization = apply_automatic_profile_impact(
        actor=actor,
        cliente_id=turno.cliente_id,
        values=explicit_values,
        reason=(
            f'Impacto explícito del Servicio {service.pk} durante la '
            f'finalización del Turno {turno.pk}.'
        ),
    )
    return {
        'applied': bool(synchronization.updated_fields),
        'reason': 'SINGLE_SERVICE_EXPLICIT_IMPACT',
        'updated_fields': list(synchronization.updated_fields),
        'profile_change_id': (
            synchronization.change.pk
            if synchronization.change is not None
            else None
        ),
        'service_impacts': impacts,
    }


def _care_dates(turno, rule):
    if rule.tipo == 'RESTRICCION':
        duration = rule.dias_duracion if rule.dias_duracion > 0 else 1
        return [turno.fecha + timedelta(days=offset) for offset in range(duration)]
    if rule.tipo == 'HABITO':
        start = turno.fecha + timedelta(days=1)
        if rule.frecuencia_dias and rule.frecuencia_dias > 0:
            return [
                start + timedelta(days=offset)
                for offset in range(0, 30, rule.frecuencia_dias)
            ]
        return [start]
    return []


def _create_care_effects(turno, details):
    care_items = []
    notification_ids = []

    for detail in details:
        service = detail.servicio
        rules = list(
            ReglaCuidado.objects.filter(servicio=service)
            .select_related('rutina')
            .order_by('pk')
        )
        for rule in rules:
            for care_date in _care_dates(turno, rule):
                care_items.append(AgendaCuidados(
                    cliente=turno.cliente,
                    fecha=care_date,
                    titulo=(
                        'RESTRICCIÓN'
                        if rule.tipo == 'RESTRICCION'
                        else 'Hábito Sugerido'
                    ),
                    descripcion=(
                        f'{rule.descripcion} - Servicio: {service.nombre}'
                    ),
                ))
            notification = Notificacion.objects.create(
                usuario=turno.cliente.usuario,
                tipo='recordatorio',
                titulo=f'Cuidados post {service.nombre}',
                mensaje=(
                    f'{rule.descripcion}. '
                    f'(Válido por {rule.dias_duracion} días)'
                ),
                origen_entidad='Turno',
                origen_id=turno.pk,
            )
            notification_ids.append(notification.pk)

    if care_items:
        AgendaCuidados.objects.bulk_create(care_items)

    return {
        'care_item_ids': [item.pk for item in care_items],
        'rule_notification_ids': notification_ids,
    }


def _assign_routines(turno, details):
    from .models import Rutina

    routine_ids = {
        detail.servicio.rutina_recomendada_id
        for detail in details
        if detail.servicio.rutina_recomendada_id is not None
    }
    routine_ids.update(
        ReglaCuidado.objects.filter(
            servicio_id__in=[detail.servicio_id for detail in details],
            rutina_id__isnull=False,
        ).values_list('rutina_id', flat=True)
    )
    assignment_ids = []
    for routine in Rutina.objects.filter(pk__in=routine_ids).order_by('pk'):
        assignment, _ = ensure_internal_routine_assignment(
            cliente=turno.cliente,
            rutina=routine,
        )
        assignment_ids.append(assignment.pk)
    return assignment_ids


def _create_promotions(turno, details):
    promotion_ids = []
    for detail in details:
        configuration = (
            ConfiguracionRetoque.objects.filter(
                servicio_principal=detail.servicio
            ).order_by('pk').first()
        )
        if configuration is None:
            continue
        ideal_date = turno.fecha + timedelta(
            days=configuration.dias_sugeridos
        )
        notice_date = ideal_date - timedelta(days=7)
        promotion = Promocion.objects.create(
            nombre=f'Mantenimiento de {detail.servicio.nombre}',
            descripcion=(
                'Es el momento ideal para retocar tu '
                f'{detail.servicio.nombre} y lucir impecable.'
            ),
            tipo='RETOQUE',
            descuento_porcentaje=configuration.descuento_retoque,
            fecha_inicio=notice_date,
            fecha_fin=ideal_date + timedelta(days=7),
            fecha_envio_notificacion=notice_date,
            cliente_especifico=turno.cliente,
            is_active=True,
        )
        promotion_ids.append(promotion.pk)
    return promotion_ids


@transaction.atomic
def finalize_turno(*, actor, turno_id, idempotency_key=''):
    _require_finalizer(actor)
    key = _normalize_idempotency_key(idempotency_key, turno_id=turno_id)

    try:
        turno = (
            Turno.objects.select_for_update()
            .select_related('cliente__usuario')
            .get(pk=turno_id)
        )
    except Turno.DoesNotExist as exc:
        raise TurnoFinalizationNotFound(
            'El Turno no existe.',
            code='TURNO_NOT_FOUND',
        ) from exc

    # Revalidación posterior al lock.
    personal = _require_finalizer(actor)
    if turno.profesional_id != personal.pk:
        raise TurnoFinalizationPermissionDenied(
            'Sólo el Personal asignado puede finalizar el Turno.',
            code='TURN_ASSIGNMENT_REQUIRED',
        )

    fingerprint = _fingerprint(turno_id=turno.pk, actor_id=actor.pk)
    existing = (
        FinalizacionTurno.objects.select_for_update()
        .filter(turno=turno)
        .first()
    )
    if existing is not None:
        if (
            existing.actor_id == actor.pk
            and existing.idempotency_key == key
            and existing.command_fingerprint == fingerprint
        ):
            return TurnoFinalizationResult(existing, False)
        raise TurnoFinalizationConflict(
            'El Turno ya fue finalizado con otro comando.',
            code='TURN_ALREADY_FINALIZED',
        )

    reused_key = (
        FinalizacionTurno.objects.select_for_update()
        .filter(idempotency_key=key)
        .first()
    )
    if reused_key is not None:
        raise TurnoFinalizationConflict(
            'La clave idempotente ya fue usada para otra finalización.',
            code='IDEMPOTENCY_KEY_REUSED',
        )

    if turno.estado != Turno.Estado.CONFIRMADO:
        raise TurnoFinalizationConflict(
            'Sólo un Turno confirmado puede finalizarse.',
            code='INVALID_FINALIZATION_TRANSITION',
        )

    previous_state = turno.estado
    details = list(
        turno.detalles.select_related(
            'servicio__rutina_recomendada',
            'servicio__impacto_porosidad',
            'servicio__impacto_estado',
        ).order_by('pk')
    )

    turno.estado = Turno.Estado.REALIZADO
    turno.save(update_fields=['estado'])

    profile_effect = _apply_profile_impact(turno, details, actor)
    care_effects = _create_care_effects(turno, details)
    care_effects['routine_assignment_ids'] = _assign_routines(turno, details)
    final_notification = Notificacion.objects.create(
        usuario=turno.cliente.usuario,
        titulo='¡Servicio Finalizado!',
        mensaje='Tu servicio fue finalizado y ya puedes consultar sus cuidados.',
        tipo='informativa',
        canal='app',
        estado='pendiente',
        origen_entidad='Turno',
        origen_id=turno.pk,
    )
    promotion_ids = _create_promotions(turno, details)
    effects = {
        'automatic_diagnosis_ids': [],
        'profile': profile_effect,
        **care_effects,
        'final_notification_id': final_notification.pk,
        'promotion_ids': promotion_ids,
    }
    audit = Auditoria.objects.create(
        tabla=TURN_FINALIZED_EVENT,
        registro_id=turno.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior={'estado': previous_state},
        valor_nuevo={
            'estado': turno.estado,
            'effects': effects,
        },
    )
    effects['audit_id'] = audit.pk

    try:
        with transaction.atomic():
            finalization = FinalizacionTurno.objects.create(
                turno=turno,
                actor=actor,
                idempotency_key=key,
                command_fingerprint=fingerprint,
                estado_anterior=previous_state,
                estado_final=turno.estado,
                efectos=effects,
            )
    except IntegrityError as exc:
        raise TurnoFinalizationConflict(
            'La finalización compitió con otra operación.',
            code='TURN_FINALIZATION_CONCURRENCY_CONFLICT',
        ) from exc

    return TurnoFinalizationResult(finalization, True)
