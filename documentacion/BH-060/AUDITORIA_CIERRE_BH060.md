# Auditoría consolidada de cierre BH-060

**Fecha:** 2026-11-06

**Commit auditado:** `1531f692b11bfae25817ef94d1e9822b4c782102`

**Rama:** `save/work-in-progress`

**Modalidad:** análisis estático, ejecución real sobre PostgreSQL y revisión documental.

**Alcance:** BH-060 Incrementos 1–7. No se modificó código, tests, migraciones,
configuración, datos de aplicación ni backlog; no se hizo commit ni push.

## 1. Resumen ejecutivo

La implementación corrigió y prueba la mayoría de los riesgos que originaron
BH-060. La auditoría reprodujo satisfactoriamente:

- **1.068/1.068 tests backend** en siete bloques disjuntos;
- **64/64 tests concurrentes PostgreSQL**, incluidos una sola vez en ese total;
- **289/289 tests frontend**;
- dos ejecuciones controladas `--keepdb`, ambas **6/6**;
- `check`, `makemigrations --check --dry-run`, `migrate --check` y build frontend.

La suite tiene valor de regresión real: prueba permisos efectivos, grants
individuales, grupos, `is_staff` contrario, ownership, estados, habilidades,
idempotencia, locks y ausencia de mutación en una cantidad significativa de
rechazos. No depende de datos de desarrollo para sus tests.

No obstante, **BH-060 todavía no satisface todos sus criterios de cierre**:

1. **Severidad alta — agenda:** el CRUD y las acciones masivas de la ruta activa
   `/api/gestion/horariolaboral/` dependen sólo de `IsAdminUser`, es decir, de
   `is_staff` (`gestion/views.py:4454-4464`; registro en
   `gestion/urls.py:39`). Un staff sin permiso de negocio puede cambiar horarios
   y un ADMINISTRADOR efectivo sin `is_staff` no puede hacerlo.
2. **Severidad alta — requisitos técnicos/equipamiento:**
   `/api/gestion/requisitos-servicio/` conserva
   `[IsAuthenticated, IsAdminUser]` para CRUD
   (`gestion/views.py:4897-4909`; `gestion/urls.py:102`). No existe una matriz
   API directa de positivo por permiso efectivo, negativo para staff sin permiso
   y cero mutación.
3. **Severidad media — productos/storage:** `/api/gestion/upload-imagen/` escribe
   archivos con sólo `IsAdminUser` (`gestion/views.py:352-400`;
   `gestion/urls.py:148-149`) y tampoco tiene tests de autorización directos.
4. **Severidad alta para el cierre contractual — CI:** no existe
   `.github/workflows` ni otra automatización. La matriz sigue dependiendo de
   ejecución manual, en contradicción literal con el criterio 14.

Los tres primeros hallazgos también impiden afirmar el criterio 1 para **cada**
operación y contradicen el criterio 7. Por ello, el resultado obligatorio es:

> **BH-060 = BLOQUEADO PARA CIERRE**

Esto no invalida los siete incrementos ni los 1.068 tests aprobados; identifica
un cierre incompleto en superficies activas que quedaron fuera de esa matriz.

## 2. Baseline y método

### 2.1 Integridad del baseline

- `HEAD`, upstream y `origin/save/work-in-progress` coincidían con
  `1531f692b11bfae25817ef94d1e9822b4c782102` al iniciar la auditoría.
- La rama no avanzó durante la ejecución.
- Ya existía una modificación local ajena en
  `bohemiacore/bohemiacore/settings.py`: una sustitución del mapping `NAME` de
  base de datos. Se preservó sin mostrar su valor. También se preservaron todos
  los documentos, media, Cypress y `show_urls.py` no rastreados.
- `bohemiacore.test_settings` fija por separado `TEST.NAME`, exige prefijo
  `test_` y usa `StablePostgresTestRunner`; por ello la modificación local del
  nombre de la base normal no eligió la base de los tests. Sí determina qué base
  configurada inspeccionó el comando de sólo lectura `migrate --check`.
- `git diff --check` terminó con código 0; sólo informó el warning de conversión
  CRLF/LF del `settings.py` local preexistente.

### 2.2 Método

1. Se recuperaron los 14 criterios de
   `ANALISIS_BH060_TESTS_PERMISOS_POR_ROL.md:346-371`.
2. Se contrastaron informes 1–7 con rutas registradas, permisos, servicios,
   ModelAdmin y tests reales; el texto `VALIDADO` no se tomó como evidencia.
