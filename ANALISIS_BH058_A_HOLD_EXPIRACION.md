# BH-058 A — SlotHold, expiración y concurrencia de agenda

Fecha del análisis: 2026-10-25
Alcance: diseño y auditoría de agenda. No se modificó implementación y no se
analizan pagos, caja, stock comercial ni integraciones financieras, salvo la
frontera mínima de que un flujo posterior podrá consumir un HOLD.

## 1. Conclusión ejecutiva

`SolicitudTecnicaReserva` debe continuar siendo una intención no bloqueante.
Cuando está `APROBADA_TECNICAMENTE`, un servicio transaccional nuevo debe poder
crear un agregado `SlotHold` distinto de `Turno`. El HOLD reservará durante un
TTL corto un intervalo de Personal, el intervalo del Cliente y capacidad por
tipo de equipamiento.

La validez no puede depender de que un job haya actualizado la fila:

```text
hold bloqueante := state = ACTIVE AND expires_at > now
```

Por ello, una fila todavía marcada `ACTIVE` pero con `expires_at <= now` ya no
bloquea disponibilidad y jamás puede consumirse. El job sólo materializa
`EXPIRED`, genera trazabilidad y reduce deuda de filas vencidas.

La creación, reprogramación y consumo de cualquier compromiso de agenda deben
usar el mismo servicio de disponibilidad y el mismo protocolo de locks. Agregar
consultas a `SlotHold` sin un protocolo común no resolvería las carreras.

`limpiar_turnos` no es apropiado como motor de HOLD. Debe mantenerse
temporalmente como compatibilidad de estados legacy de `Turno`, corregido y
aislado del expirador de HOLD.

---

## 2. Inventario actual de disponibilidad

### 2.1 Fuente canónica

`gestion/turno_creation_services.py` contiene
`TurnoAvailabilityService`, que hoy:

1. obtiene `HorarioLaboral` activo y vigente para el día;
2. filtra Personal activo y compatible con las habilidades de todos los
   Servicios;
3. valida que el intervalo completo entre en el horario;
4. rechaza slots pasados y fuera de `max_dias_anticipacion`;
5. detecta solapamientos de Turnos del mismo Personal;
6. detecta `BloqueoAgenda` del Personal o global;
7. calcula capacidad agregada de equipamiento obligatorio por tipo;
8. genera slots según `Configuracion.intervalo_turnos`.

Las rutas principales que delegan en esa lógica son:

- `GET /api/gestion/disponibilidad/` mediante
  `DisponibilidadTurnosView`;
- `GET /api/gestion/turnos/consultar_disponibilidad/`;
- `_generar_slots_disponibles`, usado también para recomendaciones;
- creación mediante `TurnoCreationService.create`;
- reprogramación mediante `turno_management_services`.

Consultar disponibilidad es sólo una observación. Entre el GET y la operación
de escritura otro proceso puede ocupar el intervalo; la escritura siempre debe
adquirir locks y volver a validar.

### 2.2 Superficies legacy o parciales

Persisten métodos duplicados en `TurnoViewSet`, como `_validar_slot_libre` y
`_verificar_disponibilidad_equipamiento`. Parte del flujo ya delega al servicio
canónico, pero la implementación duplicada usa una lista de estados distinta y
no debe ampliarse para HOLD.

`obtener_disponibilidad_calendario` es aún más débil: expone horarios y
bloqueos para que el frontend derive un calendario. No considera ocupación de
Turnos ni capacidad y no puede representar disponibilidad autoritativa.

La recomendación originada por diagnóstico consulta disponibilidad canónica,
pero luego crea directamente un `Turno.SUGERIDO`, fuera de
`TurnoCreationService` y sin locks/revalidación transaccional. Ese estado
bloquea agenda indefinidamente y constituye una ruta legacy que debe retirarse
del conjunto de escritores de agenda.

### 2.3 Intervalos y duración

La disponibilidad calcula el fin como:

```text
fin = fecha + hora_inicio + duración total en minutos
```

Un Turno existente obtiene su duración de la suma de `DetalleTurno`; usa 60
minutos como fallback. Para múltiples Servicios se usa la suma de sus detalles.
`hora_fin_calculada` no es la fuente canónica del conflicto y casi nunca se
completa en la creación actual.

Los solapamientos usan correctamente intervalos semiabiertos:

```text
nuevo_inicio < existente_fin AND nuevo_fin > existente_inicio
```

Por tanto, que uno termine exactamente cuando otro comienza no es conflicto.
El primer incremento debería rechazar intervalos que crucen de día hasta que
exista soporte explícito de horarios nocturnos.

