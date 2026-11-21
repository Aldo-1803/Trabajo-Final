from datetime import datetime, time, timedelta

from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    BloqueoAgenda,
    CategoriaServicio,
    DetalleTurno,
    Habilidad,
    HorarioLaboral,
    Personal,
    PersonalHabilidad,
    RequisitoServicio,
    Servicio,
    ServicioHabilidad,
    TipoEquipamiento,
    Turno,
)
from gestion.service_skill_compatibility import (
    personal_can_perform_service,
    personal_can_perform_services,
)
from gestion.turno_creation_services import (
    TurnoAvailabilityService,
    TurnoCreationError,
)
from usuarios.models import Cliente, Usuario


class TurnoCanonicalSkillCompatibilityTests(APITestCase):
    def setUp(self):
        self.fecha = timezone.localdate() + timedelta(days=3)
        self.hora = time(10, 0)
        self.personal = Personal.objects.create(
            nombre='Julia',
            apellido='Skills',
            rol='asistente',
            activo=True,
            realiza_color=False,
            realiza_lavado=False,
        )
        self.schedule = HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=self.fecha.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
            permite_diseno_color=True,
            permite_complemento=True,
        )
        self.service = Servicio.objects.create(
            nombre='Servicio compatibilidad canónica',
            duracion_estimada=60,
            precio_base='5000.00',
            activo=True,
        )
        self.color = Habilidad.objects.get(code='COLORACION')
        self.lavado = Habilidad.objects.get(code='LAVADO')

    def require(self, service, skill):
        return ServicioHabilidad.objects.create(servicio=service, habilidad=skill)

    def assign(self, personal, skill, *, active=True):
        return PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=skill,
            activa=active,
        )

    def validate(self, **overrides):
        arguments = {
            'fecha': self.fecha,
            'hora_inicio': self.hora,
            'servicio': self.service,
            'profesional': self.personal,
        }
        arguments.update(overrides)
        return TurnoAvailabilityService.validate_slot(**arguments)

    def assert_validation_code(self, expected_code, **overrides):
        with self.assertRaises(TurnoCreationError) as raised:
            self.validate(**overrides)
        self.assertEqual(raised.exception.code, expected_code)

    def test_service_without_skills_adds_no_technical_restriction(self):
        self.assertTrue(personal_can_perform_service(self.personal, self.service))
        self.assertTrue(self.validate())

    def test_active_required_skill_and_assignment_are_compatible(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color)

        self.assertTrue(personal_can_perform_service(self.personal, self.service))
        self.assertTrue(self.validate())

    def test_missing_assignment_is_incompatible(self):
        self.require(self.service, self.color)

        self.assertFalse(personal_can_perform_service(self.personal, self.service))
        self.assert_validation_code('PERSONAL_SKILL_MISMATCH')

    def test_inactive_assignment_is_incompatible(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color, active=False)

        self.assert_validation_code('PERSONAL_SKILL_MISMATCH')

    def test_inactive_required_skill_fails_closed(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color)
        self.color.activa = False
        self.color.save(update_fields=['activa'])

        self.assert_validation_code('INACTIVE_REQUIRED_SKILL')
        self.assertFalse(
            TurnoAvailabilityService.matching_schedules(
                fecha=self.fecha,
                servicio=self.service,
            ).exists()
        )

    def test_legacy_true_does_not_replace_missing_canonical_assignment(self):
        self.personal.realiza_color = True
        self.personal.save(update_fields=['realiza_color'])
        self.require(self.service, self.color)

        self.assert_validation_code('PERSONAL_SKILL_MISMATCH')

    def test_legacy_false_does_not_block_active_canonical_assignment(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color)

        self.assertFalse(self.personal.realiza_color)
        self.assertTrue(self.validate())

    def test_single_service_requires_all_skills(self):
        self.require(self.service, self.color)
        self.require(self.service, self.lavado)
        self.assign(self.personal, self.color)

        self.assertFalse(personal_can_perform_service(self.personal, self.service))
        self.assign(self.personal, self.lavado)
        self.assertTrue(personal_can_perform_service(self.personal, self.service))

    def test_multiservice_requires_union_of_skills(self):
        second_service = Servicio.objects.create(
            nombre='Segundo Servicio skills', activo=True, duracion_estimada=30
        )
        self.require(self.service, self.color)
        self.require(second_service, self.lavado)
        self.assign(self.personal, self.color)

        self.assertFalse(personal_can_perform_services(
            self.personal, (self.service, second_service)
        ))
        self.assert_validation_code(
            'PERSONAL_SKILL_MISMATCH',
            servicios=(self.service, second_service),
            duracion_minutos=90,
        )

        self.assign(self.personal, self.lavado)
        self.assertTrue(personal_can_perform_services(
            self.personal, (self.service, second_service)
        ))
        self.assertTrue(self.validate(
            servicios=(self.service, second_service),
            duracion_minutos=90,
        ))

    def test_skill_does_not_bypass_schedule_or_block_rules(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color)
        self.schedule.permite_diseno_color = False
        self.schedule.save(update_fields=['permite_diseno_color'])
        self.assert_validation_code('OUTSIDE_WORK_SCHEDULE')

        self.schedule.permite_diseno_color = True
        self.schedule.save(update_fields=['permite_diseno_color'])
        BloqueoAgenda.objects.create(
            personal=self.personal,
            fecha_inicio=timezone.make_aware(
                datetime.combine(self.fecha, time(9, 30))
            ),
            fecha_fin=timezone.make_aware(
                datetime.combine(self.fecha, time(11, 30))
            ),
            motivo='Bloqueo de prueba',
        )
        self.assert_validation_code('SLOT_BLOCKED')

    def test_skill_does_not_bypass_equipment_rules(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color)
        equipment_type = TipoEquipamiento.objects.create(
            nombre='Equipo requerido por servicio con skill'
        )
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )

        self.assert_validation_code('EQUIPMENT_UNAVAILABLE')

    def test_skill_does_not_bypass_overlap_rules(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color)
        user = Usuario.objects.create_user(
            email='overlap-skill@test.com', password='SkillTurno!2026'
        )
        client = Cliente.objects.create(usuario=user, activo=True)
        occupied = Turno.objects.create(
            cliente=client,
            profesional=self.personal,
            fecha=self.fecha,
            hora_inicio=self.hora,
            estado=Turno.Estado.CONFIRMADO,
        )
        DetalleTurno.objects.create(
            turno=occupied,
            servicio=self.service,
            precio_historico=self.service.precio_base,
            duracion_minutos=60,
        )

        self.assert_validation_code('SLOT_UNAVAILABLE')

    def test_inactive_personal_is_never_eligible(self):
        self.require(self.service, self.color)
        self.assign(self.personal, self.color)
        self.personal.activo = False
        self.personal.save(update_fields=['activo'])

        self.assert_validation_code('INACTIVE_PERSONAL')

    def test_legacy_and_canonical_results_match_backfilled_classification(self):
        color_category = CategoriaServicio.objects.create(nombre='Diseño y Color')
        complement_category = CategoriaServicio.objects.create(nombre='Complemento')
        other_category = CategoriaServicio.objects.create(nombre='Corte')
        color_service = Servicio.objects.create(
            nombre='Color legacy comparable', categoria=color_category
        )
        complement_service = Servicio.objects.create(
            nombre='Lavado legacy comparable', categoria=complement_category
        )
        other_service = Servicio.objects.create(
            nombre='Corte legacy comparable', categoria=other_category
        )
        self.require(color_service, self.color)
        self.require(complement_service, self.lavado)

        personnel = [
            Personal.objects.create(
                nombre='Solo color', apellido='Legacy', rol='colorista',
                realiza_color=True, realiza_lavado=False,
            ),
            Personal.objects.create(
                nombre='Solo lavado', apellido='Legacy', rol='asistente',
                realiza_color=False, realiza_lavado=True,
            ),
        ]
        self.assign(personnel[0], self.color)
        self.assign(personnel[1], self.lavado)

        def legacy_result(personal, service):
            category = service.categoria.nombre.lower()
            if 'diseño' in category or 'color' in category:
                return personal.realiza_color
            if 'complemento' in category:
                return personal.realiza_lavado
            return True

        for personal in personnel:
            for service in (color_service, complement_service, other_service):
                with self.subTest(personal=personal.pk, service=service.pk):
                    self.assertEqual(
                        legacy_result(personal, service),
                        personal_can_perform_service(personal, service),
                    )


