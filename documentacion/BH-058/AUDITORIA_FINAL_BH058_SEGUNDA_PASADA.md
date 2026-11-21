# AUDITORÍA FINAL BH-058 — SEGUNDA PASADA

**Fecha:** 2026-10-29<br>
**Baseline auditado:** `7bd95df7917e2217e8ef6f0000c2266a869317d8`<br>
**Rama:** `save/work-in-progress`<br>
**Tipo de revisión:** inspección y pruebas sin modificar código, migraciones ni configuración y sin efectuar cobros reales<br>
**Veredicto:** **BH-058 = BLOQUEADO PARA CIERRE**

## 1. Resumen ejecutivo

La segunda pasada confirma que los cuatro incrementos correctivos publicados
después de la primera auditoría están implementados y funcionan en la matriz
automatizada local:

- **F1:** la entrega exige `gestion.manage_stock`, una orden `PAGADO` y
  compromisos coherentes; el retry no duplica la salida física.
- **F2:** el worker ejecuta C2a y C2b en un pipeline recuperable, con claims,
  retries, recuperación stale y exclusión entre workers.
- **F3:** la clienta puede continuar desde una solicitud técnica aprobada hasta
  HOLD, PaymentIntent, checkout y seguimiento autoritativo del backend.
- **F4:** la UI distingue `PAGADO` de `COMPLETADO`, recupera checkout y sólo
  ofrece entrega a quien tiene el permiso efectivo.

La ejecución propia de esta auditoría obtuvo **411/411 pruebas backend** y
**226/226 pruebas frontend**, además de build exitoso y migraciones coherentes.

Sin embargo, el cierre integral de BH-058 continúa bloqueado. No se trata sólo
de una validación dependiente del entorno real:

1. **La caja presencial B2/C1 sigue sin interfaz operativa canónica.** No hay
   pantalla para registrar CASH, transferencia con evidencia privada, generar
   link `IN_PERSON`, consultar saldo del Intent ni aceptar/rechazar una
   conciliación. `PagoModal` e `HistorialPagos` no constituyen ese reemplazo.
2. **Una clienta propietaria todavía puede cancelar por API su `OrdenCompra`,
   incluso en `PAGADO`.** `OrdenCompraViewSet.cancelar` sólo aplica ownership y
   `release_order_stock_commitments` no restringe el estado pagado. El resultado
   libera el compromiso y deja el dinero sin caso financiero, actor ni política
   de resolución semántica.
3. **Las cancelaciones con dinero, refunds y chargebacks no tienen resolución
   comercial completa.** C2b detecta y abre casos, pero no hay compensación ni
   bandeja operativa para decidir refund, retención u otra obligación.
4. **La preparación productiva no está acreditada.** Existe una receta systemd
   versionada, pero no evidencia de instalación/actividad del servicio; no se
   ejecutó sandbox, continúan seis warnings de `check --deploy`,
   `ALLOWED_HOSTS=['*']` y múltiples URLs frontend de localhost. En particular,
   `Carrito.js` conserva el inicio de checkout ORDER contra
   `http://127.0.0.1:8000`, lo que impide considerar probado el recorrido en un
   despliegue web real sin una corrección/configuración adicional.

Por lo tanto:

- **cierre de implementación F1–F4:** apto;
- **validación Mercado Pago sandbox:** no realizada;
- **autorización para operar en producción:** no otorgable;
- **cierre formal integral BH-058:** bloqueado.

## 2. Alcance y método

Se contrastaron la auditoría original, los informes F1–F4, el código publicado y
las pruebas ejecutables. Un documento marcado `VALIDADO` se usó sólo como índice;
ninguna conclusión depende exclusivamente de ese texto.

Se inspeccionaron directamente:

- servicios de HOLD, PaymentIntent, pagos manuales, confirmación B3, checkout,
  webhook, verificación y conciliación;
- pipeline y comando `process_provider_events`;
- servicios de inventario, compromisos y entrega;
- APIs, serializers, permisos, ownership y auditorías;
- frontend de BOOKING, retornos, carrito, pedidos y órdenes;
- procesos legacy CU-11, CU-27 y CU-35;
- configuración, receta systemd, dependencias y migraciones.

