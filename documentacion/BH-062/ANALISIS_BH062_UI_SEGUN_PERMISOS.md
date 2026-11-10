# BH-062 — Análisis de UI según permisos efectivos

**Fecha:** 2026-11-10

**Baseline publicado inspeccionado:**
`2ce3aaff24bfd43cfc56f196748b0b69fb634a1b`

**Rama:** `save/work-in-progress`

**Modalidad:** análisis estático de frontend React, contrato de sesión, APIs,
autorizaciones backend y pruebas existentes. No se modificaron implementación,
tests, migraciones, configuración ni auditorías cerradas. Tampoco se ejecutó
nuevamente la matriz completa de BH-060.

## 1. Objetivo, alcance y veredicto

BH-062 no puede resolverse únicamente ocultando enlaces. La UI debe representar
la autoridad efectiva en cinco niveles distintos:

1. destino inicial y navegación;
2. acceso por URL directa;
3. datos que puede consultar cada pantalla;
4. acciones y campos que puede operar dentro de una pantalla parcialmente
   habilitada;
5. pérdida o cambio de capacidades durante una sesión abierta.

La base actual es válida y reutilizable: `/api/usuarios/me/` entrega el
`BusinessRole`, los permisos Django efectivos y los perfiles; `SessionContext`
los centraliza; `ProtectedRoute` protege la mayoría de las rutas; y varias
pantallas ya separan correctamente permisos de lectura y escritura.

Sin embargo, **BH-062 requiere implementación**. Se confirmó una brecha alta de
autoridad backend en contenido educativo y varias brechas medias de
representación frontend:

- las tres rutas administrativas de contenido educativo requieren sólo sesión;
- `ContenidoEducativoViewSet.perform_destroy()` no valida ni
  `gestion.manage_content` ni autoría, por lo que un Cliente autenticado puede
  borrar lógicamente contenido publicado y un Personal puede borrar contenido
  ajeno visible;
- `/me/` no informa capacidades compuestas que el backend calcula con permiso,
  Personal activo y habilidad `DIAGNOSTICO` activa;
- revisión técnica y fórmulas pueden aparecer habilitadas y terminar en 403;
- controles de creación de administradores y de vínculo/rol de Personal omiten
  `usuarios.assign_roles`;
- landing, destinos de notificaciones y dos entradas del menú todavía usan
  `BusinessRole` como restricción adicional aunque las rutas aceptan permisos
  efectivos;
- la sesión se refresca al montar y al iniciar sesión, pero no cuando otro actor
  revoca permisos, cambia el rol o desactiva Personal;
- fichas técnicas, diagnósticos y finalización técnica tienen componentes o APIs,
  pero no una superficie React integrada y enrutable por capacidades.

> **Veredicto:** `BH-062 — ANÁLISIS COMPLETADO; IMPLEMENTACIÓN PENDIENTE`.

## 2. Conceptos que no deben mezclarse

| Concepto | Fuente | Uso legítimo en frontend | No debe usarse como |
|---|---|---|---|
| `BusinessRole` | Uno de los grupos canónicos `CLIENTE`, `EMPLEADO`, `PROFESIONAL`, `ADMINISTRADOR`. | Identidad de negocio, experiencia inicial y casos cuyo contrato exige realmente ese rol. | Sustituto de permisos efectivos. |
| Permisos Django efectivos | `Usuario.get_all_permissions()`, limitado por `/me/` a `BusinessPermission.ALL`. Incluye rol, grupos técnicos y permisos individuales. | Fuente primaria para rutas, módulos y acciones simples. | Prueba suficiente de una capacidad compuesta con habilidad o ownership. |
| `Usuario.is_staff` | Flag técnico de Django. | Acceso técnico a Django Admin fuera de la autorización de negocio de la SPA. | Rol administrador de la SPA. |
| `Usuario.is_superuser` | Bypass técnico de Django. | No debe proyectarse ni utilizarse en decisiones normales de la SPA. | `BusinessRole.ADMINISTRADOR`. |
| `Personal.rol` / `function_role` | Función laboral, por ejemplo `colorista` o `asistente`. | Etiqueta y contexto funcional. | BusinessRole, permiso o habilidad. |
| Habilidades técnicas | `PersonalHabilidad.activa`, `Habilidad.activa` y Personal activo. | Condición adicional para acciones técnicas concretas. | Permiso Django o inferencia desde `Personal.rol`/flags `realiza_*`. |
| `Usuario.is_active` | Estado principal de cuenta. | La autenticación debe fallar o perderse al desactivarse. | Estado laboral de Personal. |
| `Personal.activo` | Estado del vínculo laboral. | Habilita agenda propia y participa en habilidades efectivas. | Estado de cuenta ni revocación automática de todos los permisos Django. |
| `Cliente.activo` | Estado del perfil Cliente. | Condición de operaciones propias que así lo exijan. | Permiso administrativo. |

Evidencia principal:

- `bohemiacore/usuarios/roles.py:10-127` define ambos catálogos y su contrato;
- `bohemiacore/usuarios/serializers.py:113-153` excluye deliberadamente
  `is_staff`/`is_superuser` de `/me/` y expone perfiles por separado;
- `bohemiacore/gestion/permissions.py:149-235` demuestra que permiso y habilidad
  son condiciones independientes;
- `frontend/src/context/SessionContext.test.js:291-310` verifica que
  `is_staff` almacenado localmente no autoriza nada.

## 3. Arquitectura actual de autenticación y autorización frontend

### 3.1 Autenticación y tokens

1. `Login.js` envía credenciales a `/api/usuarios/login/`.
2. Los access/refresh tokens se guardan en `localStorage`.
3. Tras el login, `refreshSession()` consulta `/api/usuarios/me/` antes de
   seleccionar el destino inicial.
4. El interceptor global de Axios agrega el bearer token a las peticiones.
5. Ante un 401 global, `axiosConfig.js:27-40` elimina tokens y `user_info`, y
   fuerza `window.location.href = '/login'`.
