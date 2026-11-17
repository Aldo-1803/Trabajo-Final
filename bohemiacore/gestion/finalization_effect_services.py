"""Planificación, ejecución y trazabilidad de efectos de finalización."""

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction

from .hair_profile_services import apply_automatic_profile_impact
from .models import (
    AgendaCuidados,
    Auditoria,
    CambioPerfilCapilar,
    ConfiguracionRetoque,
    EfectoFinalizacion,
    FinalizacionTurno,
    Notificacion,
    Promocion,
    ReglaCuidado,
    Rutina,
    RutinaCliente,
)
from .routine_services import ensure_internal_routine_assignment


EFFECT_PLAN_SCHEMA = 'turno.finalization.effects:v1'


class FinalizationEffectLedgerConflict(Exception):
    pass


@dataclass(frozen=True)
class EffectDescriptor:
    tipo: str
    estado: str
    clave_logica: str
    parametros_snapshot: dict
    resultado: dict
    detalle_turno_id: int | None = None
    servicio_id: int | None = None
    regla_cuidado_id: int | None = None
    rutina_id: int | None = None
    configuracion_retoque_id: int | None = None


@dataclass(frozen=True)
class EffectExecutionResult:
    legacy_effects: dict
    descriptors: tuple[EffectDescriptor, ...]


def _descriptor_from_effect(effect):
    return EffectDescriptor(
        tipo=effect.tipo,
        estado=effect.estado,
        clave_logica=effect.clave_logica,
        detalle_turno_id=effect.detalle_turno_id,
        servicio_id=effect.servicio_id,
        regla_cuidado_id=effect.regla_cuidado_id,
        rutina_id=effect.rutina_id,
        configuracion_retoque_id=effect.configuracion_retoque_id,
        parametros_snapshot=effect.parametros_snapshot,
        resultado=effect.resultado,
    )


def _existing_effect(finalization, logical_key):
    return EfectoFinalizacion.objects.filter(
        finalizacion=finalization,
        clave_logica=logical_key,
    ).first()


def record_effect_descriptor(*, finalization, descriptor):
    effect = EfectoFinalizacion.objects.create(
        finalizacion=finalization,
        tipo=descriptor.tipo,
        estado=descriptor.estado,
        clave_logica=descriptor.clave_logica,
        detalle_turno_id=descriptor.detalle_turno_id,
        servicio_id=descriptor.servicio_id,
        regla_cuidado_id=descriptor.regla_cuidado_id,
        rutina_id=descriptor.rutina_id,
        configuracion_retoque_id=descriptor.configuracion_retoque_id,
        parametros_snapshot=descriptor.parametros_snapshot,
        resultado=descriptor.resultado,
    )
    return effect


def _care_dates(turno_date, rule):
    if rule.tipo == 'RESTRICCION':
        duration = rule.dias_duracion if rule.dias_duracion > 0 else 1
        return [
            turno_date + timedelta(days=offset)
            for offset in range(duration)
        ]
    if rule.tipo == 'HABITO':
        start = turno_date + timedelta(days=1)
        if rule.frecuencia_dias and rule.frecuencia_dias > 0:
            return [
                start + timedelta(days=offset)
                for offset in range(0, 30, rule.frecuencia_dias)
            ]
        return [start]
    return []


