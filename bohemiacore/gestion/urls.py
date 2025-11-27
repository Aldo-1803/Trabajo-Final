from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DisponibilidadTurnosView
from .views import (
    TipoCabelloViewSet,
    GrosorCabelloViewSet,
    PorosidadCabelloViewSet,
    CueroCabelludoViewSet,
    EstadoGeneralViewSet,
    ServicioViewSet,
    ServiciosQuimicosViewSet,
    TurnoViewSet,
)

# Crear el router automático
router = DefaultRouter()
router.register(r'tipos-cabello', TipoCabelloViewSet, basename='tipocabello')
router.register(r'grosores-cabello', GrosorCabelloViewSet, basename='grosorcabello')
router.register(r'porosidades-cabello', PorosidadCabelloViewSet, basename='porosidadcabello')
router.register(r'cueros-cabelludos', CueroCabelludoViewSet, basename='cuerocabelludo')
router.register(r'estados-generales', EstadoGeneralViewSet, basename='estadogeneral')
router.register(r'servicios', ServicioViewSet, basename='servicio')
router.register(r'turnos', TurnoViewSet, basename='turno')
router.register(
    r'servicios-quimicos',       # La URL será /api/gestion/servicios-quimicos/
    ServiciosQuimicosViewSet, 
    basename='servicios-quimicos'
)

# Las URLs se generan automáticamente
urlpatterns = [
    path('', include(router.urls)),
    path('disponibilidad/', DisponibilidadTurnosView.as_view(), name='disponibilidad'),
]