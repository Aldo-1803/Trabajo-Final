import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from usuarios.models import Cliente
from usuarios.roles import BusinessPermission

from .models import (
    Auditoria,
    CompromisoStock,
    FinancialResolutionDecision,
    FinancialResolutionEvent,
    FinancialResolutionRequest,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    SlotHold,
    SolicitudTecnicaReserva,
    Turno,
)


FINANCIAL_RESOLUTION_REQUESTED = 'FINANCIAL_RESOLUTION_REQUESTED'
FINANCIAL_RESOLUTION_DECIDED = 'FINANCIAL_RESOLUTION_DECIDED'
FINANCIAL_EVIDENCE_REQUESTED = 'FINANCIAL_EVIDENCE_REQUESTED'

REQUESTABLE_PAYMENT_STATUSES = (
    Pago.Status.PENDING_RECONCILIATION,
    Pago.Status.RECONCILED,
)
OWNER_REQUESTABLE_CASE_TYPES = (
    PaymentReconciliationCase.Type.LATE_PAYMENT,
    PaymentReconciliationCase.Type.BOOKING_CONFIRMATION_FAILED,
    PaymentReconciliationCase.Type.ORDER_FULFILLMENT_FAILED,
    PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT,
)
OWNER_REQUESTABLE_OUTCOMES = (
    FinancialResolutionRequest.RequestedOutcome.REFUND,
    FinancialResolutionRequest.RequestedOutcome.CANCEL_AND_REFUND,
    FinancialResolutionRequest.RequestedOutcome.REVIEW_PAYMENT,
)


class FinancialResolutionError(Exception):
    default_code = 'FINANCIAL_RESOLUTION_ERROR'

    def __init__(self, detail, *, code=None, field='non_field_errors'):
        self.code = code or self.default_code
        self.detail = detail
        self.field = field
        super().__init__(detail)


class FinancialResolutionInvalid(FinancialResolutionError):
    default_code = 'INVALID_FINANCIAL_RESOLUTION'


class FinancialResolutionConflict(FinancialResolutionError):
    default_code = 'FINANCIAL_RESOLUTION_CONFLICT'


class FinancialResolutionNotFound(FinancialResolutionError):
    default_code = 'FINANCIAL_RESOLUTION_NOT_FOUND'


class FinancialResolutionPermissionDenied(FinancialResolutionError):
    default_code = 'FINANCIAL_RESOLUTION_PERMISSION_DENIED'


@dataclass(frozen=True)
class FinancialResolutionRequestResult:
    resolution_request: FinancialResolutionRequest
    created: bool


@dataclass(frozen=True)
class FinancialResolutionDecisionResult:
    decision: FinancialResolutionDecision
    created: bool


@dataclass(frozen=True)
class LockedBookingFinancialContext:
    solicitud: SolicitudTecnicaReserva
    hold: SlotHold
    intent: PaymentIntent
    cliente: Cliente
    payments: tuple


@dataclass(frozen=True)
class LockedCaseContext:
    case: PaymentReconciliationCase
    payments: tuple
    case_payments: tuple
    context: str


def _normalized_text(value):
    return str(value or '').strip()


def _normalized_amount(value):
    if value in (None, ''):
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FinancialResolutionInvalid(
            'El importe no es válido.',
            code='INVALID_RESOLUTION_AMOUNT',
            field='amount',
        ) from exc
    if amount <= 0:
        raise FinancialResolutionInvalid(
            'El importe debe ser mayor que cero.',
            code='INVALID_RESOLUTION_AMOUNT',
            field='amount',
        )
    return amount


def _operation_key(value):
    key = _normalized_text(value)
    if not key or len(key) > 128:
        raise FinancialResolutionInvalid(
            'Debe informar una clave idempotente válida.',
            code='INVALID_IDEMPOTENCY_KEY',
            field='idempotency_key',
        )
    return key


def _fingerprint(payload):
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True,
        default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _is_financial_reviewer(actor):
    return bool(
        getattr(actor, 'is_authenticated', False)
        and getattr(actor, 'is_active', False)
        and actor.has_perm(BusinessPermission.RECONCILE_EXTERNAL_PAYMENT)
    )


def _require_financial_reviewer(actor):
    if not _is_financial_reviewer(actor):
        raise FinancialResolutionPermissionDenied(
            'No tiene permisos para decidir incidencias financieras.',
        )


