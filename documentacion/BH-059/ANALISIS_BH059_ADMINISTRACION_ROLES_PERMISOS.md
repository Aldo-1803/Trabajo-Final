# BH-059 — Análisis de administración de roles y permisos

**Fecha:** 2026-11-03

**Baseline inspeccionado:** `21a30fb17a54e87b1190810badba2b6a37b55fc2`

**Modalidad:** revisión estática del repositorio. No se ejecutaron servicios,
migraciones ni pruebas y no se modificó implementación.

## 1. Objetivo y veredicto

El sistema ya tiene una base sólida para administrar acceso mediante roles de
negocio, permisos Django efectivos y operaciones semánticas auditadas. Sin
embargo, **BH-059 todavía no está listo para implementación directa como una
única pantalla de permisos**: antes deben cerrarse varias decisiones de
autoridad y contención.

Las brechas principales son:

1. el cambio de rol no protege al último `ADMINISTRADOR` activo;
2. el servicio genérico de asignación exige sólo `usuarios.assign_roles`, una
   autoridad insuficiente para promoción o degradación administrativa;
3. listar, consultar y eliminar usuarios sigue dependiendo de `IsAdminUser`,
   es decir, de `is_staff`, mientras el frontend usa correctamente permisos
   efectivos;
4. el `DELETE` legacy de usuarios escribe `is_active` y `Cliente.activo`
   directamente, sin motivo, bloqueo de autoacción, protección de último
   administrador ni auditoría semántica;
5. los permisos individuales y grupos técnicos sobreviven al cambio de rol y
   pueden conservar privilegios superiores al nuevo rol;
6. no existe una vista administrativa canónica de capacidades efectivas y de
   su origen;
7. las superficies Django Admin y de reversión histórica pueden modificar
   campos de acceso por fuera de los servicios semánticos;
8. las lecturas de `Personal` admiten a cualquier usuario autenticado y la
   creación de acceso de Personal todavía permite `ADMINISTRADOR`, aunque el
   cambio de rol laboral lo excluye.

Por tanto, BH-059 debe implementar **operaciones administrativas acotadas**, no
un editor genérico de grupos o permisos.

## 2. Modelo conceptual vigente

### 2.1 Identidad y perfiles

| Elemento | Función | Observaciones |
|---|---|---|
| `Usuario` | Identidad autenticable Django | Email único; contiene `is_active`, `is_staff`, `is_superuser`, grupos y permisos individuales. |
| `Cliente` | Perfil de dominio de cliente | Relación uno a uno con `Usuario`; tiene estado `activo` propio. |
| `Personal` | Perfil laboral | Relación opcional uno a uno con `Usuario`; tiene estado `activo` y `rol` laboral propios. |
| `Personal.rol` | Función laboral | Valores como administrador, estilista o recepcionista; **no es** autoridad de acceso. |
| BusinessRole | Rol de acceso | Se representa mediante exactamente uno de cuatro grupos Django canónicos. |

Una misma identidad puede conservar simultáneamente perfiles `Cliente` y
`Personal`. El rol de negocio determina el acceso actual; los perfiles expresan
relaciones de dominio y no deben crearse, eliminarse ni desvincularse como
efecto lateral implícito de un cambio de rol.

### 2.2 Roles de negocio canónicos

`usuarios.roles.BusinessRole` define:

- `CLIENTE`;
- `EMPLEADO`;
- `PROFESIONAL`;
- `ADMINISTRADOR`.

`get_business_roles` detecta todos los grupos canónicos del usuario y
`get_business_role` rechaza conceptualmente la multiplicidad. El estado válido
es cero o un rol durante preparación y **exactamente uno** para una cuenta
operativa o reactivable.

### 2.3 Permisos base

`usuarios.roles.ROLE_BASE_PERMISSIONS` establece:

| Rol | Capacidades base |
|---|---|
| `CLIENTE` | Ninguna capacidad administrativa del catálogo. El acceso de cliente se resuelve por ownership y perfil. |
| `EMPLEADO` | Clientes presenciales, agenda global, turnos, llegada, reprogramación/cancelación, pago y lectura de stock. |
| `PROFESIONAL` | Base operativa sin registro de pago, más diagnóstico, ficha técnica, fórmulas, rutinas, finalización y revisión técnica. |
| `ADMINISTRADOR` | Todo `BusinessPermission.ALL`. |

El grupo `ADMINISTRADOR` contiene, entre otros,
`usuarios.manage_users`, `usuarios.assign_roles` y
`gestion.manage_personal`.

### 2.4 Permisos efectivos

