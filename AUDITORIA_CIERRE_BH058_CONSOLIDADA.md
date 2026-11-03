# AUDITORÍA DE CIERRE BH-058 — CONSOLIDADA

**Fecha:** 2026-11-03

**Baseline auditado:** `95a74c245720f99062c5da772744fd3dd9241d1d`

**Rama:** `save/work-in-progress`

**Sincronización:** el baseline coincide con `origin/save/work-in-progress`
**Tipo de revisión:** inspección de código, contratos, permisos, migraciones y
pruebas locales; sin cobros ni devoluciones reales

## 1. Resumen ejecutivo

Esta auditoría consolida las dos revisiones anteriores y contrasta directamente
la implementación posterior F1–F6 y F7.1–F7.6. Los documentos marcados como
`VALIDADO` se utilizaron como índice, pero las conclusiones se apoyan también en
servicios, modelos, API, permisos y pruebas ejecutables.

Los bloqueantes funcionales locales identificados en las auditorías previas
quedaron resueltos:

- F1 protege la entrega de órdenes con permiso efectivo, pago confirmado,
  compromisos coherentes e idempotencia;
- F2 conecta el inbox durable con C2a y C2b en un pipeline recuperable;
- F3 completa BOOKING desde la solicitud técnica hasta el seguimiento del pago
  y la creación autoritativa del Turno;
- F4 separa pago y entrega en ORDER y representa `PAGADO` y `COMPLETADO` como
  hechos distintos;
- F5 impide cancelar convencionalmente una orden pagada o con dinero todavía no
  resuelto;
- F6 aporta una caja operativa para obligaciones BOOKING mediante efectivo,
  transferencia y enlace Mercado Pago presencial;
- F7.1–F7.6 implementa consulta, solicitud, decisión, ejecución durable de
  refund, confirmación externa, ledger, efecto comercial, cierre e interfaz de
  incidencias financieras.

Los recorridos y sus invariantes fueron validados localmente sobre PostgreSQL.
La única matriz que no terminó totalmente verde fue la de inventario/F7:
**101/103**. Los dos fallos son expectativas demasiado específicas sobre el
código de rechazo de una carrera; en ambas ejecuciones hubo un solo ganador, la
entrega quedó `COMPLETADO`, el compromiso `CONSUMED` y no existió doble efecto.
No se observó pérdida de integridad.

Esto no acredita producción. No se verificaron credenciales ni fondos de
sandbox, webhook HTTPS público, worker systemd activo, proxy/origen definitivo,
observabilidad productiva ni E2E de navegador contra un despliegue real. Además,
`check --deploy` conserva seis warnings, `ALLOWED_HOSTS=['*']` y numerosas URLs
de desarrollo siguen presentes.

## 2. Alcance, método y límites

### 2.1 Inspección directa

Se revisaron, entre otros:

- HOLD, `PaymentIntent`, pagos manuales, B3, checkout y conciliación externa;
- `process_provider_events` y `process_provider_event_pipeline`;
- compromisos, entrega, cancelación y liberación post-resolución de ORDER;
- solicitudes, decisiones, operaciones de refund, ajustes y cierres;
- modelos inmutables, constraints, locks, idempotencia y auditorías;
- serializers, permisos efectivos, ownership y superficies API;
- interfaces BOOKING, ORDER, Caja e Incidencias financieras;
- diagnóstico y procesos CU-11, CU-27 y CU-35;
- configuración Django, receta systemd, migraciones, dependencias y build.

### 2.2 Acciones deliberadamente no realizadas

- no se hicieron cobros, refunds ni contracargos reales;
- no se usaron credenciales o fondos de sandbox;
- no se leyó ni modificó el contenido de secretos locales;
- no se instaló ni operó systemd desde este entorno Windows;
- no se desplegó frontend/backend ni se ejecutó un E2E contra infraestructura;
- no se modificó código, configuración, migraciones, backlog ni Git remoto;
- no se inició BH-059.

