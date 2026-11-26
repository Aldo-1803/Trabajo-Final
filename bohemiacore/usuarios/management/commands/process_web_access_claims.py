from django.core.management.base import BaseCommand, CommandError

from usuarios.web_access_claim_services import process_next_web_access_claim


class Command(BaseCommand):
    help = 'Procesa solicitudes de reclamo BH-064 pendientes; ejecutar periódicamente.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 200:
            raise CommandError('--limit debe estar entre 1 y 200.')
        processed = 0
        while processed < limit and process_next_web_access_claim():
            processed += 1
        self.stdout.write(f'Solicitudes de reclamo procesadas: {processed}')
