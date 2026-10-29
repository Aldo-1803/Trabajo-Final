from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import (
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    Turno,
)


class FinancialCasePaymentSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        source='monto',
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    method = serializers.CharField(source='metodo_pago', read_only=True)
    occurred_at = serializers.DateTimeField(source='fecha_pago', read_only=True)

    class Meta:
        model = Pago
        fields = (
            'public_id',
            'amount',
            'currency',
            'method',
            'purpose',
            'status',
            'occurred_at',
            'recorded_at',
            'reconciled_at',
            'terminal_reason',
            'provider_code',
            'provider_payment_id',
        )
        read_only_fields = fields


class FinancialCasePaymentIntentSerializer(serializers.ModelSerializer):
    slot_hold_public_id = serializers.UUIDField(
        source='slot_hold.public_id',
        read_only=True,
    )

    class Meta:
        model = PaymentIntent
        fields = (
            'public_id',
            'slot_hold_public_id',
            'mode',
            'total_amount_snapshot',
            'required_amount',
            'currency',
            'status',
            'expires_at',
            'created_at',
            'confirmed_turno_id',
        )
        read_only_fields = fields


class FinancialCaseTurnoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Turno
        fields = (
            'id',
            'fecha',
            'hora_inicio',
            'estado',
            'canal_origen',
        )
        read_only_fields = fields


class FinancialCaseOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenCompra
        fields = ('id', 'codigo', 'estado', 'total', 'creado_at')
        read_only_fields = fields


class FinancialCaseProviderAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderPaymentAttempt
        fields = (
            'public_id',
            'provider',
            'context',
            'channel',
            'status',
            'amount',
            'currency',
            'provider_order_id',
            'provider_status',
            'reconciliation_status',
            'last_reconciled_at',
            'created_at',
        )
        read_only_fields = fields


class FinancialCaseProviderEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderEvent
        fields = (
            'provider',
            'event_id',
            'provider_resource_id',
            'status',
            'received_at',
            'event_created_at',
            'reconciliation_status',
            'reconciled_at',
            'reconciliation_code',
        )
        read_only_fields = fields


class PaymentReconciliationCaseListSerializer(serializers.ModelSerializer):
    case_type_label = serializers.CharField(
        source='get_case_type_display',
        read_only=True,
    )
    context = serializers.SerializerMethodField()
    context_reference = serializers.SerializerMethodField()
    financial_summary = serializers.SerializerMethodField()
    provider_reference = serializers.SerializerMethodField()
    age_seconds = serializers.SerializerMethodField()

    class Meta:
        model = PaymentReconciliationCase
        fields = (
            'public_id',
            'case_type',
            'case_type_label',
            'status',
            'reason_code',
            'context',
            'context_reference',
            'financial_summary',
            'provider_reference',
            'created_at',
            'resolved_at',
            'age_seconds',
        )
        read_only_fields = fields

    @staticmethod
    def get_context(obj):
        return 'BOOKING' if obj.payment_intent_id is not None else 'ORDER'

    @staticmethod
    def get_context_reference(obj):
        if obj.payment_intent_id is not None:
            return {
                'payment_intent_public_id': str(obj.payment_intent.public_id),
                'payment_intent_status': obj.payment_intent.status,
                'slot_hold_public_id': str(obj.slot_hold.public_id),
                'turno_id': obj.turno_id,
                'turno_status': obj.turno.estado if obj.turno_id else None,
            }
        return {
            'order_id': obj.order_id,
            'order_code': obj.order.codigo,
            'order_status': obj.order.estado,
        }

    @staticmethod
    def get_financial_summary(obj):
        payments = list(obj.payments.all())
        total = sum((payment.monto for payment in payments), Decimal('0.00'))
        currencies = sorted({payment.currency for payment in payments})
        statuses = sorted({payment.status for payment in payments})
        return {
            'payment_count': len(payments),
            'total_amount': f'{total:.2f}',
            'currencies': currencies,
            'payment_statuses': statuses,
            'payment_public_ids': [str(payment.public_id) for payment in payments],
        }

    @staticmethod
    def get_provider_reference(obj):
        attempt = obj.provider_attempt
        event = obj.provider_event
        if attempt is None and event is None:
            return None
        return {
            'provider': (
                attempt.provider if attempt is not None else event.provider
            ),
            'attempt_public_id': (
                str(attempt.public_id) if attempt is not None else None
            ),
            'attempt_status': attempt.status if attempt is not None else None,
            'attempt_reconciliation_status': (
                attempt.reconciliation_status if attempt is not None else None
            ),
            'provider_order_id': (
                attempt.provider_order_id if attempt is not None else None
            ),
            'event_id': event.event_id if event is not None else None,
            'event_status': event.status if event is not None else None,
            'event_reconciliation_status': (
                event.reconciliation_status if event is not None else None
            ),
            'reconciliation_code': (
                event.reconciliation_code if event is not None else ''
            ),
        }

    def get_age_seconds(self, obj):
        now = self.context.get('now') or timezone.now()
        return max(0, int((now - obj.created_at).total_seconds()))


class PaymentReconciliationCaseDetailSerializer(
    PaymentReconciliationCaseListSerializer
):
    payments = FinancialCasePaymentSerializer(many=True, read_only=True)
    payment_intent = FinancialCasePaymentIntentSerializer(read_only=True)
    turno = FinancialCaseTurnoSerializer(read_only=True)
    order = FinancialCaseOrderSerializer(read_only=True)
    provider_attempt = FinancialCaseProviderAttemptSerializer(read_only=True)
    provider_event = FinancialCaseProviderEventSerializer(read_only=True)

    class Meta(PaymentReconciliationCaseListSerializer.Meta):
        fields = PaymentReconciliationCaseListSerializer.Meta.fields + (
            'payments',
            'payment_intent',
            'turno',
            'order',
            'provider_attempt',
            'provider_event',
        )
        read_only_fields = fields
