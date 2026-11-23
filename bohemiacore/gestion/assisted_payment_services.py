"""Preparación financiera asistida sobre BH-058, sin autoridad de excepción."""

from dataclasses import dataclass

from django.db import transaction

from usuarios.roles import BusinessPermission

from .assisted_slot_hold_services import assisted_slot_hold_for_actor
from .assisted_technical_booking_services import (
    AssistedTechnicalBookingConflict,
    AssistedTechnicalBookingError,
    AssistedTechnicalBookingNotFound,
    AssistedTechnicalBookingPermissionDenied,
    _advisory_lock,
    _audit,
    _authorized_actor,
    _existing_operation,
    _fingerprint,
    _normalized_key,
    _normalized_operation_id,
    _sha256,
    assisted_request_for_actor,
)
from .models import (
    ConsentimientoAdvertenciaAsistido,
    PaymentIntent,
    SolicitudTecnicaAsistidaOperacion,
    SolicitudTecnicaReserva,
    TechnicalRiskOutcome,
)
from .payment_intent_services import (
    PaymentIntentConflict,
    PaymentIntentError,
    PaymentIntentNotFound,
    _create_payment_intent,
    _get_payment_intent_options,
)


ASSISTED_PAYMENT_INTENT_PREPARED = 'ASSISTED_PAYMENT_INTENT_PREPARED'


@dataclass(frozen=True)
class AssistedPaymentIntentResult:
    intent: PaymentIntent
    operation_id: str
    recovered: bool


def _authorized_financial_actor(actor):
    current = _authorized_actor(actor)
    if not current.has_perm(BusinessPermission.REGISTER_PAYMENT):
        raise AssistedTechnicalBookingPermissionDenied(
            'ASSISTED_PAYMENT_PERMISSION_DENIED',
            (
                'Preparar una obligación asistida requiere conjuntamente '
                'create_turno_for_client y register_payment.'
            ),
        )
    return current


def _lock_operation_identity(command, key_digest, operation_id):
    for value in sorted((
        f'assisted-key:{command}:{key_digest}',
        f'assisted-operation:{operation_id}',
    )):
        _advisory_lock(value)


def _internal_intent_key(key_digest):
    return f'assisted-intent:{key_digest}'


def _validate_assisted_financial_context(solicitud):
    evaluation = solicitud.evaluacion_vigente
    if (
        solicitud.estado
        != SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
        or evaluation is None
        or evaluation.superseded_by_id is not None
        or evaluation.cliente_id != solicitud.cliente_id
        or evaluation.fecha_solicitada != solicitud.fecha_preferida
    ):
        raise AssistedTechnicalBookingConflict(
            'TECHNICAL_CONTEXT_NOT_CURRENT',
            'La solicitud o evaluación técnica ya no está vigente.',
        )
    if evaluation.outcome == TechnicalRiskOutcome.ADVERTENCIA:
        snapshot = evaluation.result_snapshot
        consent = (
            ConsentimientoAdvertenciaAsistido.objects.filter(
                solicitud=solicitud,
                evaluacion=evaluation,
                cliente_informado_id=solicitud.cliente_id,
                operador_id=solicitud.operador_registrante_id,
                medio_solicitud=solicitud.medio_solicitud,
                outcome=TechnicalRiskOutcome.ADVERTENCIA,
                policy_version=snapshot.get('policy_version'),
                warning_codes=list(snapshot.get('rule_codes', [])),
                warning_texts=list(snapshot.get('mensajes_cliente', [])),
                decision=ConsentimientoAdvertenciaAsistido.Decision.ACEPTA,
            )
            .order_by('-decided_at', '-pk')
            .first()
        )
        if consent is None:
            raise AssistedTechnicalBookingConflict(
                'ASSISTED_CONSENT_NOT_CURRENT',
                'La ADVERTENCIA no conserva un consentimiento asistido válido.',
            )
    elif evaluation.outcome != TechnicalRiskOutcome.APTO:
        raise AssistedTechnicalBookingConflict(
            'TECHNICAL_OUTCOME_NOT_APPROVED',
            'El outcome técnico no habilita preparación financiera.',
        )


def _assisted_scope(*, solicitud_id, hold, cliente, actor):
    current = _authorized_financial_actor(actor)
    if (
        hold.solicitud_id != solicitud_id
        or hold.cliente_id != cliente.pk
        or hold.created_by_id != current.pk
    ):
        return False
    try:
        solicitud = SolicitudTecnicaReserva.objects.get(pk=solicitud_id)
    except SolicitudTecnicaReserva.DoesNotExist:
        return False
    if (
        solicitud.operador_registrante_id != current.pk
        or solicitud.medio_solicitud not in {
            SolicitudTecnicaReserva.MedioSolicitud.TELEFONO,
            SolicitudTecnicaReserva.MedioSolicitud.PRESENCIAL,
        }
    ):
        return False
    return SolicitudTecnicaAsistidaOperacion.objects.filter(
        solicitud=solicitud,
        actor=current,
        command=SolicitudTecnicaAsistidaOperacion.Command.HOLD,
        hold=hold,
    ).exists()


