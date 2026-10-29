from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo,
    EstadoGeneral, Equipamiento, Producto, ImagenProducto, ReglaDiagnostico,
    Notificacion, Rutina, AgendaCuidados, RutinaCliente, Servicio,
    CategoriaServicio, Turno, DetalleTurno, HorarioLaboral, BloqueoAgenda, Personal,
    Habilidad, PersonalHabilidad, FamiliaProcesoTecnico,
    PerfilTecnicoServicio, PoliticaRiesgoTecnico,
    ReglaIntervaloTecnico, ReglaDiagnosticoTecnico,
    ReglaFrecuenciaTecnica,
    TipoEquipamiento, FichaTecnica, DiagnosticoCapilar, RequisitoServicio,
    CategoriaProducto, Promocion, Configuracion, ConfiguracionRetoque,
    Carrito, CarritoItem, ContenidoEducativo, MeGusta, ContenidoGuardado,
    OrdenPendiente, OrdenCompra, OrdenItem, Pago, ConfiguracionDiagnostico,
    DecisionRevisionTecnica, PAYMENT_CURRENCY_CHOICES, Pago,
    PaymentIntent, PaymentIntentLine, PaymentReconciliationCase, ProviderEvent,
    ProviderPaymentAttempt, MovimientoStock, SlotHold, SolicitudTecnicaReserva,
    #PasoRutina, #PasoRutinaCliente,
)

from usuarios.models import Usuario, Cliente
from usuarios.roles import BusinessPermission, BusinessRole
import os
from django.core.exceptions import ValidationError 
from datetime import datetime
from django.db import transaction
from django.utils import timezone

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


class FamiliaProcesoTecnicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = FamiliaProcesoTecnico
        fields = ['id', 'code', 'nombre', 'descripcion', 'activa']
        read_only_fields = ['id']


class PerfilTecnicoServicioSerializer(serializers.ModelSerializer):
    familia_code = serializers.CharField(source='familia.code', read_only=True)

    class Meta:
        model = PerfilTecnicoServicio
        fields = [
            'id', 'servicio', 'familia', 'familia_code',
            'estado_clasificacion', 'nivel_riesgo', 'activa',
        ]
        read_only_fields = ['id', 'familia_code']

    def validate(self, attrs):
        state = attrs.get(
            'estado_clasificacion',
            getattr(self.instance, 'estado_clasificacion', None),
        )
        risk = attrs.get(
            'nivel_riesgo',
            getattr(self.instance, 'nivel_riesgo', None),
        )
        if (
            state == PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
            and risk == PerfilTecnicoServicio.NivelRiesgo.NO_DEFINIDO
        ):
            raise serializers.ValidationError({
                'nivel_riesgo': 'Un Servicio clasificado requiere nivel de riesgo.'
            })
        return attrs


class PoliticaRiesgoTecnicoSerializer(serializers.ModelSerializer):
    publicada_por_email = serializers.CharField(
        source='publicada_por.email', read_only=True
    )

    class Meta:
        model = PoliticaRiesgoTecnico
        fields = [
            'id', 'version', 'estado', 'creada_at', 'publicada_at',
            'publicada_por', 'publicada_por_email',
        ]
        read_only_fields = [
            'id', 'estado', 'creada_at', 'publicada_at',
            'publicada_por', 'publicada_por_email',
        ]

    def validate_version(self, value):
        if self.instance is not None and self.instance.version != value:
            raise serializers.ValidationError(
                'La versión de una política no puede modificarse.'
            )
        return value


class TechnicalRiskRuleSerializerMixin:
    def validate(self, attrs):
        attrs = super().validate(attrs)
        policy = attrs.get('politica') or getattr(self.instance, 'politica', None)
        if (
            policy is None
            or policy.estado != PoliticaRiesgoTecnico.Estado.BORRADOR
        ):
            raise serializers.ValidationError({
                'politica': 'Sólo se pueden administrar reglas de un borrador.'
            })
        if (
            self.instance is not None
            and 'politica' in attrs
            and attrs['politica'].pk != self.instance.politica_id
        ):
            raise serializers.ValidationError({
                'politica': 'Una regla no puede moverse a otra política.'
            })
        self.validate_selectors(attrs)
        return attrs

    @staticmethod
    def _exactly_one(first, second):
        return (first is None) != (second is None)


