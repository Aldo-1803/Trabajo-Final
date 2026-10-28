from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from gestion.inventory_services import StockConflict, receive_stock
from gestion.models import (
    Carrito,
    CarritoItem,
    CategoriaProducto,
    CompromisoStock,
    MovimientoStock,
    OrdenCompra,
    OrdenItem,
    OrdenPendiente,
    Producto,
    ProviderPaymentAttempt,
)
from gestion.order_inventory_services import (
    OrderInventoryConflict,
    apply_order_inventory_effect,
    create_order_stock_commitments,
    release_order_stock_commitments,
)
from gestion.payment_providers import (
    CheckoutCreated,
    PaymentProviderOutcomeUnknown,
)
from usuarios.models import Cliente, Usuario


class OrderInventoryFixtureMixin:
    def setUp(self):
        super().setUp()
        self.user = Usuario.objects.create_user(
            email='order-client@test.com',
            password='OrderClient!2026',
        )
        self.client_profile = Cliente.objects.create(usuario=self.user)
        self.stock_actor = Usuario.objects.create_user(
            email='order-stock@test.com',
            password='OrderStock!2026',
        )
        self.stock_actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_stock',
        ))
        category = CategoriaProducto.objects.create(nombre='Órdenes D2')
        self.product = Producto.objects.create(
            sku='D2-001',
            nombre='Producto D2',
            categoria=category,
            precio=Decimal('100.00'),
        )
        self.other_product = Producto.objects.create(
            sku='D2-002',
            nombre='Otro producto D2',
            categoria=category,
            precio=Decimal('50.00'),
        )

    def receive(self, product, quantity, suffix):
        return receive_stock(
            product_id=product.pk,
            quantity=quantity,
            reason_code='ORDER_TEST_RECEIPT',
            actor=self.stock_actor,
            idempotency_key=f'order-test-receipt-{suffix}',
        )

    def make_order(self, lines, *, state='PENDIENTE', code=None):
        order = OrdenCompra.objects.create(
            codigo=code or f'D2-{OrdenCompra.objects.count() + 1}',
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


class OrderInventoryServiceTests(OrderInventoryFixtureMixin, TestCase):
    def test_create_commitment_with_sufficient_stock_and_retry(self):
        self.receive(self.product, 5, 'create')
        order = self.make_order([(self.product, 2)])

        first = create_order_stock_commitments(order.pk)
        retry = create_order_stock_commitments(order.pk)
        self.product.refresh_from_db()

        self.assertEqual(first[0].pk, retry[0].pk)
        self.assertEqual(first[0].estado, CompromisoStock.State.ACTIVE)
        self.assertEqual(first[0].cantidad, 2)
        self.assertEqual(self.product.stock_real, 5)
        self.assertEqual(self.product.stock_comprometido, 2)
        self.assertEqual(self.product.stock_disponible, 3)
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).exists()
        )

    def test_insufficient_multi_product_commitment_is_all_or_nothing(self):
        self.receive(self.product, 3, 'multi-first')
        self.receive(self.other_product, 1, 'multi-second')
        order = self.make_order([
            (self.product, 2),
            (self.other_product, 2),
        ])

        with self.assertRaises(OrderInventoryConflict) as conflict:
            create_order_stock_commitments(order.pk)

        self.assertEqual(conflict.exception.code, 'INSUFFICIENT_AVAILABLE_STOCK')
        self.product.refresh_from_db()
        self.other_product.refresh_from_db()
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertEqual(self.other_product.stock_comprometido, 0)
        self.assertFalse(CompromisoStock.objects.exists())

    def test_release_is_idempotent_and_never_changes_real_stock(self):
        self.receive(self.product, 4, 'release')
        order = self.make_order([(self.product, 3)])
        create_order_stock_commitments(order.pk)

        first = release_order_stock_commitments(order.pk)
        retry = release_order_stock_commitments(order.pk)
        order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=order)

        self.assertEqual(first[0].pk, retry[0].pk)
        self.assertEqual(commitment.estado, CompromisoStock.State.RELEASED)
        self.assertIsNotNone(commitment.released_at)
        self.assertIsNone(commitment.consumed_at)
        self.assertEqual(order.estado, 'CANCELADO')
        self.assertEqual(self.product.stock_real, 4)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).exists()
        )

    def test_consume_creates_one_sale_movement_and_retry_is_idempotent(self):
        opening = self.receive(self.product, 5, 'consume')
        order = self.make_order([
            (self.product, 1),
            (self.product, 2),
        ])
        create_order_stock_commitments(order.pk)

        first = apply_order_inventory_effect(order.pk)
        retry = apply_order_inventory_effect(order.pk)
        order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=order)
        movement = MovimientoStock.objects.get(
            tipo=MovimientoStock.Type.ORDER_SALE_OUT
        )

        self.assertTrue(first.applied)
        self.assertFalse(retry.applied)
        self.assertEqual(first.movements[0].pk, retry.movements[0].pk)
        self.assertEqual(movement.delta, -3)
        self.assertEqual(movement.reference_type, 'ORDEN_COMPRA')
        self.assertEqual(movement.reference_id, str(order.pk))
        self.assertEqual(movement.stock_before, 5)
        self.assertEqual(movement.stock_after, 2)
        self.assertEqual(commitment.estado, CompromisoStock.State.CONSUMED)
        self.assertIsNotNone(commitment.consumed_at)
        self.assertEqual(order.estado, 'COMPLETADO')
        self.assertEqual(self.product.stock_real, 2)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertEqual(self.product.stock_disponible, 2)
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).count(),
            1,
        )
        self.assertEqual(
            MovimientoStock.objects.filter(producto=self.product).aggregate(
                total=Sum('delta')
            )['total'],
            self.product.stock_real,
        )
        self.assertEqual(opening.delta + movement.delta, self.product.stock_real)

    def test_active_commitment_sum_matches_materialized_projection(self):
        self.receive(self.product, 6, 'projection')
        first = self.make_order([(self.product, 2)])
        second = self.make_order([(self.product, 1)])
        create_order_stock_commitments(first.pk)
        create_order_stock_commitments(second.pk)
        self.product.refresh_from_db()
        active_sum = CompromisoStock.objects.filter(
            producto=self.product,
            estado=CompromisoStock.State.ACTIVE,
        ).aggregate(total=Sum('cantidad'))['total']
        self.assertEqual(active_sum, self.product.stock_comprometido)
        self.assertEqual(
            self.product.stock_disponible,
            self.product.stock_real - self.product.stock_comprometido,
        )

    def test_manual_output_cannot_invade_active_commitment(self):
        self.receive(self.product, 3, 'reserved-adjust')
        order = self.make_order([(self.product, 2)])
        create_order_stock_commitments(order.pk)
        with self.assertRaises(StockConflict) as conflict:
            from gestion.inventory_services import adjust_stock
            adjust_stock(
                product_id=self.product.pk,
                delta=-2,
                reason_code='COUNT',
                actor=self.stock_actor,
                idempotency_key='reserved-adjustment',
            )
        self.assertEqual(conflict.exception.code, 'STOCK_RESERVED_BY_ACTIVE_ORDERS')

    def test_commitment_cannot_be_created_or_modified_outside_service(self):
        order = self.make_order([(self.product, 1)])
        with self.assertRaises(ValidationError):
            CompromisoStock.objects.create(
                orden=order,
                producto=self.product,
                cantidad=1,
                idempotency_key='direct-commitment',
            )

    def test_migration_preflight_blocks_ambiguous_legacy_projection(self):
        self.receive(self.product, 2, 'migration-preflight')
        order = self.make_order([(self.product, 1)])
        create_order_stock_commitments(order.pk)
        migration = import_module(
            'gestion.migrations.0033_compromisostock_order_inventory'
        )
        schema_editor = SimpleNamespace(
            connection=SimpleNamespace(alias=self.product._state.db)
        )
        with self.assertRaisesRegex(RuntimeError, 'no puede atribuirse'):
            migration.preflight_legacy_commitments(apps, schema_editor)


