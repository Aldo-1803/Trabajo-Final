from pathlib import Path

from django.contrib.auth.models import Group, Permission
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Personal
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class AdminUsuarioCrudContainmentTests(APITestCase):
    def setUp(self):
        self.manage_users = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        )
        self.actor = self.create_user('identity-manager@test.com')
        self.actor.user_permissions.add(self.manage_users)
        self.staff_only = self.create_user(
            'legacy-staff@test.com',
            is_staff=True,
        )
        self.target = self.create_user('identity-target@test.com')

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def detail_url(self, user=None):
        return reverse(
            'admin-usuarios-detail',
            args=[(user or self.target).pk],
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def test_manage_users_actor_can_patch_basic_identity(self):
        self.authenticate()

        response = self.client.patch(
            self.detail_url(),
            {
                'email': 'identity-updated@test.com',
                'first_name': 'Nombre',
                'last_name': 'Actualizado',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, 'identity-updated@test.com')
        self.assertEqual(self.target.first_name, 'Nombre')
        self.assertEqual(self.target.last_name, 'Actualizado')

    def test_is_staff_without_manage_users_cannot_put_or_patch_identity(self):
        self.authenticate(self.staff_only)

        requests = (
            ('patch', {'first_name': 'No permitido'}),
            (
                'put',
                {
                    'email': 'forbidden-update@test.com',
                    'first_name': 'No',
                    'last_name': 'Permitido',
                },
            ),
        )
        for method, payload in requests:
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.detail_url(),
                    payload,
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

        self.target.refresh_from_db()
        self.assertEqual(self.target.email, 'identity-target@test.com')
        self.assertEqual(self.target.first_name, '')
        self.assertEqual(self.target.last_name, '')

    def test_sensitive_fields_are_explicitly_rejected_by_identity_patch(self):
        technical_group = Group.objects.create(name='IDENTITY_TECHNICAL')
        target_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        self.target.groups.add(technical_group)
        self.target.user_permissions.add(target_permission)
        original_password = self.target.password
        original_groups = set(
            self.target.groups.values_list('pk', flat=True)
        )
        original_permissions = set(
            self.target.user_permissions.values_list('pk', flat=True)
        )
        self.authenticate()

        attempts = (
            ('password', {'password': 'Replacement-Password-123!'}),
            ('is_staff', {'is_staff': True}),
            ('is_superuser', {'is_superuser': True}),
            ('groups', {'groups': []}),
            ('user_permissions', {'user_permissions': []}),
            ('role', {'role': BusinessRole.ADMINISTRADOR}),
            (
                'business_role',
                {'business_role': BusinessRole.ADMINISTRADOR},
            ),
        )
        for field, payload in attempts:
            with self.subTest(field=field):
                response = self.client.patch(
                    self.detail_url(),
                    payload,
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

        self.target.refresh_from_db()
        self.assertEqual(self.target.password, original_password)
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.is_superuser)
        self.assertTrue(self.target.is_active)
        self.assertSetEqual(
            set(self.target.groups.values_list('pk', flat=True)),
            original_groups,
        )
        self.assertSetEqual(
            set(self.target.user_permissions.values_list('pk', flat=True)),
            original_permissions,
        )

    def test_is_active_is_isolated_in_exact_legacy_patch_only(self):
        self.authenticate()

        mixed_response = self.client.patch(
            self.detail_url(),
            {'first_name': 'No aplicar', 'is_active': False},
            format='json',
        )
        put_response = self.client.put(
            self.detail_url(),
            {'is_active': False},
            format='json',
        )

        self.assertEqual(
            mixed_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            mixed_response.data['error']['code'],
            'INVALID_PAYLOAD',
        )
        self.assertIn('is_active', mixed_response.data['error']['fields'])
        self.assertEqual(put_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            put_response.data['error']['code'],
            'INVALID_PAYLOAD',
        )
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertEqual(self.target.first_name, '')

        legacy_response = self.client.patch(
            self.detail_url(),
            {'is_active': False},
            format='json',
        )

        self.assertEqual(legacy_response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_legacy_status_patch_also_requires_manage_users(self):
        self.authenticate(self.staff_only)

        response = self.client.patch(
            self.detail_url(),
            {'is_active': False},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'PERMISSION_DENIED',
        )
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_superuser_target_is_protected_from_put_and_patch(self):
        target = self.create_user(
            'protected-superuser@test.com',
            is_staff=True,
            is_superuser=True,
        )
        self.authenticate()

        requests = (
            ('patch', {'first_name': 'No permitido'}),
            (
                'put',
                {
                    'email': 'protected-changed@test.com',
                    'first_name': 'No',
                    'last_name': 'Permitido',
                },
            ),
        )
        for method, payload in requests:
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.detail_url(target),
                    payload,
                    format='json',
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'PROTECTED_SUPERUSER',
                )

        target.refresh_from_db()
        self.assertEqual(target.email, 'protected-superuser@test.com')
        self.assertEqual(target.first_name, '')
        self.assertEqual(target.last_name, '')

    def test_identity_patch_preserves_security_and_profiles(self):
        self.target.is_staff = True
        self.target.is_active = False
        self.target.save(update_fields=['is_staff', 'is_active'])
        original_password = self.target.password
        role_group = Group.objects.get(name=BusinessRole.CLIENTE)
        technical_group = Group.objects.create(name='PRESERVED_TECHNICAL')
        self.target.groups.add(role_group, technical_group)
        individual_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        self.target.user_permissions.add(individual_permission)
        cliente = Cliente.objects.create(
            usuario=self.target,
            zona='Centro',
            activo=False,
        )
        personal = Personal.objects.create(
            usuario=self.target,
            nombre='Perfil',
            apellido='Laboral',
            rol='colorista',
            activo=False,
            realiza_diagnostico=True,
            realiza_lavado=False,
            realiza_color=True,
        )
        group_ids = set(self.target.groups.values_list('pk', flat=True))
        permission_ids = set(
            self.target.user_permissions.values_list('pk', flat=True)
        )
        self.authenticate()

        response = self.client.patch(
            self.detail_url(),
            {
                'email': 'preserved-identity@test.com',
                'first_name': 'Identidad',
                'last_name': 'Segura',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        cliente.refresh_from_db()
        personal.refresh_from_db()
        self.assertEqual(self.target.password, original_password)
        self.assertTrue(self.target.is_staff)
        self.assertFalse(self.target.is_superuser)
        self.assertFalse(self.target.is_active)
        self.assertSetEqual(
            set(self.target.groups.values_list('pk', flat=True)),
            group_ids,
        )
        self.assertSetEqual(
            set(self.target.user_permissions.values_list('pk', flat=True)),
            permission_ids,
        )
        self.assertEqual(cliente.zona, 'Centro')
        self.assertFalse(cliente.activo)
        self.assertEqual(personal.nombre, 'Perfil')
        self.assertEqual(personal.rol, 'colorista')
        self.assertFalse(personal.activo)
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)

    def test_list_and_retrieve_keep_legacy_read_contract(self):
        self.target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        self.authenticate(self.staff_only)

        list_response = self.client.get(
            reverse('admin-usuarios-list'),
        )
        retrieve_response = self.client.get(self.detail_url())

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.data['id'], self.target.pk)
        self.assertIn('is_staff', retrieve_response.data)
        self.assertIn('is_active', retrieve_response.data)
        self.assertEqual(
            retrieve_response.data['business_role'],
            BusinessRole.CLIENTE,
        )
        self.assertNotIn('password', retrieve_response.data)

    def test_legacy_post_behavior_is_preserved(self):
        self.authenticate(self.staff_only)
        payload = {
            'email': 'legacy-created@test.com',
            'first_name': 'Alta',
            'last_name': 'Legacy',
            'password': 'legacy-create-password',
            'is_staff': True,
            'is_active': False,
        }

        response = self.client.post(
            reverse('admin-usuarios-list'),
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Usuario.objects.get(email=payload['email'])
        self.assertEqual(created.first_name, 'Alta')
        self.assertEqual(created.last_name, 'Legacy')
        self.assertTrue(created.is_staff)
        self.assertFalse(created.is_active)
        self.assertTrue(created.check_password(payload['password']))


class LegacyPersonalStaffScriptRemovalTests(SimpleTestCase):
    def test_fix_personal_staff_is_not_an_executable_python_script(self):
        gestion_directory = Path(__file__).resolve().parents[1]

        self.assertFalse(
            (gestion_directory / 'fix_personal_staff.py').exists()
        )
