from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection, models
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from gestion.financial_case_closure_services import close_financial_case
from gestion.financial_resolution_services import (
    FinancialResolutionConflict,
    FinancialResolutionPermissionDenied,
    decide_financial_resolution,
    request_paid_order_cancellation,
    submit_financial_resolution_request,
)
from gestion.models import (
    Auditoria,
    CompromisoStock,
    FinancialAdjustment,
    FinancialCaseClosure,
    FinancialRefundOperation,
    FinancialRefundOperationEvent,
    FinancialResolutionDecision,
    FinancialResolutionEvent,
    FinancialResolutionRequest,
    MovimientoStock,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    SlotHold,
    Turno,
)
from gestion.order_inventory_services import (
    OrderInventoryConflict,
    apply_order_inventory_effect,
    create_order_stock_commitments,
)
from gestion.payment_confirmation_services import (
    approve_payment_intent_and_confirm_booking,
)
from gestion.provider_reconciliation_services import (
    reconcile_verified_provider_event,
)
from gestion.tests.test_financial_resolution import FinancialResolutionFixtureMixin
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from gestion.tests.test_provider_reconciliation import (
    provider_snapshot,
    verified_event,
)
from usuarios.models import Usuario


class FinancialFactHelpers:
    def provider_payment(self, *, suffix, amount, intent=None, order=None):
        context = (
            ProviderPaymentAttempt.Context.BOOKING
            if intent is not None
            else ProviderPaymentAttempt.Context.ORDER
        )
        attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=context,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=intent,
            order=order,
            amount=amount,
            currency='ARS',
            external_reference=f'bh:c1:{context.lower()}:f75-{suffix}',
            client_idempotency_key=f'f75-attempt-client-{suffix}',
            provider_idempotency_key=f'f75-attempt-provider-{suffix}',
            request_fingerprint='5' * 64,
            provider_order_id=f'ORD-F75-{suffix}',
            provider_status='processed',
            reconciliation_status=ProviderPaymentAttempt.ReconciliationStatus.APPLIED,
            created_by=self.user,
        )
        event = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.processed',
            event_id=f'EV-F75-ORIGIN-{suffix}',
            provider_resource_id=attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=attempt,
            notification_snapshot={'id': f'EV-F75-ORIGIN-{suffix}'},
            provider_snapshot={'id': attempt.provider_order_id},
            reconciliation_status=ProviderEvent.ReconciliationStatus.APPLIED,
            reconciled_at=timezone.now(),
            reconciliation_code='PAYMENT_RECONCILED',
        )
        now = timezone.now()
        return Pago.objects._create_external_from_service(
            payment_intent=intent,
            orden=order,
            turno=(intent.confirmed_turno if intent is not None else None),
            monto=amount,
            currency='ARS',
            metodo_pago=Pago.Method.MERCADO_PAGO,
            purpose=Pago.Purpose.CONFIRMATION,
            status=Pago.Status.RECONCILED,
            transaccion_id=f'MERCADO_PAGO:PAY-F75-{suffix}',
            fecha_pago=now,
            recorded_at=now,
            recorded_by=None,
            reconciled_at=now,
            reconciled_by=None,
            manual_reference='',
            receipt_sha256='',
            idempotency_key=f'provider-payment-f75-{suffix}',
            terminal_reason='',
            es_sena=intent is not None,
            provider_code=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            provider_payment_id=f'PAY-F75-{suffix}',
            provider_attempt=attempt,
            provider_event=event,
            provider_occurred_at=now,
            provider_snapshot={'id': f'PAY-F75-{suffix}', 'status': 'processed'},
        )

    def confirm_refund(self, *, decision, payment, suffix):
        now = timezone.now()
        operation = FinancialRefundOperation.objects._create_from_service(
            decision=decision,
            payment=payment,
            amount=decision.authorized_amount,
            currency=decision.currency,
            payment_method=payment.metodo_pago,
            provider=FinancialRefundOperation.Provider.MERCADO_PAGO,
            status=FinancialRefundOperation.Status.CONFIRMED,
            client_idempotency_key=f'f75-operation-{suffix}',
            provider_idempotency_key=f'f75-provider-operation-{suffix}',
            request_fingerprint='6' * 64,
            provider_order_id=payment.provider_attempt.provider_order_id,
            provider_transaction_id=payment.provider_payment_id,
            external_refund_id=f'REF-F75-{suffix}',
            provider_status='processed',
            provider_status_detail='refunded',
            baseline_refund_ids=[],
            latest_evidence={'source': 'F7.5_TEST'},
            created_by=self.reviewer,
            created_at=now,
            response_received_at=now,
            confirmed_at=now,
        )
        FinancialRefundOperationEvent.objects._create_from_service(
            operation=operation,
            event_type=FinancialRefundOperationEvent.Type.CONFIRMED,
            actor=None,
            operation_key=f'f75-refund-confirmed-{suffix}',
            payload={'source': 'VERIFIED_PROVIDER_EVENT'},
            created_at=now,
        )
        event = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.refunded',
            event_id=f'EV-F75-REFUND-{suffix}',
            provider_resource_id=payment.provider_attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=payment.provider_attempt,
            notification_snapshot={'id': f'EV-F75-REFUND-{suffix}'},
            provider_snapshot={'id': payment.provider_attempt.provider_order_id},
            reconciliation_status=ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED,
            reconciled_at=now,
            reconciliation_code='POST_PAYMENT_CHANGE',
        )
        adjustment = FinancialAdjustment.objects._create_from_service(
            payment=payment,
            adjustment_type=FinancialAdjustment.Type.REFUND,
            effect=FinancialAdjustment.Effect.DEBIT,
            amount=decision.authorized_amount,
            currency=decision.currency,
            provider=FinancialAdjustment.Provider.MERCADO_PAGO,
            external_adjustment_id=f'REF-F75-{suffix}',
            provider_status='processed',
            provider_event=event,
            refund_operation=operation,
            effective_at=now,
            evidence={'source': 'VERIFIED_PROVIDER_EVENT'},
            created_at=now,
        )
        return operation, adjustment

    def external_adjustment(self, *, payment, suffix, adjustment_type):
        now = timezone.now()
        event = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action=f'order.{adjustment_type.lower()}',
            event_id=f'EV-F75-{adjustment_type}-{suffix}',
            provider_resource_id=payment.provider_attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=payment.provider_attempt,
            notification_snapshot={'id': f'EV-F75-{adjustment_type}-{suffix}'},
            provider_snapshot={'id': payment.provider_attempt.provider_order_id},
            reconciliation_status=ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED,
            reconciled_at=now,
            reconciliation_code='POST_PAYMENT_CHANGE',
        )
        adjustment = FinancialAdjustment.objects._create_from_service(
            payment=payment,
            adjustment_type=adjustment_type,
            effect=FinancialAdjustment.Effect.DEBIT,
            amount=payment.monto,
            currency=payment.currency,
            provider=FinancialAdjustment.Provider.MERCADO_PAGO,
            external_adjustment_id=f'{adjustment_type}-F75-{suffix}',
            provider_status='processed',
            provider_event=event,
            effective_at=now,
            evidence={'source': 'VERIFIED_PROVIDER_EVENT'},
            created_at=now,
        )
        return event, adjustment

    def create_order_case(self, *, order, payment, suffix, case_type, event=None):
        case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=None,
            slot_hold=None,
            turno=None,
            order=order,
            provider_attempt=payment.provider_attempt,
            provider_event=event,
            case_type=case_type,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code=f'F75_{suffix.upper()}',
            operation_key=f'f75-order-case-{suffix}',
            details={'source': 'F7_5_TEST'},
            created_by=self.reviewer,
            created_at=timezone.now(),
        )
        case.payments.add(payment)
        return case


