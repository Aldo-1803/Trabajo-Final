# Análisis conjunto BH-063/BH-064 — Turnos y altas presenciales

**Fecha:** 2026-11-19

**Baseline funcional analizado:** `2de633ce5d0008ff7ee127fb6aafab27bff83113`

**HEAD documental verificado:** `07e581045b1d6d4f46df046c38a20d73c46d7eeb`

**Estado:** análisis técnico-funcional; sin implementación

> **Nota de cierre del 2026-11-20:** este análisis conserva el estado previo a
> la decisión del propietario. D-01 a D-07 fueron aprobadas y D-08 fue declarada
> no aplicable al alcance actual en
> [BH-063/BH-064 — Incremento 0: decisiones y contratos](DECISIONES_Y_CONTRATOS_BH063_BH064.md).
> Las menciones a decisiones “pendientes” dentro del cuerpo son trazabilidad del
> análisis antecedente, no el estado contractual vigente.

## 1. Objetivo, alcance y límites

Este documento analiza en conjunto:

- **BH-063:** registrar, por Personal autorizado, un Turno asistido para un
  Cliente existente;
- **BH-064:** dar de alta una identidad básica de Cliente presencial y continuar
  al Turno sin inventar ni exigir un diagnóstico capilar universal.

Se inspeccionaron modelos, servicios, permisos efectivos, APIs, React, pruebas y
documentación de Usuarios, Clientes, Personal, agenda, riesgo técnico, holds,
pagos, trabajo profesional y flujos cerrados.

Este análisis **no** implementa APIs, modelos, migraciones, permisos, tests ni
pantallas; no cambia pagos, stock, diagnóstico, recomendaciones, BusinessRole,
grants ni autoevaluaciones. Tampoco modifica BH-062, los flujos profesionales
cerrados, el backlog ni documentos históricos.

## 2. Resultado ejecutivo

BH-063 y BH-064 son viables de forma incremental, pero **no están resueltas por
las APIs actuales**.

1. `TurnoCreationService` aporta una validación de disponibilidad sólida para un
   Servicio, pero el comando asistido actual crea siempre un Turno
   `SOLICITADO`, no es idempotente, no soporta multiservicio público, no ejecuta
   el evaluador BH-057 y no deja una auditoría semántica suficiente del operador.
2. El recorrido moderno de reserva ya aporta las piezas más fuertes para
   multiservicio, riesgo, concurrencia e idempotencia:
   `SolicitudTecnicaReserva -> EvaluacionRiesgoTecnico -> SlotHold ->
   PaymentIntent/Pago -> Turno CONFIRMADO`.
3. Esas piezas no se pueden invocar sin adaptación: aceptar una advertencia y
   crear/liberar un `SlotHold` exigen hoy al Usuario propietario. El operador no
   debe suplantar al Cliente; hacen falta comandos asistidos explícitos,
   autorizados y auditados.
4. La primitiva `create_confirmed_turno_from_locked_hold()` garantiza consumo
   único, pero declara expresamente que **no es autorización financiera**. No
   puede exponerse como “confirmar gratis”.
5. La política recomendada es la alternativa **C**: evaluar riesgo y reservar
   capacidad siempre; confirmar según riesgo y política financiera. El Turno se
   crea `CONFIRMADO` sólo en el punto terminal autorizado, no antes.
6. El alta administrativa existente crea atómicamente Usuario, Cliente, rol
   `CLIENTE` y auditoría, pero exige email y contraseña temporal, activa la
   cuenta y no es idempotente. Es base parcial, no BH-064.
7. Un Cliente puede existir con los cinco campos capilares nulos y sin
   `DiagnosticoCapilar`. Esto ya es compatible con el trabajo profesional. La
   falta de diagnóstico no equivale a “saludable”; el evaluador aplica la
   política publicada de cada Servicio.
8. El caso “sin email” requiere separar identidad comercial de acceso web. No se
   recomienda inventar un email de contacto ni entregar una contraseña conocida
   por el operador. Debe existir un acceso **pendiente de reclamo**, con
   contraseña inutilizable hasta verificar un contacto.
9. `registrar_llegada` produce `EN_PROCESO`, mientras la finalización sólo admite
   `CONFIRMADO`. Esta incompatibilidad ya existente debe resolverse antes de
   adoptar `EN_PROCESO` como recorrido oficial; BH-063 no debe crearlo
   anticipadamente.

No hay un bloqueante para planificar. Sí hay decisiones funcionales que son
condiciones de inicio de determinados incrementos.

## 3. Separación A/B/C/D

### A. Comportamiento implementado

| Área | Contrato comprobado |
|---|---|
| Identidad | `Usuario.email` es único, obligatorio y `USERNAME_FIELD`; `Cliente` es 1:1 y usa el PK del Usuario. |
| Perfil capilar | Los cinco campos de `Cliente` son anulables; no se crea automáticamente un diagnóstico. |
| Alta por Personal | `create_client_account_by_staff()` exige `usuarios.create_walkin_client`, email, nombre, apellido, contraseña temporal válida y motivo. Crea Usuario activo, Cliente activo, rol `CLIENTE` y auditoría en una transacción. |
| Consulta de Clientes | `usuarios.view_clients` protege el listado general. El selector de Turnos usa `gestion.create_turno_for_client` y devuelve id, nombre, apellido y email de todos los Clientes activos. |
| Creación asistida | `POST /turnos/crear-para-cliente/` exige `gestion.create_turno_for_client`, acepta un Servicio, Cliente, Personal, fecha y hora, usa canal `PRESENCIAL` y crea `SOLICITADO`. |
| Disponibilidad | Se validan Cliente, Servicio, Personal, habilidad, jornada, bloqueos, superposición de Cliente/Personal, holds activos, equipo obligatorio y horario futuro. Se bloquean filas relevantes dentro de una transacción. |
| Riesgo legacy | La creación calcula `alerta_daño_capilar` por categoría y espera mínima; no reemplaza BH-057. |
| Riesgo moderno | BH-057 evalúa uno o varios Servicios contra política versionada, diagnóstico e historial, con outcomes `APTO`, `ADVERTENCIA`, `REQUIERE_REVISION` y `NO_APTO`. Persiste evidencia inmutable. |
| Solicitud técnica | Conserva Servicios ordenados, evaluación vigente, advertencia/revisión y decisiones trazables. |
| Hold | `SlotHold` es multiservicio, idempotente, temporal, bloquea capacidad y equipamiento y se consume una sola vez. |
| Pago | La confirmación financiera aprobada consume el hold y crea un único Turno `CONFIRMADO`; pagos manuales y externos tienen permisos, identidades y conciliación propios. |
| Estados operativos | La llegada admite `CONFIRMADO -> EN_PROCESO`; la finalización admite sólo `CONFIRMADO -> REALIZADO`. |
| Agenda profesional | El Turno asignado aparece en agenda global o propia según permiso/ownership, independientemente del canal. |
| Trabajo técnico | `/turnos/:turnoId/trabajo-tecnico` depende de ownership, capabilities, estado y políticas del Servicio; no del canal ni de la existencia universal de diagnóstico. |

