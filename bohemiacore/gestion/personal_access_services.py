from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from gestion.models import Auditoria, Personal
from usuarios.access_services import (
    InconsistentBusinessRoleState,
    InvalidRoleAssignmentTarget,
    InvalidRoleChangeReason,
    MissingClientProfile,
    PermissionDeniedForRoleAssignment,
    ProtectedSuperuser,
    SelfRoleAssignmentNotAllowed,
    assign_validated_business_role,
)
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    get_business_role,
    get_business_roles,
    has_inconsistent_business_roles,
)


PERSONAL_LINK_AUDIT_EVENT = 'PERSONAL_USER_LINKED'
PERSONAL_LINK_AUDIT_SOURCE = (
    'gestion.personal_access_services.link_user_to_personal'
)
PERSONAL_LINK_AUDIT_TABLE = 'PersonalUserLink'
PERSONAL_ACCESS_AUDIT_EVENT = 'PERSONAL_ACCESS_CREATED'
PERSONAL_ACCESS_AUDIT_SOURCE = (
    'gestion.personal_access_services.create_access_for_personal'
)
PERSONAL_ACCESS_AUDIT_TABLE = 'PersonalAccess'
PERSONAL_STATUS_AUDIT_TABLE = 'PersonalStatus'
PERSONAL_DEACTIVATED_EVENT = 'PERSONAL_DEACTIVATED'
PERSONAL_REACTIVATED_EVENT = 'PERSONAL_REACTIVATED'
PERSONAL_DEACTIVATED_SOURCE = (
    'gestion.personal_access_services.deactivate_personal'
)
PERSONAL_REACTIVATED_SOURCE = (
    'gestion.personal_access_services.reactivate_personal'
)
WORK_ACCESS_REVOCATION_AUDIT_TABLE = 'WorkAccessRevocation'
WORK_ACCESS_REVOKED_KEEP_CLIENT_EVENT = (
    'WORK_ACCESS_REVOKED_KEEP_CLIENT'
)
WORK_ACCESS_REVOCATION_SOURCE = (
    'gestion.personal_access_services.revoke_work_access_keep_client'
)
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 500
ALLOWED_PERSONAL_ACCESS_ROLES = (
    BusinessRole.EMPLEADO,
    BusinessRole.PROFESIONAL,
    BusinessRole.ADMINISTRADOR,
)


class PersonalLinkError(Exception):
    pass


class PersonalAlreadyLinked(PersonalLinkError):
    pass


class UserAlreadyLinkedToPersonal(PersonalLinkError):
    pass


class PermissionDeniedForPersonalLink(PersonalLinkError):
    pass


class InvalidPersonalLinkReason(PersonalLinkError):
    pass


class InvalidPersonalLinkTarget(PersonalLinkError):
    pass


class InvalidPersonalLinkUser(PersonalLinkError):
    pass


class PersonalLinkConflict(PersonalLinkError):
    pass


class PersonalAccessCreateError(Exception):
    pass


class PersonalAlreadyHasAccess(PersonalAccessCreateError):
    pass


class EmailAlreadyExists(PersonalAccessCreateError):
    pass


class PersonalInactiveForAccess(PersonalAccessCreateError):
    pass


class InvalidPersonalAccessRole(PersonalAccessCreateError):
    pass


class InvalidTemporaryPassword(PersonalAccessCreateError):
    pass


class InvalidPersonalAccessEmail(PersonalAccessCreateError):
    pass


class PersonalAccessConflict(PersonalAccessCreateError):
    pass


class PersonalStatusChangeError(Exception):
    pass


class PermissionDeniedForPersonalStatusChange(PersonalStatusChangeError):
    pass


class InvalidPersonalStatusReason(PersonalStatusChangeError):
    pass


class PersonalStatusConflict(PersonalStatusChangeError):
    pass


class WorkAccessRevocationError(Exception):
    pass


class PermissionDeniedForWorkAccessRevocation(WorkAccessRevocationError):
    pass


class InvalidWorkAccessRevocationReason(WorkAccessRevocationError):
    pass


class PersonalHasNoUser(WorkAccessRevocationError):
    pass


class ClientProfileRequired(WorkAccessRevocationError):
    pass


