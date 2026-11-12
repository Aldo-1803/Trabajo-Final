# Auditoría integral de cierre BH-061

**Fecha:** 2026-11-10

**Commit auditado:** `a9d0daecaa0d6fcf5008bdb0c22cd81f877e02b1`

**Rama:** `save/work-in-progress`

**Modalidad:** inspección independiente de código y contratos, ejecución real
sobre PostgreSQL, pruebas frontend, build y verificaciones documentales.

**Alcance:** BH-061 Incrementos 1–4. No se modificaron implementación, tests,
configuración, migraciones, README ni backlog; no se hizo commit ni push y no
se inició BH-062.

## 1. Resumen ejecutivo y veredicto

La implementación satisface los 15 criterios de cierre definidos en
`ANALISIS_BH061_AUDITORIA_ROLES_PERMISOS.md:519-550`. La auditoría no encontró
una ruta productiva que cambie `BusinessRole`, estado de acceso o habilidades
sin pasar por los servicios semánticos correspondientes, ni una superficie
API/Admin que permita alterar los eventos.

Se verificaron especialmente:

- no-op real de `assign_initial_client_role()`;
- contrato histórico inmutable `bh061-role-capabilities-v1` y fingerprints
  reproducibles e independientes del orden;
- metadata versionada en todas las rutas productivas de asignación efectiva;
- cuatro operaciones compuestas con UUIDv4 común, referencias y cardinalidad;
- motivo, fuente, actor, objetivo y before/after de habilidades;
- rollback ante fallas de `Auditoria` y ausencia de eventos huérfanos;
- cinco carreras críticas sobre PostgreSQL real, **5/5**;
- frontend relevante, **33/33**;
- matriz backend de 95 módulos y **1.103 pruebas**, con **1.102 aprobadas** y un
  fallo temporal ajeno a BH-061, analizado en la sección 7. El caso fallido
  aprobó aisladamente **1/1** después de la ventana de medianoche.

**Balance de criterios:** 15 CUMPLE, 0 CUMPLE PARCIAL, 0 NO CUMPLE y 0 NO
VERIFICADO.

> **BH-061 = LISTO PARA CIERRE TÉCNICO**

Este veredicto no declara todavía la tarea cerrada y no equivale a aptitud para
producción.

## 2. Baseline y metodología

### 2.1 Integridad del baseline

- Al inicio, `HEAD`, upstream y `origin/save/work-in-progress` coincidían con el
  commit auditado.
- El cambio BH-061 respecto de su baseline de inicio (`c0f70cd`) está limitado
  a servicios, serializers, vistas, frontend de habilidades, pruebas y
  documentación de BH-061/índice. No contiene migraciones, settings ni BH-062.
- Se preservaron sin modificación los cambios locales ajenos: `settings.py`,
  media, Cypress y `show_urls.py`.
- `bohemiacore.test_settings` exige un nombre `test_*`, fija
  `StablePostgresTestRunner` y mantuvo la base de prueba aislada
  (`bohemiacore/bohemiacore/test_settings.py:8-19`).

### 2.2 Método

1. Se recuperaron literalmente los 15 criterios originales.
2. Se inspeccionaron servicios y todos los callsites productivos de
   `assign_business_role()`, además de API, serializers, routers y Django Admin.
3. Se revisaron aserciones de cardinalidad, no sólo estados finales o informes
   previos.
4. Los eventos semánticos se contaron por `tabla + valor_nuevo.event`; las
   señales CRUD genéricas no se contaron como mutaciones semánticas adicionales.
5. Se ejecutaron los 95 módulos `test*.py` de `usuarios` y `gestion/tests`
   mediante etiquetas explícitas, secuencialmente y sin `--parallel`.
6. Se aislaron las cinco carreras requeridas y se ejecutaron frontend, build,
   checks, migraciones, enlaces, secretos y diff.

El descubrimiento sin etiquetas encontró sólo 163 tests, y la etiqueta de
paquete `gestion.tests` sólo elevó el total a 166. Esas corridas aprobaron, pero
no se presentan como matriz completa ni se suman como pruebas únicas. La matriz
real se construyó enumerando explícitamente los 95 módulos.

