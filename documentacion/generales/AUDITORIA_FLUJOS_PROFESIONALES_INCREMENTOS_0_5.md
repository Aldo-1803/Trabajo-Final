# Auditoría independiente — Flujos profesionales, Incrementos 0–5

**Fecha:** 2026-11-19
**Rama auditada:** `save/work-in-progress`
**HEAD auditado:** `2de633ce5d0008ff7ee127fb6aafab27bff83113`
**Tipo de entrega:** auditoría posterior e independiente; no reabre BH-062
**Veredicto:** `FLUJOS PROFESIONALES 0–5 = LISTOS PARA CIERRE TÉCNICO`

## 1. Baselines e integridad histórica

La auditoría histórica de BH-062 evaluó el baseline:

```text
fa2a027dd7a8f4fd8b142f0cd54b87317d720406
```

El cierre documental histórico corresponde a:

```text
62bc96c17b0e8aeedfdb207b94ecd4e2bea54381
```

La diferencia entre aquel baseline y el HEAD actual es esperada: los seis
incrementos se publicaron después del cierre de BH-062. La cadena comprobada es:

| Etapa | Commit | Mensaje |
|---|---|---|
| Baseline BH-062 | `fa2a027dd7a8f4fd8b142f0cd54b87317d720406` | `test(ui): completar matriz de permisos y regresion BH-062` |
| Cierre histórico | `62bc96c17b0e8aeedfdb207b94ecd4e2bea54381` | `docs(bh-062): registrar cierre tecnico` |
| Incremento 0 | `7de385f818b9c4c54f3d7d0fc892b729e8d7b3e9` | `fix(turnos): asegurar finalizacion transaccional e idempotente` |
| Incremento 1 | `cf7d49a53c7fa0727d3ed0843897c38310cccba6` | `feat(hair): trazar evaluaciones y cambios del perfil capilar` |
| Incremento 2 | `71c080db7d33ed2775efcfb8062492479a794fab` | `feat(technical): completar ciclo trazable de fichas` |
| Incremento 3 | `53cb9fbadf901cbe24d7f535e71bd649c2bf7e1b` | `feat(turnos): consolidar efectos trazables de finalizacion` |
| Incremento 4 | `dbead55051fee50021889ba7dc374db54734e6b4` | `feat(ui): integrar recorrido tecnico profesional` |
| Incremento 5 / HEAD | `2de633ce5d0008ff7ee127fb6aafab27bff83113` | `test(professional): validar compatibilidad con turnos presenciales` |

HEAD, upstream y `origin/save/work-in-progress` coincidieron en `2de633c…` al
iniciar esta auditoría. `documentacion/BH-062/AUDITORIA_CIERRE_BH062.md` no tiene
diferencias desde `62bc96c…`; conserva 9 `CUMPLE`, 3 `CUMPLE PARCIAL`, 0 `NO
CUMPLE` y 0 `NO VERIFICADO`. Este informe no modifica ese resultado histórico.

## 2. Metodología

La validación no tomó los informes de implementación como prueba suficiente.
Se realizaron cuatro actividades independientes:

1. comparación de la cadena Git, documentos y archivos implementados;
2. inspección estática de modelos, constraints, servicios de dominio,
   serializers, permisos, views, rutas, sesión y pantalla React;
3. contraste de cada afirmación de los documentos 0–5 con implementación y
   pruebas concretas;
4. ejecución nueva sobre PostgreSQL de focales y matriz B1–B7, más frontend,
   build, checks y migraciones.

Las bases de prueba de esta auditoría usaron nombres nuevos
`test_bohemia_hair_audit_*`. Las 152 focales backend son repeticiones dirigidas y
no se suman a las 1.203 pruebas únicas de B1–B7.

## 3. Matriz de incrementos

