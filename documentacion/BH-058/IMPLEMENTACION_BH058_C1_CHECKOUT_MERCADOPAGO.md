# BH-058 C1 — Checkout Mercado Pago

Fecha de validación: 2026-10-28.

## Alcance implementado

- Checkout Pro mediante **Orders API** (`POST /v1/orders`) para obligaciones `BOOKING` y `ORDER`.
- Canal `ONLINE` para la persona propietaria o personal con autoridad operativa.
- Canal `IN_PERSON` exclusivamente con `gestion.register_payment`.
- Conversión idempotente del carrito a `OrdenCompra`, conservando compromisos D2.
- Retornos success/pending/failure estrictamente informativos.

No se implementaron webhooks C1, `ProviderEvent`, conciliación, creación de `Pago`, aprobación de `PaymentIntent`, confirmación de `Turno`, consumo A2, entrega/consumo de stock, refunds, Point, QR ni C2.

## Diseño y garantías

### Persistencia

La migración `gestion/0034_provider_payment_attempt_c1.py` crea `ProviderPaymentAttempt` con:

- contexto exclusivo `BOOKING` o `ORDER`;
- monto y moneda congelados desde `PaymentIntent.required_amount/currency` u `OrdenCompra.total` (órdenes ARS);
- referencia opaca namespaced `bh:c1:<context>:<uuid>`;
- clave del cliente separada de la clave enviada al provider;
- unicidad por actor/clave, por referencia y por clave provider;
- un solo Attempt activo por obligación;
- estados `PROCESSING`, `READY`, `OUTCOME_UNKNOWN`, `FAILED` y `EXPIRED`;
- URL, ID/estado provider, expiración, contador de llamadas y errores sanitizados.

Las referencias C1 son ignoradas explícitamente por el webhook legacy.

### Frontera provider

`gestion/payment_providers.py` es la única capa que usa el SDK. `MercadoPagoAdapter`:

- usa `mercadopago==3.2.0` fijado en `requirements-payments.txt`;
- envía `X-Idempotency-Key` y deshabilita retries opacos del SDK;
- aplica timeout configurable;
- valida moneda, retornos y URL HTTPS de checkout;
- clasifica timeout, conexión, HTTP 408/423/429/5xx y respuestas incompletas como `OUTCOME_UNKNOWN`;
- no persiste payloads, tokens ni errores crudos.

Las consultas/payment y Preferences legacy también atraviesan el adapter; C1 no usa Preferences.

### Transacciones y carreras

`gestion/provider_checkout_services.py` aplica:

1. **TX1:** lock y validación de obligación, ownership/permiso, monto, moneda, vigencia e idempotencia; persiste/reutiliza Attempt.
2. **HTTP:** llamada al adapter fuera de `transaction.atomic` y sin locks de base de datos.
3. **TX2:** vuelve a validar obligación y persiste el resultado.

El orden de locks es siempre obligación → Attempt. La prueba PostgreSQL de dos claves concurrentes confirmó un único Attempt y una única llamada provider.

Un resultado incierto sólo se reintenta con la misma clave provider. Una clave nueva reutiliza el Attempt incierto y no crea otro checkout. Una respuesta tardía luego de cancelación/vencimiento queda trazada como `EXPIRED`, sin URL utilizable y sin reactivar el HOLD.

### Invariantes financieras

- BOOKING exige Intent activo, HOLD activo, ownership o autoridad y ausencia de pagos existentes.
- ORDER exige estado pagable, líneas cuyo total coincide, compromisos D2 activos/coherentes y ausencia de pagos existentes.
- El request no acepta monto ni moneda.
- Crear/visitar un checkout no crea `Pago`, no aprueba Intent, no crea `Turno`, no cambia una orden a pagada y no consume stock.
- El serializer declara `financial_authority: false`.

## API

- `POST /api/gestion/payment-intents/{public_id}/checkout/`
- `POST /api/gestion/ordenes-compra/{id}/checkout/`
- `POST /api/gestion/checkout/iniciar-pago/` (compatibilidad de carrito)
- `POST /api/gestion/carrito/generar-pago-mercadopago/` (compatibilidad)

Header obligatorio: `Idempotency-Key` (máximo 128 caracteres).

Body permitido:

```json
{"channel": "ONLINE"}
```

Para enlaces presenciales se usa `{"channel": "IN_PERSON"}` y se exige `gestion.register_payment` mediante `user.has_perm(...)`.

## Configuración requerida

Todas las credenciales permanecen en backend. La integración falla cerrada si falta configuración:

```env
MERCADO_PAGO_ACCESS_TOKEN=...
MERCADO_PAGO_CHECKOUT_CURRENCY=ARS
MERCADO_PAGO_CHECKOUT_TIMEOUT_SECONDS=8
MERCADO_PAGO_CHECKOUT_TTL_MINUTES=30
MERCADO_PAGO_CHECKOUT_SUCCESS_URL=https://.../compra-exitosa
MERCADO_PAGO_CHECKOUT_PENDING_URL=https://.../compra-pendiente
MERCADO_PAGO_CHECKOUT_FAILURE_URL=https://.../compra-fallida
```

HTTP sólo se admite para `localhost`/`127.0.0.1` en desarrollo.

## Frontend

- `Carrito.js` genera una clave por operación y la conserva ante `OUTCOME_UNKNOWN`.
- Sólo redirige si el backend devuelve un Attempt `READY` con URL validada.
- Las páginas `/compra-exitosa`, `/compra-pendiente` y `/compra-fallida` advierten que navegador y query params no confirman pagos.

## Validación ejecutada

- C1 funcional, errores, idempotencia y carreras PostgreSQL: **15 tests OK**.
- Regresión A (HOLD/consumo/concurrencia): **48 tests OK**.
- Regresión B1 (PaymentIntent): **21 tests OK**.
- Regresión B2 (pagos manuales): **26 tests OK**.
- Regresión B3 (confirmación): **18 tests OK**.
- Regresión D1/D3 (stock/permisos/concurrencia): **37 tests OK**.
- Regresión D2 (órdenes/compromisos/concurrencia): **23 tests OK**.
- `manage.py check`: OK.
- `manage.py makemigrations --check --dry-run`: sin cambios.
- `manage.py migrate --noinput`: `0034_provider_payment_attempt_c1` aplicada.
- `python -m compileall -q gestion`: OK.
- `npm run build`: compiló correctamente; sólo advertencias preexistentes de ESLint/Browserslist.
- `git diff --check`: sin errores (sólo avisos de normalización CRLF).

La ejecución agregada `manage.py test gestion.tests` queda afectada por un defecto preexistente de aislamiento en `test_auditoria.py`: conserva `_thread_locals.user` entre tests y luego referencia un usuario revertido, produciendo FK inválida. No se modificó ese test ajeno; todas las regresiones A/B/D y C1 se ejecutaron explícitamente y pasaron.

## Referencias verificadas

- Mercado Pago, Checkout Pro vía Orders API: <https://www.mercadopago.com.br/developers/en/docs/checkout-pro-orders/create-order>
- SDK Python instalado: 3.2.0, recursos `order().create(...)` y `order().get(...)`.

BH-058 C1 = VALIDADO
