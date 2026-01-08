from datetime import datetime, timedelta, time, date
from .models import Turno, HorarioLaboral, Configuracion, Equipamiento
import logging

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