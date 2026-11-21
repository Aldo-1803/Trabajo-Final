from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from usuarios.roles import BusinessPermission

from .models import (
    Auditoria,
    PoliticaRiesgoTecnico,
)


TECHNICAL_POLICY_PUBLISHED = 'TECHNICAL_POLICY_PUBLISHED'


class TechnicalRiskPolicyPermissionDenied(Exception):
    pass


class TechnicalRiskPolicyNotFound(Exception):
    pass


class TechnicalRiskPolicyStateError(Exception):
    pass


class TechnicalRiskPolicyInvalid(Exception):
    def __init__(self, errors):
        super().__init__('La política técnica no es válida.')
        self.errors = errors


def _authorized_actor(actor):
    user_model = get_user_model()
    if (
        not isinstance(actor, user_model)
        or actor.pk is None
        or not actor.is_authenticated
    ):
        raise TechnicalRiskPolicyPermissionDenied
    try:
        current_actor = user_model.objects.get(pk=actor.pk, is_active=True)
    except user_model.DoesNotExist as exc:
        raise TechnicalRiskPolicyPermissionDenied from exc
    if not current_actor.has_perm(
        BusinessPermission.MANAGE_TECHNICAL_RISK_POLICY
    ):
        raise TechnicalRiskPolicyPermissionDenied
    return current_actor


def _validate_reference(*, service, family, label):
    errors = []
    if service is not None and not service.activo:
        errors.append(f'{label}: el Servicio {service.pk} está inactivo.')
    if family is not None and not family.activa:
        errors.append(f'{label}: la familia {family.code} está inactiva.')
    return errors


def _validate_policy_rules(policy):
    errors = []
    seen_codes = {}
    rule_groups = (
        policy.reglas_intervalo.select_related(
            'servicio_origen', 'familia_origen',
            'servicio_destino', 'familia_destino',
        ),
        policy.reglas_diagnostico_tecnico.select_related(
            'servicio_destino', 'familia_destino'
        ),
        policy.reglas_frecuencia.select_related('servicio', 'familia'),
    )
    for rules in rule_groups:
        for rule in rules:
            previous_model = seen_codes.get(rule.code)
            if previous_model is not None:
                errors.append(
                    f'El code {rule.code} está repetido entre '
                    f'{previous_model} y {rule._meta.label}.'
                )
            else:
                seen_codes[rule.code] = rule._meta.label
            try:
                rule.full_clean()
            except ValidationError as exc:
                errors.append({
                    'model': rule._meta.label,
                    'id': rule.pk,
                    'code': rule.code,
                    'errors': exc.message_dict,
                })

            if hasattr(rule, 'servicio_origen_id'):
                reference_errors = _validate_reference(
                    service=rule.servicio_origen,
                    family=rule.familia_origen,
                    label=f'{rule.code}/origen',
                ) + _validate_reference(
                    service=rule.servicio_destino,
                    family=rule.familia_destino,
                    label=f'{rule.code}/destino',
                )
            elif hasattr(rule, 'servicio_destino_id'):
                reference_errors = _validate_reference(
                    service=rule.servicio_destino,
                    family=rule.familia_destino,
                    label=f'{rule.code}/destino',
                )
            else:
                reference_errors = _validate_reference(
                    service=rule.servicio,
                    family=rule.familia,
                    label=f'{rule.code}/selector',
                )
            errors.extend(reference_errors)
    return errors


@transaction.atomic
def publish_technical_risk_policy(*, actor, policy_id):
    current_actor = _authorized_actor(actor)
    try:
        policy = PoliticaRiesgoTecnico.objects.select_for_update().get(
            pk=policy_id
        )
    except PoliticaRiesgoTecnico.DoesNotExist as exc:
        raise TechnicalRiskPolicyNotFound from exc

    if policy.estado != PoliticaRiesgoTecnico.Estado.BORRADOR:
        raise TechnicalRiskPolicyStateError(
            'Sólo una política en borrador puede publicarse.'
        )

    errors = _validate_policy_rules(policy)
    if errors:
        raise TechnicalRiskPolicyInvalid(errors)

    policy.estado = PoliticaRiesgoTecnico.Estado.PUBLICADA
    policy.publicada_at = timezone.now()
    policy.publicada_por = current_actor
    policy._allow_explicit_publication = True
    policy.save(update_fields=['estado', 'publicada_at', 'publicada_por'])

    Auditoria.objects.create(
        tabla='PoliticaRiesgoTecnico',
        registro_id=policy.pk,
        usuario=current_actor,
        accion='MODIFICACION',
        valor_anterior={
            'estado': PoliticaRiesgoTecnico.Estado.BORRADOR,
        },
        valor_nuevo={
            'event': TECHNICAL_POLICY_PUBLISHED,
            'estado': PoliticaRiesgoTecnico.Estado.PUBLICADA,
            'version': policy.version,
            'actor_id': current_actor.pk,
        },
    )
    return policy
