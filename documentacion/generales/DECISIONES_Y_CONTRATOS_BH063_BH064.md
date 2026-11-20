# BH-063/BH-064 — Incremento 0: decisiones y contratos

**Fecha de diseño:** 2026-11-19

**Fecha de aprobación funcional:** 2026-11-20

**Baseline publicado:** `07e581045b1d6d4f46df046c38a20d73c46d7eeb`

**Documento antecedente local:**
[Análisis conjunto BH-063/BH-064](ANALISIS_BH063_BH064_TURNOS_Y_ALTAS_PRESENCIALES.md)

**Estado:** Incremento 0 cerrado documentalmente; sin implementación

## 1. Objetivo y criterio de decisión

Este documento completa el diseño del Incremento 0 de BH-063/BH-064. Precisa
las decisiones D-01 a D-08, los comandos objetivo y sus dependencias sin crear
endpoints, código, migraciones, permisos, grupos, Pagos ni datos de negocio.

Se usan cuatro estados de decisión:

- **PROPUESTA:** existe una recomendación técnica completa, pero el propietario
  del sistema todavía no la aprobó;
- **PENDIENTE:** falta una definición operativa o de negocio indispensable para
  elegir/cerrar la alternativa;
- **APROBADA:** sólo corresponde ante aprobación explícita y verificable del
  propietario;
- **NO APLICABLE AL ALCANCE ACTUAL:** el propietario resolvió explícitamente no
  habilitar esa alternativa en BH-063/BH-064; el análisis se conserva sólo como
  referencia futura no autorizada.

El 2026-11-20 el propietario aprobó expresamente D-01 a D-07 con el alcance
registrado en este documento y declaró D-08 no aplicable al alcance actual. Esta
aprobación cierra el diseño contractual; **no significa que los modelos,
servicios, permisos, APIs o pantallas ya estén implementados**.

## 2. Fuentes y separación entre realidad e implementación futura

### 2.1 Comportamiento implementado verificado

- `Usuario.email` es obligatorio, único y `USERNAME_FIELD`; el manager, registro
  público, login, recuperación, administración, filtros y serializers asumen
  email no nulo.
- `Cliente.usuario` es una relación 1:1 y PK; los cinco campos capilares pueden
  permanecer nulos.
- `create_client_account_by_staff()` exige email, contraseña temporal válida,
  nombres, motivo y `usuarios.create_walkin_client`; crea Usuario/Cliente activos,
  rol `CLIENTE` y auditoría en una transacción, sin idempotencia.
- El contrato BH-061 activo es `bh061-role-capabilities-v1`, con snapshots y
  fingerprints inmutables. Un cambio futuro debe publicar otra versión.
- `TurnoCreationService.create()` acepta un Servicio, bloquea recursos, valida
  disponibilidad y crea siempre `SOLICITADO`; no ejecuta BH-057 ni recibe clave
  idempotente.
- `SolicitudTecnicaReserva` y BH-057 soportan multiservicio, evaluación
  versionada y outcomes `APTO`, `ADVERTENCIA`, `REQUIERE_REVISION` y `NO_APTO`.
- La aceptación web de advertencia y la creación/liberación de `SlotHold` son
  owner-only. No existe actuación de Personal en nombre del Cliente.
- `SlotHold` aplica reloj de base de datos, locks, snapshots, TTL, idempotencia,
  capacidad y consumo único.
- BH-058 usa una única `PaymentPolicy` publicada. Define modalidad
  `DEPOSIT_ONLY`, `FULL_ONLY` o `DEPOSIT_OR_FULL`, cálculo fijo/porcentual,
  moneda, TTL y medios manuales. No tiene scope por canal.
- El Turno se confirma financieramente cuando Pagos `RECONCILED` alcanzan
  `PaymentIntent.required_amount` y el hold sigue vigente. La operación revalida
  el grafo y consume el hold atómicamente.
- Efectivo manual válido se concilia al registrarse con
  `gestion.register_payment`; otras evidencias quedan pendientes y
  `gestion.confirm_deposit` las concilia/rechaza. Este último permiso no significa
  “confirmar gratis”.
- `create_confirmed_turno_from_locked_hold()` garantiza una creación única, pero
  declara que no constituye autorización financiera.
- `registrar_llegada` realiza `CONFIRMADO -> EN_PROCESO`, es no-op repetible y
  audita en la misma transacción.
- `finalize_turno()` sólo admite `CONFIRMADO -> REALIZADO`; bloquea Turno,
  Detalles y fichas, exige permiso, Personal activo, ownership, idempotencia y
  sella `FinalizacionTurno` con efectos/auditoría.
- Las fichas admiten edición en `CONFIRMADO` y `EN_PROCESO`; reprogramación y
  cancelación no admiten `EN_PROCESO`.

### 2.2 Decisiones aprobadas aún no implementadas

Todo concepto siguiente continúa siendo exclusivamente contractual hasta su
incremento de implementación:

- email nullable, estado de reclamo y contraseña inutilizable en alta rápida;
- búsqueda minimizada por teléfono;
- medio `TELEFONO` separado;
- solicitud, consentimiento, hold o Intent operados por Personal para terceros;
- ledgers idempotentes de BH-063/BH-064;
- finalización desde `EN_PROCESO`;
- estado agregado de recuperación.

La confirmación sin pago previo, el permiso
`gestion.confirm_assisted_turno_without_prepayment`, las políticas de excepción,
la deuda posterior y un contrato BH-061 v2 motivado por esa excepción **no están
aprobados para este alcance**. Se conservan como alternativa histórica futura.

## 3. Registro ejecutivo D-01 a D-08

| ID | Decisión funcional | Estado | Efecto para la implementación |
|---|---|---|---|
| D-01 | Mantener `USERNAME_FIELD=email`; permitir email nulo sólo en acceso `PENDING_CLAIM`, con password inutilizable y claim verificado por token de un solo uso. | **APROBADA** | Implementar en Incremento 1 sin alterar credenciales históricas. |
| D-02 | Aplicar la `PaymentPolicy` publicada a WEB, TELEFONO y PRESENCIAL; confirmar sólo al acreditar el umbral y sin excepción por presencia. | **APROBADA** | Implementar exclusivamente la rama financiera vigente. |
| D-03 | Crear evidencia asistida separada, distinguiendo Cliente informado y operador registrante, sin impersonación. | **APROBADA** | Implementar en Incremento 2; rechazo/no obtenido no habilitan hold. |
| D-04 | Conservar `canal_origen` histórico y agregar `medio_solicitud=WEB/TELEFONO/PRESENCIAL`, con actor real separado. | **APROBADA** | No inferir ni reescribir medios históricos. |
| D-05 | Elegir el primer slot de la grilla vigente estrictamente futuro según PostgreSQL, sin tolerancia alternativa y con TTL vigente limitado por inicio. | **APROBADA** | Revalidar todas las restricciones al crear el hold en Incremento 3. |
| D-06 | Conservar `EN_PROCESO` como atención iniciada y permitir luego `EN_PROCESO -> REALIZADO`, manteniendo también `CONFIRMADO -> REALIZADO`. | **APROBADA** | Implementar en Incremento 4 sin crear Turnos directamente en proceso. |
| D-07 | Normalizar teléfonos argentinos como señal no unique, permitir números compartidos, resolver coincidencias humanamente y proteger concurrencia. | **APROBADA** | Implementar en Incremento 1 sin autofusión. |
| D-08 | No permitir confirmación sin el prepago exigido por la policy; no crear permiso, policy de excepción, deuda posterior ni BH-061 v2 por esta causa. | **NO APLICABLE AL ALCANCE ACTUAL** | Conservar la alternativa sólo como referencia futura fuera de alcance. |

## 4. D-01 — Identidad presencial sin email

