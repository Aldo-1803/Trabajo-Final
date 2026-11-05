from datetime import time

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    CategoriaServicio,
    CueroCabelludo,
    DetalleTurno,
    DiagnosticoCapilar,
    Equipamiento,
    EstadoGeneral,
    GrosorCabello,
    PorosidadCabello,
    ReglaDiagnostico,
    RequisitoServicio,
    Servicio,
    TipoCabello,
    TipoEquipamiento,
    Turno,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessPermission, BusinessRole


class CatalogAndEquipmentPermissionTests(APITestCase):
    CATALOG_SPECS = (
        ('tipocabello', TipoCabello),
        ('grosorcabello', GrosorCabello),
        ('porosidadcabello', PorosidadCabello),
        ('cuerocabelludo', CueroCabelludo),
        ('estadogeneral', EstadoGeneral),
        ('categoria-servicio', CategoriaServicio),
    )

    @classmethod
    def setUpTestData(cls):
        cls.catalog_objects = {}
        for basename, model in cls.CATALOG_SPECS:
            cls.catalog_objects[basename] = model.objects.create(
                nombre=f'Base {basename}',
            )

        cls.equipment_type = TipoEquipamiento.objects.create(
            nombre='Tipo base',
            descripcion='Tipo visible',
        )
        cls.equipment = Equipamiento.objects.create(
            codigo='EQ-BASE',
            nombre='Equipo base',
            tipo=cls.equipment_type,
        )

        cls.client_user = cls.create_user('cliente-catalogos@test.com')
        Cliente.objects.create(usuario=cls.client_user)
        cls.employee = cls.create_user_with_role(
            'empleado-catalogos@test.com',
            BusinessRole.EMPLEADO,
        )
        cls.professional = cls.create_user_with_role(
            'profesional-catalogos@test.com',
            BusinessRole.PROFESIONAL,
        )
        cls.administrator = cls.create_user_with_role(
            'administrador-catalogos@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        cls.staff_without_permission = cls.create_user(
            'staff-catalogos@test.com',
            is_staff=True,
        )
        cls.direct_manager = cls.create_user('grant-catalogos@test.com')
        cls.direct_manager.user_permissions.add(cls.manage_configuration())
        cls.inactive_manager = cls.create_user(
            'inactivo-catalogos@test.com',
            is_active=False,
        )
        cls.inactive_manager.user_permissions.add(cls.manage_configuration())

    @staticmethod
    def create_user(email, **flags):
        return Usuario.objects.create_user(email=email, **flags)

    @classmethod
    def create_user_with_role(cls, email, role):
        user = cls.create_user(email)
        user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def manage_configuration():
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_configuration',
        )

    @staticmethod
    def catalog_payload(basename, suffix):
        payload = {
            'nombre': f'{basename} {suffix}',
            'descripcion': 'Configuración autorizada',
        }
        if basename != 'categoria-servicio':
            payload.update({'activo': True, 'puntaje_base': 7})
        else:
            payload['activo'] = True
        return payload

    def equipment_specs(self):
        return (
            (
                'tipo-equipamiento',
                TipoEquipamiento,
                self.equipment_type,
                {
                    'nombre': 'Tipo solicitado',
                    'descripcion': 'Configuración solicitada',
                },
            ),
            (
                'equipamiento',
                Equipamiento,
                self.equipment,
                {
                    'codigo': 'EQ-SOLICITADO',
                    'nombre': 'Equipo solicitado',
                    'tipo': self.equipment_type.pk,
                    'estado': Equipamiento.EstadoRecurso.DISPONIBLE,
                    'ubicacion': 'Salón',
                    'observaciones': 'Configuración solicitada',
                },
            ),
        )

    def all_specs(self):
        catalog_specs = tuple(
            (
                basename,
                model,
                self.catalog_objects[basename],
                self.catalog_payload(basename, 'solicitado'),
            )
            for basename, model in self.CATALOG_SPECS
        )
        return catalog_specs + self.equipment_specs()

    @staticmethod
    def authenticate(client, user):
        client.force_authenticate(user=user)

    def assert_denied_write_matrix(self, user, expected_status):
        self.authenticate(self.client, user) if user is not None else None
        for basename, model, instance, valid_payload in self.all_specs():
            list_url = reverse(f'{basename}-list')
            detail_url = reverse(f'{basename}-detail', args=[instance.pk])
            original_count = model.objects.count()
            original_name = instance.nombre

            malicious_payload = {
                **valid_payload,
                'is_staff': True,
                'is_superuser': True,
                'user_permissions': ['gestion.manage_configuration'],
            }
            requests = (
                ('post', list_url, malicious_payload),
                ('patch', detail_url, {'nombre': 'ESCALAMIENTO', **malicious_payload}),
                ('put', detail_url, {'nombre': 'ESCALAMIENTO', **malicious_payload}),
                ('delete', detail_url, None),
            )
            for method, url, payload in requests:
                with self.subTest(
                    actor=getattr(user, 'email', 'anonymous'),
                    resource=basename,
                    method=method,
                ):
                    request = getattr(self.client, method)
                    response = (
                        request(url, payload, format='json')
                        if payload is not None
                        else request(url)
                    )
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(model.objects.count(), original_count)
                    instance.refresh_from_db()
                    self.assertEqual(instance.nombre, original_name)
                    if hasattr(instance, 'activo'):
                        self.assertTrue(instance.activo)
                    if hasattr(instance, 'is_active'):
                        self.assertTrue(instance.is_active)

    def test_public_catalog_reads_remain_available(self):
        for basename, _model in self.CATALOG_SPECS:
            instance = self.catalog_objects[basename]
            with self.subTest(resource=basename, action='list'):
                self.assertEqual(
                    self.client.get(reverse(f'{basename}-list')).status_code,
                    status.HTTP_200_OK,
                )
            with self.subTest(resource=basename, action='retrieve'):
                self.assertEqual(
                    self.client.get(
                        reverse(f'{basename}-detail', args=[instance.pk])
                    ).status_code,
                    status.HTTP_200_OK,
                )

    def test_equipment_reads_remain_authenticated_and_options_are_not_public(self):
        for basename, _model, instance, _payload in self.equipment_specs():
            with self.subTest(resource=basename, actor='anonymous'):
                self.assertEqual(
                    self.client.get(reverse(f'{basename}-list')).status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )
            self.authenticate(self.client, self.client_user)
            with self.subTest(resource=basename, actor='client'):
                self.assertEqual(
                    self.client.get(reverse(f'{basename}-list')).status_code,
                    status.HTTP_200_OK,
                )
                self.assertEqual(
                    self.client.get(
                        reverse(f'{basename}-detail', args=[instance.pk])
                    ).status_code,
                    status.HTTP_200_OK,
                )
            self.client.force_authenticate(user=None)

        self.assertEqual(
            self.client.get(reverse('equipamiento-opciones')).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.authenticate(self.client, self.client_user)
        self.assertEqual(
            self.client.get(reverse('equipamiento-opciones')).status_code,
            status.HTTP_200_OK,
        )

    def test_anonymous_cannot_write_any_resource(self):
        self.assert_denied_write_matrix(None, status.HTTP_401_UNAUTHORIZED)

    def test_actors_without_effective_permission_cannot_write_any_resource(self):
        for user in (
            self.client_user,
            self.employee,
            self.professional,
            self.staff_without_permission,
            self.inactive_manager,
        ):
            with self.subTest(actor=user.email):
                self.client.force_authenticate(user=None)
                self.assert_denied_write_matrix(
                    user,
                    status.HTTP_403_FORBIDDEN,
                )

    def assert_authorized_crud(self, user):
        self.authenticate(self.client, user)
        for basename, model, _instance, create_payload in self.all_specs():
            with self.subTest(actor=user.email, resource=basename):
                created = self.client.post(
                    reverse(f'{basename}-list'),
                    create_payload,
                    format='json',
                )
                self.assertEqual(created.status_code, status.HTTP_201_CREATED)
                created_instance = model.objects.get(pk=created.data['id'])

                patch_payload = {'nombre': f'{basename} patch {user.pk}'}
                patched = self.client.patch(
                    reverse(f'{basename}-detail', args=[created_instance.pk]),
                    patch_payload,
                    format='json',
                )
                self.assertEqual(patched.status_code, status.HTTP_200_OK)

                if basename == 'equipamiento':
                    put_payload = {
                        **create_payload,
                        'codigo': f'EQ-PUT-{user.pk}',
                        'nombre': f'{basename} put {user.pk}',
                        'is_active': False,
                    }
                else:
                    put_payload = {
                        **create_payload,
                        'nombre': f'{basename} put {user.pk}',
                    }
                replaced = self.client.put(
                    reverse(f'{basename}-detail', args=[created_instance.pk]),
                    put_payload,
                    format='json',
                )
                self.assertEqual(replaced.status_code, status.HTTP_200_OK)
                created_instance.refresh_from_db()
                if basename == 'equipamiento':
                    self.assertTrue(created_instance.is_active)

                deleted = self.client.delete(
                    reverse(f'{basename}-detail', args=[created_instance.pk])
                )
                self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
                if hasattr(created_instance, 'activo'):
                    created_instance.refresh_from_db()
                    self.assertFalse(created_instance.activo)
                elif hasattr(created_instance, 'is_active'):
                    created_instance.refresh_from_db()
                    self.assertFalse(created_instance.is_active)
                else:
                    self.assertFalse(
                        model.objects.filter(pk=created_instance.pk).exists()
                    )

    def test_administrator_can_write_all_resources(self):
        self.assert_authorized_crud(self.administrator)

    def test_non_staff_actor_with_effective_permission_can_write_all_resources(self):
        self.assertFalse(self.direct_manager.is_staff)
        self.assert_authorized_crud(self.direct_manager)

    def test_catalog_deletes_preserve_diagnoses_rules_services_and_turnos(self):
        self.authenticate(self.client, self.direct_manager)
        client_user = self.create_user('integridad-catalogos@test.com')
        client_profile = Cliente.objects.create(usuario=client_user)

        for basename, model in self.CATALOG_SPECS[:-1]:
            instance = self.catalog_objects[basename]
            field = {
                'tipocabello': 'tipo_cabello',
                'grosorcabello': 'grosor_cabello',
                'porosidadcabello': 'porosidad_cabello',
                'cuerocabelludo': 'cuero_cabelludo',
                'estadogeneral': 'estado_general',
            }[basename]
            rule = ReglaDiagnostico.objects.create(
                mensaje_resultado=f'Resultado protegido {basename}',
                accion_resultado=f'ACCION_{basename.upper()}',
                **{field: instance},
            )
            diagnosis = DiagnosticoCapilar.objects.create(
                cliente=client_profile,
                **{field: instance},
            )

            with self.subTest(resource=basename):
                response = self.client.delete(
                    reverse(f'{basename}-detail', args=[instance.pk])
                )
                self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
                instance.refresh_from_db()
                self.assertFalse(instance.activo)
                self.assertTrue(ReglaDiagnostico.objects.filter(pk=rule.pk).exists())
                self.assertTrue(
                    DiagnosticoCapilar.objects.filter(pk=diagnosis.pk).exists()
                )

        category = self.catalog_objects['categoria-servicio']
        service = Servicio.objects.create(
            nombre='Servicio con categoría histórica',
            categoria=category,
            precio_base='100.00',
            duracion_estimada=30,
        )
        turno = Turno.objects.create(
            cliente=client_profile,
            fecha=timezone.localdate(),
            hora_inicio=time(9, 0),
        )
        detail = DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico=service.precio_base,
            duracion_minutos=service.duracion_estimada,
        )

        response = self.client.delete(
            reverse('categoria-servicio-detail', args=[category.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        category.refresh_from_db()
        service.refresh_from_db()
        self.assertFalse(category.activo)
        self.assertEqual(service.categoria, category)
        self.assertTrue(Turno.objects.filter(pk=turno.pk).exists())
        self.assertTrue(DetalleTurno.objects.filter(pk=detail.pk).exists())

    def test_referenced_equipment_type_cannot_be_deleted(self):
        self.authenticate(self.client, self.direct_manager)
        service = Servicio.objects.create(
            nombre='Servicio con requisito protegido',
            precio_base='50.00',
            duracion_estimada=30,
        )
        requirement = RequisitoServicio.objects.create(
            servicio=service,
            tipo_equipamiento=self.equipment_type,
        )

        response = self.client.delete(
            reverse('tipo-equipamiento-detail', args=[self.equipment_type.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'EQUIPMENT_TYPE_IN_USE')
        self.assertTrue(
            TipoEquipamiento.objects.filter(pk=self.equipment_type.pk).exists()
        )
        self.assertTrue(Equipamiento.objects.filter(pk=self.equipment.pk).exists())
        self.assertTrue(RequisitoServicio.objects.filter(pk=requirement.pk).exists())

    def test_equipment_soft_delete_preserves_turno_reference(self):
        self.authenticate(self.client, self.direct_manager)
        client_user = self.create_user('integridad-equipo@test.com')
        client_profile = Cliente.objects.create(usuario=client_user)
        turno = Turno.objects.create(
            cliente=client_profile,
            equipamiento=self.equipment,
            fecha=timezone.localdate(),
            hora_inicio=time(10, 0),
        )

        response = self.client.delete(
            reverse('equipamiento-detail', args=[self.equipment.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.equipment.refresh_from_db()
        turno.refresh_from_db()
        self.assertFalse(self.equipment.is_active)
        self.assertEqual(turno.equipamiento, self.equipment)
