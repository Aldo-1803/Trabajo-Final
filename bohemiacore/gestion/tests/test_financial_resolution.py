from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.financial_resolution_services import (
    FINANCIAL_EVIDENCE_REQUESTED,
    FINANCIAL_RESOLUTION_DECIDED,
    FINANCIAL_RESOLUTION_REQUESTED,
    FinancialResolutionPermissionDenied,
    decide_financial_resolution,
    submit_financial_resolution_request,
)
from gestion.models import (
    Auditoria,
    CompromisoStock,
    FinancialResolutionDecision,
    FinancialResolutionEvent,
    FinancialResolutionRequest,
    MovimientoStock,
    OrdenCompra,
    Pago,
    PaymentIntent,
    PaymentReconciliationCase,
    SlotHold,
    Turno,
)
from gestion.order_inventory_services import create_order_stock_commitments
from gestion.payment_confirmation_services import (
    approve_payment_intent_and_confirm_booking,
)
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin
from gestion.tests.test_order_inventory import OrderInventoryFixtureMixin
from usuarios.models import Usuario


class FinancialResolutionFixtureMixin(ManualPaymentFixtureMixin):
    def setUp(self):
        super().setUp()
        self.permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='reconcile_external_payment',
        )
        self.reviewer = Usuario.objects.create_user(
            email='f7-2-reviewer@test.com',
            password='Financial!2026',
        )
        self.reviewer.user_permissions.add(self.permission)
        self.staff_without_permission = Usuario.objects.create_user(
            email='f7-2-staff@test.com',
            password='Financial!2026',
            is_staff=True,
        )
        self.api = APIClient()
        self.payment = self.register(
            amount=Decimal('10.00'),
            idempotency_key='f7-2-base-payment',
        ).payment
        self.case = self.create_booking_case(
            payment=self.payment,
            suffix='base',
        )

    def create_booking_case(
        self,
        *,
        payment,
        suffix,
        case_type=PaymentReconciliationCase.Type.LATE_PAYMENT,
    ):
        case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=self.intent,
            slot_hold=self.hold,
            turno=self.intent.confirmed_turno,
            order=None,
            provider_attempt=None,
            provider_event=None,
            case_type=case_type,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code=f'F7_2_{suffix.upper()}',
            operation_key=f'f7-2-case-{suffix}',
            details={'source': 'F7_2_TEST'},
            created_by=self.reviewer,
            created_at=timezone.now(),
        )
        case.payments.add(payment)
        return case

    @staticmethod
    def submit_url(case):
        return reverse(
            'payment-reconciliation-case-submit-resolution-request',
            kwargs={'public_id': case.public_id},
        )

    @staticmethod
    def state_url(case):
        return reverse(
            'payment-reconciliation-case-resolution-request',
            kwargs={'public_id': case.public_id},
        )

    @staticmethod
    def decision_url(case):
        return reverse(
            'payment-reconciliation-case-record-decision',
            kwargs={'public_id': case.public_id},
        )

    def submit_payload(self, **overrides):
        payload = {
            'requested_outcome': FinancialResolutionRequest.RequestedOutcome.REFUND,
            'reason': 'Pago acreditado sin prestación disponible.',
            'amount': '10.00',
            'currency': 'ARS',
            'evidence_reference': 'CONTACT:CASE-10',
            'evidence_note': 'La titular solicita revisión documentada.',
        }
        payload.update(overrides)
        return payload

    def submit_as_owner(self, *, case=None, key='f7-2-request', payload=None):
        self.api.force_authenticate(self.user)
        return self.api.post(
            self.submit_url(case or self.case),
            payload or self.submit_payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def decide(self, *, case=None, key='f7-2-decision', **overrides):
        payload = {
            'action': FinancialResolutionDecision.Action.APPROVE_REFUND,
            'rationale': 'Los hechos y la política permiten autorizar el reintegro.',
            'authorized_amount': '10.00',
            'currency': 'ARS',
            'policy_reference': 'REFUNDS-V1:4.2',
        }
        payload.update(overrides)
        self.api.force_authenticate(self.reviewer)
        return self.api.post(
            self.decision_url(case or self.case),
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )


class FinancialResolutionFunctionalTests(
    FinancialResolutionFixtureMixin,
    TestCase,
):
    def test_legitimate_request_is_idempotent_and_append_only(self):
        first = self.submit_as_owner()
        retry = self.submit_as_owner()

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['public_id'], retry.data['public_id'])
        self.assertEqual(FinancialResolutionRequest.objects.count(), 1)
        self.assertEqual(FinancialResolutionEvent.objects.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=FINANCIAL_RESOLUTION_REQUESTED).count(),
            1,
        )
        self.case.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.case.status, PaymentReconciliationCase.Status.OPEN)
        self.assertIsNone(self.case.resolved_at)
        self.assertEqual(self.payment.status, Pago.Status.RECONCILED)

    def test_owner_cannot_access_or_submit_against_foreign_resource(self):
        foreign_order = OrdenCompra.objects.create(
            codigo='F7-2-FOREIGN',
            cliente=self.other_cliente,
            estado='PAGADO',
            total=Decimal('15.00'),
        )
        foreign_payment = Pago.objects.create(
            orden=foreign_order,
            monto=Decimal('15.00'),
            metodo_pago=Pago.Method.CASH,
            status=Pago.Status.RECONCILED,
        )
        foreign_case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=None,
            slot_hold=None,
            turno=None,
            order=foreign_order,
            provider_attempt=None,
            provider_event=None,
            case_type=PaymentReconciliationCase.Type.ORDER_FULFILLMENT_FAILED,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code='FOREIGN_ORDER_REVIEW',
            operation_key='f7-2-foreign-case',
            details={},
            created_by=self.reviewer,
            created_at=timezone.now(),
        )
        foreign_case.payments.add(foreign_payment)
        self.api.force_authenticate(self.user)

        submitted = self.api.post(
            self.submit_url(foreign_case),
            self.submit_payload(amount='15.00'),
            format='json',
            HTTP_IDEMPOTENCY_KEY='foreign-request',
        )
        state = self.api.get(self.state_url(foreign_case))

        self.assertEqual(submitted.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(state.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(FinancialResolutionRequest.objects.exists())

    def test_client_and_staff_without_effective_permission_cannot_decide(self):
        self.assertEqual(
            self.submit_as_owner().status_code,
            status.HTTP_201_CREATED,
        )
        payload = {
            'action': FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE,
            'rationale': 'Intento no autorizado.',
        }
        for denied in (self.user, self.staff_without_permission):
            with self.subTest(user=denied.email):
                self.api.force_authenticate(denied)
                response = self.api.post(
                    self.decision_url(self.case),
                    payload,
                    format='json',
                    HTTP_IDEMPOTENCY_KEY=f'denied-{denied.pk}',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                with self.assertRaises(FinancialResolutionPermissionDenied):
                    decide_financial_resolution(
                        case_public_id=self.case.public_id,
                        actor=denied,
                        action=(
                            FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE
                        ),
                        rationale='El dominio también debe rechazar este actor.',
                        idempotency_key=f'domain-denied-{denied.pk}',
                    )
        inactive = Usuario.objects.create_user(
            email='f7-2-inactive-reviewer@test.com',
            is_active=False,
        )
        inactive.user_permissions.add(self.permission)
        with self.assertRaises(FinancialResolutionPermissionDenied):
            decide_financial_resolution(
                case_public_id=self.case.public_id,
                actor=inactive,
                action=FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE,
                rationale='Una cuenta inactiva no es autoridad.',
                idempotency_key='domain-denied-inactive',
            )
        self.assertFalse(FinancialResolutionDecision.objects.exists())

    def test_authorized_decision_records_basis_without_financial_effect_or_closure(self):
        self.submit_as_owner()
        before = {
            'payments': Pago.objects.count(),
            'payment': Pago.objects.filter(pk=self.payment.pk).values().get(),
            'intent_status': PaymentIntent.objects.get(pk=self.intent.pk).status,
            'turnos': Turno.objects.count(),
            'movements': MovimientoStock.objects.count(),
        }

        response = self.decide()
        retry = self.decide()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        decision = FinancialResolutionDecision.objects.get()
        resolution_request = FinancialResolutionRequest.objects.get()
        self.case.refresh_from_db()
        self.assertEqual(decision.decided_by, self.reviewer)
        self.assertEqual(decision.authorized_amount, Decimal('10.00'))
        self.assertEqual(decision.policy_reference, 'REFUNDS-V1:4.2')
        self.assertEqual(
            resolution_request.status,
            FinancialResolutionRequest.Status.DECIDED,
        )
        self.assertEqual(self.case.status, PaymentReconciliationCase.Status.OPEN)
        self.assertIsNone(self.case.resolved_at)
        after = {
            'payments': Pago.objects.count(),
            'payment': Pago.objects.filter(pk=self.payment.pk).values().get(),
            'intent_status': PaymentIntent.objects.get(pk=self.intent.pk).status,
            'turnos': Turno.objects.count(),
            'movements': MovimientoStock.objects.count(),
        }
        self.assertEqual(after, before)
        self.assertEqual(FinancialResolutionDecision.objects.count(), 1)
        self.assertEqual(FinancialResolutionEvent.objects.count(), 2)
        self.assertEqual(
            Auditoria.objects.filter(tabla=FINANCIAL_RESOLUTION_DECIDED).count(),
            1,
        )

    def test_invalid_request_and_decision_amounts_are_rejected(self):
        excessive_request = self.submit_as_owner(
            key='f7-2-excessive-request',
            payload=self.submit_payload(amount='10.01'),
        )
        self.assertEqual(excessive_request.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            excessive_request.data['code'],
            'RESOLUTION_AMOUNT_EXCEEDS_PAYMENTS',
        )
        self.assertFalse(FinancialResolutionRequest.objects.exists())

        self.submit_as_owner(key='f7-2-valid-request')
        excessive_decision = self.decide(
            key='f7-2-excessive-decision',
            authorized_amount='10.01',
        )
        mismatch = self.decide(
            key='f7-2-currency-mismatch',
            authorized_amount='5.00',
            currency='USD',
        )
        self.assertEqual(excessive_decision.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(FinancialResolutionDecision.objects.exists())

    def test_more_evidence_then_final_decision_is_audited_without_contradiction(self):
        self.submit_as_owner()
        evidence = self.decide(
            key='f7-2-evidence',
            action=FinancialResolutionDecision.Action.REQUIRE_MORE_EVIDENCE,
            rationale='La referencia inicial no permite corroborar la titularidad.',
            evidence_request='Adjuntar constancia bancaria legible.',
            authorized_amount=None,
            currency='',
            policy_reference='',
        )
        self.assertEqual(evidence.status_code, status.HTTP_201_CREATED)
        resolution_request = FinancialResolutionRequest.objects.get()
        self.assertEqual(
            resolution_request.status,
            FinancialResolutionRequest.Status.EVIDENCE_REQUIRED,
        )
        final = self.decide(key='f7-2-final-after-evidence')
        contradictory = self.decide(
            key='f7-2-contradictory-final',
            action=FinancialResolutionDecision.Action.DENY_REFUND,
            authorized_amount=None,
            currency='',
            rationale='Una segunda decisión final no debe persistirse.',
        )

        self.assertEqual(final.status_code, status.HTTP_201_CREATED)
        self.assertEqual(contradictory.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(FinancialResolutionDecision.objects.count(), 2)
        self.assertEqual(
            FinancialResolutionDecision.objects.filter(
                action__in=FinancialResolutionDecision.FINAL_ACTIONS,
            ).count(),
            1,
        )
        self.assertEqual(
            Auditoria.objects.filter(tabla=FINANCIAL_EVIDENCE_REQUESTED).count(),
            1,
        )

    def test_denial_acknowledgement_and_no_change_are_supported_final_actions(self):
        denied_case = self.case
        self.submit_as_owner(case=denied_case, key='f7-2-denied-request')
        denied = self.decide(
            case=denied_case,
            key='f7-2-denied-decision',
            action=FinancialResolutionDecision.Action.DENY_REFUND,
            rationale='La política documentada no habilita el reintegro.',
            authorized_amount=None,
            currency='',
            policy_reference='REFUNDS-V1:DENIAL',
        )

        external_case = self.create_booking_case(
            payment=self.payment,
            suffix='external-adjustment',
            case_type=PaymentReconciliationCase.Type.POST_PAYMENT_CHANGE,
        )
        external_request = submit_financial_resolution_request(
            case_public_id=external_case.public_id,
            actor=self.reviewer,
            requested_outcome=(
                FinancialResolutionRequest.RequestedOutcome.REVIEW_EXTERNAL_ADJUSTMENT
            ),
            reason='El proveedor notificó una novedad posterior.',
            idempotency_key='f7-2-external-request',
        )
        acknowledged = decide_financial_resolution(
            case_public_id=external_case.public_id,
            actor=self.reviewer,
            action=(
                FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT
            ),
            rationale='Se reconoce la evidencia externa sin materializar ajustes.',
            idempotency_key='f7-2-external-decision',
        )

        no_change_case = self.create_booking_case(
            payment=self.payment,
            suffix='no-change',
            case_type=PaymentReconciliationCase.Type.EXTERNAL_PAYMENT_REVIEW,
        )
        submit_financial_resolution_request(
            case_public_id=no_change_case.public_id,
            actor=self.reviewer,
            requested_outcome=(
                FinancialResolutionRequest.RequestedOutcome.NO_FINANCIAL_CHANGE
            ),
            reason='La evidencia corresponde a un duplicado técnico.',
            idempotency_key='f7-2-no-change-request',
        )
        no_change = decide_financial_resolution(
            case_public_id=no_change_case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE,
            rationale='No existe un segundo hecho financiero.',
            idempotency_key='f7-2-no-change-decision',
        )

        self.assertEqual(denied.status_code, status.HTTP_201_CREATED)
        self.assertTrue(external_request.created)
        self.assertTrue(acknowledged.created)
        self.assertTrue(no_change.created)
        self.assertEqual(
            set(FinancialResolutionDecision.objects.values_list('action', flat=True)),
            {
                FinancialResolutionDecision.Action.DENY_REFUND,
                FinancialResolutionDecision.Action.ACKNOWLEDGE_EXTERNAL_ADJUSTMENT,
                FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE,
            },
        )
        self.assertFalse(
            PaymentReconciliationCase.objects.exclude(
                status=PaymentReconciliationCase.Status.OPEN,
                resolved_at__isnull=True,
            ).exists()
        )

    def test_public_state_is_reduced_while_reviewer_gets_internal_history(self):
        self.submit_as_owner()
        self.decide(
            action=FinancialResolutionDecision.Action.REQUIRE_MORE_EVIDENCE,
            authorized_amount=None,
            currency='',
            policy_reference='',
            evidence_request='Comprobante adicional.',
        )
        self.api.force_authenticate(self.user)
        public = self.api.get(self.state_url(self.case))
        self.api.force_authenticate(self.reviewer)
        internal = self.api.get(self.state_url(self.case))

        self.assertEqual(public.status_code, status.HTTP_200_OK)
        self.assertNotIn('requested_by', public.data)
        self.assertNotIn('decisions', public.data)
        self.assertNotIn('events', public.data)
        self.assertEqual(
            public.data['latest_decision']['evidence_request'],
            'Comprobante adicional.',
        )
        self.assertEqual(internal.status_code, status.HTTP_200_OK)
        self.assertEqual(internal.data['requested_by'], self.user.email)
        self.assertEqual(len(internal.data['decisions']), 1)
        self.assertEqual(len(internal.data['events']), 2)

    def test_decision_audit_failure_rolls_back_decision_event_and_state(self):
        self.submit_as_owner()
        with patch(
            'gestion.financial_resolution_services.Auditoria.objects.create',
            side_effect=RuntimeError('audit unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                decide_financial_resolution(
                    case_public_id=self.case.public_id,
                    actor=self.reviewer,
                    action=FinancialResolutionDecision.Action.NO_FINANCIAL_CHANGE,
                    rationale='No se verifica una modificación financiera.',
                    idempotency_key='f7-2-audit-failure',
                )
        resolution_request = FinancialResolutionRequest.objects.get()
        self.assertEqual(
            resolution_request.status,
            FinancialResolutionRequest.Status.PENDING_DECISION,
        )
        self.assertFalse(FinancialResolutionDecision.objects.exists())
        self.assertEqual(FinancialResolutionEvent.objects.count(), 1)

    def test_models_reject_generic_mutation_and_deletion(self):
        self.submit_as_owner()
        self.decide()
        resolution_request = FinancialResolutionRequest.objects.get()
        decision = FinancialResolutionDecision.objects.get()
        event = FinancialResolutionEvent.objects.order_by('pk').first()

        with self.assertRaises(ValidationError):
            FinancialResolutionRequest.objects.filter(pk=resolution_request.pk).update(
                status=FinancialResolutionRequest.Status.DECIDED
            )
        with self.assertRaises(ValidationError):
            decision.delete()
        with self.assertRaises(ValidationError):
            event.delete()

    def test_late_payment_decision_does_not_resurrect_hold_intent_or_turno(self):
        now = timezone.now()
        Pago.objects._create_booking_from_service(
            payment_intent=self.intent,
            orden=None,
            turno=None,
            monto=Decimal('20.00'),
            currency='ARS',
            metodo_pago=Pago.Method.CASH,
            purpose=Pago.Purpose.CONFIRMATION,
            status=Pago.Status.RECONCILED,
            fecha_pago=now,
            recorded_at=now,
            recorded_by=self.register_actor,
            reconciled_at=now,
            reconciled_by=self.register_actor,
            manual_reference='',
            receipt_sha256='',
            idempotency_key='f7-2-late-balance',
            terminal_reason='',
            es_sena=True,
        )
        deadline = now - timedelta(seconds=1)
        models.QuerySet.update(
            SlotHold.objects.filter(pk=self.hold.pk),
            created_at=deadline - timedelta(minutes=10),
            expires_at=deadline,
        )
        models.QuerySet.update(
            PaymentIntent.objects.filter(pk=self.intent.pk),
            created_at=deadline - timedelta(minutes=10),
            expires_at=deadline,
        )
        confirmation = approve_payment_intent_and_confirm_booking(
            intent_id=self.intent.pk,
            actor=self.register_actor,
        )
        late_case = confirmation.reconciliation_case
        submit_financial_resolution_request(
            case_public_id=late_case.public_id,
            actor=self.user,
            requested_outcome=FinancialResolutionRequest.RequestedOutcome.REFUND,
            reason='Pago posterior al vencimiento del HOLD.',
            amount=Decimal('30.00'),
            currency='ARS',
            idempotency_key='f7-2-late-request',
        )
        decide_financial_resolution(
            case_public_id=late_case.public_id,
            actor=self.reviewer,
            action=FinancialResolutionDecision.Action.APPROVE_REFUND,
            rationale='Se autoriza únicamente la futura ejecución financiera.',
            authorized_amount=Decimal('30.00'),
            currency='ARS',
            policy_reference='LATE-PAYMENT-V1',
            idempotency_key='f7-2-late-decision',
        )
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        late_case.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentIntent.Status.EXPIRED)
        self.assertEqual(self.hold.state, SlotHold.State.EXPIRED)
        self.assertFalse(Turno.objects.exists())
        self.assertEqual(late_case.status, PaymentReconciliationCase.Status.OPEN)

    def test_turno_cancellation_with_money_creates_linked_request_atomically(self):
        balance = self.register(
            amount=Decimal('20.00'),
            idempotency_key='f7-2-confirming-balance',
        ).payment
        self.intent.refresh_from_db()
        turno = self.intent.confirmed_turno
        payment_snapshots = list(
            Pago.objects.filter(payment_intent=self.intent).values()
        )
        self.api.force_authenticate(self.user)

        response = self.api.post(
            reverse('turno-cancelar-cliente', args=[turno.pk]),
            {'motivo': 'No podré asistir y solicito revisión del dinero.'},
            format='json',
        )
        retry = self.api.post(
            reverse('turno-cancelar-cliente', args=[turno.pk]),
            {'motivo': 'No podré asistir y solicito revisión del dinero.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['financial_resolution_required'])
        turno.refresh_from_db()
        self.intent.refresh_from_db()
        self.hold.refresh_from_db()
        balance.refresh_from_db()
        resolution_request = FinancialResolutionRequest.objects.get(
            public_id=response.data['financial_request_public_id']
        )
        self.assertEqual(turno.estado, Turno.Estado.CANCELADO)
        self.assertEqual(resolution_request.turno, turno)
        self.assertEqual(
            resolution_request.case.case_type,
            PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT,
        )
        self.assertEqual(resolution_request.amount, Decimal('30.00'))
        self.assertEqual(self.intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(self.hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(
            list(Pago.objects.filter(payment_intent=self.intent).values()),
            payment_snapshots,
        )
        self.assertEqual(FinancialResolutionRequest.objects.count(), 1)


class PaidOrderCancellationRequestTests(OrderInventoryFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.receive(self.product, 2, 'f7-2-order')
        self.order = self.make_order(
            [(self.product, 1)],
            state='PAGADO',
            code='F7-2-PAID-ORDER',
        )
        create_order_stock_commitments(self.order.pk)
        self.payment = Pago.objects.create(
            orden=self.order,
            monto=self.order.total,
            metodo_pago=Pago.Method.CASH,
            status=Pago.Status.RECONCILED,
        )

    @staticmethod
    def request_url():
        return reverse(
            'payment-reconciliation-case-request-paid-order-cancellation'
        )

    def test_paid_order_request_preserves_f5_order_commitment_payment_and_stock(self):
        self.api.force_authenticate(self.user)
        payment_before = Pago.objects.filter(pk=self.payment.pk).values().get()
        movement_count = MovimientoStock.objects.count()
        conventional = self.api.post(
            reverse('orden-compra-cancelar', args=[self.order.pk]),
            {},
            format='json',
        )
        payload = {
            'order_id': self.order.pk,
            'reason': 'Solicito cancelar la compra pagada.',
            'evidence_reference': 'CONTACT:ORDER-CANCEL',
        }
        response = self.api.post(
            self.request_url(),
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='f7-2-order-cancel',
        )
        retry = self.api.post(
            self.request_url(),
            payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY='f7-2-order-cancel',
        )

        self.assertEqual(conventional.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        commitment = CompromisoStock.objects.get(orden=self.order)
        resolution_request = FinancialResolutionRequest.objects.get()
        self.assertEqual(self.order.estado, 'PAGADO')
        self.assertEqual(commitment.estado, CompromisoStock.State.ACTIVE)
        self.assertEqual(self.product.stock_real, 2)
        self.assertEqual(self.product.stock_comprometido, 1)
        self.assertEqual(MovimientoStock.objects.count(), movement_count)
        self.assertEqual(
            Pago.objects.filter(pk=self.payment.pk).values().get(),
            payment_before,
        )
        self.assertEqual(
            resolution_request.case.case_type,
            PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT,
        )
        self.assertEqual(resolution_request.amount, self.order.total)
        self.assertEqual(FinancialResolutionRequest.objects.count(), 1)

    def test_foreign_client_cannot_request_paid_order_cancellation(self):
        foreign = Usuario.objects.create_user(email='f7-2-foreign-order@test.com')
        self.api.force_authenticate(foreign)
        response = self.api.post(
            self.request_url(),
            {'order_id': self.order.pk, 'reason': 'Intento ajeno.'},
            format='json',
            HTTP_IDEMPOTENCY_KEY='f7-2-foreign-order',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(FinancialResolutionRequest.objects.exists())
