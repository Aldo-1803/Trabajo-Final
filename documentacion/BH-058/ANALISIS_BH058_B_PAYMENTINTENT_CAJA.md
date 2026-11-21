# BH-058 B — PaymentIntent, Pago y caja MVP

Fecha del análisis: 2026-10-25

Alcance: obligación financiera interna para reservas técnicas, modalidades
seña/total, pagos manuales, conciliación, saldo y permisos. Este documento no
diseña preferencias, webhooks ni validación de un proveedor externo. Tampoco
rediseña stock; las órdenes de productos sólo se mencionan porque actualmente
comparten el modelo `Pago`.

## 1. Conclusión ejecutiva

El modelo actual mezcla tres conceptos:

- obligación de pago en campos mutables de `Turno`;
- evidencia de transferencia en `Turno.comprobante_pago`;
- hecho financiero en `Pago`, sin estado, moneda, actor ni obligación.

BH-058 B debe separarlos:

```text
PaymentPolicy versionada
        ↓ snapshot
PaymentIntent ── pertenece a ── SlotHold
        ↓ 1:N
Pago reconciliado
        ↓
saldo derivado
```

`PaymentIntent` representa cuánto debe abonarse para satisfacer el requisito de
confirmación y bajo qué snapshot de precios/política. `Pago` representa dinero
recibido o evidencia financiera reconciliable. Ninguno confirma un `Turno` por
sí solo.

La aprobación financiera sólo significa que pagos reconciliados alcanzaron el
`required_amount`. BH-058 C deberá combinar esa condición con un HOLD vigente y
consumirlo atómicamente. No debe existir un signal que cree o confirme un Turno
por observar `PaymentIntent.APPROVED`.

No existe hoy una Caja real. Para v1 es suficiente un ledger de `Pago` con
actor, medio, moneda, estado y auditoría. Apertura, cierre, egresos y arqueo son
otro subsistema y no deben inventarse dentro de BH-058 B.

---

## 2. Inventario financiero actual

### 2.1 Resumen por elemento

| Elemento actual | Significado/autoridad real | Side effects | Clasificación |
|---|---|---|---|
| `Configuracion.monto_sena` | Monto fijo global editable. No se encontró uso para calcular un pago de Turno. | Cambiarlo no recalcula Turnos ni Pagos. | **Legacy reutilizable sólo como dato de migración**. |
| `Configuracion.tiempo_limite_pago_sena` | Horas legacy para completar `fecha_limite_pago`. | Sólo se consulta en una rama de actualización genérica hoy deshabilitada. | **Legacy**. No reutilizar como TTL de HOLD sin nueva política. |
| `Turno.fecha_limite_pago` | Deadline del estado `esperando_sena`. | `limpiar_turnos` cancela cuando vence. | **Legacy**; la obligación nueva debe vencer en `PaymentIntent`. |
| `Turno.tipo_pago_registro` | Mezcla modalidad (`sena`, `total`) y medio (`efectivo`, `transferencia`) en una columna. | Ninguno observado en servicios actuales. | **Conflictivo**. Son dimensiones distintas. |
| `Turno.monto_abonado` | Acumulado materializado. La creación lo inicializa en cero. | `registrar_pago` no lo actualiza. | **Conflictivo/derivado obsoleto**. |
| `Turno.saldo_pendiente` | Saldo materializado. Se inicializa en cero incluso sin total calculado. | No se deriva de `Pago`. | **Conflictivo**; no es autoridad. |
| `Turno.comprobante_pago` | Archivo que el Cliente puede reemplazar en `esperando_sena`. | Guarda evidencia, genera historia/auditoría genérica y el signal puede volver a notificar “Turno aceptado” aunque el estado no haya cambiado. | **Legacy**; evidencia futura debe asociarse a un Pago. |
| `DetalleTurno.precio_historico` | Precio capturado al crear el Turno. | Puede reconstruir total del Turno después de existir. | **Reutilizable para Turnos**, pero llega demasiado tarde para el Intent previo. |
| `Servicio.precio_base` | Precio vigente del catálogo de Servicios. | Alimenta `DetalleTurno` al crear Turno. | **Fuente para crear el snapshot**, nunca para recomputar un Intent existente. |
| `OrdenCompra.total` | Total snapshot de una orden de productos. No es total de un Turno. | Alimenta flujos de orden y reportes legacy. | **Fuera del agregado de reserva**; conservar como frontera de compatibilidad. |
| `Pago` | Fila de monto y medio asociable a Orden o Turno. | Manualmente sólo crea la fila; un flujo externo legacy afecta además la Orden. | **Reutilizable como base de migración, no como contrato actual**. |
| `Pago.es_sena` | Booleano enviado por UI; no se valida contra política ni importe. | Sólo etiqueta la fila y filtros. | **Conflictivo**; debe derivarse del Intent/modo. |
| `Pago.transaccion_id` | Referencia externa opcional y única. | Evita repetir una misma referencia no nula en un flujo legacy. | **Idea reutilizable**, generalizada por provider/referencia. |
| `Pago.comprobante_foto` | Evidencia obligatoria para `TRANSFERENCIA` en serializer. | Crea archivo; no implica conciliación real. | **Reutilizable con controles**, no equivale a aprobación. |
| `PagoViewSet` | Historial de filas `Pago`. | Sólo lectura. | **Reutilizable como base de reporte**, con permisos y estados corregidos. |
| `HistorialPagos` | Pantalla denominada “Caja” que suma montos cargados. | Imprime comprobantes desde datos del navegador. | **No es Caja**; es un historial/resumen incompleto. |
| `confirm_deposit` | Permiso declarado en `Turno`. | Ninguno: no existe action o servicio que lo consulte. | **Permiso huérfano**. |
| `register_payment` | Permiso declarado en `Pago` y asignado a grupos. | Ninguno en autorización: los endpoints usan `is_staff`. | **Permiso correcto no aplicado**. |
| `manage_payment_configuration` | Permiso declarado en `Configuracion`. | No protege la vista actual. | **Permiso correcto no aplicado**. |
| `view_financial_reports` | Permiso declarado en `Auditoria`. | Frontend lo usa para Reportes, pero backend usa `IsAdminUser`. | **Permiso parcialmente aplicado**. |

### 2.2 `Pago` actual

`gestion.models.Pago` contiene:

- FK nullable a `OrdenCompra` con `CASCADE`;
- FK nullable a `Turno` con `CASCADE`;
- `monto`;
- `metodo_pago`: `EFECTIVO`, `TRANSFERENCIA`, `MERCADO_PAGO`;
- `transaccion_id` nullable y único;
- `fecha_pago`, escribible por API;
- `comprobante_foto`;
- `es_sena` booleano;
- simple-history.

