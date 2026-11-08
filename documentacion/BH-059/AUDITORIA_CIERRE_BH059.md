# Auditoría consolidada de cierre BH-059

**Fecha:** 2026-11-05
**Commit auditado:** `46641e818d24683312323dc970a2f36e4a008f35`
**Rama:** `save/work-in-progress`
**Modalidad:** análisis estático, inventario de sólo lectura y pruebas.
**Alcance de la auditoría:** BH-059 A, B, C y D. Durante la auditoría no se
modificó código, migraciones, configuración ni backlog; tampoco se hizo commit
ni push.
**Cierre documental:** esta versión incorpora únicamente el registro de estado,
las transferencias propuestas y los riesgos independientes de la sección 11.

## 1. Resultado ejecutivo

BH-059 puede cerrarse técnicamente sin implementar E. A–D forman un límite de
seguridad coherente:

- la autoridad de las APIs de Usuario, Personal y auditoría se resuelve con
  permisos Django efectivos, no con `is_staff`;
- las mutaciones de acceso se concentran en comandos semánticos, con motivo,
  locks, atomicidad y auditoría;
- el cambio general de BusinessRole exige `manage_users + assign_roles`;
- la degradación y la desactivación comparten la protección concurrente del
  último administrador;
- las capacidades individuales y de grupos técnicos son visibles por origen y
  una degradación administrativa se bloquea si conservaría autoridad para
  administrar accesos;
- no hay API, UI ni Django Admin para otorgar permisos individuales o editar
  grupos técnicos;
- Usuario, Cliente y Personal conservan estados e identidades independientes;
- los bypasses originales de DELETE, Django Admin y reversión histórica están
  contenidos.

La auditoría encontró una expectativa legacy desactualizada, no un defecto de
seguridad: un test de diagnóstico espera que el serializer acepte y omita flags
legacy de habilidades, mientras el contrato seguro de A los rechaza como campos
no permitidos. La implementación y las pruebas de contención establecen el
rechazo estricto como conducta canónica.

**Decisión:** `BH-059 E = DIFERIBLE`.

## 2. Fuentes y método

Se contrastaron:

- `ANALISIS_BH059_ADMINISTRACION_ROLES_PERMISOS.md`;
- `IMPLEMENTACION_BH059_A_SUPERFICIES_SEGURAS.md`;
- `IMPLEMENTACION_BH059_B_LECTURA_CAPACIDADES.md`;
- `IMPLEMENTACION_BH059_C_CAMBIO_BUSINESSROLE.md`;
- `IMPLEMENTACION_BH059_D_CICLO_CUENTAS_PERSONAL.md`;
- servicios, permisos, serializers, APIs, Django Admin, frontend y pruebas del
  commit auditado;
- la base PostgreSQL local configurada (`bohemia_hair_clean`), exclusivamente
  mediante consultas de lectura.

No se tomó “VALIDADO” de los documentos como evidencia suficiente. Cada punto
se comprobó contra implementación, contratos ejecutables y resultados de
pruebas.

## 3. Matriz de brechas originales

