from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from gestion.models import Auditoria
from usuarios.models import Cliente
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    assign_business_role,
    get_business_role,
    get_business_roles,
    has_inconsistent_business_roles,
)


ROLE_AUDIT_EVENT = 'BUSINESS_ROLE_CHANGED'
ROLE_AUDIT_SOURCE = 'usuarios.access_services.assign_validated_business_role'
ROLE_AUDIT_TABLE = 'UsuarioBusinessRole'
ACCOUNT_DEACTIVATED_EVENT = 'ACCOUNT_DEACTIVATED'
ACCOUNT_DEACTIVATION_SOURCE = 'usuarios.access_services.deactivate_account'
ACCOUNT_DEACTIVATION_AUDIT_TABLE = 'UsuarioAccountStatus'
ACCOUNT_REACTIVATED_EVENT = 'ACCOUNT_REACTIVATED'
ACCOUNT_REACTIVATION_SOURCE = 'usuarios.access_services.reactivate_account'
ACCOUNT_REACTIVATION_AUDIT_TABLE = 'UsuarioAccountStatus'
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 500


class RoleAssignmentError(Exception):
    pass


class InvalidBusinessRole(RoleAssignmentError):
    pass


class InconsistentBusinessRoleState(RoleAssignmentError):
    pass


class MissingClientProfile(RoleAssignmentError):
    pass


class MissingPersonalProfile(RoleAssignmentError):
    pass


class InactivePersonal(RoleAssignmentError):
    pass


class ProtectedSuperuser(RoleAssignmentError):
    pass


class PermissionDeniedForRoleAssignment(RoleAssignmentError):
    pass


class InvalidRoleChangeReason(RoleAssignmentError):
    pass


class SelfRoleAssignmentNotAllowed(RoleAssignmentError):
    pass


class InvalidRoleAssignmentTarget(RoleAssignmentError):
    pass


class AccountDeactivationError(Exception):
    pass


class PermissionDeniedForAccountDeactivation(AccountDeactivationError):
    pass


class InvalidAccountDeactivationReason(AccountDeactivationError):
    pass


class InvalidAccountDeactivationTarget(AccountDeactivationError):
    pass


class SelfDeactivationNotAllowed(AccountDeactivationError):
    pass


class LastActiveAdministrator(AccountDeactivationError):
    pass


class AccountDeactivationConflict(AccountDeactivationError):
    pass


class AccountReactivationError(Exception):
    pass


class PermissionDeniedForAccountReactivation(AccountReactivationError):
    pass


class InvalidAccountReactivationReason(AccountReactivationError):
    pass


class InvalidAccountReactivationTarget(AccountReactivationError):
    pass


class UserHasNoBusinessRole(AccountReactivationError):
    pass


class AccountReactivationConflict(AccountReactivationError):
    pass


@dataclass(frozen=True)
class RoleAssignmentResult:
    changed: bool
    previous_role: str | None
    new_role: str
    audit_id: int | None


@dataclass(frozen=True)
class AccountDeactivationResult:
    changed: bool
    user_id: int
    previous_active: bool
    current_active: bool
    current_role: str | None
    audit_id: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AccountReactivationResult:
    changed: bool
    user_id: int
    previous_active: bool
    current_active: bool
    current_role: str
    audit_id: int | None
    warnings: tuple[str, ...]


