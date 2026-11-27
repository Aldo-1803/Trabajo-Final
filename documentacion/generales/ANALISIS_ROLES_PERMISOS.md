# Analisis de usuarios, roles y permisos

**Fecha:** 20 de octubre de 2026
**Modalidad:** analisis estatico, sin cambios funcionales ni ejecucion del sistema
**Alcance:** usuarios, perfiles, autenticacion, autorizacion, roles de negocio y habilidades operativas

> Este documento describe el estado observado en el repositorio. No se ejecutaron servidores, pruebas, migraciones ni consultas a la base de datos. La propuesta es de transicion: no representa cambios ya implementados.

## 1. MODELO ACTUAL DE USUARIOS

### Usuario

`usuarios.Usuario` hereda de `AbstractUser` y usa email como identificador (`usuarios/models.py:51`). Sus particularidades son:

| Campo o capacidad | Estado actual |
|---|---|
| `email` | Unico y obligatorio; es `USERNAME_FIELD` |
| `username` | Eliminado (`None`) |
| `first_name`, `last_name` | Heredados de `AbstractUser`; requeridos por el manager para superusuarios |
| `is_active` | Heredado; representa habilitacion de la cuenta |
| `is_staff` | Heredado; hoy se usa como rol de negocio y como autorizacion API, ademas de su significado nativo de acceso a Django Admin |
| `is_superuser` | Heredado; concede todos los permisos Django y se usa expresamente solo en pocos flujos |
| `groups` | Heredado; administrable desde Django Admin, pero no utilizado por la API ni el frontend |
| `user_permissions` | Heredado; administrable desde Django Admin, pero no se encontraron llamadas a `has_perm()` ni permisos DRF basados en estos valores |
| Campo `rol` | No existe en `Usuario` |
| Campo `es_cliente` | No existe en el modelo; la asignacion de `RegistroView` es un atributo transitorio sin persistencia de esquema |

El manager establece `is_staff=False` e `is_superuser=False` al crear un usuario normal, y ambos en `True` al crear un superusuario (`usuarios/models.py:23-47`).

### Cliente

`usuarios.Cliente` es un perfil de dominio con relacion `OneToOneField` a `Usuario`, usa el usuario como clave primaria y se elimina en cascada con la cuenta (`usuarios/models.py:66-72`). Contiene datos de contacto y cabello, mas un segundo indicador de estado llamado `activo`.

La existencia de `Cliente` es usada en distintos lugares como prueba implicita de que el usuario es cliente. No existe una restriccion que impida que el mismo `Usuario` tenga simultaneamente `Cliente` y `Personal`.

### Personal

`gestion.Personal` es un perfil operativo opcional (`gestion/models.py:26-66`). Puede existir sin cuenta de acceso y puede vincularse uno a uno con un `Usuario` mediante `related_name='perfil_profesional'`.

| Campo | Funcion actual |
|---|---|
| `usuario` | Vinculo opcional con la cuenta; `SET_NULL` al eliminar el usuario |
| `nombre`, `apellido`, `email`, `telefono` | Datos operativos duplicados parcialmente respecto de `Usuario` |
| `rol` | Choice operativo: `colorista`, `asistente`, `administrador` |
| `realiza_diagnostico` | Habilidad booleana; por defecto `False` |
| `realiza_lavado` | Habilidad booleana; por defecto `True` |
| `realiza_color` | Habilidad booleana; por defecto `False` |
| `activo` | Habilita el registro operativo, independientemente de `Usuario.is_active` |
| `color_calendario` | Presentacion en agenda |
| `horarios` | Relacion inversa con `HorarioLaboral` |
| `bloqueos` | Relacion inversa con `BloqueoAgenda` |
| `turnos_asignados` | Relacion inversa desde `Turno.profesional` |

El campo `rol` no participa de las clases de permiso. Sus usos observados son presentacion/filtro, seleccion hardcodeada de un colorista al crear bloqueos (`gestion/views.py:2906`) y creacion automatica de un perfil `administrador` para autores de contenido (`gestion/views.py:4682-4689`).

Las habilidades si intervienen parcialmente en la disponibilidad. `TurnoViewSet` infiere una habilidad a partir del nombre de la categoria del servicio y filtra horarios por `realiza_color` o `realiza_lavado` (`gestion/views.py:1005-1018`). `realiza_diagnostico` no se valida al crear diagnosticos: ese flujo solo comprueba `is_staff`.

No se encontro un modelo de tareas laborales asignables al personal. Las asignaciones operativas actuales se expresan principalmente mediante turnos, horarios, bloqueos y autoria de contenido. `AgendaCuidados` corresponde a cuidados del cliente, no a tareas del empleado.

### Esquema textual de relaciones

```text
Usuario (identidad y autenticacion)
|-- 0..1 Cliente [OneToOne, PK compartida, CASCADE]
|   |-- diagnosticos, rutinas, turnos, carrito, ordenes, contenido guardado
|
|-- 0..1 Personal [OneToOne opcional, related_name=perfil_profesional, SET_NULL]
|   |-- rol operativo actual: colorista | asistente | administrador
|   |-- skills actuales: diagnostico | lavado | color
|   |-- horarios, bloqueos, turnos asignados, contenido educativo
|
|-- groups [ManyToMany heredado, actualmente sin uso aplicativo]
|-- user_permissions [ManyToMany heredado, actualmente sin uso aplicativo]
|-- is_staff [hoy equivale de hecho a cliente vs staff/admin en gran parte del sistema]
|-- is_superuser [superusuario Django]

Turno.profesional ----------> Personal
DiagnosticoCapilar.profesional -> Usuario
FichaTecnica.profesional_autor -> Usuario
ContenidoEducativo.autor -----> Personal
```

Hay cuatro ejes independientes que hoy pueden quedar desincronizados: `Usuario.is_active`, `Cliente.activo`, `Personal.activo` y la presencia de los perfiles. Tambien hay dos tipos de referencia para quien realiza trabajo tecnico, unas hacia `Usuario` y otras hacia `Personal`.

## 2. CREACION DE USUARIOS

### Puntos de creacion y elevacion

