import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from gestion.models import Auditoria

from .models import Cliente, WebAccessClaimToken


CLAIM_TOKEN_TTL = timedelta(minutes=60)
WEB_ACCESS_CLAIM_AUDIT_TABLE = 'WebAccessClaim'
WEB_ACCESS_CLAIM_REQUESTED_EVENT = 'WEB_ACCESS_CLAIM_REQUESTED'
WEB_ACCESS_CLAIM_COMPLETED_EVENT = 'WEB_ACCESS_CLAIM_COMPLETED'
WEB_ACCESS_CLAIM_SOURCE = 'usuarios.web_access_claim_services'


class WebAccessClaimError(ValueError):
    def __init__(self, code, detail, field=None):
        self.code = code
        self.detail = detail
        self.field = field
        super().__init__(detail)


@dataclass(frozen=True)
class ClaimRequestResult:
    sent: bool


@dataclass(frozen=True)
class ClaimConfirmationResult:
    user_id: int
    cliente_id: int
    web_access_status: str


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _normalize_email(email, user_model):
    if not isinstance(email, str):
        raise WebAccessClaimError('INVALID_EMAIL', 'Debe informar un email válido.', 'email')
    normalized = user_model.objects.normalize_email(email.strip())
    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise WebAccessClaimError(
            'INVALID_EMAIL',
            'Debe informar un email válido.',
            'email',
        ) from exc
    return normalized


@transaction.atomic
def request_web_access_claim(*, email):
    user_model = get_user_model()
    normalized_email = _normalize_email(email, user_model)
    user = (
        user_model.objects.select_for_update()
        .filter(email__iexact=normalized_email)
        .first()
    )
    if user is None:
        return ClaimRequestResult(sent=False)
    cliente = Cliente.objects.select_for_update().filter(usuario=user).first()
    if (
        cliente is None
        or not user.is_active
        or not cliente.activo
        or user.web_access_status != user_model.WebAccessStatus.PENDING_CLAIM
        or user.has_usable_password()
        or not user.email
    ):
        return ClaimRequestResult(sent=False)

    now = timezone.now()
    WebAccessClaimToken.objects.filter(
        usuario=user,
        consumed_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    raw_token = secrets.token_urlsafe(32)
    token = WebAccessClaimToken.objects.create(
        usuario=user,
        token_digest=_digest(raw_token),
        email_fingerprint=_digest(user.email.casefold()),
        expires_at=now + CLAIM_TOKEN_TTL,
    )
    Auditoria.objects.create(
        tabla=WEB_ACCESS_CLAIM_AUDIT_TABLE,
        registro_id=token.pk,
        usuario=None,
        accion='ALTA',
        valor_nuevo={
            'event': WEB_ACCESS_CLAIM_REQUESTED_EVENT,
            'source': WEB_ACCESS_CLAIM_SOURCE,
            'user_id': user.pk,
            'cliente_id': cliente.pk,
            'claim_token_id': token.pk,
            'email_fingerprint': token.email_fingerprint,
            'expires_at': token.expires_at.isoformat(),
        },
    )
    claim_base_url = os.getenv(
        'WEB_ACCESS_CLAIM_FRONTEND_URL',
        'http://localhost:3000/reclamar-acceso',
    ).rstrip('/')
    claim_link = f'{claim_base_url}/{raw_token}'
    message = EmailMultiAlternatives(
        'Reclamo de acceso web - Bohemia Hair',
        (
            'Recibimos una solicitud para habilitar tu acceso web. '
            f'Usá este enlace dentro de 60 minutos: {claim_link}\n\n'
            'Si no solicitaste el acceso, ignorá este mensaje.'
        ),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    message.send(fail_silently=False)
    return ClaimRequestResult(sent=True)


@transaction.atomic
def confirm_web_access_claim(*, token, new_password):
    if not isinstance(token, str) or not token.strip():
        raise WebAccessClaimError(
            'INVALID_OR_EXPIRED_CLAIM',
            'El enlace de reclamo es inválido o expiró.',
        )
    digest = _digest(token.strip())
    claim = (
        WebAccessClaimToken.objects.select_for_update()
        .select_related('usuario')
        .filter(token_digest=digest)
        .first()
    )
    now = timezone.now()
    if (
        claim is None
        or claim.consumed_at is not None
        or claim.revoked_at is not None
        or claim.expires_at <= now
    ):
        raise WebAccessClaimError(
            'INVALID_OR_EXPIRED_CLAIM',
            'El enlace de reclamo es inválido o expiró.',
        )

    user_model = get_user_model()
    user = user_model.objects.select_for_update().get(pk=claim.usuario_id)
    cliente = Cliente.objects.select_for_update().filter(usuario=user).first()
    if (
        cliente is None
        or not user.is_active
        or not cliente.activo
        or user.web_access_status != user_model.WebAccessStatus.PENDING_CLAIM
        or user.has_usable_password()
        or not user.email
        or _digest(user.email.casefold()) != claim.email_fingerprint
    ):
        raise WebAccessClaimError(
            'CLAIM_STATE_CONFLICT',
            'La cuenta ya no admite este reclamo.',
        )
    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        raise WebAccessClaimError(
            'INVALID_PASSWORD',
            'La contraseña no cumple los requisitos de seguridad.',
            'password',
        ) from exc

    user.set_password(new_password)
    user.web_access_status = user_model.WebAccessStatus.CLAIMED
    user.save(update_fields=['password', 'web_access_status'])
    claim.consumed_at = now
    claim.save(update_fields=['consumed_at'])
    WebAccessClaimToken.objects.filter(
        usuario=user,
        consumed_at__isnull=True,
        revoked_at__isnull=True,
    ).exclude(pk=claim.pk).update(revoked_at=now)
    Auditoria.objects.create(
        tabla=WEB_ACCESS_CLAIM_AUDIT_TABLE,
        registro_id=claim.pk,
        usuario=None,
        accion='MODIFICACION',
        valor_anterior={
            'web_access_status': user_model.WebAccessStatus.PENDING_CLAIM,
        },
        valor_nuevo={
            'event': WEB_ACCESS_CLAIM_COMPLETED_EVENT,
            'source': WEB_ACCESS_CLAIM_SOURCE,
            'user_id': user.pk,
            'cliente_id': cliente.pk,
            'claim_token_id': claim.pk,
            'web_access_status': user.web_access_status,
            'consumed_at': now.isoformat(),
        },
    )
    return ClaimConfirmationResult(
        user_id=user.pk,
        cliente_id=cliente.pk,
        web_access_status=user.web_access_status,
    )
