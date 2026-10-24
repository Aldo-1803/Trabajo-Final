from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Habilidad, Personal, PersonalHabilidad, Servicio, ServicioHabilidad
from gestion.personal_skill_services import (
    PERSONAL_SKILL_ASSIGNED,
    PERSONAL_SKILL_AUDIT_TABLE,
    assign_skill,
)
from usuarios.models import Usuario
from usuarios.roles import BusinessRole


class SkillModelTests(TestCase):
    def setUp(self):
        self.personal = Personal.objects.create(
            nombre='Julia', apellido='Díaz', rol='asistente'
        )
        self.skill = Habilidad.objects.create(
            code='LAVADO_MODEL_TEST', nombre='Lavado de prueba'
        )
        self.service = Servicio.objects.create(nombre='Lavado básico')

    def test_skill_code_is_unique(self):
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Habilidad.objects.create(
                    code='LAVADO_MODEL_TEST', nombre='Duplicada'
                )

    def test_personal_skill_is_unique_and_can_be_revoked_without_deleting(self):
        assignment = PersonalHabilidad.objects.create(
            personal=self.personal, habilidad=self.skill
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PersonalHabilidad.objects.create(personal=self.personal, habilidad=self.skill)

        assignment.activa = False
        assignment.save(update_fields=['activa'])
        self.assertFalse(PersonalHabilidad.objects.get(pk=assignment.pk).activa)

    def test_service_skill_is_unique(self):
        ServicioHabilidad.objects.create(servicio=self.service, habilidad=self.skill)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                ServicioHabilidad.objects.create(servicio=self.service, habilidad=self.skill)


class PersonalSkillApiTests(APITestCase):
    def setUp(self):
        self.manage_skills = Permission.objects.get(
            content_type__app_label='gestion', codename='manage_skills'
        )
        self.actor = self.create_user('skills-manager@test.com')
        self.actor.user_permissions.add(self.manage_skills)
        self.personal = Personal.objects.create(
            nombre='Julia', apellido='Díaz', rol='asistente', activo=False
        )
        self.active_skill = Habilidad.objects.create(
            code='DIAGNOSTICO_TEST', nombre='Diagnóstico test'
        )
        self.inactive_skill = Habilidad.objects.create(
            code='COLORACION_TEST', nombre='Coloración test', activa=False
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='SkillsTest!2026',
            **extra_fields,
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def skills_url(self):
        return reverse('habilidad-list')

    def assignments_url(self):
        return reverse('personal-habilidades', args=[self.personal.pk])

    def assign_url(self):
        return reverse('personal-asignar-habilidad', args=[self.personal.pk])

    def revoke_url(self, skill):
        return reverse('personal-revocar-habilidad', args=[self.personal.pk, skill.pk])

    def reactivate_url(self, skill):
        return reverse('personal-reactivar-habilidad', args=[self.personal.pk, skill.pk])

    def test_individual_manage_skills_lists_assigns_revokes_and_reactivates(self):
        self.authenticate()

        self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(self.assignments_url()).status_code, status.HTTP_200_OK)
        response = self.client.post(
            self.assign_url(), {'habilidad_id': self.active_skill.pk}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['event'], PERSONAL_SKILL_ASSIGNED)
        assignment = PersonalHabilidad.objects.get(
            personal=self.personal, habilidad=self.active_skill
        )
        self.assertTrue(assignment.activa)
        self.assertFalse(self.personal.activo)
        self.assertTrue(Auditoria.objects.filter(
            tabla=PERSONAL_SKILL_AUDIT_TABLE,
            registro_id=assignment.pk,
            valor_nuevo__event=PERSONAL_SKILL_ASSIGNED,
        ).exists())

        response = self.client.post(self.revoke_url(self.active_skill), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        self.assertFalse(assignment.activa)
        self.assertEqual(PersonalHabilidad.objects.filter(
            personal=self.personal, habilidad=self.active_skill
        ).count(), 1)

        response = self.client.post(self.reactivate_url(self.active_skill), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        self.assertTrue(assignment.activa)

    def test_assigning_again_reactivates_existing_assignment_without_duplicate(self):
        PersonalHabilidad.objects.create(
            personal=self.personal, habilidad=self.active_skill, activa=False
        )
        self.authenticate()

        response = self.client.post(
            self.assign_url(), {'habilidad_id': self.active_skill.pk}, format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['event'], 'PERSONAL_SKILL_REACTIVATED')
        self.assertEqual(PersonalHabilidad.objects.filter(
            personal=self.personal, habilidad=self.active_skill
        ).count(), 1)

    def test_inactive_skill_cannot_be_assigned_or_reactivated(self):
        self.authenticate()

        response = self.client.post(
            self.assign_url(), {'habilidad_id': self.inactive_skill.pk}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'INACTIVE_SKILL')

    def test_manage_personal_without_manage_skills_is_forbidden(self):
        actor = self.create_user('no-skills@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion', codename='manage_personal'
        ))
        self.authenticate(actor)

        self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(
            self.assign_url(), {'habilidad_id': self.active_skill.pk}, format='json'
        ).status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_without_permission_and_client_are_forbidden(self):
        client = self.create_user('client@test.com')
        client.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        for user in (
            self.create_user('staff-only@test.com', is_staff=True),
            client,
        ):
            with self.subTest(user=user.email):
                self.authenticate(user)
                self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_403_FORBIDDEN)

    def test_administrador_with_is_staff_false_uses_effective_permission(self):
        actor = self.create_user('business-admin@test.com', is_staff=False)
        actor.groups.add(Group.objects.get(name=BusinessRole.ADMINISTRADOR))
        self.authenticate(actor)

        self.assertFalse(actor.is_staff)
        self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_200_OK)

    def test_anonymous_is_unauthorized(self):
        self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_audit_failure_rolls_back_assignment(self):
        with patch('gestion.personal_skill_services.Auditoria.objects.create', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                assign_skill(
                    actor=self.actor,
                    personal_id=self.personal.pk,
                    skill_id=self.active_skill.pk,
                )
        self.assertFalse(PersonalHabilidad.objects.filter(
            personal=self.personal, habilidad=self.active_skill
        ).exists())
