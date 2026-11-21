# Flujos profesionales — Incremento 4: interfaz profesional React integrada

**Fecha:** 2026-11-19

**Baseline de partida:** `53cb9fbadf901cbe24d7f535e71bd649c2bf7e1b`

**Rama:** `save/work-in-progress`

**Estado:** validado para publicación

## 1. Objetivo y alcance

Este incremento publica el recorrido profesional React desde un Turno asignado
hasta su finalización idempotente. Integra los contratos reales de los
Incrementos 0–3 sin duplicar sus reglas en la interfaz:

1. contexto autorizado del Turno y perfil capilar;
2. evaluación profesional y corrección trazable;
3. ficha técnica independiente por `DetalleTurno`;
4. preflight informativo de finalización;
5. confirmación idempotente y resultado persistido;
6. resumen seguro de automatizaciones.

No implementa BH-063, BH-064, autoevaluaciones periódicas, nuevas reglas
capilares, prioridad multiservicio, pagos, consumo de stock ni reprocesamiento
administrativo. Tampoco modifica las políticas de los Incrementos 0–3.

## 2. Rutas y superficies publicadas

La ruta nueva es:

```text
/turnos/:turnoId/trabajo-tecnico
```

Se integra desde:

- **Mi agenda laboral**, para el Turno cuyo `profesional` coincide con el perfil
  Personal de la sesión;
- **Operaciones del día**, bajo la misma comprobación de asignación;
- acceso directo seguro por URL, protegido antes de montar la pantalla.

`ProtectedRoute` exige simultáneamente:

- perfil `personal` activo;
- capability `technical_record.read_global`.

La capability no concede por sí sola acceso al ID solicitado. El backend vuelve
a validar que el Turno esté asignado al actor mediante
`can_read_turn_context()`. Un 403/404 no monta datos del Cliente ni dispara
mutaciones.

Componentes y utilidades principales:

| Archivo | Responsabilidad |
|---|---|
| `frontend/src/pages/session/TrabajoTecnicoTurno.js` | recorrido completo, formularios, preflight, confirmación y resultado |
| `frontend/src/api/professionalWorkflowApi.js` | cliente semántico sobre el Axios global |
| `frontend/src/utils/turnoFinalizationKey.js` | identidad estable del comando de finalización en `sessionStorage` |
| `frontend/src/routes/index.js` | ruta protegida |
| `MiAgendaLaboral.js` / `Operaciones.js` | entradas condicionadas por capability y ownership visible |

No se publican los componentes legacy ni su instancia Axios aislada.

## 3. Proyección backend mínima

Se amplía el contrato de lectura ya existente, sin crear un CRUD ni una lectura
global nueva:

```text
GET /api/gestion/fichas-tecnicas/contexto-turno/?turno_id={id}
```

La respuesta incorpora únicamente el contexto necesario:

- Turno, fecha, hora, estado y profesional asignado;
- Cliente vinculado;
- perfil vigente por dimensión, con procedencia, fuente y fecha disponibles;
- evaluaciones históricas permitidas y correcciones trazables;
- detalles, Servicios, política técnica, ficha, completitud, versión e historial;
- catálogos mínimos para los formularios;
- flags de acceso efectivos;
- preflight con bloqueos, advertencias y evidencia por detalle;
- resultado persistido de finalización, si ya existe.

Las evaluaciones se proyectan con campos capilares, observaciones,
recomendaciones, resultado automático, estado, fecha y procedencia. Se excluyen
email, IDs internos de regla, autor y otros campos que la pantalla no necesita.

Sin `service_formula.manage` se retiran:

- fórmula aplicada;
- fórmula estándar de catálogo;
- valores de fórmula en correcciones históricas.

La pantalla nunca muestra snapshots de reglas, `parametros_snapshot`, claves
lógicas del ledger ni fórmulas no autorizadas. De `effects` sólo representa los
tipos, estados y advertencias del `summary` autorizado.

## 4. Perfil y evaluaciones profesionales

La pantalla distingue expresamente estas procedencias:

- declarado por el Cliente;
- observación profesional;
- resultado automático post-servicio;
- procedencia desconocida.

