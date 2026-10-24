from datetime import date, time, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    CategoriaServicio,
    DiagnosticoCapilar,
    Habilidad,
    HorarioLaboral,
    Personal,
    PersonalHabilidad,
    Servicio,
    TipoCabello,
    Turno,
)
from gestion.serializers import PersonalSerializer
from gestion.technical_skill_access import user_has_active_skill
from gestion.views import DiagnosticoCapilarViewSet
from usuarios.models import Cliente, Usuario


class DiagnosisAuthorizationApiTests(APITestCase):
    def setUp(self):
        self.engine_patcher = patch(
            'gestion.views.DiagnosticoCapilarViewSet._ejecutar_motor_diagnostico'
        )
        self.engine = self.engine_patcher.start()
        self.addCleanup(self.engine_patcher.stop)

        self.skill = Habilidad.objects.get(code='DIAGNOSTICO')
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
        self.client_user = self.create_user('diagnosis-client@test.com')
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            activo=True,
        )
        self.other_client_user = self.create_user('other-diagnosis-client@test.com')
        self.other_client = Cliente.objects.create(
            usuario=self.other_client_user,
            activo=True,
        )
        self.list_url = reverse('diagnostico-capilar-list')

    @staticmethod
    def create_user(email, *, active=True):
        user = Usuario(email=email, is_active=active)
        user.set_unusable_password()
        user.save()
        return user

    @staticmethod
    def add_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    def create_personal(
        self,
        user,
        *,
        active=True,
        legacy_diagnosis=False,
        role='asistente',
    ):
        return Personal.objects.create(
            usuario=user,
            nombre='Actor',
            apellido=user.email.split('@')[0],
            rol=role,
            activo=active,
            realiza_diagnostico=legacy_diagnosis,
        )

    def assign_diagnosis_skill(self, personal, *, active=True):
        return PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=self.skill,
            activa=active,
        )

    def authorize_writer(
        self,
        email,
        *,
        personal_active=True,
        assignment=True,
        legacy_diagnosis=False,
    ):
        user = self.create_user(email)
        user.user_permissions.add(self.create_permission)
        personal = self.create_personal(
            user,
            active=personal_active,
            legacy_diagnosis=legacy_diagnosis,
        )
        if assignment:
            self.assign_diagnosis_skill(personal)
        return user, personal

    def create_diagnosis(self, actor, **payload):
        self.client.force_authenticate(actor)
        return self.client.post(
            self.list_url,
            {'cliente': self.client_profile.pk, **payload},
            format='json',
        )

    def assert_create_forbidden(self, actor):
        response = self.create_diagnosis(actor)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(DiagnosticoCapilar.objects.exists())

    def test_permission_skill_and_active_personal_create_with_real_actor(self):
        actor, _ = self.authorize_writer('valid-diagnosis@test.com')
        spoofed_author = self.create_user('spoofed-author@test.com')

        response = self.create_diagnosis(
            actor,
            profesional=spoofed_author.pk,
            recomendaciones='Cuidado técnico',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        diagnosis = DiagnosticoCapilar.objects.get()
        self.assertEqual(diagnosis.profesional, actor)
        self.assertEqual(diagnosis.recomendaciones, 'Cuidado técnico')
        self.engine.assert_called_once_with(diagnosis)

    def test_permission_without_skill_is_forbidden(self):
        actor, _ = self.authorize_writer(
            'permission-without-skill@test.com',
            assignment=False,
        )
        self.assert_create_forbidden(actor)

    def test_inactive_skill_assignment_is_forbidden(self):
        actor = self.create_user('inactive-diagnosis-assignment@test.com')
        actor.user_permissions.add(self.create_permission)
        personal = self.create_personal(actor)
        self.assign_diagnosis_skill(personal, active=False)
        self.assert_create_forbidden(actor)

    def test_skill_without_permission_is_forbidden(self):
        actor = self.create_user('skill-without-permission@test.com')
        personal = self.create_personal(actor)
        self.assign_diagnosis_skill(personal)
        self.assert_create_forbidden(actor)

    def test_inactive_personal_is_forbidden(self):
        actor, _ = self.authorize_writer(
            'inactive-personal-diagnosis@test.com',
            personal_active=False,
        )
        self.assert_create_forbidden(actor)

    def test_user_without_personal_is_forbidden(self):
        actor = self.create_user('diagnosis-without-personal@test.com')
        actor.user_permissions.add(self.create_permission)
        self.assert_create_forbidden(actor)

    def test_administrator_without_skill_is_forbidden(self):
        actor = self.create_user('admin-without-diagnosis-skill@test.com')
        self.add_role(actor, 'ADMINISTRADOR')
        self.create_personal(actor, role='administrador')
        self.assertFalse(actor.is_staff)
        self.assert_create_forbidden(actor)

    def test_administrator_with_skill_is_allowed_without_is_staff(self):
        actor = self.create_user('admin-with-diagnosis-skill@test.com')
        self.add_role(actor, 'ADMINISTRADOR')
        personal = self.create_personal(actor, role='administrador')
        self.assign_diagnosis_skill(personal)

        response = self.create_diagnosis(actor)

        self.assertFalse(actor.is_staff)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_employee_with_individual_permission_and_skill_is_allowed(self):
        actor = self.create_user('employee-diagnosis@test.com')
        self.add_role(actor, 'EMPLEADO')
        actor.user_permissions.add(self.create_permission)
        personal = self.create_personal(actor)
        self.assign_diagnosis_skill(personal)

        response = self.create_diagnosis(actor)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_professional_role_with_permission_and_skill_is_allowed(self):
        actor = self.create_user('professional-diagnosis@test.com')
        self.add_role(actor, 'PROFESIONAL')
        personal = self.create_personal(actor, role='colorista')
        self.assign_diagnosis_skill(personal)

        response = self.create_diagnosis(actor)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_legacy_true_without_canonical_assignment_is_forbidden(self):
        actor, _ = self.authorize_writer(
            'legacy-true-diagnosis@test.com',
            assignment=False,
            legacy_diagnosis=True,
        )
        self.assert_create_forbidden(actor)

    def test_legacy_false_with_canonical_assignment_is_allowed(self):
        actor, personal = self.authorize_writer(
            'legacy-false-diagnosis@test.com',
            legacy_diagnosis=False,
        )

        response = self.create_diagnosis(actor)

        self.assertFalse(personal.realiza_diagnostico)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_legacy_flags_are_read_only_in_personal_serializer(self):
        personal = Personal.objects.create(
            nombre='Flags',
            apellido='Legacy',
            rol='asistente',
            realiza_diagnostico=True,
            realiza_lavado=False,
            realiza_color=True,
        )
        serializer = PersonalSerializer(
            personal,
            data={
                'realiza_diagnostico': False,
                'realiza_lavado': True,
                'realiza_color': False,
            },
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        personal.refresh_from_db()
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)

    def test_inactive_skill_catalog_is_forbidden(self):
        actor, _ = self.authorize_writer('inactive-diagnosis-skill@test.com')
        self.skill.activa = False
        self.skill.save(update_fields=['activa'])
        self.assert_create_forbidden(actor)

    def test_inactive_user_fails_skill_helper(self):
        actor, _ = self.authorize_writer('inactive-diagnosis-user@test.com')
        actor.is_active = False
        actor.save(update_fields=['is_active'])
        self.assertFalse(user_has_active_skill(actor, 'DIAGNOSTICO'))
        self.assert_create_forbidden(actor)

    def test_anonymous_create_is_unauthorized(self):
        response = self.client.post(
            self.list_url,
            {'cliente': self.client_profile.pk},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_client_reads_only_owned_diagnoses(self):
        own = DiagnosticoCapilar.objects.create(cliente=self.client_profile)
        foreign = DiagnosticoCapilar.objects.create(cliente=self.other_client)
        self.client.force_authenticate(self.client_user)

        list_response = self.client.get(self.list_url)
        own_response = self.client.get(
            reverse('diagnostico-capilar-detail', args=[own.pk])
        )
        foreign_response = self.client.get(
            reverse('diagnostico-capilar-detail', args=[foreign.pk])
        )
        mine_response = self.client.get(
            reverse('diagnostico-capilar-mis-diagnosticos')
        )

        list_items = list_response.data.get('results', list_response.data)

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in list_items], [own.pk])
        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(foreign_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual([item['id'] for item in mine_response.data], [own.pk])

    def test_por_cliente_preserves_ownership(self):
        DiagnosticoCapilar.objects.create(cliente=self.other_client)
        self.client.force_authenticate(self.client_user)

        response = self.client.get(
            reverse('diagnostico-capilar-por-cliente'),
            {'cliente_id': self.other_client.pk},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_profile_endpoint_keeps_owned_latest_diagnosis(self):
        own = DiagnosticoCapilar.objects.create(cliente=self.client_profile)
        DiagnosticoCapilar.objects.create(cliente=self.other_client)
        self.client.force_authenticate(self.client_user)

        response = self.client.get(reverse('diagnostico'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], own.pk)

    def test_global_read_requires_manage_permission_and_skill(self):
        DiagnosticoCapilar.objects.create(cliente=self.client_profile)
        actor, _ = self.authorize_writer('create-only-reader@test.com')
        self.client.force_authenticate(actor)
        denied = self.client.get(self.list_url)

        actor.user_permissions.add(self.manage_permission)
        actor = Usuario.objects.get(pk=actor.pk)
        self.client.force_authenticate(actor)
        allowed = self.client.get(self.list_url)

        allowed_items = allowed.data.get('results', allowed.data)

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(allowed_items), 1)

    def test_manage_permission_without_skill_cannot_read_globally(self):
        actor = self.create_user('manage-without-skill@test.com')
        actor.user_permissions.add(self.manage_permission)
        self.create_personal(actor)
        self.client.force_authenticate(actor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_protects_client_and_author(self):
        actor, _ = self.authorize_writer('diagnosis-updater@test.com')
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=actor,
        )
        foreign_author = self.create_user('foreign-diagnosis-author@test.com')
        self.client.force_authenticate(actor)
        detail_url = reverse('diagnostico-capilar-detail', args=[diagnosis.pk])

        author_response = self.client.patch(
            detail_url,
            {
                'profesional': foreign_author.pk,
                'recomendaciones': 'Actualizada',
            },
            format='json',
        )
        client_response = self.client.patch(
            detail_url,
            {'cliente': self.other_client.pk},
            format='json',
        )
        diagnosis.refresh_from_db()

        self.assertEqual(author_response.status_code, status.HTTP_200_OK)
        self.assertEqual(client_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(diagnosis.profesional, actor)
        self.assertEqual(diagnosis.cliente, self.client_profile)
        self.assertEqual(diagnosis.recomendaciones, 'Actualizada')

    def test_writer_without_global_management_cannot_update_another_author(self):
        actor, _ = self.authorize_writer('own-diagnosis-only@test.com')
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=self.create_user('original-author@test.com'),
        )
        self.client.force_authenticate(actor)

        response = self.client.patch(
            reverse('diagnostico-capilar-detail', args=[diagnosis.pk]),
            {'recomendaciones': 'No permitida'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_is_method_not_allowed(self):
        actor, _ = self.authorize_writer('diagnosis-delete@test.com')
        diagnosis = DiagnosticoCapilar.objects.create(
            cliente=self.client_profile,
            profesional=actor,
        )
        self.client.force_authenticate(actor)

        response = self.client.delete(
            reverse('diagnostico-capilar-detail', args=[diagnosis.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(DiagnosticoCapilar.objects.filter(pk=diagnosis.pk).exists())

    def test_finalize_service_uses_same_diagnosis_capability_and_actor(self):
        hair_type = TipoCabello.objects.create(nombre='Tipo finalización')
        self.client_profile.tipo_cabello = hair_type
        self.client_profile.save(update_fields=['tipo_cabello'])
        turno = Turno.objects.create(
            cliente=self.client_profile,
            fecha=timezone.localdate(),
            hora_inicio=timezone.localtime().time(),
            estado=Turno.Estado.EN_PROCESO,
        )
        actor = self.create_user('finalize-diagnosis@test.com')
        actor.user_permissions.add(self.finalize_permission, self.create_permission)
        personal = self.create_personal(actor)
        self.client.force_authenticate(actor)
        url = reverse('turno-finalizar-turno', args=[turno.pk])

        denied = self.client.post(url, {}, format='json')
        self.assign_diagnosis_skill(personal)
        allowed = self.client.post(url, {}, format='json')

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        diagnosis = DiagnosticoCapilar.objects.get(cliente=self.client_profile)
        self.assertEqual(diagnosis.profesional, actor)

    def test_diagnosis_recommendation_uses_canonical_availability_not_category_text(self):
        tomorrow = date.today() + timedelta(days=1)
        category = CategoriaServicio.objects.create(nombre='Diseño y Color legacy')
        service = Servicio.objects.create(
            nombre='Servicio recomendado sin requisito técnico',
            categoria=category,
            activo=True,
            duracion_estimada=30,
            precio_base='1000.00',
        )
        personal = Personal.objects.create(
            nombre='Agenda',
            apellido='Canónica',
            rol='asistente',
            activo=True,
            realiza_color=False,
        )
        HorarioLaboral.objects.create(
            personal=personal,
            dia_semana=tomorrow.weekday(),
            hora_inicio=time(9, 0),
            hora_fin=time(12, 0),
            activo=True,
            permite_diseno_color=False,
            permite_complemento=False,
        )
        diagnosis = DiagnosticoCapilar.objects.create(cliente=self.client_profile)

        suggested = DiagnosticoCapilarViewSet()._recomendar_primer_hueco_disponible(
            diagnosis,
            service,
        )

        self.assertIsNotNone(suggested)
        self.assertEqual(suggested.profesional, personal)
        self.assertEqual(suggested.fecha, tomorrow)
