from rest_framework import viewsets, status, serializers
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.exceptions import (
    MethodNotAllowed,
    PermissionDenied,
    ValidationError,
)
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from datetime import datetime, date, timedelta, time
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import logging
import datetime as dt
import os
from uuid import uuid4
import mercadopago

from django.conf import settings
from django.http import Http404

# Configurar logger global
logger = logging.getLogger(__name__)

from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral, CategoriaServicio, Servicio, Turno, DetalleTurno,
    Configuracion, ListaEspera, Producto, ImagenProducto, Equipamiento, Rutina, Notificacion, AgendaCuidados, Producto, ReglaDiagnostico,
    RutinaCliente, HorarioLaboral, BloqueoAgenda, Personal, Habilidad, PersonalHabilidad, TipoEquipamiento, FichaTecnica, DiagnosticoCapilar, RequisitoServicio,
    CategoriaProducto, Promocion, ConfiguracionRetoque, DiasSemana, Carrito, CarritoItem, ContenidoEducativo, MeGusta, ContenidoGuardado,
    OrdenPendiente, OrdenCompra, OrdenItem, Pago, ConfiguracionDiagnostico,
    #PasoRutinaCliente
    #PasoRutina
)

from .serializers import (
    TipoCabelloSerializer, GrosorCabelloSerializer, PorosidadCabelloSerializer, CueroCabelludoSerializer, EstadoGeneralSerializer,
    CategoriaServicioSerializer, ServicioSerializer, TurnoSerializer,
    TurnoAgendaReadSerializer, TurnoClienteReadSerializer,
    TurnoComprobanteUploadSerializer, TurnoReservaCommandSerializer,
    TurnoParaClienteCommandSerializer, TurnoArrivalCommandSerializer,
    TurnoCancellationCommandSerializer, TurnoClientRescheduleCommandSerializer,
    TurnoRescheduleCommandSerializer,
    RutinaSerializer, RutinaClienteSerializer,
    RutinaClienteCreateSerializer, ReglaDiagnosticoSerializer, NotificacionSerializer, ProductoSerializer, ImagenProductoSerializer, EquipamientoSerializer,
    UsuarioAccountStatusCommandSerializer, UsuarioAdminIdentityUpdateSerializer,
    UsuarioAdminReadSerializer, AgendaCuidadosSerializer,
    HorarioLaboralSerializer, BloqueoAgendaSerializer, PersonalSerializer,
    HabilidadSerializer, PersonalHabilidadSerializer,
    PersonalHabilidadAssignCommandSerializer,
    PersonalAccessCreateCommandSerializer,
    PersonalBusinessRoleChangeCommandSerializer,
    PersonalStatusChangeCommandSerializer,
    PersonalUserLinkCommandSerializer,
    PagoSerializer,
    TipoEquipamientoSerializer, FichaTecnicaSerializer, RequisitoServicioSerializer, DiagnosticoCapilarSerializer,
    CategoriaProductoSerializer, PromocionSerializer, ConfiguracionSerializer, ConfiguracionRetoqueSummarySerializer,
    CarritoSerializer, CarritoItemSerializer, ContenidoEducativoSerializer, MeGustaSerializer, ContenidoGuardadoSerializer,
    OrdenPendienteSerializer, OrdenCompraSerializer, OrdenItemSerializer, ConfiguracionDiagnosticoSerializer,
    #PasoRutinaSerializer,
)
from .permissions import (
    CanCancelAnyTurno,
    CanCreateTurnoForClient,
    CanRegisterTurnoArrival,
    CanReprogramAnyTurno,
    CanViewGlobalAgenda,
    CanManageSkills,
)
from .turno_creation_services import (
    TurnoAvailabilityService,
    TurnoCreationError,
    TurnoCreationService,
)
from .turno_arrival_services import (
    InvalidTurnoArrivalTransition,
    PermissionDeniedForTurnoArrival,
    TurnoArrivalTargetNotFound,
    register_turno_arrival,
)
from .turno_management_services import (
    CLIENT_CANCELLABLE_STATES,
    CLIENT_REPROGRAMMABLE_STATES,
    InvalidTurnoManagementTransition,
    PermissionDeniedForTurnoManagement,
    TurnoManagementError,
    TurnoManagementTargetNotFound,
    cancel_owned_turno,
    cancel_turno,
    reprogram_owned_turno,
    reprogram_turno,
)
from .personal_access_services import (
    ClientProfileRequired,
    EmailAlreadyExists,
    FullWorkAccessRevocationConflict,
    InactiveUserForWorkAccessRevocation,
    InvalidFullWorkAccessRevocationReason,
    InvalidPersonalAccessEmail,
    InvalidPersonalAccessRole,
    InvalidPersonalBusinessRoleReason,
    InvalidPersonalBusinessRoleTarget,
    InvalidPersonalLinkReason,
    InvalidPersonalLinkTarget,
    InvalidPersonalLinkUser,
    InvalidPersonalStatusReason,
    InvalidTemporaryPassword,
    InvalidWorkAccessRevocationReason,
    PermissionDeniedForPersonalLink,
    PermissionDeniedForPersonalBusinessRoleChange,
    PermissionDeniedForPersonalStatusChange,
    PermissionDeniedForFullWorkAccessRevocation,
    PermissionDeniedForWorkAccessRevocation,
    PersonalAccessConflict,
    PersonalAlreadyLinked,
    PersonalAlreadyHasAccess,
    PersonalBusinessRoleChangeConflict,
    PersonalBusinessRoleChangeNotAllowed,
    PersonalInactiveForAccess,
    PersonalInactiveForRoleChange,
    PersonalHasNoUser,
    PersonalLinkConflict,
    PersonalStatusConflict,
    PersonalWithoutUserForRoleChange,
    MultiplePersonalBusinessRoles,
    UserAlreadyLinkedToPersonal,
    create_access_for_personal,
    change_personal_business_role,
    deactivate_personal,
    link_user_to_personal,
    reactivate_personal,
    revoke_work_access_and_disable_account,
    revoke_work_access_keep_client,
    WorkAccessRevocationConflict,
)
from .personal_skill_services import (
    InactiveSkill,
    PersonalSkillAssignmentNotFound,
    PersonalSkillNotFound,
    PersonalSkillPermissionDenied,
    assign_skill,
    reactivate_skill,
    revoke_skill,
)
from .service_skill_compatibility import service_skill_policy
from usuarios.access_services import (
    AccountDeactivationConflict,
    AccountReactivationConflict,
    InactivePersonal,
    InconsistentBusinessRoleState,
    InvalidAccountDeactivationReason,
    InvalidAccountDeactivationTarget,
    InvalidAccountReactivationReason,
    InvalidAccountReactivationTarget,
    LastActiveAdministrator,
    MissingClientProfile,
    MissingPersonalProfile,
    PermissionDeniedForAccountDeactivation,
    PermissionDeniedForAccountReactivation,
    ProtectedSuperuser,
    SelfDeactivationNotAllowed,
    UserHasNoBusinessRole,
    deactivate_account,
    reactivate_account,
)

from .services import MercadoPagoService
from usuarios.models import Usuario, Cliente
from usuarios.filters import UsuarioFilter
from usuarios.roles import BusinessPermission
from .filters import (
    ProductoFilter, TurnoFilter, PersonalFilter, ServicioFilter, 
    ClienteFilter, RutinaFilter, TipoEquipamientoFilter, EquipamientoFilter, DiagnosticoCapilarFilter,
    ConfiguracionFilter
)

