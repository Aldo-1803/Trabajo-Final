# BH-058 F7.1 — Consulta segura de incidencias financieras

**Fecha de validación:** 2026-10-29.

## Alcance

F7.1 incorpora exclusivamente lectura operativa de
`PaymentReconciliationCase`. No agrega modelos, migraciones, decisiones,
refunds, cierres ni efectos comerciales.

La superficie resultante permite clasificar los casos existentes por tipo,
contexto, estado, razón y antigüedad sin modificar:

- `PaymentReconciliationCase`;
- `Pago`;
- `PaymentIntent`;
- `Turno`;
- `OrdenCompra`;
- `CompromisoStock`;
- `ProviderPaymentAttempt`;
- `ProviderEvent`.

## API

Endpoints registrados mediante `ReadOnlyModelViewSet`:

```text
GET /api/gestion/payment-reconciliation-cases/
GET /api/gestion/payment-reconciliation-cases/{public_id}/
```

El lookup usa el UUID público del caso. `POST`, `PUT`, `PATCH` y `DELETE` no
tienen acciones registradas y responden `405 Method Not Allowed` para un actor
autorizado.

### Filtros

| Parámetro | Semántica |
|---|---|
| `status` | Estado exacto `OPEN` o `RESOLVED` |
| `type` | Tipo exacto de caso |
| `context` | `BOOKING` u `ORDER` derivado de las relaciones canónicas |
| `created_from` | Fecha/hora ISO-8601 inclusiva desde la creación |
| `created_to` | Fecha/hora ISO-8601 inclusiva hasta la creación |
| `reason` | Coincidencia case-insensitive sobre `reason_code` |
| `ordering` | `created_at`, `-created_at`, `resolved_at` o `-resolved_at` |

El orden predeterminado es `created_at, pk`: casos más antiguos primero. Así la
bandeja prioriza incidencias envejecidas sin calcular ni persistir estados
nuevos.

### Paginación

- tamaño predeterminado: 20;
- selector: `page_size`;
- máximo por página: 100;
- formato DRF estándar: `count`, `next`, `previous`, `results`.

## Clasificación y respuesta

El listado devuelve:

- UUID, tipo, etiqueta, estado y razón;
- contexto BOOKING u ORDER;
- referencia acotada al Intent/HOLD/Turno o a la orden;
- cantidad, total, monedas, estados y UUID de Pagos relacionados;
- referencia sanitaria de Attempt/ProviderEvent;
- fechas y antigüedad en segundos.

Los cinco tipos existentes se presentan sin reinterpretación:

- `LATE_PAYMENT`;
- `BOOKING_CONFIRMATION_FAILED`;
- `EXTERNAL_PAYMENT_REVIEW`;
- `ORDER_FULFILLMENT_FAILED`;
- `POST_PAYMENT_CHANGE`.

El detalle añade representaciones de sólo lectura y allowlisted de:

- Pagos;
- PaymentIntent y SlotHold;
- Turno;
- OrdenCompra;
- ProviderPaymentAttempt;
- ProviderEvent.

No se agrega ningún campo de decisión, resultado de refund o resolución.

## Privacidad

F7.1 no serializa:

- `PaymentReconciliationCase.details` completo;
- `notification_snapshot`, `provider_snapshot` o `business_result`;
- `policy_snapshot`;
- claves idempotentes o fingerprints;
- URL de checkout;
- referencias manuales;
- comprobantes o enlaces de descarga;
- notas internas de la orden;
- tokens, credenciales o datos completos del medio de pago.

Se exponen únicamente referencias financieras y estados necesarios para ubicar
la incidencia. No se incorporó PII adicional de la clienta a esta API.

## Autorización

La API exige simultáneamente:

```text
usuario autenticado
+ cuenta activa
+ user.has_perm('gestion.reconcile_external_payment')
```

La comprobación vive en `CanReconcileExternalPayment`. No usa `is_staff`,
`BusinessRole`, nombres de grupo ni `Personal.rol` como autoridad directa.

