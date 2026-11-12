"""Inventario y bootstrap conservador de perfiles técnicos de Servicios."""

from django.db import transaction

from .models import PerfilTecnicoServicio, Servicio


class TechnicalProfileStatus:
    MISSING_PROFILE = 'MISSING_PROFILE'
    PENDING = 'PENDING'
    CLASSIFIED_VALID = 'CLASSIFIED_VALID'
    INACTIVE_PROFILE = 'INACTIVE_PROFILE'
    INACTIVE_FAMILY = 'INACTIVE_FAMILY'
    INVALID_PROFILE = 'INVALID_PROFILE'


def _profile_status(profile):
    if profile is None:
        return TechnicalProfileStatus.MISSING_PROFILE
    if not profile.activa:
        return TechnicalProfileStatus.INACTIVE_PROFILE
    if profile.familia_id is not None and not profile.familia.activa:
        return TechnicalProfileStatus.INACTIVE_FAMILY
    if (
        profile.estado_clasificacion
        == PerfilTecnicoServicio.EstadoClasificacion.PENDIENTE
    ):
        return TechnicalProfileStatus.PENDING
    if (
        profile.estado_clasificacion
        == PerfilTecnicoServicio.EstadoClasificacion.CLASIFICADO
        and profile.nivel_riesgo
        != PerfilTecnicoServicio.NivelRiesgo.NO_DEFINIDO
    ):
        return TechnicalProfileStatus.CLASSIFIED_VALID
    return TechnicalProfileStatus.INVALID_PROFILE


def technical_service_profile_inventory():
    """Devuelve una fila explícita por Servicio, incluso cuando falta el perfil."""
    inventory = []
    services = Servicio.objects.select_related(
        'perfil_tecnico', 'perfil_tecnico__familia'
    ).order_by('pk')
    for service in services:
        try:
            profile = service.perfil_tecnico
        except PerfilTecnicoServicio.DoesNotExist:
            profile = None
        inventory.append({
            'service_id': service.pk,
            'service_name': service.nombre,
            'service_active': service.activo,
            'profile_id': profile.pk if profile else None,
            'status': _profile_status(profile),
            'classification_state': (
                profile.estado_clasificacion if profile else None
            ),
            'risk_level': profile.nivel_riesgo if profile else None,
            'family_code': (
                profile.familia.code
                if profile and profile.familia_id is not None
                else None
            ),
        })
    return tuple(inventory)


@transaction.atomic
def backfill_missing_technical_profiles():
    """Crea únicamente perfiles pendientes, sin inferir familia ni riesgo."""
    created_service_ids = []
    missing_service_ids = list(
        Servicio.objects.filter(perfil_tecnico__isnull=True)
        .order_by('pk')
        .values_list('pk', flat=True)
    )
    for service_id in missing_service_ids:
        _, created = PerfilTecnicoServicio.objects.get_or_create(
            servicio_id=service_id,
            defaults={
                'familia': None,
                'estado_clasificacion': (
                    PerfilTecnicoServicio.EstadoClasificacion.PENDIENTE
                ),
                'nivel_riesgo': (
                    PerfilTecnicoServicio.NivelRiesgo.NO_DEFINIDO
                ),
                'activa': True,
            },
        )
        if created:
            created_service_ids.append(service_id)
    return tuple(created_service_ids)
