# Implementación BH-058 D1 — MovimientoStock y autoridad de inventario

Fecha de validación: 2026-10-26.

## Alcance cerrado

Este incremento implementa únicamente la autoridad física de inventario:

- `MovimientoStock` es el ledger inmutable y autoritativo;
- `Producto.stock_real` es una proyección materializada escrita por commands de
  inventario;
- se incorporan recepción, ajuste, corrección compensatoria y consulta de
  movimientos;
- se separan `gestion.view_stock` y `gestion.manage_stock`;
- el catálogo público conserva sólo disponibilidad comercial booleana.

No se implementaron D2, efectos nuevos de `OrdenCompra`/`OrdenPendiente`,
`CompromisoStock`, integraciones de Mercado Pago, booking, consumo por Servicio,
devoluciones, proveedores, promociones ni BH-059.

## Autoridad e invariantes

La igualdad verificable es:

```text
Producto.stock_real = SUM(MovimientoStock.delta por producto)
```

`MovimientoStock` registra:

- Producto, delta no nulo y tipo semántico;
- razón estructurada y nota opcional;
- actor `HUMAN` con usuario obligatorio o `SYSTEM` sin usuario;
- referencia de origen;
- clave de idempotencia única;
- snapshots `stock_before` y `stock_after` coherentes con el delta;
- referencia al movimiento compensado cuando el tipo es `CORRECTION`.

El modelo rechaza `save()` sobre filas existentes, `delete()`, `QuerySet.update`,
`QuerySet.delete`, `bulk_update`, `bulk_create`, `update_or_create` y creación
directa fuera del manager interno del servicio. La base agrega constraints para
delta, saldos, actor, razón, idempotencia, signos fijos y coherencia de
corrección.

`Producto.stock_real` y `Producto.stock_minimo` tienen constraints nombrados
`>= 0`. `stock_disponible` se calcula exactamente como
`stock_real - stock_comprometido`, sin clamp que oculte inconsistencias legacy.

`ORDER_SALE_OUT` existe como choice reservado, pero D1 no habilita ningún writer
de ventas.

## Commands y concurrencia

`gestion/inventory_services.py` expone:

- `apply_stock_delta`;
- `apply_stock_deltas`;
- `receive_stock`;
- `adjust_stock`;
- `correct_stock_movement`;
- `reconcile_product_stock`.

Todas las mutaciones son atómicas. Los Productos afectados se bloquean con
`select_for_update()` en PK ascendente; una operación múltiple valida el conjunto
antes de persistir y falla completa si algún saldo quedaría negativo.

La idempotencia devuelve el mismo movimiento cuando key y payload coinciden, y
responde conflicto cuando una key se reutiliza con otro payload. Cada movimiento
produce exactamente una auditoría semántica `STOCK_MOVEMENT_CREATED`; la key se
registra sólo como fingerprint SHA-256.

Una corrección crea el delta opuesto y nunca modifica la fila original. D1 admite
una sola corrección compensatoria completa por movimiento; un segundo intento con
otra key produce `STOCK_MOVEMENT_ALREADY_CORRECTED`.

## API semántica

- `POST /api/gestion/productos/{id}/stock/receive/`
- `POST /api/gestion/productos/{id}/stock/adjust/`
- `GET /api/gestion/productos/{id}/stock-movements/`
- `GET /api/gestion/stock-movements/`
- `POST /api/gestion/stock-movements/{id}/correct/`

El listado global es paginado y filtra por `producto`, `tipo`, `actor`,
`reference_type`, `reference_id`, `fecha_desde` y `fecha_hasta`. El viewset no
expone create, update, partial update ni delete genéricos del ledger.

## Permisos y privacidad

- cantidades, mínimos, alertas y movimientos requieren
  `gestion.view_stock`;
- recepción, ajuste y corrección requieren `gestion.manage_stock`;
- backend y servicios usan `user.has_perm(...)`;
- `is_staff`, rol textual y skills no autorizan commands de stock;
- `manage_stock` no implica lectura del ledger ni gestión de catálogo/precios;
- el permiso individual funciona sin `is_staff`.

El serializer público de Producto retira `stock_real`, `stock_comprometido`,
`stock_minimo`, `stock_disponible` y `necesita_reposicion` cuando falta
`view_stock`; conserva únicamente `available`. El cliente web ya no calcula ni
muestra unidades internas. `stock_real`, `stock_comprometido` y, temporalmente,
`stock_minimo` son read-only en serializer y admin; la pantalla de Producto dejó
de enviarlos en altas o ediciones.

## Migración 0032

`0032_movimientostock_inventory_authority.py`:

1. crea el ledger, índices y constraints;
2. falla explícitamente si encuentra `stock_minimo < 0` y lista IDs afectados;
3. advierte si `stock_comprometido > stock_real`, sin corregir ni ocultar esa
   deuda de D2;
4. crea un único `OPENING_BALANCE` determinista sólo para cada saldo legacy
   estrictamente positivo;
5. no crea openings de cero ni inventa historial de compras/ventas;
6. agrega los constraints no negativos de Producto.

La migración está aplicada en la base auditada. Esa base no contenía Productos,
por lo que no generó openings artificiales.

## Frontera D2 preservada

La búsqueda final conserva exactamente cinco asignaciones legacy directas de
`stock_real`, todas en flujos de órdenes existentes de `gestion/views.py`:

1. webhook Mercado Pago de `OrdenCompra`;
2. `OrdenPendiente.confirmar_pago`;
3. `OrdenPendiente.confirmar_entrega`, rama de items relacionados;
4. `OrdenPendiente.confirmar_entrega`, rama legacy `items_json`;
5. `OrdenCompra.confirmar_entrega`.

No se migraron deliberadamente porque requieren idempotencia de orden,
`CompromisoStock`, locks y semántica de venta definidos por D2. Los writers
genéricos de serializer, admin y frontend sí quedaron cerrados en D1.

## Validación ejecutada

- 20 pruebas D1 de modelo, servicios, API, permisos, privacidad, idempotencia,
  corrección, auditoría y reconciliación: OK.
- 6 carreras `TransactionTestCase` sobre PostgreSQL real: OK.
- regresión A1–B3: 113 pruebas: OK.
- roles y `/me/`: 31 pruebas: OK.
- regresión BH-057: 368 de 369 pruebas OK. El único error restante se reproduce
  aislado y es previo a D1: borrar cualquier Usuario activa `SET_NULL` sobre
  `PaymentReconciliationCase.created_by`, pero su manager inmutable prohíbe el
  `QuerySet.update()` usado por el collector de Django.
- `python manage.py check`: OK.
- `python manage.py makemigrations --check --dry-run`: sin cambios.
- `python -m compileall gestion usuarios`: OK.
- `git diff --check`: OK; sólo advertencias de normalización CRLF/LF.
- `npm run build`: compilación correcta, con warnings legacy ajenos a D1.
- frontend: 21 suites y 174 assertions pasan; la suite global conserva un fallo
  legacy en `src/App.test.js` al resolver `react-router-dom`.

Los dos fallos globales documentados no afectan el contrato ni las pruebas de
BH-058 D1 y no se corrigieron para evitar ampliar el alcance.

BH-058 D1 = VALIDADO
