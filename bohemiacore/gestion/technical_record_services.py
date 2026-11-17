"""Ciclo trazable y concurrente de fichas técnicas por DetalleTurno."""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .effective_access import (
    user_can_manage_service_formula,
    user_can_manage_technical_record,
    user_can_read_global_technical_record,
)
from .models import (
    CorreccionFichaTecnica,
    DetalleTurno,
    FichaTecnica,
    PerfilTecnicoServicio,
    Turno,
)


TECHNICAL_RECORD_FIELDS = (
    'formula',
    'observaciones_proceso',
    'comentario_cliente',
    'rutina_recomendada',
    'porosidad_final',
    'estado_general_final',
    'resultado_post_servicio',
    'foto_resultado',
)
CONFIGURABLE_REQUIRED_FIELDS = (
    'observaciones_proceso',
    'comentario_cliente',
    'rutina_recomendada',
    'porosidad_final',
    'estado_general_final',
    'resultado_post_servicio',
    'foto_resultado',
)
MUTABLE_TURNO_STATES = (
    Turno.Estado.CONFIRMADO,
    Turno.Estado.EN_PROCESO,
)


class TechnicalRecordError(Exception):
    def __init__(self, detail, *, code, field='non_field_errors'):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.field = field


class TechnicalRecordInvalid(TechnicalRecordError):
    pass


class TechnicalRecordConflict(TechnicalRecordError):
    pass


class TechnicalRecordNotFound(TechnicalRecordError):
    pass


class TechnicalRecordPermissionDenied(TechnicalRecordError):
    pass


@dataclass(frozen=True)
class TechnicalRecordPolicy:
    status: str
    record_requirement: str | None
    formula_mode: str | None
    required_fields: tuple[str, ...]
    reason: str | None = None

    @property
    def defined(self):
        return self.status == 'DEFINIDA'

    @property
    def record_required(self):
        return (
            self.defined
            and self.record_requirement
            == PerfilTecnicoServicio.RequisitoFicha.REQUERIDA
        )


@dataclass(frozen=True)
class TechnicalRecordMutationResult:
    record: FichaTecnica
    correction: CorreccionFichaTecnica | None = None


def _service_policy(service):
    try:
        profile = service.perfil_tecnico
    except PerfilTecnicoServicio.DoesNotExist:
        return TechnicalRecordPolicy(
            status='PENDIENTE',
            record_requirement=None,
            formula_mode=None,
            required_fields=(),
            reason='SERVICE_TECHNICAL_PROFILE_MISSING',
        )

    requirement = profile.requisito_ficha
    formula_mode = profile.modo_formula_ficha
    configured_fields = profile.campos_requeridos_ficha
    if not profile.activa:
        return TechnicalRecordPolicy(
            status='PENDIENTE',
            record_requirement=requirement,
            formula_mode=formula_mode,
            required_fields=(),
            reason='SERVICE_TECHNICAL_PROFILE_INACTIVE',
        )
    if not isinstance(configured_fields, list):
        return TechnicalRecordPolicy(
            status='PENDIENTE',
            record_requirement=requirement,
            formula_mode=formula_mode,
            required_fields=(),
            reason='INVALID_REQUIRED_FIELDS_CONFIGURATION',
        )
    fields = tuple(dict.fromkeys(configured_fields))
    if any(field not in CONFIGURABLE_REQUIRED_FIELDS for field in fields):
        return TechnicalRecordPolicy(
            status='PENDIENTE',
            record_requirement=requirement,
            formula_mode=formula_mode,
            required_fields=(),
            reason='INVALID_REQUIRED_FIELDS_CONFIGURATION',
        )
    if (
        requirement == PerfilTecnicoServicio.RequisitoFicha.PENDIENTE
        or formula_mode == PerfilTecnicoServicio.ModoFormulaFicha.PENDIENTE
    ):
        return TechnicalRecordPolicy(
            status='PENDIENTE',
            record_requirement=requirement,
            formula_mode=formula_mode,
            required_fields=fields,
            reason='SERVICE_TECHNICAL_RECORD_POLICY_PENDING',
        )
    if (
        requirement == PerfilTecnicoServicio.RequisitoFicha.NO_REQUERIDA
        and fields
    ):
        return TechnicalRecordPolicy(
            status='PENDIENTE',
            record_requirement=requirement,
            formula_mode=formula_mode,
            required_fields=fields,
            reason='NON_REQUIRED_RECORD_HAS_REQUIRED_FIELDS',
        )
    if (
        requirement == PerfilTecnicoServicio.RequisitoFicha.REQUERIDA
        and not fields
        and formula_mode != PerfilTecnicoServicio.ModoFormulaFicha.REQUERIDA
    ):
        return TechnicalRecordPolicy(
            status='PENDIENTE',
            record_requirement=requirement,
            formula_mode=formula_mode,
            required_fields=(),
            reason='REQUIRED_RECORD_WITHOUT_COMPLETION_FIELDS',
        )
    if formula_mode == PerfilTecnicoServicio.ModoFormulaFicha.REQUERIDA:
        fields = ('formula', *fields)
    return TechnicalRecordPolicy(
        status='DEFINIDA',
        record_requirement=requirement,
        formula_mode=formula_mode,
        required_fields=fields,
    )


