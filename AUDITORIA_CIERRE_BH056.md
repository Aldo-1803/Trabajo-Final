# Auditoría final de cierre — BH-056

Fecha: 2026-10-24

## Veredicto ejecutivo

BH-056 puede cerrarse. Las skills canónicas son la única autoridad técnica para
compatibilidad entre Personal y Servicios, y para autorización técnica de
Diagnóstico. No se encontró ningún uso productivo de
`Personal.realiza_diagnostico`, `Personal.realiza_lavado` o
`Personal.realiza_color` que decida elegibilidad.

Decisión sobre los flags legacy: **opción B, mantenerlos temporalmente sin
autoridad**. Retirarlos ahora requeriría una migración destructiva y actualizar
fixtures, pruebas y contratos de presentación, sin aportar seguridad adicional
al cierre. Su permanencia no habilita ningún fallback operativo.

No se modificó implementación ni se inició BH-057 durante esta auditoría.

## 1. Modelo canónico

Confirmado en `bohemiacore/gestion/models.py` y migración `0021`:

- `Habilidad`: catálogo con `code` único y estado `activa`.
- `PersonalHabilidad`: asignación reversible con estado `activa` y constraint
  único `(personal, habilidad)`.
- `ServicioHabilidad`: requisito técnico explícito y constraint único
  `(servicio, habilidad)`.
- `Servicio.habilidades_requeridas`: M2M mediante `ServicioHabilidad`.

La migración
`bohemiacore/gestion/migrations/0021_habilidad_personalhabilidad_serviciohabilidad.py`:

- siembra idempotentemente `DIAGNOSTICO`, `LAVADO` y `COLORACION` activas;
- hace backfill de asignaciones desde los tres flags legacy;
- reactiva una asignación preexistente en lugar de duplicarla;
- clasifica inicialmente Servicios de categorías diseño/color como
  `COLORACION` y complemento como `LAVADO`;
- deja esa inferencia textual confinada al backfill histórico.

La administración de asignaciones usa servicios transaccionales en
`personal_skill_services.py`, conserva una sola fila por Personal/skill,
permite asignar, revocar y reactivar, rechaza altas/reactivaciones de skills
inactivas y registra auditoría semántica.

## 2. Autoridad de compatibilidad

La fuente central es
`bohemiacore/gestion/service_skill_compatibility.py`:

- `service_skill_policy()` reúne los requisitos de todos los Servicios;
- `ServiceSkillPolicy.filter_personal()` y `personal_can_perform()` exigen
  Personal activo, asignación activa y `Habilidad.activa=True`;
- `personal_can_perform_service()` y `personal_can_perform_services()` ofrecen
  consultas reutilizables para uno o varios Servicios.

`TurnoAvailabilityService.matching_schedules()` y `validate_slot()` consumen
esa política. Disponibilidad, creación para Cliente, creación para tercero y
reprogramación convergen en `validate_slot()`. La reprogramación pasa la lista
completa de Servicios del Turno.

No hay lectura runtime de `realiza_color`, `realiza_lavado` ni nombres de
categoría en esta decisión. Tampoco existe OR o fallback hacia flags legacy.

### Coincidencias textuales restantes

| Ubicación | Uso | Clasificación | ¿Autoridad técnica? |
|---|---|---|---|
| migración `0021` | Backfill inicial por `diseño`, `color` y `complemento` | Migración histórica | No |
| `test_skills_migration.py` | Verifica la clasificación inicial | Test | No |
| `test_turno_skill_compatibility.py` | Compara clasificación legacy y canónica | Test de regresión | No |
| `test_diagnosis_authorization_api.py` | Demuestra que el recomendador usa disponibilidad canónica | Test | No |
| `ServiciosQuimicosViewSet` en `views.py` | Selecciona Servicios para historial químico | Función de catálogo/historial | No decide Personal elegible |
| creación de promoción last-minute en `views.py` | Elige Servicios a promocionar por categoría Color | Marketing | No decide Personal elegible |

## 3. Diagnóstico

La escritura de `DiagnosticoCapilarViewSet` exige conjuntamente:

1. `gestion.create_diagnosis`;
2. `Usuario.is_active=True`;
3. vínculo a `Personal` activo;
4. asignación `PersonalHabilidad` activa;
5. skill `DIAGNOSTICO` activa.

