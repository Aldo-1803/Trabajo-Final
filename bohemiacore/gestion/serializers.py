from rest_framework import serializers
from .models import (
    TipoCabello, GrosorCabello, PorosidadCabello, 
    CueroCabelludo, EstadoGeneral
)

from .models import Servicio, CategoriaServicio

# 1. EL SERIALIZER BASE (El "Molde")
# Define los campos que TODOS los catálogos compartirán
class CatalogoBaseSerializer(serializers.ModelSerializer):
    class Meta:
        # Note que no definimos el 'model' aquí, solo los campos
        fields = ['id', 'nombre', 'descripcion']
        abstract = True # No es una clase real, solo un molde

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

    # Esto hace que en lugar de mostrar 'categoria: 1', 
    # muestre 'categoria: "Diseño de Color"' (más legible)
    categoria = serializers.StringRelatedField() 

    class Meta:
        model = Servicio
        # Solo enviamos los campos que el frontend necesita
        fields = ['id', 'nombre', 'categoria']
