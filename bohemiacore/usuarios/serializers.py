from rest_framework import serializers
from django.db import transaction
from .models import Usuario, Cliente
from django.contrib.auth.password_validation import validate_password
from gestion.models import (
    TipoCabello,
    GrosorCabello,
    EstadoGeneral,
    PorosidadCabello,
    CueroCabelludo,
    Servicio 
)

class UsuarioPerfilReadSerializer(serializers.ModelSerializer):
    """
    Serializer de "solo lectura" (plano) para MOSTRAR el perfil.
    """
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    
    # Accedemos a los campos del Cliente (relación 1:1)
    zona = serializers.SerializerMethodField()
    numero = serializers.SerializerMethodField()
    fecha_nacimiento = serializers.SerializerMethodField()
    sexo = serializers.SerializerMethodField()
    redes = serializers.SerializerMethodField()
    
    # Campos con los IDs (para actualización)
    tipo_cabello = serializers.SerializerMethodField()
    grosor_cabello = serializers.SerializerMethodField()
    porosidad_cabello = serializers.SerializerMethodField()
    cuero_cabelludo = serializers.SerializerMethodField()
    estado_general = serializers.SerializerMethodField()
    historial_servicios = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            'email', 'first_name', 'last_name', 'zona', 'numero', 'fecha_nacimiento',
            'sexo', 'redes','is_staff', 'tipo_cabello', 'grosor_cabello',
            'porosidad_cabello', 'cuero_cabelludo', 'estado_general',
            'historial_servicios'
        ]
    
    def get_zona(self, obj):
        return obj.cliente.zona if hasattr(obj, 'cliente') else None
    
    def get_numero(self, obj):
        return obj.cliente.numero if hasattr(obj, 'cliente') else None
    
    def get_fecha_nacimiento(self, obj):
        return obj.cliente.fecha_nacimiento if hasattr(obj, 'cliente') else None
    
    def get_sexo(self, obj):
        return obj.cliente.sexo if hasattr(obj, 'cliente') else None
    
    def get_redes(self, obj):
        return obj.cliente.redes if hasattr(obj, 'cliente') else None
    
    def get_tipo_cabello(self, obj):
        if hasattr(obj, 'cliente') and obj.cliente.tipo_cabello:
            return obj.cliente.tipo_cabello.nombre
        return None
    
    def get_grosor_cabello(self, obj):
        if hasattr(obj, 'cliente') and obj.cliente.grosor_cabello:
            return obj.cliente.grosor_cabello.nombre
        return None
    
    def get_porosidad_cabello(self, obj):
        if hasattr(obj, 'cliente') and obj.cliente.porosidad_cabello:
            return obj.cliente.porosidad_cabello.nombre
        return None
    
    def get_cuero_cabelludo(self, obj):
        if hasattr(obj, 'cliente') and obj.cliente.cuero_cabelludo:
            return obj.cliente.cuero_cabelludo.nombre
        return None
    
    def get_estado_general(self, obj):
        if hasattr(obj, 'cliente') and obj.cliente.estado_general:
            return obj.cliente.estado_general.nombre
        return None
    
    def get_historial_servicios(self, obj):
        if hasattr(obj, 'cliente'):
            # Obtiene el histórico completo desde la propiedad @property del Cliente
            return [turno.id for turno in obj.cliente.historial_completo]
        return []


class UsuarioPerfilUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer (PADRE) para la actualización.
    Acepta datos del cliente directamente y los mapea correctamente.
    """
    # Mapeo de nombres del frontend al modelo
    tipo_cabello = serializers.PrimaryKeyRelatedField(
        queryset=TipoCabello.objects.all(), 
        allow_null=True, 
        required=False
    )
    grosor_cabello = serializers.PrimaryKeyRelatedField(
        queryset=GrosorCabello.objects.all(), 
        allow_null=True, 
        required=False
    )
    porosidad_cabello = serializers.PrimaryKeyRelatedField(
        queryset=PorosidadCabello.objects.all(), 
        allow_null=True, 
        required=False
    )
    cuero_cabelludo = serializers.PrimaryKeyRelatedField(
        queryset=CueroCabelludo.objects.all(), 
        allow_null=True, 
        required=False
    )
    estado_general = serializers.PrimaryKeyRelatedField(
        queryset=EstadoGeneral.objects.all(), 
        allow_null=True, 
        required=False
    )
    
    # Campos adicionales del cliente
    zona = serializers.CharField(required=False, allow_blank=True)
    numero = serializers.CharField(required=False, allow_blank=True)
    fecha_nacimiento = serializers.DateField(required=False, allow_null=True)
    sexo = serializers.CharField(required=False, allow_blank=True)
    redes = serializers.CharField(required=False, allow_blank=True)
    productos_actuales = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Usuario
        fields = [
            'first_name', 'last_name', 
            'tipo_cabello', 'grosor_cabello', 'porosidad_cabello',
            'cuero_cabelludo', 'estado_general',
            'zona', 'numero', 'fecha_nacimiento', 'sexo', 'redes',
            'productos_actuales'
        ]

    def to_internal_value(self, data):
        # Mapeo de nombres del frontend al modelo
        if 'porosidad' in data and 'porosidad_cabello' not in data:
            data['porosidad_cabello'] = data.pop('porosidad')
        if 'grosor' in data and 'grosor_cabello' not in data:
            data['grosor_cabello'] = data.pop('grosor')
        
        return super().to_internal_value(data)


    @transaction.atomic
    def update(self, instance, validated_data):
        # 1. Extraer campos del Usuario
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.save()

        # 2. Preparar datos para el Cliente
        cliente = instance.cliente
        
        # Mapeo de campos del Cliente
        cliente.zona = validated_data.get('zona', cliente.zona)
        cliente.numero = validated_data.get('numero', cliente.numero)
        cliente.fecha_nacimiento = validated_data.get('fecha_nacimiento', cliente.fecha_nacimiento)
        cliente.sexo = validated_data.get('sexo', cliente.sexo)
        cliente.redes = validated_data.get('redes', cliente.redes)
        
        # Relaciones ForeignKey
        if 'tipo_cabello' in validated_data:
            cliente.tipo_cabello = validated_data['tipo_cabello']
        if 'grosor_cabello' in validated_data:
            cliente.grosor_cabello = validated_data['grosor_cabello']
        if 'porosidad_cabello' in validated_data:
            cliente.porosidad_cabello = validated_data['porosidad_cabello']
        if 'cuero_cabelludo' in validated_data:
            cliente.cuero_cabelludo = validated_data['cuero_cabelludo']
        if 'estado_general' in validated_data:
            cliente.estado_general = validated_data['estado_general']
        
        cliente.save()

        return instance


class UsuarioDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'email', 'first_name', 'last_name']


class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    # Campos del Cliente
    tipo_cabello = serializers.PrimaryKeyRelatedField(
        queryset=TipoCabello.objects.all(), 
        allow_null=True, 
        required=False
    )
    grosor_cabello = serializers.PrimaryKeyRelatedField(
        queryset=GrosorCabello.objects.all(), 
        allow_null=True, 
        required=False
    )
    porosidad_cabello = serializers.PrimaryKeyRelatedField(
        queryset=PorosidadCabello.objects.all(), 
        allow_null=True, 
        required=False
    )
    cuero_cabelludo = serializers.PrimaryKeyRelatedField(
        queryset=CueroCabelludo.objects.all(), 
        allow_null=True, 
        required=False
    )
    estado_general = serializers.PrimaryKeyRelatedField(
        queryset=EstadoGeneral.objects.all(), 
        allow_null=True, 
        required=False
    )
    
    # Datos de contacto
    zona = serializers.CharField(required=False, allow_blank=True)
    numero = serializers.CharField(required=False, allow_blank=True)
    redes = serializers.CharField(required=False, allow_blank=True)
    sexo = serializers.CharField(required=False, allow_blank=True, default='F')
    fecha_nacimiento = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = Usuario
        fields = (
            'email', 'first_name', 'last_name', 'password', 'password2',
            'tipo_cabello', 'grosor_cabello', 'porosidad_cabello',
            'cuero_cabelludo', 'estado_general',
            'zona', 'numero', 'redes', 'sexo', 'fecha_nacimiento'
        )
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True}
        }

    def to_internal_value(self, data):
        # Mapeo de nombres del frontend al modelo
        if 'porosidad' in data and 'porosidad_cabello' not in data:
            data['porosidad_cabello'] = data.pop('porosidad')
        if 'grosor' in data and 'grosor_cabello' not in data:
            data['grosor_cabello'] = data.pop('grosor')
        
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        validate_password(attrs['password'])
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('password2')
        
        # Extraer datos del Cliente
        cliente_data = {
            'zona': validated_data.pop('zona', ''),
            'numero': validated_data.pop('numero', ''),
            'redes': validated_data.pop('redes', ''),
            'sexo': validated_data.pop('sexo', 'F'),
            'fecha_nacimiento': validated_data.pop('fecha_nacimiento', None),
            'tipo_cabello': validated_data.pop('tipo_cabello', None),
            'grosor_cabello': validated_data.pop('grosor_cabello', None),
            'porosidad_cabello': validated_data.pop('porosidad_cabello', None),
            'cuero_cabelludo': validated_data.pop('cuero_cabelludo', None),
            'estado_general': validated_data.pop('estado_general', None),
        }
        
        # Crear el Usuario
        user = Usuario.objects.create_user(**validated_data)
        
        # Crear el Cliente con todos los datos
        cliente = Cliente.objects.create(usuario=user, **cliente_data)
        
        # AUTOMÁTICO: Si hay datos capilares, crear diagnóstico
        if cliente.tipo_cabello or cliente.grosor_cabello or cliente.porosidad_cabello or cliente.cuero_cabelludo or cliente.estado_general:
            from gestion.models import DiagnosticoCapilar
            from gestion.views import DiagnosticoCapilarViewSet
            
            # Crear el diagnóstico inicial
            diag = DiagnosticoCapilar.objects.create(
                cliente=cliente,
                tipo_cabello=cliente.tipo_cabello,
                grosor_cabello=cliente.grosor_cabello,
                porosidad_cabello=cliente.porosidad_cabello,
                cuero_cabelludo=cliente.cuero_cabelludo,
                estado_general=cliente.estado_general
            )
            
            # Ejecutar el motor diagnóstico automáticamente
            viewset = DiagnosticoCapilarViewSet()
            viewset._ejecutar_motor_diagnostico(diag)
        
        return user


class SetNewPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        validate_password(attrs['password'])
        return attrs


class ClienteListSerializer(serializers.ModelSerializer):
    # Usamos SerializerMethodField para evitar crasheos si el usuario no existe
    id = serializers.ReadOnlyField(source='usuario.id')
    email = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    date_joined = serializers.SerializerMethodField()
    
    class Meta:
        model = Cliente
        fields = ['id', 'email', 'first_name', 'last_name', 'numero', 'date_joined', 'zona']

    def get_email(self, obj):
        return obj.usuario.email if obj.usuario else "Sin Usuario"

    def get_first_name(self, obj):
        return obj.usuario.first_name if obj.usuario else "---"

    def get_last_name(self, obj):
        return obj.usuario.last_name if obj.usuario else "---"

    def get_date_joined(self, obj):
        return obj.usuario.date_joined if obj.usuario else None