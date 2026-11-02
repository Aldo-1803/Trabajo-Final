from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from .financial_case_filters import PaymentReconciliationCaseFilter
from .financial_case_serializers import (
    FinancialResolutionDecisionCommandSerializer,
    FinancialResolutionDecisionInternalSerializer,
    FinancialResolutionRequestCommandSerializer,
    FinancialResolutionRequestInternalSerializer,
    FinancialResolutionRequestPublicSerializer,
    PaidOrderCancellationRequestCommandSerializer,
    PaymentReconciliationCaseDetailSerializer,
    PaymentReconciliationCaseListSerializer,
)
from .financial_resolution_services import (
    FinancialResolutionConflict,
    FinancialResolutionInvalid,
    FinancialResolutionNotFound,
    FinancialResolutionPermissionDenied,
    decide_financial_resolution,
    get_financial_resolution_request,
    request_paid_order_cancellation,
    submit_financial_resolution_request,
)
from .models import PaymentReconciliationCase
from .permissions import CanReconcileExternalPayment


class PaymentReconciliationCasePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PaymentReconciliationCaseViewSet(viewsets.ReadOnlyModelViewSet):
    """Lectura interna y comandos semánticos de resolución financiera."""

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
            'resolution_request__requested_by',
            'resolution_request__turno',
        )
        .prefetch_related(
            'payments',
            'resolution_request__decisions__decided_by',
            'resolution_request__events__actor',
        )
        .order_by('created_at', 'pk')
    )

    @staticmethod
    def _error_response(exc):
        if isinstance(exc, FinancialResolutionNotFound):
            response_status = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, FinancialResolutionPermissionDenied):
            response_status = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, FinancialResolutionConflict):
            response_status = status.HTTP_409_CONFLICT
        else:
            response_status = status.HTTP_400_BAD_REQUEST
        return Response(
            {
                'code': exc.code,
                'errors': {exc.field: [exc.detail]},
            },
            status=response_status,
        )

    @staticmethod
    def _idempotency_key(request):
        return request.headers.get('Idempotency-Key', '')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PaymentReconciliationCaseDetailSerializer
        return PaymentReconciliationCaseListSerializer

    def get_serializer_context(self):
        return {
            **super().get_serializer_context(),
            'now': timezone.now(),
        }

    @action(
        detail=True,
        methods=['post'],
        url_path='submit-resolution-request',
        permission_classes=[IsAuthenticated],
    )
    def submit_resolution_request(self, request, public_id=None):
        command = FinancialResolutionRequestCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        values = command.validated_data
        try:
            result = submit_financial_resolution_request(
                case_public_id=public_id,
                actor=request.user,
                requested_outcome=values['requested_outcome'],
                reason=values['reason'],
                amount=values.get('amount'),
                currency=values.get('currency', ''),
                evidence_reference=values.get('evidence_reference', ''),
                evidence_note=values.get('evidence_note', ''),
                idempotency_key=self._idempotency_key(request),
            )
        except (
            FinancialResolutionInvalid,
            FinancialResolutionConflict,
            FinancialResolutionNotFound,
            FinancialResolutionPermissionDenied,
        ) as exc:
            return self._error_response(exc)
        return Response(
            FinancialResolutionRequestPublicSerializer(
                result.resolution_request
            ).data,
            status=(
                status.HTTP_201_CREATED
                if result.created
                else status.HTTP_200_OK
            ),
        )

    @action(
        detail=True,
        methods=['get'],
        url_path='resolution-request',
        permission_classes=[IsAuthenticated],
    )
    def resolution_request(self, request, public_id=None):
        try:
            resolution_request, internal = get_financial_resolution_request(
                case_public_id=public_id,
                actor=request.user,
            )
        except (
            FinancialResolutionConflict,
            FinancialResolutionNotFound,
            FinancialResolutionPermissionDenied,
        ) as exc:
            return self._error_response(exc)
        serializer_class = (
            FinancialResolutionRequestInternalSerializer
            if internal
            else FinancialResolutionRequestPublicSerializer
        )
        return Response(serializer_class(resolution_request).data)

    @action(
        detail=True,
        methods=['post'],
        url_path='record-decision',
        permission_classes=[IsAuthenticated, CanReconcileExternalPayment],
    )
    def record_decision(self, request, public_id=None):
        command = FinancialResolutionDecisionCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        values = command.validated_data
        try:
            result = decide_financial_resolution(
                case_public_id=public_id,
                actor=request.user,
                action=values['action'],
                rationale=values['rationale'],
                authorized_amount=values.get('authorized_amount'),
                currency=values.get('currency', ''),
                policy_reference=values.get('policy_reference', ''),
                evidence_request=values.get('evidence_request', ''),
                idempotency_key=self._idempotency_key(request),
            )
        except (
            FinancialResolutionInvalid,
            FinancialResolutionConflict,
            FinancialResolutionNotFound,
            FinancialResolutionPermissionDenied,
        ) as exc:
            return self._error_response(exc)
        return Response(
            FinancialResolutionDecisionInternalSerializer(result.decision).data,
            status=(
                status.HTTP_201_CREATED
                if result.created
                else status.HTTP_200_OK
            ),
        )

    @action(
        detail=False,
        methods=['post'],
        url_path='request-paid-order-cancellation',
        permission_classes=[IsAuthenticated],
    )
    def request_paid_order_cancellation(self, request):
        command = PaidOrderCancellationRequestCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        values = command.validated_data
        try:
            result, order = request_paid_order_cancellation(
                order_id=values['order_id'],
                actor=request.user,
                reason=values['reason'],
                amount=values.get('amount'),
                currency=values.get('currency', ''),
                evidence_reference=values.get('evidence_reference', ''),
                evidence_note=values.get('evidence_note', ''),
                idempotency_key=self._idempotency_key(request),
            )
        except (
            FinancialResolutionInvalid,
            FinancialResolutionConflict,
            FinancialResolutionNotFound,
            FinancialResolutionPermissionDenied,
        ) as exc:
            return self._error_response(exc)
        return Response(
            {
                'order_id': order.pk,
                'order_status': order.estado,
                'business_effect': 'NO_CANCELLATION_NO_STOCK_RELEASE',
                'resolution_request': (
                    FinancialResolutionRequestPublicSerializer(
                        result.resolution_request
                    ).data
                ),
            },
            status=(
                status.HTTP_201_CREATED
                if result.created
                else status.HTTP_200_OK
            ),
        )