| Brecha | Servicio implementado | API | Frontend | Pruebas/evidencia | Resultado | Riesgo residual |
|---|---|---|---|---|---|---|
| **B1. Pérdida del último administrador por cambio de rol** | `change_administrative_business_role` bloquea grupo y objetivo, y usa `_another_active_business_administrator_exists`; `deactivate_account` comparte el mismo lock. | `cambiar-rol-negocio` devuelve `LAST_ACTIVE_ADMIN`; baja total delega en la baja segura. | `GestionUsuarios` presenta el conflicto sin ofrecer bypass. | Servicio/API y 2 carreras PostgreSQL reales: degradación/degradación y degradación/desactivación. | **Cerrada** | No se cubren aquí operaciones directas de DBA, que quedan fuera de la aplicación. |
| **B2. Autoridad insuficiente para cambios generales** | El orquestador recarga al actor y exige conjuntamente `usuarios.manage_users` y `usuarios.assign_roles`; actor inactivo falla. | La action aplica la misma conjunción y envelope estable. | El botón requiere ambas capacidades publicadas por `/me/`. | Actores con cada permiso parcial, sólo `is_staff` e inactivos son rechazados. | **Cerrada** | Django conserva el bypass de superusuario, pero el superusuario es objetivo protegido y cuenta técnica de confianza. |
| **B3. DELETE, Django Admin y reversión evitaban invariantes** | Las bajas usan comandos semánticos; no existe servicio genérico alternativo de borrado. | DELETE de Usuario y Personal responde 405; reversión bloquea `usuario_id`, `rol` y `activo` de Personal. | No se presenta borrado físico. | Pruebas A, contención CRUD y Admin verifican ausencia de mutación. | **Cerrada** | Acceso directo a base/shell sigue siendo una capacidad operacional privilegiada externa al producto. |
| **B4. `is_staff` como autorización de acceso administrativo** | Los servicios usan `has_perm()` y vuelven a cargar al actor. | Usuario usa `CanManageUsers`; Personal usa `CanManagePersonal` o `CanManageSkills`; auditoría usa `CanViewAudit`/`CanRevertAudit`. | Rutas y navegación usan permisos de `/me/`. | Staff sin permiso recibe 403; actores no-staff con permiso efectivo acceden. | **Cerrada en superficies BH-059** | Persisten usos legacy de `IsAdminUser` en APIs de otros dominios, por ejemplo Ficha Técnica; no escriben acceso y no son regresión de A–D. |
| **B5. Degradación nominal con autoridad residual** | La proyección conserva fuentes técnicas/individuales y bloquea `manage_users`, `assign_roles` o `manage_personal` residuales; no elimina excepciones silenciosamente. | Devuelve `RESIDUAL_ADMIN_CAPABILITIES` y sus orígenes. | El modal advierte la autoridad que sobreviviría. | Pruebas cubren origen individual y grupo técnico; una capacidad no escalante como `view_stock` se conserva. | **Cerrada para administración de accesos** | Capacidades operativas no relacionadas pueden sobrevivir por diseño; se muestran y requieren gobierno fuera de un cambio silencioso de rol. |
| **B6. Ausencia de consulta canónica de capacidades** | `build_administrative_access_summary` recarga al usuario y separa asignación, efectividad, catálogo, origen, perfil y anomalías. | `resumen-acceso` requiere `manage_users` y minimiza permisos externos a conteo/tipo. | Modal de sólo lectura, sin inputs de grants/revokes. | B cubre roles cero/múltiples, drift, cache, superusuario, perfiles, fuentes y secretos. | **Cerrada** | Es diagnóstico actual, no historial forense; eso corresponde a BH-061. |
| **B7. Alta administrativa duplicada desde Personal** | `create_access_for_personal` sólo acepta `EMPLEADO`/`PROFESIONAL`; el alta administrativa dedicada permanece separada. | `ADMINISTRADOR`/`CLIENTE` producen `INVALID_ROLE`. | Personal sólo ofrece Empleado y Profesional. | Pruebas backend y frontend verifican rechazo y ausencia de creación parcial. | **Cerrada** | Ninguno identificado dentro del producto. |
| **B8. Lectura de Personal demasiado amplia** | No hay mutación en lectura; directorio de skills tiene serializer mínimo. | Lista/detalle completos requieren `manage_personal`; `manage_skills` sólo recibe id, nombre, apellido y estado laboral. | La pantalla oculta contacto y acceso en modo skills. | Pruebas A, Personal y skills verifican scopes. | **Cerrada** | Las APIs de otros dominios pueden exponer sus propios datos conforme a contratos ajenos a BH-059. |
| **B9. Semántica parcial de estados** | Cuenta, Cliente y Personal mantienen flags independientes; reactivación laboral valida Personal; Cliente inactivo se preserva y advierte. | Actions separadas, motivos y códigos estables; revocaciones no reparan roles ambiguos. | Las confirmaciones describen exactamente qué estado cambia. | D cubre perfiles, ownership, no-op, rollback, tokens y estados ambiguos. | **Cerrada** | Un access JWT previo puede recuperar validez al reactivar hasta vencer. Está advertido y documentado. |

