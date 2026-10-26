# Corrección de blockers — BH-057 Incremento A

Fecha: 2026-10-24

## Alcance

Se corrigieron exclusivamente los tres blockers registrados en
`AUDITORIA_BH057_INCREMENTO_A.md`. No se implementó Incremento B ni se conectó el
evaluador al flujo productivo de Turnos.

## B1 — Inventario y backfill conservador

### Servicio reusable

`gestion/technical_risk_profile_services.py` incorpora:

- `technical_service_profile_inventory()`;
- `backfill_missing_technical_profiles()`.

El inventario produce una fila por Servicio con ID, nombre, actividad, perfil,
estado de clasificación, riesgo y code de familia. Clasifica explícitamente:

- `MISSING_PROFILE`;
- `PENDING`;
- `CLASSIFIED_VALID`;
- `INACTIVE_PROFILE`;
- `INACTIVE_FAMILY`;
- `INVALID_PROFILE`.

No consulta `CategoriaServicio`, nombre o descripción para decidir estado o
metadata.

### Backfill

La migración `gestion.0023_backfill_pending_technical_profiles` crea una fila
OneToOne sólo cuando el Servicio no tiene perfil:

```text
estado_clasificacion = PENDIENTE
nivel_riesgo = NO_DEFINIDO
familia = NULL
activa = true
```

El servicio de backfill usa la misma semántica para Servicios creados después de
la migración. Ambos caminos son idempotentes y preservan perfiles existentes,
incluidos los ya clasificados.

### Comando

```text
python manage.py report_unclassified_services
python manage.py report_unclassified_services --backfill
python manage.py report_unclassified_services --all
```

Sin opciones muestra los estados que requieren atención. `--backfill` crea
perfiles pendientes faltantes antes de reportar. `--all` incluye también los
clasificados válidos.

## B2 — Historial realizado incompleto

El evaluador consulta además Turnos `REALIZADO` con fecha menor o igual a
`fecha_solicitada` que no tengan ningún `DetalleTurno`.

Cada inconsistencia usa el code estable:

```text
REALIZED_TURNO_WITHOUT_DETAILS
```

Semántica:

- se agrega a `missing_data`;
- se agrega a `historial_considerado` e `inconsistencias_historial`;
- dispara evidencia `HISTORY_INCONSISTENCY`;
- conserva `turno_id`, fecha, hora, estado y `detalle_count=0`;
- produce como mínimo `REQUIERE_REVISION`;
- no inventa el Servicio realizado;
- no produce `NO_APTO` clínico.

Los Turnos posteriores a `fecha_solicitada` se ignoran. La ausencia legítima de
Turnos no genera inconsistencia, y un Turno realizado con Detalles continúa por
la evaluación normal.

## B3 — Inmutabilidad histórica

La reauditoría final detectó dos bypasses en la primera corrección: el manager
base de Django conservaba un `QuerySet` estándar y `bulk_create()` heredaba el
modo UPSERT mediante `update_conflicts=True`. Ambos caminos podían modificar una
fila sin ejecutar `save()`.

La migración `gestion.0024_alter_evaluacionriesgotecnico_options` fija
`base_manager_name` y `default_manager_name` en `objects`. En runtime,
`objects`, `_default_manager`, `_base_manager` y los managers relacionados usan
`ImmutableTechnicalRiskEvaluationQuerySet`.

`EvaluacionRiesgoTecnico` permite creación inicial mediante `create()` y luego
rechaza explícitamente:

- `save()` de una fila persistida;
- `delete()` de instancia;
- `QuerySet.update()`;
- `QuerySet.delete()`;
- `bulk_update()`;
- `update_or_create()`;
- toda variante de `bulk_create()`, incluido `update_conflicts=True`.

Se prohíbe también `bulk_create()` normal porque omite `save()`, `full_clean()` y
la auditoría de creación; no hay una necesidad productiva de creación masiva
para esta evidencia histórica. `get_or_create()` se conserva: puede crear por el
camino normal o devolver una fila existente, pero nunca actualiza esta última
con `defaults`.

Esto protege Cliente, política, outcome, severidad, fecha solicitada,
`evaluated_at` y ambos snapshots frente a las APIs ORM productivas. No existe
ViewSet/API de evaluaciones, por lo que no hay endpoints genéricos de POST, PUT,
PATCH o DELETE que cerrar. `persist_technical_risk_evaluation()` sigue siendo la
única vía productiva soportada de creación auditada.

No se agregó un trigger de base de datos: la arquitectura no usa triggers para
estas invariantes y el alcance solicitado es cerrar managers, querysets,
servicios y APIs ORM productivas, no impedir SQL manual administrativo.

### `superseded_by`

`supersede_technical_risk_evaluation()` es una operación transaccional y
semántica. Requiere:

- E1 y E2 existentes y distintas;
- mismo Cliente;
- E2 posterior a E1;
- E1 sin reemplazo incompatible;
- E2 todavía vigente.

La operación sólo fija `E1.superseded_by = E2` mediante
`_set_superseded_by()`, una ruta interna del manager que no acepta otros campos.
El flag de instancia `_allow_explicit_supersession` fue eliminado, por lo que no
es posible habilitar un `save()` genérico desde código llamador. El servicio
mantiene locks, validación de Cliente y orden temporal, rechazo de
self-reference/ciclos e idempotencia para el mismo par, y registra
`TECHNICAL_ASSESSMENT_SUPERSEDED`. No tiene consumidor productivo en Incremento
A.

## Tests

Suite BH-057 A:

```text
gestion.tests.test_technical_risk_profiles
gestion.tests.test_technical_risk_models
gestion.tests.test_technical_risk_evaluator
gestion.tests.test_technical_risk_policy_api

54/54 OK
```

Cobertura nueva:

- todos los estados del inventario;
- backfill conservador e idempotente;
- preservación de perfil clasificado;
- comando y reporte de pendientes;
- historial inconsistente anterior y futuro;
- distinción entre historial vacío, válido e inconsistente;
- snapshot y outcome de inconsistencia;
- rechazo de cambios de outcome, snapshot, política y Cliente;
- rechazo de eliminación, `objects.update()`, `_default_manager.update()`,
  `_base_manager.update()` y updates por managers relacionados;
- rechazo explícito de `bulk_update()`, `bulk_create()` normal,
  `bulk_create(update_conflicts=True)` y `update_or_create()`;
- `get_or_create()` sobre una fila existente no la modifica;
- creación inicial normal permitida;
- supersesión válida, idempotente, auditada, sin self-reference ni ciclos;
- rechazo de supersesión directa incluso con el antiguo flag de instancia;
- preservación de E1/v1 frente a E2/v2.

Regresión solicitada: **126/126 OK**.

## Fronteras preservadas

No se modificaron:

- `Turno.alerta_daño_capilar`;
- `Turno.Estado.SUGERIDO`;
- `ACTIVE_TURNO_STATES`;
- `TurnoCreationService` para consumir el evaluador;
- flujo productivo de reserva;
- HOLD, pagos, Mercado Pago o confirmación financiera;
- Incremento B.

## Resultado

BH-057 A BLOCKERS = CORREGIDOS

BH-057 A B3 = CORREGIDO
