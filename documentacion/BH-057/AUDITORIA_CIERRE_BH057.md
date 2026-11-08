# Auditoría de cierre completo BH-057

Fecha: 2026-10-25  
Alcance: Incrementos A+B, con foco en B y su integración con el evaluador de A.  
Modalidad: revisión estática y ejecución de pruebas; no se corrigió implementación ni se trabajó en BH-058.

## Veredicto ejecutivo

BH-057 conserva correctamente su frontera arquitectónica: la solicitud técnica es un agregado distinto de `Turno`, consume el evaluador productivo, no bloquea agenda y no incorpora HOLD ni pagos. Ownership, separación de DTOs, elegibilidad backend y exclusión mutua de decisiones están implementados.

No obstante, el cierre completo queda bloqueado por tres incumplimientos verificables:

1. La UI revisora no presenta los `antecedentes` estructurados que el backend entrega, aunque son parte de la evidencia mínima requerida para decidir.
2. La auditoría semántica de decisiones no deja una evidencia autocontenida e inmutable del motivo y la versión de policy: el evento no guarda `decision_id`, motivo ni policy/version, y la fila `DecisionRevisionTecnica` que contiene el motivo no es inmutable ni tiene auditoría propia.
3. La suite B no prueba varios escenarios obligatorios de cierre. Los 20 tests ejecutados corresponden a 13 cuerpos de prueba distintos porque 7 tests de la clase base se repiten por herencia; faltan integraciones críticas detalladas en la sección de pruebas.

## Matriz funcional

| Área | Estado | Evidencia |
|---|---|---|
| Modelo de solicitud | Conforme | `SolicitudTecnicaReserva`, through multiservicio, intento y evaluación vigente en `gestion/models.py` |
| Estados técnicos | Conforme | Ocho estados requeridos; no hay estados financieros |
| Creación productiva | Conforme | `create_technical_booking_request()` invoca `evaluate_booking_risk()` y persiste por `persist_technical_risk_evaluation()` |
| Mapeo de outcomes | Conforme | Mapeo explícito de los cuatro outcomes en `OUTCOME_TO_REQUEST_STATE` |
| Ownership Cliente | Conforme | Cliente derivado de sesión; queryset acotado; objetos ajenos devuelven 404 |
| DTO público/interno | Conforme | Serializers separados; faltantes públicos sanitizados; sin snapshots completos ni fórmulas |
| Advertencia | Conforme | Lock, evaluación vigente, versión, actor, timestamp, idempotencia y rechazo de warning superado |
| Reevaluación | Conforme en código | Nueva evaluación, supersesión y conservación de policy histórica; cobertura B incompleta |
| Cola y elegibilidad | Conforme | Usuario/Personal activos, permiso, `DIAGNOSTICO` y `service_skill_policy()` en backend |
| Decisiones y locking | Conforme funcionalmente | `select_for_update()`, estado `EN_REVISION`, validaciones e idempotencia semántica |
| Evidencia en frontend revisor | No conforme | El componente no renderiza `item.antecedentes` |
| Auditoría de decisiones | No conforme | Evento incompleto y evidencia del motivo mutable/no enlazada por `decision_id` |
| No bloqueo | Conforme en código | Sin integración con consultas de agenda, Personal, equipamiento o conflictos de Cliente |
| Frontera BH-058 | Conforme | Sin HOLD, PaymentIntent, pagos ni confirmación de Turno en el agregado BH-057 |
| Evidencia automatizada de cierre | No conforme | Faltan pruebas B explícitas obligatorias |

## 1. SolicitudTecnicaReserva

El modelo contiene:

- `cliente` protegido;
- `fecha_preferida` y `hora_preferida`;
- `personal_preferido` opcional y protegido;
- relación multiservicio explícita mediante `SolicitudTecnicaServicio`;
- `estado`;
- `intento`;
- `evaluacion_vigente` one-to-one;
- `created_at` y `updated_at`;
- `fecha_recomendada` para la acción de revisión.

Constraints relevantes:

- un Servicio no puede repetirse dentro de una solicitud;
- un número de intento no puede repetirse dentro de una solicitud;
- una evaluación sólo puede pertenecer a un intento y sólo puede ser vigente en una solicitud;
- índices por Cliente/fecha de creación y estado/fecha de creación.

No hereda de `Turno`, no tiene FK a `Turno` y no aparece en `ACTIVE_TURNO_STATES`.

## 2. Creación productiva e integración A+B

El flujo real es:

1. la API obtiene `request.user.cliente`;
2. valida Servicios activos, fecha y Personal preferido activo;
3. crea la solicitud y sus relaciones de Servicios;
4. llama a la misma función `evaluate_booking_risk()` de Incremento A;
5. persiste con `persist_technical_risk_evaluation()`;
6. crea `EvaluacionSolicitudTecnica`;
7. asigna `evaluacion_vigente`;
8. deriva el estado.

Mapeo auditado:

| Outcome | Estado |
|---|---|
| `APTO` | `APROBADA_TECNICAMENTE` |
| `ADVERTENCIA` | `ADVERTENCIA_PENDIENTE` |
| `REQUIERE_REVISION` | `EN_REVISION` |
| `NO_APTO` | `RECHAZADA_TECNICAMENTE` |

La operación está dentro de `transaction.atomic`; un fallo del evaluador revierte la solicitud incompleta. No existe creación de `Turno` en este servicio.

## 3. Ownership

La API no acepta autoridad de ownership desde el payload:

- `cliente` y `cliente_id` son rechazados por el serializer;
- creación deriva el Cliente de la sesión;
- listado y detalle filtran por `cliente=request.user.cliente`;
- aceptar advertencia y reevaluar pasan primero por `get_object()`, por lo que un objeto ajeno responde 404;
- el servicio vuelve a verificar el actor propietario dentro de la transacción.

La prueba B cubre inyección de `cliente_id`, listado ajeno, detalle ajeno y aceptación ajena.

## 4. DTO y privacidad

### DTO Cliente

Expone estado, outcome público, Servicios con snapshot de nombre, preferencia, Personal preferido básico, advertencias seguras, fecha mínima, faltantes sanitizados por `code`, alternativas y mensaje seguro.

No expone:

- `input_snapshot` o `result_snapshot` completos;
- `reglas_disparadas` ni parámetros internos;
- mensajes profesionales;
- motivo interno de rechazo;
- fórmulas o fotografías.

### DTO revisor

Expone Cliente básico, Servicios, preferencia, outcome, rule codes, faltantes, antecedentes estructurados, fecha mínima y mensajes profesionales. No expone fórmulas.

El filtrado de la cola ocurre en backend. `view_clients`, `manage_formulas` y `manage_technical_record` no son consultados por el permiso de revisión y no conceden acceso por sí solos.

## 5. Advertencias

`accept_technical_warning()`:

- bloquea la solicitud con `select_for_update()`;
- exige propietario;
- exige estado `ADVERTENCIA_PENDIENTE`;
- exige outcome `ADVERTENCIA` en la evaluación vigente;
- rechaza `superseded_by` no nulo;
- registra evaluación, policy version, codes, textos, actor y `accepted_at`;
- retorna la evidencia existente en una repetición exacta;
- cambia a `APROBADA_TECNICAMENTE`.

No existe parámetro público para seleccionar una evaluación vieja. Tras una reevaluación, aceptar la advertencia anterior devuelve 409.

## 6. Reevaluación

El servicio detecta cambios de:

- Servicios y su orden;
- fecha;
- hora;
- Personal preferido;
- indicador de información técnica actualizada.

Ante un cambio:

- bloquea la solicitud;
- incrementa intento;
- crea otra evaluación;
- enlaza ambos intentos;
- supersede la evaluación anterior mediante el servicio validado de A;
- no modifica snapshots históricos;
- recalcula estado;
- limpia una fecha recomendada anterior.

Por defecto conserva la versión de policy de la evaluación previa. Publicar otra policy no genera reevaluaciones automáticas ni reinterpreta el historial.

## 7. Cola y elegibilidad

La autoridad backend exige simultáneamente:

1. Usuario autenticado y activo;
2. permiso efectivo `gestion.review_technical_booking`;
3. Personal vinculado y activo;
4. habilidad `DIAGNOSTICO` activa con asignación activa;
5. compatibilidad AND de `service_skill_policy()` con todos los Servicios.

No se consulta `BusinessRole`, `is_staff`, `Personal.rol` ni flags legacy `realiza_*`.

La cola parte sólo de solicitudes `EN_REVISION` y filtra cada resultado por compatibilidad antes de serializarlo. Un administrador/superusuario sin `DIAGNOSTICO` recibe 403. Un permiso individual con skills funciona.

## 8. Estados y transiciones

| Estado origen | Acción | Estado destino | Permitida |
|---|---|---|---|
| `ADVERTENCIA_PENDIENTE` | aceptar advertencia vigente | `APROBADA_TECNICAMENTE` | Sí, propietario |
| `EN_REVISION` | `APROBAR` con motivo | `APROBADA_TECNICAMENTE` | Sí, revisor elegible |
| `EN_REVISION` | `RECHAZAR` con motivo y mensaje seguro | `RECHAZADA_TECNICAMENTE` | Sí, revisor elegible |
| `EN_REVISION` | `SOLICITAR_INFORMACION` con codes válidos | `INFORMACION_REQUERIDA` | Sí, revisor elegible |
| `EN_REVISION` | `RECOMENDAR_OTRA_FECHA` con fecha válida | `EN_REVISION` | Sí, no aprueba automáticamente |
| distinto de `EN_REVISION` | cualquier decisión revisora nueva | sin cambio | No, 409 |
| warning aceptado o superado | aceptar advertencia nueva | sin cambio | No; sólo repetición idempotente de la aceptación ya registrada |
| `SUPERADA`/`VENCIDA` | reevaluar | sin cambio | No |

Una solicitud aprobada no puede ser rechazada y una rechazada no puede ser aprobada mediante las acciones de revisión. Las reevaluaciones por cambio real de intención son un flujo diferente y generan nueva evaluación.

## 9. Concurrencia

Advertencia, reevaluación y decisión revisora usan `transaction.atomic` y `select_for_update()` sobre la solicitud. En PostgreSQL:

- Revisor A bloquea y aprueba.
- Revisor B espera el lock.
- Al continuar, B observa un estado distinto de `EN_REVISION` y recibe conflicto.

La prueba existente valida la transición protegida A-aprueba/B-rechaza y una única `DecisionRevisionTecnica`. No usa threads reales, pero cumple la alternativa mínima de probar la transición protegida.

## 10. No bloqueo

La búsqueda estática confirmó:

- `turno_creation_services.py` y `turno_management_services.py` no importan ni consultan solicitudes técnicas;
- `ACTIVE_TURNO_STATES` conserva exclusivamente estados de `Turno`;
- el agregado no tiene relación con equipamiento, bloqueos o HOLD;
- no hay unique constraint por Cliente/fecha/Personal que impida solicitudes concurrentes;
- el servicio no crea `Turno` ni `DetalleTurno`.

La prueba de no bloqueo crea tres solicitudes iguales y verifica disponibilidad antes/después y cero Turnos. Su cobertura no reproduce literalmente el Personal preferido ni capacidad de equipamiento, lo que forma parte del blocker de pruebas.

## 11. Turnos legacy y frontera BH-058

El nuevo flujo:

- no crea `Turno.SUGERIDO`;
- no agrega estados a `Turno`;
- no modifica `ACTIVE_TURNO_STATES`;
- no consulta `alerta_daño_capilar`;
- no usa disponibilidad como garantía de slot.

La búsqueda global encuentra Mercado Pago, webhooks, `Pago`, seña y `alerta_daño_capilar` en módulos legacy preexistentes. Ninguna de esas referencias aparece en `technical_booking_request_services.py` ni en la migración `0025`.

No se incorporaron `SlotHold`, `PaymentIntent`, preferencia de pago ni confirmación financiera. `APROBADA_TECNICAMENTE` no dispara ninguna operación posterior y sólo representa aptitud para un futuro BH-058.

## 12. Evaluador y casos fail-closed

