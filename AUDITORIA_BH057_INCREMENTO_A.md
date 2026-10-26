# Auditoría independiente — BH-057 Incremento A

Fecha: 2026-10-24

## 1. Conclusión ejecutiva

La implementación cubre la mayor parte del núcleo técnico: metadata explícita,
políticas versionadas, tres tipos de reglas, evaluador puro y multiservicio,
procedencia de diagnóstico, snapshots, permisos, API administrativa y pruebas.
También respeta la frontera con Turnos, pagos y BH-058.

No obstante, el Incremento A no puede validarse como completo por tres brechas
concretas:

1. no existe el reporte/inventario de Servicios sin clasificación ni una
   migración conservadora que cree metadata pendiente para los Servicios
   existentes;
2. un historial estructuralmente inconsistente puede desaparecer de la entrada
   del evaluador y terminar en `APTO`;
3. `EvaluacionRiesgoTecnico` no es inmutable: una evaluación histórica puede
   editarse o eliminarse mediante las operaciones ordinarias del modelo.

Las suites pasan, pero no ejercitan esos escenarios.

## 2. Fuentes y método

Se contrastaron de forma independiente:

- `ANALISIS_BH057_HISTORIAL_RIESGO.md`;
- implementación real y diff del repositorio;
- migración `gestion.0022`;
- modelos, serializers, ViewSets, permisos y roles;
- servicios de publicación, evaluación y comparación;
- las tres suites BH-057 A;
- `IMPLEMENTACION_BH057_INCREMENTO_A.md`;
- regresiones solicitadas y validaciones estáticas.

No se modificó código. La única escritura de esta auditoría es este documento.

## 3. Inventario real

### Modelos y migración

- `TechnicalRiskOutcome` y `TECHNICAL_RISK_OUTCOME_ORDER`.
- `FamiliaProcesoTecnico`.
- `PerfilTecnicoServicio`.
- `PoliticaRiesgoTecnico`.
- `ReglaIntervaloTecnico`.
- `ReglaDiagnosticoTecnico`.
- `ReglaFrecuenciaTecnica`.
- `EvaluacionRiesgoTecnico`.
- `DiagnosticoCapilar.procedencia`, incluido el modelo histórico.
- Migración
  `0022_familiaprocesotecnico_diagnosticocapilar_procedencia_and_more.py`.

La migración crea esquema y permisos. No crea familias, perfiles ni reglas de
negocio.

### Permisos

- `gestion.review_technical_booking`.
- `gestion.manage_technical_risk_policy`.
- Catálogo canónico en `usuarios/roles.py`.
- Seed idempotente por `update_or_create` y asignación a grupos:
  - `PROFESIONAL`: revisión técnica;
  - `ADMINISTRADOR`: revisión y gestión de políticas.

### Servicios

- `technical_risk_policy_services.py`: validación y publicación explícita.
- `technical_risk_evaluator.py`: evaluación pura y persistencia separada.
- `technical_risk_comparison.py`: comparación diagnóstica contra legacy.

### API

CRUD administrativo para familias, perfiles, políticas y tres familias de
reglas, más acción `publicar`, bajo
`gestion.manage_technical_risk_policy`.

No existe API de evaluación productiva, solicitud técnica, cola o decisión.

### Tests

- `test_technical_risk_models.py`: 9 tests.
- `test_technical_risk_evaluator.py`: 23 tests.
- `test_technical_risk_policy_api.py`: 6 tests.
- Total BH-057 A: 38 tests.

### Documentación

- `ANALISIS_BH057_HISTORIAL_RIESGO.md`.
- `IMPLEMENTACION_BH057_INCREMENTO_A.md`.
- Este informe independiente.

## 4. Matriz requisito → evidencia → estado