6. `SessionContext` también trata un 401 de `/me/` como sesión anónima.

No se observó renovación automática del access token. El logout intenta
blacklistear el refresh token y luego limpia el estado local.

### 3.2 Fuente actual de verdad del usuario autenticado

`GET /api/usuarios/me/` es una proyección propia y de sólo lectura. Devuelve:

```json
{
  "user": {
    "id": 42,
    "email": "persona@example.com",
    "first_name": "Persona",
    "last_name": "Ejemplo",
    "is_active": true
  },
  "business_role": "PROFESIONAL",
  "permissions": ["gestion.manage_formulas"],
  "profiles": {
    "cliente": {"exists": false, "id": null, "active": null},
    "personal": {
      "exists": true,
      "id": 17,
      "active": true,
      "function_role": "colorista"
    }
  }
}
```

Aspectos correctos:

- `CurrentSessionSerializer.get_permissions()` usa
  `get_all_permissions()` y conserva sólo `BusinessPermission.ALL`;
- reconoce por igual grants de rol, grupo técnico o permiso individual;
- un superusuario obtiene por Django todos los permisos y, por lo tanto, la
  intersección proyecta todos los códigos de negocio, pero la SPA no recibe ni
  consulta el flag `is_superuser` ni intenta reconstruir ese origen;
- no expone orígenes de grants, otros grupos, permisos fuera del catálogo,
  `is_staff` ni `is_superuser`;
- una inconsistencia de múltiples BusinessRole responde 409 con
  `MULTIPLE_BUSINESS_ROLES`, y React falla cerrado;
- es una proyección mínima distinta del resumen administrativo de BH-059. No
  corresponde enviar al propio usuario orígenes, drift, flags técnicos ni
  advertencias administrativas de terceros.

Límite actual: los permisos simples no expresan las capacidades compuestas del
backend. Tener `gestion.manage_formulas`, por ejemplo, no implica poder editar
fórmulas si falta la habilidad técnica efectiva.

### 3.3 Estado React

`frontend/src/context/SessionContext.js` conserva:

- `status`: `loading`, `authenticated`, `anonymous` o `error`;
- `user`, `businessRole`, `permissions`, `profiles` y `error`;
- helpers `hasPermission`, `hasAnyPermission`, `hasRole`, `hasProfile` y
  `hasActiveProfile`;
- operaciones `refreshSession()` y `clearSession()`.

La sesión se consulta al montar el provider y tras el login. Una búsqueda de
callsites sólo encontró uso productivo adicional en `Login.js`; no hay polling,
refresco al recuperar foco, invalidación por 403 ni evento entre pestañas.

### 3.4 Controles de acceso

| Capa | Implementación | Evaluación |
|---|---|---|
| Ruta | `ProtectedRoute.js` admite perfil, perfil activo, permiso, cualquiera de varios permisos y roles. | Correcto como guard declarativo. Falla cerrado ante sesión inválida o BusinessRole ausente. No conoce capacidades compuestas. |
| Declaración de rutas | `frontend/src/routes/index.js`. | La mayoría de las rutas administrativas ya declara permisos efectivos. Contenido educativo es la excepción crítica. |
| Navegación | `navigationConfig.js` filtra con los mismos helpers. | Buena base, pero Usuarios y Auditoría agregan `allowedRoles: ['ADMINISTRADOR']`, y faltan entradas para rutas legítimas. |
| Pantallas | Varias páginas usan `useSession()` para capacidades por acción. | Correcto en Turnos, Personal/habilidades, productos/stock, caja y usuarios, con brechas puntuales. |
| Backend | Clases DRF, ownership y servicios semánticos. | Sigue siendo la autoridad. La UI nunca debe considerarse una barrera de seguridad. |

### 3.5 401, 403 y errores de negocio

- **401:** existe tratamiento global destructivo y tratamiento propio de
  `SessionContext`. Es seguro, aunque la redirección imperativa no sincroniza
  elegantemente el árbol React antes de navegar.
- **403:** no existe coordinación global. Algunas pantallas muestran mensajes
  específicos (`GestionTurnos`, `GestionUsuarios`, caja e incidencias), otras
  muestran errores genéricos y otras sólo escriben en consola.
- **409/validación:** los flujos recientes de Turnos, stock, usuarios y finanzas
  distinguen conflictos de permisos; pantallas legacy todavía mezclan 403,
  validación y red.
- Un 403 no provoca relectura de `/me/`; por ello una revocación puede dejar
  visibles rutas y botones obsoletos después de que el backend ya niega la
  acción.

## 4. Inventario de rutas React

### 4.1 Sesión y Cliente

| Ruta o grupo | Guard actual | Autoridad efectiva esperada | Estado |
|---|---|---|---|
| `/operaciones` | Cualquiera de nueve permisos operativos/financieros. | Permisos efectivos por tarjeta y acción. La página además puede leer agenda propia de Personal activo. | Parcial: un Personal activo sin esos nueve permisos no entra aunque tenga agenda propia válida. |
| `/mi-agenda-laboral` | Personal activo. | Ownership del Personal autenticado; llegada requiere `register_arrival`. | Correcto. |
| `/revision-tecnica` | `review_technical_booking` + Personal activo. | Lo anterior + habilidad `DIAGNOSTICO` activa. | Incompleto: permite una ruta que el backend rechazará. |
| Rutas Cliente (`/perfil`, reservas, turnos, pedidos, rutinas, catálogos, carrito y contenido) | Existencia de perfil Cliente. | Ownership/lectura pública según endpoint y, donde aplique, Cliente activo. | En general correcto por scope backend; el guard no distingue perfil inactivo. |
| Retornos de compra | Perfil Cliente. | Ownership financiero backend. | Correcto. |

### 4.2 Administración

