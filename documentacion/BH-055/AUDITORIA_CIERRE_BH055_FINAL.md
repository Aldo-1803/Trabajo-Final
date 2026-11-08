# Auditoría final de cierre — BH-055

**Alcance:** verificación exclusiva del cierre de B1, B2 y B3. No se evaluaron ni
se abrieron BH-056, BH-057, BH-058 ni otros backlogs fuera de BH-055.

**Método:** revisión estática de guards, navegación, consumidores de endpoints y
autorización backend; ejecución focalizada de regresión frontend. Esta auditoría
no modifica código de producto.

## Veredicto

Los tres blockers previos están cerrados. No se identificaron blockers nuevos de
BH-055.

## B1 — `/operaciones` capability-driven

**Resultado: CERRADO.**

- La ruta acepta exactamente cualquiera de estas capacidades:
  `gestion.view_global_agenda`, `usuarios.create_walkin_client`,
  `gestion.create_turno_for_client`, `gestion.register_arrival`,
  `gestion.reprogram_any_turno` y `gestion.cancel_any_turno`.
- Con `gestion.view_global_agenda`, `Operaciones` consume únicamente el listado
  global `GET /api/gestion/turnos/?fecha=...` y conserva el enlace a la agenda
  global.
- Sin ese permiso y con perfil `personal` activo, consume exclusivamente
  `GET /api/gestion/turnos/mi-agenda-laboral/`, filtrando la presentación a los
  Turnos de hoy. No realiza `GET /api/gestion/turnos/`.
- Una capacidad aislada sin agenda global ni Personal activo no provoca ninguna
  consulta de Turnos: se muestra el estado seguro sin scope inventado.
- Llegada, reprogramación y cancelación se renderizan por sus permisos exactos;
  las escrituras continúan en sus endpoints semánticos dedicados.
- El Header expone Operaciones con cualquiera de las seis capacidades, sin usar
  BusinessRole ni `is_staff` como autorización.

## B2 — alta independiente de Cliente

**Resultado: CERRADO.**

- `/admin/clientes/nuevo` está protegida sólo con
  `usuarios.create_walkin_client`.
- `/admin/clientes` mantiene, de forma independiente, el guard
  `usuarios.view_clients` para el listado global.
- `ClienteCreationForm` reutiliza el contrato existente
  `POST /api/usuarios/admin/clientes/crear/`; no concede lectura de Clientes.
- Tras crear, navega a `/admin/clientes` sólo si existe `view_clients`; de lo
  contrario usa `getLandingPath(session)` o `/operaciones`, sin terminar en una
  ruta que el usuario no pueda abrir.
- Header y tarjeta de Operaciones enlazan **Nuevo cliente** a
  `/admin/clientes/nuevo`; **Clientes** conserva el enlace al listado global.
- Backend mantiene el permiso dedicado: la creación con
  `create_walkin_client` retorna 201 y un `is_staff` sin ese permiso retorna
  403. El listado usa `CanViewClients` por separado.

## B3 — agenda laboral propia de Personal

**Resultado: CERRADO.**

- La ruta `/mi-agenda-laboral` usa `requiredActiveProfile="personal"`. El
  contrato `hasActiveProfile` exige `profiles.personal.exists === true` y
  `profiles.personal.active === true` desde `/api/usuarios/me/`.
- No exige `view_global_agenda`, un BusinessRole concreto ni `is_staff`.
- `MiAgendaLaboral` lee sólo
  `GET /api/gestion/turnos/mi-agenda-laboral/`; no consume el listado global.
- La UI sólo presenta Cliente mínimo, Servicio, fecha/hora y estado. Las
  acciones son semánticas: llegada con `register_arrival`, reprogramación con
  `reprogram_any_turno` y cancelación con `cancel_any_turno`.
- Backend limita la consulta al `Personal` activo enlazado al usuario activo
  (`profesional=personal`); Personal inactivo o inexistente recibe 403.
- Los perfiles Cliente y Personal siguen siendo scopes separados: el frontend
  conserva los enlaces de Cliente para un perfil coexistente y el backend cubre
  ambas colecciones sin permitir agenda global.

## Autoridad frontend

La autoridad de las capacidades BH-055 es `SessionContext`, que refresca
`GET /api/usuarios/me/` y consulta el conjunto de permisos efectivos mediante
`hasPermission`/`hasAnyPermission`.

Revisión de los archivos productivos BH-055 (`SessionContext`, guards, rutas,
Header/navegación, Operaciones, MiAgendaLaboral, NuevoCliente,
GestionClientes y acciones semánticas):