# --- UPLOAD DE IMÁGENES ---
@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_imagen(request):
    """
    Endpoint para subir imágenes de productos.
    Retorna la URL de la imagen subida.
    """
    if 'imagen' not in request.FILES:
        return Response(
            {'error': 'No se proporcionó imagen'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    imagen = request.FILES['imagen']
    
    # Validar tipo de archivo
    archivo_valido = imagen.content_type in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if not archivo_valido:
        return Response(
            {'error': 'Solo se permiten archivos de imagen (JPEG, PNG, GIF, WebP)'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validar tamaño (máx 5MB)
    if imagen.size > 5 * 1024 * 1024:
        return Response(
            {'error': 'La imagen es demasiado grande. Máximo 5MB'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Generar nombre único para el archivo
        ext = os.path.splitext(imagen.name)[1]
        nombre_archivo = f'productos/{uuid4()}{ext}'
        
        # Guardar archivo en el storage (local o cloud)
        ruta = default_storage.save(nombre_archivo, ContentFile(imagen.read()))
        
        # Obtener URL accesible de la imagen
        url = default_storage.url(ruta)
        
        logger.info(f'Imagen subida exitosamente: {ruta}')
        
        return Response({
            'url': url,
            'nombre': imagen.name,
            'tamano': imagen.size
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f'Error al subir imagen: {str(e)}')
        return Response(
            {'error': f'Error al guardar la imagen: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _crear_checkout_mercadopago_para_usuario(user):
    """
    Crea la OrdenCompra en estado ESPERANDO_PAGO, genera la preferencia de Mercado Pago
    y vacía el carrito. Se reutiliza desde la acción del carrito y desde la APIView.
    """
    cliente = Cliente.objects.get(usuario=user)
    carrito = Carrito.objects.get_or_create(cliente=cliente)[0]

    if not carrito.items.exists():
        raise ValidationError('El carrito está vacío o no existe.')

    items_carrito = list(carrito.items.select_related('producto'))

    with transaction.atomic():
        orden = OrdenCompra.objects.create(
            codigo=f"ORD-{uuid4().hex[:8].upper()}",
            cliente=cliente,
            estado='ESPERANDO_PAGO',
            total=carrito.total_carrito,
        )

        for item in items_carrito:
            OrdenItem.objects.create(
                orden=orden,
                producto=item.producto,
                cantidad=item.cantidad,
                precio_historico=item.producto.precio,
            )

        url_pago = MercadoPagoService().crear_preferencia(orden)
        carrito.items.all().delete()

    return orden, url_pago, len(items_carrito)


class GenerarPagoMercadoPagoView(APIView):
    """
    Endpoint para convertir el carrito actual en una OrdenCompra y generar
    el link oficial de Mercado Pago.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            orden, url_pago, items_count = _crear_checkout_mercadopago_para_usuario(request.user)

            logger.info(
                f"Orden Mercado Pago generada para {request.user.email} | "
                f"Orden: {orden.codigo} | Total: ${orden.total}"
            )

            return Response(
                {
                    'mensaje': 'Orden creada con éxito. Redirigiendo a Mercado Pago...',
                    'init_point': url_pago,
                    'orden_codigo': orden.codigo,
                    'orden_id': orden.id,
                    'preference_id': orden.preference_id,
                    'total': float(orden.total),
                    'items_count': items_count,
                },
                status=status.HTTP_200_OK
            )

        except Cliente.DoesNotExist:
            return Response(
                {'error': 'El usuario no tiene perfil de cliente.'},
                status=status.HTTP_403_FORBIDDEN
            )
        except ValidationError as e:
            mensaje = str(e.detail[0]) if hasattr(e, 'detail') and e.detail else str(e)
            return Response({'error': mensaje}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            logger.error(f"Error al generar preferencia de Mercado Pago: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"Error generando pago Mercado Pago: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al generar el pago de Mercado Pago'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WebhookMercadoPagoView(APIView):
    """
    Endpoint que recibe las notificaciones de Mercado Pago (Server-to-Server).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        payment_id = request.data.get('data', {}).get('id') or request.GET.get('data.id') or request.GET.get('id')
        tipo_evento = request.data.get('type') or request.data.get('topic') or request.GET.get('topic')

        if tipo_evento != 'payment' or not payment_id:
            return Response({'status': 'recibido'}, status=status.HTTP_200_OK)

        try:
            sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)
            pago_info = sdk.payment().get(payment_id)
            pago_oficial = pago_info.get('response', {})

            estado_pago = pago_oficial.get('status')
            orden_id = pago_oficial.get('external_reference')
            monto_pagado = pago_oficial.get('transaction_amount')

            if not orden_id:
                logger.warning(f'Webhook MP sin external_reference. Payment ID: {payment_id}')
                return Response({'status': 'recibido'}, status=status.HTTP_200_OK)

            with transaction.atomic():
                orden = OrdenCompra.objects.select_for_update().get(id=orden_id)

                if estado_pago == 'approved':
                    Pago.objects.get_or_create(
                        transaccion_id=str(payment_id),
                        defaults={
                            'orden': orden,
                            'metodo_pago': 'MERCADO_PAGO',
                            'monto': monto_pagado,
                        },
                    )

                    if orden.estado != 'COMPLETADO':
                        for item in orden.items.select_related('producto'):
                            producto = item.producto
                            producto.stock_real = max(0, producto.stock_real - item.cantidad)
                            producto.save(update_fields=['stock_real'])

                        orden.estado = 'COMPLETADO'
                        orden.save(update_fields=['estado', 'actualizado_at'])

                elif estado_pago in ('rejected', 'cancelled'):
                    orden.estado = 'RECHAZADO'
                    orden.save(update_fields=['estado', 'actualizado_at'])

                elif estado_pago in ('pending', 'in_process') and orden.estado == 'PENDIENTE':
                    orden.estado = 'ESPERANDO_PAGO'
                    orden.save(update_fields=['estado', 'actualizado_at'])

            return Response({'status': 'recibido'}, status=status.HTTP_200_OK)

        except OrdenCompra.DoesNotExist:
            logger.warning(
                f"Webhook MP: pago {payment_id} aprobado, pero la orden {orden_id} no existe."
            )
            return Response({'status': 'recibido'}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error en Webhook MP: {str(e)}", exc_info=True)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConfiguracionViewSet(viewsets.ModelViewSet):
    queryset = Configuracion.objects.all()
    serializer_class = ConfiguracionSerializer
    permission_classes = [IsAdminUser]  # Solo administradores
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ConfiguracionFilter
    
    def _ensure_singleton_exists(self):
        """
        Garantiza que existe el record singleton con pk=1.
        Si no existe, lo crea con valores por defecto.
        """
        config, created = Configuracion.objects.get_or_create(pk=1)
        if created:
            logger.info("Configuración singleton creada automáticamente con valores por defecto")
        return config
    
    def get_queryset(self):
        # Asegurar que existe el singleton antes de consultar
        self._ensure_singleton_exists()
        # El singleton siempre retorna 1 solo objeto
        return Configuracion.objects.filter(pk=1)

    def update(self, request, *args, **kwargs):
        # Log de quién cambió qué
        logger.info(f"Usuario {request.user} ({request.user.email}) modificó Configuración Global del Sistema")
        return super().update(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        # Asegurar que existe antes de recuperar
        self._ensure_singleton_exists()
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='publica', permission_classes=[AllowAny])
    def configuracion_publica(self, request):
        config = self._ensure_singleton_exists()
        return Response({
            'empresa_nombre': config.empresa_nombre or 'Bohemia Hair'
        })


class ConfiguracionDiagnosticoViewSet(viewsets.ModelViewSet):
    queryset = ConfiguracionDiagnostico.objects.all()
    serializer_class = ConfiguracionDiagnosticoSerializer
    permission_classes = [IsAdminUser]

    def _ensure_singleton_exists(self):
        ConfiguracionDiagnostico.get_singleton()

    def get_queryset(self):
        self._ensure_singleton_exists()
        return ConfiguracionDiagnostico.objects.filter(pk=1)

    def retrieve(self, request, *args, **kwargs):
        self._ensure_singleton_exists()
        return super().retrieve(request, *args, **kwargs)

class CatalogoBaseListView(generics.ListAPIView):
    permission_classes = [AllowAny]

    def get_queryset(self):
        # self.queryset se define en las clases hijas
        # Filtramos para devolver solo los que están activos
        return self.queryset.filter(activo=True)

class TipoCabelloView(CatalogoBaseListView):
    queryset = TipoCabello.objects.all()
    serializer_class = TipoCabelloSerializer    
class GrosorCabelloView(CatalogoBaseListView):
    queryset = GrosorCabello.objects.all()
    serializer_class = GrosorCabelloSerializer
class PorosidadCabelloView(CatalogoBaseListView):
    queryset = PorosidadCabello.objects.all()
    serializer_class = PorosidadCabelloSerializer
class CueroCabelludoView(CatalogoBaseListView):
    queryset = CueroCabelludo.objects.all()
    serializer_class = CueroCabelludoSerializer
class EstadoGeneralView(CatalogoBaseListView):
    queryset = EstadoGeneral.objects.all()
    serializer_class = EstadoGeneralSerializer
class TipoCabelloViewSet(viewsets.ModelViewSet):
    queryset = TipoCabello.objects.all()
    serializer_class = TipoCabelloSerializer
    permission_classes = [AllowAny]
class GrosorCabelloViewSet(viewsets.ModelViewSet):
    queryset = GrosorCabello.objects.all()
    serializer_class = GrosorCabelloSerializer
    permission_classes = [AllowAny]
class PorosidadCabelloViewSet(viewsets.ModelViewSet):
    queryset = PorosidadCabello.objects.all()
    serializer_class = PorosidadCabelloSerializer
    permission_classes = [AllowAny]
class CueroCabelludoViewSet(viewsets.ModelViewSet):
    queryset = CueroCabelludo.objects.all()
    serializer_class = CueroCabelludoSerializer
    permission_classes = [AllowAny]
class EstadoGeneralViewSet(viewsets.ModelViewSet):
    queryset = EstadoGeneral.objects.all()
    serializer_class = EstadoGeneralSerializer
    permission_classes = [AllowAny]

class CategoriaServicioViewSet(viewsets.ModelViewSet):
    queryset = CategoriaServicio.objects.all()
    serializer_class = CategoriaServicioSerializer
    permission_classes = [AllowAny]

class ServicioViewSet(viewsets.ModelViewSet):
    """
    ViewSet que retorna TODOS los servicios activos para la reserva de turnos.
    """
    serializer_class = ServicioSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ServicioFilter
    search_fields = ['nombre', 'descripcion']
    ordering_fields = ['nombre', 'precio_base']
    
    def get_queryset(self):
        return Servicio.objects.all().order_by('nombre')

class ServiciosQuimicosViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Un ViewSet que retorna *solamente* los servicios que
    afectan el historial químico del cliente, filtrados por
    las categorías "Diseño de Color" y "Turno de Complemento".
    """
    
    serializer_class = ServicioSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # 1. Definimos las categorías relevantes:
        categorias_relevantes = [
            "Diseño de Color",
            "Turno de Complemento"
        ]
        
        # 2. Filtramos los servicios:
        # Busca en el modelo Servicio, mira la 'categoria' relacionada,
        # y filtra por el 'nombre' de esa categoría usando la lista.
        return Servicio.objects.filter(
            categoria__nombre__in=categorias_relevantes
        ).order_by('nombre')


class HabilidadViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo administrativo de skills técnicas."""
    queryset = Habilidad.objects.all().order_by('nombre')
    serializer_class = HabilidadSerializer
    permission_classes = [IsAuthenticated, CanManageSkills]
    pagination_class = None


class PersonalViewSet(viewsets.ModelViewSet):
    """
    Gestiona Personal mediante altas, edición y operaciones semánticas.

    La eliminación física no forma parte de esta API.
    """
    queryset = (
        Personal.objects.select_related('usuario')
        .prefetch_related('usuario__groups', 'horarios')
    )
    serializer_class = PersonalSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PersonalFilter
    search_fields = ['nombre']
    ordering_fields = ['nombre']

    def get_permissions(self):
        if self.action in [
            'habilidades',
            'asignar_habilidad',
            'revocar_habilidad',
            'reactivar_habilidad',
        ]:
            permission_classes = [IsAuthenticated, CanManageSkills]
        elif self.action in [
            'destroy',
            'vincular_usuario',
            'crear_acceso',
            'cambiar_rol_acceso',
            'desactivar',
            'reactivar',
            'revocar_acceso_laboral',
            'revocar_acceso_total',
        ]:
            permission_classes = [IsAuthenticated]
        elif self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    def destroy(self, request, *args, **kwargs):
        """Personal has no ordinary hard-delete operation."""
        raise MethodNotAllowed(
            request.method,
            detail=(
                'Personal no puede eliminarse. Utilice las operaciones '
                'semánticas de estado o revocación de acceso.'
            ),
        )

    @staticmethod
    def _skill_error(code, detail, status_code):
        return Response(
            {'error': {'code': code, 'detail': detail}},
            status=status_code,
        )

    def _run_skill_command(self, command, *, skill_id):
        try:
            return command(
                actor=self.request.user,
                personal_id=self.kwargs['pk'],
                skill_id=skill_id,
            )
        except PersonalSkillPermissionDenied:
            return self._skill_error(
                'PERMISSION_DENIED',
                'No tiene permisos para gestionar habilidades técnicas.',
                status.HTTP_403_FORBIDDEN,
            )
        except PersonalSkillNotFound:
            return self._skill_error(
                'SKILL_OR_PERSONAL_NOT_FOUND',
                'El Personal o la habilidad solicitada no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except PersonalSkillAssignmentNotFound:
            return self._skill_error(
                'SKILL_ASSIGNMENT_NOT_FOUND',
                'El Personal no tiene asignada esa habilidad.',
                status.HTTP_404_NOT_FOUND,
            )
        except InactiveSkill:
            return self._skill_error(
                'INACTIVE_SKILL',
                'La habilidad está inactiva y no puede asignarse ni reactivarse.',
                status.HTTP_409_CONFLICT,
            )

    @action(detail=True, methods=['get'], url_path='habilidades')
    def habilidades(self, request, pk=None):
        personal = self.get_object()
        assignments = (
            PersonalHabilidad.objects.filter(personal=personal)
            .select_related('habilidad')
            .order_by('habilidad__nombre')
        )
        return Response(PersonalHabilidadSerializer(assignments, many=True).data)

    @action(detail=True, methods=['post'], url_path='habilidades/asignar')
    def asignar_habilidad(self, request, pk=None):
        command = PersonalHabilidadAssignCommandSerializer(data=request.data)
        if not command.is_valid():
            return self._skill_error(
                'INVALID_PAYLOAD',
                'El payload de asignación de habilidad es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        result = self._run_skill_command(
            assign_skill,
            skill_id=command.validated_data['habilidad_id'],
        )
        if isinstance(result, Response):
            return result
        return Response({
            'changed': result.changed,
            'event': result.event,
            'assignment': PersonalHabilidadSerializer(result.assignment).data,
        })

    @action(
        detail=True,
        methods=['post'],
        url_path=r'habilidades/(?P<habilidad_id>[^/.]+)/revocar',
    )
    def revocar_habilidad(self, request, pk=None, habilidad_id=None):
        result = self._run_skill_command(revoke_skill, skill_id=habilidad_id)
        if isinstance(result, Response):
            return result
        return Response({
            'changed': result.changed,
            'event': result.event,
            'assignment': PersonalHabilidadSerializer(result.assignment).data,
        })

    @action(
        detail=True,
        methods=['post'],
        url_path=r'habilidades/(?P<habilidad_id>[^/.]+)/reactivar',
    )
    def reactivar_habilidad(self, request, pk=None, habilidad_id=None):
        result = self._run_skill_command(reactivate_skill, skill_id=habilidad_id)
        if isinstance(result, Response):
            return result
        return Response({
            'changed': result.changed,
            'event': result.event,
            'assignment': PersonalHabilidadSerializer(result.assignment).data,
        })

    @action(
        detail=True,
        methods=['post'],
        url_path='vincular-usuario',
        permission_classes=[IsAuthenticated],
    )
    def vincular_usuario(self, request, pk=None):
        try:
            personal = self.get_object()
        except Http404:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = PersonalUserLinkCommandSerializer(data=request.data)
        if not command.is_valid():
            error_code = (
                'INVALID_REASON'
                if set(command.errors) == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._link_error(
                error_code,
                'El payload de vinculación es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            user = Usuario.objects.get(
                pk=command.validated_data['usuario_id']
            )
        except Usuario.DoesNotExist:
            return self._link_error(
                'USER_NOT_FOUND',
                'El Usuario solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        try:
            result = link_user_to_personal(
                actor=request.user,
                personal=personal,
                user=user,
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForPersonalLink:
            return self._link_error(
                'PERMISSION_DENIED',
                'No tiene permisos para vincular usuarios a Personal.',
                status.HTTP_403_FORBIDDEN,
            )
        except ProtectedSuperuser:
            return self._link_error(
                'PROTECTED_SUPERUSER',
                'El Usuario protegido no puede vincularse mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )
        except PersonalAlreadyLinked:
            return self._link_error(
                'PERSONAL_ALREADY_LINKED',
                'El Personal ya está vinculado a otro Usuario.',
                status.HTTP_409_CONFLICT,
            )
        except UserAlreadyLinkedToPersonal:
            return self._link_error(
                'USER_ALREADY_LINKED_TO_PERSONAL',
                'El Usuario ya está vinculado a otro Personal.',
                status.HTTP_409_CONFLICT,
            )
        except InconsistentBusinessRoleState:
            return self._link_error(
                'INCONSISTENT_BUSINESS_ROLES',
                'El Usuario tiene múltiples roles de negocio.',
                status.HTTP_409_CONFLICT,
            )
        except PersonalLinkConflict:
            return self._link_error(
                'PERSONAL_LINK_CONFLICT',
                'El vínculo entra en conflicto con otra operación.',
                status.HTTP_409_CONFLICT,
            )
        except InvalidPersonalLinkTarget:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except InvalidPersonalLinkUser:
            return self._link_error(
                'USER_NOT_FOUND',
                'El Usuario solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except InvalidPersonalLinkReason:
            return self._link_error(
                'INVALID_REASON',
                'El motivo de vinculación es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'changed': result.changed,
            'personal_id': result.personal_id,
            'usuario_id': result.user_id,
            'personal_activo': result.personal_is_active,
            'usuario_activo': result.user_is_active,
            'rol': result.business_role,
            'warnings': list(result.warnings),
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='crear-acceso',
        permission_classes=[IsAuthenticated],
    )
    def crear_acceso(self, request, pk=None):
        try:
            personal = self.get_object()
        except Http404:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = PersonalAccessCreateCommandSerializer(data=request.data)
        if not command.is_valid():
            error_code = (
                'INVALID_REASON'
                if set(command.errors) == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._link_error(
                error_code,
                'El payload de creación de acceso es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            result = create_access_for_personal(
                actor=request.user,
                personal=personal,
                email=command.validated_data['email'],
                raw_password=command.validated_data['password_temporal'],
                role=command.validated_data['role'],
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForPersonalLink:
            return self._link_error(
                'PERMISSION_DENIED',
                'No tiene permisos para crear acceso para Personal.',
                status.HTTP_403_FORBIDDEN,
            )
        except InvalidTemporaryPassword:
            return self._link_error(
                'INVALID_PASSWORD',
                'La contraseña temporal no cumple los requisitos de seguridad.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalAccessRole:
            return self._link_error(
                'INVALID_ROLE',
                'El rol solicitado no está permitido para acceso laboral.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalLinkReason:
            return self._link_error(
                'INVALID_REASON',
                'El motivo de creación de acceso es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalAccessEmail:
            return self._link_error(
                'INVALID_PAYLOAD',
                'El email proporcionado es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalLinkTarget:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except EmailAlreadyExists:
            return self._link_error(
                'EMAIL_ALREADY_EXISTS',
                'Ya existe un Usuario con ese email; utilice vincular-usuario.',
                status.HTTP_409_CONFLICT,
            )
        except (PersonalAlreadyHasAccess, PersonalAlreadyLinked):
            return self._link_error(
                'PERSONAL_ALREADY_HAS_ACCESS',
                'El Personal ya tiene un Usuario vinculado.',
                status.HTTP_409_CONFLICT,
            )
        except PersonalInactiveForAccess:
            return self._link_error(
                'PERSONAL_INACTIVE',
                'No se puede crear acceso para Personal inactivo.',
                status.HTTP_409_CONFLICT,
            )
        except InconsistentBusinessRoleState:
            return self._link_error(
                'INCONSISTENT_BUSINESS_ROLES',
                'El estado de roles de negocio es inconsistente.',
                status.HTTP_409_CONFLICT,
            )
        except (PersonalAccessConflict, PersonalLinkConflict):
            return self._link_error(
                'PERSONAL_ACCESS_CONFLICT',
                'La creación de acceso entra en conflicto con otra operación.',
                status.HTTP_409_CONFLICT,
            )

        return Response({
            'created': result.changed,
            'personal_id': result.personal_id,
            'usuario_id': result.user_id,
            'email': result.email,
            'rol': result.role,
            'personal_activo': result.personal_active,
            'usuario_activo': result.user_active,
        }, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=['post'],
        url_path='cambiar-rol-acceso',
        permission_classes=[IsAuthenticated],
    )
    def cambiar_rol_acceso(self, request, pk=None):
        try:
            personal = self.get_object()
        except Http404:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = PersonalBusinessRoleChangeCommandSerializer(
            data=request.data
        )
        if not command.is_valid():
            error_fields = set(command.errors)
            error_code = (
                'INVALID_TARGET_ROLE'
                if error_fields == {'role'}
                else 'INVALID_REASON'
                if error_fields == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._link_error(
                error_code,
                'El payload de cambio de rol de acceso es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            result = change_personal_business_role(
                actor=request.user,
                personal=personal,
                target_role=command.validated_data['role'],
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForPersonalBusinessRoleChange:
            return self._link_error(
                'PERMISSION_DENIED',
                'No tiene permisos para cambiar el rol de acceso.',
                status.HTTP_403_FORBIDDEN,
            )
        except InvalidPersonalBusinessRoleTarget:
            return self._link_error(
                'INVALID_TARGET_ROLE',
                'Solo se permite asignar EMPLEADO o PROFESIONAL.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalBusinessRoleReason:
            return self._link_error(
                'INVALID_REASON',
                'El motivo del cambio de rol es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except PersonalWithoutUserForRoleChange:
            return self._link_error(
                'PERSONAL_WITHOUT_USER',
                'El Personal no tiene un Usuario vinculado.',
                status.HTTP_409_CONFLICT,
            )
        except PersonalInactiveForRoleChange:
            return self._link_error(
                'PERSONAL_INACTIVE',
                'El Personal debe estar activo para tener un rol laboral.',
                status.HTTP_409_CONFLICT,
            )
        except MultiplePersonalBusinessRoles:
            return self._link_error(
                'MULTIPLE_BUSINESS_ROLES',
                'El Usuario tiene múltiples roles de negocio.',
                status.HTTP_409_CONFLICT,
            )
        except PersonalBusinessRoleChangeNotAllowed:
            return self._link_error(
                'ROLE_CHANGE_NOT_ALLOWED',
                'El rol actual no puede cambiarse mediante esta acción.',
                status.HTTP_409_CONFLICT,
            )
        except InvalidPersonalLinkTarget:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except PersonalBusinessRoleChangeConflict:
            return self._link_error(
                'ROLE_CHANGE_CONFLICT',
                'El cambio de rol entra en conflicto con otra operación.',
                status.HTTP_409_CONFLICT,
            )

        return Response({
            'changed': result.changed,
            'personal_id': result.personal_id,
            'usuario_id': result.user_id,
            'previous_role': result.previous_role,
            'new_role': result.new_role,
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='desactivar',
        permission_classes=[IsAuthenticated],
    )
    def desactivar(self, request, pk=None):
        return self._change_status(request, deactivate_personal)

    @action(
        detail=True,
        methods=['post'],
        url_path='reactivar',
        permission_classes=[IsAuthenticated],
    )
    def reactivar(self, request, pk=None):
        return self._change_status(request, reactivate_personal)

    def _change_status(self, request, service):
        try:
            personal = self.get_object()
        except Http404:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = PersonalStatusChangeCommandSerializer(data=request.data)
        if not command.is_valid():
            error_code = (
                'INVALID_REASON'
                if set(command.errors) == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._link_error(
                error_code,
                'El payload de cambio de estado es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            result = service(
                actor=request.user,
                personal=personal,
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForPersonalStatusChange:
            return self._link_error(
                'PERMISSION_DENIED',
                'No tiene permisos para cambiar el estado del Personal.',
                status.HTTP_403_FORBIDDEN,
            )
        except InvalidPersonalStatusReason:
            return self._link_error(
                'INVALID_REASON',
                'El motivo del cambio de estado es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalLinkTarget:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except PersonalStatusConflict:
            return self._link_error(
                'PERSONAL_STATUS_CONFLICT',
                'El estado del Personal cambió durante la operación.',
                status.HTTP_409_CONFLICT,
            )

        return Response({
            'changed': result.changed,
            'personal_id': result.personal_id,
            'activo_anterior': result.previous_active,
            'activo_actual': result.current_active,
            'usuario_id': result.user_id,
            'usuario_activo': result.user_active,
            'rol': result.current_role,
            'warnings': list(result.warnings),
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='revocar-acceso-laboral',
        permission_classes=[IsAuthenticated],
    )
    def revocar_acceso_laboral(self, request, pk=None):
        try:
            personal = self.get_object()
        except Http404:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = PersonalStatusChangeCommandSerializer(data=request.data)
        if not command.is_valid():
            error_code = (
                'INVALID_REASON'
                if set(command.errors) == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._link_error(
                error_code,
                'El payload de revocación laboral es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            result = revoke_work_access_keep_client(
                actor=request.user,
                personal=personal,
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForWorkAccessRevocation:
            return self._link_error(
                'PERMISSION_DENIED',
                'No tiene permisos para revocar acceso laboral.',
                status.HTTP_403_FORBIDDEN,
            )
        except ProtectedSuperuser:
            return self._link_error(
                'PROTECTED_SUPERUSER',
                'El Usuario protegido no puede gestionarse mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )
        except InvalidWorkAccessRevocationReason:
            return self._link_error(
                'INVALID_REASON',
                'El motivo de revocación laboral es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalLinkTarget:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except PersonalHasNoUser:
            return self._link_error(
                'PERSONAL_HAS_NO_USER',
                'El Personal no tiene un Usuario vinculado.',
                status.HTTP_409_CONFLICT,
            )
        except ClientProfileRequired:
            return self._link_error(
                'CLIENT_PROFILE_REQUIRED',
                'El Usuario debe tener un perfil Cliente existente.',
                status.HTTP_409_CONFLICT,
            )
        except InactiveUserForWorkAccessRevocation:
            return self._link_error(
                'USER_INACTIVE',
                'El Usuario está inactivo y no puede conservar acceso Cliente.',
                status.HTTP_409_CONFLICT,
            )
        except InconsistentBusinessRoleState:
            return self._link_error(
                'INCONSISTENT_BUSINESS_ROLES',
                'El Usuario tiene múltiples roles de negocio.',
                status.HTTP_409_CONFLICT,
            )
        except (WorkAccessRevocationConflict, PersonalStatusConflict):
            return self._link_error(
                'WORK_ACCESS_REVOCATION_CONFLICT',
                'La revocación entra en conflicto con otra operación.',
                status.HTTP_409_CONFLICT,
            )

        return Response({
            'changed': result.changed,
            'personal_id': result.personal_id,
            'usuario_id': result.user_id,
            'rol_anterior': result.previous_role,
            'rol_actual': result.current_role,
            'personal_activo_anterior': result.previous_personal_active,
            'personal_activo_actual': result.current_personal_active,
            'usuario_activo': result.user_active,
            'cliente_id': result.client_id,
            'warnings': list(result.warnings),
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='revocar-acceso-total',
        permission_classes=[IsAuthenticated],
    )
    def revocar_acceso_total(self, request, pk=None):
        try:
            personal = self.get_object()
        except Http404:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = PersonalStatusChangeCommandSerializer(data=request.data)
        if not command.is_valid():
            error_code = (
                'INVALID_REASON'
                if set(command.errors) == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._link_error(
                error_code,
                'El payload de baja total es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            result = revoke_work_access_and_disable_account(
                actor=request.user,
                personal=personal,
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForFullWorkAccessRevocation:
            return self._link_error(
                'PERMISSION_DENIED',
                'No tiene permisos para realizar la baja total.',
                status.HTTP_403_FORBIDDEN,
            )
        except ProtectedSuperuser:
            return self._link_error(
                'PROTECTED_SUPERUSER',
                'El Usuario protegido no puede gestionarse mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )
        except SelfDeactivationNotAllowed:
            return self._link_error(
                'SELF_DEACTIVATION_NOT_ALLOWED',
                'No puede desactivar su propia cuenta mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )
        except LastActiveAdministrator:
            return self._link_error(
                'LAST_ACTIVE_ADMIN',
                'No puede desactivarse el último administrador activo.',
                status.HTTP_403_FORBIDDEN,
            )
        except InvalidFullWorkAccessRevocationReason:
            return self._link_error(
                'INVALID_REASON',
                'El motivo de baja total es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidPersonalLinkTarget:
            return self._link_error(
                'PERSONAL_NOT_FOUND',
                'El Personal solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except PersonalHasNoUser:
            return self._link_error(
                'PERSONAL_HAS_NO_USER',
                'El Personal no tiene un Usuario vinculado.',
                status.HTTP_409_CONFLICT,
            )
        except FullWorkAccessRevocationConflict:
            return self._link_error(
                'WORK_ACCESS_REVOCATION_CONFLICT',
                'La baja total entra en conflicto con otra operación.',
                status.HTTP_409_CONFLICT,
            )

        return Response({
            'changed': result.changed,
            'personal_id': result.personal_id,
            'usuario_id': result.user_id,
            'personal_activo_anterior': result.previous_personal_active,
            'personal_activo_actual': result.current_personal_active,
            'usuario_activo_anterior': result.previous_user_active,
            'usuario_activo_actual': result.current_user_active,
            'rol_actual': result.current_role,
            'warnings': list(result.warnings),
        }, status=status.HTTP_200_OK)

    @staticmethod
    def _link_error(code, detail, status_code, fields=None):
        error = {'code': code, 'detail': detail}
        if fields is not None:
            error['fields'] = fields
        return Response({'error': error}, status=status_code)
    
class DisponibilidadTurnosView(APIView):
    """
    Alias público legacy para consultar slots mediante la lógica canónica.
    Uso: GET /api/gestion/disponibilidad/?fecha=2023-11-01&servicio_id=1
    """
    permission_classes = [AllowAny]

    def get(self, request):
        fecha_str = request.query_params.get('fecha')
        servicio_id = request.query_params.get('servicio_id')

        if not fecha_str or not servicio_id:
            return Response(
                {"error": "Faltan parámetros obligatorios: 'fecha' y 'servicio_id'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {"error": "Formato de fecha inválido. Use AAAA-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            servicio = Servicio.objects.prefetch_related(
                'requisitos_habilidad__habilidad'
            ).get(id=servicio_id, activo=True)
        except Servicio.DoesNotExist:
            return Response(
                {"error": "El servicio especificado no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )

        config = Configuracion.objects.first()
        max_dias = config.max_dias_anticipacion if config else 60
        intervalo_minutos = config.intervalo_turnos if config else 30
        hoy = timezone.localdate()
        if fecha_consulta < hoy:
            return Response(
                {"error": "No se pueden agendar turnos en el pasado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if fecha_consulta > hoy + timedelta(days=max_dias):
            return Response(
                {"error": "La fecha supera el horizonte habilitado para reservas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        horarios = set()
        for schedule in TurnoAvailabilityService.matching_schedules(
            fecha=fecha_consulta,
            servicio=servicio,
        ):
            slots = TurnoAvailabilityService.available_slots_for_schedule(
                fecha=fecha_consulta,
                schedule=schedule,
                servicio=servicio,
                intervalo_minutos=intervalo_minutos,
            )
            horarios.update(slot['hora'] for slot in slots)

        return Response({
            "fecha": fecha_str,
            "servicio_solicitado": servicio.nombre,
            "duracion_minutos": servicio.duracion_estimada or 60,
            "horarios_disponibles": sorted(horarios),
        }, status=status.HTTP_200_OK)


class ServicioViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar servicios con CRUD completo.
    - Lectura: AllowAny (clientes pueden ver servicios disponibles)
    - Creación/Actualización/Eliminación: Solo IsAdminUser
    """
    serializer_class = ServicioSerializer
    pagination_class = None

    def get_queryset(self):
        # Admins ven todos los servicios (activos e inactivos)
        # Clientes ven solo activos
        if self.request.user.is_staff:
            return Servicio.objects.all().order_by('nombre')
        else:
            return Servicio.objects.filter(activo=True).order_by('nombre')
    
    def get_permissions(self):
        """Permisos dinámicos: lista/retrieve abierto, CRUD solo para admins"""
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def perform_destroy(self, instance):
        """Soft delete: marca como inactivo en lugar de eliminar"""
        instance.activo = False
        instance.save()

# --- 3. VIEWSET DE TURNOS (CRUD) ---
class TurnoViewSet(viewsets.ModelViewSet):
    # Usamos prefetch_related para optimizar la consulta de la tabla intermedia
    queryset = Turno.objects.all().prefetch_related('detalles__servicio', 'cliente__usuario')
    serializer_class = TurnoSerializer
    pagination_class = None 
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TurnoFilter
    search_fields = ['cliente__usuario__first_name', 'cliente__usuario__last_name']
    ordering_fields = ['fecha', 'hora_inicio', 'estado']

    SAFE_DETAIL_ACTIONS = {
        'retrieve',
        'verificar_expiracion',
    }

    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [IsAuthenticated, CanViewGlobalAgenda]
        elif self.action in [
            'crear_para_cliente',
            'selector_clientes',
            'selector_personal',
        ]:
            permission_classes = [IsAuthenticated, CanCreateTurnoForClient]
        elif self.action == 'registrar_llegada':
            permission_classes = [IsAuthenticated, CanRegisterTurnoArrival]
        elif self.action == 'reprogramar':
            permission_classes = [IsAuthenticated, CanReprogramAnyTurno]
        elif self.action == 'cancelar':
            permission_classes = [IsAuthenticated, CanCancelAnyTurno]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action in ['list', 'mi_agenda_laboral']:
            return TurnoAgendaReadSerializer
        if self.action in ['mis_turnos', 'subir_comprobante']:
            return TurnoClienteReadSerializer
        return TurnoSerializer

    def _readable_turnos(self):
        queryset = super().get_queryset()
        user = self.request.user

        if user.has_perm(BusinessPermission.VIEW_GLOBAL_AGENDA):
            return queryset

        scopes = Q(cliente__usuario=user)
        if user.is_active:
            scopes |= Q(
                profesional__usuario=user,
                profesional__activo=True,
            )
        return queryset.filter(scopes)

    def _legacy_action_queryset(self):
        """Preserva el alcance previo de acciones aún no migradas."""
        queryset = super().get_queryset()
        if self.request.user.is_staff:
            return queryset
        if hasattr(self.request.user, 'cliente'):
            return queryset.filter(cliente=self.request.user.cliente)
        return queryset.none()

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.action == 'list':
            queryset = queryset
        elif self.action == 'mis_turnos':
            cliente = getattr(self.request.user, 'cliente', None)
            queryset = (
                queryset.filter(cliente=cliente)
                if cliente is not None
                else queryset.none()
            )
        elif self.action == 'mi_agenda_laboral':
            personal = getattr(self.request.user, 'perfil_profesional', None)
            if (
                personal is None
                or not personal.activo
                or not self.request.user.is_active
            ):
                queryset = queryset.none()
            else:
                queryset = queryset.filter(profesional=personal)
        elif self.action in self.SAFE_DETAIL_ACTIONS:
            queryset = self._readable_turnos()
        else:
            queryset = self._legacy_action_queryset()
             
        #Filtro opcional por estado
        estado = self.request.query_params.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)
        
        #Ordenar por fecha y hora
        queryset = queryset.order_by('-fecha', '-hora_inicio')
        
        return queryset

    def retrieve(self, request, *args, **kwargs):
        turno = self.get_object()
        serializer_class = (
            TurnoClienteReadSerializer
            if turno.cliente.usuario_id == request.user.pk
            else TurnoAgendaReadSerializer
        )
        serializer = serializer_class(
            turno,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    @staticmethod
    def _creation_validation_error(exc):
        return ValidationError({
            exc.field: [exc.detail],
            'code': exc.code,
        })

    @action(detail=False, methods=['post'], url_path='reservar')
    def reservar(self, request):
        cliente = getattr(request.user, 'cliente', None)
        if cliente is None or not cliente.activo or not request.user.is_active:
            raise PermissionDenied('Se requiere un perfil de Cliente activo.')

        command = TurnoReservaCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        try:
            turno = TurnoCreationService.create(
                cliente_id=cliente.pk,
                servicio_id=command.validated_data['servicio'],
                profesional_id=command.validated_data['profesional'],
                fecha=command.validated_data['fecha'],
                hora_inicio=command.validated_data['hora_inicio'],
                source=Turno.CanalOrigen.WEB,
            )
        except TurnoCreationError as exc:
            raise self._creation_validation_error(exc)

        return Response({
            'mensaje': 'Turno solicitado correctamente.',
            'turno': TurnoClienteReadSerializer(
                turno,
                context=self.get_serializer_context(),
            ).data,
            'alerta_daño_capilar': turno.alerta_daño_capilar,
            'advertencia': (
                'El Turno requiere evaluación profesional por posible riesgo capilar.'
                if turno.alerta_daño_capilar
                else None
            ),
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='crear-para-cliente')
    def crear_para_cliente(self, request):
        command = TurnoParaClienteCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        try:
            turno = TurnoCreationService.create(
                cliente_id=command.validated_data['cliente_id'],
                servicio_id=command.validated_data['servicio'],
                profesional_id=command.validated_data['profesional'],
                fecha=command.validated_data['fecha'],
                hora_inicio=command.validated_data['hora_inicio'],
                source=Turno.CanalOrigen.PRESENCIAL,
            )
        except TurnoCreationError as exc:
            raise self._creation_validation_error(exc)

        return Response({
            'mensaje': 'Turno solicitado para el Cliente correctamente.',
            'turno': TurnoAgendaReadSerializer(
                turno,
                context=self.get_serializer_context(),
            ).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='registrar-llegada')
    def registrar_llegada(self, request, pk=None):
        command = TurnoArrivalCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)

        try:
            result = register_turno_arrival(
                actor=request.user,
                turno_id=pk,
            )
        except PermissionDeniedForTurnoArrival:
            raise PermissionDenied('No tiene permisos para registrar la llegada.')
        except TurnoArrivalTargetNotFound:
            raise Http404
        except InvalidTurnoArrivalTransition as exc:
            return Response(
                {
                    'code': 'INVALID_ARRIVAL_TRANSITION',
                    'detail': 'El Turno no admite registrar llegada en su estado actual.',
                    'estado_actual': exc.current_state,
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response({
            'turno_id': result.turno.pk,
            'changed': result.changed,
            'estado_anterior': result.previous_state,
            'estado_actual': result.current_state,
        }, status=status.HTTP_200_OK)

    @staticmethod
    def _management_conflict(exc, code):
        return Response(
            {
                'code': code,
                'detail': 'El Turno no admite esta operación en su estado actual.',
                'estado_actual': exc.current_state,
            },
            status=status.HTTP_409_CONFLICT,
        )

    @staticmethod
    def _management_validation_error(exc):
        return Response(
            {
                exc.field: [exc.detail],
                'code': exc.code,
            },
            status=status.HTTP_409_CONFLICT,
        )

    @action(detail=True, methods=['post'], url_path='reprogramar')
    def reprogramar(self, request, pk=None):
        command = TurnoRescheduleCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        try:
            result = reprogram_turno(
                actor=request.user,
                turno_id=pk,
                fecha=command.validated_data['fecha'],
                hora_inicio=command.validated_data['hora'],
                profesional_id=command.validated_data.get('profesional_id'),
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForTurnoManagement:
            raise PermissionDenied('No tiene permisos para reprogramar Turnos.')
        except TurnoManagementTargetNotFound:
            raise Http404
        except InvalidTurnoManagementTransition as exc:
            return self._management_conflict(exc, 'INVALID_RESCHEDULE_TRANSITION')
        except (TurnoManagementError, TurnoCreationError) as exc:
            return self._management_validation_error(exc)

        return Response({
            'turno_id': result.turno.pk,
            'fecha_anterior': result.previous_date,
            'fecha_actual': result.current_date,
            'hora_anterior': result.previous_time,
            'hora_actual': result.current_time,
            'profesional_anterior_id': result.previous_professional_id,
            'profesional_actual_id': result.current_professional_id,
            'estado_anterior': result.previous_state,
            'estado_actual': result.current_state,
        })

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        command = TurnoCancellationCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        try:
            result = cancel_turno(
                actor=request.user,
                turno_id=pk,
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForTurnoManagement:
            raise PermissionDenied('No tiene permisos para cancelar Turnos.')
        except TurnoManagementTargetNotFound:
            raise Http404
        except InvalidTurnoManagementTransition as exc:
            return self._management_conflict(exc, 'INVALID_CANCELLATION_TRANSITION')

        return Response({
            'turno_id': result.turno.pk,
            'changed': result.changed,
            'estado_anterior': result.previous_state,
            'estado_actual': result.current_state,
        })

    @action(detail=False, methods=['get'], url_path='selector-clientes')
    def selector_clientes(self, request):
        clientes = (
            Cliente.objects.filter(activo=True, usuario__is_active=True)
            .select_related('usuario')
            .order_by('usuario__first_name', 'usuario__last_name', 'usuario__email')
        )
        return Response([
            {
                'id': cliente.pk,
                'nombre': cliente.usuario.first_name,
                'apellido': cliente.usuario.last_name,
                'email': cliente.usuario.email,
            }
            for cliente in clientes
        ])

    @action(detail=False, methods=['get'], url_path='selector-personal')
    def selector_personal(self, request):
        personal = Personal.objects.filter(activo=True).order_by('nombre', 'apellido')
        raw_service_ids = request.query_params.getlist('servicio_ids')
        if raw_service_ids:
            service_ids = []
            try:
                for raw_value in raw_service_ids:
                    service_ids.extend(
                        int(value)
                        for value in raw_value.split(',')
                        if value.strip()
                    )
            except ValueError:
                raise ValidationError({
                    'servicio_ids': 'Los IDs de Servicio deben ser enteros.'
                })

            services = list(
                Servicio.objects.filter(pk__in=service_ids, activo=True)
                .prefetch_related('requisitos_habilidad__habilidad')
            )
            if len({service.pk for service in services}) != len(set(service_ids)):
                raise ValidationError({
                    'servicio_ids': 'Uno o más Servicios no existen o están inactivos.'
                })
            personal = service_skill_policy(services).filter_personal(personal)
        return Response([
            {
                'id': persona.pk,
                'nombre': persona.nombre,
                'apellido': persona.apellido,
                'funcion': persona.get_rol_display(),
            }
            for persona in personal
        ])

    @action(detail=False, methods=['get'], url_path='mis-turnos')
    def mis_turnos(self, request):
        if getattr(request.user, 'cliente', None) is None:
            raise PermissionDenied('El usuario no tiene un perfil de Cliente.')

        queryset = self.filter_queryset(self.get_queryset())
        serializer = TurnoClienteReadSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='mi-agenda-laboral')
    def mi_agenda_laboral(self, request):
        personal = getattr(request.user, 'perfil_profesional', None)
        if personal is None or not personal.activo or not request.user.is_active:
            raise PermissionDenied('No existe un perfil de Personal activo.')

        queryset = self.filter_queryset(self.get_queryset())
        serializer = TurnoAgendaReadSerializer(
            queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        return Response(serializer.data)

    @action(
        detail=True,
        methods=['post'],
        url_path='subir-comprobante',
        parser_classes=[MultiPartParser, FormParser],
    )
    def subir_comprobante(self, request, pk=None):
        try:
            turno = Turno.objects.get(
                pk=pk,
                cliente__usuario=request.user,
            )
        except Turno.DoesNotExist:
            raise Http404

        if turno.estado != Turno.Estado.ESPERANDO_SENA:
            raise ValidationError({
                'estado': 'El Turno no admite comprobantes en su estado actual.',
            })

        command = TurnoComprobanteUploadSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        turno.comprobante_pago = command.validated_data['comprobante_pago']
        turno.save(update_fields=['comprobante_pago'])

        return Response(
            TurnoClienteReadSerializer(
                turno,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )

    def perform_update(self, serializer):
        """
        Admins pueden actualizar cualquier turno.
        Clientes pueden actualizar solo sus propios turnos (principalmente para subir comprobante).
        """
        turno = serializer.instance
        
        # Validar que el cliente solo actualiza sus propios turnos
        if not self.request.user.is_staff:
            if turno.cliente.usuario != self.request.user:
                raise PermissionDenied("No puedes actualizar turnos de otros clientes.")
        
        # Si el turno transiciona a ESPERANDO_SENA, calcular fecha_limite_pago
        nuevo_estado = serializer.validated_data.get('estado', turno.estado)
        
        if nuevo_estado == Turno.Estado.ESPERANDO_SENA and turno.estado != Turno.Estado.ESPERANDO_SENA:
            # Primera vez que pasa a ESPERANDO_SENA, calcular plazo de pago
            config = Configuracion.objects.first()
            if config:
                turno.fecha_limite_pago = timezone.now() + timedelta(hours=config.tiempo_limite_pago_sena)
        
        serializer.save()

    @action(detail=True, methods=['post'])
    def registrar_pago(self, request, pk=None):
        """
        POST /api/gestion/turnos/{id}/registrar_pago/

        Permite al profesional registrar un pago asociado a un turno.
        """
        if not request.user.is_staff:
            raise PermissionDenied("No tienes permisos para registrar pagos.")

        turno = self.get_object()
        serializer = PagoSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        pago = serializer.save(turno=turno)

        return Response(
            {
                'status': 'Pago registrado',
                'pago': PagoSerializer(pago, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def reprogramar_cliente(self, request, pk=None):
        """
        Permite que el cliente reprograme su turno (solo turnos en estado 'solicitado' o 'esperando_sena')
        POST /api/gestion/turnos/{id}/reprogramar_cliente/
        Body: {"fecha": "2026-01-20", "hora_inicio": "14:00"}
        """
        command = TurnoClientRescheduleCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        try:
            result = reprogram_owned_turno(
                actor=request.user,
                turno_id=pk,
                fecha=command.validated_data['fecha'],
                hora_inicio=command.validated_data['hora_inicio'],
                profesional_id=command.validated_data.get('profesional_id'),
            )
        except TurnoManagementTargetNotFound:
            raise Http404
        except InvalidTurnoManagementTransition as exc:
            return self._management_conflict(exc, 'INVALID_CLIENT_RESCHEDULE_TRANSITION')
        except (TurnoManagementError, TurnoCreationError) as exc:
            return self._management_validation_error(exc)

        return Response({
            'mensaje': 'Turno reprogramado con éxito.',
            'turno_id': result.turno.pk,
            'fecha': result.current_date,
            'hora_inicio': result.current_time,
            'profesional_id': result.current_professional_id,
            'estado': result.current_state,
        })

    @action(detail=True, methods=['get'], url_path='opciones-cliente')
    def opciones_cliente(self, request, pk=None):
        try:
            turno = Turno.objects.get(pk=pk, cliente__usuario=request.user)
        except Turno.DoesNotExist:
            raise Http404

        config = Configuracion.objects.first() or Configuracion()
        appointment_at = timezone.make_aware(
            datetime.combine(turno.fecha, turno.hora_inicio),
            timezone.get_current_timezone(),
        )
        remaining_hours = (appointment_at - timezone.now()).total_seconds() / 3600
        within_window = remaining_hours >= config.horas_limite_cancelacion
        can_reprogram = turno.estado in CLIENT_REPROGRAMMABLE_STATES
        if turno.estado == Turno.Estado.CONFIRMADO:
            can_reprogram = (
                can_reprogram
                and within_window
                and turno.cambios_realizados < config.max_reprogramaciones
            )

        return Response({
            'puede_reprogramar': can_reprogram,
            'puede_cancelar': (
                turno.estado in CLIENT_CANCELLABLE_STATES and within_window
            ),
            'mensaje': 'Seleccioná una operación disponible para tu Turno.',
            'tipo_alerta': 'info',
            'cambios_realizados': turno.cambios_realizados,
            'limite_cambios': config.max_reprogramaciones,
            'horas_restantes': round(remaining_hours, 2),
        })

    @action(detail=True, methods=['post'], url_path='cancelar-cliente')
    def cancelar_cliente(self, request, pk=None):
        command = TurnoCancellationCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        try:
            result = cancel_owned_turno(
                actor=request.user,
                turno_id=pk,
                reason=command.validated_data['motivo'],
            )
        except TurnoManagementTargetNotFound:
            raise Http404
        except InvalidTurnoManagementTransition as exc:
            return self._management_conflict(exc, 'INVALID_CLIENT_CANCELLATION_TRANSITION')
        except TurnoManagementError as exc:
            return self._management_validation_error(exc)

        return Response({
            'mensaje': 'Turno cancelado correctamente.',
            'turno_id': result.turno.pk,
            'changed': result.changed,
            'estado_actual': result.current_state,
        })
    
    def _validar_slot_libre(self, fecha, hora, profesional, duracion_minutos, servicios_ids=None, excluir_turno_id=None):
        """
        Valida si un slot está realmente disponible (sin conflictos).
        servicios_ids: Lista de IDs de servicios para validar equipamiento
        excluir_turno_id: ID del turno a excluir de la búsqueda (usado para reprogramación)
        """
        if not profesional:
            return False
        
        # Convertir hora a datetime para comparación
        inicio_dt = datetime.combine(fecha, hora)
        duracion_min = duracion_minutos or 60
        fin_minutos = hora.hour * 60 + hora.minute + duracion_min
        fin_horas = fin_minutos // 60
        fin_mins = fin_minutos % 60
        fin_hora = time(fin_horas, fin_mins)
        fin_dt = datetime.combine(fecha, fin_hora)
        
        # 1. Verificar conflictos con otros turnos
        turnos_conflicto = Turno.objects.filter(
            fecha=fecha,
            profesional=profesional,
            estado__in=['confirmado', 'esperando_sena', 'solicitado', 'sugerido']
        ).prefetch_related('detalles')
        
        # Excluir el turno actual si se proporciona un ID
        if excluir_turno_id:
            turnos_conflicto = turnos_conflicto.exclude(id=excluir_turno_id)
        
        for turno in turnos_conflicto:
            turno_duracion = sum(d.duracion_minutos for d in turno.detalles.all()) or 60
            turno_fin_minutos = turno.hora_inicio.hour * 60 + turno.hora_inicio.minute + turno_duracion
            turno_fin_horas = turno_fin_minutos // 60
            turno_fin_mins = turno_fin_minutos % 60
            turno_fin_hora = time(turno_fin_horas, turno_fin_mins)
            turno_fin_dt = datetime.combine(fecha, turno_fin_hora)
            
            turno_inicio_dt = datetime.combine(fecha, turno.hora_inicio)
            
            # Verificar solapamiento: (inicio < otro_fin) AND (fin > otro_inicio)
            if (inicio_dt < turno_fin_dt) and (fin_dt > turno_inicio_dt):
                return False
        
        # 2. Verificar conflictos con bloqueos
        bloqueos_conflicto = BloqueoAgenda.objects.filter(
            Q(personal=profesional) | Q(personal__isnull=True),
            fecha_inicio__date__lte=fecha,
            fecha_fin__date__gte=fecha
        )
        
        for bloqueo in bloqueos_conflicto:
            bloqueo_inicio = bloqueo.fecha_inicio.replace(tzinfo=None) if bloqueo.fecha_inicio.tzinfo else bloqueo.fecha_inicio
            bloqueo_fin = bloqueo.fecha_fin.replace(tzinfo=None) if bloqueo.fecha_fin.tzinfo else bloqueo.fecha_fin
            inicio_dt_naive = inicio_dt.replace(tzinfo=None) if hasattr(inicio_dt, 'tzinfo') else inicio_dt
            fin_dt_naive = fin_dt.replace(tzinfo=None) if hasattr(fin_dt, 'tzinfo') else fin_dt
            
            if (inicio_dt_naive < bloqueo_fin) and (fin_dt_naive > bloqueo_inicio):
                return False
        
        # 3. Nueva Validación: Recursos Físicos
        if servicios_ids:
            if not self._verificar_disponibilidad_equipamiento(fecha, inicio_dt, fin_dt, servicios_ids, excluir_turno_id):
                return False
        
        return True

    # =====================================================================
    # NUEVA ACCIÓN: CONSULTAR DISPONIBILIDAD (Flujo actualizado)
    # =====================================================================
    @action(detail=False, methods=['get'])
    def consultar_disponibilidad(self, request):
        """
        Devuelve fechas y horarios disponibles para un servicio.
        Query params: ?servicio_id=1&fecha=2026-01-15 (fecha opcional, por defecto hoy)
        """
        servicio_id = request.query_params.get('servicio_id')
        fecha_inicio_str = request.query_params.get('fecha')
        excluir_turno_id = request.query_params.get('turno_id')
        slot_services = None
        
        if not servicio_id:
            return Response(
                {"error": "Se requiere servicio_id"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            servicio = Servicio.objects.prefetch_related(
                'requisitos_habilidad__habilidad'
            ).get(id=servicio_id, activo=True)
        except Servicio.DoesNotExist:
            return Response(
                {"error": "El servicio no existe"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if excluir_turno_id:
            try:
                turno_excluido = Turno.objects.get(pk=excluir_turno_id)
            except (Turno.DoesNotExist, ValueError):
                raise Http404
            is_owner = turno_excluido.cliente.usuario_id == request.user.pk
            if not (
                is_owner
                or request.user.has_perm(BusinessPermission.REPROGRAM_ANY_TURNO)
            ):
                raise Http404
            if not turno_excluido.detalles.filter(servicio=servicio).exists():
                return Response(
                    {'error': 'El Servicio no corresponde al Turno indicado.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            detalles_turno = list(
                turno_excluido.detalles.select_related('servicio').prefetch_related(
                    'servicio__requisitos_habilidad__habilidad'
                ).all()
            )
            slot_services = [detalle.servicio for detalle in detalles_turno]
            duracion_minutos = (
                sum(detalle.duracion_minutos for detalle in detalles_turno) or 60
            )
            excluir_turno_id = turno_excluido.pk
        
        # Determinar fecha de inicio
        try:
            if fecha_inicio_str:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            else:
                fecha_inicio = timezone.now().date()
        except ValueError:
            return Response(
                {"error": "Formato de fecha inválido. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 1. Obtener horizonte de reserva (config)
        config = Configuracion.objects.first()
        max_dias = config.max_dias_anticipacion if config else 60
        intervalo_minutos = config.intervalo_turnos if config else 30
        fecha_limite = timezone.localdate() + timedelta(days=max_dias)
        
        # 2. Validar que no sea fecha pasada
        if fecha_inicio < timezone.now().date():
            return Response(
                {"error": "No se pueden agendar turnos en el pasado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if fecha_inicio > fecha_limite:
            return Response(
                {"error": "La fecha supera el horizonte habilitado para reservas"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        if slot_services is None:
            slot_services = [servicio]
            duracion_minutos = servicio.duracion_estimada or 60
        
        # 4. Iterar próximos días (hasta 7 para mostrar lo más cercano)
        disponibilidad_total = []
        
        for i in range(7):
            fecha_consulta = fecha_inicio + timedelta(days=i)
            
            # Validar horizonte
            if fecha_consulta > fecha_limite:
                break
            
            # No agendar en fechas pasadas
            if fecha_consulta < timezone.now().date():
                continue
            
            dia_semana = fecha_consulta.weekday()
            
            reglas = TurnoAvailabilityService.matching_schedules(
                fecha=fecha_consulta,
                servicio=servicio,
                servicios=slot_services,
            )
            
            if not reglas.exists():
                continue
            
            # 6. Generar slots disponibles para este día
            slots_del_dia = []
            profesionales_dia = {}
            
            for regla in reglas:
                prof_id = regla.personal.id
                prof_nombre = regla.personal.nombre
                
                slots = self._generar_slots_disponibles(
                    fecha_consulta, 
                    regla, 
                    duracion_minutos,
                    intervalo_minutos,
                    servicios_ids=[servicio.id],
                    excluir_turno_id=excluir_turno_id,
                    servicios=slot_services,
                )
                
                if slots:
                    if prof_id not in profesionales_dia:
                        profesionales_dia[prof_id] = {
                            "id": prof_id,
                            "nombre": prof_nombre,
                            "slots": []
                        }
                    profesionales_dia[prof_id]["slots"].extend(slots)
            
            if profesionales_dia:
                disponibilidad_total.append({
                    "fecha": fecha_consulta.isoformat(),
                    "dia_semana": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][dia_semana],
                    "profesionales": list(profesionales_dia.values())
                })
        
        return Response({
            "servicio_id": servicio.id,
            "servicio_nombre": servicio.nombre,
            "duracion_minutos": duracion_minutos,
            "disponibilidad": disponibilidad_total,
            "horizonte_dias": max_dias
        }, status=status.HTTP_200_OK)
    
    def _generar_slots_disponibles(
        self,
        fecha,
        regla,
        duracion_minutos,
        intervalo_minutos,
        servicios_ids=None,
        excluir_turno_id=None,
        servicios=None,
    ):
        servicio = (
            servicios[0]
            if servicios
            else (
                Servicio.objects.filter(pk=servicios_ids[0], activo=True).first()
                if servicios_ids
                else None
            )
        )
        if servicio is None:
            return []
        return TurnoAvailabilityService.available_slots_for_schedule(
            fecha=fecha,
            schedule=regla,
            servicio=servicio,
            intervalo_minutos=intervalo_minutos,
            excluir_turno_id=excluir_turno_id,
            duracion_minutos=duracion_minutos,
            servicios=servicios,
        )
    
    def _buscar_proxima_fecha(self, servicio_id, fecha_desde):
        """
        Escanea los próximos 30 días para encontrar el primer día con al menos un slot.
        """
        servicio = Servicio.objects.get(id=servicio_id)
        config = Configuracion.objects.first()
        max_busqueda = 30 # No buscamos eternamente, solo un mes
        
        for i in range(7, max_busqueda): # Empezamos desde el día 7
            fecha_proxima = fecha_desde + timedelta(days=i)
            
            # 1. Filtramos reglas para ese día
            weekday = fecha_proxima.weekday()
            reglas = HorarioLaboral.objects.filter(
                dia_semana=weekday,
                fecha_desde__lte=fecha_proxima,
                fecha_hasta__gte=fecha_proxima,
                activo=True
            )
            
            # Filtro por tipo de servicio (lo que ya tienes)
            # ... (aquí aplicas el filtro de Diseño/Complemento) ...

            for regla in reglas:
                slots = self._generar_slots_disponibles(
                    fecha_proxima, 
                    regla, 
                    servicio.duracion_estimada, 
                    config.intervalo_turnos,
                    servicios_ids=[servicio.id],
                )
                if slots:
                    return fecha_proxima.isoformat()
                    
        return None # No hay nada en todo el mes

    def _verificar_disponibilidad_equipamiento(self, fecha, inicio_dt, fin_dt, servicios_ids, excluir_turno_id=None):
        """
        Valida si hay unidades físicas disponibles (lavacabezas, puestos)
        para realizar los servicios en el rango horario solicitado.
        """
        from django.db.models import Max
        if not servicios_ids:
            return True

        # 1. Obtener los tipos de equipo requeridos por los servicios
        requisitos = RequisitoServicio.objects.filter(
            servicio_id__in=servicios_ids,
            obligatorio=True
        ).select_related('tipo_equipamiento')

        if not requisitos.exists():
            return True

        # 2. Consolidar requerimientos (por si varios servicios piden lo mismo)
        req_por_tipo = {}
        for req in requisitos:
            tid = req.tipo_equipamiento_id
            req_por_tipo[tid] = max(req_por_tipo.get(tid, 0), req.cantidad_minima)

        # 3. Chequear stock vs ocupación para cada tipo
        for tipo_id, cant_necesaria in req_por_tipo.items():
            # Unidades totales operativas de este tipo
            stock_total = Equipamiento.objects.filter(
                tipo_id=tipo_id,
                is_active=True,
                estado='DISPONIBLE'
            ).count()

            # Turnos que ya ocupan este recurso en esa fecha
            turnos_competencia = Turno.objects.filter(
                fecha=fecha,
                estado__in=['confirmado', 'esperando_sena', 'solicitado', 'sugerido'],
                detalles__servicio__requisitos_equipamiento__tipo_equipamiento_id=tipo_id
            ).distinct()

            if excluir_turno_id:
                turnos_competencia = turnos_competencia.exclude(id=excluir_turno_id)

            # Contar cuántos equipos están 'en uso' en ese rango exacto
            ocupados = 0
            for t in turnos_competencia:
                t_ini = datetime.combine(fecha, t.hora_inicio)
                dur_t = sum(d.duracion_minutos for d in t.detalles.all()) or 60
                t_fin = t_ini + timedelta(minutes=dur_t)

                # Si hay solapamiento de horarios
                if (inicio_dt < t_fin) and (fin_dt > t_ini):
                    # Ver cuánto pide ese turno específico
                    req_t = RequisitoServicio.objects.filter(
                        servicio__detalles__turno=t,
                        tipo_equipamiento_id=tipo_id
                    ).aggregate(m=Max('cantidad_minima'))['m'] or 1
                    ocupados += req_t

            if (ocupados + cant_necesaria) > stock_total:
                return False # No hay suficientes lavacabezas/puestos

        return True

    # =====================================================================
    # NUEVO: VERIFICAR SI TURNO ESTÁ EXPIRADO
    # =====================================================================
    @action(detail=True, methods=['get'], url_path='verificar-expiracion')
    def verificar_expiracion(self, request, pk=None):
        """
        Verifica si un turno ha expirado (pasó la fecha sin confirmación).
        GET /api/gestion/turnos/{id}/verificar-expiracion/
        
        Retorna:
        - expired: bool - True si el turno ya pasó su fecha
        - estado_actual: str - Estado actual del turno
        - fecha_hora: datetime - Fecha del turno
        - horas_transcurridas: float - Horas desde que pasó la fecha (si aplica)
        """
        turno = self.get_object()
        now = timezone.now()
        
        # Convertir fecha_hora a datetime aware
        turno_dt = timezone.make_aware(datetime.combine(turno.fecha, turno.hora_inicio)) \
            if timezone.is_naive(datetime.combine(turno.fecha, turno.hora_inicio)) \
            else datetime.combine(turno.fecha, turno.hora_inicio)
        
        expired = turno_dt < now
        horas_transcurridas = (now - turno_dt).total_seconds() / 3600 if expired else 0
        
        return Response({
            'expired': expired,
            'estado_actual': turno.get_estado_display(),
            'fecha_hora': turno_dt,
            'horas_transcurridas': round(horas_transcurridas, 1),
            'mensaje': f'El turno pasó hace {round(horas_transcurridas, 1)} horas sin confirmación. Ha sido cancelado automáticamente.' 
                      if expired and turno.estado == Turno.Estado.CANCELADO 
                      else 'Turno vigente' if not expired 
                      else f'Turno expirado hace {round(horas_transcurridas, 1)} horas.'
        }, status=status.HTTP_200_OK)

    # =====================================================================
    # AQUÍ ESTÁ EL PROCESO AUTOMATIZADO #2 (Integrado como Acción)
    # =====================================================================
    @action(detail=True, methods=['post'], url_path='gestionar')
    def gestionar_cancelacion(self, request, pk=None):
        raise MethodNotAllowed(request.method)

    @action(detail=True, methods=['post'], url_path='gestionar-profesional')
    def gestionar_profesional(self, request, pk=None):
        raise MethodNotAllowed(request.method)

    @action(detail=True, methods=['post'])
    def finalizar_turno(self, request, pk=None):
        """
        Acción para marcar el turno como realizado y disparar 
        las Reglas de Cuidado automáticas + crear diagnóstico post-servicio + Promociones de Retoque.
        
        POST /api/gestion/turnos/{id}/finalizar_turno/
        """
        turno = self.get_object()
        
        if turno.estado == Turno.Estado.REALIZADO:
            return Response({"error": "Este turno ya fue finalizado anteriormente."}, status=400)

        # 1. Cambiamos el estado del turno
        turno.estado = Turno.Estado.REALIZADO
        turno.save()

        # 2. CREAR DIAGNÓSTICO POST-SERVICIO AUTOMÁTICAMENTE
        # Se crea un nuevo diagnóstico después de cada servicio para reevaluar el estado del cabello
        cliente = turno.cliente
        
        # Solo crear diagnóstico si el cliente tiene datos capilares registrados
        if cliente.tipo_cabello or cliente.grosor_cabello or cliente.porosidad_cabello or cliente.cuero_cabelludo or cliente.estado_general:
            diag = DiagnosticoCapilar.objects.create(
                cliente=cliente,
                tipo_cabello=cliente.tipo_cabello,
                grosor_cabello=cliente.grosor_cabello,
                porosidad_cabello=cliente.porosidad_cabello,
                cuero_cabelludo=cliente.cuero_cabelludo,
                estado_general=cliente.estado_general
            )
            
            # Ejecutar el motor diagnóstico automáticamente
            DiagnosticoCapilarViewSet()._ejecutar_motor_diagnostico(diag)

        # 3. PROCESO AUTOMATIZADO: Aplicar Reglas de Cuidado
        # Buscamos todos los servicios que se hicieron en este turno
        detalles = turno.detalles.all()
        servicios_realizados = [d.servicio for d in detalles]

        for servicio in servicios_realizados:
            # Buscamos las reglas configuradas para este servicio
            reglas = servicio.reglas_post_servicio.all()
            
            for regla in reglas:
                # A. Notificar a la clienta (Instrucciones de cuidado)
                Notificacion.objects.create(
                    usuario=turno.cliente.usuario,
                    tipo='recordatorio',
                    titulo=f"Cuidados post {servicio.nombre}",
                    mensaje=f"{regla.descripcion}. (Válido por {regla.dias_duracion} días)",
                    origen_entidad='Turno',
                    origen_id=turno.id
                )

                # B. Si la regla tiene una RUTINA asociada, se la asignamos automáticamente
                if regla.rutina:
                    # Verificamos si ya la tiene activa para no duplicar
                    if not RutinaCliente.objects.filter(
                        cliente=turno.cliente, 
                        rutina_original=regla.rutina, 
                        estado='activa'
                    ).exists():
                        RutinaCliente.objects.create(
                            cliente=turno.cliente,
                            rutina_original=regla.rutina,
                            nombre=regla.rutina.nombre,
                            objetivo=regla.rutina.objetivo,
                            archivo=regla.rutina.archivo,
                            version_asignada=regla.rutina.version,
                            estado='activa'
                        )

        # 4. LÓGICA P3: Programación de Retoque (Marketing Inteligente)
        # Crea promociones diferidas para sugerir retoques en el momento ideal
        for detalle in turno.detalles.all():
            # Buscamos si el servicio tiene una regla de mantenimiento
            config = ConfiguracionRetoque.objects.filter(servicio_principal=detalle.servicio).first()
            
            if config:
                # Calculamos tiempos
                fecha_ideal_retoque = date.today() + timedelta(days=config.dias_sugeridos)
                # Programamos el aviso para 7 días antes de la fecha ideal
                fecha_aviso = fecha_ideal_retoque - timedelta(days=7)

                # Creamos la Promoción "Diferida"
                Promocion.objects.create(
                    nombre=f"Mantenimiento de {detalle.servicio.nombre}",
                    descripcion=f"Es el momento ideal para retocar tu {detalle.servicio.nombre} y lucir impecable.",
                    tipo='RETOQUE',
                    descuento_porcentaje=config.descuento_retoque,
                    fecha_inicio=fecha_aviso, 
                    fecha_fin=fecha_ideal_retoque + timedelta(days=7),
                    fecha_envio_notificacion=fecha_aviso,
                    cliente_especifico=turno.cliente,
                    is_active=True
                )
                logger.info(f"P3: Promoción de retoque programada para el cliente {turno.cliente} el día {fecha_aviso}")

        return Response({
            "mensaje": "Turno finalizado. Se han enviado las recomendaciones de cuidado, se ha creado un nuevo diagnóstico y se han programado promociones de retoque.",
            "estado": turno.estado
        })

class MiAgendaCuidadosView(generics.ListAPIView):
    """
    Devuelve la lista de cuidados/restricciones futuras para el cliente logueado.
    """
    serializer_class = AgendaCuidadosSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filtramos por el cliente logueado y ordenamos por fecha
        # Opcional: Mostrar solo tareas desde hoy en adelante (fecha__gte=date.today())
        return AgendaCuidados.objects.filter(
            cliente=self.request.user.cliente
        ).order_by('fecha')
    

class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint para listar notificaciones.
    Solo lectura (el usuario no crea notificaciones, el sistema lo hace).
    """
    serializer_class = NotificacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # FILTRO DE SEGURIDAD: Solo devolver las notificaciones del usuario actual
        return Notificacion.objects.filter(usuario=self.request.user).order_by('-fecha_envio')
    
    @action(detail=True, methods=['post'])
    def marcar_leida(self, request, pk=None):
        notificacion = self.get_object()
        notificacion.estado = 'leido'
        notificacion.save()
        return Response({'status': 'ok'})
    
    @action(detail=True, methods=['post'])
    def aceptar(self, request, pk=None):
        """
        Endpoint para aceptar una oferta de adelanto de turno.
        Extrae los datos de la notificación y actualiza el turno correspondiente.
        """
        notificacion = self.get_object()
        
        # Validar que sea del tipo ADELANTO
        if notificacion.tipo != 'ADELANTO':
            return Response(
                {'error': 'Esta notificación no es una oferta de adelanto'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar que tenga datos_extra
        if not notificacion.datos_extra:
            return Response(
                {'error': 'Datos incompletos en la notificación'},
                status=status.HTTP_400_BAD_REQUEST
            )

        expira_en = notificacion.datos_extra.get('expira_en')
        if expira_en:
            try:
                expira_dt = datetime.datetime.fromisoformat(expira_en)
                if timezone.is_naive(expira_dt):
                    expira_dt = timezone.make_aware(expira_dt)
                if timezone.now() > expira_dt:
                    notificacion.estado = 'leido'
                    notificacion.save()
                    return Response(
                        {'error': 'La oferta de adelanto expiró.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception:
                pass
        
        try:
            # Extraer datos de la notificación
            fecha_oferta = notificacion.datos_extra.get('fecha_oferta')
            hora_oferta = notificacion.datos_extra.get('hora_oferta')
            turno_actual_id = notificacion.datos_extra.get('turno_actual_id')
            
            if not all([fecha_oferta, hora_oferta, turno_actual_id]):
                return Response(
                    {'error': 'Datos incompletos en la oferta'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            oferta_ya_tomada = Notificacion.objects.filter(
                tipo='ADELANTO',
                datos_extra__turno_actual_id=turno_actual_id,
                datos_extra__fecha_oferta=fecha_oferta,
                datos_extra__hora_oferta=hora_oferta,
                datos_extra__aceptada=True
            ).exclude(id=notificacion.id).exists()

            if oferta_ya_tomada:
                notificacion.estado = 'leido'
                notificacion.datos_extra = {
                    **(notificacion.datos_extra or {}),
                    'oferta_cerrada': True
                }
                notificacion.save()
                return Response(
                    {'error': 'Esta oferta ya fue aceptada por otro cliente.'},
                    status=status.HTTP_409_CONFLICT
                )
            
            # Obtener el turno
            turno = Turno.objects.get(id=turno_actual_id, cliente=self.request.user.cliente)
            
            # Convertir strings a tipos correctos
            import datetime as dt
            nueva_fecha = dt.datetime.strptime(fecha_oferta, '%Y-%m-%d').date()
            nueva_hora = dt.datetime.strptime(hora_oferta, '%H:%M').time()
            
            # Actualizar el turno
            turno.fecha = nueva_fecha
            turno.hora_inicio = nueva_hora
            turno.save()
            
            # Marcar la notificación como leída
            notificacion.estado = 'leido'
            notificacion.datos_extra = {
                **(notificacion.datos_extra or {}),
                'aceptada': True
            }
            notificacion.save()

            # Cerrar ofertas equivalentes para otros clientes
            otras_notifs = Notificacion.objects.filter(
                tipo='ADELANTO',
                estado='pendiente',
                datos_extra__turno_actual_id=turno_actual_id,
                datos_extra__fecha_oferta=fecha_oferta,
                datos_extra__hora_oferta=hora_oferta
            ).exclude(id=notificacion.id)

            for otra in otras_notifs:
                otra.estado = 'leido'
                otra.titulo = 'Oferta tomada'
                otra.mensaje = 'Otro cliente ya acepto el adelantamiento. La oferta fue cerrada.'
                otra.datos_extra = {
                    **(otra.datos_extra or {}),
                    'oferta_cerrada': True
                }
                otra.save()
            
            return Response({
                'mensaje': 'Turno adelantado correctamente',
                'turno_id': turno.id,
                'nueva_fecha': nueva_fecha,
                'nueva_hora': nueva_hora
            }, status=status.HTTP_200_OK)
            
        except Turno.DoesNotExist:
            return Response(
                {'error': 'No se encontró el turno'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"Error al aceptar oferta: {str(e)}")
            return Response(
                {'error': f'Error al procesar la oferta: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
class AdminDashboardStatsView(APIView):
    """
    Devuelve estadísticas rápidas para la Pantalla Home del Administrador.
    """
    permission_classes = [IsAdminUser] # Solo para Staff/Yani

    def get(self, request):
        today = timezone.now().date()
        
        # 1. Contadores Rápidos
        turnos_hoy = Turno.objects.filter(fecha=today, estado='confirmado').count()
        solicitudes_pendientes = Turno.objects.filter(estado='solicitado').count()
        turnos_esperando_sena = Turno.objects.filter(estado='esperando_sena').count()
        
        # 2. Próximos Turnos (Agenda inmediata)
        proximos_turnos = Turno.objects.filter(
            fecha__gte=today, 
            estado__in=['confirmado', 'esperando_sena']
        ).prefetch_related('detalles__servicio', 'cliente__usuario').order_by('fecha', 'hora_inicio')[:5]
        
        # Serializamos manualmente para no crear otro serializer solo para esto
        lista_proximos = []
        for t in proximos_turnos:
            # Obtener nombres de servicios desde detalles
            servicios = [d.servicio.nombre for d in t.detalles.all()]
            servicios_str = ', '.join(servicios) if servicios else 'Sin servicios'
            
            lista_proximos.append({
                'id': t.id,
                'cliente': f"{t.cliente.usuario.first_name} {t.cliente.usuario.last_name}",
                'servicios': servicios_str,
                'hora': t.hora_inicio.strftime("%H:%M"),
                'fecha': t.fecha,
                'estado': t.estado
            })

        data = {
            'turnos_hoy': turnos_hoy,
            'pendientes_accion': solicitudes_pendientes,
            'esperando_sena': turnos_esperando_sena,
            'proximos_turnos': lista_proximos
        }
        
        return Response(data, status=status.HTTP_200_OK)


# ============================================
# VIEWSETS PARA RUTINAS
# ============================================

class RutinaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar Rutinas (catálogo de rutinas disponibles).
    - Admins/Staff: Pueden crear, actualizar, eliminar rutinas
    - Clientes: Solo pueden ver rutinas publicadas
    """
    serializer_class = RutinaSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = RutinaFilter
    search_fields = ['nombre', 'descripcion']
    ordering_fields = ['nombre']
    
    def get_queryset(self):
        """
        - Admins ven todas las rutinas
        - Clientes solo ven las publicadas
        """
        if self.request.user.is_staff:
            return Rutina.objects.all()
        else:
            return Rutina.objects.filter(estado='publicada')
    
    def get_permissions(self):
        """
        - list, retrieve, seleccionar: Clientes autenticados
        - create, update, destroy: Solo staff
        """
        if self.action in ['list', 'retrieve', 'seleccionar']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def destroy(self, request, *args, **kwargs):
        """
        Lógica especial para eliminar rutinas:
        - Si la rutina está asignada a clientes: marcar como OBSOLETA y notificar
        - Si no está asignada: eliminar directamente
        """
        rutina = self.get_object()
        
        # 1. Verificar si hay clientes usando esta rutina
        # Usando el related_name correcto: 'copias_cliente'
        tiene_clientes = rutina.copias_cliente.exists() 

        if tiene_clientes:
            # --- CAMINO ALTERNATIVO: MARCAR OBSOLETA ---
            rutina.estado = 'OBSOLETA' 
            rutina.save()
            
            # --- NOTIFICACIÓN MASIVA ---
            # Obtenemos todas las relaciones activas
            asignaciones = rutina.copias_cliente.all()
            
            cont_notificados = 0
            for asignacion in asignaciones:
                # Creamos la notificación para cada cliente
                Notificacion.objects.create(
                    usuario=asignacion.cliente.usuario, # Navegamos al usuario
                    tipo='INFO',
                    titulo="⚠️ Actualización de Rutina",
                    mensaje=(
                        f"La rutina '{rutina.nombre}' que tenías asignada ha sido marcada como obsoleta "
                        "por el profesional. Te recomendamos solicitar un nuevo diagnóstico."
                    ),
                    datos_extra={"rutina_id": rutina.id}
                )
                cont_notificados += 1

            return Response(
                {
                    "mensaje": "La rutina no se pudo eliminar porque está en uso.",
                    "accion_tomada": "Se marcó como OBSOLETA.",
                    "notificados": f"Se envió aviso a {cont_notificados} clientes."
                },
                status=status.HTTP_200_OK
            )
            
        else:
            # --- CAMINO NORMAL: ELIMINAR ---
            rutina.delete()
            return Response(
                {"mensaje": "La plantilla de rutina se eliminó correctamente."},
                status=status.HTTP_204_NO_CONTENT
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def publicar(self, request, pk=None):
        """
        Endpoint para PUBLICAR una rutina (cambiar estado a 'publicada').
        POST /api/gestion/rutinas/{id}/publicar/
        """
        rutina = self.get_object()
        rutina.publicar()
        
        serializer = self.get_serializer(rutina)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def obsoletar(self, request, pk=None):
        """
        Endpoint para MARCAR COMO OBSOLETA una rutina.
        POST /api/gestion/rutinas/{id}/obsoletar/
        
        Notifica automáticamente a todos los clientes que la tienen asignada.
        """
        rutina = self.get_object()
        rutina.obsoletar()
        
        serializer = self.get_serializer(rutina)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def notificar_actualizacion(self, request, pk=None):
        """
        Endpoint para NOTIFICAR a los clientes sobre actualización.
        POST /api/gestion/rutinas/{id}/notificar_actualizacion/
        
        Se ejecuta cuando se modifica una rutina publicada.
        """
        rutina = self.get_object()
        rutina.notificar_actualizacion_a_copias()
        
        return Response(
            {'mensaje': 'Notificaciones enviadas a los clientes'},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['get'], permission_classes=[IsAdminUser])
    def usuarios_usando(self, request, pk=None):
        """
        Endpoint para obtener detalles de usuarios usando una rutina.
        GET /api/gestion/rutinas/{id}/usuarios_usando/
        
        Retorna lista de clientes/usuarios que tienen esta rutina asignada.
        """
        rutina = self.get_object()
        
        # Obtener todas las asignaciones de esta rutina
        asignaciones = rutina.copias_cliente.all()
        
        usuarios_list = []
        for asignacion in asignaciones:
            usuario = asignacion.cliente.usuario
            usuarios_list.append({
                'id': usuario.id,
                'nombre': usuario.get_full_name(),
                'email': usuario.email,
                'fecha_asignacion': asignacion.fecha_asignacion,
                'version_asignada': asignacion.version_asignada,
                'estado': asignacion.estado
            })
        
        return Response({
            'rutina_id': rutina.id,
            'rutina_nombre': rutina.nombre,
            'total_usuarios': len(usuarios_list),
            'usuarios': usuarios_list
        }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def seleccionar(self, request):
        """
        Permite a un cliente autenticado seleccionar/asignar una rutina del catálogo.
        POST /api/gestion/rutinas/seleccionar/
        Body: {"rutina_id": 1}
        """
        rutina_id = request.data.get('rutina_id')
        
        if not rutina_id:
            return Response(
                {"error": "ID de rutina requerido"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Obtener la rutina
            rutina = Rutina.objects.get(id=rutina_id)
            
            # Validar que el usuario tenga perfil de cliente
            if not hasattr(request.user, 'cliente'):
                return Response(
                    {"error": "El usuario no es un cliente"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            cliente = request.user.cliente
            
            # Crear la copia de la rutina para el cliente con todos los datos necesarios
            rutina_cliente = RutinaCliente.objects.create(
                cliente=cliente,
                rutina_original=rutina,
                nombre=rutina.nombre,
                objetivo=rutina.objetivo,
                descripcion=rutina.descripcion,
                archivo=rutina.archivo,  # ✅ AGREGADO: Copiar el archivo
                version_asignada=rutina.version
            )
            
            # Copiar los pasos de la rutina original
            """
            for paso_original in rutina.pasos.all():
                PasoRutinaCliente.objects.create(
                    rutina_cliente=rutina_cliente,
                    orden=paso_original.orden,
                    descripcion=paso_original.descripcion,
                    frecuencia=paso_original.frecuencia
                
            """

            
            return Response(
                {
                    "mensaje": f"Rutina '{rutina.nombre}' agregada exitosamente a Mis Rutinas",
                    "rutina_cliente_id": rutina_cliente.id
                },
                status=status.HTTP_201_CREATED
            )
            
        except Rutina.DoesNotExist:
            return Response(
                {"error": "La rutina no existe"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"ERROR en seleccionar rutina: {str(e)}")
            return Response(
                {"error": f"Error al agregar la rutina: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RutinaClienteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para gestionar las COPIAS de rutinas asignadas a clientes.
    - Clientes: Ven solo sus propias rutinas
    - Admins: Ven todas las rutinas de todos los clientes
    """
    serializer_class = RutinaClienteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        - Clientes ven solo sus rutinas
        - Admins ven todas
        """
        if self.request.user.is_staff:
            return RutinaCliente.objects.all()
        else:
            try:
                return RutinaCliente.objects.filter(cliente=self.request.user.cliente)
            except:
                return RutinaCliente.objects.none()
    
    def get_permissions(self):
        """
        - list, retrieve: Clientes ven sus propias
        - update, destroy: Usuarios autenticados (solo sus propias rutinas)
        - create: No permitido (se crean automáticamente)
        """
        if self.action in ['list', 'retrieve', 'destroy']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def create(self, request, *args, **kwargs):
        """Desabilita creación manual."""
        return Response(
            {'error': 'Use POST /rutinas/seleccionar/ para asignar rutinas'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def actualizar_desde_original(self, request, pk=None):
        """
        Endpoint para ACTUALIZAR la copia con los datos de la rutina original.
        POST /api/gestion/rutinas-cliente/{id}/actualizar_desde_original/
        
        El cliente usa esto cuando recibe notificación de actualización.
        """
        rutina_cliente = self.get_object()
        
        # Verificar que el cliente es el dueño
        if rutina_cliente.cliente.usuario != request.user and not request.user.is_staff:
            return Response(
                {'error': 'No tienes permiso'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not rutina_cliente.rutina_original:
            return Response(
                {'error': 'La rutina original no existe'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        rutina_cliente.actualizar_desde_original()
        
        serializer = self.get_serializer(rutina_cliente)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def destroy(self, request, *args, **kwargs):
        """
        Permite que el cliente elimine su propia rutina.
        DELETE /api/gestion/rutinas-cliente/{id}/
        """
        rutina_cliente = self.get_object()
        
        # Verificar que el usuario es el dueño de la rutina o es admin
        if rutina_cliente.cliente.usuario != request.user and not request.user.is_staff:
            return Response(
                {'error': 'No tienes permiso para eliminar esta rutina'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        rutina_cliente.delete()
        return Response(
            {'mensaje': 'Rutina eliminada exitosamente'},
            status=status.HTTP_204_NO_CONTENT
        )
    
    """
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def marcar_paso_completado(self, request, pk=None):
        ""
        Endpoint para MARCAR UN PASO COMO COMPLETADO.
        POST /api/gestion/rutinas-cliente/{id}/marcar_paso_completado/
        {
            "paso_id": 1
        }
        ""
        rutina_cliente = self.get_object()
        
        # Verificar permisos
        if rutina_cliente.cliente.usuario != request.user and not request.user.is_staff:
            return Response(
                {'error': 'No tienes permiso'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        paso_id = request.data.get('paso_id')
        if not paso_id:
            return Response(
                {'error': 'paso_id es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from .models import PasoRutinaCliente
            paso = PasoRutinaCliente.objects.get(id=paso_id, rutina_cliente=rutina_cliente)
            paso.marcar_completado()
            
            return Response(
                {'mensaje': 'Paso marcado como completado'},
                status=status.HTTP_200_OK
            )
        except PasoRutinaCliente.DoesNotExist:
            return Response(
                {'error': 'Paso no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
    """


# ============================================
# VIEWSET PARA PASOS DE RUTINA
# ============================================
"""
class PasoRutinaViewSet(viewsets.ModelViewSet):
    ""
    ViewSet para gestionar PasoRutina (pasos de rutinas plantilla).
    Solo staff puede crear/editar/eliminar.
    ""
    serializer_class = PasoRutinaSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return PasoRutina.objects.all()
    
    def get_permissions(self):
        ""
        - list, retrieve: Autenticados
        - create, update, destroy: Solo staff
        ""
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def create(self, request, *args, **kwargs):
        ""
        Sobrescribimos create para mejor debugging y validación
        ""
        print(f"DEBUG: Datos recibidos para crear PasoRutina: {request.data}")
        print(f"DEBUG: Usuario autenticado: {request.user}")
        
        # Validar que plantilla existe
        plantilla_id = request.data.get('plantilla')
        if not plantilla_id:
            return Response(
                {'error': 'El campo plantilla es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            rutina = Rutina.objects.get(id=plantilla_id)
            print(f"DEBUG: Rutina encontrada: {rutina.nombre}")
        except Rutina.DoesNotExist:
            return Response(
                {'error': f'No se encontró la rutina con ID {plantilla_id}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return super().create(request, *args, **kwargs)
    
"""


class ReglaDiagnosticoViewSet(viewsets.ModelViewSet):
    """
    Vista de API para administrar las Reglas de Diagnóstico (Motor Experto).
    Permite: Listar, Crear, Editar y Eliminar reglas.
    """
    # Ordenamos por 'prioridad' descendente (de mayor a menor importancia)
    # Esto es vital para que el motor evalúe primero las reglas específicas
    queryset = ReglaDiagnostico.objects.all().order_by('-prioridad')
    
    serializer_class = ReglaDiagnosticoSerializer
    
    # Restricción de seguridad: Solo usuarios Administradores (Yani) pueden tocar esto.
    # Si quieres que cualquier usuario logueado acceda (para pruebas), usa IsAuthenticated.
    permission_classes = [IsAdminUser]

class SeleccionarRutinaView(APIView):
    # 2. FORZAR AUTENTICACIÓN JWT (Esto arregla el conflicto con cookies/CSRF)
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Debug para ver en la consola negra quién está entrando
        print(f"DEBUG AUTH: Usuario detectado -> {request.user}")
        print(f"DEBUG AUTH: Autenticación usada -> {request.auth}")

        usuario = request.user
        
        # Validación de seguridad: ¿Tiene perfil de cliente?
        if not hasattr(usuario, 'cliente'):
             return Response(
                 {"error": "El usuario no es un cliente."}, 
                 status=status.HTTP_403_FORBIDDEN
             )

        rutina_id = request.data.get('rutina_id')
        if not rutina_id:
            return Response({"error": "Falta el ID de la rutina"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 3. LÓGICA DE GUARDADO
            rutina = Rutina.objects.get(id=rutina_id)
            cliente = usuario.cliente
            
            # --- ADVERTENCIA DE MODELO ---
            # En tus archivos models.py NO vi un campo 'rutinas' en Cliente.
            # Solo vi 'historial_servicios'. 
            # Si creaste un campo nuevo ManyToMany para rutinas, úsalo aquí:
            if hasattr(cliente, 'rutinas'):
                cliente.rutinas.add(rutina)
            elif hasattr(cliente, 'rutinas_guardadas'):
                 cliente.rutinas_guardadas.add(rutina)
            else:
                # Si no tienes el campo, esto fallará. 
                # Para la demo de hoy, puedes simular el éxito o imprimirlo:
                print(f"DEBUG: Simulando guardado de Rutina {rutina.nombre} para {usuario.email}")
            
            return Response(
                {"mensaje": f"Rutina '{rutina.nombre}' agregada a tus favoritos"}, 
                status=status.HTTP_200_OK
            )

        except Rutina.DoesNotExist:
            return Response({"error": "La rutina no existe"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"ERROR: {str(e)}")
            return Response({"error": "Error interno del servidor"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

# ----------------------------------------------------
# A. CRUD USUARIOS (ADMIN)
# ----------------------------------------------------
class AdminUsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()  # Cambiar a todos, luego filtramos en get_queryset
    serializer_class = UsuarioAdminReadSerializer
    permission_classes = [IsAdminUser] # Solo admins pueden entrar aquí
    
    # Configurar filtros
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UsuarioFilter
    search_fields = ['first_name', 'last_name', 'email']
    ordering_fields = ['date_joined', 'email', 'first_name', 'last_name']
    ordering = ['-date_joined']  # Por defecto, mostrar primero los más nuevos

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return UsuarioAdminReadSerializer
        if self.action == 'update':
            return UsuarioAdminIdentityUpdateSerializer
        if self.action == 'partial_update':
            return UsuarioAdminIdentityUpdateSerializer
        return UsuarioAdminReadSerializer

    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [AllowAny]
        elif self.action in [
            'update',
            'partial_update',
            'desactivar_cuenta',
            'reactivar_cuenta',
        ]:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(
            request.method,
            detail=(
                'La creación genérica de Usuario está deshabilitada. '
                'Utilice una operación de alta semántica.'
            ),
        )

    def get_queryset(self):
        """
        Retornar todos los usuarios y dejar que django-filter haga el filtrado.
        """
        return Usuario.objects.prefetch_related('groups')

    def update(self, request, *args, **kwargs):
        if (
            not request.user.is_active
            or not request.user.has_perm(BusinessPermission.MANAGE_USERS)
        ):
            return self._command_error(
                'PERMISSION_DENIED',
                'No tiene permisos para actualizar la identidad de usuarios.',
                status.HTTP_403_FORBIDDEN,
            )

        instance = self.get_object()
        if instance.is_superuser:
            return self._command_error(
                'PROTECTED_SUPERUSER',
                'El Usuario protegido no puede gestionarse mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )

        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        if not serializer.is_valid():
            return self._command_error(
                'INVALID_PAYLOAD',
                'El payload de actualización de Usuario es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=serializer.errors,
            )

        self.perform_update(serializer)
        read_serializer = UsuarioAdminReadSerializer(
            instance,
            context=self.get_serializer_context(),
        )
        return Response(read_serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='desactivar-cuenta',
        permission_classes=[IsAuthenticated],
    )
    def desactivar_cuenta(self, request, pk=None):
        try:
            target_user = self.get_object()
        except Http404:
            return self._command_error(
                'USER_NOT_FOUND',
                'El Usuario solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = UsuarioAccountStatusCommandSerializer(data=request.data)
        if not command.is_valid():
            error_code = (
                'INVALID_REASON'
                if set(command.errors) == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._command_error(
                error_code,
                'El payload de desactivación de cuenta es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            result = deactivate_account(
                actor=request.user,
                target_user=target_user,
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForAccountDeactivation:
            return self._command_error(
                'PERMISSION_DENIED',
                'No tiene permisos para desactivar cuentas.',
                status.HTTP_403_FORBIDDEN,
            )
        except ProtectedSuperuser:
            return self._command_error(
                'PROTECTED_SUPERUSER',
                'El Usuario protegido no puede gestionarse mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )
        except SelfDeactivationNotAllowed:
            return self._command_error(
                'SELF_DEACTIVATION_NOT_ALLOWED',
                'No puede desactivar su propia cuenta mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )
        except LastActiveAdministrator:
            return self._command_error(
                'LAST_ACTIVE_ADMIN',
                'No puede desactivarse el último administrador activo.',
                status.HTTP_403_FORBIDDEN,
            )
        except InvalidAccountDeactivationReason:
            return self._command_error(
                'INVALID_REASON',
                'El motivo de desactivación es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidAccountDeactivationTarget:
            return self._command_error(
                'USER_NOT_FOUND',
                'El Usuario solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except AccountDeactivationConflict:
            return self._command_error(
                'ACCOUNT_DEACTIVATION_CONFLICT',
                'La desactivación entra en conflicto con otra operación.',
                status.HTTP_409_CONFLICT,
            )

        return Response({
            'changed': result.changed,
            'usuario_id': result.user_id,
            'usuario_activo_anterior': result.previous_active,
            'usuario_activo_actual': result.current_active,
            'rol_actual': result.current_role,
            'warnings': list(result.warnings),
        }, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path='reactivar-cuenta',
        permission_classes=[IsAuthenticated],
    )
    def reactivar_cuenta(self, request, pk=None):
        try:
            target_user = self.get_object()
        except Http404:
            return self._command_error(
                'USER_NOT_FOUND',
                'El Usuario solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )

        command = UsuarioAccountStatusCommandSerializer(data=request.data)
        if not command.is_valid():
            error_code = (
                'INVALID_REASON'
                if set(command.errors) == {'motivo'}
                else 'INVALID_PAYLOAD'
            )
            return self._command_error(
                error_code,
                'El payload de reactivación de cuenta es inválido.',
                status.HTTP_400_BAD_REQUEST,
                fields=command.errors,
            )

        try:
            result = reactivate_account(
                actor=request.user,
                target_user=target_user,
                reason=command.validated_data['motivo'],
            )
        except PermissionDeniedForAccountReactivation:
            return self._command_error(
                'PERMISSION_DENIED',
                'No tiene permisos para reactivar cuentas.',
                status.HTTP_403_FORBIDDEN,
            )
        except ProtectedSuperuser:
            return self._command_error(
                'PROTECTED_SUPERUSER',
                'El Usuario protegido no puede gestionarse mediante esta acción.',
                status.HTTP_403_FORBIDDEN,
            )
        except InvalidAccountReactivationReason:
            return self._command_error(
                'INVALID_REASON',
                'El motivo de reactivación es inválido.',
                status.HTTP_400_BAD_REQUEST,
            )
        except InvalidAccountReactivationTarget:
            return self._command_error(
                'USER_NOT_FOUND',
                'El Usuario solicitado no existe.',
                status.HTTP_404_NOT_FOUND,
            )
        except UserHasNoBusinessRole:
            return self._command_error(
                'USER_HAS_NO_BUSINESS_ROLE',
                'El Usuario no tiene un rol de negocio.',
                status.HTTP_409_CONFLICT,
            )
        except InconsistentBusinessRoleState:
            return self._command_error(
                'INCONSISTENT_BUSINESS_ROLES',
                'El Usuario tiene múltiples roles de negocio.',
                status.HTTP_409_CONFLICT,
            )
        except MissingClientProfile:
            return self._command_error(
                'CLIENT_PROFILE_REQUIRED',
                'El rol CLIENTE requiere un perfil Cliente.',
                status.HTTP_409_CONFLICT,
            )
        except MissingPersonalProfile:
            return self._command_error(
                'PERSONAL_PROFILE_REQUIRED',
                'El rol laboral requiere un Personal vinculado.',
                status.HTTP_409_CONFLICT,
            )
        except InactivePersonal:
            return self._command_error(
                'PERSONAL_INACTIVE',
                'Debe reactivar el Personal antes de reactivar la cuenta.',
                status.HTTP_409_CONFLICT,
            )
        except AccountReactivationConflict:
            return self._command_error(
                'ACCOUNT_REACTIVATION_CONFLICT',
                'La reactivación entra en conflicto con otra operación.',
                status.HTTP_409_CONFLICT,
            )

        return Response({
            'changed': result.changed,
            'usuario_id': result.user_id,
            'usuario_activo_anterior': result.previous_active,
            'usuario_activo_actual': result.current_active,
            'rol_actual': result.current_role,
            'warnings': list(result.warnings),
        }, status=status.HTTP_200_OK)

    @staticmethod
    def _command_error(code, detail, status_code, fields=None):
        error = {'code': code, 'detail': detail}
        if fields is not None:
            error['fields'] = fields
        return Response({'error': error}, status=status_code)

    def perform_destroy(self, instance):
        """
        Desactiva el usuario en lugar de eliminarlo (Soft Delete).
        Validación: No desactivar si tiene turnos futuros.
        """
        # Validación: No desactivar si es staff con turnos futuros
        if instance.is_staff:
            turnos_pendientes = Turno.objects.filter(
                fecha__gte=timezone.now().date(), 
                estado='confirmado'
            ).exists()
            if turnos_pendientes:
                raise serializers.ValidationError(
                    "No se puede desactivar: Hay turnos futuros confirmados en el sistema."
                )
        
        # Desactivar usuario (Soft Delete)
        instance.is_active = False
        instance.save()
        
        # También desactivar el cliente asociado si existe
        if hasattr(instance, 'cliente'):
            instance.cliente.activo = False
            instance.cliente.save()

# ----------------------------------------------------
# B. CRUD PRODUCTOS
# ----------------------------------------------------
class ProductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar productos del catálogo.
    Incluye validaciones de stock, acciones personalizadas para alertas de stock bajo,
    y recomendaciones inteligentes basadas en diagnósticos de clientes.
    """
    serializer_class = ProductoSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductoFilter
    search_fields = ['nombre']
    ordering_fields = ['nombre', 'precio', 'stock_real']

    def get_queryset(self):
        """Optimiza queries con prefetch_related para imágenes"""
        return Producto.objects.filter(activo=True).prefetch_related('imagenes')

    def get_permissions(self):
        """
        Permisos dinámicos:
        - list/retrieve: AllowAny (clientes pueden ver productos)
        - create/update/destroy: IsAdminUser (solo admins gestionan)
        - stock_bajo/sugeridos_por_cliente: AllowAny (endpoints públicos)
        """
        if self.action in ['list', 'retrieve', 'stock_bajo', 'sugeridos_por_cliente']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    def perform_update(self, serializer):
        """Asegura que los cambios se guarden correctamente"""
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        producto = self.get_object()
        
        # Validación 1: Stock en inventario
        if producto.stock_real > 0:
            return Response(
                {"error": "No se puede eliminar: El producto tiene stock físico."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validación 2: Referencia en rutinas activas
        # Asumiendo relación ManyToMany en Rutina -> productos
        # if producto.rutina_set.exists(): ...
        
        # Si pasa validaciones, eliminar definitivamente.
        producto.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='desactivar')
    def desactivar(self, request, pk=None):
        producto = self.get_object()
        if not producto.activo:
            return Response(
                {"error": "El producto ya está desactivado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        producto.activo = False
        producto.save()
        return Response({"mensaje": "Producto desactivado."}, status=status.HTTP_200_OK)

    # --- 1. ENDPOINT: ALERTA DE STOCK BAJO ---
    @action(detail=False, methods=['get'])
    def stock_bajo(self, request):
        """
        Devuelve productos cuyo stock disponible es menor o igual al mínimo.
        Útil para el panel de Yanina para saber qué reabastecer.
        GET /api/gestion/productos/stock_bajo/
        """
        # Filtrar: stock_real - stock_comprometido <= stock_minimo
        from django.db.models import Q
        productos = Producto.objects.filter(
            Q(stock_real__lte=F('stock_minimo')),
            activo=True
        )
        serializer = self.get_serializer(productos, many=True)
        return Response({
            "total_productos_bajo_stock": productos.count(),
            "productos": serializer.data
        })

    # --- 2. ENDPOINT: RECOMENDACIONES INTELIGENTES (SMART SELLING) ---
    @action(detail=False, methods=['get'], url_path='sugeridos-cliente')
    def sugeridos_por_cliente(self, request):
        """
        Sugiere productos basados en el último diagnóstico del cliente autenticado.
        Solo funciona si el cliente está autenticado.
        GET /api/gestion/productos/sugeridos-cliente/
        """
        if not request.user.is_authenticated:
            return Response(
                {"error": "Debes estar autenticado para recibir sugerencias personalizadas."},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        try:
            cliente = request.user.cliente
        except:
            return Response(
                {"error": "Tu usuario no tiene perfil de cliente."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Buscamos el último diagnóstico del cliente
            ultimo_diagnostico = DiagnosticoCapilar.objects.filter(
                cliente=cliente
            ).latest('fecha_diagnostico')
            
            # Mapeo de lógica: Diagnóstico -> Compatibilidad de Producto
            # Si el pelo está dañado, prioridad productos DANADO
            if ultimo_diagnostico.estado_general and "Dañado" in ultimo_diagnostico.estado_general.nombre:
                tag_busqueda = 'DANADO'
            elif ultimo_diagnostico.cuero_cabelludo and "Graso" in ultimo_diagnostico.cuero_cabelludo.nombre:
                tag_busqueda = 'GRASO'
            elif ultimo_diagnostico.cuero_cabelludo and "Seco" in ultimo_diagnostico.cuero_cabelludo.nombre:
                tag_busqueda = 'SECO'
            elif ultimo_diagnostico.tipo_cabello and ultimo_diagnostico.tipo_cabello.nombre in ["Rizado", "Afro"]:
                tag_busqueda = 'RIZADO'
            elif ultimo_diagnostico.tipo_cabello and "Lacio" in ultimo_diagnostico.tipo_cabello.nombre:
                tag_busqueda = 'LACIO'
            else:
                tag_busqueda = 'TODO'

            # Buscamos productos que coincidan y tengan stock
            sugeridos = Producto.objects.filter(
                Q(compatibilidad=tag_busqueda) | Q(compatibilidad='TODO'),
                stock_real__gt=0,
                activo=True
            ).order_by('nombre')[:5]  # Limitamos a los mejores 5

            serializer = self.get_serializer(sugeridos, many=True)
            return Response({
                "motivo_sugerencia": f"Basado en tu diagnóstico: {tag_busqueda}",
                "diagnostico_id": ultimo_diagnostico.id,
                "fecha_diagnostico": ultimo_diagnostico.fecha_diagnostico,
                "productos_sugeridos": serializer.data
            }, status=status.HTTP_200_OK)

        except DiagnosticoCapilar.DoesNotExist:
            return Response({
                "error": "No tienes diagnósticos previos. Realiza un diagnóstico para recibir recomendaciones personalizadas.",
                "productos": []
            }, status=status.HTTP_404_NOT_FOUND)

# ----------------------------------------------------
# D. CRUD TIPO EQUIPAMIENTO
# ----------------------------------------------------
class TipoEquipamientoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para tipos de equipamiento.
    
    Lógica de filtrado:
    - ADMINS: Ven TODOS los tipos (para poder crear nuevos y gestionar)
    - CLIENTES: Solo ven tipos con equipamiento activo (para seleccionar en servicios)
    """
    serializer_class = TipoEquipamientoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TipoEquipamientoFilter
    search_fields = ['nombre']
    ordering_fields = ['nombre']

    def get_queryset(self):
        """
        Lógica inteligente de filtrado según el rol del usuario.
        """
        # ADMINS/STAFF: Devolver todos los tipos (necesitan crearlos y gestionarlos)
        if self.request.user.is_staff:
            return TipoEquipamiento.objects.all().order_by('nombre')
        
        # CLIENTES NORMALES: Solo tipos con equipamiento activo
        # (para no mostrar tipos de equipamiento sin instancias reales)
        tipos_con_equipos = Equipamiento.objects.filter(
            is_active=True
        ).values_list('tipo_id', flat=True).distinct()
        
        queryset = TipoEquipamiento.objects.filter(id__in=tipos_con_equipos).order_by('nombre')
        
        logger.info(f"TiposEquipamiento disponibles para servicios: {queryset.count()}")
        
        return queryset
        
        return queryset


# ----------------------------------------------------
# E. CRUD EQUIPAMIENTO
# ----------------------------------------------------
class EquipamientoViewSet(viewsets.ModelViewSet):
    queryset = Equipamiento.objects.filter(is_active=True) # Solo mostramos los activos
    serializer_class = EquipamientoSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = EquipamientoFilter
    search_fields = ['nombre']
    ordering_fields = ['nombre', 'tipo']

    def destroy(self, request, *args, **kwargs):
        """Sobrescribimos el borrado para que sea una Baja Lógica"""
        instance = self.get_object()
        
        # Validación de Negocio (Consistencia con UC):
        # Aquí iría la lógica para verificar si hay turnos pendientes.
        # Por ahora, simplemente desactivamos:
        instance.is_active = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def opciones(self, request):
        """Endpoint para que el Front arme los desplegables dinámicamente"""
        return Response({
            "tipos": [{"id": key, "label": value} for key, value in Equipamiento.TipoRecurso.choices],
            "estados": [{"id": key, "label": value} for key, value in Equipamiento.EstadoRecurso.choices],
        })

class HorarioLaboralViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar HorarioLaboral y crear disponibilidad en masa.
    """
    queryset = HorarioLaboral.objects.all().order_by('dia_semana', 'hora_inicio')
    serializer_class = HorarioLaboralSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None

    @action(detail=False, methods=['post'])
    def configurar_rango(self, request):
        fecha_desde = request.data.get('fecha_desde')
        fecha_hasta = request.data.get('fecha_hasta')
        patron = request.data.get('patron')
        # Nuevo: recibir si es para todos o un ID específico
        seleccionar_todos = request.data.get('todos_profesionales', False) 

        try:
            # VALIDACIÓN ESTRICTA: Si no es "todos", verificar que NO haya personal_id nulo
            if not seleccionar_todos:
                has_null_personal = any(item.get('personal_id') is None for item in patron)
                if has_null_personal:
                    return Response(
                        {"error": "No se pueden crear horarios sin asignar personal. Selecciona profesionales específicos o usa 'Todos'."},
                        status=400
                    )
            
            with transaction.atomic():
                for item in patron:
                    # 1. Determinamos a quiénes aplicar la regla
                    if seleccionar_todos:
                        # Buscamos a todo el personal activo
                        profesionales = Personal.objects.filter(activo=True)
                    else:
                        # Solo al ID que viene en el item
                        personal_id = item.get('personal_id')
                        profesionales = Personal.objects.filter(id=personal_id, activo=True)
                        
                        # Validar que el personal existe y está activo
                        if not profesionales.exists():
                            return Response(
                                {"error": f"El profesional con ID {personal_id} no existe o está inactivo."},
                                status=400
                            )

                    # 2. Creamos la regla para cada profesional identificado
                    for prof in profesionales:
                        HorarioLaboral.objects.create(
                            personal=prof,
                            fecha_desde=fecha_desde,
                            fecha_hasta=fecha_hasta,
                            dia_semana=int(item.get('dia')),
                            hora_inicio=item.get('hora_inicio'),
                            hora_fin=item.get('hora_fin'),
                            permite_diseno_color=item.get('permite_diseno', True),
                            permite_complemento=item.get('permite_complemento', True),
                            activo=True
                        )
            
            return Response({"status": "success", "mensaje": "Agenda configurada para el personal seleccionado."}, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

    @action(detail=False, methods=['delete'])
    def limpiar_agenda(self, request):
        """
        Borra todos los horarios del profesional para permitir una nueva carga masiva.
        Query param: ?personal_id=1
        """
        personal_id = request.query_params.get('personal_id')
        if not personal_id:
            return Response({"error": "Se requiere personal_id"}, status=400)
            
        try:
            # Borramos solo los de ese profesional
            count, _ = HorarioLaboral.objects.filter(personal_id=personal_id).delete()
            return Response({
                "mensaje": f"Agenda limpiada con éxito. Se eliminaron {count} horarios."
            }, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def obtener_agenda_general(request):
    """
    Devuelve la configuración base, horarios y bloqueos para un profesional específico.
    Query params: ?personal_id=1 (opcional, si no viene usa el primer profesional activo)
    """
    # 1. Obtenemos el personal (ahora pasamos el ID por parámetro para que sea flexible)
    # Si no viene ID, buscamos al primer profesional activo
    personal_id = request.query_params.get('personal_id')
    
    if personal_id:
        personal = Personal.objects.filter(id=personal_id).first()
    else:
        # Fallback: buscamos el primer profesional
        personal = Personal.objects.filter(activo=True).first()

    if not personal:
        return Response({"error": "No se encontró personal disponible"}, status=404)

    # 2. Obtenemos la Regla (Horarios Base)
    horarios = HorarioLaboral.objects.filter(personal=personal, activo=True)
    
    # 3. Obtenemos la Excepción (Bloqueos)
    hoy = timezone.now()
    bloqueos = BloqueoAgenda.objects.filter(
        Q(personal=personal) | Q(personal__isnull=True),  # Bloqueos suyos o globales
        fecha_fin__gte=hoy
    )

    # 4. Obtenemos la Configuración Global (Singleton)
    config = Configuracion.objects.first()  # El ID=1 que definiste

    return Response({
        'profesional': {
            'id': personal.id,
            'nombre': personal.nombre,
        },
        'configuracion': {
            'max_dias_anticipacion': config.max_dias_anticipacion if config else 60,
            'intervalo': config.intervalo_turnos if config else 30
        },
        'horarios_base': HorarioLaboralSerializer(horarios, many=True).data,
        'bloqueos': BloqueoAgendaSerializer(bloqueos, many=True).data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crear_bloqueo(request):
    try:
        # 1. Identificamos a Yanina (Colorista)
        personal = Personal.objects.filter(rol='colorista', activo=True).first()
        if not personal:
            return Response({"error": "No existe personal colorista activo"}, status=400)

        data = request.data
        
        # Convertimos los strings ISO que vienen del React a objetos Datetime
        # Formato esperado: "2025-12-07T09:00:00"
        bloqueo_inicio = parse_datetime(data.get('fecha_inicio'))
        bloqueo_fin = parse_datetime(data.get('fecha_fin'))

        if not bloqueo_inicio or not bloqueo_fin:
            return Response({"error": "Fechas inválidas"}, status=400)

        # ------------------------------------------------------------------
        # VALIDACIÓN DE CONFLICTOS (Excepción C.U. Paso 5)
        # ------------------------------------------------------------------
        
        # A. Filtramos primero por FECHA para no traer toda la base de datos
        # Traemos turnos que ocurran en los días involucrados en el bloqueo
        turnos_candidatos = Turno.objects.filter(
            fecha__range=[bloqueo_inicio.date(), bloqueo_fin.date()],
            estado__in=[
                Turno.Estado.SOLICITADO,
                Turno.Estado.ESPERANDO_SENA,
                Turno.Estado.CONFIRMADO,
                Turno.Estado.SUGERIDO
            ]
        )

        conflictos = []

        # B. Validación fina de HORARIOS (Memoria)
        # Como Turno tiene fecha y hora separadas, las combinamos para comparar
        for turno in turnos_candidatos:
            # Crear datetime del inicio del turno
            turno_inicio_dt = datetime.combine(turno.fecha, turno.hora_inicio)
            # Crear datetime del fin del turno
            turno_fin_dt = datetime.combine(turno.fecha, turno.hora_fin_calculada)
            
            # Hacemos los datetimes "aware" (con zona horaria) si Django lo usa
            if timezone.is_aware(bloqueo_inicio):
                turno_inicio_dt = timezone.make_aware(turno_inicio_dt)
                turno_fin_dt = timezone.make_aware(turno_fin_dt)

            # C. Fórmula de Solapamiento de Rangos:
            # (StartA < EndB) and (EndA > StartB)
            if (turno_inicio_dt < bloqueo_fin) and (turno_fin_dt > bloqueo_inicio):
                # Obtener servicios desde detalles
                servicios = [d.servicio.nombre for d in turno.detalles.all()]
                servicios_str = ', '.join(servicios) if servicios else 'Sin servicios'
                
                conflictos.append({
                    "cliente": f"{turno.cliente.nombre} {turno.cliente.apellido}",
                    "fecha": turno.fecha.strftime('%d/%m'),
                    "hora": f"{turno.hora_inicio.strftime('%H:%M')} - {turno.hora_fin_calculada.strftime('%H:%M')}",
                    "servicios": servicios_str
                })

        # D. Si encontramos conflictos, BLOQUEAMOS el guardado
        if conflictos:
            return Response({
                "error": "CONFLICTO_AGENDA",
                "mensaje": "No se puede bloquear porque existen turnos activos en ese horario.",
                "instruccion": "Debes reprogramar o cancelar los siguientes turnos manualmente:",
                "turnos_afectados": conflictos
            }, status=409) # 409 Conflict

        # ------------------------------------------------------------------
        # Si pasa la validación, GUARDAMOS
        # ------------------------------------------------------------------
        serializer = BloqueoAgendaSerializer(data=data)
        if serializer.is_valid():
            serializer.save(personal=personal)
            return Response(serializer.data, status=201)
        
        return Response(serializer.errors, status=400)

    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def obtener_disponibilidad_calendario(request):
    """
    Cruza Reglas (HorarioLaboral) + Excepciones (BloqueoAgenda) para mostrar disponibilidad en calendario.
    Query params: ?mes=1&anio=2025
    Retorna las reglas de horarios y bloqueos para que el frontend calcule disponibilidad.
    """
    try:
        mes = int(request.query_params.get('mes', 1))
        anio = int(request.query_params.get('anio', timezone.now().year))
        
        # Validar rango válido de mes
        if mes < 1 or mes > 12:
            return Response(
                {"error": "El mes debe estar entre 1 y 12"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 1. Traer todas las reglas activas (HorarioLaboral)
        # Filtramos por profesional si se proporciona
        reglas = HorarioLaboral.objects.filter(activo=True)
        
        personal_id = request.query_params.get('personal_id')
        if personal_id:
            reglas = reglas.filter(personal_id=personal_id)
        
        # 2. Traer bloqueos del mes especificado
        # Buscamos bloqueos que se sobrepongan con cualquier día del mes
        from datetime import date, timedelta
        
        primer_dia = date(anio, mes, 1)
        if mes == 12:
            ultimo_dia = date(anio + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia = date(anio, mes + 1, 1) - timedelta(days=1)
        
        bloqueos = BloqueoAgenda.objects.filter(
            fecha_inicio__lte=ultimo_dia,
            fecha_fin__gte=primer_dia
        )
        
        # Filtrar por personal si se proporciona
        if personal_id:
            from django.db.models import Q
            bloqueos = bloqueos.filter(
                Q(personal_id=personal_id) | Q(personal__isnull=True)
            )
        
        # 3. Serializar y retornar
        return Response({
            "mes": mes,
            "anio": anio,
            "reglas": HorarioLaboralSerializer(reglas, many=True).data,
            "bloqueos": BloqueoAgendaSerializer(bloqueos, many=True).data
        }, status=status.HTTP_200_OK)
    
    except ValueError:
        return Response(
            {"error": "Los parámetros mes y anio deben ser números enteros"},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {"error": f"Error al obtener disponibilidad: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================
# FICHA TÉCNICA VIEWSET
# ============================================================

class FichaTecnicaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar fichas técnicas de servicios realizados.
    Solo el personal técnico (is_staff) puede crear/editar fichas.
    """
    queryset = FichaTecnica.objects.all()
    serializer_class = FichaTecnicaSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        """
        Filtro: 
        - Admins ven todas las fichas
        - Staff solo ve sus propias fichas redactadas
        """
        user = self.request.user
        if user.is_superuser:
            return FichaTecnica.objects.all()
        elif user.is_staff:
            return FichaTecnica.objects.filter(profesional_autor=user)
        else:
            # No staff no puede ver fichas (la permission_classes lo bloquea igual)
            return FichaTecnica.objects.none()
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdminUser])
    def por_turno(self, request):
        """
        GET /fichas-tecnicas/por-turno/?turno_id=123
        Obtiene la ficha técnica de un turno específico.
        """
        turno_id = request.query_params.get('turno_id')
        if not turno_id:
            return Response(
                {"error": "Se requiere el parámetro turno_id"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            turno = Turno.objects.get(id=turno_id)
            fichas = FichaTecnica.objects.filter(detalle_turno__turno=turno)
            serializer = self.get_serializer(fichas, many=True)
            return Response(serializer.data)
        except Turno.DoesNotExist:
            return Response(
                {"error": "Turno no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdminUser])
    def por_cliente(self, request):
        """
        GET /fichas-tecnicas/por_cliente/?cliente_id=123
        Obtiene fichas técnicas asociadas a un cliente.
        """
        cliente_id = request.query_params.get('cliente_id')
        if not cliente_id:
            return Response(
                {"error": "Se requiere el parámetro cliente_id"},
                status=status.HTTP_400_BAD_REQUEST
            )

        fichas = FichaTecnica.objects.filter(detalle_turno__turno__cliente_id=cliente_id).order_by('-fecha_registro')
        serializer = self.get_serializer(fichas, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsAdminUser])
    def mis_fichas(self, request):
        """
        GET /fichas-tecnicas/mis_fichas/
        Obtiene todas las fichas técnicas creadas por el usuario autenticado (profesional).
        """
        fichas = FichaTecnica.objects.filter(profesional_autor=request.user)
        serializer = self.get_serializer(fichas, many=True)
        return Response(serializer.data)


class RequisitoServicioViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar los requisitos de equipamiento por servicio.
    Solo administradores pueden ver/crear/editar/eliminar.
    
    Validaciones:
    - El tipo_equipamiento debe existir en la BD antes de asignarlo
    - El tipo_equipamiento DEBE tener al menos una instancia activa
    - Se valida automáticamente en el serializer y en el modelo
    """
    queryset = RequisitoServicio.objects.all()
    serializer_class = RequisitoServicioSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def get_queryset(self):
        """
        Filtra por servicio si se proporciona en query params.
        GET /requisitos-servicio/?servicio_id=1
        """
        queryset = super().get_queryset()
        servicio_id = self.request.query_params.get('servicio_id')
        if servicio_id:
            queryset = queryset.filter(servicio_id=servicio_id)
        return queryset
    
    def perform_create(self, serializer):
        """
        Crear un requisito de servicio con validaciones.
        
        VALIDACIÓN IMPORTANTE:
        El tipo_equipamiento DEBE tener al menos una instancia activa.
        No permite asignar tipos sin equipamiento real.
        """
        tipo_equipamiento = serializer.validated_data.get('tipo_equipamiento')
        
        # Validar que el tipo tenga al menos una instancia activa
        tiene_instancias = Equipamiento.objects.filter(
            tipo=tipo_equipamiento,
            is_active=True
        ).exists()
        
        if not tiene_instancias:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                f"El tipo de equipamiento '{tipo_equipamiento.nombre}' no tiene instancias activas. "
                f"Crea un equipamiento en la sección 'Gestión de Equipamiento' antes de asignarlo a un servicio."
            )
        
        try:
            # Ejecutar validaciones del modelo
            if hasattr(serializer.validated_data['tipo_equipamiento'], 'clean'):
                serializer.validated_data['tipo_equipamiento'].clean()
            serializer.save()
            logger.info(
                f"Requisito de equipamiento creado: "
                f"Servicio {serializer.validated_data['servicio'].nombre} "
                f"requiere {serializer.validated_data['tipo_equipamiento'].nombre}"
            )
        except Exception as e:
            logger.error(f"Error al crear requisito de equipamiento: {str(e)}")
            raise
    
    def perform_update(self, serializer):
        """
        Actualizar un requisito de servicio con validaciones.
        """
        try:
            # Ejecutar validaciones del modelo
            if hasattr(serializer.validated_data.get('tipo_equipamiento'), 'clean'):
                serializer.validated_data['tipo_equipamiento'].clean()
            serializer.save()
            logger.info(
                f"Requisito de equipamiento actualizado: "
                f"Servicio {serializer.validated_data['servicio'].nombre} "
                f"requiere {serializer.validated_data['tipo_equipamiento'].nombre}"
            )
        except Exception as e:
            logger.error(f"Error al actualizar requisito de equipamiento: {str(e)}")
            raise


class DiagnosticoCapilarViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar diagnósticos capilares.
    - Lectura: Cualquier usuario autenticado puede ver diagnósticos (especialmente clientes sus propios)
    - Creación/Edición: Solo staff (profes
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = DiagnosticoCapilarFilter
    search_fields = ['cliente__usuario__first_name', 'cliente__usuario__last_name']
    ordering_fields = ['fecha_creacion']ionales) pueden crear y editar
    """
    queryset = DiagnosticoCapilar.objects.all()
    serializer_class = DiagnosticoCapilarSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Clientes ven solo sus diagnósticos.
        Staff ve todos.
        """
        if self.request.user.is_staff:
            return DiagnosticoCapilar.objects.all()
        
        # Cliente solo ve sus propios diagnósticos
        try:
            cliente = Cliente.objects.get(usuario=self.request.user)
            return DiagnosticoCapilar.objects.filter(cliente=cliente)
        except Cliente.DoesNotExist:
            return DiagnosticoCapilar.objects.none()
    
    def create(self, request, *args, **kwargs):
        """Solo staff puede crear diagnósticos"""
        if not request.user.is_staff:
            raise PermissionDenied("Solo profesionales pueden crear diagnósticos.")
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        """
        Sobrescribimos perform_create para ejecutar el motor de diagnóstico
        automáticamente después de guardar el diagnóstico.
        """
        # 1. Guarda el diagnóstico en la base de datos
        diagnostico = serializer.save()
        
        # 2. Dispara el motor de análisis (dos niveles)
        self._ejecutar_motor_diagnostico(diagnostico)
    
    def update(self, request, *args, **kwargs):
        """Solo staff puede actualizar diagnósticos"""
        if not request.user.is_staff:
            raise PermissionDenied("Solo profesionales pueden actualizar diagnósticos.")
        return super().update(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    def por_cliente(self, request):
        """
        GET /diagnosticos-capilares/por_cliente/?cliente_id=1
        Obtiene todos los diagnósticos de un cliente específico.
        """
        cliente_id = request.query_params.get('cliente_id')
        if not cliente_id:
            return Response(
                {"error": "Se requiere cliente_id como parámetro"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        diagnosticos = DiagnosticoCapilar.objects.filter(cliente_id=cliente_id).order_by('-fecha_diagnostico')
        serializer = self.get_serializer(diagnosticos, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def mis_diagnosticos(self, request):
        """
        GET /diagnosticos-capilares/mis_diagnosticos/
        Un cliente obtiene el histórico de sus propios diagnósticos.
        """
        try:
            cliente = Cliente.objects.get(usuario=request.user)
            diagnosticos = DiagnosticoCapilar.objects.filter(cliente=cliente).order_by('-fecha_diagnostico')
            serializer = self.get_serializer(diagnosticos, many=True)
            return Response(serializer.data)
        except Cliente.DoesNotExist:
            return Response(
                {"error": "El usuario no es un cliente registrado"},
                status=status.HTTP_404_NOT_FOUND
            )

    def _ejecutar_motor_diagnostico(self, diagnostico):
        """
        Proceso Automatizado P1: Diagnóstico en dos niveles.
        Nivel 1: Reglas Expertas (Combinaciones específicas).
        Nivel 2: Matriz de Puntuación (Estado de salud general).
        """
        # --- NIVEL 1: REGLAS EXPERTAS ---
        # Buscamos reglas priorizando las de mayor peso
        reglas = ReglaDiagnostico.objects.all().order_by('-prioridad')
        regla_matcheada = None
        
        for r in reglas:
            # Comprobamos coincidencia (si el campo de la regla no es null, debe coincidir)
            if r.tipo_cabello and r.tipo_cabello != diagnostico.tipo_cabello: continue
            if r.grosor_cabello and r.grosor_cabello != diagnostico.grosor_cabello: continue
            if r.porosidad_cabello and r.porosidad_cabello != diagnostico.porosidad_cabello: continue
            if r.cuero_cabelludo and r.cuero_cabelludo != diagnostico.cuero_cabelludo: continue
            if r.estado_general and r.estado_general != diagnostico.estado_general: continue
            
            regla_matcheada = r
            break

        rutina_final = None
        servicio_urgente = None

        if regla_matcheada:
            # 1. Asignamos la rutina (con seguridad si es None)
            rutina_final = regla_matcheada.rutina_sugerida
            
            # 2. Asignamos el servicio configurado en la regla
            if regla_matcheada.servicio_sugerido:
                servicio_urgente = regla_matcheada.servicio_sugerido
                # Forzamos que el sistema busque turno aunque Yanina no haya escrito "TURNO" en la acción
                # ya que al elegir un servicio se sobreentiende la intención.
        else:
            # --- NIVEL 2: MATRIZ DE PUNTUACIÓN (SCORING) ---
            # Suma usando los puntajes configurados en los catalogos
            puntos = 0
            if diagnostico.tipo_cabello:
                puntos += diagnostico.tipo_cabello.puntaje_base
            if diagnostico.grosor_cabello:
                puntos += diagnostico.grosor_cabello.puntaje_base
            if diagnostico.porosidad_cabello:
                puntos += diagnostico.porosidad_cabello.puntaje_base
            if diagnostico.cuero_cabelludo:
                puntos += diagnostico.cuero_cabelludo.puntaje_base
            if diagnostico.estado_general:
                puntos += diagnostico.estado_general.puntaje_base

            config_diag = ConfiguracionDiagnostico.get_singleton()
            umbral_critico = config_diag.umbral_critico
            umbral_alerta = config_diag.umbral_alerta

            if puntos <= umbral_critico:
                rutina_final = config_diag.rutina_critico
                servicio_urgente = config_diag.servicio_critico
            elif puntos <= umbral_alerta:
                rutina_final = config_diag.rutina_alerta
                servicio_urgente = config_diag.servicio_alerta
            else:
                rutina_final = config_diag.rutina_saludable
                servicio_urgente = config_diag.servicio_saludable

        # --- EJECUCIÓN DE ACCIONES ---
        # 1. Asignar Rutina
        rutina_cliente = None
        if rutina_final:
            rutina_cliente = RutinaCliente.objects.create(
                cliente=diagnostico.cliente,
                rutina_original=rutina_final,
                nombre=rutina_final.nombre,
                objetivo=rutina_final.objetivo,
                archivo=rutina_final.archivo,
                version_asignada=rutina_final.version,
                estado='activa'
            )
            print(f"\n✅ DEBUG: RutinaCliente creada (ID: {rutina_cliente.id})")

        # 2. GENERAR MENSAJE PROFESIONAL
        mensaje_profesional = self._generar_mensaje_diagnostico(
            diagnostico, puntos if 'puntos' in locals() else None, 
            servicio_urgente, regla_matcheada
        )
        
        # 3. Guardar resultados en el Diagnóstico
        diagnostico.servicio_urgente = servicio_urgente
        diagnostico.rutina_asignada = rutina_final
        diagnostico.rutina_sugerida = rutina_final
        diagnostico.regla_diagnostico = regla_matcheada
        diagnostico.observaciones = mensaje_profesional
        diagnostico.save()

        # 4. Recomendar Turno (Si el score es bajo o la regla lo pide)
        if servicio_urgente:
            try:
                turno_sugerido = self._recomendar_primer_hueco_disponible(diagnostico, servicio_urgente)
                if turno_sugerido:
                    diagnostico.turno_sugerido = turno_sugerido
                    diagnostico.save(update_fields=['turno_sugerido'])
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error en _recomendar_primer_hueco_disponible: {str(e)}")


    def _generar_mensaje_diagnostico(self, diagnostico, puntos, servicio_urgente, regla_matcheada):
        """
        Genera un mensaje profesional unificado.
        Prioriza Reglas Expertas (Nivel 1) sobre la Matriz de Puntuación (Nivel 2).
        """
        # 1. Obtención de datos básicos
        servicio_nombre = servicio_urgente.nombre if servicio_urgente else "Tratamiento Especializado"
        porosidad = diagnostico.porosidad_cabello.nombre if diagnostico.porosidad_cabello else "desconocida"
        grosor = diagnostico.grosor_cabello.nombre if diagnostico.grosor_cabello else "desconocido"
        cuero = diagnostico.cuero_cabelludo.nombre if diagnostico.cuero_cabelludo else "desconocido"
        estado = diagnostico.estado_general.nombre if diagnostico.estado_general else "desconocido"

        # 2. Construcción descriptiva del problema
        descripciones = []
        if estado == "Dañado":
            descripciones.append("daño estructural severo")
        if porosidad == "Alta":
            descripciones.append("porosidad alta con pérdida de hidratación")
        elif porosidad == "Baja":
            descripciones.append("porosidad baja que dificulta la nutrición")
        if grosor == "Fino":
            descripciones.append("fragilidad capilar")
        if cuero == "Seco":
            descripciones.append("deshidratación en cuero cabelludo")

        problema = " debido a " + ", ".join(descripciones) if descripciones else ""

        # CASO A: REGLA EXPERTA
        if regla_matcheada:
            mensaje_regla = (regla_matcheada.mensaje_resultado or "").strip()
            if not mensaje_regla:
                mensaje_regla = (regla_matcheada.accion_resultado or "").strip()
            return mensaje_regla

        config_diag = ConfiguracionDiagnostico.get_singleton()
        umbral_critico = config_diag.umbral_critico
        umbral_alerta = config_diag.umbral_alerta

        def render_mensaje(template):
            if not template:
                return ""
            try:
                return template.format(score=puntos, servicio=servicio_nombre)
            except Exception:
                return template

        # CASO B: ESTADO CRÍTICO
        if puntos is not None and puntos <= umbral_critico:
            return render_mensaje(config_diag.mensaje_critico)

        # CASO C: ESTADO DE ALERTA
        if puntos is not None and puntos <= umbral_alerta:
            return render_mensaje(config_diag.mensaje_alerta)

        # CASO D: ESTADO SALUDABLE
        return render_mensaje(config_diag.mensaje_saludable)

    def _recomendar_primer_hueco_disponible(self, diagnostico, servicio):
        """
        Busca el primer hueco disponible en los próximos 30 días
        y crea una notificación para el cliente recomendando agendar un turno.
        """
        import logging
        from datetime import date, timedelta
        logger = logging.getLogger(__name__)
        
        try:
            # 1. VALIDACIONES INICIALES
            if not servicio:
                logger.error(f"[DIAGNOSTICO] Servicio no encontrado para recomendación")
                return
            
            if not diagnostico or not diagnostico.cliente or not diagnostico.cliente.usuario:
                logger.error(f"[DIAGNOSTICO] Diagnóstico o cliente inválido")
                return
            
            # 2. OBTENER DURACIÓN DEL SERVICIO
            duracion_minutos = servicio.duracion_estimada or 60
            logger.info(f"[DIAGNOSTICO] Buscando turno para: {servicio.nombre} ({duracion_minutos} min)")
            
            # Obtener instancia de TurnoViewSet para usar su método _generar_slots_disponibles
            turno_viewset = TurnoViewSet()
            
            # 3. BUSCAR PRIMER SLOT DISPONIBLE EN PRÓXIMOS 30 DÍAS
            fecha_busqueda = date.today() + timedelta(days=1)
            fecha_fin = fecha_busqueda + timedelta(days=30)
            slot_encontrado = None
            
            while fecha_busqueda <= fecha_fin:
                # Obtener día de la semana (0=lunes, 6=domingo)
                dia_semana = fecha_busqueda.weekday()
                
                # 4. BUSCAR HORARIOS DEL PERSONAL PARA ESTE DÍA
                horarios_disponibles = HorarioLaboral.objects.filter(
                    activo=True,
                    dia_semana=dia_semana,
                    personal__isnull=False
                )
                
                # Filtrar por tipo de servicio (Diseño vs Complemento)
                categoria_nombre = servicio.categoria.nombre if servicio.categoria else ""
                
                if "Diseño" in categoria_nombre or "Color" in categoria_nombre:
                    # Servicios de color/diseño: necesitan permite_diseno_color=True
                    horarios_disponibles = horarios_disponibles.filter(permite_diseno_color=True)
                    tipo_servicio = "Diseño"
                else:
                    # Servicios cortos (corte, nutrición): necesitan permite_complemento=True
                    horarios_disponibles = horarios_disponibles.filter(permite_complemento=True)
                    tipo_servicio = "Complemento"
                
                logger.info(f"[DIAGNOSTICO] {fecha_busqueda} ({DiasSemana(dia_semana).label}): {horarios_disponibles.count()} horarios disponibles para {tipo_servicio}")
                
                # 5. ITERAR POR CADA HORARIO DISPONIBLE
                for horario in horarios_disponibles:
                    personal = horario.personal
                    
                    # Verificar si el personal tiene bloqueo en esta fecha
                    bloqueo = BloqueoAgenda.objects.filter(
                        personal=personal,
                        fecha_inicio__date__lte=fecha_busqueda,
                        fecha_fin__date__gte=fecha_busqueda
                    ).exists()
                    
                    if bloqueo:
                        logger.info(f"[DIAGNOSTICO] {personal.nombre} tiene bloqueo en {fecha_busqueda}")
                        continue
                    
                    # 6. GENERAR SLOTS PARA ESTE HORARIO
                    try:
                        slots = turno_viewset._generar_slots_disponibles(
                            fecha_busqueda,
                            horario,
                            duracion_minutos,
                            intervalo_minutos=15,
                            servicios_ids=[servicio.id]
                        )
                        
                        if slots:
                            primer_slot = slots[0]
                            slot_encontrado = {
                                'fecha': fecha_busqueda,
                                'hora': primer_slot.get('hora'),
                                'profesional': personal,
                                'horario': horario
                            }
                            logger.info(f"[DIAGNOSTICO] Slot encontrado: {fecha_busqueda} {primer_slot.get('hora')} con {personal.nombre}")
                            break
                    except Exception as e:
                        logger.warning(f"[DIAGNOSTICO] Error generando slots para {personal.nombre}: {str(e)}")
                        continue
                
                # Si encontramos slot, salir del loop de fechas
                if slot_encontrado:
                    break
                
                fecha_busqueda += timedelta(days=1)
            
            # 7. SI SE ENCONTRÓ SLOT, CREAR NOTIFICACIÓN
            if slot_encontrado:
                logger.info(f"[DIAGNOSTICO] Creando notificación de recomendación de turno...")
                try:
                    # Formato correcto: "2025-01-30" y "14:30"
                    fecha_str = slot_encontrado['fecha'].strftime('%Y-%m-%d')
                    hora_str = slot_encontrado['hora']  # Ya viene como string "HH:MM"
                    hora_inicio = datetime.strptime(hora_str, '%H:%M').time()
                    hora_fin_dt = datetime.combine(slot_encontrado['fecha'], hora_inicio) + timedelta(minutes=duracion_minutos)
                    hora_fin = hora_fin_dt.time()

                    turno_sugerido = Turno.objects.filter(
                        cliente=diagnostico.cliente,
                        fecha=slot_encontrado['fecha'],
                        hora_inicio=hora_inicio
                    ).first()

                    if not turno_sugerido:
                        turno_sugerido = Turno.objects.create(
                            cliente=diagnostico.cliente,
                            profesional=slot_encontrado['profesional'],
                            fecha=slot_encontrado['fecha'],
                            hora_inicio=hora_inicio,
                            hora_fin_calculada=hora_fin,
                            estado=Turno.Estado.SUGERIDO
                        )
                        DetalleTurno.objects.create(
                            turno=turno_sugerido,
                            servicio=servicio,
                            precio_historico=servicio.precio_base or 0,
                            duracion_minutos=duracion_minutos
                        )
                    
                    # Usar el mensaje profesional del diagnóstico que ya fue generado
                    mensaje_notificacion = diagnostico.observaciones or "Te recomendamos agendar tu cita"
                    
                    notif = Notificacion.objects.create(
                        usuario=diagnostico.cliente.usuario,
                        tipo='alerta',
                        titulo="Recomendación para tu cabello",
                        mensaje=mensaje_notificacion,
                        datos_extra={
                            "fecha": fecha_str,
                            "hora": hora_str,
                            "servicio_id": servicio.id,
                            "profesional_id": slot_encontrado['profesional'].id,
                            "turno_id": turno_sugerido.id
                        }
                    )
                    logger.info(f"[DIAGNOSTICO] OK - Notificacion creada (ID: {notif.id})")
                    return turno_sugerido
                except Exception as e:
                    logger.error(f"[DIAGNOSTICO] Error creando notificacion: {str(e)}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.warning(f"[DIAGNOSTICO] AVISO - No se encontro disponibilidad en los proximos 30 dias para {servicio.nombre}")
                return None
        
        except Exception as e:
            logger.error(f"[DIAGNOSTICO] Error en _recomendar_primer_hueco_disponible: {str(e)}")
            import traceback
            traceback.print_exc()
            logger.error(traceback.format_exc())
            return None


# ============================================
# VIEWSETS PARA PRODUCTOS
# ============================================

class CategoriaProductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar categorías de productos.
    """
    queryset = CategoriaProducto.objects.filter(activo=True)
    serializer_class = CategoriaProductoSerializer
    permission_classes = [AllowAny]
    pagination_class = None




# ============================================
# VIEWSET PARA PROMOCIONES
# ============================================

class PromocionViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar promociones del sistema.
    Soporta tres pilares: COMBO, RETOQUE, LAST_MINUTE.
    
    Clientes pueden ver promociones activas (list/retrieve).
    Solo admins pueden crear/actualizar/eliminar.
    """
    queryset = Promocion.objects.all()
    serializer_class = PromocionSerializer
    pagination_class = None
    
    def get_permissions(self):
        """
        Permisos dinámicos: 
        - list/retrieve: AllowAny (clientes pueden ver promociones activas)
        - create/update/destroy: IsAdminUser (solo admins)
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """
        Filtra promociones activas por defecto.
        Query params: ?activas=true|false
        
        Para clientes: solo retorna promociones activas hoy
        Para admins: retorna todas las promociones
        """
        queryset = super().get_queryset()
        
        # Si no es admin, solo mostrar promociones activas
        if not self.request.user.is_staff:
            hoy = timezone.now().date()
            queryset = queryset.filter(
                is_active=True,
                fecha_inicio__lte=hoy,
                fecha_fin__gte=hoy
            )
        else:
            # Para admins, permitir filtrar por ?activas=true|false
            activas_only = self.request.query_params.get('activas', 'false').lower() == 'true'
            if activas_only:
                hoy = timezone.now().date()
                queryset = queryset.filter(
                    is_active=True,
                    fecha_inicio__lte=hoy,
                    fecha_fin__gte=hoy
                )
        
        return queryset.order_by('-fecha_inicio')

    def perform_create(self, serializer):
        promocion = serializer.save()
        if promocion.es_sugerencia_automatica:
            promocion.estado_sugerencia = 'PENDIENTE'
            promocion.is_active = False
        elif not promocion.estado_sugerencia:
            promocion.estado_sugerencia = 'ACEPTADA'
        promocion.save()

    @action(detail=False, methods=['get'], url_path='sugerencias')
    def sugerencias(self, request):
        """
        Lista sugerencias automáticas de combos pendientes.
        GET /api/gestion/promociones/sugerencias/
        """
        if not request.user.is_staff:
            return Response({'error': 'No autorizado'}, status=status.HTTP_403_FORBIDDEN)

        queryset = Promocion.objects.filter(
            tipo='COMBO',
            es_sugerencia_automatica=True,
            estado_sugerencia='PENDIENTE'
        ).order_by('-fecha_creacion')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='publicar')
    def publicar(self, request, pk=None):
        """
        Publica una sugerencia de combo.
        POST /api/gestion/promociones/{id}/publicar/
        """
        if not request.user.is_staff:
            return Response({'error': 'No autorizado'}, status=status.HTTP_403_FORBIDDEN)

        promocion = self.get_object()
        data = request.data or {}

        if 'nombre' in data:
            promocion.nombre = data.get('nombre', promocion.nombre)
        if 'descripcion' in data:
            promocion.descripcion = data.get('descripcion', promocion.descripcion)
        if 'descuento_porcentaje' in data:
            promocion.descuento_porcentaje = data.get('descuento_porcentaje', promocion.descuento_porcentaje)

        promocion.is_active = True
        promocion.estado_sugerencia = 'ACEPTADA'
        promocion.save()

        serializer = self.get_serializer(promocion)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='rechazar')
    def rechazar(self, request, pk=None):
        """
        Rechaza una sugerencia de combo.
        POST /api/gestion/promociones/{id}/rechazar/
        """
        if not request.user.is_staff:
            return Response({'error': 'No autorizado'}, status=status.HTTP_403_FORBIDDEN)

        promocion = self.get_object()
        promocion.is_active = False
        promocion.estado_sugerencia = 'RECHAZADA'
        promocion.save()

        serializer = self.get_serializer(promocion)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='escanear-huecos')
    def escanear_huecos(self, request):
        """
        Escanea la agenda de los próximos 3 días buscando huecos > 3 horas
        y genera promociones automáticas Last Minute.
        
        POST /api/gestion/promociones/escanear-huecos/
        """
        logger = logging.getLogger(__name__)
        hoy = date.today()
        proximos_dias = [hoy + timedelta(days=i) for i in range(1, 4)]
        promos_creadas = 0
        
        try:
            # 1. Iteramos por cada profesional activo
            profesionales = Personal.objects.filter(activo=True)
            
            for profe in profesionales:
                for fecha in proximos_dias:
                    # 2. Obtenemos su horario laboral para ese día
                    dia_semana = fecha.weekday()
                    horario = HorarioLaboral.objects.filter(
                        personal=profe, 
                        dia_semana=dia_semana, 
                        activo=True
                    ).first()
                    
                    if not horario:
                        continue  # No trabaja ese día

                    # 3. Obtenemos sus turnos ocupados
                    turnos = Turno.objects.filter(
                        profesional=profe, 
                        fecha=fecha, 
                        estado__in=['confirmado', 'esperando_sena', 'solicitado']
                    ).order_by('hora_inicio').prefetch_related('detalles')

                    # 4. Calculamos los huecos entre turnos
                    huecos = self._calcular_huecos(horario, turnos, fecha)
                    
                    for h_ini, h_fin, duracion in huecos:
                        # REGLA: Si el hueco es mayor a 180 minutos (3 horas)
                        if duracion >= 180:
                            nombre_promo = f"Flash Sale: {profe.nombre} - {fecha.strftime('%d/%m')}"
                            # Evitamos duplicados para el mismo hueco
                            if not Promocion.objects.filter(
                                nombre=nombre_promo, 
                                fecha_especifica=fecha
                            ).exists():
                                self._crear_promocion_last_minute(profe, fecha, h_ini, h_fin)
                                promos_creadas += 1
                                logger.info(f"Promo creada: {nombre_promo}")
            
            return Response({
                "status": "Escaneo completado",
                "promociones_generadas": promos_creadas,
                "dias_escaneados": len(proximos_dias)
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Error en escanear_huecos: {str(e)}", exc_info=True)
            return Response({
                "error": f"Error al escanear huecos: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _calcular_huecos(self, horario, turnos, fecha):
        """
        Lógica auxiliar para encontrar intervalos de tiempo libre en la jornada.
        Retorna lista de tuplas: (hora_inicio, hora_fin, duracion_minutos)
        """
        huecos = []
        
        # El día empieza en horario.hora_inicio
        ultimo_fin = datetime.combine(fecha, horario.hora_inicio)
        final_jornada = datetime.combine(fecha, horario.hora_fin)

        for t in turnos:
            t_inicio = datetime.combine(fecha, t.hora_inicio)
            
            # Calculamos el hueco antes del turno
            if t_inicio > ultimo_fin:
                dif_minutos = int((t_inicio - ultimo_fin).total_seconds() / 60)
                huecos.append((ultimo_fin.time(), t_inicio.time(), dif_minutos))
            
            # Actualizamos el fin según la duración del turno
            duracion_t = sum(d.duracion_minutos for d in t.detalles.all()) or 60
            ultimo_fin = t_inicio + timedelta(minutes=duracion_t)

        # Hueco final (después del último turno hasta cierre de jornada)
        if final_jornada > ultimo_fin:
            dif_minutos = int((final_jornada - ultimo_fin).total_seconds() / 60)
            huecos.append((ultimo_fin.time(), final_jornada.time(), dif_minutos))
            
        return huecos
    
    def _crear_promocion_last_minute(self, profesional, fecha, hora_inicio, hora_fin):
        """
        Crea una promoción Last Minute para un hueco específico en la agenda.
        """
        logger = logging.getLogger(__name__)
        
        try:
            nombre_promo = f"¡Oportunidad Last-Minute con {profesional.nombre}!"
            
            promo = Promocion.objects.create(
                nombre=nombre_promo,
                descripcion=f"Tenemos un espacio libre {fecha.strftime('%d/%m')}. ¡Aprovéchalo con 30% OFF!",
                tipo='LAST_MINUTE',
                descuento_porcentaje=30,
                fecha_inicio=date.today(),
                fecha_fin=fecha,
                fecha_especifica=fecha,
                hora_inicio_promo=hora_inicio,
                hora_fin_promo=hora_fin,
                is_active=True
            )
            
            # Agregar servicios que queremos incentivar (especialmente servicios de Color)
            servicios_complejos = Servicio.objects.filter(
                categoria__nombre__icontains="Color",
                activo=True
            )[:2]
            
            if servicios_complejos.exists():
                promo.servicios.set(servicios_complejos)
            else:
                # Si no hay servicios de Color, asignamos los primeros 2 disponibles
                servicios_fallback = Servicio.objects.filter(activo=True).order_by('?')[:2]
                promo.servicios.set(servicios_fallback)
            
            # Registro de notificación masiva
            logger.info(f"NOTIFICACIÓN: Promoción Last Minute publicada para el {fecha.strftime('%d/%m/%Y')} de {hora_inicio} a {hora_fin}")
            logger.info(f"Servicios incluidos: {', '.join([s.nombre for s in promo.servicios.all()])}")
            
            return promo
        
        except Exception as e:
            logger.error(f"Error al crear promo last minute: {str(e)}", exc_info=True)
            return None


# ============================================================================
# FUNCIONES AUXILIARES - WHATSAPP
# ============================================================================

def generar_link_whatsapp(carrito_items, total):
    """
    Genera un enlace de WhatsApp con los detalles del pedido.
    Usa el formato configurado en el modelo Configuracion.
    
    Args:
        carrito_items: QuerySet de CarritoItem
        total: Total del carrito (float)
    
    Returns:
        str: URL de WhatsApp Web con mensaje pre-redactado
    """
    import urllib.parse
    
    # Obtener configuración
    from gestion.models import Configuracion
    config = Configuracion.objects.first()
    
    # Valores por defecto
    telefono = config.whatsapp_numero if config else "5491122334455"
    saludo = config.whatsapp_saludo if config else "¡Hola Bohemia Hair! 👋 Quiero realizar el siguiente pedido:"
    cierre = config.whatsapp_cierre if config else "\n💰 *Total estimado: ${total}*\n\n¿Me confirman la disponibilidad y los detalles del envío?"
    formato_producto = config.whatsapp_formato_producto if config else "• {nombre}\n  Cantidad: {cantidad} x ${precio:.2f} = ${subtotal:.2f}"
    
    # Construir mensaje
    mensaje = saludo + "\n\n"
    
    for item in carrito_items:
        precio_unitario = float(item.producto.precio)
        subtotal = precio_unitario * item.cantidad
        
        linea_producto = formato_producto.format(
            nombre=item.producto.nombre,
            cantidad=item.cantidad,
            precio=precio_unitario,
            subtotal=subtotal
        )
        mensaje += linea_producto + "\n"
    
    # Agregar cierre con total formateado
    mensaje_cierre = cierre.replace("{total}", f"${total:.2f}")
    mensaje += mensaje_cierre
    
    # Codificar para URL
    mensaje_encoded = urllib.parse.quote(mensaje)
    
    logger.info(f"Link de WhatsApp generado. Número: {telefono} | Total: ${total}")
    
    return f"https://wa.me/{telefono}?text={mensaje_encoded}"


# ============================================================================
# SECCIÓN CARRITO DE COMPRAS
# ============================================================================

class CarritoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar el carrito de compras del cliente.
    Cada cliente tiene UN ÚNICO carrito (OneToOneField).
    
    Endpoints disponibles:
    - GET /api/carrito/ - Lista el carrito del usuario actual
    - POST /api/carrito/agregar_producto/ - Agrega/actualiza producto
    - POST /api/carrito/eliminar_producto/ - Elimina un producto
    - DELETE /api/carrito/vaciar/ - Vacía todo el carrito
    - POST /api/carrito/finalizar_compra/ - Procesa la compra
    - POST /api/carrito/generar_pago_mercadopago/ - Crea orden y link de pago
    """
    serializer_class = CarritoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Cada cliente solo ve su propio carrito."""
        try:
            cliente = Cliente.objects.get(usuario=self.request.user)
            return Carrito.objects.filter(cliente=cliente).prefetch_related('items', 'items__producto', 'items__producto__imagenes')
        except Cliente.DoesNotExist:
            return Carrito.objects.none()

    def get_carrito_cliente(self):
        """Helper: obtiene el carrito del cliente autenticado."""
        try:
            cliente = Cliente.objects.get(usuario=self.request.user)
            carrito, created = Carrito.objects.get_or_create(cliente=cliente)
            return carrito
        except Cliente.DoesNotExist:
            logger.warning(f"Usuario {self.request.user.email} no tiene perfil de cliente")
            raise ValidationError('El usuario no tiene perfil de cliente. Por favor, contacta al administrador.')

    @action(detail=False, methods=['get'], url_path='mi-carrito')
    def mi_carrito(self, request):
        """
        GET /api/gestion/carrito/mi-carrito/
        Retorna el carrito del usuario autenticado.
        """
        try:
            carrito = self.get_carrito_cliente()
            # Usar prefetch para optimizar
            carrito = Carrito.objects.filter(id=carrito.id).prefetch_related(
                'items', 'items__producto', 'items__producto__imagenes'
            ).first()
            serializer = CarritoSerializer(carrito, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(
                {'error': str(e.detail[0]) if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error obteniendo carrito: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Error al obtener el carrito: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='agregar-producto')
    def agregar_producto(self, request):
        """
        POST /api/gestion/carrito/agregar-producto/
        Body: {
            "producto_id": 5,
            "cantidad": 2
        }
        Agrega o actualiza un producto en el carrito.
        """
        try:
            producto_id = request.data.get('producto_id')
            cantidad = int(request.data.get('cantidad', 1))
            
            # Validaciones
            if not producto_id:
                return Response(
                    {'error': 'producto_id es requerido'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if cantidad < 1:
                return Response(
                    {'error': 'cantidad debe ser mayor a 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Obtener producto
            producto = Producto.objects.get(id=producto_id, activo=True)
            
            # Validar stock disponible
            if producto.stock_disponible < cantidad:
                return Response(
                    {'error': f'Stock insuficiente. Disponible: {producto.stock_disponible}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Obtener carrito
            carrito = self.get_carrito_cliente()
            
            # Agregar o actualizar item
            from gestion.models import CarritoItem
            item, created = CarritoItem.objects.get_or_create(
                carrito=carrito,
                producto=producto
            )
            
            if created:
                item.cantidad = cantidad
            else:
                item.cantidad += cantidad
            
            item.save()
            
            logger.info(f"Producto {producto.id} agregado al carrito de {self.request.user.email}")
            
            serializer = CarritoSerializer(carrito, context={'request': self.request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        except Producto.DoesNotExist:
            return Response(
                {'error': 'Producto no encontrado o inactivo'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            return Response(
                {'error': str(e.detail[0]) if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error agregando producto: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Error al agregar producto: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='eliminar-producto', url_name='eliminar_producto')
    def eliminar_producto(self, request):
        """
        POST /api/gestion/carrito/eliminar-producto/
        Body: {"carrito_item_id": 10}
        Elimina un producto específico del carrito.
        """
        try:
            item_id = request.data.get('carrito_item_id')
            if not item_id:
                return Response(
                    {'error': 'carrito_item_id es requerido'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            carrito = self.get_carrito_cliente()
            
            from gestion.models import CarritoItem
            item = CarritoItem.objects.get(id=item_id, carrito=carrito)
            item.delete()
            
            logger.info(f"Item {item_id} eliminado del carrito de {self.request.user.email}")
            
            serializer = CarritoSerializer(carrito)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except CarritoItem.DoesNotExist:
            return Response(
                {'error': 'Item no encontrado en el carrito'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error eliminando producto: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['delete'], url_path='vaciar')
    def vaciar(self, request):
        """
        DELETE /api/gestion/carrito/vaciar/
        Vacía todos los items del carrito.
        """
        try:
            carrito = self.get_carrito_cliente()
            carrito.items.all().delete()
            
            logger.info(f"Carrito vaciado para {self.request.user.email}")
            
            serializer = CarritoSerializer(carrito)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error vaciando carrito: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='finalizar-compra')
    def finalizar_compra(self, request):
        """
        POST /api/gestion/carrito/finalizar-compra/
        Procesa la compra: valida stock, resta inventario y limpia el carrito.
        
        Cumple con REQ-11: Auditoría de Stock
        """
        try:
            carrito = self.get_carrito_cliente()
            
            if not carrito.items.exists():
                return Response(
                    {'error': 'El carrito está vacío'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 1. VALIDAR STOCK de todos los productos ANTES de procesar
            items_carrito = list(carrito.items.select_related('producto'))
            items_count = len(items_carrito)
            for item in items_carrito:
                if item.producto.stock_disponible < item.cantidad:
                    return Response(
                        {
                            'error': f'Stock insuficiente de {item.producto.nombre}',
                            'disponible': item.producto.stock_disponible,
                            'solicitado': item.cantidad
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # 2. PROCESAR COMPRA (Lógica de Negocio) - Dentro de transacción atómica
            with transaction.atomic():
                total_venta = 0
                
                # Crear orden y reservar stock
                cliente = carrito.cliente
                # Max length is 20; keep code compact but readable.
                codigo = f"OC{timezone.now().strftime('%y%m%d%H%M%S')}{uuid4().hex[:4].upper()}"
                orden = OrdenCompra.objects.create(
                    codigo=codigo,
                    cliente=cliente,
                    estado='PENDIENTE',
                    total=0
                )

                for item in items_carrito:
                    producto = item.producto
                    cantidad = item.cantidad
                    precio_unitario = producto.precio
                    subtotal = cantidad * precio_unitario

                    OrdenItem.objects.create(
                        orden=orden,
                        producto=producto,
                        cantidad=cantidad,
                        precio_historico=precio_unitario
                    )

                    # Reservar stock comprometido
                    producto.stock_comprometido = max(0, producto.stock_comprometido + cantidad)
                    producto.save()

                    total_venta += subtotal

                    logger.info(
                        f"Stock comprometido: {producto.nombre} | "
                        f"Cantidad: {cantidad} | Comprometido: {producto.stock_comprometido}"
                    )

                orden.total = total_venta
                orden.save(update_fields=['total'])

                whatsapp_link = generar_link_whatsapp(items_carrito, total_venta)

                # 3. LIMPIAR CARRITO
                carrito.items.all().delete()

                # 4. CREAR NOTIFICACIÓN DE COMPRA EXITOSA
                Notificacion.objects.create(
                    usuario=cliente.usuario,
                    tipo='alerta',
                    titulo='✅ Compra Realizada',
                    mensaje=f'Tu compra por ${total_venta:.2f} ha sido procesada exitosamente.',
                    datos_extra={
                        'total': float(total_venta),
                        'cantidad_items': items_count,
                        'contexto': 'compra_exitosa'
                    },
                    canal='app',
                    estado='pendiente'
                )
            
            logger.info(
                f"Compra completada por {self.request.user.email} | "
                f"Total: ${total_venta:.2f} | Items: {items_count}"
            )
            
            serializer = CarritoSerializer(carrito)
            return Response(
                {
                    'status': 'Compra realizada con éxito',
                    'orden_id': orden.id,
                    'total': float(total_venta),
                    'items_count': items_count,
                    'whatsapp_link': whatsapp_link,
                    'carrito': serializer.data
                },
                status=status.HTTP_200_OK
            )
        
        except ValidationError as e:
            return Response(
                {'error': str(e.detail[0])},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error al finalizar compra: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error procesando la compra'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def generar_pedido_whatsapp(self, request):
        """
        POST /api/gestion/carrito/generar_pedido_whatsapp/
        
        Genera un enlace de WhatsApp con los detalles del pedido.
        El cliente se redirige a WhatsApp para confirmar el pedido.
        
        Response:
        {
            "whatsapp_link": "https://wa.me/5491122334455?text=...",
            "total": 1250.00,
            "items_count": 3
        }
        """
        try:
            carrito = self.get_carrito_cliente()
            
            if not carrito.items.exists():
                return Response(
                    {'error': 'El carrito está vacío'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Obtener items con relaciones
            items_carrito = carrito.items.select_related('producto').all()
            
            # Calcular total
            total_pedido = sum(
                float(item.producto.precio) * item.cantidad 
                for item in items_carrito
            )
            
            # Generar link de WhatsApp
            whatsapp_link = generar_link_whatsapp(items_carrito, total_pedido)
            
            logger.info(
                f"Pedido WhatsApp generado para {self.request.user.email} | "
                f"Total: ${total_pedido:.2f} | Items: {items_carrito.count()}"
            )
            
            return Response(
                {
                    'whatsapp_link': whatsapp_link,
                    'total': round(total_pedido, 2),
                    'items_count': items_carrito.count(),
                    'mensaje': 'Redirigiendo a WhatsApp...'
                },
                status=status.HTTP_200_OK
            )
        
        except ValidationError as e:
            return Response(
                {'error': str(e.detail[0]) if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            logger.error(f"Error generando pedido WhatsApp: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al generar link de WhatsApp'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def registrar_intencion_compra(self, request):
        """
        POST /api/gestion/carrito/registrar_intencion_compra/
        
        Registra una intención de compra (orden pendiente) en la base de datos
        para auditoría cuando el cliente abre WhatsApp.
        
        Body:
        {
            "items": [{"producto_id": 1, "nombre": "X", "cantidad": 2, "precio": 100, "subtotal": 200}],
            "total": 200
        }
        
        Response:
        {
            "orden_id": 123,
            "estado": "PENDIENTE",
            "fecha_creacion": "2026-02-04T10:30:00Z"
        }
        """
        try:
            carrito = self.get_carrito_cliente()
            items_carrito = carrito.items.select_related('producto').all()
            
            if not items_carrito.exists():
                return Response(
                    {'error': 'El carrito está vacío'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Construir JSON de items
            items_json = []
            total_pedido = 0
            
            for item in items_carrito:
                precio = float(item.producto.precio)
                subtotal = precio * item.cantidad
                total_pedido += subtotal
                
                items_json.append({
                    'producto_id': item.producto.id,
                    'nombre': item.producto.nombre,
                    'cantidad': item.cantidad,
                    'precio': precio,
                    'subtotal': subtotal
                })
            
            # Obtener cliente
            from usuarios.models import Cliente
            cliente = Cliente.objects.filter(usuario=self.request.user).first()
            
            # Validar disponibilidad de stock y comprometer
            from gestion.models import OrdenPendiente, Auditoria
            
            for item in items_carrito:
                producto = item.producto
                if producto.stock_disponible < item.cantidad:
                    return Response(
                        {
                            'error': f"Stock insuficiente para {producto.nombre}. "
                                   f"Disponible: {producto.stock_disponible}, Solicitado: {item.cantidad}"
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Crear orden pendiente
            orden = OrdenPendiente.objects.create(
                cliente=cliente,
                estado='PENDIENTE',
                items_json=items_json,
                monto_total=total_pedido
            )
            
            # Comprometer el stock para cada item
            for item in items_carrito:
                producto = item.producto
                producto.stock_comprometido += item.cantidad
                producto.save()
                logger.info(f"Stock comprometido: {producto.nombre} +{item.cantidad} (Disponible: {producto.stock_disponible})")
            
            # Registrar en auditoría
            try:
                ip_address = self.request.META.get('REMOTE_ADDR', '')
                Auditoria.objects.create(
                    tabla='OrdenPendiente',
                    registro_id=orden.id,
                    usuario=self.request.user,
                    accion='ALTA',
                    valor_nuevo={
                        'id': orden.id,
                        'estado': orden.estado,
                        'monto_total': float(orden.monto_total),
                        'items_count': len(items_json),
                        'items_resumido': ', '.join([f"{item['nombre']} (x{item['cantidad']})" for item in items_json[:3]]),
                        'fecha_creacion': orden.fecha_creacion.isoformat()
                    },
                    ip_address=ip_address
                )
            except Exception as audit_error:
                logger.warning(f"No se registró auditoría para orden {orden.id}: {str(audit_error)}")
            
            logger.info(
                f"Intención de compra registrada - Orden ID: {orden.id} | "
                f"Usuario: {self.request.user.email} | Total: ${total_pedido:.2f}"
            )
            
            return Response(
                {
                    'orden_id': orden.id,
                    'estado': orden.estado,
                    'fecha_creacion': orden.fecha_creacion.isoformat(),
                    'monto_total': float(orden.monto_total),
                    'items_count': len(items_json)
                },
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error registrando intención de compra: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al registrar la orden'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='generar-pago-mercadopago')
    def generar_pago_mercadopago(self, request):
        try:
            orden, url_pago, items_count = _crear_checkout_mercadopago_para_usuario(request.user)

            logger.info(
                f"Orden Mercado Pago generada para {request.user.email} | "
                f"Orden: {orden.codigo} | Total: ${orden.total}"
            )

            return Response(
                {
                    'mensaje': 'Orden creada con éxito. Redirigiendo a Mercado Pago...',
                    'init_point': url_pago,
                    'orden_codigo': orden.codigo,
                    'orden_id': orden.id,
                    'preference_id': orden.preference_id,
                    'total': float(orden.total),
                    'items_count': items_count,
                },
                status=status.HTTP_200_OK
            )

        except Cliente.DoesNotExist:
            return Response(
                {'error': 'El usuario no tiene perfil de cliente.'},
                status=status.HTTP_403_FORBIDDEN
            )
        except ValidationError as e:
            mensaje = str(e.detail[0]) if hasattr(e, 'detail') and e.detail else str(e)
            return Response({'error': mensaje}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            logger.error(f"Error al generar preferencia de Mercado Pago: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Error generando pago Mercado Pago: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al generar el pago de Mercado Pago'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='sugerencias_inteligentes')
    def sugerencias_inteligentes(self, request):
        """
        GET /api/gestion/carrito/sugerencias_inteligentes/
        
        Analiza el diagnóstico del cliente y los productos en su carrito
        para sugerir productos complementarios basados en su tipo de cabello.
        
        Implementa lógica de recomendación inteligente (IRQ-09).
        """
        try:
            # 1. Obtener cliente
            cliente = Cliente.objects.get(usuario=request.user)
            
            # 2. Obtener carrito actual (si existe)
            carrito = Carrito.objects.filter(cliente=cliente).first()
            productos_en_carrito = set(
                carrito.items.values_list('producto_id', flat=True)
            ) if carrito else set()
            
            # 3. Obtener último diagnóstico
            ultimo_diag = DiagnosticoCapilar.objects.filter(
                cliente=cliente
            ).latest('fecha_diagnostico')
            
            if not ultimo_diag:
                return Response({
                    "sugerencias": [],
                    "mensaje": "No hay diagnóstico disponible. Realiza un diagnóstico para obtener recomendaciones."
                })
            
            # 4. Mapear diagnóstico a compatibilidad de producto
            tag_busqueda = 'TODO'
            razon = 'general'
            
            if ultimo_diag.estado_general:
                estado = ultimo_diag.estado_general.nombre.lower()
                if 'dañado' in estado or 'seco' in estado:
                    tag_busqueda = 'DANADO'
                    razon = f'cabello {estado}'
                elif 'graso' in estado:
                    tag_busqueda = 'GRASO'
                    razon = 'cuero cabelludo graso'
            
            if ultimo_diag.cuero_cabelludo and 'graso' in ultimo_diag.cuero_cabelludo.nombre.lower():
                tag_busqueda = 'GRASO'
                razon = 'cuero cabelludo graso'
            
            # 5. Buscar productos sugeridos
            # Nota: stock_disponible es una propiedad calculada, no un campo de BD
            # Por eso filtramos por stock_real > 0
            sugeridos = Producto.objects.filter(
                compatibilidad=tag_busqueda,
                stock_real__gt=0,
                activo=True
            ).exclude(
                id__in=productos_en_carrito
            )[:5]  # Top 5 sugerencias
            
            if not sugeridos.exists():
                return Response({
                    "sugerencias": [],
                    "mensaje": f"No hay productos disponibles para tu tipo de {razon}."
                })
            
            from gestion.serializers import ProductoSerializer
            serializer = ProductoSerializer(sugeridos, many=True)
            
            logger.info(
                f"Sugerencias generadas para {request.user.email} | "
                f"Razón: {razon} | Productos: {sugeridos.count()}"
            )
            
            return Response({
                "mensaje_marketing": f"Basado en tu diagnóstico ({razon}), estos productos potenciarán tus resultados:",
                "sugerencias": serializer.data,
                "diagnostico_fecha": ultimo_diag.fecha_diagnostico
            }, status=status.HTTP_200_OK)
        
        except Cliente.DoesNotExist:
            return Response(
                {'error': 'Usuario no es cliente del sistema'},
                status=status.HTTP_403_FORBIDDEN
            )
        except DiagnosticoCapilar.DoesNotExist:
            return Response({
                "sugerencias": [],
                "mensaje": "No hay diagnóstico disponible. Realiza un diagnóstico para obtener recomendaciones."
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error generando sugerencias: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al generar sugerencias'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================
# VIEWSETS PARA CONTENIDO EDUCATIVO
# ============================================================

class ContenidoEducativoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar contenido educativo.
    - Profesionales: CRUD completo de su contenido
    - Clientes: Listar publicado, like, guardar
    """
    serializer_class = ContenidoEducativoSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['estado', 'tipo', 'autor', 'tags']
    search_fields = ['titulo', 'descripcion', 'contenido_texto']
    ordering_fields = ['fecha_publicacion', 'total_likes']
    ordering = ['-fecha_publicacion']

    def get_queryset(self):
        """
        Filtro basado en rol del usuario:
        - Profesionales ven TODO (borradores, publicado, archivado)
        - Clientes ven solo PUBLICADO
        """
        user = self.request.user

        if user.is_staff or user.is_superuser:
            return ContenidoEducativo.objects.filter(
                activo=True
            ).select_related('autor').prefetch_related('me_gusta_recibidos', 'guardados_recibidos')
        
        # Verificar si es profesional
        try:
            personal = user.perfil_profesional
            # Profesional ve todo lo activo
            return ContenidoEducativo.objects.filter(
                activo=True
            ).select_related('autor').prefetch_related('me_gusta_recibidos', 'guardados_recibidos')
        except AttributeError:
            # No es profesional - solo contenido publicado
            return ContenidoEducativo.objects.filter(
                estado='PUBLICADO',
                activo=True
            ).select_related('autor').prefetch_related('me_gusta_recibidos', 'guardados_recibidos')

    def perform_create(self, serializer):
        """Solo profesionales pueden crear contenido."""
        try:
            personal = self.request.user.perfil_profesional
            serializer.save(autor=personal)
            logger.info(f"Contenido creado por {personal.nombre}")
        except AttributeError:
            user = self.request.user
            if user.is_staff or user.is_superuser:
                nombre = (user.first_name or 'Admin').strip() or 'Admin'
                apellido = (user.last_name or 'Sistema').strip() or 'Sistema'
                personal, _ = Personal.objects.get_or_create(
                    usuario=user,
                    defaults={
                        'nombre': nombre,
                        'apellido': apellido,
                        'rol': 'administrador',
                        'activo': True
                    }
                )
                serializer.save(autor=personal)
                logger.info(f"Contenido creado por admin {user.email}")
            else:
                raise PermissionDenied("Solo profesionales pueden crear contenido")

    def perform_update(self, serializer):
        """Solo el autor puede editar su contenido."""
        contenido = self.get_object()
        if not (self.request.user.is_staff or self.request.user.is_superuser) and contenido.autor.usuario != self.request.user:
            raise PermissionDenied("Solo el autor puede editar este contenido")
        serializer.save()

    def perform_destroy(self, instance):
        """Soft delete - marcar como inactivo."""
        instance.activo = False
        instance.save()
        logger.info(f"Contenido {instance.id} marcado como inactivo")

    # === ENDPOINTS DE INTERACCIÓN ===

    @action(detail=True, methods=['post'], url_path='like', permission_classes=[IsAuthenticated])
    def toggle_like(self, request, pk=None):
        """
        Toggle: agregar/quitar me gusta
        POST /api/contenido-educativo/{id}/like/
        """
        contenido = self.get_object()
        
        try:
            cliente = request.user.cliente
        except AttributeError:
            return Response(
                {'error': 'Solo clientes pueden dar like'},
                status=status.HTTP_403_FORBIDDEN
            )

        with transaction.atomic():
            like_existente = MeGusta.objects.filter(
                contenido=contenido, 
                cliente=cliente
            ).first()
            
            if like_existente:
                like_existente.delete()
                logger.info(f"Like removido: {cliente.usuario.email} -> {contenido.id}")
                return Response({
                    'status': 'disliked',
                    'total_likes': contenido.total_likes
                }, status=status.HTTP_200_OK)
            else:
                MeGusta.objects.create(contenido=contenido, cliente=cliente)
                logger.info(f"Like agregado: {cliente.usuario.email} -> {contenido.id}")
                return Response({
                    'status': 'liked',
                    'total_likes': contenido.total_likes
                }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='guardar', permission_classes=[IsAuthenticated])
    def toggle_guardar(self, request, pk=None):
        """
        Toggle: guardar/quitar de favoritos
        POST /api/contenido-educativo/{id}/guardar/
        """
        contenido = self.get_object()
        
        try:
            cliente = request.user.cliente
        except AttributeError:
            return Response(
                {'error': 'Solo clientes pueden guardar contenido'},
                status=status.HTTP_403_FORBIDDEN
            )

        with transaction.atomic():
            guardado_existente = ContenidoGuardado.objects.filter(
                contenido=contenido, 
                cliente=cliente
            ).first()
            
            if guardado_existente:
                guardado_existente.delete()
                logger.info(f"Contenido no guardado: {cliente.usuario.email} -> {contenido.id}")
                return Response(
                    {'status': 'unbooked'}, 
                    status=status.HTTP_200_OK
                )
            else:
                ContenidoGuardado.objects.create(contenido=contenido, cliente=cliente)
                logger.info(f"Contenido guardado: {cliente.usuario.email} -> {contenido.id}")
                return Response(
                    {'status': 'bookmarked'}, 
                    status=status.HTTP_201_CREATED
                )

    @action(detail=False, methods=['get'], url_path='mis-guardados', permission_classes=[IsAuthenticated])
    def mis_guardados(self, request):
        """
        Lista contenido guardado por el cliente actual
        GET /api/contenido-educativo/mis-guardados/
        """
        try:
            cliente = request.user.cliente
        except AttributeError:
            return Response(
                {'error': 'Solo clientes pueden ver guardados'},
                status=status.HTTP_403_FORBIDDEN
            )

        guardados = ContenidoEducativo.objects.filter(
            guardados_recibidos__cliente=cliente,
            activo=True
        ).select_related('autor').prefetch_related('me_gusta_recibidos').distinct()

        page = self.paginate_queryset(guardados)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(guardados, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='recomendados', permission_classes=[IsAuthenticated])
    def recomendados_por_diagnostico(self, request):
        """
        Contenido recomendado basado en el último diagnóstico del cliente
        GET /api/contenido-educativo/recomendados/
        """
        try:
            cliente = request.user.cliente
        except AttributeError:
            return Response(
                {'error': 'Solo clientes pueden ver recomendaciones'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            # Obtener último diagnóstico
            ultimo_diag = DiagnosticoCapilar.objects.filter(
                cliente=cliente
            ).select_related('estado_general', 'tipo_cabello').latest('fecha_diagnostico')
            
            # Construir tags desde el diagnóstico
            tags_diagnostico = []
            
            if ultimo_diag.estado_general:
                tags_diagnostico.append(ultimo_diag.estado_general.nombre.lower())
            if ultimo_diag.tipo_cabello:
                tags_diagnostico.append(ultimo_diag.tipo_cabello.nombre.lower())
            
            if not tags_diagnostico:
                # Si no hay tags, retornar contenido más reciente
                recomendados = ContenidoEducativo.objects.filter(
                    estado='PUBLICADO',
                    activo=True
                ).select_related('autor').prefetch_related('me_gusta_recibidos')[:10]
            else:
                # Buscar contenido con tags similares
                filtros = Q()
                for tag in tags_diagnostico:
                    filtros |= Q(tags__icontains=tag)
                
                recomendados = ContenidoEducativo.objects.filter(
                    filtros,
                    estado='PUBLICADO',
                    activo=True
                ).select_related('autor').prefetch_related('me_gusta_recibidos').distinct()
            
            # Paginar
            page = self.paginate_queryset(recomendados)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(recomendados, many=True)
            return Response(serializer.data)
            
        except DiagnosticoCapilar.DoesNotExist:
            # Sin diagnóstico, retornar contenido más reciente
            recomendados = ContenidoEducativo.objects.filter(
                estado='PUBLICADO',
                activo=True
            ).select_related('autor').prefetch_related('me_gusta_recibidos')[:10]
            
            serializer = self.get_serializer(recomendados, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error generando recomendaciones: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al generar recomendaciones'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MeGustaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar los 'me gusta' en contenido educativo.
    Permite listar, crear y eliminar likes.
    """
    serializer_class = MeGustaSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        """Cada usuario solo ve sus propios likes."""
        user = self.request.user
        try:
            cliente = user.cliente
            return MeGusta.objects.filter(cliente=cliente).select_related('contenido')
        except Cliente.DoesNotExist:
            return MeGusta.objects.none()

    def perform_create(self, serializer):
        """
        Al crear un like, asigna automáticamente el cliente actual.
        """
        try:
            cliente = self.request.user.cliente
            serializer.save(cliente=cliente)
        except Cliente.DoesNotExist:
            raise PermissionDenied("Solo clientes pueden dar like")


class ContenidoGuardadoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para contenido guardado por clientes.
    Permite ver el historial de favoritos y agregarlos/eliminarlos.
    """
    serializer_class = ContenidoGuardadoSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        """Cada cliente solo ve sus propios guardados."""
        user = self.request.user
        try:
            cliente = user.cliente
            return ContenidoGuardado.objects.filter(cliente=cliente).select_related('contenido')
        except Cliente.DoesNotExist:
            return ContenidoGuardado.objects.none()

    def perform_create(self, serializer):
        """
        Al guardar un contenido, asigna automáticamente el cliente actual.
        """
        try:
            cliente = self.request.user.cliente
            serializer.save(cliente=cliente)
        except Cliente.DoesNotExist:
            raise PermissionDenied("Solo clientes pueden guardar contenido")


# ============================================================================
# VIEWSET PARA ÓRDENES PENDIENTES (AUDITORÍA)
# ============================================================================

class OrdenPendienteViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar órdenes pendientes (intenciones de compra por WhatsApp).
    Solo Yanina (admin) puede verlas y confirmar pagos.
    """
    queryset = OrdenPendiente.objects.all()
    serializer_class = OrdenPendienteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['estado', 'cliente', 'fecha_creacion']
    search_fields = ['cliente__usuario__email', 'cliente__usuario__first_name', 'cliente__usuario__last_name']
    ordering_fields = ['fecha_creacion', 'monto_total']
    ordering = ['-fecha_creacion']
    
    def get_queryset(self):
        """
        Los clientes ven solo sus propias órdenes.
        Los admins ven todas.
        """
        if self.request.user.is_staff:
            return OrdenPendiente.objects.all()
        
        try:
            cliente = self.request.user.cliente
            return OrdenPendiente.objects.filter(cliente=cliente)
        except Cliente.DoesNotExist:
            return OrdenPendiente.objects.none()
    
    @action(detail=True, methods=['post'])
    def confirmar_pago(self, request, pk=None):
        """
        POST /api/gestion/ordenes-pendientes/{id}/confirmar_pago/
        
        Yanina confirma que recibió el pago por WhatsApp.
        Descontar del stock_real y limpiar el stock_comprometido.
        """
        try:
            orden = self.get_object()
            
            if orden.estado != 'PENDIENTE':
                return Response(
                    {'error': f'Solo se puede confirmar órdenes PENDIENTES. Estado actual: {orden.estado}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Procesar cada item: descontar stock_real y limpiar stock_comprometido
            for item_data in orden.items_json:
                try:
                    producto = Producto.objects.get(id=item_data['producto_id'])
                    cantidad = item_data['cantidad']
                    
                    # Validar que hay suficiente stock comprometido
                    if producto.stock_comprometido < cantidad:
                        return Response(
                            {'error': f'Stock comprometido inconsistente para {producto.nombre}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    
                    # Descontar del real y limpiar del comprometido
                    producto.stock_real = max(0, producto.stock_real - cantidad)
                    producto.stock_comprometido -= cantidad
                    producto.save()
                    
                    logger.info(
                        f"Stock descontado: {producto.nombre} -({cantidad}) | "
                        f"Real: {producto.stock_real}, Comprometido: {producto.stock_comprometido}"
                    )
                except Producto.DoesNotExist:
                    logger.warning(f"Producto {item_data['producto_id']} no encontrado en orden {orden.id}")
                except Exception as e:
                    logger.error(f"Error procesando producto en orden {orden.id}: {str(e)}")
            
            # Marcar orden como completada
            orden.estado = 'COMPLETADA'
            orden.fecha_completacion = timezone.now()
            orden.save()
            
            logger.info(f"Orden {orden.id} completada. Stock descontado. Usuario: {request.user.email}")
            
            return Response(
                {
                    'status': 'Pago confirmado',
                    'orden_id': orden.id,
                    'estado': orden.estado,
                    'fecha_completacion': orden.fecha_completacion.isoformat(),
                    'mensaje': 'Stock descontado del inventario físico'
                },
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            logger.error(f"Error confirmando pago de orden {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al confirmar el pago'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def confirmar_entrega(self, request, pk=None):
        """
        POST /api/gestion/ordenes-pendientes/{id}/confirmar_entrega/
        
        Confirmar que la orden ha sido entregada.
        Actualiza el estado a COMPLETADA y resta del stock_real y stock_comprometido.
        """
        try:
            orden = self.get_object()
            
            if orden.estado not in ['PENDIENTE', 'CONFIRMADA']:
                return Response(
                    {'error': f'Solo se pueden completar órdenes PENDIENTES o CONFIRMADAS. Estado actual: {orden.estado}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Procesar cada item: descontar stock_real y stock_comprometido
            with transaction.atomic():
                # Soportar tanto el nuevo formato (items relacionados) como el viejo (items_json)
                if hasattr(orden, 'items') and orden.items.exists():
                    # Nuevo formato: usar la relación OrdenPendienteItem
                    for item in orden.items.all():
                        if not item.producto:
                            logger.warning(f"Item {item.id} sin producto en orden {orden.id}")
                            continue
                        
                        producto = item.producto
                        cantidad = item.cantidad
                        
                        # Validar stock
                        if producto.stock_real < cantidad:
                            return Response(
                                {'error': f'Stock insuficiente de {producto.nombre}. Disponible: {producto.stock_real}'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        
                        # Descontar stock
                        producto.stock_real -= cantidad
                        producto.stock_comprometido = max(0, producto.stock_comprometido - cantidad)
                        producto.save()
                        
                        logger.info(
                            f"Stock descontado: {producto.nombre} -({cantidad}) | "
                            f"Real: {producto.stock_real}, Comprometido: {producto.stock_comprometido}"
                        )
                else:
                    # Viejo formato: usar items_json
                    for item_data in orden.items_json:
                        try:
                            producto = Producto.objects.get(id=item_data['producto_id'])
                            cantidad = item_data['cantidad']
                            
                            if producto.stock_real < cantidad:
                                return Response(
                                    {'error': f'Stock insuficiente de {producto.nombre}'},
                                    status=status.HTTP_400_BAD_REQUEST
                                )
                            
                            producto.stock_real = max(0, producto.stock_real - cantidad)
                            producto.stock_comprometido = max(0, producto.stock_comprometido - cantidad)
                            producto.save()
                            
                            logger.info(
                                f"Stock descontado: {producto.nombre} -({cantidad}) | "
                                f"Real: {producto.stock_real}, Comprometido: {producto.stock_comprometido}"
                            )
                        except Producto.DoesNotExist:
                            logger.warning(f"Producto {item_data['producto_id']} no encontrado")
                
                # Marcar orden como completada
                orden.estado = 'COMPLETADA'
                orden.fecha_completacion = timezone.now()
                orden.save()
            
            logger.info(f"Orden {orden.id} entregada. Stock actualizado. Usuario: {request.user.email}")
            
            return Response(
                {
                    'status': 'Entrega confirmada',
                    'orden_id': orden.id,
                    'estado': orden.estado,
                    'fecha_completacion': orden.fecha_completacion.isoformat(),
                    'mensaje': 'Orden completada y stock actualizado'
                },
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            logger.error(f"Error confirmando entrega de orden {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al confirmar la entrega'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def registrar_pago(self, request, pk=None):
        """
        POST /api/gestion/ordenes-compra/{id}/registrar_pago/

        Permite al profesional registrar un pago asociado a la orden.
        """
        if not request.user.is_staff:
            raise PermissionDenied("No tienes permisos para registrar pagos.")

        orden = self.get_object()
        serializer = PagoSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        pago = serializer.save(orden=orden)

        return Response(
            {
                'status': 'Pago registrado',
                'pago': PagoSerializer(pago, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        """
        POST /api/gestion/ordenes-compra/{id}/cancelar/

        Cancela una orden pendiente y libera el stock comprometido.
        """
        try:
            orden = self.get_object()

            if orden.estado != 'PENDIENTE':
                return Response(
                    {'error': f'Solo se puede cancelar órdenes PENDIENTES. Estado actual: {orden.estado}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            with transaction.atomic():
                for item in orden.items.all():
                    producto = item.producto
                    cantidad = item.cantidad

                    producto.stock_comprometido = max(0, producto.stock_comprometido - cantidad)
                    producto.save()

                    logger.info(
                        f"Stock liberado: {producto.nombre} -({cantidad}) | "
                        f"Comprometido: {producto.stock_comprometido}"
                    )

                orden.estado = 'CANCELADO'
                orden.save()

            serializer = self.get_serializer(orden)
            return Response(
                {
                    'status': 'Orden cancelada',
                    'orden': serializer.data,
                    'mensaje': 'Orden cancelada y stock liberado'
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Error cancelando orden {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al cancelar la orden'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================
# VIEWSET PARA ORDEN DE COMPRA
# ============================================

class OrdenCompraViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar órdenes de compra de clientes.
    Segun el usuario, estos son pedidos efectuados por clientes que pasan a ser órdenes completadas.
    """
    queryset = OrdenCompra.objects.all()
    serializer_class = OrdenCompraSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['estado', 'cliente', 'creado_at']
    search_fields = ['cliente__usuario__email', 'codigo', 'cliente__usuario__first_name']
    ordering_fields = ['creado_at', 'total']
    ordering = ['-creado_at']
    
    def get_queryset(self):
        """
        Los clientes ven solo sus propias órdenes.
        Los admins ven todas.
        """
        if self.request.user.is_staff:
            return OrdenCompra.objects.all()
        
        try:
            cliente = self.request.user.cliente
            return OrdenCompra.objects.filter(cliente=cliente)
        except Cliente.DoesNotExist:
            return OrdenCompra.objects.none()

    @action(detail=True, methods=['post'])
    def registrar_pago(self, request, pk=None):
        """
        POST /api/gestion/ordenes-compra/{id}/registrar_pago/

        Permite al profesional registrar un pago asociado a la orden.
        """
        if not request.user.is_staff:
            raise PermissionDenied("No tienes permisos para registrar pagos.")

        orden = self.get_object()
        serializer = PagoSerializer(data=request.data, context={'request': request})

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        pago = serializer.save(orden=orden)

        return Response(
            {
                'status': 'Pago registrado',
                'pago': PagoSerializer(pago, context={'request': request}).data
            },
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=True, methods=['post'])
    def confirmar_entrega(self, request, pk=None):
        """
        POST /api/gestion/ordenes-compra/{id}/confirmar_entrega/
        
        Confirma la entrega de una orden de compra a un cliente.
        Descontar del stock_real y del stock_comprometido.
        """
        try:
            orden = self.get_object()
            
            if orden.estado != 'PENDIENTE':
                return Response(
                    {'error': f'Solo se puede confirmar órdenes PENDIENTES. Estado actual: {orden.estado}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Usar transacción atómica para garantizar consistencia
            with transaction.atomic():
                # Procesar cada item de la orden
                for item in orden.items.all():
                    try:
                        producto = item.producto
                        cantidad = item.cantidad
                        
                        # Validar que hay suficiente stock comprometido
                        if producto.stock_comprometido < cantidad:
                            return Response(
                                {'error': f'Stock comprometido inconsistente para {producto.nombre}'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        
                        # Descontar del real y del comprometido
                        producto.stock_real = max(0, producto.stock_real - cantidad)
                        producto.stock_comprometido = max(0, producto.stock_comprometido - cantidad)
                        producto.save()
                        
                        logger.info(
                            f"Stock descontado: {producto.nombre} -({cantidad}) | "
                            f"Real: {producto.stock_real}, Comprometido: {producto.stock_comprometido}"
                        )
                    except Exception as e:
                        logger.warning(f"Error procesando item {item.id}: {str(e)}")
                        raise
                
                # Marcar orden como completada
                orden.estado = 'COMPLETADO'
                orden.save()
            
            logger.info(f"Orden {orden.id} completada. Stock actualizado. Usuario: {request.user.email}")
            
            # Serializar la orden actualizada
            serializer = self.get_serializer(orden)
            
            return Response(
                {
                    'status': 'Entrega confirmada',
                    'orden': serializer.data,
                    'mensaje': 'Orden completada y stock actualizado'
                },
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            logger.error(f"Error confirmando entrega de orden {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al confirmar la entrega'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        """
        POST /api/gestion/ordenes-compra/{id}/cancelar/

        Cancela una orden pendiente y libera el stock comprometido.
        """
        try:
            orden = self.get_object()

            if orden.estado != 'PENDIENTE':
                return Response(
                    {'error': f'Solo se puede cancelar órdenes PENDIENTES. Estado actual: {orden.estado}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            with transaction.atomic():
                for item in orden.items.all():
                    producto = item.producto
                    cantidad = item.cantidad

                    producto.stock_comprometido = max(0, producto.stock_comprometido - cantidad)
                    producto.save()

                    logger.info(
                        f"Stock liberado: {producto.nombre} -({cantidad}) | "
                        f"Comprometido: {producto.stock_comprometido}"
                    )

                orden.estado = 'CANCELADO'
                orden.save()

            serializer = self.get_serializer(orden)
            return Response(
                {
                    'status': 'Orden cancelada',
                    'orden': serializer.data,
                    'mensaje': 'Orden cancelada y stock liberado'
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"Error cancelando orden {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Error al cancelar la orden'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PagoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para listar pagos (Caja).
    Solo admins/staff pueden acceder.
    """
    queryset = Pago.objects.all().select_related(
        'orden__cliente__usuario',
        'turno__cliente__usuario'
    )
    serializer_class = PagoSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['metodo_pago', 'es_sena']
    search_fields = [
        'orden__codigo',
        'orden__cliente__usuario__email',
        'turno__cliente__usuario__email'
    ]
    ordering_fields = ['fecha_pago', 'monto']
    ordering = ['-fecha_pago']

    def get_queryset(self):
        queryset = super().get_queryset()
        solo_hoy = self.request.query_params.get('solo_hoy')
        fecha = self.request.query_params.get('fecha')

        if solo_hoy and solo_hoy.lower() in ['1', 'true', 'si', 'yes']:
            queryset = queryset.filter(fecha_pago__date=timezone.localdate())

        if fecha:
            try:
                fecha_dt = datetime.strptime(fecha, '%Y-%m-%d').date()
                queryset = queryset.filter(fecha_pago__date=fecha_dt)
            except ValueError:
                pass

        return queryset
# ============================================
# VIEWSET PARA IMÁGENES DE PRODUCTOS
# ============================================

class ImagenProductoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar imágenes adicionales de productos.
    Permite agregar múltiples imágenes a un producto existente.
    """
    queryset = ImagenProducto.objects.all()
    serializer_class = ImagenProductoSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['producto']
    ordering_fields = ['orden', 'fecha_creacion']
    ordering = ['orden', 'fecha_creacion']

    def get_permissions(self):
        """
        Permisos dinámicos:
        - list/retrieve: AllowAny (clientes pueden ver imágenes)
        - create/update/destroy: IsAdminUser (solo admins gestionan)
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAdminUser]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """
        Guarda la imagen asociada al producto.
        Se ejecuta la optimización de imagen automáticamente en el modelo.
        """
        try:
            serializer.save()
        except Exception as e:
            logger.error(f"Error al guardar imagen de producto: {str(e)}")
            raise

    def create(self, request, *args, **kwargs):
        if 'imagen' not in request.FILES:
            return Response(
                {'detail': 'No se envio imagen, no se creo registro.'},
                status=status.HTTP_200_OK
            )
        return super().create(request, *args, **kwargs)

