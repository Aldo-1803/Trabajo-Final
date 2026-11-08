# Diagnóstico del deadlock de refunds — BH-060 F2

## 1. Alcance y veredicto

- **Fecha:** 2026-11-07
- **Commit inspeccionado:** `41d7e29c43a1f33affd4d563a13ae63df98810f8`
- **Run principal:** [42405102458](https://github.com/Aldo-1803/Trabajo-Final/actions/runs/42405102458)
- **Job B7:** `128500983062`

El deadlock corresponde a la **lógica transaccional del servicio de refunds**, no
al harness de pruebas. La causa exacta es un `SELECT ... FOR UPDATE` sin cláusula
`OF` en `_record_provider_result()`: al combinarse con `select_related()`,
PostgreSQL bloquea no sólo `FinancialRefundOperation`, sino también las filas
unidas de decisión, solicitud, caso, pago y usuario. Ese query adquiere
`FinancialResolutionDecision` antes de intentar
`FinancialResolutionRequest`, mientras `_prepare_operation()` usa el orden
explícito inverso `Request -> Decision`.

El ciclo observado es:

```text
TX3 / operador A:
  posee FinancialResolutionDecision(1)
  espera FinancialResolutionRequest(1)

TX1 / operador B:
  posee FinancialResolutionRequest(1)
  espera FinancialResolutionDecision(1)
```

El fixture y la barrera sólo hacen coincidir dos solicitudes legítimas. No
introducen locks, no comparten una conexión y no fuerzan artificialmente el
orden interno que causa el ciclo.

## 2. Evidencia obtenida de GitHub Actions

### 2.1 Logs accesibles

Se descargaron mediante la API de GitHub los logs completos, incluidos los logs
del contenedor PostgreSQL que Actions imprime al finalizar el job:

| Ejecución | Run | Job B7 | Copia local temporal |
|---|---:|---:|---|
| Primera | `42404318264` | `128498621674` | `C:\Users\AldoA\AppData\Local\Temp\opencode\bh060-f2-run1-b7-job-full.log` |
| Segunda | `42405102458` | `128500983062` | `C:\Users\AldoA\AppData\Local\Temp\opencode\bh060-f2-run2-b7-job-full.log` |

También se inspeccionaron los artifacts `bh060-B7-failure-log` de ambos runs.
El artifact contiene el traceback Django; el log completo del job agrega las
dos sentencias SQL del reporte de deadlock de PostgreSQL.

### 2.2 Segunda ejecución

PostgreSQL 16.9 informó:

```text
Process 351 waits for ShareLock on transaction 4312;
blocked by process 352.
Process 352 waits for ShareLock on transaction 4314;
blocked by process 351.
```

Las sentencias activas eran:

- **Proceso 351:** el `SELECT` de `FinancialRefundOperation` con joins a
  `FinancialResolutionDecision`, `FinancialResolutionRequest`,
  `PaymentReconciliationCase`, `Pago` y `Usuario`, terminado en `FOR UPDATE`.
  El traceback lo ubica en `refund_execution_services.py:429-433`, dentro de
  `_record_provider_result()`.
- **Proceso 352:**

  ```sql
  SELECT ...
  FROM gestion_financialresolutiondecision
  WHERE action = 'APPROVE_REFUND'
    AND resolution_request_id = 1
  LIMIT 21
  FOR UPDATE;
  ```

  Corresponde a `refund_execution_services.py:282-285`, dentro de
  `_prepare_operation()`.

El proceso 351 fue elegido como víctima. PostgreSQL precisó:

```text
CONTEXT: while locking tuple (0,2)
in relation "gestion_financialresolutionrequest"
```

Por tanto, el query de resultado ya poseía una fila que impedía al proceso 352
bloquear la decisión y estaba intentando adquirir la solicitud que poseía el
proceso 352. La fila que bloqueaba el segundo query sólo puede ser
`FinancialResolutionDecision(1)`: el query de resultado la incluye y su
`FOR UPDATE` no está limitado a la tabla principal.

### 2.3 Repetición independiente

La primera ejecución produjo el mismo grafo, con procesos 352 y 353:

```text
Process 352 waits for ShareLock on transaction 4312;
blocked by process 353.
Process 353 waits for ShareLock on transaction 4314;
blocked by process 352.
```

Nuevamente:

- la víctima ejecutaba el query unido de `_record_provider_result()`;
- el competidor ejecutaba `FinancialResolutionDecision ... FOR UPDATE` para
  `resolution_request_id = 1`;
- la espera de la víctima ocurrió sobre la misma relación y tuple física de
  `FinancialResolutionRequest`.

Dos bases limpias y dos runners separados reprodujeron la misma inversión.

### 2.4 Datos de entorno

El segundo job usó:

- `ubuntu-24.04`;
- Python 3.13.7;
- Django 5.2.7;
- psycopg2-binary 2.9.11;
- PostgreSQL 16.9, imagen oficial Debian;
- un único proceso `manage.py test`, sin `--parallel` ni `--keepdb`;
- base y contenedor exclusivos del job B7.

El aviso `staticfiles.W004`, el evento duplicado esperado de otra prueba y los
mensajes posteriores de `ANALYZE` no intervienen en el ciclo. El deadlock fue
registrado antes del `ANALYZE` y exclusivamente entre las dos conexiones del
test de refund.

## 3. Transacciones y registros involucrados

### 3.1 Escenario del fixture

`RefundExecutionConcurrencyTests` hereda
`RefundExecutionFixtureMixin` y crea un contexto BOOKING:

- un `PaymentIntent`, su `SolicitudTecnicaReserva`, `SlotHold` y `Cliente`;
- dos pagos en el fixture completo: uno manual base y el pago de proveedor usado
  para el refund;
- un segundo `PaymentReconciliationCase`, el caso de refund;
- `FinancialResolutionRequest(1)` en estado `DECIDED`;
- `FinancialResolutionDecision(1)` con acción `APPROVE_REFUND`;
- dos revisores con permiso, claves idempotentes de cliente diferentes y el
  mismo caso, decisión y pago.

La secuencia reiniciada permite identificar explícitamente solicitud y decisión
como ID 1. La operación durable creada durante la carrera es la única operación
asociable a esa decisión por el `OneToOneField` y la constraint única
subyacente.

### 3.2 Fronteras transaccionales

`execute_authorized_refund()` está dividido correctamente en cuanto a no hacer
HTTP bajo una transacción abierta:

1. **TX1 — `_prepare_operation()`**: valida, bloquea contexto y crea o recupera
   la operación `PENDING`.
2. **TX2 — `_claim_submission()`**: bloquea la operación y confirma
   `PENDING -> SUBMITTED`, `provider_call_count += 1` y el evento
   `SUBMISSION_STARTED`.
3. **Sin transacción:** llama al adaptador externo.
4. **TX3 — `_record_provider_result()`**: bloquea la operación y registra la
   respuesta y el tercer evento.

El defecto no es separar esos tramos; esa separación evita mantener locks
durante HTTP. El defecto es que TX3 amplía accidentalmente su conjunto de locks
a entidades de TX1.

## 4. Reconstrucción exacta del orden de locks

### 4.1 Operador A, ganador inicial

El operador A progresa primero:

1. TX1 bloquea, para el contexto BOOKING:
   `SolicitudTecnicaReserva -> SlotHold -> PaymentIntent -> Cliente -> Pagos`
   ordenados por PK -> `PaymentReconciliationCase -> FinancialResolutionRequest
   -> FinancialResolutionDecision`.
2. No encuentra una operación previa, crea
   `FinancialRefundOperation(PENDING)`, el evento `CREATED` y auditoría.
3. TX1 confirma y libera sus locks.
4. TX2 bloquea la operación, la deja `SUBMITTED`, incrementa el contador de
   llamadas y crea `SUBMISSION_STARTED`; después confirma.
5. Ejecuta una vez `adapter.submit_refund()`; el mock retorna inmediatamente.
6. TX3 entra a `_record_provider_result()` y ejecuta:

   ```python
   FinancialRefundOperation.objects.select_for_update().select_related(
       'decision__resolution_request__case',
       'payment',
       'created_by',
   ).get(pk=operation_id)
   ```

7. Django genera un join de seis tablas terminado simplemente en
   `FOR UPDATE`. Sin `OF`, PostgreSQL intenta bloquear filas de todas las tablas
   seleccionadas. En el plan observado TX3 ya posee la decisión y luego espera
   la solicitud.

### 4.2 Operador B, competidor

El operador B comienza en la misma barrera:

1. TX1 espera inicialmente alguno de los locks de contexto del operador A.
2. Cuando A confirma su TX1, B adquiere el contexto y después
   `FinancialResolutionRequest(1)`.
3. B intenta adquirir `FinancialResolutionDecision(1)` mediante el query
   explícito `FOR UPDATE` de `_prepare_operation()`.
4. Esa decisión ya está bloqueada por TX3 de A.

### 4.3 Grafo final

```text
TX3 A / xid 4314 / query de resultado
  HOLD: FinancialResolutionDecision(1)
  WAIT: FinancialResolutionRequest(1), poseída por TX1 B / xid 4312

TX1 B / xid 4312 / query de preparación
  HOLD: FinancialResolutionRequest(1)
  WAIT: FinancialResolutionDecision(1), poseída por TX3 A / xid 4314
```

Los `ShareLock on transaction` del log son la representación de PostgreSQL de
la espera por una versión de tuple bloqueada por la otra transacción; no son
locks de tabla ni indican una base compartida entre jobs.

## 5. SQL compilado y amplitud accidental

La compilación local del queryset actual, sin ejecutarlo ni modificar código,
confirmó este final:

```sql
... INNER JOIN gestion_financialresolutiondecision ...
    INNER JOIN gestion_financialresolutionrequest ...
    INNER JOIN gestion_paymentreconciliationcase ...
    INNER JOIN gestion_pago ...
    INNER JOIN usuarios_usuario ...
WHERE gestion_financialrefundoperation.id = 1
FOR UPDATE;
```

No aparece `OF gestion_financialrefundoperation`. En PostgreSQL, `FOR UPDATE`
sin `OF` aplica el row lock a todas las relaciones bloqueables del query, no
sólo al modelo desde el que se inició el QuerySet.

Además, `_record_provider_result()` no modifica la decisión, solicitud, caso,
pago ni usuario. `_audit_submission()` sólo usa campos escalares de la operación
y el actor recibido. Esos locks relacionados no protegen un invariante de TX3.

## 6. Evaluación de las cuatro hipótesis

### 6.1 Lógica transaccional de refunds — causa primaria

**Sí.** TX3 toma locks no requeridos y en orden incompatible con TX1. El
problema nació con la implementación de F7.3 y está en el servicio, no en el
workflow.

### 6.2 Orden inconsistente de bloqueos — mecanismo exacto

**Sí.** TX1 usa `Request -> Decision`; TX3, por el join bloqueado completo,
termina usando `Decision -> Request`. Éste es el ciclo demostrado por las dos
sentencias y el tuple indicado por PostgreSQL.

### 6.3 Fixture o sincronización del test — disparador, no causa

**No como defecto.** El test:

- usa `TransactionTestCase`;
- abre dos conexiones reales mediante `close_old_connections()`;
- sincroniza sólo el inicio con `threading.Barrier(2)`;
- utiliza dos actores y claves diferentes contra una misma aprobación;
- no introduce sleeps ni locks propios sobre modelos.

El mock responde más rápido que una llamada HTTP real y hace más probable que
TX3 se solape con TX1 del competidor. Eso aumenta la capacidad de detección del
test, pero no inventa el orden inverso. Dos operadores concurrentes constituyen
un escenario válido que el servicio declara soportar.

### 6.4 Diferencias PostgreSQL local/CI — afectan la ventana, no la semántica

El caso focal aprobó localmente sobre PostgreSQL 16.9, mientras falló dos veces
en PostgreSQL 16.9 Linux CI. Las versiones principales y el SQL generado son
equivalentes. Pueden variar scheduling, latencia, estadísticas y plan físico;
por ello un entorno entra en la ventana con más frecuencia.

Ninguna diferencia de plataforma cambia que el SQL actual permita bloquear
Decision y Request en orden inverso. Un pase local no elimina el ciclo. La
reproducción idéntica en dos contenedores limpios descarta contaminación de base
o competencia con otros jobs.

## 7. Posibilidad en producción

**Sí, puede presentarse en producción.** Requiere dos ejecuciones casi
simultáneas sobre la misma aprobación:

- el primer operador ya confirmó la identidad y el claim;
- el segundo conserva TX1 entre el lock de Request y el lock de Decision;
- la respuesta del proveedor permite al primero entrar a TX3 durante esa
  ventana.

Una llamada HTTP real normalmente ensancha el tiempo antes de TX3 y puede dar al
segundo operador tiempo para terminar; eso reduce cierta probabilidad respecto
al mock inmediato, pero no la lleva a cero. Un proveedor rápido, scheduling del
servidor, carga de base o pausas entre queries pueden recrear exactamente el
interleaving observado.

La vista no captura `django.db.OperationalError`; sólo captura errores de
dominio. Si TX3 es la víctima después de que el proveedor aceptó el refund, la
petición puede responder 500 y perder el registro sanitario inmediato de la
respuesta externa. La operación permanece reclamada y debe recuperarse por la
consulta oficial prevista por F7.3.

## 8. Estado de los invariantes tras el deadlock

### 8.1 Una sola operación durable

**Se conserva.** Antes de HTTP, TX1 del operador A confirmó una operación
`PENDING` asociada uno-a-uno a la decisión. El competidor, una vez liberado,
encuentra esa operación. La relación `FinancialRefundOperation.decision` es
`OneToOneField`, por lo que una segunda inserción también sería rechazada por la
base.

### 8.2 Una sola llamada externa

**Se conserva por el camino observado.** La víctima estaba dentro de
`_record_provider_result()`, función que sólo se invoca después del retorno de
`submit_refund()`. Antes de esa llamada, TX2 confirmó atómicamente
`PENDING -> SUBMITTED` y `provider_call_count += 1`. El competidor encuentra la
misma operación en `SUBMITTED`; `_claim_submission()` devuelve `claimed=False`
y no llama al proveedor.

El artifact no contiene el valor final de `Mock.call_count` porque la excepción
interrumpe el test antes de sus aserciones y Django destruye la base. La
conservación se deduce del estado y de las sentencias observadas, no de una
aserción post mortem ejecutada en CI.

### 8.3 Evidencia completa de respuesta

**No se conserva en ese intento.** PostgreSQL aborta TX3 antes de actualizar la
operación y crear el evento de respuesta. El estado durable esperable es:

- una operación `SUBMITTED`;
- `provider_call_count = 1`;
- eventos `CREATED` y `SUBMISSION_STARTED`;
- sin el tercer evento `SUBMITTED` y sin la evidencia devuelta por el mock.

Esto evita una segunda llamada ciega, pero deja un resultado externo que debe
reconciliarse mediante `recover_refund_operation()`. Por ello el deadlock sigue
siendo un defecto operativo aunque preserve los dos invariantes principales.

## 9. Corrección mínima segura propuesta

Limitar el row lock de `_record_provider_result()` exclusivamente a
`FinancialRefundOperation`, preservando si se desea el eager loading:

```python
operation = (
    FinancialRefundOperation.objects
    .select_for_update(of=('self',))
    .select_related(
        'decision__resolution_request__case',
        'payment',
        'created_by',
    )
    .get(pk=operation_id)
)
```

La compilación del queryset propuesto fue comprobada sin editar archivos y
termina en:

```sql
FOR UPDATE OF "gestion_financialrefundoperation"
```

### Por qué elimina el ciclo

- TX3 conserva el lock necesario sobre la operación cuyo estado y evidencia
  actualiza.
- TX3 deja de tomar Decision y Request, que son inmutables para este tramo.
- TX1 puede continuar con `Request -> Decision` y luego esperar brevemente la
  operación existente si TX3 aún la posee.
- TX3 ya no necesita ningún recurso poseído por TX1; desaparece la arista de
  regreso y, por tanto, el ciclo.

Eliminar por completo el `select_related()` también evitaría esos locks y el
query no parece necesitar las relaciones, pero `of=('self',)` es el cambio más
pequeño: conserva la forma y la caché de relaciones del objeto y modifica sólo
el alcance accidental del lock.

No se recomienda:

- reintentar ciegamente la operación completa después del deadlock;
- dormir o serializar artificialmente el test;
- mantener la transacción abierta durante HTTP;
- capturar y ocultar `OperationalError`;
- usar `continue-on-error` o tolerar B7 rojo.

Como revisión preventiva posterior, conviene auditar los otros
`select_for_update().select_related()` del mismo módulo para exigir `OF` cuando
las filas relacionadas sean sólo de lectura. Eso no es necesario para la
corrección mínima de este deadlock y no se realizó en este diagnóstico.

## 10. Validación requerida después de una futura corrección

Sin aplicar cambios en este incremento de diagnóstico, la validación futura
debería comprobar:

1. SQL terminado en `FOR UPDATE OF gestion_financialrefundoperation`.
2. El test concurrente existente sin excepciones.
3. Exactamente una operación, una llamada externa y tres eventos.
4. Suite F7.3 completa.
5. B7 completo, en proceso único y sin `--parallel`/`--keepdb`.
6. Una nueva ejecución completa de BH-060 F2 en GitHub Actions.

## 11. Conclusión

La evidencia de PostgreSQL demuestra una inversión real de locks causada por
el alcance implícito de `FOR UPDATE` en `_record_provider_result()`. El harness
es correcto y revela un escenario de dos operadores que la lógica declara
idempotente. Las diferencias local/CI sólo cambian la probabilidad del
interleaving.

> **Clasificación final: defecto de lógica transaccional de negocio (orden y
> alcance de locks), no defecto del harness de pruebas.**
