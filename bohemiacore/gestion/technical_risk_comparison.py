"""Comparación diagnóstica; nunca actúa como fallback del evaluador canónico."""

from .services import SaludCapilarService
from .technical_risk_evaluator import evaluate_booking_risk
from .turno_creation_services import TurnoCreationService


def compare_legacy_and_technical_risk(
    *, cliente, servicios, fecha_solicitada, policy_version=None
):
    services = tuple(servicios)
    canonical = evaluate_booking_risk(
        cliente=cliente,
        servicios=services,
        fecha_solicitada=fecha_solicitada,
        policy_version=policy_version,
    )
    legacy_alerts = {
        service.pk: TurnoCreationService._requires_hair_damage_alert(
            cliente, service
        )
        for service in services
    }
    legacy_health_block = SaludCapilarService.obtener_bloqueo_salud_capilar(
        cliente,
        [service.pk for service in services],
    )
    return {
        'canonical': canonical,
        'legacy': {
            'hair_damage_alerts': legacy_alerts,
            'health_block': legacy_health_block,
        },
        'diverges': bool(any(legacy_alerts.values()) or legacy_health_block)
        != (canonical.outcome != 'APTO'),
    }
