# BH-060 F2 — CI automatizada de permisos por rol

## 1. Estado

**Fecha de implementación:** 2026-11-07
**Baseline:** `dd833b8ac2d9ae30037dda840ada762486f11ea4`
**Workflow:** `.github/workflows/bh060-permisos.yml`

**Implementación local:** VALIDADA

**Ejecución real en GitHub Actions:** BLOQUEADA POR B7

> **BH-060 F2 = BLOQUEADO**

Este estado sólo puede cambiar a VALIDADO después de que una ejecución remota
complete B1–B7, Jest y build con resultado global exitoso.

## 2. Inspección del entorno

| Componente | Fuente/versionado | Versión usada en CI |
|---|---|---:|
| Python | venv validado y `requirements-ci.txt` nuevo, totalmente fijado | 3.13.7 |
| Node | `frontend/package-lock.json`, lockfile v3 | 24.11.0 |
| npm | Incluido con Node; instalación mediante `npm ci` | La provista por Node 24.11.0 |
| PostgreSQL | Servicio Docker por job | 16.9 |
| Django | `requirements-ci.txt` | 5.2.7 |
| Frontend | `frontend/package.json` + `package-lock.json` | Dependencias exactas del lockfile |

Antes de F2 no existía un manifiesto Python completo: sólo
`requirements-payments.txt` para Mercado Pago. Se agregó
`bohemiacore/requirements-ci.txt` con las versiones del entorno que aprobó
BH-060. No se incluyó el paquete fuente `psycopg2` junto con
`psycopg2-binary`; CI usa únicamente el wheel binario fijado para evitar dos
distribuciones que exponen el mismo módulo.

`bohemiacore.test_settings` conserva:

- `TEST.NAME` controlado por `BH_TEST_DB_NAME`;
- rechazo de nombres sin prefijo `test_`;
- `StablePostgresTestRunner`;
- restauración idempotente de roles BusinessRole y habilidades canónicas;
- comprobación de que la conexión activa coincide exactamente con la base de
  test configurada.

La zona Django permanece en `America/Bogota`; el runner también recibe
`TZ=America/Bogota`. Los directorios media/private media pertenecen al workspace
efímero del runner. Los servicios de pago/provider continúan simulados por los
tests; CI no configura tokens reales ni inicia workers externos.

## 3. Disparadores y permisos

El workflow se ejecuta en:

- push a `save/work-in-progress`;
- pull request cuyo destino sea `save/work-in-progress`;
- `workflow_dispatch` manual.

El `GITHUB_TOKEN` tiene sólo `contents: read`. No se solicitan permisos de
escritura sobre contenido, issues, paquetes, deployments ni pull requests.

Las credenciales PostgreSQL están escritas como valores de prueba sin uso fuera
del contenedor efímero. No se usan secrets de repositorio o producción.

La API del repositorio confirmó antes de publicar:

- GitHub Actions habilitado;
- política `allowed_actions=all`.

## 4. Arquitectura de jobs

### 4.1 Backend B1–B6

Un job matrix crea seis runners `ubuntu-24.04`. Cada entrada dispone de:

- contenedor PostgreSQL propio;
- puerto y filesystem propios del runner;
- nombre `BH_TEST_DB_NAME` único;
- instalación Python desde `requirements-ci.txt`;
- `check` y `makemigrations --check --dry-run`;
- base limpia: nunca usa `--keepdb`;
- ejecución con `--buffer --noinput`, sin `--parallel`;
- timeout según la duración histórica.

`fail-fast: false` evita que el fallo de un bloque oculte los resultados de los
demás. `max-parallel: 6` reduce la duración total sin compartir base o proceso.

### 4.2 B7 de concurrencia

B7 es un job explícito, no una entrada de la matriz funcional. Tiene runner,
servicio PostgreSQL y base `test_bohemia_hair_ci_b7` propios. Ejecuta las 17
etiquetas oficiales en un único proceso y nunca pasa `--parallel`.

B7 puede coexistir con otros jobs porque GitHub asigna una máquina y un
contenedor aislados; no existe un nombre de base o servidor compartido.

### 4.3 Frontend

Job independiente con:

```text
npm ci
npm test -- --watchAll=false --runInBand
npm run build
```

