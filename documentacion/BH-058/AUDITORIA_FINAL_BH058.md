# AUDITORÍA FINAL BH-058

**Fecha:** 2026-10-29

**Baseline publicado:** `9f3dc9b7066d29a3a177ff19b9264163c9c9cc8f`

**Tipo de revisión:** análisis, inspección y pruebas sin cobros reales

**Veredicto:** **BH-058 = BLOQUEADO PARA CIERRE**

## 1. Resumen ejecutivo

Los incrementos A1/A2, B1/B2/B3, C1/C2a/C2b y D1/D2/D3 tienen servicios de
dominio y pruebas sólidas cuando se invocan aisladamente. La auditoría ejecutó
394 pruebas backend representativas sobre PostgreSQL y todas pasaron al usar
Python en modo UTF-8. También se confirmó la creación de bases de prueba vacías,
la aplicación de migraciones, la idempotencia y las carreras principales.

Eso no constituye un recorrido de negocio completo. BH-058 no puede cerrarse
por tres razones determinantes:

1. El comando operativo `process_provider_events` sólo ejecuta C2a y deja el
   evento en `VERIFIED`; no llama a
   `reconcile_verified_provider_event`. Por ello un pago acreditado puede no
   generar `Pago`, no ejecutar B3, no crear el `Turno` y no llevar una orden a
   `PAGADO`.
2. El frontend de reservas termina en `SlotHold`: muestra el temporizador, pero
   no crea `PaymentIntent`, no permite elegir seña/pago total, no inicia checkout
   BOOKING ni muestra el estado financiero posterior.
3. `OrdenCompraViewSet.confirmar_entrega` requiere sólo autenticación y el
   servicio de inventario no exige estado `PAGADO`. Un cliente propietario puede
   confirmar su propia entrega, incluso sin pago, consumir stock y llevar la
   orden a `COMPLETADO`. La prueba existente lo acepta como resultado exitoso.

Adicionalmente, la UI operativa de órdenes no reconoce `PAGADO`, los cobros
presenciales canónicos no tienen interfaz, las cancelaciones posteriores a un
pago carecen de política compensatoria y la suite frontend no está verde.

## 2. Alcance y criterio

Se revisaron:

- `ANALISIS_BH058_ARQUITECTURA_FINAL.md` y los análisis A/B/C/D;
- documentos de implementación A1, A2, B1, B2, B3, C1, C2a, C2b, D1, D2 y D3;
- modelos, servicios, endpoints, permisos, comandos, migraciones y pruebas;
- UI de solicitudes técnicas, carrito, retorno de Mercado Pago, pagos y órdenes;
- cancelaciones, excepciones financieras, configuración y reproducibilidad.

Se distingue expresamente entre:

- **VALIDADO:** la unidad implementada pasó pruebas;
- **INTEGRADO:** dos o más tramos se ejecutaron juntos por una entrada
  productiva;
- **FRONTEND PROBADO:** existe UI y prueba automatizada representativa;
- **SANDBOX PENDIENTE:** requiere credenciales y webhook público;
- **NO IMPLEMENTADO / NO VERIFICADO:** no hay capacidad o cobertura suficiente.

No se consideró funcional un recorrido por la sola existencia de modelos,
servicios o endpoints. Los archivos locales ajenos preexistentes —incluido el
cambio de nombre de base en `settings.py`, medios y Cypress no versionado— se
preservaron y no forman parte del baseline publicado.

## 3. Matriz de trazabilidad