3. Se clasificaron los usos de `AllowAny`, `IsAuthenticated` e `IsAdminUser`
   según la operación activa. Por ejemplo, el webhook público autentica firma en
   el servicio y las solicitudes financieras de owner validan ownership dentro
   del servicio; no se marcaron como bypass por coincidencia textual.
4. Se ejecutó literalmente la partición oficial de BH-060.7, secuencialmente,
   sin `--parallel`, con base nueva y destruida por bloque. El bloque concurrente
   se ejecutó solo.
5. Los logs se guardaron fuera del repositorio en
   `C:\Users\AldoA\AppData\Local\Temp\opencode\bh060-audit-*.log`.

### 2.3 Autoridad nominal y efectiva

`usuarios/roles.py:88-118` define estos grants base:

| BusinessRole | Permisos base relevantes |
|---|---|
| CLIENTE | Ninguno; actúa por identidad y ownership de su perfil. |
| EMPLEADO | clientes walk-in/lectura, agenda global, alta/reprogramación/cancelación de Turnos, llegada, `register_payment`, `view_stock`. |
| PROFESIONAL | Los de EMPLEADO salvo `register_payment`, más diagnóstico, ficha, fórmulas, rutinas, finalización y revisión técnica. |
| ADMINISTRADOR | Todos los `BusinessPermission`. |

El rol nominal no basta cuando hay requisitos adicionales. La autoridad se
calcula con `has_perm`, puede provenir de rol, permiso individual o grupo
técnico, y en operaciones técnicas se combina con cuenta/Personal activo,
habilidad y ownership. `is_staff` sólo debe abrir Django Admin, no conceder
autoridad de negocio en API.

## 3. Matriz de los 14 criterios de cierre

| # | Requisito | Código/servicio y pruebas | Resultado de auditoría | Cobertura faltante / riesgo residual | Veredicto |
|---:|---|---|---|---|---|
| 1 | Cada operación: positivo por permiso efectivo, negativo sin permiso y `is_staff` contrario. | Permisos en `gestion/permissions.py`, `usuarios/permissions.py`; matrices BH-060.1–.6 y bloques 1–6. | Las superficies cubiertas prueban los tres ejes y aprobaron. | HorarioLaboral, RequisitoServicio y upload no tienen matriz directa y siguen usando `IsAdminUser`. | **PARCIAL** |
| 2 | Ownership: owner/tercero en list, detail y acciones. | Querysets/servicios de Turno, ficha, RutinaCliente, órdenes, solicitudes e incidencias; `test_turno_read_authorization_api`, `test_technical_record_formula_routine_permissions_bh060_3`, `test_order_inventory`, `test_financial_resolution`. | Owner y tercero, ocultamiento y acciones personalizadas aprobaron; rechazos no mutan. | No se halló bypass de ownership activo en el alcance. | **CUMPLE** |
| 3 | Operaciones técnicas: habilidad ausente/inactiva, Personal inactivo y cuenta inactiva. | `user_has_active_skill`, permisos técnicos y filtros; `test_diagnosis_authorization_api`, BH-060.3, `test_state_residual_aliases_bh060_6`, `test_turno_skill_compatibility`. | Los cuatro estados y ausencia de filas nuevas aprobaron. | Un access token anterior puede volver a servir después de reactivar la cuenta; no elude el estado mientras está inactiva. | **CUMPLE** |
| 4 | Cambio de rol: pérdida inmediata, caché, permiso individual y grupo técnico. | `assign_business_role` limpia caches; servicios BH-059; `test_bh059_c_*`, `test_state_residual_aliases_bh060_6`. | Pérdida inmediata en instancia actual/nueva y requests; grant/revoke individual y grupo técnico aprobados. | Riesgo de token tras reactivación, no de caché de permisos. | **CUMPLE** |
| 5 | Último administrador secuencial y concurrente. | Servicios con locks de BH-059; `test_bh059_c_role_change_services` y `test_bh059_c_business_role_concurrency`. | Casos secuenciales y carrera PostgreSQL aprobaron. | Ninguno material en el alcance. | **CUMPLE** |
| 6 | Caja, pagos, refunds, ajustes y cierres: permisos separados y cero mutación al rechazo. | Servicios de PaymentIntent, pagos, conciliación, ajustes, refund y cierre; bloque 5 y concurrentes. | 170/170 funcionales y sus concurrentes aprobaron; PROFESIONAL base carece de `register_payment`; staff no lo reemplaza. | Writer ORDER legacy sigue separado del grafo PaymentIntent, aunque endurecido. | **CUMPLE** |
| 7 | Ninguna escritura sensible depende sólo de `AllowAny`, `IsAuthenticated` o `is_staff`. | Las superficies corregidas usan permisos efectivos. | Catálogos, bloqueos, equipamiento, configuración, rutinas, ficha y fórmulas corregidos. | HorarioLaboral y RequisitoServicio dependen de `IsAdminUser`; upload también. Son rutas activas y mutables. | **NO CUMPLE** |
| 8 | Django Admin: contención HTTP de acceso, inventario y finanzas. | Mixins/ModelAdmin de `gestion/admin.py` y `usuarios/admin.py`; `test_django_admin_security_bh060_5`, `test_admin_usuario_crud_containment`. | Los 35 ModelAdmin, puertas técnicas, permisos de modelo/negocio, inmutabilidad y ausencia de bulk delete aprobaron. | Django Admin conserva `is_staff` como puerta técnica por diseño, no como autoridad suficiente. | **CUMPLE** |
| 9 | Aliases legacy cerrados o delegados al mismo servicio/invariantes. | Agenda comparte resolver; selección de Rutina comparte helper; `payments/pagos` comparte ViewSet; orden legacy delega a `register_legacy_order_payment`; tests BH-060.2/.3/.6. | Equivalencia, ownership, estados, idempotencia y pérdida de acceso aprobaron. | Mantener plan de retiro del pago ORDER legacy. | **CUMPLE** |
| 10 | PostgreSQL limpio y `--keepdb` documentado, sin contaminación. | `test_settings.py`, `test_runner.py:18-116`, `test_test_harness`. | Cada bloque creó/destruyó base; dos reutilizaciones controladas 6/6. | La primera corrida auditada con `--keepdb` encontró la base de test ya existente, la verificó/reparó y la preservó; no era una base de aplicación. | **CUMPLE** |
| 11 | Concurrencia aislada y determinista. | 17 etiquetas `TransactionTestCase`, locks e invariantes. | 64/64 en proceso único, sin otros tests ni `--parallel`. | Los códigos terminales válidos dependen del ganador, pero se prueba un único efecto final. | **CUMPLE** |
| 12 | Flags legacy: rechazo estricto sin debilitar serializer. | `DiagnosisAuthorizationApiTests.test_legacy_flags_are_read_only_in_personal_serializer`. | Incluido en bloque 2; 155/155. Comprueba campos, código/mensaje y cero mutación. | Aserciones de texto exacto son algo frágiles, pero expresan el contrato vigente. | **CUMPLE** |
| 13 | Sin logging masivo y con presupuesto/timeout por bloque. | Backend usa `--buffer`; BH-060.7 documenta duraciones y partición. | Backend no emitió ruido de casos aprobados. | Frontend aún emite varios `console.error`, warnings `act(...)` y logs simulados; el presupuesto está documentado, pero no hay timeout automatizado en repositorio. | **PARCIAL** |
| 14 | Matriz automatizada en CI, no manual. | BH-060.7 sólo propone un workflow. | No existe `.github/workflows` ni configuración CI equivalente. | Una regresión sólo se detecta si alguien ejecuta manualmente la matriz de aproximadamente 52 minutos en este equipo. | **NO CUMPLE** |

