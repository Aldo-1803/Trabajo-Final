# BH-058 F7 — Análisis de resolución de incidencias financieras

**Fecha:** 2026-10-29<br>
**Alcance:** análisis de dominio y propuesta; no incluye implementación, migraciones, tests ni frontend.

## 1. Conclusión ejecutiva

Bohemia Hair ya tiene contratos sólidos para registrar pagos, confirmar reservas,
conciliar Mercado Pago, conservar evidencia externa y proteger el stock. La
brecha no está en la detección: está en la **resolución posterior**.

`PaymentReconciliationCase` es el punto natural de entrada porque identifica la
incidencia, su contexto BOOKING u ORDER, los pagos y la evidencia de proveedor.
Sin embargo, hoy no constituye un workflow de resolución:

- sólo tiene `OPEN` y `RESOLVED`;
- es inmutable y no existe un servicio que lo resuelva;
- no registra solicitud, decisión, decisor, importe autorizado, ejecución de
  refund, confirmación externa ni resultado comercial;
- no hay bandeja o API operativa para revisarlo;
- C2b abre casos ante refund, refund parcial, contracargo o regresión, pero deja
  expresamente `NO_BUSINESS_EFFECT`;
- `Pago.REVERSED` existe, pero no hay transición semántica implementada que lo
  produzca y, por sí solo, no puede representar una reversión parcial.

El circuito mínimo seguro debe mantener cinco hechos diferentes:

```text
solicitud
  -> decisión humana autorizada
  -> ejecución de devolución, si fue aprobada
  -> confirmación externa del resultado financiero
  -> efecto comercial/stock y cierre verificable
```

Una solicitud, una aprobación y un envío de refund **no equivalen** a dinero
devuelto. Sólo una confirmación inequívoca del proveedor o del medio manual
autorizado puede crear el hecho financiero compensatorio. Un refund o
contracargo que se origine fuera del sistema puede llegar antes de una decisión
local; en ese caso se registra primero el hecho externo y se mantiene el caso
abierto hasta decidir sus efectos comerciales.

## 2. Fuentes y contratos inspeccionados

Se contrastaron estas fuentes obligatorias:

- `AUDITORIA_FINAL_BH058_SEGUNDA_PASADA.md`;
- `IMPLEMENTACION_BH058_B2_PAGO_MANUAL.md`;
- `IMPLEMENTACION_BH058_B3_ORQUESTACION_FINANCIERA.md`;
- `IMPLEMENTACION_BH058_C2B_CONCILIACION_EXTERNA.md`;
- `CORRECCION_BH058_F5_CANCELACION_ORDEN_PAGADA.md`;
- `CORRECCION_BH058_F6_CAJA_PRESENCIAL.md`.

También se inspeccionaron modelos, servicios, APIs y pruebas actuales de pagos,
Intents, conciliación externa, Turnos, órdenes, compromisos, auditoría y roles.

## 3. Inventario de contratos actuales

### 3.1 `Pago`

**Contrato reutilizable**

- Contexto exclusivo: `PaymentIntent` o `OrdenCompra`.
- Estados: `PENDING_RECONCILIATION`, `RECONCILED`, `REJECTED`, `REVERSED`.
- Identidad pública, moneda, importe, propósito, actor, timestamps, referencia,
  comprobante privado, clave idempotente y razón terminal.
- Para Mercado Pago conserva proveedor, pago oficial, Attempt, evento, fecha y
  snapshot sanitario.
- La identidad `(provider_code, provider_payment_id)` es única.
- Un Pago persistido no admite update/delete genérico. Las transiciones quedan
  reservadas a managers y servicios.
- B2 permite registrar CASH ya conciliado o evidencia manual pendiente; sólo
  `gestion.confirm_deposit` puede aceptar o rechazar esta última.
- La autoridad actual de cobro es la suma de pagos `RECONCILED`.

**Operaciones existentes**

- Registrar pago manual idempotente.
- Aceptar o rechazar evidencia manual pendiente.
- Crear un pago externo desde un evento verificado.
- Vincular pagos BOOKING con el Turno confirmado.

**Brechas**

- No existe servicio de refund/reversión.
- No hay referencia, importe ni fecha de devolución confirmada.
- `REVERSED` no distingue refund, refund parcial, contracargo o corrección.
- Marcar un Pago completo como `REVERSED` sería incorrecto ante una devolución
  parcial y no alcanza para varias compensaciones sobre el mismo pago.
- No existe una proyección canónica de cobrado bruto, ajustes confirmados y
  cobrado neto.

### 3.2 `PaymentIntent`

**Contrato reutilizable**

