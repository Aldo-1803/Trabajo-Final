# BH-060 Incremento 5 — Seguridad de Django Admin

## 1. Alcance y resultado

Se auditó Django Admin sobre el baseline publicado
`b0831a326b33bbbac10e6ec367e20458a3b5e2b1`. El alcance se limitó al
Incremento 5: inventario de `ModelAdmin`, autorización HTTP efectiva y
contención de escrituras genéricas que podían evitar servicios semánticos.

Resultado técnico: los 35 `ModelAdmin` registrados quedaron clasificados y
probados. No se modificaron modelos, migraciones, APIs funcionales, servicios
financieros ni contratos de frontend.

## 2. Política aplicada

Las tres condiciones de acceso se mantienen separadas:

1. `is_staff=True`, cuenta activa y autenticada: puerta técnica del sitio.
2. Permiso Django del modelo: `view_*`/`change_*` para lectura y el permiso
   específico `add_*`, `change_*` o `delete_*` para cada escritura.
3. Capacidad efectiva de negocio: autoridad adicional indicada en el
   inventario siguiente.

Un ADMINISTRADOR de negocio no recibe `is_staff` automáticamente. Para los 32
Admin funcionales se requieren simultáneamente permiso de modelo y capacidad
de negocio. Los tres Admin técnicos son de lectura exclusiva para un
superusuario activo.

El superusuario conserva acceso técnico de lectura, pero no puede escribir en
los dominios declarados de sólo lectura. Todas las acciones masivas genéricas
quedaron deshabilitadas con `actions = None`.

### Leyenda de operaciones

- **Doble**: `is_staff` + permiso Django aplicable + capacidad de negocio.
- **Técnica**: superusuario Django activo; lectura exclusivamente técnica.
- **CRUD**: alta, cambio y baja disponibles sólo con la autoridad doble de la
  operación.
- **RO**: changelist y detalle permitidos; alta, cambio y baja denegados en el
  servidor, incluso al superusuario.
- **Producto especial**: alta requiere `MANAGE_PRODUCTS` y `MANAGE_PRICES`;
  cambio se limita por campo; baja requiere `MANAGE_PRODUCTS`. El stock nunca
  es escribible desde Admin.

## 3. Inventario de los 35 ModelAdmin

En todas las filas, **Lista/detalle** incluye tanto changelist como consulta
directa de objeto. **Acciones masivas** es `No` para los 35 modelos.