---

## 3. `ACTIVE_TURNO_STATES` y estados legacy

La constante canónica contiene:

```text
SOLICITADO
ESPERANDO_SENA
CONFIRMADO
SUGERIDO
PENDIENTE
EN_PROCESO
```

| Estado | Bloquea Personal/equipamiento | Situación actual |
|---|---:|---|
| `solicitado` | Sí | Puede bloquear desde que se crea hasta cancelación o fecha pasada. |
| `esperando_sena` | Sí | Tiene `fecha_limite_pago` sólo si la transición pasó por lógica legacy específica. |
| `confirmado` | Sí | Reserva operativa real. |
| `sugerido` | Sí | Puede ser creado por diagnóstico y no tiene expiración observada. |
| `pendiente` | Sí | Semántica ambigua y sin TTL propio. |
| `en_proceso` | Sí | Ocupación operativa correcta. |
| `realizado`, `cancelado`, `ausente` | No | Estados no bloqueantes. |

BH-058 A no debe redefinir todavía la dimensión financiera. La frontera mínima
es:

- no crear un `Turno` como sustituto de un HOLD;
- no reutilizar `esperando_sena` ni `pendiente` para representar el HOLD;
- el consumo futuro del HOLD creará exactamente un Turno mediante un contrato
  de dominio; este análisis no decide la condición financiera que autoriza a
  invocarlo.

La restricción actual de `Turno`:

```text
unique_together(fecha, hora_inicio, cliente)
```

es demasiado amplia y demasiado estrecha a la vez:

- incluye Turnos cancelados o realizados, por lo que puede impedir reutilizar
  el mismo inicio aunque ya no bloqueen;
- sólo protege igualdad de inicio del Cliente, no solapamientos;
- no protege al Personal ni capacidad de equipamiento.

Antes de consumir HOLDs de forma confiable deberá sustituirse por una
restricción coherente con estados bloqueantes y una validación de intervalo del
Cliente bajo lock.

---

## 4. Conflictos que debe modelar la agenda

### 4.1 Personal

No puede existir solapamiento entre:

- Turno bloqueante y Turno bloqueante;
- Turno bloqueante y HOLD vigente;
- HOLD vigente y HOLD vigente;
- cualquiera de los anteriores y `BloqueoAgenda` aplicable.

Además, al crear y consumir se validan actividad, habilidad, horario laboral y
flags del horario. La disponibilidad debe ignorar HOLDs liberados, consumidos o
expirados lógica o materialmente.

### 4.2 Cliente

El Cliente no debe mantener dos compromisos solapados aunque sean con distinto
Personal. La implementación actual sólo comprueba misma fecha y misma hora de
inicio. BH-058 A debe elevarlo a conflicto por intervalo entre Turnos y HOLDs.

Una solicitud técnica por sí sola nunca participa de esta consulta.

### 4.3 Equipamiento

La capacidad se administra por `TipoEquipamiento`, no por una unidad asignada a
cada Turno. Para cada intervalo:

```text
ocupación de Turnos
+ reservas de HOLDs vigentes
+ cantidad requerida por el nuevo compromiso
<= unidades activas y DISPONIBLES del tipo
```

La regla actual consolida múltiples Servicios con `max(cantidad_minima)` por
tipo, no con suma. El HOLD debe capturar esa misma política en su snapshot para
no cambiar silenciosamente de capacidad durante su vida.

Bloquear sólo filas existentes de `Equipamiento`, como hoy, tiene una brecha si
no existe ninguna unidad o si una unidad se crea concurrentemente. El mutex de
capacidad recomendado es la fila `TipoEquipamiento`; las mutaciones de unidades
de ese tipo también deben respetarlo.

---

## 5. Estado actual de locking y carreras

### 5.1 Fortalezas

`TurnoCreationService.create` usa `transaction.atomic` y bloquea:

- Cliente;
- Servicio;
- Personal;
- unidades de equipamiento de tipos requeridos.

Luego comprueba duplicado de Cliente y vuelve a validar disponibilidad. La
reprogramación bloquea Turno, Cliente, Personal y equipamiento y también
revalida.

En PostgreSQL, bloquear la fila de Personal serializa dos escrituras canónicas
para el mismo profesional, aun cuando inicialmente no exista ningún Turno en el
intervalo. Esto evita depender de bloquear una consulta vacía.

### 5.2 Brechas

