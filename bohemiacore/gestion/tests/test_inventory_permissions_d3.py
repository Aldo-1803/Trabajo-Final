from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from gestion.models import (
    CategoriaProducto,
    MovimientoStock,
    Producto,
    Promocion,
    Servicio,
)
from usuarios.models import Cliente, Usuario


class InventoryPermissionMatrixD3Tests(TestCase):
    def setUp(self):
        self.category = CategoriaProducto.objects.create(nombre='D3')
        self.product = Producto.objects.create(
            sku='D3-001',
            nombre='Producto D3',
            categoria=self.category,
            precio=Decimal('100.00'),
        )
        self.users = {}
        for name in (
            'viewer', 'stock_manager', 'product_manager', 'price_manager',
            'promotion_manager', 'staff_without_permissions', 'client',
        ):
            self.users[name] = Usuario.objects.create_user(
                email=f'{name}@d3.test',
                is_staff=name == 'staff_without_permissions',
            )
        Cliente.objects.create(usuario=self.users['client'])
        self.grant('viewer', 'view_stock')
        self.grant('stock_manager', 'manage_stock')
        self.grant('product_manager', 'manage_products')
        self.grant('price_manager', 'manage_prices')
        self.grant('promotion_manager', 'manage_promotions')

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    def grant(self, username, codename):
        self.users[username].user_permissions.add(self.permission(codename))

    def client_for(self, username):
        client = APIClient()
        client.force_authenticate(self.users[username])
        return client

    def product_url(self):
        return reverse('productos-detail', args=[self.product.pk])

    def test_view_stock_reads_internal_inventory_but_cannot_mutate(self):
        client = self.client_for('viewer')
        catalog = client.get(reverse('productos-list'))
        self.assertEqual(catalog.status_code, 200)
        self.assertIn('stock_real', catalog.data[0])
        denied = client.post(
            reverse('productos-receive-stock', args=[self.product.pk]),
            {
                'quantity': 1,
                'reason_code': 'D3_TEST',
                'idempotency_key': 'd3-viewer-receipt',
            },
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

    def test_manage_stock_uses_commands_but_cannot_manage_prices(self):
        client = self.client_for('stock_manager')
        received = client.post(
            reverse('productos-receive-stock', args=[self.product.pk]),
            {
                'quantity': 2,
                'reason_code': 'D3_TEST',
                'idempotency_key': 'd3-manager-receipt',
            },
            format='json',
        )
        self.assertEqual(received.status_code, 200)
        denied = client.patch(
            self.product_url(),
            {'precio': '250.00'},
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

    def test_manage_products_updates_metadata_not_price_or_stock(self):
        client = self.client_for('product_manager')
        create_denied = client.post(
            reverse('productos-list'),
            {
                'nombre': 'Producto sin permiso de precio',
                'categoria': self.category.pk,
                'precio': '100.00',
            },
            format='json',
        )
        self.assertEqual(create_denied.status_code, 403)
        updated = client.patch(
            self.product_url(),
            {'nombre': 'Metadata autorizada'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        price_denied = client.patch(
            self.product_url(),
            {'precio': '200.00'},
            format='json',
        )
        self.assertEqual(price_denied.status_code, 403)
        stock_denied = client.patch(
            self.product_url(),
            {'stock_real': 10},
            format='json',
        )
        self.assertEqual(stock_denied.status_code, 400)

    def test_manage_prices_updates_only_price(self):
        client = self.client_for('price_manager')
        updated = client.patch(
            self.product_url(),
            {'precio': '175.50'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.precio, Decimal('175.50'))
        metadata_denied = client.patch(
            self.product_url(),
            {'nombre': 'No autorizado'},
            format='json',
        )
        self.assertEqual(metadata_denied.status_code, 403)

    def test_service_price_surface_uses_manage_prices_not_staff(self):
        service = Servicio.objects.create(
            nombre='Servicio precio D3',
            precio_base=Decimal('500.00'),
        )
        updated = self.client_for('price_manager').patch(
            reverse('servicio-detail', args=[service.pk]),
            {'precio_base': '650.00'},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        denied = self.client_for('staff_without_permissions').patch(
            reverse('servicio-detail', args=[service.pk]),
            {'precio_base': '700.00'},
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

    def test_manage_promotions_manages_promotions_but_not_stock(self):
        client = self.client_for('promotion_manager')
        today = date.today()
        created = client.post(
            reverse('promocion-list'),
            {
                'nombre': 'Promo D3',
                'descripcion': 'Permiso efectivo',
                'tipo': 'COMBO',
                'descuento_porcentaje': 10,
                'fecha_inicio': today.isoformat(),
                'fecha_fin': (today + timedelta(days=2)).isoformat(),
                'productos': [self.product.pk],
            },
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(Promocion.objects.filter(nombre='Promo D3').exists())
        denied = client.post(
            reverse('productos-adjust-stock', args=[self.product.pk]),
            {
                'delta': 1,
                'reason_code': 'D3_TEST',
                'idempotency_key': 'd3-promotion-adjust',
            },
            format='json',
        )
        self.assertEqual(denied.status_code, 403)

    def test_staff_without_effective_permissions_has_no_write_authority(self):
        client = self.client_for('staff_without_permissions')
        self.assertEqual(
            client.patch(
                self.product_url(),
                {'nombre': 'Staff bypass'},
                format='json',
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                reverse('promocion-list'),
                {},
                format='json',
            ).status_code,
            403,
        )

    def test_individual_manage_products_permission_can_manage_categories(self):
        inactive = CategoriaProducto.objects.create(
            nombre='Categoría inactiva',
            activo=False,
        )
        client = self.client_for('product_manager')
        managed_list = client.get(reverse('categoria-producto-list'))
        self.assertEqual(managed_list.status_code, 200)
        self.assertIn(inactive.pk, {item['id'] for item in managed_list.data})
        created = client.post(
            reverse('categoria-producto-list'),
            {'nombre': 'Categoría individual', 'activo': True},
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        anonymous = APIClient().post(
            reverse('categoria-producto-list'),
            {'nombre': 'Categoría pública'},
            format='json',
        )
        self.assertIn(anonymous.status_code, {401, 403})
        public_list = APIClient().get(reverse('categoria-producto-list'))
        self.assertNotIn(inactive.pk, {item['id'] for item in public_list.data})

    def test_client_never_receives_internal_quantities_or_movements(self):
        client = self.client_for('client')
        catalog = client.get(reverse('productos-list'))
        self.assertEqual(catalog.status_code, 200)
        for field in (
            'stock_real', 'stock_comprometido', 'stock_minimo',
            'stock_disponible', 'necesita_reposicion',
        ):
            self.assertNotIn(field, catalog.data[0])
        movements = client.get(reverse('stock-movement-list'))
        self.assertEqual(movements.status_code, 403)

    def test_generic_inventory_write_is_rejected_not_ignored(self):
        response = self.client_for('product_manager').patch(
            self.product_url(),
            {'stock_real': 99, 'stock_comprometido': 50},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_real, 0)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertFalse(MovimientoStock.objects.exists())

    def test_mixed_authorized_and_unauthorized_update_is_atomic(self):
        response = self.client_for('product_manager').patch(
            self.product_url(),
            {'nombre': 'No debe persistir', 'precio': '999.00'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertEqual(self.product.nombre, 'Producto D3')
        self.assertEqual(self.product.precio, Decimal('100.00'))