### B. Requisitos oficiales aún pendientes

- Crear un Turno asistido para un Cliente existente por teléfono, presencial o
  llegada sin reserva.
- Integrar riesgo técnico moderno sin omitir disponibilidad ni reglas del
  Servicio.
- Ser seguro ante concurrencia, timeout y reintentos.
- Definir confirmación coherente con pagos/señas y revisión técnica.
- Soportar varios Servicios si se aprueba ese alcance.
- Auditar operador, consentimiento, decisión técnica y fundamento de
  confirmación.
- Dar de alta un Cliente con datos mínimos, incluso cuando no dispone de email,
  sin diagnóstico inventado y con incorporación web posterior segura.
- Recuperar alta correcta + Turno fallido sin duplicar ni compensar borrando al
  Cliente.

### C. Defectos o incompatibilidades comprobados

| ID | Incompatibilidad | Consecuencia |
|---|---|---|
| C-01 | Creación asistida termina en `SOLICITADO`; ficha/finalización operativa requieren `CONFIRMADO`. | El recorrido queda incompleto. |
| C-02 | `TurnoCreationService.create()` no usa BH-057. | El canal asistido puede omitir política técnica publicada. |
| C-03 | API asistida acepta un único Servicio. | No cubre multiservicio ni riesgo agregado. |
| C-04 | No hay Idempotency-Key ni ledger de creación asistida. | Un timeout puede inducir reintento ambiguo o duplicado. |
| C-05 | `unique_together(fecha, hora_inicio, cliente)` no representa identidad de comando. | Evita sólo una forma de duplicado y no permite recuperar el resultado original. |
| C-06 | Aceptación de advertencia y hold exigen al Usuario propietario. | Recepción no puede reutilizarlos simulando al Cliente. |
| C-07 | Alta actual exige email y contraseña temporal. | No cubre Cliente sin email ni acceso pendiente seguro. |
| C-08 | Alta actual deduplica por email, no tiene idempotencia y no busca por teléfono/documento. | Reintentos y coincidencias humanas siguen ambiguos. |
| C-09 | Usuario y Cliente se activan juntos; riesgo/hold/Turno rechazan Usuario inactivo. | `is_active=False` no sirve para expresar sólo “web pendiente”. |
| C-10 | Selector de Clientes no busca por teléfono y devuelve el conjunto completo. | Usabilidad y minimización de datos insuficientes para escala. |
| C-11 | Turno no guarda `created_by`; la creación directa no emite evento semántico completo. | No queda demostrada toda la causalidad del operador. |
| C-12 | `PRESENCIAL` no distingue llamada telefónica de presencia física. | La procedencia queda imprecisa. |
| C-13 | Slots iniciados o pasados se rechazan con `PAST_SLOT`. | “Atención inmediata” requiere semántica de próximo intervalo; no admite backdating. |
| C-14 | Llegada produce `EN_PROCESO`, pero finalización lo rechaza. | Registrar llegada puede bloquear el cierre profesional. |
| C-15 | La aceptación de advertencia existente representa al Cliente autenticado. | Hace falta definir cómo se registra consentimiento asistido, sin firma ficticia. |

### D. Decisiones funcionales pendientes

Las decisiones D-01 a D-08 se detallan en la sección 16. Las recomendaciones de
este informe permiten iniciar contratos e idempotencia; los puntos de pago,
identidad sin email, consentimiento y `EN_PROCESO` deben ser aprobados antes de
publicar sus respectivos comandos.

## 4. Contratos reutilizables y fronteras

### 4.1 Reutilización directa

- permisos efectivos de BH-059/BH-060/BH-062 y su proyección de sesión;
- `service_skill_policy()` para compatibilidad AND de Personal y Servicios;
- `TurnoAvailabilityService` para jornada, bloqueos, superposición, holds y
  equipamiento;
- evaluación y persistencia versionada de BH-057;
- snapshots y decisiones de `SolicitudTecnicaReserva`;
- locks, expiración e idempotencia de `SlotHold`;
- consumo único del hold para construir Turno y `DetalleTurno`;
- confirmación financiera y pagos manuales/exteriores existentes;
- agenda global, agenda propia y serializers de lectura;
- permisos/capabilities y ownership del trabajo técnico;
- atomicidad de Usuario + Cliente + rol + auditoría del alta actual;
- patrón de ledgers idempotentes ya usado en checkout, pagos y finalización.

### 4.2 Reutilización con adaptación explícita

- la creación de solicitud técnica necesita un modo asistido autorizado;
- advertencias necesitan registrar aceptación informada del Cliente observada
  por un operador, no atribuirla al operador como si fuera el Cliente;
- hold y liberación necesitan scopes asistidos con
  `gestion.create_turno_for_client` y auditoría de actor/Cliente;
