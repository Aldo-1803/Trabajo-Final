from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .assisted_technical_booking_serializers import (
    AssistedConsentCommandSerializer,
    AssistedNextSlotQuerySerializer,
    AssistedPaymentIntentCreateSerializer,
    AssistedPaymentIntentPublicSerializer,
    AssistedPaymentOptionsQuerySerializer,
    AssistedSlotHoldCreateSerializer,
    AssistedSlotHoldPublicSerializer,
    AssistedSlotHoldReleaseSerializer,
    AssistedTechnicalRequestCreateSerializer,
    AssistedTechnicalRequestPublicSerializer,
)
from .assisted_payment_services import (
    assisted_payment_intent_for_actor,
    assisted_payment_options,
    prepare_assisted_payment_intent,
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
from .assisted_slot_hold_services import (
    assisted_slot_availability,
    assisted_slot_hold_for_actor,
    create_assisted_slot_hold,
    next_assisted_available_slot,
    release_assisted_slot_hold,
)
from .models import SolicitudTecnicaAsistidaOperacion
from .permissions import CanCreateTurnoForClient, IsActiveUser
from .slot_hold_clock import database_now


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

    @classmethod
    def _invalid_payload(cls, detail, errors):
        return cls._error(
            'INVALID_PAYLOAD',
            detail,
            status.HTTP_400_BAD_REQUEST,
            fields=errors,
        )

    @classmethod
    def _execute_domain_command(cls, command):
        try:
            return command(), None
        except AssistedTechnicalBookingPermissionDenied as exc:
            return None, cls._domain_error(exc, status.HTTP_403_FORBIDDEN)
        except AssistedTechnicalBookingNotFound as exc:
            return None, cls._domain_error(exc, status.HTTP_404_NOT_FOUND)
        except AssistedTechnicalBookingConflict as exc:
            return None, cls._domain_error(exc, status.HTTP_409_CONFLICT)
        except AssistedTechnicalBookingError as exc:
            return None, cls._domain_error(exc, status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _serialize_hold(hold, *, operation_id=None):
        return dict(AssistedSlotHoldPublicSerializer(
            hold,
            context={
                'database_now': database_now(),
                'operation_id': operation_id,
            },
        ).data)

    @staticmethod
    def _serialize_intent(intent, *, operation_id=None):
        return dict(AssistedPaymentIntentPublicSerializer(
            intent,
            context={
                'database_now': database_now(),
                'operation_id': operation_id,
            },
        ).data)

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

    @action(detail=True, methods=['get'], url_path='disponibilidad')
    def disponibilidad(self, request, pk=None):
        result, error = self._execute_domain_command(lambda: (
            assisted_slot_availability(
                solicitud_id=pk,
                actor=request.user,
            )
        ))
        return error or Response(result)

    @action(
        detail=True,
        methods=['get'],
        url_path='proximo-intervalo',
        url_name='proximo-intervalo',
    )
    def proximo_intervalo(self, request, pk=None):
        serializer = AssistedNextSlotQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return self._invalid_payload(
                'La búsqueda de próximo intervalo es inválida.',
                serializer.errors,
            )
        result, error = self._execute_domain_command(lambda: (
            next_assisted_available_slot(
                solicitud_id=pk,
                actor=request.user,
                **serializer.validated_data,
            )
        ))
        return error or Response(result)

    @action(detail=True, methods=['get', 'post'], url_path='hold')
    def hold(self, request, pk=None):
        if request.method == 'GET':
            result, error = self._execute_domain_command(lambda: (
                assisted_slot_hold_for_actor(
                    solicitud_id=pk,
                    actor=request.user,
                )
            ))
            if error:
                return error
            operation = result.operaciones_asistidas.filter(
                actor=request.user,
                command=SolicitudTecnicaAsistidaOperacion.Command.HOLD,
            ).order_by('-created_at', '-pk').first()
            return Response(self._serialize_hold(
                result,
                operation_id=(
                    str(operation.operation_id) if operation else None
                ),
            ))

        serializer = AssistedSlotHoldCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self._invalid_payload(
                'El payload de hold asistido es inválido.',
                serializer.errors,
            )
        result, error = self._execute_domain_command(lambda: (
            create_assisted_slot_hold(
                solicitud_id=pk,
                actor=request.user,
                idempotency_key=request.headers.get('Idempotency-Key'),
                **serializer.validated_data,
            )
        ))
        if error:
            return error
        data = self._serialize_hold(
            result.hold,
            operation_id=result.operation_id,
        )
        data['recovered'] = result.recovered
        return Response(
            data,
            status=(
                status.HTTP_200_OK
                if result.recovered
                else status.HTTP_201_CREATED
            ),
        )

    @action(
        detail=True,
        methods=['post'],
        url_path='hold/liberar',
        url_name='liberar-hold',
    )
    def liberar_hold(self, request, pk=None):
        serializer = AssistedSlotHoldReleaseSerializer(data=request.data)
        if not serializer.is_valid():
            return self._invalid_payload(
                'El payload de liberación asistida es inválido.',
                serializer.errors,
            )
        result, error = self._execute_domain_command(lambda: (
            release_assisted_slot_hold(
                solicitud_id=pk,
                actor=request.user,
                idempotency_key=request.headers.get('Idempotency-Key'),
                **serializer.validated_data,
            )
        ))
        if error:
            return error
        data = self._serialize_hold(
            result.hold,
            operation_id=result.operation_id,
        )
        data.update({
            'recovered': result.recovered,
            'changed': result.changed,
            'expiration_materialized': result.expiration_materialized,
        })
        return Response(data)

    @action(
        detail=True,
        methods=['get'],
        url_path='pago/opciones',
        url_name='opciones-pago',
    )
    def opciones_pago(self, request, pk=None):
        serializer = AssistedPaymentOptionsQuerySerializer(
            data=request.query_params
        )
        if not serializer.is_valid():
            return self._invalid_payload(
                'La consulta financiera asistida es inválida.',
                serializer.errors,
            )
        result, error = self._execute_domain_command(lambda: (
            assisted_payment_options(
                solicitud_id=pk,
                actor=request.user,
                **serializer.validated_data,
            )
        ))
        if error:
            return error
        return Response({
            'slot_hold_public_id': str(result.hold.public_id),
            'policy_version': result.policy_version,
            'total_amount': str(result.total_amount),
            'currency': result.currency,
            'expires_at': result.expires_at.isoformat(),
            'modes': [
                {
                    'mode': option.mode,
                    'required_amount': str(option.required_amount),
                }
                for option in result.modes
            ],
            'existing_intent': (
                self._serialize_intent(result.existing_intent)
                if result.existing_intent is not None
                else None
            ),
        })

    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='pago/intent',
        url_name='intent-pago',
    )
    def intent_pago(self, request, pk=None):
        if request.method == 'GET':
            result, error = self._execute_domain_command(lambda: (
                assisted_payment_intent_for_actor(
                    solicitud_id=pk,
                    actor=request.user,
                )
            ))
            if error:
                return error
            intent, operation_id = result
            return Response(self._serialize_intent(
                intent,
                operation_id=operation_id,
            ))

        serializer = AssistedPaymentIntentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self._invalid_payload(
                'El payload de Intent asistido es inválido.',
                serializer.errors,
            )
        result, error = self._execute_domain_command(lambda: (
            prepare_assisted_payment_intent(
                solicitud_id=pk,
                actor=request.user,
                idempotency_key=request.headers.get('Idempotency-Key'),
                **serializer.validated_data,
            )
        ))
        if error:
            return error
        data = self._serialize_intent(
            result.intent,
            operation_id=result.operation_id,
        )
        data['recovered'] = result.recovered
        return Response(
            data,
            status=(
                status.HTTP_200_OK
                if result.recovered
                else status.HTTP_201_CREATED
            ),
        )
