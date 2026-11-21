from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .assisted_technical_booking_serializers import (
    AssistedConsentCommandSerializer,
    AssistedTechnicalRequestCreateSerializer,
    AssistedTechnicalRequestPublicSerializer,
)
from .assisted_technical_booking_services import (
    AssistedTechnicalBookingConflict,
    AssistedTechnicalBookingError,
    AssistedTechnicalBookingNotFound,
    AssistedTechnicalBookingPermissionDenied,
    assisted_request_for_actor,
    create_assisted_technical_request,
    next_assisted_action,
    register_assisted_warning_consent,
)
from .permissions import CanCreateTurnoForClient, IsActiveUser


class AssistedTechnicalRequestViewSet(viewsets.GenericViewSet):
    permission_classes = [
        IsAuthenticated,
        IsActiveUser,
        CanCreateTurnoForClient,
    ]

    def handle_exception(self, exc):
        if isinstance(exc, (
            exceptions.NotAuthenticated,
            exceptions.AuthenticationFailed,
        )):
            return self._error(
                'AUTHENTICATION_REQUIRED',
                'Se requiere una sesión válida.',
                status.HTTP_401_UNAUTHORIZED,
            )
        if isinstance(exc, exceptions.PermissionDenied):
            return self._error(
                'PERMISSION_DENIED',
                'No tiene permisos para registrar solicitudes asistidas.',
                status.HTTP_403_FORBIDDEN,
            )
        return super().handle_exception(exc)

    @staticmethod
    def _error(code, detail, status_code, *, field=None, fields=None):
        payload = {'code': code, 'detail': detail}
        if field:
            payload['field'] = field
        if fields is not None:
            payload['fields'] = fields
        return Response({'error': payload}, status=status_code)

    @classmethod
    def _domain_error(cls, exc, status_code):
        return cls._error(
            exc.code,
            exc.detail,
            status_code,
            field=exc.field,
        )

    def _get_scoped_request(self, pk):
        return assisted_request_for_actor(
            solicitud_id=pk,
            actor=self.request.user,
        )

    def create(self, request):
        serializer = AssistedTechnicalRequestCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self._error(
                'INVALID_PAYLOAD',
                'El payload de solicitud asistida es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=serializer.errors,
            )
        command = dict(serializer.validated_data)
        try:
            result = create_assisted_technical_request(
                actor=request.user,
                idempotency_key=request.headers.get('Idempotency-Key'),
                **command,
            )
        except AssistedTechnicalBookingPermissionDenied as exc:
            return self._domain_error(exc, status.HTTP_403_FORBIDDEN)
        except AssistedTechnicalBookingNotFound as exc:
            return self._domain_error(exc, status.HTTP_404_NOT_FOUND)
        except AssistedTechnicalBookingConflict as exc:
            return self._domain_error(exc, status.HTTP_409_CONFLICT)
        except AssistedTechnicalBookingError as exc:
            return self._domain_error(exc, status.HTTP_400_BAD_REQUEST)
        data = dict(AssistedTechnicalRequestPublicSerializer(
            result.solicitud
        ).data)
        data['recovered'] = result.recovered
        return Response(
            data,
            status=(
                status.HTTP_200_OK
                if result.recovered
                else status.HTTP_201_CREATED
            ),
        )

    def retrieve(self, request, pk=None):
        try:
            solicitud = self._get_scoped_request(pk)
        except AssistedTechnicalBookingNotFound as exc:
            return self._domain_error(exc, status.HTTP_404_NOT_FOUND)
        return Response(AssistedTechnicalRequestPublicSerializer(solicitud).data)

    @action(detail=True, methods=['post'], url_path='consentimiento')
    def consentimiento(self, request, pk=None):
        serializer = AssistedConsentCommandSerializer(data=request.data)
        if not serializer.is_valid():
            return self._error(
                'INVALID_PAYLOAD',
                'El payload de consentimiento asistido es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=serializer.errors,
            )
        try:
            result = register_assisted_warning_consent(
                solicitud_id=pk,
                actor=request.user,
                idempotency_key=request.headers.get('Idempotency-Key'),
                **serializer.validated_data,
            )
        except AssistedTechnicalBookingPermissionDenied as exc:
            return self._domain_error(exc, status.HTTP_403_FORBIDDEN)
        except AssistedTechnicalBookingNotFound as exc:
            return self._domain_error(exc, status.HTTP_404_NOT_FOUND)
        except AssistedTechnicalBookingConflict as exc:
            return self._domain_error(exc, status.HTTP_409_CONFLICT)
        except AssistedTechnicalBookingError as exc:
            return self._domain_error(exc, status.HTTP_400_BAD_REQUEST)
        result.solicitud._prefetched_objects_cache = {}
        data = dict(AssistedTechnicalRequestPublicSerializer(
            result.solicitud
        ).data)
        data['recovered'] = result.recovered
        data['consent_operation_id'] = result.operation_id
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='accion-siguiente')
    def accion_siguiente(self, request, pk=None):
        try:
            solicitud = self._get_scoped_request(pk)
        except AssistedTechnicalBookingNotFound as exc:
            return self._domain_error(exc, status.HTTP_404_NOT_FOUND)
        return Response({
            'solicitud_id': solicitud.pk,
            'estado': solicitud.estado,
            'outcome_publico': (
                solicitud.evaluacion_vigente.outcome
                if solicitud.evaluacion_vigente else None
            ),
            'siguiente_accion': next_assisted_action(solicitud),
        })