**Balance:** 10 CUMPLE, 2 PARCIAL y 2 NO CUMPLE. Los criterios son
acumulativos; una suite verde no compensa los criterios 7 y 14.

## 4. Matriz final de permisos por rol y módulo

Leyenda: **propio** = limitado por ownership; **efectivo** = `has_perm`, no el
nombre del rol; **técnico** = además cuenta/Personal/habilidad activos.

| Módulo | Permiso Django efectivo / regla | CLIENTE | EMPLEADO | PROFESIONAL | ADMINISTRADOR | Evidencia, `is_staff` y estado final |
|---|---|---|---|---|---|---|
| 1. Usuarios, Cliente y Personal | `create_walkin_client`, `view_clients`, `manage_users`, `assign_roles`, `manage_personal`, `manage_skills`; comandos semánticos para rol/estado. | Alta pública controlada, sesión y perfil propio. | Walk-in/lectura según grants base. | Igual base laboral. | Administración completa por permisos, con protecciones de self, superuser y último admin. | Bloque 1, 411/411. Staff sin permisos no administra; admin efectivo sin staff sí usa API. Estados y residuos cubiertos. **CUMPLE**. |
| 2. Diagnóstico y ficha técnica | `create_diagnosis`, `manage_technical_record`; habilidad `DIAGNOSTICO`, Personal activo, profesional asignado y ownership. | Lee sólo diagnóstico/ficha propios; no escribe. | Sin autoridad base; un grant requiere además requisitos técnicos. | Crea/gestiona sólo con skill/estado/ownership. | Tiene grants, pero la operación técnica sigue requiriendo Personal/skill cuando corresponde. | Bloque 2. Positivos/negativos, staff contrario, cuenta/Personal/skill y cero mutación. **CUMPLE**. |
| 3. Fórmulas y rutinas | `manage_formulas` + skill; `assign_routines`; selección propia por Cliente activo. | Ve publicadas, selecciona copia propia; no inyecta target. | Sólo lectura autenticada publicada salvo grant. | Fórmulas y asignación por permisos; ownership de copias. | Administración por permisos efectivos. | BH-060.3 prueba separación ficha/fórmula, payload atómico, draft, duplicado y owner/tercero. Staff solo es rechazado. **CUMPLE**. |
| 4. Agenda, bloqueos y turnos | `view_global_agenda`, `create_turno_for_client`, `register_arrival`, `reprogram_any_turno`, `cancel_any_turno`; bloqueo: `manage_configuration`; agenda propia por Personal activo. | Turnos propios y disponibilidad pública; no agenda ajena. | Agenda global y gestión operativa base. | Agenda global y propia, con skill en operaciones técnicas. | Todos los permisos base. | Bloques 1, 3 y 7 cubren aliases, owner, estados, no mutación y carreras. **Brecha:** HorarioLaboral CRUD/masivos usa sólo `is_staff`. **NO CUMPLE íntegramente**. |
| 5. Servicios, catálogos y equipamiento | Lectura pública limitada; escritura de catálogos/equipamiento: `manage_configuration`; Servicio: `manage_prices` o fórmula según campo. | Lectura pública/activa. | Lectura; sin escritura base. | Lectura y fórmulas con skill, no precios/config por rol solo. | Escritura por permisos efectivos. | BH-060.1 prueba anónimo, roles, grant individual sin staff, staff sin grant y borrado seguro. **Brecha:** RequisitoServicio CRUD usa sólo `is_staff` y carece de test API directo. **PARCIAL**. |
| 6. Productos, precios, stock y órdenes | `manage_products`, `manage_prices`, `view_stock`, `manage_stock`; órdenes por owner o `manage_stock`. | Catálogo/orden propia, checkout propio. | `view_stock`; no muta stock sin grant. | `view_stock`; no muta stock sin grant. | Gestión completa por capacidades. | Inventario/órdenes prueban locks, idempotencia, compromisos, auditoría y staff contrario. **Brecha:** upload de imagen de producto usa sólo `is_staff`; no hay test directo. **PARCIAL**. |
| 7. Caja, pagos e incidencias | `register_payment`, `view_financial_reports`, `reconcile_external_payment`, y permisos semánticos de ajustes/refund/cierre. | Historial/checkout y solicitud propia reducida; no decide. | `register_payment` base, sin conciliación/reportes por ese solo grant. | **No** tiene `register_payment` base; sin grant individual no cobra. | Todos, pero cada comando exige su permiso exacto. | Bloques 5/7: separación, staff contrario, privacidad, idempotencia, rollback, cero Pago/stock/evento de éxito al rechazo. **CUMPLE**. |
| 8. Configuración, dashboards y reportes | `manage_configuration`, `view_reports`, `view_financial_reports`; proyecciones separadas. | Sólo configuración pública mínima. | Sin acceso base. | Sin acceso base. | Acceso por grants, aun sin staff. | Ruta activa `stats` usa `CanViewGeneralOrFinancialReports`; admin dashboard usa `CanViewReports`. BH-060.4 prueba exclusión de datos y no mutación. **CUMPLE**. |
| 9. Auditoría y Django Admin | API: `view_audit`/`revert_audit`; Admin: cuenta activa + `is_staff` + permiso de modelo + capacidad de negocio; modelos técnicos superuser-only o read-only. | Sin acceso. | Sin acceso base. | Sin acceso base. | API por permisos; Admin sólo si además recibe puerta técnica/model perms. | 35 ModelAdmin inventariados; grupos/permisos no expuestos, acceso/finanzas inmutables, stock no forjable y bulk delete deshabilitado. **CUMPLE**. |

