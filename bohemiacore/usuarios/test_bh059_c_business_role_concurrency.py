from concurrent.futures import ThreadPoolExecutor
import json
import threading

from django.contrib.auth.models import Group, Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gestion.models import Auditoria, Personal
from usuarios.access_services import (
    ACCOUNT_DEACTIVATED_EVENT,
    ACCOUNT_DEACTIVATION_AUDIT_TABLE,
    ACCOUNT_DEACTIVATION_SOURCE,
    LastActiveAdministrator,
    LastActiveAdministratorRoleChange,
    ROLE_AUDIT_EVENT,
    ROLE_AUDIT_SOURCE,
    ROLE_AUDIT_TABLE,
    change_administrative_business_role,
    deactivate_account,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    build_business_role_audit_metadata,
    get_business_roles,
)


class AdministrativeBusinessRoleConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')

        # TransactionTestCase flushes data-migration rows between methods.
        for role in BusinessRole.ALL:
            Group.objects.get_or_create(name=role)

        self.actor = Usuario.objects.create_user(
            email='role-race-manager@test.com',
            password='RoleRace!2026',
        )
        self.actor.user_permissions.add(
            self.permission(BusinessPermission.MANAGE_USERS),
            self.permission(BusinessPermission.ASSIGN_ROLES),
        )
        self.first_admin = self.create_administrator(
            'role-race-first@test.com'
        )
        self.second_admin = self.create_administrator(
            'role-race-second@test.com'
        )

    @staticmethod
    def permission(code):
        app_label, codename = code.split('.', 1)
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )

    @staticmethod
    def create_administrator(email):
        user = Usuario.objects.create_user(
            email=email,
            password='RoleRace!2026',
        )
        Cliente.objects.create(usuario=user)
        user.groups.add(Group.objects.get(name=BusinessRole.ADMINISTRADOR))
        return user

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
            return [future.result(timeout=timeout) for future in futures]

    def demotion_worker(
        self,
        target_id,
        reason='Degradación administrativa concurrente',
        target_role=BusinessRole.CLIENTE,
    ):
        def operation():
            try:
                result = change_administrative_business_role(
                    actor=Usuario.objects.get(pk=self.actor.pk),
                    target_user=Usuario.objects.get(pk=target_id),
                    target_role=target_role,
                    reason=reason,
                )
                return {
                    'status': 'changed' if result.changed else 'noop',
                    'operation': 'role_change',
                    'target_id': target_id,
                    'target_role': target_role,
                    'reason': reason,
                    'audit_id': result.audit_id,
                }
            except LastActiveAdministratorRoleChange:
                return {
                    'status': 'last_admin',
                    'operation': 'role_change',
                    'target_id': target_id,
                    'target_role': target_role,
                    'reason': reason,
                    'audit_id': None,
                }

        return operation

    def deactivation_worker(
        self,
        target_id,
        reason='Desactivación administrativa concurrente',
    ):
        def operation():
            try:
                result = deactivate_account(
                    actor=Usuario.objects.get(pk=self.actor.pk),
                    target_user=Usuario.objects.get(pk=target_id),
                    reason=reason,
                )
                return {
                    'status': 'changed' if result.changed else 'noop',
                    'operation': 'account_deactivation',
                    'target_id': target_id,
                    'reason': reason,
                    'audit_id': result.audit_id,
                }
            except LastActiveAdministrator:
                return {
                    'status': 'last_admin',
                    'operation': 'account_deactivation',
                    'target_id': target_id,
                    'reason': reason,
                    'audit_id': None,
                }

        return operation

    def assert_audit_has_no_secrets(self, audit):
        payload = {
            'before': audit.valor_anterior,
            'after': audit.valor_nuevo,
        }
        serialized = json.dumps(payload).lower()
        self.assertNotIn('rolerace!2026', serialized)
        payload_keys = set(audit.valor_anterior) | set(audit.valor_nuevo)
        self.assertTrue({
            'password',
            'password_hash',
            'jwt',
            'jti',
            'access_token',
            'refresh_token',
            'token',
        }.isdisjoint(payload_keys))

    def role_audits(self):
        return Auditoria.objects.filter(
            tabla=ROLE_AUDIT_TABLE,
            valor_nuevo__event=ROLE_AUDIT_EVENT,
        )

    def deactivation_audits(self):
        return Auditoria.objects.filter(
            tabla=ACCOUNT_DEACTIVATION_AUDIT_TABLE,
            valor_nuevo__event=ACCOUNT_DEACTIVATED_EVENT,
        )

    def assert_role_change_audit(self, outcome, previous_role):
        audit = self.role_audits().get(pk=outcome['audit_id'])
        self.assertEqual(audit.usuario_id, self.actor.pk)
        self.assertEqual(audit.registro_id, outcome['target_id'])
        self.assertEqual(audit.valor_anterior['event'], ROLE_AUDIT_EVENT)
        self.assertEqual(
            audit.valor_anterior['target_user_id'],
            outcome['target_id'],
        )
        self.assertEqual(
            audit.valor_anterior['business_role'],
            previous_role,
        )
        self.assertEqual(audit.valor_nuevo['event'], ROLE_AUDIT_EVENT)
        self.assertEqual(audit.valor_nuevo['source'], ROLE_AUDIT_SOURCE)
        self.assertEqual(audit.valor_nuevo['actor_id'], self.actor.pk)
        self.assertEqual(
            audit.valor_nuevo['target_user_id'],
            outcome['target_id'],
        )
        self.assertEqual(audit.valor_nuevo['previous_role'], previous_role)
        self.assertEqual(
            audit.valor_nuevo['new_role'],
            outcome['target_role'],
        )
        self.assertEqual(audit.valor_nuevo['reason'], outcome['reason'])
        self.assertNotIn('operation_id', audit.valor_nuevo)
        for key, value in build_business_role_audit_metadata(
            previous_role=previous_role,
            new_role=outcome['target_role'],
        ).items():
            self.assertEqual(audit.valor_nuevo[key], value)
        self.assert_audit_has_no_secrets(audit)

    def assert_deactivation_audit(self, outcome, current_role):
        audit = self.deactivation_audits().get(pk=outcome['audit_id'])
        self.assertEqual(audit.usuario_id, self.actor.pk)
        self.assertEqual(audit.registro_id, outcome['target_id'])
        self.assertEqual(
            audit.valor_anterior['event'],
            ACCOUNT_DEACTIVATED_EVENT,
        )
        self.assertTrue(audit.valor_anterior['active'])
        self.assertEqual(
            audit.valor_anterior['target_user_id'],
            outcome['target_id'],
        )
        self.assertEqual(
            audit.valor_nuevo['source'],
            ACCOUNT_DEACTIVATION_SOURCE,
        )
        self.assertEqual(audit.valor_nuevo['actor_id'], self.actor.pk)
        self.assertEqual(
            audit.valor_nuevo['target_user_id'],
            outcome['target_id'],
        )
        self.assertTrue(audit.valor_nuevo['previous_active'])
        self.assertFalse(audit.valor_nuevo['current_active'])
        self.assertEqual(
            audit.valor_nuevo['current_business_role'],
            current_role,
        )
        self.assertEqual(audit.valor_nuevo['reason'], outcome['reason'])
        self.assertNotIn('operation_id', audit.valor_nuevo)
        self.assert_audit_has_no_secrets(audit)

    def active_administrators(self):
        return [
            user
            for user in Usuario.objects.filter(
                is_active=True,
                is_superuser=False,
                groups__name=BusinessRole.ADMINISTRADOR,
            ).distinct()
            if get_business_roles(user) == (BusinessRole.ADMINISTRADOR,)
        ]

    def test_two_concurrent_demotions_preserve_one_active_administrator(self):
        results = self.run_concurrently(
            self.demotion_worker(self.first_admin.pk),
            self.demotion_worker(self.second_admin.pk),
        )

        self.assertCountEqual(
            [result['status'] for result in results],
            ['changed', 'last_admin'],
        )
        self.assertEqual(len(self.active_administrators()), 1)
        changed = next(
            result for result in results if result['status'] == 'changed'
        )
        rejected = next(
            result for result in results if result['status'] == 'last_admin'
        )
        self.assertEqual(self.role_audits().count(), 1)
        self.assertEqual(
            set(self.role_audits().values_list('pk', flat=True)),
            {changed['audit_id']},
        )
        self.assert_role_change_audit(changed, BusinessRole.ADMINISTRADOR)
        self.assertFalse(
            self.role_audits().filter(
                registro_id=rejected['target_id']
            ).exists()
        )
        self.assertEqual(
            get_business_roles(Usuario.objects.get(pk=changed['target_id'])),
            (BusinessRole.CLIENTE,),
        )
        self.assertEqual(
            get_business_roles(Usuario.objects.get(pk=rejected['target_id'])),
            (BusinessRole.ADMINISTRADOR,),
        )

    def test_concurrent_demotion_and_deactivation_preserve_one_active_admin(self):
        results = self.run_concurrently(
            self.demotion_worker(self.first_admin.pk),
            self.deactivation_worker(self.second_admin.pk),
        )

        self.assertCountEqual(
            [result['status'] for result in results],
            ['changed', 'last_admin'],
        )
        self.assertEqual(len(self.active_administrators()), 1)
        changed = next(
            result for result in results if result['status'] == 'changed'
        )
        rejected = next(
            result for result in results if result['status'] == 'last_admin'
        )
        semantic_audits = list(self.role_audits()) + list(
            self.deactivation_audits()
        )
        self.assertEqual(len(semantic_audits), 1)
        self.assertEqual(semantic_audits[0].pk, changed['audit_id'])
        if changed['operation'] == 'role_change':
            self.assert_role_change_audit(changed, BusinessRole.ADMINISTRADOR)
            self.assertEqual(
                get_business_roles(
                    Usuario.objects.get(pk=changed['target_id'])
                ),
                (BusinessRole.CLIENTE,),
            )
        else:
            self.assert_deactivation_audit(
                changed,
                BusinessRole.ADMINISTRADOR,
            )
            self.assertFalse(
                Usuario.objects.get(pk=changed['target_id']).is_active
            )
        rejected_events = (
            self.role_audits()
            if rejected['operation'] == 'role_change'
            else self.deactivation_audits()
        )
        self.assertFalse(
            rejected_events.filter(registro_id=rejected['target_id']).exists()
        )
        rejected_user = Usuario.objects.get(pk=rejected['target_id'])
        self.assertTrue(rejected_user.is_active)
        self.assertEqual(
            get_business_roles(rejected_user),
            (BusinessRole.ADMINISTRADOR,),
        )

    def test_same_concurrent_role_change_has_one_mutation_and_one_noop(self):
        target = Usuario.objects.create_user(
            email='same-role-race-target@test.com',
            password='RoleRace!2026',
        )
        Cliente.objects.create(usuario=target)
        Personal.objects.create(
            usuario=target,
            nombre='Cambio',
            apellido='Concurrente',
            rol='asistente',
            activo=True,
        )
        target.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))

        results = self.run_concurrently(
            self.demotion_worker(
                target.pk,
                reason='Primer comando concurrente de rol',
                target_role=BusinessRole.PROFESIONAL,
            ),
            self.demotion_worker(
                target.pk,
                reason='Segundo comando concurrente de rol',
                target_role=BusinessRole.PROFESIONAL,
            ),
        )

        self.assertCountEqual(
            [result['status'] for result in results],
            ['changed', 'noop'],
        )
        changed = next(
            result for result in results if result['status'] == 'changed'
        )
        noop = next(result for result in results if result['status'] == 'noop')
        self.assertIsNone(noop['audit_id'])
        self.assertEqual(
            get_business_roles(Usuario.objects.get(pk=target.pk)),
            (BusinessRole.PROFESIONAL,),
        )
        self.assertEqual(self.role_audits().count(), 1)
        self.assertEqual(self.role_audits().get().pk, changed['audit_id'])
        self.assert_role_change_audit(changed, BusinessRole.EMPLEADO)

    def test_two_concurrent_deactivations_have_one_mutation_and_one_noop(self):
        target = Usuario.objects.create_user(
            email='same-deactivation-race-target@test.com',
            password='RoleRace!2026',
        )
        Cliente.objects.create(usuario=target)
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))

        results = self.run_concurrently(
            self.deactivation_worker(
                target.pk,
                reason='Primera desactivación concurrente',
            ),
            self.deactivation_worker(
                target.pk,
                reason='Segunda desactivación concurrente',
            ),
        )

        self.assertCountEqual(
            [result['status'] for result in results],
            ['changed', 'noop'],
        )
        changed = next(
            result for result in results if result['status'] == 'changed'
        )
        noop = next(result for result in results if result['status'] == 'noop')
        self.assertIsNone(noop['audit_id'])
        self.assertFalse(Usuario.objects.get(pk=target.pk).is_active)
        self.assertEqual(self.deactivation_audits().count(), 1)
        self.assertEqual(
            self.deactivation_audits().get().pk,
            changed['audit_id'],
        )
        self.assert_deactivation_audit(changed, BusinessRole.CLIENTE)