- consumo no financiero necesita una autorización de negocio explícita;
- alta necesita una variante idempotente y un estado de acceso web pendiente;
- selectores deben convertirse en búsquedas acotadas y minimizadas.

### 4.3 Contratos que no deben reutilizarse como atajo

- `alerta_daño_capilar` no sustituye la evaluación BH-057;
- `is_staff`, `is_superuser` o BusinessRole nominal no autorizan operaciones;
- `confirm_deposit` no autoriza confirmaciones sin pago;
- `create_confirmed_turno_from_locked_hold()` no autoriza financieramente;
- `estado` no debe exponerse como campo libre;
- no deben crearse un Pago, diagnóstico, aceptación o email de contacto
  ficticios para atravesar validaciones;
- no debe crearse `EN_PROCESO` al cargar el Turno.

## 5. Diferencias reales entre web y canal asistido

| Dimensión | Web | Asistido/presencial |
|---|---|---|
| Actor | Cliente autenticado propietario | Operador autenticado con permiso efectivo |
| Cliente | Derivado de sesión | Seleccionado mediante búsqueda minimizada o resultado de BH-064 |
| Intención | El Cliente expresa y acepta directamente | El operador registra una solicitud comunicada por el Cliente |
| Advertencia | El propietario acepta en su sesión | Debe registrarse consentimiento asistido con texto, momento y operador |
| Hold | Owner-only actual | Requiere variante asistida, sin impersonación |
| Contacto | Cuenta web ya reclamada | Puede no tener acceso web ni email |
| Pago | Checkout/flujo publicado | Puede usar el mismo pago o una excepción presencial explícita |
| Canal | `WEB` | Debe distinguir al menos teléfono de presencia si la auditoría lo requiere |
| Inmediatez | Selección futura | Próximo intervalo disponible del día; nunca omite locks o riesgo |
| Evidencia visible | Mensajes orientados al Cliente | Estado y mensajes mínimos; datos técnicos sólo con capability |

Las reglas técnicas, de habilidad, agenda, equipo y concurrencia **no cambian**
por canal. Sólo cambian actor, consentimiento, contacto y política financiera.

## 6. Recorrido objetivo BH-063

### 6.1 Cliente existente por teléfono o presencial

1. Comprobar sesión activa y `gestion.create_turno_for_client`.
2. Buscar por nombre, apellido y contacto normalizado; mostrar resultados
   mínimos y exigir selección explícita.
3. Seleccionar uno o varios Servicios activos.
4. Seleccionar fecha/hora y Personal compatible; la UI sólo orienta, backend
   vuelve a validar.
5. Crear/reutilizar una solicitud técnica idempotente para ese Cliente e
   intención, conservando actor y medio de solicitud.
6. Evaluar todos los Servicios con política publicada.
7. Resolver outcome según sección 8.
8. Crear un hold idempotente y revalidar capacidad bajo locks.
9. Aplicar la rama financiera/no financiera aprobada.
10. Consumir el hold una sola vez y crear el Turno `CONFIRMADO` con todos sus
    detalles.
11. Auditar operador, Cliente, solicitud, evaluación, hold, fundamento de
    confirmación y Turno.
12. Devolver siempre el mismo resultado ante el mismo Idempotency-Key y payload.

El Turno llega a agenda global y a `mi-agenda-laboral` por su `profesional`, sin
tratamiento especial por canal.

### 6.2 Llegada sin reserva y atención inmediata

“Inmediata” significa el **primer inicio futuro válido** según reloj de base de
datos, grilla comercial, duración total, jornada, bloqueos, habilidad, equipo y
reservas concurrentes.

- no se permite backdating ni crear un Turno después de iniciado el servicio;
- si el minuto de grilla actual ya comenzó, se usa el próximo intervalo;
- la disponibilidad visual nunca reserva capacidad: debe materializarse hold;
- riesgo y pago no se omiten por urgencia;
- no se crea `EN_PROCESO`; llegada/inicio ocurre por transición posterior;
- si el negocio necesita tolerancia de segundos o una grilla especial, debe
  definirla en D-05 y probarla con reloj de base de datos.

### 6.3 Matriz de los diez escenarios solicitados

| Escenario | Resultado objetivo |
|---|---|
| 1. Registrado por teléfono | Búsqueda, medio `TELEFONO`, riesgo, hold y confirmación condicionada. |
| 2. Registrado presencial | Igual, medio `PRESENCIAL`; no cambia reglas técnicas. |
| 3. Sin reserva, inmediato | Próximo slot futuro; 409 si pierde capacidad; no backdating. |
| 4. Perfil completo | El evaluador usa datos vigentes según política; no garantiza automáticamente `APTO`. |
| 5. Diagnóstico pendiente | Se evalúa fail-closed según reglas del Servicio; no se inventan datos. |
| 6. Requiere revisión | No se crea Turno; queda solicitud técnica revisable. |
| 7. Varios Servicios | Evaluación conjunta, compatibilidad AND, duración/equipo agregados y detalles ordenados. |
| 8. Personal sin disponibilidad | Rechazo semántico; refrescar opciones, sin mutación parcial. |
| 9. Personal disponible ahora | Hold del próximo intervalo válido y continuación según riesgo/pago. |
| 10. Conflicto concurrente | Un ganador; el otro recibe 409 y nuevas opciones. Reintento igual recupera resultado. |

### 6.4 Impacto en superficies operativas existentes

- **Gestión de Turnos:** consulta agenda global con
  `gestion.view_global_agenda`, pero abre con filtro `solicitado`. Si BH-063 crea
  `CONFIRMADO`, la implementación debe hacerlo visible en una pestaña/resultado
  coherente y no dar la impresión de que desapareció.
- **Operaciones del día:** consulta por fecha la agenda global o filtra la agenda
  propia. Un Turno asistido confirmado entra sin adaptación de canal; acciones
  continúan dependiendo de permisos efectivos.
- **Mi agenda laboral:** lista los Turnos asignados al perfil de Personal y
  ofrece llegada/trabajo técnico según permiso, capability y ownership. No
  filtra por canal.