## 4. Matriz de criterios de cierre del análisis original

| # | Criterio | Evidencia consolidada | Resultado | Riesgo/deuda |
|---:|---|---|---|---|
| 1 | Ninguna API de Usuario, Personal o auditoría usa `is_staff` como autoridad de negocio. | Permission classes efectivas y doble validación en servicios; staff-only rechazado. | **Cumple** | `IsAdminUser` permanece en dominios legacy fuera de estas superficies. |
| 2 | DELETE y rutas alternativas no cambian acceso fuera de comandos semánticos. | DELETE 405, Admin sensible read-only, GroupAdmin retirado, reversión de acceso bloqueada. | **Cumple** | Shell/DBA no forman parte del límite de la aplicación. |
| 3 | Lectura de rol, perfiles, capacidades, origen y anomalías. | Resumen B canónico y modal read-only. | **Cumple** | Sin línea temporal avanzada. |
| 4 | Cambio general estricto con conjunción, perfiles y auditoría. | Servicio C, action estricta, payload limitado, motivo y evento semántico. | **Cumple** | Ninguno material. |
| 5 | Flujos laborales limitados y sin alta administrativa. | Servicios Personal y opciones UI sólo EMPLEADO/PROFESIONAL. | **Cumple** | Ninguno material. |
| 6 | Autoescalamiento, superusuario y escalamiento indirecto bloqueados. | Autoacción y objetivos superusuario rechazados; promoción exige conjunción; alta laboral no crea admin. | **Cumple** | Superusuario conserva autoridad técnica global por diseño de Django. |
| 7 | Desactivación/degradación con protección concurrente común. | Lock del grupo ADMINISTRADOR compartido; carreras PostgreSQL 2/2. | **Cumple** | La reproducibilidad global de concurrencia queda para BH-060. |
| 8 | Degradación no deja autoridad administrativa residual sin detectar/rechazar. | Proyección previa y conflicto estable para tres capacidades de mutación de accesos. | **Cumple** | `view_audit`/`revert_audit` y permisos operativos se diagnostican, pero no se consideran autoridad para cambiar accesos. |
| 9 | Perfiles/ownership preservados y efectos de estado explícitos. | Servicios y pruebas de Usuario/Cliente/Personal, incluida revocación total/laboral. | **Cumple** | Cliente inactivo con cuenta activa es un estado admitido y advertido. |
| 10 | No hay otorgamiento arbitrario de permisos o grupos. | No hay endpoint/serializer/UI de grant; GroupAdmin está retirado y campos de Usuario son read-only. | **Cumple** | Modelos Django permiten aprovisionamiento externo por código/DB de confianza. |
| 11 | Éxitos auditados sin secretos y reversión genérica sin acceso. | Eventos con actor, objetivo, motivo, antes/después; no-op y rollback sin falso éxito; pruebas de ausencia de password/token. | **Cumple** | Presentación forense avanzada queda para BH-061. |
| 12 | Pruebas de aceptación pasan, dejando estabilización transversal a BH-060. | 452 pruebas backend conformes, 1 expectativa legacy clasificada, 283 frontend, checks y build. | **Cumple con deuda de test identificada** | Suite grande supera 20 minutos y logging es excesivo. |
| 13 | BH-061/BH-062 no fueron adelantados. | No hay historial avanzado ni editor genérico/matriz de permisos. | **Cumple** | Ninguno. |

## 5. Evidencia integral de seguridad

### 5.1 Autoridad efectiva e `is_staff`

