# BH-058 D3 — Permisos y frontend de inventario

## Alcance

Este incremento cierra exclusivamente las superficies de autorización, API y
frontend de inventario definidas para D3. No modifica modelos, migraciones,
locks, idempotencia ni transiciones de D1/D2.

## Matriz auditada

| Operación | Endpoint o componente | Permiso requerido | Autoridad encontrada | Brecha y resultado |
|---|---|---|---|---|
| Consultar catálogo público | `GET /productos/` | público | `AllowAny`; el serializer ya ocultaba cantidades | Se conservó `available` y se verificó que no exponga cantidades internas. |
| Consultar inventario y movimientos | detalle/listado de productos, `stock_bajo`, `stock-movements` | `gestion.view_stock` | D1 ya usaba permiso efectivo | Sin brecha backend; se añadió la vista frontend de sólo lectura. |
| Recibir y ajustar stock | `stock/receive`, `stock/adjust` | `gestion.manage_stock` | D1 ya usaba permiso efectivo | Sin brecha backend; GestiónProductos ahora consume exclusivamente estos commands. |
| Corregir un movimiento | `stock-movements/{id}/correct` | `gestion.manage_stock` | D1 ya usaba permiso efectivo | Sin brecha backend; se añadió solicitud de corrección compensatoria en frontend. |
| Crear/editar/desactivar productos | `ProductoViewSet`, GestiónProductos | `gestion.manage_products` | `IsAdminUser` y controles sin capacidades | Reemplazado por permiso efectivo y controles por capacidad. |
| Crear un producto con precio inicial | `POST /productos/` | `manage_products` y `manage_prices` | autoridad única de admin | El endpoint exige metadata autorizada y el serializer exige `manage_prices` al recibir `precio`; la UI sólo habilita alta con ambos. |
| Modificar precios de productos | `PATCH /productos/{id}/` | `gestion.manage_prices` | mezclado con CRUD administrativo | Separado por campo; un usuario con sólo precios no puede alterar metadata. |
| Modificar precios de servicios | escrituras de `ServicioViewSet` | `gestion.manage_prices` | `IsAdminUser` / `is_staff` | La superficie existente de escritura quedó bajo el permiso efectivo de precios. |
| Administrar categorías | `CategoriaProductoViewSet`, pestaña Categorías | `gestion.manage_products` | escritura pública (`AllowAny`) | Escrituras cerradas; la lectura pública ve activas y el gestor también ve inactivas. |
| Administrar imágenes | `ImagenProductoViewSet` y admin | `gestion.manage_products` | `IsAdminUser` | Reemplazado por permiso efectivo. |
| Administrar promociones | `PromocionViewSet`, acciones y combos | `gestion.manage_promotions` | comprobaciones `is_staff` | Reemplazadas por permiso efectivo, también para sugerencias, publicación y rechazo. |
| Acceder a GestiónProductos | navegación y ruta | cualquiera de las cinco capacidades D3 | rol `ADMINISTRADOR` o mera autenticación | Menú y ruta usan permisos efectivos, incluidos permisos individuales. |
| Editar inventario genéricamente | serializer, admin y formulario | no permitido | campos omitidos/read-only podían ignorarse silenciosamente | `stock_real`, `stock_comprometido`, `stock_minimo` y proyecciones se rechazan; admin/UI son sólo lectura. |

## Matriz definitiva de permisos

| Capacidad | Autoridad efectiva | Operaciones habilitadas |
|---|---|---|
| Inventario interno | `user.has_perm('gestion.view_stock')` | cantidades internas, alertas y movimientos físicos |
| Operaciones de stock | `user.has_perm('gestion.manage_stock')` | recepción, ajuste y corrección mediante commands D1 |
| Productos | `user.has_perm('gestion.manage_products')` | metadata, categorías e imágenes |
| Precios | `user.has_perm('gestion.manage_prices')` | precio de producto y superficie existente de precios de servicios |
| Promociones | `user.has_perm('gestion.manage_promotions')` | CRUD y acciones de promociones/combos |

Los defaults existentes en `usuarios/roles.py` fueron auditados y no requirieron
cambios: CLIENTE no recibe permisos D3; EMPLEADO y PROFESIONAL reciben sólo
`view_stock`; ADMINISTRADOR recibe los cinco. Los permisos individuales de un
usuario activo funcionan sin rol administrativo. `is_staff`, `Personal.rol`,
`BusinessRole` y skills no son autoridad para estas operaciones.

