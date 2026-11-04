from concurrent.futures import ThreadPoolExecutor
import threading

from django.contrib.auth.models import Group, Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from usuarios.access_services import (
    LastActiveAdministrator,
    LastActiveAdministratorRoleChange,
    change_administrative_business_role,
    deactivate_account,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessPermission, BusinessRole, get_business_roles


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

    def demotion_worker(self, target_id):
        def operation():
            try:
                result = change_administrative_business_role(
                    actor=Usuario.objects.get(pk=self.actor.pk),
                    target_user=Usuario.objects.get(pk=target_id),
                    target_role=BusinessRole.CLIENTE,
                    reason='Degradación administrativa concurrente',
                )
                return 'changed' if result.changed else 'noop'
            except LastActiveAdministratorRoleChange:
                return 'last_admin'

        return operation

    def deactivation_worker(self, target_id):
        def operation():
            try:
                result = deactivate_account(
                    actor=Usuario.objects.get(pk=self.actor.pk),
                    target_user=Usuario.objects.get(pk=target_id),
                    reason='Desactivación administrativa concurrente',
                )
                return 'changed' if result.changed else 'noop'
            except LastActiveAdministrator:
                return 'last_admin'

        return operation

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

        self.assertCountEqual(results, ['changed', 'last_admin'])
        self.assertEqual(len(self.active_administrators()), 1)

    def test_concurrent_demotion_and_deactivation_preserve_one_active_admin(self):
        results = self.run_concurrently(
            self.demotion_worker(self.first_admin.pk),
            self.deactivation_worker(self.second_admin.pk),
        )

        self.assertCountEqual(results, ['changed', 'last_admin'])
        self.assertEqual(len(self.active_administrators()), 1)
