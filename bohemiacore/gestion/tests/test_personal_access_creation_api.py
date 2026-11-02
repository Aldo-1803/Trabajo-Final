import json

from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Personal
from usuarios.models import Usuario
from usuarios.roles import BusinessRole, get_business_role


class PersonalAccessCreationActionTests(APITestCase):
    strong_password = 'Temporary!Access2026'

    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('api-access-create-actor@test.com')
        self.actor.user_permissions.add(
            self.manage_personal,
            self.assign_roles,
        )

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def create_personal(self, suffix, **overrides):
        values = {
            'nombre': f'Nombre {suffix}',
            'apellido': 'API Acceso',
            'rol': 'asistente',
            'activo': True,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def url(self, personal_id):
        return reverse('personal-crear-acceso', args=[personal_id])

    def payload(self, **overrides):
        values = {
            'email': 'new-personal-access@test.com',
            'password_temporal': self.strong_password,
            'role': BusinessRole.EMPLEADO,
            'motivo': 'Alta de acceso laboral desde API',
        }
        values.update(overrides)
        return values

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def test_valid_creation_returns_201_without_credentials(self):
        personal = self.create_personal('valid')
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['created'], True)
        self.assertEqual(response.data['personal_id'], personal.pk)
        self.assertEqual(response.data['email'], 'new-personal-access@test.com')
        self.assertEqual(response.data['rol'], BusinessRole.EMPLEADO)
        self.assertTrue(response.data['personal_activo'])
        self.assertTrue(response.data['usuario_activo'])
        serialized_response = json.dumps(response.data).lower()
        self.assertNotIn('password', serialized_response)
        self.assertNotIn('hash', serialized_response)

        personal.refresh_from_db()
        self.assertEqual(personal.usuario_id, response.data['usuario_id'])
        self.assertEqual(
            get_business_role(personal.usuario),
            BusinessRole.EMPLEADO,
        )

    def test_invalid_payload_returns_400(self):
        personal = self.create_personal('invalid-payload')
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            {'email': 'not-an-email'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PAYLOAD')

    def test_weak_password_returns_stable_400(self):
        personal = self.create_personal('weak-password')
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            self.payload(password_temporal='123'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PASSWORD')
        self.assertNotIn('123', json.dumps(response.data))

    def test_client_role_returns_stable_400(self):
        personal = self.create_personal('client-role')
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            self.payload(role=BusinessRole.CLIENTE),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_ROLE')

    def test_invalid_reason_returns_stable_400(self):
        personal = self.create_personal('invalid-reason')
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            self.payload(motivo=' '),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_REASON')

    def test_unauthenticated_actor_returns_401(self):
        personal = self.create_personal('anonymous')

        response = self.client.post(
            self.url(personal.pk),
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_actor_without_both_permissions_returns_403(self):
        for index, permission in enumerate(
            (None, self.manage_personal, self.assign_roles),
            start=1,
        ):
            with self.subTest(permission=permission):
                actor = self.create_user(f'api-access-denied-{index}@test.com')
                if permission is not None:
                    actor.user_permissions.add(permission)
                personal = self.create_personal(f'denied-{index}')
                self.authenticate(actor)

                response = self.client.post(
                    self.url(personal.pk),
                    self.payload(email=f'denied-{index}@test.com'),
                    format='json',
                )

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(
                    response.data['error']['code'],
                    'PERMISSION_DENIED',
                )

    def test_nonexistent_personal_returns_stable_404(self):
        self.authenticate()

        response = self.client.post(
            self.url(999999),
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'PERSONAL_NOT_FOUND')

    def test_existing_email_returns_409_and_does_not_link(self):
        existing = self.create_user('existing-api-access@test.com')
        personal = self.create_personal('existing-email')
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            self.payload(email='EXISTING-API-ACCESS@Test.com'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'EMAIL_ALREADY_EXISTS')
        personal.refresh_from_db()
        self.assertIsNone(personal.usuario_id)
        self.assertEqual(
            Usuario.objects.filter(email__iexact=existing.email).count(),
            1,
        )

    def test_personal_with_access_returns_409(self):
        user = self.create_user('already-linked-api@test.com')
        personal = self.create_personal('already-linked', usuario=user)
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'PERSONAL_ALREADY_HAS_ACCESS',
        )

    def test_inactive_personal_returns_409_without_reactivation(self):
        personal = self.create_personal('inactive', activo=False)
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'PERSONAL_INACTIVE')
        personal.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertIsNone(personal.usuario_id)

    def test_sensitive_and_unexpected_fields_are_rejected(self):
        personal = self.create_personal('sensitive-fields')
        self.authenticate()
        payload = self.payload(
            is_staff=True,
            is_superuser=True,
            is_active=False,
            groups=[],
            user_permissions=[],
            cliente=True,
            personal_id=personal.pk,
            skills=['color'],
        )

        response = self.client.post(
            self.url(personal.pk),
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PAYLOAD')
        self.assertSetEqual(
            set(response.data['error']['fields']),
            set(payload) - {'email', 'password_temporal', 'role', 'motivo'},
        )
        personal.refresh_from_db()
        self.assertIsNone(personal.usuario_id)
