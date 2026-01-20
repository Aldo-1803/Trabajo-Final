from django.db import models
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError


# ============================================================
# SECCIÓN 1: USUARIOS Y PERSONAL
# ============================================================

class DiasSemana(models.IntegerChoices):
    """
    ENUM para días de la semana. Más eficiente y seguro.
    """
    LUNES = 0, 'Lunes'
    MARTES = 1, 'Martes'
    MIERCOLES = 2, 'Miércoles'
    JUEVES = 3, 'Jueves'
    VIERNES = 4, 'Viernes'
    SABADO = 5, 'Sábado'
    DOMINGO = 6, 'Domingo'


class Personal(models.Model):
    """
    Modelo para gestionar el personal / staff de la peluquería.
    Puede estar vinculado a un usuario del sistema o ser solo un registro administrativo.
    """
    ROL_CHOICES = [
        ('colorista', 'Colorista / Principal'),  # Yanina
        ('asistente', 'Asistente / Lavado'),     # Empleadas
        ('administrador', 'Administrador'),
    ]

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        related_name='perfil_profesional',
        help_text="Vincular solo si esta persona necesita loguearse al sistema"
    )
    
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    rol = models.CharField(max_length=20, choices=ROL_CHOICES)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Skills (Para saber a quién asignar tareas automáticas)
    realiza_diagnostico = models.BooleanField(default=False)
    realiza_lavado = models.BooleanField(default=True)
    realiza_color = models.BooleanField(default=False)
    
    activo = models.BooleanField(default=True)
    color_calendario = models.CharField(max_length=7, default="#E11D48", help_text="Color Hex para identificarlo en la agenda")

    class Meta:
        verbose_name = "Personal / Staff"
        verbose_name_plural = "Personal"

    def __str__(self):
        return f"{self.nombre} ({self.get_rol_display()})"


# ============================================================
# SECCIÓN 2: SERVICIOS Y PRODUCTOS
# ============================================================

class CategoriaServicio(models.Model):
    """
    Clasifica los servicios de Bohemia (ej. 'Químicos', 'Corte', 'Peinado', 'Diagnóstico').
    """
    nombre = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Nombre único del categoría."
    )
    descripcion = models.TextField(
        blank=True, 
        null=True,
        help_text="Descripción de la categoría"
    )
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Categoría de Servicio"
        verbose_name_plural = "Categorías de Servicios"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Servicio(models.Model):
    """
    El modelo principal para los servicios de Bohemia Hair.
    Define nombre, duración, precio, impacto en el cabello, etc.
    """
    
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    
    # 1. CATEGORIA
    categoria = models.ForeignKey(
        CategoriaServicio,
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        verbose_name="Categoría"
    )
    
    # 2. DURACION
    duracion_estimada = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Duración Estimada (en minutos)"
    )
    
    # 3. PRECIO
    precio_base = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0.00,
        verbose_name="Precio Base"
    )
    
    # 3.5 PLANTILLA DE FORMULA
    plantilla_formula = models.TextField(
        blank=True, 
        help_text="Estructura base: Base: __, Medios: __, Oxidante: __"
    )
    
    # 4. SIMULTANEIDAD
    permite_simultaneidad = models.BooleanField(
        default=False, 
        help_text="Si es True, Yani puede atender a otra persona durante el reposo."
    )
    
    # 5. RUTINA RECOMENDADA
    rutina_recomendada = models.ForeignKey(
        'Rutina', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Rutina que se asignará automáticamente al finalizar este servicio."
    )

    # 6. IMPACTO EN EL CABELLO
    impacto_porosidad = models.ForeignKey(
        'PorosidadCabello', 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        help_text="Nivel de porosidad que tendrá el cabello después del servicio."
    )
    
    impacto_estado = models.ForeignKey(
        'EstadoGeneral', 
        on_delete=models.SET_NULL, 
        null=True, blank=True,
        help_text="Estado general en el que quedará el cabello (ej: Seco, Dañado)."
    )

    activo = models.BooleanField(default=True)
    puntaje_base = models.IntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = ['nombre']

    def __str__(self):
        if self.categoria:
            return f"[{self.categoria.nombre}] {self.nombre}"
        return self.nombre


