# BH-058 B2 — Pago manual, conciliación y permisos

Fecha de validación: 2026-10-26.

## Alcance

Se implementó exclusivamente B2 sobre el baseline validado de A1, A2 y B1:

```text
PaymentIntent -> Pago 1:N -> registro manual -> conciliación/rechazo
```

El incremento registra hechos financieros y expone las proyecciones
`paid_reconciled`, `confirmation_due`, `balance` y
`financial_threshold_reached`. No aprueba el Intent, no consume el HOLD y no
crea Turnos.

## Auditoría previa del legado

Se revisaron el modelo y serializer de `Pago`, sus tres escritores
`registrar_pago`, `PagoViewSet`, historial, comprobantes, `transaccion_id`,
`es_sena`, relaciones con `Turno`/`OrdenCompra` y permisos basados en
`is_staff`/`IsAdminUser`.

Preflight de datos del entorno:

| Clasificación | Cantidad |
|---|---:|
| Pagos totales | 0 |
| Sólo OrdenCompra | 0 |
| Sólo Turno | 0 |
| OrdenCompra + Turno | 0 |
| Huérfanos | 0 |

La migración conserva además un preflight fail-closed para otros entornos. Si
encuentra un Pago Turno-only, huérfano o ambiguo, aborta sin inventar un
`PaymentIntent`.

## Modelo financiero

`Pago` incorpora:

- `public_id` UUID;
- `payment_intent` con `PROTECT`;
- contexto legacy `orden` con `PROTECT`;
- `currency`, `purpose` y `status`;
- actor y fechas de registro/conciliación;
- referencia manual normalizada;
- hash SHA-256 del comprobante;
- clave de idempotencia;
- razón terminal.

Se mantienen `monto`, `metodo_pago`, `fecha_pago`, `comprobante_foto`,
`transaccion_id` y `es_sena` para compatibilidad de almacenamiento legacy. Los
servicios y DTO exponen los nombres canónicos `amount`, `method`,
`occurred_at` y descarga de `receipt`.

Las constraints garantizan:

- importe positivo;
- exactamente un contexto: `PaymentIntent` o `OrdenCompra`;
- ausencia de la combinación legacy ambigua Orden + Turno;
- actor y clave idempotente obligatorios para booking;
- consistencia entre estado y metadatos de conciliación;
- unicidad de referencias manuales de transferencia/tarjeta;
- UUID público único.

Los Pagos persistidos no admiten update/delete genérico. Las únicas
transiciones B2 se ejecutan mediante el manager interno y los servicios
semánticos.

## Registro manual

`register_manual_payment()` exige `gestion.register_payment` y bloquea en
orden canónico:

1. `SolicitudTecnicaReserva`;
2. `SlotHold`;
3. `PaymentIntent`;
4. `Cliente`;
5. Pagos del Intent ordenados por PK.

Valida vigencia, contexto técnico, policy snapshot, medio habilitado, importe,
moneda, saldo, idempotencia, referencia y evidencia. El primer Pago vigente
sólo puede mover el Intent de `CREATED` a `PENDING`.

Semántica de medios:

- `CASH`: nace `RECONCILED` con actor y timestamp de conciliación;
- `BANK_TRANSFER`, `EXTERNAL_CARD` y `OTHER`: nacen
  `PENDING_RECONCILIATION` y requieren referencia y comprobante;
- referencias normalizadas repetidas se rechazan;
- se rechazan referencias que puedan contener PAN completo, incluso con
  separadores;
- no se acepta sobrepago respecto de `total_amount_snapshot`.

La misma clave con el mismo payload devuelve el mismo Pago. La misma clave con
otro payload produce conflicto.

## Pago tardío

Un Intent/HOLD vencido no admite registro normal. Con `late_evidence=true` se
puede preservar evidencia real como:

```text
status = PENDING_RECONCILIATION
terminal_reason = LATE_MANUAL_REVIEW
```

Esto no reactiva el HOLD ni el Intent. B2 tampoco permite conciliar esa
evidencia como aplicable; queda explícitamente reservada para un flujo futuro.

## Conciliación

`reconcile_manual_payment()` exige `gestion.confirm_deposit`, aplica los mismos
locks canónicos y sólo opera sobre `PENDING_RECONCILIATION`:

- `ACCEPT` -> `RECONCILED`;
- `REJECT` -> `REJECTED`, con razón obligatoria.

Una repetición con la misma decisión es idempotente y no genera otra auditoría
semántica. La aceptación vuelve a validar vigencia y sobrepago. Nunca modifica
importe, moneda, referencia ni origen.

## Proyecciones

La autoridad financiera es la suma de Pagos `RECONCILED`:

```text
paid_reconciled = SUM(Pago.amount WHERE status = RECONCILED)
confirmation_due = max(required_amount - paid_reconciled, 0)
balance = max(total_amount_snapshot - paid_reconciled, 0)
```

`Turno.monto_abonado` y `Turno.saldo_pendiente` no se leen ni se actualizan
desde B2. Alcanzar el umbral sólo devuelve
`financial_threshold_reached=true`.

