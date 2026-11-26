from uuid import UUID

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .authentication import ClaimAwareTokenObtainPairSerializer
from .contact_normalization import try_normalize_argentine_phone
from .models import Cliente, WalkInClientOperation
from .roles import BusinessPermission
from .serializers import (
    WalkInClientCreateCommandSerializer,
    WebAccessClaimConfirmSerializer,
    WebAccessClaimRequestSerializer,
)
from .walkin_client_services import (
    WalkInClientConflict,
    WalkInClientError,
    WalkInClientNotFound,
    WalkInClientPermissionDenied,
    candidate_summary,
    create_walkin_client,
)
from .web_access_claim_services import (
    WebAccessClaimError,
    confirm_web_access_claim,
    request_web_access_claim,
)


class ClaimAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = ClaimAwareTokenObtainPairSerializer


class WalkInClientCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        actor = request.user
        if not actor.is_active or not actor.has_perm(BusinessPermission.CREATE_WALKIN_CLIENT):
            return self._error('PERMISSION_DENIED', 'No tiene permisos para consultar altas.', 403)
        try:
            operation_id = UUID(request.query_params.get('operation_id', ''))
        except ValueError:
            return self._error('INVALID_UUID', 'La referencia de alta es inválida.', 400)
        operation = WalkInClientOperation.objects.select_related('cliente__usuario').filter(
            actor=actor, operation_id=operation_id,
        ).first()
        if operation is None:
            return self._error('OPERATION_NOT_FOUND', 'No hay un alta disponible en este alcance.', 404)
        return Response({
            **candidate_summary(operation.cliente),
            'stage': 'CLIENT_READY',
            'created': operation.result_created,
            'operation_id': str(operation.operation_id),
        }, headers={'Cache-Control': 'no-store'})

    def post(self, request):
        serializer = WalkInClientCreateCommandSerializer(data=request.data)
        if not serializer.is_valid():
            return self._error(
                'INVALID_PAYLOAD',
                'El payload de alta rápida es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=serializer.errors,
            )
        try:
            command = dict(serializer.validated_data)
            command['reason'] = command.pop('motivo')
            result = create_walkin_client(
                actor=request.user,
                idempotency_key=request.headers.get('Idempotency-Key'),
                **command,
            )
        except WalkInClientPermissionDenied as exc:
            return self._domain_error(exc, status.HTTP_403_FORBIDDEN)
        except WalkInClientNotFound as exc:
            return self._domain_error(exc, status.HTTP_404_NOT_FOUND)
        except WalkInClientConflict as exc:
            return self._domain_error(exc, status.HTTP_409_CONFLICT)
        except WalkInClientError as exc:
            return self._domain_error(exc, status.HTTP_400_BAD_REQUEST)
        response_status = (
            status.HTTP_200_OK
            if result.recovered or not result.created
            else status.HTTP_201_CREATED
        )
        return Response({
            'created': result.created,
            'recovered': result.recovered,
            'cliente_id': result.cliente_id,
            'usuario_id': result.user_id,
            'display_name': result.display_name,
            'masked_email': result.masked_email,
            'masked_phone': result.masked_phone,
            'cliente_activo': result.client_active,
            'web_access_status': result.web_access_status,
            'operation_id': result.operation_id,
        }, status=response_status)

    @classmethod
    def _domain_error(cls, exc, status_code):
        return cls._error(
            exc.code,
            exc.detail,
            status_code,
            field=exc.field,
            candidates=exc.candidates,
        )

    @staticmethod
    def _error(code, detail, status_code, field=None, fields=None, candidates=()):
        error = {'code': code, 'detail': detail}
        if field:
            error['field'] = field
        if fields is not None:
            error['fields'] = fields
        if candidates:
            error['candidates'] = list(candidates)
        return Response({'error': error}, status=status_code)