def build_effect_plan(*, turno, details):
    """Captura bajo locks los parámetros exactos usados por los efectos."""
    service_ids = [detail.servicio_id for detail in details]
    rules = list(
        ReglaCuidado.objects.select_for_update(of=('self',))
        .filter(servicio_id__in=service_ids)
        .order_by('servicio_id', 'pk')
    )
    configurations = list(
        ConfiguracionRetoque.objects.select_for_update(of=('self',))
        .filter(servicio_principal_id__in=service_ids)
        .order_by('servicio_principal_id', 'pk')
    )
    configuration_by_service = {}
    for configuration in configurations:
        configuration_by_service.setdefault(
            configuration.servicio_principal_id,
            configuration,
        )

    routine_ids = {
        detail.servicio.rutina_recomendada_id
        for detail in details
        if detail.servicio.rutina_recomendada_id is not None
    }
    routine_ids.update(
        rule.rutina_id for rule in rules if rule.rutina_id is not None
    )
    routines = {
        routine.pk: routine
        for routine in Rutina.objects.select_for_update().filter(
            pk__in=routine_ids
        ).order_by('pk')
    }

    rules_by_service = {}
    for rule in rules:
        rules_by_service.setdefault(rule.servicio_id, []).append(rule)

    routine_causes = {}
    detail_plans = []
    for detail in details:
        service = detail.servicio
        care_rules = []
        if service.rutina_recomendada_id is not None:
            routine_causes.setdefault(
                service.rutina_recomendada_id,
                [],
            ).append({
                'detalle_turno_id': detail.pk,
                'origen': 'SERVICIO',
                'regla_cuidado_id': None,
            })
        for rule in rules_by_service.get(service.pk, []):
            dates = _care_dates(turno.fecha, rule)
            care_rules.append({
                'regla_cuidado_id': rule.pk,
                'tipo': rule.tipo,
                'descripcion': rule.descripcion,
                'dias_duracion': rule.dias_duracion,
                'frecuencia_dias': rule.frecuencia_dias,
                'rutina_id': rule.rutina_id,
                'fechas': [value.isoformat() for value in dates],
            })
            if rule.rutina_id is not None:
                routine_causes.setdefault(rule.rutina_id, []).append({
                    'detalle_turno_id': detail.pk,
                    'origen': 'REGLA_CUIDADO',
                    'regla_cuidado_id': rule.pk,
                })

        configuration = configuration_by_service.get(service.pk)
        retouch = None
        if configuration is not None:
            ideal_date = turno.fecha + timedelta(
                days=configuration.dias_sugeridos
            )
            notice_date = ideal_date - timedelta(days=7)
            retouch = {
                'configuracion_retoque_id': configuration.pk,
                'servicio_retoque_id': configuration.servicio_retoque_id,
                'dias_sugeridos': configuration.dias_sugeridos,
                'descuento_retoque': configuration.descuento_retoque,
                'fecha_inicio': notice_date.isoformat(),
                'fecha_fin': (ideal_date + timedelta(days=7)).isoformat(),
                'fecha_envio_notificacion': notice_date.isoformat(),
            }

        detail_plans.append({
            'detalle_turno_id': detail.pk,
            'servicio_id': service.pk,
            'servicio_nombre': service.nombre,
            'impacto_porosidad_id': service.impacto_porosidad_id,
            'impacto_estado_id': service.impacto_estado_id,
            'rutina_recomendada_id': service.rutina_recomendada_id,
            'reglas_cuidado': care_rules,
            'retoque': retouch,
        })

    routine_plans = []
    for routine_id in sorted(routine_causes):
        routine = routines[routine_id]
        routine_plans.append({
            'rutina_id': routine.pk,
            'version': routine.version,
            'nombre': routine.nombre,
            'causas': routine_causes[routine_id],
        })

    return {
        'schema': EFFECT_PLAN_SCHEMA,
        'turno_id': turno.pk,
        'turno_fecha': turno.fecha.isoformat(),
        'cliente_id': turno.cliente_id,
        'detalles': detail_plans,
        'rutinas': routine_plans,
        'diagnostico_automatico': {
            'habilitado': False,
            'motivo': 'NO_PROFESSIONAL_EVALUATION_PERFORMED',
        },
    }


