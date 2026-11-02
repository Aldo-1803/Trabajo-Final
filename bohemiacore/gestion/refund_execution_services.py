"""Ejecución durable e idempotente de refunds autorizados (BH-058 F7.3)."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import uuid

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .financial_resolution_services import (
    FinancialResolutionConflict,
    FinancialResolutionInvalid,
    FinancialResolutionNotFound,
    _lock_case_context,
    _operation_key,
    _require_financial_reviewer,
)
from .models import (
    Auditoria,
    FinancialAdjustment,
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
    FinancialResolutionDecision,
    FinancialResolutionRequest,
    Pago,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
)
from .payment_providers import (
    PaymentProviderError,
    RefundRequest,
    get_payment_provider,
)


FINANCIAL_REFUND_OPERATION_CREATED = 'FINANCIAL_REFUND_OPERATION_CREATED'
FINANCIAL_REFUND_SUBMISSION_RECORDED = 'FINANCIAL_REFUND_SUBMISSION_RECORDED'
FINANCIAL_REFUND_RECOVERY_RECORDED = 'FINANCIAL_REFUND_RECOVERY_RECORDED'
ACTIVE_REFUND_STATUSES = (
    FinancialRefundOperation.Status.PENDING,
    FinancialRefundOperation.Status.SUBMITTED,
    FinancialRefundOperation.Status.UNKNOWN,
)


@dataclass(frozen=True)
class FinancialRefundExecutionResult:
    operation: FinancialRefundOperation
    created: bool
    provider_called: bool


@dataclass(frozen=True)
class FinancialRefundRecoveryResult:
    operation: FinancialRefundOperation
    uniquely_recovered: bool


def _fingerprint(payload):
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
        default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _amount_text(value):
    return format(Decimal(value).quantize(Decimal('0.01')), 'f')


def _event(*, operation, event_type, actor, suffix, payload):
    return FinancialRefundOperationEvent.objects._create_from_service(
        operation=operation,
        event_type=event_type,
        actor=actor,
        operation_key=f'financial-refund:{operation.public_id}:{suffix}',
        payload=payload,
        created_at=timezone.now(),
    )


def _audit_created(operation):
    Auditoria.objects.create(
        tabla=FINANCIAL_REFUND_OPERATION_CREATED,
        registro_id=operation.pk,
        usuario=operation.created_by,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': FINANCIAL_REFUND_OPERATION_CREATED,
            'operation_public_id': str(operation.public_id),
            'decision_public_id': str(operation.decision.public_id),
            'case_public_id': str(
                operation.decision.resolution_request.case.public_id
            ),
            'payment_public_id': str(operation.payment.public_id),
            'amount': str(operation.amount),
            'currency': operation.currency,
            'payment_method': operation.payment_method,
            'provider': operation.provider,
            'status': operation.status,
            'effect': 'NO_FINANCIAL_OR_BUSINESS_EFFECT',
        },
    )


def _audit_submission(operation, event_name, actor):
    Auditoria.objects.create(
        tabla=FINANCIAL_REFUND_SUBMISSION_RECORDED,
        registro_id=operation.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior=None,
        valor_nuevo={
            'event': event_name,
            'operation_public_id': str(operation.public_id),
            'status': operation.status,
            'provider': operation.provider,
            'provider_order_id': operation.provider_order_id,
            'provider_transaction_id': operation.provider_transaction_id,
            'external_refund_id': operation.external_refund_id,
            'provider_status': operation.provider_status,
            'error_code': operation.error_code,
            'effect': 'NO_CONFIRMATION_NO_FINANCIAL_OR_BUSINESS_EFFECT',
        },
    )


def _baseline_refund_ids(attempt_id):
    identifiers = set()
    snapshots = ProviderEvent.objects.filter(
        attempt_id=attempt_id,
        status=ProviderEvent.Status.VERIFIED,
    ).values_list('provider_snapshot', flat=True)
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        transactions = snapshot.get('transactions') or snapshot
        refunds = (
            transactions.get('refunds', [])
            if isinstance(transactions, dict)
            else []
        )
        if isinstance(refunds, dict):
            refunds = [refunds]
        if isinstance(refunds, list):
            identifiers.update(
                str(item.get('id'))
                for item in refunds
                if isinstance(item, dict) and item.get('id')
            )
    return sorted(identifiers)


def _validate_payment_for_refund(*, locked, decision, payment_public_id):
    payment = next(
        (
            item for item in locked.case_payments
            if str(item.public_id) == str(payment_public_id)
        ),
        None,
    )
    if payment is None:
        raise FinancialResolutionNotFound(
            'El Pago de origen no pertenece a la resolución.',
        )
    if payment.status != Pago.Status.RECONCILED:
        raise FinancialResolutionConflict(
            'El Pago de origen no está conciliado.',
            code='REFUND_PAYMENT_NOT_RECONCILED',
        )
    if payment.currency != decision.currency:
        raise FinancialResolutionInvalid(
            'La moneda del Pago no coincide con la autorización.',
            code='REFUND_PAYMENT_CURRENCY_MISMATCH',
            field='payment_public_id',
        )
    if decision.authorized_amount > payment.monto:
        raise FinancialResolutionInvalid(
            'El importe autorizado supera el Pago seleccionado.',
            code='REFUND_AMOUNT_EXCEEDS_PAYMENT',
            field='payment_public_id',
        )
    if payment.fecha_pago < timezone.now() - timedelta(days=180):
        raise FinancialResolutionConflict(
            'El Pago excede el plazo documentado por el proveedor.',
            code='PROVIDER_REFUND_WINDOW_EXPIRED',
        )
    if payment.metodo_pago != Pago.Method.MERCADO_PAGO:
        raise FinancialResolutionConflict(
            'El medio manual no tiene un contrato ejecutable verificable.',
            code='MANUAL_REFUND_EXECUTION_UNSUPPORTED',
        )
    if (
        payment.provider_code
        != ProviderPaymentAttempt.Provider.MERCADO_PAGO
        or payment.provider_attempt_id is None
        or not payment.provider_payment_id
    ):
        raise FinancialResolutionConflict(
            'El Pago no conserva identidad completa de Mercado Pago.',
            code='PROVIDER_REFUND_IDENTITY_INCOMPLETE',
        )
    attempt = payment.provider_attempt
    if not attempt.provider_order_id:
        raise FinancialResolutionConflict(
            'El Pago no está vinculado a una Order recuperable.',
            code='PROVIDER_ORDER_ID_MISSING',
        )
    same_context = (
        payment.payment_intent_id == attempt.payment_intent_id
        if payment.payment_intent_id is not None
        else payment.orden_id == attempt.order_id
    )
    if not same_context:
        raise FinancialResolutionConflict(
            'El Pago y la Order no comparten contexto.',
            code='PROVIDER_REFUND_CONTEXT_MISMATCH',
        )
    already_reserved = (
        FinancialRefundOperation.objects.filter(
            payment=payment,
            status__in=ACTIVE_REFUND_STATUSES,
        ).aggregate(total=models.Sum('amount'))['total']
        or Decimal('0.00')
    )
    confirmed_debits = (
        FinancialAdjustment.objects.filter(
            payment=payment,
            effect=FinancialAdjustment.Effect.DEBIT,
        ).aggregate(total=models.Sum('amount'))['total']
        or Decimal('0.00')
    )
    confirmed_credits = (
        FinancialAdjustment.objects.filter(
            payment=payment,
            effect=FinancialAdjustment.Effect.CREDIT,
        ).aggregate(total=models.Sum('amount'))['total']
        or Decimal('0.00')
    )
    if (
        already_reserved
        + confirmed_debits
        - confirmed_credits
        + decision.authorized_amount
        > payment.monto
    ):
        raise FinancialResolutionConflict(
            'Las operaciones existentes superan el saldo ejecutable del Pago.',
            code='REFUND_AMOUNT_EXCEEDS_AVAILABLE_PAYMENT',
        )
    return payment, attempt


@transaction.atomic
def _prepare_operation(
    *,
    case_public_id,
    actor,
    payment_public_id,
    idempotency_key,
):
    _require_financial_reviewer(actor)
    key = _operation_key(idempotency_key)
    locked = _lock_case_context(case_public_id)
    if locked.case.status != PaymentReconciliationCase.Status.OPEN:
        raise FinancialResolutionConflict(
            'El caso no está abierto.',
            code='FINANCIAL_CASE_NOT_OPEN',
        )
    try:
        resolution_request = FinancialResolutionRequest.objects.select_for_update().get(
            case=locked.case,
        )
        decision = FinancialResolutionDecision.objects.select_for_update().get(
            resolution_request=resolution_request,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
        )
    except FinancialResolutionRequest.DoesNotExist as exc:
        raise FinancialResolutionConflict(
            'El caso no tiene una solicitud financiera.',
            code='FINANCIAL_REQUEST_REQUIRED',
        ) from exc
    except FinancialResolutionDecision.DoesNotExist as exc:
        raise FinancialResolutionConflict(
            'La resolución no tiene una aprobación de refund vigente.',
            code='APPROVED_REFUND_DECISION_REQUIRED',
        ) from exc
    if resolution_request.status != FinancialResolutionRequest.Status.DECIDED:
        raise FinancialResolutionConflict(
            'La solicitud no tiene una decisión final vigente.',
            code='APPROVED_REFUND_DECISION_REQUIRED',
        )

    key_match = FinancialRefundOperation.objects.select_for_update().filter(
        created_by=actor,
        client_idempotency_key=key,
    ).first()
    existing = FinancialRefundOperation.objects.select_for_update().filter(
        decision=decision,
    ).first()
    if key_match is not None and (
        existing is None or key_match.pk != existing.pk
    ):
        raise FinancialResolutionConflict(
            'La clave idempotente ya fue usada con otra operación.',
            code='IDEMPOTENCY_KEY_REUSED',
        )
    if existing is not None:
        if str(existing.payment.public_id) != str(payment_public_id):
            raise FinancialResolutionConflict(
                'La aprobación ya está vinculada a otro Pago de origen.',
                code='REFUND_OPERATION_ALREADY_EXISTS',
            )
        return existing, False

    payment, attempt = _validate_payment_for_refund(
        locked=locked,
        decision=decision,
        payment_public_id=payment_public_id,
    )
    public_id = uuid.uuid4()
    provider_key = f'bh-f73-{public_id.hex}'
    fingerprint = _fingerprint({
        'decision_public_id': str(decision.public_id),
        'payment_public_id': str(payment.public_id),
        'amount': _amount_text(decision.authorized_amount),
        'currency': decision.currency,
        'provider': payment.provider_code,
        'provider_order_id': attempt.provider_order_id,
        'provider_transaction_id': payment.provider_payment_id,
    })
    now = timezone.now()
    try:
        operation = FinancialRefundOperation.objects._create_from_service(
            public_id=public_id,
            decision=decision,
            payment=payment,
            amount=decision.authorized_amount,
            currency=decision.currency,
            payment_method=payment.metodo_pago,
            provider=FinancialRefundOperation.Provider.MERCADO_PAGO,
            status=FinancialRefundOperation.Status.PENDING,
            client_idempotency_key=key,
            provider_idempotency_key=provider_key,
            request_fingerprint=fingerprint,
            provider_order_id=attempt.provider_order_id,
            provider_transaction_id=payment.provider_payment_id,
            baseline_refund_ids=_baseline_refund_ids(attempt.pk),
            created_by=actor,
            created_at=now,
        )
    except IntegrityError as exc:
        raise FinancialResolutionConflict(
            'La operación compitió con otra ejecución.',
            code='REFUND_OPERATION_CONCURRENCY_CONFLICT',
        ) from exc
    _event(
        operation=operation,
        event_type=FinancialRefundOperationEvent.Type.CREATED,
        actor=actor,
        suffix='created',
        payload={
            'decision_public_id': str(decision.public_id),
            'payment_public_id': str(payment.public_id),
            'amount': str(operation.amount),
            'currency': operation.currency,
            'provider': operation.provider,
            'provider_order_id': operation.provider_order_id,
            'provider_transaction_id': operation.provider_transaction_id,
            'effect': 'NO_FINANCIAL_OR_BUSINESS_EFFECT',
        },
    )
    _audit_created(operation)
    return operation, True


@transaction.atomic
def _claim_submission(operation_id, actor):
    operation = FinancialRefundOperation.objects.select_for_update().get(
        pk=operation_id,
    )
    if operation.status != FinancialRefundOperation.Status.PENDING:
        return operation, False
    now = timezone.now()
    transitioned = FinancialRefundOperation.objects._transition(
        operation_id=operation.pk,
        from_statuses=(FinancialRefundOperation.Status.PENDING,),
        status=FinancialRefundOperation.Status.SUBMITTED,
        submission_started_at=now,
        provider_call_count=models.F('provider_call_count') + 1,
        error_code='',
        error_detail='',
        updated_at=now,
    )
    if transitioned != 1:
        return (
            FinancialRefundOperation.objects.get(pk=operation.pk),
            False,
        )
    operation.status = FinancialRefundOperation.Status.SUBMITTED
    operation.submission_started_at = now
    operation.provider_call_count += 1
    _event(
        operation=operation,
        event_type=FinancialRefundOperationEvent.Type.SUBMISSION_STARTED,
        actor=actor,
        suffix='submission-started',
        payload={
            'provider': operation.provider,
            'provider_order_id': operation.provider_order_id,
            'provider_transaction_id': operation.provider_transaction_id,
            'provider_call_count': operation.provider_call_count,
            'effect': 'REQUEST_CLAIMED_NO_CONFIRMATION',
        },
    )
    return operation, True


@transaction.atomic
def _record_provider_result(operation_id, actor, *, submitted=None, error=None):
    operation = FinancialRefundOperation.objects.select_for_update().select_related(
        'decision__resolution_request__case',
        'payment',
        'created_by',
    ).get(pk=operation_id)
    if operation.status != FinancialRefundOperation.Status.SUBMITTED:
        return operation
    now = timezone.now()
    if error is not None:
        next_status = (
            FinancialRefundOperation.Status.UNKNOWN
            if error.outcome_unknown
            else FinancialRefundOperation.Status.FAILED
        )
        event_type = (
            FinancialRefundOperationEvent.Type.UNKNOWN
            if error.outcome_unknown
            else FinancialRefundOperationEvent.Type.FAILED
        )
        evidence = {
            'provider': operation.provider,
            'provider_order_id': operation.provider_order_id,
            'provider_transaction_id': operation.provider_transaction_id,
            'outcome_unknown': bool(error.outcome_unknown),
        }
        values = {
            'status': next_status,
            'response_received_at': now,
            'latest_evidence': evidence,
            'error_code': str(error.code)[:50],
            'error_detail': str(error.detail)[:200],
            'updated_at': now,
        }
    else:
        next_status = FinancialRefundOperation.Status.SUBMITTED
        event_type = FinancialRefundOperationEvent.Type.SUBMITTED
        evidence = dict(submitted.evidence)
        values = {
            'status': next_status,
            'external_refund_id': submitted.provider_refund_id,
            'provider_status': submitted.provider_status[:50],
            'provider_status_detail': submitted.provider_status_detail[:100],
            'response_received_at': now,
            'latest_evidence': evidence,
            'error_code': '',
            'error_detail': '',
            'updated_at': now,
        }
    FinancialRefundOperation.objects._transition(
        operation_id=operation.pk,
        from_statuses=(FinancialRefundOperation.Status.SUBMITTED,),
        **values,
    )
    for name, value in values.items():
        if name != 'updated_at':
            setattr(operation, name, value)
    _event(
        operation=operation,
        event_type=event_type,
        actor=actor,
        suffix=f'response-{uuid.uuid4().hex}',
        payload={
            'status': next_status,
            'provider_status': operation.provider_status,
            'external_refund_id': operation.external_refund_id,
            'error_code': operation.error_code,
            'evidence': evidence,
            'effect': 'NO_CONFIRMATION_NO_FINANCIAL_OR_BUSINESS_EFFECT',
        },
    )
    _audit_submission(operation, event_type, actor)
    return operation


def execute_authorized_refund(
    *,
    case_public_id,
    actor,
    payment_public_id,
    idempotency_key,
):
    operation, created = _prepare_operation(
        case_public_id=case_public_id,
        actor=actor,
        payment_public_id=payment_public_id,
        idempotency_key=idempotency_key,
    )
    operation, claimed = _claim_submission(operation.pk, actor)
    if not claimed:
        return FinancialRefundExecutionResult(operation, created, False)
    request = RefundRequest(
        provider_order_id=operation.provider_order_id,
        provider_transaction_id=operation.provider_transaction_id,
        idempotency_key=operation.provider_idempotency_key,
        amount=_amount_text(operation.amount),
        currency=operation.currency,
    )
    submitted = None
    error = None
    try:
        submitted = get_payment_provider(operation.provider).submit_refund(request)
    except PaymentProviderError as exc:
        error = exc
    operation = _record_provider_result(
        operation.pk,
        actor,
        submitted=submitted,
        error=error,
    )
    return FinancialRefundExecutionResult(operation, created, True)


@transaction.atomic
def get_refund_operation(*, case_public_id, actor):
    _require_financial_reviewer(actor)
    locked = _lock_case_context(case_public_id)
    try:
        return FinancialRefundOperation.objects.select_for_update().select_related(
            'decision',
            'payment',
            'created_by',
        ).prefetch_related('events__actor').get(
            decision__resolution_request__case=locked.case,
        )
    except FinancialRefundOperation.DoesNotExist as exc:
        raise FinancialResolutionNotFound(
            'La operación de refund no existe.',
        ) from exc


def _refund_decimal(value):
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return None


@transaction.atomic
def _record_recovery(operation_id, actor, *, snapshot=None, provider_error=None):
    operation = FinancialRefundOperation.objects.select_for_update().select_related(
        'created_by',
    ).get(pk=operation_id)
    if operation.status not in {
        FinancialRefundOperation.Status.SUBMITTED,
        FinancialRefundOperation.Status.UNKNOWN,
    }:
        return operation, False
    now = timezone.now()
    matches = []
    evidence = {
        'provider': operation.provider,
        'provider_order_id': operation.provider_order_id,
    }
    if snapshot is not None:
        baseline = set(operation.baseline_refund_ids or [])
        order_identity_matches = (
            snapshot.provider_order_id == operation.provider_order_id
        )
        if order_identity_matches:
            matches = [
                refund for refund in snapshot.refunds
                if refund.get('transaction_id')
                == operation.provider_transaction_id
                and _refund_decimal(refund.get('amount')) == operation.amount
                and refund.get('id')
                and (
                    refund.get('id') == operation.external_refund_id
                    if operation.external_refund_id
                    else refund.get('id') not in baseline
                )
            ]
        evidence.update({
            'returned_order_id': snapshot.provider_order_id,
            'order_identity_matches': order_identity_matches,
            'order_status': snapshot.status,
            'order_status_detail': snapshot.status_detail,
            'last_updated_date': snapshot.last_updated_date,
            'matching_refund_count': len(matches),
            'matching_refunds': list(matches[:2]),
        })
    else:
        evidence.update({
            'query_error_code': str(provider_error.code)[:50],
            'query_outcome_unknown': bool(provider_error.outcome_unknown),
        })

    uniquely_recovered = len(matches) == 1
    if uniquely_recovered:
        refund = matches[0]
        next_status = FinancialRefundOperation.Status.SUBMITTED
        values = {
            'status': next_status,
            'external_refund_id': str(refund['id'])[:128],
            'provider_status': str(refund.get('status') or '')[:50],
            'provider_status_detail': snapshot.status_detail[:100],
            'latest_evidence': evidence,
            'last_recovery_at': now,
            'error_code': '',
            'error_detail': '',
            'updated_at': now,
        }
    else:
        next_status = FinancialRefundOperation.Status.UNKNOWN
        values = {
            'status': next_status,
            'latest_evidence': evidence,
            'last_recovery_at': now,
            'error_code': 'REFUND_NOT_UNIQUELY_RECOVERABLE',
            'error_detail': (
                'La consulta oficial no identifica un único refund; '
                'requiere revisión manual sin reenvío.'
            ),
            'updated_at': now,
        }
    FinancialRefundOperation.objects._transition(
        operation_id=operation.pk,
        from_statuses=(
            FinancialRefundOperation.Status.SUBMITTED,
            FinancialRefundOperation.Status.UNKNOWN,
        ),
        **values,
    )
    for name, value in values.items():
        if name != 'updated_at':
            setattr(operation, name, value)
    _event(
        operation=operation,
        event_type=FinancialRefundOperationEvent.Type.RECOVERY_OBSERVED,
        actor=actor,
        suffix=f'recovery-{uuid.uuid4().hex}',
        payload={
            'status': next_status,
            'uniquely_recovered': uniquely_recovered,
            'evidence': evidence,
            'effect': 'NO_CONFIRMATION_NO_RETRY_NO_FINANCIAL_EFFECT',
        },
    )
    Auditoria.objects.create(
        tabla=FINANCIAL_REFUND_RECOVERY_RECORDED,
        registro_id=operation.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior=None,
        valor_nuevo={
            'event': FINANCIAL_REFUND_RECOVERY_RECORDED,
            'operation_public_id': str(operation.public_id),
            'status': next_status,
            'uniquely_recovered': uniquely_recovered,
            'external_refund_id': operation.external_refund_id,
            'effect': 'NO_CONFIRMATION_NO_RETRY_NO_FINANCIAL_EFFECT',
        },
    )
    return operation, uniquely_recovered


def recover_refund_operation(*, case_public_id, actor):
    operation = get_refund_operation(
        case_public_id=case_public_id,
        actor=actor,
    )
    if operation.status not in {
        FinancialRefundOperation.Status.SUBMITTED,
        FinancialRefundOperation.Status.UNKNOWN,
    }:
        return FinancialRefundRecoveryResult(operation, False)
    snapshot = None
    provider_error = None
    try:
        snapshot = get_payment_provider(operation.provider).fetch_provider_order(
            operation.provider_order_id,
        )
    except PaymentProviderError as exc:
        provider_error = exc
    operation, recovered = _record_recovery(
        operation.pk,
        actor,
        snapshot=snapshot,
        provider_error=provider_error,
    )
    return FinancialRefundRecoveryResult(operation, recovered)
