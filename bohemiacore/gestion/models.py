from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError


# ----------------------------------------------------
# 1. CLASE BASE ABSTRACTA (Su excelente diseño)
# ----------------------------------------------------
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

# ----------------------------------------------------
# 2. MODELOS DE DIAGNÓSTICO (Heredan de la Base)
# ----------------------------------------------------

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

# ----------------------------------------------------
# 3. MODELO DE REGLAS DE DIAGNÓSTICO
# ----------------------------------------------------
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
    

class CategoriaServicio(CatalogoBase):
    """
    Clasifica los servicios (ej. 'Químicos', 'Corte', 'Peinado').
    Hereda 'nombre' y 'descripcion' de CatalogoBase.
    """
    class Meta:
        verbose_name = "Categoría de Servicio"
        verbose_name_plural = "Categorías de Servicios"


class Servicio(CatalogoBase):
    """
    El modelo principal para los servicios de Bohemia.
    Hereda 'nombre' y 'descripcion' de CatalogoBase.
    """
    
    # 1. CATEGORIA (Tu atributo clave)
    categoria = models.ForeignKey(
        CategoriaServicio,
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        verbose_name="Categoría"
    )
    
    # 2. DURACION (Tu atributo)
    duracion_estimada = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Duración Estimada (en minutos)"
    )
    
    # 3. PRECIO (Tu atributo)
    precio_base = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0.00,
        verbose_name="Precio Base"
    )
    
    #Campo para identificar si requiere tiempo de reposo (paralelismo)
    permite_simultaneidad = models.BooleanField(
        default=False, 
        help_text="Si es True, Yani puede atender a otra persona durante el reposo."
    )
    
    # 1. RUTINA ESPECÍFICA (La recomendación)
    rutina_recomendada = models.ForeignKey(
        'Rutina', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Rutina que se asignará automáticamente al finalizar este servicio."
    )

    # 2. IMPACTO EN EL CABELLO (El nuevo diagnóstico)
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

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"

    # Opcional: Modificamos el __str__ para que muestre la categoría
    def __str__(self):
        if self.categoria:
            return f"[{self.categoria.nombre}] {self.nombre}"
        return self.nombre
    

# ----------------------------------------------------
# 4. MODELOS DE CONFIGURACIÓN DEL AGENDA
# ----------------------------------------------------
class Configuracion(models.Model):
    """
    PATRÓN SINGLETON: Guarda las reglas globales del negocio.
    Cumple con OBJ-10, IRQ-15 (Políticas de Seña) y RF-05.
    """
    # Grid y Tiempo
    intervalo_turnos = models.IntegerField(default=30, help_text="Minutos de cada bloque visual en la agenda")
    max_dias_anticipacion = models.IntegerField(default=60, help_text="Cuanto tiempo antes se puede reservar")
    
    # Política de Señas (IRQ-15)
    monto_sena = models.DecimalField(max_digits=10, decimal_places=2, default=5000.00, verbose_name="Monto de Seña")
    tiempo_limite_pago_sena = models.IntegerField(default=24, help_text="Horas para pagar la seña antes de cancelar automático")
    
    # Reglas de Cancelación y Reprogramación (RF-05)
    max_reprogramaciones = models.IntegerField(default=2, help_text="Máximo de cambios permitidos por cliente")
    horas_limite_cancelacion = models.IntegerField(
        default=48, 
        help_text="Horas antes del turno donde YA NO se puede cancelar y recuperar la seña."
    )

    class Meta:
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuración"

    def save(self, *args, **kwargs):
        # Fuerza ID=1 siempre
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Configuración General de Bohemia Hair"

#----------------------------------------------------
# 5. MODELOS DE AGENDA
#----------------------------------------------------
class DiasSemana(models.IntegerChoices):
    """
    ENUM para días. Más eficiente y seguro.
    """
    LUNES = 0, 'Lunes'
    MARTES = 1, 'Martes'
    MIERCOLES = 2, 'Miércoles'
    JUEVES = 3, 'Jueves'
    VIERNES = 4, 'Viernes'
    SABADO = 5, 'Sábado'
    DOMINGO = 6, 'Domingo'

