# BH-058 F1 — Bloqueo de entregas no autorizadas o impagas

Fecha de validación: 2026-10-29.

## Resultado

Se cerró el hallazgo P0 por el cual un Cliente podía confirmar la entrega de su
propia `OrdenCompra`, aun sin pago, y provocar la salida física de stock.

La autoridad resultante es:

```text
actor autenticado, activo y con gestion.manage_stock
                         +
OrdenCompra bloqueada en estado PAGADO
                         +
CompromisoStock ACTIVE, completo y coherente
                         ↓
un único MovimientoStock ORDER_SALE_OUT
                         +
OrdenCompra COMPLETADO / CompromisoStock CONSUMED
```

`COMPLETADO` sólo es aceptado como reintento idempotente cuando ya existen todos
los compromisos `CONSUMED` y todos los movimientos determinísticos. No permite
iniciar un efecto físico nuevo.

## Diagnóstico

La ruta indebida principal era:

```text
POST /api/gestion/ordenes-compra/{id}/confirmar_entrega/
```

`OrdenCompraViewSet` usaba únicamente `IsAuthenticated`. Su queryset permitía
al Cliente obtener su propia orden y la acción llamaba directamente a
`apply_order_inventory_effect(order_id)`. El servicio aceptaba estados no
terminales como `PENDIENTE` o `ESPERANDO_PAGO`, creaba compromisos si faltaban y
aplicaba la salida física sin comprobar autoridad ni acreditación.

La prueba D2 previa reproducía y aceptaba ese comportamiento: autenticaba al
Cliente, finalizaba su carrito y confirmaba la entrega sin llevar antes la orden
a `PAGADO`.

También se localizaron dos rutas legacy equivalentes que alcanzaban el mismo
efecto mediante `apply_pending_order_inventory_effect`:

```text
POST /api/gestion/ordenes-pendientes/{id}/confirmar_pago/
POST /api/gestion/ordenes-pendientes/{id}/confirmar_entrega/
```

Ambas quedaron cerradas con el mismo permiso y la misma precondición canónica.
`confirmar_pago` no puede usar una afirmación legacy como sustituto de la
conciliación que lleva la `OrdenCompra` a `PAGADO`.

## Corrección

### Autorización efectiva

Las tres acciones físicas requieren ahora:

```python
permission_classes=[IsAuthenticated, CanManageStock]
```

`CanManageStock` evalúa `user.has_perm('gestion.manage_stock')`. No se usa
`is_staff`, nombre de rol ni `Personal.rol`.

Los querysets de `OrdenCompra` y `OrdenPendiente` permiten visibilidad global al
actor con ese permiso efectivo. Un `is_staff` sin el permiso no obtiene
autoridad implícita.

La misma comprobación existe dentro del servicio de dominio. Tanto
`apply_order_inventory_effect` como `apply_pending_order_inventory_effect`
requieren el `actor`; si no está autenticado, activo o no posee
`gestion.manage_stock`, rechazan la operación. Esto evita que una ruta futura
pueda omitir la política DRF.

### Precondición financiera e inventario

La primera entrega sólo puede iniciarse desde `OrdenCompra.estado == 'PAGADO'`,
estado que C2b asigna después de acreditar y conciliar el `Pago`. Recibir un
webhook, crear un checkout o quedar en `VERIFIED` no satisface esta condición.

El servicio exige además:

- compromisos de stock ya existentes;
- correspondencia exacta entre items y compromisos;
- todos los compromisos en `ACTIVE` para una primera entrega;
- proyección `stock_comprometido` consistente;
- ausencia de movimientos previos incompatibles.

No se crean compromisos just-in-time durante una entrega. C2b ya exige que la
orden conserve compromisos activos antes de llevarla a `PAGADO`.

### Transacción, locks e idempotencia

La validación comercial se ejecuta dentro de `transaction.atomic()` después de
obtener `SELECT ... FOR UPDATE` sobre la `OrdenCompra`. Luego se bloquean, en el
orden canónico existente, productos, compromisos y movimientos.

Una entrega válida mantiene las garantías D2:

- transición atómica de compromisos `ACTIVE → CONSUMED`;
- reducción simultánea de `stock_real` y `stock_comprometido`;
- clave determinística por orden y producto;
- un solo `MovimientoStock` por efecto;
- transición final `PAGADO → COMPLETADO`.

En un retry, `COMPLETADO + CONSUMED + movimientos completos` devuelve el mismo
efecto con `applied=False`. Estados incompletos o contradictorios fallan
cerrados, sin intentar repararlos mediante una nueva salida.

`OrdenPendiente` se bloquea antes de delegar en la orden canónica. Si una orden
legacy no vinculada intenta materializarse y no está pagada, toda la creación
transitoria se revierte por la transacción.

## Rechazos y stock intacto

Los siguientes rechazos fueron comprobados sin cambios de dominio:

| Caso | Respuesta | Orden | Compromiso | Stock real/comprometido | Movimiento |
|---|---|---|---|---|---|
| Cliente, orden `PENDIENTE` | HTTP 403 | `PENDIENTE` | `ACTIVE` | intacto | ninguno |
| Cliente, orden `PAGADO` | HTTP 403 | `PAGADO` | `ACTIVE` | intacto | ninguno |
| Actor autorizado, `ESPERANDO_PAGO` | HTTP 409 `ORDER_NOT_PAID` | sin cambio | `ACTIVE` | intacto | ninguno |
| Actor autorizado, `CANCELADO` | HTTP 409 `ORDER_NOT_PAID` | `CANCELADO` | `RELEASED` | intacto | ninguno |
| Cliente por aliases `OrdenPendiente` | HTTP 403 | `PAGADO` | `ACTIVE` | intacto | ninguno |
| Legacy sin orden canónica pagada | HTTP 409 `ORDER_NOT_PAID` | no se materializa | no se crea | intacto | ninguno |

## Pruebas

Se ejecutó sobre PostgreSQL real:

```text
python -X utf8 manage.py test \
  gestion.tests.test_inventory_stock \
  gestion.tests.test_inventory_stock_concurrency \
  gestion.tests.test_inventory_permissions_d3 \
  gestion.tests.test_order_inventory \
  gestion.tests.test_order_inventory_concurrency \
  gestion.tests.test_provider_reconciliation \
  gestion.tests.test_provider_reconciliation_concurrency \
  --noinput
```

Resultado:

```text
Ran 93 tests in 296.383s
OK
```

La matriz incluye:

- Cliente intenta entregar orden no pagada: rechazado, stock intacto;
- Cliente intenta entregar orden `PAGADO`: rechazado por permiso;
- `is_staff` sin permiso efectivo: rechazado;
- llamada directa al servicio con actor sin permiso: rechazada;
- actor con `gestion.manage_stock` intenta entregar orden no pagada: rechazado;
- actor autorizado entrega orden `PAGADO`: `COMPLETADO` y un efecto físico;
- reintento: mismo movimiento, sin segunda salida;
- dos entregas concurrentes: un único movimiento;
- entrega versus cancelación: un solo ganador terminal;
- orden cancelada e inconsistencias: rechazo sin mutación;
- aliases de `OrdenPendiente`: misma política;
- D1/D2/D3 completos y conciliación C2b funcional/concurrente.

Controles adicionales:

- `python -X utf8 manage.py check`: sin issues;
- `python -X utf8 manage.py makemigrations --check --dry-run`: sin cambios;
- compilación Python: correcta;
- `git diff --check`: sin errores.

No se modificaron checkout, webhooks, frontend BOOKING ni procesos automáticos.
No se creó ninguna migración ni permiso nuevo: se reutilizó el permiso efectivo
`gestion.manage_stock` ya definido y asignable mediante Django.

## Archivos F1

- `bohemiacore/gestion/order_inventory_services.py`;
- `bohemiacore/gestion/views.py`;
- `bohemiacore/gestion/tests/test_order_inventory.py`;
- `bohemiacore/gestion/tests/test_order_inventory_concurrency.py`;
- `bohemiacore/gestion/tests/test_provider_reconciliation.py`;
- `CORRECCION_BH058_F1_ENTREGA_ORDENES.md`.

## Veredicto

**BH-058 F1 = VALIDADO**
