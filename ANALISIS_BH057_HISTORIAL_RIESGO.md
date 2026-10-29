# BH-057 — Análisis de historial técnico y riesgo

Fecha: 2026-10-24

## Alcance y conclusión ejecutiva

BH-057 debe introducir una evaluación técnica **previa al Turno** que responda,
de forma determinista y explicable, si un Cliente puede solicitar uno o varios
Servicios para una fecha determinada.

La arquitectura recomendada es:

1. metadata técnica explícita por Servicio, sin inferencias por nombre;
2. políticas publicadas e inmutables por versión;
3. familias separadas de reglas de intervalo, diagnóstico y frecuencia;
4. evaluador central sin efectos laterales;
5. solicitud técnica que no ocupa agenda;
6. evaluación persistida con snapshot de entradas y reglas;
7. revisión profesional con permiso específico, `DIAGNOSTICO` activa y
   compatibilidad BH-056 con todos los Servicios solicitados.

BH-057 termina en una solicitud técnicamente aprobada, rechazada o en revisión.
No cobra, no crea preferencia de pago, no confirma Turno y no crea HOLD.

## 1. Inventario del historial técnico actual

### 1.1 Fuentes principales

| Fuente | Datos disponibles | Estructura y antigüedad | Confiabilidad | Uso recomendado |
|---|---|---|---|---|
| `DiagnosticoCapilar` | Cinco dimensiones discretas: tipo, grosor, porosidad, cuero cabelludo y estado general; textos; autor; fecha; regla/rutina/Servicio sugeridos | Histórico fechado con `HistoricalRecords`; no tiene vigencia, origen, nivel de confianza ni completitud | Media/baja para registros legacy: el autor es nullable y también se crean diagnósticos automáticos o desde autorreporte | Datos discretos como señal si se conoce su procedencia; textos sólo para revisión humana |
| `Cliente` | Copia del estado capilar actual y `productos_actuales` | Snapshot mutable, sin fecha ni procedencia propia | Baja para decisiones duras: el Cliente puede editarlo y la automatización post-servicio lo sobrescribe | Contexto y detección de datos faltantes, no antecedente clínico autónomo |
| `Turno` | Cliente, Personal, fecha/hora planificada, estado y alerta booleana | Tiene histórico, pero no fecha real de ejecución/finalización | Alta para estado `REALIZADO`; media para la hora efectiva | Fuente de eventos realizados, usando temporalmente la fecha planificada |
| `DetalleTurno` | Servicio exacto, precio y duración históricos | Relación explícita con Turno; no guarda snapshot de metadata técnica del Servicio | Alta para saber qué Servicio se registró; media para reconstruir su riesgo histórico si el Servicio cambió | Fuente principal de procedimientos anteriores; agregar snapshot técnico futuro |
| `Servicio` | Categoría comercial, impactos, `es_quimico_agresivo`, dos esperas, puntaje y skills | Metadata mutable con histórico; no existe familia técnica, nivel de riesgo ni requisito de diagnóstico | Potencialmente útil, pero insuficiente y sin datos locales | Migrar a perfil técnico explícito; no inferir desde nombre/categoría comercial |
| `FichaTecnica` | Servicio exacto vía Detalle, autor, fecha, porosidad y estado final, rutina; fórmula, observaciones, resultado y foto | Una por Detalle; no tiene `HistoricalRecords`; puede crearse con Turno confirmado o en proceso, no sólo realizado | Media; la autoría actual depende de `is_staff` y no prueba finalización | Campos discretos como evidencia estructurada; textos/foto/fórmula sólo para revisión |
| `ReglaDiagnostico` | Combinación opcional de cinco atributos, prioridad, acción/mensaje y sugerencias | Parametrizable y con histórico, pero sin code, activa, versión ni outcome BH-057 | Útil para recomendación diagnóstica, no para compatibilidad temporal | Reutilizar conceptos, no usarla directamente como regla de booking |
| `ConfiguracionDiagnostico` | Umbrales, mensajes, rutinas y Servicios por nivel | Singleton mutable con histórico | Baja para riesgo de reserva: suma puntajes heterogéneos y no conserva versión aplicada | Antecedente; no convertir su score en decisión BH-057 sin validación de negocio |
| `ReglaCuidado`, `Rutina`, `AgendaCuidados` | Cuidados y restricciones posteriores al Servicio | Estructura de recomendación y documentos versionados | Útil para post-servicio, no prueba recuperación ni cumplimiento | Evidencia contextual; no autoriza automáticamente otro proceso |
| Fórmulas | Plantilla en Servicio y fórmula real en Ficha | Texto libre | No automatizable de forma segura | Sólo evidencia interna para revisor con `manage_formulas` |
| `Turno.alerta_daño_capilar` | Booleano calculado al crear | Sin regla, valores, versión ni fecha mínima asociada | Baja y no explicable | Reemplazar por evaluación persistida; conservar sólo durante transición |

