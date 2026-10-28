from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
import requests

from gestion.payment_providers import (
    CheckoutRequest,
    MercadoPagoAdapter,
    PaymentProviderConfigurationError,
    PaymentProviderOutcomeUnknown,
    PaymentProviderRejected,
    PaymentProviderTemporaryError,
)


@override_settings(
    MERCADO_PAGO_ACCESS_TOKEN='TEST-token-backend-only',
    MERCADO_PAGO_CHECKOUT_CURRENCY='ARS',
    MERCADO_PAGO_CHECKOUT_TIMEOUT_SECONDS='4',
    MERCADO_PAGO_CHECKOUT_SUCCESS_URL='https://bohemia.test/compra-exitosa',
    MERCADO_PAGO_CHECKOUT_PENDING_URL='https://bohemia.test/compra-pendiente',
    MERCADO_PAGO_CHECKOUT_FAILURE_URL='https://bohemia.test/compra-fallida',
)
class MercadoPagoAdapterTests(SimpleTestCase):
    @staticmethod
    def request():
        return CheckoutRequest(
            external_reference='bh:c1:order:opaque',
            idempotency_key='bh-c1-opaque',
            amount='125.50',
            currency='ARS',
            payer_email='payer@test.com',
            title='Compra Bohemia Hair',
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    @patch('gestion.payment_providers.mercadopago.SDK')
    def test_orders_api_payload_timeout_and_idempotency_header(self, sdk_class):
        sdk_class.return_value.order.return_value.create.return_value = {
            'status': 201,
            'response': {
                'id': '01JMP-ORDER',
                'status': 'created',
                'checkout_url': 'https://www.mercadopago.com.ar/checkout/opaque',
                'expiration_time': (
                    timezone.now() + timedelta(minutes=15)
                ).isoformat(),
            },
        }

        created = MercadoPagoAdapter().create_checkout(self.request())

        self.assertEqual(created.provider_order_id, '01JMP-ORDER')
        payload = sdk_class.return_value.order.return_value.create.call_args.args[0]
        options = sdk_class.return_value.order.return_value.create.call_args.kwargs[
            'request_options'
        ]
        self.assertEqual(payload['type'], 'online')
        self.assertEqual(payload['external_reference'], 'bh:c1:order:opaque')
        self.assertEqual(payload['total_amount'], '125.50')
        self.assertEqual(payload['transactions']['payments'][0]['amount'], '125.50')
        self.assertEqual(options.custom_headers['X-Idempotency-Key'], 'bh-c1-opaque')
        self.assertEqual(options.connection_timeout, 4.0)
        self.assertEqual(options.max_retries, 0)

    @patch('gestion.payment_providers.mercadopago.SDK')
    def test_timeout_and_locked_response_are_outcome_unknown(self, sdk_class):
        create = sdk_class.return_value.order.return_value.create
        create.side_effect = requests.Timeout()
        with self.assertRaises(PaymentProviderOutcomeUnknown):
            MercadoPagoAdapter().create_checkout(self.request())

        create.side_effect = None
        create.return_value = {'status': 423, 'response': {'status': 'processing'}}
        with self.assertRaises(PaymentProviderOutcomeUnknown):
            MercadoPagoAdapter().create_checkout(self.request())

    @override_settings(MERCADO_PAGO_CHECKOUT_CURRENCY='USD')
    @patch('gestion.payment_providers.mercadopago.SDK')
    def test_currency_configuration_fails_closed_before_http(self, sdk_class):
        with self.assertRaises(PaymentProviderConfigurationError):
            MercadoPagoAdapter().create_checkout(self.request())
        sdk_class.return_value.order.return_value.create.assert_not_called()

    @patch('gestion.payment_providers.mercadopago.SDK')
    def test_untrusted_checkout_url_is_not_exposed(self, sdk_class):
        sdk_class.return_value.order.return_value.create.return_value = {
            'status': 201,
            'response': {
                'id': '01JMP-ORDER',
                'checkout_url': 'https://attacker.test/checkout',
            },
        }
        with self.assertRaises(PaymentProviderOutcomeUnknown):
            MercadoPagoAdapter().create_checkout(self.request())

    @patch('gestion.payment_providers.mercadopago.SDK')
    def test_fetch_provider_order_uses_orders_api_and_sanitizes(self, sdk_class):
        sdk_class.return_value.order.return_value.get.return_value = {
            'status': 200,
            'response': {
                'id': '01JMP-ORDER',
                'status': 'processed',
                'status_detail': 'accredited',
                'external_reference': 'bh:c1:order:opaque',
                'total_amount': '125.50',
                'total_paid_amount': '125.50',
                'currency_id': 'ARS',
                'live_mode': False,
                'integration_data': {'application_id': 'app-123'},
                'user_id': 'seller-456',
                'type': 'online',
                'country_code': 'AR',
                'transactions': {'payments': [{'status': 'processed'}]},
                'payer': {'email': 'must-not-be-persisted@test.com'},
            },
        }

        snapshot = MercadoPagoAdapter().fetch_provider_order('01JMP-ORDER')

        self.assertEqual(snapshot.total_amount, Decimal('125.50'))
        self.assertEqual(snapshot.application_id, 'app-123')
        self.assertEqual(snapshot.environment, 'sandbox')
        self.assertNotIn('payer', snapshot.sanitized())
        sdk_class.return_value.order.return_value.get.assert_called_once()

    @patch('gestion.payment_providers.mercadopago.SDK')
    def test_fetch_provider_order_classifies_temporary_and_permanent_errors(self, sdk_class):
        fetch = sdk_class.return_value.order.return_value.get
        fetch.side_effect = requests.Timeout()
        with self.assertRaises(PaymentProviderTemporaryError):
            MercadoPagoAdapter().fetch_provider_order('01JMP-ORDER')

        fetch.side_effect = None
        fetch.return_value = {'status': 503, 'response': {}}
        with self.assertRaises(PaymentProviderTemporaryError):
            MercadoPagoAdapter().fetch_provider_order('01JMP-ORDER')

        fetch.return_value = {'status': 404, 'response': {}}
        with self.assertRaises(PaymentProviderRejected):
            MercadoPagoAdapter().fetch_provider_order('01JMP-ORDER')