Un perfil puede estar incompleto y no obliga a crear una evaluación nueva. La
nueva evaluación permite seleccionar sólo las dimensiones realmente observadas
y explica que esos campos se promoverán al perfil vigente. Consume:

```text
POST /api/gestion/diagnosticos-capilares/
```

La corrección consume exclusivamente la acción semántica:

```text
POST /api/gestion/diagnosticos-capilares/{id}/corregir/
```

Exige un motivo de al menos diez caracteres y sólo ofrece campos evaluados en el
registro original. La evaluación y sus correcciones anteriores permanecen en el
historial. No se usa `PUT/PATCH` genérico y no se presenta un resultado calculado
como confirmación profesional.

La escritura requiere la capability `diagnosis.create` en sesión y la autoridad
backend real. Una revocación 403 oculta nuevas acciones, actualiza la sesión y
no reenvía el comando.

## 5. Fichas técnicas por Servicio

Cada tarjeta corresponde a un `DetalleTurno`; un Turno multiservicio mantiene
tarjetas, versiones y estados independientes. Se consumen:

```text
POST /api/gestion/fichas-tecnicas/
POST /api/gestion/fichas-tecnicas/{id}/guardar-borrador/
POST /api/gestion/fichas-tecnicas/{id}/completar/
POST /api/gestion/fichas-tecnicas/{id}/corregir/
```

La UI respeta la proyección de `PerfilTecnicoServicio`:

- `BORRADOR` y `COMPLETA`;
- campos condicionales configurados;
- modo de fórmula `NO_APLICA`, `OPCIONAL` o `REQUERIDA`;
- fórmula estándar separada de la aplicada;
- versión optimista en cada mutación;
- motivo obligatorio para una corrección;
- restricciones por estado del Turno y de la ficha;
- historial de correcciones autorizado.

No ofrece DELETE, edición genérica ni corrección posfinalización fuera de la
política actual. Un 409 recarga la versión vigente y nunca sobrescribe datos en
silencio. Una política pendiente se muestra como advertencia y no genera campos
obligatorios inventados.

## 6. Preflight de finalización

`inspect_finalization_record_status()` separa la inspección de sólo lectura de
la validación que ya usa `finalize_turno()`. No cambia completitud ni reglas de
dominio.

El preflight proyecta:

- transición permitida del Turno;
- autoridad efectiva para finalizar;
- fichas requeridas incompletas;
- evidencia técnica por `DetalleTurno`;
- políticas pendientes como advertencias no bloqueantes;
- finalización ya persistida.

No convierte pagos ni stock en bloqueos. El resultado es informativo: el
backend vuelve a bloquear y validar Turno, detalles y fichas dentro de la
transacción de finalización.

## 7. Confirmación e idempotencia

La acción final conserva el contrato del Incremento 0:

```text
POST /api/gestion/turnos/{id}/finalizar_turno/
Idempotency-Key: <identidad estable>
```

Política React:

1. se exige una confirmación explícita;
2. una referencia en memoria bloquea doble clic y llamadas simultáneas;
3. la clave se crea una vez por Turno y se conserva en `sessionStorage`;
4. no existe retry automático de mutaciones;
5. ante timeout/red se ofrece retry manual con la misma clave;
6. la clave sólo se elimina después de una respuesta exitosa;
7. `changed=false` se muestra como recuperación del resultado persistido;
8. una falla de red al recargar contexto no oculta el resultado ya recibido.

Después de finalizar se muestra el estado actualizado del Turno y
`effects.summary`. Los estados `COMPLETADO`, `OMITIDO`, `PENDIENTE` y `FALLIDO`
se traducen a mensajes comprensibles. En particular, un diagnóstico automático
omitido nunca se presenta como generado.

## 8. Permisos y tratamiento HTTP

La autoridad usa `SessionContext`, permisos efectivos, capabilities,
`ProtectedRoute` y validación backend. No usa `is_staff`, `is_superuser`,
BusinessRole nominal ni grants reconstruidos en React.