class ReglaIntervaloTecnicoSerializer(
    TechnicalRiskRuleSerializerMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = ReglaIntervaloTecnico
        fields = '__all__'

    def validate_selectors(self, attrs):
        instance = self.instance
        origin_service = attrs.get(
            'servicio_origen', getattr(instance, 'servicio_origen', None)
        )
        origin_family = attrs.get(
            'familia_origen', getattr(instance, 'familia_origen', None)
        )
        target_service = attrs.get(
            'servicio_destino', getattr(instance, 'servicio_destino', None)
        )
        target_family = attrs.get(
            'familia_destino', getattr(instance, 'familia_destino', None)
        )
        errors = {}
        if not self._exactly_one(origin_service, origin_family):
            errors['origen'] = 'Debe seleccionar exactamente un origen.'
        if not self._exactly_one(target_service, target_family):
            errors['destino'] = 'Debe seleccionar exactamente un destino.'
        if errors:
            raise serializers.ValidationError(errors)


class ReglaDiagnosticoTecnicoSerializer(
    TechnicalRiskRuleSerializerMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = ReglaDiagnosticoTecnico
        fields = '__all__'

    def validate_selectors(self, attrs):
        instance = self.instance
        service = attrs.get(
            'servicio_destino', getattr(instance, 'servicio_destino', None)
        )
        family = attrs.get(
            'familia_destino', getattr(instance, 'familia_destino', None)
        )
        if not self._exactly_one(service, family):
            raise serializers.ValidationError({
                'destino': 'Debe seleccionar exactamente un destino.'
            })


class ReglaFrecuenciaTecnicaSerializer(
    TechnicalRiskRuleSerializerMixin,
    serializers.ModelSerializer,
):
    class Meta:
        model = ReglaFrecuenciaTecnica
        fields = '__all__'

    def validate_selectors(self, attrs):
        instance = self.instance
        service = attrs.get('servicio', getattr(instance, 'servicio', None))
        family = attrs.get('familia', getattr(instance, 'familia', None))
        if not self._exactly_one(service, family):
            raise serializers.ValidationError({
                'selector': 'Debe seleccionar exactamente un Servicio o familia.'
            })


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


class ProductoSerializer(StrictInputFieldsMixin, serializers.ModelSerializer):
    # Esto permite ver el nombre de la categoría en lugar de solo el ID
    categoria_nombre = serializers.ReadOnlyField(source='categoria.nombre')
    # Incluir las imágenes del producto
    imagenes = ImagenProductoSerializer(many=True, read_only=True)
    # URL de la primera imagen (para compatibilidad)
    imagen_url = serializers.SerializerMethodField()
    # Stock disponible (propiedad calculada)
    stock_disponible = serializers.SerializerMethodField()
    necesita_reposicion = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id', 'sku', 'nombre', 'marca', 'categoria', 'categoria_nombre',
            'descripcion', 'precio', 'stock_real', 'stock_comprometido', 'stock_minimo',
            'stock_disponible', 'necesita_reposicion', 'available',
            'imagen', 'imagen_url', 'imagenes', 'estado_publicacion', 'compatibilidad',
            'material_principal', 'proposito_uso', 'activo'
        ]
        read_only_fields = [
            'id', 'categoria_nombre', 'imagen_url', 'imagenes', 'stock_real',
            'stock_comprometido', 'stock_minimo', 'stock_disponible',
            'necesita_reposicion', 'available',
        ]

    INVENTORY_FIELDS = {
        'stock_real',
        'stock_comprometido',
        'stock_minimo',
        'stock_disponible',
        'necesita_reposicion',
        'available',
    }
    PRICE_FIELDS = {'precio'}
    PRODUCT_METADATA_FIELDS = {
        'sku',
        'nombre',
        'marca',
        'categoria',
        'descripcion',
        'imagen',
        'estado_publicacion',
        'compatibilidad',
        'material_principal',
        'proposito_uso',
        'activo',
    }

    def to_internal_value(self, data):
        submitted = set(data.keys()) if hasattr(data, 'keys') else set()
        inventory_fields = submitted & self.INVENTORY_FIELDS
        if inventory_fields:
            raise serializers.ValidationError({
                field: [
                    'El inventario sólo puede modificarse mediante los commands de stock.'
                ]
                for field in sorted(inventory_fields)
            })

        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if submitted & self.PRICE_FIELDS and not (
            user and user.has_perm(BusinessPermission.MANAGE_PRICES)
        ):
            raise PermissionDenied('No tiene permisos para modificar precios.')
        if submitted & self.PRODUCT_METADATA_FIELDS and not (
            user and user.has_perm(BusinessPermission.MANAGE_PRODUCTS)
        ):
            raise PermissionDenied('No tiene permisos para modificar productos.')
        return super().to_internal_value(data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        can_view_stock = bool(
            user is not None
            and user.has_perm(BusinessPermission.VIEW_STOCK)
        )
        if not can_view_stock:
            for field in (
                'stock_real',
                'stock_comprometido',
                'stock_minimo',
                'stock_disponible',
                'necesita_reposicion',
            ):
                representation.pop(field, None)
        return representation
    
    def get_stock_disponible(self, obj):
        """Retorna el stock disponible calculado"""
        return obj.stock_disponible
    
    def get_necesita_reposicion(self, obj):
        """Indica si necesita reposición"""
        return obj.necesita_reposicion()

    def get_available(self, obj):
        """Disponibilidad comercial mínima, sin publicar cantidades internas."""
        return obj.stock_disponible > 0
    
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
            'fecha_diagnostico', 'procedencia'
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
            'turno_sugerido', 'turno_sugerido_id', 'procedencia'
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


# ============================================================
# SOLICITUD TÉCNICA DE RESERVA (BH-057 B)
# ============================================================


class TechnicalBookingRequestCreateSerializer(serializers.Serializer):
    servicio_ids = serializers.PrimaryKeyRelatedField(
        source='servicios',
        queryset=Servicio.objects.filter(activo=True),
        many=True,
        allow_empty=False,
    )
    fecha_preferida = serializers.DateField()
    hora_preferida = serializers.TimeField()
    personal_preferido_id = serializers.PrimaryKeyRelatedField(
        source='personal_preferido',
        queryset=Personal.objects.filter(activo=True),
        required=False,
        allow_null=True,
    )

    def validate_fecha_preferida(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                'La fecha preferida no puede estar en el pasado.'
            )
        return value

    def validate_servicio_ids(self, value):
        if len({service.pk for service in value}) != len(value):
            raise serializers.ValidationError(
                'No se permiten Servicios repetidos.'
            )
        return value

    def validate(self, attrs):
        if 'cliente_id' in self.initial_data or 'cliente' in self.initial_data:
            raise serializers.ValidationError({
                'cliente_id': 'El Cliente se deriva de la sesión autenticada.'
            })
        return attrs


class SlotHoldCreateCommandSerializer(serializers.Serializer):
    personal_id = serializers.IntegerField(min_value=1)
    starts_at = serializers.DateTimeField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {'personal_id', 'starts_at'}
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class SlotHoldReleaseCommandSerializer(serializers.Serializer):
    def validate(self, attrs):
        if self.initial_data:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(self.initial_data),
            })
        return attrs


