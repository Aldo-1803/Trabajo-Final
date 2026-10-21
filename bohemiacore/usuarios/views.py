from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str


from django.db.models import Min
from .serializers import (
    UsuarioPerfilReadSerializer, UsuarioPerfilUpdateSerializer, RegistroSerializer, ClienteListSerializer, SetNewPasswordSerializer
)
from .cliente_filters import ClienteFilter

from .models import (
    Usuario,  Cliente
) 

from gestion.models import (
    ReglaDiagnostico, TipoCabello, GrosorCabello,
    PorosidadCabello, CueroCabelludo, EstadoGeneral, Servicio,
    DiagnosticoCapilar
)
from gestion.serializers import DiagnosticoCapilarSerializer

# Vista para redirigir a la pantalla de registro
def home(request):
    return redirect('registro')  # Redirige al nombre de la ruta 'registro'

class LogoutView(APIView):
    """
    Vista para invalidar (blacklist) un Refresh Token.
    """
    permission_classes = (IsAuthenticated,) # 

    def post(self, request):
        try:
            # 1. Recibir el refresh_token del body del JSON
            refresh_token = request.data["refresh_token"]
            
            # 2. Crear un objeto Token y "registrarlo" en la blacklist
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            # Si el token ya es inválido o falta, igual damos OK
            return Response(status=status.HTTP_400_BAD_REQUEST)

