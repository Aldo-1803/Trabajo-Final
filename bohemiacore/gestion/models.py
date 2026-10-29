from django.db import models
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
import logging
import uuid
from simple_history.models import HistoricalRecords
from .private_storage import private_payment_receipt_storage

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


class TechnicalRiskOutcome(models.TextChoices):
    APTO = 'APTO', 'Apto'
    ADVERTENCIA = 'ADVERTENCIA', 'Advertencia'
    REQUIERE_REVISION = 'REQUIERE_REVISION', 'Requiere revisión'
    NO_APTO = 'NO_APTO', 'No apto'


TECHNICAL_RISK_OUTCOME_ORDER = {
    TechnicalRiskOutcome.APTO: 0,
    TechnicalRiskOutcome.ADVERTENCIA: 1,
    TechnicalRiskOutcome.REQUIERE_REVISION: 2,
    TechnicalRiskOutcome.NO_APTO: 3,
}


PAYMENT_CURRENCY_MINOR_UNITS = {
    'ARS': 2,
    'BOB': 2,
    'BRL': 2,
    'CLP': 0,
    'EUR': 2,
    'PYG': 0,
    'USD': 2,
    'UYU': 2,
}
PAYMENT_CURRENCY_CHOICES = tuple(
    (code, code) for code in PAYMENT_CURRENCY_MINOR_UNITS
)
MANUAL_PAYMENT_METHODS = (
    'CASH',
    'BANK_TRANSFER',
    'EXTERNAL_CARD',
    'OTHER',
)


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
    
    # LEGACY - compatibility only. No son autoridad operativa de Turnos ni
    # Diagnóstico. Se conservan temporalmente hasta su retiro final.
    realiza_diagnostico = models.BooleanField(default=False)
    realiza_lavado = models.BooleanField(default=True)
    realiza_color = models.BooleanField(default=False)
    
    activo = models.BooleanField(default=True)
    color_calendario = models.CharField(max_length=7, default="#E11D48", help_text="Color Hex para identificarlo en la agenda")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Personal / Staff"
        verbose_name_plural = "Personal"
        permissions = [
            ('manage_personal', 'Can manage personnel'),
            ('manage_skills', 'Can manage personnel skills'),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.get_rol_display()})"


class Habilidad(models.Model):
    """Catálogo canónico de habilitaciones técnicas de Personal."""
    code = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Habilidad'
        verbose_name_plural = 'Habilidades'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.code} - {self.nombre}'


class PersonalHabilidad(models.Model):
    """Asignación auditable y reversible de una habilidad a Personal."""
    personal = models.ForeignKey(
        Personal,
        on_delete=models.CASCADE,
        related_name='habilidades_personal',
    )
    habilidad = models.ForeignKey(
        Habilidad,
        on_delete=models.PROTECT,
        related_name='asignaciones_personal',
    )
    activa = models.BooleanField(default=True)
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Habilidad de Personal'
        verbose_name_plural = 'Habilidades de Personal'
        constraints = [
            models.UniqueConstraint(
                fields=['personal', 'habilidad'],
                name='unique_personal_habilidad',
            ),
        ]

    def __str__(self):
        return f'{self.personal} - {self.habilidad.code}'


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

    es_quimico_agresivo = models.BooleanField(
        default=False,
        help_text="Marca si el servicio produce un impacto químico agresivo sobre el cabello."
    )
    dias_espera_bloqueo = models.PositiveIntegerField(
        default=0,
        help_text="Cantidad mínima de días de espera antes de repetir otro servicio químico agresivo."
    )
    dias_espera_minima = models.IntegerField(
        default=0,
        help_text="Cantidad mínima de días recomendada antes de repetir un servicio de la misma categoría."
    )

    habilidades_requeridas = models.ManyToManyField(
        Habilidad,
        through='ServicioHabilidad',
        related_name='servicios_requeridos',
        blank=True,
    )

    activo = models.BooleanField(default=True)
    puntaje_base = models.IntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"
        ordering = ['nombre']
        permissions = [
            ('manage_prices', 'Can manage prices'),
        ]

    def __str__(self):
        if self.categoria:
            return f"[{self.categoria.nombre}] {self.nombre}"
        return self.nombre


class ServicioHabilidad(models.Model):
    """Requisito técnico obligatorio de un Servicio (semántica AND)."""
    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.CASCADE,
        related_name='requisitos_habilidad',
    )
    habilidad = models.ForeignKey(
        Habilidad,
        on_delete=models.PROTECT,
        related_name='requisitos_servicio',
    )

    class Meta:
        verbose_name = 'Habilidad requerida por Servicio'
        verbose_name_plural = 'Habilidades requeridas por Servicio'
        constraints = [
            models.UniqueConstraint(
                fields=['servicio', 'habilidad'],
                name='unique_servicio_habilidad',
            ),
        ]

    def __str__(self):
        return f'{self.servicio} requiere {self.habilidad.code}'


class FamiliaProcesoTecnico(models.Model):
    """Clasificación técnica estable, independiente de la categoría comercial."""
    code = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Familia de proceso técnico'
        verbose_name_plural = 'Familias de procesos técnicos'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.code} - {self.nombre}'


class PerfilTecnicoServicio(models.Model):
    class EstadoClasificacion(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        CLASIFICADO = 'CLASIFICADO', 'Clasificado'

    class NivelRiesgo(models.TextChoices):
        NO_DEFINIDO = 'NO_DEFINIDO', 'No definido'
        BAJO = 'BAJO', 'Bajo'
        MEDIO = 'MEDIO', 'Medio'
        ALTO = 'ALTO', 'Alto'

    servicio = models.OneToOneField(
        Servicio,
        on_delete=models.CASCADE,
        related_name='perfil_tecnico',
    )
    familia = models.ForeignKey(
        FamiliaProcesoTecnico,
        on_delete=models.PROTECT,
        related_name='perfiles_servicio',
        null=True,
        blank=True,
    )
    estado_clasificacion = models.CharField(
        max_length=20,
        choices=EstadoClasificacion.choices,
        default=EstadoClasificacion.PENDIENTE,
    )
    nivel_riesgo = models.CharField(
        max_length=20,
        choices=NivelRiesgo.choices,
        default=NivelRiesgo.NO_DEFINIDO,
    )
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Perfil técnico de Servicio'
        verbose_name_plural = 'Perfiles técnicos de Servicios'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(estado_clasificacion='PENDIENTE')
                    | ~models.Q(nivel_riesgo='NO_DEFINIDO')
                ),
                name='classified_service_has_risk_level',
            ),
        ]

    def __str__(self):
        return f'{self.servicio} - {self.estado_clasificacion}'

class CategoriaProducto(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Categoría de Producto"
        verbose_name_plural = "Categorías de Productos"

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    # Atributos Básicos y de Diagrama
    sku = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text="Código único de inventario (se genera automáticamente si está vacío)"
    )
    nombre = models.CharField(max_length=100)
    marca = models.CharField(max_length=50, blank=True, null=True)
    categoria = models.ForeignKey(
        'CategoriaProducto', 
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='productos'
    )
    descripcion = models.TextField(blank=True)

    MATERIAL_PRINCIPAL_CHOICES = [
        ('SATEN', 'Satén'),
        ('MICROFIBRA', 'Microfibra'),
        ('MADERA', 'Madera'),
        ('PLASTICO', 'Plástico'),
    ]
    PROPOSITO_USO_CHOICES = [
        ('DORMIR', 'Dormir'),
        ('STYLING', 'Styling (Peinado)'),
        ('HIGIENE', 'Higiene'),
        ('SECADO', 'Secado'),
    ]
    material_principal = models.CharField(
        max_length=20,
        choices=MATERIAL_PRINCIPAL_CHOICES,
        null=True,
        blank=True
    )
    proposito_uso = models.CharField(
        max_length=20,
        choices=PROPOSITO_USO_CHOICES,
        null=True,
        blank=True
    )
    
    # Precios y Stock (Auditoría REQ-11)
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    # Parámetros de promoción (combos)
    promo_descuento_x2 = models.IntegerField(
        default=10,
        help_text="Descuento porcentual para combos de 2 productos"
    )
    promo_descuento_x3 = models.IntegerField(
        default=15,
        help_text="Descuento porcentual para combos de 3 productos"
    )
    
    # Gestión de Stock: Real vs Comprometido
    stock_real = models.PositiveIntegerField(
        default=0,
        help_text="Stock físico disponible en almacén"
    )
    stock_comprometido = models.PositiveIntegerField(
        default=0,
        help_text="Stock reservado por órdenes pendientes de WhatsApp"
    )
    stock_minimo = models.IntegerField(
        default=5,
        help_text="Mínimo para alerta de reposición"
    )

    def save(self, *args, **kwargs):
        if not self.sku:
            siguiente = 1
            ultimo = Producto.objects.order_by('-id').first()
            if ultimo and ultimo.id:
                siguiente = ultimo.id + 1
            sku_generado = f"PROD-{siguiente:06d}"
            while Producto.objects.filter(sku=sku_generado).exists():
                siguiente += 1
                sku_generado = f"PROD-{siguiente:06d}"
            self.sku = sku_generado

        super().save(*args, **kwargs)
    
    @property
    def stock_disponible(self):
        """Proyección comercial; una inconsistencia legacy no se oculta con clamp."""
        return self.stock_real - self.stock_comprometido
    
    def necesita_reposicion(self):
        """Devuelve True si el stock disponible está por debajo del mínimo"""
        return self.stock_disponible <= self.stock_minimo

    # Atributos Visuales y de Estado (Diagrama)
    imagen = models.ImageField(
        upload_to='productos/',
        blank=True,
        null=True,
        help_text="Imagen del producto"
    )
    estado_publicacion = models.CharField(
        max_length=20, 
        choices=[('BORRADOR', 'Borrador'), ('PUBLICADO', 'Publicado')],
        default='PUBLICADO'
    )
    activo = models.BooleanField(default=True)

    # --- EL SECRETO PARA LA TESIS: Compatibilidades ---
    # Esto permite que el sistema diga: "Si el diagnóstico dio Pelo Seco, ofrece este producto"
    COMPATIBILIDAD_CABELLO = [
        ('TODO', 'Todo tipo'),
        ('LACIO', 'Lacio'),
        ('RIZADO', 'Rizado/Afro'),
        ('DANADO', 'Dañado/Procesado'),
        ('GRASO', 'Graso'),
        ('SECO', 'Seco'),
    ]
    compatibilidad = models.CharField(
        max_length=20, 
        choices=COMPATIBILIDAD_CABELLO, 
        default='TODO'
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['nombre']
        permissions = [
            ('manage_products', 'Can manage products'),
            ('view_stock', 'Can view stock'),
            ('manage_stock', 'Can manage stock'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stock_real__gte=0),
                name='product_nonnegative_real_stock',
            ),
            models.CheckConstraint(
                condition=models.Q(stock_comprometido__gte=0),
                name='product_nonnegative_committed_stock',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    stock_comprometido__lte=models.F('stock_real')
                ),
                name='product_committed_not_above_real_stock',
            ),
            models.CheckConstraint(
                condition=models.Q(stock_minimo__gte=0),
                name='product_nonnegative_minimum_stock',
            ),
        ]

    def __str__(self):
        return f"{self.marca} - {self.nombre} ({self.stock_disponible} ud.)"


class ImmutableStockMovementQuerySet(models.QuerySet):
    immutable_error = 'Los movimientos de stock son inmutables.'

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(
            'La creación masiva de movimientos de stock no está permitida.'
        )

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(self.immutable_error)


class StockMovementManager(
    models.Manager.from_queryset(ImmutableStockMovementQuerySet)
):
    def _create_from_inventory_service(self, **values):
        movement = self.model(**values)
        movement._allow_inventory_service_create = True
        movement.save(force_insert=True, using=self.db)
        return movement


