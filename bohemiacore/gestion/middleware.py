"""
Middleware para capturar el usuario actual en cada request
y hacerlo disponible para los signals.

Soporta:
- Autenticación por sesión (Django estándar)
- Autenticación por JWT (Django REST Framework)
"""
import threading
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed

# Almacenar el usuario actual en thread-local storage
_thread_locals = threading.local()


def get_current_user():
    """Obtener el usuario actual del request."""
    user = getattr(_thread_locals, 'user', None)
    
    # DEBUG
    print(f"👤 get_current_user: {user} (is_authenticated: {user.is_authenticated if user else 'N/A'})")
    
    return user


def get_current_request():
    """Obtener el request actual."""
    return getattr(_thread_locals, 'request', None)


class AuditoriaMiddleware:
    """
    Middleware que captura el usuario actual y el IP address
    para usar en los signals de auditoría.
    
    Primero intenta autenticar con sesión, luego con JWT.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_authenticator = JWTAuthentication()
    
    def __call__(self, request):
        usuario = None
        
        # 1. Intentar autenticar con sesión (Django estándar)
        if request.user.is_authenticated:
            usuario = request.user
            print(f"🔐 Middleware: Usuario autenticado por SESIÓN: {usuario.email if hasattr(usuario, 'email') else usuario}")
        
        # 2. Si no hay sesión, intentar con JWT
        if not usuario:
            try:
                # Intenta extraer y validar el token JWT
                auth_info = self.jwt_authenticator.authenticate(request)
                if auth_info:
                    usuario = auth_info[0]  # El usuario está en la primera posición
                    print(f"🔐 Middleware: Usuario autenticado por JWT: {usuario.email if hasattr(usuario, 'email') else usuario}")
            except (InvalidToken, AuthenticationFailed, TypeError) as e:
                # TypeError: authenticate retorna None si no hay token
                # InvalidToken/AuthenticationFailed: Token inválido
                print(f"⚠️  Middleware: No se pudo validar JWT: {type(e).__name__}")
                usuario = None
        
        # 3. Guardar en thread-locals
        _thread_locals.user = usuario
        _thread_locals.request = request
        
        # DEBUG
        print(f"🔐 Middleware: user={usuario} authenticated={usuario.is_authenticated if usuario else False}")
        
        # Procesar el request
        response = self.get_response(request)
        
        return response