class Producto(models.Model):
    """
    Productos que se venden en la peluquería.
    """
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} (${self.precio})"


# ============================================================
# SECCIÓN 3: DIAGNÓSTICO Y RUTINAS
# ============================================================

class CatalogoBase(models.Model):
    """
    Modelo base abstracto para todos los catálogos de diagnóstico.
    """
    nombre = models.CharField(
        max_length=100, 
        unique=True,
        help_text="Nombre único del atributo."
    )
    descripcion = models.TextField(
        blank=True, 
        null=True,
        help_text="Descripción o notas internas sobre esta opción."
    )
    activo = models.BooleanField(
        default=True,
        help_text="Marcar si esta opción está disponible para nuevos registros."
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    puntaje_base = models.IntegerField(
        default=0, 
        verbose_name="Puntaje PH (Lógica Diagnóstico)",
        help_text="Usado por el motor de reglas (ej. Sano=10, Dañado=50)"
    )

    class Meta:
        abstract = True
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class CueroCabelludo(CatalogoBase):
    class Meta(CatalogoBase.Meta):
        verbose_name_plural = "Cueros Cabelludos"


class EstadoGeneral(CatalogoBase): 
    class Meta(CatalogoBase.Meta):
        verbose_name_plural = "Estados Generales"


class GrosorCabello(CatalogoBase):
    class Meta(CatalogoBase.Meta):
        verbose_name_plural = "Grosores de Cabello"


class PorosidadCabello(CatalogoBase):
    class Meta(CatalogoBase.Meta):
        verbose_name_plural = "Porosidades de Cabello"


class TipoCabello(CatalogoBase):
    class Meta(CatalogoBase.Meta):
        verbose_name_plural = "Tipos de Cabello"


class ReglaDiagnostico(models.Model):
    """
    Define una regla experta para el motor de diagnóstico (Nivel 1).
    """
    # --- 1. CONDICIONES (LOS 5 INPUTS) ---
    tipo_cabello = models.ForeignKey(
        TipoCabello, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Dejar vacío para 'Cualquier tipo'"
    )
    grosor_cabello = models.ForeignKey(
        GrosorCabello, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Dejar vacío para 'Cualquier grosor'"
    )
    porosidad_cabello = models.ForeignKey(
        PorosidadCabello, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Dejar vacío para 'Cualquier porosidad'"
    )
    cuero_cabelludo = models.ForeignKey(
        CueroCabelludo, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Dejar vacío para 'Cualquier cuero cabelludo'"
    )
    
    estado_general = models.ForeignKey(
        EstadoGeneral, on_delete=models.CASCADE, null=True, blank=True,
        help_text="Dejar vacío para 'Cualquier estado'"
    )

    # --- 2. RESULTADO ---
    prioridad = models.IntegerField(
        default=0, 
        help_text="Reglas con número más alto se evalúan primero"
    )
    mensaje_resultado = models.TextField(
        help_text="El mensaje que verá el cliente si esta regla coincide"
    )
    accion_resultado = models.CharField(
        max_length=50,
        help_text="Código de acción que el frontend usará para decidir qué mostrar"
    )

    rutina_sugerida = models.ForeignKey(
        'Rutina',
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="La rutina que se asignará automáticamente al cliente."
    )

    class Meta:
        ordering = ['-prioridad']

    def __str__(self):
        return f"Regla (P:{self.prioridad}) -> {self.accion_resultado}"


class Rutina(models.Model):
    """
    Define una rutina de cuidado personalizada para los clientes.
    """
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('publicada', 'Publicada'),
        ('obsoleta', 'Obsoleta'),
    ]

    nombre = models.CharField(max_length=150)
    objetivo = models.CharField(max_length=255, help_text="Ej: Hidratación profunda")
    
    archivo = models.FileField(
        upload_to='rutinas_pdfs/', 
        verbose_name="Documento de Rutina (PDF/Img)",
        help_text="Sube el diseño exportado de Canva o Word."
    )
    
    descripcion = models.TextField(blank=True, null=True, verbose_name="Notas internas")
    
    version = models.PositiveIntegerField(default=1)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT,
        related_name='rutinas_creadas'
    )

    clientes_asignados = models.ManyToManyField(
        'usuarios.Cliente',
        related_name='rutinas_asignadas',
        blank=True
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_obsoleta = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Rutina"
        verbose_name_plural = "Rutinas"
        ordering = ['-fecha_creacion']

    def actualizar_version(self):
        self.version += 1
        self.save()

    def publicar(self):
        self.estado = 'publicada'
        self.save()

    def obsoletar(self):
        from django.utils import timezone
        self.estado = 'obsoleta'
        self.fecha_obsoleta = timezone.now()
        self.save()

    def asignar_a_cliente(self, cliente):
        """Crea una copia de esta rutina para el cliente."""
        if self.estado != 'publicada':
            raise ValueError(f"La rutina no está publicada.")

        rutina_cliente = RutinaCliente.objects.create(
            cliente=cliente,
            rutina_original=self,
            nombre=self.nombre,
            objetivo=self.objetivo,
            archivo=self.archivo,
            version_asignada=self.version,
            estado='activa'
        )
        return rutina_cliente

    def __str__(self):
        return f"{self.nombre} (v{self.version})"


class RutinaCliente(models.Model):
    """
    Copia personalizada de una rutina asignada a un cliente.
    Mantiene el histórico de versiones.
    """
    ESTADO_CHOICES = [
        ('activa', 'Activa'),
        ('desactualizada', 'Desactualizada'),
        ('obsoleta_original', 'Original Obsoleta'),
        ('archivada', 'Archivada'),
    ]

    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.CASCADE,
        related_name='rutinas_cliente'
    )
    rutina_original = models.ForeignKey(
        Rutina,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='copias_cliente'
    )

    nombre = models.CharField(max_length=150)
    objetivo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True, null=True, verbose_name="Notas")
    
    archivo = models.FileField(
        upload_to='rutinas_clientes/', 
        verbose_name="Archivo Asignado"
    )

    version_asignada = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='activa')
    fecha_asignacion = models.DateTimeField(auto_now_add=True)
    
    descargar_notificacion = models.BooleanField(default=False)
    fecha_ultima_notificacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Rutina del Cliente"
        verbose_name_plural = "Rutinas del Cliente"
        ordering = ['-fecha_asignacion']

    def actualizar_desde_original(self):
        """Actualiza la copia con el nuevo archivo de la original."""
        if self.rutina_original:
            self.nombre = self.rutina_original.nombre
            self.objetivo = self.rutina_original.objetivo
            self.archivo = self.rutina_original.archivo
            self.version_asignada = self.rutina_original.version
            self.estado = 'activa'
            self.save()
            return True
        return False

    def __str__(self):
        return f"{self.cliente} - {self.nombre}"


