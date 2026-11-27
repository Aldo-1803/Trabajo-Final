from django.core.management.base import BaseCommand
from django.db.models.functions import Now

from usuarios.models import WalkInRateBucket


class Command(BaseCommand):
    help = 'Elimina cuotas BH-064 ya expiradas. Ejecutar periódicamente.'

    def handle(self, *args, **options):
        # Django usa un DELETE directo sin cargar filas (el modelo no tiene FK
        # ni señales). El predicado vuelve a validarse si hubo un UPSERT rival.
        count, _ = WalkInRateBucket.objects.filter(expires_at__lte=Now()).delete()
        self.stdout.write(f'Cuotas expiradas eliminadas: {count}')
