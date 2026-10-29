from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    PaymentIntent,
    PaymentPolicy,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    SlotHold,
)
from gestion.payment_intent_services import publish_payment_policy
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin
from usuarios.models import Usuario


class BookingFrontendReadApiTests(SlotHoldFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        policy_actor = Usuario.objects.create_user(
            email='f3-policy@test.com',
            password='Payment!2026',
        )
        policy_actor.user_permissions.add(Permission.objects.get(
            codename='manage_payment_configuration'
        ))
        policy = PaymentPolicy.objects.create(
            version='F3-POLICY',
            allowed_mode=PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL,
            deposit_kind=PaymentPolicy.DepositKind.PERCENTAGE,
            deposit_value=Decimal('25.00'),
            fixed_exceeds_total_behavior=None,
            currency='ARS',
            intent_ttl_minutes=10,
            enabled_manual_methods=['CASH'],
            created_by=policy_actor,
        )
        publish_payment_policy(policy_id=policy.pk, actor=policy_actor)
        self.hold = self.create_hold(key='f3-hold')
        self.owner_api = APIClient()
        self.owner_api.force_authenticate(self.user)
        self.other_api = APIClient()
        self.other_api.force_authenticate(self.other_user)

    def options_url(self, hold=None):
        return (
            reverse('payment-intent-options')
            + f'?slot_hold_public_id={(hold or self.hold).public_id}'
        )

    def create_intent(self, *, mode=PaymentIntent.Mode.DEPOSIT):
        response = self.owner_api.post(
            reverse('payment-intent-list'),
            {
                'slot_hold_public_id': str(self.hold.public_id),
                'mode': mode,
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=f'f3-intent-{mode.lower()}',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response

    def test_options_are_backend_calculated_and_owner_scoped(self):
        response = self.owner_api.get(self.options_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['policy_version'], 'F3-POLICY')
        self.assertEqual(response.data['total_amount'], '1000.00')
        self.assertEqual(response.data['currency'], 'ARS')
        self.assertEqual(response.data['modes'], [
            {'mode': 'DEPOSIT', 'required_amount': '250.00'},
            {'mode': 'FULL', 'required_amount': '1000.00'},
        ])
        self.assertIsNone(response.data['existing_intent'])
        self.assertFalse(PaymentIntent.objects.exists())
        self.assertEqual(
            self.other_api.get(self.options_url()).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_hold_history_is_private_and_supports_frontend_resume(self):
        owner = self.owner_api.get(reverse('slot-hold-list'))
        other = self.other_api.get(reverse('slot-hold-list'))

        self.assertEqual(owner.status_code, status.HTTP_200_OK)
        self.assertEqual(other.status_code, status.HTTP_200_OK)
        self.assertEqual(len(owner.data), 1)
        self.assertEqual(other.data, [])
        self.assertEqual(owner.data[0]['solicitud_id'], self.solicitud.pk)
        self.assertEqual(owner.data[0]['effective_state'], SlotHold.State.ACTIVE)
        self.assertIn('expires_at', owner.data[0])
        self.assertIn('created_at', owner.data[0])

    def test_options_reuse_existing_intent_and_expose_safe_tracking(self):
        created = self.create_intent()
        response = self.owner_api.get(self.options_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        existing = response.data['existing_intent']
        self.assertEqual(existing['public_id'], created.data['public_id'])
        self.assertEqual(existing['tracking']['state'], 'READY_FOR_CHECKOUT')
        self.assertEqual(existing['hold_effective_state'], SlotHold.State.ACTIVE)
        self.assertIsNone(existing['confirmed_turno_id'])
        self.assertEqual(PaymentIntent.objects.count(), 1)

    def test_expired_hold_has_no_payment_options(self):
        expired_request = self.create_approved_request(
            self.cliente,
            self.service,
            self.date,
            order=1,
        )
        expired = self.direct_hold(
            solicitud=expired_request,
            state=SlotHold.State.EXPIRED,
            key='f3-expired',
        )

        response = self.owner_api.get(self.options_url(expired))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'HOLD_EXPIRED')
        self.assertEqual(PaymentIntent.objects.count(), 0)

    def test_tracking_uses_persisted_checkout_and_review_state(self):
        created = self.create_intent()
        intent = PaymentIntent.objects.get(public_id=created.data['public_id'])
        attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=intent,
            amount=intent.required_amount,
            currency=intent.currency,
            external_reference='bh:c1:booking:f3-tracking',
            client_idempotency_key='f3-checkout',
            provider_idempotency_key='f3-provider-checkout',
            request_fingerprint='f' * 64,
            provider_order_id='F3-ORDER',
            provider_status='created',
            checkout_url='https://www.mercadopago.com.ar/checkout/f3',
            provider_expires_at=timezone.now() + timedelta(minutes=10),
            response_received_at=timezone.now(),
            created_by=self.user,
        )
        detail_url = reverse('payment-intent-detail', args=[intent.public_id])

        verification = self.owner_api.get(detail_url)

        self.assertEqual(verification.status_code, status.HTTP_200_OK)
        self.assertEqual(
            verification.data['tracking']['state'],
            'PAYMENT_VERIFICATION',
        )
        self.assertEqual(
            verification.data['checkout']['public_id'],
            str(attempt.public_id),
        )
        self.assertFalse(verification.data['checkout']['financial_authority'])

        PaymentReconciliationCase.objects._create_from_service(
            payment_intent=intent,
            slot_hold=self.hold,
            turno=None,
            order=None,
            provider_attempt=attempt,
            provider_event=None,
            case_type=PaymentReconciliationCase.Type.LATE_PAYMENT,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code='LATE_PAYMENT',
            operation_key='f3-review-case',
            details={'decision': 'REVIEW_REQUIRED'},
            created_by=None,
            created_at=timezone.now(),
        )
        review = self.owner_api.get(detail_url)

        self.assertEqual(
            review.data['tracking']['state'],
            'PAID_WITHOUT_BOOKING',
        )
        self.assertEqual(review.data['tracking']['code'], 'LATE_PAYMENT')
        self.assertEqual(
            self.other_api.get(detail_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_tracking_distinguishes_pending_and_rejected_provider_states(self):
        created = self.create_intent()
        intent = PaymentIntent.objects.get(public_id=created.data['public_id'])
        attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=intent,
            amount=intent.required_amount,
            currency=intent.currency,
            external_reference='bh:c1:booking:f3-provider-state',
            client_idempotency_key='f3-provider-state',
            provider_idempotency_key='f3-provider-state-key',
            request_fingerprint='e' * 64,
            provider_order_id='F3-PROVIDER-STATE',
            provider_status='created',
            checkout_url='https://www.mercadopago.com.ar/checkout/f3-state',
            provider_expires_at=timezone.now() + timedelta(minutes=10),
            response_received_at=timezone.now(),
            created_by=self.user,
        )
        detail_url = reverse('payment-intent-detail', args=[intent.public_id])
        pending = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.updated',
            event_id='f3-pending',
            provider_resource_id=attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=attempt,
            provider_snapshot={'status': 'processing'},
            reconciliation_status=ProviderEvent.ReconciliationStatus.IGNORED,
            reconciliation_code='PAYMENT_NOT_ACCREDITED',
        )

        response = self.owner_api.get(detail_url)

        self.assertEqual(response.data['tracking']['state'], 'PAYMENT_PENDING')
        self.assertTrue(response.data['tracking']['requires_polling'])

        ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.updated',
            event_id='f3-rejected',
            provider_resource_id=attempt.provider_order_id,
            received_at=pending.received_at + timedelta(seconds=1),
            status=ProviderEvent.Status.VERIFIED,
            attempt=attempt,
            provider_snapshot={'status': 'failed'},
            reconciliation_status=ProviderEvent.ReconciliationStatus.IGNORED,
            reconciliation_code='PAYMENT_NOT_ACCREDITED',
        )

        response = self.owner_api.get(detail_url)

        self.assertEqual(response.data['tracking']['state'], 'PAYMENT_REJECTED')
        self.assertFalse(response.data['tracking']['requires_polling'])