class MovimientoStock(models.Model):
    class Type(models.TextChoices):
        OPENING_BALANCE = 'OPENING_BALANCE', 'Saldo inicial'
        RECEIPT_IN = 'RECEIPT_IN', 'Recepción'
        ORDER_SALE_OUT = 'ORDER_SALE_OUT', 'Salida por venta'
        MANUAL_ADJUSTMENT = 'MANUAL_ADJUSTMENT', 'Ajuste manual'
        CORRECTION = 'CORRECTION', 'Corrección'

    class ActorKind(models.TextChoices):
        HUMAN = 'HUMAN', 'Humano'
        SYSTEM = 'SYSTEM', 'Sistema'

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name='movimientos_stock',
    )
    delta = models.IntegerField()
    tipo = models.CharField(max_length=24, choices=Type.choices)
    reason_code = models.CharField(max_length=50)
    nota = models.CharField(max_length=500, blank=True, default='')
    actor_kind = models.CharField(max_length=10, choices=ActorKind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='movimientos_stock',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    reference_type = models.CharField(max_length=50, blank=True, default='')
    reference_id = models.CharField(max_length=100, blank=True, default='')
    idempotency_key = models.CharField(max_length=128, unique=True)
    stock_before = models.IntegerField()
    stock_after = models.IntegerField()
    reverses_movement = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        related_name='correction_movements',
        null=True,
        blank=True,
    )

    objects = StockMovementManager()

    class Meta:
        verbose_name = 'Movimiento de stock'
        verbose_name_plural = 'Movimientos de stock'
        ordering = ['-created_at', '-pk']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(delta=0),
                name='stock_movement_nonzero_delta',
            ),
            models.CheckConstraint(
                condition=models.Q(stock_before__gte=0),
                name='stock_movement_nonnegative_before',
            ),
            models.CheckConstraint(
                condition=models.Q(stock_after__gte=0),
                name='stock_movement_nonnegative_after',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    stock_after=models.F('stock_before') + models.F('delta')
                ),
                name='stock_movement_coherent_balance',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(actor_kind='HUMAN', actor__isnull=False)
                    | models.Q(actor_kind='SYSTEM', actor__isnull=True)
                ),
                name='stock_movement_coherent_actor',
            ),
            models.CheckConstraint(
                condition=~models.Q(reason_code=''),
                name='stock_movement_reason_required',
            ),
            models.CheckConstraint(
                condition=~models.Q(idempotency_key=''),
                name='stock_movement_key_required',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(reverses_movement__isnull=True)
                    | ~models.Q(pk=models.F('reverses_movement_id'))
                ),
                name='stock_movement_not_self_reversing',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tipo='CORRECTION', reverses_movement__isnull=False)
                    | (
                        ~models.Q(tipo='CORRECTION')
                        & models.Q(reverses_movement__isnull=True)
                    )
                ),
                name='stock_movement_correction_reference',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tipo__in=['OPENING_BALANCE', 'RECEIPT_IN'], delta__gt=0)
                    | models.Q(tipo='ORDER_SALE_OUT', delta__lt=0)
                    | models.Q(tipo__in=['MANUAL_ADJUSTMENT', 'CORRECTION'])
                ),
                name='stock_movement_fixed_type_sign',
            ),
            models.UniqueConstraint(
                fields=['reverses_movement'],
                condition=models.Q(reverses_movement__isnull=False),
                name='stock_movement_one_correction',
            ),
        ]
        indexes = [
            models.Index(
                fields=['producto', '-created_at'],
                name='stock_move_product_time_idx',
            ),
            models.Index(
                fields=['tipo', '-created_at'],
                name='stock_move_type_time_idx',
            ),
        ]

    def clean(self):
        errors = {}
        if self.delta == 0:
            errors['delta'] = 'El delta debe ser distinto de cero.'
        if not self.reason_code or not self.reason_code.strip():
            errors['reason_code'] = 'El motivo estructurado es obligatorio.'
        if not self.idempotency_key or not self.idempotency_key.strip():
            errors['idempotency_key'] = 'La clave de idempotencia es obligatoria.'
        if self.actor_kind == self.ActorKind.HUMAN and self.actor_id is None:
            errors['actor'] = 'Un movimiento humano requiere actor.'
        if self.actor_kind == self.ActorKind.SYSTEM and self.actor_id is not None:
            errors['actor'] = 'Un movimiento de sistema no admite actor humano.'
        if self.stock_before is not None and self.stock_before < 0:
            errors['stock_before'] = 'El saldo anterior no puede ser negativo.'
        if self.stock_after is not None and self.stock_after < 0:
            errors['stock_after'] = 'El saldo posterior no puede ser negativo.'
        if (
            self.stock_before is not None
            and self.stock_after is not None
            and self.delta is not None
            and self.stock_after != self.stock_before + self.delta
        ):
            errors['stock_after'] = 'El saldo posterior no coincide con el delta.'
        if self.tipo == self.Type.CORRECTION:
            if self.reverses_movement_id is None:
                errors['reverses_movement'] = (
                    'Una corrección debe referenciar el movimiento compensado.'
                )
            elif (
                self.producto_id is not None
                and self.reverses_movement.producto_id != self.producto_id
            ):
                errors['reverses_movement'] = (
                    'La corrección debe pertenecer al mismo Producto.'
                )
        elif self.reverses_movement_id is not None:
            errors['reverses_movement'] = (
                'Sólo una corrección puede referenciar otro movimiento.'
            )
        if self.tipo in {self.Type.OPENING_BALANCE, self.Type.RECEIPT_IN}:
            if self.delta is not None and self.delta <= 0:
                errors['delta'] = 'Este tipo requiere un delta positivo.'
        if self.tipo == self.Type.ORDER_SALE_OUT:
            if self.delta is not None and self.delta >= 0:
                errors['delta'] = 'Una salida por venta requiere un delta negativo.'
        if self.pk and self.reverses_movement_id == self.pk:
            errors['reverses_movement'] = (
                'Un movimiento no puede corregirse a sí mismo.'
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Un movimiento de stock persistido es inmutable.')
        if not getattr(self, '_allow_inventory_service_create', False):
            raise ValidationError(
                'Un movimiento de stock sólo puede crearse mediante inventario.'
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Un movimiento de stock no puede eliminarse.')

    def __str__(self):
        return f'{self.producto_id} {self.tipo} {self.delta:+d}'


class ImagenProducto(models.Model):
    """
    Modelo para gestionar múltiples imágenes por producto.
    Permite que un producto tenga varias imágenes.
    Redimensiona automáticamente las imágenes para optimizar espacio.
    """
    # Tamaño máximo de imagen redimensionada
    TAMAÑO_THUMBNAIL = (400, 400)  # Para thumbnails
    TAMAÑO_DISPLAY = (800, 800)    # Para display en galería
    
    producto = models.ForeignKey(
        'Producto',
        on_delete=models.CASCADE,
        related_name='imagenes',
        help_text="Producto al que pertenece esta imagen"
    )
    imagen = models.ImageField(
        upload_to='productos/',
        help_text="Imagen del producto"
    )
    orden = models.PositiveIntegerField(
        default=0,
        help_text="Orden de visualización (0 = principal)"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['orden', 'fecha_creacion']
        verbose_name_plural = "Imágenes de Productos"
    
    def __str__(self):
        return f"{self.producto.nombre} - Imagen {self.orden}"
    
    def save(self, *args, **kwargs):
        """Redimensiona la imagen antes de guardar para optimizar espacio"""
        super().save(*args, **kwargs)
        
        if self.imagen:
            from PIL import Image
            import os
            
            try:
                # Abrir la imagen
                img = Image.open(self.imagen.path)
                
                # Convertir RGBA a RGB si es necesario
                if img.mode in ('RGBA', 'LA', 'P'):
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = rgb_img
                
                # Redimensionar manteniendo proporción (máximo 800x800)
                img.thumbnail(self.TAMAÑO_DISPLAY, Image.Resampling.LANCZOS)
                
                # Guardar con compresión (calidad 85 para balance entre calidad y tamaño)
                img.save(self.imagen.path, 'JPEG', quality=85, optimize=True)
                
            except Exception as e:
                print(f"Error al redimensionar imagen: {e}")


class Promocion(models.Model):
    """
    Gestiona promociones del sistema en tres pilares:
    - COMBO: Combos de productos
    - RETOQUE: Packs de retoque/servicios
    - LAST_MINUTE: Promociones de último minuto
    """
    TIPO_CHOICES = [
        ('COMBO', 'Combo de Productos'),
        ('RETOQUE', 'Pack Retoque Servicio'),
        ('LAST_MINUTE', 'Promoción Last Minute'),
    ]

    nombre = models.CharField(
        max_length=100,
        help_text="Nombre de la promoción (ej: 'Combo Hidratación Profunda')"
    )
    descripcion = models.TextField(
        help_text="Descripción detallada de la promoción"
    )
    tipo = models.CharField(
        max_length=20, 
        choices=TIPO_CHOICES,
        help_text="Tipo de promoción"
    )
    descuento_porcentaje = models.IntegerField(
        default=10,
        help_text="Porcentaje de descuento aplicado"
    )
    stock_combo = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Stock disponible para combos (cantidad de combos armables)"
    )
    fecha_inicio = models.DateField(
        help_text="Fecha de inicio de la promoción"
    )
    fecha_fin = models.DateField(
        help_text="Fecha de finalización de la promoción"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Si está activa la promoción"
    )

    ES_SUGERENCIA_ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('ACEPTADA', 'Aceptada'),
        ('RECHAZADA', 'Rechazada'),
    ]

    es_sugerencia_automatica = models.BooleanField(
        default=False,
        help_text="Indica si la promoción fue sugerida automáticamente"
    )

    estado_sugerencia = models.CharField(
        max_length=20,
        choices=ES_SUGERENCIA_ESTADOS,
        default='ACEPTADA',
        help_text="Estado de revisión para sugerencias automáticas"
    )
    
    # Horario y Fecha Específica para promociones time-sensitive
    hora_inicio_promo = models.TimeField(
        null=True, 
        blank=True,
        help_text="Hora de inicio si la promoción es por horario específico"
    )
    hora_fin_promo = models.TimeField(
        null=True, 
        blank=True,
        help_text="Hora de fin si la promoción es por horario específico"
    )
    fecha_especifica = models.DateField(
        null=True, 
        blank=True,
        help_text="Fecha específica si la promoción aplica solo en un día concreto"
    )
    
    # Para el Pilar A (Combos)
    productos = models.ManyToManyField(
        'Producto', 
        blank=True,
        related_name='promociones',
        help_text="Productos incluidos en este combo"
    )
    
    # Para el Pilar B y C (Servicios)
    servicios = models.ManyToManyField(
        'Servicio', 
        blank=True,
        related_name='promociones',
        help_text="Servicios incluidos en este pack/promoción"
    )
    
    # Campos para Promociones Diferidas / Personalizadas por Cliente
    cliente_especifico = models.ForeignKey(
        'usuarios.Cliente', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='promociones_personalizadas',
        help_text="Si se especifica, esta promoción es solo para este cliente (ej: Mantenimiento post-servicio)"
    )
    fecha_envio_notificacion = models.DateField(
        null=True, 
        blank=True, 
        help_text="Día en que se enviará el aviso al cliente (para promociones diferidas)"
    )
    procesada = models.BooleanField(
        default=False, 
        help_text="Indica si la notificación ya fue enviada al cliente"
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Promoción"
        verbose_name_plural = "Promociones"
        ordering = ['-fecha_inicio']
        permissions = [
            ('manage_promotions', 'Can manage promotions'),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.nombre}"


class ConfiguracionRetoque(models.Model):
    """
    Configura los detalles del Pilar B (RETOQUE): 
    qué servicio principal requiere retoque, cuál es el servicio de retoque,
    cuántos días se recomienda y qué descuento ofrecer.
    """
    servicio_principal = models.ForeignKey(
        'Servicio', 
        on_delete=models.CASCADE, 
        related_name='config_retoques'
    )
    servicio_retoque = models.ForeignKey(
        'Servicio', 
        on_delete=models.CASCADE
    )
    dias_sugeridos = models.IntegerField(
        default=21, 
        help_text="Días recomendados para el retoque"
    )
    descuento_retoque = models.IntegerField(
        default=15, 
        help_text="Porcentaje de descuento si reserva ahora"
    )

    class Meta:
        verbose_name = "Configuración de Retoque"
        verbose_name_plural = "Configuraciones de Retoque"

    def __str__(self):
        return f"Retoque para {self.servicio_principal.nombre}"


class Carrito(models.Model):
    """
    Carrito de compras para un cliente.
    Permite acumular productos antes de proceder al pago.
    """
    cliente = models.OneToOneField(
        'usuarios.Cliente', 
        on_delete=models.CASCADE, 
        related_name='carrito',
        help_text="Cliente propietario del carrito"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Carrito de Compras"
        verbose_name_plural = "Carritos de Compras"
        ordering = ['-actualizado']

    def __str__(self):
        return f"Carrito de {self.cliente.usuario.email}"

    @property
    def total_carrito(self):
        """Calcula el total del carrito sumando subtotales de items."""
        return sum(item.subtotal for item in self.items.all())
    
    @property
    def cantidad_items(self):
        """Cuenta total de items en el carrito."""
        return self.items.aggregate(
            total=models.Sum('cantidad')
        )['total'] or 0


class CarritoItem(models.Model):
    """
    Item individual dentro de un carrito.
    Asocia un producto con una cantidad en el carrito.
    """
    carrito = models.ForeignKey(
        Carrito, 
        related_name='items', 
        on_delete=models.CASCADE,
        help_text="Carrito al que pertenece este item"
    )
    producto = models.ForeignKey(
        'Producto', 
        on_delete=models.CASCADE,
        help_text="Producto en el carrito"
    )
    cantidad = models.PositiveIntegerField(
        default=1,
        help_text="Cantidad del producto"
    )
    fecha_agregado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Item del Carrito"
        verbose_name_plural = "Items del Carrito"
        unique_together = ('carrito', 'producto')
        ordering = ['-fecha_agregado']

    def __str__(self):
        return f"{self.cantidad}x {self.producto.nombre} - Carrito {self.carrito.id}"

    @property
    def subtotal(self):
        """Calcula el subtotal para este item (precio × cantidad)."""
        return self.producto.precio * self.cantidad


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
        verbose_name="Puntaje (Lógica Diagnóstico)",
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
    
    servicio_sugerido = models.ForeignKey(
        'Servicio', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Servicio específico para este diagnóstico técnico."
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ['-prioridad']

    def __str__(self):
        return f"Regla (P:{self.prioridad}) -> {self.accion_resultado}"


class ConfiguracionDiagnostico(models.Model):
    """
    Configuracion global para mensajes y umbrales del nivel 2 del diagnostico.
    """
    umbral_critico = models.IntegerField(default=2)
    umbral_alerta = models.IntegerField(default=6)

    mensaje_critico = models.TextField(
        default=(
            "🔴 Diagnóstico Profesional: Tu cabello presenta un nivel de daño crítico. "
            "Con un score de {score}, la fibra capilar necesita atención inmediata."
        )
    )
    mensaje_alerta = models.TextField(
        default=(
            "🟡 Diagnóstico Profesional: Tu cabello requiere cuidado preventivo especializado. "
            "Con un score de {score}, está en estado de alerta."
        )
    )
    mensaje_saludable = models.TextField(
        default=(
            "🟢 Diagnóstico Profesional: ¡Buenas noticias! Tu cabello se encuentra en buen estado general. "
            "Con un score de {score}, te sugerimos mantener tu rutina actual."
        )
    )

    rutina_critico = models.ForeignKey(
        'Rutina',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='config_diagnostico_critico'
    )
    rutina_alerta = models.ForeignKey(
        'Rutina',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='config_diagnostico_alerta'
    )
    rutina_saludable = models.ForeignKey(
        'Rutina',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='config_diagnostico_saludable'
    )

    servicio_critico = models.ForeignKey(
        'Servicio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='config_diagnostico_critico'
    )
    servicio_alerta = models.ForeignKey(
        'Servicio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='config_diagnostico_alerta'
    )
    servicio_saludable = models.ForeignKey(
        'Servicio',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='config_diagnostico_saludable'
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Configuración de Diagnóstico"
        verbose_name_plural = "Configuraciones de Diagnóstico"

    @classmethod
    def get_singleton(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


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

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Rutina"
        verbose_name_plural = "Rutinas"
        ordering = ['-fecha_creacion']
        permissions = [
            ('assign_routines', 'Can assign routines'),
        ]

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

    history = HistoricalRecords()

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
    slot_hold_ttl_minutes = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
        help_text=(
            "Minutos de vigencia de una reserva temporal de agenda. "
            "No modifica HOLDs ya creados."
        ),
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

    # Adelanto automático de turnos cancelados
    adelanto_min_horas_anticipacion = models.IntegerField(
        default=24,
        help_text="Horas mínimas de anticipación para disparar la búsqueda de adelantos"
    )
    adelanto_rango_dias_busqueda = models.IntegerField(
        default=7,
        help_text="Días posteriores a considerar al buscar candidatos"
    )
    adelanto_max_candidatos = models.IntegerField(
        default=5,
        help_text="Máximo de clientes a notificar por cada cancelación"
    )
    adelanto_expira_horas = models.IntegerField(
        default=6,
        help_text="Horas de validez de la oferta de adelanto"
    )

    # WhatsApp - Contacto para Pedidos
    whatsapp_numero = models.CharField(
        max_length=20,
        default="5491122334455",
        verbose_name="Número de WhatsApp",
        help_text="Número completo con código de país (ej: 549112233445). Este es el número que recibe los pedidos."
    )

    # Identidad de la empresa
    empresa_nombre = models.CharField(
        max_length=150,
        default="Bohemia Hair",
        verbose_name="Nombre de la Empresa",
        help_text="Nombre comercial que se mostrará en reportes y comprobantes"
    )

    # Datos fiscales para comprobantes
    comprobante_razon_social = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="Razón Social",
        help_text="Razón social que se imprimirá en los comprobantes de pago"
    )
    comprobante_cuil = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="CUIL",
        help_text="CUIL que se imprimirá en los comprobantes de pago"
    )
    comprobante_fecha_inicio_actividad = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Inicio de Actividad",
        help_text="Fecha de inicio de actividad para comprobantes"
    )

    # Promociones - Combos
    promo_descuento_combo_x2 = models.IntegerField(
        default=10,
        help_text="Descuento porcentual para combos de 2 productos"
    )
    promo_descuento_combo_x3 = models.IntegerField(
        default=15,
        help_text="Descuento porcentual para combos de 3 productos"
    )

    combo_auto_activo = models.BooleanField(
        default=True,
        help_text="Habilita la creación automática de combos al cargar productos"
    )
    combo_min_similitud = models.IntegerField(
        default=2,
        help_text="Cantidad mínima de criterios coincidentes para armar un combo"
    )
    combo_max_productos = models.IntegerField(
        default=3,
        help_text="Máximo de productos por combo automático"
    )
    combo_min_stock = models.IntegerField(
        default=1,
        help_text="Stock mínimo disponible por producto para crear combos"
    )
    combo_dias_vigencia = models.IntegerField(
        default=15,
        help_text="Días de vigencia de un combo automático"
    )
    combo_usar_marca = models.BooleanField(
        default=True,
        help_text="Considerar marca para similitud"
    )
    combo_usar_proposito = models.BooleanField(
        default=True,
        help_text="Considerar propósito de uso para similitud"
    )
    combo_usar_material = models.BooleanField(
        default=False,
        help_text="Considerar material principal para similitud"
    )
    combo_usar_compatibilidad = models.BooleanField(
        default=True,
        help_text="Considerar compatibilidad capilar para similitud"
    )
    
    # Formato del Mensaje de WhatsApp
    whatsapp_saludo = models.CharField(
        max_length=200,
        default="¡Hola Bohemia Hair! 👋 Quiero realizar el siguiente pedido:",
        verbose_name="Saludo Inicial del Mensaje",
        help_text="Texto que aparece al inicio del mensaje de WhatsApp"
    )
    whatsapp_cierre = models.TextField(
        default="\n💰 *Total estimado: ${total}*\n\n¿Me confirman la disponibilidad y los detalles del envío?",
        verbose_name="Cierre del Mensaje",
        help_text="Texto final del mensaje. Usa {total} como variable para el monto"
    )
    whatsapp_formato_producto = models.CharField(
        max_length=300,
        default="• {nombre}\n  Cantidad: {cantidad} x ${precio:.2f} = ${subtotal:.2f}",
        verbose_name="Formato de Cada Producto",
        help_text="Cómo aparece cada producto. Variables disponibles: {nombre}, {cantidad}, {precio}, {subtotal}"
    )

    class Meta:
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuración"
        ordering = ['id']  # Elimina UnorderedObjectListWarning en paginación
        permissions = [
            ('manage_payment_configuration', 'Can manage payment configuration'),
            ('manage_configuration', 'Can manage configuration'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(slot_hold_ttl_minutes__gte=1)
                    & models.Q(slot_hold_ttl_minutes__lte=120)
                ),
                name='config_slot_hold_ttl_range',
            ),
        ]

    def save(self, *args, **kwargs):
        """
        Implementa patrón Singleton: siempre hay un solo record con pk=1.
        Aunque alguien intente crear otro, se sobrescribe automáticamente.
        """
        self.pk = 1
        super().save(*args, **kwargs)
        logger_config = logging.getLogger(__name__)
        logger_config.info(f"Configuración actualizada: intervalo={self.intervalo_turnos}, max_dias={self.max_dias_anticipacion}, whatsapp={self.whatsapp_numero}")

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

    history = HistoricalRecords()


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

    history = HistoricalRecords()

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
        SUGERIDO = 'sugerido', 'Sugerido (Recomendación)'
        REALIZADO = 'realizado', 'Realizado'
        CANCELADO = 'cancelado', 'Cancelado / Rechazado'
        AUSENTE = 'ausente', 'Ausente (No vino)'
        PENDIENTE = 'pendiente', 'Pendiente'
        EN_PROCESO = 'en_proceso', 'En Proceso'

    class CanalOrigen(models.TextChoices):
        WEB = 'web', 'Web (Cliente)'
        PRESENCIAL = 'presencial', 'Presencial (Profesional)'

    class TipoPagoRegistro(models.TextChoices):
        SENA = 'sena', 'Seña Parcial'
        TOTAL = 'total', 'Pago Total Anticipado'
        EFECTIVO = 'efectivo', 'Efectivo en Salón'
        TRANSFERENCIA = 'transferencia', 'Transferencia Directa'

    # Relaciones
    cliente = models.ForeignKey(
        'usuarios.Cliente', 
        on_delete=models.CASCADE, 
        related_name='mis_turnos'
    )
    profesional = models.ForeignKey(
        'gestion.Personal', 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='turnos_asignados'
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
    alerta_daño_capilar = models.BooleanField(
        default=False,
        help_text="Indica si el turno requiere revisión profesional por posible riesgo capilar."
    )
    canal_origen = models.CharField(
        max_length=20,
        choices=CanalOrigen.choices,
        default=CanalOrigen.WEB,
        help_text="Indica si el turno fue solicitado por la web o cargado presencialmente."
    )

    # Seña y pago
    fecha_limite_pago = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Fecha y hora máxima para recibir el comprobante"
    )
    tipo_pago_registro = models.CharField(
        max_length=20,
        choices=TipoPagoRegistro.choices,
        null=True,
        blank=True,
        help_text="Tipo de pago registrado para auditoría contable."
    )
    monto_abonado = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Monto abonado por el cliente para auditoría contable."
    )
    saldo_pendiente = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Saldo pendiente de pago asociado al turno."
    )
    
    # Auditoría
    comprobante_pago = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    cambios_realizados = models.IntegerField(default=0)
    
    # Información de cancelación
    cancelado_por = models.ForeignKey(
        'usuarios.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='turnos_cancelados',
        help_text="Usuario que canceló el turno (cliente o profesional)"
    )
    motivo_cancelacion = models.TextField(blank=True, null=True, help_text="Motivo de la cancelación")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Turno"
        verbose_name_plural = "Turnos"
        ordering = ['fecha', 'hora_inicio']
        unique_together = ['fecha', 'hora_inicio', 'cliente']
        permissions = [
            ('view_global_agenda', 'Can view the global agenda'),
            ('create_turno_for_client', 'Can create appointments for clients'),
            ('register_arrival', 'Can register client arrival'),
            ('reprogram_any_turno', 'Can reschedule any appointment'),
            ('cancel_any_turno', 'Can cancel any appointment'),
            ('finalize_service', 'Can finalize services'),
            ('confirm_deposit', 'Can confirm deposits'),
        ]

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

    history = HistoricalRecords()

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
    formula = models.TextField(blank=True, null=True)  # Aquí se guarda la fórmula ajustada
    observaciones_proceso = models.TextField(blank=True, null=True)
    comentario_cliente = models.TextField(blank=True, null=True)
    rutina_recomendada = models.ForeignKey(
        Rutina,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fichas_tecnicas_recomendadas'
    )
    
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
        permissions = [
            ('manage_technical_record', 'Can manage technical records'),
            ('manage_formulas', 'Can manage formulas'),
        ]


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
# SECCIÓN 5: CONTENIDO EDUCATIVO Y RED SOCIAL
# ============================================================