El permiso está en `CanCreateDiagnosisWithSkill`; la comprobación reutilizable
está en `user_has_active_skill()`. El autor se deriva de `request.user` y no del
payload.

Para lectura:

- Cliente autenticado: sólo sus propios diagnósticos;
- lectura técnica global: `gestion.manage_technical_record` más
  `DIAGNOSTICO` activa;
- escritura sin gestión global: limitada a registros cuyo autor es el actor;
- DELETE: 405.

Dentro de `DiagnosticoCapilarViewSet` hay **cero** usos de `is_staff`,
`realiza_diagnostico` o `Personal.rol` como autoridad. Ser ADMINISTRADOR o
`is_staff` no reemplaza permiso ni skill.

## 4. `Personal.rol`

Coincidencias productivas relevantes:

| Archivo / ubicación | Uso | Clasificación | Decisión |
|---|---|---|---|
| `models.py`, `Personal.__str__()` | Muestra `get_rol_display()` | Descriptivo | Correcto |
| `views.py`, `selector_personal` | Devuelve `get_rol_display()` como `funcion` | Presentación | Correcto; la compatibilidad se filtra mediante `service_skill_policy()` |
| `views.py`, `crear_bloqueo` | Selecciona el primer `rol='colorista'` activo como destinatario de un bloqueo | Productivo legacy | Deuda BH-059, no blocker BH-056 |

`crear_bloqueo` usa el rol como sustituto de una persona concreta en una ruta
administrativa de bloqueo. No declara capacidad para un Servicio, no participa
en disponibilidad, creación o reprogramación y no constituye fallback de
skills. Debe reemplazarse por un `personal_id` explícito o una configuración de
agenda en BH-059.

Las demás coincidencias de `rol='colorista'` están en fixtures/tests y no son
autoridad productiva.

## 5. Gestión de skills

Confirmado:

- catálogo, listado de asignaciones, asignación, revocación y reactivación
  requieren `gestion.manage_skills`;
- los servicios vuelven a comprobar el permiso contra el actor persistido;
- `manage_personal` sin `manage_skills` recibe 403 y no cambia asignaciones;
- un permiso individual `manage_skills` funciona;
- `is_staff` sin el permiso no funciona;
- un ADMINISTRADOR efectivo puede operar sin `is_staff` porque la autoridad es
  el permiso, no el BusinessRole;
- las operaciones son atómicas y una falla de auditoría revierte el cambio.

## 6. Frontend

`frontend/src/pages/admin/GestionPersonal.js` separa:

- función laboral (`Personal.rol`);
- estado laboral;
- acceso/BusinessRole del Usuario;
- skills canónicas.

El catálogo y las asignaciones sólo se consultan y modifican cuando
`hasPermission('gestion.manage_skills')` es verdadero. Tener sólo
`manage_personal` no muestra controles de edición de skills. Los flags legacy
se muestran identificados como legacy, con controles `readOnly` y `disabled`.
Aunque forman parte del estado general del formulario por compatibilidad, el
serializer backend también los declara read-only.

No se encontró lógica JavaScript que calcule compatibilidad técnica. Los flujos
consumen selectores/disponibilidad del backend.

## 7. Inventario exhaustivo de flags legacy

### Consumidores de implementación y presentación

| Archivo | Uso | Tipo | ¿Autoridad? | ¿Eliminar ahora? |
|---|---|---|---|---|
| `bohemiacore/gestion/models.py` | Define las tres columnas legacy | Esquema productivo de compatibilidad de datos | No | No; requiere migración coordinada |
| `bohemiacore/gestion/serializers.py` | Los expone como read-only | Presentación/API compatible | No | Posible sólo junto al retiro coordinado |
| `bohemiacore/gestion/admin.py` | Campos read-only y resumen informativo | Presentación | No | Posible, pero no necesario para cerrar |
| `frontend/src/pages/admin/GestionPersonal.js` | Estado de formulario y presentación legacy deshabilitada | Presentación | No | Posible, pero conviene coordinar con contrato API |
| migración `0001_initial.py` | Creación histórica de columnas | Migración histórica | No | No se reescribe |
| migración `0006_historicalbloqueoagenda_and_more.py` | Estado histórico generado | Migración histórica | No | No se reescribe |
| migración `0021_habilidad_personalhabilidad_serviciohabilidad.py` | Fuente del backfill único | Migración histórica | No en runtime | No se reescribe |

