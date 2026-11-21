# BH-058 — Arquitectura final y plan incremental

Fecha: 2026-10-25

Fuente exclusiva: análisis BH-058 A (HOLD), B (PaymentIntent/Pago), C
(Mercado Pago) y D (stock/permisos). Este documento no reaudita el repositorio,
no modifica código y no implementa ningún incremento.

## 1. Mapa final del dominio

### 1.1 Booking

```text
SolicitudTecnicaReserva
  → SlotHold
  → PaymentIntent
  → ProviderPaymentAttempt (opcional)
  → Pago 1:N
  → conciliación + consumo atómico del HOLD
  → Turno CONFIRMADO
```

| Entidad | Responsabilidad única |
|---|---|
| `SolicitudTecnicaReserva` | Intención y evaluación técnica previa; habilita, pero no reserva. |
| `SlotHold` | Reserva temporal de Cliente, Personal, intervalo, Servicios y capacidad. |
| `PaymentPolicy` | Política versionada de seña/total, moneda, TTL y medios. |
| `PaymentIntent` | Obligación financiera inmutable y umbral requerido para un HOLD. |
| `ProviderPaymentAttempt` | Un intento de checkout externo con referencia, monto, moneda y key persistidos. |
| `ProviderEvent` | Inbox durable, autenticado y deduplicado de notificaciones externas. |
| `Pago` | Hecho financiero 1:N, manual o externo, pendiente/reconciliado/rechazado/revertido. |
| `PaymentReconciliationCase` | Excepción operativa: tardío, mismatch o confirmación fallida. |
| `Turno` | Cita operativa final, creada exactamente una vez al consumir un HOLD válido. |

### 1.2 Venta de productos

```text
OrdenCompra (venta al Cliente)
  → Pago
  → apply_order_inventory_effect(order)
  → MovimientoStock ORDER_SALE_OUT
```

| Entidad | Responsabilidad única |
|---|---|
| `OrdenCompra` | Pedido/venta de productos al Cliente; no compra a proveedor. |
| `CompromisoStock` | Reserva estructurada de unidades para una orden, si el checkout las garantiza. |
| `MovimientoStock` | Hecho físico inmutable de entrada/salida/ajuste; autoridad histórica. |
| `Producto.stock_real` | Proyección materializada y no editable de movimientos. |
| `Producto.stock_comprometido` | Proyección materializada de compromisos activos. |

`Pago` puede conservar ambos contextos durante la transición, pero cada fila
debe pertenecer a **exactamente uno**: `PaymentIntent` de booking u
`OrdenCompra`. Los reconciliadores y efectos permanecen separados.

Confirmaciones explícitas:

- Solicitud **!=** HOLD.
- HOLD **!=** Turno.
- `PaymentIntent` **!=** Pago.
- Pago **!=** confirmación de agenda.
- `OrdenCompra` **!=** Turno.
- `MovimientoStock` **!=** reserva de agenda.

## 2. Invariantes no negociables

1. Una solicitud técnica no bloquea agenda.
2. Sólo `SlotHold(ACTIVE, expires_at > database_now)` bloquea.
3. Un HOLD vencido nunca se consume ni vuelve a `ACTIVE`.
4. Un HOLD consumido produce exactamente un Turno y conserva el vínculo único.
5. El frontend no confirma Pagos, Intents, HOLDs ni Turnos y no aporta montos autoritativos.
6. `PaymentIntent.APPROVED` expresa umbral financiero; aislado no confirma agenda.
7. El Turno sólo nace si solicitud, evaluación, HOLD, pagos y recursos se revalidan juntos.
8. Un pago tardío se conserva, pero no resucita Intent/HOLD ni crea Turno.
9. Un webhook no es autoridad: requiere firma válida, evento durable y fetch oficial.
10. Payload, query y return URL nunca prueban pago ni estado interno.
11. Toda llamada HTTP al provider ocurre fuera de `transaction.atomic()` y sin locks DB.
12. Toda mutación concurrente respeta un orden global de locks y revalida después de esperar.
13. Toda operación retryable usa idempotencia persistida y constraints unique.
14. Un Payment ID externo produce como máximo un Pago; un HOLD, como máximo un Turno.
15. Stock físico y comprometido nunca son negativos ni se corrigen con clamps.
16. Stock no se modifica por serializer, admin, webhook, signal o asignación directa.
17. `MovimientoStock` es inmutable; una corrección es un movimiento compensatorio.
18. Booking nunca crea movimientos de stock ni reserva productos por Turno.
19. Mercado Pago de `OrdenCompra` nunca ejecuta lógica booking, y booking nunca ejecuta stock de Orden.
20. Backend verifica permisos efectivos/ownership; nunca `is_staff`, BusinessRole o `Personal.rol` como autoridad.

