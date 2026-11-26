import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from gestion.models import Auditoria

from .models import Cliente, WebAccessClaimDelivery, WebAccessClaimToken


CLAIM_TOKEN_TTL = timedelta(minutes=60)
CLAIM_DELIVERY_TTL = timedelta(minutes=15)
WEB_ACCESS_CLAIM_AUDIT_TABLE = 'WebAccessClaim'
WEB_ACCESS_CLAIM_REQUESTED_EVENT = 'WEB_ACCESS_CLAIM_REQUESTED'
WEB_ACCESS_CLAIM_COMPLETED_EVENT = 'WEB_ACCESS_CLAIM_COMPLETED'
WEB_ACCESS_CLAIM_SOURCE = 'usuarios.web_access_claim_services'
logger = logging.getLogger(__name__)


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


class ClaimDeliveryFailed(Exception):
    pass


def _claim_contact_digest(email):
    return salted_hmac('bh064.claim-delivery', email.casefold(), algorithm='sha256').hexdigest()


def queue_web_access_claim(*, email):
    user_model = get_user_model()
    email = _normalize_email(email, user_model)
    target_id = user_model.objects.filter(email__iexact=email).values_list('pk', flat=True).first()
    # Misma forma de lectura y escritura para una cuenta conocida o no. Nada
    # en el POST espera al proveedor; no se persiste email ni token en la cola.
    WebAccessClaimDelivery.objects.create(
        target_user_id=target_id, contact_digest=_claim_contact_digest(email),
    )


@transaction.atomic
def process_next_web_access_claim():
    job = WebAccessClaimDelivery.objects.select_for_update(skip_locked=True).order_by('pk').first()
    if job is None:
        return False
    if job.target_user_id and job.requested_at > timezone.now() - CLAIM_DELIVERY_TTL:
        email = get_user_model().objects.filter(pk=job.target_user_id).values_list('email', flat=True).first()
        if email and _claim_contact_digest(email) == job.contact_digest:
            request_web_access_claim(email=email, expected_user_id=job.target_user_id)
    job.delete()
    return True


def request_web_access_claim(*, email, expected_user_id=None):
    try:
        return _request_and_send_claim(email=email, expected_user_id=expected_user_id)
    except ClaimDeliveryFailed:
        # El rollback ya ocurrió. No volcar excepción SMTP (puede contener
        # destinatarios), enlaces, tokens ni información de la cuenta.
        logger.warning('web_access_claim_delivery_failed')
        return ClaimRequestResult(sent=False)


@transaction.atomic
def _request_and_send_claim(*, email, expected_user_id):
    user_model = get_user_model()
    normalized_email = _normalize_email(email, user_model)
    candidates = user_model.objects.select_for_update().filter(email__iexact=normalized_email)
    if expected_user_id is not None:
        candidates = candidates.filter(pk=expected_user_id)
    user = candidates.first()
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
    try:
        message.connection = get_connection(timeout=10)
        delivered = message.send(fail_silently=False)
    except Exception:
        # La frontera de captura es sólo el backend de entrega, no la BD ni
        # la validación del dominio. Cualquier fallo de ese backend es igual.
        raise ClaimDeliveryFailed from None
    if delivered != 1:
        raise ClaimDeliveryFailed
    return ClaimRequestResult(sent=True)


@transaction.atomic
def confirm_web_access_claim(*, token, new_password):
    if not isinstance(token, str) or not token.strip():
        raise WebAccessClaimError(
            'INVALID_OR_EXPIRED_CLAIM',
            'El enlace de reclamo es inválido o expiró.',
        )
    digest = _digest(token.strip())
    candidate_user_id = WebAccessClaimToken.objects.filter(token_digest=digest).values_list(
        'usuario_id', flat=True,
    ).first()
    # Mismo orden que emisión: primero Usuario, luego filas dependientes.
    # El token se vuelve a leer bajo lock, no se acepta el estado preliminar.
    user_model = get_user_model()
    user = user_model.objects.select_for_update().filter(pk=candidate_user_id).first() if candidate_user_id else None
    claim = (
        WebAccessClaimToken.objects.select_for_update()
        .filter(token_digest=digest, usuario_id=user.pk)
        .first()
    ) if user else None
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
