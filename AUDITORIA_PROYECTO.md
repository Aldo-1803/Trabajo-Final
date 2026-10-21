# Auditoría técnica integral - Bohemia Hair

**Fecha del análisis:** 20 de octubre de 2026
**Modalidad:** revisión estática del repositorio
**Alcance:** backend, frontend, persistencia, API, seguridad, integraciones, automatizaciones, pruebas y trazabilidad contra requisitos
**Resultado general:** el sistema tiene una cobertura funcional amplia y una base de dominio considerable, pero no está en condiciones de producción sin corregir fallas críticas de autorización, consistencia transaccional, agenda, stock, automatizaciones y configuración.

> Este informe no certifica funcionamiento en ejecución. No se levantaron servicios, no se conectó PostgreSQL, no se aplicaron migraciones, no se invocaron integraciones externas y no se ejecutaron pruebas. Las conclusiones distinguen evidencia estática de comportamiento verificado.

## 1. Resumen ejecutivo

El proyecto implementa una SPA React conectada por REST a Django REST Framework y PostgreSQL. El dominio cubre autenticación, clientes, diagnóstico capilar, servicios, rutinas, agenda, turnos, señas, personal, equipamiento, productos, promociones, carrito, órdenes, pagos, contenido educativo, notificaciones, reportes y auditoría.

La implementación no es un prototipo vacío: existen modelos, serializers, endpoints y pantallas para la mayoría de los requisitos. Sin embargo, la amplitud se logró concentrando gran parte de la lógica en archivos muy extensos y acumulando alternativas de un mismo flujo. El resultado es una aplicación de madurez **preproducción inestable**.

Los riesgos de mayor impacto son:

| Prioridad | Hallazgo | Impacto |
|---|---|---|
| Crítica | Acciones sensibles de órdenes y turnos no exigen rol administrativo | Un cliente puede completar/cancelar su propia orden o marcar su turno como realizado mediante la API |
| Crítica | Reprogramaciones modifican fecha/hora sin validar siempre agenda, profesional y equipamiento | Dobles reservas y sobreasignación de recursos |
| Crítica | Catálogos capilares y categorías de producto exponen CRUD con `AllowAny` | Modificación o borrado anónimo de datos maestros |
| Crítica | Credenciales administrativas reales están hardcodeadas en `frontend/cypress.config.js` | Compromiso de cuenta si el archivo se comparte, publica o respalda |
| Alta | Login propio no verifica `is_active` | Una cuenta desactivada podría obtener JWT si conserva credenciales válidas |
| Alta | Automatización post-servicio está duplicada entre view y múltiples signals no idempotentes | Diagnósticos, rutinas, tareas, promociones y notificaciones duplicadas; fallos parciales |
| Alta | Checkout, webhook y stock carecen de invariantes y bloqueos suficientes | Sobreventa, descuentos incorrectos y órdenes aprobadas con monto no validado |
| Alta | Mercado Pago redirige a rutas React inexistentes y usa defaults locales/túnel | Flujo de retorno incompleto y configuración no apta para producción |
| Alta | No existe manifiesto reproducible de dependencias Python ni pipeline de despliegue/CI | Entornos no reproducibles y cambios sin control automático |
| Alta | Cobertura automatizada real es mínima y no cubre flujos críticos | Regresiones probables en turnos, pagos, stock y permisos |

**Dictamen:** no apto para producción. Sí es una base válida para estabilización si se congela el alcance y se priorizan autorización, invariantes de negocio, transacciones, pruebas y despliegue.

## 2. Alcance y metodología

Se revisaron:

- Estructura completa bajo `bohemiacore/`, `frontend/` y `documentacion/`.
- Configuración Django, DRF, JWT, CORS, correo, media y Mercado Pago.
- Modelos, serializers, views, routers, servicios, señales, middleware, migraciones y comandos de gestión.
- Rutas React, pantallas administrativas y de cliente, servicios Axios, almacenamiento de tokens y pruebas Cypress/Jest.
- Documento de requisitos convertido a texto y diagramas PlantUML disponibles.
- Estado de Git para separar el análisis de cambios preexistentes.

No se realizaron:

- Cambios sobre código funcional.
- Ejecución de servidor, build, tests, migraciones o consultas a base de datos.
- Validación de credenciales, SMTP, Mercado Pago, WhatsApp o URLs públicas.
- Pruebas de carga, accesibilidad, seguridad dinámica o compatibilidad real de navegadores.

Escala utilizada:

| Estado | Significado |
|---|---|
| Implementado estáticamente | Existe un flujo coherente de modelo, API y UI, sin prueba runtime |
| Parcial | Hay piezas funcionales, pero faltan requisitos o integración |
| Defectuoso | Existe código, pero contiene fallas que comprometen el flujo principal |
| No implementado | No se encontró evidencia suficiente |
| No verificable | Requiere ejecución, datos o servicio externo |

## 3. Estado del repositorio y línea base

El worktree ya estaba modificado antes de generar este informe. Se observaron cambios en archivos centrales y numerosos archivos no versionados, incluidas migraciones, pruebas, documentación, media, Cypress y módulos de auditoría. Esta auditoría analiza el estado presente, no un commit limpio ni necesariamente reproducible.

Aspectos relevantes:

- `gestion/migrations/0002_initial.py` a `0018_*.py` aparecen como no versionadas en el estado observado.
- `documentacion/`, `frontend/cypress/`, `frontend/cypress.config.js` y varios módulos recientes también aparecen no versionados.
- Archivos de media cargados por la aplicación están dentro del workspace y no versionados.
- `venv/` existe localmente, pero no está versionado.
- No se encontró un `requirements.txt`, `pyproject.toml`, `Pipfile`, `Dockerfile`, `docker-compose.*` ni workflows de CI.
- El archivo raíz `.gitignore` no pudo interpretarse como texto por la herramienta de lectura, indicio de codificación o formato atípico; el `.gitignore` de frontend sí excluye `node_modules`, builds y variantes de `.env`.

Consecuencia: no hay una línea base confiable de entrega. Antes de estabilizar funcionalidad se debe decidir qué archivos forman parte del producto y construir un commit reproducible sin secretos ni media de usuario.

## 4. Estructura del proyecto