| Requisito | Implementación | Endpoint/UI | Prueba y evidencia | Resultado | Brecha |
|---|---|---|---|---|---|
| Solicitud y evaluación técnica | `SolicitudTecnicaReserva` y motor de riesgo | `/solicitudes-tecnicas/`; `SolicitudesTecnicas.js` | 94 regresiones técnicas en verde; prueba UI de solicitud | **VALIDADO / FRONTEND PROBADO** | El recorrido financiero posterior no continúa en UI. |
| HOLD autoritativo | A1, `SlotHold`, reloj PostgreSQL y locks | `POST .../hold/`; `/slot-holds/{uuid}/release/` | Suites HOLD y concurrencia en bloque de 113 pruebas | **VALIDADO E INTEGRADO CON A2/B3** | Falta observabilidad operativa del scheduler. |
| Temporizador | `countdown` calculado por backend; vigencia por `database_now` | Countdown en `SolicitudesTecnicas.js` | `crea un HOLD, muestra countdown...` pasa | **FRONTEND PROBADO** | El reloj de UI es informativo; correctamente no es autoridad. |
| PaymentIntent seña/total | B1, policy y snapshots inmutables | `/payment-intents/` | Seña fija/porcentaje, full, expiración, ownership y carreras pasan | **BACKEND VALIDADO** | **Sin UI** para crear, elegir modo, consultar o cancelar. |
| Pagos parciales y saldos | B2/B3, `Pago` 1:N y proyección financiera | `/payment-intents/{uuid}/payments/` | Parciales, umbral y saldo posterior pasan | **BACKEND VALIDADO** | Sin interfaz canónica de caja ni saldo. |
| Checkout BOOKING | C1 `start_booking_checkout` | `/payment-intents/{uuid}/checkout/` | Adapter, contrato e idempotencia pasan | **BACKEND VALIDADO** | No invocado por el frontend; recorrido cliente incompleto. |
| Checkout ORDER | C1 y conversión transaccional de carrito | `/checkout/iniciar-pago/`; `Carrito.js` | Checkout y compromiso previo pasan; botón “Pagar con Mercado Pago” | **INTEGRADO HASTA REDIRECCIÓN** | Sandbox no probado; host API está hardcodeado en varias UI. |
| Retorno de checkout | Retorno deliberadamente no autoritativo | `RetornoMercadoPago.js` | Inspección de código y build | **IMPLEMENTADO, INFORMATIVO** | No presenta seguimiento de Intent/orden; no acredita dinero. |
| Webhook autenticado e inbox | C2a, firma y persistencia idempotente | `/checkout/webhook/` | Firma, duplicados, mismatch, retries y carreras pasan | **VALIDADO** | Requiere secreto, URL pública y sandbox configurado. |
| Consulta y verificación del evento | `process_pending_provider_events` | comando `process_provider_events` | 57 pruebas C1/C2 pasan | **VALIDADO** | Termina en `ProviderEvent.VERIFIED`. |
| VERIFIED → Pago/B3/D2 | C2b `reconcile_verified_provider_event` | Sólo servicio interno | Depósito, full, late, duplicados, refund y ORDER pasan por llamada directa en tests | **IMPLEMENTACIÓN VALIDADA, INTEGRACIÓN AUSENTE** | **No hay comando, worker ni invocación productiva de C2b.** |
| Pago → B3 → Turno | B3 y A2, locks e idempotencia | Sin endpoint de aprobación; invocación interna desde pago manual/C2b | Parcial, umbral, retry, HOLD vencido y recurso inválido pasan | **VALIDADO CUANDO SE INVOCA** | Online queda bloqueado por C2a→C2b y por UI BOOKING ausente. |
| Carrito sin WhatsApp | Checkout MP directo desde `Carrito.js` | Botón “Pagar con Mercado Pago” | Inspección y build | **IMPLEMENTADO** | Persisten contratos legacy de `OrdenPendiente`, pero WhatsApp no es requisito del botón de compra. |
| Compromiso y no sobreventa | D2, `CompromisoStock`, locks por producto | Conversión carrito/orden | Inventario y carreras pasan | **VALIDADO** | Ninguna brecha en la unidad de compromiso. |
| Pago ORDER → `PAGADO` | C2b separa pago de entrega | Sin UI específica | Prueba confirma `PAGADO`, compromiso activo y cero salida física | **BACKEND VALIDADO** | C2b no corre productivamente; UI no contempla `PAGADO`. |
| Entrega → salida física → `COMPLETADO` | D2, movimiento idempotente | `/ordenes-compra/{id}/confirmar_entrega/` | Un único `MovimientoStock` por efecto y carreras pasan | **LÓGICA VALIDADA / AUTORIZACIÓN FALLIDA** | Cliente propietario y orden no pagada pueden ejecutar el efecto. |
| CASH presencial | B2 nace `RECONCILED` y puede disparar B3 | POST payments del Intent | Permiso efectivo, umbral e idempotencia pasan | **BACKEND VALIDADO** | No hay UI canónica; `PagoModal` usa writer legacy. |
| Transferencia y comprobante | B2 pendiente + conciliación; storage privado | payments, reconcile y receipt autorizado | MIME/tamaño/hash, privacidad, aceptación/rechazo pasan | **BACKEND VALIDADO** | No hay UI de registro, consulta privada ni conciliación. |
| Enlace MP presencial | C1 canal `IN_PERSON` restringido a personal autorizado | Checkout de Intent/orden | Contrato backend pasa | **BACKEND VALIDADO** | Sin interfaz y **SANDBOX PENDIENTE**. |
| Auditoría financiera | Auditorías semánticas y casos de conciliación | API de pagos/casos sólo parcial | Exactamente una auditoría/notificación en pruebas | **VALIDADO EN SERVICIOS** | No existe bandeja operativa de casos de C2b. |
| Cancelación antes de pagar | Cancelación de Intent libera HOLD | `/payment-intents/{uuid}/cancel/` | Idempotencia y liberación pasan | **BACKEND VALIDADO** | Sin UI del Intent. |
| Cancelación después de pagar | Pago inmutable; cancelación de Intent bloqueada | Cancelación de Turno/orden separada | Inspección y regresiones | **POLÍTICA NO IMPLEMENTADA** | No decide refund, retención, crédito ni caso manual de forma general. |
| Refund/chargeback | C2b abre caso `POST_PAYMENT_CHANGE` sin reversión | Sin UI; depende de C2b | Prueba de refund posterior pasa por llamada directa | **BACKEND PARCIAL** | No compensación automática y C2b no está conectado al worker. |
| Créditos futuros de turnos | Fuera de BH-058 | Ninguno | Inspección | **NO IMPLEMENTADO** | Correcto para este alcance; requiere backlog separado. |

