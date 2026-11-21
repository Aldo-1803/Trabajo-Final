# BH-064 — Incremento 1: identidad presencial y alta rápida idempotente

**Fecha:** 2026-11-20

**Baseline de inicio:** `408132d9a6f9c8a58ce8da3fbe0829a9e3f9901c`

**Contrato antecedente:**
[BH-063/BH-064 — Incremento 0: decisiones y contratos](DECISIONES_Y_CONTRATOS_BH063_BH064.md)

**Alcance:** BH-064 Incremento 1. No crea Turnos ni inicia los Incrementos 2–5.

## 1. Resultado ejecutivo

El incremento separa la identidad comercial activa del acceso web sin cambiar
`USERNAME_FIELD=email` ni la relación 1:1 `Usuario`–`Cliente`.

- un alta rápida crea `Usuario` y `Cliente` activos, rol `CLIENTE`, contraseña
  inutilizable y estado `PENDING_CLAIM`;
- el email es opcional y nunca se reemplaza por un valor sintético;
- el teléfono argentino se conserva como fue ingresado y se agrega una versión
  E.164 para búsqueda y coincidencias;
- las coincidencias son señales para revisión humana: no existe autofusión ni
  unicidad global del teléfono;
- una clave idempotente, un fingerprint canónico, un ledger persistente y locks
  advisory de PostgreSQL protegen reintentos y carreras;
- el claim verificable implementado usa exclusivamente email, token de un solo
  uso, expiración, digest SHA-256, locks y consumo transaccional;
- los Clientes sin email permanecen `PENDING_CLAIM`: no se inventó un canal SMS
  o WhatsApp;
- React busca primero una identidad existente, no solicita contraseña y conserva
  clave y payload en `sessionStorage` ante un resultado de red incierto;
- el resultado entrega un `cliente_id` estable para el futuro BH-063, pero este
  incremento no crea, enlaza ni simula un Turno asistido.

## 2. Matriz de impacto inspeccionada

| Área | Realidad encontrada | Cambio / garantía del incremento |
|---|---|---|
| Identidad | `Usuario.email` era obligatorio, único y `USERNAME_FIELD`; `Cliente.usuario` era 1:1 y PK. | Se conserva el principal y la relación. Email pasa a nullable bajo constraints; no se cambian PK/FK. |
| Manager y superusuario | `UsuarioManager` exige email. | Se conserva. Sólo el servicio de alta rápida construye el pendiente sin email. |
| Registro público | Crea Usuario, Cliente y rol con email/password. | Continúa exigiendo email y password; los nuevos registros públicos quedan `CLAIMED`. |
| Login y JWT | Existían login propio y `TokenObtainPairView`. | Ambos rechazan pendientes; email faltante se rechaza antes de consultar. JWT estándar se reemplazó por una vista claim-aware. |
| Recuperación | Buscaba el email directamente y podía consultar `None`. | Normaliza, usa respuesta genérica y no convierte reset en claim. Pendientes no reciben reset. |
| Alta administrativa histórica | Exige email y contraseña temporal. | Se conserva como contrato separado y no se reutiliza para BH-064. |
| Administración | Varias vistas asumían email no nulo. | Admin y representaciones toleran “sin email”; estado y normalización son de sólo lectura técnica. |
| BusinessRole | El servicio semántico asigna un único grupo de negocio. | Alta rápida reutiliza `assign_business_role()` y verifica exactamente `CLIENTE`. No cambia BH-061 v1. |
| Permisos | `usuarios.create_walkin_client` ya existía y está en contratos efectivos. | Protege el alta. El selector admite ese permiso, `create_turno_for_client` o `view_clients`, sin ampliar el listado general. |
| Selector | El listado global no era una superficie mínima. | Se agregó búsqueda paginada independiente por nombre, apellido, email y teléfono normalizado, con contactos enmascarados. |
| Notificaciones | Los envíos dependen de email real. | El alta no envía ni crea token. Un Cliente sin email no recibe correo ficticio. |
| Teléfono | Sólo existía el texto de presentación. | Se agregan E.164 y estado de normalización. No hay unique ni backfill especulativo. |
| Servicios comerciales | Riesgo, holds y Turnos requieren Usuario y Cliente activos. | Ambos permanecen activos; la falta de acceso web o diagnóstico no invalida la identidad comercial. |
| React | El formulario administrativo pedía contraseña temporal y usaba URL/token manuales. | Alta semántica sin contraseña, selector previo, resolución humana, Axios global y permiso efectivo. |
| PostgreSQL | Email histórico sin NULL ni duplicados case-insensitive. | Preflight bloqueante, constraints, índices y advisory locks. |

## 3. Modelo de identidad y compatibilidad histórica

### 3.1 Estado de acceso

`web_access_status` se ubicó en `Usuario`, no en `Cliente`, porque credenciales,
email principal y password pertenecen al Usuario. Duplicarlo en ambos modelos
permitiría estados contradictorios.

Estados:

- `LEGACY_UNKNOWN`: valor conservador para históricos; no infiere reclamo;
- `PENDING_CLAIM`: alta rápida activa, sin password utilizable;
- `CLAIMED`: registro público o claim de email completado.

