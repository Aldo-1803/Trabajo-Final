# Validacion de impacto del diseno de roles y permisos

**Fecha:** 20 de octubre de 2026
**Modalidad:** analisis estatico del codigo actual
**Politica evaluada:** un rol de negocio por Django Group, permisos de Group mas `user_permissions`, ownership, Personal activo, asignacion y skills

> No se modifico codigo funcional, no se crearon migraciones y no se ejecutaron servidores ni pruebas. Este documento valida impacto y propone una secuencia; no implementa la politica.

## 1. RESUMEN DE IMPACTO

### Evaluacion general

El cambio es **alto** en alcance, pero puede implementarse de forma incremental. La arquitectura de datos ya contiene las piezas basicas necesarias: `Usuario` hereda Groups y Permissions de Django, `Cliente` expresa ownership, `Personal` expresa la relacion laboral, `Turno.profesional` expresa asignacion y existen tres skills booleanos. No hace falta reemplazar autenticacion, usuarios ni perfiles para iniciar la transicion.

El impacto alto proviene de la autorizacion, no del esquema base. Actualmente `is_staff` decide simultaneamente:

- Acceso a endpoints protegidos por `IsAdminUser`.
- Visibilidad global frente a datos propios.
- Posibilidad de crear turnos presenciales.
- Registro de pagos.
- Escritura de diagnosticos y fichas.
- Gestion de rutinas, promociones, productos, configuracion, reportes y auditoria.
- Redireccion, menus y etiquetas del frontend.
- Destinatarios de notificaciones administrativas.

### Clasificacion por area

| Area | Impacto | Motivo |
|---|---|---|
| Modelos `Usuario`, `Cliente`, `Personal` | Medio | Se pueden conservar; Groups y `user_permissions` ya existen. El catalogo de skills puede esperar |
| Login y JWT | Medio | El formato de token puede conservarse; deben centralizarse usuario activo e identidad efectiva |
| Creacion de Cliente | Medio | El backend ya permite cabello opcional, pero falta un flujo presencial autorizado y el frontend obliga diagnostico |
| Creacion/vinculacion de Personal | Critico | El serializer eleva automaticamente a `is_staff` desde un endpoint permitido a cualquier autenticado |
| Turnos y agenda | Alto | Contienen muchos chequeos `is_staff`, ownership parcial, transiciones genericas y falta de asignacion tecnica |
| Ficha, diagnostico, formulas y rutinas | Alto | Deben combinar rol, permiso, Personal activo, skill y asignacion; hoy predominan `is_staff`/`IsAdminUser` |
| Pagos y senas | Alto | EMPLEADO debe tener acceso base, pero hoy todo staff comparte el mismo privilegio y algunas acciones de orden carecen de control laboral |
| Productos, stock, precios y promociones | Alto | Deben pasar de staff global a permisos independientes; no hace falta refactorizar su negocio interno en esta fase |
| Reportes, auditoria y configuracion | Medio-alto | Reemplazo directo de `IsAdminUser` por permisos especificos, con especial cuidado para reversion de auditoria |
| Frontend | Alto en UX, bajo como seguridad | Muchas pantallas cambian, pero no deben bloquear la migracion backend ni ser autoridad de acceso |
| Usuarios existentes | Alto | `is_staff` no distingue empleado, profesional y administrador; un backfill automatico amplio seria inseguro |

### Migracion gradual posible

Pueden introducirse sin cambiar acceso existente:

- Groups y Permissions.
- Servicio de resolucion de rol.
- Contrato `/me` con rol, permisos, `personal_id` y skills.
- Asignacion conservadora de grupos a casos inequivocos.
- Comprobaciones nuevas en modo observacion antes de cortar acceso.
- Migracion endpoint por endpoint, empezando por identidad y Personal.

No deben migrarse parcialmente sin una barrera clara:

- La escritura de rol/is_staff.
- `PersonalSerializer.create()` y su elevacion implicita.
- Finalizacion de turnos y ficha tecnica.
- Cambio generico de estado de turnos.
- Confirmacion de pagos/entregas y operaciones de stock desde ordenes.
- Reversion de auditoria.

### Riesgo principal

El mayor riesgo no es dejar a alguien sin acceso, sino clasificar como ADMINISTRADOR a todo usuario que hoy tiene `is_staff=True`. Ese backfill conservaria el acceso tecnico, pero transformaria accidentalmente empleados y profesionales en administradores permanentes bajo el nuevo modelo.

## 2. MAPA DE DEPENDENCIAS ACTUALES

### Backend y configuracion