## Comprobantes privados

Los nuevos comprobantes se guardan fuera de `MEDIA_ROOT` mediante
`PrivatePaymentReceiptStorage`, que no expone `url()`. Se validan tamaño máximo
de 5 MB, MIME y firma binaria para PDF, PNG y JPEG.

La descarga se realiza únicamente por un endpoint autenticado y autorizado.
Los nombres legacy `pagos/comprobantes/...` conservan fallback de lectura para
no romper archivos históricos, pero no se exponen como URL desde el DTO B2.

## API

Superficies semánticas:

- `POST /api/gestion/payment-intents/{public_id}/payments/`;
- `GET /api/gestion/payment-intents/{public_id}/payments/`;
- `POST /api/gestion/payments/{public_id}/reconcile/`;
- `GET /api/gestion/payments/{public_id}/receipt/`;
- `GET /api/gestion/payments/` para reporte global autorizado.

No se expone create/update/delete genérico de Pago. Se conserva el alias
legacy `/api/gestion/pagos/` para lectura global con el mismo permiso.

El historial global devuelve totales por estado, moneda y medio reconciliado.
`physical_cash_balance` se informa como `null`: no representa caja física.

`OrdenCompra.registrar_pago` se conserva para compatibilidad y ahora exige
`register_payment`, incluso cuando el permiso es individual y el usuario no es
staff. Los escritores Turno-only y `OrdenPendiente` quedaron deshabilitados.

## Permisos y defaults

La autoridad se obtiene exclusivamente con `has_perm()`:

| Rol | Defaults B2 |
|---|---|
| CLIENTE | Lectura de Pagos propios cuando corresponde |
| EMPLEADO | `gestion.register_payment` |
| PROFESIONAL | Sin permisos financieros por default |
| ADMINISTRADOR | `register_payment`, `confirm_deposit`, `view_financial_reports` |

Se verificó que:

- un permiso individual funciona con `is_staff=False`;
- `is_staff=True` sin permiso devuelve 403;
- `confirm_deposit` no registra;
- `register_payment` no concilia ni habilita reportes globales;
- `BusinessRole` o `Personal.rol` por sí solos no autorizan;
- `view_financial_reports` sólo habilita lectura global.

## Auditoría

Se registran:

- `PAYMENT_MANUAL_REGISTERED`;
- `PAYMENT_RECONCILED`;
- `PAYMENT_REJECTED`;
- la transición auxiliar `PAYMENT_INTENT_PENDING`.

Cada evento incluye actor, Intent, HOLD, Pago, importe, moneda, medio, estado
anterior/nuevo, razón, timestamp y hash de la clave idempotente/referencia. No
se registra el binario ni información completa de tarjeta.

## Migración

`gestion/migrations/0030_pago_manual_b2.py`:

- agrega campos, índices y constraints;
- asigna UUID único fila por fila;
- aborta ante contextos legacy no convertibles de forma segura;
- no crea Intents ni reinterpreta Pagos;
- actualiza defaults de EMPLEADO, PROFESIONAL y ADMINISTRADOR.

La creación completa de la base de pruebas PostgreSQL aplicó correctamente la
migración.

## Concurrencia PostgreSQL real

`test_manual_payment_concurrency.py` cubre seis carreras con conexiones
independientes y timeout anti-deadlock:

1. dos Pagos CASH que intentarían sobrepagar;
2. misma clave idempotente;
3. misma referencia bancaria;
4. dos conciliaciones del mismo Pago;
5. cancelación de Intent contra registro;
6. expiración de Intent contra registro.

Resultado: 6/6. No hubo deadlocks, doble transición, doble auditoría ni
sobrepago.

## Evidencia de pruebas

Todas las suites se ejecutaron sobre PostgreSQL:

| Bloque | Resultado |
|---|---:|
| B2 funcional + permisos + concurrencia | 26/26 |
| A1 + A2 + B1, incluidas concurrencias | 69/69 |
| BH-057 | 92/92 |
| Turnos y disponibilidad | 94/94 |
| Roles y `/me/` | 31/31 |
| Total de la matriz ejecutada | 312/312 |

Checks técnicos:

- `python manage.py check`: OK;
- `python manage.py makemigrations --check --dry-run`: sin cambios;
- `python -m compileall -q gestion usuarios`: OK;
- `git diff --check`: OK.

## Frontera estricta verificada

En el servicio B2 no existe:

- transición de `PaymentIntent` a `APPROVED` por Pagos;
- consumo de A2/HOLD desde finanzas;
- creación o confirmación de Turno;
- actualización de saldos legacy del Turno;
- Mercado Pago nuevo;
- `ProviderPaymentAttempt` o `ProviderEvent`;
- webhook nuevo;
- stock o `MovimientoStock`;
- apertura, cierre, arqueo o saldo de caja física;
- autoridad basada en `is_staff`, `BusinessRole` o `Personal.rol`.

La integración Mercado Pago/stock legacy existente no fue extendida ni
convertida en autoridad del flujo B2. B3 no fue implementado.

BH-058 B2 = VALIDADO
