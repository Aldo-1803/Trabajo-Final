# Flujos profesionales — Incremento 0: contención de finalización

**Fecha:** 2026-11-11

**Baseline de partida:** `62bc96c17b0e8aeedfdb207b94ecd4e2bea54381`

**Rama:** `save/work-in-progress`

**Estado:** validado para publicación

## 1. Objetivo y alcance

Este incremento contiene la transición de un Turno a `REALIZADO` antes de
publicar una interfaz React profesional. Introduce una autoridad única de
dominio, autorización por objeto, lock PostgreSQL, atomicidad e idempotencia
persistente.

No implementa:

- UI de finalización o diagnóstico;
- integración de fichas legacy;
- una política nueva de diagnóstico o sincronización capilar;
- BH-063 (Turnos asistidos/presenciales);
- BH-064 (alta rápida de Cliente presencial);
- cobro, conciliación, stock ni liquidación de saldo;
- bypass de supervisión o BusinessRole nuevos.

BH-062 permanece cerrado y no se modificó su auditoría.

## 2. Comportamiento anterior

`POST /api/gestion/turnos/{id}/finalizar_turno/` ejecutaba directamente en el
ViewSet:

1. rechazaba sólo un Turno ya `REALIZADO`;
2. guardaba `estado=REALIZADO` sin transacción ni lock;
3. disparaba tres receptores `post_save` que reaccionaban a cualquier guardado
   de un Turno realizado;
4. creaba un diagnóstico automático si el perfil tenía algún dato;
5. ejecutaba el motor de diagnóstico;
6. volvía a producir cuidados/rutinas desde la vista;
7. creaba promociones de retoque.

La acción exigía `finalize_service` y también `diagnosis.create` con Personal y
habilidad `DIAGNOSTICO` activos, aun cuando no se creara diagnóstico.

## 3. Defectos caracterizados antes del refactor

La primera ejecución útil sobre PostgreSQL de los cinco tests iniciales obtuvo
**11 fallas** por defectos reales:

| Defecto | Evidencia previa |
|---|---|
| Estados inválidos | `SOLICITADO`, `ESPERANDO_SENA`, `SUGERIDO`, `CANCELADO`, `AUSENTE`, `PENDIENTE` y `EN_PROCESO` respondieron 200 y quedaron realizados. |
| Retry | La segunda solicitud devolvió 400 en vez de recuperar el resultado. |
| Ownership | Un profesional autorizado pudo finalizar un Turno asignado a otro Personal. |
| Señales por estado | Guardar nuevamente un Turno realizado duplicó la notificación final. |
| Impacto nulo | Un Servicio sin `impacto_estado` borró `Cliente.estado_general`. |

La inspección confirmó además:

- diagnóstico, agendas, notificaciones y promociones sin identidad única por
  finalización;
- cuidados y rutinas con más de un productor;
- posible estado `REALIZADO` con efectos parciales ante una excepción;
- dos solicitudes concurrentes capaces de leer el mismo estado inicial;
- resultado capilar multiservicio dependiente del orden de Detalles.

## 4. Política de transición

La única transición admitida provisionalmente es:

```text
CONFIRMADO -> REALIZADO
```

Todo otro estado sin un resultado de finalización compatible responde:

```json
{
  "code": "INVALID_FINALIZATION_TRANSITION",
  "detail": "Sólo un Turno confirmado puede finalizarse."
}
```

con HTTP 409.

`EN_PROCESO` ya existe en el modelo, pero no se habilitó como origen en este
incremento. Tampoco se agregó otro estado. Cobro, conciliación, saldo y stock no
participan de la transición.

## 5. Contrato de autorización

La API y el servicio de dominio requieren:

1. usuario autenticado y activo;
2. permiso Django efectivo `gestion.finalize_service`;
3. perfil `Personal` existente y activo;
4. `turno.profesional` igual al Personal del actor.

Las condiciones se revalidan dentro del servicio después de adquirir el lock.
No se consulta BusinessRole nominal ni `is_staff`, no existe bypass y un permiso
global no permite finalizar Turnos ajenos.

Se eliminó la dependencia de `diagnosis.create` y de la habilidad
`DIAGNOSTICO`. Finalizar no crea un diagnóstico automático: copiar un snapshot
del perfil no constituye una evaluación profesional y no se inventa evidencia
para satisfacer la transición.

## 6. Diseño transaccional

La operación vive en
`gestion/turno_finalization_services.py::finalize_turno` y usa
`@transaction.atomic`.

Secuencia:

1. valida autoridad sin consultar el Turno;
2. normaliza la clave idempotente;
3. carga el Turno con `select_for_update()`;
4. revalida cuenta, permiso, Personal y ownership;
5. busca un resultado compatible o conflictos de clave;
6. valida `CONFIRMADO`;
7. captura Detalles e impactos en orden estable por PK;
8. guarda `REALIZADO`;
9. ejecuta una sola vez los efectos internos;
10. crea auditoría semántica `TURN_FINALIZED`;
11. persiste el resultado único `FinalizacionTurno`.

Una excepción en cualquier escritura crítica revierte estado, perfil, rutinas,
cuidados, notificaciones, promociones, auditoría y resultado. No hay llamadas a
proveedores externos en este flujo; por eso no se introdujo outbox en el
Incremento 0.

## 7. Identidad e idempotencia

La migración `0041_turno_finalization_increment0.py` agrega
`FinalizacionTurno` con:

- `public_id` UUID único;
- `turno` OneToOne protegido;
- `actor` protegido;
- `idempotency_key` única y persistente;
- fingerprint SHA-256 de operación, Turno y actor;
- estados anterior/final;
- JSON de efectos y fecha de finalización.

El modelo rechaza `save()` de actualización y `delete()` de instancia. La base
garantiza un resultado por Turno y una sola operación por clave.

Política:

| Caso | Resultado |
|---|---|
| Misma clave, Turno, actor y fingerprint | 200, mismo `finalization_id`, `changed=false`. |
| Mismo Turno con otra clave/comando | 409 `TURN_ALREADY_FINALIZED`. |
| Misma clave para otro Turno | 409 `IDEMPOTENCY_KEY_REUSED`. |
| Carrera que alcanza una constraint | rollback y 409 `TURN_FINALIZATION_CONCURRENCY_CONFLICT`. |
| Consumidor legacy sin header | clave determinista `legacy-turno-finalization:{turno_id}`; el endpoint sigue siendo invocable y repetible. |

La clave no se almacena en memoria.

## 8. Efectos secundarios

### 8.1 Productor único

Se retiraron los dos receptores `post_save` dedicados a cuidados/evolución
post-servicio y la rama `REALIZADO` del receptor de notificaciones. El receptor
de cambios de otros estados continúa activo.

Un `save()` posterior de un Turno realizado ya no produce cuidados, rutinas,
notificaciones, promociones ni cambios capilares.

### 8.2 Efectos transaccionales actuales

El servicio crea una sola vez:

- agenda para cada `ReglaCuidado`;
- una notificación por regla;
- una notificación final;
- una copia por Rutina distinta, reutilizando el helper con lock;
- una promoción de retoque por Detalle con configuración;
- auditoría semántica;
- impacto capilar explícito sólo bajo la política descrita abajo.

Los IDs se guardan en `FinalizacionTurno.efectos`, permitiendo explicar el
resultado del retry. `automatic_diagnosis_ids` queda vacío de forma explícita.

### 8.3 Perfil capilar

- Un impacto `None` nunca borra un dato del Cliente.
- No se interpreta ausencia de impacto como cabello saludable.
- Con un único Servicio se conserva el comportamiento previo sólo para impactos
  explícitamente configurados y no nulos.
- Con varios Servicios no se calcula un estado global: se preserva el perfil y
  se guardan en el resultado los impactos declarados por cada
  `DetalleTurno/Servicio`.

No se definió prioridad multiservicio ni sincronización nueva entre `Cliente` y
`DiagnosticoCapilar`; ambas decisiones permanecen para incrementos posteriores.

## 9. Compatibilidad API

Se conserva exactamente la ruta y método existentes:

```text
POST /api/gestion/turnos/{id}/finalizar_turno/
Idempotency-Key: <texto de hasta 128 caracteres>  # recomendado, no obligatorio
```

La respuesta 200 mantiene `mensaje` y `estado` y agrega:

```json
{
  "changed": true,
  "finalization_id": "uuid",
  "idempotency_key": "clave",
  "estado_anterior": "confirmado",
  "estado_actual": "realizado",
  "effects": {}
}
```

Errores:

- 400: clave inválida;
- 403: cuenta, permiso, Personal u ownership;
- 404: Turno inexistente para actor autorizado;
- 409: transición, finalización previa incompatible, reutilización de clave o
  carrera.

No se encontraron consumidores React de `finalizar_turno`; no se modificó
frontend.

## 10. Pruebas

### 10.1 Suite nueva PostgreSQL

`gestion/tests/test_turno_finalization_increment0.py` cubre:

1. finalización correcta desde `CONFIRMADO` y resultado persistente;
2. rechazo de cada estado origen incompatible;
3. permiso efectivo;
4. cuenta activa;
5. Personal activo;
6. ownership;
7. finalización sin permiso ni creación de diagnóstico;
8. retry con misma identidad;
9. misma clave para otro Turno;
10. otra clave para el mismo Turno;
11. dos requests concurrentes reales;
12. rollback forzado de escritura crítica;
13. no duplicación de cuidados, rutina, notificaciones y retoque;
14. guardado posterior sin efectos;
15. multiservicio sin resultado global arbitrario;
16. impacto nulo preservado;
17. impacto único explícito y compatibilidad del endpoint.

La concurrencia usa `TransactionTestCase`, dos conexiones/requests y PostgreSQL
real; no depende exclusivamente de mocks. El mock de falla se usa sólo para
forzar y comprobar rollback.

### 10.2 Regresiones ejecutadas

| Matriz | Pruebas únicas | Resultado |
|---|---:|---|
| Caracterización/Incremento 0 | 17 | OK |
| Diagnóstico + ficha/fórmula/rutina | 54 | OK |
| Turnos, llegada, gestión, creación, lectura, skills, riesgo, diagnóstico, ficha/rutina y finalización | 197 | OK |

La matriz backend oficial con labels explícitos quedó validada así:

| Bloque | Alcance | Ejecuciones | Resultado |
|---|---|---:|---|
| B1 | Roles, usuarios y Personal | 416 | OK |
| B2 | Diagnóstico, ficha y rutinas | 170 | OK |
| B3 | Agenda, Turnos, CU-27 y finalización API | 176 | OK |
| B4 | Catálogos, inventario y órdenes | 79 | OK |
| B5 | Caja, pagos e incidencias | 170 | OK |
| B6 | Django Admin y auditoría | 43 | OK |
| B7 | Concurrencia PostgreSQL, incluida finalización | 67 | OK |
| **Total** | **Matriz B1–B7** | **1121** | **OK** |

También se ejecutaron:

- `python manage.py check`: sin incidencias;
- `python manage.py makemigrations --check --dry-run`: sin cambios pendientes;
- `python manage.py sqlmigrate gestion 0041`: SQL PostgreSQL válido.

La autodetección sin labels explícitos no constituye la matriz oficial y falló
al importar `test_settings.py` con `KeyError: 'MIRROR'`. La configuración y la
matriz B1–B7 con labels explícitos sí se ejecutaron completas y sin fallas.

## 11. Archivos de implementación

- `bohemiacore/gestion/models.py`;
- `bohemiacore/gestion/migrations/0041_turno_finalization_increment0.py`;
- `bohemiacore/gestion/turno_finalization_services.py`;
- `bohemiacore/gestion/views.py`;
- `bohemiacore/gestion/signals.py`;
- `bohemiacore/gestion/tests/test_turno_finalization_increment0.py`;
- ajuste de regresión en
  `gestion/tests/test_diagnosis_authorization_api.py`;
- `.github/workflows/bh060-permisos.yml`.

## 12. Riesgos y decisiones pendientes

1. **`EN_PROCESO`:** registrar llegada lleva hoy un Turno confirmado a ese
   estado, pero la política provisional sólo permite finalizar desde
   `CONFIRMADO`. La ampliación requiere decisión funcional explícita y debe
   coordinarse con BH-063; no se inventó en este incremento.
2. **Multiservicio:** los impactos se preservan por Servicio, pero no existe una
   regla aprobada para producir un estado global.
3. **Diagnóstico post-servicio:** queda deshabilitado como efecto automático.
   El Incremento 1 deberá decidir cuándo existe una evaluación real y cómo se
   relaciona con el perfil vigente.
4. **Efectos versionados/reconciliables:** todos los efectos actuales son DB e
   integran la transacción. El Incremento 3 deberá versionar reglas, agregar
   identidad por efecto y reconciliación si aparecen canales externos.
5. **Datos históricos:** Turnos realizados antes de esta migración no reciben
   una `FinalizacionTurno` inventada. Un intento sobre uno de ellos responde 409.
6. **Ficha:** no se volvió obligatoria; la política por Servicio corresponde al
   Incremento 2.

## 13. Conclusión

La finalización deja de ser un conjunto de escrituras dispersas y señales
reactivas. El endpoint existente delega en un servicio transaccional con
ownership, identidad persistente, retry seguro y serialización PostgreSQL. No se
publicó UI ni se inició el Incremento 1.
