from django.contrib import admin
from .models import (
    TipoCabello, 
    GrosorCabello, 
    PorosidadCabello, 
    CueroCabelludo, 
    EstadoGeneral,
    CategoriaServicio,
    Servicio,
    ReglaDiagnostico,
    Rutina,
    PasoRutina,
    RutinaCliente,
    PasoRutinaCliente,
    Notificacion
)

# ----------------------------------------------------
# 1. CLASE ADMIN PERSONALIZADA (Para Mantenibilidad)
# ----------------------------------------------------
class CatalogoAdmin(admin.ModelAdmin):
    """
    Configuración base para mostrar los catálogos en el Admin.
    Permite buscar por 'nombre' y filtrar por 'activo'.
    """
    list_display = ('nombre', 'activo', 'fecha_creacion') # Columnas a mostrar
    search_fields = ('nombre',) # Habilita una barra de búsqueda
    #list_filter = ('activo',) # Habilita un filtro lateral
    ordering = ('nombre',)

# ----------------------------------------------------
# 2. REGISTRO DE MODELOS
# ----------------------------------------------------
# Le dice a Django que muestre estos modelos en el panel de admin
# usando la configuración de CatalogoAdmin.

admin.site.register(TipoCabello, CatalogoAdmin)
admin.site.register(GrosorCabello, CatalogoAdmin)
admin.site.register(PorosidadCabello, CatalogoAdmin)
admin.site.register(CueroCabelludo, CatalogoAdmin)
admin.site.register(EstadoGeneral, CatalogoAdmin)

@admin.register(CategoriaServicio)
class CategoriaServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)

@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'precio_base', 'duracion_estimada')
    list_filter = ('categoria',) # ¡Muy útil para filtrar por categoría!
    search_fields = ('nombre', 'descripcion')


@admin.register(ReglaDiagnostico)
class ReglaDiagnosticoAdmin(admin.ModelAdmin):
    """
    Configuración para mostrar las Reglas de Diagnóstico (Nivel 1)
    en el panel de administrador.
    """
    list_display = (
        '__str__',  # Muestra el nombre de la regla
        'prioridad', 
        'mensaje_resultado',
        'cuero_cabelludo', # Condición 1
        'estado_general'   # Condición 2
    )
    list_filter = ('prioridad', 'cuero_cabelludo', 'estado_general')
    search_fields = ('mensaje_resultado', 'accion_resultado')
    
    # Esto ayuda a organizar el formulario de creación
    fieldsets = (
        ("Resultado (Qué pasa si coincide)", {
            'fields': ('prioridad', 'mensaje_resultado', 'accion_resultado')
        }),
        ("Condiciones (Cuándo coincide)", {
            'classes': ('collapse',), # Lo muestra colapsado
            'fields': (
                'tipo_cabello', 
                'grosor_cabello', 
                'porosidad_cabello', 
                'cuero_cabelludo', 
                'estado_general'
            ),
            'description': "Deja un campo vacío para 'Cualquiera'. La regla solo coincidirá si TODOS los campos seleccionados son iguales a los del perfil del cliente."
        }),
    )


# ============================================
# ADMIN PARA RUTINAS Y PASOS
# ============================================
class PasoRutinaInline(admin.TabularInline):
    """
    Permite editar PasoRutina directamente desde el formulario de Rutina.
    """
    model = PasoRutina
    extra = 1  # Muestra 1 fila vacía al final para agregar nuevos pasos
    fields = ('orden', 'descripcion', 'frecuencia')
    ordering = ('orden',)


@admin.register(Rutina)
class RutinaAdmin(admin.ModelAdmin):
    """
    Admin para gestionar Rutinas con protección de soft-delete.
    """
    list_display = ('nombre', 'version', 'estado', 'creada_por', 'fecha_creacion', 'cantidad_clientes')
    list_filter = ('estado', 'fecha_creacion')
    search_fields = ('nombre', 'objetivo')
    readonly_fields = ('fecha_creacion', 'fecha_obsoleta', 'version')
    inlines = [PasoRutinaInline]
    filter_horizontal = ('clientes_asignados',)  # Interface visual mejor para M2M
    
    fieldsets = (
        ("Información Básica", {
            'fields': ('nombre', 'objetivo', 'descripcion', 'version')
        }),
        ("Estado y Control", {
            'fields': ('estado', 'creada_por', 'clientes_asignados')
        }),
        ("Auditoría (Solo Lectura)", {
            'classes': ('collapse',),
            'fields': ('fecha_creacion', 'fecha_obsoleta')
        }),
    )
    
    def cantidad_clientes(self, obj):
        """Muestra cuántos clientes tienen asignada esta rutina."""
        return obj.clientes_asignados.count()
    cantidad_clientes.short_description = "Clientes Asignados"
    
    def get_readonly_fields(self, request, obj=None):
        """
        Si la rutina es OBSOLETA, todos los campos son de solo lectura.
        Esto evita ediciones accidentales.
        """
        readonly = list(self.readonly_fields)
        if obj and obj.estado == 'obsoleta':
            readonly.extend(['nombre', 'objetivo', 'descripcion', 'estado', 'creada_por', 'clientes_asignados'])
        return readonly
    
    def save_model(self, request, obj, form, change):
        """
        Hook para cuando se guarda la rutina.
        Aquí podemos ejecutar la lógica de obsoletar si es necesario.
        """
        # Si cambió el estado a OBSOLETA, llamamos al método
        if obj.estado == 'obsoleta' and obj.fecha_obsoleta is None:
            obj.obsoletar()  # Esto notifica a los clientes automáticamente
        else:
            obj.save()