## Cambios backend

- Se añadieron permisos DRF basados en `user.has_perm(...)` para productos,
  precios, promociones y la combinación necesaria para PATCH de producto.
- `ProductoSerializer` clasifica los campos antes de validar o guardar:
  metadata requiere `manage_products`, precio requiere `manage_prices` e
  inventario genérico se rechaza explícitamente.
- Una actualización que mezcla campos autorizados y no autorizados falla antes
  de `save()`, sin actualización parcial ni movimiento de stock.
- Productos y categorías conservan lectura pública filtrada. Usuarios internos
  autorizados pueden gestionar registros inactivos sin exponerlos al público.
- Categorías, imágenes, promociones y precios de servicios dejaron de depender
  de `IsAdminUser`/`is_staff` en las superficies auditadas.
- Django admin separa metadata y precio, mantiene inventario en sólo lectura y
  oculta cantidades a quien no tenga `view_stock`.
- No se creó ninguna migración ni se cambió la persistencia de inventario.

## Contrato frontend

- GestiónProductos obtiene capacidades desde `SessionContext`; no infiere
  autoridad a partir del nombre del rol.
- `view_stock` muestra stock real, comprometido, disponible, alertas y
  movimientos físicos sin controles de escritura.
- `manage_stock` muestra recepción, ajuste y corrección y llama únicamente a
  los endpoints semánticos D1. No crea `MovimientoStock` directamente.
- `manage_products` controla metadata, imágenes, desactivación y categorías;
  `manage_prices` controla únicamente el precio; `manage_promotions` controla
  combos/promociones.
- Tras un command exitoso se recargan producto, listado, alertas y movimientos
  permitidos. Los errores 403 y errores de dominio se muestran sin modificar
  saldos en el cliente.
- El catálogo cliente usa `available`, no muestra cantidades internas y al
  agregar al carrito sólo llama al command de carrito; no llama endpoints de
  stock, efectos de órdenes ni estados financieros.

## Pruebas y regresiones

### Backend

- Matriz D3 y D1 inventario durante desarrollo: **31/31 OK**.
- Matriz consolidada final de D1, D2, concurrencia, productos, categorías,
  órdenes, roles y `/me/`: **91/91 OK**.
- Matriz D3 después del ajuste de categorías inactivas: **11/11 OK**.
- Casos D3 cubiertos: lectura versus mutación, separación de los cinco
  permisos, `is_staff` sin autoridad, permiso individual, privacidad cliente,
  rechazo genérico, atomicidad de campos mixtos, categorías, promociones y
  precios de servicios.

### Frontend

- GestiónProductos y navegación durante desarrollo: **16/16 OK**.
- Suites afectadas finales (`GestionProductos`, catálogo cliente, navegación,
  sesión y rutas protegidas): **5 suites, 65/65 OK**.
- Cubierto: navegación por permiso, inventario de sólo lectura, recepción,
  ajuste, corrección, separación metadata/precio, categorías, promociones,
  errores 403/dominio, catálogo sin cantidades y ausencia de mutaciones de
  inventario desde acciones cliente.
- `npm run build`: **OK**. Permanecen warnings preexistentes en archivos ajenos
  a D3 y avisos de dependencias/Browserslist; no son bloqueantes. El warning de
  dependencias de `useEffect` introducido inicialmente en GestiónProductos fue
  eliminado.

### Checks técnicos

- `python manage.py check`: **OK**, sin issues.
- `python manage.py makemigrations --check --dry-run`: **OK**, sin cambios.
- `python -m compileall gestion usuarios`: **OK**.
- `git diff --check`: **OK** después de retirar tres espacios finales; los
  avisos CRLF/LF del entorno no representan errores del diff.

## Compatibilidad D1/D2

Las regresiones funcionales y concurrentes de D1/D2 pasan. D3 no altera
servicios transaccionales, locks, claves de idempotencia, compromisos ni el
efecto de inventario de `OrdenCompra`. GestiónProductos no ejecuta ese efecto y
no modifica estados financieros.

## Cuestiones diferidas y frontera

Quedan fuera de este incremento Mercado Pago nuevo, `ProviderPaymentAttempt`,
`ProviderEvent`, webhooks, booking/turnos, movimientos por servicios,
proveedores, devoluciones, caja física, un motor promocional nuevo, BH-059 y
los incrementos C1/C2. Los warnings legacy del build tampoco se corrigen para
no ampliar alcance.

BH-058 D3 = VALIDADO