La autoridad real sigue el contrato Django:

1. permisos del grupo BusinessRole;
2. permisos de grupos no canónicos;
3. `user_permissions` individuales;
4. bypass técnico de superusuario.

`CanManageUsers`, `CanManageUsersAndAssignRoles`, `CanManagePersonal`,
`CanManageSkills`, `CanViewAudit` y `CanRevertAudit` consultan `has_perm()`.
Los comandos sensibles vuelven a cargar el actor y comprueban actividad y
permisos. Por tanto, alterar el rol declarado por el frontend o `Personal.rol`
no concede autoridad.

`is_staff` queda como indicador técnico y habilitación del sitio Django Admin.
No autoriza las superficies de administración de acceso. Las pruebas confirman
los dos sentidos: staff sin permiso falla y no-staff con permiso efectivo puede
operar.

### 5.2 BusinessRole, promociones y degradaciones

- La primitiva elimina únicamente los cuatro grupos BusinessRole y agrega un
  destino canónico.
- La operación general requiere `manage_users + assign_roles` tanto en API como
  en servicio.
- CLIENTE requiere Cliente; EMPLEADO/PROFESIONAL requieren Personal activo;
  ADMINISTRADOR no crea perfiles ni convierte `is_staff`.
- La autoacción y los objetivos superusuario se rechazan.
- Promover a ADMINISTRADOR no puede hacerse desde Personal.
- Degradar al último administrador activo se bloquea con lock común.
- Antes de degradar se proyectan grupos técnicos y permisos individuales. Si
  sobreviviría `manage_users`, `assign_roles` o `manage_personal`, no hay cambio.
- Una capacidad técnica no escalante se preserva y queda visible; no se borra
  sin una decisión de gobierno.

El respaldo del último administrador debe ser otro usuario activo, no
superusuario, con exactamente ADMINISTRADOR. No cuentan `is_staff`, permisos
individuales, cuentas inactivas ni múltiples roles.

### 5.3 Cliente, Personal y ciclo de cuenta

Las invariantes están separadas:

- `Usuario.is_active` controla autenticación;
- `Cliente.activo` controla el perfil Cliente;
- `Personal.activo` controla el estado laboral;
- `Personal.rol` expresa función laboral, no autoridad digital;
- BusinessRole expresa acceso y debe ser único para una cuenta operativa.

La baja/reactivación de cuenta no altera perfiles. La baja/reactivación laboral
no altera la cuenta. Reactivar CLIENTE conserva un Cliente inactivo y advierte;
reactivar un rol laboral exige Personal activo. Vincular no asigna rol ni activa
entidades. La revocación laboral sólo acepta un rol laboral o el estado final
CLIENTE; no convierte cuentas sin rol ni ADMINISTRADOR implícitamente.

### 5.4 Sesiones y tokens

La baja y la reactivación agregan a blacklist todos los refresh SimpleJWT
pendientes y no vencidos, dentro de la misma transacción del cambio y su
auditoría. Las respuestas sólo exponen el contador, nunca JWT ni JTI.

Riesgo aceptado para este cierre: un access token emitido antes de la baja se
rechaza mientras la cuenta está inactiva, pero puede volver a ser válido al
reactivar hasta su vencimiento configurado de 7 días. SimpleJWT no consulta la
blacklist de refresh para access tokens normales. La API/UI emiten
`PREEXISTING_ACCESS_TOKENS_MAY_REGAIN_VALIDITY`; el refresh anterior permanece
bloqueado. Esto satisface el criterio original de política documentada, pero no
equivale a revocación inmediata de access tokens.

### 5.5 Auditoría semántica, Admin y reversión

Los eventos de rol, cuenta y Personal registran actor, objetivo, fuente,
transición y motivo. Las operaciones compuestas correlacionan IDs subordinados.
Los no-op no duplican eventos y un fallo de auditoría revierte la mutación.
Pruebas específicas verifican que no se incluyan contraseñas, hashes ni tokens.

