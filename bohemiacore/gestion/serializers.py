from rest_framework import serializers
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo,
    EstadoGeneral, Equipamiento, Producto, ReglaDiagnostico,
    Notificacion, Rutina, AgendaCuidados, RutinaCliente, Servicio,
    CategoriaServicio, Turno, HorarioLaboral, BloqueoAgenda, Personal,
    #PasoRutina, #PasoRutinaCliente,

)

from usuarios.models import Usuario, Cliente
import os
from django.core.exceptions import ValidationError 

# 1. EL SERIALIZER BASE (El "Molde")
# Define los campos que TODOS los catálogos compartirán
class CatalogoBaseSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ['id', 'nombre', 'descripcion']
        abstract = True 

# 2. LOS SERIALIZERS ESPECÍFICOS (Heredan los campos)
# Ahora solo definimos el 'model' y heredamos los campos del molde
class TipoCabelloSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = TipoCabello

class GrosorCabelloSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = GrosorCabello

class PorosidadCabelloSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = PorosidadCabello

class CueroCabelludoSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = CueroCabelludo

class EstadoGeneralSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = EstadoGeneral

class CategoriaServicioSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = CategoriaServicio

# 3. SERIALIZERS ADICIONALES PARA OTROS MODELOS
class ServicioSerializer(serializers.ModelSerializer):
    # Campos de lectura para mostrar nombres en lugar de IDs en la tabla
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    rutina_nombre = serializers.CharField(source='rutina_recomendada.nombre', read_only=True)
    
    class Meta:
        model = Servicio
        fields = [
            'id', 'nombre', 'descripcion', 'categoria', 'categoria_nombre',
            'duracion_estimada', 'precio_base',
            'rutina_recomendada', 'rutina_nombre',
            'impacto_porosidad', 'impacto_estado',
            'activo'
        ]
   
class TurnoSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.usuario.get_full_name', read_only=True)
    servicio_nombre = serializers.CharField(source='servicio.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(),
        required=False,
        allow_null=True
    )
    profesional = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.filter(is_staff=True), #
        required=False,
        allow_null=True
    )
    class Meta:
        model = Turno
        fields = [
            'id', 'cliente', 'cliente_nombre', 
            'servicio', 'servicio_nombre', 
            'profesional', 
            'fecha', 'hora_inicio', 'hora_fin_calculada', 
            'estado', 'estado_display', 'comprobante_pago', 'fecha_creacion'
        ]
        read_only_fields = ['id', 'hora_fin_calculada', 'fecha_creacion', 'cliente_nombre', 'servicio_nombre', 'estado_display']
        extra_kwargs = {
            'estado': {'required': False},
        }

    def validate_comprobante_pago(self, value):
        """
        Validación Técnica del Comprobante (Item 4 Cátedra)
        """
        if not value:
            return value

        # 1. Validar Tamaño (Máximo 5MB)
        limit_mb = 5
        if value.size > limit_mb * 1024 * 1024:
            raise serializers.ValidationError(f"El archivo es muy grande. Máximo permitido: {limit_mb}MB.")

        # 2. Validar Extensión (Solo imágenes o PDF)
        ext = os.path.splitext(value.name)[1].lower()
        valid_extensions = ['.jpg', '.jpeg', '.png', '.pdf']
        if ext not in valid_extensions:
            raise serializers.ValidationError("Formato no soportado. Suba una imagen (JPG, PNG) o PDF.")

        return value

class TurnoCreateSerializer(serializers.ModelSerializer):
    """
    Serializer ESPECÍFICO para crear turnos desde el cliente.
    Hace que el campo 'cliente' sea de solo lectura para el frontend,
    eliminando la validación de 'requerido'.
    """
    class Meta:
        model = Turno
        fields = ['servicio', 'fecha', 'hora_inicio', 'cliente', 'estado']
        # ALERTA: Esto es la Solución Definitiva
        read_only_fields = ['cliente', 'estado']

