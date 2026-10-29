# BH-058 D — Stock, movimientos de inventario, permisos, productos, precios y reportes

Fecha del análisis: 2026-10-25

Alcance: autoridad de inventario, movimientos trazables, concurrencia,
idempotencia, pedidos de productos, permisos efectivos, catálogo, precios,
promociones, reportes, privacidad, migración y pruebas.

Este documento **no modifica código**, no rediseña `SlotHold`, `PaymentIntent`,
`Pago` ni `MercadoPagoAdapter`, no implementa BH-059 y no propone reservar
inventario por un Turno. Conserva las decisiones de BH-058 A/B/C.

## 1. Conclusión ejecutiva

El inventario actual es una **mezcla de autoridad directa y proyecciones sin
dueño**:

- `Producto.stock_real` es la autoridad física mutable en la práctica;
- `Producto.stock_comprometido` intenta ser una proyección de reservas de
  pedidos, pero no existe una entidad que explique cada unidad comprometida;
- `stock_disponible = max(0, stock_real - stock_comprometido)` oculta
  inconsistencias en vez de impedirlas;
- no existe `MovimientoStock`, recepción, proveedor, devolución, receta de
  Servicio ni consumo estructurado;
- al menos ocho caminos escriben stock o compromiso directamente, ninguno
  bloquea filas `Producto` y varios aplican `max(0, ...)`;
- `transaction.atomic()` no evita carreras si no se usa `select_for_update()`;
- `OrdenCompra` es, pese a su nombre, una **venta/pedido de productos al
  Cliente**. Su efecto físico correcto es una salida, nunca una entrada;
- `OrdenPendiente` duplica el dominio con estados, items JSON y efectos de
  stock incompatibles;
- los permisos `view_stock`, `manage_stock`, `manage_products`,
  `manage_prices`, `manage_promotions` y `view_financial_reports` existen, pero
  los endpoints relevantes usan mayormente `AllowAny`, `IsAdminUser` o
  `is_staff`;
- el serializer público revela stock real, comprometido, mínimo y disponible;
- la misma pantalla administrativa permite cambiar catálogo, precio, stock y
  promociones sin separar capabilities;
- no hay tests backend de stock, órdenes o concurrencia.

### Decisión de arquitectura

Se recomienda:

```text
MovimientoStock inmutable = hechos físicos autoritativos
Producto.stock_real       = proyección materializada controlada

CompromisoStock/ReservaStock de pedido = hechos de reserva autoritativos
Producto.stock_comprometido            = proyección materializada controlada
Producto.stock_disponible               = real - comprometido, sin clamp
```

No conviene calcular la existencia sumando todo el ledger en cada lectura. La
proyección permite conservar el rendimiento y casi todo el esquema actual, pero
deja de ser editable: sólo commands transaccionales pueden moverla. El ledger
permite reconstruirla y reconciliarla.

El primer incremento debe cerrar autoridad, locks, ledger, idempotencia,
permisos y el efecto único de `OrdenCompra`. No debe agregar proveedores,
compras al proveedor, lotes, costos, devoluciones ni consumo por Servicio.

---

## 2. Fuentes auditadas y estado de datos

Se revisaron modelos, serializers, views, signals, admin, filtros, estadísticas,
roles, migraciones, commands, tests, rutas y pantallas frontend relacionadas.
Los puntos principales están en:

- `bohemiacore/gestion/models.py`;
- `bohemiacore/gestion/views.py`;
- `bohemiacore/gestion/serializers.py`;
- `bohemiacore/gestion/signals.py`;
- `bohemiacore/gestion/admin.py`;
- `bohemiacore/gestion/stats_views.py`;
- `bohemiacore/gestion/filters.py`;
- `bohemiacore/usuarios/roles.py`;
- `frontend/src/pages/admin/GestionProductos.js`;
- `frontend/src/pages/cliente/CatalogoProductos.js`;
- `frontend/src/components/AlertasCriticas.js`;
- `frontend/src/components/admin/DashboardStats.js`;
- `frontend/src/navigation/navigationConfig.js` y `frontend/src/routes/index.js`.

Una consulta sólo lectura a la PostgreSQL configurada devolvió:

```text
productos=0; OrdenCompra=0; OrdenPendiente=0; OrdenItem=0
```

No hay, en este entorno, saldo que conservar ni historia que reconstruir. Los
archivos de media existentes no prueban filas vigentes. Otro entorno debe pasar
un preflight antes de migrar; no se debe inferir que también está vacío.

---

## 3. Inventario actual

### 3.1 Mapa de piezas

| Elemento | Autoridad y escritores actuales | Lectores/efectos | Historial y autorización | Riesgo |
|---|---|---|---|---|
| `Producto` | Registro de catálogo y contenedor de precio/stock. API, admin y flujos de órdenes llaman `save()` directamente. | Catálogo, carrito, recomendaciones, alertas, combos, admin. | `HistoricalRecords` y señal `Auditoria`. API escribe con `IsAdminUser`; admin usa permisos Django estándar. | Mezcla catálogo, precio y tres conceptos de inventario bajo una sola autorización. |
| `stock_real` | Autoridad física directa. Writable por `ProductoSerializer`, admin, webhook y confirmaciones de órdenes. | Se usa para borrar producto, sugerir productos y validar/descontar ventas. | Hay snapshots genéricos, no un hecho semántico. | Lost updates, doble descuento, clamps silenciosos y ausencia de origen/idempotencia. |
| `stock_comprometido` | Campo mutable que intenta representar pedidos WhatsApp. Read-only en serializer, pero escrito por múltiples views. | Alimenta `stock_disponible`; admin lo muestra read-only. | No existe detalle de qué orden explica el saldo. | Deriva, se libera o descuenta de forma desigual; puede quedar huérfano. |
| `stock_disponible` | Property calculada `max(0, real-comprometido)`. | Catálogo, carrito, UI administrativa y signal de combos. | No persiste ni tiene historial. | El clamp convierte un saldo inválido en cero y dificulta detectar `comprometido > real`. |
| `stock_minimo` | Configuración directa en CRUD Producto y admin. Admite negativos en modelo. | Property `necesita_reposicion`, UI y endpoint `stock_bajo`. | Auditoría genérica; misma autorización que todo Producto. | No hay constraint `>= 0`; el endpoint usa una fórmula distinta de la property. |
| `CategoriaProducto` | CRUD completo `AllowAny`. | Catálogo y agrupación de combos. | Señal genérica de auditoría. | Un anónimo puede crear, editar o borrar categorías. |
| Proveedor/compra al proveedor | No existen modelos, serializers, UI ni commands. | Ninguno. | Ninguno. | `OrdenCompra` no debe reutilizarse para este concepto. |
| `OrdenCompra` | Pedido/venta al Cliente, con `cliente`, items, total y pagos. Cualquier autenticado tiene ModelViewSet; staff ve todas. | Checkout MP, pedidos, caja, estadísticas y efecto de salida. | `HistoricalRecords`; no hay permiso comercial específico. | Nombre ambiguo, estados mutables por CRUD, clientes pueden invocar acciones sobre sus órdenes. |
| `OrdenItem` | Item estructurado de `OrdenCompra`, cantidad y `precio_historico`. | Webhook, entrega, cancelación y reportes. | `HistoricalRecords`. | No hay uniqueness por orden/producto ni estado de reserva/aplicación de inventario. |
| `OrdenPendiente` | Intención WhatsApp paralela con `items_json`. | Reserva, confirmación, entrega y cancelación legacy. | Auditoría manual sólo al registrar intención; ModelViewSet autenticado. | Items sin FK, estados incompatibles, acciones duplicadas y manipulables. |
| Entradas/recepciones | No existe flujo. El botón “Reabastecer” no tiene handler. | Ninguno. | Ninguno. | La única forma real de aumentar stock es editar `Producto.stock_real`. |
| Ajustes | No existe command. | Sólo edición absoluta del campo. | Snapshot genérico. | No exige motivo ni conserva delta semántico. |
| Devoluciones | No existe devolución de Cliente, proveedor ni reversión de venta. | Ninguno. | Ninguno. | No hay evidencia para implementar tipos o automatizaciones ahora. |
| Signals | El signal de `Producto` lee stock al crear y puede crear una sugerencia `Promocion`; no escribe stock. | Calcula `stock_combo` como mínimo disponible inicial. | Promoción y Producto tienen history/auditoría. | `stock_combo` queda como snapshot y no se reduce con ventas. |
| Servicios de dominio | No hay servicio de inventario. Las mutaciones viven en views. | MercadoPagoService sólo crea preferences. | Logging parcial. | Reglas duplicadas y difíciles de probar/reutilizar. |
| Commands/scripts | Los commands existentes no escriben inventario. No hay fixtures o seeds de Producto. | `procesar_promos` trata promociones, no stock físico. | N/A. | No hay bootstrap estructurado de inventario. |
| Reportes | `stats` agrega ventas desde órdenes completadas. No hay reporte de saldo ni movimientos. | UI mezcla ingresos, ventas y rutinas. | Backend `IsAdminUser`; frontend admite permisos de reportes. | Autorización incoherente y datos financieros/operativos mezclados. |