class SlotHoldPublicSerializer(serializers.ModelSerializer):
    effective_state = serializers.SerializerMethodField()
    countdown = serializers.SerializerMethodField()
    personal = serializers.SerializerMethodField()
    persisted_state = serializers.CharField(source='state', read_only=True)

    class Meta:
        model = SlotHold
        fields = (
            'public_id',
            'solicitud_id',
            'starts_at',
            'ends_at',
            'expires_at',
            'created_at',
            'persisted_state',
            'effective_state',
            'countdown',
            'personal',
        )
        read_only_fields = fields

    def get_fields(self):
        fields = super().get_fields()
        if not self.context.get('include_resume_metadata', False):
            fields.pop('solicitud_id', None)
            fields.pop('created_at', None)
        return fields

    def _now(self):
        return self.context['database_now']

    def get_effective_state(self, obj):
        if obj.state == SlotHold.State.ACTIVE and obj.expires_at <= self._now():
            return SlotHold.State.EXPIRED
        return obj.state

    def get_countdown(self, obj):
        now = self._now()
        effective_state = self.get_effective_state(obj)
        remaining = (
            max(0, int((obj.expires_at - now).total_seconds()))
            if effective_state == SlotHold.State.ACTIVE
            else 0
        )
        return {
            'server_now': now.isoformat(),
            'seconds_remaining': remaining,
            'authoritative': False,
        }

    @staticmethod
    def get_personal(obj):
        return {
            'id': obj.personal_id,
            'nombre': obj.personal.nombre,
            'apellido': obj.personal.apellido,
        }


class PaymentIntentCreateCommandSerializer(serializers.Serializer):
    slot_hold_public_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=PaymentIntent.Mode.choices)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {'slot_hold_public_id', 'mode'}
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class PaymentIntentOptionsQuerySerializer(serializers.Serializer):
    slot_hold_public_id = serializers.UUIDField()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {'slot_hold_public_id'}
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class PaymentIntentCancelCommandSerializer(serializers.Serializer):
    def validate(self, attrs):
        if self.initial_data:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(self.initial_data),
            })
        return attrs


class ProviderCheckoutCommandSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(
        choices=ProviderPaymentAttempt.Channel.choices,
        default=ProviderPaymentAttempt.Channel.ONLINE,
    )

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {'channel'}
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class ProviderPaymentAttemptPublicSerializer(serializers.ModelSerializer):
    checkout_url = serializers.SerializerMethodField()
    payment_intent_public_id = serializers.UUIDField(
        source='payment_intent.public_id',
        read_only=True,
        allow_null=True,
    )
    order_id = serializers.IntegerField(read_only=True, allow_null=True)
    retryable_with_same_key = serializers.SerializerMethodField()
    financial_authority = serializers.SerializerMethodField()

    class Meta:
        model = ProviderPaymentAttempt
        fields = (
            'public_id',
            'provider',
            'context',
            'channel',
            'status',
            'payment_intent_public_id',
            'order_id',
            'amount',
            'currency',
            'checkout_url',
            'provider_expires_at',
            'error_code',
            'error_detail',
            'retryable_with_same_key',
            'financial_authority',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields

    @staticmethod
    def get_checkout_url(obj):
        if obj.status != ProviderPaymentAttempt.Status.READY:
            return None
        return obj.checkout_url or None

    @staticmethod
    def get_retryable_with_same_key(obj):
        return obj.status == ProviderPaymentAttempt.Status.OUTCOME_UNKNOWN

    @staticmethod
    def get_financial_authority(obj):
        # Crear o visitar el checkout nunca acredita la obligación.
        return False


class PaymentIntentLinePublicSerializer(serializers.ModelSerializer):
    servicio_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PaymentIntentLine
        fields = (
            'servicio_id',
            'orden',
            'nombre_snapshot',
            'cantidad',
            'precio_unitario_snapshot',
            'descuento',
            'subtotal',
            'moneda',
        )
        read_only_fields = fields


class PaymentIntentPublicSerializer(serializers.ModelSerializer):
    lines = PaymentIntentLinePublicSerializer(many=True, read_only=True)
    slot_hold_public_id = serializers.UUIDField(
        source='slot_hold.public_id',
        read_only=True,
    )
    policy_version = serializers.SerializerMethodField()
    effective_status = serializers.SerializerMethodField()
    countdown = serializers.SerializerMethodField()
    paid_reconciled = serializers.SerializerMethodField()
    confirmation_due = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    financial_threshold_reached = serializers.SerializerMethodField()
    confirmed_turno_id = serializers.IntegerField(read_only=True, allow_null=True)
    hold_effective_state = serializers.SerializerMethodField()
    checkout = serializers.SerializerMethodField()
    tracking = serializers.SerializerMethodField()

    class Meta:
        model = PaymentIntent
        fields = (
            'public_id',
            'slot_hold_public_id',
            'policy_version',
            'policy_snapshot',
            'mode',
            'total_amount_snapshot',
            'required_amount',
            'currency',
            'status',
            'effective_status',
            'expires_at',
            'created_at',
            'pending_at',
            'approved_at',
            'terminal_at',
            'terminal_reason',
            'countdown',
            'paid_reconciled',
            'confirmation_due',
            'balance',
            'financial_threshold_reached',
            'confirmed_turno_id',
            'hold_effective_state',
            'checkout',
            'tracking',
            'lines',
        )
        read_only_fields = fields

    def _now(self):
        return self.context['database_now']

    @staticmethod
    def get_policy_version(obj):
        return obj.policy_snapshot.get('version')

    def get_effective_status(self, obj):
        if obj.status in PaymentIntent.ACTIVE_STATUSES:
            now = self._now()
            if (
                obj.expires_at <= now
                or obj.slot_hold.state != SlotHold.State.ACTIVE
                or obj.slot_hold.expires_at <= now
            ):
                return PaymentIntent.Status.EXPIRED
        return obj.status

    def get_countdown(self, obj):
        now = self._now()
        remaining = (
            max(0, int((obj.expires_at - now).total_seconds()))
            if self.get_effective_status(obj) in PaymentIntent.ACTIVE_STATUSES
            else 0
        )
        return {
            'server_now': now.isoformat(),
            'seconds_remaining': remaining,
            'authoritative': False,
        }

    def get_hold_effective_state(self, obj):
        if (
            obj.slot_hold.state == SlotHold.State.ACTIVE
            and obj.slot_hold.expires_at <= self._now()
        ):
            return SlotHold.State.EXPIRED
        return obj.slot_hold.state

    @staticmethod
    def _latest_attempt(obj):
        attempts = list(obj.provider_attempts.all())
        return max(
            attempts,
            key=lambda item: (item.created_at, item.pk),
            default=None,
        )

    @staticmethod
    def _latest_event(attempt):
        if attempt is None:
            return None
        events = list(attempt.provider_events.all())
        return max(
            events,
            key=lambda item: (item.received_at, item.pk),
            default=None,
        )

    def get_checkout(self, obj):
        attempt = self._latest_attempt(obj)
        if attempt is None:
            return None
        return ProviderPaymentAttemptPublicSerializer(
            attempt,
            context=self.context,
        ).data

    def get_tracking(self, obj):
        attempt = self._latest_attempt(obj)
        event = self._latest_event(attempt)
        open_cases = [
            case for case in obj.reconciliation_cases.all()
            if case.status == PaymentReconciliationCase.Status.OPEN
        ]
        has_pending_payment = any(
            payment.status == Pago.Status.PENDING_RECONCILIATION
            for payment in obj.payments.all()
        )
        booking_failure = next(
            (
                case for case in open_cases
                if case.case_type in {
                    PaymentReconciliationCase.Type.LATE_PAYMENT,
                    PaymentReconciliationCase.Type.BOOKING_CONFIRMATION_FAILED,
                }
            ),
            None,
        )
        if booking_failure is not None:
            return {
                'state': 'PAID_WITHOUT_BOOKING',
                'code': booking_failure.reason_code,
                'requires_polling': False,
            }
        if (
            open_cases
            or has_pending_payment
            or event is not None
            and event.reconciliation_status
            == ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED
        ):
            state = 'ADMIN_REVIEW'
            code = (
                event.reconciliation_code
                if event is not None and event.reconciliation_code
                else 'PAYMENT_RECONCILIATION_REQUIRED'
            )
            return {'state': state, 'code': code, 'requires_polling': False}

        if obj.status == PaymentIntent.Status.APPROVED and obj.confirmed_turno_id:
            return {
                'state': 'CONFIRMED',
                'code': 'BOOKING_CONFIRMED',
                'requires_polling': False,
            }
        if obj.status == PaymentIntent.Status.REJECTED:
            return {
                'state': 'PAYMENT_REJECTED',
                'code': obj.terminal_reason or 'PAYMENT_REJECTED',
                'requires_polling': False,
            }
        if obj.status == PaymentIntent.Status.CANCELLED:
            return {
                'state': 'CANCELLED',
                'code': obj.terminal_reason or 'PAYMENT_INTENT_CANCELLED',
                'requires_polling': False,
            }
        if self.get_effective_status(obj) == PaymentIntent.Status.EXPIRED:
            return {
                'state': 'HOLD_EXPIRED',
                'code': obj.terminal_reason or 'HOLD_EXPIRED',
                'requires_polling': False,
            }

        if event is not None:
            provider_status = str(
                (event.provider_snapshot or {}).get('status') or ''
            ).lower()
            if (
                event.reconciliation_status
                == ProviderEvent.ReconciliationStatus.IGNORED
                and provider_status
                in {'failed', 'rejected', 'canceled', 'cancelled'}
            ):
                return {
                    'state': 'PAYMENT_REJECTED',
                    'code': event.reconciliation_code or 'PAYMENT_NOT_ACCREDITED',
                    'requires_polling': False,
                }
            if (
                event.reconciliation_status
                == ProviderEvent.ReconciliationStatus.IGNORED
                and provider_status in {'created', 'processing', 'pending'}
            ):
                return {
                    'state': 'PAYMENT_PENDING',
                    'code': 'PAYMENT_PENDING',
                    'requires_polling': True,
                }
            if (
                event.reconciliation_status
                == ProviderEvent.ReconciliationStatus.APPLIED
                or obj.status == PaymentIntent.Status.PENDING
            ):
                return {
                    'state': 'PAYMENT_PENDING',
                    'code': event.reconciliation_code or 'PAYMENT_PENDING',
                    'requires_polling': True,
                }

        if attempt is not None:
            if attempt.status == ProviderPaymentAttempt.Status.OUTCOME_UNKNOWN:
                return {
                    'state': 'CHECKOUT_UNCERTAIN',
                    'code': attempt.error_code or 'PROVIDER_OUTCOME_UNKNOWN',
                    'requires_polling': True,
                }
            if attempt.status == ProviderPaymentAttempt.Status.FAILED:
                return {
                    'state': 'CHECKOUT_ERROR',
                    'code': attempt.error_code or 'PROVIDER_CHECKOUT_FAILED',
                    'requires_polling': False,
                }
            if attempt.status in {
                ProviderPaymentAttempt.Status.PROCESSING,
                ProviderPaymentAttempt.Status.READY,
            }:
                return {
                    'state': 'PAYMENT_VERIFICATION',
                    'code': 'AWAITING_PROVIDER_VERIFICATION',
                    'requires_polling': True,
                }
        return {
            'state': 'READY_FOR_CHECKOUT',
            'code': 'PAYMENT_INTENT_READY',
            'requires_polling': False,
        }

    @staticmethod
    def _financial(obj):
        if not hasattr(obj, '_payment_financial_snapshot'):
            from .manual_payment_services import financial_snapshot

            obj._payment_financial_snapshot = financial_snapshot(obj)
        return obj._payment_financial_snapshot

    def get_paid_reconciled(self, obj):
        return self._financial(obj).paid_reconciled

    def get_confirmation_due(self, obj):
        return self._financial(obj).confirmation_due

    def get_balance(self, obj):
        return self._financial(obj).balance

    def get_financial_threshold_reached(self, obj):
        return self._financial(obj).financial_threshold_reached


class TechnicalBookingRequestReevaluateSerializer(serializers.Serializer):
    servicio_ids = serializers.PrimaryKeyRelatedField(
        source='servicios',
        queryset=Servicio.objects.filter(activo=True),
        many=True,
        allow_empty=False,
        required=False,
    )
    fecha_preferida = serializers.DateField(required=False)
    hora_preferida = serializers.TimeField(required=False)
    personal_preferido_id = serializers.PrimaryKeyRelatedField(
        source='personal_preferido',
        queryset=Personal.objects.filter(activo=True),
        required=False,
        allow_null=True,
    )
    informacion_tecnica_actualizada = serializers.BooleanField(
        required=False,
        default=False,
    )

    def validate_fecha_preferida(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                'La fecha preferida no puede estar en el pasado.'
            )
        return value

    def validate_servicio_ids(self, value):
        if len({service.pk for service in value}) != len(value):
            raise serializers.ValidationError(
                'No se permiten Servicios repetidos.'
            )
        return value

    def validate(self, attrs):
        changed_fields = {
            'servicios',
            'fecha_preferida',
            'hora_preferida',
            'personal_preferido',
        }
        if (
            not any(key in attrs for key in changed_fields)
            and not attrs.get('informacion_tecnica_actualizada', False)
        ):
            raise serializers.ValidationError(
                'Debe informar un cambio que requiera reevaluación.'
            )
        return attrs


class TechnicalBookingReviewCommandSerializer(serializers.Serializer):
    accion = serializers.ChoiceField(
        choices=DecisionRevisionTecnica.Accion.choices
    )
    motivo = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )
    mensaje_cliente = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )
    datos_faltantes = serializers.ListField(
        child=serializers.ChoiceField(choices=(
            'DIAGNOSTICO_ACTUALIZADO',
            'INFORMACION_ADICIONAL',
        )),
        required=False,
        allow_empty=True,
    )
    fecha_recomendada = serializers.DateField(required=False)