Contención alternativa:

- Usuario: estados, superusuario, staff, grupos y permisos son read-only;
- GroupAdmin: no registrado;
- Cliente: usuario/estado read-only, sin alta/baja genérica;
- Personal: usuario/estado read-only, sin baja ni acciones masivas;
- Auditoria en Admin: inmutable;
- reversión histórica: no copia ni revierte campos de acceso de Personal.

## 6. Permisos individuales y grupos técnicos: decisión E

### 6.1 Fuentes posibles

| Fuente | Puede aportar permisos efectivos | Detección | Otorgamiento por producto | Tratamiento al degradar admin |
|---|---:|---|---|---|
| BusinessRole canónico | Sí | Rol, capacidades y drift | Sólo comandos semánticos | Se reemplaza por el destino. |
| Grupo técnico no canónico | Sí | Origen `TECHNICAL_GROUP`, nombre y capacidades canónicas | No existe API/UI/Admin | Se conserva; bloquea si aporta autoridad de mutación de accesos. |
| Permiso individual | Sí | Origen `INDIVIDUAL`; permisos externos sólo por conteo/tipo | No existe API/UI/Admin | Se conserva; bloquea si aporta autoridad de mutación de accesos. |
| Superusuario | Sí, bypass Django | `SUPERUSER_ACCOUNT` y origen `SUPERUSER` | No gestionable por comandos de negocio | Objetivo protegido; no se degrada. |

Los permisos fuera de `BusinessPermission.ALL` no se publican por código ni se
convierten en catálogo otorgable. La lectura sólo informa cantidad y tipo de
fuente. La búsqueda global de `.user_permissions.add()` sólo encontró usos en
pruebas, no en código de aplicación; las migraciones agregan permisos a grupos
canónicos, no a usuarios. La asignación de BusinessRole está encapsulada en los
servicios de onboarding y acceso.

### 6.2 Inventario real de la base disponible

Consulta de sólo lectura sobre PostgreSQL local:

- 4 usuarios: 3 activos, 1 staff y 1 superusuario;
- 0 usuarios con permisos individuales;
- 0 asignaciones individuales dentro o fuera del catálogo;
- 0 grupos técnicos con miembros o capacidades de negocio;
- 3 usuarios con rol válido y 1 sin BusinessRole;
- 0 cuentas con múltiples roles;
- 0 drift en CLIENTE, EMPLEADO, PROFESIONAL o ADMINISTRADOR;
- 0 miembros actuales del grupo ADMINISTRADOR;
- la única advertencia de autoridad fuera de rol corresponde al superusuario
  protegido, que también explica `NO_ROLE`.

No se observaron excepciones individuales o técnicas reales que requieran una
operación de revocación. La ausencia de un ADMINISTRADOR de negocio en esta base
local es una condición de aprovisionamiento del entorno, no una excepción E ni
un defecto del comando: antes de operar ese entorno debe crearse una cuenta
administrativa regular mediante el onboarding dedicado.

Este inventario no sustituye una consulta equivalente en producción. Si otro
entorno contiene excepciones, el resumen B las mostrará y C impedirá una
degradación administrativa insegura.

### 6.3 Decisión

E no es requisito para cerrar BH-059 porque:

1. no hay excepciones reales en la base inspeccionada;
2. el sistema detecta origen individual/técnico, drift y permisos externos;
3. una excepción de administración de accesos bloquea la degradación;
4. no existe una ruta para otorgar excepciones desde el producto;
5. una revocación automática o silenciosa podría eliminar autoridad operativa
   legítima sin política aprobada.

E pasa a ser necesario sólo si un inventario de otro entorno descubre
excepciones que deban resolverse mediante el producto, o si se aprueba una
política de revocación administrativa auditada. Incluso en ese caso debe ser
revocación acotada, nunca grant genérico.

**Decisión formal:** `BH-059 E = DIFERIBLE`.