## 3. Matriz de los 15 criterios

| # | Criterio | Evidencia independiente | Resultado |
|---:|---|---|---|
| 1 | Una mutación efectiva de `BusinessRole` produce exactamente un evento semántico. | Los únicos callsites productivos de la primitiva están en altas CLIENTE/ADMINISTRADOR y `access_services`; todos escriben evento y metadata (`usuarios/access_services.py:196-273,530-613`; `client_account_services.py:120-174`; `administrator_account_services.py:110-157`). Los compuestos delegan en esos servicios. | **CUMPLE** |
| 2 | Repetir un comando en estado final no crea evento. | Retornos `changed=False` antes de escribir (`access_services.py:227-235`; habilidades en `personal_skill_services.py:176-177,207-208,238-239`). Pruebas de rol, cuenta, Personal, compuestos y habilidades verifican conteo cero. | **CUMPLE** |
| 3 | `assign_initial_client_role()` respeta no-op. | Bloqueo y detección en `access_services.py:212-235`; el evento se crea sólo después del cambio, líneas 237-266. `test_public_registration.py:79-105` comprueba segunda invocación sin duplicado. | **CUMPLE** |
| 4 | Promoción, degradación y EMPLEADO↔PROFESIONAL incluyen before/after y contrato versionado. | `build_business_role_audit_metadata()` se incorpora en el evento base (`access_services.py:585-610`) y en altas; pruebas secuenciales y concurrentes comprueban roles y fingerprints (`test_bh059_c_role_change_services.py`, `test_bh059_c_business_role_concurrency.py`). | **CUMPLE** |
| 5 | Último administrador y privilegios residuales rechazados no cambian estado ni eventos. | Locks y validaciones del servicio; pruebas secuenciales en `test_bh059_c_role_change_services.py:159-225` y carrera en `test_bh059_c_business_role_concurrency.py:266-353` verifican estado y cardinalidad. | **CUMPLE** |
| 6 | Una falla de `Auditoria` revierte la mutación y no deja hijos huérfanos. | Servicios atómicos en `access_services.py`, `personal_access_services.py` y `personal_skill_services.py`; fallas forzadas en `test_access_services.py:357-374`, `test_personal_access_creation_services.py:258-313`, `test_*work_access_revocation_services.py` y `test_skills_api.py:282-352`. | **CUMPLE** |
| 7 | Cada operación compuesta comparte `operation_id` y referencias verificables. | UUIDv4 generado dentro de cada transacción (`personal_access_services.py:443,572,802,1055`), propagado a hijos y padre. Las cuatro suites consultan el conjunto total por JSON y comparan IDs/cardinalidad exacta. | **CUMPLE** |
| 8 | Las carreras PostgreSQL producen exactamente los eventos de cambios confirmados. | Cuatro carreras de rol/cuenta en `test_bh059_c_business_role_concurrency.py:266-434` y una de habilidad en `test_bh061_audit_concurrency.py:97-154`; ejecución aislada 5/5. Las aserciones cuentan eventos y enlazan el único ID con el resultado ganador. | **CUMPLE** |
| 9 | Habilidades auditan actor, before/after, fuente y motivo. | Constantes de fuente y payload en `personal_skill_services.py:11-21,105-144`; comandos atómicos y locks en líneas 147-252. API exige motivo 3–500 y payload estricto (`serializers.py:869-886`); frontend valida el mismo rango (`GestionPersonal.js:210-237`). | **CUMPLE** |
| 10 | No hay CRUD alternativo de acceso o auditoría. | `PersonalSerializer` hace read-only estado, vínculo, rol de negocio y flags (`serializers.py:614-660`); serializers de Usuario separan identidad de comandos (`serializers.py:1033-1075`); alta/baja genérica de Usuario está deshabilitada (`views.py:3642-3692`). `Group` está desregistrado y Usuario no expone grupos/permisos (`usuarios/admin.py:22-64`); `AuditoriaAdmin` es read-only (`gestion/admin.py:654-722`). | **CUMPLE** |
| 11 | Lectura usa `view_audit`; reversión usa `revert_audit` y excluye acceso. | Permisos efectivos y cuenta activa en `gestion/permissions.py:68-87`; ViewSets en `views_auditoria.py:35-92,95-153`; campos `Personal.usuario_id`, `rol` y `activo` bloqueados en líneas 122-133, 199-223. Pruebas en `test_bh059_a_access_surfaces.py:186-271`. | **CUMPLE** |
| 12 | Ningún evento contiene secretos. | Payloads inspeccionados sólo incluyen IDs, estados, metadatos, fuente y motivo. Pruebas buscan password/hash/token/JTI/credenciales en altas, cambios, compuestos, cuenta y habilidades. El diff focal no añadió claves sensibles; `refresh_tokens_revoked` es un contador, no un token. | **CUMPLE** |
| 13 | Rechazos no se publican como éxito. | Motivo inválido, falta de permiso, último admin, residuos, target/skill inexistente e inactivo se validan antes del evento o revierten atómicamente. Las suites de servicios/API comprueban cero evento semántico y cero mutación. | **CUMPLE** |
| 14 | Se separan permisos Django, `BusinessRole`, estados y habilidades. | `assign_business_role()` sólo reemplaza grupos canónicos y conserva grupos técnicos/permisos individuales (`roles.py:282-308`); cuenta y Personal usan campos/servicios separados; `PersonalHabilidad` es un modelo con unicidad propia (`models.py:129-152`) y no un permiso Django. | **CUMPLE** |
| 15 | No hay ampliaciones fuera de alcance. | El diff BH-061 se limita al contrato, correlación, auditoría de habilidades, frontend asociado, pruebas y documentación. No incorpora grants arbitrarios, editor genérico, retención/exportación forense, rediseño UX ni BH-062. | **CUMPLE** |

