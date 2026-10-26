"""Evaluación técnica versionada de BH-057, sin efectos laterales."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count

from .models import (
    Auditoria,
    DetalleTurno,
    DiagnosticoCapilar,
    EvaluacionRiesgoTecnico,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    ReglaDiagnosticoTecnico,
    ReglaFrecuenciaTecnica,
    ReglaIntervaloTecnico,
    TECHNICAL_RISK_OUTCOME_ORDER,
    TechnicalRiskOutcome,
    Turno,
)


TECHNICAL_ASSESSMENT_CREATED = 'TECHNICAL_ASSESSMENT_CREATED'
TECHNICAL_ASSESSMENT_SUPERSEDED = 'TECHNICAL_ASSESSMENT_SUPERSEDED'
UNCLASSIFIED_SERVICE_RULE_CODE = 'SERVICE_TECHNICAL_PROFILE_MISSING'
INCOMPLETE_HISTORY_RULE_CODE = 'REALIZED_TURNO_WITHOUT_DETAILS'
TRUSTED_DIAGNOSIS_SOURCES = frozenset({DiagnosticoCapilar.Procedencia.PROFESIONAL})


class TechnicalRiskConfigurationError(Exception):
    """La evaluación no puede ejecutarse con seguridad por configuración inválida."""


class TechnicalRiskInputError(ValueError):
    """Los argumentos de evaluación no representan una intención válida."""


class TechnicalRiskSupersessionError(ValueError):
    """La relación entre evaluaciones no representa una supersesión válida."""


@dataclass(frozen=True)
class TechnicalRiskEvaluationResult:
    cliente_id: int
    politica_id: int
    policy_version: str
    fecha_solicitada: date
    outcome: str
    severity: int
    rule_codes: tuple
    missing_data: tuple
    relevant_history: tuple
    minimum_recommended_date: date | None
    client_messages: tuple
    professional_messages: tuple
    input_snapshot: dict
    result_snapshot: dict


def _policy_for_version(policy_version):
    queryset = PoliticaRiesgoTecnico.objects.filter(
        estado=PoliticaRiesgoTecnico.Estado.PUBLICADA
    )
    if policy_version is not None:
        queryset = queryset.filter(version=policy_version)
    else:
        queryset = queryset.order_by('-publicada_at', '-pk')
    policy = queryset.first()
    if policy is None:
        detail = (
            f'No existe una política publicada con versión {policy_version}.'
            if policy_version is not None
            else 'No existe una política técnica publicada.'
        )
        raise TechnicalRiskConfigurationError(detail)
    return policy


def _service_profiles(services):
    profiles = {
        profile.servicio_id: profile
        for profile in PerfilTecnicoServicio.objects.filter(
            servicio_id__in=[service.pk for service in services]
        ).select_related('familia')
    }
    return profiles


def _validate_active_policy_rules(*rule_groups):
    seen_codes = set()
    for rules in rule_groups:
        for rule in rules:
            if rule.code in seen_codes:
                raise TechnicalRiskConfigurationError(
                    f'El code de regla {rule.code} está duplicado en la política.'
                )
            seen_codes.add(rule.code)
            try:
                rule.full_clean()
            except ValidationError as exc:
                raise TechnicalRiskConfigurationError(
                    f'La regla {rule.code} tiene configuración inválida.'
                ) from exc

            for field_name in (
                'servicio_origen',
                'servicio_destino',
                'servicio',
            ):
                service = getattr(rule, field_name, None)
                if service is not None and not service.activo:
                    raise TechnicalRiskConfigurationError(
                        f'La regla {rule.code} referencia un Servicio inactivo.'
                    )
            for field_name in (
                'familia_origen',
                'familia_destino',
                'familia',
            ):
                family = getattr(rule, field_name, None)
                if family is not None and not family.activa:
                    raise TechnicalRiskConfigurationError(
                        f'La regla {rule.code} referencia una familia inactiva.'
                    )


def _profile_is_classified(profile):
    return bool(
        profile
        and profile.activa
        and profile.estado_clasificacion
        == PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
        and profile.nivel_riesgo != PerfilTecnicoServicio.NivelRiesgo.NO_DEFINIDO
        and (profile.familia_id is None or profile.familia.activa)
    )


def _service_snapshot(service, profile):
    return {
        'id': service.pk,
        'activo': service.activo,
        'perfil_tecnico_id': profile.pk if profile else None,
        'estado_clasificacion': profile.estado_clasificacion if profile else None,
        'nivel_riesgo': profile.nivel_riesgo if profile else None,
        'perfil_activo': profile.activa if profile else None,
        'familia_code': (
            profile.familia.code if profile and profile.familia_id else None
        ),
        'familia_activa': (
            profile.familia.activa if profile and profile.familia_id else None
        ),
    }


def _selector_matches_service(*, selected_service_id, selected_family_id, service, profile):
    if selected_service_id is not None:
        return selected_service_id == service.pk
    return bool(profile and profile.familia_id == selected_family_id)


def _interval_rule_matches(rule, previous_service, previous_profile, target, target_profile):
    origin_matches = _selector_matches_service(
        selected_service_id=rule.servicio_origen_id,
        selected_family_id=rule.familia_origen_id,
        service=previous_service,
        profile=previous_profile,
    )
    target_matches = _selector_matches_service(
        selected_service_id=rule.servicio_destino_id,
        selected_family_id=rule.familia_destino_id,
        service=target,
        profile=target_profile,
    )
    return origin_matches and target_matches


def _interval_specificity(rule):
    exact_selectors = int(rule.servicio_origen_id is not None) + int(
        rule.servicio_destino_id is not None
    )
    return exact_selectors + 1


def _diagnosis_rule_matches(rule, service, profile):
    return _selector_matches_service(
        selected_service_id=rule.servicio_destino_id,
        selected_family_id=rule.familia_destino_id,
        service=service,
        profile=profile,
    )


def _frequency_rule_matches(rule, service, profile):
    return _selector_matches_service(
        selected_service_id=rule.servicio_id,
        selected_family_id=rule.familia_id,
        service=service,
        profile=profile,
    )


def _rule_trigger(*, kind, rule, outcome, parameters, evidence):
    return {
        'kind': kind,
        'code': rule.code,
        'outcome': outcome,
        'severity': rule.severidad,
        'priority': rule.prioridad,
        'mensaje_cliente': rule.mensaje_cliente,
        'mensaje_profesional': rule.mensaje_profesional,
        'parameters': parameters,
        'evidence': evidence,
    }


def _missing_profile_trigger(service):
    return {
        'kind': 'CONFIGURATION',
        'code': UNCLASSIFIED_SERVICE_RULE_CODE,
        'outcome': TechnicalRiskOutcome.REQUIERE_REVISION,
        'severity': TECHNICAL_RISK_OUTCOME_ORDER[
            TechnicalRiskOutcome.REQUIERE_REVISION
        ],
        'priority': 10_000,
        'mensaje_cliente': (
            'La solicitud necesita revisión antes de poder continuar.'
        ),
        'mensaje_profesional': (
            f'El Servicio {service.pk} no tiene un perfil técnico clasificado y activo.'
        ),
        'parameters': {'service_id': service.pk},
        'evidence': {'service_id': service.pk},
    }


def _incomplete_history_trigger(inconsistency):
    return {
        'kind': 'HISTORY_INCONSISTENCY',
        'code': INCOMPLETE_HISTORY_RULE_CODE,
        'outcome': TechnicalRiskOutcome.REQUIERE_REVISION,
        'severity': TECHNICAL_RISK_OUTCOME_ORDER[
            TechnicalRiskOutcome.REQUIERE_REVISION
        ],
        'priority': 10_000,
        'mensaje_cliente': (
            'La solicitud necesita revisión antes de poder continuar.'
        ),
        'mensaje_profesional': (
            f'El Turno realizado {inconsistency["turno_id"]} no tiene '
            'Detalles de Servicio.'
        ),
        'parameters': {'reason': 'REALIZED_TURNO_WITHOUT_DETAILS'},
        'evidence': inconsistency,
    }


def _history_for_client(cliente, fecha_solicitada):
    details = list(
        DetalleTurno.objects.filter(
            turno__cliente=cliente,
            turno__estado=Turno.Estado.REALIZADO,
            turno__fecha__lte=fecha_solicitada,
        )
        .select_related(
            'turno',
            'servicio',
            'servicio__perfil_tecnico',
            'servicio__perfil_tecnico__familia',
        )
        .order_by('-turno__fecha', '-turno__hora_inicio', '-pk')
    )
    snapshots = []
    for detail in details:
        try:
            profile = detail.servicio.perfil_tecnico
        except PerfilTecnicoServicio.DoesNotExist:
            profile = None
        snapshots.append({
            'detail': detail,
            'profile': profile,
            'snapshot': {
                'turno_id': detail.turno_id,
                'detalle_id': detail.pk,
                'servicio_id': detail.servicio_id,
                'fecha': detail.turno.fecha.isoformat(),
                'hora': detail.turno.hora_inicio.isoformat(),
                'familia_code': (
                    profile.familia.code
                    if profile and profile.familia_id
                    else None
                ),
                'estado_clasificacion': (
                    profile.estado_clasificacion if profile else None
                ),
            },
        })
    incomplete_turnos = list(
        Turno.objects.filter(
            cliente=cliente,
            estado=Turno.Estado.REALIZADO,
            fecha__lte=fecha_solicitada,
        )
        .annotate(detail_count=Count('detalles'))
        .filter(detail_count=0)
        .order_by('-fecha', '-hora_inicio', '-pk')
    )
    inconsistencies = [
        {
            'code': INCOMPLETE_HISTORY_RULE_CODE,
            'turno_id': turno.pk,
            'fecha': turno.fecha.isoformat(),
            'hora': turno.hora_inicio.isoformat(),
            'estado': turno.estado,
            'detalle_count': 0,
        }
        for turno in incomplete_turnos
    ]
    return snapshots, inconsistencies


def _diagnosis_snapshot(cliente, fecha_solicitada):
    diagnosis = (
        DiagnosticoCapilar.objects.filter(
            cliente=cliente,
            fecha_diagnostico__date__lte=fecha_solicitada,
        )
        .order_by('-fecha_diagnostico', '-pk')
        .first()
    )
    if diagnosis is None:
        return None, None
    fields = {
        'tipo_cabello': diagnosis.tipo_cabello_id,
        'grosor_cabello': diagnosis.grosor_cabello_id,
        'porosidad_cabello': diagnosis.porosidad_cabello_id,
        'cuero_cabelludo': diagnosis.cuero_cabelludo_id,
        'estado_general': diagnosis.estado_general_id,
    }
    snapshot = {
        'id': diagnosis.pk,
        'fecha': diagnosis.fecha_diagnostico.isoformat(),
        'procedencia': diagnosis.procedencia,
        'completo': all(value is not None for value in fields.values()),
        'campos_presentes': {
            field: value is not None for field, value in fields.items()
        },
    }
    return diagnosis, snapshot


def _append_diagnosis_triggers(
    *, triggers, rules, services, profiles, diagnosis, diagnosis_snapshot,
    fecha_solicitada,
):
    for service in services:
        profile = profiles.get(service.pk)
        matching = [
            rule for rule in rules
            if _diagnosis_rule_matches(rule, service, profile)
        ]
        if not matching:
            continue
        most_specific = max(
            int(rule.servicio_destino_id is not None) for rule in matching
        )
        selected = [
            rule for rule in matching
            if int(rule.servicio_destino_id is not None) == most_specific
        ]
        for rule in selected:
            if not rule.requiere_diagnostico:
                continue
            base_parameters = {
                'service_id': service.pk,
                'antiguedad_maxima_dias': rule.antiguedad_maxima_dias,
            }
            if diagnosis is None:
                triggers.append(_rule_trigger(
                    kind='DIAGNOSIS_MISSING',
                    rule=rule,
                    outcome=rule.outcome_si_falta,
                    parameters=base_parameters,
                    evidence={'diagnostico_id': None},
                ))
                continue

            age = (fecha_solicitada - diagnosis.fecha_diagnostico.date()).days
            evidence = {
                'diagnostico_id': diagnosis.pk,
                'fecha_diagnostico': diagnosis.fecha_diagnostico.isoformat(),
                'antiguedad_dias': age,
                'procedencia': diagnosis.procedencia,
            }
            if (
                rule.antiguedad_maxima_dias is not None
                and age > rule.antiguedad_maxima_dias
            ):
                triggers.append(_rule_trigger(
                    kind='DIAGNOSIS_EXPIRED',
                    rule=rule,
                    outcome=rule.outcome_si_vencido,
                    parameters=base_parameters,
                    evidence=evidence,
                ))
            if not diagnosis_snapshot['completo']:
                triggers.append(_rule_trigger(
                    kind='DIAGNOSIS_INCOMPLETE',
                    rule=rule,
                    outcome=rule.outcome_si_incompleto,
                    parameters=base_parameters,
                    evidence=evidence,
                ))
            if diagnosis.procedencia not in TRUSTED_DIAGNOSIS_SOURCES:
                triggers.append(_rule_trigger(
                    kind='DIAGNOSIS_UNTRUSTED_SOURCE',
                    rule=rule,
                    outcome=rule.outcome_si_procedencia_no_confiable,
                    parameters=base_parameters,
                    evidence=evidence,
                ))


def _append_interval_triggers(
    *, triggers, rules, history, services, profiles, fecha_solicitada,
):
    minimum_dates = []
    for event in history:
        detail = event['detail']
        previous_service = detail.servicio
        previous_profile = event['profile']
        elapsed_days = (fecha_solicitada - detail.turno.fecha).days
        for target in services:
            target_profile = profiles.get(target.pk)
            matching = [
                rule for rule in rules
                if _interval_rule_matches(
                    rule,
                    previous_service,
                    previous_profile,
                    target,
                    target_profile,
                )
            ]
            if not matching:
                continue
            specificity = max(_interval_specificity(rule) for rule in matching)
            selected = [
                rule for rule in matching
                if _interval_specificity(rule) == specificity
            ]
            for rule in selected:
                if elapsed_days >= rule.dias_minimos:
                    continue
                minimum_date = detail.turno.fecha + timedelta(
                    days=rule.dias_minimos
                )
                minimum_dates.append(minimum_date)
                triggers.append(_rule_trigger(
                    kind='INTERVAL',
                    rule=rule,
                    outcome=rule.outcome,
                    parameters={
                        'dias_minimos': rule.dias_minimos,
                        'specificity': specificity,
                        'servicio_origen_id': rule.servicio_origen_id,
                        'familia_origen_id': rule.familia_origen_id,
                        'servicio_destino_id': rule.servicio_destino_id,
                        'familia_destino_id': rule.familia_destino_id,
                    },
                    evidence={
                        'turno_id': detail.turno_id,
                        'detalle_id': detail.pk,
                        'servicio_previo_id': previous_service.pk,
                        'servicio_solicitado_id': target.pk,
                        'fecha_servicio_previo': detail.turno.fecha.isoformat(),
                        'dias_transcurridos': elapsed_days,
                        'fecha_minima_recomendada': minimum_date.isoformat(),
                    },
                ))
    return minimum_dates


def _append_requested_service_interaction_triggers(
    *, triggers, rules, services, profiles, fecha_solicitada,
):
    minimum_dates = []
    if len(services) < 2:
        return minimum_dates
    for origin in services:
        origin_profile = profiles.get(origin.pk)
        for target in services:
            if origin.pk == target.pk:
                continue
            target_profile = profiles.get(target.pk)
            matching = [
                rule for rule in rules
                if _interval_rule_matches(
                    rule,
                    origin,
                    origin_profile,
                    target,
                    target_profile,
                )
            ]
            if not matching:
                continue
            specificity = max(_interval_specificity(rule) for rule in matching)
            selected = [
                rule for rule in matching
                if _interval_specificity(rule) == specificity
            ]
            for rule in selected:
                if rule.dias_minimos == 0:
                    continue
                minimum_date = fecha_solicitada + timedelta(
                    days=rule.dias_minimos
                )
                minimum_dates.append(minimum_date)
                triggers.append(_rule_trigger(
                    kind='REQUESTED_SERVICE_INTERACTION',
                    rule=rule,
                    outcome=rule.outcome,
                    parameters={
                        'dias_minimos': rule.dias_minimos,
                        'specificity': specificity,
                        'servicio_origen_id': rule.servicio_origen_id,
                        'familia_origen_id': rule.familia_origen_id,
                        'servicio_destino_id': rule.servicio_destino_id,
                        'familia_destino_id': rule.familia_destino_id,
                    },
                    evidence={
                        'servicio_origen_solicitado_id': origin.pk,
                        'servicio_destino_solicitado_id': target.pk,
                        'dias_entre_servicios': 0,
                        'fecha_minima_recomendada': minimum_date.isoformat(),
                    },
                ))
    return minimum_dates


def _append_frequency_triggers(
    *, triggers, rules, history, services, profiles, fecha_solicitada,
):
    for rule in rules:
        requested_matches = sum(
            1 for service in services
            if _frequency_rule_matches(rule, service, profiles.get(service.pk))
        )
        if requested_matches == 0:
            continue
        window_start = fecha_solicitada - timedelta(days=rule.ventana_dias)
        matching_history = []
        for event in history:
            detail = event['detail']
            if detail.turno.fecha < window_start:
                continue
            if _frequency_rule_matches(
                rule,
                detail.servicio,
                event['profile'],
            ):
                matching_history.append(event)
        projected_count = len(matching_history) + requested_matches
        if projected_count <= rule.cantidad_maxima:
            continue
        triggers.append(_rule_trigger(
            kind='FREQUENCY',
            rule=rule,
            outcome=rule.outcome,
            parameters={
                'ventana_dias': rule.ventana_dias,
                'cantidad_maxima': rule.cantidad_maxima,
                'servicio_id': rule.servicio_id,
                'familia_id': rule.familia_id,
            },
            evidence={
                'window_start': window_start.isoformat(),
                'fecha_solicitada': fecha_solicitada.isoformat(),
                'eventos_previos': len(matching_history),
                'eventos_solicitados': requested_matches,
                'cantidad_proyectada': projected_count,
                'detalle_ids': [
                    event['detail'].pk for event in matching_history
                ],
            },
        ))


def evaluate_booking_risk(
    *,
    cliente,
    servicios,
    fecha_solicitada,
    policy_version=None,
):
    """Evalúa riesgo sin crear ni modificar ninguna entidad de negocio."""
    if not getattr(cliente, 'pk', None):
        raise TechnicalRiskInputError('Se requiere un Cliente persistido.')
    if (
        not isinstance(fecha_solicitada, date)
        or isinstance(fecha_solicitada, datetime)
    ):
        raise TechnicalRiskInputError('fecha_solicitada debe ser una fecha.')

    provided_services = tuple(servicios)
    if not provided_services:
        raise TechnicalRiskInputError('Se requiere al menos un Servicio persistido.')
    if any(not getattr(service, 'pk', None) for service in provided_services):
        raise TechnicalRiskInputError('Todos los Servicios deben estar persistidos.')
    unique_services = {
        service.pk: service for service in provided_services
    }
    services = tuple(unique_services.values())
    if any(not service.activo for service in services):
        raise TechnicalRiskConfigurationError(
            'Todos los Servicios evaluados deben estar activos.'
        )

    policy = _policy_for_version(policy_version)
    profiles = _service_profiles(services)
    history, history_inconsistencies = _history_for_client(
        cliente, fecha_solicitada
    )
    diagnosis, diagnosis_snapshot = _diagnosis_snapshot(
        cliente, fecha_solicitada
    )

    interval_rules = list(
        ReglaIntervaloTecnico.objects.filter(
            politica=policy,
            activa=True,
        ).select_related(
            'servicio_origen', 'familia_origen',
            'servicio_destino', 'familia_destino',
        )
    )
    diagnosis_rules = list(
        ReglaDiagnosticoTecnico.objects.filter(
            politica=policy,
            activa=True,
        ).select_related('servicio_destino', 'familia_destino')
    )
    frequency_rules = list(
        ReglaFrecuenciaTecnica.objects.filter(
            politica=policy,
            activa=True,
        ).select_related('servicio', 'familia')
    )
    _validate_active_policy_rules(
        interval_rules,
        diagnosis_rules,
        frequency_rules,
    )

    triggers = []
    missing_data = []
    for inconsistency in history_inconsistencies:
        missing_data.append(dict(inconsistency))
        triggers.append(_incomplete_history_trigger(inconsistency))
    for service in services:
        profile = profiles.get(service.pk)
        if not _profile_is_classified(profile):
            missing_data.append({
                'code': 'SERVICE_TECHNICAL_PROFILE_INCOMPLETE',
                'service_id': service.pk,
            })
            triggers.append(_missing_profile_trigger(service))

    minimum_dates = _append_interval_triggers(
        triggers=triggers,
        rules=interval_rules,
        history=history,
        services=services,
        profiles=profiles,
        fecha_solicitada=fecha_solicitada,
    )
    minimum_dates.extend(_append_requested_service_interaction_triggers(
        triggers=triggers,
        rules=interval_rules,
        services=services,
        profiles=profiles,
        fecha_solicitada=fecha_solicitada,
    ))
    _append_diagnosis_triggers(
        triggers=triggers,
        rules=diagnosis_rules,
        services=services,
        profiles=profiles,
        diagnosis=diagnosis,
        diagnosis_snapshot=diagnosis_snapshot,
        fecha_solicitada=fecha_solicitada,
    )
    _append_frequency_triggers(
        triggers=triggers,
        rules=frequency_rules,
        history=history,
        services=services,
        profiles=profiles,
        fecha_solicitada=fecha_solicitada,
    )

    triggers.sort(key=lambda item: (-item['priority'], item['code']))
    if triggers:
        outcome = max(
            (item['outcome'] for item in triggers),
            key=lambda value: TECHNICAL_RISK_OUTCOME_ORDER[value],
        )
        severity = max(item['severity'] for item in triggers)
    else:
        outcome = TechnicalRiskOutcome.APTO
        severity = 0

    rule_codes = tuple(dict.fromkeys(item['code'] for item in triggers))
    client_messages = tuple(dict.fromkeys(
        item['mensaje_cliente'] for item in triggers if item['mensaje_cliente']
    ))
    professional_messages = tuple(dict.fromkeys(
        item['mensaje_profesional']
        for item in triggers
        if item['mensaje_profesional']
    ))
    minimum_recommended_date = max(minimum_dates) if minimum_dates else None
    for trigger in triggers:
        trigger['policy_version'] = policy.version

    history_snapshot = [event['snapshot'] for event in history]
    history_snapshot.extend(history_inconsistencies)
    input_snapshot = {
        'cliente_id': cliente.pk,
        'servicios': [
            _service_snapshot(service, profiles.get(service.pk))
            for service in services
        ],
        'fecha_solicitada': fecha_solicitada.isoformat(),
        'policy_version': policy.version,
        'historial_considerado': history_snapshot,
        'inconsistencias_historial': history_inconsistencies,
        'diagnostico_usado': diagnosis_snapshot,
        'datos_faltantes': missing_data,
    }
    result_snapshot = {
        'outcome': outcome,
        'severity': severity,
        'policy_version': policy.version,
        'rule_codes': list(rule_codes),
        'reglas_disparadas': triggers,
        'fecha_minima_recomendada': (
            minimum_recommended_date.isoformat()
            if minimum_recommended_date
            else None
        ),
        'mensajes_cliente': list(client_messages),
        'mensajes_profesional': list(professional_messages),
    }
    return TechnicalRiskEvaluationResult(
        cliente_id=cliente.pk,
        politica_id=policy.pk,
        policy_version=policy.version,
        fecha_solicitada=fecha_solicitada,
        outcome=outcome,
        severity=severity,
        rule_codes=rule_codes,
        missing_data=tuple(missing_data),
        relevant_history=tuple(history_snapshot),
        minimum_recommended_date=minimum_recommended_date,
        client_messages=client_messages,
        professional_messages=professional_messages,
        input_snapshot=input_snapshot,
        result_snapshot=result_snapshot,
    )


@transaction.atomic
def persist_technical_risk_evaluation(*, result, actor=None):
    """Orquestador separado: persiste y audita un resultado ya calculado."""
    evaluation = EvaluacionRiesgoTecnico.objects.create(
        cliente_id=result.cliente_id,
        politica_id=result.politica_id,
        outcome=result.outcome,
        severity=result.severity,
        fecha_solicitada=result.fecha_solicitada,
        input_snapshot=result.input_snapshot,
        result_snapshot=result.result_snapshot,
    )
    Auditoria.objects.create(
        tabla='EvaluacionRiesgoTecnico',
        registro_id=evaluation.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='ALTA',
        valor_nuevo={
            'event': TECHNICAL_ASSESSMENT_CREATED,
            'evaluation_id': evaluation.pk,
            'policy_version': result.policy_version,
            'outcome': result.outcome,
            'rule_codes': list(result.rule_codes),
        },
    )
    return evaluation


@transaction.atomic
def supersede_technical_risk_evaluation(
    *, original_evaluation_id, replacement_evaluation_id, actor=None
):
    """Marca E1 como superada por E2 sin alterar su evidencia histórica."""
    if original_evaluation_id == replacement_evaluation_id:
        raise TechnicalRiskSupersessionError(
            'Una evaluación no puede superarse a sí misma.'
        )
    evaluations = EvaluacionRiesgoTecnico.objects.select_for_update().filter(
        pk__in=[original_evaluation_id, replacement_evaluation_id]
    ).in_bulk()
    try:
        original = evaluations[original_evaluation_id]
        replacement = evaluations[replacement_evaluation_id]
    except KeyError as exc:
        raise TechnicalRiskSupersessionError(
            'Las dos evaluaciones deben existir.'
        ) from exc

    if original.cliente_id != replacement.cliente_id:
        raise TechnicalRiskSupersessionError(
            'Las evaluaciones deben pertenecer al mismo Cliente.'
        )
    if replacement.evaluated_at <= original.evaluated_at:
        raise TechnicalRiskSupersessionError(
            'La evaluación reemplazante debe ser posterior.'
        )
    if original.superseded_by_id is not None:
        if original.superseded_by_id == replacement.pk:
            return original
        raise TechnicalRiskSupersessionError(
            'La evaluación original ya fue superada.'
        )
    if replacement.superseded_by_id is not None:
        raise TechnicalRiskSupersessionError(
            'La evaluación reemplazante ya fue superada.'
        )

    updated = EvaluacionRiesgoTecnico.objects._set_superseded_by(
        evaluation_id=original.pk,
        replacement_id=replacement.pk,
    )
    if updated != 1:
        raise TechnicalRiskSupersessionError(
            'La evaluación original ya fue superada.'
        )
    original.superseded_by = replacement
    Auditoria.objects.create(
        tabla='EvaluacionRiesgoTecnico',
        registro_id=original.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='MODIFICACION',
        valor_anterior={'superseded_by_id': None},
        valor_nuevo={
            'event': TECHNICAL_ASSESSMENT_SUPERSEDED,
            'evaluation_id': original.pk,
            'superseded_by_id': replacement.pk,
            'policy_version': original.result_snapshot['policy_version'],
            'outcome': original.outcome,
            'rule_codes': original.result_snapshot['rule_codes'],
        },
    )
    return original
