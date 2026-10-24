import importlib
from itertools import product

from django.apps import apps
from django.test import TestCase

from gestion.models import (
    CategoriaServicio,
    Habilidad,
    Personal,
    PersonalHabilidad,
    Servicio,
    ServicioHabilidad,
)


seed_and_backfill_skills = importlib.import_module(
    'gestion.migrations.0021_habilidad_personalhabilidad_serviciohabilidad'
).seed_and_backfill_skills


class SkillLegacyBackfillTests(TestCase):
    def test_every_legacy_boolean_combination_backfills_exact_skills_idempotently(self):
        expected_by_personal = {}
        for index, (diagnostico, lavado, color) in enumerate(product((False, True), repeat=3)):
            personal = Personal.objects.create(
                nombre=f'Personal {index}',
                apellido='Backfill',
                rol='asistente',
                realiza_diagnostico=diagnostico,
                realiza_lavado=lavado,
                realiza_color=color,
            )
            expected_by_personal[personal.pk] = {
                code for enabled, code in (
                    (diagnostico, 'DIAGNOSTICO'),
                    (lavado, 'LAVADO'),
                    (color, 'COLORACION'),
                ) if enabled
            }

        seed_and_backfill_skills(apps, None)
        seed_and_backfill_skills(apps, None)

        self.assertEqual(set(Habilidad.objects.values_list('code', flat=True)), {
            'DIAGNOSTICO', 'LAVADO', 'COLORACION'
        })
        for personal_id, expected_codes in expected_by_personal.items():
            assignments = PersonalHabilidad.objects.filter(
                personal_id=personal_id,
                activa=True,
            ).select_related('habilidad')
            self.assertEqual(
                {assignment.habilidad.code for assignment in assignments},
                expected_codes,
            )
            self.assertEqual(assignments.count(), len(expected_codes))

    def test_service_backfill_matches_legacy_category_text_rule(self):
        color_category = CategoriaServicio.objects.create(nombre='Diseño de Color')
        complemento_category = CategoriaServicio.objects.create(nombre='Turno de Complemento')
        other_category = CategoriaServicio.objects.create(nombre='Corte')
        color_service = Servicio.objects.create(nombre='Color', categoria=color_category)
        lavado_service = Servicio.objects.create(nombre='Lavado', categoria=complemento_category)
        other_service = Servicio.objects.create(nombre='Corte', categoria=other_category)

        seed_and_backfill_skills(apps, None)
        seed_and_backfill_skills(apps, None)

        self.assertEqual(set(ServicioHabilidad.objects.filter(
            servicio=color_service
        ).values_list('habilidad__code', flat=True)), {'COLORACION'})
        self.assertEqual(set(ServicioHabilidad.objects.filter(
            servicio=lavado_service
        ).values_list('habilidad__code', flat=True)), {'LAVADO'})
        self.assertFalse(ServicioHabilidad.objects.filter(servicio=other_service).exists())
