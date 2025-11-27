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
)

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

class ServicioViewSet(viewsets.ReadOnlyModelViewSet):
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


class ServicioViewSet(viewsets.ReadOnlyModelViewSet):
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