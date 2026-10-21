from datetime import datetime, date

from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from gestion.models import OrdenCompra, OrdenItem, RutinaCliente


class DashboardStatsViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminUser]

    def get_date_range(self, periodo, valor, anio):
        """Calcula fecha inicio y fin segun el filtro."""
        anio = int(anio)
        if periodo == 'mes':
            mes = int(valor)
            start_date = date(anio, mes, 1)
            if mes == 12:
                end_date = date(anio + 1, 1, 1)
            else:
                end_date = date(anio, mes + 1, 1)
        elif periodo == 'trimestre':
            # T1: 1, T2: 4, T3: 7, T4: 10
            mes_inicio = (int(valor) - 1) * 3 + 1
            start_date = date(anio, mes_inicio, 1)
            mes_fin = mes_inicio + 3
            if mes_fin > 12:
                end_date = date(anio + 1, 1, 1)
            else:
                end_date = date(anio, mes_fin, 1)
        else:  # anual
            start_date = date(anio, 1, 1)
            end_date = date(anio + 1, 1, 1)

        return start_date, end_date

    def list(self, request):
        periodo = request.query_params.get('periodo', 'mes')  # mes, trimestre, anual
        valor = request.query_params.get('valor', datetime.now().month)
        anio = request.query_params.get('anio', datetime.now().year)

        start_date, end_date = self.get_date_range(periodo, valor, anio)

        # 1. Top Servicios (Ingresos por categoria de servicio/producto)
        servicios_stats = OrdenItem.objects.filter(
            orden__estado='COMPLETADO',
            orden__creado_at__date__range=[start_date, end_date]
        ).values('producto__nombre').annotate(
            valor=Sum('precio_historico')
        ).order_by('-valor')[:5]

        # 2. Productos mas vendidos (Cantidad)
        productos_stats = OrdenItem.objects.filter(
            orden__estado='COMPLETADO',
            orden__creado_at__date__range=[start_date, end_date]
        ).values('producto__nombre').annotate(
            valor=Count('id')
        ).order_by('-valor')[:5]

        # 3. Rutinas mas frecuentes
        rutinas_stats = RutinaCliente.objects.filter(
            fecha_asignacion__date__range=[start_date, end_date]
        ).values('rutina_original__nombre').annotate(
            valor=Count('id')
        ).order_by('-valor')[:5]

        return Response({
            'servicios': servicios_stats,
            'productos': productos_stats,
            'rutinas': rutinas_stats,
            'rango': {'inicio': start_date, 'fin': end_date}
        })