class InactiveUserForWorkAccessRevocation(WorkAccessRevocationError):
    pass


class WorkAccessRevocationConflict(WorkAccessRevocationError):
    pass


@dataclass(frozen=True)
class PersonalLinkResult:
    changed: bool
    personal_id: int
    user_id: int
    user_is_active: bool
    personal_is_active: bool
    business_role: str | None
    warnings: tuple[str, ...]
    audit_id: int | None


@dataclass(frozen=True)
class PersonalAccessCreateResult:
    changed: bool
    personal_id: int
    user_id: int
    email: str
    role: str
    personal_active: bool
    user_active: bool
    link_audit_id: int
    role_audit_id: int
    access_audit_id: int


@dataclass(frozen=True)
class PersonalStatusChangeResult:
    changed: bool
    personal_id: int
    previous_active: bool
    current_active: bool
    user_id: int | None
    user_active: bool | None
    current_role: str | None
    audit_id: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class WorkAccessRevocationResult:
    changed: bool
    personal_id: int
    user_id: int
    previous_role: str | None
    current_role: str
    previous_personal_active: bool
    current_personal_active: bool
    user_active: bool
    client_id: int
    audit_id: int | None
    status_audit_id: int | None
    role_audit_id: int | None
    warnings: tuple[str, ...]