## 4. Recorridos de negocio

### 4.1 Reserva de turnos

Recorrido requerido:

```text
Solicitud → evaluación → HOLD → temporizador → Intent → checkout
→ webhook → Pago → B3 → Turno
```

Resultado por caso:

| Caso | Evidencia | Resultado |
|---|---|---|
| Seña | Policy, Intent, C2b y B3 probados | Backend validado; recorrido UI/online incompleto. |
| Pago total | B1/B3/C2b en verde | Backend validado; recorrido UI/online incompleto. |
| Parciales | Pago 1:N; no confirma antes del umbral | Validado en backend. |
| Saldo después de confirmar | Vincula el Pago al Turno sin reconsumir HOLD | Validado en backend; sin UI. |
| HOLD vencido | Conserva dinero y abre caso de pago tardío; no crea Turno | Validado. |
| Notificación tardía | Pago preservado y caso `LATE_PAYMENT` | Validado por llamada directa a C2b. |
| Recurso invalidado | Pago preservado, HOLD liberado/caso abierto, sin Turno | Validado. |
| Retorno checkout | Mensaje informativo, sin acreditar | Correcto, pero no da seguimiento financiero. |
| Reintentos y duplicados | Claves, constraints y locks evitan doble Pago/Turno | Validado, incluida concurrencia PostgreSQL. |
| Sandbox | No se usaron credenciales ni dinero real | **NO VERIFICADO**. |

**Conclusión:** no existe un recorrido BOOKING completo utilizable por el
cliente. La UI se detiene en HOLD y la automatización del webhook se detiene en
`VERIFIED`.

