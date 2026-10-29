"""Políticas e Intents financieros internos, sin registrar dinero (BH-058 B1)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from usuarios.models import Cliente
from usuarios.roles import BusinessPermission

from .models import (
    Auditoria,
    PAYMENT_CURRENCY_MINOR_UNITS,
    PaymentIntent,
    PaymentIntentLine,
    PaymentPolicy,
    Servicio,
    SlotHold,
    SlotHoldService,
    SolicitudTecnicaReserva,
)
from .slot_hold_clock import database_now
from .slot_hold_services import (
    SLOT_HOLD_RELEASED,
    _audit as audit_hold,
    _expire_locked_hold,
    _key_fingerprint,
    technical_request_is_current_for_hold,
)


PAYMENT_POLICY_PUBLISHED = 'PAYMENT_POLICY_PUBLISHED'
PAYMENT_INTENT_CREATED = 'PAYMENT_INTENT_CREATED'
PAYMENT_INTENT_CANCELLED = 'PAYMENT_INTENT_CANCELLED'
PAYMENT_INTENT_EXPIRED = 'PAYMENT_INTENT_EXPIRED'


class PaymentPolicyError(ValueError):
    pass


class PaymentPolicyPermissionDenied(PaymentPolicyError):
    pass


class PaymentPolicyNotFound(PaymentPolicyError):
    pass


class PaymentPolicyStateError(PaymentPolicyError):
    pass


class PaymentPolicyInvalid(PaymentPolicyError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__('La política de pago no es válida.')


class PaymentIntentError(ValueError):
    def __init__(self, code, detail, field='non_field_errors'):
        self.code = code
        self.detail = detail
        self.field = field
        super().__init__(detail)


class PaymentIntentNotFound(PaymentIntentError):
    def __init__(self):
        super().__init__('PAYMENT_INTENT_NOT_FOUND', 'El Intent no existe.')


class PaymentIntentConflict(PaymentIntentError):
    pass


@dataclass(frozen=True)
class PaymentIntentCreateResult:
    intent: PaymentIntent | None
    created: bool
    code: str = ''
    detail: str = ''

    @property
    def succeeded(self):
        return self.intent is not None


@dataclass(frozen=True)
class PaymentIntentTransitionResult:
    intent: PaymentIntent
    hold: SlotHold
    changed: bool
    previous_status: str
    current_status: str
    code: str = ''


@dataclass(frozen=True)
class PaymentIntentModeOption:
    mode: str
    required_amount: Decimal


@dataclass(frozen=True)
class PaymentIntentOptionsResult:
    hold: SlotHold
    existing_intent: PaymentIntent | None
    policy_version: str
    total_amount: Decimal
    currency: str
    expires_at: datetime
    modes: tuple[PaymentIntentModeOption, ...]


def _authorized_policy_actor(actor):
    user_model = get_user_model()
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PaymentPolicyPermissionDenied
    try:
        current_actor = user_model.objects.get(pk=actor.pk, is_active=True)
    except user_model.DoesNotExist as exc:
        raise PaymentPolicyPermissionDenied from exc
    if not current_actor.has_perm(
        BusinessPermission.MANAGE_PAYMENT_CONFIGURATION
    ):
        raise PaymentPolicyPermissionDenied
    return current_actor


@transaction.atomic
def publish_payment_policy(*, policy_id, actor):
    current_actor = _authorized_policy_actor(actor)
    policies = list(
        PaymentPolicy.objects.select_for_update().order_by('pk')
    )
    policy = next((item for item in policies if item.pk == policy_id), None)
    if policy is None:
        raise PaymentPolicyNotFound
    if policy.status != PaymentPolicy.Status.DRAFT:
        raise PaymentPolicyStateError(
            'Sólo una política de pago en borrador puede publicarse.'
        )
    try:
        policy.full_clean()
    except ValidationError as exc:
        raise PaymentPolicyInvalid(
            getattr(exc, 'message_dict', {'non_field_errors': exc.messages})
        ) from exc

    published_at = database_now()
    PaymentPolicy.objects._retire_published(exclude_id=policy.pk)
    policy.status = PaymentPolicy.Status.PUBLISHED
    policy.published_at = published_at
    policy._allow_publication_transition = True
    policy.save(update_fields=['status', 'published_at'])
    Auditoria.objects.create(
        tabla=PAYMENT_POLICY_PUBLISHED,
        registro_id=policy.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={'status': PaymentPolicy.Status.DRAFT},
        valor_nuevo={
            'event': PAYMENT_POLICY_PUBLISHED,
            'status': PaymentPolicy.Status.PUBLISHED,
            'version': policy.version,
            'actor_id': current_actor.pk,
            'published_at': published_at.isoformat(),
        },
    )
    return policy


def _money_quantum(currency):
    try:
        minor_units = PAYMENT_CURRENCY_MINOR_UNITS[currency]
    except KeyError as exc:
        raise PaymentIntentConflict(
            'UNSUPPORTED_CURRENCY',
            'La moneda de la política no está soportada.',
        ) from exc
    return Decimal('1').scaleb(-minor_units)


def _quantize(value, currency):
    return Decimal(value).quantize(_money_quantum(currency), rounding=ROUND_HALF_UP)


def _policy_snapshot(policy):
    return {
        'version': policy.version,
        'allowed_mode': policy.allowed_mode,
        'deposit_kind': policy.deposit_kind,
        'deposit_value': (
            str(policy.deposit_value)
            if policy.deposit_value is not None
            else None
        ),
        'fixed_exceeds_total_behavior': policy.fixed_exceeds_total_behavior,
        'currency': policy.currency,
        'intent_ttl_minutes': policy.intent_ttl_minutes,
        'enabled_manual_methods': list(policy.enabled_manual_methods),
    }


def _allowed_modes(policy):
    return {
        PaymentPolicy.AllowedMode.DEPOSIT_ONLY: {PaymentIntent.Mode.DEPOSIT},
        PaymentPolicy.AllowedMode.FULL_ONLY: {PaymentIntent.Mode.FULL},
        PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL: {
            PaymentIntent.Mode.DEPOSIT,
            PaymentIntent.Mode.FULL,
        },
    }[policy.allowed_mode]


def _validate_mode(policy, mode):
    valid_modes = _allowed_modes(policy)
    if mode not in valid_modes:
        raise PaymentIntentConflict(
            'PAYMENT_MODE_NOT_ALLOWED',
            'La modalidad no está habilitada por la política vigente.',
            'mode',
        )


def _required_amount(*, policy, mode, total):
    if mode == PaymentIntent.Mode.FULL:
        required = total
    elif policy.deposit_kind == PaymentPolicy.DepositKind.PERCENTAGE:
        required = _quantize(
            total * policy.deposit_value / Decimal('100'),
            policy.currency,
        )
    else:
        required = _quantize(policy.deposit_value, policy.currency)
        if required > total:
            if (
                policy.fixed_exceeds_total_behavior
                == PaymentPolicy.FixedExceedsTotalBehavior.CAP_TO_TOTAL
            ):
                required = total
            else:
                raise PaymentIntentConflict(
                    'FIXED_DEPOSIT_EXCEEDS_TOTAL',
                    'La seña fija supera el total y la política exige rechazar.',
                )
    if required <= 0 or required > total:
        raise PaymentIntentConflict(
            'INVALID_REQUIRED_AMOUNT',
            'El monto requerido calculado no es válido.',
        )
    return required


def _audit_intent(*, event, intent, actor, previous_status, reason=''):
    payload = {
        'event': event,
        'intent_public_id': str(intent.public_id),
        'intent_id': intent.pk,
        'hold_public_id': str(intent.slot_hold.public_id),
        'solicitud_id': intent.solicitud_id,
        'cliente_id': intent.cliente_id,
        'policy_id': intent.policy_id,
        'policy_version': intent.policy_snapshot['version'],
        'mode': intent.mode,
        'total_amount_snapshot': str(intent.total_amount_snapshot),
        'required_amount': str(intent.required_amount),
        'currency': intent.currency,
        'previous_status': previous_status,
        'current_status': intent.status,
        'reason': reason,
        'actor': getattr(actor, 'pk', None) or 'SYSTEM',
        'event_at': (
            intent.terminal_at or intent.created_at
        ).isoformat(),
    }
    if event == PAYMENT_INTENT_CREATED:
        payload['idempotency_key_sha256'] = _key_fingerprint(
            intent.idempotency_key
        )
    Auditoria.objects.create(
        tabla=event,
        registro_id=intent.pk,
        usuario=actor if getattr(actor, 'pk', None) else None,
        accion='ALTA' if event == PAYMENT_INTENT_CREATED else 'MODIFICACION',
        valor_anterior=(
            {'status': previous_status}
            if previous_status is not None
            else None
        ),
        valor_nuevo=payload,
    )


def _create_failure(code, detail):
    return PaymentIntentCreateResult(
        intent=None,
        created=False,
        code=code,
        detail=detail,
    )


def _locked_payment_terms(*, solicitud, hold, cliente, now):
    snapshots = tuple(
        SlotHoldService.objects.filter(hold=hold).order_by('orden', 'pk')
    )
    service_ids = sorted({item.servicio_id for item in snapshots})
    services_by_id = {
        service.pk: service
        for service in Servicio.objects.select_for_update()
        .filter(pk__in=service_ids)
        .order_by('pk')
    }
    policies = list(PaymentPolicy.objects.select_for_update().order_by('pk'))
    policy = next(
        (
            item for item in policies
            if item.status == PaymentPolicy.Status.PUBLISHED
        ),
        None,
    )
    if not technical_request_is_current_for_hold(
        solicitud=solicitud,
        hold=hold,
        snapshots=snapshots,
    ):
        raise PaymentIntentConflict(
            'TECHNICAL_REQUEST_INVALIDATED',
            'La solicitud o evaluación técnica ya no está vigente.',
        )
    if (
        solicitud.cliente_id != cliente.pk
        or not cliente.activo
        or not cliente.usuario.is_active
    ):
        raise PaymentIntentConflict(
            'INVALID_CLIENT',
            'El Cliente del HOLD ya no está activo.',
        )
    if (
        not snapshots
        or len(services_by_id) != len(snapshots)
        or any(not service.activo for service in services_by_id.values())
    ):
        raise PaymentIntentConflict(
            'INVALID_HOLD_SERVICES',
            'Los Servicios del HOLD ya no son válidos.',
        )
    if policy is None:
        raise PaymentIntentConflict(
            'NO_PUBLISHED_PAYMENT_POLICY',
            'No existe una política de pago publicada.',
        )
    try:
        policy.full_clean()
    except ValidationError as exc:
        raise PaymentIntentConflict(
            'INVALID_PAYMENT_POLICY',
            'La política de pago publicada no es válida.',
        ) from exc

    line_values = []
    total = Decimal('0')
    for snapshot in snapshots:
        service = services_by_id[snapshot.servicio_id]
        if service.precio_base is None or service.precio_base <= 0:
            raise PaymentIntentConflict(
                'INVALID_SERVICE_PRICE',
                'Un Servicio del HOLD no tiene un precio válido.',
            )
        unit_price = _quantize(service.precio_base, policy.currency)
        discount = _quantize(Decimal('0'), policy.currency)
        subtotal = _quantize(unit_price - discount, policy.currency)
        line_values.append((snapshot, service, unit_price, discount, subtotal))
        total += subtotal
    total = _quantize(total, policy.currency)
    if total <= 0:
        raise PaymentIntentConflict(
            'INVALID_TOTAL_AMOUNT',
            'El total contractual debe ser mayor que cero.',
        )
    expires_at = min(
        now + timedelta(minutes=policy.intent_ttl_minutes),
        hold.expires_at,
    )
    return policy, tuple(line_values), total, expires_at


def _options_for_terms(policy, total):
    options = []
    for mode in (PaymentIntent.Mode.DEPOSIT, PaymentIntent.Mode.FULL):
        if mode not in _allowed_modes(policy):
            continue
        try:
            required = _required_amount(policy=policy, mode=mode, total=total)
        except PaymentIntentConflict as exc:
            if exc.code == 'FIXED_DEPOSIT_EXCEEDS_TOTAL':
                continue
            raise
        options.append(PaymentIntentModeOption(
            mode=mode,
            required_amount=required,
        ))
    if not options:
        raise PaymentIntentConflict(
            'NO_AVAILABLE_PAYMENT_MODE',
            'La política no ofrece una modalidad válida para este total.',
        )
    return tuple(options)


@transaction.atomic
def get_payment_intent_options(*, hold, actor):
    """Cotiza B1 para un HOLD propio sin crear obligaciones ni registrar dinero."""
    if hold is None or getattr(hold, 'pk', None) is None:
        raise PaymentIntentNotFound()
    try:
        target = SlotHold.objects.only('solicitud_id').get(pk=hold.pk)
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=target.solicitud_id
        )
        locked_hold = SlotHold.objects.select_for_update().get(pk=hold.pk)
        locked_intents = list(
            PaymentIntent.objects.select_for_update()
            .filter(slot_hold=locked_hold)
            .order_by('pk')
        )
        cliente = (
            Cliente.objects.select_for_update()
            .select_related('usuario')
            .get(pk=locked_hold.cliente_id)
        )
    except (SlotHold.DoesNotExist, SolicitudTecnicaReserva.DoesNotExist) as exc:
        raise PaymentIntentNotFound() from exc
    if (
        not getattr(actor, 'is_authenticated', False)
        or getattr(actor, 'pk', None) != cliente.usuario_id
    ):
        raise PaymentIntentNotFound()

    existing = next(
        (
            intent for intent in reversed(locked_intents)
            if intent.status == PaymentIntent.Status.APPROVED
            or intent.status in PaymentIntent.ACTIVE_STATUSES
        ),
        None,
    )
    now = database_now()
    if existing is not None:
        if (
            existing.status in PaymentIntent.ACTIVE_STATUSES
            and (
                existing.expires_at <= now
                or locked_hold.state != SlotHold.State.ACTIVE
                or locked_hold.expires_at <= now
            )
        ):
            raise PaymentIntentConflict(
                'INTENT_EXPIRED',
                'El Intent existente ya no está vigente.',
            )
        return PaymentIntentOptionsResult(
            hold=locked_hold,
            existing_intent=existing,
            policy_version=str(existing.policy_snapshot.get('version') or ''),
            total_amount=existing.total_amount_snapshot,
            currency=existing.currency,
            expires_at=existing.expires_at,
            modes=(PaymentIntentModeOption(
                mode=existing.mode,
                required_amount=existing.required_amount,
            ),),
        )

    if locked_hold.state != SlotHold.State.ACTIVE or locked_hold.expires_at <= now:
        raise PaymentIntentConflict(
            'HOLD_EXPIRED',
            'La reserva temporal está vencida.',
        )
    policy, _line_values, total, expires_at = _locked_payment_terms(
        solicitud=solicitud,
        hold=locked_hold,
        cliente=cliente,
        now=now,
    )
    if expires_at <= now:
        raise PaymentIntentConflict(
            'HOLD_EXPIRED',
            'La reserva temporal está vencida.',
        )
    return PaymentIntentOptionsResult(
        hold=locked_hold,
        existing_intent=None,
        policy_version=policy.version,
        total_amount=total,
        currency=policy.currency,
        expires_at=expires_at,
        modes=_options_for_terms(policy, total),
    )


def _same_create_payload(intent, *, hold_id, mode):
    return intent.slot_hold_id == hold_id and intent.mode == mode


@transaction.atomic
def create_payment_intent(*, hold, mode, idempotency_key, actor):
    key = (idempotency_key or '').strip()
    if not key or len(key) > 128:
        raise PaymentIntentError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
            'idempotency_key',
        )
    if mode not in PaymentIntent.Mode.values:
        raise PaymentIntentError(
            'INVALID_PAYMENT_MODE',
            'La modalidad de pago no es válida.',
            'mode',
        )
    if hold is None or getattr(hold, 'pk', None) is None:
        raise PaymentIntentNotFound()
    try:
        target = SlotHold.objects.only('solicitud_id').get(pk=hold.pk)
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=target.solicitud_id
        )
        locked_hold = SlotHold.objects.select_for_update().get(pk=hold.pk)
    except (SlotHold.DoesNotExist, SolicitudTecnicaReserva.DoesNotExist) as exc:
        raise PaymentIntentNotFound() from exc

    locked_intents = list(
        PaymentIntent.objects.select_for_update()
        .filter(slot_hold=locked_hold)
        .order_by('pk')
    )
    cliente = (
        Cliente.objects.select_for_update()
        .select_related('usuario')
        .get(pk=locked_hold.cliente_id)
    )
    if (
        not getattr(actor, 'is_authenticated', False)
        or getattr(actor, 'pk', None) != cliente.usuario_id
    ):
        raise PaymentIntentNotFound()

    same_key = next(
        (
            intent for intent in locked_intents
            if intent.idempotency_key == key
        ),
        None,
    )
    if same_key is None:
        same_key = PaymentIntent.objects.filter(idempotency_key=key).first()
    if same_key is not None:
        if not _same_create_payload(same_key, hold_id=locked_hold.pk, mode=mode):
            raise PaymentIntentConflict(
                'IDEMPOTENCY_KEY_REUSED',
                'La clave ya fue usada con otro payload.',
            )
        return PaymentIntentCreateResult(intent=same_key, created=False)

    if any(
        intent.status in PaymentIntent.ACTIVE_STATUSES
        for intent in locked_intents
    ):
        raise PaymentIntentConflict(
            'ACTIVE_PAYMENT_INTENT_EXISTS',
            'El HOLD ya tiene un Intent no terminal.',
        )

    now = database_now()

    if locked_hold.state == SlotHold.State.ACTIVE and locked_hold.expires_at <= now:
        _expire_locked_hold(locked_hold, now=now, actor=actor)
        return _create_failure(
            'HOLD_EXPIRED',
            'La reserva temporal está vencida.',
        )
    if locked_hold.state != SlotHold.State.ACTIVE:
        code = {
            SlotHold.State.EXPIRED: 'HOLD_EXPIRED',
            SlotHold.State.RELEASED: 'HOLD_RELEASED',
            SlotHold.State.CONSUMED: 'HOLD_ALREADY_CONSUMED',
        }[locked_hold.state]
        raise PaymentIntentConflict(
            code,
            'La reserva temporal no está disponible para crear un Intent.',
        )
    policy, line_values, total, expires_at = _locked_payment_terms(
        solicitud=solicitud,
        hold=locked_hold,
        cliente=cliente,
        now=now,
    )
    _validate_mode(policy, mode)
    required = _required_amount(policy=policy, mode=mode, total=total)
    if expires_at <= now:
        _expire_locked_hold(locked_hold, now=now, actor=actor)
        return _create_failure(
            'HOLD_EXPIRED',
            'La reserva temporal está vencida.',
        )

    try:
        with transaction.atomic():
            intent = PaymentIntent.objects._create_from_service(
                solicitud=solicitud,
                slot_hold=locked_hold,
                cliente=cliente,
                policy=policy,
                policy_snapshot=_policy_snapshot(policy),
                mode=mode,
                total_amount_snapshot=total,
                required_amount=required,
                currency=policy.currency,
                status=PaymentIntent.Status.CREATED,
                expires_at=expires_at,
                created_at=now,
                idempotency_key=key,
                created_by=actor,
            )
            for snapshot, service, unit_price, discount, subtotal in line_values:
                PaymentIntentLine.objects._create_from_service(
                    intent=intent,
                    servicio=service,
                    orden=snapshot.orden,
                    nombre_snapshot=snapshot.nombre_snapshot,
                    cantidad=1,
                    precio_unitario_snapshot=unit_price,
                    descuento=discount,
                    subtotal=subtotal,
                    moneda=policy.currency,
                )
            _audit_intent(
                event=PAYMENT_INTENT_CREATED,
                intent=intent,
                actor=actor,
                previous_status=None,
            )
    except IntegrityError as exc:
        existing = PaymentIntent.objects.filter(idempotency_key=key).first()
        if existing is not None:
            if _same_create_payload(existing, hold_id=locked_hold.pk, mode=mode):
                return PaymentIntentCreateResult(intent=existing, created=False)
            raise PaymentIntentConflict(
                'IDEMPOTENCY_KEY_REUSED',
                'La clave ya fue usada con otro payload.',
            ) from exc
        if PaymentIntent.objects.filter(
            slot_hold=locked_hold,
            status__in=PaymentIntent.ACTIVE_STATUSES,
        ).exists():
            raise PaymentIntentConflict(
                'ACTIVE_PAYMENT_INTENT_EXISTS',
                'El HOLD ya tiene un Intent no terminal.',
            ) from exc
        raise
    return PaymentIntentCreateResult(intent=intent, created=True)


def _lock_intent_graph(*, public_id=None, intent_id=None):
    lookup = {'public_id': public_id} if public_id is not None else {'pk': intent_id}
    try:
        target = PaymentIntent.objects.only(
            'solicitud_id', 'slot_hold_id'
        ).get(**lookup)
        solicitud = SolicitudTecnicaReserva.objects.select_for_update().get(
            pk=target.solicitud_id
        )
        hold = SlotHold.objects.select_for_update().get(pk=target.slot_hold_id)
        intent = PaymentIntent.objects.select_for_update().get(pk=target.pk)
        cliente = (
            Cliente.objects.select_for_update()
            .select_related('usuario')
            .get(pk=intent.cliente_id)
        )
    except (
        PaymentIntent.DoesNotExist,
        SolicitudTecnicaReserva.DoesNotExist,
        SlotHold.DoesNotExist,
        Cliente.DoesNotExist,
    ) as exc:
        raise PaymentIntentNotFound() from exc
    return solicitud, hold, intent, cliente


def _transition_terminal(*, intent, actor, event, reason, now):
    previous = intent.status
    updated = PaymentIntent.objects._transition(
        intent_id=intent.pk,
        from_statuses=PaymentIntent.ACTIVE_STATUSES,
        status=(
            PaymentIntent.Status.CANCELLED
            if event == PAYMENT_INTENT_CANCELLED
            else PaymentIntent.Status.EXPIRED
        ),
        terminal_at=now,
        terminal_reason=reason,
    )
    intent.refresh_from_db()
    if updated == 1:
        _audit_intent(
            event=event,
            intent=intent,
            actor=actor,
            previous_status=previous,
            reason=reason,
        )
    return updated == 1, previous


def _release_hold_for_payment(*, hold, actor, now, reason):
    if hold.state != SlotHold.State.ACTIVE:
        return False
    if hold.expires_at <= now:
        return _expire_locked_hold(hold, now=now, actor=actor).changed
    previous = hold.state
    hold.state = SlotHold.State.RELEASED
    hold.released_at = now
    hold.release_reason = reason
    hold.save(update_fields=['state', 'released_at', 'release_reason'])
    audit_hold(
        hold=hold,
        actor=actor,
        event=SLOT_HOLD_RELEASED,
        previous_state=previous,
        reason=reason,
    )
    return True


def _expire_locked_intent(*, intent, hold, actor, now):
    if intent.status not in PaymentIntent.ACTIVE_STATUSES:
        return PaymentIntentTransitionResult(
            intent=intent,
            hold=hold,
            changed=False,
            previous_status=intent.status,
            current_status=intent.status,
        )

    if hold.state == SlotHold.State.ACTIVE and hold.expires_at <= now:
        _expire_locked_hold(hold, now=now, actor=actor)
        reason = 'HOLD_EXPIRED'
    elif hold.state == SlotHold.State.EXPIRED:
        reason = 'HOLD_EXPIRED'
    elif hold.state == SlotHold.State.RELEASED:
        reason = 'HOLD_RELEASED'
    elif hold.state == SlotHold.State.CONSUMED:
        reason = 'HOLD_CONSUMED'
    elif intent.expires_at <= now:
        reason = 'INTENT_EXPIRED'
        _release_hold_for_payment(
            hold=hold,
            actor=actor,
            now=now,
            reason=SlotHold.ReleaseReason.PAYMENT_INTENT_EXPIRED,
        )
    else:
        raise PaymentIntentConflict(
            'PAYMENT_INTENT_NOT_EXPIRED',
            'El Intent todavía está vigente.',
        )

    changed, previous = _transition_terminal(
        intent=intent,
        actor=actor,
        event=PAYMENT_INTENT_EXPIRED,
        reason=reason,
        now=now,
    )
    return PaymentIntentTransitionResult(
        intent=intent,
        hold=hold,
        changed=changed,
        previous_status=previous,
        current_status=intent.status,
        code=reason,
    )


@transaction.atomic
def expire_payment_intent(*, intent_id, actor=None):
    _, hold, intent, _ = _lock_intent_graph(intent_id=intent_id)
    return _expire_locked_intent(
        intent=intent,
        hold=hold,
        actor=actor,
        now=database_now(),
    )


@transaction.atomic
def cancel_payment_intent(*, public_id, actor):
    _, hold, intent, cliente = _lock_intent_graph(public_id=public_id)
    if (
        not getattr(actor, 'is_authenticated', False)
        or getattr(actor, 'pk', None) != cliente.usuario_id
    ):
        raise PaymentIntentNotFound()
    if intent.status == PaymentIntent.Status.CANCELLED:
        return PaymentIntentTransitionResult(
            intent=intent,
            hold=hold,
            changed=False,
            previous_status=intent.status,
            current_status=intent.status,
        )
    if intent.status not in PaymentIntent.ACTIVE_STATUSES:
        raise PaymentIntentConflict(
            'PAYMENT_INTENT_TERMINAL',
            'El Intent ya se encuentra en un estado terminal.',
        )
    if intent.payments.select_for_update().order_by('pk').exists():
        raise PaymentIntentConflict(
            'PAYMENT_EXISTS',
            'Un Intent con Pagos registrados no puede cancelarse en B2.',
        )

    now = database_now()
    if (
        intent.expires_at <= now
        or hold.state != SlotHold.State.ACTIVE
        or hold.expires_at <= now
    ):
        return _expire_locked_intent(
            intent=intent,
            hold=hold,
            actor=actor,
            now=now,
        )

    _release_hold_for_payment(
        hold=hold,
        actor=actor,
        now=now,
        reason=SlotHold.ReleaseReason.PAYMENT_INTENT_CANCELLED,
    )
    changed, previous = _transition_terminal(
        intent=intent,
        actor=actor,
        event=PAYMENT_INTENT_CANCELLED,
        reason='CLIENT_CANCELLED',
        now=now,
    )
    return PaymentIntentTransitionResult(
        intent=intent,
        hold=hold,
        changed=changed,
        previous_status=previous,
        current_status=intent.status,
        code='CLIENT_CANCELLED',
    )