@transaction.atomic
def revoke_work_access_keep_client(actor, personal, reason):
    normalized_reason = _validate_reason(
        reason,
        error_class=InvalidWorkAccessRevocationReason,
        operation='work-access revocation',
    )
    user_model = get_user_model()
    current_actor = _get_authorized_actor(
        actor,
        user_model,
        error_class=PermissionDeniedForWorkAccessRevocation,
        error_message='The actor cannot revoke personnel work access.',
    )
    personal_snapshot = _get_personal_snapshot(personal)

    if personal_snapshot.usuario_id is None:
        locked_personal = _get_locked_personal(personal_snapshot)
        if locked_personal.usuario_id is None:
            raise PersonalHasNoUser(
                'The personnel record has no linked user.'
            )
        raise WorkAccessRevocationConflict(
            'The personnel link changed during the operation.'
        )

    try:
        locked_user = user_model.objects.select_for_update().get(
            pk=personal_snapshot.usuario_id
        )
    except user_model.DoesNotExist as exc:
        raise WorkAccessRevocationConflict(
            'The linked user no longer exists.'
        ) from exc

    locked_personal = _get_locked_personal(personal_snapshot)
    if locked_personal.usuario_id is None:
        raise PersonalHasNoUser(
            'The personnel record has no linked user.'
        )
    if locked_personal.usuario_id != locked_user.pk:
        raise WorkAccessRevocationConflict(
            'The personnel link changed during the operation.'
        )
    if locked_user.is_superuser:
        raise ProtectedSuperuser(
            'Superusers cannot be managed through work-access revocation.'
        )
    if not locked_user.is_active:
        raise InactiveUserForWorkAccessRevocation(
            'An inactive user cannot retain client access.'
        )
    if has_inconsistent_business_roles(locked_user):
        raise InconsistentBusinessRoleState(
            'The target user has multiple business roles.'
        )

    from usuarios.models import Cliente

    client = (
        Cliente.objects.select_for_update()
        .filter(usuario=locked_user)
        .first()
    )
    if client is None:
        raise ClientProfileRequired(
            'A client profile is required to retain client access.'
        )

    previous_role = get_business_role(locked_user)
    previous_personal_active = locked_personal.activo
    personal_needs_change = previous_personal_active
    role_needs_change = previous_role != BusinessRole.CLIENTE

    if not personal_needs_change and not role_needs_change:
        return WorkAccessRevocationResult(
            changed=False,
            personal_id=locked_personal.pk,
            user_id=locked_user.pk,
            previous_role=previous_role,
            current_role=BusinessRole.CLIENTE,
            previous_personal_active=previous_personal_active,
            current_personal_active=False,
            user_active=locked_user.is_active,
            client_id=client.pk,
            audit_id=None,
            status_audit_id=None,
            role_audit_id=None,
            warnings=(),
        )

    status_result = None
    if personal_needs_change:
        try:
            status_result = deactivate_personal(
                actor=current_actor,
                personal=locked_personal,
                reason=normalized_reason,
            )
        except PermissionDeniedForPersonalStatusChange as exc:
            raise PermissionDeniedForWorkAccessRevocation(
                'The actor cannot revoke personnel work access.'
            ) from exc
        except (InvalidPersonalStatusReason, InvalidPersonalLinkTarget) as exc:
            raise WorkAccessRevocationConflict(
                'The personnel status could not be changed.'
            ) from exc

    role_result = None
    if role_needs_change:
        try:
            role_result = assign_validated_business_role(
                actor=current_actor,
                target_user=locked_user,
                target_role=BusinessRole.CLIENTE,
                reason=normalized_reason,
            )
        except PermissionDeniedForRoleAssignment as exc:
            raise PermissionDeniedForWorkAccessRevocation(
                'The actor cannot revoke personnel work access.'
            ) from exc
        except MissingClientProfile as exc:
            raise ClientProfileRequired(
                'A client profile is required to retain client access.'
            ) from exc
        except (
            InvalidRoleAssignmentTarget,
            InvalidRoleChangeReason,
            SelfRoleAssignmentNotAllowed,
        ) as exc:
            raise WorkAccessRevocationConflict(
                'The business role could not be changed.'
            ) from exc

    audit = Auditoria.objects.create(
        tabla=WORK_ACCESS_REVOCATION_AUDIT_TABLE,
        registro_id=locked_personal.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={
            'event': WORK_ACCESS_REVOKED_KEEP_CLIENT_EVENT,
            'personal_id': locked_personal.pk,
            'user_id': locked_user.pk,
            'business_role': previous_role,
            'personal_active': previous_personal_active,
            'user_active': locked_user.is_active,
        },
        valor_nuevo={
            'event': WORK_ACCESS_REVOKED_KEEP_CLIENT_EVENT,
            'source': WORK_ACCESS_REVOCATION_SOURCE,
            'actor_id': current_actor.pk,
            'personal_id': locked_personal.pk,
            'user_id': locked_user.pk,
            'client_id': client.pk,
            'previous_role': previous_role,
            'current_role': BusinessRole.CLIENTE,
            'previous_personal_active': previous_personal_active,
            'current_personal_active': False,
            'user_active': locked_user.is_active,
            'reason': normalized_reason,
            'status_audit_id': (
                status_result.audit_id if status_result is not None else None
            ),
            'role_audit_id': (
                role_result.audit_id if role_result is not None else None
            ),
        },
    )

    return WorkAccessRevocationResult(
        changed=True,
        personal_id=locked_personal.pk,
        user_id=locked_user.pk,
        previous_role=previous_role,
        current_role=BusinessRole.CLIENTE,
        previous_personal_active=previous_personal_active,
        current_personal_active=False,
        user_active=locked_user.is_active,
        client_id=client.pk,
        audit_id=audit.pk,
        status_audit_id=(
            status_result.audit_id if status_result is not None else None
        ),
        role_audit_id=(
            role_result.audit_id if role_result is not None else None
        ),
        warnings=(),
    )


def deactivate_personal(actor, personal, reason):
    return _change_personal_status(
        actor=actor,
        personal=personal,
        reason=reason,
        target_active=False,
        event=PERSONAL_DEACTIVATED_EVENT,
        source=PERSONAL_DEACTIVATED_SOURCE,
    )


def reactivate_personal(actor, personal, reason):
    return _change_personal_status(
        actor=actor,
        personal=personal,
        reason=reason,
        target_active=True,
        event=PERSONAL_REACTIVATED_EVENT,
        source=PERSONAL_REACTIVATED_SOURCE,
    )


