import json
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import TestCase

from gestion.models import Auditoria, Personal
from gestion.personal_access_services import (
    InvalidPersonalLinkReason,
    InvalidPersonalLinkTarget,
    InvalidPersonalLinkUser,
    PERSONAL_LINK_AUDIT_EVENT,
    PERSONAL_LINK_AUDIT_SOURCE,
    PERSONAL_LINK_AUDIT_TABLE,
    PermissionDeniedForPersonalLink,
    PersonalAlreadyLinked,
    UserAlreadyLinkedToPersonal,
    link_user_to_personal,
)
from usuarios.access_services import (
    InconsistentBusinessRoleState,
    ProtectedSuperuser,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class PersonalAccessServiceTests(TestCase):
    def setUp(self):
        self.actor = self.create_user('link-actor@test.com')
        self.actor.groups.add(
            Group.objects.get(name=BusinessRole.ADMINISTRADOR)
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
            'apellido': 'Prueba',
            'rol': 'asistente',
            'activo': True,
            'realiza_diagnostico': False,
            'realiza_lavado': True,
            'realiza_color': False,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def semantic_audits(self):
        return Auditoria.objects.filter(tabla=PERSONAL_LINK_AUDIT_TABLE)

    def test_normal_link_succeeds(self):
        user = self.create_user('normal-link@test.com')
        personal = self.create_personal('normal')

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion administrativa inicial',
        )

        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(result.personal_id, personal.pk)
        self.assertEqual(result.user_id, user.pk)
        self.assertEqual(personal.usuario, user)
        self.assertFalse(Cliente.objects.filter(usuario=user).exists())

    def test_existing_client_profile_is_preserved(self):
        user = self.create_user('client-profile-link@test.com')
        cliente = Cliente.objects.create(usuario=user, zona='Centro')
        personal = self.create_personal('client-profile')

        link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion conservando cliente',
        )

        cliente.refresh_from_db()
        personal.refresh_from_db()
        self.assertEqual(cliente.usuario, user)
        self.assertEqual(cliente.zona, 'Centro')
        self.assertEqual(personal.usuario, user)

    def test_roleless_user_remains_roleless(self):
        user = self.create_user('roleless-link@test.com')
        personal = self.create_personal('roleless')

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion sin asignar rol',
        )

        self.assertEqual(get_business_roles(user), ())
        self.assertIsNone(result.business_role)
        self.assertIn('NO_BUSINESS_ROLE', result.warnings)

    def test_client_business_role_is_not_changed(self):
        user = self.create_user('client-role-link@test.com')
        user.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        personal = self.create_personal('client-role')

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion conservando rol cliente',
        )

        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertEqual(result.business_role, BusinessRole.CLIENTE)

    def test_administrator_business_role_is_not_changed(self):
        user = self.create_user('admin-role-link@test.com')
        user.groups.add(Group.objects.get(name=BusinessRole.ADMINISTRADOR))
        personal = self.create_personal('admin-role')

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion conservando rol administrador',
        )

        self.assertEqual(
            get_business_roles(user),
            (BusinessRole.ADMINISTRADOR,),
        )
        self.assertEqual(result.business_role, BusinessRole.ADMINISTRADOR)

    def test_labor_roles_without_personal_can_be_corrected_by_link(self):
        for index, role in enumerate(
            (BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL),
            start=1,
        ):
            with self.subTest(role=role):
                user = self.create_user(f'labor-role-{index}@test.com')
                user.groups.add(Group.objects.get(name=role))
                personal = self.create_personal(f'labor-{index}')

                result = link_user_to_personal(
                    self.actor,
                    personal,
                    user,
                    'Vinculacion que completa perfil laboral',
                )

                personal.refresh_from_db()
                self.assertEqual(personal.usuario, user)
                self.assertEqual(get_business_roles(user), (role,))
                self.assertEqual(result.business_role, role)

    def test_personal_linked_to_another_user_is_rejected(self):
        current_user = self.create_user('current-personal-user@test.com')
        requested_user = self.create_user('requested-personal-user@test.com')
        personal = self.create_personal(
            'personal-conflict',
            usuario=current_user,
        )

        with self.assertRaises(PersonalAlreadyLinked):
            link_user_to_personal(
                self.actor,
                personal,
                requested_user,
                'Intento de reemplazar vinculo',
            )

        personal.refresh_from_db()
        self.assertEqual(personal.usuario, current_user)
        self.assertFalse(self.semantic_audits().exists())

    def test_user_linked_to_another_personal_is_rejected(self):
        user = self.create_user('already-linked-user@test.com')
        existing_personal = self.create_personal(
            'existing-link',
            usuario=user,
        )
        requested_personal = self.create_personal('requested-link')

        with self.assertRaises(UserAlreadyLinkedToPersonal):
            link_user_to_personal(
                self.actor,
                requested_personal,
                user,
                'Intento de segundo perfil',
            )

        existing_personal.refresh_from_db()
        requested_personal.refresh_from_db()
        self.assertEqual(existing_personal.usuario, user)
        self.assertIsNone(requested_personal.usuario)

    def test_repeated_same_link_is_noop_without_audit(self):
        user = self.create_user('same-link@test.com')
        personal = self.create_personal('same-link', usuario=user)

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Confirmacion del vinculo existente',
        )

        self.assertFalse(result.changed)
        self.assertIsNone(result.audit_id)
        self.assertFalse(self.semantic_audits().exists())

    def test_user_with_multiple_business_roles_is_rejected(self):
        user = self.create_user('multiple-roles-link@test.com')
        user.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )
        personal = self.create_personal('multiple-roles')

        with self.assertRaises(InconsistentBusinessRoleState):
            link_user_to_personal(
                self.actor,
                personal,
                user,
                'Intento con roles inconsistentes',
            )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario)

    def test_superuser_target_is_rejected(self):
        user = self.create_user(
            'superuser-link@test.com',
            is_staff=True,
            is_superuser=True,
        )
        personal = self.create_personal('superuser')

        with self.assertRaises(ProtectedSuperuser):
            link_user_to_personal(
                self.actor,
                personal,
                user,
                'Intento sobre superusuario',
            )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario)

    def test_inactive_user_is_linked_without_reactivation(self):
        user = self.create_user('inactive-user-link@test.com', is_active=False)
        personal = self.create_personal('inactive-user')

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Preparacion de usuario inactivo',
        )

        user.refresh_from_db()
        personal.refresh_from_db()
        self.assertEqual(personal.usuario, user)
        self.assertFalse(user.is_active)
        self.assertFalse(result.user_is_active)
        self.assertIn('USER_INACTIVE', result.warnings)

    def test_inactive_personal_is_linked_without_reactivation(self):
        user = self.create_user('inactive-personal-link@test.com')
        personal = self.create_personal('inactive-personal', activo=False)

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Preparacion de personal inactivo',
        )

        personal.refresh_from_db()
        self.assertEqual(personal.usuario, user)
        self.assertFalse(personal.activo)
        self.assertFalse(result.personal_is_active)
        self.assertIn('PERSONAL_INACTIVE', result.warnings)

    def test_account_flags_and_password_are_preserved(self):
        user = self.create_user(
            'flags-link@test.com',
            is_active=False,
            is_staff=True,
            is_superuser=False,
        )
        original_password = user.password
        personal = self.create_personal('flags')

        link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion sin modificar credenciales',
        )

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.password, original_password)

    def test_groups_and_individual_permissions_are_preserved(self):
        user = self.create_user('permissions-link@test.com')
        role_group = Group.objects.get(name=BusinessRole.CLIENTE)
        technical_group = Group.objects.create(name='LINK_TECHNICAL_GROUP')
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        )
        user.groups.add(role_group, technical_group)
        user.user_permissions.add(permission)
        group_ids = set(user.groups.values_list('pk', flat=True))
        permission_ids = set(
            user.user_permissions.values_list('pk', flat=True)
        )
        personal = self.create_personal('permissions')

        link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion conservando permisos',
        )

        self.assertSetEqual(
            set(user.groups.values_list('pk', flat=True)),
            group_ids,
        )
        self.assertSetEqual(
            set(user.user_permissions.values_list('pk', flat=True)),
            permission_ids,
        )

    def test_personal_role_active_state_and_skills_are_preserved(self):
        user = self.create_user('personal-fields-link@test.com')
        personal = self.create_personal(
            'personal-fields',
            rol='colorista',
            activo=False,
            realiza_diagnostico=True,
            realiza_lavado=False,
            realiza_color=True,
        )

        link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion conservando datos laborales',
        )

        personal.refresh_from_db()
        self.assertEqual(personal.rol, 'colorista')
        self.assertFalse(personal.activo)
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)

    def test_valid_link_creates_exactly_one_semantic_audit(self):
        user = self.create_user('audit-count-link@test.com')
        personal = self.create_personal('audit-count')
        audit_count_before = Auditoria.objects.count()

        result = link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion auditada',
        )

        self.assertEqual(self.semantic_audits().count(), 1)
        self.assertEqual(Auditoria.objects.count(), audit_count_before + 1)
        self.assertEqual(result.audit_id, self.semantic_audits().get().pk)

    def test_semantic_audit_contains_required_link_data(self):
        user = self.create_user('audit-content-link@test.com')
        personal = self.create_personal('audit-content')

        link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion aprobada por administracion',
        )

        audit = self.semantic_audits().get()
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, personal.pk)
        self.assertEqual(audit.valor_nuevo['event'], PERSONAL_LINK_AUDIT_EVENT)
        self.assertEqual(audit.valor_nuevo['source'], PERSONAL_LINK_AUDIT_SOURCE)
        self.assertEqual(audit.valor_nuevo['actor_id'], self.actor.pk)
        self.assertEqual(audit.valor_nuevo['personal_id'], personal.pk)
        self.assertIsNone(audit.valor_nuevo['previous_user_id'])
        self.assertEqual(audit.valor_nuevo['new_user_id'], user.pk)
        self.assertEqual(audit.valor_nuevo['user_email'], user.email)
        self.assertEqual(
            audit.valor_nuevo['reason'],
            'Vinculacion aprobada por administracion',
        )

    def test_semantic_audit_contains_no_credentials_or_tokens(self):
        user = self.create_user('audit-secret-link@test.com')
        personal = self.create_personal('audit-secret')

        link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion sin secretos',
        )

        audit = self.semantic_audits().get()
        payload = {
            'before': audit.valor_anterior,
            'after': audit.valor_nuevo,
        }
        payload_keys = set(payload['before']) | set(payload['after'])
        for forbidden_key in (
            'password',
            'password_hash',
            'token',
            'refresh_token',
            'access_token',
        ):
            self.assertNotIn(forbidden_key, payload_keys)

        serialized_payload = json.dumps(payload)
        self.assertNotIn(user.password, serialized_payload)
        self.assertNotIn(self.actor.password, serialized_payload)

    def test_audit_failure_rolls_back_link(self):
        user = self.create_user('audit-rollback-link@test.com')
        personal = self.create_personal('audit-rollback')

        with patch(
            'gestion.personal_access_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                link_user_to_personal(
                    self.actor,
                    personal,
                    user,
                    'Vinculacion que debe revertirse',
                )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario)
        self.assertFalse(self.semantic_audits().exists())

    def test_actor_requires_both_business_permissions(self):
        permissions = {
            codename: Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            )
            for app_label, codename in (
                ('gestion', 'manage_personal'),
                ('usuarios', 'assign_roles'),
            )
        }
        actor_permissions = (
            (),
            (permissions['manage_personal'],),
            (permissions['assign_roles'],),
        )

        for index, granted_permissions in enumerate(actor_permissions, start=1):
            with self.subTest(granted_permissions=granted_permissions):
                actor = self.create_user(
                    f'unauthorized-link-{index}@test.com',
                    is_staff=True,
                )
                actor.user_permissions.add(*granted_permissions)
                user = self.create_user(f'unauthorized-target-{index}@test.com')
                personal = self.create_personal(f'unauthorized-{index}')

                with self.assertRaises(PermissionDeniedForPersonalLink):
                    link_user_to_personal(
                        actor,
                        personal,
                        user,
                        'Intento sin todos los permisos',
                    )

                personal.refresh_from_db()
                self.assertIsNone(personal.usuario)

    def test_anonymous_actor_is_rejected(self):
        user = self.create_user('anonymous-target-link@test.com')
        personal = self.create_personal('anonymous')

        with self.assertRaises(PermissionDeniedForPersonalLink):
            link_user_to_personal(
                AnonymousUser(),
                personal,
                user,
                'Intento anonimo',
            )

    def test_technical_groups_are_preserved(self):
        user = self.create_user('technical-group-link@test.com')
        technical_group = Group.objects.create(name='LINK_TECHNICAL_ONLY')
        user.groups.add(technical_group)
        personal = self.create_personal('technical-group')

        link_user_to_personal(
            self.actor,
            personal,
            user,
            'Vinculacion conservando grupo tecnico',
        )

        self.assertSetEqual(
            set(user.groups.values_list('name', flat=True)),
            {technical_group.name},
        )

    def test_reason_is_required_and_bounded(self):
        user = self.create_user('invalid-reason-link@test.com')
        personal = self.create_personal('invalid-reason')

        for reason in (None, '', '  ', 'x', 'x' * 501):
            with self.subTest(reason=reason):
                with self.assertRaises(InvalidPersonalLinkReason):
                    link_user_to_personal(
                        self.actor,
                        personal,
                        user,
                        reason,
                    )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario)

    def test_deleted_personal_is_rejected(self):
        user = self.create_user('deleted-personal-user@test.com')
        personal = self.create_personal('deleted-personal')
        personal.delete()

        with self.assertRaises(InvalidPersonalLinkTarget):
            link_user_to_personal(
                self.actor,
                personal,
                user,
                'Intento con personal inexistente',
            )

    def test_deleted_user_is_rejected(self):
        user = self.create_user('deleted-user-link@test.com')
        personal = self.create_personal('deleted-user')
        user.delete()

        with self.assertRaises(InvalidPersonalLinkUser):
            link_user_to_personal(
                self.actor,
                personal,
                user,
                'Intento con usuario inexistente',
            )
