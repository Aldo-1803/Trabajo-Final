# BH-058 C — Mercado Pago, webhook, conciliación externa y confirmación final

Fecha del análisis: 2026-10-25

Alcance: integración Mercado Pago detrás de un provider adapter, creación de
checkout, recepción y deduplicación de eventos, consulta oficial, conciliación
externa, pagos parciales/tardíos y confirmación atómica del Turno.

Este documento no modifica BH-058 A ni B y no propone implementar stock. Sólo
identifica el efecto lateral de stock que hoy ejecuta el webhook de
`OrdenCompra` para impedir que el flujo booking lo reutilice.

## 1. Conclusión ejecutiva

La integración actual sirve únicamente a `OrdenCompra`. Tiene una defensa
valiosa —consulta el Payment por SDK antes de actuar—, pero no constituye una
conciliación segura:

- no verifica autenticidad/firma del webhook;
- usa un `OrdenCompra.id` decimal como `external_reference`;
- no persiste ni deduplica eventos;
- no compara monto, moneda, preference ni contexto esperado;
- ejecuta la llamada HTTP de creación dentro de `transaction.atomic`;
- no usa una idempotency key persistente;
- un evento `rejected/cancelled` puede degradar una orden ya completada y un
  `approved` posterior puede volver a ejecutar sus efectos laterales;
- la return URL y sus páginas frontend están incompletas;
- no hay tests Mercado Pago.

El booking nuevo debe seguir esta separación:

```text
PaymentIntent interno
        │ 1:N
ProviderPaymentAttempt ── PaymentProvider/MercadoPagoAdapter
        │
ProviderEvent (inbox durable)
        │ consulta oficial server-to-server
        ▼
Pago interno reconciliado
        │
reconcile_external_payment_and_confirm_booking(...)
        │
PaymentIntent APPROVED + SlotHold CONSUMED + un Turno CONFIRMADO
```

Ni el payload, ni una query string, ni una return URL, ni un estado o monto
recibidos son autoridad. El adapter produce un snapshot oficial consultado con
credenciales server-to-server; el core vuelve a compararlo contra snapshots
internos y toma la decisión bajo locks.

El pago tardío conserva el dinero observado, pero no resucita un Intent/HOLD:
Attempt oficialmente aprobado, Pago `PENDING_RECONCILIATION` con causa
`LATE_PAYMENT`, caso operativo abierto, Intent `EXPIRED`, cero Turnos.

---

## 2. Inventario Mercado Pago actual

### 2.1 SDK e imports

| Pieza | Situación actual | Autoridad/persistencia/efectos | Evaluación |
|---|---|---|---|
| Paquete Python `mercadopago` | El entorno virtual local tiene SDK `3.2.0`. Se importa en `gestion/services.py` y directamente en `gestion/views.py`. | Efectúa HTTP de preferences y payments. | Reutilizable sólo dentro del adapter. No hay manifiesto Python de dependencias que fije la versión. |
| `MercadoPagoService` | Construye el SDK con access token y crea una preference para una `OrdenCompra`. | Escribe `OrdenCompra.preference_id`. | Acoplado a órdenes; no es una interfaz provider. |
| SDK directo en webhook | `WebhookMercadoPagoView` instancia nuevamente `mercadopago.SDK`. | Consulta `sdk.payment().get(payment_id)`. | Debe migrar al adapter; el core no debe importar el SDK. |

El SDK local acepta `request_options` en `preference().create(...)` y
`payment().get(...)`. Su `RequestOptions` admite headers personalizados,
timeout y retries; por defecto genera un header `x-idempotency-key` aleatorio al
construir headers. El código actual no entrega una clave persistida ni opciones
propias. La presencia de esa capacidad en el SDK no demuestra por sí sola la
semántica vigente de deduplicación del endpoint de preferences.

### 2.2 Settings, env y secrets

| Variable | Fuente actual | Uso |
|---|---|---|
| `MERCADO_PAGO_ACCESS_TOKEN` | `settings.py`, con alias legacy `MERCADOPAGO_ACCESS_TOKEN`; valor local en `.env`. | SDK de preference y Payment. |
| `MERCADO_PAGO_PUBLIC_KEY` | `settings.py`, con alias legacy `MERCADOPAGO_PUBLIC_KEY`; valor local en `.env`. | No se encontró ningún consumidor. |
| `MERCADO_PAGO_PUBLIC_BASE_URL` | Env opcional; default a un dominio ngrok concreto. | Base para notification/back URLs. |
| `MERCADO_PAGO_WEBHOOK_URL` | Env opcional; default derivado. | `notification_url` de preference. |
| `MERCADO_PAGO_BACK_SUCCESS_URL` | Env opcional; default a endpoint backend. | `back_urls.success`. |
| `MERCADO_PAGO_BACK_FAILURE_URL` | Ídem. | `back_urls.failure`. |
| `MERCADO_PAGO_BACK_PENDING_URL` | Ídem. | `back_urls.pending`. |
| Webhook secret | No existe en settings/env. | No hay verificación de firma. |
| Modo sandbox/production | No existe una variable explícita. | El código no distingue entornos. |

Hallazgos:

- `.env` está ignorado por git y no figura como trackeado. Contiene credenciales
  Mercado Pago con apariencia de test; este informe no reproduce valores.
- `.env.example` no documenta ninguna variable Mercado Pago.
- no se encontraron credenciales MP en frontend, fixtures, tests o archivos
  versionados;
- no hay secret manager ni validación de coherencia de entorno/URLs;
- el default ngrok es configuración pública hardcodeada, no una credencial,
  pero es inseguro para despliegue y puede apuntar a un túnel ajeno/vencido;
- `ALLOWED_HOSTS=['*']` no crea autenticidad para el webhook;
- la public key no se usa porque el checkout actual sólo redirige a
  `init_point`;
- `MercadoPagoService` declara fallbacks propios a localhost para back URLs,
  distintos de los defaults de `settings.py`; en la configuración estándar los
  atributos de settings existen y esos fallbacks internos no se usan.

Clasificación:

- **configuración técnica:** tokens, public key si llega a usarse, secret de
  webhook, provider environment, API base fija, notification URL y return URLs;
  debe vivir en env/settings/secret manager;
- **configuración de negocio:** modo DEPOSIT/FULL, montos, moneda, TTL y medios;
  pertenece a `PaymentPolicy` de B;
- los secrets no deben trasladarse a DB editable ni exponerse por serializer.

### 2.3 Creación actual de preference

`MercadoPagoService.crear_preferencia(orden_compra)` envía:

```text
items[0].title       = orden/código
items[0].quantity    = 1
items[0].currency_id = ARS
items[0].unit_price  = float(orden.total)
payer.email          = email del Cliente
notification_url     = settings
back_urls             = success/failure/pending
auto_return           = approved
external_reference    = str(OrdenCompra.id)
```

Después exige `response.id` e `init_point`, guarda `preference_id` y devuelve
la URL. No usa `sandbox_init_point`, no configura expiración externa y no
persiste request/response hash, status, moneda o clave idempotente.

Riesgos:

- conversión `Decimal -> float` para el importe;
- un único item sintético oculta el desglose, aunque el total interno de la
  orden sigue existiendo;
- `external_reference` es un PK enumerable y sin namespace;
- `preference_id` no tiene constraint unique;
- no valida que notification/back URLs sean HTTPS o pertenezcan a hosts
  permitidos;
- en error imprime la respuesta completa del provider a stdout;
- errores `ValueError` pueden devolverse textualmente al Cliente;
- no hay idempotencia persistida ni recuperación de preference huérfana.

### 2.4 Checkout y transacción actuales

`_crear_checkout_mercadopago_para_usuario`:

1. obtiene Cliente y carrito;
2. entra en `transaction.atomic`;
3. crea `OrdenCompra(ESPERANDO_PAGO)` e items;
4. llama Mercado Pago mientras la transacción sigue abierta;
5. guarda preference;
6. borra el carrito;
7. commit.

Lo llaman dos endpoints autenticados que duplican la misma respuesta:

- `POST /api/gestion/checkout/iniciar-pago/`;
- `POST /api/gestion/carrito/generar-pago-mercadopago/`.

No bloquea carrito/items ni acepta una idempotency key. Dos requests
concurrentes pueden crear más de una orden/preference. Si Mercado Pago crea la
preference y la respuesta se pierde o el commit falla, queda una preference
externa sin fila confirmada. El retry no puede recuperar por Attempt porque esa
entidad no existe.

### 2.5 Frontend checkout

`frontend/src/pages/cliente/Carrito.js`:

- valida que el carrito local no esté vacío;
- hace POST al endpoint absoluto `127.0.0.1`;
- toma `init_point` y usa `window.location.href`;
- muestra el error recibido;
- no envía monto ni marca la orden aprobada.

Esa redirección es reutilizable como patrón UX. La URL absoluta, el mensaje de
error potencialmente técnico y la ausencia de idempotency key no lo son.