El preflight real previo a la migración encontró 4 Usuarios, 0 emails NULL, 0
vacíos y 0 duplicados case-insensitive. Ningún email histórico fue modificado,
fusionado o reemplazado.

### 3.2 Constraints

`Usuario.email` conserva `unique=True` para satisfacer `auth.E003`, pasa a
`null=True, blank=True` y suma unicidad funcional parcial sobre `Lower(email)`
para valores no nulos. PostgreSQL admite múltiples NULL.

Las constraints impiden:

- email vacío;
- email NULL fuera de `PENDING_CLAIM`;
- password utilizable en `PENDING_CLAIM`;
- estado `CLAIMED` sin email.

El login, JWT y reset no consultan un principal NULL. Los Usuarios históricos
con password continúan autenticando como `LEGACY_UNKNOWN`; no se les atribuye un
claim inexistente.

### 3.3 Migraciones

- `usuarios.0003_walkinclientoperation_webaccessclaimtoken_and_more`: preflight,
  estado, email nullable, normalización telefónica, ledgers, índices y
  constraints principales;
- `usuarios.0004_enforce_nonblank_email`: rechazo explícito del string vacío.

`sqlmigrate` confirmó `jsonb`, índices, FKs `PROTECT`, unique por actor/comando/
digest, `Lower(email)` condicional y checks esperados. Las migraciones fueron
aplicadas sobre PostgreSQL y `makemigrations --check --dry-run` no detectó drift.

## 4. Teléfono, coincidencias y resolución humana

`phonenumbers==9.0.43` normaliza con región `AR` y formato E.164. Se conservan:

- `Cliente.numero`: texto original para presentación;
- `Cliente.numero_normalizado`: E.164 para búsqueda/locks;
- `numero_normalizacion_estado`: `LEGACY_UNKNOWN`, `VALID` o `INVALID`.

Los históricos permanecen `LEGACY_UNKNOWN`; no se reinterpretaron números
ambiguos. Un teléfono puede pertenecer a varias personas.

Las coincidencias por email case-insensitive o teléfono producen candidatos
minimizados. El operador debe elegir:

- `USE_EXISTING`: el ID debe pertenecer a la lista efectivamente revisada;
- `CREATE_DISTINCT`: exige revisar todos los candidatos y justificar la nueva
  identidad. No se permite si el email ya pertenece a otra identidad.

El frontend no marca la revisión automáticamente: cada candidato requiere una
confirmación visible. Un ID ajeno al scope devuelve 404 sin exponer una ficha.

## 5. Idempotencia, locks y auditoría

`WalkInClientOperation` conserva:

- UUID público de operación;
- actor y comando;
- digest SHA-256 de `Idempotency-Key`;
- fingerprint SHA-256 del payload normalizado, actor y comando;
- Cliente resultante, indicador de creación y evidencia de resolución.

No persiste password, token, email completo ni teléfono completo. La auditoría
semántica usa IDs, flags y fingerprints de contactos.

La transacción adquiere locks advisory PostgreSQL en orden estable:

1. actor + comando + digest de clave;
2. email casefold, si existe;
3. teléfono E.164, si existe.

Luego reconsulta ledger y candidatos. Esto garantiza:

- misma clave + mismo fingerprint: mismo Cliente y operación, respuesta 200;
- misma clave + payload incompatible: 409;
- dos requests simultáneos con igual clave: una creación;
- claves distintas sobre igual identidad: una creación y revisión requerida;
- fallo de rol o auditoría: rollback de Usuario, Cliente, rol y ledger.

## 6. Claim por email y límite real

El alta nunca genera un token. `POST /api/usuarios/access-claim/request/` recibe
un email y devuelve el mismo mensaje exista o no una cuenta reclamable.

Si existe un pendiente activo con Cliente activo y email real:

1. bloquea Usuario y Cliente;
2. revoca tokens anteriores no consumidos;
3. genera 32 bytes aleatorios URL-safe;
4. persiste sólo SHA-256 y fingerprint del email;
5. fija expiración de 60 minutos;
6. audita sin token ni email completos;
7. envía el enlace al email que será verificado.

La base del enlace se configura con `WEB_ACCESS_CLAIM_FRONTEND_URL`; el fallback
local es `http://localhost:3000/reclamar-acceso`.

`POST /api/usuarios/access-claim/confirm/` bloquea token, Usuario y Cliente,
revalida estado/email/actividad/expiración, valida la contraseña, consume una
sola vez y cambia atómicamente a `CLAIMED`.

**Límite documentado:** un Cliente creado sin email no dispone de un canal
verificable en el sistema actual. Permanece activo comercialmente y
`PENDING_CLAIM`, sin token ni password. Integrar SMS/WhatsApp verificado o un
procedimiento equivalente pertenece a trabajo futuro y no fue simulado.

## 7. API

