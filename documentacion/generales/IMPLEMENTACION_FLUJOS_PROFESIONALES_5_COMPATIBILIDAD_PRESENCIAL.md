# Flujos profesionales — Incremento 5: compatibilidad presencial

**Fecha:** 2026-11-19

**Baseline de partida:** `dbead55051fee50021889ba7dc374db54734e6b4`

**Rama:** `save/work-in-progress`

**Estado:** validado para publicación

## 1. Objetivo y límite

Este incremento verifica que el recorrido profesional publicado en el
Incremento 4 pueda recibir, en el futuro, Clientes y Turnos originados por:

- **BH-063:** Turnos asistidos/presenciales registrados por Personal autorizado;
- **BH-064:** alta rápida de un Cliente presencial, sin diagnóstico inicial
  obligatorio.

No implementa BH-063 ni BH-064, no agrega pantallas de recepción, no crea un
estado, no altera pagos o stock y no completa diagnósticos faltantes. Las APIs
actuales de alta administrativa y creación para Cliente se ejercitan sólo como
fundaciones existentes; no se presentan como cierre de esas tareas oficiales.

## 2. Resultado ejecutivo

El recorrido profesional es compatible con Clientes sin diagnóstico y con
perfiles parciales. Su autoridad depende del Turno, del Personal asignado, de
capabilities efectivas y de la política del Servicio; no depende del canal web,
de una sesión del Cliente, de un `SlotHold`, de un pago previo ni de cinco datos
capilares completos.

La integración futura debe respetar dos fronteras:

1. la ausencia de diagnóstico sólo bloquea cuando una regla de riesgo publicada
   y aplicable al Servicio lo determina;
2. el trabajo técnico es editable en `CONFIRMADO` (y en el literal existente
   `EN_PROCESO`), pero la finalización actual sólo acepta `CONFIRMADO`.

La creación asistida existente deja el Turno en `SOLICITADO`. Por eso BH-063
deberá definir o reutilizar una transición autorizada hasta `CONFIRMADO` antes
de habilitar el trabajo técnico. Este incremento no salta la transición y no
introduce `EN_PROCESO`.

## 3. Precondiciones reales del recorrido

### 3.1 Abrir `/turnos/:turnoId/trabajo-tecnico`

La ruta React exige antes de montar:

- cuenta autenticada;
- perfil Personal activo;
- capability `technical_record.read_global`.

El backend vuelve a exigir:

- cuenta, Personal y habilidad `DIAGNOSTICO` activos;
- permiso efectivo que compone `technical_record.read_global`;
- que `Turno.profesional_id` coincida con el Personal del actor.

La lectura no exige que el Turno venga de la web, esté pagado, tenga `HOLD` o
posea diagnóstico. Un Turno propio en `SOLICITADO` puede proyectar contexto de
sólo lectura, pero muestra el bloqueo de transición y no habilita ficha.

### 3.2 Evaluar y editar

| Acción | Autoridad | Condición de estado |
|---|---|---|
| Nueva evaluación | `diagnosis.create` efectiva | no se impone completar cinco campos |
| Corrección de evaluación | autoridad efectiva y operación semántica | sólo campos evaluados originalmente, con motivo |
| Crear/editar ficha | `technical_record.manage` + ownership | `CONFIRMADO` o `EN_PROCESO` |
| Modificar fórmula | además `service_formula.manage` | política del Servicio aplicable |

Una evaluación profesional nueva promueve únicamente los campos observados al
perfil vigente y conserva la procedencia. Los campos no evaluados no se
sobrescriben. Un valor de perfil sin una fuente trazable se proyecta como
`DESCONOCIDO`.

### 3.3 Finalizar

La finalización exige:

- `gestion.finalize_service`;
- cuenta y Personal activos;
- Personal asignado al Turno;
- estado `CONFIRMADO`;
- ficha completa sólo para cada `DetalleTurno` cuyo
  `PerfilTecnicoServicio.requisito_ficha` sea `REQUERIDA`;
- `Idempotency-Key` compatible con el comando persistido.

