import hashlib
import threading
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, DiagnosticoCapilar
from usuarios.models import (
    Cliente,
    Usuario,
    WalkInClientOperation,
    WebAccessClaimToken,
)
from usuarios.roles import BusinessRole, get_business_roles
from usuarios.walkin_client_services import (
    WalkInClientConflict,
    WalkInClientError,
    WalkInClientPermissionDenied,
    create_walkin_client,
)
from usuarios.web_access_claim_services import (
    WebAccessClaimError,
    confirm_web_access_claim,
    request_web_access_claim,
)


VALID_PHONE = '+54 9 11 6123-4567'
VALID_PHONE_E164 = '+5491161234567'


class WalkInFixtureMixin:
    def create_user(self, email, *, password='ActorPassword!2026', **extra):
        return Usuario.objects.create_user(
            email=email,
            password=password,
            **extra,
        )

    def create_actor(self, email='walkin-actor@example.com', *, active=True):
        Group.objects.get_or_create(name=BusinessRole.CLIENTE)
        actor = self.create_user(email, is_active=active)
        permission = Permission.objects.get(
            content_type__app_label='usuarios',
            codename='create_walkin_client',
        )
        actor.user_permissions.add(permission)
        return actor

    @staticmethod
    def command(**overrides):
        values = {
            'idempotency_key': 'walkin-key-001',
            'first_name': 'Ana',
            'last_name': 'Pérez',
            'reason': 'Alta presencial en recepción',
            'email': 'ana.walkin@example.com',
            'telefono': '',
            'zona': 'Centro',
        }
        values.update(overrides)
        return values

    def create_existing_client(
        self,
        *,
        email='existing@example.com',
        phone=VALID_PHONE_E164,
        first_name='Eva',
        last_name='Existente',
    ):
        user = self.create_user(
            email,
            first_name=first_name,
            last_name=last_name,
            web_access_status=Usuario.WebAccessStatus.CLAIMED,
        )
        return Cliente.objects.create(
            usuario=user,
            numero=phone,
            numero_normalizado=phone,
            numero_normalizacion_estado=Cliente.PhoneNormalizationStatus.VALID,
        )