| Archivo | Clase/funcion | Dependencia actual | Que comportamiento controla | Impacto del cambio |
|---|---|---|---|---|
| `usuarios/models.py` | `UsuarioManager` | Fija `is_staff`/`is_superuser` al crear cuentas | Usuario normal frente a superusuario | Medio; conservar manager, agregar rol fuera de estos flags |
| `usuarios/models.py` | `Usuario` | Hereda `groups` y `user_permissions` | Capacidades Django disponibles pero no usadas por la API | Bajo y favorable; base de la politica aprobada |
| `usuarios/models.py` | `Cliente` | One-to-one con Usuario | Ownership de datos de cliente | Bajo; reutilizable |
| `usuarios/admin.py` | `UsuarioAdmin` | Edita staff, superuser, Groups y permisos | Privilegios desde Django Admin | Alto; debe evitar fuentes de verdad contradictorias |
| `usuarios/filters.py` | `UsuarioFilter` | Traduce rol a `is_staff` | Filtro Cliente frente a Personal/Staff | Medio; reemplazar por Group de negocio |
| `usuarios/serializers.py` | `UsuarioPerfilReadSerializer` | Expone `is_staff` | Identidad consumida por React | Alto; debe exponer rol/permisos, manteniendo datos personales |
| `usuarios/serializers.py` | `RegistroSerializer` | `create_user()` y `Cliente.objects.create()` | Registro publico y diagnostico inicial opcional | Medio; asignar CLIENTE internamente y no aceptar privilegios |
| `usuarios/views.py` | `LoginView` | `RefreshToken.for_user()` sin `is_active` explicito | Emision de JWT | Alto por usuario inactivo; no requiere cambiar el formato JWT |
| `usuarios/views.py` | `PerfilView` | `request.user`; update asume `Cliente` | Lectura/edicion del perfil propio | Medio; separar identidad comun de perfil Cliente |
| `usuarios/views.py` | `ClienteViewSet` | `IsAdminUser` | Listado de clientes | Alto; EMPLEADO/PROFESIONAL necesitan permiso operativo, no staff |
| `bohemiacore/settings.py` | `REST_FRAMEWORK` | `AllowAny` + `IsAuthenticated` como defaults | Permiso por defecto efectivo: autenticado | Medio; aclarar y simplificar, no cambiar al inicio |
| `bohemiacore/urls.py` | Token/refresh SimpleJWT | Rutas estandar paralelas al login propio | Obtencion y renovacion de token | Medio; conservar temporalmente |
| `gestion/models.py` | `Personal` | `rol`, perfil opcional y skills booleanos | Funcion laboral y aptitud tecnica | Alto; `rol` no debe autorizar, skills se pueden reutilizar temporalmente |
| `gestion/models.py` | `Turno.profesional` | FK a Personal | Asignacion de trabajo | Medio y favorable; reutilizable para reglas tecnicas |
| `gestion/serializers.py` | `PersonalSerializer.create()` | Fuerza `usuario.is_staff=True` | Vinculacion Personal-Usuario y elevacion | Critico; escalada directa |
| `gestion/serializers.py` | `TurnoSerializer` | Ramas por `user.is_staff` | Cliente del turno, canal, estado inicial, pagos | Alto; sustituir por permisos de accion |
| `gestion/serializers.py` | `FichaTecnicaSerializer` | Exige `is_staff` | Registro de formula/ficha | Alto; debe exigir PROFESIONAL/ADMIN, Personal activo, asignacion y skill |
| `gestion/serializers.py` | `DiagnosticoCapilarSerializer` | Autoasigna `request.user` como profesional | Autoria tecnica | Alto; debe validar perfil Personal y skill |
| `gestion/serializers.py` | `UsuarioAdminSerializer` | `is_staff` escribible | Alta/edicion administrativa de cuentas | Critico; rol debe cambiar solo por operacion dedicada |
| `gestion/views.py` | `PersonalViewSet` | `IsAuthenticated` | CRUD completo de Personal | Critico; cualquier cliente autenticado puede operar Personal |
| `gestion/views.py` | `ServicioViewSet` | `is_staff` y `IsAdminUser` | Catalogo completo y escritura de servicios/precios | Alto; separar lectura, servicio y precio |
| `gestion/views.py` | `TurnoViewSet` | `is_staff`, Cliente y chequeos manuales | Visibilidad, alta presencial, reprogramacion, cancelacion, pagos, finalizacion | Critico; nucleo de la politica laboral |
| `gestion/views.py` | `AdminDashboardStatsView` | `IsAdminUser` | Dashboard global | Medio; permiso de dashboard/reportes |
| `gestion/views.py` | `RutinaViewSet` | `is_staff`/`IsAdminUser` | Plantillas, publicacion y usuarios asignados | Alto; PROFESIONAL base, admin y permisos adicionales |
| `gestion/views.py` | `AdminUsuarioViewSet` | `IsAdminUser` | CRUD de usuarios | Critico; todo staff puede administrar privilegios |
| `gestion/views.py` | Productos/promociones | `IsAdminUser`, `get_permissions`, `is_staff` | Productos, precios, stock y promociones | Alto; permisos granulares no base para PROFESIONAL |
| `gestion/views.py` | Agenda/horarios/bloqueos | `IsAuthenticated`, `IsAdminUser`, `Personal.rol` | Lectura y escritura de agenda | Alto; EMPLEADO necesita lectura/operacion, no administracion total |
| `gestion/views.py` | `FichaTecnicaViewSet` | `IsAdminUser`, `is_superuser`, `is_staff` | Acceso y ownership por autor | Alto; superuser no es rol, admin no salta reglas tecnicas |
| `gestion/views.py` | `DiagnosticoCapilarViewSet` | `is_staff` y Cliente | Lectura propia y escritura tecnica | Alto; incorporar skill y cerrar consulta por `cliente_id` |
| `gestion/views.py` | `ContenidoEducativoViewSet` | `is_staff`, `is_superuser`, `perfil_profesional` | Visibilidad, autoria y edicion | Alto; decidir permiso de contenido sin hacerlo base profesional |
| `gestion/views.py` | Ordenes/Pagos | `is_staff`, `IsAdminUser`, queryset por Cliente | Caja y transiciones que afectan stock | Alto; EMPLEADO base para pagos, ownership no debe autorizar operaciones internas |
| `gestion/stats_views.py` | `DashboardStatsViewSet` | `IsAdminUser` | Reportes | Medio; permiso explicito, no base PROFESIONAL |
| `gestion/views_auditoria.py` | Ambos ViewSets | `IsAdminUser` | Lectura y reversion de auditoria | Alto; separar ver y revertir |
| `gestion/signals.py` | Notificaciones | `Usuario.objects.filter(is_staff=True)` | Destinatarios administrativos | Medio; resolver por rol/permiso |
| `gestion/signals.py` | Auditoria generica | `post_save` de Usuario/Personal | Registra campos directos | Alto para roles: cambios M2M de Groups/permisos no quedan auditados automaticamente |
| `gestion/fix_personal_staff.py` | Script manual | Eleva todo Personal vinculado a staff | Reparacion masiva legacy | Critico; no volver a ejecutar durante la migracion |

### Hallazgos transversales

- No se encontraron usos de `has_perm()` en el codigo aplicativo.
- Groups y `user_permissions` solo aparecen en el modelo heredado, migracion inicial y Django Admin.
- No existen permisos personalizados de DRF.
- `IsAdminUser` significa `is_staff=True`; no significa rol ADMINISTRADOR.
- `[IsAuthenticated, IsAdminUser]` es una conjuncion redundante porque `IsAdminUser` ya exige usuario autenticado y staff.
- `Personal.rol` solo controla datos operativos puntuales, filtros/presentacion y una seleccion hardcodeada de colorista; no es fuente consistente de autorizacion.
- Algunas comprobaciones buscan `usuario.personal` o `usuario.profesional`, pero la relacion real es `usuario.perfil_profesional`.

## 3. AUTENTICACION

### Login

**Puede conservarse:** email como identidad, `check_password`, SimpleJWT y el par access/refresh.

**Debe cambiar:** el login propio debe rechazar `is_active=False` antes de emitir tokens. Tambien debe existir una unica funcion/serializer de autenticacion para evitar que `/api/usuarios/login/` y `/api/token/` apliquen reglas distintas.

El rol no debe decidir si las credenciales son validas. Despues de autenticar, el backend resuelve un unico Group de negocio y sus permisos.

### Perfil / me

El perfil actual esta orientado a Cliente y solo expone `is_staff` como informacion de acceso. Debe evolucionar a un contrato de identidad comun:

```text
id, email, nombre, is_active
role
permissions efectivos (Group + user_permissions)
cliente_id opcional
personal_id opcional
personal_activo opcional
skills actuales
```

La edicion de datos de Cliente debe permanecer separada de la identidad comun, porque EMPLEADO, PROFESIONAL o ADMINISTRADOR pueden no tener Cliente. Que un Usuario tenga Cliente y Personal simultaneamente no implica dos roles.

### JWT

**Puede conservarse:** `JWTAuthentication`, URLs y formato de tokens durante la primera fase.

No conviene guardar la lista completa de permisos como autoridad dentro de un access token de siete dias: un cambio/revocacion de rol quedaria desactualizado. Las vistas deben usar `request.user.has_perm()` contra el estado actual; `/me` informa al frontend para UX.

Los claims de rol pueden agregarse mas adelante solo como dato orientativo o para navegacion, nunca como unica fuente de autorizacion.

### Refresh

El endpoint estandar existe, pero el frontend no lo utiliza. La politica objetivo exige que un usuario desactivado no siga renovando acceso. Se necesita una validacion explicita de `is_active` en el flujo de refresh o una comprobacion equivalente probada con la version instalada de SimpleJWT.

### Logout

El backend ya puede poner un refresh token en blacklist. El frontend actualmente solo borra `localStorage`, por lo que debe invocar logout antes de limpiar estado. Este cambio no depende de roles y puede implementarse separadamente.

### Usuario inactivo

Las tres fronteras deben ser coherentes:

| Frontera | Regla futura |
|---|---|
| Login | No emitir tokens |
| Refresh | No renovar access |
| Request autenticada | Rechazar aunque exista un token anterior |

`Personal.activo=False` no equivale a `Usuario.is_active=False`: puede impedir acciones laborales y asignacion, pero la cuenta podria conservar acceso no laboral segun su rol.

### Que no conviene tocar todavia

- No cambiar algoritmo/firma JWT.
- No cambiar duraciones de tokens dentro de la migracion de roles.
- No mover tokens de `localStorage` en el mismo primer cambio.
- No eliminar una de las rutas de login hasta medir consumidores.
- No incluir permisos autoritativos persistentes dentro del JWT.
- No mezclar recuperacion de contrasena con asignacion de rol.

## 4. CREACION DE CLIENTES

### Registro publico actual

`RegistroSerializer` crea `Usuario` y `Cliente` dentro de una transaccion. Los campos capilares y de contacto son opcionales en backend. Solo crea `DiagnosticoCapilar` si al menos uno de los cinco campos capilares tiene valor (`usuarios/serializers.py:273-315`).

Por tanto:

- **El diagnostico no bloquea el registro en backend.**
- **El diagnostico si bloquea efectivamente el formulario publico actual.** `Paso2PerfilCabello.js` marca los cinco selects como `required`, y `Registro.js` espera cargar todos los catalogos antes de mostrar el formulario.
- La creacion automatica del diagnostico ejecuta ademas el motor desde el serializer, acoplando alta de cuenta con logica de gestion.

### Campos minimos actuales

| Nivel | Minimo observado |
|---|---|
| Modelo `Usuario` / manager | Email unico y no vacio; password puede ser no utilizable tecnicamente, aunque el flujo actual exige uno |
| `RegistroSerializer` | Email, nombre, apellido, password y confirmacion |
| Modelo `Cliente` | No agrega campos obligatorios de dominio; `sexo` tiene default |
| Frontend publico | Lo anterior mas los cinco campos capilares por `required` |

Mientras `Usuario.email` siga siendo no nulo, unico y `USERNAME_FIELD`, un cliente presencial con cuenta necesita email. No se recomienda fabricar emails falsos. Si el negocio necesita clientes sin email, eso requiere una decision de identidad y un cambio de modelo separado, no debe ocultarse dentro de esta migracion.

### Alta rapida presencial requerida

No existe hoy un endpoint para que EMPLEADO cree un Cliente: `ClienteViewSet` es de solo lectura, y `AdminUsuarioViewSet` crea Usuario pero no Cliente.

El flujo futuro debe ser dedicado y transaccional:

```text
permiso base: usuarios.create_walkin_client
entrada minima: email, first_name, last_name
opcionales: telefono/zona/datos personales
password: invitacion segura o password no utilizable hasta activacion
salida: Usuario + Cliente + Group CLIENTE
diagnostico: omitido; se completa en otra accion
```

Reglas de seguridad obligatorias:

- El payload no acepta `role`, `groups`, `user_permissions`, `is_staff` ni `is_superuser`.
- El servidor asigna exclusivamente el Group CLIENTE.
- Crear Cliente para un Usuario existente no cambia su rol de acceso; esto permite Cliente + Personal simultaneos.
- Si se crea una nueva cuenta, nunca puede resultar EMPLEADO, PROFESIONAL o ADMINISTRADOR.
- El endpoint valida duplicados por email y no reemplaza silenciosamente cuentas existentes.
- La autoria del alta presencial queda auditada.
- Diagnostico, rutina y turno se crean solo mediante acciones posteriores y permisos independientes.

La pantalla publica puede conservar sus dos pasos si esa es la experiencia deseada. La pantalla presencial debe ser otra UI minima; no conviene reutilizar el formulario publico obligatorio ni relajar sus reglas de forma global solo para el personal.

## 5. PERSONAL

### Estado actual

`Personal` puede crearse por API, Django Admin o frontend. La relacion a Usuario es opcional. El frontend de `GestionPersonal` no envia `usuario`, mientras el serializer API si lo acepta como campo relacional.

`Personal.rol` contiene `colorista`, `asistente` y `administrador`; mezcla puesto/especialidad con autorizacion. Los skills son `realiza_diagnostico`, `realiza_lavado` y `realiza_color`.

### Escalada precisa

La escalada ocurre por la combinacion de dos piezas:

1. `PersonalViewSet.permission_classes = [IsAuthenticated]` permite CRUD a cualquier cuenta autenticada (`gestion/views.py:417-424`).
2. `PersonalSerializer.create()` toma el `usuario` enviado y ejecuta `usuario.is_staff = True; usuario.save()` antes de crear Personal (`gestion/serializers.py:597-608`).

Un CLIENTE autenticado puede crear un Personal vinculado a su propio Usuario o intentar vincular otro ID disponible en el campo relacional. Al quedar staff, obtiene todos los endpoints protegidos por `IsAdminUser`, incluida gestion de usuarios.

### Otras inconsistencias