Los mocks de proveedor demuestran comportamiento determinista del adaptador y
del dominio, pero **no equivalen a sandbox ni a una prueba E2E desplegada**.

### 2.3 Estado del árbol local preservado

Antes del informe ya existían una modificación local en
`bohemiacore/bohemiacore/settings.py` y múltiples archivos no versionados
(documentación, medios y Cypress). No fueron alterados ni descartados. Este
informe es la única incorporación de la auditoría consolidada.

## 3. Reconciliación de bloqueantes históricos

| Hallazgo histórico | Defecto original | Corrección comprobada | Evidencia actual | Resultado | Riesgo residual |
|---|---|---|---|---|---|
| C2a no continuaba a C2b | El worker podía dejar un evento sólo en `VERIFIED` | F2 ejecuta verificación y conciliación mediante `process_provider_event_pipeline`, con claim, retry y recuperación stale | Suites de pipeline, eventos y conciliación; **154/154** del bloque BOOKING/Caja/proveedor | **CERRADO LOCALMENTE** | La receta systemd existe, pero no se verificó un proceso productivo activo |
| Entrega no autorizada o impaga | Una clienta podía consumir stock y completar una orden no pagada | F1 exige cuenta activa, `gestion.manage_stock`, estado `PAGADO`, revisión financiera ausente y compromisos coherentes | API, dominio, retry y concurrencia | **CERRADO LOCALMENTE** | La operación productiva depende de permisos y configuración reales |
| BOOKING se detenía en HOLD | No había Intent, checkout ni seguimiento financiero en UI | F3 incorpora elección DEPOSIT/FULL, Intent, checkout, retorno informativo y polling autoritativo | Backend y suites frontend BOOKING | **CERRADO LOCALMENTE** | Mercado Pago sandbox y cierre/reanudación de navegador desplegado no verificados |
| ORDER no distinguía pago de entrega | `PagoModal` legacy mezclaba registro y salida física; UI no entendía `PAGADO` | F4 separa checkout, conciliación, `PAGADO`, entrega F1 y `COMPLETADO` | Estados, ownership, 403/409, retry y movimiento único | **CERRADO LOCALMENTE** | URLs de desarrollo y sandbox impiden acreditación productiva |
| Cancelación convencional de orden pagada | La titular podía liberar compromiso con dinero acreditado sin resolución | F5 bloquea `PAGADO`, `COMPLETADO` y pagos no resueltos bajo lock; la solicitud pagada de F7 es una acción separada | Pruebas funcionales, C2b y carreras | **CERRADO LOCALMENTE** | La ruta legacy general sigue mereciendo hardening separado |
| Caja B2/C1 sin interfaz | Efectivo, transferencia, recibo privado y link `IN_PERSON` existían sólo en backend | F6 incorpora `/admin/caja`, saldos backend, B2 y C1 sin aceptar total ni estados desde UI | Caja frontend y regresiones backend | **CERRADO PARA BOOKING** | ORDER manual no tiene obligación B2 equivalente; arqueo y contabilidad están fuera de alcance |
| Cancelaciones, refunds y contracargos sin resolución | C2b detectaba incidencias, pero no había decisión, ejecución, ledger, efecto ni cierre | F7.1–F7.6 separa solicitud, decisión, refund, confirmación, ajuste, efecto comercial y cierre | Suites F7, API, interfaz y concurrencia | **CERRADO LOCALMENTE** | Refund manual no se simula; devolución física de una orden entregada queda diferida |
| Suite frontend roja | Fallaban recorridos operativos y faltaba cobertura crítica | Se agregaron y estabilizaron suites BOOKING, ORDER, Caja y F7 | Repetición final **33/33 suites, 276/276 tests** | **CERRADO LOCALMENTE** | No existe E2E desplegado acreditado |
| Configuración productiva insegura | Warnings de seguridad, hosts abiertos y URLs locales | Sin corrección en el baseline auditado | `check --deploy` y escaneo de configuración | **PENDIENTE PRODUCTIVO** | Bloquea habilitación de producción |

