# Cierre técnico BH-063 — Turnos asistidos/presenciales

**Veredicto: BH-063 = CERRADO TÉCNICAMENTE.** Baseline funcional reauditado: `6556209e4eea78055962928cbd4e11ec9ff62383`, en `save/work-in-progress`. El cierre se limita al recorrido asistido aprobado; no certifica preparación para producción.

## Alcance e incrementos

Recepción puede seleccionar un Cliente activo o continuar desde el [alta rápida BH-064](../BH-064/CIERRE_BH064_ALTA_RAPIDA_CLIENTE_PRESENCIAL.md), registrar una solicitud por teléfono o presencial y completar la cadena técnica y financiera que produce un Turno confirmado. Se mantienen [D-01–D-07 y los contratos A–G](../generales/DECISIONES_Y_CONTRATOS_BH063_BH064.md), BH-061 v1 y la autoridad de los servicios BH-057/BH-058. **D-08**, excepción de confirmación sin el prepago exigido, quedó fuera de alcance y no se implementó. No se incorporaron diagnóstico automático, autoevaluación ni reclamo telefónico verificable.

| Incremento | Commit | Resultado |
|---|---|---|
| 0–1 | `408132d`, `c62421f` | Decisiones y contratos; identidad presencial utilizable en recepción. |
| 2 | `23e1e0d` | Solicitud asistida, evaluación BH-057, consentimiento y registro causal de operaciones. |
| 3 | `df9335c` | Disponibilidad, primer intervalo futuro y hold asistido. |
| 4 | `ff1cea9` | Preparación del Intent, confirmación financiera y compatibilidad de inicio/finalización profesional. |
| 5 | `3209dbd` | Recorrido de recepción, continuidad desde alta, recuperación, Caja y destinos autorizados. |
| Corrección | `6556209` | AI-01–AI-03 de BH-063 y AI-04–AI-05 de BH-064. |

El [consolidado de Incrementos 1–5 y correcciones](../generales/IMPLEMENTACION_BH063_BH064_CONSOLIDADA.md) contiene los contratos de las APIs, la cadena de migraciones `gestion.0045–0048` y la trazabilidad de implementación.

## Recorrido y garantías auditadas

1. **Solicitud y riesgo.** El operador activo necesita `gestion.create_turno_for_client` y actúa con su identidad, no como el Cliente. La solicitud admite uno o más Servicios en orden y registra `PRESENCIAL` o `TELEFONO`, Cliente y operador por separado. BH-057 determina el resultado con una evaluación versionada; no se reserva capacidad por el mero registro. Recepción no adquiere permiso de revisión técnica ni ve diagnósticos, fórmulas o snapshots internos. Web y asistido se separan por procedencia y autoridad en el backend.
2. **Consentimiento asistido.** Ante `ADVERTENCIA`, la decisión identifica con `evaluacion_id` el intento comunicado. La persistencia bajo locks verifica Cliente, intento y vigencia; guarda actor, Cliente informado y textos/códigos de la evaluación, no valores editables por el operador. Una evaluación reemplazada devuelve `409`; sólo `ACEPTA` habilita la continuación, no el rechazo ni el consentimiento no obtenido.
3. **Disponibilidad y hold.** Sólo se ofrece capacidad para el contexto técnico aprobado y vigente. La consulta es orientativa; el alta del `SlotHold` comprueba bajo locks y reloj PostgreSQL jornada, grilla, bloqueos, duración, skills, equipo y solapes. La atención inmediata selecciona el primer intervalo estrictamente futuro de la fecha evaluada. La retención es temporal, con expiración y liberación atribuida al operador; no es un Pago ni un Turno.
4. **Pago y confirmación.** Preparar el `PaymentIntent` requiere **ambos** permisos, `gestion.create_turno_for_client` y `gestion.register_payment`. La `PaymentPolicy` publicada y el backend fijan moneda, importes y umbral; preparar no registra dinero. En Caja, `gestion.confirm_deposit` es una autoridad separada para conciliación manual. Sólo al alcanzar el umbral con pagos conciliados y revalidar contexto y capacidad se aprueba el Intent, se consume el hold y se crea un único Turno `CONFIRMADO`. Si el pago llega tarde, procede el tratamiento BH-058; no se reactiva el hold ni se genera confirmación artificial.
5. **Inicio y finalización.** El Turno no nace en `EN_PROCESO`. «Iniciar atención» usa la transición autorizada y auditada `CONFIRMADO → EN_PROCESO`. La finalización mantiene los dos orígenes autorizados, `CONFIRMADO` y `EN_PROCESO`, hacia `REALIZADO`, con `gestion.finalize_service`, Personal activo asignado, precondiciones técnicas, efectos únicos y rollback. Agenda, Caja y trabajo técnico conservan sus propios permisos.