### 4.1 Usos públicos o autenticados que no son bypass

- Los catálogos/servicios públicos exponen sólo lectura/proyección activa; sus
  escrituras cambian a permisos efectivos.
- `WebhookMercadoPagoView` usa `AllowAny` porque autentica la firma y persiste un
  inbox sin ejecutar efectos financieros en esa petición.
- Checkout y carrito usan `IsAuthenticated`, pero los servicios validan actor,
  ownership, estado e idempotencia.
- Solicitudes de resolución/cancelación financiera usan `IsAuthenticated` para
  que el owner solicite; las decisiones, refunds y cierres exigen
  `reconcile_external_payment` de forma independiente.
- Agenda legacy usa `IsAuthenticated` externamente, pero
  `_resolve_legacy_agenda_scope` aplica `view_global_agenda`, ownership y estado.

### 4.2 Dependencias indebidas pendientes

| Ruta activa | Operación sensible | Puerta actual | Problema |
|---|---|---|---|
| `/api/gestion/horariolaboral/` y acciones `configurar_rango`/`limpiar_agenda` | CRUD y mutación masiva de horarios | `IsAdminUser` | `is_staff` concede negocio y bloquea al grant efectivo no staff. |
| `/api/gestion/requisitos-servicio/` | CRUD de requisitos técnicos/equipamiento por Servicio | `IsAuthenticated + IsAdminUser` | Mismo acoplamiento a staff; sin matriz API de no mutación. |
| `/api/gestion/upload-imagen/` | Escritura en storage para productos | `IsAdminUser` | No exige `manage_products`; sin prueba directa de autorización. |

