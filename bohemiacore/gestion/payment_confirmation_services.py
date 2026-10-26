"""Aprobación financiera y confirmación atómica de booking (BH-058 B3)."""

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from usuarios.models import Cliente

from .models import (
    Auditoria,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    SlotHold,
    SolicitudTecnicaReserva,
    Turno,
)
from .payment_intent_services import _expire_locked_intent
from .slot_hold_clock import database_now
from .slot_hold_consumption_services import (
    create_confirmed_turno_from_locked_hold,
)
from .slot_hold_services import _key_fingerprint


PAYMENT_INTENT_APPROVED = 'PAYMENT_INTENT_APPROVED'
BOOKING_CONFIRMED_FROM_PAYMENT = 'BOOKING_CONFIRMED_FROM_PAYMENT'
PAYMENT_CONFIRMATION_FAILED = 'PAYMENT_CONFIRMATION_FAILED'


class PaymentConfirmationError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(detail)


class PaymentConfirmationConflict(PaymentConfirmationError):
    pass


@dataclass(frozen=True)
class PaymentConfirmationResult:
    intent: PaymentIntent
    hold: SlotHold
    turno: Turno | None
    reconciliation_case: PaymentReconciliationCase | None
    paid_reconciled: Decimal
    changed: bool
    code: str = ''
    detail: str = ''

    @property
    def succeeded(self):
        return self.turno is not None

    @property
    def threshold_reached(self):
        return self.paid_reconciled >= self.intent.required_amount


def confirmation_operation_key(intent):
    return f'payment-confirm:{intent.public_id}'


def _lock_confirmation_graph(intent_id):
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
            .filter(payment_intent=intent)
            .order_by('pk')
        )
    except (
        PaymentIntent.DoesNotExist,
        SolicitudTecnicaReserva.DoesNotExist,
        SlotHold.DoesNotExist,
        Cliente.DoesNotExist,
    ) as exc:
        raise PaymentConfirmationError(
            'PAYMENT_CONFIRMATION_CONTEXT_NOT_FOUND',
            'No existe el contexto financiero completo.',
        ) from exc
    return solicitud, hold, intent, cliente, payments


def _paid_reconciled(intent, payments):
    eligible = tuple(
        payment
        for payment in payments
        if payment.status == Pago.Status.RECONCILED
    )
    if any(payment.currency != intent.currency for payment in eligible):
        raise PaymentConfirmationConflict(
            'PAYMENT_CURRENCY_MISMATCH',
            'Un Pago conciliado no coincide con la moneda del Intent.',
        )
    paid = sum((payment.monto for payment in eligible), Decimal('0.00'))
    if paid > intent.total_amount_snapshot:
        raise PaymentConfirmationConflict(
            'PAYMENT_OVERPAYMENT',
            'Los Pagos conciliados superan el total del Intent.',
        )
    return paid, eligible


def _audit_success(
    *,
    intent,
    hold,
    turno,
    payments,
    actor,
    operation_key,
    approved_at,
    previous_status,
):
    payload = {
        'intent_id': intent.pk,
        'intent_public_id': str(intent.public_id),
        'hold_id': hold.pk,
        'hold_public_id': str(hold.public_id),
        'payment_ids': [payment.pk for payment in payments],
        'turno_id': turno.pk,
        'actor': getattr(actor, 'pk', None) or 'SYSTEM',
        'operation_key_sha256': _key_fingerprint(operation_key),
    }
    Auditoria.objects.create(
        tabla=PAYMENT_INTENT_APPROVED,
        registro_id=intent.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='MODIFICACION',
        valor_anterior={'status': previous_status},
        valor_nuevo={
            'event': PAYMENT_INTENT_APPROVED,
            'previous_status': previous_status,
            'current_status': PaymentIntent.Status.APPROVED,
            'event_at': approved_at.isoformat(),
            **payload,
        },
    )
    Auditoria.objects.create(
        tabla=BOOKING_CONFIRMED_FROM_PAYMENT,
        registro_id=turno.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': BOOKING_CONFIRMED_FROM_PAYMENT,
            'event_at': hold.consumed_at.isoformat(),
            **payload,
        },
    )