class ContenidoEducativo(models.Model):
    """
    Contenido educativo publicado por profesionales.
    Sistema similar a una red social pero enfocado en educación capilar.
    Los clientes pueden dar "me gusta" y guardar contenido.
    """
    ESTADOS = [
        ('BORRADOR', 'Borrador'),
        ('PUBLICADO', 'Publicado'),
        ('ARCHIVADO', 'Archivado'),
    ]
    TIPO_CONTENIDO = [
        ('IMAGEN', 'Imagen'),
        ('VIDEO', 'Video'),
        ('TEXTO', 'Solo Texto'),
    ]

    # Contenido
    titulo = models.CharField(max_length=200, help_text="Título del post educativo")
    descripcion = models.CharField(
        max_length=500, 
        help_text="Breve resumen para la lista de contenidos"
    )
    contenido_texto = models.TextField(help_text="Cuerpo completo del post educativo")
    multimedia_url = models.URLField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="Link a S3, YouTube, Cloudinary, etc."
    )
    tipo = models.CharField(
        max_length=10, 
        choices=TIPO_CONTENIDO, 
        default='IMAGEN',
        help_text="Tipo de contenido principal"
    )
    
    # Organización
    tags = models.CharField(
        max_length=200, 
        blank=True, 
        help_text="Etiquetas separadas por comas (ej: hidratacion,secado,color)"
    )
    
    # Relaciones y Control
    autor = models.ForeignKey(
        'Personal', 
        on_delete=models.PROTECT, 
        related_name='posts_educativos',
        help_text="Profesional que creó el contenido"
    )
    estado = models.CharField(
        max_length=20, 
        choices=ESTADOS, 
        default='BORRADOR',
        help_text="Estado de publicación del contenido"
    )
    activo = models.BooleanField(
        default=True,
        help_text="Soft delete - Marcar como inactivo para ocultar"
    )
    
    # Timestamps
    fecha_publicacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contenido Educativo"
        verbose_name_plural = "Contenidos Educativos"
        ordering = ['-fecha_publicacion']
        permissions = [
            ('manage_content', 'Can manage educational content'),
        ]
        indexes = [
            models.Index(fields=['estado', '-fecha_publicacion']),
            models.Index(fields=['autor', '-fecha_publicacion']),
        ]

    def clean(self):
        """Validar que tipo y multimedia_url sean coherentes."""
        if self.tipo != 'TEXTO' and not self.multimedia_url:
            raise ValidationError("Video e Imagen requieren URL de multimedia")
        if self.tipo == 'TEXTO' and self.multimedia_url:
            raise ValidationError("Contenido de Texto no debe tener multimedia")

    @property
    def total_likes(self):
        """Cantidad total de 'me gusta' recibidos."""
        return self.me_gusta_recibidos.count()

    @property
    def total_guardados(self):
        """Cantidad total de veces que fue guardado."""
        return self.guardados_recibidos.count()

    def me_gusta_por(self, cliente):
        """Verifica si un cliente específico likeó este contenido."""
        return self.me_gusta_recibidos.filter(cliente=cliente).exists()

    def es_guardado_por(self, cliente):
        """Verifica si un cliente específico guardó este contenido."""
        return self.guardados_recibidos.filter(cliente=cliente).exists()

    def __str__(self):
        return f"[{self.get_estado_display()}] {self.titulo}"


class MeGusta(models.Model):
    """
    Registra cuándo un cliente dio "me gusta" a un contenido educativo.
    Permite analytics: qué tipos de contenido les interesa más a los clientes.
    """
    contenido = models.ForeignKey(
        ContenidoEducativo, 
        on_delete=models.CASCADE, 
        related_name='me_gusta_recibidos',
        help_text="Contenido que recibió el like"
    )
    cliente = models.ForeignKey(
        'usuarios.Cliente', 
        on_delete=models.CASCADE,
        related_name='contenido_likeado',
        help_text="Cliente que dio el like"
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        help_text="Cuándo se dio el like (para analytics)"
    )

    class Meta:
        verbose_name = "Me Gusta"
        verbose_name_plural = "Me Gusta"
        unique_together = ('contenido', 'cliente')
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['cliente', '-fecha']),
            models.Index(fields=['contenido', '-fecha']),
        ]

    def __str__(self):
        return f"{self.cliente} likeó {self.contenido.titulo}"


class ContenidoGuardado(models.Model):
    """
    Registra cuándo un cliente guardó un contenido en su perfil.
    Permite que los clientes tengan un historial de contenidos favoritos.
    """
    contenido = models.ForeignKey(
        ContenidoEducativo, 
        on_delete=models.CASCADE, 
        related_name='guardados_recibidos',
        help_text="Contenido que fue guardado"
    )
    cliente = models.ForeignKey(
        'usuarios.Cliente', 
        on_delete=models.CASCADE,
        related_name='contenido_guardado',
        help_text="Cliente que guardó el contenido"
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        help_text="Cuándo se guardó (para analytics)"
    )

    class Meta:
        verbose_name = "Contenido Guardado"
        verbose_name_plural = "Contenidos Guardados"
        unique_together = ('contenido', 'cliente')
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['cliente', '-fecha']),
            models.Index(fields=['contenido', '-fecha']),
        ]

    def __str__(self):
        return f"{self.cliente} guardó {self.contenido.titulo}"