No exige diagnóstico universal, pago o stock. Es atómica, bloquea el agregado,
persiste una única `FinalizacionTurno` y deduplica automatizaciones. La mera
realización no crea un `DiagnosticoCapilar`: el efecto de diagnóstico automático
queda `OMITIDO`. Un impacto capilar sólo puede provenir de la configuración
explícita del Servicio y queda trazado como efecto post-servicio; no equivale a
una observación profesional.

## 4. Cliente sin diagnóstico

El caso `Cliente activo + Turno CONFIRMADO + cero DiagnosticoCapilar` se verificó
de extremo a extremo:

- el contexto responde sin excepción;
- las cinco dimensiones vacías se muestran con `id=null`, `nombre=null` y
  procedencia `DESCONOCIDO`;
- `evaluaciones` permanece vacío;
- el GET no crea diagnóstico, ficha ni cambio de estado;
- las acciones permitidas siguen disponibles para el Personal asignado;
- una ficha se decide por `PerfilTecnicoServicio`, no por la existencia de un
  diagnóstico;
- un Servicio sin ficha requerida puede finalizar sin diagnóstico;
- la finalización no fabrica datos capilares.

Si una regla publicada de riesgo técnico exige diagnóstico para el Servicio,
`evaluate_booking_risk()` produce evidencia `DIAGNOSIS_MISSING` y el outcome
configurado, con mensaje profesional seguro. El evaluador no crea un diagnóstico
para satisfacer la regla.

## 5. Perfil parcial y procedencia

Se verificaron estas combinaciones:

| Situación | Resultado |
|---|---|
| cinco campos nulos | perfil pendiente, atención consultable |
| un campo existente sin vigencia trazable | `DESCONOCIDO` y sin fuente ficticia |
| evaluación profesional parcial | sólo ese campo pasa a procedencia `PROFESIONAL` |
| otro campo previo no evaluado | conserva valor y procedencia anterior/desconocida |
| diagnóstico de otro Cliente | no aparece en el Turno consultado |
| evaluación histórica | permanece separada del snapshot vigente |

No existe una regla de “completar cinco campos para consultar”. El evaluador de
riesgo sí puede considerar un diagnóstico incompleto o de fuente no confiable,
pero únicamente bajo una regla publicada aplicable al Servicio.

## 6. Turnos asistidos y atención inmediata

### 6.1 Contrato existente comprobado

`POST /api/gestion/turnos/crear-para-cliente/` recibe:

```json
{
  "cliente_id": 123,
  "servicio": 45,
  "profesional": 7,
  "fecha": "2026-11-21",
  "hora_inicio": "10:00"
}
```

El servidor fija:

- `canal_origen=PRESENCIAL`;
- `estado=SOLICITADO`;
- importes iniciales en cero;
- un `DetalleTurno` con precio y duración históricos.

La operación requiere `gestion.create_turno_for_client` y valida Cliente,
Servicio y Personal activos, habilidades, agenda laboral, fecha futura, ventana
de reserva, superposición del Profesional y Cliente, bloqueos, `SlotHold` activo
y capacidad de equipamiento. No requiere sesión autenticada del Cliente, un
`HOLD` previo, comprobante ni diagnóstico universal.

El flujo web actual `POST /api/gestion/turnos/reservar/` conserva el mismo
servicio de creación, pero obtiene el Cliente de la sesión y fija
`canal_origen=WEB`. Ambos canales quedan separados y ambos crean actualmente en
`SOLICITADO`.

### 6.2 Atención inmediata

No existe un comando productivo específico de “atención inmediata”. BH-063
podrá seleccionar un horario futuro disponible, incluso del mismo día, usando la
autoridad de disponibilidad existente. “Inmediata” no autoriza a:

- crear en un intervalo pasado o ya iniciado;
- omitir horario laboral, habilidades, bloqueos, solapamientos o equipamiento;
- ignorar un `HOLD` activo;
- forzar `CONFIRMADO`, `EN_PROCESO` o `REALIZADO` mediante el payload.

## 7. Matriz de los 18 escenarios

