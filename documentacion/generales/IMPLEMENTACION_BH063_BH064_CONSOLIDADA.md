# BH-063/BH-064 — Implementación consolidada, Incrementos 1–4

**Fecha:** 2026-11-23

**Baseline publicado al iniciar el Incremento 4:** `df9335c939d2bd525cb6e5913f5cd9a8efed7f25`

**Contratos:** [Decisiones D-01 a D-07](DECISIONES_Y_CONTRATOS_BH063_BH064.md)

## 1. Alcance consolidado

Este documento enlaza los incrementos implementados sin duplicar sus actas:

1. [BH-064, Incremento 1 — identidad presencial y alta rápida](IMPLEMENTACION_BH064_1_IDENTIDAD_PRESENCIAL.md).
2. [BH-063, Incremento 2 — solicitud, riesgo y consentimiento](IMPLEMENTACION_BH063_2_SOLICITUD_RIESGO_CONSENTIMIENTO.md).
3. **BH-063, Incremento 3 — hold asistido y disponibilidad**, documentado a
   continuación.

El Incremento 3 retiene temporalmente capacidad para una solicitud asistida
técnicamente aprobada. No crea `Turno`, `PaymentIntent` ni `Pago`; tampoco
publica acciones de pago o confirmación.

## 2. Incremento 3 — autoridad y scope

La autoridad exclusiva es un Usuario autenticado y activo con
`gestion.create_turno_for_client`. La lectura y los comandos vuelven a comprobar
el permiso efectivo y exigen que el actor sea el `operador_registrante` de una
solicitud `PRESENCIAL` o `TELEFONO`.

El operador conserva su identidad real en el ledger, el `SlotHold` y la
auditoría. El Cliente permanece como propietario de la capacidad. No existe
impersonación y este permiso no concede revisión técnica, diagnóstico, acceso a
snapshots sensibles ni autoridad financiera. Un recurso fuera de scope se
proyecta como 404.

## 3. Integración con BH-057 y `SlotHold`

Antes de ofrecer o retener capacidad se exige:

- solicitud en `APROBADA_TECNICAMENTE`;
- evaluación vigente, no superada, para el mismo Cliente y fecha;
- Cliente y Servicios activos;
- igualdad ordenada entre Servicios solicitados y evaluados;
- Personal activo, operativo y compatible con todos los Servicios.

La disponibilidad asistida usa `TurnoAvailabilityService` y la creación usa el
nuevo núcleo privado de `slot_hold_services.py`. Los wrappers públicos web
`create_slot_hold()` y `release_slot_hold()` siguen siendo owner-only. Por lo
tanto no se duplicaron jornada, grilla, skills, bloqueos, superposiciones,
Turnos, holds, equipamiento, TTL ni locks.

La consulta sólo proyecta candidatos. El `POST` vuelve a validar dentro de la
transacción con reloj PostgreSQL y locks canónicos; el frontend no decide la
disponibilidad definitiva.

## 4. API

Base: `/api/gestion/solicitudes-tecnicas-asistidas/{solicitud_id}/`.

| Método | Ruta | Resultado |
|---|---|---|
| `GET` | `disponibilidad/` | Profesionales y slots mínimos para la fecha evaluada |
| `GET` | `proximo-intervalo/` | Primer intervalo futuro; acepta `personal_id` opcional |
| `POST` | `hold/` | Crea (201) o recupera (200) el mismo hold |
| `GET` | `hold/` | Estado efectivo, expiración y countdown del último hold asistido |
| `POST` | `hold/liberar/` | Libera de forma explícita e idempotente |

La creación recibe `operation_id`, `personal_id`, `starts_at` e
`Idempotency-Key`. La liberación recibe `operation_id`, `public_id` e
`Idempotency-Key`. Los serializers rechazan campos extra.

Las respuestas de hold incluyen estado persistido y efectivo, expiración,
countdown informativo, Personal, acción siguiente segura y el aviso de que un
hold no equivale a un Turno confirmado. Los conflictos de capacidad,
idempotencia, evaluación, expiración o falta de intervalo usan 409 semántico.

## 5. Atención inmediata