B no duplica reglas de riesgo. Pasa Cliente, colección multiservicio, fecha y policy version al evaluador de A.

A conserva cobertura para:

- Servicio sin perfil: `REQUIERE_REVISION`, nunca `APTO` silencioso;
- Turno `REALIZADO` sin Detalle: inconsistencia estructurada y `REQUIERE_REVISION`;
- policy inexistente o referencias desactivadas: fallo cerrado;
- precedencia multiservicio;
- snapshots versionados;
- pureza sin efectos laterales;
- supersesión controlada.

Como B aplica el resultado único de A mediante el mismo mapa, ambos casos se reflejan como `EN_REVISION`. Falta, sin embargo, la prueba de integración B que materialice esas dos entradas reales y compruebe solicitud + estado + DTO.

## 13. Permisos

Las semánticas permanecen separadas:

- `review_technical_booking`: acceso al workflow de solicitudes, además condicionado por `DIAGNOSTICO` y compatibilidad;
- `manage_technical_record`: lectura técnica global de diagnósticos con `DIAGNOSTICO`, no acceso a cola;
- `manage_formulas`: fórmulas, no acceso a solicitudes;
- `create_diagnosis`: creación de diagnóstico con `DIAGNOSTICO`, no revisión de solicitudes.

Los roles pueden otorgar permisos base, pero no reemplazan skill ni compatibilidad en la decisión backend.

## 14. Frontend

### Cliente

La pantalla:

- crea intención multiservicio sin enviar Cliente;
- lista estados;
- muestra advertencias y permite aceptarlas;
- muestra fecha mínima, faltantes y mensaje seguro;
- permite reevaluar una fecha recomendada;
- repite explícitamente que todavía no hay Turno reservado;
- no muestra disponibilidad ni promete slot.

### Revisor

La ruta y navegación requieren permiso efectivo y Personal activo. La API sigue siendo autoridad para skill y compatibilidad. Las respuestas actualizan o retiran el caso localmente; 403/409 dejan el caso sin mutarlo y muestran mensajes backend acotados.

Incumplimiento: aunque el DTO incluye `antecedentes`, `RevisionTecnica.js` no los renderiza. Sólo presenta rule codes, faltantes, fecha mínima y mensajes profesionales. Esto no satisface la evidencia estructurada requerida para la UI revisora.

## 15. Auditoría

Eventos implementados:

- `TECHNICAL_ASSESSMENT_CREATED`;
- `TECHNICAL_WARNING_ACCEPTED`;
- `TECHNICAL_REVIEW_REQUIRED`;
- `TECHNICAL_REVIEW_APPROVED`;
- `TECHNICAL_REVIEW_REJECTED`;
- `TECHNICAL_REVIEW_INFORMATION_REQUESTED`;
- `TECHNICAL_REVIEW_DATE_RECOMMENDED` adicional;
- `TECHNICAL_ASSESSMENT_SUPERSEDED`.

Conformes:

- actor y timestamp de `Auditoria`;
- solicitud y evaluación en eventos de solicitud;
- policy/version en evaluación creada, supersesión y warning;
- estado anterior/nuevo en decisiones;
- payloads acotados sin snapshots ni fórmulas completas.

Incumplimiento bloqueante:

- los eventos de decisión no incluyen `decision_id`, motivo ni policy/version;
- el motivo sólo queda en `DecisionRevisionTecnica`;
- `DecisionRevisionTecnica` no es inmutable y no está registrada entre los modelos con signals genéricas de auditoría;
- por ello, el motivo podría modificarse por ORM sin dejar rastro y el evento semántico no permite enlazar de forma inequívoca la evidencia original;
- el evento de warning registra estado anterior, pero no explicita el estado nuevo.

La evidencia puede reconstruirse actualmente mediante joins y semántica del evento, pero no satisface el estándar de auditoría íntegra solicitado para el cierre.

## 16. Revisión de pruebas

### Resultados ejecutados

