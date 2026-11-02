from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Usuario, Cliente
from django.utils.html import format_html

@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    """
    Admin personalizado para Usuario (CustomUser)
    ⚠️ IMPORTANTE: "Desactivar" un usuario NO lo elimina, solo lo desactiva temporalmente.
    Los datos se mantienen en el sistema y pueden ser recuperados.
    """
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active', 'estado_badge')
    list_filter = ('is_staff', 'is_active', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-date_joined',)  # Mostrar primero los más nuevos
    
    # Campos a mostrar en el formulario de edición
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Información Personal', {'fields': ('first_name', 'last_name')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas importantes', {'fields': ('last_login', 'date_joined')}),
    )
    
    # Campos a mostrar al crear nuevo usuario
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
        ('Permisos', {'fields': ('is_staff', 'is_superuser')}),
    )
    
    readonly_fields = ('date_joined', 'last_login')
    
    def get_queryset(self, request):
        """
        Por defecto muestra solo usuarios ACTIVOS.
        Los admins pueden ver inactivos usando el filtro.
        """
        queryset = super().get_queryset(request)
        # Por defecto, filtrar solo activos
        if not request.GET.get('is_active'):
            queryset = queryset.filter(is_active=True)
        return queryset
    
    def estado_badge(self, obj):
        """Muestra un badge de estado (Activo/Inactivo)"""
        if obj.is_active:
            return format_html(
                '<span style="background-color: #6B9C7A; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">ACTIVO</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #C73E3E; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">INACTIVO</span>'
            )
    estado_badge.short_description = 'Estado'
    
    actions = ['desactivar_usuarios', 'activar_usuarios']
    
    def desactivar_usuarios(self, request, queryset):
        """Acción para desactivar TEMPORALMENTE (no eliminar) usuarios seleccionados"""
        updated = queryset.update(is_active=False)
        # También desactivar sus clientes asociados
        for usuario in queryset:
            if hasattr(usuario, 'cliente'):
                usuario.cliente.activo = False
                usuario.cliente.save()
        
        self.message_user(request, f'{updated} usuario(s) desactivado(s) temporalmente. Los datos se mantienen en el sistema.')
    desactivar_usuarios.short_description = "⏸️ Desactivar temporalmente (sin eliminar)"
    
    def activar_usuarios(self, request, queryset):
        """Acción para reactivar usuarios desactivados"""
        updated = queryset.update(is_active=True)
        # También reactivar sus clientes asociados
        for usuario in queryset:
            if hasattr(usuario, 'cliente'):
                usuario.cliente.activo = True
                usuario.cliente.save()
        
        self.message_user(request, f'{updated} usuario(s) reactivado(s) correctamente.')
    activar_usuarios.short_description = "✅ Reactivar (recuperar acceso)"


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    """
    Admin para listar Clientes
    """
    list_display = ('usuario_email', 'usuario_nombre', 'activo', 'fecha_creacion', 'estado_badge')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('usuario__email', 'usuario__first_name', 'usuario__last_name')
    readonly_fields = ('usuario', 'fecha_creacion', 'fecha_actualizacion')
    
    fieldsets = (
        ('Usuario Asociado', {'fields': ('usuario',)}),
        ('Información Personal', {'fields': ('zona', 'redes', 'numero', 'fecha_nacimiento', 'sexo')}),
        ('Diagnóstico', {'fields': ('tipo_cabello', 'grosor_cabello', 'porosidad_cabello', 'cuero_cabelludo', 'estado_general')}),
        ('Productos', {'fields': ('productos_actuales',)}),
        ('Estado', {'fields': ('activo',)}),
        ('Auditoría', {'fields': ('fecha_creacion', 'fecha_actualizacion')}),
    )
    
    def get_queryset(self, request):
        """
        Filtra clientes para mostrar solo los de usuarios activos.
        Esto previene desincronización cuando se desactivan usuarios.
        """
        queryset = super().get_queryset(request)
        return queryset.filter(usuario__is_active=True).select_related('usuario')
    
    def usuario_email(self, obj):
        """Muestra el email del usuario asociado"""
        return obj.usuario.email if obj.usuario else "—"
    usuario_email.short_description = "Email del Usuario"
    
    def usuario_nombre(self, obj):
        """Muestra el nombre completo del usuario asociado"""
        if obj.usuario:
            return f"{obj.usuario.first_name} {obj.usuario.last_name}".strip()
        return "—"
    usuario_nombre.short_description = "Nombre"
    
    def estado_badge(self, obj):
        """Muestra un badge de estado (Activo/Inactivo)"""
        if obj.activo:
            return format_html(
                '<span style="background-color: #6B9C7A; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">ACTIVO</span>'
            )
        else:
            return format_html(
                '<span style="background-color: #C73E3E; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">INACTIVO</span>'
            )
    estado_badge.short_description = 'Estado'