## 7. Integración de módulos

| Módulo | Evidencia | Resultado | Observación |
|---|---|---|---|
| Gestión de usuarios | A/B/C/D, CRUD contenido, resumen y actions | **Conforme** | Envelopes heredados 403 ahora son `error.code=PERMISSION_DENIED`. |
| Gestión de Personal | Scopes completos/mínimos, alta, vínculo, estado y revocaciones | **Conforme** | CLIENTE/ADMINISTRADOR vinculados se advierten como incompatibles para acceso laboral. |
| Habilidades técnicas | `manage_skills`, directorio mínimo y pruebas frontend | **Conforme** | Flags legacy no son autoridad ni campos escribibles. |
| `/me/` y rutas | Capacidades efectivas limitadas al catálogo, ProtectedRoute y navegación | **Conforme** | `is_staff` no forma parte del contrato de sesión. |
| Diagnóstico capilar | Permiso efectivo más habilidad DIAGNOSTICO activa | **Conforme con test legacy** | El único fallo espera tolerancia de campos que el contrato estricto rechaza. |
| Turnos | Lectura global, creación, llegada, reprogramación/cancelación y skills | **Conforme** | Pruebas representativas no muestran regresión de roles. |
| Caja/pagos manuales | `register_payment`, `confirm_deposit` y scopes de Caja | **Conforme** | EMPLEADO conserva registro de pago; PROFESIONAL no lo recibe por rol. |
| Incidencias financieras | `reconcile_external_payment`, lectura, resolución y cierre | **Conforme** | Staff sin permiso no sustituye la autoridad efectiva. |

Se observó deuda legacy fuera de BH-059: `FichaTecnicaViewSet` y otras APIs de
dominio todavía usan `IsAdminUser`. El análisis A ya la clasificó fuera de las
superficies de Usuario, Personal y auditoría. No permite editar grupos, permisos
o estados de acceso y no fue introducida por A–D; por eso no bloquea este cierre,
pero debe tratarse en una iniciativa de autorización de dominio.

## 8. Pruebas y contratos

### 8.1 Backend

Todas las corridas se hicieron secuencialmente y con bases de prueba nuevas.

| Bloque | Resultado | Cobertura principal |
|---|---:|---|
| Núcleo BH-059 | **230/230** | A/B/C, roles, `/me/`, CRUD contenido, cuenta/tokens, Personal, skills y envelopes 403. |
| Concurrencia PostgreSQL | **2/2** | degradación/degradación y degradación/desactivación. |
| Diagnóstico y turnos | **119/120 conformes** | diagnóstico, lectura/creación/gestión/llegada de turnos y compatibilidad de skills. |
| Caja e incidencias financieras | **101/101** | pagos manuales, intents, lectura/resolución/cierre y conciliación externa. |

Total representativo: **453 pruebas ejecutadas; 452 conformes y 1 expectativa
legacy desactualizada**.

El fallo clasificado es
`DiagnosisAuthorizationApiTests.test_legacy_flags_are_read_only_in_personal_serializer`.
Espera `serializer.is_valid() == True` al enviar `realiza_diagnostico`,
`realiza_lavado` y `realiza_color`. `PersonalSerializer.to_internal_value`
rechaza todo campo fuera de `WRITABLE_FIELDS`; A documenta expresamente que una
escritura que incluya flags legacy debe rechazarse. Las pruebas de seguridad de
Personal también exigen 400 y cero mutación ante campos de privilegio, vínculo
o resumen. Por tanto, la expectativa del test es obsoleta; cambiar la
implementación para satisfacerla debilitaría el contrato estricto.

Una corrida inicial de 583 pruebas superó 20 minutos por volumen y logging y fue
interrumpida sin resultado final; no se usa como evidencia. Los mismos dominios
se dividieron luego en los bloques secuenciales anteriores. La duración y el
ruido de señales/middleware son evidencia de estabilización pendiente para
BH-060, no de un defecto funcional de BH-059.