`proximo-intervalo/` toma una sola lectura de `database_now()`, usa
`Configuracion.intervalo_turnos` y selecciona el menor `starts_at` que sea
estrictamente posterior al reloj DB. Evalúa la duración agregada multiservicio,
la fecha técnicamente evaluada y todas las reglas canónicas.

No hay tolerancia alternativa, backdating ni transición a `EN_PROCESO`. Si no
existe candidato se responde `NO_AVAILABILITY_FOUND` sin persistir reservas. Si
el candidato deja de ser válido, el `POST hold/` devuelve conflicto tras la
revalidación autoritativa.

## 6. Idempotencia, locks y causalidad

`SolicitudTecnicaAsistidaOperacion` admite `HOLD` y `RELEASE` y enlaza el
`SlotHold`. Conserva:

- `operation_id` único;
- digest SHA-256 de `Idempotency-Key`;
- fingerprint del actor y comando canónico;
- actor real, solicitud y resultado;
- ledger y auditoría dentro de la misma transacción.

Advisory locks ordenados serializan clave y `operation_id`; los locks de
solicitud, Personal, Cliente, tipos de equipamiento y capacidad permanecen en el
motor canónico. Un retry idéntico recupera la misma fila y payload diferente
produce 409. Las carreras PostgreSQL verifican un único ganador tanto para el
mismo Personal como para la última unidad de equipamiento.

La liberación asistida usa `OPERATOR_CANCELLED`. Nunca escribe
`CLIENT_CANCELLED`, causal reservada al wrapper owner-only web. Un hold vencido
se materializa como `TTL_EXPIRED` y no se presenta como activo.

## 7. React

`frontend/src/pages/admin/NuevoTurno.js` usa `SessionContext` y Axios global.
Sólo monta las acciones con el permiso efectivo y permite:

- consultar profesionales e intervalos;
- seleccionar slot o solicitar atención inmediata;
- crear, consultar y liberar el hold;
- mostrar expiración y countdown;
- actualizar el estado efectivo;
- conservar payload, `operation_id` e `Idempotency-Key` ante timeout incierto;
- impedir doble submit y manejar 400/401/403/404/409.

La revocación del permiso desmonta la superficie. No se ofrecen botones de pago
o confirmación y se muestra explícitamente que el hold no es un Turno.

## 8. Migración

`gestion/migrations/0046_assisted_slot_hold_increment3.py`:

1. agrega el FK nullable y `PROTECT` de operación asistida a `SlotHold`;
2. amplía comandos con `HOLD` y `RELEASE`;
3. amplía la causal de liberación con `OPERATOR_CANCELLED`;
4. reemplaza el check de resultado para exigir hold sólo en esos comandos.

`makemigrations --check --dry-run` no detectó cambios y `sqlmigrate 0046`
confirmó SQL aditivo, índice y constraint esperado.

## 9. Regresión selectiva

| Ejecución | Resultado | Justificación |
|---|---:|---|
| Hold asistido focal, incluidas 3 carreras PostgreSQL | 16/16 | Contrato nuevo, idempotencia, recursos, ownership y causalidad |
| Backend relacionado | 108/108 | Incremento 2/BH-057, web holds, disponibilidad, skills, equipamiento y concurrencia |
| React `NuevoTurno.test.js` | 23/23 | selección, inmediato, activo/vencido, timeout, doble submit, errores y revocación |
| `manage.py check` | OK | Validación Django |
| `makemigrations --check --dry-run` | OK | Estado de modelos/migraciones |
| Build React estándar | OK con warnings históricos | El archivo modificado no agregó warnings |

No se ejecutaron B1–B7 ni el frontend completo: la política solicitada exige
regresión por impacto y no hubo hallazgo transversal. El build con `CI=true`
permanece bloqueado por warnings ESLint preexistentes en archivos ajenos; el
build estándar finalizó correctamente. Los logs extensos quedaron en archivos
temporales locales.

## 10. Compatibilidad y riesgos pendientes

- El canal web conserva ownership y causal `CLIENT_CANCELLED`; sus pruebas están
  incluidas en la regresión selectiva.
- El countdown del navegador es informativo; cada consulta y mutación usa reloj
  DB y estado efectivo.
- Un slot leído puede perderse antes del comando; el 409 recuperable es parte
  del contrato y requiere refrescar disponibilidad.