`MisPedidos.js` consulta órdenes y muestra “Esperando confirmación de Mercado
Pago”, pero no hace polling específico ni refresh oficial.

### 2.6 Back URLs y callbacks

Las back URLs por defecto llegan a endpoints Django que redirigen de forma
hardcodeada a:

- `http://localhost:3000/compra-exitosa`;
- `http://localhost:3000/compra-fallida`;
- `http://localhost:3000/compra-pendiente`.

Existen además aliases legacy en URLs raíz. No existen rutas/componentes React
para esos paths. No se encontró código que procese `collection_id`,
`payment_id`, status o preference desde el callback. Por tanto, actualmente la
return UX es incompleta, pero tampoco confirma pagos desde frontend.

### 2.7 Webhook actual completo

Endpoint principal:

```text
POST /api/gestion/checkout/webhook/
```

Alias legacy:

```text
POST /api/checkout/webhook/
```

Comportamiento:

1. `AllowAny`;
2. extrae payment ID de `body.data.id`, query `data.id` o query `id`;
3. extrae tipo de `body.type`, `body.topic` o query `topic`;
4. si no es exactamente `payment`, responde 200 e ignora;
5. consulta `sdk.payment().get(payment_id)`;
6. usa de la respuesta `status`, `external_reference` y
   `transaction_amount`;
7. interpreta la referencia como `OrdenCompra.id`;
8. bloquea sólo esa orden;
9. aplica estado/efectos;
10. responde 200; ante excepción general, 500.

El proyecto usa autenticación DRF JWT y esta APIView reemplaza permisos por
`AllowAny`. Como endpoint API server-to-server no obtiene autenticidad de CSRF
y no usa cookies/sesión; en la práctica queda públicamente invocable sin firma.
Eso es normal para alcanzabilidad del provider, pero inseguro sin la capa de
autenticidad propia del webhook.

No inspecciona explícitamente el HTTP status del SDK. Una respuesta de error
sin `external_reference` termina como 200 “recibido”. Una orden inexistente
también devuelve 200, por lo que el provider no tiene incentivo para reintentar.

### 2.8 Autoridad y side effects actuales del webhook

| Estado oficial leído | Acción actual |
|---|---|
| `approved` | `Pago.get_or_create(transaccion_id=payment_id)`, método MP e importe oficial; luego completa la Orden. |
| `rejected` / `cancelled` | Cambia la Orden a `RECHAZADO`, incluso si estaba completada. |
| `pending` / `in_process` | Sólo cambia `PENDIENTE -> ESPERANDO_PAGO`; las órdenes MP nacen ya en `ESPERANDO_PAGO`. |
| cualquier otro | No hace nada y devuelve 200. |

La consulta oficial es la única pieza de autoridad externa razonable. No basta
porque el código no compara:

- monto oficial contra `OrdenCompra.total`;
- moneda;
- preference de la operación contra `OrdenCompra.preference_id`;
- referencia completa contra una entidad tipada;
- cuenta/provider esperado;
- estado previo permitido;
- evento ya procesado.

El `transaccion_id` unique deduplica parcialmente el Pago, y el lock de Orden
serializa webhooks de la misma orden. Sin embargo:

- no hay `ProviderEvent` ni auditoría semántica;
- no se comprueba que un Pago existente corresponda al mismo agregado;
- un `rejected` tardío puede cambiar `COMPLETADO -> RECHAZADO`;
- un `approved` posterior vuelve a entrar en la rama de completación;
- no se manejan reversión, refund o chargeback;
- la escritura usa directamente el ORM, no un reconciliador.

El único efecto lateral de inventario relevante para esta auditoría es que la
rama `approved` reduce `Producto.stock_real` por los items antes de marcar la
Orden `COMPLETADO`. Esa rama es exclusiva de órdenes y nunca debe invocarse para
booking. No se analiza aquí su corrección contable.

### 2.9 `OrdenCompra`, `Pago`, tests y signals

- `OrdenCompra.preference_id` es nullable, no unique y no identifica provider.
- `Pago.transaccion_id` es nullable/unique, pero `Pago` no tiene moneda, estado,
  actor, Attempt/Event ni obligación; B ya define su evolución.
- `PagoSerializer` ni siquiera expone `transaccion_id`; el webhook escribe ORM.
- `OrdenCompra` y `Pago` tienen simple-history, pero no están registrados en el
  signal semántico `Auditoria`; el webhook anónimo deja actor humano ausente.
- `HistorialAuditoriaViewSet` permite leer sus histories, pero impide revertir
  esos modelos. Eso es correcto para hechos financieros.
- no hay signals específicos de Mercado Pago, Orden o Pago.
- crear directamente un Turno `CONFIRMADO` no dispara la notificación legacy de
  “Turno Confirmado”, porque ese signal sólo la genera en updates, no al crear;
  el flujo nuevo requiere evento/notificación explícitos on-commit.
- no se encontraron tests backend o frontend de preference, webhook, callbacks,
  deduplicación o estados MP.

---

## 3. Piezas reutilizables y piezas acopladas

| Pieza | Reutilización segura |
|---|---|
| SDK 3.2.0 local | Sólo detrás de `MercadoPagoAdapter` y fijado en dependencias. |
| Consulta `payment().get(id)` | Sí, como implementación de `fetch_payment`; debe validar respuesta y normalizar Decimal. |
| Redirección a `init_point` | Sí, como UX del checkout propio. |
| `notification_url`/`back_urls` desde settings | Sí, eliminando defaults inseguros y validando entorno. |
| `Pago.transaccion_id` unique | Concepto reutilizable como unique `(provider, provider_payment_id)`, no campo global ambiguo. |
| Lock de agregado antes de mutar | Sí; se amplía al orden A/B. |
| `MercadoPagoService.crear_preferencia(OrdenCompra)` | No para booking: está acoplado a orden, monto, email, persistencia y referencia. |
| `_crear_checkout_mercadopago_para_usuario` | No: crea Orden, llama HTTP dentro de TX y vacía carrito. |
| `WebhookMercadoPagoView` y ramas de Orden | No para booking. Sólo puede quedar temporalmente como handler legacy aislado. |
| `external_reference=str(order.id)` | No para el flujo nuevo. |
| return URLs actuales | Sólo concepto UX; rutas/configuración actual no son reutilizables. |

---

## 4. Arquitectura provider

### 4.1 Dependencias

```text
booking/application services
        ↓ usa protocolo
PaymentProvider
        ↑ implementa
MercadoPagoAdapter
        ↓
SDK Mercado Pago
```

`SlotHold`, `PaymentIntent`, `Pago`, `Turno`, serializers de dominio y servicios
de agenda no importan `mercadopago`. La selección ocurre mediante un registry
server-side por `provider_code`; nunca se importa una clase cuyo nombre venga
del request.

### 4.2 Interfaz mínima

```python
class PaymentProvider(Protocol):
    code: str

    def create_payment_attempt(
        self,
        command: CreateProviderCheckout,
    ) -> ProviderCheckoutResult: ...

    def fetch_payment(
        self,
        provider_payment_id: str,
    ) -> ProviderPaymentSnapshot: ...

    def verify_webhook(
        self,
        *, raw_body: bytes, headers: Mapping[str, str], query: Mapping[str, str]
    ) -> VerifiedWebhookEnvelope: ...

    def normalize_status(self, raw_payment: Mapping) -> ProviderPaymentSnapshot: ...
```

Objetos devueltos inmutables:

- `ProviderCheckoutResult`: provider, preference/checkout ID, checkout URL,
  provider status, response hash y timestamp;
- `VerifiedWebhookEnvelope`: autenticidad, event ID si existe, event type,
  payment ID, safe hash y campos mínimos;
- `ProviderPaymentSnapshot`: payment ID, raw status, normalized status,
  `Decimal amount`, currency, external reference, checkout/preference ID,
  approved/updated timestamps, fetched_at y safe response hash.

`verify_webhook` autentica y parsea; `fetch_payment` obtiene la verdad externa.
Aunque el webhook sea auténtico, el payload no reemplaza el fetch.

### 4.3 Excepciones del adapter

- `ProviderRetryableError`: timeout, red, 429, 5xx, indisponibilidad;
- `ProviderConfigurationError`: credencial inválida, entorno incoherente;
- `ProviderRequestRejected`: preference inválida/4xx determinístico;
- `ProviderSecurityError`: firma/replay inválidos;
- `ProviderNotFound`: payment inexistente confirmado;
- `ProviderProtocolError`: respuesta incompleta o imposible.

La API traduce a códigos internos estables. Nunca devuelve token, payload o
mensaje crudo del provider al Cliente.

---

## 5. `ProviderPaymentAttempt`

### 5.1 Necesidad y cardinalidad

Sí hace falta. `PaymentIntent` es la obligación; un Attempt es una interacción
externa recuperable. Un Intent tiene 0..N Attempts históricos y un Attempt
pertenece a exactamente un Intent/provider.