Problemas estructurales:

1. no exige monto positivo;
2. no tiene moneda;
3. no tiene estado de registro/conciliación/reversión;
4. no conserva actor que recibió o verificó el dinero;
5. no tiene idempotency key manual;
6. no exige exactamente un origen: Orden y Turno pueden ser ambos nulos o ambos
   estar presentes;
7. `CASCADE` permite eliminar hechos financieros al eliminar su origen;
8. no relaciona una obligación o política;
9. no limita suma pagada ni valida saldo;
10. no tiene referencia manual normalizada;
11. `__str__` asume que siempre existe `orden` y falla conceptualmente para un
    Pago asociado sólo a Turno;
12. `Pago` no está incluido entre los modelos con signal genérico de
    `Auditoria`; simple-history no reemplaza actor y evento financiero
    semántico.

`PagoSerializer` sólo exige comprobante para transferencia. No valida monto,
estado del origen, total, saldo, duplicado lógico, fecha futura ni permiso. El
frontend acepta PDF, pero el modelo usa `ImageField`, inconsistencia que puede
rechazar el mismo archivo que la UI ofrece.

### 2.3 Campos financieros de `Turno`

`Turno` no posee un `total` canónico. Su total de Servicios podría derivarse de
`DetalleTurno.precio_historico`, pero los campos `monto_abonado` y
`saldo_pendiente` no se actualizan al crear `Pago`.

La creación canónica escribe:

```text
tipo_pago_registro = null
monto_abonado = 0
saldo_pendiente = 0
```

Ese saldo cero no significa “pagado”: significa que nunca fue calculado. Por
ello, esos campos no deben migrarse como verdad financiera sin conciliarlos
contra `Pago` y precios históricos.

`fecha_limite_pago` se asignaba en `TurnoViewSet.perform_update` al pasar a
`esperando_sena`, pero `update` y `partial_update` están deshabilitados. No se
encontró actualmente una acción dedicada que haga esa transición. El command
`limpiar_turnos` sí consume el campo si fue completado por otra vía.

### 2.4 Comprobantes

El Cliente propietario puede cargar `Turno.comprobante_pago` sólo en
`esperando_sena`. La subida:

- no registra monto, moneda, referencia ni banco;
- no crea `Pago`;
- no cambia estado;
- no tiene decisión de aceptación/rechazo;
- permite reemplazar el archivo;
- no invoca `confirm_deposit`;
- al guardar el Turno en `esperando_sena`, el signal de notificaciones puede
  emitir de nuevo “Turno aceptado” aunque sólo haya cambiado el archivo.

Un comprobante es evidencia, no un Pago reconciliado. En el modelo futuro debe
pertenecer al registro de Pago/evidencia y mantenerse fuera de respuestas no
financieras.

### 2.5 Views y autorización actuales

`POST /turnos/{id}/registrar_pago/` y las acciones equivalentes de órdenes:

- exigen `request.user.is_staff`;
- no consultan `gestion.register_payment`;
- crean mediante `serializer.save` sin `transaction.atomic` ni lock;
- no validan estado, obligación, importe ni saldo;
- no actualizan `Turno`;
- no persisten actor;
- no son idempotentes.

`PagoViewSet` es read-only y usa `IsAdminUser`, no
`view_financial_reports`. `ConfiguracionViewSet` usa también `IsAdminUser`, no
`manage_payment_configuration` ni `manage_configuration`.

Los permisos efectivos existen y se entregan a roles base, pero no gobiernan
estas operaciones. Un usuario `is_staff` sin permiso registra y ve pagos; un
usuario con permiso individual pero sin `is_staff` no puede hacerlo.

### 2.6 Frontend actual

- `PagoModal` captura monto, efectivo/transferencia, fecha, archivo y `es_sena`.
  Sólo valida monto positivo y archivo para transferencia en el navegador.
- En el árbol actual el modal está conectado a gestión de órdenes; no se
  encontró una acción de pago activa en `GestionTurnos` u `Operaciones`.
- Para Turnos, el modal no recibiría total ni pagos desde los serializers de
  agenda actuales, por lo que su cálculo local de saldo no sería autoridad.
- `HistorialPagos` suma las filas recibidas y llama al resultado “Total caja”,
  incluyendo transferencias y sin estados/reversiones. Si la API pagina, el
  total sería sólo el de la página cargada.
- La ruta `/admin/caja` sólo exige autenticación en frontend; backend restringe
  por `is_staff`. No usa `view_financial_reports`.
- Reportes sí usa el permiso en routing frontend, pero el backend usa
  `IsAdminUser`; sus “ingresos” provienen de totales de órdenes completadas, no
  de Pagos reconciliados.
- Configuración muestra monto fijo de seña y plazo bajo
  `manage_configuration`; no separa `manage_payment_configuration`.
- No existe UI de `PaymentIntent`, conciliación o confirmación de seña.

### 2.7 Caja actual

No se encontraron modelos de:

- caja o sesión de caja;
- apertura/cierre;
- ingreso/egreso;
- arqueo;
- responsable de turno de caja;
- saldo inicial/final;
- diferencias de efectivo.

La palabra “Caja” nombra una vista de `Pago`; no representa control de efectivo.

---

## 3. Responsabilidades separadas

| Concepto | Responsabilidad | ¿Es hecho financiero? |
|---|---|---:|
| `PaymentPolicy` | Define modos, cálculo de seña, moneda, expiración y medios permitidos. | No |
| `PaymentIntent` | Obligación y umbral financiero inmutables para un HOLD. | No |
| `Pago` | Dinero recibido/evidencia y su conciliación. | Sí |
| `SlotHold` | Reserva temporal de agenda. | No |
| `Turno` | Cita operativa creada al consumir el HOLD. | No |
| `CashSession` futuro | Apertura, cierre y arqueo físico. | Agrega hechos; no es necesario en v1 |
| `Refund` futuro | Devolución parcial/total trazable. | Sí |

Ni el Intent debe fingir que recibió dinero ni un Pago aislado debe decidir la
agenda.

---

## 4. Modelo mínimo `PaymentIntent`

### 4.1 Campos

