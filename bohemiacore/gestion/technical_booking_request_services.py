"""Orquestación de solicitudes técnicas previas y no bloqueantes."""

from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from usuarios.roles import BusinessPermission

from .models import (
    AceptacionAdvertenciaTecnica,
    Auditoria,
    DecisionRevisionTecnica,
    EvaluacionSolicitudTecnica,
    Personal,
    Servicio,
    SolicitudTecnicaReserva,
    SolicitudTecnicaServicio,
    TechnicalRiskOutcome,
)
from .service_skill_compatibility import service_skill_policy
from .technical_risk_evaluator import (
    TechnicalRiskConfigurationError,
    evaluate_booking_risk,
    persist_technical_risk_evaluation,
    supersede_technical_risk_evaluation,
)
from .technical_skill_access import DIAGNOSIS_SKILL_CODE, user_has_active_skill


TECHNICAL_WARNING_ACCEPTED = 'TECHNICAL_WARNING_ACCEPTED'
TECHNICAL_REVIEW_REQUIRED = 'TECHNICAL_REVIEW_REQUIRED'
TECHNICAL_REVIEW_APPROVED = 'TECHNICAL_REVIEW_APPROVED'
TECHNICAL_REVIEW_REJECTED = 'TECHNICAL_REVIEW_REJECTED'
TECHNICAL_REVIEW_INFORMATION_REQUESTED = (
    'TECHNICAL_REVIEW_INFORMATION_REQUESTED'
)
TECHNICAL_REVIEW_DATE_RECOMMENDED = 'TECHNICAL_REVIEW_DATE_RECOMMENDED'

OUTCOME_TO_REQUEST_STATE = {
    TechnicalRiskOutcome.APTO: (
        SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
    ),
    TechnicalRiskOutcome.ADVERTENCIA: (
        SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE
    ),
    TechnicalRiskOutcome.REQUIERE_REVISION: (
        SolicitudTecnicaReserva.Estado.EN_REVISION
    ),
    TechnicalRiskOutcome.NO_APTO: (
        SolicitudTecnicaReserva.Estado.RECHAZADA_TECNICAMENTE
    ),
}

ALLOWED_INFORMATION_CODES = frozenset({
    'DIAGNOSTICO_ACTUALIZADO',
    'INFORMACION_ADICIONAL',
})


class TechnicalBookingRequestError(ValueError):
    pass


class TechnicalBookingRequestNotFound(TechnicalBookingRequestError):
    pass


class TechnicalBookingRequestPermissionDenied(TechnicalBookingRequestError):
    pass


class TechnicalBookingRequestTransitionError(TechnicalBookingRequestError):
    pass


_UNSET = object()


def _audit(*, solicitud, actor, event, previous=None, payload=None):
    values = {
        'event': event,
        'solicitud_id': solicitud.pk,
        'evaluation_id': solicitud.evaluacion_vigente_id,
    }
    values.update(payload or {})
    return Auditoria.objects.create(
        tabla='SolicitudTecnicaReserva',
        registro_id=solicitud.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='MODIFICACION',
        valor_anterior=previous,
        valor_nuevo=values,
    )


def _validated_client(cliente):
    if (
        not getattr(cliente, 'pk', None)
        or not cliente.activo
        or not cliente.usuario.is_active
    ):
        raise TechnicalBookingRequestError('Se requiere un Cliente activo.')
    return cliente


def _validated_services(servicios):
    provided = tuple(servicios)
    unique_ids = tuple(dict.fromkeys(
        getattr(service, 'pk', None) for service in provided
    ))
    if not unique_ids or None in unique_ids:
        raise TechnicalBookingRequestError(
            'Se requiere al menos un Servicio persistido.'
        )
    persisted = {
        service.pk: service
        for service in Servicio.objects.filter(pk__in=unique_ids, activo=True)
    }
    if set(persisted) != set(unique_ids):
        raise TechnicalBookingRequestError(
            'Todos los Servicios deben existir y estar activos.'
        )
    return tuple(persisted[service_id] for service_id in unique_ids)