@transaction.atomic
def reactivate_account(actor, target_user, reason):
    """Reactivate one coherent account without changing roles or profiles."""
    normalized_reason = _validate_account_reactivation_reason(reason)
    user_model = get_user_model()
    current_actor = _get_account_reactivation_actor(actor, user_model)
    locked_target = _get_locked_reactivation_target(target_user, user_model)

    if current_actor.pk == locked_target.pk:
        raise PermissionDeniedForAccountReactivation(
            'Self-service account reactivation is not allowed.'
        )
    if locked_target.is_superuser:
        raise ProtectedSuperuser(
            'Superusers cannot be managed through account reactivation.'
        )
    if has_inconsistent_business_roles(locked_target):
        raise InconsistentBusinessRoleState(
            'The target user has multiple business roles.'
        )

    current_role = get_business_role(locked_target)
    if current_role is None:
        raise UserHasNoBusinessRole(
            'A business role is required to reactivate an account.'
        )

    warnings = []
    if current_role == BusinessRole.CLIENTE:
        client = (
            Cliente.objects.select_for_update()
            .filter(usuario=locked_target)
            .first()
        )
        if client is None:
            raise MissingClientProfile(
                'The CLIENTE role requires a client profile.'
            )
        if not client.activo:
            warnings.append('CLIENT_PROFILE_INACTIVE')
    elif current_role in (
        BusinessRole.EMPLEADO,
        BusinessRole.PROFESIONAL,
    ):
        from gestion.models import Personal

        personal = (
            Personal.objects.select_for_update()
            .filter(usuario=locked_target)
            .first()
        )
        if personal is None:
            raise MissingPersonalProfile(
                'The labor role requires a personnel profile.'
            )
        if not personal.activo:
            raise InactivePersonal(
                'Active personnel is required to reactivate a labor account.'
            )

    previous_active = locked_target.is_active
    if previous_active:
        return AccountReactivationResult(
            changed=False,
            user_id=locked_target.pk,
            previous_active=True,
            current_active=True,
            current_role=current_role,
            audit_id=None,
            warnings=tuple(warnings),
        )

    updated = user_model.objects.filter(
        pk=locked_target.pk,
        is_active=False,
    ).update(is_active=True)
    if updated != 1:
        raise AccountReactivationConflict(
            'The account status conflicts with another operation.'
        )

    locked_target.is_active = True
    warnings.append('PREEXISTING_TOKENS_MAY_REGAIN_VALIDITY')
    audit = Auditoria.objects.create(
        tabla=ACCOUNT_REACTIVATION_AUDIT_TABLE,
        registro_id=locked_target.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={
            'event': ACCOUNT_REACTIVATED_EVENT,
            'target_user_id': locked_target.pk,
            'active': previous_active,
            'business_role': current_role,
        },
        valor_nuevo={
            'event': ACCOUNT_REACTIVATED_EVENT,
            'source': ACCOUNT_REACTIVATION_SOURCE,
            'actor_id': current_actor.pk,
            'target_user_id': locked_target.pk,
            'previous_active': previous_active,
            'current_active': True,
            'current_business_role': current_role,
            'reason': normalized_reason,
        },
    )

    return AccountReactivationResult(
        changed=True,
        user_id=locked_target.pk,
        previous_active=previous_active,
        current_active=True,
        current_role=current_role,
        audit_id=audit.pk,
        warnings=tuple(warnings),
    )


@transaction.atomic
def deactivate_account(actor, target_user, reason):
    """Deactivate one account without changing roles, profiles, or flags."""
    normalized_reason = _validate_account_deactivation_reason(reason)
    user_model = get_user_model()
    current_actor = _get_account_manager_actor(actor, user_model)
    locked_target = _get_locked_account_target(target_user, user_model)

    if current_actor.pk == locked_target.pk:
        raise SelfDeactivationNotAllowed(
            'Users cannot deactivate their own account.'
        )
    if locked_target.is_superuser:
        raise ProtectedSuperuser(
            'Superusers cannot be managed through account deactivation.'
        )

    roles = get_business_roles(locked_target)
    warnings = (
        ('INCONSISTENT_BUSINESS_ROLES',)
        if len(roles) > 1
        else ()
    )
    current_role = roles[0] if len(roles) == 1 else None
    previous_active = locked_target.is_active

    if not previous_active:
        return AccountDeactivationResult(
            changed=False,
            user_id=locked_target.pk,
            previous_active=False,
            current_active=False,
            current_role=current_role,
            audit_id=None,
            warnings=warnings,
        )

    if BusinessRole.ADMINISTRADOR in roles:
        administrator_group = Group.objects.select_for_update().get(
            name=BusinessRole.ADMINISTRADOR
        )
        another_active_administrator_exists = user_model.objects.filter(
            is_active=True,
            groups=administrator_group,
        ).exclude(pk=locked_target.pk).exists()
        if not another_active_administrator_exists:
            raise LastActiveAdministrator(
                'The last active business administrator cannot be deactivated.'
            )

    updated = user_model.objects.filter(
        pk=locked_target.pk,
        is_active=True,
    ).update(is_active=False)
    if updated != 1:
        raise AccountDeactivationConflict(
            'The account status conflicts with another operation.'
        )

    locked_target.is_active = False
    audit = Auditoria.objects.create(
        tabla=ACCOUNT_DEACTIVATION_AUDIT_TABLE,
        registro_id=locked_target.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={
            'event': ACCOUNT_DEACTIVATED_EVENT,
            'target_user_id': locked_target.pk,
            'active': previous_active,
            'business_roles': list(roles),
        },
        valor_nuevo={
            'event': ACCOUNT_DEACTIVATED_EVENT,
            'source': ACCOUNT_DEACTIVATION_SOURCE,
            'actor_id': current_actor.pk,
            'target_user_id': locked_target.pk,
            'previous_active': previous_active,
            'current_active': False,
            'current_business_role': current_role,
            'business_roles': list(roles),
            'reason': normalized_reason,
        },
    )

    return AccountDeactivationResult(
        changed=True,
        user_id=locked_target.pk,
        previous_active=previous_active,
        current_active=False,
        current_role=current_role,
        audit_id=audit.pk,
        warnings=warnings,
    )