## 4. Contrato versionado de roles

`usuarios/roles.py:117-151` conserva un snapshot histórico real:

- versión publicada `bh061-role-capabilities-v1`;
- mapping exterior e interior mediante `MappingProxyType`;
- tuplas propias para cada rol, no un alias mutable al mapping vigente;
- fingerprints SHA-256 publicados para los cuatro roles.

`fingerprint_business_permissions()` ordena y deduplica antes de serializar JSON
canónico (`roles.py:154-171`), por lo que el orden de entrada no cambia el hash.
La validación ejecutada al importar recalcula los fingerprints y lanza
`RuntimeError` si v1 fue alterado (`roles.py:217-237`).

`ROLE_BASE_PERMISSIONS` apunta al contrato vigente sólo después de esa
validación (`roles.py:239-241`). Un cambio futuro de capacidades deberá publicar
otra versión; no puede sobrescribir silenciosamente v1 sin romper la carga.

La metadata se agrega a:

- alta CLIENTE pública (`access_services.py:244-266`);
- alta CLIENTE por staff (`client_account_services.py:146-174`);
- alta ADMINISTRADOR (`administrator_account_services.py:131-157`);
- cambio general de rol (`access_services.py:577-610`);
- padres compuestos que describen la transición laboral.

La primitiva reemplaza sólo grupos cuyos nombres pertenecen a
`BusinessRole.ALL`; no toca grupos técnicos ni `user_permissions`. Los eventos
históricos sin fingerprints u `operation_id` siguen siendo legibles, demostrado
por `test_bh059_a_access_surfaces.py:196-226`.

## 5. Correlación de las cuatro operaciones compuestas

| Operación | Evento padre | Hijos completos | Total exacto |
|---|---|---|---:|
| Cambio laboral | `PERSONAL_BUSINESS_ROLE_CHANGED` | `BUSINESS_ROLE_CHANGED` | 2 |
| Creación de acceso Personal | `PERSONAL_ACCESS_CREATED` | `PERSONAL_USER_LINKED`, `BUSINESS_ROLE_CHANGED` | 3 |
| Revocación conservando Cliente | `WORK_ACCESS_REVOKED_KEEP_CLIENT` | `PERSONAL_DEACTIVATED`, `BUSINESS_ROLE_CHANGED` | 3 |
| Revocación desactivando cuenta | `WORK_ACCESS_REVOKED_ACCOUNT_DISABLED` | `PERSONAL_DEACTIVATED`, `ACCOUNT_DEACTIVATED` | 3 |