### 1.2 Datos locales observados

La base local auditada contiene:

- 0 Servicios y 0 categorías;
- 0 Turnos, Detalles, Fichas y Diagnósticos;
- 0 Reglas de Diagnóstico y ningún singleton de configuración persistido;
- por tanto, 0 registros con metadata química, impactos o esperas.

No es posible validar distribución, calidad, antigüedad real ni valores de
negocio con esta base. El primer despliegue debe incluir un reporte de
completitud sobre datos reales y no debe inventar esperas o clasificaciones.

## 2. Automatizaciones existentes

| Automatización | Estado real | Problemas | Integración BH-057 |
|---|---|---|---|
| `TurnoCreationService._requires_hair_damage_alert()` | Activa en creación de Turno | Sólo busca mismo `categoria_id`, usa `timezone.now()` en lugar de `fecha_solicitada`, considera un solo Servicio y guarda un booleano sin explicación. No bloquea ni deriva a cola | Sustituir su decisión por el evaluador; usarla temporalmente sólo como comparación de regresión |
| `SaludCapilarService.obtener_bloqueo_salud_capilar()` | Sin consumidores | Sólo contempla químicos agresivos con Ficha, toma la espera del Servicio previo y no una regla origen→destino; elige un solicitado “crítico” pero no evalúa cada combinación | Extraer casos de prueba y mensajes; no conectar directamente |
| Motor de `DiagnosticoCapilar` | Activo al crear Diagnóstico por API, registro público y finalización | Tiene efectos laterales: crea rutina, modifica el Diagnóstico, recomienda Servicio y puede crear Turno. Sin versión ni snapshot | Separar cálculo puro de efectos; usar diagnóstico resultante como señal, no como motor de booking |
| `ReglaDiagnostico` | Consumida por el motor; sólo gana la primera por prioridad | Sin estado activa, code, outcome estable o versionado; prioridad puede ocultar otras señales | Mantener para diagnóstico/recomendación o migrarla posteriormente; no mezclar con reglas temporales |
| Scoring de catálogos | Activo cuando no coincide una regla | Suma “puntajes base” sin explicación por regla y trata faltantes como cero, lo que puede parecer crítico | No usar como scoring acumulado BH-057 |
| Impactos post-servicio | Activos por signal al guardar un Turno `realizado` | Sobrescriben el perfil del Cliente; no crean ledger acumulativo. La actualización de `estado_general` puede ejecutarse incluso sin impacto configurado. Un nuevo save del Turno realizado puede repetir efectos | Leer con cautela; reemplazar por eventos/snapshots idempotentes en una fase posterior |
| Diagnóstico post-servicio | Activo en `finalizar_turno` | Copia el perfil resultante; no distingue observación profesional de inferencia automática | Agregar procedencia futura; legacy ambiguo implica revisión en casos de alto riesgo |
| Reglas/rutinas post-servicio | Activas en vista y signal | Responsabilidad duplicada y potencial repetición de notificaciones/cuidados | Fuera del resultado de riesgo; puede aportar evidencia de cuidado recomendado, no de cumplimiento |
| Creación de Turno sugerido | Activa si el motor recomienda Servicio y encuentra slot | Crea `Turno.SUGERIDO`; ese estado está en `ACTIVE_TURNO_STATES`, por lo que bloquea disponibilidad | Retirar del concepto Turno: usar recomendación o solicitud no bloqueante |

No existe hoy un consumidor de `SaludCapilarService`. Tampoco existen tests
específicos para esperas, reglas químicas, vigencia de diagnóstico o el motor
de riesgo; la cobertura encontrada de `SUGERIDO` y alerta es incidental.

## 3. Servicio previo frente a Servicio solicitado

La evaluación no debe buscar únicamente “la última categoría igual”. Para cada
Servicio solicitado debe:

1. obtener `DetalleTurno` de Turnos `REALIZADO` anteriores a la fecha solicitada;
2. ordenar por fecha/hora del evento;
3. identificar Servicio y familia técnica vigentes **en el momento del evento**;
4. comparar todos los antecedentes relevantes contra cada Servicio solicitado;
5. aplicar reglas exactas o por familia;
6. calcular días entre el evento y `fecha_solicitada`, no entre el evento y hoy;
7. calcular `fecha_minima_recomendada` como el máximo de las fechas mínimas
   disparadas;
