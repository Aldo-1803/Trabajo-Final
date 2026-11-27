from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Personal
from gestion.personal_access_services import PERSONAL_STATUS_AUDIT_TABLE
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class PersonalStatusActionTests(APITestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.actor = self.create_user('status-api-actor@test.com')
        self.actor.user_permissions.add(self.manage_personal)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def create_personal(self, suffix, **overrides):
        values = {
            'nombre': f'Nombre {suffix}',
            'apellido': 'API Estado',
            'rol': 'asistente',
            'activo': True,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def url(self, action, personal_id):
        return reverse(f'personal-{action}', args=[personal_id])

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def post_status(self, action, personal, motivo='Cambio laboral aprobado'):
        return self.client.post(
            self.url(action, personal.pk),
            {'motivo': motivo},
            format='json',
        )

    def test_valid_deactivation_returns_200_and_preserves_identity(self):
        user = self.create_user('status-api-linked@test.com', is_active=False)
        user.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))
        cliente = Cliente.objects.create(usuario=user, zona='Centro')
        personal = self.create_personal('deactivate', usuario=user)
        self.authenticate()

        response = self.post_status('desactivar', personal)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertTrue(response.data['activo_anterior'])
        self.assertFalse(response.data['activo_actual'])
        self.assertEqual(response.data['usuario_id'], user.pk)
        self.assertFalse(response.data['usuario_activo'])
        self.assertEqual(response.data['rol'], BusinessRole.EMPLEADO)

        personal.refresh_from_db()
        user.refresh_from_db()
        cliente.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertEqual(personal.usuario, user)
        self.assertFalse(user.is_active)
        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))
        self.assertEqual(cliente.zona, 'Centro')

    def test_valid_reactivation_returns_200_without_reactivating_user(self):
        user = self.create_user('status-api-reactivate@test.com', is_active=False)
        user.groups.add(Group.objects.get(name=BusinessRole.PROFESIONAL))
        personal = self.create_personal(
            'reactivate',
            usuario=user,
            activo=False,
        )
        self.authenticate()

        response = self.post_status('reactivar', personal)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertFalse(response.data['activo_anterior'])
        self.assertTrue(response.data['activo_actual'])
        self.assertFalse(response.data['usuario_activo'])
        self.assertEqual(response.data['rol'], BusinessRole.PROFESIONAL)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_noop_returns_200_without_status_audit(self):
        personal = self.create_personal('noop', activo=False)
        audit_count = Auditoria.objects.count()
        self.authenticate()

        response = self.post_status('desactivar', personal)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertFalse(response.data['activo_anterior'])
        self.assertFalse(response.data['activo_actual'])
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assertFalse(
            Auditoria.objects.filter(tabla=PERSONAL_STATUS_AUDIT_TABLE).exists()
        )

    def test_unauthenticated_requests_return_401(self):
        personal = self.create_personal('anonymous')

        for action in ('desactivar', 'reactivar'):
            with self.subTest(action=action):
                response = self.post_status(action, personal)
                self.assertEqual(
                    response.status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )

    def test_actor_without_manage_personal_returns_403(self):
        actor = self.create_user('status-api-denied@test.com', is_staff=True)
        personal = self.create_personal('denied')
        self.authenticate(actor)

        response = self.post_status('desactivar', personal)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')
        personal.refresh_from_db()
        self.assertTrue(personal.activo)

    def test_nonexistent_personal_returns_stable_404(self):
        self.authenticate()

        response = self.client.post(
            self.url('desactivar', 999999),
            {'motivo': 'Personal inexistente'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'PERSONAL_NOT_FOUND')

    def test_invalid_reason_returns_stable_400(self):
        personal = self.create_personal('invalid-reason')
        self.authenticate()

        response = self.post_status('desactivar', personal, motivo=' ')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_REASON')

    def test_unexpected_fields_are_rejected(self):
        personal = self.create_personal('unexpected-fields')
        self.authenticate()
        payload = {
            'motivo': 'Intento con campos no permitidos',
            'activo': False,
            'is_active': False,
            'role': BusinessRole.EMPLEADO,
            'groups': [],
            'usuario': 1,
            'password': 'unsafe',
            'skills': [],
            'rol': 'colorista',
        }

        response = self.client.post(
            self.url('desactivar', personal.pk),
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PAYLOAD')
        self.assertSetEqual(
            set(response.data['error']['fields']),
            set(payload) - {'motivo'},
        )
        personal.refresh_from_db()
        self.assertTrue(personal.activo)
