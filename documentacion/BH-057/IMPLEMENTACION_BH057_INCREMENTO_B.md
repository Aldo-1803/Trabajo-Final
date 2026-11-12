# Implementación BH-057 — Incremento B

## Resultado

Se implementó una solicitud técnica previa, productiva y completamente separada de `Turno`. La creación consume `evaluate_booking_risk()`, conserva evaluaciones inmutables por intento y deriva el estado técnico sin reservar agenda.

## Modelo

La migración `gestion/0025_solicitudtecnicareserva_decisionrevisiontecnica_and_more.py` incorpora:

- `SolicitudTecnicaReserva`: Cliente propietario, fecha/hora preferida, Personal preferido opcional, estado, intento, evaluación vigente, fecha recomendada y timestamps.
- `SolicitudTecnicaServicio`: relación explícita multiservicio, orden y snapshot del nombre.
- `EvaluacionSolicitudTecnica`: vínculo inmutable entre cada intento y su `EvaluacionRiesgoTecnico`.
- `AceptacionAdvertenciaTecnica`: evaluación, versión de política, codes/textos, actor y timestamp.
- `DecisionRevisionTecnica`: evidencia histórica inmutable con solicitud,
  evaluación, versión de política, actor, acción, motivo, mensaje seguro,
  faltantes estructurados, fecha recomendada, estado anterior/nuevo y timestamp.
- La migración `0026_immutable_technical_review_decisions.py` completa esos
  campos en decisiones existentes y los deja obligatorios.

Estados disponibles:

- `EVALUANDO`
- `ADVERTENCIA_PENDIENTE`
- `APROBADA_TECNICAMENTE`
- `EN_REVISION`
- `INFORMACION_REQUERIDA`
- `RECHAZADA_TECNICAMENTE`
- `SUPERADA`
- `VENCIDA`

No se agregaron estados financieros.

## Integración con el evaluador

`create_technical_booking_request()` valida Cliente, Servicios, fecha y Personal preferido; crea la intención y sus relaciones; ejecuta `evaluate_booking_risk()`; persiste la evaluación auditada; la vincula como vigente y deriva:

| Outcome | Estado de solicitud |
|---|---|
| `APTO` | `APROBADA_TECNICAMENTE` |
| `ADVERTENCIA` | `ADVERTENCIA_PENDIENTE` |
| `REQUIERE_REVISION` | `EN_REVISION` |
| `NO_APTO` | `RECHAZADA_TECNICAMENTE` |

Una prueba de integración sin mocks confirma el recorrido real evaluador → persistencia → solicitud para `APTO`.

## Advertencias

`accept_technical_warning()`:

- exige al Cliente propietario;
- bloquea la solicitud con `select_for_update()`;
- sólo acepta la evaluación vigente con outcome `ADVERTENCIA`;
- rechaza evidencia superada;
- registra versión, codes, mensajes públicos, actor y fecha;
- es idempotente ante la repetición exacta;
- cambia a `APROBADA_TECNICAMENTE` sin crear Turno ni HOLD.

## Reevaluación y política

`reevaluate_technical_booking_request()` admite cambios de Servicios, fecha, hora, Personal preferido o información técnica relevante. Cada cambio:

1. incrementa el intento;
2. crea otra evaluación;
3. usa `supersede_technical_risk_evaluation()`;
4. conserva intactos los snapshots anteriores;
5. recalcula el estado.

La propiedad del Cliente no puede cambiar desde la API. No se implementó creación staff para terceros porque el flujo actual no la requiere.

Una reevaluación conserva por defecto la versión de política de la evaluación vigente. Sólo un llamado interno explícito puede indicar otra versión. Publicar una política no ejecuta reevaluaciones ni reinterpreta solicitudes históricas.

## API y privacidad

Router: `/api/gestion/solicitudes-tecnicas/`.

- `POST reservar/`: crea para `request.user.cliente`; rechaza `cliente`/`cliente_id` enviados por el consumidor.
- `GET /` y `GET /{id}/`: sólo solicitudes del Cliente autenticado.
- `POST /{id}/aceptar-advertencia/`.
- `POST /{id}/reevaluar/`.
- `GET cola/`: sólo casos compatibles para el revisor.
- `POST /{id}/revisar/`.

El DTO público contiene estado, outcome público, Servicios, advertencias, fecha mínima, faltantes sanitizados, alternativa recomendada y mensaje seguro. No contiene notas internas, fórmulas, parámetros de reglas ni evidencia histórica interna.

El DTO revisor contiene Cliente básico, Servicios, preferencia, outcome, rule
codes, faltantes, diagnóstico sanitizado con antigüedad/procedencia,
antecedentes de Servicios, intervalos calculados, fecha mínima y mensajes
profesionales. Cada estructura usa una lista permitida explícita; no expone
snapshots crudos, fórmulas, fotografías, observaciones ni notas internas.

`manage_technical_record`, `manage_formulas` y `view_clients` no conceden acceso a la cola por sí mismos.

## Revisor y cola

La elegibilidad exige simultáneamente:

- Usuario activo;
- Personal activo vinculado;
- permiso efectivo `gestion.review_technical_booking`;
- asignación activa de la habilidad activa `DIAGNOSTICO`;
- compatibilidad AND de `service_skill_policy(servicios)`.

No se consulta `BusinessRole`, `Personal.rol` ni `is_staff` como autoridad. Un administrador sin `DIAGNOSTICO` recibe 403. El permiso individual funciona.

## Decisiones

Las acciones v1 son:

- `APROBAR`: exige motivo y pasa a `APROBADA_TECNICAMENTE`.
- `RECHAZAR`: exige motivo interno y mensaje seguro; pasa a `RECHAZADA_TECNICAMENTE`.
- `SOLICITAR_INFORMACION`: exige codes permitidos y pasa a `INFORMACION_REQUERIDA`.
- `RECOMENDAR_OTRA_FECHA`: guarda la fecha y mantiene `EN_REVISION`; sólo un cambio posterior del Cliente provoca reevaluación.

Todas verifican elegibilidad, bloquean la solicitud, validan transición, son idempotentes para la repetición exacta y auditan. El lock y la validación de estado impiden decisiones incompatibles de dos revisores.

Una decisión persistida no puede cambiarse ni eliminarse por `save()`,
`update()`, managers base/default, `bulk_update()`, `bulk_create()`/upsert,
`update_or_create()` o `delete()`. La creación inicial individual continúa
exclusivamente por el servicio de revisión auditado.

## Auditoría

Se registran sin copiar datos sensibles completos:

- `TECHNICAL_ASSESSMENT_CREATED`
- `TECHNICAL_WARNING_ACCEPTED`
- `TECHNICAL_REVIEW_REQUIRED`
- `TECHNICAL_REVIEW_APPROVED`
- `TECHNICAL_REVIEW_REJECTED`
- `TECHNICAL_REVIEW_INFORMATION_REQUESTED`
- `TECHNICAL_REVIEW_DATE_RECOMMENDED`
- `TECHNICAL_ASSESSMENT_SUPERSEDED`

Los cuatro eventos de decisión conservan `decision_id`, `solicitud_id`,
`evaluation_id`, `policy_version`, actor, acción, motivo o referencia segura,
mensaje seguro cuando corresponde, estado anterior/nuevo y timestamp de la
decisión. Por lo tanto, la reconstrucción histórica no depende del estado
mutable de la solicitud.

## Frontend

- Cliente: `/solicitudes-tecnicas`, con creación multiservicio, estados, advertencia, fecha mínima, faltantes, rechazo seguro y reevaluación de fecha recomendada.
- Revisor: `/revision-tecnica`, con cola, Servicios y fecha solicitados,
  diagnóstico relevante, antigüedad/procedencia, antecedentes de Servicios,
  intervalos, faltantes, rules, fecha mínima, mensajes profesionales y
  acciones v1.
- La navegación de revisión depende del permiso efectivo y Personal activo; no de un rol de negocio.
- Ambas pantallas indican expresamente que la solicitud todavía no reserva un Turno.

## No bloqueo y frontera BH-058

`SolicitudTecnicaReserva` no se incorporó a `ACTIVE_TURNO_STATES` ni a consultas de disponibilidad. No bloquea Cliente, Personal, equipamiento o slot. Una prueba exacta crea solicitudes con el mismo Cliente, Servicios, fecha/hora y Personal preferido sobre un Servicio con requisito de equipamiento; confirma disponibilidad idéntica, equipamiento intacto, cero conflictos y cero Turnos.

El flujo nuevo no crea ni referencia:

- `Turno` o `Turno.SUGERIDO`;
- `SlotHold`/HOLD;
- `PaymentIntent`;
- Pago o seña;
- Mercado Pago o webhooks.

`ALERTA_DAÑO_CAPILAR` no participa. Los registros y caminos legacy existentes no se retiraron. `APROBADA_TECNICAMENTE` sólo habilita un futuro BH-058.

## Validación ejecutada

Backend, PostgreSQL y entorno virtual del proyecto:

- BH-057 B original: **20/20 OK**.
- Corrección B.1, con 18 cuerpos nuevos independientes: **18/18 OK**.
- BH-057 A: **54/54 OK**.
- BH-056/skills, diagnóstico y Turnos: **133/133 OK**.
- roles y `/me/`: **31/31 OK**.
- Total backend validado en la matriz solicitada: **256/256 OK**.
- `python manage.py check`: **OK**.
- `python manage.py makemigrations --check --dry-run`: **sin cambios**.
- `python -m compileall gestion usuarios`: **OK**.
- `git diff --check`: **OK** (sólo avisos informativos CRLF/LF del árbol preexistente).

Frontend:

- UI, navegación, sesión, header y protección de rutas relevantes: **75/75 OK**.
- Build productivo: **OK**, con warnings preexistentes de ESLint/Browserslist.
- Corrida global: **166 pruebas OK** y 3 fallos fuera del alcance de BH-057 en `Operaciones.test.js` (fecha local de fixtures) más la suite `App.test.js` (resolución Jest de `react-router-dom`); las suites modificadas y el build no presentan fallos.

## Veredicto

**BH-057 B = VALIDADO**