def technical_record_policy(service):
    """Contrato público de política; no infiere por nombre ni categoría."""
    return _service_policy(service)


def validate_required_fields_configuration(*, requirement, formula_mode, fields):
    if not isinstance(fields, list):
        raise TechnicalRecordInvalid(
            'campos_requeridos_ficha debe ser una lista.',
            code='INVALID_REQUIRED_FIELDS_CONFIGURATION',
            field='campos_requeridos_ficha',
        )
    duplicates = len(fields) != len(set(fields))
    invalid = [
        field for field in fields if field not in CONFIGURABLE_REQUIRED_FIELDS
    ]
    if duplicates or invalid:
        raise TechnicalRecordInvalid(
            'La lista contiene campos repetidos o no soportados.',
            code='INVALID_REQUIRED_FIELDS_CONFIGURATION',
            field='campos_requeridos_ficha',
        )
    if requirement == PerfilTecnicoServicio.RequisitoFicha.PENDIENTE:
        if fields or formula_mode != PerfilTecnicoServicio.ModoFormulaFicha.PENDIENTE:
            raise TechnicalRecordInvalid(
                'Una política pendiente no puede declarar requisitos parciales.',
                code='PARTIAL_TECHNICAL_RECORD_POLICY',
                field='requisito_ficha',
            )
    elif formula_mode == PerfilTecnicoServicio.ModoFormulaFicha.PENDIENTE:
        raise TechnicalRecordInvalid(
            'Debe definir expresamente si la fórmula aplica.',
            code='FORMULA_POLICY_REQUIRED',
            field='modo_formula_ficha',
        )
    if (
        requirement == PerfilTecnicoServicio.RequisitoFicha.NO_REQUERIDA
        and fields
    ):
        raise TechnicalRecordInvalid(
            'Un Servicio sin ficha requerida no puede exigir campos de ficha.',
            code='NON_REQUIRED_RECORD_HAS_REQUIRED_FIELDS',
            field='campos_requeridos_ficha',
        )
    if (
        requirement == PerfilTecnicoServicio.RequisitoFicha.REQUERIDA
        and not fields
        and formula_mode != PerfilTecnicoServicio.ModoFormulaFicha.REQUERIDA
    ):
        raise TechnicalRecordInvalid(
            'Una ficha requerida debe declarar al menos un campo verificable.',
            code='REQUIRED_RECORD_WITHOUT_COMPLETION_FIELDS',
            field='campos_requeridos_ficha',
        )


def _require_active_record_manager(actor):
    if not user_can_manage_technical_record(actor):
        raise TechnicalRecordPermissionDenied(
            'Se requiere technical_record.manage, Personal y DIAGNOSTICO activos.',
            code='TECHNICAL_RECORD_MANAGE_REQUIRED',
        )
    return actor.perfil_profesional