- Modos `DEPOSIT` y `FULL`.
- Estados `CREATED`, `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `CANCELLED`.
- Snapshot de obligación, importe requerido, total, moneda, vencimiento y HOLD.
- B3 es la única autoridad que aprueba el Intent y confirma un Turno cuando los
  pagos conciliados alcanzan el umbral.
- La cancelación por la clienta sólo admite Intents activos y sin pagos;
  `PAYMENT_EXISTS` impide usarla como falsa resolución financiera.

**Brechas**

- No tiene estado de refund, contracargo ni resolución posterior.
- Un Intent aprobado no debe degradarse a `CANCELLED` o `EXPIRED` para simular
  una devolución: esos estados describen el ciclo de la obligación original.
- La situación financiera posterior debe ser una proyección separada y
  trazable, no una reescritura del hecho histórico.

### 3.3 `PaymentReconciliationCase`

**Contrato reutilizable**

- Tipos: `LATE_PAYMENT`, `BOOKING_CONFIRMATION_FAILED`,
  `EXTERNAL_PAYMENT_REVIEW`, `ORDER_FULFILLMENT_FAILED` y
  `POST_PAYMENT_CHANGE`.
- Contexto exclusivo:
  - BOOKING: `PaymentIntent` + `SlotHold`;
  - ORDER: `OrdenCompra`.
- Puede relacionar Turno, Pagos, Attempt y ProviderEvent.
- `operation_key` único e idempotente.
- Casos y relaciones principales están protegidos contra escritura genérica.
- Constraints enlazan `OPEN` con `resolved_at = null` y `RESOLVED` con fecha.

**Operaciones existentes**

- B3 abre/reutiliza casos por pago tardío o fallo de confirmación.
- C2b abre/reutiliza casos por evidencia dudosa, orden no cumplible, cambios
  posteriores, refund o contracargo.

**Brechas**

- No existe servicio de solicitud, decisión o cierre.
- No existe responsable asignado, decisor, resolución, fundamento de política,
  importe solicitado/aprobado/confirmado ni referencia de refund.
- `details` es un snapshot de detección; no debe transformarse en workflow
  mutable ni en sustituto de campos financieros verificables.
- No existe endpoint/listado interno de casos. El frontend sólo proyecta
  `ADMIN_REVIEW` o `PAID_WITHOUT_BOOKING` dentro del tracking de un Intent.

### 3.4 `OrdenCompra`, compromisos y stock

**Contrato reutilizable**

- Estados: `PENDIENTE`, `ESPERANDO_PAGO`, `PAGADO`, `COMPLETADO`, `RECHAZADO`,
  `CANCELADO`.
- C2b mueve una orden consistente a `PAGADO` sin tocar stock.
- `CompromisoStock.ACTIVE` reserva unidades para una orden pagada.
- La entrega autorizada consume el compromiso, crea la salida física y lleva la
  orden a `COMPLETADO`.
- F5 bloquea la cancelación ordinaria de:
  - una orden `PAGADO`;
  - una orden con Pago `PENDING_RECONCILIATION` o `RECONCILED`;
  - una orden `COMPLETADO`.
- Una cancelación impaga válida libera el compromiso de forma idempotente.

**Brechas**

- No hay “solicitud de cancelación pagada” ni vínculo con una resolución.
- No existe transición post-refund que, bajo una única decisión confirmada,
  cancele la orden y libere un compromiso todavía `ACTIVE`.
- Una orden `COMPLETADO` ya tiene stock consumido. Su refund no puede fingir una
  cancelación ni reponer stock sin devolución física y un proceso de retorno.

### 3.5 Cancelación de `Turno`

**Contrato reutilizable**

- Las operaciones de titular y personal aplican ownership/permisos, estados
  cancelables e idempotencia.
- Registran actor, motivo y auditoría `TURN_CANCELLED`.
- El permiso global es `gestion.cancel_any_turno`.

**Brechas**

- La cancelación no inspecciona ni resuelve pagos.
- No abre un caso por seña o pago total ya acreditado.
- No define si corresponde devolución, retención, refund parcial o crédito.
- Cambiar el Turno a `CANCELADO` es un hecho comercial, no una constancia de que
  el dinero fue devuelto.

### 3.6 Conciliación externa

**Contrato reutilizable**

- C2a verifica y persiste evidencia oficial; C2b consume sólo snapshots
  verificados.
- La operación C2b es idempotente, provider-neutral en su dominio y conserva
  eventos, decisiones, efectos e identidades oficiales.
- Detecta refund total/parcial, contracargo y regresión mediante
  `POST_PAYMENT_CHANGE`.
- Ante cambios posteriores crea/reutiliza caso y responde
  `REVIEW_REQUIRED / NO_BUSINESS_EFFECT`.
- Nunca revierte automáticamente Pago, Intent, Turno, orden o stock.

**Brechas**

- C2b preserva snapshots de refunds y chargebacks, pero no materializa un hecho
  compensatorio canónico por importe.
- No correlaciona una devolución iniciada localmente con su resultado oficial.
- No distingue todavía entre refund confirmado, solicitado, fallido o de
  resultado desconocido.

### 3.7 Auditoría y permisos

**Contrato reutilizable**

- `Auditoria` conserva actor, fecha, tabla, acción y snapshots JSON.
- Los servicios financieros actuales emiten eventos semánticos, entre ellos
  registro/conciliación de Pago, confirmación BOOKING, conciliación externa y
  revisión requerida.
- Existe API de auditoría de sólo lectura, aunque actualmente usa
  `IsAdminUser`, no el permiso declarado `gestion.view_audit`.
- Permisos efectivos relevantes:
  - `gestion.register_payment`: registrar pagos manuales;
  - `gestion.confirm_deposit`: aceptar/rechazar evidencia manual;
  - `gestion.reconcile_external_payment`: revisión financiera externa;
  - `gestion.cancel_any_turno`: cancelar Turnos ajenos;
  - `gestion.manage_stock`: entrega, cancelación impaga y stock.
- C2b asigna `gestion.reconcile_external_payment` al grupo `ADMINISTRADOR` y no
  usa `is_staff`, nombres de rol ni `Personal.rol` como autoridad.

**Brechas y regla propuesta**

- `gestion.reconcile_external_payment` debe ser la autoridad mínima para
  decisiones de incidencias y cierre financiero.
- `is_staff`, un rol textual, `manage_stock`, `cancel_any_turno`,
  `confirm_deposit` o `register_payment` no deben conceder esa decisión.
- `Auditoria` complementa, pero no sustituye, entidades financieras con
  constraints, idempotencia e identidad externa.
- Cada etapa debe generar auditoría semántica con actor real; un worker se
  registra como autoridad de sistema, no como un administrador inventado.

## 4. Invariantes de F7

1. Un pago acreditado no desaparece ni se edita para ocultar su historia.
2. Solicitar un refund no significa aprobarlo.
3. Aprobar un refund no significa haberlo enviado.
4. Enviar un refund no significa que el proveedor lo haya completado.
5. Sólo un hecho confirmado modifica el neto financiero.
6. Un resultado de red desconocido no se reintenta con otra identidad: primero
   se consulta/reconcilia el proveedor con la misma clave idempotente.
7. Refund parcial y refund total son hechos diferentes.
8. Un contracargo confirmado es una reversión externa, no una devolución
   voluntaria ejecutada por Bohemia Hair.
9. Ningún caso se cierra con ejecución pendiente, desconocida o sin evidencia.
10. Una orden pagada no libera compromiso antes de la resolución financiera
    confirmada que autoriza su cancelación.
11. Una orden completada no repone stock por un evento financiero.
12. No se recrean HOLD, Turno u orden automáticamente a causa de un pago tardío.
13. No se decide automáticamente si una seña es reembolsable, si corresponde
    retención o quién soporta un contracargo sin política comercial/legal.
14. Dinero, estado comercial y stock se resuelven por autoridades distintas y
    sólo se coordinan mediante un servicio transaccional explícito.

## 5. Matriz de escenarios

### 5.1 Cancelación de Turno sin pago

| Aspecto | Análisis |
|---|---|
| Estado actual | La cancelación existente cambia el Turno a `CANCELADO`, registra actor/motivo y audita. Si existe un Intent activo sin pagos, su cancelación separada puede liberar el HOLD. |
| Resultado esperado | Mantener la cancelación ordinaria. No crear resolución financiera si se verifica que no hay Pago pendiente ni conciliado. Cancelar/liberar Intent/HOLD activo cuando corresponda mediante su servicio existente, no por update directo. |
| Autoridad | Titular bajo la política actual o actor con `gestion.cancel_any_turno`; la cancelación del Intent conserva ownership. |
| Dinero | Ningún efecto. No crear refund ni ajuste. |
| Turno/OrdenCompra | Turno `CANCELADO`; no aplica OrdenCompra. |
| Compromisos/stock | Sin efecto sobre stock de órdenes. El HOLD de agenda se libera por el contrato de Intent/HOLD, no como stock. |
| Trazabilidad | `TURN_CANCELLED` y, si aplica, auditoría de cancelación del Intent/HOLD. |
| Intervención humana | No adicional, salvo las reglas actuales de cancelación. |

### 5.2 Cancelación de Turno con seña acreditada

| Aspecto | Análisis |
|---|---|
| Estado actual | El Turno puede quedar `CANCELADO`, pero el Pago sigue `RECONCILED`; no se abre caso ni se resuelve la seña. |
| Resultado esperado | Ejecutar la cancelación comercial sólo si la política actual la permite y, en la misma operación lógica, abrir/reutilizar caso y registrar una **solicitud de resolución**. No asumir que la seña se devuelve ni se retiene. |
| Autoridad | Titular/`cancel_any_turno` solicita o cancela; sólo `reconcile_external_payment` decide refund, refund parcial o denegación con fundamento explícito. |
| Dinero | Sin cambio al solicitar. Si se aprueba devolución: ejecución idempotente y ajuste sólo tras confirmación. Si se deniega: no cambia el dinero y debe quedar razón/política. |
| Turno/OrdenCompra | El Turno puede permanecer `CANCELADO`; la resolución financiera no lo vuelve a confirmar. No aplica OrdenCompra. |
| Compromisos/stock | Sin efecto de inventario. No recrear HOLD. |
| Trazabilidad | Cancelación + caso + solicitud + decisión + operación + confirmación + cierre como eventos distintos. |
| Intervención humana | Obligatoria porque no existe política explícita de reembolsabilidad de señas. |

### 5.3 Cancelación de Turno totalmente pagado

| Aspecto | Análisis |
|---|---|
| Estado actual | Igual que con seña: la cancelación no resuelve el total acreditado. El Intent puede seguir `APPROVED`. |
| Resultado esperado | Abrir/reutilizar resolución por todo el saldo financiero afectado. La cancelación no equivale a refund. Permitir decisión total, parcial o denegada únicamente bajo política documentada. |
| Autoridad | Autoridad comercial actual para cancelar; `reconcile_external_payment` para decidir y cerrar el dinero. |
| Dinero | Pago original conservado. Ajuste compensatorio sólo por importe confirmado. El Intent histórico no se degrada para simular el refund. |
| Turno/OrdenCompra | Turno `CANCELADO` si la cancelación fue válida. No reactivar automáticamente ante fallo del refund. |
| Compromisos/stock | Sin efecto de inventario. |
| Trazabilidad | Debe mostrar importe original, solicitado, autorizado, ejecutado y confirmado, cada uno con actor/fecha. |
| Intervención humana | Obligatoria hasta que exista política explícita y validada para cancelaciones pagadas. |

### 5.4 HOLD vencido con pago posterior

| Aspecto | Análisis |
|---|---|
| Estado actual | B2/C2b conserva la evidencia como `PENDING_RECONCILIATION`, abre `LATE_PAYMENT` y no resucita HOLD, Intent ni Turno. La evidencia manual tardía tampoco puede aceptarse por el flujo ordinario. |
| Resultado esperado | Mantener el fail-closed actual. Un decisor elige, con contacto/evidencia, entre devolución u otra resolución permitida por política. La aplicación a una nueva reserva no forma parte del mínimo y nunca debe recrear disponibilidad automáticamente. |
| Autoridad | `reconcile_external_payment`; `confirm_deposit` no basta para decidir un pago tardío. |
| Dinero | Si el proveedor ya acreditó, conservar el hecho y devolver sólo mediante operación confirmada. Si la evidencia no está acreditada, puede rechazarse sin inventar refund. |
| Turno/OrdenCompra | No crear ni confirmar Turno. No modificar una orden. |
| Compromisos/stock | HOLD permanece vencido/liberado; sin stock. |
| Trazabilidad | Caso `LATE_PAYMENT`, evidencia original, decisión, contacto con clienta, operación y confirmación. |
| Intervención humana | Obligatoria por disponibilidad, consentimiento y política comercial. |

### 5.5 Orden `PAGADO` que no puede entregarse

| Aspecto | Análisis |
|---|---|
| Estado actual | Si C2b detecta la imposibilidad al acreditar, conserva Pago pendiente y abre `ORDER_FULFILLMENT_FAILED`. Si la imposibilidad aparece después de marcar `PAGADO`, no existe una operación general de resolución. F5 impide cancelar/liberar por la ruta ordinaria. |
| Resultado esperado | Abrir/reutilizar caso y solicitar resolución. Si se aprueba cancelación con refund total, conservar `PAGADO` y compromiso `ACTIVE` hasta confirmación; después, una transición post-resolución dedicada lleva a `CANCELADO`/`RECHAZADO` y libera una sola vez. Alternativas comerciales requieren política y aceptación, no automatización. |
| Autoridad | `reconcile_external_payment` decide dinero; el efecto de stock usa el servicio canónico bajo la resolución aprobada. `manage_stock` solo no puede decidir el refund. |
| Dinero | Ningún cambio por imposibilidad o solicitud. Refund sólo confirmado externamente. |
| Turno/OrdenCompra | Antes de confirmar: orden sin cambio. Después de refund total y cancelación aprobada: estado terminal no entregado. Un refund parcial no cancela toda la orden por defecto. |
| Compromisos/stock | `ACTIVE` mientras el dinero está sin resolver. Tras refund total confirmado y antes de entrega: `RELEASED`, sin movimiento físico. Si ya fue consumido, no liberar ni reponer. |
| Trazabilidad | Causa de incumplimiento, decisión, importe, proveedor, ajuste y transición de compromiso enlazados al mismo caso. |
| Intervención humana | Obligatoria para elegir refund, sustitución u otra salida y para validar la imposibilidad. |

### 5.6 Solicitud de cancelación de una orden `PAGADO`

| Aspecto | Análisis |
|---|---|
| Estado actual | F5 responde `ORDER_CANCELLATION_REQUIRES_FINANCIAL_RESOLUTION`; no cambia orden, Pago, compromiso, stock ni movimientos. No crea solicitud. |
| Resultado esperado | Preservar F5 y añadir una acción separada de **solicitud**, idempotente. La orden continúa `PAGADO` y reservada hasta decisión. Si se rechaza, continúa cumplible. Si se aprueba refund total, sólo se cancela/libera tras confirmación. |
| Autoridad | Titular o personal con alcance comercial puede solicitar; `reconcile_external_payment` decide. La ruta ordinaria protegida por F5 no se reabre. |
| Dinero | Sin cambio al solicitar o aprobar. Ajuste sólo al confirmar. |
| Turno/OrdenCompra | La solicitud no cambia la orden. El cierre aprobado y confirmado usa transición post-financiera dedicada. `COMPLETADO` queda fuera. |
| Compromisos/stock | Permanece `ACTIVE` hasta confirmación total. Luego puede liberarse atómicamente una vez. |
| Trazabilidad | Solicitante, motivo, estado de orden/pagos al solicitar, decisión, refund y liberación. |
| Intervención humana | Obligatoria mientras no exista política explícita de cancelación de ventas pagadas. |

### 5.7 Reembolso total o parcial confirmado por Mercado Pago

| Aspecto | Análisis |
|---|---|
| Estado actual | C2b detecta snapshots de refund y abre `POST_PAYMENT_CHANGE`; no revierte Pago ni aplica efectos comerciales. Las pruebas garantizan esa ausencia de reversión automática. |
| Resultado esperado | Materializar idempotentemente un ajuste confirmado por importe y moneda, enlazado al Pago y ProviderEvent. Correlacionarlo con una operación aprobada si existe; si fue externo/no solicitado, abrir o mantener revisión. Total y parcial deben proyectarse por separado. |
| Autoridad | C2a/C2b tiene autoridad de evidencia externa. Una persona con `reconcile_external_payment` decide los efectos comerciales y cierra; no puede negar la existencia del hecho confirmado. |
| Dinero | Disminuye el neto sólo por el importe confirmado. `Pago.REVERSED` puede ser una proyección terminal cuando el total acumulado confirmado iguale el Pago, pero no es el ledger ni se usa para un parcial. |
| Turno/OrdenCompra | No cancelar automáticamente. Aplicar el efecto ya autorizado: por ejemplo, una orden no entregada con refund total aprobado puede cancelarse. Un parcial conserva el objeto salvo decisión explícita. |
| Compromisos/stock | Sin efecto automático. Sólo el servicio post-resolución puede liberar un compromiso `ACTIVE`; nunca modificar uno `CONSUMED` por el refund. |
| Trazabilidad | ID de refund, pago origen, importe, snapshot sanitario, evento verificado, operación local correlacionada y diferencias. |
| Intervención humana | No es necesaria para reconocer el hecho financiero verificado; sí para efectos comerciales no decididos previamente o discrepancias. |

### 5.8 Contracargo

| Aspecto | Análisis |
|---|---|
| Estado actual | C2b detecta chargeback como `POST_PAYMENT_CHANGE`, abre revisión y no degrada el negocio confirmado. |
| Resultado esperado | Registrar el ajuste externo confirmado como `CHARGEBACK`, separado de `REFUND`. Mantener revisión para evidencia, disputa y efecto comercial. No presentarlo como refund ejecutado por Bohemia Hair. |
| Autoridad | Proveedor es autoridad del hecho; `reconcile_external_payment` acusa recibo, gestiona el caso y decide acciones permitidas. Disputa/legal requiere política y eventualmente autoridad adicional. |
| Dinero | Reduce el neto cuando está confirmado. Reversiones posteriores del contracargo deben ser otro hecho compensatorio, no editar el anterior. |
| Turno/OrdenCompra | No cancelar automáticamente un servicio prestado ni una orden entregada. Para una orden aún no entregada, el caso abierto debe impedir la entrega irreversible hasta revisión; no equivale a cancelarla. |
| Compromisos/stock | No reponer stock consumido. Un compromiso activo se conserva hasta decisión; su liberación exige resolución comercial. |
| Trazabilidad | ID y estado del contracargo, importe, fechas, evidencia, disputa, decisiones y resultado final. |
| Intervención humana | Obligatoria por riesgo comercial/legal. Sólo la ingestión del hecho es automática. |

### 5.9 Duplicación o discrepancia financiera

| Aspecto | Análisis |
|---|---|
| Estado actual | Las claves idempotentes y unicidad externa evitan duplicados exactos. C2b abre revisión por importe, obligación, sobrepago, identidad o estado inconsistente y evita efecto comercial. |
| Resultado esperado | Reutilizar la detección actual. Clasificar si es evento repetido, dos pagos reales, error de importe o evidencia insuficiente. Sólo un pago real excedente confirmado puede originar una decisión de refund; un evento duplicado técnico no genera devolución. |
| Autoridad | Sistema deduplica identidades exactas; `reconcile_external_payment` resuelve discrepancias semánticas. |
| Dinero | No cambiar ante duplicado técnico. Con dos cobros reales, conservar ambos hechos y compensar sólo el excedente confirmado que haya sido autorizado. |
| Turno/OrdenCompra | No duplicar Turno, aprobación, orden ni entrega. Mantener efecto comercial único. |
| Compromisos/stock | Sin movimientos por reconciliación. No duplicar consumo o liberación. |
| Trazabilidad | Identidades, fingerprints, snapshots, comparación de importes, decisión y ajuste correlacionado. |
| Intervención humana | No para deduplicación exacta; sí para dos cargos reales o evidencia contradictoria. |

## 6. Política mínima propuesta

### 6.1 Vocabulario obligatorio

| Etapa | Significado | Lo que no significa |
|---|---|---|
| Solicitud | Una persona o detector pide revisar una incidencia y propone un resultado. | No autoriza ni mueve dinero. |
| Decisión | Actor autorizado aprueba, rechaza o pide evidencia, indicando importe y fundamento. | No prueba ejecución ni confirmación. |
| Ejecución | Se envía una orden idempotente al proveedor/medio correspondiente. | Una respuesta aceptada o HTTP 2xx no prueba devolución final. |
| Confirmación externa | Evidencia verificada acredita refund, chargeback u otro ajuste por importe concreto. | No decide por sí sola el estado comercial o el stock. |
| Cierre | Se verifican decisión, dinero, efectos comerciales/stock y trazabilidad. | No puede usarse para ocultar un estado desconocido. |

### 6.2 Entidades mínimas

No conviene ampliar `details` ni convertir `Auditoria` en ledger. La propuesta
mínima es conservar `PaymentReconciliationCase` como sobre de incidencia y
agregar contratos explícitos:

1. **Resolución financiera** vinculada 1:1 al caso:
   - solicitud: tipo, resultado propuesto, importe/moneda, motivo, solicitante y
     fecha;
   - decisión: `APPROVE_REFUND`, `DENY_REFUND`,
     `ACKNOWLEDGE_EXTERNAL_ADJUSTMENT`, `NO_FINANCIAL_CHANGE` o
     `REQUIRE_MORE_EVIDENCE`;
   - importe autorizado, decisor, fecha, fundamento y referencia a política;
   - estado derivado del workflow, modificable sólo por servicios semánticos.
2. **Operación de devolución** para cada ejecución:
   - resolución y Pago de origen;
   - importe/moneda;
   - proveedor/medio;
   - clave idempotente estable;
   - estados `PENDING`, `SUBMITTED`, `CONFIRMED`, `FAILED`, `UNKNOWN`;
   - referencia externa y timestamps;
   - intentos/eventos sin sobrescribir evidencia anterior.
3. **Ajuste financiero confirmado**, inmutable:
   - tipo `REFUND`, `CHARGEBACK` o reversión/corrección explícitamente
     soportada;
   - Pago de origen, importe positivo, moneda y fecha efectiva;
   - ProviderEvent/identidad externa o evidencia manual autorizada;
   - operación local correlacionada, si existe;
   - clave única que impida contabilizar dos veces el mismo ajuste.
4. **Eventos de resolución append-only**:
   - etapa, actor/sistema, fecha, operation key y metadata sanitaria;
   - respaldo detallado de solicitud, decisión, ejecución, confirmación, efecto
     comercial y cierre.

El nombre concreto de los modelos puede variar. Lo obligatorio es no colapsar
las cuatro responsabilidades en un booleano `refunded` o en `RESOLVED`.

### 6.3 Proyecciones financieras

La lectura debe exponer al menos:

```text
gross_reconciled = pagos originalmente acreditados
confirmed_adjustments = refunds/chargebacks confirmados
net_reconciled = gross_reconciled - confirmed_adjustments
refund_pending = importe autorizado o enviado aún no confirmado
```

Reglas:

- un ajuste nunca puede superar el saldo reversible del Pago;
- moneda de operación, ajuste y Pago debe coincidir;
- varios parciales pueden acumularse sin exceder el original;
- `Pago.REVERSED`, si se reutiliza, sólo se proyecta tras reversión total y no
  reemplaza los ajustes;
- los cálculos no deben descontar simultáneamente el estado `REVERSED` y el
  ajuste, porque producirían doble resta;
- `refund_pending` no reduce `net_reconciled`.

### 6.4 Operaciones semánticas mínimas

#### A. Solicitar resolución

- Entrada: contexto, motivo, resultado solicitado, importe opcional y clave
  idempotente.
- Puede ser iniciada por titular dentro de su recurso, personal con autoridad
  comercial o un detector del sistema.
- Bloquea el contexto y pagos, crea/reutiliza el caso y registra la solicitud.
- No cambia Pago, dinero, orden, compromiso ni stock.
- En cancelación de Turno, coordina de forma atómica la cancelación comercial y
  la apertura del caso cuando ya hay dinero.

#### B. Decidir resolución

- Exige actor activo con `gestion.reconcile_external_payment`.
- Bloquea caso, resolución, contexto, pagos y ajustes.
- Exige motivo y fundamento; valida importe reversible y moneda.
- No permite aprobar más de lo acreditado neto.
- No llama al proveedor dentro de la transacción.
- Una denegación no se infiere de timeouts ni de reglas tácitas.

#### C. Ejecutar devolución

- Sólo admite una decisión `APPROVE_REFUND` vigente.
- Crea primero la operación local con clave idempotente estable y commit.
- El adaptador externo se invoca fuera de la transacción.
- Persiste `SUBMITTED`, `FAILED` o `UNKNOWN` sin declarar devolución realizada.
- Ante timeout/resultado desconocido, consulta por la misma identidad y espera
  C2a/C2b; no crea otro refund.
- Para medios manuales se exige evidencia, referencia, actor y conciliación
  independiente equivalente; no basta una nota libre.

#### D. Confirmar ajuste externo

- C2a/C2b sigue siendo autoridad de Mercado Pago.
- Crea/reutiliza el ajuste inmutable por identidad oficial e importe.
- Correlaciona con la operación local cuando sea posible.
- Si no hay operación local, conserva el hecho y abre/reutiliza caso para
  revisión humana.
- Una diferencia entre importe autorizado y confirmado mantiene el caso abierto.

#### E. Aplicar efecto comercial y cerrar

- Revalida bajo locks el estado actual, no el snapshot de la solicitud.
- BOOKING: conserva historial de Intent; aplica únicamente la decisión sobre el
  Turno, sin recrear HOLD.
- ORDER no entregada: una cancelación aprobada con refund total confirmado puede
  cambiar estado y liberar un compromiso `ACTIVE` mediante el servicio
  canónico, en una transición coordinada e idempotente.
- ORDER completada: no cancela ni repone; requiere proceso de retorno separado
  si se pretende recuperar stock.
- Cierra el caso sólo cuando sus criterios verificables se cumplen.

### 6.5 Condiciones de cierre de un caso

Un caso puede pasar a `RESOLVED` sólo si se registra `resolved_at` y se cumplen
todas las condiciones aplicables:

- existe decisión final autorizada y auditada;
- no hay operación `PENDING`, `SUBMITTED` o `UNKNOWN`;
- todo importe aprobado para devolución está confirmado, o la operación falló y
  una nueva decisión final define cómo continuar;
- los ajustes confirmados coinciden con importe, moneda e identidad esperados;
- el efecto de Turno/OrdenCompra fue aplicado o se justificó explícitamente que
  no corresponde;
- el compromiso/stock es coherente con el estado comercial;
- no hay discrepancia externa más reciente sin evaluar;
- se registra resultado final, actor de cierre y referencias a todos los hechos.

La confirmación mecánica puede completar automáticamente etapas ya decididas,
pero no inventar una decisión comercial. El cierre automático sólo sería válido
si todas las condiciones anteriores son determinísticas y la decisión humana ya
existe; en caso contrario lo ejecuta `reconcile_external_payment`.

## 7. Efectos permitidos por contexto

| Contexto y resultado | Dinero | Objeto comercial | Stock/compromiso |
|---|---|---|---|
| Turno cancelado, refund total/parcial confirmado | Ajuste por importe confirmado | Turno permanece `CANCELADO`; Intent conserva historia | No aplica |
| Turno cancelado, refund denegado con fundamento | Sin ajuste | Turno permanece `CANCELADO` | No aplica |
| Pago tardío devuelto | Ajuste confirmado | No crear Turno ni reactivar Intent/HOLD | No aplica |
| Orden pagada no entregada, cancelación + refund total confirmados | Neto reversible en cero | `CANCELADO` o estado terminal acordado | `ACTIVE -> RELEASED`, una vez, sin movimiento físico |
| Orden pagada con refund parcial | Ajuste parcial | Permanece sin cancelación total salvo política explícita | Mantener `ACTIVE` |
| Orden completada con refund | Ajuste confirmado | Mantener historia de `COMPLETADO`; devolución comercial separada | `CONSUMED` no cambia; reposición requiere retorno físico |
| Contracargo | Ajuste `CHARGEBACK` | Revisión; no cancelar servicio prestado automáticamente | No reponer; bloquear entrega pendiente hasta revisión |
| Duplicado técnico | Ninguno | Ninguno | Ninguno |

## 8. Concurrencia, idempotencia y seguridad

- Reutilizar el orden de locks de B3 para BOOKING y C2b/F5 para ORDER.
- ORDER debe bloquear primero orden, luego pagos/ajustes y después compromisos,
  evitando carreras con conciliación, entrega y cancelación.
- Una decisión aprobada no debe ejecutar dos refunds concurrentes.
- Toda solicitud, decisión, operación y ajuste necesita operation key única.
- La identidad externa de refund/chargeback debe tener constraint única.
- Nunca realizar HTTP dentro de `transaction.atomic()`.
- Guardar sólo snapshots sanitarios; no PAN, tokens ni secretos.
- Los comprobantes manuales siguen siendo privados.
- Un evento stale no degrada un hecho más reciente.
- Un caso abierto por ajuste negativo confirmado debe impedir la entrega
  irreversible de una orden todavía pendiente hasta que exista revisión; esto
  es un bloqueo de seguridad, no una cancelación automática.
- Fallos de auditoría semántica dentro de una transición deben hacer rollback de
  esa transición local.

## 9. Incrementos pequeños sugeridos

### F7.1 — Lectura operativa y clasificación

- Bandeja/API read-only de casos `OPEN` y detalle seguro.
- Filtros por tipo, contexto, antigüedad y razón.
- Autoridad `reconcile_external_payment` y eliminación de dependencias de
  `is_staff`.
- Sin decisiones ni refunds todavía.

### F7.2 — Solicitud y decisión

- Resolución y eventos append-only.
- Acciones idempotentes de solicitar, pedir evidencia, aprobar o denegar.
- Integración de cancelaciones con dinero para abrir caso sin mover dinero.
- Prohibición explícita de cerrar con sólo una solicitud.

### F7.3 — Ejecución de refund

- Operación local idempotente y adaptador de Mercado Pago.
- Estados `SUBMITTED`, `FAILED`, `UNKNOWN`; reconciliación por identidad.
- Sin efecto comercial hasta confirmación.

### F7.4 — Ajustes confirmados y proyecciones

- Hecho financiero compensatorio para refund parcial/total y chargeback.
- Integración C2a/C2b, constraints de no sobre-reversión y proyecciones bruto,
  pendiente y neto.
- Correlación entre operación local y evento externo.

### F7.5 — Efectos comerciales, stock y cierre

- Transición dedicada para orden no entregada con refund total confirmado.
- Bloqueo ante chargeback/revisión previa a entrega.
- Cierre verificable de casos y auditorías completas.
- Matriz de concurrencia contra entrega, cancelación y eventos duplicados.

### F7.6 — Interfaz y validación operativa

- Bandeja de revisión separada de caja F6.
- Confirmaciones claras de importe/moneda, evidencia y estado externo.
- Pruebas sandbox de refund total, parcial, duplicado, timeout y chargeback.
- Manual operativo, alertas de casos envejecidos y recuperación de operaciones
  `UNKNOWN`.

Cada incremento debe poder desplegarse sin declarar refunds como completados
antes de F7.4. F7.1/F7.2 pueden mejorar trazabilidad sin habilitar ejecución.

## 10. Créditos futuros exclusivamente para Turnos

Un crédito a favor puede evaluarse después de F7 como alternativa voluntaria
para BOOKING, pero no debe modelarse ahora como una billetera ni sustituir por
defecto un refund exigible.

Requisitos mínimos futuros:

- consentimiento explícito de la clienta y alternativa visible de devolución
  cuando corresponda;
- origen trazable en una resolución cerrada y un importe/moneda confirmados;
- titular único, saldo no transferible y uso exclusivo en `PaymentIntent` de
  Turnos;
- ledger append-only de emisión, consumo, vencimiento y anulación;
- idempotencia y prohibición de saldo negativo/doble consumo;
- reglas legales, fiscales, contables, de expiración y devolución del remanente;
- permiso para emitir/anular y auditoría separada;
- aplicación atómica al nuevo Intent sin recrear HOLD ni disponibilidad;
- tratamiento de cancelación de la nueva reserva y de contracargos del pago de
  origen.

Puede diferirse fuera de BH-058:

- UI de saldo, promociones, regalos y transferencias;
- créditos para productos u órdenes;
- cash-out, recargas y medios de pago generales;
- combinación avanzada de monedas o múltiples titulares;
- cualquier “wallet” o cuenta de dinero electrónico.

Para cerrar BH-058 no hace falta implementar créditos. Sí hace falta que el
workflow de F7 no registre “crédito ofrecido” o “crédito solicitado” como refund
realizado y que no obligue a aceptar crédito en reemplazo de dinero.

## 11. Riesgos principales y mitigaciones

| Riesgo | Mitigación mínima |
|---|---|
| Refund doble por retry o dos operadores | Clave idempotente estable, locks y unicidad externa. |
| Timeout interpretado como fallo y segundo envío | Estado `UNKNOWN`; consultar/reconciliar antes de reintentar. |
| Solicitud registrada como devolución | Etapas y campos separados; neto cambia sólo con ajuste confirmado. |
| Refund parcial tratado como total | Ajustes por importe y saldo reversible; no usar sólo `Pago.REVERSED`. |
| Doble resta financiera | Una única fórmula canónica bruto menos ajustes; `REVERSED` sólo proyección. |
| Liberar stock antes de resolver dinero | Mantener compromiso `ACTIVE` hasta refund total confirmado y decisión de cancelación. |
| Reponer stock sin retorno físico | Nunca alterar `CONSUMED` por refund; proceso de devolución separado. |
| Entregar tras chargeback confirmado | Bloqueo fail-closed de entrega mientras el caso esté abierto. |
| Decisión por rol débil o `is_staff` | Exigir permiso efectivo `reconcile_external_payment` en servicio. |
| Automatizar retención o derecho a refund | Decisión humana con fundamento/política versionada. |
| Cerrar con evento stale o discrepante | Revalidar última evidencia y dejar abierto ante diferencia. |
| Exponer datos financieros | Snapshots sanitarios, comprobantes privados y serializers mínimos. |
| Casos abiertos sin seguimiento | Bandeja, antigüedad, alertas y responsable operativo. |
| Mercado Pago no validado realmente | Sandbox HTTPS/webhook firmado y pruebas de estados adversos. |

## 12. Criterios para cerrar BH-058

BH-058 sólo debería declararse cerrado cuando se verifique, como mínimo:

1. Existe bandeja/API operativa de casos bajo permiso efectivo.
2. Solicitud, decisión, ejecución, confirmación y cierre son hechos separados y
   auditables.
3. Ninguna solicitud o respuesta ambigua reduce el neto financiero.
4. Refund total, parcial y chargeback se representan por importes confirmados e
   identidades externas únicas.
5. `Pago.REVERSED` no se usa para falsear parciales ni provocar doble resta.
6. Los nueve escenarios de este documento tienen pruebas funcionales y de
   permisos.
7. Hay pruebas de idempotencia y concurrencia contra conciliación, cancelación,
   entrega y eventos duplicados/stale.
8. La orden pagada conserva su compromiso hasta resolución confirmada; la orden
   completada nunca repone stock sólo por refund.
9. Un Turno cancelado con dinero abre resolución sin declarar devolución.
10. Pagos tardíos no recrean HOLD/Turno y disponen de una salida autorizada.
11. La autoridad de decisión es `reconcile_external_payment`; permisos de caja,
    agenda o stock no la sustituyen.
12. Los casos sólo cierran con condiciones verificables y sin operaciones
    pendientes/desconocidas.
13. La operación manual dispone de procedimiento, alertas y recuperación.
14. Mercado Pago se valida en sandbox con refund total, parcial, duplicados,
    timeout/resultado desconocido y notificación de chargeback.
15. Se mantienen los invariantes de B2, B3, C2b, F5 y F6 sin reabrir rutas
    genéricas de escritura o cancelación.

## 13. Backlog explícitamente diferido

- créditos a favor para Turnos y cualquier interfaz de saldo;
- wallet, transferencias de crédito o créditos para productos;
- motor automático de elegibilidad de refunds/retenciones;
- doble aprobación por umbral de importe, si la política futura la exige;
- disputas legales automatizadas de chargebacks;
- devoluciones físicas, cambios y reposición de órdenes `COMPLETADO`;
- repricing o división comercial automática tras refund parcial de una orden;
- sustitución automática de productos o rebooking automático;
- contabilidad general, asientos, comisiones, arqueo y cierre de caja;
- soporte multi-moneda y nuevos proveedores;
- compensaciones promocionales, cupones y gift cards;
- refund autoservicio inmediato para clientas;
- SLA avanzados, asignación automática y escalamiento multiequipo.

## 14. Propuesta final

F7 debe implementarse como una capa de resolución sobre los contratos actuales,
no como una reescritura de pagos, Intents o stock. La secuencia segura es:

```text
PaymentReconciliationCase (detección/contexto)
  -> Resolución (solicitud y decisión autorizada)
  -> Operación de refund (intento idempotente)
  -> Ajuste confirmado (hecho financiero inmutable)
  -> Efecto comercial/stock validado
  -> Case.RESOLVED
```

Este alcance permite resolver cancelaciones con dinero, pagos tardíos, órdenes
no cumplibles, refunds, contracargos y discrepancias sin automatizar derechos
comerciales inexistentes, sin confundir intención con ejecución y sin sacrificar
las garantías de F5 sobre stock.

BH-058 F7 — ANALISIS COMPLETADO