| Origen | Flujo | Campos asignados | `is_staff` / `is_superuser` | Riesgo |
|---|---|---|---|---|
| Registro publico | `POST /api/usuarios/registro/` -> `RegistroSerializer` | Email, nombre, apellido, password y datos de `Cliente` | `create_user()` deja ambos en `False` | Bajo respecto de privilegios; crea cuenta y `Cliente` atomicamente |
| Registro publico, post guardado | `RegistroView` | Asigna `usuario.es_cliente = True` | No afecta flags | `es_cliente` no es campo: parece rol persistido, pero no lo es (`usuarios/views.py:80-81`) |
| API administrativa | `POST /api/gestion/admin/usuarios/` -> `UsuarioAdminSerializer` | Email, nombres, password opcional, `is_staff`, `is_active` | El payload puede establecer `is_staff`; no expone `is_superuser` | Todo usuario con `is_staff=True` puede crear o promover mas staff porque `IsAdminUser` solo comprueba `is_staff` |
| API administrativa, edicion | `PATCH/PUT /api/gestion/admin/usuarios/{id}/` | Incluye `is_staff` e `is_active` | Puede subir o bajar `is_staff` | No hay separacion entre administrar cuentas y administrar privilegios |
| Alta de Personal por API | `POST /api/gestion/personal/` -> `PersonalSerializer.create()` | Todos los campos de `Personal`, incluido `usuario` y skills | Si recibe `usuario`, fuerza `usuario.is_staff=True` | Critico: el ViewSet acepta cualquier autenticado, por lo que un cliente puede vincular un usuario y elevarlo a staff (`gestion/views.py:417-424`; `serializers.py:597-608`) |
| Alta de Personal desde frontend | `GestionPersonal.js` | Nombre, contacto, rol, estado y tres skills | No envia `usuario` | Crea personal sin cuenta; no eleva por esta UI, pero tampoco permite iniciar sesion con ese registro |
| Alta de Personal desde Django Admin | `PersonalAdmin` | Puede incluir un `usuario`, rol y skills | No ejecuta `PersonalSerializer.create()` y no ajusta `is_staff` | La misma vinculacion produce resultados distintos segun se haga por API o Django Admin |
| Django Admin | `UsuarioAdmin` / formulario de alta | Identidad, `is_staff`, `is_superuser`; en edicion tambien grupos y permisos | Asignacion manual | Correcto solo si el operador del Django Admin ya esta fuertemente controlado |
| CLI Django | `createsuperuser` -> `UsuarioManager.create_superuser()` | Email, nombres y password | Ambos en `True`, con validacion | Ruta esperada para superusuario; debe limitarse operacionalmente |
| Creacion de contenido por staff sin Personal | `ContenidoEducativoViewSet.perform_create()` | Crea `Personal` con rol `administrador` y datos del usuario | No modifica flags; requiere que ya sea staff | Genera perfiles operativos administrativos de forma lateral, sin skills ni revision |
| Script manual | `gestion/fix_personal_staff.py` | Recorre `Personal.usuario` | Fuerza `is_staff=True` | Eleva masivamente cualquier cuenta vinculada a Personal, sin distinguir empleado, profesional o admin |
| Tests | `gestion/tests/test_auditoria.py` | Crea usuario con `is_staff=True` | Staff explicito | Solo fixture; evidencia que staff se usa como admin |

No se encontraron signals de `Usuario` o `Cliente` que creen cuentas, perfiles o roles. `gestion.signals` se carga desde `GestionConfig.ready()`, pero sus receptores se concentran en auditoria, turnos, rutinas, promociones y notificaciones.

### Riesgos de escalada y consistencia

- `PersonalViewSet` mas `PersonalSerializer.create()` constituye una escalada directa desde cualquier cuenta autenticada a `is_staff=True`.
- Una vez que una cuenta obtiene `is_staff`, `IsAdminUser` le abre gestion de usuarios, configuracion, reportes, pagos, auditoria y otros endpoints sensibles.
- `UsuarioAdminSerializer` deja `is_staff` como campo de escritura y no separa el permiso para editar datos del permiso para asignar privilegios.
- El update generico de `PersonalSerializer` puede cambiar el usuario vinculado sin ejecutar la logica de `create()`; borrar o desvincular `Personal` tampoco revoca `is_staff`.
- Un `Personal` creado desde la UI no tiene necesariamente `Usuario`; un usuario staff no tiene necesariamente `Personal`.
- Una cuenta puede conservar `Cliente` al convertirse en staff, sin regla explicita para decidir su rol efectivo.
- `Personal.rol='administrador'` no garantiza permisos, e `is_staff=True` no garantiza que exista ese rol ni un perfil Personal.
- Los receptores notifican a `Usuario.objects.filter(is_staff=True)`, por lo que empleados y profesionales reciben notificaciones tratadas como administrativas (`gestion/signals.py:379` y `636`).

## 3. AUTENTICACION

### Login

Existen dos entradas para obtener JWT:

| Endpoint | Implementacion | Observacion |
|---|---|---|
| `POST /api/usuarios/login/` | `LoginView`, usada por React | Busca por email, ejecuta `check_password()` y llama `RefreshToken.for_user()` |
| `POST /api/token/` | `TokenObtainPairView` de SimpleJWT | Ruta estandar adicional; no es la usada por `Login.js` |

El login propio no llama `authenticate()` ni verifica `usuario.is_active` (`usuarios/views.py:88-108`). `RefreshToken.for_user()` tampoco realiza esa comprobacion por si mismo. Por eso una cuenta inactiva puede recibir tokens. La validacion posterior de un access token normalmente aplica la regla de usuario activo de SimpleJWT, pero el rechazo no esta expresado en esta vista y depende de la configuracion/version de la libreria.

### JWT y refresh

- La autenticacion DRF global usa `JWTAuthentication` (`settings.py:125-141`).
- Access token: 7 dias.
- Refresh token: 30 dias.
- No hay rotacion de refresh tokens.
- `BLACKLIST_AFTER_ROTATION=False`; la blacklist se usa solo si se invoca logout.
- `POST /api/token/refresh/` esta publicado, pero no se encontraron llamadas desde React.
- El interceptor frontend, ante un `401`, elimina ambos tokens y redirige al login; no intenta refresh (`frontend/src/api/axiosConfig.js:27-40`).
- Los tokens se almacenan en `localStorage`, por lo que cualquier XSS podria leerlos.

### Perfil y determinacion del tipo de usuario

Despues del login, React consulta `GET /api/usuarios/perfil/`. La respuesta incluye `is_staff`, pero no incluye `is_superuser`, grupos, permisos, rol de `Personal`, skills ni un rol de negocio explicito (`usuarios/serializers.py:38-45`).

El tipo de usuario se decide actualmente de forma no uniforme:

| Mecanismo | Interpretacion actual |
|---|---|
| `user.is_staff` | Staff, profesional o administrador, segun el archivo |
| `user.is_superuser` | Administrador total, solo comprobado expresamente en fichas y contenido |
| `hasattr(user, 'cliente')` | Cliente |
| `user.perfil_profesional` | Profesional en contenido educativo |
| `hasattr(user, 'personal')` o `hasattr(user, 'profesional')` | Intento de detectar profesional en turnos, pero esos nombres no coinciden con `related_name='perfil_profesional'` |
| `Personal.rol` | Funcion operativa, no autorizacion |

La clasificacion efectiva del frontend es binaria: `is_staff ? Administrador : Cliente`.

### Logout

`POST /api/usuarios/logout/` requiere autenticacion y agrega el refresh token recibido a la blacklist. La app `token_blacklist` esta instalada. Sin embargo, los botones de logout del frontend solo borran `localStorage`; no invocan el endpoint. Por tanto, el refresh token sigue siendo valido en servidor hasta vencer si fue copiado antes del logout.

### Recuperacion de contraseña

