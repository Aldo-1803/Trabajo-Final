from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    CompromisoStock,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentPolicy,
    ProviderPaymentAttempt,
    SlotHold,
    Turno,
)
from gestion.order_inventory_services import create_order_stock_commitments
from gestion.payment_intent_services import (
    cancel_payment_intent,
    create_payment_intent,
    publish_payment_policy,
)
from gestion.payment_providers import (
    CheckoutCreated,
    PaymentProviderConfigurationError,
    PaymentProviderOutcomeUnknown,
)
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin
from usuarios.models import Usuario


def checkout_created(identifier='mp-order-1'):
    return CheckoutCreated(
        provider_order_id=identifier,
        checkout_url='https://www.mercadopago.com.ar/checkout/v1/redirect?id=opaque',
        provider_status='created',
        expires_at=timezone.now() + timedelta(minutes=20),
    )


class OrderProviderCheckoutTests(OrderInventoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.receive(self.product, 3, 'provider-checkout')
        self.order = self.make_order([(self.product, 2)])
        create_order_stock_commitments(self.order.pk)
        self.url = reverse('orden-compra-checkout', args=[self.order.pk])

    @staticmethod
    def provider(*effects):
        adapter = Mock()
        adapter.create_checkout.side_effect = effects or None
        if not effects:
            adapter.create_checkout.return_value = checkout_created()
        return adapter

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_order_checkout_is_idempotent_and_has_no_financial_effects(self, factory):
        adapter = self.provider()
        factory.return_value = adapter

        first = self.api.post(
            self.url,
            {'channel': 'ONLINE'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='order-checkout-key',
        )
        retry = self.api.post(
            self.url,
            {'channel': 'ONLINE'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='order-checkout-key',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['public_id'], retry.data['public_id'])
        self.assertEqual(first.data['amount'], '200.00')
        self.assertFalse(first.data['financial_authority'])
        self.assertEqual(adapter.create_checkout.call_count, 1)
        self.assertEqual(ProviderPaymentAttempt.objects.count(), 1)
        self.assertFalse(Pago.objects.exists())
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.estado, 'PENDIENTE')
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(self.product.stock_comprometido, 2)

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_unknown_outcome_retries_same_provider_key_without_duplicate(self, factory):
        adapter = self.provider(
            PaymentProviderOutcomeUnknown(),
            checkout_created('mp-after-timeout'),
        )
        factory.return_value = adapter

        first = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='unknown-key',
        )
        attempt = ProviderPaymentAttempt.objects.get()
        second = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='unknown-key',
        )
        attempt.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(first.data['status'], 'OUTCOME_UNKNOWN')
        self.assertIsNone(first.data['checkout_url'])
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data['status'], 'READY')
        self.assertEqual(ProviderPaymentAttempt.objects.count(), 1)
        self.assertEqual(attempt.provider_call_count, 2)
        keys = [
            call.args[0].idempotency_key
            for call in adapter.create_checkout.call_args_list
        ]
        self.assertEqual(keys[0], keys[1])

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_new_key_cannot_bypass_unknown_attempt(self, factory):
        adapter = self.provider(PaymentProviderOutcomeUnknown())
        factory.return_value = adapter
        first = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='uncertain-original',
        )
        repeated = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='uncertain-new-key',
        )
        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(repeated.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(first.data['public_id'], repeated.data['public_id'])
        self.assertEqual(adapter.create_checkout.call_count, 1)

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_configuration_failure_retries_same_cart_obligation(self, factory):
        adapter = self.provider(
            PaymentProviderConfigurationError('Falta configuración.'),
            checkout_created('mp-after-config'),
        )
        factory.return_value = adapter
        first = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='configuration-retry',
        )
        second = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='configuration-retry',
        )
        self.assertEqual(first.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['public_id'], second.data['public_id'])
        self.assertEqual(ProviderPaymentAttempt.objects.count(), 1)

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_in_person_requires_exact_permission(self, factory):
        factory.return_value = self.provider()
        denied = self.api.post(
            self.url,
            {'channel': 'IN_PERSON'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='in-person-denied',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ProviderPaymentAttempt.objects.count(), 0)

        operator = Usuario.objects.create_user(
            email='checkout-operator@test.com',
            password='Checkout!2026',
        )
        operator.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='register_payment',
        ))
        self.api.force_authenticate(operator)
        allowed = self.api.post(
            self.url,
            {'channel': 'IN_PERSON'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='in-person-allowed',
        )
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(allowed.data['channel'], 'IN_PERSON')

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_order_amount_cannot_be_supplied_or_recomputed_from_request(self, factory):
        factory.return_value = self.provider()
        response = self.api.post(
            self.url,
            {'channel': 'ONLINE', 'amount': '1.00'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='arbitrary-amount',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ProviderPaymentAttempt.objects.exists())

    @patch('gestion.views.MercadoPagoAdapter.fetch_legacy_payment')
    def test_legacy_webhook_ignores_namespaced_c1_reference(self, fetch_payment):
        fetch_payment.return_value = {
            'response': {
                'status': 'approved',
                'external_reference': 'bh:c1:order:opaque-reference',
                'transaction_amount': '200.00',
            }
        }
        response = self.api.post(
            reverse('webhook_mp'),
            {'type': 'payment', 'data': {'id': 'legacy-event-for-c1'}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Pago.objects.exists())
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.estado, 'PENDIENTE')
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(self.product.stock_comprometido, 2)


class BookingProviderCheckoutTests(SlotHoldFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        admin = Usuario.objects.create_user(
            email='checkout-policy@test.com',
            password='Checkout!2026',
        )
        admin.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_payment_configuration',
        ))
        policy = PaymentPolicy.objects.create(
            version='CHECKOUT-C1',
            allowed_mode=PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL,
            deposit_kind=PaymentPolicy.DepositKind.PERCENTAGE,
            deposit_value=Decimal('25.00'),
            currency='ARS',
            intent_ttl_minutes=10,
            enabled_manual_methods=['CASH'],
            created_by=admin,
        )
        publish_payment_policy(policy_id=policy.pk, actor=admin)
        self.hold = self.create_hold(key='checkout-hold')
        self.intent = create_payment_intent(
            hold=self.hold,
            mode=PaymentIntent.Mode.DEPOSIT,
            idempotency_key='checkout-intent',
            actor=self.user,
        ).intent
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.url = reverse(
            'payment-intent-checkout',
            args=[self.intent.public_id],
        )

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_booking_checkout_freezes_intent_without_turno_or_hold_mutation(self, factory):
        adapter = Mock()
        adapter.create_checkout.return_value = checkout_created('booking-order')
        factory.return_value = adapter

        response = self.api.post(
            self.url,
            {'channel': 'ONLINE'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='booking-checkout',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['amount'], str(self.intent.required_amount))
        self.assertEqual(response.data['currency'], self.intent.currency)
        self.assertFalse(Turno.objects.exists())
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.Status.CREATED)
        self.assertEqual(self.hold.state, SlotHold.State.ACTIVE)
        self.assertEqual(self.hold.expires_at, self.intent.slot_hold.expires_at)

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_booking_checkout_rejects_non_owner_without_authority(self, factory):
        factory.return_value = SimpleNamespace(create_checkout=Mock())
        self.api.force_authenticate(self.other_user)
        response = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='not-owner',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ProviderPaymentAttempt.objects.exists())

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_late_provider_response_does_not_reactivate_released_hold(self, factory):
        def release_during_http(_request):
            cancel_payment_intent(
                public_id=self.intent.public_id,
                actor=self.user,
            )
            return checkout_created('late-booking-order')

        adapter = Mock()
        adapter.create_checkout.side_effect = release_during_http
        factory.return_value = adapter
        response = self.api.post(
            self.url,
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='late-booking-checkout',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['status'], 'EXPIRED')
        self.assertIsNone(response.data['checkout_url'])
        self.hold.refresh_from_db()
        self.intent.refresh_from_db()
        self.assertEqual(self.hold.state, SlotHold.State.RELEASED)
        self.assertEqual(self.intent.status, PaymentIntent.Status.CANCELLED)
        self.assertFalse(Turno.objects.exists())