| Ruta | Guard actual | Resultado |
|---|---|---|
| `/admin-dashboard` | `gestion.view_reports` | Correcto para sus estadísticas. El landing por rol puede enviar aquí a un administrador sin ese permiso. |
| `/admin/reportes` | `view_reports` o `view_financial_reports` | Correcto; `DashboardStats` oculta cada proyección y el backend limita la respuesta. |
| `/admin/nuevo-turno` | `create_turno_for_client` | Correcto. |
| `/admin/turnos` | `view_global_agenda` | Correcto; acciones internas se separan. |
| `/admin/agenda` | `view_global_agenda` | Correcto para lectura. Las escrituras legacy están deshabilitadas en UI. |
| `/admin/gestionar-rutinas` y detalle | `assign_routines` | Correcto para la superficie administrativa. |
| `/admin/servicios` | `manage_prices` o `manage_formulas` | Parcial: fórmulas requieren además habilidad activa. |
| `/admin/reglas`, `/admin/equipamiento`, `/admin/configuracion` | `manage_configuration` | Correcto. |
| `/admin/productos` | Alguno de cinco permisos de catálogo/stock/precio/promoción | Correcto como pantalla parcial. |
| `/admin/usuarios` | `manage_users` | Correcto para lectura/estado; las acciones de rol y alta de administrador requieren también `assign_roles`. |
| `/admin/clientes` | `view_clients` | Correcto; crear Cliente se filtra con permiso aparte. |
| `/admin/clientes/nuevo` | `create_walkin_client` | Correcto. |
| `/admin/personal` | `manage_personal` o `manage_skills` | Correcto como pantalla parcial; acciones de vínculo y rol omiten `assign_roles` en UI. |
| `/admin/ordenes` | `manage_stock` | Correcto para gestión global de entrega/cancelación. |
| `/admin/caja` | Registro, conciliación o reporte financiero | Correcto como pantalla parcial. |
| `/admin/incidencias-financieras` | `reconcile_external_payment` | Correcto. |
| `/admin/auditoria` | `view_audit` | Correcto en ruta; el menú impone además BusinessRole administrador. |
| Tres rutas `/admin/contenido-educativo*` | Sólo autenticación. | Incorrecto. Deben distinguir autor de contenido y administración global. |

No existen rutas React para `RegistroFichaTecnica`, `VisualizadorFichas`,
diagnóstico profesional ni finalización de Servicio. Los dos primeros
componentes existen aislados y `fichasTecnicasApi.js` expone CRUD, pero no están
integrados a `routes/index.js` ni a una pantalla operativa.

## 5. Matriz pantalla × acción × permiso × endpoint

La tabla expresa la autoridad backend observada. “Propio” significa que la API
aplica ownership; no equivale a un permiso administrativo.

### 5.1 Clientes, Turnos y agenda

| Pantalla / acción | Permiso o condición | Endpoint principal | Control frontend actual | Evaluación |
|---|---|---|---|---|
| Cartera de Clientes: listar | `usuarios.view_clients` | `GET /api/usuarios/clientes/` | Ruta y mensaje 403. | Correcto. |
| Cartera: crear Cliente presencial | `usuarios.create_walkin_client` | `POST /api/usuarios/admin/clientes/crear/` | Botón condicional y ruta propia. | Correcto. |
| Nuevo Turno para Cliente: selectores/crear | `gestion.create_turno_for_client` | `GET .../turnos/selector-clientes/`; `POST .../turnos/crear-para-cliente/` | Ruta protegida. | Correcto. |
| Agenda global: listar | `gestion.view_global_agenda` | `GET /api/gestion/turnos/` | Ruta y error 403 específicos. | Correcto. |
| Registrar llegada | `gestion.register_arrival` | `POST .../turnos/{id}/registrar-llegada/` | Botón condicional en Operaciones y Gestión Turnos. | Correcto. |
| Reprogramar cualquier Turno | `gestion.reprogram_any_turno` + estado válido | `POST .../turnos/{id}/reprogramar/` | Botón condicional y validación de estado. | Correcto. |
| Cancelar cualquier Turno | `gestion.cancel_any_turno` + estado válido | `POST .../turnos/{id}/cancelar/` | Botón condicional y validación de estado. | Correcto. |
| Agenda laboral propia | Personal activo y ownership | `GET .../turnos/mi-agenda-laboral/` | Ruta por Personal activo. | Correcto. |
| Finalizar Servicio | `gestion.finalize_service` + `gestion.create_diagnosis` + habilidad `DIAGNOSTICO` | `POST .../turnos/{id}/finalizar_turno/` | No hay acción productiva React. | Funcionalidad backend no representada. |
| Revisión técnica: cola y decisión | `review_technical_booking` + Personal/habilidad `DIAGNOSTICO` activos | `GET .../solicitudes-tecnicas/cola/`; `POST .../{id}/revisar/` | Ruta sólo verifica permiso + Personal activo; todos los botones se muestran. | 403 evitable si falta habilidad. |

### 5.2 Servicios, fórmulas, rutinas y registros técnicos