### 4.2 Compra de productos

Recorrido requerido:

```text
Carrito → OrdenCompra → compromiso → checkout → conciliación
→ PAGADO → entrega → COMPLETADO
```

- Carrito, creación de orden, compromiso e inicio de checkout están integrados.
- No se descuenta stock físico al crear orden, iniciar checkout ni acreditar el
  pago.
- C2b lleva la orden a `PAGADO` y conserva el compromiso.
- D2 crea una única salida por producto al aplicar la entrega.
- Las carreras de última unidad y la idempotencia pasan.
- WhatsApp no es dependencia del botón de checkout actual.

El recorrido no es aceptable de extremo a extremo:

- no hay C2b productivo después de `VERIFIED`;
- `GestionOrdenes.js` sólo acciona sobre `PENDIENTE`, no ofrece filtro/entrega
  para `PAGADO` y usa `PagoModal` legacy antes de entregar;
- la API de entrega no exige permiso operativo ni estado `PAGADO`;
- `apply_order_inventory_effect` tampoco exige `PAGADO`;
- `test_finalize_and_confirm_delivery_delegate_to_single_effect` autentica al
  cliente dueño, finaliza su carrito y confirma entrega exitosamente. Esta
  prueba demuestra el defecto de autorización, no un permiso correcto.

### 4.3 Cobros presenciales

| Capacidad | Backend | Interfaz operativa | Estado |
|---|---|---|---|
| Efectivo | Registro reconciliado, permiso e idempotencia | No existe UI canónica | Parcial |
| Transferencia | Evidencia privada, pending, aceptar/rechazar | No existe UI canónica | Parcial |
| Link MP en salón | Canal `IN_PERSON` con autoridad | No existe UI; sandbox pendiente | Parcial |
| Saldo de Turno | Proyección y pago posterior probados | No existe UI | Parcial |
| Conciliación manual | Endpoint y permiso separado | No existe bandeja | Parcial |
| Comprobante privado | Endpoint autorizado, sin URL pública en serializer | No existe UI | Backend validado |
| Auditoría | Hechos y transiciones auditados | Sin bandeja integral | Backend validado |

`PagoModal.js` no consume B2: para Turnos recibe
`LEGACY_TURNO_PAYMENT_DISABLED`; para órdenes usa el writer legacy de
`OrdenCompra` y luego dispara entrega. Por tanto no debe presentarse como caja
BH-058 terminada.

## 5. Cancelaciones, devoluciones y excepciones

| Escenario | Pago | Intent | HOLD | Turno/orden | Intervención/política faltante |
|---|---|---|---|---|---|
| Antes de pagar | No existe | `CANCELLED` | `RELEASED` | No Turno | Sólo falta UI. |
| Después de pago parcial sin umbral | Se preserva | No puede cancelarse | Sigue según vigencia | Sin Turno | Falta política de devolución/retención/crédito y acción operativa. |
| Después de seña con Turno | Se preserva | `APPROVED` | `CONSUMED` | Turno puede cancelarse | La cancelación sólo cambia Turno y audita; no abre caso financiero. |
| Pago total con Turno | Se preserva | `APPROVED` | `CONSUMED` | Turno puede cancelarse | Misma brecha; no hay refund/crédito automático. |
| Cancelación por cliente | Sin efecto financiero | Sin efecto | Sin efecto adicional | `CANCELADO` si está en ventana | Falta política explícita. |
| Cancelación por salón | Sin efecto financiero | Sin efecto | Sin efecto adicional | `CANCELADO` con permiso | Falta política explícita y compensación. |
| Pago tardío sin Turno | Se preserva pending/reconciliado según canal | Expirado/no aprobable | No se resucita | No se crea Turno | Caso manual existe en C2b/B3; falta operación y UI. |
| Orden pagada cancelada | Pago se preserva | No aplica | No aplica | Puede liberar compromiso y quedar `CANCELADO` | No abre necesariamente caso ni resuelve dinero. |
| Refund/chargeback | Pago original no se borra ni revierte | No se reabre | No se resucita | Sin reversión automática | C2b abre caso sólo si se ejecuta; política y resolución manual ausentes. |

