"""Ledger y proyecciones canónicas de ajustes confirmados (BH-058 F7.4)."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    Auditoria,
    FinancialAdjustment,
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
    Pago,
    ProviderEvent,
)


FINANCIAL_ADJUSTMENT_CONFIRMED = 'FINANCIAL_ADJUSTMENT_CONFIRMED'
FINANCIAL_REFUND_CONFIRMED = 'FINANCIAL_REFUND_CONFIRMED'
TERMINAL_ADJUSTMENT_STATUS = 'processed'
PENDING_REFUND_STATUSES = (
    FinancialRefundOperation.Status.PENDING,
    FinancialRefundOperation.Status.SUBMITTED,
    FinancialRefundOperation.Status.UNKNOWN,
)


@dataclass(frozen=True)
class PaymentFinancialProjection:
    payment_id: int
    currency: str
    gross_reconciled: Decimal
    confirmed_adjustments: Decimal
    net_reconciled: Decimal
    refund_pending: Decimal
    refunds_confirmed: Decimal
    chargebacks_confirmed: Decimal


@dataclass(frozen=True)
class AdjustmentIssue:
    code: str
    detail: str


@dataclass(frozen=True)
class AdjustmentMaterializationResult:
    adjustments: tuple[FinancialAdjustment, ...]
    issues: tuple[AdjustmentIssue, ...]


def _money(value):
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _official_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None or timezone.is_naive(parsed):
        return None
    return parsed


def project_payment_finances(payment):
    """Proyecta un Pago sin interpretar REVERSED como una resta adicional."""
    gross = (
        payment.monto
        if payment.status in {Pago.Status.RECONCILED, Pago.Status.REVERSED}
        else Decimal('0.00')
    )
    adjustments = tuple(payment.financial_adjustments.all())
    debit = sum(
        (
            item.amount for item in adjustments
            if item.effect == FinancialAdjustment.Effect.DEBIT
        ),
        Decimal('0.00'),
    )
    credit = sum(
        (
            item.amount for item in adjustments
            if item.effect == FinancialAdjustment.Effect.CREDIT
        ),
        Decimal('0.00'),
    )
    confirmed = debit - credit
    refund_confirmed = sum(
        (
            item.amount for item in adjustments
            if item.adjustment_type == FinancialAdjustment.Type.REFUND
            and item.effect == FinancialAdjustment.Effect.DEBIT
        ),
        Decimal('0.00'),
    )
    chargeback_confirmed = sum(
        (
            item.amount for item in adjustments
            if item.adjustment_type == FinancialAdjustment.Type.CHARGEBACK
            and item.effect == FinancialAdjustment.Effect.DEBIT
        ),
        Decimal('0.00'),
    )
    refund_pending = sum(
        (
            operation.amount for operation in payment.refund_operations.all()
            if operation.status in PENDING_REFUND_STATUSES
        ),
        Decimal('0.00'),
    )
    return PaymentFinancialProjection(
        payment_id=payment.pk,
        currency=payment.currency,
        gross_reconciled=gross,
        confirmed_adjustments=confirmed,
        net_reconciled=gross - confirmed,
        refund_pending=refund_pending,
        refunds_confirmed=refund_confirmed,
        chargebacks_confirmed=chargeback_confirmed,
    )


def project_payments_by_currency(payments):
    """Agrega BOOKING/ORDER/caso sin sumar monedas incompatibles."""
    grouped = {}
    for payment in payments:
        projection = project_payment_finances(payment)
        values = grouped.setdefault(
            projection.currency,
            {
                'gross_reconciled': Decimal('0.00'),
                'confirmed_adjustments': Decimal('0.00'),
                'net_reconciled': Decimal('0.00'),
                'refund_pending': Decimal('0.00'),
                'refunds_confirmed': Decimal('0.00'),
                'chargebacks_confirmed': Decimal('0.00'),
            },
        )
        for field in values:
            values[field] += getattr(projection, field)
    return grouped


def project_booking_finances(payment_intent):
    return project_payments_by_currency(payment_intent.payments.all())


def project_order_finances(order):
    return project_payments_by_currency(order.pagos.all())


def _same_adjustment(adjustment, *, payment, amount, currency, event, status):
    return bool(
        adjustment.payment_id == payment.pk
        and adjustment.amount == amount
        and adjustment.currency == currency
        and adjustment.provider_event.provider == event.provider
        and adjustment.provider_status.lower() == status
    )


def _find_refund_operation(*, payment, event, row, amount, currency):
    external_id = str(row.get('id') or '').strip()
    exact = list(
        FinancialRefundOperation.objects.select_for_update().filter(
            provider=event.provider,
            external_refund_id=external_id,
        )
    )
    if exact:
        operation = exact[0]
        if (
            operation.payment_id == payment.pk
            and operation.amount == amount
            and operation.currency == currency
            and operation.provider_transaction_id
            == str(row.get('transaction_id') or '').strip()
        ):
            return operation, None
        return None, AdjustmentIssue(
            'REFUND_OPERATION_IDENTITY_MISMATCH',
            'El refund externo coincide con una operación F7.3 incompatible.',
        )

    candidates = list(
        FinancialRefundOperation.objects.select_for_update().filter(
            payment=payment,
            provider=event.provider,
            provider_transaction_id=str(row.get('transaction_id') or '').strip(),
            amount=amount,
            currency=currency,
            status__in=PENDING_REFUND_STATUSES,
            external_refund_id='',
        )
    )
    candidates = [
        operation for operation in candidates
        if external_id not in set(operation.baseline_refund_ids or [])
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, AdjustmentIssue(
            'REFUND_OPERATION_AMBIGUOUS',
            'Más de una operación F7.3 podría corresponder al refund externo.',
        )
    return None, None


def _confirm_refund_operation(operation, adjustment, event, evidence):
    if operation is None:
        return
    now = timezone.now()
    values = {
        'status': FinancialRefundOperation.Status.CONFIRMED,
        'external_refund_id': adjustment.external_adjustment_id,
        'provider_status': adjustment.provider_status,
        'provider_status_detail': str(
            (event.provider_snapshot or {}).get('status_detail') or ''
        )[:100],
        'latest_evidence': evidence,
        'confirmed_at': now,
        'error_code': '',
        'error_detail': '',
        'updated_at': now,
    }
    transitioned = FinancialRefundOperation.objects._transition(
        operation_id=operation.pk,
        from_statuses=PENDING_REFUND_STATUSES,
        **values,
    )
    if not transitioned:
        return
    for name, value in values.items():
        if name != 'updated_at':
            setattr(operation, name, value)
    FinancialRefundOperationEvent.objects._create_from_service(
        operation=operation,
        event_type=FinancialRefundOperationEvent.Type.CONFIRMED,
        actor=None,
        operation_key=(
            f'adjustment-confirmed:{operation.pk}:{adjustment.pk}'
        ),
        payload={
            'adjustment_public_id': str(adjustment.public_id),
            'provider_event_id': event.pk,
            'external_refund_id': adjustment.external_adjustment_id,
            'amount': str(adjustment.amount),
            'currency': adjustment.currency,
            'effect': 'FINANCIAL_CONFIRMATION_ONLY',
        },
        created_at=now,
    )
    Auditoria.objects.create(
        tabla=FINANCIAL_REFUND_CONFIRMED,
        registro_id=operation.pk,
        usuario=None,
        accion='MODIFICACION',
        valor_anterior=None,
        valor_nuevo={
            'event': FINANCIAL_REFUND_CONFIRMED,
            'operation_public_id': str(operation.public_id),
            'adjustment_public_id': str(adjustment.public_id),
            'provider_event_id': event.pk,
            'status': FinancialRefundOperation.Status.CONFIRMED,
            'effect': 'NO_COMMERCIAL_EFFECT',
        },
    )


def _create_adjustment(
    *, event, payment, adjustment_type, row, amount, currency, effective_at,
    refund_operation,
):
    external_id = str(row.get('id') or '').strip()
    status = str(row.get('status') or '').strip().lower()
    existing = FinancialAdjustment.objects.select_for_update().filter(
        provider=event.provider,
        adjustment_type=adjustment_type,
        external_adjustment_id=external_id,
    ).select_related('provider_event').first()
    if existing is not None:
        if _same_adjustment(
            existing,
            payment=payment,
            amount=amount,
            currency=currency,
            event=event,
            status=status,
        ):
            return existing, False, None
        return None, False, AdjustmentIssue(
            'ADJUSTMENT_IDENTITY_MISMATCH',
            'La identidad externa ya existe con Pago, importe o moneda diferente.',
        )

    locked_payment = Pago.objects.select_for_update().get(pk=payment.pk)
    debit_total = FinancialAdjustment.objects.filter(
        payment=locked_payment,
        effect=FinancialAdjustment.Effect.DEBIT,
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    credit_total = FinancialAdjustment.objects.filter(
        payment=locked_payment,
        effect=FinancialAdjustment.Effect.CREDIT,
    ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    if debit_total - credit_total + amount > locked_payment.monto:
        return None, False, AdjustmentIssue(
            'ADJUSTMENT_EXCEEDS_PAYMENT',
            'Los ajustes confirmados superarían el Pago de origen.',
        )

    evidence = {
        'provider': event.provider,
        'provider_event_id': event.pk,
        'provider_event_identity': event.event_id,
        'provider_order_id': event.provider_resource_id,
        'provider_order_status': str(
            (event.provider_snapshot or {}).get('status') or ''
        )[:50],
        'provider_order_updated_at': str(
            (event.provider_snapshot or {}).get('last_updated_date') or ''
        )[:64],
        'adjustment': {
            'id': external_id,
            'transaction_id': str(row.get('transaction_id') or '')[:128],
            'reference_id': str(row.get('reference_id') or '')[:128],
            'amount': str(amount),
            'currency': currency,
            'status': status,
            'status_detail': str(row.get('status_detail') or '')[:100],
            'created_date': str(
                row.get('created_date') or row.get('date_created') or ''
            )[:64],
            'last_updated_date': str(
                row.get('last_updated_date')
                or row.get('date_last_updated')
                or ''
            )[:64],
        },
    }
    try:
        with transaction.atomic():
            adjustment = FinancialAdjustment.objects._create_from_service(
                payment=locked_payment,
                adjustment_type=adjustment_type,
                effect=FinancialAdjustment.Effect.DEBIT,
                amount=amount,
                currency=currency,
                provider=event.provider,
                external_adjustment_id=external_id,
                provider_status=status,
                provider_event=event,
                refund_operation=refund_operation,
                reverses_adjustment=None,
                effective_at=effective_at,
                evidence=evidence,
                created_at=timezone.now(),
            )
    except IntegrityError:
        adjustment = FinancialAdjustment.objects.select_for_update().filter(
            provider=event.provider,
            adjustment_type=adjustment_type,
            external_adjustment_id=external_id,
        ).select_related('provider_event').first()
        if adjustment is None or not _same_adjustment(
            adjustment,
            payment=locked_payment,
            amount=amount,
            currency=currency,
            event=event,
            status=status,
        ):
            return None, False, AdjustmentIssue(
                'ADJUSTMENT_IDENTITY_MISMATCH',
                'La identidad externa entró en conflicto concurrente.',
            )
        return adjustment, False, None

    Auditoria.objects.create(
        tabla=FINANCIAL_ADJUSTMENT_CONFIRMED,
        registro_id=adjustment.pk,
        usuario=None,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': FINANCIAL_ADJUSTMENT_CONFIRMED,
            'adjustment_public_id': str(adjustment.public_id),
            'adjustment_type': adjustment.adjustment_type,
            'payment_public_id': str(locked_payment.public_id),
            'provider_event_id': event.pk,
            'external_adjustment_id': external_id,
            'amount': str(amount),
            'currency': currency,
            'effective_at': effective_at.isoformat(),
            'effect': 'NET_RECONCILED_REDUCED_NO_COMMERCIAL_EFFECT',
        },
    )
    if adjustment_type == FinancialAdjustment.Type.REFUND:
        _confirm_refund_operation(refund_operation, adjustment, event, evidence)
    return adjustment, True, None


def materialize_confirmed_adjustments(*, event, attempt, snapshot, payments):
    """Materializa sólo filas terminales completas de un snapshot ya verificado."""
    if event.status != ProviderEvent.Status.VERIFIED:
        return AdjustmentMaterializationResult((), (
            AdjustmentIssue(
                'PROVIDER_EVENT_NOT_VERIFIED',
                'La evidencia del ajuste no está verificada.',
            ),
        ))
    payment_by_transaction = {
        payment.provider_payment_id: payment
        for payment in payments
        if payment.provider_payment_id
    }
    adjustments = []
    issues = []
    collections = (
        ('refunds', FinancialAdjustment.Type.REFUND),
        ('chargebacks', FinancialAdjustment.Type.CHARGEBACK),
    )
    for collection_name, adjustment_type in collections:
        rows = snapshot.get(collection_name) or []
        if not isinstance(rows, list):
            issues.append(AdjustmentIssue(
                'INVALID_ADJUSTMENT_COLLECTION',
                f'La colección {collection_name} no es verificable.',
            ))
            continue
        for row in rows:
            if not isinstance(row, dict):
                issues.append(AdjustmentIssue(
                    'INVALID_ADJUSTMENT_ROW',
                    f'Una fila de {collection_name} no es verificable.',
                ))
                continue
            status = str(row.get('status') or '').strip().lower()
            if status != TERMINAL_ADJUSTMENT_STATUS:
                continue
            external_id = str(row.get('id') or '').strip()
            transaction_id = str(row.get('transaction_id') or '').strip()
            amount = _money(row.get('amount'))
            currency = str(row.get('currency') or snapshot.get('currency') or '').upper()
            effective_at = (
                _official_datetime(row.get('last_updated_date'))
                or _official_datetime(row.get('date_last_updated'))
                or _official_datetime(row.get('created_date'))
                or _official_datetime(row.get('date_created'))
                or _official_datetime(snapshot.get('last_updated_date'))
            )
            if (
                not external_id
                or len(external_id) > 128
                or not transaction_id
                or amount is None
                or amount <= 0
                or effective_at is None
            ):
                issues.append(AdjustmentIssue(
                    'ADJUSTMENT_EVIDENCE_INCOMPLETE',
                    'El ajuste terminal no conserva identidad, importe o fecha verificable.',
                ))
                continue
            payment = payment_by_transaction.get(transaction_id)
            if payment is None:
                issues.append(AdjustmentIssue(
                    'ADJUSTMENT_PAYMENT_NOT_FOUND',
                    'El ajuste no identifica un Pago de origen único.',
                ))
                continue
            same_context = (
                payment.provider_attempt_id == attempt.pk
                and payment.provider_code == event.provider
            )
            if (
                not same_context
                or payment.currency != currency
                or payment.status not in {Pago.Status.RECONCILED, Pago.Status.REVERSED}
            ):
                issues.append(AdjustmentIssue(
                    'ADJUSTMENT_PAYMENT_MISMATCH',
                    'Pago, proveedor, moneda o estado no coinciden con el ajuste.',
                ))
                continue
            operation = None
            if adjustment_type == FinancialAdjustment.Type.REFUND:
                operation, operation_issue = _find_refund_operation(
                    payment=payment,
                    event=event,
                    row=row,
                    amount=amount,
                    currency=currency,
                )
                if operation_issue is not None:
                    issues.append(operation_issue)
            adjustment, _created, issue = _create_adjustment(
                event=event,
                payment=payment,
                adjustment_type=adjustment_type,
                row=row,
                amount=amount,
                currency=currency,
                effective_at=effective_at,
                refund_operation=operation,
            )
            if issue is not None:
                issues.append(issue)
            elif adjustment is not None:
                adjustments.append(adjustment)
    return AdjustmentMaterializationResult(tuple(adjustments), tuple(issues))
