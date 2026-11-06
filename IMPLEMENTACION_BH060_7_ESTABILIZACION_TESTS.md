# BH-060 Incremento 7 — Estabilización de pruebas automatizadas

Fecha de validación: 2026-11-06
Baseline publicado: `476c53de15aa3563a4f747c3ad34b965494dba51`

## 1. Alcance y resultado

Se estabilizó el harness de permisos y regresiones sobre PostgreSQL sin cambiar
reglas de autorización, locks, transacciones ni cálculos productivos. La matriz
final aprobó **1.068/1.068 tests backend** y **289/289 tests frontend**. BH-060
no se declara cerrado: queda pendiente su auditoría integral.

El documento de referencia
`ANALISIS_BH060_TESTS_PERMISOS_POR_ROL.md` fue inspeccionado pero no modificado
ni incluido en este incremento.

## 2. Causas reproducidas y correcciones

### 2.1 Expectativa legacy de Personal

`DiagnosisAuthorizationApiTests.test_legacy_flags_are_read_only_in_personal_serializer`
esperaba que `PersonalSerializer` aceptara e ignorara tres flags técnicos. El
contrato vigente los rechaza con código `invalid` y texto
`Este campo no está permitido.`.

Se corrigió sólo el test para comprobar:

- `is_valid()` falso;
- los tres campos exactos;
- código y mensaje exactos;
- ausencia de `save()` y cero mutación de `Personal`.

No se debilitó el serializer.

### 2.2 PostgreSQL y `--keepdb`

`TransactionTestCase` ejecuta `flush` después de cada caso. Las filas creadas por
las data migrations `0020` y `0021` no se vuelven a ejecutar porque las
migraciones siguen registradas como aplicadas. Por ello una base preservada
podía quedar sin grupos `BusinessRole` y sin habilidades canónicas.

Se agregó:

- `bohemiacore.test_settings`, separado del `settings.py` local;
- base explícita `test_bohemia_hair_bh060`, configurable mediante
  `BH_TEST_DB_NAME`;
- rechazo inmediato de nombres que no comiencen con `test_`;
- verificación de que la conexión activa coincide exactamente con `TEST.NAME`;
- restauración idempotente de `ROLE_BASE_PERMISSIONS` y de `DIAGNOSTICO`,
  `LAVADO`, `COLORACION` al preparar la base, después de cada `flush` y al
  finalizar una ejecución preservada;
- seis pruebas del contrato, seguridad, idempotencia y aislamiento entre dos
  `TransactionTestCase` consecutivos.

El runner no elimina bases arbitrarias y no opera sobre la base de desarrollo.
No usa fixtures dependientes del orden.

### 2.3 Concurrencia

Las suites concurrentes permanecen en un bloque PostgreSQL separado, ejecutado
sin `--parallel`. Dos aserciones de inventario imponían un único código para el
perdedor aunque el resultado legítimo depende de quién obtiene primero el lock:

- antes del consumo, la cancelación observa una orden pagada;
- después del consumo, observa una orden ya completada.

Se aceptan ambos códigos terminales válidos y se conservan las aserciones de un
único ganador, orden completada, compromiso consumido, stock, movimiento e
idempotencia. No se tocaron servicios, locks ni límites transaccionales.

### 2.4 Fecha, reloj y zona horaria

- Los tests Django relevantes dejaron de usar `date.today()` y usan
  `timezone.localdate()` con `TIME_ZONE='America/Bogota'`.
- `Operaciones.test.js` fija el reloj y deriva la fecha mediante getters locales,
  igual que el componente, evitando depender de la medianoche o de la zona del
  proceso Jest.
- La frontera de HOLD ya está cubierta por `test_slot_holds`: un microsegundo
  antes de `expires_at` se rechaza la expiración y exactamente en `expires_at`
  se materializa. También se cubre consumo de HOLD vencido sin crear Turno.
- No se cambió ningún cálculo productivo.

### 2.5 Logging y contexto de auditoría

Los `print` activos principales de middleware y signals se migraron a logging
`DEBUG`. Las excepciones de auditoría conservan traceback mediante
`logger.exception`. `AuditoriaMiddleware` limpia `user` y `request` del
thread-local en `finally`, tanto para responses normales como para excepciones.
Dos pruebas verifican esa limpieza.

