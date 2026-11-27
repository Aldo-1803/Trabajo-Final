"""Aplicación comercial y cierre verificable de casos financieros (F7.5)."""

from dataclasses import dataclass
import hashlib
import json
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from .financial_adjustment_services import project_payments_by_currency
from .financial_resolution_services import (
    FINANCIAL_RESOLUTION_DECIDED,
    FinancialResolutionConflict,
    FinancialResolutionInvalid,
    _lock_case_context,
    _operation_key,
    _require_financial_reviewer,
)
from .models import (
    Auditoria,
    CompromisoStock,
    FinancialAdjustment,
    FinancialCaseClosure,
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
    FinancialResolutionDecision,
    FinancialResolutionEvent,
    FinancialResolutionRequest,
    MovimientoStock,
    PaymentReconciliationCase,
    ProviderEvent,
    SlotHold,
    Turno,
)
from .order_inventory_services import (
    release_order_after_confirmed_financial_resolution,
)


FINANCIAL_CASE_CLOSED = 'FINANCIAL_CASE_CLOSED'
ALLOWED_RESULTS = set(FinancialCaseClosure.Result.values)


@dataclass(frozen=True)
class FinancialCaseClosureResult:
    closure: FinancialCaseClosure
    changed: bool


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
    ).encode('utf-8')).hexdigest()


def _expected_result(action):
    return {
        FinancialResolutionDecision.Action.APPROVE_REFUND: 'REFUND_CONFIRMED',
        FinancialResolutionDecision.Action.DENY_REFUND: 'REFUND_DENIED',
        FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE: (
            'NO_FINANCIAL_CHANGE'
        ),
        FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT: (
            'EXTERNAL_ADJUSTMENT_ACKNOWLEDGED'
        ),
    }.get(action)


def _assert_no_unresolved_provider_evidence(locked):
    attempt_ids = {
        payment.provider_attempt_id for payment in locked.payments
        if payment.provider_attempt_id
    }
    if locked.case.provider_attempt_id:
        attempt_ids.add(locked.case.provider_attempt_id)
    context_attempts = ProviderEvent.objects.none()
    if locked.case.payment_intent_id:
        context_attempts = ProviderEvent.objects.filter(
            attempt__payment_intent_id=locked.case.payment_intent_id,
        )
    elif locked.case.order_id:
        context_attempts = ProviderEvent.objects.filter(
            attempt__order_id=locked.case.order_id,
        )
    attempt_ids.update(
        context_attempts.values_list('attempt_id', flat=True)
    )
    if attempt_ids and ProviderEvent.objects.select_for_update().filter(
        attempt_id__in=attempt_ids,
        status=ProviderEvent.Status.VERIFIED,
        reconciliation_status=ProviderEvent.ReconciliationStatus.NOT_EVALUATED,
    ).exists():
        raise FinancialResolutionConflict(
            'Existe evidencia externa verificada todavía no evaluada.',
            code='UNEVALUATED_PROVIDER_EVENT',
        )


def _validate_refund_confirmation(decision, payments, adjustments):
    try:
        operation = FinancialRefundOperation.objects.select_for_update().get(
            decision=decision
        )
    except FinancialRefundOperation.DoesNotExist as exc:
        raise FinancialResolutionConflict(
            'La devolución aprobada no tiene operación verificable.',
            code='REFUND_OPERATION_REQUIRED',
        ) from exc
    if operation.status in {
        FinancialRefundOperation.Status.PENDING,
        FinancialRefundOperation.Status.SUBMITTED,
        FinancialRefundOperation.Status.UNKNOWN,
    }:
        raise FinancialResolutionConflict(
            'La operación de devolución todavía no tiene resultado final.',
            code='REFUND_OPERATION_UNRESOLVED',
        )
    if operation.status != FinancialRefundOperation.Status.CONFIRMED:
        raise FinancialResolutionConflict(
            'La devolución aprobada no fue confirmada externamente.',
            code='REFUND_NOT_CONFIRMED',
        )
    if not FinancialRefundOperationEvent.objects.select_for_update().filter(
        operation=operation,
        event_type=FinancialRefundOperationEvent.Type.CONFIRMED,
    ).exists():
        raise FinancialResolutionConflict(
            'La devolución confirmada no conserva su evento de confirmación.',
            code='REFUND_CONFIRMATION_EVENT_REQUIRED',
        )
    matching = [
        adjustment for adjustment in adjustments
        if adjustment.refund_operation_id == operation.pk
        and adjustment.adjustment_type == FinancialAdjustment.Type.REFUND
    ]
    if len(matching) != 1:
        raise FinancialResolutionConflict(
            'La operación no tiene un ajuste confirmado único.',
            code='REFUND_ADJUSTMENT_MISMATCH',
        )
    adjustment = matching[0]
    if (
        adjustment.amount != decision.authorized_amount
        or adjustment.currency != decision.currency
        or adjustment.payment_id not in {payment.pk for payment in payments}
        or operation.payment.provider_code != operation.provider
        or operation.payment.provider_payment_id
        != operation.provider_transaction_id
        or operation.payment.provider_attempt_id is None
        or operation.payment.provider_attempt.provider_order_id
        != operation.provider_order_id
    ):
        raise FinancialResolutionConflict(
            'Importe, moneda o Pago del ajuste no coinciden con la decisión.',
            code='REFUND_ADJUSTMENT_MISMATCH',
        )
    return operation, adjustment


