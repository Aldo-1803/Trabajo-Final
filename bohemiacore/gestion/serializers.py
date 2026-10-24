from rest_framework import serializers
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo,
    EstadoGeneral, Equipamiento, Producto, ImagenProducto, ReglaDiagnostico,
    Notificacion, Rutina, AgendaCuidados, RutinaCliente, Servicio,
    CategoriaServicio, Turno, DetalleTurno, HorarioLaboral, BloqueoAgenda, Personal,
    Habilidad, PersonalHabilidad,
    TipoEquipamiento, FichaTecnica, DiagnosticoCapilar, RequisitoServicio,
    CategoriaProducto, Promocion, Configuracion, ConfiguracionRetoque,
    Carrito, CarritoItem, ContenidoEducativo, MeGusta, ContenidoGuardado,
    OrdenPendiente, OrdenCompra, OrdenItem, Pago, ConfiguracionDiagnostico,
    #PasoRutina, #PasoRutinaCliente,
)

from usuarios.models import Usuario, Cliente
from usuarios.roles import BusinessRole
import os
from django.core.exceptions import ValidationError 
from datetime import datetime
from django.db import transaction

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
    requisitos_equipamiento = serializers.SerializerMethodField()
    
    class Meta:
        model = Servicio
        fields = [
            'id', 'nombre', 'descripcion', 'categoria', 'categoria_nombre',
            'duracion_estimada', 'precio_base',
            'rutina_recomendada', 'rutina_nombre',
            'impacto_porosidad', 'impacto_estado',
            'es_quimico_agresivo', 'dias_espera_bloqueo', 'dias_espera_minima',
            'plantilla_formula',
            'requisitos_equipamiento',
            'activo'
        ]
    
    def get_requisitos_equipamiento(self, obj):
        """Retorna los requisitos de equipamiento para este servicio"""
        requisitos = obj.requisitos_equipamiento.all()
        return RequisitoServicioSerializer(requisitos, many=True).data
   
class DetalleTurnoSerializer(serializers.ModelSerializer):
    servicio_nombre = serializers.CharField(source='servicio.nombre', read_only=True)
    servicio_plantilla_formula = serializers.CharField(source='servicio.plantilla_formula', read_only=True)
    servicio_impacto_porosidad = serializers.IntegerField(source='servicio.impacto_porosidad.id', read_only=True)
    servicio_impacto_porosidad_nombre = serializers.CharField(source='servicio.impacto_porosidad.nombre', read_only=True)
    servicio_impacto_estado = serializers.IntegerField(source='servicio.impacto_estado.id', read_only=True)
    servicio_impacto_estado_nombre = serializers.CharField(source='servicio.impacto_estado.nombre', read_only=True)
    
    class Meta:
        model = DetalleTurno
        fields = [
            'id', 'servicio', 'servicio_nombre', 'servicio_plantilla_formula',
            'servicio_impacto_porosidad', 'servicio_impacto_porosidad_nombre',
            'servicio_impacto_estado', 'servicio_impacto_estado_nombre',
            'precio_historico', 'duracion_minutos'
        ]
        read_only_fields = [
            'id', 'servicio_nombre', 'servicio_plantilla_formula',
            'servicio_impacto_porosidad', 'servicio_impacto_porosidad_nombre',
            'servicio_impacto_estado', 'servicio_impacto_estado_nombre'
        ]


class DetalleTurnoClienteReadSerializer(serializers.ModelSerializer):
    servicio_nombre = serializers.CharField(source='servicio.nombre', read_only=True)

    class Meta:
        model = DetalleTurno
        fields = ['id', 'servicio', 'servicio_nombre', 'duracion_minutos']


class TurnoAgendaReadSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.SerializerMethodField()
    profesional_nombre = serializers.SerializerMethodField()
    servicio_nombre = serializers.SerializerMethodField()
    servicio_id = serializers.SerializerMethodField()

    class Meta:
        model = Turno
        fields = [
            'id',
            'cliente',
            'cliente_nombre',
            'profesional',
            'profesional_nombre',
            'fecha',
            'hora_inicio',
            'estado',
            'servicio_id',
            'servicio_nombre',
        ]
        read_only_fields = fields

    def get_cliente_nombre(self, obj):
        return obj.cliente.usuario.get_full_name().strip() or obj.cliente.usuario.email

    def get_profesional_nombre(self, obj):
        if not obj.profesional:
            return None
        return f'{obj.profesional.nombre} {obj.profesional.apellido}'.strip()

    def get_servicio_nombre(self, obj):
        return ', '.join(
            detalle.servicio.nombre for detalle in obj.detalles.all()
        ) or 'Sin servicios'

    def get_servicio_id(self, obj):
        detalle = next(iter(obj.detalles.all()), None)
        return detalle.servicio_id if detalle else None


class TurnoClienteReadSerializer(serializers.ModelSerializer):
    detalles = DetalleTurnoClienteReadSerializer(many=True, read_only=True)
    profesional_nombre = serializers.SerializerMethodField()
    servicio_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Turno
        fields = [
            'id',
            'profesional',
            'profesional_nombre',
            'fecha',
            'hora_inicio',
            'estado',
            'detalles',
            'servicio_nombre',
            'comprobante_pago',
        ]
        read_only_fields = fields

    def get_profesional_nombre(self, obj):
        if not obj.profesional:
            return None
        return f'{obj.profesional.nombre} {obj.profesional.apellido}'.strip()

    def get_servicio_nombre(self, obj):
        return ', '.join(
            detalle.servicio.nombre for detalle in obj.detalles.all()
        ) or 'Sin servicios'