- Solicitud y confirmacion son publicas.
- La solicitud usa `default_token_generator` y responde de forma generica si el email no existe.
- La confirmacion valida UID/token y actualiza mediante `set_password()`.
- No se observo throttling especifico.
- No se filtra por rol, lo cual es correcto: la recuperacion debe depender de la identidad, no del rol.
- Debe definirse expresamente si una cuenta inactiva puede solicitar/cambiar contraseña y si eso debe reactivarla. Hoy cambiar la contraseña no modifica `is_active`.

## 4. AUTORIZACION BACKEND

### Semantica global

`DEFAULT_PERMISSION_CLASSES` contiene `AllowAny` e `IsAuthenticated`. DRF exige que todas las clases listadas concedan acceso, por lo que la combinacion equivale en la practica a requerir autenticacion. `AllowAny` no vuelve publico un endpoint mientras `IsAuthenticated` este en la misma lista.

Las vistas que declaran `permission_classes` reemplazan ese valor global. No se encontraron clases de permiso personalizadas, uso de `DjangoModelPermissions`, `DjangoObjectPermissions`, `has_perm()`, Groups o permisos Django en la API.

`IsAdminUser` no significa superusuario ni rol ADMINISTRADOR: concede acceso a cualquier usuario autenticado con `is_staff=True`.

### Tabla de accesos actuales

| Archivo / Endpoint | Permiso actual | Que usuario puede acceder | Riesgo |
|---|---|---|---|
| `usuarios/views.py` - registro | `AllowAny` | Cualquiera | Esperado para alta de clientes; depende de que el serializer nunca acepte flags privilegiados |
| `usuarios/views.py` - login | `AllowAny` | Cualquiera con credenciales | No comprueba `is_active` |
| `bohemiacore/urls.py` - token y refresh | Vistas SimpleJWT | Publico con credenciales/token | Segundo flujo de login; politica de usuario activo no centralizada |
| `usuarios/views.py` - perfil | `IsAuthenticated` | Cualquier autenticado, sobre si mismo | El update asume que existe `Cliente`; un staff sin Cliente puede fallar |
| `usuarios/views.py` - logout | `IsAuthenticated` | Cualquier autenticado | El frontend no lo invoca |
| `usuarios/views.py` - password reset | `AllowAny` | Cualquiera | Sin throttling especifico |
| `usuarios/views.py` - diagnostico propio | `IsAuthenticated` | Usuario con `Cliente` | Alcance propio correcto |
| `usuarios/views.py` - `/clientes/` | `IsAdminUser` | Cualquier `is_staff` | Expone datos de clientes a todo empleado marcado staff |
| `gestion/views.py` - `/admin/usuarios/` | `IsAdminUser` | Cualquier `is_staff` | Un empleado puede crear/promover staff y administrar estados de cuenta |
| Configuracion y configuracion de diagnostico | `IsAdminUser`; accion `publica` es `AllowAny` | Staff para CRUD; publico para nombre de empresa | Todo staff puede cambiar parametros globales |
| Catalogos capilares y categoria de servicio | `AllowAny` sobre `ModelViewSet` | Anonimos, incluido CRUD | Escritura y borrado anonimos de datos maestros |
| Servicios | `AllowAny` en definicion duplicada; la clase efectiva usa `get_permissions()` | Lectura publica; escritura `is_staff` | Dependencia fragil de una clase duplicada; todo staff administra servicios/precios |
| Servicios quimicos y disponibilidad | `AllowAny` | Anonimos, lectura | Razonable si los datos se consideran catalogo publico |
| Personal | `IsAuthenticated` sobre CRUD completo | Cualquier cuenta autenticada | Critico: lectura, alta, edicion y baja de personal; alta puede elevar `is_staff` |
| Turnos, listado | `IsAuthenticated` + filtro manual | Staff ve todos; Cliente ve propios | Staff no se segmenta por rol; la consulta dispara cambios al auto-cancelar |
| Turnos, create/update/destroy | `IsAuthenticated` + controles parciales | Staff opera cualquier turno; Cliente el propio | Cliente puede enviar campos operativos como estado/profesional en update y puede eliminar su turno por CRUD generico |
| Turnos, `registrar_pago` | `IsAuthenticated` + chequeo `is_staff` | Todo staff | No hay permiso especifico de caja |
| Turnos, reprogramar/cancelar | `IsAuthenticated` + ownership o `is_staff` | Cliente propio; staff global | Algunas ramas usan relaciones inexistentes `personal`/`profesional`; permisos y reglas varian por accion |
| Turnos, `finalizar_turno` | Solo permiso base `IsAuthenticated` | Staff sobre cualquiera; Cliente sobre su propio turno por el queryset | Critico: el cliente puede marcar su servicio como realizado y disparar automatizaciones |
| Agenda general | `IsAuthenticated` | Cualquier autenticado | Expone horarios y bloqueos generales a clientes |
| Crear bloqueo | `IsAuthenticated` | Cualquier autenticado | Critico: un cliente puede bloquear agenda |
| Horarios laborales | `IsAdminUser` | Cualquier staff | Empleado y profesional administran horarios globales |
| Tipo de equipamiento | `IsAuthenticated` sobre CRUD | Cualquier autenticado | Cliente puede alterar tipos de equipamiento |
| Equipamiento | Permisos globales efectivos | Cualquier autenticado | Cliente puede crear, editar o desactivar equipamiento |
| Dashboard y stats | `IsAdminUser` | Cualquier staff | Datos globales disponibles a todos los empleados/profesionales staff |
| Rutinas catalogo | Lectura `IsAuthenticated`; escritura `IsAdminUser` | Autenticados leen; staff escribe | Todo staff administra plantillas y ve usuarios que las usan |
| Rutinas de cliente | `IsAuthenticated` con filtro por dueño; varias acciones manuales | Cliente propio; staff todas | En general acotado, pero usa staff como bypass universal |
| Reglas de diagnostico | `IsAdminUser` | Cualquier staff | Todo staff modifica el motor experto |
| Fichas tecnicas | `IsAuthenticated` + `IsAdminUser` | Cualquier staff | `is_superuser` ve todas; staff solo las propias, pero no se comprueba skill ni asignacion al turno |
| Requisitos de servicio | `IsAuthenticated` + `IsAdminUser` | Cualquier staff | Todo staff modifica requisitos tecnicos/equipamiento |
| Diagnosticos capilares | `IsAuthenticated`; escritura chequea `is_staff` | Cliente ve queryset propio; staff ve/escribe todo | `por_cliente` consulta por ID sin validar ownership; cliente podria pedir diagnosticos de otro cliente |
| Categorias de producto | `AllowAny` sobre CRUD completo | Anonimos | Escritura y borrado anonimos |
| Productos e imagenes | Lectura `AllowAny`; escritura `IsAdminUser` | Publico lee; staff escribe | `stock_bajo` es publico y expone informacion operativa |
| Promociones | Lectura `AllowAny`; escritura `IsAdminUser` | Publico lee; staff escribe | Todo staff administra precios/promociones |
| Carrito | `IsAuthenticated` + perfil Cliente | Cliente sobre su carrito | Alcance propio adecuado; rol se infiere por perfil |
| Contenido educativo | `IsAuthenticated` + comprobaciones manuales | Clientes leen publicados; Personal o staff crea; staff edita cualquier contenido | Staff sin perfil provoca creacion lateral de `Personal(administrador)`; cualquier autenticado que obtenga un contenido por el queryset puede ejecutar el soft delete porque `perform_destroy` no valida autoria/rol |
| Likes y guardados | `IsAuthenticated` + perfil Cliente | Cliente sobre sus datos | Alcance propio adecuado |
| Ordenes pendientes | `IsAuthenticated` + queryset propio/global | Cliente ve propias; staff todas | Acciones `confirmar_pago`, `confirmar_entrega` y `cancelar` no exigen staff; cliente puede mutar su orden/stock |
| Ordenes de compra | `IsAuthenticated` + queryset propio/global | Cliente ve propias; staff todas | `confirmar_entrega` y `cancelar` no exigen staff; `registrar_pago` si comprueba staff |
| Pagos/caja | `IsAdminUser` | Cualquier staff | No separa caja de otros empleados |
| Auditoria e historial/reversion | `IsAdminUser` | Cualquier staff | Cualquier empleado staff puede ver auditoria y ejecutar reversiones permitidas |
| Upload de imagen | `IsAdminUser` | Cualquier staff | Permiso amplio, sin capacidad especifica de contenido |

