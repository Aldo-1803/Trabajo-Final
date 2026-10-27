from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .inventory_services import StockReference, apply_stock_deltas
from .models import (
    CompromisoStock,
    MovimientoStock,
    OrdenCompra,
    OrdenItem,
    OrdenPendiente,
    Producto,
)


ORDER_INVENTORY_REASON = 'ORDER_FULFILLMENT'
ORDER_COMMITMENT_REASON = 'ORDER_RESERVATION'
ORDER_INVENTORY_VERSION = 'v1'


class OrderInventoryError(Exception):
    default_code = 'ORDER_INVENTORY_ERROR'

    def __init__(self, detail, *, code=None):
        self.code = code or self.default_code
        self.detail = detail
        super().__init__(detail)


class OrderInventoryInvalid(OrderInventoryError):
    default_code = 'INVALID_ORDER_INVENTORY'


class OrderInventoryConflict(OrderInventoryError):
    default_code = 'ORDER_INVENTORY_CONFLICT'


class OrderInventoryNotFound(OrderInventoryError):
    default_code = 'ORDER_NOT_FOUND'


@dataclass(frozen=True)
class OrderInventoryEffectResult:
    order: OrdenCompra
    commitments: tuple
    movements: tuple
    applied: bool


def _commitment_key(order_id, product_id):
    return f'order:{order_id}:commitment:{ORDER_INVENTORY_VERSION}:product:{product_id}'


def _movement_key(order_id, product_id):
    return f'order:{order_id}:inventory:{ORDER_INVENTORY_VERSION}:product:{product_id}'


def _lock_order(order_id):
    try:
        return OrdenCompra.objects.select_for_update().get(pk=order_id)
    except OrdenCompra.DoesNotExist:
        raise OrderInventoryNotFound('La OrdenCompra no existe.')


def _consolidated_items(order):
    rows = list(
        order.items.values('producto_id')
        .annotate(cantidad=Sum('cantidad'))
        .order_by('producto_id')
    )
    if not rows:
        raise OrderInventoryInvalid(
            'La OrdenCompra no tiene items.',
            code='ORDER_WITHOUT_ITEMS',
        )
    quantities = {}
    for row in rows:
        quantity = row['cantidad']
        if quantity is None or quantity <= 0:
            raise OrderInventoryInvalid(
                'Las cantidades de la OrdenCompra deben ser positivas.',
                code='INVALID_ORDER_ITEM_QUANTITY',
            )
        quantities[row['producto_id']] = quantity
    return quantities


def _lock_products(product_ids):
    locked = list(
        Producto.objects.select_for_update()
        .filter(pk__in=sorted(product_ids))
        .order_by('pk')
    )
    products = {product.pk: product for product in locked}
    missing = [product_id for product_id in sorted(product_ids) if product_id not in products]
    if missing:
        raise OrderInventoryNotFound(
            f'No existe el Producto {missing[0]}.',
            code='ORDER_PRODUCT_NOT_FOUND',
        )
    return products


def _lock_commitments(order_id):
    return list(
        CompromisoStock.objects.select_for_update()
        .filter(orden_id=order_id)
        .order_by('pk')
    )


def _active_totals(product_ids):
    return {
        row['producto_id']: row['total']
        for row in (
            CompromisoStock.objects.filter(
                producto_id__in=product_ids,
                estado=CompromisoStock.State.ACTIVE,
            )
            .values('producto_id')
            .annotate(total=Coalesce(Sum('cantidad'), 0))
        )
    }


def _assert_projection(products):
    totals = _active_totals(products)
    for product_id, product in products.items():
        active_total = totals.get(product_id, 0)
        if product.stock_comprometido != active_total:
            raise OrderInventoryConflict(
                (
                    f'La proyección comprometida del Producto {product_id} '
                    'no coincide con sus compromisos activos.'
                ),
                code='ORDER_COMMITMENT_PROJECTION_MISMATCH',
            )


def _validate_existing_commitments(order, quantities, commitments):
    by_product = {commitment.producto_id: commitment for commitment in commitments}
    if set(by_product) != set(quantities):
        raise OrderInventoryConflict(
            'Los compromisos existentes no coinciden con los items de la orden.',
            code='ORDER_COMMITMENT_SET_MISMATCH',
        )
    for product_id, quantity in quantities.items():
        commitment = by_product[product_id]
        if (
            commitment.cantidad != quantity
            or commitment.idempotency_key != _commitment_key(order.pk, product_id)
        ):
            raise OrderInventoryConflict(
                'Un compromiso existente no coincide con la orden.',
                code='ORDER_COMMITMENT_PAYLOAD_MISMATCH',
            )
    return by_product