@transaction.atomic
def assign_validated_business_role(actor, target_user, target_role, reason):
    """
    Assign one validated business role and write its semantic audit event.

    Last-active-administrator protection is intentionally deferred until the
    business-role backfill is complete. Legacy is_staff data is never treated
    as evidence that a user is an ADMINISTRADOR.
    """
    normalized_reason = _validate_reason(reason)
    _validate_role(target_role)

    user_model = get_user_model()
    current_actor = _get_authorized_actor(actor, user_model)
    locked_target = _get_locked_target(target_user, user_model)

    if current_actor.pk == locked_target.pk:
        raise SelfRoleAssignmentNotAllowed(
            'Users cannot assign their own business role.'
        )
    if locked_target.is_superuser:
        raise ProtectedSuperuser(
            'Superusers cannot be managed through business-role assignment.'
        )
    if has_inconsistent_business_roles(locked_target):
        raise InconsistentBusinessRoleState(
            'The target user has multiple business roles.'
        )

    previous_role = get_business_role(locked_target)
    _validate_target_profile(locked_target, target_role)

    if previous_role == target_role:
        return RoleAssignmentResult(
            changed=False,
            previous_role=previous_role,
            new_role=target_role,
            audit_id=None,
        )

    assign_business_role(target_user, target_role)
    removed_groups = [previous_role] if previous_role else []
    audit = Auditoria.objects.create(
        tabla=ROLE_AUDIT_TABLE,
        registro_id=locked_target.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={
            'event': ROLE_AUDIT_EVENT,
            'target_user_id': locked_target.pk,
            'business_role': previous_role,
            'business_groups': removed_groups,
        },
        valor_nuevo={
            'event': ROLE_AUDIT_EVENT,
            'source': ROLE_AUDIT_SOURCE,
            'actor_id': current_actor.pk,
            'actor_email': current_actor.email,
            'target_user_id': locked_target.pk,
            'target_email': locked_target.email,
            'previous_role': previous_role,
            'new_role': target_role,
            'reason': normalized_reason,
            'removed_business_groups': removed_groups,
            'added_business_group': target_role,
        },
    )

    return RoleAssignmentResult(
        changed=True,
        previous_role=previous_role,
        new_role=target_role,
        audit_id=audit.pk,
    )


def _validate_role(role):
    if role not in BusinessRole.ALL:
        raise InvalidBusinessRole('The requested business role is invalid.')


def _validate_reason(reason):
    if not isinstance(reason, str):
        raise InvalidRoleChangeReason('A role-change reason is required.')

    normalized_reason = reason.strip()
    if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
        raise InvalidRoleChangeReason(
            f'The reason must contain between {MIN_REASON_LENGTH} and '
            f'{MAX_REASON_LENGTH} characters.'
        )
    return normalized_reason


