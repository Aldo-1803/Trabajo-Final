# BH-058 F7.5 — Efectos comerciales y cierre financiero verificable

## 1. Alcance

F7.5 coordina únicamente efectos comerciales derivados de resoluciones F7.2 ya
decididas y hechos financieros F7.3/F7.4 ya confirmados. No ejecuta refunds, no
consulta proveedores y no implementa F7.6.

La autoridad nueva es `close_financial_case()`, expuesta por
`POST /api/payment-reconciliation-cases/{public_id}/close-financial-case/`.
Exige una cuenta activa con `gestion.reconcile_external_payment`, fundamento,
resultado final e `Idempotency-Key`.

## 2. Hecho de cierre

`FinancialCaseClosure` es un registro inmutable y uno-a-uno con
`PaymentReconciliationCase`. Conserva:

- decisión final;
- actor, fecha, fundamento y resultado;
- efecto comercial aplicado o preservado;
- fingerprint e identidad idempotente;
- referencias a Pagos, operación, ajustes, orden, compromisos y movimientos.

El cierre también agrega el evento append-only `CASE_CLOSED`, una auditoría
`FINANCIAL_CASE_CLOSED` y cambia conjuntamente el caso de `OPEN` a `RESOLVED`
con `resolved_at`. La relación de eventos con la decisión pasó a `ForeignKey`
porque una misma decisión necesita su evento de decisión y su evento de cierre.

## 3. Requisitos verificables de cierre

Dentro de una única transacción se exige:

1. caso actualmente `OPEN`;
2. solicitud `DECIDED` y una única decisión final F7.2;
3. auditoría semántica de la decisión;
4. resultado compatible con la acción decidida;
5. ausencia de operaciones `PENDING`, `SUBMITTED` o `UNKNOWN` en el contexto;
6. para un refund aprobado, operación `CONFIRMED`, evento de confirmación y un
   único `FinancialAdjustment.REFUND` correlacionado;
7. coincidencia de importe, moneda, Pago, Attempt, Order externa y transacción;
8. ausencia de ajustes no contemplados materializados después de la decisión;
9. ausencia de `ProviderEvent` verificados todavía `NOT_EVALUATED` en el
   contexto completo;
10. estado comercial, compromisos y movimientos compatibles con el resultado.

Un retry idéntico devuelve el mismo cierre sin repetir efectos. Una clave usada
con otro payload/caso o dos cierres diferentes producen conflicto. Un fallo en
la auditoría o en cualquier verificación revierte cierre, estado y stock.

## 4. BOOKING

| Escenario | Efecto permitido |
|---|---|
| Turno cancelado + refund confirmado total o parcial | El Turno sigue `CANCELADO`; se conserva Intent/Pago; no se crea HOLD ni Turno. |
| Refund denegado | Se conserva la denegación fundada; no se inventa un ajuste. |
| Pago tardío | Intent sin Turno confirmado y HOLD no activo; no se ejecuta B3 ni se crea una reserva. |
| Otros casos | Se preserva el historial BOOKING sin mutación comercial implícita. |

F7.5 nunca reactiva un HOLD, reprograma, crea créditos ni modifica Pagos.

## 5. ORDER y stock

### Refund total con cancelación explícita

Una orden no entregada sólo cambia de `PAGADO` a `CANCELADO` si concurren:

- resultado solicitado `CANCEL_AND_REFUND`;
- decisión `APPROVE_REFUND`;
- autorizado igual al bruto conciliado y al total de la orden;
- refunds confirmados iguales al bruto y neto conciliado cero;
- compromisos exclusivamente `ACTIVE`;
- ausencia de movimientos físicos de la orden.

La transición usa `release_order_after_confirmed_financial_resolution()`, que
delega en la autoridad canónica de compromisos. Cada compromiso pasa una vez de
`ACTIVE` a `RELEASED`; `stock_real` no cambia y no se crea
`MovimientoStock.ORDER_SALE_OUT`. La cancelación ordinaria F5 continúa
rechazando órdenes pagadas.

### Otros resultados

