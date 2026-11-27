# BH-058 A1 — SlotHold, disponibilidad y expiración

## Resultado

Se implementó una reserva temporal persistida de agenda separada de `Turno` y
de cualquier concepto financiero. La vigencia autoritativa es:

```text
state = ACTIVE AND expires_at > database_now
```

Por lo tanto, `now == expires_at` ya está vencido y un scheduler detenido no
mantiene recursos bloqueados.

La implementación sigue `ANALISIS_BH058_A_HOLD_EXPIRACION.md` y
`ANALISIS_BH058_ARQUITECTURA_FINAL.md`.

## Implementación realizada

### Persistencia y configuración

- `SlotHold` con UUID público, solicitud, evaluación, Cliente, Personal,
  intervalo, expiración, estado, timestamps terminales, razón de liberación,
  actor, clave de idempotencia y vínculo futuro nullable/único a `Turno`.
- `SlotHoldService` conserva nombre, orden y duración de cada Servicio.
- `SlotHoldEquipmentRequirement` conserva el tipo y cantidad de equipamiento.
- Constraints de intervalo, expiración, coherencia estado/timestamps, un HOLD
  `ACTIVE` por solicitud, un futuro `CONSUMED` por solicitud y claves únicas.
- Índices por estado/expiración, Personal/intervalo, Cliente/intervalo y tipo de
  equipamiento.
- `Configuracion.slot_hold_ttl_minutes`, default 15 y rango de base/modelo
  1–120. Un cambio sólo afecta HOLDs futuros.
- Migración: `gestion/migrations/0027_slothold_slotholdequipmentrequirement_and_more.py`.

### Reloj, ciclo de vida y auditoría

- `database_now()` usa `STATEMENT_TIMESTAMP()` en PostgreSQL para obtener un
  reloj nuevo aun dentro de una transacción larga.
- Se implementaron `create_slot_hold`, `release_slot_hold` y
  `expire_slot_hold` con transacciones, locks, revalidación e idempotencia.
- Crear deriva duración y equipamiento desde los Servicios; el cliente no
  aporta duración, fin, TTL, estado ni capacidad.
- La expiración se limita al inicio del slot y un HOLD sin ventana positiva se
  rechaza.
- Release y expire repetidos no duplican transiciones ni auditorías.
- Eventos semánticos: `SLOT_HOLD_CREATED`, `SLOT_HOLD_RELEASED` y
  `SLOT_HOLD_EXPIRED`. La auditoría guarda SHA-256 de la clave, nunca su valor.

### Disponibilidad y concurrencia

- `TurnoAvailabilityService` continúa siendo la única fuente canónica.
- Turnos y HOLDs vigentes se combinan para Personal, Cliente y capacidad de
  equipamiento con intervalos semiabiertos (`inicio < otro_fin` y
  `fin > otro_inicio`).
- Disponibilidad pública, disponibilidad canónica, creación de Turno y
  reprogramación consultan la misma semántica.
- Los writers canónicos bloquean Cliente, Servicios, Personal y
  `TipoEquipamiento`; `TipoEquipamiento` serializa la última unidad disponible.
- Crear/reprogramar Turno vuelve a validar contra HOLDs después de los locks.
- Una solicitud técnica sin HOLD no ocupa agenda.

### API y ownership

| Operación | Ruta | Contrato |
|---|---|---|
| Crear | `POST /api/gestion/solicitudes-tecnicas/{id}/hold/` | Requiere `Idempotency-Key`, `personal_id` y `starts_at`; sólo dueño y solicitud aprobada/evaluación vigente. |
| Estado | `GET /api/gestion/slot-holds/{public_id}/` | Sólo dueño; informa estado persistido, efectivo y countdown; nunca muta. |
| Liberar | `POST /api/gestion/slot-holds/{public_id}/release/` | Sólo dueño, body vacío e idempotencia semántica. |

Un usuario staff no obtiene acceso transversal a HOLDs ajenos. Las respuestas
no exponen la solicitud, Cliente, evaluación ni clave de idempotencia.

### Expirador operativo

`python manage.py expirar_slot_holds --batch-size 100` materializa vencimientos
en lotes cortos con `SELECT ... FOR UPDATE SKIP LOCKED`, savepoint por fila,
continuación ante fallo, contadores e idempotencia. El command mejora auditoría
y observabilidad, pero no participa en la decisión de disponibilidad.

### Frontend mínimo A1

- La solicitud permite elegir un profesional preferido.
- Una solicitud aprobada puede crear el HOLD para su fecha/hora evaluada.
- Se muestra un countdown local marcado expresamente como informativo.
- Se puede liberar el HOLD.
- La pantalla nunca presenta el HOLD como “Turno confirmado”.

## Frontera respetada

- No se crea ningún `Turno` desde un HOLD.
- No se implementa la transición a `CONSUMED`; el estado y vínculo existen sólo
  como contrato de persistencia para A2.
- No se añadieron `PaymentPolicy`, `PaymentIntent`, intentos/eventos de provider,
  pagos, Mercado Pago, stock, recetas ni efectos sobre `OrdenCompra`.
- `limpiar_turnos` no importa, consulta ni modifica `SlotHold`.
- No se amplió ningún writer legacy de Turnos.

## Evidencia de pruebas

Todas las pruebas backend se ejecutaron con
`C:/Users/AldoA/Desktop/Bohemia-hair/venv/Scripts/python.exe`, PostgreSQL real,
`PYTHONIOENCODING=utf-8` y la base de test reconstruida antes de las regresiones
de permisos.

| Suite | Resultado |
|---|---:|
| A1 modelo, lifecycle, API, disponibilidad, command y job caído | 19/19 |
| A1 concurrencia PostgreSQL (`TransactionTestCase`, conexiones y barreras reales) | 7/7 |
| BH-057 riesgo técnico y solicitudes | 92/92 |
| BH-056 skills y compatibilidad | 34/34 |
| Turnos, reprogramación, llegada, autorización, diagnóstico, roles y `/me/` | 130/130 |
| Frontend `SolicitudesTecnicas.test.js` | 3/3 |

Las siete carreras PostgreSQL cubren:

1. dos HOLDs para el mismo Personal/slot;
2. mismo Cliente con distintos profesionales;
3. dos profesionales para la última unidad de equipamiento;
4. creación de Turno contra creación de HOLD;
5. reprogramación de Turno contra creación de HOLD;
6. creación contra liberación;
7. dos commands expiradores sobre el mismo HOLD.

En los escenarios de capacidad hubo exactamente un ganador y no se observaron
deadlocks ni auditorías duplicadas.

## Checks técnicos

- `python manage.py check`: sin issues.
- `python manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- `python -m compileall -q gestion`: correcto.
- `git diff --check`: correcto; sólo avisos de normalización CRLF/LF ya
  existentes.
- Build frontend normal: compilado correctamente. Conserva warnings ESLint
  preexistentes en pantallas ajenas a A1; con `CI=true` esos warnings globales
  se tratan como error, sin errores reportados en `SolicitudesTecnicas.js`.

BH-058 A1 = VALIDADO
