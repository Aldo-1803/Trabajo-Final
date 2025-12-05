from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DisponibilidadTurnosView, 
    MiAgendaCuidadosView, 
    AdminDashboardStatsView,
    #ListaEsperaCreateView,
    # ViewSets
    TipoCabelloViewSet,
    GrosorCabelloViewSet,
    PorosidadCabelloViewSet,
    CueroCabelludoViewSet,
    EstadoGeneralViewSet,
    ServicioViewSet,
    ServiciosQuimicosViewSet,
    TurnoViewSet,
    RutinaViewSet,
    PasoRutinaViewSet,
    ReglaDiagnosticoViewSet,
    NotificacionViewSet,
    RutinaClienteViewSet,
    SeleccionarRutinaView
)

from . import views

# Crear el router automático
router = DefaultRouter()

# --- CAMBIO IMPORTANTE: RUTAS EN SINGULAR PARA COINCIDIR CON FRONTEND ---
router.register(r'tipo-cabello', TipoCabelloViewSet, basename='tipocabello')
router.register(r'grosor-cabello', GrosorCabelloViewSet, basename='grosorcabello')
router.register(r'porosidad-cabello', PorosidadCabelloViewSet, basename='porosidadcabello')
router.register(r'cuero-cabelludo', CueroCabelludoViewSet, basename='cuerocabelludo')
router.register(r'estado-general', EstadoGeneralViewSet, basename='estadogeneral')

# Resto de rutas (estas ya estaban bien o son nuevas)
router.register(r'servicios', ServicioViewSet, basename='servicio')
router.register(r'turnos', TurnoViewSet, basename='turno')
router.register(r'notificaciones', NotificacionViewSet, basename='notificaciones')
router.register(r'servicios-quimicos', ServiciosQuimicosViewSet, basename='servicios-quimicos')
router.register(r'rutinas', RutinaViewSet, basename='rutina')
router.register(r'pasorutina', PasoRutinaViewSet, basename='pasorutina')
router.register(r'reglas-diagnostico', ReglaDiagnosticoViewSet, basename='reglas-diagnostico')
router.register(r'rutinas-cliente', RutinaClienteViewSet, basename='rutina-cliente')

# Las URLs se generan automáticamente
urlpatterns = [
    path('', include(router.urls)),
    
    # Endpoints personalizados (fuera del router)
    path('disponibilidad/', DisponibilidadTurnosView.as_view(), name='disponibilidad-turnos'),
    path('mi-agenda/', MiAgendaCuidadosView.as_view(), name='mi-agenda'),
    path('admin-dashboard/stats/', AdminDashboardStatsView.as_view(), name='admin-stats'),
    path('prueba-rutina/', views.SeleccionarRutinaView.as_view(), name='prueba-rutina'),
    #path('lista-espera/', ListaEsperaCreateView.as_view(), name='unirse-lista-espera'),
]