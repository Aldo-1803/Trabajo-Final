# Análisis técnico-funcional de flujos profesionales y perfil capilar

**Fecha:** 2026-11-11

**Baseline analizado:** `62bc96c17b0e8aeedfdb207b94ecd4e2bea54381`

**Tipo de entrega:** análisis transversal posterior a BH-062; no reabre su cierre

**Estado:** propuesta para decisión; no modifica implementación

## 1. Resultado ejecutivo

El sistema ya posee piezas backend para perfil capilar, diagnósticos, fichas
técnicas y finalización, pero todavía no forman un único recorrido profesional
seguro y publicable.

Los hallazgos principales son:

1. `Cliente` conserva un **perfil actual mutable**, mientras
   `DiagnosticoCapilar` conserva **evaluaciones históricas**. Hoy ambas fuentes
   pueden divergir y no existe una política funcional que determine cómo se
   sincronizan.
2. La necesidad de diagnóstico depende de las reglas técnicas del Servicio. No
   corresponde exigir diagnóstico para toda alta, todo Turno ni toda atención,
   ni crear uno nuevo obligatoriamente en cada visita.
3. `FichaTecnica` representa el resultado de un `DetalleTurno`, por lo que un
   Turno multiservicio puede tener una ficha por Servicio. Su backend tiene
   ownership útil, pero no define completitud por tipo de Servicio, ventana de
   edición ni trazabilidad histórica de cambios.
4. La finalización es el riesgo inmediato: cambia cualquier estado no realizado
   a `REALIZADO`, no comprueba actor asignado, ficha, pago o stock y ejecuta
   efectos duplicados desde la vista y tres señales sin atomicidad ni
   idempotencia integral.
5. No hay UI React productiva para diagnóstico profesional, ficha técnica o
   finalización. Los componentes legacy de ficha no deben publicarse
   directamente.

La prioridad recomendada es **contener y endurecer la finalización antes de
publicar UI**. Luego deben separarse la corrección del perfil actual, una nueva
evaluación profesional y el resultado post-servicio, preservando siempre la
historia.

## 2. Alcance y método de clasificación

Este documento integra:

- perfil capilar actual de `Cliente`;
- evaluaciones históricas `DiagnosticoCapilar`;
- ficha técnica por Servicio atendido;
- transición de Turno a `REALIZADO`;
- rutinas, cuidados, notificaciones, promociones y mutaciones de perfil
  asociadas;
- contratos API, permisos efectivos, React y pruebas;
- interfaces futuras con BH-063 y BH-064.

Cada afirmación funcional se clasifica en una de estas categorías:

| Categoría | Significado |
|---|---|
| **[ORIGINAL]** | Requisito encontrado en UC-05, UC-11, UC-17 o sus diagramas históricos. Es evidencia de intención, no de comportamiento actual. |
| **[IMPLEMENTADO]** | Comportamiento comprobado en modelos, servicios, APIs, permisos, React o tests del baseline. |
| **[HIPÓTESIS]** | Necesidad nueva planteada para completar el recorrido; aún no es contrato aprobado. |
| **[DECISIÓN ABIERTA]** | Política de negocio que el propietario debe resolver antes de implementarla. |

No se consideran requisitos automáticos las frases presentes sólo en
comentarios de código o documentos históricos si contradicen el contrato real.

## 3. Separación conceptual obligatoria

| Concepto | Fuente actual | Semántica correcta |
|---|---|---|
| Perfil capilar vigente | cinco FK mutables en `Cliente` | Resumen actual para experiencia de usuario; puede estar incompleto y no prueba quién evaluó. |
| Evaluación capilar | `DiagnosticoCapilar` | Hecho histórico con fecha, procedencia y autor; no debe sobrescribirse para representar una evaluación nueva. |
| Historial técnico de una atención | `FichaTecnica` ligada 1:1 a `DetalleTurno` | Evidencia del proceso y resultado de un Servicio concreto. |
| Resultado automático | diagnóstico, rutina, cuidado, notificación o promoción generados por reglas | Efecto derivado que debe indicar origen, versión/regla y evento causante. No equivale por sí solo a observación profesional. |

Dos operaciones no deben confundirse:

- **corregir un dato**: corrige un error material y debe auditar antes/después,
  actor y motivo;
- **registrar una evaluación nueva**: crea un hecho histórico nuevo, con fecha,
  autor y procedencia.

Mutar silenciosamente el perfil actual o editar el diagnóstico anterior no
resuelve ambas necesidades.

## 4. Requisitos originales y límites de interpretación

### 4.1 UC-05 — guía de diagnóstico capilar

