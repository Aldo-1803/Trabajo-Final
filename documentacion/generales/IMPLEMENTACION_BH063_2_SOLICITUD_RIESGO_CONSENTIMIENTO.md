# BH-063 — Incremento 2: solicitud asistida, riesgo y consentimiento

**Fecha:** 2026-11-21
**Baseline de inicio:** `c62421f39884fa3d25e28efaacde298215875634`
**Contrato antecedente:** [BH-063/BH-064 — decisiones y contratos](DECISIONES_Y_CONTRATOS_BH063_BH064.md)
**Alcance:** solicitud técnica asistida previa a capacidad, pago y Turno.

## 1. Resultado

El incremento incorpora un adaptador asistido sobre el agregado y evaluador
BH-057. Un operador activo con `gestion.create_turno_for_client` puede registrar
una intención para un Cliente activo, uno o más Servicios ordenados y medio
`TELEFONO` o `PRESENCIAL`.

La operación:

- persiste `SolicitudTecnicaReserva` y todos sus Servicios;
- ejecuta `evaluate_booking_risk()` y
  `persist_technical_risk_evaluation()` sin duplicar reglas técnicas;
- conserva política, snapshots, diagnóstico realmente disponible, procedencia,
  completitud, antigüedad, historial y agregación multiservicio de BH-057;
- proyecta sólo outcome, mensajes permitidos y acción siguiente;
- registra, cuando corresponde, consentimiento asistido inmutable separado de
  la aceptación web;
- no crea `SlotHold`, `PaymentIntent`, `Pago`, `Turno` ni diagnóstico.

Una habilitación técnica se describe como **“Pendiente de selección de horario
y confirmación”**. No se presenta como Turno o reserva.

## 2. Autoridad y scope

La única autoridad del canal es:

```text
usuario autenticado y activo
AND gestion.create_turno_for_client
```

No se consulta rol nominal, `is_staff` ni `is_superuser`. El servicio vuelve a
leer y bloquear al actor antes de mutar. No existe impersonación: el Cliente es
el sujeto evaluado y `operador_registrante` conserva la identidad real del
operador.

El permiso no concede `diagnosis.create`, `technical_booking.review`, lectura o
gestión técnica global ni autoridad financiera. La lectura por ID del canal
asistido exige que el actor siga autorizado y sea el operador que registró la
solicitud; fuera de ese scope responde 404.

## 3. Persistencia

### 3.1 `SolicitudTecnicaReserva`

Se agregaron campos aditivos y compatibles:

- `medio_solicitud`: `WEB`, `TELEFONO`, `PRESENCIAL` o nulo histórico;
- `operador_registrante`: Usuario real o nulo histórico.

Las nuevas solicitudes owner-only existentes se marcan `WEB`. No se modifica ni
se infiere `Turno.canal_origen`; tampoco se backfillean filas antiguas.

### 3.2 `SolicitudTecnicaAsistidaOperacion`

Ledger inmutable con:

- `operation_id` UUID único;
- actor y comando `CREATE` o `CONSENT`;
- digest SHA-256 de `Idempotency-Key`, nunca la clave en claro;
- fingerprint SHA-256 del comando canónico;
- solicitud y, para `CONSENT`, evidencia resultante;
- fecha autoritativa.

La restricción `(command, idempotency_key_digest)` es global para detectar el
uso de una identidad por otro actor. `operation_id` también es globalmente
único. El fingerprint de creación contiene IDs, orden de Servicios, preferencia
temporal, Personal y medio; no incluye snapshots, diagnóstico ni datos de salud.

### 3.3 `ConsentimientoAdvertenciaAsistido`

Evidencia inmutable y paralela a `AceptacionAdvertenciaTecnica`:

- solicitud y evaluación vigente;
- Cliente informado y operador registrante;
- medio asistido;
- outcome `ADVERTENCIA` y versión de política;
- códigos y textos permitidos tomados del snapshot, no del frontend;
- decisión `ACEPTA`, `RECHAZA` o `NO_OBTENIDO`;
- motivo obligatorio para rechazo o no obtención;
- timestamp autoritativo e identidad de ledger.

