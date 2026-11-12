import os as _os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


_TEST_DATABASE_NAME = _os.environ.get(
    'BH_TEST_DB_NAME',
    'test_bohemia_hair_bh060',
)
if not _TEST_DATABASE_NAME.startswith('test_'):
    raise ImproperlyConfigured(
        'BH_TEST_DB_NAME debe comenzar con "test_" para impedir el uso '
        'accidental de una base de desarrollo o producción.'
    )

DATABASES['default']['TEST'] = {'NAME': _TEST_DATABASE_NAME}  # noqa: F405
TEST_RUNNER = 'bohemiacore.test_runner.StablePostgresTestRunner'
