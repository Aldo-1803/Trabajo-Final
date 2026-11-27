from datetime import date, datetime, time, timezone as dt_timezone

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from gestion.models import BloqueoAgenda


class BusinessTimezoneTests(TestCase):
    def test_posadas_is_the_default_business_timezone(self):
        self.assertEqual(settings.TIME_ZONE, 'America/Argentina/Cordoba')
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(
            str(timezone.get_default_timezone()),
            'America/Argentina/Cordoba',
        )

    def test_utc_boundary_resolves_to_previous_business_date_in_posadas(self):
        fixed_utc = datetime(2026, 11, 11, 2, 30, tzinfo=dt_timezone.utc)
        business_timezone = timezone.get_default_timezone()

        local_value = timezone.localtime(fixed_utc, business_timezone)

        self.assertEqual(local_value.date(), date(2026, 11, 10))
        self.assertEqual(local_value.time(), time(23, 30))
        self.assertEqual(local_value.utcoffset().total_seconds(), -3 * 60 * 60)

    def test_historical_utc_timestamp_keeps_the_same_instant(self):
        historical_utc = datetime(2024, 6, 15, 15, 0, tzinfo=dt_timezone.utc)
        block = BloqueoAgenda.objects.create(
            fecha_inicio=historical_utc,
            fecha_fin=historical_utc.replace(hour=16),
            motivo='Compatibilidad histórica UTC',
        )

        block.refresh_from_db()
        local_value = timezone.localtime(
            block.fecha_inicio,
            timezone.get_default_timezone(),
        )

        self.assertTrue(timezone.is_aware(block.fecha_inicio))
        self.assertEqual(
            block.fecha_inicio.astimezone(dt_timezone.utc),
            historical_utc,
        )
        self.assertEqual(local_value.time(), time(12, 0))
