from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Personal
from usuarios.administrator_account_services import (
    AdministratorAccountCreationConflict,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class AdministratorAccountCreationApiTests(APITestCase):
    password = 'Temporal!Admin2026'

    def setUp(self):
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('admin-api-actor@test.com')
        self.actor.user_permissions.add(
            self.manage_users,
            self.assign_roles,
        )
        self.url = reverse('admin-administrator-account-create')

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
            'email': 'ana.admin@example.com',
            'password_temporal': self.password,
            'motivo': 'Incorporación como administradora',
        }
        values.update(overrides)
        return values

    def test_valid_creation_returns_201_without_credentials(self):
        self.client.force_authenticate(user=self.actor)

        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = Usuario.objects.get(pk=response.data['usuario_id'])
        self.assertEqual(response.data, {
            'created': True,
            'usuario_id': user.pk,
            'email': 'ana.admin@example.com',
            'rol': BusinessRole.ADMINISTRADOR,
            'usuario_activo': True,
        })
        self.assertNotIn('password', response.data)
        self.assertNotIn('password_temporal', response.data)
        self.assertNotIn('token', response.data)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(
            get_business_roles(user),
            (BusinessRole.ADMINISTRADOR,),
        )
        self.assertFalse(Cliente.objects.filter(usuario=user).exists())
        self.assertFalse(Personal.objects.filter(usuario=user).exists())

    def test_invalid_payload_password_and_reason_return_400(self):
        self.client.force_authenticate(user=self.actor)
        cases = (
            ({'first_name': ''}, 'INVALID_PAYLOAD'),
            ({'password_temporal': '123'}, 'INVALID_PASSWORD'),
            ({'motivo': ''}, 'INVALID_REASON'),
        )

        for overrides, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                response = self.client.post(
                    self.url,
                    self.payload(**overrides),
                    format='json',
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    expected_code,
                )

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_actor_requires_both_permissions_and_staff_is_not_enough(self):
        actors = (
            self.create_user('no-permissions@test.com'),
            self.create_user('manage-only@test.com'),
            self.create_user('assign-only@test.com'),
            self.create_user('staff-only@test.com', is_staff=True),
        )
        actors[1].user_permissions.add(self.manage_users)
        actors[2].user_permissions.add(self.assign_roles)

        for index, actor in enumerate(actors, start=1):
            with self.subTest(actor=actor.email):
                self.client.force_authenticate(user=actor)
                response = self.client.post(
                    self.url,
                    self.payload(email=f'denied-{index}@test.com'),
                    format='json',
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'PERMISSION_DENIED',
                )

    def test_existing_email_case_insensitive_returns_409(self):
        self.create_user('Existing.Admin@Example.com')
        self.client.force_authenticate(user=self.actor)

        response = self.client.post(
            self.url,
            self.payload(email='existing.admin@EXAMPLE.COM'),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'EMAIL_ALREADY_EXISTS',
        )

    def test_creation_conflict_returns_safe_409(self):
        self.client.force_authenticate(user=self.actor)

        with patch(
            'usuarios.views.create_administrator_account',
            side_effect=AdministratorAccountCreationConflict(
                'internal database detail'
            ),
        ):
            response = self.client.post(
                self.url,
                self.payload(),
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'ADMIN_ACCOUNT_CREATION_CONFLICT',
        )
        self.assertNotIn(
            'internal database detail',
            response.data['error']['detail'],
        )

    def test_sensitive_role_profile_and_permission_fields_are_rejected(self):
        self.client.force_authenticate(user=self.actor)
        forbidden_fields = {
            'role': BusinessRole.CLIENTE,
            'business_role': BusinessRole.PROFESIONAL,
            'is_staff': True,
            'is_superuser': True,
            'is_active': False,
            'groups': [1],
            'user_permissions': [1],
            'cliente': {},
            'personal': {},
            'usuario_id': 99,
        }

        for field, value in forbidden_fields.items():
            with self.subTest(field=field):
                response = self.client.post(
                    self.url,
                    self.payload(**{field: value}),
                    format='json',
                )
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
            Usuario.objects.filter(email='ana.admin@example.com').exists()
        )
