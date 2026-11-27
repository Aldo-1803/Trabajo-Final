from django.contrib.auth.models import update_last_login
from rest_framework import exceptions
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenObtainSerializer,
)
from rest_framework_simplejwt.settings import api_settings


class ClaimAwareTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue JWTs only after a pending walk-in account is claimed."""

    def validate(self, attrs):
        data = TokenObtainSerializer.validate(self, attrs)
        if self.user.web_access_status == self.user.WebAccessStatus.PENDING_CLAIM:
            raise exceptions.AuthenticationFailed(
                'La cuenta todavía no reclamó su acceso web.',
                'web_access_pending_claim',
            )
        refresh = self.get_token(self.user)
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        return data
