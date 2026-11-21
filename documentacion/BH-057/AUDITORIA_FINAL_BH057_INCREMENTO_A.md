# Auditoría final — BH-057 Incremento A

Fecha: 2026-10-24

## Alcance y método

Reauditoría de B1, B2 y B3 sin modificar código ni avanzar a Incremento B. Se
revisaron implementación, migraciones, servicios, modelos, pruebas y
documentación. Los escapes ORM de inmutabilidad se comprobaron contra la base de
tests dentro de una transacción revertida; no se conservaron datos de auditoría.

## B1 — Servicios sin perfil técnico

**Resultado: B1 = CERRADO**

- La migración `0023_backfill_pending_technical_profiles` localiza Servicios sin
  perfil y usa `get_or_create` para crear exclusivamente perfiles `PENDIENTE`,
  `NO_DEFINIDO`, activos y sin familia.
- La migración y `backfill_missing_technical_profiles()` son conservadores e
  idempotentes. No reescriben perfiles existentes ni infieren familia o riesgo
  desde nombre, descripción o categoría.
- `technical_service_profile_inventory()` distingue perfil faltante, pendiente,
  clasificado válido, perfil inactivo, familia inactiva y perfil inválido.
- `report_unclassified_services` expone el inventario, el resumen y el backfill
  explícito mediante `--backfill`.
- `_profile_is_classified()` sólo acepta un perfil activo, `CLASIFICADO`, con
  riesgo distinto de `NO_DEFINIDO` y familia activa cuando exista. Todo perfil
  ausente, pendiente, inactivo o inválido dispara
  `SERVICE_TECHNICAL_PROFILE_MISSING` y `REQUIERE_REVISION`; no concede `APTO`.

## B2 — Turno realizado sin DetalleTurno

**Resultado: B2 = CERRADO**

- El evaluador detecta Turnos `REALIZADO` sin detalles cuya fecha sea menor o
  igual a `fecha_solicitada`.
- Usa el code estable `REALIZED_TURNO_WITHOUT_DETAILS` como
  `HISTORY_INCONSISTENCY`, lo agrega a `missing_data` y conserva en el snapshot
  `turno_id`, fecha, hora, estado y `detalle_count=0`.
- El resultado mínimo es `REQUIERE_REVISION`; no inventa el Servicio realizado
  ni lo convierte en `NO_APTO` clínico.
- Los Turnos futuros se ignoran. Un Cliente sin Turnos no genera inconsistencia,
  y un Turno realizado con detalles sigue el flujo normal.

## B3 — Inmutabilidad histórica

**Resultado: B3 = ABIERTO**

La protección parcial funciona para:

- `save()` normal sobre una instancia persistida;
- `delete()` de instancia;
- `objects.update()` y `objects.delete()`;
- `objects.bulk_update()`, que termina invocando el `update()` bloqueado;
- creación inicial.

No obstante, una evaluación persistida todavía puede modificarse sin pasar por
`save()` ni por `ImmutableTechnicalRiskEvaluationQuerySet`:

1. `EvaluacionRiesgoTecnico.objects.bulk_create(...,
   update_conflicts=True, ...)` está heredado sin restricción. En la prueba de
   auditoría actualizó el `outcome` de una fila existente de `APTO` a `NO_APTO`.
2. `EvaluacionRiesgoTecnico._base_manager` es un `QuerySet` estándar, no el
   QuerySet inmutable. En la prueba de auditoría,
   `_base_manager.filter(...).update(severity=77)` modificó una evaluación
   persistida.

El segundo escape permite escribir por SQL ORM cualquiera de los campos
históricos, incluido `evaluated_at`, snapshots, Cliente, política, fecha,
severity y outcome, sujeto únicamente a constraints de base de datos. Por ello
la evidencia no es históricamente inmutable en todas las APIs ORM expuestas.

No existe ViewSet/API de evaluaciones, por lo que no se detectó una vía HTTP de
PUT, PATCH o DELETE.

## Supersesión

El servicio `supersede_technical_risk_evaluation()`:

- rechaza autosupersesión y Clientes distintos;
- exige que E2 sea posterior a E1;
- preserva outcome, política, fecha y snapshots de E1;
- es idempotente para el mismo par;
- audita `TECHNICAL_ASSESSMENT_SUPERSEDED`;
- impide ciclos cuando se usa el servicio, por el orden temporal estricto.

No hay consumidor productivo, lo cual es aceptable en Incremento A. Sin embargo,
la exclusividad de esta vía tampoco está cerrada: el atributo interno
`_allow_explicit_supersession` puede establecerse desde código llamador y los
escapes ORM anteriores también pueden escribir `superseded_by` sin ejecutar las
reglas ni la auditoría del servicio.

## Versionado histórico

El escenario v1/E1 y v2/E2 está implementado y cubierto. En el camino soportado,
E1 conserva referencia a v1, parámetros y snapshot originales, rule codes y
outcome; evaluar o persistir v2 no reinterpreta E1. Esta garantía queda
globalmente condicionada por el blocker de inmutabilidad descrito en B3.

## Pureza y persistencia separada

`evaluate_booking_risk()` sólo consulta y construye el resultado. La prueba de
pureza confirma que no crea ni modifica Turnos, Detalles, Cliente, Rutina,
AgendaCuidados, pagos, notificaciones, evaluaciones ni auditorías. Tampoco hay
escrituras de diagnóstico. La persistencia continúa separada en
`persist_technical_risk_evaluation()`.

## Fail-closed

- Servicio sin perfil y perfiles pendientes, inactivos o inválidos:
  `REQUIERE_REVISION`.
- Turno realizado sin detalles: `REQUIERE_REVISION` con inconsistencia explícita.
- Política ausente o versión desconocida: `TechnicalRiskConfigurationError`.
- Regla activa corrupta o con referencias desactivadas:
  `TechnicalRiskConfigurationError`.
- `NO_APTO` queda reservado para una regla técnica explícita; no se usa para
  ocultar datos faltantes o configuración corrupta.

No se encontró un camino evaluado que convierta esos casos en `APTO` silencioso.

## Frontera de alcance

No se encontró implementación de `SolicitudTecnicaReserva`, cola de revisión,
frontend cliente/revisor, HOLD, `PaymentIntent` o Mercado Pago. No hay cambios en
`turno_creation_services.py` ni `turno_management_services.py`, no se conectó
`TurnoCreationService` con el evaluador nuevo y no se añadieron cambios
productivos a `ACTIVE_TURNO_STATES`.

## Pruebas y checks ejecutados

- BH-057 A: **49/49 OK**.
- Regresiones BH-056, diagnóstico, creación/disponibilidad/reprogramación de
  Turnos, roles y `/me/`: **126/126 OK**.
- `python manage.py check`: OK.
- `python manage.py makemigrations --check`: OK, sin cambios detectados.
- `python -m compileall gestion usuarios`: OK.
- `git diff --check`: exit code 0; sólo avisos preexistentes de normalización
  CRLF/LF, sin errores de whitespace.

Los 49 tests cubren B1, B2, los caminos ordinarios de B3, supersesión, versionado,
snapshots, pureza y fail-closed. No cubren `bulk_create(update_conflicts=True)`,
`_base_manager.update()`, escritura directa de `superseded_by` ni mutación de
`evaluated_at` por esos escapes.

## Documentación

`IMPLEMENTACION_BH057_INCREMENTO_A.md` y
`CORRECCION_BH057_A_BLOCKERS.md` coinciden con B1, B2, versionado, pureza,
fail-closed y fronteras. No coinciden con B3: afirman inmutabilidad fuera de HTTP
y una única transición soportada de supersesión, garantías que las APIs ORM
expuestas todavía permiten evadir.

## Blocker real restante

- **B3 — Inmutabilidad histórica incompleta:** `bulk_create` con actualización
  de conflictos y el `_base_manager` estándar permiten modificar evaluaciones
  persistidas y evadir tanto las validaciones como la auditoría semántica.

BH-057 A = NO VALIDABLE
