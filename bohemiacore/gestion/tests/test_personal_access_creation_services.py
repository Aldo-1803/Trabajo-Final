import json
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.db import IntegrityError
from django.test import TestCase

from gestion.models import Auditoria, Personal
from gestion.personal_access_services import (
    EmailAlreadyExists,
    InvalidPersonalAccessRole,
    InvalidTemporaryPassword,
    PERSONAL_ACCESS_AUDIT_EVENT,
    PERSONAL_ACCESS_AUDIT_SOURCE,
    PERSONAL_ACCESS_AUDIT_TABLE,
    PersonalAccessConflict,
    PersonalAlreadyHasAccess,
    PersonalInactiveForAccess,
    PermissionDeniedForPersonalLink,
    create_access_for_personal,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_role


class PersonalAccessCreationServiceTests(TestCase):
    strong_password = 'Temporary!Access2026'

    def setUp(self):
        self.actor = self.create_user('access-create-actor@test.com')
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
            'apellido': 'Acceso',
            'rol': 'asistente',
            'activo': True,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def create_access(self, personal, role, **overrides):
        values = {
            'actor': self.actor,
            'personal': personal,
            'email': f'access-{personal.pk}@test.com',
            'raw_password': self.strong_password,
            'role': role,
            'reason': 'Alta inicial de acceso laboral',
        }
        values.update(overrides)
        return create_access_for_personal(**values)

    def test_employee_access_is_created(self):
        personal = self.create_personal('employee')

        result = self.create_access(personal, BusinessRole.EMPLEADO)

        personal.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(personal.usuario_id, result.user_id)
        self.assertEqual(
            get_business_role(personal.usuario),
            BusinessRole.EMPLEADO,
        )

    def test_professional_access_is_created(self):
        personal = self.create_personal(
            'professional',
            rol='asistente',
            realiza_diagnostico=True,
            realiza_lavado=False,
            realiza_color=True,
        )

        result = self.create_access(personal, BusinessRole.PROFESIONAL)

        personal.refresh_from_db()
        self.assertEqual(result.role, BusinessRole.PROFESIONAL)
        self.assertEqual(
            get_business_role(personal.usuario),
            BusinessRole.PROFESIONAL,
        )
        self.assertEqual(personal.rol, 'asistente')
        self.assertTrue(personal.realiza_diagnostico)
        self.assertFalse(personal.realiza_lavado)
        self.assertTrue(personal.realiza_color)

    def test_administrator_access_is_created_without_staff_flag(self):
        personal = self.create_personal('administrator')

        result = self.create_access(personal, BusinessRole.ADMINISTRADOR)

        user = Usuario.objects.get(pk=result.user_id)
        self.assertEqual(get_business_role(user), BusinessRole.ADMINISTRADOR)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_client_role_is_rejected(self):
        personal = self.create_personal('client-role')

        with self.assertRaises(InvalidPersonalAccessRole):
            self.create_access(personal, BusinessRole.CLIENTE)

        self.assertIsNone(Personal.objects.get(pk=personal.pk).usuario_id)
        self.assertFalse(
            Usuario.objects.filter(email=f'access-{personal.pk}@test.com').exists()
        )

    def test_inactive_personal_is_rejected_without_reactivation(self):
        personal = self.create_personal('inactive', activo=False)

        with self.assertRaises(PersonalInactiveForAccess):
            self.create_access(personal, BusinessRole.ADMINISTRADOR)

        personal.refresh_from_db()
        self.assertFalse(personal.activo)
        self.assertIsNone(personal.usuario_id)

    def test_personal_with_user_is_rejected(self):
        current_user = self.create_user('already-access@test.com')
        personal = self.create_personal('already-access', usuario=current_user)

        with self.assertRaises(PersonalAlreadyHasAccess):
            self.create_access(personal, BusinessRole.EMPLEADO)

        personal.refresh_from_db()
        self.assertEqual(personal.usuario, current_user)

    def test_existing_email_is_rejected_without_link(self):
        self.create_user('existing-access@test.com')
        personal = self.create_personal('existing-email')

        with self.assertRaises(EmailAlreadyExists):
            self.create_access(
                personal,
                BusinessRole.EMPLEADO,
                email='existing-access@test.com',
            )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario_id)

    def test_existing_email_is_detected_case_insensitively(self):
        self.create_user('MixedCaseAccess@test.com')
        personal = self.create_personal('case-email')

        with self.assertRaises(EmailAlreadyExists):
            self.create_access(
                personal,
                BusinessRole.EMPLEADO,
                email='mixedcaseaccess@TEST.COM',
            )

        self.assertEqual(
            Usuario.objects.filter(email__iexact='mixedcaseaccess@test.com').count(),
            1,
        )

    def test_concurrent_user_integrity_conflict_has_domain_exception(self):
        personal = self.create_personal('integrity-conflict')

        with patch.object(
            Usuario.objects,
            'create_user',
            side_effect=IntegrityError('concurrent conflict'),
        ):
            with self.assertRaises(PersonalAccessConflict):
                self.create_access(personal, BusinessRole.EMPLEADO)

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario_id)

    def test_weak_password_is_rejected_before_user_creation(self):
        personal = self.create_personal('weak-password')

        with self.assertRaises(InvalidTemporaryPassword):
            self.create_access(
                personal,
                BusinessRole.EMPLEADO,
                raw_password='123',
            )

        self.assertIsNone(Personal.objects.get(pk=personal.pk).usuario_id)
        self.assertFalse(
            Usuario.objects.filter(email=f'access-{personal.pk}@test.com').exists()
        )

    def test_created_user_has_safe_explicit_flags_and_personal_names(self):
        personal = self.create_personal('safe-flags')

        result = self.create_access(personal, BusinessRole.EMPLEADO)

        user = Usuario.objects.get(pk=result.user_id)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.first_name, personal.nombre)
        self.assertEqual(user.last_name, personal.apellido)

    def test_client_profile_is_not_created(self):
        personal = self.create_personal('no-client')

        result = self.create_access(personal, BusinessRole.EMPLEADO)

        self.assertFalse(Cliente.objects.filter(usuario_id=result.user_id).exists())

    def test_only_business_role_group_and_no_individual_permissions_are_added(self):
        personal = self.create_personal('permissions')

        result = self.create_access(personal, BusinessRole.PROFESIONAL)

        user = Usuario.objects.get(pk=result.user_id)
        self.assertSetEqual(
            set(user.groups.values_list('name', flat=True)),
            {BusinessRole.PROFESIONAL},
        )
        self.assertFalse(user.user_permissions.exists())

    def test_link_failure_rolls_back_created_user(self):
        personal = self.create_personal('link-rollback')
        email = 'link-rollback@test.com'

        with patch(
            'gestion.personal_access_services.link_user_to_personal',
            side_effect=RuntimeError('link unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                self.create_access(
                    personal,
                    BusinessRole.EMPLEADO,
                    email=email,
                )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario_id)
        self.assertFalse(Usuario.objects.filter(email=email).exists())

    def test_role_failure_rolls_back_user_link_and_link_audit(self):
        personal = self.create_personal('role-rollback')
        email = 'role-rollback@test.com'

        with patch(
            'gestion.personal_access_services.assign_validated_business_role',
            side_effect=RuntimeError('role unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                self.create_access(
                    personal,
                    BusinessRole.EMPLEADO,
                    email=email,
                )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario_id)
        self.assertFalse(Usuario.objects.filter(email=email).exists())
        self.assertFalse(
            Auditoria.objects.filter(tabla='PersonalUserLink').exists()
        )

    def test_compound_audit_failure_rolls_back_everything(self):
        personal = self.create_personal('audit-rollback')
        email = 'audit-rollback@test.com'
        real_create = Auditoria.objects.create

        def fail_compound_audit(*args, **kwargs):
            if kwargs.get('tabla') == PERSONAL_ACCESS_AUDIT_TABLE:
                raise RuntimeError('audit unavailable')
            return real_create(*args, **kwargs)

        with patch(
            'gestion.personal_access_services.Auditoria.objects.create',
            side_effect=fail_compound_audit,
        ):
            with self.assertRaises(RuntimeError):
                self.create_access(
                    personal,
                    BusinessRole.EMPLEADO,
                    email=email,
                )

        personal.refresh_from_db()
        self.assertIsNone(personal.usuario_id)
        self.assertFalse(Usuario.objects.filter(email=email).exists())
        self.assertFalse(
            Auditoria.objects.filter(
                tabla__in=(
                    'PersonalUserLink',
                    'UsuarioBusinessRole',
                    PERSONAL_ACCESS_AUDIT_TABLE,
                )
            ).exists()
        )

    def test_password_never_appears_in_audit(self):
        personal = self.create_personal('audit-password')
        raw_password = 'Unique!Temporary2026'

        self.create_access(
            personal,
            BusinessRole.EMPLEADO,
            raw_password=raw_password,
        )

        payload = json.dumps(list(
            Auditoria.objects.values('valor_anterior', 'valor_nuevo')
        ))
        self.assertNotIn(raw_password, payload)
        self.assertNotIn('password_hash', payload.lower())

    def test_password_is_persisted_as_hash(self):
        personal = self.create_personal('hashed-password')

        result = self.create_access(personal, BusinessRole.EMPLEADO)

        user = Usuario.objects.get(pk=result.user_id)
        self.assertNotEqual(user.password, self.strong_password)
        self.assertTrue(user.check_password(self.strong_password))

    def test_actor_without_required_permissions_is_rejected_before_creation(self):
        unauthorized = self.create_user('unauthorized-create@test.com')
        personal = self.create_personal('unauthorized')

        with self.assertRaises(PermissionDeniedForPersonalLink):
            self.create_access(
                personal,
                BusinessRole.EMPLEADO,
                actor=unauthorized,
            )

        self.assertIsNone(Personal.objects.get(pk=personal.pk).usuario_id)
        self.assertFalse(
            Usuario.objects.filter(email=f'access-{personal.pk}@test.com').exists()
        )

    def test_compound_audit_records_creation_context_and_component_events(self):
        personal = self.create_personal('audit-content')

        result = self.create_access(personal, BusinessRole.ADMINISTRADOR)

        audit = Auditoria.objects.get(tabla=PERSONAL_ACCESS_AUDIT_TABLE)
        self.assertEqual(audit.usuario, self.actor)
        self.assertEqual(audit.registro_id, personal.pk)
        self.assertEqual(audit.valor_nuevo['event'], PERSONAL_ACCESS_AUDIT_EVENT)
        self.assertEqual(audit.valor_nuevo['source'], PERSONAL_ACCESS_AUDIT_SOURCE)
        self.assertEqual(audit.valor_nuevo['personal_id'], personal.pk)
        self.assertEqual(audit.valor_nuevo['user_id'], result.user_id)
        self.assertEqual(audit.valor_nuevo['role'], BusinessRole.ADMINISTRADOR)
        self.assertEqual(audit.valor_nuevo['reason'], 'Alta inicial de acceso laboral')
        self.assertEqual(audit.valor_nuevo['link_audit_id'], result.link_audit_id)
        self.assertEqual(audit.valor_nuevo['role_audit_id'], result.role_audit_id)
        self.assertEqual(audit.pk, result.access_audit_id)
