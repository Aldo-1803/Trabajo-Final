from datetime import date, time
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    Auditoria,
    Equipamiento,
    HorarioLaboral,
    Personal,
    RequisitoServicio,
    Servicio,
    TipoEquipamiento,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class RecordingStorage:
    def __init__(self, *, fail_url=False):
        self.fail_url = fail_url
        self.files = {}
        self.saved_names = []
        self.deleted_names = []

    def save(self, name, content):
        self.saved_names.append(name)
        self.files[name] = content.read()
        return name

    def url(self, name):
        if self.fail_url:
            raise RuntimeError('storage url unavailable')
        return f'/media/{name}'

    def exists(self, name):
        return name in self.files

    def delete(self, name):
        self.deleted_names.append(name)
        self.files.pop(name, None)


class ResidualAuthorizationClosureBh060F1Tests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manage_configuration = cls.permission('manage_configuration')
        cls.manage_products = cls.permission('manage_products')

        cls.client_user = cls.user_with_role(
            'f1-client@test.com',
            BusinessRole.CLIENTE,
        )
        Cliente.objects.create(usuario=cls.client_user)
        cls.employee = cls.user_with_role(
            'f1-employee@test.com',
            BusinessRole.EMPLEADO,
        )
        cls.professional = cls.user_with_role(
            'f1-professional@test.com',
            BusinessRole.PROFESIONAL,
        )
        cls.administrator = cls.user_with_role(
            'f1-administrator@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        cls.staff_without_permission = cls.create_user(
            'f1-staff@test.com',
            is_staff=True,
        )
        cls.configuration_manager = cls.create_user(
            'f1-configuration@test.com'
        )
        cls.configuration_manager.user_permissions.add(cls.manage_configuration)
        cls.product_manager = cls.create_user('f1-product@test.com')
        cls.product_manager.user_permissions.add(cls.manage_products)
        cls.inactive_manager = cls.create_user(
            'f1-inactive@test.com',
            is_active=False,
        )
        cls.inactive_manager.user_permissions.add(
            cls.manage_configuration,
            cls.manage_products,
        )

        cls.target_personal = Personal.objects.create(
            nombre='Profesional',
            apellido='Objetivo',
            rol='colorista',
            activo=True,
        )
        cls.other_personal = Personal.objects.create(
            nombre='Profesional',
            apellido='Alternativo',
            rol='asistente',
            activo=True,
        )
        cls.schedule = HorarioLaboral.objects.create(
            personal=cls.target_personal,
            dia_semana=0,
            fecha_desde=date(2026, 11, 9),
            fecha_hasta=date(2026, 11, 30),
            hora_inicio=time(9, 0),
            hora_fin=time(12, 0),
        )

        cls.service = Servicio.objects.create(
            nombre='Servicio F1',
            precio_base='100.00',
            duracion_estimada=30,
        )
        cls.other_service = Servicio.objects.create(
            nombre='Servicio alternativo F1',
            precio_base='120.00',
            duracion_estimada=40,
        )
        cls.equipment_type = TipoEquipamiento.objects.create(
            nombre='Tipo F1',
        )
        cls.other_equipment_type = TipoEquipamiento.objects.create(
            nombre='Tipo alternativo F1',
        )
        Equipamiento.objects.create(
            codigo='F1-EQ-1',
            nombre='Equipo F1',
            tipo=cls.equipment_type,
            is_active=True,
        )
        Equipamiento.objects.create(
            codigo='F1-EQ-2',
            nombre='Equipo alternativo F1',
            tipo=cls.other_equipment_type,
            is_active=True,
        )
        cls.requirement = RequisitoServicio.objects.create(
            servicio=cls.service,
            tipo_equipamiento=cls.equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )

        cls.schedule_list_url = reverse('horariolaboral-list')
        cls.schedule_detail_url = reverse(
            'horariolaboral-detail',
            args=[cls.schedule.pk],
        )
        cls.configure_range_url = reverse(
            'horariolaboral-configurar-rango'
        )
        cls.clear_schedule_url = reverse('horariolaboral-limpiar-agenda')
        cls.requirement_list_url = reverse('requisito-servicio-list')
        cls.requirement_detail_url = reverse(
            'requisito-servicio-detail',
            args=[cls.requirement.pk],
        )
        cls.upload_url = reverse('upload-imagen')

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(email=email, **extra_fields)

    @classmethod
    def user_with_role(cls, email, role):
        user = cls.create_user(email)
        user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def image(*, name='product.png', content_type='image/png', size=16):
        return SimpleUploadedFile(
            name,
            b'\x89PNG' + (b'x' * size),
            content_type=content_type,
        )

    @staticmethod
    def schedule_payload(**overrides):
        payload = {
            'personal': None,
            'dia_semana': 2,
            'fecha_desde': '2026-11-09',
            'fecha_hasta': '2026-11-30',
            'hora_inicio': '13:00:00',
            'hora_fin': '17:00:00',
            'permite_diseno_color': True,
            'permite_complemento': True,
            'activo': True,
        }
        payload.update(overrides)
        return payload

    def requirement_payload(self, **overrides):
        payload = {
            'servicio': self.other_service.pk,
            'tipo_equipamiento': self.equipment_type.pk,
            'obligatorio': True,
            'cantidad_minima': 1,
        }
        payload.update(overrides)
        return payload

    def range_payload(self, **overrides):
        payload = {
            'fecha_desde': '2026-12-01',
            'fecha_hasta': '2026-12-31',
            'todos_profesionales': False,
            'patron': [
                {
                    'dia': 1,
                    'hora_inicio': '10:00',
                    'hora_fin': '12:00',
                    'permite_diseno': True,
                    'permite_complemento': True,
                    'personal_id': self.other_personal.pk,
                }
            ],
        }
        payload.update(overrides)
        return payload

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def assert_configuration_mutations_denied(self, user, expected_status):
        self.client.force_authenticate(user=user)
        schedule_count = HorarioLaboral.objects.count()
        requirement_count = RequisitoServicio.objects.count()
        audit_count = Auditoria.objects.count()
        original_schedule = (
            self.schedule.dia_semana,
            self.schedule.hora_inicio,
            self.schedule.hora_fin,
        )
        original_requirement = (
            self.requirement.servicio_id,
            self.requirement.tipo_equipamiento_id,
            self.requirement.cantidad_minima,
        )
        malicious = {
            'is_staff': True,
            'is_superuser': True,
            'user_permissions': ['gestion.manage_configuration'],
        }

        requests = (
            self.client.post(
                self.schedule_list_url,
                {**self.schedule_payload(), **malicious},
                format='json',
            ),
            self.client.patch(
                self.schedule_detail_url,
                {'dia_semana': 5, **malicious},
                format='json',
            ),
            self.client.delete(self.schedule_detail_url),
            self.client.post(
                self.configure_range_url,
                {**self.range_payload(), **malicious},
                format='json',
            ),
            self.client.delete(
                self.clear_schedule_url,
                {'personal_id': self.target_personal.pk},
                format='json',
                QUERY_STRING=f'personal_id={self.target_personal.pk}',
            ),
            self.client.post(
                self.requirement_list_url,
                {**self.requirement_payload(), **malicious},
                format='json',
            ),
            self.client.patch(
                self.requirement_detail_url,
                {'cantidad_minima': 9, **malicious},
                format='json',
            ),
            self.client.delete(self.requirement_detail_url),
        )
        for response in requests:
            self.assertEqual(response.status_code, expected_status)

        self.assertEqual(HorarioLaboral.objects.count(), schedule_count)
        self.assertEqual(RequisitoServicio.objects.count(), requirement_count)
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.schedule.refresh_from_db()
        self.requirement.refresh_from_db()
        self.assertEqual(
            (
                self.schedule.dia_semana,
                self.schedule.hora_inicio,
                self.schedule.hora_fin,
            ),
            original_schedule,
        )
        self.assertEqual(
            (
                self.requirement.servicio_id,
                self.requirement.tipo_equipamiento_id,
                self.requirement.cantidad_minima,
            ),
            original_requirement,
        )

    def test_anonymous_cannot_read_or_mutate_any_closed_surface(self):
        self.assertEqual(
            self.client.get(self.schedule_list_url).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.get(self.requirement_list_url).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assert_configuration_mutations_denied(
            None,
            status.HTTP_401_UNAUTHORIZED,
        )
        storage = RecordingStorage()
        with patch('gestion.views.default_storage', storage):
            response = self.client.post(
                self.upload_url,
                {'imagen': self.image()},
                format='multipart',
            )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(storage.saved_names, [])

    def test_client_staff_and_inactive_grants_have_zero_authority(self):
        for actor in (
            self.client_user,
            self.staff_without_permission,
            self.inactive_manager,
        ):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                self.assertEqual(
                    self.client.get(self.schedule_list_url).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get(self.requirement_list_url).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                storage = RecordingStorage()
                with patch('gestion.views.default_storage', storage):
                    uploaded = self.client.post(
                        self.upload_url,
                        {'imagen': self.image()},
                        format='multipart',
                    )
                self.assertEqual(
                    uploaded.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(storage.saved_names, [])
                self.assert_configuration_mutations_denied(
                    actor,
                    status.HTTP_403_FORBIDDEN,
                )
                storage = RecordingStorage()
                with patch('gestion.views.default_storage', storage):
                    response = self.client.post(
                        self.upload_url,
                        {'imagen': self.image()},
                        format='multipart',
                    )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(storage.saved_names, [])

    def test_employee_and_professional_have_schedule_read_only(self):
        for actor in (self.employee, self.professional):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                listed = self.client.get(self.schedule_list_url)
                detail = self.client.get(self.schedule_detail_url)
                self.assertEqual(listed.status_code, status.HTTP_200_OK)
                self.assertEqual(detail.status_code, status.HTTP_200_OK)
                self.assert_configuration_mutations_denied(
                    actor,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get(self.requirement_list_url).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_configuration_grant_without_staff_controls_schedule_crud(self):
        actor = self.configuration_manager
        self.assertFalse(actor.is_staff)
        self.authenticate(actor)

        listed = self.client.get(self.schedule_list_url)
        detail = self.client.get(self.schedule_detail_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)

        created = self.client.post(
            self.schedule_list_url,
            self.schedule_payload(personal=self.other_personal.pk),
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        created_url = reverse('horariolaboral-detail', args=[created.data['id']])

        patched = self.client.patch(
            created_url,
            {'hora_fin': '18:00:00'},
            format='json',
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        replaced = self.client.put(
            created_url,
            self.schedule_payload(
                personal=self.other_personal.pk,
                dia_semana=3,
                hora_inicio='14:00:00',
                hora_fin='18:00:00',
            ),
            format='json',
        )
        self.assertEqual(replaced.status_code, status.HTTP_200_OK)
        deleted = self.client.delete(created_url)
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            HorarioLaboral.objects.filter(pk=created.data['id']).exists()
        )

        storage = RecordingStorage()
        with patch('gestion.views.default_storage', storage):
            uploaded = self.client.post(
                self.upload_url,
                {'imagen': self.image()},
                format='multipart',
            )
        self.assertEqual(uploaded.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(storage.saved_names, [])

    def test_configuration_grant_controls_mass_actions_atomically(self):
        self.authenticate(self.configuration_manager)
        initial_count = HorarioLaboral.objects.count()

        created = self.client.post(
            self.configure_range_url,
            self.range_payload(),
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(HorarioLaboral.objects.count(), initial_count + 1)

        cleared = self.client.delete(
            f'{self.clear_schedule_url}?personal_id={self.other_personal.pk}'
        )
        self.assertEqual(cleared.status_code, status.HTTP_200_OK)
        self.assertFalse(
            HorarioLaboral.objects.filter(personal=self.other_personal).exists()
        )

        count_before_invalid = HorarioLaboral.objects.count()
        invalid = self.range_payload(
            patron=[
                self.range_payload()['patron'][0],
                {
                    **self.range_payload()['patron'][0],
                    'personal_id': 999999,
                },
            ]
        )
        rejected = self.client.post(
            self.configure_range_url,
            invalid,
            format='json',
        )
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(HorarioLaboral.objects.count(), count_before_invalid)

    def test_configuration_grant_without_staff_controls_requirement_crud(self):
        actor = self.configuration_manager
        self.assertFalse(actor.is_staff)
        self.authenticate(actor)

        listed = self.client.get(
            self.requirement_list_url,
            {'servicio_id': self.service.pk},
        )
        detail = self.client.get(self.requirement_detail_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        listed_results = (
            listed.data['results']
            if isinstance(listed.data, dict)
            else listed.data
        )
        self.assertEqual(len(listed_results), 1)
        self.assertEqual(listed_results[0]['servicio'], self.service.pk)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)

        created = self.client.post(
            self.requirement_list_url,
            self.requirement_payload(),
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        created_url = reverse(
            'requisito-servicio-detail',
            args=[created.data['id']],
        )

        patched = self.client.patch(
            created_url,
            {'cantidad_minima': 2},
            format='json',
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        replaced = self.client.put(
            created_url,
            self.requirement_payload(
                tipo_equipamiento=self.other_equipment_type.pk,
                obligatorio=False,
                cantidad_minima=3,
            ),
            format='json',
        )
        self.assertEqual(replaced.status_code, status.HTTP_200_OK)
        deleted = self.client.delete(created_url)
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            RequisitoServicio.objects.filter(pk=created.data['id']).exists()
        )

    def test_requirement_rejects_type_without_active_equipment_without_mutation(self):
        inactive_type = TipoEquipamiento.objects.create(nombre='Sin equipo activo')
        Equipamiento.objects.create(
            codigo='F1-EQ-INACTIVE',
            nombre='Equipo inactivo F1',
            tipo=inactive_type,
            is_active=False,
        )
        self.authenticate(self.configuration_manager)
        original = (
            self.requirement.tipo_equipamiento_id,
            self.requirement.cantidad_minima,
        )

        response = self.client.patch(
            self.requirement_detail_url,
            {
                'tipo_equipamiento': inactive_type.pk,
                'cantidad_minima': 8,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.requirement.refresh_from_db()
        self.assertEqual(
            (
                self.requirement.tipo_equipamiento_id,
                self.requirement.cantidad_minima,
            ),
            original,
        )

    def test_product_grant_without_staff_uploads_only_to_safe_generated_path(self):
        actor = self.product_manager
        self.assertFalse(actor.is_staff)
        self.authenticate(actor)
        storage = RecordingStorage()

        with patch('gestion.views.default_storage', storage):
            response = self.client.post(
                self.upload_url,
                {
                    'imagen': self.image(
                        name='../../malicious.php',
                        content_type='image/png',
                    )
                },
                format='multipart',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(storage.saved_names), 1)
        saved_name = storage.saved_names[0]
        self.assertTrue(saved_name.startswith('productos/'))
        self.assertTrue(saved_name.endswith('.png'))
        self.assertNotIn('malicious', saved_name)
        self.assertNotIn('..', saved_name)
        self.assertEqual(response.data['url'], f'/media/{saved_name}')

        self.assertEqual(
            self.client.get(self.schedule_list_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.get(self.requirement_list_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_upload_rejects_invalid_type_and_size_without_storage_write(self):
        self.authenticate(self.product_manager)
        storage = RecordingStorage()

        with patch('gestion.views.default_storage', storage):
            invalid_type = self.client.post(
                self.upload_url,
                {
                    'imagen': self.image(
                        name='payload.svg',
                        content_type='image/svg+xml',
                    )
                },
                format='multipart',
            )
            oversized = self.client.post(
                self.upload_url,
                {
                    'imagen': self.image(
                        size=(5 * 1024 * 1024) + 1,
                    )
                },
                format='multipart',
            )

        self.assertEqual(invalid_type.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(oversized.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(storage.saved_names, [])

    def test_upload_cleans_saved_file_when_storage_url_fails(self):
        self.authenticate(self.product_manager)
        storage = RecordingStorage(fail_url=True)

        with patch('gestion.views.default_storage', storage):
            response = self.client.post(
                self.upload_url,
                {'imagen': self.image()},
                format='multipart',
            )

        self.assertEqual(
            response.status_code,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        self.assertEqual(len(storage.saved_names), 1)
        self.assertEqual(storage.deleted_names, storage.saved_names)
        self.assertEqual(storage.files, {})

    def test_administrator_role_works_without_staff_on_all_three_surfaces(self):
        actor = self.administrator
        self.assertFalse(actor.is_staff)
        self.authenticate(actor)

        self.assertEqual(
            self.client.get(self.schedule_list_url).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(self.requirement_list_url).status_code,
            status.HTTP_200_OK,
        )
        created = self.client.post(
            self.configure_range_url,
            self.range_payload(
                patron=[
                    {
                        **self.range_payload()['patron'][0],
                        'personal_id': self.target_personal.pk,
                        'dia': 4,
                    }
                ]
            ),
            format='json',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        storage = RecordingStorage()
        with patch('gestion.views.default_storage', storage):
            uploaded = self.client.post(
                self.upload_url,
                {'imagen': self.image(name='admin.webp', content_type='image/webp')},
                format='multipart',
            )
        self.assertEqual(uploaded.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(storage.saved_names), 1)
