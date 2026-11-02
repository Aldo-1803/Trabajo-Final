# BH-058 F7.4 — Ajustes financieros confirmados

**Fecha:** 2026-11-02
**Alcance:** exclusivamente F7.4; no incluye cierre de casos ni efectos
comerciales de F7.5.

## 1. Resultado

F7.4 incorpora un ledger append-only para refunds y contracargos confirmados y
una única proyección financiera:

```text
net_reconciled = gross_reconciled - confirmed_adjustments
```

`refund_pending` se informa por separado y nunca reduce el neto. Una respuesta
HTTP exitosa, `SUBMITTED`, un timeout o una disputa provisional no constituyen
confirmación financiera.

## 2. Modelo `FinancialAdjustment`

Cada ajuste conserva:

- Pago de origen;
- tipo `REFUND`, `CHARGEBACK`, `CORRECTION` o `REVERSAL`;
- efecto `DEBIT` o `CREDIT`, siempre con importe positivo;
- moneda del Pago;
- proveedor e identidad externa;
- estado terminal observado;
- `ProviderEvent` oficial verificado;
- fecha efectiva obtenida de la fila o de la última actualización oficial de
  la Order;
- evidencia sanitaria de Order, transacción y ajuste;
- operación F7.3 correlacionada, cuando existe;
- ajuste revertido, para futuras reversiones verificables.

Restricciones principales:

- unicidad `(provider, adjustment_type, external_adjustment_id)`;
- importe positivo;
- `REFUND` y `CHARGEBACK` sólo reducen neto;
- `REVERSAL` sólo restaura neto y exige un ajuste de origen;
- una operación F7.3 sólo puede respaldar un ajuste;
- relaciones protegidas y creación exclusiva por servicio;
- `save`, `delete`, `update`, `bulk_update`, `bulk_create` y
  `update_or_create` genéricos quedan bloqueados.

No existe CRUD de ajustes. F7.4 no infiere correcciones ni reversiones: el
modelo puede conservarlas, pero sólo un futuro contrato de evidencia oficial
explícito podrá crearlas.

## 3. Autoridad de confirmación

La autoridad mecánica es C2a/C2b:

1. C2a autentica la notificación, consulta la Order fuera de la transacción y
   persiste un snapshot sanitario.
2. C2b vuelve a validar Order, Attempt, referencia externa, importe, moneda y
   proveedor bajo los locks existentes.
3. F7.4 examina `transactions.refunds` y `transactions.chargebacks` del
   snapshot verificado.

Una fila sólo se materializa si reúne conjuntamente:

- estado terminal `processed`;
- ID externo y transacción de origen completos;
- importe positivo y moneda coherente;
- fecha oficial verificable;
- Pago reconciliado o legacy `REVERSED` del mismo Attempt/proveedor;
- saldo suficiente para no superar el Pago.

Para contracargos se aplica deliberadamente el mismo criterio terminal y
completo de la transacción de Order. Estados como `opened`, `in_process` o
cualquier fila sin importe/fecha no reducen el neto y permanecen en revisión.
Esto evita transformar retenciones o disputas provisionales en débitos.

## 4. Correlación con F7.3

Un refund confirmado intenta correlacionarse así:

1. coincidencia exacta por proveedor e ID externo;
2. si F7.3 todavía no conocía el ID, coincidencia única por Pago, transacción,
   importe, moneda y exclusión del baseline previo;
3. cero coincidencias significa refund externo válido sin operación local;
4. varias coincidencias o una identidad incompatible mantienen revisión.

Una operación `PENDING`, `SUBMITTED` o `UNKNOWN` correlacionada pasa a
`CONFIRMED` dentro de la misma transacción que crea el ajuste. Se agrega un
evento inmutable `CONFIRMED`. La ausencia temporal de una fila nunca convierte
`UNKNOWN` en `FAILED`; F7.4 tampoco reenvía refunds.

## 5. Proyección canónica