### Consumidores de tests y fixtures

Todos los siguientes usos crean datos, verifican preservación durante cambios
de acceso/estado o prueban expresamente que los flags no tienen autoridad:

| Archivo | Uso | Tipo | ¿Autoridad? | ¿Eliminar ahora? |
|---|---|---|---|---|
| `gestion/tests/test_admin_usuario_crud_containment.py` | Fixture/preservación | Test | No | No; actualizar al retirar columnas |
| `gestion/tests/test_diagnosis_authorization_api.py` | Flags opuestos a skills y read-only | Test de no autoridad | No | No mientras exista transición |
| `gestion/tests/test_full_work_access_revocation_services.py` | Preservación de datos | Test | No | No; actualizar al retirar columnas |
| `gestion/tests/test_personal_access_api.py` | Fixture/preservación | Test | No | No; actualizar al retirar columnas |
| `gestion/tests/test_personal_access_creation_services.py` | Fixture/contrato | Test | No | No; actualizar al retirar columnas |
| `gestion/tests/test_personal_access_services.py` | Preservación de skills/flags | Test | No | No; actualizar al retirar columnas |
| `gestion/tests/test_personal_security.py` | No escalamiento/cambios laterales | Test | No | No; actualizar al retirar columnas |
| `gestion/tests/test_personal_status_services.py` | Preservación al cambiar estado | Test | No | No; actualizar al retirar columnas |
| `gestion/tests/test_skills_migration.py` | Backfill exhaustivo e idempotente | Test de migración | No | Conservar como evidencia histórica |
| `gestion/tests/test_turno_skill_compatibility.py` | Demuestra que true no habilita y false no bloquea | Test de no autoridad | No | Conservar durante transición |
| `gestion/tests/test_work_access_revocation_services.py` | Preservación de datos | Test | No | No; actualizar al retirar columnas |
| `usuarios/test_account_reactivation_services.py` | Preservación de datos al reactivar | Test | No | No; actualizar al retirar columnas |
| `frontend/src/pages/admin/GestionPersonal.test.js` | Fixture y comportamiento de UI | Test | No | Actualizar junto con la UI |

No existe consumidor real que bloquee el retiro futuro. La razón para no
retirarlos en BH-056 es evitar una migración destructiva puramente cosmética,
no una dependencia operativa.

## 8. Servicios, agenda y recursos

`Servicio.habilidades_requeridas` es la declaración futura y persistente de
compatibilidad técnica. Las categorías textuales sólo fueron antecedente del
backfill inicial.

Las responsabilidades permanecen separadas:

- skills: capacidad técnica Personal–Servicio;
- `HorarioLaboral.permite_diseno_color` y `permite_complemento`: restricción
  temporal de agenda, aplicada por códigos canónicos y no por texto;
- requisitos/equipamiento: capacidad de recursos;
- bloqueos y solapamientos: disponibilidad temporal.

Una skill no evita horario, bloqueos, solapamientos ni equipamiento, y esas
dimensiones tampoco conceden una skill.

## 9. Multiservicio y fail-closed

La política calcula la **unión** de skills requeridas por todos los Servicios y
aplica **AND** sobre cada skill única para el Personal asignado.

Comportamiento confirmado:

- skill requerida inactiva: Servicio no ejecutable / sin slots;
- `PersonalHabilidad` inactiva: incompatible;
- Personal inactivo: incompatible;
- asignación faltante: incompatible;
- varias skills: deben estar todas presentes y activas;
- Servicio sin requisitos: no agrega restricción técnica;
- nunca se prueba un flag legacy después de fallar una skill.

## 10. Preparación para BH-057

BH-056 deja disponibles consultas reutilizables para “¿qué Personal está
técnicamente habilitado para este Servicio o conjunto de Servicios?” mediante:

- `service_skill_policy(servicios).filter_personal(queryset)`;
- `personal_can_perform_service(personal, servicio)`;
- `personal_can_perform_services(personal, servicios)`.