def _translate_payment_error(exc):
    if isinstance(exc, PaymentIntentNotFound):
        return AssistedTechnicalBookingNotFound(
            'ASSISTED_PAYMENT_CONTEXT_NOT_FOUND',
            'El contexto financiero asistido no está disponible.',
        )
    if isinstance(exc, PaymentIntentConflict):
        return AssistedTechnicalBookingConflict(exc.code, exc.detail, exc.field)
    return AssistedTechnicalBookingError(exc.code, exc.detail, exc.field)


@transaction.atomic
def assisted_payment_options(*, solicitud_id, hold_public_id, actor):
    current = _authorized_financial_actor(actor)
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current,
    )
    _validate_assisted_financial_context(solicitud)
    hold = assisted_slot_hold_for_actor(
        solicitud_id=solicitud.pk,
        actor=current,
        public_id=hold_public_id,
    )
    try:
        return _get_payment_intent_options(
            hold=hold,
            actor=current,
            scope_checker=lambda locked_hold, cliente, scope_actor: (
                _assisted_scope(
                    solicitud_id=solicitud.pk,
                    hold=locked_hold,
                    cliente=cliente,
                    actor=scope_actor,
                )
            ),
        )
    except PaymentIntentError as exc:
        raise _translate_payment_error(exc) from exc


@transaction.atomic
def prepare_assisted_payment_intent(
    *,
    solicitud_id,
    hold_public_id,
    mode,
    actor,
    idempotency_key,
    operation_id,
):
    key = _normalized_key(idempotency_key)
    normalized_operation_id = _normalized_operation_id(operation_id)
    key_digest = _sha256(key)
    fingerprint = _fingerprint({
        'actor_id': getattr(actor, 'pk', None),
        'operation_id': str(normalized_operation_id),
        'solicitud_id': solicitud_id,
        'hold_public_id': str(hold_public_id),
        'mode': mode,
    })
    command = SolicitudTecnicaAsistidaOperacion.Command.INTENT
    _lock_operation_identity(command, key_digest, normalized_operation_id)
    current = _authorized_financial_actor(actor)
    existing = _existing_operation(
        command=command,
        key_digest=key_digest,
        operation_id=normalized_operation_id,
        actor=current,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return AssistedPaymentIntentResult(
            intent=existing.payment_intent,
            operation_id=str(existing.operation_id),
            recovered=True,
        )
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current,
        lock=True,
    )
    _validate_assisted_financial_context(solicitud)
    hold = assisted_slot_hold_for_actor(
        solicitud_id=solicitud.pk,
        actor=current,
        public_id=hold_public_id,
    )
    try:
        result = _create_payment_intent(
            hold=hold,
            mode=mode,
            idempotency_key=_internal_intent_key(key_digest),
            actor=current,
            scope_checker=lambda locked_hold, cliente, scope_actor: (
                _assisted_scope(
                    solicitud_id=solicitud.pk,
                    hold=locked_hold,
                    cliente=cliente,
                    actor=scope_actor,
                )
            ),
        )
    except PaymentIntentError as exc:
        raise _translate_payment_error(exc) from exc
    if not result.succeeded:
        raise AssistedTechnicalBookingConflict(result.code, result.detail)
    operation = SolicitudTecnicaAsistidaOperacion.objects.create(
        operation_id=normalized_operation_id,
        actor=current,
        command=command,
        idempotency_key_digest=key_digest,
        fingerprint=fingerprint,
        solicitud=solicitud,
        hold=hold,
        payment_intent=result.intent,
    )
    _audit(
        operation=operation,
        event=ASSISTED_PAYMENT_INTENT_PREPARED,
        extra={
            'hold_public_id': str(hold.public_id),
            'intent_public_id': str(result.intent.public_id),
            'policy_version': result.intent.policy_snapshot.get('version'),
            'mode': result.intent.mode,
            'total_amount_snapshot': str(result.intent.total_amount_snapshot),
            'required_amount': str(result.intent.required_amount),
            'currency': result.intent.currency,
            'expires_at': result.intent.expires_at.isoformat(),
        },
    )
    return AssistedPaymentIntentResult(
        intent=result.intent,
        operation_id=str(operation.operation_id),
        recovered=False,
    )


@transaction.atomic
def assisted_payment_intent_for_actor(*, solicitud_id, actor):
    current = _authorized_financial_actor(actor)
    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current,
    )
    operation = (
        SolicitudTecnicaAsistidaOperacion.objects.select_related(
            'payment_intent__slot_hold',
            'payment_intent__confirmed_turno',
        )
        .prefetch_related(
            'payment_intent__lines',
            'payment_intent__payments',
            'payment_intent__reconciliation_cases',
            'payment_intent__provider_attempts__provider_events',
        )
        .filter(
            solicitud=solicitud,
            actor=current,
            command=SolicitudTecnicaAsistidaOperacion.Command.INTENT,
            payment_intent__isnull=False,
        )
        .order_by('-created_at', '-pk')
        .first()
    )
    if operation is None:
        raise AssistedTechnicalBookingNotFound(
            'ASSISTED_PAYMENT_INTENT_NOT_FOUND',
            'No existe un Intent asistido disponible en este alcance.',
        )
    return operation.payment_intent, str(operation.operation_id)