| Incremento | Contrato auditado | Evidencia principal | Resultado |
|---:|---|---|---|
| 0 | Finalización única, atómica, idempotente y con ownership | `turno_finalization_services.py`, `FinalizacionTurno`, rollback y carrera PostgreSQL | **CUMPLE** |
| 1 | Evaluaciones, correcciones y procedencia del perfil | `hair_profile_services.py`, `CambioPerfilCapilar`, `VigenciaCampoPerfilCapilar` | **CUMPLE** |
| 2 | Ficha por `DetalleTurno`, políticas y versión optimista | `technical_record_services.py`, `FichaTecnica`, `PerfilTecnicoServicio` | **CUMPLE** |
| 3 | Ledger causal e idempotente de automatizaciones | `finalization_effect_services.py`, `EfectoFinalizacion`, snapshots | **CUMPLE** |
| 4 | Recorrido React profesional integrado | ruta, contexto, API semántica, preflight, sesión y tests React | **CUMPLE con límites no bloqueantes** |
| 5 | Compatibilidad contractual presencial, sin implementar BH-063/BH-064 | 18 escenarios reales y contratos existentes/futuros separados | **CUMPLE** |

No se encontraron afirmaciones de implementación que simulen BH-063 o BH-064
como concluidos.

## 4. Evidencia de código y modelo

### 4.1 Finalización y efectos

`FinalizacionTurno` tiene relación `OneToOne` con `Turno`, UUID e
`idempotency_key` únicos, fingerprint de comando y resultado persistido. El
modelo impide actualización y eliminación ordinarias.

`EfectoFinalizacion` conserva causa, tipo, estado, clave lógica, referencias al
Detalle/Servicio/regla/Rutina/configuración, snapshot y resultado. La constraint
`unique_finalization_effect_logical_key` impide repetir una clave dentro de la
misma finalización. También es inmutable por contrato de modelo.

`finalize_turno()`:

- usa `@transaction.atomic`;
- exige cuenta activa, permiso Django efectivo, Personal activo y ownership;
- bloquea `Turno`, resultado existente, detalles, fichas y configuración
  derivada mediante `select_for_update()`;
- sólo admite `CONFIRMADO -> REALIZADO`;
- valida fichas obligatorias antes de cambiar estado;
- crea y sella un único resultado, auditoría y ledger dentro de la transacción;
- devuelve el resultado persistido para el mismo comando idempotente;
- responde conflicto para otra clave, otro Turno o transición incompatible.

### 4.2 Perfil y evaluaciones

`DiagnosticoCapilar` conserva historia, autor, profesional, procedencia, campos
realmente evaluados, observaciones y resultado calculado separado.
`CambioPerfilCapilar` registra actor, motivo, operación, procedencia y valores
antes/después. `VigenciaCampoPerfilCapilar` tiene unicidad por Cliente/campo y
explica la fuente vigente de cada dimensión.

Una evaluación nueva crea historia y promueve sólo campos explícitos. Una
corrección exige motivo, conserva el evento original, invalida derivados sin
recalcularlos y sólo actualiza el perfil si la evaluación corregida sigue siendo
la fuente vigente. Los escritores bloquean el Cliente, evitando pérdida de
actualizaciones parciales concurrentes.

### 4.3 Fichas técnicas

`FichaTecnica.detalle_turno` es `OneToOne`: un Turno multiservicio mantiene una
ficha por Servicio reservado. Los estados son `BORRADOR` y `COMPLETA`; cada
mutación semántica usa versión esperada. Las correcciones guardan actor, motivo,
campos, antes/después y versiones anterior/nueva.

La política no se infiere por nombre comercial. `PerfilTecnicoServicio` define
si la ficha es requerida, el modo de fórmula y los campos obligatorios. Una
política pendiente no inventa requisitos. La finalización bloquea sólo cuando
una política explícita `REQUERIDA` no tiene ficha completa.

## 5. Pruebas ejecutadas

### 5.1 Resultados independientes

| Ejecución | Resultado | Clasificación |
|---|---:|---|
| Focal 0–5, riesgo y creación de Turno | 152/152 | repetición dirigida |
| B1 — roles, usuarios y Personal | 416/416 | matriz única |
| B2 — diagnóstico, ficha y rutinas | 216/216 | matriz única |
| B3 — agenda, Turnos y flujos profesionales | 210/210 | matriz única |
| B4 — catálogos, inventario y órdenes | 79/79 | matriz única |
| B5 — Caja, pagos e incidencias | 170/170 | matriz única |
| B6 — Django Admin y auditoría | 43/43 | matriz única |
| B7 — concurrencia PostgreSQL | 69/69 | matriz única |
| **Total B1–B7** | **1.203/1.203** | **pruebas backend únicas** |
| Frontend completo | 438/438, 46 suites | pruebas frontend únicas |
| Build React | aprobado | warnings no bloqueantes |
| `manage.py check` | aprobado | 0 incidencias |
| `makemigrations --check --dry-run` | aprobado | sin cambios |

