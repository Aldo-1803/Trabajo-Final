# BH-058 F7.3 — Ejecución durable e idempotente de refunds

**Fecha:** 2026-11-02
**Alcance:** exclusivamente F7.3; no incluye confirmación financiera F7.4 ni
efectos comerciales posteriores.

## 1. Resultado

F7.3 incorpora la operación técnica que ejecuta un refund previamente aprobado
en F7.2 y conserva esta separación obligatoria:

```text
DECISIÓN APROBADA
  -> OPERACIÓN DURABLE
  -> RESPUESTA/ESTADO DEL PROVEEDOR
  -> futura CONFIRMACIÓN FINANCIERA (fuera de F7.3)
```

Una respuesta HTTP exitosa o un refund con estado `processed` sólo deja la
operación en `SUBMITTED`. F7.3 no asigna `CONFIRMED`, no crea un ajuste
compensatorio y no modifica el neto financiero.

## 2. Contrato oficial de Mercado Pago

La implementación usa exclusivamente Checkout vía **Orders API**:

- documentación de reembolsos y cancelaciones:
  <https://www.mercadopago.com.ar/developers/es/docs/checkout-api-orders/payment-management/refunds-cancellations>;
- referencia de refund de Order:
  <https://www.mercadopago.com.ar/developers/es/reference/online-payments/checkout-api/refund-order/post>.

Contrato aplicado:

- `POST /v1/orders/{order_id}/refund`;
- encabezado `X-Idempotency-Key` estable, de hasta 128 caracteres;
- cuerpo limitado a `transactions[0].id` y `transactions[0].amount`;
- consulta de recuperación mediante `GET /v1/orders/{order_id}`;
- evidencia de recuperación tomada de `transactions.refunds`.

La referencia de Orders API no ofrece una consulta de refund por clave
idempotente. Por ello, después de un timeout nunca se reenvía a ciegas. Si la
consulta de la Order no produce exactamente una coincidencia nueva por Order,
transacción e importe, la operación permanece `UNKNOWN` para revisión manual.

## 3. Modelo durable

### `FinancialRefundOperation`

Conserva:

- decisión `APPROVE_REFUND` y Pago de origen;
- importe, moneda y medio de pago copiados de la autorización y del Pago;
- proveedor, Order y transacción de proveedor;
- clave idempotente externa estable y fingerprint de la solicitud;
- IDs de refund existentes antes de ejecutar;
- estado, timestamps, referencia externa y evidencia sanitaria;
- operador creador y contador de llamadas al proveedor.

Restricciones principales:

- una sola operación por decisión;
- unicidad de clave idempotente externa;
- unicidad de refund externo por proveedor;
- unicidad de clave de comando por operador;
- importe positivo;
- coherencia entre `CONFIRMED` y `confirmed_at` para el futuro F7.4.

El modelo y sus QuerySets rechazan creación, actualización y eliminación fuera
de sus servicios.

### `FinancialRefundOperationEvent`

Es evidencia append-only de:

- creación;
- claim previo al envío;
- respuesta recibida;
- fallo definitivo;
- resultado ambiguo;
- consulta de recuperación.

No se persisten access tokens, cuerpos HTTP completos, datos de tarjeta, datos
del pagador ni respuestas crudas.

## 4. Estados

| Estado | Significado en F7.3 |
|---|---|
| `PENDING` | Identidad y operación creadas; todavía no reclamada para HTTP. |
| `SUBMITTED` | Claim confirmado antes del HTTP o respuesta/consulta que acredita el envío. No es confirmación financiera. |
| `FAILED` | Rechazo definitivo del proveedor. No habilita reenvío automático. |
| `UNKNOWN` | Timeout, ambigüedad o recuperación no unívoca. Sólo admite consulta oficial. |
| `CONFIRMED` | Reservado para F7.4; F7.3 nunca lo asigna. |

## 5. Fronteras transaccionales e idempotencia

La ejecución tiene tres tramos:

1. **TX1:** bloquea caso, contexto financiero, Pago, solicitud y decisión;
   valida y crea la operación `PENDING` con identidad idempotente estable.
2. **TX2:** reclama una única vez `PENDING -> SUBMITTED`, incrementa el contador
   y confirma el evento `SUBMISSION_STARTED`.
3. **Sin locks ni transacción abierta:** realiza el HTTP y después persiste una
   respuesta sanitaria en otra transacción corta.

Así, la identidad existe antes del HTTP y la red nunca ocurre bajo locks. Un
segundo operador encuentra la misma operación y no vuelve a invocar al
proveedor. Si el proceso cae después del claim, el estado `SUBMITTED` impide el
reenvío y obliga a recuperar por consulta.