**[ORIGINAL]** UC-05 describe un cuestionario autenticado sobre tipo, grosor,
porosidad y estado, seguido por un resultado de perfil, recomendaciones de
cuidados y productos. Su actor es el Cliente; no define una evaluación
profesional ni obliga a repetirla por atención.

**[IMPLEMENTADO]** El registro público puede recibir esos datos y crear un
diagnóstico de procedencia `AUTORREPORTE`, pero no existe el cuestionario
independiente completo descrito por UC-05.

### 4.2 UC-11 — rutina inicial automática

**[ORIGINAL]** UC-11 busca asignar una primera rutina a partir del diagnóstico.
El texto contiene una inconsistencia: habla de la primera rutina, pero declara
como precondición que el Cliente ya tiene al menos una rutina. Esta
contradicción no debe trasladarse a código sin decisión.

**[IMPLEMENTADO]** El motor de diagnóstico puede seleccionar una rutina por
regla o puntuación y crear una copia para el Cliente. El helper de asignación es
transaccional, bloquea al Cliente y puede devolver una copia existente.

### 4.3 UC-17 — historial técnico profesional

**[ORIGINAL]** UC-17 une en una sola acción:

1. elegir un Turno “Aceptado”;
2. recuperar fórmula estándar y diagnóstico base;
3. ajustar fórmula, registrar estado final, notas y foto;
4. guardar la ficha y finalizar el Turno;
5. actualizar el “último diagnóstico” del perfil;
6. permitir editar la fórmula hasta 24 horas después de finalizar.

También diferencia Servicios químicos de no químicos: para un Corte no deben
mostrarse campos químicos y, si falta fórmula base en un Servicio químico, se
parte de un formulario vacío.

**[IMPLEMENTADO]** La ficha y la finalización son endpoints separados; no hay
ventana de 24 horas, clasificación de campos obligatorios por Servicio ni una
transacción que guarde ficha y finalización como una sola operación.

**Límite:** “actualizar el último diagnóstico” no autoriza a sobrescribir
historia ni determina si debe actualizarse `Cliente`, crearse una evaluación o
registrarse sólo el resultado en la ficha.

## 5. Modelo y persistencia reales

### 5.1 Perfil actual de `Cliente`

**[IMPLEMENTADO]** `Cliente` guarda `tipo_cabello`, `grosor_cabello`,
`porosidad_cabello`, `cuero_cabelludo` y `estado_general` como FK opcionales.
No usa `HistoricalRecords` ni conserva procedencia, fecha de observación o actor
por cada cambio.

Consecuencias:

- representa un snapshot, no una línea temporal;
- un `PUT /api/usuarios/perfil/` puede cambiarlo sin crear diagnóstico;
- una señal post-servicio también puede cambiar parte del snapshot;
- una evaluación profesional nueva no lo actualiza;
- no es posible explicar de forma uniforme por qué el valor actual difiere del
  último diagnóstico.

### 5.2 `DiagnosticoCapilar`

**[IMPLEMENTADO]** Es histórico, permite datos parciales y registra fecha,
procedencia (`PROFESIONAL`, `AUTORREPORTE`, `POST_SERVICIO_AUTOMATICO`,
`MIGRADO`, `DESCONOCIDO`) y profesional opcional. Usa `HistoricalRecords`.

El motor puede:

- asociar regla, rutina y Servicio urgente;
- reemplazar `observaciones` por un mensaje calculado;
- asignar una rutina;
- crear un Turno `SUGERIDO` y notificación si encuentra un Servicio urgente.

El motor corre al crear desde el ViewSet, pero no al actualizar un diagnóstico.
Por tanto, un `PATCH` puede dejar resultados derivados desalineados con las
entradas. Además, el texto profesional enviado en `observaciones` puede perderse
al crear por la sobrescritura del motor.

### 5.3 `FichaTecnica`

**[IMPLEMENTADO]** Tiene relación `OneToOne` con `DetalleTurno`; esto soporta
correctamente una ficha por Servicio en Turnos multiservicio. Incluye fórmula,
observaciones, comentario, rutina, porosidad/estado finales, resultado y foto.
Casi todos son opcionales y el modelo no usa `HistoricalRecords`.

El serializer:

- fija el autor desde el request;
- exige que el actor sea el Personal activo asignado al Turno;
- exige permiso adicional para modificar `formula`;
- acepta sólo estado `CONFIRMADO` o `EN_PROCESO`;
- impide cambiar el `DetalleTurno` y duplicar su ficha.

`Turno.Estado` declara ambos estados. La ficha no puede editarse después de que
el Turno queda `REALIZADO`, en contradicción con las 24 horas de UC-17.

### 5.4 Turno y ausencia de evento de finalización

