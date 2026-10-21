from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Usuario


class InactiveUserLoginTests(APITestCase):
    password = 'StrongTestPass123!'

    def create_user(self, email, *, is_active=True):
        return Usuario.objects.create_user(
            email=email,
            password=self.password,
            is_active=is_active,
        )

    def credentials(self, email):
        return {'email': email, 'password': self.password}

    def test_custom_login_rejects_inactive_user(self):
        user = self.create_user(
            'inactive-custom-login@test.com',
            is_active=False,
        )

        response = self.client.post(
            reverse('login'),
            self.credentials(user.email),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)

    def test_standard_jwt_endpoint_rejects_inactive_user(self):
        user = self.create_user(
            'inactive-standard-login@test.com',
            is_active=False,
        )

        response = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(user.email),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)

    def test_existing_access_tokens_are_rejected_after_deactivation(self):
        user = self.create_user('existing-token@test.com')
        pair = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(user.email),
            format='json',
        )
        self.assertEqual(pair.status_code, status.HTTP_200_OK)

        Usuario.objects.filter(pk=user.pk).update(is_active=False)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {pair.data['access']}"
        )

        protected_response = self.client.get(reverse('perfil'))

        self.assertEqual(
            protected_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_existing_refresh_token_is_rejected_after_deactivation(self):
        user = self.create_user('existing-refresh@test.com')
        pair = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(user.email),
            format='json',
        )
        self.assertEqual(pair.status_code, status.HTTP_200_OK)
        Usuario.objects.filter(pk=user.pk).update(is_active=False)

        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': pair.data['refresh']},
            format='json',
        )

        self.assertEqual(
            refresh_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertNotIn('access', refresh_response.data)