| # | Modelo | Lista/detalle | Alta / cambio / baja | Capacidad de negocio | Campos sensibles e invariantes |
|---:|---|---|---|---|---|
| 1 | `usuarios.Usuario` | Doble | RO | `MANAGE_USERS` | Password, `is_active`, `is_staff`, `is_superuser`, grupos y permisos. Altas, estados y roles siguen por onboarding y servicios de cuentas/roles; protege último administrador. |
| 2 | `usuarios.Cliente` | Doble | RO | `VIEW_CLIENTS` | `usuario`, `activo`, datos personales y perfil capilar. Asociación y estado siguen por servicios semánticos. |
| 3 | `gestion.Personal` | Doble | RO | `MANAGE_PERSONAL` | `usuario`, `activo`, rol, habilidades y flags legacy. Asociación, estado y acceso laboral siguen por servicios semánticos. |
| 4 | `gestion.TipoCabello` | Doble | CRUD | `MANAGE_CONFIGURATION` | Nombre, estado y puntaje del catálogo usado por diagnóstico. |
| 5 | `gestion.GrosorCabello` | Doble | CRUD | `MANAGE_CONFIGURATION` | Nombre, estado y puntaje del catálogo usado por diagnóstico. |
| 6 | `gestion.PorosidadCabello` | Doble | CRUD | `MANAGE_CONFIGURATION` | Nombre, estado y puntaje del catálogo usado por diagnóstico. |
| 7 | `gestion.CueroCabelludo` | Doble | CRUD | `MANAGE_CONFIGURATION` | Nombre, estado y puntaje del catálogo usado por diagnóstico. |
| 8 | `gestion.EstadoGeneral` | Doble | CRUD | `MANAGE_CONFIGURATION` | Nombre, estado y puntaje del catálogo usado por diagnóstico. |
| 9 | `gestion.CategoriaServicio` | Doble | CRUD | `MANAGE_CONFIGURATION` | Clasificación de servicios. |
| 10 | `gestion.ReglaDiagnostico` | Doble | CRUD | `MANAGE_CONFIGURATION` | Condiciones, prioridad, resultado y vigencia de reglas diagnósticas. |
| 11 | `gestion.Rutina` | Doble | RO | `ASSIGN_ROUTINES` | Versión, vigencia, pasos y clientes asignados. Creación/asignación/obsolescencia siguen por el flujo semántico de rutinas. |
| 12 | `gestion.RutinaCliente` | Doble | RO | `ASSIGN_ROUTINES` | Copia versionada, cliente, progreso y notificaciones. No se altera la asignación genéricamente. |
| 13 | `gestion.Notificacion` | Técnica | RO | Sólo superusuario | Destinatario, mensaje, canal, entidad e id de origen. Registro técnico inmutable desde Admin. |
| 14 | `gestion.Configuracion` | Doble | RO | `MANAGE_CONFIGURATION` | Seña, agenda, cancelaciones, pagos y WhatsApp. La configuración operativa no se salta por un formulario genérico. |
| 15 | `gestion.HorarioLaboral` | Doble | RO | `VIEW_GLOBAL_AGENDA` | Personal, días, rangos y horas. Cambios siguen por servicios de agenda/personal. |
| 16 | `gestion.BloqueoAgenda` | Doble | RO | `VIEW_GLOBAL_AGENDA` | Personal, motivo, alcance y rango temporal. Evita saltar conflictos e invariantes de agenda. |
| 17 | `gestion.TipoEquipamiento` | Doble | CRUD | `MANAGE_CONFIGURATION` | Tipos que condicionan requisitos de servicios. |
| 18 | `gestion.Equipamiento` | Doble | CRUD | `MANAGE_CONFIGURATION` | Código, tipo, estado, ubicación y activación. |
| 19 | `gestion.Servicio` | Doble | CRUD | `MANAGE_PRICES` | Precio base, duración y definición del servicio. El inline de requisitos exige además autoridad y permisos del modelo asociado. |
| 20 | `gestion.RequisitoServicio` | Doble | CRUD | `MANAGE_CONFIGURATION` | Servicio, tipo de equipamiento, obligatoriedad y cantidad mínima. |
| 21 | `gestion.FichaTecnica` | Doble | RO | `MANAGE_TECHNICAL_RECORD` | Turno/detalle, autor y resultados técnicos. Registro sólo mediante el flujo técnico autorizado. |
| 22 | `gestion.DiagnosticoCapilar` | Doble | RO | `MANAGE_TECHNICAL_RECORD` | Cliente, profesional, resultados, observaciones y fecha. Mantiene ownership, habilitación y trazabilidad del servicio semántico. |
| 23 | `gestion.ContenidoEducativo` | Doble | CRUD | `MANAGE_CONTENT` | Autor, contenido, estado y publicación. |
| 24 | `gestion.MeGusta` | Doble | RO | `MANAGE_CONTENT` | Asociación cliente-contenido y fecha; se origina en la interacción del cliente. |
| 25 | `gestion.ContenidoGuardado` | Doble | RO | `MANAGE_CONTENT` | Asociación cliente-contenido y fecha; se origina en la interacción del cliente. |
| 26 | `gestion.Auditoria` | Doble | RO | `VIEW_AUDIT` | Actor, tabla, registro, valores anterior/nuevo, IP y fecha. No admite edición, borrado ni reversión desde Admin. |
| 27 | `gestion.Producto` | Doble | Producto especial | `MANAGE_PRODUCTS`, `MANAGE_PRICES` o `VIEW_STOCK`, según operación/campo | Metadatos y precio conservan CRUD autorizado. `stock_real`, comprometido, disponible y mínimo son siempre RO y sólo cambian por commands de inventario. |
| 28 | `gestion.ImagenProducto` | Doble | CRUD | `MANAGE_PRODUCTS` | Producto, imagen y orden. El inline también exige permiso Django del modelo y capacidad efectiva. |
| 29 | `gestion.CategoriaProducto` | Doble | CRUD | `MANAGE_PRODUCTS` | Nombre y vigencia del catálogo de productos. |
| 30 | `gestion.Promocion` | Doble | CRUD | `MANAGE_PROMOTIONS` | Tipo, descuento, productos/servicios, vigencia, stock de combo y estado de sugerencia. |
| 31 | `gestion.MovimientoStock` | Doble | RO | `VIEW_STOCK` | Delta, saldos anterior/posterior, actor, razón, referencia e idempotencia. Ledger inmutable; creación sólo por servicio de inventario. |
| 32 | `gestion.CompromisoStock` | Doble | RO | `VIEW_STOCK` | Orden, producto, cantidad, estado, consumo/liberación e idempotencia. Reserva sólo por servicio de órdenes/inventario. |
| 33 | `gestion.OrdenPendiente` | Doble | RO | `MANAGE_STOCK` | Cliente, orden canónica, JSON, monto y estado. No confirma/cancela/completa órdenes fuera del flujo semántico. |
| 34 | `token_blacklist.OutstandingToken` | Técnica | RO | Sólo superusuario | Usuario, JTI, token y vencimiento. No permite reasociar ni borrar tokens. |
| 35 | `token_blacklist.BlacklistedToken` | Técnica | RO | Sólo superusuario | Asociación con token y fecha de blacklist. No permite revocar ni borrar genéricamente. |

### Modelos sensibles deliberadamente no registrados

- `auth.Group` y `auth.Permission`: roles y permisos sólo por servicios de
  autoridad; no existe una segunda administración funcional en Django Admin.
- `Habilidad` y `PersonalHabilidad`: asociaciones técnicas por servicios de
  Personal/habilidades.
