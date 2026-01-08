from rest_framework import serializers
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo,
    EstadoGeneral, Equipamiento, Producto, ReglaDiagnostico,
    Notificacion, Rutina, AgendaCuidados, RutinaCliente, Servicio,
    CategoriaServicio, Turno, DetalleTurno, HorarioLaboral, BloqueoAgenda, Personal,
    TipoEquipamiento,
    #PasoRutina, #PasoRutinaCliente,
)

from .services import DisponibilidadService
from usuarios.models import Usuario, Cliente
import os
from django.core.exceptions import ValidationError 
from datetime import datetime

# 1. EL SERIALIZER BASE (El "Molde")
# Define los campos que TODOS los catálogos compartirán
class CatalogoBaseSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ['id', 'nombre', 'descripcion', 'activo', 'puntaje_base']
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

class CategoriaServicioSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaServicio
        fields = ['id', 'nombre', 'descripcion', 'activo']

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
   
class DetalleTurnoSerializer(serializers.ModelSerializer):
    servicio_nombre = serializers.CharField(source='servicio.nombre', read_only=True)
    
    class Meta:
        model = DetalleTurno
        fields = ['id', 'servicio', 'servicio_nombre', 'precio_historico', 'duracion_minutos']
        read_only_fields = ['id', 'servicio_nombre']


class TurnoSerializer(serializers.ModelSerializer):
    # Nested serializer para los detalles/servicios del turno
    detalles = DetalleTurnoSerializer(many=True)

    class Meta:
        model = Turno
        fields = [
            'id', 'cliente', 'profesional', 'equipamiento', 
            'fecha', 'hora_inicio', 'estado', 'detalles'
        ]

    def create(self, validated_data):
        # 1. Sacamos los detalles del paquete de datos
        detalles_data = validated_data.pop('detalles', [])
        # 2. Creamos el Turno principal
        turno = Turno.objects.create(**validated_data)
        # 3. Creamos cada detalle en la tabla intermedia
        for detalle in detalles_data:
            DetalleTurno.objects.create(turno=turno, **detalle)
        return turno

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


class PersonalSerializer(serializers.ModelSerializer):
    usuario_email = serializers.CharField(source='usuario.email', read_only=True)
    horarios = serializers.SerializerMethodField()
    
    class Meta:
        model = Personal
        fields = [
            'id', 'nombre', 'apellido', 'rol', 'email', 'telefono', 
            'activo', 'color_calendario', 'usuario',
            'realiza_diagnostico', 'realiza_lavado', 'realiza_color',
            'usuario_email', 'horarios'
        ]

    def get_horarios(self, obj):
        """Obtiene los horarios laborales asociados"""
        horarios = obj.horarios.all()
        return [
            {
                'id': h.id,
                'dia_semana': h.get_dia_semana_display(),
                'hora_inicio': str(h.hora_inicio),
                'hora_fin': str(h.hora_fin)
            }
            for h in horarios
        ]

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

class TipoEquipamientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoEquipamiento
        fields = ['id', 'nombre', 'descripcion']


class EquipamientoSerializer(serializers.ModelSerializer):
    # Ajuste 1: Para lectura, queremos ver el nombre del tipo, no solo el ID.
    tipo_nombre = serializers.ReadOnlyField(source='tipo.nombre')
    
    # Ajuste 2: El estado sigue siendo un choice, así que mantenemos su display.
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model = Equipamiento
        fields = [
            'id', 'codigo', 'nombre', 
            'tipo', 'tipo_nombre',  # Relación con la tabla maestra
            'estado', 'estado_display', 
            'ubicacion', 'observaciones', 
            'is_active', 'ultimo_mantenimiento'
        ]
        read_only_fields = ['is_active']

    def validate_codigo(self, value):
        return value.upper()

class HorarioLaboralSerializer(serializers.ModelSerializer):
    dia_nombre = serializers.CharField(source='get_dia_semana_display', read_only=True)
    
    class Meta:
        model = HorarioLaboral
        fields = [
            'id', 'personal', 'dia_semana', 'dia_nombre', 
            'hora_inicio', 'hora_fin', 
            'permite_diseno_color', 'permite_complemento', 'activo'
        ]

class BloqueoAgendaSerializer(serializers.ModelSerializer):
    class Meta:
        model = BloqueoAgenda
        fields = '__all__'

    def validate(self, data):
        inicio_bloqueo = data.get('fecha_inicio')
        fin_bloqueo = data.get('fecha_fin')
        personal = data.get('personal') # Puede ser None si es para todo el salón 

        # 1. Validación básica de fechas 
        if fin_bloqueo <= inicio_bloqueo:
            raise serializers.ValidationError("La fecha de fin debe ser posterior a la de inicio.")

        # 2. Búsqueda de Conflictos (Optimización SQL) 
        # Filtramos turnos activos en el rango de fechas involucradas
        turnos_en_rango = Turno.objects.filter(
            fecha__range=[inicio_bloqueo.date(), fin_bloqueo.date()],
            estado__in=['pendiente', 'confirmado']
        )

        if personal:
            turnos_en_rango = turnos_en_rango.filter(personal=personal)

        conflictos = []
        for turno in turnos_en_rango:
            # Combinamos fecha y hora para la comparación precisa
            t_inicio = datetime.combine(turno.fecha, turno.hora_inicio)
            t_fin = datetime.combine(turno.fecha, turno.hora_fin_calculada)
            
            # Lógica de solapamiento: (StartA < EndB) y (EndA > StartB) 
            if (t_inicio < fin_bloqueo.replace(tzinfo=None)) and (t_fin > inicio_bloqueo.replace(tzinfo=None)):
                conflictos.append({
                    "cliente": f"{turno.cliente.usuario.first_name} {turno.cliente.usuario.last_name}",
                    "horario": f"{turno.hora_inicio} - {turno.hora_fin_calculada}",
                    "servicio": turno.servicio.nombre
                })

        if conflictos:
            raise serializers.ValidationError({
                "error": "CONFLICTO_AGENDA",
                "mensaje": "Existen turnos que se solapan con este bloqueo.",
                "turnos_afectados": conflictos
            })

        return data