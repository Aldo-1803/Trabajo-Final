# BH-056 — Incremento A: modelo canónico de skills

## Alcance entregado

Se incorporó el modelo canónico de habilidades, el seed/backfill legacy, API
administrativa semántica, auditoría y una UI mínima de Gestión Personal.

No se modificaron:

- `TurnoAvailabilityService`, creación o reprogramación de Turnos;
- reserva de Cliente;
- `DiagnosticoCapilarViewSet`;
- BusinessRole ni permisos ya existentes;
- BH-057 o BH-058.

Los flags `Personal.realiza_diagnostico`, `realiza_lavado` y `realiza_color`
siguen presentes y son la única autoridad de compatibilidad operativa hasta el
Incremento B.

## Modelos y constraints

| Modelo | Campos relevantes | Constraint |
|---|---|---|
| `Habilidad` | `code` único, `nombre`, `descripcion`, `activa` | `code` es la identidad estable. |
| `PersonalHabilidad` | `personal`, `habilidad`, `activa`, `fecha_asignacion` | único `(personal, habilidad)`. |
| `ServicioHabilidad` | `servicio`, `habilidad` | único `(servicio, habilidad)`. |
| `Servicio.habilidades_requeridas` | M2M vía `ServicioHabilidad` | Semántica futura AND; no activa aún disponibilidad. |

No se agregaron nivel, certificación, vencimiento, observación ni
`asignado_por`.

## Seed y backfill

La migración `0021_habilidad_personalhabilidad_serviciohabilidad` crea de forma
idempotente:

| Code | Nombre |
|---|---|
| `DIAGNOSTICO` | Diagnóstico |
| `LAVADO` | Lavado |
| `COLORACION` | Coloración |

Para cada Personal existente, crea o reactiva la asignación correspondiente si
el flag legacy almacenado es `True`; no modifica flags ni asume defaults. En
particular, `realiza_lavado=True` produce `LAVADO` activa.

Para Servicios, replica exactamente la clasificación vigente en
`TurnoAvailabilityService`:

- categoría normalizada que contiene `diseño` o `color` → `COLORACION`;
- categoría normalizada que contiene `complemento` → `LAVADO`;
- las demás categorías no reciben requisito inventado.

La base local inspeccionada no contiene categorías ni Servicios (0/0), por lo
que no hay categorías reales ambiguas o inesperadas que reportar. La migración
deja sin requisito todo nombre que no coincide con la regla legacy comprobable.

## API y autorización

| Endpoint | Acción | Autoridad |
|---|---|---|
| `GET /api/gestion/habilidades/` | catálogo, incluso skills inactivas | `gestion.manage_skills` |
| `GET /api/gestion/personal/{id}/habilidades/` | asignaciones de un Personal | `gestion.manage_skills` |
| `POST /api/gestion/personal/{id}/habilidades/asignar/` | asigna o reactiva con `habilidad_id` | `gestion.manage_skills` |
| `POST /api/gestion/personal/{id}/habilidades/{skill}/revocar/` | `activa=False`, sin borrar | `gestion.manage_skills` |
| `POST /api/gestion/personal/{id}/habilidades/{skill}/reactivar/` | `activa=True` | `gestion.manage_skills` |

No se usa `manage_personal`, `is_staff` ni BusinessRole como sustituto. Se
permite asignar a Personal inactivo para conservar habilitaciones ante una
reactivación. No se permite asignar o reactivar una `Habilidad.activa=False`.

## Auditoría

Las operaciones usan un servicio transaccional y escriben en `Auditoria` los
eventos `PERSONAL_SKILL_ASSIGNED`, `PERSONAL_SKILL_REVOKED` y
`PERSONAL_SKILL_REACTIVATED`, con actor, Personal, skill y estados anterior y
nuevo. Un fallo al escribir auditoría provoca rollback de la asignación.

## Gestión Personal

- La ruta/navegación admite `gestion.manage_personal` **o**
  `gestion.manage_skills`.
- Quien sólo posee `manage_personal` conserva gestión laboral y no recibe
  lectura ni controles de skills canónicas.
- Quien posee `manage_skills` ve asignaciones canónicas y puede
  asignar/revocar/reactivar.
- Los tres checkboxes previos permanecen visibles como flags **LEGACY de sólo
  lectura**, para evitar doble edición contradictoria durante la coexistencia.

## Tests y validación

Se agregaron tests backend para constraints, asignación/revocación/reactivación,
autoridad por permiso individual, staff sin permiso, Cliente, anónimo,
ADMINISTRADOR con `is_staff=False`, rollback de auditoría y backfill de las ocho
combinaciones de flags legacy más clasificación de Servicios.

- El intérprete global carece de `django-simple-history`, pero el `venv` raíz
  esperado incorpora `django-simple-history 3.11.0` con Django 5.2.7. No se
  cambiaron dependencias; el repositorio no posee manifiesto de dependencias,
  una inconsistencia pendiente de BH-060.
- `venv\Scripts\python.exe manage.py check`: exitoso.
- `venv\Scripts\python.exe manage.py makemigrations --check`: sin cambios.
- La migración `0021` se aplicó correctamente en la base de pruebas aislada.
- Tests BH-056: **13/13 aprobados**.
- Regresión personal/access, roles y `/me/`: **59/59 aprobados**.
- Regresión de creación, disponibilidad, lectura, gestión y llegada de Turnos:
  **73/73 aprobados**.
- Frontend focalizado: **8 suites / 125 tests aprobados**.
- Build frontend, `python -m compileall gestion` y `git diff --check`:
  exitosos (el build conserva warnings preexistentes fuera de este incremento).

## Siguiente límite

El Incremento B podrá sustituir las reglas legacy de disponibilidad por
`Servicio.habilidades_requeridas` y `PersonalHabilidad`. No debe iniciarse sin
validar esta migración y el backfill en un entorno con dependencias backend.