### 3.2 Constraints actuales

- `stock_real` y `stock_comprometido` son `PositiveIntegerField`;
- `stock_minimo` es `IntegerField` y puede ser negativo;
- no hay `CheckConstraint` para `stock_comprometido <= stock_real`;
- no hay constraint de coherencia entre saldo y una suma de hechos;
- `OrdenItem.cantidad` es positiva, pero no hay unicidad por producto/orden;
- no hay idempotency key de inventario;
- no hay referencia que demuestre qué orden comprometió cada unidad.

### 3.3 Lecturas incoherentes

1. `Producto.necesita_reposicion` compara `stock_disponible <= stock_minimo`.
2. `ProductoViewSet.stock_bajo` documenta esa fórmula, pero filtra
   `stock_real <= stock_minimo` e ignora comprometido.
3. `ProductoFilter.filter_stock` consulta un campo inexistente `stock__lte=5`.
4. `sugeridos_por_cliente` exige `stock_real > 0`, no stock disponible.
5. El signal de combos sí usa `stock_disponible`, pero persiste `stock_combo`
   una sola vez y no lo reconcilia.
6. `AlertasCriticas` espera `producto.stock`; el serializer entrega
   `stock_real`/`stock_disponible`, por lo que muestra `undefined` y calcula
   porcentajes inválidos.

`stock_minimo` es hoy sólo un **umbral informativo**. No bloquea ventas, no
genera recepción y no debe convertirse en regla automática. Cero sí debe poder
venderse hasta agotar; “bajo mínimo” no equivale a “insuficiente”.

---

## 4. Todos los escritores de stock

| Origen | Operación | Campo | Lock de Producto | Auditoría | Permiso efectivo actual | Riesgo |
|---|---|---|---|---|---|---|
| CRUD `ProductoViewSet` | POST/PUT/PATCH con valor absoluto | `stock_real`, `stock_minimo`; también `precio` | No | simple-history + `Auditoria` genérica | `IsAdminUser` (`is_staff`) | Cambio sin delta/motivo; mezcla stock, precio y catálogo. |
| Django admin `ProductoAdmin` | Alta/cambio directo | `stock_real`, `stock_minimo`, `precio` | No | history + señal; admin log adicional | `is_staff` para entrar + permiso Django `add/change_producto`; no permisos de negocio | Evade `manage_stock` y `manage_prices`. |
| `CarritoViewSet.finalizar_compra` | Reserva pedido y crea `OrdenCompra(PENDIENTE)` | `stock_comprometido += cantidad` | No | history/señal genérica + logger | Cualquier usuario autenticado con perfil Cliente | Dos carritos pueden comprometer el mismo saldo; validación ocurre antes de `atomic`. |
| `CarritoViewSet.registrar_intencion_compra` | Reserva intención WhatsApp | `stock_comprometido += cantidad` | No; tampoco `atomic` | history/señal + `Auditoria` sólo de la orden; errores de auditoría se ignoran | Cliente autenticado | Orden y reservas parciales si falla; doble click duplica compromisos; items JSON. |
| Webhook MP de `OrdenCompra` | Aprobación de pago | `stock_real = max(0, real-cantidad)` | Bloquea Orden, no Productos | history/señal con actor sistema nulo + logger | Endpoint `AllowAny`; autoridad externa tratada en C | Oversell, clamp, productos sin reserva, efecto acoplado al webhook. |
| `OrdenPendiente.confirmar_pago` | Completa pedido WhatsApp | `stock_real -=` con clamp y `stock_comprometido -=` | No; no `atomic` | history/señal + logger | **Cualquier autenticado** sobre orden visible; no check staff | Cliente puede completar su orden; fallos dejan productos parcialmente aplicados. |
| `OrdenPendiente.confirmar_entrega` | Completa pedido | `stock_real -=`; `stock_comprometido -=` con clamp | `atomic`, sin row lock | history/señal + logger | **Cualquier autenticado** sobre orden visible | Duplica confirmar pago; return dentro de TX; formato relacionado inexistente y fallback JSON. |
| `OrdenPendiente.cancelar` | Intenta liberar reserva | `stock_comprometido -=` con clamp | `atomic`, sin row lock | history/señal + logger | **Cualquier autenticado** | Referencia `orden.items`, relación que no existe; en el modelo actual termina en 500 y no libera. |
| `OrdenCompra.confirmar_entrega` | Completa venta | `stock_real -=` y `stock_comprometido -=`, ambos con clamp | `atomic`, sin row lock | history/señal + logger | **Cualquier autenticado** sobre su orden; no check staff | Puede descontar además del webhook; exige compromiso que checkout MP nunca creó. |
| `OrdenCompra.cancelar` | Libera pedido pendiente | `stock_comprometido -=` con clamp | `atomic`, sin row lock | history/señal + logger | **Cualquier autenticado** sobre su orden | Sólo acepta `PENDIENTE`; MP nace `ESPERANDO_PAGO`; puede liberar compromiso ajeno/inexistente. |
| Migraciones/model defaults | Inicialización | saldo inicial `0`, mínimo `5` | N/A | Historia de schema, no hecho comercial | Despliegue | No sirve como ledger ni bootstrap de datos. |
| Signals | Ninguna escritura de stock encontrada | — | — | — | — | El signal de Producto sólo lee saldo y crea promociones. |
| Commands/scripts/fixtures | Ninguna escritura encontrada | — | — | — | — | No hay recepción ni ajuste por command. |