## 3. Orden global de locks

### 3.1 Booking

Orden canónico único; se omiten entidades inexistentes para la operación:

```text
SolicitudTecnicaReserva
→ SlotHold
→ PaymentIntent
→ Cliente
→ ProviderPaymentAttempt (PK ascendente)
→ ProviderEvent (PK ascendente)
→ Pago (PK ascendente)
→ Servicio (PK ascendente)
→ Personal
→ TipoEquipamiento (PK ascendente)
→ unidad de Equipamiento, sólo si se modifica
→ Turno ya enlazado, sólo en retry
```

El Event puede reclamarse antes en una transacción breve. La mutación semántica
lo vuelve a bloquear en su posición canónica. Crear HOLD aún no tiene Intent;
por eso pasa de HOLD a Cliente. Crear Intent no tiene Attempt/Event/Pago y omite
esas filas. Siempre se toma un reloj nuevo después de esperar locks.

### 3.2 Inventario de productos

```text
OrdenCompra
→ Producto por PK ascendente
→ CompromisoStock/reservas por PK ascendente
→ MovimientoStock existente por key, si lo hay
```

El command consolida cantidades por Producto, bloquea el conjunto antes de
validar y aplica todo o nada. El reconciliador de una Orden no toma locks de
Solicitud/HOLD/Turno; el de booking nunca toma locks de Producto.

### 3.3 Conflictos resueltos

- A ubicaba Cliente inmediatamente después del HOLD; B/C insertan Intent antes.
  Se adopta B/C porque toda operación financiera debe serializar la obligación
  antes del dueño y después conserva el orden de recursos de A.
- C permite claim temprano del Event. Se conserva sólo como leasing técnico;
  no altera el orden de la transacción de dominio.
- `Pago` compartido podría unir grafos. El constraint de contexto exclusivo y
  reconciliadores separados impide que una fila requiera ambos órdenes de lock.
- D es un agregado independiente. Ningún command combinado booking+stock queda permitido.

## 4. Permisos finales BH-058

| Permiso/autoridad | Acción y scope | Defaults | Individual | Actor |
|---|---|---|---:|---|
| ownership Cliente | Crear/consultar/cancelar Intent propio en estado permitido | CLIENTE | No aplica | Humano |
| `view_stock` | Ver cantidades, mínimos y movimientos internos | EMPLEADO, PROFESIONAL, ADMIN | Sí | Humano |
| `manage_stock` | Recibir, ajustar y corregir stock manualmente | ADMIN | Sí | Humano |
| `manage_products` | Catálogo, SKU, categoría, imágenes y publicación | ADMIN | Sí | Humano |
| `manage_prices` | Precio base de Producto y Servicio | ADMIN | Sí | Humano |
| `manage_promotions` | Crear/publicar/rechazar reglas promocionales | ADMIN | Sí | Humano |
| `register_payment` | Registrar recepción/evidencia de Pago manual | EMPLEADO, ADMIN | Sí | Humano |
| `confirm_deposit` | Conciliar/rechazar evidencia manual DEPOSIT o FULL | ADMIN | Sí | Humano |
| `manage_payment_configuration` | Publicar nueva `PaymentPolicy` | ADMIN | Sí | Humano |
| `view_financial_reports` | Pagos e importes globales reconciliados | ADMIN | Sí | Humano |
| `reconcile_external_payment` | Forzar fetch y reconciliación externa, nunca editar montos | ADMIN | Sí | Humano; sistema usa canal interno |
| efecto automático de venta | Aplicar inventario de Orden ya reconciliada | Ningún rol | No | Sistema |
| webhook/expiradores | Ingresar evento o materializar vencimientos | Ningún rol | No | Sistema identificado |

No se crean en v1 `create_payment_intent` ni `cancel_payment_intent`: el Cliente
opera lo propio por ownership y el sistema crea/expira por servicios internos.
No hay requerimiento aprobado para que personal cree/cancele Intents por otro
Cliente. Si aparece, se agregará un permiso explícito; no se reutiliza
`create_turno_for_client` ni se concede por ADMIN textual.

