from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from threading import Barrier

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    CorreccionFichaTecnica,
    DetalleTurno,
    FichaTecnica,
    Habilidad,
    Personal,
    PersonalHabilidad,
    PerfilTecnicoServicio,
    Servicio,
    Turno,
)
from gestion.technical_record_services import (
    TechnicalRecordConflict,
    save_draft,
)
from usuarios.models import Cliente, Usuario


class TechnicalRecordIncrement2ApiTests(APITestCase):
    def setUp(self):
        self.manage_record = self.permission('manage_technical_record')
        self.manage_formula = self.permission('manage_formulas')
        self.finalize_service = self.permission('finalize_service')
        self.skill = Habilidad.objects.get(code='DIAGNOSTICO')

        self.client_user = self.create_user('increment2-client@test.com')
        self.client_profile = Cliente.objects.create(
            usuario=self.client_user,
            activo=True,
        )
        self.other_client_user = self.create_user('increment2-other-client@test.com')
        self.other_client = Cliente.objects.create(
            usuario=self.other_client_user,
            activo=True,
        )
        self.actor, self.personal = self.create_professional(
            'increment2-professional@test.com',
            formula=True,
            finalizer=True,
        )
        self.other_actor, self.other_personal = self.create_professional(
            'increment2-other-professional@test.com',
            formula=True,
        )
        self.service = self.create_service('Servicio configurable incremento 2')
        self.turno = self.create_turno()
        self.detail = self.create_detail(self.turno, self.service)
        self.list_url = reverse('ficha-tecnica-list')

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    @staticmethod
    def create_user(email, *, active=True, staff=False):
        return Usuario.objects.create_user(
            email=email,
            is_active=active,
            is_staff=staff,
        )

    def create_professional(
        self,
        email,
        *,
        manage=True,
        formula=False,
        finalizer=False,
        personal_active=True,
        skill_active=True,
        account_active=True,
        staff=False,
    ):
        user = self.create_user(email, active=account_active, staff=staff)
        permissions = []
        if manage:
            permissions.append(self.manage_record)
        if formula:
            permissions.append(self.manage_formula)
        if finalizer:
            permissions.append(self.finalize_service)
        user.user_permissions.add(*permissions)
        personal = Personal.objects.create(
            usuario=user,
            nombre='Profesional',
            apellido=email.split('@')[0],
            rol='colorista',
            activo=personal_active,
        )
        PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=self.skill,
            activa=skill_active,
        )
        return user, personal

    @staticmethod
    def create_service(name, *, standard='FÓRMULA ESTÁNDAR CATÁLOGO'):
        return Servicio.objects.create(
            nombre=name,
            precio_base='100.00',
            duracion_estimada=60,
            plantilla_formula=standard,
        )

    def configure(
        self,
        service=None,
        *,
        requirement=PerfilTecnicoServicio.RequisitoFicha.REQUERIDA,
        formula=PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA,
        fields=None,
        active=True,
    ):
        profile, _ = PerfilTecnicoServicio.objects.update_or_create(
            servicio=service or self.service,
            defaults={
                'requisito_ficha': requirement,
                'modo_formula_ficha': formula,
                'campos_requeridos_ficha': (
                    ['observaciones_proceso'] if fields is None else fields
                ),
                'activa': active,
            },
        )
        return profile

    def create_turno(
        self,
        *,
        client=None,
        personal=None,
        state=Turno.Estado.CONFIRMADO,
        minute=0,
    ):
        return Turno.objects.create(
            cliente=client or self.client_profile,
            profesional=personal or self.personal,
            fecha=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(10, minute),
            estado=state,
        )

    @staticmethod
    def create_detail(turno, service):
        return DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico='100.00',
            duracion_minutos=60,
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user or self.actor)

    def create_draft(self, detail=None, **fields):
        self.authenticate()
        payload = {'detalle_turno': (detail or self.detail).pk, **fields}
        return self.client.post(self.list_url, payload, format='json')

    @staticmethod
    def action_url(action, record):
        return reverse(f'ficha-tecnica-{action}', args=[record.pk])

    def complete(self, record, **fields):
        return self.client.post(
            self.action_url('completar', record),
            {'version': record.version, **fields},
            format='json',
        )

    def test_one_record_per_detail_and_multiservice_turno(self):
        self.configure()
        other_service = self.create_service('Segundo servicio incremento 2')
        self.configure(other_service)
        other_detail = self.create_detail(self.turno, other_service)

        first = self.create_draft(observaciones_proceso='Primer proceso')
        duplicate = self.create_draft(observaciones_proceso='Duplicado')
        second = self.create_draft(
            other_detail,
            observaciones_proceso='Segundo proceso',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FichaTecnica.objects.count(), 2)

    def test_create_draft_sets_server_author_state_version_and_snapshot(self):
        self.configure(
            formula=PerfilTecnicoServicio.ModoFormulaFicha.OPCIONAL,
        )

        response = self.create_draft(observaciones_proceso='Proceso parcial')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = FichaTecnica.objects.get()
        self.assertEqual(record.profesional_autor, self.actor)
        self.assertEqual(record.estado, FichaTecnica.Estado.BORRADOR)
        self.assertEqual(record.version, 1)
        self.assertEqual(
            record.formula_estandar_referencia,
            'FÓRMULA ESTÁNDAR CATÁLOGO',
        )
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)

    def test_pending_policy_allows_draft_but_never_fictitious_completion(self):
        response = self.create_draft(observaciones_proceso='Dato verificable')
        record = FichaTecnica.objects.get()

        completed = self.complete(record)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(completed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(completed.data['code'], 'TECHNICAL_RECORD_INCOMPLETE')
        record.refresh_from_db()
        self.assertEqual(record.estado, FichaTecnica.Estado.BORRADOR)

    def test_complete_validates_only_explicit_conditional_fields(self):
        self.configure(fields=['resultado_post_servicio', 'foto_resultado'])
        created = self.create_draft(resultado_post_servicio='Resultado observado')
        record = FichaTecnica.objects.get()

        missing_photo = self.complete(record)

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(missing_photo.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing_photo.data['field'], 'MISSING_FOTO_RESULTADO')

    def test_non_formula_service_completes_without_chemical_fields(self):
        self.configure(
            formula=PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA,
            fields=['observaciones_proceso'],
        )
        self.create_draft(observaciones_proceso='Corte controlado')
        record = FichaTecnica.objects.get()

        response = self.complete(record)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.estado, FichaTecnica.Estado.COMPLETA)
        self.assertIsNone(record.formula)
        self.assertEqual(record.completada_por, self.actor)
        self.assertEqual(record.version, 2)

    def test_standard_formula_is_separate_from_applied_formula(self):
        self.configure(
            formula=PerfilTecnicoServicio.ModoFormulaFicha.REQUERIDA,
            fields=[],
        )
        response = self.create_draft(formula='FÓRMULA REALMENTE APLICADA')
        record = FichaTecnica.objects.get()

        completed = self.complete(record)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        self.assertEqual(record.formula, 'FÓRMULA REALMENTE APLICADA')
        self.assertEqual(
            record.formula_estandar_referencia,
            'FÓRMULA ESTÁNDAR CATÁLOGO',
        )

    def test_formula_requires_additional_effective_capability(self):
        actor, personal = self.create_professional(
            'increment2-record-only@test.com',
            formula=False,
        )
        self.turno.profesional = personal
        self.turno.save(update_fields=['profesional'])
        self.configure(
            formula=PerfilTecnicoServicio.ModoFormulaFicha.OPCIONAL,
        )
        self.authenticate(actor)

        response = self.client.post(
            self.list_url,
            {
                'detalle_turno': self.detail.pk,
                'formula': 'No autorizada',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(FichaTecnica.objects.exists())

    def test_assigned_professional_required_without_staff_or_role_bypass(self):
        self.configure()
        self.authenticate(self.other_actor)
        foreign = self.client.post(
            self.list_url,
            {
                'detalle_turno': self.detail.pk,
                'observaciones_proceso': 'Ajenas',
            },
            format='json',
        )
        staff_actor, _ = self.create_professional(
            'increment2-staff@test.com',
            manage=False,
            formula=False,
            staff=True,
        )
        self.authenticate(staff_actor)
        staff = self.client.post(
            self.list_url,
            {
                'detalle_turno': self.detail.pk,
                'observaciones_proceso': 'Staff',
            },
            format='json',
        )

        self.assertEqual(foreign.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(staff.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(FichaTecnica.objects.exists())

    def test_inactive_account_personal_or_skill_are_rejected(self):
        self.configure()
        actors = []
        for suffix, flags in (
            ('account', {'account_active': False}),
            ('personal', {'personal_active': False}),
            ('skill', {'skill_active': False}),
        ):
            actor, _ = self.create_professional(
                f'increment2-inactive-{suffix}@test.com',
                **flags,
            )
            actors.append(actor)
        for actor in actors:
            self.authenticate(actor)
            with self.subTest(actor=actor.email):
                response = self.client.post(
                    self.list_url,
                    {
                        'detalle_turno': self.detail.pk,
                        'observaciones_proceso': 'No autorizado',
                    },
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owned_client_context_omits_sensitive_formulas(self):
        self.configure(
            formula=PerfilTecnicoServicio.ModoFormulaFicha.OPCIONAL,
        )
        created = self.create_draft(
            formula='FÓRMULA SENSIBLE',
            observaciones_proceso='Proceso visible',
        )
        self.authenticate(self.client_user)

        detail = self.client.get(
            reverse('ficha-tecnica-detail', args=[created.data['id']])
        )
        context = self.client.get(
            reverse('ficha-tecnica-contexto-turno'),
            {'turno_id': self.turno.pk},
        )
        foreign_context = self.client.get(
            reverse('ficha-tecnica-contexto-turno'),
            {'turno_id': self.create_turno(client=self.other_client, minute=1).pk},
        )

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertNotIn('formula', detail.data)
        self.assertNotIn('formula_base_servicio', detail.data)
        self.assertEqual(context.status_code, status.HTTP_200_OK)
        self.assertNotIn('formula', context.data['detalles'][0]['ficha'])
        self.assertNotIn('formula_estandar_catalogo', context.data['detalles'][0])
        self.assertEqual(foreign_context.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_and_generic_updates_are_rejected(self):
        self.configure()
        created = self.create_draft(observaciones_proceso='Preservar')
        detail_url = reverse('ficha-tecnica-detail', args=[created.data['id']])

        patched = self.client.patch(
            detail_url,
            {'observaciones_proceso': 'Silenciosa'},
            format='json',
        )
        deleted = self.client.delete(detail_url)

        self.assertEqual(patched.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(deleted.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(FichaTecnica.objects.filter(pk=created.data['id']).exists())

    def test_authorized_correction_preserves_author_before_after_and_history(self):
        self.configure()
        self.create_draft(observaciones_proceso='Proceso original')
        record = FichaTecnica.objects.get()
        completed = self.complete(record)
        record.refresh_from_db()
        history_before = record.history.count()

        corrected = self.client.post(
            self.action_url('corregir', record),
            {
                'version': record.version,
                'motivo': 'Corrección técnica documentada',
                'observaciones_proceso': 'Proceso corregido',
            },
            format='json',
        )

        self.assertEqual(completed.status_code, status.HTTP_200_OK)
        self.assertEqual(corrected.status_code, status.HTTP_200_OK)
        record.refresh_from_db()
        correction = CorreccionFichaTecnica.objects.get(ficha=record)
        self.assertEqual(record.profesional_autor, self.actor)
        self.assertEqual(correction.actor, self.actor)
        self.assertEqual(correction.version_anterior, 2)
        self.assertEqual(correction.version_nueva, 3)
        self.assertEqual(
            correction.valores_anteriores['observaciones_proceso'],
            'Proceso original',
        )
        self.assertEqual(
            correction.valores_nuevos['observaciones_proceso'],
            'Proceso corregido',
        )
        self.assertEqual(record.history.count(), history_before + 1)

    def test_correction_requires_reason_and_complete_record(self):
        self.configure()
        self.create_draft(observaciones_proceso='Proceso original')
        record = FichaTecnica.objects.get()

        draft_correction = self.client.post(
            self.action_url('corregir', record),
            {
                'version': record.version,
                'motivo': 'Motivo técnicamente suficiente',
                'observaciones_proceso': 'Cambio',
            },
            format='json',
        )
        self.complete(record)
        record.refresh_from_db()
        missing_reason = self.client.post(
            self.action_url('corregir', record),
            {
                'version': record.version,
                'motivo': 'corto',
                'observaciones_proceso': 'Cambio',
            },
            format='json',
        )

        self.assertEqual(draft_correction.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CorreccionFichaTecnica.objects.exists())

    def test_stale_version_returns_409_without_lost_update(self):
        self.configure()
        self.create_draft(observaciones_proceso='Versión uno')
        record = FichaTecnica.objects.get()
        url = self.action_url('guardar-borrador', record)

        first = self.client.post(
            url,
            {'version': 1, 'observaciones_proceso': 'Versión dos'},
            format='json',
        )
        stale = self.client.post(
            url,
            {'version': 1, 'observaciones_proceso': 'Sobrescritura perdida'},
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(stale.data['code'], 'TECHNICAL_RECORD_VERSION_CONFLICT')
        record.refresh_from_db()
        self.assertEqual(record.observaciones_proceso, 'Versión dos')
        self.assertEqual(record.version, 2)

    def test_realized_turno_correction_is_safely_denied_without_24h_rule(self):
        self.configure()
        self.create_draft(observaciones_proceso='Proceso completo')
        record = FichaTecnica.objects.get()
        self.complete(record)
        record.refresh_from_db()
        self.turno.estado = Turno.Estado.REALIZADO
        self.turno.save(update_fields=['estado'])

        response = self.client.post(
            self.action_url('corregir', record),
            {
                'version': record.version,
                'motivo': 'Intento después de finalización',
                'observaciones_proceso': 'No debe persistir',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data['code'],
            'FINALIZED_RECORD_CORRECTION_POLICY_PENDING',
        )

    def test_finalization_allows_not_required_and_pending_policies(self):
        self.configure(
            requirement=PerfilTecnicoServicio.RequisitoFicha.NO_REQUERIDA,
            formula=PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA,
            fields=[],
        )
        pending_service = self.create_service('Política pendiente incremento 2')
        self.create_detail(self.turno, pending_service)
        self.authenticate()

        response = self.client.post(
            reverse('turno-finalizar-turno', args=[self.turno.pk]),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='increment2-not-required',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        statuses = response.data['effects']['technical_records']
        self.assertEqual(len(statuses), 2)
        self.assertEqual(statuses[0]['policy_status'], 'DEFINIDA')
        self.assertEqual(statuses[1]['policy_status'], 'PENDIENTE')

    def test_finalization_rejects_explicit_required_incomplete_record_atomically(self):
        self.configure()
        self.authenticate()

        response = self.client.post(
            reverse('turno-finalizar-turno', args=[self.turno.pk]),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='increment2-required-missing',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'REQUIRED_TECHNICAL_RECORD_INCOMPLETE')
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado, Turno.Estado.CONFIRMADO)
        self.assertFalse(hasattr(self.turno, 'finalizacion'))

    def test_finalization_accepts_explicit_complete_record_and_is_idempotent(self):
        self.configure()
        self.create_draft(observaciones_proceso='Proceso final')
        record = FichaTecnica.objects.get()
        self.complete(record)
        key = 'increment2-required-complete'

        first = self.client.post(
            reverse('turno-finalizar-turno', args=[self.turno.pk]),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )
        second = self.client.post(
            reverse('turno-finalizar-turno', args=[self.turno.pk]),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data['changed'])
        self.assertFalse(second.data['changed'])
        self.assertTrue(first.data['effects']['technical_records'][0]['complete'])

    def test_record_does_not_create_diagnosis_or_mutate_client_profile(self):
        self.configure()
        profile_before = {
            'tipo_cabello_id': self.client_profile.tipo_cabello_id,
            'porosidad_cabello_id': self.client_profile.porosidad_cabello_id,
            'estado_general_id': self.client_profile.estado_general_id,
        }

        self.create_draft(observaciones_proceso='Registro aislado')

        self.client_profile.refresh_from_db()
        self.assertEqual(
            {
                'tipo_cabello_id': self.client_profile.tipo_cabello_id,
                'porosidad_cabello_id': self.client_profile.porosidad_cabello_id,
                'estado_general_id': self.client_profile.estado_general_id,
            },
            profile_before,
        )
        self.assertEqual(self.client_profile.diagnosticos_capilares.count(), 0)


class TechnicalRecordConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        manage = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_technical_record',
        )
        skill = Habilidad.objects.get(code='DIAGNOSTICO')
        client_user = Usuario.objects.create_user(email='increment2-race-client@test.com')
        client = Cliente.objects.create(usuario=client_user, activo=True)
        self.actor = Usuario.objects.create_user(email='increment2-race-actor@test.com')
        self.actor.user_permissions.add(manage)
        personal = Personal.objects.create(
            usuario=self.actor,
            nombre='Race',
            apellido='Writer',
            rol='colorista',
            activo=True,
        )
        PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=skill,
            activa=True,
        )
        service = Servicio.objects.create(
            nombre='Servicio carrera incremento 2',
            precio_base='100.00',
            duracion_estimada=60,
        )
        PerfilTecnicoServicio.objects.update_or_create(
            servicio=service,
            defaults={
                'requisito_ficha': PerfilTecnicoServicio.RequisitoFicha.REQUERIDA,
                'modo_formula_ficha': PerfilTecnicoServicio.ModoFormulaFicha.NO_APLICA,
                'campos_requeridos_ficha': ['observaciones_proceso'],
            },
        )
        turno = Turno.objects.create(
            cliente=client,
            profesional=personal,
            fecha=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(12, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        detail = DetalleTurno.objects.create(
            turno=turno,
            servicio=service,
            precio_historico='100.00',
            duracion_minutos=60,
        )
        self.record = FichaTecnica.objects.create(
            detalle_turno=detail,
            profesional_autor=self.actor,
            observaciones_proceso='Versión inicial',
        )

    def test_postgresql_concurrent_writers_detect_stale_version(self):
        if connection.vendor != 'postgresql':
            self.skipTest('La prueba exige locks reales de PostgreSQL.')
        barrier = Barrier(2)

        def worker(value):
            close_old_connections()
            try:
                actor = Usuario.objects.get(pk=self.actor.pk)
                barrier.wait(timeout=10)
                save_draft(
                    actor=actor,
                    record_id=self.record.pk,
                    expected_version=1,
                    values={'observaciones_proceso': value},
                )
                return 'saved'
            except TechnicalRecordConflict as exc:
                return exc.code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, ('Escritor A', 'Escritor B')))

        self.assertCountEqual(
            results,
            ['saved', 'TECHNICAL_RECORD_VERSION_CONFLICT'],
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.version, 2)
        self.assertIn(self.record.observaciones_proceso, {'Escritor A', 'Escritor B'})