- El lock sólo es eficaz si todos los escritores siguen el mismo protocolo.
- El `Turno.SUGERIDO` del diagnóstico evita el servicio canónico.
- `BloqueoAgenda`, horarios y cambios de equipamiento no participan hoy de un
  protocolo común con reservas.
- Las consultas no conocen HOLDs.
- No hay tests reales de concurrencia con conexiones independientes; los tests
  actuales validan comportamiento funcional.
- Bloquear un `Personal` serializa todas sus fechas y es correcto pero grueso.
- El lock de unidades no funciona como mutex estable de capacidad cero ni
  protege altas concurrentes; es preferible bloquear `TipoEquipamiento`.
- Ningún constraint de base impide por sí solo intervalos solapados de Personal.

No se recomienda un constraint de exclusión condicionado por
`expires_at > now`: PostgreSQL no puede basar de forma estable el predicado de
un índice en el reloj. Una fila `ACTIVE` vencida también seguiría ocupando un
constraint parcial por estado. La corrección debe provenir del protocolo de
locks más normalización defensiva; los constraints protegen estructura y
cardinalidad, no el paso del tiempo.

---

## 6. Modelo mínimo recomendado

### 6.1 `SlotHold`

Campos mínimos:

| Campo | Propósito |
|---|---|
| `id` opaco/UUID | Identidad no predecible del HOLD. |
| `solicitud` FK `PROTECT` | Solicitud aprobada que lo originó. |
| `evaluacion` FK `PROTECT` | Evaluación aprobada exacta; evita consumir aprobación superada. |
| `cliente` FK `PROTECT` | Recurso Cliente bloqueado y snapshot relacional. |
| `personal` FK `PROTECT` | Personal reservado. |
| `starts_at`, `ends_at` | Intervalo aware e inmutable del compromiso. |
| `state` | `ACTIVE`, `CONSUMED`, `RELEASED`, `EXPIRED`. |
| `expires_at` | Vencimiento fijo, aware e inmutable. |
| `created_at`, `created_by` | Trazabilidad de creación. |
| `consumed_at`, `released_at`, `expired_at` | Timestamp de la transición terminal correspondiente. |
| `release_reason` | Causa acotada de liberación/invalidez. |
| `consumed_turno` OneToOne nullable | Turno producido, si fue consumido. |
| `idempotency_key` | Retry seguro de creación/consumo según contrato. |

No debe existir `updated_at` como sustituto de timestamps semánticos. Los datos
de intervalo, origen y snapshots son inmutables; sólo se permite una transición
terminal controlada.

### 6.2 Snapshots relacionados

Se recomiendan tablas hijas, no un JSON opaco para todo:

- `SlotHoldService`: Servicio, orden, nombre snapshot y duración en minutos;
- `SlotHoldEquipmentRequirement`: Tipo de equipamiento y cantidad reservada.

Esto permite consultar capacidad con índices y conserva el contrato aunque
cambien nombre, duración o requisitos del Servicio. No hace falta capturar
precios ni datos financieros para BH-058 A.

### 6.3 Constraints e índices

- `starts_at < ends_at`;
- `created_at < expires_at` y `expires_at <= starts_at` como regla de servicio;
- un solo HOLD con estado `ACTIVE` por solicitud;
- como máximo un HOLD `CONSUMED` por solicitud;
- `consumed_turno` único y presente sólo en `CONSUMED`;
- timestamps terminales coherentes con su estado;
- requerimiento único por `(hold, tipo_equipamiento)`;
- Servicio único por `(hold, servicio)` conservando orden;
- índice `(state, expires_at)` para el worker;
- índices de intervalo por Personal y Cliente;
- índice por tipo de equipamiento desde la tabla hija.

El unique parcial de `ACTIVE` considera también una fila vencida aún no
materializada. Al pedir otro HOLD para la misma solicitud, el servicio debe
bloquear la solicitud, marcar defensivamente como `EXPIRED` el HOLD vencido y
recién después insertar el nuevo.

### 6.4 TTL

Agregar a `Configuracion` un campo específico, por ejemplo
`slot_hold_ttl_minutes`, positivo, con default recomendado de **15 minutos** y
un máximo operativo validado. No reutilizar `tiempo_limite_pago_sena`, que está
expresado en horas y pertenece a semántica legacy distinta.

Al crear:

```text
created_at = reloj autoritativo del backend/base
expires_at = min(created_at + TTL snapshot, starts_at)
```

La creación se rechaza si no queda una ventana positiva. Cambiar la
configuración afecta HOLDs nuevos, nunca extiende implícitamente uno existente.
Una extensión futura debe ser una operación explícita, limitada y auditada; no
forma parte del primer incremento.