`confirm_deposit` se conserva por compatibilidad, aunque su nombre futuro debe
evolucionar a `reconcile_payment`. No confirma Turno.

## 5. Defaults definitivos de roles

| Rol | Defaults BH-058 |
|---|---|
| CLIENTE | Ningún permiso administrativo; ownership sobre Solicitud/Intent/Pago propios. |
| EMPLEADO | `view_stock`, `register_payment`; no conciliación, configuración, reportes ni stock mutable. |
| PROFESIONAL | `view_stock`; **no** hereda permisos financieros de EMPLEADO y nunca `manage_stock` por skill. |
| ADMINISTRADOR | Todos los permisos administrativos/operativos de la tabla, incluido `reconcile_external_payment`. |

Decisión: EMPLEADO puede registrar efectivo/evidencia como función operativa
base, pero `confirm_deposit` requiere asignación individual si también concilia
transferencias. Esto conserva separación captura/aprobación. PROFESIONAL recibe
capacidades clínicas/agenda por su propio set, no mediante herencia ciega del
tuple de EMPLEADO. Cualquier permiso puede otorgarse individualmente a una
cuenta activa. BusinessRole sólo entrega defaults; cada endpoint usa
`user.has_perm(...)` u ownership.

## 6. Legacy que debe convivir

| Legacy | Estado actual | Estrategia durante BH-058 | Destino final |
|---|---|---|---|
| `limpiar_turnos` | Limpia estados legacy con tiempo/atomicidad defectuosos | Aislar y corregir con locks, causa, actor y notificación idempotente; nunca tocar HOLD | Retirar al drenar productores/datos en BH-059 |
| `Turno.SOLICITADO` | Bloquea agenda | Cesar nuevos productores para booking nuevo; seguir leyendo filas históricas | Migrar/retirar semántica pre-reserva en BH-059 |
| `ESPERANDO_SENA` | Mezcla agenda y obligación | Nuevo flujo usa HOLD + Intent; mantener sólo compatibilidad | Migrar tras conciliación de datos |
| `PENDIENTE` | Estado ambiguo y bloqueante | No usar para nuevo booking; limpieza legacy controlada | Retirar/normalizar en BH-059 |
| `SUGERIDO` | Puede bloquear sin TTL | No añadirlo silenciosamente a limpieza; política/migración puntual | Retirar productor legacy en BH-059 |
| `Turno.fecha_limite_pago` | Deadline de `esperando_sena` | Sólo lectura/limpieza legacy | `PaymentIntent.expires_at` lo reemplaza |
| `monto_abonado` | Acumulado divergente | No escribir desde flujo nuevo; reportar inconsistencias | Derivar de Pagos y retirar/caché explícita |
| `saldo_pendiente` | Inicializado ambiguamente | No usar como autoridad | Derivar de Intent/Pagos y retirar |
| `comprobante_pago` | Evidencia pegada a Turno | Mantener lectura; evidencia nueva pertenece a Pago | Migrar tras revisión, luego retirar |
| `tipo_pago_registro` | Mezcla modalidad y medio | Congelar escritura nueva | Reemplazar por Intent.mode + Pago.method |
| `Configuracion.monto_sena` | Monto fijo global | Seed explícito de primera `PaymentPolicy`; no doble autoridad | Deprecar y retirar |
| `tiempo_limite_pago_sena` | TTL legacy en horas | No usar para HOLD; seed documentado si aplica a Policy | Reemplazar por TTLs de HOLD/Intent |
| `OrdenCompra` MP legacy | Venta con checkout/webhook acoplados | Namespace/reconciliador de Orden separado; efectos por command D | Mantener dominio de venta, modernizar integración aparte |
| `OrdenPendiente` | Intención WhatsApp duplicada con JSON | Delegar cualquier efecto a commands D; no escritura directa | Retirar/migrar en BH-059 |
| `stock_comprometido` | Proyección sin hechos | Volver read-only; atribuir a compromisos o reset explícito | Proyección de `CompromisoStock` |
| `stock_real` editable | Autoridad directa | Volver read-only y mover sólo por command | Proyección de `MovimientoStock` |

No se hace una eliminación masiva. El flujo nuevo deja de producir legacy; los
adaptadores de convivencia permanecen observados hasta drenar datos.

## 7. Migraciones necesarias por incremento