@admin.register(PasoRutina)
class PasoRutinaAdmin(admin.ModelAdmin):
    """
    Admin para gestionar Pasos de Rutina individualmente (si es necesario).
    """
    list_display = ('plantilla', 'orden', 'descripcion', 'frecuencia')
    list_filter = ('plantilla', 'orden')
    search_fields = ('descripcion',)
    ordering = ('plantilla', 'orden')
    
    fieldsets = (
        ("Información del Paso", {
            'fields': ('plantilla', 'orden', 'descripcion', 'frecuencia')
        }),
    )


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    """
    Admin para visualizar todas las notificaciones del sistema.
    """
    list_display = ('titulo', 'usuario', 'tipo', 'estado', 'canal', 'fecha_envio')
    list_filter = ('estado', 'tipo', 'canal', 'fecha_envio')
    search_fields = ('titulo', 'mensaje', 'usuario__email')
    readonly_fields = ('fecha_envio', 'usuario', 'titulo', 'mensaje', 'origen_entidad', 'origen_id')
    ordering = ('-fecha_envio',)
    
    def has_add_permission(self, request):
        """Las notificaciones se crean automáticamente, no manualmente."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Las notificaciones no se pueden eliminar (auditoría)."""
        return False


# ============================================
# ADMIN PARA RUTINAS DEL CLIENTE
# ============================================
class PasoRutinaClienteInline(admin.TabularInline):
    """
    Permite visualizar los pasos de la rutina del cliente.
    """
    model = PasoRutinaCliente
    extra = 0  # No permite agregar nuevos pasos (son copias)
    fields = ('orden', 'descripcion', 'frecuencia', 'completado', 'fecha_completado')
    readonly_fields = ('orden', 'descripcion', 'frecuencia', 'completado', 'fecha_completado')


@admin.register(RutinaCliente)
class RutinaClienteAdmin(admin.ModelAdmin):
    """
    Admin para ver las copias de rutinas asignadas a clientes.
    """
    list_display = ('cliente', 'nombre', 'estado', 'version_asignada', 'fecha_asignacion', 'actualizado')
    list_filter = ('estado', 'fecha_asignacion', 'descargar_notificacion')
    search_fields = ('cliente__usuario__email', 'nombre')
    readonly_fields = ('cliente', 'rutina_original', 'nombre', 'objetivo', 'descripcion', 
                       'version_asignada', 'fecha_asignacion', 'fecha_ultima_notificacion')
    inlines = [PasoRutinaClienteInline]
    
    fieldsets = (
        ("Información del Cliente", {
            'fields': ('cliente', 'rutina_original')
        }),
        ("Datos de la Rutina (Copia)", {
            'fields': ('nombre', 'objetivo', 'descripcion', 'version_asignada')
        }),
        ("Estado y Control", {
            'fields': ('estado', 'descargar_notificacion', 'fecha_asignacion', 'fecha_ultima_notificacion')
        }),
    )
    
    def actualizado(self, obj):
        """Muestra si la copia está actualizada o desactualizada."""
        if obj.estado == 'activa':
            return '✅ Activa'
        elif obj.estado == 'desactualizada':
            return '⚠️ Desactualizada'
        elif obj.estado == 'obsoleta_original':
            return '❌ Original Obsoleta'
        else:
            return obj.get_estado_display()
    actualizado.short_description = "Estado"
    
    def has_add_permission(self, request):
        """Las rutinas del cliente se crean automáticamente, no manualmente."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """No se pueden eliminar directamente las copias de clientes."""
        return False


@admin.register(PasoRutinaCliente)
class PasoRutinaClienteAdmin(admin.ModelAdmin):
    """
    Admin para visualizar los pasos de las rutinas del cliente.
    """
    list_display = ('rutina_cliente', 'orden', 'frecuencia', 'completado', 'fecha_completado')
    list_filter = ('completado', 'fecha_completado', 'rutina_cliente')
    search_fields = ('descripcion', 'rutina_cliente__cliente__usuario__email')
    readonly_fields = ('rutina_cliente', 'orden', 'descripcion', 'frecuencia')
    
    fieldsets = (
        ("Información", {
            'fields': ('rutina_cliente', 'orden', 'descripcion', 'frecuencia')
        }),
        ("Estado de Completado", {
            'fields': ('completado', 'fecha_completado')
        }),
    )
    
    def has_add_permission(self, request):
        """Los pasos se crean automáticamente con la rutina."""
        return False