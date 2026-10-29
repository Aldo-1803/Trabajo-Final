from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gestion.inventory_services import receive_stock
from gestion.models import (
    CategoriaProducto,
    CompromisoStock,
    MovimientoStock,
    OrdenCompra,
    OrdenItem,
    OrdenPendiente,
    Producto,
)
from gestion.order_inventory_services import (
    OrderInventoryError,
    apply_order_inventory_effect,
    apply_pending_order_inventory_effect,
    create_order_stock_commitments,
    release_order_stock_commitments,
    release_pending_order_stock_commitments,
)
from usuarios.models import Cliente, Usuario


class OrderInventoryConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.user = Usuario.objects.create_user(email='d2-race-client@test.com')
        self.client_profile = Cliente.objects.create(usuario=self.user)
        self.actor = Usuario.objects.create_user(email='d2-race-stock@test.com')
        self.actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_stock',
        ))
        category = CategoriaProducto.objects.create(nombre='Concurrencia D2')
        self.first_product = Producto.objects.create(
            sku='D2-RACE-1',
            nombre='Primero D2',
            categoria=category,
            precio=Decimal('10.00'),
        )
        self.second_product = Producto.objects.create(
            sku='D2-RACE-2',
            nombre='Segundo D2',
            categoria=category,
            precio=Decimal('20.00'),
        )

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

    def receive(self, product, quantity, suffix):
        receive_stock(
            product_id=product.pk,
            quantity=quantity,
            reason_code='D2_CONCURRENCY_OPENING',
            actor=self.actor,
            idempotency_key=f'd2-race-opening-{suffix}',
        )

    def make_order(self, lines, suffix, *, state='PENDIENTE'):
        order = OrdenCompra.objects.create(
            codigo=f'D2-RACE-{suffix}',
            cliente=self.client_profile,
            estado=state,
            total=sum(product.precio * quantity for product, quantity in lines),
        )
        for product, quantity in lines:
            OrdenItem.objects.create(
                orden=order,
                producto=product,
                cantidad=quantity,
                precio_historico=product.precio,
            )
        return order

    @staticmethod
    def operation(callable_):
        def run():
            try:
                result = callable_()
                return 'ok', result
            except OrderInventoryError as exc:
                return exc.code, None
        return run

    def test_two_orders_compete_for_last_unit_only_one_commits(self):
        self.receive(self.first_product, 1, 'last-unit')
        first = self.make_order([(self.first_product, 1)], 'LAST-A')
        second = self.make_order([(self.first_product, 1)], 'LAST-B')
        results = self._run_two(
            self.operation(lambda: create_order_stock_commitments(first.pk)[0].pk),
            self.operation(lambda: create_order_stock_commitments(second.pk)[0].pk),
        )
        self.first_product.refresh_from_db()
        self.assertEqual(sum(code == 'ok' for code, _ in results), 1)
        self.assertEqual(
            sum(code == 'INSUFFICIENT_AVAILABLE_STOCK' for code, _ in results),
            1,
        )
        self.assertEqual(self.first_product.stock_comprometido, 1)
        self.assertEqual(
            CompromisoStock.objects.filter(
                estado=CompromisoStock.State.ACTIVE
            ).count(),
            1,
        )

    def test_two_confirmations_same_order_create_one_movement(self):
        self.receive(self.first_product, 1, 'double-confirm')
        order = self.make_order(
            [(self.first_product, 1)],
            'DOUBLE',
            state='PAGADO',
        )
        create_order_stock_commitments(order.pk)
        results = self._run_two(
            self.operation(
                lambda: apply_order_inventory_effect(
                    order.pk,
                    actor=self.actor,
                ).movements[0].pk
            ),
            self.operation(
                lambda: apply_order_inventory_effect(
                    order.pk,
                    actor=self.actor,
                ).movements[0].pk
            ),
        )
        self.assertTrue(all(code == 'ok' for code, _ in results))
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).count(),
            1,
        )

    def test_confirm_vs_cancel_pending_contract_has_one_terminal_winner(self):
        self.receive(self.first_product, 1, 'pending-race')
        order = self.make_order(
            [(self.first_product, 1)],
            'PENDING',
            state='PAGADO',
        )
        create_order_stock_commitments(order.pk)
        pending = OrdenPendiente.objects.create(
            cliente=self.client_profile,
            orden_compra=order,
            estado='PENDIENTE',
            items_json=[{
                'producto_id': self.first_product.pk,
                'cantidad': 1,
                'precio': '10.00',
            }],
            monto_total=Decimal('10.00'),
        )
        results = self._run_two(
            self.operation(
                lambda: apply_pending_order_inventory_effect(
                    pending.pk,
                    actor=self.actor,
                )[0].estado
            ),
            self.operation(
                lambda: release_pending_order_stock_commitments(pending.pk).estado
            ),
        )
        pending.refresh_from_db()
        order.refresh_from_db()
        self.first_product.refresh_from_db()
        self.assertEqual(sum(code == 'ok' for code, _ in results), 1)
        self.assertIn(pending.estado, {'COMPLETADA', 'CANCELADA'})
        if pending.estado == 'COMPLETADA':
            self.assertEqual(order.estado, 'COMPLETADO')
            self.assertEqual(self.first_product.stock_real, 0)
        else:
            self.assertEqual(order.estado, 'CANCELADO')
            self.assertEqual(self.first_product.stock_real, 1)
        self.assertEqual(self.first_product.stock_comprometido, 0)

    def test_release_vs_consume_only_one_transition_wins(self):
        self.receive(self.first_product, 1, 'release-consume')
        order = self.make_order(
            [(self.first_product, 1)],
            'REL-CONS',
            state='PAGADO',
        )
        create_order_stock_commitments(order.pk)
        results = self._run_two(
            self.operation(
                lambda: apply_order_inventory_effect(
                    order.pk,
                    actor=self.actor,
                ).order.estado
            ),
            self.operation(
                lambda: release_order_stock_commitments(order.pk)[0].estado
            ),
        )
        commitment = CompromisoStock.objects.get(orden=order)
        self.first_product.refresh_from_db()
        self.assertEqual(sum(code == 'ok' for code, _ in results), 1)
        self.assertIn(
            commitment.estado,
            {CompromisoStock.State.CONSUMED, CompromisoStock.State.RELEASED},
        )
        self.assertEqual(self.first_product.stock_comprometido, 0)

    def test_crossed_product_orders_use_pk_order_without_deadlock(self):
        self.receive(self.first_product, 2, 'cross-first')
        self.receive(self.second_product, 2, 'cross-second')
        first = self.make_order([
            (self.first_product, 1),
            (self.second_product, 1),
        ], 'CROSS-A')
        second = self.make_order([
            (self.second_product, 1),
            (self.first_product, 1),
        ], 'CROSS-B')
        results = self._run_two(
            self.operation(lambda: create_order_stock_commitments(first.pk)[0].pk),
            self.operation(lambda: create_order_stock_commitments(second.pk)[0].pk),
        )
        self.assertTrue(all(code == 'ok' for code, _ in results))
        self.first_product.refresh_from_db()
        self.second_product.refresh_from_db()
        self.assertEqual(self.first_product.stock_comprometido, 2)
        self.assertEqual(self.second_product.stock_comprometido, 2)

    def test_same_deterministic_key_under_concurrency_has_one_effect(self):
        self.receive(self.first_product, 2, 'same-key')
        order = self.make_order(
            [(self.first_product, 1)],
            'SAME-KEY',
            state='PAGADO',
        )
        create_order_stock_commitments(order.pk)
        results = self._run_two(
            self.operation(
                lambda: apply_order_inventory_effect(
                    order.pk,
                    actor=self.actor,
                ).movements[0].idempotency_key
            ),
            self.operation(
                lambda: apply_order_inventory_effect(
                    order.pk,
                    actor=self.actor,
                ).movements[0].idempotency_key
            ),
        )
        self.assertTrue(all(code == 'ok' for code, _ in results))
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(MovimientoStock.objects.filter(
            idempotency_key=results[0][1]
        ).count(), 1)
