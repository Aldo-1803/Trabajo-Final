from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import models
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    Auditoria,
    OrdenCompra,
    Pago,
    Personal,
    PaymentIntent,
    PaymentPolicy,
    SlotHold,
)
from gestion.manual_payment_services import (
    LATE_MANUAL_REVIEW,
    PAYMENT_MANUAL_REGISTERED,
    PAYMENT_RECONCILED,
    PAYMENT_REJECTED,
    ManualPaymentConflict,
    ManualPaymentPermissionDenied,
    financial_snapshot,
    reconcile_manual_payment,
    register_manual_payment,
)
from gestion.payment_intent_services import (
    PaymentIntentConflict,
    cancel_payment_intent,
    create_payment_intent,
    publish_payment_policy,
)
from gestion.private_storage import PrivatePaymentReceiptStorage
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin
from usuarios.models import Usuario
from usuarios.roles import BusinessRole


class ManualPaymentFixtureMixin(SlotHoldFixtureMixin):
    def setUp(self):
        super().setUp()
        self.original_storage = Pago._meta.get_field('comprobante_foto').storage
        Pago._meta.get_field('comprobante_foto').storage = InMemoryStorage()
        self.addCleanup(self._restore_storage)

        self.policy_actor = Usuario.objects.create_user(
            email='b2-policy@test.com',
            password='Payment!2026',
        )
        self.policy_actor.user_permissions.add(
            Permission.objects.get(codename='manage_payment_configuration')
        )
        policy = PaymentPolicy.objects.create(
            version='B2-POLICY',
            allowed_mode=PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL,
            deposit_kind=PaymentPolicy.DepositKind.FIXED,
            deposit_value=Decimal('30.00'),
            fixed_exceeds_total_behavior=(
                PaymentPolicy.FixedExceedsTotalBehavior.REJECT
            ),
            currency='ARS',
            intent_ttl_minutes=10,
            enabled_manual_methods=[
                Pago.Method.CASH,
                Pago.Method.BANK_TRANSFER,
                Pago.Method.EXTERNAL_CARD,
                Pago.Method.OTHER,
            ],
            created_by=self.policy_actor,
        )
        publish_payment_policy(policy_id=policy.pk, actor=self.policy_actor)
        self.hold = self.create_hold()
        self.intent = create_payment_intent(
            hold=self.hold,
            mode=PaymentIntent.Mode.DEPOSIT,
            idempotency_key='b2-intent',
            actor=self.user,
        ).intent
        self.register_actor = Usuario.objects.create_user(
            email='register-payment@test.com',
            password='Payment!2026',
        )
        self.register_actor.user_permissions.add(
            Permission.objects.get(codename='register_payment')
        )
        self.reconcile_actor = Usuario.objects.create_user(
            email='reconcile-payment@test.com',
            password='Payment!2026',
        )
        self.reconcile_actor.user_permissions.add(
            Permission.objects.get(codename='confirm_deposit')
        )
        self.occurred_at = timezone.now() - timedelta(minutes=1)

    def _restore_storage(self):
        Pago._meta.get_field('comprobante_foto').storage = self.original_storage

    @staticmethod
    def receipt(name='receipt.pdf'):
        return SimpleUploadedFile(
            name,
            b'%PDF-1.7\nfinancial evidence',
            content_type='application/pdf',
        )

    def register(self, **overrides):
        values = {
            'intent_public_id': self.intent.public_id,
            'amount': Decimal('10.00'),
            'currency': 'ARS',
            'method': Pago.Method.CASH,
            'purpose': Pago.Purpose.CONFIRMATION,
            'occurred_at': self.occurred_at,
            'manual_reference': '',
            'receipt': None,
            'idempotency_key': 'b2-payment-key',
            'actor': self.register_actor,
            'late_evidence': False,
        }
        values.update(overrides)
        return register_manual_payment(**values)

    def register_transfer(self, **overrides):
        values = {
            'method': Pago.Method.BANK_TRANSFER,
            'manual_reference': ' bank-ref-001 ',
            'receipt': self.receipt(),
        }
        values.update(overrides)
        return self.register(**values)