No se inspeccionaron valores del `.env` local. Se verificó que está ignorado por
Git. El escaneo de archivos versionados no encontró credenciales concretas; la
única coincidencia con formato Mercado Pago fue el placeholder
`APP_USR-reemplazar` de `.env.example`.

## 3. Reconciliación de hallazgos de la auditoría original

| Hallazgo original | Condición que fallaba | Corrección/evidencia actual | Prueba específica | Resultado actual | Riesgo residual |
|---|---|---|---|---|---|
| P0: C2a no encadenaba C2b | El comando dejaba eventos en `VERIFIED` | `process_provider_event_pipeline` ejecuta verificación y `process_verified_provider_events`; el comando invoca el pipeline completo | `test_received_event_is_verified_and_reconciled_in_same_cycle`, `test_management_command_runs_complete_pipeline_once`, interrupciones y doble worker | **RESUELTO EN CÓDIGO Y PRUEBAS** | El servicio systemd real no fue acreditado; sin proceso activo, el código no procesa eventos productivos. |
| P0: entrega no autorizada o impaga | Cliente propietaria podía consumir stock; el dominio no exigía pago | `apply_order_inventory_effect` llama `_require_delivery_authority`, exige `PAGADO`, locks y compromisos completos; endpoints legacy delegan al mismo efecto | Cliente 403, personal sin permiso 403, impaga 409, pagada 200, retry y carreras | **RESUELTO PARA ENTREGA** | La cancelación de orden conserva una brecha separada; no permite salida física, pero sí libera compromiso con dinero ya acreditado. |
| P1: BOOKING se detenía en HOLD | No había Intent/checkout/seguimiento en frontend | `BookingPaymentFlow`, opciones calculadas por backend, persistencia de Intent, polling y `RetornoMercadoPago` autoritativo | Suites `BookingPaymentFlow`, `SolicitudesTecnicas`, `RetornoMercadoPago` y `test_booking_frontend_api` | **RESUELTO EN IMPLEMENTACIÓN LOCAL** | Sin sandbox real; no hay cancelación explícita de Intent en UI después de crearlo, aunque el cierre de página no acredita y el vencimiento libera de forma autoritativa. |
| P1: UI de orden incompatible con `PAGADO` | Mezclaba pago y entrega mediante `PagoModal` | `GestionOrdenes`, `MisPedidos` y `orderStatus` separan pago/entrega y usan endpoints C1/F1 | Estados, ownership, permiso, 403/409, retry, refresh y checkout idempotente | **RESUELTO EN F4** | Inicio original desde `Carrito.js` mantiene URL absoluta de desarrollo; despliegue real no verificado. |
| P1: caja presencial incompleta | B2/C1 existían sólo en backend | Servicios y endpoints siguen sólidos, con permisos separados y recibos privados | CASH, transferencia, aceptación/rechazo, saldo, `IN_PERSON` y reportes pasan | **NO RESUELTO EN UI** | No existe herramienta operativa canónica para el salón. |
| P1: cancelación con dinero sin política | Cancelar Turno/orden no resolvía la obligación financiera | No se añadió política general ni acción de resolución | Inspección de servicios y APIs; C2b prueba detección de refund sin reversión | **NO RESUELTO** | Orden pagada puede quedar cancelada y sin compromiso, conservando un pago sin caso; Turno cancelado tampoco resuelve el dinero automáticamente. |
| P1: worker/despliegue/sandbox | No había consumidor C2b ni mecanismo versionado | F2 agrega `--watch` y `deploy/systemd/bohemia-provider-events.service` | Comando de un ciclo y pipeline probados | **PARCIALMENTE RESUELTO** | Receta no equivale a servicio instalado; no hay evidencia de `systemctl`, logs productivos, alertas ni sandbox. |
| P1: frontend rojo y sin pruebas críticas | 2 suites y 3 tests fallaban; F3/F4 sin cobertura | Se agregaron suites de BOOKING, retorno y órdenes; regresiones anteriores fueron reparadas | Suite completa: 29/29, 226/226 | **RESUELTO PARA UNIT/INTEGRATION FRONTEND** | Cypress permanece local no versionado y no se ejecutó; no existe E2E de navegador publicado para BOOKING/ORDER. |
| P2: configuración insegura | Seis warnings, host abierto y defaults de desarrollo | Sin corrección posterior en el baseline | `check --deploy` repite seis warnings | **NO RESUELTO** | Bloquea autorización productiva, no la validez de servicios de dominio. |
| P2: dependencias y portabilidad | Sólo manifiesto de pagos; logs con emoji rompían CP1252 | Sin cambios relevantes | `pip check` y tests con `python -X utf8` | **NO RESUELTO / NO REGRESIÓN** | Entorno instalado es consistente, pero no reproducible desde un manifiesto Python completo; salida de señales sigue siendo excesiva. |
| P2: automatizaciones legacy sin evidencia | CU-11/CU-27/CU-35 no estaban claramente verificadas | CU-27 sí tiene servicio/UI/tests; CU-11 y CU-35 siguen sin suites dedicadas | Inspección y matriz CU-27 incluida | **CU-27 VERIFICADO; CU-11/CU-35 NO VERIFICADOS** | Riesgos legacy detallados en la sección 7; no fueron introducidos por F1–F4. |

