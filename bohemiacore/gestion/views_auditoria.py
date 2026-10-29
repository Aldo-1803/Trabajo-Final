"""
ViewSet para el modelo Auditoria - Solo lectura (ReadOnly)
Acceso restringido solo a administradores
"""
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.db import models as dj_models
from django.core.exceptions import ValidationError
from .models import (
    Auditoria,
    Personal,
    Servicio,
    Producto,
    Promocion,
    ReglaDiagnostico,
    ConfiguracionDiagnostico,
    DiagnosticoCapilar,
    Rutina,
    RutinaCliente,
    HorarioLaboral,
    BloqueoAgenda,
    Turno,
    DetalleTurno,
    OrdenCompra,
    OrdenItem,
    Pago,
)
from .serializers_auditoria import AuditoriaSerializer, AuditoriaListSerializer


class AuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet de auditoría para visualizar el log de cambios en el sistema.
    Solo administradores pueden acceder.
    
    Endpoints:
    - GET /api/auditoria/ - Lista todas las auditorías
    - GET /api/auditoria/{id}/ - Detalle de una auditoría
    
    Filtros disponibles:
    - tabla: Filtrar por tabla (Ej: Usuario, Turno, Servicio)
    - accion: Filtrar por tipo de acción (ALTA, MODIFICACION, BAJA)
    - usuario: Filtrar por usuario que realizó la acción
    - fecha_hora: Filtrar por rango de fechas
    """
    
    queryset = Auditoria.objects.all().order_by('-fecha_hora')
    permission_classes = [permissions.IsAdminUser]  # Solo administradores
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]
    filterset_fields = ['tabla', 'accion', 'usuario', 'fecha_hora']
    search_fields = ['tabla', 'usuario__first_name', 'usuario__last_name', 'usuario__email', 'ip_address']
    ordering_fields = ['fecha_hora', 'tabla', 'accion', 'usuario']
    ordering = ['-fecha_hora']
    
    def get_serializer_class(self):
        """
        Usa serializer simplificado para listas, completo para detalles
        """
        if self.action == 'list':
            return AuditoriaListSerializer
        return AuditoriaSerializer
    
    def get_queryset(self):
        """
        Aplica filtros adicionales si es necesario
        """
        queryset = super().get_queryset()
        
        # Filtrar por tabla si se proporciona como query param
        tabla = self.request.query_params.get('tabla', None)
        if tabla:
            queryset = queryset.filter(tabla=tabla)
        
        # Filtrar por usuario si se proporciona
        usuario_id = self.request.query_params.get('usuario_id', None)
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)
        
        # Filtrar por acción
        accion = self.request.query_params.get('accion', None)
        if accion:
            queryset = queryset.filter(accion=accion)
        
        return queryset


class HistorialAuditoriaViewSet(viewsets.ViewSet):
    """
    ViewSet para exponer historial de django-simple-history.
    Solo administradores pueden acceder.
    """

    permission_classes = [permissions.IsAdminUser]

    HISTORY_MODELS = [
        Personal,
        Servicio,
        Producto,
        Promocion,
        ReglaDiagnostico,
        ConfiguracionDiagnostico,
        DiagnosticoCapilar,
        Rutina,
        RutinaCliente,
        HorarioLaboral,
        BloqueoAgenda,
        Turno,
        DetalleTurno,
        OrdenCompra,
        OrdenItem,
        Pago,
    ]

    SAFE_REVERT_MODELS = [
        Personal,
        Servicio,
        Producto,
        Promocion,
        HorarioLaboral,
        BloqueoAgenda,
    ]

    SAFE_FIELD_TYPES = (
        dj_models.CharField,
        dj_models.TextField,
        dj_models.IntegerField,
        dj_models.DecimalField,
        dj_models.BooleanField,
        dj_models.DateField,
        dj_models.DateTimeField,
        dj_models.TimeField,
        dj_models.FloatField,
    )

    def list(self, request):
        tabla = request.query_params.get('tabla')
        accion = request.query_params.get('accion')
        usuario = request.query_params.get('usuario')
        busqueda = request.query_params.get('search')
        ordering = request.query_params.get('ordering', '-fecha_hora')

        registros = []

        for model in self.HISTORY_MODELS:
            for history in model.history.all():
                registro = self._build_history_record(history, model)
                if self._passes_filters(registro, tabla, accion, usuario, busqueda):
                    registros.append(registro)

        registros = self._apply_ordering(registros, ordering)
        return Response(registros)

    def retrieve(self, request, pk=None):
        if not pk or ':' not in pk:
            return Response({'detail': 'ID inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        model_key, history_id = pk.split(':', 1)
        model = self._get_model_by_key(model_key)
        if not model:
            return Response({'detail': 'Modelo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        history = model.history.filter(history_id=history_id).first()
        if not history:
            return Response({'detail': 'Historial no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        registro = self._build_history_record(history, model)
        return Response(registro)

    @action(detail=True, methods=['post'], url_path='revertir')
    def revertir(self, request, pk=None):
        if not pk or ':' not in pk:
            return Response({'detail': 'ID inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        model_key, history_id = pk.split(':', 1)
        model = self._get_model_by_key(model_key)
        if not model:
            return Response({'detail': 'Modelo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if model not in self.SAFE_REVERT_MODELS:
            return Response({'detail': 'Reversión no permitida para este modelo.'}, status=status.HTTP_403_FORBIDDEN)

        history = model.history.filter(history_id=history_id).first()
        if not history:
            return Response({'detail': 'Historial no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if history.history_type != '~':
            return Response({'detail': 'Solo se permiten reversiones de modificaciones.'}, status=status.HTTP_400_BAD_REQUEST)

        instance = model.objects.filter(pk=history.instance.pk if history.instance else None).first()
        if not instance:
            return Response({'detail': 'Registro actual no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        safe_fields = self._get_safe_revert_fields(model)
        if not safe_fields:
            return Response({'detail': 'No hay campos seguros para revertir.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                for field_name in safe_fields:
                    setattr(instance, field_name, getattr(history, field_name))

                if hasattr(instance, '_change_reason'):
                    instance._change_reason = 'Revertido desde auditoría'

                instance.full_clean()
                instance.save()

            registro = self._build_history_record(history, model)
            return Response({'detail': 'Reversión aplicada.', 'registro': registro})
        except ValidationError as exc:
            return Response({'detail': exc.message_dict}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'detail': f'Error al revertir: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_model_by_key(self, model_key):
        for model in self.HISTORY_MODELS:
            if model._meta.model_name == model_key:
                return model
        return None

    def _apply_ordering(self, registros, ordering):
        reverse = ordering.startswith('-')
        campo = ordering.lstrip('-')
        if campo not in ['fecha_hora', 'tabla', 'accion', 'usuario']:
            campo = 'fecha_hora'

        def key_fn(item):
            if campo == 'usuario':
                return item.get('usuario_nombre') or ''
            return item.get(campo) or ''

        return sorted(registros, key=key_fn, reverse=reverse)

    def _passes_filters(self, registro, tabla, accion, usuario, busqueda):
        if tabla and tabla.lower() not in (registro.get('tabla') or '').lower():
            return False
        if accion and accion != registro.get('accion'):
            return False
        if usuario and usuario.lower() not in (registro.get('usuario_nombre') or '').lower():
            return False
        if busqueda:
            haystack = ' '.join([
                registro.get('tabla') or '',
                registro.get('usuario_nombre') or '',
                str(registro.get('registro_id') or ''),
            ]).lower()
            if busqueda.lower() not in haystack:
                return False
        return True

    def _build_history_record(self, history, model):
        accion = self._map_history_action(history.history_type)
        current_values = self._serialize_history_values(history)
        previous = getattr(history, 'prev_record', None)
        previous_values = self._serialize_history_values(previous) if previous else None

        cambios = self._diff_values(previous_values, current_values, accion)
        cambios_count = 0
        if accion == 'MODIFICACION':
            cambios_count = len(cambios)
        elif accion in ['ALTA', 'BAJA']:
            cambios_count = len(cambios.get('valores', {})) if isinstance(cambios, dict) else 0

        return {
            'id': f"{model._meta.model_name}:{history.history_id}",
            'tabla': model.__name__,
            'registro_id': history.instance.pk if history.instance else None,
            'usuario_nombre': self._get_usuario_nombre(history.history_user),
            'fecha_hora': history.history_date,
            'accion': accion,
            'valor_anterior': previous_values if accion != 'ALTA' else None,
            'valor_nuevo': current_values if accion != 'BAJA' else None,
            'cambios': cambios,
            'cambios_count': cambios_count,
            'ip_address': None,
            'fuente': 'HISTORY',
            'can_revert': self._can_revert(model, history),
            'revert_disabled_reason': self._revert_disabled_reason(model, history),
        }

    def _get_usuario_nombre(self, usuario):
        if not usuario:
            return 'Sistema/Anónimo'
        nombre = getattr(usuario, 'get_full_name', None)
        if callable(nombre):
            full_name = nombre()
            return full_name or usuario.email or usuario.username
        return str(usuario)

    def _map_history_action(self, history_type):
        if history_type == '+':
            return 'ALTA'
        if history_type == '-':
            return 'BAJA'
        return 'MODIFICACION'

    def _can_revert(self, model, history):
        if model not in self.SAFE_REVERT_MODELS:
            return False
        if history.history_type != '~':
            return False
        return model.objects.filter(pk=history.instance.pk if history.instance else None).exists()

    def _revert_disabled_reason(self, model, history):
        if model not in self.SAFE_REVERT_MODELS:
            return 'Modelo no permitido'
        if history.history_type != '~':
            return 'Solo se permiten modificaciones'
        if not model.objects.filter(pk=history.instance.pk if history.instance else None).exists():
            return 'Registro actual no encontrado'
        return None

    def _get_safe_revert_fields(self, model):
        campos = []
        for field in model._meta.fields:
            if field.primary_key:
                continue
            if field.is_relation:
                continue
            if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
                continue
            if not isinstance(field, self.SAFE_FIELD_TYPES):
                continue
            campos.append(field.name)
        return campos

    def _serialize_history_values(self, history):
        if not history:
            return None

        excluded = {
            'history_id',
            'history_date',
            'history_type',
            'history_user',
            'history_change_reason',
        }

        data = {}
        for field in history._meta.fields:
            if field.name in excluded:
                continue
            value = getattr(history, field.name, None)
            if hasattr(value, 'isoformat'):
                value = value.isoformat()
            data[field.name] = value
        return data

    def _diff_values(self, previous, current, accion):
        if accion == 'ALTA':
            return {'accion': 'CREACIÓN', 'valores': current or {}}
        if accion == 'BAJA':
            return {'accion': 'ELIMINACIÓN', 'valores': previous or {}}
        if not previous or not current:
            return {}

        cambios = {}
        for campo, valor_nuevo in current.items():
            valor_anterior = previous.get(campo)
            if valor_anterior != valor_nuevo:
                cambios[campo] = {
                    'antes': valor_anterior,
                    'ahora': valor_nuevo,
                }
        return cambios