def _is_case_owner(case, actor):
    if not (
        getattr(actor, 'is_authenticated', False)
        and getattr(actor, 'is_active', False)
        and getattr(actor, 'pk', None) is not None
    ):
        return False
    if case.payment_intent_id is not None:
        return case.payment_intent.cliente.usuario_id == actor.pk
    return case.order.cliente.usuario_id == actor.pk


def _lock_booking_context(intent_id):
    try:
        target = PaymentIntent.objects.only(
            'pk',
            'solicitud_id',
            'slot_hold_id',
        ).get(pk=intent_id)
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=target.solicitud_id
        )
        hold = SlotHold.objects.select_for_update().get(pk=target.slot_hold_id)
        intent = PaymentIntent.objects.select_for_update().get(pk=target.pk)
        cliente = Cliente.objects.select_for_update().get(pk=intent.cliente_id)
        payments = tuple(
            Pago.objects.select_for_update()
            .filter(payment_intent_id=intent.pk)
            .order_by('pk')
        )
    except (
        PaymentIntent.DoesNotExist,
        SolicitudTecnicaReserva.DoesNotExist,
        SlotHold.DoesNotExist,
        Cliente.DoesNotExist,
    ) as exc:
        raise FinancialResolutionConflict(
            'El contexto BOOKING está incompleto.',
            code='BOOKING_FINANCIAL_CONTEXT_INCOMPLETE',
        ) from exc
    return LockedBookingFinancialContext(
        solicitud=solicitud,
        hold=hold,
        intent=intent,
        cliente=cliente,
        payments=payments,
    )


def lock_turno_financial_context(turno_id):
    target = PaymentIntent.objects.filter(
        confirmed_turno_id=turno_id
    ).only('pk').first()
    if target is None:
        return None
    return _lock_booking_context(target.pk)


def _lock_case_context(case_public_id):
    try:
        target = PaymentReconciliationCase.objects.only(
            'pk',
            'payment_intent_id',
            'order_id',
        ).get(public_id=case_public_id)
    except PaymentReconciliationCase.DoesNotExist as exc:
        raise FinancialResolutionNotFound(
            'La incidencia financiera no existe.',
        ) from exc

    if target.payment_intent_id is not None:
        booking = _lock_booking_context(target.payment_intent_id)
        case = PaymentReconciliationCase.objects.select_for_update().get(
            pk=target.pk
        )
        payments = booking.payments
        context = FinancialResolutionRequest.Context.BOOKING
    else:
        try:
            order = OrdenCompra.objects.select_for_update().get(
                pk=target.order_id
            )
        except OrdenCompra.DoesNotExist as exc:
            raise FinancialResolutionConflict(
                'El contexto ORDER está incompleto.',
                code='ORDER_FINANCIAL_CONTEXT_INCOMPLETE',
            ) from exc
        payments = tuple(
            Pago.objects.select_for_update()
            .filter(orden_id=order.pk)
            .order_by('pk')
        )
        case = PaymentReconciliationCase.objects.select_for_update().get(
            pk=target.pk
        )
        context = FinancialResolutionRequest.Context.ORDER

    case_payment_ids = set(case.payments.values_list('pk', flat=True))
    case_payments = tuple(
        payment for payment in payments if payment.pk in case_payment_ids
    )
    if not case_payments:
        case_payments = payments
    return LockedCaseContext(
        case=case,
        payments=payments,
        case_payments=case_payments,
        context=context,
    )


def _payment_totals(payments, statuses):
    eligible = tuple(payment for payment in payments if payment.status in statuses)
    currencies = {payment.currency for payment in eligible}
    if len(currencies) > 1:
        raise FinancialResolutionConflict(
            'Los Pagos relacionados tienen monedas incompatibles.',
            code='PAYMENT_CURRENCY_MISMATCH',
        )
    total = sum((payment.monto for payment in eligible), Decimal('0.00'))
    currency = next(iter(currencies), '')
    return total, currency, eligible