class TurnoComprobanteUploadSerializer(serializers.Serializer):
    comprobante_pago = serializers.FileField(required=True)

    def validate(self, attrs):
        unexpected_fields = set(self.initial_data.keys()) - {'comprobante_pago'}
        if unexpected_fields:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected_fields),
            })
        return attrs


class StrictTurnoCommandSerializer(serializers.Serializer):
    allowed_fields = frozenset()

    def validate(self, attrs):
        unexpected_fields = set(self.initial_data.keys()) - self.allowed_fields
        if unexpected_fields:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected_fields),
            })
        return attrs


class TurnoReservaCommandSerializer(StrictTurnoCommandSerializer):
    servicio = serializers.IntegerField(min_value=1)
    profesional = serializers.IntegerField(min_value=1)
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField()
    allowed_fields = frozenset({
        'servicio',
        'profesional',
        'fecha',
        'hora_inicio',
    })


class TurnoParaClienteCommandSerializer(TurnoReservaCommandSerializer):
    cliente_id = serializers.IntegerField(min_value=1)
    allowed_fields = TurnoReservaCommandSerializer.allowed_fields | {'cliente_id'}


class TurnoArrivalCommandSerializer(StrictTurnoCommandSerializer):
    allowed_fields = frozenset()


class TurnoRescheduleCommandSerializer(StrictTurnoCommandSerializer):
    fecha = serializers.DateField()
    hora = serializers.TimeField()
    profesional_id = serializers.IntegerField(min_value=1, required=False)
    motivo = serializers.CharField(max_length=500, trim_whitespace=True)
    allowed_fields = frozenset({
        'fecha',
        'hora',
        'profesional_id',
        'motivo',
    })


class TurnoCancellationCommandSerializer(StrictTurnoCommandSerializer):
    motivo = serializers.CharField(max_length=500, trim_whitespace=True)
    allowed_fields = frozenset({'motivo'})


class TurnoClientRescheduleCommandSerializer(StrictTurnoCommandSerializer):
    fecha = serializers.DateField()
    hora_inicio = serializers.TimeField()
    profesional_id = serializers.IntegerField(min_value=1, required=False)
    allowed_fields = frozenset({'fecha', 'hora_inicio', 'profesional_id'})


class TurnoSerializer(serializers.ModelSerializer):
    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(),
        required=False
    )
    # Nested serializer para los detalles/servicios del turno
    detalles = DetalleTurnoSerializer(many=True, required=False, allow_null=True)
    # Campo para servicio simple (cuando el frontend envía servicio_id)
    servicio = serializers.IntegerField(write_only=True, required=False)
    # Campos de lectura con nombres amigables
    cliente_nombre = serializers.SerializerMethodField(read_only=True)
    servicio_nombre = serializers.SerializerMethodField(read_only=True)
    profesional_nombre = serializers.SerializerMethodField(read_only=True)
    cancelado_por_nombre = serializers.SerializerMethodField(read_only=True)
    # ✅ NUEVO: Campos para verificar expiración
    expired = serializers.SerializerMethodField(read_only=True)
    horas_transcurridas = serializers.SerializerMethodField(read_only=True)
    puede_modificar = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Turno
        fields = [
            'id', 'cliente', 'cliente_nombre', 'profesional', 'profesional_nombre', 
            'equipamiento', 'fecha', 'hora_inicio', 'estado', 'alerta_daño_capilar', 'canal_origen',
            'tipo_pago_registro', 'monto_abonado', 'saldo_pendiente', 'detalles', 'servicio', 
            'servicio_nombre', 'comprobante_pago', 'expired', 'horas_transcurridas', 'puede_modificar',
            'cancelado_por', 'cancelado_por_nombre', 'motivo_cancelacion'
        ]
        read_only_fields = ['alerta_daño_capilar', 'canal_origen', 'saldo_pendiente', 'expired', 'horas_transcurridas', 'puede_modificar', 'cancelado_por', 'cancelado_por_nombre']
        validators = []
    
    def get_cliente_nombre(self, obj):
        """Retorna el nombre completo del cliente"""
        if obj.cliente and obj.cliente.usuario:
            return f"{obj.cliente.usuario.first_name} {obj.cliente.usuario.last_name}".strip()
        return "Desconocido"
    
    def get_servicio_nombre(self, obj):
        """Retorna los nombres de servicios concatenados"""
        servicios = [d.servicio.nombre for d in obj.detalles.all()]
        return ', '.join(servicios) if servicios else "Sin servicios"
    
    def get_profesional_nombre(self, obj):
        """Retorna el nombre del profesional si existe"""
        if obj.profesional:
            return obj.profesional.nombre
        return "No asignado"
    
    def get_cancelado_por_nombre(self, obj):
        """Retorna el nombre de quién canceló"""
        if obj.cancelado_por:
            return obj.cancelado_por.get_full_name()
        return None

    def get_expired(self, obj):
        """✅ NUEVO: Verifica si el turno ya pasó su fecha"""
        from django.utils import timezone
        now = timezone.now()
        turno_dt = timezone.make_aware(datetime.combine(obj.fecha, obj.hora_inicio)) \
            if timezone.is_naive(datetime.combine(obj.fecha, obj.hora_inicio)) \
            else datetime.combine(obj.fecha, obj.hora_inicio)
        return turno_dt < now

    def get_horas_transcurridas(self, obj):
        """✅ NUEVO: Horas que transcurrieron desde que pasó la fecha"""
        from django.utils import timezone
        now = timezone.now()
        turno_dt = timezone.make_aware(datetime.combine(obj.fecha, obj.hora_inicio)) \
            if timezone.is_naive(datetime.combine(obj.fecha, obj.hora_inicio)) \
            else datetime.combine(obj.fecha, obj.hora_inicio)
        if turno_dt < now:
            return round((now - turno_dt).total_seconds() / 3600, 1)
        return 0

    def get_puede_modificar(self, obj):
        """✅ NUEVO: Indica si el cliente puede aún modificar el turno"""
        expired = self.get_expired(obj)
        return not expired and obj.estado in ['solicitado', 'esperando_sena']

    def update(self, instance, validated_data):
        """Actualizar un turno existente"""
        from .models import DetalleTurno
        
        # Remover campos que no se pueden actualizar
        validated_data.pop('servicio', None)
        detalles_data = validated_data.pop('detalles', None)
        
        # Actualizar campos simples
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # No actualizar detalles en un PATCH de estado
        # Los detalles solo se crean en POST
        
        return instance