| Pantalla / acción | Permiso o condición | Endpoint | Control frontend actual | Evaluación |
|---|---|---|---|---|
| Servicios: catálogo | Lectura pública; datos internos condicionados | `GET /api/gestion/servicios/` | Se entra por permiso de escritura. | Sin exposición adicional; no es una pantalla de sólo lectura. |
| Crear/eliminar Servicio | `gestion.manage_prices` | `POST/DELETE .../servicios/` | Botones/campos por `manage_prices`. | Correcto. |
| Editar precio/metadata | `gestion.manage_prices` | `PATCH .../servicios/{id}/` | Payload parcial por permiso. | Correcto. |
| Editar fórmula | `gestion.manage_formulas` + habilidad `DIAGNOSTICO` activa | `PATCH .../servicios/{id}/` | Sólo comprueba `manage_formulas`. | Incompleto. |
| Rutinas: listar catálogo | Usuario activo; publicadas salvo `assign_routines` | `GET /api/gestion/rutinas/` | Rutas Cliente o administrativa. | Correcto. |
| Rutinas: crear/editar/publicar/obsoletar/eliminar/ver usuarios | `gestion.assign_routines` | CRUD y acciones de `/rutinas/` | Ruta administrativa única. | Correcto. |
| Reglas de diagnóstico | `gestion.manage_configuration` | CRUD `/reglas-diagnostico/` y `/configuracion-diagnostico/` | Ruta protegida. | Correcto. |
| Diagnóstico: crear/editar | `gestion.create_diagnosis` + habilidad `DIAGNOSTICO` activa | CRUD `/diagnosticos-capilares/` | No hay pantalla profesional integrada. | Faltante frontend. |
| Diagnóstico: leer global | `manage_technical_record` + habilidad activa; Cliente lee propio | `GET /diagnosticos-capilares/` | Cliente consume su perfil; no hay visor técnico integrado. | Parcial. |
| Ficha técnica: leer | Cliente activo propio, o `manage_technical_record` + habilidad activa | `GET /fichas-tecnicas/` | Componentes no enrutados. | Faltante frontend. |
| Ficha técnica: crear/editar | `manage_technical_record` + habilidad activa | CRUD `/fichas-tecnicas/` | Componente aislado sin guard. | Faltante frontend; no debe enrutarse sin capacidad compuesta. |

### 5.3 Productos, stock, promociones y órdenes

| Pantalla / acción | Permiso | Endpoint | Control frontend actual | Evaluación |
|---|---|---|---|---|
| Catálogo de productos | Público; stock interno sólo con autoridad | `GET /productos/` | Pantalla administrativa admite acceso parcial. | Correcto. |
| Ver stock y movimientos | `gestion.view_stock` | `stock_bajo`, `stock-movements`, ledger | Columnas, tabs y consultas condicionales. | Correcto. |
| Recibir/ajustar stock | `gestion.manage_stock` | `POST .../stock/receive` y `stock/adjust` | Formularios condicionales. | Correcto. |
| Crear producto | `manage_products` **y** `manage_prices` | `POST /productos/` | Botón requiere ambos. | Correcto. |
| Editar metadata / precio | `manage_products` / `manage_prices` | `PATCH /productos/{id}/` | Campos y payload separados. | Correcto. |
| Desactivar/eliminar producto/categoría | `manage_products` + reglas de negocio | acciones de productos/categorías | Botones condicionales y restricciones de stock. | Correcto. |
| Gestionar promociones | `manage_promotions` | CRUD y acciones `/promociones/` | Tab y acciones condicionales. | Correcto. |
| Ver todas las órdenes | `manage_stock` | `GET /ordenes-compra/` | Ruta protegida. | Correcto. |
| Confirmar entrega/cancelar | `manage_stock` + estado válido | acciones de `/ordenes-compra/{id}/` | Botones por permiso y estado. | Correcto. |
| Pedidos de Cliente | Perfil/ownership | `GET /ordenes-compra/` | Ruta Cliente y queryset propio. | Correcto. |

### 5.4 Personal, habilidades, usuarios y roles

| Pantalla / acción | Permiso | Endpoint | Control frontend actual | Evaluación |
|---|---|---|---|---|
| Personal: leer datos completos/crear/editar | `gestion.manage_personal` | CRUD `/personal/` | Ruta parcial y controles condicionales. | Correcto. |
| Personal: desactivar/reactivar/revocar acceso | `manage_personal` + reglas semánticas | acciones `/personal/{id}/...` | Controles por `manage_personal`. | Correcto. |
| Catálogo/directorio/asignación de habilidades | `gestion.manage_skills` | `/habilidades/`, `directorio-habilidades` y acciones | Para skills-only usa proyección mínima, sin contacto. | Correcto y sin filtración. |
| Crear/vincular acceso de Personal | `manage_personal` + `usuarios.assign_roles` | `crear-acceso`, `vincular-usuario` | Se muestra sólo con `manage_personal`. | Incorrecto: 403 evitable. |
| Cambiar rol laboral de acceso | `manage_personal` + `assign_roles` | `cambiar-rol-acceso` | Se muestra sólo con `manage_personal`. | Incorrecto: 403 evitable. |
| Usuarios: listar, identidad, resumen y estado | `usuarios.manage_users` | `/admin/usuarios/` y acciones | Ruta y acciones. | Correcto. |
| Cambiar BusinessRole | `manage_users` + `assign_roles` | `cambiar-rol-negocio` | Botón comprueba ambos. | Correcto. |
| Crear administrador SPA | `manage_users` + `assign_roles` | `POST /usuarios/admin/administradores/crear/` | Botón visible para todo `manage_users`. | Incorrecto: 403 evitable. |
| Navegar desde Usuarios a Clientes/Personal/Dashboard | permisos de cada destino | rutas React respectivas | Links incondicionales. | Restricción/denegación evitable. |

### 5.5 Configuración, reportes, pagos, incidencias y auditoría

| Pantalla / acción | Permiso | Endpoint | Control frontend actual | Evaluación |
|---|---|---|---|---|
| Configuración y catálogos: CRUD | `gestion.manage_configuration` | `/configuracion/` y catálogos | Ruta única. | Correcto. El botón “Volver” siempre apunta a Dashboard, que puede no estar autorizado. |
| Equipamiento: lectura operativa | `view_global_agenda` o `manage_configuration`, según endpoint | `/equipamiento/` | La pantalla de gestión exige `manage_configuration`. | Correcto para CRUD. |
| Equipamiento: escritura | `manage_configuration` | CRUD `/equipamiento/` | Ruta protegida. | Correcto. |
| Dashboard | `gestion.view_reports` | `GET /admin-dashboard/stats/` | Ruta protegida y links rápidos filtrados. | Correcto en datos; una tarjeta de Turnos navega sin comprobar `view_global_agenda`. |
| Reportes generales/financieros | `view_reports` / `view_financial_reports` | `GET /stats/` | La pantalla admite cualquiera y separa visualización/exportación. | Correcto. |
| Caja: consultar obligaciones | registro, conciliación o reporte financiero | `/payment-intents/` | `canRead`. | Correcto. |
| Caja: registrar efectivo/transferencia | `gestion.register_payment` | `POST .../payments/` | Formularios por `canRegister`. | Correcto. |
| Caja: conciliar comprobante | `gestion.confirm_deposit` | `POST /payments/{id}/reconcile/` | Acciones por `canReconcile`. | Correcto. |
| Incidencias financieras | `reconcile_external_payment` | `/financial-cases/` y comandos | Ruta, pantalla y mensajes dedicados. | Correcto. |
| Auditoría: leer/revertir | `view_audit` / `revert_audit` | `/auditoria/` y `/auditoria-historial/` | Ruta por lectura; backend separa reversión. | Correcto en ruta/acción; menú restringe además por rol. |