class FinancialCaseClosureTests(FinancialResolutionFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.case = self.create_booking_case(
            payment=self.payment,
            suffix='closure',
            case_type=PaymentReconciliationCase.Type.BOOKING_CONFIRMATION_FAILED,
        )
        submit_financial_resolution_request(
            case_public_id=self.case.public_id,
            actor=self.reviewer,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REVIEW_PAYMENT,
            reason='Revisión concluida sin cambio financiero.',
            idempotency_key='f75-request',
        )
        decide_financial_resolution(
            case_public_id=self.case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE,
            rationale='La evidencia acredita que no corresponde mover dinero.',
            idempotency_key='f75-decision',
        )

    def close(self, **overrides):
        values = {
            'case_public_id': self.case.public_id,
            'actor': self.reviewer,
            'rationale': 'Resultado verificado y sin efectos pendientes.',
            'result': FinancialCaseClosure.Result.NO_FINANCIAL_CHANGE,
            'idempotency_key': 'f75-close',
        }
        values.update(overrides)
        return close_financial_case(**values)

    def test_close_is_audited_idempotent_and_preserves_booking(self):
        before = (self.intent.confirmed_turno_id, self.hold.state, Pago.objects.count())
        first = self.close()
        retry = self.close()

        self.case.refresh_from_db()
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        self.assertTrue(first.changed)
        self.assertFalse(retry.changed)
        self.assertEqual(FinancialCaseClosure.objects.count(), 1)
        self.assertEqual(self.case.status, PaymentReconciliationCase.Status.RESOLVED)
        self.assertEqual(
            (self.intent.confirmed_turno_id, self.hold.state, Pago.objects.count()),
            before,
        )
        self.assertTrue(FinancialResolutionEvent.objects.filter(
            event_type=FinancialResolutionEvent.Type.CASE_CLOSED,
        ).exists())
        self.assertTrue(Auditoria.objects.filter(
            tabla='FINANCIAL_CASE_CLOSED',
            usuario=self.reviewer,
        ).exists())

    def test_late_payment_denial_closes_without_resurrecting_booking(self):
        case = self.create_booking_case(
            payment=self.payment,
            suffix='late-denied',
            case_type=PaymentReconciliationCase.Type.LATE_PAYMENT,
        )
        models.QuerySet.update(
            SlotHold.objects.filter(pk=self.hold.pk),
            state=SlotHold.State.RELEASED,
            released_at=timezone.now(),
            release_reason=SlotHold.ReleaseReason.PAYMENT_INTENT_EXPIRED,
        )
        models.QuerySet.update(
            PaymentIntent.objects.filter(pk=self.intent.pk),
            status=PaymentIntent.Status.EXPIRED,
            terminal_at=timezone.now(),
            terminal_reason='LATE_PAYMENT_TEST',
        )
        submit_financial_resolution_request(
            case_public_id=case.public_id,
            actor=self.reviewer,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REFUND,
            reason='Pago tardío revisado.',
            amount=self.payment.monto,
            currency=self.payment.currency,
            idempotency_key='f75-late-request',
        )
        decide_financial_resolution(
            case_public_id=case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.DENY_REFUND,
            rationale='Denegación fundada por política documentada.',
            policy_reference='LATE-PAYMENT-DENIAL',
            idempotency_key='f75-late-denial',
        )
        turno_count = Turno.objects.count()

        result = close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='La denegación final conserva el pago tardío sin reserva.',
            result=FinancialCaseClosure.Result.REFUND_DENIED,
            idempotency_key='f75-late-close',
        )

        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertIsNone(self.intent.confirmed_turno_id)
        self.assertNotEqual(self.hold.state, SlotHold.State.ACTIVE)
        self.assertEqual(Turno.objects.count(), turno_count)
        self.assertFalse(FinancialAdjustment.objects.exists())

    def test_new_verified_event_blocks_close(self):
        attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=self.intent,
            amount=Decimal('10.00'),
            currency='ARS',
            external_reference='bh:c1:booking:f75-new-event',
            client_idempotency_key='f75-new-event-client',
            provider_idempotency_key='f75-new-event-provider',
            request_fingerprint='8' * 64,
            provider_order_id='ORD-F75-NEW-EVENT',
            created_by=self.user,
        )
        ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.updated',
            event_id='EV-F75-UNEVALUATED',
            provider_resource_id=attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=attempt,
        )
        with self.assertRaises(FinancialResolutionConflict) as evidence:
            self.close()
        self.assertEqual(evidence.exception.code, 'UNEVALUATED_PROVIDER_EVENT')

    def test_domain_and_api_require_effective_permission(self):
        for actor in (self.user, self.staff_without_permission):
            with self.subTest(actor=actor.email):
                with self.assertRaises(FinancialResolutionPermissionDenied):
                    self.close(actor=actor, idempotency_key=f'denied-{actor.pk}')
                self.api.force_authenticate(actor)
                response = self.api.post(
                    reverse(
                        'payment-reconciliation-case-close-financial-case',
                        kwargs={'public_id': self.case.public_id},
                    ),
                    {
                        'rationale': 'Intento sin permiso efectivo.',
                        'result': FinancialCaseClosure.Result.NO_FINANCIAL_CHANGE,
                    },
                    format='json',
                    HTTP_IDEMPOTENCY_KEY=f'api-denied-{actor.pk}',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        inactive = Usuario.objects.create_user(
            email='f75-inactive-reviewer@test.com',
            is_active=False,
        )
        inactive.user_permissions.add(self.permission)
        with self.assertRaises(FinancialResolutionPermissionDenied):
            self.close(actor=inactive, idempotency_key='f75-inactive-close')

    def test_semantic_api_closes_retries_and_projects_closure(self):
        self.api.force_authenticate(self.reviewer)
        url = reverse(
            'payment-reconciliation-case-close-financial-case',
            kwargs={'public_id': self.case.public_id},
        )
        payload = {
            'rationale': 'Cierre semántico verificado por API.',
            'result': FinancialCaseClosure.Result.NO_FINANCIAL_CHANGE,
        }

        first = self.api.post(
            url,
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='f75-api-close',
        )
        retry = self.api.post(
            url,
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='f75-api-close',
        )
        detail = self.api.get(
            reverse(
                'payment-reconciliation-case-detail',
                kwargs={'public_id': self.case.public_id},
            )
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['closure']['public_id'], first.data['public_id'])


class BookingRefundClosureTests(FinancialFactHelpers, FinancialResolutionFixtureMixin, TestCase):
    def prepare_cancelled_booking(self, *, authorized_amount, suffix):
        provider_payment = self.provider_payment(
            suffix=suffix,
            amount=Decimal('10.00'),
            intent=self.intent,
        )
        self.register(
            amount=Decimal('10.00'),
            idempotency_key=f'f75-threshold-{suffix}',
        )
        approve_payment_intent_and_confirm_booking(
            intent_id=self.intent.pk,
            actor=self.reviewer,
        )
        self.intent.refresh_from_db()
        turno = self.intent.confirmed_turno
        models.QuerySet.update(
            Turno.objects.filter(pk=turno.pk),
            estado=Turno.Estado.CANCELADO,
        )
        case = self.create_booking_case(
            payment=provider_payment,
            suffix=suffix,
            case_type=PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT,
        )
        submit_financial_resolution_request(
            case_public_id=case.public_id,
            actor=self.reviewer,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REFUND,
            reason='Turno cancelado con devolución a verificar.',
            amount=authorized_amount,
            currency='ARS',
            idempotency_key=f'f75-booking-request-{suffix}',
        )
        decision = decide_financial_resolution(
            case_public_id=case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
            rationale='La política autoriza la devolución confirmada.',
            authorized_amount=authorized_amount,
            currency='ARS',
            policy_reference='BOOKING-CANCELLATION-F75',
            idempotency_key=f'f75-booking-decision-{suffix}',
        ).decision
        self.confirm_refund(
            decision=decision,
            payment=provider_payment,
            suffix=suffix,
        )
        return case, provider_payment, turno

    def test_cancelled_turno_confirmed_refund_preserves_history(self):
        case, payment, turno = self.prepare_cancelled_booking(
            authorized_amount=Decimal('10.00'),
            suffix='booking-total',
        )
        intent_id = self.intent.pk
        hold_id = self.hold.pk
        turno_count = Turno.objects.count()

        close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Refund verificado; el Turno permanece cancelado.',
            result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
            idempotency_key='f75-booking-total-close',
        )

        turno.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.CANCELADO)
        self.assertEqual(payment.payment_intent_id, intent_id)
        self.assertEqual(self.intent.slot_hold_id, hold_id)
        self.assertEqual(Turno.objects.count(), turno_count)

    def test_cancelled_turno_partial_refund_does_not_recreate_booking(self):
        case, _, turno = self.prepare_cancelled_booking(
            authorized_amount=Decimal('5.00'),
            suffix='booking-partial',
        )
        before = (Turno.objects.count(), SlotHold.objects.count())

        close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Refund parcial confirmado sin reprogramación automática.',
            result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
            idempotency_key='f75-booking-partial-close',
        )

        turno.refresh_from_db()
        self.assertEqual(turno.estado, Turno.Estado.CANCELADO)
        self.assertEqual((Turno.objects.count(), SlotHold.objects.count()), before)


