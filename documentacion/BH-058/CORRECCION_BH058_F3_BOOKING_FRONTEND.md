# BH-058 F3 — BOOKING frontend con checkout y seguimiento

Fecha de cierre: 2026-10-29

## Alcance

Se completó exclusivamente la experiencia online de la clienta:

```text
Solicitud técnica aprobada
        ↓ A1
SlotHold vigente
        ↓ B1
PaymentIntent (seña o total según política)
        ↓ C1
Checkout Mercado Pago
        ↓ C2a / C2b / B3
seguimiento seguro → Turno confirmado
```

El frontend no calcula importes contractuales, no acredita pagos, no consume el
HOLD y no crea el Turno. Esas decisiones continúan en A1/A2, B1/B2/B3 y
C1/C2a/C2b.

## Brechas encontradas antes del cambio

- `SolicitudesTecnicas.js` terminaba después de crear el `SlotHold`.
- No había lectura previa de los modos habilitados por `PaymentPolicy`; la UI no
  podía ofrecer seña/total sin duplicar reglas B1.
- No se creaba ni reutilizaba `PaymentIntent` desde la interfaz.
- C1 no era invocado para BOOKING desde frontend.
- las rutas de retorno sólo mostraban el parámetro de retorno y no consultaban
  el estado propio del Intent;
- el detalle público de `PaymentIntent` no agregaba el checkout persistido, el
  `Turno` confirmado ni los casos de conciliación necesarios para representar
  el recorrido completo;
- tras recargar no existía un listado privado mínimo para recuperar el HOLD.

## Pantallas

### Solicitudes técnicas

`frontend/src/pages/cliente/SolicitudesTecnicas.js` recupera las solicitudes y
los HOLDs propios. Para cada solicitud con HOLD delega el recorrido financiero a
`BookingPaymentFlow.js`.

La tarjeta muestra:

- servicios, fecha/hora y profesional;
- vencimiento informado por `expires_at`;
- total contractual;
- modalidades y monto de seña/total entregados por B1;
- estado del checkout, del pago y de la confirmación.

### Retorno Mercado Pago

`RetornoMercadoPago.js` atiende:

- `/compra-exitosa`;
- `/compra-pendiente`;
- `/compra-fallida`.

Las tres rutas requieren perfil Cliente. El valor de la ruta sólo se presenta
como información del navegador. La pantalla recupera de `sessionStorage`
únicamente el UUID del Intent y consulta el endpoint autenticado. No usa
`status`, `payment_id`, `collection_status` ni otro parámetro del proveedor como
evidencia financiera.

## Endpoints utilizados

| Método y endpoint | Uso |
| --- | --- |
| `GET /api/gestion/solicitudes-tecnicas/` | solicitudes propias y estado técnico |
| `GET /api/gestion/slot-holds/` | listado privado mínimo para reanudar |
| `GET /api/gestion/slot-holds/{public_id}/` | vigencia autoritativa antes de operar |
| `POST /api/gestion/slot-holds/{public_id}/release/` | liberación explícita existente |
| `GET /api/gestion/payment-intents/options/?slot_hold_public_id=...` | cotización B1 sin crear obligación |
| `POST /api/gestion/payment-intents/` | creación/reutilización B1 con `Idempotency-Key` |
| `GET /api/gestion/payment-intents/{public_id}/` | seguimiento propio seguro |
| `POST /api/gestion/payment-intents/{public_id}/checkout/` | C1 BOOKING con `Idempotency-Key` |

Los dos agregados de lectura son deliberadamente mínimos:

1. el listado de HOLDs filtra por `request.user.cliente` y sólo añade
   `solicitud_id`/`created_at` en ese listado, preservando el contrato A1 de
   create/retrieve;
2. `options` exige ownership del HOLD y reutiliza exactamente los cálculos,
   validaciones, locks, política publicada y redondeo de B1.

## Recorrido e idempotencia

1. La UI obtiene un HOLD de A1 o recupera el último HOLD de la solicitud.
2. Consulta `options`; el backend devuelve total, moneda y sólo las modalidades
   permitidas. Si ya existe un Intent activo/aprobado, lo devuelve para
   reutilizarlo.
3. La clienta elige entre las opciones recibidas. No existe campo de importe.
4. La creación del Intent envía sólo `slot_hold_public_id` y `mode`. La misma
   combinación conserva su `Idempotency-Key` durante reintentos.
