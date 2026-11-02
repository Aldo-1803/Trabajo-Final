from datetime import datetime, date

from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper
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
        ingresos_expr = ExpressionWrapper(
            F('precio_historico') * F('cantidad'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )

        servicios_stats = OrdenItem.objects.filter(
            orden__estado='COMPLETADO',
            orden__creado_at__date__range=[start_date, end_date]
        ).values('producto__nombre').annotate(
            valor=Sum(ingresos_expr)
        ).order_by('-valor')[:5]

        # 2. Productos mas vendidos (Cantidad)
        productos_stats = OrdenItem.objects.filter(
            orden__estado='COMPLETADO',
            orden__creado_at__date__range=[start_date, end_date]
        ).values('producto__nombre').annotate(
            valor=Sum('cantidad')
        ).order_by('-valor')[:5]

        # 3. Rutinas mas frecuentes
        rutinas_stats = RutinaCliente.objects.filter(
            fecha_asignacion__date__range=[start_date, end_date]
        ).values('rutina_original__nombre').annotate(
            valor=Count('id')
        ).order_by('-valor')[:5]

        resumen = OrdenCompra.objects.filter(
            estado='COMPLETADO',
            creado_at__date__range=[start_date, end_date]
        ).aggregate(
            total_ingresos=Sum('total'),
            ordenes_count=Count('id')
        )

        cliente_mes = OrdenCompra.objects.filter(
            estado='COMPLETADO',
            creado_at__date__range=[start_date, end_date]
        ).values(
            'cliente__usuario__id',
            'cliente__usuario__first_name',
            'cliente__usuario__last_name',
            'cliente__usuario__email'
        ).annotate(
            total_ordenes=Count('id')
        ).order_by('-total_ordenes').first()

        cliente_nombre = None
        if cliente_mes:
            nombre = f"{cliente_mes.get('cliente__usuario__first_name', '').strip()} {cliente_mes.get('cliente__usuario__last_name', '').strip()}".strip()
            if nombre:
                cliente_nombre = nombre
            else:
                cliente_nombre = cliente_mes.get('cliente__usuario__email') or f"Cliente #{cliente_mes.get('cliente__id')}"

        return Response({
            'servicios': servicios_stats,
            'productos': productos_stats,
            'rutinas': rutinas_stats,
            'total_ingresos': float(resumen.get('total_ingresos') or 0),
            'ordenes_count': int(resumen.get('ordenes_count') or 0),
            'cliente_mes': {
                'id': cliente_mes.get('cliente__usuario__id') if cliente_mes else None,
                'nombre': cliente_nombre,
                'total_ordenes': cliente_mes.get('total_ordenes') if cliente_mes else 0,
            },
            'rango': {'inicio': start_date, 'fin': end_date}
        })
