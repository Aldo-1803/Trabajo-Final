import django_filters
from django.db.models import Q
from .models import Cliente


class ClienteFilter(django_filters.FilterSet):
    """
    Filtro para búsqueda y filtrado de clientes en el admin.
    Permite búsqueda global y filtrado por estado.
    """
    # Búsqueda global (nombre, apellido o email del usuario asociado)
    search = django_filters.CharFilter(
        method='filter_global_search', 
        label="Búsqueda rápida",
        help_text="Busca por nombre, apellido o email"
    )
    
    # Filtro por estado del cliente
    activo = django_filters.BooleanFilter(
        field_name='activo', 
        label="Cliente Activo"
    )
    
    # Filtro por estado del usuario asociado
    usuario_activo = django_filters.BooleanFilter(
        field_name='usuario__is_active',
        label="Usuario Activo"
    )

    class Meta:
        model = Cliente
        fields = ['activo']

    def filter_global_search(self, queryset, name, value):
        """Búsqueda global en múltiples campos"""
        if not value:
            return queryset
        
        return queryset.filter(
            Q(usuario__first_name__icontains=value) | 
            Q(usuario__last_name__icontains=value) | 
            Q(usuario__email__icontains=value)
        )
