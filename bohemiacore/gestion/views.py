from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
import rest_framework.permissions as permissions
from rest_framework import generics
from rest_framework.response import Response
from .models import TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral, Servicio
from .serializers import (
    TipoCabelloSerializer,
    GrosorCabelloSerializer,
    PorosidadCabelloSerializer,
    CueroCabelludoSerializer,
    EstadoGeneralSerializer,
    ServicioSerializer,
)



class CatalogoBaseListView(generics.ListAPIView):
    permission_classes = [AllowAny]

    def get_queryset(self):
        # self.queryset se define en las clases hijas
        # Filtramos para devolver solo los que están activos
        return self.queryset.filter(activo=True)


class TipoCabelloView(CatalogoBaseListView):
    queryset = TipoCabello.objects.all()
    serializer_class = TipoCabelloSerializer
    

class GrosorCabelloView(CatalogoBaseListView):
    queryset = GrosorCabello.objects.all()
    serializer_class = GrosorCabelloSerializer

class PorosidadCabelloView(CatalogoBaseListView):
    queryset = PorosidadCabello.objects.all()
    serializer_class = PorosidadCabelloSerializer

class CueroCabelludoView(CatalogoBaseListView):
    queryset = CueroCabelludo.objects.all()
    serializer_class = CueroCabelludoSerializer

class EstadoGeneralView(CatalogoBaseListView):
    queryset = EstadoGeneral.objects.all()
    serializer_class = EstadoGeneralSerializer

class TipoCabelloViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TipoCabello.objects.filter(activo=True)
    serializer_class = TipoCabelloSerializer
    permission_classes = [AllowAny]

class GrosorCabelloViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GrosorCabello.objects.filter(activo=True)
    serializer_class = GrosorCabelloSerializer
    permission_classes = [AllowAny]

class PorosidadCabelloViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PorosidadCabello.objects.filter(activo=True)
    serializer_class = PorosidadCabelloSerializer
    permission_classes = [AllowAny]

class CueroCabelludoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CueroCabelludo.objects.filter(activo=True)
    serializer_class = CueroCabelludoSerializer
    permission_classes = [AllowAny]

class EstadoGeneralViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EstadoGeneral.objects.filter(activo=True)
    serializer_class = EstadoGeneralSerializer
    permission_classes = [AllowAny]


class ServiciosQuimicosViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Un ViewSet que retorna *solamente* los servicios que
    afectan el historial químico del cliente, filtrados por
    las categorías "Diseño de Color" y "Turno de Complemento".
    """
    
    serializer_class = ServicioSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # 1. Definimos las categorías relevantes:
        categorias_relevantes = [
            "Diseño de Color",
            "Turno de Complemento"
        ]
        
        # 2. Filtramos los servicios:
        # Busca en el modelo Servicio, mira la 'categoria' relacionada,
        # y filtra por el 'nombre' de esa categoría usando la lista.
        return Servicio.objects.filter(
            categoria__nombre__in=categorias_relevantes
        ).order_by('nombre')