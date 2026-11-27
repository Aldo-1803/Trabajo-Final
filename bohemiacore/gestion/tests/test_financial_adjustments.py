from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from gestion.financial_adjustment_services import project_payment_finances
from gestion.models import (
    FinancialAdjustment,
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
    Pago,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    Turno,
)
from gestion.payment_providers import PaymentProviderOutcomeUnknown
from gestion.provider_reconciliation_services import (
    reconcile_verified_provider_event,
)
from gestion.refund_execution_services import execute_authorized_refund
from gestion.tests.test_provider_reconciliation import (
    provider_snapshot,
    verified_event,
)
from gestion.tests.test_refund_execution import RefundExecutionFixtureMixin
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin


class ConfirmedAdjustmentReconciliationTests(
    ManualPaymentFixtureMixin,
    TestCase,
):
    def attempt(self):
        return ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=self.intent,
            amount=Decimal('30.00'),
            currency='ARS',
            external_reference='bh:c1:booking:f74-adjustments',
            client_idempotency_key='f74-adjustment-client',
            provider_idempotency_key='f74-adjustment-provider',
            request_fingerprint='4' * 64,
            provider_order_id='ORD-F74-ADJUSTMENTS',
            provider_status='processed',
            created_by=self.user,
        )

    def reconcile(self):
        attempt = self.attempt()
        event = verified_event(
            attempt,
            event_id='f74-origin-payment',
            snapshot=provider_snapshot(attempt, payment_id='PAY-1'),
        )
        return attempt, event, reconcile_verified_provider_event(event.pk)

    def adjustment_event(
        self,
        attempt,
        *,
        suffix,
        refunds=None,
        chargebacks=None,
        seconds=1,
    ):
        snapshot = provider_snapshot(
            attempt,
            payment_id='PAY-1',
            refunds=refunds,
            chargebacks=chargebacks,
            order_status='refunded' if refunds else 'processed',
            updated_at=timezone.now() + timedelta(seconds=seconds),
        )
        return verified_event(
            attempt,
            event_id=f'adjustment-{suffix}',
            snapshot=snapshot,
        )

    @staticmethod
    def refund(identifier, amount, *, status='processed'):
        return {
            'id': identifier,
            'transaction_id': 'PAY-1',
            'amount': str(amount),
            'status': status,
        }

    def test_partial_and_multiple_refunds_reduce_net_only_when_confirmed(self):
        attempt, _, result = self.reconcile()
        payment = result.payments[0]
        turno_ids = list(Turno.objects.values_list('pk', flat=True))

        first = self.adjustment_event(
            attempt,
            suffix='partial-1',
            refunds=[self.refund('REF-PARTIAL-1', '10.00')],
        )
        first_result = reconcile_verified_provider_event(first.pk)
        projection = project_payment_finances(payment)

        self.assertEqual(
            first_result.effect,
            'CONFIRMED_ADJUSTMENT_RECORDED_NO_BUSINESS_EFFECT',
        )
        self.assertEqual(projection.gross_reconciled, Decimal('30.00'))
        self.assertEqual(projection.confirmed_adjustments, Decimal('10.00'))
        self.assertEqual(projection.net_reconciled, Decimal('20.00'))

        second = self.adjustment_event(
            attempt,
            suffix='partial-2',
            refunds=[
                self.refund('REF-PARTIAL-1', '10.00'),
                self.refund('REF-PARTIAL-2', '5.00'),
            ],
            seconds=2,
        )
        reconcile_verified_provider_event(second.pk)
        projection = project_payment_finances(payment)

        self.assertEqual(FinancialAdjustment.objects.count(), 2)
        self.assertEqual(projection.refunds_confirmed, Decimal('15.00'))
        self.assertEqual(projection.net_reconciled, Decimal('15.00'))
        self.assertEqual(list(Turno.objects.values_list('pk', flat=True)), turno_ids)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, self.intent.Status.APPROVED)

    def test_submitted_or_provisional_rows_do_not_reduce_net(self):
        attempt, _, result = self.reconcile()
        payment = result.payments[0]
        event = self.adjustment_event(
            attempt,
            suffix='provisional',
            refunds=[self.refund('REF-SUBMITTED', '10.00', status='submitted')],
            chargebacks=[{
                'id': 'CBK-OPENED',
                'transaction_id': 'PAY-1',
                'amount': '30.00',
                'status': 'opened',
            }],
        )

        reconcile_verified_provider_event(event.pk)
        projection = project_payment_finances(payment)

        self.assertFalse(FinancialAdjustment.objects.exists())
        self.assertEqual(projection.net_reconciled, Decimal('30.00'))

    def test_terminal_chargeback_is_separate_from_refund(self):
        attempt, _, result = self.reconcile()
        payment = result.payments[0]
        event = self.adjustment_event(
            attempt,
            suffix='chargeback',
            chargebacks=[{
                'id': 'CBK-PROCESSED',
                'transaction_id': 'PAY-1',
                'amount': '30.00',
                'status': 'processed',
            }],
        )

        reconcile_verified_provider_event(event.pk)
        adjustment = FinancialAdjustment.objects.get()
        projection = project_payment_finances(payment)

        self.assertEqual(
            adjustment.adjustment_type,
            FinancialAdjustment.Type.CHARGEBACK,
        )
        self.assertEqual(projection.refunds_confirmed, Decimal('0.00'))
        self.assertEqual(projection.chargebacks_confirmed, Decimal('30.00'))
        self.assertEqual(projection.net_reconciled, Decimal('0.00'))

    def test_duplicate_identity_mismatch_and_overadjustment_stay_in_review(self):
        attempt, _, _ = self.reconcile()
        first = self.adjustment_event(
            attempt,
            suffix='identity-base',
            refunds=[self.refund('REF-IDENTITY', '10.00')],
        )
        reconcile_verified_provider_event(first.pk)

        mismatch = self.adjustment_event(
            attempt,
            suffix='identity-mismatch',
            refunds=[self.refund('REF-IDENTITY', '11.00')],
            seconds=2,
        )
        mismatch_result = reconcile_verified_provider_event(mismatch.pk)
        excessive = self.adjustment_event(
            attempt,
            suffix='excessive',
            refunds=[self.refund('REF-EXCESSIVE', '25.00')],
            seconds=3,
        )
        excessive_result = reconcile_verified_provider_event(excessive.pk)

        self.assertEqual(FinancialAdjustment.objects.count(), 1)
        self.assertEqual(
            mismatch_result.reconciliation_case.reason_code,
            'ADJUSTMENT_IDENTITY_MISMATCH',
        )
        self.assertEqual(
            excessive_result.reconciliation_case.reason_code,
            'ADJUSTMENT_EXCEEDS_PAYMENT',
        )

    def test_reversed_status_does_not_double_subtract_ledger(self):
        attempt, _, result = self.reconcile()
        payment = result.payments[0]
        event = self.adjustment_event(
            attempt,
            suffix='reversed-compatible',
            refunds=[self.refund('REF-TOTAL', '30.00')],
        )
        reconcile_verified_provider_event(event.pk)
        Pago.objects._transition(
            payment_id=payment.pk,
            from_statuses=[Pago.Status.RECONCILED],
            status=Pago.Status.REVERSED,
            reconciled_by=self.user,
            terminal_reason='LEGACY_REVERSED_COMPATIBILITY',
        )
        payment.refresh_from_db()

        projection = project_payment_finances(payment)

        self.assertEqual(projection.gross_reconciled, Decimal('30.00'))
        self.assertEqual(projection.confirmed_adjustments, Decimal('30.00'))
        self.assertEqual(projection.net_reconciled, Decimal('0.00'))

    def test_adjustment_rejects_generic_update_and_delete(self):
        attempt, _, _ = self.reconcile()
        event = self.adjustment_event(
            attempt,
            suffix='immutable',
            refunds=[self.refund('REF-IMMUTABLE', '10.00')],
        )
        reconcile_verified_provider_event(event.pk)
        adjustment = FinancialAdjustment.objects.get()

        adjustment.amount = Decimal('1.00')
        with self.assertRaises(ValidationError):
            adjustment.save()
        with self.assertRaises(ValidationError):
            adjustment.delete()
        with self.assertRaises(ValidationError):
            FinancialAdjustment.objects.filter(pk=adjustment.pk).update(
                amount=Decimal('1.00')
            )


