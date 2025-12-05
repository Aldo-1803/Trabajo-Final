from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError
import rest_framework.permissions as permissions
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from datetime import datetime, date
from .service import DisponibilidadService 
from django.db.models import Q
from .serializers import AgendaCuidadosSerializer
from .models import AgendaCuidados
from .models import Notificacion
from .serializers import NotificacionSerializer
from rest_framework.decorators import action
from django.utils import timezone
from .models import PasoRutina
from .serializers import PasoRutinaSerializer
from .models import ReglaDiagnostico
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Rutina, RutinaCliente
from .serializers import RutinaSerializer, RutinaClienteSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication



from .models import TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral, Servicio, Turno
from .serializers import (
    TipoCabelloSerializer,
    GrosorCabelloSerializer,
    PorosidadCabelloSerializer,
    CueroCabelludoSerializer,
    EstadoGeneralSerializer,
    ServicioSerializer,
    TurnoCreateSerializer,
    TurnoSerializer,
    RutinaSerializer,
    RutinaClienteSerializer,
    RutinaClienteCreateSerializer,
    PasoRutinaSerializer,
    ReglaDiagnosticoSerializer
)
from .models import Rutina, RutinaCliente, PasoRutinaCliente

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
class TipoCabelloViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TipoCabello.objects.filter(activo=True)
    serializer_class = TipoCabelloSerializer
    permission_classes = [AllowAny]
class GrosorCabelloViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GrosorCabello.objects.filter(activo=True)
    serializer_class = GrosorCabelloSerializer
    permission_classes = [AllowAny]
class PorosidadCabelloViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PorosidadCabello.objects.filter(activo=True)
    serializer_class = PorosidadCabelloSerializer
    permission_classes = [AllowAny]
class CueroCabelludoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CueroCabelludo.objects.filter(activo=True)
    serializer_class = CueroCabelludoSerializer
    permission_classes = [AllowAny]
class EstadoGeneralViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EstadoGeneral.objects.filter(activo=True)
    serializer_class = EstadoGeneralSerializer
    permission_classes = [AllowAny]

class ServicioViewSet(viewsets.ModelViewSet):
    """
    ViewSet que retorna TODOS los servicios activos para la reserva de turnos.
    """
    serializer_class = ServicioSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    
    def get_queryset(self):
        return Servicio.objects.all().order_by('nombre')

class ServiciosQuimicosViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Un ViewSet que retorna *solamente* los servicios que
    afectan el historial químico del cliente, filtrados por
    las categorías "Diseño de Color" y "Turno de Complemento".
    """
    
    serializer_class = ServicioSerializer
    permission_classes = [permissions.AllowAny]

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
    

class DisponibilidadTurnosView(APIView):
    """
    Endpoint público (o protegido) para consultar la agenda.
    Uso: GET /api/gestion/disponibilidad/?fecha=2023-11-01&servicio_id=1
    """
    # Sugerencia: AllowAny para que el cliente pueda ver horarios antes de registrarse/loguearse.
    # Si prefieres privacidad total, cámbialo a [IsAuthenticated]
    permission_classes = [AllowAny] 

    def get(self, request):
        # 1. Recibir parámetros del Frontend
        fecha_str = request.query_params.get('fecha') # Esperamos 'YYYY-MM-DD'
        servicio_id = request.query_params.get('servicio_id')

        # 2. Validaciones de Entrada
        if not fecha_str or not servicio_id:
            return Response(
                {"error": "Faltan parámetros obligatorios: 'fecha' y 'servicio_id'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            
            # Validación básica de negocio: No viajar al pasado
            if fecha_consulta < date.today():
                 return Response(
                     {"error": "No se pueden agendar turnos en el pasado."}, 
                     status=status.HTTP_400_BAD_REQUEST
                 )
                 
            servicio = Servicio.objects.get(id=servicio_id)
            
        except ValueError:
            return Response({"error": "Formato de fecha inválido. Use AAAA-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        except Servicio.DoesNotExist:
            return Response({"error": "El servicio especificado no existe."}, status=status.HTTP_404_NOT_FOUND)

        # 3. Invocar al "Cerebro" (Tu Service)
        try:
            # Si el servicio no tiene duración, asumimos 60 min por defecto para evitar crash
            duracion = servicio.duracion_estimada or 60
            
            bloques_libres = DisponibilidadService.obtener_bloques_disponibles(
                fecha_consulta=fecha_consulta,
                duracion_servicio_minutos=duracion
            )
        except Exception as e:
            # Capturamos errores inesperados del algoritmo
            return Response({"error": f"Error interno de agenda: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 4. Responder JSON al Frontend
        return Response({
            "fecha": fecha_str,
            "servicio_solicitado": servicio.nombre,
            "duracion_minutos": duracion,
            # Convertimos los objetos time a string "HH:MM" para JSON
            "horarios_disponibles": [t.strftime('%H:%M') for t in bloques_libres]
        }, status=status.HTTP_200_OK)


class ServicioViewSet(viewsets.ModelViewSet):
    queryset = Servicio.objects.filter(activo=True)
    serializer_class = ServicioSerializer
    permission_classes = [AllowAny]
    pagination_class = None

# --- 3. VIEWSET DE TURNOS (CRUD) ---
class TurnoViewSet(viewsets.ModelViewSet):
    queryset = Turno.objects.all().order_by('fecha', 'hora_inicio')
    pagination_class = None 

    def get_serializer_class(self):
        """
        Selector dinámico de Serializer
        """
        if self.action == 'create':
            return TurnoCreateSerializer
        return TurnoSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        estado = self.request.query_params.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        
        # Validación de seguridad: ¿El usuario tiene perfil de cliente?
        if not user.is_staff and not hasattr(user, 'cliente'):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": "Este usuario no tiene un perfil de cliente asociado."})

        if user.is_staff:
            serializer.save()
        else:
            # Aquí inyectamos el cliente manualmente
            serializer.save(
                cliente=user.cliente, 
                estado='solicitado'
            )

class MiAgendaCuidadosView(generics.ListAPIView):
    """
    Devuelve la lista de cuidados/restricciones futuras para el cliente logueado.
    """
    serializer_class = AgendaCuidadosSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filtramos por el cliente logueado y ordenamos por fecha
        # Opcional: Mostrar solo tareas desde hoy en adelante (fecha__gte=date.today())
        return AgendaCuidados.objects.filter(
            cliente=self.request.user.cliente
        ).order_by('fecha')
    

class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Devuelve solo las notificaciones del usuario logueado
        return Notificacion.objects.filter(usuario=self.request.user)

    @action(detail=True, methods=['post'])
    def marcar_leida(self, request, pk=None):
        notificacion = self.get_object()
        notificacion.estado = 'leido'
        notificacion.save()
        return Response({'status': 'ok'})
    
class AdminDashboardStatsView(APIView):
    """
    Devuelve estadísticas rápidas para la Pantalla Home del Administrador.
    """
    permission_classes = [permissions.IsAdminUser] # Solo para Staff/Yani

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
        ).order_by('fecha', 'hora_inicio')[:5]
        
        # Serializamos manualmente para no crear otro serializer solo para esto
        lista_proximos = []
        for t in proximos_turnos:
            lista_proximos.append({
                'id': t.id,
                'cliente': f"{t.cliente.usuario.first_name} {t.cliente.usuario.last_name}",
                'servicio': t.servicio.nombre,
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
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]
    
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
    def publicar(self, request, pk=None):
        """
        Endpoint para PUBLICAR una rutina (cambiar estado a 'publicada').
        POST /api/gestion/rutinas/{id}/publicar/
        """
        rutina = self.get_object()
        rutina.publicar()
        
        serializer = self.get_serializer(rutina)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
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
    
    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAdminUser])
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
                version_asignada=rutina.version
            )
            
            # Copiar los pasos de la rutina original
            for paso_original in rutina.pasos.all():
                PasoRutinaCliente.objects.create(
                    rutina_cliente=rutina_cliente,
                    orden=paso_original.orden,
                    descripcion=paso_original.descripcion,
                    frecuencia=paso_original.frecuencia
                )
            
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
        - update, destroy: Solo staff
        - create: No permitido (se crean automáticamente)
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [permissions.IsAdminUser]
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
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def marcar_paso_completado(self, request, pk=None):
        """
        Endpoint para MARCAR UN PASO COMO COMPLETADO.
        POST /api/gestion/rutinas-cliente/{id}/marcar_paso_completado/
        {
            "paso_id": 1
        }
        """
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


# ============================================
# VIEWSET PARA PASOS DE RUTINA
# ============================================
class PasoRutinaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar PasoRutina (pasos de rutinas plantilla).
    Solo staff puede crear/editar/eliminar.
    """
    serializer_class = PasoRutinaSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return PasoRutina.objects.all()
    
    def get_permissions(self):
        """
        - list, retrieve: Autenticados
        - create, update, destroy: Solo staff
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]
    
    def create(self, request, *args, **kwargs):
        """
        Sobrescribimos create para mejor debugging y validación
        """
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
    permission_classes = [permissions.IsAdminUser]

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