def _create_commitments_locked(order, quantities, products):
    _assert_projection(products)
    for product_id, quantity in quantities.items():
        product = products[product_id]
        available = product.stock_real - product.stock_comprometido
        if available < quantity:
            raise OrderInventoryConflict(
                (
                    f'Stock insuficiente para {product.nombre}. '
                    f'Disponible: {available}, solicitado: {quantity}.'
                ),
                code='INSUFFICIENT_AVAILABLE_STOCK',
            )

    commitments = []
    for product_id, quantity in quantities.items():
        commitments.append(
            CompromisoStock.objects._create_from_order_service(
                producto_id=product_id,
                orden_id=order.pk,
                cantidad=quantity,
                estado=CompromisoStock.State.ACTIVE,
                idempotency_key=_commitment_key(order.pk, product_id),
                reason_code=ORDER_COMMITMENT_REASON,
                metadata={'source': 'OrdenCompra'},
            )
        )
        product = products[product_id]
        new_committed = product.stock_comprometido + quantity
        models.QuerySet.update(
            Producto.objects.filter(pk=product_id),
            stock_comprometido=new_committed,
        )
        product.stock_comprometido = new_committed
    return commitments


@transaction.atomic
def create_order_stock_commitments(order_id):
    """Crea reservas todo-o-nada; un retry nunca reabre una reserva terminal."""
    order = _lock_order(order_id)
    if order.estado in {'COMPLETADO', 'CANCELADO', 'RECHAZADO'}:
        raise OrderInventoryConflict(
            'La orden está en un estado terminal y no puede reservar stock.',
            code='ORDER_TERMINAL_FOR_COMMITMENT',
        )
    quantities = _consolidated_items(order)
    products = _lock_products(quantities)
    commitments = _lock_commitments(order.pk)
    if commitments:
        _validate_existing_commitments(order, quantities, commitments)
        _assert_projection(products)
        return commitments
    return _create_commitments_locked(order, quantities, products)


def _set_product_commitment_projection(product, value):
    if value < 0 or value > product.stock_real:
        raise OrderInventoryConflict(
            'La transición dejaría una proyección de compromiso inválida.',
            code='INVALID_ORDER_COMMITMENT_PROJECTION',
        )
    models.QuerySet.update(
        Producto.objects.filter(pk=product.pk),
        stock_comprometido=value,
    )
    product.stock_comprometido = value