```text
Bohemia-hair/
|-- bohemiacore/
|   |-- bohemiacore/          # settings, URLs, WSGI/ASGI
|   |-- gestion/              # dominio principal, API, signals, comandos
|   |-- usuarios/             # usuario, cliente, auth y perfil
|   |-- media/                # archivos cargados localmente
|   |-- staticfiles/          # salida recolectada de estáticos
|   `-- manage.py
|-- frontend/
|   |-- src/                  # SPA React
|   |-- cypress/              # E2E y ejemplos de Cypress
|   `-- package.json
|-- documentacion/            # requisitos, UML y DSS
`-- venv/                     # entorno Python local
```

La separación física frontend/backend es clara. Dentro del backend, `gestion` concentra casi todos los subdominios. Dentro del frontend, la organización por `pages/admin`, `pages/cliente`, `components`, `api` y `routes` es entendible, pero muchas páginas contienen estado, API, validaciones y presentación en un único archivo.

No existe una capa profesional independiente: `frontend/src/pages/profesional/` no contiene implementación y las operaciones profesionales se mezclan con las administrativas.

## 5. Arquitectura observada

Flujo principal:

```text
React SPA
  -> Axios + JWT Bearer almacenado en localStorage
  -> Django REST Framework
  -> modelos Django + signals + servicios
  -> PostgreSQL

Integraciones laterales:
  -> almacenamiento local de media
  -> Gmail SMTP para recuperación de contraseña
  -> Mercado Pago SDK para checkout/webhook
  -> enlaces wa.me para pedidos por WhatsApp
  -> notificaciones persistidas en base de datos y polling del frontend