class WalkInClientSelectorView(APIView):
    permission_classes = [IsAuthenticated]
    allowed_permissions = (
        BusinessPermission.CREATE_WALKIN_CLIENT,
        BusinessPermission.CREATE_TURNO_FOR_CLIENT,
        BusinessPermission.VIEW_CLIENTS,
    )

    def get(self, request):
        actor = request.user
        if not actor.is_active or not any(
            actor.has_perm(permission) for permission in self.allowed_permissions
        ):
            return Response({
                'error': {
                    'code': 'PERMISSION_DENIED',
                    'detail': 'No tiene permisos para seleccionar Clientes.',
                }
            }, status=status.HTTP_403_FORBIDDEN)
        query = request.query_params.get('q', '').strip()
        client_ref = request.query_params.get('cliente_id')
        if client_ref is not None:
            try:
                client_id = int(client_ref)
                if not 0 < client_id < 2**63:
                    raise ValueError
            except ValueError:
                return WalkInClientCreateView._error('INVALID_QUERY', 'La referencia de Cliente es inválida.', 400)
            client = Cliente.objects.select_related('usuario').filter(
                pk=client_id, activo=True, usuario__is_active=True,
            ).first()
            if client is None:
                return WalkInClientCreateView._error('CLIENT_NOT_FOUND', 'El Cliente no está disponible.', 404)
            return Response({'results': [candidate_summary(client)]}, headers={'Cache-Control': 'no-store'})
        if not 2 <= len(query) <= 100:
            return Response({
                'error': {
                    'code': 'INVALID_QUERY',
                    'detail': 'La búsqueda debe contener entre 2 y 100 caracteres.',
                    'field': 'q',
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 10))
        except (TypeError, ValueError):
            page = 0
            page_size = 0
        if page < 1 or not 1 <= page_size <= 20:
            return Response({
                'error': {
                    'code': 'INVALID_PAGINATION',
                    'detail': 'La paginación es inválida.',
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        filters = (
            Q(usuario__first_name__icontains=query)
            | Q(usuario__last_name__icontains=query)
            | Q(usuario__email__icontains=query)
        )
        normalized_phone = try_normalize_argentine_phone(query)
        if normalized_phone:
            filters |= Q(numero_normalizado=normalized_phone)
        queryset = (
            Cliente.objects.select_related('usuario')
            .filter(
                filters,
                activo=True,
                usuario__is_active=True,
            )
            .order_by('usuario__last_name', 'usuario__first_name', 'pk')
        )
        total = queryset.count()
        start = (page - 1) * page_size
        clients = queryset[start:start + page_size]
        return Response({
            'results': [candidate_summary(client) for client in clients],
            'page': page,
            'page_size': page_size,
            'total': total,
            'has_next': start + page_size < total,
        })


class WebAccessClaimRequestView(APIView):
    permission_classes = [AllowAny]
    generic_message = (
        'Si el email corresponde a un acceso pendiente, recibirás instrucciones.'
    )

    def post(self, request):
        serializer = WebAccessClaimRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': {
                    'code': 'INVALID_EMAIL',
                    'detail': 'Debe informar un email válido.',
                    'fields': serializer.errors,
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        request_web_access_claim(email=serializer.validated_data['email'])
        return Response({'mensaje': self.generic_message}, status=status.HTTP_200_OK)


class WebAccessClaimConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = WebAccessClaimConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': {
                    'code': 'INVALID_PAYLOAD',
                    'detail': 'Los datos de reclamo son inválidos.',
                    'fields': serializer.errors,
                }
            }, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        try:
            result = confirm_web_access_claim(
                token=data['token'],
                new_password=data['password'],
            )
        except WebAccessClaimError as exc:
            response_status = (
                status.HTTP_409_CONFLICT
                if exc.code == 'CLAIM_STATE_CONFLICT'
                else status.HTTP_400_BAD_REQUEST
            )
            error = {'code': exc.code, 'detail': exc.detail}
            if exc.field:
                error['field'] = exc.field
            return Response({'error': error}, status=response_status)
        return Response({
            'mensaje': 'Acceso web reclamado correctamente.',
            'web_access_status': result.web_access_status,
        }, status=status.HTTP_200_OK)
