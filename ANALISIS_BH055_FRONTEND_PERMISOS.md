# Análisis BH-055: frontend, sesión y permisos

## Resumen ejecutivo

El frontend actual no está preparado para representar los cuatro `BusinessRole`.
La decisión global sigue siendo binaria:

```text
is_staff = true  -> experiencia administrativa
is_staff = false -> experiencia Cliente
```

Esto entra en conflicto directo con BH-054: las cuentas SPA `EMPLEADO`,
`PROFESIONAL` y `ADMINISTRADOR` pueden y deben tener `is_staff=False`. En el
estado actual, esas cuentas son redirigidas a `/perfil`, reciben el menú de
Cliente y no pueden consumir numerosos endpoints protegidos con
`IsAdminUser`.

El backend ya tiene una matriz canónica de `BusinessRole` y permisos en
`usuarios/roles.py`, incluyendo permisos individuales. Sin embargo, no existe
un endpoint de contexto de sesión que exponga el rol y los permisos efectivos,
y buena parte de los endpoints legacy todavía autoriza con `is_staff` o
`IsAdminUser` en vez de `has_perm(...)`.

La dirección recomendada es:

1. agregar un `GET /api/usuarios/me/` de solo lectura;
2. cargarlo una vez en un `SessionContext`;
3. construir rutas, menús y acciones con permisos efectivos;
4. usar el rol solo para elegir experiencia/landing conceptual;
5. migrar la autorización backend de cada módulo antes de habilitarlo a
   EMPLEADO o PROFESIONAL.

---

## 1. Arquitectura actual

### 1.1 Flujo de login

Flujo observado en `frontend/src/pages/auth/Login.js`:

```text
POST /api/usuarios/login/
  -> backend valida email/password/is_active
  -> devuelve solamente access + refresh
  -> frontend guarda access_token y refresh_token
  -> GET /api/usuarios/perfil/
  -> guarda un resumen en localStorage.user_info
  -> decide ruta inicial usando usuario.is_staff
```

La respuesta de login definida en `usuarios/views.py::LoginView` contiene:

```json
{
  "access": "...",
  "refresh": "..."
}
```

No contiene rol, permisos ni perfiles.

### 1.2 Estado persistido en localStorage

Se guardan:

- `access_token`;
- `refresh_token`;
- `user_info` con `id`, `email`, `is_staff`, `first_name`, `last_name`.

Problema adicional: `UsuarioPerfilReadSerializer` no expone `id`, por lo que
el `id` escrito por Login en `user_info` actualmente queda `undefined`.

`user_info` no contiene:

- `business_role`;
- permisos efectivos;
- `is_active`;
- existencia/estado de Cliente;
- existencia/estado de Personal.

`frontend/src/api/axiosConfig.js` agrega el access token a las peticiones y,
ante 401, limpia la sesión y redirige a `/login`. Aunque existe
`/api/token/refresh/` en backend, no se observó un flujo frontend de renovación
automática del access token.

### 1.3 Ruta inicial

Después del login y al reingresar desde una sesión existente:

```javascript
usuario.is_staff ? '/admin-dashboard' : '/perfil'
```

Si falla la carga de `/perfil/`, el fallback también es `/perfil`.

Consecuencias actuales:

- `ADMINISTRADOR` SPA con `is_staff=False` va a `/perfil`;
- `EMPLEADO` va a `/perfil`;
- `PROFESIONAL` va a `/perfil`;
- solo una cuenta técnica con `is_staff=True` llega al dashboard admin.

### 1.4 ProtectedRoute

`frontend/src/routes/ProtectedRoute.js` solo verifica:

```javascript
Boolean(localStorage.getItem('access_token'))
```

No valida el token contra el backend y no comprueba:

- rol;
- permisos;
- actividad de la cuenta;
- perfil Cliente/Personal;
- estado activo de Personal.

Todas las rutas Cliente y todas las rutas admin usan el mismo guard. Cualquier
usuario con un string en `access_token` puede renderizar cualquier página; la
protección real queda delegada a las respuestas de cada endpoint.

### 1.5 Menú y navegación

`frontend/src/components/Header.js` vuelve a consultar `/api/usuarios/perfil/`
y calcula:

```javascript
const isAdmin = user?.is_staff;
const navLinks = isAdmin ? adminLinks : clientLinks;
```

El logo, el carrito, el menú desplegable y la etiqueta de rol también dependen
de `is_staff`. Solo hay dos etiquetas: `Administrador` y `Cliente`.

