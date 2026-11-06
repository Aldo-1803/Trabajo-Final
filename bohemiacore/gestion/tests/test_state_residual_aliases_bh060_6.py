from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from gestion.inventory_services import STOCK_MOVEMENT_CREATED
from gestion.middleware import _thread_locals
from gestion.models import (
    Auditoria,
    CategoriaProducto,
    DiagnosticoCapilar,
    Habilidad,
    MovimientoStock,
    OrdenCompra,
    Pago,
    Personal,
    PersonalHabilidad,
    Producto,
)
from usuarios.access_services import (
    change_administrative_business_role,
    deactivate_account,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessPermission, BusinessRole, get_business_role


def permission(codename, app_label='gestion'):
    return Permission.objects.get(
        content_type__app_label=app_label,
        codename=codename,
    )


def user_with_role(email, role, **flags):
    user = Usuario.objects.create_user(email=email, **flags)
    user.groups.add(Group.objects.get(name=role))
    return user


def jwt_client(user):
    client = APIClient()
    access = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return client


class CleanThreadLocalAPITestCase(APITestCase):
    def setUp(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().setUp()

    def tearDown(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().tearDown()


class AccountAndStockTransitionTests(CleanThreadLocalAPITestCase):
    def setUp(self):
        self.category = CategoriaProducto.objects.create(nombre='BH060-6 stock')
        self.product = Producto.objects.create(
            sku='BH0606-STOCK',
            nombre='Producto de transición',
            marca='BH',
            categoria=self.category,
            precio='100.00',
        )
        self.manage_stock = permission('manage_stock')

    def receive(self, client, key):
        return client.post(
            reverse('productos-receive-stock', args=[self.product.pk]),
            {
                'quantity': 3,
                'reason_code': 'BH060_STATE_TEST',
                'idempotency_key': key,
            },
            format='json',
        )

    def test_preissued_access_token_cannot_mutate_after_deactivation(self):
        actor = Usuario.objects.create_user(email='bh060-inactive@test.com')
        actor.user_permissions.add(self.manage_stock)
        client = jwt_client(actor)
        account_manager = Usuario.objects.create_user(
            email='bh060-account-manager@test.com'
        )
        account_manager.user_permissions.add(permission('manage_users', 'usuarios'))

        deactivate_account(
            account_manager,
            actor,
            'Desactivación dinámica para verificar token previo',
        )
        response = self.receive(client, 'inactive-preissued-token')

        self.product.refresh_from_db()
        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )
        self.assertEqual(self.product.stock_real, 0)
        self.assertFalse(MovimientoStock.objects.exists())
        self.assertFalse(
            Auditoria.objects.filter(tabla=STOCK_MOVEMENT_CREATED).exists()
        )

    def test_individual_grant_and_revoke_apply_to_new_requests_without_staff(self):
        actor = Usuario.objects.create_user(email='bh060-grant-revoke@test.com')
        client = jwt_client(actor)

        denied_before = self.receive(client, 'before-grant')
        actor.user_permissions.add(self.manage_stock)
        allowed = self.receive(client, 'after-grant')
        actor.user_permissions.remove(self.manage_stock)
        denied_after = self.receive(client, 'after-revoke')

        staff = Usuario.objects.create_user(
            email='bh060-staff-no-permission@test.com',
            is_staff=True,
        )
        denied_staff = self.receive(jwt_client(staff), 'staff-without-grant')

        self.product.refresh_from_db()
        self.assertEqual(denied_before.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(denied_after.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(denied_staff.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(actor.is_staff)
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(MovimientoStock.objects.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=STOCK_MOVEMENT_CREATED).count(),
            1,
        )


class RoleCacheAndAliasTransitionTests(CleanThreadLocalAPITestCase):
    def test_demotion_invalidates_role_capacity_and_preserves_technical_group(self):
        actor = Usuario.objects.create_user(email='bh060-role-manager@test.com')
        actor.user_permissions.add(
            permission('manage_users', 'usuarios'),
            permission('assign_roles', 'usuarios'),
        )
        target = user_with_role(
            'bh060-demoted-admin@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        Cliente.objects.create(usuario=target)
        user_with_role(
            'bh060-backup-admin@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        technical_group = Group.objects.create(name='BH0606_STOCK_READERS')
        technical_group.permissions.add(permission('view_stock'))
        target.groups.add(technical_group)
        client = jwt_client(target)

        self.assertTrue(target.has_perm(BusinessPermission.VIEW_FINANCIAL_REPORTS))
        self.assertIn('_perm_cache', target.__dict__)
        for route_name in ('payment-list', 'pagos-list'):
            self.assertEqual(
                client.get(reverse(route_name)).status_code,
                status.HTTP_200_OK,
            )

        result = change_administrative_business_role(
            actor,
            target,
            BusinessRole.CLIENTE,
            'Degradación dinámica para verificar autoridad efectiva',
        )

        fresh_target = Usuario.objects.get(pk=target.pk)
        self.assertTrue(result.changed)
        self.assertNotIn('_perm_cache', target.__dict__)
        self.assertFalse(target.has_perm(BusinessPermission.VIEW_FINANCIAL_REPORTS))
        self.assertFalse(
            fresh_target.has_perm(BusinessPermission.VIEW_FINANCIAL_REPORTS)
        )
        self.assertEqual(get_business_role(fresh_target), BusinessRole.CLIENTE)
        self.assertTrue(fresh_target.groups.filter(pk=technical_group.pk).exists())
        self.assertTrue(fresh_target.has_perm(BusinessPermission.VIEW_STOCK))

        for route_name in ('payment-list', 'pagos-list'):
            self.assertEqual(
                client.get(reverse(route_name)).status_code,
                status.HTTP_403_FORBIDDEN,
            )
        self.assertEqual(
            client.get(reverse('stock-movement-list')).status_code,
            status.HTTP_200_OK,
        )


class PersonalAndSkillTransitionTests(CleanThreadLocalAPITestCase):
    def test_personal_deactivation_closes_canonical_and_legacy_own_agenda(self):
        actor = Usuario.objects.create_user(email='bh060-personal-state@test.com')
        personal = Personal.objects.create(
            usuario=actor,
            nombre='Estado',
            apellido='Dinámico',
            rol='asistente',
            activo=True,
        )
        client = jwt_client(actor)

        canonical_before = client.get(reverse('turno-mi-agenda-laboral'))
        legacy_before = client.get(
            reverse('agenda-general'),
            {'personal_id': personal.pk},
        )
        personal.activo = False
        personal.save(update_fields=['activo'])
        canonical_after = client.get(reverse('turno-mi-agenda-laboral'))
        legacy_after = client.get(
            reverse('agenda-general'),
            {'personal_id': personal.pk},
        )

        self.assertEqual(canonical_before.status_code, status.HTTP_200_OK)
        self.assertEqual(legacy_before.status_code, status.HTTP_200_OK)
        self.assertEqual(canonical_after.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(
            legacy_after.status_code,
            {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND},
        )

    @patch('gestion.views.DiagnosticoCapilarViewSet._ejecutar_motor_diagnostico')
    def test_individual_permission_never_bypasses_skill_or_personal_state(
        self,
        diagnosis_engine,
    ):
        client_user = Usuario.objects.create_user(email='bh060-diagnosed@test.com')
        client_profile = Cliente.objects.create(usuario=client_user, activo=True)
        actor = user_with_role(
            'bh060-diagnosis-actor@test.com',
            BusinessRole.EMPLEADO,
        )
        actor.user_permissions.add(permission('create_diagnosis'))
        personal = Personal.objects.create(
            usuario=actor,
            nombre='Diagnóstico',
            apellido='Dinámico',
            rol='asistente',
            activo=True,
        )
        assignment = PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=Habilidad.objects.get(code='DIAGNOSTICO'),
            activa=True,
        )
        client = jwt_client(actor)
        url = reverse('diagnostico-capilar-list')

        allowed = client.post(url, {'cliente': client_profile.pk}, format='json')
        assignment.activa = False
        assignment.save(update_fields=['activa'])
        denied_skill = client.post(url, {'cliente': client_profile.pk}, format='json')
        assignment.activa = True
        assignment.save(update_fields=['activa'])
        personal.activo = False
        personal.save(update_fields=['activo'])
        denied_personal = client.post(
            url,
            {'cliente': client_profile.pk},
            format='json',
        )

        self.assertEqual(allowed.status_code, status.HTTP_201_CREATED)
        self.assertEqual(denied_skill.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(denied_personal.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(DiagnosticoCapilar.objects.count(), 1)
        diagnosis_engine.assert_called_once()


class LegacyOrderPaymentRegressionTests(CleanThreadLocalAPITestCase):
    audit_event = 'ORDER_MANUAL_PAYMENT_REGISTERED'

    def setUp(self):
        customer = Usuario.objects.create_user(email='bh060-order-client@test.com')
        self.customer = Cliente.objects.create(usuario=customer, activo=True)
        self.actor = Usuario.objects.create_user(email='bh060-order-cashier@test.com')
        self.actor.user_permissions.add(permission('register_payment'))
        self.client = jwt_client(self.actor)

    def create_order(self, suffix, state='PENDIENTE', total='50.00'):
        return OrdenCompra.objects.create(
            codigo=f'BH0606-{suffix}',
            cliente=self.customer,
            estado=state,
            total=Decimal(total),
        )

    def register(self, order, key, amount='50.00'):
        return self.client.post(
            reverse('orden-compra-registrar-pago', args=[order.pk]),
            {
                'monto': amount,
                'metodo_pago': 'EFECTIVO',
                'es_sena': False,
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_terminal_order_rejection_has_zero_payment_and_zero_success_event(self):
        order = self.create_order('TERMINAL', state='CANCELADO')

        response = self.register(order, 'terminal-order-payment')

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(Pago.objects.filter(orden=order).exists())
        self.assertFalse(
            Auditoria.objects.filter(
                tabla=self.audit_event,
                registro_id=order.pk,
            ).exists()
        )

    def test_retry_is_idempotent_and_overpayment_is_rejected(self):
        order = self.create_order('IDEMPOTENT')

        first = self.register(order, 'same-order-command', amount='30.00')
        retry = self.register(order, 'same-order-command', amount='30.00')
        overpayment = self.register(order, 'overpayment-command', amount='30.00')

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(overpayment.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Pago.objects.filter(orden=order).count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=self.audit_event,
                registro_id=order.pk,
            ).count(),
            1,
        )
