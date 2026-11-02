from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Personal
from gestion.personal_access_services import (
    WORK_ACCESS_REVOCATION_AUDIT_TABLE,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class WorkAccessRevocationActionTests(APITestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('revoke-api-actor@test.com')
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
            'apellido': 'Revocacion API',
            'rol': 'asistente',
            'activo': True,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def create_linked_context(
        self,
        suffix,
        role=BusinessRole.EMPLEADO,
        *,
        personal_active=True,
        user_active=True,
        with_client=True,
    ):
        user = self.create_user(
            f'revoke-api-{suffix}@test.com',
            is_active=user_active,
        )
        user.groups.add(Group.objects.get(name=role))
        client = None
        if with_client:
            client = Cliente.objects.create(usuario=user, zona='Centro')
        personal = self.create_personal(
            suffix,
            usuario=user,
            activo=personal_active,
        )
        return personal, user, client

    def url(self, personal_id):
        return reverse(
            'personal-revocar-acceso-laboral',
            args=[personal_id],
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def post(self, personal_id, payload=None):
        if payload is None:
            payload = {'motivo': 'Fin de relacion laboral'}
        return self.client.post(
            self.url(personal_id),
            payload,
            format='json',
        )

    def test_valid_revocation_returns_200_and_final_client_state(self):
        personal, user, client = self.create_linked_context('valid')
        original_password = user.password
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['personal_id'], personal.pk)
        self.assertEqual(response.data['usuario_id'], user.pk)
        self.assertEqual(
            response.data['rol_anterior'],
            BusinessRole.EMPLEADO,
        )
        self.assertEqual(response.data['rol_actual'], BusinessRole.CLIENTE)
        self.assertTrue(response.data['personal_activo_anterior'])
        self.assertFalse(response.data['personal_activo_actual'])
        self.assertTrue(response.data['usuario_activo'])
        self.assertEqual(response.data['cliente_id'], client.pk)

        personal.refresh_from_db()
        user.refresh_from_db()
        client.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertEqual(personal.usuario, user)
        self.assertTrue(user.is_active)
        self.assertEqual(user.password, original_password)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertEqual(client.zona, 'Centro')

    def test_final_state_noop_returns_200_without_audit(self):
        personal, user, client = self.create_linked_context(
            'noop',
            role=BusinessRole.CLIENTE,
            personal_active=False,
        )
        audit_count = Auditoria.objects.count()
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertEqual(response.data['rol_actual'], BusinessRole.CLIENTE)
        self.assertFalse(response.data['personal_activo_actual'])
        self.assertTrue(response.data['usuario_activo'])
        self.assertEqual(response.data['cliente_id'], client.pk)
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assertFalse(
            Auditoria.objects.filter(
                tabla=WORK_ACCESS_REVOCATION_AUDIT_TABLE
            ).exists()
        )
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_unauthenticated_request_returns_401(self):
        personal, _, _ = self.create_linked_context('anonymous')

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_actor_without_each_required_permission_returns_403(self):
        personal, user, _ = self.create_linked_context('denied')
        permission_sets = (
            (),
            (self.manage_personal,),
            (self.assign_roles,),
        )

        for index, permissions in enumerate(permission_sets, start=1):
            with self.subTest(permissions=permissions):
                actor = self.create_user(
                    f'revoke-api-denied-{index}@test.com',
                    is_staff=True,
                )
                actor.user_permissions.add(*permissions)
                self.authenticate(actor)

                response = self.post(personal.pk)

                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    response.data['error']['code'],
                    'PERMISSION_DENIED',
                )

        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))

    def test_self_role_change_returns_stable_409_and_rolls_back(self):
        self.actor.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        Cliente.objects.create(usuario=self.actor, zona='Centro')
        personal = self.create_personal('self-target', usuario=self.actor)
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'WORK_ACCESS_REVOCATION_CONFLICT',
        )
        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertEqual(
            get_business_roles(self.actor),
            (BusinessRole.EMPLEADO,),
        )

    def test_nonexistent_personal_returns_stable_404(self):
        self.authenticate()

        response = self.post(999999)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'PERSONAL_NOT_FOUND')

    def test_personal_without_user_returns_stable_409(self):
        personal = self.create_personal('without-user')
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'PERSONAL_HAS_NO_USER',
        )
        personal.refresh_from_db()
        self.assertTrue(personal.activo)

    def test_user_without_client_returns_stable_409(self):
        personal, user, _ = self.create_linked_context(
            'without-client',
            with_client=False,
        )
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'CLIENT_PROFILE_REQUIRED',
        )
        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))
        self.assertFalse(Cliente.objects.filter(usuario=user).exists())

    def test_inactive_user_returns_stable_409_without_reactivation(self):
        personal, user, _ = self.create_linked_context(
            'inactive-user',
            user_active=False,
        )
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'USER_INACTIVE')
        personal.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertFalse(user.is_active)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))

    def test_multiple_roles_return_stable_409_without_correction(self):
        personal, user, _ = self.create_linked_context('multiple-roles')
        user.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'INCONSISTENT_BUSINESS_ROLES',
        )
        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertSetEqual(
            set(get_business_roles(user)),
            {BusinessRole.CLIENTE, BusinessRole.EMPLEADO},
        )

    def test_invalid_reason_returns_stable_400(self):
        personal, _, _ = self.create_linked_context('invalid-reason')
        self.authenticate()

        response = self.post(personal.pk, {'motivo': ' '})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_REASON')

    def test_unexpected_fields_are_rejected(self):
        personal, user, _ = self.create_linked_context('unexpected')
        self.authenticate()
        payload = {
            'motivo': 'Intento con campos no permitidos',
            'role': BusinessRole.CLIENTE,
            'is_active': True,
            'activo': False,
            'usuario': user.pk,
            'groups': [],
            'password': 'unsafe',
            'skills': [],
        }

        response = self.post(personal.pk, payload)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PAYLOAD')
        self.assertSetEqual(
            set(response.data['error']['fields']),
            set(payload) - {'motivo'},
        )
        personal.refresh_from_db()
        self.assertTrue(personal.activo)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))

    def test_response_does_not_expose_secrets_or_internal_audit_ids(self):
        personal, _, _ = self.create_linked_context('safe-response')
        self.authenticate()

        response = self.post(personal.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        forbidden_fields = {
            'password',
            'token',
            'access',
            'refresh',
            'audit_id',
            'status_audit_id',
            'role_audit_id',
        }
        self.assertTrue(forbidden_fields.isdisjoint(response.data))
