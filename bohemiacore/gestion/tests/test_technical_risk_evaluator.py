from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import TestCase
from django.utils import timezone

from gestion.models import (
    AgendaCuidados,
    Auditoria,
    CueroCabelludo,
    DetalleTurno,
    DiagnosticoCapilar,
    EstadoGeneral,
    EvaluacionRiesgoTecnico,
    FamiliaProcesoTecnico,
    GrosorCabello,
    Notificacion,
    Pago,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    PorosidadCabello,
    ReglaDiagnosticoTecnico,
    ReglaFrecuenciaTecnica,
    ReglaIntervaloTecnico,
    Rutina,
    Servicio,
    TechnicalRiskOutcome,
    TipoCabello,
    Turno,
)
from gestion.technical_risk_evaluator import (
    INCOMPLETE_HISTORY_RULE_CODE,
    TECHNICAL_ASSESSMENT_CREATED,
    TECHNICAL_ASSESSMENT_SUPERSEDED,
    TechnicalRiskConfigurationError,
    TechnicalRiskSupersessionError,
    evaluate_booking_risk,
    persist_technical_risk_evaluation,
    supersede_technical_risk_evaluation,
)
from gestion.technical_risk_comparison import compare_legacy_and_technical_risk
from usuarios.models import Cliente, Usuario