## 4. Matriz de cierre F1–F4

| Bloque | Contrato verificado | Evidencia de implementación | Evidencia ejecutada | Estado |
|---|---|---|---|---|
| **F1** | Sólo actor activo con `gestion.manage_stock`; orden `PAGADO`; compromisos coherentes; una salida física | `order_inventory_services.py`, `OrdenCompraViewSet.confirmar_entrega` y aliases de `OrdenPendiente` | `test_order_inventory`, concurrencia y reconciliación ORDER | **CERRADO EN CÓDIGO/PRUEBAS** |
| **F2** | Inbox durable → C2a → C2b; interrupción recuperable; stale claims; doble worker sin duplicado | `provider_event_pipeline.py`, comando `process_provider_events --watch`, unidad systemd | Pipeline normal, interrupción antes/después de commit, stale, duplicados, ORDER y BOOKING | **CERRADO EN CÓDIGO/PRUEBAS; DESPLIEGUE NO ACREDITADO** |
| **F3** | Solicitud → HOLD → Intent → checkout → evento → Pago → Turno, con seguimiento backend | `SolicitudesTecnicas`, `BookingPaymentFlow`, `RetornoMercadoPago`, API de lectura segura | Seña, full, vencimiento, reanudación, retorno, tardío y revisión | **CERRADO EN CÓDIGO/PRUEBAS; SANDBOX NO ACREDITADO** |
| **F4** | Orden → compromiso → checkout → `PAGADO` → entrega → `COMPLETADO` | `GestionOrdenes`, `MisPedidos`, `orderStatus`, C1/C2b/F1/D2 | Estados, permiso, 403/409, retry, no salida antes de entrega y movimiento único | **CERRADO EN CÓDIGO/PRUEBAS; DESPLIEGUE WEB NO ACREDITADO** |

## 5. Recorridos funcionales verificados

### 5.1 BOOKING

Recorrido implementado:

```text
Solicitud técnica
→ evaluación y aprobación
→ SlotHold
→ PaymentIntent DEPOSIT o FULL
→ checkout Mercado Pago
→ ProviderEvent durable
→ verificación C2a
→ Pago + conciliación C2b
→ B3
→ Turno confirmado
```