### Problemas estructurales

- El rol binario `staff/no staff` no representa cuatro roles de negocio.
- La autorizacion esta distribuida entre clases DRF, querysets, serializers y `if request.user.is_staff`.
- No hay una politica unica para ownership, acciones sobre objetos asignados o skills.
- Un booleano tecnico de Django concede acceso transversal a modulos sin relacion entre si.
- El mismo actor es llamado admin, profesional o staff segun el archivo.
- Los campos y relaciones incorrectos `personal`/`profesional` hacen que algunas ramas de deteccion profesional no funcionen como se documentan.
- Los permisos de modelo que Django ya provee existen en base, pero no gobiernan la API.

## 5. AUTORIZACION FRONTEND

### Enrutamiento

`ProtectedRoute` solo comprueba si existe `access_token` en `localStorage` (`frontend/src/routes/ProtectedRoute.js:4-11`). No valida vigencia, rol ni permiso. Todas las rutas de cliente y todas las rutas administrativas usan exactamente ese mismo guard (`frontend/src/routes/index.js:76-123`).

Consecuencias:

- Cualquier usuario con un token puede navegar manualmente a cualquier pagina `/admin/*`.
- La seguridad real queda en el backend, lo cual es obligatorio, pero varios endpoints backend solo requieren autenticacion.
- No existe un guard de ruta para `CLIENTE`, `EMPLEADO`, `PROFESIONAL` o `ADMINISTRADOR`.
- Tampoco existe un estado explicito de “autenticando/cargando permisos”; la presencia del token se considera suficiente.

### Login, menus y estado de usuario

- `Login.js` obtiene el perfil y redirige por `usuario.is_staff`: staff a `/admin-dashboard`, resto a `/perfil`.
- `Header.js` repite la misma decision binaria para mostrar `adminLinks` o `clientLinks`.
- El badge muestra solo “Administrador” o “Cliente”, incluso si el registro es empleado o profesional.
- `CampanaNotificaciones.js` lee `user_info.is_staff` desde `localStorage` para elegir destinos administrativos o de cliente.
- `user_info` es una copia manipulable y potencialmente desactualizada; sirve para UX, nunca debe autorizar acciones.
- El perfil devuelto por backend no expone permisos ni skills.

### Rutas y controles administrativos

El dashboard muestra accesos a rutinas, clientes, usuarios, personal, servicios, productos, equipamiento, reglas, agenda, configuracion, ordenes y auditoria sin filtrar por permiso individual. Las paginas administrativas muestran botones de alta, edicion, baja, confirmacion y pagos en funcion de la pagina cargada, no de capacidades del usuario.

Algunas paginas reaccionan a un `403` despues de intentar la llamada, por ejemplo dashboard, auditoria, clientes, usuarios y equipamiento. Esto es manejo de error, no autorizacion preventiva.

`GestionUsuarios.js` mantiene la clasificacion cliente/staff, permite enviar `is_staff` mediante un checkbox y declara que marcarlo concede acceso al panel. `GestionPersonal.js` administra `Personal.rol` y skills, pero no vincula una cuenta de usuario en su formulario.

### Conclusion frontend

Actualmente el frontend decide que mostrar con `is_staff`, no con roles o permisos. La transicion necesita un contexto de identidad unico que consuma un contrato del backend con rol, permisos efectivos, perfil Personal y skills. Ocultar rutas/botones mejora UX, pero toda decision debe repetirse y hacerse cumplir en backend.

## 6. PERSONAL Y ROLES

### Evaluacion del campo actual

`Personal.rol` mezcla tres conceptos:

| Valor | Concepto real |
|---|---|
| `colorista` | Especialidad o puesto operativo |
| `asistente` | Puesto o nivel operativo |
| `administrador` | Rol de autorizacion |

Por esa mezcla, el campo no debe convertirse en la fuente de los nuevos roles. Tampoco puede representar `CLIENTE`, porque solo existe en `Personal`, ni es fiable para autorizar porque `Personal.usuario` es opcional.

### Recomendacion para `Personal.rol`

No reutilizarlo como rol de seguridad. Durante la transicion debe conservarse porque contiene datos existentes y se usa en UI/filtros. Su destino recomendado es uno de estos:

1. Renombrarlo conceptualmente a `puesto` o `especialidad_principal`, con valores exclusivamente operativos.
2. Reemplazarlo de forma posterior por un catalogo de puestos si aparecen mas especialidades.
3. Eliminar el valor `administrador` una vez que el rol ADMINISTRADOR viva en Groups y los registros hayan sido revisados.

No se recomienda eliminarlo en la primera migracion.

### Skills actuales

Los tres booleanos son utiles como punto de partida, pero escalan mal: cada habilidad nueva exige columna, migracion, serializer, formulario y cambios de logica. Ademas, la asociacion servicio-habilidad se infiere hoy por texto de categoria.

Modelo futuro sugerido:

```text
Habilidad
- codigo unico: DIAGNOSTICO, LAVADO, SECADO, COLOR, TRATAMIENTO, CORTE, etc.
- nombre
- activa

Personal.habilidades <ManyToMany> Habilidad

Servicio.habilidades_requeridas <ManyToMany> Habilidad
```

Si se necesitan certificaciones, vencimientos o niveles, la relacion puede usar un modelo intermedio `PersonalHabilidad`. No hace falta introducirlo hasta que exista ese requerimiento.

## 7. PROPUESTA DE MODELO FUTURO

### Alternativas

