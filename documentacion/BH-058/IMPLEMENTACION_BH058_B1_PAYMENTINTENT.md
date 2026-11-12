# BH-058 B1 — PaymentPolicy + PaymentIntent + snapshots

Fecha de cierre: 2026-10-26

## Alcance implementado

Se implementó exclusivamente el contrato financiero interno anterior al registro
de dinero:

```text
PaymentPolicy versionada
        ↓ snapshot
PaymentIntent vinculado a SlotHold
        ↓ 1:N
PaymentIntentLine inmutable
```

B1 crea, consulta, cancela y expira obligaciones. No aprueba Intents, no registra
Pagos y no consume el HOLD mediante A2.

## PaymentPolicy

`PaymentPolicy` incorpora:

- versión única y estados `DRAFT`, `PUBLISHED`, `RETIRED`;
- modos `DEPOSIT_ONLY`, `FULL_ONLY`, `DEPOSIT_OR_FULL`;
- seña `FIXED` o `PERCENTAGE` y comportamiento fijo `REJECT` o
  `CAP_TO_TOTAL`;
- moneda, TTL del Intent y medios manuales habilitados;
- actor de creación, fecha de creación y fecha de publicación.

Las monedas soportadas son ARS, BOB, BRL, EUR, USD y UYU con dos decimales, y
CLP/PYG con cero decimales. Los medios configurables son `CASH`,
`BANK_TRANSFER`, `EXTERNAL_CARD` y `OTHER`; B1 sólo los guarda en el snapshot y
no los consume.

`publish_payment_policy()` exige exclusivamente el permiso efectivo
`gestion.manage_payment_configuration`. No usa `is_staff`, `BusinessRole` ni
`Personal.rol`. La publicación bloquea las policies, valida el borrador, retira
la publicada anterior y publica la nueva dentro de una única transacción. Sólo
puede existir una policy `PUBLISHED`.

Una policy publicada o retirada no puede modificarse ni eliminarse. También se
bloquearon escapes ORM por `update`, `bulk_update`, `bulk_create` y
`update_or_create`. Retirar una versión no altera sus parámetros ni su fecha
original de publicación.

## PaymentIntent y líneas

`PaymentIntent` contiene:

- `public_id`, solicitud, HOLD, Cliente y policy protegidos;
- snapshot explícito de policy;
- modalidad `DEPOSIT` o `FULL`;
- total, monto requerido y moneda calculados por backend;
- estados previstos por el contrato: `CREATED`, `PENDING`, `APPROVED`,
  `REJECTED`, `EXPIRED`, `CANCELLED`;
- vencimiento y timestamps de ciclo de vida;
- razón terminal, clave de idempotencia y actor de creación.

B1 sólo crea en `CREATED` y realiza transiciones a `CANCELLED` o `EXPIRED`.
`PENDING`, `APPROVED` y `REJECTED` quedan modelados, pero B1 no expone ninguna
operación que los produzca.

Cada `PaymentIntentLine` conserva Servicio, orden, nombre, cantidad, precio
unitario, descuento, subtotal y moneda. No existe una fuente confiable de
promociones para este contrato, por lo que el descuento es siempre cero. No se
reutilizan ni inventan promociones de productos.

Intent y líneas se crean sólo mediante el servicio canónico. Después de
persistirse no admiten `save`, `update`, `bulk_update`, `bulk_create`,
`update_or_create` ni `delete`; tampoco se pueden anexar líneas por creación ORM
directa. Las FK contractuales usan `PROTECT` y la base aplica constraints de
montos, cardinalidad, timestamps y estados.

## Creación y cálculo

`create_payment_intent()` respeta el orden global:

1. bloquea `SolicitudTecnicaReserva`;
2. bloquea `SlotHold`;
3. bloquea Intents del HOLD;
4. bloquea Cliente;
5. bloquea Servicios y policies en orden estable.

Después de esperar los locks vuelve a leer el reloj PostgreSQL y valida:

- ownership y actividad del Cliente;
- HOLD `ACTIVE` y vigente;
- solicitud y evaluación técnica vigentes;
- correspondencia exacta de Servicios del HOLD;
- Servicios activos y precios positivos;
- policy publicada y modalidad permitida.

El cliente HTTP sólo informa `slot_hold_public_id`, `mode` e
`Idempotency-Key`. Total, required, moneda, policy y precios nunca se aceptan
desde frontend.

Las fórmulas son:

```text
FULL                  required = total
DEPOSIT + PERCENTAGE  required = total × percentage / 100
DEPOSIT + FIXED       required = fixed
```

Todos los importes se cuantizan con `ROUND_HALF_UP` según la unidad menor de la
moneda. Se rechazan total o required no positivos. Un fijo mayor al total se
rechaza salvo `CAP_TO_TOTAL`, que lo limita explícitamente al total.

`expires_at` es el mínimo entre el TTL de policy y `hold.expires_at`.

## Cardinalidad, idempotencia y concurrencia

- Un HOLD conserva historial de Intents terminales.
- Un índice único parcial permite un solo Intent `CREATED/PENDING` por HOLD.
- Otro índice único parcial reserva como máximo un `APPROVED` por HOLD para la
  integración futura.
