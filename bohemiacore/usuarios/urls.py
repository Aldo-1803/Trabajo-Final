from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'clientes', views.ClienteViewSet, basename='cliente')

urlpatterns = [
    path('', include(router.urls)),
    path('registro/', views.RegistroView.as_view(), name='registro'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('perfil/', views.PerfilView.as_view(), name='perfil'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('diagnostico/', views.DiagnosticoView.as_view(), name='diagnostico'),
    
    # Endpoint A (El que ya hicimos)
    path('password-reset/request/', views.PasswordResetRequestView.as_view(), name='password-reset-request'),
    
    # Endpoint B (El que acabamos de hacer)
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]