class ReglaCuidado(models.Model):
    """
    Define reglas automáticas asociadas a un servicio.
    Ej: Servicio "Alisado" -> Restricción "No mojar" por 2 días.
    """
    TIPO_ACCION = [
        ('RESTRICCION', 'Restricción (Lo que NO debes hacer)'),
        ('HABITO', 'Hábito (Lo que DEBES hacer)'),
    ]

    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='reglas_post_servicio')
    tipo = models.CharField(max_length=20, choices=TIPO_ACCION)
    descripcion = models.CharField(max_length=255, help_text="Ej: No mojar el cabello")
    
    dias_duracion = models.IntegerField(default=0, help_text="Duración de la regla en días (0 = puntual)")
    frecuencia_dias = models.IntegerField(null=True, blank=True, help_text="Cada cuántos días repetir")
    
    rutina = models.ForeignKey(
        Rutina,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reglas_cuidado',
        help_text="Rutina específica recomendada."
    )

    class Meta:
        verbose_name = "Regla de Cuidado"
        verbose_name_plural = "Reglas de Cuidado"

    def __str__(self):
        return f"{self.servicio.nombre} -> {self.tipo}: {self.descripcion}"


class AgendaCuidados(models.Model):
    """
    Registra las tareas/cuidados que debe hacer un cliente en determinadas fechas.
    """
    cliente = models.ForeignKey('usuarios.Cliente', on_delete=models.CASCADE, related_name='agenda_cuidados')
    fecha = models.DateField()
    titulo = models.CharField(max_length=100)
    descripcion = models.TextField()
    completado = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Agenda de Cuidados"
        verbose_name_plural = "Agendas de Cuidados"
        ordering = ['fecha']

    def __str__(self):
        return f"{self.cliente} - {self.fecha}: {self.titulo}"