#----------------------------------------------------
# 5. MODELO DE PERSONAL
#----------------------------------------------------
class Personal(models.Model):
    ROL_CHOICES = [
        ('colorista', 'Colorista / Principal'), # Yanina
        ('asistente', 'Asistente / Lavado'),    # Empleadas
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


#----------------------------------------------------
# 6. MODELOS DE TURNOS Y RUTINAS   
#----------------------------------------------------
class HorarioLaboral(models.Model):
    """
    Define la disponibilidad recurrente semanal POR EMPLEADO.
    Usamos tu enum DiasSemana.
    """
    personal = models.ForeignKey(Personal, on_delete=models.CASCADE, related_name='horarios', null=True, blank=True)
    
    # Aquí usamos tu clase DiasSemana
    dia_semana = models.IntegerField(choices=DiasSemana.choices, default=0)  
    
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()

    class Meta:
        ordering = ['dia_semana', 'hora_inicio']
        verbose_name = "Horario Laboral"
        verbose_name_plural = "Horarios Laborales"
        # Constraint opcional: Evitar duplicados exactos, pero permitir turnos cortados (mañana/tarde)
        # unique_together = ['personal', 'dia_semana', 'hora_inicio'] 

    def __str__(self):
        return f"{self.personal.nombre} - {self.get_dia_semana_display()} {self.hora_inicio}-{self.hora_fin}"
    
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

    def clean(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha de fin no puede ser anterior a la de inicio.")

    def __str__(self):
        persona = self.personal.nombre if self.personal else "TODO EL SALÓN"
        return f"Bloqueo: {persona} - {self.motivo}"
    
#----------------------------------------------------
# 7. MODELOS DE TURNOS
#----------------------------------------------------
class Turno(models.Model):
    class Estado(models.TextChoices):
        # --- FLUJO NORMAL ---
        SOLICITADO = 'solicitado', 'Solicitado (Requiere Análisis)'
        ESPERANDO_SENA = 'esperando_sena', 'Aprobado (Esperando Seña)'
        CONFIRMADO = 'confirmado', 'Confirmado (Seña OK)'
        
        # --- ESTADOS FINALES ---
        REALIZADO = 'realizado', 'Realizado'
        CANCELADO = 'cancelado', 'Cancelado / Rechazado'
        AUSENTE = 'ausente', 'Ausente (No vino)'

    # Relaciones
    cliente = models.ForeignKey(
        'usuarios.Cliente', 
        on_delete=models.CASCADE, 
        related_name='mis_turnos'
    )
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT)
    
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
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    comprobante_pago = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    cambios_realizados = models.IntegerField(
        default=0, 
        help_text="Contador de cuántas veces se ha reprogramado este turno"
    )

    class Meta:
        ordering = ['fecha', 'hora_inicio']
        # Restricción opcional: No permitir duplicados exactos (mismo día, misma hora, mismo cliente)
        unique_together = ['fecha', 'hora_inicio', 'cliente']

    def save(self, *args, **kwargs):
        # Cálculo automático de la hora de fin al guardar
        if self.hora_inicio and self.servicio:
            # Truco para sumar minutos a un objeto Time: combinar con fecha dummy
            inicio_dt = timezone.datetime.combine(timezone.now(), self.hora_inicio)
            fin_dt = inicio_dt + timezone.timedelta(minutes=self.servicio.duracion_estimada)
            self.hora_fin_calculada = fin_dt.time()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Turno {self.fecha} {self.hora_inicio} - {self.cliente}"
    
class ListaEspera(models.Model):
    """
    Registra clientas interesadas en un hueco si se libera.
    Funciona como una cola de prioridad FIFO (First In, First Out).
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
        help_text="Servicio que la clienta quiere realizarse"
    )
    
    # Rango de fechas en las que la clienta puede asistir
    fecha_deseada_inicio = models.DateField()
    fecha_deseada_fin = models.DateField()
    
    # Preferencia horaria (opcional, para filtrar mejor)
    hora_rango_inicio = models.TimeField(default="08:00")
    hora_rango_fin = models.TimeField(default="20:00")
    
    # Estado de la solicitud
    fecha_registro = models.DateTimeField(auto_now_add=True)
    notificado = models.BooleanField(default=False, help_text="Si ya se le avisó de un hueco disponible")
    
    # Para desactivar la solicitud si la clienta ya consiguió turno o se arrepintió
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Lista de Espera"
        verbose_name_plural = "Listas de Espera"
        ordering = ['fecha_registro'] # Prioridad por orden de llegada

    def __str__(self):
        return f"Espera: {self.cliente} ({self.fecha_deseada_inicio} al {self.fecha_deseada_fin})"
    
#----------------------------------------------------
# 8. MODELOS DE RUTINAS
#----------------------------------------------------

class Rutina(models.Model):
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('publicada', 'Publicada'),
        ('obsoleta', 'Obsoleta'),
    ]

    nombre = models.CharField(max_length=150)
    objetivo = models.CharField(max_length=255, help_text="Ej: Hidratación profunda")
    
    # --- NUEVO CAMPO PRINCIPAL ---
    archivo = models.FileField(
        upload_to='rutinas_pdfs/', 
        verbose_name="Documento de Rutina (PDF/Img)",
        help_text="Sube el diseño exportado de Canva o Word."
    )
    
    # Mantenemos descripción como opcional por si quiere dejar notas internas
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
        # Aquí podrías notificar a clientes (lógica de notificación)

    def asignar_a_cliente(self, cliente):
        """
        Crea una copia de esta rutina para el cliente.
        Ahora copia el archivo físico para mantener el histórico.
        """
        if self.estado != 'publicada':
            raise ValueError(f"La rutina no está publicada.")

        # Creamos la copia
        rutina_cliente = RutinaCliente.objects.create(
            cliente=cliente,
            rutina_original=self,
            nombre=self.nombre,
            objetivo=self.objetivo,
            archivo=self.archivo, # <--- Copiamos la referencia al archivo
            version_asignada=self.version,
            estado='activa'
        )
        return rutina_cliente

    def __str__(self):
        return f"{self.nombre} (v{self.version})"


"""
class PasoRutina(models.Model):
    # Nota: En tu diagrama se llama 'PasoPlantilla', aquí usamos PasoRutina para mantener coherencia con tu código anterior.
    # Si prefieres cambiar el nombre de la tabla, avísame.
    
    plantilla = models.ForeignKey(Rutina, related_name='pasos', on_delete=models.CASCADE)
    orden = models.PositiveIntegerField()
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    frecuencia = models.CharField(max_length=100, help_text="Ej: Diaria, Semanal")
    
    # Relación con Producto (opcional según tu diagrama tiene producto_id)
    # Asumimos que tienes un modelo Producto, si no, comenta esta línea.
    # producto = models.ForeignKey('Producto', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['orden']
        verbose_name = "Paso de Rutina"
        verbose_name_plural = "Pasos de Rutina"

    # Métodos del Diagrama
    def reordenar(self, nuevo_orden):
        ""Cambia el orden del paso.""
        # Nota: Aquí iría lógica compleja para mover los otros pasos, 
        # pero para la tesis basta con actualizar este valor.
        self.orden = nuevo_orden
        self.save()

    def __str__(self):
        return f"{self.orden}. {self.descripcion[:30]}..."

"""



#----------------------------------------------------
# 9. MODELOS DE REGLAS DE CUIDADO POST-SERVICIO
# ----------------------------------------------------    
class ReglaCuidado(models.Model):
    """
    Define reglas automáticas asociadas a un servicio.
    Ej: Servicio "Alisado" -> Restricción "No lavar" por 2 días.
    """
    TIPO_ACCION = [
        ('RESTRICCION', 'Restricción (Lo que NO debes hacer)'),
        ('HABITO', 'Hábito (Lo que DEBES hacer)'),
    ]

    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='reglas_post_servicio')
    tipo = models.CharField(max_length=20, choices=TIPO_ACCION)
    descripcion = models.CharField(max_length=255, help_text="Ej: No mojar el cabello")
    
    # Cuánto dura o cada cuánto se hace
    dias_duracion = models.IntegerField(default=0, help_text="Duración de la regla en días (0 = puntual/un solo día)")
    frecuencia_dias = models.IntegerField(null=True, blank=True, help_text="Cada cuántos días repetir (solo para hábitos)")
    
    rutina = models.ForeignKey(
        'Rutina',  # Modelo que define las rutinas
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reglas_cuidado',
        help_text="Rutina específica recomendada para esta regla."
    )

    def __str__(self):
        return f"{self.servicio.nombre} -> {self.tipo}: {self.descripcion}"
    
class AgendaCuidados(models.Model):
    cliente = models.ForeignKey('usuarios.Cliente', on_delete=models.CASCADE)
    fecha = models.DateField()
    titulo = models.CharField(max_length=100)
    descripcion = models.TextField()
    completado = models.BooleanField(default=False)


# ============================================
# 10.MODELOS DE RUTINA CLIENTE (COPIA PERSONALIZADA)
# ============================================
class RutinaCliente(models.Model):
    ESTADO_CHOICES = [
        ('activa', 'Activa'),
        ('desactualizada', 'Desactualizada'),
        ('obsoleta_original', 'Original Obsoleta'),
        ('archivada', 'Archivada'), # En vez de "completada"
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
    
    # --- LA COPIA DEL ARCHIVO ---
    archivo = models.FileField(
        upload_to='rutinas_clientes/', 
        verbose_name="Archivo Asignado"
    )

    version_asignada = models.PositiveIntegerField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='activa')
    fecha_asignacion = models.DateTimeField(auto_now_add=True)
    
    # Campos de notificación
    descargar_notificacion = models.BooleanField(default=False)
    fecha_ultima_notificacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_asignacion']
        verbose_name = "Rutina del Cliente"
        verbose_name_plural = "Rutinas del Cliente"

    def actualizar_desde_original(self):
        """Actualiza la copia con el nuevo archivo de la original."""
        if self.rutina_original:
            self.nombre = self.rutina_original.nombre
            self.objetivo = self.rutina_original.objetivo
            self.archivo = self.rutina_original.archivo # Actualizamos archivo
            self.version_asignada = self.rutina_original.version
            self.estado = 'activa'
            self.save()
            return True
        return False

    def __str__(self):
        return f"{self.cliente} - {self.nombre}"


"""
class PasoRutinaCliente(models.Model):
    ""
    Representa un PASO de la copia de rutina del cliente.
    Es una copia del PasoRutina original.
    ""
    rutina_cliente = models.ForeignKey(
        RutinaCliente,
        on_delete=models.CASCADE,
        related_name='pasos'
    )
    orden = models.PositiveIntegerField()
    descripcion = models.TextField()
    frecuencia = models.CharField(max_length=100, help_text="Ej: Diaria, Semanal")
    completado = models.BooleanField(default=False)
    fecha_completado = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['orden']
        verbose_name = "Paso de Rutina del Cliente"
        verbose_name_plural = "Pasos de Rutina del Cliente"

    def marcar_completado(self):
        ""Marca el paso como completado.""
        from django.utils import timezone
        
        self.completado = True
        self.fecha_completado = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.orden}. {self.descripcion[:40]}... ({self.rutina_cliente.cliente.usuario.email})"
