from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from gestion.models import Auditoria
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    assign_business_role,
    get_business_roles,
)


ADMINISTRATOR_ACCOUNT_CREATION_AUDIT_TABLE = (
    'AdministratorAccountCreation'
)
ADMINISTRATOR_ACCOUNT_CREATED_EVENT = 'ADMINISTRATOR_ACCOUNT_CREATED'
ADMINISTRATOR_ACCOUNT_CREATION_SOURCE = 'admin_onboarding'
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 500


class AdministratorAccountCreationError(Exception):
    pass


class PermissionDeniedForAdministratorAccountCreation(
    AdministratorAccountCreationError
):
    pass


class InvalidAdministratorAccountPayload(AdministratorAccountCreationError):
    pass


class InvalidAdministratorAccountPassword(AdministratorAccountCreationError):
    pass


class InvalidAdministratorAccountReason(AdministratorAccountCreationError):
    pass


class AdministratorEmailAlreadyExists(AdministratorAccountCreationError):
    pass


class AdministratorAccountCreationConflict(
    AdministratorAccountCreationError
):
    pass


@dataclass(frozen=True)
class AdministratorAccountCreationResult:
    created: bool
    user_id: int
    email: str
    role: str
    user_active: bool
    audit_id: int


@transaction.atomic
def create_administrator_account(
    actor,
    email,
    first_name,
    last_name,
    raw_password,
    reason,
):
    """Create one SPA administrator without enabling Django Admin access."""
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

    if user_model.objects.filter(email__iexact=normalized_email).exists():
        raise AdministratorEmailAlreadyExists(
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
            raise AdministratorEmailAlreadyExists(
                'An account already exists for the requested email.'
            ) from exc
        raise AdministratorAccountCreationConflict(
            'Administrator creation conflicts with another operation.'
        ) from exc

    try:
        assign_business_role(created_user, BusinessRole.ADMINISTRADOR)
        if get_business_roles(created_user) != (
            BusinessRole.ADMINISTRADOR,
        ):
            raise AdministratorAccountCreationConflict(
                'The account did not receive exactly one administrator role.'
            )

        audit = _write_administrator_account_creation_audit(
            actor=current_actor,
            user=created_user,
            reason=normalized_reason,
        )
    except AdministratorAccountCreationConflict:
        raise
    except Exception as exc:
        raise AdministratorAccountCreationConflict(
            'Administrator creation conflicts with another operation.'
        ) from exc

    return AdministratorAccountCreationResult(
        created=True,
        user_id=created_user.pk,
        email=created_user.email,
        role=BusinessRole.ADMINISTRADOR,
        user_active=created_user.is_active,
        audit_id=audit.pk,
    )


def _get_authorized_actor(actor, user_model):
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PermissionDeniedForAdministratorAccountCreation(
            'A valid authenticated actor is required.'
        )

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise PermissionDeniedForAdministratorAccountCreation(
            'A valid authenticated actor is required.'
        ) from exc

    required_permissions = (
        BusinessPermission.MANAGE_USERS,
        BusinessPermission.ASSIGN_ROLES,
    )
    if not current_actor.is_active or not all(
        current_actor.has_perm(permission)
        for permission in required_permissions
    ):
        raise PermissionDeniedForAdministratorAccountCreation(
            'The actor cannot create administrator accounts.'
        )
    return current_actor


def _normalize_email(email, user_model):
    if not isinstance(email, str):
        raise InvalidAdministratorAccountPayload(
            'A valid email is required.'
        )

    normalized_email = user_model.objects.normalize_email(email.strip())
    try:
        validate_email(normalized_email)
    except ValidationError as exc:
        raise InvalidAdministratorAccountPayload(
            'A valid email is required.'
        ) from exc
    return normalized_email


def _normalize_required_text(value, *, field_name, max_length):
    if not isinstance(value, str):
        raise InvalidAdministratorAccountPayload(
            f'A valid {field_name} is required.'
        )
    normalized_value = value.strip()
    if not normalized_value or len(normalized_value) > max_length:
        raise InvalidAdministratorAccountPayload(
            f'A valid {field_name} is required.'
        )
    return normalized_value


def _validate_temporary_password(raw_password, candidate_user):
    if not isinstance(raw_password, str):
        raise InvalidAdministratorAccountPassword(
            'A valid temporary password is required.'
        )
    try:
        validate_password(raw_password, user=candidate_user)
    except ValidationError as exc:
        raise InvalidAdministratorAccountPassword(
            'The temporary password does not meet security requirements.'
        ) from exc


def _validate_reason(reason):
    if not isinstance(reason, str):
        raise InvalidAdministratorAccountReason(
            'An administrator-account creation reason is required.'
        )
    normalized_reason = reason.strip()
    if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
        raise InvalidAdministratorAccountReason(
            f'The reason must contain between {MIN_REASON_LENGTH} and '
            f'{MAX_REASON_LENGTH} characters.'
        )
    return normalized_reason


def _write_administrator_account_creation_audit(*, actor, user, reason):
    return Auditoria.objects.create(
        tabla=ADMINISTRATOR_ACCOUNT_CREATION_AUDIT_TABLE,
        registro_id=user.pk,
        usuario=actor,
        accion='ALTA',
        valor_nuevo={
            'event': ADMINISTRATOR_ACCOUNT_CREATED_EVENT,
            'source': ADMINISTRATOR_ACCOUNT_CREATION_SOURCE,
            'actor_id': actor.pk,
            'user_id': user.pk,
            'email': user.email,
            'business_role': BusinessRole.ADMINISTRADOR,
            'reason': reason,
            'is_active': user.is_active,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
        },
    )