La preservación del hecho `Pago` es correcta. Lo incompleto es la decisión
comercial y contable posterior. No debe inferirse que cancelar un Turno u orden
equivale a devolver dinero.

## 6. Regresiones

| Área | Pruebas ejecutadas/evidencia | Resultado |
|---|---|---|
| Diagnóstico capilar | `test_diagnosis_authorization_api` y riesgo técnico | **VERIFICADO** en 94 pruebas técnicas compartidas. |
| Evaluación técnica de reservas | Requests, blockers y evaluator | **VERIFICADO**. |
| Reprogramación y disponibilidad | `test_turno_management_api`, skill compatibility, carrera HOLD vs reprogramación | **VERIFICADO**. |
| Autorización/privacidad de Turnos y fórmulas | `test_turno_read_authorization_api` | **VERIFICADO** para lectura y no exposición. |
| Roles efectivos | `usuarios.test_roles` | **VERIFICADO**. |
| Notificaciones de confirmación | A2/B3 exactamente una vez | **VERIFICADO** para eventos BH-058. |
| Rutina inicial automática | Existe lógica legacy en modelos/señales, sin prueba dedicada localizada | **NO VERIFICADO**. |
| Optimizador automático de agenda | No se localizó suite específica del proceso automático | **NO VERIFICADO**; sólo reprogramación/disponibilidad. |
| Generador automático de promociones | Sólo se probó permiso CRUD D3; `procesar_promos` no tiene suite dedicada | **NO VERIFICADO**. |
| Notificaciones generales/recordatorios | No se ejecutó cobertura integral de comandos legacy | **NO VERIFICADO**. |
| Ficha técnica y gestión de fórmulas | Cobertura localizada sólo de privacidad/bloqueo | **NO VERIFICADO** como recorrido funcional completo. |

No se encontraron cambios BH-058 que deliberadamente reescriban esos contratos
legacy, pero ausencia de evidencia no se declara como funcionamiento.

## 7. Seguridad, infraestructura y reproducibilidad

### 7.1 Permisos

Validado:

- permisos efectivos separados para registrar, conciliar y reportar pagos;
- comprobantes fuera de `MEDIA_ROOT`, descarga autorizada y sin URL de storage
  en el serializer;
- ownership de Intent, HOLD y lectura financiera;
- permisos D3 para lectura y gestión de stock.

Bloqueante:

- `OrdenCompraViewSet` usa `IsAuthenticated` para todas las acciones. Ownership
  limita visibilidad, pero no autoridad: el cliente puede ejecutar
  `confirmar_entrega` y `cancelar` sobre su orden. La entrega produce el efecto
  físico D2 sin comprobar permiso ni pago.

### 7.2 Webhook y worker

- El webhook legacy en `/checkout/webhook/` apunta al receptor firmado C2a.
- El receptor no acredita dinero dentro de HTTP, decisión correcta.
- `process_provider_events` implementa claim, stale recovery y retries de C2a.
- No hay scheduler/deployment versionado que garantice ejecución periódica.
- No existe segunda fase operativa que procese `VERIFIED` con C2b.
- Refunds y chargebacks dependen de esa misma fase ausente.

### 7.3 Configuración y despliegue

`manage.py check` pasó. `manage.py check --deploy` produjo seis advertencias:

- HSTS no configurado;
- redirect HTTPS no configurado;
- fallback de `SECRET_KEY` inseguro;
- cookie de sesión no marcada secure;
- cookie CSRF no marcada secure;
- `DEBUG=True` por defecto.

Además, `ALLOWED_HOSTS=['*']` permanece abierto y existen defaults/hardcodes de
desarrollo para URLs públicas y retornos. Los secretos de Mercado Pago se leen
desde entorno y no se exponen en este informe.