- Actualizar Personal usa el update generico y no replica la asignacion de staff al cambiar `usuario`.
- Eliminar/desvincular Personal no revoca staff.
- Crear Personal desde Django Admin no pasa por el serializer y no asigna staff.
- El script `fix_personal_staff.py` fuerza staff para todos los perfiles vinculados.
- `Personal.activo` no controla actualmente la mayoria de acciones autenticadas del usuario.
- `Personal.rol='administrador'` no concede permisos por si solo.

### Contencion prioritaria

Lo primero es eliminar la elevacion implicita del CRUD generico: vincular/crear Personal no debe cambiar `is_staff`, Groups ni permisos. La vinculacion de cuenta y el cambio de rol deben ser operaciones dedicadas, separadas y auditadas.

Tambien debe cerrarse el CRUD de Personal a quien tenga un permiso explicito de gestion. Mientras la infraestructura nueva no exista, no conviene profundizar la dependencia en `IsAdminUser` como solucion definitiva.

### Comportamiento reutilizable temporalmente

- Mantener Personal sin Usuario para integrantes que no inician sesion.
- Mantener la relacion one-to-one y `related_name='perfil_profesional'`.
- Mantener nombre, contacto, activo, color de calendario, horarios y bloqueos.
- Mantener `rol` como dato operativo legacy, sin usarlo para autorizar.
- Mantener los tres booleanos de skills como controles tecnicos temporales.
- Mantener `Turno.profesional` como asignacion al perfil Personal.
- No cambiar automaticamente flags o Groups al guardar Personal.

## 6. ENDPOINTS AFECTADOS POR ROLES

Prioridades: P0 contencion, P1 frontera de identidad/operacion, P2 granularidad administrativa, P3 UX/limpieza.

| Endpoint / accion | Regla actual | Regla futura propuesta | Tipo de cambio | Prioridad |
|---|---|---|---|---|
| Registro publico de usuario/Cliente | `AllowAny`; crea usuario no staff | Siempre crea CLIENTE; ignora campos privilegiados | Asignacion interna de Group | P1 |
| Alta presencial de Cliente | No existe | EMPLEADO, PROFESIONAL y ADMIN con `create_walkin_client`; sin diagnostico obligatorio | Endpoint/accion dedicada | P1 |
| Perfil propio | Autenticado; serializer de Cliente, expone staff | Ownership propio; identidad comun mas perfiles opcionales | Contrato y ownership | P1 |
| Listar clientes | `IsAdminUser` | EMPLEADO/PROFESIONAL base; ADMIN; permiso `view_clients` | Reemplazo de permiso | P1 |
| CRUD usuarios | Cualquier staff | ADMIN con `manage_users`; sin cambio de rol implicito | Reemplazo y separacion | P0/P1 |
| Cambiar rol | Escritura de `is_staff` en CRUD | Accion dedicada `assign_role`, ADMIN autorizado, auditada | Nueva frontera critica | P1 |
| CRUD Personal | Cualquier autenticado | ADMIN o permiso `manage_personal`; sin side effects de rol | Cierre de escalada | P0 |
| Ver agenda global | Cualquier autenticado en varios endpoints | EMPLEADO/PROFESIONAL/ADMIN; Cliente solo disponibilidad publica | Reemplazo de permiso | P1 |
| Administrar horarios/bloqueos | Staff para horarios; cualquier autenticado puede crear bloqueo | ADMIN o permiso especifico `manage_schedules` | Cierre de escritura | P1 |
| Crear turno propio | Cliente autenticado, inferido por no staff | CLIENTE sobre su Cliente; tambien quien tenga perfil Cliente, sin importar rol, mediante modo propio | Ownership | P1 |
| Crear turno para cliente | Rama `is_staff` | EMPLEADO/PROFESIONAL/ADMIN con permiso base y Cliente elegido | Permiso de accion | P1 |
| Registrar llegada | No hay accion explicita; se puede PATCHear estado | EMPLEADO/PROFESIONAL/ADMIN con permiso `register_arrival`; transicion definida | Nueva accion; cerrar PATCH generico | P1 |
| Reprogramar/cancelar propio | Ownership parcial y ramas por staff | Dueno bajo reglas; acciones laborales para EMPLEADO/PROFESIONAL/ADMIN | Normalizar permiso + ownership | P1 |
| Reprogramar/cancelar de cliente | Staff global; deteccion profesional usa relaciones incorrectas | EMPLEADO/PROFESIONAL base; ADMIN, sin requerir skill tecnica | Reemplazo de permiso | P1 |
| Confirmar sena | PATCH de estado/pago por staff | EMPLEADO/PROFESIONAL/ADMIN con `confirm_deposit` | Accion dedicada | P1 |
| Registrar pagos | Chequeo `is_staff` | EMPLEADO/PROFESIONAL/ADMIN base `register_payments` | Reemplazo de permiso | P1 |
| Finalizar servicio | Cualquier autenticado sobre objeto visible | PROFESIONAL o ADMIN con Personal activo, turno asignado y skill; override separado/auditado | Critico: permiso + asignacion + skill | P0/P1 |
| Ficha tecnica/formulas | `IsAdminUser`; staff autor | Solo PROFESIONAL/ADMIN con Personal activo, asignacion y skill | Reglas tecnicas completas | P1 |
| Diagnosticos propios | Cliente autenticado, queryset propio | Cliente: lectura propia | Reutilizar ownership | P1 |
| Crear/editar diagnostico | `is_staff` | PROFESIONAL/ADMIN con Personal activo y `realiza_diagnostico`; no bypass admin | Permiso + skill | P1 |
| Rutinas de cliente | Propias o staff global | Cliente propias; PROFESIONAL/ADMIN segun permiso y alcance | Ownership + permiso | P1 |
| Gestionar plantillas de rutina | `IsAdminUser` | PROFESIONAL base; ADMIN; permiso explicito para otros | Reemplazo de permiso | P1 |
| Ver productos | Publico | Mantener lectura publica/autenticada segun negocio | Sin impacto de rol | P3 |
| Gestionar productos | Staff | ADMIN o permiso adicional; no base PROFESIONAL | Permiso granular | P2 |
| Ver stock | Parte del catalogo/endpoint publico | EMPLEADO/PROFESIONAL/ADMIN; no exponer cantidades operativas publicamente | Separar lectura operativa | P2 |
| Modificar stock | Staff mediante productos/ordenes | ADMIN; EMPLEADO/PROFESIONAL solo con permiso adicional | Permiso granular | P2 |
| Modificar precios | Staff junto con productos/servicios | ADMIN; permiso adicional explicito | Separar campo/accion | P2 |
| Promociones | Staff escribe | ADMIN; permiso adicional, no base PROFESIONAL | Reemplazo de permiso | P2 |
| Contenido educativo | Personal/staff por chequeos manuales | Publicado para clientes; gestion solo con permiso `manage_content`; no base PROFESIONAL | Permiso + autoria | P2 |
| Reportes | `IsAdminUser` | ADMIN o permiso adicional `view_reports` | Reemplazo directo | P2 |
| Auditoria, lectura | `IsAdminUser` | ADMIN con `view_audit`; posibles concesiones explicitas de solo lectura | Reemplazo directo | P2 |
| Auditoria, reversion | Mismo permiso que lectura | ADMIN con `revert_audit`; operacion auditada | Separar permiso sensible | P1/P2 |
| Configuracion global | `IsAdminUser` | ADMIN con `manage_configuration` | Reemplazo directo | P2 |
| Ordenes: confirmar/cancelar/entregar | Autenticado; Cliente puede accionar sobre propia orden | Operacion laboral con permisos; Cliente solo consulta/cancelacion comercial expresamente permitida | Cerrar acciones | P1 |