También hay bypasses de estado: los serializers de `OrdenCompra` y
`OrdenPendiente` permiten escrituras genéricas de estados/totales sin ejecutar
el efecto correspondiente. Aunque no escriben stock por sí mismos, rompen la
premisa de que el estado de la orden identifica si el inventario fue aplicado.

### 4.1 Por qué `atomic()` actual no alcanza

Dos transacciones pueden leer `stock_real=1`, validar una salida de una unidad y
guardar ambas `0`. Las dos órdenes quedan completadas y sólo se observa una
unidad menos. El mismo patrón pierde incrementos en entrada + ajuste, o libera
reservas dos veces. Bloquear la orden no bloquea el Producto.

Los `max(0, ...)` agravan el problema: convierten una salida imposible en una
venta aparentemente válida y destruyen la evidencia de faltante.

---

## 5. Autoridad futura

### 5.1 Alternativas

| Alternativa | Ventaja | Problema | Decisión |
|---|---|---|---|
| `Producto.stock_real` autoridad; movimiento sólo auditoría | Cambio pequeño. | Un escritor directo puede cambiar saldo sin hecho; no se reconstruye ni prueba completitud. | Rechazada. |
| Derivar cada lectura de `SUM(delta)` | Fuente única estricta. | Más costo y mayor cambio para catálogo/carrito; complica hot path. | No para v1. |
| Movimiento autoridad + `stock_real` proyección controlada | Trazabilidad y reconstrucción con lecturas simples. | Exige un único command y reconciliación. | **Recomendada.** |

La proyección no significa “otra autoridad”. Su escritura queda encapsulada y
la igualdad siguiente pasa a ser un invariante verificable:

```text
Producto.stock_real = SUM(MovimientoStock.delta por producto)
```

Ningún serializer, form, admin, signal, webhook o view puede asignarla.

### 5.2 Stock negativo

Recomendación v1: **no permitir stock físico negativo**.

- una salida que dejaría saldo menor que cero falla completa;
- no se usa clamp;
- un conteo físico de cero genera delta hasta cero, nunca saldo negativo;
- backorders, preventa o venta sin existencia serían otro concepto explícito,
  no un número físicamente imposible.

También se debe impedir `stock_comprometido < 0` y
`stock_comprometido > stock_real`.

---

## 6. Modelo mínimo `MovimientoStock`

### 6.1 Campos recomendados

| Campo | Contrato |
|---|---|
| `id` | PK inmutable. |
| `producto` | FK obligatoria, `PROTECT`. |
| `delta` | Entero signed, distinto de cero. Positivo entra; negativo sale. |
| `tipo` | Choice cerrado del conjunto implementado. |
| `reason_code` | Motivo estructurado; obligatorio en ajustes/correcciones. |
| `nota` | Opcional, longitud limitada; no sustituye al reason code. |
| `actor_kind` | `HUMAN` o `SYSTEM`. |
| `actor` | FK a usuario; obligatoria cuando `actor_kind=HUMAN`. |
| `created_at` | Timestamp de creación, no editable. |
| `reference_type`, `reference_id` | Origen estable del hecho. Para la venta debe apuntar a Orden/Item. |
| `idempotency_key` | Obligatoria y unique; generada por Cliente sólo para commands humanos o derivada internamente para efectos de dominio. |
| `stock_before`, `stock_after` | Obligatorios en esta proyección; facilitan auditoría y reconciliación. |
| `reverses_movement` | FK opcional `PROTECT` para corrección compensatoria. |

Una FK nullable directa a `OrdenCompra` puede añadirse mientras sea el único
origen automático. Un `GenericForeignKey` no ofrece integridad referencial. Si
se eligen referencias polimórficas, `reference_type/id` deben validarse en el
servicio y no aceptar tipos arbitrarios desde la API.

### 6.2 Tipos para el primer incremento

Con evidencia actual sólo hacen falta:

- `OPENING_BALANCE`: exclusivamente migración/bootstrap identificado;
- `RECEIPT_IN`: entrada manual de mercadería, sin inventar proveedor;
- `ORDER_SALE_OUT`: salida por venta de `OrdenCompra`;
- `MANUAL_ADJUSTMENT`: diferencia de conteo con motivo;
- `CORRECTION`: compensación de un movimiento erróneo.

No incluir aún:

- `SERVICE_CONSUMPTION`: no hay receta estructurada;
- `RETURN`: no existe contrato de devolución;
- `PURCHASE_IN`: no existe compra a proveedor; una recepción simple no prueba
  ese origen comercial;
- `RESERVATION_RELEASE`: reservar/liberar no cambia stock físico y debe vivir en
  el ledger de compromisos, no en `MovimientoStock`.

### 6.3 Constraints

En base de datos:

- `delta <> 0`;
- `stock_before >= 0`, `stock_after >= 0`;
- `stock_after = stock_before + delta`;
- unique no nullable en `idempotency_key`;
- producto obligatorio;
- actor obligatorio si `actor_kind='HUMAN'` y nulo si se adopta un actor sistema
  explícito sin usuario;
- una corrección referencia un movimiento y no puede revertirse a sí misma;
- checks de signo por tipo cuando el tipo tenga dirección fija;
- `Producto.stock_real >= 0`, `stock_minimo >= 0`,
  `0 <= stock_comprometido <= stock_real`.

En el servicio:

- existencia/coherencia de la referencia;
- permiso y actor;
- motivo permitido por operación;
- política de salida;
- relación entre corrección y movimiento original;
- idempotency key esperada para hechos automáticos.

### 6.4 Inmutabilidad

- no exponer ModelViewSet con update o destroy;
- API de movimientos sólo `list/retrieve/create` mediante commands permitidos;
- no permitir edición por Django admin; listado read-only, sin delete;
- corregir con delta compensatorio y `reverses_movement`;
- nunca cambiar actor, origen, delta, before/after o fecha;
- automatizaciones usan `actor_kind=SYSTEM` y origen explícito;
- operaciones humanas exigen actor autenticado.

Una protección de aplicación es necesaria; para mayor garantía se pueden
revocar UPDATE/DELETE al usuario DB de runtime o añadir trigger. No se debe
afirmar inmutabilidad fuerte si sólo se ocultan botones.