| Condición | Tratamiento |
|---|---|
| `401` | el interceptor global aplica la política de sesión; la mutación no se repite |
| `403` | se actualiza sesión/autoridad y se deshabilita la acción; sin retry |
| `404` de contexto | mensaje seguro equivalente a ausencia de acceso, sin proyección |
| `409` de ficha | mensaje de concurrencia y recarga de versión, sin sobrescritura |
| `409` de finalización | informa cambio/conflicto y actualiza contexto, sin repetir POST |
| `400/422` | muestra validación devuelta por el contrato semántico |
| timeout/red | conserva el contexto; sólo finalización ofrece retry manual con la misma clave |
| `5xx` | mensaje temporal seguro; sin retry automático de mutaciones |

## 9. Pruebas

### 9.1 Backend

`gestion/tests/test_professional_workflow_context_increment4.py` agrega 10
pruebas PostgreSQL para:

- ownership y denegación sin datos;
- capability ausente y revocada;
- perfil completo/incompleto y procedencia;
- evaluaciones y correcciones históricas;
- ocultamiento de fórmulas y de campos innecesarios;
- ficha requerida y preflight listo;
- política pendiente no bloqueante;
- resultado persistido seguro;
- lectura sin mutaciones.

La regresión focal conjunta de los Incrementos 0–4 pasó **81/81**.

### 9.2 Frontend

Los 30 escenarios solicitados están cubiertos entre:

- `TrabajoTecnicoTurno.test.js`;
- `MiAgendaLaboral.test.js`;
- `Operaciones.test.js`;
- `ProtectedRoute.test.js`;
- `professionalWorkflowApi.test.js`;
- `turnoFinalizationKey.test.js`.

Incluyen entrada autorizada, ID ajeno, capability ausente/revocada, perfil,
evaluaciones y correcciones, multiservicio, estados de ficha, campos
condicionales, fórmula, 409 optimista, preflight, confirmación, doble clic,
timeout, misma clave, `changed=false`, 401/403/409, efectos, datos sensibles,
ausencia de mutaciones no autorizadas y ausencia de bucles de navegación.

| Suite / bloque | Resultado |
|---|---:|
| Frontend focal del recorrido, rutas y entradas | 122/122 |
| Frontend completo | 438/438 |
| Build React | aprobado |
| Backend focal Incrementos 0–4 | 81/81 |
| B1 — roles, usuarios y Personal | 416/416 |
| B2 — diagnóstico, ficha y rutinas | 216/216 |
| B3 — agenda, Turnos y automatizaciones | 192/192 |
| B4 — catálogos, inventario y órdenes | 79/79 |
| B5 — Caja, pagos e incidencias | 170/170 |
| B6 — Django Admin y auditoría | 43/43 |
| B7 — concurrencia PostgreSQL | 69/69 |

La matriz B1–B7 ejecutó **1.185/1.185 pruebas backend únicas**. La primera
ejecución local paralela de B1 agotó el timeout del harness sin informar un
fallo funcional; su repetición aislada con base nueva pasó 416/416. El build
conserva warnings preexistentes en otros archivos y no agrega warnings propios
del incremento.

## 10. Cambios de CI, migraciones y compatibilidad

El workflow incorpora las 10 pruebas nuevas a B2, que pasa de 206 a 216, y
actualiza el total frontend a 438. B1, B3–B7 no cambian sus labels ni conteos.

No se crea migración. `check` y `makemigrations --check --dry-run` pasan. El
helper de preflight reutiliza exactamente la evaluación de fichas que usa la
finalización, y `finalization_record_status()` mantiene su excepción y contrato
previos.

## 11. Riesgos y funciones fuera de alcance

Permanecen fuera de este incremento:

1. clasificación/aprobación operativa de perfiles técnicos todavía pendientes;
2. política de corrección de fichas después de finalizar;
3. combinación de impactos capilares en Turnos multiservicio;
4. autoevaluaciones periódicas del Cliente;
5. reprocesamiento administrativo de efectos;
6. pagos, facturación, prioridad multiservicio y consumo automático de stock;
7. cualquier trabajo de Incremento 5.

## 12. Publicación

El cambio se publica en `save/work-in-progress` con el mensaje:

```text
feat(ui): integrar recorrido tecnico profesional
```

No se inicia el Incremento 5.