| # | Escenario | Evidencia | Resultado |
|---:|---|---|---|
| 1 | Cliente existente con diagnóstico | contexto + historia profesional | compatible |
| 2 | Cliente existente sin diagnóstico | contexto real | compatible |
| 3 | Perfil parcial | promoción selectiva | compatible |
| 4 | Procedencia desconocida | campo sin vigencia | explícita, no inventada |
| 5 | Turno confirmado sin diagnóstico | access + preflight | listo según Servicio |
| 6 | Servicio requiere evaluación | evaluador real y regla publicada | explica `DIAGNOSIS_MISSING` |
| 7 | Servicio no la requiere | evaluador sin regla aplicable | `APTO`, sin requisito inventado |
| 8 | Ficha por `DetalleTurno` | dos Servicios, dos fichas | independiente |
| 9 | Finalización sin diagnóstico | endpoint real + retry | permitida e idempotente |
| 10 | Condición técnica aplicable | ficha requerida ausente | bloqueo sin efectos parciales |
| 11 | Personal asignado | contexto efectivo | autorizado |
| 12 | Personal ajeno | contexto y finalización | 403 sin datos |
| 13 | Revocación de capability | lectura y mutación | 403 sin persistencia |
| 14 | Perfil/Turno no correspondientes | Turno de otro Cliente | no mezcla datos |
| 15 | Datos sensibles | proyección serializada | sin fórmula, snapshots o autor innecesario |
| 16 | Automatizaciones | ledger de finalización | no crea diagnóstico ficticio |
| 17 | Conflicto | versión optimista obsoleta | 409 sin pérdida de actualización |
| 18 | Flujo web actual | alta existente + creación asistida + reserva web | canales y estados preservados |

## 8. Contratos existentes

| Necesidad | Contrato actual | Garantía relevante |
|---|---|---|
| Alta administrativa | `POST /api/usuarios/admin/clientes/crear/` | Usuario + Cliente + rol y auditoría atómicos; sin diagnóstico |
| Selector mínimo | `GET /api/gestion/turnos/selector-clientes/` | acceso por permiso de crear Turno |
| Disponibilidad | `GET /api/gestion/turnos/consultar_disponibilidad/` | agenda, habilidades, conflictos, bloqueos, holds y equipo |
| Reserva web | `POST /api/gestion/turnos/reservar/` | Cliente de sesión, canal `WEB`, estado servidor |
| Creación para Cliente | `POST /api/gestion/turnos/crear-para-cliente/` | Cliente explícito, canal `PRESENCIAL`, estado servidor |
| Riesgo técnico | `evaluate_booking_risk()` y solicitudes técnicas | reglas publicadas por Servicio, evidencia inmutable al persistir |
| Contexto profesional | `GET /api/gestion/fichas-tecnicas/contexto-turno/?turno_id=` | ownership y proyección mínima |
| Fichas | comandos semánticos de `fichas-tecnicas` | una por Detalle, versión optimista |
| Finalización | `POST /api/gestion/turnos/{id}/finalizar_turno/` | lock, atomicidad, ownership e idempotencia |

## 9. Contrato futuro propuesto para BH-064

BH-064 es responsable del alta rápida; no de reservar el Turno. Debe reutilizar
la autoridad de `create_walkin_client` y la transacción de alta existente, o
evolucionarla sin duplicarla.

### Datos mínimos de entrada

- identidad/contacto mínimo decidido por BH-064;
- credencial o mecanismo de activación decidido por BH-064;
- motivo auditable del alta.

La obligatoriedad actual de email, nombre, apellido y contraseña temporal es un
contrato del alta administrativa existente, no una decisión ya tomada para el
alta rápida oficial.

### Datos mínimos de salida para encadenar BH-063

```json
{
  "created": true,
  "usuario_id": 10,
  "cliente_id": 10,
  "nombre": "Cliente Presencial",
  "usuario_activo": true,
  "cliente_activo": true
}
```

Puede incluir un contacto de presentación autorizado. No debe devolver hash,
contraseña temporal, permisos, grupos ni datos capilares inventados. El
`cliente_id` es la única identidad necesaria para el comando de BH-063.

