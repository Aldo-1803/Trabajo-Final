from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TipoCabelloViewSet,
    GrosorCabelloViewSet,
    PorosidadCabelloViewSet,
    CueroCabelludoViewSet,
    EstadoGeneralViewSet,
    ServiciosQuimicosViewSet,
)

# Crear el router automático
router = DefaultRouter()
router.register(r'tipos-cabello', TipoCabelloViewSet, basename='tipocabello')
router.register(r'grosores-cabello', GrosorCabelloViewSet, basename='grosorcabello')
router.register(r'porosidades-cabello', PorosidadCabelloViewSet, basename='porosidadcabello')
router.register(r'cueros-cabelludos', CueroCabelludoViewSet, basename='cuerocabelludo')
router.register(r'estados-generales', EstadoGeneralViewSet, basename='estadogeneral')
router.register(
    r'servicios-quimicos',       # La URL será /api/gestion/servicios-quimicos/
    ServiciosQuimicosViewSet, 
    basename='servicios-quimicos'
)

# Las URLs se generan automáticamente
urlpatterns = [
    path('', include(router.urls)),
]