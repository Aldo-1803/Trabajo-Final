from dataclasses import dataclass
import hashlib

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce

from usuarios.roles import BusinessPermission

from .models import Auditoria, MovimientoStock, Producto


STOCK_MOVEMENT_CREATED = 'STOCK_MOVEMENT_CREATED'


class StockError(Exception):
    default_code = 'STOCK_ERROR'

    def __init__(self, detail, *, code=None):
        self.code = code or self.default_code
        self.detail = detail
        super().__init__(detail)


class StockInvalid(StockError):
    default_code = 'INVALID_STOCK_COMMAND'


class StockConflict(StockError):
    default_code = 'STOCK_CONFLICT'


class StockNotFound(StockError):
    default_code = 'STOCK_TARGET_NOT_FOUND'


class StockPermissionDenied(StockError):
    default_code = 'STOCK_PERMISSION_DENIED'


@dataclass(frozen=True)
class StockReference:
    type: str = ''
    id: str = ''


@dataclass(frozen=True)
class StockDeltaCommand:
    product_id: int
    delta: int
    movement_type: str
    reason_code: str
    actor: object | None
    reference: StockReference
    idempotency_key: str
    note: str = ''
    reverses_movement_id: int | None = None


@dataclass(frozen=True)
class StockReconciliation:
    product_id: int
    projected_balance: int
    ledger_balance: int

    @property
    def reconciled(self):
        return self.projected_balance == self.ledger_balance


def _clean_text(value, *, field, max_length, required=False):
    value = '' if value is None else str(value).strip()
    if required and not value:
        raise StockInvalid(
            f'{field} es obligatorio.',
            code=f'{field.upper()}_REQUIRED',
        )
    if len(value) > max_length:
        raise StockInvalid(
            f'{field} supera {max_length} caracteres.',
            code=f'{field.upper()}_TOO_LONG',
        )
    return value


def _normalize_reference(reference):
    if reference is None:
        return StockReference()
    if isinstance(reference, StockReference):
        reference_type, reference_id = reference.type, reference.id
    elif isinstance(reference, dict):
        reference_type = reference.get('type', reference.get('reference_type'))
        reference_id = reference.get('id', reference.get('reference_id'))
    elif isinstance(reference, (tuple, list)) and len(reference) == 2:
        reference_type, reference_id = reference
    else:
        raise StockInvalid(
            'La referencia de inventario no es válida.',
            code='INVALID_STOCK_REFERENCE',
        )
    return StockReference(
        type=_clean_text(
            reference_type,
            field='reference_type',
            max_length=50,
        ),
        id=_clean_text(
            reference_id,
            field='reference_id',
            max_length=100,
        ),
    )


