# Análisis BH-056 — skills / habilitaciones de Personal

**Alcance:** análisis de modelo y plan de evolución. No se modificó código,
migraciones, permisos ni frontend. BH-057 y BH-058 quedan fuera de alcance.

## 1. Estado actual e inventario

### `Personal`

`gestion.models.Personal` define tres booleanos técnicos y un campo de función
laboral:

| Campo | Definición | Consumidores backend | Consumidor frontend | Efecto actual |
|---|---|---|---|---|
| `rol` | `Personal.rol`, choices `colorista`, `asistente`, `administrador` | serializador de sesión; administración; un endpoint legacy de bloqueos | Gestión Personal | Función laboral, salvo un uso legacy puntual detallado abajo. |
| `realiza_diagnostico` | `Personal`, default `False` | serializador, Django admin y preservación en servicios/tests de Personal | Gestión Personal | Informativo/configurable; **no** filtra diagnóstico, disponibilidad ni creación de Turnos. |
| `realiza_lavado` | `Personal`, default `True` | `TurnoAvailabilityService.matching_schedules` | Gestión Personal | Filtra elegibilidad para categorías cuyo nombre contiene `complemento`; afecta disponibilidad y creación por medio de la validación canónica. |
| `realiza_color` | `Personal`, default `False` | `TurnoAvailabilityService.matching_schedules` | Gestión Personal | Filtra elegibilidad para categorías cuyo nombre contiene `diseño` o `color`; afecta disponibilidad y creación por medio de la validación canónica. |

Ubicaciones relevantes de definición o exposición:

- `bohemiacore/gestion/models.py`: modelo, flags y permiso declarado
  `gestion.manage_skills`.
- `bohemiacore/gestion/serializers.py`: `PersonalSerializer` expone los tres
  flags de lectura/escritura.
- `bohemiacore/gestion/admin.py`: los muestra y edita como “Habilidades
  Técnicas”.
- `frontend/src/pages/admin/GestionPersonal.js`: formulario con tres checkboxes
  y badges de listado.
- `bohemiacore/gestion/turno_creation_services.py`: único consumidor de
  elegibilidad operativa de `realiza_color` y `realiza_lavado`.

Los servicios de acceso, alta/baja y reactivación de Personal no usan los flags
para decidir autorización: los preservan al cambiar acceso o estado. Las suites
de Personal contienen fixtures y aserciones de esa preservación, por lo que son
consumidores de compatibilidad, no de elegibilidad.

### Diagnóstico, ficha, fórmulas y color

- `DiagnosticoCapilarViewSet` no consulta `realiza_diagnostico`; actualmente
  basa crear/editar y lectura global en `request.user.is_staff`. El permiso
  `gestion.create_diagnosis` existe en `BusinessPermission`, pero no gobierna
  ese ViewSet todavía.
- `DiagnosticoCapilar.profesional` registra un `Usuario`, no una habilidad ni un
  `Personal`; el flujo no valida perfil Personal activo.
- `Servicio.plantilla_formula`, impactos capilares, servicios químicos y
  `RequisitoServicio` (equipamiento) no están vinculados a skills.
- No hay relación `Servicio ↔ Personal`, `Servicio ↔ habilidad`, ni categoría
  técnica estable. El único vínculo actual es inferido desde texto de categoría.

## 2. `Personal.rol`: significado y usos reales

Los únicos valores declarados son `colorista`, `asistente` y `administrador`.
Su significado correcto es **función laboral legacy/descriptiva**: etiqueta de
puesto, filtro administrativo y dato de perfil (`profiles.personal.function_role`
en `/me`).

No debe ser autoridad de autenticación, BusinessRole, permisos Django ni
habilitación técnica. Un mismo Personal puede ser `asistente` y tener una skill
adicional; un `colorista` no debe obtener técnica o permiso por inferencia.

| Uso productivo de `rol` | Evaluación |
|---|---|
| `PersonalSerializer`, Django admin, Gestión Personal, filtros y `/me` | Presentación, administración o identidad laboral; válido como función legacy. |
| `Personal.__str__` | Informativo. |
| `crear_bloqueo` en `gestion/views.py` selecciona el primer `Personal` activo con `rol='colorista'` | Uso indebido como sustituto de persona/capacidad. Es frágil si hay más de un colorista y no expresa skill. Debe aislarse en una futura corrección de agenda, no convertirse en regla de skills. |
| Disponibilidad y `TurnoCreationService` | No usan `rol`; correcto, aunque usan flags legacy y texto de categoría. |

