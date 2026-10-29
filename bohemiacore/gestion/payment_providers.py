"""Frontera única para llamadas externas a proveedores (BH-058 C1/C2a)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
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


class PaymentProviderTemporaryError(PaymentProviderError):
    code = 'PROVIDER_TEMPORARY_ERROR'
    outcome_unknown = True


class PaymentProviderResponseInvalid(PaymentProviderError):
    code = 'PROVIDER_RESPONSE_INVALID'


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


@dataclass(frozen=True)
class ProviderOrderSnapshot:
    provider_order_id: str
    status: str
    status_detail: str
    external_reference: str
    total_amount: Decimal | None
    total_paid_amount: Decimal | None
    currency: str
    application_id: str
    seller_id: str
    environment: str
    order_type: str
    country_code: str
    transaction_statuses: tuple[str, ...]
    created_date: str = ''
    last_updated_date: str = ''
    payments: tuple[dict, ...] = ()
    refunds: tuple[dict, ...] = ()
    chargebacks: tuple[dict, ...] = ()

    def sanitized(self):
        return {
            'id': self.provider_order_id,
            'status': self.status,
            'status_detail': self.status_detail,
            'external_reference': self.external_reference,
            'total_amount': (
                str(self.total_amount) if self.total_amount is not None else None
            ),
            'total_paid_amount': (
                str(self.total_paid_amount)
                if self.total_paid_amount is not None else None
            ),
            'currency': self.currency,
            'application_id': self.application_id,
            'seller_id': self.seller_id,
            'environment': self.environment,
            'type': self.order_type,
            'country_code': self.country_code,
            'transaction_statuses': list(self.transaction_statuses),
            'created_date': self.created_date,
            'last_updated_date': self.last_updated_date,
            'payments': list(self.payments),
            'refunds': list(self.refunds),
            'chargebacks': list(self.chargebacks),
        }


class PaymentProvider(Protocol):
    def create_checkout(self, request: CheckoutRequest) -> CheckoutCreated:
        ...

    def fetch_provider_order(self, order_id: str) -> ProviderOrderSnapshot:
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

    @staticmethod
    def _decimal_or_none(value):
        if value in (None, ''):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PaymentProviderResponseInvalid(
                'Mercado Pago devolvió un importe no verificable.'
            ) from exc

    @staticmethod
    def _first_mapping(value):
        if isinstance(value, list):
            return next((item for item in value if isinstance(item, dict)), {})
        if isinstance(value, dict):
            return value
        return {}

    @classmethod
    def _payment_snapshots(cls, value):
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return ()
        snapshots = []
        for item in value:
            if not isinstance(item, dict):
                continue
            snapshots.append({
                'id': str(item.get('id') or '')[:128],
                'amount': cls._amount_text(item.get('amount')),
                'paid_amount': cls._amount_text(item.get('paid_amount')),
                'confirmed_amount': cls._amount_text(
                    item.get('confirmed_amount')
                ),
                'status': str(item.get('status') or '')[:50],
                'status_detail': str(item.get('status_detail') or '')[:100],
                'created_date': str(item.get('created_date') or '')[:64],
                'last_updated_date': str(
                    item.get('last_updated_date') or ''
                )[:64],
            })
        return tuple(snapshots)

    @classmethod
    def _refund_snapshots(cls, value):
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return ()
        return tuple({
            'id': str(item.get('id') or '')[:128],
            'transaction_id': str(item.get('transaction_id') or '')[:128],
            'amount': cls._amount_text(item.get('amount')),
            'status': str(item.get('status') or '')[:50],
        } for item in value if isinstance(item, dict))

    @staticmethod
    def _chargeback_snapshots(value):
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return ()
        return tuple({
            'id': str(item.get('id') or '')[:128],
            'transaction_id': str(item.get('transaction_id') or '')[:128],
            'status': str(item.get('status') or '')[:50],
        } for item in value if isinstance(item, dict))

    @classmethod
    def _amount_text(cls, value):
        amount = cls._decimal_or_none(value)
        return str(amount) if amount is not None else ''

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

    def fetch_provider_order(self, order_id):
        """Consulta y reduce una Order a un snapshot técnico no sensible."""
        order_id = str(order_id or '').strip()
        if not order_id or len(order_id) > 128:
            raise PaymentProviderResponseInvalid(
                'El identificador de Order no es válido.'
            )
        try:
            result = self.sdk.order().get(
                order_id,
                request_options=self.request_options,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise PaymentProviderTemporaryError() from exc
        except Exception as exc:
            raise PaymentProviderTemporaryError() from exc

        try:
            http_status, response = self._response_parts(result)
        except PaymentProviderOutcomeUnknown as exc:
            raise PaymentProviderTemporaryError() from exc
        try:
            http_status = int(http_status)
        except (TypeError, ValueError) as exc:
            raise PaymentProviderTemporaryError() from exc
        if http_status in self.UNKNOWN_HTTP_STATUSES or http_status >= 500:
            raise PaymentProviderTemporaryError(
                f'Mercado Pago no pudo responder la consulta (HTTP {http_status}).'
            )
        if http_status not in {200, 201}:
            raise PaymentProviderRejected(
                f'Mercado Pago rechazó la consulta de Order (HTTP {http_status}).'
            )
        if not isinstance(response, dict):
            raise PaymentProviderResponseInvalid()

        transactions = response.get('transactions') or {}
        payments = self._first_mapping(
            transactions.get('payments') if isinstance(transactions, dict) else {}
        )
        integration = response.get('integration_data') or {}
        if not isinstance(integration, dict):
            integration = {}
        live_mode = response.get('live_mode')
        environment = ''
        if isinstance(live_mode, bool):
            environment = 'production' if live_mode else 'sandbox'
        currency = (
            response.get('currency')
            or response.get('currency_id')
            or payments.get('currency')
            or payments.get('currency_id')
            or ''
        )
        payment_values = (
            transactions.get('payments', [])
            if isinstance(transactions, dict)
            else []
        )
        if isinstance(payment_values, dict):
            payment_values = [payment_values]
        transaction_statuses = tuple(
            str(item.get('status') or '')[:50]
            for item in payment_values
            if isinstance(item, dict) and item.get('status')
        )
        payment_snapshots = self._payment_snapshots(payment_values)
        refund_snapshots = self._refund_snapshots(
            transactions.get('refunds', [])
            if isinstance(transactions, dict)
            else []
        )
        chargeback_snapshots = self._chargeback_snapshots(
            transactions.get('chargebacks', [])
            if isinstance(transactions, dict)
            else []
        )
        return ProviderOrderSnapshot(
            provider_order_id=str(response.get('id') or '').strip(),
            status=str(response.get('status') or '')[:50],
            status_detail=str(response.get('status_detail') or '')[:100],
            external_reference=str(response.get('external_reference') or '')[:128],
            total_amount=self._decimal_or_none(response.get('total_amount')),
            total_paid_amount=self._decimal_or_none(
                response.get('total_paid_amount')
            ),
            currency=str(currency).strip().upper()[:3],
            application_id=str(
                integration.get('application_id')
                or response.get('application_id')
                or ''
            )[:128],
            seller_id=str(
                response.get('user_id') or response.get('collector_id') or ''
            )[:128],
            environment=environment,
            order_type=str(response.get('type') or '')[:30],
            country_code=str(response.get('country_code') or '')[:10],
            transaction_statuses=transaction_statuses,
            created_date=str(response.get('created_date') or '')[:64],
            last_updated_date=str(response.get('last_updated_date') or '')[:64],
            payments=payment_snapshots,
            refunds=refund_snapshots,
            chargebacks=chargeback_snapshots,
        )

    def fetch_order(self, provider_order_id):
        """Alias transitorio de C1; devuelve ahora el snapshot sanitizado."""
        return self.fetch_provider_order(provider_order_id)

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