El archivo `gestion/views/stats_views.py` también contiene un ViewSet antiguo
con `IsAdminUser`, pero **no es la clase registrada**: `gestion/urls.py:22`
importa `gestion/stats_views.py`, cuya clase activa exige permisos de reporte.
No se contabiliza el archivo no conectado como bypass activo.

## 5. Estado de los riesgos originales

| Riesgo original | Evidencia efectiva | Estado |
|---|---|---|
| CRUD anónimo de catálogos | Mixins de lectura pública/escritura `manage_configuration`; BH-060.1 prueba todos los verbos y cero mutación. | **RESUELTO** |
| Equipamiento modificable por cualquier autenticado | Lectura autenticada y escritura `manage_configuration`; soft delete/referencias probados. | **RESUELTO**, salvo RequisitoServicio relacionado. |
| Agenda general legacy sin `view_global_agenda` | Resolver común aplica permiso global u ownership/Personal activo; alias/canónica probados. | **RESUELTO** |
| Bloqueos con autorización insuficiente | `crear_bloqueo` exige `manage_configuration`, target explícito, conflicto y atomicidad. | **RESUELTO** |
| Ficha y fórmulas con `IsAdminUser` | Permisos separados, skill, estado, asignación y ownership. | **RESUELTO** |
| Rutinas sin `assign_routines` | Catálogo/asignación administrativa exigen permiso; selección cliente se limita a copia propia publicada. | **RESUELTO** |
| Configuración sin `manage_configuration` | ViewSets y reglas usan permiso efectivo; pública es mínima y no crea singleton. | **RESUELTO** |
| Dashboards sin `view_reports` | Dashboard operativo y stats activos exigen permisos generales/financieros y separan proyecciones. | **RESUELTO** |
| Riesgos de Django Admin | Doble/triple puerta, modelos sensibles inmutables, modelos técnicos restringidos y acciones masivas contenidas. | **RESUELTO** |
| Estado, caché y permisos residuales | Cambio de rol limpia caches; grant/revoke, grupos, cuenta/Personal inactivos y JWT durante baja probados. | **RESUELTO CON RIESGO DE TOKEN** |
| Aliases legacy sensibles | Agenda/Rutina/pagos comparten resolver, helper o ViewSet; acciones de orden delegan en servicios semánticos. | **RESUELTO** |
| Registro de pagos de órdenes | `register_legacy_order_payment` exige `register_payment`, actor activo, estado pagable, saldo, key, locks e idempotencia; audita una vez. | **RESUELTO CON DEUDA DE RETIRO** |

### Hallazgo adicional de esta auditoría

La documentación de BH-060.2 dejó fuera cambios generales de horarios. La ruta
activa HorarioLaboral siguió dependiendo de `IsAdminUser`; BH-060.7 no la incluyó
en una matriz API específica. Es una brecha de alcance que ahora viola de forma
directa los criterios 1 y 7. RequisitoServicio y upload presentan el mismo patrón.

## 6. Evidencia de pruebas backend y frontend

### 6.1 Comando común backend

Desde `bohemiacore/`, cada bloque usó las etiquetas exactas de
`IMPLEMENTACION_BH060_7_ESTABILIZACION_TESTS.md:124-252`:

```powershell
..\venv\Scripts\python.exe -X utf8 manage.py test <etiquetas-del-bloque> `
  --settings=bohemiacore.test_settings --verbosity 1 --buffer --noinput