| Campo | Propósito |
|---|---|
| `id` y `public_id` opaco | Identidad interna y referencia pública segura. |
| `solicitud_tecnica` FK `PROTECT` | Solicitud aprobada de origen. |
| `slot_hold` FK `PROTECT` | HOLD al que pertenece. |
| `cliente` FK `PROTECT` | Dueño financiero; debe coincidir con solicitud/HOLD. |
| `mode` | `DEPOSIT` o `FULL`. |
| `total_amount_snapshot` | Total contractual inmutable. |
| `required_amount` | Umbral reconciliado para aprobación. |
| `currency` | Código ISO-4217 de tres letras. |
| `status` | `CREATED`, `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `CANCELLED`. |
| `policy` FK `PROTECT` | Versión de política aplicada. |
| `policy_snapshot` o columnas explícitas | Parámetros exactos usados en el cálculo. |
| `expires_at` | Vencimiento fijo y nunca posterior al HOLD. |
| `created_at`, `pending_at`, `approved_at` | Timestamps semánticos. |
| `terminal_at`, `terminal_reason` | Causa de rechazo, expiración o cancelación. |
| `idempotency_key` | Retry seguro de creación. |
| `created_by` nullable | Actor o sistema que originó el Intent. |

El core puede permanecer agnóstico de proveedor. Si se desea reservar la
abstracción, usar sólo un `provider_code` genérico nullable. IDs, payloads y
eventos de un proveedor pertenecen a un futuro `ProviderPaymentAttempt`, no a
columnas específicas del Intent interno.

### 4.2 Líneas financieras

Agregar `PaymentIntentLine` inmutable:

- Servicio y orden;
- nombre snapshot;
- cantidad;
- precio unitario snapshot;
- descuento explícito;
- subtotal bruto y neto;
- moneda.

Los ajustes globales deben persistirse como líneas/ajustes identificables, no
como una resta sin causa. No incluir fórmulas técnicas ni datos sensibles.

### 4.3 Constraints

- `total_amount_snapshot > 0`;
- `required_amount > 0`;
- `required_amount <= total_amount_snapshot`;
- moneda de Intent y líneas idéntica;
- suma de líneas/ajustes igual al total snapshot;
- `created_at < expires_at <= slot_hold.expires_at` validado en servicio;
- Cliente, solicitud y HOLD coherentes;
- una sola obligación no terminal por HOLD;
- como máximo un Intent `APPROVED` por HOLD;
- `approved_at` sólo y obligatoriamente en `APPROVED`;
- timestamp/causa terminal coherentes con estado;
- `idempotency_key` única;
- líneas únicas por orden lógico;
- no borrado físico.

Las coherencias entre tablas requieren servicio transaccional además de checks
locales. La unicidad parcial de estados no terminales sirve como última defensa
ante carreras.

### 4.4 Mutabilidad

Son inmutables:

- origen y Cliente;
- HOLD y solicitud;
- líneas/precios/descuentos;
- total, modo, required amount y moneda;
- policy/version/snapshot;
- fecha de creación y vencimiento;
- idempotency key.

Sólo cambian estado, timestamps/causa de transición y referencias operativas
controladas. No se permite `QuerySet.update` genérico, edición en admin ni
delete. Las transiciones pasan por servicios auditados.

---

## 5. Política parametrizable de pago

### 5.1 Modelo recomendado

No seguir ampliando el singleton mutable con booleanos ambiguos. Crear
`PaymentPolicy` versionada y publicable, con una única versión vigente:

| Campo | Valores/semántica |
|---|---|
| `version` | Identificador único e inmutable. |
| `allowed_mode` | `DEPOSIT_ONLY`, `FULL_ONLY`, `DEPOSIT_OR_FULL`. |
| `deposit_kind` | `FIXED` o `PERCENTAGE`, sólo si se admite seña. |
| `deposit_value` | Decimal positivo; monto o porcentaje según kind. |
| `fixed_exceeds_total_behavior` | Regla explícita: `REJECT` o `CAP_TO_TOTAL`. |
| `currency` | Moneda única de la política. |
| `intent_ttl_minutes` | Ventana financiera, acotada por el HOLD. |
| `enabled_manual_methods` | Medios internos habilitados. |
| `status` | `DRAFT`, `PUBLISHED`, `RETIRED`. |
| `published_at`, `created_by` | Gobierno y trazabilidad. |

Evitar combinaciones como `solo_sena=true`, `solo_total=true` y
`permite_ambos=true`. Un enum exclusivo expresa la política sin estados
imposibles.

Validaciones:

- `FULL_ONLY`: `deposit_kind` y `deposit_value` deben ser nulos;
- cualquier política que permita `DEPOSIT` exige exactamente kind y value;
- porcentaje mayor que cero y no mayor que 100;
- monto fijo mayor que cero;
- comportamiento explícito cuando fijo excede total;
- TTL positivo;
- moneda válida;
- al menos un medio habilitado para uso manual si ese canal está activo.

### 5.2 Versionado y snapshot

La política debe versionarse. Publicar crea una nueva versión; no modifica una
publicada. Cada Intent guarda FK y snapshot de los parámetros relevantes.

Cambiar política o precios después de crear el Intent sólo afecta Intents
nuevos. Esto permite explicar y auditar exactamente por qué se exigió un monto.

Los campos actuales `monto_sena` y `tiempo_limite_pago_sena` pueden alimentar
una migración inicial explícita, pero no deben coexistir indefinidamente como
segunda autoridad.

---

## 6. Cálculo del monto requerido

### 6.1 Total snapshot

Al crear el Intent:

1. bloquear solicitud, HOLD, Servicios y política vigente;
2. leer precios actuales autorizados en backend;
3. aplicar sólo descuentos verificables y vigentes;
4. cuantizar cada importe según moneda;
5. persistir líneas y total;
6. calcular `required_amount` una sola vez.

Como la solicitud técnica actual sólo guarda nombre de Servicio y no precio, el
primer compromiso financiero nace al crear el Intent. Un cambio previo a ese
momento puede afectar el precio; un cambio posterior no.

### 6.2 Fórmulas

```text
FULL:
required_amount = total_amount_snapshot

DEPOSIT + PERCENTAGE:
required_amount = round_currency(total_amount_snapshot * percentage / 100)

