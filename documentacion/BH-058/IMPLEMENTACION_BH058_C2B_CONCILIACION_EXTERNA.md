# BH-058 C2b — Conciliación externa y efectos de negocio

Fecha: 2026-10-28

## Alcance

C2b incorpora una única autoridad interna:

```python
reconcile_verified_provider_event(event_id)
```

El servicio consume exclusivamente snapshots persistidos por C2a. No recibe
HTTP, no consulta Mercado Pago y no desplaza lógica financiera al webhook, a
serializers ni al frontend.

Quedan fuera de este incremento los refunds automáticos, Point, QR físico,
nuevos checkouts, promociones, procesos automáticos y cambios de frontend.

## Contrato oficial aplicado

Se revisaron las referencias oficiales de Mercado Pago para Orders y webhooks:

- `https://www.mercadopago.com.br/developers/en/reference/online-payments/checkout-pro/get-order/get`;
- `https://www.mercadopago.com.br/developers/en/docs/checkout-pro-orders/notifications`;
- `https://www.mercadopago.com.ar/developers/en/docs/your-integrations/notifications/webhooks`.

Decisiones:

- la Order no constituye por sí sola evidencia de un Pago elegible;
- sólo una entrada de `transactions.payments` con `status=processed` y
  `status_detail=accredited` se acredita automáticamente;
- la identidad financiera es `(provider_code, provider_payment_id)`, donde el
  identificador oficial es el `PAY…` de la transacción;
- el importe financiero es `paid_amount`, con `confirmed_amount` como fallback
  del mismo snapshot oficial;
- se persisten únicamente campos financieros sanitizados de pagos, refunds y
  chargebacks; no se guardan tokens ni datos del medio de pago;
- `last_updated_date` es la primera referencia temporal para la acreditación y
  `created_date` su fallback. Se conserva por separado recepción/verificación
  interna mediante `ProviderEvent`.

## Persistencia e idempotencia

### Pago

`Pago` incorpora proveedor, ID oficial, Attempt, evento de origen, fecha del
proveedor y snapshot sanitario. La restricción parcial única
`payment_unique_provider_identity` impide dos hechos financieros para un mismo
pago oficial, incluso si llegan eventos diferentes o reconciliadores
concurrentes.

Los pagos externos son creados sólo por `_create_external_from_service`; usan
autoridad de sistema (`recorded_by=None`, `reconciled_by=None`) respaldada por
la identidad del proveedor, sin inventar un administrador.

### ProviderEvent y ProviderPaymentAttempt

Ambos conservan el estado de conciliación. El evento registra decisión, efecto,
IDs financieros, fecha y código; el Attempt conserva el último estado oficial
y si quedó aplicado, parcial, tardío o en revisión. La relación M2M entre
eventos y pagos permite que varios eventos apunten al mismo hecho financiero.

### PaymentReconciliationCase

Los casos ahora admiten exactamente uno de estos contextos:

- BOOKING: `PaymentIntent` + `SlotHold`;
- ORDER: `OrdenCompra`.

También conservan Attempt, evento y pagos relacionados. El `operation_key`
determinista evita casos duplicados.

## Transiciones

### BOOKING

1. Se bloquea el grafo canónico B3.
2. Se revalida evento VERIFIED, referencia, contexto, Order del proveedor,
   moneda e importe del Attempt.
3. Se registra una sola vez el Pago externo.
4. Se suma exclusivamente `Pago.RECONCILED`.
5. Se delega a `approve_payment_intent_and_confirm_booking`.

Si el umbral no se alcanza, el Intent queda pendiente y el HOLD vigente. Si se
alcanza, B3/A2 confirma exactamente un Turno. Un Intent ya aprobado puede
recibir saldo posterior sin resucitar ni reevaluar el vencimiento del HOLD
consumido.

