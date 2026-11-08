# BH-058 F5 — Cancelación segura de órdenes pagadas

Fecha de validación: 2026-10-29.

## Resultado

Se cerró el defecto por el cual la titular de una `OrdenCompra` podía invocar la
cancelación ordinaria sobre una orden `PAGADO`, cambiarla a `CANCELADO` y liberar
su `CompromisoStock` sin resolver el dinero ya acreditado.

La regla resultante es:

```text
titular activa o actor activo con gestion.manage_stock
                            +
OrdenCompra bloqueada sin pago no resuelto
                            ↓
cancelación idempotente y CompromisoStock RELEASED
```

Una orden `PAGADO`, una orden con un `Pago` `PENDING_RECONCILIATION` o
`RECONCILED`, y una orden `COMPLETADO` quedan fuera de la cancelación
convencional. El rechazo no cambia orden, pagos, compromisos, stock ni
movimientos.

## Defecto

La ruta principal era:

```text
POST /api/gestion/ordenes-compra/{id}/cancelar/
```

El queryset aplicaba ownership para la clienta, pero el servicio
`release_order_stock_commitments` no recibía actor ni validaba el estado
financiero bajo el lock de la orden. Por eso aceptaba `PAGADO`, pasaba el
compromiso de `ACTIVE` a `RELEASED` y dejaba el pago sin una resolución
financiera asociada.

El alias legacy presentaba el mismo riesgo al delegar sin autoridad explícita:

```text
POST /api/gestion/ordenes-pendientes/{id}/cancelar/
```

## Rutas inspeccionadas

- `OrdenCompraViewSet.cancelar`: usada por titular y por personal con
  visibilidad global derivada de `gestion.manage_stock`;
- `OrdenPendienteViewSet.cancelar`: contrato legacy para clienta y personal;
- `release_order_stock_commitments`: única transición canónica que libera un
  compromiso de una `OrdenCompra`;
- `release_pending_order_stock_commitments`: bloquea la orden legacy y delega
  en la transición canónica cuando existe el puente a `OrdenCompra`;
- callers internos de pruebas de inventario y conciliación C2b.

Las acciones `Turno.cancelar`, `Turno.cancelar-cliente` y
`PaymentIntent.cancel` también fueron identificadas, pero no cancelan
`OrdenCompra` ni liberan `CompromisoStock`; no forman parte de F5.

## Corrección de dominio

### Autoridad efectiva

Los dos servicios de liberación requieren ahora `actor`. La autorización se
comprueba dentro de la transacción y permite únicamente:

- la titular activa y autenticada de la orden; o
- un actor activo y autenticado con `gestion.manage_stock` efectivo.

No se usa `is_staff`, nombre de rol ni `Personal.rol`. Un usuario marcado sólo
como staff fue probado sin autoridad de cancelación.

Las views pasan `request.user` explícitamente. El ownership de sus querysets
sigue evitando enumerar órdenes ajenas, pero ya no es la única barrera.

### Estados y hechos financieros

Después de bloquear la `OrdenCompra`, el servicio bloquea los pagos no resueltos
asociados y aplica estas reglas:

| Condición | Resultado |
|---|---|
| Orden impaga, sin pago no resuelto | Puede cancelarse; libera sólo compromiso y proyección comprometida |
| `PAGADO` | HTTP 409 `ORDER_CANCELLATION_REQUIRES_FINANCIAL_RESOLUTION` |
| Pago `PENDING_RECONCILIATION` o `RECONCILED` aunque la orden figure impaga | Mismo rechazo financiero |
| Pago `REJECTED` o `REVERSED` y orden impaga | No bloquea por sí solo: ya existe resolución previa |
| `COMPLETADO` | HTTP 409 `COMPLETED_ORDER_CANNOT_CANCEL` |
| Retry de cancelación válida | Idempotente; no duplica transición ni movimiento |

El mensaje de `ORDER_CANCELLATION_REQUIRES_FINANCIAL_RESOLUTION` indica de forma
explícita que la orden requiere resolución financiera. F5 no crea una solicitud
de cancelación ni inventa un estado comercial nuevo.

### Transacción y locks

La decisión se ejecuta en `transaction.atomic()` con este orden:

```text
OrdenCompra FOR UPDATE
→ autorización
→ Pago no resuelto FOR UPDATE
→ validación de estado financiero
→ productos y CompromisoStock FOR UPDATE
→ liberación, sólo si todo lo anterior permite cancelar
```

C2b también bloquea primero `OrdenCompra` antes de crear/conciliar el pago y
marcar `PAGADO`. Por lo tanto, cancelación y conciliación se serializan:

- si C2b gana, la cancelación observa `PAGADO` y se rechaza;
- si la cancelación impaga gana, C2b observa una orden no cumplible, conserva el
  pago como `PENDING_RECONCILIATION` y abre revisión en vez de marcarla pagada.

En la carrera con entrega, una orden ya `PAGADO` nunca puede liberar el
compromiso: la entrega autorizada consume una sola vez y la cancelación devuelve
el rechazo financiero.

## Invariantes comprobados ante rechazo

- `OrdenCompra.estado` permanece sin cambios;
- `CompromisoStock` permanece `ACTIVE` para la orden pagada;
- `stock_real` y `stock_comprometido` permanecen intactos;
- el `Pago` reconciliado conserva todos sus campos;
- no se crea ningún `MovimientoStock`;
- el alias `OrdenPendiente` tampoco cambia su estado;
- titular y personal con permiso reciben el mismo error semántico.

## Pruebas

Matriz funcional focalizada F5:

```text
Ran 9 tests in 17.484s
OK
```

Las carreras F5 forman parte de la siguiente matriz de regresiones F1, D1, D2,
D3 y C2b sobre PostgreSQL real:

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

Ran 103 tests in 269.964s
OK
```

Descubrimiento backend general del proyecto:

```text
python -X utf8 manage.py test --noinput

Ran 140 tests in 221.041s
OK
```

Controles adicionales:

- `python manage.py check`: sin issues;
- `python manage.py makemigrations --check --dry-run`: sin cambios;
- compilación Python de `gestion`: correcta;
- `git diff --check`: sin errores (sólo avisos locales de normalización CRLF).

## Archivos F5

- `bohemiacore/gestion/order_inventory_services.py`;
- `bohemiacore/gestion/views.py`;
- `bohemiacore/gestion/tests/test_order_inventory.py`;
- `bohemiacore/gestion/tests/test_order_inventory_concurrency.py`;
- `bohemiacore/gestion/tests/test_provider_reconciliation.py`;
- `bohemiacore/gestion/tests/test_provider_reconciliation_concurrency.py`;
- `CORRECCION_BH058_F5_CANCELACION_ORDEN_PAGADA.md`.

## Operaciones diferidas

F5 deliberadamente no implementa:

- refunds, créditos ni chargebacks;
- nueva caja o estados financieros;
- una solicitud comercial separada de cancelación;
- cambios de webhooks o automatizaciones;
- cambios en frontend BOOKING.

Una futura operación de cancelación con dinero deberá resolver primero la
obligación financiera mediante un contrato explícito y auditable. No deberá
reabrir la liberación ordinaria protegida por F5.

## Veredicto

**BH-058 F5 = VALIDADO**