class FichaTecnicaSerializer(serializers.ModelSerializer):
    """Serializador para el registro técnico del profesional"""
    detalle_turno_id = serializers.IntegerField(source='detalle_turno.id', read_only=True)
    servicio_nombre = serializers.CharField(source='detalle_turno.servicio.nombre', read_only=True)
    servicio_id = serializers.IntegerField(source='detalle_turno.servicio.id', read_only=True)
    profesional_nombre = serializers.CharField(source='profesional_autor.get_full_name', read_only=True)
    cliente_id = serializers.IntegerField(source='detalle_turno.turno.cliente.id', read_only=True)
    cliente_nombre = serializers.CharField(source='detalle_turno.turno.cliente.usuario.get_full_name', read_only=True)
    turno_id = serializers.IntegerField(source='detalle_turno.turno.id', read_only=True)
    turno_fecha = serializers.DateField(source='detalle_turno.turno.fecha', read_only=True)
    turno_hora = serializers.TimeField(source='detalle_turno.turno.hora_inicio', read_only=True)
    rutina_recomendada_nombre = serializers.CharField(source='rutina_recomendada.nombre', read_only=True)
    
    # Campo extra para enviar la plantilla al frontend (Lógica de Inicio)
    formula_base_servicio = serializers.CharField(
        source='detalle_turno.servicio.plantilla_formula', read_only=True
    )
    
    # Campos de lectura con nombres amigables para el frontend
    porosidad_final_nombre = serializers.CharField(
        source='porosidad_final.nombre', read_only=True
    )
    estado_general_final_nombre = serializers.CharField(
        source='estado_general_final.nombre', read_only=True
    )
    
    class Meta:
        model = FichaTecnica
        fields = [
            'id', 'detalle_turno', 'detalle_turno_id', 'servicio_nombre',
            'servicio_id', 'profesional_autor', 'profesional_nombre', 'formula_base_servicio',
            'cliente_id', 'cliente_nombre', 'turno_id', 'turno_fecha', 'turno_hora',
            'formula', 'observaciones_proceso', 'comentario_cliente',
            'rutina_recomendada', 'rutina_recomendada_nombre',
            'porosidad_final', 'porosidad_final_nombre',
            'estado_general_final', 'estado_general_final_nombre',
            'resultado_post_servicio', 'foto_resultado', 'fecha_registro'
        ]
        read_only_fields = [
            'id', 'fecha_registro', 'detalle_turno_id', 'servicio_nombre', 
            'servicio_id', 'profesional_nombre', 'formula_base_servicio',
            'cliente_id', 'cliente_nombre', 'turno_id', 'turno_fecha', 'turno_hora',
            'porosidad_final_nombre', 'estado_general_final_nombre',
            'rutina_recomendada_nombre'
        ]
    
    def validate(self, data):
        # 1. Validar que el usuario sea Staff/Profesional
        user = self.context['request'].user
        if not user.is_staff:
            raise serializers.ValidationError("Solo el personal técnico puede registrar fórmulas.")
        
        detalle = data.get('detalle_turno')
        
        # 2. Validación: Solo se puede crear ficha si el turno está 'confirmado' o 'en_proceso'
        if detalle.turno.estado not in ['confirmado', 'en_proceso']:
            raise serializers.ValidationError("No se puede registrar una ficha para un turno que no ha sido iniciado o confirmado.")
        
        # 3. Validar que el DetalleTurno no tenga ya una ficha (OneToOneField)
        if FichaTecnica.objects.filter(detalle_turno=detalle).exists():
            raise serializers.ValidationError("Este servicio ya tiene una ficha técnica registrada.")
            
        return data
    
    def create(self, validated_data):
        # Implementación del Punto 2 del análisis: Persistencia Robusta y Atómica
        with transaction.atomic():
            # 1. Asignar autor
            validated_data['profesional_autor'] = self.context['request'].user
            ficha = super().create(validated_data)

            return ficha

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
    usuario_activo = serializers.BooleanField(
        source='usuario.is_active',
        read_only=True,
    )
    usuario_business_role = serializers.SerializerMethodField()
    horarios = serializers.SerializerMethodField()
    
    class Meta:
        model = Personal
        fields = [
            'id', 'nombre', 'apellido', 'rol', 'email', 'telefono', 
            'activo', 'color_calendario', 'usuario',
            'realiza_diagnostico', 'realiza_lavado', 'realiza_color',
            'usuario_email', 'usuario_activo', 'usuario_business_role',
            'horarios'
        ]
        read_only_fields = [
            'usuario',
            'usuario_email',
            'usuario_activo',
            'usuario_business_role',
            'realiza_diagnostico',
            'realiza_lavado',
            'realiza_color',
        ]

    def get_usuario_business_role(self, obj):
        if obj.usuario_id is None:
            return None
        group_names = {group.name for group in obj.usuario.groups.all()}
        roles = tuple(
            role for role in BusinessRole.ALL if role in group_names
        )
        return roles[0] if len(roles) == 1 else None

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


class HabilidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habilidad
        fields = ['id', 'code', 'nombre', 'descripcion', 'activa']
        read_only_fields = fields


class PersonalHabilidadSerializer(serializers.ModelSerializer):
    habilidad = HabilidadSerializer(read_only=True)

    class Meta:
        model = PersonalHabilidad
        fields = ['id', 'habilidad', 'activa', 'fecha_asignacion']
        read_only_fields = fields


class PersonalHabilidadAssignCommandSerializer(serializers.Serializer):
    habilidad_id = serializers.IntegerField(min_value=1)

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unexpected_fields = set(data.keys()) - set(self.fields)
            if unexpected_fields:
                raise serializers.ValidationError({
                    field: ['Este campo no está permitido.']
                    for field in sorted(unexpected_fields)
                })
        return super().to_internal_value(data)


class PersonalUserLinkCommandSerializer(serializers.Serializer):
    usuario_id = serializers.IntegerField(min_value=1)
    motivo = serializers.CharField(
        min_length=3,
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
    )

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unexpected_fields = set(data.keys()) - set(self.fields)
            if unexpected_fields:
                raise serializers.ValidationError({
                    field: ['Este campo no está permitido.']
                    for field in sorted(unexpected_fields)
                })
        return super().to_internal_value(data)


class PersonalAccessCreateCommandSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password_temporal = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )
    role = serializers.CharField(max_length=50)
    motivo = serializers.CharField(
        min_length=3,
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
    )

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unexpected_fields = set(data.keys()) - set(self.fields)
            if unexpected_fields:
                raise serializers.ValidationError({
                    field: ['Este campo no está permitido.']
                    for field in sorted(unexpected_fields)
                })
        return super().to_internal_value(data)


class PersonalBusinessRoleChangeCommandSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=(
        BusinessRole.EMPLEADO,
        BusinessRole.PROFESIONAL,
    ))
    motivo = serializers.CharField(
        min_length=3,
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
    )

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unexpected_fields = set(data.keys()) - set(self.fields)
            if unexpected_fields:
                raise serializers.ValidationError({
                    field: ['Este campo no está permitido.']
                    for field in sorted(unexpected_fields)
                })
        return super().to_internal_value(data)


class PersonalStatusChangeCommandSerializer(serializers.Serializer):
    motivo = serializers.CharField(
        min_length=3,
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
    )

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unexpected_fields = set(data.keys()) - set(self.fields)
            if unexpected_fields:
                raise serializers.ValidationError({
                    field: ['Este campo no está permitido.']
                    for field in sorted(unexpected_fields)
                })
        return super().to_internal_value(data)
    
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
    servicio_nombre = serializers.CharField(source='servicio_sugerido.nombre', read_only=True)
    
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
            'rutina_sugerida', 'rutina_nombre',
            'servicio_sugerido', 'servicio_nombre'
        ]
    

# --- A. SERIALIZERS USUARIOS (ADMIN) ---
class StrictInputFieldsMixin:
    """Reject fields outside the explicit command contract."""

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unexpected_fields = set(data.keys()) - set(self.fields)
            if unexpected_fields:
                raise serializers.ValidationError({
                    field: ['Este campo no está permitido.']
                    for field in sorted(unexpected_fields)
                })
        return super().to_internal_value(data)


class UsuarioAdminReadSerializer(serializers.ModelSerializer):
    business_role = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            # Compatibilidad temporal de lectura con GestionUsuarios.js.
            'is_staff',
            'is_active',
            'business_role',
        ]
        read_only_fields = fields

    def get_business_role(self, obj):
        group_names = {group.name for group in obj.groups.all()}
        roles = tuple(
            role for role in BusinessRole.ALL if role in group_names
        )
        return roles[0] if len(roles) == 1 else None


