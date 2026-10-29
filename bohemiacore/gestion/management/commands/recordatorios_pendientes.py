from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from gestion.models import Turno, Notificacion, Personal

class Command(BaseCommand):
    help = 'Notifica al profesional sobre turnos que requieren su atención (Solicitados o Sin Seña)'

    def handle(self, *args, **options):
        ahora = timezone.now()
        
        # 1. Buscamos turnos que requieran acción inmediata (próximas 48hs)
        pendientes = Turno.objects.filter(
            estado__in=['solicitado', 'esperando_sena'],
            fecha__range=[ahora.date(), ahora.date() + timedelta(days=2)]
        ).count()

        if pendientes > 0:
            # 2. Buscamos a los usuarios que son Staff (Yani y otros admins)
            # O directamente al Personal activo
            profesionales = Personal.objects.filter(activo=True)
            
            for prof in profesionales:
                # Evitamos duplicar la misma notificación si ya se envió una hace poco
                ultima_noti = Notificacion.objects.filter(
                    usuario=prof.usuario,
                    tipo='ALERTA',
                    titulo="Recordatorio de Pendientes",
                    fecha_creacion__gte=ahora - timedelta(hours=4) # Solo 1 cada 4 horas
                ).exists()

                if not ultima_noti:
                    Notificacion.objects.create(
                        usuario=prof.usuario,
                        tipo='ALERTA',
                        canal='app',
                        titulo="Recordatorio de Pendientes",
                        mensaje=f"Hola! Tienes {pendientes} turnos pendientes de aprobación o seña para los próximos días. Revisa tu agenda.",
                        origen_entidad='Turno'
                    )
            self.stdout.write(self.style.SUCCESS(f'Recordatorios enviados por {pendientes} turnos.'))
        else:
            self.stdout.write(self.style.SUCCESS('No hay turnos pendientes urgentes.'))