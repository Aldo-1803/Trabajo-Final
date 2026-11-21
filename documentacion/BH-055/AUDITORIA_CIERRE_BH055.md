# Auditoría final de cierre — BH-055

**Método:** revisión estática de frontend/backend y tests disponibles.
No se modificó implementación.

## Veredicto

# BH-055 = NO CERRABLE

Hay tres blockers de frontend. El backend ya autoriza capacidades independientes,
pero la SPA no permite ejercer todas en los casos autorizados.

## Alcance aplicado

Auditado: `/api/usuarios/me/`, SessionContext, login/landing, Header,
navegación, ProtectedRoute, Clientes, agenda global, Turnos de hoy, reserva y
Turnos propios de Cliente, creación para Cliente, llegada, reprogramación,
cancelación y `/operaciones`.

Fuera de evaluación: skills, historial/evaluación técnica, HOLD, seña/pago,
Mercado Pago de Turnos, caja, stock, finalización técnica y fórmulas.

## Autoridad frontend

| Coincidencia relacionada | Clase | Resultado |
|---|---|---|
| `is_staff`/`is_superuser` en SessionContext, landing, Header, rutas, Operaciones, Clientes y acciones de Turno | A | No hay uso productivo para autorizar capacidades BH-055. |
| `localStorage.user_info` en Login | B | Sólo persiste identidad mínima derivada de `/me`; sin rol, permisos ni `is_staff`. |
| `localStorage.user_info` en SessionContext | B | Sólo limpieza ante logout/401; nunca se lee para autorizar. |
| `businessRole` en landing/Header | B | Identidad, etiqueta y experiencia; no deriva permisos. |
| `allowedRoles` de navegación administrativa | C | Módulos fuera de alcance: Dashboard, Productos, Reportes y similares. |
| `is_staff` en catálogo, pagos y serializers legacy | C | Fuera de los flujos BH-055 migrados. |

No hay matriz frontend `BusinessRole -> permissions`. `SessionContext` recibe
permisos efectivos del backend y `hasPermission` compara membresía exacta.

## Sesión y fallo cerrado

| Requisito | Evidencia | Estado |
|---|---|---|
| `/me` es autoridad SPA | `fetchCurrentSession()` y `refreshSession()` | Correcto |
| Permisos efectivos backend | serializer intersecta Django con `BusinessPermission.ALL` | Correcto |
| Perfiles independientes | `/me` devuelve `profiles.cliente` y `profiles.personal` | Correcto |
| Rol conceptual / permiso capacidad | UI usa `hasPermission` | Parcial: B1/B2 |
| Error y rol nulo cerrados | error a `/error-acceso`, nulo a `/cuenta-sin-acceso` | Correcto |
| Roles múltiples | 409 `MULTIPLE_BUSINESS_ROLES`, sin capacidades inventadas | Correcto |

El contrato `/me` no incluye `is_staff` ni `is_superuser`.

## Login y landing

| BusinessRole | Destino |
|---|---|
| CLIENTE | `/perfil` |
| EMPLEADO | `/operaciones` |
| PROFESIONAL | `/operaciones` |
| ADMINISTRADOR | `/admin-dashboard` |
| nulo | `/cuenta-sin-acceso` |
| desconocido o error semántico | `/error-acceso` |

Login obtiene tokens, consulta `/me` mediante `refreshSession()` y luego navega.
No existe fallback por `is_staff`.

## Header, navegación y ProtectedRoute

- Cliente se filtra por `profiles.cliente`.
- Operaciones se filtra por permisos efectivos, no por BusinessRole.
- Profesional con perfil Cliente conserva ambos grupos de enlaces.
- ADMINISTRADOR con `is_staff=False` depende de permisos efectivos.
- Loading/error no renderizan navegación privilegiada.
- El logo usa `getLandingPath()` centralizado.
- `ProtectedRoute` soporta `requiredPermission`, `requiredAnyPermission`,
  `requiredProfile` y `allowedRoles`; verifica loading, anónimo, error y rol
  nulo antes de contenido.

