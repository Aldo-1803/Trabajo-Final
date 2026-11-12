# Verificación final de B3 — BH-057 A

Fecha: 2026-10-24

Alcance exclusivo: inmutabilidad y supersesión de
`EvaluacionRiesgoTecnico`. No se reauditaron B1/B2 ni Incremento B.

## Resultado de los caminos ORM

| Camino | Resultado |
|---|---|
| `save()` sobre instancia persistida | Bloqueado por `ValidationError` |
| `objects.update()` | Bloqueado |
| `_base_manager.update()` | Bloqueado |
| `_default_manager.update()` | Bloqueado |
| `bulk_update()` | Bloqueado explícitamente |
| `bulk_create()` normal | Bloqueado por la política adoptada |
| `bulk_create(update_conflicts=True)` | Bloqueado explícitamente |
| `update_or_create()` | Bloqueado; no modifica la fila existente |
| `get_or_create()` sobre existente | Devuelve la fila sin aplicar `defaults` |
| `delete()` de instancia o QuerySet | Bloqueado |
| managers relacionados | Usan el mismo QuerySet inmutable |

Como comprobación adicional, se construyó una instancia nueva con la PK de una
evaluación existente y se invocó `save()`. La operación fue rechazada por
`ValidationError`; outcome, severity y snapshot permanecieron intactos. La
prueba se ejecutó en la base de tests dentro de una transacción revertida.

## Managers y migración

`base_manager_name` y `default_manager_name` apuntan a `objects`. En runtime,
`objects`, `_base_manager` y `_default_manager` producen
`ImmutableTechnicalRiskEvaluationQuerySet`; los managers inversos heredan la
misma protección. La migración
`0024_alter_evaluacionriesgotecnico_options.py` coincide con estas opciones.
`makemigrations --check` no detectó cambios.

## Supersesión

`supersede_technical_risk_evaluation()` mantiene locks y valida evaluaciones
distintas, mismo Cliente, orden temporal y estado de supersesión. La escritura
interna `_set_superseded_by()` está acotada a una sola columna: no acepta ni
actualiza outcome, severity, Cliente, política, fecha, `evaluated_at` o
snapshots. La transacción registra `TECHNICAL_ASSESSMENT_SUPERSEDED`.

La repetición del mismo par es idempotente y no duplica auditoría. La
self-reference y la inversión de la cadena se rechazan; el orden temporal
estricto impide ciclos por el servicio soportado.

## Cobertura

Los tests contienen casos explícitos para:

- `save()` y `delete()` de una evaluación persistida;
- `objects.update()`, `_base_manager.update()`, `_default_manager.update()` y
  update mediante managers relacionados;
- `bulk_update()`;
- `bulk_create()` normal y con `update_conflicts=True`;
- `update_or_create()` y ambos resultados de `get_or_create()`;
- rechazo del antiguo flag de supersesión directa;
- supersesión, idempotencia, auditoría, self-reference y ciclo inverso;
- preservación de la evidencia histórica de E1.

## Ejecución

- Suite BH-057 A: **54/54 OK**.
- `python manage.py check`: OK.
- `python manage.py makemigrations --check`: OK, sin cambios.
- `python -m compileall gestion usuarios`: OK.
- `git diff --check`: exit code 0; sólo avisos de normalización CRLF/LF, sin
  errores de whitespace.

No se identificó un bypass ORM productivo restante dentro del alcance definido.

BH-057 A = VALIDADO
