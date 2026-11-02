# BH-058 F7.2 — Solicitudes y decisiones financieras

**Fecha:** 2026-11-02

**Base:** F7.1, commit `54a4245`

**Alcance:** solicitud y decisión auditables. No incluye ejecución, confirmación
financiera ni cierre.

## Resultado

F7.2 incorpora un workflow explícito que conserva esta separación:

```text
SOLICITUD -> DECISIÓN -> futura EJECUCIÓN -> futura CONFIRMACIÓN -> futuro CIERRE
```

Una solicitud o decisión no modifica `Pago`, `PaymentIntent`, stock, compromiso,
orden ni neto financiero. Tampoco cambia un `PaymentReconciliationCase` a
`RESOLVED`.

## Modelos y migración

La migración `gestion/0037_financial_resolution_f7_2.py` agrega:

- `PaymentReconciliationCase.Type.CANCELLATION_WITH_PAYMENT`;
- `FinancialResolutionRequest`, una solicitud por caso;
- `FinancialResolutionDecision`, historial inmutable de decisiones;
- `FinancialResolutionEvent`, eventos append-only de solicitud y decisión.

### Solicitud

Registra identidad pública, caso, solicitante, contexto `BOOKING`/`ORDER`, Turno
cuando corresponde, resultado solicitado, motivo, importe/moneda opcionales,
referencia y nota de evidencia, estado, fecha, clave idempotente y fingerprint.

Resultados solicitables:

- `REFUND`;
- `CANCEL_AND_REFUND`;
- `REVIEW_PAYMENT`;
- `REVIEW_EXTERNAL_ADJUSTMENT`;
- `NO_FINANCIAL_CHANGE`.

La relación 1:1 con el caso impide solicitudes activas contradictorias. La clave
`(requested_by, idempotency_key)` es única y el fingerprint impide reutilizarla
con otro payload.

### Decisión

Registra secuencia, acción, fundamento, evidencia adicional requerida, importe
autorizado, moneda, política, decisor, fecha, clave idempotente y fingerprint.

Acciones permitidas:

- `APPROVE_REFUND`;
- `DENY_REFUND`;
- `REQUIRE_MORE_EVIDENCE`;
- `ACKNOWLEDGE_EXTERNAL_ADJUSTMENT`;
- `NO_FINANCIAL_CHANGE`.

Existe una restricción condicional que permite una sola decisión final por
solicitud. Puede haber decisiones previas `REQUIRE_MORE_EVIDENCE`, pero ninguna
decisión final se sobrescribe.

### Estados

```text
PENDING_DECISION --REQUIRE_MORE_EVIDENCE--> EVIDENCE_REQUIRED
PENDING_DECISION --decisión final---------> DECIDED
EVIDENCE_REQUIRED --REQUIRE_MORE_EVIDENCE-> EVIDENCE_REQUIRED
EVIDENCE_REQUIRED --decisión final--------> DECIDED
```

`DECIDED` es terminal dentro de F7.2. En todas las transiciones el caso conserva
`status=OPEN` y `resolved_at=null`.

## Integridad de dominio

`financial_resolution_services.py` aplica transacciones y locks siguiendo los
órdenes existentes:

- BOOKING: solicitud técnica, HOLD, Intent, Cliente, Pagos y caso;
- ORDER: orden, Pagos, caso y, para solicitud de cancelación pagada,
  compromisos.

Las filas autoritativas se bloquean sin `LEFT JOIN`, para que `FOR UPDATE` sea
válido en PostgreSQL. Solicitudes, decisiones y eventos bloquean creación,
update/delete y operaciones masivas genéricas; sólo sus managers internos
permiten las transiciones semánticas.

Validaciones principales:

- ownership para titulares y allowlist de tipos/resultados;
- cuenta activa y permiso efectivo
  `gestion.reconcile_external_payment` para decidir, también en dominio;
- coherencia de contexto, resultado, moneda e importe;
- `APPROVE_REFUND` sólo contra Pagos `RECONCILED` y sin superar el menor entre
  importe solicitado y total actualmente reversible;
- pagos pendientes pueden motivar solicitud, pero no aprobación de devolución;
- política obligatoria para aprobar o denegar refund;
- evidencia concreta obligatoria para `REQUIRE_MORE_EVIDENCE`;
- `ACKNOWLEDGE_EXTERNAL_ADJUSTMENT` sólo para casos y solicitudes compatibles;
- idempotencia con detección de payload divergente;
- rollback si falla la auditoría semántica.

