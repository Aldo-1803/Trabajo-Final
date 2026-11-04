from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.middleware import _thread_locals
from gestion.models import Auditoria, Personal
from usuarios.access_services import ROLE_AUDIT_TABLE
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessPermission, BusinessRole, get_business_role


class AdministrativeBusinessRoleChangeApiTests(APITestCase):
    def setUp(self):
        _thread_locals.user = None
        _thread_locals.request = None
        self.actor = self.create_user('role-api-manager@test.com')
        self.actor.user_permissions.add(
            self.permission(BusinessPermission.MANAGE_USERS),
            self.permission(BusinessPermission.ASSIGN_ROLES),
        )

    def tearDown(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().tearDown()

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='RoleApi!2026',
            **extra_fields,
        )

    @staticmethod
    def permission(code):
        app_label, codename = code.split('.', 1)
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    @staticmethod
    def create_personal(user, *, active=True):
        return Personal.objects.create(
            usuario=user,
            nombre='Cuenta',
            apellido='Laboral',
            rol='asistente',
            activo=active,
        )

    @staticmethod
    def error_code(response):
        return response.data['error']['code']

    def url(self, target):
        return reverse(
            'admin-usuarios-cambiar-rol-negocio',
            args=[target.pk],
        )

    def post(self, target, role, actor=None, **payload):
        self.client.force_authenticate(user=actor or self.actor)
        body = {
            'role': role,
            'motivo': 'Cambio general aprobado',
        }
        body.update(payload)
        return self.client.post(self.url(target), body, format='json')

    def test_authorized_change_returns_updated_canonical_summary(self):
        target = self.create_user('role-api-target@test.com')
        cliente = Cliente.objects.create(usuario=target, zona='Centro')
        personal = self.create_personal(target)
        self.assign_role(target, BusinessRole.EMPLEADO)

        response = self.post(target, BusinessRole.CLIENTE)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['previous_role'], BusinessRole.EMPLEADO)
        self.assertEqual(response.data['business_role'], BusinessRole.CLIENTE)
        self.assertEqual(
            response.data['access_summary']['business_role'],
            BusinessRole.CLIENTE,
        )
        target.refresh_from_db()
        cliente.refresh_from_db()
        personal.refresh_from_db()
        self.assertEqual(get_business_role(target), BusinessRole.CLIENTE)
        self.assertEqual(cliente.usuario_id, target.pk)
        self.assertEqual(personal.usuario_id, target.pk)

    def test_each_partial_permission_and_staff_only_receive_403(self):
        target = self.create_user('role-api-authority-target@test.com')
        Cliente.objects.create(usuario=target)
        actors = []
        for index, permission in enumerate((
            BusinessPermission.MANAGE_USERS,
            BusinessPermission.ASSIGN_ROLES,
        )):
            actor = self.create_user(f'role-api-partial-{index}@test.com')
            actor.user_permissions.add(self.permission(permission))
            actors.append(actor)
        actors.append(self.create_user('role-api-staff@test.com', is_staff=True))
        inactive_actor = self.create_user(
            'role-api-inactive-manager@test.com',
            is_active=False,
        )
        inactive_actor.user_permissions.add(
            self.permission(BusinessPermission.MANAGE_USERS),
            self.permission(BusinessPermission.ASSIGN_ROLES),
        )
        actors.append(inactive_actor)

        for actor in actors:
            with self.subTest(actor=actor.email):
                response = self.post(target, BusinessRole.CLIENTE, actor=actor)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(self.error_code(response), 'PERMISSION_DENIED')

        self.assertIsNone(get_business_role(target))

    def test_self_change_and_superuser_target_are_rejected(self):
        Cliente.objects.create(usuario=self.actor)
        self.assign_role(self.actor, BusinessRole.CLIENTE)
        self_response = self.post(self.actor, BusinessRole.ADMINISTRADOR)

        superuser = self.create_user(
            'role-api-superuser@test.com',
            is_staff=True,
            is_superuser=True,
        )
        super_response = self.post(superuser, BusinessRole.ADMINISTRADOR)

        self.assertEqual(self_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.error_code(self_response),
            'SELF_ROLE_CHANGE_NOT_ALLOWED',
        )
        self.assertEqual(super_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.error_code(super_response), 'PROTECTED_SUPERUSER')

    def test_invalid_role_reason_and_unexpected_fields_are_rejected(self):
        target = self.create_user('role-api-invalid@test.com')
        Cliente.objects.create(usuario=target)

        invalid_role = self.post(target, 'UNKNOWN')
        invalid_reason = self.post(
            target,
            BusinessRole.CLIENTE,
            motivo=' ',
        )
        unexpected = self.post(
            target,
            BusinessRole.CLIENTE,
            groups=['ADMINISTRADOR'],
        )

        self.assertEqual(invalid_role.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.error_code(invalid_role), 'INVALID_ROLE')
        self.assertEqual(invalid_reason.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.error_code(invalid_reason), 'INVALID_REASON')
        self.assertEqual(unexpected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.error_code(unexpected), 'INVALID_PAYLOAD')
        self.assertIn('groups', unexpected.data['error']['fields'])

    def test_destination_profile_requirements_return_stable_conflicts(self):
        missing_client = self.create_user('role-api-no-client@test.com')
        missing_personal = self.create_user('role-api-no-personal@test.com')
        inactive_personal = self.create_user('role-api-inactive-personal@test.com')
        self.create_personal(inactive_personal, active=False)

        cases = (
            (missing_client, BusinessRole.CLIENTE, 'CLIENT_PROFILE_REQUIRED'),
            (
                missing_personal,
                BusinessRole.EMPLEADO,
                'PERSONAL_PROFILE_REQUIRED',
            ),
            (
                inactive_personal,
                BusinessRole.PROFESIONAL,
                'PERSONAL_INACTIVE',
            ),
        )
        for target, role, code in cases:
            with self.subTest(role=role, code=code):
                response = self.post(target, role)
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(self.error_code(response), code)

    def test_multiple_roles_and_last_administrator_are_rejected(self):
        multiple = self.create_user('role-api-multiple@test.com')
        Cliente.objects.create(usuario=multiple)
        multiple.groups.add(
            Group.objects.get(name=BusinessRole.CLIENTE),
            Group.objects.get(name=BusinessRole.EMPLEADO),
        )
        multiple_response = self.post(multiple, BusinessRole.CLIENTE)

        last_admin = self.create_user('role-api-last-admin@test.com')
        Cliente.objects.create(usuario=last_admin)
        self.assign_role(last_admin, BusinessRole.ADMINISTRADOR)
        last_response = self.post(last_admin, BusinessRole.CLIENTE)

        self.assertEqual(multiple_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            self.error_code(multiple_response),
            'INCONSISTENT_BUSINESS_ROLES',
        )
        self.assertEqual(last_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.error_code(last_response), 'LAST_ACTIVE_ADMIN')

    def test_residual_admin_capability_returns_origins_without_mutation(self):
        target = self.create_user('role-api-residual@test.com')
        backup = self.create_user('role-api-residual-backup@test.com')
        Cliente.objects.create(usuario=target)
        self.assign_role(target, BusinessRole.ADMINISTRADOR)
        self.assign_role(backup, BusinessRole.ADMINISTRADOR)
        target.user_permissions.add(
            self.permission(BusinessPermission.ASSIGN_ROLES)
        )

        response = self.post(target, BusinessRole.CLIENTE)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            self.error_code(response),
            'RESIDUAL_ADMIN_CAPABILITIES',
        )
        self.assertEqual(response.data['error']['capabilities'], [{
            'code': BusinessPermission.ASSIGN_ROLES,
            'effective': True,
            'origins': [{'type': 'INDIVIDUAL', 'identifier': None}],
        }])
        self.assertEqual(get_business_role(target), BusinessRole.ADMINISTRADOR)

    def test_noop_has_no_new_audit(self):
        target = self.create_user('role-api-noop@test.com')
        Cliente.objects.create(usuario=target)
        self.assign_role(target, BusinessRole.CLIENTE)
        before = Auditoria.objects.filter(tabla=ROLE_AUDIT_TABLE).count()

        response = self.post(target, BusinessRole.CLIENTE)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['changed'])
        self.assertIsNone(response.data['audit_id'])
        self.assertEqual(
            Auditoria.objects.filter(tabla=ROLE_AUDIT_TABLE).count(),
            before,
        )
