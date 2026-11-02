from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from io import StringIO
import threading

from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.models import (
    Auditoria,
    Equipamiento,
    HorarioLaboral,
    Personal,
    RequisitoServicio,
    SlotHold,
    TipoEquipamiento,
    Turno,
)
from gestion.slot_hold_services import (
    SLOT_HOLD_EXPIRED,
    SlotHoldError,
    create_slot_hold,
    release_slot_hold,
)
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin
from gestion.turno_creation_services import (
    TurnoCreationError,
    TurnoCreationService,
)
from gestion.turno_management_services import reprogram_owned_turno
from usuarios.models import Usuario


class SlotHoldConcurrencyTests(SlotHoldFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')

    @staticmethod
    def _run_two(first, second):
        barrier = threading.Barrier(2)

        def wrapped(callable_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return callable_()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(wrapped, first),
                executor.submit(wrapped, second),
            ]
            return [future.result(timeout=20) for future in futures]

    def hold_worker(self, *, request_id, personal_id, user_id, key):
        def operation():
            try:
                result = create_slot_hold(
                    solicitud_id=request_id,
                    personal_id=personal_id,
                    starts_at=self.starts_at,
                    idempotency_key=key,
                    actor=Usuario.objects.get(pk=user_id),
                )
                return ('created', result.hold.pk)
            except SlotHoldError as exc:
                return ('conflict', exc.code)
        return operation

    def second_personal(self, name='Second'):
        personal = Personal.objects.create(
            nombre=name, apellido='Professional', rol='asistente', activo=True
        )
        HorarioLaboral.objects.create(
            personal=personal,
            dia_semana=self.date.weekday(),
            hora_inicio=time(8),
            hora_fin=time(18),
            activo=True,
        )
        return personal

    def test_two_holds_same_personal_slot_have_exactly_one_winner(self):
        other_request = self.create_approved_request(
            self.other_cliente, self.service, self.date
        )
        results = self._run_two(
            self.hold_worker(
                request_id=self.solicitud.pk,
                personal_id=self.personal.pk,
                user_id=self.user.pk,
                key='personal-race-1',
            ),
            self.hold_worker(
                request_id=other_request.pk,
                personal_id=self.personal.pk,
                user_id=self.other_user.pk,
                key='personal-race-2',
            ),
        )
        self.assertEqual(sum(result[0] == 'created' for result in results), 1)
        self.assertEqual(SlotHold.objects.filter(state=SlotHold.State.ACTIVE).count(), 1)

    def test_same_client_different_personal_has_exactly_one_winner(self):
        other_personal = self.second_personal()
        second_request = self.create_approved_request(
            self.cliente, self.service, self.date
        )
        results = self._run_two(
            self.hold_worker(
                request_id=self.solicitud.pk,
                personal_id=self.personal.pk,
                user_id=self.user.pk,
                key='client-race-1',
            ),
            self.hold_worker(
                request_id=second_request.pk,
                personal_id=other_personal.pk,
                user_id=self.user.pk,
                key='client-race-2',
            ),
        )
        self.assertEqual(sum(result[0] == 'created' for result in results), 1)

    def test_last_equipment_capacity_has_exactly_one_winner(self):
        equipment_type = TipoEquipamiento.objects.create(nombre='Mutex equipment')
        RequisitoServicio.objects.create(
            servicio=self.service,
            tipo_equipamiento=equipment_type,
            obligatorio=True,
            cantidad_minima=1,
        )
        Equipamiento.objects.create(
            codigo='MUTEX-1', nombre='Mutex 1', tipo=equipment_type,
            estado=Equipamiento.EstadoRecurso.DISPONIBLE, is_active=True,
        )
        other_personal = self.second_personal('Equipment')
        other_request = self.create_approved_request(
            self.other_cliente, self.service, self.date
        )
        results = self._run_two(
            self.hold_worker(
                request_id=self.solicitud.pk,
                personal_id=self.personal.pk,
                user_id=self.user.pk,
                key='equipment-race-1',
            ),
            self.hold_worker(
                request_id=other_request.pk,
                personal_id=other_personal.pk,
                user_id=self.other_user.pk,
                key='equipment-race-2',
            ),
        )
        self.assertEqual(sum(result[0] == 'created' for result in results), 1)

    def test_turno_vs_hold_has_exactly_one_resource_winner(self):
        def turno_operation():
            try:
                turno = TurnoCreationService.create(
                    cliente_id=self.cliente.pk,
                    servicio_id=self.service.pk,
                    profesional_id=self.personal.pk,
                    fecha=self.date,
                    hora_inicio=time(10),
                    source=Turno.CanalOrigen.WEB,
                )
                return ('created', turno.pk)
            except TurnoCreationError as exc:
                return ('conflict', exc.code)

        results = self._run_two(
            self.hold_worker(
                request_id=self.solicitud.pk,
                personal_id=self.personal.pk,
                user_id=self.user.pk,
                key='turno-hold-race',
            ),
            turno_operation,
        )
        self.assertEqual(sum(result[0] == 'created' for result in results), 1)
        self.assertEqual(
            SlotHold.objects.filter(state=SlotHold.State.ACTIVE).count()
            + Turno.objects.count(),
            1,
        )

    def test_reprogram_turno_vs_hold_has_exactly_one_target_slot_winner(self):
        turno = Turno.objects.create(
            cliente=self.other_cliente,
            profesional=self.personal,
            fecha=self.date,
            hora_inicio=time(9),
            estado=Turno.Estado.SOLICITADO,
        )
        turno.detalles.create(
            servicio=self.service,
            precio_historico='1000.00',
            duracion_minutos=60,
        )

        def reprogram_operation():
            try:
                result = reprogram_owned_turno(
                    actor=Usuario.objects.get(pk=self.other_user.pk),
                    turno_id=turno.pk,
                    fecha=self.date,
                    hora_inicio=time(10),
                    profesional_id=self.personal.pk,
                )
                return ('created', result.turno.pk)
            except TurnoCreationError as exc:
                return ('conflict', exc.code)

        results = self._run_two(
            self.hold_worker(
                request_id=self.solicitud.pk,
                personal_id=self.personal.pk,
                user_id=self.user.pk,
                key='reprogram-hold-race',
            ),
            reprogram_operation,
        )
        self.assertEqual(sum(result[0] == 'created' for result in results), 1)
        turno.refresh_from_db()
        target_turnos = int(turno.hora_inicio == time(10))
        self.assertEqual(
            SlotHold.objects.filter(state=SlotHold.State.ACTIVE).count()
            + target_turnos,
            1,
        )

    def test_create_vs_release_stays_serialized_without_duplicate_active_hold(self):
        existing = self.create_hold(key='release-race-existing')

        def release_operation():
            result = release_slot_hold(
                public_id=existing.public_id,
                actor=Usuario.objects.get(pk=self.user.pk),
            )
            return ('released', result.changed)

        results = self._run_two(
            self.hold_worker(
                request_id=self.solicitud.pk,
                personal_id=self.personal.pk,
                user_id=self.user.pk,
                key='release-race-new',
            ),
            release_operation,
        )
        self.assertIn(results[1][0], {'released', 'conflict'})
        self.assertLessEqual(
            SlotHold.objects.filter(state=SlotHold.State.ACTIVE).count(), 1
        )

    def test_two_expiry_commands_emit_one_transition_and_one_audit(self):
        hold = self.direct_hold(
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
            key='expiry-race',
        )

        def expiry_operation():
            output = StringIO()
            call_command(
                'expirar_slot_holds',
                batch_size=1,
                stdout=output,
            )
            return output.getvalue()

        results = self._run_two(expiry_operation, expiry_operation)
        self.assertEqual(
            sum('expirados=1' in output for output in results),
            1,
        )
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=SLOT_HOLD_EXPIRED,
                registro_id=hold.pk,
            ).count(),
            1,
        )
