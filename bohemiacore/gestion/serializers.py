from rest_framework import serializers
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, 
    CueroCabelludo, EstadoGeneral
)

from usuarios.models import Usuario, Cliente

from .models import Servicio, CategoriaServicio, Turno

# 1. EL SERIALIZER BASE (El "Molde")
# Define los campos que TODOS los catálogos compartirán
class CatalogoBaseSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ['id', 'nombre', 'descripcion']
        abstract = True 

# 2. LOS SERIALIZERS ESPECÍFICOS (Heredan los campos)
# Ahora solo definimos el 'model' y heredamos los campos del molde

class TipoCabelloSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = TipoCabello

class GrosorCabelloSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = GrosorCabello

class PorosidadCabelloSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = PorosidadCabello

class CueroCabelludoSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = CueroCabelludo

class EstadoGeneralSerializer(CatalogoBaseSerializer):
    class Meta(CatalogoBaseSerializer.Meta):
        model = EstadoGeneral


class ServicioSerializer(serializers.ModelSerializer):
    """
    Serializer para el modelo Servicio.
    Muestra el nombre de la categoría en lugar de su ID.
    """
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    
    class Meta:
        model = Servicio
        # Solo enviamos los campos que el frontend necesita
        fields = ['id', 'nombre', 'categoria_nombre', 'duracion_estimada', 'precio_base']
   
class TurnoSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source='cliente.usuario.get_full_name', read_only=True)
    servicio_nombre = serializers.CharField(source='servicio.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(),
        required=False,
        allow_null=True
    )
    profesional = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.filter(is_staff=True), #
        required=False,
        allow_null=True
    )
    class Meta:
        model = Turno
        fields = [
            'id', 'cliente', 'cliente_nombre', 
            'servicio', 'servicio_nombre', 
            'profesional', 
            'fecha', 'hora_inicio', 'hora_fin_calculada', 
            'estado', 'estado_display', 'comprobante_pago', 'fecha_creacion'
        ]
        read_only_fields = ['id', 'hora_fin_calculada', 'fecha_creacion', 'cliente_nombre', 'servicio_nombre', 'estado_display']
        extra_kwargs = {
            'estado': {'required': False},
        }

class TurnoCreateSerializer(serializers.ModelSerializer):
    """
    Serializer ESPECÍFICO para crear turnos desde el cliente.
    Hace que el campo 'cliente' sea de solo lectura para el frontend,
    eliminando la validación de 'requerido'.
    """
    class Meta:
        model = Turno
        fields = ['servicio', 'fecha', 'hora_inicio', 'cliente', 'estado']
        # ALERTA: Esto es la Solución Definitiva
        read_only_fields = ['cliente', 'estado']
     