### 6.5 Auditoría semántica

`HistoricalRecords` y `Auditoria` no alcanzan:

- describen snapshots técnicos, no recepción/venta/ajuste/corrección;
- no exigen motivo, referencia ni idempotencia;
- la señal genérica atrapa errores de auditoría y deja continuar la operación;
- el actor depende de thread-local; automatizaciones quedan con actor nulo;
- no prueban que cada cambio de saldo tenga un hecho.

`MovimientoStock` es la auditoría semántica. Como eventos secundarios basta con
uno por command relevante —por ejemplo `STOCK_MOVEMENT_CREATED` con subtipo—;
no hace falta duplicar cada fila en cuatro eventos casi idénticos. Como mínimo
debe conservar producto, delta, origen, actor, before/after, reason y timestamp.

---

## 7. Commands de inventario

### 7.1 Primitiva interna

```text
apply_stock_delta(
    product_id,
    delta,
    movement_type,
    reason_code,
    actor,
    reference,
    idempotency_key,
    note=None,
)
```

Secuencia obligatoria:

```text
transaction.atomic
  → select_for_update Producto
  → buscar idempotency_key
  → si ya existe, devolver el mismo resultado
  → calcular before/after
  → validar after >= 0 y demás invariantes
  → crear MovimientoStock
  → actualizar Producto.stock_real = after
  → emitir auditoría/evento con transaction.on_commit si es externo
commit
```

Para varios productos se bloquean todos por ID ascendente antes de validar
cualquiera. Se valida el conjunto completo y luego se escribe; no se permiten
efectos parciales.

### 7.2 Ajuste manual

```text
adjust_stock(product, delta, reason_code, actor, idempotency_key, note=None)
```

- requiere `gestion.manage_stock`;
- `delta` no puede ser cero;
- razón estructurada obligatoria;
- nota opcional y limitada;
- no acepta `stock_after` elegido por el cliente.

Una UI de conteo puede ofrecer “saldo contado = X”, pero el command backend
bloquea el producto, vuelve a leer el saldo y registra `delta = X - current`.
Nunca hace un `PATCH stock_real=X` sin movimiento.

### 7.3 Entrada mínima

```text
receive_stock(product, quantity, reason_code, actor, idempotency_key, note=None)
```

- requiere `manage_stock`;
- cantidad estrictamente positiva;
- genera `RECEIPT_IN`;
- no exige ni inventa proveedor, orden de compra, costo, lote o factura.

Esta operación mínima sí es necesaria: de otro modo no existe forma legítima de
reponer productos. El botón actual “Reabastecer” puede abrirla sólo para quien
tenga capability; hoy el botón no ejecuta nada.

### 7.4 Corrección

No se actualiza ni borra la fila equivocada. Se crea `CORRECTION` con delta
opuesto o correctivo, referencia al movimiento original, razón y una nueva key.
Reintentar la misma corrección devuelve el mismo movimiento.

### 7.5 Devoluciones

No hay evidencia de devolución de Cliente, devolución a proveedor ni refund
ligado a mercadería. No se implementa `return_stock` ni se presupone que un
refund financiero repone unidades: la mercadería puede no haber vuelto o no ser
vendible. Es un backlog nuevo con decisión operativa.

---

## 8. Concurrencia e idempotencia

### 8.1 Escenarios

| Escenario | Resultado requerido |
|---|---|
| Dos salidas sobre una unidad | Una confirma; la otra falla sin movimiento ni estado de orden aplicado. |
| Entrada + salida | Se serializan por lock del Producto; el orden de commits define saldos trazables. |
| Devolución futura + consumo futuro | Mismo patrón; no se implementan hasta tener dominio. |
| Saldo llega exactamente a cero | Permitido; movimiento after=0. |
| Saldo quedaría negativo | Rechazo de todo el command; nunca clamp. |
| Doble click en ajuste/recepción | Misma key devuelve mismo movimiento. |
| Webhook repetido | Una salida por orden/producto/versión de efecto. |
| Dos workers procesan la misma orden | Locks + unique keys; uno crea, el otro observa el resultado. |
| Corrección reintentada | Una sola compensación. |

### 8.2 Claves

- humana: UUID generado por UI y persistido durante retry;
- recepción: `stock-receipt:{uuid}`;
- ajuste: `stock-adjustment:{uuid}`;
- venta: `order:{order_id}:inventory:v1:product:{product_id}` tras consolidar
  cantidades repetidas del mismo producto;
- opening: `opening-balance:{migration_id}:product:{product_id}`.

La key de venta no debe venir del webhook. La deriva el core de su propia Orden.
Una constraint unique es la última defensa; consultar primero no basta ante una
carrera.

---

## 9. `OrdenCompra`, pedidos y reservas

### 9.1 Semántica probada

`OrdenCompra` representa una venta/pedido **al Cliente**:

- FK obligatoria a `Cliente`, related name `ordenes_compra`;
- items referencian `Producto` y guardan `precio_historico`;
- nace desde el carrito del Cliente;
- la UI Cliente muestra “Mis Pedidos”;
- el ViewSet dice expresamente “pedidos efectuados por clientes”;
- el webhook reduce stock al aprobar;
- los reportes lo cuentan como ingresos y productos vendidos.

Por tanto:

- pago/entrega puede producir `ORDER_SALE_OUT`;
- nunca produce `PURCHASE_IN`;
- una compra del salón a proveedor necesita otro nombre y otro dominio futuro.

### 9.2 Duplicación actual

Hay tres caminos incompatibles:

1. `finalizar_compra`: crea `OrdenCompra(PENDIENTE)` y compromete stock;
2. checkout MP: crea `OrdenCompra(ESPERANDO_PAGO)` sin comprometer stock;
3. intención WhatsApp: crea `OrdenPendiente(PENDIENTE)` con JSON y compromete.

Luego webhook, confirmar pago y confirmar entrega pueden descontar por momentos
distintos. No existe campo que diga “inventario ya aplicado”. Cancelar sólo
acepta `PENDIENTE`, aunque MP nace `ESPERANDO_PAGO`.

### 9.3 Contrato objetivo

El reconciliador de C no muta Producto. Ante el hecho interno de pago de una
orden de productos invoca:

```text
ORDER_PAYMENT_COMPLETED
  → apply_order_inventory_effect(order_id)
```

El command:

- bloquea Orden y todos los Productos por orden estable;
- verifica el estado interno reconciliado, no el payload del provider;
- consolida items por producto;
- verifica/consume compromisos activos;
- crea una salida idempotente por producto;
- marca el efecto de inventario aplicado sólo dentro de la misma transacción;
- no comparte ninguna función con confirmación de un Turno de booking.

La decisión de descontar al pago o a la entrega es de negocio. Con el flujo
actual, que ya descuenta al aprobar MP y llama `COMPLETADO` a la venta, el primer
incremento debe conservar **pago reconciliado = salida física/comercial** para
no cambiar además fulfillment. Si el negocio necesita despacho posterior,
deberá separar `PAID` de `DELIVERED` en otro incremento y escoger allí el hecho
físico exacto.