- Los warnings históricos impiden tratar warnings como errores en el build
  global, sin afectar la compilación estándar.
- Las migraciones 0041–0045 siguen pendientes sólo en la base local de
  desarrollo; las bases PostgreSQL de prueba aplicaron la cadena completa.

## 11. Handoff del Incremento 3

Al cerrar el Incremento 3, el Incremento 4 debía diseñar `PaymentIntent` asistido
y políticas financieras para tercero. La confirmación, creación de Turno, Pago
y transición de estados todavía estaban fuera de aquel alcance.

`BH-063 INCREMENTO 3 = VALIDADO`

## 12. Incremento 4 — Confirmación financiera asistida y estados

### 12.1 Contratos y autoridad efectiva

La preparación financiera para tercero exige la intersección estricta de
`gestion.create_turno_for_client` y `gestion.register_payment`. La primera
capacidad aporta el scope de solicitud asistida y la segunda la autoridad para
crear una obligación financiera. Esta composición no modifica
`bh061-role-capabilities-v1`, no agrega grants y no autoriza conciliación:

- registrar efectivo o evidencia conserva `gestion.register_payment`;
- aceptar o rechazar evidencia conserva `gestion.confirm_deposit`;
- provider conserva el actor de sistema o permiso publicado;
- confirmar el Turno no es un comando libre: sigue siendo consecuencia interna
  de B2/B3 al alcanzar el umbral con Pagos `RECONCILED` en moneda válida.

El operador nunca se autentica como el Cliente. Los wrappers web de
`payment_intent_services.py` permanecen owner-only; los núcleos privados exigen
un `scope_checker` explícito. El scope asistido requiere solicitud
`PRESENCIAL`/`TELEFONO`, operador originador, ledger `HOLD`, Cliente y hold
coincidentes, y revalida ambos permisos desde base de datos dentro de la
transacción.

### 12.2 Intent, Pago, hold y Turno

API añadida bajo
`/api/gestion/solicitudes-tecnicas-asistidas/{solicitud_id}/`:

| Método | Ruta | Contrato |
|---|---|---|
| `GET` | `pago/opciones/` | Cotiza desde la `PaymentPolicy` publicada, precios bajo lock y expiración del hold |
| `POST` | `pago/intent/` | Prepara o recupera el Intent con `operation_id` e `Idempotency-Key` |
| `GET` | `pago/intent/` | Recupera la proyección financiera y el Turno sólo si ya existe |

El frontend sólo envía hold y modalidad. Total, umbral, moneda, versión de
policy, snapshots, estado de Pago y estado de Turno son autoritativos del
backend. Preparar el Intent no crea `Pago` ni `Turno`.

Efectivo, transferencia, tarjeta externa, provider y conciliación continúan en
los servicios BH-058 existentes. Efectivo real se registra `RECONCILED`; una
transferencia queda `PENDING_RECONCILIATION`. Sólo la suma suficiente de Pagos
`RECONCILED` permite que B3 apruebe el Intent y consuma el hold. Pago tardío no
recrea hold ni Turno y conserva los casos de reconciliación existentes.

`create_confirmed_turno_from_locked_hold()` sigue siendo interno y se invoca
únicamente después de la autorización financiera. Mantiene locks, revalidación
de solicitud/evaluación/Personal/capacidad/equipamiento, consumo único,
multiservicio ordenado e idempotencia. Para una solicitud asistida, el histórico
`canal_origen` es `PRESENCIAL`; `medio_solicitud` y operador originador se
conservan causalmente en solicitud, ledger y auditoría. El canal owner-only
permanece `WEB`.

### 12.3 Idempotencia, recuperación y auditoría

`SolicitudTecnicaAsistidaOperacion` incorpora el comando `INTENT` y un FK
nullable `PROTECT` a `PaymentIntent`. El check de coherencia exige hold e Intent
sólo para ese comando. El modelo valida además que solicitud, hold e Intent
pertenezcan al mismo agregado.

