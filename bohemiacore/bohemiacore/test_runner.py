from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, transaction
from django.test import TransactionTestCase
from django.test.runner import DiscoverRunner

from gestion.models import Habilidad
from usuarios.roles import ROLE_BASE_PERMISSIONS


TECHNICAL_SKILLS = {
    'DIAGNOSTICO': 'Diagnóstico',
    'LAVADO': 'Lavado',
    'COLORACION': 'Coloración',
}


def assert_is_configured_test_database(connection):
    """Refuse seed maintenance unless Django is connected to its test DB."""
    configured_name = connection.settings_dict.get('TEST', {}).get('NAME')
    actual_name = connection.settings_dict.get('NAME')
    if (
        not configured_name
        or not configured_name.startswith('test_')
        or actual_name != configured_name
    ):
        raise ImproperlyConfigured(
            'La restauración de seeds sólo puede ejecutarse sobre la base de '
            'pruebas explícita cuyo nombre comienza con "test_". '
            f'Actual={actual_name!r}; TEST.NAME={configured_name!r}.'
        )


def restore_test_seeds(alias='default'):
    """Restore only the canonical role and skill seeds in a verified test DB."""
    connection = connections[alias]
    assert_is_configured_test_database(connection)

    permission_labels = {
        label
        for labels in ROLE_BASE_PERMISSIONS.values()
        for label in labels
    }
    permissions = Permission.objects.using(alias).filter(
        content_type__app_label__in={
            label.split('.', 1)[0] for label in permission_labels
        },
        codename__in={label.split('.', 1)[1] for label in permission_labels},
    ).select_related('content_type')
    permissions_by_label = {
        f'{permission.content_type.app_label}.{permission.codename}': permission
        for permission in permissions
        if f'{permission.content_type.app_label}.{permission.codename}'
        in permission_labels
    }
    missing = permission_labels - permissions_by_label.keys()
    if missing:
        raise RuntimeError(
            'Faltan permisos migrados requeridos por ROLE_BASE_PERMISSIONS: '
            + ', '.join(sorted(missing))
        )

    with transaction.atomic(using=alias):
        for role, labels in ROLE_BASE_PERMISSIONS.items():
            group, _ = Group.objects.using(alias).get_or_create(name=role)
            group.permissions.set(
                [permissions_by_label[label] for label in labels]
            )

        for code, name in TECHNICAL_SKILLS.items():
            Habilidad.objects.using(alias).update_or_create(
                code=code,
                defaults={
                    'nombre': name,
                    'descripcion': '',
                    'activa': True,
                },
            )


def _install_transaction_seed_restoration():
    """Restore data-migration seeds after every TransactionTestCase flush."""
    if getattr(TransactionTestCase, '_bh060_seed_restoration', False):
        return

    original_teardown = TransactionTestCase._fixture_teardown

    def fixture_teardown_with_seed_restoration(test_case):
        original_teardown(test_case)
        for alias in test_case._databases_names(include_mirrors=False):
            restore_test_seeds(alias)

    TransactionTestCase._fixture_teardown = (
        fixture_teardown_with_seed_restoration
    )
    TransactionTestCase._bh060_seed_restoration = True


class StablePostgresTestRunner(DiscoverRunner):
    """Keep PostgreSQL data-migration seeds reproducible, including --keepdb."""

    def build_suite(self, *args, **kwargs):
        _install_transaction_seed_restoration()
        return super().build_suite(*args, **kwargs)

    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        restore_test_seeds()
        return old_config

    def run_suite(self, suite, **kwargs):
        try:
            return super().run_suite(suite, **kwargs)
        finally:
            if self.keepdb:
                restore_test_seeds()
