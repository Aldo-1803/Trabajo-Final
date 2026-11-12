"""Recepción y procesamiento recuperable del inbox Mercado Pago (BH-058 C2a)."""

from dataclasses import dataclass
from datetime import timedelta
import uuid

from decouple import config
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from mercadopago.webhook import (
    InvalidWebhookSignatureError,
    WebhookSignatureValidator,
)

from .models import ProviderEvent, ProviderPaymentAttempt
from .payment_providers import (
    PaymentProviderConfigurationError,
    PaymentProviderRejected,
    PaymentProviderResponseInvalid,
    PaymentProviderTemporaryError,
    get_payment_provider,
)


PROVIDER = ProviderEvent.Provider.MERCADO_PAGO
ALLOWED_TOPICS = {'order'}
KNOWN_ORDER_STATUSES = {
    'created',
    'processing',
    'processed',
    'failed',
    'action_required',
    'refunded',
    'canceled',
    'cancelled',
}


class ProviderEventError(Exception):
    code = 'INVALID_NOTIFICATION'

    def __init__(self, detail='Notificación inválida.'):
        self.detail = detail
        super().__init__(detail)


class ProviderEventAuthenticationError(ProviderEventError):
    code = 'INVALID_SIGNATURE'


class ProviderEventConfigurationError(ProviderEventError):
    code = 'WEBHOOK_NOT_CONFIGURED'


class ProviderEventConflict(ProviderEventError):
    code = 'EVENT_ID_CONFLICT'


@dataclass(frozen=True)
class ReceivedProviderEvent:
    event: ProviderEvent
    created: bool


@dataclass(frozen=True)
class ProviderEventProcessingResult:
    examined: int
    verified: int
    retryable: int
    rejected: int
    mismatched: int


def _setting(name, default=''):
    if hasattr(settings, name):
        return getattr(settings, name)
    return config(name, default=default)


