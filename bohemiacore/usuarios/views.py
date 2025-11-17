from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from .serializers import RegistroSerializer
from .serializers import SetNewPasswordSerializer
from django.db.models import Min
from .serializers import (
    UsuarioPerfilReadSerializer,
    UsuarioPerfilUpdateSerializer
)
from .models import Usuario
from .models import Cliente

from gestion.models import (
    ReglaDiagnostico, TipoCabello, GrosorCabello, 
    PorosidadCabello, CueroCabelludo, EstadoGeneral, Servicio
)

# Vista para redirigir a la pantalla de registro
def home(request):
    return redirect('registro')  # Redirige al nombre de la ruta 'registro'

class LogoutView(APIView):
    """
    Vista para invalidar (blacklist) un Refresh Token.
    """
    permission_classes = (IsAuthenticated,) # <-- Solo usuarios logueados pueden hacer logout

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
            usuario = serializer.save()  # Guarda el usuario y cliente asociado
            usuario.es_cliente = True  # Asigna automáticamente el rol de cliente
            usuario.save()
            return Response(
                {"mensaje": "Usuario registrado exitosamente."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class LoginView(APIView):
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
                return Response({'detail': 'Credenciales inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)
        except Usuario.DoesNotExist:
            return Response({'detail': 'Credenciales inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)

class PerfilView(APIView):
    """
    Endpoint para LEER (GET) y ACTUALIZAR (PUT) el perfil del usuario.
    Responde a /api/usuarios/perfil/
    """
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
            
            # 4. Enviar el correo (¡con el enlace, no con la clave!)
            asunto = 'Recuperación de contraseña - Bohemia Hair'
            mensaje = f"""
                Hola {usuario.first_name},

                Haz clic en el siguiente enlace para crear una nueva contraseña:

                {reset_link}

                Si no solicitaste esto, ignora este correo.

                Saludos,
                Bohemia Hair
                """
            
            send_mail(
                asunto,
                mensaje,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            
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

        # --- INICIO DE LA LÓGICA DEL MOTOR DE REGLAS V6.0 (Tu Lógica) ---
        
        # --- 1. NIVEL 1: REGLAS DE EXCEPCIÓN (Tu modelo ReglaDiagnostico) ---
        
        reglas_nivel_1 = ReglaDiagnostico.objects.all()
        
        for regla in reglas_nivel_1:
            match = True 
            if regla.tipo_cabello and regla.tipo_cabello != perfil.tipo_cabello:
                match = False
            if match and regla.grosor_cabello and regla.grosor_cabello != perfil.grosor_cabello:
                match = False
            if match and regla.porosidad_cabello and regla.porosidad_cabello != perfil.porosidad_cabello:
                match = False
            if match and regla.cuero_cabelludo and regla.cuero_cabelludo != perfil.cuero_cabelludo:
                match = False
            if match and regla.estado_general and regla.estado_general != perfil.estado_general:
                match = False
            
            if match:
                # ¡COINCIDENCIA DE NIVEL 1! Devolvemos la excepción.
                return Response({
                    'mensaje_diagnostico': regla.mensaje_resultado,
                    'accion': regla.accion_resultado,
                    'puntaje_final': 0, # Nivel 1 no usa puntaje
                    'fuente': f"Análisis v6.0 (Regla Nivel 1: {regla})"
                })

        # --- 2. NIVEL 2 vs NIVEL 3 (Servicios vs Matriz) ---
        
        puntaje_salud_total = 0
        reglas_activadas = []
        fuente_principal = ""

        try:
            servicios_del_perfil = perfil.historial_servicios.all()
            
            if servicios_del_perfil.exists():
                # --- NIVEL 2: LÓGICA DE SERVICIOS (Anulación) ---
                # Buscamos el servicio con el puntaje MÁS BAJO (el más dañino)
                puntaje_minimo_servicio = servicios_del_perfil.aggregate(
                    puntaje_minimo=Min('puntaje_base')
                )['puntaje_minimo']
                
                puntaje_salud_total = puntaje_minimo_servicio
                fuente_principal = "Análisis v6.0 (Nivel 2: Historial de Servicios)"
                reglas_activadas.append(f"Puntaje de Servicio: {puntaje_salud_total} pts")

            else:
                # --- NIVEL 3: LÓGICA DE MATRIZ (Fallback) ---
                # (Si no hay servicios, calculamos la matriz)
                
                if perfil.estado_general:
                    puntaje_salud_total += perfil.estado_general.puntaje_base
                    reglas_activadas.append(f"Estado({perfil.estado_general.puntaje_base} pts)")
                if perfil.cuero_cabelludo:
                    puntaje_salud_total += perfil.cuero_cabelludo.puntaje_base
                    reglas_activadas.append(f"Cuero({perfil.cuero_cabelludo.puntaje_base} pts)")
                if perfil.tipo_cabello:
                    puntaje_salud_total += perfil.tipo_cabello.puntaje_base
                    reglas_activadas.append(f"Tipo({perfil.tipo_cabello.puntaje_base} pts)")
                if perfil.grosor_cabello:
                    puntaje_salud_total += perfil.grosor_cabello.puntaje_base
                    reglas_activadas.append(f"Grosor({perfil.grosor_cabello.puntaje_base} pts)")
                if perfil.porosidad_cabello:
                    puntaje_salud_total += perfil.porosidad_cabello.puntaje_base
                    reglas_activadas.append(f"Porosidad({perfil.porosidad_cabello.puntaje_base} pts)")
                
                fuente_principal = "Análisis v6.0 (Nivel 3: Matriz de Perfil)"
                
        except AttributeError as e:
            return Response(
                {"error": f"Error de configuración: {e}. ¿Falta 'puntaje_base' en models.py o en la migración?"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # --- 3. GENERACIÓN DE MENSAJE (Basado en tu lógica de puntaje 1-10) ---
        
        mensaje_diagnostico = ""
        accion_recomendada = ""
        
        # (Usamos tu escala: 1=Malo, 10=Bueno)
        if puntaje_salud_total <= 3: # Umbral para "Dañado"
            mensaje_diagnostico = "Tu perfil indica que tu cabello está muy dañado y necesita una rutina de reparación intensiva."
            accion_recomendada = "Recomendamos rutina de Reparación Intensiva."
        elif puntaje_salud_total <= 7: # Umbral para "Normal"
            mensaje_diagnostico = "Tu cabello está en un estado normal, pero necesita mantenimiento regular."
            accion_recomendada = "Recomendamos rutina de Mantenimiento (Hidratación/Nutrición)."
        else: # (Puntaje > 7 = "Sano")
            mensaje_diagnostico = "¡Felicidades! Tu cabello está en un estado óptimo y saludable."
            accion_recomendada = "Recomendamos una rutina de cuidado preventivo."

        # --- 4. RESPUESTA FINAL (Nivel 2/3) ---
        return Response({
            'mensaje_diagnostico': mensaje_diagnostico,
            'accion': accion_recomendada,
            'puntaje_final': puntaje_salud_total,
            'fuente': f"{fuente_principal} (Reglas: {', '.join(reglas_activadas)})"
        })