El Cliente resultante puede tener las cinco FK capilares nulas y cero
`DiagnosticoCapilar`. Eso no es un error de alta.

## 10. Contrato futuro propuesto para BH-063

BH-063 es responsable de registrar el Turno asistido para un Cliente existente;
no de crear el Cliente ni de alterar el recorrido de finalización.

### Datos necesarios

- `cliente_id` activo;
- uno o más Servicios según el alcance que apruebe BH-063;
- `profesional_id` compatible;
- fecha y hora futura seleccionadas de disponibilidad autoritativa;
- referencia a evaluación/decisión técnica cuando el flujo de riesgo aplicable
  la exija;
- identidad idempotente si BH-063 permite reintentar el alta del Turno.

### Estado de integración

El contrato existente produce `SOLICITADO`. La pantalla técnica puede leerlo,
pero no permite editar ficha ni finalizar. Para dejarlo disponible para trabajo
técnico, BH-063 debe llegar a `CONFIRMADO` mediante una transición semántica y
auditada. Quedan dos opciones funcionales para decisión:

1. reutilizar aprobación/confirmación existente, incluida la política de pago
   que corresponda al canal presencial;
2. crear en BH-063 un comando explícito de confirmación presencial, con permiso,
   auditoría y revalidación, sin aceptar `estado` libre en el payload.

No se recomienda crear directamente en `EN_PROCESO`. Si BH-063 decide usar ese
estado para “atención iniciada”, deberá resolver primero que la finalización
actual lo rechaza, además de definir actor, instante y transición.

### Riesgo técnico

`TurnoCreationService.create()` valida disponibilidad y la alerta histórica
legacy, pero no orquesta por sí solo `evaluate_booking_risk()`. BH-063 no debe
interpretar esto como permiso para omitir reglas publicadas. Su orquestador debe:

1. evaluar los Servicios con la política publicada;
2. continuar, advertir, derivar a revisión o bloquear según el outcome y el
   contrato ya aprobado del subsistema de solicitudes técnicas;
3. persistir la evidencia que corresponda;
4. crear el Turno sólo cuando esa decisión lo permita.

Agregar esa orquestación ahora sería implementar BH-063 y queda expresamente
fuera de este incremento.

## 11. Autorización por transición

| Operación | Requisito efectivo |
|---|---|
| Alta rápida futura | `usuarios.create_walkin_client` |
| Consultar selectores/crear para Cliente | `gestion.create_turno_for_client` |
| Evaluar/revisar riesgo | permisos y capabilities del flujo técnico existente |
| Confirmar seña/pago, si aplica | autoridad financiera existente; no se infiere por rol |
| Abrir contexto | `technical_record.read_global` + ownership |
| Crear evaluación | `diagnosis.create` |
| Editar ficha | `technical_record.manage` + ownership + estado |
| Finalizar | `gestion.finalize_service` + ownership + `CONFIRMADO` |

No se usa `is_staff`, `is_superuser` ni BusinessRole nominal como atajo.

## 12. Errores y recuperación segura

| Caso | Respuesta/resultado | Recuperación |
|---|---|---|
| payload o entidad inválida | 400 con código estable | corregir entrada, sin mutación parcial |
| sesión ausente | 401 | renovar sesión; no repetir mutación automáticamente |
| permiso/capability/ownership | 403 | refrescar autoridad; no proyectar Cliente ajeno |
| recurso fuera de alcance | 404 seguro cuando corresponda | volver a selector autorizado |
| slot ocupado/bloqueado/equipo | 400/409 según contrato existente | consultar disponibilidad nuevamente |
| riesgo requiere revisión/no apto | outcome técnico explicable | usar revisión técnica; no crear diagnóstico ficticio |
| estado no finalizable | 409 | refrescar Turno; no forzar estado |
| ficha requerida incompleta | 400 semántico | completar la ficha del Detalle indicado |
| versión de ficha obsoleta | 409 | recargar y reconciliar; nunca sobrescribir |
| timeout de finalización | resultado incierto | retry manual con el mismo `Idempotency-Key` |
| clave incompatible | 409 | recuperar resultado o iniciar comando realmente nuevo |