| # | Requisito | Evidencia real | Estado |
|---|---|---|---|
| 1 | Alcance real del Incremento A | Existen modelos, migración, permisos, servicios, API y tests. No existe reporte de Servicios sin perfil ni backfill conservador a perfiles `PENDIENTE`, requeridos en el punto 23.6 del análisis. | **PARCIAL** |
| 2 | Perfil técnico separado de categoría comercial | `FamiliaProcesoTecnico` tiene `code` único; `PerfilTecnicoServicio` es OneToOne con estado y riesgo. El evaluador no consulta nombre, descripción ni `CategoriaServicio`. | **COMPLETO** |
| 3 | Política versionada y publicación explícita | `version`, estado, timestamps y actor; publicación transaccional y auditada. `save/delete`, serializers y API bloquean cambios publicados por caminos ordinarios. | **COMPLETO** |
| 4 | Reglas de intervalo | Selectores exclusivos en constraints DB, días, outcome, severidad, prioridad, mensajes, activa y code. `_interval_specificity()` implementa 3 > 2 > 1 y conserva empates. | **COMPLETO** |
| 5 | Reglas de diagnóstico | Selector exclusivo, antigüedad configurable y outcomes separados para falta, vencimiento, incompletitud y procedencia. No hay 90 días globales. | **COMPLETO** |
| 6 | Frecuencia | `N` eventos en ventana `X`, selector Servicio/familia y outcome explícito, sin score. | **COMPLETO** |
| 7 | Outcomes canónicos | Enum único con `APTO`, `ADVERTENCIA`, `REQUIERE_REVISION`, `NO_APTO`; orden 0/1/2/3 y agregación por máximo. | **COMPLETO** |
| 8 | Evaluador | Firma conceptual correcta; deduplica Servicios, evalúa todos, conserva triggers y codes, usa `fecha_solicitada`, outcome restrictivo y máximo de fechas mínimas. | **COMPLETO** |
| 9 | Pureza | `evaluate_booking_risk()` sólo consulta. La creación de evaluación/auditoría está en `persist_technical_risk_evaluation()`. El test de efectos laterales verifica Cliente y conteos de Turno, Detalle, Rutina, Agenda, Pago, Notificación, Evaluación y Auditoría. | **COMPLETO** |
| 10 | Historial técnico | Consulta `DetalleTurno` unido a `Turno REALIZADO`, sin exigir Ficha, y conserva fecha/hora planificadas. No detecta Turnos `REALIZADO` sin Detalles u otras inconsistencias estructurales. | **PARCIAL** |
| 11 | Procedencia | Enum explícito; legacy queda `DESCONOCIDO`; registro público usa `AUTORREPORTE`, API profesional `PROFESIONAL` y finalización automática `POST_SERVICIO_AUTOMATICO`. Sólo `PROFESIONAL` es confiable. | **COMPLETO** |
| 12 | Snapshot explicable | Guarda versión, Servicios/perfiles/familias, fecha, historial, diagnóstico, datos faltantes, triggers, parámetros, evidencia, outcome, mensajes y fecha mínima. `evaluated_at` queda normalizado en el modelo. | **COMPLETO** |
| 13 | Inmutabilidad histórica | V1 y V2 no se mezclan y el snapshot conserva valores efectivos disparados. Sin embargo, `EvaluacionRiesgoTecnico.save()` permite actualizar una fila existente y no se sobreescribe `delete()`. | **PARCIAL** |
| 14 | Configuración inválida fail-closed | Política ausente/no publicada y referencias activas inválidas lanzan `TechnicalRiskConfigurationError`; Servicio sin perfil da revisión, no `NO_APTO`. El historial inconsistente no se detecta y puede terminar en `APTO`. | **PARCIAL** |
| 15 | Multiservicio | Evalúa todos los Servicios, interacciones dirigidas, todos los triggers, precedencia global y máximo de fechas mínimas. | **COMPLETO** |
| 16 | Datos faltantes | Diagnóstico faltante/vencido/incompleto/no confiable y perfil faltante están cubiertos; no existe regla global “sin historial = NO_APTO”. Falta escalación de historial inconsistente. | **PARCIAL** |
| 17 | Permisos nuevos | Ambos permisos existen en modelo, migración y catálogo; grupos correctos; `is_staff` no sustituye permiso; permiso individual está probado. | **COMPLETO** |
| 18 | Administración de políticas | Todos los endpoints usan `IsAuthenticated` + `CanManageTechnicalRiskPolicy`; no se usa rol o staff como autoridad directa. No se exige UI. | **COMPLETO** |
| 19 | Auditoría | Publicación registra actor, versión y transición; persistencia registra evaluación, versión, outcome y codes sin datos sensibles. El evento de evaluación admite actor nulo y no copia `policy_id` directamente al payload. | **PARCIAL** |
| 20 | Comparación legacy | Existe helper y test de divergencia, sin fallback ni consumo en `TurnoCreationService`. No hay invocación operacional o comando que ejecute comparación fuera de tests. | **PARCIAL** |
| 21 | Alerta legacy | `Turno.alerta_daño_capilar` sigue presente y el evaluador nuevo no adquirió autoridad productiva. | **COMPLETO** |
| 22 | `SUGERIDO` y estados activos | El evaluador no crea Turnos. No hay diff en `turno_creation_services.py` ni `turno_management_services.py`; `SUGERIDO` sigue en el flujo legacy. | **COMPLETO** |
| 23 | Frontera BH-058 | No se añadieron `SolicitudTecnicaReserva`, HOLD, `PaymentIntent`, seña, webhook, Pago o Mercado Pago por BH-057. Las funciones de pago encontradas son legacy preexistente. | **FUERA DE ALCANCE** |
| 24 | Datos y seeds | `0022` sólo siembra permisos. No contiene 45/90 días, familias inventadas ni umbrales de frecuencia. Esos valores sólo aparecen en tests. | **COMPLETO** |
| 25 | Cobertura de tests | Buena cobertura de reglas, precedencia, fecha, pureza, permisos y comparación. Faltan los escenarios críticos detallados en la sección 8. | **PARCIAL** |
| 26 | Regresión y checks | 38/38 BH-057, 126/126 regresiones, `check`, migraciones, compilación y diff pasan. | **COMPLETO** |
| 27 | Documento de implementación | La mayoría de las afirmaciones coincide. Sobregeneraliza la inmutabilidad y no informa la ausencia del reporte/backfill de no clasificados ni la falta de detección de historial inconsistente. | **PARCIAL** |
| 28 | Veredicto | Hay blockers concretos de completitud, fail-closed e integridad histórica. | **NO VALIDABLE** |

