# BH-062 — Incremento 2: rutas y navegación por acceso efectivo

**Fecha:** 2026-11-10

**Baseline:** `ddd64a0d43d736fe15f56233fbc20b410dc656d0`

**Rama:** `save/work-in-progress`

## 1. Objetivo y alcance

Este incremento alinea las rutas React, el menú, el destino posterior al login
y los enlaces de notificaciones con `permissions`, `capabilities` y perfiles
publicados por `/api/usuarios/me/`.

No se cambió backend, no se agregaron pantallas y no se implementaron los
controles internos de formularios reservados para el Incremento 3. El backend
continúa siendo la única autoridad sobre datos, ownership, estados y comandos.

## 2. Políticas finales de rutas

`ProtectedRoute` conserva perfiles, perfiles activos, permisos, cualquiera de
varios permisos y `allowedRoles` para compatibilidad. Agrega:

- `requiredCapability`;
- `requiredAnyCapability`;
- `requiredAnyAccess`, como OR explícito entre listas de permisos y
  capabilities.

La sesión debe terminar de cargar antes de evaluar el guard. Una capability
ausente, desconocida o falsa deniega el acceso. El componente hijo no se monta
y por lo tanto no inicia sus efectos ni fetches cuando el guard deniega.

Se eliminó el rechazo global por `businessRole === null`: un grant efectivo de
grupo técnico o individual puede abrir una ruta aunque no exista BusinessRole.
`allowedRoles` sigue aplicándose sólo en una ruta que lo declare expresamente.

| Ruta | Política final |
|---|---|
| `/revision-tecnica` | `technical_booking.review`. El permiso simple y Personal activo ya no alcanzan si la habilidad efectiva no está vigente. |
| `/admin/servicios` | `gestion.manage_prices` **o** `service_formula.manage`. Se conserva la pantalla parcial para cualquiera de sus dos operaciones legítimas. |
| Tres rutas `/admin/contenido-educativo*` | `content.author` **o** `content.manage_global`. Ownership y operaciones concretas siguen en backend. |
| `/operaciones` | Cualquiera de sus permisos operativos/financieros existentes. |
| `/mi-agenda-laboral` | Personal activo, sin exigir agenda global. |
| Resto de rutas | Conservan sus permisos o perfiles existentes; las listas compartidas sólo evitan divergencia entre ruta, menú y landing. |

No se publicaron rutas para diagnósticos o fichas técnicas legacy.

## 3. Menú y accesos rápidos

`navigationConfig.js` evalúa las mismas clases de condiciones que las rutas:
permisos, perfiles, capabilities y el OR explícito de Servicios.

Cambios principales:

- Usuarios depende únicamente de `usuarios.manage_users`;
- Auditoría depende únicamente de `gestion.view_audit`;
- se eliminaron sus `allowedRoles: ['ADMINISTRADOR']` redundantes;
- Revisión técnica usa `technical_booking.review`;
- Servicios usa precio o fórmula efectiva;
- Contenido educativo usa autoría o gestión global;
- se agregaron entradas para Agenda, gestión de rutinas, Servicios y Contenido;
- Equipamiento, Reglas y Configuración se mantienen como opciones secundarias
  del menú de cuenta para no alargar todavía más la barra principal;
- Operaciones y Mi agenda laboral mantienen sus entradas existentes.

Un permiso efectivo tiene el mismo resultado si proviene de BusinessRole,
grupo técnico o grant individual. `is_staff` no participa.

También se alinearon accesos rápidos que apuntaban a rutas potencialmente
denegadas:

- la tarjeta de solicitudes del Dashboard sólo navega a Turnos con
  `gestion.view_global_agenda`;
- el acceso del Dashboard a Servicios acepta la capability de fórmulas;
- los enlaces de Gestión de Usuarios a Dashboard, Clientes y Personal sólo se
  ofrecen con el permiso propio del destino.

## 4. Selección del landing

`getLandingPath()` ya no concede destinos por BusinessRole. El algoritmo:

1. resuelve primero estados de sesión: loading no redirige, anonymous vuelve a
   login y un error estable va a `/error-acceso`;