## 7. OWNERSHIP

### Inventario

| Ubicacion | Control actual | Clasificacion | Reutilizacion/correccion |
|---|---|---|---|
| `PerfilView` | Usa `request.user` | Correcto y reutilizable para identidad | Separar campos Cliente para usuarios sin Cliente |
| `DiagnosticoView` | Usa `request.user.cliente` | Correcto y reutilizable | Mantener para "mi diagnostico" |
| `TurnoViewSet.get_queryset()` | Cliente ve `cliente=request.user.cliente` | Correcto y reutilizable para Cliente | Reemplazar bypass staff por permisos/alcance laboral |
| `TurnoViewSet.perform_update()` | No staff solo puede actualizar turno propio | Incompleto | Limita objeto, pero no campos/transiciones permitidas |
| `reprogramar_cliente` | Compara `turno.cliente.usuario` | Correcto para dueno | Mantener junto con politica temporal/disponibilidad |
| `gestionar_cancelacion` | Dueno, profesional detectado incorrectamente o staff | Incorrecto | Usar `perfil_profesional`, permiso y alcance explicito |
| `gestionar_profesional` | Busca relacion inexistente `usuario.profesional`; staff global | Incorrecto | Exigir permiso laboral; asignacion solo cuando la accion lo requiera |
| `finalizar_turno` | Depende del queryset; no chequea actor tecnico | Incompleto/critico | Exigir rol, Personal activo, asignacion y skill |
| `MiAgendaCuidadosView` | Filtra por `request.user.cliente` | Correcto y reutilizable | Manejar usuario sin Cliente con 403 controlado |
| `NotificacionViewSet` | Filtra por `usuario=request.user` | Correcto y reutilizable | Sin cambio de rol |
| Aceptar adelanto | Busca turno con Cliente actual | Correcto y reutilizable | Agregar validacion transaccional, fuera del alcance de roles |
| `RutinaClienteViewSet.get_queryset()` | Cliente ve propias; staff todas | Correcto para Cliente, incompleto laboral | Sustituir staff por permiso y alcance |
| Acciones de rutina cliente | Comparan dueno o staff | Incompleto | Mantener dueno; reemplazar bypass staff |
| `CarritoViewSet` | Resuelve Cliente actual y su carrito | Correcto y reutilizable | Sin cambio de rol; aplica tambien a rol laboral con Cliente |
| `MeGustaViewSet` | Queryset y create con Cliente actual | Correcto y reutilizable | Sin cambio de rol |
| `ContenidoGuardadoViewSet` | Queryset y create con Cliente actual | Correcto y reutilizable | Sin cambio de rol |
| `ContenidoEducativoViewSet` update | Autor o staff | Incompleto | Permiso de contenido + autoria; destroy carece de control equivalente |
| `DiagnosticoCapilarViewSet.get_queryset()` | Cliente propio; staff todos | Correcto para Cliente, incompleto laboral | Reemplazar staff y exigir skill para escritura |
| `DiagnosticoCapilarViewSet.por_cliente` | Filtra directamente por `cliente_id` | Incorrecto | No usa queryset acotado; un Cliente puede consultar ID ajeno |
| `FichaTecnicaViewSet` | Staff ve propias; superuser todas | Incompleto | Autor no equivale a asignado; ADMIN tampoco debe saltar skill/asignacion |
| `OrdenPendienteViewSet.get_queryset()` | Cliente propias; staff todas | Correcto para lectura | Acciones operativas heredadas siguen disponibles al dueno |
| `OrdenCompraViewSet.get_queryset()` | Cliente propias; staff todas | Correcto para lectura | Confirmar entrega/cancelar requieren permiso laboral separado |
| Checkout/generacion de pago | Resuelve Cliente desde `request.user` | Correcto y reutilizable | Sin cambio de rol |
| `PersonalViewSet` | Sin ownership ni permiso de gestion | Inexistente | Debe ser administracion por permiso explicito |
| Agenda general/bloqueos | Sin ownership laboral | Inexistente | Lectura por rol; escritura por permiso; agenda propia/asignada si se diferencia |

### Regla de diseno

El rol no reemplaza ownership. Un Usuario con rol PROFESIONAL y perfil Cliente debe seguir viendo su carrito, sus pedidos y sus turnos como cliente. De forma separada, sus permisos laborales le permiten operar objetos de terceros. La API debe distinguir la accion "propia" de la accion "laboral", aunque ambas pertenezcan al mismo Usuario.

## 8. PERSONAL + ASIGNACION + SKILLS

### Logica existente reutilizable

| Elemento | Uso actual | Valor para la transicion |
|---|---|---|
| `Turno.profesional` | FK opcional a Personal | Fuente adecuada para verificar asignacion tecnica |
| `Personal.activo` | Filtra disponibilidad, carga masiva de horarios y promociones | Puede ser precondicion laboral desde la primera fase |
| `HorarioLaboral.personal` | Disponibilidad por integrante | Reutilizable |
| `realiza_color` | Filtra reglas para categorias de diseno/color | Reutilizable temporalmente, aunque la inferencia por texto es fragil |
| `realiza_lavado` | Filtra reglas para complementos/lavado | Reutilizable temporalmente |
| `realiza_diagnostico` | Se muestra/administra, pero no se aplica al endpoint de diagnostico | Debe incorporarse como control temporal |
| `FichaTecnica.profesional_autor` | Guarda Usuario autor | Sirve para auditoria, pero no sustituye `Turno.profesional` |
| `DiagnosticoCapilar.profesional` | Guarda Usuario autor | Sirve para autoria; debe relacionarse con Personal valido |
| `perfil_profesional` | Deteccion correcta en contenido | Debe ser el acceso canonico de Usuario a Personal |

