# Auditoría final de cierre BH-057

Fecha: 2026-10-25  
Alcance: verificación final, en modo sólo lectura, de los tres blockers
corregidos de BH-057 B. No se modificó implementación, no se reabrió BH-057 A
y no se inició BH-058.

## Veredicto ejecutivo

Los tres blockers documentados en `AUDITORIA_CIERRE_BH057.md` están cerrados:

| Blocker | Resultado |
|---|---|
| B1 — evidencia estructurada y segura en UI revisora | **CERRADO** |
| B2a — inmutabilidad real de `DecisionRevisionTecnica` | **CERRADO** |
| B2b — trazabilidad histórica de decisiones y auditoría | **CERRADO** |
| B3 — cobertura B.1 obligatoria | **CERRADO** |

## 1. B1 — UI revisora

### Evidencia renderizada

`frontend/src/pages/session/RevisionTecnica.js` representa explícitamente:

- Servicios solicitados;
- fecha y hora preferidas;
- último diagnóstico relevante;
- fecha, antigüedad, procedencia y completitud del diagnóstico;
- antecedentes de Servicios relevantes;
- fecha, hora y familia del Servicio previo cuando están disponibles;
- intervalos calculados, incluyendo origen/destino, mínimo, días
  transcurridos o separación y fecha mínima del intervalo;
- datos faltantes;
- rule codes disparados;
- fecha mínima recomendada;
- mensajes profesionales permitidos.

La pantalla también presenta estados vacíos seguros para diagnóstico,
antecedentes, intervalos, datos faltantes, reglas y mensajes.

### Sanitización y privacidad

`TechnicalBookingRequestReviewSerializer` no entrega snapshots completos. Usa
listas permitidas independientes para:

- `datos_faltantes`;
- `diagnostico`;
- `antecedentes`;
- `intervalos`.

El DTO revisor no incluye fórmulas, notas internas, fotografías,
observaciones clínicas libres, `input_snapshot` ni `result_snapshot`. La UI,
a su vez, accede sólo a propiedades expresamente declaradas en ese DTO y no
renderiza objetos genéricos ni JSON crudo.

La prueba frontend inyecta deliberadamente `formula`, `notas_internas`,
`fotografia`, `observaciones` y `snapshot_json` en el fixture y confirma que
ninguno aparece en pantalla. La prueba backend hace la misma comprobación
sobre el DTO real de la cola.

**B1 = CERRADO**

## 2. B2a — Inmutabilidad de DecisionRevisionTecnica

`DecisionRevisionTecnica` usa
`ImmutableTechnicalReviewDecisionQuerySet` a través de un manager configurado
simultáneamente como `_base_manager` y `_default_manager`.

Protecciones verificadas:

| Ruta ORM | Resultado |
|---|---|
| creación inicial individual por el servicio | Permitida |
| `save()` sobre instancia existente | Bloqueada con `ValidationError` |
| `QuerySet.update()` | Bloqueada |
| `_base_manager.update()` | Bloqueada |
| `_default_manager.update()` | Bloqueada |
| `bulk_update()` | Bloqueada |
| `bulk_create()` | Bloqueada por diseño |
| `bulk_create(update_conflicts=True)` | Bloqueada |
| `update_or_create()` | Bloqueada; no puede modificar existente |
| `delete()` de instancia | Bloqueada |
| `QuerySet.delete()` | Bloqueada |

La prueba vuelve a consultar la fila después de todos los intentos y confirma
que motivo, policy y evaluación permanecen intactos.

**B2a = CERRADO**

## 3. B2b — Trazabilidad de decisiones

### Evidencia persistida

Cada `DecisionRevisionTecnica` conserva en columnas propias:

- `id`, usado como `decision_id`;
- `solicitud_id`;
- `evaluacion_id`;
- `policy_version`;
- actor;
- acción;
- `motivo_interno`;
- `mensaje_cliente` cuando corresponde;
- datos faltantes o fecha recomendada cuando corresponden;
- `estado_anterior`;
- `estado_nuevo`;
- `created_at`.

La migración `0026_immutable_technical_review_decisions.py` completa policy y
transición en las decisiones preexistentes antes de volver obligatorias esas
columnas.

### Evento de auditoría

Los eventos de aprobar, rechazar, solicitar información y recomendar otra
fecha contienen:

- `decision_id`;
- `solicitud_id`;
- `evaluation_id`;
- `policy_version`;
- acción;
- motivo;
- mensaje seguro al Cliente;
- codes faltantes o fecha recomendada como referencia segura;
- estado anterior y nuevo;
- timestamp de creación de la decisión.

El actor y el timestamp del evento están además en `Auditoria.usuario` y
`Auditoria.fecha_hora`. No se copian snapshots, fotografías ni evidencia
clínica completa.

La reconstrucción no depende del estado actual de
`SolicitudTecnicaReserva`: evaluación, policy, actor, acción, transición y
contenido decisorio permanecen en la fila inmutable y el evento se enlaza por
`decision_id`.

**B2b = CERRADO**

## 4. Idempotencia, transición y locking

El servicio mantiene `transaction.atomic` y obtiene la solicitud mediante
`select_for_update()` antes de verificar o crear una decisión.

Se confirmó que:

- un retry exacto encuentra la decisión de la misma evaluación y actor;
- devuelve la fila existente;
- la cantidad de `DecisionRevisionTecnica` permanece en uno;
- la cantidad del evento de auditoría permanece sin cambios;
- una decisión incompatible posterior recibe HTTP 409;
- el estado se vuelve a comprobar después de adquirir el lock.

