# BH-061 — Análisis de auditoría de roles y permisos

**Fecha:** 2026-11-08

**Baseline publicado inspeccionado:**
`b729881daddb07acfe475bf7ff2ebfdce78d19a5`

**Rama:** `save/work-in-progress`

**Modalidad:** revisión estática focal de implementación, rutas y pruebas ya
existentes. No se ejecutó nuevamente la matriz de BH-059/BH-060 y no se
modificaron código, tests, migraciones, configuración ni backlog.

## 1. Objetivo y veredicto

La mayor parte de la infraestructura necesaria para BH-061 ya está
implementada. Los cambios de `BusinessRole`, los estados principales de cuenta
y Personal, y las operaciones compuestas de acceso laboral pasan por servicios
semánticos atómicos que escriben eventos en `gestion.Auditoria`. Las APIs y
Django Admin contienen las mutaciones genéricas que podrían eludir esos
servicios.

Sin embargo, **BH-061 requiere una implementación focal antes de poder
cerrarse**. Las brechas reales son:

1. `assign_initial_client_role()` escribe
   `INITIAL_CLIENT_ROLE_ASSIGNED` incluso cuando `changed=False`; un no-op queda
   representado falsamente como asignación efectiva;
2. las operaciones compuestas relacionan eventos mediante IDs subordinados,
   pero no tienen un identificador uniforme de operación que permita consultar
   la correlación desde cualquiera de sus eventos;
3. un evento de rol guarda los roles y grupos cambiados, pero no identifica la
   versión del contrato `ROLE_BASE_PERMISSIONS` usada para reconstruir las
   capacidades canónicas afectadas;
4. las habilidades canónicas son una condición real de autorización técnica,
   separada de los permisos Django, y sus eventos no guardan `source` ni
   `reason`;
5. la concurrencia del último administrador está probada sobre el estado final,
   pero las pruebas no verifican la cardinalidad exacta de los eventos
   semánticos concurrentes.

No se encontró una brecha que justifique un editor genérico, grants arbitrarios,
un nuevo modelo forense, exportaciones, retención ni cambios de UX.

> **Veredicto:** `BH-061 REQUIERE IMPLEMENTACIÓN FOCAL`.

## 2. Modelo de acceso que debe auditarse

### 2.1 BusinessRole y grupos canónicos

`usuarios.roles.BusinessRole` define cuatro roles, materializados como grupos
Django de nombre canónico:

- `CLIENTE`;
- `EMPLEADO`;
- `PROFESIONAL`;
- `ADMINISTRADOR`.

`assign_business_role()` reemplaza exclusivamente las pertenencias a esos
cuatro grupos. Preserva grupos no canónicos, permisos individuales, perfiles,
credenciales y flags de cuenta.

La primitiva es interna al dominio, no valida actor ni escribe auditoría por sí
sola. Los callsites productivos encontrados están contenidos:

- `assign_initial_client_role()` para registro público;
- `create_client_account_by_staff()` para alta presencial;
- `create_administrator_account()` para alta de administrador SPA;
- `assign_validated_business_role()` para cambios auditados;
- los orquestadores administrativos y laborales que reutilizan este último.

No se encontró una ruta HTTP que invoque directamente `assign_business_role()`.

### 2.2 Capacidades derivadas

Los permisos efectivos derivados de rol se definen en
`usuarios.roles.ROLE_BASE_PERMISSIONS`:

| Rol | Contrato derivado |
|---|---|
| `CLIENTE` | Sin permisos de negocio base. |
| `EMPLEADO` | Operación de clientes, agenda, turnos, pagos manuales y lectura de stock. |
| `PROFESIONAL` | Base operativa sin registro de pago, más diagnóstico, ficha técnica, fórmulas, rutinas, finalización y revisión técnica. |
| `ADMINISTRADOR` | Todo `BusinessPermission.ALL`. |

Un evento de cambio **no debe duplicar el snapshot completo de permisos**. El
delta canónico puede reconstruirse desde `previous_role`, `new_role` y una
versión estable de `ROLE_BASE_PERMISSIONS`. Actualmente falta esa versión.

La proyección administrativa de sólo lectura en
`usuarios.access_read_services.build_administrative_access_summary()` ya
distingue correctamente:

- origen `BUSINESS_ROLE`;
- origen `TECHNICAL_GROUP`;
- origen `INDIVIDUAL`;
- origen `SUPERUSER`;
- asignación frente a efectividad;
- drift del grupo canónico y privilegios administrativos residuales.

### 2.3 Permisos individuales y grupos técnicos

No existe una vía de producto autorizada para otorgar o revocar
`user_permissions` ni para administrar grupos técnicos:

- los serializers de Usuario y Personal rechazan esos campos;
- el alta pública rechaza `groups` y `user_permissions`;
- `UsuarioAdmin` expone ambos como read-only;
- `Group` está desregistrado de Django Admin;
- las URLs Admin de `Group` y `Permission` responden `404`;
- no se encontró ViewSet o comando de grants/revokes.

Por ello no corresponde implementar en BH-061 eventos de grants arbitrarios.
Las asignaciones observadas en tests, migraciones y test harness son fixtures o
aprovisionamiento técnico, no operaciones de producto.

Si una integración externa confiable modifica estos orígenes, deberá hacerlo
fuera del contrato de producto y con su propio control operativo. No debe
atribuirse a `BUSINESS_ROLE_CHANGED` una mutación que el servicio preserva.

### 2.4 Estados y condiciones relacionadas con acceso

Se deben distinguir los siguientes conceptos:

| Estado o condición | Efecto | Clasificación BH-061 |
|---|---|---|
| `Usuario.is_active` | Un usuario inactivo no tiene permisos Django efectivos y no autentica normalmente. | Estado de acceso principal. |
| `Personal.activo` | Requisito para roles laborales y para habilidades técnicas efectivas. | Estado de acceso laboral principal. |
| `PersonalHabilidad.activa` + `Habilidad.activa` | Condición adicional para operaciones técnicas; no es un permiso Django. | Condición de autorización relacionada. |
| `Cliente.activo` | Estado del perfil; la reactivación de cuenta lo informa como warning y no lo cambia. | Contexto de acceso, no grant de rol. |
| `is_staff` | Acceso técnico al sitio Admin; no autoriza las APIs de negocio. | Flag técnico contenido. |
| `is_superuser` | Bypass técnico de Django; los comandos semánticos protegen al superusuario objetivo. | Fuente técnica externa al BusinessRole. |
| `Personal.rol` | Función laboral descriptiva heredada. | No equivale a `BusinessRole`. |
| `realiza_*` | Flags legacy read-only; la autoridad canónica está en `PersonalHabilidad`. | No son la fuente vigente. |

## 3. Inventario de operaciones y eventos existentes

### 3.1 Eventos de rol y alta

| Operación productiva | Mutación efectiva | Evento principal | Actor y motivo | Antes/después | Atomicidad |
|---|---|---|---|---|---|
| Registro público | Crea Usuario, Cliente y asigna `CLIENTE`. | `INITIAL_CLIENT_ROLE_ASSIGNED` / `UsuarioBusinessRole` | Actor nulo; `source=public_registration`. No hay motivo humano aplicable. | Roles anteriores y rol final. | Sí. Serializer y servicio son atómicos. |
| Alta de cliente por staff | Crea Usuario, Cliente y grupo `CLIENTE`. | `CLIENT_ACCOUNT_CREATED_BY_STAFF` / `ClientAccountCreation` | Actor FK/ID y `reason`. | Alta sin objeto previo; snapshot nuevo acotado. | Sí. |
| Alta de administrador SPA | Crea Usuario y grupo `ADMINISTRADOR`. | `ADMINISTRATOR_ACCOUNT_CREATED` / `AdministratorAccountCreation` | Actor FK/ID y `reason`. | Alta sin objeto previo; snapshot nuevo acotado. | Sí. |
| Cambio administrativo general | Reemplaza un BusinessRole por otro. | `BUSINESS_ROLE_CHANGED` / `UsuarioBusinessRole` | Actor FK/ID/email y `reason`. | Rol/grupo anterior; rol/grupo nuevo. | Sí. |
| Cambio laboral acotado | `CLIENTE`, sin rol, `EMPLEADO` o `PROFESIONAL` hacia `EMPLEADO`/`PROFESIONAL`. | `BUSINESS_ROLE_CHANGED` + `PERSONAL_BUSINESS_ROLE_CHANGED` | Mismo actor y motivo. | Roles, Personal, Usuario, perfiles y estado. | Sí, transacción compuesta. |
| Alta de acceso para Personal | Crea Usuario, vínculo y rol laboral. | `PERSONAL_USER_LINKED` + `BUSINESS_ROLE_CHANGED` + `PERSONAL_ACCESS_CREATED` | Mismo actor y motivo. | Alta y estados finales. | Sí, transacción compuesta. |