5. Antes de crear el Intent y antes de C1 se vuelve a consultar el HOLD.
6. C1 recibe sólo `channel: ONLINE`; el frontend redirige exclusivamente a
   `checkout_url` de la respuesta.
7. El UUID del Intent se conserva en `sessionStorage` para continuar después de
   la navegación externa.
8. El retorno y la tarjeta consultan el Intent propio. C2a/C2b/B3 son quienes
   registran dinero y confirman la reserva.

No se crea otro HOLD automáticamente y no se crea una segunda obligación al
reintentar checkout.

## Temporizador

- El valor inicial usa `countdown.seconds_remaining`, derivado por backend de
  `expires_at` y hora de base de datos.
- El decremento del navegador sólo es informativo.
- La UI resincroniza el HOLD cada 15 segundos, cuando llega visualmente a cero y
  antes de cada operación sensible.
- El backend vuelve a validar estado y vencimiento dentro de sus transacciones.
- Un HOLD vencido/liberado deshabilita pago y ofrece consultar disponibilidad de
  nuevo; nunca se extiende ni recrea automáticamente.

## Estados visibles

El serializer del Intent agrega `tracking`, `hold_effective_state`, checkout C1
persistido y `confirmed_turno_id`, siempre dentro del queryset con ownership.

| Estado UI | Significado |
| --- | --- |
| `READY_FOR_CHECKOUT` | Intent vigente sin checkout |
| `PAYMENT_VERIFICATION` | checkout creado o consulta oficial en curso |
| `CHECKOUT_UNCERTAIN` | C1 no pudo determinar el resultado; admite retry idempotente |
| `CHECKOUT_ERROR` | C1 falló sin crear una obligación nueva |
| `PAYMENT_PENDING` | snapshot oficial pendiente o pago parcial |
| `PAYMENT_REJECTED` | snapshot oficial no acreditado/rechazado |
| `HOLD_EXPIRED` | HOLD/Intent sin vigencia |
| `ADMIN_REVIEW` | conciliación financiera requiere intervención |
| `PAID_WITHOUT_BOOKING` | pago preservado, pero reserva no confirmable o tardía |
| `CONFIRMED` | B3 confirmó y existe `Turno` |
| `CANCELLED` | Intent cancelado |

Los casos de revisión y los pagos pendientes de conciliación tienen prioridad
sobre cualquier mensaje optimista del retorno.

## Pruebas

### F3 dirigidas

- Backend: `gestion.tests.test_booking_frontend_api` valida ownership, no
  exposición entre clientas, opciones B1, inexistencia de importes arbitrarios,
  reanudación, expiración, checkout persistido, pendiente, rechazo y
  conciliación.
- Frontend: `BookingPaymentFlow.test.js`, `RetornoMercadoPago.test.js` y
  `SolicitudesTecnicas.test.js` cubren HOLD/countdown, seña, total, creación,
  idempotencia, C1, retry, expiración, resultado incierto, retorno informativo,
  confirmación por backend y revisión.

### Regresiones y controles

Se ejecutaron:

- A1/A2: HOLD, consumo y concurrencia;
- B1/B2/B3: Intent, pagos manuales, confirmación y concurrencia;
- C1/C2a/C2b: proveedor, checkout, inbox, pipeline, conciliación y concurrencia;
- roles, servicios de acceso y `/me/`;
- suite frontend completa, incluidos Turnos, navegación y rutas protegidas;
- `npm run build`;
- `python -X utf8 manage.py check`;
- `python -X utf8 manage.py makemigrations --check --dry-run`;
- `git diff --check`.

Resultados finales:

- regresiones backend requeridas: **243/243 OK**;
- suite frontend completa: **26/26 suites, 204/204 tests OK**;
- pruebas F3 dirigidas: **6 backend y 16 frontend OK**;
- build de producción: exitoso, con warnings preexistentes en archivos ajenos a
  F3.

No se realizaron cobros reales.

## Limitaciones de sandbox

- No se valida el comportamiento de una cuenta Mercado Pago real ni tiempos de
  acreditación de producción.
- Checkout, eventos y conciliación se prueban con adaptadores/mocks y snapshots
  sanitizados ya definidos por C1/C2a/C2b.
- Si el proveedor acredita después del vencimiento o no puede confirmarse el
  Turno, la UI informa revisión; no implementa refund, crédito ni resolución
  manual nueva.

## Fuera de alcance preservado

No se modificaron pagos presenciales B2, reglas financieras de C1, inventario,
promociones, rutinas, diagnóstico, refunds, Point/QR ni un reconciliador
alternativo.