## 5. Blockers reales

### B1. Falta el inventario y la migración conservadora de Servicios no clasificados

El Incremento 1 del análisis exige preparar un reporte de Servicios no
clasificados y una migración conservadora de metadata existente.

La migración `0022` no crea perfiles `PENDIENTE` ni genera un inventario. El
endpoint de perfiles parte de `PerfilTecnicoServicio`, por lo que tampoco puede
listar Servicios que no tienen ninguna fila de perfil. La búsqueda de
`perfil_tecnico__isnull`, reporte o comando equivalente no devuelve
implementación.

El evaluador escala correctamente un Servicio cuando ya llega a evaluación, pero
eso no sustituye el entregable operativo necesario para identificar y completar
el catálogo antes de activar consumidores.

### B2. Historial inconsistente puede fallar abierto

`_history_for_client()` comienza la consulta en `DetalleTurno` y filtra su Turno
como `REALIZADO`. No consulta independientemente los Turnos realizados ni marca
inconsistencias.

Caso concreto:

1. existe un `Turno` `REALIZADO` para el Cliente;
2. por datos legacy/corruptos, no tiene `DetalleTurno`;
3. el historial resultante es vacío;
4. si los Servicios solicitados tienen perfil y no dispara otra regla,
   `triggers` queda vacío;
5. el evaluador devuelve `APTO`.

Esto contradice la conducta explícita del análisis: “historial inconsistente →
marcar inconsistencia y escalar”. Es un fallo abierto en datos históricos, no
una mera ausencia legítima de historial.

### B3. La evaluación histórica persistida es mutable

`EvaluacionRiesgoTecnico.save()` sólo ejecuta `full_clean()` y luego guarda. No
distingue creación de actualización, y el modelo tampoco protege `delete()`.
Por lo tanto, una evaluación persistida puede cambiar por una operación ordinaria
de modelo:

- política;
- outcome/severidad;
- fecha solicitada;
- snapshots;
- relación `superseded_by`;
- o puede eliminarse.

Que no exista todavía un endpoint de edición reduce exposición, pero no convierte
la inmutabilidad histórica en un invariante. El snapshot preserva una decisión
sólo mientras nadie edite la propia evaluación.

## 6. Deudas no bloqueantes

1. **Bulk ORM:** `QuerySet.update()` y `QuerySet.delete()` evitan los hooks de
   modelo que protegen políticas y reglas publicadas. Los caminos API,
   serializer, servicio y `save/delete` de instancia sí están protegidos, por lo
   que se registra como endurecimiento pendiente y no como B3.