### 3.2 Eventos de estado y revocación

| Operación productiva | Evento principal o compuesto | Datos relevantes |
|---|---|---|
| Desactivar cuenta | `ACCOUNT_DEACTIVATED` / `UsuarioAccountStatus` | Actor, Usuario, roles, activo antes/después, motivo y cantidad de refresh tokens revocados. |
| Reactivar cuenta | `ACCOUNT_REACTIVATED` / `UsuarioAccountStatus` | Actor, Usuario, rol coherente, activo antes/después, motivo y warnings. |
| Vincular Usuario a Personal | `PERSONAL_USER_LINKED` / `PersonalUserLink` | Personal, Usuario anterior/nuevo, email, actor y motivo. No cambia rol. |
| Desactivar/reactivar Personal | `PERSONAL_DEACTIVATED` o `PERSONAL_REACTIVATED` / `PersonalStatus` | Personal, Usuario vinculado, estado anterior/nuevo, actor y motivo. |
| Revocar trabajo conservando cliente | `PERSONAL_DEACTIVATED` + `BUSINESS_ROLE_CHANGED` + `WORK_ACCESS_REVOKED_KEEP_CLIENT` | El evento padre guarda `status_audit_id` y `role_audit_id`. |
| Revocar trabajo y cuenta | `ACCOUNT_DEACTIVATED` + eventual `PERSONAL_DEACTIVATED` + `WORK_ACCESS_REVOKED_ACCOUNT_DISABLED` | El padre guarda `account_audit_id` y `status_audit_id`. |
| Asignar/revocar/reactivar habilidad | `PERSONAL_SKILL_ASSIGNED`, `PERSONAL_SKILL_REVOKED` o `PERSONAL_SKILL_REACTIVATED` / `PersonalHabilidad` | Actor, Personal, habilidad y activa antes/después; faltan fuente y motivo. |

### 3.3 Datos comunes del modelo Auditoria

`gestion.models.Auditoria` aporta a todos los eventos:

- `usuario`: FK del actor, con `SET_NULL`;
- `fecha_hora`: `auto_now_add=True`;
- `tabla` y `registro_id`: objetivo lógico;
- `accion`;
- `valor_anterior` y `valor_nuevo` JSON;
- `ip_address` opcional.

Los eventos semánticos duplican `actor_id` dentro del JSON. Esto preserva el ID
histórico si la FK queda nula por una eliminación externa del actor. Los IDs de
Usuario/Personal/Cliente permiten identificar el objetivo sin depender sólo de
emails mutables.

## 4. Contrato de auditoría evaluado

| Requisito | Estado | Evaluación |
|---|---|---|
| Actor | **CUMPLE** | FK e ID explícito en eventos administrativos. Registro público usa actor nulo y fuente explícita. |
| Usuario afectado | **CUMPLE** | `registro_id`, `target_user_id` o `user_id`; eventos laborales agregan `personal_id`. |
| Fecha y hora | **CUMPLE** | `fecha_hora` automática en base de datos. |
| Operación | **CUMPLE PARCIAL** | `event`, `source` y `accion`, salvo que los eventos de habilidad no incluyen `source`. |
| Estado anterior/posterior | **CUMPLE PARCIAL** | Roles y estados principales están presentes. Altas expresan sólo estado nuevo, lo cual es válido; habilidades sí guardan antes/después. |
| Motivo | **CUMPLE PARCIAL** | Está en todos los comandos administrativos principales. Habilidades no aceptan ni registran motivo. Registro público usa la causa de sistema `source`. |
| Correlación | **CUMPLE PARCIAL** | Padres compuestos referencian IDs hijos, pero no hay `operation_id` uniforme ni navegación hijo→operación. |
| Capacidades afectadas | **CUMPLE PARCIAL** | Se derivan por rol, pero falta versión/fingerprint del contrato canónico. |
| Ausencia de secretos | **CUMPLE** | No se guardan contraseñas, hashes ni tokens. Sólo se registra el conteo de refresh tokens revocados. |