## 4. Recorridos funcionales

### 4.1 BOOKING

Recorrido implementado:

```text
Solicitud técnica
→ evaluación/aprobación
→ SlotHold
→ PaymentIntent DEPOSIT o FULL
→ checkout o pago manual
→ Pago reconciliado
→ B3
→ Turno confirmado
```

| Escenario | Comportamiento comprobado | Estado |
|---|---|---|
| Seña | El umbral proviene del snapshot de política; sólo B3 confirma | **PROBADO** |
| Pago total | Intent `FULL`, saldo cero y un único Turno | **PROBADO** |
| Pagos parciales | Se acumulan sin confirmar antes del umbral | **PROBADO** |
| Saldo posterior | Se vincula al Turno ya creado sin volver a consumir HOLD | **PROBADO** |
| HOLD vencido | No se recrea ni se confirma Turno; el dinero/evidencia se preserva | **PROBADO** |
| Pago tardío | Abre o reutiliza `LATE_PAYMENT`; no resucita HOLD, Intent ni Turno | **PROBADO** |
| Retorno de checkout | Es informativo y consulta backend; no acredita por parámetros de URL | **PROBADO** |
| Retry/duplicado | Identidades, constraints y locks evitan doble Pago o doble Turno | **PROBADO** |
| Proveedor real | Credenciales, webhook público y fondos de prueba | **NO VERIFICADO** |

### 4.2 ORDER

Recorrido implementado:

```text
Carrito
→ OrdenCompra
→ CompromisoStock ACTIVE
→ checkout
→ C2a/C2b
→ Pago RECONCILED + orden PAGADO
→ entrega autorizada
→ ORDER_SALE_OUT
→ compromiso CONSUMED + orden COMPLETADO
```

Invariantes confirmados:

- reservar o acreditar no disminuye `stock_real`;
- sólo un actor activo con `gestion.manage_stock` puede entregar;
- sólo una orden `PAGADO`, sin caso financiero abierto ni débito confirmado
  pendiente de resolución, puede iniciar la salida;
- el retry de entrega no crea un segundo movimiento;
- una cancelación impaga válida libera el compromiso sin movimiento físico;
- una orden pagada no usa la cancelación ordinaria F5;
- la solicitud de cancelación F7 conserva orden `PAGADO`, compromiso `ACTIVE`,
  pago y stock hasta la resolución;
- refund total confirmado y cancelación expresamente aprobada pueden liberar una
  orden no entregada una sola vez;
- un refund parcial mantiene la orden pagada y el compromiso activo;
- una orden `COMPLETADO` nunca repone stock por el solo hecho financiero.

### 4.3 Caja presencial

F6 opera obligaciones BOOKING ya existentes; no acepta que el frontend invente
total, moneda, estado ni obligación.

| Medio | Autoridad y resultado | Estado |
|---|---|---|
| Efectivo | B2 registra `RECONCILED`; B3 puede confirmar al alcanzar umbral | **PROBADO CON MOCKS/BASE LOCAL** |
| Transferencia | Nace `PENDING_RECONCILIATION`, exige referencia y archivo; sólo `confirm_deposit` acepta/rechaza | **PROBADO** |
| Comprobante | Descarga autenticada; no se expone URL pública de storage | **PROBADO** |
| Enlace MP presencial | C1 usa `channel=IN_PERSON`; abrir el enlace no acredita | **PROBADO SIN PROVEEDOR REAL** |
| Saldos y parciales | Se derivan en backend y se refrescan después de operar | **PROBADO** |
| Caja física/arqueo/contabilidad | No forman parte de F6 | **FUERA DE ALCANCE** |
| Cobro manual de ORDER | No existe contrato B2 canónico equivalente | **FUERA DEL CIERRE IMPLEMENTADO** |

### 4.4 Resolución financiera

El circuito implementado conserva hechos separados:

```text
caso
→ solicitud
→ decisión autorizada
→ operación de refund, si corresponde
→ confirmación oficial
→ ajuste append-only
→ efecto comercial/stock verificable
→ cierre
```

