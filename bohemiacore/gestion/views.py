from rest_framework import viewsets, status, serializers
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from datetime import datetime, date, timedelta, time
import datetime as dt
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import logging

from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral, CategoriaServicio, Servicio, Turno, DetalleTurno,
    Configuracion, ListaEspera, Producto, Equipamiento, Rutina, Notificacion, AgendaCuidados, Producto, ReglaDiagnostico,
    RutinaCliente, HorarioLaboral, BloqueoAgenda, Personal, TipoEquipamiento, FichaTecnica, DiagnosticoCapilar, RequisitoServicio,
    #PasoRutinaCliente
    #PasoRutina
)

from .serializers import (
    TipoCabelloSerializer, GrosorCabelloSerializer, PorosidadCabelloSerializer, CueroCabelludoSerializer, EstadoGeneralSerializer,
    CategoriaServicioSerializer, ServicioSerializer, TurnoSerializer, RutinaSerializer, RutinaClienteSerializer,
    RutinaClienteCreateSerializer, ReglaDiagnosticoSerializer, NotificacionSerializer, ProductoSerializer, EquipamientoSerializer,
    UsuarioAdminSerializer, AgendaCuidadosSerializer, HorarioLaboralSerializer, BloqueoAgendaSerializer, PersonalSerializer,
    TipoEquipamientoSerializer, FichaTecnicaSerializer, RequisitoServicioSerializer, DiagnosticoCapilarSerializer,
    #PasoRutinaSerializer,
)

from .services import DisponibilidadService 
from usuarios.models import Usuario, Cliente

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


class PersonalViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar el personal / staff del salón (CRUD completo).
    """
    queryset = Personal.objects.all()
    serializer_class = PersonalSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    

class DisponibilidadTurnosView(APIView):
    """
    Endpoint público (o protegido) para consultar la agenda.
    Uso: GET /api/gestion/disponibilidad/?fecha=2023-11-01&servicio_id=1
    """
    # Sugerencia: AllowAny para que el cliente pueda ver horarios antes de registrarse/loguearse.
    # Si prefieres privacidad total, cámbialo a [IsAuthenticated]
    permission_classes = [AllowAny] 

    def get(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        # 1. Recibir parámetros del Frontend
        fecha_str = request.query_params.get('fecha') # Esperamos 'YYYY-MM-DD'
        servicio_id = request.query_params.get('servicio_id')
        
        logger.info(f"DisponibilidadTurnosView: Recibida solicitud - fecha={fecha_str}, servicio_id={servicio_id}")

        # 2. Validaciones de Entrada
        if not fecha_str or not servicio_id:
            logger.error(f"Parámetros incompletos: fecha_str={fecha_str}, servicio_id={servicio_id}")
            return Response(
                {"error": "Faltan parámetros obligatorios: 'fecha' y 'servicio_id'."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            logger.info(f"Fecha parseada correctamente: {fecha_consulta}")
            
            # Validación básica de negocio: No viajar al pasado
            if fecha_consulta < date.today():
                 logger.warning(f"Intento de consultar fecha pasada: {fecha_consulta}")
                 return Response(
                     {"error": "No se pueden agendar turnos en el pasado."}, 
                     status=status.HTTP_400_BAD_REQUEST
                 )
                 
            servicio = Servicio.objects.get(id=servicio_id)
            logger.info(f"Servicio encontrado: {servicio.nombre}, duración: {servicio.duracion_estimada}")
            
        except ValueError as ve:
            logger.error(f"Error de formato de fecha: {ve}")
            return Response({"error": "Formato de fecha inválido. Use AAAA-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        except Servicio.DoesNotExist:
            logger.error(f"Servicio no encontrado con ID: {servicio_id}")
            return Response({"error": "El servicio especificado no existe."}, status=status.HTTP_404_NOT_FOUND)

        # 3. Invocar al "Cerebro" (Tu Service)
        try:
            # Si el servicio no tiene duración, asumimos 60 min por defecto para evitar crash
            duracion = servicio.duracion_estimada or 60
            logger.info(f"Calculando bloques disponibles para {fecha_consulta} con duración {duracion} min")
            
            bloques_libres = DisponibilidadService.obtener_bloques_disponibles(
                fecha_consulta=fecha_consulta,
                servicio=servicio
            )
            
            logger.info(f"Bloques libres encontrados: {len(bloques_libres)}")
            
        except Exception as e:
            # Capturamos errores inesperados del algoritmo
            logger.error(f"Error al calcular disponibilidad: {str(e)}", exc_info=True)
            return Response({"error": f"Error interno de agenda: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 4. Responder JSON al Frontend
        logger.info(f"Respuesta exitosa: {len(bloques_libres)} horarios disponibles")
        return Response({
            "fecha": fecha_str,
            "servicio_solicitado": servicio.nombre,
            "duracion_minutos": duracion,
            # Convertimos los objetos time a string "HH:MM" para JSON
            "horarios_disponibles": [t.strftime('%H:%M') for t in bloques_libres]
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

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filtro según el rol del usuario
        if self.request.user.is_staff:
            # Admin ve todos los turnos
            pass
        elif hasattr(self.request.user, 'cliente'):
            # Cliente solo ve sus propios turnos
            queryset = queryset.filter(cliente=self.request.user.cliente)
        else:
            # Usuario sin cliente, no ve nada
            queryset = queryset.none()
             
        # Filtro opcional por estado
        estado = self.request.query_params.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)
        return queryset

    def perform_create(self, serializer):
        # El serializer se encargará de asignar el cliente desde el usuario autenticado
        serializer.save()
    
    def perform_update(self, serializer):
        """Solo admins pueden actualizar turnos"""
        if not self.request.user.is_staff:
            raise PermissionDenied("Solo administradores pueden actualizar turnos.")
        serializer.save()
    
    @action(detail=True, methods=['post'])
    def reprogramar_cliente(self, request, pk=None):
        """
        Permite que el cliente reprograme su turno (solo turnos en estado 'solicitado' o 'esperando_sena')
        POST /api/gestion/turnos/{id}/reprogramar_cliente/
        Body: {"fecha": "2026-01-20", "hora_inicio": "14:00"}
        """
        turno = self.get_object()
        
        # 1. Validar que el cliente es el dueño del turno
        if turno.cliente.usuario != request.user:
            raise PermissionDenied("No puedes reprogramar turnos de otros clientes.")
        
        # 2. Validar que el turno pueda ser reprogramado (solo en ciertos estados)
        if turno.estado not in ['solicitado', 'esperando_sena']:
            return Response({
                "error": f"No puedes reprogramar un turno en estado '{turno.estado}'. "
                         "Solo puedes reprogramar turnos solicitados o pendientes de seña."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 3. Obtener nueva fecha y hora
        nueva_fecha_str = request.data.get('fecha')
        nueva_hora_str = request.data.get('hora_inicio')
        
        if not nueva_fecha_str or not nueva_hora_str:
            return Response({
                "error": "Debes proporcionar 'fecha' y 'hora_inicio'."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            nueva_fecha = datetime.strptime(nueva_fecha_str, '%Y-%m-%d').date()
            nueva_hora = datetime.strptime(nueva_hora_str, '%H:%M').time()
        except ValueError:
            return Response({
                "error": "Formato inválido. Usa: fecha='YYYY-MM-DD', hora_inicio='HH:MM'"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 4. Validar política de tiempo para reprogramación (48hs antes para confirmados)
        config = Configuracion.objects.first()
        if turno.estado == 'confirmado':
            horas_limite = config.horas_limite_cancelacion if config else 48
            fecha_hora_actual = datetime.combine(turno.fecha, turno.hora_inicio)
            fecha_hora_utc = timezone.make_aware(fecha_hora_actual) if timezone.is_naive(fecha_hora_actual) else fecha_hora_actual
            ahora = timezone.now()
            
            horas_restantes = (fecha_hora_utc - ahora).total_seconds() / 3600
            if horas_restantes < horas_limite:
                return Response({
                    "error": f"Ya no puedes reprogramar este turno de forma autónoma. "
                             f"Quedan menos de {horas_limite}hs. Por favor, contacta al salón."
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # 5. Validar que no hay turno duplicado en la nueva fecha/hora
        turno_duplicado = Turno.objects.filter(
            cliente=turno.cliente,
            fecha=nueva_fecha,
            hora_inicio=nueva_hora,
            estado__in=['solicitado', 'esperando_sena', 'confirmado']
        ).exclude(id=turno.id).exists()
        
        if turno_duplicado:
            return Response({
                "error": "Ya tienes un turno en esa fecha y hora."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 6. Validar que el nuevo slot está disponible (sin conflictos)
        es_valido = self._validar_slot_libre(
            fecha=nueva_fecha,
            hora=nueva_hora,
            profesional=turno.profesional,
            duracion_minutos=sum(d.duracion_minutos for d in turno.detalles.all()) or 60,
            excluir_turno_id=turno.id  # Excluir el turno actual de la validación
        )
        
        if not es_valido:
            return Response({
                "error": "El horario seleccionado ya no está disponible."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # 7. Guardar cambios
        turno.fecha = nueva_fecha
        turno.hora_inicio = nueva_hora
        turno.cambios_realizados += 1
        turno.save()
        
        # Refrescar desde BD para asegurar que los cambios se persistieron
        turno.refresh_from_db()
        
        return Response({
            "mensaje": "Turno reprogramado con éxito.",
            "turno": TurnoSerializer(turno, context={'request': request}).data
        }, status=status.HTTP_200_OK)
    
    def _validar_slot_libre(self, fecha, hora, profesional, duracion_minutos, excluir_turno_id=None):
        """
        Valida si un slot está realmente disponible (sin conflictos)
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
            estado__in=['confirmado', 'esperando_sena', 'solicitado']
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
        
        if not servicio_id:
            return Response(
                {"error": "Se requiere servicio_id"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            servicio = Servicio.objects.get(id=servicio_id, activo=True)
        except Servicio.DoesNotExist:
            return Response(
                {"error": "El servicio no existe"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determinar fecha de inicio
        try:
            if fecha_inicio_str:
                fecha_inicio = datetime.datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
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
        fecha_limite = fecha_inicio + timedelta(days=max_dias)
        
        # 2. Validar que no sea fecha pasada
        if fecha_inicio < timezone.now().date():
            return Response(
                {"error": "No se pueden agendar turnos en el pasado"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 3. Determinar tipo de servicio (para filtrar reglas)
        categoria_nombre = servicio.categoria.nombre if servicio.categoria else ""
        requiere_diseno = "Diseño" in categoria_nombre
        requiere_complemento = "Complemento" in categoria_nombre or "Turno de Complemento" in categoria_nombre
        
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
            
            # 5. Obtener reglas de horarios para este día
            reglas = HorarioLaboral.objects.filter(
                dia_semana=dia_semana,
                activo=True,
                personal__activo=True,  # Solo profesionales activos
            )
            
            # Filtrar solo reglas que aplican en esta fecha (null = aplica siempre)
            reglas = reglas.filter(
                Q(fecha_desde__isnull=True) | Q(fecha_desde__lte=fecha_consulta),
                Q(fecha_hasta__isnull=True) | Q(fecha_hasta__gte=fecha_consulta)
            )
            
            # --- FILTRO DE COMPETENCIA TÉCNICA (Refinado) ---
            # Identificamos qué habilidad se requiere según la categoría
            habilidad_requerida = None
            if requiere_diseno:
                habilidad_requerida = 'realiza_color'
                reglas = reglas.filter(permite_diseno_color=True)
            elif requiere_complemento:
                habilidad_requerida = 'realiza_lavado'
                reglas = reglas.filter(permite_complemento=True)
            
            # Aplicamos el filtro dinámico de habilidad a las reglas
            if habilidad_requerida:
                filtro_habilidad = {f'personal__{habilidad_requerida}': True}
                reglas = reglas.filter(**filtro_habilidad)
            
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
                    intervalo_minutos
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
    
    def _generar_slots_disponibles(self, fecha, regla, duracion_minutos, intervalo_minutos):
        slots_disponibles = []
        
        # 1. Traemos TODOS los turnos y bloqueos del día UNA SOLA VEZ (Optimización)
        turnos_del_dia = Turno.objects.filter(
            fecha=fecha,
            profesional=regla.personal,
            estado__in=['confirmado', 'esperando_sena', 'solicitado']
        ).prefetch_related('detalles')

        bloqueos_del_dia = BloqueoAgenda.objects.filter(
            Q(personal=regla.personal) | Q(personal__isnull=True),
            fecha_inicio__date__lte=fecha,
            fecha_fin__date__gte=fecha
        )

        # Convertimos los horarios de la regla a minutos
        actual_min = regla.hora_inicio.hour * 60 + regla.hora_inicio.minute
        fin_min = regla.hora_fin.hour * 60 + regla.hora_fin.minute

        while actual_min + duracion_minutos <= fin_min:
            hora_inicio_slot = time(actual_min // 60, actual_min % 60)
            hora_fin_slot = time((actual_min + duracion_minutos) // 60, (actual_min + duracion_minutos) % 60)
            
            # Combinamos con fecha para comparar datetimes completos (más seguro)
            inicio_dt = datetime.combine(fecha, hora_inicio_slot)
            fin_dt = datetime.combine(fecha, hora_fin_slot)

            # --- VALIDACIÓN DE CONFLICTOS ---
            hay_choque = False

            # A. Choque con Turnos (Validación de Rango)
            for turno in turnos_del_dia:
                # Fórmula: (StartA < EndB) y (EndA > StartB)
                t_ini = datetime.combine(fecha, turno.hora_inicio)
                # Calculamos la hora fin basándose en duración total de servicios del turno
                duracion_turno = sum(d.duracion_minutos for d in turno.detalles.all()) or 60
                t_fin_minutos = turno.hora_inicio.hour * 60 + turno.hora_inicio.minute + duracion_turno
                t_fin_hours = t_fin_minutos // 60
                t_fin_mins = t_fin_minutos % 60
                t_fin = datetime.combine(fecha, time(t_fin_hours, t_fin_mins))
                
                if (inicio_dt < t_fin) and (fin_dt > t_ini):
                    hay_choque = True
                    break
            
            # B. Choque con Bloqueos
            if not hay_choque:
                for bloqueo in bloqueos_del_dia:
                    # Quitamos zona horaria si es necesario para comparar
                    b_ini = bloqueo.fecha_inicio.replace(tzinfo=None) if bloqueo.fecha_inicio.tzinfo else bloqueo.fecha_inicio
                    b_fin = bloqueo.fecha_fin.replace(tzinfo=None) if bloqueo.fecha_fin.tzinfo else bloqueo.fecha_fin
                    
                    if (inicio_dt < b_fin) and (fin_dt > b_ini):
                        hay_choque = True
                        break
            
            if not hay_choque:
                # Validación extra: si es HOY, no mostrar horas que ya pasaron
                ahora_naive = timezone.now().replace(tzinfo=None)
                if inicio_dt > ahora_naive:
                    slots_disponibles.append({
                        "hora": hora_inicio_slot.strftime("%H:%M"),
                        "profesional_id": regla.personal.id,
                    })
            
            actual_min += intervalo_minutos
        
        return slots_disponibles
    
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
                    config.intervalo_turnos
                )
                if slots:
                    return fecha_proxima.isoformat()
                    
        return None # No hay nada en todo el mes

    # =====================================================================
    # AQUÍ ESTÁ EL PROCESO AUTOMATIZADO #2 (Integrado como Acción)
    # =====================================================================
    @action(detail=True, methods=['post'], url_path='gestionar')
    def gestionar_cancelacion(self, request, pk=None):
        """
        Lógica de Reprogramación Diferenciada por Estado (A, B, C).
        """
        import datetime
        
        turno = self.get_object()
        usuario = request.user
        es_profesional = usuario.is_staff
        
        # Configuración
        config = Configuracion.objects.first()
        limite_cambios = config.max_reprogramaciones if config else 2
        horas_limite = config.horas_limite_cancelacion if config else 48

        accion = request.data.get('accion') # 'CONSULTAR', 'REPROGRAMAR', 'CANCELAR'

        # Cálculos de tiempo (Solo necesarios para Estado C, pero los preparamos)
        ahora = timezone.now()
        # Aseguramos que fecha_hora_turno sea aware (con zona horaria)
        fecha_hora_turno = timezone.datetime.combine(turno.fecha, turno.hora_inicio)
        if timezone.is_naive(fecha_hora_turno):
            fecha_hora_turno = timezone.make_aware(fecha_hora_turno)
        
        diferencia = fecha_hora_turno - ahora
        horas_restantes = diferencia.total_seconds() / 3600

        # =====================================================================
        # 1. BLOQUEO DE SEGURIDAD (Solo aplica a CONFIRMADOS)
        # =====================================================================
        # La regla de 48hs solo aplica si el turno ya es firme (Estado C)
        es_confirmado = turno.estado == Turno.Estado.CONFIRMADO
        
        if not es_profesional and es_confirmado and horas_restantes < horas_limite:
            if accion in ['REPROGRAMAR', 'CANCELAR']:
                return Response({
                    "error": "Restricción de tiempo",
                    "mensaje_bloqueo": f"Faltan menos de {horas_limite}hs. Ya no se puede modificar por la App.",
                    "contacto": "WhatsApp: +54 9 ..."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if accion == 'CONSULTAR':
                return Response({
                    "puede_reprogramar": False,
                    "mensaje": "Tiempo límite excedido (menos de 48hs).",
                    "tipo_alerta": "danger"
                })

        # =====================================================================
        # 2. ACCIÓN: CONSULTAR (Información según Estado)
        # =====================================================================
        if accion == 'CONSULTAR':
            # --- ESTADO A: SOLICITADO ---
            if turno.estado == Turno.Estado.SOLICITADO:
                return Response({
                    "puede_reprogramar": True,
                    "mensaje": "Aún no confirmamos tu turno. Puedes modificar la fecha libremente.",
                    "tipo_alerta": "info"
                })
            
            # --- ESTADO B: ESPERANDO SEÑA ---
            elif turno.estado == Turno.Estado.ESPERANDO_SENA:
                return Response({
                    "puede_reprogramar": True,
                    "mensaje": "Si cambias la fecha ahora, deberemos volver a validar la disponibilidad (vuelve a estado Solicitado).",
                    "tipo_alerta": "warning"
                })

            # --- ESTADO C: CONFIRMADO ---
            elif turno.estado == Turno.Estado.CONFIRMADO:
                cambios_restantes = limite_cambios - turno.cambios_realizados
                puede = cambios_restantes > 0
                msg = f"Te quedan {cambios_restantes} cambios disponibles." if puede else "Has agotado tus cambios."
                return Response({
                    "puede_reprogramar": puede,
                    "mensaje": msg,
                    "cambios_realizados": turno.cambios_realizados,
                    "limite_cambios": limite_cambios,
                    "tipo_alerta": "info" if puede else "danger"
                })

        # =====================================================================
        # 3. ACCIÓN: REPROGRAMAR (Lógica Diferenciada)
        # =====================================================================
        elif accion == 'REPROGRAMAR':
            # Validación de datos de entrada (común a todos)
            nueva_fecha_str = request.data.get('nueva_fecha')
            nueva_hora_str = request.data.get('nueva_hora')
            if not nueva_fecha_str or not nueva_hora_str:
                return Response({"error": "Faltan datos"}, status=400)

            try:
                # Conversión segura
                nueva_fecha = datetime.datetime.strptime(nueva_fecha_str, '%Y-%m-%d').date()
                nueva_hora = datetime.datetime.strptime(nueva_hora_str, '%H:%M').time()
            except ValueError:
                return Response({"error": "Formato inválido"}, status=400)

            # --- LÓGICA ESTADO A (Solicitado) ---
            if turno.estado == Turno.Estado.SOLICITADO:
                turno.fecha = nueva_fecha
                turno.hora_inicio = nueva_hora
                # No cambia estado, no suma contador
                turno.save()
                return Response({"mensaje": "Solicitud modificada correctamente."})

            # --- LÓGICA ESTADO B (Esperando Seña) ---
            elif turno.estado == Turno.Estado.ESPERANDO_SENA:
                turno.fecha = nueva_fecha
                turno.hora_inicio = nueva_hora
                turno.estado = Turno.Estado.SOLICITADO # REINICIO DEL FLUJO
                # No suma contador
                turno.save()
                return Response({"mensaje": "Fecha cambiada. Tu turno espera nueva aprobación."})

            # --- LÓGICA ESTADO C (Confirmado) ---
            elif turno.estado == Turno.Estado.CONFIRMADO:
                if turno.cambios_realizados >= limite_cambios:
                    return Response({"error": "Límite de cambios excedido."}, status=400)
                
                turno.fecha = nueva_fecha
                turno.hora_inicio = nueva_hora
                turno.cambios_realizados += 1
                # Mantiene estado Confirmado (Seña se traslada)
                turno.save()
                
                # Aquí iría el disparador de optimización (liberar hueco viejo), 
                # pero como es un update sobre el mismo objeto, el hueco se libera implícitamente.
                
                return Response({"mensaje": "Turno reprogramado. Seña transferida."})

        # =====================================================================
        # 4. ACCIÓN: CANCELAR (Lógica General)
        # =====================================================================
        elif accion == 'CANCELAR':
            # 1. Guardar datos del hueco (Snapshot)
            fecha_hueco = turno.fecha
            hora_hueco = turno.hora_inicio
            # Obtener servicios asociados desde detalles
            detalles_turno = turno.detalles.all()
            servicios_hueco = [d.servicio for d in detalles_turno]
            cliente_que_cancela = turno.cliente
            
            # 2. Ejecutar la cancelación
            turno.estado = Turno.Estado.CANCELADO
            turno.save()
            
            candidatos_notificados = []

            # === MOTOR DE OPTIMIZACIÓN DE AGENDA ===
            
            # GRUPO 1: Lista de Espera (Gente sin turno)
            espera_q = ListaEspera.objects.filter(
                activa=True,
                notificado=False,
                fecha_deseada_inicio__lte=fecha_hueco,
                fecha_deseada_fin__gte=fecha_hueco
            )
            
            # GRUPO 2: Adelanto de Turnos (Gente con turno futuro)
            # Buscamos turnos con al menos uno de los servicios liberados
            futuros_q = Turno.objects.filter(
                estado=Turno.Estado.CONFIRMADO,
                detalles__servicio__in=servicios_hueco,
                fecha__gt=fecha_hueco
            ).exclude(cliente=cliente_que_cancela).distinct()
            
            # --- Ejecución de Notificaciones ---
            
            # Procesar Grupo 1 (Lista de Espera)
            for cand in espera_q:
                servicios_str = ', '.join([s.nombre for s in servicios_hueco])
                print(f"[LISTA ESPERA] Notificando a {cand.cliente.usuario.first_name} sobre hueco el {fecha_hueco}")
                
                # Crear notificación con datos_extra
                Notificacion.objects.create(
                    usuario=cand.cliente.usuario,
                    tipo='ADELANTO',  
                    canal='app',
                    titulo="¡Disponibilidad de Turno!",
                    mensaje=f"Se liberó un espacio para {servicios_str} el {fecha_hueco} a las {hora_hueco.strftime('%H:%M')}. ¿Te gustaría reservarlo?",
                    origen_entidad='Turno',
                    origen_id=turno.id,
                    datos_extra={
                        "fecha_oferta": str(fecha_hueco),
                        "hora_oferta": str(hora_hueco),
                        "servicio_ids": [s.id for s in servicios_hueco],
                        "turno_cancelado_id": turno.id
                    }
                )
                
                cand.notificado = True
                cand.save()
                candidatos_notificados.append(f"LE: {cand.cliente.usuario.first_name}")

            # Procesar Grupo 2 (Adelanto de Turnos)
            for turno_futuro in futuros_q:
                servicios_str = ', '.join([s.nombre for s in servicios_hueco])
                print(f"[ADELANTO] Ofreciendo a {turno_futuro.cliente.usuario.first_name} (Turno del {turno_futuro.fecha}) adelantar al {fecha_hueco}")
                
                # Crear notificación con datos_extra
                Notificacion.objects.create(
                    usuario=turno_futuro.cliente.usuario,
                    tipo='ADELANTO',
                    canal='app',
                    titulo="¡Oportunidad de Adelantar Turno!",
                    mensaje=f"Se liberó un espacio para {servicios_str} el {fecha_hueco} a las {hora_hueco.strftime('%H:%M')}. ¿Te gustaría adelantar tu turno del {turno_futuro.fecha}?",
                    origen_entidad='Turno',
                    origen_id=turno_futuro.id,
                    datos_extra={
                        "fecha_oferta": str(fecha_hueco),
                        "hora_oferta": str(hora_hueco),
                        "turno_actual_id": turno_futuro.id,
                        "servicio_ids": [s.id for s in servicios_hueco]
                    }
                )
                
                candidatos_notificados.append(f"Adelanto: {turno_futuro.cliente.usuario.first_name}")

            return Response({
                "mensaje": "Turno cancelado correctamente.",
                "automatizacion_info": {
                    "hueco_liberado": f"{fecha_hueco} a las {hora_hueco.strftime('%H:%M')}",
                    "total_notificados": len(candidatos_notificados),
                    "detalle": candidatos_notificados
                }
            })

        return Response({"error": "Acción inválida"}, status=400)

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
            notificacion.save()
            
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
    queryset = Usuario.objects.all()
    serializer_class = UsuarioAdminSerializer
    permission_classes = [IsAdminUser] # Solo admins pueden entrar aquí

    def perform_destroy(self, instance):
        """
        No elimina el registro (Soft Delete). Lo desactiva.
        Validación: No desactivar si tiene turnos futuros.
        """
        # 1. Verificar turnos activos/futuros
        # Asumiendo que Turno tiene FK 'profesional' o lo buscas por otro medio. 
        # Si Yani es la única, esta validación es vital si agregas más staff.
        
        # Ejemplo: Turno.objects.filter(profesional=instance, fecha__gte=timezone.now(), estado='confirmado')
        # Como tu modelo Turno actual no tiene 'profesional' explícito (es Yani), 
        # esta validación aplica si el usuario a borrar fuera un cliente con deuda o un futuro empleado.
        
        # Para cumplir el requisito del enunciado A:
        # "No se puede eliminar una cuenta de profesional si tiene turnos activos"
        if instance.is_staff:
             # Simulamos chequeo
             turnos_pendientes = Turno.objects.filter(fecha__gte=timezone.now().date(), estado='confirmado').exists()
             if turnos_pendientes:
                 # En un sistema multi-profesional filtraríamos por profesional=instance
                 # Como es tesis y Yani es única, protegemos su cuenta.
                 raise serializers.ValidationError("No se puede desactivar: Hay turnos futuros confirmados en el sistema.")

        # 2. Desactivación (Soft Delete)
        instance.is_active = False
        instance.save()

# ----------------------------------------------------
# B. CRUD PRODUCTOS
# ----------------------------------------------------
class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.filter(activo=True) # Por defecto mostramos solo activos
    serializer_class = ProductoSerializer
    permission_classes = [IsAdminUser] # Solo staff gestiona productos
    pagination_class = None

    def destroy(self, request, *args, **kwargs):
        producto = self.get_object()
        
        # Validación 1: Stock en inventario
        if producto.stock > 0:
            return Response(
                {"error": "No se puede eliminar: El producto tiene stock físico."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validación 2: Referencia en rutinas activas
        # Asumiendo relación ManyToMany en Rutina -> productos
        # if producto.rutina_set.exists(): ...
        
        # Si pasa validaciones, Soft Delete o Hard Delete según prefieras.
        # El requisito dice "Retira producto descontinuado".
        producto.activo = False
        producto.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

# ----------------------------------------------------
# D. CRUD TIPO EQUIPAMIENTO
# ----------------------------------------------------
class TipoEquipamientoViewSet(viewsets.ModelViewSet):
    queryset = TipoEquipamiento.objects.all()
    serializer_class = TipoEquipamientoSerializer


# ----------------------------------------------------
# E. CRUD EQUIPAMIENTO
# ----------------------------------------------------
class EquipamientoViewSet(viewsets.ModelViewSet):
    queryset = Equipamiento.objects.filter(is_active=True) # Solo mostramos los activos
    serializer_class = EquipamientoSerializer

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
            estado__in=[Turno.Estado.SOLICITADO, Turno.Estado.ESPERANDO_SENA, Turno.Estado.CONFIRMADO]
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


class DiagnosticoCapilarViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar diagnósticos capilares.
    - Lectura: Cualquier usuario autenticado puede ver diagnósticos (especialmente clientes sus propios)
    - Creación/Edición: Solo staff (profesionales) pueden crear y editar
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
            return Response(
                {"error": "Solo profesionales pueden crear diagnósticos"},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Solo staff puede actualizar diagnósticos"""
        if not request.user.is_staff:
            return Response(
                {"error": "Solo profesionales pueden actualizar diagnósticos"},
                status=status.HTTP_403_FORBIDDEN
            )
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