DEPOSIT + FIXED:
required_amount = fixed_amount
```

Si el fijo supera el total:

- `REJECT`: no crear Intent y reportar configuración incompatible;
- `CAP_TO_TOTAL`: required igual al total y registrar esa regla en snapshot.

No aplicar `min()` silencioso. La política debe decir cuál comportamiento usa.

Se rechazan total/required negativos o cero, porcentaje inválido, moneda
inconsistente, descuentos superiores al subtotal y desbordes de precisión.
Ningún monto llega como autoridad desde frontend.

---

## 7. Snapshot financiero

El Intent debe permitir reconstruir sin consultar precios actuales:

- Servicios, orden y nombres;
- precios unitarios;
- descuentos/ajustes y causa;
- subtotal por línea;
- total;
- versión y parámetros de política;
- modo elegido;
- required amount;
- moneda;
- fecha de cotización/creación;
- vencimiento.

Los snapshots son datos contractuales, no caché. No se recomputan
históricamente ni se actualizan en cascada.

---

## 8. Relación con `SlotHold`

### 8.1 Cardinalidad segura

- cada `PaymentIntent` pertenece a exactamente un HOLD;
- un HOLD puede tener varios Intents históricos terminales;
- sólo puede tener un Intent no terminal (`CREATED`/`PENDING`);
- sólo puede tener un Intent `APPROVED`;
- cada Intent puede tener varios Pagos;
- retry con la misma idempotency key reutiliza el mismo Intent;
- crear un Intent diferente mientras hay otro activo devuelve conflicto;
- tras `REJECTED` puede crearse otro sólo si HOLD y solicitud siguen vigentes,
  y únicamente como reemplazo atómico permitido por política.

Permitir historial múltiple evita mutar/revivir un intento rechazado. La
unicidad parcial y el lock del HOLD evitan dos obligaciones activas.

`CANCELLED` libera el HOLD. `REJECTED` también lo libera salvo que el mismo
command cree inmediatamente un Intent de reemplazo autorizado. No debe quedar
un HOLD bloqueando sin una obligación utilizable.

### 8.2 Vencimientos relativos

```text
intent.expires_at = min(
    created_at + policy.intent_ttl,
    hold.expires_at
)
```

En v1 se recomienda que el vencimiento operativo coincida con el tiempo
restante del HOLD. Si el Intent vence antes, debe liberar el HOLD, salvo que una
política futura implemente explícitamente un retry dentro de la misma ventana.
No conviene dejar agenda bloqueada sin obligación pagable.

Si el HOLD vence primero, el Intent deja de ser aprobable aunque su estado aún
no haya sido materializado. La regla defensiva siempre revisa ambos relojes.

---

## 9. Estados e invariantes de `PaymentIntent`

### 9.1 Transiciones

```text
CREATED -> PENDING
CREATED -> CANCELLED
CREATED -> EXPIRED

