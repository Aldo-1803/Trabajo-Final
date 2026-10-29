from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import models
from django.test import TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from gestion.models import (
    Auditoria,
    CompromisoStock,
    MovimientoStock,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    SlotHold,
    Turno,
)
from gestion.order_inventory_services import (
    apply_order_inventory_effect,
    create_order_stock_commitments,
    release_order_stock_commitments,
)
from gestion.provider_reconciliation_services import (
    EXTERNAL_PAYMENT_RECONCILED,
    PROVIDER_EVENT_RECONCILED,
    ProviderReconciliationConflict,
    reconcile_verified_provider_event,
)
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin


def provider_snapshot(
    attempt,
    *,
    payment_id='PAY-1',
    paid_amount=None,
    payment_status='processed',
    status_detail='accredited',
    order_status='processed',
    updated_at=None,
    refunds=None,
    chargebacks=None,
):
    paid_amount = str(paid_amount or attempt.amount)
    updated_at = updated_at or timezone.now()
    return {
        'id': attempt.provider_order_id,
        'status': order_status,
        'status_detail': status_detail,
        'external_reference': attempt.external_reference,
        'total_amount': str(attempt.amount),
        'total_paid_amount': paid_amount,
        'currency': attempt.currency,
        'application_id': 'app-123',
        'seller_id': 'seller-456',
        'environment': 'sandbox',
        'type': 'online',
        'country_code': 'AR',
        'created_date': (updated_at - timedelta(minutes=1)).isoformat(),
        'last_updated_date': updated_at.isoformat(),
        'transaction_statuses': [payment_status],
        'payments': [{
            'id': payment_id,
            'amount': str(attempt.amount),
            'paid_amount': paid_amount,
            'confirmed_amount': paid_amount,
            'status': payment_status,
            'status_detail': status_detail,
            'created_date': (updated_at - timedelta(seconds=30)).isoformat(),
            'last_updated_date': updated_at.isoformat(),
        }],
        'refunds': refunds or [],
        'chargebacks': chargebacks or [],
    }


def verified_event(attempt, *, event_id='event-1', snapshot=None):
    now = timezone.now()
    return ProviderEvent.objects.create(
        provider=ProviderEvent.Provider.MERCADO_PAGO,
        topic='order',
        action='order.processed',
        event_id=event_id,
        provider_resource_id=attempt.provider_order_id,
        event_created_at=now - timedelta(seconds=20),
        status=ProviderEvent.Status.VERIFIED,
        attempt=attempt,
        notification_snapshot={
            'id': event_id,
            'type': 'order',
            'action': 'order.processed',
            'data': {'id': attempt.provider_order_id},
        },
        provider_snapshot=snapshot or provider_snapshot(attempt),
        processed_at=now,
    )