`BusinessRole` sigue siendo acceso al sistema; puede diferir de `Personal.rol`.
Por ejemplo, un `PROFESIONAL` no se vuelve colorista, ni un
`ADMINISTRADOR` obtiene capacidad técnica por el rol. Un `CLIENTE` tampoco
recibe skills laborales.

## 3. Servicios y compatibilidad vigente

La compatibilidad se concentra en `TurnoAvailabilityService.matching_schedules`.
`TurnoCreationService.create()` llama a `validate_slot()`, por lo que la misma
regla se aplica a disponibilidad, reserva propia, creación para Cliente y
reprogramación que reutiliza la validación canónica.

| Servicio / tipo actual | Habilidad necesaria actual | Regla actual | Problema |
|---|---|---|---|
| Categoría cuyo nombre contiene `Diseño` o `Color` | `realiza_color=True` | Horario activo + `permite_diseno_color=True` + flag Personal | Regla por substring de nombre; no hay requisito declarado por Servicio ni distingue coloración de otros trabajos. |
| Categoría cuyo nombre contiene `Complemento` | `realiza_lavado=True` | Horario activo + `permite_complemento=True` + flag Personal | Mezcla “servicio corto/complemento” con lavado; depende del nombre de categoría. |
| Cualquier otra categoría, incluido Servicio sin categoría | Ninguna | Sólo Personal/horario activos, tiempo, bloqueos y equipamiento | Corte, peinado, tratamiento y diagnóstico no tienen compatibilidad técnica explícita. |
| Diagnóstico capilar | Ninguna | `is_staff` en el ViewSet legacy | No utiliza ni permiso canónico ni flag `realiza_diagnostico`. |
| Fórmula / impacto químico | Ninguna | Metadatos del Servicio y reglas capilares | No restringe quién puede ejecutar o formular. |

`HorarioLaboral.permite_diseno_color` y `permite_complemento` **no son skills**:
son capacidad temporal del horario. Deben mantenerse como segunda dimensión de
elegibilidad junto a agenda, bloqueos y equipamiento.

La recomendación automática de diagnóstico (`_recomendar_primer_hueco_disponible`)
duplica parte de la clasificación textual; aunque luego llama a generación de
slots, debe converger en la consulta canónica de compatibilidad cuando se
implemente BH-056.

## 4. Alternativas evaluadas

| Alternativa | Ventajas | Limitaciones | Decisión |
|---|---|---|---|
| A. Booleanos en `Personal` | Cambio mínimo. | Nueva columna/UI/migración por cada habilidad; no representa requisitos de Servicio ni auditoría de asignación. | Descartada como arquitectura destino. |
| B. `Habilidad` + M2M `Personal.habilidades` | Catálogo extensible y asignación individual. | M2M implícita no conserva estado de revocación ni es buena base para auditoría. | Base elegida, con relación explícita. |
| C. `PersonalServicio` solamente | Precisión por servicio. | Duplica mantenimiento al crear servicios, no expresa competencias transversales ni revisión futura. | No usar como modelo principal. |
| D. Híbrido skills + requisitos por Servicio | Skills reutilizables, Servicios declarativos y reglas simples. | Requiere dos relaciones explícitas y migración gradual. | **Recomendado.** |

## 5. Arquitectura objetivo recomendada

### Modelo mínimo

```text
Habilidad
  code: CharField(unique=True, estable, no editable funcionalmente)
  nombre: CharField
  descripcion: TextField(blank=True)
  activa: BooleanField(default=True)

PersonalHabilidad
  personal: FK(Personal)
  habilidad: FK(Habilidad)
  activa: BooleanField(default=True)
  fecha_asignacion: DateTimeField(auto_now_add=True)
  UniqueConstraint(personal, habilidad)

Servicio.habilidades_requeridas
  M2M(Habilidad, through=ServicioHabilidad, blank=True)

ServicioHabilidad
  servicio: FK(Servicio)
  habilidad: FK(Habilidad)
  UniqueConstraint(servicio, habilidad)
```

La relación explícita `PersonalHabilidad` es preferible a un M2M implícito:
`activa` conserva una revocación sin borrar el vínculo y `fecha_asignacion`
aporta trazabilidad operacional. La auditoría existente puede registrar altas y
cambios de este modelo con el actor de request. No agregar en v1 nivel,
certificación, vencimiento, observación ni `asignado_por`: no existe requisito
de negocio demostrado y el actor ya pertenece al registro de auditoría.

