# Reauditoría independiente — BH-063/BH-064 después de AI-01–AI-05

**Fecha:** 2026-11-26. **HEAD auditado:** `6556209e4eea78055962928cbd4e11ec9ff62383`.
Rama `save/work-in-progress`; HEAD, upstream y referencia remota coincidieron al inicio y al verificar el inventario final.

## 1. Alcance y procedencia

Se leyó íntegramente la [auditoría original](AUDITORIA_INDEPENDIENTE_BH063_BH064.md), se contrastó la sección 14 del [consolidado](IMPLEMENTACION_BH063_BH064_CONSOLIDADA.md) con el delta de 24 archivos y se usaron las [decisiones y contratos](DECISIONES_Y_CONTRATOS_BH063_BH064.md) como criterio. El veredicto original, **BH-063/BH-064 = BLOQUEADOS** en `3209dbd0ea5d6dae26245c2967a43a2bc79dd1fb`, no cambia. Las 235 pruebas PostgreSQL, 60 Jest y el E2E previamente reportados por implementación no se contabilizan aquí.

Se auditó un `git archive` del commit exacto. PostgreSQL 16.9 en `127.0.0.1:55441`, bases `test_bh063064_6556209_*`, Django `bohemiacore.test_settings` y `StablePostgresTestRunner`; sin `--parallel` ni `--keepdb` dentro de los bloques. No se usaron la base de desarrollo, identidades reales, pagos reales ni SMTP de producción. La única escritura en archivos de trabajo del repositorio es este informe; los artefactos quedan fuera del repo.

D-01–D-07 son el alcance aprobado. No se evalúa D-08, reclamo telefónico verificable, diagnóstico automático ni autoevaluación. Se conservan BH-061 v1 y la separación de permisos: preparar pago asistido requiere `gestion.create_turno_for_client` **y** `gestion.register_payment`; conciliar exige `gestion.confirm_deposit` por separado. No se deduce autoridad de un rol nominal.

## 2. Matriz diferencial

| Hallazgo | Causa en `3209dbd` | Diferencia en `6556209` | Evidencia contrastada y estado |
|---|---|---|---|
| AI-01 · BH-063 | El consentimiento podía tomar el intento vigente B aunque se hubiese comunicado A. | `evaluacion_id` obligatorio, incluido en la huella; locks de solicitud y evaluación; evidencia derivada del snapshot del servidor. | Carrera con supersesión, referencia obsoleta, texto entrante rechazado, rollback y replay con la misma evidencia. **Corregido.** |
| AI-02 · BH-063 | El propietario web podía aceptar una advertencia asistida. | Owner **y** `WEB` explícito; registrante nulo o igual al propietario. Filtro en la API y revalidación en las operaciones de dominio. | Pruebas HTTP de aceptación, reevaluación, hold y preparación; web legítimo y retry. **Corregido** para las operaciones auditadas. |
| AI-03 · BH-063 | El 404 definitivo dejaba la pestaña sin salida o el comando en estado incierto. | Se distingue referencia inválida de un CREATE cuyo resultado no se observó. Salida explícita y recuperación autorizada del resto de la selección, sin POST automático. | React: reload, raíz y alta descartables, conservación de Cliente válido, timeouts, 401/403/409. **Corregido** para el 404 definitivo del dominio. |
| AI-04 · BH-064 | Alta y selector sin límite compartido. | Buckets PostgreSQL con HMAC, UPSERT atómico y reloj de BD. Cuotas previas a búsqueda y creación por actor. | Ventana, límite, permiso antes de cuota, reintento idempotente y ocho conexiones simultáneas. **Corregido.** |
| AI-05 · BH-064 | El request síncrono trasladaba el fallo y el tiempo del proveedor a la respuesta pública. | Solicitud pública genérica; cola transaccional con referencias y digest; emisión y envío en comando separado. | Pruebas de igualdad HTTP con fallo de proveedor, rollback, expiración, consumo único y verificación local del worker. **Corregido en código**; despliegue del worker **NO VERIFICADO**. |

