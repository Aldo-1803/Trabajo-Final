from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import time as time_module

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection, models, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.models import (
    Auditoria,
    PaymentIntent,
    PaymentPolicy,
    SlotHold,
)
from gestion.payment_intent_services import (
    PAYMENT_INTENT_EXPIRED,
    PaymentIntentError,
    cancel_payment_intent,
    create_payment_intent,
    expire_payment_intent,
    publish_payment_policy,
)
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin
from usuarios.models import Usuario


class PaymentIntentConcurrencyTests(SlotHoldFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        admin = Usuario.objects.create_user(
            email='concurrent-payment-admin@test.com',
            password='Concurrent!2026',
        )
        admin.user_permissions.add(
            Permission.objects.get(codename='manage_payment_configuration')
        )
        policy = PaymentPolicy.objects.create(
            version='CONCURRENT-PAYMENT',
            allowed_mode=PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL,
            deposit_kind=PaymentPolicy.DepositKind.PERCENTAGE,
            deposit_value='25.00',
            currency='ARS',
            intent_ttl_minutes=10,
            enabled_manual_methods=['CASH'],
            created_by=admin,
        )
        publish_payment_policy(policy_id=policy.pk, actor=admin)

    @staticmethod
    def _run_two(first, second, timeout=20):
        barrier = threading.Barrier(2)

        def wrapped(callable_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return callable_()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(wrapped, first),
                executor.submit(wrapped, second),
            )
            return [future.result(timeout=timeout) for future in futures]

    @staticmethod
    def _create_worker(*, hold_id, actor_id, key):
        def operation():
            try:
                result = create_payment_intent(
                    hold=SlotHold.objects.get(pk=hold_id),
                    mode=PaymentIntent.Mode.DEPOSIT,
                    idempotency_key=key,
                    actor=Usuario.objects.get(pk=actor_id),
                )
                return (
                    'created' if result.succeeded else 'rejected',
                    result.created,
                    result.code,
                )
            except PaymentIntentError as exc:
                return ('conflict', False, exc.code)
        return operation

    def test_two_intents_same_hold_leave_exactly_one_active(self):
        hold = self.create_hold()
        results = self._run_two(
            self._create_worker(
                hold_id=hold.pk,
                actor_id=self.user.pk,
                key='concurrent-intent-one',
            ),
            self._create_worker(
                hold_id=hold.pk,
                actor_id=self.user.pk,
                key='concurrent-intent-two',
            ),
        )

        self.assertEqual(sum(item[0] == 'created' for item in results), 1)
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(
            PaymentIntent.objects.filter(
                status__in=PaymentIntent.ACTIVE_STATUSES
            ).count(),
            1,
        )
        self.assertEqual(PaymentIntent.objects.get().lines.count(), 1)

    def test_cancel_vs_expire_has_one_terminal_transition(self):
        hold = self.create_hold()
        intent = create_payment_intent(
            hold=hold,
            mode=PaymentIntent.Mode.DEPOSIT,
            idempotency_key='cancel-expire-create',
            actor=self.user,
        ).intent
        now = timezone.now()
        models.QuerySet.update(
            PaymentIntent.objects.filter(pk=intent.pk),
            created_at=now - timedelta(minutes=2),
            expires_at=now - timedelta(minutes=1),
        )

        def cancel():
            try:
                result = cancel_payment_intent(
                    public_id=intent.public_id,
                    actor=Usuario.objects.get(pk=self.user.pk),
                )
                return result.current_status, result.changed
            except PaymentIntentError as exc:
                return exc.code, False

        def expire():
            try:
                result = expire_payment_intent(intent_id=intent.pk)
                return result.current_status, result.changed
            except PaymentIntentError as exc:
                return exc.code, False

        results = self._run_two(cancel, expire)
        intent.refresh_from_db()
        hold.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(hold.state, SlotHold.State.RELEASED)
        self.assertEqual(sum(item[1] for item in results), 1)
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=PAYMENT_INTENT_EXPIRED,
                registro_id=intent.pk,
            ).count(),
            1,
        )

    def test_create_waiting_for_hold_lock_crosses_expiry(self):
        hold = self.create_hold()
        now = timezone.now()
        deadline = now + timedelta(seconds=2)
        SlotHold.objects.filter(pk=hold.pk).update(
            created_at=now - timedelta(minutes=2),
            expires_at=deadline,
        )

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            with transaction.atomic():
                SlotHold.objects.select_for_update().get(pk=hold.pk)

                def create_with_connection():
                    close_old_connections()
                    try:
                        return self._create_worker(
                            hold_id=hold.pk,
                            actor_id=self.user.pk,
                            key='cross-hold-expiry',
                        )()
                    finally:
                        close_old_connections()

                future = executor.submit(create_with_connection)
                time_module.sleep(2.3)
            result = future.result(timeout=10)
        finally:
            executor.shutdown(wait=True)

        hold.refresh_from_db()
        self.assertEqual(result[0], 'rejected')
        self.assertEqual(result[2], 'HOLD_EXPIRED')
        self.assertEqual(hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(PaymentIntent.objects.exists())
