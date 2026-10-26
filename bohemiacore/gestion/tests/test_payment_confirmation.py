from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.test import TestCase
from django.utils import timezone

from gestion.manual_payment_services import (
    financial_snapshot,
    register_manual_payment,
)
from gestion.models import (
    Auditoria,
    Notificacion,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    SlotHold,
    SolicitudTecnicaReserva,
    Turno,
)
from gestion.payment_confirmation_services import (
    BOOKING_CONFIRMED_FROM_PAYMENT,
    PAYMENT_CONFIRMATION_FAILED,
    PAYMENT_INTENT_APPROVED,
    PaymentConfirmationConflict,
    approve_payment_intent_and_confirm_booking,
)
from gestion.payment_intent_services import create_payment_intent
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin


class PaymentConfirmationFixtureMixin(ManualPaymentFixtureMixin):
    def _create_reconciled_fact(self, amount='30.00', key='b3-fact'):
        now = timezone.now()
        payment = Pago.objects._create_booking_from_service(
            payment_intent=self.intent,
            orden=None,
            turno=None,
            monto=Decimal(amount),
            currency='ARS',
            metodo_pago=Pago.Method.CASH,
            purpose=Pago.Purpose.CONFIRMATION,
            status=Pago.Status.RECONCILED,
            fecha_pago=now - timedelta(minutes=1),
            recorded_at=now,
            recorded_by=self.register_actor,
            reconciled_at=now,
            reconciled_by=self.register_actor,
            manual_reference='',
            receipt_sha256='',
            idempotency_key=key,
            terminal_reason='',
            es_sena=True,
        )
        PaymentIntent.objects._transition(
            intent_id=self.intent.pk,
            from_statuses=[PaymentIntent.Status.CREATED],
            status=PaymentIntent.Status.PENDING,
            pending_at=now,
        )
        self.intent.refresh_from_db()
        return payment

    def _register(self, *, amount, key, purpose=Pago.Purpose.CONFIRMATION):
        return register_manual_payment(
            intent_public_id=self.intent.public_id,
            amount=Decimal(amount),
            currency='ARS',
            method=Pago.Method.CASH,
            purpose=purpose,
            occurred_at=timezone.now() - timedelta(minutes=1),
            manual_reference='',
            receipt=None,
            idempotency_key=key,
            actor=self.register_actor,
        )