- La misma clave y el mismo HOLD/modo devuelven el Intent original sin duplicar
  líneas ni auditoría.
- Reutilizar la clave con otro payload produce conflicto.
- HOLD vencido, liberado o consumido no puede crear un Intent.

Las carreras PostgreSQL verifican dos creaciones sobre el mismo HOLD, cancel vs
expire y una espera de lock que cruza el TTL. Los locks, constraints e
idempotencia dejan un único resultado válido y una única auditoría terminal.

## Cancelación y expiración

El Cliente propietario puede cancelar un Intent `CREATED/PENDING`. La
cancelación es idempotente si ya quedó `CANCELLED`, libera el HOLD con
`PAYMENT_INTENT_CANCELLED` y audita ambas transiciones.

Si el Intent vence antes que el HOLD, `expire_payment_intent()` lo deja
`EXPIRED`, libera el HOLD con `PAYMENT_INTENT_EXPIRED` y usa la razón terminal
`INTENT_EXPIRED`. Si el HOLD ya venció, materializa su vencimiento y usa
`HOLD_EXPIRED` en el Intent. Un HOLD liberado o consumido tampoco mantiene un
Intent efectivo vigente.

La liberación directa de un HOLD con Intent no terminal se rechaza con
`ACTIVE_PAYMENT_INTENT_EXISTS`; el Cliente debe cancelar el Intent para conservar
la transición y auditoría financiera. No se agregó scheduler B1.

## API mínima

| Operación | Endpoint | Contrato |
|---|---|---|
| Crear | `POST /api/gestion/payment-intents/` | HOLD propio, `mode` e `Idempotency-Key`; no acepta montos ni precios. |
| Consultar | `GET /api/gestion/payment-intents/{public_id}/` | Sólo propietario; devuelve snapshots, líneas, estado efectivo y countdown informativo. |
| Cancelar | `POST /api/gestion/payment-intents/{public_id}/cancel/` | Sólo propietario y body vacío. |

No existen list, PUT, PATCH, DELETE ni CRUD genérico de policy o Intent.

## Auditoría

Se registran los eventos:

- `PAYMENT_POLICY_PUBLISHED`;
- `PAYMENT_INTENT_CREATED`;
- `PAYMENT_INTENT_CANCELLED`;
- `PAYMENT_INTENT_EXPIRED`.

La clave de idempotencia no se guarda en claro en auditoría; se registra su hash
SHA-256. Los eventos incluyen IDs contractuales, versión de policy, montos,
moneda, transición, razón, actor y timestamp.

## Archivos B1

- `bohemiacore/gestion/models.py`;
- `bohemiacore/gestion/payment_intent_services.py`;
- `bohemiacore/gestion/slot_hold_services.py`;
- `bohemiacore/gestion/slot_hold_consumption_services.py`;
- `bohemiacore/gestion/serializers.py`;
- `bohemiacore/gestion/views.py`;
- `bohemiacore/gestion/urls.py`;
- `bohemiacore/gestion/migrations/0029_alter_slothold_release_reason_paymentpolicy_and_more.py`;
- `bohemiacore/gestion/tests/test_payment_intents.py`;
- `bohemiacore/gestion/tests/test_payment_intent_concurrency.py`.

La única extracción sobre A2 fue mover la precondición técnica compartida a
`technical_request_is_current_for_hold()`; A2 la reutiliza sin ser invocado por
finanzas.

## Pruebas ejecutadas

Todas las suites usaron PostgreSQL real,
`C:/Users/AldoA/Desktop/Bohemia-hair/venv/Scripts/python.exe`, salida UTF-8 y
base de test reconstruida antes de las regresiones sensibles a permisos.

| Suite | Resultado |
|---|---:|
| B1 funcional: policy, fórmulas, snapshots, ownership, API, cancel/expire e inmutabilidad | 18/18 |
| B1 concurrencia PostgreSQL | 3/3 |
| B1 + A1 + A2 funcional | 52/52 |
| A1 + A2 + B1 concurrencia PostgreSQL | 17/17 |
| BH-057 completo | 92/92 |
| Skills, Turnos, disponibilidad, diagnóstico, roles y `/me/` | 164/164 |

Después del endurecimiento final de creación ORM se repitió B1 funcional y
concurrencia conjuntamente: 21/21.

## Checks técnicos

- `python manage.py check`: cero issues.
- `python manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- `python -m compileall -q gestion usuarios`: correcto.
- `git diff --check`: correcto; sólo avisos informativos CRLF/LF preexistentes.

## Frontera estricta

La revisión de imports, llamadas y diff confirma que B1 no agregó ni modificó
lógica de:

- `Pago` o pago manual;
- `registrar_pago` o `confirm_deposit`;
- conciliación;
- Mercado Pago;
- `ProviderPaymentAttempt` o `ProviderEvent`;
- stock o movimientos de stock;
- creación de Turno por pago.

El servicio productivo B1 no importa ni llama
`create_confirmed_turno_from_locked_hold`. Una prueba funcional usa A2 solamente
para construir el caso negativo de un HOLD previamente consumido. No se inició
B2, no se creó frontend y no se añadió integración con providers.

BH-058 B1 = VALIDADO