8. evaluar aparte frecuencia/acumulación dentro de ventanas explícitas.

Temporalmente, registros legacy usarán `Turno.fecha` y `hora_inicio`. A futuro
debe existir `finalizado_at` porque una cita planificada no prueba la hora real
del procedimiento.

Una Ficha faltante no debe borrar un Servicio `REALIZADO`: el Turno/Detalle
prueba el procedimiento; la Ficha aporta estado final y evidencia adicional.

## 4. Arquitectura de reglas de compatibilidad

### Comparación

| Alternativa | Ventajas | Problemas |
|---|---|---|
| A. Servicio individual | Máxima precisión y mensajes específicos | Explosión combinatoria y mantenimiento repetitivo |
| B. Categoría técnica | Pocas reglas y buena cobertura | Una categoría comercial actual es demasiado amplia; excepciones son difíciles |
| C. Híbrida | Regla base por familia técnica y excepción por Servicio | Requiere precedencia y validación claras |

### Recomendación: híbrida

Crear una clasificación técnica explícita, estable y con code, distinta de
`CategoriaServicio`. Conceptualmente puede llamarse `FamiliaProcesoTecnico` y
representar, por ejemplo, coloración, decoloración, alisado químico o proceso
térmico. Los valores reales deben validarse con negocio; no se siembran desde
nombres.

Cada Servicio necesita un perfil técnico explícito, incluido un estado de
clasificación (`CLASIFICADO`/`PENDIENTE`) y nivel de riesgo. Un Servicio no
clasificado no recibe APTO silencioso para una solicitud real.

No conviene una única tabla genérica con JSON para todas las condiciones. El
modelo mínimo mantenible separa al menos:

1. **Regla de intervalo**: selector origen (Servicio o familia), selector
   destino, días mínimos, outcome, severidad, mensajes y prioridad.
2. **Regla de diagnóstico**: selector destino, diagnóstico requerido,
   antigüedad máxima, outcome si falta y outcome si venció.
3. **Regla de frecuencia**: familia/Servicio, ventana temporal, cantidad máxima
   y outcome. Puede incorporarse cuando negocio valide umbrales; no debe ser un
   score mágico.

Todas pertenecen a una versión publicada de política. Cada selector debe exigir
exactamente Servicio o familia, nunca ambos ni ninguno. Para intervalo, la
precedencia es exacto→exacto, exacto→familia/familia→exacto y finalmente
familia→familia. Dentro de la misma especificidad se conservan todas las reglas
aplicables y gana el outcome más restrictivo. La prioridad ordena mensajes y
recomendaciones, no permite que una regla leve rebaje una prohibición.

## 5. Diagnóstico vigente

Hoy sólo existe `fecha_diagnostico`; no existe política de vigencia. BH-057 debe
calcular vigencia contra `fecha_solicitada`, mediante reglas por Servicio o
familia, no con un único número hardcodeado.

La regla debe distinguir:

- diagnóstico inexistente;
- diagnóstico vencido;
- diagnóstico incompleto;
- diagnóstico de procedencia no verificable;
- diagnóstico vigente y profesional.

No se deben asumir ahora 90 días ni qué Servicios lo requieren. El ejemplo
COLORACION/90 días es soportado por el diseño, pero necesita configuración
publicada.

Para bajo riesgo, la política puede permitir APTO o ADVERTENCIA sin diagnóstico.
Para alto riesgo, la recomendación inicial es REQUIERE_REVISION si falta, está
vencido o su procedencia es ambigua. NO_APTO debe surgir de una regla dura, no
sólo de ausencia de información.

El modelo futuro de Diagnóstico necesita `source`/`provenance` (profesional,
autorreporte, inferencia post-servicio, migrado), completitud y, si corresponde,
vínculo al evento que lo originó. No debe inferirse indefinidamente la confianza
sólo por `profesional IS NULL`.

## 6. Ficha Técnica

### Automatizable con cautela

- Servicio/Detalle/Turno asociados;
- fecha del procedimiento;
- `porosidad_final`;
- `estado_general_final`;
- existencia de una Ficha y autoría.

Estos datos pueden disparar reglas discretas sólo después de corregir permisos,
procedencia, estado válido del Turno e inmutabilidad/auditoría. En legacy deben
presentarse como evidencia y no como única base de NO_APTO.

### Sólo revisión humana

- `formula` y plantilla de fórmula;
- `observaciones_proceso`;
- `comentario_cliente`;
- `resultado_post_servicio`;
- fotografía;
- texto de rutina o recomendaciones.

No se recomienda NLP, búsqueda de palabras ni conversión automática de esos
textos a outcome.