| Caso | Evidencia | Resultado |
|---|---|---|
| Seña | Policy/Intent, C2b y B3 alcanzan umbral y crean un Turno | **PROBADO** |
| Pago total | Intent `FULL`, pago total, saldo cero y un Turno | **PROBADO** |
| Temporizador | Countdown frontend; vigencia revalidada con reloj de base en cada operación | **PROBADO**; la UI no es autoridad |
| Abandono antes del Intent | Botón libera HOLD mediante endpoint semántico | **PROBADO EN FRONTEND/BACKEND** |
| Abandono cerrando página | No acredita nada; HOLD/Intent vencen según backend y pueden materializarse al reconsultar | **PROBADO EN SERVICIOS**; sin E2E de cierre de navegador |
| HOLD vencido | Bloquea checkout, no crea Turno y ofrece volver a disponibilidad | **PROBADO** |
| Reanudación | Lista privada de HOLD, `existing_intent`, checkout persistido e idempotencia | **PROBADO** |
| Retorno `success/pending/failure` | Mensaje informativo y GET al Intent; no confía en query/URL | **PROBADO** |
| Pago tardío | Preserva Pago, expira obligación, no crea Turno y abre `LATE_PAYMENT` | **PROBADO** |
| Caso de conciliación | UI distingue `ADMIN_REVIEW`/`PAID_WITHOUT_BOOKING`; backend preserva evidencia | **PROBADO** |
| Sandbox Mercado Pago | No se usaron credenciales de prueba ni endpoint externo | **NO VERIFICADO** |

### 5.2 ORDER

Recorrido implementado:

```text
Carrito
→ OrdenCompra + CompromisoStock ACTIVE
→ checkout
→ ProviderEvent / C2a / C2b
→ Pago RECONCILED + orden PAGADO
→ entrega autorizada F1
→ movimiento ORDER_SALE_OUT
→ compromiso CONSUMED + orden COMPLETADO
```

Confirmaciones:

- la clienta sólo consulta sus órdenes y ve pendiente, revisión, pagada y
  entregada como estados diferentes;
- puede recuperar checkout con clave idempotente y no envía el monto desde UI;
- no se expone entrega a la clienta y el backend devuelve 403 aunque fuerce la
  llamada;
- una orden impaga devuelve 409 al actor autorizado;
- C2b deja la orden `PAGADO`, compromiso `ACTIVE`, `stock_real` intacto y cero
  `ORDER_SALE_OUT`;
- F1 consume después un único compromiso/movimiento y el retry es idempotente;
- aliases legacy de entrega pasan por la misma autoridad;
- el checkout online no depende de WhatsApp.

Riesgos que impiden declarar el recorrido productivo:

- `Carrito.js` conserva la URL absoluta `http://127.0.0.1:8000` para iniciar el
  checkout; F4 usa URLs relativas, pero no reemplaza ese punto de entrada;
- una propietaria puede llamar `POST /ordenes-compra/{id}/cancelar/` sobre una
  orden pagada. La UI no muestra el botón, pero ocultarlo no es autorización;
- no se ejecutó sandbox ni despliegue web real.

## 6. Cobros presenciales

| Capacidad | Backend | Autorización/trazabilidad | Pantalla operativa | Resultado |
|---|---|---|---|---|
| CASH | Nace `RECONCILED`, puede alcanzar umbral y confirmar Turno | `register_payment`, actor y auditoría; idempotencia | **No existe caja B2** | Backend probado / operación incompleta |
| Transferencia | Nace `PENDING_RECONCILIATION`; exige referencia, MIME, tamaño, hash y recibo privado | Registrar y conciliar son permisos separados; aceptar/rechazar es idempotente | **No existe registro/conciliación canónica** | Backend probado / operación incompleta |
| Link Mercado Pago en salón | C1 admite canal `IN_PERSON` y usa la misma conciliación | Requiere permiso exacto; rol o `is_staff` no alcanzan | **No existe generador de link** | Backend probado / sandbox y UI pendientes |
| Saldos | Snapshot deriva pagado, umbral, saldo y propósito `BALANCE` | Pago posterior se vincula sin duplicar Turno | **No existe pantalla de saldo del Intent** | Backend probado / UI pendiente |
| Conciliación | Endpoint semántico aceptar/rechazar | Auditoría y permisos separados | **No existe bandeja** | Backend probado / UI pendiente |
| Evidencia privada | Storage sin URL pública y descarga con autorización | Stranger obtiene 404 | **No existe visor canónico del flujo B2** | Backend probado / UI pendiente |
| Reporte | `PagoViewSet` lista por permiso y resume por estado/método | `physical_cash_balance` es deliberadamente `null` | `HistorialPagos` es lectura/reporte legacy | No sustituye una caja física |

