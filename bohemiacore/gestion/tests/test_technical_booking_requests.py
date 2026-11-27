from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    AceptacionAdvertenciaTecnica,
    Auditoria,
    DecisionRevisionTecnica,
    EvaluacionRiesgoTecnico,
    FamiliaProcesoTecnico,
    Habilidad,
    Personal,
    PersonalHabilidad,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    Servicio,
    ServicioHabilidad,
    SolicitudTecnicaReserva,
    TechnicalRiskOutcome,
    Turno,
)
from gestion.technical_booking_request_services import (
    TECHNICAL_REVIEW_APPROVED,
    TECHNICAL_WARNING_ACCEPTED,
    create_technical_booking_request,
)
from gestion.technical_risk_policy_services import publish_technical_risk_policy
from gestion.technical_risk_evaluator import TechnicalRiskEvaluationResult
from gestion.turno_creation_services import TurnoAvailabilityService
from usuarios.models import Cliente, Usuario


class TechnicalBookingRequestTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user = Usuario.objects.create_user(
            email='client-bh057@test.com',
            password='pass1234',
            first_name='Client',
        )
        self.cliente = Cliente.objects.create(usuario=self.user, zona='Centro')
        self.other_user = Usuario.objects.create_user(
            email='other-bh057@test.com', password='pass1234'
        )
        self.other_client = Cliente.objects.create(
            usuario=self.other_user, zona='Norte'
        )
        self.service = Servicio.objects.create(
            nombre='Servicio técnico BH057 B',
            duracion_estimada=60,
            precio_base='1000.00',
            activo=True,
        )
        self.requested_date = timezone.localdate() + timedelta(days=3)
        self.requested_time = time(10, 0)
        self.policy = PoliticaRiesgoTecnico.objects.create(version='BH057-B-T1')
        self.api.force_authenticate(self.user)

    def result(self, outcome, *, date_value=None, client_message='Mensaje seguro'):
        date_value = date_value or self.requested_date
        rule_codes = () if outcome == TechnicalRiskOutcome.APTO else ('RULE_B',)
        missing = (
            ({'code': 'DIAGNOSTICO_ACTUALIZADO'},)
            if outcome == TechnicalRiskOutcome.REQUIERE_REVISION
            else ()
        )
        minimum = (
            date_value + timedelta(days=5)
            if outcome in {
                TechnicalRiskOutcome.ADVERTENCIA,
                TechnicalRiskOutcome.NO_APTO,
            }
            else None
        )
        return TechnicalRiskEvaluationResult(
            cliente_id=self.cliente.pk,
            politica_id=self.policy.pk,
            policy_version=self.policy.version,
            fecha_solicitada=date_value,
            outcome=outcome,
            severity=1 if rule_codes else 0,
            rule_codes=rule_codes,
            missing_data=missing,
            relevant_history=(),
            minimum_recommended_date=minimum,
            client_messages=(client_message,) if rule_codes else (),
            professional_messages=('Evidencia profesional',) if rule_codes else (),
            input_snapshot={
                'cliente_id': self.cliente.pk,
                'servicios': [{
                    'id': self.service.pk,
                    'nombre': self.service.nombre,
                }],
                'fecha_solicitada': date_value.isoformat(),
                'policy_version': self.policy.version,
                'historial_considerado': [],
                'inconsistencias_historial': [],
                'diagnostico_usado': None,
                'datos_faltantes': list(missing),
            },
            result_snapshot={
                'outcome': outcome,
                'severity': 1 if rule_codes else 0,
                'policy_version': self.policy.version,
                'rule_codes': list(rule_codes),
                'reglas_disparadas': [],
                'fecha_minima_recomendada': (
                    minimum.isoformat() if minimum else None
                ),
                'mensajes_cliente': [client_message] if rule_codes else [],
                'mensajes_profesional': (
                    ['Evidencia profesional'] if rule_codes else []
                ),
            },
        )

    def reserve_payload(self, **overrides):
        payload = {
            'servicio_ids': [self.service.pk],
            'fecha_preferida': self.requested_date.isoformat(),
            'hora_preferida': self.requested_time.isoformat(),
        }
        payload.update(overrides)
        return payload

    def create_via_api(self, outcome):
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(outcome),
        ):
            return self.api.post(
                reverse('solicitud-tecnica-reservar'),
                self.reserve_payload(),
                format='json',
            )

    def create_direct(self, outcome):
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(outcome),
        ):
            return create_technical_booking_request(
                cliente=self.cliente,
                servicios=[self.service],
                fecha_preferida=self.requested_date,
                hora_preferida=self.requested_time,
                actor=self.user,
            )

    def test_outcomes_map_to_states_without_creating_turnos(self):
        expected = {
            TechnicalRiskOutcome.APTO:
                SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
            TechnicalRiskOutcome.ADVERTENCIA:
                SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE,
            TechnicalRiskOutcome.REQUIERE_REVISION:
                SolicitudTecnicaReserva.Estado.EN_REVISION,
            TechnicalRiskOutcome.NO_APTO:
                SolicitudTecnicaReserva.Estado.RECHAZADA_TECNICAMENTE,
        }
        for outcome, state in expected.items():
            with self.subTest(outcome=outcome):
                response = self.create_via_api(outcome)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data['estado'], state)
                self.assertEqual(response.data['outcome_publico'], outcome)
                self.assertIn('aún no reserva', response.data['aviso_reserva'])
        self.assertEqual(Turno.objects.count(), 0)

    def test_real_evaluator_is_integrated_for_an_apto_request(self):
        family = FamiliaProcesoTecnico.objects.create(
            code='BH057_REAL', nombre='Familia real BH057'
        )
        PerfilTecnicoServicio.objects.create(
            servicio=self.service,
            familia=family,
            estado_clasificacion=(
                PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
            ),
            nivel_riesgo=PerfilTecnicoServicio.NivelRiesgo.BAJO,
            activa=True,
        )
        administrator = Usuario.objects.create_superuser(
            email='policy-admin-bh057@test.com', password='pass1234'
        )
        publish_technical_risk_policy(
            actor=administrator,
            policy_id=self.policy.pk,
        )

        solicitud = create_technical_booking_request(
            cliente=self.cliente,
            servicios=[self.service],
            fecha_preferida=self.requested_date,
            hora_preferida=self.requested_time,
            actor=self.user,
        )

        self.assertEqual(
            solicitud.estado,
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )
        self.assertEqual(
            solicitud.evaluacion_vigente.outcome,
            TechnicalRiskOutcome.APTO,
        )
        self.assertEqual(Turno.objects.count(), 0)

    def test_client_is_derived_and_ownership_is_enforced(self):
        response = self.create_via_api(TechnicalRiskOutcome.APTO)
        request_id = response.data['id']
        injected = self.create_via_api(TechnicalRiskOutcome.APTO)
        # A second explicit call verifies arbitrary ownership input is rejected.
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(TechnicalRiskOutcome.APTO),
        ):
            rejected = self.api.post(
                reverse('solicitud-tecnica-reservar'),
                self.reserve_payload(cliente_id=self.other_client.pk),
                format='json',
            )
        self.assertEqual(injected.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)

        self.api.force_authenticate(self.other_user)
        foreign = self.api.get(
            reverse('solicitud-tecnica-detail', args=[request_id])
        )
        self.assertEqual(foreign.status_code, status.HTTP_404_NOT_FOUND)
        listed = self.api.get(reverse('solicitud-tecnica-list'))
        self.assertEqual(listed.data, [])

    def test_warning_acceptance_is_explicit_versioned_audited_and_idempotent(self):
        response = self.create_via_api(TechnicalRiskOutcome.ADVERTENCIA)
        request_id = response.data['id']
        self.assertEqual(
            response.data['estado'],
            SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE,
        )
        url = reverse(
            'solicitud-tecnica-aceptar-advertencia', args=[request_id]
        )
        accepted = self.api.post(url, {}, format='json')
        repeated = self.api.post(url, {}, format='json')
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(
            accepted.data['estado'],
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )
        evidence = AceptacionAdvertenciaTecnica.objects.get(
            solicitud_id=request_id
        )
        self.assertEqual(evidence.policy_version, self.policy.version)
        self.assertEqual(evidence.warning_codes, ['RULE_B'])
        self.assertEqual(
            AceptacionAdvertenciaTecnica.objects.filter(
                solicitud_id=request_id
            ).count(),
            1,
        )
        self.assertTrue(Auditoria.objects.filter(
            registro_id=request_id,
            valor_nuevo__event=TECHNICAL_WARNING_ACCEPTED,
        ).exists())

    def test_foreign_client_cannot_accept_warning(self):
        request_id = self.create_via_api(
            TechnicalRiskOutcome.ADVERTENCIA
        ).data['id']
        self.api.force_authenticate(self.other_user)
        response = self.api.post(reverse(
            'solicitud-tecnica-aceptar-advertencia', args=[request_id]
        ))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_reevaluation_supersedes_immutable_evidence_and_old_warning(self):
        request_id = self.create_via_api(
            TechnicalRiskOutcome.ADVERTENCIA
        ).data['id']
        solicitud = SolicitudTecnicaReserva.objects.get(pk=request_id)
        previous = solicitud.evaluacion_vigente
        previous_snapshot = dict(previous.result_snapshot)
        next_date = self.requested_date + timedelta(days=1)
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(
                TechnicalRiskOutcome.APTO,
                date_value=next_date,
            ),
        ) as evaluator:
            response = self.api.post(
                reverse('solicitud-tecnica-reevaluar', args=[request_id]),
                {'fecha_preferida': next_date.isoformat()},
                format='json',
            )
        self.assertEqual(
            evaluator.call_args.kwargs['policy_version'],
            self.policy.version,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        solicitud.refresh_from_db()
        previous.refresh_from_db()
        self.assertEqual(solicitud.intento, 2)
        self.assertEqual(previous.superseded_by_id, solicitud.evaluacion_vigente_id)
        self.assertEqual(previous.result_snapshot, previous_snapshot)
        self.assertEqual(solicitud.intentos_evaluacion.count(), 2)
        old_warning = self.api.post(reverse(
            'solicitud-tecnica-aceptar-advertencia', args=[request_id]
        ))
        self.assertEqual(old_warning.status_code, status.HTTP_409_CONFLICT)

    def test_multiple_requests_do_not_change_slot_availability(self):
        professional = Personal.objects.create(
            nombre='Disponible', apellido='BH057', rol='colorista', activo=True
        )
        args = {
            'fecha': self.requested_date,
            'hora_inicio': self.requested_time,
            'servicio': self.service,
            'profesional': professional,
            'check_schedule': False,
        }
        before = TurnoAvailabilityService.is_slot_available(**args)
        for _ in range(3):
            self.create_direct(TechnicalRiskOutcome.APTO)
        after = TurnoAvailabilityService.is_slot_available(**args)
        self.assertTrue(before)
        self.assertTrue(after)
        self.assertEqual(Turno.objects.count(), 0)
        self.assertEqual(SolicitudTecnicaReserva.objects.count(), 3)


class TechnicalBookingReviewTests(TechnicalBookingRequestTests):
    def setUp(self):
        super().setUp()
        self.review_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='review_technical_booking',
        )
        self.diagnosis_skill, _ = Habilidad.objects.get_or_create(
            code='DIAGNOSTICO',
            defaults={'nombre': 'Diagnóstico', 'activa': True},
        )
        if not self.diagnosis_skill.activa:
            self.diagnosis_skill.activa = True
            self.diagnosis_skill.save(update_fields=['activa'])

    def reviewer(self, suffix='one', *, permission=True, skill=True, active=True):
        user = Usuario.objects.create_user(
            email=f'reviewer-{suffix}@test.com', password='pass1234'
        )
        personal = Personal.objects.create(
            usuario=user,
            nombre='Review',
            apellido=suffix,
            rol='colorista',
            activo=active,
        )
        if permission:
            user.user_permissions.add(self.review_permission)
        if skill:
            PersonalHabilidad.objects.create(
                personal=personal,
                habilidad=self.diagnosis_skill,
                activa=True,
            )
        return user, personal

    def test_eligible_individual_permission_can_queue_and_approve(self):
        request_id = self.create_via_api(
            TechnicalRiskOutcome.REQUIERE_REVISION
        ).data['id']
        reviewer, _ = self.reviewer()
        self.api.force_authenticate(reviewer)
        queue = self.api.get(reverse('solicitud-tecnica-cola'))
        self.assertEqual(queue.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in queue.data], [request_id])
        self.assertNotIn('formula', str(queue.data).lower())
        approved = self.api.post(
            reverse('solicitud-tecnica-revisar', args=[request_id]),
            {'accion': 'APROBAR', 'motivo': 'Evidencia suficiente'},
            format='json',
        )
        repeated = self.api.post(
            reverse('solicitud-tecnica-revisar', args=[request_id]),
            {'accion': 'APROBAR', 'motivo': 'Evidencia suficiente'},
            format='json',
        )
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(
            approved.data['estado'],
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )
        self.assertEqual(
            DecisionRevisionTecnica.objects.filter(
                solicitud_id=request_id
            ).count(),
            1,
        )
        self.assertTrue(Auditoria.objects.filter(
            registro_id=request_id,
            valor_nuevo__event=TECHNICAL_REVIEW_APPROVED,
        ).exists())
        self.assertEqual(Turno.objects.count(), 0)

    def test_review_reject_and_information_transitions_hide_internal_reason(self):
        reviewer, _ = self.reviewer()
        for action, payload, expected in (
            (
                'RECHAZAR',
                {
                    'motivo': 'Nota clínica interna',
                    'mensaje_cliente': 'Por seguridad no podemos aprobarla.',
                },
                SolicitudTecnicaReserva.Estado.RECHAZADA_TECNICAMENTE,
            ),
            (
                'SOLICITAR_INFORMACION',
                {'datos_faltantes': ['DIAGNOSTICO_ACTUALIZADO']},
                SolicitudTecnicaReserva.Estado.INFORMACION_REQUERIDA,
            ),
        ):
            self.api.force_authenticate(self.user)
            request_id = self.create_via_api(
                TechnicalRiskOutcome.REQUIERE_REVISION
            ).data['id']
            self.api.force_authenticate(reviewer)
            response = self.api.post(
                reverse('solicitud-tecnica-revisar', args=[request_id]),
                {'accion': action, **payload},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data['estado'], expected)

            self.api.force_authenticate(self.user)
            public = self.api.get(
                reverse('solicitud-tecnica-detail', args=[request_id])
            )
            self.assertNotIn('Nota clínica interna', str(public.data))
            if action == 'RECHAZAR':
                self.assertEqual(
                    public.data['mensaje_cliente'],
                    'Por seguridad no podemos aprobarla.',
                )
            else:
                self.assertEqual(
                    public.data['faltantes'], ['DIAGNOSTICO_ACTUALIZADO']
                )

    def test_recommend_date_does_not_approve_and_requires_reevaluation(self):
        request_id = self.create_via_api(
            TechnicalRiskOutcome.REQUIERE_REVISION
        ).data['id']
        reviewer, _ = self.reviewer()
        recommended = self.requested_date + timedelta(days=10)
        self.api.force_authenticate(reviewer)
        response = self.api.post(
            reverse('solicitud-tecnica-revisar', args=[request_id]),
            {
                'accion': 'RECOMENDAR_OTRA_FECHA',
                'fecha_recomendada': recommended.isoformat(),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['estado'],
            SolicitudTecnicaReserva.Estado.EN_REVISION,
        )
        self.assertEqual(response.data['fecha_recomendada'], recommended.isoformat())
        self.assertEqual(Turno.objects.count(), 0)

    def test_missing_permission_skill_or_active_personal_is_forbidden(self):
        request_id = self.create_via_api(
            TechnicalRiskOutcome.REQUIERE_REVISION
        ).data['id']
        for suffix, options in (
            ('no-permission', {'permission': False}),
            ('no-skill', {'skill': False}),
            ('inactive', {'active': False}),
        ):
            user, _ = self.reviewer(suffix, **options)
            self.api.force_authenticate(user)
            self.assertEqual(
                self.api.get(reverse('solicitud-tecnica-cola')).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.api.post(
                    reverse('solicitud-tecnica-revisar', args=[request_id]),
                    {'accion': 'APROBAR', 'motivo': 'No debería operar'},
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )

        admin = Usuario.objects.create_superuser(
            email='admin-no-skill@test.com', password='pass1234'
        )
        Personal.objects.create(
            usuario=admin,
            nombre='Admin',
            apellido='Sin skill',
            rol='administrador',
            activo=True,
        )
        self.api.force_authenticate(admin)
        self.assertEqual(
            self.api.get(reverse('solicitud-tecnica-cola')).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_incompatible_reviewer_does_not_see_or_decide(self):
        required_skill = Habilidad.objects.create(
            code='BH057_SPECIAL', nombre='Especial BH057', activa=True
        )
        ServicioHabilidad.objects.create(
            servicio=self.service, habilidad=required_skill
        )
        request_id = self.create_via_api(
            TechnicalRiskOutcome.REQUIERE_REVISION
        ).data['id']
        reviewer, _ = self.reviewer('incompatible')
        self.api.force_authenticate(reviewer)
        queue = self.api.get(reverse('solicitud-tecnica-cola'))
        self.assertEqual(queue.status_code, status.HTTP_200_OK)
        self.assertEqual(queue.data, [])
        decision = self.api.post(
            reverse('solicitud-tecnica-revisar', args=[request_id]),
            {'accion': 'APROBAR', 'motivo': 'No compatible'},
            format='json',
        )
        self.assertEqual(decision.status_code, status.HTTP_403_FORBIDDEN)

    def test_second_incompatible_transition_is_rejected_under_lock(self):
        request_id = self.create_via_api(
            TechnicalRiskOutcome.REQUIERE_REVISION
        ).data['id']
        reviewer_one, _ = self.reviewer('lock-one')
        reviewer_two, _ = self.reviewer('lock-two')
        url = reverse('solicitud-tecnica-revisar', args=[request_id])
        self.api.force_authenticate(reviewer_one)
        first = self.api.post(
            url,
            {'accion': 'APROBAR', 'motivo': 'Primera decisión'},
            format='json',
        )
        self.api.force_authenticate(reviewer_two)
        second = self.api.post(
            url,
            {
                'accion': 'RECHAZAR',
                'motivo': 'Decisión incompatible',
                'mensaje_cliente': 'Mensaje seguro',
            },
            format='json',
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            DecisionRevisionTecnica.objects.filter(
                solicitud_id=request_id
            ).count(),
            1,
        )