No se usa `PaymentReconciliationCase.details` como estado mutable. Los hechos
originales de `Pago` y `PaymentIntent` se conservan.

## Cancelaciones integradas

### Turno con dinero

Las cancelaciones autorizadas inspeccionan primero el contexto financiero
BOOKING. Si existe un Pago `PENDING_RECONCILIATION` o `RECONCILED`, en la misma
transacción:

1. se aplica la cancelación comercial vigente;
2. se crea/reutiliza un caso `CANCELLATION_WITH_PAYMENT`;
3. se presenta una solicitud `CANCEL_AND_REFUND`.

No se altera la política de cancelación, no se degrada el Intent y no se recrea
el HOLD. La respuesta incluye los UUID públicos de caso y solicitud.

### Orden `PAGADO`

La acción separada de solicitud crea/reutiliza caso y solicitud, pero conserva:

- orden `PAGADO`;
- compromiso `ACTIVE`;
- Pago original;
- stock real y comprometido;
- ausencia de movimientos nuevos.

La ruta ordinaria F5 continúa respondiendo
`ORDER_CANCELLATION_REQUIRES_FINANCIAL_RESOLUTION`.

## API semántica

Sobre `payment-reconciliation-cases` se agregan:

- `POST /{public_id}/submit-resolution-request/`;
- `GET /{public_id}/resolution-request/`;
- `POST /{public_id}/record-decision/`;
- `POST /request-paid-order-cancellation/`.

Los comandos mutables exigen `Idempotency-Key`. No se expone CRUD de
solicitudes, decisiones o eventos.

La lista y detalle F7.1 siguen reservados a conciliadores. La consulta de una
solicitud permite al titular de su propio recurso una proyección pública
reducida; el historial interno con actores, fundamentos, políticas y eventos se
expone sólo a quien tiene el permiso financiero.

## Auditoría

Cada transición crea un evento append-only y una auditoría semántica:

- `FINANCIAL_RESOLUTION_REQUESTED`;
- `FINANCIAL_EVIDENCE_REQUESTED`;
- `FINANCIAL_RESOLUTION_DECIDED`.

Los snapshots declaran explícitamente
`NO_FINANCIAL_OR_BUSINESS_EFFECT` o
`NO_EXECUTION_NO_CONFIRMATION_NO_CASE_CLOSURE`.

## Pruebas

`test_financial_resolution.py` cubre 14 escenarios funcionales:

1. solicitud legítima e idempotente;
2. recurso ajeno;
3. cliente, `is_staff` sin permiso y cuenta inactiva intentando decidir;
4. validación duplicada del permiso en API y dominio;
5. decisión autorizada con fundamento y política;
6. importes excesivos y moneda incompatible;
7. evidencia adicional seguida de una única decisión final;
8. las cinco acciones admitidas;
9. separación de payload público e interno;
10. rollback ante fallo de auditoría e inmutabilidad genérica;
11. pago tardío sin resurrección de HOLD, Intent o Turno;
12. cancelación de Turno con dinero y solicitud enlazada;
13. orden `PAGADO` sin cancelación, liberación ni movimiento;
14. ownership de la solicitud de cancelación pagada.

`test_financial_resolution_concurrency.py` usa PostgreSQL real y verifica dos
decisiones finales contradictorias concurrentes: persiste exactamente una.

Regresiones ejecutadas:

- B3: confirmación financiera y concurrencia;
- C2b: conciliación externa y concurrencia;
- F5: inventario/cancelación y concurrencia;
- F6: checkout presencial y concurrencia;
- F7.1: lectura segura de casos;
- cancelaciones semánticas de Turno.

La consola Windows requiere `PYTHONIOENCODING=utf-8` por mensajes de diagnóstico
preexistentes con emoji. Las pruebas de roles deben correr sobre base limpia si
antes se reutilizó una base vaciada por `TransactionTestCase`.

## Límites explícitos

F7.2 no implementa:

- llamadas de refund a Mercado Pago;
- devoluciones manuales;
- operaciones de ejecución;
- ajustes financieros o chargebacks materializados;
- transición de `Pago` a `REVERSED`;
- cancelación post-refund ni compensación de stock;
- créditos;
- cierre de casos;
- frontend o bandeja.

Esos límites preservan F7.3+ como incrementos separados y verificables.