- **Agenda administrativa:** horarios y bloqueos siguen siendo fuentes
  autoritativas de disponibilidad; crear un Turno no debe mutarlos.
- **Trabajo técnico:** puede abrirse para el profesional asignado, pero la
  edición y finalización continúan condicionadas por estado y policy.

## 7. Creación y confirmación de Turnos

### 7.1 Alternativa A — crear directamente `CONFIRMADO`

**Ventaja:** recorrido corto y compatible con trabajo profesional.

**Riesgo:** es insegura si “directamente” significa omitir evaluación, hold,
pago o autorización. Sólo es aceptable como resultado terminal de una
transacción/orquestación que ya verificó todo.

### 7.2 Alternativa B — crear `SOLICITADO` y confirmar después

**Ventaja:** hace visible una intención pendiente.

**Riesgos:** materializa un Turno antes de cerrar riesgo/pago, ocupa agenda como
estado activo, duplica conceptos ya representados por solicitud/hold y requiere
un nuevo comando de confirmación. No resuelve por sí misma idempotencia ni
autorización financiera.

### 7.3 Alternativa C — política según riesgo, canal y pago (recomendada)

La intención pendiente se representa con `SolicitudTecnicaReserva`; la
capacidad temporal con `SlotHold`; el Turno se crea al final:

| Condición | Resultado |
|---|---|
| `APTO` | Puede avanzar a hold. |
| `ADVERTENCIA` | Avanza sólo luego de consentimiento asistido válido. |
| `REQUIERE_REVISION` | Queda en revisión; sin hold prolongado ni Turno. |
| `NO_APTO` | No crea hold ni Turno; conserva evidencia y mensaje seguro. |
| Pago/seña previa obligatoria | La confirmación financiera existente consume el hold. |
| Excepción presencial sin pago previo aprobada | Un comando no financiero explícito y auditado consume el hold. Nunca crea Pago ficticio. |
| Hold vencido o capacidad perdida | 409; nueva disponibilidad y nuevo hold/evaluación cuando corresponda. |

La operación terminal crea `CONFIRMADO`, nunca `EN_PROCESO`. Si se decide
conservar una etapa administrativa `SOLICITADO`, deberá tener propósito, TTL,
transiciones y ocupación de agenda definidos; no es la recomendación de este
informe.

### 7.4 Transiciones autorizadas propuestas

```text
Intención asistida
  -> evaluación técnica
     -> revisión / rechazo / advertencia pendiente
     -> aprobada técnicamente
        -> SlotHold ACTIVE
           -> confirmación financiera autorizada
              o confirmación presencial no financiera autorizada
           -> Turno CONFIRMADO + SlotHold CONSUMED

Turno CONFIRMADO
  -> REALIZADO
  -> CANCELADO/AUSENTE según comandos existentes/futuros
  -> EN_PROCESO sólo después de resolver su finalización
```

Toda transición debe bloquear el agregado, verificar estado origen, ser
idempotente, emitir auditoría y responder 409 ante estado incompatible.

## 8. Integración de riesgo técnico

### 8.1 Política

- Evaluar **todos** los Servicios solicitados con la versión publicada.
- No imponer diagnóstico universal.
- Respetar procedencia, antigüedad y completitud del diagnóstico.
- Un perfil ausente/incompleto recibe el outcome configurado; nunca `APTO` por
  defecto ni un estado saludable inventado.
- Persistir evaluación real e inmutable; no crear autoevaluaciones ni
  diagnósticos para completar el flujo.
- Al cambiar Cliente, Servicios, fecha o información técnica, invalidar/revisar
  la evidencia conforme al contrato BH-057.

### 8.2 Advertencia y revisión asistidas

La aceptación actual sólo admite al Cliente autenticado. La variante asistida
debe guardar separadamente:

- Cliente al que se informó;
- evaluación y versión de política;
- códigos y textos comunicados;
- forma de consentimiento aprobada;
- operador que lo registró;
- fecha/hora y medio de solicitud;
- motivo si el Cliente no puede prestar consentimiento.

El operador no se convierte en autor técnico ni en Cliente. `REQUIERE_REVISION`
sólo puede resolverlo quien cumpla `technical_booking.review`, Personal activo y
compatibilidad con todos los Servicios. El operador de recepción puede ver el
estado y los mensajes habilitados para Cliente, no historial, diagnóstico,
fórmulas o notas internas sin capabilities propias.

## 9. Política propuesta BH-064

### 9.1 Datos mínimos

Recomendación:

- nombre y apellido reales;
- al menos un contacto utilizable: email **o** teléfono normalizado;
- medio/origen del alta y motivo;
- Idempotency-Key;
- consentimiento/aviso de tratamiento de datos según política externa.

Zona, fecha de nacimiento, sexo y datos capilares no son obligatorios para el
alta rápida. Si no hay ningún contacto, el alta debe detenerse o seguir un
procedimiento excepcional de reconciliación definido; nombre solo no permite
deduplicar ni recuperar acceso con seguridad.

### 9.2 Búsqueda y duplicados

Antes de crear:

1. normalizar email y teléfono;
2. buscar coincidencia exacta autorizada;
3. presentar candidatos mínimos, sin auto-fusionar homónimos;
4. si hay una coincidencia inequívoca, continuar con el Cliente existente;
5. si hay ambigüedad, requerir selección/corrección; no crear “por las dudas”.

Email verificado puede ser identidad fuerte. El teléfono puede compartirse o
reciclarse, por lo que su unicidad global requiere decisión D-07; como mínimo
debe generar conflicto de revisión, no fusión automática.

### 9.3 Usuario, Cliente y rol

Conservar una única transacción para:

- identidad de Usuario;
- perfil Cliente;
- único BusinessRole `CLIENTE` mediante contrato publicado;
- estado de incorporación web;
- evento de auditoría con actor y motivo;
- resultado idempotente.

No se crea un BusinessRole nuevo. El `cliente_id` persistido es la identidad
interna mínima que BH-063 necesita; puede añadirse un UUID público si se decide
no exponer PK secuencial, pero no es condición para el dominio interno.

