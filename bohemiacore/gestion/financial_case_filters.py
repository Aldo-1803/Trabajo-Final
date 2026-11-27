import django_filters

from .models import PaymentReconciliationCase


class PaymentReconciliationCaseFilter(django_filters.FilterSet):
    type = django_filters.ChoiceFilter(
        field_name='case_type',
        choices=PaymentReconciliationCase.Type.choices,
    )
    context = django_filters.ChoiceFilter(
        method='filter_context',
        choices=(('BOOKING', 'Booking'), ('ORDER', 'Order')),
    )
    created_from = django_filters.IsoDateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
    )
    created_to = django_filters.IsoDateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
    )
    reason = django_filters.CharFilter(
        field_name='reason_code',
        lookup_expr='icontains',
    )

    class Meta:
        model = PaymentReconciliationCase
        fields = ('status', 'type', 'context', 'created_from', 'created_to', 'reason')

    @staticmethod
    def filter_context(queryset, _name, value):
        if value == 'BOOKING':
            return queryset.filter(payment_intent__isnull=False)
        if value == 'ORDER':
            return queryset.filter(order__isnull=False)
        return queryset
