from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from gestion.provider_event_services import process_pending_provider_events


class Command(BaseCommand):
    help = 'Consulta y verifica el inbox autenticado de proveedores de pago.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--stale-minutes', type=int, default=10)
        parser.add_argument('--retry-seconds', type=int, default=60)

    def handle(self, *args, **options):
        limit = options['limit']
        stale_minutes = options['stale_minutes']
        retry_seconds = options['retry_seconds']
        if not 1 <= limit <= 1000:
            raise CommandError('limit debe estar entre 1 y 1000.')
        if stale_minutes < 1 or retry_seconds < 1:
            raise CommandError('Los intervalos deben ser positivos.')

        result = process_pending_provider_events(
            limit=limit,
            stale_after=timedelta(minutes=stale_minutes),
            retry_delay=timedelta(seconds=retry_seconds),
        )
        self.stdout.write(self.style.SUCCESS(
            'Provider events: '
            f'examinados={result.examined} verificados={result.verified} '
            f'reintentables={result.retryable} rechazados={result.rejected} '
            f'divergentes={result.mismatched}'
        ))
