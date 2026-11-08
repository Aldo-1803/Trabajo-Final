# Flujo objetivo de Solicitud a Confirmación de Turnos

> **Alcance:** análisis de arquitectura y propuesta de negocio. No modifica
> modelos, endpoints ni autorizaciones. Se basa en el código actual luego de
> BH-055 (reprogramación/cancelación semánticas).

## Resumen ejecutivo

El flujo actual trata a `Turno` como solicitud, reserva de agenda, evaluación
técnica, espera de seña y cita operativa al mismo tiempo. Esto obliga a que
gran parte de los casos parezcan necesitar revisión humana y, más grave, hace
que una solicitud sin pago pueda consumir un slot indefinidamente.

El flujo objetivo recomendado es:

```text
selección de servicio y preferencia de horario
  -> SOLICITUD
  -> evaluación técnica automática
       APTO / ADVERTENCIA -> aprobación automática
       REQUIERE_REVISION  -> cola técnica; no bloquea el slot
       NO_APTO            -> rechazo técnico; no bloquea el slot
  -> revalidación canónica de disponibilidad
  -> HOLD temporal del slot
  -> intención/preferencia de pago (seña o total)
  -> webhook Mercado Pago validado por backend
  -> Pago registrado + Turno confirmado + HOLD consumido
```

La regla clave es: **una solicitud no es un HOLD y un HOLD no es un Turno
confirmado**. El Profesional sólo interviene en `REQUIERE_REVISION` (y en
excepciones de pago), no en cada solicitud normal.

---

## 1. Inventario actual

### 1.1 Información técnica disponible

| Fuente actual | Datos utilizables | Situación para decisión de reserva |
|---|---|---|
| `DiagnosticoCapilar` | tipo, grosor, porosidad, cuero cabelludo, estado general, fecha, regla/mensaje y servicio urgente | Existe histórico; el motor actual clasifica salud general, pero no devuelve un contrato de aptitud para un servicio solicitado. |
| `DetalleTurno` + `Turno` | servicios realizados, fecha/hora, duración y estado | Permite medir intervalos y combinaciones si se filtra por servicios realmente realizados. |
| `FichaTecnica` | fórmula libre, observaciones, resultado, porosidad/estado final y autor | Muy útil para revisión humana; no es fiable para automatización mientras fórmula/observaciones sean texto libre. |
| `Servicio` | categoría, duración, precio, plantilla de fórmula, impacto de porosidad/estado, agresividad química, días de espera | Es la base para reglas deterministas; hoy parte de esos campos no participa en la creación de Turnos. |
| `ReglaDiagnostico` | combinaciones de diagnóstico, prioridad, acción/mensaje, rutina y servicio sugeridos | Motor experto existente, pero orientado a recomendación, no a autorizar una solicitud. |
| `ConfiguracionDiagnostico` | umbrales y resultados de scoring | Existe un scoring de salud; requiere normalización/validación antes de convertirse en política de autorización. |
| `ReglaCuidado`/automatizaciones | cuidados y restricciones posteriores al servicio | Son señales de riesgo y contexto futuro; no forman parte hoy de la validación de reserva. |

### 1.2 Automatizaciones existentes relevantes

1. `TurnoCreationService._requires_hair_damage_alert()` marca
   `Turno.alerta_daño_capilar` si existe un **Turno realizado** de la misma
   categoría dentro de `Servicio.dias_espera_minima`. Es solamente una bandera;
   no bloquea, no clasifica riesgo, no genera cola y no condiciona el pago.
2. `SaludCapilarService.obtener_bloqueo_salud_capilar()` contiene una regla de
   enfriamiento para químicos agresivos, basada en la última `FichaTecnica`.
   **No tiene consumidores actualmente**, por lo que no protege reservas.
3. `DiagnosticoCapilarViewSet._ejecutar_motor_diagnostico()` ejecuta reglas
   expertas o scoring, asigna rutinas y puede sugerir un servicio/turno. No toma
   como entrada el servicio que el Cliente está solicitando.
4. Al finalizar un Turno, señales y `finalizar_turno` propagan impactos de
   `Servicio` al perfil de Cliente, crean/actualizan diagnóstico y rutinas. Es
   información valiosa para futuras evaluaciones, pero sucede después del
   servicio.
5. El motor de diagnóstico puede crear un Turno `sugerido`. Actualmente ese
   estado es considerado activo por disponibilidad, algo que contradice la
   semántica de una recomendación no aceptada.