def _validated_date(value):
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TechnicalBookingRequestError('La fecha preferida es inválida.')
    if value < timezone.localdate():
        raise TechnicalBookingRequestError(
            'La fecha preferida no puede estar en el pasado.'
        )
    return value


def _validated_personal(personal):
    if personal is None:
        return None
    if not getattr(personal, 'pk', None) or not personal.activo:
        raise TechnicalBookingRequestError(
            'El Personal preferido debe existir y estar activo.'
        )
    return personal


def _replace_services(solicitud, services):
    solicitud.servicios_solicitados.all().delete()
    for order, service in enumerate(services):
        SolicitudTecnicaServicio.objects.create(
            solicitud=solicitud,
            servicio=service,
            orden=order,
            nombre_snapshot=service.nombre,
        )


def _persist_attempt(*, solicitud, services, actor, policy_version=None):
    try:
        result = evaluate_booking_risk(
            cliente=solicitud.cliente,
            servicios=services,
            fecha_solicitada=solicitud.fecha_preferida,
            policy_version=policy_version,
        )
    except TechnicalRiskConfigurationError as exc:
        raise TechnicalBookingRequestError(
            'No pudimos evaluar la solicitud de forma segura. '
            'La configuración técnica requiere revisión.'
        ) from exc
    evaluation = persist_technical_risk_evaluation(result=result, actor=actor)
    EvaluacionSolicitudTecnica.objects.create(
        solicitud=solicitud,
        evaluacion=evaluation,
        intento=solicitud.intento,
    )
    return result, evaluation


def _apply_result(solicitud, result, evaluation):
    solicitud.evaluacion_vigente = evaluation
    solicitud.estado = OUTCOME_TO_REQUEST_STATE[result.outcome]
    solicitud.save(update_fields=[
        'evaluacion_vigente',
        'estado',
        'updated_at',
    ])


@transaction.atomic
def create_technical_booking_request(
    *,
    cliente,
    servicios,
    fecha_preferida,
    hora_preferida,
    personal_preferido=None,
    actor=None,
    policy_version=None,
):
    cliente = _validated_client(cliente)
    services = _validated_services(servicios)
    fecha_preferida = _validated_date(fecha_preferida)
    personal_preferido = _validated_personal(personal_preferido)
    if hora_preferida is None:
        raise TechnicalBookingRequestError('La hora preferida es obligatoria.')

    solicitud = SolicitudTecnicaReserva.objects.create(
        cliente=cliente,
        fecha_preferida=fecha_preferida,
        hora_preferida=hora_preferida,
        personal_preferido=personal_preferido,
        estado=SolicitudTecnicaReserva.Estado.EVALUANDO,
    )
    _replace_services(solicitud, services)
    result, evaluation = _persist_attempt(
        solicitud=solicitud,
        services=services,
        actor=actor,
        policy_version=policy_version,
    )
    _apply_result(solicitud, result, evaluation)
    if result.outcome == TechnicalRiskOutcome.REQUIERE_REVISION:
        _audit(
            solicitud=solicitud,
            actor=actor,
            event=TECHNICAL_REVIEW_REQUIRED,
            payload={'rule_codes': list(result.rule_codes)},
        )
    return solicitud


