from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.db import models
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from gestion.financial_resolution_services import (
    FinancialResolutionConflict,
    FinancialResolutionInvalid,
    FinancialResolutionPermissionDenied,
    decide_financial_resolution,
    submit_financial_resolution_request,
)
from gestion.models import (
    CompromisoStock,
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
    FinancialResolutionDecision,
    FinancialResolutionRequest,
    MovimientoStock,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    SlotHold,
    Turno,
)
from gestion.payment_providers import (
    PaymentProviderOutcomeUnknown,
    PaymentProviderRejected,
    ProviderOrderSnapshot,
    RefundSubmitted,
)
from gestion.refund_execution_services import (
    execute_authorized_refund,
    recover_refund_operation,
)
from gestion.tests.test_financial_resolution import FinancialResolutionFixtureMixin
from usuarios.models import Usuario


class RefundExecutionFixtureMixin(FinancialResolutionFixtureMixin):
    def setUp(self):
        super().setUp()
        self.provider_payment = self._provider_payment('base')
        self.refund_case = self.create_booking_case(
            payment=self.provider_payment,
            suffix='refund-execution',
        )
        submit_financial_resolution_request(
            case_public_id=self.refund_case.public_id,
            actor=self.user,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REFUND,
            reason='Pago de proveedor autorizado para devolución.',
            amount=Decimal('10.00'),
            currency='ARS',
            idempotency_key='f7-3-request',
        )
        decide_financial_resolution(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
            rationale='La política autoriza la devolución.',
            authorized_amount=Decimal('10.00'),
            currency='ARS',
            policy_reference='REFUNDS-F73',
            idempotency_key='f7-3-decision',
        )

    def _provider_payment(self, suffix, amount=Decimal('10.00')):
        attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=self.intent,
            amount=amount,
            currency='ARS',
            external_reference=f'bh:c1:booking:f73-{suffix}',
            client_idempotency_key=f'f73-attempt-{suffix}',
            provider_idempotency_key=f'f73-provider-attempt-{suffix}',
            request_fingerprint='a' * 64,
            provider_order_id=f'ORD-F73-{suffix}',
            provider_status='processed',
            created_by=self.user,
        )
        event = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.processed',
            event_id=f'EV-F73-{suffix}',
            provider_resource_id=attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=attempt,
            notification_snapshot={'id': f'EV-F73-{suffix}'},
            provider_snapshot={
                'id': attempt.provider_order_id,
                'refunds': [],
            },
        )
        now = timezone.now()
        return Pago.objects._create_external_from_service(
            payment_intent=self.intent,
            orden=None,
            turno=self.intent.confirmed_turno,
            monto=amount,
            currency='ARS',
            metodo_pago=Pago.Method.MERCADO_PAGO,
            purpose=Pago.Purpose.CONFIRMATION,
            status=Pago.Status.RECONCILED,
            transaccion_id=f'MERCADO_PAGO:PAY-F73-{suffix}',
            fecha_pago=now,
            recorded_at=now,
            recorded_by=None,
            reconciled_at=now,
            reconciled_by=None,
            manual_reference='',
            receipt_sha256='',
            idempotency_key=f'provider-payment-f73-{suffix}',
            terminal_reason='',
            es_sena=True,
            provider_code=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            provider_payment_id=f'PAY-F73-{suffix}',
            provider_attempt=attempt,
            provider_event=event,
            provider_occurred_at=now,
            provider_snapshot={'id': f'PAY-F73-{suffix}', 'status': 'processed'},
        )

    @staticmethod
    def submitted(operation=None):
        return RefundSubmitted(
            provider_order_id=(
                operation.provider_order_id if operation else 'ORD-F73-base'
            ),
            provider_refund_id='REF-F73-1',
            provider_transaction_id='PAY-F73-base',
            amount=Decimal('10.00'),
            provider_status='processed',
            provider_status_detail='partially_refunded',
            evidence={
                'order_id': 'ORD-F73-base',
                'order_status': 'processed',
                'order_status_detail': 'partially_refunded',
                'refund': {
                    'id': 'REF-F73-1',
                    'transaction_id': 'PAY-F73-base',
                    'amount': '10.00',
                    'status': 'processed',
                },
            },
        )

    def execute_url(self):
        return reverse(
            'payment-reconciliation-case-execute-authorized-refund',
            kwargs={'public_id': self.refund_case.public_id},
        )

    def operation_url(self):
        return reverse(
            'payment-reconciliation-case-refund-operation',
            kwargs={'public_id': self.refund_case.public_id},
        )

    def recovery_url(self):
        return reverse(
            'payment-reconciliation-case-recover-refund-operation',
            kwargs={'public_id': self.refund_case.public_id},
        )