El menú admin es estático; muestra todas las secciones sin comprobar permisos.
El menú Cliente también es estático y no comprueba si realmente existe un
perfil Cliente.

`CampanaNotificaciones.js` lee `localStorage.user_info.is_staff` para decidir,
por ejemplo, si una notificación de compra debe abrir `/admin/ordenes` o
`/mis-pedidos`.

### 1.6 Router

`frontend/src/routes/index.js` separa rutas por prefijo conceptual
`CLIENTE_ROUTES` y `ADMIN_ROUTES`, pero todas están envueltas por el mismo
`ProtectedRoute` sin requisitos.

No existen rutas ni dashboards específicos para EMPLEADO o PROFESIONAL.

`DashboardAdmin.js`:

- consume `/api/gestion/admin-dashboard/stats/`;
- tiene el saludo hardcodeado `Hola, Yani`;
- muestra todas las tarjetas y accesos rápidos;
- no comprueba permisos;
- ante 403 redirige a `/perfil`;
- asume que todo usuario operativo es admin/staff.

---

## 2. Usos legacy de is_staff y rol

### 2.1 Frontend

Usos de autorización o experiencia basados en `is_staff`:

| Archivo | Uso actual | Impacto |
|---|---|---|
| `pages/auth/Login.js` | landing, etiqueta y botón de sesión | EMPLEADO/PROFESIONAL/ADMINISTRADOR SPA quedan como Cliente |
| `components/Header.js` | selección completa del menú, logo, carrito y etiqueta | navegación binaria e incompatible con permisos individuales |
| `components/CampanaNotificaciones.js` | destino de notificaciones | puede enviar personal operativo a rutas Cliente |
| `localStorage.user_info` | persiste `is_staff` como contexto | dato incompleto y manipulable utilizado para UX |

`GestionUsuarios.js` ya representa el rol listado mediante `business_role`; no
usa `is_staff` para determinar ADMINISTRADOR. Es una excepción positiva, pero
no resuelve la sesión global.

No se encontró uso frontend de `usuario.es_cliente`.

`Personal.rol` continúa apareciendo en `GestionPersonal.js`, pero allí se usa
como función laboral (`colorista`, `asistente`, `administrador`) y se muestra
separado de `usuario_business_role`. No debe reutilizarse para autorización.

El `rol` mostrado en autores de contenido educativo también es información de
presentación del Personal, no un `BusinessRole`.

### 2.2 Backend

El backend contiene dos modelos de autorización coexistentes:

1. modelo nuevo: `BusinessRole` + permisos Django + `has_perm(...)`;
2. modelo legacy: `is_staff`, `is_superuser` e `IsAdminUser`.

Los servicios semánticos de Usuarios/Personal ya usan permisos explícitos. En
cambio, numerosos viewsets legacy siguen usando `IsAdminUser` o ramas
`request.user.is_staff`.

Ejemplos relevantes:

- dashboard y reportes: `IsAdminUser`;
- listado de Clientes: `IsAdminUser`;
- listado de Usuarios: `IsAdminUser`;
- CRUD de Servicios, Rutinas, Productos, Horarios, Caja y Auditoría:
  `IsAdminUser` total o parcialmente;
- Turnos, diagnósticos, órdenes y contenido tienen ramas internas por
  `is_staff`;
- fichas técnicas exigen `IsAdminUser`, por lo que un PROFESIONAL normal no
  puede ejercer sus permisos técnicos;
- Personal mezcla `IsAuthenticated`, `IsAdminUser` y servicios semánticos con
  permisos correctos.

Por lo tanto, ocultar o mostrar nuevas rutas por permisos antes de migrar los
endpoints produciría dos fallos posibles:

- falso negativo: el frontend habilita una acción por permiso, pero backend la
  rechaza porque `is_staff=False`;
- falso positivo: una página está oculta, pero el endpoint `IsAuthenticated`
  permite una operación que debería exigir permiso.

---

## 3. Contrato actual de `/me`

No existe `GET /api/usuarios/me/`.

El equivalente utilizado es:

```http
GET /api/usuarios/perfil/
```

Está protegido con JWT + `IsAuthenticated` y devuelve exactamente los campos
de `UsuarioPerfilReadSerializer`:

- `email`;
- `first_name`;
- `last_name`;
- `is_staff`;
- datos Cliente aplanados: `zona`, `numero`, `fecha_nacimiento`, `sexo`,
  `redes`, características capilares e `historial_servicios`.