No hubo fallos funcionales. La suite React emitió logs esperados de errores
simulados y avisos `act(...)` en pruebas de `Operaciones`/acciones semánticas. El
build conserva warnings de lint y tamaño en archivos legacy no modificados por
los incrementos. Son deuda de calidad, no evidencia de fallo del recorrido.

### 5.2 Evidencia negativa y concurrencia

Las pruebas ejecutadas incluyen:

- 401 de sesión, 403 de capability/ownership y 409 de estado, clave o versión;
- dos finalizaciones concurrentes con un resultado y un ledger único;
- dos escritores concurrentes del perfil sin perder campos parciales;
- dos escritores de ficha con un ganador y un 409 para la versión obsoleta;
- rollback forzado sin Turno realizado, finalización, ledger o notificación
  residual;
- reintento global e invocación repetida de handlers sin duplicar salidas;
- guardado posterior del Turno realizado sin reprocesamiento.

## 6. Seguridad y permisos

La autorización efectiva se compone con permisos Django, cuenta activa,
Personal activo y habilidad `DIAGNOSTICO` cuando corresponde. No se encontraron
decisiones en los servicios auditados basadas en `BusinessRole`, `is_staff` o
`is_superuser`.

El ownership se revalida en backend:

- finalización: Personal asignado al Turno;
- ficha: Turno y `DetalleTurno` asignados;
- contexto: Cliente propietario o Personal asignado con lectura técnica;
- corrección de evaluación: autor profesional o alcance global efectivo.

La ruta React exige perfil Personal activo y
`technical_record.read_global`; el backend no confía en esa guarda y vuelve a
validar el ID. Una URL directa sin capability no monta ni consulta la pantalla.
Una revocación 403 actualiza `SessionContext`, retira acciones y no reenvía la
mutación. La lectura sin escritura mantiene el contexto pero no presenta
botones mutantes.

Las fórmulas aplicada, estándar y sus correcciones se eliminan de la
serialización sin `service_formula.manage`. El contexto también excluye email,
autor, reglas internas y snapshots no necesarios. `effects.summary` no expone
fórmulas, textos de reglas ni `parametros_snapshot`; la UI tampoco representa
claves lógicas.

## 7. Integridad transaccional

La transición, ficha, snapshot, automatizaciones, perfil, auditoría y resultado
quedan bajo la misma transacción PostgreSQL. Los locks siguen un orden estable.
Los outputs actuales son sólo escrituras DB; no hay proveedor externo que
requiera outbox en este flujo.

Se comprobó:

- `CONFIRMADO -> REALIZADO` y rechazo del resto de estados;
- revalidación de actor asignado después del lock;
- retry con misma identidad y rechazo de identidades incompatibles;
- rollback total ante una falla crítica;
- una finalización por Turno y una clave por comando;
- impactos nulos sin borrar perfil;
- multiservicio sin prioridad global inventada;
- ficha obligatoria sólo por política explícita.

## 8. Trazabilidad del perfil

La historia no se reemplaza por el snapshot vigente. Evaluación, autorreporte,
corrección e impacto automático tienen procedencias distintas. Los valores
legacy sin evidencia se informan como `DESCONOCIDO` y no reciben metadatos
ficticios.

Los datos parciales no borran campos omitidos. Las observaciones profesionales
se conservan separadas del resultado calculado. Una corrección no crea una nueva
observación ni duplica rutinas/notificaciones; registra actor, motivo y
antes/después. La finalización nunca crea un `DiagnosticoCapilar` automático.

## 9. Fichas y automatizaciones

La ficha conserva borrador, completitud, versión, autor y correcciones. No se
admite `PUT/PATCH/DELETE` genérico. La fórmula estándar es sólo referencia; la
aplicada es un dato distinto y protegido.

