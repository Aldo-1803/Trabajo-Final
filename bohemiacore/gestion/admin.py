from django.contrib import admin
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral,
    CategoriaServicio, Servicio, ReglaDiagnostico, Rutina, RutinaCliente,
    Notificacion, Configuracion, Personal, HorarioLaboral, BloqueoAgenda, DiasSemana, Equipamiento,
    TipoEquipamiento, RequisitoServicio, FichaTecnica, DiagnosticoCapilar
    #PasoRutinaCliente, #PasoRutina,
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
"""
class PasoRutinaInline(admin.TabularInline):
    ""
    Permite editar PasoRutina directamente desde el formulario de Rutina.
    ""
    model = PasoRutina
    extra = 1  # Muestra 1 fila vacía al final para agregar nuevos pasos
    fields = ('orden', 'descripcion', 'frecuencia')
    ordering = ('orden',)

"""


@admin.register(Rutina)
class RutinaAdmin(admin.ModelAdmin):
    """
    Admin para gestionar Rutinas con protección de soft-delete.
    """
    list_display = ('nombre', 'version', 'estado', 'creada_por', 'fecha_creacion', 'cantidad_clientes')
    list_filter = ('estado', 'fecha_creacion')
    search_fields = ('nombre', 'objetivo')
    readonly_fields = ('fecha_creacion', 'fecha_obsoleta', 'version')
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


"""
@admin.register(PasoRutina)
class PasoRutinaAdmin(admin.ModelAdmin):
    ""
    Admin para gestionar Pasos de Rutina individualmente (si es necesario).
    ""
    list_display = ('plantilla', 'orden', 'descripcion', 'frecuencia')
    list_filter = ('plantilla', 'orden')
    search_fields = ('descripcion',)
    ordering = ('plantilla', 'orden')
    
    fieldsets = (
        ("Información del Paso", {
            'fields': ('plantilla', 'orden', 'descripcion', 'frecuencia')
        }),
    )

"""


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
"""
class PasoRutinaClienteInline(admin.TabularInline):
    ""
    Permite visualizar los pasos de la rutina del cliente.
    ""
    model = PasoRutinaCliente
    extra = 0  # No permite agregar nuevos pasos (son copias)
    fields = ('orden', 'descripcion', 'frecuencia', 'completado', 'fecha_completado')
    readonly_fields = ('orden', 'descripcion', 'frecuencia', 'completado', 'fecha_completado')

"""
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

"""
@admin.register(PasoRutinaCliente)
class PasoRutinaClienteAdmin(admin.ModelAdmin):
    ""
    Admin para visualizar los pasos de las rutinas del cliente.
    ""
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
        ""Los pasos se crean automáticamente con la rutina.""
        return False
"""

@admin.register(Configuracion)
class ConfiguracionAdmin(admin.ModelAdmin):
    """
    Controla que solo exista una configuración en el sistema.
    """
    list_display = ('__str__', 'monto_sena', 'max_dias_anticipacion')
    fieldsets = (
        ('Reglas Generales', {
            'fields': ('intervalo_turnos', 'max_dias_anticipacion')
        }),
        ('Política de Señas y Pagos', {
            'fields': ('monto_sena', 'tiempo_limite_pago_sena'),
            'description': 'Define cuánto deben pagar y cuánto tiempo tienen.'
        }),
        ('Cancelaciones y Reprogramaciones', {
            'fields': ('max_reprogramaciones', 'horas_limite_cancelacion'),
            'description': 'Reglas para evitar huecos en la agenda a último momento.'
        }),
    )

    def has_add_permission(self, request):
        # Si ya existe 1 configuración, no deja crear otra.
        if Configuracion.objects.exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        # No permitir borrar la configuración base
        return False
    
class HorarioLaboralInline(admin.TabularInline):
    """
    Permite editar los horarios DENTRO de la ficha del personal.
    Se ve como una planilla Excel.
    """
    model = HorarioLaboral
    extra = 0  # No muestra filas vacías extra innecesarias
    ordering = ['dia_semana', 'hora_inicio']
    fields = ['dia_semana', 'hora_inicio', 'hora_fin']
    # Tip visual: Mostrar el nombre del día claramente

@admin.register(Personal)
class PersonalAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido', 'rol', 'activo', 'skills_resumen')
    list_filter = ('rol', 'activo')
    search_fields = ('nombre', 'apellido', 'email')
    
    # Aquí incrustamos los horarios dentro del personal
    inlines = [HorarioLaboralInline]

    fieldsets = (
        ('Datos Personales', {
            'fields': ('usuario', 'nombre', 'apellido', 'email', 'telefono', 'color_calendario')
        }),
        ('Rol y Estado', {
            'fields': ('rol', 'activo')
        }),
        ('Habilidades Técnicas', {
            'fields': ('realiza_diagnostico', 'realiza_color', 'realiza_lavado'),
            'description': 'Define qué tipos de turno puede atender esta persona.'
        }),
    )

    def skills_resumen(self, obj):
        skills = []
        if obj.realiza_diagnostico: skills.append("Diagnóstico")
        if obj.realiza_color: skills.append("Color")
        if obj.realiza_lavado: skills.append("Lavado")
        return ", ".join(skills)
    skills_resumen.short_description = "Habilidades"

