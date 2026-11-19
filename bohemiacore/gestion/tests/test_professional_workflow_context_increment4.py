from datetime import time, timedelta

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    CorreccionFichaTecnica,
    DetalleTurno,
    DiagnosticoCapilar,
    EstadoGeneral,
    FichaTecnica,
    Habilidad,
    Personal,
    PersonalHabilidad,
    PerfilTecnicoServicio,
    Servicio,
    TipoCabello,
    Turno,
)
from usuarios.models import Cliente, Usuario


class ProfessionalWorkflowContextIncrement4Tests(APITestCase):
    def setUp(self):
        self.manage_record = self.permission('manage_technical_record')
        self.create_diagnosis = self.permission('create_diagnosis')
        self.manage_formulas = self.permission('manage_formulas')
        self.finalize_service = self.permission('finalize_service')
        self.skill = Habilidad.objects.get(code='DIAGNOSTICO')
        self.actor, self.personal = self.create_professional(
            'increment4-professional@test.com',
            permissions=(
                self.manage_record,
                self.create_diagnosis,
                self.finalize_service,
            ),
        )
        self.client_user = Usuario.objects.create_user(
            email='increment4-client@test.com'
        )
        self.hair_type = TipoCabello.objects.create(nombre='Ondulado trazable')
        self.hair_state = EstadoGeneral.objects.create(nombre='Estado observado')
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            tipo_cabello=self.hair_type,
            activo=True,
        )
        self.service = Servicio.objects.create(
            nombre='Servicio técnico incremento 4',
            precio_base='1500.00',
            duracion_estimada=60,
            plantilla_formula='FÓRMULA ESTÁNDAR SENSIBLE',
        )
        PerfilTecnicoServicio.objects.create(
            servicio=self.service,
            requisito_ficha=PerfilTecnicoServicio.RequisitoFicha.REQUERIDA,
            modo_formula_ficha=(
                PerfilTecnicoServicio.ModoFormulaFicha.OPCIONAL
            ),
            campos_requeridos_ficha=['observaciones_proceso'],
        )
        self.turno = self.create_turno()
        self.detail = DetalleTurno.objects.create(
            turno=self.turno,
            servicio=self.service,
            precio_historico='1500.00',
            duracion_minutos=60,
        )
        self.client.force_authenticate(self.actor)

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    def create_professional(self, email, *, permissions=()):
        user = Usuario.objects.create_user(email=email)
        user.user_permissions.add(*permissions)
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

    def create_turno(self, *, personal=None, client=None, minute=0):
        return Turno.objects.create(
            cliente=client or self.client_profile,
            profesional=personal or self.personal,
            fecha=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(10, minute),
            estado=Turno.Estado.CONFIRMADO,
        )

    @staticmethod
    def context_url(turno):
        return reverse('ficha-tecnica-contexto-turno') + f'?turno_id={turno.pk}'

    def get_context(self, turno=None):
        return self.client.get(self.context_url(turno or self.turno))

    def test_assigned_context_projects_profile_services_access_and_preflight(self):
        response = self.get_context()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['turno']['id'], self.turno.pk)
        self.assertEqual(response.data['cliente']['id'], self.client_profile.pk)
        self.assertEqual(
            response.data['perfil_capilar']['tipo_cabello']['nombre'],
            self.hair_type.nombre,
        )
        self.assertEqual(
            response.data['perfil_capilar']['tipo_cabello']['procedencia'],
            DiagnosticoCapilar.Procedencia.DESCONOCIDO,
        )
        self.assertTrue(response.data['access']['can_create_evaluation'])
        self.assertTrue(response.data['access']['can_manage_technical_records'])
        self.assertTrue(response.data['access']['can_finalize'])
        self.assertFalse(response.data['preflight']['ready'])
        self.assertEqual(
            response.data['preflight']['blockers'][0]['code'],
            'REQUIRED_TECHNICAL_RECORD_INCOMPLETE',
        )

    def test_foreign_turn_is_denied_without_projecting_client_data(self):
        other_actor, other_personal = self.create_professional(
            'increment4-other@test.com',
            permissions=(self.manage_record,),
        )
        foreign = self.create_turno(personal=other_personal, minute=1)
        self.client.force_authenticate(self.actor)

        response = self.get_context(foreign)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn('cliente', response.data)
        self.assertNotIn('perfil_capilar', response.data)
        self.assertIsNotNone(other_actor.pk)

    def test_capability_absent_or_revoked_denies_context(self):
        without_capability, personal = self.create_professional(
            'increment4-no-capability@test.com'
        )
        own_turn = self.create_turno(personal=personal, minute=2)
        self.client.force_authenticate(without_capability)
        absent = self.get_context(own_turn)

        self.client.force_authenticate(self.actor)
        self.assertEqual(self.get_context().status_code, status.HTTP_200_OK)
        self.actor.user_permissions.remove(self.manage_record)
        self.actor = Usuario.objects.get(pk=self.actor.pk)
        self.client.force_authenticate(self.actor)
        revoked = self.get_context()

        self.assertEqual(absent.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(revoked.status_code, status.HTTP_403_FORBIDDEN)

    def test_partial_profile_and_professional_evaluation_history_are_explicit(self):
        self.client_profile.tipo_cabello = None
        self.client_profile.save(update_fields=['tipo_cabello'])
        created = self.client.post(
            reverse('diagnostico-capilar-list'),
            {
                'cliente': self.client_profile.pk,
                'estado_general': self.hair_state.pk,
                'observaciones': 'Observación profesional verificable.',
            },
            format='json',
        )

        response = self.get_context()

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(
            response.data['perfil_capilar']['tipo_cabello']['id']
        )
        self.assertEqual(len(response.data['evaluaciones']), 1)
        evaluation = response.data['evaluaciones'][0]
        self.assertEqual(evaluation['procedencia'], 'PROFESIONAL')
        self.assertEqual(
            evaluation['observaciones'],
            'Observación profesional verificable.',
        )
        self.assertEqual(evaluation['estado_resultado'], 'CALCULADO')
        self.assertNotIn('cliente_email', evaluation)
        self.assertNotIn('regla_diagnostico', evaluation)
        self.assertNotIn('autor', evaluation)

    def test_evaluation_correction_history_is_preserved(self):
        created = self.client.post(
            reverse('diagnostico-capilar-list'),
            {
                'cliente': self.client_profile.pk,
                'tipo_cabello': self.hair_type.pk,
            },
            format='json',
        )
        corrected_type = TipoCabello.objects.create(nombre='Tipo corregido UI')
        corrected = self.client.post(
            reverse('diagnostico-capilar-corregir', args=[created.data['id']]),
            {
                'motivo': 'Corrección profesional suficientemente explicada.',
                'tipo_cabello': corrected_type.pk,
            },
            format='json',
        )

        response = self.get_context()

        self.assertEqual(corrected.status_code, status.HTTP_200_OK)
        evaluation = response.data['evaluaciones'][0]
        self.assertEqual(evaluation['tipo_cabello'], corrected_type.pk)
        self.assertEqual(len(evaluation['correcciones']), 1)
        self.assertEqual(
            evaluation['correcciones'][0]['motivo'],
            'Corrección profesional suficientemente explicada.',
        )

    def test_formula_and_formula_corrections_require_effective_capability(self):
        record = FichaTecnica.objects.create(
            detalle_turno=self.detail,
            profesional_autor=self.actor,
            formula_estandar_referencia='FÓRMULA ESTÁNDAR SENSIBLE',
            formula='FÓRMULA APLICADA SENSIBLE',
            observaciones_proceso='Proceso completo',
            estado=FichaTecnica.Estado.COMPLETA,
            version=2,
            completada_por=self.actor,
            completada_en=timezone.now(),
        )
        CorreccionFichaTecnica.objects.create(
            ficha=record,
            actor=self.actor,
            motivo='Corrección de fórmula documentada',
            version_anterior=1,
            version_nueva=2,
            campos=['formula', 'observaciones_proceso'],
            valores_anteriores={
                'formula': 'SECRETO ANTERIOR',
                'observaciones_proceso': 'Anterior',
            },
            valores_nuevos={
                'formula': 'SECRETO NUEVO',
                'observaciones_proceso': 'Proceso completo',
            },
        )

        hidden = self.get_context()
        hidden_item = hidden.data['detalles'][0]
        self.assertNotIn('formula', hidden_item['ficha'])
        self.assertNotIn('formula_estandar_catalogo', hidden_item)
        self.assertNotIn('formula', hidden_item['correcciones'][0]['campos'])
        self.assertNotIn(
            'formula',
            hidden_item['correcciones'][0]['valores_nuevos'],
        )

        self.actor.user_permissions.add(self.manage_formulas)
        self.actor = Usuario.objects.get(pk=self.actor.pk)
        self.client.force_authenticate(self.actor)
        visible = self.get_context()
        visible_item = visible.data['detalles'][0]
        self.assertEqual(
            visible_item['ficha']['formula'],
            'FÓRMULA APLICADA SENSIBLE',
        )
        self.assertEqual(
            visible_item['formula_estandar_catalogo'],
            'FÓRMULA ESTÁNDAR SENSIBLE',
        )

    def test_complete_record_makes_preflight_ready(self):
        FichaTecnica.objects.create(
            detalle_turno=self.detail,
            profesional_autor=self.actor,
            observaciones_proceso='Proceso verificable',
            estado=FichaTecnica.Estado.COMPLETA,
            version=2,
            completada_por=self.actor,
            completada_en=timezone.now(),
        )

        response = self.get_context()

        self.assertTrue(response.data['preflight']['ready'])
        self.assertEqual(response.data['preflight']['blockers'], [])
        self.assertTrue(
            response.data['preflight']['technical_records'][0]['complete']
        )

    def test_pending_policy_is_warning_not_invented_blocker(self):
        PerfilTecnicoServicio.objects.filter(servicio=self.service).delete()

        response = self.get_context()

        self.assertTrue(response.data['preflight']['ready'])
        self.assertEqual(response.data['preflight']['blockers'], [])
        self.assertEqual(
            response.data['preflight']['warnings'][0]['code'],
            'SERVICE_TECHNICAL_PROFILE_MISSING',
        )

    def test_persisted_finalization_exposes_only_authorized_summary(self):
        PerfilTecnicoServicio.objects.filter(servicio=self.service).update(
            requisito_ficha=PerfilTecnicoServicio.RequisitoFicha.NO_REQUERIDA,
            modo_formula_ficha=(
                PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA
            ),
            campos_requeridos_ficha=[],
        )
        finalized = self.client.post(
            reverse('turno-finalizar-turno', args=[self.turno.pk]),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='increment4-context-result',
        )

        response = self.get_context()

        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['preflight']['already_finalized'])
        result = response.data['finalizacion']
        self.assertTrue(result['persisted'])
        self.assertEqual(result['estado_actual'], Turno.Estado.REALIZADO)
        self.assertIn('summary', result['effects'])
        serialized = str(result)
        self.assertNotIn('parametros_snapshot', serialized)
        self.assertNotIn('FÓRMULA ESTÁNDAR SENSIBLE', serialized)

    def test_context_get_is_read_only(self):
        before = {
            'diagnoses': DiagnosticoCapilar.objects.count(),
            'records': FichaTecnica.objects.count(),
            'state': self.turno.estado,
        }

        first = self.get_context()
        second = self.get_context()
        self.turno.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(before, {
            'diagnoses': DiagnosticoCapilar.objects.count(),
            'records': FichaTecnica.objects.count(),
            'state': self.turno.estado,
        })
