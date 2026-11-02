from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
from unittest.mock import Mock, patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.models import ProviderPaymentAttempt
from gestion.order_inventory_services import create_order_stock_commitments
from gestion.payment_providers import CheckoutCreated
from gestion.provider_checkout_services import start_order_checkout
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from usuarios.models import Usuario


class ProviderCheckoutConcurrencyTests(
    OrderInventoryFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.receive(self.product, 3, 'provider-race')
        self.order = self.make_order([(self.product, 1)])
        create_order_stock_commitments(self.order.pk)

    def test_two_keys_create_one_attempt_and_one_provider_call(self):
        gate = threading.Barrier(2)
        adapter = Mock()
        adapter.create_checkout.return_value = CheckoutCreated(
            provider_order_id='provider-race-order',
            checkout_url='https://www.mercadopago.com.ar/checkout/race',
            provider_status='created',
            expires_at=timezone.now() + timedelta(minutes=20),
        )

        def worker(key):
            close_old_connections()
            try:
                actor = Usuario.objects.get(pk=self.user.pk)
                gate.wait(timeout=10)
                result = start_order_checkout(
                    order_id=self.order.pk,
                    actor=actor,
                    idempotency_key=key,
                    channel=ProviderPaymentAttempt.Channel.ONLINE,
                )
                return result.attempt.public_id
            finally:
                close_old_connections()

        with patch(
            'gestion.provider_checkout_services.get_payment_provider',
            return_value=adapter,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(worker, 'provider-race-a'),
                    executor.submit(worker, 'provider-race-b'),
                ]
                public_ids = [future.result(timeout=20) for future in futures]

        self.assertEqual(public_ids[0], public_ids[1])
        self.assertEqual(ProviderPaymentAttempt.objects.count(), 1)
        self.assertEqual(adapter.create_checkout.call_count, 1)
        self.assertEqual(
            ProviderPaymentAttempt.objects.get().status,
            ProviderPaymentAttempt.Status.READY,
        )