```

Las listas no se alteraron:

- **B1:** las 36 etiquetas desde `usuarios.test_roles` hasta
  `gestion.tests.test_audit_middleware` (BH-060.7:127-158).
- **B2:** las 10 etiquetas de diagnóstico, skills, ficha, fórmulas, rutinas y
  riesgo técnico (BH-060.7:164-174).
- **B3:** las 9 etiquetas de booking, agenda legacy, HOLD y Turnos
  (BH-060.7:180-189).
- **B4:** las 4 etiquetas de catálogos, inventario y órdenes
  (BH-060.7:195-199).
- **B5:** las 13 etiquetas financieras desde pagos manuales hasta refunds
  (BH-060.7:205-217).
- **B6:** las 4 etiquetas de Admin, auditoría, configuración y reportes
  (BH-060.7:223-228).
- **B7:** las 17 etiquetas concurrentes (BH-060.7:234-252), ejecutadas aparte.

Los logs temporales contienen la invocación expandida completa. Los bloques son
disjuntos; no se sumaron las dos corridas `--keepdb` ni los checks.

### 6.2 Resultado backend auditado

| Bloque | Ejecutados | Aprobados | Fallos/errores | Duración pared | Base | Log |
|---|---:|---:|---:|---:|---|---|
| 1. Roles, Usuario, Personal y permisos | 411 | 411 | 0 | 820,61 s | `test_bohemia_hair_bh060`, creada/destruida | `bh060-audit-block1.log` |
| 2. Diagnóstico, ficha y rutinas | 155 | 155 | 0 | 234,71 s | misma denominación, nueva | `bh060-audit-block2.log` |
| 3. Agenda, turnos y CU-27 | 152 | 152 | 0 | 324,74 s | nueva | `bh060-audit-block3.log` |
| 4. Catálogos, inventario y órdenes | 74 | 74 | 0 | 121,97 s | nueva | `bh060-audit-block4.log` |
| 5. Caja, pagos e incidencias | 170 | 170 | 0 | 806,85 s | nueva | `bh060-audit-block5.log` |
| 6. Django Admin y auditoría | 42 | 42 | 0 | 222,37 s | nueva | `bh060-audit-block6.log` |
| 7. Concurrencia PostgreSQL aislada | 64 | 64 | 0 | 559,74 s | nueva, proceso único | `bh060-audit-block7-concurrency.log` |
| **Total único** | **1.068** | **1.068** | **0** | **3.090,99 s** | PostgreSQL | — |

El backend informó `System check identified no issues`. PowerShell presentó
líneas nativas de stderr como `NativeCommandError` al crear/destruir la base,
pero cada proceso terminó con exit code 0 y Django informó `OK`; no es un error
de test.

### 6.3 Frontend y build

Comandos ejecutados desde `frontend/`:

```powershell
$env:CI = 'true'
npm test -- --watchAll=false --runInBand
npm run build
```

| Ejecución | Resultado | Duración pared | Advertencias |
|---|---:|---:|---|
| Jest, 34 suites | **289/289**, 34/34 suites, exit 0 | 78,89 s | `act(...)`, `console.error` de escenarios simulados y dos `console.log` de Turnos. |
| Build | **OK**, exit 0 | 89,48 s | dependencia dinámica, Browserslist desactualizado, deprecación Node y ESLint preexistente. |

Los warnings no ocultaron fallos, pero justifican el **PARCIAL** del criterio 13
y no deben interpretarse como habilitación de producción.

### 6.4 Calidad de la suite

**Fortalezas verificadas**

- Aserta contratos HTTP y efectos de negocio, no sólo métodos internos.
- Incluye positivos, negativos, `is_staff` contrario y grants individuales.
- Comprueba conteos, estados, stock, Pagos, Auditoria y eventos después de
  rechazos; varias pruebas fuerzan rollback ante fallo de auditoría.
- Separa `TestCase`/`APITestCase` de carreras `TransactionTestCase`.
- Controla HOLD en la frontera de microsegundo, usa `timezone.localdate()` y fija
  reloj frontend donde es sensible.
- Prueba locks e idempotencia con conexiones PostgreSQL reales.
- El runner restaura sólo roles/habilidades canónicos y rechaza bases sin prefijo
  `test_` o distintas de `TEST.NAME`.

**Fragilidad o cobertura insuficiente**

- No hay tests API directos para HorarioLaboral, RequisitoServicio y upload.
- Algunas aserciones fijan mensajes exactos; cambios de copy pueden romperlas sin
  cambiar seguridad.
- Frontend conserva actualizaciones asíncronas fuera de `act(...)` y salida de
  consola abundante.
- La matriz completa tarda cerca de 52 minutos de pared en este equipo, lo que
  aumenta el incentivo a omitirla mientras no exista CI.
- Existe duplicación razonable entre tests de servicio y API, pero captura capas
  distintas; no se detectaron tests vacíos en la muestra focalizada.

## 7. Evidencia de concurrencia y `--keepdb`

### 7.1 Concurrencia

- Comando: el comando común con las 17 etiquetas de BH-060.7 bloque 7.
- Base: PostgreSQL `test_bohemia_hair_bh060`, creada y destruida por Django.
- Aislamiento: sin `--parallel`, sin otro proceso contra el mismo nombre.
- Resultado: **64/64**, exit 0, 559,74 s de pared.
- Invariantes: último administrador, un ganador en bloqueos/HOLD, stock y
  compromisos, idempotencia de pagos/provider, resolución, refunds y eventos.

### 7.2 Reutilización controlada

Se eligió un nombre separado y seguro:

```powershell
$env:BH_TEST_DB_NAME = 'test_bohemia_hair_bh060_audit'
..\venv\Scripts\python.exe -X utf8 manage.py test `
  gestion.tests.test_test_harness `
  --settings=bohemiacore.test_settings --verbosity 1 --buffer --keepdb --noinput