def _apply_booking_effect(locked, decision):
    case = locked.case
    intent = case.payment_intent
    if case.case_type == PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT:
        turno = case.turno or intent.confirmed_turno
        if turno is None or turno.estado != Turno.Estado.CANCELADO:
            raise FinancialResolutionConflict(
                'El Turno cancelado no conserva su efecto comercial.',
                code='BOOKING_CANCELLATION_EFFECT_REQUIRED',
            )
        return 'TURN_REMAINS_CANCELLED'
    if case.case_type == PaymentReconciliationCase.Type.LATE_PAYMENT:
        if intent.confirmed_turno_id or intent.slot_hold.state == SlotHold.State.ACTIVE:
            raise FinancialResolutionConflict(
                'El pago tardío no puede cerrar con una reserva activa.',
                code='LATE_PAYMENT_BOOKING_RESURRECTED',
            )
        return 'NO_BOOKING_RECREATED'
    return 'BOOKING_HISTORY_PRESERVED'


def _order_projection(locked):
    grouped = project_payments_by_currency(locked.payments)
    if len(grouped) != 1:
        raise FinancialResolutionConflict(
            'La Orden no tiene una proyección monetaria única.',
            code='ORDER_FINANCIAL_PROJECTION_MISMATCH',
        )
    return next(iter(grouped.items()))


def _apply_order_effect(locked, request, decision, adjustments, actor):
    order = locked.case.order
    quantities = {
        row['producto_id']: row['cantidad']
        for row in order.items.values('producto_id').annotate(
            cantidad=models.Sum('cantidad')
        )
    }
    commitments = tuple(
        CompromisoStock.objects.select_for_update()
        .filter(orden=order)
        .order_by('pk')
    )
    commitment_quantities = {
        commitment.producto_id: commitment.cantidad
        for commitment in commitments
    }
    movements = tuple(
        MovimientoStock.objects.select_for_update()
        .filter(reference_type='ORDEN_COMPRA', reference_id=str(order.pk))
        .order_by('pk')
    )
    if order.estado == 'COMPLETADO':
        if (
            commitment_quantities != quantities
            or any(
                item.estado != CompromisoStock.State.CONSUMED
                for item in commitments
            )
        ):
            raise FinancialResolutionConflict(
                'La Orden completada no conserva compromisos consumidos.',
                code='COMPLETED_ORDER_INVENTORY_MISMATCH',
            )
        movement_quantities = {
            movement.producto_id: -movement.delta
            for movement in movements
            if movement.tipo == MovimientoStock.Type.ORDER_SALE_OUT
        }
        if movement_quantities != quantities or len(movements) != len(quantities):
            raise FinancialResolutionConflict(
                'La Orden completada no conserva sus movimientos físicos.',
                code='COMPLETED_ORDER_INVENTORY_MISMATCH',
            )
        if decision.action == FinancialResolutionDecision.Action.APPROVE_REFUND:
            return 'COMPLETED_ORDER_UNCHANGED_RETURN_DEFERRED'
        return 'COMPLETED_ORDER_UNCHANGED'

    if order.estado != 'PAGADO':
        raise FinancialResolutionConflict(
            'La Orden no entregada cambió de estado antes del cierre.',
            code='ORDER_STATE_CHANGED_BEFORE_FINANCIAL_EFFECT',
        )
    if commitment_quantities != quantities:
        raise FinancialResolutionConflict(
            'La Orden pagada no conserva compromisos de stock coherentes.',
            code='ORDER_COMMITMENTS_REQUIRED',
        )
    if any(item.estado != CompromisoStock.State.ACTIVE for item in commitments):
        raise FinancialResolutionConflict(
            'La Orden pagada no conserva compromisos activos.',
            code='PAID_ORDER_COMMITMENT_MISMATCH',
        )
    if movements:
        raise FinancialResolutionConflict(
            'La Orden no entregada ya tiene movimientos físicos.',
            code='UNDELIVERED_ORDER_HAS_MOVEMENTS',
        )

    if (
        decision.action == FinancialResolutionDecision.Action.APPROVE_REFUND
        and request.requested_outcome
        == FinancialResolutionRequest.RequestedOutcome.CANCEL_AND_REFUND
    ):
        currency, projection = _order_projection(locked)
        full_refund = (
            decision.currency == currency
            and projection['gross_reconciled'] == order.total
            and decision.authorized_amount == projection['gross_reconciled']
            and projection['refunds_confirmed']
            == projection['gross_reconciled']
            and projection['net_reconciled'] == Decimal('0.00')
        )
        if full_refund:
            release_order_after_confirmed_financial_resolution(
                order.pk,
                actor=actor,
                final_state='CANCELADO',
            )
            return 'ORDER_CANCELLED_COMMITMENTS_RELEASED'
        return 'PARTIAL_REFUND_ORDER_UNCHANGED'

    return 'ORDER_UNCHANGED'