PENDING -> APPROVED
PENDING -> REJECTED
PENDING -> CANCELLED
PENDING -> EXPIRED
```

`APPROVED`, `REJECTED`, `EXPIRED` y `CANCELLED` son terminales. Nunca se
resucitan; un nuevo intento crea otra fila.

### 9.2 Significado y autoridad

| Estado/transición | Significado | Autoridad |
|---|---|---|
| `CREATED` | Obligación calculada, sin pago/evidencia en proceso. | Servicio interno tras solicitud/HOLD válidos. |
| `CREATED -> PENDING` | Existe pago/evidencia o intento de cobro aún no conciliado. | Servicio interno; futuro adapter de provider sólo a través del servicio. |
| `PENDING -> APPROVED` | Suma reconciliada alcanzó `required_amount`. | Servicio de conciliación; nunca campo enviado por usuario. |
| `PENDING -> REJECTED` | El intento se cerró sin cumplir la obligación. | Revisor autorizado o adapter futuro verificado. |
| `* -> EXPIRED` | Reloj de Intent/HOLD venció. | Sistema/command/defensa transaccional. |
| `CREATED/PENDING -> CANCELLED` | Se abandona antes de aprobación. | Cliente propietario dentro de política, sistema o permiso explícito. |

Un empleado registra o revisa hechos; no escribe arbitrariamente
`PaymentIntent.status=APPROVED`.

### 9.3 Invariantes

1. Intent activo requiere HOLD `ACTIVE` y no vencido.
2. Intent vencido o con HOLD vencido nunca se aprueba.
3. `APPROVED` requiere suma reconciliada en misma moneda mayor o igual a
   `required_amount`.
4. En v1 la suma neta reconciliada no supera el total snapshot.
5. `APPROVED` no implica saldo total cero en modo `DEPOSIT`.
6. `APPROVED` no confirma ni crea Turno.
7. Estados terminales no vuelven a estados activos.
8. Frontend no calcula montos autoritativos ni aprueba.

---

## 10. Modelo objetivo de `Pago`

### 10.1 Reutilización

El nombre, tabla histórica y relación con órdenes pueden conservarse mediante
una migración cuidadosa, pero el modelo actual no puede reutilizarse sin
cambios sustanciales.

Para reservas técnicas:

| Campo | Diseño recomendado |
|---|---|
| `payment_intent` FK `PROTECT` | Obligación a la que se aplica. |
| `turno` FK `PROTECT`, nullable | Turno resultante cuando exista; debe coincidir con el HOLD consumido. |
| `amount` | Decimal positivo e inmutable. |
| `currency` | Igual al Intent. |
| `method` | `CASH`, `BANK_TRANSFER`, `EXTERNAL_CARD`, `OTHER`, futuro provider. |
| `purpose` | `CONFIRMATION` o `BALANCE`; no un booleano ambiguo. |
| `status` | `PENDING_RECONCILIATION`, `RECONCILED`, `REJECTED`, `REVERSED`. |
| `occurred_at` | Cuándo se recibió/observó el pago. |
| `recorded_at`, `recorded_by` | Quién y cuándo lo registró. |
| `reconciled_at`, `reconciled_by` | Quién lo aceptó como hecho válido. |
| `manual_reference` | Referencia segura normalizada cuando aplica. |
| `provider_code/reference` | Abstracción futura, nullable y única por provider. |
| `receipt` | Evidencia privada opcional/obligatoria según medio. |
| `idempotency_key` | Retry de registro. |
| `terminal_reason` | Rechazo/reversión sin datos sensibles. |

Los importes y referencias son inmutables. Una corrección no edita el Pago: lo
rechaza/revierte con evento compensatorio.

### 10.2 Compatibilidad con órdenes

`Pago` sirve también a `OrdenCompra`, fuera del flujo de agenda. Hay dos caminos:

1. migrar órdenes a una obligación financiera común en un incremento propio; o
2. mantener temporalmente `orden` como origen legacy y exigir exactamente uno
   entre `payment_intent` y `orden`.

Para BH-058 B se recomienda el segundo, sin tocar stock. `turno` deja de ser un
origen alternativo y pasa a ser referencia derivada del Intent. Pagos Turno-only
preexistentes requieren migración/reconciliación antes de aplicar el constraint.

`on_delete=PROTECT` debe sustituir `CASCADE` para hechos reconciliados.

### 10.3 Constraints

- `amount > 0`;
- currency igual a Intent;
- exactamente un contexto financiero;
- idempotency key única;
- `(provider_code, provider_reference)` único cuando exista;
- referencia manual normalizada única dentro del medio/institución cuando el
  medio lo permita;
- timestamps/actor coherentes con estado;
- `RECONCILED` exige `reconciled_by/at`;
- no delete físico;
- no importe neto por encima de total bajo lock.

---

## 11. Pago manual/presencial

### 11.1 Flujo base

1. actor autenticado con `gestion.register_payment` selecciona un Intent válido;
2. backend bloquea solicitud, HOLD e Intent;
3. verifica vigencia, moneda, medio habilitado y saldo;
4. valida monto/referencia/comprobante;
5. busca idempotency key y referencia repetida;
6. crea `Pago` con actor y evidencia;
7. concilia de acuerdo con el medio/permisos;
8. recalcula suma neta bajo el mismo lock;
9. si alcanza required amount, transiciona el Intent a `APPROVED`;
10. audita todo en la misma transacción.

No se acepta pago huérfano. Para un walk-in u otro caso real, el sistema crea
primero un Intent interno con snapshot; no se omite la obligación. Las órdenes
legacy son la excepción temporal ya identificada.

### 11.2 Medios

| Medio | Datos mínimos | Conciliación recomendada |
|---|---|---|
| Efectivo | monto, moneda, actor, fecha, idempotency key | Puede quedar `RECONCILED` al registrarlo un actor autorizado que recibió el efectivo. |
| Transferencia | monto, referencia y comprobante | Empieza pendiente; otro paso con autoridad de conciliación verifica el ingreso. |
| Tarjeta fuera del sistema | monto, referencia/voucher seguro, adquirente genérico | Pendiente o reconciliado según proceso interno explícito. Nunca guardar PAN/CVV. |
| Otro | medio configurado, referencia y motivo | Deshabilitado por defecto; requiere política explícita. |

El archivo debe ser `FileField` con validación de MIME/tamaño, almacenamiento
privado y acceso autorizado. No almacenar credenciales, números completos de
tarjeta ni datos bancarios sensibles.

---

## 12. `confirm_deposit` frente a `register_payment`

### 12.1 Semántica actual

- `register_payment`: existe como permiso, pero la implementación usa
  `is_staff`; conceptualmente crea una fila `Pago`.
- `confirm_deposit`: sólo existe como permiso y asignación de grupos. No valida
  comprobante, transferencia, seña ni transición alguna.

Por tanto, hoy no son operaciones superpuestas: una está implementada con
autorización incorrecta y la otra no está implementada.

### 12.2 Recomendación

**A. Conservar separados, con semántica estricta**, y planificar un nombre más
general para conciliación:

- `register_payment`: registrar recepción/evidencia de un Pago manual;
- `confirm_deposit`: aceptar o rechazar un Pago pendiente aplicado al umbral de
  confirmación, sin crear otra fila Pago.

El codename `confirm_deposit` es estrecho para modo FULL. En una evolución debe
migrarse a `reconcile_payment`; mientras exista por compatibilidad, su action
puede operar la obligación de confirmación tanto DEPOSIT como FULL y documentar
que no “confirma el Turno”.

Efectivo puede registrarse ya reconciliado por quien tenga
`register_payment`, porque el mismo actor observa el hecho físico. Transferencia
y tarjeta externa deben requerir el paso de conciliación. Si el negocio exige
doble control de efectivo, se requiere también el permiso de conciliación; debe
ser política explícita, no `is_staff`.

No se recomienda unificar ambos permisos: impediría separar captura de
evidencia de aprobación financiera.

---

## 13. Caja MVP

BH-058 B no necesita un subsistema Caja completo para confirmar una reserva.
Necesita:

- Pagos inmutables y reconciliables;
- actor de registro y conciliación;
- medio y moneda;
- timestamps y referencia;
- auditoría;
- consulta de ingresos reconciliados.

La UI debe llamarse inicialmente “Pagos” o “Ingresos registrados”, no “Caja”.
Puede mostrar:

- total reconciliado por período;
- total de efectivo separado de transferencias/tarjetas;
- pendientes, rechazados y reversados;
- actor y origen;
- saldo de cada obligación.

No puede afirmar saldo físico de caja porque faltan apertura, fondo inicial,
egresos, retiros, cierre y arqueo.

Si el negocio luego necesita caja física, crear por separado:

- `CashSession` con apertura/cierre/actor;
- `CashMovement` para ingresos, egresos y retiros;
- arqueo y diferencia;
- vínculo del Pago CASH al movimiento.

Ese diseño no es requisito de v1 y no debe bloquear BH-058 B.

---

## 14. Matriz exacta de permisos

La autoridad backend se basa en permisos efectivos y ownership, nunca en
`BusinessRole`, `is_staff` o `Personal.rol`. Los roles sólo entregan defaults.

| Operación | CLIENTE | EMPLEADO | PROFESIONAL | ADMINISTRADOR | Permiso individual | SISTEMA |
|---|---|---|---|---|---|---|
| Crear Intent propio | Sí, ownership + solicitud/HOLD propios y vigentes | Sólo con nuevo `create_payment_intent` si actúa por Cliente | Igual; no por ser Profesional | Sólo con permiso efectivo o actuación propia | Funciona si se asigna `create_payment_intent`, sujeto al objeto | Sí, mediante servicio |
| Ver estado propio | Sí, ownership | Con `register_payment` para el Intent que opera o `view_financial_reports` para lectura amplia | Igual | Sólo por permisos efectivos | Sí | Sí |
| Registrar pago manual | No | `register_payment` | Sólo si tiene `register_payment`; no por perfil | `register_payment` | Sí, aunque no sea staff | Sólo servicios internos identificados |
| Confirmar/rechazar evidencia | No | `confirm_deposit` | Sólo si tiene `confirm_deposit` | `confirm_deposit` | Sí | Adapter/servicio verificado en futuro |
| Cancelar Intent propio pendiente | Sí, ownership y estado permitido | Nuevo `cancel_payment_intent` | Igual | `cancel_payment_intent` | Sí | Sí por invalidación/expiración |
| Configurar política | No | No por defecto | No por defecto | `manage_payment_configuration` | Sí | Sólo migración/operación controlada |
| Ver historial/reportes globales | Sólo sus propios Pagos | `view_financial_reports` | `view_financial_reports` | `view_financial_reports` | Sí | Sí para jobs/reportes internos |

El acceso a archivos de comprobante requiere además alcance al Pago; no basta
con conocer su URL.

### 14.1 Defaults recomendados

- **EMPLEADO:** `register_payment`; `confirm_deposit` si su función incluye
  conciliación.
- **PROFESIONAL:** no recibir permisos financieros sólo por ser Profesional.
  La base actual los hereda de EMPLEADO; debe validarse con negocio y retirarse
  si no corresponde.
- **ADMINISTRADOR:** recibe configuración, reportes y operaciones por permisos
  efectivos; no por el nombre del rol en cada endpoint.
- **Permisos individuales:** siguen funcionando para cualquier cuenta activa y
  habilitada, aunque no sea `is_staff`.

La configuración base de grupos puede mantener defaults, pero código y UI
siempre consultan `user.has_perm`/permisos efectivos exactos.

---

## 15. Configuración de negocio y secretos

### En base de datos

- política seña/total versionada;
- tipo y valor de seña;
- regla de fijo mayor al total;
- moneda;
- TTL financiero;
- medios manuales habilitados;
- requisitos de comprobante/conciliación por medio.

### Configuración técnica/secrets

- credenciales de providers futuros;
- claves de firma;
- secretos de webhook;
- URLs privadas/técnicas cuando corresponda.

Los secrets permanecen en variables de entorno o gestor de secretos. No se
exponen en serializers, frontend ni tablas de configuración editables por
negocio.

---

## 16. Expiración de `PaymentIntent`

La vigencia efectiva exige simultáneamente:

```text
intent.status IN (CREATED, PENDING)
AND intent.expires_at > database_now
AND hold.state = ACTIVE
AND hold.expires_at > database_now
```

El command periódico sólo materializa estados; no es la fuente de seguridad.
Registro, conciliación y aprobación hacen chequeo defensivo bajo lock.

### A. Intent expira antes del HOLD

En v1: `Intent -> EXPIRED` y `Hold -> RELEASED` en la misma transacción. No se
mantiene agenda sin obligación pagable. Un retry requiere nuevo HOLD.

### B. HOLD expira antes del Intent

El Intent es efectivamente no aprobable. Se materializa `EXPIRED` con causa
`HOLD_EXPIRED`; no se consume ni recrea el HOLD.

### C. Ambos vencen

El proceso que adquiere locks en orden común materializa ambas transiciones.
Repeticiones devuelven `changed=false` y no duplican eventos.

### D. Pago llega tarde

Si realmente hubo movimiento de dinero, no se descarta. Se registra como Pago
pendiente de revisión con evento `PAYMENT_LATE_APPROVAL`, pero:

- no aprueba el Intent vencido;
- no consume ni recrea HOLD;
- no crea Turno;
- queda para devolución, crédito o conciliación manual según política futura.

Un dato tardío que es sólo retry del mismo pago retorna la fila existente.

---

## 17. Aprobación financiera y frontera con agenda

`PaymentIntent.APPROVED` significa únicamente:

```text
pagos netos reconciliados en la moneda correcta >= required_amount
```

No basta para confirmar un Turno. También se requiere:

- solicitud técnica aún válida;
- HOLD `ACTIVE` y no vencido;
- evaluación técnica vigente;
- Pagos conciliados no revertidos;
- consumo del HOLD y creación de Turno en una operación atómica.

BH-058 C debe invocar un command de dominio explícito. No usar signals, polling
del frontend ni una actualización independiente después de aprobar: el HOLD
podría vencer entre ambas operaciones.

Si la reconciliación que alcanza el umbral es parte del flujo confirmatorio,
la transición `Pago -> RECONCILED`, `Intent -> APPROVED`, consumo del HOLD y
creación del Turno deben integrarse en una única transacción de orquestación.

---

## 18. Pago parcial y saldo

### 18.1 Multiplicidad

Un Intent admite varios Pagos. Esto soporta:

- varias entregas parciales hasta completar seña;
- seña y pago posterior del saldo;
- combinación permitida de medios;
- pago total directo.

En modo `DEPOSIT`, alcanzar `required_amount` aprueba el Intent aunque quede
saldo del total. En modo `FULL`, required y total son iguales.

Pagos adicionales después de aprobación pueden asociarse al mismo Intent y al
Turno ya creado, hasta completar total. El estado del Intent permanece
`APPROVED`; no se vuelve a abrir.

### 18.2 Fórmula

```text
paid_reconciled =
    suma(Pago RECONCILED)
    - suma(Reversal/Refund COMPLETED)