def _create_failure_case(
    *,
    intent,
    hold,
    payments,
    actor,
    operation_key,
    code,
    detail,
    failed_at,
):
    case_type = (
        PaymentReconciliationCase.Type.LATE_PAYMENT
        if code in {'HOLD_EXPIRED', 'INTENT_EXPIRED'}
        else PaymentReconciliationCase.Type.BOOKING_CONFIRMATION_FAILED
    )
    existing = PaymentReconciliationCase.objects.filter(
        operation_key=operation_key
    ).first()
    if existing is not None:
        if existing.payment_intent_id != intent.pk:
            raise PaymentConfirmationConflict(
                'OPERATION_KEY_REUSED',
                'La operation key ya fue usada para otro Intent.',
            )
        return existing

    case = PaymentReconciliationCase.objects._create_from_service(
        payment_intent=intent,
        slot_hold=hold,
        turno=None,
        case_type=case_type,
        status=PaymentReconciliationCase.Status.OPEN,
        reason_code=code,
        operation_key=operation_key,
        details={
            'detail': detail,
            'paid_reconciled': str(
                sum((payment.monto for payment in payments), Decimal('0.00'))
            ),
            'required_amount': str(intent.required_amount),
            'currency': intent.currency,
        },
        created_by=actor if getattr(actor, 'pk', None) else None,
        created_at=failed_at,
    )
    case.payments.add(*(payment.pk for payment in payments))
    Auditoria.objects.create(
        tabla=PAYMENT_CONFIRMATION_FAILED,
        registro_id=case.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': PAYMENT_CONFIRMATION_FAILED,
            'case_id': case.pk,
            'case_public_id': str(case.public_id),
            'case_type': case.case_type,
            'reason_code': code,
            'intent_id': intent.pk,
            'intent_public_id': str(intent.public_id),
            'hold_id': hold.pk,
            'hold_public_id': str(hold.public_id),
            'payment_ids': [payment.pk for payment in payments],
            'turno_id': None,
            'actor': getattr(actor, 'pk', None) or 'SYSTEM',
            'operation_key_sha256': _key_fingerprint(operation_key),
            'event_at': failed_at.isoformat(),
        },
    )
    return case


def _terminal_failure_status(code):
    if code in {'HOLD_EXPIRED', 'INTENT_EXPIRED'}:
        return PaymentIntent.Status.EXPIRED
    return PaymentIntent.Status.REJECTED


def _materialize_preconsumption_failure(
    *, intent, hold, payments, actor, operation_key, code, detail, now
):
    if intent.status in PaymentIntent.ACTIVE_STATUSES:
        if code in {'HOLD_EXPIRED', 'INTENT_EXPIRED', 'HOLD_RELEASED'}:
            _expire_locked_intent(
                intent=intent,
                hold=hold,
                actor=actor,
                now=now,
            )
            intent.refresh_from_db()
        else:
            PaymentIntent.objects._transition(
                intent_id=intent.pk,
                from_statuses=PaymentIntent.ACTIVE_STATUSES,
                status=PaymentIntent.Status.REJECTED,
                terminal_at=now,
                terminal_reason=code,
                confirmation_operation_key=operation_key,
            )
            intent.refresh_from_db()
    if intent.confirmation_operation_key is None:
        PaymentIntent.objects._transition(
            intent_id=intent.pk,
            from_statuses=[intent.status],
            confirmation_operation_key=operation_key,
        )
        intent.refresh_from_db()
    case = _create_failure_case(
        intent=intent,
        hold=hold,
        payments=payments,
        actor=actor,
        operation_key=operation_key,
        code=code,
        detail=detail,
        failed_at=now,
    )
    return PaymentConfirmationResult(
        intent=intent,
        hold=hold,
        turno=None,
        reconciliation_case=case,
        paid_reconciled=sum(
            (payment.monto for payment in payments), Decimal('0.00')
        ),
        changed=True,
        code=code,
        detail=detail,
    )