| Alternativa | Simplicidad | Seguridad | Mantenibilidad | Impacto actual | Migracion |
|---|---|---|---|---|---|
| A. Campo `rol` en `Usuario` | Alta al inicio | Media; tiende a acumular `if rol == ...` y permisos gruesos | Media-baja al crecer acciones | Moderado; reemplaza muchos `is_staff` por otro switch | Facil para un rol unico, dificil para excepciones por empleado |
| B. Django Groups + Permissions | Media | Alta si todos los endpoints usan `has_perm` y ownership | Alta; tecnologia nativa, auditable y administrable | Moderado-alto | Buena; grupos pueden cargarse sin cambiar comportamiento al principio |
| C. Groups + Permissions + `Personal.skills` | Media | Alta; separa acceso de competencia operativa | Alta; roles son bundles y skills evolucionan independientemente | Alto pero incremental | La mejor para este dominio; preserva `Personal` y permite migrar skills gradualmente |
| D. Tablas RBAC propias o motor de politicas | Baja | Potencialmente muy alta | Baja para el tamano actual por complejidad adicional | Muy alto | No justificado salvo multi-sucursal, roles temporales, delegacion compleja o politicas externas |

### Opcion recomendada

**Opcion C: Django Groups + Permissions + skills en Personal.**

Los cuatro grupos de negocio serian:

- `CLIENTE`
- `EMPLEADO`
- `PROFESIONAL`
- `ADMINISTRADOR`

Cada usuario debe pertenecer a exactamente uno de esos grupos de rol. Django puede seguir teniendo otros grupos tecnicos en el futuro, pero solo uno debe pertenecer al conjunto de roles de negocio. Esa invariante debe controlarse en un servicio de asignacion de roles y en tests, no mediante escritura libre de `groups` desde serializers.

### Responsabilidad de cada capa

| Capa | Responsabilidad |
|---|---|
| `Usuario` | Identidad, credenciales, estado activo y pertenencia al grupo de rol |
| Group de negocio | Paquete base de permisos para CLIENTE, EMPLEADO, PROFESIONAL o ADMINISTRADOR |
| Permission Django | Accion autorizable, por ejemplo `gestion.confirmar_sena` o `usuarios.asignar_roles` |
| `Cliente` | Perfil y datos propios del cliente; no es la fuente unica de autorizacion |
| `Personal` | Perfil laboral, estado operativo, horarios y habilidades |
| Skill | Competencia tecnica para ser asignado o ejecutar una tarea del salon |
| Regla de objeto | Ownership o asignacion: propio cliente, propio turno, turno asignado al Personal, etc. |

### Semantica futura de flags Django

- `is_active`: unica bandera de habilitacion de la cuenta. Un `Personal.activo=False` impide asignacion/operacion laboral, pero no reemplaza la desactivacion de cuenta.
- `is_staff`: reservado a acceso al sitio `/admin/` de Django. No representa EMPLEADO, PROFESIONAL ni ADMINISTRADOR de la SPA.
- `is_superuser`: cuenta excepcional de emergencia, no rol cotidiano. No debe aparecer como opcion en la API de negocio.
- `IsAdminUser`: debe ser reemplazado gradualmente en la API porque solo lee `is_staff`.

Un ADMINISTRADOR de negocio no necesita necesariamente `is_staff` si solo usa la SPA. Si tambien debe entrar al Django Admin, se le otorga `is_staff` de forma separada y controlada.

### Permisos de negocio sugeridos

Los permisos deben expresar acciones, no pantallas. Primera taxonomia posible:

| Dominio | Permisos ejemplo |
|---|---|
| Usuarios | `view_users`, `manage_users`, `assign_roles`, `deactivate_users` |
| Personal | `view_personal`, `manage_personal`, `manage_skills`, `manage_schedules` |
| Turnos | `view_global_agenda`, `create_turno_for_client`, `reprogram_any_turno`, `cancel_any_turno`, `confirm_deposit`, `finalize_service` |
| Tecnico | `create_diagnosis`, `manage_technical_record`, `manage_formulas`, `assign_routines` |
| Catalogos | `manage_services`, `manage_products`, `manage_stock`, `manage_prices`, `manage_promotions`, `manage_content` |
| Finanzas | `register_payments`, `view_cash`, `manage_orders` |
| Gobierno | `view_reports`, `view_audit`, `revert_audit`, `manage_configuration` |

Los nombres concretos deben acordarse antes de migrar. Los permisos CRUD generados por Django pueden reutilizarse donde sean suficientes; las transiciones de negocio requieren permisos personalizados.

### Evaluacion de acceso

Una accion sensible deberia autorizarse por la conjuncion:

```text
cuenta autenticada y activa
+ permiso de negocio
+ alcance sobre el objeto
+ Personal activo, cuando la accion es laboral
+ skill requerida, cuando la accion es tecnica
+ asignacion al turno, cuando corresponde
```

El rol aporta permisos predeterminados. Una skill nunca debe conceder acceso por si sola.

## 8. DIFERENCIA ENTRE ROL Y HABILIDAD

### Rol

El rol define que partes y acciones del sistema puede usar una persona. Se implementa mediante un Group de negocio y sus Permissions.

Ejemplos:

- EMPLEADO puede tener permiso para ver agenda y registrar una seña.
- PROFESIONAL puede tener permiso para completar ficha tecnica y finalizar servicios asignados.
- ADMINISTRADOR puede administrar usuarios, precios, reportes y configuracion.

### Habilidad

La habilidad define que trabajo tecnico puede ejecutar el Personal. No concede acceso administrativo.

```text
Usuario
  rol = EMPLEADO

Personal
  habilidades = LAVADO, SECADO, TRATAMIENTO
```

Ese empleado podria ser asignado a servicios que requieran esas habilidades si tambien tiene el permiso operativo pertinente. No podria administrar usuarios o precios por saber realizar un tratamiento.

### Efecto sobre turnos y asignacion

- Cada Servicio debe declarar las habilidades requeridas de forma estructurada, no por coincidencias de texto en la categoria.
- La disponibilidad solo debe ofrecer Personal activo cuyo horario cubra el turno y cuyas habilidades cubran todas las requeridas.
- Registrar un turno para un cliente requiere permiso de agenda; no requiere necesariamente ejecutar el servicio.
- Finalizar el servicio requiere permiso, asignacion al turno y las habilidades correspondientes, salvo una accion administrativa de correccion separada y auditada.
- Crear diagnostico requiere permiso `create_diagnosis` y skill `DIAGNOSTICO`.
- Registrar una formula requiere permiso `manage_formulas`, skill apropiada y relacion con el turno.
- Cambiar skills debe ser una accion administrativa auditable; el Personal no debe autoasignarselas.
- El historial debe registrar al `Personal` que ejecuto la tarea, no solo a un `Usuario` generico.

## 9. MATRIZ DE PERMISOS PROPUESTA

Leyenda: `PROPIO` limita al objeto del cliente; `ASIGNADO` limita al trabajo asignado al Personal; `SEGUN PERMISO` exige un permiso especifico adicional; `SKILL` exige capacidad operativa.