### 4.1 Reconstrucción sin redundancia

Para reconstruir un cambio de rol basta con:

1. `target_user_id`;
2. `previous_role` y `new_role`;
3. grupos canónicos removidos/agregado;
4. una versión estable del contrato de capacidades;
5. el contexto de cuenta/Personal cuando el cambio es compuesto.

No es necesario copiar `ROLE_BASE_PERMISSIONS[rol]` completo en cada evento.
La implementación mínima debe agregar una referencia como
`role_contract_version` y, para verificación, fingerprints deterministas de los
conjuntos canónicos anterior y posterior. La versión debe corresponder a una
definición conservada en código; un simple número que se sobreescribe sin
mantener contratos anteriores no permite reconstrucción histórica.

Los permisos individuales y grupos técnicos no deben aparecer como si fueran
modificados por el cambio de rol: los servicios los preservan. Pueden
registrarse como warnings o anomalías en la lectura administrativa, no como
delta del evento.

## 5. Integridad y seguridad

### 5.1 Atomicidad y rollback

Los servicios críticos usan `@transaction.atomic`. Los eventos semánticos se
crean directamente con `Auditoria.objects.create()` dentro de la misma
transacción. Las pruebas existentes fuerzan errores de auditoría y demuestran
rollback para:

- cambio general y laboral de BusinessRole;
- registro público;
- altas Cliente, Administrador y acceso de Personal;
- vínculo Personal–Usuario;
- estado de cuenta y Personal;
- ambas revocaciones compuestas;
- asignación de habilidad.

Los eventos subordinados de una operación compuesta también se revierten si
falla el evento padre.

### 5.2 No-op

Cumplen no-op sin evento:

- cambio al mismo BusinessRole;
- vínculo Personal–Usuario ya existente;
- desactivación/reactivación repetida de cuenta;
- desactivación/reactivación repetida de Personal;
- revocaciones ya en estado final;
- asignación o revocación repetida de habilidad.

**Excepción real:** `assign_initial_client_role()` calcula `changed=False`
cuando el Usuario ya tiene exactamente `CLIENTE`, pero después crea siempre un
evento `INITIAL_CLIENT_ROLE_ASSIGNED` y retorna un `audit_id`. No existe una
prueba del caso. Aunque el registro público normal entrega un Usuario nuevo, el
contrato reusable del servicio es incorrecto y permite duplicar evidencia de
una mutación inexistente.

### 5.3 Concurrencia

Los locks relevantes existen:

- Usuario objetivo con `select_for_update()`;
- grupo `ADMINISTRADOR` bloqueado para promoción/degradación y baja;
- Personal, habilidades y asignaciones bloqueados;
- updates condicionales de estados;
- restricciones únicas de vínculo y asignación.

`test_bh059_c_business_role_concurrency.py` prueba en PostgreSQL real que dos
degradaciones, o degradación y desactivación concurrentes, conservan un
administrador activo. Falta afirmar que el resultado concurrente produce
exactamente un evento de éxito y ninguno para la operación rechazada.

No hay una prueba concurrente específica de dos cambios sobre el mismo Usuario,
dos comandos de estado iguales ni una asignación simultánea de habilidad. Los
locks y restricciones reducen el riesgo, pero BH-061 debe agregar únicamente
las pruebas focales de cardinalidad que no dupliquen la matriz de autorización
de BH-059/BH-060.

### 5.4 Contención de rutas alternativas

La revisión no encontró una ruta de producto alternativa que cambie roles,
grupos canónicos, grants individuales o estados principales sin pasar por los
servicios:

- POST y DELETE genéricos de Usuario están deshabilitados;
- PUT/PATCH de Usuario sólo aceptan identidad;
- `PersonalSerializer` deja `usuario`, `activo` y flags legacy como read-only;
- DELETE de Personal está deshabilitado;
- los payloads de comandos rechazan campos inesperados;
- Admin de Usuario, Cliente, Personal y Auditoria impide altas/cambios/bajas de
  acceso;
- Group/Permission no tienen superficie Admin.