# ============================================================
# SECCIÓN 4: CONFIGURACIÓN, HORARIOS Y TURNOS
# ============================================================

class Configuracion(models.Model):
    """
    PATRÓN SINGLETON: Guarda las reglas globales del negocio.
    Cumple con OBJ-10, IRQ-15 (Políticas de Seña) y RF-05.
    """
    # Grid y Tiempo
    intervalo_turnos = models.IntegerField(
        default=30, 
        help_text="Minutos de cada bloque visual en la agenda"
    )
    max_dias_anticipacion = models.IntegerField(
        default=60, 
        help_text="Cuanto tiempo antes se puede reservar"
    )
    
    # Política de Señas
    monto_sena = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=5000.00, 
        verbose_name="Monto de Seña"
    )
    tiempo_limite_pago_sena = models.IntegerField(
        default=24, 
        help_text="Horas para pagar la seña antes de cancelar automático"
    )
    
    # Cancelación y Reprogramación
    max_reprogramaciones = models.IntegerField(
        default=2, 
        help_text="Máximo de cambios permitidos por cliente"
    )
    horas_limite_cancelacion = models.IntegerField(
        default=48, 
        help_text="Horas antes del turno donde YA NO se puede cancelar."
    )

    class Meta:
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuración"

    def save(self, *args, **kwargs):
        # Fuerza ID=1 siempre (patrón Singleton)
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Configuración General de Bohemia Hair"