`finalization_effect_services.py` es el productor post-servicio único. Cada
efecto tiene identidad lógica persistente y snapshot de los parámetros usados.
Los handlers consultan el ledger antes de producir. El resumen público informa
tipo, estado y resultado acotado.

`inspect_effect_ledger()` permite detectar ledger o salidas faltantes sin
releer reglas, reejecutar efectos ni modificar perfil. Rutinas compartidas se
reutilizan; cuidados, notificaciones y retoques no se duplican. El diagnóstico
automático queda `OMITIDO`. Un impacto capilar sólo se aplica para un Servicio y
valores no nulos configurados; no se presenta como evaluación de salud.

## 10. UI profesional

El recorrido productivo está publicado en:

```text
/turnos/:turnoId/trabajo-tecnico
```

Se enlaza desde Mi agenda laboral y Operaciones sólo para el Personal asignado
que posee la capability de lectura. La pantalla integra:

1. Turno y perfil vigente con procedencia por campo;
2. evaluación parcial o corrección trazable;
3. ficha independiente por Detalle/Servicio;
4. preflight de transición, autoridad y fichas;
5. confirmación explícita con una clave estable en `sessionStorage`;
6. retry manual con la misma clave sólo ante resultado incierto;
7. estado final y resumen seguro de efectos.

Los casos React cubren acceso directo, Turno ajeno, perfil incompleto,
revocación, sólo lectura, multiservicio, fórmulas, conflicto 409, doble clic,
timeout, 401/403, resultado persistido y no filtración.

## 11. Compatibilidad con BH-063 y BH-064

La compatibilidad es contractual, no una declaración de implementación.

- Un Cliente puede existir sin diagnóstico y con los cinco campos capilares
  nulos. El contexto carga y no inventa una evaluación.
- La necesidad de evaluación depende de reglas publicadas del Servicio.
- La ficha depende de `PerfilTecnicoServicio`, no de un diagnóstico universal.
- La creación actual para Cliente valida disponibilidad y fija canal
  `PRESENCIAL`, pero deja el Turno en `SOLICITADO`.
- BH-063 deberá orquestar el evaluador moderno y definir una transición auditada
  hasta `CONFIRMADO`.
- BH-064 deberá decidir el alta rápida y devolver como mínimo la identidad de
  Cliente necesaria para BH-063, sin fabricar perfil.

No se verificó una operación productiva completa de BH-063/BH-064 porque no
existe y no debía simularse.

## 12. Reevaluación actual de los criterios 5, 7 y 11 de BH-062

La clasificación siguiente corresponde exclusivamente al HEAD `2de633c…`. No
reemplaza ni edita la clasificación histórica.

### Criterio 5

> “cada pantalla parcial separa lectura, creación, edición, eliminación/desactivación y acciones especiales”

**Faltaba originalmente:** diagnóstico, fichas y finalización tenían autoridad
backend, pero no pantalla React productiva para comprobar la separación de
operaciones.

**Implementado después:** la pantalla profesional separa lectura de perfil e
historia; nueva evaluación de corrección; crear/guardar/completar/corregir ficha;
y preflight/confirmación/finalización. No ofrece eliminación, edición genérica ni
acciones fuera de política.

**Evidencia actual:** ruta productiva, comandos semánticos, flags efectivos,
ownership backend y tests positivos/negativos React y API.

**Clasificación actual:** **CUMPLE**.

**Límite residual:** no existe corrección posfinalización; se rechaza de forma
explícita hasta aprobar esa política.

### Criterio 7

> “condiciones técnicas no cumplidas se detectan antes de ofrecer la acción y se explican sin revelar detalles administrativos”

**Faltaba originalmente:** no existía UI productiva que anticipara skill/estado
para diagnóstico, ficha o finalización.

**Implementado después:** `ProtectedRoute`, capabilities, flags del contexto,
restricciones por ficha/estado, errores de completitud y preflight impiden
presentar la confirmación cuando existe un bloqueo. Fórmula requerida sin
capability, políticas pendientes y fichas incompletas tienen mensajes seguros.

**Evidencia actual:** tests de URL directa, revocación, sólo lectura, fórmula,
preflight, 401/403/409 y ausencia de datos sensibles.

