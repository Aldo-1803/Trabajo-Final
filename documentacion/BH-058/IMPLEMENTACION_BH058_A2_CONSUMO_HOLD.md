# BH-058 A2 — Consumo canónico de SlotHold

## Resultado

Se implementó una única primitiva interna:

```python
create_confirmed_turno_from_locked_hold(
    *,
    hold,
    operation_key,
    actor=None,
)
```

La primitiva consume un `SlotHold` `ACTIVE` y vigente, crea exactamente un
`Turno` en estado `CONFIRMADO`, crea todos sus `DetalleTurno`, enlaza el Turno
al HOLD y lleva el HOLD a `CONSUMED` dentro de la misma transacción.

No se agregó un endpoint de confirmación. La capacidad queda disponible sólo
como servicio de dominio interno para un flujo financiero posterior.

## Persistencia y constraints

La migración
`gestion/migrations/0028_remove_slothold_slot_hold_state_timestamps_ok_and_more.py`
agrega `SlotHold.consumption_idempotency_key`, nullable y única.

El constraint de coherencia de estados exige:

- `CONSUMED`: `consumed_turno`, `consumed_at` y
  `consumption_idempotency_key` obligatorios;
- `ACTIVE`, `RELEASED` y `EXPIRED`: los tres campos de consumo deben ser
  nulos;
- los timestamps y la razón terminal deben corresponder al estado persistido.

El `OneToOneField` `consumed_turno` existente desde A1 garantiza tanto un solo
Turno por HOLD como un solo HOLD consumidor por Turno. Las transiciones de los
servicios son terminales y nunca reactivan un HOLD.

## Locks y reloj

El consumo respeta el orden canónico de A2:

1. `SolicitudTecnicaReserva`;
2. `SlotHold`;
3. `Cliente`;
4. `Servicio`, ordenados por PK;
5. `Personal`;
6. `TipoEquipamiento`, ordenados por PK;
7. `Turno`, únicamente al resolver un retry ya consumido.

Después de adquirir los locks se toma un reloj nuevo mediante
`database_now()`, que en PostgreSQL usa `STATEMENT_TIMESTAMP()`.

Los writers canónicos de skills serializan sus cambios por `Personal`. Por
ello, la comprobación de skills realizada después del lock observa una
asignación anterior completa o la revocación ya confirmada, nunca un estado
intermedio.

## Revalidación bajo lock

Antes de crear el Turno se vuelve a validar:

- estado `ACTIVE` y `expires_at > database_now`;
- solicitud `APROBADA_TECNICAMENTE`;
- evaluación vigente, no superada, del mismo Cliente, fecha y Servicios;
- Cliente y usuario activos;
- Servicios del snapshot existentes y activos;
- Personal y usuario asociado activos;
- skills BH-056 vigentes con semántica AND multiservicio;
- duración total y fin coherentes con los snapshots del HOLD;
- horario laboral y flags de agenda;
- `BloqueoAgenda` global o del Personal;
- conflictos de Turno y de otros HOLDs para Personal y Cliente;
- capacidad de equipamiento usando las cantidades snapshot del HOLD.

La llamada a `TurnoAvailabilityService.validate_slot()` usa
`excluir_hold_id=hold.id`. De este modo el HOLD consumido no se bloquea a sí
mismo, pero los demás HOLDs vigentes continúan ocupando recursos.

## Creación canónica del Turno

Se extrajo `TurnoCreationService._create_from_locked_resources()` como builder
interno compartido. `TurnoCreationService.create()` conserva su comportamiento
legacy y ahora delega únicamente la persistencia del agregado a ese builder.

A2 no llama `create()` como caja negra: adquiere los locks en el orden de A2,
revalida y llama directamente al builder con datos derivados del HOLD.

El Turno se crea con:

- Cliente, Personal, fecha y hora obtenidos del HOLD;
- estado inicial `CONFIRMADO`;
- un `DetalleTurno` por cada `SlotHoldService`, conservando orden y duración
  snapshot;
- cero montos abonados y sin tipo de pago.

`DetalleTurno.precio_historico` sigue siendo obligatorio en el modelo actual.
Como A2 no es autoridad financiera, usa de forma mínima el `precio_base`
vigente del Servicio. BH-058 B deberá sustituir o fortalecer este punto con el
snapshot financiero autorizado; A2 no crea políticas ni intents de pago.

## Atomicidad y carrera de expiración

Turno y detalles se crean dentro de un savepoint. La transición final se hace
con un `UPDATE` condicional que exige simultáneamente:

```text
state = ACTIVE
AND expires_at > database_now
AND consumed_turno IS NULL
AND consumption_idempotency_key IS NULL
```