confirmation_due = max(required_amount - paid_reconciled, 0)
balance = max(total_amount_snapshot - paid_reconciled, 0)
```

El saldo es una proyección desde hechos inmutables. Puede materializarse como
caché sólo con actualización transaccional y prueba de reconciliación; nunca es
la fuente única.

`Turno.saldo_pendiente` y `monto_abonado` deben clasificarse como legacy hasta
ser removidos o convertidos en caché derivada claramente marcada. No se escriben
desde frontend.

En v1 no aceptar sobrepago por encima del total. Propina, crédito a favor y
ajustes requieren reglas explícitas futuras.

---

## 19. Reversiones y reembolsos

No existe soporte actual de devolución, refund ni reversión financiera. La
reversión genérica de `Auditoria` no debe usarse sobre Pagos.

`Pago` necesita estado, pero una devolución no debe borrar la fila ni convertir
su monto en negativo. Diseño futuro:

- `PaymentReversal` para corrección/reversión interna, con actor, causa y monto;
- `Refund` 1:N desde Pago para devoluciones parciales o totales;
- estado `REQUESTED`, `APPROVED`, `COMPLETED`, `REJECTED`;
- referencia externa/manual y timestamps;
- suma de refunds nunca superior al Pago neto.

Un Pago completamente revertido puede reflejar `REVERSED` como estado resumen,
pero el hecho compensatorio permanece separado. Pago tardío o duplicado queda
en revisión y no cuenta para saldo hasta resolverse.

BH-058 B sólo debe reservar este contrato y evitar decisiones que impidan 1:N;
no implementa reembolso.

---

## 20. Idempotencia

| Operación | Clave/defensa | Resultado de retry |
|---|---|---|
| Crear Intent | `idempotency_key` única + lock HOLD | Devuelve mismo Intent si payload/snapshot coincide; conflicto si no. |
| Registrar Pago manual | idempotency key única por comando | Devuelve mismo Pago, sin sumar otra vez. |
| Transferencia/tarjeta externa manual | referencia normalizada única por medio/institución | Misma referencia devuelve existente o conflicto si datos difieren. |
| Conciliar/rechazar | lock Pago + operation key/evento único | Estado terminal previo devuelve `changed=false`; nunca reaplica monto. |
| Cancelar | update condicional de estado + event key | Repetición no duplica auditoría ni libera dos veces. |
| Expirar | condición estado no terminal y reloj | Idempotente; workers concurrentes afectan una fila una vez. |

Doble click y retry de red quedan cubiertos por idempotency key. Dos empleados
que registran la misma transferencia quedan cubiertos por referencia única.

Efectivo no posee referencia externa natural. La idempotency key evita retries
del mismo command, pero no puede demostrar que dos empleados con claves
distintas describen el mismo billete. El lock y el límite de saldo reducen el
riesgo; la prevención completa requiere operación de caja/recibo y disciplina
operativa.

---

## 21. Concurrencia y orden de locks

Orden compatible con BH-058 A:

1. `SolicitudTecnicaReserva`;
2. `SlotHold`;
3. `PaymentIntent`;
4. Cliente;
5. Pagos afectados en orden de PK;
6. al consumir agenda: Servicios, Personal y tipos de equipamiento según A;
7. Turno resultante cuando corresponda.

### Casos

- **Dos Intents activos:** ambos bloquean HOLD; el primero inserta, el segundo
  ve el Intent o choca con unique parcial.
- **Pago manual simultáneo:** ambos bloquean Intent antes de consultar suma. El
  segundo ve el nuevo saldo y no excede required/total.
- **Cancelación vs Pago:** compiten por HOLD/Intent; sólo el ganador puede hacer
  transición desde estado no terminal.
- **Expiración vs aprobación:** update de aprobación exige Intent/HOLD vigentes
  contra reloj nuevo. Si expiró durante espera, no aprueba.
- **Saldo parcial concurrente:** agregar Pago y recalcular suma ocurre bajo lock
  de Intent; no se usa un read-modify-write sobre `Turno.saldo_pendiente`.
- **Reconciliación que confirma:** BH-058 C conserva los locks de Intent/HOLD
  hasta consumir el HOLD y crear Turno.

Todos los checks temporales usan un reloj nuevo después de esperar locks y una
condición final en base. Los servicios devuelven resultados de dominio sin
hacer rollback accidental de una expiración materializada.

---

## 22. Auditoría financiera

Eventos mínimos:

```text
PAYMENT_INTENT_CREATED
PAYMENT_INTENT_PENDING
PAYMENT_INTENT_APPROVED
PAYMENT_INTENT_REJECTED
PAYMENT_INTENT_EXPIRED
PAYMENT_INTENT_CANCELLED