# ============================================================
# SECCIÓN 6: EQUIPAMIENTO Y NOTIFICACIONES
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

    def clean(self):
        """
        Validación: Asegurar que el tipo_equipamiento existe y está activo.
        """
        from django.core.exceptions import ValidationError
        
        if not self.tipo_equipamiento:
            raise ValidationError(
                'El tipo de equipamiento es obligatorio.'
            )
        
        # Verificar que el TipoEquipamiento existe
        if not TipoEquipamiento.objects.filter(id=self.tipo_equipamiento.id).exists():
            raise ValidationError(
                f'El tipo de equipamiento "{self.tipo_equipamiento.nombre}" no existe en el sistema.'
            )

    def __str__(self):
        return f"{self.servicio.nombre} requiere {self.tipo_equipamiento.nombre}"

class DiagnosticoCapilar(models.Model):
    """
    Registro de diagnóstico realizado a un cliente.
    Tabla maestra que guarda el histórico de evaluaciones del cabello.
    """
    class Procedencia(models.TextChoices):
        PROFESIONAL = 'PROFESIONAL', 'Profesional'
        AUTORREPORTE = 'AUTORREPORTE', 'Autorreporte'
        POST_SERVICIO_AUTOMATICO = (
            'POST_SERVICIO_AUTOMATICO',
            'Post-servicio automático',
        )
        MIGRADO = 'MIGRADO', 'Migrado'
        DESCONOCIDO = 'DESCONOCIDO', 'Desconocido'

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
    
    # Rutina sugerida como resultado (por Nivel 1 o Nivel 2)
    rutina_sugerida = models.ForeignKey(
        Rutina,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosticos_que_la_sugirieron'
    )
    
    # Servicio urgente (si diagnóstico es CRÍTICO, ≤5 puntos)
    servicio_urgente = models.ForeignKey(
        Servicio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosticos_urgentes',
        help_text="Servicio recomendado urgentemente si score ≤5"
    )

    turno_sugerido = models.ForeignKey(
        'Turno',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosticos_con_turno_sugerido',
        help_text="Turno sugerido generado por el motor de diagnostico"
    )
    
    # Rutina asignada al cliente (registro de quién ejecutó el motor)
    rutina_asignada = models.ForeignKey(
        Rutina,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diagnosticos_que_la_asignaron',
        help_text="Rutina efectivamente asignada al cliente"
    )
    
    fecha_diagnostico = models.DateTimeField(auto_now_add=True)
    procedencia = models.CharField(
        max_length=30,
        choices=Procedencia.choices,
        default=Procedencia.DESCONOCIDO,
    )

    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Diagnóstico Capilar"
        verbose_name_plural = "Diagnósticos Capilares"
        ordering = ['-fecha_diagnostico']
        permissions = [
            ('create_diagnosis', 'Can create diagnoses'),
        ]
    
    def __str__(self):
        return f"Diagnóstico {self.cliente} - {self.fecha_diagnostico.strftime('%d/%m/%Y')}"


class PoliticaRiesgoTecnico(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        PUBLICADA = 'PUBLICADA', 'Publicada'
        RETIRADA = 'RETIRADA', 'Retirada'

    version = models.CharField(max_length=50, unique=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )
    creada_at = models.DateTimeField(auto_now_add=True)
    publicada_at = models.DateTimeField(null=True, blank=True)
    publicada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='politicas_riesgo_publicadas',
    )

    class Meta:
        verbose_name = 'Política de riesgo técnico'
        verbose_name_plural = 'Políticas de riesgo técnico'
        ordering = ['-creada_at']
        permissions = [
            (
                'manage_technical_risk_policy',
                'Can manage technical risk policies',
            ),
        ]

    def save(self, *args, **kwargs):
        allow_publication = getattr(self, '_allow_explicit_publication', False)
        if not self.pk and self.estado != self.Estado.BORRADOR:
            raise ValidationError(
                'Toda política debe crearse como borrador y publicarse explícitamente.'
            )
        if self.pk:
            current = type(self).objects.filter(pk=self.pk).first()
            if current is not None:
                if current.estado == self.Estado.PUBLICADA:
                    raise ValidationError(
                        'Una política publicada es inmutable.'
                    )
                if current.version != self.version:
                    raise ValidationError(
                        'La versión de una política no puede modificarse.'
                    )
                if (
                    self.estado == self.Estado.PUBLICADA
                    and current.estado != self.Estado.PUBLICADA
                    and not allow_publication
                ):
                    raise ValidationError(
                        'La publicación sólo puede realizarse mediante el servicio explícito.'
                    )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.estado == self.Estado.PUBLICADA:
            raise ValidationError('Una política publicada no puede eliminarse.')
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f'Política técnica {self.version} ({self.estado})'


class ReglaRiesgoTecnicoBase(models.Model):
    code = models.CharField(max_length=80)
    severidad = models.PositiveSmallIntegerField(default=0)
    prioridad = models.IntegerField(default=0)
    mensaje_cliente = models.TextField(blank=True)
    mensaje_profesional = models.TextField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def _ensure_draft_policy(self):
        if self.pk:
            original_policy_id = type(self).objects.values_list(
                'politica_id', flat=True
            ).get(pk=self.pk)
            if original_policy_id != self.politica_id:
                raise ValidationError('Una regla no puede moverse a otra política.')
        else:
            original_policy_id = self.politica_id
        policy_state = PoliticaRiesgoTecnico.objects.values_list(
            'estado', flat=True
        ).get(pk=original_policy_id)
        if policy_state != PoliticaRiesgoTecnico.Estado.BORRADOR:
            raise ValidationError(
                'Las reglas de una política publicada o retirada son inmutables.'
            )

    def save(self, *args, **kwargs):
        self._ensure_draft_policy()
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._ensure_draft_policy()
        return super().delete(*args, **kwargs)


class ReglaIntervaloTecnico(ReglaRiesgoTecnicoBase):
    politica = models.ForeignKey(
        PoliticaRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='reglas_intervalo',
    )
    servicio_origen = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='reglas_intervalo_como_origen',
        null=True,
        blank=True,
    )
    familia_origen = models.ForeignKey(
        FamiliaProcesoTecnico,
        on_delete=models.PROTECT,
        related_name='reglas_intervalo_como_origen',
        null=True,
        blank=True,
    )
    servicio_destino = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='reglas_intervalo_como_destino',
        null=True,
        blank=True,
    )
    familia_destino = models.ForeignKey(
        FamiliaProcesoTecnico,
        on_delete=models.PROTECT,
        related_name='reglas_intervalo_como_destino',
        null=True,
        blank=True,
    )
    dias_minimos = models.PositiveIntegerField()
    outcome = models.CharField(
        max_length=25,
        choices=TechnicalRiskOutcome.choices,
    )

    class Meta:
        verbose_name = 'Regla de intervalo técnico'
        verbose_name_plural = 'Reglas de intervalo técnico'
        constraints = [
            models.UniqueConstraint(
                fields=['politica', 'code'],
                name='unique_interval_rule_code_per_policy',
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(servicio_origen__isnull=False)
                        & models.Q(familia_origen__isnull=True)
                    )
                    | (
                        models.Q(servicio_origen__isnull=True)
                        & models.Q(familia_origen__isnull=False)
                    )
                ),
                name='interval_rule_exactly_one_origin',
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(servicio_destino__isnull=False)
                        & models.Q(familia_destino__isnull=True)
                    )
                    | (
                        models.Q(servicio_destino__isnull=True)
                        & models.Q(familia_destino__isnull=False)
                    )
                ),
                name='interval_rule_exactly_one_destination',
            ),
        ]


class ReglaDiagnosticoTecnico(ReglaRiesgoTecnicoBase):
    politica = models.ForeignKey(
        PoliticaRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='reglas_diagnostico_tecnico',
    )
    servicio_destino = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='reglas_diagnostico_tecnico',
        null=True,
        blank=True,
    )
    familia_destino = models.ForeignKey(
        FamiliaProcesoTecnico,
        on_delete=models.PROTECT,
        related_name='reglas_diagnostico_tecnico',
        null=True,
        blank=True,
    )
    requiere_diagnostico = models.BooleanField(default=True)
    antiguedad_maxima_dias = models.PositiveIntegerField(null=True, blank=True)
    outcome_si_falta = models.CharField(
        max_length=25,
        choices=TechnicalRiskOutcome.choices,
        default=TechnicalRiskOutcome.REQUIERE_REVISION,
    )
    outcome_si_vencido = models.CharField(
        max_length=25,
        choices=TechnicalRiskOutcome.choices,
        default=TechnicalRiskOutcome.REQUIERE_REVISION,
    )
    outcome_si_incompleto = models.CharField(
        max_length=25,
        choices=TechnicalRiskOutcome.choices,
        default=TechnicalRiskOutcome.REQUIERE_REVISION,
    )
    outcome_si_procedencia_no_confiable = models.CharField(
        max_length=25,
        choices=TechnicalRiskOutcome.choices,
        default=TechnicalRiskOutcome.REQUIERE_REVISION,
    )

    class Meta:
        verbose_name = 'Regla de diagnóstico técnico'
        verbose_name_plural = 'Reglas de diagnóstico técnico'
        constraints = [
            models.UniqueConstraint(
                fields=['politica', 'code'],
                name='unique_diagnosis_rule_code_per_policy',
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(servicio_destino__isnull=False)
                        & models.Q(familia_destino__isnull=True)
                    )
                    | (
                        models.Q(servicio_destino__isnull=True)
                        & models.Q(familia_destino__isnull=False)
                    )
                ),
                name='diagnosis_rule_exactly_one_destination',
            ),
        ]


class ReglaFrecuenciaTecnica(ReglaRiesgoTecnicoBase):
    politica = models.ForeignKey(
        PoliticaRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='reglas_frecuencia',
    )
    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='reglas_frecuencia_tecnica',
        null=True,
        blank=True,
    )
    familia = models.ForeignKey(
        FamiliaProcesoTecnico,
        on_delete=models.PROTECT,
        related_name='reglas_frecuencia_tecnica',
        null=True,
        blank=True,
    )
    ventana_dias = models.PositiveIntegerField()
    cantidad_maxima = models.PositiveIntegerField()
    outcome = models.CharField(
        max_length=25,
        choices=TechnicalRiskOutcome.choices,
    )

    class Meta:
        verbose_name = 'Regla de frecuencia técnica'
        verbose_name_plural = 'Reglas de frecuencia técnica'
        constraints = [
            models.UniqueConstraint(
                fields=['politica', 'code'],
                name='unique_frequency_rule_code_per_policy',
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(servicio__isnull=False)
                        & models.Q(familia__isnull=True)
                    )
                    | (
                        models.Q(servicio__isnull=True)
                        & models.Q(familia__isnull=False)
                    )
                ),
                name='frequency_rule_exactly_one_selector',
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad_maxima__gte=1),
                name='frequency_rule_positive_maximum',
            ),
            models.CheckConstraint(
                condition=models.Q(ventana_dias__gte=1),
                name='frequency_rule_positive_window',
            ),
        ]


class ImmutableTechnicalRiskEvaluationQuerySet(models.QuerySet):
    immutable_error = 'Las evaluaciones de riesgo técnico son inmutables.'

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(
            'La creación masiva de evaluaciones de riesgo técnico no está '
            'permitida; use el servicio de persistencia auditado.'
        )

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(
            'update_or_create no está permitido para evaluaciones de riesgo '
            'técnico inmutables.'
        )


class ImmutableTechnicalRiskEvaluationManager(
    models.Manager.from_queryset(ImmutableTechnicalRiskEvaluationQuerySet)
):
    def _set_superseded_by(self, *, evaluation_id, replacement_id):
        """Ruta interna acotada; las reglas y auditoría viven en el servicio."""
        queryset = self.get_queryset().filter(
            pk=evaluation_id,
            superseded_by__isnull=True,
        )
        return models.QuerySet.update(
            queryset,
            superseded_by_id=replacement_id,
        )


class EvaluacionRiesgoTecnico(models.Model):
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.PROTECT,
        related_name='evaluaciones_riesgo_tecnico',
    )
    politica = models.ForeignKey(
        PoliticaRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='evaluaciones',
    )
    outcome = models.CharField(
        max_length=25,
        choices=TechnicalRiskOutcome.choices,
    )
    severity = models.PositiveSmallIntegerField(default=0)
    fecha_solicitada = models.DateField()
    evaluated_at = models.DateTimeField(auto_now_add=True)
    input_snapshot = models.JSONField()
    result_snapshot = models.JSONField()
    superseded_by = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='evaluaciones_superadas',
    )
    objects = ImmutableTechnicalRiskEvaluationManager()

    class Meta:
        verbose_name = 'Evaluación de riesgo técnico'
        verbose_name_plural = 'Evaluaciones de riesgo técnico'
        ordering = ['-evaluated_at']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        permissions = [
            (
                'review_technical_booking',
                'Can review technical bookings',
            ),
        ]

    def clean(self):
        errors = {}
        if not isinstance(self.input_snapshot, dict):
            errors['input_snapshot'] = 'Debe ser un objeto JSON.'
        elif not {'cliente_id', 'servicios', 'fecha_solicitada'} <= set(
            self.input_snapshot
        ):
            errors['input_snapshot'] = 'El snapshot de entrada está incompleto.'
        if not isinstance(self.result_snapshot, dict):
            errors['result_snapshot'] = 'Debe ser un objeto JSON.'
        elif not {'outcome', 'policy_version', 'rule_codes'} <= set(
            self.result_snapshot
        ):
            errors['result_snapshot'] = 'El snapshot de resultado está incompleto.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                'Una evaluación de riesgo técnico persistida es inmutable.'
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            'Una evaluación de riesgo técnico persistida no puede eliminarse.'
        )


