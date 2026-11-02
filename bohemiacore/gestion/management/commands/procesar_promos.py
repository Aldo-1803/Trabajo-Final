from django.core.management.base import BaseCommand
from django.utils import timezone
from gestion.models import Promocion, Notificacion

class Command(BaseCommand):
    help = 'Envía las notificaciones de promociones programadas para el día de hoy'

    def handle(self, *args, **kwargs):
        hoy = timezone.now().date()
        # Buscamos promociones de retoque que deban enviarse hoy y no hayan sido procesadas
        promos_pendientes = Promocion.objects.filter(
            fecha_envio_notificacion=hoy,
            procesada=False,
            is_active=True
        )

        for promo in promos_pendientes:
            # Enviamos la notificación al cliente
            Notificacion.objects.create(
                usuario=promo.cliente_especifico.usuario,
                tipo='promocion',
                titulo="✨ ¡Es hora de tu retoque!",
                mensaje=f"{promo.descripcion} Tienes un {promo.descuento_porcentaje}% OFF si reservas ahora.",
                datos_extra={"promo_id": promo.id}
            )
            # Marcamos como procesada para no repetir
            promo.procesada = True
            promo.save()
            
        self.stdout.write(self.style.SUCCESS(f'Se procesaron {promos_pendientes.count()} promociones.'))