def _validate_request_amount(*, amount, currency, payments, outcome):
    amount = _normalized_amount(amount)
    currency = _normalized_text(currency).upper()
    if (amount is None) != (not currency):
        raise FinancialResolutionInvalid(
            'Importe y moneda deben informarse juntos.',
            code='RESOLUTION_AMOUNT_CURRENCY_REQUIRED',
            field='amount',
        )
    available, available_currency, _ = _payment_totals(
        payments,
        REQUESTABLE_PAYMENT_STATUSES,
    )
    money_outcomes = {
        FinancialResolutionRequest.RequestedOutcome.REFUND,
        FinancialResolutionRequest.RequestedOutcome.CANCEL_AND_REFUND,
        FinancialResolutionRequest.RequestedOutcome.REVIEW_PAYMENT,
    }
    if outcome == FinancialResolutionRequest.RequestedOutcome.REFUND and amount is None:
        raise FinancialResolutionInvalid(
            'Una solicitud de devolución debe indicar importe y moneda.',
            code='REFUND_REQUEST_AMOUNT_REQUIRED',
            field='amount',
        )
    if amount is not None and outcome not in money_outcomes:
        raise FinancialResolutionInvalid(
            'El resultado solicitado no admite importe ni moneda.',
            code='RESOLUTION_AMOUNT_NOT_ALLOWED',
            field='amount',
        )
    if amount is not None:
        if available <= 0:
            raise FinancialResolutionConflict(
                'El caso no contiene un Pago pendiente o conciliado.',
                code='NO_REQUESTABLE_PAYMENT',
            )
        if currency != available_currency:
            raise FinancialResolutionInvalid(
                'La moneda no coincide con los Pagos del caso.',
                code='RESOLUTION_CURRENCY_MISMATCH',
                field='currency',
            )
        if amount > available:
            raise FinancialResolutionInvalid(
                'El importe solicitado supera los Pagos relacionados.',
                code='RESOLUTION_AMOUNT_EXCEEDS_PAYMENTS',
                field='amount',
            )
    elif outcome in money_outcomes and available > 0:
        amount = available
        currency = available_currency
    return amount, currency


def _request_payload(
    *,
    case,
    actor,
    outcome,
    reason,
    amount,
    currency,
    evidence_reference,
    evidence_note,
    turno,
):
    return {
        'case_public_id': str(case.public_id),
        'actor_id': actor.pk,
        'requested_outcome': outcome,
        'reason': reason,
        'amount': str(amount) if amount is not None else None,
        'currency': currency,
        'evidence_reference': evidence_reference,
        'evidence_note': evidence_note,
        'turno_id': turno.pk if turno is not None else None,
    }


def _audit_request(resolution_request):
    Auditoria.objects.create(
        tabla=FINANCIAL_RESOLUTION_REQUESTED,
        registro_id=resolution_request.pk,
        usuario=resolution_request.requested_by,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': FINANCIAL_RESOLUTION_REQUESTED,
            'case_id': resolution_request.case_id,
            'case_public_id': str(resolution_request.case.public_id),
            'request_public_id': str(resolution_request.public_id),
            'context': resolution_request.context,
            'requested_outcome': resolution_request.requested_outcome,
            'reason': resolution_request.reason,
            'amount': (
                str(resolution_request.amount)
                if resolution_request.amount is not None
                else None
            ),
            'currency': resolution_request.currency,
            'status': resolution_request.status,
            'effect': 'NO_FINANCIAL_OR_BUSINESS_EFFECT',
        },
    )