class SolicitudTecnicaReserva(models.Model):
    class Estado(models.TextChoices):
        EVALUANDO = 'EVALUANDO', 'Evaluando'
        ADVERTENCIA_PENDIENTE = (
            'ADVERTENCIA_PENDIENTE',
            'Advertencia pendiente',
        )
        APROBADA_TECNICAMENTE = (
            'APROBADA_TECNICAMENTE',
            'Aprobada técnicamente',
        )
        EN_REVISION = 'EN_REVISION', 'En revisión'
        INFORMACION_REQUERIDA = (
            'INFORMACION_REQUERIDA',
            'Información requerida',
        )
        RECHAZADA_TECNICAMENTE = (
            'RECHAZADA_TECNICAMENTE',
            'Rechazada técnicamente',
        )
        SUPERADA = 'SUPERADA', 'Superada'
        VENCIDA = 'VENCIDA', 'Vencida'

    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.PROTECT,
        related_name='solicitudes_tecnicas',
    )
    fecha_preferida = models.DateField()
    hora_preferida = models.TimeField()
    personal_preferido = models.ForeignKey(
        Personal,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='solicitudes_tecnicas_preferidas',
    )
    servicios = models.ManyToManyField(
        Servicio,
        through='SolicitudTecnicaServicio',
        related_name='solicitudes_tecnicas',
    )
    estado = models.CharField(
        max_length=30,
        choices=Estado.choices,
        default=Estado.EVALUANDO,
    )
    intento = models.PositiveIntegerField(default=1)
    evaluacion_vigente = models.OneToOneField(
        EvaluacionRiesgoTecnico,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='solicitud_tecnica_vigente',
    )
    fecha_recomendada = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Solicitud técnica de reserva'
        verbose_name_plural = 'Solicitudes técnicas de reserva'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cliente', '-created_at']),
            models.Index(fields=['estado', '-created_at']),
        ]


class SolicitudTecnicaServicio(models.Model):
    solicitud = models.ForeignKey(
        SolicitudTecnicaReserva,
        on_delete=models.CASCADE,
        related_name='servicios_solicitados',
    )
    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='intenciones_tecnicas',
    )
    orden = models.PositiveSmallIntegerField(default=0)
    nombre_snapshot = models.CharField(max_length=100)

    class Meta:
        ordering = ['orden', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['solicitud', 'servicio'],
                name='unique_service_per_technical_request',
            ),
        ]


class SlotHold(models.Model):
    """Reserva temporal persistida de recursos de agenda."""

    class State(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activo'
        CONSUMED = 'CONSUMED', 'Consumido'
        RELEASED = 'RELEASED', 'Liberado'
        EXPIRED = 'EXPIRED', 'Vencido'

    class ReleaseReason(models.TextChoices):
        CLIENT_CANCELLED = 'CLIENT_CANCELLED', 'Cancelado por el Cliente'
        TTL_EXPIRED = 'TTL_EXPIRED', 'Vencimiento del tiempo de reserva'
        TECHNICAL_REQUEST_INVALIDATED = (
            'TECHNICAL_REQUEST_INVALIDATED',
            'Solicitud técnica invalidada',
        )
        RESOURCE_INVALIDATED = 'RESOURCE_INVALIDATED', 'Recurso invalidado'
        PAYMENT_INTENT_CANCELLED = (
            'PAYMENT_INTENT_CANCELLED',
            'Intento de pago cancelado',
        )
        PAYMENT_INTENT_EXPIRED = (
            'PAYMENT_INTENT_EXPIRED',
            'Intento de pago vencido',
        )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    solicitud = models.ForeignKey(
        SolicitudTecnicaReserva,
        on_delete=models.PROTECT,
        related_name='slot_holds',
    )
    evaluacion = models.ForeignKey(
        EvaluacionRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='slot_holds',
    )
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.PROTECT,
        related_name='slot_holds',
    )
    personal = models.ForeignKey(
        Personal,
        on_delete=models.PROTECT,
        related_name='slot_holds',
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    state = models.CharField(
        max_length=10,
        choices=State.choices,
        default=State.ACTIVE,
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='slot_holds_created',
    )
    consumed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(
        max_length=40,
        choices=ReleaseReason.choices,
        blank=True,
        default='',
    )
    consumed_turno = models.OneToOneField(
        Turno,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='consumed_slot_hold',
    )
    idempotency_key = models.CharField(max_length=128, unique=True)
    consumption_idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(starts_at__lt=models.F('ends_at')),
                name='slot_hold_valid_interval',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(created_at__lt=models.F('expires_at'))
                    & models.Q(expires_at__lte=models.F('starts_at'))
                ),
                name='slot_hold_valid_expiry',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        state='ACTIVE',
                        consumed_at__isnull=True,
                        released_at__isnull=True,
                        expired_at__isnull=True,
                        consumed_turno__isnull=True,
                        consumption_idempotency_key__isnull=True,
                        release_reason='',
                    )
                    | models.Q(
                        state='CONSUMED',
                        consumed_at__isnull=False,
                        released_at__isnull=True,
                        expired_at__isnull=True,
                        consumed_turno__isnull=False,
                        consumption_idempotency_key__isnull=False,
                        release_reason='',
                    )
                    | (
                        models.Q(
                            state='RELEASED',
                            consumed_at__isnull=True,
                            released_at__isnull=False,
                            expired_at__isnull=True,
                            consumed_turno__isnull=True,
                            consumption_idempotency_key__isnull=True,
                        )
                        & ~models.Q(release_reason='')
                    )
                    | (
                        models.Q(
                            state='EXPIRED',
                            consumed_at__isnull=True,
                            released_at__isnull=True,
                            expired_at__isnull=False,
                            consumed_turno__isnull=True,
                            consumption_idempotency_key__isnull=True,
                        )
                        & ~models.Q(release_reason='')
                    )
                ),
                name='slot_hold_state_timestamps_ok',
            ),
            models.UniqueConstraint(
                fields=['solicitud'],
                condition=models.Q(state='ACTIVE'),
                name='slot_hold_one_active_request',
            ),
            models.UniqueConstraint(
                fields=['solicitud'],
                condition=models.Q(state='CONSUMED'),
                name='slot_hold_one_consumed_req',
            ),
        ]
        indexes = [
            models.Index(
                fields=['state', 'expires_at'],
                name='slot_hold_state_exp_idx',
            ),
            models.Index(
                fields=['personal', 'starts_at', 'ends_at'],
                name='slot_hold_person_time_idx',
            ),
            models.Index(
                fields=['cliente', 'starts_at', 'ends_at'],
                name='slot_hold_client_time_idx',
            ),
        ]


class SlotHoldService(models.Model):
    hold = models.ForeignKey(
        SlotHold,
        on_delete=models.CASCADE,
        related_name='service_snapshots',
    )
    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='slot_hold_snapshots',
    )
    orden = models.PositiveSmallIntegerField()
    nombre_snapshot = models.CharField(max_length=100)
    duracion_minutos_snapshot = models.PositiveIntegerField()

    class Meta:
        ordering = ['orden', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['hold', 'servicio'],
                name='slot_hold_service_unique',
            ),
        ]


class SlotHoldEquipmentRequirement(models.Model):
    hold = models.ForeignKey(
        SlotHold,
        on_delete=models.CASCADE,
        related_name='equipment_requirements',
    )
    tipo_equipamiento = models.ForeignKey(
        TipoEquipamiento,
        on_delete=models.PROTECT,
        related_name='slot_hold_requirements',
    )
    cantidad_snapshot = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['hold', 'tipo_equipamiento'],
                name='slot_hold_equipment_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad_snapshot__gte=1),
                name='slot_hold_equipment_positive',
            ),
        ]
        indexes = [
            models.Index(
                fields=['tipo_equipamiento', 'hold'],
                name='slot_hold_equipment_idx',
            ),
        ]


class PaymentPolicyQuerySet(models.QuerySet):
    immutable_error = 'Una política de pago publicada o retirada es inmutable.'

    def update(self, **kwargs):
        if 'version' in kwargs:
            raise ValidationError(
                'La versión de una política de pago no puede modificarse.'
            )
        if 'status' in kwargs and kwargs['status'] != 'DRAFT':
            raise ValidationError(
                'La publicación sólo puede realizarse mediante el servicio.'
            )
        if self.exclude(status='DRAFT').exists():
            raise ValidationError(self.immutable_error)
        return super().update(**kwargs)

    def delete(self):
        if self.exclude(status='DRAFT').exists():
            raise ValidationError(self.immutable_error)
        return super().delete()

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            'bulk_update no está permitido para políticas de pago.'
        )

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(
            'bulk_create no está permitido para políticas de pago.'
        )

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(
            'update_or_create no está permitido para políticas de pago.'
        )


class PaymentPolicyManager(models.Manager.from_queryset(PaymentPolicyQuerySet)):
    def _retire_published(self, *, exclude_id=None):
        queryset = self.get_queryset().filter(status='PUBLISHED')
        if exclude_id is not None:
            queryset = queryset.exclude(pk=exclude_id)
        return models.QuerySet.update(queryset, status='RETIRED')


class PaymentPolicy(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        PUBLISHED = 'PUBLISHED', 'Publicada'
        RETIRED = 'RETIRED', 'Retirada'

    class AllowedMode(models.TextChoices):
        DEPOSIT_ONLY = 'DEPOSIT_ONLY', 'Sólo seña'
        FULL_ONLY = 'FULL_ONLY', 'Sólo total'
        DEPOSIT_OR_FULL = 'DEPOSIT_OR_FULL', 'Seña o total'

    class DepositKind(models.TextChoices):
        FIXED = 'FIXED', 'Monto fijo'
        PERCENTAGE = 'PERCENTAGE', 'Porcentaje'

    class FixedExceedsTotalBehavior(models.TextChoices):
        REJECT = 'REJECT', 'Rechazar'
        CAP_TO_TOTAL = 'CAP_TO_TOTAL', 'Limitar al total'

    version = models.CharField(max_length=50, unique=True)
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    allowed_mode = models.CharField(max_length=20, choices=AllowedMode.choices)
    deposit_kind = models.CharField(
        max_length=15,
        choices=DepositKind.choices,
        null=True,
        blank=True,
    )
    deposit_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fixed_exceeds_total_behavior = models.CharField(
        max_length=15,
        choices=FixedExceedsTotalBehavior.choices,
        null=True,
        blank=True,
    )
    currency = models.CharField(
        max_length=3,
        choices=PAYMENT_CURRENCY_CHOICES,
    )
    intent_ttl_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )
    enabled_manual_methods = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payment_policies_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    objects = PaymentPolicyManager()

    class Meta:
        ordering = ['-created_at']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [
            models.UniqueConstraint(
                fields=['status'],
                condition=models.Q(status='PUBLISHED'),
                name='payment_policy_one_published',
            ),
            models.CheckConstraint(
                condition=models.Q(intent_ttl_minutes__gte=1),
                name='payment_policy_positive_ttl',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        allowed_mode='FULL_ONLY',
                        deposit_kind__isnull=True,
                        deposit_value__isnull=True,
                        fixed_exceeds_total_behavior__isnull=True,
                    )
                    | models.Q(
                        allowed_mode__in=['DEPOSIT_ONLY', 'DEPOSIT_OR_FULL'],
                        deposit_kind='PERCENTAGE',
                        deposit_value__gt=0,
                        deposit_value__lte=100,
                        fixed_exceeds_total_behavior__isnull=True,
                    )
                    | models.Q(
                        allowed_mode__in=['DEPOSIT_ONLY', 'DEPOSIT_OR_FULL'],
                        deposit_kind='FIXED',
                        deposit_value__gt=0,
                        fixed_exceeds_total_behavior__isnull=False,
                    )
                ),
                name='payment_policy_deposit_configuration',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status='DRAFT', published_at__isnull=True)
                    | models.Q(
                        status__in=['PUBLISHED', 'RETIRED'],
                        published_at__isnull=False,
                    )
                ),
                name='payment_policy_publication_timestamp',
            ),
        ]

    def clean(self):
        errors = {}
        if self.allowed_mode == self.AllowedMode.FULL_ONLY:
            if any(
                value is not None
                for value in (
                    self.deposit_kind,
                    self.deposit_value,
                    self.fixed_exceeds_total_behavior,
                )
            ):
                errors['allowed_mode'] = (
                    'FULL_ONLY no admite configuración de seña.'
                )
        elif self.deposit_kind == self.DepositKind.PERCENTAGE:
            if self.deposit_value is None or not (0 < self.deposit_value <= 100):
                errors['deposit_value'] = (
                    'El porcentaje debe ser mayor que cero y no superar 100.'
                )
            if self.fixed_exceeds_total_behavior is not None:
                errors['fixed_exceeds_total_behavior'] = (
                    'El comportamiento de monto fijo no aplica a porcentajes.'
                )
        elif self.deposit_kind == self.DepositKind.FIXED:
            if self.deposit_value is None or self.deposit_value <= 0:
                errors['deposit_value'] = 'El monto fijo debe ser mayor que cero.'
            if self.fixed_exceeds_total_behavior is None:
                errors['fixed_exceeds_total_behavior'] = (
                    'Debe definir el comportamiento si el fijo supera el total.'
                )
        else:
            errors['deposit_kind'] = (
                'Una política que admite seña requiere un tipo de seña.'
            )
        if self.currency not in PAYMENT_CURRENCY_MINOR_UNITS:
            errors['currency'] = 'La moneda no está soportada.'
        methods = self.enabled_manual_methods
        if not isinstance(methods, list):
            errors['enabled_manual_methods'] = 'Debe ser una lista.'
        else:
            invalid = set(methods) - set(MANUAL_PAYMENT_METHODS)
            if invalid or len(methods) != len(set(methods)):
                errors['enabled_manual_methods'] = (
                    'Los medios manuales deben ser válidos y no repetirse.'
                )
            else:
                self.enabled_manual_methods = sorted(methods)
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        allow_publication = getattr(self, '_allow_publication_transition', False)
        if not self.pk and self.status != self.Status.DRAFT:
            raise ValidationError(
                'Toda política de pago debe crearse como borrador.'
            )
        if self.pk:
            current = type(self).objects.filter(pk=self.pk).first()
            if current is not None:
                if current.version != self.version:
                    raise ValidationError(
                        'La versión de una política de pago no puede modificarse.'
                    )
                if current.status != self.Status.DRAFT:
                    raise ValidationError(
                        'Una política de pago publicada o retirada es inmutable.'
                    )
                if (
                    self.status == self.Status.PUBLISHED
                    and not allow_publication
                ):
                    raise ValidationError(
                        'La publicación sólo puede realizarse mediante el servicio.'
                    )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.Status.DRAFT:
            raise ValidationError(
                'Una política de pago publicada o retirada no puede eliminarse.'
            )
        return super().delete(*args, **kwargs)


class ImmutablePaymentIntentQuerySet(models.QuerySet):
    immutable_error = 'Los PaymentIntent son inmutables fuera de sus servicios.'

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(
            'La creación masiva de PaymentIntent no está permitida.'
        )

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(self.immutable_error)


