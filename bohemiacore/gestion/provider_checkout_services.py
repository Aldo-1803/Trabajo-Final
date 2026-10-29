"""Orquestación TX1 -> HTTP -> TX2 para checkout externo (BH-058 C1)."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
import hashlib
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from decouple import config

from usuarios.models import Cliente
from usuarios.roles import BusinessPermission

from .models import (
    Carrito,
    CompromisoStock,
    OrdenCompra,
    OrdenItem,
    Pago,
    PaymentIntent,
    ProviderPaymentAttempt,
    SlotHold,
)
from .order_inventory_services import create_order_stock_commitments
from .payment_providers import (
    CheckoutRequest,
    PaymentProviderError,
    get_payment_provider,
)
from .slot_hold_clock import database_now


class ProviderCheckoutError(Exception):
    default_code = 'CHECKOUT_ERROR'

    def __init__(self, detail, *, code=None, field=None):
        self.code = code or self.default_code
        self.detail = detail
        self.field = field
        super().__init__(detail)


class ProviderCheckoutInvalid(ProviderCheckoutError):
    default_code = 'CHECKOUT_INVALID'


class ProviderCheckoutPermissionDenied(ProviderCheckoutError):
    default_code = 'CHECKOUT_PERMISSION_DENIED'


class ProviderCheckoutNotFound(ProviderCheckoutError):
    default_code = 'CHECKOUT_OBLIGATION_NOT_FOUND'


class ProviderCheckoutConflict(ProviderCheckoutError):
    default_code = 'CHECKOUT_CONFLICT'


@dataclass(frozen=True)
class CheckoutResult:
    attempt: ProviderPaymentAttempt
    created: bool


def _validate_client_key(value):
    value = str(value or '').strip()
    if not value:
        raise ProviderCheckoutInvalid(
            'Debe informar el header Idempotency-Key.',
            code='IDEMPOTENCY_KEY_REQUIRED',
            field='Idempotency-Key',
        )
    if len(value) > 128:
        raise ProviderCheckoutInvalid(
            'Idempotency-Key no puede superar 128 caracteres.',
            code='IDEMPOTENCY_KEY_TOO_LONG',
            field='Idempotency-Key',
        )
    return value


def _validate_channel(channel):
    allowed = {choice for choice, _ in ProviderPaymentAttempt.Channel.choices}
    if channel not in allowed:
        raise ProviderCheckoutInvalid(
            'Canal de checkout no válido.',
            code='INVALID_CHECKOUT_CHANNEL',
            field='channel',
        )
    return channel


def _authorize(actor, owner_user_id, channel):
    operational = actor.has_perm(BusinessPermission.REGISTER_PAYMENT)
    if channel == ProviderPaymentAttempt.Channel.IN_PERSON and not operational:
        raise ProviderCheckoutPermissionDenied(
            'El enlace presencial requiere permiso para registrar pagos.',
            code='IN_PERSON_CHECKOUT_PERMISSION_REQUIRED',
        )
    if actor.pk != owner_user_id and not operational:
        raise ProviderCheckoutPermissionDenied(
            'No tiene autoridad sobre esta obligación financiera.'
        )


def _fingerprint(*parts):
    canonical = '|'.join(str(part) for part in parts)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _amount_text(value):
    return format(Decimal(value).quantize(Decimal('0.01')), 'f')


def _order_checkout_expiry(now):
    raw = getattr(
        settings,
        'MERCADO_PAGO_CHECKOUT_TTL_MINUTES',
        config('MERCADO_PAGO_CHECKOUT_TTL_MINUTES', default='30'),
    )
    try:
        minutes = int(raw)
    except (TypeError, ValueError) as exc:
        raise ProviderCheckoutInvalid(
            'La vigencia configurada del checkout no es válida.',
            code='CHECKOUT_CONFIGURATION_INVALID',
        ) from exc
    if minutes < 1 or minutes > 1440:
        raise ProviderCheckoutInvalid(
            'La vigencia del checkout debe estar entre 1 y 1440 minutos.',
            code='CHECKOUT_CONFIGURATION_INVALID',
        )
    return now + timedelta(minutes=minutes)


def _assert_booking_obligation(intent, now):
    hold = intent.slot_hold
    if intent.status not in PaymentIntent.ACTIVE_STATUSES:
        raise ProviderCheckoutConflict(
            'El PaymentIntent ya no está vigente.',
            code='PAYMENT_INTENT_NOT_ACTIVE',
        )
    if intent.expires_at <= now:
        raise ProviderCheckoutConflict(
            'El PaymentIntent venció.',
            code='PAYMENT_INTENT_EXPIRED',
        )
    if hold.state != SlotHold.State.ACTIVE or hold.expires_at <= now:
        raise ProviderCheckoutConflict(
            'El HOLD ya no está vigente.',
            code='SLOT_HOLD_NOT_ACTIVE',
        )
    if intent.payments.exclude(status=Pago.Status.REJECTED).exists():
        raise ProviderCheckoutConflict(
            'La obligación ya posee registros de pago.',
            code='OBLIGATION_ALREADY_HAS_PAYMENTS',
        )


def _locked_order_items(order):
    return list(
        OrdenItem.objects.select_for_update()
        .filter(orden=order)
        .select_related('producto')
        .order_by('pk')
    )


def _assert_order_obligation(order, items):
    if order.estado not in {'PENDIENTE', 'ESPERANDO_PAGO'}:
        raise ProviderCheckoutConflict(
            'La orden ya no admite checkout.',
            code='ORDER_NOT_PAYABLE',
        )
    if not items:
        raise ProviderCheckoutInvalid(
            'La orden no contiene productos verificables.',
            code='ORDER_WITHOUT_ITEMS',
        )
    computed = sum(
        (item.precio_historico * item.cantidad for item in items),
        Decimal('0.00'),
    )
    if computed != order.total or order.total <= 0:
        raise ProviderCheckoutConflict(
            'El total congelado no coincide con las líneas de la orden.',
            code='ORDER_TOTAL_MISMATCH',
        )
    if order.pagos.exclude(status__in=[Pago.Status.REJECTED, Pago.Status.REVERSED]).exists():
        raise ProviderCheckoutConflict(
            'La orden ya posee registros de pago.',
            code='OBLIGATION_ALREADY_HAS_PAYMENTS',
        )
    commitments = {
        row['producto_id']: row
        for row in CompromisoStock.objects.filter(
            orden=order,
            estado=CompromisoStock.State.ACTIVE,
        ).values('producto_id', 'cantidad')
    }
    expected = {}
    for item in items:
        expected[item.producto_id] = (
            expected.get(item.producto_id, 0) + item.cantidad
        )
    actual = {key: value['cantidad'] for key, value in commitments.items()}
    if actual != expected:
        raise ProviderCheckoutConflict(
            'La orden no tiene compromisos de stock activos y coherentes.',
            code='ORDER_STOCK_COMMITMENT_MISMATCH',
        )


def _existing_for_key(actor, key):
    return (
        ProviderPaymentAttempt.objects.select_for_update()
        .filter(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            created_by=actor,
            client_idempotency_key=key,
        )
        .first()
    )


def _reuse_or_retry(existing, *, fingerprint, context, channel, now):
    if existing.request_fingerprint != fingerprint:
        raise ProviderCheckoutConflict(
            'Idempotency-Key ya fue usado con otra solicitud.',
            code='IDEMPOTENCY_KEY_REUSED',
            field='Idempotency-Key',
        )
    if existing.context != context or existing.channel != channel:
        raise ProviderCheckoutConflict(
            'Idempotency-Key ya fue usado con otro contexto.',
            code='IDEMPOTENCY_KEY_REUSED',
            field='Idempotency-Key',
        )
    if existing.status == ProviderPaymentAttempt.Status.PROCESSING:
        raise ProviderCheckoutConflict(
            'La solicitud al proveedor todavía está en curso.',
            code='PROVIDER_REQUEST_IN_PROGRESS',
        )
    if (
        existing.status == ProviderPaymentAttempt.Status.READY
        and existing.provider_expires_at
        and existing.provider_expires_at <= now
    ):
        existing.status = ProviderPaymentAttempt.Status.EXPIRED
        existing.checkout_url = ''
        existing.error_code = 'PROVIDER_CHECKOUT_EXPIRED'
        existing.error_detail = 'El checkout del proveedor ya venció.'
        existing.save(update_fields=[
            'status', 'checkout_url', 'error_code', 'error_detail', 'updated_at'
        ])
        return existing, False
    if existing.status == ProviderPaymentAttempt.Status.OUTCOME_UNKNOWN:
        existing.status = ProviderPaymentAttempt.Status.PROCESSING
        existing.error_code = ''
        existing.error_detail = ''
        existing.save(update_fields=[
            'status', 'error_code', 'error_detail', 'updated_at'
        ])
        return existing, True
    if (
        existing.status == ProviderPaymentAttempt.Status.FAILED
        and existing.error_code in {
            'PROVIDER_CONFIGURATION_ERROR',
            'CHECKOUT_CONFIGURATION_INVALID',
        }
    ):
        # No hubo una llamada válida al proveedor; es seguro reintentar el
        # mismo Attempt después de corregir configuración, sin nueva orden.
        existing.status = ProviderPaymentAttempt.Status.PROCESSING
        existing.error_code = ''
        existing.error_detail = ''
        existing.save(update_fields=[
            'status', 'error_code', 'error_detail', 'updated_at'
        ])
        return existing, True
    return existing, False


def _new_attempt(*, actor, key, context, channel, amount, currency,
                 payment_intent=None, order=None):
    public_id = uuid.uuid4()
    obligation = (
        str(payment_intent.public_id) if payment_intent is not None else str(order.pk)
    )
    fingerprint = _fingerprint(context, obligation, channel, amount, currency)
    return ProviderPaymentAttempt.objects.create(
        public_id=public_id,
        provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
        context=context,
        channel=channel,
        payment_intent=payment_intent,
        order=order,
        amount=amount,
        currency=currency,
        external_reference=f'bh:c1:{context.lower()}:{public_id.hex}',
        client_idempotency_key=key,
        provider_idempotency_key=f'bh-c1-{public_id.hex}',
        request_fingerprint=fingerprint,
        created_by=actor,
    )


def _booking_tx1(*, intent_public_id, actor, key, channel):
    now = database_now()
    try:
        intent = (
            PaymentIntent.objects.select_for_update()
            .select_related('slot_hold', 'cliente__usuario')
            .get(public_id=intent_public_id)
        )
    except PaymentIntent.DoesNotExist as exc:
        raise ProviderCheckoutNotFound('PaymentIntent no encontrado.') from exc
    _authorize(actor, intent.cliente.usuario_id, channel)
    _assert_booking_obligation(intent, now)
    fingerprint = _fingerprint(
        ProviderPaymentAttempt.Context.BOOKING,
        intent.public_id,
        channel,
        intent.required_amount,
        intent.currency,
    )
    existing = _existing_for_key(actor, key)
    if existing:
        return _reuse_or_retry(
            existing,
            fingerprint=fingerprint,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=channel,
            now=now,
        )
    active = (
        ProviderPaymentAttempt.objects.select_for_update()
        .filter(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            payment_intent=intent,
            status__in=ProviderPaymentAttempt.ACTIVE_STATUSES,
        )
        .first()
    )
    if active:
        if (
            active.status == ProviderPaymentAttempt.Status.READY
            and active.provider_expires_at
            and active.provider_expires_at <= now
        ):
            active.status = ProviderPaymentAttempt.Status.EXPIRED
            active.checkout_url = ''
            active.error_code = 'PROVIDER_CHECKOUT_EXPIRED'
            active.error_detail = 'El checkout del proveedor ya venció.'
            active.save(update_fields=[
                'status', 'checkout_url', 'error_code', 'error_detail', 'updated_at'
            ])
            active = None
    if active:
        return active, False
    return _new_attempt(
        actor=actor,
        key=key,
        context=ProviderPaymentAttempt.Context.BOOKING,
        channel=channel,
        amount=intent.required_amount,
        currency=intent.currency,
        payment_intent=intent,
    ), True


def _order_tx1(*, order_id, actor, key, channel):
    now = database_now()
    try:
        order = (
            OrdenCompra.objects.select_for_update()
            .select_related('cliente__usuario')
            .get(pk=order_id)
        )
    except OrdenCompra.DoesNotExist as exc:
        raise ProviderCheckoutNotFound('Orden no encontrada.') from exc
    _authorize(actor, order.cliente.usuario_id, channel)
    items = _locked_order_items(order)
    _assert_order_obligation(order, items)
    fingerprint = _fingerprint(
        ProviderPaymentAttempt.Context.ORDER,
        order.pk,
        channel,
        order.total,
        'ARS',
    )
    existing = _existing_for_key(actor, key)
    if existing:
        return _reuse_or_retry(
            existing,
            fingerprint=fingerprint,
            context=ProviderPaymentAttempt.Context.ORDER,
            channel=channel,
            now=now,
        )
    active = (
        ProviderPaymentAttempt.objects.select_for_update()
        .filter(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            order=order,
            status__in=ProviderPaymentAttempt.ACTIVE_STATUSES,
        )
        .first()
    )
    if active:
        if (
            active.status == ProviderPaymentAttempt.Status.READY
            and active.provider_expires_at
            and active.provider_expires_at <= now
        ):
            active.status = ProviderPaymentAttempt.Status.EXPIRED
            active.checkout_url = ''
            active.error_code = 'PROVIDER_CHECKOUT_EXPIRED'
            active.error_detail = 'El checkout del proveedor ya venció.'
            active.save(update_fields=[
                'status', 'checkout_url', 'error_code', 'error_detail', 'updated_at'
            ])
            active = None
    if active:
        return active, False
    return _new_attempt(
        actor=actor,
        key=key,
        context=ProviderPaymentAttempt.Context.ORDER,
        channel=channel,
        amount=order.total,
        currency='ARS',
        order=order,
    ), True


def _cart_tx1(*, actor, key):
    existing = _existing_for_key(actor, key)
    if existing:
        if existing.context != ProviderPaymentAttempt.Context.ORDER:
            raise ProviderCheckoutConflict(
                'Idempotency-Key ya fue usado con otro contexto.',
                code='IDEMPOTENCY_KEY_REUSED',
            )
        fingerprint = _fingerprint(
            ProviderPaymentAttempt.Context.ORDER,
            existing.order_id,
            ProviderPaymentAttempt.Channel.ONLINE,
            existing.amount,
            existing.currency,
        )
        return _reuse_or_retry(
            existing,
            fingerprint=fingerprint,
            context=ProviderPaymentAttempt.Context.ORDER,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            now=database_now(),
        )
    try:
        cliente = Cliente.objects.select_for_update().get(usuario=actor)
    except Cliente.DoesNotExist as exc:
        raise ProviderCheckoutPermissionDenied(
            'El usuario no tiene perfil de Cliente.'
        ) from exc
    carrito, _ = Carrito.objects.get_or_create(cliente=cliente)
    carrito = Carrito.objects.select_for_update().get(pk=carrito.pk)
    cart_items = list(
        carrito.items.select_for_update()
        .select_related('producto')
        .order_by('pk')
    )
    if not cart_items:
        raise ProviderCheckoutInvalid(
            'El carrito está vacío.',
            code='EMPTY_CART',
        )
    total = sum(
        (item.producto.precio * item.cantidad for item in cart_items),
        Decimal('0.00'),
    )
    if total <= 0:
        raise ProviderCheckoutInvalid('El total del carrito no es válido.')
    order = OrdenCompra.objects.create(
        codigo=f'ORD-{uuid.uuid4().hex[:8].upper()}',
        cliente=cliente,
        estado='ESPERANDO_PAGO',
        total=total,
    )
    OrdenItem.objects.bulk_create([
        OrdenItem(
            orden=order,
            producto=item.producto,
            cantidad=item.cantidad,
            precio_historico=item.producto.precio,
        )
        for item in cart_items
    ])
    create_order_stock_commitments(order.pk)
    attempt = _new_attempt(
        actor=actor,
        key=key,
        context=ProviderPaymentAttempt.Context.ORDER,
        channel=ProviderPaymentAttempt.Channel.ONLINE,
        amount=total,
        currency='ARS',
        order=order,
    )
    carrito.items.all().delete()
    return attempt, True


def _obligation_still_valid(attempt, now):
    try:
        if attempt.context == ProviderPaymentAttempt.Context.BOOKING:
            intent = (
                PaymentIntent.objects.select_for_update()
                .select_related('slot_hold')
                .get(pk=attempt.payment_intent_id)
            )
            _assert_booking_obligation(intent, now)
            return min(intent.expires_at, intent.slot_hold.expires_at)
        order = OrdenCompra.objects.select_for_update().get(pk=attempt.order_id)
        items = _locked_order_items(order)
        _assert_order_obligation(order, items)
        return _order_checkout_expiry(now)
    except ProviderCheckoutError:
        return None


def _request_expiry(attempt, now):
    if attempt.context == ProviderPaymentAttempt.Context.BOOKING:
        intent = PaymentIntent.objects.select_related('slot_hold').get(
            pk=attempt.payment_intent_id
        )
        return min(intent.expires_at, intent.slot_hold.expires_at)
    return _order_checkout_expiry(now)


def _call_provider(attempt):
    with transaction.atomic():
        locked = ProviderPaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status != ProviderPaymentAttempt.Status.PROCESSING:
            return locked
        now = database_now()
        try:
            expiry = _request_expiry(locked, now)
        except ProviderCheckoutError as exc:
            locked.status = ProviderPaymentAttempt.Status.FAILED
            locked.error_code = exc.code
            locked.error_detail = exc.detail[:200]
            locked.response_received_at = now
            locked.save(update_fields=[
                'status', 'error_code', 'error_detail',
                'response_received_at', 'updated_at',
            ])
            return locked
        locked.provider_call_count = F('provider_call_count') + 1
        locked.last_provider_call_at = now
        locked.save(update_fields=['provider_call_count', 'last_provider_call_at', 'updated_at'])
        payer_email = (
            locked.payment_intent.cliente.usuario.email
            if locked.payment_intent_id
            else locked.order.cliente.usuario.email
        )
        title = (
            'Reserva Bohemia Hair'
            if locked.context == ProviderPaymentAttempt.Context.BOOKING
            else f'Compra Bohemia Hair - {locked.order.codigo}'
        )
        request = CheckoutRequest(
            external_reference=locked.external_reference,
            idempotency_key=locked.provider_idempotency_key,
            amount=_amount_text(locked.amount),
            currency=locked.currency,
            payer_email=payer_email,
            title=title,
            expires_at=expiry,
        )

    created = None
    error = None
    try:
        created = get_payment_provider(attempt.provider).create_checkout(request)
    except PaymentProviderError as exc:
        error = exc

    with transaction.atomic():
        # Mantener el mismo orden de locks que TX1: obligación -> Attempt.
        # Así un TX1 concurrente nunca retiene la obligación mientras espera
        # un Attempt que TX2 retiene antes de pedir esa misma obligación.
        snapshot = ProviderPaymentAttempt.objects.get(pk=attempt.pk)
        now = database_now()
        valid_until = (
            _obligation_still_valid(snapshot, now) if error is None else None
        )
        locked = ProviderPaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status != ProviderPaymentAttempt.Status.PROCESSING:
            return locked
        locked.response_received_at = now
        if error is not None:
            locked.status = (
                ProviderPaymentAttempt.Status.OUTCOME_UNKNOWN
                if error.outcome_unknown
                else ProviderPaymentAttempt.Status.FAILED
            )
            locked.error_code = error.code
            locked.error_detail = str(error.detail)[:200]
            locked.checkout_url = ''
            locked.save(update_fields=[
                'status', 'error_code', 'error_detail', 'checkout_url',
                'response_received_at', 'updated_at',
            ])
            return locked

        locked.provider_order_id = created.provider_order_id
        locked.provider_status = created.provider_status
        locked.provider_expires_at = created.expires_at
        provider_expired = created.expires_at and created.expires_at <= now
        if valid_until is None or valid_until <= now or provider_expired:
            locked.status = ProviderPaymentAttempt.Status.EXPIRED
            locked.checkout_url = ''
            locked.error_code = 'OBLIGATION_NO_LONGER_ACTIVE'
            locked.error_detail = 'La obligación venció durante la creación del checkout.'
        else:
            locked.status = ProviderPaymentAttempt.Status.READY
            locked.checkout_url = created.checkout_url
            locked.error_code = ''
            locked.error_detail = ''
        locked.save(update_fields=[
            'status', 'provider_order_id', 'provider_status',
            'provider_expires_at', 'checkout_url', 'error_code',
            'error_detail', 'response_received_at', 'updated_at',
        ])
        return locked


def _run(tx1):
    try:
        with transaction.atomic():
            attempt, should_call = tx1()
    except IntegrityError as exc:
        raise ProviderCheckoutConflict(
            'Otro checkout para la misma obligación se creó concurrentemente.',
            code='CHECKOUT_CONCURRENT_REQUEST',
        ) from exc
    if not should_call:
        return CheckoutResult(attempt=attempt, created=False)
    attempt_created = attempt.provider_call_count == 0
    return CheckoutResult(
        attempt=_call_provider(attempt),
        created=attempt_created,
    )


def start_booking_checkout(*, intent_public_id, actor, idempotency_key, channel):
    key = _validate_client_key(idempotency_key)
    channel = _validate_channel(channel)
    return _run(lambda: _booking_tx1(
        intent_public_id=intent_public_id,
        actor=actor,
        key=key,
        channel=channel,
    ))


def start_order_checkout(*, order_id, actor, idempotency_key, channel):
    key = _validate_client_key(idempotency_key)
    channel = _validate_channel(channel)
    return _run(lambda: _order_tx1(
        order_id=order_id,
        actor=actor,
        key=key,
        channel=channel,
    ))


def start_cart_checkout(*, actor, idempotency_key):
    key = _validate_client_key(idempotency_key)
    return _run(lambda: _cart_tx1(actor=actor, key=key))
