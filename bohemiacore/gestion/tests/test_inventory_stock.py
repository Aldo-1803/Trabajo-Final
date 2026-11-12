from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from gestion.inventory_services import (
    STOCK_MOVEMENT_CREATED,
    StockConflict,
    StockInvalid,
    StockPermissionDenied,
    adjust_stock,
    correct_stock_movement,
    receive_stock,
    reconcile_product_stock,
)
from gestion.models import (
    Auditoria,
    CategoriaProducto,
    MovimientoStock,
    Producto,
)
from usuarios.models import Usuario


class InventoryFixtureMixin:
    def setUp(self):
        super().setUp()
        self.category = CategoriaProducto.objects.create(nombre='Inventario')
        self.product = Producto.objects.create(
            sku='INV-001',
            nombre='Producto inventariable',
            marca='BH',
            categoria=self.category,
            precio='100.00',
        )
        self.manager = Usuario.objects.create_user(
            email='stock-manager@test.com',
        )
        self.viewer = Usuario.objects.create_user(
            email='stock-viewer@test.com',
        )
        self.staff_without_permission = Usuario.objects.create_user(
            email='stock-staff@test.com',
            is_staff=True,
        )
        self.manager.user_permissions.add(self.permission('manage_stock'))
        self.viewer.user_permissions.add(self.permission('view_stock'))

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    def receive(self, *, key='receipt-1', quantity=5, actor=None):
        return receive_stock(
            product_id=self.product.pk,
            quantity=quantity,
            reason_code='COUNTED_RECEIPT',
            actor=actor or self.manager,
            idempotency_key=key,
            note='Recepción controlada',
        )

    def adjust(self, delta, *, key, actor=None):
        return adjust_stock(
            product_id=self.product.pk,
            delta=delta,
            reason_code='PHYSICAL_COUNT',
            actor=actor or self.manager,
            idempotency_key=key,
            note='Conteo físico',
        )