### Brechas actuales

- Finalizar un turno no exige que `request.user.perfil_profesional == turno.profesional`.
- Ficha tecnica no exige asignacion al turno.
- Diagnostico no exige `realiza_diagnostico`.
- `Personal.activo` no se comprueba al crear diagnostico, ficha, formula o finalizar.
- ADMINISTRADOR hoy pasa por staff/superuser; la politica aprobada exige las mismas reglas tecnicas que PROFESIONAL.
- No existe skill para corte, secado, tratamiento u otras tareas; no deben inventarse equivalencias amplias.
- Hay dos algoritmos de disponibilidad: uno usa Personal/skills y otro toma el primer horario sin validar las mismas capacidades.

### Uso temporal recomendado de booleanos

Sin crear aun `Habilidad`, las primeras reglas tecnicas pueden mapearse asi:

| Accion | Requisito temporal |
|---|---|
| Crear diagnostico | Personal activo + `realiza_diagnostico=True` |
| Operar servicio de color/formula | Personal activo + asignado + `realiza_color=True` |
| Operar lavado/complemento | Personal activo + asignado + `realiza_lavado=True` |
| Finalizar servicio | Personal activo + asignado + skill conocida del servicio |
| ADMINISTRADOR tecnico | Exactamente los mismos requisitos; sin bypass implicito |

Para servicios sin correspondencia segura, debe definirse una regla explicita antes de bloquearlos. No conviene tratar `realiza_color=True` como skill universal.

Los overrides administrativos deben ser endpoints/acciones distintos, requerir un permiso como `override_technical_rule`, exigir motivo y quedar auditados. No deben implementarse como `if admin: allow` dentro de la accion tecnica normal.

## 9. FRONTEND

| Archivo/componente | Logica actual | Cambio futuro requerido |
|---|---|---|
| `routes/ProtectedRoute.js` | Solo comprueba presencia de access token | Cargar `/me` y aceptar permiso requerido; cambio de UX, backend sigue siendo seguridad |
| `routes/index.js` | Todas las rutas Cliente y Admin usan el mismo guard | Declarar permisos por ruta y permitir rutas laborales a EMPLEADO/PROFESIONAL |
| `routes/routes.js` | Agrupa todo lo operativo bajo `ADMIN_ROUTES` | Puede conservar URLs; renombrar/reagrupar es UX y no es requisito de seguridad inicial |
| `pages/auth/Login.js` | Redirige por `is_staff` y guarda copia en `user_info` | Redirigir por rol/permisos del contrato `/me` |
| `components/Header.js` | Menu binario admin/cliente por `is_staff` | Construir menu por permisos efectivos; soportar Usuario con Cliente + Personal |
| `components/CampanaNotificaciones.js` | Decide destinos usando `user_info.is_staff` | Usar rol/permisos del contexto actual; no confiar en localStorage |
| `pages/admin/DashboardAdmin.js` | Muestra todos los accesos; un 403 tardio redirige | Dashboard por capacidades; ocultar modulos no concedidos |
| `pages/admin/GestionUsuarios.js` | Filtro cliente/staff y checkbox que escribe `is_staff` | Mostrar rol Group; quitar checkbox; cambio de rol por dialogo/endpoint dedicado |
| `pages/admin/GestionPersonal.js` | Edita puesto y skills; no vincula Usuario | Mantener datos operativos; vinculacion/rol en flujo dedicado y autorizado |
| `pages/admin/NuevoTurno.js` | "Panel Profesional"; cualquier token alcanza la ruta | Visible a EMPLEADO/PROFESIONAL/ADMIN con permiso `create_turno_for_client` |
| `pages/admin/GestionTurnos.js` | Todos los botones se muestran juntos | Mostrar llegada, sena, pago, ficha y finalizacion por permisos; backend valida siempre |
| `pages/admin/RegistroFichaTecnica.js` | Se abre desde gestion general de turnos | Solo UX para actores con permiso; backend exige Personal/asignacion/skill |
| `pages/admin/HistorialPagos.js` | Pagina administrativa unica | Visible a quien tenga `view_cash`/`register_payments` |
| `pages/admin/Reportes.js` | Ruta admin generica | Visible solo con `view_reports` |
| `pages/admin/Auditoria.js` | Lectura y reversion en la misma pantalla | Separar botones por `view_audit` y `revert_audit` |
| `pages/admin/ConfiguracionAdmin.js` | Ruta admin generica | Solo `manage_configuration` |
| `pages/auth/Registro.js` | Dos pasos; siempre carga catalogos capilares | Conservar publico; agregar flujo presencial separado y minimo |
| `pages/auth/Paso2PerfilCabello.js` | Cinco selects obligatorios | No reutilizar para alta presencial; diagnostico posterior |
| `api/axiosConfig.js` | En 401 borra sesion; no refresh/logout remoto | Integrar estado de identidad y, en fase separada, refresh/logout |

### Seguridad frente a UX

- **Cambio de seguridad:** permission classes, `has_perm`, ownership, Personal activo, asignacion, skills y auditoria en backend.
- **Cambio de UX:** rutas visibles, menus, botones, labels y redireccion de login.
- Ocultar un boton nunca reemplaza el control backend.
- La migracion backend puede avanzar antes que la UI; temporalmente un usuario podria ver una pantalla y recibir 403, lo cual es preferible a conceder acceso indebido.

## 10. COMPATIBILIDAD CON USUARIOS EXISTENTES

| Escenario actual | Rol/manejo propuesto | Como preservar acceso sin elevar |
|---|---|---|
| Cliente sin Personal | Group CLIENTE | Backfill automatico si no es staff/superuser; conservar Cliente y credenciales |
| Personal sin Usuario | Sin Group porque no hay identidad digital | Conservar Personal, horarios, turnos y skills; vincular cuenta solo mediante flujo posterior |
| Usuario staff sin Personal | Ambiguo | No asignar ADMIN automaticamente; mantener temporalmente acceso legacy y enviar a revision manual |
| Personal colorista vinculado | Candidato PROFESIONAL | Asignar solo tras validar que es una funcion tecnica real; conservar `is_staff` temporal hasta migrar endpoints usados |
| Personal asistente vinculado | Candidato EMPLEADO | Asignar EMPLEADO; conservar permisos base aprobados y revisar adicionales |
| Personal administrador vinculado | Candidato sujeto a revision | No confiar solo en `Personal.rol`; confirmar responsabilidad administrativa antes de ADMINISTRADOR |
| Usuario con Cliente + Personal | Un solo rol laboral, ambos perfiles conservados | Si es EMPLEADO/PROFESIONAL/ADMIN mantiene acciones propias por ownership de Cliente y acciones laborales por permiso |
| Superusuario | Fuera de roles normales | Conservar superuser para emergencia/Django Admin; si usa SPA, asignar Group ADMINISTRADOR de forma explicita y auditada |