class WalkInClientServiceTests(WalkInFixtureMixin, TestCase):
    def setUp(self):
        self.actor = self.create_actor()

    def test_creates_active_pending_client_with_email_without_password(self):
        result = create_walkin_client(actor=self.actor, **self.command())

        user = Usuario.objects.get(pk=result.user_id)
        client = Cliente.objects.get(pk=result.cliente_id)
        self.assertTrue(result.created)
        self.assertFalse(result.recovered)
        self.assertTrue(user.is_active)
        self.assertTrue(client.activo)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(
            user.web_access_status,
            Usuario.WebAccessStatus.PENDING_CLAIM,
        )
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertFalse(DiagnosticoCapilar.objects.filter(cliente=client).exists())
        self.assertTrue(
            Auditoria.objects.filter(
                tabla='WalkInClientOperation',
                registro_id__isnull=False,
            ).exists()
        )

    def test_creates_multiple_clients_without_email_and_normalizes_phone(self):
        first = create_walkin_client(
            actor=self.actor,
            **self.command(
                idempotency_key='phone-only-1',
                email=None,
                telefono=VALID_PHONE,
            ),
        )
        second = create_walkin_client(
            actor=self.actor,
            **self.command(
                idempotency_key='phone-only-2',
                first_name='Berta',
                last_name='López',
                email=None,
                telefono='+54 9 351 612-3456',
            ),
        )

        users = Usuario.objects.filter(pk__in=[first.user_id, second.user_id])
        self.assertEqual(users.filter(email__isnull=True).count(), 2)
        self.assertTrue(all(not user.has_usable_password() for user in users))
        client = Cliente.objects.get(pk=first.cliente_id)
        self.assertEqual(client.numero, VALID_PHONE)
        self.assertEqual(client.numero_normalizado, VALID_PHONE_E164)
        self.assertEqual(
            client.numero_normalizacion_estado,
            Cliente.PhoneNormalizationStatus.VALID,
        )

    def test_requires_one_valid_contact(self):
        with self.assertRaises(WalkInClientError) as context:
            create_walkin_client(
                actor=self.actor,
                **self.command(email='', telefono=''),
            )
        self.assertEqual(context.exception.code, 'CONTACT_REQUIRED')
        self.assertEqual(WalkInClientOperation.objects.count(), 0)

    def test_rejects_invalid_phone(self):
        with self.assertRaises(WalkInClientError) as context:
            create_walkin_client(
                actor=self.actor,
                **self.command(email=None, telefono='123'),
            )
        self.assertEqual(context.exception.code, 'INVALID_PHONE')

    def test_permission_and_inactive_actor_are_rejected(self):
        without_permission = self.create_user('without-permission@example.com')
        inactive = self.create_actor('inactive-actor@example.com', active=False)
        for actor in (without_permission, inactive):
            with self.subTest(actor=actor.pk):
                with self.assertRaises(WalkInClientPermissionDenied):
                    create_walkin_client(
                        actor=actor,
                        **self.command(
                            idempotency_key=f'denied-{actor.pk}',
                            email=f'denied-{actor.pk}@example.com',
                        ),
                    )

    def test_same_key_and_fingerprint_returns_same_stable_result(self):
        command = self.command(idempotency_key='stable-retry')
        first = create_walkin_client(actor=self.actor, **command)
        second = create_walkin_client(actor=self.actor, **command)

        self.assertEqual(first.cliente_id, second.cliente_id)
        self.assertEqual(first.operation_id, second.operation_id)
        self.assertFalse(first.recovered)
        self.assertTrue(second.recovered)
        self.assertEqual(WalkInClientOperation.objects.count(), 1)

    def test_same_key_with_different_payload_conflicts(self):
        command = self.command(idempotency_key='incompatible-retry')
        create_walkin_client(actor=self.actor, **command)
        with self.assertRaises(WalkInClientConflict) as context:
            create_walkin_client(
                actor=self.actor,
                **{**command, 'last_name': 'Distinto'},
            )
        self.assertEqual(context.exception.code, 'IDEMPOTENCY_KEY_REUSED')

    def test_email_match_is_case_insensitive_and_cannot_create_distinct(self):
        existing = self.create_existing_client(email='Duplicate@Example.com')
        command = self.command(email='duplicate@example.com')
        with self.assertRaises(WalkInClientConflict) as initial:
            create_walkin_client(actor=self.actor, **command)
        self.assertEqual(initial.exception.code, 'DUPLICATE_REVIEW_REQUIRED')
        self.assertEqual(initial.exception.candidates[0]['cliente_id'], existing.pk)

        with self.assertRaises(WalkInClientConflict) as resolved:
            create_walkin_client(
                actor=self.actor,
                **{
                    **command,
                    'duplicate_resolution': 'CREATE_DISTINCT',
                    'reviewed_candidate_ids': [existing.pk],
                    'duplicate_reason': 'Es una persona diferente',
                },
            )
        self.assertEqual(resolved.exception.code, 'EMAIL_ALREADY_EXISTS')

    def test_phone_match_requires_real_human_resolution(self):
        existing = self.create_existing_client(email='phone-owner@example.com')
        base = self.command(
            idempotency_key='phone-match',
            email='other-person@example.com',
            telefono=VALID_PHONE,
        )
        with self.assertRaises(WalkInClientConflict) as initial:
            create_walkin_client(actor=self.actor, **base)
        self.assertEqual(initial.exception.code, 'DUPLICATE_REVIEW_REQUIRED')

        with self.assertRaises(WalkInClientError) as no_reason:
            create_walkin_client(
                actor=self.actor,
                **{
                    **base,
                    'duplicate_resolution': 'CREATE_DISTINCT',
                    'reviewed_candidate_ids': [existing.pk],
                },
            )
        self.assertEqual(no_reason.exception.code, 'DUPLICATE_REASON_REQUIRED')

        created = create_walkin_client(
            actor=self.actor,
            **{
                **base,
                'duplicate_resolution': 'CREATE_DISTINCT',
                'reviewed_candidate_ids': [existing.pk],
                'duplicate_reason': 'Contacto compartido entre familiares',
            },
        )
        self.assertNotEqual(created.cliente_id, existing.pk)
        self.assertEqual(
            Cliente.objects.filter(numero_normalizado=VALID_PHONE_E164).count(),
            2,
        )

    def test_use_existing_persists_selection_without_new_identity(self):
        existing = self.create_existing_client()
        user_count = Usuario.objects.count()
        result = create_walkin_client(
            actor=self.actor,
            **self.command(
                idempotency_key='use-existing',
                email='existing@example.com',
                duplicate_resolution='USE_EXISTING',
                candidate_client_id=existing.pk,
                reviewed_candidate_ids=[existing.pk],
            ),
        )
        self.assertFalse(result.created)
        self.assertEqual(result.cliente_id, existing.pk)
        self.assertEqual(Usuario.objects.count(), user_count)

    @patch('usuarios.walkin_client_services.assign_business_role')
    def test_role_failure_rolls_back_whole_aggregate(self, mocked_assign):
        mocked_assign.side_effect = RuntimeError('forced role failure')
        with self.assertRaises(WalkInClientConflict):
            create_walkin_client(
                actor=self.actor,
                **self.command(idempotency_key='role-rollback'),
            )
        self.assertFalse(
            Usuario.objects.filter(email='ana.walkin@example.com').exists()
        )
        self.assertEqual(WalkInClientOperation.objects.count(), 0)

    @patch('usuarios.walkin_client_services.Auditoria.objects.create')
    def test_audit_failure_rolls_back_whole_aggregate(self, mocked_create):
        mocked_create.side_effect = RuntimeError('forced audit failure')
        with self.assertRaises(WalkInClientConflict):
            create_walkin_client(
                actor=self.actor,
                **self.command(idempotency_key='audit-rollback'),
            )
        self.assertFalse(
            Usuario.objects.filter(email='ana.walkin@example.com').exists()
        )
        self.assertEqual(WalkInClientOperation.objects.count(), 0)