La autoridad real es `Usuario.has_perm(...)` / `get_all_permissions()`, que
combina:

1. permisos del grupo de BusinessRole;
2. permisos de otros grupos Django;
3. `user_permissions` individuales;
4. el bypass de `is_superuser` propio de Django.

`/api/usuarios/me/` publica sólo la intersección entre los permisos efectivos y
`BusinessPermission.ALL`, junto con BusinessRole y perfiles. El frontend usa
esta respuesta para `hasPermission` y no considera `is_staff` como autoridad.

`is_staff` debe quedar limitado al ingreso al sitio Django Admin. No demuestra
rol `ADMINISTRADOR`, no otorga capacidades de negocio y no debe autorizar una
API.

## 3. Inventario de servicios de seguridad

### 3.1 Asignación de rol

`assign_business_role`:

- bloquea la fila de `Usuario`;
- elimina sólo los cuatro grupos de negocio;
- agrega el nuevo grupo canónico;
- conserva grupos no canónicos y permisos individuales;
- limpia caches de permisos.

Es una primitiva de persistencia, no una operación administrativa completa.

`assign_validated_business_role` agrega:

- actor autenticado y activo;
- permiso efectivo `usuarios.assign_roles`;
- motivo obligatorio;
- bloqueo del objetivo;
- prohibición de autoasignación y de gestionar superusuarios;
- rechazo de múltiples BusinessRoles;
- validación de perfil `Cliente` o `Personal` según el destino;
- auditoría semántica y atomicidad.

Brecha explícita: no protege la degradación del último administrador activo y
sólo exige `assign_roles` para cualquier rol destino.

### 3.2 Estado de cuenta

`deactivate_account` exige `usuarios.manage_users`, preserva grupos, permisos,
credenciales y perfiles, y bloquea:

- autodesactivación;
- gestión de superusuarios;
- desactivación del último administrador activo.

La operación toma un lock sobre el grupo `ADMINISTRADOR`, lo que sirve como
punto de serialización para la comprobación concurrente.

`reactivate_account` también exige `manage_users`, rechaza autoacción y
superusuario, requiere un único BusinessRole y valida el perfil necesario. Para
un rol laboral exige `Personal.activo`; para `CLIENTE` permite reactivar la
cuenta con una advertencia si `Cliente.activo=False`.

La cuenta y los perfiles tienen estados diferentes de forma intencional. Una
operación debe indicar cuál cambia, no sincronizarlos silenciosamente.

### 3.3 Acceso de Personal

`gestion.personal_access_services` ya ofrece:

- vincular un usuario existente a `Personal`;
- crear cuenta y acceso para `Personal`;
- cambiar entre `EMPLEADO` y `PROFESIONAL`;
- activar/desactivar el perfil laboral;
- revocar trabajo conservando acceso `CLIENTE` cuando existe ese perfil;
- revocar trabajo y desactivar también la cuenta.

Las operaciones de vínculo, creación y rol laboral exigen
`gestion.manage_personal` **y** `usuarios.assign_roles`; la baja total exige
`manage_personal` **y** `manage_users`; el cambio de estado laboral exige
`manage_personal`.

Aspectos correctos:

- locks y transacciones;
- rechazo de superusuarios y estados de rol inconsistentes;
- motivos obligatorios;
- eventos de auditoría con actor, objetivo, perfiles y eventos relacionados;
- separación entre función laboral y BusinessRole;
- el cambio laboral ordinario no admite `ADMINISTRADOR`.

Aspectos pendientes:

- el alta de acceso para Personal sí admite `ADMINISTRADOR` y la UI lo ofrece;
- el vínculo puede conservar una cuenta sin rol, inactiva o con un rol no
  laboral, devolviendo advertencias pero sin cerrar el flujo;
- desactivar sólo `Personal` no revoca la cuenta, por diseño, pero la UI debe
  distinguir claramente estado laboral de acceso digital;
- los permisos individuales y grupos técnicos también se preservan en estas
  transiciones.

### 3.4 Alta de administradores

`create_administrator_account` es una operación dedicada que exige
`manage_users` y `assign_roles`, crea una cuenta activa con
`is_staff=False`/`is_superuser=False`, asigna sólo `ADMINISTRADOR` y audita el
motivo. Es la vía correcta para altas administrativas y no debe duplicarse en
el flujo de Personal.

## 4. Inventario de API y UI

### 4.1 Usuarios

`AdminUsuarioViewSet` (`/api/gestion/admin/usuarios/`):

