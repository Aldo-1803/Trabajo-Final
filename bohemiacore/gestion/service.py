from datetime import datetime, timedelta, time, date
from .models import Turno, HorarioLaboral, Configuracion

class DisponibilidadService:
    @staticmethod
    def obtener_bloques_disponibles(fecha_consulta, duracion_servicio_minutos):
        """
        Devuelve los horarios de INICIO disponibles.
        Regla de Negocio: "Escalonamiento".
        - Yani solo puede recibir (iniciar) a una persona a la vez.
        - Pero puede haber gente en el local de turnos anteriores (superposición).
        """
        # 1. Validar si el día está abierto según HorarioLaboral
        dia_semana = fecha_consulta.weekday()
        try:
            horario_laboral = HorarioLaboral.objects.get(dia=dia_semana, activo=True)
        except HorarioLaboral.DoesNotExist:
            return [] # Día cerrado

        # Obtenemos configuración (ej: intervalos de 60 min para respetar la grilla de turnos)
        config = Configuracion.objects.first()
        # FORZAMOS intervalo de 60 min si es un servicio largo, o usamos el de config
        # Según tus docs, los turnos de diseño son a las 10, 11, 12 (en punto).
        intervalo = 60 
        
        # 2. Generar la grilla teórica del día (ej: 10:00, 11:00, 12:00...)
        bloques_posibles = []
        hora_actual = datetime.combine(fecha_consulta, horario_laboral.hora_inicio)
        hora_cierre = datetime.combine(fecha_consulta, horario_laboral.hora_fin)
        
        # El turno debe terminar antes del cierre
        while hora_actual + timedelta(minutes=duracion_servicio_minutos) <= hora_cierre:
            bloques_posibles.append(hora_actual.time())
            hora_actual += timedelta(minutes=intervalo)

        # 3. Buscar qué horarios de INICIO ya están ocupados
        # Solo nos importa la hora de ARRANQUE. Si alguien reservó a las 10:00, 
        # las 10:00 ya no están disponibles para iniciar.
        turnos_ocupados = Turno.objects.filter(
            fecha=fecha_consulta,
            estado__in=['pendiente', 'confirmado', 'en_proceso']
        ).values_list('hora_inicio', flat=True)

        # Convertimos a set para búsqueda rápida
        horarios_ocupados_set = set(turnos_ocupados)

        # 4. Filtrar: Solo devolvemos las horas donde NO empieza nadie
        bloques_libres = []
        for bloque in bloques_posibles:
            if bloque not in horarios_ocupados_set:
                bloques_libres.append(bloque)

        return bloques_libres