**[IMPLEMENTADO]** El Turno sólo conserva `estado=realizado`; no existe una
entidad persistida que identifique el evento de finalización, actor, instante,
estado origen, versión de reglas ni estado de cada efecto. Sin esa identidad no
hay clave natural para idempotencia y reanudación.

## 6. Recorridos actuales de punta a punta

### 6.1 Registro público y edición del perfil

1. **[IMPLEMENTADO]** Backend acepta los cinco datos capilares como opcionales.
2. Si llega al menos uno, crea `DiagnosticoCapilar(AUTORREPORTE)` con el
   snapshot recibido.
3. React obliga a completar los cinco en el paso 2, por lo que UI y API tienen
   políticas distintas.
4. `GET /api/usuarios/perfil/` devuelve nombres amigables de catálogos, pero
   `EditarPerfil.js` intenta cargarlos como valores de selects cuyos valores son
   IDs.
5. `PUT /api/usuarios/perfil/` actualiza directamente `Cliente`; no crea una
   evaluación ni auditoría semántica.

### 6.2 Alta presencial y creación de Turno

1. **[IMPLEMENTADO]** El alta administrativa crea atómicamente
   `Usuario + Cliente + rol CLIENTE`, sin exigir perfil capilar ni diagnóstico.
2. `TurnoCreationService.create` tampoco exige los cinco datos ni un diagnóstico
   universal.
3. El riesgo técnico previo evalúa reglas configuradas por Servicio. Una regla
   puede requerir diagnóstico y distinguir ausencia, incompletitud, antigüedad o
   procedencia no confiable.

**Conclusión:** no debe añadirse una barrera global de diagnóstico al alta o al
Turno. La decisión corresponde al evaluador de riesgo y a la política publicada
del Servicio.

### 6.3 Diagnóstico profesional

1. **[IMPLEMENTADO]** El profesional crea o edita por
   `/api/gestion/diagnosticos-capilares/`.
2. Backend fija `profesional=request.user` y procedencia profesional al crear.
3. Se ejecuta el motor de diagnóstico y sus efectos derivados.
4. El perfil actual de `Cliente` no se sincroniza.
5. No existe UI React profesional productiva.

### 6.4 Ficha técnica

1. **[IMPLEMENTADO]** El Personal asignado puede crear/editar una ficha por
   `DetalleTurno` mientras el Turno esté `confirmado` (o en el literal legacy
   `en_proceso`).
2. Fórmula requiere una capacidad adicional.
3. DELETE devuelve 405 y preserva la ficha.
4. No se exige una ficha para finalizar ni campos mínimos según el Servicio.
5. No hay UI productiva conectada al recorrido de agenda.

### 6.5 Finalización actual

`POST /api/gestion/turnos/{id}/finalizar_turno/` realiza, en este orden lógico:

1. carga el Turno mediante el queryset visible;
2. rechaza sólo si ya está `REALIZADO`;
3. guarda `estado=REALIZADO`;
4. el `save()` dispara síncronamente tres señales;
5. crea, si hay algún dato capilar, un diagnóstico automático desde el snapshot
   y ejecuta el motor;
6. crea notificaciones por reglas y asigna sus rutinas;
7. crea promociones de retoque;
8. responde éxito.

No existe `transaction.atomic()`, `select_for_update()`, clave de idempotencia ni
registro de finalización. Una excepción después del paso 3 deja el Turno
realizado y efectos parciales; el reintento queda bloqueado y no repara lo
faltante.

## 7. Permisos y ownership efectivos

| Operación | Autoridad actual | Ownership/alcance |
|---|---|---|
| Crear diagnóstico | capability `diagnosis.create`: permiso `create_diagnosis` + cuenta, Personal y habilidad `DIAGNOSTICO` activos | Autor fijado por servidor. Sin gestión técnica global, sólo diagnósticos propios. |
| Leer diagnóstico | Cliente propio o capability `technical_record.read_global` | La lectura global usa `manage_technical_record` + habilidad activa. |
| Crear/editar ficha | capability `technical_record.manage` | Sólo Personal activo asignado al Turno; fórmula requiere `manage_formulas`. |
| Leer ficha | Cliente propio o capacidad técnica | Para Personal, el queryset sigue limitado a fichas que redactó o Turnos que tiene asignados. |
| Finalizar | `finalize_service` y, por la configuración actual de la acción, también capacidad efectiva de diagnóstico | No valida que el actor sea el Personal asignado. |

Reglas de diseño que deben conservarse:

- no usar `BusinessRole` ni `is_staff` como autoridad;
- no reconstruir en React una autorización que sólo backend puede decidir;
- no ampliar `technical_record.read_global` ni el queryset de fichas como efecto
  lateral de publicar la UI;