### 9.4 Cuenta activa y acceso web pendiente

No debe confundirse “Cliente habilitado para recibir Turnos” con “credencial web
reclamada”. Los servicios actuales exigen `Cliente.activo=True` y
`Usuario.is_active=True`; desactivar el Usuario rompería riesgo, hold y Turno.

Se recomienda:

- mantener habilitada la identidad de negocio;
- crear la credencial con contraseña **inutilizable**;
- registrar estado `PENDING_CLAIM` separado de `is_active`;
- activar acceso sólo mediante enlace/token de un solo uso enviado a un contacto
  verificado;
- nunca mostrar, registrar ni compartir contraseña temporal.

La cuenta actual con contraseña elegida por el operador puede seguir existiendo
para su caso administrativo, pero no debe ser el contrato de alta rápida.

### 9.5 Cliente sin email

El modelo actual no lo representa: email es obligatorio y además es la clave de
login. La política recomendada es **no inventar un email de contacto**. Se debe
separar un identificador interno de autenticación del email opcional, o publicar
otro diseño equivalente que distinga explícitamente principal interno y dato de
contacto.

Hasta completar esa migración, el alcance sin email no puede declararse
cumplido. Un placeholder presentado como email real contaminaría búsqueda,
notificaciones y recuperación. Si se adopta transitoriamente un principal
reservado, debe estar tipado como interno, excluido de interfaces/contacto y con
contraseña inutilizable; esta alternativa queda subordinada a D-01.

### 9.6 Idempotencia del alta

La Idempotency-Key debe identificar un comando persistido con fingerprint del
payload normalizado. Reglas:

- misma clave + mismo fingerprint: devolver el mismo `cliente_id` y `created`;
- misma clave + payload distinto: 409 `IDEMPOTENCY_KEY_REUSED`;
- email/contacto ya asociado: 409 o resultado “Cliente existente” según contrato,
  nunca segunda cuenta;
- dos claves concurrentes para la misma identidad: constraint/lock de identidad
  normalizada decide un ganador; la otra operación recupera o entra en revisión;
- nunca guardar la contraseña, token o contacto sensible en logs de comando.

## 10. Integración alta rápida + Turno

Alta y Turno no deben encerrarse en una única transacción larga. La identidad de
Cliente es un hecho recuperable; disponibilidad, riesgo y pago tienen ciclos y
locks distintos.

| Caso | Política propuesta |
|---|---|
| Cliente se crea y Turno falla | Conservar Cliente; devolver `cliente_id`, causa y acción “reintentar Turno”. No borrar ni compensar el alta. |
| Slot pierde disponibilidad | 409, liberar/expirar hold si corresponde y ofrecer nuevos slots. |
| Servicio requiere revisión | Conservar Cliente y solicitud; no crear Turno. Continuar luego de decisión técnica. |
| Cliente ya existía | Seleccionarlo explícitamente; no alterar credenciales, perfil o rol como efecto lateral. |
| Dos operadores crean al mismo Cliente | Match + identidad normalizada + constraint; uno crea, el otro recupera/conflicta sin duplicar. |
| Timeout de alta | Repetir la misma clave y recuperar el resultado. |
| Timeout de Turno | Repetir la misma clave; recuperar solicitud/hold/Turno ya producido. |
| Sin email | Alta pendiente de reclamo según 9.5; teléfono sirve de contacto si está permitido/verificado. |
| Sin acceso web | Puede recibir Turnos; no se simula login ni se entrega contraseña compartida. |

### Unidades transaccionales

1. **Alta:** Usuario + Cliente + rol + estado de acceso + auditoría + comando.
2. **Solicitud/evaluación:** intención + Servicios + evaluación + auditoría.
3. **Hold:** locks + disponibilidad + capacidad + snapshot + idempotencia.
4. **Confirmación:** autorización financiera/no financiera + consumo del hold +
   Turno + detalles + enlaces + auditoría.

Cada unidad se confirma o revierte por separado y deja una referencia estable
para retomar la siguiente.

## 11. Diagnóstico pendiente y trabajo técnico

- Cliente puede conservar los cinco campos capilares nulos.
- No se crea `DiagnosticoCapilar` durante BH-064.
- La ausencia se presenta como “sin diagnóstico/información pendiente”, no como
  normalidad clínica.
- Sólo Personal autorizado crea o corrige diagnóstico y se conserva
  `Procedencia` real.
- El evaluador decide si esa ausencia permite, advierte, deriva o bloquea según
  el Servicio.
- El contexto técnico ya acepta Turnos presenciales y Clientes sin diagnóstico.
- Una vez `CONFIRMADO`, asignado y con ownership/capabilities, el profesional
  puede abrir `/turnos/:turnoId/trabajo-tecnico` sin depender del canal.
- La ficha se exige por política de `PerfilTecnicoServicio`, no por una regla
  universal de alta.

## 12. Seguridad y minimización de datos

| Operación | Autorización efectiva |
|---|---|
| Crear Cliente rápido | `usuarios.create_walkin_client` |
| Buscar/listar Clientes | `usuarios.view_clients`; el selector de Turno debe exigir además/alternativamente el scope explícito aprobado |
| Crear solicitud/Turno asistido | `gestion.create_turno_for_client` |
| Asignar Personal | Dentro del comando anterior y sujeto a compatibilidad/disponibilidad; no implica administrar Personal |
| Ver agenda global | `gestion.view_global_agenda` |
| Ver agenda propia | Perfil Personal activo + ownership |
| Revisar riesgo | capability `technical_booking.review`, Personal activo y skill |
| Registrar pago | `gestion.register_payment` |
| Confirmar seña | `gestion.confirm_deposit` y contratos financieros aplicables |
| Confirmación presencial sin pago | Autoridad semántica a decidir; no inferir de permisos financieros ni roles |
| Ver contexto técnico global | `technical_record.read_global` + scope/ownership |
| Crear diagnóstico | `diagnosis.create` |
| Editar ficha | `technical_record.manage` + ownership + estado |
| Finalizar | `gestion.finalize_service` + Personal activo + ownership + estado válido |

