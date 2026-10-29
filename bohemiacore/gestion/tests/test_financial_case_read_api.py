from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    Auditoria,
    OrdenCompra,
    Pago,
    PaymentReconciliationCase,
    ProviderEvent,
    ProviderPaymentAttempt,
    Turno,
)
from gestion.tests.test_manual_payments import ManualPaymentFixtureMixin
from usuarios.models import Usuario


class FinancialCaseReadApiTests(ManualPaymentFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='reconcile_external_payment',
        )
        self.reader = Usuario.objects.create_user(
            email='financial-case-reader@test.com',
            password='Payment!2026',
        )
        self.reader.user_permissions.add(self.permission)
        self.staff_without_permission = Usuario.objects.create_user(
            email='financial-case-staff@test.com',
            password='Payment!2026',
            is_staff=True,
        )
        self.inactive_reader = Usuario.objects.create_user(
            email='financial-case-inactive@test.com',
            password='Payment!2026',
            is_active=False,
        )
        self.inactive_reader.user_permissions.add(self.permission)
        self.api = APIClient()

        self.booking_payment = self.register(
            amount=Decimal('10.00'),
            idempotency_key='f7-1-booking-payment',
        ).payment
        self.turno = Turno.objects.create(
            cliente=self.cliente,
            profesional=self.personal,
            fecha=self.date,
            hora_inicio=time(12, 0),
            estado=Turno.Estado.CONFIRMADO,
        )
        self.booking_attempt = ProviderPaymentAttempt.objects.create(
            provider=ProviderPaymentAttempt.Provider.MERCADO_PAGO,
            context=ProviderPaymentAttempt.Context.BOOKING,
            channel=ProviderPaymentAttempt.Channel.ONLINE,
            status=ProviderPaymentAttempt.Status.READY,
            payment_intent=self.intent,
            amount=Decimal('10.00'),
            currency='ARS',
            external_reference='f7-1-booking-external',
            client_idempotency_key='f7-1-booking-client',
            provider_idempotency_key='f7-1-booking-provider',
            request_fingerprint='a' * 64,
            provider_order_id='F7-1-BOOKING-ORDER',
            provider_status='processed',
            reconciliation_status=(
                ProviderPaymentAttempt.ReconciliationStatus.REVIEW_REQUIRED
            ),
            created_by=self.reader,
        )
        self.booking_event = ProviderEvent.objects.create(
            provider=ProviderEvent.Provider.MERCADO_PAGO,
            topic='order',
            action='order.processed',
            event_id='F7-1-BOOKING-EVENT',
            provider_resource_id='F7-1-BOOKING-ORDER',
            status=ProviderEvent.Status.VERIFIED,
            attempt=self.booking_attempt,
            notification_snapshot={
                'token': 'notification-secret-must-not-leak',
            },
            provider_snapshot={
                'access_token': 'provider-secret-must-not-leak',
                'payments': [{'card_number': '4111111111111111'}],
            },
            reconciliation_status=(
                ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED
            ),
            reconciliation_code='LATE_PAYMENT_REVIEW',
        )
        self.booking_case = self.create_booking_case(
            case_type=PaymentReconciliationCase.Type.LATE_PAYMENT,
            reason_code='LATE_PAYMENT_REVIEW',
            operation_key='f7-1-booking-case',
            created_at=timezone.now() - timedelta(days=3),
            provider_attempt=self.booking_attempt,
            provider_event=self.booking_event,
            turno=self.turno,
            payment=self.booking_payment,
        )

        self.order = OrdenCompra.objects.create(
            codigo='F7-1-ORDER',
            cliente=self.cliente,
            estado='PAGADO',
            total=Decimal('80.00'),
            notas='internal order note must not leak',
        )
        self.order_payment = Pago.objects.create(
            orden=self.order,
            monto=Decimal('80.00'),
            metodo_pago=Pago.Method.CASH,
            currency='ARS',
            status=Pago.Status.RECONCILED,
            manual_reference='private-manual-reference',
        )
        self.order_case = self.create_order_case(
            case_type=PaymentReconciliationCase.Type.ORDER_FULFILLMENT_FAILED,
            reason_code='ORDER_NOT_FULFILLABLE',
            operation_key='f7-1-order-case',
            created_at=timezone.now() - timedelta(days=1),
            payment=self.order_payment,
        )

    def create_booking_case(
        self,
        *,
        case_type,
        reason_code,
        operation_key,
        created_at=None,
        provider_attempt=None,
        provider_event=None,
        turno=None,
        payment=None,
    ):
        case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=self.intent,
            slot_hold=self.hold,
            turno=turno,
            order=None,
            provider_attempt=provider_attempt,
            provider_event=provider_event,
            case_type=case_type,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code=reason_code,
            operation_key=operation_key,
            details={
                'detail': 'Allowlisted operational description',
                'secret': 'case-secret-must-not-leak',
                'provider_snapshot': {'token': 'nested-secret-must-not-leak'},
            },
            created_by=self.reader,
            created_at=created_at or timezone.now(),
        )
        if payment is not None:
            case.payments.add(payment)
        return case

    def create_order_case(
        self,
        *,
        case_type,
        reason_code,
        operation_key,
        created_at=None,
        payment=None,
    ):
        case = PaymentReconciliationCase.objects._create_from_service(
            payment_intent=None,
            slot_hold=None,
            turno=None,
            order=self.order,
            provider_attempt=None,
            provider_event=None,
            case_type=case_type,
            status=PaymentReconciliationCase.Status.OPEN,
            reason_code=reason_code,
            operation_key=operation_key,
            details={'detail': 'Order requires review'},
            created_by=self.reader,
            created_at=created_at or timezone.now(),
        )
        if payment is not None:
            case.payments.add(payment)
        return case

    @staticmethod
    def list_url():
        return reverse('payment-reconciliation-case-list')

    @staticmethod
    def detail_url(case):
        return reverse(
            'payment-reconciliation-case-detail',
            kwargs={'public_id': case.public_id},
        )

    def authenticate(self, user=None):
        self.api.force_authenticate(user=user or self.reader)

    def test_authorized_list_is_paginated_oldest_first_and_classifies_context(self):
        self.authenticate()

        response = self.api.get(self.list_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        results = response.data['results']
        self.assertEqual(
            [item['public_id'] for item in results],
            [str(self.booking_case.public_id), str(self.order_case.public_id)],
        )
        self.assertEqual(results[0]['case_type'], 'LATE_PAYMENT')
        self.assertEqual(results[0]['context'], 'BOOKING')
        self.assertEqual(results[1]['case_type'], 'ORDER_FULFILLMENT_FAILED')
        self.assertEqual(results[1]['context'], 'ORDER')
        self.assertGreater(results[0]['age_seconds'], results[1]['age_seconds'])
        self.assertEqual(
            results[0]['financial_summary']['payment_public_ids'],
            [str(self.booking_payment.public_id)],
        )

    def test_authorized_detail_exposes_safe_related_references(self):
        self.authenticate()

        response = self.api.get(self.detail_url(self.booking_case))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['context'], 'BOOKING')
        self.assertEqual(
            response.data['payment_intent']['public_id'],
            str(self.intent.public_id),
        )
        self.assertEqual(response.data['turno']['id'], self.turno.pk)
        self.assertEqual(
            response.data['provider_attempt']['public_id'],
            str(self.booking_attempt.public_id),
        )
        self.assertEqual(
            response.data['provider_event']['event_id'],
            self.booking_event.event_id,
        )
        self.assertEqual(
            response.data['payments'][0]['public_id'],
            str(self.booking_payment.public_id),
        )

        order_response = self.api.get(self.detail_url(self.order_case))
        self.assertEqual(order_response.status_code, status.HTTP_200_OK)
        self.assertEqual(order_response.data['context'], 'ORDER')
        self.assertEqual(order_response.data['order']['codigo'], self.order.codigo)
        self.assertIsNone(order_response.data['payment_intent'])

    def test_permission_is_effective_individual_permission_not_staff_flag(self):
        unauthenticated = self.api.get(self.list_url())
        self.assertEqual(unauthenticated.status_code, status.HTTP_401_UNAUTHORIZED)

        for denied_user in (
            self.staff_without_permission,
            self.user,
            self.inactive_reader,
        ):
            with self.subTest(user=denied_user.email):
                self.authenticate(denied_user)
                response = self.api.get(self.list_url())
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.reader)
        allowed = self.api.get(self.list_url())
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_filters_by_status_type_context_date_and_reason(self):
        self.authenticate()
        url = self.list_url()

        expectations = (
            ({'status': 'OPEN'}, {str(self.booking_case.public_id), str(self.order_case.public_id)}),
            ({'type': 'LATE_PAYMENT'}, {str(self.booking_case.public_id)}),
            ({'context': 'BOOKING'}, {str(self.booking_case.public_id)}),
            ({'context': 'ORDER'}, {str(self.order_case.public_id)}),
            ({'reason': 'not_fulfill'}, {str(self.order_case.public_id)}),
            (
                {'created_from': (timezone.now() - timedelta(days=2)).isoformat()},
                {str(self.order_case.public_id)},
            ),
            (
                {'created_to': (timezone.now() - timedelta(days=2)).isoformat()},
                {str(self.booking_case.public_id)},
            ),
        )
        for params, expected_ids in expectations:
            with self.subTest(params=params):
                response = self.api.get(url, params)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    {item['public_id'] for item in response.data['results']},
                    expected_ids,
                )

        newest_first = self.api.get(url, {'ordering': '-created_at'})
        self.assertEqual(newest_first.status_code, status.HTTP_200_OK)
        self.assertEqual(
            newest_first.data['results'][0]['public_id'],
            str(self.order_case.public_id),
        )

    def test_all_supported_classifications_are_returned_without_decisions(self):
        existing = {
            self.booking_case.case_type,
            self.order_case.case_type,
        }
        for index, case_type in enumerate(PaymentReconciliationCase.Type.values):
            if case_type in existing:
                continue
            self.create_booking_case(
                case_type=case_type,
                reason_code=f'CLASSIFICATION_{index}',
                operation_key=f'f7-1-classification-{index}',
            )
        self.authenticate()

        response = self.api.get(self.list_url(), {'page_size': 100})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item['case_type'] for item in response.data['results']},
            set(PaymentReconciliationCase.Type.values),
        )
        forbidden_decision_fields = {
            'decision',
            'refund',
            'approved',
            'resolution',
        }
        for item in response.data['results']:
            self.assertTrue(forbidden_decision_fields.isdisjoint(item.keys()))

    def test_pagination_has_bounded_client_page_size(self):
        for index in range(5):
            self.create_booking_case(
                case_type=PaymentReconciliationCase.Type.EXTERNAL_PAYMENT_REVIEW,
                reason_code=f'PAGINATION_{index}',
                operation_key=f'f7-1-pagination-{index}',
            )
        self.authenticate()

        first = self.api.get(self.list_url(), {'page_size': 2})
        second = self.api.get(self.list_url(), {'page_size': 2, 'page': 2})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['count'], 7)
        self.assertEqual(len(first.data['results']), 2)
        self.assertEqual(len(second.data['results']), 2)
        self.assertIsNotNone(first.data['next'])
        self.assertTrue(
            {item['public_id'] for item in first.data['results']}.isdisjoint(
                {item['public_id'] for item in second.data['results']}
            )
        )

    def test_payload_omits_snapshots_credentials_receipts_and_internal_details(self):
        self.authenticate()

        response = self.api.get(self.detail_url(self.booking_case))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rendered = response.content.decode('utf-8')
        for secret in (
            'notification-secret-must-not-leak',
            'provider-secret-must-not-leak',
            '4111111111111111',
            'case-secret-must-not-leak',
            'nested-secret-must-not-leak',
        ):
            self.assertNotIn(secret, rendered)
        forbidden_fields = {
            'details',
            'notification_snapshot',
            'provider_snapshot',
            'business_result',
            'checkout_url',
            'client_idempotency_key',
            'provider_idempotency_key',
            'request_fingerprint',
            'manual_reference',
            'comprobante_foto',
            'receipt_download',
            'policy_snapshot',
        }

        def collect_keys(value):
            if isinstance(value, dict):
                keys = set(value)
                for nested in value.values():
                    keys.update(collect_keys(nested))
                return keys
            if isinstance(value, list):
                keys = set()
                for nested in value:
                    keys.update(collect_keys(nested))
                return keys
            return set()

        self.assertTrue(forbidden_fields.isdisjoint(collect_keys(response.data)))

    def test_reads_and_generic_write_methods_do_not_mutate_domain(self):
        self.authenticate()
        self.booking_case.refresh_from_db()
        self.booking_payment.refresh_from_db()
        self.intent.refresh_from_db()
        self.turno.refresh_from_db()
        self.order.refresh_from_db()
        self.booking_event.refresh_from_db()
        self.booking_attempt.refresh_from_db()
        before = {
            'audits': Auditoria.objects.count(),
            'cases': PaymentReconciliationCase.objects.count(),
            'case_status': self.booking_case.status,
            'case_resolved_at': self.booking_case.resolved_at,
            'payment_status': self.booking_payment.status,
            'payment_amount': self.booking_payment.monto,
            'intent_status': self.intent.status,
            'turno_status': self.turno.estado,
            'order_status': self.order.estado,
            'event_status': self.booking_event.status,
            'event_reconciliation_status': self.booking_event.reconciliation_status,
            'attempt_status': self.booking_attempt.status,
        }

        self.assertEqual(self.api.get(self.list_url()).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.api.get(self.detail_url(self.booking_case)).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.api.post(self.list_url(), {}, format='json').status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        for method in ('put', 'patch', 'delete'):
            response = getattr(self.api, method)(
                self.detail_url(self.booking_case),
                {} if method != 'delete' else None,
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        self.booking_case.refresh_from_db()
        self.booking_payment.refresh_from_db()
        self.intent.refresh_from_db()
        self.turno.refresh_from_db()
        self.order.refresh_from_db()
        self.booking_event.refresh_from_db()
        self.booking_attempt.refresh_from_db()
        after = {
            'audits': Auditoria.objects.count(),
            'cases': PaymentReconciliationCase.objects.count(),
            'case_status': self.booking_case.status,
            'case_resolved_at': self.booking_case.resolved_at,
            'payment_status': self.booking_payment.status,
            'payment_amount': self.booking_payment.monto,
            'intent_status': self.intent.status,
            'turno_status': self.turno.estado,
            'order_status': self.order.estado,
            'event_status': self.booking_event.status,
            'event_reconciliation_status': self.booking_event.reconciliation_status,
            'attempt_status': self.booking_attempt.status,
        }
        self.assertEqual(after, before)
