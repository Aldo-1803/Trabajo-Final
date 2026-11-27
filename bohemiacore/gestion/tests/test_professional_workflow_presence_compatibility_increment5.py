from datetime import time, timedelta

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    CambioPerfilCapilar,
    DetalleTurno,
    DiagnosticoCapilar,
    EfectoFinalizacion,
    FamiliaProcesoTecnico,
    FichaTecnica,
    FinalizacionTurno,
    GrosorCabello,
    Habilidad,
    HorarioLaboral,
    Personal,
    PersonalHabilidad,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    ReglaDiagnosticoTecnico,
    Servicio,
    SlotHold,
    TechnicalRiskOutcome,
    TipoCabello,
    Turno,
)
from gestion.technical_risk_evaluator import evaluate_booking_risk
from usuarios.models import Cliente, Usuario


class ProfessionalWorkflowPresenceCompatibilityIncrement5Tests(APITestCase):
    """Compatibilidad real; no representa BH-063/BH-064 como implementados."""

    def setUp(self):
        self.manage_record = self.gestion_permission('manage_technical_record')
        self.create_diagnosis = self.gestion_permission('create_diagnosis')
        self.finalize_service = self.gestion_permission('finalize_service')
        self.create_turno_permission = self.gestion_permission(
            'create_turno_for_client'
        )
        self.create_walkin = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='create_walkin_client',
        )
        self.skill = Habilidad.objects.get(code='DIAGNOSTICO')
        self.actor, self.personal = self.create_professional(
            'increment5-assigned@test.com'
        )
        self.other_actor, self.other_personal = self.create_professional(
            'increment5-foreign@test.com'
        )
        self.client_user, self.client_profile = self.create_client(
            'increment5-client@test.com'
        )
        self.other_client_user, self.other_client = self.create_client(
            'increment5-other-client@test.com'
        )
        self.hair_type = TipoCabello.objects.create(nombre='Ondulado presencial')
        self.hair_thickness = GrosorCabello.objects.create(nombre='Fino presencial')
        self.family = FamiliaProcesoTecnico.objects.create(
            code='PRESENCE_COMPATIBILITY',
            nombre='Compatibilidad presencial',
        )
        self.service = self.create_service(
            'Servicio sin diagnóstico obligatorio',
            record_required=False,
        )
        self.required_record_service = self.create_service(
            'Servicio con ficha obligatoria',
            record_required=True,
        )
        self.turno = self.create_turno()
        self.detail = self.add_detail(self.turno, self.service)
        self.client.force_authenticate(self.actor)

    @staticmethod
    def gestion_permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='PresenceCompatibility!2026',
            first_name='Nombre',
            last_name='Seguro',
            **extra_fields,
        )

    def create_client(self, email):
        user = self.create_user(email)
        return user, Cliente.objects.create(usuario=user, activo=True)

    def create_professional(self, email):
        user = self.create_user(email)
        user.user_permissions.add(
            self.manage_record,
            self.create_diagnosis,
            self.finalize_service,
        )
        personal = Personal.objects.create(
            usuario=user,
            nombre='Profesional',
            apellido=email.split('@')[0],
            rol='colorista',
            activo=True,
        )
        PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=self.skill,
            activa=True,
        )
        return user, personal

    def create_service(self, name, *, record_required):
        service = Servicio.objects.create(
            nombre=name,
            precio_base='2500.00',
            duracion_estimada=60,
            activo=True,
        )
        PerfilTecnicoServicio.objects.create(
            servicio=service,
            familia=self.family,
            estado_clasificacion=(
                PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
            ),
            nivel_riesgo=PerfilTecnicoServicio.NivelRiesgo.BAJO,
            requisito_ficha=(
                PerfilTecnicoServicio.RequisitoFicha.REQUERIDA
                if record_required
                else PerfilTecnicoServicio.RequisitoFicha.NO_REQUERIDA
            ),
            modo_formula_ficha=(
                PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA
            ),
            campos_requeridos_ficha=(
                ['observaciones_proceso'] if record_required else []
            ),
        )
        return service

    def create_turno(
        self,
        *,
        client=None,
        personal=None,
        state=Turno.Estado.CONFIRMADO,
        minute=0,
        channel=Turno.CanalOrigen.PRESENCIAL,
    ):
        return Turno.objects.create(
            cliente=client or self.client_profile,
            profesional=personal or self.personal,
            fecha=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(10, minute),
            estado=state,
            canal_origen=channel,
        )

    @staticmethod
    def add_detail(turno, service):
        return DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico=service.precio_base,
            duracion_minutos=service.duracion_estimada,
        )

    @staticmethod
    def context_url(turno):
        return reverse('ficha-tecnica-contexto-turno') + f'?turno_id={turno.pk}'

    @staticmethod
    def finalization_url(turno):
        return reverse('turno-finalizar-turno', args=[turno.pk])

    def context(self, turno=None):
        return self.client.get(self.context_url(turno or self.turno))

    def create_diagnosis_rule(self, service):
        policy = PoliticaRiesgoTecnico.objects.create(
            version=f'PRESENCE-{service.pk}'
        )
        ReglaDiagnosticoTecnico.objects.create(
            politica=policy,
            code='VALID_PROFESSIONAL_DIAGNOSIS_REQUIRED',
            servicio_destino=service,
            requiere_diagnostico=True,
            antiguedad_maxima_dias=30,
            outcome_si_falta=TechnicalRiskOutcome.NO_APTO,
            outcome_si_vencido=TechnicalRiskOutcome.REQUIERE_REVISION,
            outcome_si_incompleto=TechnicalRiskOutcome.REQUIERE_REVISION,
            outcome_si_procedencia_no_confiable=(
                TechnicalRiskOutcome.REQUIERE_REVISION
            ),
            mensaje_profesional=(
                'El Servicio requiere una evaluación profesional vigente.'
            ),
        )
        PoliticaRiesgoTecnico.objects.filter(pk=policy.pk).update(
            estado=PoliticaRiesgoTecnico.Estado.PUBLICADA,
            publicada_at=timezone.now(),
        )
        policy.refresh_from_db()
        return policy

    def test_01_existing_client_with_professional_diagnosis_is_projected(self):
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=self.actor,
            autor=self.actor,
            procedencia=DiagnosticoCapilar.Procedencia.PROFESIONAL,
            tipo_cabello=self.hair_type,
        )
        self_report = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            procedencia=DiagnosticoCapilar.Procedencia.AUTORREPORTE,
            grosor_cabello=self.hair_thickness,
        )

        response = self.context()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        evaluations = {
            item['id']: item for item in response.data['evaluaciones']
        }
        self.assertEqual(
            evaluations[diagnosis.pk]['procedencia'],
            DiagnosticoCapilar.Procedencia.PROFESIONAL,
        )
        self.assertEqual(
            evaluations[self_report.pk]['procedencia'],
            DiagnosticoCapilar.Procedencia.AUTORREPORTE,
        )

    def test_02_existing_client_without_diagnosis_loads_pending_profile(self):
        response = self.context()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['evaluaciones'], [])
        self.assertTrue(all(
            value['id'] is None
            and value['procedencia'] == DiagnosticoCapilar.Procedencia.DESCONOCIDO
            for value in response.data['perfil_capilar'].values()
        ))
        self.assertFalse(DiagnosticoCapilar.objects.exists())

    def test_03_partial_profile_promotes_only_professionally_evaluated_field(self):
        self.client_profile.grosor_cabello = self.hair_thickness
        self.client_profile.save(update_fields=['grosor_cabello'])

        created = self.client.post(
            reverse('diagnostico-capilar-list'),
            {
                'cliente': self.client_profile.pk,
                'tipo_cabello': self.hair_type.pk,
            },
            format='json',
        )
        response = self.context()

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        profile = response.data['perfil_capilar']
        self.assertEqual(profile['tipo_cabello']['id'], self.hair_type.pk)
        self.assertEqual(
            profile['tipo_cabello']['procedencia'],
            DiagnosticoCapilar.Procedencia.PROFESIONAL,
        )
        self.assertEqual(profile['grosor_cabello']['id'], self.hair_thickness.pk)
        self.assertEqual(
            profile['grosor_cabello']['procedencia'],
            DiagnosticoCapilar.Procedencia.DESCONOCIDO,
        )

    def test_04_profile_without_traceable_source_is_explicitly_unknown(self):
        self.client_profile.tipo_cabello = self.hair_type
        self.client_profile.save(update_fields=['tipo_cabello'])

        response = self.context()

        self.assertEqual(
            response.data['perfil_capilar']['tipo_cabello']['procedencia'],
            DiagnosticoCapilar.Procedencia.DESCONOCIDO,
        )
        self.assertIsNone(
            response.data['perfil_capilar']['tipo_cabello'][
                'diagnostico_fuente_id'
            ]
        )

    def test_05_confirmed_turn_without_diagnosis_keeps_authorized_actions(self):
        response = self.context()

        self.assertEqual(response.data['turno_estado'], Turno.Estado.CONFIRMADO)
        self.assertTrue(response.data['access']['can_create_evaluation'])
        self.assertTrue(response.data['access']['can_manage_technical_records'])
        self.assertTrue(response.data['preflight']['ready'])

    def test_06_service_diagnosis_rule_explains_missing_evaluation(self):
        policy = self.create_diagnosis_rule(self.service)

        result = evaluate_booking_risk(
            cliente=self.client_profile,
            servicios=[self.service],
            fecha_solicitada=self.turno.fecha,
            policy_version=policy.version,
        )

        self.assertEqual(result.outcome, TechnicalRiskOutcome.NO_APTO)
        self.assertEqual(
            result.result_snapshot['reglas_disparadas'][0]['kind'],
            'DIAGNOSIS_MISSING',
        )
        self.assertIn('evaluación profesional', result.professional_messages[0])
        self.assertFalse(DiagnosticoCapilar.objects.exists())

    def test_07_service_without_diagnosis_rule_does_not_invent_requirement(self):
        policy = PoliticaRiesgoTecnico.objects.create(version='PRESENCE-NO-RULE')
        PoliticaRiesgoTecnico.objects.filter(pk=policy.pk).update(
            estado=PoliticaRiesgoTecnico.Estado.PUBLICADA,
            publicada_at=timezone.now(),
        )

        result = evaluate_booking_risk(
            cliente=self.client_profile,
            servicios=[self.service],
            fecha_solicitada=self.turno.fecha,
            policy_version=policy.version,
        )

        self.assertEqual(result.outcome, TechnicalRiskOutcome.APTO)
        self.assertEqual(result.rule_codes, ())
        self.assertFalse(DiagnosticoCapilar.objects.exists())

    def test_08_technical_records_remain_independent_per_turn_detail(self):
        second_detail = self.add_detail(self.turno, self.required_record_service)
        list_url = reverse('ficha-tecnica-list')

        first = self.client.post(
            list_url,
            {'detalle_turno': self.detail.pk, 'comentario_cliente': 'Primera'},
            format='json',
        )
        second = self.client.post(
            list_url,
            {
                'detalle_turno': second_detail.pk,
                'observaciones_proceso': 'Segunda',
            },
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertSetEqual(
            set(FichaTecnica.objects.values_list('detalle_turno_id', flat=True)),
            {self.detail.pk, second_detail.pk},
        )

    def test_09_finalization_is_allowed_without_universal_diagnosis(self):
        first = self.client.post(
            self.finalization_url(self.turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='presence-no-diagnosis',
        )
        retry = self.client.post(
            self.finalization_url(self.turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='presence-no-diagnosis',
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data['changed'])
        self.assertFalse(retry.data['changed'])
        self.assertEqual(
            FinalizacionTurno.objects.filter(turno=self.turno).count(),
            1,
        )

    def test_10_required_record_blocks_finalization_without_partial_effects(self):
        required_turno = self.create_turno(minute=1)
        self.add_detail(required_turno, self.required_record_service)

        response = self.client.post(
            self.finalization_url(required_turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='presence-required-record',
        )
        required_turno.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['code'],
            'REQUIRED_TECHNICAL_RECORD_INCOMPLETE',
        )
        self.assertEqual(required_turno.estado, Turno.Estado.CONFIRMADO)
        self.assertFalse(
            FinalizacionTurno.objects.filter(turno=required_turno).exists()
        )
        self.assertFalse(EfectoFinalizacion.objects.exists())

    def test_11_assigned_personal_receives_effective_work_authority(self):
        response = self.context()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['access']['can_read_technical_context'])
        self.assertTrue(response.data['access']['can_manage_technical_records'])
        self.assertTrue(response.data['access']['can_finalize'])

    def test_12_foreign_personal_cannot_read_or_finalize_turn(self):
        self.client.force_authenticate(self.other_actor)

        context = self.context()
        finalization = self.client.post(
            self.finalization_url(self.turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='presence-foreign',
        )

        self.assertEqual(context.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(finalization.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn('cliente', context.data)
        self.assertFalse(FinalizacionTurno.objects.exists())

    def test_13_revoked_technical_capability_prevents_context_and_mutation(self):
        self.actor.user_permissions.remove(self.manage_record)
        self.actor = Usuario.objects.get(pk=self.actor.pk)
        self.client.force_authenticate(self.actor)

        context = self.context()
        mutation = self.client.post(
            reverse('ficha-tecnica-list'),
            {'detalle_turno': self.detail.pk, 'comentario_cliente': 'No guardar'},
            format='json',
        )

        self.assertEqual(context.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(mutation.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(FichaTecnica.objects.exists())

    def test_14_turn_projects_only_its_corresponding_client_profile(self):
        DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=self.actor,
            procedencia=DiagnosticoCapilar.Procedencia.PROFESIONAL,
            tipo_cabello=self.hair_type,
        )
        other_turno = self.create_turno(client=self.other_client, minute=2)
        self.add_detail(other_turno, self.service)

        response = self.context(other_turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['cliente']['id'], self.other_client.pk)
        self.assertEqual(response.data['evaluaciones'], [])
        self.assertIsNone(
            response.data['perfil_capilar']['tipo_cabello']['id']
        )

    def test_15_context_omits_sensitive_and_unnecessary_internal_data(self):
        self.service.plantilla_formula = 'FÓRMULA INTERNA NO AUTORIZADA'
        self.service.save(update_fields=['plantilla_formula'])
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=self.actor,
            autor=self.actor,
            procedencia=DiagnosticoCapilar.Procedencia.PROFESIONAL,
            tipo_cabello=self.hair_type,
        )

        response = self.context()
        serialized = str(response.data)
        evaluation = next(
            item for item in response.data['evaluaciones']
            if item['id'] == diagnosis.pk
        )

        self.assertNotIn('FÓRMULA INTERNA NO AUTORIZADA', serialized)
        self.assertNotIn('parametros_snapshot', serialized)
        self.assertNotIn('password', serialized.lower())
        self.assertNotIn('cliente_email', evaluation)
        self.assertNotIn('regla_diagnostico', evaluation)
        self.assertNotIn('autor', evaluation)

    def test_16_finalization_does_not_create_fictitious_hair_records(self):
        response = self.client.post(
            self.finalization_url(self.turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='presence-no-fiction',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(DiagnosticoCapilar.objects.exists())
        self.assertFalse(CambioPerfilCapilar.objects.exists())
        diagnosis_effect = EfectoFinalizacion.objects.get(
            tipo=EfectoFinalizacion.Tipo.DIAGNOSTICO_AUTOMATICO
        )
        self.assertEqual(
            diagnosis_effect.estado,
            EfectoFinalizacion.Estado.OMITIDO,
        )

    def test_17_stale_record_version_preserves_last_committed_value(self):
        created = self.client.post(
            reverse('ficha-tecnica-list'),
            {'detalle_turno': self.detail.pk, 'comentario_cliente': 'Versión uno'},
            format='json',
        )
        record = FichaTecnica.objects.get(pk=created.data['id'])
        url = reverse('ficha-tecnica-guardar-borrador', args=[record.pk])
        first = self.client.post(
            url,
            {'version': 1, 'comentario_cliente': 'Versión dos'},
            format='json',
        )
        stale = self.client.post(
            url,
            {'version': 1, 'comentario_cliente': 'Sobrescritura'},
            format='json',
        )
        record.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale.data['code'], 'TECHNICAL_RECORD_VERSION_CONFLICT')
        self.assertEqual(record.comentario_cliente, 'Versión dos')
        self.assertEqual(record.version, 2)

    def test_18_current_web_and_assisted_foundations_keep_channel_boundaries(self):
        self.actor.user_permissions.add(
            self.create_walkin,
            self.create_turno_permission,
        )
        self.actor = Usuario.objects.get(pk=self.actor.pk)
        self.client.force_authenticate(self.actor)
        created_client = self.client.post(
            reverse('admin-client-account-create'),
            {
                'first_name': 'Cliente',
                'last_name': 'Presencial',
                'email': 'increment5-walkin@test.com',
                'password_temporal': 'Temporal!Presence2026',
                'motivo': 'Alta presencial compatible',
            },
            format='json',
        )
        assisted_date = timezone.localdate() + timedelta(days=2)
        HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=assisted_date.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
            permite_complemento=True,
            permite_diseno_color=True,
        )
        assisted = self.client.post(
            reverse('turno-crear-para-cliente'),
            {
                'cliente_id': created_client.data['cliente_id'],
                'servicio': self.service.pk,
                'profesional': self.personal.pk,
                'fecha': assisted_date.isoformat(),
                'hora_inicio': '10:00',
            },
            format='json',
        )
        assisted_turno = Turno.objects.get(pk=assisted.data['turno']['id'])
        assisted_context = self.client.get(self.context_url(assisted_turno))

        self.client.force_authenticate(self.client_user)
        web = self.client.post(
            reverse('turno-reservar'),
            {
                'servicio': self.service.pk,
                'profesional': self.personal.pk,
                'fecha': assisted_date.isoformat(),
                'hora_inicio': '12:00',
            },
            format='json',
        )

        self.assertEqual(created_client.status_code, status.HTTP_201_CREATED)
        new_client = Cliente.objects.get(pk=created_client.data['cliente_id'])
        self.assertFalse(
            DiagnosticoCapilar.objects.filter(cliente=new_client).exists()
        )
        self.assertEqual(assisted.status_code, status.HTTP_201_CREATED)
        self.assertEqual(assisted_turno.estado, Turno.Estado.SOLICITADO)
        self.assertEqual(
            assisted_turno.canal_origen,
            Turno.CanalOrigen.PRESENCIAL,
        )
        self.assertEqual(assisted_context.status_code, status.HTTP_200_OK)
        self.assertFalse(
            assisted_context.data['access']['can_manage_technical_records']
        )
        self.assertEqual(
            assisted_context.data['preflight']['blockers'][0]['code'],
            'INVALID_FINALIZATION_TRANSITION',
        )
        self.assertEqual(assisted_turno.monto_abonado, 0)
        self.assertFalse(assisted_turno.comprobante_pago.name)
        self.assertEqual(web.status_code, status.HTTP_201_CREATED)
        web_turno = Turno.objects.get(pk=web.data['turno']['id'])
        self.assertEqual(web_turno.estado, Turno.Estado.SOLICITADO)
        self.assertEqual(web_turno.canal_origen, Turno.CanalOrigen.WEB)
        self.assertFalse(SlotHold.objects.exists())