- Refund parcial: orden `PAGADO` y compromisos `ACTIVE`; no libera stock.
- Orden `COMPLETADO`: mantiene `COMPLETADO`, compromisos `CONSUMED`, stock real y
  movimientos; el retorno físico queda diferido.
- Contracargo: se reconoce como ajuste, pero no cancela automáticamente.
- Disputa provisional: no se trata como débito confirmado.

## 6. Bloqueo de entrega

`apply_order_inventory_effect()` revalida bajo lock antes de consumir stock:

- cualquier caso financiero `OPEN` de la orden bloquea la entrega;
- un saldo de ajustes confirmado con débitos superiores a créditos continúa
  bloqueando aunque el caso de revisión haya sido cerrado;
- una disputa provisional sin débito deja de bloquear sólo después de una
  resolución coherente.

Este control está en el servicio de dominio y también alcanza aliases legacy de
entrega; no depende de UI. El bloqueo no cambia el estado de la orden.

Si llega una nueva incidencia externa después de cerrar un caso, C2b abre un
nuevo caso en vez de reutilizar el caso `RESOLVED` anterior.

## 7. Locks y concurrencia

Se conserva el orden global existente:

- BOOKING: solicitud técnica → HOLD → Intent → Cliente → Pagos → caso;
- ORDER: OrdenCompra → Pagos/ajustes → caso/decisión → compromisos/movimientos;
- entrega, conciliación y cierre toman primero la OrdenCompra, por lo que las
  carreras se serializan sin una entrega y liberación simultáneas.

No hay HTTP dentro de `transaction.atomic()`. El servicio sólo lee hechos
externos ya persistidos por C2/F7.4.

## 8. API y permisos

El comando acepta exclusivamente:

```json
{
  "rationale": "Fundamento verificable",
  "result": "REFUND_CONFIRMED"
}
```

Resultados admitidos: `REFUND_CONFIRMED`, `REFUND_DENIED`,
`NO_FINANCIAL_CHANGE`, `EXTERNAL_ADJUSTMENT_ACKNOWLEDGED` y
`PHYSICAL_RETURN_DEFERRED`. El detalle interno del caso proyecta el cierre, pero
no expone claves idempotentes ni fingerprints.

Una clienta, un `is_staff` sin permiso o una cuenta inactiva reciben denegación
tanto en API como en dominio.

## 9. Migración

`0040_financial_case_closure_f7_5.py`:

- crea `FinancialCaseClosure` y su unicidad idempotente por actor;
- agrega `CASE_CLOSED` al evento financiero;
- permite múltiples eventos append-only por decisión.

No hay migración de datos destructiva ni edición de Pago, ajustes o eventos
históricos.

## 10. Pruebas ejecutadas

### F7.5 focalizado — PostgreSQL

`gestion.tests.test_financial_case_closure`: **18/18 OK**.

Cobertura:

- Turno cancelado con refund confirmado total y parcial;
- denegación fundada y pago tardío sin resurrección;
- ORDER total, parcial y completada;
- liberación única y ausencia de salida física al cancelar;
- contracargo confirmado y disputa provisional;
- operaciones `PENDING`, `SUBMITTED` y `UNKNOWN`;
- divergencias de importe y moneda;
- evento verificado sin evaluar;
- nueva incidencia posterior al cierre que abre un caso nuevo;
- API, idempotencia, actor inactivo, clienta y staff sin permiso;
- cierre duplicado, dos operadores y carrera cierre/entrega/conciliación.

### Regresiones obligatorias

F1, F2, F5 y F7.1–F7.4: **132/132 OK** sobre PostgreSQL real, incluyendo sus
suites de concurrencia.

Controles estructurales ejecutados:

- `manage.py check`;
- `makemigrations --check --dry-run`;
- migración desde esquema F7.4;
- `compileall gestion`;
- `git diff --check`.

## 11. Diferidos explícitos

Permanecen fuera de F7.5:

- nuevos refunds o reintentos de resultados ambiguos;
- créditos, rebooking y promociones;
- devolución física y reposición de órdenes completadas;
- política automática para refund parcial;
- ajustes manuales arbitrarios;
- interfaz/bandeja F7.6 y validación sandbox.
