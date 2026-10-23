from datetime import datetime
from django.utils import timezone
from django.conf import settings
from .models import FichaTecnica, Servicio
import mercadopago

class SaludCapilarService:
    @staticmethod
    def obtener_bloqueo_salud_capilar(cliente, servicios_nuevos_ids):
        """
        Verifica si el cliente está bloqueado biológicamente para realizarse nuevos servicios.
        Recibe una lista de IDs de los servicios que el cliente intenta reservar.
        """

        servicios_nuevos = Servicio.objects.filter(
            id__in=servicios_nuevos_ids,
            es_quimico_agresivo=True
        )

        if not servicios_nuevos.exists():
            return None

        servicio_critico_solicitado = servicios_nuevos.order_by('-dias_espera_bloqueo').first()

        ultima_ficha = (
            FichaTecnica.objects
            .select_related('detalle_turno__servicio', 'detalle_turno__turno')
            .filter(
                detalle_turno__turno__cliente=cliente,
                detalle_turno__servicio__es_quimico_agresivo=True,
            )
            .order_by('-fecha_registro')
            .first()
        )

        if not ultima_ficha:
            return None

        ultimo_detalle_quimico = ultima_ficha.detalle_turno
        servicio_origen = ultimo_detalle_quimico.servicio

        ultimo_servicio_dt = datetime.combine(
            ultimo_detalle_quimico.turno.fecha,
            ultimo_detalle_quimico.turno.hora_inicio
        )
        if timezone.is_naive(ultimo_servicio_dt):
            ultimo_servicio_dt = timezone.make_aware(
                ultimo_servicio_dt,
                timezone.get_current_timezone()
            )

        dias_transcurridos = (timezone.now() - ultimo_servicio_dt).days
        dias_espera = servicio_origen.dias_espera_bloqueo or 0

        if dias_transcurridos < dias_espera:
            return {
                "non_field_errors": [
                    (
                        f"Por la salud de tu cabello, no podemos agendar '{servicio_critico_solicitado.nombre}' todavía. "
                        f"Tu último proceso fue '{servicio_origen.nombre}' hace {dias_transcurridos} días "
                        f"y requiere un reposo mínimo de {dias_espera} días."
                    )
                ],
                "bloqueo_salud_capilar": {
                    "servicio_previo": servicio_origen.nombre,
                    "servicio_solicitado": servicio_critico_solicitado.nombre,
                    "fecha_ultimo_servicio": str(ultimo_servicio_dt.date()),
                    "dias_transcurridos": dias_transcurridos,
                    "dias_espera": dias_espera,
                    "dias_restantes": dias_espera - dias_transcurridos,
                },
            }

        return None


class MercadoPagoService:
    """
    Servicio de integración con Mercado Pago.

    Encapsula la creación de preferencias para mantener la lógica de pago fuera
    de views/serializers y facilitar futuras extensiones del flujo asíncrono.
    """

    def __init__(self):
        access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', '')
        if not access_token:
            raise ValueError('Falta configurar MERCADO_PAGO_ACCESS_TOKEN en settings/.env')

        self.sdk = mercadopago.SDK(access_token)

    def crear_preferencia(self, orden_compra):
        """
        Crea la preferencia de pago en Mercado Pago y guarda su ID en la orden.

        Returns:
            str: init_point para redirigir a la clienta al checkout de Mercado Pago.
        """
        webhook_url = getattr(
            settings,
            'MERCADO_PAGO_WEBHOOK_URL',
            'https://garland-bucked-mauve.ngrok-free.dev/api/gestion/checkout/webhook/'
        )

        success_url = getattr(
            settings,
            'MERCADO_PAGO_BACK_SUCCESS_URL',
            'http://localhost:3000/compra-exitosa'
        )
        failure_url = getattr(
            settings,
            'MERCADO_PAGO_BACK_FAILURE_URL',
            'http://localhost:3000/compra-fallida'
        )
        pending_url = getattr(
            settings,
            'MERCADO_PAGO_BACK_PENDING_URL',
            'http://localhost:3000/compra-pendiente'
        )

        preference_data = {
            'items': [
                {
                    'title': f'Compra en Bohemia Hair - Orden #{orden_compra.codigo}',
                    'quantity': 1,
                    'currency_id': 'ARS',
                    'unit_price': float(orden_compra.total),
                }
            ],
            'payer': {
                'email': orden_compra.cliente.usuario.email,
            },
            'notification_url': webhook_url,

            'back_urls': {
                'success': success_url,
                'failure': failure_url,
                'pending': pending_url,
            },
            'auto_return': 'approved',
            'external_reference': str(orden_compra.id),
        }

        preference_response = self.sdk.preference().create(preference_data)

        # 🚨 MODO DEBUG: Atrapamos el error exacto de Mercado Pago y lo imprimimos
        if preference_response.get("status") not in [200, 201]:
            print("\n🚨 RECHAZO DE MERCADO PAGO:")
            print(preference_response)
            print("🚨 ------------------------\n")


        preference = preference_response.get('response', {})

        if not preference.get('id') or not preference.get('init_point'):
            raise ValueError('Mercado Pago no devolvió una preferencia válida.')

        orden_compra.preference_id = preference['id']
        orden_compra.save(update_fields=['preference_id', 'actualizado_at'])

        return preference['init_point']
