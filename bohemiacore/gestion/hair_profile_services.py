"""Operaciones trazables sobre evaluaciones y perfil capilar vigente."""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from usuarios.models import Cliente

from .effective_access import (
    user_can_create_diagnosis,
    user_can_manage_technical_record,
)
from .models import (
    CambioPerfilCapilar,
    CorreccionDiagnosticoCapilar,
    DiagnosticoCapilar,
    VigenciaCampoPerfilCapilar,
)


HAIR_PROFILE_FIELDS = (
    'tipo_cabello',
    'grosor_cabello',
    'porosidad_cabello',
    'cuero_cabelludo',
    'estado_general',
)
CORRECTABLE_DIAGNOSIS_FIELDS = HAIR_PROFILE_FIELDS + (
    'observaciones',
    'recomendaciones',
)


class HairProfileError(Exception):
    def __init__(self, detail, *, code, field='non_field_errors'):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.field = field


class HairProfileInvalid(HairProfileError):
    pass


class HairProfilePermissionDenied(HairProfileError):
    pass


class HairProfileNotFound(HairProfileError):
    pass


@dataclass(frozen=True)
class ProfileSynchronizationResult:
    change: CambioPerfilCapilar | None
    updated_fields: tuple[str, ...]
    synchronized_fields: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosisCorrectionResult:
    diagnosis: DiagnosticoCapilar
    correction: CorreccionDiagnosticoCapilar
    profile_change: CambioPerfilCapilar | None


def _value_id(value):
    if value is None:
        return None
    return getattr(value, 'pk', value)


def _profile_snapshot(cliente, fields):
    return {
        field: getattr(cliente, f'{field}_id')
        for field in fields
    }


def _require_active_actor(actor):
    if not (
        actor is not None
        and getattr(actor, 'is_authenticated', False)
        and getattr(actor, 'is_active', False)
        and getattr(actor, 'pk', None)
    ):
        raise HairProfilePermissionDenied(
            'La cuenta debe estar autenticada y activa.',
            code='ACTIVE_ACCOUNT_REQUIRED',
        )


def _lock_active_client(cliente_id):
    try:
        cliente = (
            Cliente.objects.select_for_update()
            .select_related('usuario')
            .get(pk=cliente_id)
        )
    except Cliente.DoesNotExist as exc:
        raise HairProfileNotFound(
            'El Cliente no existe.',
            code='CLIENT_NOT_FOUND',
            field='cliente',
        ) from exc
    if not cliente.activo or not cliente.usuario.is_active:
        raise HairProfileInvalid(
            'El Cliente debe estar activo.',
            code='CLIENT_INACTIVE',
            field='cliente',
        )
    return cliente


def _normalize_profile_values(values):
    unknown = set(values) - set(HAIR_PROFILE_FIELDS)
    if unknown:
        raise HairProfileInvalid(
            f'Campos capilares no soportados: {", ".join(sorted(unknown))}.',
            code='UNSUPPORTED_HAIR_PROFILE_FIELD',
        )
    return {
        field: _value_id(value)
        for field, value in values.items()
    }


def _apply_profile_values_locked(
    *,
    cliente,
    actor,
    values,
    procedencia,
    operation,
    reason,
    source_diagnosis=None,
):
    normalized = _normalize_profile_values(values)
    if not normalized:
        return ProfileSynchronizationResult(None, (), ())

    fields = tuple(field for field in HAIR_PROFILE_FIELDS if field in normalized)
    before = _profile_snapshot(cliente, fields)
    updated_fields = tuple(
        field for field in fields if before[field] != normalized[field]
    )
    for field in updated_fields:
        setattr(cliente, f'{field}_id', normalized[field])
    if updated_fields:
        cliente.save(update_fields=[*updated_fields, 'fecha_actualizacion'])

    change = CambioPerfilCapilar.objects.create(
        cliente=cliente,
        actor=actor,
        diagnostico_fuente=source_diagnosis,
        operacion=operation,
        procedencia=procedencia,
        motivo=reason,
        campos=list(fields),
        valores_anteriores=before,
        valores_nuevos={field: normalized[field] for field in fields},
    )

    current_states = {
        state.campo: state
        for state in VigenciaCampoPerfilCapilar.objects.select_for_update().filter(
            cliente=cliente,
            campo__in=fields,
        )
    }
    now = timezone.now()
    for field in fields:
        state = current_states.get(field)
        if state is None:
            VigenciaCampoPerfilCapilar.objects.create(
                cliente=cliente,
                campo=field,
                procedencia=procedencia,
                diagnostico_fuente=source_diagnosis,
                cambio=change,
                actor=actor,
                actualizado_en=now,
            )
            continue
        state.procedencia = procedencia
        state.diagnostico_fuente = source_diagnosis
        state.cambio = change
        state.actor = actor
        state.actualizado_en = now
        state.save(update_fields=[
            'procedencia',
            'diagnostico_fuente',
            'cambio',
            'actor',
            'actualizado_en',
        ])

    return ProfileSynchronizationResult(change, updated_fields, fields)