---

## 7. Máquina de estados e invariantes

Transiciones permitidas:

```text
ACTIVE -> CONSUMED
ACTIVE -> RELEASED
ACTIVE -> EXPIRED
```

Los cuatro estados son persistidos. Los tres últimos son terminales.

Invariantes:

1. `SolicitudTecnicaReserva` nunca bloquea recursos.
2. Sólo `SlotHold(state=ACTIVE, expires_at > now)` bloquea.
3. `expires_at <= now` significa vencido, aunque el worker no haya corrido.
4. Un HOLD vencido nunca se consume.
5. Un HOLD consumido produce exactamente un Turno y conserva el vínculo.
6. Liberar o expirar repetidamente no duplica efectos.
7. Una transición terminal nunca vuelve a `ACTIVE`.
8. El frontend sólo muestra tiempos; no decide vigencia ni envía un estado
   confiable.
9. Crear y consumir adquieren locks y revalidan después de adquirirlos.
10. Los snapshots de duración y capacidad no mutan durante la vida del HOLD.

La API puede devolver `effective_state=EXPIRED` cuando encuentre un `ACTIVE`
vencido, sin que un GET necesite escribir. Toda operación de escritura sí debe
normalizar la fila bajo lock.

---

## 8. Integración con disponibilidad

`TurnoAvailabilityService` debe evolucionar a un servicio de disponibilidad de
agenda y aceptar exclusiones explícitas:

- `exclude_turno_id` para reprogramación;
- `exclude_hold_id` para consumir el propio HOLD.

Cada validación debe considerar conjuntamente:

```text
Turno.estado IN ACTIVE_TURNO_STATES
OR
SlotHold.state = ACTIVE AND SlotHold.expires_at > now
```

Esto aplica a Personal, Cliente y equipamiento. La generación pública de slots
usa la misma lectura, pero sigue sin garantizar reserva.

Al consumir no puede existir un instante visible sin protección. Dentro de una
sola transacción se bloquea y se revalida excluyendo el propio HOLD. El Turno y
sus detalles se preparan sin hacer commit y la transición condicional a
`CONSUMED` enlaza ese Turno en el mismo paso. Otros procesos sólo ven el estado
anterior completo o el nuevo completo.

El Turno creado debe pasar por un único servicio de dominio. BH-058 A no debe
aceptar desde el cliente un estado financiero ni marcarlo confirmado por sí
solo; esa autorización pertenece a un orquestador posterior.

---

## 9. Estrategia de locks

### 9.1 Orden común

Para reducir deadlocks, todas las operaciones nuevas deben usar orden estable:

1. `SolicitudTecnicaReserva`, cuando exista;
2. `SlotHold`, cuando ya exista;
3. Cliente;
4. Servicios en orden de PK;
5. Personal;
6. `TipoEquipamiento` requeridos en orden de PK;
7. unidades de equipamiento sólo si una operación necesita modificarlas.

Turnos sin solicitud comienzan en Cliente y mantienen desde allí el mismo
orden. La reprogramación primero bloquea su Turno objetivo, como agregado que
va a mutar, y luego respeta Cliente → Servicios → Personal → tipos.

### 9.2 Creación de HOLD

En `transaction.atomic`:

1. bloquear la solicitud y verificar estado `APROBADA_TECNICAMENTE`;
2. comprobar que `evaluacion_vigente` coincide con la aprobación a capturar;
3. bloquear Cliente, Servicios, Personal y tipos de equipamiento;
4. usar un `now` nuevo después de cualquier espera de lock;
5. materializar como `EXPIRED` el HOLD previo vencido de esa solicitud;
6. si existe HOLD vigente con el mismo payload/idempotency key, devolverlo;
7. si existe otro HOLD vigente de esa solicitud, devolver conflicto;
8. revalidar horarios, skill, bloqueos, Turnos y HOLDs;
9. insertar snapshots y HOLD `ACTIVE`;
10. registrar evento de auditoría en la misma transacción.

### 9.3 Consumo

En `transaction.atomic`:

1. bloquear solicitud y HOLD;
2. si ya está consumido por la misma operación, devolver el mismo Turno;
3. bloquear Cliente, Servicios, Personal y tipos;
4. revalidar solicitud, evaluación y recursos;
5. si un reloj nuevo ya alcanzó `expires_at`, cambiar a `EXPIRED` y devolver el
   resultado sin lanzar una excepción que revierta esa transición;