class OrderClosureFixture(FinancialFactHelpers, OrderInventoryFixtureMixin):
    def setUp(self):
        super().setUp()
        self.permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='reconcile_external_payment',
        )
        self.reviewer = Usuario.objects.create_user(email='f75-reviewer@test.com')
        self.reviewer.user_permissions.add(self.permission)

    def paid_order(self, suffix):
        self.receive(self.product, 3, f'f75-{suffix}')
        order = self.make_order(
            [(self.product, 1)],
            state='PAGADO',
            code=f'F75-{suffix}',
        )
        create_order_stock_commitments(order.pk)
        payment = self.provider_payment(
            suffix=suffix,
            amount=order.total,
            order=order,
        )
        return order, payment

    def cancellation_refund(self, *, order, payment, amount, suffix):
        result, _ = request_paid_order_cancellation(
            order_id=order.pk,
            actor=self.reviewer,
            reason='Cancelación financiera explícita.',
            amount=amount,
            currency='ARS',
            idempotency_key=f'f75-order-request-{suffix}',
        )
        decision = decide_financial_resolution(
            case_public_id=result.resolution_request.case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
            rationale='Devolución autorizada bajo política documentada.',
            authorized_amount=amount,
            currency='ARS',
            policy_reference='ORDER-CANCELLATION-F75',
            idempotency_key=f'f75-order-decision-{suffix}',
        ).decision
        operation, adjustment = self.confirm_refund(
            decision=decision,
            payment=payment,
            suffix=suffix,
        )
        return result.resolution_request.case, decision, operation, adjustment