- responder por capacidades efectivas, perfil activo y ownership;
- distinguir 403 de autorización, 409 de transición/conflicto y 400 de datos.

La dependencia actual entre finalizar y `diagnosis.create` es accidental: un
Turno sin datos capilares no crea diagnóstico, pero el actor igualmente necesita
esa capacidad. Debe desacoplarse si el diagnóstico automático pasa a ser un
efecto opcional.

## 8. Matriz de estados y transiciones

### 8.1 Comportamiento real

| Estado origen | Crear/editar ficha | Finalizar hoy | Problema |
|---|---:|---:|---|
| `SOLICITADO` | No | Sí | Puede saltar análisis, seña y confirmación. |
| `ESPERANDO_SENA` | No | Sí | Puede finalizar con seña pendiente. |
| `CONFIRMADO` | Sí | Sí | Único origen operativo coherente hoy. |
| `SUGERIDO` | No | Sí | Una sugerencia puede marcarse realizada sin reserva confirmada. |
| `CANCELADO` | No | Sí | Reactiva semánticamente una cancelación como realizada. |
| `AUSENTE` | No | Sí | Convierte una inasistencia en atención realizada. |
| `REALIZADO` | No | Rechaza con 400 | No es retry idempotente ni permite completar efectos parciales. |
| `EN_PROCESO` | Sí | Sí | Existe en el modelo, pero el Incremento 0 lo excluye provisionalmente como origen válido. |

### 8.2 Política objetivo recomendada

**[HIPÓTESIS recomendada]** Aunque `EN_PROCESO` ya existe en el modelo, la
transición provisional del Incremento 0 debe ser sólo
`CONFIRMADO -> REALIZADO`, bajo lock. La posible ampliación a
`EN_PROCESO -> REALIZADO` requiere una decisión funcional posterior.

**[DECISIÓN ABIERTA]** Definir si registrar llegada es suficiente para iniciar
un Servicio o si debe existir un estado `EN_PROCESO` con actor e instante.

Un reintento de la misma finalización debe devolver el resultado persistido sin
duplicar efectos; una finalización distinta o incompatible debe responder 409.

## 9. Automatizaciones y garantías actuales

| Efecto | Productor actual | Idempotencia/atomicidad | Riesgo |
|---|---|---|---|
| Agenda de cuidados | primera señal y tercera señal | Sin unicidad por Turno/regla | Duplicados incluso en una misma finalización. |
| Notificación “Servicio finalizado” | segunda señal | Sin unicidad | Se repite en cualquier guardado posterior del Turno realizado. |
| Mutación del perfil | tercera señal | No registra causa ni valores previos | En multiservicio gana el último recorrido. |
| Estado general | tercera señal | Asigna incluso cuando `impacto_estado` es `None` por indentación | Puede borrar el estado vigente. |
| Rutina de Servicio | tercera señal | Helper interno con lock y retorno del existente | Es el efecto mejor contenido, aunque no identifica el evento causante. |
| Diagnóstico post-servicio | vista | Sin unicidad por Turno/finalización | Concurrencia puede crear varios. |
| Motor de diagnóstico | vista/ViewSet | No envuelve todos sus efectos con la finalización | Puede dejar diagnóstico y derivados parciales. |
| Cuidados/notificaciones por regla | vista | Sin unicidad | Se superponen con señales. |
| Promoción de retoque | vista | Sin unicidad por Turno/Servicio | Reintentos/concurrencia duplican promociones. |

Las señales verifican solamente `instance.estado == 'realizado'`, no una
transición real. Por eso cualquier `save()` futuro del Turno vuelve a ejecutar
los tres receptores.

No son efectos directos de finalizar:

- recomendaciones de productos, que se calculan bajo demanda;
- contenido educativo, consultado por endpoints de contenido;
- pago/saldo, que no se registra ni liquida aquí;
- stock, que no se consume ni reserva aquí.

## 10. Atomicidad, concurrencia e idempotencia

### 10.1 Fallos reproducibles por diseño

1. Dos requests pueden leer simultáneamente un Turno no realizado.
2. Ambos pueden guardarlo como realizado y disparar señales.
3. Ambos pueden crear diagnóstico, agendas, notificaciones y promociones.
4. Si una creación posterior falla, el estado ya quedó realizado.
5. El retry encuentra `REALIZADO`, devuelve error y no completa los efectos
   faltantes.

`transaction.atomic()` sólo dentro de la creación de ficha o del helper de
rutina no protege la unidad completa.

### 10.2 Garantía objetivo mínima

La finalización debe tener una única autoridad de dominio que:

