import hashlib
import json
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.db.models import Q

from gestion.models import Auditoria

from .contact_normalization import (
    InvalidArgentinePhone,
    mask_email,
    mask_phone,
    normalize_argentine_phone,
)
from .models import Cliente, WalkInClientOperation
from .roles import (
    BusinessPermission,
    BusinessRole,
    assign_business_role,
    build_business_role_audit_metadata,
    get_business_roles,
)


WALKIN_CLIENT_AUDIT_TABLE = 'WalkInClientOperation'
WALKIN_CLIENT_CREATED_EVENT = 'WALKIN_CLIENT_CREATED'
WALKIN_CLIENT_EXISTING_SELECTED_EVENT = 'WALKIN_CLIENT_EXISTING_SELECTED'
WALKIN_CLIENT_SOURCE = 'usuarios.walkin_client_services.create_walkin_client'
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 500
MAX_IDEMPOTENCY_KEY_LENGTH = 128


class WalkInClientError(ValueError):
    def __init__(self, code, detail, field=None, candidates=None):
        self.code = code
        self.detail = detail
        self.field = field
        self.candidates = tuple(candidates or ())
        super().__init__(detail)


class WalkInClientPermissionDenied(WalkInClientError):
    pass


class WalkInClientConflict(WalkInClientError):
    pass


class WalkInClientNotFound(WalkInClientError):
    pass


@dataclass(frozen=True)
class WalkInClientResult:
    created: bool
    recovered: bool
    cliente_id: int
    user_id: int
    display_name: str
    masked_email: str | None
    masked_phone: str | None
    client_active: bool
    web_access_status: str
    operation_id: str


