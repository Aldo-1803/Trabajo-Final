from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    Auditoria,
    BloqueoAgenda,
    DecisionRevisionTecnica,
    Equipamiento,
    FamiliaProcesoTecnico,
    Habilidad,
    Personal,
    PersonalHabilidad,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    RequisitoServicio,
    Servicio,
    ServicioHabilidad,
    SolicitudTecnicaReserva,
    TechnicalRiskOutcome,
    TipoEquipamiento,
    Turno,
)
from gestion.technical_booking_request_services import (
    TECHNICAL_REVIEW_APPROVED,
    TECHNICAL_REVIEW_DATE_RECOMMENDED,
    TECHNICAL_REVIEW_INFORMATION_REQUESTED,
    TECHNICAL_REVIEW_REJECTED,
)
from gestion.technical_risk_evaluator import TechnicalRiskEvaluationResult
from gestion.turno_creation_services import TurnoAvailabilityService
from usuarios.models import Cliente, Usuario


class TechnicalBookingBlockerBase(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user = Usuario.objects.create_user(
            email='client-bh057-b1@test.com', password='pass1234'
        )
        self.cliente = Cliente.objects.create(usuario=self.user, zona='Centro')
        self.service = Servicio.objects.create(
            nombre='Servicio B1',
            duracion_estimada=60,
            precio_base='1000.00',
            activo=True,
        )
        self.requested_date = timezone.localdate() + timedelta(days=5)
        self.requested_time = time(10, 0)
        self.policy = PoliticaRiesgoTecnico.objects.create(version='BH057-B1')
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
        self.api.force_authenticate(self.user)

    def result(
        self,
        outcome,
        *,
        date_value=None,
        services=None,
        input_overrides=None,
        result_overrides=None,
    ):
        date_value = date_value or self.requested_date
        services = services or [self.service]
        rule_codes = () if outcome == TechnicalRiskOutcome.APTO else ('RULE_B1',)
        missing = (
            ({'code': 'DIAGNOSTICO_ACTUALIZADO'},)
            if outcome == TechnicalRiskOutcome.REQUIERE_REVISION
            else ()
        )
        input_snapshot = {
            'cliente_id': self.cliente.pk,
            'servicios': [
                {'id': service.pk, 'nombre': service.nombre}
                for service in services
            ],
            'fecha_solicitada': date_value.isoformat(),
            'policy_version': self.policy.version,
            'historial_considerado': [],
            'inconsistencias_historial': [],
            'diagnostico_usado': None,
            'datos_faltantes': list(missing),
        }
        input_snapshot.update(input_overrides or {})
        result_snapshot = {
            'outcome': outcome,
            'severity': 1 if rule_codes else 0,
            'policy_version': self.policy.version,
            'rule_codes': list(rule_codes),
            'reglas_disparadas': [],
            'fecha_minima_recomendada': None,
            'mensajes_cliente': ['Mensaje seguro'] if rule_codes else [],
            'mensajes_profesional': (
                ['Mensaje profesional seguro'] if rule_codes else []
            ),
        }
        result_snapshot.update(result_overrides or {})
        return TechnicalRiskEvaluationResult(
            cliente_id=self.cliente.pk,
            politica_id=self.policy.pk,
            policy_version=self.policy.version,
            fecha_solicitada=date_value,
            outcome=outcome,
            severity=1 if rule_codes else 0,
            rule_codes=rule_codes,
            missing_data=missing,
            relevant_history=tuple(input_snapshot['historial_considerado']),
            minimum_recommended_date=None,
            client_messages=tuple(result_snapshot['mensajes_cliente']),
            professional_messages=tuple(
                result_snapshot['mensajes_profesional']
            ),
            input_snapshot=input_snapshot,
            result_snapshot=result_snapshot,
        )

    def reserve(self, outcome, *, personal=None, result=None, services=None):
        services = services or [self.service]
        result = result or self.result(outcome, services=services)
        payload = {
            'servicio_ids': [service.pk for service in services],
            'fecha_preferida': self.requested_date.isoformat(),
            'hora_preferida': self.requested_time.isoformat(),
        }
        if personal is not None:
            payload['personal_preferido_id'] = personal.pk
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=result,
        ):
            return self.api.post(
                reverse('solicitud-tecnica-reservar'), payload, format='json'
            )

    def reviewer(
        self,
        suffix,
        *,
        review_permission=True,
        diagnosis_skill=True,
        extra_permissions=(),
        extra_skills=(),
    ):
        user = Usuario.objects.create_user(
            email=f'reviewer-b1-{suffix}@test.com', password='pass1234'
        )
        personal = Personal.objects.create(
            usuario=user,
            nombre='Revisor',
            apellido=suffix,
            rol='colorista',
            activo=True,
        )
        if review_permission:
            user.user_permissions.add(self.review_permission)
        for permission in extra_permissions:
            user.user_permissions.add(permission)
        if diagnosis_skill:
            PersonalHabilidad.objects.create(
                personal=personal,
                habilidad=self.diagnosis_skill,
                activa=True,
            )
        for skill in extra_skills:
            PersonalHabilidad.objects.create(
                personal=personal,
                habilidad=skill,
                activa=True,
            )
        return user, personal

    def publish_policy(self):
        PoliticaRiesgoTecnico.objects.filter(pk=self.policy.pk).update(
            estado=PoliticaRiesgoTecnico.Estado.PUBLICADA,
            publicada_at=timezone.now(),
        )
        self.policy.refresh_from_db()

    def assert_reevaluated(self, request_id, previous, expected_state):
        solicitud = SolicitudTecnicaReserva.objects.get(pk=request_id)
        previous.refresh_from_db()
        self.assertNotEqual(solicitud.evaluacion_vigente_id, previous.pk)
        self.assertEqual(previous.superseded_by_id, solicitud.evaluacion_vigente_id)
        self.assertEqual(solicitud.intentos_evaluacion.count(), 2)
        self.assertEqual(solicitud.estado, expected_state)
        with self.assertRaises(ValidationError):
            previous.save()


