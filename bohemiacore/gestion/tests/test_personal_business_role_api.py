from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Personal
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class PersonalBusinessRoleChangeApiTests(APITestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('role-api-actor@test.com')
        self.actor.user_permissions.add(
            self.manage_personal,
            self.assign_roles,
        )

    def create_user(self, email, role=None, **extra_fields):
        user = Usuario.objects.create_user(
            email=email,
            password='StrongTestPassword!2026',
            **extra_fields,
        )
        if role is not None:
            user.groups.add(Group.objects.get(name=role))
        return user

    def create_context(
        self,
        suffix,
        role=BusinessRole.CLIENTE,
        *,
        personal_active=True,
    ):
        user = self.create_user(f'role-api-{suffix}@test.com', role=role)
        client = Cliente.objects.create(usuario=user, zona='Centro')
        personal = Personal.objects.create(
            usuario=user,
            nombre=f'Nombre {suffix}',
            apellido='Rol API',
            rol='asistente',
            activo=personal_active,
        )
        return personal, user, client

    def url(self, personal):
        return reverse('personal-cambiar-rol-acceso', args=[personal.pk])

    def post(self, personal, payload=None):
        if payload is None:
            payload = {
                'role': BusinessRole.EMPLEADO,
                'motivo': 'Cliente incorporado al equipo',
            }
        return self.client.post(self.url(personal), payload, format='json')

    def test_valid_change_returns_200_and_contract(self):
        personal, user, client = self.create_context('valid')
        self.client.force_authenticate(user=self.actor)

        response = self.post(personal)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {
            'changed': True,
            'personal_id': personal.pk,
            'usuario_id': user.pk,
            'previous_role': BusinessRole.CLIENTE,
            'new_role': BusinessRole.EMPLEADO,
        })
        user.refresh_from_db()
        personal.refresh_from_db()
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))
        self.assertEqual(personal.usuario, user)
        self.assertTrue(Cliente.objects.filter(pk=client.pk).exists())

    def test_same_role_returns_200_noop(self):
        personal, user, _ = self.create_context(
            'noop',
            BusinessRole.PROFESIONAL,
        )
        self.client.force_authenticate(user=self.actor)

        response = self.post(personal, {
            'role': BusinessRole.PROFESIONAL,
            'motivo': 'Confirmación del rol vigente',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertEqual(response.data['previous_role'], BusinessRole.PROFESIONAL)
        self.assertEqual(response.data['new_role'], BusinessRole.PROFESIONAL)
        self.assertEqual(get_business_roles(user), (BusinessRole.PROFESIONAL,))

    def test_invalid_payload_returns_400(self):
        personal, _, _ = self.create_context('invalid-payload')
        self.client.force_authenticate(user=self.actor)

        response = self.post(personal, {'role': BusinessRole.EMPLEADO})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_REASON')

    def test_unauthenticated_returns_401(self):
        personal, _, _ = self.create_context('anonymous')

        response = self.post(personal)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_actor_requires_both_permissions_without_staff_shortcut(self):
        personal, user, _ = self.create_context('permissions')
        permission_sets = (
            (),
            (self.manage_personal,),
            (self.assign_roles,),
        )

        for index, permissions in enumerate(permission_sets, start=1):
            with self.subTest(permissions=permissions):
                actor = self.create_user(
                    f'role-api-denied-{index}@test.com',
                    is_staff=True,
                )
                actor.user_permissions.add(*permissions)
                self.client.force_authenticate(user=actor)

                response = self.post(personal)

                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'PERMISSION_DENIED',
                )

        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_cliente_and_administrador_targets_are_rejected(self):
        personal, user, _ = self.create_context('invalid-target-role')
        self.client.force_authenticate(user=self.actor)

        for role in (BusinessRole.CLIENTE, BusinessRole.ADMINISTRADOR):
            with self.subTest(role=role):
                response = self.post(personal, {
                    'role': role,
                    'motivo': 'Intento de rol no permitido',
                })

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'INVALID_TARGET_ROLE',
                )

        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_sensitive_and_identity_fields_are_rejected(self):
        personal, user, _ = self.create_context('sensitive-fields')
        self.client.force_authenticate(user=self.actor)
        forbidden_fields = {
            'is_staff': True,
            'is_superuser': True,
            'groups': [1],
            'user_permissions': [1],
            'is_active': False,
            'usuario_id': user.pk,
            'personal_id': personal.pk,
        }

        for field, value in forbidden_fields.items():
            with self.subTest(field=field):
                response = self.post(personal, {
                    'role': BusinessRole.EMPLEADO,
                    'motivo': 'Payload con campo no permitido',
                    field: value,
                })

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'INVALID_PAYLOAD',
                )
                self.assertIn(field, response.data['error']['fields'])

        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_personal_without_user_returns_stable_409(self):
        personal = Personal.objects.create(
            nombre='Sin',
            apellido='Usuario',
            rol='asistente',
            activo=True,
        )
        self.client.force_authenticate(user=self.actor)

        response = self.post(personal)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'PERSONAL_WITHOUT_USER',
        )

    def test_inactive_personal_returns_stable_409(self):
        personal, user, _ = self.create_context(
            'inactive',
            personal_active=False,
        )
        self.client.force_authenticate(user=self.actor)

        response = self.post(personal)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'PERSONAL_INACTIVE')
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_multiple_roles_returns_stable_409(self):
        personal, user, _ = self.create_context('multiple')
        user.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        self.client.force_authenticate(user=self.actor)

        response = self.post(personal, {
            'role': BusinessRole.PROFESIONAL,
            'motivo': 'Intento con roles múltiples',
        })

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'MULTIPLE_BUSINESS_ROLES',
        )

    def test_current_administrator_returns_stable_409(self):
        personal, user, _ = self.create_context(
            'administrator',
            BusinessRole.ADMINISTRADOR,
        )
        self.client.force_authenticate(user=self.actor)

        response = self.post(personal)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'ROLE_CHANGE_NOT_ALLOWED',
        )
        self.assertEqual(
            get_business_roles(user),
            (BusinessRole.ADMINISTRADOR,),
        )
