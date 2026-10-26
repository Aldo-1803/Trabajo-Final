from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from gestion.models import Auditoria
from usuarios.models import Cliente
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    assign_business_role,
    get_business_roles,
)


CLIENT_ACCOUNT_CREATION_AUDIT_TABLE = 'ClientAccountCreation'
CLIENT_ACCOUNT_CREATED_BY_STAFF_EVENT = 'CLIENT_ACCOUNT_CREATED_BY_STAFF'
CLIENT_ACCOUNT_CREATION_SOURCE = (
    'usuarios.client_account_services.create_client_account_by_staff'
)
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 500


class ClientAccountCreationError(Exception):
    pass


class PermissionDeniedForClientAccountCreation(ClientAccountCreationError):
    pass


class InvalidClientAccountPayload(ClientAccountCreationError):
    pass


class InvalidClientAccountPassword(ClientAccountCreationError):
    pass


class InvalidClientAccountReason(ClientAccountCreationError):
    pass


class EmailAlreadyExists(ClientAccountCreationError):
    pass


class ClientAccountCreationConflict(ClientAccountCreationError):
    pass


@dataclass(frozen=True)
class ClientAccountCreationResult:
    created: bool
    user_id: int
    cliente_id: int
    email: str
    role: str
    user_active: bool
    audit_id: int


@transaction.atomic
def create_client_account_by_staff(
    actor,
    email,
    first_name,
    last_name,
    raw_password,
    reason,
    telefono=None,
    zona=None,
):
    """Create one client account, profile, role, and semantic audit event."""
    user_model = get_user_model()
    current_actor = _get_authorized_actor(actor, user_model)
    normalized_email = _normalize_email(email, user_model)
    normalized_first_name = _normalize_required_text(
        first_name,
        field_name='first_name',
        max_length=user_model._meta.get_field('first_name').max_length,
    )
    normalized_last_name = _normalize_required_text(
        last_name,
        field_name='last_name',
        max_length=user_model._meta.get_field('last_name').max_length,
    )
    normalized_reason = _validate_reason(reason)
    normalized_phone = _normalize_optional_text(
        telefono,
        field_name='telefono',
        max_length=Cliente._meta.get_field('numero').max_length,
    )
    normalized_zone = _normalize_optional_text(
        zona,
        field_name='zona',
        max_length=Cliente._meta.get_field('zona').max_length,
    )

    if user_model.objects.filter(email__iexact=normalized_email).exists():
        raise EmailAlreadyExists(
            'An account already exists for the requested email.'
        )

    candidate_user = user_model(
        email=normalized_email,
        first_name=normalized_first_name,
        last_name=normalized_last_name,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    _validate_temporary_password(raw_password, candidate_user)

    try:
        with transaction.atomic():
            created_user = user_model.objects.create_user(
                email=normalized_email,
                password=raw_password,
                first_name=normalized_first_name,
                last_name=normalized_last_name,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
    except IntegrityError as exc:
        if user_model.objects.filter(email__iexact=normalized_email).exists():
            raise EmailAlreadyExists(
                'An account already exists for the requested email.'
            ) from exc
        raise ClientAccountCreationConflict(
            'User creation conflicts with another operation.'
        ) from exc

    try:
        cliente = Cliente.objects.create(
            usuario=created_user,
            numero=normalized_phone,
            zona=normalized_zone,
        )
        assign_business_role(created_user, BusinessRole.CLIENTE)
        if get_business_roles(created_user) != (BusinessRole.CLIENTE,):
            raise ClientAccountCreationConflict(
                'The created account did not receive exactly one client role.'
            )

        audit = Auditoria.objects.create(
            tabla=CLIENT_ACCOUNT_CREATION_AUDIT_TABLE,
            registro_id=created_user.pk,
            usuario=current_actor,
            accion='ALTA',
            valor_nuevo={
                'event': CLIENT_ACCOUNT_CREATED_BY_STAFF_EVENT,
                'source': CLIENT_ACCOUNT_CREATION_SOURCE,
                'actor_id': current_actor.pk,
                'user_id': created_user.pk,
                'cliente_id': cliente.pk,
                'email': created_user.email,
                'business_role': BusinessRole.CLIENTE,
                'user_active': created_user.is_active,
                'client_active': cliente.activo,
                'reason': normalized_reason,
            },
        )
    except ClientAccountCreationConflict:
        raise
    except Exception as exc:
        raise ClientAccountCreationConflict(
            'Client account creation conflicts with another operation.'
        ) from exc

    return ClientAccountCreationResult(
        created=True,
        user_id=created_user.pk,
        cliente_id=cliente.pk,
        email=created_user.email,
        role=BusinessRole.CLIENTE,
        user_active=created_user.is_active,
        audit_id=audit.pk,
    )


def _get_authorized_actor(actor, user_model):
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PermissionDeniedForClientAccountCreation(
            'A valid authenticated actor is required.'
        )

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise PermissionDeniedForClientAccountCreation(
            'A valid authenticated actor is required.'
        ) from exc

    if (
        not current_actor.is_active
        or not current_actor.has_perm(
            BusinessPermission.CREATE_WALKIN_CLIENT
        )
    ):
        raise PermissionDeniedForClientAccountCreation(
            'The actor cannot create client accounts.'
        )
    return current_actor


def _normalize_email(email, user_model):
    if not isinstance(email, str):
        raise InvalidClientAccountPayload('A valid email is required.')

    normalized_email = user_model.objects.normalize_email(email.strip())
    try:
        validate_email(normalized_email)
    except ValidationError as exc:
        raise InvalidClientAccountPayload(
            'A valid email is required.'
        ) from exc
    return normalized_email


def _normalize_required_text(value, *, field_name, max_length):
    if not isinstance(value, str):
        raise InvalidClientAccountPayload(
            f'A valid {field_name} is required.'
        )
    normalized_value = value.strip()
    if not normalized_value or len(normalized_value) > max_length:
        raise InvalidClientAccountPayload(
            f'A valid {field_name} is required.'
        )
    return normalized_value


def _normalize_optional_text(value, *, field_name, max_length):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise InvalidClientAccountPayload(
            f'A valid {field_name} is required.'
        )
    normalized_value = value.strip()
    if len(normalized_value) > max_length:
        raise InvalidClientAccountPayload(
            f'A valid {field_name} is required.'
        )
    return normalized_value


def _validate_temporary_password(raw_password, candidate_user):
    if not isinstance(raw_password, str):
        raise InvalidClientAccountPassword(
            'A valid temporary password is required.'
        )
    try:
        validate_password(raw_password, user=candidate_user)
    except ValidationError as exc:
        raise InvalidClientAccountPassword(
            'The temporary password does not meet security requirements.'
        ) from exc


def _validate_reason(reason):
    if not isinstance(reason, str):
        raise InvalidClientAccountReason(
            'A client-account creation reason is required.'
        )
    normalized_reason = reason.strip()
    if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
        raise InvalidClientAccountReason(
            f'The reason must contain between {MIN_REASON_LENGTH} and '
            f'{MAX_REASON_LENGTH} characters.'
        )
    return normalized_reason
