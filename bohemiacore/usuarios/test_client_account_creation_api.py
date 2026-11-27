from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class ClientAccountCreationApiTests(APITestCase):
    password = 'Temporal!Cliente2026'

    def setUp(self):
        self.permission = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='create_walkin_client',
        )
        self.actor = self.create_user('client-api-actor@test.com')
        self.actor.user_permissions.add(self.permission)
        self.url = reverse('admin-client-account-create')

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='ActorPassword!2026',
            **extra_fields,
        )

    def payload(self, **overrides):
        values = {
            'first_name': 'Ana',
            'last_name': 'Pérez',
            'email': 'api-client@test.com',
            'password_temporal': self.password,
            'telefono': '1122334455',
            'zona': 'Centro',
            'motivo': 'Alta presencial en recepción',
        }
        values.update(overrides)
        return values

    def post(self, payload=None):
        return self.client.post(
            self.url,
            payload if payload is not None else self.payload(),
            format='json',
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def test_valid_creation_returns_201_without_secrets(self):
        self.authenticate()

        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['created'])
        self.assertEqual(response.data['email'], 'api-client@test.com')
        self.assertEqual(response.data['rol'], BusinessRole.CLIENTE)
        self.assertTrue(response.data['usuario_activo'])
        self.assertNotIn('password', str(response.data).lower())
        user = Usuario.objects.get(pk=response.data['usuario_id'])
        cliente = Cliente.objects.get(pk=response.data['cliente_id'])
        self.assertNotIn(user.password, str(response.data))
        self.assertEqual(cliente.usuario, user)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertTrue(user.check_password(self.password))

    def test_unauthenticated_request_returns_401(self):
        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(
            Usuario.objects.filter(email='api-client@test.com').exists()
        )

    def test_permission_is_required_without_staff_shortcut(self):
        actors = (
            self.create_user('api-client-denied@test.com'),
            self.create_user('api-client-staff-only@test.com', is_staff=True),
        )

        for index, actor in enumerate(actors):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.post(
                    self.payload(email=f'api-denied-{index}@test.com')
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'PERMISSION_DENIED',
                )

    def test_duplicate_email_returns_stable_conflict(self):
        self.create_user('API-CLIENT@test.com')
        self.authenticate()

        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'EMAIL_ALREADY_EXISTS',
        )

    def test_invalid_password_reason_and_payload_return_400(self):
        self.authenticate()
        requests = (
            (
                self.payload(
                    email='weak-password@test.com',
                    password_temporal='123',
                ),
                'INVALID_PASSWORD',
            ),
            (
                self.payload(email='invalid-reason@test.com', motivo=' '),
                'INVALID_REASON',
            ),
            (
                {
                    key: value
                    for key, value in self.payload(
                        email='missing-name@test.com'
                    ).items()
                    if key != 'first_name'
                },
                'INVALID_PAYLOAD',
            ),
        )

        for payload, expected_code in requests:
            with self.subTest(expected_code=expected_code):
                response = self.post(payload)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    expected_code,
                )

    def test_sensitive_and_domain_fields_are_rejected(self):
        self.authenticate()
        forbidden_fields = (
            ('is_staff', True),
            ('is_superuser', True),
            ('is_active', False),
            ('groups', [1]),
            ('user_permissions', [1]),
            ('role', BusinessRole.ADMINISTRADOR),
            ('business_role', BusinessRole.ADMINISTRADOR),
            ('cliente_id', 99),
            ('personal', 99),
            ('tipo_cabello', 1),
            ('diagnostico', {'estado': 'x'}),
        )

        for field, value in forbidden_fields:
            with self.subTest(field=field):
                payload = self.payload(
                    email=f'{field.replace("_", "-")}@test.com'
                )
                payload[field] = value
                response = self.post(payload)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'INVALID_PAYLOAD',
                )
                self.assertIn(field, response.data['error']['fields'])

        self.assertFalse(
            Usuario.objects.filter(email__contains='@test.com').exclude(
                pk=self.actor.pk
            ).exists()
        )