| Accion / modulo | Cliente | Empleado | Profesional | Admin |
|---|---|---|---|---|
| Perfil propio | Si, lectura/edicion | Si, lectura/edicion | Si, lectura/edicion | Si, lectura/edicion |
| Diagnostico | PROPIO, lectura | SEGUN PERMISO + SKILL | SEGUN PERMISO + SKILL | Si; correccion auditada |
| Rutinas | PROPIO y catalogo | SEGUN PERMISO | SEGUN PERMISO | Si |
| Turnos propios | Si | Si, si posee perfil Cliente | Si, si posee perfil Cliente | Si, si posee perfil Cliente |
| Registrar turno para cliente | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Ver agenda global | No; solo disponibilidad publica | SEGUN PERMISO | SEGUN PERMISO | Si |
| Reprogramar turno propio | PROPIO, segun reglas | PROPIO o SEGUN PERMISO para terceros | PROPIO o SEGUN PERMISO para ASIGNADO | Si |
| Cancelar turno propio | PROPIO, segun reglas | PROPIO o SEGUN PERMISO para terceros | PROPIO o SEGUN PERMISO para ASIGNADO | Si |
| Confirmar seña | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Finalizar servicio | No | SEGUN PERMISO + ASIGNADO + SKILL | SEGUN PERMISO + ASIGNADO + SKILL | Si, como override administrativo auditado |
| Ficha tecnica | Lectura futura solo si negocio lo aprueba | SEGUN PERMISO + ASIGNADO + SKILL | SEGUN PERMISO + ASIGNADO + SKILL | Si |
| Formulas | No | SEGUN PERMISO + ASIGNADO + SKILL | SEGUN PERMISO + ASIGNADO + SKILL | Si |
| Ver productos | Si | Si | Si | Si |
| Gestionar productos | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Gestionar stock | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Gestionar precios | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Registrar/ver pagos | PROPIO, solo comprobantes/estado | SEGUN PERMISO | SEGUN PERMISO | Si |
| Gestionar promociones | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Ver contenido publicado | Si | Si | Si | Si |
| Crear/editar contenido | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Gestionar personal y skills | No | No | No | Si |
| Gestionar usuarios | No | No | No | Si |
| Asignar roles/permisos | No | No | No | SEGUN PERMISO; restringido incluso dentro de Admin |
| Reportes | No | SEGUN PERMISO | SEGUN PERMISO | Si |
| Auditoria | No | No | SEGUN PERMISO, solo lectura si se justifica | Si |
| Revertir auditoria | No | No | No | SEGUN PERMISO |
| Configuracion global | No | No | No | Si |

La matriz es una base de discusion. Antes de codificar debe resolverse si EMPLEADO puede operar caja/stock, si PROFESIONAL puede cambiar precios y si ADMINISTRADOR puede ejecutar acciones tecnicas sin un `Personal` asociado. La recomendacion por defecto es minimo privilegio.

## 10. PLAN DE MIGRACION

### Paso 0. Congelar la semantica

Definir y aprobar nombres de roles, permisos y reglas de objeto. Resolver las decisiones abiertas de la matriz antes de crear migraciones.

### Paso 1. Crear tests de caracterizacion y seguridad

Capturar el login y los accesos actuales sin cambiar comportamiento. Agregar primero tests que demuestren las escaladas de `PersonalViewSet`, mutacion de `is_staff`, acciones de turnos y ordenes. Estos tests fijan la linea base y evitan una transicion a ciegas.

### Paso 2. Contener las rutas de escalada actuales

Como cambio P0 posterior a este analisis, restringir la administracion de Personal y hacer no escribible `is_staff` fuera de una operacion exclusiva de asignacion de roles. Debe hacerse con tests y sin tocar aun los roles de usuarios existentes.

### Paso 3. Inventariar cuentas reales

Generar un reporte de solo lectura con estas categorias:

| Estado encontrado | Tratamiento propuesto |
|---|---|
| `Cliente`, no staff, sin Personal | Candidato automatico a CLIENTE |
| `Personal.rol=colorista` vinculado | Candidato a PROFESIONAL |
| `Personal.rol=asistente` vinculado | Candidato a EMPLEADO |
| `is_superuser=True` | Candidato a ADMINISTRADOR y cuenta de emergencia segun uso real |
| `Personal.rol=administrador` | Revision manual antes de ADMINISTRADOR |
| `is_staff=True` sin Personal | Revision manual; no asumir ADMINISTRADOR |
| Usuario con Cliente y Personal | Conservar ambos perfiles; elegir un unico rol laboral manualmente |
| Personal sin Usuario | Conservar; no asignar rol hasta crear/vincular cuenta |
| Usuario sin Cliente ni Personal | Revision manual; no elevar privilegios |

No debe inferirse ADMINISTRADOR solamente desde `is_staff`, porque hoy ese flag incluye a personal tecnico.

### Paso 4. Crear Groups y Permissions sin activarlos

Crear de forma idempotente los cuatro Groups y los permisos acordados mediante una migracion de datos versionada. Este paso no cambia todavia `permission_classes`, `is_staff` ni el frontend.

### Paso 5. Backfill conservador de roles

Asignar automaticamente solo casos inequívocos. Los ambiguos quedan en una lista de revision y conservan temporalmente su acceso actual. La operacion debe ser repetible, auditable y tener conteos antes/despues.

No modificar masivamente `is_staff` en este paso. Eso evita romper Django Admin y rutas que todavia dependan de `IsAdminUser`.

### Paso 6. Exponer identidad efectiva

Extender el contrato de perfil o crear `/api/usuarios/me/` para devolver:

```json
{
  "id": 1,
  "email": "...",
  "role": "PROFESIONAL",
  "permissions": ["gestion.view_global_agenda", "gestion.finalize_service"],
  "personal_id": 4,
  "skills": ["COLOR", "DIAGNOSTICO"]
}
```

El backend calcula esa respuesta. El frontend no deriva el rol desde `is_staff` ni confia en claims editables de `localStorage`.

### Paso 7. Introducir permisos en modo sombra

Crear helpers/clases de permiso y comparar en logs el resultado nuevo contra el acceso actual, sin denegar todavia por el modelo nuevo. Revisar diferencias sobre cuentas reales antes del corte.

### Paso 8. Migrar backend por modulos

Orden recomendado:

1. Usuarios, asignacion de roles y Personal.
2. Turnos, agenda, señas, finalizacion y fichas.
3. Ordenes, pagos, stock y precios.
4. Contenido, rutinas y diagnosticos.
5. Reportes, auditoria y configuracion.

Cada endpoint debe combinar permiso de accion, alcance del objeto y skill cuando corresponda. Retirar el fallback antiguo solo cuando el modulo tenga tests y usuarios clasificados.

### Paso 9. Migrar frontend

Incorporar un contexto de autenticacion con `role`, `permissions` y `skills`; crear guardas de ruta por permiso; construir menus y botones desde permisos. Mantener el backend como autoridad final.

### Paso 10. Migrar skills

