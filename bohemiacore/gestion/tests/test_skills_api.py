import json
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Habilidad, Personal, PersonalHabilidad, Servicio, ServicioHabilidad
from gestion.personal_skill_services import (
    InvalidPersonalSkillReason,
    PERSONAL_SKILL_ASSIGNED,
    PERSONAL_SKILL_AUDIT_TABLE,
    PERSONAL_SKILL_ASSIGN_SOURCE,
    PERSONAL_SKILL_REACTIVATED,
    PERSONAL_SKILL_REACTIVATE_SOURCE,
    PERSONAL_SKILL_REVOKED,
    PERSONAL_SKILL_REVOKE_SOURCE,
    assign_skill,
    reactivate_skill,
    revoke_skill,
)
from gestion.technical_skill_access import user_has_active_skill
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


class PersonalSkillServiceAuditTests(TestCase):
    reason = 'Habilitación técnica aprobada por administración'

    def setUp(self):
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_skills',
        )
        self.actor = self.create_user('skill-service-actor@test.com')
        self.actor.user_permissions.add(permission)
        self.linked_user = self.create_user('skill-service-target@test.com')
        self.personal = Personal.objects.create(
            usuario=self.linked_user,
            nombre='Técnica',
            apellido='Auditada',
            rol='asistente',
            activo=True,
        )
        self.skill = Habilidad.objects.create(
            code='SKILL_SERVICE_AUDIT',
            nombre='Skill service audit',
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='SkillService!2026',
            **extra_fields,
        )

    def semantic_audits(self):
        return Auditoria.objects.filter(
            tabla=PERSONAL_SKILL_AUDIT_TABLE,
            valor_nuevo__event__in=(
                PERSONAL_SKILL_ASSIGNED,
                PERSONAL_SKILL_REVOKED,
                PERSONAL_SKILL_REACTIVATED,
            ),
        )

    def test_new_assignment_records_actor_target_source_reason_and_state(self):
        result = assign_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason=f'  {self.reason}  ',
        )

        self.assertTrue(result.changed)
        self.assertEqual(result.event, PERSONAL_SKILL_ASSIGNED)
        audit = self.semantic_audits().get()
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, result.assignment.pk)
        self.assertEqual(audit.valor_anterior['personal_id'], self.personal.pk)
        self.assertEqual(audit.valor_anterior['skill_id'], self.skill.pk)
        self.assertIsNone(audit.valor_anterior['activa'])
        self.assertEqual(audit.valor_anterior['user_id'], self.linked_user.pk)
        self.assertEqual(audit.valor_nuevo['event'], PERSONAL_SKILL_ASSIGNED)
        self.assertEqual(
            audit.valor_nuevo['source'],
            PERSONAL_SKILL_ASSIGN_SOURCE,
        )
        self.assertEqual(audit.valor_nuevo['actor_id'], self.actor.pk)
        self.assertEqual(audit.valor_nuevo['personal_id'], self.personal.pk)
        self.assertEqual(audit.valor_nuevo['skill_id'], self.skill.pk)
        self.assertEqual(audit.valor_nuevo['user_id'], self.linked_user.pk)
        self.assertIsNone(audit.valor_nuevo['previous_active'])
        self.assertTrue(audit.valor_nuevo['current_active'])
        self.assertEqual(audit.valor_nuevo['reason'], self.reason)
        self.assertNotIn('operation_id', audit.valor_nuevo)

    def test_effective_revoke_and_reactivate_have_one_event_each(self):
        assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.skill,
            activa=True,
        )

        revoked = revoke_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason='Suspensión temporal de la habilitación',
        )

        assignment.refresh_from_db()
        self.assertTrue(revoked.changed)
        self.assertFalse(assignment.activa)
        revoke_audit = self.semantic_audits().get()
        self.assertEqual(revoke_audit.usuario, self.actor)
        self.assertEqual(
            revoke_audit.valor_nuevo['personal_id'],
            self.personal.pk,
        )
        self.assertEqual(revoke_audit.valor_nuevo['skill_id'], self.skill.pk)
        self.assertEqual(revoke_audit.valor_nuevo['event'], PERSONAL_SKILL_REVOKED)
        self.assertEqual(
            revoke_audit.valor_nuevo['source'],
            PERSONAL_SKILL_REVOKE_SOURCE,
        )
        self.assertTrue(revoke_audit.valor_nuevo['previous_active'])
        self.assertFalse(revoke_audit.valor_nuevo['current_active'])
        self.assertEqual(
            revoke_audit.valor_nuevo['reason'],
            'Suspensión temporal de la habilitación',
        )

        reactivated = reactivate_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason='Reactivación técnica formalmente aprobada',
        )

        assignment.refresh_from_db()
        self.assertTrue(reactivated.changed)
        self.assertTrue(assignment.activa)
        self.assertEqual(self.semantic_audits().count(), 2)
        reactivate_audit = self.semantic_audits().get(
            valor_nuevo__event=PERSONAL_SKILL_REACTIVATED
        )
        self.assertEqual(reactivate_audit.usuario, self.actor)
        self.assertEqual(
            reactivate_audit.valor_nuevo['personal_id'],
            self.personal.pk,
        )
        self.assertEqual(reactivate_audit.valor_nuevo['skill_id'], self.skill.pk)
        self.assertEqual(
            reactivate_audit.valor_nuevo['source'],
            PERSONAL_SKILL_REACTIVATE_SOURCE,
        )
        self.assertFalse(reactivate_audit.valor_nuevo['previous_active'])
        self.assertTrue(reactivate_audit.valor_nuevo['current_active'])
        self.assertEqual(
            reactivate_audit.valor_nuevo['reason'],
            'Reactivación técnica formalmente aprobada',
        )

    def test_assign_command_can_reactivate_with_its_own_stable_source(self):
        PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.skill,
            activa=False,
        )

        result = assign_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason='Reincorporación desde el comando de asignación',
        )

        self.assertEqual(result.event, PERSONAL_SKILL_REACTIVATED)
        audit = self.semantic_audits().get()
        self.assertEqual(audit.valor_nuevo['source'], PERSONAL_SKILL_ASSIGN_SOURCE)

    def test_noops_do_not_create_semantic_events(self):
        assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.skill,
            activa=True,
        )

        assigned = assign_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason='Confirmación de habilidad ya asignada',
        )
        reactivated = reactivate_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason='Confirmación de habilidad ya activa',
        )
        assignment.activa = False
        assignment.save(update_fields=['activa'])
        revoked = revoke_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason='Confirmación de habilidad ya revocada',
        )

        self.assertFalse(assigned.changed)
        self.assertFalse(reactivated.changed)
        self.assertFalse(revoked.changed)
        self.assertFalse(self.semantic_audits().exists())

    def test_invalid_reasons_change_nothing_and_create_no_events(self):
        assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.skill,
            activa=True,
        )
        commands = (
            assign_skill,
            revoke_skill,
            reactivate_skill,
        )
        for command in commands:
            for reason in (None, '', ' ', 'x', 'x' * 501):
                with self.subTest(command=command.__name__, reason=reason):
                    with self.assertRaises(InvalidPersonalSkillReason):
                        command(
                            actor=self.actor,
                            personal_id=self.personal.pk,
                            skill_id=self.skill.pk,
                            reason=reason,
                        )

        assignment.refresh_from_db()
        self.assertTrue(assignment.activa)
        self.assertFalse(self.semantic_audits().exists())

    def test_audit_failures_roll_back_each_mutation(self):
        with patch(
            'gestion.personal_skill_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                assign_skill(
                    actor=self.actor,
                    personal_id=self.personal.pk,
                    skill_id=self.skill.pk,
                    reason=self.reason,
                )
        self.assertFalse(
            PersonalHabilidad.objects.filter(
                personal=self.personal,
                habilidad=self.skill,
            ).exists()
        )

        assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.skill,
            activa=True,
        )
        with patch(
            'gestion.personal_skill_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                revoke_skill(
                    actor=self.actor,
                    personal_id=self.personal.pk,
                    skill_id=self.skill.pk,
                    reason='Revocación que debe revertirse',
                )
        assignment.refresh_from_db()
        self.assertTrue(assignment.activa)

        assignment.activa = False
        assignment.save(update_fields=['activa'])
        with patch(
            'gestion.personal_skill_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                reactivate_skill(
                    actor=self.actor,
                    personal_id=self.personal.pk,
                    skill_id=self.skill.pk,
                    reason='Reactivación que debe revertirse',
                )
        assignment.refresh_from_db()
        self.assertFalse(assignment.activa)
        self.assertFalse(self.semantic_audits().exists())

    def test_inactive_personal_can_be_administered_but_skill_is_not_effective(self):
        self.personal.activo = False
        self.personal.save(update_fields=['activo'])

        result = assign_skill(
            actor=self.actor,
            personal_id=self.personal.pk,
            skill_id=self.skill.pk,
            reason='Preparación técnica previa a reincorporación',
        )

        self.assertTrue(result.changed)
        self.assertFalse(
            user_has_active_skill(self.linked_user, self.skill.code)
        )
        self.assertEqual(self.semantic_audits().count(), 1)

    def test_unlinked_personal_omits_user_and_payload_has_no_secrets(self):
        unlinked = Personal.objects.create(
            nombre='Luciana',
            apellido='Reservada',
            rol='asistente',
        )
        result = assign_skill(
            actor=self.actor,
            personal_id=unlinked.pk,
            skill_id=self.skill.pk,
            reason='Asignación para Personal sin acceso digital',
        )

        audit = self.semantic_audits().get(registro_id=result.assignment.pk)
        self.assertNotIn('user_id', audit.valor_anterior)
        self.assertNotIn('user_id', audit.valor_nuevo)
        serialized = json.dumps({
            'before': audit.valor_anterior,
            'after': audit.valor_nuevo,
        }).lower()
        for forbidden in (
            'password',
            'token',
            'jwt',
            self.actor.email.lower(),
            unlinked.nombre.lower(),
            unlinked.apellido.lower(),
        ):
            self.assertNotIn(forbidden, serialized)