### 5.6 Contenido educativo

| Acción | Autoridad esperada mínima | Backend actual | Frontend actual |
|---|---|---|---|
| Ver contenido publicado propio de Cliente | Perfil/ownership según interacción | Autenticado; queryset publicado para no Personal. | Rutas Cliente separadas. |
| Crear contenido | Personal activo apto para autoría, o política explícita equivalente | Sólo exige que exista `perfil_profesional`; no verifica que esté activo. | Cualquier autenticado entra al editor y ve “Crear”. |
| Ver borradores globales | `gestion.manage_content`; un autor sin autoridad global sólo debería ver lo propio | Cualquier usuario con cualquier Personal ve todo contenido activo. | Pantalla de gestión para cualquier autenticado. |
| Editar | Autor del contenido o `manage_content` | Esta comprobación sí existe. | Botón “Editar” en todos los elementos visibles. |
| Publicar/archivar | Debe definirse expresamente: autor o `manage_content`; no inferirlo del rol | Usa el mismo update/ownership. | Botones para todos los elementos visibles. |
| Eliminar/desactivar | Autor o `manage_content` | **No hay comprobación en `perform_destroy()`.** | Botón para todos los elementos visibles. |

Esta superficie requiere corrección backend antes o en el primer incremento de
BH-062. Una mejora visual aislada dejaría abierta la operación HTTP directa.

## 6. Brechas y riesgos priorizados

La clasificación consolidada contiene **1 hallazgo alto, 7 medios y 3 bajos**.

### 6.1 Severidad alta

#### A-1 — Eliminación no autorizada y visibilidad excesiva en contenido educativo

**Evidencia:**

- rutas sólo autenticadas en `frontend/src/routes/index.js:142-145`;
- controles incondicionales en
  `GestionContenidoEducativo.js:55-89,121-127,289+`;
- `permission_classes = [IsAuthenticated]` y queryset por mera existencia de
  Personal en `gestion/views.py:6519-6557`;
- `perform_destroy()` sin autorización en `gestion/views.py:6584-6588`.

**Impacto:** desactivación de contenido publicado por un Cliente y de contenido
ajeno por un Personal; exposición de borradores a Personal sin
`manage_content` ni ownership.

**Tratamiento:** contener primero la API con permisos/ownership/estado activo y
tests negativos; después alinear rutas y controles. No considerar la ocultación
del botón una mitigación suficiente.

### 6.2 Severidad media

#### M-1 — Capacidades técnicas compuestas no representables

`CanReviewTechnicalBooking`, `CanCreateDiagnosisWithSkill`,
`CanManageTechnicalRecordWithSkill` y la rama de `CanManagePricesOrFormulas`
exigen habilidad `DIAGNOSTICO` activa además del permiso. `/me/` no expone ni la
habilidad ni el resultado compuesto. La UI ofrece revisión/fórmulas con el
permiso simple y recibe 403.

#### M-2 — Contexto de sesión desactualizado

Cambiar BusinessRole, revocar permisos, desactivar Personal o revocar una
habilidad en otra sesión no modifica el snapshot React. Los permisos Django se
aplican de inmediato en backend, pero rutas, menú y botones quedan obsoletos
hasta recarga completa. Un 403 tampoco invalida el snapshot.

La desactivación de cuenta terminará en 401 en la siguiente petición
autenticada; hasta esa petición la UI puede seguir mostrando información ya
cargada. La blacklist de refresh no invalida por sí sola un access token ya
emitido, aunque la regla de autenticación consulta `is_active`.

#### M-3 — BusinessRole restringe navegación legítima

- Usuarios y Auditoría requieren `ADMINISTRADOR` en el menú, aunque sus rutas y
  APIs aceptan permisos efectivos de grupos técnicos o individuales;
- `notificationNavigation.js:20-32` exige rol administrador para Turnos y
  Órdenes; además, acepta `register_payment` como destino de Órdenes aunque esa
  ruta requiere `manage_stock`;
- `sessionLanding.js:22-29` siempre envía al administrador al Dashboard, aunque
  no tenga `view_reports`, y no selecciona el primer destino realmente
  habilitado.

Esto no concede autoridad, pero bloquea o degrada experiencias legítimas.

#### M-4 — Acciones compuestas de roles visibles sin `assign_roles`

- “Nuevo administrador” aparece con `manage_users` aunque el servicio exige
  también `assign_roles`;
- crear/vincular acceso y cambiar rol de Personal aparecen con
  `manage_personal` aunque los servicios exigen también `assign_roles`.

El backend niega correctamente; la UI genera 403 evitables y comunica de forma
engañosa que la acción está disponible.

#### M-5 — Superficies técnicas incompletas

No hay rutas ni flujo integrado para finalizar Servicio, crear/consultar
diagnósticos profesionales o crear/consultar fichas técnicas. Los componentes
aislados contienen comentarios legacy “admins/staff” y un cliente Axios propio,
sin el contrato de capacidades actual. No deben conectarse sin revisar primero
ownership, acciones permitidas y capacidad compuesta.

#### M-6 — Navegación incompleta o destinos de retorno no autorizados