Jest se ejecuta con `CI=true` para impedir modo watch. El build se ejecuta con
`CI=false` porque Create React App convierte todos los warnings preexistentes en
errores cuando esa variable vale `true`; los warnings permanecen visibles en el
log y cualquier error real de compilación conserva un código distinto de cero.
Jest y build se ejecutan ambos y el job falla si cualquiera devuelve código no
cero. No se usa `|| true` ni se silencian aserciones, errores o warnings.

### 4.4 Resultado global

Un job final usa `if: always()` para publicar el estado de backend B1–B6, B7 y
frontend. Termina con error si cualquier dependencia no fue `success`; por ello
un fallo no puede quedar representado por un check global verde.

## 5. Matriz auditable

| Bloque | Alcance | Tests esperados | Timeout | Base CI |
|---|---|---:|---:|---|
| B1 | Roles, Usuario, Personal y permisos | 411 | 30 min | `test_bohemia_hair_ci_b1` |
| B2 | Diagnóstico, ficha y rutinas | 155 | 20 min | `test_bohemia_hair_ci_b2` |
| B3 | Agenda, turnos, CU-27 y 6 casos F1 | 158 | 25 min | `test_bohemia_hair_ci_b3` |
| B4 | Catálogos, inventario, órdenes y 5 casos F1 | 79 | 15 min | `test_bohemia_hair_ci_b4` |
| B5 | Caja, pagos e incidencias | 170 | 35 min | `test_bohemia_hair_ci_b5` |
| B6 | Django Admin y auditoría | 42 | 20 min | `test_bohemia_hair_ci_b6` |
| B7 | Concurrencia PostgreSQL | 64 | 30 min | `test_bohemia_hair_ci_b7` |
| Frontend | 34 suites Jest + build | 289 | 20 min | No aplica |

**Backend esperado único:** 1.079 tests: los 1.068 oficiales más los 11 casos
de F1. Los métodos F1 se distribuyen una sola vez:

- B3: autorización general y HorarioLaboral;
- B4: RequisitoServicio y upload de productos.

No se redujo ni reemplazó ninguna etiqueta de BH-060.7.

## 6. PostgreSQL y aislamiento

Cada job backend levanta `postgres:16.9` con health check `pg_isready`. El usuario
efímero `bh060_ci` puede crear y eliminar exclusivamente las bases del
contenedor del job. La base de conexión inicial es `bohemia_hair_clean`; Django
crea y destruye el `TEST.NAME` explícito.

Variables de prueba:

```text
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=bh060_ci
DB_PASSWORD=<credencial literal sólo de CI>
BH_TEST_DB_NAME=test_bohemia_hair_ci_bN
```

No hay acceso de red a una base de desarrollo o producción. Las migraciones y
seeds se aplican al crear cada base de test y el runner repone roles/habilidades
después de cada flush de `TransactionTestCase`.

## 7. Observabilidad

Cada job publica en `GITHUB_STEP_SUMMARY`:

- bloque;
- tests esperados;
- aprobado/fallido;
- duración en segundos;
- run y referencia del job.

La salida completa permanece visible en el log normal de Actions. Si falla un
test se sube sólo el log de ese bloque durante 7 días. Frontend sube sus logs de
Jest/build únicamente al fallar. No se generan dumps de PostgreSQL, `.env`,
tokens, media ni datos de aplicación como artifacts.

## 8. Validación local previa

| Validación | Resultado |
|---|---|
| Parseo YAML con el paquete `yaml` del lockfile frontend | Correcto; triggers y cuatro jobs reconocidos. |
| Conteo de labels | B1 36, B2 10, B3 15, B4 9, B5 13, B6 4, B7 17. |
| Resolución Python | `pip install --dry-run -r requirements-ci.txt`: conforme. |
| Resolución frontend | `npm ci --dry-run`: conforme. |
| Frontend con entorno corregido | Jest 34/34 suites y 289/289 tests; build exitoso con warnings visibles. |
| Matriz F1 previa | 11/11 y regresión afectada 217/217 sobre PostgreSQL. |
| Matriz BH-060.7 previa | 1.068/1.068 backend y 289/289 frontend. |
| Whitespace | Sin errores en archivos F2. |

Esta evidencia valida estructura y compatibilidad local, pero no sustituye el
run remoto requerido.

## 9. Resultado remoto

### 9.1 Primera ejecución