class TurnoSkillEnforcementApiTests(APITestCase):
    def setUp(self):
        self.fecha = timezone.localdate() + timedelta(days=4)
        self.hora = time(10, 0)
        self.color = Habilidad.objects.get(code='COLORACION')
        self.service = Servicio.objects.create(
            nombre='Servicio API requiere color',
            duracion_estimada=60,
            precio_base='5000.00',
            activo=True,
        )
        ServicioHabilidad.objects.create(servicio=self.service, habilidad=self.color)
        self.personal = Personal.objects.create(
            nombre='Personal', apellido='Sin skill', rol='colorista',
            activo=True, realiza_color=True,
        )
        HorarioLaboral.objects.create(
            personal=self.personal,
            dia_semana=self.fecha.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
            permite_diseno_color=True,
        )
        self.client_user = Usuario.objects.create_user(
            email='skill-client@test.com', password='SkillTurno!2026'
        )
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user, activo=True
        )
        self.employee = Usuario.objects.create_user(
            email='skill-employee@test.com', password='SkillTurno!2026'
        )
        self.employee.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_turno_for_client',
        ))

    def payload(self):
        return {
            'servicio': self.service.pk,
            'profesional': self.personal.pk,
            'fecha': self.fecha.isoformat(),
            'hora_inicio': self.hora.strftime('%H:%M'),
        }

    def test_client_cannot_force_personal_without_required_skill(self):
        self.client.force_authenticate(self.client_user)
        response = self.client.post(
            reverse('turno-reservar'), self.payload(), format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['code']), 'PERSONAL_SKILL_MISMATCH')
        self.assertFalse(Turno.objects.exists())

    def test_employee_cannot_force_personal_without_required_skill(self):
        self.client.force_authenticate(self.employee)
        response = self.client.post(
            reverse('turno-crear-para-cliente'),
            {**self.payload(), 'cliente_id': self.client_profile.pk},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(str(response.data['code']), 'PERSONAL_SKILL_MISMATCH')

    def test_compatible_personal_can_create(self):
        PersonalHabilidad.objects.create(
            personal=self.personal, habilidad=self.color, activa=True
        )
        self.client.force_authenticate(self.client_user)

        response = self.client.post(
            reverse('turno-reservar'), self.payload(), format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_service_aware_selector_excludes_incompatible_personal(self):
        compatible = Personal.objects.create(
            nombre='Compatible', apellido='Selector', rol='colorista', activo=True
        )
        PersonalHabilidad.objects.create(
            personal=compatible, habilidad=self.color, activa=True
        )
        self.client.force_authenticate(self.employee)

        response = self.client.get(
            reverse('turno-selector-personal'),
            {'servicio_ids': str(self.service.pk)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item['id'] for item in response.data}, {compatible.pk})

    def test_availability_exposes_only_canonically_compatible_personal(self):
        self.client.force_authenticate(self.client_user)
        url = reverse('turno-consultar-disponibilidad')
        params = {
            'servicio_id': self.service.pk,
            'fecha': self.fecha.isoformat(),
        }

        incompatible_response = self.client.get(url, params)
        self.assertEqual(incompatible_response.status_code, status.HTTP_200_OK)
        self.assertEqual(incompatible_response.data['disponibilidad'], [])

        PersonalHabilidad.objects.create(
            personal=self.personal, habilidad=self.color, activa=True
        )
        compatible_response = self.client.get(url, params)
        professional_ids = {
            professional['id']
            for day in compatible_response.data['disponibilidad']
            for professional in day['profesionales']
        }
        self.assertEqual(professional_ids, {self.personal.pk})


class TurnoSkillReprogrammingTests(APITestCase):
    def setUp(self):
        self.original_date = timezone.localdate() + timedelta(days=6)
        self.new_date = timezone.localdate() + timedelta(days=7)
        self.color = Habilidad.objects.get(code='COLORACION')
        self.service = Servicio.objects.create(
            nombre='Servicio reprogramación con skill',
            duracion_estimada=60,
            precio_base='5000.00',
            activo=True,
        )
        ServicioHabilidad.objects.create(servicio=self.service, habilidad=self.color)
        self.target = Personal.objects.create(
            nombre='Destino', apellido='Incompatible', rol='colorista',
            activo=True, realiza_color=True,
        )
        HorarioLaboral.objects.create(
            personal=self.target,
            dia_semana=self.new_date.weekday(),
            hora_inicio=time(8, 0),
            hora_fin=time(18, 0),
            activo=True,
            permite_diseno_color=True,
        )
        user = Usuario.objects.create_user(
            email='reprogram-skill-client@test.com', password='SkillTurno!2026'
        )
        client_profile = Cliente.objects.create(usuario=user, activo=True)
        self.turno = Turno.objects.create(
            cliente=client_profile,
            profesional=self.target,
            fecha=self.original_date,
            hora_inicio=time(10, 0),
            estado=Turno.Estado.SOLICITADO,
        )
        DetalleTurno.objects.create(
            turno=self.turno,
            servicio=self.service,
            precio_historico=self.service.precio_base,
            duracion_minutos=60,
        )
        self.actor = Usuario.objects.create_user(
            email='reprogram-skill-actor@test.com', password='SkillTurno!2026'
        )
        self.actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='reprogram_any_turno',
        ))
        self.client.force_authenticate(self.actor)

    def payload(self):
        return {
            'fecha': self.new_date.isoformat(),
            'hora': '11:00',
            'profesional_id': self.target.pk,
            'motivo': 'Validar skills canónicas',
        }

    def test_reprogramming_rejects_incompatible_personal(self):
        response = self.client.post(
            reverse('turno-reprogramar', args=[self.turno.pk]),
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(response.data['code']), 'PERSONAL_SKILL_MISMATCH')

    def test_reprogramming_accepts_compatible_personal(self):
        PersonalHabilidad.objects.create(
            personal=self.target, habilidad=self.color, activa=True
        )

        response = self.client.post(
            reverse('turno-reprogramar', args=[self.turno.pk]),
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