class InventoryModelAndServiceTests(InventoryFixtureMixin, TestCase):
    def test_receive_positive_balance_snapshots_actor_and_audit(self):
        movement = self.receive(quantity=7)
        self.product.refresh_from_db()

        self.assertEqual(movement.delta, 7)
        self.assertEqual(movement.tipo, MovimientoStock.Type.RECEIPT_IN)
        self.assertEqual(movement.stock_before, 0)
        self.assertEqual(movement.stock_after, 7)
        self.assertEqual(movement.actor_kind, MovimientoStock.ActorKind.HUMAN)
        self.assertEqual(movement.actor, self.manager)
        self.assertEqual(movement.reason_code, 'COUNTED_RECEIPT')
        self.assertEqual(self.product.stock_real, 7)
        audit = Auditoria.objects.get(
            tabla=STOCK_MOVEMENT_CREATED,
            registro_id=movement.pk,
        )
        self.assertEqual(audit.valor_nuevo['delta'], 7)
        self.assertNotIn('receipt-1', audit.valor_nuevo.values())

    def test_receive_retry_returns_same_movement_and_new_key_adds(self):
        first = self.receive(key='receipt-retry', quantity=4)
        retry = self.receive(key='receipt-retry', quantity=4)
        second = self.receive(key='receipt-distinct', quantity=4)
        self.product.refresh_from_db()

        self.assertEqual(first.pk, retry.pk)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.product.stock_real, 8)
        self.assertEqual(MovimientoStock.objects.count(), 2)
        self.assertEqual(
            Auditoria.objects.filter(tabla=STOCK_MOVEMENT_CREATED).count(),
            2,
        )

    def test_same_key_with_different_payload_conflicts(self):
        self.receive(key='reused-key', quantity=3)
        with self.assertRaises(StockConflict) as conflict:
            self.receive(key='reused-key', quantity=4)
        self.assertEqual(conflict.exception.code, 'STOCK_IDEMPOTENCY_KEY_REUSED')

    def test_receive_requires_positive_quantity_and_permission(self):
        with self.assertRaises(StockInvalid):
            self.receive(quantity=0)
        with self.assertRaises(StockInvalid):
            self.receive(quantity=-1)
        with self.assertRaises(StockPermissionDenied):
            self.receive(actor=self.viewer)

    def test_adjust_positive_negative_to_zero_and_reject_below_zero(self):
        self.receive(quantity=5)
        positive = self.adjust(2, key='adjust-positive')
        negative = self.adjust(-3, key='adjust-negative')
        to_zero = self.adjust(-4, key='adjust-zero')
        self.product.refresh_from_db()

        self.assertEqual((positive.stock_before, positive.stock_after), (5, 7))
        self.assertEqual((negative.stock_before, negative.stock_after), (7, 4))
        self.assertEqual((to_zero.stock_before, to_zero.stock_after), (4, 0))
        self.assertEqual(self.product.stock_real, 0)
        with self.assertRaises(StockConflict) as conflict:
            self.adjust(-1, key='adjust-below-zero')
        self.assertEqual(conflict.exception.code, 'INSUFFICIENT_REAL_STOCK')
        self.assertFalse(
            MovimientoStock.objects.filter(
                idempotency_key='adjust-below-zero'
            ).exists()
        )

    def test_adjust_rejects_zero_and_is_idempotent(self):
        with self.assertRaises(StockInvalid):
            self.adjust(0, key='zero-adjustment')
        first = self.adjust(2, key='adjust-retry')
        retry = self.adjust(2, key='adjust-retry')
        self.assertEqual(first.pk, retry.pk)

    def test_correction_compensates_retries_and_preserves_original(self):
        original = self.receive(quantity=6)
        correction = correct_stock_movement(
            movement_id=original.pk,
            reason_code='WRONG_RECEIPT',
            actor=self.manager,
            idempotency_key='correction-retry',
            note='Carga duplicada',
        )
        retry = correct_stock_movement(
            movement_id=original.pk,
            reason_code='WRONG_RECEIPT',
            actor=self.manager,
            idempotency_key='correction-retry',
            note='Carga duplicada',
        )
        original.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(correction.pk, retry.pk)
        self.assertEqual(correction.tipo, MovimientoStock.Type.CORRECTION)
        self.assertEqual(correction.delta, -6)
        self.assertEqual(correction.reverses_movement, original)
        self.assertEqual(original.delta, 6)
        self.assertEqual(self.product.stock_real, 0)
        with self.assertRaises(StockConflict) as conflict:
            correct_stock_movement(
                movement_id=original.pk,
                reason_code='SECOND_CORRECTION',
                actor=self.manager,
                idempotency_key='second-correction',
            )
        self.assertEqual(
            conflict.exception.code,
            'STOCK_MOVEMENT_ALREADY_CORRECTED',
        )

    def test_correction_that_would_make_current_balance_negative_is_rejected(self):
        receipt = self.receive(quantity=5)
        self.adjust(-5, key='consume-for-correction-test')
        with self.assertRaises(StockConflict):
            correct_stock_movement(
                movement_id=receipt.pk,
                reason_code='WRONG_RECEIPT',
                actor=self.manager,
                idempotency_key='negative-correction',
            )

    def test_movement_is_strongly_immutable(self):
        movement = self.receive()
        movement.delta = 99
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            MovimientoStock.objects.filter(pk=movement.pk).update(delta=99)
        with self.assertRaises(ValidationError):
            movement.delete()
        with self.assertRaises(ValidationError):
            MovimientoStock.objects.filter(pk=movement.pk).delete()
        with self.assertRaises(ValidationError):
            MovimientoStock.objects.bulk_update([movement], ['delta'])
        with self.assertRaises(ValidationError):
            MovimientoStock.objects.bulk_create([])
        with self.assertRaises(ValidationError):
            MovimientoStock.objects.update_or_create(
                idempotency_key=movement.idempotency_key,
                defaults={'delta': 1},
            )
        with self.assertRaises(ValidationError):
            MovimientoStock.objects.create(
                producto=self.product,
                delta=1,
                tipo=MovimientoStock.Type.RECEIPT_IN,
                reason_code='DIRECT_CREATE',
                actor_kind=MovimientoStock.ActorKind.HUMAN,
                actor=self.manager,
                idempotency_key='direct-create',
                stock_before=5,
                stock_after=6,
            )

    def test_database_rejects_zero_delta_when_orm_guard_is_bypassed(self):
        invalid = MovimientoStock(
            producto=self.product,
            delta=0,
            tipo=MovimientoStock.Type.MANUAL_ADJUSTMENT,
            reason_code='DB_CHECK',
            actor_kind=MovimientoStock.ActorKind.SYSTEM,
            idempotency_key='db-zero-delta',
            stock_before=0,
            stock_after=0,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet.bulk_create(
                MovimientoStock.objects.all(),
                [invalid],
            )

    def test_projection_reconciles_with_ledger_sum(self):
        self.receive(quantity=10)
        self.adjust(-4, key='reconcile-out')
        result = reconcile_product_stock(self.product.pk)
        self.assertTrue(result.reconciled)
        self.assertEqual(result.projected_balance, 6)
        self.assertEqual(result.ledger_balance, 6)

    def test_stock_disponible_does_not_hide_legacy_debt_with_clamp(self):
        # La constraint D2 impide persistir deuda; la property sigue siendo una
        # resta exacta y no oculta una instancia legacy cargada en memoria.
        self.product.stock_real = 1
        self.product.stock_comprometido = 3
        self.assertEqual(self.product.stock_disponible, -2)
        self.assertTrue(self.product.necesita_reposicion())


class InventoryPermissionAndPrivacyApiTests(InventoryFixtureMixin, TestCase):
    def client_for(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def test_public_catalog_has_availability_without_internal_quantities(self):
        self.receive(quantity=2)
        response = self.client_for().get(reverse('productos-list'))
        self.assertEqual(response.status_code, 200)
        payload = response.data[0]
        self.assertTrue(payload['available'])
        for internal_field in (
            'stock_real',
            'stock_comprometido',
            'stock_minimo',
            'stock_disponible',
            'necesita_reposicion',
        ):
            self.assertNotIn(internal_field, payload)

    def test_view_stock_can_read_quantities_and_movements_only(self):
        movement = self.receive(quantity=2)
        client = self.client_for(self.viewer)
        catalog = client.get(reverse('productos-list'))
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.data[0]['stock_real'], 2)
        movements = client.get(
            reverse('productos-stock-movements', args=[self.product.pk])
        )
        self.assertEqual(movements.status_code, 200)
        self.assertEqual(movements.data['count'], 1)
        self.assertEqual(movements.data['results'][0]['id'], movement.pk)
        global_movements = client.get(
            reverse('stock-movement-list'),
            {'producto': self.product.pk, 'tipo': 'RECEIPT_IN'},
        )
        self.assertEqual(global_movements.status_code, 200)
        self.assertEqual(global_movements.data['count'], 1)
        self.assertEqual(global_movements.data['results'][0]['id'], movement.pk)
        forbidden = client.post(
            reverse('productos-receive-stock', args=[self.product.pk]),
            {
                'quantity': 1,
                'reason_code': 'API_RECEIPT',
                'idempotency_key': 'viewer-cannot-receive',
            },
            format='json',
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_manage_stock_does_not_imply_ledger_read_permission(self):
        response = self.client_for(self.manager).get(
            reverse('stock-movement-list')
        )
        self.assertEqual(response.status_code, 403)

    def test_manage_stock_individual_permission_mutates_without_staff(self):
        self.assertFalse(self.manager.is_staff)
        response = self.client_for(self.manager).post(
            reverse('productos-receive-stock', args=[self.product.pk]),
            {
                'quantity': 3,
                'reason_code': 'API_RECEIPT',
                'idempotency_key': 'individual-permission-receipt',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_real, 3)
        self.assertFalse(self.manager.has_perm('gestion.manage_products'))
        self.assertFalse(self.manager.has_perm('gestion.manage_prices'))

    def test_staff_without_manage_stock_cannot_mutate(self):
        response = self.client_for(self.staff_without_permission).post(
            reverse('productos-adjust-stock', args=[self.product.pk]),
            {
                'delta': 1,
                'reason_code': 'API_ADJUSTMENT',
                'idempotency_key': 'staff-without-permission',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MovimientoStock.objects.exists())

    def test_manage_stock_can_adjust_and_correct_through_semantic_api(self):
        client = self.client_for(self.manager)
        adjusted = client.post(
            reverse('productos-adjust-stock', args=[self.product.pk]),
            {
                'delta': 4,
                'reason_code': 'API_ADJUSTMENT',
                'idempotency_key': 'api-adjust',
            },
            format='json',
        )
        self.assertEqual(adjusted.status_code, 200)
        corrected = client.post(
            reverse('stock-movement-correct', args=[adjusted.data['id']]),
            {
                'reason_code': 'API_CORRECTION',
                'idempotency_key': 'api-correction',
            },
            format='json',
        )
        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(corrected.data['delta'], -4)

    def test_generic_product_patch_cannot_write_inventory_fields(self):
        self.staff_without_permission.user_permissions.add(
            self.permission('manage_products')
        )
        self.receive(quantity=3)
        response = self.client_for(self.staff_without_permission).patch(
            reverse('productos-detail', args=[self.product.pk]),
            {
                'nombre': 'Nombre actualizado',
                'stock_real': 999,
                'stock_comprometido': 999,
                'stock_minimo': 999,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertNotEqual(self.product.nombre, 'Nombre actualizado')
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertEqual(self.product.stock_minimo, 5)

    def test_client_without_view_stock_cannot_list_movements(self):
        client_user = Usuario.objects.create_user(
            email='inventory-client@test.com',
        )
        response = self.client_for(client_user).get(
            reverse('productos-stock-movements', args=[self.product.pk])
        )
        self.assertEqual(response.status_code, 403)
