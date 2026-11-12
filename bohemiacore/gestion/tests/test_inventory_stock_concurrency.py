from concurrent.futures import ThreadPoolExecutor
import threading

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gestion.inventory_services import (
    StockConflict,
    adjust_stock,
    apply_stock_deltas,
    correct_stock_movement,
    receive_stock,
)
from gestion.models import CategoriaProducto, MovimientoStock, Producto
from usuarios.models import Usuario


class InventoryStockConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        category = CategoriaProducto.objects.create(nombre='Concurrencia stock')
        self.product = Producto.objects.create(
            sku='CONCURRENT-1',
            nombre='Producto concurrente',
            categoria=category,
            precio='100.00',
        )
        self.other_product = Producto.objects.create(
            sku='CONCURRENT-2',
            nombre='Otro producto concurrente',
            categoria=category,
            precio='200.00',
        )
        self.actor = Usuario.objects.create_user(
            email='concurrent-stock@test.com',
        )
        self.actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_stock',
        ))

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
            futures = (
                executor.submit(wrapped, first),
                executor.submit(wrapped, second),
            )
            return [future.result(timeout=timeout) for future in futures]

    def _actor(self):
        return Usuario.objects.get(pk=self.actor.pk)

    def _adjust_worker(self, *, product_id, delta, key):
        def operation():
            try:
                movement = adjust_stock(
                    product_id=product_id,
                    delta=delta,
                    reason_code='CONCURRENT_ADJUSTMENT',
                    actor=self._actor(),
                    idempotency_key=key,
                )
                return 'ok', movement.pk
            except StockConflict as exc:
                return exc.code, None
        return operation

    def _receive_worker(self, *, product_id, quantity, key):
        def operation():
            movement = receive_stock(
                product_id=product_id,
                quantity=quantity,
                reason_code='CONCURRENT_RECEIPT',
                actor=self._actor(),
                idempotency_key=key,
            )
            return 'ok', movement.pk
        return operation

    def _opening(self, quantity, key):
        return receive_stock(
            product_id=self.product.pk,
            quantity=quantity,
            reason_code='TEST_OPENING',
            actor=self.actor,
            idempotency_key=key,
        )

    def test_two_outputs_over_one_unit_only_one_wins(self):
        self._opening(1, 'race-a-opening')
        results = self._run_two(
            self._adjust_worker(
                product_id=self.product.pk,
                delta=-1,
                key='race-a-out-1',
            ),
            self._adjust_worker(
                product_id=self.product.pk,
                delta=-1,
                key='race-a-out-2',
            ),
        )
        self.product.refresh_from_db()
        self.assertEqual(sum(result[0] == 'ok' for result in results), 1)
        self.assertEqual(
            sum(result[0] == 'INSUFFICIENT_REAL_STOCK' for result in results),
            1,
        )
        self.assertEqual(self.product.stock_real, 0)
        self.assertEqual(MovimientoStock.objects.count(), 2)

    def test_receipt_and_output_are_serialized_and_traceable(self):
        self._opening(1, 'race-b-opening')
        results = self._run_two(
            self._receive_worker(
                product_id=self.product.pk,
                quantity=2,
                key='race-b-in',
            ),
            self._adjust_worker(
                product_id=self.product.pk,
                delta=-1,
                key='race-b-out',
            ),
        )
        self.product.refresh_from_db()
        self.assertTrue(all(result[0] == 'ok' for result in results))
        self.assertEqual(self.product.stock_real, 2)
        movements = list(
            MovimientoStock.objects.filter(producto=self.product).order_by('pk')
        )
        for previous, current in zip(movements, movements[1:]):
            self.assertEqual(previous.stock_after, current.stock_before)

    def test_two_adjustments_have_no_lost_update(self):
        results = self._run_two(
            self._adjust_worker(
                product_id=self.product.pk,
                delta=2,
                key='race-c-adjust-1',
            ),
            self._adjust_worker(
                product_id=self.product.pk,
                delta=3,
                key='race-c-adjust-2',
            ),
        )
        self.product.refresh_from_db()
        self.assertTrue(all(result[0] == 'ok' for result in results))
        self.assertEqual(self.product.stock_real, 5)
        self.assertEqual(
            MovimientoStock.objects.filter(producto=self.product).count(),
            2,
        )

    def test_same_idempotency_key_creates_one_movement(self):
        results = self._run_two(
            self._adjust_worker(
                product_id=self.product.pk,
                delta=1,
                key='race-d-same-key',
            ),
            self._adjust_worker(
                product_id=self.product.pk,
                delta=1,
                key='race-d-same-key',
            ),
        )
        self.product.refresh_from_db()
        self.assertTrue(all(result[0] == 'ok' for result in results))
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(self.product.stock_real, 1)
        self.assertEqual(MovimientoStock.objects.count(), 1)

    def test_correction_and_adjustment_serialize_consistently(self):
        original = self._opening(5, 'race-e-opening')

        def correct():
            movement = correct_stock_movement(
                movement_id=original.pk,
                reason_code='CONCURRENT_CORRECTION',
                actor=self._actor(),
                idempotency_key='race-e-correction',
            )
            return 'ok', movement.pk

        results = self._run_two(
            correct,
            self._adjust_worker(
                product_id=self.product.pk,
                delta=1,
                key='race-e-adjustment',
            ),
        )
        self.product.refresh_from_db()
        self.assertTrue(all(result[0] == 'ok' for result in results))
        self.assertEqual(self.product.stock_real, 1)
        self.assertEqual(
            MovimientoStock.objects.filter(
                reverses_movement=original
            ).count(),
            1,
        )

    def test_multiple_products_use_canonical_lock_order_without_deadlock(self):
        def batch(first_id, second_id, suffix):
            def operation():
                movements = apply_stock_deltas([
                    {
                        'product_id': first_id,
                        'delta': 1,
                        'movement_type': MovimientoStock.Type.MANUAL_ADJUSTMENT,
                        'reason_code': 'MULTI_PRODUCT_TEST',
                        'actor': self._actor(),
                        'reference': None,
                        'idempotency_key': f'race-f-{suffix}-first',
                    },
                    {
                        'product_id': second_id,
                        'delta': 1,
                        'movement_type': MovimientoStock.Type.MANUAL_ADJUSTMENT,
                        'reason_code': 'MULTI_PRODUCT_TEST',
                        'actor': self._actor(),
                        'reference': None,
                        'idempotency_key': f'race-f-{suffix}-second',
                    },
                ])
                return 'ok', [movement.pk for movement in movements]
            return operation

        results = self._run_two(
            batch(self.product.pk, self.other_product.pk, 'forward'),
            batch(self.other_product.pk, self.product.pk, 'reverse'),
        )
        self.product.refresh_from_db()
        self.other_product.refresh_from_db()
        self.assertTrue(all(result[0] == 'ok' for result in results))
        self.assertEqual(self.product.stock_real, 2)
        self.assertEqual(self.other_product.stock_real, 2)
        self.assertEqual(MovimientoStock.objects.count(), 4)