class TechnicalBookingReevaluationCoverageTests(TechnicalBookingBlockerBase):
    def test_reevaluation_by_services_supersedes_and_invalidates_old_warning(self):
        response = self.reserve(TechnicalRiskOutcome.ADVERTENCIA)
        request_id = response.data['id']
        solicitud = SolicitudTecnicaReserva.objects.get(pk=request_id)
        previous = solicitud.evaluacion_vigente
        previous_snapshot = dict(previous.result_snapshot)
        other_service = Servicio.objects.create(nombre='Servicio B1 alternativo')
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(
                TechnicalRiskOutcome.APTO, services=[other_service]
            ),
        ):
            reevaluated = self.api.post(
                reverse('solicitud-tecnica-reevaluar', args=[request_id]),
                {'servicio_ids': [other_service.pk]},
                format='json',
            )
        self.assertEqual(reevaluated.status_code, status.HTTP_200_OK)
        self.assert_reevaluated(
            request_id,
            previous,
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )
        previous.refresh_from_db()
        self.assertEqual(previous.result_snapshot, previous_snapshot)
        old_warning = self.api.post(reverse(
            'solicitud-tecnica-aceptar-advertencia', args=[request_id]
        ))
        self.assertEqual(old_warning.status_code, status.HTTP_409_CONFLICT)

    def test_reevaluation_by_date_supersedes_and_recalculates_state(self):
        request_id = self.reserve(TechnicalRiskOutcome.REQUIERE_REVISION).data['id']
        previous = SolicitudTecnicaReserva.objects.get(
            pk=request_id
        ).evaluacion_vigente
        next_date = self.requested_date + timedelta(days=2)
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(
                TechnicalRiskOutcome.NO_APTO, date_value=next_date
            ),
        ):
            response = self.api.post(
                reverse('solicitud-tecnica-reevaluar', args=[request_id]),
                {'fecha_preferida': next_date.isoformat()},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_reevaluated(
            request_id,
            previous,
            SolicitudTecnicaReserva.Estado.RECHAZADA_TECNICAMENTE,
        )

    def test_reevaluation_by_preferred_personal_supersedes_evidence(self):
        request_id = self.reserve(TechnicalRiskOutcome.REQUIERE_REVISION).data['id']
        previous = SolicitudTecnicaReserva.objects.get(
            pk=request_id
        ).evaluacion_vigente
        preferred = Personal.objects.create(
            nombre='Preferida', apellido='B1', rol='colorista', activo=True
        )
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(TechnicalRiskOutcome.APTO),
        ):
            response = self.api.post(
                reverse('solicitud-tecnica-reevaluar', args=[request_id]),
                {'personal_preferido_id': preferred.pk},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['personal_preferido']['id'], preferred.pk)
        self.assert_reevaluated(
            request_id,
            previous,
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )

    def test_reevaluation_by_relevant_technical_data_supersedes_evidence(self):
        request_id = self.reserve(TechnicalRiskOutcome.REQUIERE_REVISION).data['id']
        previous = SolicitudTecnicaReserva.objects.get(
            pk=request_id
        ).evaluacion_vigente
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(TechnicalRiskOutcome.APTO),
        ):
            response = self.api.post(
                reverse('solicitud-tecnica-reevaluar', args=[request_id]),
                {'informacion_tecnica_actualizada': True},
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_reevaluated(
            request_id,
            previous,
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )


class TechnicalBookingFailClosedAndBlockingTests(TechnicalBookingBlockerBase):
    def test_service_without_profile_enters_review_in_real_flow(self):
        self.publish_policy()
        response = self.api.post(
            reverse('solicitud-tecnica-reservar'),
            {
                'servicio_ids': [self.service.pk],
                'fecha_preferida': self.requested_date.isoformat(),
                'hora_preferida': self.requested_time.isoformat(),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data['estado'], SolicitudTecnicaReserva.Estado.EN_REVISION
        )
        self.assertNotEqual(response.data['outcome_publico'], TechnicalRiskOutcome.APTO)

    def test_pending_profile_enters_review_in_real_flow(self):
        PerfilTecnicoServicio.objects.create(
            servicio=self.service,
            estado_clasificacion=PerfilTecnicoServicio.EstadoClasificacion.PENDIENTE,
            nivel_riesgo=PerfilTecnicoServicio.NivelRiesgo.NO_DEFINIDO,
        )
        self.publish_policy()
        response = self.api.post(
            reverse('solicitud-tecnica-reservar'),
            {
                'servicio_ids': [self.service.pk],
                'fecha_preferida': self.requested_date.isoformat(),
                'hora_preferida': self.requested_time.isoformat(),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data['estado'], SolicitudTecnicaReserva.Estado.EN_REVISION
        )

    def test_realized_turno_without_detail_enters_review_in_real_flow(self):
        family = FamiliaProcesoTecnico.objects.create(
            code='B1_REAL', nombre='Familia B1 real'
        )
        PerfilTecnicoServicio.objects.create(
            servicio=self.service,
            familia=family,
            estado_clasificacion=PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO,
            nivel_riesgo=PerfilTecnicoServicio.NivelRiesgo.BAJO,
        )
        Turno.objects.create(
            cliente=self.cliente,
            fecha=self.requested_date - timedelta(days=1),
            hora_inicio=time(9, 0),
            estado=Turno.Estado.REALIZADO,
        )
        self.publish_policy()
        response = self.api.post(
            reverse('solicitud-tecnica-reservar'),
            {
                'servicio_ids': [self.service.pk],
                'fecha_preferida': self.requested_date.isoformat(),
                'hora_preferida': self.requested_time.isoformat(),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data['estado'], SolicitudTecnicaReserva.Estado.EN_REVISION
        )

    def test_invalid_policy_returns_safe_error_and_rolls_back_request(self):
        response = self.api.post(
            reverse('solicitud-tecnica-reservar'),
            {
                'servicio_ids': [self.service.pk],
                'fecha_preferida': self.requested_date.isoformat(),
                'hora_preferida': self.requested_time.isoformat(),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('evaluar la solicitud de forma segura', response.data['detail'])
        self.assertNotIn(self.policy.version, response.data['detail'])
        self.assertEqual(SolicitudTecnicaReserva.objects.count(), 0)

    def test_identical_requests_do_not_block_personal_equipment_or_agenda(self):
        preferred = Personal.objects.create(
            nombre='Disponible', apellido='B1', rol='colorista', activo=True
        )
        equipment_type = TipoEquipamiento.objects.create(nombre='Equipo B1')
        equipment = Equipamiento.objects.create(
            codigo='EQ-B1', nombre='Equipo disponible B1', tipo=equipment_type
        )
        requirement = RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        slot = {
            'fecha': self.requested_date,
            'hora_inicio': self.requested_time,
            'servicio': self.service,
            'profesional': preferred,
            'check_schedule': False,
        }
        before = TurnoAvailabilityService.is_slot_available(**slot)
        first = self.reserve(
            TechnicalRiskOutcome.APTO, personal=preferred
        )
        second = self.reserve(
            TechnicalRiskOutcome.APTO, personal=preferred
        )
        after = TurnoAvailabilityService.is_slot_available(**slot)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertTrue(before)
        self.assertTrue(after)
        self.assertEqual(SolicitudTecnicaReserva.objects.count(), 2)
        self.assertEqual(Turno.objects.count(), 0)
        self.assertEqual(BloqueoAgenda.objects.count(), 0)
        self.assertEqual(Equipamiento.objects.count(), 1)
        self.assertTrue(Equipamiento.objects.filter(pk=equipment.pk).exists())
        self.assertTrue(RequisitoServicio.objects.filter(pk=requirement.pk).exists())


class TechnicalBookingPrivacyAndPermissionTests(TechnicalBookingBlockerBase):
    def structured_result(self):
        previous = Servicio.objects.create(nombre='Servicio previo B1')
        diagnosis_date = self.requested_date - timedelta(days=12)
        return self.result(
            TechnicalRiskOutcome.REQUIERE_REVISION,
            input_overrides={
                'historial_considerado': [{
                    'turno_id': 80,
                    'detalle_id': 81,
                    'servicio_id': previous.pk,
                    'fecha': (self.requested_date - timedelta(days=20)).isoformat(),
                    'hora': '09:00:00',
                    'familia_code': 'COLOR',
                    'estado_clasificacion': 'CLASIFICADO',
                    'formula': 'NO EXPONER',
                    'notas_internas': 'NO EXPONER',
                }],
                'diagnostico_usado': {
                    'id': 77,
                    'fecha': f'{diagnosis_date.isoformat()}T12:00:00-03:00',
                    'procedencia': 'PROFESIONAL',
                    'completo': True,
                    'campos_presentes': {'tipo_cabello': True},
                    'observaciones': 'NO EXPONER',
                    'fotografia': 'NO EXPONER',
                },
                'formula': 'NO EXPONER',
                'notas_internas': 'NO EXPONER',
            },
            result_overrides={
                'rule_codes': ['INTERVAL_B1', 'DIAG_B1'],
                'reglas_disparadas': [{
                    'kind': 'INTERVAL',
                    'code': 'INTERVAL_B1',
                    'parameters': {
                        'dias_minimos': 30,
                        'servicio_origen_id': previous.pk,
                        'servicio_destino_id': self.service.pk,
                        'formula': 'NO EXPONER',
                    },
                    'evidence': {
                        'servicio_previo_id': previous.pk,
                        'servicio_solicitado_id': self.service.pk,
                        'dias_transcurridos': 20,
                        'fecha_servicio_previo': (
                            self.requested_date - timedelta(days=20)
                        ).isoformat(),
                        'fecha_minima_recomendada': (
                            self.requested_date + timedelta(days=10)
                        ).isoformat(),
                        'fotografia': 'NO EXPONER',
                    },
                }],
                'fecha_minima_recomendada': (
                    self.requested_date + timedelta(days=10)
                ).isoformat(),
                'mensajes_profesional': ['Revisar intervalo y diagnóstico.'],
                'formula': 'NO EXPONER',
            },
        )

    def test_public_dto_is_owned_and_excludes_internal_evidence(self):
        response = self.reserve(
            TechnicalRiskOutcome.REQUIERE_REVISION,
            result=self.structured_result(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        serialized = str(response.data).lower()
        for forbidden in (
            'input_snapshot', 'result_snapshot', 'mensajes_profesional',
            'formula', 'notas_internas', 'fotografia', 'antecedentes',
        ):
            self.assertNotIn(forbidden, serialized)

        other_user = Usuario.objects.create_user(
            email='other-b1@test.com', password='pass1234'
        )
        Cliente.objects.create(usuario=other_user)
        self.api.force_authenticate(other_user)
        self.assertEqual(
            self.api.get(reverse(
                'solicitud-tecnica-detail', args=[response.data['id']]
            )).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.api.get(reverse('solicitud-tecnica-list')).data, []
        )

    def test_reviewer_dto_is_structured_safe_and_eligibility_filtered(self):
        request_id = self.reserve(
            TechnicalRiskOutcome.REQUIERE_REVISION,
            result=self.structured_result(),
        ).data['id']
        reviewer, _ = self.reviewer('structured')
        self.api.force_authenticate(reviewer)
        response = self.api.get(reverse('solicitud-tecnica-cola'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [request_id])
        item = response.data[0]
        self.assertEqual(item['diagnostico']['procedencia'], 'PROFESIONAL')
        self.assertEqual(item['diagnostico']['antiguedad_dias'], 12)
        self.assertEqual(item['antecedentes'][0]['servicio_nombre'], 'Servicio previo B1')
        self.assertEqual(item['intervalos'][0]['dias_minimos'], 30)
        self.assertEqual(item['datos_faltantes'][0], {
            'code': 'DIAGNOSTICO_ACTUALIZADO'
        })
        serialized = str(item).lower()
        for forbidden in (
            'input_snapshot', 'result_snapshot', 'formula',
            'notas_internas', 'fotografia', 'observaciones',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_multiservice_queue_requires_compatibility_with_every_service(self):
        second = Servicio.objects.create(nombre='Segundo Servicio B1')
        first_skill = Habilidad.objects.create(
            code='B1_FIRST', nombre='B1 primera', activa=True
        )
        second_skill = Habilidad.objects.create(
            code='B1_SECOND', nombre='B1 segunda', activa=True
        )
        ServicioHabilidad.objects.create(servicio=self.service, habilidad=first_skill)
        ServicioHabilidad.objects.create(servicio=second, habilidad=second_skill)
        request_id = self.reserve(
            TechnicalRiskOutcome.REQUIERE_REVISION,
            services=[self.service, second],
        ).data['id']

        partial, _ = self.reviewer('partial', extra_skills=[first_skill])
        self.api.force_authenticate(partial)
        self.assertEqual(self.api.get(reverse('solicitud-tecnica-cola')).data, [])

        complete, _ = self.reviewer(
            'complete', extra_skills=[first_skill, second_skill]
        )
        self.api.force_authenticate(complete)
        queue = self.api.get(reverse('solicitud-tecnica-cola'))
        self.assertEqual([item['id'] for item in queue.data], [request_id])

    def test_view_clients_does_not_grant_another_clients_technical_history(self):
        other_user = Usuario.objects.create_user(
            email='technical-history-owner-b1@test.com', password='pass1234'
        )
        other_client = Cliente.objects.create(usuario=other_user)
        view_clients = Permission.objects.get(
            content_type__app_label='usuarios', codename='view_clients'
        )
        actor, _ = self.reviewer(
            'view-clients-history',
            review_permission=False,
            extra_permissions=[view_clients],
        )
        self.api.force_authenticate(actor)
        response = self.api.get(
            reverse('diagnostico-capilar-por-cliente'),
            {'cliente_id': other_client.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_permissions_remain_separated_and_individual_grant_works(self):
        request_id = self.reserve(
            TechnicalRiskOutcome.REQUIERE_REVISION
        ).data['id']
        queue_url = reverse('solicitud-tecnica-cola')
        review_url = reverse('solicitud-tecnica-revisar', args=[request_id])

        review_without_diagnosis, _ = self.reviewer(
            'review-no-diagnosis', diagnosis_skill=False
        )
        diagnosis_without_review, _ = self.reviewer(
            'diagnosis-no-review', review_permission=False
        )
        unrelated = (
            Permission.objects.get(
                content_type__app_label='usuarios', codename='view_clients'
            ),
            Permission.objects.get(
                content_type__app_label='gestion',
                codename='manage_technical_record',
            ),
            Permission.objects.get(
                content_type__app_label='gestion', codename='manage_formulas'
            ),
        )
        actors = [review_without_diagnosis, diagnosis_without_review]
        for index, permission in enumerate(unrelated):
            actor, _ = self.reviewer(
                f'unrelated-{index}',
                review_permission=False,
                extra_permissions=[permission],
            )
            actors.append(actor)

        admin = Usuario.objects.create_superuser(
            email='admin-b1-no-skill@test.com', password='pass1234'
        )
        Personal.objects.create(
            usuario=admin,
            nombre='Admin',
            apellido='Sin diagnóstico',
            rol='administrador',
            activo=True,
        )
        actors.append(admin)
        for actor in actors:
            with self.subTest(actor=actor.email):
                self.api.force_authenticate(actor)
                self.assertEqual(
                    self.api.get(queue_url).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.api.post(
                        review_url,
                        {'accion': 'APROBAR', 'motivo': 'No autorizado'},
                        format='json',
                    ).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        allowed, _ = self.reviewer('individual-allowed')
        self.api.force_authenticate(allowed)
        self.assertEqual(self.api.get(queue_url).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.api.post(
                review_url,
                {'accion': 'APROBAR', 'motivo': 'Permiso individual válido'},
                format='json',
            ).status_code,
            status.HTTP_200_OK,
        )


class TechnicalReviewDecisionEvidenceTests(TechnicalBookingBlockerBase):
    def create_decision(self, *, action='APROBAR', payload=None):
        request_id = self.reserve(
            TechnicalRiskOutcome.REQUIERE_REVISION
        ).data['id']
        reviewer, _ = self.reviewer(f'decision-{request_id}')
        self.api.force_authenticate(reviewer)
        body = {'accion': action, **(payload or {})}
        response = self.api.post(
            reverse('solicitud-tecnica-revisar', args=[request_id]),
            body,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return request_id, reviewer, body

    def test_decision_creation_is_allowed_and_traceability_is_explicit(self):
        request_id, reviewer, _ = self.create_decision(
            payload={'motivo': 'Evidencia técnica suficiente'}
        )
        decision = DecisionRevisionTecnica.objects.get(solicitud_id=request_id)
        self.assertEqual(decision.solicitud_id, request_id)
        self.assertEqual(decision.evaluacion_id, decision.solicitud.evaluacion_vigente_id)
        self.assertEqual(decision.policy_version, self.policy.version)
        self.assertEqual(decision.actor, reviewer)
        self.assertEqual(decision.accion, DecisionRevisionTecnica.Accion.APROBAR)
        self.assertEqual(decision.motivo_interno, 'Evidencia técnica suficiente')
        self.assertEqual(
            decision.estado_anterior, SolicitudTecnicaReserva.Estado.EN_REVISION
        )
        self.assertEqual(
            decision.estado_nuevo,
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )
        self.assertIsNotNone(decision.created_at)

    def test_all_mutation_and_deletion_paths_are_blocked(self):
        request_id, _, _ = self.create_decision(
            payload={'motivo': 'Motivo histórico inmutable'}
        )
        decision = DecisionRevisionTecnica.objects.get(solicitud_id=request_id)
        decision.motivo_interno = 'Intento de cambio'
        with self.assertRaises(ValidationError):
            decision.save()
        with self.assertRaises(ValidationError):
            DecisionRevisionTecnica.objects.filter(pk=decision.pk).update(
                motivo_interno='Intento queryset'
            )
        with self.assertRaises(ValidationError):
            DecisionRevisionTecnica._base_manager.filter(pk=decision.pk).update(
                motivo_interno='Intento base manager'
            )
        with self.assertRaises(ValidationError):
            DecisionRevisionTecnica._default_manager.filter(pk=decision.pk).update(
                motivo_interno='Intento default manager'
            )
        with self.assertRaises(ValidationError):
            DecisionRevisionTecnica.objects.bulk_update(
                [decision], ['motivo_interno']
            )
        with self.assertRaises(ValidationError):
            DecisionRevisionTecnica.objects.update_or_create(
                pk=decision.pk,
                defaults={'motivo_interno': 'Intento update_or_create'},
            )
        with self.assertRaises(ValidationError):
            DecisionRevisionTecnica.objects.bulk_create(
                [decision],
                update_conflicts=True,
                update_fields=['motivo_interno'],
                unique_fields=['id'],
            )
        with self.assertRaises(ValidationError):
            decision.delete()
        with self.assertRaises(ValidationError):
            DecisionRevisionTecnica.objects.filter(pk=decision.pk).delete()

        persisted = DecisionRevisionTecnica.objects.get(pk=decision.pk)
        self.assertEqual(persisted.motivo_interno, 'Motivo histórico inmutable')
        self.assertEqual(persisted.policy_version, self.policy.version)
        self.assertEqual(
            persisted.evaluacion_id,
            persisted.solicitud.evaluacion_vigente_id,
        )

    def test_exact_retry_is_idempotent_without_duplicate_audit(self):
        request_id, _, body = self.create_decision(
            payload={'motivo': 'Misma decisión'}
        )
        url = reverse('solicitud-tecnica-revisar', args=[request_id])
        first_decision = DecisionRevisionTecnica.objects.get(
            solicitud_id=request_id
        )
        before = Auditoria.objects.filter(
            registro_id=request_id,
            valor_nuevo__event=TECHNICAL_REVIEW_APPROVED,
        ).count()
        repeated = self.api.post(url, body, format='json')
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertEqual(
            DecisionRevisionTecnica.objects.filter(
                solicitud_id=request_id
            ).count(),
            1,
        )
        self.assertEqual(
            Auditoria.objects.filter(
                registro_id=request_id,
                valor_nuevo__event=TECHNICAL_REVIEW_APPROVED,
            ).count(),
            before,
        )
        self.assertEqual(
            DecisionRevisionTecnica.objects.get(
                solicitud_id=request_id
            ).pk,
            first_decision.pk,
        )

    def test_every_decision_event_contains_reconstructable_references(self):
        cases = (
            (
                'APROBAR',
                {'motivo': 'Aprobación justificada'},
                TECHNICAL_REVIEW_APPROVED,
                SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
            ),
            (
                'RECHAZAR',
                {
                    'motivo': 'Rechazo justificado',
                    'mensaje_cliente': 'No es seguro continuar.',
                },
                TECHNICAL_REVIEW_REJECTED,
                SolicitudTecnicaReserva.Estado.RECHAZADA_TECNICAMENTE,
            ),
            (
                'SOLICITAR_INFORMACION',
                {'datos_faltantes': ['DIAGNOSTICO_ACTUALIZADO']},
                TECHNICAL_REVIEW_INFORMATION_REQUESTED,
                SolicitudTecnicaReserva.Estado.INFORMACION_REQUERIDA,
            ),
            (
                'RECOMENDAR_OTRA_FECHA',
                {
                    'fecha_recomendada': (
                        self.requested_date + timedelta(days=10)
                    ).isoformat()
                },
                TECHNICAL_REVIEW_DATE_RECOMMENDED,
                SolicitudTecnicaReserva.Estado.EN_REVISION,
            ),
        )
        for index, (action, payload, event, target_state) in enumerate(cases):
            with self.subTest(action=action):
                self.api.force_authenticate(self.user)
                request_id = self.reserve(
                    TechnicalRiskOutcome.REQUIERE_REVISION
                ).data['id']
                reviewer, _ = self.reviewer(f'audit-{index}')
                self.api.force_authenticate(reviewer)
                response = self.api.post(
                    reverse('solicitud-tecnica-revisar', args=[request_id]),
                    {'accion': action, **payload},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                decision = DecisionRevisionTecnica.objects.get(
                    solicitud_id=request_id
                )
                audit = Auditoria.objects.get(
                    registro_id=request_id,
                    valor_nuevo__event=event,
                )
                values = audit.valor_nuevo
                self.assertEqual(values['decision_id'], decision.pk)
                self.assertEqual(values['solicitud_id'], request_id)
                self.assertEqual(values['evaluation_id'], decision.evaluacion_id)
                self.assertEqual(values['policy_version'], self.policy.version)
                self.assertEqual(values['accion'], action)
                self.assertEqual(values['motivo'], decision.motivo_interno)
                self.assertEqual(
                    values['estado_anterior'],
                    SolicitudTecnicaReserva.Estado.EN_REVISION,
                )
                self.assertEqual(values['estado_nuevo'], target_state)
                self.assertEqual(audit.usuario, reviewer)
                self.assertEqual(
                    values['decision_created_at'], decision.created_at.isoformat()
                )
                serialized = str(values).lower()
                self.assertNotIn('input_snapshot', serialized)
                self.assertNotIn('result_snapshot', serialized)
                self.assertNotIn('fotografia', serialized)