### AI-01 — Identidad, locks y efectos

- [Serializador y proyección](../../bohemiacore/gestion/assisted_technical_booking_serializers.py): React envía el ID leído, no el snapshot. El comando rechaza campos técnicos ajenos al contrato. La clave del panel de consentimiento depende de la evaluación y reinicia la decisión si cambia la referencia visible.
- [Servicio](../../bohemiacore/gestion/assisted_technical_booking_services.py#L450-L559): identidad advisory y revalidación del actor, `FOR NO KEY UPDATE` para permitir referencias FK de auditoría concurrentes, y locks de solicitud → evaluación. Comprueba Cliente, vínculo con el número de intento vigente, estado `ADVERTENCIA_PENDIENTE`, outcome, mensajes y ausencia de supersesión. Un ID anterior no se sustituye: `409 STALE_TECHNICAL_EVALUATION`. Estado, evidencia, ledger y auditoría se escriben en una transacción; versión, códigos y textos provienen de la evaluación persistida.
- La suite [asistida](../../bohemiacore/gestion/tests/test_assisted_technical_booking.py) incluye `test_reevaluation_wins_lock_and_stale_consent_does_not_accept_replacement`, rollback al fallar auditoría y el caso idempotente positivo. Un replay válido recupera lo ya guardado, no produce un consentimiento nuevo; para huellas históricas requiere además que el ID enviado coincida con la evidencia antigua. No se certificó retrospectivamente qué se comunicó en registros anteriores al fix.

### AI-02 — Frontera de canales

- [Solicitud web y hold](../../bohemiacore/gestion/views.py): el filtro de origen no se puede elegir en el request. Aceptación y reevaluación repiten el control en [servicio](../../bohemiacore/gestion/technical_booking_request_services.py); creación/liberación de hold y opciones/creación de Intent lo comprueban también en sus servicios. Medio nulo o ambiguo falla cerrado; no se infiere desde `canal_origen` del Turno. La vía asistida requiere medio asistido, actor registrante y permisos efectivos.
- [Pruebas de solicitud](../../bohemiacore/gestion/tests/test_assisted_technical_booking.py#L510-L553) y [de pago](../../bohemiacore/gestion/tests/test_assisted_payments.py#L130): la solicitud ajena al canal se trata como ausente; no se crea aceptación web ni se cambia el estado por esa vía, y un hold asistido no habilita preparación web. El positivo web mantiene la aceptación propia y el retry sin segunda evidencia. Se revisaron las rutas registradas y la preparación asistida: no se encontró otro punto público que apruebe esa advertencia, cree un hold para ella o constituya un Intent sin pasar por esas reglas.
- Límite de la separación: lectura/cancelación del Intent propio y checkout de una obligación **ya preparada** conservan controles BH-058/C1, y Caja conserva sus permisos operativos. No equivalen a aceptar una advertencia ni a preparar un Intent nuevo. No se certificó separación absoluta de vistas financieras ni se inició un checkout externo.

### AI-03 — Qué descarta la UI y qué conserva

- [Recuperación y fallos de comandos](../../frontend/src/pages/admin/NuevoTurno.js#L493-L613): el 404 de una referencia confirmada, o un código de rechazo de dominio que identifica raíz/alta/Cliente, permite volver según la referencia inválida. La [salida explícita](../../frontend/src/pages/admin/NuevoTurno.js#L1054-L1067) sólo cambia el diario de esa pestaña y reconsulta por GET lo que aún puede recuperarse. Si se descarta un alta pero el Cliente sigue accesible, se conserva el Cliente sin volver a adjuntar el alta inválida. No borra datos persistidos ni autoriza repetir un movimiento financiero.
- Un GET de recuperación sin raíz visible con CREATE incierto no demuestra que no hubo commit. Se conservan clave, identidad y payload; el reenvío, si procede, es explícito y con los mismos datos. Un 404 sin contrato de dominio en un POST no se interpreta como prueba de ausencia de efecto. Algunos 404 de hold/finanzas reconsultan o se tratan como error de lectura; para estos últimos existe «Actualizar recorrido» para volver a consultar la raíz, no se inventa una clasificación transitoria.
- 401/403 bloquean el panel sensible; conflictos de identidad conservan el diario y el conflicto semántico de consentimiento exige volver a leer y decidir. La proyección de backend está filtrada por actor y permiso: un UUID por sí solo no otorga acceso. Cubre el [conjunto Jest de recepción](../../frontend/src/pages/admin/NuevoTurno.test.js); no prueba recuperación cuando el storage del navegador ya no está disponible ni cuando la infraestructura entrega un 404 genérico en lugar del contrato.

### AI-04 — Cuotas y reintentos

| Operación | Sujeto y ventana fija | Resultado al agotar |
|---|---|---|
| POST alta | Actor, 30 / 10 min | `429 RATE_LIMITED`, `Retry-After: 600` |
| GET alta / selector | Actor, 60 / min cada uno, buckets separados | `429`, `Retry-After: 60` |
| POST solicitud de reclamo | Origen, 30 / 10 min; contacto normalizado, 3 / h | `429` por origen; por contacto el mismo `200` sin encolar |
| POST confirmación de reclamo | Origen, 30 / 10 min, separado de solicitud | `429`, `Retry-After: 600` |

[Limitador](../../bohemiacore/usuarios/walkin_rate_limits.py): un `INSERT … ON CONFLICT … DO UPDATE … WHERE … RETURNING` serializa cada sujeto en la primaria, incluso al crear el bucket. El reloj es `statement_timestamp()`; una denegación no prorroga la ventana. Se guarda digest HMAC en clave separada por propósito, no IP/email claro. Detrás de una IP compartida las cuotas de operadores son independientes; para el reclamo anónimo se usa `REMOTE_ADDR`, IPv6 por `/64`, nunca una cabecera libre del solicitante.

[Vistas](../../bohemiacore/usuarios/walkin_views.py): las rutas autenticadas revisan usuario activo y permiso antes de cuota y la cuota precede a la búsqueda, validación y ledger. Un retry puede recibir `429`, pero no crea otra identidad: puede usar su GET acotado al actor o volver con la misma clave tras esperar. En el selector no se agregan datos en el `429`; el acceso autorizado sigue viendo coincidencias activas minimizadas y paginadas (no anonimato frente a un operador autorizado). Los tests [BH-064](../../bohemiacore/usuarios/test_walkin_client_bh064.py#L440-L506) prueban 3 permitidos y 5 limitados en ocho conexiones con umbral reducido de fixture, reset tras expirar, separación por actor y limpieza selectiva. No se hizo prueba de carga de producción ni de disponibilidad bajo abuso distribuido.

### AI-05 — Reclamo y frontera entre HTTP y entrega

- En el POST válido conocido y desconocido se observa el mismo `200`, cuerpo genérico y cabeceras, también cuando se simula excepción de correo o un retorno de cero envíos en el worker. No se prueba latencia constante; la espera de SMTP desaparece del HTTP. Cuota por contacto silenciosa y cuota por origen independiente del contacto.
- [Servicio de reclamo](../../bohemiacore/usuarios/web_access_claim_services.py#L75-L185): el job guarda ID interno nullable, HMAC de contacto y fecha, sin email en claro ni token. El procesador bloquea con `FOR UPDATE SKIP LOCKED`, revalida identidad, contacto, elegibilidad y vigencia de 15 min. El token sólo se almacena como digest, expira a los 60 min desde la emisión y no habilita credenciales hasta su confirmación única. Emisión y confirmación serializan sobre Usuario; se vuelve a comprobar el token bajo lock. Contacto cambiado, cuenta no elegible o job vencido no envían.
- Fallo conocido: rollback del token nuevo, revocación previa y auditoría de emisión; el token anterior sigue válido si no expiró ni se consumió. El job se elimina y se registra sólo `web_access_claim_delivery_failed`, sin excepción, destinatario ni credencial. Un fallo inesperado/interrupción antes del commit revierte la transacción y deja el job para un nuevo intento, sujeto a TTL. SMTP y commit PostgreSQL no son atómicos: una interrupción tras aceptación por el transporte puede dejar un enlace no válido en un correo, y un nuevo intento puede emitir otro. No hay garantía de entrega exactamente una vez ni reintento automático de un fallo conocido de transporte. La cantidad «procesadas» no equivale a «entregadas».

## 3. Regresión y evidencia nueva

Se ejecutó una vez cada bloque de la [matriz versionada](../../.github/workflows/bh060-permisos.yml), con sus etiquetas exactas. Los IDs enumerados por el runner se cotejaron con los resultados: **1.292 ejecutados, 1.292 únicos, 0 duplicados, 0 omitidos** dentro del conjunto B1–B7.

| Bloque | Área | Aprobados / ejecutados | Exit |
|---|---|---:|---:|
| B1 | Roles, usuarios y Personal; alta, cuotas y reclamo | 448/448 | 0 |
| B2 | Diagnóstico, ficha y rutinas; BH-057 y consentimiento | 238/238 | 0 |
| B3 | Agenda, Turnos, holds y CU-27 | 224/224 | 0 |
| B4 | Catálogos, inventario y órdenes | 79/79 | 0 |
| B5 | Caja, pagos e incidencias | 180/180 | 0 |
| B6 | Django Admin y auditoría | 43/43 | 0 |
| B7 | Concurrencia PostgreSQL: evaluación, cuotas, reclamo, holds y pagos, entre otros | 80/80 | 0 |

Evidencia: `B1.log`–`B7.log`, `matrix-results.json`, `matrix-labels.json` e `ids-B1.log`–`ids-B7.log`. La enumeración no se contabiliza como otra ejecución. No se extrapola la cobertura a suites fuera de las etiquetas, servicios remotos ni usuarios reales.

- **Jest completo:** 49/49 suites, 488/488 tests, salida 0; una ejecución en serie, sin snapshots. **Focal repetida de recepción:** 15 aprobados, 21 fuera del filtro, salida 0; los 15 ya están incluidos en los 488. No se suman al total ni son probes nuevos.
- **Probes independientes PostgreSQL del worker: 3 IDs distintos comprobados**, fuera de la matriz. (1) HTTP uniforme conocido/desconocido, sin envío ni credenciales antes de procesar; `--limit 1`, entrega en memoria, confirmación válida sólo una vez y drenaje de la cola. (2) `KeyboardInterrupt` simulado antes de commit: rollback, trabajo retenido y envío de prueba al reanudar. (3) otra conexión salta el job bloqueado, procesa el siguiente y el vencido luego se descarta sin token. Logs `claim-worker-audit*.log`: el primer ciclo HTTP se repitió por errores del harness en los nombres/campos obligatorios del formulario de confirmación; la ejecución con `password` y `password2` pasó. Las dos ejecuciones previas de ese ID no se suman como resultados distintos. No hubo SMTP real ni se simuló caída después de la aceptación del transporte.
- `check`, `makemigrations --check --dry-run` y ambos `sqlmigrate usuarios 0005/0006`: salida 0. `staticfiles.W004` corresponde al directorio `static` no versionado que falta en el snapshot; sin drift. `0005` crea bucket con PK y expiración indexada; `0006` crea cola con PK identity, referencia nullable, digest y fecha; no hay backfill. Aplicación de migraciones sólo en la auditoría aislada.
- Build React estándar: salida 0, con avisos. Build `CI=true`: **salida 1**, Webpack `Critical dependency: the request of a dependency is an expression` y 18 avisos ESLint en 10 archivos. Ambos grupos están presentes en los logs de `3209dbd`; la comparación archivo/línea/regla de ESLint no encontró diferencias. También se observaron avisos preexistentes de Browserslist y Node `DEP0176`. No es una regresión del delta; el build estricto sigue siendo un impedimento si se exige como gate de despliegue.
- Logs: `%LOCALAPPDATA%/Temp/opencode/bh063-064-reaudit-6556209/logs/`. Allí quedan también manifiestos de etiquetas/IDs y códigos de salida. `git diff --check` del delta y del árbol, enlaces relativos y revisión por patrones del delta, sin incidencias; el chequeo de secretos no fue un escaneo dedicado ni una certificación de todo el repositorio.

## 4. E2E aislado

Microsoft Edge headless `158.0.4370.33` con el build estándar del snapshot, Django local y base `test_bh063064_6556209_e2e`. Datos sintéticos, correo en memoria y sin proveedores de pago.

| Escenario | Observación |
|---|---|
| Alta y selección | Login real del operador; alta `201`, handoff y selección desde recepción. La BD confirmó una sola alta. |
| 404 definitivo | Selección sintética inactivada en la BD de auditoría; reload obtuvo `404` del selector. «Volver a selección de Cliente» permitió elegir otro Cliente en la misma pestaña, sin editar el storage. |
| Solicitud y advertencia | Solicitud asistida `201`; se mostró la advertencia generada por BH-057. |
| Canal y autoridad | La cuenta sintética propietaria recibió `404` al intentar aceptación web de esa solicitud asistida y `403` al consultar el detalle asistido sin permiso. Sin evidencia de aceptación web en BD. No es una prueba exhaustiva de rutas o sesiones. |
| Consentimiento vigente | POST asistido `200`; BD confirmó evaluación vigente, actor y texto esperado; luego disponibilidad `200`. |
| Hold | Creación `201` desde la UI; «Actualizar estado» hizo GET `200` y mostró hold activo; la BD confirmó vínculo con la solicitud. No se crearon Pagos ni Intents. |

Log: `e2e-reaudit.log`. Se observaron todas las respuestas y la comprobación final de BD, pero el harness agotó su timeout al salir: no se atribuye un exit 0 al proceso E2E. Checkout/conciliación en navegador y correo externo **NO VERIFICADOS**; sus pruebas automatizadas de dominio no equivalen a un E2E externo.

## 5. AI-06 — Ruta legacy

**Persistente.** [La creación legacy](../../bohemiacore/gestion/views.py#L2107-L2129) sigue disponible por HTTP con autenticación, usuario activo y `gestion.create_turno_for_client`. No requiere staff nominal ni hay consumidor de `crear-para-cliente` en `frontend/src`. Persiste un Turno `SOLICITADO` con canal histórico `PRESENCIAL`, sin BH-057, ledger asistido ni Intent. El aviso legacy basado en categoría/espera no sustituye al evaluador. `SOLICITADO` aparece en `ACTIVE_TURNO_STATES`: se usa para detectar solapes de profesional, Cliente y equipo, por lo que **sí reduce disponibilidad**. [Regresión HTTP](../../bohemiacore/gestion/tests/test_turno_creation_api.py) cubre permiso efectivo, rechazo a Cliente sin permiso, estado fijado por servidor y `SLOT_UNAVAILABLE` con un `SOLICITADO` que ya ocupa el intervalo.

Se revisaron las transiciones posteriores: CRUD Turno no permite escribir estado; el comprobante legacy sólo actualiza el archivo de un Turno `ESPERANDO_SENA`; `registrar_pago` legacy responde 409 y la conciliación vigente exige un Intent. Reprogramación/cancelación no confirman; llegada y finalización rechazan `SOLICITADO`. La escritura moderna de `CONFIRMADO` [consume un hold y crea un Turno nuevo](../../bohemiacore/gestion/slot_hold_consumption_services.py#L331-L441), revalida la vigencia técnica y depende de la cadena financiera; no promueve el Turno legacy. No se encontró una ruta posterior que confirme ese `SOLICITADO` sin BH-057 en el código y APIs auditados. La constatación de capacidad se basa en código y regresión existente, no en una prueba contra un despliegue.

Conclusión: compatibilidad legacy acotada en **confirmación**, con impacto real de agenda. No bloquea por sí sola el contrato actual de confirmación BH-063, pero impide afirmar que toda ocupación presencial pasa por BH-057. Antes del cierre oficial, inventariar consumidores, acordar su deprecación o documentar explícitamente la excepción y asignar responsable. Si la regla de operación pretende exigir BH-057 antes de **cualquier** ocupación, debe cerrarse la ruta antes de aplicar esa regla. Consumidores y datos históricos desplegados: **NO VERIFICADOS**.

## 6. Condiciones de despliegue y límites

1. Aplicar `usuarios.0005–0006` antes de habilitar las rutas. HTTP y worker deben apuntar a la misma primaria PostgreSQL y usar la misma `SECRET_KEY`; coordinar rotaciones, que afectan buckets y trabajos pendientes. Migración y aplicación en auditoría no prueban migración en destino.
2. Ejecutar `process_web_access_claims --limit 50` con scheduler supervisado (por ejemplo cada minuto, ajustar al volumen), con backlog por debajo de 15 min, y programar `prune_walkin_rate_buckets`. Alertar por antigüedad y tamaño de cola, última ejecución y el evento de fallo. Validar backend de correo, remitente y URL HTTPS de reclamo; no registrar cuerpos, enlaces de reclamo ni credenciales en proxy/APM. Hacer una comprobación de entrega y consumo con identidad sintética en preproducción antes de habilitar tráfico.
3. Verificar en el proxy la asignación confiable de `REMOTE_ADDR`; sin ella los reclamos anónimos originados detrás del proxy pueden compartir cuota. Revisar registros históricos ambiguos sin inferir origen ni reescribir aceptaciones; pueden dejar de continuar por el canal web. Más de un tipo de lectura autorizada no equivale a permitir operaciones entre canales.
4. Scheduler/worker desplegado, SMTP externo, proxy, configuración de logs del entorno, carga, datos históricos y estado efectivo del CI remoto: **NO VERIFICADOS**. El comando existe y se probó localmente; el delta no instala un scheduler. Este informe no habilita tráfico, no certifica entrega externa y no inicia el cierre oficial ni modifica el backlog.

## 7. Veredictos técnicos separados

| Tarea | Veredicto independiente | Fundamento |
|---|---|---|
| **BH-063** | **LISTO PARA CIERRE TÉCNICO** | AI-01–AI-03 corregidos en los contratos revisados, sin regresión en B1–B7/Jest y con los escenarios funcionales observados en Edge. No se encontró confirmación legacy sin cadena moderna; queda documentado el impacto legacy sobre capacidad. |
| **BH-064** | **LISTO PARA CIERRE TÉCNICO** | AI-04 corregido; AI-05 corregido en código con procesamiento y consumo probados en aislamiento. No habilitar el reclamo hasta verificar migraciones, scheduler, configuración de proxy y una entrega de prueba en destino. |

No se identificaron bloqueantes funcionales del delta para las dos tareas. El build estricto sigue fallando por avisos preexistentes; no se declara verde ni se da por cumplida ninguna condición operativa. Se verificó que el inventario de trabajo sólo agrega este informe; hashes del informe histórico y `settings.py` intactos y el índice vacío. No se hizo stage, commit ni push.

**BH-063/BH-064 = LISTOS PARA CIERRE TÉCNICO**