Sólo debe existir un Attempt de checkout utilizable por Intent a la vez. Un
reemplazo se crea únicamente cuando el anterior está demostrado terminal o
expirado. “Cancelar” localmente una URL no prueba que el provider dejó de
aceptarla; sin cancelación externa verificada, se conserva como riesgo y todo
pago posterior entra por la regla tardía.

Una preference puede originar más de un Payment del provider. Por eso el
Attempt guarda el checkout/preference ID; los payment IDs viven en
`ProviderEvent` y `Pago`, no en una única columna sobreescribible.

### 5.2 Campos

| Campo | Semántica |
|---|---|
| `public_id` | UUID/ULID opaco para API. |
| `payment_intent` FK `PROTECT` | Obligación interna. |
| `provider_code` | Código estable, p. ej. `MERCADO_PAGO`. |
| `provider_checkout_id` | Preference ID, nullable hasta TX2. |
| `external_reference` | Referencia opaca única enviada al provider. |
| `status` | Estado operacional interno. |
| `last_provider_status` | Estado crudo más reciente consultado, no autoridad del core. |
| `reconciliation_status` | `NOT_EVALUATED`, `MATCHED`, `PARTIAL`, `LATE`, `MISMATCH`, `APPLIED` o `REVIEW_REQUIRED`. |
| `amount_expected` | Monto server-side esperado para este checkout. |
| `currency` | Moneda esperada. |
| `checkout_url` | URL retornable sólo al propietario; no loguearla. |
| `created_at`, `expires_at` | Ventana del checkout, nunca posterior al Intent/HOLD. |
| `provider_created_at` | Si el provider lo informa. |
| `last_verified_at` | Último fetch oficial exitoso. |
| `idempotency_key` | Clave persistida para llamada externa. |
| `request_hash` | Detecta reuse de key con payload diferente. |
| `safe_response_hash` | Diagnóstico sin payload completo. |
| `error_class`, `error_code` | Código seguro de fallo. |

### 5.3 Estados

```text
CREATED
  -> CREATING
  -> CHECKOUT_READY
  -> PAYMENT_PENDING
  -> PAYMENT_APPROVED
  -> CANCELLED | EXPIRED

CREATING -> CREATE_FAILED | OUTCOME_UNKNOWN
ANY_NON_TERMINAL -> RECONCILIATION_REQUIRED
```

`PAYMENT_APPROVED` significa que al menos un Payment asociado fue observado
como aprobado por consulta oficial; no significa que monto/moneda coincidieron,
que el Intent fue aprobado ni que existe Turno.

Los estados crudos se preservan por separado. Rechazar un Payment individual no
debe cerrar automáticamente el Intent si la preference aún permite otro pago.
La condición exacta para considerar terminal una preference es provider-specific.

### 5.4 Constraints e inmutabilidad

- unique `(provider_code, idempotency_key)`;
- unique `(provider_code, external_reference)`;
- unique `(provider_code, provider_checkout_id)` cuando no sea null;
- unique parcial de Attempt utilizable por Intent;
- `amount_expected > 0` y moneda igual al Intent;
- `expires_at <= intent.expires_at <= hold.expires_at` validado en servicio;
- provider, Intent, amount, currency, reference, request hash y key inmutables;
- checkout ID sólo puede pasar `null -> valor` y no cambiar;
- no delete ni CRUD genérico.

---

## 6. `external_reference`

Formato recomendado:

```text
bh:v1:booking:<attempt-public-uuid>:<random-token>
```

Propiedades:

- namespace y versión separan booking de órdenes;
- identifica el Attempt, que conduce al Intent/HOLD;
- token aleatorio criptográfico de al menos 128 bits;
- valor completo unique, persistido antes de llamar al provider;
- sin Cliente, Turno, email, monto ni dato sensible;
- no se acepta una referencia reconstruida desde parámetros del frontend.

El webhook no hace lookup por `PaymentIntent.id` directo. Busca coincidencia
exacta del `external_reference` oficial con el Attempt persistido y después
verifica Intent, checkout ID, amount y currency. El UUID facilita soporte; el
token impide que conocerlo baste para enumerar otros Attempts.

Para órdenes legacy:

```text
solo dígitos          -> handler OrdenCompra legacy explícito
bh:v1:booking:...     -> handler booking
otro namespace        -> unmatched/rejected + alerta
```

No usar fallback “si no encuentro booking, probar orden” para referencias
namespaced; ocultaría corrupción.

**REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**: longitud,
charset y preservación exacta de `external_reference` en preference, Payment y
notificaciones vigentes antes de fijar el formato final.

---

## 7. Creación de checkout en dos transacciones

### 7.1 TX1

En `transaction.atomic`:

1. autenticar ownership del Intent;
2. lock `SolicitudTecnicaReserva`;
3. lock `SlotHold`;
4. lock `PaymentIntent`;
5. usar reloj nuevo y normalizar expiraciones;
6. exigir HOLD `ACTIVE`, Intent `CREATED/PENDING`, ambos no vencidos;
7. resolver monto esperado desde snapshot/saldo interno, nunca del request;
8. buscar idempotency key existente;
9. devolver Attempt previo si key y request hash coinciden;
10. rechazar misma key con payload distinto;
11. generar referencia opaca y provider key;
12. crear Attempt `CREATED/CREATING`;
13. auditar `PROVIDER_PAYMENT_ATTEMPT_CREATED`;
14. commit.

### 7.2 Llamada externa fuera de TX

El `MercadoPagoAdapter` crea la preference con:

- líneas/monto server-side del Attempt;
- moneda snapshot;
- email sólo si es necesario y permitido;
- referencia persistida;
- notification/back URLs de configuración técnica allowlisted;
- expiración compatible si el producto la soporta;
- idempotency key persistida.

No se mantiene ningún lock DB durante red, retries o timeout.

### 7.3 TX2

1. lock Attempt;
2. comprobar que sigue siendo la misma operación y no fue resuelto por otro
   worker;
3. validar resultado/provider/ID/URL;
4. guardar checkout ID, URL, safe hash y status `CHECKOUT_READY`;
5. auditar `PROVIDER_CHECKOUT_CREATED`;
6. commit;
7. devolver URL al propietario.

La URL puede tratarse como dato sensible de corta vida: no log, no listado y no
exposición a terceros.

### 7.4 Fallos y recuperación

| Caso | Estado/recuperación |
|---|---|
| A. TX1 OK, MP falla con certeza sin crear | Attempt `CREATE_FAILED`; clasificar retryable/no retryable. Retry reutiliza misma fila/key. |
| A'. Timeout/resultado incierto | `OUTCOME_UNKNOWN`; no crear otro Attempt. Reintentar misma operación/key o reconciliar por referencia. |
| B. MP crea y se pierde respuesta | Misma key persistida; retry idempotente si API lo garantiza. Sin garantía, buscar por referencia si existe API oficial o abrir conciliación manual. |
| C. MP OK, TX2 falla | La fila TX1 permite reintentar con misma key; guardar resultado en TX2 posterior. No asumir que no se creó. |
| D. Retry del Cliente | Misma endpoint key devuelve URL si ready, 202 si creating/unknown o el error estable; nunca nueva obligación. |
| Respuesta HTTP al Cliente se pierde tras TX2 | El siguiente retry encuentra el mismo Attempt y URL. |

Un worker/outbox puede retomar Attempts `CREATING/OUTCOME_UNKNOWN`; no es
necesario implementarlo en este análisis, pero el modelo no debe depender de
que el proceso web sobreviva.

---

## 8. Idempotencia externa

El SDK local genera una key aleatoria por defecto y permite custom headers, pero
el código actual no persiste ni reutiliza una clave. BH-058 C necesita dos
niveles:

1. **API interna:** `Idempotency-Key` del comando, unique con actor/Intent y
   request hash;
2. **provider:** key derivada/persistida por Attempt, estable en todos los
   retries HTTP de esa creación.

Nunca derivar la key sólo de `PaymentIntent.id` si se permiten Attempts
secuenciales: usar `provider:attempt-public-id:version` o UUID aleatorio
persistido.

**REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**: si el
endpoint vigente de creación de Checkout Pro preferences garantiza
idempotencia, header exacto, alcance, ventana temporal y respuesta ante misma
key con payload igual/diferente. Hasta verificarlo, `OUTCOME_UNKNOWN` no puede
resolverse creando otra preference a ciegas.

También debe verificarse si existe búsqueda fiable de preference/payment por
`external_reference`; no se la asume en el diseño base.

---

## 9. Frontend checkout y return URL

El frontend futuro puede:

- `POST` para iniciar checkout propio con una idempotency key;
- recibir Attempt público, `checkout_url`, expiry y estado informativo;
- redirigir;
- consultar `GET status` por ownership;
- mostrar “pendiente”, “confirmado”, “vencido” o “requiere revisión”.

Nunca envía como autoridad:

- amount/currency;
- Cliente, Personal, Servicios o slot;
- estado provider/interno;
- `approved=true`;
- Turno a confirmar.

