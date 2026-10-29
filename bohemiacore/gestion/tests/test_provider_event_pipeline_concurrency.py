from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gestion.models import Pago, ProviderEvent, ProviderPaymentAttempt
from gestion.order_inventory_services import create_order_stock_commitments
from gestion.provider_event_pipeline import process_verified_provider_events
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from gestion.tests.test_provider_reconciliation import (
    provider_snapshot,
    verified_event,
)


class ProviderEventPipelineConcurrencyTests(
    OrderInventoryFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.receive(self.product, 3, 'f2-pipeline-race')
        self.order = self.make_order(
            [(self.product, 1)],
            state='ESPERANDO_PAGO',
            code='F2-RACE',
        )
        create_order_stock_commitments(self.order.pk)
        self.attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.ORDER,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            order=self.order,
            amount=Decimal('100.00'),
            currency='ARS',
            external_reference='bh:c1:order:f2-race',
            client_idempotency_key='f2-race-client',
            provider_idempotency_key='f2-race-provider',
            request_fingerprint='r' * 64,
            provider_order_id='ORD-F2-RACE',
            provider_status='processed',
            created_by=self.user,
        )

    @staticmethod
    def threaded(callable_):
        close_old_connections()
        try:
            return callable_()
        finally:
            close_old_connections()

    def test_two_workers_claim_verified_event_once(self):
        event = verified_event(
            self.attempt,
            event_id='f2-worker-race',
            snapshot=provider_snapshot(
                self.attempt,
                payment_id='PAY-F2-RACE',
            ),
        )
        gate = threading.Barrier(2)

        def process():
            gate.wait(timeout=10)
            return process_verified_provider_events(limit=1)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=30)
                for future in (
                    executor.submit(self.threaded, process),
                    executor.submit(self.threaded, process),
                )
            ]

        event.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(sum(result.examined for result in results), 1)
        self.assertEqual(sum(result.applied for result in results), 1)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(self.order.estado, 'PAGADO')
        self.assertEqual(event.reconciliation_attempts, 1)
        self.assertIsNone(event.claim_token)