def _detail_reference(detail_id):
    try:
        return DetalleTurno.objects.only('pk', 'turno_id').get(pk=detail_id)
    except DetalleTurno.DoesNotExist as exc:
        raise TechnicalRecordNotFound(
            'El Detalle de Turno no existe.',
            code='TURN_DETAIL_NOT_FOUND',
            field='detalle_turno',
        ) from exc


def _lock_owned_detail(*, actor, detail_id):
    personal = _require_active_record_manager(actor)
    reference = _detail_reference(detail_id)
    try:
        turno = Turno.objects.select_for_update().get(pk=reference.turno_id)
        detail = (
            DetalleTurno.objects.select_for_update(of=('self',))
            .select_related('servicio__perfil_tecnico', 'turno')
            .get(pk=reference.pk, turno=turno)
        )
    except (Turno.DoesNotExist, DetalleTurno.DoesNotExist) as exc:
        raise TechnicalRecordNotFound(
            'El Detalle de Turno no existe.',
            code='TURN_DETAIL_NOT_FOUND',
            field='detalle_turno',
        ) from exc
    if turno.profesional_id != personal.pk:
        raise TechnicalRecordPermissionDenied(
            'Sólo el Personal asignado al Turno puede gestionar su ficha.',
            code='TURN_ASSIGNMENT_REQUIRED',
        )
    if turno.estado not in MUTABLE_TURNO_STATES:
        code = (
            'FINALIZED_RECORD_CORRECTION_POLICY_PENDING'
            if turno.estado == Turno.Estado.REALIZADO
            else 'TURN_STATE_DOES_NOT_ALLOW_TECHNICAL_RECORD'
        )
        raise TechnicalRecordConflict(
            'El estado del Turno no permite modificar su ficha técnica.',
            code=code,
        )
    return detail


def _record_reference(record_id):
    try:
        return FichaTecnica.objects.only(
            'pk', 'detalle_turno_id'
        ).get(pk=record_id)
    except FichaTecnica.DoesNotExist as exc:
        raise TechnicalRecordNotFound(
            'La ficha técnica no existe.',
            code='TECHNICAL_RECORD_NOT_FOUND',
        ) from exc


def _lock_owned_record(*, actor, record_id):
    reference = _record_reference(record_id)
    detail = _lock_owned_detail(
        actor=actor,
        detail_id=reference.detalle_turno_id,
    )
    try:
        record = (
            FichaTecnica.objects.select_for_update(of=('self',))
            .select_related('detalle_turno__servicio__perfil_tecnico')
            .get(pk=reference.pk, detalle_turno=detail)
        )
    except FichaTecnica.DoesNotExist as exc:
        raise TechnicalRecordNotFound(
            'La ficha técnica no existe.',
            code='TECHNICAL_RECORD_NOT_FOUND',
        ) from exc
    return record


def _json_value(value):
    if value is None:
        return None
    if hasattr(value, 'pk'):
        return value.pk
    if hasattr(value, 'name'):
        return value.name or None
    return value


def _field_value(record, field):
    if field in {
        'rutina_recomendada',
        'porosidad_final',
        'estado_general_final',
    }:
        return getattr(record, f'{field}_id')
    if field == 'foto_resultado':
        return record.foto_resultado.name or None
    return getattr(record, field)


def _has_value(record, field):
    value = _field_value(record, field)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _completion_errors(record, policy):
    if not policy.defined:
        return [policy.reason or 'SERVICE_TECHNICAL_RECORD_POLICY_PENDING']
    errors = [
        f'MISSING_{field.upper()}'
        for field in policy.required_fields
        if not _has_value(record, field)
    ]
    if (
        policy.formula_mode
        == PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA
        and _has_value(record, 'formula')
    ):
        errors.append('FORMULA_NOT_APPLICABLE')
    if not any(_has_value(record, field) for field in TECHNICAL_RECORD_FIELDS):
        errors.append('EMPTY_TECHNICAL_RECORD')
    return errors


def technical_record_completion(record):
    policy = _service_policy(record.detalle_turno.servicio)
    errors = _completion_errors(record, policy)
    return policy, errors