La página de retorno es UX. Ignora status, amount y IDs de pago de su query para
decisiones; consulta el estado interno. Puede ofrecer “Actualizar estado”, que
encola un refresh server-side rate-limited e idempotente. Si el webhook llegó
primero, simplemente muestra el Turno. Si no llegó, muestra procesamiento.

Las back URLs deberían apuntar a rutas frontend realmente existentes o a un
redirect backend configurable. No deben usar `localhost` en producción ni
mezclarse con la notification URL.

---

## 10. `ProviderEvent`: inbox durable

### 10.1 Campos

| Campo | Propósito |
|---|---|
| `provider_code` | Origen. |
| `external_event_id` | ID del evento si el provider garantiza estabilidad. |
| `dedup_fingerprint` | Hash/HMAC canónico fallback. |
| `event_type` | Tipo normalizado; conservar raw type seguro. |
| `external_payment_id` | Payment ID extraído. |
| `attempt` nullable | Se resuelve tras fetch/reference. |
| `received_at` | Primera recepción. |
| `last_received_at`, `duplicate_count` | Replays sin filas semánticas nuevas. |
| `processed_at` | Finalización. |
| `status` | Estado del inbox. |
| `attempt_count`, `next_retry_at` | Recuperación interna. |
| `signature_result` | `VALID`, `INVALID`, `NOT_SUPPORTED`, nunca el secret. |
| `safe_payload_hash` | Hash del raw body. |
| `official_response_hash` | Hash del snapshot consultado. |
| `error_class`, `error_code` | Diagnóstico seguro. |

Estados:

```text
RECEIVED -> AUTHENTICATED -> FETCHED -> PROCESSED
         -> IGNORED
         -> RETRYABLE_ERROR
         -> NON_RETRYABLE_ERROR
         -> SECURITY_REJECTED
         -> RECONCILIATION_REQUIRED
```

No guardar el payload completo por defecto. Si soporte exige retención, usar
campos allowlisted o blob cifrado con TTL y acceso restringido.

### 10.2 Deduplicación

- unique `(provider_code, external_event_id)` cuando sea estable;
- si no lo hay, unique `(provider_code, dedup_fingerprint)`;
- el fingerprint usa sólo campos canónicos estables y el hash del body, no IP
  ni timestamp local;
- entregas duplicadas incrementan contadores sobre el mismo inbox;
- eventos distintos para el mismo Payment sí pueden coexistir;
- unique `(provider_code, provider_payment_id)` en Pago garantiza un solo hecho
  financiero.

**REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**: campo de ID
estable por entrega, semántica de `type`/`action`/`data.id` y qué partes cambian
entre retries. Hasta verificarlo, no usar sólo payment ID como event ID porque
impediría registrar transiciones diferentes del mismo Payment.

---

## 11. Webhook seguro

### 11.1 Ingreso HTTP

1. endpoint provider-specific y `AllowAny` sólo a nivel de usuario;
2. límite pequeño de body, content type y campos;
3. conservar `raw_body` exacto;
4. verificar autenticidad con adapter antes de confiar en IDs;
5. rechazar firma inválida y medir replay;
6. extraer event/payment ID mínimo;
7. insertar/deduplicar `ProviderEvent` en una transacción breve;
8. procesar síncrono o en worker durable;
9. devolver respuesta según durabilidad, no según resultado financiero.

Una firma inválida no entra a conciliación. Puede registrarse como
`SECURITY_REJECTED` con hash/fingerprint mínimo y retención acotada si el control
de volumen lo permite; si no, queda sólo en métrica/log de seguridad para que un
ataque no fuerce crecimiento ilimitado de la tabla.

CSRF no autentica un webhook. El endpoint server-to-server puede estar exento
de sesión/CSRF, pero requiere firma y consulta oficial. CORS tampoco lo protege.

### 11.2 Procesamiento

1. claim idempotente del Event;
2. `fetch_payment(payment_id)` fuera de transacción larga;
3. exigir respuesta HTTP/API válida;
4. verificar que ID consultado coincide;
5. leer `external_reference` oficial;
6. resolver exactamente Attempt/contexto;
7. comparar provider, checkout/preference ID cuando esté disponible, amount,
   currency y referencia;
8. invocar reconciliador interno;
9. marcar Event `PROCESSED` sólo on-commit;
10. clasificar fallos y programar retry/caso manual.

### 11.3 HTTP codes

- autenticidad inválida: 401/403 según contrato del provider;
- payload sintácticamente inválido: 400;
- evento soportado y duramente persistido: 200/204, aunque quede pendiente de
  worker;
- duplicado ya persistido: 200/204;
- fallo antes de persistir o sin mecanismo interno de retry: 5xx;
- fallo transitorio después de persistir: 200 sólo si existe retry durable; de
  lo contrario 5xx para obtener redelivery.

Nunca devolver 200 silencioso para una referencia booking válida pero
inprocesable sin Event/caso persistido.

**REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**: algoritmo y
canonicalización de firma, headers vigentes, tolerancia temporal/replay,
respuesta esperada, política de retries y diferencias entre Webhooks/IPN o
productos. El repositorio no contiene esa documentación ni webhook secret.

---

## 12. Estados externos

Los únicos estados de Payment observados en código son:

| Raw actual | Normalización propuesta | Acción interna |
|---|---|---|
| `approved` | `APPROVED` | Candidato a conciliación; jamás aprobación directa. |
| `pending` | `PENDING` | Attempt pendiente; no Pago reconciliado ni Turno. |
| `in_process` | `PENDING` | Ídem, conservando raw. |
| `rejected` | `REJECTED` | Resultado de ese Payment; no cerrar Intent automáticamente. |
| `cancelled` | `CANCELLED` | Resultado externo; no confundir con cancelación interna. |
| desconocido | `UNKNOWN` | Preservar raw y abrir retry/reconciliación; no mutar dominio. |

`type/topic` soportado hoy: sólo `payment`. Otros se ignoran.

Refunds y chargebacks no se manejan. El SDK instalado expone recursos para
refund/chargeback, pero eso no prueba estados/eventos vigentes. Si aparecen,
deben ir al futuro flujo compensatorio de B; nunca borrar Pago o cancelar
automáticamente un Turno.

**REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**: catálogo y
transiciones vigentes de status/status_detail, eventos de refund/chargeback,
posibilidad de `rejected -> approved`, estados terminales y timestamps
autoritativos. No extender la tabla desde memoria.

---

## 13. Monto y moneda

La autoridad esperada es interna:

```text
PaymentIntent snapshot
    -> confirmation_due/balance permitido
    -> ProviderPaymentAttempt.amount_expected + currency
```

La autoridad observada es la consulta oficial:

```text
ProviderPaymentSnapshot.amount + currency
```

Comparación exacta tras convertir strings a `Decimal` y cuantizar según moneda.
No usar `float` ni tolerancia porcentual.

| Caso | Resultado automático |
|---|---|
| amount == Attempt.expected y currency == expected | Puede reconciliar. |
| amount menor al Attempt.expected | `AMOUNT_MISMATCH`; Pago pendiente/caso; no aprobar. |
| amount mayor al Attempt.expected | `AMOUNT_MISMATCH/OVERPAYMENT`; Pago pendiente/caso; no aprobar. |
| currency distinta | `CURRENCY_MISMATCH`; no aplicar ni aprobar. |
| referencia/preference distinta | `REFERENCE_MISMATCH`; security/reconciliation case. |

Un pago menor que el `required_amount` puede ser un parcial legítimo sólo si el
backend creó ese Attempt con `amount_expected` igual a ese parcial. Ejemplo:

```text
required_amount = 30
Attempt.amount_expected = 10 (permitido por política interna)
provider.amount = 10
```

Se crea Pago reconciliado por 10; Intent sigue `PENDING`, confirmation_due=20 y
el HOLD sólo continúa mientras su reloj siga vigente. Si el Attempt esperaba 30
y el provider informa 10, no se redefine retroactivamente como parcial.

La capacidad exacta de Mercado Pago para pagos parciales de una misma
preference no se presupone; el diseño puede crear Attempts secuenciales por el
saldo permitido.

---

## 14. Pago reconciliado desde provider

No usar `PagoSerializer`. El servicio interno recibe un
`ProviderPaymentSnapshot` inmutable producido por el adapter.

Flujo idempotente:

1. lock ordenado de Intent/Attempt/Pagos;
2. buscar Pago unique por `(provider_code, provider_payment_id)`;
3. si existe, verificar que sus datos/contexto coinciden y devolverlo;
4. si datos difieren, `SECURITY/INTEGRITY_CONFLICT`, nunca actualizarlo;
5. si amount/currency/reference/checkouts coinciden y está en tiempo, crear
   Pago `RECONCILED`, método/provider MP, monto/moneda oficiales, actor sistema;
6. guardar approved/fetched timestamp, Attempt y Event;
7. recalcular suma reconciliada;
8. continuar al orquestador de booking.

Para mismatch o tardío se crea/reutiliza Pago `PENDING_RECONCILIATION`, con
importe oficial y reason explícita. Así el dinero observado no desaparece, pero
no cuenta para el umbral hasta una resolución permitida.