Ninguna solicitud, aprobación, respuesta HTTP o estado `SUBMITTED` reduce el
neto. Sólo un evento oficial terminal verificado puede crear el ajuste y llevar
la operación a `CONFIRMED`.

| Caso | Resultado comprobado |
|---|---|
| Turno cancelado con seña o total | Se abre solicitud financiera sin degradar Intent ni recrear HOLD |
| Pago tardío sin Turno | Permanece sin reserva; requiere decisión explícita |
| Orden `PAGADO` no entregable | Permanece reservada hasta resolución confirmada |
| Refund total | Reduce neto por el importe confirmado; puede cancelar/liberar ORDER no entregada si la decisión lo exige |
| Refund parcial | Reduce sólo el importe confirmado; no cancela ORDER por defecto |
| Contracargo | Se registra como ajuste distinto de refund; no se presenta como devolución voluntaria |
| Disputa provisional | No reduce el neto ni produce efecto comercial terminal |
| Duplicado técnico | Se deduplica por identidad; no origina una devolución adicional |
| Dos cobros reales | Conserva ambos hechos y exige resolución semántica del excedente |
| `UNKNOWN` | No reenvía; sólo consulta la Order oficial y conserva revisión si no hay coincidencia única |
| Orden ya entregada | Mantiene `COMPLETADO` y stock consumido; usa `PHYSICAL_RETURN_DEFERRED` |

## 5. Integridad financiera, netos y doble devolución

### 5.1 Hechos originales e inmutabilidad

- `Pago` conserva el bruto acreditado y no se edita para ocultar una devolución;
- solicitudes, decisiones, eventos, operaciones, ajustes y cierres bloquean
  escrituras genéricas mediante managers/querysets y servicios internos;
- los casos canónicos exponen lectura más comandos semánticos, no CRUD;
- las auditorías semánticas complementan, pero no reemplazan, las entidades y
  constraints financieras.

### 5.2 Proyección canónica

```text
net_reconciled = gross_reconciled - confirmed_adjustments
```

- `refund_pending` se informa aparte y no disminuye neto;
- refunds y contracargos tienen identidades y subtotales distintos;
- `Pago.REVERSED` es historia/compatibilidad, no un segundo ledger;
- un refund total no se resta dos veces aunque el Pago figure `REVERSED`;
- refunds parciales y múltiples se limitan al bruto reversible;
- monedas incompatibles no se agregan entre sí;
- una identidad externa repetida con importe diferente queda en revisión;
- la operación local sólo pasa a `CONFIRMED` junto con el ajuste oficial
  correlacionado.

### 5.3 Prevención de doble refund

La identidad durable se confirma antes del HTTP. Una segunda ejecución, incluso
por otro operador, recupera la misma operación y no vuelve a invocar al
proveedor. Después de timeout o caída posterior al claim, `SUBMITTED`/`UNKNOWN`
obliga a consultar la Order oficial. No existe retry ciego con otra identidad.

## 6. Permisos, ownership y exposición API

| Operación | Autoridad efectiva comprobada |
|---|---|
| Leer obligación propia BOOKING | Ownership de la clienta |
| Registrar pago manual | `gestion.register_payment` |
| Aceptar/rechazar transferencia | `gestion.confirm_deposit` |
| Ver reportes financieros | `gestion.view_financial_reports` |
| Entregar ORDER | `gestion.manage_stock` en API y dominio |
| Cancelar ORDER impaga | Titular activa o `gestion.manage_stock`, con validación financiera bajo lock |
| Solicitar cancelación de ORDER pagada | Titular/actor autorizado; sin efecto comercial inmediato |
| Decidir, ejecutar refund y cerrar caso | `gestion.reconcile_external_payment` en API y dominio |

`is_staff`, el nombre de un rol o `Personal.rol` no sustituyen las capacidades
efectivas. Se probaron clientas, staff sin permiso, cuentas inactivas y recursos
ajenos. Las respuestas públicas de resolución están reducidas y no exponen
claves idempotentes, fingerprints, tokens, comprobantes ni snapshots completos.