Crear catalogo `Habilidad` y relaciones. Copiar los booleanos actuales a habilidades equivalentes, comparar resultados de disponibilidad y luego cambiar la asignacion de turnos. Los booleanos se eliminan solo en una migracion posterior y separada.

### Paso 11. Desacoplar `is_staff`

Cuando ningun endpoint de negocio dependa de `IsAdminUser` o `is_staff`, dejar `is_staff=True` solo a quienes necesiten Django Admin. Recalcular destinatarios de notificaciones por permiso/rol, no por staff.

### Paso 12. Retirar compatibilidad

Eliminar filtros cliente/staff, checkbox de `is_staff`, scripts de elevacion y ramas obsoletas. Convertir `Personal.rol` a puesto/especialidad o retirarlo despues de validar datos. Documentar una unica via para crear cuentas laborales y asignar roles.

## 11. ARCHIVOS QUE HABRIA QUE MODIFICAR

No se modifica ninguno como parte de este analisis.

### Modelos y administracion

| Archivo probable | Motivo futuro |
|---|---|
| `bohemiacore/usuarios/models.py` | Invariantes/servicios de rol si se ubican en la app de identidad; no se recomienda agregar un segundo rol canonico |
| `bohemiacore/usuarios/admin.py` | Administrar rol/grupo sin exponer flags peligrosos; separar acceso Django Admin |
| `bohemiacore/gestion/models.py` | Catalogo de habilidades, relacion con Personal/Servicio y eventual conversion de `Personal.rol` |
| `bohemiacore/gestion/admin.py` | Gestion de puestos, habilidades y asignaciones |

### Serializers

| Archivo probable | Motivo futuro |
|---|---|
| `bohemiacore/usuarios/serializers.py` | Contrato `/me`, rol/permisos efectivos y registro siempre CLIENTE |
| `bohemiacore/gestion/serializers.py` | Retirar escritura directa de `is_staff`; validar Personal, skills, turnos y acciones tecnicas |
| `bohemiacore/gestion/serializers_auditoria.py` | Mostrar cambios de rol/permisos si se incorporan a auditoria |

### Views y servicios

| Archivo probable | Motivo futuro |
|---|---|
| `bohemiacore/usuarios/views.py` | Login activo, endpoint de identidad, asignacion segura de roles y logout coherente |
| `bohemiacore/usuarios/urls.py` | Nueva ruta `/me` o endpoints administrativos de roles |
| `bohemiacore/gestion/views.py` | Reemplazar chequeos `is_staff`, aplicar ownership, permisos y skills por accion |
| `bohemiacore/gestion/views_auditoria.py` | Permisos separados de lectura y reversion |
| `bohemiacore/gestion/stats_views.py` | Permiso especifico de reportes |
| `bohemiacore/gestion/services.py` | Elegibilidad de Personal por permisos, asignacion y skills |
| `bohemiacore/gestion/signals.py` | Destinatarios por rol/permiso, no por `is_staff` |
| `bohemiacore/usuarios/filters.py` | Filtros por rol real en vez de staff |
| `bohemiacore/gestion/filters.py` | Filtros de Personal/skills y eliminacion de semantica staff |
| `bohemiacore/bohemiacore/settings.py` | Simplificar permiso DRF por defecto y configurar politica JWT coherente |
| `bohemiacore/bohemiacore/urls.py` | Consolidar la entrada de login/token si se decide una sola |

### Permissions

Archivos nuevos probables, a definir durante implementacion:

- `bohemiacore/usuarios/permissions.py`: cuenta activa, rol y administracion de usuarios.
- `bohemiacore/gestion/permissions.py`: permiso por accion, ownership, Personal activo, asignacion y skill.
- Alternativamente un unico modulo `core/permissions.py` si se crea una app transversal. No conviene duplicar helpers entre apps.

### Frontend

| Archivo probable | Motivo futuro |
|---|---|
| `frontend/src/routes/ProtectedRoute.js` | Guard de autenticacion y permisos |
| `frontend/src/routes/index.js` | Declarar permisos por ruta |
| `frontend/src/routes/routes.js` | Separar rutas operativas de administrativas si mejora la navegacion |
| `frontend/src/pages/auth/Login.js` | Redireccion por rol/capacidad y contrato `/me` |
| `frontend/src/components/Header.js` | Menu por permisos y etiqueta de rol real |
| `frontend/src/components/CampanaNotificaciones.js` | Destinos por permisos, no por copia de `is_staff` |
| `frontend/src/pages/admin/GestionUsuarios.js` | Sustituir checkbox staff por asignacion controlada de rol |
| `frontend/src/pages/admin/GestionPersonal.js` | Vincular cuenta, puesto y skills sin elevar privilegios implicitamente |
| `frontend/src/pages/admin/DashboardAdmin.js` | Mostrar accesos segun permisos |
| `frontend/src/api/axiosConfig.js` | Refresh/logout y carga coherente de sesion |
| `frontend/src/auth/AuthContext.js` o equivalente nuevo | Fuente unica de identidad y permisos en React |

Tambien se revisarian todas las paginas administrativas que ejecutan acciones sensibles para ocultar o deshabilitar controles segun permiso.

### Migraciones

- Migracion de datos idempotente para Groups y Permissions.
- Migracion de backfill de roles solo para casos inequívocos.
- Migraciones separadas para `Habilidad`, relaciones y copia de booleanos.
- Migracion posterior, no inicial, para retirar booleanos o reconvertir `Personal.rol`.

### Tests

- Nuevos tests de permisos por rol y accion en `usuarios/tests/` y `gestion/tests/`.
- Ampliacion de `gestion/tests/test_auditoria.py` para permisos de consulta/reversion.
- Tests frontend de guardas, menus y botones.
- Cypress con cuentas por rol sin credenciales versionadas.

## 12. RIESGOS