### 4.1 Problema y contrato vigente

Un Cliente sin email real no puede crearse mediante los contratos actuales.
`Usuario.email` es obligatorio y funciona simultáneamente como contacto y
principal de login. Usar `is_active=False` tampoco sirve: riesgo, hold, Intent y
Turno exigen Usuario y Cliente activos.

El registro público, login y reset deben conservar email obligatorio. El cambio
afecta sólo al alta presencial no reclamada; no habilita login sin email.

### 4.2 Alternativas

| Alternativa | Ventajas | Desventajas/decisión |
|---|---|---|
| A. Email sintético en `Usuario.email` | Cambio pequeño | Contamina contacto, búsqueda, notificaciones y recuperación; puede enviarse información a un destino falso. **Descartada.** |
| B. `Cliente` sin Usuario | Separación de dominio ideal | Rompe PK 1:1, FKs, ownership, agenda, riesgo, pagos y serializers. Migración de alto riesgo. No recomendada para BH-064. |
| C. Nuevo `login_identifier` y cambio de `USERNAME_FIELD` | Desacoplamiento completo | Cambia autenticación, admin, JWT, registro, reset y todos los tests. Excede el incremento y la necesidad actual. |
| D. Mantener `USERNAME_FIELD=email`, permitir `email=NULL` sólo mientras no hay claim | Aditiva, conserva PK/FKs y flujos de email existentes | Exige auditar todas las suposiciones de email y un estado de claim. **Recomendada.** |

### 4.3 Plan técnico aprobado para implementación posterior

La siguiente secuencia concreta el alcance aprobado para el Incremento 1. Los
nombres físicos definitivos se validarán al diseñar la migración sin cambiar la
decisión funcional:

1. preflight PostgreSQL para detectar emails duplicados por mayúsculas y filas
   incompatibles; no corregir datos automáticamente;
2. agregar a `Cliente` un estado, nombre provisional
   `web_access_status`, con `LEGACY_UNKNOWN`, `PENDING_CLAIM` y `CLAIMED`;
3. asignar `LEGACY_UNKNOWN` a históricos sin inferir que una contraseña temporal
   fue reclamada; registro público nuevo usaría `CLAIMED` y alta rápida
   `PENDING_CLAIM`;
4. cambiar `Usuario.email` a `null=True`, `blank=True`, conservando
   `USERNAME_FIELD='email'` y la unicidad de valores no nulos;
5. agregar constraint PostgreSQL condicional case-insensitive sobre `Lower(email)`
   para emails no nulos, luego del preflight;
6. mantener el manager general y superusuarios exigiendo email; sólo el servicio
   específico de alta rápida puede crear Usuario con email nulo y
   `set_unusable_password()`;
7. hacer que login/reset rechacen email vacío antes de consultar y que no
   interpreten `NULL` como principal; normalizar comparación case-insensitive;
8. adaptar admin, serializers, filtros, notificaciones y templates para mostrar
   “sin email” y omitir envíos, nunca un placeholder;
9. implementar claim con token de un solo uso y contacto verificado; bajo lock,
   asigna email no nulo, establece contraseña usable y pasa a `CLAIMED`;
10. decidir si reset de contraseña para `PENDING_CLAIM` redirige al claim o lo
    completa atómicamente; no puede dejar estado y credencial divergentes.

PostgreSQL permite múltiples `NULL` bajo una unicidad convencional, pero la
constraint funcional debe proteger los emails no nulos sin depender de checks
`iexact` previos vulnerables a carrera.

### 4.4 Impactos

| Área | Impacto propuesto |
|---|---|
| Backend | Nuevo servicio de intake/claim; email opcional sólo en alta rápida; guards de login/reset; serializers null-safe. |
| React | Formulario email o teléfono; estado “acceso pendiente”; nunca campo de contraseña temporal; claim separado. |
| Seguridad/permisos | Alta conserva `create_walkin_client`; claim requiere token de un solo uso del Cliente, no permiso del operador. No se emiten JWT para password inutilizable. |
| Migraciones | Alter email, estado de claim, constraint `Lower(email)`; posible ledger de claim. |
| Compatibilidad histórica | Sin cambio de PK, FKs, `USERNAME_FIELD`, email o contraseña históricos. `LEGACY_UNKNOWN` evita backfill especulativo. |

### 4.5 Casos extremos y riesgos

- Usuario nulo buscado por login, múltiples NULL y `MultipleObjectsReturned`;
- email ingresado durante claim ya ocupado con distinta capitalización;
- Persona con email luego de haber sido creada sólo con teléfono;
- claim y cambio administrativo de contacto concurrentes;
- notificación que intenta enviar a `None`;
- reset usado como claim sin actualizar estado;
- cuenta comercial desactivada durante claim.

Todos requieren lock de Usuario/Cliente, constraint DB y respuesta 409. Email y
token no deben aparecer completos en auditoría.

### 4.6 Recomendación, aceptación y estado

**Recomendación:** alternativa D, sin modificar `USERNAME_FIELD`.

**Criterio de aceptación:** un Cliente con email nulo, password inutilizable y
estado `PENDING_CLAIM` puede recibir un Turno; no puede autenticarse ni recibir
email; registro/login/reset históricos siguen funcionando; claim verificado
produce exactamente una credencial usable sin cambiar `cliente_id`.

**Estado: APROBADA el 2026-11-20; implementación diferida al Incremento 1.**

## 5. D-02 — Política presencial de pago y seña

### 5.1 Problema y contrato vigente

BH-058 no distingue canal. Crear un Intent requiere una `PaymentPolicy`
publicada; sin ella falla. La policy determina si se exige seña, total o permite
elegir:

- `DEPOSIT_ONLY`: umbral fijo o porcentual;
- `FULL_ONLY`: umbral igual al total;
- `DEPOSIT_OR_FULL`: el modo elegido fija el umbral.

El importe se calcula desde precios de Servicios bajo lock y se congela en
snapshots. `expires_at` es el menor entre TTL de policy y vencimiento del hold.
Sólo Pagos conciliados en la moneda correcta cuentan. El valor concreto de la
policy publicada es dato operativo de base de datos; no existe seed productivo
en código que permita afirmar aquí porcentaje, monto o versión vigente.

Autoridades actuales:

| Operación | Autoridad |
|---|---|
| Crear/consultar/cancelar Intent | Ownership del Cliente; no existe Personal-for-client |
| Registrar efectivo/evidencia | `gestion.register_payment` |
| Conciliar/rechazar evidencia | `gestion.confirm_deposit` |
| Publicar policy | `gestion.manage_payment_configuration` |
| Reconciliar provider | `gestion.reconcile_external_payment` o sistema interno |
| Crear Turno desde umbral | Orquestador interno tras revalidar; no acción libre del actor |

### 5.2 Alternativas

| Alternativa | Ventajas | Desventajas/decisión |
|---|---|---|
| A. Misma policy para web y asistido | Menor extensión, invariantes BH-058 intactas | Requiere autoridad efectiva concreta para operar por cuenta del Cliente. **Aprobada.** |
| B. Confirmar siempre sin pago por ser presencial | Flujo corto | Elude policy y separación financiera. **Descartada.** |
| C. Excepción versionada “pagar en salón” | Reflejaría otro modelo de negocio | Requeriría scope, autoridad y deuda posterior. **Fuera del alcance actual.** |
| D. Crear Pago cero/ficticio o marcar Intent APPROVED | Reutiliza consumo | Falsifica hecho financiero e invariantes. **Descartada.** |
| E. Usar campos legacy del Turno | Parece simple | `monto_abonado`, `saldo_pendiente` y comprobante no son autoridad BH-058. **Descartada.** |

### 5.3 Alcance aprobado

La decisión aprobada establece:

1. toda reserva asistida usa la `PaymentPolicy` publicada;
2. se cotiza y crea `PaymentIntent` con snapshots existentes;
3. la captura de efectivo/evidencia conserva permisos actuales;
4. el umbral conciliado confirma mediante el orquestador BH-058 existente;
5. el adapter asistido para crear Intent requiere autoridad efectiva concreta,
   que se diseñará en el Incremento 4,
   porque BH-058 documentó que `create_turno_for_client` no la concede;
6. un pago tardío conserva la evidencia/caso, pero no resucita el hold.

El propietario decidió no habilitar excepciones al pago previo en este alcance.
Si una necesidad futura reabriera esa alternativa, exigiría como mínimo una
policy versionada separada o una extensión versionada inequívoca y evidencia de:

- versión y scope de la policy de excepción;
- hold, solicitud, evaluación, Cliente, Servicios y total snapshot;
- medio de solicitud;
- reason code cerrado y justificación obligatoria;
- actor, permiso efectivo y hora DB;
- Turno resultante y operation key hash;
- disposición de cobro posterior.

El último punto seguiría siendo imprescindible. El modelo moderno no representa hoy una
obligación “confirmado sin umbral, cobrar saldo después” sin alterar la
semántica de `PaymentIntent.required_amount/status`. Este diseño futuro no
autoriza implementación alguna en BH-063/BH-064.

### 5.4 Impactos

| Área | Impacto propuesto |
|---|---|
| Backend | Adapter owner-for-client de Intent con autoridad efectiva explícita o sistema acotado; ninguna alteración de cálculo/conciliación ni rama de excepción. |
| React | Mostrar policy, modo, total, umbral, expiración y quién puede registrar/conciliar. No botón “confirmar gratis”. |
| Seguridad/permisos | Separar crear obligación por cuenta del Cliente, registrar Pago y conciliar. Ninguna de estas capacidades exceptúa el prepago. |
| Migraciones | Ninguna para una excepción; la autoridad asistida se definirá sin ampliar implícitamente permisos existentes. |
| Compatibilidad histórica | Intents/Pagos/Turnos existentes no se reinterpretan ni backfillean. |

### 5.5 Casos extremos, riesgos y aceptación

Casos: efectivo que alcanza umbral, transferencia pendiente, pago parcial,
sobrepago, hold/Intent vencido, policy retirada luego del snapshot, callback
duplicado y pago tardío.

Riesgo principal: convertir presencia física o la actuación por cuenta del
Cliente en un bypass financiero.

**Decisión:** alternativa A. La alternativa C queda expresamente fuera de alcance.

**Criterio de aceptación:** ningún Turno asistido nace por la rama financiera
sin Pagos conciliados que alcancen el snapshot; errores tardíos conservan dinero
sin recrear agenda; permisos financieros siguen separados.

La autoridad concreta para crear/cotizar Intents por cuenta de un Cliente se
definirá en el Incremento 4 con permisos efectivos; no reabre la decisión sobre
el umbral ni autoriza excepciones.

**Estado: APROBADA el 2026-11-20.**

## 6. D-03 — Consentimiento técnico asistido

### 6.1 Problema y contrato vigente

`accept_technical_warning()` sólo permite al Usuario propietario y crea
`AceptacionAdvertenciaTecnica.actor=Cliente.usuario`. Un operador no puede usar
ese contrato sin atribuir falsamente una acción autenticada.

### 6.2 Alternativas

| Alternativa | Ventajas | Desventajas/decisión |
|---|---|---|
| A. Autenticar/impersonar al Cliente | Reutiliza API | Suplantación y auditoría falsa. **Descartada.** |
| B. Guardar operador en `actor` existente | Cambio menor | Cambia el significado histórico de actor. **Descartada.** |
| C. Agregar campos opcionales al modelo existente | Unifica tabla | Mezcla dos pruebas de consentimiento y obliga a interpretar históricos. |
| D. Evidencia asistida inmutable separada | Semántica clara y aditiva | Nuevo modelo/servicio. **Recomendada.** |

### 6.3 Evidencia propuesta

Una entidad provisional `ConsentimientoAdvertenciaAsistido` debe conservar:

- solicitud y evaluación vigente;
- Cliente informado;
- outcome `ADVERTENCIA`, versión de policy, rule codes y textos cliente
  obtenidos del snapshot del servidor;
- decisión `ACEPTA`, `RECHAZA` o `NO_OBTENIDO`;
- medio `TELEFONO` o `PRESENCIAL`;
- operador registrante y hora de base de datos;
- motivo obligatorio para rechazo/no obtenido;
- idempotency key/fingerprint y `operation_id`.

El request no puede enviar textos técnicos para reemplazar el snapshot. La
evidencia declara “el operador registró que informó/recibió esta respuesta”; no
es firma digital, grabación ni autenticación del Cliente.

Sólo `ACEPTA` sobre evaluación vigente puede llevar la solicitud a
`APROBADA_TECNICAMENTE`. `RECHAZA` y `NO_OBTENIDO` no crean hold. Para evitar
forzar una semántica falsa en estados técnicos, la solicitud puede permanecer
`ADVERTENCIA_PENDIENTE` y la operación asistida cerrarse; un cambio posterior de
voluntad inicia una nueva intención/evidencia según policy aprobada.

### 6.4 Impactos

| Área | Impacto propuesto |
|---|---|
| Backend | Modelo inmutable, comando idempotente y transición bajo lock; no modifica aceptación web. |
| React | Mostrar sólo textos cliente y tres decisiones explícitas; confirmación visual previa. |
| Seguridad/permisos | `create_turno_for_client` permite registrar comunicación, no revisar riesgo ni leer historial. Revisión conserva capability técnica. |
| Migraciones | Nueva tabla/constraints; no backfill de aceptaciones web. |
| Compatibilidad histórica | `AceptacionAdvertenciaTecnica` mantiene actor=Cliente autenticado. |

Casos extremos: evaluación supersedida, warning ya aceptado web, dos operadores,
aceptar/rechazar concurrente, Cliente ausente, error después de auditoría y retry.

**Recomendación:** alternativa D.

**Criterio de aceptación:** sólo una aceptación asistida efectiva por evaluación
habilita hold; queda distinguido quién fue informado y quién registró; rechazo o
imposibilidad nunca se interpreta como aceptación.

**Estado: APROBADA el 2026-11-20; implementación diferida al Incremento 2.**

## 7. D-04 — Medio de solicitud

### 7.1 Problema y contrato vigente

`Turno.CanalOrigen` sólo tiene `WEB` y `PRESENCIAL`. El valor actual combina
quién originó y cómo se comunicó. Un turno telefónico cargado por Personal queda
incorrectamente descrito como presencial. `Turno` tampoco guarda causalmente al
operador, aunque hold/auditorías pueden hacerlo.

### 7.2 Alternativas

| Alternativa | Ventajas | Desventajas/decisión |
|---|---|---|
| A. Agregar `TELEFONO` a `CanalOrigen` | Cambio pequeño | Sigue mezclando origen, medio y actor. |
| B. Reemplazar/reinterpretar históricos | Esquema limpio | Backfill especulativo. **Descartada.** |
| C. Conservar canal y agregar medio explícito | Aditiva y trazable | Dos campos relacionados. **Recomendada.** |

### 7.3 Representación propuesta

- `canal_origen`: conserva `WEB`/`PRESENCIAL` y su lectura histórica;
- `medio_solicitud`: enum nuevo `WEB`, `TELEFONO`, `PRESENCIAL`;
- `registrado_por`: causalidad en operación/auditoría; no se deriva del medio;
- `cliente`: persona a favor de quien se registra;
- `operation_id`: une solicitud, consentimiento, hold y confirmación.

Para filas nuevas:

