# Flujos profesionales — Incremento 3: automatizaciones trazables

**Fecha:** 2026-11-17

**Baseline de partida:** `71c080db7d33ed2775efcfb8062492479a794fab`

**Rama:** `save/work-in-progress`

**Estado:** validado para publicación

## 1. Objetivo y alcance

Este incremento consolida los efectos DB derivados de finalizar un Turno bajo
una causa, un plan inmutable y una identidad lógica persistente. Mantiene la
atomicidad del Incremento 0, el ledger capilar del Incremento 1 y las políticas
de ficha del Incremento 2.

No publica UI profesional, no agrega colas/outbox, no crea evaluaciones
profesionales ficticias y no modifica pagos, Mercado Pago, stock, facturación,
BH-063 ni BH-064.

## 2. Inventario inspeccionado

| Efecto | Productor antes del incremento | Disparador | Identidad previa | Persistencia/rollback | Retry previo |
|---|---|---|---|---|---|
| Impacto explícito del perfil | `turno_finalization_services` | comando de finalización | ID dentro de JSON | DB, transacción completa | sólo retry global |
| Agenda de cuidados | servicio de finalización | regla y fecha calculada | IDs dentro de JSON | DB, transacción completa | sólo retry global |
| Notificación por regla | servicio de finalización | una `ReglaCuidado` | IDs dentro de JSON | DB, transacción completa | sólo retry global |
| Rutina de Cliente | `ensure_internal_routine_assignment` | rutina de Servicio/regla | Cliente + Rutina bajo lock | DB, transacción completa | reutiliza copia existente |
| Notificación final | servicio de finalización | finalización | ID dentro de JSON | DB, transacción completa | sólo retry global |
| Promoción de retoque | servicio de finalización | primera configuración del Servicio | ID dentro de JSON | DB, transacción completa | sólo retry global |
| Diagnóstico automático | deshabilitado explícitamente | ninguno | lista vacía | no se crea | no aplica |
| Auditoría semántica | servicio de finalización | `TURN_FINALIZED` | ID dentro de JSON | DB, transacción completa | sólo retry global |

El Incremento 0 ya había retirado los dos receptores `post_save` que producían
cuidados/evolución y la rama `REALIZADO` del receptor de notificaciones. No se
encontró un productor final duplicado que eliminar en este incremento.

Se preservan porque pertenecen a otros flujos:

- señales genéricas de auditoría;
- notificaciones de solicitud, aceptación, confirmación y cancelación;
- sugerencias de combos al crear productos;
- comandos temporales de promociones y recordatorios;
- asignación explícita de rutinas desde CU-11.

Guardar nuevamente un Turno `REALIZADO` no ejecuta efectos post-servicio.

## 3. Productor consolidado

`gestion/finalization_effect_services.py` es la autoridad de planificación y
producción de efectos. `turno_finalization_services.py` conserva la autoridad de
la transición, ownership, idempotencia del comando, locks y coordinación de la
transacción.

La secuencia es:

1. bloquear Turno, detalles, Servicios y fichas;
2. validar transición y fichas requeridas;
3. bloquear reglas, configuraciones y rutinas;
4. construir `parametros_snapshot`;
5. crear la identidad provisional de `FinalizacionTurno` dentro de la misma
   transacción;
6. cambiar el Turno a `REALIZADO`;
7. ejecutar cada efecto consultando antes su clave lógica;
8. persistir `EfectoFinalizacion` junto con cada salida;
9. crear auditoría y sellar el resultado estructurado;
10. confirmar todo o revertir todo.

La identidad provisional nunca es visible parcialmente: cualquier excepción
revierte la transacción externa completa.

## 4. Modelo causa/efecto

`FinalizacionTurno` agrega `parametros_snapshot`, con schema
`turno.finalization.effects:v1`. Conserva:

- fecha comercial del Turno;
- detalles y Servicios por PK;
- impactos capilares explícitos;
- reglas de cuidado, textos, duración, frecuencia y fechas calculadas;
- Rutina y versión utilizada, con todas sus causas;
- configuración de retoque, descuento y fechas calculadas;
- política explícita de no crear diagnóstico automático.

`EfectoFinalizacion` registra:

- finalización causal;
- tipo y estado;
- clave lógica;
- DetalleTurno, Servicio, regla, Rutina y configuración cuando corresponden;
- snapshot acotado;
- modelo/ID de salida o motivo de omisión;
- fecha.

Es inmutable por contrato de modelo. La constraint
`unique_finalization_effect_logical_key` garantiza una fila por finalización y
clave lógica.