No se confía en la UI para exclusión mutua.

## 5. B3 — Revisión cualitativa de las 18 pruebas B.1

`gestion/tests/test_technical_booking_blockers.py` contiene 18 cuerpos de
prueba únicos. La cobertura no se evaluó únicamente por cantidad:

| Escenario obligatorio | Evidencia explícita |
|---|---|
| Reevaluación por Servicios | cambia `servicio_ids`, crea evaluación nueva, supersede la anterior, conserva snapshot y rechaza warning viejo |
| Reevaluación por fecha | cambia fecha, supersede y recalcula a `RECHAZADA_TECNICAMENTE` |
| Reevaluación por Personal preferido | cambia Personal, supersede y refleja el nuevo Personal en DTO |
| Reevaluación por dato técnico | usa `informacion_tecnica_actualizada`, supersede y recalcula |
| Fail-closed sin perfil | flujo real termina en `EN_REVISION`, nunca APTO silencioso |
| Fail-closed perfil PENDIENTE | flujo real termina en `EN_REVISION` |
| Historial inconsistente | Turno REALIZADO sin Detalle termina en `EN_REVISION` |
| Configuración inválida | respuesta pública segura y rollback completo de la solicitud |
| No bloqueo exacto | dos solicitudes iguales con mismo Cliente, Servicio, fecha/hora y Personal preferido |
| Equipamiento/agenda | disponibilidad antes/después, equipamiento y requisito intactos, cero bloqueos y cero Turnos |
| Privacidad Cliente | DTO público sin snapshots/evidencia interna; objeto ajeno 404 y listado ajeno vacío |
| Privacidad Revisor | DTO estructurado sanitizado y cola filtrada |
| Compatibilidad multiservicio | exige compatibilidad AND con todos los Servicios |
| `view_clients` | no concede historial técnico de otro Cliente |
| Separación de permisos | review sin DIAGNOSTICO, DIAGNOSTICO sin review, `manage_technical_record` y `manage_formulas` no revisan |
| ADMIN sin skill | cola y decisión responden 403 |
| Permiso individual + skill | accede a cola y decide correctamente |
| Inmutabilidad | cubre todas las rutas ORM enumeradas en B2a |
| Idempotencia/auditoría | no duplica fila/evento y valida referencias de las cuatro acciones |

Los tests de reevaluación usan resultados controlados para aislar la
orquestación B; los casos fail-closed ejecutan el evaluador real. Esta
separación prueba tanto la lógica de integración como los contratos del motor
sin rediseñar BH-057 A.

## 6. No bloqueo

La prueba exacta crea dos solicitudes con:

- el mismo Cliente;
- el mismo Servicio;
- la misma fecha y hora;
- el mismo Personal preferido;
- un Servicio con requisito obligatorio de equipamiento.

Resultado confirmado:

- ambas solicitudes coexisten;
- disponibilidad verdadera antes y después;
- cero `Turno` creados;
- cero `BloqueoAgenda` creados;
- cantidad y estado del equipamiento sin cambios;
- requisito de equipamiento intacto.

`SolicitudTecnicaReserva` no participa en las consultas de conflictos de
Turnos, Personal o capacidad de equipamiento. No existe `SlotHold` en este
incremento ni referencia a HOLD en el servicio o migraciones BH-057.

## 7. Frontera BH-058

La búsqueda explícita en:

- `technical_booking_request_services.py`;
- migraciones `0025` y `0026`;
- DTOs y UI revisora;
- pruebas B.1;
- cambios de `models.py` y `serializers.py`;

no encontró implementación nueva de:

- `SlotHold`;
- `PaymentIntent`;
- Mercado Pago;
- webhooks financieros;
- Pago o seña dentro de BH-057;
- confirmación financiera.

Las coincidencias globales de `Pago`, Mercado Pago y seña permanecen en los
modelos y servicios legacy preexistentes. No están enlazadas al agregado ni al
servicio de `SolicitudTecnicaReserva`.

## 8. Regresión ejecutada

Backend:

| Suite | Resultado |
|---|---:|
| BH-057 A | **54/54 OK** |
| BH-057 B original | **20/20 OK** |
| BH-057 B.1 | **18/18 OK** |
| BH-056/skills, Diagnóstico y Turnos | **133/133 OK** |
| roles y `/me/` | **31/31 OK** |
| Total de la matriz solicitada | **256/256 OK** |

Los 20 resultados de B original conservan la herencia ya documentada; las 18
pruebas B.1 son cuerpos independientes y fueron revisadas individualmente.

Frontend relevante:

- `RevisionTecnica`;
- `SolicitudesTecnicas`;
- navegación;
- Header;
- contexto de sesión;
- routing/guards.

Resultado: **75/75 OK**.

Validaciones adicionales:

- `python manage.py check`: **OK**, cero issues;
- `python manage.py makemigrations --check --dry-run`: **OK**, sin cambios;
- `python -m compileall gestion usuarios`: **OK**;
- `git diff --check`: **OK**, sólo avisos informativos CRLF/LF ya conocidos.

Los fallos globales previamente documentados de `Operaciones.test.js` y
`App.test.js` no se mezclaron con esta verificación y sus archivos no fueron
modificados.

## Blockers reales restantes

Ninguno dentro de los tres blockers verificados de BH-057 B.

BH-057 = LISTO PARA CERRAR