Las pruebas `test_personal_business_role_services.py`,
`test_personal_access_creation_services.py`,
`test_work_access_revocation_services.py` y
`test_full_work_access_revocation_services.py` verifican:

- un único UUIDv4 por ejecución y distinto entre ejecuciones;
- igualdad exacta entre el conjunto consultado por `operation_id` y los IDs
  padre/hijos retornados;
- referencias del padre sólo a hijos realmente creados;
- no-op/rechazo sin duplicados;
- rollback del estado y cero auditorías huérfanas al fallar el padre.

No se exige `operation_id` a eventos simples ni retroactivamente a eventos
históricos.

## 6. Habilidades técnicas

Asignación, revocación y reactivación pasan por servicios atómicos con locks de
Personal, Habilidad y asignación. El modelo impide duplicar el par
Personal/Habilidad. Cada cambio efectivo registra:

- actor (`usuario` y `actor_id`), Personal, habilidad y Usuario vinculado si
  existe;
- `previous_active`/`current_active` y snapshots anterior/nuevo;
- fuente estable del comando y motivo normalizado de 3–500 caracteres.

El permiso es `gestion.manage_skills`, comprobado tanto en API como nuevamente
en servicio con actor recargado y activo (`personal_skill_services.py:51-70`).
No-op, payload inválido, permiso insuficiente, habilidad inactiva o inexistente
no publican éxito. Una falla del escritor revierte la asignación. El frontend
envía únicamente `{motivo}` y sus pruebas cubren asignar/revocar/reactivar,
límites y errores.

`Habilidad`/`PersonalHabilidad` siguen siendo entidades técnicas separadas; no
se añadieron codenames Django por habilidad ni se modificaron flags legacy para
conceder acceso.

## 7. Pruebas y regresiones

### 7.1 Backend PostgreSQL

Matriz completa auditada, secuencial y sin `--parallel`:

```powershell
$labels = <95 módulos test*.py de usuarios y gestion/tests>
python manage.py test $labels `
  --settings=bohemiacore.test_settings --keepdb --noinput -v 1
```

Resultado: **1.103 ejecutadas; 1.102 aprobadas y 1 fallo**, 2.575,64 s totales.
Los trazados de `forced audit failure`, storage y proveedor corresponden a
casos que fuerzan esas excepciones y aprobaron; no son errores adicionales.

El único fallo fue:

`gestion.tests.test_diagnosis_authorization_api.DiagnosisAuthorizationApiTests.test_diagnosis_recommendation_uses_canonical_availability_not_category_text`

Durante una ventana de medianoche esperaba 2026-11-10 y recibió 2026-11-17.
El test calcula mañana con `timezone.localdate()`
(`test_diagnosis_authorization_api.py:452-487`), mientras la implementación
parte de `date.today()` (`views.py:5392-5394`). Si la fecha UTC ya avanzó pero
la fecha local aún no, busca desde un día posterior y encuentra el mismo día de
semana una semana después. Repetido aisladamente tras cambiar la fecha local:
**1/1**, 9,11 s.

Este hallazgo es real y debe corregirse en otra tarea, pero no es regresión ni
alcance de BH-061: las líneas de test/producto anteceden BH-061 y el diff de los
cuatro incrementos no toca esa función ni ese test. Todos los tests propios de
BH-061 y las regresiones de acceso/auditoría dentro de la matriz aprobaron.

Carreras críticas aisladas:

```powershell
python manage.py test `
  usuarios.test_bh059_c_business_role_concurrency `
  gestion.tests.test_bh061_audit_concurrency `
  --settings=bohemiacore.test_settings --keepdb --noinput -v 1
```

Resultado: **5/5**, 55,48 s. Incluye exactamente:

1. dos degradaciones de administrador;
2. degradación contra desactivación;
3. dos cambios idénticos de rol;
4. dos desactivaciones de cuenta;
5. dos asignaciones de la misma habilidad.