@transaction.atomic
def apply_order_inventory_effect(order_id):
    """Aplica una única salida física por Producto lógico de OrdenCompra."""
    order = _lock_order(order_id)
    quantities = _consolidated_items(order)
    products = _lock_products(quantities)
    commitments = _lock_commitments(order.pk)
    keys = [_movement_key(order.pk, product_id) for product_id in quantities]
    locked_movements = list(
        MovimientoStock.objects.select_for_update()
        .filter(idempotency_key__in=keys)
        .order_by('pk')
    )

    if commitments:
        _validate_existing_commitments(order, quantities, commitments)
    else:
        if order.estado in {'CANCELADO', 'RECHAZADO'}:
            raise OrderInventoryConflict(
                'Una orden cancelada o rechazada no puede consumir inventario.',
                code='ORDER_TERMINAL_FOR_INVENTORY',
            )
        commitments = _create_commitments_locked(order, quantities, products)

    states = {commitment.estado for commitment in commitments}
    if states == {CompromisoStock.State.RELEASED}:
        raise OrderInventoryConflict(
            'Los compromisos de la orden ya fueron liberados.',
            code='ORDER_COMMITMENTS_RELEASED',
        )
    if len(states) != 1:
        raise OrderInventoryConflict(
            'Los compromisos de la orden tienen estados incompatibles.',
            code='ORDER_COMMITMENT_STATE_MISMATCH',
        )

    existing_by_key = {
        movement.idempotency_key: movement for movement in locked_movements
    }
    _assert_projection(products)
    commands = [
        {
            'product_id': product_id,
            'delta': -quantity,
            'movement_type': MovimientoStock.Type.ORDER_SALE_OUT,
            'reason_code': ORDER_INVENTORY_REASON,
            'actor': None,
            'reference': StockReference('ORDEN_COMPRA', str(order.pk)),
            'idempotency_key': _movement_key(order.pk, product_id),
            'note': f'Salida física por OrdenCompra {order.codigo}.',
        }
        for product_id, quantity in quantities.items()
    ]
    if states == {CompromisoStock.State.CONSUMED}:
        if set(existing_by_key) != set(keys):
            raise OrderInventoryConflict(
                'Hay compromisos consumidos sin su movimiento físico.',
                code='CONSUMED_COMMITMENT_WITHOUT_MOVEMENT',
            )
        if order.estado != 'COMPLETADO':
            OrdenCompra.objects.filter(pk=order.pk).update(estado='COMPLETADO')
            order.estado = 'COMPLETADO'
        ordered = tuple(apply_stock_deltas(commands))
        return OrderInventoryEffectResult(
            order=order,
            commitments=tuple(commitments),
            movements=ordered,
            applied=False,
        )

    if order.estado in {'CANCELADO', 'RECHAZADO'}:
        raise OrderInventoryConflict(
            'Una orden cancelada o rechazada no puede consumir inventario.',
            code='ORDER_TERMINAL_FOR_INVENTORY',
        )

    for product_id, quantity in quantities.items():
        product = products[product_id]
        _set_product_commitment_projection(
            product,
            product.stock_comprometido - quantity,
        )

    movements = tuple(apply_stock_deltas(commands))
    now = timezone.now()
    commitment_ids = [commitment.pk for commitment in commitments]
    CompromisoStock.objects._transition_from_order_service(
        commitment_ids=commitment_ids,
        estado=CompromisoStock.State.CONSUMED,
        consumed_at=now,
        released_at=None,
    )
    for commitment in commitments:
        commitment.estado = CompromisoStock.State.CONSUMED
        commitment.consumed_at = now
        commitment.released_at = None

    OrdenCompra.objects.filter(pk=order.pk).update(estado='COMPLETADO')
    order.estado = 'COMPLETADO'
    return OrderInventoryEffectResult(
        order=order,
        commitments=tuple(commitments),
        movements=movements,
        applied=not bool(existing_by_key),
    )


@transaction.atomic
def release_order_stock_commitments(order_id, *, final_state='CANCELADO'):
    if final_state not in {'CANCELADO', 'RECHAZADO'}:
        raise OrderInventoryInvalid(
            'El estado final de liberación no es válido.',
            code='INVALID_RELEASE_ORDER_STATE',
        )
    order = _lock_order(order_id)
    quantities = _consolidated_items(order)
    products = _lock_products(quantities)
    commitments = _lock_commitments(order.pk)
    if not commitments:
        if order.estado == 'COMPLETADO':
            raise OrderInventoryConflict(
                'Una orden completada no puede liberar inventario.',
                code='COMPLETED_ORDER_CANNOT_RELEASE',
            )
        OrdenCompra.objects.filter(pk=order.pk).update(estado=final_state)
        order.estado = final_state
        return []

    _validate_existing_commitments(order, quantities, commitments)
    states = {commitment.estado for commitment in commitments}
    if states == {CompromisoStock.State.CONSUMED}:
        raise OrderInventoryConflict(
            'Los compromisos consumidos no pueden liberarse.',
            code='CONSUMED_COMMITMENTS_CANNOT_RELEASE',
        )
    if states == {CompromisoStock.State.RELEASED}:
        _assert_projection(products)
        if order.estado != final_state:
            OrdenCompra.objects.filter(pk=order.pk).update(estado=final_state)
            order.estado = final_state
        return commitments
    if states != {CompromisoStock.State.ACTIVE}:
        raise OrderInventoryConflict(
            'Los compromisos de la orden tienen estados incompatibles.',
            code='ORDER_COMMITMENT_STATE_MISMATCH',
        )

    _assert_projection(products)
    for product_id, quantity in quantities.items():
        product = products[product_id]
        _set_product_commitment_projection(
            product,
            product.stock_comprometido - quantity,
        )
    now = timezone.now()
    CompromisoStock.objects._transition_from_order_service(
        commitment_ids=[commitment.pk for commitment in commitments],
        estado=CompromisoStock.State.RELEASED,
        consumed_at=None,
        released_at=now,
    )
    for commitment in commitments:
        commitment.estado = CompromisoStock.State.RELEASED
        commitment.released_at = now
        commitment.consumed_at = None
    OrdenCompra.objects.filter(pk=order.pk).update(estado=final_state)
    order.estado = final_state
    return commitments