Los comandos oficiales usan `--buffer`: la salida rutinaria de casos aprobados
queda capturada, mientras stdout/stderr se muestra cuando un test falla.

## 3. Requisitos y política oficial

1. PostgreSQL real accesible mediante `DB_USER`, `DB_PASSWORD`, `DB_HOST` y
   `DB_PORT`; el rol debe poder crear/eliminar bases de test.
2. Entorno Python del proyecto y dependencias instaladas.
3. Dependencias frontend instaladas en `frontend`.
4. Ejecutar secuencialmente. No usar `--parallel` ni compartir la misma base
   entre dos procesos.
5. Usar siempre `--settings=bohemiacore.test_settings`.
6. La referencia de validación omite `--keepdb`; `--keepdb` se reserva para el
   escenario controlado de reutilización.

Prefijo PowerShell usado desde `bohemiacore/`:

```powershell
$python = '..\venv\Scripts\python.exe'
$common = @(
  '--settings=bohemiacore.test_settings',
  '--verbosity', '1', '--buffer', '--noinput'
)
```

## 4. Matriz oficial reproducible

Cada bloque backend se ejecuta así, reemplazando `$labels` por la lista indicada:

```powershell
& $python -X utf8 manage.py test @labels @common
```

### Bloque 1 — Roles, Usuario, Personal y permisos

```powershell
$labels = @(
  'usuarios.test_roles', 'usuarios.test_public_registration',
  'usuarios.test_inactive_login', 'usuarios.test_current_session_api',
  'usuarios.test_client_account_creation_services',
  'usuarios.test_client_account_creation_api', 'usuarios.test_client_access_api',
  'usuarios.test_administrator_account_creation_services',
  'usuarios.test_administrator_account_creation_api',
  'usuarios.test_bh059_c_role_change_services',
  'usuarios.test_account_reactivation_services',
  'usuarios.test_account_deactivation_services', 'usuarios.test_access_services',
  'usuarios.tests', 'gestion.tests.test_account_deactivation_api',
  'gestion.tests.test_account_reactivation_api',
  'gestion.tests.test_bh059_a_access_surfaces',
  'gestion.tests.test_bh059_b_capability_read',
  'gestion.tests.test_bh059_c_business_role_change',
  'gestion.tests.test_personal_access_api',
  'gestion.tests.test_personal_access_creation_api',
  'gestion.tests.test_personal_access_creation_services',
  'gestion.tests.test_personal_access_services',
  'gestion.tests.test_personal_business_role_api',
  'gestion.tests.test_personal_business_role_services',
  'gestion.tests.test_personal_delete_disabled_api',
  'gestion.tests.test_personal_security',
  'gestion.tests.test_personal_status_api',
  'gestion.tests.test_personal_status_services',
  'gestion.tests.test_work_access_revocation_api',
  'gestion.tests.test_work_access_revocation_services',
  'gestion.tests.test_full_work_access_revocation_api',
  'gestion.tests.test_full_work_access_revocation_services',
  'gestion.tests.test_state_residual_aliases_bh060_6',
  'gestion.tests.test_test_harness', 'gestion.tests.test_audit_middleware'
)
```

### Bloque 2 — Diagnóstico, ficha y rutinas

```powershell
$labels = @(
  'gestion.tests.test_diagnosis_authorization_api',
  'gestion.tests.test_skills_api', 'gestion.tests.test_skills_migration',
  'gestion.tests.test_technical_record_formula_routine_permissions_bh060_3',
  'gestion.tests.test_technical_booking_blockers',
  'gestion.tests.test_technical_booking_requests',
  'gestion.tests.test_technical_risk_evaluator',
  'gestion.tests.test_technical_risk_models',
  'gestion.tests.test_technical_risk_policy_api',
  'gestion.tests.test_technical_risk_profiles'
)
```

### Bloque 3 — Agenda, turnos y CU-27

```powershell
$labels = @(
  'gestion.tests.test_booking_frontend_api',
  'gestion.tests.test_legacy_agenda_permissions_bh060_2.LegacyAgendaPermissionTests',
  'gestion.tests.test_slot_holds', 'gestion.tests.test_slot_hold_consumption',
  'gestion.tests.test_turno_arrival_api',
  'gestion.tests.test_turno_creation_api',
  'gestion.tests.test_turno_management_api',
  'gestion.tests.test_turno_read_authorization_api',
  'gestion.tests.test_turno_skill_compatibility'
)
```

