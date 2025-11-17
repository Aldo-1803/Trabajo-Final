from django.contrib import admin
from .models import (
    TipoCabello, 
    GrosorCabello, 
    PorosidadCabello, 
    CueroCabelludo, 
    EstadoGeneral,
    CategoriaServicio,
    Servicio,
    ReglaDiagnostico
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