Esta ejecución es repetición aislada de casos ya incluidos en las 1.103 y no se
suma como tests únicos.

### 7.2 Frontend, build y checks

- `GestionPersonal.test.js` + `GestionUsuarios.test.js`: **33/33**, 2 suites.
- `npm run build`: compiló correctamente. Emitió warnings preexistentes de
  Browserslist, dependencia dinámica y lint en componentes ajenos a BH-061.
- `manage.py check --settings=bohemiacore.test_settings`: sin issues.
- `makemigrations --check --dry-run`: sin cambios.
- `migrate --check`: sin migraciones pendientes.

### 7.3 Documentación, secretos y diff

- Los seis enlaces de la sección BH-061 de `documentacion/README.md` resuelven;
  los cinco documentos BH-061 existentes no contienen links locales rotos.
- El escaneo de adiciones en los servicios BH-061 no encontró claves de
  password, hash, token, JTI, secret o credential en payloads.
- `git diff --check` no encontró whitespace errors; sólo mostró el warning
  CRLF/LF del `settings.py` local preexistente.
- Antes de crear este informe, el único archivo tracked modificado era ese
  `settings.py`; media, Cypress y `show_urls.py` seguían no rastreados. No se
  tocaron.

## 8. Hallazgos por severidad

| Severidad | Hallazgo | Impacto en BH-061 |
|---|---|---|
| Bloqueante | Ninguno. | No bloquea. |
| Media, fuera de alcance | `_recomendar_primer_hueco_disponible()` mezcla `date.today()` con tests/stack timezone-aware. Puede omitir una semana alrededor de medianoche y vuelve la suite sensible a la hora. | Preexistente, sin relación con auditoría de acceso; requiere tarea separada y no reabre BH-059/BH-060 ni bloquea BH-061. |
| Baja, documental | `documentacion/README.md:82-92` aún dice que BH-061 está “en curso” y “contiene 2 documentos”, aunque enlaza los cinco correctamente. | Debe actualizarse durante el cierre documental posterior; se preservó por restricción. |
| Informativa | El build conserva warnings ajenos y el descubrimiento Django por defecto omite `gestion/tests`; la matriz completa requiere etiquetas de módulos. | No afecta contratos BH-061; conviene automatizar la enumeración para futuras auditorías. |

## 9. Riesgos residuales

### No bloqueantes de BH-061

- `assign_business_role()` es una primitiva interna no auditora; la cobertura
  depende de mantener la regla de que todo nuevo callsite productivo use un
  servicio semántico. Actualmente todos los callsites productivos cumplen.
- Las carreras cubren las cinco combinaciones críticas, no todas las
  intercalaciones posibles entre comandos administrativos.
- `operation_id` vive en JSON sin índice dedicado.

### Pendientes de producción

- Ejecutar smoke tests de permisos/grupos y lectura de eventos en el entorno
  desplegado, con backup y monitoreo operativo.
- Confirmar que los grupos canónicos desplegados conservan los grants esperados
  y que no existen callsites externos al repositorio.
- Resolver y estabilizar el hallazgo timezone antes de presentar la matriz
  global como totalmente verde.

### Mejoras futuras fuera de alcance

- Protección forense append-only frente a acceso SQL directo.
- Retención, exportación, firma y búsqueda avanzada de auditoría.
- Índice/proyección dedicada para correlación por `operation_id`.

Ninguno de esos puntos impide el cierre técnico específico de BH-061.

## 10. Veredicto final

La evidencia productiva, contractual y de pruebas demuestra los 15 criterios.
No existe hallazgo bloqueante atribuible a BH-061. El único fallo de la matriz
global fue reproducido y clasificado como una inconsistencia temporal
preexistente en recomendación de Turnos, fuera del diff y del contrato auditado.

> **BH-061 = LISTO PARA CIERRE TÉCNICO**

Corresponde ahora realizar el cierre documental posterior. Este informe no hace
ese cierre, no actualiza backlog/README y no declara aptitud para producción.