## 5. Claves lógicas y unicidad

| Tipo | Clave lógica |
|---|---|
| Impacto de perfil | `profile-impact` |
| Cuidado agendado | `care-item:{detalle}:{regla}:{fecha}` |
| Notificación de cuidado | `care-notification:{detalle}:{regla}` |
| Rutina | `routine-assignment:{rutina}` |
| Notificación final | `final-notification` |
| Retoque configurado | `retouch-promotion:{detalle}:{configuracion}` |
| Retoque omitido | `retouch-promotion:{detalle}:none` |
| Diagnóstico omitido | `automatic-diagnosis` |
| Auditoría | `semantic-audit` |

Las claves usan IDs y fechas del plan, nunca nombres, timestamps accidentales ni
memoria de proceso. Cada handler consulta primero la fila causal. Una repetición
devuelve la salida persistida sin ejecutar nuevamente el productor. El lock de
`FinalizacionTurno` serializa handlers y la constraint es el respaldo final ante
una carrera.

La asignación compartida de Rutina conserva además el lock de Cliente/Rutina de
`routine_services.py`; una copia existente se registra como resultado
`created=false` sin duplicarla.

## 6. Versionado de reglas y fechas

Reglas de cuidado y configuraciones de retoque no tenían versión propia. No se
inventó una. El snapshot completo de parámetros es la versión efectiva del
evento.

Las fechas de cuidados y retoque se calculan una sola vez desde `Turno.fecha`,
que representa la fecha comercial de atención. Un retry posterior usa el plan
persistido; cambiar duración, texto, descuento, días de retoque o versión de
Rutina no altera el resultado histórico.

La promoción queda además relacionada por M2M con el Servicio de retoque
configurado, mientras el efecto conserva el Servicio principal y Detalle que la
causaron.

## 7. Perfil capilar y diagnóstico

- Sólo un Turno de un Servicio puede aplicar impactos no nulos configurados.
- La causa textual del `CambioPerfilCapilar` incluye el UUID de finalización.
- `EfectoFinalizacion` referencia el cambio producido.
- Sin impacto explícito no se borra ni inventa dato capilar.
- En multiservicio se registran todos los impactos y se omite el cambio global
  con `MULTISERVICE_POLICY_PENDING`.
- No se crea `DiagnosticoCapilar`; el efecto
  `DIAGNOSTICO_AUTOMATICO` queda `OMITIDO` con motivo verificable.

No se alteró la semántica de corrección/invalidez de derivados del Incremento
1 ni se implementó recálculo retroactivo.

## 8. Atomicidad y fallas

Todos los efectos actuales son escrituras PostgreSQL críticas. Permanecen bajo
el mismo `transaction.atomic()` que Turno y finalización. No hay correo,
WhatsApp, proveedor externo ni tarea diferida en este recorrido; por eso no se
agrega outbox, cola ni `transaction.on_commit()` anticipatorio.

Una falla en cualquier salida o en el ledger revierte:

- estado del Turno;
- finalización y efectos causales;
- cambios/vigencias del perfil;
- cuidados y rutinas;
- notificaciones;
- promociones;
- auditoría.

No puede persistir normalmente un efecto `PENDIENTE` o `FALLIDO`: una falla
crítica produce rollback. Los estados quedan explícitos para detectar datos
anómalos, no para convertir la operación atómica en escrituras parciales.

## 9. Reconciliación acotada

`inspect_effect_ledger(finalization)` es una operación interna de sólo lectura.
Compara el resumen esperado con el ledger, verifica que las salidas referidas
existan e informa:

- efectos faltantes o inesperados;
- salidas faltantes;
- estados pendientes o fallidos;
- completitud verificable.

No vuelve a finalizar, no relee reglas vigentes, no reaplica perfil y no expone
una API pública de reprocesamiento. Repetir handlers con un ledger completo es
seguro y no produce escrituras nuevas.

Una finalización histórica sin schema v1 devuelve
`reconciliation_supported=false` y `complete=null`. No se crean efectos
retroactivos ni se interpreta su JSON legacy como evidencia inexistente.

No se implementa reparación automática de corrupción manual o borrado de
salidas: no existe una política aprobada de compensación. En el flujo normal esa
condición no puede surgir por una falla transaccional.

## 10. Contrato API

La ruta y códigos permanecen sin cambios:

```text
POST /api/gestion/turnos/{id}/finalizar_turno/
```

`effects` conserva todos los campos legacy e incorpora:

```json
{
  "summary": {
    "schema": "turno.finalization.effects:v1",
    "counts": {},
    "items": [
      {
        "type": "NOTIFICACION_FINAL",
        "state": "COMPLETADO",
        "logical_key": "final-notification",
        "detalle_turno_id": null,
        "servicio_id": null,
        "result": {"model": "Notificacion", "id": 1}
      }
    ],
    "warnings": []
  }
}
```

No expone snapshots, textos internos de reglas, fórmulas ni configuración
administrativa. Un retry devuelve exactamente `FinalizacionTurno.efectos` y
`changed=false`.

## 11. Migración

`gestion/migrations/0044_finalizacionturno_parametros_snapshot_and_more.py`:

- agrega el snapshot con default `{}` para resultados anteriores;
- crea `EfectoFinalizacion`, índice causal y constraint única;
- no contiene `RunPython`;
- no crea efectos históricos ni modifica Turnos, perfil o salidas previas.

## 12. Pruebas y regresiones

`gestion/tests/test_finalization_effects_increment3.py` agrega 16 pruebas que
cubren los 24 escenarios solicitados junto con las suites ya existentes:

- identidad de todos los tipos y unicidad DB;
- resultado inicial, retry global y repetición individual de handlers;
- snapshot estable ante cambios de reglas;
- inspección/reconciliación sin mutación;
- resultados históricos no reinterpretados;
- Rutina, notificación y promoción preexistentes;
- fechas comerciales y Servicio de retoque;
- ausencia de diagnóstico/datos capilares ficticios;
- multiservicio incompatible;
- causa del ledger capilar;
- contrato sin fórmula/snapshot sensible;
- ficha completa requerida;
- 403/409 sin efectos nuevos.

La prueba PostgreSQL concurrente del Incremento 0 agrega aserción de unicidad de
la notificación final en `EfectoFinalizacion`. La prueba de rollback fue adaptada
al productor consolidado y verifica ausencia de ledger residual.

| Suite | Resultado |
|---|---:|
| Incremento 3 focal | 16/16 |
| Incremento 3 + finalización Incremento 0 | 31/31 |
| Concurrencia de finalización PostgreSQL | 1/1 |
| Focal API explícita de Incrementos 0–3 | 95/95 |
| B1 — roles, usuarios y Personal | 416/416 |
| B2 — diagnóstico, ficha y rutinas | 206/206 |
| B3 — agenda, Turnos y automatizaciones | 192/192 |
| B4 — catálogos, inventario y órdenes | 79/79 |
| B5 — Caja, pagos e incidencias | 170/170 |
| B6 — Django Admin y auditoría | 43/43 |
| B7 — concurrencia PostgreSQL | 69/69 |

El workflow agrega las 16 pruebas a B3, que pasa de 176 a 192 pruebas. B7
mantiene 69 métodos; su prueba de finalización ahora verifica también el ledger.
La matriz pasó **1.175/1.175 pruebas backend únicas**. Una corrida exploratoria
que mezcló indiscriminadamente varias `TransactionTestCase` ejecutó 96 pruebas
correctas y encontró dos errores de seed posteriores a `flush`; no se contó como
evidencia. Las mismas clases API (95/95) y las clases concurrentes aisladas en B7
(69/69) pasaron con bases PostgreSQL separadas, igual que el workflow.

## 13. Compatibilidad y productores preservados

- Incremento 0: misma transición, endpoint, idempotencia y rollback.
- Incremento 1: misma política de perfil, vigencias y correcciones.
- Incremento 2: validación de fichas antes del plan de efectos.
- CU-11: `assign_routine_copy` y `ensure_internal_routine_assignment` conservan
  su API y ownership externo.
- señales de otros estados, combos y comandos temporales no cambian.
- no se modifica frontend porque `summary` es una ampliación compatible y no se
  encontraron consumidores React de finalización.

## 14. Riesgos y decisiones pendientes

1. Una futura salida realmente externa requerirá outbox/on-commit, estado de
   entrega y autorización específica de retry.
2. La reparación de corrupción manual o salida borrada necesita política de
   compensación; hoy sólo se detecta.
3. Continúa pendiente una política de combinación capilar multiservicio.
4. Continúa pendiente el recálculo/reemplazo de recomendaciones invalidadas.
5. Los resultados previos a 0044 permanecen legacy no versionados.
6. La UI profesional corresponde al Incremento 4.

## 15. Publicación

El cambio se publica en `save/work-in-progress` con el mensaje:

```text
feat(turnos): consolidar efectos trazables de finalizacion
```

No se inicia el Incremento 4.