La búsqueda debe ser paginada, con longitud mínima, rate limit y proyección
reducida. No debe entregar diagnóstico, historial, roles, permisos ni datos de
terceros no necesarios. Los errores de recursos fuera de scope deben usar 404
seguro cuando corresponda.

No se usa BusinessRole nominal, `is_staff` ni `is_superuser` como autorización
de negocio. No se otorgan capacidades técnicas a recepción por habilitar altas
o Turnos.

## 13. Integridad, concurrencia y recuperación

### 13.1 Garantías a conservar

- reloj autoritativo de base de datos para hold/expiración;
- `transaction.atomic` y `select_for_update` con orden estable;
- revalidación dentro de lock, no confianza en la UI;
- capacidad de Personal, Cliente y equipo;
- consumo único de hold y enlace único al Turno;
- fingerprints de idempotencia;
- 409 estable para capacidad, estado o clave incompatible;
- auditoría con causalidad y actor real.

### 13.2 Identidades distintas

No debe usarse una sola clave para toda la cadena. Se recomienda una correlación
común y claves por comando:

- `client_intake_key`;
- `assisted_request_key`;
- `slot_hold_key`;
- `confirmation_operation_key`.

El backend devuelve todas las referencias necesarias, pero no deriva una
autorización de otra clave.

### 13.3 Respuestas y recuperación

| Clase | Respuesta | Recuperación |
|---|---|---|
| Entrada inválida | 400 + code/campo | Corregir; sin mutación parcial. |
| Sin sesión | 401 | Renovar sesión; no cambiar clave de mutación incierta. |
| Sin permiso/capability | 403 | Refrescar sesión; no ampliar datos. |
| Fuera de scope | 404 seguro | Volver a búsqueda autorizada. |
| Duplicado/capacidad/estado | 409 + code | Recuperar resultado o refrescar disponibilidad. |
| Revisión/no apto | Estado técnico explicable | Continuar por revisión o elegir otra intención. |
| Timeout | Resultado incierto | Repetir manual/automáticamente con la misma clave. |
| Clave con payload distinto | 409 | Nueva clave sólo para una intención realmente nueva. |

## 14. Plan incremental recomendado

No se recomienda implementar ambas tareas en un commit masivo. Cada incremento
debe cerrar contrato, migraciones, pruebas y documentación antes del siguiente.

### Incremento 0 — decisiones y contratos de comandos

| Punto | Plan |
|---|---|
| 1. Objetivo | Cerrar D-01 a D-08 y publicar contratos de payload, estados, códigos, scopes e idempotencia. |
| 2. Alcance | Diseño ejecutable; sin cambiar aún flujo productivo. |
| 3. Backend | Serializers estrictos propuestos; fingerprints y matriz de transiciones. |
| 4. Frontend | Wireframes y estados de recuperación; sin activar rutas. |
| 5. Modelos/migraciones | Inventario aprobado de ledger, acceso pendiente, contacto/canal; ninguna migración todavía. |
| 6. Permisos | Confirmar reutilización de permisos efectivos y autoridad no financiera. |
| 7. Casos | Email/sin email, existente/nuevo, warning/revisión, pago/no pago, inmediato. |
| 8. PostgreSQL | Diseñar constraints y orden de locks; matriz concurrente. |
| 9. React | Diseñar pruebas por permiso y pérdida de sesión. |
| 10. Regresiones | Web BH-057/BH-058, roles BH-061/BH-062 y flujos profesionales. |
| 11. Aceptación | Ningún estado o autorización queda implícito; decisiones firmadas. |
| 12. Riesgos/abiertos | Todos D-01–D-08; bloquean sólo el incremento afectado. |

### Incremento 1 — identidad idempotente BH-064

| Punto | Plan |
|---|---|
| 1. Objetivo | Crear/reutilizar Cliente mínimo sin diagnóstico y recuperar reintentos. |
| 2. Alcance | Alta y búsqueda previa; aún no crea Turno. |
| 3. Backend | Servicio idempotente, normalización, match, contraseña inutilizable, claim pendiente, auditoría. |
| 4. Frontend | Formulario mínimo, búsqueda primero, conflictos y resultado con “continuar al Turno”. |
| 5. Modelos/migraciones | Ledger de alta; estado de claim; identidad/contacto opcional según D-01; constraints normalizados. |
| 6. Permisos | `create_walkin_client` para mutar; `view_clients` para búsqueda amplia; scopes minimizados. |
| 7. Casos | Con/sin email, email/phone existente, homónimo, clave repetida, payload distinto, contacto inválido. |
| 8. PostgreSQL | `TransactionTestCase`: dos keys misma identidad, misma key concurrente, rollback en rol/auditoría. |
| 9. React | Éxito, 400/403/409, timeout + retry, sesión revocada, sin exposición de contraseña. |
| 10. Regresiones | Registro público, login, recuperación, administración de cuentas y contrato de roles. |
| 11. Aceptación | Un solo Cliente/rol/evento efectivo; diagnóstico cero; mismo retry devuelve mismo id. |
| 12. Riesgos/abiertos | Migración de login sin email y política de teléfono compartido. |

### Incremento 2 — solicitud asistida y riesgo BH-063