def _diagnosis_create_payload(data):
    allowed = set(HAIR_PROFILE_FIELDS) | {'observaciones', 'recomendaciones'}
    return {key: value for key, value in data.items() if key in allowed}


@transaction.atomic
def create_professional_evaluation(*, actor, cliente_id, data, run_engine=None):
    _require_active_actor(actor)
    if not user_can_create_diagnosis(actor):
        raise HairProfilePermissionDenied(
            'Se requiere diagnosis.create, Personal activo y DIAGNOSTICO activo.',
            code='DIAGNOSIS_CREATE_CAPABILITY_REQUIRED',
        )
    cliente = _lock_active_client(cliente_id)
    payload = _diagnosis_create_payload(data)
    evaluated = [
        field
        for field in HAIR_PROFILE_FIELDS
        if field in payload and payload[field] is not None
    ]
    diagnosis = DiagnosticoCapilar.objects.create(
        cliente=cliente,
        profesional=actor,
        autor=actor,
        procedencia=DiagnosticoCapilar.Procedencia.PROFESIONAL,
        campos_evaluados=evaluated,
        **payload,
    )
    if evaluated:
        _apply_profile_values_locked(
            cliente=cliente,
            actor=actor,
            values={field: payload[field] for field in evaluated},
            procedencia=DiagnosticoCapilar.Procedencia.PROFESIONAL,
            operation=CambioPerfilCapilar.Operacion.EVALUACION_PROFESIONAL,
            reason=f'Nueva evaluación profesional {diagnosis.pk}.',
            source_diagnosis=diagnosis,
        )
    if run_engine is not None and evaluated:
        run_engine(diagnosis)
    return diagnosis


@transaction.atomic
def record_client_self_report(*, actor, values, reason, run_engine=None):
    _require_active_actor(actor)
    cliente_id = getattr(getattr(actor, 'cliente', None), 'pk', None)
    if cliente_id is None:
        raise HairProfilePermissionDenied(
            'Se requiere un perfil de Cliente propio.',
            code='CLIENT_PROFILE_REQUIRED',
        )
    cliente = _lock_active_client(cliente_id)
    normalized = _normalize_profile_values(values)
    changed = {
        field: values[field]
        for field in normalized
        if getattr(cliente, f'{field}_id') != normalized[field]
    }
    if not changed:
        return None

    diagnosis = DiagnosticoCapilar.objects.create(
        cliente=cliente,
        profesional=None,
        autor=actor,
        procedencia=DiagnosticoCapilar.Procedencia.AUTORREPORTE,
        campos_evaluados=list(changed),
        **changed,
    )
    _apply_profile_values_locked(
        cliente=cliente,
        actor=actor,
        values=changed,
        procedencia=DiagnosticoCapilar.Procedencia.AUTORREPORTE,
        operation=CambioPerfilCapilar.Operacion.AUTORREPORTE,
        reason=reason,
        source_diagnosis=diagnosis,
    )
    if run_engine is not None:
        run_engine(diagnosis)
    return diagnosis


@transaction.atomic
def apply_automatic_profile_impact(*, actor, cliente_id, values, reason):
    _require_active_actor(actor)
    cliente = _lock_active_client(cliente_id)
    return _apply_profile_values_locked(
        cliente=cliente,
        actor=actor,
        values=values,
        procedencia=DiagnosticoCapilar.Procedencia.POST_SERVICIO_AUTOMATICO,
        operation=CambioPerfilCapilar.Operacion.DERIVACION_AUTOMATICA,
        reason=reason,
        source_diagnosis=None,
    )


def _diagnosis_field_value(diagnosis, field):
    if field in HAIR_PROFILE_FIELDS:
        return getattr(diagnosis, f'{field}_id')
    return getattr(diagnosis, field)


