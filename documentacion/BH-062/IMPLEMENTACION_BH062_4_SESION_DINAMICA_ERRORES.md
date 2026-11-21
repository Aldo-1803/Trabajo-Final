# BH-062 — Incremento 4: sesión dinámica y errores HTTP

## Resultado

El frontend actualiza durante una sesión activa la proyección conjunta de
Usuario, BusinessRole, permisos, capabilities y perfiles. El backend continúa
siendo la autoridad: React retira rutas y acciones cuando `/api/usuarios/me/`
refleja una revocación, pero no intenta decidir ownership ni estados de objetos.

Este incremento modifica React, tests y documentación. No cambia JWT, permisos,
roles, endpoints ni código backend.

## Comportamiento previo inspeccionado

- `SessionContext` consultaba `/me/` al montar o después del login. Cada refresh
  reemplazaba la proyección por `loading`, no se deduplicaba y no existían
  eventos de foco o visibilidad.
- Un contador evitaba aplicar una respuesta anterior después de otro refresh o
  logout, pero no protegía explícitamente cambios de token/identidad.
- El interceptor global trataba todo `401`, incluso uno de login, como sesión
  expirada: borraba storage y asignaba `window.location.href = '/login'`.
- No existía coordinación global para `403`.
- `AccesoDenegado` era estática y las pantallas prioritarias usaban mensajes y
  ramas HTTP diferentes.
- `ProtectedRoute` ya reaccionaba declarativamente al contexto y no necesitó
  una nueva matriz de autorización.

## Refresco por foco y visibilidad

Se eligió un intervalo mínimo de **45 segundos**
(`SESSION_REFRESH_INTERVAL_MS = 45_000`), dentro del rango requerido.

- Un `focus` de `window` o un `visibilitychange` a `visible` consulta `/me/`
  sólo si la última comprobación exitosa ocurrió hace 45 segundos o más.
- No hay polling ni timers permanentes.
- Sin `access_token` o sin sesión autenticada no se consulta `/me/`.
- Los listeners se eliminan al desmontar `SessionProvider`.
- El `Cache-Control: no-store` de la respuesta `/me/` continúa garantizado por
  el backend existente; no se añadió un header de request que alterase CORS.

El refresh de una sesión ya autenticada es silencioso: conserva la proyección
visible mientras consulta. Red o `5xx` conservan esa proyección y exponen
`refreshError`; no aparentan una revocación. La carga inicial continúa siendo
fail-closed si no puede obtener el contexto.

## Deduplicación y respuestas obsoletas

`SessionContext` mantiene una única promesa en vuelo por token. Foco,
visibilidad, reintento manual y varios `403` concurrentes comparten esa promesa.

Cada request captura token, generación e identidad esperada. Su resultado se
ignora cuando, antes de resolver:

- ocurrió logout o expiración;
- cambió el access token por un nuevo login;
- comenzó un refresh de otra generación;
- cambió la identidad mantenida por el contexto.

El desmontaje también invalida la generación pendiente.

## Coordinación de 401

`axiosConfig` ya no navega ni borra storage por su cuenta. Publica un evento
`unauthorized` sólo cuando el request protegido salió con un token de sesión.
Los endpoints públicos de autenticación no reciben ese token y un login fallido
no se interpreta como expiración.

Al recibir el evento para el token todavía vigente, `SessionContext`:

1. invalida refreshes pendientes;
2. borra access token, refresh token, `user_info` y el header por defecto;
3. vacía permisos, capabilities y perfiles;
4. pasa a sesión anónima;
5. deja que `ProtectedRoute` abandone declarativamente la ruta protegida;
6. muestra en Login: `Tu sesión finalizó. Ingresá nuevamente.`

Un `401` de `/me/` aplica el mismo procedimiento. No se modificó el contrato JWT.

## Coordinación de 403

Un `403` de un request autenticado publica un evento `forbidden`. El contexto
refresca `/me/` una vez y comparte la consulta si hay otros `403` simultáneos.

- La operación rechazada **no se reenvía**.
- El `403` no cierra sesión.
- Si cambió la autoridad, la nueva proyección hace que rutas, navegación y
  acciones se retiren; `ProtectedRoute` desmonta el hijo protegido.
