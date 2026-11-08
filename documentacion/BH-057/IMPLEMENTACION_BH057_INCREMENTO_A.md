# Implementación BH-057 — Incremento A

## Estado

Se implementó la base técnica versionada para evaluar riesgo de reserva sin
activar el nuevo flujo productivo de Turnos.

No se implementaron solicitud productiva, cola de revisión, frontend, HOLD,
pagos, Mercado Pago ni confirmación de Turnos. Tampoco se modificaron
`Turno.alerta_daño_capilar`, `Turno.Estado.SUGERIDO` ni
`ACTIVE_TURNO_STATES`.

## Modelos creados

- `FamiliaProcesoTecnico`: catálogo técnico independiente de
  `CategoriaServicio`, con `code` estable, nombre, descripción y estado activo.
- `PerfilTecnicoServicio`: metadata OneToOne por `Servicio`, familia opcional,
  estado `PENDIENTE`/`CLASIFICADO`, nivel de riesgo estable y estado activo.
- `PoliticaRiesgoTecnico`: versión única y estados `BORRADOR`, `PUBLICADA` y
  `RETIRADA`, con fecha y actor de publicación.
- `ReglaIntervaloTecnico`: selectores exclusivos Servicio/familia para origen y
  destino, días mínimos, outcome, severidad, prioridad y mensajes.
- `ReglaDiagnosticoTecnico`: selector Servicio/familia, obligatoriedad,
  antigüedad opcional y outcomes separados para faltante, vencido, incompleto y
  procedencia no confiable.
- `ReglaFrecuenciaTecnica`: selector Servicio/familia, ventana, máximo de
  eventos y outcome; no usa scoring.
- `EvaluacionRiesgoTecnico`: Cliente, política, outcome, severidad,
  `fecha_solicitada`, fecha de evaluación y snapshots JSON validados.

Los outcomes se centralizaron en `TechnicalRiskOutcome`:

1. `APTO`
2. `ADVERTENCIA`
3. `REQUIERE_REVISION`
4. `NO_APTO`

`TECHNICAL_RISK_OUTCOME_ORDER` define la precedencia restrictiva. La prioridad
sólo ordena evidencia y mensajes; no puede rebajar el outcome.

## Migración

Se creó:

- `gestion/migrations/0022_familiaprocesotecnico_diagnosticocapilar_procedencia_and_more.py`
- `gestion/migrations/0023_backfill_pending_technical_profiles.py`

La migración crea toda la estructura, agrega procedencia al diagnóstico actual
y a su histórico, crea los permisos y los asigna de forma idempotente:

- `gestion.review_technical_booking`
  - `PROFESIONAL`
  - `ADMINISTRADOR`
- `gestion.manage_technical_risk_policy`
  - `ADMINISTRADOR`

No se sembraron familias técnicas ni reglas clínicas. La migración `0023` crea,
de forma idempotente, un perfil `PENDIENTE`, sin familia y con riesgo
`NO_DEFINIDO`, para cada Servicio existente que carecía de perfil. No modifica
perfiles existentes. Los ejemplos de días aparecen exclusivamente como fixtures
de tests.

## Inventario y backfill conservador

`technical_risk_profile_services.py` expone:

- `technical_service_profile_inventory()`;
- `backfill_missing_technical_profiles()`.

El inventario distingue `MISSING_PROFILE`, `PENDING`, `CLASSIFIED_VALID`,
`INACTIVE_PROFILE`, `INACTIVE_FAMILY` e `INVALID_PROFILE`, e informa IDs,
nombres, perfil, estado, riesgo y code de familia sin inferir metadata desde
nombre, descripción o categoría comercial.

El comando:

```text
python manage.py report_unclassified_services
python manage.py report_unclassified_services --backfill
python manage.py report_unclassified_services --all
```

permite reportar, completar conservadoramente faltantes posteriores a la
migración y verificar el catálogo. El backfill es idempotente y nunca asigna
familia, riesgo real ni estado `CLASIFICADO`.

## Política y publicación

`publish_technical_risk_policy()` es la única vía de publicación soportada.
El servicio:

- exige `gestion.manage_technical_risk_policy` al actor;
- bloquea y relee el borrador dentro de una transacción;
- valida selectores, constraints, codes duplicados entre familias de reglas y
  referencias inactivas;
- registra fecha y actor;
- crea auditoría con el evento `TECHNICAL_POLICY_PUBLISHED`.

Una política debe crearse como borrador. Una política publicada y todas sus
reglas rechazan modificación y eliminación. Mover una regla entre políticas
también está prohibido.