No devuelve:

- id de Usuario;
- `business_role`;
- permisos efectivos;
- `is_active`;
- existencia explícita de Cliente;
- id/estado de Cliente;
- existencia de Personal;
- id/estado de Personal;
- función laboral `Personal.rol`.

Los `null` de campos capilares no permiten distinguir de forma robusta entre
“no existe Cliente” y “Cliente existe pero todavía no completó el dato”.

Tampoco se encontró uso de `get_all_permissions()` en serializers o views. Los
permisos efectivos no se exponen actualmente por API.

Fuentes alternativas existentes, pero inadecuadas como contexto de sesión:

- `/api/gestion/admin/usuarios/` expone `business_role`, pero lista cuentas,
  requiere acceso administrativo y no expone permisos;
- `/api/gestion/personal/` expone el rol del usuario vinculado, pero lista
  Personal y no identifica de forma segura la sesión actual;
- los claims JWT estándar no contienen BusinessRole ni permisos.

---

## 4. Contrato recomendado para `/me`

Crear un endpoint dedicado, de solo lectura:

```http
GET /api/usuarios/me/
Authorization: Bearer <access>
```

Contrato mínimo recomendado:

```json
{
  "user": {
    "id": 42,
    "email": "ana@example.com",
    "first_name": "Ana",
    "last_name": "Pérez",
    "is_active": true
  },
  "business_role": "PROFESIONAL",
  "permissions": [
    "gestion.view_global_agenda",
    "gestion.create_diagnosis",
    "gestion.view_reports"
  ],
  "profiles": {
    "cliente": {
      "exists": true,
      "id": 42,
      "active": true
    },
    "personal": {
      "exists": true,
      "id": 17,
      "active": true,
      "function_role": "colorista"
    }
  }
}
```

Reglas propuestas:

- `business_role` sale exclusivamente de los grupos `BusinessRole`;
- `permissions` se calcula en cada request desde permisos efectivos Django,
  incluyendo grupo e individuales;
- idealmente se expone la intersección de `user.get_all_permissions()` con
  `BusinessPermission.ALL`, con strings completos `app_label.codename`;
- Cliente y Personal se informan de manera independiente, porque pueden
  coexistir;
- `Personal.function_role` es informativo, nunca autorización;
- `is_staff` e `is_superuser` no son necesarios para decisiones SPA y no
  deberían formar parte del contrato de autorización frontend;
- un usuario con múltiples BusinessRole debe producir un error estable y
  fallar cerrado;
- un usuario sin BusinessRole puede devolver `business_role: null`, pero no
  debe recibir una experiencia privilegiada por inferencia de perfiles.

No conviene ampliar indefinidamente `/perfil/`: ese endpoint mezcla lectura y
edición del perfil Cliente. `/me/` debe representar sesión/autorización y
`/perfil/` puede continuar representando datos personales del Cliente.

---

## 5. Matriz role / permission / pantalla / acción

### 5.1 Permisos base existentes

La matriz canónica actual de `usuarios/roles.py` es:

#### CLIENTE

No recibe permisos de negocio base. Sus operaciones actuales dependen de
autenticación y ownership: perfil propio, turnos propios, pedidos propios,
carrito y contenido publicado.

#### EMPLEADO

| Permiso existente | Pantalla/capacidad propuesta | Acción |
|---|---|---|
| `usuarios.create_walkin_client` | Clientes / acceso rápido | alta presencial de Cliente |
| `usuarios.view_clients` | Gestión de Clientes | consultar clientes |
| `gestion.view_global_agenda` | Dashboard operativo / Turnos / Agenda | consultar agenda global |
| `gestion.create_turno_for_client` | Nuevo turno | crear turno para un Cliente |
| `gestion.register_arrival` | Turnos del día | registrar llegada |
| `gestion.reprogram_any_turno` | Gestión de Turnos | reprogramar cualquier turno |
| `gestion.cancel_any_turno` | Gestión de Turnos | cancelar cualquier turno |
| `gestion.confirm_deposit` | Turnos / Caja | confirmar seña |
| `gestion.register_payment` | Turnos / Órdenes | registrar pago |
| `gestion.view_stock` | Productos/stock | consultar stock |

#### PROFESIONAL

Incluye todos los permisos de EMPLEADO y agrega:

| Permiso existente | Pantalla/capacidad propuesta | Acción |
|---|---|---|
| `gestion.create_diagnosis` | Cliente / diagnóstico | crear diagnóstico capilar |
| `gestion.manage_technical_record` | Ficha técnica | crear/editar ficha técnica |
| `gestion.manage_formulas` | Ficha técnica / fórmulas | gestionar fórmulas |
| `gestion.assign_routines` | Rutinas del Cliente | asignar rutina |
| `gestion.finalize_service` | Turnos del día | finalizar servicio |

#### ADMINISTRADOR

Recibe todos los permisos anteriores y además las capacidades administrativas:

| Permiso existente | Pantalla/capacidad propuesta | Acción |
|---|---|---|
| `usuarios.manage_users` | Usuarios | listar/editar identidad y estado de cuentas |
| `usuarios.assign_roles` | Usuarios/Personal | asignar o cambiar BusinessRole |
| `gestion.manage_payment_configuration` | Configuración/Caja | configurar pagos |
| `gestion.manage_products` | Productos | CRUD de productos |
| `gestion.manage_stock` | Productos/Órdenes | modificar stock |
| `gestion.manage_prices` | Servicios/Productos | modificar precios |
| `gestion.manage_promotions` | Productos/Promociones | administrar promociones |
| `gestion.manage_content` | Contenido educativo | administrar contenido |
| `gestion.manage_personal` | Personal | alta, estado y vínculos de Personal |
| `gestion.manage_skills` | Personal | administrar habilidades |
| `gestion.view_reports` | Reportes | ver reportes operativos |
| `gestion.view_financial_reports` | Reportes/Caja | ver información financiera |
| `gestion.view_audit` | Auditoría | consultar auditoría |
| `gestion.revert_audit` | Auditoría | revertir eventos admitidos |
| `gestion.manage_configuration` | Configuración/Agenda | administrar configuración global |

### 5.2 Matriz de rutas/pantallas

| Pantalla actual | Requisito frontend recomendado | Acciones internas adicionales |
|---|---|---|
| Perfil/Mis turnos/Mis pedidos/Carrito | perfil Cliente existente y ownership | no inferir desde BusinessRole |
| Dashboard operativo | `view_global_agenda` | tarjetas condicionadas por cada permiso |
| Nuevo turno | `create_turno_for_client` | alta Cliente separada por `create_walkin_client` |
| Gestión de Turnos | `view_global_agenda` | llegada, reprogramación, cancelación, seña, pago y finalización por permiso específico |
| Gestión de Clientes | `view_clients` | crear por `create_walkin_client`; diagnóstico/ficha/rutina por permisos técnicos |
| Agenda | `view_global_agenda` | edición global por `manage_configuration` o capacidad administrativa explícita |
| Productos | `view_stock` o `manage_products` | CRUD, stock, precios y promociones con permisos distintos |
| Usuarios | `manage_users` | cambios de rol requieren además `assign_roles` |
| Personal | `manage_personal` | roles requieren `assign_roles`; skills requieren `manage_skills` |
| Reportes | `view_reports` | bloques financieros por `view_financial_reports` |
| Caja | `register_payment` para operación | histórico/indicadores sensibles por `view_financial_reports` |
| Contenido educativo | `manage_content` para gestión global | lectura pública/autenticada permanece separada |
| Auditoría | `view_audit` | botón revertir por `revert_audit` |
| Configuración | `manage_configuration` | configuración de pagos además `manage_payment_configuration` |
| Servicios/precios | `manage_prices` | requisitos/catálogos globales pueden requerir `manage_configuration` |

Hay módulos sin un permiso perfectamente granular: equipamiento, gestión de
órdenes y CRUD del catálogo maestro de rutinas. No debe reutilizarse
`is_staff` como solución. Hasta definir una capacidad adecuada, pueden quedar
limitados conceptualmente a ADMINISTRADOR, pero esa restricción debe existir
también en backend.

### 5.3 Permisos individuales

La navegación debe basarse en el array efectivo, no en una tabla frontend
rol→permiso duplicada.

Ejemplos que deben funcionar sin cambiar el BusinessRole:

```text
PROFESIONAL + gestion.view_reports
  -> muestra Reportes

EMPLEADO + gestion.manage_stock
  -> habilita gestión de stock
```

El rol sirve para el tipo de experiencia; el permiso decide la capacidad.

---

## 6. Propuesta de dashboard EMPLEADO

### Reutilizable hoy