Un Payment sin referencia resoluble no permite Pago huérfano porque B exige una
obligación. Se conserva Event `RECONCILIATION_REQUIRED` con payment ID y hash,
se alerta y una operación administrativa debe asociarlo tras consulta oficial.

---

## 15. Orquestador final

Nombre conceptual:

```text
reconcile_external_payment_and_confirm_booking(
    provider_event_id,
    verified_payment_snapshot,
    operation_key,
)
```

No recibe Cliente, slot, Personal, Servicios, precio, estado de Turno ni amount
desde frontend.

### 15.1 Orden exacto de locks

Extiende A+B sin cambiar su precedencia:

1. `SolicitudTecnicaReserva`;
2. `SlotHold`;
3. `PaymentIntent`;
4. Cliente;
5. `ProviderPaymentAttempt` en orden de PK;
6. `ProviderEvent` reclamado y Pagos afectados en orden de PK;
7. Servicios snapshot en orden de PK;
8. Personal;
9. `TipoEquipamiento` en orden de PK;
10. unidades sólo si el servicio canónico las necesita;
11. Turno ya enlazado, si es retry.

Todos los servicios financieros, expirador y cancelador deben respetar esa
secuencia. El Event puede reclamarse antes en una transacción breve, pero la
mutación semántica se vuelve a bloquear en el punto 6.

### 15.2 Operación atómica

Con el fetch HTTP ya terminado, dentro de una única transacción DB:

1. adquirir locks en orden;
2. si Hold ya `CONSUMED` por esta operación, devolver mismo Pago/Turno;
3. revalidar solicitud `APROBADA_TECNICAMENTE` y evaluación vigente;
4. usar un reloj nuevo después de esperar locks;
5. verificar Attempt/Event/reference/provider/snapshot;
6. crear o recuperar un Pago candidato idempotentemente;
7. calcular pagos reconciliados elegibles incluyendo el candidato sólo después
   de validar tiempo/match;
8. si no alcanzan required, marcar el candidato `RECONCILED`, mantener Intent
   `PENDING`, Event procesado y salir;
9. si alcanzan y Intent/HOLD siguen vigentes, abrir savepoint de confirmación y
   pasar candidato a `RECONCILED` e `Intent -> APPROVED`;
10. bloquear/revalidar snapshots y agenda con `exclude_hold_id=propio`;
11. crear Turno `CONFIRMADO` desde el HOLD mediante servicio canónico interno;
12. actualizar condicionalmente HOLD a `CONSUMED`, enlazando Turno y operation
    key, sólo si `ACTIVE AND expires_at > database_now`;
13. si el update condicional no afecta fila, revertir el savepoint del Turno y
    de la aprobación, materializar expiry y dejar el Pago candidato pendiente
    con caso tardío;
14. asociar Pago/Intent al Turno;
15. persistir auditoría/outbox semántico;
16. marcar Event procesado y commit.

El Turno y su vínculo al HOLD requieren unicidad estructural: un HOLD tiene como
máximo un `consumed_turno`, y el Turno de este flujo tiene un solo HOLD de
origen. La operation key permite devolver exactamente el mismo resultado.

### 15.3 Fallo operacional después de recibir dinero

Usar una transacción externa, un savepoint `FINANCIAL_CONFIRMATION` que incluye
la promoción del Pago/Intent y un savepoint interno `BOOKING` para Turno/HOLD:

- fallo transitorio de DB/proceso: rollback total; el Event durable queda
  retryable y el Payment oficial puede recrear idempotentemente el Pago;
- el reloj cruza expiry durante el consumo: rollback del savepoint restaura
  Intent/Pago antes de aprobación, luego se persisten Intent/HOLD expirados,
  Pago `PENDING_RECONCILIATION` y caso `LATE_PAYMENT`;
- inviabilidad de dominio definitiva al revalidar agenda: rollback de
  `BOOKING`, pero commit de `FINANCIAL_CONFIRMATION`; conservar Pago
  reconciliado, Intent `APPROVED` si fue pagado en tiempo, liberar/inutilizar
  HOLD con causa y abrir
  `BOOKING_CONFIRMATION_FAILED`; no refund automático;
- no marcar Event `PROCESSED` hasta que uno de esos resultados persistentes haya
  quedado confirmado.

---

## 16. Confirmación parcial, exacta y múltiple

### Parcial

Si el Attempt esperaba 10, provider confirma 10 y required es 30:

- Pago `RECONCILED=10`;
- Intent `PENDING`;
- Attempt `PAYMENT_APPROVED`;
- no Turno;
- HOLD permanece sólo hasta su deadline;
- status API devuelve `paid=10`, `confirmation_due=20`, expiry y posibilidad de
  crear otro Attempt si política/provider lo permiten.

### Exacto

Cuando la suma elegible alcanza exactamente required:

- Intent `APPROVED`;
- si HOLD sigue válido, se consume y crea Turno en la misma transacción;
- retries devuelven los mismos objetos.

### Múltiples pagos

Cada Payment ID produce como máximo un Pago. La suma 10+20 puede alcanzar 30.
Los Attempts pueden ser secuenciales; no se mantienen dos URLs pagables a la
vez sin garantía de cancelación externa. Un pago posterior al umbral se limita
por balance/política y nunca crea otro Turno.

---

## 17. Pago tardío y semántica del Intent

Se elige la opción **B: no marcar `PaymentIntent.APPROVED` si el pago llegó
después de la vigencia**.

Esto es consistente con B porque `APPROVED` es terminal, sólo se alcanza desde
un Intent vigente y un Intent vencido no se resucita. La condición matemática
“hay dinero suficiente” puede ser cierta después, pero la obligación temporal
de confirmar agenda no fue satisfecha en plazo.

Estado exacto:

| Entidad | Resultado tardío |
|---|---|
| Attempt | `PAYMENT_APPROVED`, `last_provider_status=approved`, `reconciliation_status=LATE`. |
| Pago | Creado/reusado como `PENDING_RECONCILIATION`, método MP, monto/moneda oficiales, reason `LATE_PAYMENT`. |
| PaymentIntent | `EXPIRED` (o conserva otro terminal previo); nunca `APPROVED`. |
| SlotHold | `EXPIRED/RELEASED`; nunca vuelve a `ACTIVE`. |
| Turno | No se crea. |
| Caso | `PaymentReconciliationCase(OPEN, LATE_PAYMENT)`. |
| Auditoría | `PAYMENT_LATE_APPROVAL` una sola vez. |

El caso permite resolución futura `REFUND_REQUIRED`, `CREDIT_APPROVED` u otra
decisión manual autorizada. Ninguna se automatiza en C. Si luego el Pago se
marca reconciliado para ledger, permanece explícitamente `NOT_APPLIED_TO_BOOKING`.

`PaymentReconciliationCase` mínimo contiene Intent/Attempt/Pago/Event, reason,
`OPEN | IN_REVIEW | RESOLVED`, resolución, actor/timestamps y auditoría. No
permite editar importes ni posee CRUD genérico. También se abre si el HOLD vence
con pagos parciales ya reconciliados: ese dinero permanece registrado, pero no
origina reserva.

Esta separación distingue:

- **dinero observado/aprobado por provider**: Attempt;
- **hecho aceptado en ledger o pendiente de resolución**: Pago;
- **obligación cumplida en plazo**: PaymentIntent;
- **agenda confirmada**: Hold consumido + Turno.

---

## 18. Concurrencia

### 18.1 Webhook vs expiración

Ambos siguen solicitud → HOLD → Intent:

- webhook gana: comprueba tiempo con reloj nuevo, reconcilia, aprueba, consume y
  crea un Turno;
- expirador gana: materializa HOLD/Intent vencidos; webhook despierta, crea Pago
  tardío/caso y no crea Turno.

No hay ventana en la que el Pago se pierda o el HOLD resucite.

### 18.2 Dos webhooks del mismo Payment

Defensas acumuladas:

- unique del Event/fingerprint;
- claim de Event;
- unique Pago `(provider, payment_id)`;
- lock Intent/HOLD;
- transición condicional de HOLD;
- unique del Turno/HOLD;
- operation key en auditoría/outbox.

Resultado: un Event efectivo por entrega duplicada, un Pago, una aprobación,
un consumo, un Turno y un evento semántico.

### 18.3 Return URL vs webhook

La return URL nunca entra al orquestador. Sólo consulta estado. Si intenta un
refresh oficial, éste crea/usa una operación idempotente y sigue exactamente el
mismo reconciliador. Dos refresh/webhook compiten bajo los mismos uniques/locks.

### 18.4 Webhook vs cancelación

- cancelador gana antes de dinero: Intent/HOLD terminales; pago posterior es
  tardío;
- webhook gana y consume: la cancelación del checkout ya no puede cancelar el
  Intent; una cancelación de Turno es otro caso de negocio;
- no se cancela por volver mediante `failure` ni cerrar navegador.

---

## 19. Eventos fuera de orden

Cada Event dispara una consulta oficial actual; no se aplica el orden de llegada
como máquina de estados.

