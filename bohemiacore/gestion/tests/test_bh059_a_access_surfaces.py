from unittest.mock import Mock

from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from gestion.admin import PersonalAdmin
from gestion.middleware import _thread_locals
from gestion.models import Auditoria, Personal
from gestion.views import ContenidoEducativoViewSet
from usuarios.admin import ClienteAdmin, UsuarioAdmin
from usuarios.models import Cliente, Usuario


class EffectiveAccessSurfaceTests(APITestCase):
    def setUp(self):
        _thread_locals.user = None
        _thread_locals.request = None
        self.personal = Personal.objects.create(
            nombre='Profesional',
            apellido='Visible',
            rol='colorista',
            email='contacto-privado@test.com',
            telefono='123456789',
            activo=True,
        )
        self.staff_only = self.create_user(
            'legacy-staff-surfaces@test.com',
            is_staff=True,
        )
        self.personal_manager = self.create_user(
            'personal-manager-surfaces@test.com'
        )
        self.personal_manager.user_permissions.add(
            self.permission('gestion', 'manage_personal')
        )
        self.skills_manager = self.create_user(
            'skills-manager-surfaces@test.com'
        )
        self.skills_manager.user_permissions.add(
            self.permission('gestion', 'manage_skills')
        )

    def tearDown(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().tearDown()

    @staticmethod
    def permission(app_label, codename):
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='SurfacePassword!2026',
            **extra_fields,
        )

    def test_staff_without_effective_permission_cannot_read_personal(self):
        self.client.force_authenticate(self.staff_only)

        response = self.client.get(reverse('personal-list'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manage_personal_without_staff_can_read_full_personal(self):
        self.client.force_authenticate(self.personal_manager)

        response = self.client.get(reverse('personal-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['email'], 'contacto-privado@test.com')
        self.assertEqual(response.data[0]['telefono'], '123456789')

    def test_manage_skills_gets_only_minimal_directory(self):
        self.client.force_authenticate(self.skills_manager)

        full_response = self.client.get(reverse('personal-list'))
        minimal_response = self.client.get(
            reverse('personal-skill-directory')
        )

        self.assertEqual(full_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(minimal_response.status_code, status.HTTP_200_OK)
        self.assertSetEqual(
            set(minimal_response.data[0]),
            {'id', 'nombre', 'apellido', 'activo'},
        )
        serialized = str(minimal_response.data).lower()
        self.assertNotIn('contacto-privado@test.com', serialized)
        self.assertNotIn('123456789', serialized)
        self.assertNotIn('usuario', serialized)

    def test_generic_personal_patch_rejects_access_state(self):
        self.client.force_authenticate(self.personal_manager)

        response = self.client.patch(
            reverse('personal-detail', args=[self.personal.pk]),
            {'nombre': 'No aplicar', 'activo': False},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('activo', response.data)
        self.personal.refresh_from_db()
        self.assertEqual(self.personal.nombre, 'Profesional')
        self.assertTrue(self.personal.activo)

    def test_staff_content_flow_cannot_create_personal_link(self):
        view = ContenidoEducativoViewSet()
        view.request = Mock(user=self.staff_only)
        serializer = Mock()

        with self.assertRaises(PermissionDenied):
            view.perform_create(serializer)

        serializer.save.assert_not_called()
        self.assertFalse(
            Personal.objects.filter(usuario=self.staff_only).exists()
        )


class AuditEffectivePermissionTests(APITestCase):
    def setUp(self):
        _thread_locals.user = None
        _thread_locals.request = None
        self.staff_only = self.create_user(
            'audit-staff-only@test.com',
            is_staff=True,
        )
        self.viewer = self.create_user('audit-viewer@test.com')
        self.viewer.user_permissions.add(self.permission('view_audit'))
        self.reverter = self.create_user('audit-reverter@test.com')
        self.reverter.user_permissions.add(self.permission('revert_audit'))
        self.legacy_audit = Auditoria.objects.create(
            tabla='AccessSurface',
            registro_id=1,
            usuario=self.viewer,
            accion='ALTA',
            valor_nuevo={'event': 'TEST'},
        )

    def tearDown(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().tearDown()

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='AuditPassword!2026',
            **extra_fields,
        )

    def test_audit_read_uses_effective_permission_instead_of_staff(self):
        self.client.force_authenticate(self.staff_only)
        denied = self.client.get(reverse('auditoria-list'))

        self.client.force_authenticate(self.viewer)
        allowed = self.client.get(reverse('auditoria-list'))

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_legacy_audit_without_role_contract_metadata_is_readable(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.get(
            reverse('auditoria-detail', args=[self.legacy_audit.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['valor_nuevo']['event'], 'TEST')
        self.assertNotIn(
            'role_contract_version',
            response.data['valor_nuevo'],
        )

    def test_generic_history_rejects_personal_access_reversal(self):
        personal = Personal.objects.create(
            nombre='Histórico',
            apellido='Protegido',
            rol='asistente',
            activo=True,
        )
        personal.activo = False
        personal.save(update_fields=['activo'])
        inactive_history = personal.history.filter(activo=False).first()
        personal.activo = True
        personal.save(update_fields=['activo'])
        self.client.force_authenticate(self.reverter)

        response = self.client.post(
            reverse(
                'auditoria-historial-revertir',
                args=[f'personal:{inactive_history.history_id}'],
            ),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('activo', response.data['blocked_fields'])
        personal.refresh_from_db()
        self.assertTrue(personal.activo)

    def test_view_permission_does_not_grant_reversion(self):
        personal = Personal.objects.create(
            nombre='Sin',
            apellido='Reversión',
            rol='asistente',
        )
        personal.nombre = 'Modificado'
        personal.save(update_fields=['nombre'])
        history = personal.history.first()
        self.client.force_authenticate(self.viewer)

        response = self.client.post(
            reverse(
                'auditoria-historial-revertir',
                args=[f'personal:{history.history_id}'],
            ),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DjangoAdminAccessContainmentTests(APITestCase):
    def setUp(self):
        _thread_locals.user = None
        _thread_locals.request = None
        self.request = RequestFactory().get('/admin/')
        self.request.user = Usuario.objects.create_superuser(
            email='admin-inspection@test.com',
            password='AdminInspection!2026',
        )

    def tearDown(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().tearDown()

    def test_usuario_admin_has_no_privilege_writes_or_bulk_actions(self):
        model_admin = UsuarioAdmin(Usuario, admin.site)
        readonly = set(model_admin.get_readonly_fields(self.request))

        self.assertTrue({
            'is_active',
            'is_staff',
            'is_superuser',
            'groups',
            'user_permissions',
        } <= readonly)
        self.assertIsNone(model_admin.actions)
        self.assertFalse(model_admin.has_add_permission(self.request))
        self.assertFalse(model_admin.has_delete_permission(self.request))
        self.assertFalse(hasattr(model_admin, 'desactivar_usuarios'))
        self.assertFalse(hasattr(model_admin, 'activar_usuarios'))
        self.assertFalse(admin.site.is_registered(Group))

    def test_personal_and_client_access_fields_are_read_only(self):
        personal_admin = PersonalAdmin(Personal, admin.site)
        cliente_admin = ClienteAdmin(Cliente, admin.site)

        self.assertTrue(
            {'usuario', 'activo'}
            <= set(personal_admin.get_readonly_fields(self.request))
        )
        self.assertIsNone(personal_admin.actions)
        self.assertFalse(personal_admin.has_delete_permission(self.request))
        self.assertIn(
            'activo',
            set(cliente_admin.get_readonly_fields(self.request)),
        )
        self.assertIsNone(cliente_admin.actions)
        self.assertFalse(cliente_admin.has_add_permission(self.request))
        self.assertFalse(cliente_admin.has_delete_permission(self.request))