@transaction.atomic
def accept_technical_warning(*, solicitud_id, actor):
    try:
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=solicitud_id
        )
    except SolicitudTecnicaReserva.DoesNotExist as exc:
        raise TechnicalBookingRequestNotFound(
            'La solicitud técnica no existe.'
        ) from exc
    if solicitud.cliente.usuario_id != getattr(actor, 'pk', None):
        raise TechnicalBookingRequestPermissionDenied(
            'Sólo el Cliente propietario puede aceptar la advertencia.'
        )
    evaluation = solicitud.evaluacion_vigente
    if (
        solicitud.estado
        != SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE
        or evaluation is None
        or evaluation.outcome != TechnicalRiskOutcome.ADVERTENCIA
        or evaluation.superseded_by_id is not None
    ):
        existing = AceptacionAdvertenciaTecnica.objects.filter(
            solicitud=solicitud,
            evaluacion=evaluation,
            actor=actor,
        ).first()
        if (
            existing
            and solicitud.estado
            == SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
        ):
            return existing
        raise TechnicalBookingRequestTransitionError(
            'La advertencia ya no está vigente.'
        )

    snapshot = evaluation.result_snapshot
    acceptance = AceptacionAdvertenciaTecnica.objects.create(
        solicitud=solicitud,
        evaluacion=evaluation,
        policy_version=snapshot['policy_version'],
        warning_codes=snapshot.get('rule_codes', []),
        warning_texts=snapshot.get('mensajes_cliente', []),
        actor=actor,
    )
    previous = solicitud.estado
    solicitud.estado = SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
    solicitud.save(update_fields=['estado', 'updated_at'])
    _audit(
        solicitud=solicitud,
        actor=actor,
        event=TECHNICAL_WARNING_ACCEPTED,
        previous={'estado': previous},
        payload={
            'policy_version': acceptance.policy_version,
            'warning_codes': acceptance.warning_codes,
        },
    )
    return acceptance


@transaction.atomic
def reevaluate_technical_booking_request(
    *,
    solicitud_id,
    actor,
    servicios=None,
    fecha_preferida=None,
    hora_preferida=None,
    personal_preferido=_UNSET,
    informacion_tecnica_actualizada=False,
    policy_version=None,
):
    try:
        solicitud = (
            SolicitudTecnicaReserva.objects.select_for_update()
            .select_related('cliente__usuario')
            .get(pk=solicitud_id)
        )
    except SolicitudTecnicaReserva.DoesNotExist as exc:
        raise TechnicalBookingRequestNotFound(
            'La solicitud técnica no existe.'
        ) from exc
    if solicitud.cliente.usuario_id != getattr(actor, 'pk', None):
        raise TechnicalBookingRequestPermissionDenied(
            'Sólo el Cliente propietario puede reevaluar la solicitud.'
        )
    if solicitud.estado in {
        SolicitudTecnicaReserva.Estado.SUPERADA,
        SolicitudTecnicaReserva.Estado.VENCIDA,
    }:
        raise TechnicalBookingRequestTransitionError(
            'La solicitud ya no admite reevaluación.'
        )

    current_services = tuple(
        item.servicio
        for item in solicitud.servicios_solicitados.select_related(
            'servicio'
        )
    )
    next_services = (
        _validated_services(servicios)
        if servicios is not None
        else current_services
    )
    next_date = _validated_date(fecha_preferida or solicitud.fecha_preferida)
    next_time = hora_preferida or solicitud.hora_preferida
    next_personal = (
        solicitud.personal_preferido
        if personal_preferido is _UNSET
        else _validated_personal(personal_preferido)
    )
    changed = (
        tuple(service.pk for service in next_services)
        != tuple(service.pk for service in current_services)
        or next_date != solicitud.fecha_preferida
        or next_time != solicitud.hora_preferida
        or getattr(next_personal, 'pk', None)
        != solicitud.personal_preferido_id
        or informacion_tecnica_actualizada
    )
    if not changed:
        return solicitud

    previous_evaluation = solicitud.evaluacion_vigente
    if previous_evaluation is None:
        raise TechnicalBookingRequestTransitionError(
            'La solicitud no tiene una evaluación vigente.'
        )
    # Una reevaluación por cambio de intención conserva la política histórica
    # salvo que un flujo explícito y auditado indique otra versión. Publicar una
    # política nueva no reinterpreta solicitudes existentes por sí solo.
    effective_policy_version = (
        policy_version
        or previous_evaluation.result_snapshot['policy_version']
    )
    solicitud.fecha_preferida = next_date
    solicitud.hora_preferida = next_time
    solicitud.personal_preferido = next_personal
    solicitud.intento += 1
    solicitud.estado = SolicitudTecnicaReserva.Estado.EVALUANDO
    solicitud.fecha_recomendada = None
    solicitud.save(update_fields=[
        'fecha_preferida',
        'hora_preferida',
        'personal_preferido',
        'intento',
        'estado',
        'fecha_recomendada',
        'updated_at',
    ])
    if servicios is not None:
        _replace_services(solicitud, next_services)

    result, evaluation = _persist_attempt(
        solicitud=solicitud,
        services=next_services,
        actor=actor,
        policy_version=effective_policy_version,
    )
    supersede_technical_risk_evaluation(
        original_evaluation_id=previous_evaluation.pk,
        replacement_evaluation_id=evaluation.pk,
        actor=actor,
    )
    _apply_result(solicitud, result, evaluation)
    if result.outcome == TechnicalRiskOutcome.REQUIERE_REVISION:
        _audit(
            solicitud=solicitud,
            actor=actor,
            event=TECHNICAL_REVIEW_REQUIRED,
            payload={'rule_codes': list(result.rule_codes)},
        )
    return solicitud


