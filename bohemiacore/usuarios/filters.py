import django_filters
from django.db.models import Q
from .models import Usuario


class UsuarioFilter(django_filters.FilterSet):
    """
    Filtro para búsqueda y filtrado de usuarios en el admin.
    Permite búsqueda global y filtrado por estado/rol.
    """
    # Búsqueda global (nombre, apellido o email)
    search = django_filters.CharFilter(
        method='filter_global_search', 
        label="Búsqueda rápida",
        help_text="Busca por nombre, apellido o email"
    )
    
    # Filtro por estado (acepta 'true' o 'false' como strings)
    is_active = django_filters.CharFilter(
        method='filter_is_active',
        label="Estado Activo",
        help_text="true para activos, false para inactivos"
    )
    
    # Filtro por Rol (basado en si es staff)
    is_staff = django_filters.ChoiceFilter(
        choices=[
            ('false', 'Cliente'),
            ('true', 'Personal/Staff'),
        ], 
        method='filter_by_staff',
        label="Rol del usuario"
    )
    
    # Mantener 'rol' para retrocompatibilidad
    rol = django_filters.ChoiceFilter(
        choices=[
            ('cliente', 'Cliente'),
            ('staff', 'Personal/Staff'),
        ], 
        method='filter_by_role',
        label="Rol del usuario"
    )

    class Meta:
        model = Usuario
        fields = ['is_active']

    def filter_global_search(self, queryset, name, value):
        """Búsqueda global en múltiples campos"""
        if not value:
            return queryset
        
        return queryset.filter(
            Q(first_name__icontains=value) | 
            Q(last_name__icontains=value) | 
            Q(email__icontains=value)
        )
    
    def filter_is_active(self, queryset, name, value):
        """
        Filtra por estado de usuario.
        Acepta 'true' o 'false' como strings y convierte a booleano.
        """
        if not value:
            return queryset
        
        # Convertir string a booleano
        if value.lower() == 'true':
            return queryset.filter(is_active=True)
        elif value.lower() == 'false':
            return queryset.filter(is_active=False)
        
        return queryset

    def filter_by_staff(self, queryset, name, value):
        """Filtra por rol usando is_staff: 'true' para staff, 'false' para clientes"""
        if not value:
            return queryset
        
        if value.lower() == 'true':
            return queryset.filter(is_staff=True)
        elif value.lower() == 'false':
            return queryset.filter(is_staff=False)
        
        return queryset

    def filter_by_role(self, queryset, name, value):
        """Filtra por rol: cliente o personal/staff"""
        if value == 'cliente':
            return queryset.filter(is_staff=False, cliente__isnull=False)
        if value == 'staff':
            return queryset.filter(is_staff=True)
        return queryset