def _validate_account_deactivation_reason(reason):
    if not isinstance(reason, str):
        raise InvalidAccountDeactivationReason(
            'An account-deactivation reason is required.'
        )

    normalized_reason = reason.strip()
    if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
        raise InvalidAccountDeactivationReason(
            f'The reason must contain between {MIN_REASON_LENGTH} and '
            f'{MAX_REASON_LENGTH} characters.'
        )
    return normalized_reason


def _validate_account_reactivation_reason(reason):
    if not isinstance(reason, str):
        raise InvalidAccountReactivationReason(
            'An account-reactivation reason is required.'
        )

    normalized_reason = reason.strip()
    if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
        raise InvalidAccountReactivationReason(
            f'The reason must contain between {MIN_REASON_LENGTH} and '
            f'{MAX_REASON_LENGTH} characters.'
        )
    return normalized_reason


def _get_authorized_actor(actor, user_model):
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PermissionDeniedForRoleAssignment(
            'A valid authenticated actor is required.'
        )

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise PermissionDeniedForRoleAssignment(
            'A valid authenticated actor is required.'
        ) from exc

    if (
        not current_actor.is_active
        or not current_actor.has_perm(BusinessPermission.ASSIGN_ROLES)
    ):
        raise PermissionDeniedForRoleAssignment(
            'The actor cannot assign business roles.'
        )
    return current_actor


def _get_account_manager_actor(actor, user_model):
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PermissionDeniedForAccountDeactivation(
            'A valid authenticated actor is required.'
        )

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise PermissionDeniedForAccountDeactivation(
            'A valid authenticated actor is required.'
        ) from exc

    if (
        not current_actor.is_active
        or not current_actor.has_perm(BusinessPermission.MANAGE_USERS)
    ):
        raise PermissionDeniedForAccountDeactivation(
            'The actor cannot deactivate user accounts.'
        )
    return current_actor


def _get_account_reactivation_actor(actor, user_model):
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PermissionDeniedForAccountReactivation(
            'A valid authenticated actor is required.'
        )

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise PermissionDeniedForAccountReactivation(
            'A valid authenticated actor is required.'
        ) from exc

    if (
        not current_actor.is_active
        or not current_actor.has_perm(BusinessPermission.MANAGE_USERS)
    ):
        raise PermissionDeniedForAccountReactivation(
            'The actor cannot reactivate user accounts.'
        )
    return current_actor


def _get_locked_target(target_user, user_model):
    if not isinstance(target_user, user_model) or target_user.pk is None:
        raise InvalidRoleAssignmentTarget('A valid target user is required.')

    try:
        return user_model.objects.select_for_update().get(pk=target_user.pk)
    except user_model.DoesNotExist as exc:
        raise InvalidRoleAssignmentTarget(
            'A valid target user is required.'
        ) from exc


def _get_locked_account_target(target_user, user_model):
    if not isinstance(target_user, user_model) or target_user.pk is None:
        raise InvalidAccountDeactivationTarget(
            'A valid target user is required.'
        )

    try:
        return user_model.objects.select_for_update().get(pk=target_user.pk)
    except user_model.DoesNotExist as exc:
        raise InvalidAccountDeactivationTarget(
            'A valid target user is required.'
        ) from exc


def _get_locked_reactivation_target(target_user, user_model):
    if not isinstance(target_user, user_model) or target_user.pk is None:
        raise InvalidAccountReactivationTarget(
            'A valid target user is required.'
        )

    try:
        return user_model.objects.select_for_update().get(pk=target_user.pk)
    except user_model.DoesNotExist as exc:
        raise InvalidAccountReactivationTarget(
            'A valid target user is required.'
        ) from exc


def _validate_target_profile(target_user, target_role):
    if target_role == BusinessRole.CLIENTE:
        if not Cliente.objects.select_for_update().filter(
            usuario=target_user
        ).exists():
            raise MissingClientProfile(
                'The CLIENTE role requires a client profile.'
            )
        return

    if target_role not in (BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL):
        return

    from gestion.models import Personal

    try:
        personal = Personal.objects.select_for_update().get(usuario=target_user)
    except Personal.DoesNotExist as exc:
        raise MissingPersonalProfile(
            'The requested labor role requires a personnel profile.'
        ) from exc

    if not personal.activo:
        raise InactivePersonal(
            'The requested labor role requires active personnel.'
        )