def _create_request_locked(
    *,
    case,
    actor,
    context,
    outcome,
    reason,
    amount,
    currency,
    evidence_reference,
    evidence_note,
    idempotency_key,
    turno=None,
):
    key = _operation_key(idempotency_key)
    reason = _normalized_text(reason)
    if not reason:
        raise FinancialResolutionInvalid(
            'El motivo es obligatorio.',
            code='RESOLUTION_REASON_REQUIRED',
            field='reason',
        )
    evidence_reference = _normalized_text(evidence_reference)
    evidence_note = _normalized_text(evidence_note)
    payload = _request_payload(
        case=case,
        actor=actor,
        outcome=outcome,
        reason=reason,
        amount=amount,
        currency=currency,
        evidence_reference=evidence_reference,
        evidence_note=evidence_note,
        turno=turno,
    )
    fingerprint = _fingerprint(payload)
    existing = FinancialResolutionRequest.objects.select_for_update().filter(
        case=case
    ).first()
    if existing is not None:
        if (
            existing.requested_by_id == actor.pk
            and existing.idempotency_key == key
            and existing.request_fingerprint == fingerprint
        ):
            return FinancialResolutionRequestResult(existing, False)
        raise FinancialResolutionConflict(
            'El caso ya tiene una solicitud financiera.',
            code='FINANCIAL_REQUEST_ALREADY_EXISTS',
        )
    actor_key_match = FinancialResolutionRequest.objects.select_for_update().filter(
        requested_by=actor,
        idempotency_key=key,
    ).first()
    if actor_key_match is not None:
        if (
            actor_key_match.case_id == case.pk
            and actor_key_match.request_fingerprint == fingerprint
        ):
            return FinancialResolutionRequestResult(actor_key_match, False)
        raise FinancialResolutionConflict(
            'La clave idempotente ya fue usada con otro payload.',
            code='IDEMPOTENCY_KEY_REUSED',
        )
    now = timezone.now()
    try:
        resolution_request = FinancialResolutionRequest.objects._create_from_service(
            case=case,
            requested_by=actor,
            context=context,
            turno=turno,
            requested_outcome=outcome,
            reason=reason,
            amount=amount,
            currency=currency,
            evidence_reference=evidence_reference,
            evidence_note=evidence_note,
            status=FinancialResolutionRequest.Status.PENDING_DECISION,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            created_at=now,
            status_updated_at=now,
        )
    except IntegrityError as exc:
        raise FinancialResolutionConflict(
            'La solicitud compitió con otra operación.',
            code='FINANCIAL_REQUEST_CONCURRENCY_CONFLICT',
        ) from exc
    FinancialResolutionEvent.objects._create_from_service(
        resolution_request=resolution_request,
        decision=None,
        event_type=FinancialResolutionEvent.Type.REQUEST_SUBMITTED,
        actor=actor,
        operation_key=f'financial-request:{resolution_request.public_id}',
        payload={
            'case_public_id': str(case.public_id),
            'context': context,
            'requested_outcome': outcome,
            'amount': str(amount) if amount is not None else None,
            'currency': currency,
            'effect': 'NO_FINANCIAL_OR_BUSINESS_EFFECT',
        },
        created_at=now,
    )
    _audit_request(resolution_request)
    return FinancialResolutionRequestResult(resolution_request, True)


@transaction.atomic
def submit_financial_resolution_request(
    *,
    case_public_id,
    actor,
    requested_outcome,
    reason,
    amount=None,
    currency='',
    evidence_reference='',
    evidence_note='',
    idempotency_key,
):
    locked = _lock_case_context(case_public_id)
    case = locked.case
    reviewer = _is_financial_reviewer(actor)
    owner = _is_case_owner(case, actor)
    if not reviewer and not owner:
        raise FinancialResolutionNotFound(
            'La incidencia financiera no existe.',
        )
    if owner and not reviewer:
        if case.case_type not in OWNER_REQUESTABLE_CASE_TYPES:
            raise FinancialResolutionPermissionDenied(
                'La incidencia no admite solicitudes de la titular.',
                code='OWNER_REQUEST_NOT_ALLOWED',
            )
        if requested_outcome not in OWNER_REQUESTABLE_OUTCOMES:
            raise FinancialResolutionPermissionDenied(
                'El resultado solicitado no está habilitado para la titular.',
                code='OWNER_OUTCOME_NOT_ALLOWED',
            )
    if case.status != PaymentReconciliationCase.Status.OPEN:
        raise FinancialResolutionConflict(
            'El caso no está abierto.',
            code='FINANCIAL_CASE_NOT_OPEN',
        )
    amount, currency = _validate_request_amount(
        amount=amount,
        currency=currency,
        payments=locked.case_payments,
        outcome=requested_outcome,
    )
    turno = case.turno
    if turno is None and case.payment_intent_id is not None:
        turno = case.payment_intent.confirmed_turno
    return _create_request_locked(
        case=case,
        actor=actor,
        context=locked.context,
        outcome=requested_outcome,
        reason=reason,
        amount=amount,
        currency=currency,
        evidence_reference=evidence_reference,
        evidence_note=evidence_note,
        idempotency_key=idempotency_key,
        turno=turno,
    )


def _select_cancellation_case(*, payment_intent=None, order=None):
    filters = {
        'status': PaymentReconciliationCase.Status.OPEN,
        'case_type': PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT,
    }
    if payment_intent is not None:
        filters['payment_intent'] = payment_intent
    else:
        filters['order'] = order
    case = (
        PaymentReconciliationCase.objects.select_for_update()
        .filter(**filters)
        .order_by('created_at', 'pk')
        .first()
    )
    if case is not None:
        return case
    return None


