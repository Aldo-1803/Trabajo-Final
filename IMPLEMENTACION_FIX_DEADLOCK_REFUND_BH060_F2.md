# BH-060 F2 — Corrección focalizada del deadlock de refunds

## 1. Estado

- **Fecha:** 2026-11-07
- **Baseline:** `41d7e29c43a1f33affd4d563a13ae63df98810f8`
- **Diagnóstico:** `ANALISIS_DEADLOCK_REFUND_BH060_F2.md`
- **Validación local:** APROBADA
- **Validación remota:** PENDIENTE

> **BH-060 F2 = BLOQUEADO** hasta que una matriz completa de GitHub Actions
> termine con todos sus jobs aprobados.

## 2. Causa corregida

`_prepare_operation()` adquiere explícitamente los locks de
`FinancialResolutionRequest` y `FinancialResolutionDecision` en ese orden. En
cambio, `_record_provider_result()` combinaba:

```python
select_for_update().select_related(
    'decision__resolution_request__case',
    'payment',
    'created_by',
)
```

En PostgreSQL, un `FOR UPDATE` sin cláusula `OF` bloquea todas las filas
bloqueables incluidas por los joins. El query de registro de respuesta adquiría
la decisión y esperaba la solicitud, mientras una segunda preparación poseía la
solicitud y esperaba la decisión:

```text
TX3 A: HOLD Decision -> WAIT Request
TX1 B: HOLD Request  -> WAIT Decision
```

El mismo ciclo fue registrado por PostgreSQL en dos runners limpios.

## 3. Verificación de necesidad de locks

La revisión de los recorridos confirmó:

- TX1 necesita solicitud y decisión para validar que el caso sigue abierto, la
  solicitud está `DECIDED` y existe una aprobación `APPROVE_REFUND` vigente;
- TX1 necesita serializar la creación o recuperación de la única operación por
  decisión;
- TX2 necesita bloquear la operación para reclamar una sola vez
  `PENDING -> SUBMITTED` antes de HTTP;
- TX3 sólo decide y persiste el resultado sobre campos de
  `FinancialRefundOperation` y crea evidencia/auditoría;
- `_audit_submission()` usa campos escalares de la operación y el actor
  recibido; no modifica solicitud, decisión, caso, pago ni usuario;
- solicitud y decisión son inmutables en este tramo y sus datos relevantes ya
  quedaron copiados a la operación durable antes de la llamada externa.

Por tanto, limitar TX3 a la fila de operación conserva el lock necesario y
elimina únicamente locks relacionados accidentales. No abre una carrera sobre
solicitud o decisión: TX3 no las consulta para decidir una transición y toda
transición de la operación permanece serializada por su propia fila.

## 4. Cambio exacto

Archivo: `bohemiacore/gestion/refund_execution_services.py`

Antes:

```python
FinancialRefundOperation.objects.select_for_update().select_related(...)
```

Después:

```python
FinancialRefundOperation.objects.select_for_update(
    of=('self',),
).select_related(...)
```

No se eliminaron los joins de lectura ni se alteraron estados, transiciones,
excepciones, llamadas externas, recuperación o auditoría.

## 5. SQL de locks antes y después

### Antes

```sql
SELECT ...
FROM gestion_financialrefundoperation
INNER JOIN gestion_financialresolutiondecision ...
INNER JOIN gestion_financialresolutionrequest ...
INNER JOIN gestion_paymentreconciliationcase ...
INNER JOIN gestion_pago ...
INNER JOIN usuarios_usuario ...
WHERE gestion_financialrefundoperation.id = %s
FOR UPDATE;
```

Al no especificar `OF`, PostgreSQL intentaba bloquear filas de todas las tablas
unidas.

### Después

La compilación real del queryset corregido termina en:

```sql
FOR UPDATE OF "gestion_financialrefundoperation"
```

Los joins siguen disponibles para lectura, pero sólo la operación recibe row
lock. Si TX1 del competidor llega a la operación existente mientras TX3 la
posee, TX1 puede esperar la operación; TX3 ya no espera Request ni Decision, por
lo que no existe arista de regreso ni ciclo.

## 6. Regresiones ajustadas

### 6.1 Carrera de dos operadores

`test_refund_execution_concurrency.py` conserva dos conexiones PostgreSQL, dos
operadores, claves distintas y una barrera únicamente al inicio. Ahora exige:

- exactamente un resultado `created=True`;
- exactamente un resultado `provider_called=True`;
- una sola llamada `submit_refund`;
- una sola `FinancialRefundOperation` y la misma PK en ambos resultados;
- estado final `SUBMITTED`;
- `provider_call_count = 1`;
- un único `external_refund_id` esperado;
- ausencia de `confirmed_at` sin evidencia terminal;
- exactamente tres eventos: `CREATED`, `SUBMISSION_STARTED` y `SUBMITTED`.

Esto comprueba ausencia de deadlock, de doble operación y de doble devolución,
además de coherencia del resultado persistido.

### 6.2 Confirmación externa idempotente

`test_financial_adjustments.py` procesa dos veces el mismo evento oficial
verificado y exige:

- una sola `FinancialAdjustment`;
- un solo evento `CONFIRMED` para la operación;
- una sola llamada original `submit_refund`.

La confirmación continúa dependiendo de evidencia oficial verificada y no del
resultado sanitario de la llamada inicial.

## 7. Invariantes preservadas

### Identidad y llamada externa

- una sola operación por decisión mediante lock de preparación y
  `OneToOneField`;
- claim durable `PENDING -> SUBMITTED` antes de HTTP;
- contador de llamada incrementado dentro de TX2;
- un competidor que encuentra `SUBMITTED` no reenvía;
- el HTTP continúa fuera de transacciones y locks.

### Resultado incierto y recuperación

- timeout o resultado ambiguo permanece `UNKNOWN`;
- un retry de ejecución no llama otra vez a `submit_refund`;
- se preservan Order, transacción, importe, clave externa y baseline de refunds
  necesarios para recuperación;
- `recover_refund_operation()` consulta `fetch_provider_order()` y nunca
  `submit_refund()`;
- cero o múltiples coincidencias permanecen `UNKNOWN`;
- una coincidencia única recupera identidad, pero no declara confirmación
  financiera;
- sólo un evento oficial verificado puede llevar a `CONFIRMED` y materializar
  el ajuste;
- una operación `PENDING`, `SUBMITTED` o `UNKNOWN` sigue impidiendo cerrar el
  caso como refund confirmado.

### Autorizaciones y efectos

- no se modificaron permisos ni superficies BH-060 F1;
- no cambia `Pago`, `PaymentIntent`, agenda, órdenes o stock por el mero envío;
- no se agregaron retries, sleeps, tolerancia a errores ni serialización
  artificial.

## 8. Resultados locales PostgreSQL

Todos los comandos usaron `bohemiacore.test_settings`, bases limpias y ningún
`--parallel` o `--keepdb`.

| Validación | Resultado | Duración Django |
|---|---:|---:|
| Carrera focal de dos operadores | 1/1 | 15,299 s |
| Confirmación oficial idempotente focal | 1/1 | 7,955 s |
| Refunds, resoluciones, ajustes y cierres | 55/55 | 413,558 s |
| B7 oficial, 17 etiquetas | 64/64 | 651,199 s |
| `manage.py check` | OK | No aplica |
| `makemigrations --check --dry-run` | Sin cambios | No aplica |
| Compilación Python de servicio/tests | OK | No aplica |

La suite de 55 incluye:

- ejecución y concurrencia de refunds;
- resultado externo incierto, retry sin reenvío y recuperación oficial;
- resoluciones financieras y su concurrencia;
- ajustes financieros y confirmación idempotente;
- cierres financieros y carreras de cierre.

## 9. Riesgos residuales

- La carrera depende de scheduling; la garantía principal procede del grafo
  ahora acíclico y se complementa con la prueba concurrente real.
- Otros `select_for_update().select_related()` del módulo deben auditarse en un
  incremento separado si se identifica otro ciclo; no se ampliaron cambios sin
  evidencia.
- Una caída real después de que el proveedor acepte y antes de persistir la
  respuesta sigue dejando `SUBMITTED`; es el diseño seguro existente y exige
  recuperación oficial, nunca reenvío ciego.
- PostgreSQL es requisito de esta corrección por el uso explícito de
  `select_for_update(of=...)` y por las pruebas de concurrencia.
- La validación local no sustituye la matriz completa Linux CI.

## 10. Estado remoto

Pendiente del push y de una ejecución completa de GitHub Actions. Deben aprobar:

- B1–B6;
- B7 con sus 64 tests;
- Jest y build;
- resultado global.

Hasta obtener esa evidencia:

> **BH-060 F2 = BLOQUEADO**