"""
class PasoRutinaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PasoRutina
        fields = ['id', 'orden', 'titulo', 'descripcion', 'frecuencia', 'plantilla']

"""
class RutinaSerializer(serializers.ModelSerializer):
    # pasos = PasoRutinaSerializer(many=True, read_only=True)
    creada_por_nombre = serializers.CharField(source='creada_por.get_full_name', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    usuarios_usando = serializers.SerializerMethodField()
    
    class Meta:
        model = Rutina
        fields = [
            'id', 'nombre', 'objetivo', 'descripcion', 'version', 'archivo',
            'estado', 'estado_display', 'creada_por', 'creada_por_nombre',
            'fecha_creacion', 'fecha_obsoleta', 'usuarios_usando'
        ]
        read_only_fields = ['id', 'fecha_creacion', 'fecha_obsoleta', 'creada_por', 'creada_por_nombre', 'estado_display', 'usuarios_usando']
    
    def get_usuarios_usando(self, obj):
        """Retorna la cantidad de usuarios que tienen esta rutina asignada."""
        return obj.copias_cliente.count()
    
    def create(self, validated_data):
        """Auto-asigna creada_por al usuario autenticado durante la creación."""
        validated_data['creada_por'] = self.context['request'].user
        print(f"✅ Creando rutina con validated_data: {validated_data}")
        print(f"✅ Archivo en validated_data: {validated_data.get('archivo')}")
        return super().create(validated_data)


"""
class PasoRutinaClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PasoRutinaCliente
        fields = '__all__'
"""

class RutinaClienteSerializer(serializers.ModelSerializer):
    # pasos = PasoRutinaClienteSerializer(many=True, read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    rutina_original = serializers.IntegerField(source='rutina_original.id', read_only=True)

    class Meta:
        model = RutinaCliente
        fields = ['id', 'nombre', 'objetivo', 'descripcion', #'pasos',
                   'archivo', 'estado', 'estado_display', 'fecha_asignacion', 'version_asignada', 'descargar_notificacion', 'rutina_original']
        read_only_fields = ['id', 'nombre', 'objetivo', 'descripcion', #'pasos',
                             'estado', 'estado_display', 'fecha_asignacion', 'version_asignada', 'descargar_notificacion', 'rutina_original']


class RutinaClienteCreateSerializer(serializers.Serializer):
    """
    Serializer ESPECÍFICO para que el cliente seleccione una rutina del catálogo.
    """
    rutina_id = serializers.IntegerField(help_text="ID de la rutina a asignar")
    
    def validate_rutina_id(self, value):
        """Valida que la rutina exista y pueda asignarse."""
        try:
            rutina = Rutina.objects.get(id=value)
        except Rutina.DoesNotExist:
            raise serializers.ValidationError("La rutina no existe.")
        
        if not rutina.puede_asignarse():
            raise serializers.ValidationError(
                f"La rutina no puede asignarse en estado '{rutina.get_estado_display()}'."
            )
        
        return value
    
    def create(self, validated_data):
        """
        Crea una copia de la rutina para el cliente.
        El cliente se obtiene de la request en la view.
        """
        rutina_id = validated_data['rutina_id']
        rutina = Rutina.objects.get(id=rutina_id)
        cliente = self.context['cliente']  # Se pasa desde la view
        
        return rutina.asignar_a_cliente(cliente)

class AgendaCuidadosSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgendaCuidados
        fields = ['id', 'fecha', 'titulo', 'descripcion', 'completado']

class NotificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacion
        fields = ['id', 'titulo', 'mensaje', 'tipo', 'estado', 'fecha_envio', 'datos_extra', 'usuario', 'canal']

class ReglaDiagnosticoSerializer(serializers.ModelSerializer):
    # Campos de solo lectura para mostrar nombres en la tabla
    rutina_nombre = serializers.CharField(source='rutina_sugerida.nombre', read_only=True)
    
    # Nombres de las condiciones para facilitar la lectura en la tabla
    tipo_nombre = serializers.CharField(source='tipo_cabello.nombre', read_only=True)
    estado_nombre = serializers.CharField(source='estado_general.nombre', read_only=True)
    cuero_nombre = serializers.CharField(source='cuero_cabelludo.nombre', read_only=True)

    class Meta:
        model = ReglaDiagnostico
        fields = [
            'id', 'prioridad', 
            'tipo_cabello', 'tipo_nombre',
            'grosor_cabello', 
            'porosidad_cabello',
            'cuero_cabelludo', 'cuero_nombre',
            'estado_general', 'estado_nombre',
            'mensaje_resultado', 'accion_resultado',
            'rutina_sugerida', 'rutina_nombre'
        ]
    

# --- A. SERIALIZER USUARIOS (ADMIN) ---
class UsuarioAdminSerializer(serializers.ModelSerializer):
    """
    Permite al admin crear/editar usuarios profesionales.
    """
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Usuario
        fields = ['id', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'password']
    
    def create(self, validated_data):
        # Usamos create_user para hashear la contraseña correctamente
        password = validated_data.pop('password', None)
        user = Usuario.objects.create_user(**validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        # Actualización estándar
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

# --- B. SERIALIZER PRODUCTOS ---
class ProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = '__all__'

    def validate_precio(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio de venta debe ser mayor a cero.") #
        return value

# --- D. SERIALIZER EQUIPAMIENTO ---
class EquipamientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Equipamiento
        fields = '__all__'


class HorarioLaboralSerializer(serializers.ModelSerializer):
    dia_nombre = serializers.CharField(source='get_dia_semana_display', read_only=True)
    
    class Meta:
        model = HorarioLaboral
        fields = ['id', 'dia_semana', 'dia_nombre', 'hora_inicio', 'hora_fin']

class BloqueoAgendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = BloqueoAgenda
        fields = ['id', 'fecha_inicio', 'fecha_fin', 'motivo', 'bloquea_todo_el_dia']