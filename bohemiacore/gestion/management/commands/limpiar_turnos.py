from django.core.management.base import BaseCommand
from django.utils import timezone
from gestion.models import Turno, Notificacion, Configuracion
from django.db.models import Q

class Command(BaseCommand):
    help = 'Cancela turnos expirados y gestiona vencimientos de señas'

    def handle(self, *args, **options):
        ahora = timezone.now()
        config = Configuracion.objects.first()

        # --- LÓGICA 1: TURNOS QUE YA PASARON (EXPIRADOS) ---
        # Si la fecha/hora es menor a ahora y no está REALIZADO ni CANCELADO
        expirados = Turno.objects.filter(
            Q(fecha__lt=ahora.date()) | Q(fecha=ahora.date(), hora_inicio__lt=ahora.time()),
            estado__in=['solicitado', 'esperando_sena', 'pendiente']
        )

        for turno in expirados:
            self._cancelar_y_notificar(turno, "Cancelado automáticamente: Fecha expirada sin confirmación.")

        # --- LÓGICA 2: VENCIMIENTO DE SEÑA ---
        # Turnos que tienen una fecha_limite_pago y ya pasó
        sin_pago = Turno.objects.filter(
            estado='esperando_sena',
            fecha_limite_pago__lt=ahora
        )

        for turno in sin_pago:
            self._cancelar_y_notificar(turno, "Cancelado automáticamente: Vencimiento de plazo para seña.")

    def _cancelar_y_notificar(self, turno, motivo):
        turno.estado = 'cancelado'
        # Si agregaste el campo motivo_cancelacion, úsalo. Si no, solo cambia el estado.
        turno.save()

        # Notificación al Cliente
        Notificacion.objects.create(
            usuario=turno.cliente.usuario,
            tipo='ALERTA',
            titulo="Turno Cancelado",
            mensaje=f"Tu turno del {turno.fecha} ha sido {motivo}"
        )
        # Notificación al Profesional
        if turno.profesional:
            Notificacion.objects.create(
                usuario=turno.profesional.usuario,
                tipo='ALERTA',
                titulo="Turno Expirado",
                mensaje=f"El turno de {turno.cliente} para el {turno.fecha} ha sido cancelado por el sistema."
            )