## 7. Impacto acumulado y señales obligatorias

| Señal | Estado actual | Automatización confiable propuesta |
|---|---|---|
| Tiempo desde último Servicio realizado | Estructurado en Turno/Detalle | Sí, con fecha solicitada y regla explícita |
| Servicio anterior y solicitado | IDs explícitos | Sí |
| Combinación origen→destino | No modelada | Sí, mediante regla de intervalo híbrida |
| Acumulación química | Sólo booleano por Servicio; no hay ledger ni regla de ventana | Sólo conteo explicable cuando la clasificación esté completa |
| Decoloraciones previas | No estructuradas | Evidencia humana hasta crear familia técnica explícita |
| Coloraciones previas | No estructuradas de forma fiable | Igual |
| Tratamientos térmicos | No estructurados | Igual |
| Diagnóstico y antigüedad | Estructurados, procedencia ambigua | Sí para edad/completitud; contenido con cautela |
| Estado/impactos | FKs discretas en Servicio, Diagnóstico, Ficha y Cliente | Sí como regla explícita; no como suma opaca |
| Frecuencia de procedimientos | Derivable de Turnos realizados | Sí mediante “N eventos en X días”, con regla identificable |
| Historial incompleto/inexistente | Detectable | Resultado según riesgo y política, normalmente no NO_APTO por sí solo |

No se recomienda un “daño acumulado” numérico general. Una política explicable
puede decir: “tres procesos de familia X en 120 días disparan revisión”,
registrando eventos y umbral. Recuperación no puede inferirse por el mero paso
del tiempo o por una rutina asignada; requiere diagnóstico/Ficha posterior.

## 8. Contrato del evaluador

Contrato conceptual:

```python
evaluate_booking_risk(
    *,
    cliente,
    servicios,
    fecha_solicitada,
    policy_version=None,
)
```

Salida interna mínima:

```text
outcome: APTO | ADVERTENCIA | REQUIERE_REVISION | NO_APTO
severity: nivel estable y ordenable
rule_codes: reglas disparadas con su versión
missing_data: datos faltantes clasificados
relevant_history: antecedentes y valores usados
minimum_recommended_date: fecha o null
alternatives: recomendaciones estructuradas opcionales
policy_version: versión publicada
evaluated_at: timestamp
input_snapshot: cliente/Servicios/fecha y metadata técnica relevante
```

El resultado debe ser determinista para el mismo snapshot y versión. El motor
no crea Turno, notificación, rutina, pago ni HOLD. Persistir y notificar son
orquestación externa.

Debe haber dos representaciones:

- **interna**: códigos, evidencia, valores y mensajes profesionales;
- **cliente**: outcome público, explicación segura, datos que debe aportar,
  fecha mínima y alternativas, sin fórmula, notas internas ni detalle clínico.

## 9. Semántica y agregación de outcomes

- **APTO**: puede avanzar automáticamente al siguiente paso del flujo.
- **ADVERTENCIA**: puede avanzar tras registrar aceptación de una advertencia
  versionada; no requiere decisión profesional.
- **REQUIERE_REVISION**: no rechaza ni ocupa slot; crea/actualiza un caso en
  cola técnica.
- **NO_APTO**: no puede continuar para esa fecha y combinación; ofrece fecha
  mínima o alternativa si la regla las produce.

Precedencia agregada:

`NO_APTO > REQUIERE_REVISION > ADVERTENCIA > APTO`.

Se conservan todas las reglas disparadas aunque sólo se devuelva un outcome.
En multiservicio se evalúan todos los Servicios y sus interacciones; el resultado
global es el más restrictivo.

Una configuración inválida, versión inexistente o regla corrupta debe fallar
cerrado como error de sistema/revisión, nunca conceder APTO por excepción. No
debe convertirse automáticamente en NO_APTO clínico.

## 10. Solicitud y revisión profesional

Se recomienda una entidad previa al Turno, conceptualmente
`SolicitudTecnicaReserva`, con Cliente, Servicios, fecha/hora preferidas,
Personal preferido opcional, estado técnico y revisión vigente. No es HOLD y no
participa en conflictos de agenda.

Estados mínimos:

- `EVALUANDO`;
- `APROBADA_TECNICAMENTE`;
- `EN_REVISION`;
- `INFORMACION_REQUERIDA`;
- `RECHAZADA_TECNICAMENTE`;
- `SUPERADA` o `VENCIDA` cuando cambian datos/fecha y se requiere reevaluar.

La decisión profesional necesita un permiso nuevo:

`gestion.review_technical_booking`

Los permisos existentes no expresan esta capacidad:

- `create_diagnosis`: crea/edita Diagnóstico, no decide solicitudes;
- `manage_technical_record`: acceso global a historial, no decisión de workflow;
- `manage_formulas`: acceso a fórmula sensible;
- `finalize_service`: finaliza un Servicio ya prestado.

Requisitos invariantes del revisor v1:

1. Usuario y Personal activos;
2. `gestion.review_technical_booking` efectivo;
3. `DIAGNOSTICO` activa, porque la decisión interpreta salud/historial;
4. compatibilidad con la unión de skills de los Servicios mediante
   `service_skill_policy(...).personal_can_perform()`.

No se justifica crear `REVISION_TECNICA` en v1: `DIAGNOSTICO` ya representa la
competencia observada necesaria. Si negocio diferencia posteriormente diagnóstico
de aprobación de riesgo, podrá introducirse otra skill con evidencia explícita.

BusinessRole, `Personal.rol` e `is_staff` no son autoridad.

## 11. Cola y acciones del profesional

La cola debe mostrar:

- Cliente e intención de Servicio/fecha;
- último diagnóstico, procedencia y antigüedad;
- Servicios realizados relevantes y sus intervalos;
- Fichas estructuradas relevantes;
- datos faltantes;
- reglas y evidencia que causaron escalación;
- recomendación del motor y fecha mínima calculada.

Acciones v1 necesarias:

1. **Aprobar** técnicamente, con motivo;
2. **Rechazar** técnicamente, con motivo y mensaje seguro;
3. **Solicitar diagnóstico/información**, indicando qué falta;
4. **Recomendar otra fecha**, estructurada y revaluable.

“Recomendar otro Servicio” puede ser un dato opcional de recomendación en v1,
pero no una transición automática: requiere volver a evaluar la nueva selección.
No debe aprobar implícitamente un Servicio distinto.

Las decisiones deben usar lock, transición válida e idempotencia. Dos revisores
no pueden resolver el mismo caso vigente con decisiones incompatibles.

## 12. Historial técnico y privacidad

| Actor | Historial visible | Permiso | Skill | Ownership/alcance |
|---|---|---|---|---|
| Cliente | Sus Diagnósticos y evaluaciones, con DTO público; sin fórmula/notas internas | Autenticado | No | Sólo propio |
| Empleado | Ningún historial técnico por `view_clients` | Ninguno | No | `view_clients` sólo conserva datos administrativos mínimos |
| Profesional genérico | Ningún historial global por rol | Permisos efectivos | Según acción | El rol no concede acceso |
| Personal revisor | Evidencia mínima de casos elegibles de su cola | `review_technical_booking` | `DIAGNOSTICO` + compatibilidad de Servicios | Sólo casos asignados/elegibles |
| Gestor técnico | Historial técnico global | `manage_technical_record` | `DIAGNOSTICO` activa | Global, sin fórmulas salvo permiso adicional |
| Gestor de fórmulas | Fórmulas dentro de un caso permitido | `manage_formulas` | No reemplaza skills/revisión | Sólo si además puede ver el caso |
| Administrador | Igual que cualquier actor con permisos efectivos | Permisos correspondientes | Skills obligatorias para revisar | ADMINISTRADOR no evita controles |
| Permiso individual | Mismo comportamiento que permiso por grupo | Permiso específico | Skills obligatorias | Sin dependencia de BusinessRole |

El `ClienteViewSet` actual expone sólo identidad/contacto básico, lo cual es
compatible: `usuarios.view_clients` no debe ampliarse con Diagnósticos, Fichas,
fórmulas o evaluaciones.

El `FichaTecnicaViewSet` actual usa `IsAdminUser`/`is_staff` y entrega en un mismo
serializer datos estructurados y fórmula. BH-057 debe migrar ese acceso a
permisos efectivos y DTOs separados antes de usar la Ficha en la cola.

## 13. Parametrización e invariantes

### Configurable sin cambiar código

- días mínimos por combinación;
- incompatibilidades;
- outcome, severidad, prioridad y mensajes de cada regla;
- vigencia máxima y Servicios que requieren diagnóstico;
- conducta ante diagnóstico/historial incompleto;
- ventanas y límites de frecuencia validados;
- SLA de revisión;
- alternativas recomendadas.

### Invariantes no editables como política

- autorización, ownership y skills activas;
- integridad y constraints;
- locks e idempotencia;
- transiciones imposibles;
- auditoría y versionado obligatorios;
- evaluación fail-closed ante configuración inválida;
- inmutabilidad de decisiones históricas;
- separación Solicitud/Evaluación de Turno/HOLD/Pago.

