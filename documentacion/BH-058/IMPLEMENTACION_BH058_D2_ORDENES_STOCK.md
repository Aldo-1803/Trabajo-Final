# BH-058 D2 — OrdenCompra, compromisos y efecto de inventario

## Alcance

D2 integra exclusivamente las ventas de productos con la autoridad de
inventario creada en D1. No agrega proveedor, compra de abastecimiento,
devolución, consumo por Servicio, caja física, booking, integración nueva de
Mercado Pago, eventos de proveedor, D3 ni BH-059.

La semántica resultante es:

```text
MovimientoStock                    = hechos físicos autoritativos
Producto.stock_real                = proyección física materializada
CompromisoStock ACTIVE             = hechos de reserva autoritativos
Producto.stock_comprometido        = proyección materializada de ACTIVE
Producto.stock_disponible          = stock_real - stock_comprometido
```

No se usa clamp. Las nuevas operaciones no permiten saldo real negativo,
compromiso negativo ni `stock_comprometido > stock_real`.

## CompromisoStock

`CompromisoStock` relaciona una `OrdenCompra` y un `Producto` con:

- cantidad estrictamente positiva;
- estado `ACTIVE`, `CONSUMED` o `RELEASED`;
- `created_at`, `consumed_at` y `released_at` coherentes con el estado;
- `idempotency_key` única y determinista;
- `reason_code` y metadata mínima de origen.

La base impone:

- `cantidad > 0`;
- unicidad `orden + producto`;
- key no vacía y única;
- timestamps terminales mutuamente excluyentes;
- `0 <= Producto.stock_comprometido <= Producto.stock_real`.

El modelo no acepta creación, actualización ni borrado genéricos. El admin es
de sólo lectura y no existe serializer de escritura. Sus únicas transiciones
son las operaciones internas de `order_inventory_services.py`.

## Lifecycle

### Crear

`create_order_stock_commitments(order_id)`:

1. bloquea la Orden;
2. consolida líneas repetidas por Producto;
3. bloquea Productos por PK ascendente;
4. bloquea compromisos existentes por PK;
5. verifica que la proyección coincida con la suma de compromisos `ACTIVE`;
6. valida disponibilidad para el conjunto completo;
7. crea un compromiso por Producto lógico;
8. aumenta exclusivamente la proyección comprometida.

No cambia `stock_real` ni crea `MovimientoStock`. Si un Producto no alcanza,
toda la operación revierte.

Los dos checkouts actuales de `OrdenCompra` crean el compromiso antes de vaciar
el carrito. En Mercado Pago legacy, si falla la creación de la preferencia, la
Orden, sus líneas y compromisos revierten junto con la transacción.

### Consumir

`apply_order_inventory_effect(order_id)` es el único writer físico de ventas de
`OrdenCompra`. Para cada Producto consolidado deriva:

```text
order:{order_id}:inventory:v1:product:{product_id}
```

El efecto:

- crea `MovimientoStock.ORDER_SALE_OUT` con delta negativo;
- referencia `ORDEN_COMPRA/{order_id}`;
- consume los compromisos;
- reduce las dos proyecciones en la misma transacción;
- deja la Orden en `COMPLETADO`;
- en un retry devuelve los mismos movimientos sin descontar nuevamente.

Una Orden legacy activa sin compromisos se trata con política explícita
just-in-time: dentro de la misma transacción se valida disponibilidad, se crea
la reserva y se consume. Una Orden cancelada/rechazada, una reserva liberada o
un estado parcialmente incoherente no se reabre silenciosamente.

### Liberar

`release_order_stock_commitments()` hace `ACTIVE -> RELEASED`, reduce únicamente
`stock_comprometido` y deja intactos `stock_real` y `MovimientoStock`. Repetir
la misma liberación devuelve el estado existente. Un compromiso `CONSUMED` no
puede liberarse.

## Locks y atomicidad

La secuencia canónica es:

```text
OrdenCompra
  -> Productos por PK ascendente
  -> CompromisoStock por PK ascendente
  -> MovimientoStock existente por idempotency_key
```

Luego D1 recibe los mismos Productos ya bloqueados y aplica el batch físico
todo-o-nada. La proyección comprometida se reduce antes del `UPDATE` físico para
respetar en cada sentencia la constraint `comprometido <= real`; cualquier
error posterior revierte ambos cambios por `transaction.atomic()`.

La compatibilidad de `OrdenPendiente` toma primero su propia fila, porque dos
acciones legacy deben serializar la creación de su vínculo canónico. Después
entra a la secuencia anterior. Ningún flujo canónico toma los locks en orden
inverso.

Las carreras PostgreSQL verificaron dos órdenes por la última unidad, doble
confirmación, confirmar contra cancelar, liberar contra consumir, órdenes
multítem cruzadas y retry con la misma key, sin deadlock ni efecto duplicado.

