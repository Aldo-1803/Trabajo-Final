from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.access_services import reactivate_account
from usuarios.models import Cliente
from usuarios.models import Usuario
from usuarios.roles import BusinessRole


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

    def test_valid_reactivation_restores_custom_and_standard_login(self):
        target = self.create_user(
            'reactivated-login@test.com',
            is_active=False,
        )
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        Cliente.objects.create(usuario=target)
        actor = self.create_user('reactivated-login-actor@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        ))

        before = self.client.post(
            reverse('login'),
            self.credentials(target.email),
            format='json',
        )
        self.assertEqual(before.status_code, status.HTTP_401_UNAUTHORIZED)

        result = reactivate_account(
            actor,
            target,
            'Reactivacion para recuperar acceso',
        )

        self.assertTrue(result.changed)
        custom_login = self.client.post(
            reverse('login'),
            self.credentials(target.email),
            format='json',
        )
        standard_login = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(target.email),
            format='json',
        )
        self.assertEqual(custom_login.status_code, status.HTTP_200_OK)
        self.assertEqual(standard_login.status_code, status.HTTP_200_OK)
        self.assertIn('access', custom_login.data)
        self.assertIn('access', standard_login.data)
