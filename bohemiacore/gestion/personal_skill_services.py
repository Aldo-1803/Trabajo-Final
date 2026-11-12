from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction

from usuarios.roles import BusinessPermission

from .models import Auditoria, Habilidad, Personal, PersonalHabilidad


PERSONAL_SKILL_AUDIT_TABLE = 'PersonalHabilidad'
PERSONAL_SKILL_ASSIGNED = 'PERSONAL_SKILL_ASSIGNED'
PERSONAL_SKILL_REVOKED = 'PERSONAL_SKILL_REVOKED'
PERSONAL_SKILL_REACTIVATED = 'PERSONAL_SKILL_REACTIVATED'
PERSONAL_SKILL_ASSIGN_SOURCE = 'gestion.personal_skill_services.assign_skill'
PERSONAL_SKILL_REVOKE_SOURCE = 'gestion.personal_skill_services.revoke_skill'
PERSONAL_SKILL_REACTIVATE_SOURCE = (
    'gestion.personal_skill_services.reactivate_skill'
)
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 500


class PersonalSkillPermissionDenied(Exception):
    pass


class PersonalSkillNotFound(Exception):
    pass


class InactiveSkill(Exception):
    pass


class PersonalSkillAssignmentNotFound(Exception):
    pass


class InvalidPersonalSkillReason(Exception):
    pass


@dataclass(frozen=True)
class PersonalSkillResult:
    assignment: PersonalHabilidad
    changed: bool
    event: str | None


def _authorized_actor(actor):
    user_model = get_user_model()
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise PersonalSkillPermissionDenied

    try:
        current_actor = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise PersonalSkillPermissionDenied from exc

    if (
        not current_actor.is_active
        or not current_actor.has_perm(BusinessPermission.MANAGE_SKILLS)
    ):
        raise PersonalSkillPermissionDenied
    return current_actor


def _locked_personal(personal_id):
    try:
        return Personal.objects.select_for_update().get(pk=personal_id)
    except Personal.DoesNotExist as exc:
        raise PersonalSkillNotFound('Personal not found.') from exc


def _locked_skill(skill_id, *, require_active):
    try:
        skill = Habilidad.objects.select_for_update().get(pk=skill_id)
    except Habilidad.DoesNotExist as exc:
        raise PersonalSkillNotFound('Skill not found.') from exc
    if require_active and not skill.activa:
        raise InactiveSkill('Skill is inactive.')
    return skill


def _validated_reason(reason):
    if not isinstance(reason, str):
        raise InvalidPersonalSkillReason(
            'A reason is required for the personnel skill change.'
        )

    normalized_reason = reason.strip()
    if not MIN_REASON_LENGTH <= len(normalized_reason) <= MAX_REASON_LENGTH:
        raise InvalidPersonalSkillReason(
            f'The reason must contain between {MIN_REASON_LENGTH} and '
            f'{MAX_REASON_LENGTH} characters.'
        )
    return normalized_reason


def _write_audit(
    *,
    actor,
    assignment,
    event,
    source,
    reason,
    previous_active,
    current_active,
):
    linked_user = (
        {'user_id': assignment.personal.usuario_id}
        if assignment.personal.usuario_id is not None
        else {}
    )
    return Auditoria.objects.create(
        tabla=PERSONAL_SKILL_AUDIT_TABLE,
        registro_id=assignment.pk,
        usuario=actor,
        accion='ALTA' if event == PERSONAL_SKILL_ASSIGNED else 'MODIFICACION',
        valor_anterior={
            'event': event,
            'personal_id': assignment.personal_id,
            'skill_id': assignment.habilidad_id,
            'activa': previous_active,
            **linked_user,
        },
        valor_nuevo={
            'event': event,
            'source': source,
            'actor_id': actor.pk,
            'personal_id': assignment.personal_id,
            'skill_id': assignment.habilidad_id,
            'activa': current_active,
            'previous_active': previous_active,
            'current_active': current_active,
            'reason': reason,
            **linked_user,
        },
    )


@transaction.atomic
def assign_skill(*, actor, personal_id, skill_id, reason):
    normalized_reason = _validated_reason(reason)
    current_actor = _authorized_actor(actor)
    personal = _locked_personal(personal_id)
    skill = _locked_skill(skill_id, require_active=True)
    assignment = (
        PersonalHabilidad.objects.select_for_update()
        .filter(personal=personal, habilidad=skill)
        .first()
    )

    if assignment is None:
        assignment = PersonalHabilidad.objects.create(
            personal=personal,
            habilidad=skill,
            activa=True,
        )
        _write_audit(
            actor=current_actor,
            assignment=assignment,
            event=PERSONAL_SKILL_ASSIGNED,
            source=PERSONAL_SKILL_ASSIGN_SOURCE,
            reason=normalized_reason,
            previous_active=None,
            current_active=True,
        )
        return PersonalSkillResult(assignment, True, PERSONAL_SKILL_ASSIGNED)

    if assignment.activa:
        return PersonalSkillResult(assignment, False, None)

    assignment.activa = True
    assignment.save(update_fields=['activa'])
    _write_audit(
        actor=current_actor,
        assignment=assignment,
        event=PERSONAL_SKILL_REACTIVATED,
        source=PERSONAL_SKILL_ASSIGN_SOURCE,
        reason=normalized_reason,
        previous_active=False,
        current_active=True,
    )
    return PersonalSkillResult(assignment, True, PERSONAL_SKILL_REACTIVATED)


@transaction.atomic
def revoke_skill(*, actor, personal_id, skill_id, reason):
    normalized_reason = _validated_reason(reason)
    current_actor = _authorized_actor(actor)
    personal = _locked_personal(personal_id)
    skill = _locked_skill(skill_id, require_active=False)
    try:
        assignment = PersonalHabilidad.objects.select_for_update().get(
            personal=personal,
            habilidad=skill,
        )
    except PersonalHabilidad.DoesNotExist as exc:
        raise PersonalSkillAssignmentNotFound from exc

    if not assignment.activa:
        return PersonalSkillResult(assignment, False, None)

    assignment.activa = False
    assignment.save(update_fields=['activa'])
    _write_audit(
        actor=current_actor,
        assignment=assignment,
        event=PERSONAL_SKILL_REVOKED,
        source=PERSONAL_SKILL_REVOKE_SOURCE,
        reason=normalized_reason,
        previous_active=True,
        current_active=False,
    )
    return PersonalSkillResult(assignment, True, PERSONAL_SKILL_REVOKED)


@transaction.atomic
def reactivate_skill(*, actor, personal_id, skill_id, reason):
    normalized_reason = _validated_reason(reason)
    current_actor = _authorized_actor(actor)
    personal = _locked_personal(personal_id)
    skill = _locked_skill(skill_id, require_active=True)
    try:
        assignment = PersonalHabilidad.objects.select_for_update().get(
            personal=personal,
            habilidad=skill,
        )
    except PersonalHabilidad.DoesNotExist as exc:
        raise PersonalSkillAssignmentNotFound from exc

    if assignment.activa:
        return PersonalSkillResult(assignment, False, None)

    assignment.activa = True
    assignment.save(update_fields=['activa'])
    _write_audit(
        actor=current_actor,
        assignment=assignment,
        event=PERSONAL_SKILL_REACTIVATED,
        source=PERSONAL_SKILL_REACTIVATE_SOURCE,
        reason=normalized_reason,
        previous_active=False,
        current_active=True,
    )
    return PersonalSkillResult(assignment, True, PERSONAL_SKILL_REACTIVATED)