class OrderFinancialCaseClosureTests(OrderClosureFixture, TestCase):
    def test_total_refund_cancels_and_releases_once_without_sale_movement(self):
        order, payment = self.paid_order('TOTAL')
        case, _, _, _ = self.cancellation_refund(
            order=order,
            payment=payment,
            amount=order.total,
            suffix='order-total',
        )

        first = close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Refund total y neto cero verificados.',
            result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
            idempotency_key='f75-order-total-close',
        )
        retry = close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Refund total y neto cero verificados.',
            result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
            idempotency_key='f75-order-total-close',
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=order)
        self.assertTrue(first.changed)
        self.assertFalse(retry.changed)
        self.assertEqual(order.estado, 'CANCELADO')
        self.assertEqual(commitment.estado, CompromisoStock.State.RELEASED)
        self.assertEqual(self.product.stock_real, 3)
        self.assertEqual(self.product.stock_comprometido, 0)
        self.assertFalse(MovimientoStock.objects.filter(
            reference_type='ORDEN_COMPRA',
            reference_id=str(order.pk),
        ).exists())

    def test_partial_refund_keeps_paid_order_and_active_commitment(self):
        order, payment = self.paid_order('PARTIAL')
        case, _, _, _ = self.cancellation_refund(
            order=order,
            payment=payment,
            amount=Decimal('40.00'),
            suffix='order-partial',
        )

        result = close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Refund parcial confirmado; no cancela la orden completa.',
            result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
            idempotency_key='f75-order-partial-close',
        )

        order.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=order)
        self.assertEqual(result.closure.commercial_effect, 'PARTIAL_REFUND_ORDER_UNCHANGED')
        self.assertEqual(order.estado, 'PAGADO')
        self.assertEqual(commitment.estado, CompromisoStock.State.ACTIVE)
        self.assertFalse(MovimientoStock.objects.filter(
            reference_id=str(order.pk),
        ).exists())

    def test_completed_order_refund_never_restocks_or_reverts_delivery(self):
        order, payment = self.paid_order('COMPLETED')
        apply_order_inventory_effect(order.pk, actor=self.stock_actor)
        self.product.refresh_from_db()
        before_stock = self.product.stock_real
        movement_count = MovimientoStock.objects.filter(
            reference_id=str(order.pk)
        ).count()
        case = self.create_order_case(
            order=order,
            payment=payment,
            suffix='completed-refund',
            case_type=PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
        )
        submit_financial_resolution_request(
            case_public_id=case.public_id,
            actor=self.reviewer,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REFUND,
            reason='Refund posterior a entrega.',
            amount=order.total,
            currency='ARS',
            idempotency_key='f75-completed-request',
        )
        decision = decide_financial_resolution(
            case_public_id=case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
            rationale='Refund financiero; retorno físico fuera de alcance.',
            authorized_amount=order.total,
            currency='ARS',
            policy_reference='COMPLETED-RETURN-DEFERRED',
            idempotency_key='f75-completed-decision',
        ).decision
        self.confirm_refund(decision=decision, payment=payment, suffix='completed')

        result = close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Se conserva entrega y se difiere retorno físico.',
            result=FinancialCaseClosure.Result.PHYSICAL_RETURN_DEFERRED,
            idempotency_key='f75-completed-close',
        )

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.estado, 'COMPLETADO')
        self.assertEqual(self.product.stock_real, before_stock)
        self.assertEqual(CompromisoStock.objects.get(orden=order).estado, CompromisoStock.State.CONSUMED)
        self.assertEqual(MovimientoStock.objects.filter(reference_id=str(order.pk)).count(), movement_count)
        self.assertEqual(
            result.closure.commercial_effect,
            'COMPLETED_ORDER_UNCHANGED_RETURN_DEFERRED',
        )

    def test_chargeback_stays_paid_and_blocks_delivery_even_after_review(self):
        order, payment = self.paid_order('CHARGEBACK')
        event, _ = self.external_adjustment(
            payment=payment,
            suffix='chargeback',
            adjustment_type=FinancialAdjustment.Type.CHARGEBACK,
        )
        case = self.create_order_case(
            order=order,
            payment=payment,
            suffix='chargeback',
            case_type=PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
            event=event,
        )
        submit_financial_resolution_request(
            case_public_id=case.public_id,
            actor=self.reviewer,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REVIEW_EXTERNAL_ADJUSTMENT,
            reason='Contracargo confirmado sujeto a revisión.',
            idempotency_key='f75-chargeback-request',
        )
        decide_financial_resolution(
            case_public_id=case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT,
            rationale='Se reconoce el contracargo sin cancelar automáticamente.',
            idempotency_key='f75-chargeback-decision',
        )
        with self.assertRaises(OrderInventoryConflict):
            apply_order_inventory_effect(order.pk, actor=self.stock_actor)

        close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Contracargo registrado; entrega sigue bloqueada por saldo.',
            result=FinancialCaseClosure.Result.EXTERNAL_ADJUSTMENT_ACKNOWLEDGED,
            idempotency_key='f75-chargeback-close',
        )
        with self.assertRaises(OrderInventoryConflict) as blocked:
            apply_order_inventory_effect(order.pk, actor=self.stock_actor)

        order.refresh_from_db()
        self.assertEqual(blocked.exception.code, 'ORDER_FINANCIAL_REVIEW_BLOCKS_DELIVERY')
        self.assertEqual(order.estado, 'PAGADO')
        self.assertEqual(CompromisoStock.objects.get(orden=order).estado, CompromisoStock.State.ACTIVE)

    def test_provisional_dispute_blocks_only_while_case_is_open(self):
        order, payment = self.paid_order('PROVISIONAL')
        event = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.dispute_opened',
            event_id='EV-F75-PROVISIONAL',
            provider_resource_id=payment.provider_attempt.provider_order_id,
            status=ProviderEvent.Status.VERIFIED,
            attempt=payment.provider_attempt,
            reconciliation_status=ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED,
            reconciled_at=timezone.now(),
            reconciliation_code='PROVISIONAL_DISPUTE',
        )
        case = self.create_order_case(
            order=order,
            payment=payment,
            suffix='provisional',
            case_type=PaymentReconciliationCase.Type.EXTERNAL_PAYMENT_REVIEW,
            event=event,
        )
        submit_financial_resolution_request(
            case_public_id=case.public_id,
            actor=self.reviewer,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REVIEW_EXTERNAL_ADJUSTMENT,
            reason='Disputa provisional sin débito terminal.',
            idempotency_key='f75-provisional-request',
        )
        decide_financial_resolution(
            case_public_id=case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT,
            rationale='La disputa no representa dinero definitivamente perdido.',
            idempotency_key='f75-provisional-decision',
        )
        with self.assertRaises(OrderInventoryConflict):
            apply_order_inventory_effect(order.pk, actor=self.stock_actor)

        close_financial_case(
            case_public_id=case.public_id,
            actor=self.reviewer,
            rationale='Disputa evaluada sin ajuste financiero confirmado.',
            result=FinancialCaseClosure.Result.EXTERNAL_ADJUSTMENT_ACKNOWLEDGED,
            idempotency_key='f75-provisional-close',
        )
        delivered = apply_order_inventory_effect(order.pk, actor=self.stock_actor)
        self.assertTrue(delivered.applied)

    def test_new_provider_incidence_after_closure_opens_a_new_case(self):
        order, payment = self.paid_order('POST-CLOSE-EVENT')
        refund = {
            'id': 'REF-F75-POST-CLOSE',
            'transaction_id': payment.provider_payment_id,
            'amount': '10.00',
            'status': 'processed',
            'last_updated_date': timezone.now().isoformat(),
        }
        first_event = verified_event(
            payment.provider_attempt,
            event_id='f75-post-close-first',
            snapshot=provider_snapshot(
                payment.provider_attempt,
                payment_id=payment.provider_payment_id,
                refunds=[refund],
                order_status='refunded',
            ),
        )
        first_result = reconcile_verified_provider_event(first_event.pk)
        first_case = first_result.reconciliation_case
        submit_financial_resolution_request(
            case_public_id=first_case.public_id,
            actor=self.reviewer,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REVIEW_EXTERNAL_ADJUSTMENT,
            reason='Refund externo revisado.',
            idempotency_key='f75-post-close-request',
        )
        decide_financial_resolution(
            case_public_id=first_case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT,
            rationale='Se reconoce el refund externo sin cancelar la orden.',
            idempotency_key='f75-post-close-decision',
        )
        close_financial_case(
            case_public_id=first_case.public_id,
            actor=self.reviewer,
            rationale='Primera incidencia externa completamente evaluada.',
            result=FinancialCaseClosure.Result.EXTERNAL_ADJUSTMENT_ACKNOWLEDGED,
            idempotency_key='f75-post-close-close',
        )

        second_event = verified_event(
            payment.provider_attempt,
            event_id='f75-post-close-second',
            snapshot=provider_snapshot(
                payment.provider_attempt,
                payment_id=payment.provider_payment_id,
                refunds=[refund],
                order_status='refunded',
                updated_at=timezone.now(),
            ),
        )
        second_result = reconcile_verified_provider_event(second_event.pk)

        first_case.refresh_from_db()
        self.assertEqual(first_case.status, PaymentReconciliationCase.Status.RESOLVED)
        self.assertNotEqual(second_result.reconciliation_case.pk, first_case.pk)
        self.assertEqual(
            second_result.reconciliation_case.status,
            PaymentReconciliationCase.Status.OPEN,
        )
        self.assertEqual(FinancialAdjustment.objects.count(), 1)

    def test_amount_and_currency_mismatch_block_close(self):
        order, payment = self.paid_order('MISMATCH')
        case, _, _, adjustment = self.cancellation_refund(
            order=order,
            payment=payment,
            amount=order.total,
            suffix='order-mismatch',
        )
        original_amount = adjustment.amount
        models.QuerySet.update(
            FinancialAdjustment.objects.filter(pk=adjustment.pk),
            amount=Decimal('99.00'),
        )
        with self.assertRaises(FinancialResolutionConflict) as amount_error:
            close_financial_case(
                case_public_id=case.public_id,
                actor=self.reviewer,
                rationale='No debe cerrar con importe divergente.',
                result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
                idempotency_key='f75-mismatch-amount-close',
            )
        self.assertEqual(amount_error.exception.code, 'REFUND_ADJUSTMENT_MISMATCH')
        models.QuerySet.update(
            FinancialAdjustment.objects.filter(pk=adjustment.pk),
            amount=original_amount,
            currency='USD',
        )
        with self.assertRaises(FinancialResolutionConflict) as currency_error:
            close_financial_case(
                case_public_id=case.public_id,
                actor=self.reviewer,
                rationale='No debe cerrar con moneda divergente.',
                result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
                idempotency_key='f75-mismatch-currency-close',
            )
        self.assertEqual(currency_error.exception.code, 'REFUND_ADJUSTMENT_MISMATCH')

    def test_unresolved_refund_operation_blocks_close(self):
        order, payment = self.paid_order('UNKNOWN')
        case, _, operation, _ = self.cancellation_refund(
            order=order,
            payment=payment,
            amount=order.total,
            suffix='order-unknown',
        )
        for operation_status in (
            FinancialRefundOperation.Status.PENDING,
            FinancialRefundOperation.Status.SUBMITTED,
            FinancialRefundOperation.Status.UNKNOWN,
        ):
            with self.subTest(operation_status=operation_status):
                models.QuerySet.update(
                    FinancialRefundOperation.objects.filter(pk=operation.pk),
                    status=operation_status,
                    confirmed_at=None,
                )
                with self.assertRaises(FinancialResolutionConflict) as unresolved:
                    close_financial_case(
                        case_public_id=case.public_id,
                        actor=self.reviewer,
                        rationale='Una operación no terminal no permite cerrar.',
                        result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
                        idempotency_key=f'f75-{operation_status.lower()}-close',
                    )
                self.assertEqual(
                    unresolved.exception.code,
                    'REFUND_OPERATION_UNRESOLVED',
                )