La administración de políticas debería usar otro permiso de mínimo privilegio,
por ejemplo `gestion.manage_technical_risk_policy`. `manage_configuration` es
demasiado amplio y `manage_technical_record` gobierna datos de Clientes, no
reglas de negocio. Publicar una versión debe ser una acción explícita y auditada.

## 14. Versionado y explicabilidad

Solución mínima:

- `PoliticaRiesgoTecnico(version, estado, publicada_at, publicada_por)`;
- reglas vinculadas a una política;
- versiones publicadas inmutables; un cambio clona a borrador nuevo;
- evaluación persistida con versión, outcome y timestamp;
- snapshot JSON validado de entradas relevantes y reglas disparadas;
- relación normalizada opcional a reglas para consultas/reportes;
- mensajes cliente/profesional copiados al snapshot.

El snapshot debe incluir, como mínimo:

- IDs y codes de Cliente/Servicios/familias;
- fecha solicitada;
- antecedentes considerados y fechas;
- intervalos calculados;
- diagnóstico usado, fecha, procedencia y campos discretos;
- datos faltantes;
- code, versión y parámetros efectivos de cada regla;
- fecha mínima y outcome agregado.

Una FK a la regla actual no basta: si se edita o elimina, cambia la interpretación.
La combinación de política publicada inmutable y snapshot preserva la decisión.

## 15. Datos faltantes

| Caso | Conducta recomendada |
|---|---|
| Cliente nuevo sin historial | No asumir daño. Aplicar política por riesgo: bajo puede ser APTO/ADVERTENCIA; alto requiere revisión/diagnóstico |
| Diagnóstico faltante | Aplicar la regla específica del Servicio/familia |
| Diagnóstico vencido | Igual, conservando fecha y antigüedad calculada |
| Diagnóstico incompleto | Tratar campos requeridos como faltantes; no sumar cero |
| Ficha incompleta | Mantener Turno realizado como antecedente y escalar sólo si una regla necesita el dato faltante |
| Servicio sin perfil técnico | `REQUIERE_REVISION` o error de configuración; nunca inferir por nombre ni APTO silencioso |
| Historial inconsistente | Marcar inconsistencia y escalar; no inventar orden ni evento |
| Política sin versión publicada | Fallo cerrado operativo; no emitir APTO |

El nivel de riesgo también debe ser metadata explícita. No se puede aplicar una
política “bajo vs alto” si el Servicio todavía no fue clasificado.

## 16. Servicios químicos y procesos consecutivos

`es_quimico_agresivo`, `dias_espera_bloqueo` y `dias_espera_minima` son buenos
antecedentes, pero tienen semánticas incompletas:

- una espera pertenece a una combinación origen→destino, no necesariamente a
  un solo Servicio;
- decoloración y coloración no están diferenciadas estructuralmente;
- procesos térmicos no están representados;
- “misma categoría” no expresa incompatibilidad química;
- no hay reglas para secuencia ni acumulación.

La migración debe mapear valores actuales sólo cuando exista confirmación de
negocio. Los campos legacy pueden coexistir read-only durante comparación, como
en BH-056, pero el evaluador final debe leer únicamente reglas versionadas.

Ejemplos soportados, sin sembrar sus valores:

- DECOLORACION→DECOLORACION, 45 días, NO_APTO, prioridad alta, versión 3;
- COLORACION exige diagnóstico de hasta 90 días y deriva a revisión si falta o
  venció.

Son familias distintas de regla y no deben forzarse en una tabla frágil.

## 17. Conexión con BH-056

Para una solicitud multiservicio en revisión:

```text
service_skill_policy(servicios)
    .filter_personal(Personal activos)
```

Luego se restringe a Personal con Usuario activo, permiso
`review_technical_booking` y `DIAGNOSTICO` activa. Esto preserva:

- unión de skills requeridas;
- AND sobre todas;
- skill y asignación activas;
- Personal activo;
- fail-closed;
- ausencia de fallback por rol, `is_staff` o flags legacy.

La selección automática puede asignar por carga/SLA entre candidatos aptos,
pero esa estrategia no modifica la autorización.

## 18. Turnos sugeridos

`Turno.SUGERIDO` no debe representar recomendación: hoy forma parte de
`ACTIVE_TURNO_STATES` y bloquea slot, equipamiento y conflictos.

Arquitectura futura:

- recomendación: dato en evaluación/revisión o entidad de recomendación;
- intención del Cliente: `SolicitudTecnicaReserva`;
- notificación: referencia a esa recomendación/solicitud;
- Turno/HOLD: sólo después, dentro del flujo BH-058.

