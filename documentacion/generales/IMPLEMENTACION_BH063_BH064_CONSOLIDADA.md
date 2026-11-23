# BH-063/BH-064 — Implementación consolidada, Incrementos 1–3

**Fecha:** 2026-11-23

**Baseline del Incremento 3:** `23e1e0d27578908ea6097cf1d900b461e2c52ef8`

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

## 11. Próximo incremento

El Incremento 4 deberá diseñar `PaymentIntent` asistido y políticas financieras
para tercero. No forma parte de este cambio. La confirmación, creación de Turno,
Pago y transición de estados continúan fuera de alcance.

`BH-063 INCREMENTO 3 = VALIDADO`