| Método y ruta | Autoridad | Resultado |
|---|---|---|
| `POST /api/usuarios/asistido/clientes/alta-rapida/` | sesión activa + `usuarios.create_walkin_client` | 201 nueva identidad; 200 replay/selección; 400 validación; 401; 403; 404 fuera de scope; 409 conflicto. |
| `GET /api/usuarios/asistido/clientes/selector/` | permiso de alta, selección de Turno o vista general | búsqueda de 2–100 caracteres, página 1–20 resultados, salida minimizada. |
| `POST /api/usuarios/access-claim/request/` | pública | respuesta anti-enumeración; correo sólo si corresponde. |
| `POST /api/usuarios/access-claim/confirm/` | token | claim único o error genérico/estado conflictivo. |
| `POST /api/token/` | pública | JWT sólo para credenciales activas no pendientes. |

La respuesta de alta incluye `cliente_id`, nombre de presentación, `created`,
`recovered`, estado comercial, estado web, UUID de operación y contactos
enmascarados. No incluye password, token, datos capilares, roles internos ni
historial.

## 8. React

`ClienteCreationForm` y `NuevoCliente` implementan:

1. búsqueda mínima previa;
2. selección de existente;
3. email opcional y teléfono argentino;
4. alta sin campo de contraseña;
5. revisión individual de candidatos;
6. `USE_EXISTING` o `CREATE_DISTINCT` con justificación;
7. bloqueo de doble submit;
8. manejo explícito de 400/401/403/404/409;
9. clave estable y copia exacta del payload en `sessionStorage` si no hubo
   respuesta, con edición/navegación bloqueadas hasta reintentar;
10. resultado con `cliente_id`, `PENDING_CLAIM` y referencia de operación.

La ruta continúa protegida por `usuarios.create_walkin_client` mediante
`ProtectedRoute` y la API revalida el permiso. No se usa un rol nominal. El
mensaje final aclara que BH-063 es futuro y no ofrece un enlace ficticio para
crear Turnos.

Se agregaron páginas públicas de solicitud y confirmación de claim y el login
ofrece la entrada al flujo presencial.

## 9. Pruebas

### 9.1 Focales del incremento

La suite PostgreSQL `usuarios.test_walkin_client_bh064` cubre alta con/sin
email, teléfono, contactos inválidos, actividad, password inutilizable,
`PENDING_CLAIM`, cero diagnósticos, rol, permisos, coincidencias, teléfono
compartido, decisiones humanas, idempotencia, rollback, lectura mínima,
anti-enumeración, login/reset con múltiples NULL, históricos, constraints,
claim único/expirado/sin canal y tres carreras reales con threads.

Resultado limpio: **30/30**. Las carreras son:

- dos requests con la misma clave;
- dos claves sobre la misma identidad;
- dos consumos del mismo token.

React agrega/actualiza 13 casos focales para selector, existente/nuevo, email
opcional, ausencia de password, candidatos, doble submit, timeout, clave estable,
400/401/403/404/409, estado pendiente, claim y ausencia de destino BH-063.

### 9.2 Matriz y regresiones

Conteos únicos esperados después de incorporar el incremento:

| Bloque | Alcance | Resultado |
|---|---|---:|
| B1 | roles, usuarios, Personal y BH-064 funcional | 443/443 |
| B2 | diagnóstico, ficha y rutinas | 216/216 |
| B3 | agenda, Turnos y flujos profesionales | 210/210 |
| B4 | catálogos, inventario y órdenes | 79/79 |
| B5 | Caja, pagos e incidencias | 170/170 |
| B6 | Django Admin y auditoría | 43/43 |
| B7 | concurrencia PostgreSQL, incluida BH-064 | 72/72 |
| Frontend | Jest completo | 449/449 |

Total backend único: **1233/1233**. La focal BH-064 final pasó **30/30**
sobre una base PostgreSQL limpia.

El build optimizado compila. Conserva warnings históricos de ESLint,
Browserslist, tamaño de bundle y dependencia dinámica; no se introdujo un warning
nuevo del incremento.

Las ejecuciones iniciales y sus repeticiones se registran por separado en la
entrega final para no inflar el conteo único.

## 10. Contrato para BH-063 y riesgos pendientes

- `cliente_id` es estable e independiente de Turno y diagnóstico;
- un fallo futuro de reserva no debe borrar esta identidad ni su ledger;
- servicios comerciales pueden usarla porque Usuario y Cliente están activos;
- BH-063 deberá consumir el ID y definir sus propios comandos, riesgo, hold,
  pago, disponibilidad, idempotencia y auditoría;
- este incremento no cambia `PaymentPolicy`, no crea excepciones financieras,
  no implementa D-08 y no crea `EN_PROCESO`;
- continúa pendiente un canal verificable para Clientes sin email;
- los teléfonos históricos ambiguos continúan sin normalización inferida;
- el payload de una operación incierta se conserva sólo en `sessionStorage` de
  la pestaña para permitir reintento exacto; no contiene password ni token.

## 11. Estado

**VALIDADO.** B1–B7, focal BH-064, Jest completo, build, checks, migraciones,
SQL, diff y revisión de secretos aprobaron. La publicación Git se registra en
la entrega final. Este cierre no implica inicio del Incremento 2.