Servicios, gestión de rutinas, agenda, equipamiento/reglas y contenido no tienen
entrada principal equivalente a sus rutas. Varias sólo se descubren desde el
Dashboard, que requiere un permiso diferente (`view_reports`). Además:

- Gestión de Usuarios muestra links a Dashboard, Clientes y Personal sin
  comprobar permisos del destino;
- Configuración siempre vuelve al Dashboard;
- la tarjeta “Solicitudes Nuevas” del Dashboard siempre navega a Turnos, aunque
  falte `view_global_agenda`;
- `/operaciones` no admite como única condición el Personal activo que sí puede
  consultar agenda propia.

#### M-7 — 403 no sincroniza autoridad ni tiene semántica uniforme

Algunas pantallas distinguen permiso, conflicto y validación; otras convierten
cualquier fallo en “Error al cargar/guardar”. En particular, contenido,
servicios y componentes técnicos no diferencian revocación de permiso, falta de
habilidad, ownership, validación y red.

### 6.3 Severidad baja

#### B-1 — Pantalla de acceso denegado sin salida segura

`AccesoDenegado.js` ofrece un mensaje estable que no filtra permisos internos,
pero no incluye retorno al primer destino autorizado ni reintento de sesión.

#### B-2 — Terminología administrativa en frontend

Persisten textos y comentarios “admin/staff” en componentes cuya autoridad real
son permisos efectivos. No alteran la seguridad, pero favorecen futuras
regresiones conceptuales.

#### B-3 — Estados vacíos ambiguos

En algunas pantallas una lista vacía, un 403 o una proyección parcial pueden
verse igual. Debe distinguirse “sin datos”, “sin acceso a esta sección” y “no se
pudo contactar al servidor”.

## 7. Funcionalidades ya correctamente protegidas

No deben reescribirse indiscriminadamente:

- `/me/` combina permisos efectivos de grupos e individuales y filtra el
  catálogo de negocio;
- `ProtectedRoute` prueba URL directa y falla cerrado;
- `is_staff` local no participa en autorización React;
- Turnos separa agenda, alta, llegada, reprogramación y cancelación;
- Personal ofrece una proyección mínima al gestor de habilidades y oculta
  contacto cuando falta `manage_personal`;
- productos separa catálogo, precios, metadata, lectura de stock, mutación de
  stock y promociones, incluso a nivel de campos y payload;
- órdenes separa ownership de Cliente y gestión global por stock;
- reportes separa proyección general de montos financieros;
- caja separa lectura, registro y conciliación;
- incidencias financieras y auditoría usan permisos efectivos;
- usuarios separa `manage_users` de `assign_roles` en el cambio general de rol;
- el backend protege diagnósticos, fichas y revisión técnica con habilidad
  canónica y no con `Personal.rol` o flags legacy.

## 8. Contrato mínimo de capacidades propuesto

### 8.1 Decisión

Mantener `/api/usuarios/me/` como fuente del propio usuario. No reutilizar la
proyección administrativa de BH-059 y no exponer orígenes, grupos, grants,
`is_staff`, `is_superuser`, habilidades completas ni información de terceros.

Conservar `permissions` para todas las decisiones simples y agregar únicamente
resultados booleanos para operaciones cuyo backend combina condiciones que la
SPA no puede calcular de forma confiable:

```json
{
  "permissions": ["gestion.manage_formulas"],
  "capabilities": {
    "technical_booking.review": false,
    "diagnosis.create": false,
    "technical_record.read_global": false,
    "technical_record.manage": false,
    "service_formula.manage": false,
    "content.author": true,
    "content.manage_global": false
  }
}
```

Semántica sugerida:

| Capacidad | Cálculo backend |
|---|---|
| `technical_booking.review` | Usuario activo + `review_technical_booking` + Personal/habilidad `DIAGNOSTICO` activos. |
| `diagnosis.create` | Usuario activo + `create_diagnosis` + habilidad efectiva. |
| `technical_record.read_global` | Usuario activo + `manage_technical_record` + habilidad efectiva. No sustituye ownership Cliente. |
| `technical_record.manage` | Usuario activo + `manage_technical_record` + habilidad efectiva. |
| `service_formula.manage` | Usuario activo + `manage_formulas` + habilidad efectiva. |
| `content.author` | Usuario y Personal activos y política de autoría confirmada. |
| `content.manage_global` | Usuario activo + `manage_content`. |

No es necesario incluir capacidades que sean idénticas a un permiso simple.
Tampoco se debe enviar el listado de habilidades para que React reconstruya la
regla: esa lógica pertenece al backend y podría divergir.

Si UX necesita explicar una capacidad técnica denegada, puede inferir una
“condición técnica no vigente” cuando el permiso simple existe y la capacidad
es falsa. No hace falta revelar asignaciones administrativas ni el detalle de
la habilidad. El 403 backend sigue siendo definitivo.

### 8.2 Actualización del contrato

La respuesta debe marcarse `Cache-Control: no-store`. React debe:

1. cargarla al montar y tras login, como hoy;
2. refrescarla al recuperar foco/visibilidad después de un intervalo acotado;
3. refrescarla una vez ante un 403 autenticado antes de decidir si la pantalla
   debe cerrarse o si fue una regla de objeto/negocio;
4. actualizarla tras operaciones propias que cambien la cuenta actual, si en el
   futuro se habilita alguna;
5. evitar bucles y peticiones duplicadas mediante un refresh compartido;
6. conservar el backend como autoridad aun cuando el snapshot diga `true`.

No se propone cambiar JWT, agregar WebSockets ni introducir un editor de
permisos. Un intervalo breve más refresh por foco/403 es un primer contrato
verificable; tiempo real estricto quedaría fuera de BH-062.

## 9. UX objetivo para denegaciones

