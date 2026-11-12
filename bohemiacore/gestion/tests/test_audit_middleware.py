from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from gestion.middleware import (
    AuditoriaMiddleware,
    _thread_locals,
    get_current_request,
    get_current_user,
)


class AuditoriaMiddlewareContextTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/audit-context-test/')
        self.request.user = AnonymousUser()

    def tearDown(self):
        for attribute in ('user', 'request'):
            if hasattr(_thread_locals, attribute):
                delattr(_thread_locals, attribute)

    def test_context_is_available_during_request_and_cleared_after_response(self):
        def get_response(request):
            self.assertIs(get_current_request(), request)
            self.assertIsNone(get_current_user())
            return object()

        response = AuditoriaMiddleware(get_response)(self.request)

        self.assertIsNotNone(response)
        self.assertFalse(hasattr(_thread_locals, 'user'))
        self.assertFalse(hasattr(_thread_locals, 'request'))

    def test_context_is_cleared_when_the_response_handler_raises(self):
        def get_response(request):
            self.assertIs(get_current_request(), request)
            raise RuntimeError('fallo controlado')

        with self.assertRaisesRegex(RuntimeError, 'fallo controlado'):
            AuditoriaMiddleware(get_response)(self.request)

        self.assertFalse(hasattr(_thread_locals, 'user'))
        self.assertFalse(hasattr(_thread_locals, 'request'))