| Caso | canal actual compatible | medio nuevo | actor causal |
|---|---|---|---|
| Autogestión | `WEB` | `WEB` | Usuario Cliente |
| Llamada cargada por Personal | `PRESENCIAL` mientras conserve el enum legacy | `TELEFONO` | Operador |
| Visita cargada por Personal | `PRESENCIAL` | `PRESENCIAL` | Operador |

El nombre histórico `PRESENCIAL` puede entenderse como “asistido” sólo para
compatibilidad. No se reescriben filas. `medio_solicitud` histórico queda NULL o
`DESCONOCIDO_LEGACY`; no se deduce de `canal_origen`.

### 7.4 Impactos y aceptación

| Área | Impacto propuesto |
|---|---|
| Backend | Campo/snapshot en solicitud y Turno o relación causal; validación servidor; auditoría. |
| React | Selector obligatorio sólo en flujo asistido; web fija `WEB`. |
| Seguridad/permisos | El medio no concede permisos ni prueba presencia/consentimiento. Actor proviene de sesión. |
| Migraciones | Campo nullable/aditivo e índice sólo si consultas lo justifican. |
| Compatibilidad | Serializers toleran NULL; históricos no cambian. |

Casos extremos: operador cambia de teléfono a presencia, reprogramación, retry
con medio distinto y Turno creado por sistema tras pago. Un cambio de medio
altera fingerprint; el actor terminal no reemplaza al actor originador.

**Recomendación:** alternativa C.

**Criterio de aceptación:** WEB, TELEFONO y PRESENCIAL son consultables sin
inferir actor; un histórico conserva su valor original y medio desconocido.

**Estado: APROBADA el 2026-11-20; implementación diferida al Incremento 2.**

## 8. D-05 — Atención inmediata

### 8.1 Problema y contrato vigente

`validate_slot()` usa `database_now()` y rechaza `inicio <= now`. La grilla se
genera desde `HorarioLaboral.hora_inicio` en saltos de
`Configuracion.intervalo_turnos` (30 minutos por default) y exige que la duración
completa termine dentro de jornada. El hold vence en el menor valor entre
`now + slot_hold_ttl_minutes` y `starts_at`.

### 8.2 Definición aprobada

“Atención inmediata” es el primer slot de grilla cuyo `starts_at` es
estrictamente posterior al reloj DB y que, bajo revalidación autoritativa,
cumple:

1. fecha evaluada técnicamente;
2. duración agregada de todos los Servicios, con fallback actual por Servicio;
3. Personal activo y Usuario operativo;
4. habilidades AND para todos los Servicios;
5. jornada completa y sin cruce de día;
6. bloqueos globales/personales;
7. ausencia de solapamiento de Personal y Cliente;
8. holds activos no vencidos;
9. capacidad de equipamiento agregada;
10. horizonte de anticipación;
11. ventana positiva para crear hold;
12. pago/consentimiento aplicables.

No se redondea hacia atrás, no se admite hora ya iniciada y la UI no reserva. Si
otro operador gana el slot, el perdedor recibe 409 y recalcula desde un nuevo
`database_now()`.

### 8.3 Parámetros operativos aprobados

| Parámetro | Decisión aprobada | Límite contractual |
|---|---|---|
| Lead time antes del inicio | 0 minutos adicionales; sólo `starts_at > now` | No se introduce margen implícito. |
| Grilla | `intervalo_turnos` vigente | No existe grilla walk-in alternativa. |
| Duración | Contrato agregado vigente de los Servicios | No se introduce paralelización especial por urgencia. |
| Hold TTL | Configuración vigente, limitada por el inicio | No existe mínimo alternativo para slots próximos. |
| Tolerancia de atraso | Ninguna para creación | Se resuelve por el flujo operativo aplicable, nunca mediante backdating. |

### 8.4 Alternativas e impactos

- **Usar el próximo slot canónico:** recomendada; reusa disponibilidad.
- **Crear a la hora actual ignorando grilla:** descartada; rompe jornada y
  conflictos.
- **Backdating con hora de llegada:** descartada; mezcla auditoría y reserva.
- **Crear `EN_PROCESO` directo:** descartada; omite confirmación y D-06.

Backend necesita sólo un selector/orquestador que consulte y luego cree hold con
la misma lógica; React muestra “primer horario disponible”, expiración y 409.
No se aprueba una configuración, migración, lead time ni TTL especial. Seguridad
y permisos son idénticos a cualquier solicitud asistida.

Casos extremos: now exactamente en grilla, slot a segundos, cambio de día,
horario partido, duración que excede cierre, equipamiento liberado/ocupado y hold
que vence al llegar el pago.

**Criterio de aceptación:** el slot elegido siempre es futuro según DB y pasa la
misma validación dentro del lock; urgencia no omite riesgo, pago ni recursos.

**Estado: APROBADA el 2026-11-20; implementación diferida al Incremento 3.**

## 9. D-06 — Semántica de `EN_PROCESO`

### 9.1 Contrato vigente e incompatibilidad

- Llegada: `CONFIRMADO -> EN_PROCESO`, lock, permiso
  `register_arrival`, auditoría y retry no-op.
- Ficha: editable en `CONFIRMADO` y `EN_PROCESO`.
- Finalización: sólo `CONFIRMADO -> REALIZADO`; `EN_PROCESO` devuelve 409.
- Reprogramar/cancelar: estados permitidos excluyen `EN_PROCESO`.
- Ausencia: existe como enum, pero no se encontró un comando semántico de
  transición productivo.
- React muestra pestaña/estado `EN_PROCESO` y sólo ofrece llegada en confirmado.

### 9.2 Opciones

| Opción | Ventajas | Desventajas |
|---|---|---|
| A. Mantener `CONFIRMADO`; llegada como evento separado | “Llegó” no equivale a “servicio iniciado”; finalización actual intacta | Cambia API/tests/UI de llegada; requiere evidencia `arrived_at`; históricos `EN_PROCESO` quedan especiales. |
| B. `EN_PROCESO` canónico y finalizable | Menor extensión; respeta comportamiento, fichas y UI existentes | El nombre técnico actual `registrar_llegada` se interpreta funcionalmente como inicio de atención. **Aprobada.** |

### 9.3 Impacto comparado

| Área | A | B |
|---|---|---|
| Fichas | Permanecen editables en confirmado | Contrato actual ya contempla ambos |
| Agenda | Estado confirmado + badge de llegada | Pestaña `EN_PROCESO` actual |
| Finalización | Sin cambio | Admitir origen `EN_PROCESO`; ledger conserva estado anterior |
| Pagos | Sin cambio | Sin cambio de umbral; saldos posteriores siguen BH-058 |
| Ausencia | Llegada separada impide marcar ausente | `EN_PROCESO` tampoco debe pasar a ausente |
| Cancelación/reprogramación | Requiere impedirlas tras `arrived_at` | Ya están impedidas por estado |
| Auditoría | Nuevo evento/fecha sin mutar estado | Evento actual + finalización desde nuevo origen |
| Automatizaciones | Siguen disparando al finalizar | Mismo plan de efectos al pasar a REALIZADO |
| Regresión | Llegada y consumidores de estado | Finalización que hoy prueba rechazo de EN_PROCESO |

### 9.4 Decisión aprobada y condiciones

La opción B fue aprobada como el cambio menor y más compatible con el estado
publicado. Debe:

- aceptar `CONFIRMADO` y `EN_PROCESO` como estados origen de `finalize_turno()`;
- conservar ownership, permiso, Personal activo, locks, fichas, idempotencia,
  efectos y auditoría idénticos;
- persistir el estado origen real en `FinalizacionTurno.estado_anterior`;
- no permitir `EN_PROCESO` desde creación ni desde payload libre;
- interpretar funcionalmente `registrar_llegada` como “iniciar atención”, aunque
  el eventual cambio de nombre técnico se resuelva durante la implementación;