Consecuencias verificadas:

- permiso individual efectivo: acceso permitido;
- `is_staff=True` sin permiso: `403`;
- clienta autenticada sin permiso: `403`;
- cuenta inactiva aun con permiso asignado: `403`;
- petición no autenticada: `401`.

## Auditoría e inmutabilidad

La consulta no crea eventos de `Auditoria`: una lectura no se presenta como
transición financiera. Los access logs de infraestructura siguen siendo una
responsabilidad operativa separada.

Se conserva la inmutabilidad existente del caso y de sus relaciones. Las
pruebas comparan antes y después:

- cantidad y estado de casos;
- estado e importe del Pago;
- estado de PaymentIntent, Turno y OrdenCompra;
- estado de Attempt y ProviderEvent;
- cantidad de auditorías.

GET no cambia ninguno de esos valores y los métodos genéricos de escritura
permanecen cerrados.

## Consultas y rendimiento

El queryset usa `select_related` para contexto, Attempt y Event, y
`prefetch_related` para Pagos. No modifica el conciliador ni duplica sus modelos
o reglas. El índice existente `(status, -created_at)` continúa siendo útil para
la bandeja de casos abiertos.

## Pruebas

### F7.1 focalizado

```text
python -X utf8 manage.py test \
  gestion.tests.test_financial_case_read_api \
  --noinput

Ran 8 tests
OK
```

Cobertura:

1. listado autorizado, paginado y más antiguo primero;
2. detalle BOOKING y ORDER;
3. permiso individual, staff sin permiso, clienta e inactivo;
4. filtros de estado, tipo, contexto, fechas y razón;
5. las cinco clasificaciones existentes;
6. paginación configurable y acotada;
7. exclusión de snapshots, secretos y comprobantes;
8. ausencia de mutaciones y métodos de escritura `405`.

### Regresiones C2b, F5 y F6 backend

```text
python -X utf8 manage.py test \
  gestion.tests.test_financial_case_read_api \
  gestion.tests.test_provider_reconciliation \
  gestion.tests.test_provider_reconciliation_concurrency \
  gestion.tests.test_order_inventory \
  gestion.tests.test_order_inventory_concurrency \
  gestion.tests.test_manual_payments \
  gestion.tests.test_provider_checkout \
  --noinput

Ran 106 tests
OK
```

### Regresión F6 frontend

```text
npm test -- --watchAll=false --runInBand \
  src/pages/admin/CajaPresencial.test.js

1 suite, 8 tests
PASS
```

### Controles estructurales

- `python -X utf8 manage.py check`: sin issues;
- `python -X utf8 manage.py makemigrations --check --dry-run`: sin cambios;
- `python -m compileall -q gestion usuarios`: correcto;
- F7.1 no requiere migración de esquema.

## Archivos F7.1

- `bohemiacore/gestion/financial_case_filters.py`;
- `bohemiacore/gestion/financial_case_serializers.py`;
- `bohemiacore/gestion/financial_case_views.py`;
- `bohemiacore/gestion/permissions.py`;
- `bohemiacore/gestion/urls.py`;
- `bohemiacore/gestion/tests/test_financial_case_read_api.py`;
- `IMPLEMENTACION_BH058_F7_1_CONSULTA_CASOS.md`.

## Limitaciones preservadas

F7.1 no incluye:

- interfaz frontend para la bandeja;
- asignación de responsables;
- solicitud o decisión de resolución;
- cierre de casos;
- ejecución o confirmación de refunds;
- ajustes financieros;
- cambios comerciales o de stock;
- auditoría específica de accesos de lectura;
- búsqueda por PII de clientas.

Estas capacidades pertenecen a incrementos posteriores. En particular, F7.1
no continúa con F7.2.

## Resultado

Los casos existentes pueden consultarse y clasificarse de forma paginada,
privada e inmutable únicamente con el permiso financiero efectivo. Los contratos
de C2b, F5 y F6 permanecen sin cambios.
