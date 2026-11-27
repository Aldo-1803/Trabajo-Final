from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import (
    PAYMENT_CURRENCY_CHOICES,
    FinancialAdjustment,
    FinancialCaseClosure,
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
    FinancialResolutionDecision,
    FinancialResolutionEvent,
    FinancialResolutionRequest,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    Turno,
)
from .financial_adjustment_services import (
    project_payment_finances,
    project_payments_by_currency,
)


class FinancialAdjustmentSerializer(serializers.ModelSerializer):
    provider_event_id = serializers.IntegerField(read_only=True)
    refund_operation_public_id = serializers.UUIDField(
        source='refund_operation.public_id',
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = FinancialAdjustment
        fields = (
            'public_id',
            'adjustment_type',
            'effect',
            'amount',
            'currency',
            'provider',
            'external_adjustment_id',
            'provider_status',
            'provider_event_id',
            'refund_operation_public_id',
            'effective_at',
            'evidence',
            'created_at',
        )
        read_only_fields = fields


class FinancialCasePaymentSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        source='monto',
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    method = serializers.CharField(source='metodo_pago', read_only=True)
    occurred_at = serializers.DateTimeField(source='fecha_pago', read_only=True)
    financial_projection = serializers.SerializerMethodField()
    adjustments = FinancialAdjustmentSerializer(
        source='financial_adjustments',
        many=True,
        read_only=True,
    )

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
            'financial_projection',
            'adjustments',
        )
        read_only_fields = fields

    @staticmethod
    def get_financial_projection(obj):
        projection = project_payment_finances(obj)
        return {
            'currency': projection.currency,
            'gross_reconciled': f'{projection.gross_reconciled:.2f}',
            'confirmed_adjustments': f'{projection.confirmed_adjustments:.2f}',
            'net_reconciled': f'{projection.net_reconciled:.2f}',
            'refund_pending': f'{projection.refund_pending:.2f}',
            'refunds_confirmed': f'{projection.refunds_confirmed:.2f}',
            'chargebacks_confirmed': (
                f'{projection.chargebacks_confirmed:.2f}'
            ),
        }


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


class FinancialResolutionRequestCommandSerializer(serializers.Serializer):
    requested_outcome = serializers.ChoiceField(
        choices=FinancialResolutionRequest.RequestedOutcome.choices,
    )
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal('0.01'),
    )
    currency = serializers.ChoiceField(
        choices=PAYMENT_CURRENCY_CHOICES,
        required=False,
        allow_blank=True,
        default='',
    )
    evidence_reference = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        default='',
    )
    evidence_note = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        default='',
    )

    def validate(self, attrs):
        allowed = {
            'requested_outcome',
            'reason',
            'amount',
            'currency',
            'evidence_reference',
            'evidence_note',
        }
        unexpected = set(self.initial_data) - allowed
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class PaidOrderCancellationRequestCommandSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal('0.01'),
    )
    currency = serializers.ChoiceField(
        choices=PAYMENT_CURRENCY_CHOICES,
        required=False,
        allow_blank=True,
        default='',
    )
    evidence_reference = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        default='',
    )
    evidence_note = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        default='',
    )

    def validate(self, attrs):
        allowed = {
            'order_id',
            'reason',
            'amount',
            'currency',
            'evidence_reference',
            'evidence_note',
        }
        unexpected = set(self.initial_data) - allowed
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class FinancialResolutionDecisionCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=FinancialResolutionDecision.Action.choices,
    )
    rationale = serializers.CharField(max_length=2000, trim_whitespace=True)
    evidence_request = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        default='',
    )
    authorized_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal('0.01'),
    )
    currency = serializers.ChoiceField(
        choices=PAYMENT_CURRENCY_CHOICES,
        required=False,
        allow_blank=True,
        default='',
    )
    policy_reference = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        default='',
    )

    def validate(self, attrs):
        allowed = {
            'action',
            'rationale',
            'evidence_request',
            'authorized_amount',
            'currency',
            'policy_reference',
        }
        unexpected = set(self.initial_data) - allowed
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class FinancialResolutionDecisionInternalSerializer(serializers.ModelSerializer):
    decided_by = serializers.EmailField(source='decided_by.email', read_only=True)

    class Meta:
        model = FinancialResolutionDecision
        fields = (
            'public_id',
            'sequence',
            'action',
            'rationale',
            'evidence_request',
            'authorized_amount',
            'currency',
            'policy_reference',
            'decided_by',
            'decided_at',
        )
        read_only_fields = fields


class FinancialRefundExecutionCommandSerializer(serializers.Serializer):
    payment_public_id = serializers.UUIDField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {'payment_public_id'}
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class FinancialCaseClosureCommandSerializer(serializers.Serializer):
    rationale = serializers.CharField(max_length=2000, trim_whitespace=True)
    result = serializers.ChoiceField(choices=FinancialCaseClosure.Result.choices)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {'rationale', 'result'}
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class FinancialCaseClosureSerializer(serializers.ModelSerializer):
    closed_by = serializers.EmailField(source='closed_by.email', read_only=True)
    decision_public_id = serializers.UUIDField(
        source='decision.public_id', read_only=True
    )

    class Meta:
        model = FinancialCaseClosure
        fields = (
            'public_id',
            'decision_public_id',
            'closed_by',
            'rationale',
            'result',
            'commercial_effect',
            'evidence',
            'closed_at',
        )
        read_only_fields = fields


class FinancialRefundOperationEventSerializer(serializers.ModelSerializer):
    actor = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = FinancialRefundOperationEvent
        fields = ('public_id', 'event_type', 'actor', 'payload', 'created_at')
        read_only_fields = fields