No es una firma digital ni evidencia de grabación. Sólo `ACEPTA` sobre la
evaluación vigente mueve la solicitud a `APROBADA_TECNICAMENTE`. Las otras dos
decisiones permanecen bloqueantes. Una decisión posterior incompatible produce
409 y un retry idéntico recupera la misma fila.

La aceptación web owner-only permanece sin cambios y no se crea durante el flujo
asistido.

## 4. Servicio de dominio

`gestion/assisted_technical_booking_services.py` implementa:

- `create_assisted_technical_request()`;
- `register_assisted_warning_consent()`;
- `assisted_request_for_actor()`;
- `next_assisted_action()`.

La creación valida actor, Cliente activo, Servicios activos y únicos,
compatibilidad AND del Personal preferido y medio asistido. Luego delega en
`create_technical_booking_request()`; por ello no existe un evaluador alterno.

Las transacciones usan `transaction.atomic`, advisory locks PostgreSQL por clave
y `operation_id`, locks de actor/Cliente y lock explícito de la fila de
`SolicitudTecnicaReserva` en la transición de consentimiento. La auditoría y el
ledger forman parte de la misma transacción: si fallan, se revierte toda la
operación.

Un retry de creación consulta el ledger antes del evaluador. Una política nueva
publicada entre intentos no reinterpreta el resultado ya persistido.

## 5. Outcomes y acción siguiente

| Outcome BH-057 | Estado inicial | Acción pública |
|---|---|---|
| `APTO` | `APROBADA_TECNICAMENTE` | `PENDING_SLOT_SELECTION_AND_CONFIRMATION` |
| `ADVERTENCIA` | `ADVERTENCIA_PENDIENTE` | `REGISTER_ASSISTED_CONSENT`; sólo `ACEPTA` habilita el paso futuro |
| `REQUIERE_REVISION` | `EN_REVISION` | `WAIT_FOR_TECHNICAL_REVIEW`; el operador no recibe acción de aprobación |
| `NO_APTO` | `RECHAZADA_TECNICAMENTE` | `TECHNICALLY_BLOCKED` |

La falta de perfil o clasificación técnica se mantiene fail-closed según
BH-057; no se convierte automáticamente en `APTO` ni crea diagnóstico.

## 6. API

Base: `/api/gestion/solicitudes-tecnicas-asistidas/`.

| Método | Ruta | Contrato |
|---|---|---|
| `POST` | `/` | crea (201) o recupera retry (200) |
| `GET` | `/{id}/` | lectura segura dentro del scope |
| `POST` | `/{id}/consentimiento/` | registra o recupera consentimiento (200) |
| `GET` | `/{id}/accion-siguiente/` | outcome, estado y acción pública |

Creación acepta `operation_id`, `cliente_id`, `servicio_ids`,
`fecha_preferida`, `hora_preferida`, `personal_preferido_id` opcional y
`medio_solicitud`. Consentimiento acepta `operation_id`, `decision` y `motivo`.
Ambos comandos exigen `Idempotency-Key`.

Los serializers rechazan campos extra. Estado, outcome, política, diagnóstico,
autor técnico, precio y duración no son autoridad del frontend.

Errores semánticos:

- 400: payload, medio, Cliente/Servicio/Personal o clave inválidos;
- 401: sesión ausente o inválida;
- 403: falta de permiso o actor inactivo;
- 404: Cliente/solicitud fuera de scope;
- 409: clave u operación reutilizada, decisión incompatible o evaluación
  obsoleta.

Las respuestas de error usan `error.code` y `error.detail`. La proyección nunca
incluye `input_snapshot`, `result_snapshot`, diagnóstico, historial, notas,
fórmulas, mensajes profesionales ni datos de terceros.

## 7. React