### 1.3 Límites actuales de esos datos

- La relación entre servicio previo y servicio solicitado no está modelada como
  matriz/regla versionada; sólo existen propiedades individuales del servicio.
- Un diagnóstico puede no existir, estar incompleto o estar desactualizado.
- Una fórmula histórica libre no debe inferirse automáticamente como segura o
  incompatible sin estructura clínica/técnica adicional.
- Los endpoints de diagnóstico y fichas aún usan `is_staff` en rutas legacy;
  no deben usarse como solución de autorización para el diseño futuro.

---

## 2. Disponibilidad actual y problema del slot

`TurnoAvailabilityService.ACTIVE_TURNO_STATES` considera activos:

```text
solicitado, esperando_sena, confirmado, sugerido, pendiente, en_proceso
```

Esos estados bloquean tanto:

- solapamiento de `Personal`;
- duplicado del Cliente; y
- capacidad de `Equipamiento` obligatorio.

La creación y reprogramación canónicas bloquean filas de Cliente, Personal y
equipamiento aplicable dentro de una transacción y revalidan disponibilidad. Es
una buena base para serializar confirmaciones que usen el mismo servicio.
Consultar disponibilidad, en cambio, es sólo informativo: nunca garantiza que
el slot siga libre al confirmar.

| Estado actual | Qué bloquea hoy | Durante cuánto tiempo | Riesgo |
|---|---|---|---|
| `solicitado` | Personal, equipamiento y duplicado del Cliente | Hasta cancelación manual o hasta que pase la fecha/hora | Una solicitud sin revisión/pago puede ocupar agenda durante días o semanas. |
| `esperando_sena` | Igual | Hasta `fecha_limite_pago`, si fue configurada correctamente, o cancelación | Hay comando de limpieza para vencimiento, pero no hay un scheduler observado ni el flujo semántico que garantice asignar ese límite. |
| `confirmado` | Igual | Hasta completar/cancelar/reprogramar | Correcto para una reserva real. |
| `sugerido` | Igual | Indefinido | Una recomendación generada por diagnóstico puede bloquear un slot nunca aceptado. |
| `pendiente` | Igual | Hasta cancelación/manual o fecha pasada | Semántica ambigua; bloquea aunque no se sepa qué espera. |
| `en_proceso` | Igual | Hasta finalización | Correcto operacionalmente. |
| `realizado`, `cancelado`, `ausente` | No | N/A | No consumen disponibilidad canónica. |

El comando `limpiar_turnos` cancela `solicitado`, `esperando_sena` y `pendiente`
cuando la cita ya pasó, y cancela `esperando_sena` vencido por
`fecha_limite_pago`. No libera de forma temprana un `solicitado` no atendido,
ni un `sugerido`; además requiere ejecución programada externa para ser una
garantía operativa.

### Concurrencia hoy

Las operaciones canónicas recientes reducen carreras porque hacen
`select_for_update` sobre Personal y equipamiento antes de revalidar. Aun así,
esta garantía debe aplicarse a **toda** transición que cree un compromiso de
slot; endpoints legacy o escrituras directas no deben participar del flujo
futuro. La respuesta de disponibilidad no es una reserva.

---

## 3. Modelo objetivo: separar solicitud, HOLD y reserva

### 3.1 Alternativas evaluadas

| Alternativa | Ventaja | Problema |
|---|---|---|
| Agregar `hold_expires_at` y más estados a `Turno` | Migración inicial menor | Continúa mezclando negocio técnico, pago, agenda y operación; cada consulta debe deducir qué bloquea. |
| Usar `Turno` sólo para confirmados y crear entidades de solicitud/HOLD | Semántica clara, expiración aislada, auditoría y pagos idempotentes | Requiere migración de flujo y contratos nuevos. **Recomendada.** |

### 3.2 Entidades conceptuales recomendadas

No se implementan ni se fijan nombres de tablas en este análisis. El diseño
debe disponer, como mínimo, de estas responsabilidades separadas:

| Concepto | Responsabilidad | ¿Bloquea slot? |
|---|---|---|
| `BookingRequest` / Solicitud | intención del Cliente, servicios, preferencia de horario, evaluación técnica y decisión | No. |
| `TechnicalAssessment` | resultado reproducible, reglas/evidencia/versiones y decisión humana si aplica | No. |
| `SlotHold` | compromiso temporal de Personal, equipamiento, intervalo y vencimiento | Sí, sólo mientras esté activo. |
| `PaymentIntent` | importe requerido, tipo seña/total, proveedor, preference/payment IDs, estado y expiración | Sólo indirectamente: debe referenciar un HOLD activo. |
| `Turno` | cita ya confirmada y ciclo operativo real | Sí, hasta que sea final/cancelada. |
| `Pago` | registro contable inmutable de un pago provider/manual conciliado | No decide disponibilidad por sí mismo. |

Un HOLD debería tener, como mínimo conceptual: intervalo calculado,
profesional, requerimientos de recursos, `expires_at`, `released_at`, causa de
liberación y referencia única a la solicitud/intención. Un campo
`hold_expires_at` en `Turno` puede ser una implementación transitoria, pero no
reemplaza la separación conceptual.

### 3.3 Reglas de HOLD

1. No crear HOLD al enviar una solicitud ni mientras espera revisión humana.
2. Tras aprobación automática o humana, revalidar en backend con la lógica
   canónica y adquirir locks; sólo entonces crear HOLD.
3. TTL corto y configurable por servidor (por ejemplo, 10–15 minutos), no las
   24 horas de la actual seña. El TTL empieza al crear la intención de pago.
4. El worker de expiración libera HOLD e invalida la intención vencida de forma
   atómica e idempotente.
5. Pago aprobado antes de `expires_at`: el webhook consume HOLD y crea/confirma
   el Turno dentro de una transacción.
6. Pago fallido/rechazado/cancelado: liberar HOLD de inmediato; un pago
   `pending` no lo renueva indefinidamente.
7. Pago aprobado después de expirar/liberar: nunca recrear el slot. Registrar
   el pago para conciliación y derivar a reembolso/manual según política.
8. Reprogramar/cancelar un Turno confirmado libera su intervalo de agenda como
   ya hace el estado final; no reutilizar el mismo HOLD.

Un job periódico robusto (worker/beat/cron monitorizado) es obligatorio. Debe
existir también expiración defensiva en cada intento de consumir HOLD: no se
puede depender sólo del job.

---

## 4. Contrato de evaluación técnica para BH-057

### 4.1 Salida propuesta

`evaluate_booking_risk(cliente, servicios, fecha_preferida)` debe devolver un
resultado explícito, versionado y explicable:

```text
APTO
ADVERTENCIA
REQUIERE_REVISION
NO_APTO
```

Además del resultado, el contrato debe incluir sólo datos necesarios para el
flujo: códigos de reglas aplicadas, severidad, datos faltantes, fechas/servicios
relevantes, recomendación de fecha mínima o servicio alternativo, versión de
política y timestamp. La explicación para Cliente debe ser segura; el detalle
técnico completo corresponde al Profesional.

| Resultado | Acción automática | HOLD | Acción humana |
|---|---|---|---|
| `APTO` | aprobar solicitud y habilitar pago | Al iniciar pago | No. |
| `ADVERTENCIA` | aprobar; informar advertencia y requerir aceptación si la política lo exige | Al iniciar pago | No. |
| `REQUIERE_REVISION` | encolar para revisión técnica | No mientras espera | Sí, sólo Personal habilitado. |
| `NO_APTO` | rechazar técnicamente, ofrecer fecha/alternativa si existe | No | No, salvo override excepcional auditado. |

### 4.2 Criterios iniciales recomendados

| Señal | Resultado por defecto | Observación |
|---|---|---|
| Servicio no activo, Personal no compatible, fecha fuera de reglas | No es evaluación capilar: rechazo de disponibilidad | Se resuelve antes del análisis técnico. |
| Período de enfriamiento duro incumplido para químico agresivo | `NO_APTO` hasta fecha calculada | Reutilizar conceptualmente `dias_espera_bloqueo`, pero versionar la regla servicio previo → solicitado. |
| Diagnóstico reciente saludable, historial completo, sin reglas de incompatibilidad | `APTO` | Caso normal que elimina trabajo manual. |
| Riesgo moderado, diagnóstico válido y política permite continuar con aviso | `ADVERTENCIA` | No debe crear cola humana por sí solo. |
| Diagnóstico crítico, impacto acumulado, servicio químico agresivo tras antecedente relevante | `REQUIERE_REVISION` o `NO_APTO` según regla dura | La diferencia debe ser explícita en política, no inferida por UI. |
| Historial técnico incompleto para servicio de alto impacto | `REQUIERE_REVISION` | Puede requerir diagnóstico/foto/consulta, no un HOLD de horas. |
| Historial incompleto para servicio de bajo riesgo | `ADVERTENCIA` o `APTO` según política | No penalizar automáticamente todos los Clientes nuevos. |
| Fórmula/observaciones libres previas relevantes | `REQUIERE_REVISION` | Hasta que se estructuren, son evidencia humana y no una regla automática. |