| Situación | Respuesta propuesta |
|---|---|
| Ruta no autorizada con sesión vigente | Redirigir a `/acceso-denegado`, ofrecer “Ir a un destino disponible” calculado por capacidades y no revelar códigos internos. |
| Acción no autorizada conocida antes de ejecutarla | Ocultar si no aporta contexto; deshabilitar con explicación si su presencia ayuda a comprender el flujo o estado. |
| Capacidad técnica no vigente | Mensaje: “Tu habilitación técnica para esta operación no está vigente”. No presentarlo como error de formulario. |
| 403 después de una revocación | Refrescar sesión, retirar la acción y, si la ruta dejó de ser válida, navegar de forma segura. |
| 403 por ownership/objeto | Mantener sesión y mostrar “No puedes operar este registro”; no asumir revocación global. |
| 409 o regla de negocio | Conservar la pantalla y explicar conflicto/estado; no ocultar la acción como si faltara permiso. |
| 401 o cuenta desactivada | Limpiar sesión y volver al login con mensaje de sesión finalizada. |
| Error de red/5xx | Mantener el estado seguro, no afirmar “sin permisos” y permitir reintentar operaciones idempotentes. |
| Sesión inconsistente | Mantener el fail-closed actual en `/error-acceso`. |

## 10. Incrementos de implementación recomendados

Se proponen **seis incrementos pequeños y verificables**.

### Incremento 0 — Contención de contenido educativo

- definir explícitamente lectura publicada, autoría propia y administración
  global;
- exigir Personal activo para autoría si ésa sigue siendo la política;
- filtrar borradores por autor salvo `manage_content`;
- proteger update, publicación/archivo y destroy con ownership o permiso;
- agregar tests backend negativos de Cliente, Personal ajeno, Personal inactivo,
  autor y `manage_content`;
- todavía no modificar la experiencia visual más allá de impedir rutas/acciones
  incompatibles con el contrato corregido.

**Cierre verificable:** ninguna petición HTTP directa puede leer borradores
ajenos ni mutar contenido sin autoridad.

### Incremento 1 — Contrato mínimo de capacidades

- extender `/me/` con los booleanos compuestos mínimos;
- centralizar su cálculo reutilizando las mismas funciones que DRF;
- consumirlos en `SessionContext` con helpers `hasCapability` y
  `hasAnyCapability`;
- preservar compatibilidad y fail-closed ante propiedades ausentes o inválidas.

**Cierre verificable:** React y DRF producen la misma decisión para cada
combinación permiso × Personal activo × habilidad activa.

### Incremento 2 — Rutas, landing y navegación

- proteger contenido por autoría/administración global;
- usar capacidad compuesta en revisión técnica y futuras rutas de ficha/
  diagnóstico;
- quitar `allowedRoles` redundante de Usuarios/Auditoría;
- seleccionar landing por primer destino autorizado, usando BusinessRole sólo
  para priorización de experiencia;
- alinear notificaciones y agregar navegación para rutas legítimas sin exigir
  acceso previo al Dashboard;
- permitir que Personal activo llegue a agenda propia aun si ésa es su única
  superficie.

**Cierre verificable:** menú, landing y URL directa coinciden para el mismo
snapshot de acceso.

### Incremento 3 — Acciones y formularios

- exigir `assign_roles` en alta de administrador y acciones de acceso de
  Personal;
- usar `service_formula.manage` para campos y guardado de fórmulas;
- corregir links y retornos incondicionales;
- revisar contenido a nivel de ownership por elemento;
- integrar finalización, diagnóstico y fichas sólo si se confirma el flujo
  existente, sin inventar CRUD genérico ni nuevas funciones de negocio;
- mantener controles por estado de dominio separados del permiso.

**Cierre verificable:** una cuenta de sólo lectura no ve acciones mutadoras y
ningún control visible produce un 403 predecible por falta de capacidad global.

### Incremento 4 — Actualización dinámica y manejo uniforme de errores

- refresh deduplicado por foco/visibilidad y ante primer 403;
- sincronizar limpieza 401 con `SessionContext` en vez de depender sólo de
  `window.location`;
- clasificar 401, 403, 409, validación, red y 5xx;
- reevaluar ruta después de refrescar;
- definir mensajes y destino seguro en acceso denegado.

**Cierre verificable:** revocar permiso, rol, Personal o habilidad en otra
sesión retira la UI dentro del intervalo acordado o al siguiente foco/403.

### Incremento 5 — Pruebas y regresión

- completar tests unitarios de contexto, rutas, navegación y acciones;
- cubrir backend sólo para contrato compuesto y contenido, sin duplicar la
  matriz de BH-060;
- agregar recorridos de integración para revocación durante sesión y URL
  directa;
- verificar ausencia de información no autorizada en DOM y respuestas.

**Cierre verificable:** la matriz del apartado siguiente queda automatizada y
no depende de inspección visual manual.

## 11. Tests existentes relevantes

### Frontend

- `context/SessionContext.test.js`: proyección, permisos exactos, refresh manual,
  401, múltiples roles e ignorar `is_staff` local;
- `routes/ProtectedRoute.test.js`: URL directa, perfiles, permisos simples,
  `anyPermission`, BusinessRole nulo y fail-closed;
- `navigation/navigationConfig.test.js` y `components/Header.test.js`: enlaces
  por capacidades;
- `utils/sessionLanding.test.js` y `notificationNavigation.test.js`: conducta
  actual basada parcialmente en rol;
- `DashboardAdmin.test.js` y `components/admin/DashboardStats.test.js`: accesos
  rápidos y separación general/financiera;
- tests de Operaciones, Mi Agenda, Turnos, Clientes, Personal, Productos,
  Órdenes, Caja, Incidencias, Usuarios y Revisión Técnica;
- `AccesoDenegado.test.js`: mensaje estable sin revelar permisos internos.

No hay tests de rutas/pantallas de contenido administrativo, editor de
contenido, servicios por fórmula compuesta, configuración, equipamiento,
rutinas o fichas técnicas integradas.

### Backend