PAYMENT_MANUAL_REGISTERED
PAYMENT_RECONCILED
PAYMENT_REVERSED
PAYMENT_LATE_APPROVAL
```

Cada evento registra:

- actor o actor de sistema;
- Intent, HOLD y solicitud;
- Pago cuando corresponda;
- monto y moneda;
- medio;
- estado anterior/nuevo;
- referencia segura truncada/hasheada cuando corresponda;
- causa/code;
- timestamp e idempotency key del comando.

No registrar payloads completos de provider, números de tarjeta, credenciales,
comprobantes binarios ni datos bancarios completos. La auditoría semántica se
crea en la misma transacción y no depende sólo del signal genérico.

---

## 23. Estados y campos legacy

Migración conceptual:

```text
Turno.esperando_sena
Turno.fecha_limite_pago
Configuracion.monto_sena
Turno.comprobante_pago
Turno.tipo_pago_registro
Turno.monto_abonado
Turno.saldo_pendiente

        ↓

SlotHold.ACTIVE
+ PaymentIntent.PENDING
+ Pago/PagoEvidence
+ saldo derivado
```

No migrar automáticamente por equivalencia textual:

- `esperando_sena` no prueba que exista obligación correcta;
- `comprobante_pago` no prueba recepción de dinero;
- `monto_abonado` puede divergir de filas `Pago`;
- `saldo_pendiente=0` puede significar “no calculado”;
- `es_sena` no prueba que el monto cumpla política.

Se requiere reporte de inconsistencias y conciliación antes de retirar campos.
Durante transición, el flujo nuevo no debe escribir ambas fuentes como si
fueran coautoritativas.

`pago_confirmado` o equivalente separado no existe. `Turno.confirmado` mezcla
resultado operativo/financiero por etiqueta, pero no conserva la prueba de qué
Pago lo originó.

---

## 24. UI futura mínima

### Cliente

- elegir `DEPOSIT` o `FULL` sólo cuando la política permita ambos;
- ver líneas, total, required amount, moneda y vencimiento calculados por backend;
- ver estado del Intent y Pagos propios;
- subir evidencia cuando el medio lo requiera;
- ver saldo derivado;
- cancelar mientras la transición sea permitida;
- nunca editar importes ni marcar `APPROVED`.

### Empleado/Profesional autorizado

- buscar una obligación válida;
- registrar Pago manual con `register_payment`;
- ver saldo/required antes de registrar;
- conciliar evidencia sólo con `confirm_deposit`;
- ver error seguro ante vencimiento/duplicado;
- no recibir botones financieros sólo por `is_staff` o perfil Personal.

### Administrador autorizado

- publicar nueva versión de política con
  `manage_payment_configuration`;
- consultar Pagos/reportes con `view_financial_reports`;
- operar pagos sólo si además posee permisos operativos;
- no editar Intents/Pagos directamente desde CRUD genérico.

Los contadores y saldos se sirven desde backend. El frontend puede formatear,
pero no sumar como autoridad.

---

## 25. Matriz de tests propuesta

### `PaymentIntent`

- creación desde solicitud aprobada + HOLD vigente;
- rechazo sin HOLD, con HOLD vencido o solicitud inválida;
- DEPOSIT/FULL según cada modalidad de política;
- porcentaje y fijo, redondeo y fijo mayor al total;
- required positivo y no superior a total;
- moneda consistente;
- snapshot de Servicios, precios, descuentos y política;
- cambios posteriores no alteran Intent;
- un activo por HOLD y un aprobado por HOLD;
- retry devuelve la misma fila;
- estados válidos e imposibilidad de resurrección;
- expiración defensiva con job caído.

### `Pago`

- efectivo manual reconciliado con actor;
- transferencia pendiente con referencia/evidencia;
- conciliación y rechazo de evidencia;
- duplicado por idempotency key;
- duplicado por referencia;
- monto cero/negativo, moneda distinta y fecha inválida;
- suma no supera total;
- varios Pagos alcanzan seña;
- Pago total directo;
- seña + saldo posterior;
- saldo derivado excluye rechazados e incorpora reversiones;
- Pago no se borra por borrar origen;
- no existe Pago sin obligación salvo contexto Orden legacy controlado.

### Permisos

- `register_payment` permite registrar sin requerir `is_staff`;
- `is_staff` sin `register_payment` recibe 403;
- `confirm_deposit` no concede registrar Pago;
- `register_payment` no concede conciliar transferencia;
- `manage_payment_configuration` publica política, pero no registra Pagos;
- `view_financial_reports` ve historial global, pero no opera;
- permisos individuales funcionan para cada acción;
- BusinessRole/Personal.rol sin permiso no autoriza;
- Cliente sólo ve/crea Intent propio;
- comprobante de otro Cliente no es accesible.

### Concurrencia PostgreSQL

- dos Intents para un HOLD: uno activo;
- doble click de Pago manual: una fila;
- dos empleados con misma transferencia: una fila;
- dos Pagos parciales simultáneos no sobrepagan;
- cancelación vs registro;
- expiración vs conciliación;
- HOLD expira mientras se aprueba;
- reconciliación vs reversión;
- orden de locks sin deadlock.

### Caja/reportes

- sólo suma `RECONCILED` neto;
- separa efectivo de otros medios;
- usa período y timezone de negocio;
- paginación no altera totales agregados del backend;
- reportes requieren `view_financial_reports`;
- no presenta el total multimedio como saldo físico de caja.

---

## 26. Frontera BH-058 C

BH-058 B termina con:

- política interna versionada;
- Intent con monto y vigencia inmutables;
- Pago manual y conciliación;
- saldo derivado;
- permisos y auditoría;
- contrato de aprobación financiera con HOLD.

BH-058 B no debe:

- crear una preferencia externa;
- procesar webhooks;
- confiar en estados o importes enviados por un provider;
- validar firma/operación externa;
- confirmar Turno desde un callback externo;
- incorporar IDs específicos de un proveedor al core salvo abstracción genérica.

BH-058 C agregará adapters/intentos externos, persistencia de eventos del
provider, validación oficial e invocación del mismo servicio interno de
reconciliación/orquestación. El provider nunca será autoridad directa sobre
agenda.

---

## 27. Decisiones finales

### Inventario financiero actual

Existe un `Pago` básico compartido por órdenes y Turnos, campos financieros
legacy en `Turno`, una configuración fija de seña y pantallas de historial. No
existe obligación financiera, conciliación, saldo confiable ni Caja real. Los
cuatro permisos financieros existen pero hoy están sustituidos total o
parcialmente por `is_staff`/`IsAdminUser`.

### Arquitectura `PaymentIntent`/`Pago`

`PaymentIntent` será la obligación inmutable vinculada a solicitud y HOLD;
`Pago` será el hecho financiero 1:N, con moneda, medio, estado, actor,
referencia, evidencia e idempotencia. La suma reconciliada aprueba el Intent;
no confirma Turno.

### Política de seña/total

Usar `PaymentPolicy` publicada y versionada con enum
`DEPOSIT_ONLY`/`FULL_ONLY`/`DEPOSIT_OR_FULL`, seña `FIXED` o `PERCENTAGE`, regla
explícita para fijo mayor al total, moneda, TTL y medios. Cada Intent captura el
snapshot exacto y nunca se recalcula.

### Tratamiento de caja

Para v1, Pago + actor + medio + conciliación + auditoría es suficiente. La UI
debe reportar ingresos y efectivo por separado, sin afirmar apertura/cierre o
saldo físico. Caja completa queda fuera hasta existir requerimiento de arqueo,
egresos y turnos de caja.

### Semántica `confirm_deposit` vs `register_payment`

Conservar separados: `register_payment` registra dinero/evidencia;
`confirm_deposit` concilia o rechaza evidencia pendiente. El segundo debe
evolucionar en nombre hacia `reconcile_payment` para cubrir también FULL. Ningún
endpoint usa `is_staff` como sustituto.

### Matriz de permisos

Ownership habilita al Cliente sólo sobre sus Intents/Pagos. Operaciones manuales
requieren `register_payment`; conciliación `confirm_deposit`; política
`manage_payment_configuration`; lectura global `view_financial_reports`.
Administrador, Empleado y Profesional actúan únicamente por permisos efectivos,
incluidos permisos individuales.

### Expiración

Intent y HOLD se validan por reloj en cada operación. El Intent nunca vence
después del HOLD. En v1, expirar el Intent libera el HOLD; expirar el HOLD
invalida el Intent. Un pago tardío se registra para revisión, pero no reserva
agenda ni crea Turno.

### Idempotencia/concurrencia

Usar keys únicas, referencias normalizadas, constraints parciales y locks en
orden solicitud → HOLD → Intent → Cliente → Pagos → recursos de agenda. Suma,
conciliación, expiración y cancelación ocurren transaccionalmente; no se actualiza
un saldo mutable mediante read-modify-write.

### Frontera con C

C implementará el adapter externo, eventos y validación oficial. Reutilizará la
obligación, Pago y orquestación internos. B no crea preferencias, no procesa
webhooks y no confirma Turnos desde proveedores.

### Primer incremento recomendado

1. Crear `PaymentPolicy` versionada, `PaymentIntent` y líneas snapshot con
   constraints e índices.
2. Ampliar/migrar `Pago` con Intent, moneda, estado, actor, referencias,
   evidencia, `PROTECT` e idempotencia, preservando órdenes legacy.
3. Implementar servicios transaccionales de crear/cancelar/expirar Intent,
   registrar Pago y conciliar, sin integración externa.
4. Aplicar `register_payment`, `confirm_deposit`,
   `manage_payment_configuration` y `view_financial_reports` en backend y UI;
   eliminar `is_staff` como autoridad financiera.
5. Exponer saldo y totales calculados por backend; renombrar Caja a historial de
   Pagos mientras no exista caja física.
6. Añadir command idempotente de expiración y defensas contra reloj/HOLD,
   separado de `limpiar_turnos`.
7. Cubrir snapshots, seña/total, pagos parciales, permisos e interleavings con
   tests PostgreSQL reales.
8. Preparar el command atómico que C usará para reconciliar, aprobar y consumir
   el HOLD, sin implementar todavía ningún provider.
