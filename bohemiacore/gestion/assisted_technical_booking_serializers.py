from django.utils import timezone
from rest_framework import serializers

from .models import (
    ConsentimientoAdvertenciaAsistido,
    PaymentIntent,
    Personal,
    Servicio,
    SolicitudTecnicaAsistidaOperacion,
    SolicitudTecnicaReserva,
)
from .serializers import (
    PaymentIntentPublicSerializer,
    SlotHoldPublicSerializer,
    TechnicalBookingRequestPublicSerializer,
)
from .assisted_technical_booking_services import next_assisted_action
from .assisted_slot_hold_services import assisted_hold_next_action


class StrictCommandSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            unexpected = set(data.keys()) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({
                    field: ['Este campo no está permitido.']
                    for field in sorted(unexpected)
                })
        return super().to_internal_value(data)


class AssistedTechnicalRequestCreateSerializer(StrictCommandSerializer):
    operation_id = serializers.UUIDField()
    alta_operation_id = serializers.UUIDField(required=False)
    cliente_id = serializers.IntegerField(min_value=1)
    servicio_ids = serializers.PrimaryKeyRelatedField(
        source='servicios',
        queryset=Servicio.objects.filter(activo=True),
        many=True,
        allow_empty=False,
    )
    fecha_preferida = serializers.DateField()
    hora_preferida = serializers.TimeField()
    personal_preferido_id = serializers.PrimaryKeyRelatedField(
        source='personal_preferido',
        queryset=Personal.objects.filter(activo=True),
        required=False,
        allow_null=True,
    )
    medio_solicitud = serializers.ChoiceField(choices=(
        SolicitudTecnicaReserva.MedioSolicitud.TELEFONO,
        SolicitudTecnicaReserva.MedioSolicitud.PRESENCIAL,
    ))

    def validate_fecha_preferida(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError(
                'La fecha preferida no puede estar en el pasado.'
            )
        return value

    def validate_servicio_ids(self, value):
        if len({service.pk for service in value}) != len(value):
            raise serializers.ValidationError(
                'No se permiten Servicios repetidos.'
            )
        return value


class AssistedConsentCommandSerializer(StrictCommandSerializer):
    operation_id = serializers.UUIDField()
    decision = serializers.ChoiceField(
        choices=ConsentimientoAdvertenciaAsistido.Decision.choices
    )
    motivo = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        max_length=500,
        trim_whitespace=True,
    )


class AssistedSlotHoldCreateSerializer(StrictCommandSerializer):
    operation_id = serializers.UUIDField()
    personal_id = serializers.IntegerField(min_value=1)
    starts_at = serializers.DateTimeField()


class AssistedSlotHoldReleaseSerializer(StrictCommandSerializer):
    operation_id = serializers.UUIDField()
    public_id = serializers.UUIDField()


class AssistedNextSlotQuerySerializer(StrictCommandSerializer):
    personal_id = serializers.IntegerField(min_value=1, required=False)


class AssistedPaymentOptionsQuerySerializer(StrictCommandSerializer):
    hold_public_id = serializers.UUIDField()


class AssistedPaymentIntentCreateSerializer(StrictCommandSerializer):
    operation_id = serializers.UUIDField()
    hold_public_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=PaymentIntent.Mode.choices)


class AssistedPaymentIntentPublicSerializer(PaymentIntentPublicSerializer):
    operation_id = serializers.SerializerMethodField()
    turno_estado = serializers.CharField(source='confirmed_turno.estado', allow_null=True)

    class Meta(PaymentIntentPublicSerializer.Meta):
        fields = (
            'operation_id', 'public_id', 'slot_hold_public_id', 'mode', 'currency',
            'required_amount', 'status', 'effective_status', 'expires_at',
            'paid_reconciled', 'confirmation_due', 'financial_threshold_reached', 'confirmed_turno_id',
            'turno_estado', 'tracking',
        )
        read_only_fields = fields

    def get_tracking(self, obj):
        return {'state': super().get_tracking(obj)['state']}

    def get_operation_id(self, _obj):
        return self.context.get('operation_id')


class AssistedSlotHoldPublicSerializer(SlotHoldPublicSerializer):
    operation_id = serializers.SerializerMethodField()
    next_action = serializers.SerializerMethodField()
    hold_notice = serializers.SerializerMethodField()

    class Meta(SlotHoldPublicSerializer.Meta):
        fields = SlotHoldPublicSerializer.Meta.fields + (
            'operation_id',
            'next_action',
            'hold_notice',
        )
        read_only_fields = fields

    def get_operation_id(self, _obj):
        return self.context.get('operation_id')

    def get_next_action(self, obj):
        return assisted_hold_next_action(obj, now=self._now())

    @staticmethod
    def get_hold_notice(_obj):
        return 'Este hold no equivale a un Turno confirmado.'


class AssistedTechnicalRequestPublicSerializer(
    TechnicalBookingRequestPublicSerializer
):
    cliente = serializers.SerializerMethodField()
    medio_solicitud = serializers.CharField(read_only=True)
    operation_id = serializers.SerializerMethodField()
    consentimiento = serializers.SerializerMethodField()
    siguiente_accion = serializers.SerializerMethodField()

    class Meta(TechnicalBookingRequestPublicSerializer.Meta):
        fields = TechnicalBookingRequestPublicSerializer.Meta.fields + (
            'cliente',
            'medio_solicitud',
            'operation_id',
            'consentimiento',
            'siguiente_accion',
        )
        read_only_fields = fields

    @staticmethod
    def get_cliente(obj):
        user = obj.cliente.usuario
        return {
            'id': obj.cliente_id,
            'display_name': user.get_full_name().strip() or 'Cliente sin nombre',
        }

    @staticmethod
    def get_operation_id(obj):
        operation = obj.operaciones_asistidas.filter(
            command=SolicitudTecnicaAsistidaOperacion.Command.CREATE
        ).first()
        return str(operation.operation_id) if operation else None

    @staticmethod
    def get_consentimiento(obj):
        consent = obj.consentimientos_asistidos.filter(
            evaluacion=obj.evaluacion_vigente
        ).first()
        if consent is None:
            return None
        return {
            'decision': consent.decision,
            'medio_solicitud': consent.medio_solicitud,
            'mensajes_comunicados': list(consent.warning_texts),
            'decided_at': consent.decided_at,
        }

    @staticmethod
    def get_siguiente_accion(obj):
        return next_assisted_action(obj)
