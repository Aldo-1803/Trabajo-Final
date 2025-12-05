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


#----------------------------------------------------
# 5. MODELOS DE AGENDA
#----------------------------------------------------
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

#----------------------------------------------------
# 6. MODELOS DE TURNOS Y RUTINAS   
#----------------------------------------------------
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
    
#----------------------------------------------------
# 7. MODELOS DE RUTINAS
#----------------------------------------------------

class Rutina(models.Model):
    # Enums para el Estado (Best Practice en Django)
    ESTADO_CHOICES = [
        ('borrador', 'Borrador'),
        ('publicada', 'Publicada'),
        ('obsoleta', 'Obsoleta'),
    ]

    # Atributos del Diagrama
    nombre = models.CharField(max_length=150)
    objetivo = models.CharField(max_length=255, help_text="Ej: Hidratación profunda")
    descripcion = models.TextField()
    version = models.PositiveIntegerField(default=1)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='borrador')
    
    # Relación con Usuario (creada_por)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT,  # Evita eliminar usuarios con rutinas
        related_name='rutinas_creadas'
    )

    # Clientes asignados a esta rutina
    clientes_asignados = models.ManyToManyField(
        'usuarios.Cliente',
        related_name='rutinas_asignadas',
        blank=True,
        help_text="Clientes que tienen esta rutina asignada"
    )

    # Campos de auditoría y control
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_obsoleta = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Fecha en que la rutina fue marcada como obsoleta"
    )

    # Métodos del Diagrama
    def actualizar_version(self):
        """Incrementa la versión de la rutina."""
        self.version += 1
        self.save()

    def publicar(self):
        """Cambia el estado a publicada."""
        self.estado = 'publicada'
        self.save()

    def obsoletar(self):
        """
        Marca la rutina como obsoleta y notifica a todos los clientes asignados.
        No se puede asignar a nuevos clientes.
        """
        from django.utils import timezone
        
        self.estado = 'obsoleta'
        self.fecha_obsoleta = timezone.now()
        self.save()
        
        # Notificar a todos los clientes asignados
        self._notificar_clientes_obsoleta()

    def _notificar_clientes_obsoleta(self):
        """
        Crea notificaciones para todos los clientes que tienen esta rutina asignada.
        """
        clientes = self.clientes_asignados.all()
        
        for cliente in clientes:
            # Crear notificación para cada cliente
            Notificacion.objects.create(
                usuario=cliente.usuario,
                tipo='alerta',
                canal='app',
                titulo=f'Rutina "{self.nombre}" Obsoleta',
                mensaje=f'La rutina "{self.nombre}" ha sido marcada como obsoleta y ya no está disponible. '
                        f'Contacta con Bohemia Hair para una nueva rutina de cuidado.',
                estado='pendiente',
                origen_entidad='Rutina',
                origen_id=self.id
            )

    def puede_asignarse(self):
        """Retorna True si la rutina puede asignarse a nuevos clientes."""
        return self.estado == 'publicada'

    def asignar_a_cliente(self, cliente):
        """
        Crea una copia de esta rutina para el cliente especificado.
        Retorna la RutinaCliente creada o existente.
        """
        if not self.puede_asignarse():
            raise ValueError(f"La rutina '{self.nombre}' no puede asignarse en estado '{self.estado}'")

        # Obtener o crear la copia para este cliente
        rutina_cliente, creada = RutinaCliente.objects.get_or_create(
            cliente=cliente,
            rutina_original=self,
            defaults={
                'nombre': self.nombre,
                'objetivo': self.objetivo,
                'descripcion': self.descripcion,
                'version_asignada': self.version,
                'estado': 'activa'
            }
        )

        # Si fue creada, copiar los pasos
        if creada:
            for paso_original in self.pasos.all():
                PasoRutinaCliente.objects.create(
                    rutina_cliente=rutina_cliente,
                    orden=paso_original.orden,
                    descripcion=paso_original.descripcion,
                    frecuencia=paso_original.frecuencia
                )

        return rutina_cliente

    def notificar_actualizacion_a_copias(self):
        """
        Notifica a todos los clientes que tienen una copia de esta rutina
        que hay una nueva versión disponible.
        """
        copias = self.copias_cliente.filter(estado='activa')
        for copia in copias:
            copia.marcar_desactualizada()

    def __str__(self):
        return f"{self.nombre} (v{self.version}) [{self.get_estado_display()}]"

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
        """Cambia el orden del paso."""
        # Nota: Aquí iría lógica compleja para mover los otros pasos, 
        # pero para la tesis basta con actualizar este valor.
        self.orden = nuevo_orden
        self.save()

    def __str__(self):
        return f"{self.orden}. {self.descripcion[:30]}..."