### 6.1 Superficie legacy residual

`OrdenCompraViewSet` sigue siendo un `ModelViewSet` autenticado y conserva
`registrar_pago`. La acción exige exactamente `gestion.register_payment`, crea
un `Pago` inmutable y no marca por sí sola la orden como `PAGADO`, por lo que no
reabre el defecto de entrega F1. El serializer genérico deja los campos
financieros principales como sólo lectura.

No obstante, este writer legacy no ofrece toda la disciplina B2: no tiene clave
idempotente de comando, no usa el grafo `PaymentIntent`, no muestra en esa ruta
la misma validación de saldo/sobrepago y crea el pago directamente. El
`ModelViewSet` también mantiene métodos genéricos innecesarios para una entidad
comercial sensible. La UI canónica F4/F6/F7 no depende de esa acción.

**Clasificación:** riesgo legacy residual y deuda de hardening, no bloqueante del
cierre funcional local de BH-058. Antes de producción debe inventariarse su uso,
restringirse a acciones semánticas o retirarse con compatibilidad controlada.

## 7. Stock, carreras e idempotencia

Se verificó el orden de locks sobre orden, pagos/ajustes, caso y compromisos. Las
carreras entre conciliación, cancelación, entrega y cierre se serializan. No hay
HTTP de proveedor dentro de `transaction.atomic()`.

La ejecución limpia de F5/F7/inventario dio **101/103**. Los dos fallos fueron:

- `test_confirm_vs_cancel_pending_contract_has_one_terminal_winner`;
- `test_release_vs_consume_only_one_transition_wins`.

Ambos tests esperaban únicamente
`ORDER_CANCELLATION_REQUIRES_FINANCIAL_RESOLUTION`. Si la entrega obtiene primero
el lock y completa la orden, la cancelación observa correctamente el estado
terminal y devuelve `COMPLETED_ORDER_CANNOT_CANCEL`. En los dos casos:

- existe un solo ganador;
- la orden termina `COMPLETADO`;
- el compromiso termina `CONSUMED`;
- existe un único movimiento físico;
- no hay liberación posterior, stock negativo ni doble descuento.

**Clasificación:** aserción no determinista de la prueba de concurrencia. Se
recomienda aceptar ambos rechazos válidos o sincronizar explícitamente qué rama
se desea probar. No se clasifica como defecto de integridad de BH-058.

## 8. Regresiones y procesos legacy

| Área | Evidencia actual | Clasificación |
|---|---|---|
| Diagnóstico capilar y autorización | `test_diagnosis_authorization_api` y evaluador técnico dentro de **93/93 OK** sobre base limpia | **FUNCIONAL; SIN REGRESIÓN BH-058 DETECTADA** |
| CU-27 — asistente de reprogramación | Servicio, permisos, disponibilidad, skills, auditoría, rollback y carrera contra HOLD; backend/frontend cubiertos | **FUNCIONAL; SIN REGRESIÓN BH-058 DETECTADA** |
| CU-11 — rutina inicial automática | Existe signal legacy, pero no suite dedicada; persisten riesgos de transición, concurrencia, versión y duplicación de efectos | **AUSENCIA DE COBERTURA Y RIESGOS/DEFECTOS PREEXISTENTES; NO REGRESIÓN ATRIBUIBLE A BH-058** |
| CU-35 — promociones automáticas | Signal, acción manual y comando sin suite integral ni scheduler acreditado; riesgos de doble ejecución y nulos | **AUSENCIA DE COBERTURA Y RIESGOS/DEFECTOS PREEXISTENTES; NO REGRESIÓN ATRIBUIBLE A BH-058** |

CU-11 y CU-35 no se declaran funcionales. Tampoco bloquean por sí solos el
cierre técnico de BH-058: requieren backlog y validación separados.

## 9. Evidencia de ejecución consolidada

### 9.1 Backend PostgreSQL