## 13. Defectos y cambios de implementación

No se encontró un defecto en los contratos publicados de los Incrementos 0–4.
No se modificó código productivo ni se agregó una API.

Se agregó una suite de 18 pruebas de integración que fija el contrato
presencial y se incorporó al bloque B3 de CI. El conteo B3 pasa de 192 a 210.

## 14. Tests y regresiones

| Suite / bloque | Resultado |
|---|---:|
| Compatibilidad presencial Incremento 5 | 18/18 |
| Focal finalización, perfil, fichas, efectos, contexto, riesgo y creación | 152/152 |
| Frontend completo | 438/438 |
| Build React | aprobado con warnings preexistentes |
| B1 — roles, usuarios y Personal | 416/416 |
| B2 — diagnóstico, ficha y rutinas | 216/216 |
| B3 — agenda, Turnos y flujos profesionales | 210/210 |
| B4 — catálogos, inventario y órdenes | 79/79 |
| B5 — Caja, pagos e incidencias | 170/170 |
| B6 — Django Admin y auditoría | 43/43 |
| B7 — concurrencia PostgreSQL | 69/69 |
| Django check / migraciones | aprobados, sin cambios |

La matriz B1–B7 ejecutó **1.203/1.203 pruebas backend únicas**. Las
ejecuciones focales se informan por separado y no se suman a ese total. Los
warnings del build React y de algunas pruebas frontend ya existían antes del
incremento y no corresponden a archivos modificados aquí.

No hay cambios frontend productivos; la suite y el build React se mantienen como
regresión requerida para confirmar que rutas, agenda y pantalla profesional no
cambiaron accidentalmente.

## 15. Decisiones pendientes

| ID | Decisión para tarea futura | Impacto |
|---|---|---|
| P1 | Datos mínimos y activación de identidad en BH-064 | determina si el alta existente puede reutilizarse sin cambios |
| P2 | Cómo un Turno presencial pasa de `SOLICITADO` a `CONFIRMADO` | habilita ficha y finalización sin alterar estado desde payload |
| P3 | Política de pago/seña del canal presencial | no debe inferirse ni acoplarse en este incremento |
| P4 | Orquestación de riesgo técnico en BH-063 | impide eludir reglas por Servicio |
| P5 | Si “llegada” o “inicio” usa `EN_PROCESO` | requeriría decidir también su finalización |
| P6 | Idempotencia de alta rápida y creación asistida | evita duplicar Cliente o Turno ante timeout |
| P7 | Alcance multiservicio de BH-063 | define payload y evaluación conjunta de riesgo/disponibilidad |

## 16. Riesgos residuales

1. El endpoint asistido existente puede crear `SOLICITADO` sin orquestar el
   evaluador moderno; BH-063 debe cerrar esa integración antes de considerarse
   completo.
2. `EN_PROCESO` es editable para ficha y producido por registrar llegada, pero
   no finalizable; no debe incorporarse al flujo oficial sin decisión.
3. La alta administrativa actual exige cuenta completa y contraseña temporal;
   puede no coincidir con la experiencia “rápida” que defina BH-064.
4. No existe aún idempotencia de comando para crear Cliente o Turno asistido.
5. Atención inmediata no significa omitir la restricción de intervalo futuro ni
   la disponibilidad autoritativa.
6. El recorrido profesional no muestra hoy la evidencia del evaluador de riesgo;
   BH-063 debe definir si esa evidencia se proyecta como contexto adicional o si
   queda resuelta antes de confirmar.

## 17. Criterio de compatibilidad

El Incremento 5 se considera compatible porque el recorrido profesional acepta
sin excepciones Clientes sin diagnóstico, conserva perfiles parciales y no
depende del canal de reserva. Las brechas identificadas pertenecen a la
orquestación y políticas futuras de BH-063/BH-064; se documentan como contratos
pendientes y no se ocultan mediante mocks, estados forzados o APIs ficticias.

No se inicia BH-063 ni BH-064.
