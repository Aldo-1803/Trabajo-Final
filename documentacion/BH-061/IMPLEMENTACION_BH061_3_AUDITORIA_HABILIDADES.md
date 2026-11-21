# BH-061 Incremento 3 — Auditoría de habilidades técnicas

**Fecha:** 2026-11-08

**Baseline de inicio:**
`f7a88580bc6a170d6fec9ee456325d93fb695ce3`

## 1. Alcance

Este incremento completa el contrato de auditoría de los comandos
administrativos que asignan, revocan o reactivan `PersonalHabilidad`.

No crea permisos Django, modelos, columnas, migraciones ni rutas. Tampoco
convierte `Personal.rol` o las habilidades técnicas en `BusinessRole`, amplía
la correlación de BH-061.2 ni modifica operaciones financieras.

## 2. Contratos de servicio y eventos

Los tres servicios exigen ahora un `reason` explícito:

- `assign_skill(..., reason=...)`;
- `revoke_skill(..., reason=...)`;
- `reactivate_skill(..., reason=...)`.

El motivo se recorta y debe contener entre 3 y 500 caracteres. `None`, vacío,
sólo espacios o valores fuera del rango producen
`InvalidPersonalSkillReason` antes de cualquier mutación.

Las fuentes estables son:

| Comando | Evento efectivo | `source` |
|---|---|---|
| Asignar una habilidad nueva | `PERSONAL_SKILL_ASSIGNED` | `gestion.personal_skill_services.assign_skill` |
| Asignar una habilidad previamente revocada | `PERSONAL_SKILL_REACTIVATED` | `gestion.personal_skill_services.assign_skill` |
| Revocar | `PERSONAL_SKILL_REVOKED` | `gestion.personal_skill_services.revoke_skill` |
| Reactivar explícitamente | `PERSONAL_SKILL_REACTIVATED` | `gestion.personal_skill_services.reactivate_skill` |

La fuente identifica el comando administrativo real. El servidor no inventa
un motivo ni presenta una reactivación solicitada mediante `assign_skill()`
como si hubiera usado el endpoint explícito de reactivación.

## 3. Payload de auditoría

Cada cambio efectivo conserva `event`, `activa` y la separación
`valor_anterior`/`valor_nuevo`, y agrega en el estado nuevo:

- `source`;
- `reason`;
- `actor_id`;
- `personal_id`;
- `skill_id`;
- `previous_active`;
- `current_active`.

Cuando el Personal tiene Usuario vinculado se incluye únicamente `user_id`.
Si no existe vínculo, el campo se omite. No se guardan nombres, apellidos,
email, teléfonos, contraseñas, hashes, JWT, tokens ni credenciales.

Los eventos son operaciones simples y no reciben `operation_id`.

## 4. Semántica preservada

- Cambio efectivo: exactamente un evento semántico.
- Asignación o reactivación ya activa: no-op sin evento.
- Revocación ya aplicada: no-op sin evento.
- Motivo inválido, falta de permiso, objetivo inexistente o catálogo no válido:
  cero eventos de éxito.
- Fallo al crear `Auditoria`: rollback de creación o cambio de `activa`.
- La restricción única de `(personal, habilidad)` continúa evitando duplicados.

Se conserva el contrato técnico existente:

- un Personal inactivo puede recibir administración anticipada de habilidades;
- esa habilidad no es efectiva mientras Usuario o Personal estén inactivos;
- asignar o reactivar exige una `Habilidad` activa;
- revocar sigue permitido aunque la habilidad del catálogo esté inactiva, para
  no impedir retirar una autorización residual.

Las operaciones internas de seed, migración o fixtures usan ORM y no son
comandos administrativos ni simulan un motivo humano.

## 5. API y frontend

Las rutas existentes se mantienen:

- `POST /api/gestion/personal/{id}/habilidades/asignar/` recibe
  `habilidad_id` y `motivo`;
- `POST /api/gestion/personal/{id}/habilidades/{habilidad_id}/revocar/` recibe
  `motivo`;
- `POST /api/gestion/personal/{id}/habilidades/{habilidad_id}/reactivar/`
  recibe `motivo`.

Los serializers rechazan campos inesperados y motivos inválidos. El esquema de
error sigue usando `{'error': {'code', 'detail'}}`; un motivo inválido devuelve
`INVALID_REASON` con HTTP 400.

La autorización continúa basada exclusivamente en el permiso efectivo
`gestion.manage_skills`: `is_staff` no concede acceso y un actor con permiso
efectivo funciona aunque no sea staff.

`GestionPersonal` incorpora un motivo administrativo por Personal, limita su
longitud, mantiene deshabilitados los comandos hasta alcanzar el mínimo y envía
el campo en las tres operaciones. El directorio mínimo de habilidades no se
modificó y continúa exponiendo sólo `id`, `nombre`, `apellido` y `activo`.

## 6. Compatibilidad histórica

No se actualizaron eventos anteriores. `valor_nuevo` continúa siendo JSON
flexible y la API de auditoría puede leer un `PERSONAL_SKILL_ASSIGNED`
histórico que no contiene `reason` ni `source`.

Los campos anteriores de los eventos nuevos se conservaron para no romper
consumidores existentes.

## 7. Pruebas y regresiones

Todas las pruebas backend se ejecutaron en PostgreSQL con
`bohemiacore.test_settings` y `StablePostgresTestRunner`:

- pruebas focales finales de habilidades y lectura histórica: **34/34**;
- regresión BH-056, Personal BH-059, permisos técnicos BH-060,
  diagnóstico/finalización y auditoría: **192/192**;
- regresión adicional de acceso, roles y estados: **173/173**;
- frontend `GestionPersonal.test.js`: **17/17**;
- total de ejecuciones finales: **416/416**.

La cobertura positiva y negativa incluye:

1. asignación, revocación y reactivación efectivas;
2. actor, Personal, habilidad y Usuario vinculado correctos;
3. fuentes y motivos normalizados;
4. motivo ausente, vacío, corto o excesivo;
5. `manage_skills`, `is_staff` y permiso efectivo sin staff;
6. habilidad o Personal inexistentes;
7. catálogo inactivo y Personal inactivo según su contrato;
8. no-op y cardinalidad exacta;
9. rollback de las tres mutaciones ante fallo de auditoría;
10. rechazo sin cambios ni eventos de éxito;
11. lectura histórica sin campos nuevos;
12. ausencia de secretos y datos personales innecesarios;
13. consumidor frontend y directorio mínimo.

Comprobaciones adicionales:

- `manage.py check`: sin observaciones;
- `makemigrations --check --dry-run`: sin cambios;
- `migrate --check`: sin migraciones pendientes;
- build frontend: correcto, con warnings preexistentes ajenos a
  `GestionPersonal`;
- `git diff --check`: correcto.

## 8. Riesgos residuales

- Los eventos históricos no obtienen motivo o fuente retroactivamente.
- La cardinalidad en carreras concurrentes de habilidades permanece como
  evidencia focal pendiente del incremento de pruebas posterior; no se
  añadieron sleeps ni retries.
- La señal CRUD genérica no sustituye estos eventos semánticos y conserva sus
  riesgos históricos documentados.
- No se implementaron exportación, retención, filtros ni protección forense
  append-only.

No se inició BH-061 Incremento 4 ni BH-062.

`BH-061 INCREMENTO 3 — IMPLEMENTADO Y VALIDADO`