| Secuencia recibida | Regla |
|---|---|
| `pending -> approved` | El segundo fetch aprobado puede reconciliar. |
| `approved -> pending` tardío | El fetch actual y estado interno impiden degradar Pago/Intent/Turno. |
| `rejected -> approved` | Sólo se procesa si el fetch oficial actual lo confirma y la transición está permitida; HOLD debe seguir vigente. |
| dos tipos diferentes mismo Payment | Dos Events, un Pago. |
| refund/chargeback posterior | Caso compensatorio futuro; no borrar ni reabrir automáticamente. |

Una vez `PaymentIntent.APPROVED`, no vuelve a PENDING. Una vez Hold consumido,
no se libera por un evento financiero tardío. Una reversión financiera tiene su
propio hecho y workflow, no una reescritura histórica.

La tabla exacta de transiciones permitidas del provider queda condicionada a la
verificación documental indicada en la sección 12.

---

## 20. Creación del Turno

El `TurnoCreationService.create` actual no puede invocarse sin adaptación:

- recibe IDs/fecha/hora externos;
- crea un único Servicio;
- fija `SOLICITADO`;
- no conoce HOLD ni `exclude_hold_id`;
- adquiere locks desde Cliente, incompatible si se llama como caja negra tras
  locks financieros.

Debe extraerse/reutilizarse una primitiva canónica interna como:

```text
create_confirmed_turno_from_locked_hold(
    hold,
    exclude_hold_id=hold.id,
    source=WEB,
)
```

Esa primitiva:

- asume locks adquiridos por el orquestador;
- usa Cliente, Personal, fecha/hora, Servicios, orden, duración, precios y
  requisitos desde HOLD/Intent snapshots;
- revalida solicitud/evaluación/agenda;
- soporta múltiples Servicios;
- excluye el propio HOLD de disponibilidad;
- no acepta estado ni datos del frontend;
- crea detalles históricos desde snapshots;
- enlaza Intent/Pagos/HOLD sin escribir campos financieros legacy como
  autoridad.

### Estado inicial

El estado correcto es `Turno.Estado.CONFIRMADO`:

- el modelo lo etiqueta “Confirmado (Seña OK)”;
- es bloqueante y habilita llegada en backend/frontend;
- la obligación de confirmación ya fue satisfecha;
- `SOLICITADO`, `ESPERANDO_SENA`, `PENDIENTE` y `SUGERIDO` reabrirían etapas ya
  superadas.

DEPOSIT y FULL comparten estado. El saldo se consulta desde Intent/Pagos, no
desde el estado del Turno. Debe emitirse notificación explícita on-commit porque
el signal actual no notifica un `CONFIRMADO` creado directamente.

---

## 21. Seña, total y saldo posterior

### DEPOSIT

- required deriva de la política snapshot;
- al alcanzarlo en tiempo, Intent `APPROVED` y Turno `CONFIRMADO`;
- `balance = total_snapshot - paid_reconciled` puede ser mayor que cero.

### FULL

- `required_amount == total_amount_snapshot`;
- al confirmar, balance es cero.

Después de crear el Turno, Intent y Pagos permanecen. Pagos manuales o externos
posteriores de balance:

- se asocian al mismo Intent y Turno;
- respetan balance y moneda;
- no reabren Intent;
- no consumen otro HOLD ni crean otro Turno;
- reutilizan el servicio de Pago de B; si son provider, crean otro Attempt
  identificado como `BALANCE`.

La UI consulta paid/confirmation due/balance desde backend. No materializa saldo
como autoridad en `Turno`.

---

## 22. Cancelación

### Antes del pago

Una cancelación explícita y autorizada:

1. lock solicitud/HOLD/Intent/Attempt;
2. verificar que no hay Payment aprobado oficial ya observado;
3. cancelar Intent y liberar HOLD según B;
4. Attempt queda `CANCELLED` internamente;
5. intentar invalidar checkout externo sólo si el producto ofrece operación
   oficial verificada;
6. cualquier pago posterior se trata como tardío.

Cerrar navegador o volver por `failure` no cancela nada. El TTL gobierna.

**REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**: posibilidad
y garantías de expirar/cancelar una preference ya creada. Sin garantía, la UI
debe advertir que el link no debe usarse y mantener la ruta de pago tardío.

### Después del pago

Si el dinero fue reconciliado pero la creación de Turno falla:

- nunca borrar Pago;
- error transitorio: Event retryable y operación idempotente;
- error de dominio definitivo: Pago/Intent financiero preservados, no Turno,
  caso `BOOKING_CONFIRMATION_FAILED`, HOLD liberado/inutilizado;
- no devolución automática;
- métrica/alerta “Intent aprobado sin Turno con caso abierto”.

---

## 23. Errores externos

| Error | Clase | Tratamiento |
|---|---|---|
| timeout/conexión/reset | `RETRYABLE` u `OUTCOME_UNKNOWN` en create | Backoff; misma key; no nuevo Attempt ciego. |
| HTTP 5xx/provider unavailable | `RETRYABLE` | Retry acotado + circuit breaker/alerta. |
| 429/rate limit | `RETRYABLE` | Respetar retry-after si está documentado; jitter. |
| 401/403 credenciales | `NON_RETRYABLE_CONFIGURATION` | Detener retries agresivos, alerta operativa; mensaje genérico al Cliente. |
| preference inválida/4xx validación | `NON_RETRYABLE` | Attempt failed con código seguro; corregir configuración/payload. |
| payment inexistente | `RETRYABLE` sólo si eventualidad documentada; si no, `NON_RETRYABLE/RECONCILIATION_REQUIRED` | No asumir aprobado. |
| respuesta incompleta/protocolo | `RETRYABLE` limitado, luego caso manual | Conservar hashes. |
| firma inválida/replay | `SECURITY_REJECTED` | No fetch/mutación; métrica, log seguro y throttle. |
| reference/amount/currency mismatch | `RECONCILIATION_REQUIRED` | Pago pendiente o Event unmatched; nunca Turno. |

Los errores públicos usan códigos como `PROVIDER_TEMPORARILY_UNAVAILABLE`,
`CHECKOUT_CONFIGURATION_ERROR` o `PAYMENT_PROCESSING`. Detalles del SDK quedan
en logs sanitizados con correlation ID.

---

## 24. Reconciliación manual

Operación administrativa semántica, no edición:

```text
POST /api/gestion/provider-payment-attempts/{public_id}/reconcile/
```

Entrada permitida:

- provider payment ID si aún no se conoce;
- operation/idempotency key;
- reason code y nota interna limitada.

No acepta amount, currency, status ni target Intent como autoridad. El backend:

1. verifica permiso efectivo;
2. bloquea Attempt/Intent;
3. consulta provider server-to-server;
4. aplica las mismas comparaciones;
5. invoca el mismo orquestador;
6. audita actor y resultado.

Se recomienda permiso nuevo `gestion.reconcile_external_payment`, más estrecho
que `confirm_deposit`. Este último conserva la semántica B de conciliar
evidencia manual; conocer/consultar IDs de provider es una capacidad distinta.
`view_financial_reports` no concede mutación.

Casos cubiertos:

- webhook nunca llegó;
- Event quedó retryable;
- TX2 incompleta;
- payment oficial conocido;
- tardío/mismatch;
- recuperación tras indisponibilidad.

No hay CRUD genérico de Attempt, Event o Pago y no se permite cambiar status en
admin Django.

---

## 25. Matriz de permisos

La autoridad es ownership o permiso efectivo; nunca `is_staff`, BusinessRole o
`Personal.rol`.

| Operación | Cliente | Empleado | Profesional | Administrador | Sistema/webhook |
|---|---|---|---|---|---|
| Iniciar checkout | Sólo Intent propio, vigente | Sólo propio; por tercero requeriría permiso explícito no incluido | Igual | Sólo propio o permiso delegado explícito | No |
| Ver status | Sólo propio | Con alcance operativo o `view_financial_reports` | Igual por permisos | Por permisos efectivos | Sí |
| Cancelar checkout/Intent | Propio, estado permitido | Sólo con permiso de cancelación financiera específico | Igual | Por permiso, no rol | Expirador puede hacerlo |
| Reconciliar provider manualmente | No | `reconcile_external_payment` | Sólo si posee el permiso | Sólo si posee el permiso | Sí, adapter autenticado |
| Ver Events/Attempts técnicos | No | No por defecto | No por defecto | Permiso de soporte financiero/auditoría explícito | Sí |
| Ver reportes financieros | Propios | `view_financial_reports` | Ídem | Ídem | Jobs internos |
| Configurar PaymentPolicy | No | No por defecto | No por defecto | `manage_payment_configuration` | Migración controlada |
| Configurar secrets/provider | No UI | No | No | No por UI; acceso infra separado | Despliegue/secret manager |

La identidad sistema debe ser explícita en auditoría (`SYSTEM:MERCADO_PAGO_WEBHOOK`
o service principal), no “usuario anónimo” como única trazabilidad.