class FinancialCaseClosureConcurrencyTests(OrderClosureFixture, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Estas carreras requieren PostgreSQL real.')
        self.order, self.payment = self.paid_order('RACE')
        self.case, _, _, _ = self.cancellation_refund(
            order=self.order,
            payment=self.payment,
            amount=self.order.total,
            suffix='order-race',
        )

    @staticmethod
    def threaded(callable_):
        close_old_connections()
        try:
            return callable_()
        finally:
            close_old_connections()

    def test_duplicate_close_and_two_operators_serialize(self):
        gate = threading.Barrier(2)

        def close():
            gate.wait(timeout=10)
            return close_financial_case(
                case_public_id=self.case.public_id,
                actor=self.reviewer,
                rationale='Cierre concurrente con refund total verificado.',
                result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
                idempotency_key='f75-race-same-close',
            ).changed

        with ThreadPoolExecutor(max_workers=2) as executor:
            changed = [
                future.result(timeout=30)
                for future in (
                    executor.submit(self.threaded, close),
                    executor.submit(self.threaded, close),
                )
            ]
        self.assertEqual(sorted(changed), [False, True])
        self.assertEqual(FinancialCaseClosure.objects.filter(case=self.case).count(), 1)
        self.assertEqual(CompromisoStock.objects.get(orden=self.order).estado, CompromisoStock.State.RELEASED)

    def test_two_different_operators_create_exactly_one_closure(self):
        other = Usuario.objects.create_user(email='f75-other-reviewer@test.com')
        other.user_permissions.add(self.permission)
        gate = threading.Barrier(2)

        def close(actor, suffix):
            gate.wait(timeout=10)
            try:
                close_financial_case(
                    case_public_id=self.case.public_id,
                    actor=actor,
                    rationale=f'Cierre concurrente del operador {suffix}.',
                    result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
                    idempotency_key=f'f75-operator-{suffix}',
                )
                return 'closed'
            except FinancialResolutionConflict as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                future.result(timeout=30)
                for future in (
                    executor.submit(self.threaded, lambda: close(self.reviewer, 'a')),
                    executor.submit(self.threaded, lambda: close(other, 'b')),
                )
            ]

        self.assertEqual(outcomes.count('closed'), 1)
        self.assertEqual(FinancialCaseClosure.objects.filter(case=self.case).count(), 1)
        self.assertEqual(CompromisoStock.objects.get(orden=self.order).estado, CompromisoStock.State.RELEASED)

    def test_close_delivery_and_reconciliation_race_remains_consistent(self):
        event = verified_event(
            self.payment.provider_attempt,
            event_id='f75-race-new-provider-event',
            snapshot=provider_snapshot(
                self.payment.provider_attempt,
                payment_id=self.payment.provider_payment_id,
                updated_at=timezone.now(),
            ),
        )
        gate = threading.Barrier(3)

        def closing():
            gate.wait(timeout=10)
            try:
                close_financial_case(
                    case_public_id=self.case.public_id,
                    actor=self.reviewer,
                    rationale='Cierre serializado contra entrega y conciliación.',
                    result=FinancialCaseClosure.Result.REFUND_CONFIRMED,
                    idempotency_key='f75-three-way-close',
                )
                return 'closed'
            except FinancialResolutionConflict as exc:
                return exc.code

        def delivering():
            gate.wait(timeout=10)
            try:
                apply_order_inventory_effect(self.order.pk, actor=self.stock_actor)
                return 'delivered'
            except OrderInventoryConflict as exc:
                return exc.code

        def reconciling():
            gate.wait(timeout=10)
            return reconcile_verified_provider_event(event.pk).decision

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = [
                future.result(timeout=30)
                for future in (
                    executor.submit(self.threaded, closing),
                    executor.submit(self.threaded, delivering),
                    executor.submit(self.threaded, reconciling),
                )
            ]
        self.order.refresh_from_db()
        event.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=self.order)
        self.assertNotIn('delivered', results)
        self.assertIn(
            event.reconciliation_status,
            {
                ProviderEvent.ReconciliationStatus.APPLIED,
                ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED,
            },
        )
        self.assertIn(self.order.estado, {'PAGADO', 'CANCELADO'})
        if self.order.estado == 'CANCELADO':
            self.assertEqual(commitment.estado, CompromisoStock.State.RELEASED)
        else:
            self.assertEqual(commitment.estado, CompromisoStock.State.ACTIVE)
        self.assertFalse(MovimientoStock.objects.filter(
            reference_id=str(self.order.pk),
            tipo=MovimientoStock.Type.ORDER_SALE_OUT,
        ).exists())