Si el `UPDATE` no afecta exactamente una fila, el savepoint revierte el Turno
y todos sus detalles. Luego se relee el HOLD:

- si venció, se materializa `EXPIRED` fuera del savepoint y se devuelve
  `HOLD_EXPIRED` sin lanzar una excepción que revierta esa transición;
- si cambió por otra causa, se devuelve un conflicto estable;
- nunca queda un Turno huérfano.

También se verificó el caso bloqueante en el que el consumo espera un lock y
cruza `expires_at`: no se crea Turno y el HOLD queda `EXPIRED`.

## Idempotencia

- Primera operación válida: crea el Turno y persiste la operation key.
- Retry con la misma operation key: bloquea el Turno vinculado y devuelve
  exactamente ese mismo registro con `created=False`.
- Otra operation key sobre el HOLD consumido: `HOLD_ALREADY_CONSUMED`.
- Reutilizar una operation key en otro HOLD: `OPERATION_KEY_REUSED`.
- Dos consumidores concurrentes producen un solo Turno, un solo conjunto de
  detalles, una sola notificación y un solo par de auditorías semánticas.

La operation key completa no se copia a auditoría; sólo se conserva su SHA-256.

## Expiración e invalidación

Un HOLD vencido se materializa como `EXPIRED` con razón `TTL_EXPIRED` y no crea
Turno.

Cuando la solicitud o evaluación deja de ser vigente, el HOLD pasa a
`RELEASED` con `TECHNICAL_REQUEST_INVALIDATED`. Cuando falla Cliente, Servicio,
Personal, skills, horario, bloqueo, equipamiento o disponibilidad, pasa a
`RELEASED` con `RESOURCE_INVALIDATED`. Cada transición queda auditada y evita
que un HOLD conocido como imposible siga ocupando hasta el TTL.

Si la invalidez se detecta cuando el TTL ya venció, prevalece `EXPIRED`.

## Notificación y auditoría

El signal legacy de `Turno` sólo notifica una transición posterior hacia
`CONFIRMADO`; no cubre un Turno insertado directamente en ese estado. A2 crea
por ello una notificación explícita y transaccional con `get_or_create`, usando
como identidad el HOLD. Un rollback elimina también la notificación y un retry
no la duplica.

Se registran exactamente una vez:

- `SLOT_HOLD_CONSUMED`;
- `TURN_CONFIRMED_FROM_HOLD`.

Ambos eventos incluyen IDs de HOLD, solicitud, evaluación, Turno, Cliente,
Personal y Servicios; intervalo, transición, actor/sistema, timestamp y hash de
la operation key. No incorporan información clínica ni credenciales.

## Pruebas

Todas las pruebas se ejecutaron con PostgreSQL real,
`venv/Scripts/python.exe` y `PYTHONIOENCODING=utf-8`.

| Suite | Resultado |
|---|---:|
| A2 funcional, snapshots, idempotencia, rollback y constraints | 15/15 |
| A2 concurrencia PostgreSQL | 7/7 |
| A1 funcional | 19/19 |
| A1 concurrencia PostgreSQL | 7/7 |
| BH-057 riesgo técnico y solicitudes | 92/92 |
| BH-056 skills y compatibilidad | 34/34 |
| Turnos, disponibilidad, reprogramación, diagnóstico, roles y `/me/` | 130/130 |

Las siete carreras A2 cubren:

1. dos consumos del mismo HOLD;
2. consumo contra expiración;
3. consumo contra release;
4. consumo contra un Turno conflictivo;
5. espera de lock que cruza el TTL;
6. invalidación de solicitud contra consumo;
7. dos HOLDs sobre recursos comunes sin deadlock.

Se verifica siempre el estado final de base, no sólo el resultado retornado.

## Checks técnicos

- `python manage.py check`: sin issues.
- `python manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- `python -m compileall gestion usuarios`: correcto.
- `git diff --check`: correcto; sólo avisos informativos de normalización
  CRLF/LF preexistentes.

## Frontera con BH-058 B

A2 no agregó ni modificó lógica de:

- `PaymentPolicy`;
- `PaymentIntent`;
- `Pago`;
- Mercado Pago;
- `ProviderPaymentAttempt` o `ProviderEvent`;
- stock, `MovimientoStock`, `OrdenCompra` u `OrdenPendiente`.

No se modificó frontend y no existe ruta, serializer ni view que exponga
`create_confirmed_turno_from_locked_hold`. El servicio interno no está conectado
a ningún flujo financiero o endpoint público. BH-058 B queda expresamente fuera
de este incremento.

BH-058 A2 = VALIDADO