class TechnicalRiskEvaluatorTests(TestCase):
    def setUp(self):
        user = Usuario.objects.create_user(
            email='risk-client@test.com', password='testpass123'
        )
        self.client_profile = Cliente.objects.create(usuario=user, zona='Centro')
        self.requested_date = date(2026, 6, 30)

        self.family_a = FamiliaProcesoTecnico.objects.create(
            code='FAMILY_A', nombre='Familia A'
        )
        self.family_b = FamiliaProcesoTecnico.objects.create(
            code='FAMILY_B', nombre='Familia B'
        )
        self.family_c = FamiliaProcesoTecnico.objects.create(
            code='FAMILY_C', nombre='Familia C'
        )
        self.service_a = self.create_service('Servicio A', self.family_a, 'ALTO')
        self.service_b = self.create_service('Servicio B', self.family_b, 'MEDIO')
        self.service_c = self.create_service('Servicio C', self.family_c, 'BAJO')
        self.policy = PoliticaRiesgoTecnico.objects.create(version='EVAL-V1')

    @staticmethod
    def create_service(name, family, risk):
        service = Servicio.objects.create(nombre=name)
        PerfilTecnicoServicio.objects.create(
            servicio=service,
            familia=family,
            estado_clasificacion=(
                PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
            ),
            nivel_riesgo=risk,
        )
        return service

    def publish(self, policy=None):
        policy = policy or self.policy
        PoliticaRiesgoTecnico.objects.filter(pk=policy.pk).update(
            estado=PoliticaRiesgoTecnico.Estado.PUBLICADA,
            publicada_at=timezone.now(),
        )
        policy.refresh_from_db()
        return policy

    def create_history(self, service, event_date, *, hour=9):
        appointment = Turno.objects.create(
            cliente=self.client_profile,
            fecha=event_date,
            hora_inicio=time(hour, 0),
            estado=Turno.Estado.REALIZADO,
        )
        return DetalleTurno.objects.create(
            turno=appointment,
            servicio=service,
            precio_historico='100.00',
            duracion_minutos=60,
        )

    def create_interval_rule(self, code, outcome, **overrides):
        values = {
            'politica': self.policy,
            'code': code,
            'servicio_origen': self.service_a,
            'servicio_destino': self.service_b,
            'dias_minimos': 45,
            'outcome': outcome,
            'prioridad': 0,
            'severidad': 1,
        }
        values.update(overrides)
        return ReglaIntervaloTecnico.objects.create(**values)

    def evaluate(self, services=None, *, policy_version='EVAL-V1'):
        return evaluate_booking_risk(
            cliente=self.client_profile,
            servicios=services or [self.service_b],
            fecha_solicitada=self.requested_date,
            policy_version=policy_version,
        )

    def test_interval_precedence_keeps_all_rules_at_highest_specificity(self):
        self.create_interval_rule(
            'EXACT_WARNING', TechnicalRiskOutcome.ADVERTENCIA, prioridad=20
        )
        self.create_interval_rule(
            'EXACT_BLOCK', TechnicalRiskOutcome.NO_APTO, prioridad=1
        )
        self.create_interval_rule(
            'MIXED_IGNORED',
            TechnicalRiskOutcome.REQUIERE_REVISION,
            servicio_destino=None,
            familia_destino=self.family_b,
        )
        self.create_interval_rule(
            'FAMILY_IGNORED',
            TechnicalRiskOutcome.NO_APTO,
            servicio_origen=None,
            familia_origen=self.family_a,
            servicio_destino=None,
            familia_destino=self.family_b,
        )
        self.create_history(
            self.service_a, self.requested_date - timedelta(days=44)
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.outcome, TechnicalRiskOutcome.NO_APTO)
        self.assertEqual(
            result.rule_codes, ('EXACT_WARNING', 'EXACT_BLOCK')
        )
        self.assertNotIn('MIXED_IGNORED', result.rule_codes)
        self.assertNotIn('FAMILY_IGNORED', result.rule_codes)

    def test_mixed_precedence_keeps_exact_family_and_family_exact(self):
        self.create_interval_rule(
            'EXACT_TO_FAMILY',
            TechnicalRiskOutcome.ADVERTENCIA,
            servicio_destino=None,
            familia_destino=self.family_b,
        )
        self.create_interval_rule(
            'FAMILY_TO_EXACT',
            TechnicalRiskOutcome.REQUIERE_REVISION,
            servicio_origen=None,
            familia_origen=self.family_a,
        )
        self.create_interval_rule(
            'FAMILY_TO_FAMILY',
            TechnicalRiskOutcome.NO_APTO,
            servicio_origen=None,
            familia_origen=self.family_a,
            servicio_destino=None,
            familia_destino=self.family_b,
        )
        self.create_history(
            self.service_a, self.requested_date - timedelta(days=10)
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(
            set(result.rule_codes), {'EXACT_TO_FAMILY', 'FAMILY_TO_EXACT'}
        )
        self.assertEqual(
            result.outcome, TechnicalRiskOutcome.REQUIERE_REVISION
        )

    def test_family_to_family_rule_applies_without_more_specific_rule(self):
        self.create_interval_rule(
            'FAMILY_ONLY',
            TechnicalRiskOutcome.ADVERTENCIA,
            servicio_origen=None,
            familia_origen=self.family_a,
            servicio_destino=None,
            familia_destino=self.family_b,
        )
        self.create_history(
            self.service_a, self.requested_date - timedelta(days=10)
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.rule_codes, ('FAMILY_ONLY',))
        self.assertEqual(result.outcome, TechnicalRiskOutcome.ADVERTENCIA)

    def test_interval_allows_exactly_45_days_and_blocks_44(self):
        self.create_interval_rule('FORTY_FIVE_DAYS', TechnicalRiskOutcome.NO_APTO)
        self.publish()
        detail = self.create_history(
            self.service_a, self.requested_date - timedelta(days=45)
        )

        at_limit = self.evaluate()
        self.assertEqual(at_limit.outcome, TechnicalRiskOutcome.APTO)

        detail.turno.fecha = self.requested_date - timedelta(days=44)
        detail.turno.save(update_fields=['fecha'])
        below_limit = self.evaluate()
        self.assertEqual(below_limit.outcome, TechnicalRiskOutcome.NO_APTO)
        trigger = below_limit.result_snapshot['reglas_disparadas'][0]
        self.assertEqual(trigger['evidence']['dias_transcurridos'], 44)

    def test_history_after_requested_date_is_ignored(self):
        self.create_interval_rule('FUTURE_EVENT', TechnicalRiskOutcome.NO_APTO)
        self.create_history(
            self.service_a, self.requested_date + timedelta(days=1)
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)
        self.assertEqual(result.relevant_history, ())

    def test_realized_turno_without_details_requires_review_and_is_snapshotted(self):
        appointment = Turno.objects.create(
            cliente=self.client_profile,
            fecha=self.requested_date - timedelta(days=1),
            hora_inicio=time(11, 0),
            estado=Turno.Estado.REALIZADO,
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(
            result.outcome, TechnicalRiskOutcome.REQUIERE_REVISION
        )
        self.assertIn(INCOMPLETE_HISTORY_RULE_CODE, result.rule_codes)
        missing = next(
            item for item in result.missing_data
            if item['code'] == INCOMPLETE_HISTORY_RULE_CODE
        )
        self.assertEqual(missing['turno_id'], appointment.pk)
        self.assertEqual(missing['detalle_count'], 0)
        snapshot = result.input_snapshot['inconsistencias_historial'][0]
        self.assertEqual(snapshot['turno_id'], appointment.pk)
        self.assertEqual(snapshot['estado'], Turno.Estado.REALIZADO)
        self.assertEqual(snapshot['detalle_count'], 0)
        trigger = next(
            item for item in result.result_snapshot['reglas_disparadas']
            if item['code'] == INCOMPLETE_HISTORY_RULE_CODE
        )
        self.assertEqual(trigger['kind'], 'HISTORY_INCONSISTENCY')
        self.assertEqual(
            trigger['outcome'], TechnicalRiskOutcome.REQUIERE_REVISION
        )

    def test_future_realized_turno_without_details_is_ignored(self):
        Turno.objects.create(
            cliente=self.client_profile,
            fecha=self.requested_date + timedelta(days=1),
            hora_inicio=time(11, 0),
            estado=Turno.Estado.REALIZADO,
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)
        self.assertNotIn(INCOMPLETE_HISTORY_RULE_CODE, result.rule_codes)
        self.assertEqual(
            result.input_snapshot['inconsistencias_historial'], []
        )

    def test_client_without_turnos_is_not_history_inconsistency(self):
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)
        self.assertNotIn(INCOMPLETE_HISTORY_RULE_CODE, result.rule_codes)
        self.assertEqual(result.missing_data, ())

    def test_realized_turno_with_detail_remains_normal_history(self):
        detail = self.create_history(
            self.service_a, self.requested_date - timedelta(days=1)
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)
        self.assertNotIn(INCOMPLETE_HISTORY_RULE_CODE, result.rule_codes)
        self.assertEqual(
            result.input_snapshot['inconsistencias_historial'], []
        )
        self.assertEqual(result.relevant_history[0]['detalle_id'], detail.pk)

    def test_global_minimum_date_is_maximum_of_triggered_dates(self):
        self.create_interval_rule(
            'A_TO_B_45', TechnicalRiskOutcome.ADVERTENCIA, dias_minimos=45
        )
        self.create_interval_rule(
            'C_TO_B_60',
            TechnicalRiskOutcome.REQUIERE_REVISION,
            servicio_origen=self.service_c,
            dias_minimos=60,
        )
        self.create_history(
            self.service_a, self.requested_date - timedelta(days=10), hour=9
        )
        self.create_history(
            self.service_c, self.requested_date - timedelta(days=10), hour=10
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(
            result.minimum_recommended_date,
            self.requested_date + timedelta(days=50),
        )

    def test_requested_services_are_evaluated_as_directed_interactions(self):
        self.create_interval_rule(
            'A_TO_B_SAME_REQUEST', TechnicalRiskOutcome.NO_APTO
        )
        self.publish()

        result = self.evaluate([self.service_a, self.service_b])

        self.assertEqual(result.outcome, TechnicalRiskOutcome.NO_APTO)
        trigger = result.result_snapshot['reglas_disparadas'][0]
        self.assertEqual(trigger['kind'], 'REQUESTED_SERVICE_INTERACTION')
        self.assertEqual(trigger['evidence']['dias_entre_servicios'], 0)

    def create_diagnosis_rule(self, code='DIAGNOSIS', **overrides):
        values = {
            'politica': self.policy,
            'code': code,
            'servicio_destino': self.service_b,
            'antiguedad_maxima_dias': 30,
            'outcome_si_falta': TechnicalRiskOutcome.NO_APTO,
            'outcome_si_vencido': TechnicalRiskOutcome.ADVERTENCIA,
            'outcome_si_incompleto': TechnicalRiskOutcome.REQUIERE_REVISION,
            'outcome_si_procedencia_no_confiable': (
                TechnicalRiskOutcome.REQUIERE_REVISION
            ),
        }
        values.update(overrides)
        return ReglaDiagnosticoTecnico.objects.create(**values)

    def create_diagnosis(self, *, days_old=0, complete=True, source='PROFESIONAL'):
        fields = {}
        if complete:
            fields = {
                'tipo_cabello': TipoCabello.objects.create(nombre='Tipo test'),
                'grosor_cabello': GrosorCabello.objects.create(nombre='Grosor test'),
                'porosidad_cabello': PorosidadCabello.objects.create(
                    nombre='Porosidad test'
                ),
                'cuero_cabelludo': CueroCabelludo.objects.create(
                    nombre='Cuero test'
                ),
                'estado_general': EstadoGeneral.objects.create(
                    nombre='Estado test'
                ),
            }
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            procedencia=source,
            **fields,
        )
        diagnosis_date = self.requested_date - timedelta(days=days_old)
        diagnosis_datetime = timezone.make_aware(
            datetime.combine(diagnosis_date, time(12, 0)),
            timezone.get_current_timezone(),
        )
        DiagnosticoCapilar.objects.filter(pk=diagnosis.pk).update(
            fecha_diagnostico=diagnosis_datetime
        )
        diagnosis.refresh_from_db()
        return diagnosis

    def test_diagnosis_missing_is_explainable(self):
        self.create_diagnosis_rule()
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.outcome, TechnicalRiskOutcome.NO_APTO)
        self.assertEqual(
            result.result_snapshot['reglas_disparadas'][0]['kind'],
            'DIAGNOSIS_MISSING',
        )

    def test_complete_trusted_diagnosis_at_age_limit_is_valid(self):
        self.create_diagnosis_rule()
        self.create_diagnosis(days_old=30)
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)
        self.assertEqual(result.rule_codes, ())

    def test_expired_incomplete_and_untrusted_diagnosis_keep_all_evidence(self):
        self.create_diagnosis_rule()
        self.create_diagnosis(
            days_old=31,
            complete=False,
            source=DiagnosticoCapilar.Procedencia.DESCONOCIDO,
        )
        self.publish()

        result = self.evaluate()

        kinds = {
            trigger['kind']
            for trigger in result.result_snapshot['reglas_disparadas']
        }
        self.assertSetEqual(
            kinds,
            {
                'DIAGNOSIS_EXPIRED',
                'DIAGNOSIS_INCOMPLETE',
                'DIAGNOSIS_UNTRUSTED_SOURCE',
            },
        )
        self.assertEqual(
            result.outcome, TechnicalRiskOutcome.REQUIERE_REVISION
        )
        snapshot = result.input_snapshot['diagnostico_usado']
        self.assertNotIn('observaciones', snapshot)
        self.assertNotIn('recomendaciones', snapshot)

    def test_exact_diagnosis_rule_precedes_family_rule(self):
        self.create_diagnosis_rule(
            code='EXACT_DIAGNOSIS',
            outcome_si_falta=TechnicalRiskOutcome.ADVERTENCIA,
        )
        self.create_diagnosis_rule(
            code='FAMILY_DIAGNOSIS',
            servicio_destino=None,
            familia_destino=self.family_b,
            outcome_si_falta=TechnicalRiskOutcome.NO_APTO,
        )
        self.publish()

        result = self.evaluate()

        self.assertEqual(result.rule_codes, ('EXACT_DIAGNOSIS',))
        self.assertEqual(result.outcome, TechnicalRiskOutcome.ADVERTENCIA)

    def test_risk_level_alone_does_not_infer_diagnosis_policy(self):
        self.create_diagnosis_rule(
            code='HIGH_ONLY', servicio_destino=self.service_a
        )
        self.publish()

        low_result = self.evaluate([self.service_c])
        high_result = self.evaluate([self.service_a])

        self.assertEqual(low_result.outcome, TechnicalRiskOutcome.APTO)
        self.assertEqual(high_result.outcome, TechnicalRiskOutcome.NO_APTO)

    def create_frequency_rule(self, **overrides):
        values = {
            'politica': self.policy,
            'code': 'FREQUENCY',
            'familia': self.family_a,
            'ventana_dias': 30,
            'cantidad_maxima': 2,
            'outcome': TechnicalRiskOutcome.ADVERTENCIA,
        }
        values.update(overrides)
        return ReglaFrecuenciaTecnica.objects.create(**values)

    def test_frequency_allows_exact_limit_and_triggers_above_it(self):
        self.create_frequency_rule()
        first = self.create_history(
            self.service_a, self.requested_date - timedelta(days=5), hour=9
        )
        self.publish()

        exact_limit = self.evaluate([self.service_a])
        self.assertEqual(exact_limit.outcome, TechnicalRiskOutcome.APTO)

        self.create_history(
            self.service_a, self.requested_date - timedelta(days=10), hour=10
        )
        above_limit = self.evaluate([self.service_a])
        self.assertEqual(above_limit.outcome, TechnicalRiskOutcome.ADVERTENCIA)
        trigger = above_limit.result_snapshot['reglas_disparadas'][0]
        self.assertEqual(trigger['evidence']['cantidad_proyectada'], 3)
        self.assertIn(first.pk, trigger['evidence']['detalle_ids'])

    def test_frequency_ignores_events_outside_window(self):
        self.create_frequency_rule(cantidad_maxima=1)
        self.create_history(
            self.service_a, self.requested_date - timedelta(days=31)
        )
        self.publish()

        result = self.evaluate([self.service_a])

        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)

    def test_frequency_counts_multiple_requested_services_in_same_family(self):
        related = self.create_service('Servicio A2', self.family_a, 'BAJO')
        self.create_frequency_rule(cantidad_maxima=1)
        self.publish()

        result = self.evaluate([self.service_a, related])

        self.assertEqual(result.outcome, TechnicalRiskOutcome.ADVERTENCIA)
        trigger = result.result_snapshot['reglas_disparadas'][0]
        self.assertEqual(trigger['evidence']['eventos_solicitados'], 2)

    def test_multiservice_outcome_uses_restrictive_precedence_and_all_codes(self):
        self.create_diagnosis_rule(
            code='WARNING_B',
            outcome_si_falta=TechnicalRiskOutcome.ADVERTENCIA,
        )
        self.create_diagnosis_rule(
            code='REVIEW_C',
            servicio_destino=self.service_c,
            outcome_si_falta=TechnicalRiskOutcome.REQUIERE_REVISION,
        )
        self.create_diagnosis_rule(
            code='BLOCK_A',
            servicio_destino=self.service_a,
            outcome_si_falta=TechnicalRiskOutcome.NO_APTO,
        )
        self.publish()

        warning = self.evaluate([self.service_b])
        review = self.evaluate([self.service_b, self.service_c])
        blocked = self.evaluate(
            [self.service_a, self.service_b, self.service_c]
        )

        self.assertEqual(warning.outcome, TechnicalRiskOutcome.ADVERTENCIA)
        self.assertEqual(review.outcome, TechnicalRiskOutcome.REQUIERE_REVISION)
        self.assertEqual(blocked.outcome, TechnicalRiskOutcome.NO_APTO)
        self.assertSetEqual(
            set(blocked.rule_codes), {'WARNING_B', 'REVIEW_C', 'BLOCK_A'}
        )

    def test_unclassified_service_requires_review(self):
        unclassified = Servicio.objects.create(nombre='Sin clasificación')
        self.publish()

        result = self.evaluate([unclassified])

        self.assertEqual(
            result.outcome, TechnicalRiskOutcome.REQUIERE_REVISION
        )
        self.assertEqual(
            result.rule_codes, ('SERVICE_TECHNICAL_PROFILE_MISSING',)
        )

    def test_missing_or_unknown_policy_fails_closed_as_configuration(self):
        with self.assertRaises(TechnicalRiskConfigurationError):
            self.evaluate(policy_version='EVAL-V1')
        with self.assertRaises(TechnicalRiskConfigurationError):
            self.evaluate(policy_version='DOES-NOT-EXIST')

        self.publish()
        with self.assertRaises(TechnicalRiskConfigurationError):
            self.evaluate(policy_version='UNKNOWN-VERSION')

    def test_rule_reference_deactivated_after_publish_fails_closed(self):
        self.create_interval_rule(
            'INACTIVE_ORIGIN', TechnicalRiskOutcome.ADVERTENCIA
        )
        self.publish()
        self.service_a.activo = False
        self.service_a.save(update_fields=['activo'])

        with self.assertRaises(TechnicalRiskConfigurationError):
            self.evaluate()

    def test_same_input_and_version_is_deterministic_and_history_is_versioned(self):
        self.create_interval_rule(
            'VERSION_ONE', TechnicalRiskOutcome.ADVERTENCIA
        )
        self.create_history(
            self.service_a, self.requested_date - timedelta(days=10)
        )
        self.publish()

        first = self.evaluate()
        repeated = self.evaluate()
        self.assertEqual(first.result_snapshot, repeated.result_snapshot)
        stored = persist_technical_risk_evaluation(result=first)

        policy_v2 = PoliticaRiesgoTecnico.objects.create(version='EVAL-V2')
        ReglaIntervaloTecnico.objects.create(
            politica=policy_v2,
            code='VERSION_TWO',
            servicio_origen=self.service_a,
            servicio_destino=self.service_b,
            dias_minimos=45,
            outcome=TechnicalRiskOutcome.NO_APTO,
        )
        self.publish(policy_v2)

        v2 = self.evaluate(policy_version='EVAL-V2')
        stored_v2 = persist_technical_risk_evaluation(result=v2)
        v1_again = self.evaluate(policy_version='EVAL-V1')
        stored.refresh_from_db()

        self.assertEqual(v2.outcome, TechnicalRiskOutcome.NO_APTO)
        self.assertEqual(v1_again.outcome, TechnicalRiskOutcome.ADVERTENCIA)
        self.assertEqual(stored.result_snapshot['policy_version'], 'EVAL-V1')
        self.assertEqual(stored.result_snapshot['rule_codes'], ['VERSION_ONE'])
        self.assertEqual(stored.outcome, TechnicalRiskOutcome.ADVERTENCIA)
        self.assertEqual(stored_v2.result_snapshot['policy_version'], 'EVAL-V2')
        self.assertEqual(stored_v2.result_snapshot['rule_codes'], ['VERSION_TWO'])

    def test_controlled_supersession_only_links_new_evaluation(self):
        self.create_interval_rule(
            'SUPERSESSION_V1', TechnicalRiskOutcome.ADVERTENCIA
        )
        self.create_history(
            self.service_a, self.requested_date - timedelta(days=10)
        )
        self.publish()
        first_result = self.evaluate()
        first = persist_technical_risk_evaluation(result=first_result)
        first_snapshot = first.result_snapshot.copy()

        policy_v2 = PoliticaRiesgoTecnico.objects.create(
            version='SUPERSESSION-V2'
        )
        ReglaIntervaloTecnico.objects.create(
            politica=policy_v2,
            code='SUPERSESSION_V2',
            servicio_origen=self.service_a,
            servicio_destino=self.service_b,
            dias_minimos=45,
            outcome=TechnicalRiskOutcome.NO_APTO,
        )
        self.publish(policy_v2)
        second_result = self.evaluate(policy_version='SUPERSESSION-V2')
        second = persist_technical_risk_evaluation(result=second_result)

        superseded = supersede_technical_risk_evaluation(
            original_evaluation_id=first.pk,
            replacement_evaluation_id=second.pk,
        )
        superseded.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(superseded.superseded_by, second)
        self.assertEqual(superseded.outcome, TechnicalRiskOutcome.ADVERTENCIA)
        self.assertEqual(superseded.result_snapshot, first_snapshot)
        self.assertEqual(
            superseded.result_snapshot['policy_version'], 'EVAL-V1'
        )
        self.assertEqual(second.outcome, TechnicalRiskOutcome.NO_APTO)
        audit = Auditoria.objects.get(
            tabla='EvaluacionRiesgoTecnico',
            registro_id=first.pk,
            valor_nuevo__event=TECHNICAL_ASSESSMENT_SUPERSEDED,
        )
        self.assertEqual(audit.valor_nuevo['superseded_by_id'], second.pk)

        repeated = supersede_technical_risk_evaluation(
            original_evaluation_id=first.pk,
            replacement_evaluation_id=second.pk,
        )
        self.assertEqual(repeated.superseded_by_id, second.pk)
        self.assertEqual(
            Auditoria.objects.filter(
                tabla='EvaluacionRiesgoTecnico',
                registro_id=first.pk,
                valor_nuevo__event=TECHNICAL_ASSESSMENT_SUPERSEDED,
            ).count(),
            1,
        )

        superseded.outcome = TechnicalRiskOutcome.NO_APTO
        with self.assertRaises(ValidationError):
            superseded.save()

        with self.assertRaises(TechnicalRiskSupersessionError):
            supersede_technical_risk_evaluation(
                original_evaluation_id=second.pk,
                replacement_evaluation_id=first.pk,
            )

    def test_supersession_rejects_self_reference(self):
        self.publish()
        evaluation = persist_technical_risk_evaluation(result=self.evaluate())

        with self.assertRaises(TechnicalRiskSupersessionError):
            supersede_technical_risk_evaluation(
                original_evaluation_id=evaluation.pk,
                replacement_evaluation_id=evaluation.pk,
            )

    def test_supersession_rejects_different_client(self):
        self.publish()
        original = persist_technical_risk_evaluation(result=self.evaluate())
        other_user = Usuario.objects.create_user(
            email='other-supersession-client@test.com',
            password='testpass123',
        )
        other_client = Cliente.objects.create(usuario=other_user)
        replacement_result = evaluate_booking_risk(
            cliente=other_client,
            servicios=[self.service_b],
            fecha_solicitada=self.requested_date,
            policy_version='EVAL-V1',
        )
        replacement = persist_technical_risk_evaluation(
            result=replacement_result
        )

        with self.assertRaises(TechnicalRiskSupersessionError):
            supersede_technical_risk_evaluation(
                original_evaluation_id=original.pk,
                replacement_evaluation_id=replacement.pk,
            )

    def test_evaluator_has_no_business_side_effects(self):
        self.publish()
        client_before = model_to_dict(self.client_profile)
        counts_before = {
            'turnos': Turno.objects.count(),
            'details': DetalleTurno.objects.count(),
            'routines': Rutina.objects.count(),
            'agendas': AgendaCuidados.objects.count(),
            'payments': Pago.objects.count(),
            'notifications': Notificacion.objects.count(),
            'evaluations': EvaluacionRiesgoTecnico.objects.count(),
            'audits': Auditoria.objects.count(),
        }

        result = self.evaluate()

        self.client_profile.refresh_from_db()
        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)
        self.assertEqual(model_to_dict(self.client_profile), client_before)
        self.assertEqual(
            {
                'turnos': Turno.objects.count(),
                'details': DetalleTurno.objects.count(),
                'routines': Rutina.objects.count(),
                'agendas': AgendaCuidados.objects.count(),
                'payments': Pago.objects.count(),
                'notifications': Notificacion.objects.count(),
                'evaluations': EvaluacionRiesgoTecnico.objects.count(),
                'audits': Auditoria.objects.count(),
            },
            counts_before,
        )

    def test_persistence_is_separate_and_audited_without_sensitive_data(self):
        self.publish()
        result = self.evaluate()

        evaluation = persist_technical_risk_evaluation(result=result)

        self.assertEqual(EvaluacionRiesgoTecnico.objects.count(), 1)
        self.assertEqual(evaluation.input_snapshot, result.input_snapshot)
        audit = Auditoria.objects.get(
            tabla='EvaluacionRiesgoTecnico', registro_id=evaluation.pk
        )
        self.assertEqual(
            audit.valor_nuevo['event'], TECHNICAL_ASSESSMENT_CREATED
        )
        serialized_audit = str(audit.valor_nuevo).lower()
        self.assertNotIn('formula', serialized_audit)
        self.assertNotIn('foto', serialized_audit)
        self.assertNotIn('observaciones', serialized_audit)

    @patch(
        'gestion.technical_risk_comparison.'
        'SaludCapilarService.obtener_bloqueo_salud_capilar',
        return_value=None,
    )
    @patch(
        'gestion.technical_risk_comparison.'
        'TurnoCreationService._requires_hair_damage_alert',
        return_value=True,
    )
    def test_legacy_comparison_reports_divergence_without_fallback(
        self, legacy_alert, legacy_health
    ):
        self.publish()

        comparison = compare_legacy_and_technical_risk(
            cliente=self.client_profile,
            servicios=[self.service_b],
            fecha_solicitada=self.requested_date,
            policy_version='EVAL-V1',
        )

        self.assertEqual(
            comparison['canonical'].outcome, TechnicalRiskOutcome.APTO
        )
        self.assertTrue(comparison['legacy']['hair_damage_alerts'][self.service_b.pk])
        self.assertTrue(comparison['diverges'])
        legacy_alert.assert_called_once_with(self.client_profile, self.service_b)
        legacy_health.assert_called_once_with(
            self.client_profile, [self.service_b.pk]
        )
