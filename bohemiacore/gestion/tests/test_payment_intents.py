from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from gestion.models import (
    Auditoria,
    EvaluacionRiesgoTecnico,
    PaymentIntent,
    PaymentIntentLine,
    PaymentPolicy,
    Servicio,
    SlotHold,
    SolicitudTecnicaServicio,
    TechnicalRiskOutcome,
)
from gestion.payment_intent_services import (
    PAYMENT_INTENT_CANCELLED,
    PAYMENT_INTENT_CREATED,
    PAYMENT_INTENT_EXPIRED,
    PAYMENT_POLICY_PUBLISHED,
    PaymentIntentConflict,
    PaymentIntentNotFound,
    PaymentPolicyPermissionDenied,
    cancel_payment_intent,
    create_payment_intent,
    expire_payment_intent,
    publish_payment_policy,
)
from gestion.slot_hold_consumption_services import (
    create_confirmed_turno_from_locked_hold,
)
from gestion.slot_hold_services import (
    SLOT_HOLD_RELEASED,
    SlotHoldConflict,
    release_slot_hold,
)
from gestion.tests.test_slot_holds import SlotHoldFixtureMixin
from usuarios.models import Usuario


class PaymentPolicyTests(TestCase):
    def setUp(self):
        self.actor = Usuario.objects.create_user(
            email='payment-policy@test.com',
            password='Policy!2026',
        )
        self.permission = Permission.objects.get(
            codename='manage_payment_configuration'
        )

    def policy(self, version='PAY-1', **overrides):
        values = {
            'version': version,
            'allowed_mode': PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL,
            'deposit_kind': PaymentPolicy.DepositKind.PERCENTAGE,
            'deposit_value': Decimal('25.00'),
            'fixed_exceeds_total_behavior': None,
            'currency': 'ARS',
            'intent_ttl_minutes': 10,
            'enabled_manual_methods': ['BANK_TRANSFER', 'CASH'],
            'created_by': self.actor,
        }
        values.update(overrides)
        return PaymentPolicy.objects.create(**values)

    def publish(self, policy):
        self.actor.user_permissions.add(self.permission)
        return publish_payment_policy(policy_id=policy.pk, actor=self.actor)

    def test_publish_requires_exact_permission_and_retires_previous(self):
        first = self.policy('PAY-1')
        staff_without_permission = Usuario.objects.create_user(
            email='staff-no-payment-permission@test.com',
            password='Policy!2026',
            is_staff=True,
        )
        with self.assertRaises(PaymentPolicyPermissionDenied):
            publish_payment_policy(
                policy_id=first.pk,
                actor=staff_without_permission,
            )

        published = self.publish(first)
        self.assertEqual(published.status, PaymentPolicy.Status.PUBLISHED)
        self.assertIsNotNone(published.published_at)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_POLICY_PUBLISHED).count(),
            1,
        )

        second = self.policy('PAY-2')
        self.publish(second)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, PaymentPolicy.Status.RETIRED)
        self.assertEqual(second.status, PaymentPolicy.Status.PUBLISHED)
        self.assertEqual(
            PaymentPolicy.objects.filter(
                status=PaymentPolicy.Status.PUBLISHED
            ).count(),
            1,
        )

    def test_published_policy_is_strongly_immutable(self):
        policy = self.publish(self.policy())
        policy.intent_ttl_minutes = 30
        with self.assertRaises(ValidationError):
            policy.save()
        with self.assertRaises(ValidationError):
            PaymentPolicy.objects.filter(pk=policy.pk).update(
                intent_ttl_minutes=30
            )
        with self.assertRaises(ValidationError):
            policy.delete()
        with self.assertRaises(ValidationError):
            PaymentPolicy.objects.bulk_create([
                PaymentPolicy(
                    version='BULK-PUBLISHED',
                    status=PaymentPolicy.Status.PUBLISHED,
                    allowed_mode=PaymentPolicy.AllowedMode.FULL_ONLY,
                    currency='ARS',
                    intent_ttl_minutes=10,
                    created_by=self.actor,
                    published_at=timezone.now(),
                )
            ])

    def test_full_only_rejects_deposit_configuration(self):
        with self.assertRaises(ValidationError):
            self.policy(
                allowed_mode=PaymentPolicy.AllowedMode.FULL_ONLY,
                deposit_kind=PaymentPolicy.DepositKind.FIXED,
                deposit_value=Decimal('100.00'),
                fixed_exceeds_total_behavior=(
                    PaymentPolicy.FixedExceedsTotalBehavior.REJECT
                ),
            )
        valid = self.policy(
            version='FULL',
            allowed_mode=PaymentPolicy.AllowedMode.FULL_ONLY,
            deposit_kind=None,
            deposit_value=None,
            fixed_exceeds_total_behavior=None,
        )
        self.assertEqual(valid.status, PaymentPolicy.Status.DRAFT)

    def test_deposit_percentage_fixed_ttl_currency_and_methods_validation(self):
        invalid_cases = (
            {'deposit_value': Decimal('0.00')},
            {'deposit_value': Decimal('100.01')},
            {
                'deposit_kind': PaymentPolicy.DepositKind.FIXED,
                'deposit_value': Decimal('0.00'),
                'fixed_exceeds_total_behavior': (
                    PaymentPolicy.FixedExceedsTotalBehavior.REJECT
                ),
            },
            {
                'deposit_kind': PaymentPolicy.DepositKind.FIXED,
                'deposit_value': Decimal('100.00'),
                'fixed_exceeds_total_behavior': None,
            },
            {'intent_ttl_minutes': 0},
            {'currency': 'XXX'},
            {'enabled_manual_methods': ['CASH', 'CASH']},
            {'enabled_manual_methods': ['CRYPTO']},
        )
        for index, overrides in enumerate(invalid_cases):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValidationError):
                    self.policy(version=f'INVALID-{index}', **overrides)