def ensure_cancelled_turno_financial_request(
    *,
    actor,
    turno,
    booking_context,
):
    if booking_context is None:
        return None
    payments = tuple(
        payment
        for payment in booking_context.payments
        if payment.status in REQUESTABLE_PAYMENT_STATUSES
    )
    if not payments:
        return None
    total, currency, _ = _payment_totals(
        payments,
        REQUESTABLE_PAYMENT_STATUSES,
    )
    case = _select_cancellation_case(payment_intent=booking_context.intent)
    if case is None:
        case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=booking_context.intent,
            slot_hold=booking_context.hold,
            turno=turno,
            order=None,
            provider_attempt=None,
            provider_event=None,
            case_type=PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code='TURN_CANCELLATION_WITH_PAYMENT',
            operation_key=(
                f'financial-cancel:booking:{booking_context.intent.public_id}'
            ),
            details={
                'source': 'TURN_CANCELLATION',
                'turno_id': turno.pk,
                'effect': 'NO_AUTOMATIC_REFUND',
            },
            created_by=actor,
            created_at=timezone.now(),
        )
    case.payments.add(*(payment.pk for payment in payments))
    existing = FinancialResolutionRequest.objects.select_for_update().filter(
        case=case
    ).first()
    if existing is not None:
        return FinancialResolutionRequestResult(existing, False)
    return _create_request_locked(
        case=case,
        actor=actor,
        context=FinancialResolutionRequest.Context.BOOKING,
        outcome=FinancialResolutionRequest.RequestedOutcome.CANCEL_AND_REFUND,
        reason=turno.motivo_cancelacion,
        amount=total,
        currency=currency,
        evidence_reference=f'TURNO:{turno.pk}',
        evidence_note='Cancelación comercial con dinero pendiente de resolución.',
        idempotency_key=f'turno-cancel-financial:{turno.pk}',
        turno=turno,
    )


def _can_request_order_cancellation(order, actor):
    owner = (
        getattr(actor, 'is_authenticated', False)
        and getattr(actor, 'is_active', False)
        and getattr(actor, 'pk', None) is not None
        and order.cliente.usuario_id == actor.pk
    )
    staff_requester = bool(
        getattr(actor, 'is_authenticated', False)
        and getattr(actor, 'is_active', False)
        and (
            actor.has_perm(BusinessPermission.MANAGE_STOCK)
            or actor.has_perm(BusinessPermission.RECONCILE_EXTERNAL_PAYMENT)
        )
    )
    return owner or staff_requester


@transaction.atomic
def request_paid_order_cancellation(
    *,
    order_id,
    actor,
    reason,
    idempotency_key,
    amount=None,
    currency='',
    evidence_reference='',
    evidence_note='',
):
    try:
        order = OrdenCompra.objects.select_for_update().get(pk=order_id)
    except OrdenCompra.DoesNotExist as exc:
        raise FinancialResolutionNotFound('La orden no existe.') from exc
    if not _can_request_order_cancellation(order, actor):
        raise FinancialResolutionNotFound('La orden no existe.')
    if order.estado != 'PAGADO':
        raise FinancialResolutionConflict(
            'Sólo una orden PAGADO admite esta solicitud.',
            code='ORDER_NOT_PAID_FOR_CANCELLATION_REQUEST',
        )
    payments = tuple(
        Pago.objects.select_for_update()
        .filter(orden=order)
        .order_by('pk')
    )
    tuple(
        CompromisoStock.objects.select_for_update()
        .filter(orden=order)
        .order_by('pk')
    )
    eligible = tuple(
        payment for payment in payments
        if payment.status in REQUESTABLE_PAYMENT_STATUSES
    )
    if amount in (None, '') and eligible:
        amount, currency, _ = _payment_totals(
            eligible,
            REQUESTABLE_PAYMENT_STATUSES,
        )
    amount, currency = _validate_request_amount(
        amount=amount,
        currency=currency,
        payments=eligible,
        outcome=FinancialResolutionRequest.RequestedOutcome.CANCEL_AND_REFUND,
    )
    case = _select_cancellation_case(order=order)
    if case is None:
        case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=None,
            slot_hold=None,
            turno=None,
            order=order,
            provider_attempt=None,
            provider_event=None,
            case_type=PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code='ORDER_CANCELLATION_REQUESTED_WITH_PAYMENT',
            operation_key=f'financial-cancel:order:{order.pk}',
            details={
                'source': 'ORDER_CANCELLATION_REQUEST',
                'order_id': order.pk,
                'effect': 'NO_AUTOMATIC_CANCELLATION_OR_RELEASE',
            },
            created_by=actor,
            created_at=timezone.now(),
        )
    case.payments.add(*(payment.pk for payment in eligible))
    result = _create_request_locked(
        case=case,
        actor=actor,
        context=FinancialResolutionRequest.Context.ORDER,
        outcome=FinancialResolutionRequest.RequestedOutcome.CANCEL_AND_REFUND,
        reason=reason,
        amount=amount,
        currency=currency,
        evidence_reference=evidence_reference or f'ORDER:{order.pk}',
        evidence_note=evidence_note,
        idempotency_key=idempotency_key,
        turno=None,
    )
    return result, order