class OrderInventoryLegacyEndpointTests(OrderInventoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def add_cart_item(self, product, quantity):
        cart, _ = Carrito.objects.get_or_create(cliente=self.client_profile)
        CarritoItem.objects.create(
            carrito=cart,
            producto=product,
            cantidad=quantity,
        )
        return cart

    def test_finalize_and_confirm_delivery_delegate_to_single_effect(self):
        self.receive(self.product, 3, 'endpoint-order')
        self.add_cart_item(self.product, 2)
        finalized = self.api.post(reverse('carrito-finalizar-compra'), {}, format='json')
        self.assertEqual(finalized.status_code, status.HTTP_200_OK)
        order = OrdenCompra.objects.get(pk=finalized.data['orden_id'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_comprometido, 2)

        url = reverse('orden-compra-confirmar-entrega', args=[order.pk])
        first = self.api.post(url, {}, format='json')
        retry = self.api.post(url, {}, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_real, 1)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT,
                reference_id=str(order.pk),
            ).count(),
            1,
        )

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_legacy_mp_checkout_creates_commitment_before_redirect(
        self,
        provider_factory,
    ):
        provider_factory.return_value.create_checkout.return_value = CheckoutCreated(
            provider_order_id='legacy-cart-c1',
            checkout_url='https://www.mercadopago.com.ar/checkout/test',
            provider_status='created',
            expires_at=None,
        )
        self.receive(self.product, 2, 'mp-checkout')
        cart = self.add_cart_item(self.product, 1)
        response = self.api.post(
            reverse('iniciar_pago_mp'),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='legacy-cart-c1',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = OrdenCompra.objects.get(pk=response.data['orden_id'])
        commitment = CompromisoStock.objects.get(orden=order)
        self.product.refresh_from_db()
        self.assertEqual(order.estado, 'ESPERANDO_PAGO')
        self.assertEqual(commitment.estado, CompromisoStock.State.ACTIVE)
        self.assertEqual(self.product.stock_real, 2)
        self.assertEqual(self.product.stock_comprometido, 1)
        self.assertFalse(cart.items.exists())

    @patch('gestion.provider_checkout_services.get_payment_provider')
    def test_mp_unknown_outcome_preserves_order_and_commitment(
        self,
        provider_factory,
    ):
        provider_factory.return_value.create_checkout.side_effect = (
            PaymentProviderOutcomeUnknown()
        )
        self.receive(self.product, 2, 'mp-rollback')
        cart = self.add_cart_item(self.product, 1)
        response = self.api.post(
            reverse('iniciar_pago_mp'),
            {},
            format='json',
            HTTP_IDEMPOTENCY_KEY='legacy-cart-unknown',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.product.refresh_from_db()
        self.assertEqual(OrdenCompra.objects.count(), 1)
        self.assertEqual(CompromisoStock.objects.count(), 1)
        self.assertEqual(self.product.stock_comprometido, 1)
        self.assertFalse(cart.items.exists())
        self.assertEqual(
            ProviderPaymentAttempt.objects.get().status,
            ProviderPaymentAttempt.Status.OUTCOME_UNKNOWN,
        )

    def test_order_cancellation_releases_without_physical_output(self):
        self.receive(self.product, 2, 'endpoint-cancel')
        order = self.make_order([(self.product, 2)])
        create_order_stock_commitments(order.pk)
        response = self.api.post(
            reverse('orden-compra-cancelar', args=[order.pk]),
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_real, 2)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).exists()
        )

    def test_pending_order_confirmation_uses_canonical_order_service(self):
        self.receive(self.product, 2, 'pending-confirm')
        self.add_cart_item(self.product, 1)
        registered = self.api.post(
            reverse('carrito-registrar-intencion-compra'),
            {},
            format='json',
        )
        self.assertEqual(registered.status_code, status.HTTP_201_CREATED)
        pending = OrdenPendiente.objects.get(pk=registered.data['orden_id'])
        self.assertIsNotNone(pending.orden_compra_id)

        response = self.api.post(
            reverse('orden-pendiente-confirmar-pago', args=[pending.pk]),
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pending.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(pending.estado, 'COMPLETADA')
        self.assertEqual(self.product.stock_real, 1)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertEqual(
            MovimientoStock.objects.filter(
                reference_id=str(pending.orden_compra_id),
                tipo=MovimientoStock.Type.ORDER_SALE_OUT,
            ).count(),
            1,
        )

    def test_pending_delivery_and_cancellation_use_commitment_services(self):
        self.receive(self.product, 3, 'pending-delivery-cancel')
        delivered_order = self.make_order(
            [(self.product, 1)],
            code='D2-PENDING-DELIVERY',
        )
        create_order_stock_commitments(delivered_order.pk)
        delivered_pending = OrdenPendiente.objects.create(
            cliente=self.client_profile,
            orden_compra=delivered_order,
            estado='CONFIRMADA',
            items_json=[{
                'producto_id': self.product.pk,
                'cantidad': 1,
                'precio': '100.00',
            }],
            monto_total=Decimal('100.00'),
        )
        delivered = self.api.post(
            reverse(
                'orden-pendiente-confirmar-entrega',
                args=[delivered_pending.pk],
            ),
            {},
            format='json',
        )
        self.assertEqual(delivered.status_code, status.HTTP_200_OK)

        cancelled_order = self.make_order(
            [(self.product, 1)],
            code='D2-PENDING-CANCEL',
        )
        create_order_stock_commitments(cancelled_order.pk)
        cancelled_pending = OrdenPendiente.objects.create(
            cliente=self.client_profile,
            orden_compra=cancelled_order,
            estado='PENDIENTE',
            items_json=[{
                'producto_id': self.product.pk,
                'cantidad': 1,
                'precio': '100.00',
            }],
            monto_total=Decimal('100.00'),
        )
        cancelled = self.api.post(
            reverse('orden-pendiente-cancelar', args=[cancelled_pending.pk]),
            {},
            format='json',
        )
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        cancelled_order.refresh_from_db()
        self.assertEqual(self.product.stock_real, 2)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertEqual(cancelled_order.estado, 'CANCELADO')
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).count(),
            1,
        )

    def test_unlinked_legacy_pending_order_is_bridged_just_in_time(self):
        self.receive(self.product, 2, 'legacy-pending-jit')
        pending = OrdenPendiente.objects.create(
            cliente=self.client_profile,
            estado='PENDIENTE',
            items_json=[{
                'producto_id': self.product.pk,
                'cantidad': 1,
                'precio': '100.00',
                'subtotal': '100.00',
            }],
            monto_total=Decimal('100.00'),
        )
        response = self.api.post(
            reverse('orden-pendiente-confirmar-entrega', args=[pending.pk]),
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pending.refresh_from_db()
        self.product.refresh_from_db()
        self.assertIsNotNone(pending.orden_compra_id)
        self.assertEqual(pending.estado, 'COMPLETADA')
        self.assertEqual(self.product.stock_real, 1)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertEqual(
            CompromisoStock.objects.get(
                orden_id=pending.orden_compra_id
            ).estado,
            CompromisoStock.State.CONSUMED,
        )

    @patch('gestion.views.MercadoPagoAdapter.fetch_legacy_payment')
    def test_legacy_webhook_delegates_and_is_idempotent(self, fetch_payment):
        self.receive(self.product, 2, 'webhook')
        order = self.make_order(
            [(self.product, 1)],
            state='ESPERANDO_PAGO',
            code='D2-WEBHOOK',
        )
        create_order_stock_commitments(order.pk)
        fetch_payment.return_value = {
            'response': {
                'status': 'approved',
                'external_reference': str(order.pk),
                'transaction_amount': 100,
            }
        }
        payload = {'type': 'payment', 'data': {'id': 'provider-d2-1'}}
        first = self.api.post(reverse('webhook_mp'), payload, format='json')
        retry = self.api.post(reverse('webhook_mp'), payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_real, 1)
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT,
                reference_id=str(order.pk),
            ).count(),
            1,
        )

    @patch('gestion.views.MercadoPagoAdapter.fetch_legacy_payment')
    def test_legacy_webhook_rejection_releases_without_output(self, fetch_payment):
        self.receive(self.product, 2, 'webhook-reject')
        order = self.make_order(
            [(self.product, 1)],
            state='ESPERANDO_PAGO',
            code='D2-WEBHOOK-REJECT',
        )
        create_order_stock_commitments(order.pk)
        fetch_payment.return_value = {
            'response': {
                'status': 'rejected',
                'external_reference': str(order.pk),
                'transaction_amount': 100,
            }
        }
        response = self.api.post(
            reverse('webhook_mp'),
            {'type': 'payment', 'data': {'id': 'provider-d2-rejected'}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=order)
        self.assertEqual(order.estado, 'RECHAZADO')
        self.assertEqual(commitment.estado, CompromisoStock.State.RELEASED)
        self.assertEqual(self.product.stock_real, 2)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertFalse(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Type.ORDER_SALE_OUT
            ).exists()
        )