| Ruta | Guard | Estado |
|---|---|---|
| `/perfil`, `/reservar`, `/mis-turnos` | perfil Cliente | Correcto |
| `/admin/clientes` | `usuarios.view_clients` | Correcto para lectura global |
| `/admin/turnos` | `gestion.view_global_agenda` | Correcto |
| `/admin/nuevo-turno` | `gestion.create_turno_for_client` | Correcto |
| `/operaciones` | agenda, alta Cliente o crear tercero | Incompleto: B1 |

`allowedRoles` no se aplica a las rutas BH-055 y no reemplaza permisos allí.

## Matriz frontend vs backend

| Capacidad | UI | Guard frontend | Endpoint | Autoridad backend | Estado |
|---|---|---|---|---|---|
| Sesión | Login/SessionContext | token/estado | `GET /api/usuarios/me/` | JWT | Correcto |
| Lista/detalle Clientes | Gestión Clientes | `usuarios.view_clients` | `GET /api/usuarios/clientes[/id]/` | `CanViewClients` | Correcto |
| Perfil Cliente propio | Perfil | perfil Cliente | `/api/usuarios/perfil/` | ownership | Correcto |
| Alta presencial | Gestión Clientes | `create_walkin_client` en botón | `POST /admin/clientes/crear/` | permiso dedicado | B2 |
| Agenda global | Gestión Turnos | `view_global_agenda` | `GET /api/gestion/turnos/` | `CanViewGlobalAgenda` | Correcto |
| Turnos de hoy | Operaciones | `view_global_agenda` | listado por fecha | `CanViewGlobalAgenda` | Correcto |
| Reserva propia | Reserva Cliente | perfil Cliente | `POST /turnos/reservar/` | Cliente activo | Correcto |
| Mis Turnos | MisTurnos | perfil Cliente | `GET /turnos/mis-turnos/` | ownership | Correcto |
| Reprogramar/cancelar propios | MisTurnos | perfil/política | endpoints `*-cliente` | ownership/transición | Correcto |
| Crear para tercero | Nuevo Turno | `create_turno_for_client` | selectores y `crear-para-cliente` | permiso dedicado | Correcto |
| Registrar llegada | agenda/Operaciones | botón por permiso | `POST /{id}/registrar-llegada/` | `CanRegisterTurnoArrival` | B1 |
| Reprogramar cualquiera | acciones semánticas | permiso exacto | `POST /{id}/reprogramar/` | `CanReprogramAnyTurno` | B1 |
| Cancelar cualquiera | acciones semánticas | permiso exacto | `POST /{id}/cancelar/` | `CanCancelAnyTurno` | B1 |
| Agenda laboral propia | no hay UI | N/A | `GET /turnos/mi-agenda-laboral/` | Personal activo | B3 |

Backend separa agenda global, ownership Cliente y agenda de Personal.
Cliente que consulta Turno ajeno recibe 404; faltas de permiso, 403.

## Operaciones y permisos individuales

La página calcula seis permisos por separado, pero su ruta y enlace sólo
aceptan:

```text
gestion.view_global_agenda
usuarios.create_walkin_client
gestion.create_turno_for_client
```

Faltan `gestion.register_arrival`, `gestion.reprogram_any_turno` y
`gestion.cancel_any_turno`. Dentro de una agenda visible, los botones sí son
independientes, pero un permiso aislado no permite entrar ni seleccionar Turno.

Además, `ProtectedRoute` rechaza `businessRole=null` antes de evaluar permisos.
Un usuario sin grupo de negocio con permiso individual tampoco accede, aunque
el backend autorice su endpoint.

## Escrituras legacy

| Operación | Resultado |
|---|---|
| `POST /api/gestion/turnos/` | 405 |
| `PUT/PATCH /api/gestion/turnos/{id}/` | 405 |
| `DELETE /api/gestion/turnos/{id}/` | 405 |
| `POST /turnos/{id}/gestionar/` | 405 |
| `POST /turnos/{id}/gestionar-profesional/` | 405 |
| Administración | endpoints semánticos de llegada/reprogramación/cancelación |
| Cliente | `opciones-cliente`, `reprogramar_cliente`, `cancelar-cliente` |