class WalkInClientApiTests(WalkInFixtureMixin, APITestCase):
    def setUp(self):
        self.actor = self.create_actor('api-walkin-actor@example.com')
        self.client.force_authenticate(self.actor)
        self.create_url = reverse('walkin-client-create')
        self.selector_url = reverse('walkin-client-selector')

    @staticmethod
    def payload(**overrides):
        values = {
            'first_name': 'Ana',
            'last_name': 'Pérez',
            'email': 'api-ana@example.com',
            'telefono': '',
            'zona': 'Centro',
            'motivo': 'Alta presencial en recepción',
        }
        values.update(overrides)
        return values

    def post_create(self, payload=None, *, key='api-key-001'):
        return self.client.post(
            self.create_url,
            payload or self.payload(),
            format='json',
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_api_returns_minimized_created_and_recovered_contract(self):
        first = self.post_create()
        second = self.post_create()

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['cliente_id'], second.data['cliente_id'])
        self.assertEqual(first.data['operation_id'], second.data['operation_id'])
        self.assertEqual(first.data['web_access_status'], 'PENDING_CLAIM')
        self.assertNotIn('password', first.data)
        self.assertNotIn('token', first.data)
        self.assertNotIn('numero', first.data)

    def test_api_differentiates_validation_permission_and_conflict(self):
        invalid = self.post_create(self.payload(email='', telefono='123'))
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        first = self.post_create(key='conflict-key')
        conflict = self.post_create(
            self.payload(last_name='Otro'),
            key='conflict-key',
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict.data['error']['code'], 'IDEMPOTENCY_KEY_REUSED')

        denied = self.create_user('api-denied@example.com')
        self.client.force_authenticate(denied)
        denied_response = self.post_create(key='denied-key')
        self.assertEqual(denied_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_response_contains_only_minimized_candidates(self):
        existing = self.create_existing_client(
            email='candidate@example.com',
            phone=VALID_PHONE_E164,
        )
        response = self.post_create(
            self.payload(email='candidate@example.com'),
            key='candidate-key',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        candidate = response.data['error']['candidates'][0]
        self.assertEqual(candidate['cliente_id'], existing.pk)
        self.assertEqual(
            set(candidate),
            {
                'cliente_id',
                'display_name',
                'masked_email',
                'masked_phone',
                'active',
                'web_access_status',
            },
        )
        self.assertNotEqual(candidate['masked_email'], 'candidate@example.com')

    def test_use_existing_outside_reviewed_scope_returns_404(self):
        existing = self.create_existing_client(email='scoped@example.com')
        response = self.post_create(
            self.payload(
                email='scoped@example.com',
                duplicate_resolution='USE_EXISTING',
                candidate_client_id=existing.pk + 999,
                reviewed_candidate_ids=[existing.pk],
            ),
            key='out-of-scope-key',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error']['code'], 'CLIENT_OUT_OF_SCOPE')

    def test_selector_requires_query_permission_and_limits_output(self):
        existing = self.create_existing_client(
            email='selector@example.com',
            first_name='Marina',
            last_name='Selector',
        )
        response = self.client.get(self.selector_url, {'q': 'Marina'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], 1)
        item = response.data['results'][0]
        self.assertEqual(item['cliente_id'], existing.pk)
        self.assertNotIn('email', item)
        self.assertNotIn('numero', item)
        self.assertNotIn('diagnostico', item)

        no_query = self.client.get(self.selector_url)
        self.assertEqual(no_query.status_code, status.HTTP_400_BAD_REQUEST)

        denied = self.create_user('selector-denied@example.com')
        self.client.force_authenticate(denied)
        forbidden = self.client.get(self.selector_url, {'q': 'Marina'})
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_public_client_cannot_invoke_assisted_creation(self):
        public_client = self.create_existing_client(email='public-client@example.com')
        self.client.force_authenticate(public_client.usuario)
        response = self.post_create(key='public-denied')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class WebAccessClaimTests(WalkInFixtureMixin, TestCase):
    password = 'ClaimedAccess!2026'

    def create_pending(self, *, email='pending-claim@example.com'):
        user = Usuario(
            email=email,
            first_name='Clara',
            last_name='Pendiente',
            is_active=True,
            web_access_status=Usuario.WebAccessStatus.PENDING_CLAIM,
        )
        user.set_unusable_password()
        user.save()
        client = Cliente.objects.create(usuario=user, activo=True)
        return user, client

    @staticmethod
    def token_from_email():
        body = mail.outbox[-1].body
        return body.split('/reclamar-acceso/', 1)[1].split()[0]

    def test_claim_request_is_generic_and_token_is_digest_only(self):
        user, _ = self.create_pending()
        sent = request_web_access_claim(email=user.email)
        missing = request_web_access_claim(email='missing@example.com')

        self.assertTrue(sent.sent)
        self.assertFalse(missing.sent)
        raw_token = self.token_from_email()
        token = WebAccessClaimToken.objects.get(usuario=user)
        self.assertNotEqual(token.token_digest, raw_token)
        self.assertEqual(
            token.token_digest,
            hashlib.sha256(raw_token.encode('utf-8')).hexdigest(),
        )

    def test_claim_is_single_use_and_enables_web_credentials(self):
        user, client = self.create_pending()
        request_web_access_claim(email=user.email)
        raw_token = self.token_from_email()

        result = confirm_web_access_claim(
            token=raw_token,
            new_password=self.password,
        )
        user.refresh_from_db()
        self.assertEqual(result.cliente_id, client.pk)
        self.assertEqual(user.web_access_status, Usuario.WebAccessStatus.CLAIMED)
        self.assertTrue(user.check_password(self.password))

        with self.assertRaises(WebAccessClaimError) as reused:
            confirm_web_access_claim(
                token=raw_token,
                new_password=self.password,
            )
        self.assertEqual(reused.exception.code, 'INVALID_OR_EXPIRED_CLAIM')

    def test_expired_claim_is_rejected(self):
        user, _ = self.create_pending()
        raw = 'expired-raw-token'
        WebAccessClaimToken.objects.create(
            usuario=user,
            token_digest=hashlib.sha256(raw.encode('utf-8')).hexdigest(),
            email_fingerprint=hashlib.sha256(
                user.email.casefold().encode('utf-8')
            ).hexdigest(),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with self.assertRaises(WebAccessClaimError) as expired:
            confirm_web_access_claim(token=raw, new_password=self.password)
        self.assertEqual(expired.exception.code, 'INVALID_OR_EXPIRED_CLAIM')

    def test_client_without_email_has_no_verifiable_claim_channel(self):
        user, _ = self.create_pending(email=None)
        self.assertEqual(user.web_access_status, Usuario.WebAccessStatus.PENDING_CLAIM)
        self.assertFalse(user.has_usable_password())
        with self.assertRaises(WebAccessClaimError):
            request_web_access_claim(email=None)
        self.assertEqual(WebAccessClaimToken.objects.count(), 0)

    def test_claim_api_does_not_enumerate_accounts(self):
        user, _ = self.create_pending()
        url = reverse('web-access-claim-request')
        existing = self.client.post(url, {'email': user.email}, format='json')
        missing = self.client.post(
            url,
            {'email': 'missing@example.com'},
            format='json',
        )
        self.assertEqual(existing.status_code, status.HTTP_200_OK)
        self.assertEqual(missing.status_code, status.HTTP_200_OK)
        self.assertEqual(existing.data, missing.data)


class AuthenticationCompatibilityTests(WalkInFixtureMixin, APITestCase):
    password = 'WebAccess!2026'

    def pending_user(self, *, email):
        user = Usuario(
            email=email,
            first_name='Web',
            last_name='Pending',
            is_active=True,
            web_access_status=Usuario.WebAccessStatus.PENDING_CLAIM,
        )
        user.set_unusable_password()
        user.save()
        Cliente.objects.create(usuario=user)
        return user

    def test_pending_is_rejected_by_custom_login_and_jwt(self):
        user = self.pending_user(email='pending-login@example.com')
        custom = self.client.post(
            reverse('login'),
            {'email': user.email, 'password': self.password},
            format='json',
        )
        jwt = self.client.post(
            reverse('token_obtain_pair'),
            {'email': user.email, 'password': self.password},
            format='json',
        )
        self.assertEqual(custom.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(jwt.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_multiple_null_emails_do_not_make_login_or_reset_ambiguous(self):
        self.pending_user(email=None)
        self.pending_user(email=None)
        login = self.client.post(
            reverse('login'),
            {'email': None, 'password': self.password},
            format='json',
        )
        reset = self.client.post(
            reverse('password-reset-request'),
            {'email': None},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reset.status_code, status.HTTP_400_BAD_REQUEST)

    def test_claimed_and_historical_web_users_keep_login_compatibility(self):
        claimed = self.create_user(
            'claimed-login@example.com',
            password=self.password,
            web_access_status=Usuario.WebAccessStatus.CLAIMED,
        )
        legacy = self.create_user(
            'legacy-login@example.com',
            password=self.password,
        )
        for user in (claimed, legacy):
            with self.subTest(status=user.web_access_status):
                response = self.client.post(
                    reverse('token_obtain_pair'),
                    {'email': user.email, 'password': self.password},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertIn('access', response.data)

    def test_database_constraints_protect_pending_credentials(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                user = Usuario(
                    email='',
                    web_access_status=Usuario.WebAccessStatus.PENDING_CLAIM,
                )
                user.set_unusable_password()
                user.save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                user = Usuario(
                    email=None,
                    web_access_status=Usuario.WebAccessStatus.PENDING_CLAIM,
                )
                user.set_password(self.password)
                user.save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                user = Usuario(
                    email=None,
                    web_access_status=Usuario.WebAccessStatus.CLAIMED,
                )
                user.set_password(self.password)
                user.save()


class WalkInConcurrencyTests(WalkInFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        Group.objects.get_or_create(name=BusinessRole.CLIENTE)
        self.actor = self.create_actor('concurrent-actor@example.com')

    def run_workers(self, worker, count=2):
        barrier = threading.Barrier(count)
        results = []
        result_lock = threading.Lock()

        def wrapped(index):
            close_old_connections()
            try:
                value = worker(index, barrier)
                outcome = ('ok', value)
            except Exception as exc:  # captured for deterministic assertions
                outcome = ('error', exc)
            finally:
                close_old_connections()
            with result_lock:
                results.append(outcome)

        threads = [
            threading.Thread(target=wrapped, args=(index,))
            for index in range(count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), 'Concurrent worker did not finish.')
        return results

    def test_same_key_concurrently_creates_one_client_and_one_ledger(self):
        actor_id = self.actor.pk

        def worker(_index, barrier):
            actor = Usuario.objects.get(pk=actor_id)
            barrier.wait(timeout=10)
            return create_walkin_client(
                actor=actor,
                **self.command(
                    idempotency_key='same-concurrent-key',
                    email='same-concurrent@example.com',
                ),
            )

        outcomes = self.run_workers(worker)
        self.assertTrue(all(kind == 'ok' for kind, _ in outcomes), outcomes)
        results = [value for _, value in outcomes]
        self.assertEqual({result.cliente_id for result in results}, {results[0].cliente_id})
        self.assertEqual(sum(result.recovered for result in results), 1)
        self.assertEqual(WalkInClientOperation.objects.count(), 1)
        self.assertEqual(
            Usuario.objects.filter(email='same-concurrent@example.com').count(),
            1,
        )

    def test_different_keys_same_identity_do_not_create_racing_duplicates(self):
        actor_id = self.actor.pk

        def worker(index, barrier):
            actor = Usuario.objects.get(pk=actor_id)
            barrier.wait(timeout=10)
            return create_walkin_client(
                actor=actor,
                **self.command(
                    idempotency_key=f'different-key-{index}',
                    email='one-identity@example.com',
                ),
            )

        outcomes = self.run_workers(worker)
        self.assertEqual(sum(kind == 'ok' for kind, _ in outcomes), 1, outcomes)
        errors = [value for kind, value in outcomes if kind == 'error']
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], WalkInClientConflict)
        self.assertEqual(errors[0].code, 'DUPLICATE_REVIEW_REQUIRED')
        self.assertEqual(
            Usuario.objects.filter(email='one-identity@example.com').count(),
            1,
        )

    def test_claim_token_concurrent_consumption_succeeds_once(self):
        user = Usuario(
            email='claim-concurrent@example.com',
            is_active=True,
            web_access_status=Usuario.WebAccessStatus.PENDING_CLAIM,
        )
        user.set_unusable_password()
        user.save()
        Cliente.objects.create(usuario=user)
        raw = 'concurrent-claim-token'
        WebAccessClaimToken.objects.create(
            usuario=user,
            token_digest=hashlib.sha256(raw.encode('utf-8')).hexdigest(),
            email_fingerprint=hashlib.sha256(
                user.email.casefold().encode('utf-8')
            ).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        def worker(_index, barrier):
            barrier.wait(timeout=10)
            return confirm_web_access_claim(
                token=raw,
                new_password='ConcurrentClaim!2026',
            )

        outcomes = self.run_workers(worker)
        self.assertEqual(sum(kind == 'ok' for kind, _ in outcomes), 1, outcomes)
        errors = [value for kind, value in outcomes if kind == 'error']
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], WebAccessClaimError)
        user.refresh_from_db()
        self.assertEqual(user.web_access_status, Usuario.WebAccessStatus.CLAIMED)