- Run: [42404318264](https://github.com/Aldo-1803/Trabajo-Final/actions/runs/42404318264).
- Evento: `push` automático.
- Commit: `9138a689652f2f054f1165264082eb880d864bbd`.
- Resultado global: fallido después de 5 min 20 s de pared.
- B1–B6: aprobados; ejecutaron los 1.015 tests funcionales esperados, incluidos
  los 11 casos F1 distribuidos entre B3 y B4.
- Duraciones de pared por job: B1 5 min 13 s; B2 1 min 41 s; B3 2 min 36 s;
  B4 1 min 34 s; B5 4 min 24 s; B6 2 min 3 s; B7 2 min 54 s; frontend
  1 min 34 s.
- Frontend: Jest aprobó 34 suites y 289 tests; build falló porque
  Create React App recibió `CI=true` y convirtió warnings preexistentes en
  errores. Los warnings fueron visibles y correspondieron a dependencia
  dinámica, Browserslist y ESLint; no hubo un error real de compilación.
- B7: encontró y ejecutó los 64 tests esperados en proceso único, pero un test
  terminó con un deadlock PostgreSQL en
  `test_refund_execution_concurrency`; el resto del bloque aprobó. No se cambia
  negocio ni el test dentro de F2.

Corrección exclusiva de CI para frontend: `CI=true` queda limitado a Jest y el
build usa `CI=false`, manteniendo sus warnings en la salida y propagando el
código de error real. Una nueva ejecución completa deberá aprobar B1–B7, Jest,
build y el resultado global antes de validar F2.

### 9.2 Segunda ejecución completa

- Run: [42405102458](https://github.com/Aldo-1803/Trabajo-Final/actions/runs/42405102458).
- Evento: `push` automático.
- Commit: `3d0a90daece78d999466391317debcb725b40142`.
- Resultado global: fallido después de 5 min 26 s de pared.
- B1–B6: aprobados nuevamente; 1.015 tests funcionales esperados.
- Frontend: aprobado; 34/34 suites, 289/289 tests Jest y build productivo. Los
  warnings preexistentes quedaron visibles y no ocultaron el resultado.
- B7: ejecutó los 64 tests esperados, en proceso único y sin `--parallel`, pero
  volvió a producir el mismo deadlock en
  `RefundExecutionConcurrencyTests.test_two_operators_create_one_operation_and_one_external_call`.
- Duraciones de pared por job: B1 5 min 7 s; B2 2 min 6 s; B3 2 min 37 s;
  B4 1 min 31 s; B5 5 min 16 s; B6 2 min 2 s; B7 2 min 56 s; frontend
  1 min 8 s.

El caso focal que falla en Linux CI aprobó localmente 1/1 sobre PostgreSQL 16.9
en 22,144 s, sin `--parallel` ni `--keepdb`. No obstante, dos runners remotos
limpios reprodujeron el mismo ciclo de bloqueo sobre
`gestion_financialresolutionrequest`, por lo que no existe evidencia remota
verde para B7.

No se agregan reintentos, tolerancia al error ni serialización artificial: esas
medidas podrían ocultar el defecto que B7 debe detectar. Su investigación puede
requerir cambios en el orden de locks, límites transaccionales o en la prueba de
concurrencia; todos están fuera del alcance autorizado de F2, que permite
corregir únicamente workflow y entorno CI.

## 10. Riesgos y limitaciones

- Las etiquetas largas se mantienen explícitas en YAML para trazabilidad; un
  cambio futuro de la matriz debe actualizar BH-060.7 y el workflow juntos.
- Los seis jobs funcionales privilegian aislamiento y tiempo de pared sobre
  ahorro de minutos de runner.
- Los warnings preexistentes del frontend seguirán visibles en build/Jest.
- B7 reproduce de forma consistente en Linux CI un deadlock de ejecución de
  refunds que no se resuelve mediante configuración del workflow.
- Los artifacts de fallo pueden contener emails y valores sintéticos de tests,
  pero no credenciales reales ni dumps. La retención se limita a 7 días.
- F2 no resuelve configuración de producción ni implementa BH-061/BH-062.

## 11. Veredicto

El workflow está implementado, publicado y ejecuta toda la matriz con bases
PostgreSQL independientes. B1–B6 y frontend están validados remotamente, pero
B7 falla de forma reproducible en GitHub Actions por el deadlock descrito. El
resultado global permanece rojo y BH-060 no se declara cerrado.

> **BH-060 F2 = BLOQUEADO**