| Operación | Estado actual |
|---|---|
| `list` / `retrieve` | `IsAdminUser`; lista identidad, `is_staff`, `is_active` y BusinessRole, pero no perfiles ni capacidades efectivas. |
| `create` | La ruta genérica está cerrada con `405`; existen altas semánticas separadas. |
| `PUT` / `PATCH` | Sólo identidad; el método valida `manage_users`, aunque la permission class exterior es sólo autenticación. |
| `desactivar-cuenta` | Usa el servicio seguro con `manage_users`. |
| `reactivar-cuenta` | Usa el servicio seguro con `manage_users`. |
| `DELETE` | Sigue disponible para `is_staff`; `perform_destroy` cambia campos directamente y evita las invariantes semánticas. |

`GestionUsuarios.js`:

- lista, busca y filtra cuentas;
- muestra BusinessRole y estado;
- crea administradores por la operación dedicada;
- activa y desactiva mediante comandos con motivo;
- no cambia roles;
- no muestra capacidades efectivas, perfiles vinculados ni anomalías;
- su ruta sí está protegida por `usuarios.manage_users`.

Existe, por tanto, una contradicción: el frontend usa la autoridad correcta,
pero el backend de lectura y `DELETE` usa `is_staff`.

### 4.2 Personal

`PersonalViewSet`:

- `list` y `retrieve` admiten cualquier usuario autenticado;
- altas y edición genérica usan `IsAdminUser`;
- las acciones semánticas exponen sólo `IsAuthenticated`, delegando la
  autorización efectiva a los servicios;
- el borrado físico está deshabilitado;
- el serializer publica contacto, estado laboral, cuenta vinculada, estado de
  cuenta y BusinessRole, pero no capacidades efectivas.

`GestionPersonal.js` distingue `Personal.rol` de BusinessRole y expone las
operaciones semánticas. La ruta requiere `manage_personal` o `manage_skills` y
los botones se filtran por permiso. No obstante, el formulario de creación de
acceso todavía permite `ADMINISTRADOR`.

El permiso `manage_skills` no debe implicar acceso irrestricto a datos de
contacto o administración de cuentas de Personal. Si esa pantalla necesita una
lista para habilidades, debe existir una proyección mínima específica.

### 4.3 Auditoría

Los servicios de rol, cuenta y Personal escriben eventos semánticos en
`Auditoria`. El modelo conserva actor, fecha, tabla, registro, antes, después e
IP opcional.

Hay dos superficies históricas:

- `AuditoriaViewSet`, sólo lectura;
- `HistorialAuditoriaViewSet`, con lectura y reversión limitada de modelos.

Ambas usan `IsAdminUser` en vez de `gestion.view_audit` y
`gestion.revert_audit`. Además, la reversión genérica permite restaurar campos
booleanos y de texto de `Personal`, lo que puede evitar motivos e invariantes de
las operaciones semánticas.

El Django Admin muestra auditoría como inmutable, pero `UsuarioAdmin` permite
editar directamente `is_active`, `is_staff`, `is_superuser`, grupos y permisos
individuales, y sus acciones masivas escriben estados de Usuario/Cliente sin
los servicios de acceso. `PersonalAdmin` también permite editar vínculo,
función y estado directamente.

## 5. Brechas priorizadas

### Críticas

#### B1. Pérdida del último administrador por cambio de rol

Un administrador distinto puede cambiar al último `ADMINISTRADOR` activo a
otro rol. La protección existente sólo cubre desactivación. La comprobación
debe ejecutarse dentro de la misma transacción y serializarse sobre un lock
común, no mediante un conteo sin bloqueo.

#### B2. Autoridad insuficiente para asignar roles

`assign_roles` por sí solo permite que un usuario promueva a un tercero a
`ADMINISTRADOR`; ese tercero recibe todo el catálogo y puede devolver el favor.
Aunque la autoasignación directa está bloqueada, existe escalamiento indirecto.

#### B3. Rutas que evitan invariantes

El `DELETE` de usuarios, Django Admin y la reversión histórica pueden cambiar
acceso sin motivo, sin controles de objetivo y sin auditoría semántica. Mientras
estas rutas existan, una API nueva no constituye un límite de seguridad.

### Altas

#### B4. `is_staff` sigue siendo autorización de API

`AdminUsuarioViewSet`, CRUD genérico de Personal y APIs de auditoría usan
`IsAdminUser`. Esto permite acceso por un flag técnico y niega acceso a un actor
delegado con los permisos de negocio correctos.

#### B5. Degradación de rol no garantiza degradación efectiva