## 6. Validaciones y autoridad

La API y el dominio exigen conjuntamente:

- usuario autenticado y activo;
- permiso `gestion.reconcile_external_payment`;
- caso abierto;
- solicitud F7.2 en `DECIDED`;
- decisión final vigente `APPROVE_REFUND`;
- Pago explícito perteneciente al caso/contexto;
- Pago `RECONCILED`;
- importe autorizado positivo que no supere el Pago ni su saldo reservado;
- misma moneda entre decisión y Pago;
- método y proveedor `MERCADO_PAGO`;
- Order y transacción externas completas y coherentes;
- ventana documentada de 180 días;
- clave idempotente válida.

Pagos en efectivo, transferencias y otros medios sin contrato de ejecución
verificable se rechazan con `MANUAL_REFUND_EXECUTION_UNSUPPORTED`. F7.3 no
simula una devolución manual.

## 7. API semántica

Sobre `/api/gestion/payment-reconciliation-cases/{public_id}/`:

| Método y acción | Uso |
|---|---|
| `POST execute-authorized-refund/` | Ejecuta una aprobación usando `payment_public_id` y encabezado `Idempotency-Key`. |
| `GET refund-operation/` | Consulta estado y evidencia sanitaria. |
| `POST recover-refund-operation/` | Consulta la Order oficial; no acepta payload y no reenvía. |

No se exponen CRUD, claves idempotentes, fingerprints ni acceso de clientas.

## 8. Invariantes de no efecto

F7.3 no modifica:

- `Pago.status` ni asigna `Pago.REVERSED`;
- neto conciliado ni hechos financieros compensatorios;
- estado o cierre del `PaymentReconciliationCase`;
- `PaymentIntent`, `SlotHold`, Turnos o solicitudes técnicas;
- `OrdenCompra`, compromisos, movimientos o existencias de stock;
- cancelaciones, créditos u otros resultados comerciales.

Todos esos efectos requieren confirmación y servicios posteriores explícitos.

## 9. Recuperación segura

La recuperación valida:

- que el snapshot corresponda a la misma Order solicitada;
- misma transacción e importe;
- ID externo presente;
- exclusión de refunds ya observados antes de ejecutar;
- coincidencia única.

Una coincidencia única actualiza evidencia y deja `SUBMITTED`. Cero, varias,
una Order distinta o un error de consulta dejan `UNKNOWN`. Ninguna rama de
recuperación llama a `submit_refund`.

## 10. Pruebas

Las pruebas usan mocks; no realizan refunds reales ni llamadas de red.

Los escenarios obligatorios cubren:

1. identidad durable y claim confirmados antes del HTTP;
2. respuesta exitosa que permanece `SUBMITTED`;
3. invariantes financieros, comerciales y de stock;
4. retry del mismo operador sin segunda llamada;
5. retry de otro operador sin segunda llamada;
6. carrera PostgreSQL de dos operadores;
7. timeout/ambigüedad a `UNKNOWN`;
8. rechazo definitivo a `FAILED`;
9. recuperación única por consulta oficial;
10. recuperación ausente o no unívoca que permanece `UNKNOWN`;
11. rechazo de snapshot perteneciente a otra Order;
12. falta de aprobación, Pago incompatible y medio manual;
13. cuenta inactiva, clienta o staff sin permiso;
14. API semántica y ausencia de secretos en la respuesta.

Resultados ejecutados:

| Área | Resultado |
|---|---:|
| F7.3, adaptador y concurrencia PostgreSQL | 21/21 OK |
| Regresiones F7.1/F7.2, C2a/C2b y F2 | 76/76 OK |

## 11. Migración y archivos

- `bohemiacore/gestion/migrations/0038_refund_execution_f7_3.py`;
- `bohemiacore/gestion/refund_execution_services.py`;
- `bohemiacore/gestion/models.py`;
- `bohemiacore/gestion/payment_providers.py`;
- `bohemiacore/gestion/financial_case_views.py`;
- `bohemiacore/gestion/financial_case_serializers.py`;
- `bohemiacore/gestion/tests/test_refund_execution.py`;
- `bohemiacore/gestion/tests/test_refund_execution_concurrency.py`;
- `bohemiacore/gestion/tests/test_payment_providers.py`.

## 12. Límites explícitos

Quedan fuera de F7.3:

- confirmar externamente un refund como hecho financiero;
- materializar ajustes, neto o `Pago.REVERSED`;
- cerrar casos;
- cancelar Turnos u órdenes;
- liberar, consumir o reponer stock;
- ejecutar devoluciones manuales;
- reintentar automáticamente operaciones ambiguas o fallidas;
- interfaz frontend;
- cualquier parte de F7.4.
