import shutil
import tempfile
from datetime import date, time, timedelta

from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import DetalleTurno, Notificacion, Personal, Servicio, Turno
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class TurnoReadAuthorizationApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp(prefix='bohemia-turnos-tests-')
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.view_global_agenda = Permission.objects.get(
            content_type__app_label='gestion',
            codename='view_global_agenda',
        )
        self.global_url = reverse('turno-list')
        self.client_user = self.create_user('client@test.com')
        self.client_profile = Cliente.objects.create(usuario=self.client_user)
        self.other_client_user = self.create_user('other-client@test.com')
        self.other_client = Cliente.objects.create(usuario=self.other_client_user)
        self.service = Servicio.objects.create(
            nombre='Servicio autorización Turnos',
            duracion_estimada=60,
            plantilla_formula='FÓRMULA PRIVADA',
        )
        tomorrow = date.today() + timedelta(days=1)
        self.own_turno = self.create_turno(
            self.client_profile,
            tomorrow,
            time(10, 0),
        )
        self.other_turno = self.create_turno(
            self.other_client,
            tomorrow,
            time(12, 0),
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='TurnosPassword!2026',
            first_name='Ana',
            last_name='Pérez',
            **extra_fields,
        )

    def create_turno(self, cliente, fecha, hora, profesional=None, estado=None):
        turno = Turno.objects.create(
            cliente=cliente,
            profesional=profesional,
            fecha=fecha,
            hora_inicio=hora,
            estado=estado or Turno.Estado.CONFIRMADO,
            monto_abonado='1500.00',
            saldo_pendiente='3500.00',
        )
        DetalleTurno.objects.create(
            turno=turno,
            servicio=self.service,
            precio_historico='5000.00',
            duracion_minutos=60,
        )
        return turno

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_employee_with_permission_can_read_global_agenda(self):
        actor = self.create_user('employee@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.EMPLEADO)
        self.authenticate(actor)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_professional_with_permission_can_read_global_agenda(self):
        actor = self.create_user('professional@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.PROFESIONAL)
        self.authenticate(actor)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_administrator_without_staff_flag_uses_effective_permission(self):
        actor = self.create_user('administrator@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.ADMINISTRADOR)
        self.authenticate(actor)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_individual_permission_allows_global_agenda(self):
        actor = self.create_user('individual@test.com', is_staff=False)
        actor.user_permissions.add(self.view_global_agenda)
        self.authenticate(actor)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_staff_without_permission_cannot_read_global_agenda(self):
        actor = self.create_user('staff@test.com', is_staff=True)
        self.authenticate(actor)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_cannot_read_global_agenda(self):
        self.assign_role(self.client_user, BusinessRole.CLIENTE)
        self.authenticate(self.client_user)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_global_agenda_returns_401(self):
        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_mis_turnos_returns_only_client_owned_turnos(self):
        self.authenticate(self.client_user)

        response = self.client.get(reverse('turno-mis-turnos'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {turno['id'] for turno in response.data},
            {self.own_turno.pk},
        )

    def test_client_cannot_retrieve_another_clients_turno(self):
        self.authenticate(self.client_user)

        response = self.client.get(
            reverse('turno-detail', args=[self.other_turno.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_client_can_retrieve_owned_turno_with_client_contract(self):
        self.authenticate(self.client_user)

        response = self.client.get(
            reverse('turno-detail', args=[self.own_turno.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('detalles', response.data)
        self.assertIn('comprobante_pago', response.data)
        self.assertNotIn('monto_abonado', response.data)

    def test_personal_agenda_returns_only_assigned_turnos(self):
        actor = self.create_user('linked-personal@test.com')
        personal = Personal.objects.create(
            usuario=actor,
            nombre='Personal',
            apellido='Propio',
            rol='asistente',
            activo=True,
        )
        assigned = self.create_turno(
            self.other_client,
            date.today() + timedelta(days=2),
            time(9, 0),
            profesional=personal,
        )
        self.authenticate(actor)

        response = self.client.get(reverse('turno-mi-agenda-laboral'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {turno['id'] for turno in response.data},
            {assigned.pk},
        )

    def test_personal_without_global_permission_can_retrieve_assigned_turno(self):
        actor = self.create_user('personal-detail@test.com')
        personal = Personal.objects.create(
            usuario=actor,
            nombre='Personal',
            apellido='Detalle',
            rol='asistente',
            activo=True,
        )
        self.other_turno.profesional = personal
        self.other_turno.save(update_fields=['profesional'])
        self.authenticate(actor)

        response = self.client.get(
            reverse('turno-detail', args=[self.other_turno.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(actor.has_perm('gestion.view_global_agenda'))

    def test_inactive_personal_cannot_read_work_agenda(self):
        actor = self.create_user('inactive-personal@test.com')
        Personal.objects.create(
            usuario=actor,
            nombre='Personal',
            apellido='Inactivo',
            rol='asistente',
            activo=False,
        )
        self.authenticate(actor)

        response = self.client.get(reverse('turno-mi-agenda-laboral'))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_client_and_personal_scopes_remain_separate(self):
        personal = Personal.objects.create(
            usuario=self.client_user,
            nombre='Perfil',
            apellido='Dual',
            rol='colorista',
            activo=True,
        )
        assigned = self.create_turno(
            self.other_client,
            date.today() + timedelta(days=3),
            time(15, 0),
            profesional=personal,
        )
        self.authenticate(self.client_user)

        client_response = self.client.get(reverse('turno-mis-turnos'))
        personal_response = self.client.get(reverse('turno-mi-agenda-laboral'))
        global_response = self.client.get(self.global_url)

        self.assertEqual(client_response.status_code, status.HTTP_200_OK)
        self.assertEqual(personal_response.status_code, status.HTTP_200_OK)
        self.assertEqual(global_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            {turno['id'] for turno in client_response.data},
            {self.own_turno.pk},
        )
        self.assertEqual(
            {turno['id'] for turno in personal_response.data},
            {assigned.pk},
        )

    def test_get_turnos_has_no_write_side_effects(self):
        expired = self.create_turno(
            self.client_profile,
            date.today() - timedelta(days=1),
            time(10, 0),
            estado=Turno.Estado.SOLICITADO,
        )
        notification_count = Notificacion.objects.count()
        actor = self.create_user('reader@test.com')
        actor.user_permissions.add(self.view_global_agenda)
        self.authenticate(actor)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expired.refresh_from_db()
        self.assertEqual(expired.estado, Turno.Estado.SOLICITADO)
        self.assertEqual(Notificacion.objects.count(), notification_count)

    def test_global_serializer_excludes_sensitive_fields(self):
        actor = self.create_user('safe-contract@test.com')
        actor.user_permissions.add(self.view_global_agenda)
        self.authenticate(actor)

        response = self.client.get(self.global_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(
            turno for turno in response.data
            if turno['id'] == self.own_turno.pk
        )
        forbidden_fields = {
            'detalles',
            'comprobante_pago',
            'monto_abonado',
            'saldo_pendiente',
            'tipo_pago_registro',
            'alerta_daño_capilar',
        }
        self.assertTrue(forbidden_fields.isdisjoint(item.keys()))
        self.assertNotIn('FÓRMULA PRIVADA', str(item))

    def test_generic_put_patch_and_delete_are_disabled_for_every_actor(self):
        actors = [
            self.client_user,
            self.create_user(
                'superuser@test.com',
                is_staff=True,
                is_superuser=True,
            ),
        ]
        url = reverse('turno-detail', args=[self.own_turno.pk])

        for actor in actors:
            self.authenticate(actor)
            with self.subTest(actor=actor.email, method='put'):
                response = self.client.put(url, {'estado': 'realizado'}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            with self.subTest(actor=actor.email, method='patch'):
                response = self.client.patch(url, {'estado': 'realizado'}, format='json')
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            with self.subTest(actor=actor.email, method='delete'):
                response = self.client.delete(url)
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        self.assertTrue(Turno.objects.filter(pk=self.own_turno.pk).exists())

    def test_owner_can_upload_receipt_in_compatible_state(self):
        self.own_turno.estado = Turno.Estado.ESPERANDO_SENA
        self.own_turno.save(update_fields=['estado'])
        self.authenticate(self.client_user)
        receipt = SimpleUploadedFile(
            'receipt.pdf',
            b'payment evidence',
            content_type='application/pdf',
        )

        response = self.client.post(
            reverse('turno-subir-comprobante', args=[self.own_turno.pk]),
            {'comprobante_pago': receipt},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.own_turno.refresh_from_db()
        self.assertTrue(self.own_turno.comprobante_pago.name.endswith('receipt.pdf'))

    def test_non_owner_cannot_upload_receipt_even_with_global_permission(self):
        self.own_turno.estado = Turno.Estado.ESPERANDO_SENA
        self.own_turno.save(update_fields=['estado'])
        actor = self.create_user('global-non-owner@test.com')
        actor.user_permissions.add(self.view_global_agenda)
        self.authenticate(actor)

        response = self.client.post(
            reverse('turno-subir-comprobante', args=[self.own_turno.pk]),
            {
                'comprobante_pago': SimpleUploadedFile(
                    'receipt.pdf',
                    b'payment evidence',
                    content_type='application/pdf',
                )
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_receipt_upload_rejects_unexpected_sensitive_fields(self):
        self.own_turno.estado = Turno.Estado.ESPERANDO_SENA
        self.own_turno.save(update_fields=['estado'])
        self.authenticate(self.client_user)

        response = self.client.post(
            reverse('turno-subir-comprobante', args=[self.own_turno.pk]),
            {
                'comprobante_pago': SimpleUploadedFile(
                    'receipt.pdf',
                    b'payment evidence',
                    content_type='application/pdf',
                ),
                'estado': Turno.Estado.REALIZADO,
                'monto_abonado': '999999.00',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('campos_no_permitidos', response.data)
        self.own_turno.refresh_from_db()
        self.assertEqual(self.own_turno.estado, Turno.Estado.ESPERANDO_SENA)
        self.assertFalse(bool(self.own_turno.comprobante_pago))

    def test_receipt_upload_rejects_incompatible_state(self):
        self.authenticate(self.client_user)

        response = self.client.post(
            reverse('turno-subir-comprobante', args=[self.own_turno.pk]),
            {
                'comprobante_pago': SimpleUploadedFile(
                    'receipt.pdf',
                    b'payment evidence',
                    content_type='application/pdf',
                )
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