`assign_business_role` conserva permisos individuales y grupos técnicos. Tras
pasar de `ADMINISTRADOR` a otro rol, el objetivo podría conservar
`manage_users`, `assign_roles` u otras capacidades administrativas por otra
fuente.

#### B6. No existe consulta administrativa de capacidades

El listado sólo muestra un rol. No diferencia permisos base, directos, de
grupos técnicos o superusuario; tampoco informa múltiples roles, ausencia de
rol o perfiles incoherentes.

### Medias

#### B7. Alta administrativa duplicada en Personal

La creación de acceso laboral admite `ADMINISTRADOR`, pese a existir un alta
administrativa dedicada con contrato más claro.

#### B8. Lectura de Personal demasiado amplia

Cualquier autenticado obtiene datos laborales y de contacto. El filtrado del
frontend no sustituye autorización backend.

#### B9. Semántica parcial de estados de perfil

Reactivar un `CLIENTE` con perfil inactivo sólo genera advertencia; desactivar
cuenta preserva perfiles; desactivar Personal preserva cuenta. Son decisiones
válidas si se presentan como operaciones distintas, pero hoy las superficies
legacy también sincronizan estados de manera diferente.

## 6. Política de autoridad propuesta

### 6.1 Reglas generales

1. La autorización se evalúa en backend con permisos Django efectivos.
2. Nunca se confía en un rol, permiso, `is_staff` o capacidad enviado por el
   frontend.
3. `is_staff` sólo habilita el sitio Django Admin; `is_superuser` es una cuenta
   protegida y fuera de las operaciones de negocio.
4. Todo comando sensible vuelve a cargar actor y objetivo desde base, exige
   actor activo, bloquea las filas necesarias y escribe auditoría semántica.
5. Ningún serializer genérico acepta grupos, permisos, BusinessRole,
   `is_active`, `is_staff`, `is_superuser` ni vínculos de perfil.
6. Un cambio de rol no crea ni elimina perfiles. Valida que exista el perfil
   requerido y preserva los demás.
7. Las operaciones de acceso deben ser idempotentes y responder con códigos de
   conflicto estables.
8. Las rutas alternativas deben cerrarse o delegar al mismo servicio; no basta
   con ocultarlas en la UI.

### 6.2 Autoridades de administración

Se mantienen los permisos existentes, sin crear inicialmente un “superpermiso”:

- `manage_users`: identidad y estado de cuentas;
- `assign_roles`: participación necesaria, pero no suficiente, en cambios de
  BusinessRole;
- `manage_personal`: perfil laboral y operaciones laborales acotadas;
- `view_audit`: consulta de auditoría;
- `revert_audit`: eventual reversión segura, nunca acceso implícito por
  `is_staff`.

La promoción/degradación general y el alta de administradores requieren la
conjunción `manage_users + assign_roles`. El cambio laboral limitado a
`EMPLEADO ↔ PROFESIONAL` requiere `manage_personal + assign_roles`.

## 7. Matriz de operaciones y autoridades

