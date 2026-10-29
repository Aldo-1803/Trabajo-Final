from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
import threading
import time as time_module

from django.db import close_old_connections, connection, models, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.manual_payment_services import (
    ManualPaymentError,
    reconcile_manual_payment,
    register_manual_payment,
)
from gestion.models import (
    Auditoria,
    Notificacion,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    Personal,
    SlotHold,
    Turno,
)
from gestion.payment_confirmation_services import (
    BOOKING_CONFIRMED_FROM_PAYMENT,
    PAYMENT_CONFIRMATION_FAILED,
    PAYMENT_INTENT_APPROVED,
    PaymentConfirmationError,
    approve_payment_intent_and_confirm_booking,
)
from gestion.payment_intent_services import (
    PaymentIntentError,
    expire_payment_intent,
)
from gestion.slot_hold_services import SlotHoldError, release_slot_hold
from gestion.tests.test_payment_confirmation import (
    PaymentConfirmationFixtureMixin,
)
from usuarios.models import Usuario


class PaymentConfirmationConcurrencyTests(
    PaymentConfirmationFixtureMixin,
    TransactionTestCase,
):
    """Carreras B3 con una conexión PostgreSQL independiente por worker."""

    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')

    @staticmethod
    def _run_two(first, second, timeout=25):
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

    def _cash_worker(self, key, amount='15.00'):
        intent_public_id = self.intent.public_id
        actor_id = self.register_actor.pk

        def operation():
            try:
                result = register_manual_payment(
                    intent_public_id=intent_public_id,
                    amount=Decimal(amount),
                    currency='ARS',
                    method=Pago.Method.CASH,
                    purpose=Pago.Purpose.CONFIRMATION,
                    occurred_at=timezone.now() - timedelta(minutes=1),
                    manual_reference='',
                    receipt=None,
                    idempotency_key=key,
                    actor=Usuario.objects.get(pk=actor_id),
                )
                return ('payment', result.payment.pk, result.created)
            except ManualPaymentError as exc:
                return ('conflict', exc.code, False)

        return operation

    def _reconcile_worker(self, payment_public_id):
        actor_id = self.reconcile_actor.pk

        def operation():
            try:
                result = reconcile_manual_payment(
                    payment_public_id=payment_public_id,
                    decision='ACCEPT',
                    reason='',
                    actor=Usuario.objects.get(pk=actor_id),
                )
                return (result.current_status, result.changed, result.code)
            except ManualPaymentError as exc:
                return ('conflict', False, exc.code)

        return operation

    def _orchestrator_worker(self):
        intent_id = self.intent.pk
        actor_id = self.register_actor.pk

        def operation():
            try:
                result = approve_payment_intent_and_confirm_booking(
                    intent_id=intent_id,
                    actor=Usuario.objects.get(pk=actor_id),
                )
                return (
                    'turno' if result.succeeded else 'failed',
                    result.changed,
                    result.turno.pk if result.turno else None,
                    result.code,
                )
            except PaymentConfirmationError as exc:
                return ('conflict', False, None, exc.code)

        return operation

    def _assert_single_success(self):
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(self.hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(self.intent.confirmed_turno_id, Turno.objects.get().pk)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_INTENT_APPROVED).count(),
            1,
        )
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=BOOKING_CONFIRMED_FROM_PAYMENT
            ).count(),
            1,
        )
        self.assertEqual(
            Notificacion.objects.filter(
                origen_entidad='SlotHold',
                origen_id=self.hold.pk,
            ).count(),
            1,
        )

    def test_two_simultaneous_cash_payments_complete_threshold_once(self):
        self._run_two(
            self._cash_worker('b3-race-cash-one'),
            self._cash_worker('b3-race-cash-two'),
        )

        self.assertEqual(
            Pago.objects.filter(
                payment_intent=self.intent,
                status=Pago.Status.RECONCILED,
            ).aggregate(total=models.Sum('monto'))['total'],
            Decimal('30.00'),
        )
        self.assertEqual(
            Pago.objects.filter(turno__isnull=False).count(),
            2,
        )
        self._assert_single_success()

    def test_two_reconciliations_complete_threshold_once(self):
        first = self.register_transfer(
            amount=Decimal('15.00'),
            idempotency_key='b3-reconcile-first',
            manual_reference='B3-RECONCILE-ONE',
            receipt=self.receipt('b3-first.pdf'),
        ).payment
        second = self.register_transfer(
            amount=Decimal('15.00'),
            idempotency_key='b3-reconcile-second',
            manual_reference='B3-RECONCILE-TWO',
            receipt=self.receipt('b3-second.pdf'),
            occurred_at=self.occurred_at + timedelta(seconds=1),
        ).payment

        results = self._run_two(
            self._reconcile_worker(first.public_id),
            self._reconcile_worker(second.public_id),
        )

        self.assertEqual(sum(item[1] for item in results), 2)
        self.assertEqual(
            Pago.objects.filter(status=Pago.Status.RECONCILED).count(),
            2,
        )
        self._assert_single_success()

    def test_reconcile_vs_expire_never_approves_expired_hold(self):
        payment = self.register_transfer(
            amount=Decimal('30.00'),
            idempotency_key='b3-expire-payment',
            manual_reference='B3-EXPIRE-RACE',
            receipt=self.receipt('b3-expire.pdf'),
        ).payment
        deadline = timezone.now() - timedelta(milliseconds=50)
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
        intent_id = self.intent.pk

        def expire():
            try:
                result = expire_payment_intent(intent_id=intent_id)
                return (result.current_status, result.changed)
            except PaymentIntentError as exc:
                return (exc.code, False)

        self._run_two(self._reconcile_worker(payment.public_id), expire)
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(self.hold.state, SlotHold.State.EXPIRED)
        self.assertEqual(payment.status, Pago.Status.PENDING_RECONCILIATION)
        self.assertFalse(Turno.objects.exists())

    def test_reconcile_vs_release_has_one_coherent_terminal_result(self):
        payment = self.register_transfer(
            amount=Decimal('30.00'),
            idempotency_key='b3-release-payment',
            manual_reference='B3-RELEASE-RACE',
            receipt=self.receipt('b3-release.pdf'),
        ).payment
        owner_id = self.user.pk

        def release():
            try:
                result = release_slot_hold(
                    public_id=self.hold.public_id,
                    actor=Usuario.objects.get(pk=owner_id),
                )
                return ('released', result.changed)
            except SlotHoldError as exc:
                return ('conflict', exc.code)

        self._run_two(self._reconcile_worker(payment.public_id), release)
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        payment.refresh_from_db()

        if self.hold.state == SlotHold.State.CONSUMED:
            self.assertEqual(payment.status, Pago.Status.RECONCILED)
            self._assert_single_success()
        else:
            self.assertEqual(self.hold.state, SlotHold.State.RELEASED)
            self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
            self.assertEqual(payment.status, Pago.Status.PENDING_RECONCILIATION)
            self.assertFalse(Turno.objects.exists())

    def test_waiting_for_resource_lock_crosses_expiry_without_turno(self):
        self._create_reconciled_fact(key='b3-cross-expiry-fact')
        deadline = timezone.now() + timedelta(seconds=2)
        models.QuerySet.update(
            SlotHold.objects.filter(pk=self.hold.pk),
            expires_at=deadline,
        )
        models.QuerySet.update(
            PaymentIntent.objects.filter(pk=self.intent.pk),
            expires_at=deadline,
        )

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            with transaction.atomic():
                Personal.objects.select_for_update().get(pk=self.personal.pk)

                def run():
                    close_old_connections()
                    try:
                        return self._orchestrator_worker()()
                    finally:
                        close_old_connections()

                future = executor.submit(run)
                time_module.sleep(2.3)
            result = future.result(timeout=15)
        finally:
            executor.shutdown(wait=True)

        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        self.assertEqual(result[0], 'failed')
        self.assertEqual(result[3], 'HOLD_EXPIRED')
        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(self.hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(PaymentReconciliationCase.objects.count(), 1)

    def test_two_orchestrators_return_same_turno(self):
        self._create_reconciled_fact(key='b3-two-orchestrators-fact')
        results = self._run_two(
            self._orchestrator_worker(),
            self._orchestrator_worker(),
        )

        self.assertEqual({item[0] for item in results}, {'turno'})
        self.assertEqual(len({item[2] for item in results}), 1)
        self.assertEqual(sum(item[1] for item in results), 1)
        self._assert_single_success()

    def test_retry_after_commit_returns_existing_turno(self):
        self._create_reconciled_fact(key='b3-after-commit-fact')
        first = self._orchestrator_worker()()
        close_old_connections()
        retry = self._orchestrator_worker()()

        self.assertEqual(first[0], 'turno')
        self.assertTrue(first[1])
        self.assertEqual(retry[0], 'turno')
        self.assertFalse(retry[1])
        self.assertEqual(first[2], retry[2])
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_CONFIRMATION_FAILED).count(),
            0,
        )
        self._assert_single_success()