@transaction.atomic
def _change_personal_status(
    *,
    actor,
    personal,
    reason,
    target_active,
    event,
    source,
):
    normalized_reason = _validate_reason(
        reason,
        error_class=InvalidPersonalStatusReason,
        operation='personnel status change',
    )
    user_model = get_user_model()
    current_actor = _get_personal_manager_actor(actor, user_model)
    locked_personal = _get_locked_personal(personal)
    previous_active = locked_personal.activo

    if previous_active == target_active:
        return _build_status_result(
            personal=locked_personal,
            changed=False,
            previous_active=previous_active,
            current_active=target_active,
        )

    updated = Personal.objects.filter(
        pk=locked_personal.pk,
        activo=previous_active,
    ).update(activo=target_active)
    if updated != 1:
        raise PersonalStatusConflict(
            'The personnel status conflicts with another operation.'
        )

    locked_personal.activo = target_active
    audit = Auditoria.objects.create(
        tabla=PERSONAL_STATUS_AUDIT_TABLE,
        registro_id=locked_personal.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={
            'event': event,
            'personal_id': locked_personal.pk,
            'user_id': locked_personal.usuario_id,
            'active': previous_active,
        },
        valor_nuevo={
            'event': event,
            'source': source,
            'actor_id': current_actor.pk,
            'personal_id': locked_personal.pk,
            'user_id': locked_personal.usuario_id,
            'previous_active': previous_active,
            'current_active': target_active,
            'reason': normalized_reason,
        },
    )

    return _build_status_result(
        personal=locked_personal,
        changed=True,
        previous_active=previous_active,
        current_active=target_active,
        audit_id=audit.pk,
    )