`ServicioHabilidad` no necesita nivel ni alternativas en v1. Todas las skills
asociadas son obligatorias (**AND**); un servicio de una sola skill es el caso
normal. No se implementan grupos OR, equivalencias o un motor genérico hasta
que haya un servicio real que los requiera.

### Catálogo inicial probado por código

El catálogo inicial debe contener exclusivamente los tres conceptos existentes:

| Code estable | Nombre | Fuente legacy |
|---|---|---|
| `DIAGNOSTICO` | Diagnóstico | `realiza_diagnostico` |
| `LAVADO` | Lavado | `realiza_lavado` |
| `COLORACION` | Coloración | `realiza_color` |

No hay evidencia actual para sembrar definitivamente `DECOLORACION`, `CORTE`,
`TRATAMIENTO`, `PEINADO` o `REVISION_TECNICA`. Pueden agregarse después sólo si
Servicios reales o una regla BH-057 los requieren. No se debe inferir el
catálogo desde `Personal.rol` ni desde nombres libres de categoría.

## 6. Rules de autorización: skill, permission y BusinessRole

| Concepto | Responde | No responde |
|---|---|---|
| BusinessRole | Qué experiencia de negocio/base de permisos tiene el Usuario. | Qué trabajo técnico puede realizar. |
| Django permission | Si el actor puede invocar una capacidad del sistema. | Si la persona asignada está técnicamente habilitada. |
| `Personal.rol` | Puesto o función laboral legacy. | Acceso o aptitud técnica. |
| Skill activa | Qué trabajo puede ejecutar/revisar un Personal activo. | Acceso a UI/API administrativa. |

Reglas propuestas:

- Crear/consultar Turnos para terceros, llegada, reprogramar y cancelar siguen
  regidos por sus permisos actuales; no requieren skill del actor administrativo.
- Elegir Personal para un Servicio requiere que el **Personal asignado** esté
  activo y tenga todas las skills activas requeridas por ese Servicio. La
  habilidad no reemplaza el permiso que permite crear el Turno.
- Crear o editar un diagnóstico técnico debe requerir conjuntamente
  `gestion.create_diagnosis`, Usuario activo, perfil Personal activo y skill
  `DIAGNOSTICO` activa. Esto reemplaza el chequeo legacy por `is_staff` de ese
  ViewSet; no se implementa en este análisis.
- `manage_technical_record`, `manage_formulas` y `finalize_service` se mantienen
  permission-only hasta que se asocie una acción concreta a un requisito técnico
  real. No inferir `COLORACION` por existir una fórmula de Servicio.
- `gestion.manage_skills` gobierna administración de catálogo y asignación o
  revocación de skills. No concede ninguna skill al propio actor.
- No existe derivación automática desde BusinessRole. Los seeds iniciales sólo
  trasladan datos legacy; toda asignación nueva es explícita.

## 7. Disponibilidad, Turnos y compatibilidad futura

La consulta única propuesta para disponibilidad es conceptualmente:

```text
Personal activo
AND horario activo compatible con esa fecha/hora
AND sin bloqueo/conflicto/equipamiento insuficiente
AND para cada skill requerida por Servicio:
    PersonalHabilidad.activa
    AND Habilidad.activa
```

`TurnoAvailabilityService.matching_schedules()` debe ser la fuente de esa
elegibilidad. `validate_slot()` y `TurnoCreationService` ya la reutilizan; al
migrar no se deben crear validaciones paralelas. Si un Servicio refiere una
skill inactiva, debe fallar cerrado como configuración inválida y no considerar
a todo el Personal apto.

La correspondencia legacy inicial debe hacerse por Servicio/categoría existente:

- categorías actualmente tratadas como diseño/color → `COLORACION`;
- categorías actualmente tratadas como complemento → `LAVADO`;
- el resto queda sin requisito hasta clasificación explícita del negocio.

La regla por nombre no debe quedar como fuente permanente: cada `Servicio`
debe declarar sus `habilidades_requeridas`. Categoría puede ayudar a poblar la
migración inicial, pero no autoriza compatibilidad futura.

## 8. BH-057: frontera explícita

BH-056 resuelve catálogo, asignación, elegibilidad básica Servicio–Personal y
la pregunta “quién puede hacer técnicamente esta tarea”.

BH-057 resuelve historial, riesgo, evaluación
`APTO`/`ADVERTENCIA`/`REQUIERE_REVISION`/`NO_APTO` y workflow de revisión. No
se implementa aquí.

Para que BH-057 pueda seleccionar revisores, su futura consulta debe pedir:

1. Personal activo con `REVISION_TECNICA` activa, cuando exista esa skill;
2. las skills técnicas que el Servicio o evaluación requiera (por ejemplo,
   `DIAGNOSTICO` o `COLORACION`);
3. el permiso de workflow que BH-057 defina.

`REVISION_TECNICA` no se siembra ahora porque no es una habilidad existente en
el código. BH-057 podrá crearla explícitamente junto a su workflow, sin mezclar
el modelo de evaluación con el catálogo BH-056.

## 9. Frontend y administración

`GestionPersonal` ya separa visualmente función laboral, estado laboral y
acceso digital, pero los checkboxes actuales mezclan skills dentro del payload
general de Personal. La UI mínima objetivo debe usar cuatro bloques distintos:

1. **Función laboral:** `Personal.rol`.
2. **Acceso al sistema:** BusinessRole y estado de `Usuario` vinculado.
3. **Permisos adicionales:** información/enlace al mecanismo de permisos, sin
   presentarlos como habilidades.
4. **Habilidades técnicas:** listado de catálogo activo y asignaciones activas
   de ese Personal.

La vista de Personal puede seguir requiriendo `gestion.manage_personal`. El
panel de modificación de habilidades y sus endpoints deben requerir
`gestion.manage_skills`; así, alguien que administra datos laborales no obtiene
por accidente la capacidad de habilitación técnica. El backend es la autoridad:
el guard frontend sólo acompaña esa separación.

El permiso `gestion.manage_skills` ya está declarado y forma parte del
catálogo canónico, pero no tiene consumidor productivo específico. Es suficiente
para gobernar el primer incremento, con permisos individuales permitidos. Alta,
revocación y cambios deben generar entradas de `Auditoria` con actor, fecha,
estado anterior y nuevo. La ampliación de auditoría y su UI pertenece a BH-061;
BH-056 sólo debe asegurar que sus modelos/eventos sean auditables.

## 10. Migración legacy por fases

1. **Esquema y catálogo:** crear los modelos, restricciones, serializers de
   lectura y seed idempotente de `DIAGNOSTICO`, `LAVADO`, `COLORACION`.
2. **Backfill de datos:** por cada Personal, crear asignación activa si el flag
   equivalente es `True`. El valor default actual `realiza_lavado=True` debe
   preservarse literalmente: asigna `LAVADO` a cada Personal que hoy lo tenga.
3. **Requisitos de Servicio:** poblar `ServicioHabilidad` sólo para las reglas
   legacy comprobables (color/diseño y complemento); revisar manualmente los
   demás Servicios, sin inventar skills.
4. **Lectura canónica:** mover `TurnoAvailabilityService` y validación de
   creación a skills; mantener temporalmente los flags y verificar que ambos
   caminos resulten equivalentes durante el despliegue.
5. **API/UI:** devolver asignaciones de skills y migrar Gestión Personal a los
   endpoints de administración de skills. El diagnóstico técnico pasa a
   permission + skill en el mismo incremento o permanece explícitamente fuera
   de uso hasta hacerlo; no debe convivir indefinidamente con `is_staff`.
6. **Retiro:** tras una migración de datos verificada y sin consumidores,
   eliminar flags de serializer, admin, frontend, fixtures/tests y finalmente
   columnas legacy. No eliminarlos en el primer despliegue.

## 11. Compatibilidad: consumidores afectados

| Impacto | Archivos / consumidores exactos | Motivo |
|---|---|---|
| Crítico | `bohemiacore/gestion/turno_creation_services.py` | Fuente de compatibilidad para disponibilidad y validación de creación/reprogramación. |
| Alto | `bohemiacore/gestion/views.py` (`consultar_disponibilidad` y recomendación de diagnóstico) | Expone o duplica la selección de slots que debe usar la regla canónica. |
| Alto | `bohemiacore/gestion/views.py` (`DiagnosticoCapilarViewSet`) | Debe abandonar `is_staff` y requerir permission + `DIAGNOSTICO`. |
| Alto | `bohemiacore/gestion/models.py`, `serializers.py`, `admin.py` | Definición, contrato API y operación administrativa de los flags. |
| Alto | `frontend/src/pages/admin/GestionPersonal.js` | Envía, edita y presenta los flags actuales. |
| Medio | `bohemiacore/gestion/models.py` (`HorarioLaboral`) y `serializers.py` | Sus flags son temporales, no se eliminan; deben combinarse con skills sin cambiar su semántica. |
| Medio | `bohemiacore/gestion/views.py` (`crear_bloqueo`) | Usa `rol='colorista'` como sustituto legacy de persona/capacidad. |
| Medio | `frontend/src/pages/admin/GestionPersonal.test.js` | Fixtures y aserciones de UI deben pasar a asignaciones de skills. |
| Medio | `gestion/tests/test_personal_access*.py`, `test_personal_status*.py`, `test_work_access_revocation*.py`, `test_full_work_access_revocation*.py`, `test_personal_security.py`, `test_admin_usuario_crud_containment.py`, `usuarios/test_account_reactivation_services.py` | Construyen, cambian o verifican los flags legacy que se deben conservar durante transición y luego actualizar. |
| Bajo | `usuarios/serializers.py` (`function_role`) y SessionContext | Expone función laboral, no flags ni autoridad técnica; no requiere migración de skill. |