Los comandos idempotentes conservan registro de operaciones, actor, digest de clave y huella del comando; un reintento compatible no duplica efectos y uno incompatible devuelve conflicto. La recuperación por GET exige actor y permiso efectivos: un UUID no autoriza acceso. El 404 definitivo permite abandonar sólo la referencia inválida; una respuesta incierta conserva clave y payload, sin segundo POST automático. La recuperación es local a actor y pestaña; si se pierde, verificar Caja y agenda antes de cualquier nuevo cobro.

## Excepción legacy — AI-06 persistente

`POST /api/gestion/turnos/crear-para-cliente/` permanece disponible por HTTP para un usuario autenticado, activo y con `gestion.create_turno_for_client` efectivo; no basta un rol nominal y no se halló un consumidor en `frontend/src`. Crea un Turno `SOLICITADO` con canal histórico `PRESENCIAL`, sin BH-057, consentimiento asistido, ledger ni Intent. Su alerta por categoría y espera no equivale a una evaluación BH-057. **El registro sí ocupa capacidad**: se considera en solapes de profesional, Cliente y equipo.

La reauditoría no encontró una transición posterior que promueva ese registro a `CONFIRMADO` sin la cadena moderna. No hay escritura genérica de estado; el registro de pago legacy devuelve `409`, y llegada/finalización no admiten `SOLICITADO`. La confirmación moderna crea un Turno nuevo al consumir un hold autorizado, no promueve el legacy. Esta conclusión se limita al código y APIs auditados; no se verificaron consumidores ni datos del entorno desplegado.

La excepción se documenta como compatibilidad acotada, no como cumplimiento BH-057 ni como nueva autorización funcional. No usarla como alternativa para el recorrido asistido. Si se exige BH-057 antes de cualquier ocupación, debe retirarse o adaptarse la ruta antes de aplicar esa regla. **Seguimiento:** corresponde al propietario del backlog asignar responsable operativo de Agenda/Recepción, inventariar consumidores y tramitar el retiro controlado o la adaptación en una tarea separada. Este cierre no altera la ruta ni crea esa tarea.

## Evidencia y estado operativo

- [Auditoría original](../generales/AUDITORIA_INDEPENDIENTE_BH063_BH064.md), `3209dbd0ea5d6dae26245c2967a43a2bc79dd1fb`: **BLOQUEADO** por AI-01–AI-03 en BH-063. [Reauditoría diferencial](../generales/REAUDITORIA_BH063_BH064_POST_AI01_AI05.md), `6556209e4eea78055962928cbd4e11ec9ff62383`: hallazgos corregidos en el alcance probado y **listo para cierre técnico**. No se cambia el dictamen original.
- Regresión independiente común: **1.292/1.292** en PostgreSQL B1–B7 y **488/488** en Jest (49 suites); las 15 focales repetidas de recepción ya están incluidas en Jest. Django `check`, comprobación de drift y SQL `usuarios.0005–0006` aprobados en auditoría. No se repitieron las suites ni se desplegó en este cierre.
- Edge aislado: alta y selección, solicitud, consentimiento vigente, rechazo de cruce web y de detalle sin permiso, recuperación en la misma pestaña tras 404, y creación y lectura del hold. Comprobaciones de escenarios y BD favorables, **timeout durante la salida del harness**, sin atribuirle exit 0. No se crearon Pagos ni Intents; checkout y conciliación en navegador quedaron **NO VERIFICADOS**. Las suites financieras y de finalización no equivalen a ese E2E.

| Estado | Condición |
|---|---|
| Cierre técnico | Aprobado para el alcance reauditado. AI-06 sigue como riesgo residual de agenda. |
| Preparación para despliegue | Pendiente. Verificar la cadena de migraciones, datos históricos, permisos efectivos y configuración del entorno. No inferir el medio de solicitudes históricas ambiguas ni reescribir evidencia. |
| Pruebas manuales integrales | Pendientes: recepción–Caja–confirmación–trabajo profesional, recuperación tras sesión y transferencia, caducidad/solapes y continuidad cuando se pierde el borrador. |
| Build React | Estándar aprobado. `CI=true` falla por avisos ESLint preexistentes (18 en 10 archivos) y un aviso Webpack también preexistente; si es gate, sigue impidiendo desplegar. CI remoto **NO VERIFICADO**. |

El countdown es informativo; la capacidad puede cambiar antes del comando. No se amplía la política capilar multiservicio ni se certifican históricos, recuperación automática de un ledger alterado o sincronización de borradores entre dispositivos. El propietario debe actualizar manualmente BH-063 en el backlog oficial externo; este cierre no cambia `BACKLOH.xlsx`.
