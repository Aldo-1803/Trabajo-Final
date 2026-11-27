# Corrección de blockers BH-057 B

Fecha: 2026-10-25  
Alcance: exclusivamente los tres blockers de
`AUDITORIA_CIERRE_BH057.md`. No se implementó BH-058 ni se modificaron HOLD,
pagos, Mercado Pago, el motor de riesgo, ownership, locking o elegibilidad.

## Resultado

Los tres blockers quedaron corregidos y cubiertos por pruebas automatizadas.

## B1 — Evidencia renderizada y privacidad

### DTO revisor

`TechnicalBookingRequestReviewSerializer` entrega vistas sanitizadas y
explícitas de:

- Servicios solicitados;
- fecha y hora preferidas;
- último diagnóstico relevante;
- fecha, antigüedad, procedencia y completitud del diagnóstico;
- antecedentes de Servicios con nombre, fecha, hora y familia cuando existen;
- intervalos calculados con origen/destino, mínimo, transcurrido y fecha mínima;
- datos faltantes;
- rule codes;
- fecha mínima recomendada;
- mensajes profesionales seguros.

Los datos se extraen de la evaluación vigente mediante listas permitidas. No
se serializan snapshots crudos, fórmulas, fotografías, observaciones clínicas
libres ni notas internas.

### UI revisora

`frontend/src/pages/session/RevisionTecnica.js` presenta secciones separadas
para Servicios, diagnóstico, antecedentes, intervalos, reglas/faltantes y
mensajes profesionales. También presenta estados vacíos seguros cuando no hay
diagnóstico, antecedentes, intervalos, faltantes o mensajes.

La UI no calcula outcomes ni reglas; sólo representa el DTO autorizado.

### Pruebas frontend

`RevisionTecnica.test.js` cubre explícitamente:

- diagnóstico, antigüedad y procedencia;
- Servicio previo y fecha;
- intervalo calculado;
- faltantes, rule codes, mensajes y fecha mínima;
- Servicios y fecha solicitados;
- ausencia de fórmula, notas internas, fotografía y snapshot no autorizado;
- caso sin antecedentes ni diagnóstico;
- acciones de aprobar y solicitar información.

## B2 — Inmutabilidad y trazabilidad de decisiones

### Evidencia persistida

`DecisionRevisionTecnica` conserva explícitamente:

- `id` como `decision_id`;
- `solicitud_id`;
- `evaluacion_id`;
- `policy_version`;
- actor;
- acción;
- motivo interno;
- mensaje seguro al Cliente cuando corresponde;
- faltantes y fecha recomendada estructurados;
- `estado_anterior`;
- `estado_nuevo`;
- `created_at`.

La migración `0026_immutable_technical_review_decisions.py` agrega los campos,
completa decisiones existentes desde su evaluación/acción y finalmente los
deja no nulos.

### Protección de inmutabilidad

Después de la creación se bloquean:

- `save()` sobre una instancia existente;
- `QuerySet.update()`;
- `_base_manager.update()`;
- `_default_manager.update()`;
- `bulk_update()`;
- `bulk_create()`, incluido `update_conflicts`;
- `update_or_create()`;
- `delete()` de instancia y queryset.

La creación individual inicial por el servicio auditado sigue permitida.

### Eventos auditables

Los eventos:

- `TECHNICAL_REVIEW_APPROVED`;
- `TECHNICAL_REVIEW_REJECTED`;
- `TECHNICAL_REVIEW_INFORMATION_REQUESTED`;
- `TECHNICAL_REVIEW_DATE_RECOMMENDED`;

incluyen `decision_id`, solicitud, evaluación, versión de policy, acción,
motivo o referencia segura, mensaje seguro cuando corresponde, estado
anterior/nuevo y timestamp de la decisión. El actor y timestamp del evento
permanecen además en `Auditoria`.

No se copian snapshots, fotografías ni evidencia clínica completa.

### Idempotencia

Una repetición exacta por el mismo actor/evaluación devuelve la decisión
existente, sin crear otra fila ni otro evento. Una decisión incompatible
posterior continúa devolviendo conflicto por transición inválida bajo lock.

## B3 — Matriz de cobertura agregada

Se agregó
`gestion/tests/test_technical_booking_blockers.py` con **18 cuerpos de prueba
independientes**:

| Área | Cobertura agregada |
|---|---|
| Reevaluación | cambio de Servicios, fecha, Personal preferido e información técnica |
| Supersesión | nueva evaluación, vínculo `superseded_by`, dos intentos, evidencia vieja inmutable y estado recalculado |
| Warning | warning de evaluación superada rechazado |
| Fail-closed B | Servicio sin perfil, perfil PENDIENTE y Turno REALIZADO sin Detalle → revisión |
| Configuración inválida | error público seguro y rollback de la solicitud |
| No bloqueo exacto | mismo Cliente/Servicios/fecha/hora/Personal y requisito de equipamiento |
| Ownership/privacidad | sólo propias, 404 ajeno y DTO público sin evidencia interna |
| DTO revisor | diagnóstico, antecedentes e intervalos estructurados y sanitizados |
| Cola multiservicio | compatibilidad AND con todos los Servicios |
| Permisos | review sin skill, skill sin review, permisos técnicos no equivalentes, admin sin skill e individual válido |
| Historial técnico | `view_clients` no concede diagnóstico de otro Cliente |
| Decisión | creación y trazabilidad completa |
| Inmutabilidad | todas las rutas ORM relevantes de mutación/borrado |
| Idempotencia | una decisión y un evento ante retry exacto |
| Auditoría | referencias completas para las cuatro acciones |

## Fail-closed de integración

La capa B transforma `TechnicalRiskConfigurationError` en un error de dominio
seguro. Al estar dentro de `transaction.atomic`, una configuración inválida no
deja una solicitud parcial. No se alteró `evaluate_booking_risk()` ni sus
políticas.

## Fronteras preservadas

No se modificaron:

- `EvaluacionRiesgoTecnico` ni su protocolo de supersesión;
- reglas o políticas del evaluador;
- `ACTIVE_TURNO_STATES`;
- `Turno.SUGERIDO`;
- `Turno.alerta_daño_capilar`;
- ownership, locking o elegibilidad;
- HOLD, `PaymentIntent`, Pago, Mercado Pago o webhooks.

## Validación final

Backend:

- BH-057 A: **54/54 OK**;
- BH-057 B original: **20/20 OK**;
- B.1 blockers: **18/18 OK**;
- BH-056/skills, Diagnóstico y Turnos: **133/133 OK**;
- roles y `/me/`: **31/31 OK**;
- total de la matriz solicitada: **256/256 OK**.

Frontend relevante:

- `RevisionTecnica`, `SolicitudesTecnicas`, navegación, Header, sesión y
  guards: **75/75 OK**.

Validaciones estáticas:

- `python manage.py check`: OK;
- `python manage.py makemigrations --check --dry-run`: sin cambios;
- `python -m compileall gestion usuarios`: OK;
- `git diff --check`: OK, únicamente avisos informativos CRLF/LF del árbol.

Los fallos globales ya documentados de `Operaciones.test.js` y `App.test.js`
no fueron ejecutados como parte de esta corrección y ninguno de esos archivos
fue modificado por este trabajo.

BH-057 B BLOCKERS = CORREGIDOS
