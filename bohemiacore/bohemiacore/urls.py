from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponseRedirect
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from gestion.views import WebhookMercadoPagoView


def redirigir_react_exito(request):
    return HttpResponseRedirect('http://localhost:3000/compra-exitosa')


def redirigir_react_fallo(request):
    return HttpResponseRedirect('http://localhost:3000/compra-fallida')


def redirigir_react_pendiente(request):
    return HttpResponseRedirect('http://localhost:3000/compra-pendiente')

urlpatterns = [
    # Administración
    path('admin/', admin.site.urls),

    # JWT Tokens
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Apps
    path('api/usuarios/', include('usuarios.urls')),
    path('api/gestion/', include('gestion.urls')),

    # Aliases para preferencias de Mercado Pago generadas con URLs anteriores.
    path('api/checkout/webhook/', WebhookMercadoPagoView.as_view(), name='webhook_mp_legacy'),
    path('compra-exitosa/', redirigir_react_exito, name='redirigir_react_exito_legacy'),
    path('compra-fallida/', redirigir_react_fallo, name='redirigir_react_fallo_legacy'),
    path('compra-pendiente/', redirigir_react_pendiente, name='redirigir_react_pendiente_legacy'),

    
]

# Servir archivos de media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