2. construye candidatos cuya condición coincide con el guard real de la ruta;
3. utiliza BusinessRole sólo para ordenar esos candidatos:
   - Cliente prioriza su perfil;
   - Empleado/Profesional priorizan Operaciones, agenda propia y revisión;
   - Administrador prioriza Dashboard únicamente si tiene `view_reports`;
4. selecciona la primera ruta realmente autorizada;
5. si no existe ninguna superficie, usa `/cuenta-sin-acceso`.

Consecuencias verificadas:

- un administrador sin `view_reports` nunca recibe `/admin-dashboard`;
- un Personal activo con agenda propia como única superficie recibe
  `/mi-agenda-laboral`;
- un usuario sin BusinessRole pero con grant técnico recibe la ruta habilitada;
- un permiso simple de fórmulas con capability falsa no selecciona Servicios;
- perfiles Cliente y Personal coexistentes se priorizan por experiencia, no se
  usan como sustituto de autorización.

`CuentaSinAcceso` ahora representa cualquier sesión autenticada sin superficie
de negocio y no sólo la ausencia de rol. Sólo redirige cuando aparece un nuevo
destino autorizado, evitando la redirección a sí misma.

## 5. Destinos de notificaciones

`notificationNavigation.js` dejó de exigir BusinessRole administrador:

- Turnos administrativos requieren exactamente
  `gestion.view_global_agenda`, igual que `/admin/turnos`;
- Órdenes administrativas requieren exactamente `gestion.manage_stock`, igual
  que `/admin/ordenes`;
- `gestion.register_payment` ya no se interpreta como acceso a Órdenes;
- un perfil Cliente coexistente prioriza `Mis Turnos` o `Mis Pedidos` propios;
- si el destino específico no está autorizado se usa el landing seguro;
- el identificador de Turno u Orden no se propaga al estado de navegación
  cuando se usa ese fallback.

Alertas y recordatorios de Turnos usan la misma condición que las
notificaciones con `turno_id`.

## 6. Coherencia y compatibilidad

Las listas de permisos repetidas se centralizaron en `utils/accessRules.js`.
Las capabilities se comprueban con igualdad estricta a `true`; no se infieren
desde permiso simple, rol, función laboral ni flags técnicos.

Se conserva compatibilidad con:

- guards existentes de perfiles, permisos y roles explícitos;
- rutas Cliente publicadas;
- Operaciones, Caja, Productos, Personal, Reportes y demás pantallas parciales;
- Login y consumidores de `SessionContext`;
- acceso por URL directa a rutas legítimas.

## 7. Pruebas y regresiones

La matriz focal ejecutó **11 suites y 164 tests OK** sobre:

- `ProtectedRoute` y no montaje/fetch ante denegación;
- `NavigationConfig` y `Header`;
- `SessionLanding` y Login;
- `NotificationNavigation`;
- `CuentaSinAcceso` y `AccesoDenegado`;
- Revisión técnica;
- Dashboard y accesos rápidos de Gestión de Usuarios.

La suite frontend completa ejecutó **36 suites y 348 tests OK**. Incluyó
`SessionContext`, todas las pantallas afectadas y las regresiones previamente
existentes.

`npm run build` compiló correctamente. Persisten advertencias legacy de ESLint,
Browserslist y dependencias dinámicas, sin errores nuevos ni bloqueo del build.

No se ejecutaron tests backend porque no hubo modificaciones de código backend.

## 8. Riesgos pendientes

1. **Incremento 3:** formularios, campos y acciones internas deben terminar de
   representar permisos/capabilities sin ampliar autoridad por objeto.
2. **Incremento 4:** una sesión abierta todavía no refresca automáticamente por
   foco, revocación externa o 403.
3. **Incremento 5:** queda pendiente la matriz final integral y evidencia de
   cierre de BH-062.
4. **Autorización contextual:** las capabilities globales no sustituyen
   ownership, estado ni compatibilidad técnica del backend.
5. **Retornos legacy internos:** algunas pantallas antiguas conservan botones
   de retorno visual al Dashboard; no conceden acceso porque la ruta está
   protegida, pero podrán unificarse sin mezclarlo con controles del Incremento
   3.

## 9. Veredicto

Rutas, menú, landing y notificaciones representan la misma autoridad efectiva
sin usar BusinessRole como permiso ni montar pantallas denegadas.

`BH-062 INCREMENTO 2 = VALIDADO`
