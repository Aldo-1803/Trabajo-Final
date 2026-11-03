from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from .models import Usuario, Cliente
from django.utils.html import format_html


# Role and permission membership is managed only through semantic services.
if admin.site.is_registered(Group):
    admin.site.unregister(Group)

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
    )
    
    readonly_fields = (
        'date_joined',
        'last_login',
        'is_active',
        'is_staff',
        'is_superuser',
        'groups',
        'user_permissions',
    )
    actions = None

    def has_add_permission(self, request):
        """Accounts must be created through a semantic onboarding flow."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Accounts are deactivated only through the semantic service."""
        return False
    
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
    
@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    """
    Admin para listar Clientes
    """
    list_display = ('usuario_email', 'usuario_nombre', 'activo', 'fecha_creacion', 'estado_badge')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('usuario__email', 'usuario__first_name', 'usuario__last_name')
    readonly_fields = (
        'usuario',
        'activo',
        'fecha_creacion',
        'fecha_actualizacion',
    )
    actions = None

    def has_add_permission(self, request):
        """Client profiles are created only by semantic onboarding flows."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Do not allow profile links to be removed through generic admin."""
        return False
    
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