class ManualPaymentFunctionalTests(ManualPaymentFixtureMixin, TestCase):
    def test_cash_at_threshold_is_reconciled_and_confirms_booking(self):
        result = self.register(amount=Decimal('30.00'))
        payment = result.payment
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()

        self.assertTrue(result.created)
        self.assertEqual(payment.status, Pago.Status.RECONCILED)
        self.assertEqual(payment.recorded_by, self.register_actor)
        self.assertEqual(payment.reconciled_by, self.register_actor)
        self.assertIsNotNone(payment.recorded_at)
        self.assertIsNotNone(payment.reconciled_at)
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(self.hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(payment.turno_id, self.intent.confirmed_turno_id)
        self.assertEqual(result.financial.paid_reconciled, Decimal('30.00'))
        self.assertEqual(result.financial.confirmation_due, Decimal('0.00'))
        self.assertEqual(result.financial.balance, Decimal('970.00'))
        self.assertTrue(result.financial.financial_threshold_reached)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_MANUAL_REGISTERED).count(),
            1,
        )

    def test_transfer_starts_pending_with_private_validated_receipt(self):
        payment = self.register_transfer().payment
        snapshot = financial_snapshot(self.intent)

        self.assertEqual(
            payment.status,
            Pago.Status.PENDING_RECONCILIATION,
        )
        self.assertEqual(payment.manual_reference, 'BANK-REF-001')
        self.assertTrue(payment.comprobante_foto.name)
        self.assertEqual(len(payment.receipt_sha256), 64)
        with self.assertRaises(ValueError):
            PrivatePaymentReceiptStorage().url(payment.comprobante_foto.name)
        self.assertEqual(snapshot.paid_reconciled, Decimal('0.00'))
        self.assertEqual(snapshot.confirmation_due, Decimal('30.00'))

    def test_transfer_requires_reference_receipt_valid_mime_and_size(self):
        with self.assertRaises(Exception) as no_reference:
            self.register_transfer(manual_reference='')
        self.assertEqual(
            getattr(no_reference.exception, 'code', None),
            'MANUAL_REFERENCE_REQUIRED',
        )
        with self.assertRaises(Exception) as no_receipt:
            self.register_transfer(receipt=None)
        self.assertEqual(
            getattr(no_receipt.exception, 'code', None),
            'PAYMENT_RECEIPT_REQUIRED',
        )
        invalid = SimpleUploadedFile(
            'receipt.pdf',
            b'not a pdf',
            content_type='application/pdf',
        )
        with self.assertRaises(Exception) as invalid_content:
            self.register_transfer(receipt=invalid)
        self.assertEqual(
            getattr(invalid_content.exception, 'code', None),
            'RECEIPT_CONTENT_MISMATCH',
        )
        with self.assertRaises(Exception) as pan_reference:
            self.register_transfer(
                manual_reference='4111-1111-1111-1111',
            )
        self.assertEqual(
            getattr(pan_reference.exception, 'code', None),
            'SENSITIVE_CARD_DATA_FORBIDDEN',
        )

    def test_reconcile_accept_and_retry_are_idempotent(self):
        payment = self.register_transfer().payment
        accepted = reconcile_manual_payment(
            payment_public_id=payment.public_id,
            decision='ACCEPT',
            reason='',
            actor=self.reconcile_actor,
        )
        retry = reconcile_manual_payment(
            payment_public_id=payment.public_id,
            decision='ACCEPT',
            reason='',
            actor=self.reconcile_actor,
        )

        self.assertTrue(accepted.changed)
        self.assertFalse(retry.changed)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Pago.Status.RECONCILED)
        self.assertEqual(payment.reconciled_by, self.reconcile_actor)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_RECONCILED).count(),
            1,
        )
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.Status.PENDING)

    def test_reject_and_retry_are_idempotent(self):
        payment = self.register_transfer().payment
        rejected = reconcile_manual_payment(
            payment_public_id=payment.public_id,
            decision='REJECT',
            reason='No acreditado',
            actor=self.reconcile_actor,
        )
        retry = reconcile_manual_payment(
            payment_public_id=payment.public_id,
            decision='REJECT',
            reason='No acreditado',
            actor=self.reconcile_actor,
        )

        self.assertTrue(rejected.changed)
        self.assertFalse(retry.changed)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Pago.Status.REJECTED)
        self.assertEqual(payment.terminal_reason, 'No acreditado')
        self.assertEqual(financial_snapshot(self.intent).paid_reconciled, 0)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_REJECTED).count(),
            1,
        )

    def test_multiple_partial_payments_and_derived_sums(self):
        first = self.register(amount='10.00').payment
        second = self.register(
            amount='20.00',
            idempotency_key='b2-payment-second',
            occurred_at=self.occurred_at + timedelta(seconds=1),
        ).payment
        snapshot = financial_snapshot(self.intent)

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.intent.payments.count(), 2)
        self.assertEqual(snapshot.paid_reconciled, Decimal('30.00'))
        self.assertEqual(snapshot.confirmation_due, Decimal('0.00'))
        self.assertEqual(snapshot.balance, Decimal('970.00'))
        self.assertTrue(snapshot.financial_threshold_reached)

    def test_registration_idempotency_and_changed_payload_conflict(self):
        first = self.register()
        retry = self.register()
        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.payment.pk, retry.payment.pk)
        self.assertEqual(Pago.objects.filter(payment_intent=self.intent).count(), 1)
        with self.assertRaises(ManualPaymentConflict) as changed:
            self.register(amount='11.00')
        self.assertEqual(
            changed.exception.code,
            'PAYMENT_IDEMPOTENCY_KEY_REUSED',
        )

    def test_duplicate_reference_is_rejected(self):
        self.register_transfer()
        with self.assertRaises(ManualPaymentConflict) as duplicate:
            self.register_transfer(
                idempotency_key='different-key',
                occurred_at=self.occurred_at + timedelta(seconds=1),
                receipt=self.receipt('other.pdf'),
            )
        self.assertEqual(duplicate.exception.code, 'MANUAL_REFERENCE_REUSED')

    def test_invalid_amount_currency_method_and_overpayment(self):
        for amount in ('0.00', '-1.00'):
            with self.subTest(amount=amount):
                with self.assertRaises(Exception) as invalid:
                    self.register(amount=amount)
                self.assertEqual(
                    getattr(invalid.exception, 'code', None),
                    'INVALID_PAYMENT_AMOUNT',
                )
        with self.assertRaises(Exception) as currency:
            self.register(currency='USD')
        self.assertEqual(
            getattr(currency.exception, 'code', None),
            'PAYMENT_CURRENCY_MISMATCH',
        )
        self.register(amount='990.00')
        with self.assertRaises(ManualPaymentConflict) as overpayment:
            self.register(
                amount='11.00',
                idempotency_key='overpayment-key',
                occurred_at=self.occurred_at + timedelta(seconds=1),
            )
        self.assertEqual(overpayment.exception.code, 'PAYMENT_OVERPAYMENT')

    def test_late_evidence_is_preserved_pending_without_resurrection(self):
        past = timezone.now() - timedelta(minutes=1)
        models.QuerySet.update(
            PaymentIntent.objects.filter(pk=self.intent.pk),
            created_at=past - timedelta(minutes=10),
            expires_at=past,
        )
        result = self.register_transfer(
            late_evidence=True,
            occurred_at=past - timedelta(minutes=1),
        )
        payment = result.payment
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()

        self.assertEqual(payment.status, Pago.Status.PENDING_RECONCILIATION)
        self.assertEqual(payment.terminal_reason, LATE_MANUAL_REVIEW)
        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(self.hold.state, SlotHold.State.RELEASED)
        self.assertFalse(result.financial.financial_threshold_reached)
        with self.assertRaises(ManualPaymentConflict) as late_accept:
            reconcile_manual_payment(
                payment_public_id=payment.public_id,
                decision='ACCEPT',
                reason='',
                actor=self.reconcile_actor,
            )
        self.assertEqual(
            late_accept.exception.code,
            'LATE_PAYMENT_REQUIRES_FUTURE_REVIEW',
        )

    def test_payment_blocks_intent_cancellation(self):
        self.register()
        with self.assertRaises(PaymentIntentConflict) as conflict:
            cancel_payment_intent(
                public_id=self.intent.public_id,
                actor=self.user,
            )
        self.assertEqual(conflict.exception.code, 'PAYMENT_EXISTS')

    def test_payment_is_strongly_immutable(self):
        payment = self.register().payment
        payment.monto = Decimal('1.00')
        with self.assertRaises(ValidationError):
            payment.save()
        with self.assertRaises(ValidationError):
            Pago.objects.filter(pk=payment.pk).update(monto=Decimal('1.00'))
        with self.assertRaises(ValidationError):
            payment.delete()
        with self.assertRaises(ValidationError):
            Pago.objects.create(
                payment_intent=self.intent,
                monto='1.00',
                currency='ARS',
                metodo_pago=Pago.Method.CASH,
                purpose=Pago.Purpose.CONFIRMATION,
                status=Pago.Status.RECONCILED,
                fecha_pago=self.occurred_at,
                recorded_by=self.register_actor,
                reconciled_at=timezone.now(),
                reconciled_by=self.register_actor,
                idempotency_key='direct-payment',
            )

    def test_legacy_order_context_remains_compatible_and_protected(self):
        order = OrdenCompra.objects.create(
            codigo='LEGACY-B2-1',
            cliente=self.cliente,
            estado='PENDIENTE',
            total=Decimal('100.00'),
        )
        payment, created = Pago.objects.get_or_create(
            orden=order,
            transaccion_id='legacy-provider-id',
            defaults={
                'monto': Decimal('100.00'),
                'metodo_pago': 'MERCADO_PAGO',
                'fecha_pago': self.occurred_at,
            },
        )
        self.assertTrue(created)
        self.assertIsNone(payment.payment_intent_id)
        self.assertEqual(payment.status, Pago.Status.RECONCILED)
        with self.assertRaises(ProtectedError):
            order.delete()
        with self.assertRaises(ValidationError):
            Pago.objects._create_booking_from_service(
                payment_intent=None,
                orden=None,
                monto=Decimal('1.00'),
                metodo_pago='EFECTIVO',
                currency='ARS',
                purpose=Pago.Purpose.BALANCE,
                status=Pago.Status.RECONCILED,
                fecha_pago=self.occurred_at,
            )