def _identifier(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ProviderEventError(f'{field} no es válido.')
    value = str(value).strip()
    if not value or len(value) > 128:
        raise ProviderEventError(f'{field} no es válido.')
    return value


def _notification_topic(payload, query):
    candidates = [
        value for value in (
            payload.get('type'),
            payload.get('topic'),
            query.get('topic'),
        ) if value not in (None, '')
    ]
    if not candidates or any(not isinstance(value, str) for value in candidates):
        raise ProviderEventError('Falta el tópico de la notificación.')
    normalized = [value.strip().lower() for value in candidates]
    if len(set(normalized)) != 1 or normalized[0] not in ALLOWED_TOPICS:
        raise ProviderEventError('El tópico no está permitido.')
    return 'order'


def _event_created_at(payload):
    value = payload.get('date_created') or payload.get('created_at')
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise ProviderEventError('La fecha del evento no es válida.')
    return parsed


def _notification_snapshot(payload, event_id, resource_id, action):
    snapshot = {
        'id': event_id,
        'type': 'order',
        'action': action,
        'data': {'id': resource_id},
    }
    for key in ('date_created', 'api_version', 'application_id', 'user_id'):
        value = payload.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            snapshot[key] = str(value)[:128]
    if isinstance(payload.get('live_mode'), bool):
        snapshot['live_mode'] = payload['live_mode']
    return snapshot


def receive_mercado_pago_order_event(*, headers, query, payload):
    """Autentica y persiste en una transacción breve, sin llamadas externas."""
    if not isinstance(payload, dict):
        raise ProviderEventError('El cuerpo debe ser un objeto JSON.')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise ProviderEventError('Falta data en la notificación.')

    topic = _notification_topic(payload, query)
    event_id = _identifier(payload.get('id'), 'id de evento')
    body_resource_id = _identifier(data.get('id'), 'data.id')
    query_resource_id = _identifier(query.get('data.id'), 'data.id de query')
    if body_resource_id != query_resource_id:
        raise ProviderEventError('data.id no coincide con la query firmada.')
    action = payload.get('action')
    if not isinstance(action, str) or not action.strip() or len(action) > 100:
        raise ProviderEventError('La acción no es válida.')
    action = action.strip().lower()
    if not action.startswith('order.'):
        raise ProviderEventError('La acción no pertenece a Orders.')

    secret = str(_setting('MERCADO_PAGO_WEBHOOK_SECRET', '')).strip()
    if not secret:
        raise ProviderEventConfigurationError(
            'El receptor de Mercado Pago no está configurado.'
        )
    signature = headers.get('x-signature')
    request_id = headers.get('x-request-id')
    if not signature or not request_id:
        raise ProviderEventAuthenticationError('Faltan encabezados de firma.')
    try:
        WebhookSignatureValidator.validate(
            signature,
            request_id,
            query_resource_id,
            secret,
        )
    except (InvalidWebhookSignatureError, TypeError, ValueError) as exc:
        raise ProviderEventAuthenticationError('Firma inválida.') from exc

    created_at = _event_created_at(payload)
    snapshot = _notification_snapshot(
        payload,
        event_id,
        body_resource_id,
        action,
    )
    attempt = ProviderPaymentAttempt.objects.filter(
        provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
        provider_order_id=body_resource_id,
    ).first()
    with transaction.atomic():
        event, created = ProviderEvent.objects.get_or_create(
            provider=PROVIDER,
            event_id=event_id,
            defaults={
                'topic': topic,
                'action': action,
                'provider_resource_id': body_resource_id,
                'event_created_at': created_at,
                'attempt': attempt,
                'notification_snapshot': snapshot,
            },
        )
        if not created and (
            event.topic != topic
            or event.action != action
            or event.provider_resource_id != body_resource_id
        ):
            raise ProviderEventConflict(
                'El identificador de evento ya existe con otra identidad.'
            )
    return ReceivedProviderEvent(event=event, created=created)


def _claim_next_event(*, stale_after, now):
    stale_before = now - stale_after
    eligible = (
        Q(status=ProviderEvent.Status.RECEIVED)
        | Q(
            status=ProviderEvent.Status.RETRYABLE_ERROR,
            next_retry_at__lte=now,
        )
        | Q(
            status=ProviderEvent.Status.FETCH_PENDING,
            processing_started_at__lte=stale_before,
        )
    )
    with transaction.atomic():
        event = (
            ProviderEvent.objects.select_for_update(skip_locked=True)
            .filter(provider=PROVIDER)
            .filter(eligible)
            .order_by('received_at', 'pk')
            .first()
        )
        if event is None:
            return None
        event.status = ProviderEvent.Status.FETCH_PENDING
        event.processing_attempts += 1
        event.processing_started_at = now
        event.processed_at = None
        event.next_retry_at = None
        event.claim_token = uuid.uuid4()
        event.last_error_code = ''
        event.last_error_detail = ''
        if event.attempt_id is None:
            event.attempt = ProviderPaymentAttempt.objects.filter(
                provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
                provider_order_id=event.provider_resource_id,
            ).first()
        event.save(update_fields=[
            'status',
            'processing_attempts',
            'processing_started_at',
            'processed_at',
            'next_retry_at',
            'claim_token',
            'last_error_code',
            'last_error_detail',
            'attempt',
            'updated_at',
        ])
        return event


def _configured_identity():
    environment = str(_setting('MERCADO_PAGO_ENVIRONMENT', '')).strip().lower()
    if environment == 'test':
        environment = 'sandbox'
    if environment and environment not in {'production', 'sandbox'}:
        raise PaymentProviderConfigurationError(
            'MERCADO_PAGO_ENVIRONMENT debe ser production o sandbox.'
        )
    return {
        'application_id': str(
            _setting('MERCADO_PAGO_APPLICATION_ID', '')
        ).strip(),
        'seller_id': str(_setting('MERCADO_PAGO_SELLER_ID', '')).strip(),
        'environment': environment,
    }


def _snapshot_mismatches(event, attempt, snapshot):
    mismatches = []
    if not snapshot.provider_order_id or (
        snapshot.provider_order_id != event.provider_resource_id
    ):
        mismatches.append('ORDER_ID')
    if attempt is None:
        return ['UNKNOWN_RESOURCE']
    if snapshot.external_reference != attempt.external_reference:
        mismatches.append('EXTERNAL_REFERENCE')
    expected_prefix = f'bh:c1:{attempt.context.lower()}:'
    if not attempt.external_reference.startswith(expected_prefix):
        mismatches.append('CONTEXT')
    if snapshot.total_amount is None or snapshot.total_amount != attempt.amount:
        mismatches.append('AMOUNT')
    if snapshot.currency and snapshot.currency != attempt.currency:
        mismatches.append('CURRENCY')
    if not snapshot.status or snapshot.status not in KNOWN_ORDER_STATUSES:
        mismatches.append('STATUS')
    if snapshot.order_type and snapshot.order_type != 'online':
        mismatches.append('ORDER_TYPE')

    expected = _configured_identity()
    notification = event.notification_snapshot
    notification_application = str(notification.get('application_id') or '')
    notification_seller = str(notification.get('user_id') or '')
    notification_environment = ''
    if isinstance(notification.get('live_mode'), bool):
        notification_environment = (
            'production' if notification['live_mode'] else 'sandbox'
        )
    for field, actual, signed_value in (
        ('APPLICATION_ID', snapshot.application_id, notification_application),
        ('SELLER_ID', snapshot.seller_id, notification_seller),
        ('ENVIRONMENT', snapshot.environment, notification_environment),
    ):
        configured = expected[field.lower()]
        if configured and actual and configured != actual:
            mismatches.append(field)
        if signed_value and actual and signed_value != actual:
            mismatches.append(f'NOTIFICATION_{field}')
    return sorted(set(mismatches))


def _finish_event(
    event,
    *,
    status,
    error_code='',
    error_detail='',
    provider_snapshot=None,
    next_retry_at=None,
):
    now = timezone.now()
    values = {
        'status': status,
        'last_error_code': error_code[:50],
        'last_error_detail': error_detail[:200],
        'provider_snapshot': provider_snapshot or {},
        'processed_at': (
            None if status == ProviderEvent.Status.RETRYABLE_ERROR else now
        ),
        'processing_started_at': None,
        'next_retry_at': next_retry_at,
        'claim_token': None,
        'updated_at': now,
    }
    return ProviderEvent.objects.filter(
        pk=event.pk,
        status=ProviderEvent.Status.FETCH_PENDING,
        claim_token=event.claim_token,
    ).update(**values) == 1


def _process_claimed_event(event, *, retry_delay):
    try:
        adapter = get_payment_provider(event.provider)
        snapshot = adapter.fetch_provider_order(event.provider_resource_id)
        mismatches = _snapshot_mismatches(event, event.attempt, snapshot)
    except (PaymentProviderTemporaryError, PaymentProviderConfigurationError) as exc:
        _finish_event(
            event,
            status=ProviderEvent.Status.RETRYABLE_ERROR,
            error_code=exc.code,
            error_detail='La consulta oficial podrá reintentarse.',
            next_retry_at=timezone.now() + retry_delay,
        )
        return ProviderEvent.Status.RETRYABLE_ERROR
    except (PaymentProviderRejected, PaymentProviderResponseInvalid) as exc:
        _finish_event(
            event,
            status=ProviderEvent.Status.REJECTED,
            error_code=exc.code,
            error_detail='La consulta oficial no es procesable.',
        )
        return ProviderEvent.Status.REJECTED

    sanitized = snapshot.sanitized()
    if mismatches == ['UNKNOWN_RESOURCE']:
        _finish_event(
            event,
            status=ProviderEvent.Status.REJECTED,
            error_code='UNKNOWN_RESOURCE',
            error_detail='La Order no corresponde a un intento C1 conocido.',
            provider_snapshot=sanitized,
        )
        return ProviderEvent.Status.REJECTED
    if mismatches:
        _finish_event(
            event,
            status=ProviderEvent.Status.MISMATCH,
            error_code='ORDER_MISMATCH',
            error_detail=','.join(mismatches),
            provider_snapshot=sanitized,
        )
        return ProviderEvent.Status.MISMATCH
    _finish_event(
        event,
        status=ProviderEvent.Status.VERIFIED,
        provider_snapshot=sanitized,
    )
    return ProviderEvent.Status.VERIFIED


def process_pending_provider_events(
    *,
    limit=100,
    stale_after=timedelta(minutes=10),
    retry_delay=timedelta(minutes=1),
):
    """Procesa eventos sin mantener locks durante la llamada a Mercado Pago."""
    if limit < 1 or limit > 1000:
        raise ValueError('limit debe estar entre 1 y 1000.')
    counters = {
        ProviderEvent.Status.VERIFIED: 0,
        ProviderEvent.Status.RETRYABLE_ERROR: 0,
        ProviderEvent.Status.REJECTED: 0,
        ProviderEvent.Status.MISMATCH: 0,
    }
    examined = 0
    while examined < limit:
        event = _claim_next_event(stale_after=stale_after, now=timezone.now())
        if event is None:
            break
        examined += 1
        outcome = _process_claimed_event(event, retry_delay=retry_delay)
        counters[outcome] += 1
    return ProviderEventProcessingResult(
        examined=examined,
        verified=counters[ProviderEvent.Status.VERIFIED],
        retryable=counters[ProviderEvent.Status.RETRYABLE_ERROR],
        rejected=counters[ProviderEvent.Status.REJECTED],
        mismatched=counters[ProviderEvent.Status.MISMATCH],
    )
