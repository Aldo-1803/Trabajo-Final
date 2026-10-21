from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction

from gestion.models import Auditoria
from usuarios.models import Cliente
from usuarios.roles import (
    BusinessPermission,
    BusinessRole,
    assign_business_role,
    get_business_role,
    has_inconsistent_business_roles,
)


ROLE_AUDIT_EVENT = 'BUSINESS_ROLE_CHANGED'
ROLE_AUDIT_SOURCE = 'usuarios.access_services.assign_validated_business_role'
ROLE_AUDIT_TABLE = 'UsuarioBusinessRole'
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


@dataclass(frozen=True)
class RoleAssignmentResult:
    changed: bool
    previous_role: str | None
    new_role: str
    audit_id: int | None


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


def _get_locked_target(target_user, user_model):
    if not isinstance(target_user, user_model) or target_user.pk is None:
        raise InvalidRoleAssignmentTarget('A valid target user is required.')

    try:
        return user_model.objects.select_for_update().get(pk=target_user.pk)
    except user_model.DoesNotExist as exc:
        raise InvalidRoleAssignmentTarget(
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