class PersonalSkillApiTests(APITestCase):
    reason = 'Decisión administrativa sobre habilidad técnica'

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
            self.assign_url(),
            {
                'habilidad_id': self.active_skill.pk,
                'motivo': self.reason,
            },
            format='json',
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

        response = self.client.post(
            self.revoke_url(self.active_skill),
            {'motivo': 'Revocación técnica aprobada'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        self.assertFalse(assignment.activa)
        self.assertEqual(PersonalHabilidad.objects.filter(
            personal=self.personal, habilidad=self.active_skill
        ).count(), 1)

        response = self.client.post(
            self.reactivate_url(self.active_skill),
            {'motivo': 'Reactivación técnica aprobada'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        self.assertTrue(assignment.activa)
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=PERSONAL_SKILL_AUDIT_TABLE,
                registro_id=assignment.pk,
                valor_nuevo__event__in=(
                    PERSONAL_SKILL_ASSIGNED,
                    PERSONAL_SKILL_REVOKED,
                    PERSONAL_SKILL_REACTIVATED,
                ),
            ).count(),
            3,
        )

    def test_assigning_again_reactivates_existing_assignment_without_duplicate(self):
        PersonalHabilidad.objects.create(
            personal=self.personal, habilidad=self.active_skill, activa=False
        )
        self.authenticate()

        response = self.client.post(
            self.assign_url(),
            {
                'habilidad_id': self.active_skill.pk,
                'motivo': 'Reactivar mediante asignación administrativa',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['event'], 'PERSONAL_SKILL_REACTIVATED')
        self.assertEqual(PersonalHabilidad.objects.filter(
            personal=self.personal, habilidad=self.active_skill
        ).count(), 1)

    def test_inactive_skill_cannot_be_assigned_or_reactivated(self):
        self.authenticate()

        response = self.client.post(
            self.assign_url(),
            {
                'habilidad_id': self.inactive_skill.pk,
                'motivo': self.reason,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'INACTIVE_SKILL')
        self.assertFalse(Auditoria.objects.filter(
            tabla=PERSONAL_SKILL_AUDIT_TABLE,
            valor_nuevo__event__in=(
                PERSONAL_SKILL_ASSIGNED,
                PERSONAL_SKILL_REVOKED,
                PERSONAL_SKILL_REACTIVATED,
            ),
        ).exists())

    def test_manage_personal_without_manage_skills_is_forbidden(self):
        actor = self.create_user('no-skills@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion', codename='manage_personal'
        ))
        self.authenticate(actor)

        self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(
            self.assign_url(),
            {'habilidad_id': self.active_skill.pk, 'motivo': self.reason},
            format='json',
        ).status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Auditoria.objects.filter(
            tabla=PERSONAL_SKILL_AUDIT_TABLE,
            valor_nuevo__event=PERSONAL_SKILL_ASSIGNED,
        ).exists())

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
                self.assertEqual(
                    self.client.post(
                        self.assign_url(),
                        {
                            'habilidad_id': self.active_skill.pk,
                            'motivo': self.reason,
                        },
                        format='json',
                    ).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
        self.assertFalse(Auditoria.objects.filter(
            tabla=PERSONAL_SKILL_AUDIT_TABLE,
            valor_nuevo__event=PERSONAL_SKILL_ASSIGNED,
        ).exists())

    def test_administrador_with_is_staff_false_uses_effective_permission(self):
        actor = self.create_user('business-admin@test.com', is_staff=False)
        actor.groups.add(Group.objects.get(name=BusinessRole.ADMINISTRADOR))
        self.authenticate(actor)

        self.assertFalse(actor.is_staff)
        self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_200_OK)
        response = self.client.post(
            self.assign_url(),
            {'habilidad_id': self.active_skill.pk, 'motivo': self.reason},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])

    def test_invalid_or_missing_reason_is_rejected_for_every_command(self):
        assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.active_skill,
            activa=True,
        )
        self.authenticate()
        invalid_reasons = (None, '', ' ', 'x', 'x' * 501)

        for reason in invalid_reasons:
            with self.subTest(command='assign', reason=reason):
                payload = {'habilidad_id': self.active_skill.pk}
                if reason is not None:
                    payload['motivo'] = reason
                response = self.client.post(
                    self.assign_url(), payload, format='json'
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['error']['code'], 'INVALID_REASON')

            with self.subTest(command='revoke', reason=reason):
                payload = {} if reason is None else {'motivo': reason}
                response = self.client.post(
                    self.revoke_url(self.active_skill), payload, format='json'
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['error']['code'], 'INVALID_REASON')

            assignment.activa = False
            assignment.save(update_fields=['activa'])
            with self.subTest(command='reactivate', reason=reason):
                payload = {} if reason is None else {'motivo': reason}
                response = self.client.post(
                    self.reactivate_url(self.active_skill),
                    payload,
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.data['error']['code'], 'INVALID_REASON')
            assignment.activa = True
            assignment.save(update_fields=['activa'])

        assignment.refresh_from_db()
        self.assertTrue(assignment.activa)
        self.assertFalse(Auditoria.objects.filter(
            tabla=PERSONAL_SKILL_AUDIT_TABLE,
            valor_nuevo__event__in=(
                PERSONAL_SKILL_ASSIGNED,
                PERSONAL_SKILL_REVOKED,
                PERSONAL_SKILL_REACTIVATED,
            ),
        ).exists())

    def test_missing_targets_and_inactive_skill_reactivation_are_rejected(self):
        self.authenticate()
        missing_skill = self.client.post(
            self.assign_url(),
            {'habilidad_id': 999999, 'motivo': self.reason},
            format='json',
        )
        missing_personal = self.client.post(
            reverse('personal-asignar-habilidad', args=[999999]),
            {'habilidad_id': self.active_skill.pk, 'motivo': self.reason},
            format='json',
        )
        inactive_assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.inactive_skill,
            activa=False,
        )
        inactive_reactivation = self.client.post(
            self.reactivate_url(self.inactive_skill),
            {'motivo': self.reason},
            format='json',
        )

        for response in (missing_skill, missing_personal):
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(
                response.data['error']['code'],
                'SKILL_OR_PERSONAL_NOT_FOUND',
            )
        self.assertEqual(
            inactive_reactivation.status_code,
            status.HTTP_409_CONFLICT,
        )
        inactive_assignment.refresh_from_db()
        self.assertFalse(inactive_assignment.activa)

    def test_inactive_catalog_skill_can_still_be_revoked(self):
        assignment = PersonalHabilidad.objects.create(
            personal=self.personal,
            habilidad=self.inactive_skill,
            activa=True,
        )
        self.authenticate()

        response = self.client.post(
            self.revoke_url(self.inactive_skill),
            {'motivo': 'Revocación preventiva de catálogo inactivo'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment.refresh_from_db()
        self.assertFalse(assignment.activa)

    def test_anonymous_is_unauthorized(self):
        self.assertEqual(self.client.get(self.skills_url()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_audit_failure_rolls_back_assignment(self):
        with patch('gestion.personal_skill_services.Auditoria.objects.create', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                assign_skill(
                    actor=self.actor,
                    personal_id=self.personal.pk,
                    skill_id=self.active_skill.pk,
                    reason=self.reason,
                )
        self.assertFalse(PersonalHabilidad.objects.filter(
            personal=self.personal, habilidad=self.active_skill
        ).exists())
