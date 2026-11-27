from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.models import FinancialAdjustment, ProviderPaymentAttempt
from gestion.provider_reconciliation_services import (
    reconcile_verified_provider_event,
)
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin
from gestion.tests.test_provider_reconciliation import (
    provider_snapshot,
    verified_event,
)


class FinancialAdjustmentConcurrencyTests(
    ManualPaymentFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=self.intent,
            amount=Decimal('30.00'),
            currency='ARS',
            external_reference='bh:c1:booking:f74-race',
            client_idempotency_key='f74-race-client',
            provider_idempotency_key='f74-race-provider',
            request_fingerprint='7' * 64,
            provider_order_id='ORD-F74-RACE',
            provider_status='processed',
            created_by=self.user,
        )
        origin = verified_event(
            self.attempt,
            event_id='f74-race-origin',
            snapshot=provider_snapshot(self.attempt, payment_id='PAY-F74-RACE'),
        )
        reconcile_verified_provider_event(origin.pk)

    @staticmethod
    def threaded(callable_):
        close_old_connections()
        try:
            return callable_()
        finally:
            close_old_connections()

    def adjustment_event(self, *, event_id, refund_id, amount, updated_at):
        return verified_event(
            self.attempt,
            event_id=event_id,
            snapshot=provider_snapshot(
                self.attempt,
                payment_id='PAY-F74-RACE',
                order_status='refunded',
                refunds=[{
                    'id': refund_id,
                    'transaction_id': 'PAY-F74-RACE',
                    'amount': amount,
                    'status': 'processed',
                }],
                updated_at=updated_at,
            ),
        )

    def reconcile_together(self, first, second):
        gate = threading.Barrier(2)

        def reconcile(event_id):
            gate.wait(timeout=10)
            return reconcile_verified_provider_event(event_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(self.threaded, lambda: reconcile(first.pk)),
                executor.submit(self.threaded, lambda: reconcile(second.pk)),
            )
            return [future.result(timeout=30) for future in futures]

    def test_two_workers_materialize_duplicate_external_identity_once(self):
        updated_at = timezone.now()
        first = self.adjustment_event(
            event_id='f74-race-duplicate-a',
            refund_id='REF-F74-RACE-SAME',
            amount='10.00',
            updated_at=updated_at,
        )
        second = self.adjustment_event(
            event_id='f74-race-duplicate-b',
            refund_id='REF-F74-RACE-SAME',
            amount='10.00',
            updated_at=updated_at,
        )

        self.reconcile_together(first, second)

        self.assertEqual(FinancialAdjustment.objects.count(), 1)
        self.assertEqual(
            FinancialAdjustment.objects.get().amount,
            Decimal('10.00'),
        )

    def test_partial_and_total_concurrent_never_overadjust_payment(self):
        updated_at = timezone.now()
        partial = self.adjustment_event(
            event_id='f74-race-partial',
            refund_id='REF-F74-RACE-PARTIAL',
            amount='10.00',
            updated_at=updated_at,
        )
        total = self.adjustment_event(
            event_id='f74-race-total',
            refund_id='REF-F74-RACE-TOTAL',
            amount='30.00',
            updated_at=updated_at,
        )

        self.reconcile_together(partial, total)

        adjusted = sum(
            FinancialAdjustment.objects.values_list('amount', flat=True),
            Decimal('0.00'),
        )
        self.assertLessEqual(adjusted, Decimal('30.00'))
        self.assertEqual(FinancialAdjustment.objects.count(), 1)