- valide permiso efectivo y ownership;
- bloquee el Turno con `select_for_update()`;
- valide estado origen;
- capture un evento/resultado de finalización único por Turno;
- persista estado, ficha requerida y efectos críticos en una transacción;
- use constraints o claves únicas por `finalizacion + tipo + regla/Servicio`;
- difiera sólo efectos externos con `transaction.on_commit()` y outbox si
  aparecen proveedores externos;
- devuelva el resultado existente ante el mismo retry;
- permita reconciliar efectos pendientes sin volver a cambiar el estado.

No se recomienda solucionar la transición con una nueva señal. Las señales
actuales deben dejar de ser productoras del flujo de finalización una vez
consolidado el servicio.

## 11. React y publicabilidad

### 11.1 Superficies productivas existentes

- registro público con paso capilar;
- perfil del Cliente y editor de perfil;
- alta administrativa de Cliente;
- creación de Turno para Cliente;
- operaciones del día, agenda laboral y revisión técnica de BH-057.

### 11.2 Ausencias

- formulario profesional de diagnóstico;
- historial profesional integrado del Cliente;
- ficha por cada Detalle del Turno desde la agenda;
- preflight y confirmación de finalización;
- resultado estructurado y manejo de retry/conflicto.

### 11.3 Componentes legacy no publicables directamente

`RegistroFichaTecnica.js`, `VisualizadorFichas.js` y
`fichasTecnicasApi.js` existen, pero:

- no están montados en rutas ni navegación;
- usan un cliente Axios aislado en vez de la configuración común de sesión;
- exponen controles sin gobernarlos por capacidades efectivas;
- ofrecen DELETE aunque backend responde 405;
- asumen contratos de Turno/detalle que no constituyen una vista de trabajo
  profesional estable;
- no manejan revocación, 403, 409 ni estados concurrentes con el patrón vigente.

Deben reutilizarse sólo como referencia visual, no publicarse como están.

## 12. Cobertura de pruebas actual y faltante

### 12.1 Evidencia existente

- autorización de diagnóstico: permiso, habilidad, Personal/cuenta activos,
  autor fijado, lectura propia/global y DELETE 405;
- autorización de ficha/fórmula/rutina: ownership, permiso, habilidad,
  fórmulas y asignación interna;
- capabilities de sesión y paridad DRF;
- evaluador de riesgo: procedencia, completitud, antigüedad y ausencia según
  reglas publicadas;
- registro público opcional con diagnóstico de autorreporte.

### 12.2 Cobertura necesaria

No hay suite dedicada que demuestre:

- transición origen válida y rechazo del resto;
- actor asignado frente a actor con permiso global;
- finalización sin diagnóstico cuando la política no lo exige;
- obligación condicional de ficha y campos por Servicio;
- rollback ante falla en cada efecto;
- dos finalizaciones concurrentes;
- retry del mismo request y conflicto de otro request;
- unicidad de diagnóstico/agendas/notificaciones/promociones;
- guardado posterior de un Turno realizado sin repetir efectos;
- orden determinista de impactos multiservicio;
- no borrar `estado_general` ante impacto nulo;
- ventana y auditoría de corrección de ficha;
- sincronización elegida entre evaluación y perfil;
- UI por capabilities y manejo 400/403/409.

Las pruebas unitarias con mocks del motor no sustituyen pruebas de integración
de la transacción completa.

## 13. Riesgos priorizados

### Críticos

| Riesgo | Impacto |
|---|---|
| Finalización no atómica ni idempotente | Estado realizado con historial y automatizaciones parciales o duplicadas. |
| Transición desde cualquier estado | Atención ficticia, cancelación/ausencia convertida en realizada. |
| Señales reejecutadas en cada guardado | Duplicación silenciosa y difícil de reconciliar. |

### Altos

| Riesgo | Impacto |
|---|---|
| Sin ownership al finalizar | Un profesional capaz puede finalizar un Turno ajeno. |
| Perfil actual sin procedencia ni auditoría | No se puede justificar qué valor es vigente ni quién lo cambió. |
| Bug de `impacto_estado=None` | Pérdida de estado capilar actual. |
| Multiservicio “último gana” | Resultado depende del orden de consulta, no de una política. |
| Ficha sin historial ni política de completitud | Resultado clínico/técnico débil y correcciones no trazables. |

### Medios

| Riesgo | Impacto |
|---|---|
| Motor sobrescribe observaciones | Se pierde texto profesional al crear. |
| Editar diagnóstico no recalcula derivados | Datos y recomendaciones quedan inconsistentes. |
| GET de perfil devuelve nombres y editor espera IDs | Selects no reflejan de forma fiable el estado guardado. |
| API de registro opcional y UI obligatoria | Canales aplican reglas funcionales diferentes. |
| Promociones usan fecha local de ejecución | Un cierre tardío/reprocesado no queda anclado inequívocamente a la atención. |