`assign_business_role()` continúa siendo una primitiva importable por código
interno. Sus callsites actuales están auditados por sus orquestadores. Conviene
mantener una prueba o regla arquitectónica de callsites permitidos; convertirla
en editor o endpoint sería una regresión de seguridad.

### 5.5 Lectura, edición y reversión

- `/api/auditoria/` es un `ReadOnlyModelViewSet`;
- todos sus serializers son read-only;
- exige Usuario activo y permiso efectivo `gestion.view_audit`;
- `is_staff` sin ese permiso recibe `403`;
- `AuditoriaAdmin` hereda `BusinessReadOnlyAdminMixin` y no permite add, change
  ni delete;
- la prueba HTTP de Django Admin intenta alterar/eliminar Auditoria y confirma
  la inmutabilidad de esa superficie;
- `gestion.revert_audit` es independiente de `view_audit`;
- la reversión histórica bloquea en `Personal` los campos `usuario_id`, `rol` y
  `activo`;
- Usuario y Auditoria no pertenecen a los modelos reversibles.

La protección es de las superficies de producto, no append-only a nivel de
base de datos. Un operador con acceso directo a ORM/SQL conserva capacidad
técnica de alterar filas; endurecimiento criptográfico o WORM sería historial
forense avanzado y está fuera de BH-061.

### 5.6 Señales CRUD genéricas

`gestion.signals` genera auditoría CRUD genérica para Usuario, Cliente y
Personal, excluyendo `password` y `refresh_token`. Esa señal:

- no observa cambios M2M de grupos ni permisos;
- captura y registra el error si falla la escritura, pero no aborta la mutación;
- puede producir eventos adicionales de alta/identidad.

Por tanto, **no puede considerarse evidencia principal de un cambio de acceso**.
Los eventos semánticos directos son el contrato de BH-061. No debe eliminarse
la señal dentro de esta tarea ni usarse para compensar una brecha semántica.

### 5.7 Intentos rechazados

El resultado esperado es:

- una mutación efectiva confirmada genera su evento de éxito;
- un no-op no genera evento de cambio;
- un intento rechazado por permiso, invariantes, último administrador,
  privilegios residuales, payload o conflicto no genera evento de éxito;
- si se desea observabilidad de intentos, debe ir a logging/seguridad con un
  tipo distinto y nunca mezclarse con `BUSINESS_ROLE_CHANGED`.

Auditar cada `401/403/409` como cambio exitoso degradaría la evidencia. Un
registro general de intentos de acceso no es requisito de BH-061.

## 6. Matriz operación × evento × prueba

Leyenda: **Sí** = cobertura directa; **Parcial** = prueba el estado pero no todo
el contrato de evento; **N/A** = no-op o concurrencia no aplicable a una alta
única.

