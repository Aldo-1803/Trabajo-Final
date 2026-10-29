from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
import threading
import time as time_module

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.models import (
    Auditoria,
    Personal,
    SlotHold,
    SlotHoldService,
    SolicitudTecnicaReserva,
    Turno,
)
from gestion.slot_hold_consumption_services import (
    SLOT_HOLD_CONSUMED,
    SlotHoldConsumptionError,
    create_confirmed_turno_from_locked_hold,
)
from gestion.slot_hold_services import (
    SLOT_HOLD_EXPIRED,
    SLOT_HOLD_RELEASED,
    SlotHoldError,
    expire_slot_hold,
    release_slot_hold,
)
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin
from gestion.turno_creation_services import (
    TurnoCreationError,
    TurnoCreationService,
)
from usuarios.models import Usuario


class SlotHoldConsumptionConcurrencyTests(
    SlotHoldFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')

    @staticmethod
    def _run_two(first, second, timeout=20):
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
            return [future.result(timeout=timeout) for future in futures]

    def consume_worker(self, *, hold_id, key, user_id):
        def operation():
            try:
                result = create_confirmed_turno_from_locked_hold(
                    hold=SlotHold.objects.get(pk=hold_id),
                    operation_key=key,
                    actor=Usuario.objects.get(pk=user_id),
                )
                return (
                    'turno' if result.succeeded else 'rejected',
                    result.created,
                    result.code,
                    result.turno.pk if result.turno else None,
                )
            except SlotHoldConsumptionError as exc:
                return ('conflict', False, exc.code, None)
        return operation

    def test_two_consumers_same_hold_create_exactly_one_turno(self):
        hold = self.create_hold()
        worker = self.consume_worker(
            hold_id=hold.pk,
            key='concurrent-same-operation',
            user_id=self.user.pk,
        )
        results = self._run_two(worker, worker)

        self.assertEqual(sum(result[0] == 'turno' for result in results), 2)
        self.assertEqual(sum(result[1] for result in results), 1)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(Turno.objects.get().detalles.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=SLOT_HOLD_CONSUMED).count(),
            1,
        )

    def test_consumption_vs_expiration_has_one_terminal_transition(self):
        hold = self.create_hold(key='consume-expire-race')
        deadline = timezone.now() + timedelta(milliseconds=300)
        SlotHold.objects.filter(pk=hold.pk).update(expires_at=deadline)
        time_module.sleep(0.35)

        def expire_operation():
            try:
                result = expire_slot_hold(hold_id=hold.pk)
                return ('expired', result.changed)
            except SlotHoldError as exc:
                return ('conflict', exc.code)

        results = self._run_two(
            self.consume_worker(
                hold_id=hold.pk,
                key='consume-expire-operation',
                user_id=self.user.pk,
            ),
            expire_operation,
        )
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=SLOT_HOLD_EXPIRED,
                registro_id=hold.pk,
            ).count(),
            1,
        )
        self.assertEqual(len(results), 2)

    def test_consumption_vs_release_leaves_consistent_terminal_state(self):
        hold = self.create_hold(key='consume-release-race')

        def release_operation():
            try:
                result = release_slot_hold(
                    public_id=hold.public_id,
                    actor=Usuario.objects.get(pk=self.user.pk),
                )
                return ('released', result.changed)
            except SlotHoldError as exc:
                return ('conflict', exc.code)

        self._run_two(
            self.consume_worker(
                hold_id=hold.pk,
                key='consume-release-operation',
                user_id=self.user.pk,
            ),
            release_operation,
        )
        hold.refresh_from_db()
        self.assertIn(
            hold.state,
            {SlotHold.State.CONSUMED, SlotHold.State.RELEASED},
        )
        if hold.state == SlotHold.State.CONSUMED:
            self.assertEqual(Turno.objects.count(), 1)
            self.assertEqual(hold.consumed_turno_id, Turno.objects.get().pk)
            self.assertEqual(
                Auditoria.objects.filter(tabla=SLOT_HOLD_CONSUMED).count(),
                1,
            )
        else:
            self.assertFalse(Turno.objects.exists())
            self.assertEqual(
                Auditoria.objects.filter(tabla=SLOT_HOLD_RELEASED).count(),
                1,
            )

    def test_consumption_vs_conflicting_turno_occupies_resource_once(self):
        hold = self.create_hold(key='consume-turno-race')

        def turno_operation():
            try:
                turno = TurnoCreationService.create(
                    cliente_id=self.other_cliente.pk,
                    servicio_id=self.service.pk,
                    profesional_id=self.personal.pk,
                    fecha=self.date,
                    hora_inicio=time(10),
                    source=Turno.CanalOrigen.WEB,
                )
                return ('turno', turno.pk)
            except TurnoCreationError as exc:
                return ('conflict', exc.code)

        self._run_two(
            self.consume_worker(
                hold_id=hold.pk,
                key='consume-turno-operation',
                user_id=self.user.pk,
            ),
            turno_operation,
        )
        self.assertEqual(Turno.objects.count(), 1)
        turno = Turno.objects.get()
        hold.refresh_from_db()
        if hold.state == SlotHold.State.CONSUMED:
            self.assertEqual(hold.consumed_turno_id, turno.pk)
        else:
            self.assertEqual(hold.state, SlotHold.State.RELEASED)

    def test_waiting_for_resource_lock_crosses_expiry_without_turno(self):
        hold = self.create_hold(key='cross-expiry-lock')
        deadline = timezone.now() + timedelta(seconds=2)
        SlotHold.objects.filter(pk=hold.pk).update(expires_at=deadline)

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            with transaction.atomic():
                Personal.objects.select_for_update().get(pk=self.personal.pk)

                def consume_with_connection():
                    close_old_connections()
                    try:
                        return self.consume_worker(
                            hold_id=hold.pk,
                            key='cross-expiry-operation',
                            user_id=self.user.pk,
                        )()
                    finally:
                        close_old_connections()

                future = executor.submit(
                    consume_with_connection
                )
                time_module.sleep(2.3)
            result = future.result(timeout=10)
        finally:
            executor.shutdown(wait=True)

        self.assertEqual(result[0], 'rejected')
        self.assertEqual(result[2], 'HOLD_EXPIRED')
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(Turno.objects.exists())

    def test_request_invalidation_vs_consumption_has_linearizable_result(self):
        hold = self.create_hold(key='invalidate-consume-race')

        def invalidate_operation():
            with transaction.atomic():
                request = SolicitudTecnicaReserva.objects.select_for_update().get(
                    pk=self.solicitud.pk
                )
                request.estado = SolicitudTecnicaReserva.Estado.VENCIDA
                request.save(update_fields=['estado'])
            return 'invalidated'

        self._run_two(
            self.consume_worker(
                hold_id=hold.pk,
                key='invalidate-consume-operation',
                user_id=self.user.pk,
            ),
            invalidate_operation,
        )
        hold.refresh_from_db()
        self.solicitud.refresh_from_db()
        self.assertEqual(
            self.solicitud.estado,
            SolicitudTecnicaReserva.Estado.VENCIDA,
        )
        self.assertIn(
            hold.state,
            {SlotHold.State.CONSUMED, SlotHold.State.RELEASED},
        )
        if hold.state == SlotHold.State.CONSUMED:
            self.assertEqual(Turno.objects.count(), 1)
            self.assertEqual(hold.consumed_turno_id, Turno.objects.get().pk)
        else:
            self.assertFalse(Turno.objects.exists())
            self.assertEqual(
                hold.release_reason,
                SlotHold.ReleaseReason.TECHNICAL_REQUEST_INVALIDATED,
            )

    def test_two_holds_same_resource_consume_without_deadlock(self):
        first = self.create_hold(key='lock-order-first')
        second_request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        second = self.direct_hold(
            solicitud=second_request,
            key='lock-order-second',
        )
        SlotHoldService.objects.create(
            hold=second,
            servicio=self.service,
            orden=0,
            nombre_snapshot=self.service.nombre,
            duracion_minutos_snapshot=60,
        )

        results = self._run_two(
            self.consume_worker(
                hold_id=first.pk,
                key='lock-order-consume-first',
                user_id=self.user.pk,
            ),
            self.consume_worker(
                hold_id=second.pk,
                key='lock-order-consume-second',
                user_id=self.other_user.pk,
            ),
        )
        self.assertEqual(sum(result[0] == 'turno' for result in results), 1)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(
            SlotHold.objects.filter(state=SlotHold.State.CONSUMED).count(),
            1,
        )
        self.assertEqual(
            SlotHold.objects.filter(state=SlotHold.State.RELEASED).count(),
            1,
        )
