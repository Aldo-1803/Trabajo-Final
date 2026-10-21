from django.urls import path, include
from django.http import HttpResponseRedirect
from rest_framework.routers import DefaultRouter
from . import views
from .views import (
    DisponibilidadTurnosView, MiAgendaCuidadosView, AdminDashboardStatsView, TipoCabelloViewSet, GrosorCabelloViewSet,
    PorosidadCabelloViewSet, CueroCabelludoViewSet, EstadoGeneralViewSet, CategoriaServicioViewSet, ServicioViewSet,
    ServiciosQuimicosViewSet, TurnoViewSet, RutinaViewSet, ReglaDiagnosticoViewSet, NotificacionViewSet, SeleccionarRutinaView,
    RutinaClienteViewSet, TipoEquipamientoViewSet, FichaTecnicaViewSet, RequisitoServicioViewSet, DiagnosticoCapilarViewSet,
    CategoriaProductoViewSet, ProductoViewSet, ImagenProductoViewSet, PromocionViewSet, ConfiguracionViewSet, CarritoViewSet,
    ContenidoEducativoViewSet, MeGustaViewSet, ContenidoGuardadoViewSet, upload_imagen, OrdenPendienteViewSet, OrdenCompraViewSet,
    PagoViewSet, ConfiguracionDiagnosticoViewSet, GenerarPagoMercadoPagoView, WebhookMercadoPagoView,
    #ListaEsperaCreateView,
    # ViewSets
    #PasoRutinaViewSet,
)
from .views_auditoria import AuditoriaViewSet, HistorialAuditoriaViewSet
from .stats_views import DashboardStatsViewSet



# Crear el router automático
router = DefaultRouter()

# --- RUTAS PARA CATÁLOGOS DE CABELLO (Plurales para coincidir con Frontend) ---
router.register(r'tipos-cabello', TipoCabelloViewSet, basename='tipocabello')
router.register(r'grosores-cabello', GrosorCabelloViewSet, basename='grosorcabello')
router.register(r'porosidades-cabello', PorosidadCabelloViewSet, basename='porosidadcabello')
router.register(r'cueros-cabelludos', CueroCabelludoViewSet, basename='cuerocabelludo')
router.register(r'estados-generales', EstadoGeneralViewSet, basename='estadogeneral')
router.register(r'categorias-servicio', CategoriaServicioViewSet, basename='categoria-servicio')

# Resto de rutas (estas ya estaban bien o son nuevas)
router.register(r'servicios', ServicioViewSet, basename='servicio')
router.register(r'horariolaboral', views.HorarioLaboralViewSet, basename='horariolaboral')
router.register(r'turnos', TurnoViewSet, basename='turno')
router.register(r'notificaciones', NotificacionViewSet, basename='notificaciones')
router.register(r'servicios-quimicos', ServiciosQuimicosViewSet, basename='servicios-quimicos')
router.register(r'rutinas', RutinaViewSet, basename='rutina')
#router.register(r'pasorutina', PasoRutinaViewSet, basename='pasorutina')
router.register(r'reglas-diagnostico', ReglaDiagnosticoViewSet, basename='reglas-diagnostico')
router.register(r'rutinas-cliente', RutinaClienteViewSet, basename='rutina-cliente')
router.register(r'admin/usuarios', views.AdminUsuarioViewSet, basename='admin-usuarios')
router.register(r'categorias-productos', views.CategoriaProductoViewSet, basename='categoria-producto')
router.register(r'productos', views.ProductoViewSet, basename='productos')
router.register(r'imagenes-productos', views.ImagenProductoViewSet, basename='imagen-producto')
router.register(r'personal', views.PersonalViewSet, basename='personal')
router.register(r'tipo-equipamiento', TipoEquipamientoViewSet, basename='tipo-equipamiento')
router.register(r'equipamiento', views.EquipamientoViewSet, basename='equipamiento')
router.register(r'fichas-tecnicas', FichaTecnicaViewSet, basename='ficha-tecnica')
router.register(r'requisitos-servicio', RequisitoServicioViewSet, basename='requisito-servicio')
router.register(r'diagnosticos-capilares', DiagnosticoCapilarViewSet, basename='diagnostico-capilar')
router.register(r'promociones', PromocionViewSet, basename='promocion')
router.register(r'configuracion', ConfiguracionViewSet, basename='configuracion')
router.register(r'configuracion-diagnostico', ConfiguracionDiagnosticoViewSet, basename='configuracion-diagnostico')
router.register(r'carrito', CarritoViewSet, basename='carrito')
router.register(r'contenido-educativo', ContenidoEducativoViewSet, basename='contenido-educativo')
router.register(r'me-gusta', MeGustaViewSet, basename='me-gusta')
router.register(r'contenido-guardado', ContenidoGuardadoViewSet, basename='contenido-guardado')
router.register(r'ordenes-pendientes', OrdenPendienteViewSet, basename='orden-pendiente')
router.register(r'ordenes-compra', OrdenCompraViewSet, basename='orden-compra')
router.register(r'pagos', PagoViewSet, basename='pagos')
router.register(r'stats', DashboardStatsViewSet, basename='dashboard-stats')
# --- AUDITORÍA ---
router.register(r'auditoria', AuditoriaViewSet, basename='auditoria')
router.register(r'auditoria-historial', HistorialAuditoriaViewSet, basename='auditoria-historial')


def redirigir_react_exito(request):
    return HttpResponseRedirect("http://localhost:3000/compra-exitosa")


def redirigir_react_fallo(request):
    return HttpResponseRedirect("http://localhost:3000/compra-fallida")


def redirigir_react_pendiente(request):
    return HttpResponseRedirect("http://localhost:3000/compra-pendiente")


# Las URLs se generan automáticamente
urlpatterns = [
    path('', include(router.urls)),

    path('checkout/iniciar-pago/', GenerarPagoMercadoPagoView.as_view(), name='iniciar_pago_mp'),
    path('checkout/webhook/', WebhookMercadoPagoView.as_view(), name='webhook_mp'),
    path('compra-exitosa/', redirigir_react_exito, name='redirigir_react_exito'),
    path('compra-fallida/', redirigir_react_fallo, name='redirigir_react_fallo'),
    path('compra-pendiente/', redirigir_react_pendiente, name='redirigir_react_pendiente'),
    
    # Upload de imágenes
    path('upload-imagen/', upload_imagen, name='upload-imagen'),
    
    # Endpoints personalizados (fuera del router)
    path('disponibilidad/', DisponibilidadTurnosView.as_view(), name='disponibilidad-turnos'),
    path('mi-agenda/', MiAgendaCuidadosView.as_view(), name='mi-agenda'),
    path('admin-dashboard/stats/', AdminDashboardStatsView.as_view(), name='admin-stats'),
    path('prueba-rutina/', views.SeleccionarRutinaView.as_view(), name='prueba-rutina'),
    #path('lista-espera/', ListaEsperaCreateView.as_view(), name='unirse-lista-espera'),
    path('agenda/general/', views.obtener_agenda_general, name='agenda-general'),
    path('agenda/bloquear/', views.crear_bloqueo, name='agenda-bloquear'),
    path('obtener_disponibilidad_calendario/', views.obtener_disponibilidad_calendario, name='disponibilidad-calendario'),
]