class PaymentIntentManager(
    models.Manager.from_queryset(ImmutablePaymentIntentQuerySet)
):
    def _create_from_service(self, **values):
        intent = self.model(**values)
        intent._allow_service_create = True
        intent.save(force_insert=True, using=self.db)
        return intent

    def _transition(self, *, intent_id, from_statuses, **values):
        queryset = self.get_queryset().filter(
            pk=intent_id,
            status__in=from_statuses,
        )
        return models.QuerySet.update(queryset, **values)


class PaymentIntent(models.Model):
    class Mode(models.TextChoices):
        DEPOSIT = 'DEPOSIT', 'Seña'
        FULL = 'FULL', 'Total'

    class Status(models.TextChoices):
        CREATED = 'CREATED', 'Creado'
        PENDING = 'PENDING', 'Pendiente'
        APPROVED = 'APPROVED', 'Aprobado'
        REJECTED = 'REJECTED', 'Rechazado'
        EXPIRED = 'EXPIRED', 'Vencido'
        CANCELLED = 'CANCELLED', 'Cancelado'

    ACTIVE_STATUSES = (Status.CREATED, Status.PENDING)
    TERMINAL_FAILURE_STATUSES = (
        Status.REJECTED,
        Status.EXPIRED,
        Status.CANCELLED,
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    solicitud = models.ForeignKey(
        SolicitudTecnicaReserva,
        on_delete=models.PROTECT,
        related_name='payment_intents',
    )
    slot_hold = models.ForeignKey(
        SlotHold,
        on_delete=models.PROTECT,
        related_name='payment_intents',
    )
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.PROTECT,
        related_name='payment_intents',
    )
    policy = models.ForeignKey(
        PaymentPolicy,
        on_delete=models.PROTECT,
        related_name='payment_intents',
    )
    policy_snapshot = models.JSONField()
    mode = models.CharField(max_length=10, choices=Mode.choices)
    total_amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    required_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=PAYMENT_CURRENCY_CHOICES)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.CREATED,
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    pending_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    terminal_at = models.DateTimeField(null=True, blank=True)
    terminal_reason = models.CharField(max_length=50, blank=True, default='')
    idempotency_key = models.CharField(max_length=128, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payment_intents_created',
    )
    confirmed_turno = models.OneToOneField(
        'Turno',
        on_delete=models.PROTECT,
        related_name='payment_intent',
        null=True,
        blank=True,
    )
    confirmation_operation_key = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
    )
    objects = PaymentIntentManager()

    class Meta:
        ordering = ['-created_at']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [
            models.UniqueConstraint(
                fields=['slot_hold'],
                condition=models.Q(status__in=['CREATED', 'PENDING']),
                name='payment_intent_one_active_hold',
            ),
            models.UniqueConstraint(
                fields=['slot_hold'],
                condition=models.Q(status='APPROVED'),
                name='payment_intent_one_approved_hold',
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount_snapshot__gt=0),
                name='payment_intent_positive_total',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(required_amount__gt=0)
                    & models.Q(
                        required_amount__lte=models.F('total_amount_snapshot')
                    )
                ),
                name='payment_intent_valid_required',
            ),
            models.CheckConstraint(
                condition=models.Q(created_at__lt=models.F('expires_at')),
                name='payment_intent_valid_expiry',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status='CREATED',
                        pending_at__isnull=True,
                        approved_at__isnull=True,
                        terminal_at__isnull=True,
                        terminal_reason='',
                    )
                    | models.Q(
                        status='PENDING',
                        pending_at__isnull=False,
                        approved_at__isnull=True,
                        terminal_at__isnull=True,
                        terminal_reason='',
                    )
                    | models.Q(
                        status='APPROVED',
                        approved_at__isnull=False,
                        terminal_at__isnull=True,
                        terminal_reason='',
                    )
                    | (
                        models.Q(
                            status__in=['REJECTED', 'EXPIRED', 'CANCELLED'],
                            approved_at__isnull=True,
                            terminal_at__isnull=False,
                        )
                        & ~models.Q(terminal_reason='')
                    )
                ),
                name='payment_intent_status_timestamps',
            ),
        ]
        indexes = [
            models.Index(
                fields=['status', 'expires_at'],
                name='payment_intent_status_exp_idx',
            ),
            models.Index(
                fields=['cliente', '-created_at'],
                name='payment_intent_client_idx',
            ),
        ]

    def clean(self):
        errors = {}
        if self.solicitud_id and self.slot_hold_id:
            if self.slot_hold.solicitud_id != self.solicitud_id:
                errors['solicitud'] = 'La solicitud no coincide con el HOLD.'
        if self.cliente_id and self.slot_hold_id:
            if self.slot_hold.cliente_id != self.cliente_id:
                errors['cliente'] = 'El Cliente no coincide con el HOLD.'
        if self.policy_id and self.currency != self.policy.currency:
            errors['currency'] = 'La moneda no coincide con la política.'
        if not isinstance(self.policy_snapshot, dict):
            errors['policy_snapshot'] = 'Debe ser un objeto JSON.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self._state.adding and not getattr(
            self,
            '_allow_service_create',
            False,
        ):
            raise ValidationError(
                'Un PaymentIntent sólo puede crearse mediante su servicio.'
            )
        if not self._state.adding:
            raise ValidationError(
                'Un PaymentIntent persistido sólo cambia mediante servicios.'
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Un PaymentIntent no puede eliminarse.')


class ImmutablePaymentIntentLineQuerySet(models.QuerySet):
    immutable_error = 'Las líneas de PaymentIntent son inmutables.'

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(self.immutable_error)

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(self.immutable_error)


class PaymentIntentLineManager(
    models.Manager.from_queryset(ImmutablePaymentIntentLineQuerySet)
):
    def _create_from_service(self, **values):
        line = self.model(**values)
        line._allow_service_create = True
        line.save(force_insert=True, using=self.db)
        return line


class PaymentIntentLine(models.Model):
    intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.PROTECT,
        related_name='lines',
    )
    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='payment_intent_lines',
    )
    orden = models.PositiveSmallIntegerField()
    nombre_snapshot = models.CharField(max_length=100)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    moneda = models.CharField(max_length=3, choices=PAYMENT_CURRENCY_CHOICES)
    objects = PaymentIntentLineManager()

    class Meta:
        ordering = ['orden', 'pk']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [
            models.UniqueConstraint(
                fields=['intent', 'orden'],
                name='payment_intent_line_unique_order',
            ),
            models.UniqueConstraint(
                fields=['intent', 'servicio'],
                name='payment_intent_line_unique_service',
            ),
            models.CheckConstraint(
                condition=models.Q(cantidad__gte=1),
                name='payment_intent_line_positive_quantity',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(precio_unitario_snapshot__gte=0)
                    & models.Q(descuento__gte=0)
                    & models.Q(subtotal__gte=0)
                ),
                name='payment_intent_line_nonnegative_amounts',
            ),
        ]

    def clean(self):
        errors = {}
        gross = self.precio_unitario_snapshot * self.cantidad
        if self.descuento > gross:
            errors['descuento'] = 'El descuento no puede superar el bruto.'
        if self.subtotal != gross - self.descuento:
            errors['subtotal'] = 'El subtotal no coincide con la línea.'
        if self.intent_id and self.moneda != self.intent.currency:
            errors['moneda'] = 'La moneda no coincide con el Intent.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self._state.adding and not getattr(
            self,
            '_allow_service_create',
            False,
        ):
            raise ValidationError(
                'Una línea de PaymentIntent sólo puede crearla su servicio.'
            )
        if not self._state.adding:
            raise ValidationError('Una línea de PaymentIntent es inmutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Una línea de PaymentIntent no puede eliminarse.')


class ProviderPaymentAttempt(models.Model):
    """Intento trazable de crear un checkout; no acredita ni registra dinero."""

    class Provider(models.TextChoices):
        MERCADO_PAGO = 'MERCADO_PAGO', 'Mercado Pago'

    class Context(models.TextChoices):
        BOOKING = 'BOOKING', 'Reserva'
        ORDER = 'ORDER', 'Orden de compra'

    class Channel(models.TextChoices):
        ONLINE = 'ONLINE', 'Online'
        IN_PERSON = 'IN_PERSON', 'Presencial'

    class Status(models.TextChoices):
        PROCESSING = 'PROCESSING', 'Creando en proveedor'
        READY = 'READY', 'Checkout disponible'
        OUTCOME_UNKNOWN = 'OUTCOME_UNKNOWN', 'Resultado incierto'
        FAILED = 'FAILED', 'Creación rechazada'
        EXPIRED = 'EXPIRED', 'No utilizable'

    class ReconciliationStatus(models.TextChoices):
        NOT_EVALUATED = 'NOT_EVALUATED', 'No evaluado'
        PARTIAL = 'PARTIAL', 'Pago parcial'
        APPLIED = 'APPLIED', 'Aplicado'
        LATE = 'LATE', 'Pago tardío'
        REVIEW_REQUIRED = 'REVIEW_REQUIRED', 'Revisión requerida'

    ACTIVE_STATUSES = (
        Status.PROCESSING,
        Status.READY,
        Status.OUTCOME_UNKNOWN,
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    context = models.CharField(max_length=10, choices=Context.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROCESSING,
    )
    payment_intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.PROTECT,
        related_name='provider_attempts',
        null=True,
        blank=True,
    )
    order = models.ForeignKey(
        'OrdenCompra',
        on_delete=models.PROTECT,
        related_name='provider_attempts',
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=PAYMENT_CURRENCY_CHOICES)
    external_reference = models.CharField(max_length=128, unique=True)
    client_idempotency_key = models.CharField(max_length=128)
    provider_idempotency_key = models.CharField(max_length=128, unique=True)
    request_fingerprint = models.CharField(max_length=64)
    provider_order_id = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
    )
    provider_status = models.CharField(max_length=50, blank=True, default='')
    checkout_url = models.URLField(max_length=1000, blank=True, default='')
    provider_expires_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=50, blank=True, default='')
    error_detail = models.CharField(max_length=200, blank=True, default='')
    provider_call_count = models.PositiveSmallIntegerField(default=0)
    last_provider_call_at = models.DateTimeField(null=True, blank=True)
    response_received_at = models.DateTimeField(null=True, blank=True)
    reconciliation_status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.NOT_EVALUATED,
    )
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    last_provider_status = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='provider_payment_attempts_created',
    )

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name='provider_attempt_positive_amount',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        context='BOOKING',
                        payment_intent__isnull=False,
                        order__isnull=True,
                    )
                    | models.Q(
                        context='ORDER',
                        payment_intent__isnull=True,
                        order__isnull=False,
                    )
                ),
                name='provider_attempt_exact_context',
            ),
            models.UniqueConstraint(
                fields=['provider', 'created_by', 'client_idempotency_key'],
                name='provider_attempt_actor_client_key',
            ),
            models.UniqueConstraint(
                fields=['provider', 'payment_intent'],
                condition=models.Q(
                    status__in=['PROCESSING', 'READY', 'OUTCOME_UNKNOWN']
                ),
                name='provider_attempt_one_active_intent',
            ),
            models.UniqueConstraint(
                fields=['provider', 'order'],
                condition=models.Q(
                    status__in=['PROCESSING', 'READY', 'OUTCOME_UNKNOWN']
                ),
                name='provider_attempt_one_active_order',
            ),
        ]
        indexes = [
            models.Index(
                fields=['provider', 'status', '-created_at'],
                name='provider_attempt_status_idx',
            ),
            models.Index(
                fields=['context', '-created_at'],
                name='provider_attempt_context_idx',
            ),
        ]


class ProviderEvent(models.Model):
    """Inbox autenticado del proveedor; no concede autoridad financiera."""

    class Provider(models.TextChoices):
        MERCADO_PAGO = 'MERCADO_PAGO', 'Mercado Pago'

    class Status(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Recibido'
        FETCH_PENDING = 'FETCH_PENDING', 'Consulta en curso'
        VERIFIED = 'VERIFIED', 'Verificado'
        RETRYABLE_ERROR = 'RETRYABLE_ERROR', 'Error recuperable'
        REJECTED = 'REJECTED', 'Rechazado'
        MISMATCH = 'MISMATCH', 'Datos divergentes'

    class ReconciliationStatus(models.TextChoices):
        NOT_EVALUATED = 'NOT_EVALUATED', 'No evaluado'
        APPLIED = 'APPLIED', 'Aplicado'
        REVIEW_REQUIRED = 'REVIEW_REQUIRED', 'Revisión requerida'
        IGNORED = 'IGNORED', 'Sin efecto financiero'

    provider = models.CharField(max_length=20, choices=Provider.choices)
    topic = models.CharField(max_length=30)
    action = models.CharField(max_length=100)
    event_id = models.CharField(max_length=128)
    provider_resource_id = models.CharField(max_length=128)
    received_at = models.DateTimeField(default=timezone.now, editable=False)
    event_created_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RECEIVED,
    )
    attempt = models.ForeignKey(
        ProviderPaymentAttempt,
        on_delete=models.PROTECT,
        related_name='provider_events',
        null=True,
        blank=True,
    )
    notification_snapshot = models.JSONField(default=dict)
    provider_snapshot = models.JSONField(default=dict)
    processing_attempts = models.PositiveSmallIntegerField(default=0)
    last_error_code = models.CharField(max_length=50, blank=True, default='')
    last_error_detail = models.CharField(max_length=200, blank=True, default='')
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    reconciliation_status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.NOT_EVALUATED,
    )
    reconciliation_attempts = models.PositiveSmallIntegerField(default=0)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciliation_code = models.CharField(max_length=50, blank=True, default='')
    business_result = models.JSONField(default=dict, blank=True)
    financial_payments = models.ManyToManyField(
        'Pago',
        related_name='provider_events',
        blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['received_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'event_id'],
                name='provider_event_unique_identity',
            ),
        ]
        indexes = [
            models.Index(
                fields=['provider', 'status', 'next_retry_at'],
                name='provider_event_pending_idx',
            ),
            models.Index(
                fields=['provider', 'provider_resource_id'],
                name='provider_event_resource_idx',
            ),
        ]