def _validate_formula_mutation(*, actor, policy, values):
    if 'formula' not in values:
        return
    if not user_can_manage_service_formula(actor):
        raise TechnicalRecordPermissionDenied(
            'Se requiere service_formula.manage para modificar la fórmula aplicada.',
            code='SERVICE_FORMULA_MANAGE_REQUIRED',
            field='formula',
        )
    formula = str(values.get('formula') or '').strip()
    if (
        formula
        and policy.defined
        and policy.formula_mode
        == PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA
    ):
        raise TechnicalRecordInvalid(
            'La política explícita del Servicio indica que la fórmula no aplica.',
            code='FORMULA_NOT_APPLICABLE',
            field='formula',
        )


def _apply_values(record, values):
    changed = []
    before = {}
    for field in TECHNICAL_RECORD_FIELDS:
        if field not in values:
            continue
        previous = _field_value(record, field)
        incoming = _json_value(values[field])
        if previous == incoming:
            continue
        before[field] = previous
        setattr(record, field, values[field])
        changed.append(field)
    return tuple(changed), before


def _assert_version(record, expected_version):
    if record.version != expected_version:
        raise TechnicalRecordConflict(
            'La ficha fue modificada por otra operación.',
            code='TECHNICAL_RECORD_VERSION_CONFLICT',
            field='version',
        )


@transaction.atomic
def create_draft(*, actor, detail_id, values):
    detail = _lock_owned_detail(actor=actor, detail_id=detail_id)
    if FichaTecnica.objects.select_for_update().filter(
        detalle_turno=detail
    ).exists():
        raise TechnicalRecordConflict(
            'El Detalle de Turno ya tiene una ficha técnica.',
            code='TECHNICAL_RECORD_ALREADY_EXISTS',
        )
    policy = _service_policy(detail.servicio)
    _validate_formula_mutation(actor=actor, policy=policy, values=values)
    standard_snapshot = None
    if policy.formula_mode in {
        PerfilTecnicoServicio.ModoFormulaFicha.OPCIONAL,
        PerfilTecnicoServicio.ModoFormulaFicha.REQUERIDA,
    }:
        standard_snapshot = detail.servicio.plantilla_formula.strip() or None
    return FichaTecnica.objects.create(
        detalle_turno=detail,
        profesional_autor=actor,
        formula_estandar_referencia=standard_snapshot,
        estado=FichaTecnica.Estado.BORRADOR,
        version=1,
        **values,
    )


@transaction.atomic
def save_draft(*, actor, record_id, expected_version, values):
    record = _lock_owned_record(actor=actor, record_id=record_id)
    _assert_version(record, expected_version)
    if record.estado != FichaTecnica.Estado.BORRADOR:
        raise TechnicalRecordConflict(
            'Una ficha completa sólo admite correcciones trazables.',
            code='TECHNICAL_RECORD_ALREADY_COMPLETE',
        )
    policy = _service_policy(record.detalle_turno.servicio)
    _validate_formula_mutation(actor=actor, policy=policy, values=values)
    changed, _ = _apply_values(record, values)
    if not changed:
        raise TechnicalRecordInvalid(
            'El guardado no modifica la ficha.',
            code='TECHNICAL_RECORD_WITHOUT_CHANGES',
        )
    record.version += 1
    record.save(update_fields=[*changed, 'version', 'actualizada_en'])
    return TechnicalRecordMutationResult(record)


@transaction.atomic
def complete_record(*, actor, record_id, expected_version, values):
    record = _lock_owned_record(actor=actor, record_id=record_id)
    _assert_version(record, expected_version)
    if record.estado != FichaTecnica.Estado.BORRADOR:
        raise TechnicalRecordConflict(
            'La ficha ya está completa.',
            code='TECHNICAL_RECORD_ALREADY_COMPLETE',
        )
    policy = _service_policy(record.detalle_turno.servicio)
    _validate_formula_mutation(actor=actor, policy=policy, values=values)
    changed, _ = _apply_values(record, values)
    errors = _completion_errors(record, policy)
    if errors:
        raise TechnicalRecordInvalid(
            'La ficha no cumple la política explícita del Servicio.',
            code='TECHNICAL_RECORD_INCOMPLETE',
            field=errors[0],
        )
    record.estado = FichaTecnica.Estado.COMPLETA
    record.completada_por = actor
    record.completada_en = timezone.now()
    record.version += 1
    record.save(update_fields=[
        *changed,
        'estado',
        'completada_por',
        'completada_en',
        'version',
        'actualizada_en',
    ])
    return TechnicalRecordMutationResult(record)