### 8.2 Frontend

- **33/33 suites**;
- **283/283 pruebas**;
- incluye Gestión de Usuarios, Gestión de Personal, ProtectedRoute,
  SessionContext, diagnóstico/operaciones, turnos, Caja e incidencias.

El build productivo completó correctamente con warnings legacy:

- dependencia dinámica;
- Browserslist desactualizado;
- imports/variables sin uso y dependencias de hooks en archivos ajenos a
  BH-059;
- export anónimo en utilidades.

No hubo error de compilación ni warning nuevo en `GestionUsuarios` o
`GestionPersonal`.

### 8.3 Checks, migraciones y secretos

- `python manage.py check`: **0 observaciones**;
- `python manage.py migrate --check`: **sin migraciones pendientes**;
- `python manage.py makemigrations --check --dry-run`: **No changes detected**;
- escaneo del árbol tracked para firmas comunes de AWS, GitHub, Stripe, claves
  privadas y JWT: **sin coincidencias**;
- no se observaron JWT/JTI ni contraseñas en respuestas o auditorías de acceso.

`check --deploy` conserva seis warnings generales:

- HSTS no configurado;
- redirect HTTPS no forzado;
- default de `SECRET_KEY` inseguro;
- cookies de sesión y CSRF no marcadas secure;
- `DEBUG=True` por defecto.

Son deuda de configuración de despliegue, no un cambio de BH-059. Deben
resolverse antes de declarar un entorno productivo seguro.

## 9. Riesgos y deuda técnica

| Riesgo/deuda | Severidad | Tratamiento |
|---|---|---|
| Access token previo puede recuperar validez tras reactivar, hasta 7 días. | Media | Aceptado y visible para cierre; reducir lifetime o agregar epoch de credenciales en una iniciativa separada si se exige revocación inmediata. |
| Inventario E sólo comprobado en la base local disponible. | Media | Repetir consulta de sólo lectura en producción antes del despliegue. |
| La base local no tiene ADMINISTRADOR de negocio regular. | Media operacional | Aprovisionar mediante alta dedicada; el superusuario no cuenta como respaldo de negocio. |
| No hay comando de revocación de excepciones individuales/técnicas. | Baja actualmente | E sigue diferible mientras no existan excepciones o política aprobada. |
| Permisos operativos no escalantes sobreviven a una degradación. | Baja/por diseño | Se detectan y muestran; no eliminarlos silenciosamente. |
| Un test legacy espera tolerancia de flags que ahora se rechazan. | Baja | Actualizar expectativa en estabilización, sin cambiar el contrato seguro. |
| Suite ampliada lenta y logging excesivo. | Media de mantenibilidad | BH-060: aislamiento, tiempos y salida determinista. |
| APIs legacy de otros dominios aún usan `IsAdminUser`. | Media de autorización | Auditoría/refactor de autorización de dominio separado; no habilitan administración de acceso. |
| Seis warnings de `check --deploy`. | Alta para producción, no para cierre BH-059 | Endurecer configuración por entorno antes de producción. |

## 10. Pendientes de tareas posteriores

### BH-060 — estabilización

- hacer reproducible la matriz completa sin depender de `--keepdb` contaminado;
- aislar bases para concurrencia y evitar ejecuciones paralelas incompatibles;
- reducir o capturar el logging de señales/middleware en tests;
- actualizar la expectativa legacy de flags de habilidades al rechazo estricto;
- definir timeouts y partición oficial de suites;
- incorporar política E2E y control de reloj/fechas.

No se atribuye a BH-060 la implementación de grants/revokes ni cambios de
autorización funcional.

### BH-061 — historial y forense

- historial unificado por actor/objetivo;
- filtros, paginación, retención y exportación;
- correlación y presentación de eventos compuestos;
- análisis temporal de cambios de acceso.