def reviewer_personal(actor):
    if (
        actor is None
        or not getattr(actor, 'is_authenticated', False)
        or not actor.is_active
        or not actor.has_perm(BusinessPermission.REVIEW_TECHNICAL_BOOKING)
        or not user_has_active_skill(actor, DIAGNOSIS_SKILL_CODE)
    ):
        raise TechnicalBookingRequestPermissionDenied(
            'No cumple los requisitos para revisar solicitudes técnicas.'
        )
    personal = Personal.objects.filter(usuario=actor, activo=True).first()
    if personal is None:
        raise TechnicalBookingRequestPermissionDenied(
            'Se requiere un perfil de Personal activo.'
        )
    return personal


def reviewer_can_review(actor, solicitud):
    try:
        personal = reviewer_personal(actor)
    except TechnicalBookingRequestPermissionDenied:
        return False
    services = tuple(solicitud.servicios.all())
    return service_skill_policy(services).personal_can_perform(personal)


def eligible_review_requests(actor):
    personal = reviewer_personal(actor)
    requests = (
        SolicitudTecnicaReserva.objects.filter(
            estado=SolicitudTecnicaReserva.Estado.EN_REVISION
        )
        .select_related(
            'cliente__usuario',
            'evaluacion_vigente',
            'personal_preferido',
        )
        .prefetch_related(
            'servicios__requisitos_habilidad__habilidad',
            'servicios_solicitados__servicio',
        )
    )
    return tuple(
        solicitud
        for solicitud in requests
        if service_skill_policy(
            tuple(solicitud.servicios.all())
        ).personal_can_perform(personal)
    )


def _same_decision(existing, *, action, reason, client_message, missing, date_value):
    return bool(
        existing
        and existing.accion == action
        and existing.motivo_interno == reason
        and existing.mensaje_cliente == client_message
        and existing.datos_faltantes == missing
        and existing.fecha_recomendada == date_value
    )