- estructura visual de `DashboardAdmin`;
- componente `Calendario`;
- listado y modales de `GestionTurnos`;
- formulario de `NuevoTurno`;
- alta de Cliente en `GestionClientes`;
- lectura de productos/stock de `GestionProductos`;
- componentes de agenda existentes.

### Necesita adaptación

- reemplazar `/admin-dashboard/stats/`, actualmente `IsAdminUser`, por datos
  operativos autorizados con `view_global_agenda`;
- eliminar saludo hardcodeado;
- filtrar tarjetas y accesos rápidos por permisos;
- adaptar Turnos, cuyo queryset y acciones todavía ramifican por `is_staff`;
- adaptar Clientes, actualmente protegido con `IsAdminUser`;
- separar vista de stock de las acciones de edición;
- asegurar que “nuevo cliente” y “nuevo turno” usen sus permisos específicos;
- definir si la agenda “propia” se obtiene por `Personal.usuario` y la global por
  `view_global_agenda`.

### Todavía no existe o no está cerrado

- dashboard operativo dedicado;
- endpoint seguro de próximos turnos para la sesión Personal;
- acción identificada de “registrar llegada”; el permiso existe, pero no se
  encontró una implementación equivalente claramente conectada en UI/backend;
- guard frontend por acción;
- endpoint de stock estrictamente de lectura por `view_stock`;
- políticas backend completas para pagos y órdenes basadas en permisos.

Composición propuesta:

1. próximos turnos y agenda;
2. acciones rápidas: llegada, nuevo turno, nuevo Cliente;
3. pagos/señas solo si corresponde;
4. stock de solo lectura;
5. alertas operativas permitidas.

---

## 7. Propuesta de dashboard PROFESIONAL

Se recomienda la opción **B: mismo dashboard operativo que EMPLEADO**, ampliado
por permisos técnicos.

Razones:

- PROFESIONAL hereda exactamente la base EMPLEADO en `ROLE_BASE_PERMISSIONS`;
- evita duplicar agenda, turnos, pagos y stock;
- soporta permisos individuales naturalmente;
- las diferencias técnicas se expresan como módulos adicionales.

Extensiones visibles cuando existan permisos:

- `create_diagnosis`: crear diagnóstico;
- `manage_technical_record`: ficha técnica;
- `manage_formulas`: fórmulas;
- `assign_routines`: asignar rutina;
- `finalize_service`: finalizar servicio.

Estado backend actual: estas capacidades todavía suelen exigir `is_staff` o
`IsAdminUser`. En particular, Ficha Técnica exige `IsAdminUser` y Diagnóstico
valida `request.user.is_staff`; deben migrarse antes de habilitar el dashboard a
un PROFESIONAL SPA normal.

---

## 8. Propuesta de dashboard ADMINISTRADOR

`DashboardAdmin` puede mantenerse como experiencia conceptual, pero debe pasar
de un menú monolítico a tarjetas condicionadas por permisos.

### Inventario de pantallas administrativas

| Pantalla | Permiso que debería controlar visibilidad | Estado backend actual | Migración sin lógica de negocio |
|---|---|---|---|
| Dashboard | composición por permisos; base `view_global_agenda` | stats usa `IsAdminUser` | requiere adaptar autorización y payload |
| Reportes | `view_reports`; finanzas `view_financial_reports` | stats usa `IsAdminUser` | sí, guard + permission backend |
| Nuevo Turno | `create_turno_for_client` | Turno usa `IsAuthenticated` y ramas `is_staff` | requiere endurecer backend |
| Turnos | `view_global_agenda` | queryset/acciones dependen de `is_staff` | requiere migración por acción |
| Rutinas | `assign_routines` para asignar; catálogo global pendiente de permiso exacto | escrituras `IsAdminUser` | parcial |
| Servicios | `manage_prices`; configuración global según `manage_configuration` | escrituras `IsAdminUser` | sí para autorización; revisar granularidad |
| Reglas de diagnóstico | `manage_configuration` | `IsAdminUser` | sí |
| Productos | `view_stock`, `manage_products`, `manage_stock`, `manage_prices`, `manage_promotions` | lectura pública y escrituras `IsAdminUser` | requiere separar botones/endpoints |
| Usuarios | `manage_users`; roles `assign_roles` | GET usa `IsAdminUser`; PATCH/estado ya usa servicios semánticos | parcial, base buena |
| Clientes | `view_clients`; alta `create_walkin_client` | listado usa `IsAdminUser`; alta dedicada correcta | parcial |
| Personal | `manage_personal`; roles `assign_roles`; skills `manage_skills` | mezcla `IsAuthenticated`, `IsAdminUser` y servicios correctos | parcial |
| Equipamiento | no hay permiso granular exacto; provisionalmente experiencia ADMINISTRADOR | CRUD efectivo para cualquier autenticado por defaults | no, primero cerrar backend |
| Agenda | `view_global_agenda`; edición `manage_configuration` | lectura/bloqueo mezclan `IsAuthenticated` e `IsAdminUser` | requiere cerrar backend |
| Configuración | `manage_configuration`; pagos `manage_payment_configuration` | `IsAdminUser` | sí |
| Contenido educativo | `manage_content` | autorización por `is_staff` o existencia de Personal | requiere migrar backend |
| Órdenes | `register_payment`/`manage_stock`; falta permiso exacto para gestión integral | `IsAuthenticated`, ramas `is_staff`; acciones sensibles insuficientemente separadas | primero cerrar backend |
| Caja | `register_payment` y/o `view_financial_reports` según acción | listado usa `IsAdminUser` | sí, separando lectura/operación |
| Auditoría | `view_audit`; reversión `revert_audit` | ambos usan `IsAdminUser` | sí |