def _profile_effect(*, turno, actor, plan, finalization):
    existing = _existing_effect(finalization, 'profile-impact')
    if existing is not None:
        return existing.resultado['legacy'], _descriptor_from_effect(existing)
    detail_plans = plan['detalles']
    service_impacts = [
        {
            'detalle_turno_id': detail['detalle_turno_id'],
            'servicio_id': detail['servicio_id'],
            'impacto_porosidad_id': detail['impacto_porosidad_id'],
            'impacto_estado_id': detail['impacto_estado_id'],
        }
        for detail in detail_plans
    ]
    base_snapshot = {
        'schema': plan['schema'],
        'service_impacts': service_impacts,
    }
    if len(detail_plans) != 1:
        reason = 'NO_SERVICE' if not detail_plans else 'MULTISERVICE_POLICY_PENDING'
        result = {
            'applied': False,
            'reason': reason,
            'updated_fields': [],
            'service_impacts': service_impacts,
        }
        descriptor = EffectDescriptor(
            tipo=EfectoFinalizacion.Tipo.IMPACTO_PERFIL,
            estado=EfectoFinalizacion.Estado.OMITIDO,
            clave_logica='profile-impact',
            parametros_snapshot=base_snapshot,
            resultado={'reason': reason, 'legacy': result},
        )
        record_effect_descriptor(finalization=finalization, descriptor=descriptor)
        return result, descriptor

    detail = detail_plans[0]
    explicit_values = {}
    if detail['impacto_porosidad_id'] is not None:
        explicit_values['porosidad_cabello'] = detail['impacto_porosidad_id']
    if detail['impacto_estado_id'] is not None:
        explicit_values['estado_general'] = detail['impacto_estado_id']
    if not explicit_values:
        result = {
            'applied': False,
            'reason': 'SINGLE_SERVICE_EXPLICIT_IMPACT',
            'updated_fields': [],
            'profile_change_id': None,
            'service_impacts': service_impacts,
        }
        descriptor = EffectDescriptor(
            tipo=EfectoFinalizacion.Tipo.IMPACTO_PERFIL,
            estado=EfectoFinalizacion.Estado.OMITIDO,
            clave_logica='profile-impact',
            detalle_turno_id=detail['detalle_turno_id'],
            servicio_id=detail['servicio_id'],
            parametros_snapshot=base_snapshot,
            resultado={'reason': 'NO_EXPLICIT_IMPACT', 'legacy': result},
        )
        record_effect_descriptor(finalization=finalization, descriptor=descriptor)
        return result, descriptor

    synchronization = apply_automatic_profile_impact(
        actor=actor,
        cliente_id=turno.cliente_id,
        values=explicit_values,
        reason=(
            f'Impacto explícito causado por la finalización '
            f'{finalization.public_id} del Turno {turno.pk}.'
        ),
    )
    result = {
        'applied': bool(synchronization.updated_fields),
        'reason': 'SINGLE_SERVICE_EXPLICIT_IMPACT',
        'updated_fields': list(synchronization.updated_fields),
        'profile_change_id': (
            synchronization.change.pk
            if synchronization.change is not None
            else None
        ),
        'service_impacts': service_impacts,
    }
    descriptor = EffectDescriptor(
        tipo=EfectoFinalizacion.Tipo.IMPACTO_PERFIL,
        estado=EfectoFinalizacion.Estado.COMPLETADO,
        clave_logica='profile-impact',
        detalle_turno_id=detail['detalle_turno_id'],
        servicio_id=detail['servicio_id'],
        parametros_snapshot={
            **base_snapshot,
            'valores_explicitos': explicit_values,
        },
        resultado={
            'model': 'CambioPerfilCapilar',
            'id': result['profile_change_id'],
            'changed': result['applied'],
            'updated_fields': result['updated_fields'],
            'legacy': result,
        },
    )
    record_effect_descriptor(finalization=finalization, descriptor=descriptor)
    return result, descriptor


def _care_effects(*, turno, plan, finalization):
    care_ids = []
    notification_ids = []
    descriptors = []
    for detail in plan['detalles']:
        for rule in detail['reglas_cuidado']:
            rule_snapshot = {
                'schema': plan['schema'],
                'tipo': rule['tipo'],
                'descripcion': rule['descripcion'],
                'dias_duracion': rule['dias_duracion'],
                'frecuencia_dias': rule['frecuencia_dias'],
                'fechas': rule['fechas'],
            }
            for care_date in rule['fechas']:
                logical_key = (
                    f"care-item:{detail['detalle_turno_id']}:"
                    f"{rule['regla_cuidado_id']}:{care_date}"
                )
                existing = _existing_effect(finalization, logical_key)
                if existing is not None:
                    care_ids.append(existing.resultado['id'])
                    descriptors.append(_descriptor_from_effect(existing))
                    continue
                care = AgendaCuidados.objects.create(
                    cliente=turno.cliente,
                    fecha=care_date,
                    titulo=(
                        'RESTRICCIÓN'
                        if rule['tipo'] == 'RESTRICCION'
                        else 'Hábito Sugerido'
                    ),
                    descripcion=(
                        f"{rule['descripcion']} - Servicio: "
                        f"{detail['servicio_nombre']}"
                    ),
                )
                care_ids.append(care.pk)
                descriptor = EffectDescriptor(
                    tipo=EfectoFinalizacion.Tipo.CUIDADO_AGENDA,
                    estado=EfectoFinalizacion.Estado.COMPLETADO,
                    clave_logica=logical_key,
                    detalle_turno_id=detail['detalle_turno_id'],
                    servicio_id=detail['servicio_id'],
                    regla_cuidado_id=rule['regla_cuidado_id'],
                    parametros_snapshot=rule_snapshot,
                    resultado={'model': 'AgendaCuidados', 'id': care.pk},
                )
                record_effect_descriptor(
                    finalization=finalization,
                    descriptor=descriptor,
                )
                descriptors.append(descriptor)
            notification_key = (
                f"care-notification:{detail['detalle_turno_id']}:"
                f"{rule['regla_cuidado_id']}"
            )
            existing = _existing_effect(finalization, notification_key)
            if existing is not None:
                notification_ids.append(existing.resultado['id'])
                descriptors.append(_descriptor_from_effect(existing))
                continue
            notification = Notificacion.objects.create(
                usuario=turno.cliente.usuario,
                tipo='recordatorio',
                titulo=f"Cuidados post {detail['servicio_nombre']}",
                mensaje=(
                    f"{rule['descripcion']}. "
                    f"(Válido por {rule['dias_duracion']} días)"
                ),
                origen_entidad='Turno',
                origen_id=turno.pk,
                datos_extra={
                    'detalle_turno_id': detail['detalle_turno_id'],
                    'regla_cuidado_id': rule['regla_cuidado_id'],
                },
            )
            notification_ids.append(notification.pk)
            descriptor = EffectDescriptor(
                tipo=EfectoFinalizacion.Tipo.NOTIFICACION_CUIDADO,
                estado=EfectoFinalizacion.Estado.COMPLETADO,
                clave_logica=notification_key,
                detalle_turno_id=detail['detalle_turno_id'],
                servicio_id=detail['servicio_id'],
                regla_cuidado_id=rule['regla_cuidado_id'],
                parametros_snapshot=rule_snapshot,
                resultado={'model': 'Notificacion', 'id': notification.pk},
            )
            record_effect_descriptor(
                finalization=finalization,
                descriptor=descriptor,
            )
            descriptors.append(descriptor)
    return care_ids, notification_ids, descriptors


