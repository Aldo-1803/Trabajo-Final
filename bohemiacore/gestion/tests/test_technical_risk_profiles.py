from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from gestion.models import (
    FamiliaProcesoTecnico,
    PerfilTecnicoServicio,
    Servicio,
)
from gestion.technical_risk_profile_services import (
    TechnicalProfileStatus,
    backfill_missing_technical_profiles,
    technical_service_profile_inventory,
)


class TechnicalRiskProfileInventoryTests(TestCase):
    def setUp(self):
        self.family = FamiliaProcesoTecnico.objects.create(
            code='PROFILE_REPORT_FAMILY', nombre='Report family'
        )

    def test_backfill_is_conservative_idempotent_and_preserves_classified(self):
        missing = Servicio.objects.create(nombre='Missing profile service')
        classified = Servicio.objects.create(nombre='Classified service')
        classified_profile = PerfilTecnicoServicio.objects.create(
            servicio=classified,
            familia=self.family,
            estado_clasificacion=(
                PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
            ),
            nivel_riesgo=PerfilTecnicoServicio.NivelRiesgo.ALTO,
        )

        first_created = backfill_missing_technical_profiles()
        second_created = backfill_missing_technical_profiles()

        self.assertEqual(first_created, (missing.pk,))
        self.assertEqual(second_created, ())
        self.assertEqual(
            PerfilTecnicoServicio.objects.filter(servicio=missing).count(), 1
        )
        pending = missing.perfil_tecnico
        self.assertEqual(
            pending.estado_clasificacion,
            PerfilTecnicoServicio.EstadoClasificacion.PENDIENTE,
        )
        self.assertEqual(
            pending.nivel_riesgo,
            PerfilTecnicoServicio.NivelRiesgo.NO_DEFINIDO,
        )
        self.assertIsNone(pending.familia_id)
        classified_profile.refresh_from_db()
        self.assertEqual(
            classified_profile.estado_clasificacion,
            PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO,
        )
        self.assertEqual(classified_profile.familia, self.family)
        self.assertEqual(
            classified_profile.nivel_riesgo,
            PerfilTecnicoServicio.NivelRiesgo.ALTO,
        )

    def test_inventory_classifies_all_supported_states(self):
        missing = Servicio.objects.create(nombre='Missing')
        pending = Servicio.objects.create(nombre='Pending')
        inactive_profile = Servicio.objects.create(nombre='Inactive profile')
        inactive_family_service = Servicio.objects.create(
            nombre='Inactive family'
        )
        valid = Servicio.objects.create(nombre='Valid')
        inactive_family = FamiliaProcesoTecnico.objects.create(
            code='INACTIVE_REPORT_FAMILY',
            nombre='Inactive report family',
            activa=False,
        )
        PerfilTecnicoServicio.objects.create(servicio=pending)
        PerfilTecnicoServicio.objects.create(
            servicio=inactive_profile, activa=False
        )
        PerfilTecnicoServicio.objects.create(
            servicio=inactive_family_service,
            familia=inactive_family,
            estado_clasificacion=(
                PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
            ),
            nivel_riesgo=PerfilTecnicoServicio.NivelRiesgo.MEDIO,
        )
        PerfilTecnicoServicio.objects.create(
            servicio=valid,
            familia=self.family,
            estado_clasificacion=(
                PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
            ),
            nivel_riesgo=PerfilTecnicoServicio.NivelRiesgo.BAJO,
        )

        inventory = {
            row['service_id']: row
            for row in technical_service_profile_inventory()
        }

        self.assertEqual(
            inventory[missing.pk]['status'],
            TechnicalProfileStatus.MISSING_PROFILE,
        )
        self.assertEqual(
            inventory[pending.pk]['status'], TechnicalProfileStatus.PENDING
        )
        self.assertEqual(
            inventory[inactive_profile.pk]['status'],
            TechnicalProfileStatus.INACTIVE_PROFILE,
        )
        self.assertEqual(
            inventory[inactive_family_service.pk]['status'],
            TechnicalProfileStatus.INACTIVE_FAMILY,
        )
        self.assertEqual(
            inventory[valid.pk]['status'],
            TechnicalProfileStatus.CLASSIFIED_VALID,
        )
        self.assertEqual(inventory[valid.pk]['family_code'], self.family.code)

    def test_command_backfills_and_reports_pending_service(self):
        service = Servicio.objects.create(nombre='Command pending service')
        output = StringIO()

        call_command(
            'report_unclassified_services',
            '--backfill',
            stdout=output,
        )

        profile = PerfilTecnicoServicio.objects.get(servicio=service)
        self.assertEqual(
            profile.estado_clasificacion,
            PerfilTecnicoServicio.EstadoClasificacion.PENDIENTE,
        )
        report = output.getvalue()
        self.assertIn(f'service_id={service.pk}', report)
        self.assertIn('status=PENDING', report)
        self.assertIn('family_code=None', report)
        self.assertIn('Backfill conservador: 1 perfil(es) creado(s).', report)