@transaction.atomic
def close_financial_case(
    *, case_public_id, actor, rationale, result, idempotency_key,
):
    _require_financial_reviewer(actor)
    key = _operation_key(idempotency_key)
    rationale = str(rationale or '').strip()
    result = str(result or '').strip().upper()
    if not rationale:
        raise FinancialResolutionInvalid(
            'El fundamento de cierre es obligatorio.',
            code='CLOSURE_RATIONALE_REQUIRED',
            field='rationale',
        )
    if result not in ALLOWED_RESULTS:
        raise FinancialResolutionInvalid(
            'El resultado de cierre no es válido.',
            code='INVALID_CLOSURE_RESULT',
            field='result',
        )
    locked = _lock_case_context(case_public_id)
    case = locked.case
    payload = {
        'case_public_id': str(case.public_id),
        'actor_id': actor.pk,
        'rationale': rationale,
        'result': result,
    }
    fingerprint = _fingerprint(payload)
    existing = FinancialCaseClosure.objects.select_for_update().filter(
        case=case
    ).first()
    if existing is not None:
        if (
            existing.closed_by_id == actor.pk
            and existing.idempotency_key == key
            and existing.closure_fingerprint == fingerprint
        ):
            return FinancialCaseClosureResult(existing, False)
        raise FinancialResolutionConflict(
            'El caso ya fue cerrado con otro comando.',
            code='FINANCIAL_CASE_ALREADY_CLOSED',
        )
    if case.status != PaymentReconciliationCase.Status.OPEN:
        raise FinancialResolutionConflict(
            'El caso no está abierto y no conserva un cierre verificable.',
            code='FINANCIAL_CASE_NOT_OPEN',
        )
    key_match = FinancialCaseClosure.objects.select_for_update().filter(
        closed_by=actor,
        idempotency_key=key,
    ).first()
    if key_match is not None:
        raise FinancialResolutionConflict(
            'La clave idempotente ya fue usada para otro cierre.',
            code='IDEMPOTENCY_KEY_REUSED',
        )
    try:
        request = FinancialResolutionRequest.objects.select_for_update().get(
            case=case,
            status=FinancialResolutionRequest.Status.DECIDED,
        )
        decision = FinancialResolutionDecision.objects.select_for_update().get(
            resolution_request=request,
            action__in=FinancialResolutionDecision.FINAL_ACTIONS,
        )
    except (
        FinancialResolutionRequest.DoesNotExist,
        FinancialResolutionDecision.DoesNotExist,
    ) as exc:
        raise FinancialResolutionConflict(
            'El caso no tiene una decisión final autorizada.',
            code='FINAL_DECISION_REQUIRED',
        ) from exc
    expected = _expected_result(decision.action)
    if result != expected and not (
        result == 'PHYSICAL_RETURN_DEFERRED'
        and case.order_id
        and case.order.estado == 'COMPLETADO'
        and decision.action == FinancialResolutionDecision.Action.APPROVE_REFUND
    ):
        raise FinancialResolutionConflict(
            'El resultado no coincide con la decisión final.',
            code='CLOSURE_RESULT_DECISION_MISMATCH',
        )
    if not Auditoria.objects.select_for_update().filter(
        tabla=FINANCIAL_RESOLUTION_DECIDED,
        registro_id=decision.pk,
        usuario_id=decision.decided_by_id,
    ).exists():
        raise FinancialResolutionConflict(
            'La decisión final no conserva su auditoría semántica.',
            code='FINAL_DECISION_AUDIT_REQUIRED',
        )
    pending = FinancialRefundOperation.objects.select_for_update().filter(
        payment__in=locked.payments,
        status__in=['PENDING', 'SUBMITTED', 'UNKNOWN'],
    )
    if pending.exists():
        raise FinancialResolutionConflict(
            'Existe una operación de refund pendiente o desconocida.',
            code='REFUND_OPERATION_UNRESOLVED',
        )
    adjustments = tuple(
        FinancialAdjustment.objects.select_for_update()
        .filter(payment__in=locked.payments)
        .select_related('provider_event')
        .order_by('pk')
    )
    _assert_no_unresolved_provider_evidence(locked)
    operation = adjustment = None
    if decision.action == FinancialResolutionDecision.Action.APPROVE_REFUND:
        operation, adjustment = _validate_refund_confirmation(
            decision,
            locked.case_payments,
            adjustments,
        )
    unexpected_new_adjustments = [
        item for item in adjustments
        if item.created_at > decision.decided_at
        and (adjustment is None or item.pk != adjustment.pk)
    ]
    if unexpected_new_adjustments:
        raise FinancialResolutionConflict(
            'El estado financiero cambió después de la decisión final.',
            code='FINANCIAL_STATE_CHANGED_AFTER_DECISION',
        )
    if locked.context == FinancialResolutionRequest.Context.BOOKING:
        commercial_effect = _apply_booking_effect(locked, decision)
    else:
        commercial_effect = _apply_order_effect(
            locked, request, decision, adjustments, actor
        )
    now = timezone.now()
    evidence = {
        'decision_public_id': str(decision.public_id),
        'decision_action': decision.action,
        'operation_public_id': str(operation.public_id) if operation else None,
        'adjustment_public_id': str(adjustment.public_id) if adjustment else None,
        'commercial_effect': commercial_effect,
        'payment_public_ids': [
            str(payment.public_id) for payment in locked.case_payments
        ],
        'confirmed_adjustment_public_ids': [
            str(item.public_id) for item in adjustments
        ],
    }
    if case.order_id:
        evidence.update({
            'order_id': case.order_id,
            'order_status': type(case.order).objects.get(pk=case.order_id).estado,
            'commitment_ids': list(
                CompromisoStock.objects.filter(orden_id=case.order_id)
                .values_list('pk', flat=True)
            ),
            'movement_ids': list(
                MovimientoStock.objects.filter(
                    reference_type='ORDEN_COMPRA',
                    reference_id=str(case.order_id),
                ).values_list('pk', flat=True)
            ),
        })
    try:
        closure = FinancialCaseClosure.objects._create_from_service(
            case=case,
            decision=decision,
            closed_by=actor,
            rationale=rationale,
            result=result,
            commercial_effect=commercial_effect,
            idempotency_key=key,
            closure_fingerprint=fingerprint,
            evidence=evidence,
            closed_at=now,
        )
    except IntegrityError as exc:
        raise FinancialResolutionConflict(
            'El cierre compitió con otra operación.',
            code='FINANCIAL_CLOSURE_CONCURRENCY_CONFLICT',
        ) from exc
    if PaymentReconciliationCase.objects._resolve_from_service(
        case_id=case.pk,
        resolved_at=now,
    ) != 1:
        raise FinancialResolutionConflict(
            'El caso cambió durante el cierre.',
            code='FINANCIAL_CASE_STATE_CONFLICT',
        )
    FinancialResolutionEvent.objects._create_from_service(
        resolution_request=request,
        decision=decision,
        event_type=FinancialResolutionEvent.Type.CASE_CLOSED,
        actor=actor,
        operation_key=f'financial-case-closed:{case.public_id}',
        payload={**evidence, 'result': result, 'rationale': rationale},
        created_at=now,
    )
    Auditoria.objects.create(
        tabla=FINANCIAL_CASE_CLOSED,
        registro_id=case.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior={'status': PaymentReconciliationCase.Status.OPEN},
        valor_nuevo={
            'event': FINANCIAL_CASE_CLOSED,
            'status': PaymentReconciliationCase.Status.RESOLVED,
            'result': result,
            **evidence,
        },
    )
    case.status = PaymentReconciliationCase.Status.RESOLVED
    case.resolved_at = now
    return FinancialCaseClosureResult(closure, True)