- `Turno`: estados de agenda por commands semánticos.
- `OrdenCompra`, `Pago`, `PaymentPolicy`, `PaymentIntent` y líneas,
  conciliaciones, solicitudes/decisiones/eventos de resolución, refunds,
  ajustes y cierres financieros: no hay escritura financiera por Admin.
- `PasoRutina` y `PasoRutinaCliente`: no están registrados; sus declaraciones
  legacy permanecen dentro de un bloque deshabilitado.

## 4. Bypasses encontrados y contención

1. **Permiso de modelo sin autoridad de negocio.** Varios Admin estándar
   aceptaban los permisos Django sin comprobar la capacidad efectiva.
   `BusinessPermissionAdminMixin` exige ambas autoridades en el servidor.
2. **Autoridad de negocio sin permiso de modelo.** Producto, imágenes,
   categorías y promociones sobreescribían `has_*_permission` considerando
   sólo capacidades de negocio. Ahora también delegan en el permiso Django de
   la operación.
3. **Escritura genérica de dominios semánticos.** Usuario, Cliente, Personal,
   rutinas, configuración, agenda, ficha/diagnóstico, interacciones, auditoría,
   ledger, compromisos y órdenes pendientes quedaron de sólo lectura.
4. **Tokens mutables.** Los Admin provistos por SimpleJWT se reemplazaron por
   vistas técnicas, sólo lectura y exclusivas para superusuario.
5. **Acciones masivas.** Se deshabilitaron en todos los Admin funcionales y
   técnicos, evitando `delete_selected` y cualquier bypass de locks,
   validaciones o auditoría.
6. **POST de campos ocultos o readonly.** Las pruebas envían valores forjados a
   grupos, permisos, estados, asociaciones, auditoría y stock. Las operaciones
   se rechazan o los campos fuera de autoridad se ignoran sin mutación ni
   auditoría falsa.
7. **Superusuario.** Sigue siendo cuenta técnica de confianza para lectura y
   CRUD legítimo de catálogos/contenido, pero no elude los bloqueos RO del
   dominio, ledger, auditoría, tokens o estados de acceso.

La protección ya no depende de que un botón o campo sea invisible: se probaron
directamente las rutas y los POST del servidor.

## 5. Pruebas ejecutadas sobre PostgreSQL

| Bloque | Resultado | Cobertura |
|---|---:|---|
| `gestion.tests.test_django_admin_security_bh060_5` | **13/13 OK** | Login/index; los 35 changelist; detalle, alta, cambio, baja y acciones; anónimo, roles, ADMINISTRADOR no-staff, staff con autoridad de modelo/negocio separada, doble autoridad, superusuario e inactivo; POST forjados; grupos/permisos; último administrador; stock; auditoría y tokens. |
| BH-059 A–D, roles, sesión, cuentas y Personal | **304/304 OK** | Autoridad efectiva y servicios de acceso/estado. |
| Personal, habilidades, inventario, stock y órdenes | **123/123 OK** | Habilitaciones, ledger, compromisos y órdenes. |
| Pagos, PaymentIntent, conciliación, incidencias, resolución, refunds, ajustes y cierres | **165/165 OK** | Inmutabilidad y autorización financiera, incluidas concurrencias. |
| Diagnóstico aislado | **25/26 OK; 1 legacy conocido** | El único fallo es `test_legacy_flags_are_read_only_in_personal_serializer`: el test espera aceptar e ignorar flags legacy, mientras el serializer los rechaza explícitamente como campos no permitidos. No se debilitó esa protección. |
| `manage.py check` | **OK** | Sin incidencias del sistema Django. |

No se ejecutaron tests frontend ni build: no hubo cambios en contratos usados
por la aplicación ni en el frontend.

## 6. Invariantes preservadas

- ADMINISTRADOR de negocio continúa sin implicar `is_staff`.
- El último administrador, grupos BusinessRole y permisos individuales no se
  pueden modificar desde Admin.
- `Usuario.is_active`, estados de Cliente/Personal y asociaciones de perfiles
  no se escriben genéricamente.
- Stock físico/comprometido, ledger y reservas sólo cambian mediante servicios
  con locks, idempotencia y auditoría.
- Pagos confirmados, refunds, ajustes, incidencias, cierres y órdenes canónicas
  no están expuestos en Admin.
- Auditoría e historial no se editan, eliminan ni revierten desde Admin.
- Los rechazos no generan mutaciones ni registros de auditoría falsos.

## 7. Riesgos residuales

- El acceso de lectura puede incluir PII, datos técnicos e información de
  inventario; la asignación de `is_staff`, permisos Django y capacidades de
  negocio debe seguir gobernada y revisada.
- El superusuario puede leer todos los registros y mantener catálogos con CRUD
  explícitamente permitido; sus credenciales requieren controles operativos
  reforzados.
- Los Admin RO no ofrecen botones para ejecutar servicios semánticos. Las
  operaciones funcionales deben realizarse por las APIs/servicios existentes,
  no reimplementarse en Admin sin una iniciativa posterior.
- El fallo legacy de `PersonalSerializer` permanece fuera de este incremento y
  se informa por separado; el comportamiento actual es más restrictivo que la
  expectativa antigua.

No se inició BH-060 Incremento 6.
