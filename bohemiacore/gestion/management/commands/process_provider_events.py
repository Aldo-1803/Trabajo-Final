from datetime import timedelta
import logging
import time

from decouple import config
from django.core.management.base import BaseCommand, CommandError

from gestion.provider_event_pipeline import process_provider_event_pipeline


logger = logging.getLogger(__name__)


def _configured_int(name, default):
    try:
        return int(config(name, default=str(default)))
    except (TypeError, ValueError) as exc:
        raise CommandError(f'{name} debe ser un entero.') from exc


class Command(BaseCommand):
    help = 'Verifica y concilia continuamente el inbox de proveedores de pago.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=_configured_int('PROVIDER_EVENT_WORKER_LIMIT', 100),
        )
        parser.add_argument(
            '--stale-minutes',
            type=int,
            default=_configured_int(
                'PROVIDER_EVENT_WORKER_STALE_MINUTES',
                10,
            ),
        )
        parser.add_argument(
            '--retry-seconds',
            type=int,
            default=_configured_int('PROVIDER_EVENT_WORKER_RETRY_SECONDS', 60),
        )
        parser.add_argument(
            '--poll-seconds',
            type=int,
            default=_configured_int('PROVIDER_EVENT_WORKER_POLL_SECONDS', 5),
        )
        parser.add_argument(
            '--watch',
            action='store_true',
            help='Mantiene el worker activo y consulta el inbox periódicamente.',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        stale_minutes = options['stale_minutes']
        retry_seconds = options['retry_seconds']
        poll_seconds = options['poll_seconds']
        watch = options['watch']
        if not 1 <= limit <= 1000:
            raise CommandError('limit debe estar entre 1 y 1000.')
        if stale_minutes < 1 or retry_seconds < 1 or poll_seconds < 1:
            raise CommandError('Los intervalos deben ser positivos.')
        while True:
            try:
                result = process_provider_event_pipeline(
                    limit=limit,
                    stale_after=timedelta(minutes=stale_minutes),
                    retry_delay=timedelta(seconds=retry_seconds),
                )
            except Exception:
                if not watch:
                    raise
                logger.exception('Falló un ciclo del worker de ProviderEvent.')
                self.stderr.write(
                    self.style.ERROR(
                        'Provider events: ciclo fallido; se reintentará.'
                    )
                )
                time.sleep(poll_seconds)
                continue

            if result.examined or not watch:
                verification = result.verification
                reconciliation = result.reconciliation
                self.stdout.write(self.style.SUCCESS(
                    'Provider events: '
                    f'verificacion_examinados={verification.examined} '
                    f'verificados={verification.verified} '
                    f'consulta_reintentable={verification.retryable} '
                    f'rechazados={verification.rejected} '
                    f'divergentes={verification.mismatched} '
                    f'conciliacion_examinados={reconciliation.examined} '
                    f'aplicados={reconciliation.applied} '
                    f'revision={reconciliation.review_required} '
                    f'ignorados={reconciliation.ignored} '
                    f'conciliacion_reintentable={reconciliation.retryable}'
                ))
            if not watch:
                break
            if result.examined < limit:
                time.sleep(poll_seconds)