| Operación | ¿BH-059? | Autoridad backend propuesta | Restricciones obligatorias |
|---|---:|---|---|
| Listar cuentas y resumen de perfiles | Sí | `manage_users` | Proyección acotada; sin secretos ni permisos Django fuera del catálogo. |
| Consultar una cuenta | Sí | `manage_users` | Mostrar rol, estado, perfiles, capacidades canónicas efectivas y origen. |
| Editar nombre/email | Sí, ya existe | `manage_users` | Superusuario protegido; contrato estricto; email único. |
| Crear cuenta Cliente | Mantener operación dedicada | `create_walkin_client` según política vigente | Crear perfil y rol inicial de forma atómica. |
| Crear cuenta laboral | Sí, vía Personal | `manage_personal + assign_roles` | Sólo `EMPLEADO` o `PROFESIONAL`; Personal activo; contraseña temporal. |
| Crear administrador | Sí, ya existe | `manage_users + assign_roles` | Sólo vía onboarding dedicado; `is_staff=False`; motivo y auditoría. |
| Cambiar rol laboral `EMPLEADO ↔ PROFESIONAL` | Sí | `manage_personal + assign_roles` | Personal activo; no autoacción; no superusuario. |
| Asignar/cambiar rol general | Sí | `manage_users + assign_roles` | Perfiles requeridos; no autoacción; estado coherente; motivo. |
| Promover a `ADMINISTRADOR` | Sí, dentro del cambio general | `manage_users + assign_roles` | No usar flujo Personal; auditar como evento de alta de privilegio. |
| Degradar `ADMINISTRADOR` | Sí | `manage_users + assign_roles` | Lock de último administrador; rechazar autoridad administrativa residual. |
| Activar/desactivar cuenta | Sí, ya existe | `manage_users` | No autoacción ni superusuario; protección concurrente de último administrador; validar rol/perfil al activar. |
| Activar/desactivar Personal | Sí, ya existe | `manage_personal` | Cambia sólo estado laboral; respuesta explicita efecto sobre cuenta. |
| Revocar trabajo y conservar Cliente | Sí, ya existe | `manage_personal + assign_roles` | Requiere perfil Cliente; cuenta activa; preserva ownership. |
| Revocar trabajo y desactivar cuenta | Sí, ya existe | `manage_personal + manage_users` | Usa la baja segura; conserva roles y perfiles; protege último administrador. |
| Vincular Usuario y Personal | Sí, ya existe | `manage_personal + assign_roles` | Unicidad 1:1, objetivo no superusuario, estado de rol coherente. |
| Listar Personal completo | Sí | `manage_personal` | No cualquier autenticado. |
| Lista mínima para administrar skills | Sí, como proyección separada | `manage_skills` | Sin teléfono, email de cuenta ni controles de acceso innecesarios. |
| Ver auditoría de acceso | Escritura en BH-059; consulta en BH-061 | `view_audit` | BH-059 garantiza eventos; BH-061 diseña historial, filtros y presentación. |
| Revertir cambios de acceso | No como reversión genérica | Comando original y su autoridad | Nunca restaurar rol/estado/vínculo copiando campos históricos. |
| Otorgar permisos individuales arbitrarios | **No** | No exponer | Riesgo de escalamiento y ausencia de catálogo/delegación aprobados. |
| Editar grupos técnicos arbitrarios | **No** | No exponer | Sólo aprovisionamiento técnico fuera de la API de negocio. |
| Revocar excepciones individuales existentes | Opcional y acotado | `manage_users + assign_roles` | Sólo revocación, nunca autoacción; evento explícito; sin catálogo de otorgamiento. |

## 8. Matriz de transición de roles y perfiles

| Destino | Perfil requerido | Estado requerido | Efectos permitidos |
|---|---|---|---|
| `CLIENTE` | `Cliente` existente | La política debe decidir si `Cliente.activo=False` bloquea o sólo limita uso | Cambiar sólo grupo de negocio; preservar `Personal`. |
| `EMPLEADO` | `Personal` vinculado | `Personal.activo=True` | Cambiar sólo grupo; preservar `Cliente`. |
| `PROFESIONAL` | `Personal` vinculado | `Personal.activo=True` | Cambiar sólo grupo; preservar `Cliente`; habilidades siguen siendo condición adicional. |
| `ADMINISTRADOR` | Ninguno obligatorio | Cuenta gestionable; no superusuario | Cambiar sólo grupo; preservar perfiles; no convertir `is_staff`. |

Reglas adicionales:

- cero roles puede admitirse sólo como estado de preparación o anomalía a
  reparar; no permite reactivación;
- múltiples roles siempre es conflicto, nunca se “elige el primero”;
- pasar desde `ADMINISTRADOR` exige que exista otro administrador activo y
  coherente;
- el conteo de último administrador usa membresía del BusinessRole
  `ADMINISTRADOR`, no `is_staff`, `Personal.rol`, superusuario ni un permiso
  individual;
- una cuenta inactiva con rol administrador no cuenta como respaldo activo;
- la comprobación y la mutación deben compartir transacción y lock de
  serialización, igual que la baja de cuenta;
- Cliente y Personal conservan sus identificadores y ownership; no se
  reasignan automáticamente a otra identidad.

## 9. Decisión sobre permisos individuales

El modelo Django **los permite técnicamente** y el sistema los reconoce como
efectivos. También hay pruebas que confirman que sobreviven a cambios de rol,
bajas y reactivaciones. Eso no equivale a tener una política administrativa
segura.

### Decisión recomendada para BH-059

No habilitar un editor de `user_permissions`, grupos técnicos ni permisos
Django registrados. En esta fase:

1. mostrar las capacidades de negocio efectivas;
2. indicar su origen: BusinessRole, grupo técnico, permiso individual o
   superusuario;
3. marcar como anomalía permisos fuera de `BusinessPermission.ALL`, sin
   publicarlos como catálogo otorgable;
4. calcular las capacidades proyectadas antes de una transición;
5. bloquear una degradación administrativa si, luego de retirar el grupo
   `ADMINISTRADOR`, el objetivo conservaría `manage_users`, `assign_roles` o
   otra autoridad de administración de accesos por una fuente residual;