| Bloque | Resultado | Lectura |
|---|---:|---|
| BOOKING, Caja, checkout, eventos, pipeline y proveedor | **154/154 OK** | Recorridos B1/B2/B3, C1/C2a/C2b y F2 |
| F5, inventario y F7.1–F7.5 | **101/103** | Dos expectativas de código de rechazo; invariantes finales íntegros |
| Diagnóstico y CU-27 sobre base recién migrada | **93/93 OK** | Repetición limpia tras descartar contaminación del harness |

Incidencias de ejecución que no se ocultaron:

1. Una matriz backend demasiado amplia superó 30 minutos por el volumen de logs
   legacy y fue terminada antes del resumen. No se usa como resultado funcional.
2. La terminación dejó la base `test_bohemia_hair_clean` contaminada. Una
   repetición con esa base produjo conteos y PK residuales; se descartó.
3. Reutilizar después esa base con `--keepdb` produjo 50 errores de setup en
   skills/diagnóstico: `TransactionTestCase.flush` había eliminado datos semilla
   de `Habilidad` y `--keepdb` no reaplicó la migración de datos.
4. La repetición desde una base recién migrada terminó **93/93 OK**. Por ello los
   50 errores se clasifican como contaminación del harness, no como defectos.

### 9.2 Frontend

- primera ejecución completa: **32 suites pasaron, 1 falló; 273/276 tests**;
- los tres fallos pertenecían a `Operaciones.test.js` y ocurrieron al cruzar
  medianoche local/UTC: el mock construía la fecha con UTC y el componente
  filtraba por fecha local;
- repetición aislada de `Operaciones.test.js`: **28/28 OK**;
- repetición completa final: **33/33 suites, 276/276 tests OK**.

**Clasificación:** fragilidad temporal preexistente de la prueba, no regresión
funcional observada. Conviene fijar el reloj o generar una fecha local única en
el test para evitar recurrencia.

### 9.3 Controles estructurales

| Control | Resultado |
|---|---|
| `python -X utf8 manage.py check` | **OK, 0 issues** |
| `makemigrations --check --dry-run` | **OK, sin cambios** |
| `migrate --plan` | **OK, sin operaciones pendientes** |
| `compileall` | **OK** |
| `pip check` | **OK, sin requisitos rotos**; warning local por distribución `~jango` |
| `npm run build` | **OK con warnings** |
| `git diff --check` | Sin errores; sólo warning CRLF/LF del `settings.py` preexistente |

El build conserva warnings de ESLint, dependencia dinámica, Browserslist
desactualizado y deprecación Node. No invalidan la compilación, pero deben
resolverse o aceptarse explícitamente antes de una entrega productiva.

## 10. Preparación productiva no acreditada

### 10.1 Seguridad de configuración

`manage.py check --deploy` mantiene seis warnings:

1. HSTS no configurado;
2. redirect HTTPS no habilitado;
3. fallback de `SECRET_KEY` inseguro;
4. cookie de sesión sin `Secure`;
5. cookie CSRF sin `Secure`;
6. `DEBUG=True` por defecto.

Además:

- `ALLOWED_HOSTS=['*']` permanece abierto;
- CORS/CSRF y retornos incluyen orígenes de desarrollo;
- el escaneo de `frontend/src` encontró **198 coincidencias** de
  `localhost`/`127.0.0.1`;
- existen retornos backend que redirigen a `http://localhost:3000`;
- no se validó una estrategia única de URL base para el frontend desplegado.

### 10.2 Worker y observabilidad

Existe `deploy/systemd/bohemia-provider-events.service` con
`process_provider_events --watch`, reinicio automático y archivo de entorno.
Eso es una receta versionada, no evidencia de que el servicio esté instalado,
activo ni saludable. No se verificaron:

- `systemctl status` en un host objetivo;
- usuario, permisos y secretos efectivos;
- reinicio después de caída o reboot;
- backlog de eventos, stale claims y latencia de conciliación;
- logs, rotación, métricas y alertas;
- drenaje de casos `OPEN`, operaciones `UNKNOWN` o eventos `NOT_EVALUATED`.

