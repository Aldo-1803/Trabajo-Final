from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, Personal
from gestion.personal_access_services import PERSONAL_LINK_AUDIT_TABLE
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class PersonalUserLinkActionTests(APITestCase):
    def setUp(self):
        self.manage_personal = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_personal',
        )
        self.assign_roles = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='assign_roles',
        )
        self.actor = self.create_user('api-link-actor@test.com')
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
            'apellido': 'API',
            'rol': 'asistente',
            'activo': True,
            'realiza_diagnostico': False,
            'realiza_lavado': True,
            'realiza_color': False,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def url(self, personal_id):
        return reverse('personal-vincular-usuario', args=[personal_id])

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.actor)

    def post_link(self, personal, user, motivo='Vinculacion desde API'):
        return self.client.post(
            self.url(personal.pk),
            {'usuario_id': user.pk, 'motivo': motivo},
            format='json',
        )

    def semantic_audits(self):
        return Auditoria.objects.filter(tabla=PERSONAL_LINK_AUDIT_TABLE)

    def test_actor_with_both_permissions_links_existing_records(self):
        user = self.create_user('api-normal-target@test.com')
        personal = self.create_personal('normal')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['changed'], True)
        self.assertEqual(response.data['personal_id'], personal.pk)
        self.assertEqual(response.data['usuario_id'], user.pk)
        personal.refresh_from_db()
        self.assertEqual(personal.usuario, user)

    def test_existing_client_profile_is_preserved(self):
        user = self.create_user('api-client-profile@test.com')
        cliente = Cliente.objects.create(usuario=user, zona='Centro')
        personal = self.create_personal('client-profile')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cliente.refresh_from_db()
        self.assertEqual(cliente.usuario, user)
        self.assertEqual(cliente.zona, 'Centro')

    def test_roleless_user_is_linked_without_receiving_role(self):
        user = self.create_user('api-roleless@test.com')
        personal = self.create_personal('roleless')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['rol'])
        self.assertIn('NO_BUSINESS_ROLE', response.data['warnings'])
        self.assertEqual(get_business_roles(user), ())

    def test_client_role_is_preserved(self):
        user = self.create_user('api-client-role@test.com')
        user.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        personal = self.create_personal('client-role')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['rol'], BusinessRole.CLIENTE)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_inactive_user_remains_inactive(self):
        user = self.create_user('api-inactive-user@test.com', is_active=False)
        personal = self.create_personal('inactive-user')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['usuario_activo'])
        self.assertIn('USER_INACTIVE', response.data['warnings'])
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_inactive_personal_remains_inactive(self):
        user = self.create_user('api-inactive-personal@test.com')
        personal = self.create_personal('inactive-personal', activo=False)
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['personal_activo'])
        self.assertIn('PERSONAL_INACTIVE', response.data['warnings'])
        personal.refresh_from_db()
        self.assertFalse(personal.activo)

    def test_personal_linked_to_another_user_returns_conflict(self):
        current_user = self.create_user('api-current-user@test.com')
        requested_user = self.create_user('api-requested-user@test.com')
        personal = self.create_personal('personal-conflict', usuario=current_user)
        self.authenticate()

        response = self.post_link(personal, requested_user)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'PERSONAL_ALREADY_LINKED',
        )

    def test_user_linked_to_another_personal_returns_conflict(self):
        user = self.create_user('api-user-conflict@test.com')
        self.create_personal('existing-personal', usuario=user)
        personal = self.create_personal('requested-personal')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'USER_ALREADY_LINKED_TO_PERSONAL',
        )

    def test_same_link_returns_changed_false_without_audit(self):
        user = self.create_user('api-same-link@test.com')
        personal = self.create_personal('same-link', usuario=user)
        self.authenticate()
        audit_count = self.semantic_audits().count()
        total_audit_count = Auditoria.objects.count()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertEqual(self.semantic_audits().count(), audit_count)
        self.assertEqual(Auditoria.objects.count(), total_audit_count)

    def test_nonexistent_user_returns_stable_not_found(self):
        personal = self.create_personal('missing-user')
        self.authenticate()

        response = self.client.post(
            self.url(personal.pk),
            {'usuario_id': 999999, 'motivo': 'Usuario inexistente'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'USER_NOT_FOUND')

    def test_nonexistent_personal_returns_stable_not_found(self):
        user = self.create_user('api-missing-personal@test.com')
        self.authenticate()

        response = self.client.post(
            self.url(999999),
            {'usuario_id': user.pk, 'motivo': 'Personal inexistente'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'PERSONAL_NOT_FOUND')

    def test_unauthenticated_actor_is_rejected(self):
        user = self.create_user('api-anonymous-target@test.com')
        personal = self.create_personal('anonymous')

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_actor_without_manage_personal_is_rejected(self):
        actor = self.create_user('api-no-manage-personal@test.com')
        actor.user_permissions.add(self.assign_roles)
        user = self.create_user('api-no-manage-target@test.com')
        personal = self.create_personal('no-manage')
        self.authenticate(actor)

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')

    def test_actor_without_assign_roles_is_rejected(self):
        actor = self.create_user('api-no-assign-roles@test.com')
        actor.user_permissions.add(self.manage_personal)
        user = self.create_user('api-no-assign-target@test.com')
        personal = self.create_personal('no-assign')
        self.authenticate(actor)

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error']['code'], 'PERMISSION_DENIED')

    def test_sensitive_and_unexpected_fields_are_rejected(self):
        user = self.create_user('api-sensitive-payload@test.com')
        personal = self.create_personal('sensitive-payload')
        self.authenticate()
        payload = {
            'usuario_id': user.pk,
            'motivo': 'Payload con campos prohibidos',
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
            'groups': [],
            'user_permissions': [],
            'role': BusinessRole.ADMINISTRADOR,
            'password': 'unsafe',
            'activo': True,
            'rol': 'administrador',
            'realiza_diagnostico': True,
            'realiza_lavado': False,
            'realiza_color': True,
        }

        response = self.client.post(
            self.url(personal.pk),
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_PAYLOAD')
        personal.refresh_from_db()
        self.assertIsNone(personal.usuario)
        self.assertSetEqual(
            set(response.data['error']['fields']),
            set(payload) - {'usuario_id', 'motivo'},
        )

    def test_link_does_not_change_access_or_personal_fields(self):
        user = self.create_user(
            'api-preserve-access@test.com',
            is_active=False,
            is_staff=True,
            is_superuser=False,
        )
        original_password = user.password
        client_group = Group.objects.get(name=BusinessRole.CLIENTE)
        technical_group = Group.objects.create(name='API_LINK_TECHNICAL')
        individual_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        user.groups.add(client_group, technical_group)
        user.user_permissions.add(individual_permission)
        group_ids = set(user.groups.values_list('pk', flat=True))
        permission_ids = set(
            user.user_permissions.values_list('pk', flat=True)
        )
        personal = self.create_personal(
            'preserve-fields',
            activo=False,
            rol='colorista',
            realiza_diagnostico=True,
            realiza_lavado=False,
            realiza_color=True,
        )
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        personal.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.password, original_password)
        self.assertSetEqual(
            set(user.groups.values_list('pk', flat=True)),
            group_ids,
        )
        self.assertSetEqual(
            set(user.user_permissions.values_list('pk', flat=True)),
            permission_ids,
        )
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertFalse(personal.activo)
        self.assertEqual(personal.rol, 'colorista')
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)

    def test_real_change_creates_exactly_one_semantic_audit(self):
        user = self.create_user('api-audit-target@test.com')
        personal = self.create_personal('audit')
        self.authenticate()
        total_audits_before = Auditoria.objects.count()

        response = self.post_link(
            personal,
            user,
            motivo='Vinculacion auditada desde API',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Auditoria.objects.count(), total_audits_before + 1)
        audit = self.semantic_audits().get()
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, personal.pk)
        self.assertEqual(audit.valor_nuevo['new_user_id'], user.pk)
        self.assertEqual(
            audit.valor_nuevo['reason'],
            'Vinculacion auditada desde API',
        )

    def test_multiple_business_roles_return_conflict(self):
        user = self.create_user('api-multiple-roles@test.com')
        user.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )
        personal = self.create_personal('multiple-roles')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['error']['code'],
            'INCONSISTENT_BUSINESS_ROLES',
        )

    def test_superuser_target_returns_forbidden(self):
        user = self.create_user(
            'api-superuser-target@test.com',
            is_staff=True,
            is_superuser=True,
        )
        personal = self.create_personal('superuser')
        self.authenticate()

        response = self.post_link(personal, user)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error']['code'],
            'PROTECTED_SUPERUSER',
        )

    def test_invalid_reason_returns_stable_bad_request(self):
        user = self.create_user('api-invalid-reason@test.com')
        personal = self.create_personal('invalid-reason')
        self.authenticate()

        response = self.post_link(personal, user, motivo=' ')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error']['code'], 'INVALID_REASON')