def _routine_effects(*, turno, plan, finalization):
    assignment_ids = []
    descriptors = []
    routines = {
        routine.pk: routine
        for routine in Rutina.objects.filter(
            pk__in=[item['rutina_id'] for item in plan['rutinas']]
        ).order_by('pk')
    }
    for routine_plan in plan['rutinas']:
        logical_key = f"routine-assignment:{routine_plan['rutina_id']}"
        existing = _existing_effect(finalization, logical_key)
        if existing is not None:
            assignment_ids.append(existing.resultado['id'])
            descriptors.append(_descriptor_from_effect(existing))
            continue
        routine = routines[routine_plan['rutina_id']]
        assignment, created = ensure_internal_routine_assignment(
            cliente=turno.cliente,
            rutina=routine,
        )
        assignment_ids.append(assignment.pk)
        descriptor = EffectDescriptor(
            tipo=EfectoFinalizacion.Tipo.ASIGNACION_RUTINA,
            estado=EfectoFinalizacion.Estado.COMPLETADO,
            clave_logica=logical_key,
            rutina_id=routine.pk,
            parametros_snapshot={
                'schema': plan['schema'],
                **routine_plan,
            },
            resultado={
                'model': 'RutinaCliente',
                'id': assignment.pk,
                'created': created,
                'assigned_version': assignment.version_asignada,
            },
        )
        record_effect_descriptor(
            finalization=finalization,
            descriptor=descriptor,
        )
        descriptors.append(descriptor)
    return assignment_ids, descriptors