@transaction.atomic
def review_technical_booking_request(
    *,
    solicitud_id,
    actor,
    action,
    motivo='',
    mensaje_cliente='',
    datos_faltantes=None,
    fecha_recomendada=None,
):
    try:
        solicitud = (
            SolicitudTecnicaReserva.objects.select_for_update()
            .prefetch_related('servicios__requisitos_habilidad__habilidad')
            .get(pk=solicitud_id)
        )
    except SolicitudTecnicaReserva.DoesNotExist as exc:
        raise TechnicalBookingRequestNotFound(
            'La solicitud técnica no existe.'
        ) from exc
    personal = reviewer_personal(actor)
    services = tuple(solicitud.servicios.all())
    if not service_skill_policy(services).personal_can_perform(personal):
        raise TechnicalBookingRequestPermissionDenied(
            'No tiene compatibilidad con todos los Servicios solicitados.'
        )
    if action not in DecisionRevisionTecnica.Accion.values:
        raise TechnicalBookingRequestError('La acción de revisión es inválida.')

    missing = list(datos_faltantes or [])
    if any(code not in ALLOWED_INFORMATION_CODES for code in missing):
        raise TechnicalBookingRequestError(
            'Los datos faltantes contienen un code no permitido.'
        )
    existing = solicitud.decisiones_revision.filter(
        evaluacion=solicitud.evaluacion_vigente,
        actor=actor,
    ).first()
    if _same_decision(
        existing,
        action=action,
        reason=motivo,
        client_message=mensaje_cliente,
        missing=missing,
        date_value=fecha_recomendada,
    ):
        return existing
    if solicitud.estado != SolicitudTecnicaReserva.Estado.EN_REVISION:
        raise TechnicalBookingRequestTransitionError(
            'La solicitud ya no está disponible para revisión.'
        )

    event = None
    target_state = solicitud.estado
    if action == DecisionRevisionTecnica.Accion.APROBAR:
        if not motivo.strip():
            raise TechnicalBookingRequestError(
                'La aprobación requiere un motivo.'
            )
        target_state = SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
        event = TECHNICAL_REVIEW_APPROVED
    elif action == DecisionRevisionTecnica.Accion.RECHAZAR:
        if not motivo.strip() or not mensaje_cliente.strip():
            raise TechnicalBookingRequestError(
                'El rechazo requiere motivo interno y mensaje al Cliente.'
            )
        target_state = SolicitudTecnicaReserva.Estado.RECHAZADA_TECNICAMENTE
        event = TECHNICAL_REVIEW_REJECTED
    elif action == DecisionRevisionTecnica.Accion.SOLICITAR_INFORMACION:
        if not missing:
            raise TechnicalBookingRequestError(
                'Debe indicar al menos un dato faltante estructurado.'
            )
        target_state = SolicitudTecnicaReserva.Estado.INFORMACION_REQUERIDA
        event = TECHNICAL_REVIEW_INFORMATION_REQUESTED
    else:
        if fecha_recomendada is None or fecha_recomendada < timezone.localdate():
            raise TechnicalBookingRequestError(
                'La fecha recomendada debe ser una fecha futura válida.'
            )
        event = TECHNICAL_REVIEW_DATE_RECOMMENDED

    previous = solicitud.estado
    evaluation = solicitud.evaluacion_vigente
    policy_version = evaluation.result_snapshot['policy_version']
    decision = DecisionRevisionTecnica.objects.create(
        solicitud=solicitud,
        evaluacion=evaluation,
        policy_version=policy_version,
        accion=action,
        actor=actor,
        motivo_interno=motivo,
        mensaje_cliente=mensaje_cliente,
        datos_faltantes=missing,
        fecha_recomendada=fecha_recomendada,
        estado_anterior=previous,
        estado_nuevo=target_state,
    )
    solicitud.estado = target_state
    if fecha_recomendada is not None:
        solicitud.fecha_recomendada = fecha_recomendada
    solicitud.save(update_fields=[
        'estado',
        'fecha_recomendada',
        'updated_at',
    ])
    _audit(
        solicitud=solicitud,
        actor=actor,
        event=event,
        previous={'estado': previous},
        payload={
            'decision_id': decision.pk,
            'evaluation_id': decision.evaluacion_id,
            'policy_version': decision.policy_version,
            'estado': target_state,
            'estado_anterior': decision.estado_anterior,
            'estado_nuevo': decision.estado_nuevo,
            'action': action,
            'accion': action,
            'motivo': decision.motivo_interno,
            'mensaje_cliente': decision.mensaje_cliente,
            'missing_codes': missing,
            'recommended_date': (
                fecha_recomendada.isoformat() if fecha_recomendada else None
            ),
            'decision_created_at': decision.created_at.isoformat(),
        },
    )
    return decision