BH-057 puede combinarlas con historial, riesgo, permiso de workflow y una
eventual skill de revisión para producir
`APTO`/`ADVERTENCIA`/`REQUIERE_REVISION`/`NO_APTO` y seleccionar revisor. Ese
workflow no fue implementado aquí.

## 11. Cobertura y validación

Cobertura localizada:

| Requisito | Evidencia principal |
|---|---|
| Modelo y constraints | `test_skills_api.py::SkillModelTests` |
| Seed/backfill e idempotencia | `test_skills_migration.py` |
| `manage_skills` y permiso individual | `test_skills_api.py` |
| `manage_personal` sin `manage_skills` | `test_skills_api.py` y `GestionPersonal.test.js` |
| `is_staff`/BusinessRole sin autoridad | `test_skills_api.py`, `test_diagnosis_authorization_api.py` |
| Disponibilidad y selector | `test_turno_skill_compatibility.py` |
| Creación forzada/aceptada | `test_turno_skill_compatibility.py` |
| Reprogramación | `test_turno_skill_compatibility.py` |
| Multiservicio AND | `test_turno_skill_compatibility.py` |
| Personal activo/inactivo y fail-closed | `test_turno_skill_compatibility.py`, `test_diagnosis_authorization_api.py` |
| Diagnóstico permission + skill | `test_diagnosis_authorization_api.py` |
| ADMINISTRADOR sin skill | `test_diagnosis_authorization_api.py` |
| Legacy flags sin autoridad | ambas suites anteriores |
| Frontend separado y edición por permiso | `GestionPersonal.test.js` |

Validación ejecutada en esta auditoría:

- backend focalizado (modelo, migración, gestión, compatibilidad y
  Diagnóstico): **60/60**;
- frontend `GestionPersonal`: **16/16**;
- `manage.py check`: sin issues;
- `manage.py makemigrations --check --dry-run`: sin cambios;
- `compileall gestion`: OK;
- `git diff --check`: sin errores; sólo avisos informativos CRLF/LF.

La ejecución backend requirió el `venv` del repositorio y `PYTHONUTF8=1`; sin
UTF-8, impresiones con emoji de middleware/signals fallan en consola CP1252.
Eso es deuda de infraestructura de tests, no un fallo de las reglas BH-056.
No se abrió BH-060.

Como evidencia adicional ya documentada durante los incrementos:

- Diagnóstico: 26/26;
- skills/Turnos: 107/107;
- Personal: 34/34;
- roles, `/me/` y registro: 77/77;
- frontend relacionado: 79/79.

## 12. Deuda aceptada no bloqueante

| Backlog | Deuda separada |
|---|---|
| BH-057 | Evaluación de riesgo, estados APTO/ADVERTENCIA/REQUIERE_REVISION/NO_APTO, revisión y selección de revisor. |
| BH-058 | HOLD, pagos, seña, Mercado Pago y conciliación; sin relación con autoridad de skills. |
| BH-059 | Retirar rutas administrativas legacy, en especial selección implícita por `rol='colorista'` en `crear_bloqueo`; coordinar retiro final de columnas/contratos legacy. |
| BH-060 | Robustecer entorno de tests: dependencias del Python global, base de test persistente y salida UTF-8 de middleware/signals. No abierto por esta auditoría. |
| BH-061 | Ampliación/UI de auditoría y limpieza de navegación legacy fuera del alcance de BH-056. |
| BH-062 | Normalizar usos restantes de `is_staff` en flujos legacy ajenos a Diagnóstico. |

Ninguna de estas deudas devuelve autoridad técnica a flags, rol, `is_staff` o
BusinessRole dentro de BH-056.

## Conclusión

La autoridad final queda en `ServicioHabilidad` + `Habilidad.activa` +
`PersonalHabilidad.activa` + `Personal.activo`, con unión multiservicio, AND y
fail-closed. Diagnóstico usa permiso efectivo + skill canónica. Los flags legacy
se conservan temporalmente sólo para compatibilidad y presentación read-only,
sin autoridad operativa.

El siguiente backlog recomendado es **BH-057**.

**BH-056 = LISTO PARA CERRAR**