class ManualPaymentPermissionAndApiTests(ManualPaymentFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.register_api = APIClient()
        self.register_api.force_authenticate(self.register_actor)
        self.reconcile_api = APIClient()
        self.reconcile_api.force_authenticate(self.reconcile_actor)
        self.owner_api = APIClient()
        self.owner_api.force_authenticate(self.user)
        self.staff_without_permission = Usuario.objects.create_user(
            email='staff-no-financial-permission@test.com',
            password='Payment!2026',
            is_staff=True,
        )
        self.staff_api = APIClient()
        self.staff_api.force_authenticate(self.staff_without_permission)
        self.payments_url = reverse(
            'payment-intent-payments',
            args=[self.intent.public_id],
        )

    def payload(self, **overrides):
        values = {
            'amount': '10.00',
            'currency': 'ARS',
            'method': Pago.Method.CASH,
            'purpose': Pago.Purpose.CONFIRMATION,
            'occurred_at': self.occurred_at.isoformat(),
        }
        values.update(overrides)
        return values

    def test_register_permission_works_without_staff_and_staff_without_it_is_403(self):
        response = self.register_api.post(
            self.payments_url,
            self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY='api-register',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(self.register_actor.is_staff)
        denied = self.staff_api.post(
            self.payments_url,
            self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY='api-staff-denied',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_permissions_are_separated_and_role_alone_does_not_authorize(self):
        with self.assertRaises(ManualPaymentPermissionDenied):
            self.register(actor=self.reconcile_actor)
        payment = self.register_transfer().payment
        with self.assertRaises(ManualPaymentPermissionDenied):
            reconcile_manual_payment(
                payment_public_id=payment.public_id,
                decision='ACCEPT',
                reason='',
                actor=self.register_actor,
            )

        professional = Usuario.objects.create_user(
            email='professional-no-payment@test.com',
            password='Payment!2026',
        )
        professional.groups.add(Group.objects.get(name=BusinessRole.PROFESIONAL))
        self.assertFalse(professional.has_perm('gestion.register_payment'))
        professional_api = APIClient()
        professional_api.force_authenticate(professional)
        denied = professional_api.post(
            self.payments_url,
            self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY='professional-denied',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        personal_role_user = Usuario.objects.create_user(
            email='legacy-personal-admin@test.com',
            password='Payment!2026',
        )
        Personal.objects.create(
            usuario=personal_role_user,
            nombre='Legacy',
            apellido='Admin',
            rol='administrador',
        )
        self.assertFalse(
            personal_role_user.has_perm('gestion.register_payment')
        )
        personal_api = APIClient()
        personal_api.force_authenticate(personal_role_user)
        denied = personal_api.post(
            self.payments_url,
            self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY='personal-role-denied',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_reconcile_endpoint_and_owner_payment_history_privacy(self):
        created = self.register_transfer().payment
        reconcile_url = reverse('payment-reconcile', args=[created.public_id])
        accepted = self.reconcile_api.post(
            reconcile_url,
            {'decision': 'ACCEPT'},
            format='json',
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertTrue(accepted.data['changed'])

        own_history = self.owner_api.get(self.payments_url)
        self.assertEqual(own_history.status_code, status.HTTP_200_OK)
        self.assertEqual(len(own_history.data['results']), 1)
        self.assertNotIn('idempotency_key', own_history.data['results'][0])

        stranger = Usuario.objects.create_user(
            email='payment-stranger@test.com',
            password='Payment!2026',
        )
        stranger_api = APIClient()
        stranger_api.force_authenticate(stranger)
        self.assertEqual(
            stranger_api.get(self.payments_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_global_reports_require_exact_permission(self):
        self.register()
        report_user = Usuario.objects.create_user(
            email='payment-reports@test.com',
            password='Payment!2026',
        )
        report_user.user_permissions.add(
            Permission.objects.get(codename='view_financial_reports')
        )
        report_api = APIClient()
        report_api.force_authenticate(report_user)
        report = report_api.get(reverse('payment-list'))
        self.assertEqual(report.status_code, status.HTTP_200_OK)
        self.assertIn('summary', report.data)
        self.assertIsNone(report.data['summary']['physical_cash_balance'])
        self.assertEqual(
            self.register_api.get(reverse('payment-list')).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.staff_api.get(reverse('payment-list')).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_legacy_order_registration_uses_permission_without_staff(self):
        order = OrdenCompra.objects.create(
            codigo='LEGACY-API-B2',
            cliente=self.cliente,
            estado='PENDIENTE',
            total=Decimal('50.00'),
        )
        response = self.register_api.post(
            reverse('orden-compra-registrar-pago', args=[order.pk]),
            {
                'monto': '50.00',
                'metodo_pago': 'EFECTIVO',
                'es_sena': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Pago.objects.get(orden=order)
        self.assertFalse(self.register_actor.is_staff)
        self.assertIsNone(payment.payment_intent_id)
        self.assertEqual(payment.recorded_by, self.register_actor)

    def test_receipt_endpoint_is_authorized_and_serializer_has_no_storage_url(self):
        payment = self.register_transfer().payment
        receipt_url = reverse('payment-receipt', args=[payment.public_id])
        response = self.reconcile_api.get(receipt_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stranger = Usuario.objects.create_user(
            email='receipt-stranger@test.com',
            password='Payment!2026',
        )
        stranger_api = APIClient()
        stranger_api.force_authenticate(stranger)
        self.assertEqual(
            stranger_api.get(receipt_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_no_generic_payment_crud_is_exposed(self):
        payment = self.register().payment
        detail = f"{reverse('payment-list')}{payment.public_id}/"
        self.assertIn(
            self.register_api.patch(detail, {}, format='json').status_code,
            {status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED},
        )
        self.assertIn(
            self.register_api.delete(detail).status_code,
            {status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED},
        )