`PagoModal.js` continúa siendo legacy: para Turnos no consume B2 y para órdenes
usa `registrar_pago` legacy. F4 lo quitó correctamente de la entrega de órdenes,
pero no creó una caja presencial alternativa.

## 7. Procesos automatizados originales

### 7.1 CU-11 — rutina inicial automática

**Clasificación: SIN COBERTURA DEDICADA / FUNCIONAMIENTO NO DEMOSTRADO.**

Existe `automatizacion_post_servicio`, receptor `post_save` de `Turno`. Cuando el
estado es `realizado`, busca `rutina_recomendada` y usa `get_or_create` para una
`RutinaCliente`.

Riesgos observados:

- no detecta la transición de estado; se ejecuta en cada `save` posterior de un
  Turno que permanezca `realizado`;
- no hay constraint única para `(cliente, rutina_original)`, por lo que
  `get_or_create` no garantiza exclusión concurrente;
- usa `version_asignada=1` y no copia `archivo`, mientras
  `Rutina.asignar_a_cliente` sí usa archivo y versión vigentes;
- la copia de pasos está comentada;
- otros receivers del mismo evento generan agenda/notificaciones sin claves de
  idempotencia, pudiendo duplicar efectos al volver a guardar.

No se localizó una prueba específica del signal. Son defectos/riesgos legacy
preexistentes; no hay evidencia de regresión introducida por BH-058.

### 7.2 CU-27 — asistente de reprogramación

**Clasificación: PROBADO Y FUNCIONAL EN EL ENTORNO LOCAL.**

La UI `TurnoSemanticActions` consulta disponibilidad canónica, excluye el turno
actual, solicita motivo y llama al endpoint dedicado. El backend:

- exige `gestion.reprogram_any_turno` para operación administrativa;
- conserva endpoints propios con ownership y política para la clienta;
- bloquea Turno, Cliente, servicios, Personal y recursos relevantes;
- valida estado, ventana, límite de cambios, skill, agenda, equipamiento,
  duración total, slot ocupado y duplicado del cliente;
- registra actor, motivo y snapshots en `TURN_RESCHEDULED`;
- revierte toda la operación si falla la auditoría;
- serializa la carrera entre reprogramación y HOLD.

Las pruebas backend y frontend correspondientes están incluidas en la matriz
verde. Riesgo residual: la UI usa una URL absoluta de localhost, por lo que su
despliegue sigue dependiendo de corregir/configurar el host.

### 7.3 CU-35 — promociones automáticas

**Clasificación: SIN COBERTURA DEDICADA / FUNCIONAMIENTO NO DEMOSTRADO.**

Hay tres mecanismos distintos:

1. signal de `Producto` que crea sugerencias de combo;
2. acción `promociones/escanear-huecos` que crea `LAST_MINUTE` y puede invocarse
   manualmente desde `AlertasCriticas`;
3. comando `procesar_promos` que envía notificaciones programadas.

No se localizaron tests para esos efectos ni scheduler versionado para el
comando. La acción de huecos es manual, no un proceso automático desplegado. El
comando tampoco tiene claim/lock: dos ejecuciones simultáneas podrían notificar
antes de que `procesada` quede guardado, y presupone que
`cliente_especifico` no es nulo aunque el modelo permite nulo.

Son brechas legacy preexistentes, ajenas a F1–F4; no se consideran regresión de
BH-058, pero tampoco se declaran funcionales.

## 8. Integridad, seguridad y despliegue

### 8.1 Ownership y permisos

Validado:

- HOLD, Intent y sus opciones son privados para la propietaria;
- pagos propios se consultan sin exponer la clave idempotente;
- registrar, conciliar, reportar y revisar pagos son capacidades separadas;
- `is_staff` o un nombre de rol no reemplazan permisos efectivos;
- comprobantes privados devuelven 404 a un tercero;
- la entrega exige `gestion.manage_stock` tanto en API como en dominio;
- la UI administrativa de órdenes y su ruta también exigen ese permiso.