6. dentro de un savepoint, crear Turno y detalles desde snapshots, todavía sin
   commit externo;
7. actualizar el HOLD en una única sentencia que establezca `CONSUMED`,
   `consumed_turno` y `consumed_at`, condicionada por
   `state=ACTIVE AND expires_at > database_now`;
8. si no actualizó una fila, revertir el savepoint —incluido el Turno—,
   materializar `EXPIRED` cuando corresponda y devolver conflicto;
9. crear la auditoría y confirmar todo junto.

El timestamp de los pasos 5 y 7 debe provenir del backend/base y obtenerse después de
esperar locks. En PostgreSQL conviene un reloj de statement, no un timestamp
congelado al inicio de una transacción larga.

Si se materializa `EXPIRED` durante un intento de consumo, el servicio no debe
lanzar una excepción que haga rollback de esa transición. Debe confirmar el
estado y devolver un resultado de dominio que la capa API traduzca a conflicto.

### 9.4 Mutaciones administrativas

Crear `BloqueoAgenda`, desactivar Personal, cambiar horarios o reducir
equipamiento puede invalidar compromisos. Esas operaciones deben adquirir los
mismos mutex. Para un bloqueo global se bloquean todos los Personal afectados
en orden o, en una evolución, un mutex estable de agenda.

El esquema con filas existentes es correcto pero grueso. Si la carga exige más
paralelismo, puede introducirse una tabla `AgendaResourceMutex` por recurso y
día. No es necesaria para el primer incremento.

---

## 10. Resolución de escenarios obligatorios

### A. Dos solicitudes intentan el mismo slot

Las solicitudes coexisten porque no bloquean. Al crear HOLD, ambos procesos
compiten por la misma fila de Personal y, si aplica, tipos de equipamiento. El
primero revalida e inserta. El segundo despierta, usa un `now` nuevo, ve el HOLD
vigente y recibe `SLOT_UNAVAILABLE`. Sólo queda un HOLD bloqueante.

Si son distintos profesionales pero compiten por la última unidad de un tipo,
el lock de `TipoEquipamiento` produce el mismo resultado. Si es el mismo
Cliente con distintos profesionales, serializa el lock del Cliente.

### B. El HOLD vence y el job todavía no corrió

La fila puede seguir en `ACTIVE`, pero no aparece en ninguna consulta de
ocupación porque `expires_at <= now`. Una escritura que la encuentra la
normaliza a `EXPIRED`; el worker lo hará posteriormente si nadie escribe.

### C. Intento de consumir un HOLD vencido

Se bloquea la fila, se compara contra un reloj nuevo y falla la actualización
condicional. Se materializa `EXPIRED` de forma idempotente, no se crea Turno y
la API devuelve un conflicto estable como `HOLD_EXPIRED`.

### D. Dos procesos intentan consumir el mismo HOLD

`select_for_update` serializa ambos. El primero crea y enlaza un único Turno.
El segundo observa `CONSUMED`: si es retry de la misma operación devuelve ese
Turno; si es otra intención, responde `HOLD_ALREADY_CONSUMED`. Nunca crea un
segundo Turno.

### E. Liberación repetida

La primera llamada hace `ACTIVE -> RELEASED` y audita. Repetir con la misma
clave devuelve `changed=false`, sin nueva auditoría ni notificación. Si ya está
`EXPIRED`, también es no-op informativo; si está `CONSUMED`, liberar es un
conflicto y no cancela el Turno.

### F. Personal/equipamiento cambia después de crear el HOLD

Duración y cantidad reservada se mantienen por snapshot. Sin embargo, la
seguridad operacional se revalida al consumir:

- Personal inactivo, sin skill o cubierto por bloqueo: no consumir;
- capacidad operativa insuficiente por baja/mantenimiento: no consumir;
- cambio posterior de nombre/duración/requisito comercial: no reescribir el
  compromiso ya otorgado.

Idealmente la mutación administrativa detecta HOLDs afectados y la rechaza o
los libera explícitamente con causa `RESOURCE_INVALIDATED` y auditoría. Como
defensa final, consumo falla y libera/invalida el HOLD de forma semántica, sin
crear Turno. No debe quedar bloqueando hasta el TTL si ya se sabe imposible.

### G. La solicitud técnica deja de estar vigente

Una reevaluación, rechazo, vencimiento o estado distinto de
`APROBADA_TECNICAMENTE` invalida el derecho a consumir. La transición de la
solicitud debe bloquear solicitud y HOLD en el orden común y liberar el HOLD
con causa `TECHNICAL_REQUEST_INVALIDATED`.

