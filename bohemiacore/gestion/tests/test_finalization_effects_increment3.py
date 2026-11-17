from datetime import time, timedelta

from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.finalization_effect_services import (
    execute_finalization_effects,
    inspect_effect_ledger,
)
from gestion.models import (
    AgendaCuidados,
    CambioPerfilCapilar,
    ConfiguracionRetoque,
    DetalleTurno,
    DiagnosticoCapilar,
    EfectoFinalizacion,
    EstadoGeneral,
    FichaTecnica,
    FinalizacionTurno,
    Notificacion,
    Personal,
    PerfilTecnicoServicio,
    Promocion,
    ReglaCuidado,
    Rutina,
    RutinaCliente,
    Servicio,
    Turno,
)
from usuarios.models import Cliente, Usuario


class FinalizationEffectsIncrement3Tests(APITestCase):
    def setUp(self):
        self.finalize_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='finalize_service',
        )
        self.actor = Usuario.objects.create_user(
            email='increment3-finalizer@test.com'
        )
        self.actor.user_permissions.add(self.finalize_permission)
        self.personal = Personal.objects.create(
            usuario=self.actor,
            nombre='Profesional',
            apellido='Incremento 3',
            rol='colorista',
            activo=True,
        )
        self.client_user = Usuario.objects.create_user(
            email='increment3-client@test.com'
        )
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            activo=True,
        )
        self.client.force_authenticate(self.actor)

    def create_turno(self, *, minute=0, personal=None):
        return Turno.objects.create(
            cliente=self.client_profile,
            profesional=personal or self.personal,
            fecha=timezone.localdate() + timedelta(days=3),
            hora_inicio=time(10, minute),
            estado=Turno.Estado.CONFIRMADO,
        )

    @staticmethod
    def add_detail(turno, service):
        return DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico=service.precio_base,
            duracion_minutos=service.duracion_estimada,
        )

    def create_effectful_service(self, suffix='principal', *, impact=True):
        routine = Rutina.objects.create(
            nombre=f'Rutina {suffix}',
            objetivo='Cuidado trazable',
            descripcion='Snapshot de rutina',
            archivo=f'rutinas_pdfs/{suffix}.pdf',
            estado='publicada',
            creada_por=self.actor,
        )
        state = (
            EstadoGeneral.objects.create(nombre=f'Impacto {suffix}')
            if impact
            else None
        )
        service = Servicio.objects.create(
            nombre=f'Servicio {suffix}',
            precio_base='1500.00',
            duracion_estimada=60,
            rutina_recomendada=routine,
            impacto_estado=state,
        )
        rule = ReglaCuidado.objects.create(
            servicio=service,
            tipo='RESTRICCION',
            descripcion='No lavar durante el período indicado',
            dias_duracion=2,
            rutina=routine,
        )
        configuration = ConfiguracionRetoque.objects.create(
            servicio_principal=service,
            servicio_retoque=service,
            dias_sugeridos=21,
            descuento_retoque=12,
        )
        return service, routine, rule, configuration, state

    @staticmethod
    def url(turno):
        return reverse('turno-finalizar-turno', args=[turno.pk])

    def finalize(self, turno, *, key='increment3-finalization'):
        return self.client.post(
            self.url(turno),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_each_effect_has_persisted_cause_identity_and_snapshot(self):
        service, routine, rule, configuration, _ = self.create_effectful_service()
        turno = self.create_turno()
        detail = self.add_detail(turno, service)

        response = self.finalize(turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        finalization = FinalizacionTurno.objects.get(turno=turno)
        effects = list(finalization.efectos_trazables.all())
        self.assertEqual(len(effects), 9)
        self.assertEqual(
            len({effect.clave_logica for effect in effects}),
            len(effects),
        )
        self.assertEqual(
            finalization.parametros_snapshot['schema'],
            'turno.finalization.effects:v1',
        )
        care = finalization.efectos_trazables.get(
            tipo=EfectoFinalizacion.Tipo.CUIDADO_AGENDA,
            clave_logica=f'care-item:{detail.pk}:{rule.pk}:{turno.fecha.isoformat()}',
        )
        self.assertEqual(care.detalle_turno, detail)
        self.assertEqual(care.servicio, service)
        self.assertEqual(care.regla_cuidado, rule)
        self.assertEqual(care.parametros_snapshot['dias_duracion'], 2)
        routine_effect = finalization.efectos_trazables.get(
            tipo=EfectoFinalizacion.Tipo.ASIGNACION_RUTINA
        )
        self.assertEqual(routine_effect.rutina, routine)
        promotion_effect = finalization.efectos_trazables.get(
            tipo=EfectoFinalizacion.Tipo.PROMOCION_RETOQUE
        )
        self.assertEqual(
            promotion_effect.configuracion_retoque,
            configuration,
        )

    def test_effect_logical_identity_has_database_uniqueness(self):
        service, *_ = self.create_effectful_service('unique')
        turno = self.create_turno()
        self.add_detail(turno, service)
        self.finalize(turno)
        effect = EfectoFinalizacion.objects.first()

        with self.assertRaises(IntegrityError), transaction.atomic():
            EfectoFinalizacion.objects.create(
                finalizacion=effect.finalizacion,
                tipo=effect.tipo,
                estado=effect.estado,
                clave_logica=effect.clave_logica,
            )

    def test_initial_result_is_structured_and_retry_returns_persisted_result(self):
        service, *_ = self.create_effectful_service('retry')
        turno = self.create_turno()
        self.add_detail(turno, service)

        first = self.finalize(turno, key='same-effect-result')
        counts = {
            'effects': EfectoFinalizacion.objects.count(),
            'care': AgendaCuidados.objects.count(),
            'notifications': Notificacion.objects.count(),
            'promotions': Promocion.objects.count(),
            'routines': RutinaCliente.objects.count(),
        }
        second = self.finalize(turno, key='same-effect-result')

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data['changed'])
        self.assertFalse(second.data['changed'])
        self.assertEqual(first.data['effects'], second.data['effects'])
        self.assertEqual(
            first.data['effects']['summary']['schema'],
            'turno.finalization.effects:v1',
        )
        self.assertEqual(counts, {
            'effects': EfectoFinalizacion.objects.count(),
            'care': AgendaCuidados.objects.count(),
            'notifications': Notificacion.objects.count(),
            'promotions': Promocion.objects.count(),
            'routines': RutinaCliente.objects.count(),
        })

    def test_individual_ledger_handler_is_idempotent(self):
        service, *_ = self.create_effectful_service('handler')
        turno = self.create_turno()
        self.add_detail(turno, service)
        self.finalize(turno)
        finalization = FinalizacionTurno.objects.get(turno=turno)
        before = {
            'effects': EfectoFinalizacion.objects.count(),
            'care': AgendaCuidados.objects.count(),
            'notifications': Notificacion.objects.count(),
            'promotions': Promocion.objects.count(),
            'routines': RutinaCliente.objects.count(),
            'profile': CambioPerfilCapilar.objects.count(),
        }

        replay = execute_finalization_effects(
            turno=turno,
            actor=self.actor,
            plan=finalization.parametros_snapshot,
            finalization=finalization,
        )

        self.assertEqual(
            replay.legacy_effects['final_notification_id'],
            finalization.efectos['final_notification_id'],
        )
        self.assertEqual(before, {
            'effects': EfectoFinalizacion.objects.count(),
            'care': AgendaCuidados.objects.count(),
            'notifications': Notificacion.objects.count(),
            'promotions': Promocion.objects.count(),
            'routines': RutinaCliente.objects.count(),
            'profile': CambioPerfilCapilar.objects.count(),
        })

    def test_read_only_reconciliation_verifies_outputs_and_detects_loss(self):
        service, *_ = self.create_effectful_service('inspection')
        turno = self.create_turno()
        self.add_detail(turno, service)
        self.finalize(turno)
        finalization = FinalizacionTurno.objects.get(turno=turno)

        complete = inspect_effect_ledger(finalization)
        care = AgendaCuidados.objects.get(
            pk=finalization.efectos['care_item_ids'][0]
        )
        care.delete()
        incomplete = inspect_effect_ledger(finalization)

        self.assertTrue(complete['complete'])
        self.assertFalse(incomplete['complete'])
        self.assertTrue(incomplete['missing_outputs'])
        self.assertEqual(incomplete['pending'], [])
        self.assertEqual(incomplete['failed'], [])

    def test_historical_unversioned_result_is_not_reinterpreted(self):
        turno = self.create_turno()
        turno.estado = Turno.Estado.REALIZADO
        turno.save(update_fields=['estado'])
        historical = FinalizacionTurno.objects.create(
            turno=turno,
            actor=self.actor,
            idempotency_key='legacy-unversioned-result',
            command_fingerprint='0' * 64,
            estado_anterior=Turno.Estado.CONFIRMADO,
            estado_final=Turno.Estado.REALIZADO,
            parametros_snapshot={},
            efectos={'final_notification_id': 999},
        )

        report = inspect_effect_ledger(historical)

        self.assertFalse(report['reconciliation_supported'])
        self.assertTrue(report['legacy_unversioned'])
        self.assertIsNone(report['complete'])
        self.assertFalse(EfectoFinalizacion.objects.exists())

    def test_rule_changes_after_completion_do_not_change_retry(self):
        service, routine, rule, configuration, _ = self.create_effectful_service(
            'snapshot'
        )
        turno = self.create_turno()
        self.add_detail(turno, service)
        first = self.finalize(turno, key='snapshot-retry')
        first_effects = first.data['effects']
        initial_dates = list(
            AgendaCuidados.objects.values_list('fecha', flat=True).order_by('fecha')
        )

        rule.dias_duracion = 8
        rule.descripcion = 'Regla modificada después del evento'
        rule.save(update_fields=['dias_duracion', 'descripcion'])
        configuration.dias_sugeridos = 90
        configuration.save(update_fields=['dias_sugeridos'])
        routine.version += 1
        routine.save(update_fields=['version'])
        second = self.finalize(turno, key='snapshot-retry')

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(second.data['changed'])
        self.assertEqual(second.data['effects'], first_effects)
        self.assertEqual(
            list(AgendaCuidados.objects.values_list('fecha', flat=True).order_by('fecha')),
            initial_dates,
        )
        finalization = FinalizacionTurno.objects.get(turno=turno)
        rule_snapshot = finalization.parametros_snapshot['detalles'][0][
            'reglas_cuidado'
        ][0]
        self.assertEqual(rule_snapshot['dias_duracion'], 2)
        self.assertEqual(
            finalization.parametros_snapshot['rutinas'][0]['version'],
            1,
        )

    def test_existing_shared_routine_is_reused_without_duplicate(self):
        service, routine, *_ = self.create_effectful_service('existing-routine')
        existing = routine.asignar_a_cliente(self.client_profile)
        turno = self.create_turno()
        self.add_detail(turno, service)

        response = self.finalize(turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(RutinaCliente.objects.count(), 1)
        effect = EfectoFinalizacion.objects.get(
            tipo=EfectoFinalizacion.Tipo.ASIGNACION_RUTINA
        )
        self.assertEqual(effect.resultado['id'], existing.pk)
        self.assertFalse(effect.resultado['created'])

    def test_existing_notification_and_promotion_do_not_replace_event_outputs(self):
        service, *_ = self.create_effectful_service('existing-outputs')
        turno = self.create_turno()
        self.add_detail(turno, service)
        Notificacion.objects.create(
            usuario=self.client_user,
            titulo='¡Servicio Finalizado!',
            mensaje='Notificación previa no causal',
            origen_entidad='Turno',
            origen_id=turno.pk,
        )
        Promocion.objects.create(
            nombre='Promoción previa',
            descripcion='No corresponde a esta finalización',
            tipo='RETOQUE',
            fecha_inicio=turno.fecha,
            fecha_fin=turno.fecha + timedelta(days=1),
            cliente_especifico=self.client_profile,
        )

        response = self.finalize(turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Notificacion.objects.count(), 3)
        self.assertEqual(Promocion.objects.count(), 2)
        self.assertEqual(
            EfectoFinalizacion.objects.filter(
                tipo=EfectoFinalizacion.Tipo.NOTIFICACION_FINAL,
                estado=EfectoFinalizacion.Estado.COMPLETADO,
            ).count(),
            1,
        )

    def test_retouch_dates_are_anchored_to_turno_business_date(self):
        service, _, _, configuration, _ = self.create_effectful_service('dates')
        turno = self.create_turno()
        self.add_detail(turno, service)

        self.finalize(turno)

        promotion = Promocion.objects.get()
        ideal = turno.fecha + timedelta(days=configuration.dias_sugeridos)
        self.assertEqual(promotion.fecha_inicio, ideal - timedelta(days=7))
        self.assertEqual(promotion.fecha_fin, ideal + timedelta(days=7))
        self.assertEqual(
            promotion.fecha_envio_notificacion,
            ideal - timedelta(days=7),
        )
        self.assertEqual(list(promotion.servicios.all()), [service])

    def test_no_hair_data_or_professional_evaluation_is_invented(self):
        service, *_ = self.create_effectful_service('no-impact', impact=False)
        turno = self.create_turno()
        self.add_detail(turno, service)

        response = self.finalize(turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_profile.refresh_from_db()
        self.assertIsNone(self.client_profile.estado_general_id)
        self.assertFalse(DiagnosticoCapilar.objects.exists())
        self.assertFalse(CambioPerfilCapilar.objects.exists())
        self.assertEqual(
            EfectoFinalizacion.objects.get(
                tipo=EfectoFinalizacion.Tipo.DIAGNOSTICO_AUTOMATICO
            ).estado,
            EfectoFinalizacion.Estado.OMITIDO,
        )

    def test_multiservice_incompatible_impacts_are_preserved_not_applied(self):
        initial = EstadoGeneral.objects.create(nombre='Estado previo estable')
        self.client_profile.estado_general = initial
        self.client_profile.save(update_fields=['estado_general'])
        first, *_ = self.create_effectful_service('multi-a')
        second, *_ = self.create_effectful_service('multi-b')
        turno = self.create_turno()
        self.add_detail(turno, second)
        self.add_detail(turno, first)

        response = self.finalize(turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.estado_general, initial)
        profile = response.data['effects']['profile']
        self.assertEqual(profile['reason'], 'MULTISERVICE_POLICY_PENDING')
        self.assertEqual(len(profile['service_impacts']), 2)
        self.assertFalse(CambioPerfilCapilar.objects.exists())

    def test_profile_change_references_finalization_cause_without_diagnosis(self):
        service, _, _, _, impact = self.create_effectful_service('profile')
        turno = self.create_turno()
        self.add_detail(turno, service)

        response = self.finalize(turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        change = CambioPerfilCapilar.objects.get()
        finalization = FinalizacionTurno.objects.get(turno=turno)
        self.assertIn(str(finalization.public_id), change.motivo)
        self.assertEqual(
            change.procedencia,
            DiagnosticoCapilar.Procedencia.POST_SERVICIO_AUTOMATICO,
        )
        self.assertIsNone(change.diagnostico_fuente)
        self.client_profile.refresh_from_db()
        self.assertEqual(self.client_profile.estado_general, impact)

    def test_summary_does_not_expose_internal_snapshots_or_formula_data(self):
        service, *_ = self.create_effectful_service('safe-contract')
        service.plantilla_formula = 'FÓRMULA SECRETA'
        service.save(update_fields=['plantilla_formula'])
        turno = self.create_turno()
        self.add_detail(turno, service)

        response = self.finalize(turno)

        serialized = str(response.data['effects']['summary'])
        self.assertNotIn('FÓRMULA SECRETA', serialized)
        self.assertNotIn('parametros_snapshot', serialized)
        self.assertNotIn('descripcion', serialized)

    def test_required_complete_record_remains_compatible(self):
        service, *_ = self.create_effectful_service('technical-record')
        profile, _ = PerfilTecnicoServicio.objects.update_or_create(
            servicio=service,
            defaults={
                'requisito_ficha': PerfilTecnicoServicio.RequisitoFicha.REQUERIDA,
                'modo_formula_ficha': PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA,
                'campos_requeridos_ficha': ['observaciones_proceso'],
            },
        )
        self.assertIsNotNone(profile)
        turno = self.create_turno()
        detail = self.add_detail(turno, service)
        FichaTecnica.objects.create(
            detalle_turno=detail,
            profesional_autor=self.actor,
            completada_por=self.actor,
            observaciones_proceso='Proceso completo',
            estado=FichaTecnica.Estado.COMPLETA,
            completada_en=timezone.now(),
        )

        response = self.finalize(turno)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['effects']['technical_records'][0]['complete'])

    def test_403_and_409_create_no_additional_effects(self):
        service, *_ = self.create_effectful_service('authority')
        unauthorized = Usuario.objects.create_user(
            email='increment3-unauthorized@test.com'
        )
        other_personal = Personal.objects.create(
            usuario=unauthorized,
            nombre='Sin',
            apellido='Permiso',
            rol='asistente',
            activo=True,
        )
        turno = self.create_turno(personal=other_personal)
        self.add_detail(turno, service)
        self.client.force_authenticate(unauthorized)

        forbidden = self.finalize(turno, key='forbidden')
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(EfectoFinalizacion.objects.exists())

        unauthorized.user_permissions.add(self.finalize_permission)
        unauthorized = Usuario.objects.get(pk=unauthorized.pk)
        self.client.force_authenticate(unauthorized)
        successful = self.finalize(turno, key='successful')
        count = EfectoFinalizacion.objects.count()
        conflict = self.finalize(turno, key='different')

        self.assertEqual(successful.status_code, status.HTTP_200_OK)
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(EfectoFinalizacion.objects.count(), count)
