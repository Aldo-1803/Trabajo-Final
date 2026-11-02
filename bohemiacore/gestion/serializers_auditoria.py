"""
Serializers para el modelo Auditoria
"""
from rest_framework import serializers
from .models import Auditoria


class AuditoriaSerializer(serializers.ModelSerializer):
    """
    Serializer para Auditoria con campos adicionales calculados
    """
    usuario_nombre = serializers.SerializerMethodField(read_only=True)
    cambios = serializers.SerializerMethodField(read_only=True)
    cambios_texto = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Auditoria
        fields = [
            'id',
            'tabla',
            'registro_id',
            'usuario',
            'usuario_nombre',
            'fecha_hora',
            'accion',
            'valor_anterior',
            'valor_nuevo',
            'cambios',
            'cambios_texto',
            'ip_address'
        ]
        read_only_fields = fields
    
    def get_usuario_nombre(self, obj):
        """Retorna el nombre del usuario que realizó la acción"""
        if obj.usuario:
            return obj.usuario.get_full_name()
        return "Sistema/Anónimo"
    
    def get_cambios(self, obj):
        """Retorna solo los campos que cambiaron"""
        return obj.obtener_diferencias()
    
    def get_cambios_texto(self, obj):
        """Retorna los cambios en formato de texto legible"""
        return obj.obtener_diferencias_texto()


class AuditoriaListSerializer(serializers.ModelSerializer):
    """
    Serializer simplificado para listar auditorías
    """
    usuario_nombre = serializers.SerializerMethodField(read_only=True)
    accion_display = serializers.CharField(source='get_accion_display', read_only=True)
    cambios_count = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Auditoria
        fields = [
            'id',
            'tabla',
            'registro_id',
            'usuario_nombre',
            'fecha_hora',
            'accion',
            'accion_display',
            'cambios_count',
            'ip_address'
        ]
        read_only_fields = fields
    
    def get_usuario_nombre(self, obj):
        """Retorna el nombre del usuario que realizó la acción"""
        if obj.usuario:
            return obj.usuario.get_full_name()
        return "Sistema/Anónimo"
    
    def get_cambios_count(self, obj):
        """Retorna la cantidad de campos que cambiaron"""
        diferencias = obj.obtener_diferencias()
        if obj.accion == 'MODIFICACION':
            return len(diferencias)
        elif obj.accion == 'ALTA':
            return len(diferencias.get('valores', {}))
        elif obj.accion == 'BAJA':
            return len(diferencias.get('valores', {}))
        return 0
