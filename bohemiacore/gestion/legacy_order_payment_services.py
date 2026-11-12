"""Hardening acotado del writer legacy de pagos de órdenes."""

from dataclasses import dataclass
from decimal import Decimal
import hashlib

from django.contrib.auth import get_user_model
from django.db import transaction

from usuarios.roles import BusinessPermission

from .models import Auditoria, OrdenCompra, Pago
from .slot_hold_clock import database_now


ORDER_MANUAL_PAYMENT_REGISTERED = 'ORDER_MANUAL_PAYMENT_REGISTERED'
PAYABLE_ORDER_STATES = {'PENDIENTE', 'ESPERANDO_PAGO'}


class LegacyOrderPaymentError(ValueError):
    def __init__(self, code, detail, field='non_field_errors'):
        self.code = code
        self.detail = detail
        self.field = field
        super().__init__(detail)


class LegacyOrderPaymentPermissionDenied(LegacyOrderPaymentError):
    def __init__(self):
        super().__init__(
            'ORDER_PAYMENT_PERMISSION_DENIED',
            'No tiene permisos para registrar pagos.',
        )


class LegacyOrderPaymentNotFound(LegacyOrderPaymentError):
    def __init__(self):
        super().__init__(
            'ORDER_PAYMENT_ORDER_NOT_FOUND',
            'La Orden no existe.',
        )


class LegacyOrderPaymentConflict(LegacyOrderPaymentError):
    pass


@dataclass(frozen=True)
class LegacyOrderPaymentResult:
    payment: Pago
    created: bool


def _authorized_actor(actor):
    user_model = get_user_model()
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise LegacyOrderPaymentPermissionDenied()
    try:
        current_actor = user_model.objects.get(pk=actor.pk, is_active=True)
    except user_model.DoesNotExist as exc:
        raise LegacyOrderPaymentPermissionDenied() from exc
    if not current_actor.has_perm(BusinessPermission.REGISTER_PAYMENT):
        raise LegacyOrderPaymentPermissionDenied()
    return current_actor


def _same_command(payment, *, order, amount, method, purpose):
    return bool(
        payment.orden_id == order.pk
        and payment.payment_intent_id is None
        and payment.monto == amount
        and payment.currency == 'ARS'
        and payment.metodo_pago == method
        and payment.purpose == purpose
    )


@transaction.atomic
def register_legacy_order_payment(
    *,
    order_id,
    amount,
    method,
    occurred_at,
    receipt,
    is_deposit,
    idempotency_key,
    actor,
):
    """Registra un pago legacy sin permitir estado terminal, retry doble ni sobrepago."""
    current_actor = _authorized_actor(actor)
    key = (idempotency_key or '').strip()
    if not key or len(key) > 128:
        raise LegacyOrderPaymentError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
            'idempotency_key',
        )
    try:
        amount = Decimal(amount)
    except Exception as exc:
        raise LegacyOrderPaymentError(
            'INVALID_ORDER_PAYMENT_AMOUNT',
            'El importe no es válido.',
            'monto',
        ) from exc
    if amount <= 0:
        raise LegacyOrderPaymentError(
            'INVALID_ORDER_PAYMENT_AMOUNT',
            'El importe debe ser mayor que cero.',
            'monto',
        )

    try:
        order = OrdenCompra.objects.select_for_update().get(pk=order_id)
    except OrdenCompra.DoesNotExist as exc:
        raise LegacyOrderPaymentNotFound() from exc

    payments = tuple(
        Pago.objects.select_for_update().filter(orden=order).order_by('pk')
    )
    existing = Pago.objects.select_for_update().filter(idempotency_key=key).first()
    purpose = (
        Pago.Purpose.CONFIRMATION if is_deposit else Pago.Purpose.BALANCE
    )
    if existing is not None:
        if not _same_command(
            existing,
            order=order,
            amount=amount,
            method=method,
            purpose=purpose,
        ):
            raise LegacyOrderPaymentConflict(
                'ORDER_PAYMENT_IDEMPOTENCY_KEY_REUSED',
                'La clave ya fue usada con otro comando de pago.',
                'idempotency_key',
            )
        return LegacyOrderPaymentResult(payment=existing, created=False)

    if order.estado not in PAYABLE_ORDER_STATES:
        raise LegacyOrderPaymentConflict(
            'ORDER_NOT_PAYABLE',
            'La Orden no admite pagos en su estado actual.',
        )
    paid = sum(
        (
            payment.monto
            for payment in payments
            if payment.status == Pago.Status.RECONCILED
        ),
        Decimal('0.00'),
    )
    if paid + amount > order.total:
        raise LegacyOrderPaymentConflict(
            'ORDER_PAYMENT_OVERPAYMENT',
            'El Pago supera el saldo de la Orden.',
            'monto',
        )

    now = database_now()
    payment = Pago.objects.create(
        orden=order,
        turno=None,
        payment_intent=None,
        monto=amount,
        currency='ARS',
        metodo_pago=method,
        purpose=purpose,
        status=Pago.Status.RECONCILED,
        fecha_pago=occurred_at,
        recorded_at=now,
        recorded_by=current_actor,
        reconciled_at=now,
        reconciled_by=current_actor,
        comprobante_foto=receipt,
        idempotency_key=key,
        es_sena=is_deposit,
    )
    Auditoria.objects.create(
        tabla=ORDER_MANUAL_PAYMENT_REGISTERED,
        registro_id=order.pk,
        usuario=current_actor,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': ORDER_MANUAL_PAYMENT_REGISTERED,
            'order_id': order.pk,
            'payment_id': payment.pk,
            'payment_public_id': str(payment.public_id),
            'amount': str(payment.monto),
            'currency': payment.currency,
            'method': payment.metodo_pago,
            'purpose': payment.purpose,
            'status': payment.status,
            'actor_id': current_actor.pk,
            'idempotency_key_sha256': hashlib.sha256(key.encode()).hexdigest(),
            'event_at': now.isoformat(),
        },
    )
    return LegacyOrderPaymentResult(payment=payment, created=True)