| Señal revisada | Resultado |
|---|---|
| `is_staff` / `is_superuser` como autorización BH-055 | No existe uso productivo para gobernar capacidades BH-055. |
| `localStorage.user_info` como autoridad | No se lee para autorizar; SessionContext sólo lo elimina al cerrar sesión o ante 401. Login almacena identidad mínima derivada de `/me`, sin `is_staff`. |
| BusinessRole como permiso BH-055 | No se usa para habilitar guards, navegación o acciones BH-055; se mantiene para identidad y landing. |
| Permisos efectivos | Provienen de `/me` y se comparan por codename exacto. |

## Matriz final

| Capacidad | Guard frontend | Scope | Endpoint backend | Autoridad backend | Estado |
|---|---|---|---|---|---|
| Ver Clientes | `usuarios.view_clients` | listado global | `GET /api/usuarios/clientes/` | `CanViewClients` | Correcto |
| Crear Cliente | `usuarios.create_walkin_client` | alta sin listado | `POST /api/usuarios/admin/clientes/crear/` | permiso dedicado de creación | Correcto |
| Agenda global | `gestion.view_global_agenda` | todos los Turnos | `GET /api/gestion/turnos/` | `CanViewGlobalAgenda` | Correcto |
| Agenda propia Personal | perfil Personal activo | sólo asignados al Personal | `GET /api/gestion/turnos/mi-agenda-laboral/` | Personal y usuario activos; filtro `profesional=personal` | Correcto |
| Reservar propio | perfil Cliente | propio | `POST /api/gestion/turnos/reservar/` | Cliente activo | Correcto |
| Crear Turno para Cliente | `gestion.create_turno_for_client` | tercero seleccionado | endpoint semántico `crear-para-cliente` | `CanCreateTurnoForClient` | Correcto |
| Llegada | `gestion.register_arrival` | agenda global o propia ya autorizada | `POST /api/gestion/turnos/{id}/registrar-llegada/` | `CanRegisterTurnoArrival` | Correcto |
| Reprogramar | `gestion.reprogram_any_turno` | agenda global o propia ya autorizada | `POST /api/gestion/turnos/{id}/reprogramar/` | `CanReprogramAnyTurno` | Correcto |
| Cancelar | `gestion.cancel_any_turno` | agenda global o propia ya autorizada | `POST /api/gestion/turnos/{id}/cancelar/` | `CanCancelAnyTurno` | Correcto |

## BusinessRole nulo: invariancia vigente

`ProtectedRoute` rechaza `businessRole=null` antes de evaluar permisos y dirige
a `/cuenta-sin-acceso`. Por decisión de arquitectura, una cuenta normal con
`businessRole=null + permiso individual` es una inconsistencia de cuenta y falla
cerrado. No concede acceso implícito y **no es un blocker de BH-055**.

## Tests y validación

- Frontend focalizado: **10 suites, 121 tests aprobados**:
  `SessionContext`, `Header`, `ProtectedRoute`, `Operaciones`,
  `MiAgendaLaboral`, `GestionClientes`, `NuevoCliente`, `GestionTurnos`,
  `MisTurnos` y `Login`.
- La cobertura revisada incluye permisos aislados, agenda propia frente a global,
  `create_walkin_client` sin `view_clients`, perfiles coexistentes, ADMINISTRADOR
  con `is_staff=False`, ausencia de permiso y accesos directos protegidos.
- Build frontend: completó correctamente. Los warnings existentes pertenecen a
  módulos fuera de este alcance y no impiden el build.
- `git diff --check`: sin errores de whitespace.
- Backend: se intentó ejecutar
  `gestion.tests.test_turno_read_authorization_api` y
  `usuarios.test_client_account_creation_api`, pero Django no inicia porque falta
  `simple_history` (`ModuleNotFoundError`). No hubo modificación backend;
  existen pruebas estáticas relevantes para agenda propia, Personal inactivo,
  scopes Cliente/Personal separados y creación de Cliente por permiso. Se
  registra como deuda de entorno **BH-060**, no como blocker funcional BH-055.

## Deuda aceptada fuera de BH-055

No afecta este cierre: BH-056 (skills), BH-057 (historial/evaluación), BH-058
(HOLD/pagos/Mercado Pago), BH-059, BH-060 (infraestructura de tests), BH-061 y
BH-062. El siguiente backlog recomendado es **BH-056**.

# BH-055 = LISTO PARA CERRAR
