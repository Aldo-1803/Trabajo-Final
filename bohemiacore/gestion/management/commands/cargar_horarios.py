from django.core.management.base import BaseCommand
from gestion.models import HorarioLaboral, DiasSemana, Configuracion
from datetime import time

class Command(BaseCommand):
    help = 'Carga la configuración inicial de horarios de Yani según el documento'

    def handle(self, *args, **kwargs):
        self.stdout.write("Iniciando carga de horarios...")

        # 1. Configuración Global (Singleton)
        config, created = Configuracion.objects.get_or_create(pk=1)
        config.intervalo_turnos = 30 # Bloques de 30 min para flexibilidad visual
        config.save()
        
        # 2. Definición de Horarios según Documento "Organización de turnos.docx"
        # Nota: Ponemos una hora de fin "segura" (ej: 20:00) para dar margen, 
        # ya que el sistema validará disponibilidad real según los turnos tomados.
        
        horarios_data = [
            # Lunes: 10hs arranque
            {
                'dia': DiasSemana.LUNES, 
                'inicio': time(10, 0), 
                'fin': time(19, 0) # Estimado segun ultimo turno de 16hs + 3hs proc
            },
            # Martes: 08hs arranque
            {
                'dia': DiasSemana.MARTES, 
                'inicio': time(8, 0), 
                'fin': time(17, 0) 
            },
            # Miércoles: 12hs arranque
            {
                'dia': DiasSemana.MIERCOLES, 
                'inicio': time(12, 0), 
                'fin': time(21, 0) 
            },
            # Jueves: 08hs arranque (Igual a Martes)
            {
                'dia': DiasSemana.JUEVES, 
                'inicio': time(8, 0), 
                'fin': time(17, 0) 
            },
            # Viernes: 10hs arranque (Igual a Lunes)
            {
                'dia': DiasSemana.VIERNES, 
                'inicio': time(10, 0), 
                'fin': time(19, 0) 
            },
            # Sábado: 08hs arranque
            {
                'dia': DiasSemana.SABADO, 
                'inicio': time(8, 0), 
                'fin': time(17, 0) 
            },
            # Domingo: Cerrado (No lo creamos o lo ponemos activo=False)
        ]

        for data in horarios_data:
            horario, created = HorarioLaboral.objects.update_or_create(
                dia=data['dia'],
                defaults={
                    'hora_inicio': data['inicio'],
                    'hora_fin': data['fin'],
                    'activo': True
                }
            )
            action = "Creado" if created else "Actualizado"
            self.stdout.write(f"- {horario.get_dia_display()}: {action}")

        # Desactivar Domingo explícitamente si existía
        HorarioLaboral.objects.filter(dia=DiasSemana.DOMINGO).update(activo=False)

        self.stdout.write(self.style.SUCCESS('¡Horarios cargados exitosamente!'))