`financial_adjustment_services.py` es la fuente única para Pago, BOOKING,
ORDER y casos:

- `gross_reconciled`: importe originalmente acreditado;
- `confirmed_adjustments`: débitos confirmados menos créditos/reversiones;
- `net_reconciled`: bruto menos ajustes;
- `refund_pending`: operaciones F7.3 `PENDING`, `SUBMITTED` o `UNKNOWN`;
- subtotales separados de refunds y chargebacks.

Las agregaciones se separan por moneda; no se suman monedas incompatibles. Las
lecturas internas de casos exponen resumen por moneda, proyección por Pago y
evidencia sanitaria de cada ajuste.

### Compatibilidad con `Pago.REVERSED`

El estado se considera parte de la historia del Pago, no un segundo ledger. Un
Pago `REVERSED` conserva su bruto original y el neto sólo descuenta los ajustes
confirmados. Por ello un refund total registrado como ajuste produce neto cero
sin doble resta, y un refund parcial no obliga a cambiar el estado del Pago.

## 6. Concurrencia e idempotencia

La materialización reutiliza el orden de locks de C2b:

- BOOKING: grafo de confirmación, Attempt, Pagos y evento;
- ORDER: Orden, Attempt, Pagos, compromisos y evento;
- luego Pago, operaciones F7.3 e identidad de ajuste.

No hay HTTP dentro de transacciones. La unicidad externa, los locks del Pago y
la validación del acumulado protegen contra:

- evento duplicado y dos workers;
- refund parcial y total concurrentes;
- identidad repetida con otro importe;
- múltiples refunds por encima del bruto;
- confirmación posterior a timeout F7.3;
- refund externo sin operación local;
- snapshots antiguos posteriores a hechos confirmados.

Un evento stale se ignora y nunca elimina ni degrada un ajuste ya confirmado.

## 7. Fronteras preservadas

Registrar un ajuste abre o conserva `POST_PAYMENT_CHANGE`, pero no:

- resuelve ni cierra `PaymentReconciliationCase`;
- cancela Turno u OrdenCompra;
- modifica HOLD o PaymentIntent;
- libera o recrea CompromisoStock;
- consume, repone o emite MovimientoStock;
- aprueba decisiones;
- ejecuta otro refund;
- emite créditos.

Todo efecto comercial y el cierre pertenecen a F7.5.

## 8. Migración y archivos principales

- `bohemiacore/gestion/migrations/0039_financial_adjustments_f7_4.py`;
- `bohemiacore/gestion/financial_adjustment_services.py`;
- `bohemiacore/gestion/models.py`;
- `bohemiacore/gestion/provider_reconciliation_services.py`;
- `bohemiacore/gestion/payment_providers.py`;
- `bohemiacore/gestion/refund_execution_services.py`;
- `bohemiacore/gestion/financial_case_serializers.py`;
- `bohemiacore/gestion/financial_case_views.py`.

## 9. Pruebas

Las pruebas no realizan llamadas reales ni refunds reales. Cubren:

- refunds parciales, múltiples y totales;
- `SUBMITTED` y contracargos provisionales sin efecto;
- contracargo terminal separado del refund;
- identidad repetida incompatible y sobreajuste;
- inmutabilidad;
- neto sin doble resta con `Pago.REVERSED`;
- refund pendiente separado del neto;
- transición `UNKNOWN -> CONFIRMED` por evento verificado;
- refund de Order sin cambios de stock ni estado comercial;
- dos workers sobre la misma identidad;
- refund parcial y total concurrentes en PostgreSQL.

Las regresiones ejecutadas y sus resultados finales se registran en la revisión
del commit de F7.4.

## 10. Pendientes exclusivos de F7.5

- determinar y aplicar el efecto comercial posterior al ajuste;
- cancelar Turno u Orden cuando corresponda;
- liberar o reponer stock mediante sus autoridades;
- verificar completitud financiera/comercial;
- cerrar el caso de conciliación.