### Evaluación de seguridad actual

No todas las páginas “admin” tienen una barrera backend uniforme:

- `IsAdminUser` bloquea correctamente a no-staff desde el modelo legacy, pero
  también bloquea a roles SPA autorizados;
- algunos endpoints con `IsAuthenticated` son demasiado amplios, por ejemplo
  listado de Personal, agenda/bloqueos y CRUD de equipamiento;
- órdenes de compra están bajo `IsAuthenticated`; acciones como confirmar
  entrega/cancelar no tienen una comprobación explícita de permiso y merecen
  revisión prioritaria;
- ocultar estas pantallas en React no corrige esos riesgos.

---

## 9. Arquitectura propuesta de guards y helpers

### 9.1 SessionContext

Crear un único `SessionProvider` responsable de:

- leer la presencia del token;
- consultar `/api/usuarios/me/`;
- mantener estados `loading`, `authenticated`, `anonymous`, `error`;
- conservar el contexto en memoria;
- limpiar tokens ante 401;
- refrescar sesión después de cambios de rol/estado relevantes.

No usar `localStorage.user_info` como autoridad. Si se conserva como caché de
presentación, debe considerarse no confiable y reemplazarse siempre por `/me/`.

Helpers mínimos:

```javascript
hasPermission('gestion.manage_stock')
hasAnyPermission(['gestion.view_reports', 'gestion.view_financial_reports'])
hasRole('PROFESIONAL')
hasProfile('cliente')
```

Semántica:

- `hasPermission`: acciones y capacidades;
- `hasAnyPermission`: entrada a páginas compuestas;
- `hasRole`: landing o diferencias conceptuales, no botones sensibles;
- `hasProfile`: acceso a experiencia propia de Cliente/Personal;
- backend sigue siendo la autoridad final.

### 9.2 ProtectedRoute

Extender el guard para aceptar:

```jsx
<ProtectedRoute requiredPermission="usuarios.manage_users" />
<ProtectedRoute requiredAnyPermission={[...]}/>
<ProtectedRoute allowedRoles={['EMPLEADO', 'PROFESIONAL']} />
```

También es conveniente soportar perfil requerido para páginas de ownership:

```jsx
<ProtectedRoute requiredProfile="cliente" />
```

Orden de evaluación:

1. esperar carga de sesión;
2. exigir autenticación;
3. comprobar perfil si aplica;
4. comprobar permiso(s);
5. usar rol solo cuando la ruta representa una experiencia conceptual;
6. mostrar una pantalla 403 estable, no redirigir siempre a `/perfil`.

### 9.3 Navegación declarativa

Definir un catálogo único de navegación:

```javascript
{
  label: 'Reportes',
  path: ADMIN_ROUTES.REPORTES,
  anyPermissions: ['gestion.view_reports', 'gestion.view_financial_reports']
}
```

El Header y los dashboards deben filtrar ese catálogo con los mismos helpers.
No copiar condiciones de rol en cada página.

Las acciones internas también deben usar permisos específicos. Poder entrar a
Productos por `view_stock` no debe habilitar automáticamente “Editar precio” o
“Eliminar producto”.