class PaymentConfirmationFunctionalTests(
    PaymentConfirmationFixtureMixin,
    TestCase,
):
    def test_partial_payment_keeps_pending_active_hold_and_no_turno(self):
        result = self._register(amount='15.00', key='b3-partial')
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()

        self.assertEqual(result.financial.paid_reconciled, Decimal('15.00'))
        self.assertEqual(self.intent.status, PaymentIntent.Status.PENDING)
        self.assertEqual(self.hold.state, SlotHold.State.ACTIVE)
        self.assertFalse(Turno.objects.exists())

    def test_exact_threshold_approves_consumes_and_creates_one_turno(self):
        result = self._register(amount='30.00', key='b3-exact')
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        result.payment.refresh_from_db()

        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(self.hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(self.intent.confirmed_turno_id, Turno.objects.get().pk)
        self.assertEqual(result.payment.turno_id, Turno.objects.get().pk)

    def test_deposit_confirms_with_derived_balance(self):
        self._register(amount='30.00', key='b3-deposit')
        snapshot = financial_snapshot(self.intent)

        self.assertEqual(snapshot.paid_reconciled, Decimal('30.00'))
        self.assertEqual(snapshot.confirmation_due, Decimal('0.00'))
        self.assertEqual(snapshot.balance, Decimal('970.00'))
        self.assertEqual(Turno.objects.count(), 1)

    def test_full_payment_confirms_with_zero_balance(self):
        request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        hold = self.create_hold(
            solicitud=request,
            starts_at=self.starts_at + timedelta(hours=2),
            actor=self.other_user,
            key='b3-full-hold',
        )
        intent = create_payment_intent(
            hold=hold,
            mode=PaymentIntent.Mode.FULL,
            idempotency_key='b3-full-intent',
            actor=self.other_user,
        ).intent
        result = register_manual_payment(
            intent_public_id=intent.public_id,
            amount=Decimal('1000.00'),
            currency='ARS',
            method=Pago.Method.CASH,
            purpose=Pago.Purpose.CONFIRMATION,
            occurred_at=timezone.now() - timedelta(minutes=1),
            manual_reference='',
            receipt=None,
            idempotency_key='b3-full-payment',
            actor=self.register_actor,
        )
        intent.refresh_from_db()

        self.assertEqual(intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(result.financial.balance, Decimal('0.00'))
        self.assertEqual(result.payment.turno_id, intent.confirmed_turno_id)

    def test_retry_returns_same_turno_without_duplicate_effects(self):
        self._register(amount='30.00', key='b3-retry-payment')
        first_turno = Turno.objects.get()
        retry = approve_payment_intent_and_confirm_booking(
            intent_id=self.intent.pk,
            actor=self.register_actor,
        )

        self.assertFalse(retry.changed)
        self.assertEqual(retry.turno.pk, first_turno.pk)
        self.assertEqual(Turno.objects.count(), 1)
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

    def test_later_balance_payment_links_turno_without_reconfirmation(self):
        self._register(amount='30.00', key='b3-confirm-payment')
        turno = Turno.objects.get()
        balance = self._register(
            amount='20.00',
            key='b3-balance-payment',
            purpose=Pago.Purpose.BALANCE,
        ).payment

        self.assertEqual(balance.turno_id, turno.pk)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_INTENT_APPROVED).count(),
            1,
        )

    def test_expired_hold_preserves_payment_and_creates_late_case(self):
        payment = self._create_reconciled_fact(key='b3-late-fact')
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

        result = approve_payment_intent_and_confirm_booking(
            intent_id=self.intent.pk,
            actor=self.register_actor,
        )
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()

        self.assertEqual(result.code, 'HOLD_EXPIRED')
        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(self.hold.state, SlotHold.State.EXPIRED)
        self.assertTrue(Pago.objects.filter(pk=payment.pk).exists())
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(
            result.reconciliation_case.case_type,
            PaymentReconciliationCase.Type.LATE_PAYMENT,
        )

    def test_invalid_request_preserves_payment_and_releases_hold(self):
        self.solicitud.estado = SolicitudTecnicaReserva.Estado.VENCIDA
        self.solicitud.save(update_fields=['estado'])
        payment = self._register(
            amount='30.00',
            key='b3-invalid-request-fact',
        ).payment
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        result = PaymentReconciliationCase.objects.get()

        self.assertEqual(result.reason_code, 'TECHNICAL_REQUEST_INVALIDATED')
        self.assertEqual(self.intent.status, PaymentIntent.Status.REJECTED)
        self.assertEqual(self.hold.state, SlotHold.State.RELEASED)
        self.assertTrue(Pago.objects.filter(pk=payment.pk).exists())
        self.assertEqual(
            result.case_type,
            PaymentReconciliationCase.Type.BOOKING_CONFIRMATION_FAILED,
        )

    def test_invalid_resource_preserves_cash_payment_and_records_failure(self):
        self.personal.activo = False
        self.personal.save(update_fields=['activo'])
        payment = self._register(amount='30.00', key='b3-resource-payment').payment
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()

        self.assertEqual(self.intent.status, PaymentIntent.Status.REJECTED)
        self.assertEqual(self.hold.state, SlotHold.State.RELEASED)
        self.assertTrue(Pago.objects.filter(pk=payment.pk).exists())
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(PaymentReconciliationCase.objects.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_CONFIRMATION_FAILED).count(),
            1,
        )

    def test_notification_and_financial_audits_are_exactly_once(self):
        self._register(amount='30.00', key='b3-once-payment')
        approve_payment_intent_and_confirm_booking(
            intent_id=self.intent.pk,
            actor=self.register_actor,
        )

        self.assertEqual(
            Notificacion.objects.filter(
                origen_entidad='SlotHold',
                origen_id=self.hold.pk,
                titulo='Turno confirmado',
            ).count(),
            1,
        )
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

    def test_approved_without_turno_is_an_exceptional_state(self):
        PaymentIntent.objects._transition(
            intent_id=self.intent.pk,
            from_statuses=[PaymentIntent.Status.CREATED],
            status=PaymentIntent.Status.APPROVED,
            approved_at=timezone.now(),
            confirmation_operation_key=f'payment-confirm:{self.intent.public_id}',
        )
        with self.assertRaises(PaymentConfirmationConflict) as conflict:
            approve_payment_intent_and_confirm_booking(
                intent_id=self.intent.pk,
                actor=self.register_actor,
            )
        self.assertEqual(
            conflict.exception.code,
            'APPROVED_INTENT_WITHOUT_CONFIRMED_BOOKING',
        )
        self.assertFalse(Turno.objects.exists())