class TechnicalBookingRequestPublicSerializer(serializers.ModelSerializer):
    outcome_publico = serializers.SerializerMethodField()
    servicios = serializers.SerializerMethodField()
    personal_preferido = serializers.SerializerMethodField()
    advertencias = serializers.SerializerMethodField()
    fecha_minima = serializers.SerializerMethodField()
    faltantes = serializers.SerializerMethodField()
    alternativas = serializers.SerializerMethodField()
    sla = serializers.SerializerMethodField()
    mensaje_cliente = serializers.SerializerMethodField()
    aviso_reserva = serializers.SerializerMethodField()

    class Meta:
        model = SolicitudTecnicaReserva
        fields = (
            'id',
            'estado',
            'outcome_publico',
            'servicios',
            'fecha_preferida',
            'hora_preferida',
            'personal_preferido',
            'intento',
            'advertencias',
            'fecha_minima',
            'faltantes',
            'alternativas',
            'sla',
            'mensaje_cliente',
            'aviso_reserva',
            'created_at',
            'updated_at',
        )

    @staticmethod
    def _result(obj):
        evaluation = obj.evaluacion_vigente
        return evaluation.result_snapshot if evaluation else {}

    def get_outcome_publico(self, obj):
        evaluation = obj.evaluacion_vigente
        return evaluation.outcome if evaluation else None

    def get_servicios(self, obj):
        return [
            {
                'id': item.servicio_id,
                'nombre': item.nombre_snapshot,
            }
            for item in obj.servicios_solicitados.all()
        ]

    def get_personal_preferido(self, obj):
        if obj.personal_preferido is None:
            return None
        return {
            'id': obj.personal_preferido_id,
            'nombre': obj.personal_preferido.nombre,
            'apellido': obj.personal_preferido.apellido,
        }

    def get_advertencias(self, obj):
        if obj.estado != SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE:
            return []
        return self._result(obj).get('mensajes_cliente', [])

    def get_fecha_minima(self, obj):
        return self._result(obj).get('fecha_minima_recomendada')

    def get_faltantes(self, obj):
        decision = obj.decisiones_revision.filter(
            accion=DecisionRevisionTecnica.Accion.SOLICITAR_INFORMACION,
            evaluacion=obj.evaluacion_vigente,
        ).first()
        if decision and obj.estado == SolicitudTecnicaReserva.Estado.INFORMACION_REQUERIDA:
            return decision.datos_faltantes
        evaluation = obj.evaluacion_vigente
        if evaluation is None:
            return []
        # El DTO público conserva sólo el code seguro, nunca IDs ni evidencia
        # histórica interna asociada al faltante.
        return [
            {'code': item.get('code')}
            for item in evaluation.input_snapshot.get('datos_faltantes', [])
            if isinstance(item, dict) and item.get('code')
        ]

    def get_alternativas(self, obj):
        if not obj.fecha_recomendada:
            return []
        return [{'fecha': obj.fecha_recomendada.isoformat()}]

    def get_sla(self, obj):
        # No existe una política de SLA configurable en este incremento.
        return None

    def get_mensaje_cliente(self, obj):
        decision = obj.decisiones_revision.filter(
            evaluacion=obj.evaluacion_vigente,
        ).exclude(mensaje_cliente='').first()
        if decision is not None:
            return decision.mensaje_cliente
        messages = self._result(obj).get('mensajes_cliente', [])
        return messages[0] if messages else ''

    def get_aviso_reserva(self, obj):
        return 'Esta solicitud técnica aún no reserva un Turno.'


class StockMovementSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = MovimientoStock
        fields = [
            'id', 'producto', 'delta', 'tipo', 'reason_code', 'nota',
            'actor_kind', 'actor', 'actor_email', 'created_at',
            'reference_type', 'reference_id', 'idempotency_key',
            'stock_before', 'stock_after', 'reverses_movement',
        ]
        read_only_fields = fields


class StockCommandSerializer(StrictInputFieldsMixin, serializers.Serializer):
    reason_code = serializers.CharField(
        min_length=1,
        max_length=50,
        allow_blank=False,
        trim_whitespace=True,
    )
    idempotency_key = serializers.CharField(
        min_length=1,
        max_length=128,
        allow_blank=False,
        trim_whitespace=True,
    )
    note = serializers.CharField(
        max_length=500,
        allow_blank=True,
        required=False,
        default='',
        trim_whitespace=True,
    )


class StockReceiveCommandSerializer(StockCommandSerializer):
    quantity = serializers.IntegerField(min_value=1)


class StockAdjustCommandSerializer(StockCommandSerializer):
    delta = serializers.IntegerField()

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError('El delta debe ser distinto de cero.')
        return value


class StockCorrectionCommandSerializer(StockCommandSerializer):
    pass


class TechnicalBookingRequestReviewSerializer(serializers.ModelSerializer):
    cliente = serializers.SerializerMethodField()
    servicios = serializers.SerializerMethodField()
    outcome = serializers.SerializerMethodField()
    rule_codes = serializers.SerializerMethodField()
    datos_faltantes = serializers.SerializerMethodField()
    diagnostico = serializers.SerializerMethodField()
    antecedentes = serializers.SerializerMethodField()
    intervalos = serializers.SerializerMethodField()
    fecha_minima = serializers.SerializerMethodField()
    mensajes_profesionales = serializers.SerializerMethodField()
    aviso_reserva = serializers.SerializerMethodField()

    class Meta:
        model = SolicitudTecnicaReserva
        fields = (
            'id',
            'estado',
            'cliente',
            'servicios',
            'fecha_preferida',
            'hora_preferida',
            'outcome',
            'rule_codes',
            'datos_faltantes',
            'diagnostico',
            'antecedentes',
            'intervalos',
            'fecha_minima',
            'fecha_recomendada',
            'mensajes_profesionales',
            'aviso_reserva',
            'created_at',
        )

    @staticmethod
    def _snapshots(obj):
        evaluation = obj.evaluacion_vigente
        if evaluation is None:
            return {}, {}
        return evaluation.input_snapshot, evaluation.result_snapshot

    def get_cliente(self, obj):
        user = obj.cliente.usuario
        return {
            'id': obj.cliente_id,
            'nombre': user.get_full_name(),
            'email': user.email,
        }

    def get_servicios(self, obj):
        return [
            {'id': item.servicio_id, 'nombre': item.nombre_snapshot}
            for item in obj.servicios_solicitados.all()
        ]

    def get_outcome(self, obj):
        return obj.evaluacion_vigente.outcome if obj.evaluacion_vigente else None

    def get_rule_codes(self, obj):
        _, result = self._snapshots(obj)
        return result.get('rule_codes', [])

    def get_datos_faltantes(self, obj):
        input_snapshot, _ = self._snapshots(obj)
        allowed_fields = {
            'code', 'service_id', 'turno_id', 'fecha', 'hora', 'estado',
            'detalle_count',
        }
        return [
            {
                key: value for key, value in item.items()
                if key in allowed_fields
            }
            for item in input_snapshot.get('datos_faltantes', [])
            if isinstance(item, dict) and item.get('code')
        ]

    def get_diagnostico(self, obj):
        input_snapshot, _ = self._snapshots(obj)
        diagnosis = input_snapshot.get('diagnostico_usado')
        if not isinstance(diagnosis, dict):
            return None
        date_value = diagnosis.get('fecha')
        age = None
        if date_value:
            try:
                diagnosis_date = datetime.fromisoformat(date_value).date()
                age = (obj.fecha_preferida - diagnosis_date).days
            except (TypeError, ValueError):
                age = None
        return {
            'id': diagnosis.get('id'),
            'fecha': date_value,
            'antiguedad_dias': age,
            'procedencia': diagnosis.get('procedencia'),
            'completo': bool(diagnosis.get('completo')),
        }

    def get_antecedentes(self, obj):
        input_snapshot, _ = self._snapshots(obj)
        history = [
            item for item in input_snapshot.get('historial_considerado', [])
            if isinstance(item, dict)
        ]
        service_ids = {
            item.get('servicio_id') for item in history
            if item.get('servicio_id') is not None
        }
        service_names = dict(
            Servicio.objects.filter(pk__in=service_ids).values_list('pk', 'nombre')
        )
        allowed_fields = {
            'turno_id', 'detalle_id', 'servicio_id', 'fecha', 'hora',
            'familia_code', 'estado_clasificacion', 'code', 'estado',
            'detalle_count',
        }
        return [
            {
                **{
                    key: value for key, value in item.items()
                    if key in allowed_fields
                },
                **(
                    {'servicio_nombre': service_names.get(item['servicio_id'])}
                    if item.get('servicio_id') is not None
                    else {}
                ),
            }
            for item in history
        ]

    def get_intervalos(self, obj):
        _, result = self._snapshots(obj)
        intervals = []
        service_ids = set()
        for trigger in result.get('reglas_disparadas', []):
            if not isinstance(trigger, dict) or trigger.get('kind') not in {
                'INTERVAL', 'REQUESTED_SERVICE_INTERACTION',
            }:
                continue
            parameters = trigger.get('parameters') or {}
            evidence = trigger.get('evidence') or {}
            origin_id = (
                evidence.get('servicio_previo_id')
                or evidence.get('servicio_origen_solicitado_id')
                or parameters.get('servicio_origen_id')
            )
            target_id = (
                evidence.get('servicio_solicitado_id')
                or evidence.get('servicio_destino_solicitado_id')
                or parameters.get('servicio_destino_id')
            )
            service_ids.update(value for value in (origin_id, target_id) if value)
            intervals.append({
                'code': trigger.get('code'),
                'tipo': trigger.get('kind'),
                'servicio_origen_id': origin_id,
                'servicio_destino_id': target_id,
                'dias_minimos': parameters.get('dias_minimos'),
                'dias_transcurridos': evidence.get('dias_transcurridos'),
                'dias_entre_servicios': evidence.get('dias_entre_servicios'),
                'fecha_servicio_previo': evidence.get('fecha_servicio_previo'),
                'fecha_minima_recomendada': evidence.get(
                    'fecha_minima_recomendada'
                ),
            })
        service_names = dict(
            Servicio.objects.filter(pk__in=service_ids).values_list('pk', 'nombre')
        )
        for interval in intervals:
            interval['servicio_origen_nombre'] = service_names.get(
                interval['servicio_origen_id']
            )
            interval['servicio_destino_nombre'] = service_names.get(
                interval['servicio_destino_id']
            )
        return intervals

    def get_fecha_minima(self, obj):
        _, result = self._snapshots(obj)
        return result.get('fecha_minima_recomendada')

    def get_mensajes_profesionales(self, obj):
        _, result = self._snapshots(obj)
        return result.get('mensajes_profesional', [])

    def get_aviso_reserva(self, obj):
        return 'Esta solicitud técnica aún no reserva un Turno.'


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
            'slot_hold_ttl_minutes',
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
        read_only_fields = [
            'id',
            'cliente',
            'estado',
            'items_json',
            'monto_total',
            'fecha_creacion',
            'fecha_confirmacion',
            'fecha_completacion',
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


class ManualPaymentRegisterCommandSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.ChoiceField(choices=PAYMENT_CURRENCY_CHOICES)
    method = serializers.ChoiceField(choices=Pago.Method.choices)
    purpose = serializers.ChoiceField(choices=Pago.Purpose.choices)
    occurred_at = serializers.DateTimeField()
    manual_reference = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=80,
        default='',
    )
    receipt = serializers.FileField(
        required=False,
        allow_null=True,
        default=None,
    )
    late_evidence = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        allowed = {
            'amount',
            'currency',
            'method',
            'purpose',
            'occurred_at',
            'manual_reference',
            'receipt',
            'late_evidence',
        }
        unexpected = set(self.initial_data) - allowed
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class ManualPaymentReconcileCommandSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=('ACCEPT', 'REJECT'))
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100,
        default='',
    )

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {'decision', 'reason'}
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        return attrs


class LegacyOrderPaymentCommandSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = serializers.ChoiceField(
        choices=('EFECTIVO', 'TRANSFERENCIA', 'MERCADO_PAGO')
    )
    fecha_pago = serializers.DateTimeField(required=False, default=timezone.now)
    comprobante_foto = serializers.FileField(required=False, allow_null=True)
    es_sena = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {
            'monto',
            'metodo_pago',
            'fecha_pago',
            'comprobante_foto',
            'es_sena',
        }
        if unexpected:
            raise serializers.ValidationError({
                'campos_no_permitidos': sorted(unexpected),
            })
        if (
            attrs['metodo_pago'] == 'TRANSFERENCIA'
            and not attrs.get('comprobante_foto')
        ):
            raise serializers.ValidationError({
                'comprobante_foto': (
                    'Se requiere comprobante para pagos por transferencia.'
                ),
            })
        return attrs


class PagoSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(
        source='monto',
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    method = serializers.CharField(source='metodo_pago', read_only=True)
    occurred_at = serializers.DateTimeField(source='fecha_pago', read_only=True)
    payment_intent_public_id = serializers.UUIDField(
        source='payment_intent.public_id',
        read_only=True,
        allow_null=True,
    )
    recorded_by = serializers.EmailField(
        source='recorded_by.email',
        read_only=True,
        allow_null=True,
    )
    reconciled_by = serializers.EmailField(
        source='reconciled_by.email',
        read_only=True,
        allow_null=True,
    )
    orden_codigo = serializers.ReadOnlyField(source='orden.codigo')
    turno_fecha = serializers.SerializerMethodField()
    cliente_nombre = serializers.SerializerMethodField()
    cliente_email = serializers.SerializerMethodField()
    tipo_origen = serializers.SerializerMethodField()
    receipt_download = serializers.SerializerMethodField()
    comprobante_foto = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = [
            'id',
            'public_id',
            'payment_intent_public_id',
            'orden',
            'turno',
            'amount',
            'currency',
            'method',
            'purpose',
            'status',
            'occurred_at',
            'recorded_at',
            'recorded_by',
            'reconciled_at',
            'reconciled_by',
            'manual_reference',
            'terminal_reason',
            'receipt_download',
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
        read_only_fields = fields

    def get_turno_fecha(self, obj):
        if obj.turno:
            return obj.turno.fecha
        return None

    def get_cliente_nombre(self, obj):
        if obj.orden and obj.orden.cliente and obj.orden.cliente.usuario:
            return obj.orden.cliente.usuario.get_full_name()
        if obj.turno and obj.turno.cliente and obj.turno.cliente.usuario:
            return obj.turno.cliente.usuario.get_full_name()
        if obj.payment_intent_id:
            return obj.payment_intent.cliente.usuario.get_full_name()
        return None

    def get_cliente_email(self, obj):
        if obj.orden and obj.orden.cliente and obj.orden.cliente.usuario:
            return obj.orden.cliente.usuario.email
        if obj.turno and obj.turno.cliente and obj.turno.cliente.usuario:
            return obj.turno.cliente.usuario.email
        if obj.payment_intent_id:
            return obj.payment_intent.cliente.usuario.email
        return None

    def get_tipo_origen(self, obj):
        if obj.orden_id:
            return 'ORDEN'
        if obj.payment_intent_id:
            return 'PAYMENT_INTENT'
        if obj.turno_id:
            return 'TURNO'
        return None

    @staticmethod
    def get_receipt_download(obj):
        if not obj.comprobante_foto:
            return None
        return f'/api/gestion/payments/{obj.public_id}/receipt/'

    def get_comprobante_foto(self, obj):
        return self.get_receipt_download(obj)


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
        read_only_fields = [
            'id',
            'codigo',
            'cliente',
            'estado',
            'total',
            'creado_at',
            'actualizado_at',
        ]
    
    def get_total_items(self, obj):
        return sum(item.cantidad for item in obj.items.all())





