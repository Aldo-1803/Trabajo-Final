# BH-060 Incremento 2 — Autorización de agenda legacy

## Estado

**BH-060 INCREMENTO 2 = VALIDADO**

- Baseline: `1bd3510` (`fix(bh-060): proteger catalogos y equipamiento`).
- Alcance: lectura de agenda legacy, calendario alternativo y creación de
  bloqueos.
- Fuera de alcance: BH-060 Incremento 3, ficha técnica, fórmulas, rutinas,
  lógica financiera y cambios generales de horarios.

## Superficies revisadas

| Operación | Ruta | Contrato |
| --- | --- | --- |
| Agenda legacy de un Personal | `GET /api/gestion/agenda/general/` | Global con `gestion.view_global_agenda`; propia por ownership y Personal activo |
| Calendario legacy/alternativo | `GET /api/gestion/obtener_disponibilidad_calendario/` | Global con `gestion.view_global_agenda`; propio por ownership y Personal activo |
| Crear bloqueo | `POST /api/gestion/agenda/bloquear/` | `gestion.manage_configuration` y Personal objetivo explícito |
| Agenda global canónica | `GET /api/gestion/turnos/` | Conserva `gestion.view_global_agenda` |
| Agenda laboral canónica | `GET /api/gestion/turnos/mi-agenda-laboral/` | Conserva ownership y Personal activo |
| Slots para reserva | `GET /api/gestion/disponibilidad/` | Conserva lectura pública mínima para reservas |

`obtener_disponibilidad_calendario` se incluyó porque entrega las mismas reglas
laborales y excepciones que la agenda general. Era una ruta `AllowAny` y es el
consumidor actual de `AgendaAdmin` y `ConfiguracionAgendaMasiva`.

## Lectura y ownership

La autoridad global es exclusivamente el permiso Django efectivo
`gestion.view_global_agenda`. No se usa `is_staff` ni el nombre del
BusinessRole.

Un usuario sin ese permiso puede consultar la agenda legacy únicamente cuando:

1. está autenticado y activo;
2. posee un `Personal` vinculado mediante `perfil_profesional`;
3. ese `Personal` está activo;
4. no envía `personal_id`, o envía exactamente su propio identificador.

Modificar `personal_id` para consultar otro Personal devuelve `403`. Un lector
global puede elegir un Personal activo explícito; un identificador inexistente
o inactivo devuelve `404`.

`agenda/general` ya no selecciona implícitamente el primer Personal activo. Si
el actor global no tiene un Personal propio debe indicar `personal_id`. El
calendario alternativo conserva la consulta agregada sin `personal_id` sólo
para actores con `view_global_agenda`, porque ese es el contrato usado por la
pantalla administrativa autorizada.

Para alcance propio, las reglas se limitan al Personal vinculado y los bloqueos
se limitan a los propios más los globales. No se devuelven horarios de terceros.

## Escritura de bloqueos

Se reutiliza `gestion.manage_configuration`, separado de
`gestion.view_global_agenda`, porque un bloqueo modifica la disponibilidad del
salón y pertenece a la configuración operativa. El permiso ya existe, se asigna
por defecto al ADMINISTRADOR y gobierna las pantallas de configuración. Un
permiso de lectura global no autoriza esta mutación.

El comando exige los campos:

- `personal_id`;
- `fecha_inicio`;
- `fecha_fin`;
- `motivo`;
- `bloquea_todo_el_dia`, opcional.

No se conserva el fallback al primer `rol='colorista'`: no existe una regla de
negocio que permita elegirlo. Tampoco se habilita un bloqueo global implícito.
Los campos desconocidos o de escalamiento se rechazan.

## Validación transaccional y concurrencia

`gestion/agenda_services.py` concentra la creación del bloqueo dentro de
`transaction.atomic()` y vuelve a comprobar el permiso efectivo. El servicio:

1. bloquea con `SELECT FOR UPDATE` la fila del Personal objetivo;
2. valida que el Personal exista y esté operativo;
3. rechaza intervalos vacíos o invertidos;
4. rechaza solapamientos con bloqueos propios o globales;
5. rechaza solapamientos con Turnos en estados activos;
6. rechaza solapamientos con `SlotHold` activo y no vencido;
7. crea el bloqueo sólo después de superar todas las validaciones.

El lock sobre Personal usa el mismo recurso de serialización que creación,
reprogramación y HOLD canónicos. La prueba concurrente PostgreSQL demuestra
que dos comandos simultáneos para el mismo intervalo producen exactamente un
bloqueo; el segundo termina en conflicto.

