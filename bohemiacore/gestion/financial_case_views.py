from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from .financial_case_filters import PaymentReconciliationCaseFilter
from .financial_case_serializers import (
    PaymentReconciliationCaseDetailSerializer,
    PaymentReconciliationCaseListSerializer,
)
from .models import PaymentReconciliationCase
from .permissions import CanReconcileExternalPayment


class PaymentReconciliationCasePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PaymentReconciliationCaseViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta interna de incidencias; no expone operaciones de escritura."""

    permission_classes = [IsAuthenticated, CanReconcileExternalPayment]
    pagination_class = PaymentReconciliationCasePagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = PaymentReconciliationCaseFilter
    ordering_fields = ('created_at', 'resolved_at')
    ordering = ('created_at', 'pk')
    lookup_field = 'public_id'
    lookup_value_regex = '[0-9a-fA-F-]{36}'

    queryset = (
        PaymentReconciliationCase.objects.select_related(
            'payment_intent__slot_hold',
            'slot_hold',
            'turno',
            'order',
            'provider_attempt',
            'provider_event',
        )
        .prefetch_related('payments')
        .order_by('created_at', 'pk')
    )

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PaymentReconciliationCaseDetailSerializer
        return PaymentReconciliationCaseListSerializer

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            'now': timezone.now(),
        }
