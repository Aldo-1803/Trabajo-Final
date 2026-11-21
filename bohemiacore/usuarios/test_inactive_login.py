from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from gestion.models import Auditoria
from usuarios.access_services import (
    ACCOUNT_DEACTIVATION_AUDIT_TABLE,
    deactivate_account,
    reactivate_account,
)
from usuarios.models import Cliente
from usuarios.models import Usuario
from usuarios.roles import BusinessRole


class InactiveUserLoginTests(APITestCase):
    password = 'StrongTestPass123!'

    def create_user(self, email, *, is_active=True):
        return Usuario.objects.create_user(
            email=email,
            password=self.password,
            is_active=is_active,
        )

    def credentials(self, email):
        return {'email': email, 'password': self.password}

    def test_custom_login_rejects_inactive_user(self):
        user = self.create_user(
            'inactive-custom-login@test.com',
            is_active=False,
        )

        response = self.client.post(
            reverse('login'),
            self.credentials(user.email),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)

    def test_standard_jwt_endpoint_rejects_inactive_user(self):
        user = self.create_user(
            'inactive-standard-login@test.com',
            is_active=False,
        )

        response = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(user.email),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)

    def test_existing_access_tokens_are_rejected_after_deactivation(self):
        user = self.create_user('existing-token@test.com')
        pair = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(user.email),
            format='json',
        )
        self.assertEqual(pair.status_code, status.HTTP_200_OK)

        Usuario.objects.filter(pk=user.pk).update(is_active=False)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {pair.data['access']}"
        )

        protected_response = self.client.get(reverse('perfil'))

        self.assertEqual(
            protected_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_existing_refresh_token_is_rejected_after_deactivation(self):
        user = self.create_user('existing-refresh@test.com')
        pair = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(user.email),
            format='json',
        )
        self.assertEqual(pair.status_code, status.HTTP_200_OK)
        Usuario.objects.filter(pk=user.pk).update(is_active=False)

        refresh_response = self.client.post(
            reverse('token_refresh'),
            {'refresh': pair.data['refresh']},
            format='json',
        )

        self.assertEqual(
            refresh_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertNotIn('access', refresh_response.data)

    def test_valid_reactivation_restores_custom_and_standard_login(self):
        target = self.create_user(
            'reactivated-login@test.com',
            is_active=False,
        )
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        Cliente.objects.create(usuario=target)
        actor = self.create_user('reactivated-login-actor@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        ))

        before = self.client.post(
            reverse('login'),
            self.credentials(target.email),
            format='json',
        )
        self.assertEqual(before.status_code, status.HTTP_401_UNAUTHORIZED)

        result = reactivate_account(
            actor,
            target,
            'Reactivacion para recuperar acceso',
        )

        self.assertTrue(result.changed)
        custom_login = self.client.post(
            reverse('login'),
            self.credentials(target.email),
            format='json',
        )
        standard_login = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(target.email),
            format='json',
        )
        self.assertEqual(custom_login.status_code, status.HTTP_200_OK)
        self.assertEqual(standard_login.status_code, status.HTTP_200_OK)
        self.assertIn('access', custom_login.data)
        self.assertIn('access', standard_login.data)

    def test_account_cycle_blacklists_refresh_but_access_risk_is_explicit(self):
        target = self.create_user('token-cycle@test.com')
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        Cliente.objects.create(usuario=target)
        actor = self.create_user('token-cycle-actor@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        ))
        pair = self.client.post(
            reverse('token_obtain_pair'),
            self.credentials(target.email),
            format='json',
        )
        self.assertEqual(pair.status_code, status.HTTP_200_OK)

        deactivation = deactivate_account(
            actor,
            target,
            'Baja con revocacion de refresh',
        )

        self.assertEqual(deactivation.refresh_tokens_revoked, 1)
        self.assertEqual(BlacklistedToken.objects.count(), 1)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {pair.data['access']}"
        )
        self.assertEqual(
            self.client.get(reverse('perfil')).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                reverse('token_refresh'),
                {'refresh': pair.data['refresh']},
                format='json',
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        reactivation = reactivate_account(
            actor,
            target,
            'Reactivacion posterior segura',
        )

        self.assertIn(
            'PREEXISTING_ACCESS_TOKENS_MAY_REGAIN_VALIDITY',
            reactivation.warnings,
        )
        self.assertEqual(reactivation.refresh_tokens_revoked, 0)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {pair.data['access']}"
        )
        self.assertEqual(
            self.client.get(reverse('perfil')).status_code,
            status.HTTP_200_OK,
        )
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                reverse('token_refresh'),
                {'refresh': pair.data['refresh']},
                format='json',
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_reactivation_blacklists_refresh_registered_while_inactive(self):
        target = self.create_user(
            'inactive-outstanding@test.com',
            is_active=False,
        )
        target.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        Cliente.objects.create(usuario=target)
        actor = self.create_user('inactive-outstanding-actor@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        ))
        refresh = RefreshToken.for_user(target)

        result = reactivate_account(
            actor,
            target,
            'Reactivar revocando refresh pendiente',
        )

        self.assertEqual(result.refresh_tokens_revoked, 1)
        response = self.client.post(
            reverse('token_refresh'),
            {'refresh': str(refresh)},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_blacklist_failure_rolls_back_deactivation_and_audit(self):
        from unittest.mock import patch

        target = self.create_user('blacklist-rollback@test.com')
        RefreshToken.for_user(target)
        actor = self.create_user('blacklist-rollback-actor@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        ))

        with patch(
            'usuarios.access_services.BlacklistedToken.objects.get_or_create',
            side_effect=RuntimeError('blacklist unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                deactivate_account(
                    actor,
                    target,
                    'Baja que debe revertirse',
                )

        target.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertFalse(BlacklistedToken.objects.exists())
        self.assertFalse(Auditoria.objects.filter(
            tabla=ACCOUNT_DEACTIVATION_AUDIT_TABLE,
            registro_id=target.pk,
        ).exists())

    def test_repeated_deactivation_does_not_duplicate_blacklist_or_audit(self):
        target = self.create_user('token-idempotence@test.com')
        RefreshToken.for_user(target)
        actor = self.create_user('token-idempotence-actor@test.com')
        actor.user_permissions.add(Permission.objects.get(
            content_type__app_label='usuarios',
            codename='manage_users',
        ))

        first = deactivate_account(actor, target, 'Primera baja segura')
        second = deactivate_account(actor, target, 'Repeticion idempotente')

        self.assertTrue(first.changed)
        self.assertEqual(first.refresh_tokens_revoked, 1)
        self.assertFalse(second.changed)
        self.assertEqual(second.refresh_tokens_revoked, 0)
        self.assertEqual(BlacklistedToken.objects.count(), 1)
        self.assertEqual(Auditoria.objects.filter(
            tabla=ACCOUNT_DEACTIVATION_AUDIT_TABLE,
            registro_id=target.pk,
        ).count(), 1)