### De producto

- obligar diagnóstico universal introduciría fricción y contradiría BH-057;
- usar ficha como diagnóstico mezclaría proceso realizado con evaluación;
- actualizar silenciosamente el último diagnóstico destruiría semántica
  histórica;
- publicar legacy antes de contener backend expondría fallos actualmente
  inaccesibles desde React.

## 14. Decisiones funcionales

### 14.1 Recomendaciones que pueden adoptarse como base

1. Diagnóstico no obligatorio universalmente; lo decide la política técnica por
   Servicio.
2. No exigir diagnóstico nuevo por atención.
3. Una ficha por `DetalleTurno`, no una ficha única por Turno.
4. Preservar diagnósticos y fichas; no DELETE físico.
5. Separar corrección de dato de evaluación nueva.
6. Usar permisos efectivos, estado de perfiles, habilidad y ownership; no roles
   nominales ni `is_staff`.
7. Mantener sin ampliación el alcance de `technical_record.read_global`.
8. Finalización como servicio de dominio único, no como colección de señales.

### 14.2 Decisiones abiertas para el propietario

| ID | Decisión | Recomendación provisional |
|---|---|---|
| D1 | ¿Una evaluación profesional actualiza automáticamente el perfil actual? | Sí, sólo mediante política explícita y auditada; conservar siempre la evaluación. |
| D2 | ¿Qué procedencias pueden convertirse en “perfil vigente”? | Profesional por defecto; autorreporte sólo como declarado por Cliente; automático debe identificarse como derivado. |
| D3 | ¿El resultado post-servicio es diagnóstico, ficha o ambos? | Ficha como evidencia; crear diagnóstico sólo si se registró una evaluación capilar suficiente, no por toda atención. |
| D4 | ¿Qué Servicios requieren ficha para finalizar? | Configuración explícita por Servicio/perfil técnico; no todos. |
| D5 | ¿Qué campos son obligatorios por tipo de Servicio? | Plantilla/versionado de campos técnicos; evitar inferencia por nombre. |
| D6 | ¿Debe admitirse finalización desde `EN_PROCESO`? | No en el Incremento 0; resolver su interacción con los Turnos asistidos/presenciales de BH-063 antes de ampliar la transición. |
| D7 | ¿Quién puede finalizar? | Personal asignado; definir capacidad excepcional separada y auditada para supervisión. |
| D8 | ¿Qué significa la ventana de 24 horas? | Corrección auditada, no edición silenciosa; precisar zona horaria, campos y excepción supervisada. |
| D9 | ¿Qué regla combina impactos multiservicio? | No usar orden incidental; definir prioridad o exigir estado final observado. |
| D10 | ¿Pago y stock bloquean finalización? | No acoplar hasta definir contrato; ofrecer preflight visible y políticas independientes. |
| D11 | ¿Los efectos derivados son parte del éxito o trabajo reconciliable? | Persistir evento y efectos críticos; tareas no críticas reintentables con estado. |
| D12 | ¿Cómo se corrige una evaluación histórica errónea? | Operación de corrección con motivo/auditoría o supersesión, nunca reemplazo de una observación nueva. |

## 15. Flujo objetivo propuesto

### 15.1 Antes de la atención

1. Cliente puede existir sin perfil completo.
2. La solicitud/creación del Turno usa BH-057 para decidir si el Servicio exige
   evidencia técnica adicional.
3. Si falta una evaluación requerida, se solicita o deriva a revisión; no se
   bloquean Servicios cuya política no la exige.
4. El profesional consulta sólo Clientes/Turnos dentro de su alcance.

### 15.2 Durante la atención

1. Desde el Turno asignado, el profesional ve snapshot actual, diagnósticos
   autorizados, fichas previas relevantes y evaluación de riesgo.
2. Puede registrar una **nueva evaluación** o una **corrección del perfil** como
   acciones distintas.
3. Cada Detalle muestra una ficha adaptada a la configuración del Servicio.
4. Guardar borrador no finaliza; la fórmula base se copia como referencia y no
   se confunde con fórmula efectivamente usada.

### 15.3 Finalización

1. UI consulta preflight: estado, ownership, detalles, fichas/campos requeridos y
   advertencias no bloqueantes.
2. El profesional confirma una única operación con clave idempotente.
3. Backend bloquea y revalida; no confía en el preflight.
4. Guarda el evento y transición una vez.
5. Genera efectos deduplicados y registra su resultado.
6. Devuelve resumen por Detalle, diagnóstico creado o no, rutinas/cuidados y
   pendientes reconciliables.

### 15.4 Después