#----------------------------------------------------
# 8. MODELOS DE REGLAS DE CUIDADO POST-SERVICIO
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
# MODELOS DE RUTINA CLIENTE (COPIA PERSONALIZADA)
# ============================================
class RutinaCliente(models.Model):
    """
    Representa una COPIA de la rutina asignada al cliente.
    Cuando se asigna una rutina, se crea una copia aquí.
    Si la rutina original se modifica o se elimina, el cliente mantiene su versión.
    """
    ESTADO_CHOICES = [
        ('activa', 'Activa'),
        ('desactualizada', 'Desactualizada'),  # La original fue modificada
        ('obsoleta_original', 'Original Obsoleta'),  # La original fue marcada como obsoleta
        ('completada', 'Completada'),
    ]

    # Relaciones
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.CASCADE,
        related_name='rutinas_cliente'
    )
    rutina_original = models.ForeignKey(
        Rutina,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='copias_cliente',
        help_text="Referencia a la rutina original (puede ser NULL si fue eliminada)"
    )

    # Datos copiados de la rutina original (snapshot)
    nombre = models.CharField(max_length=150)
    objetivo = models.CharField(max_length=255)
    descripcion = models.TextField()
    version_asignada = models.PositiveIntegerField(
        help_text="La versión de la rutina original cuando se copió"
    )

    # Estado y control
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='activa'
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)
    descargar_notificacion = models.BooleanField(
        default=False,
        help_text="¿Se le notificó al cliente sobre descarga/actualización?"
    )
    fecha_ultima_notificacion = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Cuándo se le notificó de una actualización disponible"
    )

    class Meta:
        ordering = ['-fecha_asignacion']
        unique_together = ['cliente', 'rutina_original']  # Un cliente no puede tener 2 copias de la misma rutina
        verbose_name = "Rutina del Cliente"
        verbose_name_plural = "Rutinas del Cliente"

    def activar(self):
        """Marca la copia como activa."""
        self.estado = 'activa'
        self.descargar_notificacion = False
        self.save()

    def marcar_desactualizada(self):
        """
        Marca la copia como desactualizada cuando la original cambia.
        Notifica al cliente de que hay una nueva versión disponible.
        """
        from django.utils import timezone
        
        self.estado = 'desactualizada'
        self.descargar_notificacion = True
        self.fecha_ultima_notificacion = timezone.now()
        self.save()

        # Notificar al cliente
        Notificacion.objects.create(
            usuario=self.cliente.usuario,
            tipo='recordatorio',
            canal='app',
            titulo=f'Rutina "{self.nombre}" Actualizada',
            mensaje=f'La rutina "{self.nombre}" tiene una nueva versión disponible. '
                    f'¿Deseas actualizar a la versión {self.rutina_original.version}?',
            estado='pendiente',
            origen_entidad='RutinaCliente',
            origen_id=self.id
        )

    def marcar_original_obsoleta(self):
        """
        Marca la copia como obsoleta cuando la original es marcada como obsoleta.
        """
        from django.utils import timezone
        
        self.estado = 'obsoleta_original'
        self.fecha_ultima_notificacion = timezone.now()
        self.save()

        # Notificar al cliente
        Notificacion.objects.create(
            usuario=self.cliente.usuario,
            tipo='alerta',
            canal='app',
            titulo=f'Rutina "{self.nombre}" Ya No Está Disponible',
            mensaje=f'La rutina "{self.nombre}" ha sido descontinuada por Bohemia Hair. '
                    f'Puedes seguir usándola, pero te recomendamos que solicites una nueva. '
                    f'Contacta con nosotros.',
            estado='pendiente',
            origen_entidad='RutinaCliente',
            origen_id=self.id
        )

    def actualizar_desde_original(self):
        """
        Actualiza esta copia con los datos de la rutina original.
        Elimina los pasos antiguos y copia los nuevos.
        """
        if not self.rutina_original:
            return False

        # Actualizar datos
        self.nombre = self.rutina_original.nombre
        self.objetivo = self.rutina_original.objetivo
        self.descripcion = self.rutina_original.descripcion
        self.version_asignada = self.rutina_original.version
        self.activar()

        # Eliminar pasos antiguos
        self.pasos.all().delete()

        # Copiar pasos nuevos
        for paso_original in self.rutina_original.pasos.all():
            PasoRutinaCliente.objects.create(
                rutina_cliente=self,
                orden=paso_original.orden,
                descripcion=paso_original.descripcion,
                frecuencia=paso_original.frecuencia
            )

        return True

    def __str__(self):
        return f"{self.cliente.usuario.email} - {self.nombre} (v{self.version_asignada})"


class PasoRutinaCliente(models.Model):
    """
    Representa un PASO de la copia de rutina del cliente.
    Es una copia del PasoRutina original.
    """
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
        """Marca el paso como completado."""
        from django.utils import timezone
        
        self.completado = True
        self.fecha_completado = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.orden}. {self.descripcion[:40]}... ({self.rutina_cliente.cliente.usuario.email})"

# ----------------------------------------------------
# 9. MODELO DE NOTIFICACIONES
# ----------------------------------------------------
class Notificacion(models.Model):
    # Enums para restringir valores y evitar errores de tipeo
    TIPO_CHOICES = [
        ('informativa', 'Informativa'),
        ('alerta', 'Alerta'),
        ('recordatorio', 'Recordatorio'),
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

    class Meta:
        ordering = ['-fecha_envio']

    def __str__(self):
        return f"[{self.canal}] {self.titulo} -> {self.usuario}"