@transaction.atomic
def approve_payment_intent_and_confirm_booking(
    *,
    intent_id,
    actor=None,
    operation_key=None,
):
    """Aprueba el umbral y delega en A2 la única creación del Turno."""
    _, hold, intent, _, payments = _lock_confirmation_graph(intent_id)
    key = (operation_key or confirmation_operation_key(intent)).strip()
    if not key or len(key) > 128:
        raise PaymentConfirmationError(
            'INVALID_OPERATION_KEY',
            'Debe informar una operation key válida.',
        )

    paid, eligible = _paid_reconciled(intent, payments)
    now = database_now()

    if intent.confirmation_operation_key not in {None, key}:
        raise PaymentConfirmationConflict(
            'OPERATION_KEY_MISMATCH',
            'El Intent ya fue procesado con otra operation key.',
        )

    if intent.status == PaymentIntent.Status.APPROVED:
        if (
            hold.state != SlotHold.State.CONSUMED
            or not hold.consumed_turno_id
            or intent.confirmed_turno_id != hold.consumed_turno_id
            or intent.confirmation_operation_key != key
        ):
            raise PaymentConfirmationConflict(
                'APPROVED_INTENT_WITHOUT_CONFIRMED_BOOKING',
                'El Intent aprobado no tiene una confirmación de agenda coherente.',
            )
        consumption = create_confirmed_turno_from_locked_hold(
            hold=hold,
            operation_key=key,
            actor=actor,
        )
        return PaymentConfirmationResult(
            intent=intent,
            hold=consumption.hold,
            turno=consumption.turno,
            reconciliation_case=None,
            paid_reconciled=paid,
            changed=False,
        )

    if intent.status in PaymentIntent.TERMINAL_FAILURE_STATUSES:
        case = PaymentReconciliationCase.objects.filter(
            payment_intent=intent,
            operation_key=key,
        ).first()
        if case is None:
            raise PaymentConfirmationConflict(
                'PAYMENT_INTENT_TERMINAL',
                'El Intent terminó sin una confirmación financiera recuperable.',
            )
        return PaymentConfirmationResult(
            intent=intent,
            hold=hold,
            turno=None,
            reconciliation_case=case,
            paid_reconciled=paid,
            changed=False,
            code=case.reason_code,
            detail=case.details.get('detail', ''),
        )

    if paid < intent.required_amount:
        return PaymentConfirmationResult(
            intent=intent,
            hold=hold,
            turno=None,
            reconciliation_case=None,
            paid_reconciled=paid,
            changed=False,
            code='PAYMENT_THRESHOLD_NOT_REACHED',
            detail='Los Pagos conciliados todavía no alcanzan el umbral.',
        )

    if (
        intent.expires_at <= now
        or hold.expires_at <= now
        or hold.state in {SlotHold.State.EXPIRED, SlotHold.State.RELEASED}
    ):
        code = (
            'HOLD_EXPIRED'
            if hold.expires_at <= now or hold.state == SlotHold.State.EXPIRED
            else 'HOLD_RELEASED'
            if hold.state == SlotHold.State.RELEASED
            else 'INTENT_EXPIRED'
        )
        return _materialize_preconsumption_failure(
            intent=intent,
            hold=hold,
            payments=eligible,
            actor=actor,
            operation_key=key,
            code=code,
            detail='El contexto temporal ya no permite confirmar la agenda.',
            now=now,
        )
    if hold.state != SlotHold.State.ACTIVE:
        raise PaymentConfirmationConflict(
            'HOLD_STATE_INCONSISTENT',
            'El HOLD no está disponible para la confirmación financiera.',
        )

    previous_status = intent.status
    transitioned = PaymentIntent.objects._transition(
        intent_id=intent.pk,
        from_statuses=PaymentIntent.ACTIVE_STATUSES,
        status=PaymentIntent.Status.APPROVED,
        approved_at=now,
        confirmation_operation_key=key,
    )
    if transitioned != 1:
        raise PaymentConfirmationConflict(
            'PAYMENT_APPROVAL_CONFLICT',
            'El Intent cambió durante la aprobación.',
        )
    intent.refresh_from_db()

    consumption = create_confirmed_turno_from_locked_hold(
        hold=hold,
        operation_key=key,
        actor=actor,
    )
    if not consumption.succeeded:
        failed_at = database_now()
        failure_status = _terminal_failure_status(consumption.code)
        PaymentIntent.objects._transition(
            intent_id=intent.pk,
            from_statuses=[PaymentIntent.Status.APPROVED],
            status=failure_status,
            approved_at=None,
            terminal_at=failed_at,
            terminal_reason=consumption.code,
        )
        intent.refresh_from_db()
        case = _create_failure_case(
            intent=intent,
            hold=consumption.hold,
            payments=eligible,
            actor=actor,
            operation_key=key,
            code=consumption.code,
            detail=consumption.detail,
            failed_at=failed_at,
        )
        return PaymentConfirmationResult(
            intent=intent,
            hold=consumption.hold,
            turno=None,
            reconciliation_case=case,
            paid_reconciled=paid,
            changed=True,
            code=consumption.code,
            detail=consumption.detail,
        )

    PaymentIntent.objects._transition(
        intent_id=intent.pk,
        from_statuses=[PaymentIntent.Status.APPROVED],
        confirmed_turno_id=consumption.turno.pk,
    )
    Pago.objects._link_turno(
        payment_ids=[payment.pk for payment in eligible],
        turno_id=consumption.turno.pk,
    )
    intent.refresh_from_db()
    _audit_success(
        intent=intent,
        hold=consumption.hold,
        turno=consumption.turno,
        payments=eligible,
        actor=actor,
        operation_key=key,
        approved_at=now,
        previous_status=previous_status,
    )
    return PaymentConfirmationResult(
        intent=intent,
        hold=consumption.hold,
        turno=consumption.turno,
        reconciliation_case=None,
        paid_reconciled=paid,
        changed=True,
    )