def _retouch_effects(*, turno, plan, finalization):
    promotion_ids = []
    descriptors = []
    for detail in plan['detalles']:
        retouch = detail['retoque']
        if retouch is None:
            logical_key = (
                f"retouch-promotion:{detail['detalle_turno_id']}:none"
            )
            existing = _existing_effect(finalization, logical_key)
            if existing is not None:
                descriptors.append(_descriptor_from_effect(existing))
                continue
            descriptor = EffectDescriptor(
                tipo=EfectoFinalizacion.Tipo.PROMOCION_RETOQUE,
                estado=EfectoFinalizacion.Estado.OMITIDO,
                clave_logica=logical_key,
                detalle_turno_id=detail['detalle_turno_id'],
                servicio_id=detail['servicio_id'],
                parametros_snapshot={'schema': plan['schema']},
                resultado={'reason': 'NO_RETOUCH_CONFIGURATION'},
            )
            record_effect_descriptor(
                finalization=finalization,
                descriptor=descriptor,
            )
            descriptors.append(descriptor)
            continue
        logical_key = (
            f"retouch-promotion:{detail['detalle_turno_id']}:"
            f"{retouch['configuracion_retoque_id']}"
        )
        existing = _existing_effect(finalization, logical_key)
        if existing is not None:
            promotion_ids.append(existing.resultado['id'])
            descriptors.append(_descriptor_from_effect(existing))
            continue
        promotion = Promocion.objects.create(
            nombre=f"Mantenimiento de {detail['servicio_nombre']}",
            descripcion=(
                'Es el momento ideal para retocar tu '
                f"{detail['servicio_nombre']} y lucir impecable."
            ),
            tipo='RETOQUE',
            descuento_porcentaje=retouch['descuento_retoque'],
            fecha_inicio=retouch['fecha_inicio'],
            fecha_fin=retouch['fecha_fin'],
            fecha_envio_notificacion=retouch['fecha_envio_notificacion'],
            cliente_especifico=turno.cliente,
            is_active=True,
        )
        promotion.servicios.add(retouch['servicio_retoque_id'])
        promotion_ids.append(promotion.pk)
        descriptor = EffectDescriptor(
            tipo=EfectoFinalizacion.Tipo.PROMOCION_RETOQUE,
            estado=EfectoFinalizacion.Estado.COMPLETADO,
            clave_logica=logical_key,
            detalle_turno_id=detail['detalle_turno_id'],
            servicio_id=detail['servicio_id'],
            configuracion_retoque_id=retouch['configuracion_retoque_id'],
            parametros_snapshot={'schema': plan['schema'], **retouch},
            resultado={'model': 'Promocion', 'id': promotion.pk},
        )
        record_effect_descriptor(
            finalization=finalization,
            descriptor=descriptor,
        )
        descriptors.append(descriptor)
    return promotion_ids, descriptors


@transaction.atomic
def execute_finalization_effects(
    *,
    turno,
    actor,
    plan,
    finalization,
):
    finalization = FinalizacionTurno.objects.select_for_update().get(
        pk=finalization.pk
    )
    profile, profile_descriptor = _profile_effect(
        turno=turno,
        actor=actor,
        plan=plan,
        finalization=finalization,
    )
    care_ids, care_notification_ids, care_descriptors = _care_effects(
        turno=turno,
        plan=plan,
        finalization=finalization,
    )
    routine_ids, routine_descriptors = _routine_effects(
        turno=turno,
        plan=plan,
        finalization=finalization,
    )
    existing_notification = _existing_effect(finalization, 'final-notification')
    if existing_notification is None:
        final_notification = Notificacion.objects.create(
            usuario=turno.cliente.usuario,
            titulo='¡Servicio Finalizado!',
            mensaje='Tu servicio fue finalizado y ya puedes consultar sus cuidados.',
            tipo='informativa',
            canal='app',
            estado='pendiente',
            origen_entidad='Turno',
            origen_id=turno.pk,
            datos_extra={
                'finalization_public_id': str(finalization.public_id)
            },
        )
        final_notification_descriptor = EffectDescriptor(
            tipo=EfectoFinalizacion.Tipo.NOTIFICACION_FINAL,
            estado=EfectoFinalizacion.Estado.COMPLETADO,
            clave_logica='final-notification',
            parametros_snapshot={
                'schema': plan['schema'],
                'canal': 'app',
                'tipo': 'informativa',
            },
            resultado={'model': 'Notificacion', 'id': final_notification.pk},
        )
        record_effect_descriptor(
            finalization=finalization,
            descriptor=final_notification_descriptor,
        )
    else:
        final_notification = Notificacion.objects.get(
            pk=existing_notification.resultado['id']
        )
        final_notification_descriptor = _descriptor_from_effect(
            existing_notification
        )
    promotion_ids, promotion_descriptors = _retouch_effects(
        turno=turno,
        plan=plan,
        finalization=finalization,
    )
    existing_diagnosis = _existing_effect(finalization, 'automatic-diagnosis')
    if existing_diagnosis is None:
        diagnosis_descriptor = EffectDescriptor(
            tipo=EfectoFinalizacion.Tipo.DIAGNOSTICO_AUTOMATICO,
            estado=EfectoFinalizacion.Estado.OMITIDO,
            clave_logica='automatic-diagnosis',
            parametros_snapshot={
                'schema': plan['schema'],
                **plan['diagnostico_automatico'],
            },
            resultado={'reason': plan['diagnostico_automatico']['motivo']},
        )
        record_effect_descriptor(
            finalization=finalization,
            descriptor=diagnosis_descriptor,
        )
    else:
        diagnosis_descriptor = _descriptor_from_effect(existing_diagnosis)
    descriptors = (
        profile_descriptor,
        *care_descriptors,
        *routine_descriptors,
        final_notification_descriptor,
        *promotion_descriptors,
        diagnosis_descriptor,
    )
    return EffectExecutionResult(
        legacy_effects={
            'automatic_diagnosis_ids': [],
            'profile': profile,
            'care_item_ids': care_ids,
            'rule_notification_ids': care_notification_ids,
            'routine_assignment_ids': routine_ids,
            'final_notification_id': final_notification.pk,
            'promotion_ids': promotion_ids,
        },
        descriptors=tuple(descriptors),
    )


