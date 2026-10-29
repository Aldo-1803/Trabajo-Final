"""Conciliación financiera de snapshots verificados de proveedor (BH-058 C2b)."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    Auditoria,
    CompromisoStock,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    SlotHold,
)
from .payment_confirmation_services import (
    PaymentConfirmationResult,
    _lock_confirmation_graph,
    approve_payment_intent_and_confirm_booking,
)
from .payment_intent_services import _expire_locked_intent
from .slot_hold_clock import database_now


EXTERNAL_PAYMENT_RECONCILED = 'EXTERNAL_PAYMENT_RECONCILED'
EXTERNAL_PAYMENT_REVIEW_REQUIRED = 'EXTERNAL_PAYMENT_REVIEW_REQUIRED'
PROVIDER_EVENT_RECONCILED = 'PROVIDER_EVENT_RECONCILED'
ORDER_PAYMENT_RECONCILED = 'ORDER_PAYMENT_RECONCILED'

PROVIDER = ProviderPaymentAttempt.Provider.MERCADO_PAGO
PROCESSED_PAYMENT_STATUS = 'processed'
ACCREDITED_DETAIL = 'accredited'
NON_FINANCIAL_ORDER_STATUSES = {
    'created',
    'processing',
    'action_required',
    'failed',
    'canceled',
    'cancelled',
}


class ProviderReconciliationError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(detail)


class ProviderReconciliationNotFound(ProviderReconciliationError):
    def __init__(self):
        super().__init__('PROVIDER_EVENT_NOT_FOUND', 'El evento no existe.')


class ProviderReconciliationConflict(ProviderReconciliationError):
    pass


class ProviderPaymentIdentityConflict(ProviderReconciliationConflict):
    def __init__(self, payment):
        self.payment = payment
        super().__init__(
            'PROVIDER_PAYMENT_IDENTITY_CONFLICT',
            'El pago externo ya existe con otra obligación, Attempt o importe.',
        )


@dataclass(frozen=True)
class ProviderReconciliationResult:
    event: ProviderEvent
    payments: tuple[Pago, ...]
    reconciliation_case: PaymentReconciliationCase | None
    confirmation: PaymentConfirmationResult | None
    changed: bool
    decision: str
    effect: str


def _decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderReconciliationConflict(
            'INVALID_PROVIDER_SNAPSHOT',
            f'El campo {field} no es un importe válido.',
        ) from exc
    if result <= 0:
        raise ProviderReconciliationConflict(
            'INVALID_PROVIDER_SNAPSHOT',
            f'El campo {field} debe ser positivo.',
        )
    return result


def _provider_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None or timezone.is_naive(parsed):
        return None
    return parsed


def _operation_key(prefix, *values):
    digest = hashlib.sha256(
        '|'.join(str(value) for value in values).encode('utf-8')
    ).hexdigest()
    return f'{prefix}:{digest}'


def _payment_key(provider_payment_id):
    return _operation_key('provider-payment', PROVIDER, provider_payment_id)


def _load_event(event_id):
    try:
        event = ProviderEvent.objects.select_related(
            'attempt__payment_intent__slot_hold',
            'attempt__order',
        ).get(pk=event_id)
    except ProviderEvent.DoesNotExist as exc:
        raise ProviderReconciliationNotFound() from exc
    if event.status != ProviderEvent.Status.VERIFIED:
        raise ProviderReconciliationConflict(
            'PROVIDER_EVENT_NOT_VERIFIED',
            'Sólo se concilian eventos autenticados y verificados.',
        )
    if event.attempt_id is None:
        raise ProviderReconciliationConflict(
            'PROVIDER_ATTEMPT_NOT_LINKED',
            'El evento no está asociado a una obligación verificable.',
        )
    return event


def _validate_locked_event(event, attempt):
    if event.status != ProviderEvent.Status.VERIFIED:
        raise ProviderReconciliationConflict(
            'PROVIDER_EVENT_NOT_VERIFIED',
            'El estado del evento cambió antes de conciliar.',
        )
    if event.attempt_id != attempt.pk or event.provider != attempt.provider:
        raise ProviderReconciliationConflict(
            'PROVIDER_CONTEXT_MISMATCH',
            'El evento y el Attempt no comparten identidad.',
        )
    snapshot = event.provider_snapshot
    if not isinstance(snapshot, dict):
        raise ProviderReconciliationConflict(
            'INVALID_PROVIDER_SNAPSHOT',
            'El snapshot verificado no es válido.',
        )
    expected_prefix = f'bh:c1:{attempt.context.lower()}:'
    checks = (
        str(snapshot.get('id') or '') == event.provider_resource_id,
        event.provider_resource_id == attempt.provider_order_id,
        str(snapshot.get('external_reference') or '')
        == attempt.external_reference,
        attempt.external_reference.startswith(expected_prefix),
        str(snapshot.get('currency') or '').upper() == attempt.currency,
    )
    if not all(checks):
        raise ProviderReconciliationConflict(
            'VERIFIED_SNAPSHOT_MISMATCH',
            'El snapshot dejó de coincidir con la obligación persistida.',
        )
    if _decimal(snapshot.get('total_amount'), 'total_amount') != attempt.amount:
        raise ProviderReconciliationConflict(
            'VERIFIED_SNAPSHOT_MISMATCH',
            'El total de la Order no coincide con el Attempt.',
        )
    return snapshot


def _snapshot_is_stale(event, snapshot):
    current = _provider_datetime(snapshot.get('last_updated_date'))
    if current is None:
        return False
    previous_events = ProviderEvent.objects.filter(
        attempt_id=event.attempt_id,
    ).exclude(
        reconciliation_status=(
            ProviderEvent.ReconciliationStatus.NOT_EVALUATED
        )
    ).exclude(pk=event.pk).only('provider_snapshot')
    for previous in previous_events:
        previous_date = _provider_datetime(
            (previous.provider_snapshot or {}).get('last_updated_date')
        )
        if previous_date is not None and previous_date > current:
            return True
    return False


def _transaction_rows(snapshot, name):
    rows = snapshot.get(name) or []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ProviderReconciliationConflict(
            'INVALID_PROVIDER_SNAPSHOT',
            f'La colección {name} no es válida.',
        )
    return rows


def _eligible_payments(snapshot):
    return [
        row for row in _transaction_rows(snapshot, 'payments')
        if str(row.get('status') or '').lower() == PROCESSED_PAYMENT_STATUS
        and str(row.get('status_detail') or '').lower() == ACCREDITED_DETAIL
    ]


def _payment_occurred_at(row):
    return (
        _provider_datetime(row.get('last_updated_date'))
        or _provider_datetime(row.get('created_date'))
    )


def _same_external_payment(payment, *, attempt, row, amount):
    expected_context = (
        payment.payment_intent_id == attempt.payment_intent_id
        if attempt.context == ProviderPaymentAttempt.Context.BOOKING
        else payment.orden_id == attempt.order_id
    )
    return bool(
        expected_context
        and payment.provider_code == attempt.provider
        and payment.provider_payment_id == str(row.get('id') or '')
        and payment.provider_attempt_id == attempt.pk
        and payment.monto == amount
        and payment.currency == attempt.currency
        and payment.metodo_pago == Pago.Method.MERCADO_PAGO
    )


def _create_or_get_payment(
    *,
    event,
    attempt,
    row,
    amount,
    status,
    purpose,
    reason='',
):
    provider_payment_id = str(row.get('id') or '').strip()
    if not provider_payment_id or len(provider_payment_id) > 128:
        raise ProviderReconciliationConflict(
            'PROVIDER_PAYMENT_ID_INVALID',
            'El pago oficial no tiene una identidad utilizable.',
        )
    existing = Pago.objects.select_for_update().filter(
        provider_code=attempt.provider,
        provider_payment_id=provider_payment_id,
    ).first()
    if existing is not None:
        if not _same_external_payment(
            existing,
            attempt=attempt,
            row=row,
            amount=amount,
        ):
            raise ProviderPaymentIdentityConflict(existing)
        return existing, False

    now = database_now()
    occurred_at = _payment_occurred_at(row)
    values = {
        'payment_intent_id': attempt.payment_intent_id,
        'orden_id': attempt.order_id,
        'turno_id': None,
        'monto': amount,
        'currency': attempt.currency,
        'metodo_pago': Pago.Method.MERCADO_PAGO,
        'purpose': purpose,
        'status': status,
        'transaccion_id': f'{attempt.provider}:{provider_payment_id}',
        'fecha_pago': occurred_at or event.event_created_at or event.received_at,
        'recorded_at': now,
        'recorded_by': None,
        'reconciled_at': now if status == Pago.Status.RECONCILED else None,
        'reconciled_by': None,
        'manual_reference': '',
        'receipt_sha256': '',
        'idempotency_key': _payment_key(provider_payment_id),
        'terminal_reason': reason,
        'es_sena': purpose == Pago.Purpose.CONFIRMATION,
        'provider_code': attempt.provider,
        'provider_payment_id': provider_payment_id,
        'provider_attempt': attempt,
        'provider_event': event,
        'provider_occurred_at': occurred_at,
        'provider_snapshot': {
            'id': provider_payment_id,
            'amount': str(row.get('amount') or ''),
            'paid_amount': str(row.get('paid_amount') or ''),
            'confirmed_amount': str(row.get('confirmed_amount') or ''),
            'status': str(row.get('status') or '')[:50],
            'status_detail': str(row.get('status_detail') or '')[:100],
            'created_date': str(row.get('created_date') or '')[:64],
            'last_updated_date': str(row.get('last_updated_date') or '')[:64],
        },
    }
    try:
        with transaction.atomic():
            payment = Pago.objects._create_external_from_service(**values)
    except IntegrityError:
        payment = Pago.objects.select_for_update().filter(
            provider_code=attempt.provider,
            provider_payment_id=provider_payment_id,
        ).first()
        if payment is None or not _same_external_payment(
            payment,
            attempt=attempt,
            row=row,
            amount=amount,
        ):
            if payment is None:
                raise ProviderReconciliationConflict(
                    'PROVIDER_PAYMENT_IDENTITY_CONFLICT',
                    'La identidad del pago externo entró en conflicto.',
                )
            raise ProviderPaymentIdentityConflict(payment)
        return payment, False
    _audit_payment_created(payment, event, attempt)
    return payment, True


def _audit_payment_created(payment, event, attempt):
    Auditoria.objects.create(
        tabla=EXTERNAL_PAYMENT_RECONCILED,
        registro_id=payment.pk,
        usuario=None,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': EXTERNAL_PAYMENT_RECONCILED,
            'payment_id': payment.pk,
            'payment_public_id': str(payment.public_id),
            'provider': payment.provider_code,
            'provider_payment_id': payment.provider_payment_id,
            'provider_order_id': event.provider_resource_id,
            'provider_event_id': event.pk,
            'attempt_id': attempt.pk,
            'context': attempt.context,
            'amount': str(payment.monto),
            'currency': payment.currency,
            'decision': payment.status,
            'effect': 'FINANCIAL_FACT_RECORDED',
            'event_at': payment.recorded_at.isoformat(),
        },
    )


def _create_case(
    *,
    event,
    attempt,
    payments,
    case_type,
    reason_code,
    detail,
    fingerprint,
):
    key = _operation_key(
        'provider-case',
        attempt.provider,
        attempt.pk,
        reason_code,
        fingerprint,
    )
    existing = PaymentReconciliationCase.objects.filter(operation_key=key).first()
    if existing is not None:
        return existing, False
    case = PaymentReconciliationCase.objects._create_from_service(
        payment_intent_id=attempt.payment_intent_id,
        slot_hold_id=(
            attempt.payment_intent.slot_hold_id
            if attempt.payment_intent_id
            else None
        ),
        order_id=attempt.order_id,
        turno=None,
        provider_attempt=attempt,
        provider_event=event,
        case_type=case_type,
        status=PaymentReconciliationCase.Status.OPEN,
        reason_code=reason_code,
        operation_key=key,
        details={
            'detail': detail,
            'provider': attempt.provider,
            'provider_order_id': event.provider_resource_id,
            'provider_event_id': event.pk,
            'context': attempt.context,
            'payment_ids': [payment.pk for payment in payments],
        },
        created_by=None,
        created_at=database_now(),
    )
    case.payments.add(*(payment.pk for payment in payments))
    Auditoria.objects.create(
        tabla=EXTERNAL_PAYMENT_REVIEW_REQUIRED,
        registro_id=case.pk,
        usuario=None,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': EXTERNAL_PAYMENT_REVIEW_REQUIRED,
            'case_id': case.pk,
            'case_public_id': str(case.public_id),
            'provider_event_id': event.pk,
            'attempt_id': attempt.pk,
            'context': attempt.context,
            'reason_code': reason_code,
            'payment_ids': [payment.pk for payment in payments],
            'decision': 'REVIEW_REQUIRED',
            'effect': 'NO_AUTOMATIC_REVERSAL',
        },
    )
    return case, True


def _finish_event(
    *,
    event,
    attempt,
    payments,
    status,
    code,
    decision,
    effect,
):
    now = database_now()
    event.reconciliation_status = status
    if event.claim_token is None:
        event.reconciliation_attempts += 1
    event.reconciled_at = now
    event.reconciliation_code = code[:50]
    event.business_result = {
        'decision': decision,
        'effect': effect,
        'payment_ids': [payment.pk for payment in payments],
        'provider_payment_ids': [
            payment.provider_payment_id for payment in payments
        ],
        'provider_updated_at': str(
            (event.provider_snapshot or {}).get('last_updated_date') or ''
        ),
        'event_at': now.isoformat(),
    }
    event.save(update_fields=[
        'reconciliation_status',
        'reconciliation_attempts',
        'reconciled_at',
        'reconciliation_code',
        'business_result',
        'updated_at',
    ])
    if payments:
        event.financial_payments.add(*(payment.pk for payment in payments))
    if code != 'STALE_EVENT':
        attempt.last_reconciled_at = now
        attempt.last_provider_status = str(
            (event.provider_snapshot or {}).get('status') or ''
        )[:50]
        if status == ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED:
            if code == 'LATE_PAYMENT':
                attempt.reconciliation_status = (
                    ProviderPaymentAttempt.ReconciliationStatus.LATE
                )
            else:
                attempt.reconciliation_status = (
                    ProviderPaymentAttempt.ReconciliationStatus.REVIEW_REQUIRED
                )
        elif status == ProviderEvent.ReconciliationStatus.APPLIED:
            attempt.reconciliation_status = (
                ProviderPaymentAttempt.ReconciliationStatus.PARTIAL
                if effect in {
                    'BOOKING_THRESHOLD_PENDING',
                    'ORDER_PAYMENT_PARTIAL',
                }
                else ProviderPaymentAttempt.ReconciliationStatus.APPLIED
            )
        attempt.save(update_fields=[
            'last_reconciled_at',
            'last_provider_status',
            'reconciliation_status',
            'updated_at',
        ])
    Auditoria.objects.create(
        tabla=PROVIDER_EVENT_RECONCILED,
        registro_id=event.pk,
        usuario=None,
        accion='MODIFICACION',
        valor_anterior={
            'reconciliation_status': (
                ProviderEvent.ReconciliationStatus.NOT_EVALUATED
            )
        },
        valor_nuevo={
            'event': PROVIDER_EVENT_RECONCILED,
            'provider_event_id': event.pk,
            'attempt_id': attempt.pk,
            'context': attempt.context,
            'decision': decision,
            'effect': effect,
            'code': code,
            'payment_ids': [payment.pk for payment in payments],
            'event_at': now.isoformat(),
        },
    )


def _idempotent_result(event):
    payments = tuple(event.financial_payments.order_by('pk'))
    case = event.reconciliation_cases.order_by('pk').first()
    result = event.business_result or {}
    return ProviderReconciliationResult(
        event=event,
        payments=payments,
        reconciliation_case=case,
        confirmation=None,
        changed=False,
        decision=result.get('decision', event.reconciliation_status),
        effect=result.get('effect', ''),
    )


def _mark_ignored(event, attempt, code, effect):
    _finish_event(
        event=event,
        attempt=attempt,
        payments=(),
        status=ProviderEvent.ReconciliationStatus.IGNORED,
        code=code,
        decision='NO_FINANCIAL_EFFECT',
        effect=effect,
    )
    return ProviderReconciliationResult(
        event=event,
        payments=(),
        reconciliation_case=None,
        confirmation=None,
        changed=True,
        decision='NO_FINANCIAL_EFFECT',
        effect=effect,
    )


@transaction.atomic
def mark_verified_provider_event_for_review(event_id, *, reason_code, detail):
    """Persiste como revisión un error financiero tipado y no recuperable."""
    try:
        reference = ProviderEvent.objects.only('pk', 'attempt_id').get(pk=event_id)
    except ProviderEvent.DoesNotExist as exc:
        raise ProviderReconciliationNotFound() from exc
    if reference.attempt_id is None:
        raise ProviderReconciliationConflict(
            'PROVIDER_ATTEMPT_NOT_LINKED',
            'El evento no está asociado a una obligación verificable.',
        )
    attempt_reference = ProviderPaymentAttempt.objects.only(
        'pk',
        'context',
    ).get(pk=reference.attempt_id)
    if attempt_reference.context == ProviderPaymentAttempt.Context.BOOKING:
        _graph, attempt = _lock_booking_context(attempt_reference.pk)
    elif attempt_reference.context == ProviderPaymentAttempt.Context.ORDER:
        _order, _commitments, attempt = _lock_order_context(
            attempt_reference.pk
        )
    else:
        raise ProviderReconciliationConflict(
            'PROVIDER_CONTEXT_UNSUPPORTED',
            'El contexto del Attempt no está soportado.',
        )
    event = _locked_event(reference.pk)
    if event.reconciliation_status != ProviderEvent.ReconciliationStatus.NOT_EVALUATED:
        return _idempotent_result(event)
    if event.status != ProviderEvent.Status.VERIFIED:
        raise ProviderReconciliationConflict(
            'PROVIDER_EVENT_NOT_VERIFIED',
            'Sólo se concilian eventos autenticados y verificados.',
        )
    return _review_result(
        event=event,
        attempt=attempt,
        payments=tuple(event.financial_payments.order_by('pk')),
        reason_code=str(reason_code)[:50] or 'RECONCILIATION_REVIEW_REQUIRED',
        detail=str(detail)[:200],
    )


def _review_result(
    *,
    event,
    attempt,
    payments,
    reason_code,
    detail,
    case_type=PaymentReconciliationCase.Type.EXTERNAL_PAYMENT_REVIEW,
):
    fingerprint = ','.join(
        sorted(payment.provider_payment_id for payment in payments)
    ) or event.event_id
    case, case_created = _create_case(
        event=event,
        attempt=attempt,
        payments=payments,
        case_type=case_type,
        reason_code=reason_code,
        detail=detail,
        fingerprint=fingerprint,
    )
    _finish_event(
        event=event,
        attempt=attempt,
        payments=payments,
        status=ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED,
        code=reason_code,
        decision='REVIEW_REQUIRED',
        effect='NO_BUSINESS_EFFECT',
    )
    return ProviderReconciliationResult(
        event=event,
        payments=payments,
        reconciliation_case=case,
        confirmation=None,
        changed=case_created or bool(payments),
        decision='REVIEW_REQUIRED',
        effect='NO_BUSINESS_EFFECT',
    )


def _post_payment_change(snapshot):
    refunds = _transaction_rows(snapshot, 'refunds')
    chargebacks = _transaction_rows(snapshot, 'chargebacks')
    order_status = str(snapshot.get('status') or '').lower()
    return bool(refunds or chargebacks or order_status == 'refunded')


def _lock_booking_context(attempt_id):
    unlocked = ProviderPaymentAttempt.objects.only(
        'pk', 'payment_intent_id'
    ).get(pk=attempt_id)
    if unlocked.payment_intent_id is None:
        raise ProviderReconciliationConflict(
            'PROVIDER_CONTEXT_MISMATCH',
            'El Attempt BOOKING no tiene PaymentIntent.',
        )
    graph = _lock_confirmation_graph(unlocked.payment_intent_id)
    attempt = ProviderPaymentAttempt.objects.select_for_update().get(pk=attempt_id)
    return graph, attempt


def _lock_order_context(attempt_id):
    unlocked = ProviderPaymentAttempt.objects.only('pk', 'order_id').get(
        pk=attempt_id
    )
    if unlocked.order_id is None:
        raise ProviderReconciliationConflict(
            'PROVIDER_CONTEXT_MISMATCH',
            'El Attempt ORDER no tiene OrdenCompra.',
        )
    order = OrdenCompra.objects.select_for_update().get(pk=unlocked.order_id)
    attempt = ProviderPaymentAttempt.objects.select_for_update().get(pk=attempt_id)
    tuple(
        Pago.objects.select_for_update().filter(orden=order).order_by('pk')
    )
    commitments = tuple(
        CompromisoStock.objects.select_for_update()
        .filter(orden=order)
        .order_by('pk')
    )
    return order, commitments, attempt


def _locked_event(event_id):
    return ProviderEvent.objects.select_for_update().get(pk=event_id)


def _prepare_payment_rows(event, attempt, snapshot, *, pending_reason=''):
    rows = _eligible_payments(snapshot)
    payments = []
    created_any = False
    for row in rows:
        amount = _decimal(
            row.get('paid_amount') or row.get('confirmed_amount'),
            'paid_amount',
        )
        purpose = (
            Pago.Purpose.BALANCE
            if attempt.payment_intent_id
            and attempt.payment_intent.status == PaymentIntent.Status.APPROVED
            else Pago.Purpose.CONFIRMATION
        )
        payment, created = _create_or_get_payment(
            event=event,
            attempt=attempt,
            row=row,
            amount=amount,
            status=(
                Pago.Status.PENDING_RECONCILIATION
                if pending_reason
                else Pago.Status.RECONCILED
            ),
            purpose=purpose,
            reason=pending_reason,
        )
        payments.append(payment)
        created_any = created_any or created
    return tuple(payments), created_any


def _transaction_amount_mismatch(attempt, snapshot):
    for row in _eligible_payments(snapshot):
        amount = _decimal(
            row.get('paid_amount') or row.get('confirmed_amount'),
            'paid_amount',
        )
        if amount != attempt.amount:
            return True
    return False


def _new_candidate_total(rows, existing_payments):
    existing_ids = {
        payment.provider_payment_id for payment in existing_payments
        if payment.provider_payment_id
    }
    return sum(
        (
            _decimal(
                row.get('paid_amount') or row.get('confirmed_amount'),
                'paid_amount',
            )
            for row in rows
            if str(row.get('id') or '') not in existing_ids
        ),
        Decimal('0.00'),
    )


def _booking_is_late(intent, hold, rows, now):
    if intent.status == PaymentIntent.Status.APPROVED:
        return False
    if (
        intent.status in PaymentIntent.TERMINAL_FAILURE_STATUSES
        or intent.expires_at <= now
        or hold.state in {SlotHold.State.EXPIRED, SlotHold.State.RELEASED}
        or hold.expires_at <= now
    ):
        return True
    deadlines = (intent.expires_at, hold.expires_at)
    return any(
        occurred is not None and occurred > min(deadlines)
        for occurred in (_payment_occurred_at(row) for row in rows)
    )


def _reconcile_booking(event_id, attempt_id):
    graph, attempt = _lock_booking_context(attempt_id)
    _, hold, intent, _, locked_payments = graph
    event = _locked_event(event_id)
    if event.reconciliation_status != ProviderEvent.ReconciliationStatus.NOT_EVALUATED:
        return _idempotent_result(event)
    snapshot = _validate_locked_event(event, attempt)
    if _snapshot_is_stale(event, snapshot):
        return _mark_ignored(event, attempt, 'STALE_EVENT', 'STALE_SNAPSHOT_IGNORED')
    eligible = _eligible_payments(snapshot)
    existing_external = tuple(
        payment for payment in locked_payments if payment.provider_code
    )
    if _post_payment_change(snapshot):
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='POST_PAYMENT_CHANGE',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments or existing_external,
            reason_code='POST_PAYMENT_CHANGE',
            detail='El proveedor informó refund o contracargo.',
            case_type=PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
        )
    if not eligible:
        if existing_external:
            return _review_result(
                event=event,
                attempt=attempt,
                payments=existing_external,
                reason_code='PROVIDER_STATUS_REGRESSION',
                detail='Un pago ya registrado aparece en un estado no acreditado.',
                case_type=PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
            )
        order_status = str(snapshot.get('status') or '').lower()
        code = (
            'PAYMENT_NOT_ACCREDITED'
            if order_status in NON_FINANCIAL_ORDER_STATUSES
            else 'PAYMENT_EVIDENCE_MISSING'
        )
        return _mark_ignored(event, attempt, code, 'NO_ACCREDITED_PAYMENT')
    if _transaction_amount_mismatch(attempt, snapshot):
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='PAYMENT_AMOUNT_MISMATCH',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments,
            reason_code='PAYMENT_AMOUNT_MISMATCH',
            detail='El pago no coincide con el importe del Attempt.',
        )

    now = database_now()
    if _booking_is_late(intent, hold, eligible, now):
        if intent.status in PaymentIntent.ACTIVE_STATUSES:
            _expire_locked_intent(intent=intent, hold=hold, actor=None, now=now)
            intent.refresh_from_db()
            hold.refresh_from_db()
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='LATE_PAYMENT',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments,
            reason_code='LATE_PAYMENT',
            detail='El pago no puede aplicarse a un Intent/HOLD vigente.',
            case_type=PaymentReconciliationCase.Type.LATE_PAYMENT,
        )

    reconciled_before = sum(
        (
            payment.monto
            for payment in locked_payments
            if payment.status == Pago.Status.RECONCILED
        ),
        Decimal('0.00'),
    )
    candidate_total = _new_candidate_total(eligible, existing_external)
    if reconciled_before + candidate_total > intent.total_amount_snapshot:
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='PAYMENT_OVERPAYMENT',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments,
            reason_code='PAYMENT_OVERPAYMENT',
            detail='Aplicar el pago superaría el total del Intent.',
        )

    payments, created = _prepare_payment_rows(event, attempt, snapshot)
    confirmation = approve_payment_intent_and_confirm_booking(
        intent_id=intent.pk,
        actor=None,
    )
    intent.refresh_from_db()
    if confirmation.reconciliation_case is not None:
        PaymentReconciliationCase.objects._link_provider_context(
            case_id=confirmation.reconciliation_case.pk,
            attempt_id=attempt.pk,
            event_id=event.pk,
        )
        confirmation.reconciliation_case.refresh_from_db()
    if (
        not confirmation.threshold_reached
        and intent.status == PaymentIntent.Status.CREATED
    ):
        PaymentIntent.objects._transition(
            intent_id=intent.pk,
            from_statuses=[PaymentIntent.Status.CREATED],
            status=PaymentIntent.Status.PENDING,
            pending_at=database_now(),
        )
        intent.refresh_from_db()
    effect = (
        'BOOKING_CONFIRMED'
        if confirmation.succeeded
        else 'BOOKING_CONFIRMATION_EXCEPTION'
        if confirmation.reconciliation_case
        else 'BOOKING_THRESHOLD_PENDING'
    )
    status = (
        ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED
        if confirmation.reconciliation_case
        else ProviderEvent.ReconciliationStatus.APPLIED
    )
    code = confirmation.code or 'PAYMENT_RECONCILED'
    _finish_event(
        event=event,
        attempt=attempt,
        payments=payments,
        status=status,
        code=code,
        decision='RECONCILED',
        effect=effect,
    )
    return ProviderReconciliationResult(
        event=event,
        payments=payments,
        reconciliation_case=confirmation.reconciliation_case,
        confirmation=confirmation,
        changed=created or confirmation.changed,
        decision='RECONCILED',
        effect=effect,
    )


def _order_fulfillable(order, commitments):
    if order.estado in {'CANCELADO', 'RECHAZADO'}:
        return False
    if order.estado == 'COMPLETADO':
        return True
    return bool(commitments) and {
        commitment.estado for commitment in commitments
    } == {CompromisoStock.State.ACTIVE}


def _reconcile_order(event_id, attempt_id):
    order, commitments, attempt = _lock_order_context(attempt_id)
    event = _locked_event(event_id)
    if event.reconciliation_status != ProviderEvent.ReconciliationStatus.NOT_EVALUATED:
        return _idempotent_result(event)
    snapshot = _validate_locked_event(event, attempt)
    if _snapshot_is_stale(event, snapshot):
        return _mark_ignored(event, attempt, 'STALE_EVENT', 'STALE_SNAPSHOT_IGNORED')
    existing_external = tuple(
        order.pagos.select_for_update().filter(provider_code=PROVIDER).order_by('pk')
    )
    if _post_payment_change(snapshot):
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='POST_PAYMENT_CHANGE',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments or existing_external,
            reason_code='POST_PAYMENT_CHANGE',
            detail='El proveedor informó refund o contracargo.',
            case_type=PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
        )
    if not _eligible_payments(snapshot):
        if existing_external:
            return _review_result(
                event=event,
                attempt=attempt,
                payments=existing_external,
                reason_code='PROVIDER_STATUS_REGRESSION',
                detail='Un pago registrado aparece como no acreditado.',
                case_type=PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
            )
        return _mark_ignored(
            event,
            attempt,
            'PAYMENT_NOT_ACCREDITED',
            'NO_ACCREDITED_PAYMENT',
        )
    if _transaction_amount_mismatch(attempt, snapshot):
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='PAYMENT_AMOUNT_MISMATCH',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments,
            reason_code='PAYMENT_AMOUNT_MISMATCH',
            detail='El pago no coincide con la obligación de la Orden.',
        )
    if attempt.amount != order.total:
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='OBLIGATION_AMOUNT_MISMATCH',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments,
            reason_code='OBLIGATION_AMOUNT_MISMATCH',
            detail='El total actual de la Orden difiere del Attempt.',
        )
    if not _order_fulfillable(order, commitments):
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='ORDER_NOT_FULFILLABLE',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments,
            reason_code='ORDER_NOT_FULFILLABLE',
            detail='La orden no conserva un ciclo cumplible.',
            case_type=PaymentReconciliationCase.Type.ORDER_FULFILLMENT_FAILED,
        )

    paid_before = sum(
        (
            payment.monto for payment in existing_external
            if payment.status == Pago.Status.RECONCILED
        ),
        Decimal('0.00'),
    )
    candidate = _new_candidate_total(
        _eligible_payments(snapshot),
        existing_external,
    )
    if paid_before + candidate > order.total:
        payments, _ = _prepare_payment_rows(
            event,
            attempt,
            snapshot,
            pending_reason='PAYMENT_OVERPAYMENT',
        )
        return _review_result(
            event=event,
            attempt=attempt,
            payments=payments,
            reason_code='PAYMENT_OVERPAYMENT',
            detail='Aplicar el pago superaría el total de la Orden.',
        )
    payments, created = _prepare_payment_rows(event, attempt, snapshot)
    paid = paid_before + sum((payment.monto for payment in payments), Decimal('0.00'))
    previous_order_status = order.estado
    if paid == order.total and order.estado in {'PENDIENTE', 'ESPERANDO_PAGO'}:
        OrdenCompra.objects.filter(pk=order.pk).update(estado='PAGADO')
        order.estado = 'PAGADO'
        effect = 'ORDER_MARKED_PAID'
    elif paid < order.total:
        effect = 'ORDER_PAYMENT_PARTIAL'
    else:
        effect = 'ORDER_ALREADY_FULFILLED'
    Auditoria.objects.create(
        tabla=ORDER_PAYMENT_RECONCILED,
        registro_id=order.pk,
        usuario=None,
        accion='MODIFICACION',
        valor_anterior={'estado': previous_order_status},
        valor_nuevo={
            'event': ORDER_PAYMENT_RECONCILED,
            'order_id': order.pk,
            'estado': order.estado,
            'payment_ids': [payment.pk for payment in payments],
            'provider_event_id': event.pk,
            'decision': 'RECONCILED',
            'effect': effect,
        },
    )
    _finish_event(
        event=event,
        attempt=attempt,
        payments=payments,
        status=ProviderEvent.ReconciliationStatus.APPLIED,
        code='PAYMENT_RECONCILED',
        decision='RECONCILED',
        effect=effect,
    )
    return ProviderReconciliationResult(
        event=event,
        payments=payments,
        reconciliation_case=None,
        confirmation=None,
        changed=created or effect == 'ORDER_MARKED_PAID',
        decision='RECONCILED',
        effect=effect,
    )


@transaction.atomic
def reconcile_verified_provider_event(event_id):
    """Registra hechos financieros y delega B3; nunca consulta al proveedor."""
    event = _load_event(event_id)
    if event.reconciliation_status != ProviderEvent.ReconciliationStatus.NOT_EVALUATED:
        return _idempotent_result(event)
    attempt = event.attempt
    try:
        with transaction.atomic():
            if attempt.context == ProviderPaymentAttempt.Context.BOOKING:
                return _reconcile_booking(event.pk, attempt.pk)
            if attempt.context == ProviderPaymentAttempt.Context.ORDER:
                return _reconcile_order(event.pk, attempt.pk)
    except ProviderPaymentIdentityConflict as exc:
        locked_event = ProviderEvent.objects.select_for_update().get(pk=event.pk)
        if (
            locked_event.reconciliation_status
            != ProviderEvent.ReconciliationStatus.NOT_EVALUATED
        ):
            return _idempotent_result(locked_event)
        locked_attempt = ProviderPaymentAttempt.objects.select_for_update().get(
            pk=attempt.pk
        )
        return _review_result(
            event=locked_event,
            attempt=locked_attempt,
            payments=(exc.payment,),
            reason_code='PROVIDER_PAYMENT_IDENTITY_CONFLICT',
            detail=exc.detail,
        )
    raise ProviderReconciliationConflict(
        'PROVIDER_CONTEXT_UNSUPPORTED',
        'El contexto del Attempt no está soportado.',
    )
