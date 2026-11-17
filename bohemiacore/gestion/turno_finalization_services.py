"""Finalización transaccional e idempotente de Turnos."""

from dataclasses import dataclass
import hashlib
import json
import uuid

from django.db import IntegrityError, transaction
from usuarios.roles import BusinessPermission

from .finalization_effect_services import (
    FinalizationEffectLedgerConflict,
    audit_effect_descriptor,
    build_effect_plan,
    effect_summary,
    execute_finalization_effects,
    record_effect_descriptor,
)
from .models import (
    Auditoria,
    DetalleTurno,
    FichaTecnica,
    FinalizacionTurno,
    Turno,
)
from .technical_record_services import (
    TechnicalRecordInvalid,
    finalization_record_status,
)


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
        DetalleTurno.objects.select_for_update(
            of=('self', 'servicio')
        ).filter(
            turno=turno
        ).select_related(
            'servicio__rutina_recomendada',
            'servicio__impacto_porosidad',
            'servicio__impacto_estado',
            'servicio__perfil_tecnico',
        ).order_by('pk')
    )
    records_by_detail = {
        record.detalle_turno_id: record
        for record in FichaTecnica.objects.select_for_update(
            of=('self',)
        ).filter(
            detalle_turno_id__in=[detail.pk for detail in details]
        ).select_related(
            'detalle_turno__servicio__perfil_tecnico'
        ).order_by('pk')
    }
    try:
        technical_record_statuses = finalization_record_status(
            details=details,
            records_by_detail=records_by_detail,
        )
    except TechnicalRecordInvalid as exc:
        raise TurnoFinalizationInvalid(
            exc.detail,
            code=exc.code,
            field=exc.field,
        ) from exc

    effect_plan = build_effect_plan(turno=turno, details=details)
    finalization_public_id = uuid.uuid4()

    turno.estado = Turno.Estado.REALIZADO
    turno.save(update_fields=['estado'])

    try:
        with transaction.atomic():
            finalization = FinalizacionTurno.objects.create(
                public_id=finalization_public_id,
                turno=turno,
                actor=actor,
                idempotency_key=key,
                command_fingerprint=fingerprint,
                estado_anterior=previous_state,
                estado_final=turno.estado,
                parametros_snapshot=effect_plan,
                efectos={},
            )
            execution = execute_finalization_effects(
                turno=turno,
                actor=actor,
                plan=effect_plan,
                finalization=finalization,
            )
            effects = {
                'technical_records': technical_record_statuses,
                **execution.legacy_effects,
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
            audit_descriptor = audit_effect_descriptor(
                audit_id=audit.pk,
                plan=effect_plan,
            )
            record_effect_descriptor(
                finalization=finalization,
                descriptor=audit_descriptor,
            )
            descriptors = (*execution.descriptors, audit_descriptor)
            effects['summary'] = effect_summary(descriptors)
            sealed = FinalizacionTurno.objects.filter(
                pk=finalization.pk,
                efectos={},
            ).update(efectos=effects)
            if sealed != 1:
                raise FinalizationEffectLedgerConflict(
                    'El resultado de finalización ya fue sellado.'
                )
            finalization.efectos = effects
    except (IntegrityError, FinalizationEffectLedgerConflict) as exc:
        raise TurnoFinalizationConflict(
            'La finalización compitió con otra operación.',
            code='TURN_FINALIZATION_CONCURRENCY_CONFLICT',
        ) from exc

    return TurnoFinalizationResult(finalization, True)