- probar que cancelación, reprogramación y ausencia siguen rechazadas una vez
  iniciado.

No se requiere migración para B. A requeriría timestamp/ledger de llegada y
adaptación histórica. Ninguna opción modifica Pagos ni finalizaciones pasadas.

**Criterio de aceptación B:** un Turno iniciado se finaliza exactamente una vez
con el mismo plan de efectos que uno confirmado; el ledger declara
`EN_PROCESO -> REALIZADO`; los demás estados siguen rechazados.

**Estado: APROBADA el 2026-11-20; implementación diferida al Incremento 4.**

## 10. D-07 — Duplicados por teléfono

### 10.1 Problema y contrato vigente

`Cliente.numero` es opcional, libre, no normalizado y no único. La búsqueda
actual usa nombre, apellido y email. Email evita parte de duplicados, pero no el
caso sin email ni carreras con distintas Idempotency-Key.

### 10.2 Estrategia aprobada

1. conservar valor presentado y agregar/derivar un teléfono normalizado;
2. usar parser compatible con numeración argentina, región por defecto AR,
   salida preferida E.164 y estado `VALID/INVALID/LEGACY_UNKNOWN`;
3. no agregar unique global: familiares u otras personas pueden compartir
   número y los números pueden reciclarse;
4. búsqueda exacta por normalizado más búsqueda tolerante por nombre/apellido;
5. devolver candidatos mínimos y contacto enmascarado;
6. exigir decisión humana `USE_EXISTING` o `CREATE_DISTINCT`;
7. `CREATE_DISTINCT` frente a coincidencia requiere reason y IDs revisados;
8. serializar intake concurrente con advisory lock transaccional derivado del
   hash del contacto normalizado y volver a buscar después del lock;
9. Idempotency-Key resuelve retry del mismo comando; no reemplaza revisión entre
   claves diferentes;
10. nunca fusionar ni mover Turnos/historial automáticamente.

### 10.3 Alternativas

| Alternativa | Decisión |
|---|---|
| Unique global de teléfono | Rechazada hasta demostrar que nunca se comparte/recicla. |
| Nombre+teléfono como unique | Rechazada: homónimos y variaciones legítimas. |
| Merge automático por match | Rechazada: riesgo de exposición y corrupción histórica. |
| Sólo warning frontend | Insuficiente ante concurrencia. |
| Match + lock + resolución humana | Recomendada. |

### 10.4 Impactos, extremos y aceptación

Backend necesita normalización, índice no unique, búsqueda y evidencia de
resolución; React muestra candidatos y prohíbe crear hasta resolver. El permiso
de alta no habilita ver historial; sólo datos mínimos. Migración histórica puede
calcular candidatos, pero no declarar teléfonos verificados ni fusionar.

Casos: prefijo local, `+54 9`, separadores, extensiones, número compartido,
reciclado, homónimos, typo, sin contacto, dos operadores y Cliente desactivado.

**Recomendación:** match no unique con lock y revisión humana.

**Criterio de aceptación:** ningún retry duplica; dos claves concurrentes ven la
misma lista después del lock; crear una persona distinta exige evidencia; no hay
merge automático ni rechazo de un teléfono compartido válido.

**Estado: APROBADA el 2026-11-20; implementación diferida al Incremento 1.**

## 11. D-08 — Confirmación no financiera

### 11.1 Problema y contrato vigente

`create_turno_for_client` permite registrar una solicitud/Turno para terceros,
no autoriza omitir pago. `register_payment` registra dinero/evidencia;
`confirm_deposit` concilia; ninguno significa excepción financiera. El contrato
BH-061 v1 otorga `create_turno_for_client` a EMPLEADO, PROFESIONAL y ADMIN, por
lo que reutilizarlo ampliaría la excepción a roles sin decisión explícita.

### 11.2 Alternativas

| Alternativa | Riesgo/decisión |
|---|---|
| Reusar `create_turno_for_client` | Une registrar intención con dispensar pago. **Descartada.** |
| Reusar `confirm_deposit` | Confunde conciliación de evidencia con excepción. **Descartada.** |
| Usar `is_staff`, `is_superuser` o ADMIN nominal | Viola autorización efectiva. **Descartada.** |
| Sistema confirma toda reserva presencial | Bypass no revocable por actor. **Descartada.** |
| Permiso nuevo, policy versionada y ledger de excepción | Sería la única alternativa técnicamente aceptable si el negocio cambiara. **No aplicable al alcance actual.** |

### 11.3 Decisión para BH-063/BH-064

El propietario decidió que:

- no existe excepción general por teléfono o presencia física;
- todo Turno asistido debe alcanzar el umbral de la `PaymentPolicy` vigente;
- no se implementará
  `gestion.confirm_assisted_turno_without_prepayment`;
- no se publicará un contrato BH-061 v2 por esta razón;
- no se crearán políticas de excepción, Pagos ficticios, deuda posterior ni un
  comando terminal no financiero;
- cualquier intento de consumir el hold sin umbral financiero debe rechazarse.

Esta decisión no autoriza automáticamente a recepción u otro Personal a operar
Intents, registrar Pagos o conciliar por cuenta de un Cliente. El Incremento 4
debe diseñar permisos efectivos concretos para cada operación asistida,
conservando la separación entre crear solicitud, preparar obligación, registrar
evidencia y conciliar. Esa actuación delegada sigue sujeta al umbral y **no es
una excepción financiera**.

### 11.4 Alternativa futura preservada, no autorizada

Para mantener la trazabilidad del diseño previo, si otro alcance futuro
reabriera el pago posterior, el nombre provisional evaluado fue
`gestion.confirm_assisted_turno_without_prepayment` y habría requerido:

1. agregar el permiso Django mediante migración;
2. publicar `bh061-role-capabilities-v2` como snapshot nuevo; v1 y sus
   fingerprints permanecen intactos;
3. decidir explícitamente qué roles, si alguno, lo reciben por default; este
   documento no concede el permiso;
4. preservar permisos individuales/grupos técnicos y registrar versión y
   fingerprints en eventos de cambios efectivos;
5. verificar permiso activo al momento de commit, no al abrir la pantalla;
6. exigir policy de excepción publicada, scope coincidente, reason code y
   justificación;
7. limitarlo a hold técnicamente aprobado y vigente; no permite elegir estado,
   monto, Cliente ni Servicios fuera del hold;
8. hacer la operación idempotente y auditar actor, scope, policy, evaluación,
   hold, Turno y hash de operation key;
9. revocación impide comandos nuevos; un retry del mismo actor sobre resultado
   ya confirmado sólo recupera la respuesta mínima, no vuelve a autorizar;
10. definir quién autoriza/configura la policy sin derivarlo de este permiso.

Estos puntos son referencia no normativa. No forman parte de los incrementos
1–5 ni habilitan migraciones, permisos o grants.

### 11.5 Impactos y aceptación

| Área | Impacto aprobado |
|---|---|
| Backend | Sólo rama financiera BH-058 adaptada al actor asistido; sin comando de excepción. |
| React | No muestra acción “confirmar sin pago”; muestra policy, umbral y estado financiero real. |
| Seguridad | Permisos efectivos separados para actuar por cuenta del Cliente; ninguno exceptúa el umbral. |
| Migraciones | Ninguna para permiso, policy, ledger o deuda de excepción; BH-061 v1 permanece vigente. |
| Historia | v1, auditorías, Intents y Turnos previos no se modifican ni reinterpretan. |

Casos: autoridad asistida revocada durante la operación, policy retirada, misma
persona en dos roles, hold vencido, umbral insuficiente, doble confirmación y
retry tras commit.

