# BH-058 F4 — UI de órdenes y estado PAGADO

Fecha de cierre: 2026-10-29

## Alcance

Se adaptó exclusivamente la interfaz de órdenes al ciclo comercial ya definido
por C1/C2b, D2 y F1:

```text
Orden creada
    ↓
pago pendiente
    ↓ C2b
PAGADO (compromiso de stock aún ACTIVE)
    ↓ F1, actor con gestion.manage_stock
COMPLETADO (entrega y efecto físico D2)
```

No se agregaron estados, endpoints, permisos, pagos ni transiciones de backend.

## Diferencias encontradas

### Gestión operativa

`GestionOrdenes.js` presentaba cuatro incompatibilidades:

1. no reconocía `PAGADO` en filtros, badges ni acciones;
2. mostraba “Confirmar Entrega” para `PENDIENTE`;
3. abría `PagoModal` legacy y, después de registrar un pago, intentaba entregar;
4. actualizaba localmente el estado a `COMPLETADO` sin usar la orden devuelta por
   F1.

Además, `/admin/ordenes` requería sólo autenticación y la navegación no exponía
una entrada gobernada por permiso efectivo.

### Experiencia de cliente

`MisPedidos.js` no mostraba `PAGADO`, no diferenciaba acreditación de entrega y
no permitía recuperar el checkout C1 de una orden pagable. Tampoco actualizaba
periódicamente el listado mientras C2a/C2b procesaban el pago.

## Estados visualizados

La presentación está centralizada en `frontend/src/utils/orderStatus.js`. Los
estados persistidos siguen siendo exactamente los de `OrdenCompra`.

| Estado backend | Presentación |
| --- | --- |
| `PENDIENTE` | Pendiente de pago |
| `ESPERANDO_PAGO` | Pago pendiente |
| `PAGADO` | Pagada, pendiente de entrega |
| `COMPLETADO` | Entregada |
| `RECHAZADO` | Pago rechazado |
| `CANCELADO` | Cancelada |

Si `pagos` contiene `PENDING_RECONCILIATION`, la UI muestra **Pago en revisión**
como presentación derivada y bloquea otro checkout. No se persiste un estado de
orden nuevo.

## Gestión operativa y entrega

La ruta `/admin/ordenes` y su entrada de navegación requieren
`gestion.manage_stock`, obtenido de `/me/` mediante `SessionContext`. No se usa
`is_staff`, nombre de rol ni datos locales legacy.

La acción de entrega:

- sólo aparece para `PAGADO` y con permiso efectivo;
- invoca exclusivamente
  `POST /api/gestion/ordenes-compra/{id}/confirmar_entrega/`;
- no registra pagos ni escribe stock desde frontend;
- bloquea solicitudes duplicadas mediante estado visual y una guarda en memoria;
- reemplaza la fila con `response.data.orden`, sin asumir `COMPLETADO`;
- ante HTTP 403 o 409 muestra el error y vuelve a consultar las órdenes para
  resolver revocaciones o carreras;
- permite reintentar después de que finaliza la solicitud anterior.

F1 permanece como autoridad: vuelve a validar permiso, estado `PAGADO`,
compromisos, movimientos e idempotencia dentro de la transacción.

Se eliminó `PagoModal` del recorrido de entrega. Acreditar dinero y entregar
productos ya no son una única acción de UI.

## Experiencia de cliente

`MisPedidos.js` conserva el endpoint privado existente:

```text
GET /api/gestion/ordenes-compra/
```

El queryset backend sigue limitando a una clienta a sus propias órdenes. La
pantalla no muestra entrega, cancelación operativa, compromisos ni movimientos
de stock.

Para `PENDIENTE` o `ESPERANDO_PAGO` sin pago vigente/revisión, “Continuar al
checkout” usa C1 existente:

```text
POST /api/gestion/ordenes-compra/{id}/checkout/
Idempotency-Key: <clave de la interacción>
{"channel": "ONLINE"}
```

No envía monto y redirige exclusivamente a `checkout_url` de backend. Un
resultado `OUTCOME_UNKNOWN` conserva la clave para retry; la UI no marca la
orden como pagada.

Mientras existen órdenes pagables o pagos en revisión, el listado se actualiza
cada cinco segundos. También se actualiza al recuperar foco y mediante el botón
“Actualizar pedidos”. Por ello el paso a `PAGADO` procede de la consulta segura
posterior a C2b, nunca de la URL de retorno de Mercado Pago.

## Pruebas

### Frontend focalizado

Se agregaron pruebas para:

- presentación de todos los estados y revisión derivada;
- `PAGADO` distinto de `COMPLETADO`;
- entrega sólo desde `PAGADO` y con `gestion.manage_stock`;
- ausencia de acciones de entrega para clientas o actores sin permiso;
- prevención de doble solicitud;
- manejo y resincronización ante 403/409;
- retry después de conflicto;
- checkout ORDER sin monto y usando sólo `checkout_url`;
- retry incierto con la misma clave idempotente;
- refresco desde pago pendiente hasta `PAGADO`;
- navegación y acceso directo por permiso efectivo.

Resultado focalizado: **5 suites, 61 tests OK**.

### Regresiones

Sobre PostgreSQL se ejecutaron F1, D1/D2/D3, C1, C2b, pipeline y concurrencia:

- inventario y movimientos;
- permisos de stock;
- compromisos y entrega de órdenes;
- checkout de proveedor;
- conciliación de órdenes;
- pipeline de eventos.

Resultado backend: **116/116 tests OK**.

Suite frontend completa: **29/29 suites, 226/226 tests OK**.

Controles adicionales:

- `npm run build`: exitoso, con warnings preexistentes fuera de F4;
- `python -X utf8 manage.py check`: sin issues;
- `python -X utf8 manage.py makemigrations --check --dry-run`: sin cambios;
- `git diff --check`: sin errores.

No se realizaron pagos reales.

## Limitaciones pendientes

- Los tiempos y estados reales de Mercado Pago no se validan fuera del sandbox;
  se reutilizan los adaptadores y mocks de C1/C2a/C2b.
- La UI sólo representa revisión cuando el contrato existente la expone mediante
  un `Pago` pendiente de conciliación o `RECHAZADO` en la orden.
- Refunds, créditos, Point/QR, nuevas cancelaciones posteriores al pago y cambios
  de lifecycle permanecen fuera de alcance.

## Archivos F4

- `frontend/src/utils/orderStatus.js` y prueba;
- `frontend/src/pages/admin/GestionOrdenes.js` y prueba;
- `frontend/src/pages/cliente/MisPedidos.js` y prueba;
- `frontend/src/navigation/navigationConfig.js` y prueba;
- `frontend/src/routes/index.js`;
- `frontend/src/routes/ProtectedRoute.test.js`;
- `CORRECCION_BH058_F4_UI_ORDENES.md`.