class RefundExecutionTests(RefundExecutionFixtureMixin, TestCase):
    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_authorized_execution_commits_identity_before_http_and_stays_submitted(self, factory):
        adapter = Mock()

        def verify_durable(request):
            operation = FinancialRefundOperation.objects.get()
            self.assertEqual(operation.status, FinancialRefundOperation.Status.SUBMITTED)
            self.assertEqual(request.idempotency_key, operation.provider_idempotency_key)
            self.assertIsNotNone(operation.submission_started_at)
            return self.submitted(operation)

        adapter.submit_refund.side_effect = verify_durable
        factory.return_value = adapter
        before = self._invariant_snapshot()

        result = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-execute',
        )

        self.assertTrue(result.created)
        self.assertTrue(result.provider_called)
        self.assertEqual(result.operation.status, FinancialRefundOperation.Status.SUBMITTED)
        self.assertEqual(result.operation.external_refund_id, 'REF-F73-1')
        self.assertIsNone(result.operation.confirmed_at)
        self.assertEqual(self._invariant_snapshot(), before)
        self.assertEqual(FinancialRefundOperationEvent.objects.count(), 3)

    def _invariant_snapshot(self):
        return {
            'payment': Pago.objects.filter(pk=self.provider_payment.pk).values().get(),
            'case': PaymentReconciliationCase.objects.filter(
                pk=self.refund_case.pk
            ).values('status', 'resolved_at').get(),
            'intent': PaymentIntent.objects.filter(pk=self.intent.pk).values().get(),
            'hold': SlotHold.objects.filter(pk=self.hold.pk).values().get(),
            'turnos': list(Turno.objects.order_by('pk').values()),
            'orders': list(OrdenCompra.objects.order_by('pk').values()),
            'commitments': list(CompromisoStock.objects.order_by('pk').values()),
            'movements': list(MovimientoStock.objects.order_by('pk').values()),
        }

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_retry_same_or_new_operator_identity_never_calls_twice(self, factory):
        adapter = Mock()
        adapter.submit_refund.return_value = self.submitted()
        factory.return_value = adapter
        other = Usuario.objects.create_user(email='f7-3-other-reviewer@test.com')
        other.user_permissions.add(self.permission)

        first = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-retry',
        )
        retry = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-retry',
        )
        other_retry = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=other,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-other-key',
        )

        self.assertTrue(first.provider_called)
        self.assertFalse(retry.provider_called)
        self.assertFalse(other_retry.provider_called)
        self.assertEqual(adapter.submit_refund.call_count, 1)
        self.assertEqual(FinancialRefundOperation.objects.count(), 1)

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_timeout_or_ambiguous_result_is_unknown_without_blind_retry(self, factory):
        adapter = Mock()
        adapter.submit_refund.side_effect = PaymentProviderOutcomeUnknown(
            'Resultado ambiguo.'
        )
        factory.return_value = adapter

        first = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-timeout',
        )
        retry = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-timeout',
        )

        self.assertEqual(first.operation.status, FinancialRefundOperation.Status.UNKNOWN)
        self.assertFalse(retry.provider_called)
        self.assertEqual(adapter.submit_refund.call_count, 1)

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_definitive_provider_rejection_is_failed(self, factory):
        adapter = Mock()
        adapter.submit_refund.side_effect = PaymentProviderRejected('Rechazado.')
        factory.return_value = adapter

        result = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-rejected',
        )

        self.assertEqual(result.operation.status, FinancialRefundOperation.Status.FAILED)
        self.assertEqual(result.operation.error_code, 'PROVIDER_REJECTED')
        self.assertIsNone(result.operation.confirmed_at)

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_unknown_is_recovered_only_by_official_order_query(self, factory):
        submit_adapter = Mock()
        submit_adapter.submit_refund.side_effect = PaymentProviderOutcomeUnknown()
        factory.return_value = submit_adapter
        execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-recovery',
        )
        query_adapter = Mock()
        query_adapter.fetch_provider_order.return_value = ProviderOrderSnapshot(
            provider_order_id='ORD-F73-base',
            status='processed',
            status_detail='partially_refunded',
            external_reference='bh:c1:booking:f73-base',
            total_amount=Decimal('10.00'),
            total_paid_amount=Decimal('10.00'),
            currency='ARS',
            application_id='app',
            seller_id='seller',
            environment='sandbox',
            order_type='online',
            country_code='AR',
            transaction_statuses=('processed',),
            refunds=({
                'id': 'REF-RECOVERED',
                'transaction_id': 'PAY-F73-base',
                'amount': '10.00',
                'status': 'processed',
            },),
        )
        factory.return_value = query_adapter

        recovered = recover_refund_operation(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
        )

        self.assertTrue(recovered.uniquely_recovered)
        self.assertEqual(
            recovered.operation.status,
            FinancialRefundOperation.Status.SUBMITTED,
        )
        self.assertEqual(recovered.operation.external_refund_id, 'REF-RECOVERED')
        query_adapter.fetch_provider_order.assert_called_once_with('ORD-F73-base')
        query_adapter.submit_refund.assert_not_called()

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_non_unique_recovery_remains_unknown(self, factory):
        adapter = Mock()
        adapter.submit_refund.side_effect = PaymentProviderOutcomeUnknown()
        factory.return_value = adapter
        execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-ambiguous-recovery',
        )
        adapter.fetch_provider_order.return_value = ProviderOrderSnapshot(
            provider_order_id='ORD-F73-base',
            status='processed',
            status_detail='partially_refunded',
            external_reference='bh:c1:booking:f73-base',
            total_amount=Decimal('10.00'),
            total_paid_amount=Decimal('10.00'),
            currency='ARS',
            application_id='app',
            seller_id='seller',
            environment='sandbox',
            order_type='online',
            country_code='AR',
            transaction_statuses=('processed',),
            refunds=(),
        )

        result = recover_refund_operation(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
        )

        self.assertFalse(result.uniquely_recovered)
        self.assertEqual(result.operation.status, FinancialRefundOperation.Status.UNKNOWN)
        self.assertEqual(
            result.operation.error_code,
            'REFUND_NOT_UNIQUELY_RECOVERABLE',
        )
        self.assertEqual(adapter.submit_refund.call_count, 1)

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_recovery_rejects_refund_from_a_different_order(self, factory):
        adapter = Mock()
        adapter.submit_refund.side_effect = PaymentProviderOutcomeUnknown()
        factory.return_value = adapter
        execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-wrong-order-recovery',
        )
        adapter.fetch_provider_order.return_value = ProviderOrderSnapshot(
            provider_order_id='ORD-DIFFERENT',
            status='processed',
            status_detail='partially_refunded',
            external_reference='bh:c1:booking:other',
            total_amount=Decimal('10.00'),
            total_paid_amount=Decimal('10.00'),
            currency='ARS',
            application_id='app',
            seller_id='seller',
            environment='sandbox',
            order_type='online',
            country_code='AR',
            transaction_statuses=('processed',),
            refunds=({
                'id': 'REF-WRONG-ORDER',
                'transaction_id': 'PAY-F73-base',
                'amount': '10.00',
                'status': 'processed',
            },),
        )

        result = recover_refund_operation(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
        )

        self.assertFalse(result.uniquely_recovered)
        self.assertEqual(result.operation.status, FinancialRefundOperation.Status.UNKNOWN)
        self.assertFalse(
            result.operation.latest_evidence['order_identity_matches']
        )
        self.assertEqual(adapter.submit_refund.call_count, 1)

    def test_without_approval_manual_payment_or_incompatible_amount_is_rejected(self):
        undecided_case = self.create_booking_case(
            payment=self.provider_payment,
            suffix='not-approved',
        )
        with self.assertRaises(FinancialResolutionConflict) as no_approval:
            execute_authorized_refund(
                case_public_id=undecided_case.public_id,
                actor=self.reviewer,
                payment_public_id=self.provider_payment.public_id,
                idempotency_key='f7-3-not-approved',
            )
        self.assertEqual(no_approval.exception.code, 'FINANCIAL_REQUEST_REQUIRED')

        submit_financial_resolution_request(
            case_public_id=self.case.public_id,
            actor=self.user,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REFUND,
            reason='Devolución manual sujeta a contrato verificable.',
            amount=Decimal('10.00'),
            currency='ARS',
            idempotency_key='f7-3-manual-request',
        )
        decide_financial_resolution(
            case_public_id=self.case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
            rationale='Autorización que no inventa una ejecución manual.',
            authorized_amount=Decimal('10.00'),
            currency='ARS',
            policy_reference='MANUAL-REFUND-REVIEW',
            idempotency_key='f7-3-manual-decision',
        )
        with self.assertRaises(FinancialResolutionConflict) as manual:
            execute_authorized_refund(
                case_public_id=self.case.public_id,
                actor=self.reviewer,
                payment_public_id=self.payment.public_id,
                idempotency_key='f7-3-manual',
            )
        self.assertEqual(
            manual.exception.code,
            'MANUAL_REFUND_EXECUTION_UNSUPPORTED',
        )

        models.QuerySet.update(
            ProviderPaymentAttempt.objects.filter(
                pk=self.provider_payment.provider_attempt_id
            ),
            status=ProviderPaymentAttempt.Status.EXPIRED,
        )
        second = self._provider_payment('small', amount=Decimal('5.00'))
        self.refund_case.payments.add(second)
        with self.assertRaises(FinancialResolutionInvalid) as incompatible:
            execute_authorized_refund(
                case_public_id=self.refund_case.public_id,
                actor=self.reviewer,
                payment_public_id=second.public_id,
                idempotency_key='f7-3-too-small',
            )
        self.assertEqual(
            incompatible.exception.code,
            'REFUND_AMOUNT_EXCEEDS_PAYMENT',
        )

        models.QuerySet.update(
            ProviderPaymentAttempt.objects.filter(
                pk=second.provider_attempt_id
            ),
            status=ProviderPaymentAttempt.Status.EXPIRED,
        )
        expired = self._provider_payment('expired')
        models.QuerySet.update(
            Pago.objects.filter(pk=expired.pk),
            fecha_pago=timezone.now() - timedelta(days=181),
        )
        self.refund_case.payments.add(expired)
        with self.assertRaises(FinancialResolutionConflict) as outside_window:
            execute_authorized_refund(
                case_public_id=self.refund_case.public_id,
                actor=self.reviewer,
                payment_public_id=expired.public_id,
                idempotency_key='f7-3-expired-window',
            )
        self.assertEqual(
            outside_window.exception.code,
            'PROVIDER_REFUND_WINDOW_EXPIRED',
        )

    def test_client_staff_without_permission_and_inactive_reviewer_are_rejected(self):
        for actor in (self.user, self.staff_without_permission):
            with self.subTest(actor=actor.email):
                with self.assertRaises(FinancialResolutionPermissionDenied):
                    execute_authorized_refund(
                        case_public_id=self.refund_case.public_id,
                        actor=actor,
                        payment_public_id=self.provider_payment.public_id,
                        idempotency_key=f'f7-3-denied-{actor.pk}',
                    )
        inactive = Usuario.objects.create_user(
            email='f7-3-inactive@test.com',
            is_active=False,
        )
        inactive.user_permissions.add(self.permission)
        with self.assertRaises(FinancialResolutionPermissionDenied):
            execute_authorized_refund(
                case_public_id=self.refund_case.public_id,
                actor=inactive,
                payment_public_id=self.provider_payment.public_id,
                idempotency_key='f7-3-denied-inactive',
            )
        self.assertFalse(FinancialRefundOperation.objects.exists())

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_semantic_api_executes_and_queries_without_exposing_keys(self, factory):
        adapter = Mock()
        adapter.submit_refund.return_value = self.submitted()
        factory.return_value = adapter
        self.api.force_authenticate(self.reviewer)

        response = self.api.post(
            self.execute_url(),
            {'payment_public_id': str(self.provider_payment.public_id)},
            format='json',
            HTTP_IDEMPOTENCY_KEY='f7-3-api',
        )
        queried = self.api.get(self.operation_url())

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(queried.status_code, status.HTTP_200_OK)
        self.assertFalse(queried.data['financial_confirmation'])
        self.assertNotIn('provider_idempotency_key', queried.data)
        self.assertNotIn('client_idempotency_key', queried.data)
        self.assertNotIn('request_fingerprint', queried.data)
        self.assertEqual(queried.data['status'], 'SUBMITTED')

    def test_api_permission_blocks_client_and_plain_staff(self):
        payload = {'payment_public_id': str(self.provider_payment.public_id)}
        for actor in (self.user, self.staff_without_permission):
            with self.subTest(actor=actor.email):
                self.api.force_authenticate(actor)
                response = self.api.post(
                    self.execute_url(),
                    payload,
                    format='json',
                    HTTP_IDEMPOTENCY_KEY=f'f7-3-api-denied-{actor.pk}',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(FinancialRefundOperation.objects.exists())

    @patch('gestion.refund_execution_services.get_payment_provider')
    def test_previously_submitted_operation_is_not_sent_again(self, factory):
        adapter = Mock()
        adapter.submit_refund.return_value = self.submitted()
        factory.return_value = adapter
        first = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-submitted',
        )
        models.QuerySet.update(
            FinancialRefundOperation.objects.filter(pk=first.operation.pk),
            status=FinancialRefundOperation.Status.SUBMITTED,
        )

        second = execute_authorized_refund(
            case_public_id=self.refund_case.public_id,
            actor=self.reviewer,
            payment_public_id=self.provider_payment.public_id,
            idempotency_key='f7-3-submitted',
        )

        self.assertFalse(second.provider_called)
        self.assertEqual(adapter.submit_refund.call_count, 1)
