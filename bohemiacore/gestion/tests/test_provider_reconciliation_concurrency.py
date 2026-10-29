from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import threading

from django.db import close_old_connections, connection, models
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.models import (
    CompromisoStock,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    SlotHold,
    Turno,
)
from gestion.order_inventory_services import create_order_stock_commitments
from gestion.provider_reconciliation_services import (
    reconcile_verified_provider_event,
)
from gestion.slot_hold_services import expire_slot_hold
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from gestion.tests.test_provider_reconciliation import (
    provider_snapshot,
    verified_event,
)


class ThreadedMixin:
    @staticmethod
    def threaded(callable_):
        close_old_connections()
        try:
            return callable_()
        finally:
            close_old_connections()


class BookingProviderReconciliationConcurrencyTests(
    ThreadedMixin,
    ManualPaymentFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')

    def attempt(self, *, amount, suffix, status=ProviderPaymentAttempt.Status.READY):
        return ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=status,
            payment_intent=self.intent,
            amount=Decimal(amount),
            currency='ARS',
            external_reference=f'bh:c1:booking:race-{suffix}',
            client_idempotency_key=f'race-client-{suffix}',
            provider_idempotency_key=f'race-provider-{suffix}',
            request_fingerprint=str(suffix)[0] * 64,
            provider_order_id=f'ORD-RACE-{suffix}',
            provider_status='processed',
            created_by=self.user,
        )

    def event(self, attempt, *, suffix, payment_id, amount):
        return verified_event(
            attempt,
            event_id=f'race-event-{suffix}',
            snapshot=provider_snapshot(
                attempt,
                payment_id=payment_id,
                paid_amount=amount,
            ),
        )

    def test_two_reconcilers_for_same_payment_create_one_fact(self):
        attempt = self.attempt(amount='30.00', suffix='same')
        event = self.event(
            attempt,
            suffix='same',
            payment_id='PAY-RACE-SAME',
            amount='30.00',
        )
        gate = threading.Barrier(2)

        def reconcile():
            gate.wait(timeout=10)
            return reconcile_verified_provider_event(event.pk)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=30)
                for future in (
                    executor.submit(self.threaded, reconcile),
                    executor.submit(self.threaded, reconcile),
                )
            ]
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(sum(result.changed for result in results), 1)

        retry = reconcile_verified_provider_event(event.pk)
        self.assertFalse(retry.changed)
        self.assertEqual(Pago.objects.count(), 1)

    def test_two_payments_reach_threshold_once(self):
        first_attempt = self.attempt(
            amount='10.00',
            suffix='partial-a',
            status=ProviderPaymentAttempt.Status.EXPIRED,
        )
        second_attempt = self.attempt(amount='20.00', suffix='partial-b')
        first = self.event(
            first_attempt,
            suffix='partial-a',
            payment_id='PAY-PARTIAL-A',
            amount='10.00',
        )
        second = self.event(
            second_attempt,
            suffix='partial-b',
            payment_id='PAY-PARTIAL-B',
            amount='20.00',
        )
        gate = threading.Barrier(2)

        def reconcile(event_id):
            gate.wait(timeout=10)
            return reconcile_verified_provider_event(event_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=30)
                for future in (
                    executor.submit(self.threaded, lambda: reconcile(first.pk)),
                    executor.submit(self.threaded, lambda: reconcile(second.pk)),
                )
            ]
        self.intent.refresh_from_db()
        self.assertEqual(Pago.objects.count(), 2)
        self.assertEqual(
            sum(Pago.objects.values_list('monto', flat=True)),
            Decimal('30.00'),
        )
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(
            sum(result.effect == 'BOOKING_CONFIRMED' for result in results),
            1,
        )

    def test_reconciliation_vs_expiration_never_resurrects_hold(self):
        deadline = timezone.now() - timedelta(seconds=1)
        models.QuerySet.update(
            SlotHold.objects.filter(pk=self.hold.pk),
            created_at=deadline - timedelta(minutes=10),
            expires_at=deadline,
        )
        models.QuerySet.update(
            PaymentIntent.objects.filter(pk=self.intent.pk),
            created_at=deadline - timedelta(minutes=10),
            expires_at=deadline,
        )
        attempt = self.attempt(amount='30.00', suffix='expiry')
        event = self.event(
            attempt,
            suffix='expiry',
            payment_id='PAY-EXPIRY-RACE',
            amount='30.00',
        )
        gate = threading.Barrier(2)

        def reconcile():
            gate.wait(timeout=10)
            return reconcile_verified_provider_event(event.pk)

        def expire():
            gate.wait(timeout=10)
            return expire_slot_hold(hold_id=self.hold.pk)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(self.threaded, reconcile),
                executor.submit(self.threaded, expire),
            )
            [future.result(timeout=30) for future in futures]

        self.hold.refresh_from_db()
        self.intent.refresh_from_db()
        payment = Pago.objects.get()
        self.assertIn(
            self.hold.state,
            {SlotHold.State.EXPIRED, SlotHold.State.RELEASED},
        )
        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(payment.status, Pago.Status.PENDING_RECONCILIATION)
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(PaymentReconciliationCase.objects.count(), 1)

    def test_retry_after_committed_reconciliation_is_read_only(self):
        attempt = self.attempt(amount='30.00', suffix='after-commit')
        event = self.event(
            attempt,
            suffix='after-commit',
            payment_id='PAY-AFTER-COMMIT',
            amount='30.00',
        )
        first = reconcile_verified_provider_event(event.pk)
        close_old_connections()
        retry = reconcile_verified_provider_event(event.pk)
        self.assertTrue(first.changed)
        self.assertFalse(retry.changed)
        self.assertEqual(first.payments[0].pk, retry.payments[0].pk)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Turno.objects.count(), 1)


class OrderProviderReconciliationConcurrencyTests(
    ThreadedMixin,
    OrderInventoryFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.receive(self.product, 3, 'c2b-order-race')
        self.order = self.make_order(
            [(self.product, 1)],
            state='ESPERANDO_PAGO',
            code='C2B-RACE',
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
            external_reference='bh:c1:order:c2b-race',
            client_idempotency_key='c2b-race-client',
            provider_idempotency_key='c2b-race-provider',
            request_fingerprint='r' * 64,
            provider_order_id='ORD-C2B-RACE',
            provider_status='processed',
            created_by=self.user,
        )

    def test_two_events_on_order_apply_one_payment_without_stock_output(self):
        provider_updated_at = timezone.now()
        first = verified_event(
            self.attempt,
            event_id='order-race-a',
            snapshot=provider_snapshot(
                self.attempt,
                payment_id='PAY-ORDER-RACE',
                updated_at=provider_updated_at,
            ),
        )
        second = verified_event(
            self.attempt,
            event_id='order-race-b',
            snapshot=provider_snapshot(
                self.attempt,
                payment_id='PAY-ORDER-RACE',
                updated_at=provider_updated_at,
            ),
        )
        gate = threading.Barrier(2)

        def reconcile(event_id):
            gate.wait(timeout=10)
            return reconcile_verified_provider_event(event_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            [
                future.result(timeout=30)
                for future in (
                    executor.submit(self.threaded, lambda: reconcile(first.pk)),
                    executor.submit(self.threaded, lambda: reconcile(second.pk)),
                )
            ]
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=self.order)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(self.order.estado, 'PAGADO')
        self.assertEqual(commitment.estado, CompromisoStock.State.ACTIVE)
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(self.product.stock_comprometido, 1)
        self.assertEqual(
            ProviderEvent.objects.filter(
                reconciliation_status=ProviderEvent.ReconciliationStatus.APPLIED
            ).count(),
            2,
        )
