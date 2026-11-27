from datetime import date

from django.db.models import Sum, Count, F, DecimalField, ExpressionWrapper
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from gestion.models import OrdenCompra, OrdenItem, RutinaCliente
from gestion.permissions import CanViewGeneralOrFinancialReports
from usuarios.roles import BusinessPermission


class DashboardStatsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, CanViewGeneralOrFinancialReports]

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
        today = timezone.localdate(
            timezone=timezone.get_default_timezone(),
        )
        valor = request.query_params.get('valor', today.month)
        anio = request.query_params.get('anio', today.year)

        start_date, end_date = self.get_date_range(periodo, valor, anio)

        orders = OrdenCompra.objects.filter(
            estado='COMPLETADO',
            creado_at__date__range=[start_date, end_date]
        )
        can_view_general = request.user.has_perm(BusinessPermission.VIEW_REPORTS)
        can_view_financial = request.user.has_perm(
            BusinessPermission.VIEW_FINANCIAL_REPORTS
        )

        response_data = {
            'rango': {'inicio': start_date, 'fin': end_date},
        }

        if can_view_general:
            productos_stats = OrdenItem.objects.filter(
                orden__in=orders,
            ).values('producto__nombre').annotate(
                valor=Sum('cantidad')
            ).order_by('-valor')[:5]

            rutinas_stats = RutinaCliente.objects.filter(
                fecha_asignacion__date__range=[start_date, end_date]
            ).values('rutina_original__nombre').annotate(
                valor=Count('id')
            ).order_by('-valor')[:5]

            cliente_mes = orders.values(
                'cliente__usuario__id',
                'cliente__usuario__first_name',
                'cliente__usuario__last_name',
            ).annotate(
                total_ordenes=Count('id')
            ).order_by('-total_ordenes', 'cliente__usuario__id').first()

            cliente_nombre = None
            if cliente_mes:
                cliente_nombre = (
                    f"{cliente_mes.get('cliente__usuario__first_name', '').strip()} "
                    f"{cliente_mes.get('cliente__usuario__last_name', '').strip()}"
                ).strip()
                if not cliente_nombre:
                    cliente_nombre = (
                        f"Cliente #{cliente_mes['cliente__usuario__id']}"
                    )

            response_data.update({
                'productos': productos_stats,
                'rutinas': rutinas_stats,
                'ordenes_count': orders.count(),
                'cliente_mes': {
                    'id': (
                        cliente_mes.get('cliente__usuario__id')
                        if cliente_mes else None
                    ),
                    'nombre': cliente_nombre,
                    'total_ordenes': (
                        cliente_mes.get('total_ordenes')
                        if cliente_mes else 0
                    ),
                },
            })

        if can_view_financial:
            ingresos_expr = ExpressionWrapper(
                F('precio_historico') * F('cantidad'),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
            servicios_stats = OrdenItem.objects.filter(
                orden__in=orders,
            ).values('producto__nombre').annotate(
                valor=Sum(ingresos_expr)
            ).order_by('-valor')[:5]
            resumen = orders.aggregate(total_ingresos=Sum('total'))
            response_data.update({
                'servicios': servicios_stats,
                'total_ingresos': float(
                    resumen.get('total_ingresos') or 0
                ),
            })

        return Response(response_data)