### 9.4 Reserva de productos

Aquí sí existe evidencia de una reserva real: `stock_comprometido`, los flujos
WhatsApp y el tiempo entre checkout y pago. No tiene relación con agenda.

Recomendación:

- modelar un `CompromisoStock`/`ReservaStockOrden` ligado a Orden, Producto y
  cantidad, con estados `ACTIVE`, `CONSUMED`, `RELEASED`, expiración y key;
- materializar su suma activa en `Producto.stock_comprometido`;
- crear la reserva bajo locks al abrir un checkout que deba garantizar unidades;
- consumirla al aplicar la venta; liberarla al cancelar/expirar/rechazar;
- no crear `MovimientoStock` al reservar o liberar porque `stock_real` no cambia;
- una reserva activa satisface `ACTIVE AND expires_at > now`; las vencidas se
  liberan idempotentemente.

Si producto/checkout decide explícitamente no garantizar unidades antes del
pago, debe eliminarse `stock_comprometido` de ese flujo y definirse qué ocurre
si llega un pago sin existencia. Mantener ambos comportamientos no es válido.

### 9.5 `OrdenPendiente`

BH-058 CORE debe hacer que cualquier ruta que siga habilitada delegue en los
mismos commands y permisos para no corromper stock. Retirar el modelo/rutas
duplicados y migrar estados es BH-059. No es aceptable esperar a BH-059 para
eliminar sus escrituras directas.

---

## 10. Productos internos, Servicios y consumo

### 10.1 Producto vendible vs insumo

`Producto` no distingue:

- venta al Cliente;
- insumo de salón;
- ambos.

Sus campos (`precio`, publicación, imágenes, compatibilidad, carrito) están
orientados principalmente a venta. No hay unidad de medida, costo, lote,
merma, uso interno ni ubicación. Tratar todos los Productos como consumibles de
Servicio descontaría mercadería sin base.

La clasificación `SELLABLE`, `INTERNAL_SUPPLY` o `BOTH`, unidades y reglas de
conversión pertenecen a **BACKLOG NUEVO**, no al core inicial de BH-058.

### 10.2 Fórmulas no son recetas

- `Servicio.plantilla_formula` es texto libre;
- `FichaTecnica.formula` es texto libre del resultado técnico;
- no hay FK Servicio → Producto → cantidad/unidad;
- no hay consumo estándar ni consumo real por ejecución;
- no hay historial de ingredientes estructurado.

Por tanto BH-058 **no implementa `SERVICE_CONSUMPTION`** y nunca parsea texto
para descontar stock.

### 10.3 Momento futuro de consumo

Cuando exista receta y captura real, no se recomienda consumir al confirmar un
Turno: confirmación es intención, no uso. Tampoco se debe reservar inventario al
confirmar un Turno con el dominio actual.

La opción más fiel sería registrar consumo real al finalizar el Servicio o
manualmente durante su ejecución, permitiendo cantidades efectivamente usadas.
Esto requiere diseño separado. Un PROFESIONAL no obtiene `manage_stock` por su
skill técnica; podría recibir un command y permiso específico de consumo cuando
el caso exista.

```text
SlotHold/Turno de agenda != reserva de stock
```

---

## 11. Permisos efectivos

### 11.1 Semántica objetivo

| Permiso | Autoriza | No autoriza |
|---|---|---|
| `gestion.view_stock` | Cantidades internas, mínimos y movimientos de inventario. | Ajustar, recibir, cambiar catálogo/precios/promos o ver finanzas. |
| `gestion.manage_stock` | Commands de recepción, ajuste y corrección manual. | Editar catálogo/precio/promo; no es necesario para el efecto automático de una venta válida. |
| `gestion.manage_products` | Nombre, SKU, categoría, imágenes, publicación y atributos de catálogo. | Cambiar precio o saldo. |
| `gestion.manage_prices` | Precio base de Producto y Servicio. | Catálogo, stock o promociones. |
| `gestion.manage_promotions` | Reglas, vigencia y descuento promocional. | Precio base o stock físico. |
| `gestion.view_financial_reports` | Ingresos, ticket, pagos y métricas monetarias. | Stock o ajuste. |
| `gestion.view_reports` | Reportes no financieros generales existentes según contrato. | No debe implicar finanzas ni inventario automáticamente. |

No hay implicaciones automáticas entre ellos. Si una request cambia campos de
varios dominios, requiere todos los permisos correspondientes o se rechaza.

### 11.2 Situación actual

| Superficie | Control actual | Deuda |
|---|---|---|
| Producto list/retrieve/stock bajo | `AllowAny` | Expone cantidades internas; ignora `view_stock`. |
| Producto create/update/delete | `IsAdminUser` | Ignora `manage_products`, `manage_prices`, `manage_stock`. |
| Categoría Producto | `AllowAny` para CRUD | Ignora `manage_products`, incluso para escritura anónima. |
| Servicio create/update/delete | `IsAdminUser` | `precio_base` ignora `manage_prices`; catálogo de Servicio tampoco tiene capability dedicado. |
| Promoción mutaciones | `IsAdminUser` y checks `is_staff` | Ignora `manage_promotions`. |
| Órdenes/efectos de stock | `IsAuthenticated`; algunas acciones `is_staff` sólo para pagos | Clientes pueden activar efectos de stock; ignora commands y permisos. |
| Stats/reportes | `IsAdminUser` | Ignora `view_reports` y `view_financial_reports`. |
| Frontend Productos | navegación exige rol textual ADMIN además de `view_stock/manage_products`; ruta directa sólo autenticación | Un EMPLEADO con `view_stock` no obtiene UI; un admin ve todos los botones sin separar capabilities. |
| Frontend Reportes | route acepta `view_reports` o financiero; navegación además exige ADMIN | Backend luego exige staff y el payload siempre contiene finanzas. |
| Django admin | permisos Django de modelo | No distingue stock, precio y catálogo por campo. |

El backend debe consultar `request.user.has_perm(...)`. `BusinessRole` sólo
otorga defaults; `Personal.rol` es descripción legacy/técnica; `is_staff` sólo
habilita Django admin y no es autoridad de negocio.

### 11.3 Matriz de roles y actor sistema

“Individual” significa un permiso efectivo otorgado directamente, sin cambiar
el rol base.