- Si no cambió, la sesión se conserva y la pantalla puede mostrar la denegación
  por ownership o estado del objeto.
- `/me/` usa un cliente dedicado sin el interceptor global, por lo que no existe
  un ciclo `403 → refresh → 403`.
- Eventos pertenecientes a un token anterior se descartan.

## Clasificación uniforme de errores

`utils/httpErrors.js` define una capa pequeña y sin notificaciones propias:

| Condición | Clase | Tratamiento base |
|---|---|---|
| `401` | `session` | sesión no vigente |
| `403` | `forbidden` | autorización global u ownership |
| `409` | `conflict` | conflicto de estado/regla |
| `400` / `422` | `validation` | conservar formulario y mostrar validación |
| sin respuesta / timeout | `network` | recuperable, sin afirmar revocación |
| `5xx` | `server` | fallo recuperable del servidor |
| otro | `unknown` | fallback de la pantalla |

La capa conserva `error.code` y detalles backend de validación/conflicto cuando
son aptos para el flujo. No transforma `403` en “permiso revocado”: primero se
actualiza la proyección y la pantalla conserva su mensaje contextual.

## Acceso denegado

`AccesoDenegado` ahora:

- permite actualizar la sesión de forma segura y deduplicada;
- navega, tras éxito, al primer destino obtenido por
  `getAuthorizedReturnPath()`;
- no ofrece ese botón cuando no existe otro destino, evitando volver a sí misma;
- distingue un fallo de conexión de una denegación;
- no muestra permisos, grupos ni codenames internos.

## Pantallas ajustadas

- Contenido educativo: carga, estado y eliminación usan mensajes clasificados;
  se eliminó su segundo logout imperativo.
- Servicios y fórmulas: carga, guardado, baja y cambio de estado distinguen
  validación, autorización, red y servidor sin cerrar el formulario.
- Revisión técnica: carga y decisión distinguen `409`, validación, red y `5xx`;
  el borrador se conserva y sólo un nuevo clic reintenta.
- Gestión de Usuarios: se mantuvieron códigos de dominio y se uniformaron los
  fallbacks; un `403` de listado ya no navega a `/`.
- Gestión de Personal: se mantuvieron códigos de dominio y se uniformaron carga,
  validación, conflicto, autorización, red y servidor.

No se reescribieron flujos cuyo tratamiento específico ya era correcto.

## Pruebas y regresiones

Las pruebas deterministas usan `Date.now` simulado, eventos controlados y
promesas diferidas; no usan sleeps reales. Cubren:

- foco, visibilidad, intervalo y deduplicación;
- `403` único/concurrente, ownership sin cambio y ausencia de reenvío;
- revocación de permiso, capability, Personal activo y cambio de BusinessRole;
- `401`, limpieza, mensaje de expiración y separación del login fallido;
- logout, cambio de token/Usuario y respuesta antigua;
- red, timeout, `409`, `400/422`, `5xx`, formularios y retry manual;
- destinos de `AccesoDenegado`, ausencia de destino y error de conexión;
- cleanup de listeners y desmontaje de rutas sin nuevos fetches protegidos.

Validación final:

- suite frontend completa: **41 suites, 393 tests únicos, todos aprobados**;
- build React de producción: **aprobado**;
- permanecen advertencias históricas de Browserslist, dependencias dinámicas y
  lint fuera del alcance; se eliminó la única advertencia introducida durante
  este incremento;
- no se ejecutó backend porque no hubo cambios backend.

## Límites de consistencia temporal

- No hay revocación estrictamente en tiempo real. Una sesión puede conservar una
  proyección antigua hasta recuperar foco/visibilidad después del umbral o hasta
  recibir un `403`.
- Una pestaña visible y sin interacción no hace polling.
- Si `/me/` falla por red o `5xx`, se conserva temporalmente la última proyección;
  cualquier operación sigue siendo revalidada por el backend.
- Un `403` por ownership puede ocurrir aunque permisos y capabilities no cambien.
- No se implementaron WebSockets, refresh JWT, nuevos permisos, BusinessRoles ni
  el Incremento 5.