| Operación | Evento(s) | Positiva y contenido | Negativa/sin evento | No-op | Rollback | Concurrencia | Evaluación |
|---|---|---:|---:|---:|---:|---:|---|
| Registro público CLIENTE | `INITIAL_CLIENT_ROLE_ASSIGNED` | Sí, actor nulo, fuente y sin secretos | Sí | **No; defecto** | Sí | No | Requiere corrección. |
| Alta Cliente por staff | `CLIENT_ACCOUNT_CREATED_BY_STAFF` | Sí, actor, rol, motivo y sin secretos | Sí | N/A | Sí | Parcial por unicidad | Suficiente para BH-061. |
| Alta Administrador SPA | `ADMINISTRATOR_ACCOUNT_CREATED` | Sí, flags, actor, rol, motivo y sin secretos | Sí | N/A | Sí | No específica | Suficiente para BH-061. |
| Cambio general BusinessRole | `BUSINESS_ROLE_CHANGED` | Sí, promoción, degradación y contenido | Sí, perfiles, último admin y residuos | Sí | Sí | Estado final sí; evento no | Falta metadata/versionado y cardinalidad concurrente. |
| Cambio laboral BusinessRole | `BUSINESS_ROLE_CHANGED` + `PERSONAL_BUSINESS_ROLE_CHANGED` | Sí; CLIENTE→laboral y EMPLEADO↔PROFESIONAL | Sí | Sí | Sí | No | Buena cobertura funcional; falta correlación uniforme. |
| Vincular Usuario–Personal | `PERSONAL_USER_LINKED` | Sí, actor, antes/después, motivo y sin secretos | Sí | Sí | Sí | Parcial por restricciones | Cumple contrato principal. |
| Crear acceso para Personal | vínculo + rol + `PERSONAL_ACCESS_CREATED` | Sí, IDs componentes, motivo y sin contraseña | Sí | N/A | Sí, incluidos hijos | Conflicto simulado | Cumple salvo correlación uniforme/versionado. |
| Desactivar cuenta | `ACCOUNT_DEACTIVATED` | Sí, estado, rol y tokens revocados | Sí, último admin, self y superuser | Sí | Sí | Junto con degradación; evento no | Falta cardinalidad concurrente. |
| Reactivar cuenta | `ACCOUNT_REACTIVATED` | Sí, estados y coherencia de perfil | Sí | Sí | Sí | No | Cobertura suficiente salvo carrera focal. |
| Estado Personal | `PERSONAL_DEACTIVATED` / `PERSONAL_REACTIVATED` | Sí, estados y motivo | Sí | Sí | Sí | No | Cobertura suficiente salvo carrera focal. |
| Revocar trabajo conservando Cliente | estado + rol + `WORK_ACCESS_REVOKED_KEEP_CLIENT` | Sí, IDs componentes y estados | Sí | Sí | Sí, incluidos hijos | No | Cumple salvo correlación uniforme/versionado. |
| Revocar trabajo y cuenta | cuenta + estado + `WORK_ACCESS_REVOKED_ACCOUNT_DISABLED` | Sí, IDs componentes y estados | Sí, incluido último admin | Sí | Sí, incluidos hijos | No | Cumple salvo correlación uniforme. |
| Habilidades técnicas | tres eventos `PERSONAL_SKILL_*` | Parcial: existencia y before/after | Sí en API | Comportamiento sí; cardinalidad parcial | Sí para asignación | No | Faltan motivo, fuente y pruebas de contrato completas. |

### 6.1 Cobertura solicitada expresamente

| Caso | Evidencia existente | Faltante BH-061 |
|---|---|---|
| Promoción | `test_promotion_preserves_profiles_ownership_and_account_flags` y pruebas de API. | Afirmar metadata de contrato de capacidades. |
| Degradación | Cambio Administrador→Cliente con backup y control residual. | Cardinalidad del evento en carrera. |
| EMPLEADO↔PROFESIONAL | Ambas direcciones en `test_personal_business_role_services.py`. | Correlación uniforme entre evento laboral y evento base. |
| Último administrador | Servicios, API y PostgreSQL concurrente. | Afirmar cero evento para rechazado y uno para ganador. |
| Privilegios residuales | Individual y grupo técnico, sin mutación. | Afirmar explícitamente cero evento de éxito en ambos orígenes. |
| Rollback | Cobertura directa para todos los servicios principales. | No repetir matriz; sólo añadir los nuevos campos/ramas. |
| No-op | Cobertura amplia. | Corregir y probar `assign_initial_client_role()`. |
| Concurrencia | Último admin cubierto funcionalmente. | Conteo y contenido de eventos; carreras focales del mismo objetivo. |
| Permisos explícitos | Sólo fixtures/provisioning, no vía de producto. | Ninguna implementación de grants. Mantener contención. |

## 7. Brechas reales y severidad

### BH061-G1 — Evento falso en no-op inicial CLIENTE — **ALTA**

`assign_initial_client_role()` siempre crea Auditoria. En una segunda llamada
válida retorna `changed=False` pero emite `INITIAL_CLIENT_ROLE_ASSIGNED`.

**Impacto:** duplica evidencia y confunde cambio efectivo con confirmación de
estado. El flujo público normal reduce la exposición porque crea un Usuario
nuevo, pero el contrato del servicio viola directamente un criterio de cierre.

**Cierre mínimo:** retornar `audit_id=None` antes de crear el evento cuando no
hay cambio, ajustar el tipo del resultado y agregar prueba de repetición.

### BH061-G2 — Correlación compuesta no uniforme — **MEDIA**

Los padres guardan `role_audit_id`, `status_audit_id`, `account_audit_id` o
`link_audit_id`. Es suficiente para seguir una operación desde el padre, pero
no para agrupar de forma uniforme desde un hijo ni filtrar todas las piezas por
una clave común.