def audit_effect_descriptor(*, audit_id, plan):
    return EffectDescriptor(
        tipo=EfectoFinalizacion.Tipo.AUDITORIA,
        estado=EfectoFinalizacion.Estado.COMPLETADO,
        clave_logica='semantic-audit',
        parametros_snapshot={
            'schema': plan['schema'],
            'event': 'TURN_FINALIZED',
        },
        resultado={'model': 'Auditoria', 'id': audit_id},
    )


def effect_summary(descriptors):
    counts = {
        state: sum(item.estado == state for item in descriptors)
        for state in EfectoFinalizacion.Estado.values
    }
    items = []
    warnings = []
    for item in descriptors:
        public_result = {
            key: value
            for key, value in item.resultado.items()
            if key in {'model', 'id', 'created', 'changed', 'reason'}
        }
        items.append({
            'type': item.tipo,
            'state': item.estado,
            'logical_key': item.clave_logica,
            'detalle_turno_id': item.detalle_turno_id,
            'servicio_id': item.servicio_id,
            'result': public_result,
        })
        reason = item.resultado.get('reason')
        if reason in {
            'MULTISERVICE_POLICY_PENDING',
            'NO_PROFESSIONAL_EVALUATION_PERFORMED',
        }:
            warnings.append(reason)
    return {
        'schema': EFFECT_PLAN_SCHEMA,
        'counts': counts,
        'items': items,
        'warnings': sorted(set(warnings)),
    }


OUTPUT_MODELS = {
    'AgendaCuidados': AgendaCuidados,
    'Auditoria': Auditoria,
    'CambioPerfilCapilar': CambioPerfilCapilar,
    'Notificacion': Notificacion,
    'Promocion': Promocion,
    'RutinaCliente': RutinaCliente,
}


def inspect_effect_ledger(finalization):
    """Reconciliación de sólo lectura; no reejecuta reglas ni cambia perfil."""
    summary = finalization.efectos.get('summary', {})
    if summary.get('schema') != EFFECT_PLAN_SCHEMA:
        return {
            'finalization_id': str(finalization.public_id),
            'reconciliation_supported': False,
            'legacy_unversioned': True,
            'complete': None,
            'missing_effects': [],
            'unexpected_effects': [],
            'missing_outputs': [],
            'pending': [],
            'failed': [],
        }
    expected_items = summary.get('items', [])
    expected_keys = {item['logical_key'] for item in expected_items}
    persisted = list(finalization.efectos_trazables.order_by('pk'))
    persisted_keys = {effect.clave_logica for effect in persisted}
    missing_outputs = []
    for effect in persisted:
        model_name = effect.resultado.get('model')
        output_id = effect.resultado.get('id')
        model = OUTPUT_MODELS.get(model_name)
        if model is not None and output_id is not None:
            if not model.objects.filter(pk=output_id).exists():
                missing_outputs.append(effect.clave_logica)
    return {
        'finalization_id': str(finalization.public_id),
        'reconciliation_supported': True,
        'legacy_unversioned': False,
        'complete': (
            expected_keys == persisted_keys
            and not missing_outputs
            and all(
                effect.estado
                in {
                    EfectoFinalizacion.Estado.COMPLETADO,
                    EfectoFinalizacion.Estado.OMITIDO,
                }
                for effect in persisted
            )
        ),
        'missing_effects': sorted(expected_keys - persisted_keys),
        'unexpected_effects': sorted(persisted_keys - expected_keys),
        'missing_outputs': sorted(missing_outputs),
        'pending': [
            effect.clave_logica
            for effect in persisted
            if effect.estado == EfectoFinalizacion.Estado.PENDIENTE
        ],
        'failed': [
            effect.clave_logica
            for effect in persisted
            if effect.estado == EfectoFinalizacion.Estado.FALLIDO
        ],
    }
