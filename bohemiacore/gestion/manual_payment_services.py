"""Pagos manuales y conciliación de booking."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
import hashlib
import re
import unicodedata

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from usuarios.models import Cliente
from usuarios.roles import BusinessPermission

from .models import (
    Auditoria,
    Pago,
    PaymentIntent,
    SlotHold,
    SlotHoldService,
    SolicitudTecnicaReserva,
)
from .payment_intent_services import _expire_locked_intent
from .payment_confirmation_services import (
    approve_payment_intent_and_confirm_booking,
)
from .slot_hold_clock import database_now
from .slot_hold_services import (
    _key_fingerprint,
    technical_request_is_current_for_hold,
)


PAYMENT_MANUAL_REGISTERED = 'PAYMENT_MANUAL_REGISTERED'
PAYMENT_RECONCILED = 'PAYMENT_RECONCILED'
PAYMENT_REJECTED = 'PAYMENT_REJECTED'
PAYMENT_INTENT_PENDING = 'PAYMENT_INTENT_PENDING'
LATE_MANUAL_REVIEW = 'LATE_MANUAL_REVIEW'

MAX_RECEIPT_SIZE = 5 * 1024 * 1024
ALLOWED_RECEIPT_TYPES = {
    'application/pdf': b'%PDF-',
    'image/png': b'\x89PNG\r\n\x1a\n',
    'image/jpeg': b'\xff\xd8\xff',
}
REFERENCE_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9._/\-]{2,79}$')
PAN_PATTERN = re.compile(r'(?<!\d)(?:\d[._/\-]?){12,18}\d(?!\d)')


class ManualPaymentError(ValueError):
    def __init__(self, code, detail, field='non_field_errors'):
        self.code = code
        self.detail = detail
        self.field = field
        super().__init__(detail)


class ManualPaymentPermissionDenied(ManualPaymentError):
    def __init__(self):
        super().__init__(
            'PAYMENT_PERMISSION_DENIED',
            'No tiene el permiso financiero requerido.',
        )


class ManualPaymentNotFound(ManualPaymentError):
    def __init__(self):
        super().__init__('PAYMENT_NOT_FOUND', 'El recurso financiero no existe.')


class ManualPaymentConflict(ManualPaymentError):
    pass


@dataclass(frozen=True)
class FinancialSnapshot:
    paid_reconciled: Decimal
    confirmation_due: Decimal
    balance: Decimal
    financial_threshold_reached: bool


@dataclass(frozen=True)
class ManualPaymentRegisterResult:
    payment: Pago | None
    created: bool
    financial: FinancialSnapshot | None = None
    code: str = ''
    detail: str = ''

    @property
    def succeeded(self):
        return self.payment is not None


@dataclass(frozen=True)
class ManualPaymentReconcileResult:
    payment: Pago
    changed: bool
    previous_status: str
    current_status: str
    financial: FinancialSnapshot
    code: str = ''
    detail: str = ''


def financial_snapshot(intent):
    paid = (
        intent.payments.filter(status=Pago.Status.RECONCILED).aggregate(
            total=Sum('monto')
        )['total']
        or Decimal('0.00')
    )
    confirmation_due = max(intent.required_amount - paid, Decimal('0.00'))
    balance = max(intent.total_amount_snapshot - paid, Decimal('0.00'))
    return FinancialSnapshot(
        paid_reconciled=paid,
        confirmation_due=confirmation_due,
        balance=balance,
        financial_threshold_reached=paid >= intent.required_amount,
    )


def _authorized_actor(actor, permission):
    user_model = get_user_model()
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise ManualPaymentPermissionDenied()
    try:
        current_actor = user_model.objects.get(pk=actor.pk, is_active=True)
    except user_model.DoesNotExist as exc:
        raise ManualPaymentPermissionDenied() from exc
    if not current_actor.has_perm(permission):
        raise ManualPaymentPermissionDenied()
    return current_actor


def normalize_manual_reference(value):
    normalized = unicodedata.normalize('NFKC', value or '').strip().upper()
    normalized = re.sub(r'\s+', '', normalized)
    if not normalized:
        return ''
    if not REFERENCE_PATTERN.fullmatch(normalized):
        raise ManualPaymentError(
            'INVALID_MANUAL_REFERENCE',
            'La referencia sólo admite letras, números y . _ / - (3 a 80).',
            'manual_reference',
        )
    if PAN_PATTERN.search(normalized):
        raise ManualPaymentError(
            'SENSITIVE_CARD_DATA_FORBIDDEN',
            'No se permiten números completos de tarjeta en la referencia.',
            'manual_reference',
        )
    return normalized


def _receipt_digest(receipt):
    if receipt is None:
        return ''
    if receipt.size <= 0 or receipt.size > MAX_RECEIPT_SIZE:
        raise ManualPaymentError(
            'INVALID_RECEIPT_SIZE',
            'El comprobante debe pesar entre 1 byte y 5 MB.',
            'receipt',
        )
    content_type = getattr(receipt, 'content_type', '')
    signature = ALLOWED_RECEIPT_TYPES.get(content_type)
    if signature is None:
        raise ManualPaymentError(
            'INVALID_RECEIPT_MIME',
            'Sólo se aceptan comprobantes PDF, PNG o JPEG.',
            'receipt',
        )
    position = receipt.tell() if hasattr(receipt, 'tell') else 0
    receipt.seek(0)
    header = receipt.read(max(len(value) for value in ALLOWED_RECEIPT_TYPES.values()))
    receipt.seek(0)
    digest = hashlib.sha256()
    for chunk in receipt.chunks():
        digest.update(chunk)
    receipt.seek(0)
    if not header.startswith(signature):
        raise ManualPaymentError(
            'RECEIPT_CONTENT_MISMATCH',
            'El contenido del comprobante no coincide con su MIME.',
            'receipt',
        )
    return digest.hexdigest()


def _lock_intent_graph(public_id):
    try:
        target = PaymentIntent.objects.only(
            'pk',
            'solicitud_id',
            'slot_hold_id',
        ).get(public_id=public_id)
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=target.solicitud_id
        )
        hold = SlotHold.objects.select_for_update().get(pk=target.slot_hold_id)
        intent = PaymentIntent.objects.select_for_update().get(pk=target.pk)
        cliente = Cliente.objects.select_for_update().get(pk=intent.cliente_id)
        payments = list(
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
        raise ManualPaymentNotFound() from exc
    return solicitud, hold, intent, cliente, payments


def _same_registration_payload(
    payment,
    *,
    intent,
    amount,
    currency,
    method,
    purpose,
    occurred_at,
    manual_reference,
    receipt_sha256,
):
    return bool(
        payment.payment_intent_id == intent.pk
        and payment.monto == amount
        and payment.currency == currency
        and payment.metodo_pago == method
        and payment.purpose == purpose
        and payment.fecha_pago == occurred_at
        and payment.manual_reference == manual_reference
        and payment.receipt_sha256 == receipt_sha256
    )


def _intent_is_effectively_current(intent, hold, now):
    return bool(
        intent.status in PaymentIntent.ACTIVE_STATUSES
        and intent.expires_at > now
        and hold.state == SlotHold.State.ACTIVE
        and hold.expires_at > now
    )


def _intent_has_confirmed_booking(intent, hold):
    return bool(
        intent.status == PaymentIntent.Status.APPROVED
        and intent.confirmed_turno_id
        and hold.state == SlotHold.State.CONSUMED
        and hold.consumed_turno_id == intent.confirmed_turno_id
    )


def _audit_payment(*, event, payment, actor, previous_status, event_at):
    reference_hash = (
        hashlib.sha256(payment.manual_reference.encode('utf-8')).hexdigest()
        if payment.manual_reference
        else ''
    )
    Auditoria.objects.create(
        tabla=event,
        registro_id=payment.pk,
        usuario=actor,
        accion='ALTA' if event == PAYMENT_MANUAL_REGISTERED else 'MODIFICACION',
        valor_anterior=(
            {'status': previous_status}
            if previous_status is not None
            else None
        ),
        valor_nuevo={
            'event': event,
            'payment_id': payment.pk,
            'payment_public_id': str(payment.public_id),
            'intent_id': payment.payment_intent_id,
            'intent_public_id': str(payment.payment_intent.public_id),
            'hold_public_id': str(payment.payment_intent.slot_hold.public_id),
            'amount': str(payment.monto),
            'currency': payment.currency,
            'method': payment.metodo_pago,
            'previous_status': previous_status,
            'current_status': payment.status,
            'reason': payment.terminal_reason,
            'actor_id': actor.pk,
            'manual_reference_sha256': reference_hash,
            'idempotency_key_sha256': _key_fingerprint(
                payment.idempotency_key
            ),
            'event_at': event_at.isoformat(),
        },
    )


def _audit_intent_pending(*, intent, actor, event_at):
    Auditoria.objects.create(
        tabla=PAYMENT_INTENT_PENDING,
        registro_id=intent.pk,
        usuario=actor,
        accion='MODIFICACION',
        valor_anterior={'status': PaymentIntent.Status.CREATED},
        valor_nuevo={
            'event': PAYMENT_INTENT_PENDING,
            'intent_public_id': str(intent.public_id),
            'previous_status': PaymentIntent.Status.CREATED,
            'current_status': PaymentIntent.Status.PENDING,
            'actor_id': actor.pk,
            'event_at': event_at.isoformat(),
        },
    )


def _failure(code, detail):
    return ManualPaymentRegisterResult(
        payment=None,
        created=False,
        code=code,
        detail=detail,
    )


@transaction.atomic
def register_manual_payment(
    *,
    intent_public_id,
    amount,
    currency,
    method,
    purpose,
    occurred_at,
    manual_reference,
    receipt,
    idempotency_key,
    actor,
    late_evidence=False,
):
    current_actor = _authorized_actor(actor, BusinessPermission.REGISTER_PAYMENT)
    key = (idempotency_key or '').strip()
    if not key or len(key) > 128:
        raise ManualPaymentError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
            'idempotency_key',
        )
    try:
        amount = Decimal(amount)
    except Exception as exc:
        raise ManualPaymentError(
            'INVALID_PAYMENT_AMOUNT',
            'El importe no es válido.',
            'amount',
        ) from exc
    if amount <= 0:
        raise ManualPaymentError(
            'INVALID_PAYMENT_AMOUNT',
            'El importe debe ser mayor que cero.',
            'amount',
        )
    if method not in Pago.Method.values:
        raise ManualPaymentError(
            'INVALID_PAYMENT_METHOD',
            'El medio manual no es válido.',
            'method',
        )
    if purpose not in Pago.Purpose.values:
        raise ManualPaymentError(
            'INVALID_PAYMENT_PURPOSE',
            'El propósito del Pago no es válido.',
            'purpose',
        )
    if occurred_at is None or timezone.is_naive(occurred_at):
        raise ManualPaymentError(
            'INVALID_OCCURRED_AT',
            'occurred_at debe incluir zona horaria.',
            'occurred_at',
        )
    if occurred_at > timezone.now() + timedelta(minutes=5):
        raise ManualPaymentError(
            'INVALID_OCCURRED_AT',
            'occurred_at no puede estar en el futuro.',
            'occurred_at',
        )
    reference = normalize_manual_reference(manual_reference)
    receipt_sha256 = _receipt_digest(receipt)
    requires_evidence = method in {
        Pago.Method.BANK_TRANSFER,
        Pago.Method.EXTERNAL_CARD,
        Pago.Method.OTHER,
    }
    if requires_evidence and not reference:
        raise ManualPaymentError(
            'MANUAL_REFERENCE_REQUIRED',
            'El medio informado requiere una referencia.',
            'manual_reference',
        )
    if requires_evidence and receipt is None:
        raise ManualPaymentError(
            'PAYMENT_RECEIPT_REQUIRED',
            'El medio informado requiere un comprobante.',
            'receipt',
        )

    solicitud, hold, intent, _, locked_payments = _lock_intent_graph(
        intent_public_id
    )
    existing = next(
        (item for item in locked_payments if item.idempotency_key == key),
        None,
    )
    if existing is None:
        existing = Pago.objects.filter(idempotency_key=key).first()
    if existing is not None:
        if not _same_registration_payload(
            existing,
            intent=intent,
            amount=amount,
            currency=currency,
            method=method,
            purpose=purpose,
            occurred_at=occurred_at,
            manual_reference=reference,
            receipt_sha256=receipt_sha256,
        ):
            raise ManualPaymentConflict(
                'PAYMENT_IDEMPOTENCY_KEY_REUSED',
                'La clave ya fue usada con otro payload.',
            )
        return ManualPaymentRegisterResult(
            payment=existing,
            created=False,
            financial=financial_snapshot(intent),
        )

    if reference and method in {
        Pago.Method.BANK_TRANSFER,
        Pago.Method.EXTERNAL_CARD,
    }:
        duplicate_reference = Pago.objects.filter(
            payment_intent__isnull=False,
            metodo_pago=method,
            manual_reference=reference,
        ).first()
        if duplicate_reference is not None:
            raise ManualPaymentConflict(
                'MANUAL_REFERENCE_REUSED',
                'La referencia ya pertenece a otro Pago.',
                'manual_reference',
            )

    if currency != intent.currency:
        raise ManualPaymentError(
            'PAYMENT_CURRENCY_MISMATCH',
            'La moneda no coincide con el Intent.',
            'currency',
        )
    enabled_methods = set(intent.policy_snapshot.get('enabled_manual_methods', []))
    if method not in enabled_methods:
        raise ManualPaymentConflict(
            'PAYMENT_METHOD_NOT_ENABLED',
            'El medio no está habilitado por el snapshot de policy.',
            'method',
        )

    now = database_now()
    confirmed_booking = _intent_has_confirmed_booking(intent, hold)
    effective = _intent_is_effectively_current(intent, hold, now)
    if not effective and intent.status in PaymentIntent.ACTIVE_STATUSES:
        _expire_locked_intent(
            intent=intent,
            hold=hold,
            actor=current_actor,
            now=now,
        )
        intent.refresh_from_db()
    if not effective and not confirmed_booking:
        if not late_evidence or intent.status != PaymentIntent.Status.EXPIRED:
            return _failure(
                'PAYMENT_CONTEXT_EXPIRED',
                'El Intent/HOLD no está vigente para registrar el Pago.',
            )
        late_payment = True
    else:
        snapshots = tuple(
            SlotHoldService.objects.filter(hold=hold).order_by('orden', 'pk')
        )
        if not technical_request_is_current_for_hold(
            solicitud=solicitud,
            hold=hold,
            snapshots=snapshots,
        ) and method != Pago.Method.CASH:
            raise ManualPaymentConflict(
                'TECHNICAL_REQUEST_INVALIDATED',
                'La solicitud o evaluación técnica ya no está vigente.',
            )
        late_payment = False

    paid_before = sum(
        (
            item.monto
            for item in locked_payments
            if item.status == Pago.Status.RECONCILED
        ),
        Decimal('0.00'),
    )
    if paid_before + amount > intent.total_amount_snapshot:
        raise ManualPaymentConflict(
            'PAYMENT_OVERPAYMENT',
            'El Pago supera el saldo total del Intent.',
            'amount',
        )
    if confirmed_booking and purpose != Pago.Purpose.BALANCE:
        raise ManualPaymentConflict(
            'CONFIRMATION_PAYMENT_ALREADY_COMPLETED',
            'Después de confirmar el Turno sólo se admiten Pagos de saldo.',
            'purpose',
        )

    initial_status = (
        Pago.Status.RECONCILED
        if method == Pago.Method.CASH and not late_payment
        else Pago.Status.PENDING_RECONCILIATION
    )
    reconciled_at = now if initial_status == Pago.Status.RECONCILED else None
    reconciled_by = (
        current_actor if initial_status == Pago.Status.RECONCILED else None
    )
    terminal_reason = LATE_MANUAL_REVIEW if late_payment else ''
    try:
        with transaction.atomic():
            payment = Pago.objects._create_booking_from_service(
                payment_intent=intent,
                orden=None,
                turno_id=(
                    intent.confirmed_turno_id if confirmed_booking else None
                ),
                monto=amount,
                currency=currency,
                metodo_pago=method,
                purpose=purpose,
                status=initial_status,
                fecha_pago=occurred_at,
                recorded_at=now,
                recorded_by=current_actor,
                reconciled_at=reconciled_at,
                reconciled_by=reconciled_by,
                manual_reference=reference,
                comprobante_foto=receipt,
                receipt_sha256=receipt_sha256,
                idempotency_key=key,
                terminal_reason=terminal_reason,
                es_sena=purpose == Pago.Purpose.CONFIRMATION,
            )
            if not late_payment and intent.status == PaymentIntent.Status.CREATED:
                transitioned = PaymentIntent.objects._transition(
                    intent_id=intent.pk,
                    from_statuses=[PaymentIntent.Status.CREATED],
                    status=PaymentIntent.Status.PENDING,
                    pending_at=now,
                )
                intent.refresh_from_db()
                if transitioned:
                    _audit_intent_pending(
                        intent=intent,
                        actor=current_actor,
                        event_at=now,
                    )
            _audit_payment(
                event=PAYMENT_MANUAL_REGISTERED,
                payment=payment,
                actor=current_actor,
                previous_status=None,
                event_at=now,
            )
            if (
                initial_status == Pago.Status.RECONCILED
                and intent.status in PaymentIntent.ACTIVE_STATUSES
            ):
                approve_payment_intent_and_confirm_booking(
                    intent_id=intent.pk,
                    actor=current_actor,
                )
                payment.refresh_from_db()
    except IntegrityError as exc:
        existing = Pago.objects.filter(idempotency_key=key).first()
        if existing is not None:
            if _same_registration_payload(
                existing,
                intent=intent,
                amount=amount,
                currency=currency,
                method=method,
                purpose=purpose,
                occurred_at=occurred_at,
                manual_reference=reference,
                receipt_sha256=receipt_sha256,
            ):
                return ManualPaymentRegisterResult(
                    payment=existing,
                    created=False,
                    financial=financial_snapshot(intent),
                )
            raise ManualPaymentConflict(
                'PAYMENT_IDEMPOTENCY_KEY_REUSED',
                'La clave ya fue usada con otro payload.',
            ) from exc
        if reference and Pago.objects.filter(
            payment_intent__isnull=False,
            metodo_pago=method,
            manual_reference=reference,
        ).exists():
            raise ManualPaymentConflict(
                'MANUAL_REFERENCE_REUSED',
                'La referencia ya pertenece a otro Pago.',
                'manual_reference',
            ) from exc
        raise
    return ManualPaymentRegisterResult(
        payment=payment,
        created=True,
        financial=financial_snapshot(intent),
    )


def _lock_payment_graph(public_id):
    try:
        target = Pago.objects.only(
            'pk',
            'payment_intent_id',
        ).get(public_id=public_id, payment_intent__isnull=False)
    except Pago.DoesNotExist as exc:
        raise ManualPaymentNotFound() from exc
    solicitud, hold, intent, cliente, payments = _lock_intent_graph(
        PaymentIntent.objects.only('public_id').get(
            pk=target.payment_intent_id
        ).public_id
    )
    payment = next((item for item in payments if item.pk == target.pk), None)
    if payment is None:
        raise ManualPaymentNotFound()
    return solicitud, hold, intent, cliente, payments, payment


@transaction.atomic
def reconcile_manual_payment(*, payment_public_id, decision, reason, actor):
    current_actor = _authorized_actor(actor, BusinessPermission.CONFIRM_DEPOSIT)
    if decision not in {'ACCEPT', 'REJECT'}:
        raise ManualPaymentError(
            'INVALID_RECONCILIATION_DECISION',
            'La decisión debe ser ACCEPT o REJECT.',
            'decision',
        )
    normalized_reason = ' '.join((reason or '').strip().split())
    if decision == 'REJECT' and not normalized_reason:
        raise ManualPaymentError(
            'REJECTION_REASON_REQUIRED',
            'Debe informar una razón de rechazo.',
            'reason',
        )
    if len(normalized_reason) > 100:
        raise ManualPaymentError(
            'INVALID_TERMINAL_REASON',
            'La razón no puede superar 100 caracteres.',
            'reason',
        )

    _, hold, intent, _, locked_payments, payment = _lock_payment_graph(
        payment_public_id
    )
    desired_status = (
        Pago.Status.RECONCILED
        if decision == 'ACCEPT'
        else Pago.Status.REJECTED
    )
    if payment.status == desired_status:
        if (
            desired_status == Pago.Status.REJECTED
            and payment.terminal_reason != normalized_reason
        ):
            raise ManualPaymentConflict(
                'PAYMENT_ALREADY_DECIDED',
                'El Pago ya fue rechazado con otra razón.',
            )
        return ManualPaymentReconcileResult(
            payment=payment,
            changed=False,
            previous_status=payment.status,
            current_status=payment.status,
            financial=financial_snapshot(intent),
        )
    if payment.status != Pago.Status.PENDING_RECONCILIATION:
        raise ManualPaymentConflict(
            'PAYMENT_ALREADY_DECIDED',
            'El Pago ya tiene una decisión terminal.',
        )

    now = database_now()
    confirmed_booking = _intent_has_confirmed_booking(intent, hold)
    if decision == 'ACCEPT':
        if payment.terminal_reason == LATE_MANUAL_REVIEW:
            raise ManualPaymentConflict(
                'LATE_PAYMENT_REQUIRES_FUTURE_REVIEW',
                'B2 no concilia como aplicable un Pago tardío.',
            )
        if (
            not confirmed_booking
            and not _intent_is_effectively_current(intent, hold, now)
        ):
            if intent.status in PaymentIntent.ACTIVE_STATUSES:
                _expire_locked_intent(
                    intent=intent,
                    hold=hold,
                    actor=current_actor,
                    now=now,
                )
                intent.refresh_from_db()
            return ManualPaymentReconcileResult(
                payment=payment,
                changed=False,
                previous_status=payment.status,
                current_status=payment.status,
                financial=financial_snapshot(intent),
                code='PAYMENT_CONTEXT_EXPIRED',
                detail='El Intent/HOLD venció antes de la conciliación.',
            )
        paid_other = sum(
            (
                item.monto
                for item in locked_payments
                if item.pk != payment.pk
                and item.status == Pago.Status.RECONCILED
            ),
            Decimal('0.00'),
        )
        if paid_other + payment.monto > intent.total_amount_snapshot:
            raise ManualPaymentConflict(
                'PAYMENT_OVERPAYMENT',
                'Conciliar este Pago superaría el total del Intent.',
            )

    previous = payment.status
    event = PAYMENT_RECONCILED if decision == 'ACCEPT' else PAYMENT_REJECTED
    changed = Pago.objects._transition(
        payment_id=payment.pk,
        from_statuses=[Pago.Status.PENDING_RECONCILIATION],
        status=desired_status,
        reconciled_at=now,
        reconciled_by=current_actor,
        terminal_reason='' if decision == 'ACCEPT' else normalized_reason,
    )
    payment.refresh_from_db()
    if changed:
        _audit_payment(
            event=event,
            payment=payment,
            actor=current_actor,
            previous_status=previous,
            event_at=now,
        )
        if decision == 'ACCEPT':
            if intent.status in PaymentIntent.ACTIVE_STATUSES:
                approve_payment_intent_and_confirm_booking(
                    intent_id=intent.pk,
                    actor=current_actor,
                )
                payment.refresh_from_db()
            elif confirmed_booking:
                Pago.objects._link_turno(
                    payment_ids=[payment.pk],
                    turno_id=intent.confirmed_turno_id,
                )
                payment.refresh_from_db()
    return ManualPaymentReconcileResult(
        payment=payment,
        changed=bool(changed),
        previous_status=previous,
        current_status=payment.status,
        financial=financial_snapshot(intent),
    )


def actor_can_read_payment(actor, payment):
    if not getattr(actor, 'is_authenticated', False):
        return False
    if actor.has_perm(BusinessPermission.VIEW_FINANCIAL_REPORTS):
        return True
    if actor.has_perm(BusinessPermission.REGISTER_PAYMENT):
        return True
    if actor.has_perm(BusinessPermission.CONFIRM_DEPOSIT):
        return True
    if payment.payment_intent_id:
        return payment.payment_intent.cliente.usuario_id == actor.pk
    if payment.orden_id:
        return payment.orden.cliente.usuario_id == actor.pk
    return False