| Operación | CLIENTE base | EMPLEADO base | PROFESIONAL base | ADMINISTRADOR base | Permiso individual | SISTEMA |
|---|---:|---:|---:|---:|---|---|
| Ver stock interno/movimientos | No | Sí (`view_stock`) | Sí, heredado de empleado | Sí | Sí, con `view_stock` | Lectura técnica necesaria |
| Ajustar stock | No | No | No | Sí | Sí, con `manage_stock` | No “ajuste humano”; sólo command automático tipado |
| Registrar entrada | No | No | No | Sí | Sí, con `manage_stock` | Sólo import/bootstrap explícito |
| Registrar devolución | No implementado | No implementado | No implementado | No implementado | Futuro permiso/command | Sólo tras hecho de dominio futuro |
| Modificar catálogo Producto | No | No | No | Sí | Sí, con `manage_products` | Seed explícito, no automatización incidental |
| Cambiar precio base | No | No | No | Sí | Sí, con `manage_prices` | Migración/config explícita |
| Gestionar promociones | No | No | No | Sí | Sí, con `manage_promotions` | Generar sugerencia no equivale a publicarla |
| Ver reporte de inventario v1 | No | Sí, por `view_stock` | Sí, por `view_stock` | Sí | Sí, con `view_stock` | Reconciliación/monitoring |
| Ver reporte financiero | No | No | No | Sí | Sí, con `view_financial_reports` | Jobs autorizados, sin exposición UI |
| Aplicar salida por venta válida | No como permiso manual | No como permiso manual | No como permiso manual | No como permiso manual | N/A | Sí, por transición interna idempotente |

Se confirma la propuesta:

- EMPLEADO recibe `view_stock`, no `manage_stock`;
- un empleado concreto puede recibir `manage_stock` individual;
- PROFESIONAL no recibe `manage_stock` por realizar Servicios;
- ADMINISTRADOR recibe los permisos administrativos como defaults, pero cada
  endpoint valida el permiso concreto;
- SISTEMA actúa por commands de dominio, no fingiendo ser administrador.

---

## 12. CRUD, frontend y privacidad

### 12.1 Producto y edición directa

`ProductoSerializer` declara read-only `stock_comprometido` y
`stock_disponible`, pero permite `stock_real`, `stock_minimo` y `precio`.
`GestionProductos` envía `stock_real`, `stock_minimo` y `precio` juntos tanto al
crear como al editar. `ProductoAdmin` también permite los tres.

Objetivo:

- CRUD Producto normal: `stock_real`, `stock_comprometido` y
  `stock_disponible` siempre read-only;
- `stock_minimo`: command/config de inventario con `manage_stock`;
- `precio`: endpoint/field command con `manage_prices`;
- campos de catálogo: `manage_products`;
- creación con saldo inicial: Producto se crea en cero y luego recepción/opening
  explícita; no se esconde un alta de stock dentro del POST de catálogo.

El admin debe aplicar la misma separación: saldo read-only y acciones/links a
commands; precio editable sólo con `manage_prices`; catálogo sólo con
`manage_products`.

### 12.2 UI mínima por capability

- `view_stock`: tabla de saldo/disponible/mínimo y movimientos, sin botones;
- `manage_stock`: botones “Recibir”, “Ajustar” y “Corregir” con razón/key;
- `manage_products`: alta/edición/desactivación de catálogo e imágenes;
- `manage_prices`: edición de precio separada;
- `manage_promotions`: pestaña de promociones y publicación/rechazo;
- cada control consulta capabilities de sesión, nunca texto de rol;
- ocultar botones mejora UX, pero backend sigue siendo autoridad.

La ruta `/admin/productos` actualmente sólo exige autenticación, aunque el menú
usa rol ADMIN + algunos permisos. Debe protegerse por capacidades y la pantalla
debe tolerar combinaciones parciales. No se debe usar una página monolítica que
obligue a conceder todos los permisos para ver uno.

### 12.3 Privacidad comercial

El endpoint público devuelve `stock_real`, `stock_comprometido`,
`stock_minimo`, `stock_disponible` y precio. El Cliente usa cantidades exactas
para el catálogo. Un Cliente no tiene `view_stock`; esto contradice la semántica
del permiso.

Separar serializers:

- público/Cliente: datos de catálogo, precio de venta y una disponibilidad
  comercial mínima (`available`, y opcionalmente máximo comprable si el negocio
  decide mostrarlo);
- personal con `view_stock`: cantidades internas y umbral;
- nunca exponer costos/proveedores futuros por el serializer público.

Stock no es dato clínico, pero sí información comercial.

---

## 13. Precios y promociones

### 13.1 Precios

- `Producto.precio` y `Servicio.precio_base` son mutables desde APIs protegidas
  sólo por `IsAdminUser` y desde Django admin;
- `GestionProductos` y `GestionarServicios` muestran inputs de precio sin
  capability;
- `manage_prices` existe y sólo está aplicado como default de rol, no en los
  endpoints;
- `OrdenItem.precio_historico` sí conserva snapshot al crear la orden;
- detalles de Turno también conservan precio histórico según el flujo B.

`manage_products` no implica cambiar precio. Una edición combinada debe exigir
`manage_products` por catálogo y `manage_prices` por `precio`, o dividirse en
commands separados.

### 13.2 Promociones

Las promociones relacionan Productos/Servicios y tienen descuento y
`stock_combo`, pero:

- la API de mutación usa staff, no `manage_promotions`;
- un signal genera sugerencias al crear Producto con stock suficiente;
- `stock_combo` es un snapshot, no reserva ni ledger;
- el catálogo calcula el precio descontado **sólo en frontend**;
- agregar un combo agrega Productos individualmente al carrito;
- carrito y Orden snapshottean el precio base completo, no el descuento.

Por ello una promoción hoy no cambia stock de forma propia y su descuento
mostrado no es autoridad financiera. BH-058 sólo debe impedir que
`stock_combo` se trate como saldo físico y aplicar `manage_promotions`. El motor
de promociones, elegibilidad y snapshot financiero coherente es BACKLOG NUEVO
y debe integrarse con los snapshots definidos en B; no se rediseña aquí.

---

## 14. Reportes y alertas

### 14.1 Estado actual

`DashboardStatsViewSet` devuelve en un mismo payload:

- total de ingresos y ticket promedio;
- cantidad de órdenes y cliente del mes;
- productos vendidos;
- rutinas frecuentes.

No informa saldo, mínimos ni movimientos. La sección llamada “Ingresos por
Servicio” agrega realmente `OrdenItem.producto`, no Servicios. Backend exige
`IsAdminUser`; frontend permite entrar con `view_reports` o
`view_financial_reports`, pero el menú además filtra por ADMINISTRADOR.

### 14.2 Separación objetivo

- saldo, bajos y ledger: `view_stock`;
- ajustar/recibir: `manage_stock`;
- ingresos, ticket, pagos, importes: `view_financial_reports`;
- métricas no financieras generales: `view_reports` según contrato explícito;
- una respuesta autorizada sólo con `view_reports` no puede incluir importes.

No hace falta `view_inventory_reports` en v1. `view_stock` alcanza para lectura
de saldo y movimientos. Crear otro permiso sólo se justifica si aparece una
audiencia que pueda ver agregados de inventario pero no las cantidades base, o
viceversa. Valuación/costos futuros serían además financieros.

### 14.3 Reporte mínimo de inventario

Para v1:

- saldo real, comprometido, disponible y mínimo por Producto;
- filtro de bajo stock con una sola fórmula autoritativa;
- lista paginada de `MovimientoStock` por producto, tipo, fecha, actor y origen;
- reconciliación administrativa: proyección vs suma de ledger;
- sin costo, margen, proveedor ni lote.

---

## 15. Migración y bootstrap

### 15.1 Elección para el entorno auditado

Como la base configurada tiene cero Productos/órdenes, se recomienda la opción
**B: empezar ledger limpio**, sin crear filas `OPENING_BALANCE` de valor cero.
Datos demo se cargan después y cada entrada usa bootstrap/recepción explícita.

### 15.2 Otros entornos

La migración debe hacer preflight:

1. contar Productos y órdenes activas;
2. detectar mínimos negativos y `comprometido > real`;
3. listar reservas que no se puedan atribuir a una orden;
4. si existen saldos que deben preservarse, crear un único `OPENING_BALANCE` por
   Producto con `delta=stock_real`, actor sistema, reason `LEGACY_MIGRATION` y
   key determinista;
5. marcar expresamente que no es compra ni recepción histórica;
6. reconstruir o resetear compromisos sólo mediante decisión operativa
   documentada;
7. verificar suma de ledger = proyección antes de habilitar writers nuevos.

No se debe inventar una secuencia histórica de ventas/entradas a partir del
saldo actual. Tampoco se debe resetear silenciosamente un entorno no vacío.

### 15.3 Bootstrap

Separar:

- **estructura**: permisos, grupos, reason codes y configuración necesaria;
- **demo/dev**: categorías, productos, precios y entradas demo;
- **datos reales**: nunca en migración de schema ni mezclados con demo.

Un seed de Producto crea catálogo en cero. Un segundo paso idempotente genera
`OPENING_BALANCE`/`RECEIPT_IN` demo. No se implementa en este análisis.

---

## 16. Matriz de tests requerida

### 16.1 Permisos backend

- `view_stock` permite cantidades/movimientos y no mutaciones;
- `manage_stock` permite ajuste/entrada sin implicar catálogo/precio;
- `manage_products` no cambia precio ni stock;
- `manage_prices` cambia precios sin gestionar catálogo;
- `manage_promotions` controla promociones;
- permisos individuales funcionan para EMPLEADO/PROFESIONAL;
- `is_staff=True` sin permiso concreto recibe 403 en APIs de negocio;
- un usuario con rol textual ADMINISTRADOR pero sin permiso efectivo (grupo
  ajustado en el test) no pasa;
- Cliente público no recibe cantidades internas;
- categorías no aceptan escritura anónima.

### 16.2 Movimientos

- recepción positiva;
- salida hasta cero;
- salida insuficiente sin efectos;
- ajuste positivo/negativo con razón;
- delta cero rechazado;
- corrección compensatoria;
- misma key retorna el mismo movimiento;
- key reutilizada con payload distinto produce conflicto;
- update/delete de movimiento rechazados;
- actor humano obligatorio;
- suma de movimientos coincide con proyección.

### 16.3 Concurrencia

Usar `TransactionTestCase` y una base que soporte row locks reales:

- dos salidas simultáneas;
- entrada contra salida;
- ajuste contra venta;
- dos reservas del último saldo;
- aplicación de venta contra liberación de la misma reserva;
- dos workers aplicando la misma Orden;
- orden multítem sin efectos parciales y sin deadlock por orden de locks.

### 16.4 Órdenes/MP

- efecto de Orden una sola vez;
- webhook/evento repetido no duplica salida;
- aprobar y confirmar entrega no descuentan dos veces;
- rechazo/cancelación libera una sola reserva;
- una orden sin reserva sigue la política legacy explícita;
- booking Mercado Pago confirma Turno y **nunca** crea movimiento de stock;
- un Cliente no puede llamar commands administrativos de inventario.

### 16.5 Frontend

- tabla visible con `view_stock` aunque el rol no sea ADMIN;
- botones por capability independiente;
- precio oculto/read-only sin `manage_prices`;
- catálogo sin edición sin `manage_products`;
- promociones sin controles sin `manage_promotions`;
- acceso por URL conserva guardas;
- errores 403/409 no se presentan como éxito;
- serializer público no rompe catálogo y filtra campos internos antes de llegar
  al browser.

Hoy no se encontraron tests backend específicos de Producto/stock/órdenes ni
tests frontend de `GestionProductos`; el Cypress de combos sólo llena
`stock_real` directamente y perpetúa el contrato a retirar.

---

## 17. Alcance por backlog

| Hallazgo/entrega | Clasificación | Justificación |
|---|---|---|
| `MovimientoStock`, proyección, constraints, inmutabilidad y reconciliación | **BH-058 CORE** | Integridad central de stock. |
| Commands de recepción/ajuste/corrección y retiro de PATCH directo | **BH-058 CORE** | Sin ellos no existe escritura legítima. |
| Locks, no negativos e idempotency keys | **BH-058 CORE** | Consistencia obligatoria. |
| Efecto único de `OrdenCompra` desde pago interno reconciliado | **BH-058 CORE** | Frontera expresamente dejada por C. |
| Reservas estructuradas de pedidos de productos si el checkout garantiza unidades | **BH-058 CORE** | `stock_comprometido` ya existe y afecta disponibilidad/pago. |
| Hacer que rutas legacy deleguen en commands y permisos | **BH-058 CORE** | No pueden seguir corrompiendo stock. |
| Retirar `OrdenPendiente`, rutas duplicadas y normalizar estados legacy | **BH-059** | Limpieza/migración de contratos legacy; no se implementa aquí. |
| Permisos efectivos específicos en stock/producto/precio/promo/reportes y UI correspondiente | **BH-058 CORE** | Autorización solicitada; no se difiere. |
| Eliminar otros `is_staff` ajenos a estas superficies | **BH-062** | Normalización global legacy. |
| Limpieza general de navegación `allowedRoles` fuera de estas pantallas y UI ampliada de auditoría | **BH-061** | Sólo la navegación de stock/reportes afectada es core aquí. |
| Infraestructura general para PostgreSQL concurrente/E2E estable | **BH-060** | Los tests funcionales de este dominio siguen siendo core; arreglar el harness global no. |
| Rutas legacy administrativas no relacionadas | **BH-059** | Fuera del dominio de stock. |
| Proveedores, compras del salón, facturas, costos, lotes y ubicaciones | **BACKLOG NUEVO** | No existen en el repo. |
| Producto vendible vs insumo y unidades | **BACKLOG NUEVO** | Prerrequisito para consumo técnico. |
| Receta Servicio→Producto→cantidad y consumo real | **BACKLOG NUEVO** | No hay relación estructurada. |
| Devoluciones de Cliente/proveedor y vínculo con refunds | **BACKLOG NUEVO** | No existe contrato. |
| Motor de promociones y snapshots de descuento | **BACKLOG NUEVO** | UI y backend hoy discrepan; no rediseñar en D. |
| Permiso `view_inventory_reports` | **BACKLOG NUEVO sólo si aparece necesidad** | `view_stock` alcanza para v1. |

