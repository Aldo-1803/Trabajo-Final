from concurrent.futures import ThreadPoolExecutor
from datetime import time
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from gestion.hair_profile_services import create_professional_evaluation
from gestion.models import (
    CambioPerfilCapilar,
    CategoriaServicio,
    ConfiguracionDiagnostico,
    CorreccionDiagnosticoCapilar,
    DetalleTurno,
    DiagnosticoCapilar,
    EstadoGeneral,
    GrosorCabello,
    Habilidad,
    Notificacion,
    Personal,
    PersonalHabilidad,
    Rutina,
    RutinaCliente,
    Servicio,
    TipoCabello,
    Turno,
    VigenciaCampoPerfilCapilar,
)
from usuarios.models import Cliente, Usuario


class HairProfileEvaluationApiTests(APITestCase):
    def setUp(self):
        self.create_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_diagnosis',
        )
        self.manage_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_technical_record',
        )
        self.finalize_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='finalize_service',
        )
        self.skill = Habilidad.objects.get(code='DIAGNOSTICO')
        self.type_initial = TipoCabello.objects.create(nombre='Tipo inicial')
        self.type_new = TipoCabello.objects.create(nombre='Tipo nuevo')
        self.type_corrected = TipoCabello.objects.create(nombre='Tipo corregido')
        self.thickness = GrosorCabello.objects.create(nombre='Grosor preservado')
        self.state = EstadoGeneral.objects.create(nombre='Estado observado')
        self.client_user = self.create_user('profile-client@test.com')
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            tipo_cabello=self.type_initial,
            grosor_cabello=self.thickness,
            activo=True,
        )
        self.actor, self.personal = self.create_professional(
            'profile-professional@test.com'
        )
        self.list_url = reverse('diagnostico-capilar-list')
        self.profile_url = reverse('perfil')

    @staticmethod
    def create_user(email, *, active=True):
        return Usuario.objects.create_user(
            email=email,
            password='HairProfileTests!2026',
            is_active=active,
        )

    def create_professional(
        self,
        email,
        *,
        permission=True,
        skill=True,
        active=True,
    ):
        user = self.create_user(email)
        if permission:
            user.user_permissions.add(self.create_permission)
        personal = Personal.objects.create(
            usuario=user,
            nombre='Profesional',
            apellido=email.split('@')[0],
            rol='asistente',
            activo=active,
        )
        if skill:
            PersonalHabilidad.objects.create(
                personal=personal,
                habilidad=self.skill,
                activa=True,
            )
        return user, personal

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def create_evaluation(self, **payload):
        self.authenticate(self.actor)
        return self.client.post(
            self.list_url,
            {'cliente': self.client_profile.pk, **payload},
            format='json',
        )

    @staticmethod
    def correction_url(diagnosis):
        return reverse('diagnostico-capilar-corregir', args=[diagnosis.pk])

    def test_profile_get_returns_coherent_ids_names_and_unknown_legacy_source(self):
        self.authenticate(self.client_user)

        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tipo_cabello'], self.type_initial.nombre)
        self.assertEqual(response.data['tipo_cabello_id'], self.type_initial.pk)
        self.assertEqual(response.data['grosor_cabello'], self.thickness.nombre)
        self.assertEqual(response.data['grosor_cabello_id'], self.thickness.pk)
        current = response.data['perfil_capilar']['tipo_cabello']
        self.assertEqual(current['id'], self.type_initial.pk)
        self.assertEqual(current['nombre'], self.type_initial.nombre)
        self.assertEqual(current['procedencia'], 'DESCONOCIDO')
        self.assertIsNone(current['diagnostico_fuente_id'])

    def test_client_without_diagnosis_can_read_partial_profile(self):
        self.client_profile.tipo_cabello = None
        self.client_profile.save(update_fields=['tipo_cabello'])
        self.authenticate(self.client_user)

        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['tipo_cabello_id'])
        self.assertEqual(response.data['grosor_cabello_id'], self.thickness.pk)
        self.assertFalse(DiagnosticoCapilar.objects.exists())

    def test_partial_client_self_report_preserves_other_fields_and_adds_history(self):
        self.authenticate(self.client_user)

        response = self.client.put(
            self.profile_url,
            {'tipo_cabello': self.type_new.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tipo_cabello_id'], self.type_new.pk)
        self.assertEqual(response.data['tipo_cabello'], self.type_new.nombre)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.tipo_cabello, self.type_new)
        self.assertEqual(self.client_profile.grosor_cabello, self.thickness)
        diagnosis = DiagnosticoCapilar.objects.get()
        self.assertEqual(diagnosis.autor, self.client_user)
        self.assertIsNone(diagnosis.profesional)
        self.assertEqual(diagnosis.procedencia, 'AUTORREPORTE')
        self.assertEqual(diagnosis.campos_evaluados, ['tipo_cabello'])
        change = CambioPerfilCapilar.objects.get()
        self.assertEqual(change.valores_anteriores['tipo_cabello'], self.type_initial.pk)
        self.assertEqual(change.valores_nuevos['tipo_cabello'], self.type_new.pk)

    def test_personal_only_update_does_not_create_false_self_report(self):
        self.authenticate(self.client_user)

        response = self.client.put(
            self.profile_url,
            {'first_name': 'Nombre actualizado'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(DiagnosticoCapilar.objects.exists())
        self.assertFalse(CambioPerfilCapilar.objects.exists())

    def test_new_professional_evaluation_promotes_only_evaluated_fields(self):
        response = self.create_evaluation(
            tipo_cabello=self.type_new.pk,
            estado_general=self.state.pk,
            observaciones='Observación profesional original.',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        diagnosis = DiagnosticoCapilar.objects.get()
        self.assertEqual(diagnosis.profesional, self.actor)
        self.assertEqual(diagnosis.autor, self.actor)
        self.assertEqual(diagnosis.procedencia, 'PROFESIONAL')
        self.assertCountEqual(
            diagnosis.campos_evaluados,
            ['tipo_cabello', 'estado_general'],
        )
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.tipo_cabello, self.type_new)
        self.assertEqual(self.client_profile.estado_general, self.state)
        self.assertEqual(self.client_profile.grosor_cabello, self.thickness)

    def test_new_evaluation_preserves_previous_diagnosis(self):
        first = self.create_evaluation(tipo_cabello=self.type_new.pk)
        second = self.create_evaluation(estado_general=self.state.pk)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        diagnoses = list(DiagnosticoCapilar.objects.order_by('pk'))
        self.assertEqual(len(diagnoses), 2)
        self.assertEqual(diagnoses[0].tipo_cabello, self.type_new)
        self.assertIsNone(diagnoses[0].estado_general)
        self.assertEqual(diagnoses[1].estado_general, self.state)

    def test_author_and_source_cannot_be_spoofed(self):
        spoofed = self.create_user('spoofed-profile-author@test.com')

        response = self.create_evaluation(
            tipo_cabello=self.type_new.pk,
            autor=spoofed.pk,
            profesional=spoofed.pk,
            procedencia='AUTORREPORTE',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        diagnosis = DiagnosticoCapilar.objects.get()
        self.assertEqual(diagnosis.autor, self.actor)
        self.assertEqual(diagnosis.profesional, self.actor)
        self.assertEqual(diagnosis.procedencia, 'PROFESIONAL')

    def test_professional_text_is_preserved_separately_from_calculated_result(self):
        original = 'La profesional observó elasticidad reducida.'

        response = self.create_evaluation(
            tipo_cabello=self.type_new.pk,
            observaciones=original,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        diagnosis = DiagnosticoCapilar.objects.get()
        self.assertEqual(diagnosis.observaciones, original)
        self.assertTrue(diagnosis.resultado_calculado)
        self.assertNotEqual(diagnosis.resultado_calculado, original)
        self.assertEqual(diagnosis.estado_resultado, 'CALCULADO')
        self.assertEqual(response.data['mensaje_diagnostico'], diagnosis.resultado_calculado)

    def test_correction_records_reason_before_after_and_updates_current_source(self):
        created = self.create_evaluation(tipo_cabello=self.type_new.pk)
        diagnosis = DiagnosticoCapilar.objects.get(pk=created.data['id'])

        response = self.client.post(
            self.correction_url(diagnosis),
            {
                'motivo': 'Se seleccionó por error el tipo de cabello adyacente.',
                'tipo_cabello': self.type_corrected.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        diagnosis.refresh_from_db()
        self.client_profile.refresh_from_db()
        self.assertEqual(diagnosis.tipo_cabello, self.type_corrected)
        self.assertEqual(self.client_profile.tipo_cabello, self.type_corrected)
        self.assertEqual(diagnosis.estado_resultado, 'INVALIDADO')
        self.assertIsNone(diagnosis.resultado_calculado)
        correction = CorreccionDiagnosticoCapilar.objects.get()
        self.assertEqual(correction.valores_anteriores['tipo_cabello'], self.type_new.pk)
        self.assertEqual(correction.valores_nuevos['tipo_cabello'], self.type_corrected.pk)
        self.assertTrue(
            diagnosis.history.filter(tipo_cabello=self.type_new).exists()
        )

    def test_correction_requires_reason(self):
        created = self.create_evaluation(tipo_cabello=self.type_new.pk)

        missing_reason = self.client.post(
            reverse('diagnostico-capilar-corregir', args=[created.data['id']]),
            {'tipo_cabello': self.type_corrected.pk},
            format='json',
        )
        unevaluated_field = self.client.post(
            reverse('diagnostico-capilar-corregir', args=[created.data['id']]),
            {
                'motivo': 'No debe agregarse como corrección un campo no evaluado.',
                'estado_general': self.state.pk,
            },
            format='json',
        )

        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unevaluated_field.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            unevaluated_field.data['code'],
            'FIELD_NOT_ORIGINALLY_EVALUATED',
        )
        self.assertFalse(CorreccionDiagnosticoCapilar.objects.exists())

    def test_professional_without_effective_skill_cannot_create_or_correct(self):
        actor, _ = self.create_professional(
            'profile-no-skill@test.com',
            skill=False,
        )
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=actor,
            autor=actor,
            procedencia='PROFESIONAL',
        )
        self.authenticate(actor)

        create_response = self.client.post(
            self.list_url,
            {'cliente': self.client_profile.pk, 'tipo_cabello': self.type_new.pk},
            format='json',
        )
        correction_response = self.client.post(
            self.correction_url(diagnosis),
            {
                'motivo': 'Corrección que no tiene autoridad técnica efectiva.',
                'tipo_cabello': self.type_corrected.pk,
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(correction_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_writer_cannot_correct_foreign_professional_evaluation(self):
        foreign, _ = self.create_professional('foreign-profile-owner@test.com')
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=foreign,
            autor=foreign,
            procedencia='PROFESIONAL',
        )
        self.authenticate(self.actor)

        response = self.client.post(
            self.correction_url(diagnosis),
            {
                'motivo': 'Intento de corrección de una evaluación ajena.',
                'tipo_cabello': self.type_corrected.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(CorreccionDiagnosticoCapilar.objects.exists())

    def test_correction_does_not_override_a_newer_profile_source(self):
        created = self.create_evaluation(tipo_cabello=self.type_new.pk)
        diagnosis = DiagnosticoCapilar.objects.get(pk=created.data['id'])
        self.authenticate(self.client_user)
        self.client.put(
            self.profile_url,
            {'tipo_cabello': self.type_initial.pk},
            format='json',
        )
        self.authenticate(self.actor)

        response = self.client.post(
            self.correction_url(diagnosis),
            {
                'motivo': 'Corrección histórica posterior a un autorreporte más nuevo.',
                'tipo_cabello': self.type_corrected.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.tipo_cabello, self.type_initial)
        self.assertIsNone(response.data['correccion']['cambio_perfil'])

    def test_correction_invalidates_without_duplicating_routines_or_notifications(self):
        routine = Rutina.objects.create(
            nombre='Rutina derivada',
            objetivo='Objetivo',
            archivo='rutinas_pdfs/test.pdf',
            estado='publicada',
            creada_por=self.actor,
        )
        config = ConfiguracionDiagnostico.get_singleton()
        config.rutina_critico = routine
        config.save(update_fields=['rutina_critico'])
        created = self.create_evaluation(tipo_cabello=self.type_new.pk)
        diagnosis = DiagnosticoCapilar.objects.get(pk=created.data['id'])
        before = (RutinaCliente.objects.count(), Notificacion.objects.count())

        response = self.client.post(
            self.correction_url(diagnosis),
            {
                'motivo': 'El tipo informado originalmente fue seleccionado por error.',
                'tipo_cabello': self.type_corrected.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            (RutinaCliente.objects.count(), Notificacion.objects.count()),
            before,
        )

    def test_profile_synchronization_failure_rolls_back_evaluation(self):
        self.authenticate(self.actor)

        with patch(
            'gestion.hair_profile_services.CambioPerfilCapilar.objects.create',
            side_effect=RuntimeError('forced profile synchronization failure'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.list_url,
                    {
                        'cliente': self.client_profile.pk,
                        'tipo_cabello': self.type_new.pk,
                    },
                    format='json',
                )

        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.tipo_cabello, self.type_initial)
        self.assertFalse(DiagnosticoCapilar.objects.exists())
        self.assertFalse(CambioPerfilCapilar.objects.exists())

    def test_finalization_keeps_increment0_contract_and_records_automatic_source(self):
        self.actor.user_permissions.add(self.finalize_permission)
        category = CategoriaServicio.objects.create(nombre='Impacto trazable')
        service = Servicio.objects.create(
            nombre='Servicio con impacto trazable',
            categoria=category,
            duracion_estimada=30,
            precio_base='1000.00',
            impacto_estado=self.state,
        )
        turno = Turno.objects.create(
            cliente=self.client_profile,
            profesional=self.personal,
            fecha=timezone.localdate(),
            hora_inicio=time(10, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico=service.precio_base,
            duracion_minutos=30,
        )
        self.authenticate(self.actor)

        response = self.client.post(
            reverse('turno-finalizar-turno', args=[turno.pk]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.estado_general, self.state)
        current = VigenciaCampoPerfilCapilar.objects.get(
            cliente=self.client_profile,
            campo='estado_general',
        )
        self.assertEqual(current.procedencia, 'POST_SERVICIO_AUTOMATICO')
        self.assertIsNone(current.diagnostico_fuente)
        self.assertFalse(DiagnosticoCapilar.objects.exists())

    def test_legacy_diagnosis_is_not_given_fictitious_metadata(self):
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            tipo_cabello=self.type_initial,
        )
        self.authenticate(self.client_user)

        response = self.client.get(
            reverse('diagnostico-capilar-detail', args=[diagnosis.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        diagnosis.refresh_from_db()
        self.assertIsNone(diagnosis.autor)
        self.assertIsNone(diagnosis.campos_evaluados)
        self.assertIsNone(diagnosis.estado_resultado)
        self.assertFalse(VigenciaCampoPerfilCapilar.objects.exists())


class HairProfileWriterConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_diagnosis',
        )
        self.skill = Habilidad.objects.get(code='DIAGNOSTICO')
        client_user = Usuario.objects.create_user(
            email='concurrent-profile-client@test.com',
            password='HairProfileTests!2026',
        )
        self.client_profile = Cliente.objects.create(
            usuario=client_user,
            activo=True,
        )
        self.hair_type = TipoCabello.objects.create(nombre='Concurrent type')
        self.hair_state = EstadoGeneral.objects.create(nombre='Concurrent state')
        self.actors = [
            self.create_professional(f'concurrent-profile-{index}@test.com')
            for index in range(2)
        ]

    def create_professional(self, email):
        actor = Usuario.objects.create_user(
            email=email,
            password='HairProfileTests!2026',
        )
        actor.user_permissions.add(self.permission)
        personal = Personal.objects.create(
            usuario=actor,
            nombre='Concurrente',
            apellido=email,
            rol='asistente',
            activo=True,
        )
        PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=self.skill,
            activa=True,
        )
        return actor

    def write_evaluation(self, barrier, actor_id, data):
        close_old_connections()
        try:
            actor = Usuario.objects.get(pk=actor_id)
            barrier.wait(timeout=10)
            diagnosis = create_professional_evaluation(
                actor=actor,
                cliente_id=self.client_profile.pk,
                data=data,
            )
            return diagnosis.pk
        finally:
            close_old_connections()

    def test_concurrent_writers_preserve_both_partial_updates(self):
        self.assertEqual(connection.vendor, 'postgresql')
        barrier = Barrier(2)
        commands = (
            (self.actors[0].pk, {'tipo_cabello': self.hair_type}),
            (self.actors[1].pk, {'estado_general': self.hair_state}),
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self.write_evaluation, barrier, actor_id, data)
                for actor_id, data in commands
            ]
            diagnosis_ids = [future.result(timeout=20) for future in futures]

        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.tipo_cabello, self.hair_type)
        self.assertEqual(self.client_profile.estado_general, self.hair_state)
        self.assertEqual(len(set(diagnosis_ids)), 2)
        self.assertEqual(CambioPerfilCapilar.objects.count(), 2)
        self.assertEqual(VigenciaCampoPerfilCapilar.objects.count(), 2)