### 7.4 Dependencias y migraciones

- `makemigrations --check --dry-run`: sin cambios.
- Cada bloque backend creó una base de test PostgreSQL vacía, aplicó migraciones
  y la destruyó al finalizar: migración desde vacío **VERIFICADA indirectamente
  por el test runner**.
- Sólo existe `bohemiacore/requirements-payments.txt` con
  `mercadopago==3.2.0`; no hay manifiesto/lock Python base que reproduzca Django,
  DRF, PostgreSQL driver y demás dependencias.
- Frontend sí tiene `package-lock.json`.
- En Windows CP1252, las impresiones con emoji de middleware/señales hacen fallar
  el `setUp` (`UnicodeEncodeError`). Con `python -X utf8` las suites pasan. Esto
  es una brecha de portabilidad y genera salida excesiva.

## 8. Pruebas ejecutadas

### Backend PostgreSQL

| Bloque | Casos | Resultado |
|---|---:|---|
| HOLD, consumo, Intent, pagos manuales y B3, incluida concurrencia | 113 | **OK** — 531.301 s |
| C1, adapter, C2a y C2b, incluida concurrencia | 57 | **OK** — 225.208 s |
| D1/D2/D3 y órdenes, incluida concurrencia | 60 | **OK** — 90.296 s |
| Diagnóstico, riesgo y reserva técnica | 94 | **OK** — 122.310 s |
| Turnos, reprogramación, skills, lectura y roles | 70 | **OK** — 106.475 s |
| **Total** | **394** | **OK con `python -X utf8`** |

La primera ejecución sin UTF-8 terminó con 224 errores de preparación sobre 230
casos por el `UnicodeEncodeError` descrito; no fueron fallas de aserciones de
dominio.

### Frontend

- Suite completa: **22 suites pasaron, 2 fallaron**; **187 pruebas pasaron y 3
  fallaron**.
- Tres fallos de `Operaciones.test.js` no encuentran acciones de llegada,
  reprogramación y cancelación con los mocks actuales.
- `App.test.js` no pudo cargar `react-router-dom` desde Jest, aunque el paquete
  está instalado y el build lo resuelve.
- `SolicitudesTecnicas.test.js`, incluido el countdown, pasó.
- No existen pruebas versionadas específicas para `Carrito`, retorno MP,
  `GestionOrdenes` o `PagoModal`.
- `npm run build`: **compiló con warnings** de dependencia dinámica, hooks y
  variables sin uso; no es un build limpio.
- No se ejecutó como evidencia de baseline el Cypress local no versionado.

### Sandbox

**NO VERIFICADO.** No se hicieron cobros reales ni de sandbox. Para validarlo se
necesita:

1. credenciales de vendedor/comprador de prueba y moneda ARS;
2. secreto de webhook y URL HTTPS pública estable;
3. URLs de success/pending/failure apuntando al frontend desplegado;
4. worker C2a periódico y un consumidor C2b de eventos `VERIFIED`;
5. observabilidad, retries y bandeja de casos;
6. ejecutar seña, full, parcial, duplicado, pending, tardío, refund y
   chargeback, sin usar dinero real;
7. comprobar ORDER hasta `PAGADO` y luego entrega autorizada hasta
   `COMPLETADO`.

Sin los puntos 4 y 5, una prueba sandbox aislada tampoco demostraría operación
sostenible.

## 9. Hallazgos por severidad

### P0 — bloqueantes

1. **C2a no encadena C2b.** Un pago acreditado puede quedar en `VERIFIED` sin
   efecto financiero/comercial. Afecta BOOKING, ORDER, refunds y chargebacks.
2. **Entrega ORDER sin autorización ni precondición de pago.** Un cliente dueño
   puede consumir stock y completar una orden no pagada mediante API. El servicio
   de dominio tampoco exige `PAGADO`.

### P1 — altos