---

## 18. Riesgos priorizados

| Prioridad | Riesgo | Impacto |
|---|---|---|
| Crítica | Acciones de órdenes mutan inventario con sólo autenticación | Un Cliente puede afectar stock de sus órdenes. |
| Crítica | Writers concurrentes sin lock | Oversell, saldos perdidos y doble aplicación. |
| Crítica | Webhook y entrega pueden aplicar la misma venta | Doble salida o estados incompatibles. |
| Alta | `max(0, ...)` oculta faltantes | Inventario y ventas parecen válidos aunque no lo sean. |
| Alta | No hay ledger/origen/idempotencia | No se puede explicar ni reconstruir saldo. |
| Alta | Checkout MP no reserva y WhatsApp sí | Disponibilidad depende del canal. |
| Alta | CRUD público de categorías | Alteración anónima del catálogo. |
| Alta | Serializer público revela inventario interno | Fuga comercial y permiso `view_stock` inútil. |
| Alta | Precio/stock/catálogo bajo staff | Permisos de negocio no tienen efecto. |
| Media | Alerta usa fórmula errónea; otro componente usa campo inexistente | Reposición incorrecta/UI rota. |
| Media | `stock_combo` queda obsoleto | Promesa comercial sin respaldo. |
| Media | Reporte mezcla finanzas y operaciones | Exposición indebida o denegación a usuarios autorizados. |
| Media | Auditoría genérica puede fallar sin abortar | Falsa expectativa de trazabilidad. |
| Media | Cero tests de stock | Regresiones invisibles. |

---

# Decisiones finales solicitadas

## 1. Inventario actual

`Producto` concentra catálogo, precio, `stock_real`, `stock_comprometido` y
`stock_minimo`. El disponible es una property con clamp. No existen movimientos,
proveedores, recepciones, ajustes semánticos, devoluciones ni recetas. La base
auditada está vacía. Lecturas y alertas usan fórmulas distintas.

## 2. Autoridad de stock

Hoy es una mezcla, dominada por `stock_real` como autoridad directa y
`stock_comprometido` como proyección no explicable. Futuro: `MovimientoStock`
es el hecho autoritativo y `Producto.stock_real` una proyección materializada
controlada y reconciliable. El saldo no puede ser negativo.

## 3. Todos los escritores

Escriben directamente: CRUD Producto, Django admin, finalizar compra, registrar
intención WhatsApp, webhook MP de Orden, confirmar pago/entrega/cancelar en
`OrdenPendiente` y confirmar entrega/cancelar en `OrdenCompra`. No hay writers
en signals, commands, scripts o fixtures. Ningún camino bloquea Producto; la
tabla exhaustiva está en la sección 4.

## 4. Modelo `MovimientoStock`

Inmutable, delta signed no cero, Producto obligatorio, tipo, reason, nota,
actor humano/sistema, origen, key unique, before/after y corrección compensatoria.
Tipos v1: opening, recepción, salida por Orden, ajuste y corrección. No incluir
consumo de Servicio, devolución ni compra a proveedor sin dominio.

## 5. Relación con `OrdenCompra`

Es venta al Cliente. Pago reconciliado emite un command interno idempotente que
aplica una sola salida bajo locks; el webhook no toca Producto. Reservas de
pedidos, si se garantiza stock durante pago, necesitan hechos estructurados y
una proyección comprometida. `OrdenPendiente` debe delegar ahora y retirarse en
BH-059.

## 6. Relación con Servicios

No existe Servicio→Producto→cantidad. Las fórmulas son texto. No descontar ni
reservar stock por Turno. El futuro consumo debe reflejar uso real al finalizar
o durante ejecución y requiere otro backlog.

## 7. Permisos

`view_stock`, `manage_stock`, `manage_products`, `manage_prices`,
`manage_promotions` y `view_financial_reports` son independientes. El backend
verifica `has_perm`; no usa `is_staff`, BusinessRole ni `Personal.rol` como
autoridad. El sistema aplica ventas por transición de dominio, no por permiso
humano.

## 8. Matriz de roles

EMPLEADO y PROFESIONAL reciben lectura de stock, no gestión. ADMIN recibe todos
como defaults. Un usuario concreto puede recibir permisos individuales.
CLIENTE sólo ve disponibilidad comercial, no inventario interno. PROFESIONAL no
gana stock por skills. La matriz completa está en 11.3.

## 9. Concurrencia/idempotencia

Transacción, locks de Productos en orden estable, validación de conjunto,
movimiento, actualización de proyección y commit. Nunca `stock -= cantidad` sin
lock ni clamp. Unique key por hecho; retries devuelven el mismo resultado.

## 10. Reportes/precios/promos

`view_stock` cubre saldo y movimientos v1; finanzas requieren
`view_financial_reports`. Precio base requiere `manage_prices`; catálogo no lo
implica. Promociones requieren `manage_promotions`, no cambian stock y hoy su
descuento frontend no llega al snapshot de Orden.

## 11. Migración/bootstrap

En la base vacía: ledger limpio, sin openings cero. En un entorno con saldo:
un `OPENING_BALANCE` explícito por Producto, no historia inventada. Estructura y
permisos se separan de datos demo; stock demo entra por seed idempotente de
movimientos.

## 12. Riesgos

Los principales son mutaciones por Clientes autenticados, carreras, doble
descuento, clamps, falta de ledger, reservas inconsistentes, fuga pública de
cantidades, permisos inefectivos y ausencia de tests.

## 13. Alcance BH-058 vs otros backlogs

BH-058 incluye autoridad, ledger, commands, locks, idempotencia, reservas de
pedidos, efecto de Orden y autorización específica. BH-059 retira duplicación
legacy; BH-060 mejora infraestructura de tests; BH-061 amplía auditoría/
navegación global; BH-062 normaliza `is_staff` ajeno. Proveedores, recetas,
insumos, devoluciones, costos y motor promocional son backlog nuevo.

## 14. Primer incremento recomendado

1. crear `MovimientoStock` y constraints de Producto;
2. implementar una única primitiva transaccional con locks e idempotencia;
3. agregar `receive_stock` y `adjust_stock` con `manage_stock`;
4. hacer saldo read-only en serializer/admin y separar `stock_minimo`;
5. implementar `apply_order_inventory_effect(order)` y enrutar **todos** los
   efectos actuales por él, sin rediseñar el webhook de C;
6. estructurar o deshabilitar la reserva inconsistente de pedidos antes de
   aceptar pagos concurrentes;
7. aplicar permisos efectivos y serializer público sin cantidades internas;
8. añadir tests de permisos, inmutabilidad, concurrencia, idempotencia y “booking
   nunca toca stock”.

Este incremento deja un inventario explicable y seguro sin abrir proveedores,
consumo por Servicio, devoluciones ni BH-059.
