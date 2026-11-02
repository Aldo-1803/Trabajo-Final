from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from gestion.financial_resolution_services import (
    FinancialResolutionError,
    decide_financial_resolution,
    submit_financial_resolution_request,
)
from gestion.models import (
    FinancialResolutionDecision,
    FinancialResolutionEvent,
    FinancialResolutionRequest,
    OrdenCompra,
    Pago,
    PaymentReconciliationCase,
)
from usuarios.models import Cliente, Usuario


class FinancialResolutionConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.owner = Usuario.objects.create_user(email='f7-2-race-owner@test.com')
        self.client_profile = Cliente.objects.create(usuario=self.owner)
        self.reviewer = Usuario.objects.create_user(
            email='f7-2-race-reviewer@test.com'
        )
        self.reviewer.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='reconcile_external_payment',
        ))
        self.order = OrdenCompra.objects.create(
            codigo='F7-2-RACE-ORDER',
            cliente=self.client_profile,
            estado='PAGADO',
            total=Decimal('25.00'),
        )
        self.payment = Pago.objects.create(
            orden=self.order,
            monto=Decimal('25.00'),
            metodo_pago=Pago.Method.CASH,
            status=Pago.Status.RECONCILED,
        )
        self.case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=None,
            slot_hold=None,
            turno=None,
            order=self.order,
            provider_attempt=None,
            provider_event=None,
            case_type=PaymentReconciliationCase.Type.ORDER_FULFILLMENT_FAILED,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code='F7_2_CONCURRENT_DECISION',
            operation_key='f7-2-race-case',
            details={},
            created_by=self.reviewer,
            created_at=timezone.now(),
        )
        self.case.payments.add(self.payment)
        submit_financial_resolution_request(
            case_public_id=self.case.public_id,
            actor=self.owner,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REFUND,
            reason='Orden no cumplible.',
            amount=Decimal('25.00'),
            currency='ARS',
            idempotency_key='f7-2-race-request',
        )

    @staticmethod
    def run_concurrently(*operations):
        gate = threading.Barrier(len(operations))

        def wrapped(operation):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                try:
                    result = operation()
                    return 'ok', result.created
                except FinancialResolutionError as exc:
                    return exc.code, False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            futures = [executor.submit(wrapped, operation) for operation in operations]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_contradictory_final_decisions_persist_exactly_one(self):
        approve = lambda: decide_financial_resolution(
            case_public_id=self.case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
            rationale='Autorizar según evidencia.',
            authorized_amount=Decimal('25.00'),
            currency='ARS',
            policy_reference='RACE-POLICY',
            idempotency_key='f7-2-race-approve',
        )
        deny = lambda: decide_financial_resolution(
            case_public_id=self.case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.DENY_REFUND,
            rationale='Denegar según evidencia.',
            policy_reference='RACE-POLICY',
            idempotency_key='f7-2-race-deny',
        )

        results = self.run_concurrently(approve, deny)

        self.assertEqual(sum(code == 'ok' for code, _ in results), 1)
        self.assertEqual(FinancialResolutionDecision.objects.count(), 1)
        self.assertEqual(FinancialResolutionEvent.objects.count(), 2)
        resolution_request = FinancialResolutionRequest.objects.get()
        self.case.refresh_from_db()
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(
            resolution_request.status,
            FinancialResolutionRequest.Status.DECIDED,
        )
        self.assertEqual(self.case.status, PaymentReconciliationCase.Status.OPEN)
        self.assertEqual(self.order.estado, 'PAGADO')
        self.assertEqual(self.payment.status, Pago.Status.RECONCILED)
