from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.functions import Now

from gestion.models import SlotHold
from gestion.slot_hold_clock import database_now
from gestion.slot_hold_services import SlotHoldConflict, _expire_locked_hold


class Command(BaseCommand):
    help = 'Materializa vencimientos de SlotHold en lotes idempotentes.'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=100)

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        if batch_size < 1 or batch_size > 1000:
            raise CommandError('batch-size debe estar entre 1 y 1000.')

        examined = expired = skipped = errors = 0
        failed_ids = set()
        while True:
            with transaction.atomic():
                queryset = (
                    SlotHold.objects.select_for_update(skip_locked=True)
                    .filter(
                        state=SlotHold.State.ACTIVE,
                        expires_at__lte=Now(),
                    )
                    .exclude(pk__in=failed_ids)
                    .order_by('expires_at', 'pk')[:batch_size]
                )
                batch = list(queryset)
                if not batch:
                    break
                for hold in batch:
                    examined += 1
                    try:
                        with transaction.atomic():
                            result = _expire_locked_hold(
                                hold,
                                now=database_now(),
                            )
                    except SlotHoldConflict:
                        skipped += 1
                    except Exception as exc:  # continúa otros HOLDs del lote
                        errors += 1
                        failed_ids.add(hold.pk)
                        self.stderr.write(
                            f'Error expirando SlotHold {hold.pk}: {exc}'
                        )
                    else:
                        if result.changed:
                            expired += 1
                        else:
                            skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                'SlotHold expiry: '
                f'examinados={examined} expirados={expired} '
                f'omitidos={skipped} errores={errors}'
            )
        )