### 10.3 Mercado Pago y navegador

Permanece **NO VERIFICADO**:

- vendedor y comprador de sandbox separados;
- Order/checkout real de prueba para BOOKING y ORDER;
- webhook firmado sobre URL HTTPS pública;
- pending, duplicado, tardío, refund parcial/total y contracargo de prueba;
- recuperación de timeout/`UNKNOWN` contra evidencia oficial;
- frontend servido desde el origen definitivo;
- E2E de navegador contra backend, worker y base desplegados.

## 11. Checklist obligatorio antes de producción

- [ ] Definir settings productivos sin defaults inseguros: `DEBUG=False`, clave
  robusta externa, hosts allowlisted, cookies secure, HTTPS redirect y HSTS
  planificado.
- [ ] Sustituir/configurar todas las URLs de localhost relevantes y validar CORS,
  CSRF, callback, success, pending, failure y webhook para el dominio definitivo.
- [ ] Instalar y habilitar el worker F2; comprobar reinicio, usuario, entorno,
  permisos, logs, rotación, métricas y alertas.
- [ ] Ejecutar migraciones en un staging representativo con backup y rollback
  documentados.
- [ ] Ejecutar sandbox end-to-end para BOOKING y ORDER sin dinero real, incluidos
  duplicados, pagos tardíos y resultados pendientes.
- [ ] Ejecutar refund total y parcial de sandbox, verificar webhook → C2a/C2b →
  ajuste → neto → efecto comercial → cierre.
- [ ] Simular timeout/resultado ambiguo y demostrar que `UNKNOWN` se recupera sin
  un segundo envío.
- [ ] Validar contracargo/disputa con los estados reales disponibles en sandbox o
  mediante evidencia oficial controlada.
- [ ] Ejecutar E2E de navegador desplegado para BOOKING, ORDER, Caja e Incidencias
  financieras, con cuentas de cada permiso efectivo.
- [ ] Confirmar privacidad de comprobantes, snapshots y datos de clienta detrás
  del proxy y storage reales.
- [ ] Inventariar y endurecer/retirar `OrdenCompraViewSet.registrar_pago` y los
  métodos genéricos legacy antes de exponer la API productiva.
- [ ] Definir runbook para eventos atrasados, casos abiertos, operaciones
  `SUBMITTED`/`UNKNOWN`, conciliación manual y escalamiento al proveedor.
- [ ] Acordar monitoreo de netos, sobreajustes rechazados, worker detenido,
  webhook inválido y órdenes bloqueadas por revisión financiera.
- [ ] Resolver o aceptar formalmente los warnings de build y la portabilidad de
  logs con emoji/UTF-8.

## 12. Riesgos residuales y alcance diferido

### 12.1 Riesgos que no impiden el cierre técnico local

- los dos tests de carrera deben aceptar más de un rechazo terminal válido;
- `Operaciones.test.js` debe fijar el reloj para no depender de medianoche;
- la superficie legacy de órdenes debe reducirse;
- los logs de signals/middleware son excesivos y requieren UTF-8 en Windows;
- el manifiesto Python base no es completamente reproducible desde el repo;
- CU-11 y CU-35 necesitan suites y disciplina de idempotencia propias.

### 12.2 Diferidos explícitos

- créditos o billetera para turnos;
- rebooking automático;
- Mercado Pago Point o QR físico;
- arqueo, cierre de caja y contabilidad general;
- ejecución automática de refunds manuales;
- reposición por devolución física de órdenes ya entregadas;
- políticas automáticas nuevas para refund parcial;
- corrección integral de automatizaciones CU-11/CU-35.

Estos diferidos no deben presentarse como capacidades entregadas por BH-058.

## 13. Síntesis de cierre