## 12. Tests requeridos para implementación

1. Catálogo: code único, habilidad activa/inactiva y seed idempotente.
2. Asignación: Personal con/sin skill, asignación inactiva y unicidad.
3. Servicio: uno o varios requisitos obligatorios; Servicio sin requisitos;
   requisito que apunta a skill inactiva falla cerrado.
4. Disponibilidad: sólo aparece Personal activo con todas las skills requeridas,
   además de horario, bloqueos y equipamiento existentes.
5. Creación y reprogramación de Turno: el backend rechaza Personal sin skill
   aunque el cliente fuerce su ID; acepta el Personal compatible.
6. Permiso sin skill y skill sin permiso: el primero no permite diagnóstico
   técnico; el segundo no permite invocar esa acción. Los permisos de agenda no
   se alteran por skills.
7. ADMINISTRADOR sin skill no puede ejecutar diagnóstico técnico por ser ADMIN;
   permiso individual + skill sí funciona sin depender del BusinessRole.
8. Diagnóstico: perfil Personal inactivo o skill `DIAGNOSTICO` inactiva falla
   cerrado; se registra el profesional válido.
9. Administración: `manage_personal` sin `manage_skills` no cambia
   asignaciones; `manage_skills` individual puede hacerlo; las rutas directas
   frontend/backend responden de forma coherente.
10. Auditoría: alta, activación y revocación de `PersonalHabilidad` registran
    actor y valores anterior/nuevo.
11. Migración: cada combinación de los tres booleanos produce exactamente las
    skills activas esperadas; es reejecutable y no duplica vínculos.
12. Regresión: comparación de las categorías legacy clasificadas antes/después
    del switch y conservación de los casos de disponibilidad existentes.

## Decisión final y primer incremento

- **Arquitectura recomendada:** modelo híbrido: catálogo `Habilidad`, relación
  explícita `PersonalHabilidad` y requisitos declarativos de skills por
  `Servicio`; horarios y permisos continúan siendo dimensiones independientes.
- **Modelo mínimo:** `Habilidad(code, nombre, descripcion, activa)`,
  `PersonalHabilidad(personal, habilidad, activa, fecha_asignacion)` y relación
  explícita `ServicioHabilidad` para requisitos obligatorios AND.
- **Migración legacy:** seed de `DIAGNOSTICO`, `LAVADO`, `COLORACION`; backfill
  1:1 desde los booleanos; clasificar sólo Servicios cubiertos por las reglas
  actuales; dualidad temporal y retiro de flags al final.
- **Primer incremento de implementación:** modelos/migración/seed/backfill,
  servicio canónico de compatibilidad en `TurnoAvailabilityService`, validación
  de creación, endpoints de lectura/asignación protegidos por `manage_skills` y
  UI de Gestión Personal separada. Incluir diagnóstico permission + skill si se
  expone esa acción en el incremento.
- **Archivos afectados:** los listados en la tabla de compatibilidad; el núcleo
  es `models.py`, `turno_creation_services.py`, `views.py`, `serializers.py`,
  `admin.py`, `GestionPersonal.js` y sus tests.
- **Tests requeridos:** catálogo/asignación, elegibilidad de Servicio,
  disponibilidad, creación/reprogramación, permission+skill, administración,
  auditoría y backfill.
- **Riesgos:** categorías por texto, duplicación de lógica de disponibilidad,
  defaults legacy de lavado, endpoint diagnóstico basado en `is_staff` y retiro
  prematuro de flags con fixtures activas.
- **Relación con BH-057:** BH-056 aporta quién está habilitado; BH-057 consume
  esa consulta para evaluación, riesgo y revisión técnica, sin implementar su
  workflow en este incremento.
