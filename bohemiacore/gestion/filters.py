# gestion/filters.py
import django_filters
from django.db.models import Q
from .models import (
    Producto, Turno, Personal, Servicio, Rutina, 
    Equipamiento, TipoEquipamiento, DiagnosticoCapilar, Configuracion
)
from usuarios.models import Usuario, Cliente

class ProductoFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains')
    categoria = django_filters.NumberFilter(field_name='categoria__id')
    stock_bajo = django_filters.BooleanFilter(method='filter_stock')
    precio_min = django_filters.NumberFilter(field_name='precio', lookup_expr='gte')
    precio_max = django_filters.NumberFilter(field_name='precio', lookup_expr='lte')

    class Meta:
        model = Producto
        fields = ['activo', 'categoria']

    def filter_stock(self, queryset, name, value):
        return queryset.filter(stock__lte=5) if value else queryset

class TurnoFilter(django_filters.FilterSet):
    fecha_desde = django_filters.DateFilter(field_name='fecha', lookup_expr='gte')
    fecha_hasta = django_filters.DateFilter(field_name='fecha', lookup_expr='lte')
    cliente = django_filters.NumberFilter(field_name='cliente__id')
    profesional = django_filters.NumberFilter(field_name='profesional__id')

    class Meta:
        model = Turno
        fields = ['estado', 'fecha']

class PersonalFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains')
    rol = django_filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Personal
        fields = ['activo', 'rol']

class ServicioFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains')
    categoria = django_filters.NumberFilter(field_name='categoria__id')
    precio_min = django_filters.NumberFilter(field_name='precio_base', lookup_expr='gte')
    precio_max = django_filters.NumberFilter(field_name='precio_base', lookup_expr='lte')

    class Meta:
        model = Servicio
        fields = ['activo', 'categoria']

class ClienteFilter(django_filters.FilterSet):
    # Búsqueda que abarca nombre y apellido del usuario asociado
    nombre = django_filters.CharFilter(method='filter_full_name')
    email = django_filters.CharFilter(field_name='usuario__email', lookup_expr='icontains')
    telefono = django_filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Cliente
        fields = ['activo']

    def filter_full_name(self, queryset, name, value):
        return queryset.filter(
            Q(usuario__first_name__icontains=value) | 
            Q(usuario__last_name__icontains=value)
        )

class RutinaFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains')
    descripcion = django_filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = Rutina
        fields = ['estado']

class UsuarioFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(field_name='first_name', lookup_expr='icontains')
    email = django_filters.CharFilter(lookup_expr='icontains')
    telefono = django_filters.CharFilter(field_name='cliente__telefono', lookup_expr='icontains')
    
    class Meta:
        model = Usuario
        fields = ['is_active', 'is_staff']

class TipoEquipamientoFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = TipoEquipamiento
        fields = ['nombre']

class EquipamientoFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains')
    tipo = django_filters.NumberFilter(field_name='tipo__id')
    estado = django_filters.CharFilter(lookup_expr='icontains')
    
    class Meta:
        model = Equipamiento
        fields = ['is_active', 'tipo', 'estado']

class DiagnosticoCapilarFilter(django_filters.FilterSet):
    cliente = django_filters.NumberFilter(field_name='cliente__id')
    profesional = django_filters.NumberFilter(field_name='profesional__id')
    
    class Meta:
        model = DiagnosticoCapilar
        fields = ['cliente', 'profesional']

class ConfiguracionFilter(django_filters.FilterSet):
    
    class Meta:
        model = Configuracion
        fields = []