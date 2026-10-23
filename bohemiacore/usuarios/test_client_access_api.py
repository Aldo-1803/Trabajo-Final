from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessPermission, BusinessRole


class ClientAccessApiTests(APITestCase):
    def setUp(self):
        self.list_url = reverse('cliente-list')
        self.view_permission = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='view_clients',
        )
        self.target_user = self.create_user('target@test.com')
        self.target = Cliente.objects.create(
            usuario=self.target_user,
            zona='Centro',
            numero='1122334455',
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='ClientAccess!2026',
            first_name='Ana',
            last_name='Pérez',
            **extra_fields,
        )

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def detail_url(self, cliente=None):
        return reverse('cliente-detail', args=[(cliente or self.target).pk])

    def test_employee_without_staff_flag_can_list_clients(self):
        actor = self.create_user('employee@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.EMPLEADO)
        self.assertTrue(actor.has_perm(BusinessPermission.VIEW_CLIENTS))
        self.authenticate(actor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['email'], self.target_user.email)

    def test_professional_without_staff_flag_can_list_clients(self):
        actor = self.create_user('professional@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.PROFESIONAL)
        self.authenticate(actor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_administrator_without_staff_flag_can_list_clients(self):
        actor = self.create_user('administrator@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.ADMINISTRADOR)
        self.authenticate(actor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_staff_without_view_clients_is_denied(self):
        actor = self.create_user('staff-only@test.com', is_staff=True)
        self.authenticate(actor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_cannot_list_all_clients(self):
        actor = self.create_user('client@test.com')
        Cliente.objects.create(usuario=actor)
        self.assign_role(actor, BusinessRole.CLIENTE)
        self.authenticate(actor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_request_returns_401(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detail_of_another_client_requires_view_clients(self):
        actor = self.create_user('detail-denied@test.com')
        Cliente.objects.create(usuario=actor)
        self.assign_role(actor, BusinessRole.CLIENTE)
        self.authenticate(actor)

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_view_clients_allows_reading_client_detail(self):
        actor = self.create_user('detail-allowed@test.com')
        actor.user_permissions.add(self.view_permission)
        self.authenticate(actor)

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.target_user.email)

    def test_client_keeps_access_to_own_profile(self):
        actor = self.create_user('own-profile@test.com')
        Cliente.objects.create(usuario=actor, zona='Norte')
        self.assign_role(actor, BusinessRole.CLIENTE)
        self.authenticate(actor)

        response = self.client.get(reverse('perfil'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], actor.email)
        self.assertEqual(response.data['zona'], 'Norte')

    def test_client_cannot_modify_another_client(self):
        actor = self.create_user('client-write-denied@test.com')
        Cliente.objects.create(usuario=actor)
        self.assign_role(actor, BusinessRole.CLIENTE)
        self.authenticate(actor)

        response = self.client.patch(
            self.detail_url(),
            {'zona': 'Otra zona'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.target.refresh_from_db()
        self.assertEqual(self.target.zona, 'Centro')

    def test_view_clients_is_read_only(self):
        actor = self.create_user('read-only@test.com')
        actor.user_permissions.add(self.view_permission)
        self.authenticate(actor)

        patch_response = self.client.patch(
            self.detail_url(),
            {'zona': 'Otra zona'},
            format='json',
        )
        delete_response = self.client.delete(self.detail_url())

        self.assertEqual(
            patch_response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            delete_response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.target.refresh_from_db()
        self.assertEqual(self.target.zona, 'Centro')

    def test_walkin_creation_still_uses_its_dedicated_permission(self):
        actor = self.create_user('walkin-actor@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.EMPLEADO)
        self.authenticate(actor)

        response = self.client.post(
            reverse('admin-client-account-create'),
            {
                'first_name': 'Beatriz',
                'last_name': 'Gómez',
                'email': 'walkin-created@test.com',
                'password_temporal': 'WalkinClient!2026',
                'telefono': '1199999999',
                'zona': 'Sur',
                'motivo': 'Alta presencial en recepción',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Cliente.objects.filter(
                usuario__email='walkin-created@test.com'
            ).exists()
        )

    def test_individual_view_clients_permission_allows_listing(self):
        actor = self.create_user('individual-permission@test.com')
        actor.user_permissions.add(self.view_permission)
        self.assertFalse(actor.is_staff)
        self.authenticate(actor)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_search_uses_the_same_view_clients_permission(self):
        allowed = self.create_user('search-allowed@test.com')
        allowed.user_permissions.add(self.view_permission)
        self.authenticate(allowed)

        response = self.client.get(self.list_url, {'search': 'target'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        denied = self.create_user('search-denied@test.com', is_staff=True)
        self.authenticate(denied)
        denied_response = self.client.get(
            self.list_url,
            {'search': 'target'},
        )
        self.assertEqual(
            denied_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
