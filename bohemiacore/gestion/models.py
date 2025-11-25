from django.db import models

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
        on_delete=models.SET_NULL, # Si borras la categoría, el servicio no se borra
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

    class Meta:
        verbose_name = "Servicio"
        verbose_name_plural = "Servicios"

    # Opcional: Modificamos el __str__ para que muestre la categoría
    def __str__(self):
        if self.categoria:
            return f"[{self.categoria.nombre}] {self.nombre}"
        return self.nombre