| Migración | Contenido |
|---|---|
| M1 / A1 | `SlotHold`, snapshots de Servicios/equipamiento, UUID, estados/timestamps, `consumed_turno`, keys, checks/uniques/índices; `Configuracion.slot_hold_ttl_minutes`. |
| M2 / A2 | Sólo si hace falta, vínculo único inverso Turno↔HOLD y constraint de origen; sin campos financieros. |
| M3 / B | `PaymentPolicy`, `PaymentIntent`, `PaymentIntentLine`; evolución aditiva de `Pago` con Intent/contexto, moneda, estado, actores, evidencia, referencias, key y `PROTECT`; migración escalonada antes de constraints estrictos. |
| M4 / D | `MovimientoStock`, `CompromisoStock`, before/after, origen, actor, key y corrección; checks de Producto y ledger; opening sólo si preflight encuentra saldos. |
| M5 / C1 | `ProviderPaymentAttempt` y `ProviderEvent`, public IDs, estados, hashes, references y uniques; provider config queda en env, no DB editable. |
| M6 / C2 | `PaymentReconciliationCase`, permiso `reconcile_external_payment`, constraints finales `(provider,payment_id)` y referencias tras auditar datos legacy. |

Cada migración de datos informa inconsistencias y aborta ante ambigüedad. No
fabrica Events, Pagos, movimientos ni reservas históricos.

## 8. Incrementos de implementación

| Incremento | Objetivo/modelos | Servicios y endpoints | Frontend/tests | Frontera |
|---|---|---|---|---|
| **A1 — SlotHold, disponibilidad y expiración** | Reserva temporal con reloj, snapshots y locks; M1. | Crear, leer, liberar y expirar HOLD; disponibilidad unificada; `expirar_slot_holds`. | Countdown informativo; modelo, tiempo, disponibilidad y concurrencia PostgreSQL. | No crea Turno ni toca pagos, provider o stock. |
| **A2 — Consumo canónico de HOLD** | Una primitiva interna crea exactamente un Turno `CONFIRMADO`; M2 si hace falta. | `create_confirmed_turno_from_locked_hold`, consumo condicional/idempotente; sin endpoint de “confirmar gratis”. | Sólo lectura futura; doble consumo, expiry bajo lock y revalidación. | No decide suficiencia financiera ni integra providers. |
| **B — Núcleo financiero manual** | Policy, Intent, Pago 1:N, conciliación y saldo; M3. | Crear/cancelar/expirar Intent, registrar/conciliar Pago, status/política; reutiliza A2 al alcanzar umbral manual. | Intent/evidencia/historial por capabilities; snapshots, parciales, permisos y concurrencia. | No SDK, preference, webhook ni caja física. |
| **D — Ledger y autorización de inventario** | Stock trazable/no negativo y venta idempotente; M4. | receive/adjust/correct, comprometer/liberar y `apply_order_inventory_effect`. | UI separada y serializer público; locks, inmutabilidad, permisos y Orden una vez. | No proveedores, consumo por Servicio, devoluciones ni booking. |
| **C1 — Adapter y checkout externo** | Encapsular MP y checkout recuperable; M5. | `PaymentProvider`, adapter, TX1/HTTP/TX2, checkout/status. | Redirección/status; adapter, timeouts, outcome unknown, retries y dos clicks. | No webhook, conciliación ni Turno. |
| **C2 — Webhook y confirmación final** | Inbox seguro, fetch, Pago externo, confirmación o late; M6. | Webhook namespaced, reconciliador automático/manual y orquestador B+A2. | Estados internos; firma, dedupe, mismatch, carreras y separación de dominios. | No refund automático, caja física, stock booking ni promociones. |

## 9. Dependencias y orden óptimo

```text
A1 → A2 → B → C1 → C2
D ─────────────────↗  (independiente; requerido sólo para el cutover global de OrdenCompra)
```

Orden de entrega recomendado: **A1, A2, B, D y C1 (paralelizables después de
B por planificación, no por dependencia técnica), C2**. D no depende del
booking ni del adapter para crear el ledger. C2 puede
funcionar para booking sin stock, pero su cutover global no debe dejar al
handler legacy de Orden mutando Producto directamente; por eso exige el contrato
de D para el camino OrdenCompra.

## 10. Qué no debe hacer cada incremento

| Incremento | Exclusión obligatoria |
|---|---|
| A1 | No pagos, no Intents, no Turno desde HOLD, no stock. |
| A2 | No autorizar financieramente, no endpoint directo de confirmación, no provider. |
| B | No Mercado Pago, webhook, IDs externos específicos ni caja física. |
| D | No consumo/reserva por Servicio o Turno, proveedores, devoluciones ni BH-059. |
| C1 | No webhook, conciliación ni Turno; no reutilizar `MercadoPagoService(OrdenCompra)` para booking. |
| C2 | No refund/crédito automático, no confiar en callback y no tocar inventario desde booking. |

