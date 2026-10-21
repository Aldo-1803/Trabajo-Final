from datetime import datetime, timedelta, time, date
from django.utils import timezone
from django.conf import settings
from .models import Turno, HorarioLaboral, Configuracion, Equipamiento, FichaTecnica, Servicio
import logging
import mercadopago

logger = logging.getLogger(__name__)

class DisponibilidadService:
    @staticmethod
    def obtener_bloques_disponibles(fecha_consulta, servicio):
        """
        Devuelve los horarios de INICIO disponibles.
        Regla de Negocio: "Escalonamiento".
        - Yani solo puede recibir (iniciar) a una persona a la vez.
        - Pero puede haber gente en el local de turnos anteriores (superposición).
        """
        # 1. Validar si el día está abierto según HorarioLaboral
        dia_semana = fecha_consulta.weekday()
        logger.info(f"Consultando disponibilidad para fecha: {fecha_consulta}, día de semana: {dia_semana}")
        
        # Determinar duración a partir del servicio
        duracion_servicio_minutos = getattr(servicio, 'duracion_estimada', None) or 60

        # 1. Buscar la regla horaria que coincida con el tipo de servicio
        filtros = {
            'dia_semana': dia_semana,
            'activo': True
        }

        # Si nos pasan el servicio, intentamos filtrar por campos específicos
        campo_diseno = 'permite_diseno_color'
        campo_complemento = 'permite_complemento'

        model_fields = [f.name for f in HorarioLaboral._meta.get_fields()]
        try:
            if servicio and getattr(servicio, 'categoria', None) and getattr(servicio.categoria, 'nombre', '') == 'Diseño de color':
                if campo_diseno in model_fields:
                    filtros[campo_diseno] = True
            else:
                if campo_complemento in model_fields:
                    filtros[campo_complemento] = True

            horario_laboral = HorarioLaboral.objects.filter(**filtros).first()
            if not horario_laboral:
                logger.warning(f"No hay horario laboral configurado que cumpla filtros: {filtros}")
                return []  # Día cerrado o servicio no permitido ese día
            logger.info(f"Horario encontrado: {horario_laboral.hora_inicio} - {horario_laboral.hora_fin}")
        except Exception as e:
            logger.error(f"Error al buscar horario laboral con filtros {filtros}: {str(e)}", exc_info=True)
            raise Exception(f"Error al obtener horario laboral: {str(e)}")

        # Obtenemos configuración (ej: intervalos de 60 min para respetar la grilla de turnos)
        config = Configuracion.objects.first()
        # FORZAMOS intervalo de 60 min si es un servicio largo, o usamos el de config
        # Según tus docs, los turnos de diseño son a las 10, 11, 12 (en punto).
        intervalo = 60 
        
        # 2. Generar la grilla teórica del día (ej: 10:00, 11:00, 12:00...)
        bloques_posibles = []
        try:
            hora_actual = datetime.combine(fecha_consulta, horario_laboral.hora_inicio)
            hora_cierre = datetime.combine(fecha_consulta, horario_laboral.hora_fin)
        except Exception as e:
            logger.error(f"Error al crear datetime: {str(e)}")
            raise Exception(f"Error al procesar horarios: {str(e)}")
        
        # El turno debe terminar antes del cierre
        while hora_actual + timedelta(minutes=duracion_servicio_minutos) <= hora_cierre:
            bloques_posibles.append(hora_actual.time())
            hora_actual += timedelta(minutes=intervalo)

        logger.info(f"Bloques posibles generados: {len(bloques_posibles)}")

        # 3. Buscar qué horarios de INICIO ya están ocupados
        # Solo nos importa la hora de ARRANQUE. Si alguien reservó a las 10:00, 
        # las 10:00 ya no están disponibles para iniciar.
        try:
            turnos_ocupados = Turno.objects.filter(
                fecha=fecha_consulta,
                estado__in=['pendiente', 'confirmado', 'en_proceso']
            ).values_list('hora_inicio', flat=True)

            # Convertimos a set para búsqueda rápida
            horarios_ocupados_set = set(turnos_ocupados)
            logger.info(f"Horarios ocupados: {horarios_ocupados_set}")
        except Exception as e:
            logger.error(f"Error al obtener turnos ocupados: {str(e)}")
            horarios_ocupados_set = set()

        # 4. Filtrar y retornar bloques libres considerando RECURSOS
        bloques_libres = []
        for bloque in bloques_posibles:
            # INTEGRACIÓN DE LA REGLA DE ESCALABILIDAD:
            if DisponibilidadService.validar_recursos_dinamicos(fecha_consulta, bloque, duracion_servicio_minutos):
                bloques_libres.append(bloque)

        logger.info(f"Bloques libres retornados tras validar recursos: {len(bloques_libres)}")
        return bloques_libres

    @staticmethod
    def validar_recursos_dinamicos(fecha, hora_inicio, duracion_total):
        """
        Valida si hay recursos disponibles (sillas técnicas) en el horario solicitado.
        
        Regla:
        - Yani solo puede INICIAR un turno a la vez (regla de escalonamiento)
        - Pero puede haber múltiples clientes EN EL LOCAL (superposición permitida)
        
        Args:
            fecha: date object
            hora_inicio: time object (hora de inicio del turno)
            duracion_total: int en minutos
        
        Returns:
            bool: True si hay recursos disponibles, False en caso contrario
        """
        try:
            # Convertir hora_inicio a datetime para comparaciones
            if isinstance(hora_inicio, time):
                inicio_dt = datetime.combine(fecha, hora_inicio)
            else:
                inicio_dt = hora_inicio
            
            hora_fin = (inicio_dt + timedelta(minutes=duracion_total)).time()
            
            # 1. Validar Concurrencia de INICIO (Regla de Escalonamiento)
            # Yani NO puede iniciar dos procesos al mismo tiempo
            turnos_solapados_inicio = Turno.objects.filter(
                fecha=fecha,
                hora_inicio=hora_inicio,  # Mismo INICIO exacto
                estado__in=['pendiente', 'confirmado', 'en_proceso']
            ).exists()
            
            if turnos_solapados_inicio:
                logger.warning(f"Horario {hora_inicio} ya ocupado (solapamiento de inicio)")
                return False
            
            # 2. Validar Sillas Técnicas (si existe Equipamiento)
            # Contar cuántas sillas técnicas están EN USO durante este rango
            try:
                sillas_ocupadas = Turno.objects.filter(
                    fecha=fecha,
                    estado__in=['pendiente', 'confirmado', 'en_proceso'],
                    hora_inicio__lt=hora_fin,  # Turno inicia ANTES del fin del nuestro
                    # NOTA: Se asume que hora_fin del turno = hora_inicio + duracion_estimada
                    # Pero Turno podría no tener hora_fin explícita, así que comparamos por duración
                ).count()
                
                # Obtener disponibilidad total de sillas (asumimos solo 1 silla técnica por ahora)
                total_sillas = Equipamiento.objects.filter(
                    tipo='TECNICA', 
                    estado='DISPONIBLE'
                ).count()
                
                # Si no hay sillas definidas, asumir que hay infinitas
                if total_sillas == 0:
                    logger.info(f"No hay sillas técnicas definidas, permitiendo reserva")
                    return True
                
                if sillas_ocupadas >= total_sillas:
                    logger.warning(f"No hay sillas técnicas disponibles ({sillas_ocupadas}/{total_sillas})")
                    return False
                
            except Exception as e:
                logger.error(f"Error al validar sillas técnicas: {str(e)}")
                # Si hay error, permitimos la reserva (fail-safe)
                return True
            
            # 3. Si pasó todas las validaciones, está disponible
            logger.info(f"Horario {hora_inicio} - Validación OK (recursos disponibles)")
            return True
            
        except Exception as e:
            logger.error(f"Error en validar_recursos_dinamicos: {str(e)}", exc_info=True)
            # En caso de error, permitimos la reserva (fail-safe)
            return True

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