@admin.register(HorarioLaboral)
class HorarioLaboralAdmin(admin.ModelAdmin):
    """
    Por si se necesita ver todos los horarios juntos.
    """
    list_display = ('personal', 'get_dia', 'hora_inicio', 'hora_fin')
    list_filter = ('personal', 'dia_semana')
    ordering = ('personal', 'dia_semana', 'hora_inicio')

    def get_dia(self, obj):
        return obj.get_dia_semana_display()
    get_dia.short_description = "Día"


@admin.register(BloqueoAgenda)
class BloqueoAgendaAdmin(admin.ModelAdmin):
    list_display = ('get_afectado', 'motivo', 'fecha_inicio', 'fecha_fin', 'bloquea_todo_el_dia')
    list_filter = ('bloquea_todo_el_dia', 'personal', 'fecha_inicio')
    search_fields = ('motivo',)
    date_hierarchy = 'fecha_inicio'

    def get_afectado(self, obj):
        return obj.personal if obj.personal else "⛔ TODO EL SALÓN"
    get_afectado.short_description = "Afectado"


@admin.register(TipoEquipamiento)
class TipoEquipamientoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)
    ordering = ('nombre',)


@admin.register(Equipamiento)
class EquipamientoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'tipo', 'estado', 'ubicacion', 'is_active')
    list_filter = ('tipo', 'estado', 'is_active')
    search_fields = ('codigo', 'nombre')
    ordering = ('codigo',)


class RequisitoServicioInline(admin.TabularInline):
    """
    Inline para mostrar requisitos de equipamiento dentro de Servicio.
    Permite agregar/editar requisitos directamente desde el formulario del servicio.
    """
    model = RequisitoServicio
    extra = 1
    fields = ('tipo_equipamiento', 'obligatorio', 'cantidad_minima')
    verbose_name = "Requisito de Equipamiento"
    verbose_name_plural = "Requisitos de Equipamiento"


@admin.register(Servicio)
class ServicioAdminMejorado(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'precio_base', 'duracion_estimada')
    list_filter = ('categoria',)
    search_fields = ('nombre', 'descripcion')
    inlines = [RequisitoServicioInline]  # Agregar inline


@admin.register(RequisitoServicio)
class RequisitoServicioAdmin(admin.ModelAdmin):
    list_display = ('servicio', 'tipo_equipamiento', 'obligatorio', 'cantidad_minima')
    list_filter = ('obligatorio', 'servicio', 'tipo_equipamiento')
    search_fields = ('servicio__nombre', 'tipo_equipamiento__nombre')
    ordering = ('servicio', 'tipo_equipamiento')


@admin.register(FichaTecnica)
class FichaTecnicaAdmin(admin.ModelAdmin):
    list_display = ('detalle_turno', 'profesional_autor', 'porosidad_final', 'estado_general_final', 'fecha_registro')
    list_filter = ('fecha_registro', 'porosidad_final', 'estado_general_final', 'profesional_autor')
    search_fields = ('detalle_turno__turno__cliente__usuario__email', 'profesional_autor__email')
    readonly_fields = ('fecha_registro',)
    fields = (
        'detalle_turno', 'profesional_autor', 'formula', 'observaciones_proceso',
        'porosidad_final', 'estado_general_final', 'resultado_post_servicio',
        'foto_resultado', 'fecha_registro'
    )


@admin.register(DiagnosticoCapilar)
class DiagnosticoCapilarAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'profesional', 'tipo_cabello', 'porosidad_cabello', 'fecha_diagnostico')
    list_filter = ('fecha_diagnostico', 'tipo_cabello', 'grosor_cabello', 'porosidad_cabello', 'estado_general', 'profesional')
    search_fields = ('cliente__usuario__email', 'profesional__email', 'observaciones')
    readonly_fields = ('fecha_diagnostico',)
    fieldsets = (
        ('Cliente y Profesional', {
            'fields': ('cliente', 'profesional')
        }),
        ('Estado del Cabello', {
            'fields': ('tipo_cabello', 'grosor_cabello', 'porosidad_cabello', 'cuero_cabelludo', 'estado_general')
        }),
        ('Análisis y Resultados', {
            'fields': ('observaciones', 'recomendaciones', 'regla_diagnostico', 'rutina_sugerida')
        }),
        ('Registro', {
            'fields': ('fecha_diagnostico',),
            'classes': ('collapse',)
        }),
    )
    ordering = ('-fecha_diagnostico',)