class BookingProviderReconciliationTests(ManualPaymentFixtureMixin, TestCase):
    def attempt(
        self,
        *,
        amount='30.00',
        suffix='1',
        channel=ProviderPaymentAttempt.Channel.ONLINE,
    ):
        return ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=channel,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=self.intent,
            amount=Decimal(amount),
            currency='ARS',
            external_reference=f'bh:c1:booking:external-{suffix}',
            client_idempotency_key=f'booking-client-{suffix}',
            provider_idempotency_key=f'booking-provider-{suffix}',
            request_fingerprint=str(suffix)[0] * 64,
            provider_order_id=f'ORD-BOOKING-{suffix}',
            provider_status='processed',
            created_by=self.user,
        )

    def reconcile(self, *, amount='30.00', payment_id='PAY-1', suffix='1', **kwargs):
        attempt = self.attempt(amount=amount, suffix=suffix, **kwargs)
        event = verified_event(
            attempt,
            event_id=f'event-{suffix}',
            snapshot=provider_snapshot(
                attempt,
                payment_id=payment_id,
                paid_amount=amount,
            ),
        )
        return attempt, event, reconcile_verified_provider_event(event.pk)

    def test_valid_deposit_reconciles_and_confirms_exactly_one_booking(self):
        attempt, event, result = self.reconcile()
        payment = result.payments[0]
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        event.refresh_from_db()
        attempt.refresh_from_db()

        self.assertEqual(payment.status, Pago.Status.RECONCILED)
        self.assertEqual(payment.provider_payment_id, 'PAY-1')
        self.assertIsNone(payment.recorded_by)
        self.assertEqual(
            payment.provider_occurred_at,
            parse_datetime(event.provider_snapshot['payments'][0][
                'last_updated_date'
            ]),
        )
        self.assertIsNotNone(event.processed_at)
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(self.hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(result.effect, 'BOOKING_CONFIRMED')
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.APPLIED,
        )
        self.assertEqual(
            attempt.reconciliation_status,
            ProviderPaymentAttempt.ReconciliationStatus.APPLIED,
        )

    def test_insufficient_deposit_stays_pending(self):
        _, _, result = self.reconcile(amount='10.00')
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()

        self.assertEqual(result.payments[0].status, Pago.Status.RECONCILED)
        self.assertEqual(self.intent.status, PaymentIntent.Status.PENDING)
        self.assertEqual(self.hold.state, SlotHold.State.ACTIVE)
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(result.effect, 'BOOKING_THRESHOLD_PENDING')

    def test_full_payment_confirms_and_has_zero_unpaid_total(self):
        _, _, result = self.reconcile(amount='1000.00')
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(result.payments[0].monto, Decimal('1000.00'))
        self.assertEqual(Turno.objects.count(), 1)

    def test_late_payment_is_preserved_with_case_without_booking(self):
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

        attempt, event, result = self.reconcile()
        payment = result.payments[0]
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        attempt.refresh_from_db()

        self.assertEqual(payment.status, Pago.Status.PENDING_RECONCILIATION)
        self.assertEqual(payment.terminal_reason, 'LATE_PAYMENT')
        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(self.hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(
            result.reconciliation_case.case_type,
            PaymentReconciliationCase.Type.LATE_PAYMENT,
        )
        self.assertEqual(result.reconciliation_case.provider_event_id, event.pk)
        self.assertEqual(
            attempt.reconciliation_status,
            ProviderPaymentAttempt.ReconciliationStatus.LATE,
        )

    def test_released_hold_is_not_recreated(self):
        now = timezone.now()
        models.QuerySet.update(
            SlotHold.objects.filter(pk=self.hold.pk),
            state=SlotHold.State.RELEASED,
            released_at=now,
            release_reason='TEST_RELEASE',
        )
        _, _, result = self.reconcile()
        self.hold.refresh_from_db()
        self.assertEqual(self.hold.state, SlotHold.State.RELEASED)
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(result.decision, 'REVIEW_REQUIRED')

    def test_in_person_attempt_uses_same_financial_reconciliation(self):
        _, _, result = self.reconcile(
            channel=ProviderPaymentAttempt.Channel.IN_PERSON
        )
        self.assertEqual(result.payments[0].status, Pago.Status.RECONCILED)
        self.assertEqual(Turno.objects.count(), 1)

    def test_balance_after_confirmation_does_not_resurrect_hold_deadline(self):
        first_attempt, _, _ = self.reconcile(
            amount='30.00',
            payment_id='PAY-DEPOSIT',
            suffix='deposit',
        )
        models.QuerySet.update(
            ProviderPaymentAttempt.objects.filter(pk=first_attempt.pk),
            status=ProviderPaymentAttempt.Status.EXPIRED,
        )
        past = timezone.now() - timedelta(minutes=1)
        models.QuerySet.update(
            SlotHold.objects.filter(pk=self.hold.pk),
            created_at=past - timedelta(minutes=10),
            expires_at=past,
        )
        second_attempt = self.attempt(amount='20.00', suffix='balance')
        event = verified_event(
            second_attempt,
            event_id='event-balance',
            snapshot=provider_snapshot(
                second_attempt,
                payment_id='PAY-BALANCE',
                paid_amount='20.00',
            ),
        )

        result = reconcile_verified_provider_event(event.pk)
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        balance = Pago.objects.get(provider_payment_id='PAY-BALANCE')
        self.assertEqual(balance.purpose, Pago.Purpose.BALANCE)
        self.assertEqual(balance.status, Pago.Status.RECONCILED)
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(self.hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(result.effect, 'BOOKING_CONFIRMED')
        self.assertEqual(Turno.objects.count(), 1)

    def test_same_event_retry_is_idempotent(self):
        _, event, first = self.reconcile()
        retry = reconcile_verified_provider_event(event.pk)
        self.assertTrue(first.changed)
        self.assertFalse(retry.changed)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=EXTERNAL_PAYMENT_RECONCILED).count(),
            1,
        )
        self.assertEqual(
            Auditoria.objects.filter(tabla=PROVIDER_EVENT_RECONCILED).count(),
            1,
        )

    def test_same_external_payment_in_two_events_does_not_duplicate(self):
        attempt, first_event, _ = self.reconcile()
        second_event = verified_event(
            attempt,
            event_id='event-second',
            snapshot=provider_snapshot(attempt, payment_id='PAY-1'),
        )
        second = reconcile_verified_provider_event(second_event.pk)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(second.payments[0].pk, first_event.financial_payments.get().pk)
        self.assertEqual(Turno.objects.count(), 1)

    def test_same_external_identity_on_another_attempt_opens_review(self):
        first_attempt, _, _ = self.reconcile(
            amount='30.00',
            payment_id='PAY-COLLISION',
            suffix='collision-a',
        )
        models.QuerySet.update(
            ProviderPaymentAttempt.objects.filter(pk=first_attempt.pk),
            status=ProviderPaymentAttempt.Status.EXPIRED,
        )
        second_attempt = self.attempt(amount='20.00', suffix='collision-b')
        second_event = verified_event(
            second_attempt,
            event_id='event-collision-b',
            snapshot=provider_snapshot(
                second_attempt,
                payment_id='PAY-COLLISION',
                paid_amount='20.00',
            ),
        )

        result = reconcile_verified_provider_event(second_event.pk)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(result.decision, 'REVIEW_REQUIRED')
        self.assertEqual(
            result.reconciliation_case.reason_code,
            'PROVIDER_PAYMENT_IDENTITY_CONFLICT',
        )
        self.assertEqual(Turno.objects.count(), 1)

    def test_amount_mismatch_requires_review_without_booking_effect(self):
        attempt = self.attempt(amount='30.00')
        event = verified_event(
            attempt,
            snapshot=provider_snapshot(attempt, paid_amount='29.00'),
        )
        result = reconcile_verified_provider_event(event.pk)
        self.intent.refresh_from_db()
        self.assertEqual(result.decision, 'REVIEW_REQUIRED')
        self.assertEqual(
            result.payments[0].status,
            Pago.Status.PENDING_RECONCILIATION,
        )
        self.assertNotEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertFalse(Turno.objects.exists())

    def test_currency_or_context_mismatch_cannot_bypass_c2a(self):
        attempt = self.attempt()
        event = verified_event(attempt)
        event.provider_snapshot = {
            **event.provider_snapshot,
            'currency': 'USD',
        }
        event.save(update_fields=['provider_snapshot', 'updated_at'])
        with self.assertRaises(ProviderReconciliationConflict) as conflict:
            reconcile_verified_provider_event(event.pk)
        self.assertEqual(conflict.exception.code, 'VERIFIED_SNAPSHOT_MISMATCH')
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(Turno.objects.exists())

        event.status = ProviderEvent.Status.MISMATCH
        event.save(update_fields=['status', 'updated_at'])
        with self.assertRaises(ProviderReconciliationConflict) as not_verified:
            reconcile_verified_provider_event(event.pk)
        self.assertEqual(
            not_verified.exception.code,
            'PROVIDER_EVENT_NOT_VERIFIED',
        )

    def assert_non_financial_status(
        self,
        *,
        suffix,
        payment_status,
        status_detail,
        order_status,
    ):
        attempt = self.attempt(suffix=suffix)
        snapshot = provider_snapshot(
            attempt,
            payment_id=f'PAY-{suffix}',
            payment_status=payment_status,
            status_detail=status_detail,
            order_status=order_status,
        )
        event = verified_event(
            attempt,
            event_id=f'event-non-financial-{suffix}',
            snapshot=snapshot,
        )
        result = reconcile_verified_provider_event(event.pk)
        self.assertEqual(result.decision, 'NO_FINANCIAL_EFFECT')
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(Turno.objects.exists())

    def test_pending_event_has_no_financial_effect(self):
        self.assert_non_financial_status(
            suffix='pending',
            payment_status='created',
            status_detail='pending',
            order_status='processing',
        )

    def test_rejected_event_has_no_financial_effect(self):
        self.assert_non_financial_status(
            suffix='rejected',
            payment_status='failed',
            status_detail='rejected',
            order_status='failed',
        )

    def test_older_snapshot_is_ignored(self):
        attempt = self.attempt()
        newer = timezone.now()
        first = verified_event(
            attempt,
            event_id='event-newer',
            snapshot=provider_snapshot(attempt, updated_at=newer),
        )
        reconcile_verified_provider_event(first.pk)
        older = verified_event(
            attempt,
            event_id='event-older',
            snapshot=provider_snapshot(
                attempt,
                updated_at=newer - timedelta(minutes=5),
            ),
        )
        result = reconcile_verified_provider_event(older.pk)
        older.refresh_from_db()
        self.assertEqual(result.effect, 'STALE_SNAPSHOT_IGNORED')
        self.assertEqual(
            older.reconciliation_status,
            ProviderEvent.ReconciliationStatus.IGNORED,
        )
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Turno.objects.count(), 1)

    def test_refund_after_confirmation_opens_case_without_reversal(self):
        attempt, _, _ = self.reconcile()
        refund = [{
            'id': 'REF-1',
            'transaction_id': 'PAY-1',
            'amount': '10.00',
            'status': 'processed',
        }]
        event = verified_event(
            attempt,
            event_id='event-refund',
            snapshot=provider_snapshot(
                attempt,
                payment_id='PAY-1',
                order_status='refunded',
                refunds=refund,
                updated_at=timezone.now() + timedelta(seconds=1),
            ),
        )
        result = reconcile_verified_provider_event(event.pk)
        self.intent.refresh_from_db()
        self.assertEqual(result.decision, 'REVIEW_REQUIRED')
        self.assertEqual(
            result.reconciliation_case.case_type,
            PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
        )
        self.assertEqual(Pago.objects.get().status, Pago.Status.RECONCILED)
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(Turno.objects.count(), 1)

    def test_failure_rolls_back_and_retry_recovers(self):
        attempt = self.attempt()
        event = verified_event(attempt)
        with patch(
            'gestion.provider_reconciliation_services.'
            'approve_payment_intent_and_confirm_booking',
            side_effect=RuntimeError('interrupted'),
        ):
            with self.assertRaises(RuntimeError):
                reconcile_verified_provider_event(event.pk)
        event.refresh_from_db()
        self.assertEqual(
            event.reconciliation_status,
            ProviderEvent.ReconciliationStatus.NOT_EVALUATED,
        )
        self.assertFalse(Pago.objects.exists())

        result = reconcile_verified_provider_event(event.pk)
        self.assertEqual(result.effect, 'BOOKING_CONFIRMED')
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(Turno.objects.count(), 1)

    def test_manual_review_permission_exists_without_staff_authority(self):
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='reconcile_external_payment',
        )
        self.assertEqual(permission.codename, 'reconcile_external_payment')