Aunque esa liberación no haya ocurrido por fallo, consumo compara solicitud,
evaluación vigente y evaluación snapshot y falla de forma segura. Nunca basta
con que el HOLD todavía diga `ACTIVE`.

---

## 11. Idempotencia y respuestas

Operaciones mínimas:

| Operación | Retry esperado |
|---|---|
| crear mismo HOLD | Devuelve HOLD vigente existente. |
| crear payload distinto con HOLD vigente | Conflicto; no reemplaza silenciosamente. |
| expirar vencido | Primera transición cambia; siguientes `changed=false`. |
| liberar liberado | `changed=false`. |
| consumir ya consumido con misma clave | Devuelve el mismo Turno. |
| consumir ya consumido con otra clave | Conflicto. |
| consumir vencido/liberado | Conflicto, cero Turnos. |

Las claves de idempotencia deben persistirse y tener constraint único en su
ámbito. Comparar sólo el payload en memoria no protege retries concurrentes.

Los eventos semánticos sugeridos son `SLOT_HOLD_CREATED`,
`SLOT_HOLD_CONSUMED`, `SLOT_HOLD_RELEASED` y `SLOT_HOLD_EXPIRED`, con HOLD,
solicitud, evaluación, Cliente, Personal, intervalo, estado anterior/nuevo,
causa, actor o actor de sistema y timestamp. No deben depender sólo del estado
mutable actual.

---

## 12. Auditoría de HALLAZGO-TURNOS-02: `limpiar_turnos`

Archivo: `gestion/management/commands/limpiar_turnos.py`.

### 12.1 Qué afecta

Lógica 1 cancela si el inicio del Turno ya pasó:

```text
fecha < hoy OR (fecha = hoy AND hora_inicio < hora_actual)
estado IN solicitado, esperando_sena, pendiente
```

Lógica 2 cancela:

```text
estado = esperando_sena
AND fecha_limite_pago < ahora
```

No afecta `sugerido`, aunque ese estado bloquea; tampoco afecta confirmado,
en proceso, realizado, cancelado o ausente. Usa inicio, no fin del Turno. En el
límite exacto usa `<`, por lo que vencerá en una ejecución posterior.

### 12.2 Problemas temporales

Con `USE_TZ=True`, `timezone.now()` es aware en UTC. El command usa directamente
`ahora.date()` y `ahora.time()` contra `Turno.fecha/hora_inicio`, que representan
hora local de negocio. Debe convertir una sola vez con `timezone.localtime`
antes de separar fecha y hora.

Carga `Configuracion.objects.first()` pero no usa `config`. El plazo sólo se
aplica si `fecha_limite_pago` fue completado por otro flujo.

### 12.3 Quién puede ejecutarlo

Es un management command. No existe endpoint, action ni llamada interna que lo
exponga. No aplica permisos de Django ni autorización de negocio: puede
ejecutarlo quien tenga acceso operativo a `manage.py`, al entorno y a la base.

No se encontró Celery, beat, django-crontab, APScheduler, definición de cron ni
configuración de plataforma que lo invoque. Por tanto, actualmente es manual o
depende de automatización externa no versionada en este repositorio.

### 12.4 Side effects

Por cada fila:

1. cambia `estado` a `cancelado` y ejecuta `save()`;
2. no completa `motivo_cancelacion` ni `cancelado_por`;
3. crea una notificación manual al Cliente;
4. crea otra al Personal si existe.

El `save()` también dispara el signal general de cambio de estado, que crea una
notificación de cancelación al Cliente. En consecuencia, el Cliente puede
recibir dos notificaciones por la misma cancelación.

El signal de auditoría genérica de `Turno` puede registrar el diff, y
simple-history conserva historia, pero no equivalen a una auditoría semántica
con causa estable y actor de sistema. Además, el registrador genérico captura
errores y continúa, por lo que no es garantía atómica.

### 12.5 Locking, atomicidad e idempotencia

- no usa `transaction.atomic`;
- no usa `select_for_update`;
- no hace update condicional por estado;
- dos ejecuciones concurrentes pueden seleccionar el mismo Turno;
- el estado final suele ser idempotente en ejecuciones secuenciales porque la
  siguiente ya no selecciona `cancelado`;
- concurrentemente puede duplicar notificaciones y auditorías;
- un fallo entre `save()` y notificaciones deja efectos parciales;
- un fallo entre las dos notificaciones deja destinatarios inconsistentes;
- no emite resumen, métricas, batch ni checkpoint.