| Punto | Plan |
|---|---|
| 1. Objetivo | Registrar intención multiservicio y obtener decisión BH-057, sin Turno prematuro. |
| 2. Alcance | Cliente existente o resultado del incremento 1; no confirma agenda. |
| 3. Backend | Orquestador asistido autorizado; Servicios ordenados; evaluación real; consentimiento asistido; revisión existente. |
| 4. Frontend | Selección de Cliente/Servicios, resumen de outcome y mensajes permitidos. |
| 5. Modelos/migraciones | Ledger/correlación asistida y medio de solicitud; evidencia de consentimiento si no cabe en modelos actuales. |
| 6. Permisos | `create_turno_for_client`; revisión conserva capability y skill; sin acceso técnico adicional. |
| 7. Casos | APTO, warning aceptado/rechazado, revisión, no apto, perfil nulo, política faltante, multiservicio. |
| 8. PostgreSQL | Reevaluación concurrente, policy snapshot, idempotencia y no duplicación de evidencia. |
| 9. React | Estados vacío/loading/outcome, 403 técnico, consentimiento explícito y no filtración. |
| 10. Regresiones | Flujo web de solicitud, warning del propietario y revisión profesional. |
| 11. Aceptación | Ningún Servicio evita BH-057; no se crean diagnóstico, hold ni Turno indebidos. |
| 12. Riesgos/abiertos | Forma legal/funcional del consentimiento y cambio de intención. |

### Incremento 3 — hold asistido, disponibilidad e inmediatez

| Punto | Plan |
|---|---|
| 1. Objetivo | Reservar capacidad multiservicio de forma temporal y concurrente. |
| 2. Alcance | Solicitudes técnicamente aprobadas; todavía no define pago. |
| 3. Backend | Variante asistida de hold/release, actor real, mismo motor de disponibilidad, códigos 409. |
| 4. Frontend | Slots por Personal, cuenta regresiva/expiración, refresco y próximo intervalo inmediato. |
| 5. Modelos/migraciones | Reutilizar `SlotHold`; sólo campos de actor/correlación si la evidencia actual resulta insuficiente. |
| 6. Permisos | `create_turno_for_client`; no impersonar owner. |
| 7. Casos | Jornada, habilidad, bloqueo, equipo, overlap Cliente/Personal, expiración y slot pasado. |
| 8. PostgreSQL | Carreras hold/Turno, dos operadores, equipo limitado, expiración y misma key. |
| 9. React | 409 y nueva selección, hold vencido, doble submit y reloj no autoritativo. |
| 10. Regresiones | Holds web, reprogramación, agenda y disponibilidad pública. |
| 11. Aceptación | Un ganador por capacidad; retry idéntico recupera hold; inmediato nunca backdatea. |
| 12. Riesgos/abiertos | Tolerancia/grilla D-05 y TTL apropiado para atención en mostrador. |

### Incremento 4 — confirmación condicionada y estados

| Punto | Plan |
|---|---|
| 1. Objetivo | Producir exactamente un Turno `CONFIRMADO` bajo fundamento válido. |
| 2. Alcance | Ramas con pago y sin pago; no altera cálculo financiero ni crea pagos ficticios. |
| 3. Backend | Reutilizar confirmación financiera; comando no financiero explícito si D-02 lo aprueba; locks, fingerprint, auditoría. Resolver D-06. |
| 4. Frontend | Mostrar fundamento, pago pendiente, confirmación, 409 y resultado recuperado. |
| 5. Modelos/migraciones | Ledger/fundamento de confirmación y canal preciso si no quedan cubiertos por relaciones existentes. |
| 6. Permisos | Pago conserva permisos financieros; autoridad no financiera explícita, sin rol nominal. |
| 7. Casos | Hold activo/vencido/consumido, pago suficiente/insuficiente, no-pay permitido/prohibido, estado concurrente. |
| 8. PostgreSQL | Dos confirmaciones, confirmación vs expiración/liberación, mismo/diferente key, un Turno/Detalles. |
| 9. React | Doble click, timeout luego de commit, permiso revocado y respuesta idempotente. |
| 10. Regresiones | Checkout, pagos manuales/externos, conciliación, stock y finalización. |
| 11. Aceptación | Nunca más de un Turno; `CONFIRMADO` sólo con riesgo/capacidad/política válidos. |
| 12. Riesgos/abiertos | D-02 autoridad y efecto de `EN_PROCESO` sobre finalización. |

### Incremento 5 — experiencia integrada y endurecimiento

| Punto | Plan |
|---|---|
| 1. Objetivo | Unir buscar/alta/solicitud/hold/confirmación y demostrar no regresión. |
| 2. Alcance | React operativo, recuperación y observabilidad; sin ampliar dominio. |
| 3. Backend | Endpoints de estado/reanudación, proyecciones mínimas, métricas y códigos uniformes. |
| 4. Frontend | Wizard reanudable; resultado parcial visible; enlace a agenda/trabajo técnico. |
| 5. Modelos/migraciones | Ninguna nueva salvo hallazgo; cierre de índices de consulta. |
| 6. Permisos | Rutas, botones y datos por permisos/capabilities efectivos; backend sigue autoritativo. |
| 7. Casos | Alta+Turno feliz, Cliente existente, revisión, pago, sin email, timeout en cada frontera. |
| 8. PostgreSQL | Suite integrada y de concurrencia real, no SQLite. |
| 9. React | Flujos completos, 401/403/404/409, sesión dinámica, reload y retry. |
| 10. Regresiones | Backend B1–B7, frontend completo, build y smoke de web/profesional. |
| 11. Aceptación | BH-063/BH-064 trazables extremo a extremo y flujo web sin degradación. |
| 12. Riesgos/abiertos | E2E de navegador y operación/soporte ante casos ambiguos. |

## 15. Criterios de aceptación ajustados

### BH-063

- Personal con permiso efectivo crea una intención para un Cliente activo; sin
  permiso recibe 403 y no muta datos.
- Cliente se localiza mediante búsqueda minimizada y selección explícita.
- Uno o varios Servicios se evalúan con BH-057 y política versionada.
- Advertencia, revisión y no apto no se convierten silenciosamente en Turno.
- Disponibilidad revalida Personal, Cliente, jornada, bloqueos, habilidad,
  equipo, holds y superposición bajo PostgreSQL.
- Reintento idéntico devuelve el mismo resultado; clave incompatible da 409.
- Confirmación crea exactamente un `CONFIRMADO` con fundamento financiero o no
  financiero explícito y auditado.