1. Frontend BOOKING incompleto después del HOLD.
2. UI de órdenes incompatible con `PAGADO`; no permite el flujo online canónico
   de entrega y conserva el flujo legacy `PENDIENTE` → pago modal → entrega.
3. Caja presencial B2/C1 sin UI para efectivo, transferencia, links, saldos,
   comprobantes o conciliación.
4. Cancelaciones de Turno/orden con dinero no abren de forma general un caso ni
   aplican una política de refund, retención o crédito.
5. No hay sandbox ni proceso de despliegue/worker probado.
6. Suite frontend roja y sin E2E versionado de los recorridos críticos.

### P2 — medios

1. Seis warnings de `check --deploy`, `ALLOWED_HOSTS` abierto y defaults de
   desarrollo.
2. Dependencias Python no reproducibles desde un manifiesto base completo.
3. Logs con `print` y emoji rompen tests en CP1252 y degradan observabilidad.
4. Rutina inicial, automatización de promociones/recordatorios, optimizador de
   agenda y ficha/fórmulas no tienen evidencia suficiente: **NO VERIFICADO**.
5. URLs absolutas de localhost/127.0.0.1 permanecen en superficies frontend y
   retornos legacy.

## 10. Riesgos financieros y operativos

- Dinero acreditado sin Turno ni orden `PAGADO` por falta de C2b operativo.
- Doble pago del cliente al no existir seguimiento visible después del retorno.
- Salida de productos sin pago y ejecutada por actor no autorizado.
- Orden pagada cancelada con stock liberado pero dinero sin resolver.
- Turno cancelado después de seña/full sin obligación compensatoria registrada.
- Refund/chargeback detectado pero no resuelto automáticamente.
- Evidencias manuales y casos existen en backend, pero no hay bandeja para que el
  personal actúe.
- Dependencia de comandos no desplegados/supervisados y ausencia de alertas por
  backlog `VERIFIED`, retries o casos abiertos.

## 11. Recomendación de cierre

**BH-058 = BLOQUEADO PARA CIERRE**

Condiciones mínimas para repetir la auditoría:

1. conectar operativamente C2a → C2b con claim, retries, idempotencia,
   supervisión y prueba de despliegue;
2. cerrar la autorización de entrega/cancelación ORDER y exigir transición
   válida desde `PAGADO` para el efecto físico;
3. completar el frontend BOOKING desde HOLD hasta checkout y seguimiento;
4. adaptar `GestionOrdenes` al estado `PAGADO` y separar pago de entrega;
5. exponer la caja canónica B2/C1 o declarar formalmente fuera de alcance con un
   reemplazo operativo seguro;
6. definir y registrar política para cancelación con dinero, refunds y
   chargebacks;
7. dejar verdes pruebas frontend y agregar E2E versionado de BOOKING y ORDER;
8. validar sandbox y documentar workers/configuración de producción.

Los incrementos individuales pueden conservar su estado de validación. Lo que
no puede declararse cerrado es el flujo BH-058 como capacidad de negocio.

## 12. Backlog breve para créditos exclusivos de turnos

No se implementó ni diseñó BH-059. Para un incremento futuro se recomienda:

1. crear un ledger inmutable de crédito de **turnos**, nunca aplicable a
   productos ni retirable como efectivo;
2. originar cada crédito desde un único `Pago`/caso de conciliación y una decisión
   autorizada, con constraint e idempotencia que impidan doble emisión;
3. registrar débitos por aplicación a un único `PaymentIntent`, con locks y saldo
   derivado, impidiendo doble consumo concurrente;
4. definir expiración, moneda, titularidad, transferencia, reversión y orden de
   aplicación antes de exponer UI;
5. mantener trazabilidad Pago → caso → crédito → aplicación → Turno y separar
   claramente crédito, refund y descuento;
6. probar cancelación, reprogramación, pago mixto, expiración, reintentos y
   carreras antes de integrarlo al checkout.

Este backlog no debe iniciarse hasta resolver los P0/P1 de BH-058.