@transaction.atomic
def correct_record(*, actor, record_id, expected_version, reason, values):
    reason = str(reason or '').strip()
    if len(reason) < 10:
        raise TechnicalRecordInvalid(
            'La corrección requiere un motivo de al menos 10 caracteres.',
            code='TECHNICAL_RECORD_CORRECTION_REASON_REQUIRED',
            field='motivo',
        )
    record = _lock_owned_record(actor=actor, record_id=record_id)
    _assert_version(record, expected_version)
    if record.estado != FichaTecnica.Estado.COMPLETA:
        raise TechnicalRecordConflict(
            'Sólo una ficha completa admite correcciones.',
            code='TECHNICAL_RECORD_NOT_COMPLETE',
        )
    policy = _service_policy(record.detalle_turno.servicio)
    _validate_formula_mutation(actor=actor, policy=policy, values=values)
    changed, before = _apply_values(record, values)
    if not changed:
        raise TechnicalRecordInvalid(
            'La corrección no modifica la ficha.',
            code='TECHNICAL_RECORD_WITHOUT_CHANGES',
        )
    errors = _completion_errors(record, policy)
    if errors:
        raise TechnicalRecordInvalid(
            'La corrección dejaría incompleta la ficha.',
            code='TECHNICAL_RECORD_INCOMPLETE',
            field=errors[0],
        )
    previous_version = record.version
    record.version += 1
    record.save(update_fields=[*changed, 'version', 'actualizada_en'])
    after = {field: _field_value(record, field) for field in changed}
    correction = CorreccionFichaTecnica.objects.create(
        ficha=record,
        actor=actor,
        motivo=reason,
        version_anterior=previous_version,
        version_nueva=record.version,
        campos=list(changed),
        valores_anteriores=before,
        valores_nuevos=after,
    )
    return TechnicalRecordMutationResult(record, correction)


def finalization_record_status(*, details, records_by_detail):
    """Valida sólo políticas explícitas y devuelve evidencia por Detalle."""
    statuses = []
    missing_required = []
    for detail in details:
        policy = _service_policy(detail.servicio)
        record = records_by_detail.get(detail.pk)
        errors = _completion_errors(record, policy) if record is not None else []
        complete = bool(
            record is not None
            and record.estado == FichaTecnica.Estado.COMPLETA
            and not errors
        )
        statuses.append({
            'detalle_turno_id': detail.pk,
            'servicio_id': detail.servicio_id,
            'policy_status': policy.status,
            'policy_reason': policy.reason,
            'record_required': policy.record_required,
            'record_id': record.pk if record is not None else None,
            'record_state': record.estado if record is not None else None,
            'record_version': record.version if record is not None else None,
            'complete': complete,
            'completion_errors': errors,
        })
        if policy.record_required and not complete:
            missing_required.append(detail.pk)
    if missing_required:
        raise TechnicalRecordInvalid(
            (
                'Hay Servicios con ficha técnica requerida sin completar: '
                + ', '.join(str(pk) for pk in missing_required)
                + '.'
            ),
            code='REQUIRED_TECHNICAL_RECORD_INCOMPLETE',
            field='detalles',
        )
    return statuses


def can_read_turn_context(*, actor, turno):
    cliente = getattr(actor, 'cliente', None)
    if cliente is not None:
        return bool(
            actor.is_active
            and cliente.activo
            and turno.cliente_id == cliente.pk
        )
    if not user_can_read_global_technical_record(actor):
        return False
    personal = getattr(actor, 'perfil_profesional', None)
    return bool(personal and turno.profesional_id == personal.pk)