2. **Snapshot de diagnóstico:** conserva fecha, procedencia, completitud y mapa
   de presencia, pero no copia los IDs de los cinco valores discretos. Hoy las
   reglas nuevas sólo usan presencia/procedencia/edad, por lo que la decisión
   actual sigue siendo reconstruible; conviene copiar esos valores antes de que
   una regla los use.
3. **Metadata de eventos históricos:** la familia de un antecedente se toma del
   perfil actual del Servicio al evaluar. E1 queda congelada en su snapshot, pero
   una reevaluación futura puede reclasificar retrospectivamente el evento.
4. **Auditoría de evaluación:** `TECHNICAL_ASSESSMENT_CREATED` permite actor nulo
   sin distinguir explícitamente “sistema” y no incluye `policy_id` en el JSON,
   aunque éste se recupera desde la evaluación referenciada.
5. **Comparación:** existe como función y test, pero no como comando o ejecución
   observable. Esto evita alterar producción, aunque limita su utilidad como
   medición de divergencias.
6. **Estado `RETIRADA`:** está modelado, pero no hay transición explícita de
   retiro; una política ya publicada tampoco puede pasar a retirada mediante su
   `save()` actual.

## 7. Trabajo fuera de alcance detectado

No se detectó trabajo nuevo atribuible a BH-057 en:

- solicitud productiva o cola técnica;
- HOLD;
- pagos, seña, `PaymentIntent`, Mercado Pago o webhook;
- creación o confirmación de Turnos;
- cambios productivos de disponibilidad/reprogramación;
- retiro de `alerta_daño_capilar` o `SUGERIDO`;
- frontend del nuevo flujo;
- Incremento B.

Las implementaciones de Pago/Mercado Pago encontradas ya existían y no forman
parte del diff de BH-057. La regla de frecuencia y la API administrativa son
compatibles con el diseño y no adelantan BH-058.

## 8. Tests faltantes críticos

### Críticos para los blockers

1. Turno `REALIZADO` sin `DetalleTurno` debe producir inconsistencia/revisión o
   error operativo, nunca `APTO` silencioso.
2. Una evaluación persistida debe rechazar edición y eliminación ordinarias.
3. El reporte de no clasificados debe incluir tanto perfiles `PENDIENTE` como
   Servicios sin fila de perfil; el backfill debe ser conservador e idempotente.

### Importantes, no bloqueantes por sí solos

4. Cambiar posteriormente perfil/familia/Diagnóstico no altera el snapshot E1.
5. `QuerySet.update/delete` no puede mutar política/reglas publicadas, si se
   adopta inmutabilidad reforzada a nivel manager/DB.
6. Seed de permisos ejecutado dos veces mantiene permisos y grupos sin
   duplicados.
7. Snapshot de diagnóstico conserva valores discretos cuando éstos pasen a ser
   parámetros efectivos.
8. Comparación ejecutable fuera del test produce una salida observable sin
   cambiar decisiones productivas.
9. Evento de evaluación diferencia actor humano de sistema y correlaciona
   política/evaluación de forma explícita.

## 9. Validaciones ejecutadas

### BH-057 A

```text
python manage.py test \
  gestion.tests.test_technical_risk_models \
  gestion.tests.test_technical_risk_evaluator \
  gestion.tests.test_technical_risk_policy_api \
  --keepdb --verbosity 1

38 tests — OK
```

### Regresiones

```text
gestion.tests.test_skills_api
gestion.tests.test_turno_skill_compatibility
gestion.tests.test_diagnosis_authorization_api
gestion.tests.test_turno_creation_api
gestion.tests.test_turno_management_api
usuarios.test_roles
usuarios.test_current_session_api

126 tests — OK
```

La suite de creación incluye disponibilidad canónica y conflictos de agenda; la
de gestión incluye reprogramación.

### Checks

- `python manage.py check`: OK.
- `python manage.py makemigrations --check`: `No changes detected`.
- `python -m compileall gestion usuarios`: OK.
- `git diff --check`: OK; sólo warnings informativos CRLF/LF en archivos ya
  modificados del workspace.

## 10. Decisión final

BH-057 A = NO VALIDABLE