### Bloque 4 — Catálogos, inventario y órdenes

```powershell
$labels = @(
  'gestion.tests.test_catalog_equipment_permissions_bh060_1',
  'gestion.tests.test_inventory_permissions_d3',
  'gestion.tests.test_inventory_stock', 'gestion.tests.test_order_inventory'
)
```

### Bloque 5 — Caja, pagos e incidencias

```powershell
$labels = @(
  'gestion.tests.test_manual_payments',
  'gestion.tests.test_payment_confirmation',
  'gestion.tests.test_payment_intents', 'gestion.tests.test_payment_providers',
  'gestion.tests.test_provider_checkout', 'gestion.tests.test_provider_events',
  'gestion.tests.test_provider_event_pipeline',
  'gestion.tests.test_provider_reconciliation',
  'gestion.tests.test_financial_adjustments',
  'gestion.tests.test_financial_case_closure',
  'gestion.tests.test_financial_case_read_api',
  'gestion.tests.test_financial_resolution',
  'gestion.tests.test_refund_execution'
)
```

### Bloque 6 — Django Admin y auditoría

```powershell
$labels = @(
  'gestion.tests.test_admin_usuario_crud_containment',
  'gestion.tests.test_auditoria',
  'gestion.tests.test_configuration_reports_permissions_bh060_4',
  'gestion.tests.test_django_admin_security_bh060_5'
)
```

### Bloque 7 — Concurrencia PostgreSQL aislada

```powershell
$labels = @(
  'usuarios.test_bh059_c_business_role_concurrency',
  'gestion.tests.test_legacy_agenda_permissions_bh060_2.AgendaBlockConcurrencyTests',
  'gestion.tests.test_financial_adjustments_concurrency',
  'gestion.tests.test_inventory_stock_concurrency',
  'gestion.tests.test_manual_payment_concurrency',
  'gestion.tests.test_legacy_order_payment_concurrency_bh060_6',
  'gestion.tests.test_order_inventory_concurrency',
  'gestion.tests.test_payment_confirmation_concurrency',
  'gestion.tests.test_payment_intent_concurrency',
  'gestion.tests.test_financial_resolution_concurrency',
  'gestion.tests.test_provider_reconciliation_concurrency',
  'gestion.tests.test_provider_event_pipeline_concurrency',
  'gestion.tests.test_provider_event_concurrency',
  'gestion.tests.test_slot_hold_consumption_concurrency',
  'gestion.tests.test_provider_checkout_concurrency',
  'gestion.tests.test_refund_execution_concurrency',
  'gestion.tests.test_slot_hold_concurrency'
)
```

Este bloque cubre último administrador, HOLD/Turnos, inventario/órdenes,
pagos/idempotencia e incidencias financieras. Debe ejecutarse solo, sin otro
proceso contra la misma base.

### Bloque 8 — Frontend

Desde `frontend/`:

```powershell
$env:CI = 'true'
npm test -- --watchAll=false --runInBand
npm run build
```

### Criterio de éxito

- proceso con exit code `0`;
- ejecutados = aprobados;
- cero failures y cero errors;
- checks sin issues y sin migraciones pendientes;
- concurrencia sin `--parallel`;
- build generado, aunque los warnings preexistentes se reporten.

## 5. Base limpia y reconstrucción segura de `--keepdb`

Referencia limpia del harness:

```powershell
& $python -X utf8 manage.py test gestion.tests.test_test_harness `
  --settings=bohemiacore.test_settings --verbosity 2 --buffer --noinput
```

Comprobación controlada, ejecutada dos veces:

```powershell
& $python -X utf8 manage.py test gestion.tests.test_test_harness `
  --settings=bohemiacore.test_settings --verbosity 1 --buffer --keepdb --noinput
```

Si una base preservada quedó incompleta, el mismo comando con `--keepdb` la
repara al inicio sin borrar la base. Para usar otro nombre seguro:

```powershell
$env:BH_TEST_DB_NAME = 'test_bohemia_hair_local'
```