6. opcionalmente ofrecer sólo revocación auditada de excepciones individuales
   existentes; no otorgamiento.

No deben eliminarse silenciosamente permisos o grupos técnicos: podría romper
una habilitación operativa legítima. Si en el futuro se habilitan excepciones,
se necesita una decisión separada sobre catálogo, concedentes, duración,
segregación de funciones, combinaciones prohibidas, expiración y auditoría. La
UI avanzada correspondiente pertenece a BH-062.

## 10. Contención de escalamiento

### 10.1 Autoescalamiento

Debe prohibirse:

- cambiar el propio BusinessRole;
- otorgarse o revocarse excepciones individuales;
- promover a un tercero usando sólo `assign_roles`;
- crear un administrador desde el alta laboral;
- modificar `is_staff` o `is_superuser` por la API de negocio;
- usar un valor de rol del frontend para decidir autoridad del actor.

La prohibición de autoacción debe comparar IDs cargados desde base y existir en
el servicio, no sólo en la vista.

### 10.2 Último administrador

La misma protección debe aplicar a:

- desactivar cuenta;
- degradar rol;
- revocar acceso total si el Personal vinculado fuera administrador;
- cualquier reversión o acción masiva equivalente.

El lock común debe evitar que dos transacciones degraden/desactiven en paralelo
a los dos últimos administradores después de que ambas hayan observado al otro.

### 10.3 Superusuarios

Los superusuarios son cuentas técnicas protegidas. No se listan como objetivos
gestionables o se devuelven con acciones vacías; toda mutación de negocio los
rechaza. Tampoco cuentan como reemplazo del último administrador de negocio.

## 11. Contrato de consulta administrativa

BH-059 necesita una lectura canónica por usuario con, como mínimo:

- ID, email, nombre y estado de cuenta;
- BusinessRole único o anomalía (`NO_ROLE`, `MULTIPLE_ROLES`);
- perfiles `Cliente`/`Personal`: existencia, ID y estado;
- función laboral separada;
- capacidades efectivas limitadas a `BusinessPermission.ALL`;
- origen de cada capacidad;
- indicadores `is_staff` e `is_superuser` sólo como metadatos técnicos, nunca
  como decisión de UI;
- acciones permitidas calculadas por backend o datos suficientes para que la UI
  las oculte, sin que ello reemplace la autorización backend;
- advertencias de incoherencia o privilegio residual.

No debe devolver hashes de contraseña, tokens, permisos Django internos como
catálogo otorgable ni datos completos de Cliente/Personal que no sean necesarios
para administrar acceso.

## 12. Auditoría: alcance BH-059 frente a BH-061

BH-059 debe garantizar que cada mutación de acceso produzca un evento semántico
con:

- tipo de evento y fuente;
- actor y objetivo;
- rol/estado anterior y nuevo;
- motivo normalizado;
- perfiles preservados o requeridos;
- origen y resultado de privilegios residuales cuando corresponda;
- IDs de eventos subordinados en operaciones compuestas;
- ausencia de secretos y contraseña temporal.

También debe impedir que rutas genéricas eviten esos eventos.

BH-061 queda responsable de:

- historial unificado visible;
- filtros, paginación, retención y exportación;
- línea temporal por usuario;
- correlación y presentación de eventos compuestos;
- acceso histórico detallado y análisis forense.

Cambiar las permission classes existentes de auditoría a `view_audit` /
`revert_audit` es hardening de autorización, no una duplicación de la UX de
BH-061. La reversión de campos de acceso debe quedar excluida y redirigida a los
comandos semánticos.

## 13. Incrementos pequeños propuestos

### Incremento A — Cerrar superficies inseguras

1. Reemplazar `IsAdminUser` por permisos efectivos en usuarios y Personal.
2. Deshabilitar `DELETE` de Usuario o hacerlo delegar al comando de baja con
   motivo; se recomienda deshabilitarlo para evitar dos contratos.
3. Retirar `ADMINISTRADOR` del alta de acceso laboral backend y frontend.
4. Restringir Django Admin para que rol, grupos, permisos y estados de acceso
   sean sólo lectura o deleguen en operaciones seguras.
5. Excluir campos de acceso de la reversión histórica genérica.

### Incremento B — Lectura canónica de accesos

1. Autorizar list/retrieve con `manage_users`.
2. Agregar resumen de perfiles y capacidades efectivas con origen.
3. Detectar cero/múltiples roles y privilegios residuales.
4. Separar lista completa de Personal (`manage_personal`) de la proyección para
   skills (`manage_skills`).

### Incremento C — Cambio general de BusinessRole