- el Cliente ve ficha con fórmula sensible omitida como hoy;
- una corrección permitida crea trazabilidad de versión/antes/después;
- un nuevo guardado del Turno no repite automatizaciones;
- productos y contenido siguen calculándose bajo demanda, salvo nueva decisión.

## 16. Plan incremental

### Incremento 0 — contención de finalización

**Objetivo:** eliminar el riesgo de corrupción antes de exponer UI.

**Alcance backend**

- crear servicio de dominio de finalización;
- permiso efectivo + Personal activo + ownership del Turno;
- lock y transacción;
- transición permitida explícita;
- identidad única de finalización/retry;
- corregir impacto nulo y prohibir orden multiservicio incidental;
- retirar del `post_save` los productores de finalización o guardarlos por
  transición/evento mientras se migra;
- desacoplar finalización de diagnóstico cuando no se crea uno.

**Archivos probables:** `gestion/views.py`, nuevo
`gestion/turno_finalization_services.py`, `gestion/signals.py`, `gestion/models.py`,
migración y tests dedicados. Los nombres definitivos deben seguir el patrón de
servicios semánticos existente.

**Contrato propuesto**

```text
POST /api/gestion/turnos/{id}/finalizar/
Idempotency-Key: <uuid>

200/201: finalizacion_id, turno_id, previous_state, current_state,
         changed, effects[], warnings[]
403: permiso/ownership
409: transición o clave incompatible
422/400: requisito funcional faltante
```

**UI:** ninguna publicación funcional todavía; como máximo cliente API y
fixtures.

**Pruebas:** estados, ownership, rollback por cada falla, retry, concurrencia,
unicidad de efectos, guardados posteriores y Turno sin diagnóstico.

**Aceptación:** dos requests no producen más de una finalización ni un efecto;
una falla no deja un estado imposible; el mismo retry obtiene el resultado.

### Incremento 1 — trazabilidad de perfil y evaluación

**Objetivo:** resolver la divergencia entre snapshot y evaluaciones.

**Alcance:** definir operación de nueva evaluación, corrección auditada y
política de promoción al perfil vigente; preservar procedencia y motivo. Separar
observación profesional de mensaje calculado y definir recalculo/versionado de
derivados.

**Archivos probables:** `usuarios/models.py`, `usuarios/serializers.py`,
`usuarios/views.py`, modelos/serializers/views de diagnóstico, servicio nuevo,
migraciones y tests.

**Contrato:** lectura del perfil debe devolver IDs y nombres; mutaciones deben
indicar `operation=new_evaluation|correct_current_profile`, `motivo` cuando
corresponda y resultado de sincronización.

**UI:** corregir editor del Cliente; formulario profesional separado con fuente,
fecha y advertencia visible sobre si actualizará el perfil.

**Permisos:** Cliente sólo autorreporte/corrección propia según política;
profesional usa `diagnosis.create`; una corrección excepcional puede requerir
capacidad nueva, no `is_staff`.

**Pruebas:** historia preservada, IDs/nombres, autor/procedencia no falsificable,
corrección vs evaluación, motor y rollback.

**Aceptación:** cada valor vigente puede explicarse por una operación trazable y
ninguna evaluación nueva sobrescribe una anterior.

### Incremento 2 — ciclo de ficha técnica

**Objetivo:** hacer explícita la completitud por Servicio y la corrección.

**Alcance:** configuración técnica por Servicio; borrador/completa; campos
químicos condicionales; foto opcional con fallo recuperable; ventana de
corrección decidida; versiones/auditoría; preflight de finalización.

**Archivos probables:** modelos y serializers de `Servicio`/`FichaTecnica`,
servicio de ficha, API, migraciones y tests.

**Contrato:** endpoint de contexto por Turno devuelve Detalles, plantilla,
requisitos y ficha/version; `PUT/PATCH` exige versión optimista para evitar
pisadas.

**UI:** componente nuevo por Detalle, integrado a agenda; no reutilizar sin
adaptación los componentes legacy.

**Permisos:** conservar `technical_record.manage`, ownership y
`manage_formulas`; no ampliar lectura global.

**Pruebas:** multiservicio, Servicio químico/no químico, requeridos, duplicado,
versión concurrente, ventana y fórmula sensible para Cliente.

**Aceptación:** una ficha completa pertenece inequívocamente a un Detalle y toda
corrección conserva autor, motivo e historia.

### Incremento 3 — consolidación de automatizaciones

**Objetivo:** un productor por efecto y trazabilidad de causa.

**Alcance:** trasladar cuidados, rutinas, diagnóstico condicional,
notificaciones y retoque a handlers idempotentes del evento; constraints de
unicidad; reconciliador; política multiservicio; versionado de reglas.

**Archivos probables:** servicio de finalización, nuevos handlers/outbox si
corresponde, modelos de efectos, `signals.py`, migraciones y tests.