```

La arquitectura es un monolito modular por carpetas, pero no por límites internos. `gestion/views.py` combina controladores, reglas, transacciones, consultas, pagos, recomendaciones, reportes parciales y procesos automáticos. Los signals agregan una segunda ruta implícita de negocio. Esto dificulta saber qué efecto produce cada transición.

No se encontró infraestructura de tareas asíncronas, cola, scheduler, cache, almacenamiento externo, proxy, servidor de aplicación o observabilidad de producción.

## 6. Tecnologías y dependencias

### Frontend

| Componente | Versión declarada |
|---|---:|
| React / React DOM | 19.2.3 |
| React Router DOM | 7.9.5 |
| Axios | 1.13.2 |
| react-scripts | 5.0.1 |
| Tailwind CSS | 3.4.18 |
| Cypress | 15.10.0 |
| Testing Library React | 16.3.0 |
| Recharts | 3.7.0 |
| TinyMCE React | 6.3.0 |
| DOMPurify | 3.3.1 |
| jsPDF / html2canvas | 3.0.4 / 1.4.1 |

`react-scripts` 5 es una base antigua frente a React 19 y debe validarse por compatibilidad. No hay script específico para Cypress, lint independiente, type checking ni análisis estático en `frontend/package.json`.

### Backend

El entorno local reporta Django 5.2.7, DRF 3.16.1, SimpleJWT 5.5.1, django-filter, django-cors-headers, django-simple-history, psycopg2, Pillow, Mercado Pago SDK 3.2.0, python-decouple y python-dotenv.

Riesgos de dependencias:

- Las dependencias Python solo pueden inferirse del entorno local; no hay manifiesto reproducible.
- `bohemiacore/package.json` contiene únicamente `html2canvas` y `jspdf`, dependencias ya propias del frontend.
- No hay política visible de actualización, lock de Python, escaneo de vulnerabilidades ni SBOM.
- El código depende de PostgreSQL, Pillow, SMTP y Mercado Pago, pero no hay verificación automatizada de configuración.

## 7. Configuración, entornos y despliegue

Hallazgos en `bohemiacore/bohemiacore/settings.py`:

- `SECRET_KEY` tiene un fallback inseguro en la línea 13.
- `DEBUG` usa `True` como valor por defecto en la línea 16.
- `ALLOWED_HOSTS = ['*']` en la línea 18.
- Base de datos y nombre `bohemia_hair` están fijados al motor PostgreSQL.
- `REST_FRAMEWORK` declara `AllowAny` e `IsAuthenticated` juntos como permisos globales. DRF exige que ambas clases aprueben, por lo que el resultado práctico es autenticación global, salvo overrides explícitos.
- JWT dura 7 días y refresh 30 días, sin rotación ni blacklist posterior a rotación.
- CORS y CSRF solo contemplan hosts locales.
- La zona horaria es `America/Bogota`, mientras pagos, locale y teléfonos sugieren operación argentina. Debe confirmarse el huso de negocio.
- Mercado Pago usa por defecto una URL de túnel específica y redirects dependientes de localhost.
- Archivos media se sirven por Django solo con `DEBUG`; no existe estrategia de producción.

`bohemiacore/.env.example` no documenta las variables de Mercado Pago ni URLs de frontend/backend, a pesar de que el código las requiere.

No se encontró:

- Configuración separada por ambiente.
- Health checks.
- Logging estructurado y rotación.
- Política de backups.
- HTTPS/HSTS/cookies seguras/CSP explícitos.
- Pipeline de build y despliegue.
- Configuración de servidor WSGI/ASGI para producción.

## 8. Modelo de dominio y datos

El dominio está modelado con amplitud. Entidades principales:

| Área | Entidades |
|---|---|
| Identidad | `Usuario`, `Cliente`, `Personal` |
| Catálogos capilares | `TipoCabello`, `GrosorCabello`, `PorosidadCabello`, `CueroCabelludo`, `EstadoGeneral` |
| Diagnóstico | `ReglaDiagnostico`, `ConfiguracionDiagnostico`, `DiagnosticoCapilar` |
| Servicios y cuidados | `CategoriaServicio`, `Servicio`, `ReglaCuidado`, `Rutina`, `RutinaCliente`, `AgendaCuidados` |
| Agenda | `HorarioLaboral`, `BloqueoAgenda`, `Turno`, `DetalleTurno`, `ListaEspera` |
| Historial técnico | `FichaTecnica` |
| Recursos | `TipoEquipamiento`, `Equipamiento`, `RequisitoServicio` |
| Comercio | `CategoriaProducto`, `Producto`, `ImagenProducto`, `Promocion`, `ConfiguracionRetoque`, `Carrito`, `CarritoItem` |
| Órdenes y pagos | `OrdenPendiente`, `OrdenCompra`, `OrdenItem`, `Pago` |
| Contenido | `ContenidoEducativo`, `MeGusta`, `ContenidoGuardado` |
| Comunicación y control | `Notificacion`, `Auditoria`, `Configuracion` |

Fortalezas:

- Se conservan precios y duraciones históricas en detalles de turno y orden.
- Existen restricciones únicas para items de carrito, detalle de turno, likes, guardados y requisitos de equipamiento.
- Se usa `PROTECT` en referencias donde borrar el maestro dañaría históricos.
- Hay historial de django-simple-history en 16 modelos.
- Se modelan stock real y comprometido, estados de turno, canales de origen y pagos asociados a orden o turno.

Debilidades:

- `usuarios.models` importa modelos concretos desde `gestion`, mientras `gestion` referencia `usuarios`, generando acoplamiento circular.
- El modelo de roles se reduce a `is_staff`/`is_superuser`; `Personal.rol` no constituye autorización.
- `Turno.profesional` y `Turno.equipamiento` son opcionales, en contradicción con RNF-14.
- La restricción única de turno solo evita que el mismo cliente repita fecha/hora; no evita doble asignación del profesional o recurso.
- No existe modelo de insumo, movimiento de stock, lote, costo o consumo por servicio. El inventario implementado es principalmente catálogo de productos vendibles.
- `FichaTecnica` no tiene historial propio ni una entidad de versiones de fórmula, aunque el requisito lo pide.
- `Notificacion` declara choices limitados, pero el código persiste numerosos valores fuera de esos choices.
- `Pago.__str__` asume que siempre existe `orden`, aunque un pago puede pertenecer solo a un turno.
- El SKU autogenerado por `Producto.save()` no está protegido contra carreras concurrentes más allá del índice único.

## 9. Base de datos, migraciones e integridad

La cadena encontrada va de `0001_initial.py` a `0018_historicalturno_canal_origen_and_more.py`. La división entre `0001_initial` y `0002_initial` es válida como estrategia para resolver dependencias circulares entre apps, pero debe verificarse aplicando migraciones desde una base vacía.

Riesgos:

- La mayoría de las migraciones de `gestion` están no versionadas en el estado actual.
- No se verificó `makemigrations --check` ni `migrate --plan`.
- No hay evidencia de constraints de base para solapamientos, cantidades positivas, montos, rangos de fechas o exclusión entre `Pago.orden` y `Pago.turno`.
- Varias validaciones viven solo en serializers/views y pueden omitirse desde admin, shell, signals o código interno.
- `full_clean()` no se invoca sistemáticamente al guardar modelos.
- Operaciones de stock leen, validan y actualizan sin `select_for_update()` en los flujos principales.
- La auditoría basada en signals no captura cambios many-to-many, por ejemplo productos/servicios de promociones.

Recomendación: después de consolidar migraciones, agregar constraints de integridad para cantidades/montos, exigir exactamente un origen de pago, asegurar relaciones obligatorias de turnos según estado y diseñar una estrategia explícita contra solapamientos.

## 10. Backend: arquitectura y mantenibilidad

Métricas estructurales relevantes:

| Archivo | Tamaño aproximado | Observación |
|---|---:|---|
| `gestion/views.py` | 5.476 líneas | Controla casi todos los subdominios |
| `gestion/models.py` | 2.279 líneas | Define casi todo el modelo de negocio |
| `gestion/serializers.py` | 1.390 líneas | Mezcla contratos, validación y procesos |
| `gestion/signals.py` | 656 líneas | Auditoría y automatizaciones implícitas |
| `GestionProductos.js` | 1.786 líneas | UI, API y reglas de catálogo/stock |
| `GestionarServicios.js` | 1.428 líneas | Servicios, requisitos y configuración |
| `GestionTurnos.js` | 1.138 líneas | Estados, señas, pagos y ficha técnica |
| `ReservaCliente.js` | 1.026 líneas | Flujo completo de reserva |

Problemas concretos:

- `ServicioViewSet` se define dos veces en `gestion/views.py`; solo la segunda definición queda vinculada al import final.
- Hay dos implementaciones de estadísticas en `gestion/stats_views.py` y `gestion/views/stats_views.py`.
- Existen dos componentes `CampanaNotificaciones.js` con lógica casi idéntica.
- Hay lógica duplicada de Mercado Pago en una APIView y una acción del carrito.
- Finalización de turnos, disponibilidad, órdenes y notificaciones tienen más de una implementación.
- Comentarios de prueba, bloques completos comentados, imports duplicados, `print` de depuración y `except` amplios dificultan mantenimiento.
- Se usan signals para procesos complejos con efectos múltiples, reduciendo visibilidad transaccional.

La organización recomendada no requiere microservicios. Basta dividir `gestion` por casos de uso: agenda, diagnóstico, rutinas, catálogo, comercio, contenido, notificaciones y auditoría; mantener views delgadas y centralizar transiciones en servicios explícitos.

## 11. API REST y contratos

La API usa `DefaultRouter` y expone recursos para casi todo el dominio. Hay además endpoints manuales para checkout, disponibilidad, agenda, dashboard y carga de imágenes.

Fortalezas:

- Uso consistente de serializers DRF en la mayoría de endpoints.
- Filtros, búsquedas y ordenamiento en varios recursos.
- Querysets de cliente acotados en turnos, diagnósticos, rutinas asignadas, carrito, contenido guardado y órdenes.
- Acciones de auditoría, pagos, promociones y notificaciones están representadas como endpoints explícitos.

Problemas:

- Los nombres mezclan guiones y guiones bajos: `agregar-producto` frente a `agregar_producto`, `por_turno` frente a `por-turno`.
- No existe versionado `/api/v1/`.
- No se encontró esquema OpenAPI/Swagger ni contrato generado.
- La paginación global se desactiva en varios recursos grandes.
- Se retornan detalles internos de excepciones en algunos endpoints públicos.
- Hay respuestas con estructuras heterogéneas y códigos hardcodeados como `status=400`.
- `ContenidoEducativoViewSet` declara `filterset_fields`, `search_fields` y `ordering_fields`, pero no configura explícitamente backends en la clase; depende de defaults globales solo para filtros configurados.
- `contenidoEducativoAPI.getMisGuardados()` usa `?guardado=true`, pero el backend ofrece `/mis-guardados/` y no procesa ese parámetro.
- `contenidoEducativoAPI.getMisLikes()` usa `?me_gusta=true`, sin soporte equivalente visible.
- `contenidoEducativoAPI.getEstadisticas()` llama `/estadisticas/`, acción no encontrada.
- `SmartSuggestions` llama `carrito/agregar_producto/`, pero el backend registra `carrito/agregar-producto/`.

## 12. Frontend: arquitectura, UX y estado

La SPA tiene rutas de autenticación, cliente y administración. El diseño usa Tailwind/utilidades, estilos globales y componentes propios. Hay adaptación responsive visible en varias pantallas.

Fortalezas:

- Navegación diferenciada por `is_staff` en `Header`.
- Flujos de cliente para perfil, reservas, turnos, rutinas, catálogo, carrito, pedidos y contenido.
- Flujos administrativos amplios para agenda, turnos, servicios, productos, usuarios, clientes, personal, equipamiento, contenido, reportes, caja y auditoría.
- Uso de DOMPurify antes de `dangerouslySetInnerHTML` en `VisorHTML`.
- Manejo de loading/error y feedback visual en numerosas pantallas.

Debilidades:

- No hay capa de estado o consultas centralizada; cada pantalla maneja Axios, tokens, loading y normalización.
- URLs absolutas a `127.0.0.1` y `localhost` aparecen de forma masiva.
- Se mezclan clientes Axios globales, instancias propias y headers manuales.
- `PanelEditorContenido` busca `localStorage.token`, mientras el login guarda `access_token`.
- El interceptor elimina sesión ante cualquier 401, pero no intenta refresh a pesar de guardar `refresh_token`.
- JWT y datos de usuario permanecen en `localStorage`, ampliando impacto de un XSS.
- `ProtectedRoute` solo verifica que exista una cadena de token; no valida expiración ni rol.
- Todas las rutas admin usan el mismo `ProtectedRoute` de cliente.
- Las páginas públicas `Inicio`, `Servicios`, `Precios`, `Contacto` y `Acerca` no están montadas en `AppRoutes`; varias contienen datos mock/TODO.
- No existen rutas React para `/compra-exitosa`, `/compra-fallida` o `/compra-pendiente`.
- Hay polling de notificaciones cada 5 segundos por cliente, sin backoff ni pausa visible.
- Persisten logs de tokens truncados, perfiles, carrito y notificaciones en consola.
- Componentes y páginas extensos dificultan pruebas y reutilización.

## 13. Autenticación, roles y permisos

### Autenticación

La aplicación usa JWT. Existe login propio, endpoints estándar de SimpleJWT, refresh, logout con blacklist y recuperación de contraseña por token de Django.

Hallazgos:

- `LoginView` obtiene el usuario directamente y no verifica `usuario.is_active` antes de emitir tokens (`usuarios/views.py:88-108`).
- No hay throttling de login, registro o recuperación de contraseña.
- La respuesta de recuperación oculta correctamente la existencia del correo, pero puede devolver el detalle de una excepción SMTP al cliente.
- El frontend guarda access y refresh en `localStorage` y no consume automáticamente `/api/token/refresh/`.
- `handleLogout` del frontend solo borra almacenamiento local; no llama al endpoint de blacklist.
- Un access token dura 7 días, una ventana elevada para almacenamiento expuesto a JavaScript.

### Autorización

El modelo real distingue cliente frente a staff. `Personal.rol` no participa de permisos de DRF. No existe una política reutilizable de objeto o roles profesional/admin.

Problemas de autorización confirmados:

| Recurso/acción | Permiso actual | Riesgo |
|---|---|---|
| Catálogos capilares | `AllowAny` en `ModelViewSet` | CRUD anónimo |
| Categorías de servicio | `AllowAny` en `ModelViewSet` | CRUD anónimo |
| Categorías de producto | `AllowAny` en `ModelViewSet` | CRUD anónimo |
| `PersonalViewSet` | `IsAuthenticated` | Cualquier cliente autenticado puede intentar CRUD de personal y elevar `is_staff` al vincular usuario |
| `TipoEquipamientoViewSet` | `IsAuthenticated` | Cualquier autenticado puede CRUD |
| `EquipamientoViewSet` | Permiso global autenticado | Cualquier autenticado puede CRUD |
| `crear_bloqueo` | `IsAuthenticated` | Un cliente puede crear bloqueos de agenda |
| `TurnoViewSet.finalizar_turno` | `IsAuthenticated` + objeto propio | Un cliente puede finalizar su propio turno y disparar efectos post-servicio |
| `OrdenPendiente.confirmar_pago/entrega/cancelar` | `IsAuthenticated` + orden propia | Cliente modifica estado y stock de su propia orden |
| `OrdenCompra.confirmar_entrega/cancelar` | `IsAuthenticated` + orden propia | Cliente completa/cancela su orden y afecta stock |

El frontend oculta links según `is_staff`, pero esto no reemplaza autorización backend.

## 14. Seguridad

### Hallazgos críticos y altos

1. **Credenciales en Cypress.** `frontend/cypress.config.js:8-11` contiene credenciales administrativas hardcodeadas. El archivo está no versionado, pero ya existe en el workspace y puede filtrarse por ZIP, backup o commit accidental. Se debe rotar esa contraseña, eliminar el valor del archivo y usar variables de entorno.
2. **CRUD anónimo de maestros.** Los `ModelViewSet` de catálogos capilares, categoría de servicio y categoría de producto usan `AllowAny` para todos los métodos.
3. **Escalada a staff.** `PersonalViewSet` acepta cualquier autenticado y `PersonalSerializer.create()` marca `usuario.is_staff = True` al vincular un usuario (`serializers.py:597-608`).
4. **Acciones operativas accesibles al cliente.** Varias acciones de órdenes y turnos no exigen `IsAdminUser`.
5. **Cuenta desactivada aún autenticable.** El login propio no revisa `is_active`.
6. **Webhook sin validación de firma ni invariantes de pago.** Se consulta el pago oficial por ID, lo cual ayuda, pero no se compara monto, moneda, preference ID ni titular contra la orden antes de completarla.
7. **Defaults inseguros de producción.** `DEBUG=True`, secret fallback, `ALLOWED_HOSTS=*` y URL pública de túnel por defecto.

### Hallazgos medios

- Tokens en `localStorage` y contenido enriquecido aumentan el impacto potencial de XSS; DOMPurify mitiga solo la ruta que usa `VisorHTML`.
- La validación de uploads confía en `content_type`; no inspecciona firma real ni procesa archivos en almacenamiento aislado.
- El middleware de auditoría confía en el primer `X-Forwarded-For` sin lista de proxies confiables.
- Logs incluyen correos, usuarios, estructura de respuestas y datos operativos.
- No se encontró rate limiting, CSP, protección específica de fuerza bruta ni límites de payload globales.
- Media local puede incluir comprobantes de pago y fotos técnicas; no se encontró control de acceso por archivo.
- Los comprobantes bajo `MEDIA_URL` podrían ser servidos directamente si se conoce la ruta.
- La auditoría registra una gran cantidad de campos, pero no muestra política de minimización, retención ni protección contra modificación directa de base.

## 15. Usuarios, perfil y diagnóstico capilar

**Estado:** parcial avanzado, con defectos de autorización y consistencia.

Implementado estáticamente:

- Usuario personalizado por email.
- Registro conjunto de usuario y cliente.
- Login, logout, perfil y recuperación de contraseña.
- Catálogos capilares configurables.
- Perfil con tipo, grosor, porosidad, cuero cabelludo y estado general.
- Diagnósticos históricos y motor por reglas/score.
- Sugerencia de rutina, servicio urgente y turno sugerido.
- Gestión administrativa de usuarios y listado de clientes.

Brechas:

- No hay roles formales cliente/profesional/admin ni permisos por rol de dominio.
- `RegistroView` asigna `usuario.es_cliente = True`, atributo que no existe como campo del modelo; la asignación no se persiste realmente.
- Catálogos que alimentan el diagnóstico son modificables anónimamente.
- No se encontró versionado explícito del perfil capilar del cliente; el histórico depende de `DiagnosticoCapilar` y simple-history en modelos seleccionados.
- El motor se invoca desde más de un flujo y puede producir asignaciones duplicadas.
- Recomendaciones dependen de coincidencias de texto en nombres de catálogos, sensibles a configuración y ortografía.

## 16. Servicios, rutinas e historial técnico

### Servicios

**Estado:** parcial avanzado.

Existen categorías, precio, duración, plantilla de fórmula, simultaneidad, impacto capilar, espera química, rutina recomendada y requisitos de equipamiento. El segundo `ServicioViewSet` aplica lectura pública y escritura admin.

Brechas:

- La definición duplicada de `ServicioViewSet` crea código muerto y confusión.
- No se modelan insumos estándar ni consumos por servicio, pese al requisito de inventario.
- Las esperas químicas están repartidas entre `dias_espera_bloqueo`, `dias_espera_minima`, serializer y servicios.

### Rutinas

**Estado:** defectuoso.

Existen plantillas, versión numérica, estados, archivo, copias por cliente, selección y asignación automática.

Fallas concretas:

- `RutinaViewSet.destroy()` guarda `OBSOLETA`, pero el choice válido es `obsoleta`.
- `notificar_actualizacion()` llama `rutina.notificar_actualizacion_a_copias()`, método no definido en el modelo.
- La selección permite elegir una rutina sin comprobar que esté publicada y sin evitar duplicados.
- El flujo alternativo `SeleccionarRutinaView` puede responder éxito sin persistir nada.
- La funcionalidad de pasos está comentada y el router de `PasoRutinaViewSet` está deshabilitado.
- No hay evidencia de una descarga auditada ni adherencia real a tareas.

### Historial técnico

**Estado:** parcial.

`FichaTecnica` conserva fórmula, proceso, comentario, rutina, estado final y foto por detalle de turno. La API está restringida a staff y permite filtrar por turno/cliente.

Brechas:

- No hay versionado de fórmula ni `HistoricalRecords` en `FichaTecnica`.
- No se deducen insumos desde la fórmula.
- El serializer impide crear ficha en estado `realizado`, aunque el uso real puede requerir cierre y ficha en el mismo flujo.
- El acceso se basa en `is_staff`, no en una autorización profesional específica.

## 17. Agenda, turnos y señas

**Estado:** funcionalmente amplio pero defectuoso en invariantes críticas.

Implementado estáticamente:

- Horarios por personal y vigencia.
- Bloqueos de agenda.
- Consulta de disponibilidad por servicio/profesional.
- Requisitos de equipamiento.
- Solicitud, aprobación, espera de seña, confirmación, cancelación, realización y ausencia.
- Reprogramación de cliente y profesional.
- Límites configurables, deadline de seña y comprobante.
- Ofertas de adelanto ante cancelación.
- Alta presencial y registro de pagos.

Fallas críticas:

- `gestionar_cancelacion` cambia fecha/hora en sus tres ramas de reprogramación sin llamar a `_validar_slot_libre`.
- `gestionar_profesional` también reprograma sin validar disponibilidad.
- La aceptación de una oferta de adelanto actualiza el turno sin bloqueo de fila ni validación final del slot.
- La exclusión de ofertas competidoras usa `turno_actual_id`, que es diferente para cada candidato; no representa de forma robusta el hueco cancelado.
- `reprogramar_cliente` restringe estados a solicitado/esperando seña, por lo que su rama posterior para confirmado es inalcanzable.
- No hay constraint de base contra dobles reservas.
- `TurnoSerializer.create()` valida duplicado del cliente, pero no valida integralmente profesional, horario laboral, bloqueo, solapamiento y equipamiento antes de crear.
- Clientes pueden enviar campos como `estado`, `profesional`, `equipamiento`, `tipo_pago_registro` y `monto_abonado`; parte se sobrescribe al crear, pero en actualización permanecen expuestos y la autorización es insuficiente.
- `finalizar_turno` no exige staff.
- El endpoint `crear_bloqueo` acepta cualquier autenticado.
- `crear_bloqueo` usa `turno.cliente.nombre/apellido`, atributos inexistentes, y combina `hora_fin_calculada` aunque puede ser `None`.
- `DisponibilidadService.validar_recursos_dinamicos()` filtra un ForeignKey `tipo` con el string `TECNICA`; la excepción se captura y el algoritmo permite la reserva en modo fail-open.
- Ese servicio no descuenta `horarios_ocupados_set` al construir la respuesta; calcula el set pero solo llama a la validación de recursos.

Señas:

- El modelo registra deadline, comprobante, monto abonado y saldo.
- No existe una entidad `Seña` con snapshot de política y estados completos pedidos por IRQ-15.
- El comando de vencimientos requiere ejecución externa no configurada.
- Los tipos/canales de notificación usados por el comando no coinciden con choices del modelo.

## 18. Productos, inventario y promociones

### Productos e inventario

**Estado:** parcial.

Existen catálogo, SKU, imágenes, precio, stock real, stock comprometido, mínimo, categorías y compatibilidad capilar. Se muestran alertas y recomendaciones.

Brechas:

- No hay movimientos de inventario, entradas, ajustes, costos, lotes ni historial de precio dedicado.
- No hay insumos técnicos ni descuento automático por servicio/fórmula.
- La alerta `stock_bajo` compara `stock_real <= stock_minimo`, no `stock_disponible <= stock_minimo` como indica su descripción.
- `stock_bajo` está expuesto públicamente por la política dinámica del producto.
- Al agregar a un item existente se valida solo la cantidad nueva contra stock, no la suma final del item.
- Las operaciones de reserva/descuento no bloquean filas, por lo que son vulnerables a carreras.
- `ImagenProducto.save()` guarda siempre en JPEG sobre la ruta original, incluso si la extensión era PNG/WebP/GIF.

### Promociones

**Estado:** parcial avanzado.

Existen combos, retoques y last-minute, sugerencias automáticas, aprobación/rechazo y parámetros de similitud.

Brechas:

- El escaneo de huecos es una acción manual; no se encontró scheduler cada 1-5 minutos.
- No se implementó cap de frecuencia por cliente, descuento máximo global ni prevención general de stacking.
- Las promociones de retoque pueden duplicarse cada vez que se vuelve a finalizar/guardar un turno realizado.
- La creación aleatoria de servicios fallback y las coincidencias por nombre de categoría reducen determinismo.
- No se conserva snapshot completo de la regla que generó cada promoción.

## 19. Carrito, órdenes, WhatsApp y pagos

**Estado:** defectuoso y con dos estrategias comerciales superpuestas.

Existen dos flujos:

1. Pedido externo por WhatsApp con stock comprometido y `OrdenPendiente`.
2. Compra interna con `OrdenCompra`, `OrdenItem`, `Pago` y checkout Mercado Pago.

Esto contradice el documento de requisitos, que en OBJ-06 indica que la compra se realiza externamente. Debe definirse cuál es el alcance vigente.

Problemas de consistencia:

- `OrdenPendiente` almacena items en JSON, pero acciones intentan también usar `orden.items`, relación que no existe en el modelo mostrado.
- `OrdenPendiente.cancelar()` itera `orden.items.all()` y fallará.
- Clientes pueden invocar confirmación de pago/entrega sobre sus propias órdenes pendientes.
- Clientes pueden invocar confirmación de entrega/cancelación sobre sus `OrdenCompra`.
- `OrdenCompraSerializer` permite escritura de cliente, estado y total en CRUD genérico; no hay política por acción.
- El checkout Mercado Pago no revalida ni reserva stock antes de crear la preferencia y vaciar el carrito.
- El webhook descuenta con `max(0, stock-cantidad)`, ocultando sobreventa en vez de rechazar inconsistencia.
- El webhook no compara `transaction_amount` con `orden.total`.
- La actualización de stock por webhook sí usa orden bloqueada, pero no bloquea productos individualmente.
- El flujo WhatsApp compromete stock sin transacción atómica ni expiración/liberación automática demostrada.
- El frontend actualiza cantidades borrando y recreando el item en dos requests; un fallo intermedio pierde el item.

Problemas de integración Mercado Pago:

- Defaults apuntan a túnel y localhost.
- No se valida firma del webhook.
- No hay rutas frontend para resultados del pago.
- No se encontraron pruebas del webhook, idempotencia, rechazo, monto incorrecto o concurrencia.
- La integración existe en código, pero su funcionamiento productivo es **no verificable**.

## 20. Contenido, notificaciones e integraciones externas

### Contenido educativo

**Estado:** parcial avanzado.

Existen borrador/publicado/archivado, texto/multimedia, tags, autor, likes, guardados y recomendación por diagnóstico. El render HTML usa DOMPurify.

Brechas:

- El requisito plantea consulta pública, pero backend y rutas React exigen autenticación.
- La API frontend usa endpoints/parámetros inexistentes para guardados, likes y estadísticas.
- El serializer presenta `autor` como read-only y el backend lo asigna correctamente, pero la UI conserva implementaciones de prueba/guía dentro de `src/api`.
- El campo `multimedia_url` depende de terceros sin validación de host ni estrategia de almacenamiento.

### Notificaciones

**Estado:** parcial y no durable.

Existen persistencia in-app, lectura, polling, eventos de turnos, rutinas, promociones y adelantos.

Brechas:

- No hay worker, reintentos, scheduler ni entrega durable.
- Email solo se usa para recuperación de contraseña.
- WhatsApp es un enlace `wa.me`, no una integración de envío o tracking.
- No se encontró SMS.
- Choices definidos no incluyen muchos valores escritos por views, signals y comandos.
- `recordatorios_pendientes.py` filtra `fecha_creacion`, campo inexistente en `Notificacion`; el comando fallará si hay pendientes.
- Ese comando puede intentar crear notificación para `prof.usuario=None`.
- Hay dos componentes de campana y cada uno hace polling frecuente.
- Aceptar adelanto no está protegido por una transacción integral sobre hueco, turno y ofertas.

## 21. Automatizaciones y procesos programados

Procesos encontrados:

| Proceso | Disparador actual | Estado |
|---|---|---|
| Cuidados post-servicio | `post_save(Turno)` | Defectuoso, no idempotente |
| Actualización capilar y rutina | Otro `post_save(Turno)` | Defectuoso, duplica flujo |
| Diagnóstico/promoción de retoque | `finalizar_turno` | Duplicado con signals |
| Combo automático | `post_save(Producto)` al crear | Implementado estáticamente |
| Cancelación por expiración | Consulta de turnos y comando | Duplicado, no verdaderamente programado |
| Recordatorios pendientes | Management command | Defectuoso por campo inexistente |
| Promociones programadas | Management command | Parcial, sin scheduler |
| Last-minute | Acción HTTP manual | Parcial, no automática |

Fallas importantes de signals:

- Se ejecutan cada vez que se guarda un turno cuyo estado ya es `realizado`; no detectan transición anterior -> realizado.
- `generar_cuidados_post_servicio` y `automatizacion_post_servicio` pueden crear tareas repetidas.
- `finalizar_turno` agrega su propia creación de diagnóstico, rutina y promoción.
- En `signals.py:453-461`, `cliente.estado_general` se asigna fuera del `if servicio.impacto_estado`, por lo que un servicio sin impacto puede limpiar el estado y marcar cambio igualmente.
- La creación de `RutinaCliente` desde signals omite el archivo requerido por el modelo.
- Los fallos de receivers pueden dejar el turno guardado pero el request con error si no hay una transacción externa.

No se encontró Celery, Redis, django-q, APScheduler, cron documentado ni servicio de tareas. Por tanto, los comandos no constituyen automatización operativa por sí solos.

## 22. Reportes, auditoría y observabilidad

### Reportes

**Estado:** inicial/parcial.

Hay dashboard operativo y reportes por período de ventas, productos y rutinas. Sin embargo:

- La variable/respuesta `servicios` se calcula desde `OrdenItem.producto`, no desde servicios de turnos.
- No se encontraron métricas completas de cancelaciones, no-show, tiempos, stock consumido, adherencia a rutinas o aceptación de recomendaciones.
- El filtro usa `__range=[start_date, end_date]` con un fin calculado como exclusivo, pero `range` es inclusivo; puede incluir el primer día del período siguiente.
- No hay exportación backend ni pruebas de exactitud contable.

### Auditoría

**Estado:** amplio pero complejo.

Hay dos mecanismos paralelos:

- Modelo `Auditoria` alimentado por signals propios y middleware thread-local.
- `django-simple-history` con consulta y reversión selectiva.

Fortalezas:

- Acceso administrativo.
- Captura de altas, cambios y bajas en numerosos modelos.
- Vista de diferencias y reversión limitada a modelos seleccionados/campos escalares.

Riesgos:

- `_valores_anteriores` es un diccionario global compartido y no thread-local; solicitudes concurrentes sobre el mismo registro pueden mezclar snapshots.
- El middleware no limpia thread-local en `finally`, por lo que una excepción o reutilización de hilo puede dejar contexto residual.
- Los cambios many-to-many no se registran en la auditoría propia.
- Hay registros manuales y automáticos que pueden duplicar auditoría.
- No se auditan todas las entidades críticas, por ejemplo `FichaTecnica`, `CarritoItem` y `OrdenPendiente` de forma uniforme.
- La IP basada en `X-Forwarded-For` puede falsificarse sin configuración de proxy.
- No hay política de retención, inmutabilidad ni respaldo del log.

### Observabilidad

No se encontró integración con métricas, trazas, error tracking o alertas. El proyecto mezcla `logging` y `print`, incluyendo emojis y datos operativos. No hay IDs de correlación ni configuración visible de handlers por ambiente.

## 23. Trazabilidad frontend - API - backend

| Flujo | Frontend | API/backend | Evaluación |
|---|---|---|---|
| Registro/login/perfil | Páginas auth y perfil | `usuarios/*` | Integrado estáticamente; login inactivo y refresh pendientes |
| Diagnóstico inicial | Registro/perfil | perfil + motor diagnóstico | Parcial; reglas y asignaciones requieren estabilización |
| Catálogo/solicitud de turno | `CatalogoServicios`, `ReservaCliente` | servicios, disponibilidad, turnos | Amplio, pero invariantes de agenda incompletas |
| Gestión de turnos | `GestionTurnos` | acciones de `TurnoViewSet` | Parcial; demasiadas rutas de transición |
| Agenda | `AgendaAdmin` | horarios, bloqueos, calendario | Parcial; autorización y conflictos defectuosos |
| Rutinas | catálogos/mis rutinas/admin | rutinas y rutinas-cliente | Defectuoso por métodos/estados y pasos deshabilitados |
| Ficha técnica | registro/visualización | fichas por turno/cliente | Parcial; acceso staff y sin versionado |
| Productos | catálogo/admin | productos, categorías, imágenes | Integrado; seguridad de categorías y stock pendientes |
| Carrito | `Carrito` | acciones carrito | Integrado; actualización no atómica |
| Mercado Pago | botón checkout | preferencia/webhook/redirects | Incompleto por retornos y validación |
| Pedidos | `MisPedidos`, `GestionOrdenes` | órdenes compra/pendientes | Integrado parcialmente; permisos críticos incorrectos |
| Contenido | páginas cliente/admin | contenido/likes/guardados | Parcial; contratos frontend desalineados |
| Notificaciones | campana | notificaciones/aceptar | Integrado in-app; no durable y duplicado |
| Reportes | `Reportes` | `stats` | Parcial y semánticamente incompleto |
| Auditoría | `Auditoria` | auditoría + simple-history | Integrado estáticamente; concurrencia pendiente |

## 24. Cobertura de requisitos

Matriz basada en RF-01 a RF-15 del documento de requisitos:

| RF | Requisito | Estado | Evidencia y brecha principal |
|---|---|---|---|
| RF-01 | Autenticación y usuarios | Parcial | Registro/login/reset/CRUD existen; roles débiles, login de inactivos y sin throttling |
| RF-02 | Perfil y diagnóstico | Parcial avanzado | Perfil, catálogos e histórico existen; autorización de catálogos y consistencia del motor pendientes |
| RF-03 | Rutinas de cuidado | Defectuoso | Plantillas/copias/archivos existen; pasos deshabilitados, métodos rotos y duplicados |
| RF-04 | Historial de servicios y técnico | Parcial | Turnos y fichas existen; fórmula sin versionado y acceso basado solo en staff |
| RF-05 | Turnos y agenda | Defectuoso | Flujo amplio; dobles reservas, reprogramaciones y permisos impiden considerarlo completo |
| RF-06 | Servicios | Parcial avanzado | CRUD, detalle, impacto y requisitos; sin insumos estándar y con ViewSet duplicado |
| RF-07 | Productos y promociones | Parcial | Catálogo/stock/promos existen; inventario técnico, gobernanza y concurrencia faltan |
| RF-08 | Pedidos WhatsApp | Parcial | Link y registro existen; stock/estados inconsistentes y alcance compite con Mercado Pago |
| RF-09 | Contenido educativo | Parcial avanzado | CRUD, likes, guardados y recomendación; consulta no pública y contratos desalineados |
| RF-10 | Notificaciones | Parcial | In-app existe; email/WhatsApp operativo, reintentos y scheduler ausentes |
| RF-11 | Automatizaciones | Defectuoso | Hay signals/comandos, pero no idempotencia ni orquestación |
| RF-12 | Reportes | Parcial inicial | Ventas/productos/rutinas; faltan servicios, turnos, stock y métricas requeridas |
| RF-13 | Equipamiento | Defectuoso | Modelos/UI/API existen; permisos y endpoint `opciones` incorrectos |
| RF-14 | Personal | Defectuoso | CRUD y skills existen; cualquier autenticado puede modificar y elevar staff |
| RF-15 | Horarios del personal | Parcial | CRUD masivo y consulta existen; faltan validaciones robustas e integración segura |

Requisitos no funcionales:

| RNF | Evaluación |
|---|---|
| Usabilidad/accesibilidad | Parcial; responsive visible, sin auditoría WCAG ni tests |
| Rendimiento | No verificable; consultas optimizadas en zonas, polling y loops N+1 en otras |
| Seguridad | No cumplido por permisos y configuración crítica |
| Disponibilidad 99% | No verificable; sin infraestructura ni reintentos |
| Escalabilidad/configurabilidad | Parcial; parámetros existen, reglas aún dependen de strings/código |
| Mantenibilidad | No cumplido por archivos monstruo, duplicación y efectos implícitos |
| Compatibilidad | No verificable; browserslist existe, sin matriz de pruebas |
| Auditabilidad | Parcial avanzado; cobertura amplia con riesgos de concurrencia/integridad |
| Integración externa | Parcial; SMTP/WhatsApp/MP no certificados |
| Backups | No implementado |
| Gobernanza de promociones | No implementado de forma completa |
| Seguridad de personal | No cumplido por permisos de `PersonalViewSet` |
| Recursos en tiempo real | No cumplido de forma confiable |
| Integridad referencial de recursos | No cumplido; relaciones opcionales y sin constraint |

## 25. Pruebas y calidad

### Backend

- `gestion/tests/test_auditoria.py` contiene tres pruebas para alta, modificación y baja de `Servicio`.
- `usuarios/tests.py` está vacío.
- `gestion/test.py` está vacío.
- No se encontraron pruebas unitarias de permisos, turnos, disponibilidad, signals, diagnóstico, carrito, stock, órdenes, pagos, webhook, comandos o reportes.

Las pruebas de auditoría dependen de thread-local asignado manualmente y no limpian ese estado al finalizar, lo que puede contaminar casos posteriores.

### Frontend

- `App.test.js` conserva el test plantilla `renders learn react link`, incompatible con la UI actual.
- Hay Cypress específicos para registro/diagnóstico, combos, catálogo/reserva, turnos esperando seña, dashboard, reportes y adelantos.
- Cuatro specs de nivel superior son plantillas que solo visitan `example.cypress.io`.
- También permanece el directorio completo de ejemplos oficiales de Cypress.
- La configuración Cypress contiene credenciales reales y no define `baseUrl`.
- No hay script npm de E2E ni evidencia de ejecución en CI.

Pruebas mínimas faltantes antes de producción:

1. Matriz de autorización por endpoint, método y rol.
2. Transiciones válidas/invalidas de turno y seña.
3. Concurrencia de reservas y equipamiento.
4. Idempotencia de finalización y signals.
5. Stock concurrente, cancelación y entrega.
6. Webhook firmado, duplicado, monto incorrecto, rechazo y pending.
7. Login de usuario inactivo, expiración y refresh.
8. Recuperación de contraseña sin filtración de errores.
9. Contratos frontend/backend de contenido, carrito y notificaciones.
10. Migraciones desde base vacía y actualización desde una base existente.

## 26. Hallazgos priorizados y plan de estabilización

### P0 - Contención inmediata

| Acción | Criterio de salida |
|---|---|
| Rotar credencial expuesta en Cypress y eliminar secretos del workspace/config | Ningún secreto real en archivos; pruebas usan variables de entorno |
| Restringir CRUD de catálogos, personal, equipamiento y bloqueos | Matriz backend con lectura/escritura explícita por rol |
| Restringir finalizar turnos y mutar órdenes/pagos/stock | Solo rol autorizado puede ejecutar cada transición |
| Rechazar login de `is_active=False` y agregar throttling | Tests positivos y negativos de autenticación |
| Validar firma e invariantes de webhook | Firma, merchant/preference, moneda y monto comprobados; idempotencia probada |
| Desactivar defaults inseguros de producción | Arranque falla si faltan secretos/hosts/URLs en ambiente productivo |

### P1 - Integridad de negocio

| Acción | Criterio de salida |
|---|---|
| Crear un único servicio transaccional de transición de turnos | Todas las rutas usan la misma máquina de estados |
| Validar disponibilidad al crear, reprogramar y aceptar adelanto | No hay doble booking bajo concurrencia |
| Hacer idempotente la finalización post-servicio | Repetir request/save no duplica ningún efecto |
| Consolidar flujo de stock y órdenes | Reserva, liberación y descuento son atómicos y auditables |
| Definir WhatsApp versus Mercado Pago | Un alcance vigente documentado, sin estados paralelos ambiguos |
| Reparar comandos y configurar scheduler durable | Ejecución periódica, locking, retries y monitoreo |

### P2 - Contratos y calidad

| Acción | Criterio de salida |
|---|---|
| Centralizar cliente HTTP y `API_BASE_URL` | Sin URLs locales hardcodeadas en componentes |
| Agregar esquema OpenAPI y versionar API | Frontend y backend validan un contrato único |
| Corregir endpoints desalineados | Guardados, likes, stats, carrito y pagos cubiertos por tests |
| Crear manifiesto Python y CI | Instalación limpia, checks, tests y build reproducibles |
| Agregar suite crítica | Permisos, agenda, stock, pagos y automatizaciones cubiertos |
| Consolidar migraciones | Base vacía y upgrade validado automáticamente |

### P3 - Mantenibilidad y operación

| Acción | Criterio de salida |
|---|---|
| Dividir archivos por subdominio | Views y services con responsabilidades acotadas |
| Eliminar duplicados y código de demo | Una implementación por campana, stats, servicio y checkout |
| Implementar observabilidad | Logs estructurados, error tracking, métricas y alertas |
| Diseñar backups y media privada | Restauración probada y comprobantes no públicos |
| Completar reportes y RNF | Métricas correctas, accesibilidad y rendimiento medidos |

Orden recomendado: seguridad y permisos, integridad de turnos, integridad de stock/pagos, automatizaciones, contratos, pruebas, despliegue y recién después nuevas funcionalidades.

## 27. Conclusión y preparación para producción

Bohemia Hair posee una base funcional extensa y evidencia de trabajo sobre casi todos los objetivos del documento de requisitos. El valor principal está en el modelo de dominio, la cantidad de flujos representados y la existencia de interfaces tanto para cliente como para administración.

El problema central no es falta de funcionalidades, sino falta de consolidación. Existen varias implementaciones de los mismos procesos, permisos que no representan los roles del negocio, invariantes que se validan solo en algunas rutas y automatizaciones que pueden repetirse sin control.

### Evaluación final

| Dimensión | Evaluación |
|---|---|
| Cobertura funcional | Alta en código, parcial en cierre de flujos |
| Arquitectura | Adecuada para monolito, baja modularidad interna |
| Seguridad | Insuficiente |
| Integridad de datos | Insuficiente en agenda, stock y pagos |
| Automatización | Amplia pero inestable/no orquestada |
| Pruebas | Insuficientes |
| Operación/despliegue | No preparado |
| Documentación de requisitos | Amplia, con contradicciones frente al código actual |
| Preparación para producción | No apto |

### Condiciones mínimas para una versión candidata

- Cero hallazgos P0 abiertos.
- Flujos de turno y orden expresados como máquinas de estado autorizadas e idempotentes.
- Reservas y stock protegidos contra concurrencia.
- Integración Mercado Pago validada en sandbox con retornos frontend completos.
- Dependencias, variables, migraciones y despliegue reproducibles.
- Backups y protección de media definidos.
- Suite automática de permisos, agenda, stock, pagos y migraciones ejecutada en CI.
- Revisión del documento de requisitos para decidir si la venta es externa por WhatsApp, interna por Mercado Pago o ambas con límites claros.

Hasta cumplir esas condiciones, el sistema debe considerarse un desarrollo avanzado de entorno controlado y no una aplicación lista para manejar agenda, datos técnicos, comprobantes y pagos reales.