Advisory locks ordenados serializan `operation_id` y digest de
`Idempotency-Key`; el Intent usa una clave interna derivada que nunca expone la
clave original. Un retry idéntico recupera el mismo resultado, mientras que una
clave o identidad reutilizada con payload incompatible responde 409. Ledger,
Intent, líneas y auditoría se confirman o revierten juntos. La revocación de
permiso se vuelve a comprobar después de adquirir los locks financieros.

La auditoría registra IDs causales, actor, policy, modalidad, importes y
expiración, sin comprobantes ni snapshots técnicos sensibles.

### 12.4 Estados y finalización profesional

La creación financiera terminal conserva `Turno.CONFIRMADO`; no existe payload
de estado ni creación directa `EN_PROCESO`. El endpoint técnico histórico
`registrar-llegada` conserva compatibilidad, pero React lo presenta como
**Iniciar atención**, coherente con `CONFIRMADO → EN_PROCESO`.

El único servicio `finalize_turno()` admite ahora:

- `CONFIRMADO → REALIZADO`;
- `EN_PROCESO → REALIZADO`.

No cambian cuenta/Personal activos, `gestion.finalize_service`, ownership del
profesional asignado, `atomic`, `select_for_update`, fichas obligatorias,
fingerprint, ledger de efectos, auditoría ni rollback. `FinalizacionTurno`
persiste en `estado_anterior` el origen real. Otros estados responden 409 y las
reglas financieras, de cancelación y reprogramación no se alteran.

### 12.5 React mínimo

`NuevoTurno.js` muestra por separado aprobación técnica, hold, condiciones de
policy, Intent, monto conciliado, saldo para confirmar, expiración y estado de
recuperación. La superficie financiera sólo se monta con ambos permisos
efectivos; al revocar `register_payment` se oculta incluso una proyección ya
cargada. Los timeout conservan payload e identidad para retry y el Turno sólo se
muestra cuando `confirmed_turno_id` existe.

“Continuar en Caja” reutiliza `CajaPresencial` con búsqueda por la referencia
del Intent; no agrega un mecanismo de cobro. El recorrido profesional conserva
la finalización cuando el contexto está `EN_PROCESO` y el preflight autoritativo
está listo.

### 12.6 Migración, pruebas y riesgos

`gestion/migrations/0047_assisted_payment_intent_increment4.py` agrega el FK,
amplía el enum de comando y reemplaza el check de coherencia. No migra datos ni
modifica permisos.

Focales implementadas cubren policy/snapshots, composición de autoridad,
scope, revocación bajo lock, ausencia de Pagos ficticios, efectivo parcial y
suficiente, transferencia pendiente/conciliada, sobrepago y duplicados por las
suites BH-058, hold vencido, multiservicio, canal, recuperación, rollback,
confirmación única, carrera PostgreSQL y finalización desde ambos orígenes.
React cubre doble submit, timeout, 401/403/409, Caja, confirmación real,
revocación y ocultamiento de datos.

Riesgos residuales: el countdown del navegador sigue siendo informativo; un
hold puede vencer o perder capacidad entre lecturas; una acreditación tardía
puede abrir un caso financiero sin booking. Esos casos requieren recuperación
BH-058 y nunca justifican resucitar capacidad. El wizard completo, mejoras de
operación masiva y cualquier excepción D-08 permanecen fuera del Incremento 4.

La regresión final única sobre PostgreSQL y React produjo:

| Ejecución | Pruebas únicas | Resultado |
|---|---:|---:|
| Backend B1 | 443 | OK |
| Backend B2 | 233 | OK |
| Backend B3 | 224 | OK |
| Backend B4 | 79 | OK |
| Backend B5 | 177 | OK |
| Backend B6 | 43 | OK |
| Backend B7, concurrencia PostgreSQL | 78 | OK |
| Frontend Jest completo | 480 | OK |
| Build React estándar | — | OK con warnings legacy fuera del alcance |
| Django checks / drift de migraciones / SQL 0047 / `git diff --check` | — | OK |

Antes de la regresión se ejecutaron focales repetidas para desarrollar y
corregir el incremento: backend financiero/finalización (37) y React financiero
/profesional (56), además de las suites visibles de agenda/Caja. No se suman a
los totales únicos anteriores. Los logs completos se conservaron únicamente en
el directorio temporal local.

`BH-063 INCREMENTO 4 = VALIDADO`