@transaction.atomic
def correct_diagnosis(*, actor, diagnosis_id, corrections, reason):
    _require_active_actor(actor)
    if not user_can_create_diagnosis(actor):
        raise HairProfilePermissionDenied(
            'Se requiere diagnosis.create, Personal activo y DIAGNOSTICO activo.',
            code='DIAGNOSIS_CREATE_CAPABILITY_REQUIRED',
        )
    reason = str(reason or '').strip()
    if len(reason) < 10:
        raise HairProfileInvalid(
            'El motivo debe explicar la corrección con al menos 10 caracteres.',
            code='CORRECTION_REASON_REQUIRED',
            field='motivo',
        )
    unknown = set(corrections) - set(CORRECTABLE_DIAGNOSIS_FIELDS)
    if unknown:
        raise HairProfileInvalid(
            f'Campos no corregibles: {", ".join(sorted(unknown))}.',
            code='UNSUPPORTED_CORRECTION_FIELD',
        )
    try:
        diagnosis = (
            DiagnosticoCapilar.objects.select_for_update()
            .select_related('cliente__usuario')
            .get(pk=diagnosis_id)
        )
    except DiagnosticoCapilar.DoesNotExist as exc:
        raise HairProfileNotFound(
            'La evaluación no existe.',
            code='DIAGNOSIS_NOT_FOUND',
        ) from exc

    can_manage_all = user_can_manage_technical_record(actor)
    if not can_manage_all and diagnosis.profesional_id != actor.pk:
        raise HairProfileNotFound(
            'La evaluación no existe dentro del alcance del actor.',
            code='DIAGNOSIS_NOT_FOUND',
        )

    cliente = _lock_active_client(diagnosis.cliente_id)
    before = {
        field: _diagnosis_field_value(diagnosis, field)
        for field in corrections
    }
    evaluated_fields = diagnosis.campos_evaluados
    unsupported_hair_corrections = [
        field
        for field in corrections
        if (
            field in HAIR_PROFILE_FIELDS
            and (
                (
                    evaluated_fields is not None
                    and field not in evaluated_fields
                )
                or (
                    evaluated_fields is None
                    and before[field] is None
                )
            )
        )
    ]
    if unsupported_hair_corrections:
        raise HairProfileInvalid(
            (
                'Una corrección no puede agregar campos que no formaban parte '
                'de la evaluación original.'
            ),
            code='FIELD_NOT_ORIGINALLY_EVALUATED',
            field=unsupported_hair_corrections[0],
        )
    normalized_after = {
        field: (
            _value_id(value) if field in HAIR_PROFILE_FIELDS else value
        )
        for field, value in corrections.items()
    }
    changed_fields = tuple(
        field for field in corrections if before[field] != normalized_after[field]
    )
    if not changed_fields:
        raise HairProfileInvalid(
            'La corrección no modifica información de la evaluación.',
            code='CORRECTION_WITHOUT_CHANGES',
        )

    hair_fields = tuple(
        field for field in changed_fields if field in HAIR_PROFILE_FIELDS
    )
    for field in changed_fields:
        if field in HAIR_PROFILE_FIELDS:
            setattr(diagnosis, f'{field}_id', normalized_after[field])
        else:
            setattr(diagnosis, field, normalized_after[field])

    update_fields = list(changed_fields)
    if hair_fields:
        diagnosis.regla_diagnostico = None
        diagnosis.rutina_sugerida = None
        diagnosis.rutina_asignada = None
        diagnosis.servicio_urgente = None
        diagnosis.turno_sugerido = None
        diagnosis.resultado_calculado = None
        diagnosis.estado_resultado = DiagnosticoCapilar.EstadoResultado.INVALIDADO
        diagnosis.resultado_calculado_en = None
        diagnosis.resultado_invalidado_en = timezone.now()
        diagnosis.resultado_invalidacion_motivo = reason
        update_fields.extend([
            'regla_diagnostico',
            'rutina_sugerida',
            'rutina_asignada',
            'servicio_urgente',
            'turno_sugerido',
            'resultado_calculado',
            'estado_resultado',
            'resultado_calculado_en',
            'resultado_invalidado_en',
            'resultado_invalidacion_motivo',
        ])
    diagnosis.save(update_fields=update_fields)

    profile_change = None
    if hair_fields:
        current_sources = {
            state.campo: state
            for state in VigenciaCampoPerfilCapilar.objects.select_for_update().filter(
                cliente=cliente,
                campo__in=hair_fields,
            )
        }
        profile_values = {
            field: normalized_after[field]
            for field in hair_fields
            if (
                field in current_sources
                and current_sources[field].diagnostico_fuente_id == diagnosis.pk
            )
        }
        if profile_values:
            synchronization = _apply_profile_values_locked(
                cliente=cliente,
                actor=actor,
                values=profile_values,
                procedencia=diagnosis.procedencia,
                operation=CambioPerfilCapilar.Operacion.CORRECCION,
                reason=reason,
                source_diagnosis=diagnosis,
            )
            profile_change = synchronization.change

    correction = CorreccionDiagnosticoCapilar.objects.create(
        diagnostico=diagnosis,
        actor=actor,
        motivo=reason,
        campos=list(changed_fields),
        valores_anteriores={field: before[field] for field in changed_fields},
        valores_nuevos={field: normalized_after[field] for field in changed_fields},
        cambio_perfil=profile_change,
    )
    return DiagnosisCorrectionResult(diagnosis, correction, profile_change)