class EvaluacionSolicitudTecnica(models.Model):
    solicitud = models.ForeignKey(
        SolicitudTecnicaReserva,
        on_delete=models.PROTECT,
        related_name='intentos_evaluacion',
    )
    evaluacion = models.OneToOneField(
        EvaluacionRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='intento_solicitud_tecnica',
    )
    intento = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['intento']
        constraints = [
            models.UniqueConstraint(
                fields=['solicitud', 'intento'],
                name='unique_technical_request_attempt',
            ),
        ]


class AceptacionAdvertenciaTecnica(models.Model):
    solicitud = models.ForeignKey(
        SolicitudTecnicaReserva,
        on_delete=models.PROTECT,
        related_name='aceptaciones_advertencia',
    )
    evaluacion = models.OneToOneField(
        EvaluacionRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='aceptacion_advertencia',
    )
    policy_version = models.CharField(max_length=50)
    warning_codes = models.JSONField(default=list)
    warning_texts = models.JSONField(default=list)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='advertencias_tecnicas_aceptadas',
    )
    accepted_at = models.DateTimeField(auto_now_add=True)


class ImmutableTechnicalReviewDecisionQuerySet(models.QuerySet):
    immutable_error = 'Las decisiones de revisión técnica son inmutables.'

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(
            'La creación masiva de decisiones de revisión técnica no está '
            'permitida; use el servicio de revisión auditado.'
        )

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(
            'update_or_create no está permitido para decisiones de revisión '
            'técnica inmutables.'
        )


class ImmutableTechnicalReviewDecisionManager(
    models.Manager.from_queryset(ImmutableTechnicalReviewDecisionQuerySet)
):
    pass


class DecisionRevisionTecnica(models.Model):
    class Accion(models.TextChoices):
        APROBAR = 'APROBAR', 'Aprobar'
        RECHAZAR = 'RECHAZAR', 'Rechazar'
        SOLICITAR_INFORMACION = (
            'SOLICITAR_INFORMACION',
            'Solicitar información',
        )
        RECOMENDAR_OTRA_FECHA = (
            'RECOMENDAR_OTRA_FECHA',
            'Recomendar otra fecha',
        )

    solicitud = models.ForeignKey(
        SolicitudTecnicaReserva,
        on_delete=models.PROTECT,
        related_name='decisiones_revision',
    )
    evaluacion = models.ForeignKey(
        EvaluacionRiesgoTecnico,
        on_delete=models.PROTECT,
        related_name='decisiones_revision',
    )
    policy_version = models.CharField(max_length=50)
    accion = models.CharField(max_length=30, choices=Accion.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='decisiones_revision_tecnica',
    )
    motivo_interno = models.TextField(blank=True)
    mensaje_cliente = models.TextField(blank=True)
    datos_faltantes = models.JSONField(default=list, blank=True)
    fecha_recomendada = models.DateField(null=True, blank=True)
    estado_anterior = models.CharField(
        max_length=30,
        choices=SolicitudTecnicaReserva.Estado.choices,
    )
    estado_nuevo = models.CharField(
        max_length=30,
        choices=SolicitudTecnicaReserva.Estado.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableTechnicalReviewDecisionManager()

    class Meta:
        ordering = ['-created_at']
        base_manager_name = 'objects'
        default_manager_name = 'objects'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                'Una decisión de revisión técnica persistida es inmutable.'
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            'Una decisión de revisión técnica persistida no puede eliminarse.'
        )


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


# ============================================================
# SECCIÓN 15: AUDITORÍA
# ============================================================

class Auditoria(models.Model):
    """
    Registro de auditoría para todas las operaciones CRUD en el sistema.
    Mantiene un log de todas las modificaciones en las tablas principales.
    """
    ACCION_CHOICES = [
        ('ALTA', 'Alta / Creación'),
        ('MODIFICACION', 'Modificación'),
        ('BAJA', 'Baja / Eliminación'),
    ]

    tabla = models.CharField(
        max_length=100,
        help_text="Nombre de la tabla modificada"
    )
    registro_id = models.PositiveIntegerField(
        help_text="ID del registro modificado"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auditorias',
        help_text="Usuario que realizó la acción"
    )
    fecha_hora = models.DateTimeField(
        auto_now_add=True,
        help_text="Fecha y hora de la acción"
    )
    accion = models.CharField(
        max_length=20,
        choices=ACCION_CHOICES,
        help_text="Tipo de acción realizada"
    )
    valor_anterior = models.JSONField(
        null=True,
        blank=True,
        help_text="Valores anteriores (en caso de modificación)"
    )
    valor_nuevo = models.JSONField(
        null=True,
        blank=True,
        help_text="Valores nuevos"
    )

    # Campo para distinguir entre usuario autenticado y anonimo
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP desde donde se realizó la acción"
    )

    class Meta:
        verbose_name = "Auditoría"
        verbose_name_plural = "Auditorías"
        ordering = ['-fecha_hora']
        permissions = [
            ('view_reports', 'Can view reports'),
            ('view_financial_reports', 'Can view financial reports'),
            ('view_audit', 'Can view audit records'),
            ('revert_audit', 'Can revert audited changes'),
        ]
        indexes = [
            models.Index(fields=['tabla', '-fecha_hora']),
            models.Index(fields=['usuario', '-fecha_hora']),
        ]

    def __str__(self):
        return f"{self.accion} en {self.tabla} (ID: {self.registro_id}) - {self.fecha_hora.strftime('%d/%m/%Y %H:%M')}"

    def obtener_diferencias(self):
        """
        Calcula y retorna solo los campos que cambiaron.
        Retorna: {campo: {'antes': valor_anterior, 'ahora': valor_nuevo}}
        """
        if self.accion == 'MODIFICACION' and self.valor_anterior and self.valor_nuevo:
            diferencias = {}

            for campo, valor_nuevo in self.valor_nuevo.items():
                valor_anterior = self.valor_anterior.get(campo)

                # Solo incluir campos que efectivamente cambiaron
                if valor_anterior != valor_nuevo:
                    diferencias[campo] = {
                        'antes': valor_anterior,
                        'ahora': valor_nuevo
                    }

            return diferencias

        elif self.accion == 'ALTA':
            # Para ALTA, retornar todos los valores nuevos
            return {
                'accion': 'CREACIÓN',
                'valores': self.valor_nuevo or {}
            }

        elif self.accion == 'BAJA':
            # Para BAJA, retornar todos los valores eliminados
            return {
                'accion': 'ELIMINACIÓN',
                'valores': self.valor_anterior or {}
            }

        return {}

    def obtener_diferencias_texto(self):
        """
        Retorna un texto formateado de los cambios.
        Ejemplo: "nombre: 'Juan' → 'Carlos', estado: 'activo' → 'inactivo'"
        """
        diferencias = self.obtener_diferencias()

        if not diferencias:
            return "Sin cambios"

        if self.accion == 'MODIFICACION':
            return ", ".join([
                f"<strong>{k}</strong>: '{v['antes']}' → '{v['ahora']}'"
                for k, v in diferencias.items()
            ])

        return "N/A"