**Clasificación actual:** **CUMPLE PARCIAL**.

**Límites residuales:** la pantalla no proyecta todavía evidencia del evaluador
moderno de riesgo técnico. Además, cuando la ficha queda sólo lectura por falta
de capability, el texto genérico puede atribuirlo al estado del Turno en lugar
de explicar con precisión la causa. La operación falla cerrada y el backend no
filtra datos, por lo que no es un bloqueante de seguridad, pero la explicación
anticipada aún no es completa.

### Criterio 11

> “las pruebas cubren rol, grupo técnico, permiso individual, lectura sin escritura, capacidades compuestas, revocación en sesión y no filtración”

**Faltaba originalmente:** no había prueba React integrada de diagnóstico,
fichas y finalización porque esos flujos no estaban publicados.

**Implementado después:** `TrabajoTecnicoTurno.test.js`, pruebas de agenda,
Operaciones, ruta, API profesional, identidad idempotente y sesión cubren el
recorrido publicado. Las suites backend cubren permisos individuales/grupos,
capabilities, ownership, revocación, fórmulas y concurrencia.

**Evidencia actual:** 438/438 frontend, 1.203/1.203 backend únicos y 152/152
focales repetidas.

**Clasificación actual:** **CUMPLE**.

**Límite residual:** no se ejecutó navegador E2E/Cypress; la cobertura actual es
de componentes/integración React y API PostgreSQL. Este límite no invalida las
categorías exigidas por el criterio.

## 13. Hallazgos, severidad y riesgos

### 13.1 Bloqueantes

No se encontraron hallazgos críticos o altos que impidan el cierre técnico de
los Incrementos 0–5.

### 13.2 No bloqueantes

| ID | Severidad | Hallazgo / riesgo | Tratamiento |
|---|---|---|---|
| R-01 | Media | Registrar llegada produce `EN_PROCESO`; la ficha admite ese estado, pero la finalización sólo admite `CONFIRMADO`. | Decisión funcional pendiente; no ampliar la transición sin política aprobada. |
| R-02 | Media futura | El Turno asistido actual queda `SOLICITADO` y su creación no orquesta por sí sola el evaluador moderno. | Resolver en BH-063; no se presenta como implementado. |
| R-03 | Baja | La UI no muestra evidencia de riesgo técnico y una causa de sólo lectura puede explicarse de forma genérica. | Mejora de transparencia; mantiene fail-closed. |
| R-04 | Baja | No hay política global de impactos capilares multiservicio. | Se preserva el perfil y se registra `MULTISERVICE_POLICY_PENDING`. |
| R-05 | Baja | No existe reparación automática de ledger/salidas eliminadas manualmente. | La reconciliación detecta; futura compensación requiere política. |
| R-06 | Baja | Perfiles y resultados previos a los ledgers quedan como históricos/legacy sin evidencia inventada. | Mantener trazabilidad prospectiva. |
| R-07 | Calidad | Warnings React/lint y ausencia de navegador E2E. | Mejora futura de tests; suites actuales pasan completas. |

Las políticas operativas de clasificación de Servicios, corrección
posfinalización, autoevaluaciones periódicas, pago presencial e idempotencia de
alta/Turno asistido permanecen fuera del alcance y no deben incorporarse al
cierre como si estuvieran implementadas.

## 14. Veredicto y recomendación

Los seis incrementos cumplen sus contratos publicados y mantienen seguridad,
atomicidad, trazabilidad y compatibilidad. No hay bloqueantes. Las pruebas
independientes reproducen los resultados esperados sin depender de los reportes
anteriores.

La reevaluación actual deja:

- criterio 5: **CUMPLE**;
- criterio 7: **CUMPLE PARCIAL**;
- criterio 11: **CUMPLE**.

Esto no altera el resultado histórico de BH-062. Se recomienda registrar un
cierre complementario de los Incrementos 0–5, conservando R-01 a R-07 como
riesgos/deuda futura y sin iniciar BH-063 o BH-064 desde este informe.

**FLUJOS PROFESIONALES 0–5 = LISTOS PARA CIERRE TÉCNICO**