| Riesgo | Escenario | Mitigacion |
|---|---|---|
| Romper autenticacion | Cambiar login/JWT junto con roles impide iniciar sesion | Mantener credenciales y tokens independientes del rol; migrar autorizacion por etapas |
| Romper rutas admin | Quitar `is_staff` antes de reemplazar `IsAdminUser` produce 403 a operadores validos | No tocar `is_staff` hasta migrar y probar cada modulo |
| Escalada de privilegios | Serializer, endpoint o frontend permite asignar Group ADMINISTRADOR | Unico servicio de asignacion, permiso `assign_roles`, auditoria y campos read-only |
| Clientes convertidos en staff | Inferir rol desde perfiles ambiguos o ejecutar scripts masivos | Backfill conservador; nunca derivar admin solo desde `is_staff` o `Personal` |
| Usuarios existentes sin rol | Cuentas huerfanas o ambiguas quedan sin Group | Reporte previo, grupo no privilegiado temporal o cola de revision; nunca fallback a Admin |
| Inconsistencia Usuario/Personal | Group laboral sin Personal o Personal sin usuario | Validacion al asignar EMPLEADO/PROFESIONAL; permitir Personal sin cuenta, pero sin autorizacion digital |
| Usuario con Cliente y Personal | Dos perfiles se interpretan como dos roles | Un rol de negocio canonico; perfiles expresan relaciones de dominio, no roles simultaneos |
| Duplicar fuente de verdad | Campo `Usuario.rol` y Groups divergen | Elegir Groups como canonico; no agregar campo redundante |
| Permisos demasiado amplios | Reutilizar permisos CRUD para transiciones sensibles | Permisos personalizados por accion y reglas de objeto |
| Skills usadas como permisos | Una habilidad tecnica abre modulos administrativos | Exigir permiso y skill; nunca skill sola |
| Revocacion incompleta | Cambiar rol deja token/UI con estado viejo | Backend consulta permisos actuales; invalidar cache/sesion y refrescar `/me` tras cambios |
| `is_superuser` cotidiano | Operadores trabajan con bypass total | Cuenta de emergencia separada; administradores normales por Group |
| Migraciones irreversibles | Backfill elimina o sobrescribe datos de Personal | Migraciones aditivas, reportes de conteo y retiro en fases separadas |
| Notificaciones incorrectas | Seguir enviando todo a `is_staff=True` | Seleccionar destinatarios por permiso/rol y probar no exposicion |
| Frontend como seguridad | Boton oculto se considera control suficiente | Backend siempre autoriza; frontend solo refleja capacidades |
| Acceso a objetos ajenos | Permiso de modulo sin ownership permite leer otro cliente/turno | Querysets acotados y permisos de objeto probados para cada accion |

## 13. TESTS NECESARIOS

### Autenticacion

| Test | Resultado esperado |
|---|---|
| Login CLIENTE | Token valido y `/me.role=CLIENTE` |
| Login EMPLEADO | Token valido, permisos base correctos y Personal asociado |
| Login PROFESIONAL | Token valido, permisos y skills correctos |
| Login ADMINISTRADOR | Token valido, permisos administrativos sin depender de `is_staff` |
| Login de usuario inactivo | Rechazo sin emitir access ni refresh |
| Refresh de usuario desactivado | Rechazo y no emision de nuevo access |
| Logout | Refresh token en blacklist; reutilizacion rechazada |
| Recuperacion de contraseña | Mismo resultado externo para email existente/inexistente; rol sin cambios |

### Roles y escalada

| Test | Resultado esperado |
|---|---|
| Registro publico envia `is_staff`, `is_superuser`, `groups` o `role` | Campos rechazados/ignorados; cuenta CLIENTE sin privilegios |
| Cliente crea o edita Personal | 403 |
| Cliente llama endpoint admin | 403 |
| Empleado sin `assign_roles` modifica rol | 403 |
| Profesional sin `assign_roles` modifica rol | 403 |
| Admin autorizado cambia rol | Exito, auditoria creada e invariantes conservadas |
| Admin intenta asignarse `is_superuser` por API | 403 o campo no disponible |
| Usuario pertenece a dos Groups de negocio | Operacion rechazada por invariante |
| Cambio de rol conserva password, Cliente y Personal | Sin perdida de identidad ni perfiles |

### Permisos operativos

| Test | Resultado esperado |
|---|---|
| Empleado con permiso registra turno para cliente | Exito |
| Empleado sin permiso registra turno para cliente | 403 |
| Empleado con skill requerida es candidato de asignacion | Incluido si horario/recurso disponibles |
| Empleado sin skill requerida | No asignable aunque vea agenda |
| Profesional asignado y con skill finaliza servicio | Exito |
| Profesional no asignado o sin skill finaliza servicio | 403 |
| Cliente finaliza su turno o confirma seña | 403 |
| Cliente lee/modifica turno ajeno | 404/403 sin filtrar existencia sensible |
| Cliente consulta diagnostico ajeno por `cliente_id` | 403/404 |
| Empleado con permiso de caja registra pago | Exito |
| Empleado sin permiso de caja | 403 |

### Administracion

| Test | Resultado esperado |
|---|---|
| Admin gestiona personal/skills | Exito y auditoria |
| Profesional intenta gestionar usuarios | 403 aunque tenga `is_staff` heredado durante transicion |
| Lectura de reportes con/sin permiso | 200/403 segun permiso |
| Lectura y reversion de auditoria | Permisos independientes |
| Configuracion global por no admin | 403 |
| Matriz completa endpoint x rol | Ningun acceso depende accidentalmente de la pagina frontend |

### Frontend

- Cada rol aterriza en una ruta valida.
- `ProtectedRoute` espera la carga de identidad y rechaza rutas sin permiso.
- Menus y botones reflejan permisos efectivos.
- Manipular `localStorage.user_info` no habilita una operacion backend.
- Un `403` muestra estado de acceso denegado sin bucles de navegacion.
- Cambio de rol obliga a recargar capacidades.
- Logout invoca backend y limpia estado local.

## 14. CONCLUSION

### Modelo definitivo recomendado

El modelo definitivo debe ser:

```text
Usuario
  -> exactamente un Group de negocio
     CLIENTE | EMPLEADO | PROFESIONAL | ADMINISTRADOR
  -> Permissions de Django para acciones concretas

Cliente
  -> perfil de consumo y ownership

Personal
  -> perfil laboral, horarios, asignaciones y skills

Autorizacion efectiva
  -> permiso + alcance del objeto + Personal activo + skill/asignacion cuando aplique
```

### Que conservar

- `Usuario` personalizado por email y su manager.
- `Cliente` como perfil de dominio y limite de ownership.
- `Personal` como perfil laboral opcional.
- `is_active` como estado de cuenta.
- Groups y Permissions heredados de Django, que ya existen aunque no se usen.
- Horarios, bloqueos, asignacion de `Turno.profesional` y skills actuales como datos para migrar.
- JWT, blacklist y recuperacion de contraseña, corrigiendo su politica de usuario activo y uso frontend.

### Que reemplazar o retirar gradualmente

- `is_staff` como rol de negocio o permiso API.
- `IsAdminUser` en endpoints de negocio.
- La dicotomia frontend Administrador/Cliente.
- El checkbox de escritura directa de `is_staff`.
- La elevacion implicita al crear Personal y el script masivo `fix_personal_staff.py`.
- Los chequeos dispersos `if request.user.is_staff`.
- `Personal.rol` como mezcla de especialidad y autorizacion; conservar temporalmente sus datos y convertirlo a puesto/especialidad.
- Los skills booleanos cuando el catalogo de habilidades este validado.
- La deteccion profesional mediante relaciones inexistentes `personal` o `profesional`.

### Primera tarea de implementacion

La primera tarea debe ser una **barrera de seguridad con tests**, antes de crear migraciones de roles:

1. Escribir tests que reproduzcan la elevacion por `PersonalViewSet` y la modificacion de `is_staff` por cuentas staff no administrativas.
2. Restringir la gestion de Personal y volver `is_staff` no escribible fuera de una operacion administrativa dedicada.
3. Confirmar que registro y login de clientes existentes siguen funcionando.

Despues de contener esa escalada, la primera tarea arquitectonica es definir la matriz final y sembrar Groups/Permissions sin cambiar todavia el comportamiento de los usuarios existentes.
