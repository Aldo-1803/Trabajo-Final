from concurrent.futures import ThreadPoolExecutor
import json
import threading

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gestion.models import Auditoria, Habilidad, Personal, PersonalHabilidad
from gestion.personal_skill_services import (
    PERSONAL_SKILL_ASSIGNED,
    PERSONAL_SKILL_ASSIGN_SOURCE,
    PERSONAL_SKILL_AUDIT_TABLE,
    assign_skill,
)
from usuarios.models import Usuario
from usuarios.roles import BusinessPermission


class PersonalSkillAuditConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Esta carrera requiere PostgreSQL real.')

        self.actor = Usuario.objects.create_user(
            email='skill-race-manager@test.com',
            password='SkillRace!2026',
        )
        app_label, codename = BusinessPermission.MANAGE_SKILLS.split('.', 1)
        self.actor.user_permissions.add(Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        ))
        self.linked_user = Usuario.objects.create_user(
            email='skill-race-target@test.com',
            password='SkillRace!2026',
        )
        self.personal = Personal.objects.create(
            usuario=self.linked_user,
            nombre='Técnica',
            apellido='Concurrente',
            rol='asistente',
            activo=True,
        )
        # StablePostgresTestRunner restores canonical skills after each
        # TransactionTestCase flush. Reuse one instead of creating a row after
        # reset_sequences has reset its PostgreSQL sequence.
        self.skill = Habilidad.objects.get(code='DIAGNOSTICO', activa=True)

    @staticmethod
    def run_concurrently(first, second, timeout=20):
        barrier = threading.Barrier(2)

        def wrapped(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(wrapped, first),
                executor.submit(wrapped, second),
            )
            # An unexpected database error, deadlock or domain exception is
            # propagated and fails the test; no concurrent error is ignored.
            return [future.result(timeout=timeout) for future in futures]

    def assignment_worker(self, reason):
        def operation():
            result = assign_skill(
                actor=Usuario.objects.get(pk=self.actor.pk),
                personal_id=self.personal.pk,
                skill_id=self.skill.pk,
                reason=reason,
            )
            return {
                'status': 'changed' if result.changed else 'noop',
                'event': result.event,
                'assignment_id': result.assignment.pk,
                'reason': reason,
            }

        return operation

    def semantic_audits(self):
        return Auditoria.objects.filter(
            tabla=PERSONAL_SKILL_AUDIT_TABLE,
            valor_nuevo__event=PERSONAL_SKILL_ASSIGNED,
        )

    def test_two_concurrent_assignments_have_one_event_and_one_noop(self):
        results = self.run_concurrently(
            self.assignment_worker('Primera asignación técnica concurrente'),
            self.assignment_worker('Segunda asignación técnica concurrente'),
        )

        self.assertCountEqual(
            [result['status'] for result in results],
            ['changed', 'noop'],
        )
        changed = next(result for result in results if result['status'] == 'changed')
        noop = next(result for result in results if result['status'] == 'noop')
        self.assertEqual(changed['event'], PERSONAL_SKILL_ASSIGNED)
        self.assertIsNone(noop['event'])
        self.assertEqual(changed['assignment_id'], noop['assignment_id'])
        self.assertEqual(
            PersonalHabilidad.objects.filter(
                personal_id=self.personal.pk,
                habilidad_id=self.skill.pk,
                activa=True,
            ).count(),
            1,
        )

        self.assertEqual(self.semantic_audits().count(), 1)
        audit = self.semantic_audits().get()
        self.assertEqual(audit.registro_id, changed['assignment_id'])
        self.assertEqual(audit.usuario_id, self.actor.pk)
        self.assertEqual(audit.valor_anterior['personal_id'], self.personal.pk)
        self.assertEqual(audit.valor_anterior['skill_id'], self.skill.pk)
        self.assertIsNone(audit.valor_anterior['activa'])
        self.assertEqual(audit.valor_nuevo['event'], PERSONAL_SKILL_ASSIGNED)
        self.assertEqual(
            audit.valor_nuevo['source'],
            PERSONAL_SKILL_ASSIGN_SOURCE,
        )
        self.assertEqual(audit.valor_nuevo['actor_id'], self.actor.pk)
        self.assertEqual(audit.valor_nuevo['personal_id'], self.personal.pk)
        self.assertEqual(audit.valor_nuevo['skill_id'], self.skill.pk)
        self.assertIsNone(audit.valor_nuevo['previous_active'])
        self.assertTrue(audit.valor_nuevo['current_active'])
        self.assertEqual(audit.valor_nuevo['reason'], changed['reason'])
        self.assertNotIn('operation_id', audit.valor_nuevo)

        serialized = json.dumps({
            'before': audit.valor_anterior,
            'after': audit.valor_nuevo,
        }).lower()
        for forbidden in (
            'skillrace!2026',
            '"password"',
            'password_hash',
            '"jwt"',
            '"jti"',
            'access_token',
            'refresh_token',
        ):
            self.assertNotIn(forbidden, serialized)