La implementación local satisface los recorridos funcionales e invariantes que
habían bloqueado BH-058: pago y reserva no se confunden, pago y entrega no se
confunden, los eventos del proveedor llegan al conciliador, una orden pagada no
se cancela por la vía ordinaria, la caja BOOKING tiene interfaz y las incidencias
financieras tienen un circuito auditable hasta su cierre. Los hallazgos de las
ejecuciones fallidas fueron reproducidos y clasificados sin ocultarlos.

La habilitación productiva requiere otra decisión porque depende de evidencia
que no existe en este entorno: configuración segura, URLs públicas, sandbox,
worker realmente supervisado, observabilidad y E2E desplegado. Aprobar el cierre
técnico no autoriza por sí mismo cobros o refunds productivos.

## 14. Cierre documental y propuesta de seguimiento

### 14.1 Correspondencia con el baseline auditado

Antes de versionar este cierre se verificó que:

- `git rev-parse HEAD` devolvía
  `95a74c245720f99062c5da772744fd3dd9241d1d`;
- `git rev-parse @{upstream}` devolvía el mismo hash;
- la rama era `save/work-in-progress` contra
  `origin/save/work-in-progress`;
- el árbol contenía archivos locales preexistentes excluidos de este cierre, que
  se preservaron sin stagearlos ni modificarlos.

Por tanto, el contenido funcional auditado corresponde al commit indicado. Un
eventual commit posterior de este documento cambia únicamente la documentación;
su padre sigue siendo el HEAD funcional auditado.

### 14.2 Actualización propuesta del estado

```text
BH-058 — CERRADO TÉCNICAMENTE
```

Este estado significa implementación local cerrada según la evidencia de esta
auditoría. No significa despliegue aprobado, operación habilitada, sandbox
validado ni autorización para procesar dinero en producción.

BH-059 permanece sin iniciar y sin cambios de alcance o estado. No se modifica
ninguna otra tarea mediante este cierre documental.

### 14.3 Pendientes transferidos

| Pendiente | Destino propuesto | Criterio mínimo de salida |
|---|---|---|
| Sandbox Mercado Pago y E2E desplegado | Gate de habilitación productiva posterior a BH-058 | BOOKING, ORDER, pagos tardíos, duplicados, pending, refund parcial/total y recuperación `UNKNOWN` probados con credenciales de prueba, webhook HTTPS y navegador desplegado |
| Configuración productiva segura y eliminación/configuración de URLs locales | Gate de habilitación productiva posterior a BH-058 | `check --deploy` resuelto o aceptado explícitamente; `DEBUG=False`, secretos externos, hosts/orígenes allowlisted, cookies/HTTPS seguros y URLs definitivas verificadas |
| Worker supervisado y observabilidad | Gate de habilitación productiva posterior a BH-058 | Servicio instalado y activo, reinicio probado, logs/rotación, métricas, alertas y monitoreo de backlog/eventos/casos |
| Hardening de rutas legacy de órdenes | Backlog independiente de hardening; sin iniciar ni modificar BH-059 | Inventario de consumidores, retiro o restricción de `registrar_pago` y reemplazo de métodos genéricos por comandos semánticos con compatibilidad controlada |
| Estabilización de tests de concurrencia y fechas | **Propuesta BH-060** | Aceptar ambos rechazos terminales válidos en las carreras o controlar su orden; fijar el reloj/fecha local de `Operaciones.test.js`; evitar contaminación con `--keepdb` |
| Revisión de CU-11 y CU-35 | Backlog independiente; identificador y alcance por definir fuera de este cierre | Suites dedicadas, idempotencia/concurrencia, scheduler/operación y corrección de defectos legacy validados por separado |

Los tres primeros pendientes son condiciones para una futura habilitación
productiva, no reaperturas del cierre técnico. El hardening legacy y la revisión
CU-11/CU-35 deben planificarse de manera independiente. La referencia a BH-060
es una propuesta de seguimiento para robustecer el entorno de tests; no inicia
su ejecución en este cierre.

## 15. Veredictos independientes

1. **Implementación BH-058: LISTA PARA CERRAR**
2. **Producción BH-058: NO HABILITADA**