## API administrativa mínima

Se agregaron endpoints DRF para:

- familias técnicas;
- perfiles técnicos de Servicio;
- políticas y acción `publicar`;
- reglas de intervalo;
- reglas de diagnóstico;
- reglas de frecuencia.

Todos exigen autenticación y el permiso exacto
`gestion.manage_technical_risk_policy`. `is_staff`, el nombre de un
`BusinessRole` y `Personal.rol` no autorizan por sí mismos. Un permiso individual
sí funciona.

## Contrato del evaluador

El servicio público es:

```python
evaluate_booking_risk(
    *,
    cliente,
    servicios,
    fecha_solicitada,
    policy_version=None,
)
```

Devuelve `TechnicalRiskEvaluationResult`, que incluye:

- Cliente, política y versión aplicada;
- fecha solicitada;
- outcome y severidad;
- todos los `rule_codes` aplicables;
- datos faltantes e historial relevante;
- fecha mínima global recomendada;
- mensajes de Cliente y profesional;
- snapshot de entrada y resultado.

El evaluador sólo lee. No crea ni modifica Cliente, Turno, DetalleTurno,
Rutina, AgendaCuidados, Notificación, Pago, evaluación persistida ni auditoría.
La persistencia está separada en `persist_technical_risk_evaluation()`, que crea
la evaluación y una auditoría mínima `TECHNICAL_ASSESSMENT_CREATED`.

Una evaluación persistida es inmutable por `save()`, `delete()`,
`QuerySet.update()` y `QuerySet.delete()`. No existe un ViewSet/API de
evaluaciones, por lo que tampoco hay una superficie HTTP genérica de
POST/PUT/PATCH/DELETE. La única creación soportada sigue siendo el servicio de
persistencia.

`supersede_technical_risk_evaluation()` es la única transición soportada para
`superseded_by`: exige dos evaluaciones del mismo Cliente, que la reemplazante
sea posterior y que ninguna relación incompatible exista. Sólo agrega el vínculo;
no puede cambiar outcome, política, Cliente, fecha ni snapshots de E1, y audita
`TECHNICAL_ASSESSMENT_SUPERSEDED`. Todavía no tiene consumidor productivo.

## Semántica de evaluación

### Fecha e historial

Todas las ventanas, antigüedades e intervalos se calculan contra
`fecha_solicitada`; el evaluador no usa la fecha actual.

Los antecedentes principales son `Turno.estado=REALIZADO` más `DetalleTurno`.
No se exige `FichaTecnica`. Como todavía no existe `finalizado_at`, el snapshot
conserva la fecha y hora planificadas del Turno; ésta es una limitación conocida.

Un Turno `REALIZADO` en o antes de `fecha_solicitada` sin ningún
`DetalleTurno` se conserva como inconsistencia
`REALIZED_TURNO_WITHOUT_DETAILS`. No se inventa el Servicio realizado: se agrega
a `missing_data`, al snapshot y a la evidencia disparada, y el resultado mínimo
es `REQUIERE_REVISION`. Un Turno futuro no contamina la evaluación y un Cliente
sin Turnos no se confunde con historial corrupto.

### Intervalos

La especificidad aplicada es:

1. Servicio exacto → Servicio exacto;
2. Servicio exacto → familia o familia → Servicio exacto;
3. familia → familia.

Se conservan todas las reglas de la mayor especificidad aplicable. También se
evalúan interacciones dirigidas entre Servicios incluidos en una misma solicitud
multiservicio, con intervalo efectivo de cero días.

### Diagnóstico

Se evalúan existencia, antigüedad, completitud y procedencia. Sólo
`PROFESIONAL` es confiable inicialmente. No se interpreta texto libre ni se usa
el scoring de `ConfiguracionDiagnostico`.

### Frecuencia

Se cuentan eventos realizados y Servicios solicitados que coinciden con el
selector dentro de una ventana explícita. El límite exacto se permite; se
dispara la regla sólo si la cantidad proyectada supera `cantidad_maxima`.

### Multiservicio

No se corta en la primera regla. El resultado global usa el outcome más
restrictivo, conserva todos los codes y toma el máximo de las fechas mínimas
calculadas.

### Fail-closed

- Política inexistente, versión desconocida/no publicada, Servicio solicitado
  inactivo o entrada inválida producen error de configuración/entrada; nunca
  `APTO`.
- Antes de decidir se revalidan las reglas activas y sus referencias. Selectores
  inválidos, codes duplicados o referencias desactivadas después de publicar
  producen error de configuración.