class HorarioLaboral(models.Model):
    """
    Define la disponibilidad recurrente semanal POR EMPLEADO.
    Especifica en qué horarios trabaja cada persona cada día de la semana.
    """
    personal = models.ForeignKey(
        Personal, 
        on_delete=models.CASCADE, 
        related_name='horarios', 
        null=True, blank=True
    )
    
    dia_semana = models.IntegerField(choices=DiasSemana.choices, default=0)  
    
    fecha_desde = models.DateField(null=True, blank=True) 
    fecha_hasta = models.DateField(null=True, blank=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        verbose_name = "Horario Laboral"
        verbose_name_plural = "Horarios Laborales"
        ordering = ['dia_semana', 'hora_inicio']

    def __str__(self):
        if self.personal:
            return f"{self.personal.nombre} - {self.get_dia_semana_display()} {self.hora_inicio}-{self.hora_fin}"
        return f"{self.get_dia_semana_display()} {self.hora_inicio}-{self.hora_fin}"
    
    # Nuevos campos para configuración dinámica (RF-15 y Reglas de Negocio A)
    permite_diseno_color = models.BooleanField(
        default=True, 
        help_text="Si se tilda, Yani puede recibir servicios largos (Diseño) en este horario."
    )
    permite_complemento = models.BooleanField(
        default=True, 
        help_text="Si se tilda, se permiten servicios cortos (Corte, Nutrición)."
    )
    activo = models.BooleanField(default=True)


class BloqueoAgenda(models.Model):
    """
    Días libres, vacaciones, feriados o médico.
    Sobreescribe la regla de HorarioLaboral.
    """
    personal = models.ForeignKey(
        Personal, 
        on_delete=models.CASCADE, 
        null=True, blank=True, 
        related_name='bloqueos',
        help_text="Si se deja vacío, aplica a TODO el salón (ej. Feriado Nacional)"
    )
    
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    motivo = models.CharField(max_length=200)
    bloquea_todo_el_dia = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Bloqueo / Excepción de Agenda"
        verbose_name_plural = "Bloqueos de Agenda"
        ordering = ['fecha_inicio']

    def clean(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha de fin no puede ser anterior a la de inicio.")

    def __str__(self):
        persona = self.personal.nombre if self.personal else "TODO EL SALÓN"
        return f"Bloqueo: {persona} - {self.motivo}"


class Turno(models.Model):
    """
    Representa un turno / appointment en el sistema.
    Incluye cliente, profesional, fecha, hora, estado, etc.
    """
    class Estado(models.TextChoices):
        SOLICITADO = 'solicitado', 'Solicitado (Requiere Análisis)'
        ESPERANDO_SENA = 'esperando_sena', 'Aprobado (Esperando Seña)'
        CONFIRMADO = 'confirmado', 'Confirmado (Seña OK)'
        REALIZADO = 'realizado', 'Realizado'
        CANCELADO = 'cancelado', 'Cancelado / Rechazado'
        AUSENTE = 'ausente', 'Ausente (No vino)'
        PENDIENTE = 'pendiente', 'Pendiente'
        EN_PROCESO = 'en_proceso', 'En Proceso'

    # Relaciones
    cliente = models.ForeignKey(
        'usuarios.Cliente', 
        on_delete=models.CASCADE, 
        related_name='mis_turnos'
    )
    profesional = models.ForeignKey(
        'gestion.Personal', 
        on_delete=models.PROTECT,
        related_name='turnos_asignados',
        null=True,
        blank=True
    )
    equipamiento = models.ForeignKey(
        'gestion.Equipamiento', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Datos temporales
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin_calculada = models.TimeField(blank=True, null=True)
    
    # Estado
    estado = models.CharField(
        max_length=20, 
        choices=Estado.choices, 
        default=Estado.SOLICITADO
    )
    
    # Auditoría
    comprobante_pago = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    cambios_realizados = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Turno"
        verbose_name_plural = "Turnos"
        ordering = ['fecha', 'hora_inicio']
        unique_together = ['fecha', 'hora_inicio', 'cliente']

    def __str__(self):
        return f"Turno {self.fecha} {self.hora_inicio} - {self.cliente}"
    
    @property
    def duracion_total(self):
        """Suma la duración de todos los servicios asociados a este turno"""
        return sum(detalle.duracion_minutos for detalle in self.detalles.all())


class DetalleTurno(models.Model):
    """Entidad Asociativa exigida por la cátedra"""
    turno = models.ForeignKey(Turno, on_delete=models.CASCADE, related_name='detalles')
    servicio = models.ForeignKey('gestion.Servicio', on_delete=models.PROTECT)
    
    # Mantenemos tus nombres: son claros y profesionales
    precio_historico = models.DecimalField(max_digits=10, decimal_places=2)
    duracion_minutos = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Detalle del Turno"
        verbose_name_plural = "Detalles del Turno"
        # IMPORTANTE: Evita duplicados del mismo servicio en la misma cita
        unique_together = ('turno', 'servicio') 

    def __str__(self):
        return f"{self.servicio.nombre} - Turno ID: {self.turno.id}"
    

class FichaTecnica(models.Model):
    # Relación 1:1 con el detalle del servicio realizado
    # Esto asegura que cada servicio de un turno pueda tener su propia fórmula
    detalle_turno = models.OneToOneField(
        'DetalleTurno', 
        on_delete=models.CASCADE, 
        related_name='ficha_tecnica'
    )
    
    # Profesional que realizó la anotación técnica
    profesional_autor = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        related_name='fichas_redactadas'
    )
    
    # NUEVO: Campos granulares según tu análisis
    formula = models.TextField()  # Aquí se guarda la fórmula ajustada
    observaciones_proceso = models.TextField(blank=True, null=True)
    
    # NUEVO: Estado final basado en IRQ-02
    # Relaciones a las tablas maestras de diagnóstico
    porosidad_final = models.ForeignKey(
        'gestion.PorosidadCabello', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Porosidad Post-Servicio",
        related_name='fichas_registradas'
    )
    
    estado_general_final = models.ForeignKey(
        'gestion.EstadoGeneral',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Estado General Post-Servicio",
        related_name='fichas_registradas'
    )
    
    resultado_post_servicio = models.TextField(blank=True, null=True)
    foto_resultado = models.ImageField(upload_to='fichas_tecnicas/', null=True, blank=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ficha Técnica"
        verbose_name_plural = "Fichas Técnicas"


class ListaEspera(models.Model):
    """
    Registra clientes interesadas en un hueco si se libera.
    Cola FIFO (First In, First Out).
    """
    cliente = models.ForeignKey(
        'usuarios.Cliente', 
        on_delete=models.CASCADE,
        related_name='esperas'
    )
    servicio_interes = models.ForeignKey(
        Servicio, 
        on_delete=models.SET_NULL, 
        null=True,
        help_text="Servicio deseado"
    )
    
    # Rango de fechas de preferencia
    fecha_deseada_inicio = models.DateField()
    fecha_deseada_fin = models.DateField()
    
    # Preferencia horaria
    hora_rango_inicio = models.TimeField(default="08:00")
    hora_rango_fin = models.TimeField(default="20:00")
    
    # Estado
    fecha_registro = models.DateTimeField(auto_now_add=True)
    notificado = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Lista de Espera"
        verbose_name_plural = "Listas de Espera"
        ordering = ['fecha_registro']

    def __str__(self):
        return f"Espera: {self.cliente} ({self.fecha_deseada_inicio} al {self.fecha_deseada_fin})"


# ============================================================
# SECCIÓN 5: EQUIPAMIENTO Y NOTIFICACIONES
# ============================================================

class TipoEquipamiento(models.Model):
    """Tabla Maestra para estandarizar tipos de recursos por empresa"""
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Tipo de Equipamiento"
        verbose_name_plural = "Tipos de Equipamientos"

    def __str__(self):
        return self.nombre

class Equipamiento(models.Model):
    # Tipos y Estados definidos como constantes para legibilidad interna
    class EstadoRecurso(models.TextChoices):
        DISPONIBLE = 'DISPONIBLE', 'Disponible'
        EN_USO = 'EN_USO', 'En Uso'
        MANTENIMIENTO = 'MANTENIMIENTO', 'En Mantenimiento'
        FUERA_SERVICIO = 'FUERA_SERVICIO', 'Fuera de Servicio / Roto'

    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)
    tipo = models.ForeignKey(TipoEquipamiento, on_delete=models.PROTECT, related_name='recursos')
    estado = models.CharField(max_length=20, choices=EstadoRecurso.choices, default=EstadoRecurso.DISPONIBLE)
    
    # Campos exigidos por IRQ-18 y Matriz de Rastreabilidad
    ubicacion = models.CharField(max_length=100, blank=True, null=True, help_text="Ubicación física dentro del salón")
    observaciones = models.TextField(blank=True, null=True)
    
    # Gestión de ciclo de vida (Baja Lógica)
    is_active = models.BooleanField(default=True)
    fecha_adquisicion = models.DateField(default=timezone.now)
    fecha_baja = models.DateTimeField(null=True, blank=True)
    ultimo_mantenimiento = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Equipamiento"
        verbose_name_plural = "Equipamientos"
        ordering = ['codigo']

    def __str__(self):
        return f"[{self.codigo}] {self.nombre}"


class RequisitoServicio(models.Model):
    """
    Tabla Intermedia Explícita: Asocia Servicios con Tipos de Equipamiento requeridos.
    Permite rastrear qué equipos son necesarios para cada servicio.
    """
    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.CASCADE,
        related_name='requisitos_equipamiento'
    )
    
    tipo_equipamiento = models.ForeignKey(
        TipoEquipamiento,
        on_delete=models.CASCADE,
        related_name='servicios_requeridos'
    )
    
    obligatorio = models.BooleanField(
        default=True,
        help_text="Si es True, el equipo DEBE estar disponible para realizar el servicio"
    )
    
    cantidad_minima = models.PositiveIntegerField(
        default=1,
        help_text="Cantidad mínima de este tipo de equipo necesaria"
    )
    
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Requisito de Servicio"
        verbose_name_plural = "Requisitos de Servicios"
        unique_together = ('servicio', 'tipo_equipamiento')

    def __str__(self):
        return f"{self.servicio.nombre} requiere {self.tipo_equipamiento.nombre}"

class DiagnosticoCapilar(models.Model):
    """
    Registro de diagnóstico realizado a un cliente.
    Tabla maestra que guarda el histórico de evaluaciones del cabello.
    """
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.CASCADE,
        related_name='diagnosticos_capilares'
    )
    
    # Profesional que realizó el diagnóstico
    profesional = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosticos_realizados'
    )
    
    # Estado del cabello en el momento del diagnóstico
    tipo_cabello = models.ForeignKey(
        TipoCabello,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    grosor_cabello = models.ForeignKey(
        GrosorCabello,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    porosidad_cabello = models.ForeignKey(
        PorosidadCabello,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    cuero_cabelludo = models.ForeignKey(
        CueroCabelludo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    estado_general = models.ForeignKey(
        EstadoGeneral,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Observaciones y recomendaciones
    observaciones = models.TextField(blank=True, null=True)
    recomendaciones = models.TextField(blank=True, null=True)
    
    # Regla que se aplicó
    regla_diagnostico = models.ForeignKey(
        ReglaDiagnostico,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosticos_generados'
    )
    
    # Rutina sugerida como resultado
    rutina_sugerida = models.ForeignKey(
        Rutina,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosticos_que_la_sugirieron'
    )
    
    fecha_diagnostico = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Diagnóstico Capilar"
        verbose_name_plural = "Diagnósticos Capilares"
        ordering = ['-fecha_diagnostico']
    
    def __str__(self):
        return f"Diagnóstico {self.cliente} - {self.fecha_diagnostico.strftime('%d/%m/%Y')}"

class Notificacion(models.Model):
    """
    Sistema de notificaciones para usuarios.
    Puede enviarse por app, email o WhatsApp.
    """
    TIPO_CHOICES = [
        ('informativa', 'Informativa'),
        ('alerta', 'Alerta'),
        ('recordatorio', 'Recordatorio'),
        ('ADELANTO', 'Oferta de Adelanto de Turno'),
    ]
    
    CANAL_CHOICES = [
        ('app', 'Aplicación (In-App)'),
        ('email', 'Correo Electrónico'),
        ('whatsapp', 'WhatsApp'),
    ]

    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('enviado', 'Enviado'),
        ('leido', 'Leído'),
        ('error', 'Error'),
    ]

    usuario = models.ForeignKey(
        'usuarios.Usuario', 
        on_delete=models.CASCADE, 
        related_name='notificaciones'
    )
    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES, default='informativa')
    canal = models.CharField(max_length=50, choices=CANAL_CHOICES, default='app')
    titulo = models.CharField(max_length=100)
    mensaje = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_envio = models.DateTimeField(auto_now_add=True)
    
    # Referencia genérica
    origen_entidad = models.CharField(max_length=50, blank=True, null=True)
    origen_id = models.IntegerField(blank=True, null=True)

    datos_extra = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ['-fecha_envio']

    def __str__(self):
        return f"[{self.canal}] {self.titulo} -> {self.usuario}"