class PaymentIntentTests(SlotHoldFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.payment_admin = Usuario.objects.create_user(
            email='payment-admin@test.com',
            password='Payment!2026',
        )
        self.payment_admin.user_permissions.add(
            Permission.objects.get(codename='manage_payment_configuration')
        )
        self.payment_policy = self.publish_policy()

    def publish_policy(self, version='PAYMENT-1', **overrides):
        values = {
            'version': version,
            'allowed_mode': PaymentPolicy.AllowedMode.DEPOSIT_OR_FULL,
            'deposit_kind': PaymentPolicy.DepositKind.PERCENTAGE,
            'deposit_value': Decimal('25.00'),
            'fixed_exceeds_total_behavior': None,
            'currency': 'ARS',
            'intent_ttl_minutes': 10,
            'enabled_manual_methods': ['CASH'],
            'created_by': self.payment_admin,
        }
        values.update(overrides)
        policy = PaymentPolicy.objects.create(**values)
        return publish_payment_policy(
            policy_id=policy.pk,
            actor=self.payment_admin,
        )

    def create_intent(
        self,
        hold,
        *,
        mode=PaymentIntent.Mode.DEPOSIT,
        key='payment-intent-key',
        actor=None,
    ):
        return create_payment_intent(
            hold=hold,
            mode=mode,
            idempotency_key=key,
            actor=actor or self.user,
        )

    def test_create_from_valid_hold_snapshots_amounts_policy_and_audit(self):
        hold = self.create_hold()
        result = self.create_intent(hold)

        self.assertTrue(result.created)
        intent = result.intent
        self.assertEqual(intent.status, PaymentIntent.Status.CREATED)
        self.assertEqual(intent.total_amount_snapshot, Decimal('1000.00'))
        self.assertEqual(intent.required_amount, Decimal('250.00'))
        self.assertEqual(intent.currency, 'ARS')
        self.assertLessEqual(intent.expires_at, hold.expires_at)
        self.assertEqual(intent.policy_snapshot['version'], 'PAYMENT-1')
        line = PaymentIntentLine.objects.get(intent=intent)
        self.assertEqual(line.nombre_snapshot, 'Servicio SlotHold')
        self.assertEqual(line.cantidad, 1)
        self.assertEqual(line.precio_unitario_snapshot, Decimal('1000.00'))
        self.assertEqual(line.descuento, Decimal('0.00'))
        self.assertEqual(line.subtotal, Decimal('1000.00'))
        audit = Auditoria.objects.get(
            tabla=PAYMENT_INTENT_CREATED,
            registro_id=intent.pk,
        )
        self.assertNotIn('payment-intent-key', str(audit.valor_nuevo))

    def test_full_and_percentage_rounding(self):
        self.service.precio_base = Decimal('999.99')
        self.service.save(update_fields=['precio_base'])
        hold = self.create_hold()
        deposit = self.create_intent(hold).intent
        self.assertEqual(deposit.required_amount, Decimal('250.00'))

        cancel_payment_intent(public_id=deposit.public_id, actor=self.user)
        other_request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        other_hold = self.create_hold(
            solicitud=other_request,
            actor=self.other_user,
            key='full-hold',
            starts_at=self.starts_at + timedelta(hours=2),
        )
        full = self.create_intent(
            other_hold,
            mode=PaymentIntent.Mode.FULL,
            key='full-key',
            actor=self.other_user,
        ).intent
        self.assertEqual(full.required_amount, Decimal('999.99'))

    def test_fixed_exceeds_total_reject_and_cap_are_explicit(self):
        self.publish_policy(
            version='FIXED-REJECT',
            deposit_kind=PaymentPolicy.DepositKind.FIXED,
            deposit_value=Decimal('1500.00'),
            fixed_exceeds_total_behavior=(
                PaymentPolicy.FixedExceedsTotalBehavior.REJECT
            ),
        )
        hold = self.create_hold()
        with self.assertRaises(PaymentIntentConflict) as rejected:
            self.create_intent(hold, key='fixed-reject')
        self.assertEqual(rejected.exception.code, 'FIXED_DEPOSIT_EXCEEDS_TOTAL')

        self.publish_policy(
            version='FIXED-CAP',
            deposit_kind=PaymentPolicy.DepositKind.FIXED,
            deposit_value=Decimal('1500.00'),
            fixed_exceeds_total_behavior=(
                PaymentPolicy.FixedExceedsTotalBehavior.CAP_TO_TOTAL
            ),
        )
        capped = self.create_intent(hold, key='fixed-cap').intent
        self.assertEqual(capped.required_amount, capped.total_amount_snapshot)

    def test_policy_mode_is_enforced(self):
        self.publish_policy(
            version='FULL-ONLY',
            allowed_mode=PaymentPolicy.AllowedMode.FULL_ONLY,
            deposit_kind=None,
            deposit_value=None,
            fixed_exceeds_total_behavior=None,
        )
        hold = self.create_hold()
        with self.assertRaises(PaymentIntentConflict) as denied:
            self.create_intent(hold)
        self.assertEqual(denied.exception.code, 'PAYMENT_MODE_NOT_ALLOWED')
        self.assertTrue(
            self.create_intent(
                hold,
                mode=PaymentIntent.Mode.FULL,
                key='full-only-key',
            ).succeeded
        )

    def test_multiservice_creates_all_lines_in_snapshot_order(self):
        second = Servicio.objects.create(
            nombre='Segundo servicio financiero',
            duracion_estimada=30,
            precio_base=Decimal('500.00'),
            activo=True,
        )
        old_evaluation = self.solicitud.evaluacion_vigente
        replacement = EvaluacionRiesgoTecnico.objects.create(
            cliente=self.cliente,
            politica=self.policy,
            outcome=TechnicalRiskOutcome.APTO,
            severity=0,
            fecha_solicitada=self.date,
            input_snapshot={
                'cliente_id': self.cliente.pk,
                'servicios': [
                    {'id': self.service.pk, 'nombre': self.service.nombre},
                    {'id': second.pk, 'nombre': second.nombre},
                ],
                'fecha_solicitada': self.date.isoformat(),
            },
            result_snapshot={
                'outcome': TechnicalRiskOutcome.APTO,
                'policy_version': self.policy.version,
                'rule_codes': [],
            },
        )
        EvaluacionRiesgoTecnico.objects._set_superseded_by(
            evaluation_id=old_evaluation.pk,
            replacement_id=replacement.pk,
        )
        self.solicitud.evaluacion_vigente = replacement
        self.solicitud.save(update_fields=['evaluacion_vigente'])
        SolicitudTecnicaServicio.objects.create(
            solicitud=self.solicitud,
            servicio=second,
            orden=1,
            nombre_snapshot=second.nombre,
        )
        hold = self.create_hold()

        intent = self.create_intent(hold).intent
        lines = list(intent.lines.order_by('orden'))
        self.assertEqual(len(lines), 2)
        self.assertEqual([line.orden for line in lines], [0, 1])
        self.assertEqual(intent.total_amount_snapshot, Decimal('1500.00'))
        self.assertEqual(intent.required_amount, Decimal('375.00'))

    def test_price_and_later_policy_change_do_not_mutate_snapshot(self):
        hold = self.create_hold()
        intent = self.create_intent(hold).intent
        self.service.precio_base = Decimal('9000.00')
        self.service.save(update_fields=['precio_base'])
        self.publish_policy(
            version='PAYMENT-2',
            deposit_value=Decimal('50.00'),
        )

        intent.refresh_from_db()
        line = intent.lines.get()
        self.assertEqual(intent.total_amount_snapshot, Decimal('1000.00'))
        self.assertEqual(intent.required_amount, Decimal('250.00'))
        self.assertEqual(line.precio_unitario_snapshot, Decimal('1000.00'))
        self.assertEqual(intent.policy_snapshot['version'], 'PAYMENT-1')
        self.assertEqual(intent.policy.status, PaymentPolicy.Status.RETIRED)

    def test_active_cardinality_and_idempotency(self):
        hold = self.create_hold()
        first = self.create_intent(hold, key='same-payment-key')
        retry = self.create_intent(hold, key='same-payment-key')
        self.assertTrue(first.created)
        self.assertFalse(retry.created)
        self.assertEqual(first.intent.pk, retry.intent.pk)
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_INTENT_CREATED).count(),
            1,
        )
        with self.assertRaises(PaymentIntentConflict) as active:
            self.create_intent(hold, key='different-payment-key')
        self.assertEqual(active.exception.code, 'ACTIVE_PAYMENT_INTENT_EXISTS')
        with self.assertRaises(PaymentIntentConflict) as changed_payload:
            self.create_intent(
                hold,
                key='same-payment-key',
                mode=PaymentIntent.Mode.FULL,
            )
        self.assertEqual(changed_payload.exception.code, 'IDEMPOTENCY_KEY_REUSED')

    def test_expired_released_and_consumed_holds_are_rejected(self):
        expired = self.direct_hold(
            created_at=timezone.now() - timedelta(minutes=20),
            expires_at=timezone.now() - timedelta(minutes=1),
            key='expired-payment-hold',
        )
        result = self.create_intent(expired, key='expired-payment-key')
        self.assertEqual(result.code, 'HOLD_EXPIRED')
        expired.refresh_from_db()
        self.assertEqual(expired.state, SlotHold.State.EXPIRED)

        released_request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        released = self.create_hold(
            solicitud=released_request,
            actor=self.other_user,
            starts_at=self.starts_at + timedelta(hours=2),
            key='released-payment-hold',
        )
        release_slot_hold(public_id=released.public_id, actor=self.other_user)
        with self.assertRaises(PaymentIntentConflict) as released_error:
            self.create_intent(
                released,
                key='released-payment-key',
                actor=self.other_user,
            )
        self.assertEqual(released_error.exception.code, 'HOLD_RELEASED')

        consumed_request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        consumed = self.create_hold(
            solicitud=consumed_request,
            actor=self.other_user,
            starts_at=self.starts_at + timedelta(hours=4),
            key='consumed-payment-hold',
        )
        create_confirmed_turno_from_locked_hold(
            hold=consumed,
            operation_key='consume-before-payment',
            actor=self.other_user,
        )
        with self.assertRaises(PaymentIntentConflict) as consumed_error:
            self.create_intent(
                consumed,
                key='consumed-payment-key',
                actor=self.other_user,
            )
        self.assertEqual(consumed_error.exception.code, 'HOLD_ALREADY_CONSUMED')
        self.assertFalse(
            PaymentIntent.objects.filter(
                slot_hold__in=[expired, released, consumed]
            ).exists()
        )

    def test_invalid_technical_request_is_rejected(self):
        hold = self.create_hold()
        self.solicitud.estado = self.solicitud.Estado.VENCIDA
        self.solicitud.save(update_fields=['estado'])
        with self.assertRaises(PaymentIntentConflict) as invalid:
            self.create_intent(hold)
        self.assertEqual(invalid.exception.code, 'TECHNICAL_REQUEST_INVALIDATED')

    def test_cancel_is_idempotent_releases_hold_and_blocks_direct_hold_release(self):
        hold = self.create_hold()
        intent = self.create_intent(hold).intent
        with self.assertRaises(SlotHoldConflict) as direct_release:
            release_slot_hold(public_id=hold.public_id, actor=self.user)
        self.assertEqual(
            getattr(direct_release.exception, 'code', None),
            'ACTIVE_PAYMENT_INTENT_EXISTS',
        )

        cancelled = cancel_payment_intent(
            public_id=intent.public_id,
            actor=self.user,
        )
        repeated = cancel_payment_intent(
            public_id=intent.public_id,
            actor=self.user,
        )
        self.assertTrue(cancelled.changed)
        self.assertFalse(repeated.changed)
        intent.refresh_from_db()
        hold.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CANCELLED)
        self.assertEqual(hold.state, SlotHold.State.RELEASED)
        self.assertEqual(
            hold.release_reason,
            SlotHold.ReleaseReason.PAYMENT_INTENT_CANCELLED,
        )
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_INTENT_CANCELLED).count(),
            1,
        )
        self.assertEqual(
            Auditoria.objects.filter(tabla=SLOT_HOLD_RELEASED).count(),
            1,
        )

    def test_expire_intent_releases_hold_and_hold_expiry_has_specific_reason(self):
        hold = self.create_hold()
        historical_now = timezone.now() - timedelta(minutes=20)
        from unittest.mock import patch
        with patch(
            'gestion.payment_intent_services.database_now',
            return_value=historical_now,
        ):
            intent = self.create_intent(hold).intent
        expired = expire_payment_intent(intent_id=intent.pk)
        self.assertTrue(expired.changed)
        self.assertEqual(expired.code, 'INTENT_EXPIRED')
        hold.refresh_from_db()
        self.assertEqual(hold.state, SlotHold.State.RELEASED)
        self.assertEqual(
            hold.release_reason,
            SlotHold.ReleaseReason.PAYMENT_INTENT_EXPIRED,
        )

        other_request = self.create_approved_request(
            self.other_cliente,
            self.service,
            self.date,
        )
        other_hold = self.create_hold(
            solicitud=other_request,
            actor=self.other_user,
            starts_at=self.starts_at + timedelta(hours=2),
            key='hold-expiry-payment-hold',
        )
        other_intent = self.create_intent(
            other_hold,
            key='hold-expiry-payment-key',
            actor=self.other_user,
        ).intent
        now = timezone.now()
        models.QuerySet.update(
            SlotHold.objects.filter(pk=other_hold.pk),
            created_at=now - timedelta(minutes=2),
            expires_at=now - timedelta(minutes=1),
        )
        result = expire_payment_intent(intent_id=other_intent.pk)
        self.assertEqual(result.code, 'HOLD_EXPIRED')
        other_hold.refresh_from_db()
        self.assertEqual(other_hold.state, SlotHold.State.EXPIRED)
        self.assertEqual(
            Auditoria.objects.filter(tabla=PAYMENT_INTENT_EXPIRED).count(),
            2,
        )

    def test_intent_and_lines_cannot_be_updated_deleted_or_resurrected(self):
        hold = self.create_hold()
        intent = self.create_intent(hold).intent
        line = intent.lines.get()
        intent.required_amount = Decimal('1.00')
        with self.assertRaises(ValidationError):
            intent.save()
        with self.assertRaises(ValidationError):
            PaymentIntent.objects.filter(pk=intent.pk).update(
                required_amount=Decimal('1.00')
            )
        with self.assertRaises(ValidationError):
            intent.delete()
        line.subtotal = Decimal('1.00')
        with self.assertRaises(ValidationError):
            line.save()
        with self.assertRaises(ValidationError):
            PaymentIntentLine.objects.filter(pk=line.pk).delete()
        with self.assertRaises(ValidationError):
            PaymentIntentLine.objects.create(
                intent=intent,
                servicio=self.service,
                orden=2,
                nombre_snapshot='Línea no autorizada',
                cantidad=1,
                precio_unitario_snapshot=Decimal('1000.00'),
                descuento=Decimal('0.00'),
                subtotal=Decimal('1000.00'),
                moneda='ARS',
            )
        with self.assertRaises(ValidationError):
            PaymentIntent.objects.create(
                solicitud=intent.solicitud,
                slot_hold=intent.slot_hold,
                cliente=intent.cliente,
                policy=intent.policy,
                policy_snapshot=intent.policy_snapshot,
                mode=intent.mode,
                total_amount_snapshot=intent.total_amount_snapshot,
                required_amount=intent.required_amount,
                currency=intent.currency,
                expires_at=intent.expires_at,
                created_at=intent.created_at,
                idempotency_key='direct-creation-forbidden',
                created_by=self.user,
            )

        cancel_payment_intent(public_id=intent.public_id, actor=self.user)
        intent.refresh_from_db()
        intent.status = PaymentIntent.Status.CREATED
        intent.terminal_at = None
        intent.terminal_reason = ''
        with self.assertRaises(ValidationError):
            intent.save()
        with self.assertRaises(ValidationError):
            PaymentIntent.objects.filter(pk=intent.pk).update(
                status=PaymentIntent.Status.CREATED,
                terminal_at=None,
                terminal_reason='',
            )
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CANCELLED)

    def test_api_ownership_read_create_cancel_and_no_generic_mutation(self):
        hold = self.create_hold()
        owner_api = APIClient()
        owner_api.force_authenticate(self.user)
        other_api = APIClient()
        other_api.force_authenticate(self.other_user)
        list_url = reverse('payment-intent-list')

        bad = owner_api.post(
            list_url,
            {
                'slot_hold_public_id': str(hold.public_id),
                'mode': PaymentIntent.Mode.DEPOSIT,
                'total_amount_snapshot': '1.00',
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='api-payment-bad',
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        created = owner_api.post(
            list_url,
            {
                'slot_hold_public_id': str(hold.public_id),
                'mode': PaymentIntent.Mode.DEPOSIT,
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY='api-payment-key',
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        public_id = created.data['public_id']
        detail_url = reverse('payment-intent-detail', args=[public_id])
        self.assertEqual(owner_api.get(detail_url).status_code, status.HTTP_200_OK)
        self.assertEqual(other_api.get(detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(other_api.patch(detail_url, {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(other_api.delete(detail_url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(
            other_api.post(
                reverse('payment-intent-cancel', args=[public_id]),
                {},
                format='json',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        cancelled = owner_api.post(
            reverse('payment-intent-cancel', args=[public_id]),
            {},
            format='json',
        )
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertTrue(cancelled.data['changed'])

    def test_service_hides_other_owner(self):
        hold = self.create_hold()
        with self.assertRaises(PaymentIntentNotFound):
            self.create_intent(hold, actor=self.other_user)