El actual score de diagnóstico no puede usarse directamente sin auditar su
dirección: hoy los umbrales clasifican `puntos <= umbral` como crítico, pero el
texto de catálogo usa como ejemplo “Sano=10, Dañado=50”. BH-057 debe definir
una escala única y pruebas de borde antes de automatizar decisiones.

### 4.3 Información de la revisión profesional

La cola debe mostrar al revisor habilitado:

- servicio(s) solicitado(s), duración, profesional/preferencia y horario
  preferido, dejando claro que no está reservado;
- último diagnóstico completo, antigüedad y atributos faltantes;
- últimos servicios realizados, intervalos y servicios químicos relevantes;
- ficha técnica/fórmula/observaciones post-servicio y sus autores;
- impactos acumulados o reglas que causaron la escalación;
- resultado automático, evidencias, versión de política y opciones: aprobar,
  rechazar, pedir información/diagnóstico, proponer alternativa/fecha;
- decisión, motivo y actor auditados.

Si no responde dentro de la SLA, la solicitud expira o vuelve al Cliente como
“sin disponibilidad garantizada”; nunca permanece reteniendo agenda. Al aprobar,
el backend revalida el slot. Si ya fue tomado, ofrece disponibilidad actual y
no permite pagar el slot perdido.

BH-056 debe resolver quién está habilitado: el perfil `Personal` ya contiene
`realiza_diagnostico`, `realiza_color` y otras capacidades, y existen permisos
de diagnóstico/ficha. La revisión futura debe requerir **habilitación técnica
para el servicio/riesgo**, no `is_staff`, ni el rótulo de rol. BH-057 define el
workflow y permisos específicos de decidir evaluación; BH-056 aporta las
skills verificables.

---

## 5. Mercado Pago y seña/pago total

### 5.1 Reutilizable hoy

Existe una integración para compras de productos, no para Turnos:

- configuración por `MERCADO_PAGO_ACCESS_TOKEN`, public key, URL pública,
  webhook y back URLs en `settings.py`;
- `MercadoPagoService.crear_preferencia(OrdenCompra)`;
- `POST /api/gestion/checkout/iniciar-pago/` y
  `POST /api/gestion/carrito/generar-pago-mercadopago/`;
- `POST /api/gestion/checkout/webhook/`, que consulta el pago al SDK de MP;
- `OrdenCompra.preference_id` y `Pago.transaccion_id` único.

Son reutilizables el cliente SDK, configuración de secretos, patrón de
consulta server-to-server y la idempotencia básica por `transaccion_id`. No se
debe reutilizar `OrdenCompra` para un Turno: su `external_reference` actual es
el ID numérico de una orden de productos y sus efectos descuentan stock.

### 5.2 Riesgos actuales que BH-058 debe cerrar

| Riesgo | Situación observada | Requisito futuro |
|---|---|---|
| Frontend como autoridad | Back URL sólo redirige; el webhook es el que cambia la orden, lo cual es correcto | Mantener: una redirección nunca confirma Turno/pago. |
| Autenticidad webhook | Se consulta el pago oficial, pero no se observa validación de firma `x-signature` ni almacenamiento de evento | Validar firma/secret según MP, registrar evento y responder idempotentemente. |
| Referencia ambigua | `external_reference` es el ID de `OrdenCompra` | Usar referencia namespaced, opaca e inmutable de `PaymentIntent` de Turno. |
| Importe/moneda | El webhook registra `transaction_amount`; no compara contrato de importe/currency ni estado esperado | Comparar monto, moneda, receptor, referencia y tipo de intención antes de confirmar. |
| Duplicados | `Pago.transaccion_id` es único, útil contra mismo payment ID | Añadir idempotency key de intención/evento y locks sobre intención/HOLD/Turno. |
| Pago tardío | Una orden cancelada podría ser completada por un webhook aprobado tardío | Si HOLD/intención expiró, no confirmar; conciliar/reembolsar según política. |
| Reintentos de webhook | No existe entidad de eventos/procesamiento observable | Persistir provider event/payment snapshot y resultado de procesamiento. |

