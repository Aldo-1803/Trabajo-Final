# BH-060 — Revalidación final de cierre

## 1. Alcance y veredicto

- **Fecha:** 2026-11-08
- **Rama:** `save/work-in-progress`
- **HEAD inspeccionado:** `13b92311e0d7ae26d7cf0259a1605f2401d5bd4b`
- **Corrección F1:** `dd833b8ac2d9ae30037dda840ada762486f11ea4`
- **Corrección funcional F2:** `3a6640b9cce2345d64e5498b884ed506b44c017d`
- **Actualización documental F2:** `13b92311e0d7ae26d7cf0259a1605f2401d5bd4b`
- **Run verificado:** [42411231934](https://github.com/Aldo-1803/Trabajo-Final/actions/runs/42411231934)
- **Veredicto de revalidación:** `BH-060 = LISTO PARA CERRAR`
- **Estado documental definitivo:** `BH-060 = CERRADO TÉCNICAMENTE`
- **Método:** revisión focal de código y tests, inspección de commits y consulta de
  la API/logs de GitHub Actions. No se repitieron localmente los 1.068 tests cuya
  cobertura está incluida, ampliada y aprobada en el run remoto.

Los cuatro bloqueos de `AUDITORIA_CIERRE_BH060.md` están resueltos:

1. HorarioLaboral usa permisos efectivos y tiene matriz directa;
2. RequisitoServicio usa permisos efectivos y tiene matriz directa;
3. `upload_imagen` usa permiso efectivo y prueba cero escritura al rechazo;
4. existe una matriz CI real, aislada y aprobada para B1–B7, Jest y build.

La revisión actualiza el balance de los criterios originales a **14 CUMPLE, 0
PARCIAL y 0 NO CUMPLE**. Los riesgos de despliegue y de integraciones reales se
mantienen separados y no se reinterpretan como resueltos por esta validación.

> # BH-060 = CERRADO TÉCNICAMENTE

## 2. Integridad del árbol y trazabilidad Git

La relación de ancestros fue verificada:

```text
1531f692...  auditoría original
    |
dd833b8a...  F1: cierre de tres autorizaciones residuales
    |
9138a689...  workflow inicial
    |
3d0a90da...  entorno de build frontend
    |
41d7e29c...  documentación del bloqueo remoto B7 [skip ci]
    |
3a6640b9...  corrección funcional del deadlock y run verde
    |
13b92311...  documentación final F2 [skip ci]
```

- `dd833b8...` es ancestro de `3a6640b...`.
- `3a6640b...` es el padre directo de `13b9231...`.
- El commit F1 modifica sólo su documento, `gestion/permissions.py`,
  `gestion/views.py` y la regresión F1.
- El diff `3a6640b...13b9231` contiene únicamente:
  - `IMPLEMENTACION_BH060_F2_CI_PERMISOS.md`;
  - `IMPLEMENTACION_FIX_DEADLOCK_REFUND_BH060_F2.md`.
- No hay archivos Python, JavaScript, YAML, JSON, dependencias, tests,
  workflows ni configuración ejecutable en ese commit documental.
- Su mensaje contiene `[skip ci]` y la API de Actions no registra un run de
  `push` para el SHA `13b9231...`.

Por tanto, el run verde sobre `3a6640b...` valida exactamente el último árbol
funcional; el commit posterior no cambia aquello que fue ejecutado.

## 3. Revalidación de los cuatro bloqueos

### 3.1 HorarioLaboral

**Código efectivo**

`bohemiacore/gestion/views.py:4468-4485` define:

- autenticación obligatoria;
- `CanViewGlobalAgendaOrManageConfiguration` para `list` y `retrieve`;
- `CanManageConfiguration` para POST, PUT, PATCH, DELETE,
  `configurar_rango` y `limpiar_agenda`.

`bohemiacore/gestion/permissions.py:99-121` calcula ambas capacidades con
`user.has_perm(...)` y cuenta activa. No consulta el nombre del BusinessRole ni
usa `is_staff` como autoridad de negocio.

Las acciones masivas conservan la prevalidación de todos los Personal antes de
escribir y la fase de creación dentro de `transaction.atomic`. Un target
inexistente o inactivo no deja altas parciales.

**Pruebas directas F1**

`test_residual_authorization_closure_bh060_f1.py` cubre:

- positivo con grant individual `manage_configuration` y `is_staff=False`;
- positivo de ADMINISTRADOR efectivo con `is_staff=False`;
- lectura de EMPLEADO y PROFESIONAL por `view_global_agenda`, sin escritura;
- negativos de anónimo, CLIENTE, staff sin permiso, cuenta inactiva con grants,
  EMPLEADO y PROFESIONAL para mutaciones;
- list, detail, POST, PUT, PATCH, DELETE y las dos acciones masivas;
- payloads que intentan inyectar `is_staff`, `is_superuser` y permisos;
- conteos, valores originales y Auditoria sin cambios tras cada rechazo;
- cero altas parciales ante un patrón masivo inválido.

**Resultado:** bloqueo cerrado.

### 3.2 RequisitoServicio

**Código efectivo**

`bohemiacore/gestion/views.py:4945-4957` aplica
`[IsAuthenticated, CanManageConfiguration]` al ViewSet completo. Listado,
detalle, POST, PUT, PATCH y DELETE dependen de `manage_configuration`, no de
`is_staff`.

La validación de negocio sigue exigiendo un TipoEquipamiento con al menos una
instancia activa. Create/update validan antes de persistir y un PATCH inválido
no cambia relaciones ni cantidad.

**Pruebas directas F1**

- grant individual `manage_configuration` sin staff ejecuta CRUD y filtro por
  Servicio;
- ADMINISTRADOR efectivo sin staff accede;
- anónimo, CLIENTE, staff sin permiso, cuenta inactiva, EMPLEADO y PROFESIONAL
  sin grant son rechazados;
- los rechazos conservan conteo, Servicio, TipoEquipamiento, cantidad y
  Auditoria;
- un tipo sin Equipamiento activo retorna 400 sin mutación.

**Resultado:** bloqueo cerrado.

### 3.3 `upload_imagen`

**Código efectivo**

`bohemiacore/gestion/views.py:353-420` exige
`[IsAuthenticated, CanManageProducts]`. `CanManageProducts` usa
`user.has_perm(BusinessPermission.MANAGE_PRODUCTS)`; `is_staff` no concede el
permiso.

Además, la ruta:

- admite sólo JPEG, PNG, GIF y WebP;
- limita el archivo a 5 MiB;
- genera `productos/<uuid>.<extensión derivada del MIME>`;
- no usa nombre o ruta enviados por el cliente;
- elimina el archivo si `storage.url()` falla después del guardado.

**Pruebas directas F1**

- positivo con grant individual `manage_products` y `is_staff=False`;
- positivo de ADMINISTRADOR efectivo sin staff;
- negativos de anónimo, CLIENTE, staff sin permiso y cuenta inactiva con grant;
- separación de capacidades: `manage_configuration` no permite upload y
  `manage_products` no permite horarios/requisitos;
- cero llamadas a `storage.save()` en rechazos de autorización, MIME o tamaño;
- ruta segura generada por servidor ante un nombre malicioso;
- limpieza total cuando falla la obtención de URL.

**Resultado:** bloqueo cerrado.

### 3.4 CI ausente

`.github/workflows/bh060-permisos.yml` implementa:

- disparadores de push, pull request y `workflow_dispatch`;
- `contents: read` como único permiso del token;
- B1–B6 en seis runners con PostgreSQL 16.9 y bases independientes;
- `check` y `makemigrations --check --dry-run` por job backend;
- ejecución sin `--keepdb` y sin `--parallel`;
- B7 en runner, contenedor, base y proceso propios;
- Jest con `--runInBand` y build productivo en un job independiente;
- timeouts por bloque;
- un job global que falla si backend, B7 o frontend no terminan `success`.

Los once casos F1 se distribuyen una sola vez:

- B3: seis casos de autorización general y HorarioLaboral;
- B4: cinco casos de RequisitoServicio y upload.

No se eliminaron las etiquetas originales de BH-060.7.

**Resultado:** bloqueo cerrado.

## 4. Evidencia remota verificada

La API de GitHub devolvió para el run `42411231934`:

| Campo | Valor |
|---|---|
| Evento | `push` |
| Rama | `save/work-in-progress` |
| Head SHA | `3a6640b9cce2345d64e5498b884ed506b44c017d` |
| Estado | `completed` |
| Conclusión | `success` |
| Inicio | 2026-11-07 20:28:41 UTC |
| Fin | 2026-11-07 20:33:09 UTC |

Todos los jobs informaron `completed/success`:

| Job | Evidencia del log | Resultado |
|---|---:|---:|
| B1 — roles, usuarios y Personal | 411/411 | Aprobado |
| B2 — diagnóstico, ficha y rutinas | 155/155 | Aprobado |
| B3 — agenda, turnos y CU-27 + F1 | 158/158 | Aprobado |
| B4 — catálogos, inventario y órdenes + F1 | 79/79 | Aprobado |
| B5 — Caja, pagos e incidencias | 170/170 | Aprobado |
| B6 — Django Admin y auditoría | 42/42 | Aprobado |
| B7 — concurrencia PostgreSQL | 64/64 | Aprobado |
| **Backend único** | **1.079/1.079** | **Aprobado** |
| Frontend | 34/34 suites; 289/289 tests | Aprobado |
| Build frontend | `The build folder is ready to be deployed.` | Aprobado |
| Resultado global BH-060 | dependencias en `success` | Aprobado |

El conteo backend no duplica B7:

```text
B1–B6 = 411 + 155 + 158 + 79 + 170 + 42 = 1.015
B7    = 64
Total = 1.015 + 64 = 1.079
```

Los 64 concurrentes están incluidos exactamente una vez en 1.079. Los 289 tests
frontend y el build son evidencias separadas y no se suman al backend.

### 4.1 Concurrencia B7

El job `128519626550` ejecutó las 17 etiquetas oficiales en un proceso, sin
`--parallel`. Su log contiene:

```text
Found 64 test(s).
Ran 64 tests in 103.227s
OK
```

Incluye la carrera de refunds corregida por `3a6640b...`; no aparece
`deadlock detected`, fallo ni error. No se usaron retries ciegos, sleeps,
serialización artificial o `continue-on-error`.

### 4.2 Decisión de no repetir 1.068 tests

El run remoto ejecutó el mismo árbol funcional original y añadió los once casos
F1, para un total backend de 1.079. Las seis suites funcionales y B7 fueron
creadas desde bases PostgreSQL independientes y aprobaron. Repetir localmente
los 1.068 casos no aportaría una combinación de código o cobertura distinta a
la evidencia remota ya verificada.

## 5. Estado actualizado de los 14 criterios

| # | Criterio original | Evidencia actual | Estado |
|---:|---|---|---|
| 1 | Positivo por permiso efectivo, negativo sin permiso e `is_staff` contrario para cada operación. | La matriz previa se conserva; F1 añade esos ejes para HorarioLaboral, RequisitoServicio y upload, incluidos grants sin staff, staff sin grant, inactivo y anónimo. | **CUMPLE** |
| 2 | Ownership en list, detail y acciones. | Las suites originales de Turno, diagnóstico/ficha, rutinas, órdenes, pagos y resoluciones permanecen en B1–B6 y aprobaron. F1 no debilitó scopes. | **CUMPLE** |
| 3 | Operaciones técnicas con habilidad/Personal/cuenta inactivos. | B2 ejecutó 155/155 sobre skills, diagnóstico, ficha, rutinas y riesgos técnicos. | **CUMPLE** |
| 4 | Pérdida inmediata tras cambio de rol, caché y grants residuales. | B1 conserva servicios/tests de cambio, revocación, instancia actual/nueva, permiso individual y grupo técnico; 411/411. | **CUMPLE** |
| 5 | Último administrador secuencial y concurrente. | Casos funcionales en B1 y carrera dedicada en B7 aprobaron. | **CUMPLE** |
| 6 | Permisos financieros separados y cero mutación al rechazo. | B5 170/170 y sus carreras B7 aprobaron; incluye pago, conciliación, refund, ajuste y cierre. | **CUMPLE** |
| 7 | Ninguna escritura sensible sólo con `AllowAny`, `IsAuthenticated` o `is_staff`. | Las tres excepciones activas de la auditoría ahora exigen `manage_configuration` o `manage_products`; el resto de superficies corregidas conserva permisos efectivos. | **CUMPLE** |
| 8 | Contención HTTP de Django Admin para acceso, inventario y finanzas. | B6 ejecutó 42/42, incluidos inventario de ModelAdmin, puertas técnicas y capacidades de negocio. | **CUMPLE** |
| 9 | Aliases legacy cerrados o delegados al servicio/invariantes canónicos. | Las suites de agenda, rutinas, pagos y órdenes permanecen en B1–B5; carreras de aliases en B7 aprobaron. | **CUMPLE** |
| 10 | PostgreSQL limpio y `--keepdb` documentado sin contaminación. | Cada job backend usó contenedor/base propios y sin `--keepdb`; el runner y las pruebas del harness siguen en B1. La reutilización controlada ya estaba documentada y aprobada. | **CUMPLE** |
| 11 | Concurrencia aislada y determinista. | B7 tuvo runner/base/proceso exclusivos y aprobó 64/64 sin `--parallel`. | **CUMPLE** |
| 12 | Flags legacy rechazados sin debilitar serializer. | El caso estricto permanece en B2, que aprobó 155/155. | **CUMPLE** |
| 13 | Sin logging masivo y con timeout/presupuesto por bloque. | Backend usa `--buffer`; todos los jobs tienen timeout y resumen de duración. Los warnings frontend siguen visibles pero no ocultan resultados ni producen éxito falso. | **CUMPLE** |
| 14 | Matriz automatizada en CI. | Workflow versionado, ejecución automática real y resultado global verde sobre el SHA funcional. | **CUMPLE** |

**Balance final:** **14 CUMPLE, 0 PARCIAL, 0 NO CUMPLE**.

## 6. Observaciones no bloqueantes

- Los warnings preexistentes de Jest/build continúan visibles; no cambiaron el
  exit code ni ocultaron fallos.
- Durante `makemigrations --check`, Django emitió en los logs un warning al no
  poder consultar el historial de migraciones de la base normal
  `bohemia_hair`. Esto no afectó la creación, migración y ejecución contra cada
  `TEST.NAME` aislado ni el check de cambios de modelos. Es una mejora de higiene
  futura del entorno CI, no una brecha de autorización o un fallo de la matriz.
- El pago legacy de Orden sigue siendo deuda de retiro, aunque delega en el
  servicio endurecido y sus invariantes están probadas.
- Un access token emitido antes de una baja puede recuperar validez si la cuenta
  es reactivada antes de su expiración. No concede acceso mientras la cuenta
  permanece inactiva y pertenece a una política futura de revocación.
- El upload valida MIME declarado, tamaño y ruta, pero no firma binaria,
  antivirus o content disarm. Ese hardening corresponde a storage/producción.

Ninguna de estas observaciones reabre uno de los cuatro bloqueos contractuales
de cierre de BH-060.

## 7. Riesgos de producción separados del cierre BH-060

El resultado **LISTO PARA CERRAR** no significa **LISTO PARA PRODUCCIÓN**. Antes
de desplegar deben resolverse o validarse de manera independiente:

### HTTPS y configuración de seguridad

- terminación TLS/proxy y `SECURE_SSL_REDIRECT`;
- HSTS;
- cookies de sesión y CSRF seguras;
- `DEBUG=False`, hosts, CORS y CSRF de cada entorno;
- una `SECRET_KEY` robusta y gestionada fuera del repositorio.

### Secretos y tokens

- secret manager y rotación de credenciales reales;
- scanner dedicado de secretos;
- política de revocación/rotación de JWT ante baja y reactivación;
- permisos mínimos de cuentas técnicas.

### Integraciones externas y pagos

- credenciales y entornos reales de Mercado Pago/proveedores;
- firmas, callbacks, URLs públicas, reintentos e idempotencia end-to-end;
- conciliación con evidencia oficial y recuperación de resultados inciertos;
- monitoreo, alertas y runbooks de incidencias financieras;
- validación del storage real y limpieza ante fallos parciales.

La CI de BH-060 usa credenciales sintéticas, adapters simulados y no llama a
servicios de producción. Por ello sus resultados no deben usarse como
certificación de esas integraciones.

## 8. Trazabilidad documental y cambios locales

### 8.1 Documentación versionada

El árbol contiene y relaciona:

- `AUDITORIA_CIERRE_BH060.md`, preservada como fotografía histórica del
  baseline bloqueado `1531f692...`;
- `REVALIDACION_CIERRE_BH060.md`, que registra la resolución posterior y este
  cierre técnico;
- `IMPLEMENTACION_BH060_1_CATALOGOS_EQUIPAMIENTO.md` a
  `IMPLEMENTACION_BH060_7_ESTABILIZACION_TESTS.md`;
- `IMPLEMENTACION_BH060_F1_CIERRE_AUTORIZACIONES.md`;
- `IMPLEMENTACION_BH060_F2_CI_PERMISOS.md`;
- `ANALISIS_DEADLOCK_REFUND_BH060_F2.md`;
- `IMPLEMENTACION_FIX_DEADLOCK_REFUND_BH060_F2.md`.

La auditoría histórica conserva sin reescritura su veredicto **BLOQUEADO PARA
CIERRE** y los cuatro hallazgos originales; no se altera para aparentar que el
bloqueo nunca existió. F1 documenta las tres superficies residuales. F2
documenta arquitectura, labels, aislamiento y el run verde. El análisis/fix de
deadlock explica la única corrección funcional posterior necesaria para que B7
terminara verde. La revalidación enlaza esa secuencia y emite el estado final.

### 8.2 Fuentes locales preservadas

`ANALISIS_BH060_TESTS_PERMISOS_POR_ROL.md` permanece como documento local no
rastreado. Fue usado como fuente original de los 14 criterios, pero no se
modifica ni se incluye en el cierre documental.

También permanecen fuera del entregable la modificación local preexistente de
`bohemiacore/bohemiacore/settings.py`, media, Cypress, `show_urls.py` y los demás
análisis/auditorías locales ajenos. Los logs consultados se guardaron fuera del
repositorio bajo el directorio temporal de OpenCode.

Los únicos documentos previstos para el commit de cierre son
`AUDITORIA_CIERRE_BH060.md` y `REVALIDACION_CIERRE_BH060.md`. No se incluyen
archivos de código, tests, workflows, migraciones, configuración o datos.

## 9. Propuesta de actualización de `BACKLOH.xlsx`

No se encontró `BACKLOH.xlsx` ni otro archivo `*BACKLO*.xlsx` en el repositorio
o workspace. Por ello no se crea ni modifica una planilla en esta tarea.

Se propone aplicar externamente esta actualización a la fila BH-060:

| Campo sugerido | Valor |
|---|---|
| ID | `BH-060` |
| Tarea | Tests automatizados de permisos por rol |
| Estado | `CERRADO TÉCNICAMENTE` |
| Fecha de cierre técnico | `2026-11-08` |
| Criterios | `14/14 CUMPLE` |
| Backend | `1.079/1.079` PostgreSQL, incluidos `64/64` concurrentes una sola vez |
| Frontend | `289/289`, 34/34 suites y build aprobado |
| Evidencia CI | `https://github.com/Aldo-1803/Trabajo-Final/actions/runs/42411231934` |
| Corrección F1 | `dd833b8ac2d9ae30037dda840ada762486f11ea4` |
| Commit funcional validado | `3a6640b9cce2345d64e5498b884ed506b44c017d` |
| Documentación F2 | `13b92311e0d7ae26d7cf0259a1605f2401d5bd4b` |
| Documento de cierre | `REVALIDACION_CIERRE_BH060.md` |
| Observación | Cierre técnico; producción requiere validaciones independientes de HTTPS, secretos, tokens, storage, integraciones y pagos reales. |

Esta propuesta no inicia ni cambia el estado de BH-061 o BH-062.

## 10. Veredicto definitivo

La evidencia estática, la matriz F1, la estructura del workflow, la identidad
del SHA ejecutado y los logs remotos demuestran que los cuatro bloqueos de la
auditoría anterior están cerrados. Los 14 criterios originales quedan
satisfechos. La revalidación `LISTO PARA CERRAR` queda formalizada como cierre
técnico, sin atribuir a BH-060 garantías de despliegue o de integraciones reales
que pertenecen a verificaciones independientes.

> # BH-060 = CERRADO TÉCNICAMENTE