El nombre debe comenzar con `test_`. Nunca apuntar `BH_TEST_DB_NAME` a una base
de desarrollo o real. Para una referencia completamente limpia, omitir
`--keepdb`; Django sólo recreará el `TEST.NAME` verificado.

## 6. Resultados observados

| Bloque | Ejecutados | Aprobados | Fallidos | Duración total |
|---|---:|---:|---:|---:|
| 1. Roles, Usuario, Personal y permisos | 411 | 411 | 0 | 950,14 s |
| 2. Diagnóstico, ficha y rutinas | 155 | 155 | 0 | 273,68 s |
| 3. Agenda, turnos y CU-27 | 152 | 152 | 0 | 406,01 s |
| 4. Catálogos, inventario y órdenes | 74 | 74 | 0 | 146,10 s |
| 5. Caja, pagos e incidencias | 170 | 170 | 0 | 1.015,49 s |
| 6. Django Admin y auditoría | 42 | 42 | 0 | 279,21 s |
| 7. Concurrencia aislada, ejecución final | 64 | 64 | 0 | 644,96 s |
| **Backend total, etiquetas disjuntas** | **1.068** | **1.068** | **0** | **3.715,59 s** |
| 8. Frontend, ejecución final | 289 | 289 | 0 | 72,83 s |
| Build frontend | — | OK | 0 | 85,43 s |

Validaciones adicionales:

| Validación | Resultado | Duración |
|---|---:|---:|
| Test legacy corregido | 1/1 OK | 5,65 s |
| Suite de diagnóstico | 26/26 OK | 7,37 s |
| Harness desde base limpia | 6/6 OK | 63,44 s |
| `--keepdb`, primera ejecución controlada | 6/6 OK | 61,58 s |
| `--keepdb`, segunda ejecución controlada | 6/6 OK | 16,43 s |
| Concurrencia de inventario focalizada | 6/6 OK | 93,59 s |
| `manage.py check` | 0 issues | 5,38 s |
| `makemigrations --check --dry-run` | sin cambios | 6,36 s |
| `migrate --check` | sin pendientes | 6,04 s |

Antes del ajuste de expectativas concurrentes hubo dos ejecuciones de 64 casos
con 63 aprobados y un fallo cada una. En ambas falló el código exacto esperado
del perdedor; los estados finales fueron válidos. Después del ajuste focalizado,
la suite de archivo aprobó 6/6 y el bloque completo aprobó 64/64.

## 7. CI

No existe `.github/workflows` ni otra configuración CI en el repositorio. No se
agregó infraestructura ni credenciales. La propuesta mínima para la auditoría
final es un único workflow con:

1. checkout;
2. servicio PostgreSQL oficial y health check;
3. Python y Node en versiones fijadas por el proyecto;
4. instalación con lockfiles;
5. variables `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` y
   `BH_TEST_DB_NAME=test_bohemia_hair_ci` provenientes sólo del job;
6. bloques backend 1–6 secuenciales;
7. bloque 7 en un job separado, sin matrix ni paralelismo sobre la misma DB;
8. frontend con `CI=true`, seguido de build.

La primera versión puede ejecutar sólo los bloques 1, 2, 7 y 8 en pull requests,
y la matriz completa en push/manual, debido a los tiempos observados. Los
comandos locales anteriores siguen siendo la fuente reproducible aunque CI no
esté disponible.

## 8. Riesgos residuales y auditoría final

- Los tests frontend aprueban, pero conservan warnings `act(...)` y logs de
  errores simulados; no ocultan fallos y su limpieza queda fuera de este cambio.
- El build aprueba con warnings ESLint, Browserslist y dependencia dinámica
  preexistentes.
- La matriz limpia completa tarda aproximadamente una hora en este equipo; CI
  deberá separar smoke tests de ejecución completa sin introducir paralelismo
  de concurrencia.
- `Operaciones` interpreta “hoy” según la zona local del navegador/proceso. El
  test ya no depende de una zona fija, pero una política de zona de negocio en
  producto requeriría una decisión funcional futura.
- Queda pendiente la auditoría integral de BH-060 y los riesgos de autorización
  ya registrados en el documento de análisis. No se inició BH-061 ni BH-062.

## Estado

**BH-060 INCREMENTO 7 = VALIDADO**
