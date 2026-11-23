from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.assisted_payment_services import (
    ASSISTED_PAYMENT_INTENT_PREPARED,
    prepare_assisted_payment_intent,
)
from gestion.assisted_technical_booking_services import (
    AssistedTechnicalBookingError,
)
from gestion.assisted_slot_hold_services import create_assisted_slot_hold
from gestion.manual_payment_services import (
    reconcile_manual_payment,
    register_manual_payment,
)
from gestion.models import (
    Auditoria,
    DetalleTurno,
    Pago,
    PaymentIntent,
    PaymentPolicy,
    SlotHold,
    SolicitudTecnicaAsistidaOperacion,
    Turno,
)
from gestion.payment_intent_services import publish_payment_policy
from gestion.tests.test_assisted_slot_holds import AssistedSlotHoldFixtureMixin
from usuarios.models import Usuario


class AssistedPaymentFixtureMixin(AssistedSlotHoldFixtureMixin):
    def setUp(self):
        super().setUp()
        self.register_permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='register_payment',
        )
        self.operator.user_permissions.add(self.register_permission)
        self.original_receipt_storage = (
            Pago._meta.get_field('comprobante_foto').storage
        )
        Pago._meta.get_field('comprobante_foto').storage = InMemoryStorage()
        self.addCleanup(self._restore_receipt_storage)
        self.policy_actor = Usuario.objects.create_user(
            email='assisted-payment-policy@test.com',
            password='pass1234',
        )
        self.policy_actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_payment_configuration',
        ))
        policy = PaymentPolicy.objects.create(
            version='BH063-I4-T1',
            allowed_mode=PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL,
            deposit_kind=PaymentPolicy.DepositKind.FIXED,
            deposit_value=Decimal('300.00'),
            fixed_exceeds_total_behavior=(
                PaymentPolicy.FixedExceedsTotalBehavior.REJECT
            ),
            currency='ARS',
            intent_ttl_minutes=10,
            enabled_manual_methods=[
                Pago.Method.CASH,
                Pago.Method.BANK_TRANSFER,
            ],
            created_by=self.policy_actor,
        )
        publish_payment_policy(policy_id=policy.pk, actor=self.policy_actor)
        self.hold = create_assisted_slot_hold(
            solicitud_id=self.solicitud.pk,
            actor=self.operator,
            idempotency_key='assisted-payment-hold',
            operation_id=uuid4(),
            personal_id=self.personal.pk,
            starts_at=self.starts_at,
        ).hold
        self.api = APIClient()
        self.api.force_authenticate(self.operator)

    def _restore_receipt_storage(self):
        Pago._meta.get_field('comprobante_foto').storage = (
            self.original_receipt_storage
        )

    def options_url(self):
        return reverse(
            'solicitud-tecnica-asistida-opciones-pago',
            args=[self.solicitud.pk],
        )

    def intent_url(self):
        return reverse(
            'solicitud-tecnica-asistida-intent-pago',
            args=[self.solicitud.pk],
        )

    def intent_payload(self, **overrides):
        payload = {
            'operation_id': str(uuid4()),
            'hold_public_id': str(self.hold.public_id),
            'mode': PaymentIntent.Mode.DEPOSIT,
        }
        payload.update(overrides)
        return payload

    def prepare(self, *, key='assisted-payment-intent', payload=None):
        return self.api.post(
            self.intent_url(),
            payload or self.intent_payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )


class AssistedPaymentTests(AssistedPaymentFixtureMixin, TestCase):
    def test_options_and_prepare_reuse_policy_without_creating_money_or_turno(self):
        options = self.api.get(self.options_url(), {
            'hold_public_id': str(self.hold.public_id),
        })
        self.assertEqual(options.status_code, status.HTTP_200_OK)
        self.assertEqual(options.data['policy_version'], 'BH063-I4-T1')
        self.assertEqual(options.data['total_amount'], '1500.00')
        self.assertEqual(options.data['currency'], 'ARS')
        self.assertEqual(
            {item['mode']: item['required_amount'] for item in options.data['modes']},
            {'DEPOSIT': '300.00', 'FULL': '1500.00'},
        )

        payload = self.intent_payload()
        response = self.prepare(payload=payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['required_amount'], '300.00')
        self.assertEqual(response.data['paid_reconciled'], Decimal('0.00'))
        self.assertFalse(response.data['financial_threshold_reached'])
        self.assertIsNone(response.data['confirmed_turno_id'])
        intent = PaymentIntent.objects.get(public_id=response.data['public_id'])
        self.assertEqual(intent.created_by, self.operator)
        self.assertEqual(intent.slot_hold, self.hold)
        operation = SolicitudTecnicaAsistidaOperacion.objects.get(
            command=SolicitudTecnicaAsistidaOperacion.Command.INTENT
        )
        self.assertEqual(operation.payment_intent, intent)
        self.assertEqual(operation.hold, self.hold)
        self.assertEqual(str(operation.operation_id), payload['operation_id'])
        self.assertTrue(Auditoria.objects.filter(
            usuario=self.operator,
            valor_nuevo__event=ASSISTED_PAYMENT_INTENT_PREPARED,
        ).exists())
        self.assertEqual(Pago.objects.count(), 0)
        self.assertEqual(Turno.objects.count(), 0)

    def test_prepare_retry_and_get_recover_persisted_result(self):
        payload = self.intent_payload()
        first = self.prepare(key='stable-assisted-intent', payload=payload)
        repeated = self.prepare(key='stable-assisted-intent', payload=payload)
        recovered = self.api.get(self.intent_url())
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK)
        self.assertTrue(repeated.data['recovered'])
        self.assertEqual(recovered.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['public_id'], recovered.data['public_id'])
        self.assertEqual(first.data['operation_id'], recovered.data['operation_id'])
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.filter(
                command=SolicitudTecnicaAsistidaOperacion.Command.INTENT
            ).count(),
            1,
        )

        incompatible = self.prepare(
            key='stable-assisted-intent',
            payload={**payload, 'mode': PaymentIntent.Mode.FULL},
        )
        self.assertEqual(incompatible.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            incompatible.data['error']['code'], 'IDEMPOTENCY_KEY_REUSED'
        )

    def test_effective_authority_requires_both_permissions_and_exact_scope(self):
        self.operator.user_permissions.remove(self.register_permission)
        denied = self.prepare(key='missing-financial-authority')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            denied.data['error']['code'], 'ASSISTED_PAYMENT_PERMISSION_DENIED'
        )
        self.assertFalse(PaymentIntent.objects.exists())

        self.operator.user_permissions.add(self.register_permission)
        self.other_operator.user_permissions.add(self.register_permission)
        self.api.force_authenticate(self.other_operator)
        foreign = self.api.get(self.options_url(), {
            'hold_public_id': str(self.hold.public_id),
        })
        self.assertEqual(foreign.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(PaymentIntent.objects.exists())

    def test_permission_revoked_during_locked_revalidation_rolls_back(self):
        from gestion.assisted_payment_services import _authorized_financial_actor

        calls = 0

        def revoke_before_scope(actor):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.operator.user_permissions.remove(self.register_permission)
            return _authorized_financial_actor(actor)

        with patch(
            'gestion.assisted_payment_services._authorized_financial_actor',
            side_effect=revoke_before_scope,
        ):
            response = self.prepare(key='revoked-after-lock')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(PaymentIntent.objects.exists())
        self.assertFalse(SolicitudTecnicaAsistidaOperacion.objects.filter(
            command=SolicitudTecnicaAsistidaOperacion.Command.INTENT
        ).exists())
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(Turno.objects.exists())

    def test_insufficient_then_sufficient_cash_confirms_once_from_assisted_hold(self):
        prepared = self.prepare()
        intent = PaymentIntent.objects.get(public_id=prepared.data['public_id'])
        common = {
            'intent_public_id': intent.public_id,
            'currency': 'ARS',
            'method': Pago.Method.CASH,
            'purpose': Pago.Purpose.CONFIRMATION,
            'occurred_at': timezone.now(),
            'manual_reference': '',
            'receipt': None,
            'actor': self.operator,
            'late_evidence': False,
        }
        first = register_manual_payment(
            amount=Decimal('100.00'),
            idempotency_key='assisted-cash-partial',
            **common,
        )
        self.assertEqual(first.payment.status, Pago.Status.RECONCILED)
        self.assertFalse(first.financial.financial_threshold_reached)
        self.assertEqual(Turno.objects.count(), 0)

        second = register_manual_payment(
            amount=Decimal('250.00'),
            idempotency_key='assisted-cash-terminal',
            **common,
        )
        self.assertTrue(second.financial.financial_threshold_reached)
        intent.refresh_from_db()
        self.hold.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.APPROVED)
        self.assertEqual(self.hold.state, SlotHold.State.CONSUMED)
        self.assertEqual(Turno.objects.count(), 1)
        turno = Turno.objects.get()
        self.assertEqual(turno.estado, Turno.Estado.CONFIRMADO)
        self.assertEqual(turno.canal_origen, Turno.CanalOrigen.PRESENCIAL)
        self.assertEqual(intent.confirmed_turno, turno)
        self.assertEqual(
            list(DetalleTurno.objects.filter(turno=turno).order_by('pk').values_list(
                'servicio_id', flat=True
            )),
            [self.service.pk, self.second_service.pk],
        )
        repeated = register_manual_payment(
            amount=Decimal('250.00'),
            idempotency_key='assisted-cash-terminal',
            **common,
        )
        self.assertFalse(repeated.created)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(DetalleTurno.objects.count(), 2)
        self.assertEqual(Pago.objects.count(), 2)

    def test_transfer_remains_pending_until_authorized_reconciliation(self):
        prepared = self.prepare()
        payment = register_manual_payment(
            intent_public_id=prepared.data['public_id'],
            amount=Decimal('300.00'),
            currency='ARS',
            method=Pago.Method.BANK_TRANSFER,
            purpose=Pago.Purpose.CONFIRMATION,
            occurred_at=timezone.now(),
            manual_reference='assisted-transfer-001',
            receipt=SimpleUploadedFile(
                'assisted-transfer.pdf',
                b'%PDF-1.7\nassisted transfer evidence',
                content_type='application/pdf',
            ),
            idempotency_key='assisted-transfer-payment',
            actor=self.operator,
        ).payment
        self.assertEqual(payment.status, Pago.Status.PENDING_RECONCILIATION)
        self.assertFalse(Turno.objects.exists())

        self.policy_actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='confirm_deposit',
        ))
        result = reconcile_manual_payment(
            payment_public_id=payment.public_id,
            decision='ACCEPT',
            reason='',
            actor=self.policy_actor,
        )
        self.assertTrue(result.changed)
        self.assertEqual(result.payment.status, Pago.Status.RECONCILED)
        self.assertEqual(Turno.objects.count(), 1)
        self.assertEqual(Turno.objects.get().estado, Turno.Estado.CONFIRMADO)

    def test_expired_hold_never_creates_intent_payment_or_turno(self):
        current = timezone.now()
        SlotHold.objects.filter(pk=self.hold.pk).update(
            created_at=current - timedelta(minutes=20),
            expires_at=current - timedelta(minutes=1),
        )
        response = self.prepare(key='expired-assisted-intent')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['error']['code'], 'HOLD_EXPIRED')
        self.assertFalse(PaymentIntent.objects.exists())
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(Turno.objects.exists())


class AssistedPaymentConcurrencyTests(
    AssistedPaymentFixtureMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        super().setUp()
        if connection.vendor != 'postgresql':
            self.skipTest('Esta carrera requiere PostgreSQL real.')

    def test_concurrent_identical_prepare_creates_one_intent_and_one_ledger(self):
        barrier = Barrier(2)
        operation_id = uuid4()

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                result = prepare_assisted_payment_intent(
                    solicitud_id=self.solicitud.pk,
                    hold_public_id=self.hold.public_id,
                    mode=PaymentIntent.Mode.DEPOSIT,
                    actor=Usuario.objects.get(pk=self.operator.pk),
                    idempotency_key='concurrent-assisted-intent',
                    operation_id=operation_id,
                )
                return ('success', result.recovered)
            except AssistedTechnicalBookingError as exc:
                return ('error', exc.code)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]

        self.assertEqual([item[0] for item in results], ['success', 'success'])
        self.assertEqual(sorted(item[1] for item in results), [False, True])
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(
            SolicitudTecnicaAsistidaOperacion.objects.filter(
                command=SolicitudTecnicaAsistidaOperacion.Command.INTENT
            ).count(),
            1,
        )
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(Turno.objects.exists())
