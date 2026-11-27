from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
import threading

from django.contrib.auth.models import Group, Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    BloqueoAgenda,
    HorarioLaboral,
    Personal,
    Turno,
)
from gestion.agenda_services import (
    AgendaBlockConflict,
    create_agenda_block,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class LegacyAgendaPermissionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.view_global = cls.permission('view_global_agenda')
        cls.manage_configuration = cls.permission('manage_configuration')

        cls.client_user = cls.user_with_role(
            'agenda-cliente@test.com',
            BusinessRole.CLIENTE,
        )
        Cliente.objects.create(usuario=cls.client_user)
        cls.employee = cls.user_with_role(
            'agenda-empleado@test.com',
            BusinessRole.EMPLEADO,
        )
        cls.professional = cls.user_with_role(
            'agenda-profesional@test.com',
            BusinessRole.PROFESIONAL,
        )
        cls.administrator = cls.user_with_role(
            'agenda-administrador@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        cls.staff_without_permission = cls.create_user(
            'agenda-staff@test.com',
            is_staff=True,
        )
        cls.read_grant = cls.create_user('agenda-read-grant@test.com')
        cls.read_grant.user_permissions.add(cls.view_global)
        cls.write_grant = cls.create_user('agenda-write-grant@test.com')
        cls.write_grant.user_permissions.add(cls.manage_configuration)
        cls.inactive_grant = cls.create_user(
            'agenda-inactive-grant@test.com',
            is_active=False,
        )
        cls.inactive_grant.user_permissions.add(
            cls.view_global,
            cls.manage_configuration,
        )
        cls.owner = cls.create_user('agenda-owner@test.com')
        cls.inactive_owner = cls.create_user('agenda-inactive-owner@test.com')

        cls.first_colorist = Personal.objects.create(
            nombre='Primera',
            apellido='Colorista',
            rol='colorista',
            activo=True,
        )
        cls.owned_personal = Personal.objects.create(
            usuario=cls.owner,
            nombre='Agenda',
            apellido='Propia',
            rol='asistente',
            activo=True,
        )
        cls.professional_personal = Personal.objects.create(
            usuario=cls.professional,
            nombre='Profesional',
            apellido='Autorizada',
            rol='colorista',
            activo=True,
        )
        cls.other_personal = Personal.objects.create(
            nombre='Agenda',
            apellido='Ajena',
            rol='asistente',
            activo=True,
        )
        cls.inactive_personal = Personal.objects.create(
            usuario=cls.inactive_owner,
            nombre='Personal',
            apellido='Inactivo',
            rol='asistente',
            activo=False,
        )

        for index, personal in enumerate(
            (cls.owned_personal, cls.professional_personal, cls.other_personal)
        ):
            HorarioLaboral.objects.create(
                personal=personal,
                dia_semana=index,
                hora_inicio=time(9, 0),
                hora_fin=time(17, 0),
                activo=True,
            )

        cls.block_date = cls.middle_of_next_month()
        cls.starts_at = cls.aware(cls.block_date, time(10, 0))
        cls.ends_at = cls.aware(cls.block_date, time(11, 0))
        cls.agenda_url = reverse('agenda-general')
        cls.block_url = reverse('agenda-bloquear')
        cls.calendar_url = reverse('disponibilidad-calendario')

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    @staticmethod
    def create_user(email, **flags):
        return Usuario.objects.create_user(email=email, **flags)

    @classmethod
    def user_with_role(cls, email, role):
        user = cls.create_user(email)
        user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def middle_of_next_month():
        today = timezone.localdate()
        if today.month == 12:
            return date(today.year + 1, 1, 15)
        return date(today.year, today.month + 1, 15)

    @staticmethod
    def aware(day, hour):
        return timezone.make_aware(
            datetime.combine(day, hour),
            timezone.get_current_timezone(),
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def calendar_params(self, personal_id=None):
        params = {
            'mes': self.block_date.month,
            'anio': self.block_date.year,
        }
        if personal_id is not None:
            params['personal_id'] = personal_id
        return params

    def block_payload(self, personal_id=None, **overrides):
        payload = {
            'personal_id': personal_id or self.other_personal.pk,
            'fecha_inicio': self.starts_at.isoformat(),
            'fecha_fin': self.ends_at.isoformat(),
            'motivo': 'Capacitación técnica',
            'bloquea_todo_el_dia': False,
        }
        payload.update(overrides)
        return payload

    def test_anonymous_cannot_read_legacy_agenda_surfaces(self):
        responses = (
            self.client.get(
                self.agenda_url,
                {'personal_id': self.other_personal.pk},
            ),
            self.client.get(self.calendar_url, self.calendar_params()),
        )

        self.assertTrue(
            all(response.status_code == status.HTTP_401_UNAUTHORIZED
                for response in responses)
        )

    def test_global_permission_allows_roles_and_non_staff_individual_grant(self):
        for actor in (
            self.employee,
            self.professional,
            self.administrator,
            self.read_grant,
        ):
            self.authenticate(actor)
            with self.subTest(actor=actor.email, endpoint='general'):
                response = self.client.get(
                    self.agenda_url,
                    {'personal_id': self.other_personal.pk},
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    response.data['profesional']['id'],
                    self.other_personal.pk,
                )
            with self.subTest(actor=actor.email, endpoint='calendar'):
                response = self.client.get(
                    self.calendar_url,
                    self.calendar_params(self.other_personal.pk),
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    {rule['personal'] for rule in response.data['reglas']},
                    {self.other_personal.pk},
                )

    def test_client_and_staff_without_permission_cannot_read_global_agenda(self):
        for actor in (self.client_user, self.staff_without_permission):
            self.authenticate(actor)
            for url, params in (
                (
                    self.agenda_url,
                    {'personal_id': self.other_personal.pk},
                ),
                (
                    self.calendar_url,
                    self.calendar_params(self.other_personal.pk),
                ),
            ):
                with self.subTest(actor=actor.email, url=url):
                    response = self.client.get(url, params)
                    self.assertEqual(
                        response.status_code,
                        status.HTTP_403_FORBIDDEN,
                    )

    def test_active_personal_without_global_permission_reads_only_own_agenda(self):
        own_block = BloqueoAgenda.objects.create(
            personal=self.owned_personal,
            fecha_inicio=self.starts_at,
            fecha_fin=self.ends_at,
            motivo='Bloqueo propio visible',
        )
        other_block = BloqueoAgenda.objects.create(
            personal=self.other_personal,
            fecha_inicio=self.starts_at + timedelta(hours=2),
            fecha_fin=self.ends_at + timedelta(hours=2),
            motivo='Bloqueo ajeno oculto',
        )
        self.authenticate(self.owner)

        general = self.client.get(self.agenda_url)
        calendar = self.client.get(
            self.calendar_url,
            self.calendar_params(),
        )
        explicit_own = self.client.get(
            self.agenda_url,
            {'personal_id': self.owned_personal.pk},
        )

        self.assertEqual(general.status_code, status.HTTP_200_OK)
        self.assertEqual(explicit_own.status_code, status.HTTP_200_OK)
        self.assertEqual(
            general.data['profesional']['id'],
            self.owned_personal.pk,
        )
        self.assertEqual(calendar.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {rule['personal'] for rule in calendar.data['reglas']},
            {self.owned_personal.pk},
        )
        self.assertIn(
            own_block.pk,
            {block['id'] for block in calendar.data['bloqueos']},
        )
        self.assertNotIn(
            other_block.pk,
            {block['id'] for block in calendar.data['bloqueos']},
        )

    def test_personal_id_manipulation_cannot_escape_ownership(self):
        self.authenticate(self.owner)

        general = self.client.get(
            self.agenda_url,
            {'personal_id': self.other_personal.pk},
        )
        calendar = self.client.get(
            self.calendar_url,
            self.calendar_params(self.other_personal.pk),
        )

        self.assertEqual(general.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(calendar.status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_account_or_personal_cannot_use_ownership(self):
        for actor in (self.inactive_grant, self.inactive_owner):
            self.authenticate(actor)
            with self.subTest(actor=actor.email):
                general = self.client.get(self.agenda_url)
                calendar = self.client.get(
                    self.calendar_url,
                    self.calendar_params(),
                )
                self.assertEqual(
                    general.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    calendar.status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_global_reader_must_name_target_in_general_endpoint(self):
        self.authenticate(self.read_grant)

        response = self.client.get(self.agenda_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('personal_id', response.data)

    def test_global_reader_gets_404_for_missing_or_inactive_target(self):
        self.authenticate(self.read_grant)

        for personal_id in (999999, self.inactive_personal.pk):
            with self.subTest(personal_id=personal_id):
                response = self.client.get(
                    self.agenda_url,
                    {'personal_id': personal_id},
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_404_NOT_FOUND,
                )

    def test_global_calendar_without_target_preserves_authorized_admin_consumer(self):
        self.authenticate(self.administrator)

        response = self.client.get(
            self.calendar_url,
            self.calendar_params(),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {rule['personal'] for rule in response.data['reglas']},
            {
                self.owned_personal.pk,
                self.professional_personal.pk,
                self.other_personal.pk,
            },
        )

    def test_legacy_and_canonical_agenda_authorization_are_compatible(self):
        self.authenticate(self.read_grant)
        canonical_global = self.client.get(reverse('turno-list'))
        legacy_global = self.client.get(
            self.agenda_url,
            {'personal_id': self.other_personal.pk},
        )
        legacy_calendar = self.client.get(
            self.calendar_url,
            self.calendar_params(self.other_personal.pk),
        )

        self.assertEqual(canonical_global.status_code, status.HTTP_200_OK)
        self.assertEqual(legacy_global.status_code, status.HTTP_200_OK)
        self.assertEqual(legacy_calendar.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=None)
        self.authenticate(self.owner)
        Turno.objects.create(
            cliente=self.client_user.cliente,
            profesional=self.owned_personal,
            fecha=self.block_date,
            hora_inicio=time(15, 0),
        )
        own_canonical = self.client.get(reverse('turno-mi-agenda-laboral'))
        forbidden_global = self.client.get(reverse('turno-list'))
        own_legacy = self.client.get(self.agenda_url)

        self.assertEqual(own_canonical.status_code, status.HTTP_200_OK)
        self.assertEqual(forbidden_global.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(own_legacy.status_code, status.HTTP_200_OK)

    def test_public_booking_availability_alias_remains_public(self):
        response = self.client.get(reverse('disponibilidad-turnos'))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_permission_does_not_authorize_schedule_blocks(self):
        for actor in (
            self.client_user,
            self.employee,
            self.professional,
            self.staff_without_permission,
            self.read_grant,
            self.owner,
            self.inactive_grant,
        ):
            self.authenticate(actor)
            initial_count = BloqueoAgenda.objects.count()
            with self.subTest(actor=actor.email):
                response = self.client.post(
                    self.block_url,
                    self.block_payload(),
                    format='json',
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(BloqueoAgenda.objects.count(), initial_count)

    def test_write_permission_does_not_authorize_global_read(self):
        self.authenticate(self.write_grant)

        general = self.client.get(
            self.agenda_url,
            {'personal_id': self.other_personal.pk},
        )
        calendar = self.client.get(
            self.calendar_url,
            self.calendar_params(self.other_personal.pk),
        )

        self.assertEqual(general.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(calendar.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_create_block(self):
        initial_count = BloqueoAgenda.objects.count()

        response = self.client.post(
            self.block_url,
            self.block_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(BloqueoAgenda.objects.count(), initial_count)

    def test_admin_and_non_staff_effective_grant_create_explicit_target_block(self):
        for index, actor in enumerate((self.administrator, self.write_grant)):
            self.authenticate(actor)
            start = self.starts_at + timedelta(days=index)
            end = self.ends_at + timedelta(days=index)
            with self.subTest(actor=actor.email):
                response = self.client.post(
                    self.block_url,
                    self.block_payload(
                        personal_id=self.other_personal.pk,
                        fecha_inicio=start.isoformat(),
                        fecha_fin=end.isoformat(),
                    ),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                block = BloqueoAgenda.objects.get(pk=response.data['id'])
                self.assertEqual(block.personal, self.other_personal)
                self.assertNotEqual(block.personal, self.first_colorist)
                self.assertFalse(actor.is_staff)

    def test_invalid_target_interval_and_malicious_payload_do_not_mutate(self):
        self.authenticate(self.write_grant)
        invalid_payloads = (
            {
                key: value
                for key, value in self.block_payload().items()
                if key != 'personal_id'
            },
            self.block_payload(personal_id=999999),
            self.block_payload(personal_id=self.inactive_personal.pk),
            self.block_payload(fecha_fin=self.starts_at.isoformat()),
            {
                **self.block_payload(),
                'personal': self.first_colorist.pk,
                'is_staff': True,
            },
        )

        for payload in invalid_payloads:
            initial_count = BloqueoAgenda.objects.count()
            with self.subTest(payload=payload):
                response = self.client.post(
                    self.block_url,
                    payload,
                    format='json',
                )
                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertEqual(BloqueoAgenda.objects.count(), initial_count)

    def test_turno_conflict_returns_409_without_creating_block(self):
        Turno.objects.create(
            cliente=self.client_user.cliente,
            profesional=self.other_personal,
            fecha=self.block_date,
            hora_inicio=time(10, 0),
            hora_fin_calculada=time(11, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        self.authenticate(self.write_grant)

        response = self.client.post(
            self.block_url,
            self.block_payload(
                fecha_inicio=(self.starts_at + timedelta(minutes=30)).isoformat(),
                fecha_fin=(self.ends_at + timedelta(minutes=30)).isoformat(),
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error'], 'AGENDA_TURNO_CONFLICT')
        self.assertEqual(BloqueoAgenda.objects.count(), 0)

    def test_existing_block_conflict_returns_409_without_mutation(self):
        existing = BloqueoAgenda.objects.create(
            personal=self.other_personal,
            fecha_inicio=self.starts_at,
            fecha_fin=self.ends_at,
            motivo='Bloqueo existente',
        )
        self.authenticate(self.write_grant)

        response = self.client.post(
            self.block_url,
            self.block_payload(
                fecha_inicio=(self.starts_at + timedelta(minutes=15)).isoformat(),
                fecha_fin=(self.ends_at + timedelta(minutes=15)).isoformat(),
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error'], 'AGENDA_BLOCK_CONFLICT')
        self.assertEqual(
            list(BloqueoAgenda.objects.values_list('pk', flat=True)),
            [existing.pk],
        )


class AgendaBlockConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Esta carrera requiere PostgreSQL real.')
        self.manager = Usuario.objects.create_user(
            email='agenda-concurrency@test.com'
        )
        self.manager.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='gestion',
                codename='manage_configuration',
            )
        )
        self.personal = Personal.objects.create(
            nombre='Agenda',
            apellido='Concurrente',
            rol='asistente',
            activo=True,
        )
        target_date = timezone.localdate() + timedelta(days=30)
        self.starts_at = timezone.make_aware(
            datetime.combine(target_date, time(10, 0)),
            timezone.get_current_timezone(),
        )
        self.ends_at = self.starts_at + timedelta(hours=1)

    def block_worker(self, reason):
        def operation():
            close_old_connections()
            try:
                actor = Usuario.objects.get(pk=self.manager.pk)
                block = create_agenda_block(
                    actor=actor,
                    personal_id=self.personal.pk,
                    starts_at=self.starts_at,
                    ends_at=self.ends_at,
                    reason=reason,
                )
                return ('created', block.pk)
            except AgendaBlockConflict as exc:
                return ('conflict', exc.code)
            finally:
                close_old_connections()
        return operation

    def test_two_overlapping_blocks_have_exactly_one_winner(self):
        barrier = threading.Barrier(2)

        def synchronized(operation):
            barrier.wait(timeout=10)
            return operation()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    synchronized,
                    self.block_worker('Bloqueo concurrente A'),
                ),
                executor.submit(
                    synchronized,
                    self.block_worker('Bloqueo concurrente B'),
                ),
            ]
            results = [future.result(timeout=20) for future in futures]

        self.assertEqual(
            sum(result[0] == 'created' for result in results),
            1,
        )
        self.assertEqual(
            sum(result[0] == 'conflict' for result in results),
            1,
        )
        self.assertEqual(BloqueoAgenda.objects.count(), 1)
