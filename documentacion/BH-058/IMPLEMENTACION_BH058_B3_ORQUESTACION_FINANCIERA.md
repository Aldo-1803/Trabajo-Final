# BH-058 B3 — Aprobación financiera y orquestación con A2

Fecha de validación: 2026-10-26.

## Resultado

Se implementó un único orquestador interno:

```python
approve_payment_intent_and_confirm_booking(
    *,
    intent_id,
    actor=None,
    operation_key=None,
)
```

El servicio vive en
`bohemiacore/gestion/payment_confirmation_services.py`. Es el único punto que
recalcula el umbral financiero, lleva el `PaymentIntent` a `APPROVED`, delega
en A2 el consumo del `SlotHold` y enlaza el único `Turno` `CONFIRMADO`.

No se agregó endpoint `/approve/`, signal, transición desde serializer ni
lógica de frontend. La invocación automática ocurre solamente:

- al registrar un Pago `CASH`, que nace `RECONCILED`;
- al aceptar una conciliación manual B2 que cambia el Pago a `RECONCILED`.

La autoridad sigue siendo `register_payment` o `confirm_deposit`. La transición
final es interna y no agrega permisos, `is_staff` ni roles textuales.

## Transacción y locks

B2 y B3 operan dentro de una única `transaction.atomic`; las atomicidadas
anidadas de Django son savepoints, no commits intermedios. La secuencia efectiva
es:

1. bloquear `SolicitudTecnicaReserva`;
2. bloquear `SlotHold`;
3. bloquear `PaymentIntent`;
4. bloquear `Cliente`;
5. bloquear todos los `Pago` del Intent por PK ascendente;
6. recalcular exclusivamente los importes `RECONCILED` y validar moneda/total;
7. tomar un reloj PostgreSQL nuevo;
8. si se alcanza el umbral, hacer la transición interna a `APPROVED`;
9. invocar `create_confirmed_turno_from_locked_hold(...)` de A2;
10. A2 bloquea Servicios por PK, Personal, tipos de equipamiento por PK y el
    Turno enlazado sólo en retry, y toma otro reloj después de esos locks;
11. enlazar Intent y Pagos conciliados al Turno;
12. auditar y confirmar la transacción completa.

No se duplicaron el builder, las validaciones técnicas/de disponibilidad, el
consumo condicional, la auditoría de HOLD ni la notificación de A2.

## Umbral y transición `APPROVED`

El total se deriva nuevamente bajo locks desde Pagos cuyo estado es
`RECONCILED`. Pagos `PENDING_RECONCILIATION`, `REJECTED` o `REVERSED` no cuentan.
También se valida:

- Intent en `CREATED` o `PENDING`;
- moneda de todos los hechos elegibles;
- `paid_reconciled <= total_amount_snapshot`;
- vigencia temporal de Intent y HOLD;
- HOLD `ACTIVE` antes del consumo.

Si `paid_reconciled < required_amount`, el resultado estable es
`PAYMENT_THRESHOLD_NOT_REACHED`: el Intent queda `PENDING`, el HOLD permanece
`ACTIVE` mientras sea vigente y no nace ningún Turno. No es un error.

Si se alcanza el umbral, `APPROVED` y el consumo A2 están en la misma
transacción. Nunca existe un commit intermedio. El Intent conserva
`confirmed_turno` y `confirmation_operation_key`; el HOLD conserva el mismo
Turno y operation key por su contrato A2.

## DEPOSIT, FULL y pagos posteriores

- `DEPOSIT`: al alcanzar `required_amount` confirma el Turno, aunque el balance
  derivado hasta `total_amount_snapshot` sea mayor que cero.
- `FULL`: usa la misma transición y estado de Turno; al alcanzar el total el
  balance derivado es cero.
- después de `APPROVED`, B2 sólo admite nuevos registros con propósito
  `BALANCE`; se enlazan al Turno existente;
- una conciliación posterior de saldo enlaza el Pago, pero no vuelve a ejecutar
  A2 ni crea auditoría/notificación de confirmación adicional.

No se escriben `monto_abonado`, `saldo_pendiente` ni otros acumulados legacy.

## Idempotencia

La integración usa una key determinista por Intent:

```text
payment-confirm:{intent.public_id}
```

La key se persiste en el Intent y A2 la persiste en el HOLD. Por ello:

- dos detectores simultáneos se serializan en el lock del Intent;
- el ganador aprueba y consume;
- el segundo recupera el mismo Turno mediante el retry de A2;
- un retry tras commit devuelve `changed=False` y el mismo Intent/Turno;
- otra key para el mismo Intent produce conflicto;
- un Intent `APPROVED` sin HOLD consumido, Turno coherente y key coincidente se
  trata como `APPROVED_INTENT_WITHOUT_CONFIRMED_BOOKING`; no crea a ciegas.