Durante migración, `SUGERIDO` debe excluirse de disponibilidad sólo después de
clasificar registros existentes. No crear nuevos Turnos sugeridos desde el motor
de Diagnóstico.

## 19. Integración con el flujo de solicitud

Secuencia objetivo:

```text
Cliente elige Servicios y fecha/hora preferida
→ disponibilidad informativa, sin reserva
→ crear intención/solicitud no bloqueante
→ evaluate_booking_risk(...)
   → APTO: solicitud técnicamente aprobada
   → ADVERTENCIA: aceptación versionada → aprobada
   → REQUIERE_REVISION: cola técnica, sin bloquear slot
   → NO_APTO: rechazada para esa fecha + fecha/alternativa
→ BH-058 consume una aprobación vigente y vuelve a validar disponibilidad
→ BH-058 gestiona HOLD/pago
```

Una evaluación debe invalidarse y repetirse si cambian Servicios, fecha, Cliente,
diagnóstico relevante o versión de intención. Una nueva política no invalida
retroactivamente evaluaciones históricas; la vigencia operativa de una aprobación
puede tener una regla explícita.

## 20. Frontend futuro

### Cliente

- APTO: continuidad normal;
- ADVERTENCIA: texto seguro y aceptación explícita;
- REQUIERE_REVISION: estado y SLA, sin promesa de slot reservado;
- NO_APTO: explicación segura, fecha mínima y alternativa;
- nunca mostrar fórmula, notas internas ni razonamiento clínico completo.

### Profesional

- cola filtrada por permisos y skills;
- evidencia estructurada y textos sensibles sólo cuando corresponda;
- reglas disparadas, datos faltantes y recomendación;
- acciones v1 definidas en la sección 11.

### Administrador de política

- borradores, validación de solapamientos, preview y publicación;
- nunca edición directa de una versión publicada;
- acceso por permiso, no por ruta/rol frontend.

## 21. Auditoría futura

Eventos mínimos:

- `TECHNICAL_ASSESSMENT_CREATED`;
- `TECHNICAL_WARNING_ACCEPTED`;
- `TECHNICAL_REVIEW_REQUIRED`;
- `TECHNICAL_REVIEW_INFORMATION_REQUESTED`;
- `TECHNICAL_REVIEW_APPROVED`;
- `TECHNICAL_REVIEW_REJECTED`;
- `TECHNICAL_POLICY_PUBLISHED`;
- `TECHNICAL_ASSESSMENT_SUPERSEDED`.

Cada evento debe registrar actor o sistema, solicitud/evaluación, versión de
política, estado anterior/nuevo, rule codes, motivo, timestamp y correlación.
No debe copiar fórmula, foto ni notas clínicas completas a una auditoría de
acceso más amplio. BH-061 podrá ampliar interfaz/reportes; BH-057 debe producir
eventos suficientes.

## 22. Matriz de tests requerida

### Evaluador

- Servicio previo compatible e incompatible;
- combinación exacta y regla por familia;
- precedencia exacta sobre familia;
- período mínimo cumplido, no cumplido y fecha límite exacta;
- fecha solicitada futura, no `now()`;
- varios antecedentes y selección del relevante;
- multiservicio y outcome más restrictivo;
- diagnóstico vigente, vencido, faltante, incompleto y de origen no confiable;
- Cliente sin historial de bajo y alto riesgo;
- Servicio sin metadata;
- historial inconsistente;
- regla dura, advertencia, revisión y no apto;
- varias reglas simultáneas y conservación de todos los codes;
- frecuencia N eventos/X días sin scoring;
- cálculo de fecha mínima máxima;
- ausencia de inferencias por nombres/categorías comerciales;
- configuración inválida fail-closed.

### Versionado

- misma entrada + misma versión = mismo resultado;
- publicar nueva versión no cambia evaluación histórica;
- versión publicada no se edita;
- snapshot permite reconstruir resultado aunque cambie Servicio/Diagnóstico;
- reevaluación crea revisión nueva y supera la anterior.

### Revisión y permisos

- revisor con/sin `review_technical_booking`;
- revisor con/sin `DIAGNOSTICO`;
- Personal activo/inactivo;
- compatible/incompatible con uno y varios Servicios;
- permiso individual sin BusinessRole privilegiado;
- ADMINISTRADOR sin skill rechazado;
- `is_staff` sin permiso rechazado;
- lock e idempotencia ante decisiones concurrentes;
- transiciones inválidas;
- aprobación/rechazo/información/otra fecha auditados.

### Privacidad

- Cliente sólo ve lo propio y DTO público;
- `view_clients` no accede a historial técnico;
- `manage_technical_record` no revela fórmula;
- `manage_formulas` solo no concede acceso al caso;
- cola sólo muestra casos técnicamente elegibles;
- mensajes al Cliente no exponen notas, rule internals ni fórmula.

