from datetime import timedelta
from decimal import Decimal
import hashlib
import hmac
import time
from unittest.mock import Mock, patch

from django.db import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    CompromisoStock,
    MovimientoStock,
    OrdenCompra,
    Pago,
    PaymentIntent,
    ProviderEvent,
    ProviderPaymentAttempt,
    SlotHold,
    Turno,
)
from gestion.order_inventory_services import create_order_stock_commitments
from gestion.payment_providers import (
    PaymentProviderTemporaryError,
    ProviderOrderSnapshot,
)
from gestion.provider_event_services import process_pending_provider_events
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin


WEBHOOK_SETTINGS = {
    'MERCADO_PAGO_WEBHOOK_SECRET': 'test-webhook-secret',
    'MERCADO_PAGO_ACCESS_TOKEN': 'TEST-access-token',
    'MERCADO_PAGO_ENVIRONMENT': 'sandbox',
    'MERCADO_PAGO_APPLICATION_ID': 'app-123',
    'MERCADO_PAGO_SELLER_ID': 'seller-456',
}


def signature(resource_id, request_id, secret='test-webhook-secret'):
    timestamp = str(int(time.time() * 1000))
    manifest = (
        f'id:{resource_id.lower()};request-id:{request_id};ts:{timestamp};'
    )
    digest = hmac.new(
        secret.encode(),
        manifest.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f'ts={timestamp},v1={digest}'


@override_settings(**WEBHOOK_SETTINGS)
class ProviderEventTests(OrderInventoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.receive(self.product, 3, 'provider-event')
        self.order = self.make_order([(self.product, 1)])
        create_order_stock_commitments(self.order.pk)
        self.attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.ORDER,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            order=self.order,
            amount=Decimal('100.00'),
            currency='ARS',
            external_reference='bh:c1:order:provider-event-ref',
            client_idempotency_key='provider-event-client-key',
            provider_idempotency_key='provider-event-provider-key',
            request_fingerprint='a' * 64,
            provider_order_id='mp-order-1',
            provider_status='created',
            created_by=self.user,
        )
        self.url = reverse('webhook_mp') + '?data.id=mp-order-1'

    def payload(self, *, event_id='event-1', resource_id='mp-order-1'):
        return {
            'id': event_id,
            'type': 'order',
            'action': 'order.updated',
            'date_created': timezone.now().isoformat(),
            'live_mode': False,
            'application_id': 'app-123',
            'user_id': 'seller-456',
            'data': {'id': resource_id},
        }

    def post(self, payload=None, *, signed=True, request_id='request-1', url=None):
        headers = {}
        if signed:
            resource_id = (payload or self.payload())['data']['id']
            headers = {
                'HTTP_X_REQUEST_ID': request_id,
                'HTTP_X_SIGNATURE': signature(resource_id, request_id),
            }
        return self.api.post(
            url or self.url,
            payload if payload is not None else self.payload(),
            format='json',
            **headers,
        )

    def snapshot(self, **changes):
        values = {
            'provider_order_id': 'mp-order-1',
            'status': 'processed',
            'status_detail': 'accredited',
            'external_reference': self.attempt.external_reference,
            'total_amount': Decimal('100.00'),
            'total_paid_amount': Decimal('100.00'),
            'currency': 'ARS',
            'application_id': 'app-123',
            'seller_id': 'seller-456',
            'environment': 'sandbox',
            'order_type': 'online',
            'country_code': 'AR',
            'transaction_statuses': ('processed',),
        }
        values.update(changes)
        return ProviderOrderSnapshot(**values)

    def test_valid_event_is_durable_deduplicated_and_same_order_accepts_new_event(self):
        with patch('gestion.provider_event_services.get_payment_provider') as factory:
            first = self.post()
            duplicate = self.post()
            second = self.post(self.payload(event_id='event-2'))

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_200_OK)
        self.assertTrue(duplicate.data['duplicate'])
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ProviderEvent.objects.count(), 2)
        self.assertEqual(
            ProviderEvent.objects.filter(provider_resource_id='mp-order-1').count(),
            2,
        )
        self.assertEqual(ProviderEvent.objects.get(event_id='event-1').attempt, self.attempt)
        factory.assert_not_called()

    def test_signature_and_structure_fail_closed(self):
        invalid_signature = self.api.post(
            self.url,
            self.payload(),
            format='json',
            HTTP_X_REQUEST_ID='request-1',
            HTTP_X_SIGNATURE='ts=1,v1=invalid',
        )
        missing_signature = self.post(signed=False)
        wrong_topic = self.post({**self.payload(), 'type': 'payment'})
        wrong_action = self.post({**self.payload(), 'action': 'payment.updated'})
        inconsistent_id = self.post(
            self.payload(resource_id='other-order'),
            url=self.url,
        )
        malformed = self.post(
            {'id': 'event-x', 'type': 'order'},
            signed=False,
        )

        self.assertEqual(invalid_signature.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(missing_signature.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(wrong_topic.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(wrong_action.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(inconsistent_id.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(malformed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProviderEvent.objects.exists())

    @override_settings(MERCADO_PAGO_WEBHOOK_SECRET='')
    def test_missing_secret_fails_closed(self):
        response = self.post()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(ProviderEvent.objects.exists())

    def test_database_failure_is_not_acknowledged(self):
        with patch.object(
            ProviderEvent.objects,
            'get_or_create',
            side_effect=OperationalError('database unavailable'),
        ):
            response = self.post()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch('gestion.provider_event_services.get_payment_provider')
    def test_official_order_is_verified_without_financial_or_commercial_effects(self, factory):
        self.post()
        adapter = Mock()
        adapter.fetch_provider_order.return_value = self.snapshot()
        factory.return_value = adapter
        self.product.refresh_from_db()
        self.order.refresh_from_db()
        before = {
            'pagos': Pago.objects.count(),
            'intents': PaymentIntent.objects.count(),
            'holds': SlotHold.objects.count(),
            'turnos': Turno.objects.count(),
            'movements': MovimientoStock.objects.count(),
            'commitment': CompromisoStock.objects.get(orden=self.order).estado,
            'order': self.order.estado,
            'real': self.product.stock_real,
            'committed': self.product.stock_comprometido,
        }

        result = process_pending_provider_events(limit=1)

        event = ProviderEvent.objects.get()
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual(result.verified, 1)
        self.assertEqual(event.status, ProviderEvent.Status.VERIFIED)
        self.assertEqual(event.provider_snapshot['id'], 'mp-order-1')
        self.assertEqual(Pago.objects.count(), before['pagos'])
        self.assertEqual(PaymentIntent.objects.count(), before['intents'])
        self.assertEqual(SlotHold.objects.count(), before['holds'])
        self.assertEqual(Turno.objects.count(), before['turnos'])
        self.assertEqual(MovimientoStock.objects.count(), before['movements'])
        self.assertEqual(self.order.estado, before['order'])
        self.assertEqual(self.product.stock_real, before['real'])
        self.assertEqual(self.product.stock_comprometido, before['committed'])
        self.assertEqual(
            CompromisoStock.objects.get(orden=self.order).estado,
            before['commitment'],
        )
        self.assertEqual(self.attempt.status, ProviderPaymentAttempt.Status.READY)

    @patch('gestion.provider_event_services.get_payment_provider')
    def test_amount_currency_application_and_seller_mismatches_are_retained(self, factory):
        scenarios = (
            {'total_amount': Decimal('99.00')},
            {'currency': 'USD'},
            {'application_id': 'other-app'},
            {'seller_id': 'other-seller'},
            {'environment': 'production'},
        )
        for index, changes in enumerate(scenarios):
            self.post(self.payload(event_id=f'mismatch-{index}'))
            adapter = Mock()
            adapter.fetch_provider_order.return_value = self.snapshot(**changes)
            factory.return_value = adapter
            result = process_pending_provider_events(limit=1)
            self.assertEqual(result.mismatched, 1)
        self.assertEqual(
            ProviderEvent.objects.filter(status=ProviderEvent.Status.MISMATCH).count(),
            len(scenarios),
        )

    @patch('gestion.provider_event_services.get_payment_provider')
    def test_unknown_resource_is_rejected_but_retained(self, factory):
        payload = self.payload(event_id='unknown-event', resource_id='unknown-order')
        url = reverse('webhook_mp') + '?data.id=unknown-order'
        response = self.post(payload, url=url)
        adapter = Mock()
        adapter.fetch_provider_order.return_value = self.snapshot(
            provider_order_id='unknown-order'
        )
        factory.return_value = adapter

        result = process_pending_provider_events(limit=1)

        event = ProviderEvent.objects.get(event_id='unknown-event')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(result.rejected, 1)
        self.assertEqual(event.status, ProviderEvent.Status.REJECTED)
        self.assertEqual(event.last_error_code, 'UNKNOWN_RESOURCE')

    def test_same_event_id_with_other_resource_is_a_conflict(self):
        self.post()
        payload = self.payload(event_id='event-1', resource_id='other-order')
        response = self.post(
            payload,
            request_id='request-conflict',
            url=reverse('webhook_mp') + '?data.id=other-order',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(ProviderEvent.objects.count(), 1)

    @patch('gestion.provider_event_services.get_payment_provider')
    def test_temporary_failure_retries_and_recovers(self, factory):
        self.post()
        adapter = Mock()
        adapter.fetch_provider_order.side_effect = [
            PaymentProviderTemporaryError(),
            self.snapshot(),
        ]
        factory.return_value = adapter
        first = process_pending_provider_events(limit=1)
        event = ProviderEvent.objects.get()
        self.assertEqual(first.retryable, 1)
        self.assertEqual(event.status, ProviderEvent.Status.RETRYABLE_ERROR)
        self.assertIsNotNone(event.next_retry_at)

        ProviderEvent.objects.filter(pk=event.pk).update(
            next_retry_at=timezone.now() - timedelta(seconds=1)
        )
        second = process_pending_provider_events(limit=1)
        event.refresh_from_db()
        self.assertEqual(second.verified, 1)
        self.assertEqual(event.status, ProviderEvent.Status.VERIFIED)
        self.assertEqual(event.processing_attempts, 2)

    @patch('gestion.provider_event_services.get_payment_provider')
    def test_stale_interrupted_claim_is_recovered(self, factory):
        self.post()
        ProviderEvent.objects.update(
            status=ProviderEvent.Status.FETCH_PENDING,
            claim_token=None,
            processing_started_at=timezone.now() - timedelta(minutes=20),
        )
        adapter = Mock()
        adapter.fetch_provider_order.return_value = self.snapshot()
        factory.return_value = adapter

        result = process_pending_provider_events(
            limit=1,
            stale_after=timedelta(minutes=10),
        )

        self.assertEqual(result.verified, 1)
        self.assertEqual(
            ProviderEvent.objects.get().status,
            ProviderEvent.Status.VERIFIED,
        )