class RegistroView(APIView):
    """
    Vista (Endpoint) para el registro de nuevos usuarios.
    Responde a POST /api/usuarios/registro/
    """
    permission_classes = [AllowAny]  # Permite acceso público

    def post(self, request):
        """
        Maneja la petición POST con los datos del formulario de registro.
        """
        serializer = RegistroSerializer(data=request.data)
        if serializer.is_valid():
            usuario = serializer.save() # Guarda el usuario y cliente asociado
            usuario.es_cliente = True  # Asigna automáticamente el rol de cliente
            usuario.save()
            return Response(
                {"mensaje": "Usuario registrado exitosamente."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class LoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        try:
            usuario = Usuario.objects.get(email=email)
            if usuario.check_password(password):
                refresh = RefreshToken.for_user(usuario)
                return Response({
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                }, status=status.HTTP_200_OK)
            else:
                print(f"[LOGIN] Contraseña incorrecta para {email}")
                return Response({'detail': 'Credenciales inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)
        except Usuario.DoesNotExist:
            print(f"[LOGIN] Usuario no encontrado: {email}")
            return Response({'detail': 'Credenciales inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)

class PerfilView(APIView):
    """
    Endpoint para LEER (GET) y ACTUALIZAR (PUT) el perfil del usuario.
    Responde a /api/usuarios/perfil/
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Maneja GET: Devuelve los datos del perfil del usuario logueado.
        """
        # 2. Usamos el serializer de LECTURA (plano)
        serializer = UsuarioPerfilReadSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        """
        Maneja PUT: Actualiza los datos del perfil del usuario logueado.
        """
        usuario = request.user
        
        # 3. Usamos el serializer de ESCRITURA (anidado)
        # partial=True permite actualizaciones parciales (método PATCH)
        serializer = UsuarioPerfilUpdateSerializer(
            instance=usuario, 
            data=request.data, 
            partial=True 
        )

        if serializer.is_valid():
            # 4. Guardar los datos (esto llama a nuestro método .update())
            serializer.save()
            
            # 5. Devolvemos el perfil actualizado, usando el serializer de LECTURA
            read_serializer = UsuarioPerfilReadSerializer(usuario)
            return Response(read_serializer.data, status=status.HTTP_200_OK)
        
        # Si los datos no son válidos (ej. un ID de cabello que no existe)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetRequestView(APIView):
    """
    Endpoint A: Solicitar reseteo de contraseña.
    Recibe un email y envía un enlace de un solo uso.
    Responde a POST /api/usuarios/password-reset/request/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        
        # (Opcional) Usar un Serializer aquí es más limpio
        if not email:
            return Response({"error": "Email es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = Usuario.objects.get(email=email)
            
            # --- Lógica de Token (reemplaza get_random_string) ---
            
            # 1. Generar el UID (ID del usuario codificado)
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            
            # 2. Generar el Token (token de un solo uso)
            token = default_token_generator.make_token(usuario)
            
            # 3. Definir la URL de su Frontend (React)
            # (Asegúrese de que esta sea la ruta correcta en React)
            frontend_url = 'http://localhost:3000' 
            reset_link = f'{frontend_url}/resetear-clave/{uid}/{token}/'
            
            # 4. Enviar el correo con HTML (EmailMultiAlternatives)
            asunto = 'Recuperación de contraseña - Bohemia Hair'
            
            # Contexto para el template HTML
            context = {
                'usuario': usuario,
                'reset_link': reset_link,
                'frontend_url': frontend_url,
            }
            
            # Renderizar el template HTML
            html_content = render_to_string('emails/password_reset_email.html', context)
            
            # Crear versión de texto plano (fallback)
            text_content = strip_tags(html_content)
            
            # Crear email con alternativas
            email_message = EmailMultiAlternatives(
                asunto,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [email]
            )
            
            # Agregar versión HTML
            email_message.attach_alternative(html_content, "text/html")
            
            # Enviar el email
            email_message.send(fail_silently=False)
            
            # 5. La respuesta segura (¡igual que la suya!)
            return Response(
                {"mensaje": "Si el correo existe en nuestro sistema, recibirás un correo de recuperación."},
                status=status.HTTP_200_OK
            )
            
        except Usuario.DoesNotExist:
            # No revelar si el usuario existe
            return Response(
                {"mensaje": "Si el correo existe en nuestro sistema, recibirás un correo de recuperación."},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": f"Error al enviar el correo: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


#----------------------------------------------------
# Vista para confirmar el reseteo de contraseña
#----------------------------------------------------
class PasswordResetConfirmView(APIView):
    """
    Endpoint B: Confirmar reseteo de contraseña.
    Valida el token/uid y actualiza la contraseña.
    Responde a POST /api/usuarios/password-reset/confirm/
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        # 1. Usar el serializer para validar la data de entrada
        serializer = SetNewPasswordSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Si la data es válida, extraemos las variables
        data = serializer.validated_data
        uidb64 = data['uid']
        token = data['token']
        new_password = data['password']

        try:
            # 2. Decodificar el UID para obtener el PK del usuario
            uid = force_str(urlsafe_base64_decode(uidb64))
            usuario = Usuario.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
            usuario = None

        # 3. Validar el token contra el usuario
        if usuario is not None and default_token_generator.check_token(usuario, token):
            
            # 4. ¡ÉXITO! El token es válido. Cambiar la contraseña.
            usuario.set_password(new_password)
            usuario.save()
            return Response(
                {"mensaje": "Contraseña actualizada exitosamente."},
                status=status.HTTP_200_OK
            )
        else:
            # 5. ¡FALLO! El token es inválido o el usuario no existe
            return Response(
                {"error": "El enlace de reseteo es inválido o ha expirado."},
                status=status.HTTP_400_BAD_REQUEST
            )


#----------------------------------------------------
# 4. VISTA DE DIAGNÓSTICO
#----------------------------------------------------
class DiagnosticoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            perfil = request.user.cliente
        except Cliente.DoesNotExist:
            return Response(
                {"error": "Perfil de cliente no encontrado."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        diagnostico = DiagnosticoCapilar.objects.filter(
            cliente=perfil
        ).order_by('-fecha_diagnostico').first()

        if not diagnostico:
            return Response(
                {"error": "No hay diagnósticos registrados para este cliente."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = DiagnosticoCapilarSerializer(diagnostico, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# --- VIEWSET PARA LISTAR CLIENTES (ADMIN) ---
class ClienteViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para que el admin pueda listar todos los clientes.
    Solo lectura (GET).
    Incluye filtrado, búsqueda y ordenamiento.
    """
    queryset = Cliente.objects.all().select_related('usuario')
    serializer_class = ClienteListSerializer
    permission_classes = [permissions.IsAdminUser]
    pagination_class = None
    
    # Configurar filtros, búsqueda y ordenamiento
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ClienteFilter
    search_fields = ['usuario__first_name', 'usuario__last_name', 'usuario__email']
    ordering_fields = ['usuario__first_name', 'usuario__last_name', 'usuario__date_joined', 'activo']
    ordering = ['-usuario__date_joined']  # Por defecto, mostrar primero los más nuevos
    
    def get_queryset(self):
        """
        Solo traer clientes cuyo usuario asociado esté activo.
        Esto previene desincronización cuando se "desactivan" usuarios.
        """
        return Cliente.objects.filter(usuario__is_active=True).select_related('usuario')