Pendiente bloqueante:

- `OrdenCompraViewSet.cancelar` conserva sólo `IsAuthenticated`; ownership
  autoriza a la propietaria a cancelar. El servicio no recibe actor ni comprueba
  `PAGADO`, y no crea auditoría/caso financiero específico.

### 8.2 Idempotencia y locks

La matriz confirma claves idempotentes, constraints, `select_for_update` y
orden estable de locks en HOLD, Intent, pagos, eventos, reconciliación,
compromisos y stock. Se probaron doble worker, doble evento, doble pago, doble
entrega y carreras de última unidad.

No se extrapola esa garantía a CU-11/CU-35, cuyos procesos legacy no tienen la
misma disciplina.

### 8.3 Auditoría

Los hechos financieros, reconciliación externa, creación/aprobación de Intent,
consumo de HOLD, movimientos y reprogramación tienen auditorías semánticas e
idempotentes en sus pruebas. La cancelación de orden descrita arriba no tiene un
contrato financiero/auditable equivalente.

### 8.4 Secretos y configuración

- No se encontraron secretos concretos versionados.
- `.env` está ignorado y no se leyeron sus valores.
- Mercado Pago se configura por entorno y el adapter rechaza moneda/URLs/token
  inválidos.
- `check --deploy` mantiene **6 warnings**: HSTS, redirect HTTPS, fallback
  inseguro de `SECRET_KEY`, cookies de sesión/CSRF no secure y `DEBUG=True`.
- `ALLOWED_HOSTS=['*']` permanece abierto.
- Persisten numerosas URLs absolutas de `localhost`/`127.0.0.1` en frontend y
  retornos legacy.

### 8.5 Migraciones y dependencias

- `makemigrations --check --dry-run`: sin cambios.
- `migrate --check`: código de salida 0; no hay migraciones pendientes en la
  base local configurada.
- Las dos ejecuciones backend exitosas crearon y destruyeron bases PostgreSQL de
  prueba, validando la aplicación desde vacío por el test runner.
- `pip check`: sin dependencias rotas en el entorno instalado, con warning por
  una distribución local inválida `~jango`.
- Sólo está versionado `requirements-payments.txt`; no existe manifiesto o lock
  Python base completo. La instalación no es reproducible sólo desde el repo.

### 8.6 Worker y sandbox

La receta `deploy/systemd/bohemia-provider-events.service` ejecuta:

```text
python -X utf8 manage.py process_provider_events --watch
```

También están documentados `daemon-reload`, `enable --now`, `status`, journal y
reinicio. Eso prueba que existe un procedimiento versionado, no que se haya
aplicado. Esta auditoría se ejecutó en Windows y no dispone de evidencia externa
de unidad instalada, worker activo, backlog, métricas o alertas productivas.

**Sandbox no fue ejecutado.** Todos los adapters externos se probaron con mocks.
No se realizaron cobros reales ni de prueba.

## 9. Evidencia de pruebas de esta segunda pasada

### 9.1 Backend PostgreSQL

| Bloque ejecutado | Casos | Fallos | Tiempo | Resultado |
|---|---:|---:|---:|---|
| HOLD, consumo, Intent, B2/B3, C1/C2a/C2b, pipeline F2, inventario, F1/F4, CU-27 y concurrencia | 293 | 0 | 973.569 s | **OK** |
| Diagnóstico, riesgo y solicitud/evaluación técnica previa al HOLD | 118 | 0 | 141.902 s | **OK** |
| **Total** | **411** | **0** | **1115.471 s** | **OK** |

La primera ejecución del bloque de 293 fue interrumpida por un reinicio del
servidor y no se cuenta como evidencia. El resultado informado corresponde a la
repetición completa que terminó en `OK` y destruyó su base de pruebas.

Suites relevantes incluidas:

- `test_slot_holds*` y consumo/concurrencia;
- `test_payment_intents*`, `test_manual_payments*` y confirmación;
- `test_payment_providers`, checkout, eventos, conciliación y pipeline;
- `test_booking_frontend_api`;
- `test_inventory_stock*`, permisos D3 y `test_order_inventory*`;
- `test_turno_management_api`, skill compatibility y carrera HOLD/reprogramación;
- diagnóstico, blockers y evaluación técnica.

### 9.2 Frontend

- **29/29 suites OK**.
- **226/226 pruebas OK**.
- Incluye solicitud/HOLD, `BookingPaymentFlow`, retorno MP, órdenes admin,
  pedidos cliente, rutas/permisos y asistente de reprogramación.
- La salida contiene `console.error`/`console.log` esperados por pruebas de error;
  no son fallos de aserción.

### 9.3 Controles adicionales

| Control | Resultado |
|---|---|
| `python -X utf8 manage.py check` | Sin issues |
| `python -X utf8 manage.py check --deploy` | 6 warnings de seguridad |
| `makemigrations --check --dry-run` | Sin cambios |
| `migrate --check` | Sin pendientes |
| `python -m pip check` | Sin requisitos rotos; warning local `~jango` |
| `npm run build` | Build exitoso con warnings preexistentes de ESLint, dependencia dinámica y Browserslist |
| `git diff --check` | Sin errores; sólo warning CRLF sobre `settings.py` local excluido |

Las pruebas requieren `python -X utf8` en este entorno porque los `print` con
emoji de signals/middleware siguen degradando portabilidad y producen miles de
líneas de salida.

## 10. Pendientes ajenos o parcialmente ajenos a BH-058

No se atribuyen a F1–F4 ni se corrigieron durante esta auditoría:

- CU-11 y CU-35 sin pruebas y con riesgos de idempotencia;
- manifiesto Python base incompleto;
- logs legacy con `print`/emoji;
- warnings generales del build;
- URLs absolutas en múltiples módulos no financieros;
- ficha técnica, recordatorios y otros recorridos legacy no incluidos en la
  matriz específica.

Estos pendientes deben ir a backlog separado. CU-11/CU-35 no son por sí solos
la razón del veredicto BH-058, pero su estado no puede declararse validado.

## 11. Riesgos residuales y condiciones para cierre

### Bloqueantes funcionales

1. Proveer una UI de caja para B2/C1 o declarar formalmente esa capacidad fuera
   de alcance con un reemplazo operativo seguro, autorizado y auditable.
2. Restringir y modelar la cancelación de `OrdenCompra` con dinero: impedir que
   ownership solo cancele una `PAGADO`, o abrir una obligación/caso financiero
   explícito antes de liberar el compromiso.
3. Definir la resolución de cancelaciones, refunds y chargebacks; la detección
   sin una bandeja/acción no completa el proceso comercial.

### Condiciones de autorización productiva

4. Eliminar/configurar URLs de localhost, en especial el inicio ORDER desde
   carrito, y resolver settings de producción.
5. Instalar y supervisar el worker F2; acreditar estado activo, reinicio,
   backlog, logs y alertas.
6. Ejecutar sandbox con vendedor/comprador de prueba, URL HTTPS pública y webhook
   firmado para BOOKING y ORDER, incluidos pending, duplicado, tardío, refund y
   chargeback.
7. Versionar E2E de navegador para los recorridos críticos o documentar una
   validación equivalente reproducible.

## 12. Recomendación final

F1–F4 corrigieron los dos P0 y los dos recorridos UI que motivaron su creación.
No corresponde reabrir esos incrementos por fallos de implementación local.

No obstante, BH-058 fue auditado como una capacidad integral que incluye cobros
presenciales, excepciones financieras y operación sostenible. Esas condiciones
no están cerradas y la brecha de cancelación de una orden pagada no depende de
sandbox ni de infraestructura externa.

**BH-058 = BLOQUEADO PARA CIERRE**

La validación futura debe distinguir nuevamente:

- cierre funcional del código;
- validación sandbox;
- autorización operativa de producción.

Ninguna de las dos últimas puede inferirse de mocks, del build ni de una unidad
systemd solamente versionada.