```

| Corrida | Resultado | Duración | Evidencia |
|---|---:|---:|---|
| 1, base preservada existente | **6/6**, exit 0 | 80,73 s | Verificó/reparó seeds, preservó base; `bh060-audit-keepdb-1.log`. |
| 2, reutilización inmediata | **6/6**, exit 0 | 16,59 s | Mismos contratos y seeds; `bh060-audit-keepdb-2.log`. |

La base sólo se usó como base de test y no se borró manualmente. La referencia
limpia ya quedó ejercida dentro del bloque 1, que incluyó esos seis tests después
de crear la base desde cero.

## 8. Seguridad de Django Admin y aliases

### 8.1 Django Admin

La evidencia estática y `test_django_admin_security_bh060_5` confirman:

- `is_staff` es únicamente la puerta técnica del sitio;
- cada changelist funcional exige permiso de modelo y capacidad de negocio;
- un ADMINISTRADOR de negocio sin staff no entra al sitio, y un staff sin
  capacidad no obtiene el dominio;
- Usuario, Cliente, Personal, rol, último admin y superuser no pueden forjarse
  con formularios genéricos;
- Configuracion, Orden, Auditoria y objetos financieros son inmutables o no están
  expuestos por escritura genérica;
- stock no puede forjarse desde Producto;
- Group/Permission no están registrados; tokens son técnicos e inmutables;
- acciones masivas peligrosas están deshabilitadas.

Resultado auditado: bloque 6 **42/42**, incluido el inventario de **35
ModelAdmin**. No se halló un bypass nuevo de Django Admin.

### 8.2 Aliases

| Familia | Canónica / alias | Resultado |
|---|---|---|
| Agenda | `turnos` / `agenda/general` y calendario | Misma autoridad global/propia y estado; probado. |
| Rutina propia | `rutinas/seleccionar` / `prueba-rutina` | Mismo helper, payload cerrado, publicada/owner; probado. |
| Lectura de pagos | `payments` / `pagos` | Mismo `PagoViewSet`; pierde acceso tras degradación; probado. |
| Orden pendiente | acciones legacy | Pago en OrdenPendiente está cerrado; confirmar/cancelar delegan en servicios de inventario. |
| Pago de OrdenCompra | `registrar_pago` legacy | Delega en `register_legacy_order_payment`; permiso, actor activo, lock, saldo, estados, key, retry y evento único. |

El writer de OrdenCompra permanece por compatibilidad, separado de
PaymentIntent. No es un bypass actual, pero su consumidor y retiro deben
confirmarse antes de producción.

## 9. Riesgos residuales y deuda técnica

### 9.1 Seguridad de cambios de rol y estado

- **Último administrador:** protegido secuencial y concurrentemente.
- **Autoescalamiento/autoacción:** bloqueados por servicios semánticos.
- **Superusuarios:** objetivos protegidos.
- **Residuos:** la degradación rechaza capacidades administrativas residuales;
  los grupos técnicos no canónicos permitidos se preservan deliberadamente.
- **Permisos individuales/grupos:** grants y revokes se reflejan en requests
  nuevos; el rol nominal no reemplaza `has_perm`.
- **Caché:** se limpian `_perm_cache`, `_user_perm_cache` y
  `_group_perm_cache`; probado en instancia cargada y nueva.
- **Cuenta/Personal:** inactividad cierra APIs y agenda propia; una habilidad
  inactiva no se evita con grant individual.
- **Sesiones/tokens:** un access token emitido antes de la baja deja de autenticar
  mientras la cuenta está inactiva.
- **Riesgo preservado:** si la cuenta se reactiva antes de que venza, ese access
  token anterior puede recuperar validez. No hubo cambio de autenticación en
  BH-060; permanece como riesgo explícito.

### 9.2 Checks de seguridad y operación

| Comando/revisión | Resultado | Clasificación |
|---|---|---|
| `manage.py check --settings=bohemiacore.test_settings` | 0 issues, 5,82 s | Conforme para tests. |
| `makemigrations --check --dry-run` | `No changes detected`, 5,66 s | Sin migraciones de modelo faltantes. |
| `migrate --check` | exit 0, 5,32 s | Sin migraciones pendientes en la base configurada inspeccionada; sólo lectura. |
| `git diff --check` | exit 0; warning CRLF del settings local | Sin errores de whitespace introducidos. |
| Escaneo heurístico de 652 paths tracked | 0 private keys, 0 AWS keys, 0 GitHub tokens, 0 asignaciones genéricas en código productivo | 115 coincidencias de password en tests y 3 en formularios frontend; dos `.doc` binarios no se leyeron. No sustituye un secret scanner dedicado. |
| `manage.py check --deploy` | exit 0 con 6 warnings | No listo para producción: HSTS, SSL redirect, calidad de SECRET_KEY, cookies session/CSRF seguras y DEBUG. No se imprimió ningún secreto. |

Los warnings de despliegue son distintos del cierre técnico de BH-060. No se
debe cambiar `settings.py` dentro de esta auditoría ni declarar producción
habilitada por la suite verde.

### 9.3 Deuda priorizada

1. Sustituir `IsAdminUser` en HorarioLaboral por permiso de negocio efectivo y
   agregar matriz API completa.
2. Hacer lo mismo para RequisitoServicio.
3. Proteger upload de productos con `manage_products` (y conservar validaciones
   de tipo/tamaño), con no mutación de storage al rechazo.
4. Automatizar la matriz en CI con PostgreSQL y jobs sin compartir base.
5. Limpiar warnings `act(...)`, logs y build sin confundirlo con el bloqueo de
   autorización.
6. Evaluar revocación/rotación de access tokens al reactivar en una tarea de
   autenticación separada.

## 10. Pendientes para BH-061, BH-062 y producción

### BH-061 — historial y forense

Fuera de BH-060: historial visual unificado, consultas temporales, exportación,
retención y correlación avanzada. La API actual de auditoría sí conserva
permisos de lectura/reversión y contención en Admin.

### BH-062 — UX administrativa

Fuera de BH-060: interfaces avanzadas para roles/capacidades, explicaciones de
denegación, navegación y experiencia de administración. No debe usarse BH-062
para posponer la corrección de permisos backend de las tres rutas activas.

### Producción

Antes de producción, además de cerrar BH-060:

- resolver los seis warnings de `check --deploy` con configuración por entorno;
- validar proxy/HTTPS, CORS/CSRF, callbacks, storage y secretos reales;
- usar un secret scanner dedicado y gestión de credenciales;
- confirmar consumidor y retiro del pago ORDER legacy;
- definir política de zona horaria de negocio en frontend;
- definir revocación de JWT tras baja/reactivación;
- monitorear provider, idempotencia, auditoría y recuperación de incidencias.

## 11. Veredicto final

> # BH-060 = BLOQUEADO PARA CIERRE

### Bloqueos exactos y corrección mínima

| Bloqueo | Severidad | Corrección mínima necesaria |
|---|---|---|
| HorarioLaboral usa `IsAdminUser` para CRUD/acciones masivas. | **Alta** | Exigir `IsAuthenticated + CanManageConfiguration` (o capacidad específica aprobada) y tests de grant efectivo no staff, staff sin grant, anónimo, roles, estado y cero mutación. |
| RequisitoServicio usa `IsAdminUser`. | **Alta** | Exigir `manage_configuration` o capacidad específica y la misma matriz positiva/negativa/no mutación. |
| Upload de producto usa `IsAdminUser`. | **Media** | Exigir `manage_products`; probar que el rechazo no crea archivo y que staff no sustituye el permiso. |
| No existe CI para la matriz. | **Alta para cierre** | Agregar workflow con PostgreSQL, bloques 1–6 secuenciales, concurrencia aislada sin `--parallel`, frontend y build; fijar versiones/lockfiles y timeouts. |

**Recomendación concreta:** no cerrar BH-060 todavía. Aplicar únicamente esas
correcciones mínimas en un incremento de cierre, ejecutar otra vez los bloques
afectados más la matriz CI completa y repetir la auditoría focalizada. No es
necesario implementar BH-061, BH-062 ni resolver toda la preparación de
producción para poder cerrar técnicamente BH-060.