class FinancialRefundOperationSerializer(serializers.ModelSerializer):
    decision_public_id = serializers.UUIDField(
        source='decision.public_id',
        read_only=True,
    )
    payment_public_id = serializers.UUIDField(
        source='payment.public_id',
        read_only=True,
    )
    created_by = serializers.EmailField(source='created_by.email', read_only=True)
    events = FinancialRefundOperationEventSerializer(many=True, read_only=True)
    financial_confirmation = serializers.SerializerMethodField()

    class Meta:
        model = FinancialRefundOperation
        fields = (
            'public_id',
            'decision_public_id',
            'payment_public_id',
            'amount',
            'currency',
            'payment_method',
            'provider',
            'status',
            'provider_order_id',
            'provider_transaction_id',
            'external_refund_id',
            'provider_status',
            'provider_status_detail',
            'latest_evidence',
            'error_code',
            'error_detail',
            'provider_call_count',
            'created_by',
            'created_at',
            'submission_started_at',
            'response_received_at',
            'last_recovery_at',
            'confirmed_at',
            'financial_confirmation',
            'events',
        )
        read_only_fields = fields

    @staticmethod
    def get_financial_confirmation(obj):
        return obj.status == FinancialRefundOperation.Status.CONFIRMED


class FinancialResolutionEventInternalSerializer(serializers.ModelSerializer):
    actor = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = FinancialResolutionEvent
        fields = (
            'public_id',
            'event_type',
            'actor',
            'payload',
            'created_at',
        )
        read_only_fields = fields


class FinancialResolutionRequestInternalSerializer(serializers.ModelSerializer):
    requested_by = serializers.EmailField(
        source='requested_by.email',
        read_only=True,
    )
    decisions = FinancialResolutionDecisionInternalSerializer(
        many=True,
        read_only=True,
    )
    events = FinancialResolutionEventInternalSerializer(many=True, read_only=True)

    class Meta:
        model = FinancialResolutionRequest
        fields = (
            'public_id',
            'context',
            'turno_id',
            'requested_outcome',
            'reason',
            'amount',
            'currency',
            'evidence_reference',
            'evidence_note',
            'status',
            'requested_by',
            'created_at',
            'status_updated_at',
            'decisions',
            'events',
        )
        read_only_fields = fields


class FinancialResolutionRequestPublicSerializer(serializers.ModelSerializer):
    latest_decision = serializers.SerializerMethodField()

    class Meta:
        model = FinancialResolutionRequest
        fields = (
            'public_id',
            'context',
            'turno_id',
            'requested_outcome',
            'reason',
            'amount',
            'currency',
            'evidence_reference',
            'evidence_note',
            'status',
            'created_at',
            'status_updated_at',
            'latest_decision',
        )
        read_only_fields = fields

    @staticmethod
    def get_latest_decision(obj):
        decisions = list(obj.decisions.all())
        if not decisions:
            return None
        decision = max(decisions, key=lambda item: (item.sequence, item.pk))
        return {
            'action': decision.action,
            'evidence_request': decision.evidence_request,
            'decided_at': decision.decided_at,
        }


class PaymentReconciliationCaseListSerializer(serializers.ModelSerializer):
    case_type_label = serializers.CharField(
        source='get_case_type_display',
        read_only=True,
    )
    context = serializers.SerializerMethodField()
    context_reference = serializers.SerializerMethodField()
    financial_summary = serializers.SerializerMethodField()
    provider_reference = serializers.SerializerMethodField()
    customer_reference = serializers.SerializerMethodField()
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
            'customer_reference',
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
    def get_customer_reference(obj):
        customer = (
            obj.slot_hold.cliente
            if obj.payment_intent_id is not None
            else obj.order.cliente
        )
        display_name = customer.usuario.get_full_name().strip()
        return {
            'client_id': customer.pk,
            'display_name': display_name or f'Cliente #{customer.pk}',
        }

    @staticmethod
    def get_financial_summary(obj):
        payments = list(obj.payments.all())
        total = sum((payment.monto for payment in payments), Decimal('0.00'))
        currencies = sorted({payment.currency for payment in payments})
        statuses = sorted({payment.status for payment in payments})
        grouped = project_payments_by_currency(payments)
        by_currency = {
            currency: {
                field: f'{amount:.2f}' for field, amount in values.items()
            }
            for currency, values in sorted(grouped.items())
        }
        canonical = next(iter(by_currency.values()), None) if len(by_currency) == 1 else None
        return {
            'payment_count': len(payments),
            'total_amount': f'{total:.2f}',
            'currencies': currencies,
            'payment_statuses': statuses,
            'payment_public_ids': [str(payment.public_id) for payment in payments],
            'gross_reconciled': (
                canonical['gross_reconciled'] if canonical is not None else None
            ),
            'confirmed_adjustments': (
                canonical['confirmed_adjustments'] if canonical is not None else None
            ),
            'net_reconciled': (
                canonical['net_reconciled'] if canonical is not None else None
            ),
            'refund_pending': (
                canonical['refund_pending'] if canonical is not None else None
            ),
            'by_currency': by_currency,
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
    resolution_request = FinancialResolutionRequestInternalSerializer(
        read_only=True,
    )
    closure = FinancialCaseClosureSerializer(read_only=True)

    class Meta(PaymentReconciliationCaseListSerializer.Meta):
        fields = PaymentReconciliationCaseListSerializer.Meta.fields + (
            'payments',
            'payment_intent',
            'turno',
            'order',
            'provider_attempt',
            'provider_event',
            'resolution_request',
            'closure',
        )
        read_only_fields = fields
