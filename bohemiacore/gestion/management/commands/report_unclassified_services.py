from collections import Counter

from django.core.management.base import BaseCommand

from gestion.technical_risk_profile_services import (
    TechnicalProfileStatus,
    backfill_missing_technical_profiles,
    technical_service_profile_inventory,
)


class Command(BaseCommand):
    help = (
        'Reporta el estado técnico de Servicios sin inferir familias ni riesgo.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--backfill',
            action='store_true',
            help='Crea perfiles PENDIENTE conservadores para Servicios sin perfil.',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Incluye Servicios clasificados válidos en el detalle.',
        )

    def handle(self, *args, **options):
        if options['backfill']:
            created_ids = backfill_missing_technical_profiles()
            self.stdout.write(
                f'Backfill conservador: {len(created_ids)} perfil(es) creado(s).'
            )

        inventory = technical_service_profile_inventory()
        visible = inventory
        if not options['all']:
            visible = tuple(
                row for row in inventory
                if row['status'] != TechnicalProfileStatus.CLASSIFIED_VALID
            )

        for row in visible:
            self.stdout.write(
                'service_id={service_id} name="{service_name}" '
                'status={status} profile_id={profile_id} '
                'classification={classification_state} risk={risk_level} '
                'family_code={family_code}'.format(**row)
            )

        counts = Counter(row['status'] for row in inventory)
        summary = ' '.join(
            f'{status}={counts.get(status, 0)}'
            for status in (
                TechnicalProfileStatus.MISSING_PROFILE,
                TechnicalProfileStatus.PENDING,
                TechnicalProfileStatus.CLASSIFIED_VALID,
                TechnicalProfileStatus.INACTIVE_PROFILE,
                TechnicalProfileStatus.INACTIVE_FAMILY,
                TechnicalProfileStatus.INVALID_PROFILE,
            )
        )
        self.stdout.write(f'Resumen: {summary}')