- Un Servicio sin perfil, con perfil pendiente/inactivo o sin riesgo definido
  genera `SERVICE_TECHNICAL_PROFILE_MISSING` y
  `REQUIERE_REVISION`.
- Ese resultado de configuración incompleta se distingue de un `NO_APTO`
  técnico derivado de una regla explícita.
- Un Turno realizado sin Detalles genera `REQUIERE_REVISION` operativo, no
  `NO_APTO` clínico ni `APTO` silencioso.

## Snapshot y privacidad

El snapshot conserva IDs, metadata técnica, familias/codes, fecha solicitada,
historial considerado, fecha/hora de eventos, diagnóstico usado, procedencia,
completitud, datos faltantes, reglas disparadas, parámetros efectivos,
intervalos, versión, outcome, mensajes y fecha mínima.

No copia fórmula, fotografías, observaciones de proceso, recomendaciones ni
notas libres completas. La auditoría de persistencia contiene sólo IDs, versión,
outcome y rule codes.

## Procedencia de diagnóstico

Se agregó `DiagnosticoCapilar.procedencia` con:

- `PROFESIONAL` para la API profesional;
- `AUTORREPORTE` para registro/autorreporte;
- `POST_SERVICIO_AUTOMATICO` para el diagnóstico automático al finalizar;
- `MIGRADO` disponible para migraciones futuras;
- `DESCONOCIDO` como default conservador para registros legacy.

No se infiere confianza a partir de `profesional=NULL`.

## Modo comparación

`compare_legacy_and_technical_risk()` ejecuta en paralelo diagnóstico:

- `TurnoCreationService._requires_hair_damage_alert()`;
- `SaludCapilarService.obtener_bloqueo_salud_capilar()`;
- `evaluate_booking_risk()`.

Reporta divergencia, pero nunca usa la lógica legacy como fallback ni altera la
decisión canónica. Se mantiene documentado que el alerta legacy usa categoría
comercial, fecha actual y un booleano no explicable.

## Tests y validación

Suites nuevas:

- `gestion.tests.test_technical_risk_models`
- `gestion.tests.test_technical_risk_evaluator`
- `gestion.tests.test_technical_risk_policy_api`
- `gestion.tests.test_technical_risk_profiles`

Resultado: **49/49 tests BH-057 A OK**.

Cobertura incluida:

- constraints y publicación;
- inmutabilidad y versionado;
- cuatro combinaciones de selectores de intervalo y precedencia;
- 45/44 días, eventos posteriores a la fecha solicitada y fecha mínima máxima;
- diagnóstico vigente, vencido, faltante, incompleto y no confiable;
- frecuencia, límite exacto, fuera de ventana y multiservicio;
- precedencia global de outcomes;
- Servicio no clasificado y versiones inválidas;
- snapshots y privacidad;
- ausencia de efectos laterales;
- persistencia/auditoría separada;
- comparación legacy sin fallback;
- permisos API, incluido `is_staff` sin permiso y permiso individual.
- inventario y backfill conservador e idempotente de perfiles;
- Turno realizado sin Detalles, límite temporal y distinción de historial vacío;
- inmutabilidad de evaluaciones por instancia y QuerySet;
- supersesión controlada y regresión E1/v1 frente a E2/v2.

Regresión ejecutada:

- BH-056 skills;
- autorización y procedencia de diagnóstico;
- creación y reprogramación de Turnos;
- roles;
- endpoint `/me/`.

Resultado: **126/126 tests de regresión OK**.

Validaciones finales:

- `python manage.py check`: OK.
- `python manage.py makemigrations --check`: sin cambios.
- `python -m compileall gestion usuarios`: OK.
- `git diff --check`: OK; sólo avisos informativos de normalización CRLF/LF en
  archivos preexistentes.

## Desviaciones y decisiones respecto del análisis

- La regla de frecuencia se incluyó en este incremento porque pudo implementarse
  de forma mínima, explícita y sin scoring.
- La procedencia de diagnóstico se agregó ahora, con default conservador para
  legacy.
- No se creó una entidad de solicitud ni cola aunque el análisis global las
  contempla para incrementos posteriores; el alcance solicitado termina en la
  evaluación técnica.
- No se infirieron familias desde categorías, nombres o descripciones porque la
  base local no permite validar clasificaciones reales. Sólo se crearon perfiles
  pendientes conservadores.
- `superseded_by` tiene un servicio semántico controlado, sin implementar todavía
  un workflow productivo que lo consuma.

## Resultado

BH-057 A = VALIDADO

BH-057 A BLOCKERS = CORREGIDOS
