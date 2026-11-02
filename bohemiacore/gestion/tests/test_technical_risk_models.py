from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from gestion.models import (
    Auditoria,
    EvaluacionRiesgoTecnico,
    FamiliaProcesoTecnico,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    ReglaDiagnosticoTecnico,
    ReglaFrecuenciaTecnica,
    ReglaIntervaloTecnico,
    Servicio,
    TechnicalRiskOutcome,
)
from gestion.technical_risk_policy_services import (
    TECHNICAL_POLICY_PUBLISHED,
    TechnicalRiskPolicyInvalid,
    TechnicalRiskPolicyPermissionDenied,
    publish_technical_risk_policy,
)
from usuarios.models import Cliente, Usuario


class TechnicalRiskModelTests(TestCase):
    def setUp(self):
        self.family = FamiliaProcesoTecnico.objects.create(
            code='FAMILY_TEST', nombre='Familia test'
        )
        self.origin = Servicio.objects.create(nombre='Origen técnico')
        self.target = Servicio.objects.create(nombre='Destino técnico')
        self.policy = PoliticaRiesgoTecnico.objects.create(version='MODEL-V1')

    def interval_rule(self, **overrides):
        values = {
            'politica': self.policy,
            'code': 'INTERVAL_TEST',
            'servicio_origen': self.origin,
            'servicio_destino': self.target,
            'dias_minimos': 45,
            'outcome': TechnicalRiskOutcome.NO_APTO,
        }
        values.update(overrides)
        return ReglaIntervaloTecnico(**values)

    def test_interval_selectors_require_exactly_one_on_each_side(self):
        missing_origin = self.interval_rule(servicio_origen=None)
        with self.assertRaises(ValidationError):
            missing_origin.full_clean()

        duplicate_origin = self.interval_rule(familia_origen=self.family)
        with self.assertRaises(ValidationError):
            duplicate_origin.full_clean()

        valid = self.interval_rule(
            code='VALID_FAMILY_RULE',
            servicio_origen=None,
            familia_origen=self.family,
            servicio_destino=None,
            familia_destino=self.family,
        )
        valid.full_clean()
        valid.save()

    def test_database_rejects_classified_profile_without_risk_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PerfilTecnicoServicio.objects.create(
                    servicio=self.target,
                    estado_clasificacion=(
                        PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
                    ),
                    nivel_riesgo=(
                        PerfilTecnicoServicio.NivelRiesgo.NO_DEFINIDO
                    ),
                )

    def test_policy_must_be_created_as_draft(self):
        with self.assertRaises(ValidationError):
            PoliticaRiesgoTecnico.objects.create(
                version='INVALID-DIRECT-PUBLISH',
                estado=PoliticaRiesgoTecnico.Estado.PUBLICADA,
            )

    def test_published_policy_and_rules_are_immutable(self):
        rule = self.interval_rule()
        rule.save()
        PoliticaRiesgoTecnico.objects.filter(pk=self.policy.pk).update(
            estado=PoliticaRiesgoTecnico.Estado.PUBLICADA
        )
        self.policy.refresh_from_db()

        self.policy.version = 'MODEL-V2'
        with self.assertRaises(ValidationError):
            self.policy.save()

        rule.prioridad = 99
        with self.assertRaises(ValidationError):
            rule.save()
        with self.assertRaises(ValidationError):
            rule.delete()

    def test_evaluation_validates_snapshot_shape(self):
        user = Usuario.objects.create_user(
            email='snapshot-model@test.com', password='testpass123'
        )
        client = Cliente.objects.create(usuario=user)
        evaluation = EvaluacionRiesgoTecnico(
            cliente=client,
            politica=self.policy,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            fecha_solicitada='2026-10-24',
            input_snapshot=[],
            result_snapshot={},
        )
        with self.assertRaises(ValidationError):
            evaluation.full_clean()

    def create_evaluation(self):
        user = Usuario.objects.create_user(
            email=f'immutable-{Usuario.objects.count()}@test.com',
            password='testpass123',
        )
        client = Cliente.objects.create(usuario=user)
        return EvaluacionRiesgoTecnico.objects.create(
            cliente=client,
            politica=self.policy,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            fecha_solicitada='2026-10-24',
            input_snapshot={
                'cliente_id': client.pk,
                'servicios': [self.target.pk],
                'fecha_solicitada': '2026-10-24',
            },
            result_snapshot={
                'outcome': TechnicalRiskOutcome.APTO,
                'policy_version': self.policy.version,
                'rule_codes': [],
            },
        )

    def test_persisted_evaluation_rejects_historical_field_changes(self):
        evaluation = self.create_evaluation()
        other_policy = PoliticaRiesgoTecnico.objects.create(version='MODEL-V2')
        other_user = Usuario.objects.create_user(
            email='other-evaluation-client@test.com', password='testpass123'
        )
        other_client = Cliente.objects.create(usuario=other_user)
        mutations = (
            ('outcome', TechnicalRiskOutcome.NO_APTO),
            ('input_snapshot', {
                'cliente_id': evaluation.cliente_id,
                'servicios': [],
                'fecha_solicitada': '2026-10-24',
            }),
            ('politica', other_policy),
            ('cliente', other_client),
        )

        for field, value in mutations:
            with self.subTest(field=field):
                evaluation.refresh_from_db()
                setattr(evaluation, field, value)
                with self.assertRaises(ValidationError):
                    evaluation.save()

        evaluation.refresh_from_db()
        self.assertEqual(evaluation.outcome, TechnicalRiskOutcome.APTO)
        self.assertEqual(evaluation.politica, self.policy)
        self.assertNotEqual(evaluation.cliente, other_client)

    def test_persisted_evaluation_rejects_instance_and_queryset_delete(self):
        evaluation = self.create_evaluation()

        with self.assertRaises(ValidationError):
            evaluation.delete()
        with self.assertRaises(ValidationError):
            EvaluacionRiesgoTecnico.objects.filter(pk=evaluation.pk).delete()
        with self.assertRaises(ValidationError):
            EvaluacionRiesgoTecnico.objects.filter(pk=evaluation.pk).update(
                outcome=TechnicalRiskOutcome.NO_APTO
            )

        self.assertTrue(
            EvaluacionRiesgoTecnico.objects.filter(pk=evaluation.pk).exists()
        )

    def test_base_default_and_related_managers_reject_updates(self):
        evaluation = self.create_evaluation()
        managers = (
            EvaluacionRiesgoTecnico.objects,
            EvaluacionRiesgoTecnico._default_manager,
            EvaluacionRiesgoTecnico._base_manager,
            evaluation.cliente.evaluaciones_riesgo_tecnico,
            evaluation.politica.evaluaciones,
        )

        for manager in managers:
            with self.subTest(manager=type(manager).__name__):
                with self.assertRaises(ValidationError):
                    manager.update(severity=77)

        evaluation.refresh_from_db()
        self.assertEqual(evaluation.severity, 0)

    def test_bulk_update_and_all_bulk_create_variants_are_rejected(self):
        evaluation = self.create_evaluation()
        evaluation.outcome = TechnicalRiskOutcome.NO_APTO

        with self.assertRaises(ValidationError):
            EvaluacionRiesgoTecnico.objects.bulk_update(
                [evaluation], ['outcome']
            )

        upsert = EvaluacionRiesgoTecnico(
            pk=evaluation.pk,
            cliente=evaluation.cliente,
            politica=evaluation.politica,
            outcome=TechnicalRiskOutcome.NO_APTO,
            severity=evaluation.severity,
            fecha_solicitada=evaluation.fecha_solicitada,
            input_snapshot=evaluation.input_snapshot,
            result_snapshot=evaluation.result_snapshot,
        )
        with self.assertRaises(ValidationError):
            EvaluacionRiesgoTecnico.objects.bulk_create(
                [upsert],
                update_conflicts=True,
                update_fields=['outcome'],
                unique_fields=['id'],
            )

        new_evaluation = EvaluacionRiesgoTecnico(
            cliente=evaluation.cliente,
            politica=evaluation.politica,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            fecha_solicitada=evaluation.fecha_solicitada,
            input_snapshot=evaluation.input_snapshot,
            result_snapshot=evaluation.result_snapshot,
        )
        with self.assertRaises(ValidationError):
            EvaluacionRiesgoTecnico.objects.bulk_create([new_evaluation])

        evaluation.refresh_from_db()
        self.assertEqual(evaluation.outcome, TechnicalRiskOutcome.APTO)
        self.assertEqual(EvaluacionRiesgoTecnico.objects.count(), 1)

    def test_update_or_create_is_rejected_and_get_or_create_does_not_update(self):
        evaluation = self.create_evaluation()

        with self.assertRaises(ValidationError):
            EvaluacionRiesgoTecnico.objects.update_or_create(
                pk=evaluation.pk,
                defaults={'outcome': TechnicalRiskOutcome.NO_APTO},
            )

        found, created = EvaluacionRiesgoTecnico.objects.get_or_create(
            pk=evaluation.pk,
            defaults={'outcome': TechnicalRiskOutcome.NO_APTO},
        )
        self.assertFalse(created)
        self.assertEqual(found.pk, evaluation.pk)
        self.assertEqual(found.outcome, TechnicalRiskOutcome.APTO)

        new_evaluation, created = (
            EvaluacionRiesgoTecnico.objects.get_or_create(
                cliente=evaluation.cliente,
                politica=evaluation.politica,
                fecha_solicitada='2026-10-25',
                defaults={
                    'outcome': TechnicalRiskOutcome.APTO,
                    'severity': 0,
                    'input_snapshot': {
                        'cliente_id': evaluation.cliente_id,
                        'servicios': [self.target.pk],
                        'fecha_solicitada': '2026-10-25',
                    },
                    'result_snapshot': {
                        'outcome': TechnicalRiskOutcome.APTO,
                        'policy_version': self.policy.version,
                        'rule_codes': [],
                    },
                },
            )
        )
        self.assertTrue(created)
        self.assertIsNotNone(new_evaluation.pk)

    def test_direct_supersession_save_is_rejected_even_with_legacy_flag(self):
        evaluation = self.create_evaluation()
        replacement = self.create_evaluation()
        evaluation.superseded_by = replacement
        evaluation._allow_explicit_supersession = True

        with self.assertRaises(ValidationError):
            evaluation.save(update_fields=['superseded_by'])

        evaluation.refresh_from_db()
        self.assertIsNone(evaluation.superseded_by_id)