## 11. Tests bloqueantes de cierre

| Cierre | Casos críticos (5–10) |
|---|---|
| **A1** | (1) sólo solicitud/evaluación vigente crea HOLD; (2) sólo ACTIVE no vencido bloquea; (3) límites `now <`, `==`, `>`; (4) dos HOLDs, uno; (5) conflictos Cliente/equipamiento; (6) Turno vs HOLD en PostgreSQL; (7) release/expire idempotentes; (8) job caído no bloquea. |
| **A2** | (1) crea CONFIRMADO desde snapshots; (2) vencido no consume; (3) dos consumos, un Turno; (4) revalida solicitud/evaluación/recursos; (5) excluye propio HOLD; (6) fallo revierte Turno; (7) sin deadlock PostgreSQL. |
| **B** | (1) DEPOSIT/FULL y snapshot; (2) un Intent activo/aprobado; (3) Pago/key/reference únicos; (4) parciales sin sobrepago; (5) APPROVED no duplica Turno; (6) late no resucita; (7) permisos separados; (8) staff sin permiso=403; (9) pago vs cancel/expiry PostgreSQL. |
| **D** | (1) entrada/salida a cero/no negativo; (2) ajuste con razón/actor/key; (3) inmutabilidad; (4) dos salidas sin oversell; (5) ledger=proyección; (6) Orden repetida una salida; (7) Cliente sin mutación; (8) booking sin movimientos. |
| **C1** | (1) request desde Attempt; (2) HTTP fuera de TX; (3) key/hash coherentes; (4) timeout/429/5xx recuperables; (5) dos clicks un checkout; (6) TX2 recuperable; (7) logs sin secrets. |
| **C2** | (1) firma/replay; (2) Event/Payment deduplicados; (3) fetch prevalece; (4) mismatch no confirma; (5) parcial queda pending; (6) exacto crea un Turno; (7) late crea caso; (8) carreras PostgreSQL; (9) crash recuperable; (10) namespaces sin cruce. |

## 12. Verificación externa Mercado Pago

Cada verificación debe registrar URL oficial, versión/fecha y decisión; no se
inventan headers, algoritmos, estados o garantías.

### BLOQUEA IMPLEMENTACIÓN MP DE C

- algoritmo de firma, canonical string, headers, tolerancia temporal/replay y rotación del secret;
- ID estable/fingerprint de evento, campos constantes en retry, tipos/actions, códigos HTTP y redelivery;
- idempotency key de preference: header, scope, ventana y reutilización real por SDK;
- recuperación/búsqueda tras resultado incierto por key o external reference;
- longitud, charset y preservación exacta de `external_reference`;
- campo oficial para correlacionar Payment con preference/checkout;
- campos autoritativos de amount/currency, moneda y precisión;
- catálogo de estados/status_detail y transiciones que permiten reconciliar;
- diferencias sandbox/production e `init_point`/`sandbox_init_point`.

El modelo/provider-neutral y tests con fake adapter pueden empezar antes; ningún
adapter MP real, webhook o checkout productivo se habilita sin lo anterior.

### PUEDE VERIFICARSE DURANTE C, ANTES DE HABILITAR PRODUCCIÓN

- eventual consistency de `GET Payment` y estrategia de retry;
- expiración/cancelación de preference y garantías de links viejos;
- rate limits y semántica de `Retry-After`;
- refunds/chargebacks: se clasifican como caso no soportado, sin implementarlos en BH-058.

## 13. Datos y bootstrap

- Los datos actuales no son críticos y el stock auditado está vacío.
- Se inicia `MovimientoStock` limpio; no se crean openings de cero.
- Si otro entorno tiene saldo, preflight y un `OPENING_BALANCE` explícito por
  Producto; nunca historia comercial inventada.
- Estados financieros/Turnos legacy se reportan y concilian; no se convierten
  por equivalencia textual.
- **Seed estructural:** con la migración que lo necesita: permisos, grupos,
  reason codes y primera PaymentPolicy documentada.
- **Seed demo:** sólo después de cerrar cada incremento; solicitudes/HOLDs,
  productos y stock demo separados, idempotentes y nunca en producción por
  efecto colateral de una migración.

## 14. Backlog fuera de BH-058

