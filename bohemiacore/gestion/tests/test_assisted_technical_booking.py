from datetime import time, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    AceptacionAdvertenciaTecnica,
    Auditoria,
    ConsentimientoAdvertenciaAsistido,
    DiagnosticoCapilar,
    Habilidad,
    Pago,
    PaymentIntent,
    Personal,
    PersonalHabilidad,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    Servicio,
    ServicioHabilidad,
    SlotHold,
    SolicitudTecnicaAsistidaOperacion,
    SolicitudTecnicaReserva,
    TechnicalRiskOutcome,
    Turno,
)
from gestion.assisted_technical_booking_services import (
    ASSISTED_CONSENT_RECORDED,
    ASSISTED_REQUEST_CREATED,
    AssistedTechnicalBookingConflict,
    create_assisted_technical_request,
)
from gestion.technical_risk_evaluator import TechnicalRiskEvaluationResult
from usuarios.models import Cliente, Usuario


class AssistedTechnicalBookingTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.operator = Usuario.objects.create_user(
            email='operator-assisted@test.com', password='pass1234'
        )
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_turno_for_client',
        )
        self.operator.user_permissions.add(permission)
        self.client_user = Usuario.objects.create_user(
            email='client-assisted@test.com', password='pass1234',
            first_name='Ada', last_name='Cliente',
        )
        self.cliente = Cliente.objects.create(
            usuario=self.client_user, activo=True
        )
        self.service = Servicio.objects.create(
            nombre='Servicio asistido',
            activo=True,
            duracion_estimada=60,
            precio_base='1000.00',
        )
        self.policy = PoliticaRiesgoTecnico.objects.create(
            version='BH063-I2-T1'
        )
        self.date = timezone.localdate() + timedelta(days=5)
        self.time = time(10, 30)
        self.api.force_authenticate(self.operator)

    def result(self, outcome, *, services=None, client=None, policy=None):
        services = services or [self.service]
        client = client or self.cliente
        policy = policy or self.policy
        rules = [] if outcome == TechnicalRiskOutcome.APTO else ['SAFE_RULE']
        missing = (
            [{'code': 'DIAGNOSTICO_ACTUALIZADO'}]
            if outcome == TechnicalRiskOutcome.REQUIERE_REVISION else []
        )
        return TechnicalRiskEvaluationResult(
            cliente_id=client.pk,
            politica_id=policy.pk,
            policy_version=policy.version,
            fecha_solicitada=self.date,
            outcome=outcome,
            severity=0 if not rules else 1,
            rule_codes=tuple(rules),
            missing_data=tuple(missing),
            relevant_history=(),
            minimum_recommended_date=None,
            client_messages=(
                ('Mensaje permitido para el Cliente.',) if rules else ()
            ),
            professional_messages=(
                ('Detalle interno NO EXPONER',) if rules else ()
            ),
            input_snapshot={
                'cliente_id': client.pk,
                'servicios': [
                    {'id': item.pk, 'nombre': item.nombre} for item in services
                ],
                'fecha_solicitada': self.date.isoformat(),
                'policy_version': policy.version,
                'historial_considerado': [{
                    'notas_internas': 'NO EXPONER',
                    'formula': 'NO EXPONER',
                }],
                'diagnostico_usado': {'observaciones': 'NO EXPONER'},
                'datos_faltantes': missing,
            },
            result_snapshot={
                'outcome': outcome,
                'severity': 0 if not rules else 1,
                'policy_version': policy.version,
                'rule_codes': rules,
                'reglas_disparadas': [],
                'fecha_minima_recomendada': None,
                'mensajes_cliente': (
                    ['Mensaje permitido para el Cliente.'] if rules else []
                ),
                'mensajes_profesional': (
                    ['Detalle interno NO EXPONER'] if rules else []
                ),
                'formula': 'NO EXPONER',
            },
        )

    def payload(self, **overrides):
        payload = {
            'operation_id': str(uuid4()),
            'cliente_id': self.cliente.pk,
            'servicio_ids': [self.service.pk],
            'fecha_preferida': self.date.isoformat(),
            'hora_preferida': self.time.isoformat(),
            'medio_solicitud': 'PRESENCIAL',
        }
        payload.update(overrides)
        return payload

    def create(self, outcome=TechnicalRiskOutcome.APTO, *, payload=None, key=None,
               result=None):
        payload = payload or self.payload()
        key = key or f'create-{uuid4()}'
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=result or self.result(outcome),
        ):
            response = self.api.post(
                reverse('solicitud-tecnica-asistida-list'),
                payload,
                format='json',
                HTTP_IDEMPOTENCY_KEY=key,
            )
        return response

    def consent(self, request_id, decision, *, reason='', key=None,
                operation_id=None):
        return self.api.post(
            reverse(
                'solicitud-tecnica-asistida-consentimiento',
                args=[request_id],
            ),
            {
                'operation_id': operation_id or str(uuid4()),
                'decision': decision,
                'motivo': reason,
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=key or f'consent-{uuid4()}',
        )

    def test_recovery_uses_explicit_scoped_walkin_link_and_public_evidence(self):
        from usuarios.models import WalkInClientOperation

        permission = Permission.objects.get(content_type__app_label='usuarios', codename='create_walkin_client')
        self.operator.user_permissions.add(permission)
        alta = WalkInClientOperation.objects.create(
            actor=self.operator, cliente=self.cliente, result_created=False,
            idempotency_key_digest='a' * 64, fingerprint='b' * 64,
        )
        alta_url = reverse('walkin-client-create')
        intake = self.api.get(alta_url, {'operation_id': alta.operation_id})
        self.assertEqual(intake.status_code, 200)
        self.assertEqual(intake.data['stage'], 'CLIENT_READY')
        self.assertNotIn(self.client_user.email, intake.content.decode())
        payload = self.payload(alta_operation_id=str(alta.operation_id))
        refused = self.create(payload={**payload, 'cliente_id': self.cliente.pk + 1})
        self.assertEqual(refused.status_code, 404)
        created = self.create(TechnicalRiskOutcome.REQUIERE_REVISION, payload=payload, key='linked-create')
        self.assertEqual(created.status_code, 201, created.data)
        retry = self.create(TechnicalRiskOutcome.REQUIERE_REVISION, payload=payload, key='linked-create')
        self.assertEqual(retry.status_code, 200)
        incompatible = self.create(payload={k: v for k, v in payload.items() if k != 'alta_operation_id'}, key='linked-create')
        self.assertEqual(incompatible.status_code, 409)
        recovery = reverse('solicitud-tecnica-asistida-recuperacion', args=[payload['operation_id']])
        read = self.api.get(recovery, {'command_id': payload['operation_id']})
        self.assertEqual(read.status_code, 200, read.data)
        self.assertEqual(read.data['stage'], 'TECHNICAL_REVIEW')
        self.assertEqual(read.data['alta_operation_id'], str(alta.operation_id))
        self.assertTrue(read.data['command_committed'])
        self.assertEqual(read.data['request']['faltantes'], [{'code': 'DIAGNOSTICO_ACTUALIZADO'}])
        for private in ('NO EXPONER', 'SAFE_RULE', 'linked-create', self.client_user.email):
            self.assertNotIn(private, read.content.decode())
        other = self.create(TechnicalRiskOutcome.NO_APTO)
        other_read = self.api.get(reverse('solicitud-tecnica-asistida-recuperacion', args=[other.data['operation_id']]))
        self.assertEqual(other_read.data['stage'], 'CLOSED')
        self.assertIsNone(other_read.data['alta_operation_id'])

    def test_warning_recovery_acknowledges_only_the_committed_consent(self):
        created = self.create(TechnicalRiskOutcome.ADVERTENCIA)
        recovery = reverse('solicitud-tecnica-asistida-recuperacion', args=[created.data['operation_id']])
        operation_id = uuid4()
        before = self.api.get(recovery, {'command_id': operation_id})
        self.assertEqual(before.data['stage'], 'CONSENT_PENDING')
        self.assertFalse(before.data['command_committed'])
        result = self.consent(created.data['id'], 'ACEPTA', operation_id=operation_id)
        self.assertEqual(result.status_code, 200)
        after = self.api.get(recovery, {'command_id': operation_id})
        self.assertTrue(after.data['command_committed'])
        self.assertEqual(after.data['consent_operation_id'], str(operation_id))
        self.assertEqual(after.data['stage'], 'TECHNICAL_PENDING')

    def test_authorized_operator_creates_multiservice_request_in_order(self):
        second = Servicio.objects.create(nombre='Segundo', activo=True)
        payload = self.payload(servicio_ids=[second.pk, self.service.pk])
        response = self.create(
            payload=payload,
            result=self.result(
                TechnicalRiskOutcome.APTO,
                services=[second, self.service],
            ),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            [item['id'] for item in response.data['servicios']],
            [second.pk, self.service.pk],
        )
        solicitud = SolicitudTecnicaReserva.objects.get(pk=response.data['id'])
        self.assertEqual(solicitud.cliente, self.cliente)
        self.assertEqual(solicitud.operador_registrante, self.operator)
        self.assertEqual(solicitud.medio_solicitud, 'PRESENCIAL')
        self.assertTrue(Auditoria.objects.filter(
            usuario=self.operator,
            valor_nuevo__event=ASSISTED_REQUEST_CREATED,
        ).exists())

    def test_permission_inactive_actor_and_inactive_client_are_rejected(self):
        without_permission = Usuario.objects.create_user(
            email='without-assisted@test.com', password='pass1234'
        )
        self.api.force_authenticate(without_permission)
        denied = self.api.post(
            reverse('solicitud-tecnica-asistida-list'),
            self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY='denied',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.operator.is_active = False
        self.operator.save(update_fields=['is_active'])
        self.api.force_authenticate(self.operator)
        inactive_actor = self.api.post(
            reverse('solicitud-tecnica-asistida-list'),
            self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY='inactive-actor',
        )
        self.assertEqual(inactive_actor.status_code, status.HTTP_403_FORBIDDEN)

        self.operator.is_active = True
        self.operator.save(update_fields=['is_active'])
        self.cliente.activo = False
        self.cliente.save(update_fields=['activo'])
        self.api.force_authenticate(self.operator)
        inactive_client = self.create()
        self.assertEqual(inactive_client.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(inactive_client.data['error']['code'], 'CLIENT_INACTIVE')

        self.cliente.activo = True
        self.cliente.save(update_fields=['activo'])
        missing_client = self.create(payload=self.payload(cliente_id=999999))
        self.assertEqual(missing_client.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            missing_client.data['error']['code'], 'CLIENT_OUT_OF_SCOPE'
        )

    def test_duplicate_inactive_service_and_forbidden_fields_are_invalid(self):
        duplicate = self.create(payload=self.payload(
            servicio_ids=[self.service.pk, self.service.pk]
        ))
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        inactive = Servicio.objects.create(nombre='Inactivo', activo=False)
        inactive_response = self.create(payload=self.payload(
            servicio_ids=[inactive.pk]
        ))
        self.assertEqual(inactive_response.status_code, status.HTTP_400_BAD_REQUEST)
        injected = self.create(payload=self.payload(
            estado='APROBADA_TECNICAMENTE', diagnostico={'x': 1}
        ))
        self.assertEqual(injected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('estado', injected.data['error']['fields'])
        self.assertIn('diagnostico', injected.data['error']['fields'])

    def test_preferred_personal_must_be_compatible_with_every_service(self):
        skill = Habilidad.objects.create(
            code='ASSISTED_REQUIRED', nombre='Requerida', activa=True
        )
        ServicioHabilidad.objects.create(servicio=self.service, habilidad=skill)
        personal = Personal.objects.create(
            nombre='Sin', apellido='Skill', rol='colorista', activo=True
        )
        response = self.create(payload=self.payload(
            personal_preferido_id=personal.pk
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['error']['code'], 'PERSONAL_INCOMPATIBLE'
        )
        PersonalHabilidad.objects.create(
            personal=personal, habilidad=skill, activa=True
        )
        allowed = self.create(payload=self.payload(
            personal_preferido_id=personal.pk
        ))
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)

    def test_four_outcomes_are_projected_without_downstream_artifacts(self):
        expected = {
            TechnicalRiskOutcome.APTO: 'PENDING_SLOT_SELECTION_AND_CONFIRMATION',
            TechnicalRiskOutcome.ADVERTENCIA: 'REGISTER_ASSISTED_CONSENT',
            TechnicalRiskOutcome.REQUIERE_REVISION: 'WAIT_FOR_TECHNICAL_REVIEW',
            TechnicalRiskOutcome.NO_APTO: 'TECHNICALLY_BLOCKED',
        }
        for outcome, action in expected.items():
            with self.subTest(outcome=outcome):
                response = self.create(outcome)
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data['outcome_publico'], outcome)
                self.assertEqual(
                    response.data['siguiente_accion']['code'], action
                )
                self.assertIn('aún no reserva', response.data['aviso_reserva'])
        self.assertEqual(SlotHold.objects.count(), 0)
        self.assertEqual(PaymentIntent.objects.count(), 0)
        self.assertEqual(Pago.objects.count(), 0)
        self.assertEqual(Turno.objects.count(), 0)
        self.assertEqual(DiagnosticoCapilar.objects.count(), 0)

    def test_safe_projection_excludes_internal_technical_evidence(self):
        response = self.create(TechnicalRiskOutcome.REQUIERE_REVISION)
        serialized = str(response.data).lower()
        for forbidden in (
            'input_snapshot', 'result_snapshot', 'detalle interno',
            'notas_internas', 'formula', 'observaciones',
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn('email', serialized)

    def test_request_retry_is_stable_and_policy_change_does_not_reevaluate(self):
        key = 'stable-assisted-request'
        payload = self.payload()
        first = self.create(payload=payload, key=key)
        other_policy = PoliticaRiesgoTecnico.objects.create(
            version='BH063-I2-NEW'
        )
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk'
        ) as evaluator:
            second = self.api.post(
                reverse('solicitud-tecnica-asistida-list'),
                payload,
                format='json',
                HTTP_IDEMPOTENCY_KEY=key,
            )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(second.data['recovered'])
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(first.data['operation_id'], second.data['operation_id'])
        evaluator.assert_not_called()
        self.assertEqual(SolicitudTecnicaReserva.objects.count(), 1)
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.count(), 1
        )
        self.assertTrue(other_policy.pk)

    def test_reused_key_operation_or_actor_conflicts(self):
        key = 'reused-assisted-key'
        payload = self.payload()
        self.assertEqual(self.create(payload=payload, key=key).status_code, 201)
        incompatible = self.create(
            payload={**payload, 'medio_solicitud': 'TELEFONO'}, key=key
        )
        self.assertEqual(incompatible.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            incompatible.data['error']['code'], 'IDEMPOTENCY_KEY_REUSED'
        )

        other = Usuario.objects.create_user(
            email='other-operator@test.com', password='pass1234'
        )
        other.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_turno_for_client',
        ))
        self.api.force_authenticate(other)
        actor_conflict = self.create(payload=payload, key=key)
        self.assertEqual(actor_conflict.status_code, status.HTTP_409_CONFLICT)

        self.api.force_authenticate(self.operator)
        reused_operation = self.create(
            payload={**self.payload(), 'operation_id': payload['operation_id']},
            key='other-key',
        )
        self.assertEqual(reused_operation.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            reused_operation.data['error']['code'], 'OPERATION_ID_REUSED'
        )

    def test_scope_is_limited_to_registering_operator(self):
        request_id = self.create().data['id']
        other = Usuario.objects.create_user(
            email='scoped-operator@test.com', password='pass1234'
        )
        other.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_turno_for_client',
        ))
        self.api.force_authenticate(other)
        for name in (
            'solicitud-tecnica-asistida-detail',
            'solicitud-tecnica-asistida-accion-siguiente',
        ):
            response = self.api.get(reverse(name, args=[request_id]))
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_accept_consent_is_separate_immutable_evidence_and_idempotent(self):
        created = self.create(TechnicalRiskOutcome.ADVERTENCIA)
        request_id = created.data['id']
        operation_id = str(uuid4())
        key = 'accept-assisted-warning'
        accepted = self.consent(
            request_id, 'ACEPTA', key=key, operation_id=operation_id
        )
        repeated = self.consent(
            request_id, 'ACEPTA', key=key, operation_id=operation_id
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertFalse(accepted.data['recovered'])
        self.assertTrue(repeated.data['recovered'])
        self.assertEqual(
            accepted.data['estado'],
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE,
        )
        evidence = ConsentimientoAdvertenciaAsistido.objects.get()
        self.assertEqual(evidence.cliente_informado, self.cliente)
        self.assertEqual(evidence.operador, self.operator)
        self.assertEqual(evidence.warning_codes, ['SAFE_RULE'])
        self.assertEqual(
            evidence.warning_texts, ['Mensaje permitido para el Cliente.']
        )
        self.assertEqual(AceptacionAdvertenciaTecnica.objects.count(), 0)
        self.assertEqual(ConsentimientoAdvertenciaAsistido.objects.count(), 1)
        self.assertTrue(Auditoria.objects.filter(
            usuario=self.operator,
            valor_nuevo__event=ASSISTED_CONSENT_RECORDED,
        ).exists())
        evidence.motivo = 'Intento de cambio'
        with self.assertRaises(ValidationError):
            evidence.save()

    def test_reject_and_not_obtained_do_not_authorize_continuation(self):
        for decision in ('RECHAZA', 'NO_OBTENIDO'):
            with self.subTest(decision=decision):
                created = self.create(TechnicalRiskOutcome.ADVERTENCIA)
                response = self.consent(
                    created.data['id'], decision, reason='Decisión informada'
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    response.data['siguiente_accion']['code'],
                    'CONSENT_NOT_ACCEPTED',
                )
                self.assertFalse(
                    response.data['siguiente_accion'][
                        'can_continue_to_future_hold'
                    ]
                )
        self.assertEqual(SlotHold.objects.count(), 0)

    def test_non_acceptance_requires_reason_and_incompatible_decision_conflicts(self):
        request_id = self.create(TechnicalRiskOutcome.ADVERTENCIA).data['id']
        missing = self.consent(request_id, 'RECHAZA')
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing.data['error']['code'], 'REASON_REQUIRED')
        first = self.consent(request_id, 'RECHAZA', reason='No acepta')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        second = self.consent(request_id, 'ACEPTA')
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            second.data['error']['code'], 'CONSENT_DECISION_CONFLICT'
        )

    def test_superseded_or_non_warning_evaluation_cannot_be_accepted(self):
        apto_id = self.create(TechnicalRiskOutcome.APTO).data['id']
        non_warning = self.consent(apto_id, 'ACEPTA')
        self.assertEqual(non_warning.status_code, status.HTTP_409_CONFLICT)

        warning_id = self.create(TechnicalRiskOutcome.ADVERTENCIA).data['id']
        solicitud = SolicitudTecnicaReserva.objects.get(pk=warning_id)
        evaluation = solicitud.evaluacion_vigente
        replacement = self.create(TechnicalRiskOutcome.APTO).data['id']
        replacement_evaluation = SolicitudTecnicaReserva.objects.get(
            pk=replacement
        ).evaluacion_vigente
        type(evaluation).objects._set_superseded_by(
            evaluation_id=evaluation.pk,
            replacement_id=replacement_evaluation.pk,
        )
        stale = self.consent(warning_id, 'ACEPTA')
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)

    def test_request_and_consent_are_atomic_when_audit_fails(self):
        with patch(
            'gestion.assisted_technical_booking_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit failed'),
        ):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertEqual(SolicitudTecnicaReserva.objects.count(), 0)
        self.assertEqual(SolicitudTecnicaAsistidaOperacion.objects.count(), 0)

        request_id = self.create(TechnicalRiskOutcome.ADVERTENCIA).data['id']
        with patch(
            'gestion.assisted_technical_booking_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit failed'),
        ):
            with self.assertRaises(RuntimeError):
                self.consent(request_id, 'ACEPTA')
        self.assertEqual(ConsentimientoAdvertenciaAsistido.objects.count(), 0)
        solicitud = SolicitudTecnicaReserva.objects.get(pk=request_id)
        self.assertEqual(
            solicitud.estado,
            SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE,
        )

    def test_real_fail_closed_evaluator_does_not_treat_missing_profile_as_apto(self):
        PoliticaRiesgoTecnico.objects.filter(pk=self.policy.pk).update(
            estado=PoliticaRiesgoTecnico.Estado.PUBLICADA,
            publicada_at=timezone.now(),
        )
        response = self.api.post(
            reverse('solicitud-tecnica-asistida-list'),
            self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY='real-fail-closed',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data['outcome_publico'],
            TechnicalRiskOutcome.REQUIERE_REVISION,
        )
        self.assertEqual(DiagnosticoCapilar.objects.count(), 0)

    def test_new_web_request_keeps_owner_contract_and_is_marked_web(self):
        self.api.force_authenticate(self.client_user)
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(TechnicalRiskOutcome.APTO),
        ):
            response = self.api.post(
                reverse('solicitud-tecnica-reservar'),
                {
                    'servicio_ids': [self.service.pk],
                    'fecha_preferida': self.date.isoformat(),
                    'hora_preferida': self.time.isoformat(),
                },
                format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        solicitud = SolicitudTecnicaReserva.objects.get(pk=response.data['id'])
        self.assertEqual(
            solicitud.medio_solicitud,
            SolicitudTecnicaReserva.MedioSolicitud.WEB,
        )
        self.assertEqual(solicitud.operador_registrante, self.client_user)
        other = Usuario.objects.create_user(
            email='foreign-client-assisted@test.com', password='pass1234'
        )
        Cliente.objects.create(usuario=other)
        self.api.force_authenticate(other)
        self.assertEqual(
            self.api.get(reverse(
                'solicitud-tecnica-detail', args=[solicitud.pk]
            )).status_code,
            status.HTTP_404_NOT_FOUND,
        )


class AssistedTechnicalBookingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_turno_for_client',
        )
        self.operator = self._operator('one')
        client_user = Usuario.objects.create_user(
            email='concurrent-client@test.com', password='pass1234'
        )
        self.cliente = Cliente.objects.create(usuario=client_user)
        self.service = Servicio.objects.create(
            nombre='Concurrent service', activo=True
        )
        self.policy = PoliticaRiesgoTecnico.objects.create(
            version='BH063-I2-CONCURRENT'
        )
        self.date = timezone.localdate() + timedelta(days=3)
        self.operation_id = uuid4()

    def _operator(self, suffix):
        actor = Usuario.objects.create_user(
            email=f'concurrent-{suffix}@test.com', password='pass1234'
        )
        actor.user_permissions.add(self.permission)
        return actor

    def result(self):
        return TechnicalRiskEvaluationResult(
            cliente_id=self.cliente.pk,
            politica_id=self.policy.pk,
            policy_version=self.policy.version,
            fecha_solicitada=self.date,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            rule_codes=(),
            missing_data=(),
            relevant_history=(),
            minimum_recommended_date=None,
            client_messages=(),
            professional_messages=(),
            input_snapshot={
                'cliente_id': self.cliente.pk,
                'servicios': [{
                    'id': self.service.pk, 'nombre': self.service.nombre,
                }],
                'fecha_solicitada': self.date.isoformat(),
                'policy_version': self.policy.version,
                'datos_faltantes': [],
            },
            result_snapshot={
                'outcome': TechnicalRiskOutcome.APTO,
                'severity': 0,
                'policy_version': self.policy.version,
                'rule_codes': [],
                'reglas_disparadas': [],
                'mensajes_cliente': [],
                'mensajes_profesional': [],
            },
        )

    def _run(self, actor, barrier):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return create_assisted_technical_request(
                actor=actor,
                idempotency_key='concurrent-assisted-key',
                operation_id=self.operation_id,
                cliente_id=self.cliente.pk,
                servicios=[self.service],
                fecha_preferida=self.date,
                hora_preferida=time(11, 0),
                medio_solicitud='TELEFONO',
            )
        except Exception as exc:  # Se inspecciona explícitamente en cada prueba.
            return exc
        finally:
            close_old_connections()

    def test_same_operator_concurrent_retry_creates_one_request_and_ledger(self):
        barrier = Barrier(2)
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(
                    lambda _index: self._run(self.operator, barrier),
                    range(2),
                ))
        self.assertFalse(any(isinstance(item, Exception) for item in results))
        self.assertEqual(sorted(item.recovered for item in results), [False, True])
        self.assertEqual(SolicitudTecnicaReserva.objects.count(), 1)
        self.assertEqual(SolicitudTecnicaAsistidaOperacion.objects.count(), 1)
        self.assertEqual(Auditoria.objects.filter(
            valor_nuevo__event=ASSISTED_REQUEST_CREATED,
        ).count(), 1)

    def test_two_operators_concurrently_cannot_share_operation_identity(self):
        other = self._operator('two')
        barrier = Barrier(2)
        with patch(
            'gestion.technical_booking_request_services.evaluate_booking_risk',
            return_value=self.result(),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(self._run, actor, barrier)
                    for actor in (self.operator, other)
                ]
                results = [future.result(timeout=20) for future in futures]
        successes = [item for item in results if not isinstance(item, Exception)]
        conflicts = [
            item for item in results
            if isinstance(item, AssistedTechnicalBookingConflict)
        ]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].code, 'IDEMPOTENCY_KEY_REUSED')
        self.assertEqual(SolicitudTecnicaReserva.objects.count(), 1)
        self.assertEqual(SolicitudTecnicaAsistidaOperacion.objects.count(), 1)
