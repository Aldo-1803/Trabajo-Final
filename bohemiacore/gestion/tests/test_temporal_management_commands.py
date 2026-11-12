from datetime import date, datetime, time, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from gestion.models import Notificacion, Personal, Promocion, Turno
from usuarios.models import Cliente, Usuario


class TemporalManagementCommandTests(TestCase):
    def setUp(self):
        self.client_user = Usuario.objects.create_user(
            email='timezone-client@test.com',
        )
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            activo=True,
        )
        self.personal_user = Usuario.objects.create_user(
            email='timezone-personal@test.com',
        )
        self.personal = Personal.objects.create(
            usuario=self.personal_user,
            nombre='Zona',
            apellido='Horaria',
            rol='asistente',
            activo=True,
        )
        self.fixed_utc_now = datetime(
            2026,
            11,
            11,
            2,
            30,
            tzinfo=dt_timezone.utc,
        )

    def test_pending_reminders_use_the_posadas_business_date(self):
        Turno.objects.create(
            cliente=self.client_profile,
            profesional=self.personal,
            fecha=date(2026, 11, 10),
            hora_inicio=time(23, 45),
            estado=Turno.Estado.SOLICITADO,
        )

        with patch('django.utils.timezone.now', return_value=self.fixed_utc_now):
            call_command('recordatorios_pendientes', stdout=StringIO())

        self.assertTrue(Notificacion.objects.filter(
            usuario=self.personal_user,
            titulo='Recordatorio de Pendientes',
        ).exists())

    def test_scheduled_promotions_use_the_posadas_business_date(self):
        promotion = Promocion.objects.create(
            nombre='Retoque Posadas',
            descripcion='Promoción temporal determinista',
            tipo='RETOQUE',
            descuento_porcentaje=10,
            fecha_inicio=date(2026, 11, 10),
            fecha_fin=date(2026, 11, 20),
            fecha_envio_notificacion=date(2026, 11, 10),
            cliente_especifico=self.client_profile,
            procesada=False,
            is_active=True,
        )

        with patch('django.utils.timezone.now', return_value=self.fixed_utc_now):
            call_command('procesar_promos', stdout=StringIO())

        promotion.refresh_from_db()
        self.assertTrue(promotion.procesada)
        self.assertTrue(Notificacion.objects.filter(
            usuario=self.client_user,
            tipo='promocion',
        ).exists())

    def test_turno_cleanup_compares_civil_fields_in_posadas(self):
        turno = Turno.objects.create(
            cliente=self.client_profile,
            profesional=self.personal,
            fecha=date(2026, 11, 10),
            hora_inicio=time(23, 45),
            estado=Turno.Estado.SOLICITADO,
        )

        with patch('django.utils.timezone.now', return_value=self.fixed_utc_now):
            call_command('limpiar_turnos', stdout=StringIO())

        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.SOLICITADO)
        self.assertFalse(Notificacion.objects.filter(
            usuario=self.client_user,
            titulo='Turno Cancelado',
        ).exists())