Las auditorías y la notificación se generan sólo en el camino ganador.

## Fallos confirmatorios y `PaymentReconciliationCase`

B3 necesita representar dinero reconciliado que no pudo producir agenda. Se
implementó la entidad mínima provider-neutral `PaymentReconciliationCase`, ya
reservada por la arquitectura, sin adelantar C.

Registra:

- tipo `LATE_PAYMENT` o `BOOKING_CONFIRMATION_FAILED`;
- estado `OPEN`;
- Intent, HOLD, Turno opcional y relación a los Pagos relevantes;
- `reason_code`, operation key, actor, timestamp y detalles monetarios mínimos.

La operation key es única, por lo que un retry del fallo recupera el mismo caso
y no duplica `PAYMENT_CONFIRMATION_FAILED`.

Semántica terminal:

- HOLD/Intent vencido: A2 o B1 materializa el estado temporal, el Intent queda
  `EXPIRED`, se crea `LATE_PAYMENT`, se preservan los Pagos y no hay Turno;
- solicitud/evaluación inválida: A2 deja el HOLD `RELEASED`, el Intent queda
  `REJECTED`, se crea `BOOKING_CONFIRMATION_FAILED` y se preservan los Pagos;
- Personal inactivo, skill retirada, bloqueo, equipamiento o snapshot inválido:
  A2 deja el HOLD `RELEASED` con su razón, el Intent queda `REJECTED`, se crea el
  caso y no se borra ningún hecho financiero.

No se resucita un HOLD, no se automatiza refund y no se deja un Intent
falsamente `APPROVED` después de un fallo esperado de A2.

La migración
`gestion/migrations/0031_paymentintent_confirmation_operation_key_and_more.py`
agrega el vínculo/key al Intent y crea el caso de conciliación con constraints e
índices. C podrá extender esta entidad posteriormente, pero B3 no contiene
campos ni referencias específicas de proveedor.

## Auditoría y notificaciones

B3 registra:

- `PAYMENT_INTENT_APPROVED`;
- `BOOKING_CONFIRMED_FROM_PAYMENT`;
- `PAYMENT_CONFIRMATION_FAILED` cuando corresponde.

Los payloads incluyen Intent, HOLD, IDs de Pagos, Turno, actor/sistema, timestamp,
reason code y hash SHA-256 de la operation key. La key no se copia en claro a la
auditoría.

La única notificación “Turno confirmado” sigue siendo la idempotente de A2,
identificada por el HOLD. B3 no crea una segunda notificación financiera.

## Pruebas funcionales y PostgreSQL

`test_payment_confirmation.py` cubre 11 casos:

1. parcial sin umbral;
2. umbral exacto;
3. DEPOSIT con saldo;
4. FULL con balance cero;
5. retry con el mismo Turno;
6. balance posterior sin segundo Turno;
7. HOLD vencido con Pago preservado y caso tardío;
8. solicitud inválida con Pago preservado;
9. recurso inválido con Pago preservado;
10. notificación y auditorías exactamente una vez;
11. `APPROVED` huérfano tratado como estado excepcional.

`test_payment_confirmation_concurrency.py` ejecuta siete carreras con conexiones
PostgreSQL independientes y verifica el estado final de base:

A. dos CASH simultáneos completan el umbral;
B. dos conciliaciones distintas completan el umbral;
C. conciliación contra expiración;
D. conciliación contra release;
E. espera por lock de recurso cruza `expires_at`;
F. dos orquestadores sobre los mismos datos;
G. retry después del commit.

Resultados ejecutados sobre PostgreSQL:

| Bloque | Resultado |
|---|---:|
| B3 funcional | 11/11 |
| B3 concurrencia real | 7/7 |
| B3 + B2 + B1 + A2 + A1 | 113/113 |
| BH-057 | 92/92 |
| Turnos y disponibilidad | 94/94 |
| Roles y `/me/` | 31/31 |
| Matriz total | 330/330 |

Checks técnicos:

- `python manage.py check`: sin issues;
- `python manage.py makemigrations --check --dry-run`: sin cambios pendientes;
- `python -m compileall -q gestion usuarios`: correcto;
- `git diff --check`: correcto, con avisos informativos de line endings en
  archivos preexistentes.

## Frontera C

B3 no agregó ni extendió:

- imports de `mercadopago`;
- `ProviderPaymentAttempt`;
- `ProviderEvent`;
- webhook;
- checkout externo;
- stock o `MovimientoStock`;
- caja física;
- refunds automáticos.

No se continuó con C.

BH-058 B3 = VALIDADO