class TechnicalRiskPolicyPublicationTests(TestCase):
    def setUp(self):
        self.actor = Usuario.objects.create_user(
            email='policy-publisher@test.com', password='testpass123'
        )
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_technical_risk_policy',
        )
        self.actor.user_permissions.add(permission)
        self.family = FamiliaProcesoTecnico.objects.create(
            code='POLICY_FAMILY', nombre='Policy family'
        )
        self.service = Servicio.objects.create(nombre='Policy service')

    def test_publish_validates_and_audits_policy(self):
        policy = PoliticaRiesgoTecnico.objects.create(version='PUBLISH-V1')
        ReglaFrecuenciaTecnica.objects.create(
            politica=policy,
            code='FREQUENCY_VALID',
            familia=self.family,
            ventana_dias=30,
            cantidad_maxima=2,
            outcome=TechnicalRiskOutcome.ADVERTENCIA,
        )

        published = publish_technical_risk_policy(
            actor=self.actor, policy_id=policy.pk
        )

        self.assertEqual(
            published.estado, PoliticaRiesgoTecnico.Estado.PUBLICADA
        )
        self.assertEqual(published.publicada_por, self.actor)
        self.assertIsNotNone(published.publicada_at)
        audit = Auditoria.objects.get(
            tabla='PoliticaRiesgoTecnico',
            registro_id=policy.pk,
            valor_nuevo__event=TECHNICAL_POLICY_PUBLISHED,
        )
        self.assertEqual(audit.usuario, self.actor)

    def test_publish_rejects_duplicate_codes_across_rule_types(self):
        policy = PoliticaRiesgoTecnico.objects.create(version='PUBLISH-DUP')
        ReglaFrecuenciaTecnica.objects.create(
            politica=policy,
            code='DUPLICATED_CODE',
            servicio=self.service,
            ventana_dias=30,
            cantidad_maxima=2,
            outcome=TechnicalRiskOutcome.ADVERTENCIA,
        )
        ReglaDiagnosticoTecnico.objects.create(
            politica=policy,
            code='DUPLICATED_CODE',
            servicio_destino=self.service,
        )

        with self.assertRaises(TechnicalRiskPolicyInvalid):
            publish_technical_risk_policy(
                actor=self.actor, policy_id=policy.pk
            )

        policy.refresh_from_db()
        self.assertEqual(policy.estado, PoliticaRiesgoTecnico.Estado.BORRADOR)

    def test_publish_rejects_inactive_references(self):
        policy = PoliticaRiesgoTecnico.objects.create(version='PUBLISH-INACTIVE')
        self.family.activa = False
        self.family.save(update_fields=['activa'])
        ReglaFrecuenciaTecnica.objects.create(
            politica=policy,
            code='INACTIVE_REFERENCE',
            familia=self.family,
            ventana_dias=30,
            cantidad_maxima=2,
            outcome=TechnicalRiskOutcome.ADVERTENCIA,
        )

        with self.assertRaises(TechnicalRiskPolicyInvalid):
            publish_technical_risk_policy(
                actor=self.actor, policy_id=policy.pk
            )

    def test_publish_requires_canonical_permission_not_staff(self):
        staff_only = Usuario.objects.create_user(
            email='staff-only-policy@test.com',
            password='testpass123',
            is_staff=True,
        )
        policy = PoliticaRiesgoTecnico.objects.create(version='PUBLISH-DENIED')

        with self.assertRaises(TechnicalRiskPolicyPermissionDenied):
            publish_technical_risk_policy(
                actor=staff_only, policy_id=policy.pk
            )
