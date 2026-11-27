# BH-058 F6 — Caja presencial operativa

## Alcance

F6 incorpora una interfaz operativa en `/admin/caja` para cobrar obligaciones
existentes mediante efectivo, transferencia con comprobante privado o enlace de
Mercado Pago. No crea una caja física, cuentas contables, arqueos ni cierres.

La autoridad financiera continúa en los servicios ya validados:

- B2 registra efectivo y transferencias, aplica idempotencia, valida importes y
  concilia evidencia;
- B3 confirma la reserva exclusivamente desde backend cuando corresponde;
- C1 crea o reutiliza checkout con canal `IN_PERSON` y no acredita pagos;
- C2a/C2b conserva la autoridad sobre el resultado oficial del proveedor.

No se realizaron cobros reales.

## Obligaciones soportadas

F6 opera inicialmente obligaciones `BOOKING` representadas por
`PaymentIntent`. La interfaz no acepta un total suministrado por frontend ni
crea obligaciones financieras.

Se añadió lectura operativa a `GET /api/gestion/payment-intents/`, sobre el
recurso existente, para que personal autorizado pueda buscar por nombre o
email. La respuesta incluye:

- clienta;
- contexto BOOKING y líneas de servicios;
- total inmutable y moneda;
- monto reconciliado, monto pendiente para confirmar y saldo;
- estado efectivo y tracking;
- métodos manuales habilitados por el snapshot de política;
- soporte de pagos parciales de B2.

El detalle propio de una clienta conserva su contrato de ownership. Una
clienta sin autoridad financiera no puede usar el listado operativo ni leer
pagos de otra clienta.

Las órdenes comerciales no se incorporaron: B2 no expone para ellas un
registro manual canónico equivalente al grafo `PaymentIntent`. F6 no inventa
un endpoint ni una obligación paralela.

## Operaciones disponibles

### Efectivo

La UI envía a B2 únicamente importe, moneda, método `CASH`, propósito derivado
del estado de la obligación y fecha del hecho. El actor se obtiene de la sesión
autenticada.

- el importe debe ser positivo y no superar el saldo mostrado;
- B2 vuelve a verificar moneda, método, vigencia y sobrepago;
- cada intento conserva `Idempotency-Key` y `occurred_at` durante retries;
- un envío exitoso muestra el saldo financiero devuelto por backend;
- la UI no modifica `Turno`, `PaymentIntent` ni estados de pago.

Si se alcanza el umbral, B3 puede ejecutarse dentro del backend. El comando de
frontend rechaza campos extra como `status` o una supuesta confirmación.

### Transferencia

La transferencia usa B2 con `FormData`, método `BANK_TRANSFER`, referencia y
archivo obligatorio.

- subir evidencia crea un pago `PENDING_RECONCILIATION`;
- el archivo no se expone como URL pública;
- la descarga usa JWT contra
  `/api/gestion/payments/{public_id}/receipt/`;
- `gestion.confirm_deposit` habilita aceptar o rechazar;
- rechazar requiere una razón;
- sólo aceptar modifica el monto reconciliado, sujeto a las validaciones B2.

La evidencia subida nunca se presenta como pago acreditado.

### Mercado Pago presencial

La acción llama C1 en
`POST /api/gestion/payment-intents/{public_id}/checkout/` con
`channel: IN_PERSON` e idempotencia estable por obligación.

La UI permite copiar o abrir únicamente `checkout_url` devuelta por backend y
advierte que crear o visitar el enlace no acredita el pago. El estado final se
actualiza desde backend mediante C2a/C2b; F6 no implementa Point ni QR físico.

## Permisos efectivos

La ruta, navegación, panel Operaciones y botones usan capacidades de `/me/`, no
`is_staff` ni nombres de rol:

| Capacidad | Acceso F6 |
|---|---|
| `gestion.register_payment` | leer obligaciones, registrar CASH/transferencia y generar C1 `IN_PERSON` |
| `gestion.confirm_deposit` | leer obligaciones, evidencia privada y conciliar/rechazar transferencias |
| `gestion.view_financial_reports` | lectura de obligaciones, pagos y saldos |

El backend repite todas las autorizaciones. F6 no incorpora acciones de
`gestion.reconcile_external_payment` porque no añade revisión externa.

## UX e idempotencia

- búsqueda y selección explícita de obligación;
- total, reconciliado, saldo, estado, contexto y pagos anteriores visibles;
- actualización manual de estado y saldo desde backend;
- importes acotados por el saldo sin editar el total;
- botones deshabilitados mientras una operación está en curso;
- misma clave y mismo timestamp al reintentar el mismo payload;
- nueva clave cuando cambia el payload;
- errores de dominio, incluidos 403 y 409, visibles sin reinterpretar éxito;
- enlace C1 persistente durante retries y mensaje de resultado incierto.

## Pruebas ejecutadas

### F6 frontend

`CajaPresencial.test.js` cubre:

1. lectura por capacidad y ocultamiento de mutaciones;
2. CASH B2 sin enviar total y saldo actualizado;
3. transferencia multipart pendiente y evidencia privada;
4. conciliación autorizada;
5. descarga autenticada del comprobante;
6. C1 `IN_PERSON`, copia del enlace y ausencia de autoridad financiera;
7. retry 409 con la misma clave y payload;
8. error 403, bloqueo de doble envío y rechazo sin razón.

También se ampliaron pruebas de Operaciones y navegación para las tres
capacidades financieras.

### Backend y regresiones

- B2/C1 focalizados: **31/31 OK**;
- permisos/listado y comandos B2 focalizados finales: **9/9 OK**;
- descubrimiento backend completo, incluidos B1/B2/B3, C1/C2a/C2b, F2, F3,
  permisos y `/me/`: **140/140 OK**;
- suite frontend completa: **30/30 suites, 241/241 tests OK**;
- build de producción: exitoso; sólo warnings preexistentes en archivos ajenos
  a F6;
- `python manage.py check`: sin issues;
- `python manage.py makemigrations --check --dry-run`: sin cambios;
- `python -m compileall -q gestion usuarios`: correcto;
- `git diff --check`: correcto.

## Fuera de alcance preservado

F6 no implementa refunds, créditos, billetera, Point, QR físico, arqueo, cierre
de caja, contabilidad nueva, inventario, estados de `Turno` ni procesos
automáticos. Tampoco altera settings locales, media, `show_urls.py`, Cypress o
auditorías locales.

## Pendientes para F7

F6 no continúa con F7. Quedan para una fase futura, sólo si se especifican sus
contratos:

- definir una obligación canónica para cobros manuales de órdenes, si se desea
  incorporarlas a esta interfaz;
- diseñar una UI separada para revisión externa bajo
  `gestion.reconcile_external_payment`, si el alcance futuro la requiere;
- cualquier resolución financiera posterior a pagos tardíos, refunds o
  créditos.
