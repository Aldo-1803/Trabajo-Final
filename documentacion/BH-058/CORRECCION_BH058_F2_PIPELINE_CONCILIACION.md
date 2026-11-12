# BH-058 F2 — Pipeline productivo de conciliación Mercado Pago

Fecha de validación: 2026-10-29.

## Resultado

Los eventos autenticados del inbox Mercado Pago ya no quedan detenidos en
`VERIFIED`. El worker existente ahora ejecuta dos fases independientes y
recuperables:

```text
Webhook autenticado
        ↓ ACK = recepción durable, no acreditación
ProviderEvent.RECEIVED
        ↓ C2a: consulta oficial fuera de locks
ProviderEvent.VERIFIED
        ↓ claim transaccional
reconcile_verified_provider_event(event_id)
        ↓ C2b: autoridad financiera existente
APPLIED | REVIEW_REQUIRED | IGNORED
```

No se duplicó lógica financiera. La creación de `Pago`, la confirmación de
`Turno`, la transición de `OrdenCompra` a `PAGADO`, la detección de eventos
antiguos y los casos de revisión continúan perteneciendo a C2b.

## Causa original

`process_provider_events` sólo invocaba
`process_pending_provider_events()`. Esa función cerraba correctamente C2a:
reclamaba el evento, consultaba la Order oficial sin mantener el lock, validaba
identidad e importe y persistía `VERIFIED`.

No existía ninguna integración productiva posterior que invocara
`reconcile_verified_provider_event(event_id)`. C2b era idempotente y estaba
probado, pero sólo podía ejecutarse mediante llamadas directas en pruebas o una
integración manual ajena al inbox. Además, el management command terminaba tras
un único ciclo y no se entregaba scheduler ni supervisor.

## Integración aplicada

### Orquestador durable

`gestion/provider_event_pipeline.py` incorpora dos operaciones:

- `process_verified_provider_events()`: reclama y concilia eventos
  `VERIFIED + NOT_EVALUATED`;
- `process_provider_event_pipeline()`: ejecuta primero C2a y, después de que C2a
  haya cerrado sus transacciones, ejecuta C2b.

La frontera es deliberada:

1. C2a toma un claim breve y libera el lock.
2. C2a llama a Mercado Pago sin transacción ni lock de fila abiertos.
3. C2a persiste el snapshot sanitizado y `VERIFIED`.
4. El orquestador toma un claim de conciliación en otra transacción breve.
5. C2b abre sus propias transacciones y locks canónicos; nunca llama APIs
   externas.

El endpoint webhook no llama C2b ni espera al proveedor. Su ACK conserva el
contrato de C2a: confirma únicamente que el evento autenticado quedó durable en
el inbox.

### Claims y concurrencia

No se agregó migración. Se reutilizan los campos recuperables de
`ProviderEvent`:

- `claim_token`;
- `processing_started_at`;
- `next_retry_at`;
- `last_error_code` y `last_error_detail`;
- `reconciliation_attempts`.

El claim usa `SELECT ... FOR UPDATE SKIP LOCKED` y selecciona en orden
`received_at, pk`. Dos workers pueden ejecutarse simultáneamente: sólo uno
reclama un evento dado. Si un claim supera `PROVIDER_EVENT_WORKER_STALE_MINUTES`,
otro worker puede recuperarlo.

C2b mantiene su idempotencia como segunda defensa. Incluso si un proceso tarda
más que el umbral stale y dos workers alcanzan C2b, los locks y estados
terminales de C2b permiten un solo hecho financiero y un solo efecto comercial.

### Resultados y errores

| Situación | Persistencia | Próxima acción |
|---|---|---|
| Conciliación válida | `APPLIED` | terminal |
| Estado sin efecto financiero | `IGNORED` | terminal |
| Conflicto financiero tipado | `REVIEW_REQUIRED` + `PaymentReconciliationCase` | revisión humana |
| Error de base o inesperado antes de terminar C2b | `NOT_EVALUATED`, error y `next_retry_at` | retry automático |
| Caída con claim abierto antes de C2b | claim stale | recuperación automática |
| Caída después del commit C2b | estado terminal + claim residual | limpieza al reiniciar, sin segundo efecto |

`mark_verified_provider_event_for_review()` materializa como revisión los
`ProviderReconciliationConflict` que antes sólo se propagaban al caller. No
crea pagos ni efectos comerciales por sí mismo.

Las actualizaciones de retry filtran explícitamente
`reconciliation_status=NOT_EVALUATED` y el token del claim. Por eso un error o
una limpieza tardía no puede degradar `APPLIED`, `REVIEW_REQUIRED` ni `IGNORED`.

Los eventos con snapshot anterior siguen la regla C2b existente: quedan
`IGNORED / STALE_EVENT` y no modifican el estado de conciliación ni
`last_reconciled_at` del Attempt ya aplicado.

## Ejecución automática

El comando conserva el modo de un ciclo para operación y diagnóstico:

```bash
python -X utf8 manage.py process_provider_events
```

El modo productivo persistente es:

```bash
python -X utf8 manage.py process_provider_events --watch
```

En `--watch`:

- drena lotes mientras haya trabajo;
- duerme el intervalo configurado cuando el inbox queda vacío;
- registra una excepción de ciclo y continúa después del intervalo;
- deja que systemd reinicie el proceso si éste termina.

Se entrega `deploy/systemd/bohemia-provider-events.service` como mecanismo de
supervisión productiva. No se incorporó Celery, Redis ni otra infraestructura
pesada.

## Configuración por entorno

El servicio carga `/etc/bohemia/bohemia.env`. Además de las variables Mercado
Pago y Django ya requeridas por C1/C2a, admite:

```dotenv
PROVIDER_EVENT_WORKER_LIMIT=100
PROVIDER_EVENT_WORKER_STALE_MINUTES=10
PROVIDER_EVENT_WORKER_RETRY_SECONDS=60
PROVIDER_EVENT_WORKER_POLL_SECONDS=5
```

| Variable | Función | Restricción |
|---|---|---|
| `PROVIDER_EVENT_WORKER_LIMIT` | máximo por fase y ciclo | 1–1000 |
| `PROVIDER_EVENT_WORKER_STALE_MINUTES` | antigüedad para recuperar un claim | entero positivo |
| `PROVIDER_EVENT_WORKER_RETRY_SECONDS` | demora fija de retry | entero positivo |
| `PROVIDER_EVENT_WORKER_POLL_SECONDS` | espera con inbox vacío o ciclo fallido | entero positivo |

Los argumentos CLI pueden reemplazar esos valores. Los secretos no están en la
unidad systemd ni en el repositorio; permanecen en el `EnvironmentFile`.

## Procedimiento de despliegue

Supuestos de la unidad entregada:

- código: `/opt/bohemia`;
- proyecto Django: `/opt/bohemia/bohemiacore`;
- virtualenv: `/opt/bohemia/venv`;
- usuario y grupo: `bohemia`;
- entorno/secrets: `/etc/bohemia/bohemia.env`.

Si la instalación usa otras rutas o usuario, se debe adaptar la unidad antes de
activarla.

```bash
sudo install -o root -g root -m 0644 \
  deploy/systemd/bohemia-provider-events.service \
  /etc/systemd/system/bohemia-provider-events.service

sudo systemctl daemon-reload
sudo systemctl enable --now bohemia-provider-events.service
sudo systemctl status bohemia-provider-events.service
sudo journalctl -u bohemia-provider-events.service -f
```

Comprobación posterior al despliegue:

1. enviar un webhook sandbox firmado;
2. verificar que el HTTP ACK sólo informa recepción/duplicado;
3. observar `RECEIVED → VERIFIED → APPLIED/REVIEW_REQUIRED/IGNORED`;
4. comprobar `Pago.provider_payment_id` único y el efecto esperado;
5. reiniciar la unidad y confirmar que no se repite el hecho financiero:

```bash
sudo systemctl restart bohemia-provider-events.service
```

Se pueden ejecutar varias instancias si se desea redundancia. PostgreSQL y
`SKIP LOCKED` son requisitos para la garantía concurrente validada.

## Pruebas F2

Las pruebas nuevas cubren:

1. `RECEIVED → VERIFIED → C2b APPLIED` en un ciclo;
2. dos eventos del mismo pago sin duplicar `Pago`;
3. dos workers concurrentes con un único claim;
4. interrupción antes de C2b, retry y recuperación;
5. interrupción después del commit C2b y limpieza sin segundo efecto;
6. error temporal del proveedor y recuperación completa C2a→C2b;
7. conflicto financiero no recuperable convertido en revisión explícita;
8. reinicio mediante recuperación de claim stale;
9. evento antiguo ignorado sin degradar el Attempt aplicado;
10. retry sin duplicar `MovimientoStock`;
11. eventos duplicados de BOOKING sin duplicar `Turno`;
12. comando de un ciclo ejecutando el pipeline completo.

Ejecución específica:

```text
python -X utf8 manage.py test \
  gestion.tests.test_provider_event_pipeline \
  gestion.tests.test_provider_event_pipeline_concurrency \
  --noinput

Ran 12 tests in 39.748s
OK
```

## Regresión obligatoria

Se ejecutó sobre PostgreSQL real:

```text
python -X utf8 manage.py test \
  gestion.tests.test_provider_events \
  gestion.tests.test_provider_event_concurrency \
  gestion.tests.test_provider_reconciliation \
  gestion.tests.test_provider_reconciliation_concurrency \
  gestion.tests.test_provider_event_pipeline \
  gestion.tests.test_provider_event_pipeline_concurrency \
  gestion.tests.test_payment_confirmation \
  gestion.tests.test_payment_confirmation_concurrency \
  gestion.tests.test_order_inventory \
  gestion.tests.test_order_inventory_concurrency \
  gestion.tests.test_inventory_permissions_d3 \
  usuarios.test_roles \
  usuarios.test_access_services \
  --noinput

Ran 148 tests in 624.423s
OK
```

Esto cubre C2a/C2b, B3, D2, roles y permisos, incluidos sus casos
concurrentes.

## Limitaciones operativas

- El polling introduce hasta `PROVIDER_EVENT_WORKER_POLL_SECONDS` de latencia
  cuando el inbox estaba vacío.
- El retry usa demora fija; no implementa backoff exponencial.
- `REVIEW_REQUIRED` exige operación humana mediante el flujo de conciliación
  existente; no se revierte ni acredita automáticamente.
- systemd es la receta entregada para Linux. Otra plataforma necesita un
  supervisor equivalente que mantenga `--watch` activo.
- Logs, alertas y retención deben integrarse con la observabilidad del servidor;
  la unidad escribe en journald y el evento conserva códigos resumidos.
- La disponibilidad depende de PostgreSQL y de la API oficial de Mercado Pago.

## Archivos F2

- `bohemiacore/gestion/provider_event_pipeline.py`;
- `bohemiacore/gestion/provider_reconciliation_services.py`;
- `bohemiacore/gestion/management/commands/process_provider_events.py`;
- `bohemiacore/gestion/tests/test_provider_event_pipeline.py`;
- `bohemiacore/gestion/tests/test_provider_event_pipeline_concurrency.py`;
- `deploy/systemd/bohemia-provider-events.service`;
- `CORRECCION_BH058_F2_PIPELINE_CONCILIACION.md`.

## Veredicto

**BH-058 F2 = VALIDADO**
