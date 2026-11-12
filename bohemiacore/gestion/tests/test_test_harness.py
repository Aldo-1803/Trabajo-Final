from types import SimpleNamespace

from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from bohemiacore.test_runner import (
    TECHNICAL_SKILLS,
    assert_is_configured_test_database,
    restore_test_seeds,
)
from gestion.models import Habilidad
from usuarios.roles import BusinessRole, ROLE_BASE_PERMISSIONS


class TestDatabaseSafetyTests(SimpleTestCase):
    @staticmethod
    def connection(actual_name, test_name):
        return SimpleNamespace(settings_dict={
            'NAME': actual_name,
            'TEST': {'NAME': test_name},
        })

    def test_explicit_test_database_is_accepted(self):
        connection = self.connection('test_bohemia', 'test_bohemia')

        assert_is_configured_test_database(connection)

    def test_development_database_is_rejected(self):
        connection = self.connection('bohemia', 'test_bohemia')

        with self.assertRaises(ImproperlyConfigured):
            assert_is_configured_test_database(connection)

    def test_non_test_prefixed_database_is_rejected(self):
        connection = self.connection('bohemia', 'bohemia')

        with self.assertRaises(ImproperlyConfigured):
            assert_is_configured_test_database(connection)


class TestSeedRestorationTests(TestCase):
    def test_restoration_is_idempotent_and_matches_the_current_contract(self):
        Group.objects.filter(name__in=BusinessRole.ALL).delete()
        Habilidad.objects.filter(code__in=TECHNICAL_SKILLS).delete()

        restore_test_seeds()
        restore_test_seeds()

        for role, expected_labels in ROLE_BASE_PERMISSIONS.items():
            group = Group.objects.get(name=role)
            actual_labels = {
                f'{permission.content_type.app_label}.{permission.codename}'
                for permission in group.permissions.select_related(
                    'content_type'
                )
            }
            self.assertSetEqual(actual_labels, set(expected_labels))

        self.assertEqual(
            {
                skill.code: (skill.nombre, skill.descripcion, skill.activa)
                for skill in Habilidad.objects.filter(
                    code__in=TECHNICAL_SKILLS
                )
            },
            {
                code: (name, '', True)
                for code, name in TECHNICAL_SKILLS.items()
            },
        )


class TransactionSeedIsolationTests(TransactionTestCase):
    reset_sequences = True

    def test_a_transaction_test_may_flush_seed_rows(self):
        Group.objects.filter(name__in=BusinessRole.ALL).delete()
        Habilidad.objects.filter(code__in=TECHNICAL_SKILLS).delete()

        self.assertFalse(
            Group.objects.filter(name__in=BusinessRole.ALL).exists()
        )
        self.assertFalse(
            Habilidad.objects.filter(code__in=TECHNICAL_SKILLS).exists()
        )

    def test_b_next_transaction_test_receives_reproducible_seeds(self):
        self.assertSetEqual(
            set(Group.objects.filter(name__in=BusinessRole.ALL).values_list(
                'name', flat=True
            )),
            set(BusinessRole.ALL),
        )
        self.assertSetEqual(
            set(Habilidad.objects.filter(code__in=TECHNICAL_SKILLS).values_list(
                'code', flat=True
            )),
            set(TECHNICAL_SKILLS),
        )
