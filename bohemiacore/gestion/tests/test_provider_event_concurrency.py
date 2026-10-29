from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import threading
from unittest.mock import Mock, patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from gestion.models import ProviderEvent, ProviderPaymentAttempt
from gestion.order_inventory_services import create_order_stock_commitments
from gestion.payment_providers import ProviderOrderSnapshot
from gestion.provider_event_services import process_pending_provider_events
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from gestion.tests.test_provider_events import WEBHOOK_SETTINGS, signature


@override_settings(**WEBHOOK_SETTINGS)
class ProviderEventConcurrencyTests(
    OrderInventoryFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.receive(self.product, 3, 'provider-event-race')
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
            external_reference='bh:c1:order:provider-race-ref',
            client_idempotency_key='provider-race-client',
            provider_idempotency_key='provider-race-key',
            request_fingerprint='b' * 64,
            provider_order_id='mp-race-order',
            provider_status='created',
            created_by=self.user,
        )

    @staticmethod
    def payload(event_id):
        return {
            'id': event_id,
            'type': 'order',
            'action': 'order.updated',
            'live_mode': False,
            'application_id': 'app-123',
            'user_id': 'seller-456',
            'data': {'id': 'mp-race-order'},
        }

    def post_event(self, event_id):
        request_id = f'request-{event_id}'
        return APIClient().post(
            reverse('webhook_mp') + '?data.id=mp-race-order',
            self.payload(event_id),
            format='json',
            HTTP_X_REQUEST_ID=request_id,
            HTTP_X_SIGNATURE=signature('mp-race-order', request_id),
        ).status_code

    def snapshot(self):
        return ProviderOrderSnapshot(
            provider_order_id='mp-race-order',
            status='processed',
            status_detail='accredited',
            external_reference=self.attempt.external_reference,
            total_amount=Decimal('100.00'),
            total_paid_amount=Decimal('100.00'),
            currency='ARS',
            application_id='app-123',
            seller_id='seller-456',
            environment='sandbox',
            order_type='online',
            country_code='AR',
            transaction_statuses=('processed',),
        )

    @staticmethod
    def threaded(callable_):
        close_old_connections()
        try:
            return callable_()
        finally:
            close_old_connections()

    def test_simultaneous_duplicate_webhooks_create_one_event(self):
        gate = threading.Barrier(2)

        def receive():
            gate.wait(timeout=10)
            return self.post_event('same-event')

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result(timeout=20)
                for future in (
                    executor.submit(self.threaded, receive),
                    executor.submit(self.threaded, receive),
                )
            ]
        self.assertEqual(sorted(statuses), [200, 201])
        self.assertEqual(ProviderEvent.objects.count(), 1)

    def test_distinct_events_for_same_order_are_both_durable(self):
        gate = threading.Barrier(2)

        def receive(event_id):
            gate.wait(timeout=10)
            return self.post_event(event_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result(timeout=20)
                for future in (
                    executor.submit(self.threaded, lambda: receive('event-a')),
                    executor.submit(self.threaded, lambda: receive('event-b')),
                )
            ]
        self.assertEqual(statuses, [201, 201])
        self.assertEqual(ProviderEvent.objects.count(), 2)

    def test_two_workers_do_not_fetch_the_same_event(self):
        self.post_event('worker-race')
        entered = threading.Event()
        release = threading.Event()
        adapter = Mock()

        def fetch(_resource_id):
            entered.set()
            self.assertTrue(release.wait(timeout=10))
            return self.snapshot()

        adapter.fetch_provider_order.side_effect = fetch
        with patch(
            'gestion.provider_event_services.get_payment_provider',
            return_value=adapter,
        ):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.threaded,
                    lambda: process_pending_provider_events(limit=1),
                )
                self.assertTrue(entered.wait(timeout=10))
                second = process_pending_provider_events(limit=1)
                release.set()
                first = future.result(timeout=20)

        self.assertEqual(first.verified, 1)
        self.assertEqual(second.examined, 0)
        self.assertEqual(adapter.fetch_provider_order.call_count, 1)

    def test_new_event_can_arrive_and_process_while_other_fetch_is_open(self):
        self.post_event('event-open')
        entered = threading.Event()
        release = threading.Event()
        adapter = Mock()

        def fetch(_resource_id):
            if not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(timeout=10))
            return self.snapshot()

        adapter.fetch_provider_order.side_effect = fetch
        with patch(
            'gestion.provider_event_services.get_payment_provider',
            return_value=adapter,
        ):
            with ThreadPoolExecutor(max_workers=1) as executor:
                first = executor.submit(
                    self.threaded,
                    lambda: process_pending_provider_events(limit=1),
                )
                self.assertTrue(entered.wait(timeout=10))
                self.assertEqual(self.post_event('event-arrived'), 201)
                second = process_pending_provider_events(limit=1)
                release.set()
                first.result(timeout=20)

        self.assertEqual(second.verified, 1)
        self.assertEqual(
            ProviderEvent.objects.filter(
                status=ProviderEvent.Status.VERIFIED
            ).count(),
            2,
        )

    def test_simultaneous_retry_is_claimed_once(self):
        self.post_event('retry-race')
        ProviderEvent.objects.update(
            status=ProviderEvent.Status.RETRYABLE_ERROR,
            next_retry_at=timezone.now() - timedelta(seconds=1),
        )
        adapter = Mock()
        adapter.fetch_provider_order.return_value = self.snapshot()
        gate = threading.Barrier(2)

        def process():
            gate.wait(timeout=10)
            return process_pending_provider_events(limit=1)

        with patch(
            'gestion.provider_event_services.get_payment_provider',
            return_value=adapter,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [
                    future.result(timeout=20)
                    for future in (
                        executor.submit(self.threaded, process),
                        executor.submit(self.threaded, process),
                    )
                ]
        self.assertEqual(sum(result.verified for result in results), 1)
        self.assertEqual(adapter.fetch_provider_order.call_count, 1)