def _normalize_command(command):
    if isinstance(command, StockDeltaCommand):
        values = {
            'product_id': command.product_id,
            'delta': command.delta,
            'movement_type': command.movement_type,
            'reason_code': command.reason_code,
            'actor': command.actor,
            'reference': command.reference,
            'idempotency_key': command.idempotency_key,
            'note': command.note,
            'reverses_movement_id': command.reverses_movement_id,
        }
    elif isinstance(command, dict):
        values = command
    else:
        raise StockInvalid(
            'El command de inventario no es válido.',
            code='INVALID_STOCK_COMMAND',
        )

    try:
        product_id = int(values['product_id'])
        delta = int(values['delta'])
    except (KeyError, TypeError, ValueError):
        raise StockInvalid(
            'Producto y delta deben ser enteros válidos.',
            code='INVALID_STOCK_NUMBERS',
        )
    if isinstance(values.get('delta'), bool) or delta == 0:
        raise StockInvalid(
            'El delta debe ser distinto de cero.',
            code='ZERO_STOCK_DELTA',
        )
    movement_type = _clean_text(
        values.get('movement_type'),
        field='movement_type',
        max_length=24,
        required=True,
    )
    if movement_type not in MovimientoStock.Type.values:
        raise StockInvalid(
            'El tipo de movimiento no es válido.',
            code='INVALID_STOCK_MOVEMENT_TYPE',
        )
    if (
        movement_type in {
            MovimientoStock.Type.OPENING_BALANCE,
            MovimientoStock.Type.RECEIPT_IN,
        }
        and delta <= 0
    ):
        raise StockInvalid(
            'Este tipo de movimiento requiere un delta positivo.',
            code='INVALID_STOCK_DELTA_SIGN',
        )
    if movement_type == MovimientoStock.Type.ORDER_SALE_OUT and delta >= 0:
        raise StockInvalid(
            'Una salida por venta requiere un delta negativo.',
            code='INVALID_STOCK_DELTA_SIGN',
        )

    actor = values.get('actor')
    actor_id = getattr(actor, 'pk', None)
    if actor is not None and actor_id is None:
        raise StockInvalid(
            'El actor humano debe estar persistido.',
            code='INVALID_STOCK_ACTOR',
        )
    reverses_movement_id = values.get('reverses_movement_id')
    if reverses_movement_id is not None:
        try:
            reverses_movement_id = int(reverses_movement_id)
        except (TypeError, ValueError):
            raise StockInvalid(
                'El movimiento corregido no es válido.',
                code='INVALID_REVERSED_MOVEMENT',
            )
    if movement_type == MovimientoStock.Type.CORRECTION:
        if reverses_movement_id is None:
            raise StockInvalid(
                'Una corrección debe referenciar el movimiento original.',
                code='CORRECTION_TARGET_REQUIRED',
            )
    elif reverses_movement_id is not None:
        raise StockInvalid(
            'Sólo una corrección puede referenciar otro movimiento.',
            code='UNEXPECTED_CORRECTION_TARGET',
        )

    return StockDeltaCommand(
        product_id=product_id,
        delta=delta,
        movement_type=movement_type,
        reason_code=_clean_text(
            values.get('reason_code'),
            field='reason_code',
            max_length=50,
            required=True,
        ),
        actor=actor,
        reference=_normalize_reference(values.get('reference')),
        idempotency_key=_clean_text(
            values.get('idempotency_key'),
            field='idempotency_key',
            max_length=128,
            required=True,
        ),
        note=_clean_text(values.get('note'), field='note', max_length=500),
        reverses_movement_id=reverses_movement_id,
    )


def _movement_matches_command(movement, command):
    actor_id = getattr(command.actor, 'pk', None)
    actor_kind = (
        MovimientoStock.ActorKind.HUMAN
        if actor_id is not None
        else MovimientoStock.ActorKind.SYSTEM
    )
    return all((
        movement.producto_id == command.product_id,
        movement.delta == command.delta,
        movement.tipo == command.movement_type,
        movement.reason_code == command.reason_code,
        movement.nota == command.note,
        movement.actor_kind == actor_kind,
        movement.actor_id == actor_id,
        movement.reference_type == command.reference.type,
        movement.reference_id == command.reference.id,
        movement.reverses_movement_id == command.reverses_movement_id,
    ))


def _idempotent_or_conflict(movement, command):
    if _movement_matches_command(movement, command):
        return movement
    raise StockConflict(
        'La clave de idempotencia ya fue usada con otro payload.',
        code='STOCK_IDEMPOTENCY_KEY_REUSED',
    )


def _key_fingerprint(key):
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def _audit_movement(movement):
    Auditoria.objects.create(
        tabla=STOCK_MOVEMENT_CREATED,
        registro_id=movement.pk,
        usuario=movement.actor,
        accion='ALTA',
        valor_anterior=None,
        valor_nuevo={
            'event': STOCK_MOVEMENT_CREATED,
            'movement_id': movement.pk,
            'product_id': movement.producto_id,
            'delta': movement.delta,
            'movement_type': movement.tipo,
            'stock_before': movement.stock_before,
            'stock_after': movement.stock_after,
            'actor_kind': movement.actor_kind,
            'actor_id': movement.actor_id,
            'reason_code': movement.reason_code,
            'reference_type': movement.reference_type,
            'reference_id': movement.reference_id,
            'idempotency_key_sha256': _key_fingerprint(
                movement.idempotency_key
            ),
            'event_at': movement.created_at.isoformat(),
        },
    )