| Backlog | Contenido consolidado |
|---|---|
| BH-059 | Retiro/migración de rutas, productores, estados y modelos legacy: `OrdenPendiente`, estados pre-reserva y `limpiar_turnos` al quedar sin datos. |
| BH-060 | Robustecer entorno de tests, PostgreSQL concurrente, dependencias y estabilidad E2E/CI. Los tests funcionales bloqueantes siguen dentro de BH-058. |
| BH-061 | UI ampliada de auditoría/reportes y limpieza global de navegación legacy fuera de pantallas BH-058. |
| BH-062 | Sustituir `is_staff` restante fuera de las superficies financieras/inventario que BH-058 debe corregir ya. |
| BACKLOG NUEVO | Proveedores y compras al proveedor; clasificación vendible/insumo; unidades/lotes/costos/ubicaciones; receta Servicio→Producto; consumo técnico real; devoluciones; refunds/créditos/reversiones complejas; caja física con apertura/cierre/arqueo; motor promocional y snapshots coherentes. |

## 15. Riesgos de implementación

| Nivel | Riesgo | Mitigación de cierre |
|---|---|---|
| CRÍTICO | Escritores legacy evaden locks/commands | Encapsular todas las rutas antes de habilitar flujo nuevo. |
| CRÍTICO | Orden de locks diverge y causa deadlock o doble Turno | Helpers comunes y pruebas PostgreSQL con conexiones reales. |
| CRÍTICO | Webhook falso/repetido confirma agenda | Firma verificada, Event durable, fetch oficial y uniques. |
| CRÍTICO | Booking y OrdenCompra cruzan handlers/efectos | Namespaces, contexto exclusivo de Pago y reconciliadores separados. |
| ALTO | HTTP dentro de TX deja locks o resultado incierto | TX1/HTTP/TX2 y estado `OUTCOME_UNKNOWN`. |
| ALTO | Pago tardío resucita obligación | Estados terminales, reloj tras lock y caso `LATE_PAYMENT`. |
| ALTO | Doble autoridad durante migración | Flujo nuevo no escribe campos legacy; reportes de reconciliación. |
| ALTO | Roles/staff sustituyen permisos | Tests negativos por permiso efectivo y ownership. |
| ALTO | Stock directo/clamp oculta oversell | Ledger, proyección read-only, locks y rechazo de negativo. |
| MEDIO | Workers/Events fallan sin observabilidad | Commands idempotentes, métricas mínimas y casos recuperables. |

## 16. Primer incremento a implementar

### **BH-058 A1 — SlotHold, disponibilidad y expiración**

**Alcance:** introducir HOLD persistido con snapshots, TTL propio, creación y
liberación transaccionales, disponibilidad Turno+HOLD y expiración defensiva.
No incluye consumo a Turno; esa frontera permite auditar que reservar y expirar
son correctos antes de conectar dinero.

**Zonas probables:**

- `gestion/models.py` y nueva migración M1;
- servicio actual de disponibilidad y nuevo servicio de ciclo de vida HOLD;
- serializers/views/urls semánticos de creación, consulta y liberación;
- command nuevo `expirar_slot_holds`;
- configuración TTL y tests dedicados de modelo/API/concurrencia.

**Migración:** `SlotHold`, hijos snapshot, constraints/índices, UUID, keys,
timestamps terminales, vínculo nullable único a Turno y
`slot_hold_ttl_minutes`. Sin backfill ficticio desde estados Turno.

**Servicios:** `create_slot_hold`, `release_slot_hold`, `expire_slot_hold` y
consulta efectiva; locks solicitud→HOLD→Cliente→Servicios→Personal→tipos,
reloj nuevo y auditoría idempotente.

**Tests de aceptación:** los ocho casos A1 de la sección 11, ejecutando carreras
en PostgreSQL real. Cierre exige exactamente un ganador, cero HOLD vencidos
bloqueantes y ninguna dependencia del scheduler para seguridad.

**NO tocar:** `PaymentPolicy`, `PaymentIntent`, `Pago`, Mercado Pago,
`ProviderAttempt/Event`, creación de Turno desde HOLD, stock, `OrdenCompra`,
`OrdenPendiente`, recetas, proveedores ni eliminación de `limpiar_turnos`.

## 17. Estado final

**BH-058 ANÁLISIS = COMPLETO**

**PRÓXIMO INCREMENTO = BH-058 A1 — SlotHold, disponibilidad y expiración**