Errores:

| Situación | HTTP |
| --- | ---: |
| Anónimo | `401` |
| Sin `manage_configuration` | `403` |
| Payload, intervalo o Personal inválido/inactivo | `400` |
| Turno, HOLD o bloqueo solapado | `409` |
| Creación válida | `201` |

En todos los errores se comprueba ausencia de mutación.

## Matriz automatizada

La suite
`bohemiacore/gestion/tests/test_legacy_agenda_permissions_bh060_2.py` cubre:

| Actor | Lectura global | Lectura propia | Crear bloqueo |
| --- | --- | --- | --- |
| Anónimo | `401` | `401` | `401` |
| CLIENTE | `403` | No tiene Personal | `403` |
| EMPLEADO | Permitida por permiso base | No aplica | `403` |
| PROFESIONAL | Permitida por permiso base | Preservada | `403` sin permiso de escritura |
| ADMINISTRADOR no-staff | Permitida | Preservada si tiene perfil | Permitida |
| `is_staff=True` sin permiso | `403` | Sólo si tuviera ownership válido | `403` |
| No-staff con `view_global_agenda` individual | Permitida | No aplica | `403` |
| No-staff con `manage_configuration` individual | No implica lectura global | No aplica | Permitida |
| Cuenta inactiva con permisos asignados | `403` | `403` | `403` |
| Personal activo sin permiso global | Sólo la propia | Permitida | `403` |
| Personal inactivo | `403` | `403` | Objetivo rechazado con `400` |

Casos adicionales:

- agenda propia frente a ajena;
- manipulación de `personal_id` en ambas rutas legacy;
- objetivo inexistente o inactivo;
- eliminación del fallback al primer colorista;
- intervalos inválidos y payload malicioso;
- conflictos con Turno y con otro bloqueo;
- no mutación ante `401`, `403`, `400` y `409`;
- equivalencia de autorización con agenda global y laboral canónicas;
- carrera de dos bloqueos simultáneos;
- preservación del alias público de slots para reserva.

## Compatibilidad frontend

- `/admin/agenda` ya exige `gestion.view_global_agenda` mediante
  `ProtectedRoute`.
- `AgendaAdmin` y `ConfiguracionAgendaMasiva` envían el token al calendario
  alternativo; la lectura agregada autorizada se conserva.
- Las acciones de escritura de `AgendaAdmin` siguen deshabilitadas mediante
  `agendaWriteActionsEnabled = false`. Por tanto, no se habilitó una mutación
  frontend sin selector explícito de Personal ni sin
  `manage_configuration`.
- Si esa edición se habilita en el futuro, deberá seleccionar `personal_id` y
  separar visibilidad de lectura (`view_global_agenda`) de controles de
  escritura (`manage_configuration`).
- La agenda laboral propia, reserva, reprogramación, cancelación,
  disponibilidad pública y CU-27 no cambian de URL ni contrato.

## Resultados

Entorno confirmado: PostgreSQL (`django.db.backends.postgresql`).

| Validación | Resultado |
| --- | --- |
| Suite focalizada BH-060.2 | **19/19 OK**, incluida concurrencia PostgreSQL |
| Roles, lectura/gestión/creación de Turnos, disponibilidad, bloqueos técnicos, skills y HOLD | **158/158 OK** |
| Carreras HOLD y CU-27 | **7/7 OK** |
| Frontend: rutas, agenda laboral y gestión de Turnos/CU-27 | **49/49 OK** |
| `manage.py check` | **OK**, 0 issues |
| `makemigrations --check --dry-run` | **OK**, sin cambios |
| Build frontend normal | **OK**, compila con warnings preexistentes |
| `git diff --check` | **OK** |

No aparecieron fallos legacy en las suites ejecutadas. El build conserva los
warnings globales ya documentados en archivos ajenos de agenda masiva,
contenido, rutinas y notificaciones; no se modificaron para obtener un verde
artificial.

## Riesgos pendientes

- `HorarioLaboralViewSet` conserva su política legacy `IsAdminUser`; cambiar la
  administración masiva de horarios no forma parte de este incremento.
- La UI contiene código de escritura deshabilitado que todavía no selecciona un
  Personal objetivo. No debe habilitarse sólo por permiso de lectura.
- Los bloqueos globales existentes continúan aplicándose y se muestran a cada
  agenda afectada. Crear nuevos bloqueos globales requiere una regla de negocio
  explícita y quedó deliberadamente fuera del contrato.
- Los warnings frontend globales siguen siendo deuda previa.