### 5.3 Secuencia propuesta de pago

```text
backend: aprobar solicitud
backend: lock recursos + revalidar slot + crear SlotHold activo
backend: crear PaymentIntent (DEPOSIT o FULL, monto inmutable, vence con HOLD)
backend: crear preferencia MP con external_reference del PaymentIntent
frontend: sólo redirige a init_point y muestra estado de espera
Mercado Pago -> webhook backend
backend: valida firma + consulta operación oficial + lock intent/HOLD
  approved y vigente -> Pago + confirmar Turno + consumir HOLD
  rejected/cancelled  -> marcar intento + liberar HOLD
  pending             -> mantener sólo hasta el vencimiento fijo
  late/invalid        -> registrar y conciliar; no reservar slot
```

No debe mantenerse una transacción de base abierta durante la llamada remota a
Mercado Pago. Crear HOLD/intención primero, invocar proveedor fuera del lock de
larga duración y, si la preferencia falla, liberar el HOLD mediante transición
idempotente. Un outbox/retry es recomendable para que fallos entre ambos pasos
sean recuperables.

### 5.4 Seña y pago total sin multiplicar estados de Turno

El mismo flujo soporta ambos si la elección vive en `PaymentIntent`, no en
`Turno.estado`:

| Dato económico | Fuente de verdad propuesta |
|---|---|
| total del servicio | suma/snapshot de `DetalleTurno.precio_historico` o importe total inmutable de solicitud confirmada |
| seña requerida | política snapshot al aprobar (`deposit_required`) |
| modalidad | intención `DEPOSIT` o `FULL` |
| abonado | suma de pagos conciliados, no valor enviado por frontend |
| saldo | `total - total_abonado`, calculado o materializado de forma transaccional |

Una seña aprobada suficiente y un pago total aprobado pueden producir el mismo
resultado de agenda: `Turno` confirmado. La diferencia queda en pagos/saldo,
no en estados como “confirmado_con_seña” versus “confirmado_total”. Los campos
actuales `monto_abonado`, `saldo_pendiente`, `tipo_pago_registro` y
`fecha_limite_pago` son antecedentes útiles, pero BH-058 debe decidir un único
origen de verdad junto a `Pago`; hoy no están integrados con el webhook de
Turnos.

---

## 6. Auditoría de `Turno.estado`

| Estado actual | Qué significa hoy | Dimensión | ¿Debe seguir en `Turno.estado`? | Propuesta |
|---|---|---|---|---|
| `solicitado` | cliente pidió turno; etiqueta “requiere análisis” | solicitud/técnica | No | `BookingRequest.SUBMITTED`; evaluación separada. |
| `esperando_sena` | aprobado pero sin pago | financiera/HOLD | No | `PaymentIntent.PENDING` + `SlotHold.ACTIVE`; vence corto. |
| `confirmado` | seña OK según etiqueta | agenda/financiera | Sí, sólo como cita confirmada | `Turno.CONFIRMADO`; pago separado. |
| `sugerido` | recomendación generada por diagnóstico | recomendación | No | recomendación/notificación o solicitud borrador sin bloquear agenda. |
| `pendiente` | semántica no definida de forma uniforme | ambigua | No | reemplazar por estados explícitos de solicitud/revisión/pago. |
| `en_proceso` | llegó y comenzó atención | operativa | Sí | `Turno.EN_PROCESO`. |
| `realizado` | servicio terminado | operativa | Sí | `Turno.REALIZADO`. |
| `cancelado` | cancelación, rechazo técnico o vencimiento | final, pero causa mezclada | Sí, como final | `Turno.CANCELADO` + causa/auditoría; rechazo previo pertenece a solicitud. |
| `ausente` | no-show | operativa | Sí | `Turno.AUSENTE`. |
| `alerta_daño_capilar` | booleano de riesgo | técnica | No como única decisión | sustituir/acompañar por `TechnicalAssessment.outcome` y evidencias. |

Modelo objetivo de dimensiones:

```text
Turno.status: CONFIRMADO | EN_PROCESO | REALIZADO | CANCELADO | AUSENTE
Solicitud.status: SUBMITTED | REVIEW_REQUIRED | APPROVED | REJECTED | EXPIRED | WITHDRAWN
TechnicalAssessment.outcome: APTO | ADVERTENCIA | REQUIERE_REVISION | NO_APTO
SlotHold.status: ACTIVE | CONSUMED | RELEASED | EXPIRED
PaymentIntent.status: CREATED | PENDING | APPROVED | REJECTED | EXPIRED | CANCELLED
```

No todos los modelos deben persistir un estado si puede derivarse con seguridad,
pero las transiciones con efecto externo (HOLD, pago, webhook, expiración)
deben ser explícitas, auditables e idempotentes.

---

## 7. Comportamiento determinista por escenario

| Escenario | Comportamiento objetivo |
|---|---|
| Pocos Clientes | Mismo flujo; casos aptos pasan sin revisión humana. |
| Muchas solicitudes simultáneas | Solicitudes no bloquean. Sólo el primer flujo que adquiere HOLD válido luego de lock/revalidación obtiene el slot. |
| Profesional tarda horas | `REQUIERE_REVISION` sigue en cola con SLA; no HOLD. Al responder, se revalida agenda. |
| Varios Clientes eligen el mismo slot | UI puede mostrarlo a todos; backend otorga un único HOLD atómico. Los demás reciben conflicto seguro y alternativas. |
| Dos pagos simultáneos de la misma intención | Lock de intención + idempotency key; un pago se aplica una vez, el excedente se concilia/reembolsa. |
| Webhook reenviado | Evento/payment ID ya procesado retorna éxito sin efectos duplicados. |
| Pago aprobado después de expiración | Registrar como pago tardío, no confirmar ni recrear HOLD; iniciar conciliación/reembolso según política. |
| Rechazo/fallo de pago | Liberar HOLD inmediatamente; la solicitud puede permitir nuevo intento si aún es válida. |
| Profesional rechaza mientras cliente intenta pagar | La decisión bloquea/termina intención bajo lock y libera HOLD. Un webhook posterior se trata como tardío/no aplicable. |
| Historial técnico incompleto | Bajo riesgo: aviso/política. Alto riesgo: revisión o diagnóstico. Nunca retener agenda por falta de datos. |
| Servicio previo dentro de intervalo prohibido | `NO_APTO`, mostrar fecha mínima/alternativa; sin HOLD ni pago. |
| Servicio previo relevante pero política no determinista | `REQUIERE_REVISION`; mostrar evidencia al Profesional. |

---

## 8. Frontera del backlog

| Backlog | Incluye | No incluye |
|---|---|---|
| **BH-055** | Permisos/UX operativa, agenda segura, creación/reprogramación/cancelación semánticas y disponibilidad canónica | aprobación técnica, HOLD, pagos, webhooks de Turnos. |
| **BH-056** | Skills/habilitaciones de Personal: quién puede color, diagnóstico o revisar casos técnicos; asignación por capacidad | motor de riesgo ni pago. |
| **BH-057** | Contrato `APTO/ADVERTENCIA/REQUIERE_REVISION/NO_APTO`, reglas servicio-historial, evaluación automática, cola y decisión técnica auditada | integración MP/caja definitiva. |
| **BH-058** | HOLD, intención/preferencia de pago de Turno, seña/total, webhook validado, idempotencia, `Pago`, conciliación y confirmación backend | inventar reglas clínicas/técnicas. |

### Orden recomendado

1. BH-056: definir capacidad verificable del revisor y compatibilidad de
   Personal con servicios.
2. BH-057: publicar el evaluador técnico y la cola de excepciones sin bloquear
   agenda mientras espera revisión.
3. BH-058: introducir HOLD e intención de pago para solicitudes aprobadas,
   integrando Mercado Pago por webhook backend.
4. Migrar progresivamente los estados legacy y eliminar los consumidores que
   aún dependan de `solicitado`/`esperando_sena`/`sugerido` como bloqueo.

## Conclusión

La reducción principal de trabajo manual no viene de acelerar la revisión de
todos los Turnos: viene de **no revisar los casos normales**. Un evaluador
determinista basado en intervalos, reglas de combinación, impactos, diagnóstico
vigente e integridad del historial puede aprobar automáticamente los casos
seguros, advertir los moderados y escalar sólo las excepciones. La agenda sólo
debe comprometerse brevemente al pagar; la confirmación sólo debe ocurrir por
una transición backend posterior a un pago conciliado por webhook.