### Casos de inconsistencia a reportar antes del backfill

- Usuario en mas de un Group de rol.
- Staff sin Personal y sin responsabilidad administrativa conocida.
- Personal vinculado a usuario inactivo.
- Personal inactivo vinculado a usuario con acceso laboral.
- Usuario laboral sin Personal.
- Dos fuentes con nombres/emails divergentes.
- Personal `administrador` cuyo Usuario no es staff, o staff con `Personal.rol` no administrativo.
- Usuario con Cliente y Personal que hoy es clasificado de manera diferente por frontend y backend.

### Estrategia compatible

Durante la transicion, mantener `is_staff` sin modificar para no romper endpoints aun no migrados. Cada endpoint migrado deja de consultar staff y pasa a permisos. Solo cuando no queden dependencias de negocio se recalcula `is_staff` exclusivamente para Django Admin.

Esta compatibilidad temporal esta justificada por datos persistidos y rutas en uso. Debe tener fecha de retiro y no aceptar nuevas elevaciones por el mecanismo legacy.

## 11. ORDEN DE IMPLEMENTACION

No se propone un refactor general. Cada paso debe poder revisarse y desplegarse por separado.

### Paso 1. Tests de seguridad actuales

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Nuevos tests en `bohemiacore/usuarios/tests/` y `bohemiacore/gestion/tests/` |
| Riesgo | Bajo |
| Dependencia | Ninguna |
| Trabajo | Reproducir login inactivo, escalada al crear Personal, escritura de `is_staff`, finalizacion por Cliente y acciones de orden |
| Criterio de terminado | Cada vulnerabilidad tiene prueba que falla antes de su contencion y pasa con el cambio correspondiente; se documentan respuestas actuales |

### Paso 2. Cerrar escalada Personal/is_staff

| Elemento | Detalle |
|---|---|
| Archivos aproximados | `gestion/serializers.py`, `gestion/views.py`, tests |
| Riesgo | Bajo-medio |
| Dependencia | Paso 1 |
| Trabajo | El CRUD generico de Personal no puede vincular Usuario ni modificar staff/Groups; no usar aun un nuevo sistema completo de roles |
| Criterio de terminado | Un Cliente autenticado no puede elevar ninguna cuenta; crear/editar Personal no cambia privilegios; UI actual sin `usuario` sigue funcionando |

### Paso 3. Crear infraestructura de roles

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Permisos nuevos, servicio de rol, migracion de datos idempotente, tests |
| Riesgo | Medio |
| Dependencia | Paso 2 |
| Trabajo | Crear Groups, permisos base y adicionales; imponer un unico Group de rol; no cambiar aun autorizacion de endpoints |
| Criterio de terminado | Roles/permisos se crean de forma reproducible; ningun acceso existente cambia; doble rol es rechazado |

### Paso 4. Operacion dedicada de cambio de rol

| Elemento | Detalle |
|---|---|
| Archivos aproximados | `usuarios/views.py`, `usuarios/serializers.py`, `usuarios/urls.py`, auditoria, tests |
| Riesgo | Alto por privilegios, acotado por superficie |
| Dependencia | Paso 3 |
| Trabajo | Endpoint ADMIN con `assign_roles`; validaciones de Personal para roles laborales; registro explicito antes/despues/actor/motivo |
| Criterio de terminado | Ningun serializer generico escribe rol, Groups, staff o superuser; todo cambio de rol queda auditado |

### Paso 5. Contrato `/me` y usuario activo

| Elemento | Detalle |
|---|---|
| Archivos aproximados | `usuarios/views.py`, `usuarios/serializers.py`, login/refresh y tests |
| Riesgo | Medio |
| Dependencia | Paso 3 |
| Trabajo | Exponer rol/permisos/perfiles/skills; rechazar inactivos en login y refresh |
| Criterio de terminado | Los cuatro roles reciben identidad coherente; inactivos no obtienen/renuevan tokens; login existente activo no se rompe |

### Paso 6. Inventario y backfill conservador

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Comando/reporte de solo lectura y migracion de datos revisada |
| Riesgo | Alto por datos |
| Dependencia | Pasos 3-5 |
| Trabajo | Clasificar casos inequivocos, listar ambiguos y asignar Groups sin tocar `is_staff` |
| Criterio de terminado | Conteos conciliados; ningun staff ambiguo se vuelve ADMIN; rollback/procedimiento documentado |

### Paso 7. Identidad, usuarios, clientes y Personal

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Apps `usuarios`, `PersonalViewSet`, filtros y tests |
| Riesgo | Medio-alto |
| Dependencia | Pasos 4-6 |
| Trabajo | Reemplazar `IsAdminUser`; alta presencial CLIENTE; permisos `view_clients`, `manage_users`, `manage_personal` |
| Criterio de terminado | Roles aprobados acceden segun matriz; alta Cliente nunca asigna privilegios; Personal no altera rol |

### Paso 8. Turnos, agenda, llegada, senas y pagos

| Elemento | Detalle |
|---|---|
| Archivos aproximados | `gestion/views.py`, `serializers.py`, filtros, tests |
| Riesgo | Alto |
| Dependencia | Paso 7 |
| Trabajo | Acciones explicitas por transicion; permisos base EMPLEADO/PROFESIONAL; ownership Cliente; retirar PATCH libre de campos sensibles |
| Criterio de terminado | Matriz de transiciones por rol pasa; EMPLEADO cumple capacidades aprobadas; Cliente no ejecuta acciones laborales |

### Paso 9. Reglas tecnicas con skills actuales

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Turnos, diagnosticos, fichas, rutinas, tests |
| Riesgo | Alto |
| Dependencia | Paso 8 |
| Trabajo | Personal activo, asignacion y booleanos de skill; override administrativo separado/auditado |
| Criterio de terminado | PROFESIONAL y ADMIN cumplen las mismas precondiciones tecnicas; acciones no asignadas/sin skill devuelven 403 |

### Paso 10. Permisos administrativos granulares

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Productos, promociones, stats, auditoria, configuracion y tests |
| Riesgo | Medio-alto |
| Dependencia | Pasos 3-6 |
| Trabajo | Separar stock, precio, promociones, reportes, auditoria y configuracion; no refactorizar la logica interna |
| Criterio de terminado | PROFESIONAL no recibe esos permisos por defecto; permisos adicionales funcionan y se auditan |