**Criterio de aceptación:** ningún hold asistido se consume sin Pagos conciliados
que alcancen el umbral; no existe endpoint, permiso, policy ni deuda de excepción;
la autoridad para operar por cuenta del Cliente no altera esta regla.

**Estado: NO APLICABLE AL ALCANCE ACTUAL por decisión del 2026-11-20.**

## 12. Alternativas descartadas consolidadas

1. email ficticio o compartido para Clientes sin contacto;
2. contraseña temporal elegida/conocida por recepción;
3. desactivar `Usuario` para expresar acceso web pendiente;
4. impersonar al Cliente en warning, hold o pago;
5. reemplazar/backfillear canal histórico por inferencia;
6. backdating o creación directa `EN_PROCESO` para walk-in;
7. unicidad global o merge automático por teléfono;
8. crear Pago cero/ficticio, mutar campos financieros legacy o aprobar Intent
   sin umbral;
9. reutilizar `create_turno_for_client`/`confirm_deposit` para exceptuar pago;
10. modificar el snapshot BH-061 v1 o autorizar por BusinessRole textual,
    `is_staff` o `is_superuser`.

## 13. Convenciones contractuales comunes

Estas convenciones forman el contrato objetivo aprobado para los comandos nuevos
A, C, D, E y F. Continúan sin implementación.

### 13.1 Idempotencia y causalidad

- Header `Idempotency-Key`: requerido, opaco, 1–128 caracteres y generado por el
  cliente; una intención nueva usa clave nueva.
- Fingerprint `sha256-canonical-json-v1`: JSON UTF-8, claves ordenadas, sin
  espacios, IDs enteros, fecha/hora ISO, strings normalizados y lista de
  Servicios en orden contractual. Incluye actor efectivo y tipo de comando.
- La clave se persiste como digest para búsqueda/unique; auditoría sólo conserva
  digest, nunca la clave completa.
- Misma key + fingerprint: mismo resultado con `changed=false`/HTTP 200.
- Misma key + payload/actor/tipo distinto: 409 `IDEMPOTENCY_KEY_REUSED`.
- `operation_id`: UUIDv4 opaco correlaciona alta, solicitud, consentimiento,
  hold y confirmación; no sustituye las keys de cada comando.
- El ledger de comando se escribe en la misma transacción que su efecto. Un
  rollback no deja éxito ni evento huérfano.

### 13.2 Errores comunes

| HTTP | Uso |
|---|---|
| 400 | Header/campo/formato/decisión inválidos; no hubo mutación. |
| 401 | Sesión ausente/expirada. |
| 403 | Actor autenticado sin permiso/capability. |
| 404 | Recurso inexistente o fuera de scope, sin enumeración. |
| 409 | Key reutilizada, estado/policy/evaluación obsoletos, duplicado ambiguo, capacidad o carrera. |

La respuesta de error usa `code`, `detail` seguro y `field` opcional. No devuelve
diagnóstico, existencia de terceros, policy interna no autorizada ni datos
sensibles.

### 13.3 Locks

Se conserva el orden global de BH-058: solicitud -> hold -> Intent -> Cliente ->
Pagos -> recursos de agenda. Intake usa advisory lock de contacto y luego
Usuario/Cliente. Todo comando revalida autorización y estado después de esperar.

## 14. Contrato A — Alta rápida idempotente

**Estado actual:** parcial (`create_client_account_by_staff`), no idempotente y
email/password obligatorios.

**Contrato objetivo:** nuevo.

| Elemento | Especificación objetivo aprobada |
|---|---|
| Actor/permiso | Usuario activo con `usuarios.create_walkin_client`. |
| Request | `first_name`, `last_name`, `email?`, `telefono?`, `zona?`, `motivo`, `medio_alta=PRESENCIAL`, `duplicate_resolution?`, `candidate_client_id?`. Sin password ni capilar. |
| Key/fingerprint | Convención común; contacto y nombres normalizados, resolución y candidato incluidos. |
| Identidad causal | `operation_id`, `client_intake_command_id`, actor y `cliente_id`. |
| Precondiciones | Al menos email o teléfono; D-01/D-07 aprobadas; actor vigente. |
| Validaciones | Longitud, email case-insensitive, teléfono, match, resolución explícita, Cliente/Usuario existentes. |
| Persistencia | Ledger + Usuario con password inutilizable + Cliente + único rol CLIENTE + claim status + auditoría. Cero diagnóstico. |
| Transacción/locks | Advisory lock por contacto; Usuario/Cliente candidatos; grupo de rol; todo o nada. |
| Respuesta | 201 si crea; 200 en retry o selección existente; `created`, `cliente_id`, nombre, contactos enmascarados, `web_access_status`, `operation_id`. |
| Errores | 400 datos/contacto; 401; 403; 404 candidato fuera de scope; 409 key, email, match ambiguo o carrera. |
| Retry | Mismo resultado/Cliente; jamás segunda cuenta ni segundo evento efectivo. |
| Auditoría | Actor, motivo, medio, Cliente/Usuario, rol contract version/fingerprint, claim status, resolución de duplicado; sin token/password/contacto completo. |
| Protección | Proyección mínima; email/teléfono enmascarados en conflicto; rate limit. |

Si el Cliente se crea y el Turno posterior falla, el resultado de A permanece y
se reanuda con `cliente_id`; no se elimina la identidad.

## 15. Contrato B — Búsqueda minimizada de Clientes

**Estado actual:** existen listado `view_clients` y selector completo protegido
por `create_turno_for_client`; no busca teléfono ni pagina el selector.

**Contrato objetivo:** nuevo read model, sin mutación.

| Elemento | Especificación objetivo aprobada |
|---|---|
| Actor/permiso | `usuarios.view_clients` para consulta general; `gestion.create_turno_for_client` habilita sólo selector mínimo de booking. |
| Request | `q` con longitud mínima, filtro exacto opcional de email/teléfono normalizado, `page`, `page_size` acotado. |
| Idempotencia | No aplica a lectura; se puede usar request correlation no persistida. |
| Precondiciones | Sesión/permiso efectivos; query no vacía. |
| Validaciones | Tamaño, caracteres, límites de página; no permite IDs masivos. |
| Persistencia/locks | Ninguna; índices de nombre/email/teléfono según plan de consulta. |
| Respuesta | `cliente_id`, nombre/apellido, contacto enmascarado, activo y `web_access_status`; nunca capilar/historial/roles. |
| Errores | 400 query; 401; 403; 404 sólo para detalle fuera de scope; 409 no aplica. |
| Auditoría | Métrica/log seguro de acceso; auditoría semántica sólo si política de privacidad la exige, sin término completo. |
| Protección | Paginación, rate limit, no dump inicial, 404 seguro y máscara. |

## 16. Contrato C — Solicitud técnica asistida

**Estado actual:** creación/evaluación web existente sin idempotencia de comando
asistido; servicio interno no autoriza actor.

**Contrato objetivo:** nuevo orquestador sobre BH-057.

| Elemento | Especificación objetivo aprobada |
|---|---|
| Actor/permiso | Usuario activo con `gestion.create_turno_for_client`. No concede revisión técnica. |
| Request | `cliente_id`, `servicio_ids` únicos y ordenados, `fecha_preferida`, `hora_preferida`, `personal_preferido_id?`, `medio_solicitud`, `operation_id?`. Sin outcome/estado/policy libre. |
| Key/fingerprint | Actor, Cliente, lista ordenada, fecha/hora, Personal y medio. |
| Identidad causal | Solicitud, evaluación inmutable, intento y operation. |
| Precondiciones | Cliente/Usuario activos; Servicios activos; actor autorizado; medio no WEB para actor asistido. |
| Validaciones | BH-057 publicada/configurada, skills si Personal preferido, fecha no pasada y payload estricto. |
| Persistencia | Ledger, Solicitud, snapshots de Servicios, evaluación e auditoría. No hold, Pago, Turno ni diagnóstico. |
| Transacción/locks | Cliente/Servicios/policy según servicios BH-057; persistencia atómica. |
| Respuesta | 201/200 con IDs, estado cliente-safe, outcome, mensajes permitidos, `next_action`; sin triggers internos no autorizados. |
| Errores | 400 configuración/entrada; 401; 403; 404 Cliente/Servicio fuera de scope; 409 key o intención obsoleta. |
| Retry | Recupera misma evaluación; no reevalúa con policy nueva silenciosamente. |
| Auditoría | Actor real, Cliente, medio, servicios, versión policy, outcome y operation. |
| Protección | Recepción ve códigos/mensajes cliente; historial y diagnóstico requieren capability propia. |