@transaction.atomic
def create_access_for_personal(
    actor,
    personal,
    email,
    raw_password,
    role,
    reason,
):
    """Create, link, and authorize one user for existing personnel."""
    normalized_reason = _validate_reason(reason)
    user_model = get_user_model()
    current_actor = _get_authorized_actor(actor, user_model)
    locked_personal = _get_locked_personal(personal)

    if locked_personal.usuario_id is not None:
        raise PersonalAlreadyHasAccess(
            'The personnel record already has a linked user.'
        )
    if not locked_personal.activo:
        raise PersonalInactiveForAccess(
            'Active personnel is required to create access.'
        )
    if role not in ALLOWED_PERSONAL_ACCESS_ROLES:
        raise InvalidPersonalAccessRole(
            'The requested role cannot be created as personnel access.'
        )

    normalized_email = _normalize_and_validate_email(email, user_model)
    if user_model.objects.filter(email__iexact=normalized_email).exists():
        raise EmailAlreadyExists(
            'An account already exists for the requested email.'
        )

    candidate_user = user_model(
        email=normalized_email,
        first_name=locked_personal.nombre,
        last_name=locked_personal.apellido,
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
                first_name=locked_personal.nombre,
                last_name=locked_personal.apellido,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
    except IntegrityError as exc:
        if user_model.objects.filter(email__iexact=normalized_email).exists():
            raise EmailAlreadyExists(
                'An account already exists for the requested email.'
            ) from exc
        raise PersonalAccessConflict(
            'User creation conflicts with another operation.'
        ) from exc

    link_result = link_user_to_personal(
        actor=current_actor,
        personal=locked_personal,
        user=created_user,
        reason=normalized_reason,
    )
    role_result = assign_validated_business_role(
        actor=current_actor,
        target_user=created_user,
        target_role=role,
        reason=normalized_reason,
    )
    access_audit = Auditoria.objects.create(
        tabla=PERSONAL_ACCESS_AUDIT_TABLE,
        registro_id=locked_personal.pk,
        usuario=current_actor,
        accion='ALTA',
        valor_nuevo={
            'event': PERSONAL_ACCESS_AUDIT_EVENT,
            'source': PERSONAL_ACCESS_AUDIT_SOURCE,
            'actor_id': current_actor.pk,
            'personal_id': locked_personal.pk,
            'user_id': created_user.pk,
            'user_email': created_user.email,
            'role': role,
            'personal_active': locked_personal.activo,
            'user_active': created_user.is_active,
            'reason': normalized_reason,
            'link_audit_id': link_result.audit_id,
            'role_audit_id': role_result.audit_id,
        },
    )

    return PersonalAccessCreateResult(
        changed=True,
        personal_id=locked_personal.pk,
        user_id=created_user.pk,
        email=created_user.email,
        role=role,
        personal_active=locked_personal.activo,
        user_active=created_user.is_active,
        link_audit_id=link_result.audit_id,
        role_audit_id=role_result.audit_id,
        access_audit_id=access_audit.pk,
    )


@transaction.atomic
def link_user_to_personal(actor, personal, user, reason):
    """Link an existing user and personnel record without changing access."""
    normalized_reason = _validate_reason(reason)
    user_model = get_user_model()
    current_actor = _get_authorized_actor(actor, user_model)
    locked_user = _get_locked_user(user, user_model)
    locked_personal = _get_locked_personal(personal)

    if locked_user.is_superuser:
        raise ProtectedSuperuser(
            'Superusers cannot be managed through personnel linking.'
        )
    if has_inconsistent_business_roles(locked_user):
        raise InconsistentBusinessRoleState(
            'The target user has multiple business roles.'
        )

    business_role = get_business_role(locked_user)
    linked_personal = (
        Personal.objects.select_for_update()
        .filter(usuario=locked_user)
        .first()
    )

    if locked_personal.usuario_id is not None:
        if locked_personal.usuario_id != locked_user.pk:
            raise PersonalAlreadyLinked(
                'The personnel record is already linked to another user.'
            )
        return _build_result(
            changed=False,
            personal=locked_personal,
            user=locked_user,
            business_role=business_role,
        )

    if linked_personal is not None:
        raise UserAlreadyLinkedToPersonal(
            'The user is already linked to another personnel record.'
        )

    # Avoid the generic Personal signal producing a second audit event.
    try:
        with transaction.atomic():
            updated = Personal.objects.filter(
                pk=locked_personal.pk,
                usuario__isnull=True,
            ).update(usuario_id=locked_user.pk)
    except IntegrityError as exc:
        _raise_link_conflict(locked_personal, locked_user, exc)

    if updated != 1:
        raise PersonalAlreadyLinked(
            'The personnel record was linked by another operation.'
        )

    locked_personal.usuario_id = locked_user.pk
    audit = Auditoria.objects.create(
        tabla=PERSONAL_LINK_AUDIT_TABLE,
        registro_id=locked_personal.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={
            'event': PERSONAL_LINK_AUDIT_EVENT,
            'personal_id': locked_personal.pk,
            'user_id': None,
        },
        valor_nuevo={
            'event': PERSONAL_LINK_AUDIT_EVENT,
            'source': PERSONAL_LINK_AUDIT_SOURCE,
            'actor_id': current_actor.pk,
            'personal_id': locked_personal.pk,
            'previous_user_id': None,
            'new_user_id': locked_user.pk,
            'user_email': locked_user.email,
            'reason': normalized_reason,
        },
    )

    return _build_result(
        changed=True,
        personal=locked_personal,
        user=locked_user,
        business_role=business_role,
        audit_id=audit.pk,
    )


def _validate_reason(
    reason,
    *,
    error_class=InvalidPersonalLinkReason,
    operation='personnel link',
):
    if not isinstance(reason, str):
        raise error_class(f'A reason is required for the {operation}.')

    normalized_reason = reason.strip()
    if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
        raise error_class(
            f'The reason must contain between {MIN_REASON_LENGTH} and '
            f'{MAX_REASON_LENGTH} characters.'
        )
    return normalized_reason


def _normalize_and_validate_email(email, user_model):
    if not isinstance(email, str):
        raise InvalidPersonalAccessEmail('A valid email is required.')

    normalized_email = user_model.objects.normalize_email(email.strip())
    try:
        validate_email(normalized_email)
    except ValidationError as exc:
        raise InvalidPersonalAccessEmail('A valid email is required.') from exc
    return normalized_email


def _validate_temporary_password(raw_password, candidate_user):
    if not isinstance(raw_password, str):
        raise InvalidTemporaryPassword(
            'A valid temporary password is required.'
        )

    try:
        validate_password(raw_password, user=candidate_user)
    except ValidationError as exc:
        raise InvalidTemporaryPassword(
            'The temporary password does not meet security requirements.'
        ) from exc


def _get_authorized_actor(
    actor,
    user_model,
    *,
    error_class=PermissionDeniedForPersonalLink,
    error_message='The actor cannot link users to personnel records.',
):
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise error_class(
            'A valid authenticated actor is required.'
        )

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise error_class(
            'A valid authenticated actor is required.'
        ) from exc

    required_permissions = (
        BusinessPermission.MANAGE_PERSONAL,
        BusinessPermission.ASSIGN_ROLES,
    )
    if not current_actor.is_active or not all(
        current_actor.has_perm(permission)
        for permission in required_permissions
    ):
        raise error_class(error_message)
    return current_actor


def _get_personal_manager_actor(actor, user_model):
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PermissionDeniedForPersonalStatusChange(
            'A valid authenticated actor is required.'
        )

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise PermissionDeniedForPersonalStatusChange(
            'A valid authenticated actor is required.'
        ) from exc

    if (
        not current_actor.is_active
        or not current_actor.has_perm(BusinessPermission.MANAGE_PERSONAL)
    ):
        raise PermissionDeniedForPersonalStatusChange(
            'The actor cannot change personnel status.'
        )
    return current_actor


def _get_locked_user(user, user_model):
    if not isinstance(user, user_model) or user.pk is None:
        raise InvalidPersonalLinkUser('A valid existing user is required.')

    try:
        return user_model.objects.select_for_update().get(pk=user.pk)
    except user_model.DoesNotExist as exc:
        raise InvalidPersonalLinkUser(
            'A valid existing user is required.'
        ) from exc


def _get_locked_personal(personal):
    if not isinstance(personal, Personal) or personal.pk is None:
        raise InvalidPersonalLinkTarget(
            'A valid existing personnel record is required.'
        )

    try:
        return Personal.objects.select_for_update().get(pk=personal.pk)
    except Personal.DoesNotExist as exc:
        raise InvalidPersonalLinkTarget(
            'A valid existing personnel record is required.'
        ) from exc


def _get_personal_snapshot(personal):
    if not isinstance(personal, Personal) or personal.pk is None:
        raise InvalidPersonalLinkTarget(
            'A valid existing personnel record is required.'
        )

    try:
        return Personal.objects.only('pk', 'usuario_id').get(pk=personal.pk)
    except Personal.DoesNotExist as exc:
        raise InvalidPersonalLinkTarget(
            'A valid existing personnel record is required.'
        ) from exc


def _raise_link_conflict(personal, user, original_error):
    if Personal.objects.filter(usuario=user).exclude(pk=personal.pk).exists():
        raise UserAlreadyLinkedToPersonal(
            'The user was linked to another personnel record.'
        ) from original_error

    if Personal.objects.filter(pk=personal.pk, usuario__isnull=False).exists():
        raise PersonalAlreadyLinked(
            'The personnel record was linked by another operation.'
        ) from original_error

    raise PersonalLinkConflict(
        'The personnel link conflicts with another operation.'
    ) from original_error


def _build_result(
    *,
    changed,
    personal,
    user,
    business_role,
    audit_id=None,
):
    warnings = []
    if not user.is_active:
        warnings.append('USER_INACTIVE')
    if not personal.activo:
        warnings.append('PERSONAL_INACTIVE')
    if business_role is None:
        warnings.append('NO_BUSINESS_ROLE')

    return PersonalLinkResult(
        changed=changed,
        personal_id=personal.pk,
        user_id=user.pk,
        user_is_active=user.is_active,
        personal_is_active=personal.activo,
        business_role=business_role,
        warnings=tuple(warnings),
        audit_id=audit_id,
    )


def _build_status_result(
    *,
    personal,
    changed,
    previous_active,
    current_active,
    audit_id=None,
):
    user = personal.usuario if personal.usuario_id is not None else None
    warnings = []
    current_role = None

    if user is None:
        warnings.append('NO_LINKED_USER')
    else:
        roles = get_business_roles(user)
        if len(roles) == 1:
            current_role = roles[0]
        elif len(roles) > 1:
            warnings.append('INCONSISTENT_BUSINESS_ROLES')
        else:
            warnings.append('NO_BUSINESS_ROLE')
        if not user.is_active:
            warnings.append('USER_INACTIVE')

    return PersonalStatusChangeResult(
        changed=changed,
        personal_id=personal.pk,
        previous_active=previous_active,
        current_active=current_active,
        user_id=user.pk if user is not None else None,
        user_active=user.is_active if user is not None else None,
        current_role=current_role,
        audit_id=audit_id,
        warnings=tuple(warnings),
    )