@transaction.atomic
def get_financial_resolution_request(*, case_public_id, actor):
    locked = _lock_case_context(case_public_id)
    case = locked.case
    reviewer = _is_financial_reviewer(actor)
    owner = _is_case_owner(case, actor)
    if not reviewer and not owner:
        raise FinancialResolutionNotFound(
            'La solicitud financiera no existe.',
        )
    try:
        resolution_request = (
            FinancialResolutionRequest.objects.select_for_update()
            .prefetch_related('decisions__decided_by', 'events__actor')
            .get(case=case)
        )
    except FinancialResolutionRequest.DoesNotExist as exc:
        raise FinancialResolutionNotFound(
            'La solicitud financiera no existe.',
        ) from exc
    return resolution_request, reviewer


def _decision_payload(
    *,
    resolution_request,
    actor,
    action,
    rationale,
    evidence_request,
    authorized_amount,
    currency,
    policy_reference,
):
    return {
        'request_public_id': str(resolution_request.public_id),
        'actor_id': actor.pk,
        'action': action,
        'rationale': rationale,
        'evidence_request': evidence_request,
        'authorized_amount': (
            str(authorized_amount) if authorized_amount is not None else None
        ),
        'currency': currency,
        'policy_reference': policy_reference,
    }


def _validate_decision(
    *,
    locked,
    resolution_request,
    action,
    authorized_amount,
    currency,
    policy_reference,
    evidence_request,
):
    authorized_amount = _normalized_amount(authorized_amount)
    currency = _normalized_text(currency).upper()
    policy_reference = _normalized_text(policy_reference)
    evidence_request = _normalized_text(evidence_request)
    refundable_outcomes = {
        FinancialResolutionRequest.RequestedOutcome.REFUND,
        FinancialResolutionRequest.RequestedOutcome.CANCEL_AND_REFUND,
        FinancialResolutionRequest.RequestedOutcome.REVIEW_PAYMENT,
    }
    if action == FinancialResolutionDecision.Action.APPROVE_REFUND:
        if resolution_request.requested_outcome not in refundable_outcomes:
            raise FinancialResolutionConflict(
                'La solicitud no propone una revisión reembolsable.',
                code='REFUND_DECISION_OUTCOME_MISMATCH',
            )
        if authorized_amount is None or not currency:
            raise FinancialResolutionInvalid(
                'La aprobación debe indicar importe y moneda.',
                code='REFUND_DECISION_AMOUNT_REQUIRED',
                field='authorized_amount',
            )
        maximum, payment_currency, _ = _payment_totals(
            locked.case_payments,
            (Pago.Status.RECONCILED,),
        )
        if maximum <= 0:
            raise FinancialResolutionConflict(
                'No hay un Pago conciliado reversible.',
                code='NO_RECONCILED_PAYMENT_TO_REFUND',
            )
        if currency != payment_currency:
            raise FinancialResolutionInvalid(
                'La moneda no coincide con el Pago conciliado.',
                code='REFUND_CURRENCY_MISMATCH',
                field='currency',
            )
        if authorized_amount > maximum:
            raise FinancialResolutionInvalid(
                'El importe autorizado supera el máximo reversible.',
                code='REFUND_AMOUNT_EXCEEDS_REVERSIBLE',
                field='authorized_amount',
            )
        requested_amount = resolution_request.amount
        if (
            requested_amount is not None
            and authorized_amount > requested_amount
        ):
            raise FinancialResolutionInvalid(
                'El importe autorizado supera el importe solicitado.',
                code='REFUND_AMOUNT_EXCEEDS_REQUEST',
                field='authorized_amount',
            )
        if not policy_reference:
            raise FinancialResolutionInvalid(
                'Debe indicar la política aplicada.',
                code='POLICY_REFERENCE_REQUIRED',
                field='policy_reference',
            )
    else:
        if authorized_amount is not None or currency:
            raise FinancialResolutionInvalid(
                'Esta decisión no admite un importe autorizado.',
                code='DECISION_AMOUNT_NOT_ALLOWED',
                field='authorized_amount',
            )
        authorized_amount = None
        currency = ''
    if action == FinancialResolutionDecision.Action.DENY_REFUND:
        if resolution_request.requested_outcome not in refundable_outcomes:
            raise FinancialResolutionConflict(
                'La solicitud no propone una revisión reembolsable.',
                code='REFUND_DECISION_OUTCOME_MISMATCH',
            )
        if not policy_reference:
            raise FinancialResolutionInvalid(
                'Debe indicar la política aplicada.',
                code='POLICY_REFERENCE_REQUIRED',
                field='policy_reference',
            )
    if action == FinancialResolutionDecision.Action.REQUIRE_MORE_EVIDENCE:
        if not evidence_request:
            raise FinancialResolutionInvalid(
                'Debe indicar la evidencia adicional requerida.',
                code='EVIDENCE_REQUEST_REQUIRED',
                field='evidence_request',
            )
    elif evidence_request:
        raise FinancialResolutionInvalid(
            'Esta decisión no admite una solicitud de evidencia.',
            code='EVIDENCE_REQUEST_NOT_ALLOWED',
            field='evidence_request',
        )
    if (
        action
        == FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT
        and locked.case.case_type
        not in {
            PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
            PaymentReconciliationCase.Type.EXTERNAL_PAYMENT_REVIEW,
        }
    ):
        raise FinancialResolutionConflict(
            'El caso no contiene una novedad externa reconocible.',
            code='EXTERNAL_ADJUSTMENT_NOT_PRESENT',
        )
    if (
        action
        == FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT
        and resolution_request.requested_outcome
        not in {
            FinancialResolutionRequest.RequestedOutcome.REVIEW_EXTERNAL_ADJUSTMENT,
            FinancialResolutionRequest.RequestedOutcome.REVIEW_PAYMENT,
        }
    ):
        raise FinancialResolutionConflict(
            'La solicitud no propone revisar una novedad externa.',
            code='EXTERNAL_ADJUSTMENT_OUTCOME_MISMATCH',
        )
    return (
        authorized_amount,
        currency,
        policy_reference,
        evidence_request,
    )