- Incremento B: **20/20 OK**.
- Incremento A: **54/54 OK**.
- BH-056/skills, Diagnóstico y Turnos: **133/133 OK**.
- roles y `/me/`: **31/31 OK**.
- Frontend relevante — UI técnica, navegación, Header, sesión y rutas protegidas: **73/73 OK**.
- `python manage.py check`: **OK**.
- `python manage.py makemigrations --check --dry-run`: **sin cambios**.
- `python -m compileall gestion usuarios`: **OK**.
- `git diff --check`: **OK**; sólo avisos informativos CRLF/LF.

La ejecución backend inicialmente agrupada excedió el límite del harness por el volumen de salida de signals; las mismas suites se ejecutaron luego separadas y todas concluyeron en OK.

### Calidad de los 20 tests B

El runner reporta 20 porque `TechnicalBookingReviewTests` hereda los 7 tests de `TechnicalBookingRequestTests` y los vuelve a ejecutar. Existen 13 cuerpos de prueba únicos.

Cobertura presente:

- cuatro outcomes y cero Turnos;
- integración real APTO con evaluador;
- ownership e inyección de Cliente;
- warning, auditoría básica, idempotencia y warning superado;
- reevaluación por fecha, supersesión e inmutabilidad;
- cola elegible e incompatible;
- permiso individual;
- ausencia de permiso/skill/Personal activo;
- administrador sin skill;
- aprobar, rechazar, pedir información y recomendar fecha;
- transición incompatible protegida;
- disponibilidad antes/después.

Cobertura crítica faltante:

1. reevaluación B por cambio real de Servicios, Personal preferido e información técnica;
2. integración B real para Servicio sin perfil e historial `REALIZADO` sin Detalle;
3. no bloqueo con el mismo Personal preferido y un Servicio con requisito de equipamiento/capacidad;
4. compatibilidad AND de cola con una solicitud multiservicio;
5. pruebas negativas explícitas para usuarios que sólo poseen `view_clients`, `manage_formulas` o `manage_technical_record`;
6. privacidad pública frente a snapshots, mensajes profesionales, fotografías y metadata interna;
7. contenido completo de todos los eventos de auditoría, especialmente rechazo, información requerida y supersesión desde B;
8. reevaluación ajena y matriz inversa rechazada→aprobar, aunque el control genérico de estado las bloquea en código.

## 17. Frontend global

La corrida global observada produjo 166 pruebas aprobadas, 3 pruebas fallidas en `Operaciones.test.js` y una suite `App.test.js` que no inició.

Clasificación:

- `App.test.js`: fallo preexistente/de toolchain de Jest al resolver `react-router-dom`; el import existía antes de BH-057 y el build productivo resuelve el paquete. No relacionado con BH-057.
- Tres casos de `Operaciones.test.js`: potencial regresión/flakiness del flujo de agenda laboral agregado fuera de BH-057; los fixtures usan fecha UTC mientras el componente filtra fecha local. No toca solicitudes técnicas ni sus rutas.
- Suites BH-057 y controles de navegación: sin fallos relacionados.

Estos fallos globales no bloquean BH-057 por sí mismos. Los blockers de cierre son los tres declarados en el veredicto.

## 18. Deuda no bloqueante

- La cola filtra compatibilidad en Python después de consultar los casos `EN_REVISION`; es correcta para privacidad de respuesta, pero puede optimizarse si crece el volumen.
- `SUPERADA` y `VENCIDA` existen como estados de solicitud, aunque la supersesión ordinaria ocurre sobre la evaluación y no mueve la solicitud vigente a `SUPERADA`.
- El DTO declara `sla: null` porque todavía no existe política operativa de SLA.
- Los warnings de Browserslist/ESLint del build pertenecen a archivos legacy y no afectan el flujo técnico.

## Blockers reales

1. Renderizar en la UI revisora la evidencia estructurada/antecedentes necesarios que ya entrega el DTO.
2. Completar la trazabilidad inmutable de decisiones: enlazar el evento a `DecisionRevisionTecnica` y preservar de forma auditada motivo, policy/version y transición completa sin copiar evidencia técnica sensible.
3. Agregar las pruebas B críticas enumeradas en la sección 16 para demostrar los escenarios obligatorios de reevaluación, fail-closed integrado, no bloqueo exacto, privacidad y separación de permisos.

BH-057 = NO CERRABLE