- No se acepta `estado` libre ni se crea `EN_PROCESO` anticipadamente.
- El operador y medio de solicitud quedan trazados.
- El Turno aparece en agenda del profesional y permite continuar el trabajo
  técnico por ownership/capabilities.
- El flujo web, pagos, stock, riesgo y finalización no se degradan.

### BH-064

- Personal con `create_walkin_client` crea un Cliente con datos mínimos y sin
  diagnóstico; otros actores no pueden hacerlo.
- La búsqueda previa ofrece reutilizar un Cliente existente sin auto-fusionar.
- Usuario, Cliente, rol único, claim pendiente, auditoría y ledger se confirman
  atómicamente.
- Mismo retry no crea otra cuenta; claves concurrentes para la misma identidad
  producen un ganador o revisión controlada.
- No se muestra ni comparte contraseña temporal; la credencial nace
  inutilizable y se reclama con token de un solo uso.
- El caso sin email queda representado sin falsear un contacto y puede recibir
  Turnos.
- El resultado entrega `cliente_id` y permite continuar BH-063.
- Si el Turno falla, el Cliente persiste y el flujo puede reanudarse.
- Perfil y diagnóstico quedan pendientes y pueden completarse después por vías
  autorizadas, conservando procedencia.

## 16. Decisiones indispensables

| ID | Decisión | Recomendación | Bloquea |
|---|---|---|---|
| D-01 | Identidad sin email | Separar principal interno de email opcional; acceso `PENDING_CLAIM`, password inutilizable. | BH-064 sin email |
| D-02 | Pago/seña presencial | Respetar política publicada; cualquier excepción debe ser explícita, versionada y auditada, sin Pago ficticio. | Confirmación BH-063 |
| D-03 | Consentimiento de warning | Evidencia asistida separando Cliente informado y operador registrante. | Rama `ADVERTENCIA` |
| D-04 | Canal | Distinguir `TELEFONO` y `PRESENCIAL` o agregar `medio_solicitud` auditable. | Trazabilidad completa |
| D-05 | Atención inmediata | Próximo intervalo futuro; definir tolerancia/grilla, nunca backdating. | Walk-in inmediato |
| D-06 | `EN_PROCESO` | Preferencia: permitir finalización válida desde `EN_PROCESO` o separar llegada de inicio; no usarlo antes. | Uso oficial de llegada |
| D-07 | Duplicado por teléfono | Teléfono como candidato fuerte, no fusión automática; decidir unicidad sólo con reglas de compartición/verificación. | Deduplicación sin email |
| D-08 | Autoridad no financiera | Definir si `create_turno_for_client` incluye confirmación terminal o si hace falta permiso semántico separado y contrato versionado. | Turno sin pago previo |

No se recomienda modificar en sitio el contrato inmutable de roles BH-061. Si
D-08 exige un permiso nuevo, debe publicarse una versión nueva del contrato y
aprobarse su asignación; no agregar grants ad hoc durante la implementación.

## 17. Riesgos y bloqueantes

| Riesgo | Mitigación |
|---|---|
| Suplantar al Cliente para usar APIs owner-only | Variantes asistidas explícitas con actor real y scope. |
| Confirmar sin autoridad financiera | Separar verificación técnica, capacidad y fundamento de confirmación. |
| Dos Clientes por timeout/concurrencia | Ledger + fingerprint + identidad normalizada + constraint/lock. |
| Dos Turnos o sobreventa | Hold, locks PostgreSQL, consumo único y revalidación. |
| Filtrar historia capilar a recepción | Proyecciones mínimas y capabilities técnicas independientes. |
| Email interno confundido con contacto | No inventarlo; separar principal y contacto. |
| Cliente web pendiente rechazado por servicios | Separar habilitación comercial de claim, sin usar `is_active=False`. |
| `EN_PROCESO` no finalizable | Resolver D-06 antes de publicar llegada/inicio como recorrido. |
| Multiservicio inconsistente | Reusar snapshots, duración agregada, skills AND, equipo y riesgo conjunto. |
| Política cambia durante operación | Persistir versión/snapshot; no reinterpretar automáticamente. |
| Operación parcial | Unidades transaccionales reanudables; nunca borrar Cliente válido como compensación. |

**Bloqueantes del análisis:** ninguno.

**Bloqueantes de implementación completa:** decisiones D-01, D-02, D-03,
D-04, D-05, D-06, D-07 y D-08 en el incremento al que corresponden.

## 18. Pruebas y regresiones previstas

No se ejecutaron suites porque esta etapa no modifica código. La implementación
deberá agregar como mínimo:

- servicios y APIs: autorización, payload estricto, auditoría, idempotencia y
  recuperación;
- `TransactionTestCase` PostgreSQL con barreras/hilos para alta, hold,
  confirmación, equipo y expiración;
- matriz de riesgo con perfil completo, parcial, ausente, diagnóstico confiable,
  desactualizado y multiservicio;
- React Testing Library para permisos efectivos, sesión dinámica, doble submit,
  timeout, reload, 400/401/403/404/409 y datos mínimos;
- regresión del registro público, administración de cuentas, roles, agenda,
  solicitud web, holds, pagos, conciliación, trabajo técnico y finalización;
- `makemigrations --check`, `check`, build React y suites B1–B7;
- E2E focal de alta+Turno y Cliente existente+Turno en un entorno controlado.

## 19. Conclusión

La arquitectura existente permite implementar BH-063/BH-064 sin duplicar el
motor de agenda, riesgo, pagos ni trabajo profesional. La solución segura no es
ampliar la creación directa actual, sino componer contratos existentes con
comandos asistidos explícitos, identidades idempotentes y una política terminal
de confirmación.

El orden recomendado es: cerrar decisiones y contratos, resolver identidad
BH-064, incorporar intención/riesgo BH-063, adaptar hold, confirmar según pago y
recién entonces integrar React y endurecer concurrencia. Este orden conserva al
Cliente ante fallos, evita Turnos prematuros y mantiene intacto el canal web.

**ANÁLISIS BH-063/BH-064 = COMPLETADO**