### 9.4 Landing recomendado

```text
CLIENTE         -> /perfil o futuro dashboard Cliente
EMPLEADO        -> /operaciones
PROFESIONAL     -> /operaciones (con módulos técnicos)
ADMINISTRADOR   -> /admin-dashboard
rol null/error  -> pantalla de cuenta sin acceso configurado
```

Si un EMPLEADO/PROFESIONAL también tiene Cliente, puede conservar accesos de
autogestión mediante `profiles.cliente.exists`; no debe perderlos por no tener
BusinessRole.CLIENTE.

---

## 10. Orden incremental de implementación

1. **Contrato de sesión backend**: crear y probar `/api/usuarios/me/` con rol,
   permisos efectivos y perfiles.
2. **SessionContext frontend**: reemplazar consultas duplicadas y dejar de usar
   `user_info.is_staff` para autorización.
3. **Login/landing/Header**: seleccionar experiencia por BusinessRole y menú por
   permisos.
4. **ProtectedRoute declarativo**: autenticación, permisos, roles y perfiles.
5. **Dashboard operativo base**: EMPLEADO y PROFESIONAL compartidos.
6. **Migrar backend de agenda/turnos/clientes** a permisos efectivos antes de
   mostrar sus acciones.
7. **Habilitar módulos técnicos PROFESIONAL**: diagnóstico, ficha, fórmulas,
   rutinas y finalización.
8. **Descomponer dashboard ADMINISTRADOR** por permisos.
9. **Migrar módulos administrativos restantes**: productos, reportes, Personal,
   Usuarios, configuración, contenido, caja y auditoría.
10. **Cerrar brechas críticas** en órdenes, equipamiento y bloqueos de agenda.
11. Eliminar `is_staff` de decisiones SPA y retirar `localStorage.user_info`
    como fuente de contexto.

Cada paso debe incorporar pruebas de:

- acceso directo por URL;
- menú visible/oculto;
- permisos individuales;
- rechazo backend aunque se manipule el frontend;
- coexistencia Cliente + Personal.

---

## 11. Riesgos

1. **Administrador SPA inutilizable hoy**: `ADMINISTRADOR` con `is_staff=False`
   recibe experiencia Cliente y falla contra endpoints `IsAdminUser`.
2. **Falsa seguridad frontend**: `ProtectedRoute` solo revisa presencia de un
   token.
3. **Matriz declarada pero no aplicada**: muchos permisos existen en
   `BusinessPermission`, pero los endpoints todavía no llaman `has_perm`.
4. **Endpoints demasiado amplios**: hay operaciones sensibles protegidas solo
   con `IsAuthenticated`.
5. **Permisos individuales invisibles**: no existe API para exponerlos; una
   navegación basada solo en rol los ignoraría.
6. **Perfiles coexistentes**: inferir experiencia desde “tiene Cliente” o “tiene
   Personal” sería incorrecto.
7. **Personal.rol ambiguo**: es función laboral y no puede usarse como rol de
   acceso.
8. **Contexto duplicado**: Login, Header y localStorage mantienen copias
   parciales que pueden quedar desincronizadas.
9. **Refresh token no integrado**: una expiración de access token termina la
   sesión aunque exista refresh token.
10. **Rutas hardcodeadas**: varios componentes navegan directamente a
    `/admin-dashboard` o `/perfil`, dificultando un landing por capacidades.
11. **Falta de permisos granulares en algunos módulos**: equipamiento, órdenes
    y catálogo global de rutinas requieren una decisión backend explícita.

---

## 12. Primer cambio recomendado

El primer cambio de BH-055 debería ser exclusivamente el contexto de sesión:

```text
GET /api/usuarios/me/
```

Debe devolver id, identidad, `BusinessRole`, permisos efectivos y estado de los
perfiles Cliente/Personal. Debe incluir pruebas para:

- cada uno de los cuatro BusinessRole;
- permisos heredados por grupo;
- permisos individuales adicionales;
- Cliente y Personal coexistentes;
- Personal inactivo;
- usuario sin rol;
- múltiples roles, fallando cerrado;
- ausencia de `is_staff` como decisión de negocio.

Después, implementar `SessionContext` sin cambiar todavía todos los dashboards.
Ese orden crea una única fuente de verdad y permite migrar Login, Header,
ProtectedRoute y las páginas de forma incremental, sin duplicar la matriz de
permisos backend en React.