def _audit_decision(decision):
    event_name = (
        FINANCIAL_EVIDENCE_REQUESTED
        if decision.action
        == FinancialResolutionDecision.Action.REQUIRE_MORE_EVIDENCE
        else FINANCIAL_RESOLUTION_DECIDED
    )
    Auditoria.objects.create(
        tabla=event_name,
        registro_id=decision.pk,
        usuario=decision.decided_by,
        accion='ALTA',
        valor_anterior={
            'request_status': (
                FinancialResolutionRequest.Status.PENDING_DECISION
                if decision.sequence == 1
                else FinancialResolutionRequest.Status.EVIDENCE_REQUIRED
            ),
        },
        valor_nuevo={
            'event': event_name,
            'case_id': decision.resolution_request.case_id,
            'request_public_id': str(decision.resolution_request.public_id),
            'decision_public_id': str(decision.public_id),
            'sequence': decision.sequence,
            'action': decision.action,
            'rationale': decision.rationale,
            'evidence_request': decision.evidence_request,
            'authorized_amount': (
                str(decision.authorized_amount)
                if decision.authorized_amount is not None
                else None
            ),
            'currency': decision.currency,
            'policy_reference': decision.policy_reference,
            'case_status': PaymentReconciliationCase.Status.OPEN,
            'effect': 'NO_EXECUTION_NO_CONFIRMATION_NO_CASE_CLOSURE',
        },
    )