1. Crear un command/endpoint estricto con rol destino y motivo.
2. Exigir `manage_users + assign_roles`.
3. Aplicar perfil requerido, autoacción, superusuario y atomicidad.
4. Añadir protección concurrente del último administrador.
5. Validar capacidades proyectadas y bloquear degradación administrativa
   incompleta.
6. Auditar éxito; no escribir eventos falsos en no-op.

### Incremento D — Consolidar ciclo de cuenta y Personal

1. Mantener activación/desactivación de cuenta como operación separada del
   estado laboral.
2. Definir si un `CLIENTE` inactivo bloquea reactivación o produce una cuenta
   activa sin capacidad de cliente; documentar una sola regla.
3. Cerrar estados intermedios de vínculo con respuestas y acciones de reparación
   explícitas.
4. Unificar códigos de error y contratos estrictos.

### Incremento E — Excepciones existentes, sólo si se aprueba

1. Inventariar permisos individuales y grupos no canónicos actuales.
2. Ofrecer diagnóstico y, si es imprescindible, revocación auditada.
3. No implementar otorgamiento hasta que exista una política aprobada.

Cada incremento debe poder desplegarse sin abrir la administración genérica de
permisos.

## 14. Pruebas necesarias

Estas son pruebas de aceptación de seguridad de BH-059. La estabilización del
entorno, fechas, concurrencia de la suite y reproducibilidad global corresponde
a BH-060.

### 14.1 Autoridad

- `is_staff=True` sin permisos efectivos recibe `403` en todas las APIs de
  acceso;
- un actor con cada combinación parcial recibe `403` cuando se exige conjunción;
- `manage_users` permite lectura/estado pero no cambio de rol;
- `manage_personal + assign_roles` sólo cambia `EMPLEADO ↔ PROFESIONAL`;
- actor inactivo es rechazado aunque conserve permisos;
- el backend ignora cualquier rol/capacidad declarada por el frontend.

### 14.2 Rol y perfiles

- cada destino exige el perfil correcto;
- `Personal` inactivo bloquea roles laborales;
- cambiar rol preserva IDs y datos de Cliente/Personal;
- cero o múltiples roles generan conflicto estable;
- no-op no duplica auditoría;
- superusuario y autoacción son rechazados;
- alta laboral rechaza `ADMINISTRADOR`;
- alta administrativa conserva `is_staff=False` y no crea perfiles implícitos.

### 14.3 Último administrador y concurrencia

- no se puede degradar ni desactivar al único administrador activo;
- un administrador inactivo no sirve como respaldo;
- superusuario e `is_staff` no cuentan como respaldo;
- con dos administradores, una operación válida deja al menos uno;
- dos degradaciones, dos bajas o una degradación y una baja concurrentes no
  pueden dejar cero administradores activos;
- rollback de auditoría o error de perfil revierte también el rol.

### 14.4 Permisos efectivos

- lectura combina permisos de rol, grupo técnico e individuales;
- informa el origen de cada capacidad;
- no publica permisos fuera del catálogo como otorgables;
- degradar un administrador sin excepciones elimina sus capacidades base de
  administración;
- degradar con `manage_users`/`assign_roles` residual se bloquea;
- cambio de rol no borra permisos técnicos legítimos silenciosamente;
- caches de permisos quedan invalidadas.

### 14.5 Estado de cuenta

- baja rechaza autoacción, superusuario y último administrador;
- reactivación exige rol único y perfil coherente;
- baja/alta preservan credenciales, roles, permisos y ownership;
- los tokens preexistentes y su política de revocación quedan documentados;
- `DELETE`, acción masiva y reversión no pueden evitar el servicio.

### 14.6 API y exposición

- listado de usuarios requiere `manage_users`;
- listado completo de Personal requiere `manage_personal`;
- gestor de skills recibe sólo su proyección mínima;
- serializers rechazan campos inesperados y campos de privilegio;
- filtros no permiten inferir registros fuera del scope;
- respuestas no contienen secretos ni contraseña temporal.

### 14.7 Auditoría

- cada mutación exitosa registra actor, objetivo, motivo, antes y después;
- errores y rollbacks no dejan eventos de éxito;
- operaciones compuestas correlacionan eventos;
- consulta requiere `view_audit`, no `is_staff`;
- reversión genérica no cambia rol, cuenta, vínculo o estado laboral.

## 15. Riesgos y decisiones pendientes