def _create_movement(*, command, stock_before, stock_after):
    actor_id = getattr(command.actor, 'pk', None)
    try:
        with transaction.atomic():
            return MovimientoStock.objects._create_from_inventory_service(
                producto_id=command.product_id,
                delta=command.delta,
                tipo=command.movement_type,
                reason_code=command.reason_code,
                nota=command.note,
                actor_kind=(
                    MovimientoStock.ActorKind.HUMAN
                    if actor_id is not None
                    else MovimientoStock.ActorKind.SYSTEM
                ),
                actor=command.actor,
                reference_type=command.reference.type,
                reference_id=command.reference.id,
                idempotency_key=command.idempotency_key,
                stock_before=stock_before,
                stock_after=stock_after,
                reverses_movement_id=command.reverses_movement_id,
            )
    except IntegrityError:
        existing = MovimientoStock.objects.filter(
            idempotency_key=command.idempotency_key
        ).first()
        if existing is not None:
            return _idempotent_or_conflict(existing, command)
        if command.reverses_movement_id is not None:
            if MovimientoStock.objects.filter(
                reverses_movement_id=command.reverses_movement_id
            ).exists():
                raise StockConflict(
                    'El movimiento ya tiene una corrección compensatoria.',
                    code='STOCK_MOVEMENT_ALREADY_CORRECTED',
                )
        raise


@transaction.atomic
def apply_stock_deltas(commands):
    """Bloquea Productos por PK ascendente y aplica el conjunto todo o nada."""
    normalized = [_normalize_command(command) for command in commands]
    if not normalized:
        return []
    keys = [command.idempotency_key for command in normalized]
    if len(keys) != len(set(keys)):
        raise StockInvalid(
            'Una operación múltiple no puede repetir claves de idempotencia.',
            code='DUPLICATE_STOCK_COMMAND_KEY',
        )

    product_ids = sorted({command.product_id for command in normalized})
    locked_products = list(
        Producto.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by('pk')
    )
    products = {product.pk: product for product in locked_products}
    missing = [product_id for product_id in product_ids if product_id not in products]
    if missing:
        raise StockNotFound(
            f'No existe el Producto {missing[0]}.',
            code='PRODUCT_NOT_FOUND',
        )

    existing_by_key = {
        movement.idempotency_key: movement
        for movement in MovimientoStock.objects.filter(idempotency_key__in=keys)
    }
    results = [None] * len(normalized)
    pending = []
    balances = {
        product_id: product.stock_real
        for product_id, product in products.items()
    }

    reverse_ids = {
        command.reverses_movement_id
        for command in normalized
        if command.reverses_movement_id is not None
    }
    reversed_movements = {
        movement.pk: movement
        for movement in MovimientoStock.objects.filter(pk__in=reverse_ids)
    }

    for index, command in enumerate(normalized):
        existing = existing_by_key.get(command.idempotency_key)
        if existing is not None:
            results[index] = _idempotent_or_conflict(existing, command)
            continue
        if command.reverses_movement_id is not None:
            original = reversed_movements.get(command.reverses_movement_id)
            if original is None:
                raise StockNotFound(
                    'No existe el movimiento a corregir.',
                    code='STOCK_MOVEMENT_NOT_FOUND',
                )
            if original.producto_id != command.product_id:
                raise StockInvalid(
                    'La corrección no pertenece al mismo Producto.',
                    code='CORRECTION_PRODUCT_MISMATCH',
                )
            if MovimientoStock.objects.filter(
                reverses_movement_id=original.pk
            ).exists():
                raise StockConflict(
                    'El movimiento ya tiene una corrección compensatoria.',
                    code='STOCK_MOVEMENT_ALREADY_CORRECTED',
                )
        stock_before = balances[command.product_id]
        stock_after = stock_before + command.delta
        if stock_after < 0:
            raise StockConflict(
                'El movimiento dejaría el stock físico en negativo.',
                code='INSUFFICIENT_REAL_STOCK',
            )
        balances[command.product_id] = stock_after
        pending.append((index, command, stock_before, stock_after))

    for index, command, stock_before, stock_after in pending:
        movement = _create_movement(
            command=command,
            stock_before=stock_before,
            stock_after=stock_after,
        )
        results[index] = movement
        _audit_movement(movement)

    for product_id in product_ids:
        if balances[product_id] == products[product_id].stock_real:
            continue
        models.QuerySet.update(
            Producto.objects.filter(pk=product_id),
            stock_real=balances[product_id],
        )
        products[product_id].stock_real = balances[product_id]

    return results