`frontend/src/pages/admin/NuevoTurno.js` dejó de crear el `Turno` legacy. La ruta
protegida existente continúa exigiendo `gestion.create_turno_for_client` y la
pantalla además evita montar o consultar recursos sin ese permiso efectivo.

La superficie usa Axios global y `SessionContext` para:

- buscar Clientes mediante el selector minimizado BH-064;
- recibir por router state el `cliente_id` recién creado;
- elegir múltiples Servicios y medio;
- registrar/evaluar la intención;
- representar los cuatro outcomes;
- registrar las tres decisiones de consentimiento;
- clasificar 400/401/403/404/409 y fallas de red;
- impedir doble submit y conservar payload, `operation_id` e
  `Idempotency-Key` ante timeout.

No contiene selector final de slots, pago, confirmación ni creación de Turno.

## 8. Migración

`gestion/migrations/0045_assisted_technical_request_increment2.py`:

1. agrega los dos campos nulables a `SolicitudTecnicaReserva`;
2. crea `ConsentimientoAdvertenciaAsistido`;
3. crea `SolicitudTecnicaAsistidaOperacion`, índices, unicidades y check de
   resultado por comando.

`sqlmigrate` confirmó SQL aditivo, FKs `PROTECT`, columnas históricas nulables,
índices y restricciones. No existe migración de datos ni reinterpretación del
canal histórico.

## 9. Pruebas

La suite nueva cubre autorización, usuario/Cliente inactivo, fail-closed sin
perfil, uno y varios Servicios, repetidos/inactivos, Personal incompatible,
cuatro outcomes, tres decisiones, motivo, obsolescencia, retries, cambio de
política, scope, proyección, auditoría, rollbacks, compatibilidad web y ausencia
de Hold/Pago/Turno/diagnóstico. Dos pruebas `TransactionTestCase` ejecutan
carreras reales sobre PostgreSQL para el mismo actor y dos operadores.

Resultados de validación se completan al cierre:

| Ejecución | Resultado |
|---|---:|
| Focal asistida + BH-057 | 56/56 |
| Frontend focal | 18/18 |
| Frontend completo | 463/463 |
| B1 | 443/443 |
| B2 | 232/232 |
| B3 | 210/210 |
| B4 | 79/79 |
| B5 | 170/170 |
| B6 | 43/43 |
| B7 PostgreSQL | 74/74 |
| Build React | OK; sólo warnings históricos ajenos |
| `check` / `makemigrations --check` | OK / OK |

La matriz B1–B7 enumera **1.251/1.251 pruebas backend únicas**. Los focales de
18 pruebas asistidas, el combinado de 56 pruebas asistidas/BH-057 y las 18 de
frontend focal se ejecutaron como repeticiones y no se suman a ese total. La
primera ejecución local paralela agotó el timeout del harness para B1, B5 y B7;
se repitieron secuencialmente. Un primer retry B7 reutilizó la base interrumpida
y encontró una secuencia temporal desalineada en el setup; la corrida aceptada
se realizó completa sobre una base PostgreSQL nueva (`74/74`).

## 10. Límites y trabajo posterior

- Incremento 3: selección y `SlotHold` asistido con recursos reales.
- Incremento 4: `PaymentIntent` para tercero y cumplimiento de `PaymentPolicy`.
- Incremento 5: confirmación terminal, recuperación integral y endurecimiento
  final de React.
- La reevaluación asistida explícita no se publica en este incremento; las
  evaluaciones ya persistidas conservan la política y supersesión BH-057 y un
  consentimiento nunca acepta una evaluación marcada como superada.
- No se implementa atención inmediata, excepción al prepago, cambios de
  diagnóstico/perfil ni BH-061 v2.

## 11. Estado

Backend, concurrencia PostgreSQL, frontend, build, checks, migración, SQL y
proyección segura fueron validados. No se inicia el Incremento 3 desde este
documento.

`BH-063 INCREMENTO 2 = VALIDADO`
