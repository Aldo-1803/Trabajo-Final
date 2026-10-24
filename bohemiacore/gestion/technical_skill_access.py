"""Acceso técnico basado en el vínculo real Usuario -> Personal -> Habilidad."""

from .models import PersonalHabilidad


DIAGNOSIS_SKILL_CODE = 'DIAGNOSTICO'


def user_has_active_skill(user, skill_code):
    """Indica si un Usuario activo tiene Personal y skill canónica activas."""
    if (
        user is None
        or not getattr(user, 'is_authenticated', False)
        or not getattr(user, 'is_active', False)
        or not getattr(user, 'pk', None)
    ):
        return False

    return PersonalHabilidad.objects.filter(
        personal__usuario_id=user.pk,
        personal__activo=True,
        habilidad__code=skill_code,
        habilidad__activa=True,
        activa=True,
    ).exists()
