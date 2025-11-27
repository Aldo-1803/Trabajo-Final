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
    """
    intervalo_turnos = models.IntegerField(default=30, help_text="Minutos de cada bloque en la grilla visual")
    max_dias_anticipacion = models.IntegerField(default=60, help_text="Cuanto tiempo antes se puede reservar")
    
    # Política de Señas
    monto_sena = models.DecimalField(max_digits=10, decimal_places=2, default=5000.00)
    tiempo_limite_pago_sena = models.IntegerField(default=24, help_text="Horas para pagar antes de cancelar")

    class Meta:
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuración"

    def save(self, *args, **kwargs):
        # Esto fuerza a que siempre sea el ID=1. Si intentas crear otro, sobrescribe el existente.
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Configuración General (No borrar)"


class DiasSemana(models.IntegerChoices):
    """
    ENUM para evitar una tabla extra en la BD.
    Es más rápido y fácil de usar en el código.
    """
    LUNES = 0, 'Lunes'
    MARTES = 1, 'Martes'
    MIERCOLES = 2, 'Miércoles'
    JUEVES = 3, 'Jueves'
    VIERNES = 4, 'Viernes'
    SABADO = 5, 'Sábado'
    DOMINGO = 6, 'Domingo'


class HorarioLaboral(models.Model):
    """
    Define la 'plantilla' de disponibilidad de Yani.
    Ej: Lunes de 10:00 a 16:00.
    """
    dia = models.IntegerField(choices=DiasSemana.choices, unique=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['dia']
        verbose_name = "Horario Laboral"
        verbose_name_plural = "Horarios Laborales"

    def __str__(self):
        return f"{self.get_dia_display()}: {self.hora_inicio} - {self.hora_fin}"


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