No hay consumidores productivos BH-055 de PATCH/DELETE, POST genérico,
`gestionar/` ni `gestionar-profesional/`.

## Tests inventariados

| Área | Tests existentes |
|---|---|
| Sesión | `test_current_session_api.py`, `SessionContext.test.js`, `sessionLanding.test.js`, `Login.test.js` |
| Guards/Header | `ProtectedRoute.test.js`, `Header.test.js` |
| Clientes | `test_client_access_api.py`, `GestionClientes.test.js` |
| Lectura Turnos | `test_turno_read_authorization_api.py` |
| Creación/reserva | `test_turno_creation_api.py`, `NuevoTurno.test.js`, `ReservaCliente.test.js` |
| Llegada | `test_turno_arrival_api.py`, `GestionTurnos.test.js`, `Operaciones.test.js` |
| Reprogramar/cancelar | `test_turno_management_api.py`, `GestionTurnos.test.js`, `Operaciones.test.js`, `MisTurnos.test.js` |

Cubren roles, Group, permisos individuales backend, `is_staff=False`, falta de
permiso, anónimo, perfiles coexistentes, URL directa principal, 401, 403 y 404
de ownership. Faltan pruebas integradas para B1, B2 y B3.

### Ejecución durante la auditoría

- Frontend: `npm test -- --watchAll=false --runInBand`: 16 suites y 146 tests
  aprobados. La suite total falla por `src/App.test.js`, que no resuelve
  `react-router-dom`.
- Backend: la suite seleccionada no inició porque falta `simple_history`
  (`ModuleNotFoundError` durante `django.setup`).

No se ejecutaron migraciones ni se alteraron dependencias. Ambos son deuda de
infraestructura/BH-060, no blockers funcionales adicionales de BH-055.

## Blockers reales de BH-055

### B1 — Operaciones no admite acciones de Turno con permiso aislado

Sólo `register_arrival`, `reprogram_any_turno` o `cancel_any_turno` no habilita
Operaciones ni URL directa, aunque backend permite la acción.

**Cierre requerido:** entrada capability-driven por acción aislada, o una vista
operativa con scope de lectura seguro. No conceder agenda global implícitamente.

### B2 — Alta con permiso aislado termina en ruta denegada

Operaciones muestra “Nuevo cliente” con `create_walkin_client`, pero conduce a
`/admin/clientes`, que exige `view_clients` y carga el listado global.

**Cierre requerido:** ruta/vista de alta independiente por ese permiso, sin
conceder lectura global.

### B3 — Falta agenda laboral propia de Personal en frontend

Backend expone `mi-agenda-laboral`; no hay ruta, enlace ni consumidor frontend.
`/mi-agenda` es agenda de cuidados de Cliente y consume otro endpoint.

**Cierre requerido:** vista/ruta para `profiles.personal` activo, separada de
Cliente y agenda global.

## Deuda aceptada y trabajo futuro

| Backlog | Trabajo futuro no bloqueante |
|---|---|
| BH-056 | skills/habilitaciones de Personal. |
| BH-057 | historial, diagnóstico, riesgo y evaluación automática. |
| BH-058 | HOLD, seña/pago, Mercado Pago y conciliación de Turnos. |
| BH-059 | rutas legacy administrativas/técnicas ajenas al alcance. |
| BH-060 | E2E/routing, `App.test.js` y dependencias backend. |
| BH-061 | navegación/rutas fuera de alcance que aún usan `allowedRoles`. |
| BH-062 | normalización de `is_staff` restante en flujos legacy. |

## Parametrización futura

| Configurables | Invariantes de código |
|---|---|
| TTL HOLD, seña, modalidad de pago, espera entre servicios, vigencia de diagnóstico, reglas técnicas y SLA de revisión | autorización backend, ownership, locks, idempotencia, webhook autoritativo, transiciones imposibles, integridad transaccional y fallo cerrado. |

# BH-055 = NO CERRABLE