**UI:** mostrar resumen de efectos completados/pendientes sin permitir
re-dispararlos manualmente.

**Pruebas:** repetición de cada handler, reanudación parcial, regla modificada,
multiservicio y fechas comerciales.

**Aceptación:** cada efecto identifica finalización y regla/Servicio causante;
reprocesarlo no duplica datos.

### Incremento 4 — UI profesional productiva

**Objetivo:** publicar el recorrido sólo sobre contratos endurecidos.

**Alcance React:** contexto técnico del Turno, evaluación, ficha por Detalle,
preflight, confirmación, resultado, 403/409 y refresh de sesión. Usar Axios y
`SessionContext` comunes y renderizar por capabilities sólo como UX.

**Archivos probables:** páginas de `frontend/src/pages/session/`, componentes y
API comunes, rutas, navegación y tests. Los legacy pueden descomponerse, no
montarse directamente.

**Permisos:** backend sigue siendo autoridad. La UI no muestra acceso global
por rol nominal ni supone que capacidad de lectura permite escritura.

**Pruebas:** capability ausente/revocada, ownership, conflicto de versión,
retry, multiservicio y accesibilidad básica.

**Aceptación:** un profesional asignado completa el recorrido sin rutas ocultas
ni llamadas legacy; un actor no autorizado no puede hacerlo aunque manipule UI.

### Incremento 5 — interfaces con BH-063/BH-064

**Objetivo:** integrar sin absorber los alcances de llegada, alta y operación
presencial.

- BH-063 define Turnos asistidos/presenciales y deberá consumir el contrato de
  finalización sin eludir su estado ni ownership.
- BH-064 define el alta rápida de Cliente presencial, sin exigir diagnóstico y
  devolviendo una identidad estable para continuar el recorrido.
- El preflight consume esos estados, pero no redefine sus permisos ni
  transacciones.
- Ninguno debe crear diagnósticos ficticios para satisfacer el flujo.

**Aceptación:** alta, llegada, evaluación, ficha y finalización tienen contratos
independientes, componibles y con una sola autoridad por transición.

## 17. Dependencias y no alcance

### Dependencias

- BH-057: política de riesgo y confiabilidad de diagnóstico por Servicio;
- BH-060: capacidades efectivas de diagnóstico, ficha, fórmula y rutina;
- BH-062: cierre técnico que identificó estas superficies React como pendientes
  diferibles;
- BH-063: interfaz futura de Turnos asistidos/presenciales;
- BH-064: interfaz futura de alta rápida de Cliente presencial.

### No alcance de este análisis

- implementar BH-063 o BH-064;
- convertir diagnóstico o ficha en requisitos universales;
- diseñar cobro, liquidación o consumo de stock;
- ampliar lectura técnica global;
- cambiar roles, permisos, modelos, migraciones, configuración o tests;
- publicar componentes legacy;
- modificar `BACKLOH.xlsx` o documentos históricos.

## 18. Evidencia principal revisada

- `documentacion/Bohemia Hair(2).docx.txt` — UC-05, UC-11 y UC-17.
- `documentacion/DSS_UC11_Generacion_Automatica_Rutina.puml`.
- `documentacion/DSS_UC17_Historial_Tecnico.puml`.
- `documentacion/generales/ANALISIS_FLUJO_OBJETIVO_TURNOS.md`.
- `documentacion/BH-057/ANALISIS_BH057_HISTORIAL_RIESGO.md`.
- `documentacion/BH-060/IMPLEMENTACION_BH060_3_FICHA_FORMULAS_RUTINAS.md`.
- `documentacion/BH-062/AUDITORIA_CIERRE_BH062.md`.
- `bohemiacore/usuarios/models.py`, `serializers.py`, `views.py` y
  `client_account_services.py`.
- `bohemiacore/gestion/models.py`, `serializers.py`, `views.py`, `signals.py`,
  `effective_access.py`, `permissions.py`, `technical_risk_evaluator.py`,
  `turno_creation_services.py` y `routine_services.py`.
- tests de registro, autorización de diagnóstico, ficha/fórmula/rutina, riesgo,
  sesión y Turnos.
- React de registro, perfil, alta de Cliente, Turnos, sesión y componentes
  legacy de ficha.

## 19. Conclusión

El dominio puede evolucionar sin imponer diagnósticos artificiales ni perder
historia si se mantiene la separación entre perfil vigente, evaluación, ficha y
efectos automáticos. El primer cambio no debe ser una pantalla: debe ser una
finalización transaccional, idempotente, autorizada por objeto y observable.
Después puede definirse la política de vigencia del perfil y publicarse un
recorrido profesional incremental sobre contratos seguros.