class UsuarioAdminIdentityUpdateSerializer(
    StrictInputFieldsMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = Usuario
        fields = ['email', 'first_name', 'last_name']


class UsuarioAccountStatusCommandSerializer(
    StrictInputFieldsMixin,
    serializers.Serializer,
):
    motivo = serializers.CharField(
        min_length=3,
        max_length=500,
        allow_blank=False,
        trim_whitespace=True,
    )

# --- B. SERIALIZER PRODUCTOS ---
class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = '__all__'


class ImagenProductoSerializer(serializers.ModelSerializer):
    imagen_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ImagenProducto
        fields = ['id', 'imagen', 'imagen_url', 'orden', 'producto']
    
    def get_imagen_url(self, obj):
        """Retorna la URL completa de la imagen"""
        if obj.imagen:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.imagen.url)
            return obj.imagen.url
        return None
    
    def validate_producto(self, value):
        """Valida que el producto exista"""
        if not value:
            raise serializers.ValidationError("El producto es requerido.")
        return value
    
    def create(self, validated_data):
        """Crear la imagen con logging para debuggear"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Creando ImagenProducto con datos: {validated_data}")
        return super().create(validated_data)


class ProductoSerializer(serializers.ModelSerializer):
    # Esto permite ver el nombre de la categoría en lugar de solo el ID
    categoria_nombre = serializers.ReadOnlyField(source='categoria.nombre')
    # Incluir las imágenes del producto
    imagenes = ImagenProductoSerializer(many=True, read_only=True)
    # URL de la primera imagen (para compatibilidad)
    imagen_url = serializers.SerializerMethodField()
    # Stock disponible (propiedad calculada)
    stock_disponible = serializers.SerializerMethodField()
    necesita_reposicion = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id', 'sku', 'nombre', 'marca', 'categoria', 'categoria_nombre',
            'descripcion', 'precio', 'stock_real', 'stock_comprometido', 'stock_minimo',
            'stock_disponible', 'necesita_reposicion',
            'imagen', 'imagen_url', 'imagenes', 'estado_publicacion', 'compatibilidad',
            'material_principal', 'proposito_uso', 'activo'
        ]
        read_only_fields = ['id', 'categoria_nombre', 'imagen_url', 'imagenes', 'stock_comprometido', 'stock_disponible', 'necesita_reposicion']
    
    def get_stock_disponible(self, obj):
        """Retorna el stock disponible calculado"""
        return obj.stock_disponible
    
    def get_necesita_reposicion(self, obj):
        """Indica si necesita reposición"""
        return obj.necesita_reposicion()
    
    def get_imagen_url(self, obj):
        """Retorna la URL de la primera imagen o la imagen principal"""
        # Intentar obtener la primera imagen del relacionado
        primera_imagen = obj.imagenes.first()
        if primera_imagen and primera_imagen.imagen:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(primera_imagen.imagen.url)
            return primera_imagen.imagen.url
        # Si no hay imágenes relacionadas, usar la imagen del modelo (para compatibilidad)
        if obj.imagen:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.imagen.url)
            return obj.imagen.url
        return None

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
            'hora_inicio', 'hora_fin', 'fecha_desde', 'fecha_hasta',
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


class RequisitoServicioSerializer(serializers.ModelSerializer):
    """
    Serializer para la tabla intermedia RequisitoServicio.
    Muestra qué equipamiento es requerido para cada servicio.
    
    Validaciones:
    - tipo_equipamiento debe existir en la BD
    - No permite asignar equipos que no existan
    """
    servicio_nombre = serializers.CharField(source='servicio.nombre', read_only=True)
    tipo_equipamiento_nombre = serializers.CharField(source='tipo_equipamiento.nombre', read_only=True)
    
    class Meta:
        model = RequisitoServicio
        fields = [
            'id', 'servicio', 'servicio_nombre',
            'tipo_equipamiento', 'tipo_equipamiento_nombre',
            'obligatorio', 'cantidad_minima', 'fecha_registro'
        ]
        read_only_fields = ['id', 'fecha_registro', 'servicio_nombre', 'tipo_equipamiento_nombre']

    def validate_tipo_equipamiento(self, value):
        """
        Validar que el tipo_equipamiento existe en la BD.
        """
        from .models import TipoEquipamiento
        
        if not value:
            raise serializers.ValidationError(
                'El tipo de equipamiento es obligatorio.'
            )
        
        # Verificar que existe
        if not TipoEquipamiento.objects.filter(id=value.id).exists():
            raise serializers.ValidationError(
                f'El tipo de equipamiento "{value.nombre}" no existe en el sistema. '
                f'Debes crear primero el equipamiento antes de asignarlo a un servicio.'
            )
        
        return value

    def validate_cantidad_minima(self, value):
        """
        Validar que cantidad_minima sea positiva.
        """
        if value < 1:
            raise serializers.ValidationError(
                'La cantidad mínima debe ser al menos 1.'
            )
        return value

    def validate(self, data):
        """
        Validación a nivel de objeto completo.
        """
        servicio = data.get('servicio')
        tipo_equipamiento = data.get('tipo_equipamiento')
        
        if servicio and tipo_equipamiento:
            # Evitar duplicados (ya controlado por unique_together en Meta)
            # Pero aquí podemos dar un mensaje más amigable
            existing = RequisitoServicio.objects.filter(
                servicio=servicio,
                tipo_equipamiento=tipo_equipamiento
            ).first()
            
            # Si existe un requisito duplicado y no es el que estamos editando
            if existing and (not self.instance or existing.id != self.instance.id):
                raise serializers.ValidationError(
                    f'Este servicio ya requiere "{tipo_equipamiento.nombre}".'
                )
        
        return data

class DiagnosticoCapilarSerializer(serializers.ModelSerializer):
    """
    Serializer para el diagnóstico capilar.
    Contiene toda la información del estado del cabello en un momento específico.
    """
    cliente_email = serializers.CharField(source='cliente.usuario.email', read_only=True)
    profesional_nombre = serializers.CharField(source='profesional.get_full_name', read_only=True)
    tipo_cabello_nombre = serializers.CharField(source='tipo_cabello.nombre', read_only=True)
    grosor_cabello_nombre = serializers.CharField(source='grosor_cabello.nombre', read_only=True)
    porosidad_cabello_nombre = serializers.CharField(source='porosidad_cabello.nombre', read_only=True)
    cuero_cabelludo_nombre = serializers.CharField(source='cuero_cabelludo.nombre', read_only=True)
    estado_general_nombre = serializers.CharField(source='estado_general.nombre', read_only=True)
    regla_diagnostico_mensaje = serializers.CharField(source='regla_diagnostico.mensaje_resultado', read_only=True)
    regla_diagnostico_accion = serializers.CharField(source='regla_diagnostico.accion_resultado', read_only=True)
    rutina_sugerida_nombre = serializers.CharField(source='rutina_sugerida.nombre', read_only=True)
    rutina_asignada_nombre = serializers.CharField(source='rutina_asignada.nombre', read_only=True, required=False)
    servicio_urgente_nombre = serializers.CharField(source='servicio_urgente.nombre', read_only=True, required=False)
    servicio_urgente_id = serializers.IntegerField(source='servicio_urgente.id', read_only=True, required=False)
    rutina_asignada_id = serializers.IntegerField(source='rutina_asignada.id', read_only=True, required=False)
    turno_sugerido_id = serializers.IntegerField(source='turno_sugerido.id', read_only=True, required=False)
    # Campo personalizado: el mensaje profesional guardado en observaciones
    mensaje_diagnostico = serializers.CharField(source='observaciones', read_only=True, required=False)
    
    class Meta:
        model = DiagnosticoCapilar
        fields = [
            'id', 'cliente', 'cliente_email',
            'profesional', 'profesional_nombre',
            'tipo_cabello', 'tipo_cabello_nombre',
            'grosor_cabello', 'grosor_cabello_nombre',
            'porosidad_cabello', 'porosidad_cabello_nombre',
            'cuero_cabelludo', 'cuero_cabelludo_nombre',
            'estado_general', 'estado_general_nombre',
            'observaciones', 'mensaje_diagnostico', 'recomendaciones',
            'regla_diagnostico', 'regla_diagnostico_mensaje', 'regla_diagnostico_accion',
            'rutina_sugerida', 'rutina_sugerida_nombre',
            'rutina_asignada', 'rutina_asignada_nombre', 'rutina_asignada_id',
            'servicio_urgente', 'servicio_urgente_nombre', 'servicio_urgente_id',
            'turno_sugerido', 'turno_sugerido_id',
            'fecha_diagnostico'
        ]
        read_only_fields = [
            'id', 'fecha_diagnostico', 'cliente_email', 'profesional_nombre',
            'profesional',
            'tipo_cabello_nombre', 'grosor_cabello_nombre', 'porosidad_cabello_nombre',
            'cuero_cabelludo_nombre', 'estado_general_nombre', 'regla_diagnostico_accion',
            'regla_diagnostico', 'regla_diagnostico_mensaje',
            'rutina_sugerida_nombre', 'mensaje_diagnostico', 'rutina_asignada_nombre',
            'rutina_sugerida', 'rutina_asignada',
            'servicio_urgente', 'servicio_urgente_nombre', 'servicio_urgente_id',
            'rutina_asignada_id',
            'turno_sugerido', 'turno_sugerido_id'
        ]

    def validate(self, attrs):
        if self.instance is not None and 'cliente' in self.initial_data:
            requested_client = self.initial_data.get('cliente')
            if str(requested_client) != str(self.instance.cliente_id):
                raise serializers.ValidationError({
                    'cliente': 'El Cliente del diagnóstico no puede modificarse.'
                })
        return attrs


class ConfiguracionDiagnosticoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionDiagnostico
        fields = '__all__'


class PromocionSerializer(serializers.ModelSerializer):
    """
    Serializer para promociones del sistema.
    Gestiona los tres pilares: COMBO, RETOQUE, LAST_MINUTE.
    """
    productos_count = serializers.SerializerMethodField()
    servicios_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Promocion
        fields = [
            'id', 'nombre', 'descripcion', 'tipo', 
            'descuento_porcentaje', 'fecha_inicio', 'fecha_fin',
            'fecha_especifica', 'hora_inicio_promo', 'hora_fin_promo',
            'is_active', 'stock_combo', 'productos', 'servicios',
            'es_sugerencia_automatica', 'estado_sugerencia',
            'productos_count', 'servicios_count', 'fecha_creacion'
        ]
        read_only_fields = ['id', 'fecha_creacion', 'productos_count', 'servicios_count']
    
    def get_productos_count(self, obj):
        """Retorna el número de productos en la promoción"""
        return obj.productos.count()
    
    def get_servicios_count(self, obj):
        """Retorna el número de servicios en la promoción"""
        return obj.servicios.count()


class ConfiguracionRetoqueSummarySerializer(serializers.ModelSerializer):
    """Serializer compacto para mostrar configuraciones de retoque"""
    servicio_principal_nombre = serializers.CharField(source='servicio_principal.nombre', read_only=True)
    servicio_retoque_nombre = serializers.CharField(source='servicio_retoque.nombre', read_only=True)
    
    class Meta:
        model = ConfiguracionRetoque
        fields = [
            'id', 'servicio_principal', 'servicio_principal_nombre',
            'servicio_retoque', 'servicio_retoque_nombre',
            'dias_sugeridos', 'descuento_retoque'
        ]
        read_only_fields = ['id']


class ConfiguracionSerializer(serializers.ModelSerializer):
    """
    Serializer para la configuración global del sistema (patrón Singleton).
    Expone todos los parámetros configurables del negocio.
    """
    class Meta:
        model = Configuracion
        fields = [
            'id',
            'intervalo_turnos',
            'max_dias_anticipacion',
            'monto_sena',
            'tiempo_limite_pago_sena',
            'max_reprogramaciones',
            'horas_limite_cancelacion',
            'adelanto_min_horas_anticipacion',
            'adelanto_rango_dias_busqueda',
            'adelanto_max_candidatos',
            'adelanto_expira_horas',
            'promo_descuento_combo_x2',
            'promo_descuento_combo_x3',
            'combo_auto_activo',
            'combo_min_similitud',
            'combo_max_productos',
            'combo_min_stock',
            'combo_dias_vigencia',
            'combo_usar_marca',
            'combo_usar_proposito',
            'combo_usar_material',
            'combo_usar_compatibilidad',
            'whatsapp_numero',
            'empresa_nombre',
            'comprobante_razon_social',
            'comprobante_cuil',
            'comprobante_fecha_inicio_actividad',
            'whatsapp_saludo',
            'whatsapp_cierre',
            'whatsapp_formato_producto'
        ]
        read_only_fields = ['id']


class CarritoItemSerializer(serializers.ModelSerializer):
    """
    Serializer para items individuales del carrito.
    Incluye información completa del producto y cálculo de subtotal.
    """
    producto_nombre = serializers.ReadOnlyField(source='producto.nombre')
    producto_precio = serializers.ReadOnlyField(source='producto.precio')
    producto_marca = serializers.ReadOnlyField(source='producto.marca')
    producto_imagen_url = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = CarritoItem
        fields = ['id', 'producto', 'producto_nombre', 'producto_marca', 'producto_precio', 'producto_imagen_url', 'cantidad', 'subtotal']
    
    def get_subtotal(self, obj):
        """Retorna el subtotal del item."""
        return obj.subtotal
    
    def get_producto_imagen_url(self, obj):
        """Retorna la URL de la imagen del producto."""
        request = self.context.get('request')
        if obj.producto.imagen:
            if request:
                return request.build_absolute_uri(obj.producto.imagen.url)
            return obj.producto.imagen.url
        # Intenta obtener primera imagen del relacionado
        primera_imagen = obj.producto.imagenes.first()
        if primera_imagen and primera_imagen.imagen:
            if request:
                return request.build_absolute_uri(primera_imagen.imagen.url)
            return primera_imagen.imagen.url
        return None


class CarritoSerializer(serializers.ModelSerializer):
    """
    Serializer para el carrito de compras.
    Incluye items anidados y totales calculados.
    """
    items = CarritoItemSerializer(many=True, read_only=True)
    total = serializers.ReadOnlyField(source='total_carrito')

    class Meta:
        model = Carrito
        fields = ['id', 'cliente', 'items', 'total', 'actualizado']
        read_only_fields = ['id', 'actualizado']


# ============================================================
# SERIALIZERS PARA CONTENIDO EDUCATIVO
# ============================================================

class AutorContenidoSerializer(serializers.ModelSerializer):
    """
    Serializer anidado para mostrar datos del profesional/autor.
    """
    class Meta:
        model = Personal
        fields = ['id', 'nombre', 'apellido', 'rol']


class ContenidoEducativoSerializer(serializers.ModelSerializer):
    """
    Serializer para contenido educativo con información de interacciones.
    Incluye datos del autor, contadores de likes/guardados y estado personalizado del usuario.
    """
    total_likes = serializers.ReadOnlyField()
    total_guardados = serializers.ReadOnlyField()
    autor = AutorContenidoSerializer(read_only=True)
    
    # Información personalizada por usuario
    ya_le_gusta = serializers.SerializerMethodField()
    ya_esta_guardado = serializers.SerializerMethodField()

    class Meta:
        model = ContenidoEducativo
        fields = [
            'id', 'titulo', 'descripcion', 'contenido_texto', 'multimedia_url', 
            'tipo', 'tags', 'estado', 
            'autor', 'fecha_publicacion', 'fecha_actualizacion',
            'total_likes', 'total_guardados', 'ya_le_gusta', 'ya_esta_guardado'
        ]
        read_only_fields = ['fecha_publicacion', 'fecha_actualizacion']

    def get_ya_le_gusta(self, obj):
        """
        Verifica si el usuario actual likeó este contenido.
        Retorna False si el usuario no es cliente o no está autenticado.
        """
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        
        try:
            cliente = request.user.cliente
            return obj.me_gusta_por(cliente)
        except AttributeError:
            # Usuario no es cliente (ej: staff/admin)
            return False

    def get_ya_esta_guardado(self, obj):
        """
        Verifica si el usuario actual guardó este contenido.
        Retorna False si el usuario no es cliente o no está autenticado.
        """
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        
        try:
            cliente = request.user.cliente
            return obj.es_guardado_por(cliente)
        except AttributeError:
            return False


class MeGustaSerializer(serializers.ModelSerializer):
    """
    Serializer para registrar/eliminar likes en contenido.
    Incluye información del contenido y del cliente.
    """
    contenido_titulo = serializers.CharField(
        source='contenido.titulo', 
        read_only=True
    )
    cliente_nombre = serializers.SerializerMethodField()

    class Meta:
        model = MeGusta
        fields = ['id', 'contenido', 'contenido_titulo', 'cliente', 'cliente_nombre', 'fecha']
        read_only_fields = ['fecha']

    def get_cliente_nombre(self, obj):
        """Obtiene el nombre completo del cliente."""
        try:
            return obj.cliente.usuario.get_full_name()
        except:
            return "Anónimo"


class ContenidoGuardadoSerializer(serializers.ModelSerializer):
    """
    Serializer para contenido guardado por clientes.
    Permite que los usuarios tengan un historial de favoritos.
    """
    contenido_titulo = serializers.CharField(
        source='contenido.titulo',
        read_only=True
    )
    contenido_descripcion = serializers.CharField(
        source='contenido.descripcion',
        read_only=True
    )
    contenido_tipo = serializers.CharField(
        source='contenido.tipo',
        read_only=True
    )

    class Meta:
        model = ContenidoGuardado
        fields = [
            'id', 'contenido', 'contenido_titulo', 'contenido_descripcion',
            'contenido_tipo', 'cliente', 'fecha'
        ]
        read_only_fields = ['fecha']


class OrdenPendienteSerializer(serializers.ModelSerializer):
    """
    Serializer para órdenes pendientes (intenciones de compra por WhatsApp).
    Registra los items y monto para auditoría.
    """
    class Meta:
        model = OrdenPendiente
        fields = [
            'id',
            'cliente',
            'estado',
            'items_json',
            'monto_total',
            'fecha_creacion',
            'fecha_confirmacion',
            'fecha_completacion',
            'nota_cliente'
        ]


class OrdenItemSerializer(serializers.ModelSerializer):
    """
    Serializer para items individuales de órdenes de compra.
    """
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    producto_marca = serializers.CharField(source='producto.marca', read_only=True)
    subtotal = serializers.SerializerMethodField()
    
    class Meta:
        model = OrdenItem
        fields = [
            'id',
            'orden',
            'producto',
            'producto_nombre',
            'producto_marca',
            'cantidad',
            'precio_historico',
            'subtotal'
        ]
        read_only_fields = ['id', 'subtotal']
    
    def get_subtotal(self, obj):
        return float(obj.subtotal)


class PagoSerializer(serializers.ModelSerializer):
    orden_codigo = serializers.ReadOnlyField(source='orden.codigo')
    turno_fecha = serializers.SerializerMethodField()
    cliente_nombre = serializers.SerializerMethodField()
    cliente_email = serializers.SerializerMethodField()
    tipo_origen = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            'id',
            'orden',
            'turno',
            'monto',
            'metodo_pago',
            'fecha_pago',
            'comprobante_foto',
            'es_sena',
            'orden_codigo',
            'turno_fecha',
            'cliente_nombre',
            'cliente_email',
            'tipo_origen'
        ]
        read_only_fields = ['id', 'orden', 'turno']

    def validate(self, attrs):
        metodo = attrs.get('metodo_pago')
        comprobante = attrs.get('comprobante_foto')

        if metodo == 'TRANSFERENCIA' and not comprobante:
            raise serializers.ValidationError({
                'comprobante_foto': 'Se requiere comprobante para pagos por transferencia.'
            })

        return attrs

    def get_turno_fecha(self, obj):
        if obj.turno:
            return obj.turno.fecha
        return None

    def get_cliente_nombre(self, obj):
        if obj.orden and obj.orden.cliente and obj.orden.cliente.usuario:
            return obj.orden.cliente.usuario.get_full_name()
        if obj.turno and obj.turno.cliente and obj.turno.cliente.usuario:
            return obj.turno.cliente.usuario.get_full_name()
        return None

    def get_cliente_email(self, obj):
        if obj.orden and obj.orden.cliente and obj.orden.cliente.usuario:
            return obj.orden.cliente.usuario.email
        if obj.turno and obj.turno.cliente and obj.turno.cliente.usuario:
            return obj.turno.cliente.usuario.email
        return None

    def get_tipo_origen(self, obj):
        if obj.orden_id:
            return 'ORDEN'
        if obj.turno_id:
            return 'TURNO'
        return None


class OrdenCompraSerializer(serializers.ModelSerializer):
    """
    Serializer para órdenes de compra completas incluyendo sus items.
    """
    items = OrdenItemSerializer(many=True, read_only=True)
    pagos = PagoSerializer(many=True, read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.usuario.get_full_name', read_only=True)
    cliente_email = serializers.CharField(source='cliente.usuario.email', read_only=True)
    total_items = serializers.SerializerMethodField()
    
    class Meta:
        model = OrdenCompra
        fields = [
            'id',
            'codigo',
            'cliente',
            'cliente_nombre',
            'cliente_email',
            'estado',
            'total',
            'items',
            'pagos',
            'total_items',
            'notas',
            'creado_at',
            'actualizado_at'
        ]
        read_only_fields = ['id', 'codigo', 'creado_at', 'actualizado_at']
    
    def get_total_items(self, obj):
        return sum(item.cantidad for item in obj.items.all())