def _sha256(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _advisory_lock(value):
    if connection.vendor != 'postgresql':
        raise RuntimeError('Walk-in identity locking requires PostgreSQL.')
    raw = hashlib.sha256(value.encode('utf-8')).digest()[:8]
    lock_id = int.from_bytes(raw, byteorder='big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock_id])


def _normalize_required(value, field, max_length):
    if not isinstance(value, str):
        raise WalkInClientError('INVALID_PAYLOAD', f'{field} es requerido.', field)
    normalized = ' '.join(value.split())
    if not normalized or len(normalized) > max_length:
        raise WalkInClientError('INVALID_PAYLOAD', f'{field} es inválido.', field)
    return normalized


def _normalize_optional(value, field, max_length):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise WalkInClientError('INVALID_PAYLOAD', f'{field} es inválido.', field)
    normalized = ' '.join(value.split())
    if len(normalized) > max_length:
        raise WalkInClientError('INVALID_PAYLOAD', f'{field} es inválido.', field)
    return normalized


def _normalize_email(value, user_model):
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise WalkInClientError('INVALID_EMAIL', 'El email es inválido.', 'email')
    normalized = user_model.objects.normalize_email(value.strip())
    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise WalkInClientError(
            'INVALID_EMAIL',
            'El email es inválido.',
            'email',
        ) from exc
    return normalized


def _normalize_phone(value):
    if value in (None, ''):
        return '', None
    if not isinstance(value, str):
        raise WalkInClientError(
            'INVALID_PHONE',
            'El teléfono es inválido.',
            'telefono',
        )
    display = value.strip()
    if len(display) > Cliente._meta.get_field('numero').max_length:
        raise WalkInClientError(
            'INVALID_PHONE',
            'El teléfono es demasiado largo.',
            'telefono',
        )
    try:
        normalized = normalize_argentine_phone(display)
    except InvalidArgentinePhone as exc:
        raise WalkInClientError(
            'INVALID_PHONE',
            str(exc),
            'telefono',
        ) from exc
    return display, normalized


def _authorized_actor(actor, user_model):
    if not getattr(actor, 'is_authenticated', False) or actor.pk is None:
        raise WalkInClientPermissionDenied(
            'PERMISSION_DENIED',
            'Se requiere un actor autenticado.',
        )
    try:
        current = user_model.objects.get(pk=actor.pk)
    except user_model.DoesNotExist as exc:
        raise WalkInClientPermissionDenied(
            'PERMISSION_DENIED',
            'Se requiere un actor autenticado.',
        ) from exc
    if not current.is_active or not current.has_perm(
        BusinessPermission.CREATE_WALKIN_CLIENT
    ):
        raise WalkInClientPermissionDenied(
            'PERMISSION_DENIED',
            'No tiene permisos para realizar el alta rápida.',
        )
    return current


def _candidate_queryset(email, phone):
    query = Q()
    if email:
        query |= Q(usuario__email__iexact=email)
    if phone:
        query |= Q(numero_normalizado=phone)
    if not query:
        return Cliente.objects.none()
    return (
        Cliente.objects.select_related('usuario')
        .filter(query)
        .order_by('pk')
    )


def candidate_summary(cliente):
    user = cliente.usuario
    return {
        'cliente_id': cliente.pk,
        'display_name': user.get_full_name().strip() or 'Cliente sin nombre',
        'masked_email': mask_email(user.email),
        'masked_phone': mask_phone(cliente.numero_normalizado),
        'active': bool(user.is_active and cliente.activo),
        'web_access_status': user.web_access_status,
    }


def _result_from_operation(operation, *, recovered):
    cliente = operation.cliente
    user = cliente.usuario
    return WalkInClientResult(
        created=operation.result_created,
        recovered=recovered,
        cliente_id=cliente.pk,
        user_id=user.pk,
        display_name=user.get_full_name().strip() or 'Cliente sin nombre',
        masked_email=mask_email(user.email),
        masked_phone=mask_phone(cliente.numero_normalizado),
        client_active=cliente.activo,
        web_access_status=user.web_access_status,
        operation_id=str(operation.operation_id),
    )


def _fingerprint(payload):
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    )
    return _sha256(canonical)


@transaction.atomic
def create_walkin_client(
    *,
    actor,
    idempotency_key,
    first_name,
    last_name,
    reason,
    email=None,
    telefono=None,
    zona=None,
    medio_alta='PRESENCIAL',
    duplicate_resolution=None,
    candidate_client_id=None,
    reviewed_candidate_ids=None,
    duplicate_reason=None,
):
    user_model = get_user_model()
    current_actor = _authorized_actor(actor, user_model)
    if not isinstance(idempotency_key, str):
        raise WalkInClientError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
        )
    key = idempotency_key.strip()
    if not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise WalkInClientError(
            'INVALID_IDEMPOTENCY_KEY',
            'Debe informar una Idempotency-Key válida.',
        )
    if medio_alta != 'PRESENCIAL':
        raise WalkInClientError(
            'INVALID_MEDIUM',
            'El Incremento 1 sólo admite alta PRESENCIAL.',
            'medio_alta',
        )

    normalized_first = _normalize_required(first_name, 'first_name', 150)
    normalized_last = _normalize_required(last_name, 'last_name', 150)
    normalized_reason = _normalize_required(
        reason,
        'motivo',
        MAX_REASON_LENGTH,
    )
    if len(normalized_reason) < MIN_REASON_LENGTH:
        raise WalkInClientError('INVALID_REASON', 'El motivo es inválido.', 'motivo')
    normalized_email = _normalize_email(email, user_model)
    display_phone, normalized_phone = _normalize_phone(telefono)
    normalized_zone = _normalize_optional(zona, 'zona', 100)
    if normalized_email is None and normalized_phone is None:
        raise WalkInClientError(
            'CONTACT_REQUIRED',
            'Debe informar un email o teléfono válido.',
        )

    resolution = duplicate_resolution or ''
    if resolution not in ('', 'USE_EXISTING', 'CREATE_DISTINCT'):
        raise WalkInClientError(
            'INVALID_DUPLICATE_RESOLUTION',
            'La resolución de coincidencias es inválida.',
            'duplicate_resolution',
        )
    reviewed_ids = sorted(set(reviewed_candidate_ids or []))
    if any(not isinstance(value, int) or value <= 0 for value in reviewed_ids):
        raise WalkInClientError(
            'INVALID_DUPLICATE_RESOLUTION',
            'Los candidatos revisados son inválidos.',
            'reviewed_candidate_ids',
        )
    normalized_duplicate_reason = _normalize_optional(
        duplicate_reason,
        'duplicate_reason',
        500,
    )
    fingerprint = _fingerprint({
        'actor_id': current_actor.pk,
        'command': WalkInClientOperation.Command.CREATE,
        'first_name': normalized_first,
        'last_name': normalized_last,
        'email': normalized_email.casefold() if normalized_email else None,
        'phone': normalized_phone,
        'zone': normalized_zone,
        'reason': normalized_reason,
        'medium': medio_alta,
        'duplicate_resolution': resolution,
        'candidate_client_id': candidate_client_id,
        'reviewed_candidate_ids': reviewed_ids,
        'duplicate_reason': normalized_duplicate_reason,
    })
    key_digest = _sha256(key)
    _advisory_lock(
        f'walkin-key:{current_actor.pk}:{WalkInClientOperation.Command.CREATE}:{key_digest}'
    )
    existing_operation = (
        WalkInClientOperation.objects.select_related(
            'cliente__usuario'
        ).filter(
            actor=current_actor,
            command=WalkInClientOperation.Command.CREATE,
            idempotency_key_digest=key_digest,
        ).first()
    )
    if existing_operation is not None:
        if existing_operation.fingerprint != fingerprint:
            raise WalkInClientConflict(
                'IDEMPOTENCY_KEY_REUSED',
                'La Idempotency-Key ya fue utilizada con otro payload.',
            )
        return _result_from_operation(existing_operation, recovered=True)

    identity_locks = []
    if normalized_email:
        identity_locks.append(f'walkin-email:{normalized_email.casefold()}')
    if normalized_phone:
        identity_locks.append(f'walkin-phone:{normalized_phone}')
    for lock_value in sorted(identity_locks):
        _advisory_lock(lock_value)

    candidates = list(_candidate_queryset(normalized_email, normalized_phone))
    candidate_ids = [candidate.pk for candidate in candidates]
    summaries = [candidate_summary(candidate) for candidate in candidates]
    if candidates:
        if not resolution:
            raise WalkInClientConflict(
                'DUPLICATE_REVIEW_REQUIRED',
                'Debe revisar y resolver las coincidencias encontradas.',
                candidates=summaries,
            )
        if reviewed_ids != candidate_ids:
            raise WalkInClientConflict(
                'DUPLICATE_REVIEW_STALE',
                'La lista de coincidencias cambió; debe revisarla nuevamente.',
                candidates=summaries,
            )
        if resolution == 'USE_EXISTING':
            selected = next(
                (item for item in candidates if item.pk == candidate_client_id),
                None,
            )
            if selected is None:
                raise WalkInClientNotFound(
                    'CLIENT_OUT_OF_SCOPE',
                    'El Cliente seleccionado no está disponible en este alcance.',
                )
            operation = WalkInClientOperation.objects.create(
                actor=current_actor,
                idempotency_key_digest=key_digest,
                fingerprint=fingerprint,
                cliente=selected,
                result_created=False,
                duplicate_resolution=resolution,
                reviewed_candidate_ids=reviewed_ids,
            )
            Auditoria.objects.create(
                tabla=WALKIN_CLIENT_AUDIT_TABLE,
                registro_id=operation.pk,
                usuario=current_actor,
                accion='ALTA',
                valor_nuevo={
                    'event': WALKIN_CLIENT_EXISTING_SELECTED_EVENT,
                    'source': WALKIN_CLIENT_SOURCE,
                    'operation_id': str(operation.operation_id),
                    'actor_id': current_actor.pk,
                    'cliente_id': selected.pk,
                    'duplicate_resolution': resolution,
                    'reviewed_candidate_ids': reviewed_ids,
                    'idempotency_key_digest': key_digest,
                },
            )
            return _result_from_operation(operation, recovered=False)
        if normalized_email and any(
            item.usuario.email
            and item.usuario.email.casefold() == normalized_email.casefold()
            for item in candidates
        ):
            raise WalkInClientConflict(
                'EMAIL_ALREADY_EXISTS',
                'El email ya pertenece a otra identidad.',
                candidates=summaries,
            )
        if len(normalized_duplicate_reason) < MIN_REASON_LENGTH:
            raise WalkInClientError(
                'DUPLICATE_REASON_REQUIRED',
                'Debe justificar la creación de una persona distinta.',
                'duplicate_reason',
                summaries,
            )
    elif resolution or candidate_client_id or reviewed_ids or normalized_duplicate_reason:
        raise WalkInClientConflict(
            'DUPLICATE_REVIEW_STALE',
            'No existen coincidencias vigentes para resolver.',
        )

    user = user_model(
        email=normalized_email,
        first_name=normalized_first,
        last_name=normalized_last,
        is_active=True,
        is_staff=False,
        is_superuser=False,
        web_access_status=user_model.WebAccessStatus.PENDING_CLAIM,
    )
    user.set_unusable_password()
    try:
        with transaction.atomic():
            user.save(force_insert=True)
    except IntegrityError as exc:
        raise WalkInClientConflict(
            'IDENTITY_CONFLICT',
            'La identidad entra en conflicto con otra operación.',
        ) from exc

    try:
        cliente = Cliente.objects.create(
            usuario=user,
            numero=display_phone or None,
            numero_normalizado=normalized_phone,
            numero_normalizacion_estado=(
                Cliente.PhoneNormalizationStatus.VALID
                if normalized_phone
                else Cliente.PhoneNormalizationStatus.LEGACY_UNKNOWN
            ),
            zona=normalized_zone or None,
            activo=True,
        )
        assign_business_role(user, BusinessRole.CLIENTE)
        if get_business_roles(user) != (BusinessRole.CLIENTE,):
            raise WalkInClientConflict(
                'ROLE_ASSIGNMENT_CONFLICT',
                'No se pudo asignar el rol CLIENTE de forma consistente.',
            )
        operation = WalkInClientOperation.objects.create(
            actor=current_actor,
            idempotency_key_digest=key_digest,
            fingerprint=fingerprint,
            cliente=cliente,
            result_created=True,
            duplicate_resolution=resolution,
            reviewed_candidate_ids=reviewed_ids,
        )
        Auditoria.objects.create(
            tabla=WALKIN_CLIENT_AUDIT_TABLE,
            registro_id=operation.pk,
            usuario=current_actor,
            accion='ALTA',
            valor_nuevo={
                'event': WALKIN_CLIENT_CREATED_EVENT,
                'source': WALKIN_CLIENT_SOURCE,
                'operation_id': str(operation.operation_id),
                'actor_id': current_actor.pk,
                'user_id': user.pk,
                'cliente_id': cliente.pk,
                'has_email': normalized_email is not None,
                'email_fingerprint': (
                    _sha256(normalized_email.casefold())
                    if normalized_email else None
                ),
                'phone_fingerprint': (
                    _sha256(normalized_phone) if normalized_phone else None
                ),
                'web_access_status': user.web_access_status,
                'user_active': user.is_active,
                'client_active': cliente.activo,
                'business_role': BusinessRole.CLIENTE,
                'reason': normalized_reason,
                'medium': medio_alta,
                'duplicate_resolution': resolution or None,
                'reviewed_candidate_ids': reviewed_ids,
                'duplicate_reason': normalized_duplicate_reason or None,
                'idempotency_key_digest': key_digest,
                **build_business_role_audit_metadata(
                    previous_role=None,
                    new_role=BusinessRole.CLIENTE,
                ),
            },
        )
    except WalkInClientError:
        raise
    except Exception as exc:
        raise WalkInClientConflict(
            'WALKIN_CLIENT_CREATION_CONFLICT',
            'El alta no pudo completarse de forma atómica.',
        ) from exc
    return _result_from_operation(operation, recovered=False)
