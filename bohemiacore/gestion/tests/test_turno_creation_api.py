from datetime import datetime, time, timedelta

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    BloqueoAgenda,
    DetalleTurno,
    Equipamiento,
    HorarioLaboral,
    Personal,
    RequisitoServicio,
    Servicio,
    TipoEquipamiento,
    Turno,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class TurnoCreationApiTests(APITestCase):
    def setUp(self):
        self.create_turno_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_turno_for_client',
        )
        self.fecha = timezone.localdate() + timedelta(days=2)
        self.hora = time(10, 0)
        self.service = Servicio.objects.create(
            nombre='Servicio creación segura',
            duracion_estimada=60,
            precio_base='5000.00',
            activo=True,
        )
        self.personal = Personal.objects.create(
            nombre='Julia',
            apellido='Díaz',
            rol='asistente',
            activo=True,
        )
        HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=self.fecha.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
            permite_complemento=True,
            permite_diseno_color=True,
        )
        self.client_user, self.client_profile = self.create_client(
            'client-creation@test.com'
        )
        self.other_user, self.other_client = self.create_client(
            'other-creation@test.com'
        )
        self.reserve_url = reverse('turno-reservar')
        self.for_client_url = reverse('turno-crear-para-cliente')

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='TurnosCreate!2026',
            first_name='Ana',
            last_name='Pérez',
            **extra_fields,
        )

    def create_client(self, email):
        user = self.create_user(email)
        return user, Cliente.objects.create(usuario=user, activo=True)

    @staticmethod
    def assign_role(user, role):
        user.groups.add(Group.objects.get(name=role))

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def payload(self, **overrides):
        data = {
            'servicio': self.service.pk,
            'profesional': self.personal.pk,
            'fecha': self.fecha.isoformat(),
            'hora_inicio': self.hora.strftime('%H:%M'),
        }
        data.update(overrides)
        return data

    def third_party_payload(self, **overrides):
        data = self.payload(cliente_id=self.other_client.pk)
        data.update(overrides)
        return data

    def test_client_reserves_own_turno(self):
        self.authenticate(self.client_user)

        response = self.client.post(self.reserve_url, self.payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        turno = Turno.objects.get()
        self.assertEqual(turno.cliente, self.client_profile)
        self.assertEqual(turno.estado, Turno.Estado.SOLICITADO)
        self.assertEqual(turno.canal_origen, Turno.CanalOrigen.WEB)
        self.assertEqual(turno.monto_abonado, 0)
        self.assertEqual(turno.saldo_pendiente, 0)
        self.assertEqual(turno.detalles.get().servicio, self.service)

    def test_client_cannot_send_another_client_id(self):
        self.authenticate(self.client_user)

        response = self.client.post(
            self.reserve_url,
            self.payload(cliente_id=self.other_client.pk),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('campos_no_permitidos', response.data)
        self.assertFalse(Turno.objects.exists())

    def test_client_cannot_use_create_for_client_endpoint(self):
        self.authenticate(self.client_user)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_employee_without_staff_flag_can_create_for_client(self):
        actor = self.create_user('employee-create@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.EMPLEADO)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Turno.objects.get().cliente, self.other_client)

    def test_professional_can_create_for_client_by_effective_permission(self):
        actor = self.create_user('professional-create@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.PROFESIONAL)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_administrator_without_staff_flag_can_create_for_client(self):
        actor = self.create_user('administrator-create@test.com', is_staff=False)
        self.assign_role(actor, BusinessRole.ADMINISTRADOR)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_individual_permission_can_create_for_client(self):
        actor = self.create_user('individual-create@test.com', is_staff=False)
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_staff_without_permission_cannot_create_for_client(self):
        actor = self.create_user('staff-create@test.com', is_staff=True)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Turno.objects.exists())

    def test_anonymous_cannot_create(self):
        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_selected_personal_is_rejected(self):
        self.personal.activo = False
        self.personal.save(update_fields=['activo'])
        actor = self.create_user('inactive-personal-actor@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['code']), 'INACTIVE_PERSONAL')

    def test_occupied_slot_is_rejected(self):
        occupied = Turno.objects.create(
            cliente=self.client_profile,
            profesional=self.personal,
            fecha=self.fecha,
            hora_inicio=self.hora,
            estado=Turno.Estado.SOLICITADO,
        )
        DetalleTurno.objects.create(
            turno=occupied,
            servicio=self.service,
            precio_historico=self.service.precio_base,
            duracion_minutos=60,
        )
        actor = self.create_user('occupied-actor@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['code']), 'SLOT_UNAVAILABLE')
        self.assertEqual(Turno.objects.count(), 1)

    def test_blocked_slot_is_rejected_without_exposing_the_reason(self):
        start = timezone.make_aware(datetime.combine(self.fecha, time(9, 30)))
        end = timezone.make_aware(datetime.combine(self.fecha, time(11, 0)))
        BloqueoAgenda.objects.create(
            personal=self.personal,
            fecha_inicio=start,
            fecha_fin=end,
            motivo='Motivo interno sensible',
        )
        actor = self.create_user('blocked-actor@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['code']), 'SLOT_BLOCKED')
        self.assertNotIn('Motivo interno sensible', str(response.data))
        self.assertFalse(Turno.objects.exists())

    def test_missing_required_equipment_is_rejected(self):
        equipment_type = TipoEquipamiento.objects.create(nombre='Sillón especial')
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        actor = self.create_user('equipment-actor@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['code']), 'EQUIPMENT_UNAVAILABLE')
        self.assertFalse(Turno.objects.exists())

        availability_response = self.client.get(
            reverse('turno-consultar-disponibilidad'),
            {
                'servicio_id': self.service.pk,
                'fecha': self.fecha.isoformat(),
            },
        )
        self.assertEqual(availability_response.status_code, status.HTTP_200_OK)
        self.assertEqual(availability_response.data['disponibilidad'], [])
        self.assertNotIn('equipamiento', str(availability_response.data).lower())

    def test_available_required_equipment_allows_creation(self):
        equipment_type = TipoEquipamiento.objects.create(nombre='Lavacabezas')
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        Equipamiento.objects.create(
            codigo='LAV-TEST-1',
            nombre='Lavacabezas principal',
            tipo=equipment_type,
            estado=Equipamiento.EstadoRecurso.DISPONIBLE,
            is_active=True,
        )
        actor = self.create_user('available-equipment-actor@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Turno.objects.count(), 1)

    def test_canonical_availability_returns_only_minimum_slot_data(self):
        self.authenticate(self.client_user)

        response = self.client.get(
            reverse('turno-consultar-disponibilidad'),
            {
                'servicio_id': self.service.pk,
                'fecha': self.fecha.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        day = response.data['disponibilidad'][0]
        professional = day['profesionales'][0]
        slot = next(item for item in professional['slots'] if item['hora'] == '10:00')
        self.assertEqual(set(professional), {'id', 'nombre', 'slots'})
        self.assertEqual(set(slot), {'hora', 'profesional_id'})

        legacy_response = self.client.get(
            reverse('disponibilidad-turnos'),
            {
                'servicio_id': self.service.pk,
                'fecha': self.fecha.isoformat(),
            },
        )
        self.assertEqual(legacy_response.status_code, status.HTTP_200_OK)
        self.assertIn('10:00', legacy_response.data['horarios_disponibles'])

    def test_payload_cannot_set_state(self):
        self.authenticate(self.client_user)

        response = self.client.post(
            self.reserve_url,
            self.payload(estado=Turno.Estado.CONFIRMADO),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Turno.objects.exists())

    def test_payload_cannot_set_financial_or_administrative_fields(self):
        actor = self.create_user('strict-payload@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(
                monto_abonado='5000.00',
                saldo_pendiente='0.00',
                equipamiento=1,
                comprobante_pago='archivo.pdf',
            ),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('campos_no_permitidos', response.data)
        self.assertFalse(Turno.objects.exists())

    def test_server_sets_initial_state_for_third_party_creation(self):
        actor = self.create_user('initial-state@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        response = self.client.post(
            self.for_client_url,
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        turno = Turno.objects.get()
        self.assertEqual(turno.estado, Turno.Estado.SOLICITADO)
        self.assertEqual(turno.canal_origen, Turno.CanalOrigen.PRESENCIAL)

    def test_client_and_personal_user_keeps_both_creation_intents_separate(self):
        self.assign_role(self.client_user, BusinessRole.PROFESIONAL)
        Personal.objects.create(
            usuario=self.client_user,
            nombre='Ana',
            apellido='Dual',
            rol='colorista',
            activo=True,
        )
        self.authenticate(self.client_user)

        own_response = self.client.post(
            self.reserve_url,
            self.payload(),
            format='json',
        )
        third_party_response = self.client.post(
            self.for_client_url,
            self.third_party_payload(hora_inicio='12:00'),
            format='json',
        )

        self.assertEqual(own_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(third_party_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            set(Turno.objects.values_list('cliente_id', flat=True)),
            {self.client_profile.pk, self.other_client.pk},
        )

    def test_generic_post_is_disabled_after_consumers_migrate(self):
        actor = self.create_user('generic-post@test.com', is_superuser=True, is_staff=True)
        self.authenticate(actor)

        response = self.client.post(
            reverse('turno-list'),
            self.third_party_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertFalse(Turno.objects.exists())

    def test_dedicated_selectors_require_only_create_permission_and_are_minimal(self):
        actor = self.create_user('selector-create@test.com')
        actor.user_permissions.add(self.create_turno_permission)
        self.authenticate(actor)

        clients_response = self.client.get(reverse('turno-selector-clientes'))
        personal_response = self.client.get(reverse('turno-selector-personal'))

        self.assertEqual(clients_response.status_code, status.HTTP_200_OK)
        self.assertEqual(personal_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(clients_response.data[0]),
            {'id', 'nombre', 'apellido', 'email'},
        )
        self.assertEqual(
            set(personal_response.data[0]),
            {'id', 'nombre', 'apellido', 'funcion'},
        )
        self.assertFalse(actor.has_perm('usuarios.view_clients'))