BH-059/BH-060 ya cubren permisos efectivos, grupos técnicos, grants
individuales, `is_staff`, configuración, reportes, Turnos, stock, Personal,
habilidades, diagnóstico, fichas y fórmulas. No deben duplicarse.

Brechas específicas que sí justifican tests backend nuevos:

- contrato propio `/me/` para capacidades compuestas;
- contenido educativo por lectura, ownership, estado de Personal y destroy;
- paridad entre cada capability de `/me/` y la permission class/servicio real.

## 12. Matriz de pruebas propuesta

| Caso | Nivel | Verificación esperada |
|---|---|---|
| Permiso desde BusinessRole | Backend + contexto | Aparece en `/me/` y habilita ruta/acción correspondiente. |
| Mismo permiso desde grupo técnico | Backend + frontend | Mismo resultado sin exigir BusinessRole administrador. |
| Mismo permiso individual | Backend + frontend | Mismo resultado; navegación y URL directa coinciden. |
| BusinessRole sin permiso suficiente | Ruta/nav | No entra ni ve acción; landing evita destino inválido. |
| `is_staff=true` sin permiso | Backend + frontend | No concede ninguna superficie SPA. |
| `is_superuser` | Backend | `/me/` no expone el flag; sí proyecta los permisos efectivos de negocio resultantes de Django. |
| Lectura sin escritura | Pantalla | Datos visibles; crear/editar/eliminar ausentes o explicados; no hay request mutadora. |
| Permiso técnico sin habilidad | Contrato/ruta/acción | `permissions` contiene el código, capability es falsa y no se ofrece la operación. |
| Permiso + habilidad + Personal activo | Contrato/ruta/acción | Capability verdadera y backend autoriza. |
| Personal desactivado durante sesión | Integración | Tras foco/refresh/403 desaparecen agenda/revisión/capacidades técnicas según contrato. |
| Habilidad revocada durante sesión | Integración | Se retiran revisión, fórmula, ficha y diagnóstico sin cerrar necesariamente toda la sesión. |
| BusinessRole cambiado durante sesión | Integración | Se actualizan identidad, permisos, menú, landing y ruta actual. |
| Permiso revocado durante sesión | Integración | Primer 403 refresca una vez; se retira acción y no hay loop. |
| Cuenta desactivada | Integración | Próxima petición da 401, limpia estado y vuelve a login. |
| URL manual autorizada por grant efectivo | Ruta | Entra aunque el BusinessRole no sea administrador. |
| URL manual no autorizada | Ruta | Redirige sin montar pantalla ni disparar fetch de datos sensibles. |
| Contenido: Cliente | Backend + frontend | Sólo lectura publicada/interacciones propias; no ve ni ejecuta administración. |
| Contenido: autor | Backend + frontend | Sólo ve/muta sus borradores según política; no elimina contenido ajeno. |
| Contenido: `manage_content` | Backend + frontend | Gestión global permitida; creación respeta condición de autor válida. |
| Alta de administrador sin `assign_roles` | Componente | Botón ausente/deshabilitado; petición directa 403. |
| Gestión de Personal skills-only | Componente/API | Sólo directorio mínimo; sin email, teléfono, usuario ni acciones de acceso. |
| 403 por ownership | UX | No limpia sesión ni lo reporta como red; conserva contexto. |
| 409 de estado | UX | Explica conflicto y refresca el recurso, no los permisos. |
| Fallo de red | UX | No muestra “sin permiso”; ofrece reintento seguro. |
| Ausencia de filtración | DOM/API | Ninguna respuesta ni componente contiene campos fuera de la proyección autorizada. |

## 13. Criterios verificables de cierre

BH-062 puede cerrarse sólo cuando:

1. contenido educativo niega lectura administrativa y mutaciones no autorizadas
   incluso por petición HTTP directa;
2. `/me/` sigue siendo mínimo y representa todas las capacidades compuestas que
   React necesita, sin exponer flags ni estructura administrativa;
3. menú, landing, notificaciones y rutas directas toman decisiones consistentes
   por permisos/capacidades efectivos;
4. no se usa `is_staff`, `is_superuser`, `Personal.rol` ni nombre de
   BusinessRole como sustituto de una capacidad;
5. cada pantalla parcial separa lectura, creación, edición, eliminación/
   desactivación y acciones especiales;
6. acciones de rol requieren simultáneamente los permisos que exige el backend;
7. condiciones técnicas no cumplidas se detectan antes de ofrecer la acción y
   se explican sin revelar detalles administrativos;
8. URL directa sin acceso no monta la pantalla ni consulta datos protegidos;
9. un cambio de rol, permiso, estado de cuenta/Personal o habilidad se refleja
   durante la sesión mediante la política de refresco acordada;
10. 401, 403, 409, validación, red y 5xx tienen tratamientos diferenciados;
11. las pruebas cubren rol, grupo técnico, permiso individual, lectura sin
    escritura, capacidades compuestas, revocación en sesión y no filtración;
12. el backend continúa siendo autoridad y no se incorporan roles, grants,
    editor genérico, cambios financieros ni rediseño visual fuera de alcance.

## 14. Riesgos residuales

Incluso después de los incrementos propuestos permanecerán límites explícitos:

- sin un canal push, una revocación puede tardar hasta el próximo foco,
  intervalo o request; el backend seguirá negando inmediatamente;
- una UI correcta no reemplaza pruebas de autorización HTTP;
- permissions/capabilities positivas no garantizan que un objeto concreto sea
  operable: ownership, estado y concurrencia se resuelven al ejecutar;
- `is_superuser` continúa siendo un bypass técnico de Django que debe controlarse
  operacionalmente fuera de la UX normal;
- componentes legacy de fichas no deben exponerse hasta integrarse al flujo
  semántico vigente;
- cualquier nueva condición técnica deberá agregarse en backend y proyectarse
  como capability, no reconstruirse ad hoc en React.

---

**Resultado:** `BH-062 — ANÁLISIS COMPLETADO`.