class OrderProviderReconciliationTests(OrderInventoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.receive(self.product, 3, 'c2b-order')
        self.order = self.make_order(
            [(self.product, 1)],
            state='ESPERANDO_PAGO',
            code='C2B-ORDER',
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
            external_reference='bh:c1:order:c2b-order',
            client_idempotency_key='c2b-order-client',
            provider_idempotency_key='c2b-order-provider',
            request_fingerprint='c' * 64,
            provider_order_id='ORD-C2B-ORDER',
            provider_status='processed',
            created_by=self.user,
        )

    def event(self, *, event_id='order-event', **snapshot_changes):
        snapshot = provider_snapshot(self.attempt, payment_id='PAY-ORDER')
        snapshot.update(snapshot_changes)
        return verified_event(
            self.attempt,
            event_id=event_id,
            snapshot=snapshot,
        )

    def test_valid_order_payment_marks_paid_without_physical_output(self):
        event = self.event()
        result = reconcile_verified_provider_event(event.pk)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=self.order)

        self.assertEqual(result.effect, 'ORDER_MARKED_PAID')
        self.assertEqual(self.order.estado, 'PAGADO')
        self.assertEqual(result.payments[0].status, Pago.Status.RECONCILED)
        self.assertEqual(commitment.estado, CompromisoStock.State.ACTIVE)
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(self.product.stock_comprometido, 1)
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).exists()
        )

        fulfillment = apply_order_inventory_effect(
            self.order.pk,
            actor=self.stock_actor,
        )
        self.assertTrue(fulfillment.applied)
        self.order.refresh_from_db()
        self.assertEqual(self.order.estado, 'COMPLETADO')

    def test_unfulfillable_order_preserves_payment_and_opens_case(self):
        release_order_stock_commitments(
            self.order.pk,
            actor=self.user,
            final_state='CANCELADO',
        )
        event = self.event(event_id='order-not-fulfillable')
        result = reconcile_verified_provider_event(event.pk)
        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(result.decision, 'REVIEW_REQUIRED')
        self.assertEqual(
            result.payments[0].status,
            Pago.Status.PENDING_RECONCILIATION,
        )
        self.assertEqual(
            result.reconciliation_case.case_type,
            PaymentReconciliationCase.Type.ORDER_FULFILLMENT_FAILED,
        )
        self.assertEqual(self.order.estado, 'CANCELADO')
        self.assertEqual(self.product.stock_real, 3)
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).exists()
        )