**Cierre mínimo:** generar un `operation_id` opaco por comando compuesto y
guardarlo en todos sus eventos JSON. No requiere un modelo histórico nuevo ni
una migración si se conserva el JSON actual. Los IDs subordinados pueden
mantenerse para compatibilidad.

### BH061-G3 — Contrato de capacidades no versionado — **MEDIA**

El rol anterior/nuevo permite derivar capacidades con el código actual, pero no
demuestra qué versión del mapa canónico regía al producirse el evento.

**Cierre mínimo:** versionar el contrato y registrar versión más fingerprints
deterministas anterior/posterior. No copiar snapshots completos ni permisos
técnicos preservados.

### BH061-G4 — Habilidades sin motivo ni fuente — **MEDIA**

Una habilidad activa participa en autorización real junto con permiso Django,
Usuario activo y Personal activo. Sus eventos contienen actor y transición,
pero no `source` ni `reason`; la API tampoco recibe motivo.

**Cierre mínimo:** incorporar motivo acotado en los tres comandos, fuente
estable y pruebas de contenido/no-op/rollback. Si producto decide excluir
formalmente habilidades de BH-061, debe dejar explícito que son auditoría de
condiciones técnicas y abrir una tarea separada; no deben presentarse como
permisos Django.

### BH061-G5 — Concurrencia sin aserción de auditoría exacta — **MEDIA**

La invariante del último administrador está probada, pero no se consulta
Auditoria en esas carreras.

**Cierre mínimo:** para cada carrera existente afirmar un evento semántico para
el ganador, cero para el rechazado y coherencia entre objetivo, before/after y
estado final.

### BH061-G6 — Carreras focales adicionales no cubiertas — **BAJA**

No hay prueba simultánea del mismo cambio de rol/estado/habilidad. La
implementación usa locks y updates condicionales, por lo que es una brecha de
evidencia más que una falla demostrada.

**Cierre mínimo:** seleccionar una carrera representativa por familia, sin
duplicar toda la matriz BH-060.

### BH061-G7 — Señal CRUD genérica fail-open — **BAJA / NO BLOQUEANTE**

La señal captura fallos de Auditoria y permite que el CRUD continúe. No afecta
los eventos semánticos directos revisados, pero sería inseguro usarla como
garantía de roles/permisos.

**Tratamiento:** documentar que no es evidencia de BH-061. No ampliar esta
tarea a una reescritura del subsistema CRUD genérico.

### BH061-G8 — Grants externos no auditados por producto — **INFORMATIVA**

ORM, SQL, migraciones y aprovisionamiento técnico pueden modificar grupos o
permisos fuera de las APIs. Eso no es una vía autorizada de producto.

**Tratamiento:** mantener Admin/API cerrados y exigir procedimiento externo
confiable. No crear editor ni grants genéricos.

## 8. Riesgos de duplicación y seguridad

1. **Duplicación semántica real:** no-op inicial CLIENTE.
2. **Eventos compuestos:** los hijos y el padre son intencionales, no
   duplicados, siempre que compartan `operation_id` y el padre declare sus IDs.
3. **Eventos genéricos de alta:** un alta puede generar señal CRUD y evento
   semántico. Sólo el segundo prueba el contrato de acceso; no deben contarse
   ambos como dos cambios de rol.
4. **Emails en eventos:** son datos personales, no credenciales. Los IDs son la
   identidad primaria; no agregar teléfonos, documentos, passwords, hashes o
   tokens.
5. **Refresh tokens:** registrar cantidad revocada es suficiente; nunca JTI,
   token ni contenido de credenciales.
6. **Permisos preservados:** no afirmar que un cambio de rol eliminó grants
   individuales o grupos técnicos. La degradación administrativa se bloquea si
   quedarían capacidades residuales peligrosas.
7. **Drift del grupo canónico:** la lectura administrativa ya lo detecta; el
   evento debe referenciar el contrato canónico, no copiar silenciosamente el
   estado posiblemente desviado del grupo.
8. **Inmutabilidad:** API/Admin cumplen. Sellado criptográfico, retención y WORM
   quedan fuera de alcance.

## 9. Propuesta mínima de implementación

