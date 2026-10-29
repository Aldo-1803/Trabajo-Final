from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import threading

from django.db import close_old_connections, connection, models
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.manual_payment_services import (
    PAYMENT_MANUAL_REGISTERED,
    PAYMENT_RECONCILED,
    ManualPaymentError,
    reconcile_manual_payment,
    register_manual_payment,
)
from gestion.models import Auditoria, Pago, PaymentIntent, SlotHold
from gestion.payment_intent_services import (
    PAYMENT_INTENT_EXPIRED,
    PaymentIntentError,
    cancel_payment_intent,
    expire_payment_intent,
)
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin
from usuarios.models import Usuario


class ManualPaymentConcurrencyTests(
    ManualPaymentFixtureMixin,
    TransactionTestCase,
):
    """Carreras reales; cada operación usa una conexión PostgreSQL propia."""

    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')

    @staticmethod
    def _run_two(first, second, timeout=20):
        barrier = threading.Barrier(2)

        def wrapped(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(wrapped, first),
                executor.submit(wrapped, second),
            )
            return [future.result(timeout=timeout) for future in futures]

    def _register_worker(
        self,
        *,
        key,
        amount='10.00',
        method=Pago.Method.CASH,
        reference='',
        occurred_at=None,
    ):
        intent_public_id = self.intent.public_id
        actor_id = self.register_actor.pk
        occurred_at = occurred_at or self.occurred_at

        def operation():
            receipt = None
            if method != Pago.Method.CASH:
                receipt = self.receipt(f'{key}.pdf')
            try:
                result = register_manual_payment(
                    intent_public_id=intent_public_id,
                    amount=Decimal(amount),
                    currency='ARS',
                    method=method,
                    purpose=Pago.Purpose.CONFIRMATION,
                    occurred_at=occurred_at,
                    manual_reference=reference,
                    receipt=receipt,
                    idempotency_key=key,
                    actor=Usuario.objects.get(pk=actor_id),
                )
                return (
                    'payment' if result.succeeded else 'rejected',
                    result.created,
                    result.payment.pk if result.payment else None,
                    result.code,
                )
            except ManualPaymentError as exc:
                return ('conflict', False, None, exc.code)

        return operation

    def test_two_cash_payments_cannot_overpay(self):
        results = self._run_two(
            self._register_worker(key='overpay-race-one', amount='600.00'),
            self._register_worker(key='overpay-race-two', amount='600.00'),
        )

        self.assertEqual(sum(item[0] == 'payment' for item in results), 1)
        self.assertEqual(
            sum(item[3] == 'PAYMENT_OVERPAYMENT' for item in results),
            1,
        )
        self.assertEqual(
            Pago.objects.filter(
                payment_intent=self.intent,
                status=Pago.Status.RECONCILED,
            ).aggregate(total=models.Sum('monto'))['total'],
            Decimal('600.00'),
        )

    def test_same_idempotency_key_returns_one_payment(self):
        results = self._run_two(
            self._register_worker(key='same-payment-key'),
            self._register_worker(key='same-payment-key'),
        )

        self.assertEqual(Pago.objects.filter(payment_intent=self.intent).count(), 1)
        self.assertEqual({item[2] for item in results}, {Pago.objects.get().pk})
        self.assertEqual(sum(item[1] for item in results), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_MANUAL_REGISTERED).count(),
            1,
        )

    def test_same_bank_reference_has_one_winner(self):
        results = self._run_two(
            self._register_worker(
                key='reference-race-one',
                method=Pago.Method.BANK_TRANSFER,
                reference='BANK-CONCURRENT-001',
            ),
            self._register_worker(
                key='reference-race-two',
                method=Pago.Method.BANK_TRANSFER,
                reference='BANK-CONCURRENT-001',
            ),
        )

        self.assertEqual(sum(item[0] == 'payment' for item in results), 1)
        self.assertEqual(
            sum(item[3] == 'MANUAL_REFERENCE_REUSED' for item in results),
            1,
        )
        self.assertEqual(Pago.objects.filter(payment_intent=self.intent).count(), 1)

    def test_two_reconciliations_emit_one_transition_and_audit(self):
        payment = self.register_transfer().payment
        payment_public_id = payment.public_id
        actor_id = self.reconcile_actor.pk

        def reconcile():
            result = reconcile_manual_payment(
                payment_public_id=payment_public_id,
                decision='ACCEPT',
                reason='',
                actor=Usuario.objects.get(pk=actor_id),
            )
            return result.current_status, result.changed

        results = self._run_two(reconcile, reconcile)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Pago.Status.RECONCILED)
        self.assertEqual(sum(item[1] for item in results), 1)
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=PAYMENT_RECONCILED,
                registro_id=payment.pk,
            ).count(),
            1,
        )

    def test_cancel_vs_registration_is_serialized(self):
        intent_public_id = self.intent.public_id
        owner_id = self.user.pk

        def cancel():
            try:
                result = cancel_payment_intent(
                    public_id=intent_public_id,
                    actor=Usuario.objects.get(pk=owner_id),
                )
                return ('cancelled', result.current_status)
            except PaymentIntentError as exc:
                return ('conflict', exc.code)

        register = self._register_worker(key='cancel-register-race')
        register_result, cancel_result = self._run_two(register, cancel)
        self.intent.refresh_from_db()

        if Pago.objects.filter(payment_intent=self.intent).exists():
            self.assertEqual(register_result[0], 'payment')
            self.assertEqual(cancel_result, ('conflict', 'PAYMENT_EXISTS'))
            self.assertEqual(self.intent.status, PaymentIntent.Status.PENDING)
        else:
            self.assertEqual(register_result[0], 'rejected')
            self.assertEqual(
                register_result[3],
                'PAYMENT_CONTEXT_EXPIRED',
            )
            self.assertEqual(cancel_result[0], 'cancelled')
            self.assertEqual(self.intent.status, PaymentIntent.Status.CANCELLED)

    def test_expiry_vs_registration_is_serialized_without_deadlock(self):
        now = timezone.now()
        models.QuerySet.update(
            PaymentIntent.objects.filter(pk=self.intent.pk),
            created_at=now - timedelta(minutes=2),
            expires_at=now - timedelta(minutes=1),
        )
        intent_id = self.intent.pk

        def expire():
            try:
                result = expire_payment_intent(intent_id=intent_id)
                return result.current_status, result.changed
            except PaymentIntentError as exc:
                return exc.code, False

        register_result, expire_result = self._run_two(
            self._register_worker(key='expire-register-race'),
            expire,
        )
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()

        self.assertEqual(register_result[0], 'rejected')
        self.assertEqual(register_result[3], 'PAYMENT_CONTEXT_EXPIRED')
        self.assertFalse(Pago.objects.filter(payment_intent=self.intent).exists())
        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(self.hold.state, SlotHold.State.RELEASED)
        self.assertIn(expire_result[0], {
            PaymentIntent.Status.EXPIRED,
            'PAYMENT_INTENT_TERMINAL',
        })
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=PAYMENT_INTENT_EXPIRED,
                registro_id=self.intent.pk,
            ).count(),
            1,
        )
