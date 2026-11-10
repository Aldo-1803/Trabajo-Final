from types import SimpleNamespace

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.effective_access import (
    CAPABILITY_CONTENT_AUTHOR,
    CAPABILITY_CONTENT_MANAGE_GLOBAL,
    CAPABILITY_DIAGNOSIS_CREATE,
    CAPABILITY_SERVICE_FORMULA_MANAGE,
    CAPABILITY_TECHNICAL_BOOKING_REVIEW,
    CAPABILITY_TECHNICAL_RECORD_MANAGE,
    CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL,
    SESSION_CAPABILITY_NAMES,
)
from gestion.models import (
    ContenidoEducativo,
    Habilidad,
    Personal,
    PersonalHabilidad,
)
from gestion.permissions import (
    CanCreateDiagnosisWithSkill,
    CanManagePricesOrFormulas,
    CanManageTechnicalRecordWithSkill,
    CanReadOwnedOrManageDiagnosis,
    CanReadOwnedOrManageTechnicalRecord,
    CanReviewTechnicalBooking,
)
from gestion.technical_booking_request_services import (
    TechnicalBookingRequestPermissionDenied,
    reviewer_personal,
)
from usuarios.models import Usuario
from usuarios.roles import BusinessPermission, BusinessRole


class CurrentSessionCapabilityApiTests(APITestCase):
    def setUp(self):
        self.url = reverse('current-session')
        self.diagnosis_skill = Habilidad.objects.get(code='DIAGNOSTICO')

    @staticmethod
    def create_user(suffix, **extra_fields):
        return Usuario.objects.create_user(
            email=f'{suffix}@capabilities.test',
            password='CapabilityPassword!2026',
            first_name='Capability',
            last_name='Actor',
            **extra_fields,
        )

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    @staticmethod
    def permission(label):
        app_label, codename = label.split('.', 1)
        return Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )

    def grant(self, user, *permissions):
        user.user_permissions.add(*[
            self.permission(permission) for permission in permissions
        ])

    @staticmethod
    def create_personal(user, *, active=True, name='Capability'):
        return Personal.objects.create(
            usuario=user,
            nombre=name,
            apellido='Actor',
            rol='colorista',
            activo=active,
        )

    def assign_diagnosis_skill(self, personal, *, active=True):
        return PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=self.diagnosis_skill,
            activa=active,
        )

    def get_session(self, user):
        self.client.force_authenticate(user)
        return self.client.get(self.url)

    def capabilities(self, user):
        response = self.get_session(user)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data['capabilities']

    @staticmethod
    def request_for(user):
        return SimpleNamespace(user=user)

    @staticmethod
    def create_content(title, author, state='BORRADOR'):
        return ContenidoEducativo.objects.create(
            titulo=title,
            descripcion=f'Descripción {title}',
            contenido_texto=f'Texto {title}',
            tipo='TEXTO',
            estado=state,
            autor=author,
        )

    def test_permission_without_skill_denies_every_technical_capability(self):
        user = self.create_user('permission-no-skill')
        self.create_personal(user)
        self.grant(
            user,
            BusinessPermission.REVIEW_TECHNICAL_BOOKING,
            BusinessPermission.CREATE_DIAGNOSIS,
            BusinessPermission.MANAGE_TECHNICAL_RECORD,
            BusinessPermission.MANAGE_FORMULAS,
        )

        capabilities = self.capabilities(user)

        for name in (
            CAPABILITY_TECHNICAL_BOOKING_REVIEW,
            CAPABILITY_DIAGNOSIS_CREATE,
            CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL,
            CAPABILITY_TECHNICAL_RECORD_MANAGE,
            CAPABILITY_SERVICE_FORMULA_MANAGE,
        ):
            with self.subTest(capability=name):
                self.assertFalse(capabilities[name])
        self.assertTrue(capabilities[CAPABILITY_CONTENT_AUTHOR])

    def test_permission_and_active_skill_match_real_permission_classes(self):
        user = self.create_user('permission-and-skill')
        personal = self.create_personal(user)
        self.assign_diagnosis_skill(personal)
        self.grant(
            user,
            BusinessPermission.REVIEW_TECHNICAL_BOOKING,
            BusinessPermission.CREATE_DIAGNOSIS,
            BusinessPermission.MANAGE_TECHNICAL_RECORD,
            BusinessPermission.MANAGE_FORMULAS,
        )

        capabilities = self.capabilities(user)
        request = self.request_for(user)

        parity = (
            (
                CAPABILITY_TECHNICAL_BOOKING_REVIEW,
                CanReviewTechnicalBooking(),
            ),
            (CAPABILITY_DIAGNOSIS_CREATE, CanCreateDiagnosisWithSkill()),
            (
                CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL,
                CanReadOwnedOrManageDiagnosis(),
            ),
            (
                CAPABILITY_TECHNICAL_RECORD_MANAGE,
                CanManageTechnicalRecordWithSkill(),
            ),
            (
                CAPABILITY_SERVICE_FORMULA_MANAGE,
                CanManagePricesOrFormulas(),
            ),
        )
        for capability, permission in parity:
            with self.subTest(capability=capability):
                self.assertTrue(capabilities[capability])
                self.assertEqual(
                    capabilities[capability],
                    permission.has_permission(request, None),
                )
        self.assertTrue(
            CanReadOwnedOrManageTechnicalRecord().has_permission(request, None)
        )
        self.assertEqual(
            capabilities[CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL],
            CanReadOwnedOrManageTechnicalRecord().has_permission(request, None),
        )
        self.assertEqual(reviewer_personal(user), personal)

    def test_inactive_personal_denies_skill_and_content_authorship(self):
        user = self.create_user('inactive-personal')
        personal = self.create_personal(user, active=False)
        self.assign_diagnosis_skill(personal)
        self.assign_role(user, BusinessRole.PROFESIONAL)

        capabilities = self.capabilities(user)

        self.assertFalse(capabilities[CAPABILITY_CONTENT_AUTHOR])
        for name in SESSION_CAPABILITY_NAMES:
            if name != CAPABILITY_CONTENT_MANAGE_GLOBAL:
                self.assertFalse(capabilities[name])
        with self.assertRaises(TechnicalBookingRequestPermissionDenied):
            reviewer_personal(user)

    def test_inactive_skill_or_assignment_denies_technical_capabilities(self):
        inactive_assignment = self.create_user('inactive-assignment')
        personal = self.create_personal(inactive_assignment)
        self.assign_diagnosis_skill(personal, active=False)
        self.grant(
            inactive_assignment,
            BusinessPermission.CREATE_DIAGNOSIS,
        )
        self.assertFalse(self.capabilities(inactive_assignment)[
            CAPABILITY_DIAGNOSIS_CREATE
        ])

        inactive_skill = self.create_user('inactive-skill')
        personal = self.create_personal(inactive_skill)
        self.assign_diagnosis_skill(personal)
        self.grant(inactive_skill, BusinessPermission.CREATE_DIAGNOSIS)
        self.diagnosis_skill.activa = False
        self.diagnosis_skill.save(update_fields=['activa'])
        self.assertFalse(self.capabilities(inactive_skill)[
            CAPABILITY_DIAGNOSIS_CREATE
        ])

    def test_skill_without_permission_does_not_invent_capabilities(self):
        user = self.create_user('skill-no-permission')
        personal = self.create_personal(user)
        self.assign_diagnosis_skill(personal)

        capabilities = self.capabilities(user)

        self.assertTrue(capabilities[CAPABILITY_CONTENT_AUTHOR])
        for name in (
            CAPABILITY_TECHNICAL_BOOKING_REVIEW,
            CAPABILITY_DIAGNOSIS_CREATE,
            CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL,
            CAPABILITY_TECHNICAL_RECORD_MANAGE,
            CAPABILITY_SERVICE_FORMULA_MANAGE,
            CAPABILITY_CONTENT_MANAGE_GLOBAL,
        ):
            self.assertFalse(capabilities[name])

    def test_business_role_inherited_permissions_need_and_use_real_skill(self):
        user = self.create_user('professional-role')
        personal = self.create_personal(user)
        self.assign_diagnosis_skill(personal)
        self.assign_role(user, BusinessRole.PROFESIONAL)

        response = self.get_session(user)
        capabilities = response.data['capabilities']

        for permission in (
            BusinessPermission.REVIEW_TECHNICAL_BOOKING,
            BusinessPermission.CREATE_DIAGNOSIS,
            BusinessPermission.MANAGE_TECHNICAL_RECORD,
            BusinessPermission.MANAGE_FORMULAS,
        ):
            self.assertIn(permission, response.data['permissions'])
        for name in (
            CAPABILITY_TECHNICAL_BOOKING_REVIEW,
            CAPABILITY_DIAGNOSIS_CREATE,
            CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL,
            CAPABILITY_TECHNICAL_RECORD_MANAGE,
            CAPABILITY_SERVICE_FORMULA_MANAGE,
            CAPABILITY_CONTENT_AUTHOR,
        ):
            self.assertTrue(capabilities[name])
        self.assertFalse(capabilities[CAPABILITY_CONTENT_MANAGE_GLOBAL])

    def test_technical_group_and_individual_grants_are_effective(self):
        group_user = self.create_user('technical-group')
        personal = self.create_personal(group_user)
        self.assign_diagnosis_skill(personal)
        technical_group = Group.objects.create(name='BH062_TECHNICAL_FORMULA')
        technical_group.permissions.add(
            self.permission(BusinessPermission.MANAGE_FORMULAS)
        )
        group_user.groups.add(technical_group)

        individual_user = self.create_user('individual-grant')
        personal = self.create_personal(individual_user)
        self.assign_diagnosis_skill(personal)
        self.grant(
            individual_user,
            BusinessPermission.REVIEW_TECHNICAL_BOOKING,
        )

        group_response = self.get_session(group_user)
        individual_response = self.get_session(individual_user)

        self.assertIsNone(group_response.data['business_role'])
        self.assertTrue(group_response.data['capabilities'][
            CAPABILITY_SERVICE_FORMULA_MANAGE
        ])
        self.assertIn(
            BusinessPermission.MANAGE_FORMULAS,
            group_response.data['permissions'],
        )
        self.assertIsNone(individual_response.data['business_role'])
        self.assertTrue(individual_response.data['capabilities'][
            CAPABILITY_TECHNICAL_BOOKING_REVIEW
        ])

    def test_is_staff_without_business_authority_has_no_capability(self):
        user = self.create_user('staff-only', is_staff=True)

        response = self.get_session(user)

        self.assertTrue(all(
            value is False
            for value in response.data['capabilities'].values()
        ))
        self.assertNotIn('is_staff', response.data['user'])
        self.assertNotIn('is_superuser', response.data['user'])

    def test_content_author_and_global_manager_remain_separate(self):
        author_user = self.create_user('content-author')
        author = self.create_personal(author_user, name='Author')
        other_user = self.create_user('other-author')
        other = self.create_personal(other_user, name='Other')
        own = self.create_content('Own', author)
        foreign_public = self.create_content('Foreign', other, 'PUBLICADO')

        manager = self.create_user('content-manager')
        self.grant(manager, BusinessPermission.MANAGE_CONTENT)

        author_capabilities = self.capabilities(author_user)
        manager_capabilities = self.capabilities(manager)

        self.assertTrue(author_capabilities[CAPABILITY_CONTENT_AUTHOR])
        self.assertFalse(author_capabilities[CAPABILITY_CONTENT_MANAGE_GLOBAL])
        self.assertFalse(manager_capabilities[CAPABILITY_CONTENT_AUTHOR])
        self.assertTrue(manager_capabilities[CAPABILITY_CONTENT_MANAGE_GLOBAL])

        self.client.force_authenticate(author_user)
        own_response = self.client.patch(
            reverse('contenido-educativo-detail', args=[own.pk]),
            {'titulo': 'Own updated'},
            format='json',
        )
        foreign_response = self.client.patch(
            reverse('contenido-educativo-detail', args=[foreign_public.pk]),
            {'titulo': 'Forbidden'},
            format='json',
        )
        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(foreign_response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(manager)
        manager_edit = self.client.patch(
            reverse('contenido-educativo-detail', args=[own.pk]),
            {'titulo': 'Globally managed'},
            format='json',
        )
        manager_create = self.client.post(
            reverse('contenido-educativo-list'),
            {
                'titulo': 'No author',
                'descripcion': 'No active Personal',
                'contenido_texto': 'Not created',
                'tipo': 'TEXTO',
                'estado': 'BORRADOR',
            },
            format='json',
        )
        self.assertEqual(manager_edit.status_code, status.HTTP_200_OK)
        self.assertEqual(manager_create.status_code, status.HTTP_403_FORBIDDEN)

    def test_contract_is_boolean_only_compatible_and_does_not_leak_admin_data(self):
        user = self.create_user('contract', is_staff=True)
        personal = self.create_personal(user)
        self.assign_diagnosis_skill(personal)
        self.grant(user, BusinessPermission.CREATE_DIAGNOSIS)

        response = self.get_session(user)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertSetEqual(
            set(response.data),
            {'user', 'business_role', 'permissions', 'profiles', 'capabilities'},
        )
        self.assertTupleEqual(
            tuple(response.data['capabilities']),
            SESSION_CAPABILITY_NAMES,
        )
        self.assertTrue(all(
            type(value) is bool
            for value in response.data['capabilities'].values()
        ))
        serialized = str(response.data).lower()
        for forbidden in (
            'is_staff',
            'is_superuser',
            'user_permissions',
            'permission_sources',
            'technical_groups',
            'skills',
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertIn('no-store', response['Cache-Control'])
