from concurrent.futures import ThreadPoolExecutor
from datetime import time
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from gestion.models import (
    AgendaCuidados,
    CategoriaServicio,
    ConfiguracionRetoque,
    DetalleTurno,
    DiagnosticoCapilar,
    EstadoGeneral,
    FinalizacionTurno,
    Habilidad,
    Notificacion,
    Personal,
    PersonalHabilidad,
    Promocion,
    ReglaCuidado,
    Rutina,
    RutinaCliente,
    Servicio,
    Turno,
)
from usuarios.models import Cliente, Usuario


class TurnoFinalizationApiTests(APITestCase):
    def setUp(self):
        self.finalize_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='finalize_service',
        )
        self.diagnosis_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='create_diagnosis',
        )
        self.client_user = self.create_user('finalization-client@test.com')
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            activo=True,
        )
        self.actor, self.personal = self.create_finalizer(
            'assigned-finalizer@test.com'
        )
        self.client.force_authenticate(self.actor)

    @staticmethod
    def create_user(email, *, active=True):
        return Usuario.objects.create_user(
            email=email,
            password='FinalizationTests!2026',
            is_active=active,
        )

    def create_finalizer(
        self,
        email,
        *,
        active=True,
        with_permission=True,
        with_diagnosis=False,
    ):
        user = self.create_user(email)
        if with_permission:
            user.user_permissions.add(self.finalize_permission)
        if with_diagnosis:
            user.user_permissions.add(self.diagnosis_permission)
        personal = Personal.objects.create(
            usuario=user,
            nombre='Profesional',
            apellido=email.split('@')[0],
            rol='asistente',
            activo=active,
        )
        if with_diagnosis:
            diagnosis_skill, _ = Habilidad.objects.get_or_create(
                code='DIAGNOSTICO',
                defaults={'nombre': 'Diagnóstico'},
            )
            PersonalHabilidad.objects.create(
                personal=personal,
                habilidad=diagnosis_skill,
                activa=True,
            )
        return user, personal

    def create_turno(self, *, state=Turno.Estado.CONFIRMADO, minute=0, personal=None):
        return Turno.objects.create(
            cliente=self.client_profile,
            profesional=personal if personal is not None else self.personal,
            fecha=timezone.localdate(),
            hora_inicio=time(10, minute),
            estado=state,
        )

    @staticmethod
    def url(turno):
        return reverse('turno-finalizar-turno', args=[turno.pk])

    def test_confirmed_turno_is_finalized_with_persisted_result(self):
        turno = self.create_turno()

        response = self.client.post(
            self.url(turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='confirmed-finalization',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['changed'])
        self.assertEqual(response.data['estado'], Turno.Estado.REALIZADO)
        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.REALIZADO)
        finalization = FinalizacionTurno.objects.get(turno=turno)
        self.assertEqual(finalization.actor, self.actor)
        self.assertEqual(finalization.estado_anterior, Turno.Estado.CONFIRMADO)
        self.assertEqual(finalization.idempotency_key, 'confirmed-finalization')

    def test_only_confirmed_turno_can_be_finalized(self):
        invalid_states = (
            Turno.Estado.SOLICITADO,
            Turno.Estado.ESPERANDO_SENA,
            Turno.Estado.SUGERIDO,
            Turno.Estado.CANCELADO,
            Turno.Estado.AUSENTE,
            Turno.Estado.PENDIENTE,
            Turno.Estado.EN_PROCESO,
            Turno.Estado.REALIZADO,
        )

        for minute, invalid_state in enumerate(invalid_states):
            with self.subTest(state=invalid_state):
                turno = self.create_turno(
                    state=invalid_state,
                    minute=minute,
                )

                response = self.client.post(self.url(turno), {}, format='json')

                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                turno.refresh_from_db()
                self.assertEqual(turno.estado, invalid_state)

    def test_repeated_finalization_is_an_idempotent_retry(self):
        turno = self.create_turno()

        first = self.client.post(self.url(turno), {}, format='json')
        second = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data['changed'])
        self.assertFalse(second.data['changed'])
        self.assertEqual(first.data['finalization_id'], second.data['finalization_id'])
        self.assertEqual(
            first.data['idempotency_key'],
            f'legacy-turno-finalization:{turno.pk}',
        )

    def test_saving_realized_turno_does_not_repeat_finalization_effects(self):
        turno = self.create_turno()

        response = self.client.post(self.url(turno), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification_count = Notificacion.objects.filter(
            origen_entidad='Turno',
            origen_id=turno.pk,
            titulo='¡Servicio Finalizado!',
        ).count()

        turno.refresh_from_db()
        turno.save(update_fields=['estado'])

        self.assertEqual(
            Notificacion.objects.filter(
                origen_entidad='Turno',
                origen_id=turno.pk,
                titulo='¡Servicio Finalizado!',
            ).count(),
            notification_count,
        )

    def test_professional_cannot_finalize_foreign_turno(self):
        _, other_personal = self.create_finalizer('other-finalizer@test.com')
        turno = self.create_turno(personal=other_personal)

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.CONFIRMADO)

    def test_professional_without_permission_cannot_finalize(self):
        actor, personal = self.create_finalizer(
            'without-finalize-permission@test.com',
            with_permission=False,
        )
        turno = self.create_turno(personal=personal)
        self.client.force_authenticate(actor)

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.CONFIRMADO)

    def test_inactive_personal_cannot_finalize(self):
        actor, personal = self.create_finalizer(
            'inactive-finalizer@test.com',
            active=False,
        )
        turno = self.create_turno(personal=personal)
        self.client.force_authenticate(actor)

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(str(response.data['code']), 'ACTIVE_PERSONAL_REQUIRED')
        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.CONFIRMADO)

    def test_inactive_account_cannot_finalize(self):
        actor, personal = self.create_finalizer('inactive-account@test.com')
        actor.is_active = False
        actor.save(update_fields=['is_active'])
        turno = self.create_turno(personal=personal)
        self.client.force_authenticate(actor)

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.CONFIRMADO)

    def test_finalization_does_not_require_or_create_diagnosis(self):
        turno = self.create_turno()
        self.assertFalse(self.actor.has_perm('gestion.create_diagnosis'))

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(DiagnosticoCapilar.objects.exists())
        self.assertEqual(response.data['effects']['automatic_diagnosis_ids'], [])

    def test_idempotency_key_reused_for_other_turno_is_rejected(self):
        first_turno = self.create_turno(minute=1)
        second_turno = self.create_turno(minute=2)
        headers = {'HTTP_IDEMPOTENCY_KEY': 'shared-incompatible-key'}

        first = self.client.post(
            self.url(first_turno), {}, format='json', **headers
        )
        second = self.client.post(
            self.url(second_turno), {}, format='json', **headers
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(second.data['code']), 'IDEMPOTENCY_KEY_REUSED')
        second_turno.refresh_from_db()
        self.assertEqual(second_turno.estado, Turno.Estado.CONFIRMADO)

    def test_same_turno_with_different_key_is_rejected(self):
        turno = self.create_turno()
        first = self.client.post(
            self.url(turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='first-key',
        )
        second = self.client.post(
            self.url(turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='different-key',
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(second.data['code']), 'TURN_ALREADY_FINALIZED')

    def test_critical_write_failure_rolls_back_everything(self):
        turno = self.create_turno()

        with patch(
            'gestion.turno_finalization_services.Notificacion.objects.create',
            side_effect=RuntimeError('notification storage unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                from gestion.turno_finalization_services import finalize_turno

                finalize_turno(
                    actor=self.actor,
                    turno_id=turno.pk,
                    idempotency_key='rollback-finalization',
                )

        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.CONFIRMADO)
        self.assertFalse(FinalizacionTurno.objects.filter(turno=turno).exists())
        self.assertFalse(Notificacion.objects.filter(origen_id=turno.pk).exists())

    def test_retry_does_not_duplicate_routine_notifications_or_promotion(self):
        routine = Rutina.objects.create(
            nombre='Rutina post servicio',
            objetivo='Cuidado',
            archivo='rutinas_pdfs/test.pdf',
            estado='publicada',
            creada_por=self.actor,
        )
        category = CategoriaServicio.objects.create(nombre='Efectos únicos')
        service = Servicio.objects.create(
            nombre='Servicio con efectos únicos',
            categoria=category,
            duracion_estimada=30,
            precio_base='1000.00',
            rutina_recomendada=routine,
        )
        ReglaCuidado.objects.create(
            servicio=service,
            tipo='RESTRICCION',
            descripcion='No lavar',
            dias_duracion=2,
            rutina=routine,
        )
        ConfiguracionRetoque.objects.create(
            servicio_principal=service,
            servicio_retoque=service,
            dias_sugeridos=21,
            descuento_retoque=10,
        )
        turno = self.create_turno()
        DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico=service.precio_base,
            duracion_minutos=30,
        )
        headers = {'HTTP_IDEMPOTENCY_KEY': 'effects-once'}

        first = self.client.post(self.url(turno), {}, format='json', **headers)
        counts = {
            'care_items': AgendaCuidados.objects.count(),
            'routines': RutinaCliente.objects.count(),
            'notifications': Notificacion.objects.filter(
                origen_entidad='Turno', origen_id=turno.pk
            ).count(),
            'promotions': Promocion.objects.filter(
                cliente_especifico=self.client_profile,
                tipo='RETOQUE',
            ).count(),
        }
        second = self.client.post(self.url(turno), {}, format='json', **headers)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(RutinaCliente.objects.count(), counts['routines'])
        self.assertEqual(AgendaCuidados.objects.count(), counts['care_items'])
        self.assertEqual(
            Notificacion.objects.filter(
                origen_entidad='Turno', origen_id=turno.pk
            ).count(),
            counts['notifications'],
        )
        self.assertEqual(
            Promocion.objects.filter(
                cliente_especifico=self.client_profile,
                tipo='RETOQUE',
            ).count(),
            counts['promotions'],
        )
        self.assertEqual(counts, {
            'care_items': 2,
            'routines': 1,
            'notifications': 2,
            'promotions': 1,
        })

    def test_multiservice_preserves_profile_and_records_each_impact(self):
        initial_state = EstadoGeneral.objects.create(nombre='Inicial multiservicio')
        first_impact = EstadoGeneral.objects.create(nombre='Primer impacto')
        second_impact = EstadoGeneral.objects.create(nombre='Segundo impacto')
        self.client_profile.estado_general = initial_state
        self.client_profile.save(update_fields=['estado_general'])
        category = CategoriaServicio.objects.create(nombre='Multiservicio')
        services = [
            Servicio.objects.create(
                nombre=f'Servicio multiservicio {index}',
                categoria=category,
                duracion_estimada=30,
                precio_base='1000.00',
                impacto_estado=impact,
            )
            for index, impact in enumerate((first_impact, second_impact), start=1)
        ]
        turno = self.create_turno()
        for service in reversed(services):
            DetalleTurno.objects.create(
                turno=turno,
                servicio=service,
                precio_historico=service.precio_base,
                duracion_minutos=30,
            )

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.estado_general, initial_state)
        profile_effect = response.data['effects']['profile']
        self.assertFalse(profile_effect['applied'])
        self.assertEqual(profile_effect['reason'], 'MULTISERVICE_POLICY_PENDING')
        self.assertEqual(len(profile_effect['service_impacts']), 2)

    def test_single_service_applies_only_explicit_hair_impact(self):
        initial_state = EstadoGeneral.objects.create(nombre='Estado inicial')
        explicit_impact = EstadoGeneral.objects.create(nombre='Impacto explícito')
        self.client_profile.estado_general = initial_state
        self.client_profile.save(update_fields=['estado_general'])
        service = Servicio.objects.create(
            nombre='Servicio con impacto explícito',
            duracion_estimada=30,
            precio_base='1000.00',
            impacto_estado=explicit_impact,
        )
        turno = self.create_turno()
        DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico=service.precio_base,
            duracion_minutos=30,
        )

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.estado_general, explicit_impact)
        self.assertEqual(
            response.data['effects']['profile']['updated_fields'],
            ['estado_general'],
        )

    def test_null_hair_impact_does_not_clear_general_state(self):
        current_state = EstadoGeneral.objects.create(nombre='Estado preservado')
        self.client_profile.estado_general = current_state
        self.client_profile.save(update_fields=['estado_general'])
        category = CategoriaServicio.objects.create(nombre='Sin impacto')
        service = Servicio.objects.create(
            nombre='Servicio sin impacto capilar',
            categoria=category,
            duracion_estimada=30,
            precio_base='1000.00',
            impacto_estado=None,
        )
        turno = self.create_turno()
        DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico=service.precio_base,
            duracion_minutos=30,
        )

        response = self.client.post(self.url(turno), {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.estado_general, current_state)


class TurnoFinalizationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.finalize_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='finalize_service',
        )
        self.actor = Usuario.objects.create_user(
            email='concurrent-finalizer@test.com',
            password='FinalizationTests!2026',
        )
        self.actor.user_permissions.add(self.finalize_permission)
        self.personal = Personal.objects.create(
            usuario=self.actor,
            nombre='Concurrente',
            apellido='Finalizador',
            rol='asistente',
            activo=True,
        )
        client_user = Usuario.objects.create_user(
            email='concurrent-client@test.com',
            password='FinalizationTests!2026',
        )
        client_profile = Cliente.objects.create(
            usuario=client_user,
            activo=True,
        )
        self.turno = Turno.objects.create(
            cliente=client_profile,
            profesional=self.personal,
            fecha=timezone.localdate(),
            hora_inicio=time(12, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        self.url = reverse('turno-finalizar-turno', args=[self.turno.pk])

    def _request_finalization(self, barrier):
        close_old_connections()
        try:
            actor = Usuario.objects.get(pk=self.actor.pk)
            client = APIClient()
            client.force_authenticate(actor)
            barrier.wait(timeout=10)
            response = client.post(
                self.url,
                {},
                format='json',
                HTTP_IDEMPOTENCY_KEY='concurrent-finalization',
            )
            return response.status_code, response.data
        finally:
            close_old_connections()

    def test_two_concurrent_requests_produce_one_finalization(self):
        self.assertEqual(connection.vendor, 'postgresql')
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self._request_finalization, barrier)
                for _ in range(2)
            ]
            responses = [future.result(timeout=20) for future in futures]

        self.assertEqual([item[0] for item in responses], [200, 200])
        self.assertEqual(
            sorted(item[1]['changed'] for item in responses),
            [False, True],
        )
        self.assertEqual(FinalizacionTurno.objects.filter(turno=self.turno).count(), 1)
        self.assertEqual(
            Notificacion.objects.filter(
                origen_entidad='Turno',
                origen_id=self.turno.pk,
                titulo='¡Servicio Finalizado!',
            ).count(),
            1,
        )
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.REALIZADO)
