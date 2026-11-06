from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.legacy_order_payment_services import (
    ORDER_MANUAL_PAYMENT_REGISTERED,
    LegacyOrderPaymentError,
    register_legacy_order_payment,
)
from gestion.models import Auditoria, OrdenCompra, Pago
from usuarios.models import Cliente, Usuario


class LegacyOrderPaymentConcurrencyTests(TransactionTestCase):
    """Carreras aisladas con una conexión PostgreSQL por worker."""

    reset_sequences = True

    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        customer_user = Usuario.objects.create_user(
            email='bh060-concurrent-customer@test.com'
        )
        self.customer = Cliente.objects.create(usuario=customer_user, activo=True)
        self.actor = Usuario.objects.create_user(
            email='bh060-concurrent-cashier@test.com'
        )
        self.actor.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='gestion',
                codename='register_payment',
            )
        )
        self.order = OrdenCompra.objects.create(
            codigo='BH0606-CONCURRENT',
            cliente=self.customer,
            estado='PENDIENTE',
            total=Decimal('50.00'),
        )

    @staticmethod
    def run_two(first, second):
        barrier = threading.Barrier(2)

        def wrapped(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(wrapped, first),
                executor.submit(wrapped, second),
            )
            return [future.result(timeout=20) for future in futures]

    def worker(self, key, amount):
        actor_id = self.actor.pk
        order_id = self.order.pk
        occurred_at = timezone.now()

        def operation():
            try:
                result = register_legacy_order_payment(
                    order_id=order_id,
                    amount=Decimal(amount),
                    method='EFECTIVO',
                    occurred_at=occurred_at,
                    receipt=None,
                    is_deposit=False,
                    idempotency_key=key,
                    actor=Usuario.objects.get(pk=actor_id),
                )
                return 'payment', result.created, result.payment.pk, ''
            except LegacyOrderPaymentError as exc:
                return 'conflict', False, None, exc.code

        return operation

    def test_same_key_creates_one_payment_and_one_success_event(self):
        results = self.run_two(
            self.worker('bh060-same-key', '30.00'),
            self.worker('bh060-same-key', '30.00'),
        )

        payment = Pago.objects.get(orden=self.order)
        self.assertEqual({item[2] for item in results}, {payment.pk})
        self.assertEqual(sum(item[1] for item in results), 1)
        self.assertEqual(
            Auditoria.objects.filter(
                tabla=ORDER_MANUAL_PAYMENT_REGISTERED,
                registro_id=self.order.pk,
            ).count(),
            1,
        )

    def test_two_commands_cannot_overpay_order(self):
        results = self.run_two(
            self.worker('bh060-overpay-one', '30.00'),
            self.worker('bh060-overpay-two', '30.00'),
        )

        self.assertEqual(sum(item[0] == 'payment' for item in results), 1)
        self.assertEqual(
            sum(item[3] == 'ORDER_PAYMENT_OVERPAYMENT' for item in results),
            1,
        )
        self.assertEqual(Pago.objects.filter(orden=self.order).count(), 1)