## Compatibilidad con OrdenPendiente

`OrdenPendiente` conserva su endpoint y payload hasta BH-059, pero ya no escribe
stock. Un vínculo nullable uno-a-uno identifica la `OrdenCompra` canónica:

- nuevas intenciones crean ambas entidades y comprometen mediante D2;
- una intención histórica sin vínculo materializa la Orden canónica sólo al
  ejecutar una confirmación explícita;
- confirmar pago o entrega delega en `apply_order_inventory_effect()`;
- cancelar delega en la liberación canónica;
- una intención histórica ya completada sin evidencia trazable no recibe un
  movimiento inventado retroactivamente.

Esto elimina corrupción de inventario sin retirar el contrato duplicado, cuya
limpieza continúa perteneciendo a BH-059.

## Writers legacy reemplazados

Se retiraron las cinco asignaciones directas de `stock_real` documentadas en
D1:

1. webhook Mercado Pago legacy de `OrdenCompra`;
2. `OrdenPendiente.confirmar_pago`;
3. `OrdenPendiente.confirmar_entrega`, rama de items relacionados inexistente;
4. `OrdenPendiente.confirmar_entrega`, rama `items_json`;
5. `OrdenCompra.confirmar_entrega`.

También se retiraron los writers directos de `stock_comprometido` de:

- `CarritoViewSet.finalizar_compra`;
- `CarritoViewSet.registrar_intencion_compra`;
- cancelaciones de `OrdenCompra` y `OrdenPendiente`;
- confirmaciones legacy que intentaban limpiar la proyección con clamps.

La búsqueda final sólo encuentra escrituras físicas en el command D1 y
escrituras comprometidas en el servicio D2.

## Mercado Pago legacy

No se rediseñó el provider. El webhook existente aún consulta el pago oficial,
pero:

- aprobación delega en el efecto idempotente único;
- rechazo/cancelación libera compromisos;
- retries no duplican `Pago` ni `MovimientoStock`;
- la return URL/frontend no es autoridad de inventario.

Firma durable, `ProviderEvent`, `ProviderPaymentAttempt` y reconciliación nueva
siguen fuera de D2 y pertenecen a C.

## Migración 0033

`0033_compromisostock_order_inventory.py` crea el modelo, el vínculo de
compatibilidad, índices y constraints. Su preflight:

1. bloquea la migración si cualquier Producto tiene `stock_comprometido > 0`;
2. lista IDs afectados sin imprimir datos sensibles;
3. no intenta atribuir ese saldo entre `OrdenCompra` y `OrdenPendiente`;
4. no resetea ni recalcula compromisos;
5. advierte sobre órdenes activas sin reserva estructurada;
6. permite tratarlas luego con la política just-in-time transaccional.

No existe backfill histórico automático: los datos actuales no permiten
inferirlo sin ambigüedad.

## Permisos y contratos

Se conservan `view_stock` y `manage_stock`. El efecto físico de una venta es una
operación interna de dominio y no concede autoridad por `is_staff`,
`BusinessRole` ni `Personal.rol`. Los serializers de órdenes ya no permiten
escribir genéricamente estado, Cliente o total para evadir las transiciones.

No hubo cambio frontend: los contratos de respuesta usados por las pantallas se
mantuvieron y no se implementó D3.

## Pruebas ejecutadas

- D2 funcional/integración/migración: 17/17.
- D2 concurrencia PostgreSQL real: 6/6.
- D1: 26/26 dentro de la corrida conjunta D1+D2 previa (43/43 antes de
  ampliar los últimos casos de integración D2).
- B3 funcional: 11/11; concurrencia: 7/7.
- B2 funcional: 20/20; concurrencia: 6/6.
- B1 funcional: 18/18; concurrencia: 3/3.
- A2 funcional: 15/15; concurrencia: 7/7.
- A1 funcional: 19/19; concurrencia: 7/7.
- matriz A1–B3: 113/113.
- roles y `/me/`: 31/31.

Checks técnicos:

- `python manage.py check`: sin issues;
- `python manage.py makemigrations --check --dry-run`: sin cambios;
- `python -m compileall gestion usuarios`: correcto;
- `git diff --check`: correcto, salvo avisos CRLF/LF existentes.

La primera matriz conjunta A1–B3 fue interrumpida por timeout del harness y dejó
una base temporal incompleta. No se contabilizó. Todas las suites restantes se
repitieron por bloque con una base de test limpia; no quedó ningún fallo real.

## Frontera

D2 termina en compromisos estructurados, proyección controlada y efecto físico
único de órdenes. No implementa UI D3, provider nuevo C, booking, consumo de
Servicio, proveedores, devoluciones, caja física ni BH-059.

BH-058 D2 = VALIDADO