class OrdenCompra(models.Model):
    ESTADOS = (
        ('PENDIENTE', 'Pendiente'),
        ('ESPERANDO_PAGO', 'Esperando Pago'),
        ('PAGADO', 'Pagado'),
        ('COMPLETADO', 'Completado'),
        ('RECHAZADO', 'Rechazado'),
        ('CANCELADO', 'Cancelado'),
    )

    codigo = models.CharField(max_length=20, unique=True)
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.PROTECT,
        related_name='ordenes_compra'
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    preference_id = models.CharField(max_length=255, null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    notas = models.TextField(blank=True, null=True)
    creado_at = models.DateTimeField(auto_now_add=True)
    actualizado_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Orden de Compra"
        verbose_name_plural = "Órdenes de Compra"
        ordering = ['-creado_at']
    
    def __str__(self):
        return f"{self.codigo} - {self.cliente} - ${self.total}"


class ImmutableStockCommitmentQuerySet(models.QuerySet):
    immutable_error = (
        'Los compromisos de stock sólo cambian mediante el servicio de órdenes.'
    )

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(
            'La creación masiva de compromisos de stock no está permitida.'
        )

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(self.immutable_error)


class StockCommitmentManager(
    models.Manager.from_queryset(ImmutableStockCommitmentQuerySet)
):
    def _create_from_order_service(self, **values):
        commitment = self.model(**values)
        commitment._allow_order_service_create = True
        commitment.save(force_insert=True, using=self.db)
        return commitment

    def _transition_from_order_service(self, *, commitment_ids, **values):
        queryset = self.get_queryset().filter(pk__in=commitment_ids)
        return models.QuerySet.update(queryset, **values)


class CompromisoStock(models.Model):
    class State(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Activo'
        CONSUMED = 'CONSUMED', 'Consumido'
        RELEASED = 'RELEASED', 'Liberado'

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name='compromisos_stock',
    )
    orden = models.ForeignKey(
        OrdenCompra,
        on_delete=models.PROTECT,
        related_name='compromisos_stock',
    )
    cantidad = models.PositiveIntegerField()
    estado = models.CharField(
        max_length=10,
        choices=State.choices,
        default=State.ACTIVE,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    consumed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    reason_code = models.CharField(
        max_length=50,
        default='ORDER_RESERVATION',
    )
    metadata = models.JSONField(default=dict, blank=True)

    objects = StockCommitmentManager()

    class Meta:
        verbose_name = 'Compromiso de stock'
        verbose_name_plural = 'Compromisos de stock'
        ordering = ['pk']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name='stock_commitment_positive_quantity',
            ),
            models.UniqueConstraint(
                fields=('orden', 'producto'),
                name='stock_commitment_unique_order_product',
            ),
            models.CheckConstraint(
                condition=~models.Q(idempotency_key=''),
                name='stock_commitment_key_required',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        estado='ACTIVE',
                        consumed_at__isnull=True,
                        released_at__isnull=True,
                    )
                    | models.Q(
                        estado='CONSUMED',
                        consumed_at__isnull=False,
                        released_at__isnull=True,
                    )
                    | models.Q(
                        estado='RELEASED',
                        consumed_at__isnull=True,
                        released_at__isnull=False,
                    )
                ),
                name='stock_commitment_coherent_state_timestamps',
            ),
        ]
        indexes = [
            models.Index(
                fields=['producto', 'estado'],
                name='stock_commit_product_state_idx',
            ),
            models.Index(
                fields=['orden', 'estado'],
                name='stock_commit_order_state_idx',
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and not getattr(
            self,
            '_allow_order_service_create',
            False,
        ):
            raise ValidationError(
                'Un compromiso de stock sólo puede crearse mediante su servicio.'
            )
        if not self._state.adding:
            raise ValidationError(
                'Un compromiso persistido sólo cambia mediante su servicio.'
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Un compromiso de stock no puede eliminarse.')

    def __str__(self):
        return (
            f'Orden {self.orden_id} - Producto {self.producto_id} '
            f'x{self.cantidad} ({self.estado})'
        )


class ImmutablePagoQuerySet(models.QuerySet):
    immutable_error = 'Los Pagos financieros son inmutables fuera de sus servicios.'

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError('La creación masiva de Pagos no está permitida.')

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        raise ValidationError(self.immutable_error)


class PagoManager(models.Manager.from_queryset(ImmutablePagoQuerySet)):
    def _create_booking_from_service(self, **values):
        payment = self.model(**values)
        payment._allow_booking_create = True
        payment.save(force_insert=True, using=self.db)
        return payment

    def _create_external_from_service(self, **values):
        payment = self.model(**values)
        payment._allow_booking_create = True
        payment._allow_external_create = True
        payment.save(force_insert=True, using=self.db)
        return payment

    def _transition(self, *, payment_id, from_statuses, **values):
        queryset = self.get_queryset().filter(
            pk=payment_id,
            status__in=from_statuses,
        )
        return models.QuerySet.update(queryset, **values)

    def _link_turno(self, *, payment_ids, turno_id):
        queryset = self.get_queryset().filter(
            pk__in=payment_ids,
            payment_intent__isnull=False,
            payment_intent__confirmed_turno_id=turno_id,
            turno__isnull=True,
        )
        return models.QuerySet.update(queryset, turno_id=turno_id)


class Pago(models.Model):
    METODO_PAGO_CHOICES = (
        ('EFECTIVO', 'Efectivo'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('MERCADO_PAGO', 'Mercado Pago'),
        ('CASH', 'Efectivo manual'),
        ('BANK_TRANSFER', 'Transferencia bancaria manual'),
        ('EXTERNAL_CARD', 'Tarjeta externa'),
        ('OTHER', 'Otro medio manual'),
    )

    class Method(models.TextChoices):
        CASH = 'CASH', 'Efectivo'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Transferencia bancaria'
        EXTERNAL_CARD = 'EXTERNAL_CARD', 'Tarjeta externa'
        OTHER = 'OTHER', 'Otro'
        MERCADO_PAGO = 'MERCADO_PAGO', 'Mercado Pago'

    class Purpose(models.TextChoices):
        CONFIRMATION = 'CONFIRMATION', 'Confirmación'
        BALANCE = 'BALANCE', 'Saldo'

    class Status(models.TextChoices):
        PENDING_RECONCILIATION = (
            'PENDING_RECONCILIATION',
            'Pendiente de conciliación',
        )
        RECONCILED = 'RECONCILED', 'Conciliado'
        REJECTED = 'REJECTED', 'Rechazado'
        REVERSED = 'REVERSED', 'Revertido'

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment_intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.PROTECT,
        related_name='payments',
        null=True,
        blank=True,
    )

    orden = models.ForeignKey(
        OrdenCompra,
        on_delete=models.PROTECT,
        related_name='pagos',
        null=True,
        blank=True
    )
    turno = models.ForeignKey(
        'Turno',
        on_delete=models.PROTECT,
        related_name='pagos',
        null=True,
        blank=True
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES)
    currency = models.CharField(
        max_length=3,
        choices=PAYMENT_CURRENCY_CHOICES,
        default='ARS',
    )
    purpose = models.CharField(
        max_length=15,
        choices=Purpose.choices,
        default=Purpose.BALANCE,
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.RECONCILED,
    )
    transaccion_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    fecha_pago = models.DateTimeField(default=timezone.now)
    recorded_at = models.DateTimeField(default=timezone.now, editable=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payments_recorded',
        null=True,
        blank=True,
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='payments_reconciled',
        null=True,
        blank=True,
    )
    manual_reference = models.CharField(max_length=80, blank=True, default='')
    comprobante_foto = models.FileField(
        upload_to='booking/%Y/%m/',
        storage=private_payment_receipt_storage,
        blank=True,
        null=True
    )
    receipt_sha256 = models.CharField(max_length=64, blank=True, default='')
    idempotency_key = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        unique=True,
    )
    terminal_reason = models.CharField(max_length=100, blank=True, default='')
    es_sena = models.BooleanField(default=False)
    provider_code = models.CharField(max_length=20, blank=True, default='')
    provider_payment_id = models.CharField(max_length=128, blank=True, default='')
    provider_attempt = models.ForeignKey(
        ProviderPaymentAttempt,
        on_delete=models.PROTECT,
        related_name='reconciled_payments',
        null=True,
        blank=True,
    )
    provider_event = models.ForeignKey(
        ProviderEvent,
        on_delete=models.PROTECT,
        related_name='originated_payments',
        null=True,
        blank=True,
    )
    provider_occurred_at = models.DateTimeField(null=True, blank=True)
    provider_snapshot = models.JSONField(default=dict, blank=True)

    history = HistoricalRecords()
    objects = PagoManager()

    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ['-recorded_at', '-pk']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        permissions = [
            ('register_payment', 'Can register payments'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto__gt=0),
                name='payment_positive_amount',
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(payment_intent__isnull=False)
                        & models.Q(orden__isnull=True)
                    )
                    | (
                        models.Q(payment_intent__isnull=True)
                        & models.Q(orden__isnull=False)
                    )
                ),
                name='payment_exactly_one_context',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(orden__isnull=True)
                    | models.Q(turno__isnull=True)
                ),
                name='payment_order_without_turno',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(orden__isnull=False)
                    | (
                        models.Q(recorded_by__isnull=False)
                        & models.Q(idempotency_key__isnull=False)
                    )
                    | (
                        ~models.Q(provider_code='')
                        & ~models.Q(provider_payment_id='')
                        & models.Q(provider_attempt__isnull=False)
                        & models.Q(provider_event__isnull=False)
                        & models.Q(idempotency_key__isnull=False)
                    )
                ),
                name='booking_payment_actor_and_key',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(orden__isnull=False)
                    | models.Q(
                        status='PENDING_RECONCILIATION',
                        reconciled_at__isnull=True,
                        reconciled_by__isnull=True,
                    )
                    | models.Q(
                        status='RECONCILED',
                        reconciled_at__isnull=False,
                        reconciled_by__isnull=False,
                        terminal_reason='',
                    )
                    | models.Q(
                        status='RECONCILED',
                        reconciled_at__isnull=False,
                        reconciled_by__isnull=True,
                        terminal_reason='',
                    ) & ~models.Q(provider_code='')
                    | (
                        models.Q(
                            status__in=['REJECTED', 'REVERSED'],
                            reconciled_at__isnull=False,
                            reconciled_by__isnull=False,
                        )
                        & ~models.Q(terminal_reason='')
                    )
                ),
                name='booking_payment_status_metadata',
            ),
            models.UniqueConstraint(
                fields=['metodo_pago', 'manual_reference'],
                condition=(
                    models.Q(payment_intent__isnull=False)
                    & models.Q(
                        metodo_pago__in=['BANK_TRANSFER', 'EXTERNAL_CARD']
                    )
                    & ~models.Q(manual_reference='')
                ),
                name='payment_unique_manual_reference',
            ),
            models.UniqueConstraint(
                fields=['provider_code', 'provider_payment_id'],
                condition=(
                    ~models.Q(provider_code='')
                    & ~models.Q(provider_payment_id='')
                ),
                name='payment_unique_provider_identity',
            ),
        ]
        indexes = [
            models.Index(
                fields=['payment_intent', 'status'],
                name='payment_intent_status_idx',
            ),
            models.Index(
                fields=['status', '-recorded_at'],
                name='payment_status_recorded_idx',
            ),
        ]

    @property
    def amount(self):
        return self.monto

    @property
    def method(self):
        return self.metodo_pago

    @property
    def occurred_at(self):
        return self.fecha_pago

    @property
    def receipt(self):
        return self.comprobante_foto

    def clean(self):
        errors = {}
        has_intent = self.payment_intent_id is not None
        has_order = self.orden_id is not None
        provider_fields = (
            bool(self.provider_code),
            bool(self.provider_payment_id),
            self.provider_attempt_id is not None,
            self.provider_event_id is not None,
        )
        external = all(provider_fields)
        if any(provider_fields) and not external:
            errors['provider_code'] = (
                'La identidad externa debe incluir proveedor, pago, Attempt '
                'y evento.'
            )
        if external and self.metodo_pago != self.Method.MERCADO_PAGO:
            errors['metodo_pago'] = (
                'El medio no coincide con la identidad del proveedor.'
            )
        if has_intent == has_order:
            errors['payment_intent'] = (
                'El Pago debe pertenecer exactamente a un Intent o una Orden.'
            )
        if has_order and self.turno_id is not None:
            errors['turno'] = (
                'Un Pago legacy de Orden no puede tener Turno asociado.'
            )
        if has_intent:
            if (
                self.turno_id is not None
                and self.turno_id != self.payment_intent.confirmed_turno_id
            ):
                errors['turno'] = (
                    'El Turno no coincide con el confirmado por el Intent.'
                )
            if self.currency != self.payment_intent.currency:
                errors['currency'] = 'La moneda no coincide con el Intent.'
            if self.metodo_pago not in self.Method.values:
                errors['metodo_pago'] = 'El medio de pago no es válido.'
            if self.recorded_by_id is None and not external:
                errors['recorded_by'] = 'El actor de registro es obligatorio.'
            if not self.idempotency_key:
                errors['idempotency_key'] = (
                    'La clave de idempotencia es obligatoria.'
                )
        if self.monto is not None and self.monto <= 0:
            errors['monto'] = 'El importe debe ser mayor que cero.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('Un Pago financiero persistido es inmutable.')
        if (
            self.payment_intent_id is not None
            and not getattr(self, '_allow_booking_create', False)
        ):
            raise ValidationError(
                'Un Pago de booking sólo puede crearse mediante su servicio.'
            )
        if self.provider_code and not getattr(self, '_allow_external_create', False):
            raise ValidationError(
                'Un Pago externo sólo puede crearse mediante su reconciliador.'
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Un Pago financiero no puede eliminarse.')

    def __str__(self):
        context = (
            f'Intent {self.payment_intent_id}'
            if self.payment_intent_id
            else f'Orden {self.orden_id}'
        )
        return f'Pago {self.id} - {context} - {self.currency} {self.monto}'


class ImmutablePaymentReconciliationCaseQuerySet(models.QuerySet):
    immutable_error = 'Los casos de conciliación financiera son inmutables.'

    def update(self, **kwargs):
        raise ValidationError(self.immutable_error)

    def delete(self):
        raise ValidationError(self.immutable_error)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(self.immutable_error)

    def bulk_create(self, objs, *args, **kwargs):
        raise ValidationError(self.immutable_error)


class PaymentReconciliationCaseManager(
    models.Manager.from_queryset(ImmutablePaymentReconciliationCaseQuerySet)
):
    def _create_from_service(self, **values):
        case = self.model(**values)
        case._allow_service_create = True
        case.save(force_insert=True, using=self.db)
        return case

    def _link_provider_context(self, *, case_id, attempt_id, event_id):
        queryset = self.get_queryset().filter(
            pk=case_id,
            provider_attempt__isnull=True,
            provider_event__isnull=True,
        )
        return models.QuerySet.update(
            queryset,
            provider_attempt_id=attempt_id,
            provider_event_id=event_id,
        )


class PaymentReconciliationCase(models.Model):
    """Excepción financiera provider-neutral pendiente de resolución manual."""

    class Type(models.TextChoices):
        LATE_PAYMENT = 'LATE_PAYMENT', 'Pago tardío'
        BOOKING_CONFIRMATION_FAILED = (
            'BOOKING_CONFIRMATION_FAILED',
            'Confirmación de agenda fallida',
        )
        EXTERNAL_PAYMENT_REVIEW = (
            'EXTERNAL_PAYMENT_REVIEW',
            'Revisión de pago externo',
        )
        ORDER_FULFILLMENT_FAILED = (
            'ORDER_FULFILLMENT_FAILED',
            'Orden no cumplible',
        )
        POST_PAYMENT_CHANGE = (
            'POST_PAYMENT_CHANGE',
            'Novedad financiera posterior',
        )

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Abierto'
        RESOLVED = 'RESOLVED', 'Resuelto'

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment_intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.PROTECT,
        related_name='reconciliation_cases',
        null=True,
        blank=True,
    )
    slot_hold = models.ForeignKey(
        SlotHold,
        on_delete=models.PROTECT,
        related_name='payment_reconciliation_cases',
        null=True,
        blank=True,
    )
    turno = models.ForeignKey(
        'Turno',
        on_delete=models.PROTECT,
        related_name='payment_reconciliation_cases',
        null=True,
        blank=True,
    )
    payments = models.ManyToManyField(
        Pago,
        related_name='reconciliation_cases',
        blank=True,
    )
    order = models.ForeignKey(
        OrdenCompra,
        on_delete=models.PROTECT,
        related_name='payment_reconciliation_cases',
        null=True,
        blank=True,
    )
    provider_attempt = models.ForeignKey(
        ProviderPaymentAttempt,
        on_delete=models.PROTECT,
        related_name='reconciliation_cases',
        null=True,
        blank=True,
    )
    provider_event = models.ForeignKey(
        ProviderEvent,
        on_delete=models.PROTECT,
        related_name='reconciliation_cases',
        null=True,
        blank=True,
    )
    case_type = models.CharField(max_length=40, choices=Type.choices)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.OPEN,
    )
    reason_code = models.CharField(max_length=50)
    operation_key = models.CharField(max_length=128, unique=True)
    details = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_reconciliation_cases_created',
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    objects = PaymentReconciliationCaseManager()

    class Meta:
        ordering = ['-created_at', '-pk']
        base_manager_name = 'objects'
        default_manager_name = 'objects'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status='OPEN',
                        resolved_at__isnull=True,
                    )
                    | models.Q(
                        status='RESOLVED',
                        resolved_at__isnull=False,
                    )
                ),
                name='payment_reconciliation_case_status_time',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        payment_intent__isnull=False,
                        slot_hold__isnull=False,
                        order__isnull=True,
                    )
                    | models.Q(
                        payment_intent__isnull=True,
                        slot_hold__isnull=True,
                        order__isnull=False,
                    )
                ),
                name='payment_case_exact_context',
            ),
        ]
        permissions = [
            (
                'reconcile_external_payment',
                'Can reconcile external payments manually',
            ),
        ]
        indexes = [
            models.Index(
                fields=['status', '-created_at'],
                name='payment_case_status_cr_idx',
            ),
            models.Index(
                fields=['payment_intent', 'case_type'],
                name='payment_case_intent_type_idx',
            ),
        ]

    def clean(self):
        errors = {}
        if (
            self.payment_intent_id
            and self.slot_hold_id
            and self.payment_intent.slot_hold_id != self.slot_hold_id
        ):
            errors['slot_hold'] = 'El HOLD no coincide con el Intent.'
        if not self.operation_key:
            errors['operation_key'] = 'La operation key es obligatoria.'
        if not self.reason_code:
            errors['reason_code'] = 'La razón es obligatoria.'
        if bool(self.payment_intent_id) == bool(self.order_id):
            errors['payment_intent'] = 'El caso debe tener un único contexto.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self._state.adding and not getattr(
            self,
            '_allow_service_create',
            False,
        ):
            raise ValidationError(
                'Un caso de conciliación sólo puede crearse mediante su servicio.'
            )
        if not self._state.adding:
            raise ValidationError(
                'Un caso de conciliación persistido sólo cambia mediante servicios.'
            )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Un caso de conciliación no puede eliminarse.')


class OrdenItem(models.Model):
    orden = models.ForeignKey(
        OrdenCompra,
        related_name='items',
        on_delete=models.CASCADE
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT
    )
    cantidad = models.PositiveIntegerField()
    precio_historico = models.DecimalField(max_digits=10, decimal_places=2)

    history = HistoricalRecords()
    
    class Meta:
        verbose_name = "Item de Orden"
        verbose_name_plural = "Items de Órdenes"
    
    def __str__(self):
        return f"{self.orden.codigo} - {self.producto.nombre} x{self.cantidad}"
    
    @property
    def subtotal(self):
        return self.cantidad * self.precio_historico


class OrdenPendiente(models.Model):
    """
    Registra cada intención de compra enviada por WhatsApp.
    Usada para auditoría y análisis de ventas.
    """
    ESTADOS = [
        ('PENDIENTE', 'Pendiente - Abierta en WhatsApp'),
        ('CONFIRMADA', 'Confirmada por Cliente'),
        ('COMPLETADA', 'Pedido Completado'),
        ('CANCELADA', 'Cancelada'),
    ]
    
    cliente = models.ForeignKey(
        'usuarios.Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordenes_pendientes'
    )

    orden_compra = models.OneToOneField(
        OrdenCompra,
        on_delete=models.PROTECT,
        related_name='orden_pendiente_legacy',
        null=True,
        blank=True,
        help_text='OrdenCompra canónica que respalda este contrato legacy.',
    )
    
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='PENDIENTE',
        help_text="Estado de la orden"
    )
    
    # Datos de la Orden
    items_json = models.JSONField(
        help_text="Detalles de productos: [{'nombre': 'X', 'cantidad': N, 'precio': P, 'subtotal': S}]"
    )
    monto_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Monto total de la orden"
    )
    
    # Auditoría
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_confirmacion = models.DateTimeField(null=True, blank=True)
    fecha_completacion = models.DateTimeField(null=True, blank=True)
    
    # Nota del cliente
    nota_cliente = models.TextField(
        blank=True,
        help_text="Notas adicionales del cliente sobre la orden"
    )
    
    class Meta:
        verbose_name = "Orden Pendiente (WhatsApp)"
        verbose_name_plural = "Órdenes Pendientes"
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        cliente_nombre = self.cliente.usuario.get_full_name() if self.cliente else "Anónimo"
        return f"Orden {self.id} - {cliente_nombre} - ${self.monto_total}"