### 12.6 Destino legacy

Debe conservar temporalmente sólo estas responsabilidades:

- drenar `solicitado`, `esperando_sena` y `pendiente` históricos cuyo inicio ya
  pasó;
- drenar `esperando_sena` histórico cuyo `fecha_limite_pago` venció.

No debe:

- expirar `SlotHold`;
- decidir vigencia de HOLD;
- convertirse en requisito para que disponibilidad libere un HOLD;
- incorporar más estados ambiguos sin una política de migración.

Debe refactorizarse para llamar a un servicio legacy transaccional con lock,
transición condicional, causa persistida, actor de sistema, auditoría y
notificación idempotente. La creación de nuevos `solicitado`, `sugerido`,
`pendiente` o `esperando_sena` como sustitutos de intención/HOLD debe cesar por
etapas. Cuando no queden productores ni filas legacy, el command se retira.

Los `sugerido` existentes requieren una migración/política puntual; añadirlos
silenciosamente a la limpieza cambiaría negocio y no corresponde a BH-058 A.

---

## 13. Estrategia futura de ejecución

### 13.1 Command periódico de HOLD

Crear un command separado conceptualmente, por ejemplo
`expirar_slot_holds`, que procese lotes:

```text
state = ACTIVE AND expires_at <= database_now
ORDER BY expires_at, id
SELECT FOR UPDATE SKIP LOCKED
ACTIVE -> EXPIRED mediante transición condicional
```

Cada lote usa una transacción corta. El command es seguro ante dos instancias y
ante reejecución. Debe informar examinados, expirados, omitidos, errores,
duración y antigüedad del vencido más viejo.

### 13.2 Scheduler/worker

El primer despliegue puede invocar el management command cada minuto desde el
scheduler de plataforma. Una evolución puede usar worker/beat cuando exista
infraestructura real. No se debe introducir una dependencia de scheduler sin
monitorización, política de retries y dueño operacional.

Scheduler y command son mecanismos de housekeeping, no fuentes de verdad.

### 13.3 Expiración defensiva

Debe aplicarse además en:

- consultas de disponibilidad: excluir por reloj;
- creación de otro HOLD: normalizar vencidos relevantes;
- consumo: update condicional contra reloj autoritativo;
- liberación/lectura operativa: reportar estado efectivo correcto.

### 13.4 Recuperación ante job caído

Si el job cae durante horas:

- ningún HOLD vencido bloquea lecturas o nuevas reservas;
- ningún HOLD vencido se consume;
- el siguiente job recupera todas las filas por índice;
- métricas alertan por `oldest_unmaterialized_expiry` y último éxito;
- no hace falta reconstruir disponibilidad desde memoria ni desde frontend.

---

## 14. Matriz de pruebas propuesta

### 14.1 Modelo y transiciones

- constraints de intervalo, timestamps, solicitud activa única y Turno único;
- snapshots inmutables;
- todas las transiciones válidas;
- rechazo de transiciones terminales a `ACTIVE`;
- liberación y expiración repetidas sin efectos duplicados;
- idempotency key única.

### 14.2 Disponibilidad

- HOLD vigente oculta el slot al mismo Personal;
- HOLD vencido no lo oculta aunque siga marcado `ACTIVE`;
- `RELEASED`, `EXPIRED` y `CONSUMED` no bloquean por sí mismos;
- límites semiabiertos: fin igual a inicio permitido;
- conflicto Cliente por solapamiento con distinto Personal;
- Turno contra HOLD y HOLD contra Turno;
- suma de duración de múltiples Servicios;
- capacidad de equipamiento combinando Turnos y HOLDs;
- capacidad exacta permitida y exceso rechazado;
- `BloqueoAgenda`, horario, Personal inactivo y skill incompatible;
- endpoint canónico y alias entregan el mismo resultado;
- ruta calendario se documenta como no autoritativa o deja de calcular en
  frontend.

### 14.3 Concurrencia real

Usar `TransactionTestCase`, PostgreSQL, conexiones separadas, barreras y
threads/procesos; no mocks de `select_for_update`:

- escenario A: dos HOLDs, exactamente un éxito;
- dos profesionales y una unidad de equipamiento, un éxito;
- mismo Cliente, distintos profesionales, un éxito si se solapan;
- crear Turno contra crear HOLD;
- reprogramar Turno contra crear HOLD;
- dos consumos, un solo Turno;
- consumir contra expirar en el límite;
- consumir contra liberar;
- invalidar solicitud contra consumir;
- crear bloqueo/desactivar Personal contra consumir;
- ausencia de deadlock bajo el orden documentado.