Un pago cuya acreditación ocurrió después del límite, o que llega cuando el
Intent/HOLD ya venció o fue liberado, se conserva como
`PENDING_RECONCILIATION`, abre un caso `LATE_PAYMENT` y no crea HOLD, Turno ni
aprobación artificial.

### ORDER

El pago válido mueve la orden a `PAGADO`; `COMPLETADO` continúa significando
salida física. C2b no escribe stock ni consume compromisos. La entrega posterior
continúa pasando por `apply_order_inventory_effect` (D2), única autoridad de
stock.

Una orden cancelada, rechazada, sin compromisos activos o cuyo total ya no
coincide con el Attempt conserva el pago como pendiente de conciliación y abre
un caso. No hay salida arbitraria de inventario.

### Estados sin efecto o posteriores

| Evidencia | Decisión C2b |
|---|---|
| pendiente, rechazada, fallida o cancelada sin pago acreditado | evento `IGNORED`, sin Pago ni efecto comercial |
| snapshot anterior a otro ya conciliado | `STALE_EVENT`, sin degradación |
| pago acreditado consistente | hecho financiero idempotente y efecto BOOKING/ORDER |
| importe, obligación o sobrepago inconsistente | Pago preservado y revisión, sin efecto comercial |
| refund, refund parcial o chargeback posterior | `POST_PAYMENT_CHANGE`, sin reversión automática |
| regresión posterior de un pago ya registrado | revisión, sin degradar la operación confirmada |

## Atomicidad y concurrencia

- no hay HTTP dentro de transacciones;
- BOOKING reutiliza el orden de locks de B3;
- ORDER bloquea OrdenCompra, Pagos y CompromisoStock;
- el índice único financiero resuelve carreras entre eventos distintos;
- un fallo técnico antes del commit revierte hecho y efecto, permitiendo retry;
- una imposibilidad comercial conocida conserva Pago y caso en el mismo commit;
- un retry posterior al commit es de sólo lectura y no duplica Pago, Turno,
  auditoría ni stock.

## Auditoría y permiso

Se auditan:

- `EXTERNAL_PAYMENT_RECONCILED`;
- `PROVIDER_EVENT_RECONCILED`;
- `ORDER_PAYMENT_RECONCILED`;
- `EXTERNAL_PAYMENT_REVIEW_REQUIRED`.

Los registros incluyen proveedor, referencia oficial, contexto, decisión,
efecto, pagos y caso. A2 conserva la responsabilidad exclusiva por sus
notificaciones.

La revisión manual queda reservada a
`gestion.reconcile_external_payment`. La migración otorga ese permiso sólo al
grupo `ADMINISTRADOR`; no usa `is_staff`, `Personal.rol` ni un BusinessRole como
autorización directa.

## Migración

`0036_provider_reconciliation_c2b.py` agrega los campos, relaciones,
restricciones, estado `OrdenCompra.PAGADO` y el permiso con seed idempotente.
Fue aplicada correctamente sobre PostgreSQL y `makemigrations --check` no
detectó deriva.

## Pruebas ejecutadas

| Área | Resultado |
|---|---:|
| C2b funcional | 20/20 OK |
| C2b concurrencia PostgreSQL | 5/5 OK |
| adaptador y sanitización de proveedor | 6/6 OK |
| C2a/C1 | 32/32 OK |
| A1/A2 | 48/48 OK |
| B1/B2/B3 | 65/65 OK |
| D1/D2/D3 | 60/60 OK |
| roles y `/me/` | 31/31 OK |

También se ejecutaron `manage.py check`, migración 0036,
`makemigrations --check`, `compileall` y `git diff --check`. No se ejecutó build
frontend porque C2b no modifica frontend.

## Pendientes fuera de C2b

- interfaz operativa para resolver casos con el permiso nuevo;
- políticas explícitas de refund/reversión y sus efectos compensatorios;
- ejecución asíncrona del servicio después del inbox C2a;
- nuevos medios presenciales o Point/QR físico.
