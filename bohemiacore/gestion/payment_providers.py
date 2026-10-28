"""Frontera única para llamadas externas a proveedores de pago (BH-058 C1)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

from django.conf import settings
from django.utils.dateparse import parse_datetime
import mercadopago
from mercadopago.config import RequestOptions
from decouple import config
import requests


class PaymentProviderError(Exception):
    code = 'PROVIDER_ERROR'
    outcome_unknown = False

    def __init__(self, detail=None):
        self.detail = detail or 'El proveedor rechazó la creación del checkout.'
        super().__init__(self.detail)


class PaymentProviderConfigurationError(PaymentProviderError):
    code = 'PROVIDER_CONFIGURATION_ERROR'


class PaymentProviderRejected(PaymentProviderError):
    code = 'PROVIDER_REJECTED'


class PaymentProviderOutcomeUnknown(PaymentProviderError):
    code = 'PROVIDER_OUTCOME_UNKNOWN'
    outcome_unknown = True


@dataclass(frozen=True)
class CheckoutRequest:
    external_reference: str
    idempotency_key: str
    amount: str
    currency: str
    payer_email: str
    title: str
    expires_at: datetime


@dataclass(frozen=True)
class CheckoutCreated:
    provider_order_id: str
    checkout_url: str
    provider_status: str
    expires_at: datetime | None


class PaymentProvider(Protocol):
    def create_checkout(self, request: CheckoutRequest) -> CheckoutCreated:
        ...


def _setting(name, default=''):
    if hasattr(settings, name):
        return getattr(settings, name)
    return config(name, default=default)


def _validated_return_url(name):
    value = str(_setting(name, '')).strip()
    parsed = urlparse(value)
    if not value or parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise PaymentProviderConfigurationError(
            f'Falta configurar una URL absoluta válida en {name}.'
        )
    if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1'}:
        raise PaymentProviderConfigurationError(
            f'{name} debe usar HTTPS fuera de desarrollo local.'
        )
    return value


def configured_checkout_currency():
    currency = str(_setting('MERCADO_PAGO_CHECKOUT_CURRENCY', '')).strip().upper()
    if currency not in {'ARS'}:
        raise PaymentProviderConfigurationError(
            'MERCADO_PAGO_CHECKOUT_CURRENCY debe configurarse explícitamente como ARS.'
        )
    return currency


class MercadoPagoAdapter:
    """Adapter de Mercado Pago; ninguna capa de dominio usa el SDK directamente."""

    UNKNOWN_HTTP_STATUSES = {408, 423, 429}

    def __init__(self):
        token = str(_setting('MERCADO_PAGO_ACCESS_TOKEN', '')).strip()
        if not token:
            raise PaymentProviderConfigurationError(
                'Falta configurar MERCADO_PAGO_ACCESS_TOKEN.'
            )
        try:
            timeout = float(_setting('MERCADO_PAGO_CHECKOUT_TIMEOUT_SECONDS', '8'))
        except (TypeError, ValueError) as exc:
            raise PaymentProviderConfigurationError(
                'MERCADO_PAGO_CHECKOUT_TIMEOUT_SECONDS no es válido.'
            ) from exc
        if timeout <= 0 or timeout > 60:
            raise PaymentProviderConfigurationError(
                'MERCADO_PAGO_CHECKOUT_TIMEOUT_SECONDS debe estar entre 0 y 60.'
            )
        self.request_options = RequestOptions(
            access_token=token,
            connection_timeout=timeout,
            max_retries=0,
        )
        self.sdk = mercadopago.SDK(token, request_options=self.request_options)

    @staticmethod
    def _response_parts(result):
        if not isinstance(result, dict):
            raise PaymentProviderOutcomeUnknown()
        return result.get('status'), result.get('response') or {}

    @staticmethod
    def _checkout_url(value):
        parsed = urlparse(str(value or ''))
        hostname = (parsed.hostname or '').lower()
        if (
            parsed.scheme != 'https'
            or not hostname
            or not (
                hostname == 'mercadopago.com'
                or hostname == 'mercadopago.com.ar'
                or hostname.startswith('www.mercadopago.')
                or hostname.endswith('.mercadopago.com')
                or hostname.endswith('.mercadopago.com.ar')
            )
        ):
            raise PaymentProviderOutcomeUnknown(
                'Mercado Pago devolvió una URL de checkout no verificable.'
            )
        return str(value)

    @staticmethod
    def _provider_expiry(value):
        if not value:
            return None
        parsed = parse_datetime(str(value))
        if parsed is None:
            raise PaymentProviderOutcomeUnknown(
                'Mercado Pago devolvió una expiración no verificable.'
            )
        return parsed

    def create_checkout(self, request):
        configured_currency = configured_checkout_currency()
        if request.currency != configured_currency:
            raise PaymentProviderConfigurationError(
                'La moneda de la obligación no coincide con la cuenta configurada.'
            )
        success_url = _validated_return_url('MERCADO_PAGO_CHECKOUT_SUCCESS_URL')
        failure_url = _validated_return_url('MERCADO_PAGO_CHECKOUT_FAILURE_URL')
        pending_url = _validated_return_url('MERCADO_PAGO_CHECKOUT_PENDING_URL')
        payload = {
            'type': 'online',
            'external_reference': request.external_reference,
            'processing_mode': 'automatic',
            'total_amount': request.amount,
            'payer': {'email': request.payer_email},
            'items': [{
                'title': request.title[:120],
                'quantity': 1,
                'unit_price': request.amount,
            }],
            'transactions': {'payments': [{'amount': request.amount}]},
            'expiration_time': request.expires_at.isoformat(timespec='seconds'),
            'config': {'online': {
                'success_url': success_url,
                'failure_url': failure_url,
                'pending_url': pending_url,
                'auto_return': 'approved',
            }},
        }
        options = RequestOptions(
            access_token=self.request_options.access_token,
            connection_timeout=self.request_options.connection_timeout,
            custom_headers={'X-Idempotency-Key': request.idempotency_key},
            max_retries=0,
        )
        try:
            result = self.sdk.order().create(payload, request_options=options)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise PaymentProviderOutcomeUnknown() from exc
        except Exception as exc:
            # Una excepción del SDK puede ocurrir después de enviar la solicitud.
            raise PaymentProviderOutcomeUnknown() from exc

        http_status, response = self._response_parts(result)
        try:
            http_status = int(http_status)
        except (TypeError, ValueError) as exc:
            raise PaymentProviderOutcomeUnknown() from exc
        if http_status in self.UNKNOWN_HTTP_STATUSES or http_status >= 500:
            raise PaymentProviderOutcomeUnknown()
        if http_status not in {200, 201}:
            raise PaymentProviderRejected(
                f'Mercado Pago rechazó el checkout (HTTP {http_status}).'
            )
        provider_order_id = str(response.get('id') or '').strip()
        if not provider_order_id:
            raise PaymentProviderOutcomeUnknown(
                'Mercado Pago no devolvió un identificador de orden.'
            )
        return CheckoutCreated(
            provider_order_id=provider_order_id,
            checkout_url=self._checkout_url(response.get('checkout_url')),
            provider_status=str(response.get('status') or ''),
            expires_at=self._provider_expiry(response.get('expiration_time')),
        )

    def fetch_order(self, provider_order_id):
        """Consulta técnica sin conceder autoridad financiera a C1."""
        try:
            return self.sdk.order().get(
                provider_order_id,
                request_options=self.request_options,
            )
        except Exception as exc:
            raise PaymentProviderOutcomeUnknown() from exc

    def fetch_legacy_payment(self, payment_id):
        """Compatibilidad aislada del webhook previo a C1."""
        try:
            return self.sdk.payment().get(
                payment_id,
                request_options=self.request_options,
            )
        except Exception as exc:
            raise PaymentProviderOutcomeUnknown() from exc

    def create_legacy_preference(self, payload):
        """Compatibilidad aislada; los checkouts C1 no usan Preferences."""
        try:
            return self.sdk.preference().create(
                payload,
                request_options=self.request_options,
            )
        except Exception as exc:
            raise PaymentProviderOutcomeUnknown() from exc


def get_payment_provider(provider):
    if provider == 'MERCADO_PAGO':
        return MercadoPagoAdapter()
    raise PaymentProviderConfigurationError('Proveedor de pago no soportado.')