"""

# ----------------------------------------------------
# 11. MODELO DE NOTIFICACIONES
# ----------------------------------------------------
class Notificacion(models.Model):
    # Enums para restringir valores y evitar errores de tipeo
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

    # Atributos según tu Diagrama de Clases
    usuario = models.ForeignKey('usuarios.Usuario', on_delete=models.CASCADE, related_name='notificaciones')
    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES, default='informativa')
    canal = models.CharField(max_length=50, choices=CANAL_CHOICES, default='app')
    titulo = models.CharField(max_length=100)
    mensaje = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    fecha_envio = models.DateTimeField(auto_now_add=True)
    
    # Referencia genérica manual
    origen_entidad = models.CharField(max_length=50, blank=True, null=True, help_text="Ej: 'Turno', 'Promocion'")
    origen_id = models.IntegerField(blank=True, null=True, help_text="ID de la entidad origen")

    datos_extra = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_envio']

    def __str__(self):
        return f"[{self.canal}] {self.titulo} -> {self.usuario}"
    

# ----------------------------------------------------
# B. MODELO PRODUCTOS
# ----------------------------------------------------
class Producto(models.Model):
    nombre = models.CharField(max_length=100, unique=True) # Validación: Nombre único
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2) # Validación: Mayor a cero se hace en serializer
    stock = models.IntegerField(default=0)
    activo = models.BooleanField(default=True) # Para "eliminar" lógicamente si es necesario

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    def __str__(self):
        return f"{self.nombre} (${self.precio})"

# ----------------------------------------------------
# D. MODELO EQUIPAMIENTO
# ----------------------------------------------------
class Equipamiento(models.Model):
    ESTADOS = [
        ('DISPONIBLE', 'Disponible'),
        ('MANTENIMIENTO', 'En Mantenimiento'),
        ('NO_DISPONIBLE', 'No Disponible / Roto'),
    ]

    TIPOS = [
        ('TECNICA', 'Silla Técnica/Trabajo'),
        ('REPOSO', 'Silla/Zona de Reposo'),
        ('LAVACABEZAS', 'Lavacabezas'),
    ]

    codigo = models.CharField(max_length=50, unique=True) # Validación: Código único
    nombre = models.CharField(max_length=100)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='DISPONIBLE')
    tipo = models.CharField(max_length=20, choices=TIPOS, default='TECNICA')
    fecha_adquisicion = models.DateField(auto_now_add=True)
    ultimo_mantenimiento = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Equipamiento"
        verbose_name_plural = "Equipamientos"

    def __str__(self):
        return f"[{self.codigo}] {self.nombre} - {self.get_estado_display()}"