---

## 26. Endpoints mínimos

```text
POST /api/gestion/payment-intents/{public_id}/checkout/
GET  /api/gestion/payment-intents/{public_id}/status/
POST /api/gestion/payment-intents/{public_id}/cancel/

POST /api/gestion/payments/providers/mercadopago/webhook/

POST /api/gestion/provider-payment-attempts/{public_id}/reconcile/
```

Contratos:

- IDs públicos opacos;
- POST de checkout/cancel/reconcile con `Idempotency-Key`;
- status filtra por ownership/permisos y no expone raw payload, secret ni PII;
- webhook provider-specific, sin serializer de dominio;
- reconcile es command, no update;
- no `ModelViewSet` CRUD para Attempt/Event/Pago.

Durante migración se conservan los endpoints legacy de OrdenCompra, claramente
separados y observados.

---

## 27. Seguridad

### Autenticidad y replay

- verificar firma sobre raw body/query según contrato vigente;
- validar timestamp/nonce si existe;
- event ID/fingerprint unique;
- fetch oficial siempre;
- no mutar por body/query solamente;
- rotación de secret planificada sin aceptar “sin firma” silenciosamente.

### IDs, ownership y redirecciones

- public IDs opacos y object-level ownership;
- referencia externa no contiene PK sensible;
- no aceptar provider code/API URL/callback URL desde request;
- API base y hosts de checkout allowlisted en adapter;
- no seguir URLs arbitrarias del payload: evita SSRF/open redirect;
- status no permite enumerar Attempts ajenos.

### Secrets, logs y PII

- access token y webhook secret sólo en secret manager/env;
- nunca frontend/DB editable;
- no imprimir responses completas;
- logs con Event/Attempt public ID, hash, code y correlation ID;
- email/amount sólo cuando sea necesario y con política de acceso;
- checkout URL, comprobantes y payloads no se loguean;
- error del SDK no se devuelve crudo.

### Superficie HTTP

- límite de body y longitud/formato de IDs;
- timeout/retries acotados;
- throttle específico en app/reverse proxy; hoy no hay DRF throttling global;
- HTTPS obligatorio en producción;
- CORS no habilita webhook y CSRF no sustituye firma;
- respuesta constante sin revelar si un Intent concreto existe.

---

## 28. Logging y auditoría

Eventos semánticos:

```text
PROVIDER_PAYMENT_ATTEMPT_CREATED
PROVIDER_CHECKOUT_CREATED
PROVIDER_EVENT_RECEIVED
PROVIDER_EVENT_VERIFIED
PROVIDER_EVENT_REJECTED
EXTERNAL_PAYMENT_RECONCILED
PAYMENT_LATE_APPROVAL
BOOKING_CONFIRMED_FROM_PAYMENT
PAYMENT_RECONCILIATION_REQUIRED
```

Registrar:

- actor/service principal;
- provider code;
- Attempt/Event/Intent/HOLD/Pago/Turno public IDs;
- provider IDs truncados o hasheados según sensibilidad;
- amount/currency internos y resultado de comparación;
- estado anterior/nuevo;
- operation key/correlation ID;
- error class/code, no stack al Cliente;
- timestamps provider/fetch/DB.

No registrar:

- access token, webhook secret o firma completa;
- raw payload/response completa;
- checkout URL;
- email completo sin necesidad;
- datos de tarjeta o financieros sensibles.

Auditoría y outbox se escriben en la misma transacción del resultado. La
notificación al Cliente se envía on-commit y es idempotente.

---

## 29. Observabilidad

Métricas mínimas por provider/environment:

- webhooks recibidos, autenticados, inválidos y duplicados;
- latencia ingreso → fetch → procesamiento;
- fetch 2xx/4xx/5xx/timeout/429;
- Events retryable/no retryable/security rejected;
- Attempts `CREATING/OUTCOME_UNKNOWN/PENDING` antiguos;
- preferences creadas y retries por idempotency key;
- mismatch amount/currency/reference;
- pagos reconciliados, parciales y tardíos;
- Intents aprobados;
- Holds consumidos;
- Turnos confirmados desde pago;
- reconciliaciones manuales por actor/resultado;
- casos abiertos y antigüedad.

Alertas/estados imposibles:

- HOLD `CONSUMED` sin `consumed_turno`;
- más de un Turno por HOLD;
- Turno booking sin HOLD consumido;
- Pago provider reconciliado sin Attempt/Event oficial;
- Pago provider duplicado;
- Event `PROCESSED` sin `last_verified_at`;
- Attempt `CHECKOUT_READY` sin checkout ID;
- Intent `APPROVED` sin Turno y sin caso abierto más allá de una ventana corta;
- late payment sin caso;
- mismatches repetidos o firmas inválidas en ráfaga;
- credenciales/configuración fallando.

El repo no tiene infraestructura de métricas/Sentry/OpenTelemetry; se propone el
contrato, no una herramienta concreta.

---

## 30. Matriz de tests

### Adapter y checkout

- construye preference desde Attempt, no request;
- Decimal/moneda/referencia correctos;
- URL/configuración por entorno;
- response OK guarda una sola preference;
- timeout antes/después de creación;
- 4xx/401/403/429/5xx clasificados;
- misma key + mismo hash devuelve mismo Attempt;
- misma key + payload distinto conflict;
- TX2 falla y retry recupera;
- dos clicks concurrentes crean un Attempt;
- no se mantiene transacción durante HTTP;
- no se filtran secrets en error/log.

### Webhook

- firma válida e inválida;
- timestamp/replay inválido;
- body/query malformado y tamaño excesivo;
- tipo soportado/no soportado;
- Event ID duplicado y fingerprint fallback;
- payment inexistente;
- SDK timeout/429/5xx;
- official response sin campos;
- external reference inexistente, malformada o de otro namespace;
- preference mismatch;
- amount menor/mayor;
- currency mismatch;
- respuesta oficial approved frente a payload pending y viceversa;
- Event sólo queda processed on-commit.

### Conciliación

- pago exacto crea un Pago;
- partial legítimo mantiene Intent pending;
- partial inesperado abre mismatch;
- múltiples Payments alcanzan umbral;
- duplicate payment ID devuelve mismo Pago;
- Pago existente con otro Intent genera integrity conflict;
- DEPOSIT deja balance;
- FULL deja balance cero;
- pago posterior de balance no crea Turno;
- late crea Pago pendiente/caso y no aprueba Intent;
- reconciliation manual usa fetch y permiso.

### Agenda

- HOLD vigente consume y crea Turno `CONFIRMADO`;
- usa todos los snapshots y `exclude_hold_id`;
- no acepta campos de agenda del frontend;
- HOLD vencido no crea Turno;
- solicitud/evaluación no vigente no crea Turno y preserva dinero/caso;
- revalidación operacional falla y conserva conciliación;
- exactly one Turno por operation key/HOLD;
- notificación/auditoría una vez.

### Concurrencia PostgreSQL real

- dos entregas idénticas;
- dos eventos approved distintos del mismo Payment;
- dos Payments parciales simultáneos;
- webhook vs expiración;
- webhook vs cancelación;
- webhook vs reconciliación manual;
- return refresh vs webhook;
- dos procesos consumen mismo HOLD;
- espera de lock atraviesa expiry;
- crash entre fetch y transacción;
- crash después de commit antes de ack;
- ausencia de deadlock con orden común.

### Frontend

- checkout sólo redirige URL backend;
- no envía amount/status;
- success/failure/pending no confirman;
- página retorno consulta estado interno;
- 202 pending y casos tardíos/revisión;
- ownership/404 seguro;
- retry conserva idempotency key.

### OrdenCompra/migración

- referencia numérica va sólo a legacy;
- namespace booking nunca ejecuta handler de orden;
- referencia order futura nunca ejecuta booking;
- Pago no mezcla ambos contextos;
- side effect de orden no corre para booking;
- eventos legacy continúan durante cutover;
- out-of-order no degrada una orden ya completada cuando se refactorice.

---

## 31. Convivencia con `OrdenCompra`

### 31.1 Separación de handlers

Puede compartirse:

- `MercadoPagoAdapter`;
- verificación de firma;
- `ProviderEvent` inbox;
- fetch/normalización/error handling;
- métricas de transporte.

Debe permanecer separado:

- `BookingPaymentReconciler`;
- `OrderPaymentReconciler` legacy;
- constraints y snapshots del agregado;
- estados de Orden vs Intent/HOLD;
- todo efecto lateral de orden.

El router decide sólo después de fetch oficial y namespace exacto. Nunca un
`if booking not found -> order` ambiguo.

### 31.2 Cutover seguro

1. inventariar preferences legacy pendientes y sus notification URLs;
2. desplegar adapter/inbox sin cambiar todavía su dominio;
3. aceptar referencia numérica únicamente en handler legacy;
4. emitir sólo referencias namespaced para booking nuevo;
5. separar unique provider payment de contexto Pago;
6. observar eventos unmatched;
7. migrar nuevas órdenes a namespace propio en otro incremento, no en C;
8. retirar alias sólo cuando no queden preferences vivas.