class RefundOperationConfirmationTests(RefundExecutionFixtureMixin, TestCase):
    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_unknown_operation_is_confirmed_only_by_verified_terminal_event(
        self,
        factory,
    ):
        adapter = Mock()
        adapter.submit_refund.side_effect = PaymentProviderOutcomeUnknown(
            'timeout posterior al envío'
        )
        factory.return_value = adapter
        execution = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-4-timeout-confirmed',
        )
        self.assertEqual(
            execution.operation.status,
            FinancialRefundOperation.Status.UNKNOWN,
        )
        pending_projection = project_payment_finances(self.provider_payment)
        self.assertEqual(pending_projection.refund_pending, Decimal('10.00'))
        self.assertEqual(pending_projection.confirmed_adjustments, Decimal('0.00'))
        self.assertEqual(pending_projection.net_reconciled, Decimal('10.00'))

        attempt = self.provider_payment.provider_attempt
        now = timezone.now() + timedelta(seconds=1)
        snapshot = {
            'id': attempt.provider_order_id,
            'status': 'refunded',
            'status_detail': 'refunded',
            'external_reference': attempt.external_reference,
            'total_amount': str(attempt.amount),
            'total_paid_amount': str(attempt.amount),
            'currency': attempt.currency,
            'last_updated_date': now.isoformat(),
            'payments': [{
                'id': self.provider_payment.provider_payment_id,
                'paid_amount': str(attempt.amount),
                'confirmed_amount': str(attempt.amount),
                'status': 'processed',
                'status_detail': 'accredited',
                'last_updated_date': now.isoformat(),
            }],
            'refunds': [{
                'id': 'REF-F74-CONFIRMED',
                'transaction_id': self.provider_payment.provider_payment_id,
                'amount': str(execution.operation.amount),
                'status': 'processed',
                'last_updated_date': now.isoformat(),
            }],
            'chargebacks': [],
        }
        event = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.refunded',
            event_id='EV-F74-CONFIRMED',
            provider_resource_id=attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=attempt,
            notification_snapshot={'id': 'EV-F74-CONFIRMED'},
            provider_snapshot=snapshot,
        )

        reconcile_verified_provider_event(event.pk)
        idempotent_retry = reconcile_verified_provider_event(event.pk)
        execution.operation.refresh_from_db()
        adjustment = FinancialAdjustment.objects.get()

        self.assertFalse(idempotent_retry.changed)
        self.assertEqual(
            execution.operation.status,
            FinancialRefundOperation.Status.CONFIRMED,
        )
        self.assertEqual(adjustment.refund_operation_id, execution.operation.pk)
        self.assertEqual(FinancialAdjustment.objects.count(), 1)
        self.assertEqual(
            FinancialRefundOperationEvent.objects.filter(
                operation=execution.operation,
                event_type=FinancialRefundOperationEvent.Type.CONFIRMED,
            ).count(),
            1,
        )
        self.assertEqual(adapter.submit_refund.call_count, 1)
        self.assertEqual(
            project_payment_finances(self.provider_payment).refund_pending,
            Decimal('0.00'),
        )
        self.refund_case.refresh_from_db()
        self.assertEqual(
            self.refund_case.status,
            PaymentReconciliationCase.Status.OPEN,
        )
