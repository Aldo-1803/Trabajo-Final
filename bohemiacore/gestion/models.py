from django.db import models
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError
import logging
from simple_history.models import HistoricalRecords

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
        """Calcula lo que realmente se puede vender ahora mismo"""
        return max(0, self.stock_real - self.stock_comprometido)
    
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

    def __str__(self):
        return f"{self.marca} - {self.nombre} ({self.stock_disponible} ud.)"


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


class Pago(models.Model):
    METODO_PAGO_CHOICES = (
        ('EFECTIVO', 'Efectivo'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('MERCADO_PAGO', 'Mercado Pago'),
    )

    orden = models.ForeignKey(
        OrdenCompra,
        on_delete=models.CASCADE,
        related_name='pagos',
        null=True,
        blank=True
    )
    turno = models.ForeignKey(
        'Turno',
        on_delete=models.CASCADE,
        related_name='pagos',
        null=True,
        blank=True
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES)
    transaccion_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    fecha_pago = models.DateTimeField(default=timezone.now)
    comprobante_foto = models.ImageField(
        upload_to='pagos/comprobantes/',
        blank=True,
        null=True
    )
    es_sena = models.BooleanField(default=False)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ['-fecha_pago']
        permissions = [
            ('register_payment', 'Can register payments'),
        ]

    def __str__(self):
        return f"Pago {self.id} - {self.orden.codigo} - ${self.monto}"


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