El webhook actual puede convivir temporalmente, pero no debe ser llamado desde
el nuevo endpoint. Idealmente ambos endpoints desembocan en un ingress verificado
común y luego en handlers tipados.

### 31.3 Frontera de stock

La rama legacy approved hoy reduce stock real de items de Orden. El handler
booking no importa `Producto`, `OrdenItem` ni servicios de inventario y no puede
alcanzar esa función. La revisión de ese efecto pertenece a BH-058 D/stock.

---

## 32. Migración de datos/configuración

Sin migrar órdenes ni implementar aún:

- añadir provider config requerida y validar al arrancar;
- documentar variables en `.env.example` sin valores;
- fijar SDK en manifiesto de dependencias;
- crear tablas Attempt/Event/caso y constraints;
- ampliar Pago según B con contexto exacto y provider reference;
- backfill de `OrdenCompra.preference_id` sólo como dato legacy;
- no fabricar Events históricos;
- identificar Pagos MP con `transaccion_id` y Orden para evitar colisión al crear
  unique `(provider, payment_id)`;
- auditar filas Pago sin origen o con doble origen antes del constraint;
- mantener rutas legacy hasta drenar preferences.

No copiar tokens locales a migraciones/DB. Rotar cualquier credencial si alguna
vez fue expuesta fuera del `.env` ignorado, decisión operativa fuera de este
documento.

---

## 33. Puntos que requieren documentación externa

El código y SDK instalado no bastan para cerrar los siguientes contratos. En
cada caso aplica exactamente:

**REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**

1. algoritmo, canonical string, headers y tolerancia de firma webhook;
2. secret/configuración y rotación de firma;
3. ID estable de evento y campos que permanecen iguales en retries;
4. notification types/actions vigentes para Checkout Pro;
5. códigos HTTP y calendario de redelivery;
6. soporte real de idempotency key en creación de preference, header, scope y
   ventana;
7. comportamiento del SDK 3.2.0 al reintentar POST y reutilización del header;
8. búsqueda/recuperación de preference por external reference o key;
9. longitud/charset de external reference;
10. campo oficial de preference/checkout dentro de Payment para correlación;
11. campos autoritativos de amount/currency y precisión por moneda;
12. estados/status_detail y transiciones actuales, incluidos refunds y
    chargebacks;
13. eventual consistency de `GET Payment` tras webhook;
14. expiración/cancelación de preference y garantías ante links viejos;
15. diferencias sandbox/production e `init_point`/`sandbox_init_point`;
16. rate limits y `Retry-After` aplicables.

Nada de esa lista debe inventarse durante implementación. Cada decisión debe
quedar respaldada por enlace/version/fecha de la documentación validada.

---

## 34. Frontera BH-058 D

BH-058 C no diseña:

- stock disponible/comprometido/real;
- `MovimientoStock`;
- consumo de productos en Servicios;
- permisos o reportes de inventario.

Sólo establece que el handler booking no reutiliza la rama approved de
`OrdenCompra`, porque contiene un efecto lateral sobre stock. La refactorización
de ese dominio queda fuera de C.

---

## 35. Decisiones finales solicitadas

### 1. Inventario MP actual

SDK Python 3.2.0 sólo en el venv local, sin dependency manifest; access token y
public key desde env/settings; public key sin uso; URLs con defaults ngrok/
localhost; preference acoplada a OrdenCompra; dos endpoints de checkout;
webhook `AllowAny` sin firma; fetch oficial; external reference numérica; Pago
parcialmente deduplicado; callbacks React inexistentes; cero tests MP.

### 2. Piezas reutilizables vs acopladas

Reutilizar detrás del adapter: SDK, fetch Payment, patrón de redirección,
configuración por settings y locks. No reutilizar para booking:
`MercadoPagoService(OrdenCompra)`, helper de carrito, referencia numérica,
handler/estados/efectos laterales de Orden ni return URLs actuales.

### 3. Arquitectura adapter

`PaymentProvider` define crear checkout, fetch, verificar webhook y normalizar.
`MercadoPagoAdapter` es el único importador del SDK. Entrega DTOs inmutables y
errores tipados; el dominio nunca recibe payload crudo como autoridad.

### 4. `ProviderPaymentAttempt` / `ProviderEvent`

Intent 1:N Attempts, un checkout utilizable a la vez. Attempt conserva monto,
moneda, referencia y key inmutables. Event es inbox durable con ID/fingerprint,
hash, signature result, retries y deduplicación. Payment IDs quedan unique en
Pago.

### 5. Creación checkout

TX1 persiste Attempt bajo locks; HTTP ocurre fuera de TX; TX2 fija preference y
URL. Todos los retries reutilizan Attempt/key. Resultado incierto nunca crea un
checkout nuevo a ciegas.

### 6. Webhook seguro

Verifica firma sobre raw request, persiste/deduplica Event, consulta Payment
oficial, compara referencia/preference/amount/currency y recién entonces llama
al core. CSRF, payload, query y return URL no son prueba financiera.

### 7. Conciliación

Pago se crea por servicio interno y unique `(provider,payment_id)`. Match exacto
produce `RECONCILED`; mismatch/tardío produce `PENDING_RECONCILIATION` y caso.
La suma elegible decide el umbral, no el provider.

### 8. Pago tardío

Attempt refleja approved oficial; Pago pendiente con `LATE_PAYMENT`; caso OPEN;
Intent/HOLD permanecen terminales y no hay Turno. No refund/crédito automático.

### 9. Orquestador final

`reconcile_external_payment_and_confirm_booking` reconcilia Pago, aprueba Intent,
revalida agenda, crea Turno `CONFIRMADO` y consume HOLD dentro de una sola
transacción, usando savepoint para conservar resultado financiero ante fallo de
dominio definitivo.

### 10. Concurrencia

Orden: solicitud → HOLD → Intent → Cliente → Attempt → Event/Pagos → Servicios
→ Personal → tipos → Turno. Uniques, reloj nuevo y consumo condicional producen
un Pago/Intent/Turno; expiry ganador convierte cualquier pago posterior en late.

### 11. Permisos

Cliente inicia/consulta sólo lo propio. Reconciliación externa manual requiere
nuevo `reconcile_external_payment`. Reportes usan `view_financial_reports` y
PaymentPolicy `manage_payment_configuration`. Secrets no se administran por UI.
Sistema/webhook tiene identidad explícita. No se usa rol ni `is_staff`.

### 12. Seguridad

Firma + fetch oficial + replay/idempotency + ownership + IDs opacos + URLs/API
allowlisted + body limits + throttling + logs sanitizados. No secrets/payloads/
checkout URLs en logs o respuestas.

### 13. Convivencia con `OrdenCompra`

Ingress/adapter pueden ser comunes; reconciliadores son separados. Referencia
numérica va sólo a legacy y namespace booking sólo a booking. Ningún camino
booking importa o ejecuta efectos laterales de orden.

### 14. Riesgos

Los mayores son firma ausente, monto/moneda no comparados, external reference
enumerable, POST externo dentro de TX, falta de idempotencia durable, evento no
persistido, estados fuera de orden que degradan Orden, callbacks rotos, defaults
de entorno inseguros y ausencia total de tests/observabilidad.

### 15. Puntos que requieren documentación externa

Firma/headers/canonicalización, event ID, redelivery, idempotencia de preference,
recovery/search, referencia, estados, amount/currency, refunds, expiración,
sandbox/production y rate limits están listados en la sección 33 con la marca
obligatoria **REQUIERE VERIFICACIÓN CON DOCUMENTACIÓN ACTUAL DE MERCADO PAGO**.

### 16. Primer incremento recomendado

1. Fijar SDK/dependencias y documentar configuración técnica sin secrets.
2. Verificar y registrar la documentación externa de firma, idempotencia,
   estados y expiración antes de codificar.
3. Crear protocolos/DTOs `PaymentProvider` y `MercadoPagoAdapter`, sin tocar aún
   OrdenCompra.
4. Crear `ProviderPaymentAttempt`, `ProviderEvent` y
   `PaymentReconciliationCase` con uniques/estados/auditoría.
5. Implementar checkout booking TX1/HTTP/TX2 con key persistente y recuperación
   `OUTCOME_UNKNOWN`.
6. Implementar nuevo webhook namespaced como inbox seguro + fetch oficial, sin
   conectar todavía side effects de orden.
7. Implementar el reconciliador idempotente de Pago y validaciones exactas.
8. Extraer la primitiva canónica `create_confirmed_turno_from_locked_hold` con
   snapshots y `exclude_hold_id`.
9. Implementar el orquestador final y pago tardío con el orden de locks A/B.
10. Añadir endpoints semánticos, permiso `reconcile_external_payment`, métricas
    y matriz de tests PostgreSQL/concurrencia.
11. Conectar UI mínima de checkout/status/return informativo.
12. Sólo después, enrutar legacy y booking por namespaces explícitos y ejecutar
    cutover observado sin migrar stock.