@transaction.atomic
def decide_financial_resolution(
    *,
    case_public_id,
    actor,
    action,
    rationale,
    idempotency_key,
    authorized_amount=None,
    currency='',
    policy_reference='',
    evidence_request='',
):
    _require_financial_reviewer(actor)
    locked = _lock_case_context(case_public_id)
    if locked.case.status != PaymentReconciliationCase.Status.OPEN:
        raise FinancialResolutionConflict(
            'El caso no está abierto.',
            code='FINANCIAL_CASE_NOT_OPEN',
        )
    try:
        resolution_request = FinancialResolutionRequest.objects.select_for_update().get(
            case=locked.case
        )
    except FinancialResolutionRequest.DoesNotExist as exc:
        raise FinancialResolutionConflict(
            'El caso no tiene una solicitud para decidir.',
            code='FINANCIAL_REQUEST_REQUIRED',
        ) from exc
    key = _operation_key(idempotency_key)
    rationale = _normalized_text(rationale)
    if not rationale:
        raise FinancialResolutionInvalid(
            'El fundamento es obligatorio.',
            code='DECISION_RATIONALE_REQUIRED',
            field='rationale',
        )
    (
        authorized_amount,
        currency,
        policy_reference,
        evidence_request,
    ) = _validate_decision(
        locked=locked,
        resolution_request=resolution_request,
        action=action,
        authorized_amount=authorized_amount,
        currency=currency,
        policy_reference=policy_reference,
        evidence_request=evidence_request,
    )
    payload = _decision_payload(
        resolution_request=resolution_request,
        actor=actor,
        action=action,
        rationale=rationale,
        evidence_request=evidence_request,
        authorized_amount=authorized_amount,
        currency=currency,
        policy_reference=policy_reference,
    )
    fingerprint = _fingerprint(payload)
    existing = FinancialResolutionDecision.objects.select_for_update().filter(
        decided_by=actor,
        idempotency_key=key,
    ).first()
    if existing is not None:
        if (
            existing.resolution_request_id == resolution_request.pk
            and existing.decision_fingerprint == fingerprint
        ):
            return FinancialResolutionDecisionResult(existing, False)
        raise FinancialResolutionConflict(
            'La clave idempotente ya fue usada con otra decisión.',
            code='IDEMPOTENCY_KEY_REUSED',
        )
    if resolution_request.status == FinancialResolutionRequest.Status.DECIDED:
        raise FinancialResolutionConflict(
            'La solicitud ya tiene una decisión final.',
            code='FINANCIAL_REQUEST_ALREADY_DECIDED',
        )
    sequence = (
        FinancialResolutionDecision.objects.filter(
            resolution_request=resolution_request
        ).aggregate(maximum=Max('sequence'))['maximum']
        or 0
    ) + 1
    now = timezone.now()
    try:
        decision = FinancialResolutionDecision.objects._create_from_service(
            resolution_request=resolution_request,
            sequence=sequence,
            action=action,
            rationale=rationale,
            evidence_request=evidence_request,
            authorized_amount=authorized_amount,
            currency=currency,
            policy_reference=policy_reference,
            decided_by=actor,
            idempotency_key=key,
            decision_fingerprint=fingerprint,
            decided_at=now,
        )
    except IntegrityError as exc:
        raise FinancialResolutionConflict(
            'La decisión compitió con otra operación.',
            code='FINANCIAL_DECISION_CONCURRENCY_CONFLICT',
        ) from exc
    next_status = (
        FinancialResolutionRequest.Status.EVIDENCE_REQUIRED
        if action == FinancialResolutionDecision.Action.REQUIRE_MORE_EVIDENCE
        else FinancialResolutionRequest.Status.DECIDED
    )
    transitioned = FinancialResolutionRequest.objects._transition_status(
        request_id=resolution_request.pk,
        from_statuses=(
            FinancialResolutionRequest.Status.PENDING_DECISION,
            FinancialResolutionRequest.Status.EVIDENCE_REQUIRED,
        ),
        status=next_status,
        status_updated_at=now,
    )
    if transitioned != 1:
        raise FinancialResolutionConflict(
            'La solicitud cambió durante la decisión.',
            code='FINANCIAL_REQUEST_STATE_CONFLICT',
        )
    resolution_request.status = next_status
    resolution_request.status_updated_at = now
    event_type = (
        FinancialResolutionEvent.Type.MORE_EVIDENCE_REQUIRED
        if action == FinancialResolutionDecision.Action.REQUIRE_MORE_EVIDENCE
        else FinancialResolutionEvent.Type.DECISION_RECORDED
    )
    FinancialResolutionEvent.objects._create_from_service(
        resolution_request=resolution_request,
        decision=decision,
        event_type=event_type,
        actor=actor,
        operation_key=f'financial-decision:{decision.public_id}',
        payload={
            'action': action,
            'sequence': sequence,
            'rationale': rationale,
            'evidence_request': evidence_request,
            'authorized_amount': (
                str(authorized_amount) if authorized_amount is not None else None
            ),
            'currency': currency,
            'policy_reference': policy_reference,
            'request_status': next_status,
            'case_status': PaymentReconciliationCase.Status.OPEN,
            'effect': 'NO_EXECUTION_NO_CONFIRMATION_NO_CASE_CLOSURE',
        },
        created_at=now,
    )
    _audit_decision(decision)
    return FinancialResolutionDecisionResult(decision, True)