def _pending_item_values(pending_order):
    values = []
    for raw in pending_order.items_json or []:
        try:
            product_id = int(raw['producto_id'])
            quantity = int(raw['cantidad'])
            price = Decimal(str(raw['precio']))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise OrderInventoryInvalid(
                'Los items de OrdenPendiente no tienen un formato válido.',
                code='INVALID_PENDING_ORDER_ITEMS',
            )
        if quantity <= 0 or price < 0:
            raise OrderInventoryInvalid(
                'Cantidad y precio de OrdenPendiente no son válidos.',
                code='INVALID_PENDING_ORDER_ITEMS',
            )
        values.append((product_id, quantity, price))
    if not values:
        raise OrderInventoryInvalid(
            'La OrdenPendiente no tiene items.',
            code='PENDING_ORDER_WITHOUT_ITEMS',
        )
    return values


def _ensure_pending_bridge_locked(pending_order):
    if pending_order.orden_compra_id:
        return pending_order.orden_compra_id
    if pending_order.cliente_id is None:
        raise OrderInventoryInvalid(
            'La OrdenPendiente no tiene Cliente asociado.',
            code='PENDING_ORDER_WITHOUT_CLIENT',
        )
    values = _pending_item_values(pending_order)
    order = OrdenCompra.objects.create(
        codigo=f'OP{pending_order.pk}',
        cliente_id=pending_order.cliente_id,
        estado='PENDIENTE',
        total=pending_order.monto_total,
        notas='Compatibilidad canónica de OrdenPendiente legacy.',
    )
    for product_id, quantity, price in values:
        OrdenItem.objects.create(
            orden=order,
            producto_id=product_id,
            cantidad=quantity,
            precio_historico=price,
        )
    OrdenPendiente.objects.filter(pk=pending_order.pk).update(orden_compra=order)
    pending_order.orden_compra_id = order.pk
    create_order_stock_commitments(order.pk)
    return order.pk


@transaction.atomic
def apply_pending_order_inventory_effect(pending_order_id):
    try:
        pending_order = (
            OrdenPendiente.objects.select_for_update()
            .get(pk=pending_order_id)
        )
    except OrdenPendiente.DoesNotExist:
        raise OrderInventoryNotFound(
            'La OrdenPendiente no existe.',
            code='PENDING_ORDER_NOT_FOUND',
        )
    if pending_order.estado == 'CANCELADA':
        raise OrderInventoryConflict(
            'Una OrdenPendiente cancelada no puede consumir inventario.',
            code='PENDING_ORDER_CANCELLED',
        )
    if pending_order.estado == 'COMPLETADA' and not pending_order.orden_compra_id:
        raise OrderInventoryConflict(
            'La OrdenPendiente legacy ya estaba completada sin efecto trazable.',
            code='LEGACY_PENDING_ORDER_ALREADY_COMPLETED',
        )
    order_id = _ensure_pending_bridge_locked(pending_order)
    result = apply_order_inventory_effect(order_id)
    completed_at = pending_order.fecha_completacion or timezone.now()
    OrdenPendiente.objects.filter(pk=pending_order.pk).update(
        estado='COMPLETADA',
        fecha_completacion=completed_at,
    )
    pending_order.estado = 'COMPLETADA'
    pending_order.fecha_completacion = completed_at
    return pending_order, result


@transaction.atomic
def release_pending_order_stock_commitments(pending_order_id):
    try:
        pending_order = OrdenPendiente.objects.select_for_update().get(
            pk=pending_order_id
        )
    except OrdenPendiente.DoesNotExist:
        raise OrderInventoryNotFound(
            'La OrdenPendiente no existe.',
            code='PENDING_ORDER_NOT_FOUND',
        )
    if pending_order.estado == 'COMPLETADA':
        raise OrderInventoryConflict(
            'Una OrdenPendiente completada no puede liberar inventario.',
            code='COMPLETED_PENDING_ORDER_CANNOT_RELEASE',
        )
    if pending_order.orden_compra_id:
        release_order_stock_commitments(
            pending_order.orden_compra_id,
            final_state='CANCELADO',
        )
    OrdenPendiente.objects.filter(pk=pending_order.pk).update(estado='CANCELADA')
    pending_order.estado = 'CANCELADA'
    return pending_order