### Paso 11. Frontend por capacidades

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Auth context, rutas, Header, Login, dashboard y paginas afectadas |
| Riesgo | Medio |
| Dependencia | `/me` y endpoints migrados |
| Trabajo | Guards, menus y botones por permisos; flujo presencial minimo; logout backend |
| Criterio de terminado | Cada rol ve una navegacion util; manipular estado local no cambia resultados backend |

### Paso 12. Retirar staff de negocio

| Elemento | Detalle |
|---|---|
| Archivos aproximados | Busqueda global de `is_staff`/`IsAdminUser`, signals, filtros, frontend, script legacy |
| Riesgo | Medio |
| Dependencia | Todos los endpoints de negocio migrados |
| Trabajo | Reservar staff a Django Admin; retirar compatibilidad y script de elevacion |
| Criterio de terminado | Ninguna decision de negocio usa staff; busquedas y tests lo demuestran |

## 12. PRIMER CAMBIO REAL RECOMENDADO

El primer cambio de codigo debe ser **eliminar la elevacion implicita de privilegios al crear o editar Personal**, acompanado de tests focalizados.

Alcance recomendado del primer PR:

- `PersonalSerializer` no acepta `usuario` como campo escribible en el CRUD generico.
- `PersonalSerializer.create()` no modifica `usuario.is_staff`.
- Ningun save de Personal cambia Groups, `user_permissions`, `is_staff` o `is_superuser`.
- Tests prueban que un autenticado no puede elevarse enviando un ID de Usuario.
- Tests prueban que crear Personal sin Usuario, como hace la UI actual, mantiene su comportamiento.

### Por que este cambio primero

- Cierra la vulnerabilidad mas directa sin requerir migraciones ni Groups ya cargados.
- No cambia permisos ni roles de usuarios existentes.
- No invalida tokens ni rompe login.
- El frontend actual de Personal no envia `usuario`, por lo que el riesgo funcional es bajo.
- Establece el principio aprobado de que vincular Personal y cambiar rol son operaciones diferentes.
- Es facil de verificar con una prueba negativa de escalada y una prueba positiva de alta de Personal sin cuenta.

No se recomienda como solucion final cambiar solamente `PersonalViewSet` a `IsAdminUser`: reduciria exposicion, pero seguiria usando `is_staff` como rol de negocio y permitiria a cualquier staff legacy ejecutar la elevacion.

## 13. COSAS QUE NO DEBEMOS TOCAR TODAVIA

- Refactor general de `TurnoViewSet` o division del archivo monolitico.
- Reescritura del motor de disponibilidad.
- Nuevo catalogo completo `Habilidad` y migracion de todos los skills.
- Cambio de `Personal.rol` o de sus choices.
- Eliminacion de perfiles Cliente/Personal duplicados en un mismo Usuario.
- Cambio estructural de email como identidad o soporte de clientes sin email.
- Mercado Pago, webhook, checkout y URLs de retorno.
- Algoritmos de stock, reserva, liberacion o concurrencia.
- Calculo de precios, descuentos o promociones.
- Refactor de senales y automatizaciones post-servicio, salvo destinatarios/permisos cuando llegue su paso.
- Cambio de duracion, firma o almacenamiento de JWT.
- Eliminacion inmediata de `/api/token/` o del login propio.
- Rediseno visual del frontend o cambio masivo de rutas `/admin`.
- Refactor general de Axios o de todas las llamadas hardcodeadas.
- Consolidacion de vistas/reportes duplicados.
- Limpieza de migraciones existentes.
- Eliminacion inmediata de `is_staff` en datos persistidos.
- Asignacion automatica de ADMINISTRADOR a todos los staff.
- Uso de `Personal.rol` como atajo para autorizar mientras se crea Groups.
- Inclusion de permisos efectivos como autoridad fija dentro de JWT.

En esta fase si deben tocarse, de manera acotada, las fronteras de permiso de stock/pagos cuando se migren sus endpoints. Lo que queda fuera es el refactor de su logica de negocio interna.

## 14. CONCLUSION

### Compatibilidad con la arquitectura actual

**Si, la politica aprobada es compatible.** Django Groups, Permissions y `user_permissions` ya forman parte de `Usuario`; `Cliente`, `Personal` y `Turno.profesional` permiten expresar ownership, contexto laboral y asignacion. La migracion es principalmente de autorizacion y contratos, no una sustitucion del dominio.

### Parte reutilizable

- Autenticacion por email y JWT.
- `Usuario.is_active` como estado de cuenta.
- Groups y Permissions heredados.
- `Cliente` para ownership.
- `Personal` y `perfil_profesional` para contexto laboral.
- `Personal.activo`, horarios y bloqueos.
- `Turno.profesional` para asignacion.
- Booleanos `realiza_diagnostico`, `realiza_color` y `realiza_lavado` como skills temporales.
- Querysets propios de turnos, carrito, rutinas, notificaciones, likes, guardados y ordenes.
- Infraestructura de auditoria, extendiendola para cambios M2M de rol/permisos.

### Parte a retirar progresivamente

- `is_staff` como rol o permiso de negocio.
- `IsAdminUser` en la API de negocio.
- Escritura generica de `is_staff`.
- Elevacion automatica desde Personal y `fix_personal_staff.py`.
- Bypass universales por staff/superuser.
- Clasificacion binaria Administrador/Cliente del frontend.
- `Personal.rol` como mezcla de puesto y autorizacion.
- Chequeos de relaciones inexistentes `usuario.personal`/`usuario.profesional`.

### Mayor riesgo

El mayor riesgo es un backfill incorrecto que convierta todo staff en ADMINISTRADOR o que retire `is_staff` antes de migrar los endpoints que aun dependen de el. La mitigacion es asignacion conservadora, revision de ambiguos y corte modulo por modulo.

### Secuencia recomendada

```text
tests de seguridad
-> cerrar escalada Personal/is_staff
-> crear Groups y Permissions sin cambiar acceso
-> operacion de rol dedicada y auditada
-> /me + usuario activo
-> inventario/backfill conservador
-> usuarios, clientes y Personal
-> turnos, agenda, senas y pagos
-> reglas tecnicas con skills booleanos
-> permisos administrativos granulares
-> frontend por capacidades
-> retirar is_staff del negocio
```

El primer PR no debe intentar implementar los cuatro roles completos. Debe cerrar la elevacion implicita de Personal con tests y dejar intactos los usuarios existentes. Esa contencion crea una base segura para introducir la infraestructura aprobada sin mezclarla con refactors funcionales.