Los tests deben verificar estado persistido, cantidad de Turnos, auditorías y
notificaciones, no sólo códigos HTTP.

### 14.4 Reloj y expiración

- `now < expires_at`, `now == expires_at`, `now > expires_at`;
- TTL snapshot y cambio posterior de configuración;
- `expires_at` limitado por `starts_at`;
- espera de lock que atraviesa el vencimiento;
- zona horaria de negocio y cambio de fecha local;
- job caído: lectura y consumo siguen seguros;
- worker en batch, `skip_locked`, retries y recuperación tras fallo intermedio.

### 14.5 Solicitud y recursos

- sólo `APROBADA_TECNICAMENTE` con evaluación vigente crea HOLD;
- una solicitud no altera disponibilidad antes de crear HOLD;
- reevaluación/rechazo/vencimiento libera e impide consumo;
- Servicio cambia después: snapshots permanecen;
- Personal inactivo o bloqueado después: consumo falla y libera con causa;
- reducción/mantenimiento de equipamiento: nunca sobreconsume.

### 14.6 `limpiar_turnos` legacy

- cada estado afectado y cada estado excluido;
- vencimiento por fecha local y por `fecha_limite_pago`;
- límites exactos;
- motivo y actor de sistema persistidos;
- dos commands concurrentes no duplican transición, auditoría ni notificación;
- fallo parcial recuperable;
- sin notificación doble por signal más command;
- no lee ni modifica `SlotHold`;
- no existe endpoint público o autenticado para ejecutarlo.

---

## 15. Decisiones finales

### Arquitectura SlotHold recomendada

Agregar un agregado `SlotHold` separado de `Turno` y de
`SolicitudTecnicaReserva`, con snapshots relacionales de Servicios, duración y
capacidad de equipamiento. Sólo `ACTIVE` y no vencido bloquea; `CONSUMED`,
`RELEASED` y `EXPIRED` son terminales. La solicitud aprobada habilita crear el
HOLD, pero nunca bloquea por sí misma.

### Estrategia de locks

Usar transacciones PostgreSQL, `select_for_update` y orden estable: solicitud,
HOLD, Cliente, Servicios, Personal y tipos de equipamiento. Toda creación,
reprogramación, bloqueo administrativo y consumo debe usar el mismo protocolo
y revalidar después del lock. El primer incremento puede aceptar la
serialización gruesa por Personal; no debe aceptar escritores legacy fuera del
servicio.

### Estrategia de expiración

La regla autoritativa es `ACTIVE AND expires_at > now`. Combinar un command
periódico idempotente en lotes, ejecución por scheduler/worker monitorizado y
defensas en lectura, creación y consumo. El scheduler materializa y audita; no
otorga seguridad.

### Destino de `limpiar_turnos`

Mantenerlo temporalmente como compatibilidad exclusiva de Turnos legacy,
refactorizado hacia transiciones atómicas, locks, hora local, causa, actor de
sistema y side effects idempotentes. Nunca usarlo para HOLD. Retirarlo cuando
se eliminen productores y datos de estados pre-reserva legacy.

### Riesgos

- escritores directos o duplicados que no adopten el protocolo común;
- restricción actual de Turno incompatible con reutilización de slots finales;
- `sugerido` bloqueante sin TTL;
- deadlocks si cambia el orden de locks;
- capacidad incorrecta si mutaciones de equipamiento no bloquean el tipo;
- reloj/zona horaria inconsistente;
- notificaciones o auditorías duplicadas por signals;
- job sin monitorización;
- invalidación técnica o de recursos no propagada al HOLD.

### Primer incremento de implementación

1. Migración de `SlotHold`, snapshots, constraints, índices y
   `slot_hold_ttl_minutes`.
2. Servicio puro de transiciones y auditoría, sin scheduler ni integración
   financiera.
3. Extensión única de disponibilidad para Turnos + HOLDs vigentes y conflicto
   por intervalo del Cliente.
4. Creación de HOLD sólo desde solicitud aprobada, con locks y revalidación.
5. Consumo idempotente y defensivo capaz de producir un único Turno sin decidir
   todavía autorización financiera.
6. Command separado de expiración, ejecutable manualmente y probado; la
   programación operativa queda para un incremento posterior.
7. Tests PostgreSQL de concurrencia A–G antes de habilitar el endpoint.
8. Aislar y corregir `limpiar_turnos` como deuda legacy, sin conectarlo al
   ciclo de vida de `SlotHold`.