### Flujo

- REQUIERE_REVISION no crea Turno ni bloquea slot;
- recomendación no crea `SUGERIDO` activo;
- APTO/ADVERTENCIA terminan en aprobación técnica, no pago;
- revalidación de disponibilidad queda para el consumidor BH-058.

## 23. Primer incremento de implementación recomendado

Incremento 1, sin activar aún el nuevo flujo de reserva:

1. agregar familia/perfil técnico explícito de Servicio;
2. agregar política versionada y reglas separadas de intervalo y diagnóstico;
3. agregar evaluación persistida y snapshot explicable;
4. implementar `evaluate_booking_risk()` como servicio puro y multiservicio;
5. crear permisos `review_technical_booking` y de administración de políticas,
   sin asignarlos por `is_staff`;
6. preparar reporte de Servicios no clasificados y migración conservadora de
   metadata existente;
7. cubrir motor, versionado, datos faltantes y privacidad con tests;
8. ejecutar el motor en modo comparación, sin cambiar Turnos ni pagos.

Incrementos posteriores de BH-057 pueden añadir solicitud no bloqueante, cola,
decisiones y frontend, y finalmente retirar alerta/SUGERIDO legacy. No deben
crear HOLD ni integrar cobros.

## 24. Riesgos principales

1. No hay datos locales para calibrar reglas ni probar migración real.
2. Diagnósticos legacy mezclan autorreporte, inferencia automática y evaluación
   profesional sin procedencia explícita.
3. Servicio no tiene familia técnica ni riesgo estructurado.
4. Ficha Técnica mezcla campos estructurados con información sensible y usa
   autorización legacy `is_staff`.
5. El motor diagnóstico actual combina cálculo y efectos laterales.
6. Los impactos post-servicio sobrescriben estado en vez de registrar eventos.
7. `SUGERIDO` bloquea disponibilidad.
8. No hay `finalizado_at`; se usa fecha planificada.
9. Reglas publicadas sin inmutabilidad/versionado harían irreproducibles las
   decisiones.
10. Un modelo genérico de reglas o scoring opaco reduciría explicabilidad.

## 25. Frontera BH-057 / BH-058

BH-057 entrega:

- solicitud/intención no bloqueante;
- evaluación explicable;
- advertencia aceptada;
- cola y decisión profesional;
- estado técnicamente aprobado, rechazado o en revisión.

BH-057 no define ni implementa:

- TTL de HOLD;
- monto o porcentaje de seña;
- seña frente a pago total;
- Mercado Pago, preferencia o webhook;
- conciliación;
- confirmación de Turno por pago.

BH-058 deberá consumir una aprobación técnica vigente, volver a comprobar
disponibilidad y recién entonces aplicar su estrategia de HOLD/pago.

## Resumen solicitado

- **Arquitectura recomendada:** perfil técnico explícito + política inmutable
  versionada + reglas por familias + evaluador puro + solicitud no bloqueante +
  snapshot + revisión autorizada.
- **Datos reutilizables actuales:** Turno realizado, Detalle/Servicio exactos,
  fecha, campos discretos de Diagnóstico/Ficha e impactos explícitos; todos con
  las limitaciones de procedencia y snapshot indicadas.
- **Reglas parametrizables:** intervalo origen→destino, requisito/vigencia de
  diagnóstico y frecuencia por ventana; modelo híbrido Servicio/familia.
- **Contrato del evaluador:** outcome, severidad, rule codes, faltantes,
  antecedentes, fecha mínima, alternativas, versión, fecha y snapshot.
- **Permisos necesarios:** nuevo `review_technical_booking`; nuevo permiso de
  política recomendado; reutilizar `manage_technical_record`, `manage_formulas`
  y `DIAGNOSTICO` sólo para sus capacidades exactas.
- **Modelo de revisión:** cola sin bloqueo, revisor con permiso + Personal activo
  + `DIAGNOSTICO` + compatibilidad BH-056, decisiones auditadas e idempotentes.
- **Primer incremento:** modelos de metadata/política/evaluación, motor puro,
  migración conservadora, modo comparación y tests; sin switch de pagos.
- **Riesgos:** datos vacíos, procedencia diagnóstica, metadata incompleta,
  permisos legacy de Ficha, efectos laterales, `SUGERIDO` bloqueante y falta de
  versionado.
- **Frontera con BH-058:** BH-057 termina en decisión técnica; HOLD, cobro,
  Mercado Pago y confirmación financiera pertenecen exclusivamente a BH-058.