Los eventos semánticos ya existen; BH-061 no debe reabrir la reversión genérica
de campos de acceso.

### BH-062 — UX administrativa avanzada

- comparación y matrices visuales de roles/capacidades;
- flujos de aprobación, accesibilidad y acciones masivas seguras;
- eventual UX de diagnóstico/revocación de excepciones sólo si E se aprueba.

BH-062 no debe convertirse en editor libre de permisos Django o grupos
técnicos.

## 11. Registro de cierre documental y backlog

### 11.1 Estado propuesto

Sobre el baseline funcional auditado
`46641e818d24683312323dc970a2f36e4a008f35`, se propone registrar:

```text
BH-059 — CERRADO TÉCNICAMENTE
Incrementos A–D — VALIDADOS
Incremento E — DIFERIBLE
```

El cierre es técnico y no declara habilitación productiva. E permanece
diferible: no se crea ni se propone un editor de permisos individuales o grupos
técnicos, y no se inicia una operación de grants/revokes.

### 11.2 Transferencias propuestas a BH-060

| Pendiente transferido | Criterio de salida propuesto |
|---|---|
| Expectativa legacy del serializer de Personal | Actualizar el test para exigir rechazo estricto de `realiza_diagnostico`, `realiza_lavado` y `realiza_color`, sin debilitar el contrato del serializer. |
| Reproducibilidad de bases y `--keepdb` | Aislar el estado de las bases de prueba y documentar una estrategia reproducible para ejecuciones limpias y persistentes. |
| Pruebas concurrentes deterministas | Controlar orden, barreras y resultados terminales válidos sin depender del scheduling accidental ni ejecutar suites incompatibles en paralelo. |
| Control de reloj y fechas | Fijar reloj, zona horaria y fechas límite en pruebas sensibles al día u hora de ejecución. |
| Lentitud y logging excesivo | Reducir o capturar la salida de señales/middleware y establecer presupuestos de duración verificables. |
| Partición oficial de suites | Definir bloques, comandos, timeouts y orden oficial para núcleo, concurrencia, operaciones, finanzas y frontend. |

La transferencia sólo registra deuda de estabilización. **BH-060 no se inicia**
mediante este cierre y no recibe cambios funcionales de autorización ni un
editor de permisos.

### 11.3 Riesgos independientes

| Riesgo independiente | Tratamiento posterior; no bloquea el cierre técnico |
|---|---|
| Access tokens emitidos antes de una baja pueden recuperar validez después de reactivar la cuenta y antes de vencer. | Evaluar reducción del lifetime o un epoch de credenciales si se exige revocación inmediata. No corresponde a E ni a BH-060. |
| La base local auditada no tiene un administrador de negocio regular. | Aprovisionar uno mediante el flujo dedicado antes de operar ese entorno; el superusuario técnico no cuenta como respaldo de negocio. |
| Otros dominios conservan autorizaciones legacy basadas en `IsAdminUser`/`is_staff`. | Inventariar y normalizar en una iniciativa de autorización de dominio separada; no habilitan administración de acceso dentro de BH-059. |
| La configuración productiva mantiene pendientes señalados por `check --deploy`. | Resolver o aceptar explícitamente HSTS, HTTPS, secretos, cookies seguras, hosts y `DEBUG` antes de habilitar producción. |

Estos riesgos se registran de forma separada de BH-060 y de BH-059 E. No se
inician BH-061 ni BH-062 y no se modifica su alcance mediante este cierre.

## 12. Veredicto final

Las nueve brechas originales y los trece criterios de cierre tienen evidencia
implementada y ejecutable. Los riesgos restantes están documentados, no abren
otorgamiento arbitrario de permisos y pertenecen a operación, estabilización,
despliegue o tareas posteriores. El único test no conforme contiene una
expectativa anterior al contrato estricto de A y no representa una regresión de
seguridad.

BH-059 = LISTO PARA CERRAR

BH-059 E = DIFERIBLE