## 17. Contrato D — Consentimiento asistido

**Estado actual:** aceptación web owner-only.

**Contrato objetivo:** nuevo, paralelo al web.

| Elemento | Especificación objetivo aprobada |
|---|---|
| Actor/permiso | Usuario activo con `gestion.create_turno_for_client`. |
| Request | `solicitud_id`, `evaluacion_id`, `decision`, `medio`, `motivo?`, `operation_id`. No textos ni outcome editables. |
| Key/fingerprint | Solicitud/evaluación, decisión, medio, motivo normalizado y actor. |
| Identidad causal | Evidencia asistida inmutable + audit; Cliente informado separado de registrante. |
| Precondiciones | Evaluación vigente `ADVERTENCIA`; solicitud `ADVERTENCIA_PENDIENTE`; mensajes cliente disponibles. |
| Validaciones | `motivo` obligatorio salvo ACEPTA; evaluación/Cliente coherentes; sin aceptación previa incompatible. |
| Persistencia | Evidencia y auditoría; sólo ACEPTA cambia solicitud a aprobada. |
| Transacción/locks | Solicitud y evaluación; constraint/idempotencia por evaluación/key. |
| Respuesta | 201/200, decisión, estado solicitud y próximo paso; textos snapshot autorizados. |
| Errores | 400 decisión/motivo; 401; 403; 404 scope; 409 superseded, ya decidido incompatible o key. |
| Retry | Misma evidencia sin duplicar transición/auditoría. |
| Protección | Sin firma/voz falsa; notas internas no expuestas; motivo acotado. |

## 18. Contrato E — Hold asistido

**Estado actual:** `SlotHold` sólido pero owner-only.

**Contrato objetivo:** variante asistida nueva que reusa invariantes.

| Elemento | Especificación objetivo aprobada |
|---|---|
| Actor/permiso | Usuario activo con `gestion.create_turno_for_client`. |
| Request | `solicitud_id`, `personal_id`, `starts_at` aware, `operation_id`. Sin duración, precio, estado ni expires_at cliente. |
| Key/fingerprint | Solicitud, Personal, inicio, actor y operation. |
| Identidad causal | `SlotHold.public_id`, evaluación, solicitud, actor creador. |
| Precondiciones | Solicitud aprobada, evaluación vigente, Cliente/Personal/Servicios activos. |
| Validaciones | Reloj DB, fecha aprobada, duración agregada, skills, jornada, bloqueos, overlaps, holds y equipo. |
| Persistencia | Hold/snapshots/equipo/auditoría existentes y vínculo causal de operation. |
| Transacción/locks | Mismo orden y locks de `create_slot_hold`; scope asistido sustituye sólo el owner-check. |
| Respuesta | 201/200 con public id, inicio/fin, vencimiento DB, estado y `next_action`. |
| Errores | 400 formato; 401; 403 permiso; 404 solicitud fuera de scope; 409 evaluación, active hold, slot, equipo, expiry o key. |
| Retry | Recupera hold si payload coincide, aunque quede poco TTL; estado efectivo se informa. |
| Auditoría | Actor real, Cliente, evaluación, Personal, intervalo, key hash y operation. |
| Protección | No devuelve otros Clientes/holds ni detalle técnico. |

Liberar un hold asistido requiere el mismo permiso, scope por operation/Cliente y
motivo `OPERATOR_CANCELLED` nuevo; no debe registrar `CLIENT_CANCELLED` si el
Cliente no ejecutó la acción.

## 19. Contrato F — Confirmación financiera

### 19.1 Rama financiera existente con adaptación asistida

**Estado actual:** cálculo, Pago, conciliación y consumo existen; creación de
Intent es owner-only.

**Contrato objetivo:** adapter de preparación para terceros más servicios
financieros existentes.

| Elemento | Especificación objetivo aprobada |
|---|---|
| Actor/permiso | Crear/cotizar Intent para tercero: autoridad efectiva concreta a diseñar en el Incremento 4, sin derivarla de `create_turno_for_client`. Registrar Pago: `register_payment`. Conciliar: `confirm_deposit`. Provider: sistema/permiso existente. |
| Request | Preparar: hold + mode. Pago/conciliación conservan contratos existentes. Nunca monto/policy autoritativos desde frontend. |
| Key/fingerprint | Keys separadas de Intent, Pago y confirmación; snapshots existentes. |
| Precondiciones | Hold activo, solicitud/evaluación vigentes, policy publicada y permiso específico. |
| Persistencia | Intent/líneas; Pagos; al umbral, APPROVED + hold CONSUMED + Turno CONFIRMADO + links/auditorías. |
| Locks | Orden BH-058 completo; revalidación tras lock. |
| Respuesta | Intent/financial snapshot y, al confirmar, Turno o reconciliation case. |
| Errores | 400 input; 401; 403 separación financiera; 404 scope; 409 threshold, expiry, overpay, policy/key/context. |
| Retry | Cada nivel recupera su fila/resultado; un hold produce un Turno. |
| Protección | Datos financieros sólo por ownership o permiso operativo; comprobantes protegidos. |

### 19.2 Rama no financiera fuera del alcance

**Estado actual:** no existe y no está autorizada.

**Decisión actual:** no se implementa en BH-063/BH-064. La tabla conserva el
diseño anterior sólo como referencia futura no autorizada.

| Elemento | Referencia futura no aplicable |
|---|---|
| Actor/permiso | `confirm_assisted_turno_without_prepayment` efectivo, cuenta activa; posible separación de actor originador según policy. |
| Request | `slot_hold_public_id`, `exception_reason_code`, `justification`, `operation_id`. No estado, monto ni policy version elegida por cliente. |
| Key/fingerprint | Hold, actor, reason, justificación, policy de excepción resuelta por servidor. |
| Precondiciones | Policy publicada/scope, hold/evaluación vigentes, disposición de cobro posterior definida. |
| Persistencia | Autorización inmutable + consumo hold + Turno CONFIRMADO + obligación posterior aprobada + auditoría. Nunca Pago. |
| Locks | Mismo grafo y recursos que consumo BH-058; permiso/policy revalidados antes de commit. |
| Respuesta | 201/200 con Turno, fundamento `NON_PREPAYMENT_EXCEPTION`, policy y siguiente acción de cobro. |
| Errores | 400 reason; 401; 403 permiso/scope; 404; 409 policy retirada, hold/recursos/key/obligación. |
| Retry | Recupera mismo Turno aun si permiso fue revocado después; no autoriza otro hold. |
| Protección | Justificación no visible al Cliente salvo mensaje específico; datos financieros limitados. |

## 20. Contrato G — Estado y recuperación de operaciones

**Estado actual:** cada subsistema ofrece recuperación parcial, pero no existe
una proyección BH-063/BH-064 conjunta.

**Contrato objetivo:** nuevo read model derivado, no nueva autoridad de estado.