### Incremento 1 — Corregir semántica y contrato base

1. Hacer que `assign_initial_client_role()` no cree evento cuando
   `changed=False` y retorne `audit_id=None`.
2. Agregar `role_contract_version` y fingerprints canónicos a eventos que
   asignan o cambian BusinessRole.
3. Centralizar la construcción mínima del payload para evitar diferencias de
   nombres entre altas y cambios, sin migrar eventos históricos.

### Incremento 2 — Correlación de operaciones compuestas

1. Crear un `operation_id` por orquestación compuesta.
2. Propagarlo a vínculo, rol, estado/cuenta y padre.
3. Conservar los IDs de auditoría subordinados actuales.
4. No crear tabla, timeline, exportación ni interfaz nueva.

### Incremento 3 — Condiciones técnicas de acceso

1. Añadir `motivo` a asignar, revocar y reactivar habilidad.
2. Guardar `source`, `reason`, Personal, Usuario vinculado si existe, habilidad
   y before/after.
3. No convertir habilidades en permisos Django ni tocar flags legacy.

### Incremento 4 — Pruebas focales

Agregar sólo pruebas de:

- no-op inicial CLIENTE sin evento;
- metadata/versionado de rol;
- correlación común en cada composición;
- motivo/fuente y no-op de habilidades;
- cardinalidad de Auditoria en las carreras existentes;
- cero evento de éxito en último administrador y residuos rechazados;
- ausencia de password, hash, token y credenciales en los nuevos payloads.

No es necesario repetir la matriz completa de autorización o permisos efectivos
de BH-059/BH-060.

## 10. Criterios verificables de cierre

BH-061 podrá cerrarse cuando se demuestre todo lo siguiente:

1. cada mutación efectiva de BusinessRole produce exactamente un evento base o
   un evento de alta semántico que identifica actor/sistema, objetivo, tiempo,
   operación, antes/después y motivo/fuente;
2. repetir cualquier comando en estado final no crea un evento de cambio;
3. `assign_initial_client_role()` cumple explícitamente el criterio anterior;
4. promoción, degradación y EMPLEADO↔PROFESIONAL quedan cubiertos con rol
   anterior/nuevo y contrato de capacidades versionado;
5. último administrador y privilegios residuales rechazados dejan estado y
   conteo de eventos sin cambios;
6. una falla al crear Auditoria revierte la mutación y no deja hijos huérfanos;
7. cada operación compuesta comparte un `operation_id` y conserva referencias
   verificables a sus componentes;
8. las carreras PostgreSQL producen exactamente la cantidad de eventos
   correspondiente a las mutaciones confirmadas;
9. habilidades, por ser condición de acceso técnico, registran actor,
   before/after, fuente y motivo, o quedan formalmente excluidas con tarea
   independiente explícita;
10. no existe endpoint, serializer ni Admin que permita editar BusinessRole,
    grupos, `user_permissions`, estados de acceso o Auditoria por CRUD genérico;
11. lectura de Auditoria sigue limitada a Usuario activo con
    `gestion.view_audit` y reversión a `gestion.revert_audit` sin campos de
    acceso;
12. ningún evento contiene contraseña, hash, token, JTI, secreto o credencial;
13. intentos rechazados no se publican como eventos de éxito;
14. la evidencia diferencia permisos Django explícitos, capacidades derivadas,
    estados de cuenta/Personal y habilidades técnicas;
15. no se incorpora historial forense avanzado, exportación, retención, editor
    genérico, grants arbitrarios, rediseño UX ni BH-062.

## 11. Conclusión

BH-059 y BH-060 dejaron una base sólida: operaciones semánticas, autoridad por
permisos efectivos, locks, rollback, no-op en casi todos los comandos, lectura
protegida e inmutabilidad por API/Admin. No hace falta reemplazar ese diseño.

BH-061 debe completar el contrato, no ampliar el producto. La corrección del
falso evento de no-op, la correlación uniforme, la versión del contrato de rol,
la auditoría completa de habilidades y las aserciones concurrentes focales son
suficientes para un cierre seguro y verificable.

**Estado final del análisis:** requiere implementación focal; no puede cerrarse
únicamente con evidencia adicional.

`BH-061 — ANÁLISIS COMPLETADO`