def apply_stock_delta(
    product_id,
    delta,
    movement_type,
    reason_code,
    actor,
    reference,
    idempotency_key,
    note=None,
    *,
    reverses_movement_id=None,
):
    return apply_stock_deltas([{
        'product_id': product_id,
        'delta': delta,
        'movement_type': movement_type,
        'reason_code': reason_code,
        'actor': actor,
        'reference': reference,
        'idempotency_key': idempotency_key,
        'note': note,
        'reverses_movement_id': reverses_movement_id,
    }])[0]


def _require_manage_stock(actor):
    if not (
        getattr(actor, 'is_authenticated', False)
        and getattr(actor, 'is_active', False)
        and actor.has_perm(BusinessPermission.MANAGE_STOCK)
    ):
        raise StockPermissionDenied(
            'No tiene permisos para gestionar stock.',
        )


def receive_stock(
    *,
    product_id,
    quantity,
    reason_code,
    actor,
    idempotency_key,
    note=None,
):
    _require_manage_stock(actor)
    if isinstance(quantity, bool):
        raise StockInvalid(
            'La cantidad debe ser un entero positivo.',
            code='INVALID_RECEIPT_QUANTITY',
        )
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise StockInvalid(
            'La cantidad debe ser un entero positivo.',
            code='INVALID_RECEIPT_QUANTITY',
        )
    if quantity <= 0:
        raise StockInvalid(
            'La cantidad debe ser mayor que cero.',
            code='INVALID_RECEIPT_QUANTITY',
        )
    return apply_stock_delta(
        product_id=product_id,
        delta=quantity,
        movement_type=MovimientoStock.Type.RECEIPT_IN,
        reason_code=reason_code,
        actor=actor,
        reference=None,
        idempotency_key=idempotency_key,
        note=note,
    )


def adjust_stock(
    *,
    product_id,
    delta,
    reason_code,
    actor,
    idempotency_key,
    note=None,
):
    _require_manage_stock(actor)
    return apply_stock_delta(
        product_id=product_id,
        delta=delta,
        movement_type=MovimientoStock.Type.MANUAL_ADJUSTMENT,
        reason_code=reason_code,
        actor=actor,
        reference=None,
        idempotency_key=idempotency_key,
        note=note,
    )


def correct_stock_movement(
    *,
    movement_id,
    reason_code,
    actor,
    idempotency_key,
    note=None,
):
    _require_manage_stock(actor)
    try:
        original = MovimientoStock.objects.get(pk=movement_id)
    except MovimientoStock.DoesNotExist:
        raise StockNotFound(
            'No existe el movimiento a corregir.',
            code='STOCK_MOVEMENT_NOT_FOUND',
        )
    return apply_stock_delta(
        product_id=original.producto_id,
        delta=-original.delta,
        movement_type=MovimientoStock.Type.CORRECTION,
        reason_code=reason_code,
        actor=actor,
        reference=StockReference('STOCK_MOVEMENT', str(original.pk)),
        idempotency_key=idempotency_key,
        note=note,
        reverses_movement_id=original.pk,
    )


def reconcile_product_stock(product_id):
    try:
        product = Producto.objects.only('pk', 'stock_real').get(pk=product_id)
    except Producto.DoesNotExist:
        raise StockNotFound(
            f'No existe el Producto {product_id}.',
            code='PRODUCT_NOT_FOUND',
        )
    ledger_balance = MovimientoStock.objects.filter(
        producto_id=product_id
    ).aggregate(total=Coalesce(Sum('delta'), 0))['total']
    return StockReconciliation(
        product_id=product.pk,
        projected_balance=product.stock_real,
        ledger_balance=ledger_balance,
    )
