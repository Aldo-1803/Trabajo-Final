"""Solicitud técnica asistida sobre el evaluador canónico BH-057."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import connection, transaction

from usuarios.models import Cliente, WalkInClientOperation
from usuarios.roles import BusinessPermission

from .models import (
    Auditoria,
    ConsentimientoAdvertenciaAsistido,
    EvaluacionRiesgoTecnico,
    Personal,
    SolicitudTecnicaAsistidaOperacion,
    SolicitudTecnicaReserva,
    TechnicalRiskOutcome,
)
from .service_skill_compatibility import service_skill_policy
from .technical_booking_request_services import (
    TechnicalBookingRequestError,
    create_technical_booking_request,
)


MAX_IDEMPOTENCY_KEY_LENGTH = 128
ASSISTED_REQUEST_CREATED = 'ASSISTED_TECHNICAL_REQUEST_CREATED'
ASSISTED_CONSENT_RECORDED = 'ASSISTED_TECHNICAL_CONSENT_RECORDED'


class AssistedTechnicalBookingError(ValueError):
    def __init__(self, code, detail, field=None):
        self.code = code
        self.detail = detail
        self.field = field
        super().__init__(detail)


class AssistedTechnicalBookingPermissionDenied(AssistedTechnicalBookingError):
    pass


class AssistedTechnicalBookingNotFound(AssistedTechnicalBookingError):
    pass


class AssistedTechnicalBookingConflict(AssistedTechnicalBookingError):
    pass


@dataclass(frozen=True)
class AssistedRequestResult:
    solicitud: SolicitudTecnicaReserva
    operation_id: str
    recovered: bool


@dataclass(frozen=True)
class AssistedConsentResult:
    solicitud: SolicitudTecnicaReserva
    consentimiento: ConsentimientoAdvertenciaAsistido
    operation_id: str
    recovered: bool


def _sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _fingerprint(payload):
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    )
    return _sha256(canonical)


def _advisory_lock(value):
    if connection.vendor != 'postgresql':
        raise RuntimeError(
            'La concurrencia de solicitudes asistidas requiere PostgreSQL.'
        )
    raw = hashlib.sha256(value.encode('utf-8')).digest()[:8]
    lock_id = int.from_bytes(raw, byteorder='big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock_id])


def _normalized_key(value):
    if not isinstance(value, str):
        raise AssistedTechnicalBookingError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
            'Idempotency-Key',
        )
    key = value.strip()
    if not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise AssistedTechnicalBookingError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
            'Idempotency-Key',
        )
    return key


def _normalized_operation_id(value):
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AssistedTechnicalBookingError(
            'INVALID_OPERATION_ID',
            'operation_id debe ser un UUID válido.',
            'operation_id',
        ) from exc


def _authorized_actor(actor):
    if not getattr(actor, 'is_authenticated', False) or actor.pk is None:
        raise AssistedTechnicalBookingPermissionDenied(
            'PERMISSION_DENIED',
            'Se requiere un operador autenticado.',
        )
    user_model = get_user_model()
    try:
        # Revalidar la autoridad sin bloquear referencias FK al actor. Una
        # supersesión concurrente puede auditarse con ese mismo Usuario.
        current = user_model.objects.select_for_update(no_key=True).get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise AssistedTechnicalBookingPermissionDenied(
            'PERMISSION_DENIED',
            'Se requiere un operador autenticado.',
        ) from exc
    if not current.is_active or not current.has_perm(
        BusinessPermission.CREATE_TURNO_FOR_CLIENT
    ):
        raise AssistedTechnicalBookingPermissionDenied(
            'PERMISSION_DENIED',
            'No tiene permisos para registrar solicitudes asistidas.',
        )
    return current


def _locked_client(cliente_id):
    try:
        cliente = (
            Cliente.objects.select_for_update()
            .select_related('usuario')
            .get(pk=cliente_id)
        )
    except Cliente.DoesNotExist as exc:
        raise AssistedTechnicalBookingNotFound(
            'CLIENT_OUT_OF_SCOPE',
            'El Cliente no está disponible en este alcance.',
        ) from exc
    if not cliente.activo or not cliente.usuario.is_active:
        raise AssistedTechnicalBookingError(
            'CLIENT_INACTIVE',
            'El Cliente debe estar activo.',
            'cliente_id',
        )
    return cliente


def _validate_services(servicios):
    services = tuple(servicios)
    service_ids = tuple(getattr(item, 'pk', None) for item in services)
    if not service_ids:
        raise AssistedTechnicalBookingError(
            'SERVICES_REQUIRED',
            'Debe seleccionar al menos un Servicio.',
            'servicio_ids',
        )
    if None in service_ids or len(set(service_ids)) != len(service_ids):
        raise AssistedTechnicalBookingError(
            'DUPLICATE_SERVICES',
            'Los Servicios deben ser persistidos, únicos y ordenados.',
            'servicio_ids',
        )
    if any(not item.activo for item in services):
        raise AssistedTechnicalBookingError(
            'SERVICE_INACTIVE',
            'Todos los Servicios deben estar activos.',
            'servicio_ids',
        )
    return services


def _validate_preferred_personal(personal, services):
    if personal is None:
        return
    if not isinstance(personal, Personal) or not personal.pk or not personal.activo:
        raise AssistedTechnicalBookingError(
            'PERSONAL_INACTIVE',
            'El Personal preferido debe estar activo.',
            'personal_preferido_id',
        )
    if not service_skill_policy(services).personal_can_perform(personal):
        raise AssistedTechnicalBookingError(
            'PERSONAL_INCOMPATIBLE',
            'El Personal preferido no es compatible con todos los Servicios.',
            'personal_preferido_id',
        )


def _existing_operation(*, command, key_digest, operation_id, actor, fingerprint,
                        matches_legacy=None):
    existing = (
        SolicitudTecnicaAsistidaOperacion.objects.select_related(
            'solicitud__evaluacion_vigente',
            'solicitud__cliente__usuario',
            'consentimiento',
            'hold__personal',
            'payment_intent__slot_hold',
        )
        .filter(command=command, idempotency_key_digest=key_digest)
        .first()
    )
    if existing is not None:
        if (
            existing.actor_id != actor.pk
            or existing.operation_id != operation_id
            or (existing.fingerprint != fingerprint
                and not (matches_legacy and matches_legacy(existing)))
        ):
            raise AssistedTechnicalBookingConflict(
                'IDEMPOTENCY_KEY_REUSED',
                'La Idempotency-Key ya fue utilizada con otro comando o actor.',
            )
        return existing
    operation_conflict = SolicitudTecnicaAsistidaOperacion.objects.filter(
        operation_id=operation_id
    ).exists()
    if operation_conflict:
        raise AssistedTechnicalBookingConflict(
            'OPERATION_ID_REUSED',
            'operation_id ya fue utilizado por otra operación.',
            'operation_id',
        )
    return None


def _audit(*, operation, event, extra=None):
    payload = {
        'event': event,
        'operation_id': str(operation.operation_id),
        'actor_id': operation.actor_id,
        'solicitud_id': operation.solicitud_id,
        'cliente_id': operation.solicitud.cliente_id,
        'medio_solicitud': operation.solicitud.medio_solicitud,
        'idempotency_key_digest': operation.idempotency_key_digest,
    }
    payload.update(extra or {})
    return Auditoria.objects.create(
        tabla='SolicitudTecnicaAsistidaOperacion',
        registro_id=operation.pk,
        usuario=operation.actor,
        accion='ALTA',
        valor_nuevo=payload,
    )


@transaction.atomic
def create_assisted_technical_request(
    *,
    actor,
    idempotency_key,
    operation_id,
    cliente_id,
    servicios,
    fecha_preferida,
    hora_preferida,
    medio_solicitud,
    personal_preferido=None,
    alta_operation_id=None,
):
    key = _normalized_key(idempotency_key)
    normalized_operation_id = _normalized_operation_id(operation_id)
    if medio_solicitud not in {
        SolicitudTecnicaReserva.MedioSolicitud.TELEFONO,
        SolicitudTecnicaReserva.MedioSolicitud.PRESENCIAL,
    }:
        raise AssistedTechnicalBookingError(
            'INVALID_MEDIUM',
            'El medio debe ser TELEFONO o PRESENCIAL.',
            'medio_solicitud',
        )
    services = _validate_services(servicios)
    service_ids = [item.pk for item in services]
    key_digest = _sha256(key)
    fingerprint = _fingerprint({
        'actor_id': getattr(actor, 'pk', None),
        'operation_id': str(normalized_operation_id),
        'cliente_id': cliente_id,
        'servicio_ids': service_ids,
        'fecha_preferida': fecha_preferida.isoformat(),
        'hora_preferida': hora_preferida.isoformat(),
        'personal_preferido_id': getattr(personal_preferido, 'pk', None),
        'medio_solicitud': medio_solicitud,
        **({'alta_operation_id': str(alta_operation_id)} if alta_operation_id else {}),
    })
    for lock_value in sorted((
        f'assisted-key:{SolicitudTecnicaAsistidaOperacion.Command.CREATE}:{key_digest}',
        f'assisted-operation:{normalized_operation_id}',
    )):
        _advisory_lock(lock_value)
    current_actor = _authorized_actor(actor)
    if alta_operation_id and not current_actor.has_perm(BusinessPermission.CREATE_WALKIN_CLIENT):
        raise AssistedTechnicalBookingPermissionDenied(
            'WALKIN_PERMISSION_DENIED', 'No tiene permisos para vincular un alta rápida.',
        )
    existing = _existing_operation(
        command=SolicitudTecnicaAsistidaOperacion.Command.CREATE,
        key_digest=key_digest,
        operation_id=normalized_operation_id,
        actor=current_actor,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return AssistedRequestResult(
            solicitud=existing.solicitud,
            operation_id=str(existing.operation_id),
            recovered=True,
        )

    alta = None
    if alta_operation_id:
        alta = WalkInClientOperation.objects.filter(
            operation_id=alta_operation_id, actor=current_actor, cliente_id=cliente_id,
        ).first()
        if alta is None:
            raise AssistedTechnicalBookingNotFound(
                'WALKIN_OPERATION_NOT_FOUND', 'El alta no está disponible para este Cliente.',
            )
    cliente = _locked_client(cliente_id)
    _validate_preferred_personal(personal_preferido, services)
    try:
        solicitud = create_technical_booking_request(
            cliente=cliente,
            servicios=services,
            fecha_preferida=fecha_preferida,
            hora_preferida=hora_preferida,
            personal_preferido=personal_preferido,
            actor=current_actor,
            medio_solicitud=medio_solicitud,
            operador_registrante=current_actor,
        )
    except TechnicalBookingRequestError as exc:
        raise AssistedTechnicalBookingError(
            'TECHNICAL_EVALUATION_INVALID',
            str(exc),
        ) from exc
    operation = SolicitudTecnicaAsistidaOperacion.objects.create(
        operation_id=normalized_operation_id,
        actor=current_actor,
        command=SolicitudTecnicaAsistidaOperacion.Command.CREATE,
        idempotency_key_digest=key_digest,
        fingerprint=fingerprint,
        solicitud=solicitud,
        alta_cliente=alta,
    )
    _audit(
        operation=operation,
        event=ASSISTED_REQUEST_CREATED,
        extra={
            'evaluation_id': solicitud.evaluacion_vigente_id,
            'outcome': solicitud.evaluacion_vigente.outcome,
            'service_ids': service_ids,
        },
    )
    return AssistedRequestResult(
        solicitud=solicitud,
        operation_id=str(operation.operation_id),
        recovered=False,
    )


def assisted_request_for_actor(*, solicitud_id, actor, lock=False):
    queryset = SolicitudTecnicaReserva.objects.select_related(
        'cliente__usuario',
        'evaluacion_vigente',
        'personal_preferido',
    ).prefetch_related(
        'servicios_solicitados__servicio',
        'consentimientos_asistidos',
        'operaciones_asistidas',
    )
    if lock:
        # Los joins a evaluación y Personal son nulables; PostgreSQL no permite
        # bloquear el lado nulable de un OUTER JOIN. La autoridad de transición
        # es la fila de Solicitud.
        queryset = queryset.select_for_update(of=('self',))
    try:
        return queryset.get(
            pk=solicitud_id,
            operador_registrante_id=getattr(actor, 'pk', None),
            medio_solicitud__in=[
                SolicitudTecnicaReserva.MedioSolicitud.TELEFONO,
                SolicitudTecnicaReserva.MedioSolicitud.PRESENCIAL,
            ],
        )
    except SolicitudTecnicaReserva.DoesNotExist as exc:
        raise AssistedTechnicalBookingNotFound(
            'REQUEST_OUT_OF_SCOPE',
            'La solicitud no está disponible en este alcance.',
        ) from exc


@transaction.atomic
def register_assisted_warning_consent(
    *,
    solicitud_id,
    actor,
    idempotency_key,
    operation_id,
    evaluacion_id,
    decision,
    motivo='',
):
    key = _normalized_key(idempotency_key)
    normalized_operation_id = _normalized_operation_id(operation_id)
    if decision not in ConsentimientoAdvertenciaAsistido.Decision.values:
        raise AssistedTechnicalBookingError(
            'INVALID_DECISION',
            'La decisión de consentimiento es inválida.',
            'decision',
        )
    normalized_reason = ' '.join((motivo or '').split())
    if len(normalized_reason) > 500:
        raise AssistedTechnicalBookingError(
            'INVALID_REASON',
            'El motivo no puede superar 500 caracteres.',
            'motivo',
        )
    if (
        decision != ConsentimientoAdvertenciaAsistido.Decision.ACEPTA
        and len(normalized_reason) < 3
    ):
        raise AssistedTechnicalBookingError(
            'REASON_REQUIRED',
            'Debe registrar un motivo para esta decisión.',
            'motivo',
        )
    key_digest = _sha256(key)
    payload = {
        'actor_id': getattr(actor, 'pk', None),
        'operation_id': str(normalized_operation_id),
        'solicitud_id': solicitud_id,
        'decision': decision,
        'motivo': normalized_reason,
    }
    fingerprint = _fingerprint({**payload, 'evaluacion_id': evaluacion_id})
    for lock_value in sorted((
        f'assisted-key:{SolicitudTecnicaAsistidaOperacion.Command.CONSENT}:{key_digest}',
        f'assisted-operation:{normalized_operation_id}',
    )):
        _advisory_lock(lock_value)
    current_actor = _authorized_actor(actor)
    existing = _existing_operation(
        command=SolicitudTecnicaAsistidaOperacion.Command.CONSENT,
        key_digest=key_digest,
        operation_id=normalized_operation_id,
        actor=current_actor,
        fingerprint=fingerprint,
        matches_legacy=lambda op: (
            op.consentimiento is not None
            and op.consentimiento.evaluacion_id == evaluacion_id
            and op.fingerprint == _fingerprint(payload)
        ),
    )
    if existing is not None:
        return AssistedConsentResult(
            solicitud=existing.solicitud,
            consentimiento=existing.consentimiento,
            operation_id=str(existing.operation_id),
            recovered=True,
        )

    solicitud = assisted_request_for_actor(
        solicitud_id=solicitud_id,
        actor=current_actor,
        lock=True,
    )
    # Mismo orden que una reevaluación: solicitud, luego evaluación. Leer la
    # evaluación de nuevo bajo lock protege también ante supersesión directa.
    evaluation = None
    if solicitud.evaluacion_vigente_id == evaluacion_id:
        evaluation = EvaluacionRiesgoTecnico.objects.select_for_update().filter(
            pk=evaluacion_id, cliente_id=solicitud.cliente_id,
        ).first()
    if (
        solicitud.estado
        != SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE
        or evaluation is None
        or evaluation.outcome != TechnicalRiskOutcome.ADVERTENCIA
        or evaluation.superseded_by_id is not None
        or not evaluation.result_snapshot.get('mensajes_cliente')
        or not solicitud.intentos_evaluacion.filter(
            evaluacion_id=evaluacion_id, intento=solicitud.intento,
        ).exists()
    ):
        raise AssistedTechnicalBookingConflict(
            'STALE_TECHNICAL_EVALUATION',
            'La evaluación ADVERTENCIA ya no está vigente.',
        )
    if ConsentimientoAdvertenciaAsistido.objects.filter(
        evaluacion=evaluation
    ).exists():
        raise AssistedTechnicalBookingConflict(
            'CONSENT_DECISION_CONFLICT',
            'Ya existe una decisión inmutable para esta evaluación.',
        )
    snapshot = evaluation.result_snapshot
    consentimiento = ConsentimientoAdvertenciaAsistido.objects.create(
        solicitud=solicitud,
        evaluacion=evaluation,
        cliente_informado=solicitud.cliente,
        operador=current_actor,
        medio_solicitud=solicitud.medio_solicitud,
        outcome=TechnicalRiskOutcome.ADVERTENCIA,
        policy_version=snapshot['policy_version'],
        warning_codes=list(snapshot.get('rule_codes', [])),
        warning_texts=list(snapshot.get('mensajes_cliente', [])),
        decision=decision,
        motivo=normalized_reason,
    )
    previous_state = solicitud.estado
    if decision == ConsentimientoAdvertenciaAsistido.Decision.ACEPTA:
        solicitud.estado = (
            SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE
        )
        solicitud.save(update_fields=['estado', 'updated_at'])
    operation = SolicitudTecnicaAsistidaOperacion.objects.create(
        operation_id=normalized_operation_id,
        actor=current_actor,
        command=SolicitudTecnicaAsistidaOperacion.Command.CONSENT,
        idempotency_key_digest=key_digest,
        fingerprint=fingerprint,
        solicitud=solicitud,
        consentimiento=consentimiento,
    )
    _audit(
        operation=operation,
        event=ASSISTED_CONSENT_RECORDED,
        extra={
            'consentimiento_id': consentimiento.pk,
            'evaluation_id': evaluation.pk,
            'policy_version': consentimiento.policy_version,
            'warning_codes': consentimiento.warning_codes,
            'decision': decision,
            'previous_state': previous_state,
            'new_state': solicitud.estado,
        },
    )
    return AssistedConsentResult(
        solicitud=solicitud,
        consentimiento=consentimiento,
        operation_id=str(operation.operation_id),
        recovered=False,
    )


def next_assisted_action(solicitud):
    if solicitud.estado == SolicitudTecnicaReserva.Estado.APROBADA_TECNICAMENTE:
        return {
            'code': 'PENDING_SLOT_SELECTION_AND_CONFIRMATION',
            'detail': 'Pendiente de selección de horario y confirmación.',
            'can_continue_to_future_hold': True,
        }
    if solicitud.estado == SolicitudTecnicaReserva.Estado.ADVERTENCIA_PENDIENTE:
        consent = solicitud.consentimientos_asistidos.filter(
            evaluacion=solicitud.evaluacion_vigente
        ).first()
        if consent is None:
            return {
                'code': 'REGISTER_ASSISTED_CONSENT',
                'detail': 'Debe registrar el consentimiento asistido.',
                'can_continue_to_future_hold': False,
            }
        return {
            'code': 'CONSENT_NOT_ACCEPTED',
            'detail': 'La decisión registrada no habilita la continuación.',
            'can_continue_to_future_hold': False,
        }
    if solicitud.estado in {
        SolicitudTecnicaReserva.Estado.EN_REVISION,
        SolicitudTecnicaReserva.Estado.INFORMACION_REQUERIDA,
    }:
        return {
            'code': 'WAIT_FOR_TECHNICAL_REVIEW',
            'detail': 'Pendiente de revisión por Personal técnicamente autorizado.',
            'can_continue_to_future_hold': False,
        }
    return {
        'code': 'TECHNICALLY_BLOCKED',
        'detail': 'La solicitud no puede continuar por su resultado técnico.',
        'can_continue_to_future_hold': False,
    }