| Elemento | Especificación objetivo aprobada |
|---|---|
| Actor/permiso | Actor originador o usuario con permisos actuales para el recurso/operación; no basta conocer UUID. |
| Request | `operation_id`; filtros acotados para operaciones propias/autorizadas. |
| Idempotencia | Lectura; no muta. Cada retry de comandos usa su key original. |
| Identidad causal | Root operation UUID + referencias a Cliente, solicitud, evaluación, consentimiento, hold, Intent y Turno. |
| Precondiciones | Scope vigente; relaciones coherentes. |
| Validaciones | No confiar en un status cache: derivar estados efectivos, incluyendo expiración sin materializarla en GET. |
| Persistencia | Root/correlación y links; no duplicar outcomes financieros/técnicos como autoridad. |
| Locks | Ninguno para GET; comandos de “resume” delegan en servicios con locks. |
| Respuesta | Etapas completadas, IDs públicos, estado seguro, `next_action`, `last_error_code`, keys nunca devueltas. |
| Errores | 400 UUID; 401; 403 o 404 seguro; 409 sólo si se pide reanudar una etapa incompatible. |
| Retry | Reload muestra resultado confirmado o punto exacto recuperable. |
| Auditoría | Lecturas según política; toda reanudación mutante audita en su comando. |
| Protección | Proyección distinta para recepción, financiero, técnico y Cliente. |

Estados de proyección sugeridos, no estados nuevos de Turno:
`CLIENT_READY`, `TECHNICAL_PENDING`, `TECHNICAL_REVIEW`, `CONSENT_PENDING`,
`HOLD_ACTIVE`, `PAYMENT_PENDING`, `CONFIRMED`, `RECOVERABLE_FAILURE` y `CLOSED`.

## 21. Matriz de dependencias de incrementos 0–5

| Inc. | Alcance | Decisiones bloqueantes | Dependencias/migraciones potenciales | Riesgos | Pruebas mínimas | Autorización para iniciar | Rollback/recuperación |
|---|---|---|---|---|---|---|---|
| 0 | Decisiones/contratos | Ninguna | Ninguna | Confundir aprobación con implementación | Coherencia documental y código | D-01–D-07 aprobadas, D-08 fuera de alcance y cierre publicado | Revisión documental, sin estado productivo |
| 1 | Identidad BH-064 | D-01, D-07 y D-04 aprobadas | Email nullable, claim status, unique Lower(email), teléfono argentino normalizado, ledger | Login/reset/notificaciones, duplicados | PostgreSQL alta/claim/concurrencia; registro/login/reset/admin; React sin password | Incremento 0 cerrado; plan reversible y contratos aprobados | Migraciones aditivas primero; feature flag; Cliente creado se conserva |
| 2 | Solicitud/riesgo | D-03 y D-04 aprobadas; Inc. 1 para Clientes nuevos | Consentimiento asistido, medio, operation ledger | Impersonación, fuga técnica, policy obsoleta | Outcomes BH-057, multiservicio, consent races, permisos/React | Inc. 1 aceptado; regresión web BH-057 preservada | Sin hold/Turno: cerrar operation y conservar evidencia |
| 3 | Hold/inmediatez | D-05 aprobada; Inc. 2 | Adapter asistido; quizá release reason/operation link | Sobreventa, TTL próximo al inicio | PostgreSQL holds/Turnos/equipo/expiry; 409 React | Inc. 2 aceptado; grilla y TTL vigentes; owner-only web intacto | Liberar/expirar hold; solicitud/Cliente permanecen |
| 4 | Confirmación/estados | D-02 y D-06 aprobadas; D-08 no aplicable; Inc. 3 | Autoridad efectiva para Intent de tercero; sin permiso/policy/deuda de excepción | Bypass financiero, doble Turno, efectos duplicados | Pago manual/provider, consumo concurrente, rechazo sin umbral, finalización desde ambos orígenes | Inc. 3 aceptado; scopes financieros revisados; sólo rama financiera | Fallo financiero crea caso; no borrar Pago/Cliente; hold se reintenta sólo si vigente |
| 5 | React integrado/endurecimiento | Todas las aplicables; Inc. 1–4 | Índices finales, sin nueva semántica | Flujo masivo difícil de recuperar | React completo, E2E focal, B1–B7, build/checks | Todos los incrementos previos aceptados y observables | Wizard reanudable por operation; feature flag/rutas desacopladas |

### 21.1 Orden recomendado

1. **Incremento 1 — BH-064:** identidad mínima, deduplicación, claim e
   idempotencia;
2. **Incremento 2 — BH-063:** solicitud técnica asistida, riesgo BH-057 y
   consentimiento;
3. **Incremento 3:** hold asistido, disponibilidad y atención inmediata;
4. **Incremento 4:** confirmación financiera y transición desde `EN_PROCESO`;
5. **Incremento 5:** React integrado, recuperación y endurecimiento.

La rama no financiera no forma parte del plan. El Incremento 4 debe especificar
la autoridad efectiva para operar el flujo financiero por cuenta del Cliente,
pero siempre bajo la `PaymentPolicy` y el umbral aprobados.

## 22. Aprobaciones registradas y gates de implementación

El propietario resolvió por escrito:

1. email nullable sólo en `PENDING_CLAIM`, password inutilizable y claim
   verificado, sin alterar `USERNAME_FIELD` ni credenciales históricas;
2. normalización argentina, teléfono compartido permitido, revisión humana y
   ausencia de autofusión;
3. evidencia asistida separada, sin impersonación, firma o grabación ficticias;
4. medio `WEB/TELEFONO/PRESENCIAL` separado del canal y actor históricos;
5. primer slot futuro, grilla y TTL vigentes, sin tolerancia ni backdating;
6. `registrar_llegada` como inicio de atención y `EN_PROCESO` finalizable;
7. la misma `PaymentPolicy` para todos los medios, sin excepción presencial;
8. D-08 no aplicable: sin pago posterior, permiso nuevo, policy de excepción ni
   BH-061 v2 por esta causa.

Los gates técnicos de cada incremento —migraciones reversibles, permisos
efectivos, contratos HTTP, pruebas PostgreSQL y regresión— deben validarse antes
de implementar. No reabren estas decisiones ni autorizan interpretar datos
históricos, conceder permisos o adelantar código desde este documento.

## 23. Regresión requerida para incrementos futuros

- registro público con email, login exacto/normalizado, JWT y recuperación;
- alta administrativa histórica con contraseña temporal mientras siga vigente;
- roles/fingerprints/no-op/correlación BH-061 y sesión BH-062;
- riesgo web, warning owner-only, revisión y policy BH-057;
- disponibilidad, hold, consumo, reprogramación y concurrencia;
- policy, Intent, Pagos manuales/externos, conciliación y casos BH-058;
- llegada, fichas, finalización, efectos y automatizaciones profesionales 0–5;
- agenda global, Operaciones, Mi agenda laboral y trabajo técnico;
- stock/órdenes para demostrar separación de dominios.

Las pruebas concurrentes deben usar PostgreSQL real. El Incremento 0 no ejecuta
suites completas porque no modifica código.

## 24. Resultado del Incremento 0

El diseño establece una frontera conservadora:

- no-email no significa email falso ni Usuario inactivo;
- solicitud asistida no significa impersonación;
- presencia no significa exención de pago;
- registrar Pago no significa autorizar excepción;
- hold no significa Turno;
- llegada no debe impedir la finalización;
- teléfono coincidente no significa la misma persona;
- una decisión aprobada no significa una capacidad ya implementada.

Las decisiones D-01 a D-07 quedaron aprobadas y D-08 fuera del alcance actual.
Los contratos objetivo y la alternativa futura no financiera permanecen
claramente separados del comportamiento implementado. No se inicia ningún
incremento de implementación.

**BH-063/BH-064 INCREMENTO 0 = CERRADO DOCUMENTALMENTE**
