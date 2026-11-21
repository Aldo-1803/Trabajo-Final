"""Predicados canónicos para capacidades efectivas compuestas."""

from usuarios.roles import BusinessPermission

from .technical_skill_access import (
    DIAGNOSIS_SKILL_CODE,
    user_has_active_skill,
)


CAPABILITY_TECHNICAL_BOOKING_REVIEW = 'technical_booking.review'
CAPABILITY_DIAGNOSIS_CREATE = 'diagnosis.create'
CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL = 'technical_record.read_global'
CAPABILITY_TECHNICAL_RECORD_MANAGE = 'technical_record.manage'
CAPABILITY_SERVICE_FORMULA_MANAGE = 'service_formula.manage'
CAPABILITY_CONTENT_AUTHOR = 'content.author'
CAPABILITY_CONTENT_MANAGE_GLOBAL = 'content.manage_global'

SESSION_CAPABILITY_NAMES = (
    CAPABILITY_TECHNICAL_BOOKING_REVIEW,
    CAPABILITY_DIAGNOSIS_CREATE,
    CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL,
    CAPABILITY_TECHNICAL_RECORD_MANAGE,
    CAPABILITY_SERVICE_FORMULA_MANAGE,
    CAPABILITY_CONTENT_AUTHOR,
    CAPABILITY_CONTENT_MANAGE_GLOBAL,
)


def _is_active_authenticated_user(user):
    return bool(
        user is not None
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_active', False)
        and getattr(user, 'pk', None)
    )


def active_personal_for_user(user):
    """Return the active owned Personal relation or None."""
    if not _is_active_authenticated_user(user):
        return None
    personal = getattr(user, 'perfil_profesional', None)
    if personal is None or not personal.activo:
        return None
    return personal


def _active_user_has_permission(user, permission):
    return bool(
        _is_active_authenticated_user(user)
        and user.has_perm(permission)
    )


def _user_can_with_diagnosis_skill(
    user,
    permission,
    *,
    has_diagnosis_skill=None,
):
    if not _active_user_has_permission(user, permission):
        return False
    if has_diagnosis_skill is None:
        has_diagnosis_skill = user_has_active_skill(
            user,
            DIAGNOSIS_SKILL_CODE,
        )
    return bool(has_diagnosis_skill)


def user_can_review_technical_booking(user):
    return _user_can_with_diagnosis_skill(
        user,
        BusinessPermission.REVIEW_TECHNICAL_BOOKING,
    )


def user_can_create_diagnosis(user):
    return _user_can_with_diagnosis_skill(
        user,
        BusinessPermission.CREATE_DIAGNOSIS,
    )


def user_can_read_global_technical_record(user):
    return _user_can_with_diagnosis_skill(
        user,
        BusinessPermission.MANAGE_TECHNICAL_RECORD,
    )


def user_can_manage_technical_record(user):
    return _user_can_with_diagnosis_skill(
        user,
        BusinessPermission.MANAGE_TECHNICAL_RECORD,
    )


def user_can_manage_service_formula(user):
    return _user_can_with_diagnosis_skill(
        user,
        BusinessPermission.MANAGE_FORMULAS,
    )


def user_can_author_content(user):
    return active_personal_for_user(user) is not None


def user_can_manage_content_globally(user):
    return _active_user_has_permission(
        user,
        BusinessPermission.MANAGE_CONTENT,
    )


def build_session_capabilities(user):
    """Build the complete, boolean-only session capability contract."""
    has_diagnosis_skill = user_has_active_skill(
        user,
        DIAGNOSIS_SKILL_CODE,
    )
    return {
        CAPABILITY_TECHNICAL_BOOKING_REVIEW: (
            _user_can_with_diagnosis_skill(
                user,
                BusinessPermission.REVIEW_TECHNICAL_BOOKING,
                has_diagnosis_skill=has_diagnosis_skill,
            )
        ),
        CAPABILITY_DIAGNOSIS_CREATE: _user_can_with_diagnosis_skill(
            user,
            BusinessPermission.CREATE_DIAGNOSIS,
            has_diagnosis_skill=has_diagnosis_skill,
        ),
        CAPABILITY_TECHNICAL_RECORD_READ_GLOBAL: (
            _user_can_with_diagnosis_skill(
                user,
                BusinessPermission.MANAGE_TECHNICAL_RECORD,
                has_diagnosis_skill=has_diagnosis_skill,
            )
        ),
        CAPABILITY_TECHNICAL_RECORD_MANAGE: (
            _user_can_with_diagnosis_skill(
                user,
                BusinessPermission.MANAGE_TECHNICAL_RECORD,
                has_diagnosis_skill=has_diagnosis_skill,
            )
        ),
        CAPABILITY_SERVICE_FORMULA_MANAGE: (
            _user_can_with_diagnosis_skill(
                user,
                BusinessPermission.MANAGE_FORMULAS,
                has_diagnosis_skill=has_diagnosis_skill,
            )
        ),
        CAPABILITY_CONTENT_AUTHOR: user_can_author_content(user),
        CAPABILITY_CONTENT_MANAGE_GLOBAL: (
            user_can_manage_content_globally(user)
        ),
    }
