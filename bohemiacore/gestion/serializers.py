from rest_framework import serializers
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo,
    EstadoGeneral, Equipamiento, Producto, ReglaDiagnostico,
    Notificacion, Rutina, AgendaCuidados, RutinaCliente, Servicio,
    CategoriaServicio, Turno, DetalleTurno, HorarioLaboral, BloqueoAgenda, Personal,
    TipoEquipamiento, FichaTecnica, DiagnosticoCapilar, RequisitoServicio,
    #PasoRutina, #PasoRutinaCliente,
)

from .services import DisponibilidadService
from usuarios.models import Usuario, Cliente
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
    
    class Meta:
        model = DetalleTurno
        fields = ['id', 'servicio', 'servicio_nombre', 'precio_historico', 'duracion_minutos']
        read_only_fields = ['id', 'servicio_nombre']


class TurnoSerializer(serializers.ModelSerializer):
    # Nested serializer para los detalles/servicios del turno
    detalles = DetalleTurnoSerializer(many=True, required=False, allow_null=True)
    # Campo para servicio simple (cuando el frontend envía servicio_id)
    servicio = serializers.IntegerField(write_only=True, required=False)
    # Campos de lectura con nombres amigables
    cliente_nombre = serializers.SerializerMethodField(read_only=True)
    servicio_nombre = serializers.SerializerMethodField(read_only=True)
    profesional_nombre = serializers.SerializerMethodField(read_only=True)
    # ✅ NUEVO: Campos para verificar expiración
    expired = serializers.SerializerMethodField(read_only=True)
    horas_transcurridas = serializers.SerializerMethodField(read_only=True)
    puede_modificar = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Turno
        fields = [
            'id', 'cliente', 'cliente_nombre', 'profesional', 'profesional_nombre', 
            'equipamiento', 'fecha', 'hora_inicio', 'estado', 'detalles', 'servicio', 
            'servicio_nombre', 'comprobante_pago', 'expired', 'horas_transcurridas', 'puede_modificar'
        ]
        read_only_fields = ['cliente', 'expired', 'horas_transcurridas', 'puede_modificar']
    
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

    def validate(self, data):
        """Validar según el tipo de operación"""
        request = self.context.get('request')
        
        # En POST (crear nuevo turno), validar no duplicado
        if request and request.method == 'POST' and request.user:
            try:
                cliente = request.user.cliente
                # Verificar si ya existe un turno con la misma fecha, hora y cliente
                existe = Turno.objects.filter(
                    cliente=cliente,
                    fecha=data.get('fecha'),
                    hora_inicio=data.get('hora_inicio')
                ).exists()
                
                if existe:
                    raise serializers.ValidationError(
                        "Ya tienes un turno solicitado para esa fecha y hora. "
                        "Por favor, elige otro horario."
                    )
            except Exception as e:
                if "Ya tienes un turno" in str(e):
                    raise
                pass
        
        return data

    def create(self, validated_data):
        from .models import Servicio, DetalleTurno
        from django.contrib.auth.models import User
        
        # Obtener el cliente del usuario autenticado
        request = self.context.get('request')
        if request and request.user:
            try:
                cliente = request.user.cliente
                validated_data['cliente'] = cliente
            except:
                raise serializers.ValidationError("El usuario no tiene perfil de cliente.")
        else:
            raise serializers.ValidationError("Usuario no autenticado.")
        
        # Sacar servicio_id si vino (compatibilidad con frontend simple)
        servicio_id = validated_data.pop('servicio', None)
        
        # Sacar detalles si vinieron
        detalles_data = validated_data.pop('detalles', [])
        
        # Si no hay detalles pero sí hay servicio_id, crear detalle automáticamente
        if not detalles_data and servicio_id:
            try:
                servicio = Servicio.objects.get(id=servicio_id)
                detalles_data = [{
                    'servicio': servicio,
                    'precio_historico': servicio.precio_base or 0,
                    'duracion_minutos': servicio.duracion_estimada or 60
                }]
            except Servicio.DoesNotExist:
                raise serializers.ValidationError(f"Servicio {servicio_id} no existe.")
        
        # Crear el Turno principal
        turno = Turno.objects.create(**validated_data)
        
        # Crear cada detalle en la tabla intermedia
        for detalle_data in detalles_data:
            if isinstance(detalle_data.get('servicio'), dict):
                # Si viene serializado, extraer el ID
                servicio_id = detalle_data['servicio'].get('id')
                detalle_data['servicio'] = Servicio.objects.get(id=servicio_id)
            
            DetalleTurno.objects.create(turno=turno, **detalle_data)
        
        return turno
    
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
    profesional_nombre = serializers.CharField(source='profesional_autor.get_full_name', read_only=True)
    
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
            'profesional_autor', 'profesional_nombre', 'formula_base_servicio',
            'formula', 'observaciones_proceso', 
            'porosidad_final', 'porosidad_final_nombre',
            'estado_general_final', 'estado_general_final_nombre',
            'resultado_post_servicio', 'foto_resultado', 'fecha_registro'
        ]
        read_only_fields = [
            'id', 'fecha_registro', 'detalle_turno_id', 'servicio_nombre', 
            'profesional_nombre', 'formula_base_servicio',
            'porosidad_final_nombre', 'estado_general_final_nombre'
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
            
            # 2. Actualizar estado del Turno a 'realizado' automáticamente
            turno = ficha.detalle_turno.turno
            turno.estado = 'realizado'
            turno.save()
            
            # 3. (Opcional) Aquí podrías disparar la actualización del Diagnóstico Capilar
            
            return ficha

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
    regla_diagnostico_accion = serializers.CharField(source='regla_diagnostico.accion_resultado', read_only=True)
    rutina_sugerida_nombre = serializers.CharField(source='rutina_sugerida.nombre', read_only=True)
    rutina_asignada_nombre = serializers.CharField(source='rutina_asignada.nombre', read_only=True, required=False)
    servicio_urgente_nombre = serializers.CharField(source='servicio_urgente.nombre', read_only=True, required=False)
    servicio_urgente_id = serializers.IntegerField(source='servicio_urgente.id', read_only=True, required=False)
    rutina_asignada_id = serializers.IntegerField(source='rutina_asignada.id', read_only=True, required=False)
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
            'regla_diagnostico', 'regla_diagnostico_accion',
            'rutina_sugerida', 'rutina_sugerida_nombre',
            'rutina_asignada', 'rutina_asignada_nombre', 'rutina_asignada_id',
            'servicio_urgente', 'servicio_urgente_nombre', 'servicio_urgente_id',
            'fecha_diagnostico'
        ]
        read_only_fields = [
            'id', 'fecha_diagnostico', 'cliente_email', 'profesional_nombre',
            'tipo_cabello_nombre', 'grosor_cabello_nombre', 'porosidad_cabello_nombre',
            'cuero_cabelludo_nombre', 'estado_general_nombre', 'regla_diagnostico_accion',
            'rutina_sugerida_nombre', 'mensaje_diagnostico', 'rutina_asignada_nombre',
            'servicio_urgente_nombre', 'servicio_urgente_id', 'rutina_asignada_id'
        ]
    
    def create(self, validated_data):
        """Auto-asigna el profesional actual al crear el diagnóstico"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Intenta obtener el Usuario del request
            try:
                usuario = Usuario.objects.get(email=request.user.email)
                validated_data['profesional'] = usuario
            except Usuario.DoesNotExist:
                pass
        return super().create(validated_data)