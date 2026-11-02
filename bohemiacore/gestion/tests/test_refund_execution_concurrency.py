from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import Mock, patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from gestion.models import (
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
)
from gestion.refund_execution_services import execute_authorized_refund
from gestion.tests.test_refund_execution import RefundExecutionFixtureMixin
from usuarios.models import Usuario


class RefundExecutionConcurrencyTests(
    RefundExecutionFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Esta carrera requiere PostgreSQL real.')
        self.second_reviewer = Usuario.objects.create_user(
            email='f7-3-race-reviewer@test.com',
        )
        self.second_reviewer.user_permissions.add(self.permission)

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_two_operators_create_one_operation_and_one_external_call(self, factory):
        adapter = Mock()
        adapter.submit_refund.return_value = self.submitted()
        factory.return_value = adapter
        gate = threading.Barrier(2)

        def execute(actor, key):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return execute_authorized_refund(
                    case_public_id=self.refund_case.public_id,
                    actor=actor,
                    payment_public_id=self.provider_payment.public_id,
                    idempotency_key=key,
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(execute, self.reviewer, 'f7-3-race-one'),
                executor.submit(
                    execute,
                    self.second_reviewer,
                    'f7-3-race-two',
                ),
            ]
            results = [future.result(timeout=30) for future in futures]

        self.assertEqual(sum(result.provider_called for result in results), 1)
        self.assertEqual(adapter.submit_refund.call_count, 1)
        self.assertEqual(FinancialRefundOperation.objects.count(), 1)
        self.assertEqual(FinancialRefundOperationEvent.objects.count(), 3)
