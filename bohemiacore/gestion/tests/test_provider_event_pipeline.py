from datetime import timedelta
from decimal import Decimal
from io import StringIO
import uuid
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from gestion.models import (
    CompromisoStock,
    MovimientoStock,
    Pago,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    Turno,
)
from gestion.order_inventory_services import (
    apply_order_inventory_effect,
    create_order_stock_commitments,
)
from gestion.payment_providers import (
    PaymentProviderTemporaryError,
    ProviderOrderSnapshot,
)
from gestion.provider_event_pipeline import (
    process_provider_event_pipeline,
    process_verified_provider_events,
)
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin
from gestion.tests.test_provider_events import WEBHOOK_SETTINGS
from gestion.tests.test_provider_reconciliation import (
    provider_snapshot,
    verified_event,
)


@override_settings(**WEBHOOK_SETTINGS)
class ProviderEventPipelineTests(OrderInventoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.receive(self.product, 3, 'f2-pipeline')
        self.order = self.make_order(
            [(self.product, 1)],
            state='ESPERANDO_PAGO',
            code='F2-ORDER',
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
            external_reference='bh:c1:order:f2-pipeline',
            client_idempotency_key='f2-pipeline-client',
            provider_idempotency_key='f2-pipeline-provider',
            request_fingerprint='f' * 64,
            provider_order_id='ORD-F2-PIPELINE',
            provider_status='created',
            created_by=self.user,
        )

    def received_event(self, *, event_id='f2-received'):
        now = timezone.now()
        return ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.updated',
            event_id=event_id,
            provider_resource_id=self.attempt.provider_order_id,
            event_created_at=now - timedelta(seconds=10),
            attempt=self.attempt,
            notification_snapshot={
                'id': event_id,
                'type': 'order',
                'action': 'order.updated',
                'live_mode': False,
                'application_id': 'app-123',
                'user_id': 'seller-456',
                'data': {'id': self.attempt.provider_order_id},
            },
        )

    def official_snapshot(self, *, payment_id='PAY-F2', updated_at=None):
        updated_at = updated_at or timezone.now()
        return ProviderOrderSnapshot(
            provider_order_id=self.attempt.provider_order_id,
            status='processed',
            status_detail='accredited',
            external_reference=self.attempt.external_reference,
            total_amount=self.attempt.amount,
            total_paid_amount=self.attempt.amount,
            currency=self.attempt.currency,
            application_id='app-123',
            seller_id='seller-456',
            environment='sandbox',
            order_type='online',
            country_code='AR',
            transaction_statuses=('processed',),
            created_date=(updated_at - timedelta(minutes=1)).isoformat(),
            last_updated_date=updated_at.isoformat(),
            payments=({
                'id': payment_id,
                'amount': str(self.attempt.amount),
                'paid_amount': str(self.attempt.amount),
                'confirmed_amount': str(self.attempt.amount),
                'status': 'processed',
                'status_detail': 'accredited',
                'created_date': (
                    updated_at - timedelta(seconds=30)
                ).isoformat(),
                'last_updated_date': updated_at.isoformat(),
            },),
        )

    def assert_single_order_payment_without_stock_output(self):
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=self.order)
        self.assertEqual(self.order.estado, 'PAGADO')
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Pago.objects.get().status, Pago.Status.RECONCILED)
        self.assertEqual(commitment.estado, CompromisoStock.State.ACTIVE)
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(self.product.stock_comprometido, 1)
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT,
            ).exists()
        )

    def test_received_event_is_verified_and_reconciled_in_same_cycle(self):
        event = self.received_event()
        adapter = Mock()
        adapter.fetch_provider_order.return_value = self.official_snapshot()

        with patch(
            'gestion.provider_event_services.get_payment_provider',
            return_value=adapter,
        ):
            result = process_provider_event_pipeline()

        event.refresh_from_db()
        self.assertEqual(result.verification.verified, 1)
        self.assertEqual(result.reconciliation.applied, 1)
        self.assertEqual(event.status, ProviderEvent.Status.VERIFIED)
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.APPLIED,
        )
        self.assertEqual(event.reconciliation_attempts, 1)
        self.assertIsNone(event.claim_token)
        self.assert_single_order_payment_without_stock_output()

    def test_two_events_for_same_payment_do_not_duplicate_financial_fact(self):
        snapshot = provider_snapshot(
            self.attempt,
            payment_id='PAY-F2-DUPLICATE',
        )
        first = verified_event(
            self.attempt,
            event_id='f2-duplicate-a',
            snapshot=snapshot,
        )
        second = verified_event(
            self.attempt,
            event_id='f2-duplicate-b',
            snapshot=snapshot,
        )

        result = process_verified_provider_events()

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(result.applied, 2)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(
            first.financial_payments.get().pk,
            second.financial_payments.get().pk,
        )
        self.assert_single_order_payment_without_stock_output()

    def test_interruption_before_c2b_schedules_retry_and_recovers(self):
        event = verified_event(
            self.attempt,
            event_id='f2-before-c2b',
            snapshot=provider_snapshot(self.attempt, payment_id='PAY-F2-BEFORE'),
        )
        with patch(
            'gestion.provider_event_pipeline.reconcile_verified_provider_event',
            side_effect=RuntimeError('worker interrupted before C2b'),
        ):
            first = process_verified_provider_events(
                retry_delay=timedelta(seconds=30),
            )

        event.refresh_from_db()
        self.assertEqual(first.retryable, 1)
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.NOT_EVALUATED,
        )
        self.assertEqual(
            event.last_error_code,
            'RECONCILIATION_UNEXPECTED_ERROR',
        )
        self.assertIsNotNone(event.next_retry_at)
        self.assertFalse(Pago.objects.exists())

        ProviderEvent.objects.filter(pk=event.pk).update(
            next_retry_at=timezone.now() - timedelta(seconds=1),
        )
        retry = process_verified_provider_events()

        self.assertEqual(retry.applied, 1)
        self.assert_single_order_payment_without_stock_output()

    def test_interruption_after_c2b_commit_is_cleaned_without_second_effect(self):
        event = verified_event(
            self.attempt,
            event_id='f2-after-c2b',
            snapshot=provider_snapshot(self.attempt, payment_id='PAY-F2-AFTER'),
        )
        with patch(
            'gestion.provider_event_pipeline._clear_reconciliation_claim',
            side_effect=RuntimeError('worker stopped after C2b commit'),
        ):
            with self.assertRaises(RuntimeError):
                process_verified_provider_events()

        event.refresh_from_db()
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.APPLIED,
        )
        self.assertIsNotNone(event.claim_token)
        self.assert_single_order_payment_without_stock_output()

        restarted = process_verified_provider_events()

        event.refresh_from_db()
        self.assertEqual(restarted.examined, 0)
        self.assertIsNone(event.claim_token)
        self.assertEqual(event.reconciliation_attempts, 1)
        self.assert_single_order_payment_without_stock_output()

    def test_temporary_provider_failure_retries_full_pipeline(self):
        event = self.received_event(event_id='f2-provider-retry')
        adapter = Mock()
        adapter.fetch_provider_order.side_effect = PaymentProviderTemporaryError(
            'provider unavailable'
        )
        with patch(
            'gestion.provider_event_services.get_payment_provider',
            return_value=adapter,
        ):
            first = process_provider_event_pipeline(
                retry_delay=timedelta(seconds=30),
            )

        event.refresh_from_db()
        self.assertEqual(first.verification.retryable, 1)
        self.assertEqual(event.status, ProviderEvent.Status.RETRYABLE_ERROR)
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.NOT_EVALUATED,
        )
        self.assertFalse(Pago.objects.exists())

        ProviderEvent.objects.filter(pk=event.pk).update(
            next_retry_at=timezone.now() - timedelta(seconds=1),
        )
        adapter.fetch_provider_order.side_effect = None
        adapter.fetch_provider_order.return_value = self.official_snapshot(
            payment_id='PAY-F2-PROVIDER-RETRY'
        )
        with patch(
            'gestion.provider_event_services.get_payment_provider',
            return_value=adapter,
        ):
            retry = process_provider_event_pipeline()

        self.assertEqual(retry.verification.verified, 1)
        self.assertEqual(retry.reconciliation.applied, 1)
        self.assert_single_order_payment_without_stock_output()

    def test_nonrecoverable_financial_conflict_becomes_explicit_review(self):
        snapshot = provider_snapshot(
            self.attempt,
            payment_id='PAY-F2-REVIEW',
        )
        snapshot['currency'] = 'USD'
        event = verified_event(
            self.attempt,
            event_id='f2-financial-review',
            snapshot=snapshot,
        )

        result = process_verified_provider_events()

        event.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(result.review_required, 1)
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED,
        )
        self.assertEqual(event.reconciliation_code, 'VERIFIED_SNAPSHOT_MISMATCH')
        case = PaymentReconciliationCase.objects.get(provider_event=event)
        self.assertEqual(case.reason_code, 'VERIFIED_SNAPSHOT_MISMATCH')
        self.assertEqual(self.order.estado, 'ESPERANDO_PAGO')
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT,
            ).exists()
        )

    def test_restart_recovers_stale_reconciliation_claim(self):
        event = verified_event(
            self.attempt,
            event_id='f2-stale-claim',
            snapshot=provider_snapshot(self.attempt, payment_id='PAY-F2-STALE'),
        )
        ProviderEvent.objects.filter(pk=event.pk).update(
            claim_token=uuid.uuid4(),
            processing_started_at=timezone.now() - timedelta(minutes=30),
            next_retry_at=timezone.now() + timedelta(hours=1),
        )

        result = process_verified_provider_events(
            stale_after=timedelta(minutes=10),
        )

        event.refresh_from_db()
        self.assertEqual(result.applied, 1)
        self.assertIsNone(event.claim_token)
        self.assertEqual(event.reconciliation_attempts, 1)
        self.assert_single_order_payment_without_stock_output()
    def test_older_event_is_ignored_without_degrading_applied_attempt(self):
        newer_at = timezone.now()
        newer = verified_event(
            self.attempt,
            event_id='f2-newer',
            snapshot=provider_snapshot(
                self.attempt,
                payment_id='PAY-F2-OLD',
                updated_at=newer_at,
            ),
        )
        first = process_verified_provider_events(limit=1)
        self.assertEqual(first.applied, 1)
        self.attempt.refresh_from_db()
        reconciled_at = self.attempt.last_reconciled_at

        older = verified_event(
            self.attempt,
            event_id='f2-older',
            snapshot=provider_snapshot(
                self.attempt,
                payment_id='PAY-F2-OLD',
                updated_at=newer_at - timedelta(minutes=10),
            ),
        )
        second = process_verified_provider_events()

        newer.refresh_from_db()
        older.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual(second.ignored, 1)
        self.assertEqual(
            older.reconciliation_status,
            ProviderEvent.ReconciliationStatus.IGNORED,
        )
        self.assertEqual(older.reconciliation_code, 'STALE_EVENT')
        self.assertEqual(
            newer.reconciliation_status,
            ProviderEvent.ReconciliationStatus.APPLIED,
        )
        self.assertEqual(
            self.attempt.reconciliation_status,
            ProviderPaymentAttempt.ReconciliationStatus.APPLIED,
        )
        self.assertEqual(self.attempt.last_reconciled_at, reconciled_at)
        self.assert_single_order_payment_without_stock_output()

    def test_pipeline_retry_does_not_duplicate_order_stock_movement(self):
        event = verified_event(
            self.attempt,
            event_id='f2-order-stock',
            snapshot=provider_snapshot(self.attempt, payment_id='PAY-F2-STOCK'),
        )
        process_verified_provider_events()

        first = apply_order_inventory_effect(
            self.order.pk,
            actor=self.stock_actor,
        )
        retry = apply_order_inventory_effect(
            self.order.pk,
            actor=self.stock_actor,
        )
        pipeline_retry = process_verified_provider_events()

        self.assertTrue(first.applied)
        self.assertFalse(retry.applied)
        self.assertEqual(pipeline_retry.examined, 0)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT,
                reference_id=str(self.order.pk),
            ).count(),
            1,
        )
        event.refresh_from_db()
        self.assertEqual(event.reconciliation_attempts, 1)

    def test_management_command_runs_complete_pipeline_once(self):
        event = verified_event(
            self.attempt,
            event_id='f2-command',
            snapshot=provider_snapshot(self.attempt, payment_id='PAY-F2-COMMAND'),
        )
        output = StringIO()

        call_command(
            'process_provider_events',
            limit=10,
            stale_minutes=10,
            retry_seconds=1,
            poll_seconds=1,
            stdout=output,
        )

        event.refresh_from_db()
        self.assertIn('aplicados=1', output.getvalue())
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.APPLIED,
        )
        self.assert_single_order_payment_without_stock_output()


class BookingProviderEventPipelineTests(ManualPaymentFixtureMixin, TestCase):
    def test_duplicate_provider_events_create_one_turno(self):
        attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=self.intent,
            amount=Decimal('30.00'),
            currency='ARS',
            external_reference='bh:c1:booking:f2-turno',
            client_idempotency_key='f2-turno-client',
            provider_idempotency_key='f2-turno-provider',
            request_fingerprint='t' * 64,
            provider_order_id='ORD-F2-TURNO',
            provider_status='processed',
            created_by=self.user,
        )
        snapshot = provider_snapshot(
            attempt,
            payment_id='PAY-F2-TURNO',
            paid_amount='30.00',
        )
        verified_event(
            attempt,
            event_id='f2-turno-a',
            snapshot=snapshot,
        )
        verified_event(
            attempt,
            event_id='f2-turno-b',
            snapshot=snapshot,
        )

        result = process_verified_provider_events()

        self.assertEqual(result.applied, 2)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(
            ProviderEvent.objects.filter(
                reconciliation_status=(
                    ProviderEvent.ReconciliationStatus.APPLIED
                )
            ).count(),
            2,
        )
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT,
            ).exists()
        )
