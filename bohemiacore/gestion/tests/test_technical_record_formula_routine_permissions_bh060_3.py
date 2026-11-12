import shutil
import tempfile
from datetime import date, time, timedelta

from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    DetalleTurno,
    FichaTecnica,
    Habilidad,
    Personal,
    PersonalHabilidad,
    ReglaCuidado,
    Rutina,
    RutinaCliente,
    Servicio,
    Turno,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class TechnicalRecordFormulaRoutineAuthorizationTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp(prefix='bohemia-bh060-3-')
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.skill = Habilidad.objects.get(code='DIAGNOSTICO')
        self.manage_record = self.permission('manage_technical_record')
        self.manage_formulas = self.permission('manage_formulas')
        self.assign_routines = self.permission('assign_routines')
        self.manage_prices = self.permission('manage_prices')
        self.finalize_service = self.permission('finalize_service')
        self.create_diagnosis = self.permission('create_diagnosis')

        self.client_user, self.client_profile = self.create_client(
            'technical-owner@test.com'
        )
        self.other_client_user, self.other_client = self.create_client(
            'technical-other-client@test.com'
        )

        self.professional = self.user_with_role(
            'technical-professional@test.com',
            BusinessRole.PROFESIONAL,
        )
        self.professional_personal = self.create_personal(self.professional)
        self.assign_skill(self.professional_personal)

        self.other_professional = self.create_user(
            'technical-other-professional@test.com'
        )
        self.other_personal = self.create_personal(self.other_professional)
        self.assign_skill(self.other_personal)

        self.employee = self.user_with_role(
            'technical-employee@test.com',
            BusinessRole.EMPLEADO,
        )
        self.employee_personal = self.create_personal(self.employee)
        self.assign_skill(self.employee_personal)

        self.administrator = self.user_with_role(
            'technical-admin@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        self.admin_personal = self.create_personal(self.administrator)
        self.assign_skill(self.admin_personal)

        self.staff_without_permission = self.create_user(
            'technical-staff@test.com',
            is_staff=True,
        )
        staff_personal = self.create_personal(self.staff_without_permission)
        self.assign_skill(staff_personal)

        self.service = Servicio.objects.create(
            nombre='Color técnico BH0603',
            precio_base='100.00',
            duracion_estimada=60,
            plantilla_formula='BASE HISTÓRICA',
        )
        self.turno = Turno.objects.create(
            cliente=self.client_profile,
            profesional=self.professional_personal,
            fecha=timezone.localdate() + timedelta(days=2),
            hora_inicio=time(10, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        self.detail = DetalleTurno.objects.create(
            turno=self.turno,
            servicio=self.service,
            precio_historico='100.00',
            duracion_minutos=60,
        )
        self.other_turno = Turno.objects.create(
            cliente=self.other_client,
            profesional=self.other_personal,
            fecha=timezone.localdate() + timedelta(days=3),
            hora_inicio=time(11, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        self.other_detail = DetalleTurno.objects.create(
            turno=self.other_turno,
            servicio=self.service,
            precio_historico='100.00',
            duracion_minutos=60,
        )

        self.published_routine = self.create_routine(
            'Rutina publicada BH0603',
            'publicada',
        )
        self.second_published_routine = self.create_routine(
            'Segunda rutina BH0603',
            'publicada',
        )
        self.draft_routine = self.create_routine(
            'Rutina borrador BH0603',
            'borrador',
        )

        self.ficha_list = reverse('ficha-tecnica-list')
        self.routine_list = reverse('rutina-list')
        self.assignment_list = reverse('rutina-cliente-list')

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    @staticmethod
    def create_user(email, **flags):
        return Usuario.objects.create_user(email=email, **flags)

    def user_with_role(self, email, role):
        user = self.create_user(email)
        user.groups.add(Group.objects.get(name=role))
        return user

    def create_client(self, email, *, active=True, account_active=True):
        user = self.create_user(email, is_active=account_active)
        user.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        return user, Cliente.objects.create(usuario=user, activo=active)

    @staticmethod
    def create_personal(user, *, active=True):
        return Personal.objects.create(
            usuario=user,
            nombre='Actor',
            apellido=user.email.split('@')[0],
            rol='colorista',
            activo=active,
        )

    def assign_skill(self, personal, *, active=True):
        return PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=self.skill,
            activa=active,
        )

    def create_routine(self, name, state, *, creator=None):
        return Rutina.objects.create(
            nombre=name,
            objetivo='Cuidado capilar',
            descripcion='Copia histórica completa',
            archivo=SimpleUploadedFile(
                f'{name.replace(" ", "-")}.pdf',
                b'%PDF-1.4 routine',
                content_type='application/pdf',
            ),
            estado=state,
            creada_por=creator or self.administrator,
        )

    def create_granted_actor(self, email, *permissions, skill=True):
        actor = self.create_user(email)
        actor.user_permissions.add(*permissions)
        personal = self.create_personal(actor)
        if skill:
            self.assign_skill(personal)
        return actor, personal

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def ficha_payload(self, detail=None, **overrides):
        payload = {
            'detalle_turno': (detail or self.detail).pk,
            'observaciones_proceso': 'Proceso controlado',
        }
        payload.update(overrides)
        return payload

    def create_ficha(self, *, detail=None, author=None, formula='FÓRMULA 1'):
        return FichaTecnica.objects.create(
            detalle_turno=detail or self.detail,
            profesional_autor=author or self.professional,
            formula=formula,
            observaciones_proceso='Histórico técnico',
        )

    def test_anonymous_is_rejected_without_mutation(self):
        initial_fichas = FichaTecnica.objects.count()
        initial_assignments = RutinaCliente.objects.count()

        ficha = self.client.post(
            self.ficha_list,
            self.ficha_payload(),
            format='json',
        )
        assignment = self.client.post(
            self.assignment_list,
            {
                'cliente_id': self.client_profile.pk,
                'rutina_id': self.published_routine.pk,
            },
            format='json',
        )

        self.assertEqual(ficha.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(assignment.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(FichaTecnica.objects.count(), initial_fichas)
        self.assertEqual(RutinaCliente.objects.count(), initial_assignments)

    def test_staff_flag_and_employee_role_do_not_authorize_technical_record(self):
        for actor in (self.staff_without_permission, self.employee):
            self.authenticate(actor)
            with self.subTest(actor=actor.email):
                response = self.client.post(
                    self.ficha_list,
                    self.ficha_payload(),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertFalse(FichaTecnica.objects.exists())

    def test_professional_and_administrator_groups_work_without_is_staff(self):
        self.authenticate(self.professional)
        professional_response = self.client.post(
            self.ficha_list,
            self.ficha_payload(formula='FÓRMULA PROFESIONAL'),
            format='json',
        )

        self.turno.profesional = self.admin_personal
        self.turno.save(update_fields=['profesional'])
        FichaTecnica.objects.all().delete()
        self.authenticate(self.administrator)
        admin_response = self.client.post(
            self.ficha_list,
            self.ficha_payload(formula='FÓRMULA ADMIN'),
            format='json',
        )

        self.assertFalse(self.professional.is_staff)
        self.assertFalse(self.administrator.is_staff)
        self.assertEqual(professional_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(admin_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FichaTecnica.objects.get().profesional_autor, self.administrator)

    def test_individual_record_permission_without_formula_permission_is_separated(self):
        actor, personal = self.create_granted_actor(
            'record-only@test.com',
            self.manage_record,
        )
        self.turno.profesional = personal
        self.turno.save(update_fields=['profesional'])
        self.authenticate(actor)

        allowed = self.client.post(
            self.ficha_list,
            self.ficha_payload(),
            format='json',
        )
        FichaTecnica.objects.all().delete()
        denied = self.client.post(
            self.ficha_list,
            self.ficha_payload(formula='NO AUTORIZADA'),
            format='json',
        )

        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(FichaTecnica.objects.exists())

    def test_personal_skill_and_account_must_be_active_for_ficha(self):
        actors = []
        no_skill, _ = self.create_granted_actor(
            'record-no-skill@test.com',
            self.manage_record,
            skill=False,
        )
        actors.append(no_skill)
        inactive_personal, personal = self.create_granted_actor(
            'record-inactive-personal@test.com',
            self.manage_record,
        )
        personal.activo = False
        personal.save(update_fields=['activo'])
        actors.append(inactive_personal)
        inactive_skill, personal = self.create_granted_actor(
            'record-inactive-skill@test.com',
            self.manage_record,
        )
        personal.habilidades_personal.update(activa=False)
        actors.append(inactive_skill)
        inactive_account, _ = self.create_granted_actor(
            'record-inactive-account@test.com',
            self.manage_record,
        )
        inactive_account.is_active = False
        inactive_account.save(update_fields=['is_active'])
        actors.append(inactive_account)

        for actor in actors:
            self.authenticate(actor)
            with self.subTest(actor=actor.email):
                response = self.client.post(
                    self.ficha_list,
                    self.ficha_payload(),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(FichaTecnica.objects.exists())

    def test_technical_actor_cannot_create_or_read_foreign_professional_record(self):
        self.authenticate(self.professional)

        create_response = self.client.post(
            self.ficha_list,
            self.ficha_payload(detail=self.other_detail),
            format='json',
        )
        foreign = self.create_ficha(
            detail=self.other_detail,
            author=self.other_professional,
        )
        detail_response = self.client.get(
            reverse('ficha-tecnica-detail', args=[foreign.pk])
        )
        by_turno = self.client.get(
            reverse('ficha-tecnica-por-turno'),
            {'turno_id': self.other_turno.pk},
        )

        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(by_turno.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FichaTecnica.objects.count(), 1)

    def test_client_reads_only_owned_record_without_formula(self):
        own = self.create_ficha()
        foreign = self.create_ficha(
            detail=self.other_detail,
            author=self.other_professional,
        )
        self.authenticate(self.client_user)

        listing = self.client.get(self.ficha_list)
        own_detail = self.client.get(
            reverse('ficha-tecnica-detail', args=[own.pk])
        )
        foreign_detail = self.client.get(
            reverse('ficha-tecnica-detail', args=[foreign.pk])
        )
        foreign_client = self.client.get(
            reverse('ficha-tecnica-por-cliente'),
            {'cliente_id': self.other_client.pk},
        )

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        items = listing.data.get('results', listing.data)
        self.assertEqual([item['id'] for item in items], [own.pk])
        self.assertNotIn('formula', own_detail.data)
        self.assertNotIn('formula_base_servicio', own_detail.data)
        self.assertEqual(foreign_detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(foreign_client.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_cannot_write_own_or_foreign_record(self):
        ficha = self.create_ficha()
        self.authenticate(self.client_user)

        create_response = self.client.post(
            self.ficha_list,
            self.ficha_payload(),
            format='json',
        )
        update_response = self.client.patch(
            reverse('ficha-tecnica-detail', args=[ficha.pk]),
            {'observaciones_proceso': 'Alterada'},
            format='json',
        )

        ficha.refresh_from_db()
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ficha.observaciones_proceso, 'Histórico técnico')

    def test_record_update_preserves_author_detail_and_formula_permission(self):
        actor, personal = self.create_granted_actor(
            'record-update-only@test.com',
            self.manage_record,
        )
        self.turno.profesional = personal
        self.turno.save(update_fields=['profesional'])
        ficha = self.create_ficha(author=actor)
        self.authenticate(actor)
        url = reverse('ficha-tecnica-detail', args=[ficha.pk])

        formula_response = self.client.patch(
            url,
            {'formula': 'ALTERADA'},
            format='json',
        )
        spoof_response = self.client.patch(
            url,
            {
                'profesional_autor': self.other_professional.pk,
                'detalle_turno': self.other_detail.pk,
            },
            format='json',
        )

        ficha.refresh_from_db()
        self.assertEqual(formula_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(spoof_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ficha.formula, 'FÓRMULA 1')
        self.assertEqual(ficha.profesional_autor, actor)
        self.assertEqual(ficha.detalle_turno, self.detail)

    def test_ficha_delete_is_disabled_to_preserve_history(self):
        ficha = self.create_ficha()
        self.authenticate(self.professional)

        response = self.client.delete(
            reverse('ficha-tecnica-detail', args=[ficha.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(FichaTecnica.objects.filter(pk=ficha.pk).exists())

    def test_public_service_read_does_not_expose_formula_template(self):
        response = self.client.get(
            reverse('servicio-detail', args=[self.service.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('plantilla_formula', response.data)

    def test_formula_permission_with_skill_updates_only_formula_without_staff(self):
        actor, _ = self.create_granted_actor(
            'formula-only@test.com',
            self.manage_formulas,
        )
        self.authenticate(actor)
        url = reverse('servicio-detail', args=[self.service.pk])

        formula_response = self.client.patch(
            url,
            {'plantilla_formula': 'NUEVA FÓRMULA'},
            format='json',
        )
        price_response = self.client.patch(
            url,
            {'precio_base': '900.00'},
            format='json',
        )

        self.service.refresh_from_db()
        self.assertFalse(actor.is_staff)
        self.assertEqual(formula_response.status_code, status.HTTP_200_OK)
        self.assertEqual(price_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.service.plantilla_formula, 'NUEVA FÓRMULA')
        self.assertEqual(str(self.service.precio_base), '100.00')

    def test_manage_record_does_not_imply_formula_and_mixed_payload_is_atomic(self):
        record_actor, _ = self.create_granted_actor(
            'record-not-formula@test.com',
            self.manage_record,
        )
        price_actor, _ = self.create_granted_actor(
            'price-not-formula@test.com',
            self.manage_prices,
        )
        url = reverse('servicio-detail', args=[self.service.pk])

        self.authenticate(record_actor)
        record_response = self.client.patch(
            url,
            {'plantilla_formula': 'NO'},
            format='json',
        )
        self.authenticate(price_actor)
        mixed_response = self.client.patch(
            url,
            {'precio_base': '250.00', 'plantilla_formula': 'NO'},
            format='json',
        )

        self.service.refresh_from_db()
        self.assertEqual(record_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(mixed_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(str(self.service.precio_base), '100.00')
        self.assertEqual(self.service.plantilla_formula, 'BASE HISTÓRICA')

    def test_formula_permission_requires_active_personal_and_skill(self):
        no_skill, _ = self.create_granted_actor(
            'formula-no-skill@test.com',
            self.manage_formulas,
            skill=False,
        )
        inactive_personal, personal = self.create_granted_actor(
            'formula-inactive-personal@test.com',
            self.manage_formulas,
        )
        personal.activo = False
        personal.save(update_fields=['activo'])

        for actor in (no_skill, inactive_personal):
            self.authenticate(actor)
            with self.subTest(actor=actor.email):
                response = self.client.patch(
                    reverse('servicio-detail', args=[self.service.pk]),
                    {'plantilla_formula': 'NO'},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.service.refresh_from_db()
        self.assertEqual(self.service.plantilla_formula, 'BASE HISTÓRICA')

    def test_client_catalog_contains_only_published_routines(self):
        self.authenticate(self.client_user)

        response = self.client.get(self.routine_list)

        items = (
            response.data.get('results', response.data)
            if isinstance(response.data, dict)
            else response.data
        )
        ids = {item['id'] for item in items}
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.published_routine.pk, ids)
        self.assertIn(self.second_published_routine.pk, ids)
        self.assertNotIn(self.draft_routine.pk, ids)

    def test_assign_permission_administers_catalog_without_staff(self):
        actor = self.create_user('routine-grant@test.com')
        actor.user_permissions.add(self.assign_routines)
        self.authenticate(actor)

        response = self.client.patch(
            reverse('rutina-detail', args=[self.draft_routine.pk]),
            {'objetivo': 'Objetivo actualizado'},
            format='json',
        )

        self.draft_routine.refresh_from_db()
        self.assertFalse(actor.is_staff)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.draft_routine.objetivo, 'Objetivo actualizado')

    def test_staff_without_permission_cannot_administer_routines(self):
        self.authenticate(self.staff_without_permission)

        response = self.client.patch(
            reverse('rutina-detail', args=[self.draft_routine.pk]),
            {'objetivo': 'No autorizada'},
            format='json',
        )

        self.draft_routine.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.draft_routine.objetivo, 'Cuidado capilar')

    def test_client_selects_only_own_published_routine_on_both_routes(self):
        self.authenticate(self.client_user)

        canonical = self.client.post(
            reverse('rutina-seleccionar'),
            {'rutina_id': self.published_routine.pk},
            format='json',
        )
        alternative = self.client.post(
            reverse('prueba-rutina'),
            {'rutina_id': self.second_published_routine.pk},
            format='json',
        )

        self.assertEqual(canonical.status_code, status.HTTP_201_CREATED)
        self.assertEqual(alternative.status_code, status.HTTP_201_CREATED)
        assignments = RutinaCliente.objects.filter(cliente=self.client_profile)
        self.assertEqual(assignments.count(), 2)
        self.assertEqual(
            set(assignments.values_list('rutina_original_id', flat=True)),
            {self.published_routine.pk, self.second_published_routine.pk},
        )
        self.assertTrue(all(item.archivo for item in assignments))

    def test_client_cannot_inject_target_or_select_draft_and_duplicates(self):
        self.authenticate(self.client_user)
        initial = RutinaCliente.objects.count()

        injected = self.client.post(
            reverse('rutina-seleccionar'),
            {
                'rutina_id': self.published_routine.pk,
                'cliente_id': self.other_client.pk,
            },
            format='json',
        )
        draft = self.client.post(
            reverse('rutina-seleccionar'),
            {'rutina_id': self.draft_routine.pk},
            format='json',
        )
        first = self.client.post(
            reverse('rutina-seleccionar'),
            {'rutina_id': self.published_routine.pk},
            format='json',
        )
        duplicate = self.client.post(
            reverse('rutina-seleccionar'),
            {'rutina_id': self.published_routine.pk},
            format='json',
        )

        self.assertEqual(injected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(draft.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(RutinaCliente.objects.count(), initial + 1)
        self.assertFalse(
            RutinaCliente.objects.filter(cliente=self.other_client).exists()
        )

    def test_administrative_assignment_requires_exact_permission(self):
        formula_actor, _ = self.create_granted_actor(
            'formula-not-routine@test.com',
            self.manage_formulas,
        )
        assign_actor = self.create_user('assign-routine@test.com')
        assign_actor.user_permissions.add(self.assign_routines)
        payload = {
            'cliente_id': self.other_client.pk,
            'rutina_id': self.published_routine.pk,
        }

        self.authenticate(formula_actor)
        denied = self.client.post(self.assignment_list, payload, format='json')
        self.authenticate(assign_actor)
        allowed = self.client.post(self.assignment_list, payload, format='json')

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)
        assignment = RutinaCliente.objects.get()
        self.assertEqual(assignment.cliente, self.other_client)
        self.assertEqual(assignment.rutina_original, self.published_routine)

    def test_invalid_admin_assignment_payload_does_not_mutate(self):
        actor = self.create_user('assign-invalid@test.com')
        actor.user_permissions.add(self.assign_routines)
        self.authenticate(actor)
        _, inactive_client = self.create_client(
            'inactive-routine-client@test.com',
            active=False,
        )
        payloads = (
            {
                'cliente_id': 999999,
                'rutina_id': self.published_routine.pk,
            },
            {
                'cliente_id': inactive_client.pk,
                'rutina_id': self.published_routine.pk,
            },
            {
                'cliente_id': self.client_profile.pk,
                'rutina_id': self.draft_routine.pk,
            },
            {
                'cliente_id': self.client_profile.pk,
                'rutina_id': self.published_routine.pk,
                'actor_id': actor.pk,
            },
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    self.assignment_list,
                    payload,
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(RutinaCliente.objects.exists())

    def test_routine_copy_ownership_protects_read_update_and_delete(self):
        own = self.published_routine.asignar_a_cliente(self.client_profile)
        foreign = self.second_published_routine.asignar_a_cliente(
            self.other_client
        )
        self.authenticate(self.client_user)

        listing = self.client.get(self.assignment_list)
        foreign_detail = self.client.get(
            reverse('rutina-cliente-detail', args=[foreign.pk])
        )
        foreign_update = self.client.post(
            reverse(
                'rutina-cliente-actualizar-desde-original',
                args=[foreign.pk],
            )
        )
        foreign_delete = self.client.delete(
            reverse('rutina-cliente-detail', args=[foreign.pk])
        )
        own_delete = self.client.delete(
            reverse('rutina-cliente-detail', args=[own.pk])
        )

        items = listing.data.get('results', listing.data)
        self.assertEqual([item['id'] for item in items], [own.pk])
        self.assertEqual(foreign_detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(foreign_update.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(foreign_delete.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(own_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(RutinaCliente.objects.filter(pk=foreign.pk).exists())

    def test_inactive_account_and_client_profile_cannot_use_routines(self):
        inactive_user, _ = self.create_client(
            'inactive-routine-account@test.com',
            account_active=False,
        )
        profile_user, _ = self.create_client(
            'inactive-routine-profile@test.com',
            active=False,
        )

        for actor in (inactive_user, profile_user):
            self.authenticate(actor)
            with self.subTest(actor=actor.email):
                catalog = self.client.get(self.routine_list)
                selection = self.client.post(
                    reverse('rutina-seleccionar'),
                    {'rutina_id': self.published_routine.pk},
                    format='json',
                )
                if actor.is_active:
                    self.assertEqual(catalog.status_code, status.HTTP_200_OK)
                else:
                    self.assertEqual(catalog.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(selection.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(RutinaCliente.objects.exists())

    def test_cu11_internal_assignment_does_not_depend_on_assign_permission(self):
        actor, personal = self.create_granted_actor(
            'cu11-finalizer@test.com',
            self.finalize_service,
            self.create_diagnosis,
        )
        self.assertFalse(actor.has_perm('gestion.assign_routines'))
        self.turno.profesional = personal
        self.turno.save(update_fields=['profesional'])
        ReglaCuidado.objects.create(
            servicio=self.service,
            tipo='HABITO',
            descripcion='Usar cuidado técnico',
            dias_duracion=7,
            rutina=self.draft_routine,
        )
        self.authenticate(actor)

        response = self.client.post(
            reverse('turno-finalizar-turno', args=[self.turno.pk]),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        assignment = RutinaCliente.objects.get(
            cliente=self.client_profile,
            rutina_original=self.draft_routine,
        )
        self.assertEqual(assignment.version_asignada, self.draft_routine.version)
        self.assertEqual(assignment.descripcion, self.draft_routine.descripcion)
        self.assertTrue(assignment.archivo)