| Riesgo/decisión | Impacto | Resolución propuesta |
|---|---|---|
| Permisos individuales preexistentes | Una degradación puede ser nominal | Inventariar, mostrar origen y bloquear autoridad residual; no habilitar grant genérico. |
| Grupos técnicos | Pueden conceder permisos canónicos fuera del rol | Mostrar origen y tratar capacidades administrativas residuales como conflicto. |
| Estado `Cliente.activo` al reactivar | Cuenta activa pero perfil inutilizable | Elegir una regla explícita antes del Incremento D. |
| Tokens de cuenta reactivada | Tokens anteriores podrían recuperar validez | Documentar y decidir invalidación/rotación; no ocultarlo como detalle de UI. |
| Django Admin | Bypass de servicios semánticos | Hacer campos sensibles read-only o implementar acciones que invoquen comandos seguros. |
| Reversión histórica | Puede romper invariantes actuales | Excluir acceso de la reversión genérica. |
| Delegación parcial | Combinaciones de permisos pueden habilitar colusión | Exigir conjunciones y operaciones de destino acotado. |
| Datos de Personal | Exposición a cualquier autenticado | Separar scopes y serializers mínimos. |

## 16. Fronteras con tareas posteriores

### BH-059 — Incluido

- contratos backend de administración segura;
- lectura de rol, perfiles y capacidades efectivas;
- autoridad por operación;
- cambio de rol con perfiles, no autoacción y último administrador;
- ciclo de cuenta y acceso laboral;
- contención de rutas alternativas;
- escritura de auditoría semántica;
- decisión conservadora sobre permisos individuales.

### BH-060 — No incluido

- estabilización general y reproducibilidad de la suite;
- infraestructura de concurrencia determinista;
- control global de reloj/fechas y `--keepdb`;
- ejecución E2E como política del proyecto.

BH-059 sí define las pruebas de aceptación de sus invariantes; BH-060 asegura
que se ejecuten de manera reproducible.

### BH-061 — No incluido

- historial visual y forense completo;
- consultas temporales, exportación, retención y correlación avanzada;
- panel histórico por actor/objetivo.

BH-059 sólo exige eventos correctos y evita bypasses.

### BH-062 — No incluido

- diseñador de roles o permisos;
- matrices visuales avanzadas;
- comparación interactiva, bulk actions o UX de aprobación;
- mejoras amplias de usabilidad y accesibilidad del panel.

BH-059 puede hacer ajustes mínimos de seguridad en la UI —por ejemplo retirar
`ADMINISTRADOR` del alta laboral— sin asumir el rediseño de BH-062.

## 17. Criterios de cierre de BH-059

BH-059 podrá cerrarse cuando:

1. ninguna API de usuarios, Personal o auditoría use `is_staff` como autoridad
   de negocio;
2. el `DELETE` y las acciones alternativas no puedan cambiar acceso por fuera
   de comandos semánticos;
3. exista lectura autorizada de rol, perfiles, capacidades efectivas, origen y
   anomalías;
4. exista cambio general de BusinessRole con contrato estricto,
   `manage_users + assign_roles`, perfiles y auditoría;
5. los cambios laborales sigan limitados a `EMPLEADO`/`PROFESIONAL` y el alta
   de Personal no pueda crear administradores;
6. autoescalamiento, gestión de superusuario y escalamiento indirecto estén
   bloqueados en servicio;
7. desactivación y degradación compartan una protección concurrente del último
   administrador activo;
8. una degradación no pueda dejar autoridad administrativa residual sin ser
   detectada y rechazada;
9. los perfiles y ownership se preserven y cada operación declare qué estado
   cambia;
10. no exista otorgamiento arbitrario de permisos individuales o grupos
    técnicos;
11. todos los éxitos sensibles produzcan auditoría semántica sin secretos y las
    reversiones genéricas no alteren acceso;
12. las pruebas de aceptación indicadas pasen en el entorno disponible, dejando
    la estabilización transversal a BH-060;
13. BH-061 y BH-062 permanezcan sin implementación anticipada.

## 18. Conclusión

La arquitectura base no necesita reemplazarse: BusinessRole, permisos Django
efectivos y los servicios semánticos existentes son el fundamento correcto. El
trabajo de BH-059 consiste en cerrar bypasses, elevar la autoridad requerida
para cambios de privilegio, proteger al último administrador también durante
degradaciones y hacer visible la diferencia entre rol nominal y capacidades
efectivas.

La administración segura no debe convertirse en edición libre de grupos y
permisos. Debe ofrecer pocas operaciones de negocio, con objetivos y
transiciones explícitas, autoridad efectiva, validación de perfiles, locks,
auditoría y respuestas deterministas.

BH-059 — ANÁLISIS COMPLETADO
