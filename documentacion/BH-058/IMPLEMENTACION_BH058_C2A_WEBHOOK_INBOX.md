# BH-058 C2a — Webhook seguro e inbox de Mercado Pago

Fecha: 2026-10-28

Fuentes oficiales consultadas:

- `https://www.mercadopago.com.br/developers/en/docs/checkout-pro-orders/notifications`;
- `https://www.mercadopago.com.ar/developers/en/docs/your-integrations/notifications/webhooks`;
- referencia `GET /v1/orders/{order_id}` enlazada desde la guía de Orders.

## Alcance y frontera

C2a recibe notificaciones autenticadas de Orders API, las guarda de forma
idempotente y consulta la Order oficial. No acredita pagos ni ejecuta B3/D2.
En particular, no modifica `Pago`, `PaymentIntent`, `SlotHold`, `Turno`,
`OrdenCompra`, `CompromisoStock` ni `MovimientoStock`.

La confirmación financiera y comercial queda expresamente fuera de este cambio
y pertenece a C2b.

## Contrato oficial aplicado

- firma: `x-signature` con componentes `ts` y `v1`;
- correlación firmada: `x-request-id` y query `data.id`;
- recurso canónico: `GET /v1/orders/{id}` mediante `sdk.order().get(...)`;
- reconocimiento durable: HTTP 201 para evento nuevo y HTTP 200 para duplicado;
- ante imposibilidad de persistir: HTTP 503, para que Mercado Pago reintente.

El receptor acepta exclusivamente el tópico oficial `order`; cualquier otro
tópico falla cerrado. La acción debe comenzar con `order.` y el `data.id` del
cuerpo debe coincidir exactamente con la query firmada. El ejemplo oficial
vigente usa `action: order.processed`, un `id` superior como identidad del
evento y un `data.id` `ORD...` como identidad de la Order.

Se usa `mercadopago.webhook.WebhookSignatureValidator` del SDK 3.2.0. Este
implementa HMAC-SHA256 y `hmac.compare_digest`. No se inventó una ventana de
tiempo: el contrato/SDK permiten una tolerancia opcional, pero la documentación
consultada no establece una para este producto. El replay se neutraliza como
efecto mediante la identidad durable del evento. La rotación se realiza
cambiando `MERCADO_PAGO_WEBHOOK_SECRET`; nunca se registra el secreto, token o
firma.

## Configuración

- `MERCADO_PAGO_ACCESS_TOKEN`;
- `MERCADO_PAGO_WEBHOOK_SECRET` (obligatorio para recibir);
- `MERCADO_PAGO_ENVIRONMENT`: `sandbox` o `production`;
- `MERCADO_PAGO_APPLICATION_ID`;
- `MERCADO_PAGO_SELLER_ID`;
- `MERCADO_PAGO_CHECKOUT_TIMEOUT_SECONDS`.

Los tres datos de identidad se comparan cuando están disponibles en la Order y
en la notificación autenticada. El secreto ausente produce 503 y ningún evento.

## `ProviderEvent`

La migración `0035_provider_event_inbox_c2a.py` agrega el inbox con:

- proveedor, tópico, acción, ID real de evento e ID de recurso;
- fecha de recepción y fecha informada por el proveedor;
- FK opcional a `ProviderPaymentAttempt`;
- snapshot mínimo de notificación y snapshot oficial sanitizado;
- estado, cantidad de intentos, error técnico, próxima fecha de reintento;
- claim UUID y timestamps de inicio/finalización.

La unicidad es `(provider, event_id)`, no el ID de Order. Así, un replay del
mismo evento se reconoce como duplicado y dos eventos legítimos de la misma
Order se conservan por separado. Una colisión del event ID con otra identidad
se rechaza con 409.

Estados:

- `RECEIVED`;
- `FETCH_PENDING`;
- `VERIFIED`;
- `RETRYABLE_ERROR`;
- `REJECTED`;
- `MISMATCH`.

No se guarda el payload completo. Sólo se conservan IDs y metadatos técnicos
permitidos; datos de pagador, token, firma y credenciales se descartan.

## Recepción y procesamiento

`WebhookMercadoPagoView` ejecuta únicamente:

1. validación estructural fail-closed;
2. validación oficial de firma;
3. resolución local opcional del Attempt;
4. `get_or_create` dentro de una transacción corta;
5. respuesta posterior al commit.

No hace HTTP externo. `process_pending_provider_events(...)` reclama un evento
con `select_for_update(skip_locked=True)`, escribe un claim y termina la
transacción antes de consultar Mercado Pago. El resultado sólo se guarda si el
claim continúa vigente. Un `FETCH_PENDING` antiguo vuelve a ser elegible, lo
que recupera interrupciones del proceso.

Comando operativo:

```bash
python manage.py process_provider_events --limit 100 --stale-minutes 10 --retry-seconds 60
```

Timeouts, desconexiones, HTTP 408/423/429/5xx y configuración reparable quedan
en `RETRYABLE_ERROR`. Rechazos 4xx o respuestas no procesables quedan en
`REJECTED`. No se descarta ningún evento autenticado.

## Comparación con `ProviderPaymentAttempt`

La asociación primaria usa `provider_order_id`; nunca se concede autoridad a
un `external_reference` recibido en el webhook. Sobre el snapshot obtenido de
la API se comprueban:

- Order ID exacto;
- `external_reference` exacto y namespace de contexto BOOKING/ORDER;
- importe esperado;
- moneda cuando está disponible;
- estado conocido y tipo online;
- aplicación, vendedor y entorno cuando están disponibles;
- coherencia de identidad con la notificación firmada.

Una divergencia produce `MISMATCH` y conserva el snapshot para revisión. Un
recurso sin Attempt conocido produce `REJECTED/UNKNOWN_RESOURCE`. Ninguno crea
un `Pago` ni cambia el estado del Attempt.

## Webhook legacy

Antes de C2a, las rutas `/api/gestion/checkout/webhook/` y
`/api/checkout/webhook/` aceptaban `payment` sin firma, consultaban Payment API
y podían crear `Pago`, cambiar órdenes y consumir/liberar stock.

Ambas URLs se conservan para no romper configuración de red, pero ahora apuntan
al receptor seguro de Orders. Un payload legacy `payment` es rechazado antes de
cualquier consulta o mutación. Se sacrifica esa compatibilidad funcional porque
mantenerla dejaría una vía pública insegura con autoridad financiera.

## Pruebas

La suite C2a cubre firma válida, inválida y ausente; secreto ausente; tópico,
acción, estructura y `data.id`; persistencia fallida; evento nuevo, replay y
nuevo evento de la misma Order; consulta oficial y sanitización; recurso
desconocido; divergencias de importe, moneda, aplicación y vendedor; error
temporal, reintento y recuperación de claim interrumpido.

Las pruebas PostgreSQL cubren webhook duplicado simultáneo, eventos distintos
para una Order, dos workers, retry simultáneo y llegada/procesamiento de otro
evento mientras una consulta externa permanece abierta. También se verifica la
ausencia de mutaciones financieras, comerciales y de stock.
