# Auditoría independiente — BH-063 y BH-064

**Fecha:** 2026-11-26. **HEAD auditado:** `3209dbd0ea5d6dae26245c2967a43a2bc79dd1fb`.
Rama `save/work-in-progress`; HEAD, upstream y referencia remota coinciden.

| Tarea | Veredicto | Motivo determinante |
|---|---|---|
| BH-063 — Turnos asistidos/presenciales | **BLOQUEADO** | Consentimiento no ligado al intento visto, mezcla de canales técnicos y recuperación que puede quedar sin salida. |
| BH-064 — Alta rápida presencial | **BLOQUEADO** | Protección de frecuencia no implementada en el alcance auditado y respuesta de reclamo no uniforme ante fallo del correo. |

## 1. Método, alcance y procedencia

Se usaron el [análisis original](ANALISIS_BH063_BH064_TURNOS_Y_ALTAS_PRESENCIALES.md),
las [decisiones y contratos](DECISIONES_Y_CONTRATOS_BH063_BH064.md) y la
[implementación consolidada](IMPLEMENTACION_BH063_BH064_CONSOLIDADA.md) como
criterios, no como evidencia de aprobación. Se inspeccionaron modelos, servicios,
vistas, permisos efectivos, clientes React y tests. Para las ejecuciones se
extrajo el commit exacto con `git archive` fuera del workspace; no se usó el
`settings.py` local modificado. Se emplearon Python 3.13.7, Django 5.2.7,
PostgreSQL 16.9 (clúster de auditoría en loopback) y Node 24.11.0 con las
dependencias frontend instaladas localmente. Los probes adicionales se
ejecutaron fuera del repositorio, con identidades sintéticas, sin correo real.

| Incremento | Commit | Delta comprobado |
|---|---|---|
| 0 | `408132d` | Análisis, D-01–D-07, contratos A–G; D-08 no autorizada. |
| 1 | `c62421f` | Identidad, deduplicación, claim, migraciones `usuarios.0003–0004`, pantallas y pruebas. |
| 2 | `23e1e0d` | Solicitud BH-057, consentimiento y ledger, `gestion.0045`. |
| 3 | `df9335c` | Disponibilidad y hold asistido, ledger y `OPERATOR_CANCELLED`, `gestion.0046`. |
| 4 | `ff1cea9` | Adapter financiero, consumo, estados de inicio/finalización, `gestion.0047`. |
| 5 | `3209dbd` | Proyección, referencia explícita al alta en `gestion.0048`, recuperación y destinos React. |

El delta `07e5810..3209dbd` se relaciona con el alcance: también amplía el
workflow de regresión y las dependencias CI. No cambia `usuarios/roles.py`,
artefactos versionados de BH-061, settings versionados ni planillas; no se
encontraron cambios funcionales ajenos en ese delta. Se conservaron settings,
media, Cypress, `show_urls.py` y demás cambios locales. No se hizo stage, commit
ni push; no se cambió el backlog.

## 2. Matriz de requisitos

**Comprobado** = evidencia directa en código y pruebas indicadas, o inspección
para una propiedad estática. **Parcial** = existe, con defecto o cobertura
incompleta. **No implementado** = ausente en el producto auditado. **No
verificado** = no se obtuvo evidencia suficiente. **Fuera de alcance** = no es
criterio exigible al bloque.

| Requisito | Estado | Evidencia y límite |
|---|---|---|
| BH-064 · Usuario y Cliente activos, email real o nulo, password inutilizable, rol CLIENTE y `PENDING_CLAIM` | **Comprobado** | [Servicio de alta](../../bohemiacore/usuarios/walkin_client_services.py#L229), constraints `usuarios.0003–0004`; B1 prueba contactos opcionales, estado, grants y rollback. No crea diagnóstico. |
| BH-064 · Normalización y coincidencia de email/teléfono, teléfonos compartidos, no autofusión | **Comprobado** | [`contact_normalization.py`](../../bohemiacore/usuarios/contact_normalization.py), revisión explícita de candidatos, `USE_EXISTING` y `CREATE_DISTINCT` con motivo; email no nulo único case-insensitive. B1/B7. |
| BH-064 · Idempotencia, dos operadores y auditoría real | **Comprobado** | Fingerprint/digest, locks PostgreSQL, unicidad y transacción de Usuario/Cliente/rol/auditoría; `WalkInClientServiceTests`, `WalkInConcurrencyTests`. |
| BH-064 · Búsqueda y permisos | **Parcial** | [Vista de alta y selector](../../bohemiacore/usuarios/walkin_views.py#L38): máscaras, filtros activos, paginación y permisos; rate limit ausente (AI-04). GET de alta por UUID propio recupera identidad ya creada. |
| BH-064 · Reclamo disponible y login/registro/reset históricos | **Parcial** | [Claim por email](../../bohemiacore/usuarios/web_access_claim_services.py#L67): expiración de 60 min, token digerido, vínculo email vigente, consumo único y sesión compatible. B1/B7 verifica con correo en memoria; fallo SMTP diferencial (AI-05). Sin correo no hay canal verificable. |
| BH-064 · Continuidad tras fallo de Turno | **Comprobado por tramos** | Alta en transacción previa independiente; `NuevoCliente` deja referencias por actor y `NuevoTurno` recupera por UUID/Cliente. Pruebas API + React separadas; no E2E navegador↔servidor. |
| BH-063 · Solicitud, servicios 1/N, medio y riesgo versionado | **Comprobado en la ruta canónica** | [Servicio asistido](../../bohemiacore/gestion/assisted_technical_booking_services.py#L263) y [BH-057](../../bohemiacore/gestion/technical_booking_request_services.py#L190). B2: APTO, ADVERTENCIA, REQUIERE_REVISION y NO_APTO; los cuatro casos de contrato usan resultados controlados, y el evaluador real tiene suites propias para diagnóstico confiable, parcial, ausente y policy inválida. B7 verifica retry/carrera. |
| BH-063 · Consentimiento asistido, rechazo/no obtenido y evaluación vigente | **Parcial** | [Servicio](../../bohemiacore/gestion/assisted_technical_booking_services.py#L410): evidencia, actor real, mensajes, unicidad y conflictos; no fija la evaluación leída por el operador en el comando. El propietario puede usar la aceptación web sobre una solicitud asistida (AI-01/AI-02). |
| BH-063 · Autoridad de revisión y datos públicos | **Comprobado, con límite de UI** | [Permisos técnicos](../../bohemiacore/gestion/permissions.py#L155) y [cola/revisión](../../bohemiacore/gestion/views.py#L8082) separados; el grant de recepción no los concede. DTO público y pruebas sin notas/fórmulas ni snapshots. R-03 sigue limitado a las causas y tipos públicos que React reconoce. |
| BH-063 · Jornada, bloqueos, skills AND, duración, equipo, solapamiento de Cliente/Personal y hold | **Comprobado en la ruta canónica** | [Hold asistido](../../bohemiacore/gestion/assisted_slot_hold_services.py), [servicio compartido](../../bohemiacore/gestion/slot_hold_services.py), B3/B7. Lectura DB, próximo estrictamente futuro en fecha evaluada, expiración efectiva, `OPERATOR_CANCELLED`, conflicto y carreras de Personal/equipo. Hold no se presenta como Turno. Excepción de separación de canales en AI-02. |
| BH-063 · PaymentPolicy y autoridades financieras | **Comprobado para preparación por terceros** | [Adapter asistido](../../bohemiacore/gestion/assisted_payment_services.py#L51): `create_turno_for_client` **y** `register_payment` para opciones, POST Intent y GET financiero asistido; vínculo actor/solicitud/hold, revalidación bajo lock. Alta de Pago y conciliación son comandos distintos; `confirm_deposit` no se obtiene por la combinación. Checkout/Caja conservan su contrato operativo; API web conserva ownership, con la salvedad de canal AI-02. |
| BH-063 · Efectivo, evidencia, umbral, tardíos y un Turno | **Comprobado en el flujo transaccional** | [Confirmación](../../bohemiacore/gestion/payment_confirmation_services.py), [consumo](../../bohemiacore/gestion/slot_hold_consumption_services.py#L417), B5/B7: pago insuficiente no confirma; transferencia espera conciliación; aprobado, hold consumido y Turno confirmado en la misma cadena; orden de servicios, actor/Cliente, casos BH-058 y replay. Sin Pago ficticio en la ruta auditada ni D-08. |
| BH-063 · Iniciar atención, finalizar y trabajo profesional | **Comprobado** | [Llegada](../../bohemiacore/gestion/turno_arrival_services.py#L32): `CONFIRMADO → EN_PROCESO`, permiso semántico global de recepción y auditoría; no es permiso profesional. [Finalización](../../bohemiacore/gestion/turno_finalization_services.py#L115): ambos estados fuente, ownership y perfil activo, fichas según política, idempotencia y rollback. B3/B7 verifica efectos únicos y acceso asignado; no se observó regresión de finalización. |
| BH-063 · Recuperación y pantallas | **Parcial** | [Proyección derivada](../../bohemiacore/gestion/assisted_reception.py), [recepción](../../frontend/src/pages/admin/NuevoTurno.js), [Caja](../../frontend/src/pages/admin/CajaPresencial.js) y [guards](../../frontend/src/routes/index.js#L111). UUID no autoriza; GET no muta ni expone clave; rutas de Turno/agenda/trabajo mantienen permisos. Ver AI-03 y límites debajo. |
| BH-063/BH-064 · Teléfono verificable, excepción de prepago, diagnósticos automáticos, autoevaluación | **Fuera de alcance / no implementados** | El teléfono funciona para identificación comercial, no para reclamar acceso. No se identificó una excepción D-08 publicada ni cambios a BH-061 v1. |
| BH-063/BH-064 · Sesión/productivo, proveedor y E2E integrado | **No verificado** | Sin navegador real contra Django, SMTP/proveedor real, inspección de datos históricos del despliegue ni QA de múltiples pestañas/dispositivos. |

## 3. Hallazgos

### AI-01 — El consentimiento no fija la evaluación comunicada

**Alta · BH-063 · D-03 y contrato D · bloquea.** El [serializer](../../bohemiacore/gestion/assisted_technical_booking_serializers.py#L71)
y [React](../../frontend/src/pages/admin/NuevoTurno.js#L705) no mandan `evaluacion_id`.
El fingerprint no lo contiene, y el [servicio](../../bohemiacore/gestion/assisted_technical_booking_services.py#L443)
toma la evaluación vigente al escribir. Su comprobación de `superseded_by` no
detecta que un intento nuevo válido reemplazó al que se mostró.

**Reproducción/alcance:** una solicitud asistida muestra advertencia A. El
Cliente propietario la reevalúa por la ruta canónica, con advertencia B (se
controló la salida del evaluador en la prueba). El operador envía el comando
desde la pantalla anterior. El caso relevante es que ambas evaluaciones
requieren ADVERTENCIA, no que el snapshot original esté corrupto.
**Resultado observado:** reevaluación HTTP 200 y consentimiento anterior HTTP
200; la evidencia persistida apunta a B y contiene los textos de B (`probes.log`).
**Impacto:** el sistema puede certificar que se comunicó B y permitir continuar
a hold/pago cuando la persona sólo vio A. **Recomendación:** enviar el ID del
intento visible, incluirlo en fingerprint, revalidarlo bajo lock y devolver 409
con recarga pública y nueva decisión si difiere; preservar el retry del
consentimiento ya confirmado.

### AI-02 — La frontera web/asistida se limita al propietario, no al medio

**Alta · BH-063 · D-03/D-04, contratos D–F · bloquea.** El
[queryset web](../../bohemiacore/gestion/views.py#L7926) filtra Cliente, pero no
medio, y [`accept_technical_warning`](../../bohemiacore/gestion/technical_booking_request_services.py#L235)
registra aceptación web y cambia `estado` sin validar canal ni decisión asistida.
El [wrapper de hold web](../../bohemiacore/gestion/slot_hold_services.py#L445)
exige propietario, no canal. El [consumo](../../bohemiacore/gestion/slot_hold_consumption_services.py#L417)
usa el medio de la solicitud para decidir `Turno.canal_origen`, no el tipo de
hold que la originó.

**Reproducción/alcance:** con Cliente propietario habilitado y una solicitud de
recepción en `ADVERTENCIA_PENDIENTE`, aceptar desde la ruta web. La transición
devolvió HTTP 200 y dejó `APROBADA_TECNICAMENTE`, con
`AceptacionAdvertenciaTecnica` y sin `ConsentimientoAdvertenciaAsistido`
(`probes.log`).
El código del adapter asistido exige el segundo tipo de evidencia, así que la
solicitud aparece aprobada pero puede quedar bloqueada en recepción. La rama
web opera con invariantes distintos; no se demostró confirmación sin dinero ni
acceso de un Cliente ajeno. **Impacto:** se altera la aprobación asistida con
evidencia de otro canal y se pierde la frontera de orquestación y trazabilidad.
**Recomendación:** separar por canal las mutaciones de consentimiento,
reevaluación y capacidad, o formalizar una transferencia de canal con reglas
explícitas y auditadas. Agregar regresión cruzada de aceptación/hold/Intent.

### AI-03 — Un 404 definitivo puede inmovilizar la recepción de la pestaña

**Media · BH-063 · contrato G y continuidad de alta · bloquea.**
[`commandFailed`](../../frontend/src/pages/admin/NuevoTurno.js#L563) retiene
`pending` ante cualquier 404. La [recuperación](../../frontend/src/pages/admin/NuevoTurno.js#L523)
interpreta un 404 de raíz con CREATE pendiente como un posible comando no
observado; sólo ofrece repetir. Sin resultado no se muestra el formulario; con
pendiente tampoco se puede iniciar otro recorrido.

**Reproducción/alcance (traza estática):** un operador con permiso de recepción
prepara una solicitud enlazada a un alta. El servidor devuelve
`WALKIN_OPERATION_NOT_FOUND` (referencia fuera de scope/incompatible) antes de
crear la raíz. Reconsultar esa raíz devuelve 404 y repetir el mismo payload no
puede corregir el vínculo. En la misma pestaña, recargar no desbloquea la
selección; el alta persistida no se pierde. También se puede atascar una lectura
de referencia a Cliente que ya no está activo y que no tiene comando pendiente.
**Impacto:** no satisface recuperación funcional ante 404/alcance cambiado.
**Recomendación:** separar un 404 autoritativo de comando de un resultado
incierto; ofrecer volver a selección o archivar el recorrido sin reemitir la
mutación, conservando identidad mientras no haya una resolución segura.

### AI-04 — Falta rate limit del alta y del selector

**Media · BH-064 (selector compartido con BH-063) · contratos A/B · bloquea.**
[Las vistas](../../bohemiacore/usuarios/walkin_views.py#L38) tienen autenticación,
grants, paginación, máscara y límites de tamaño, pero no clases de throttle ni
control equivalente; la [configuración](../../bohemiacore/bohemiacore/settings.py#L130)
no define throttling DRF global. También falta en el reclamo anónimo. No se
verificó un proxy que compense el control ausente en el código auditado.

**Reproducción/alcance:** revisar la configuración efectiva de las tres vistas,
no enviar carga al despliegue. **Impacto:** la página acota una respuesta, no
la frecuencia de consultas de identidad ni el envío/revocación de tokens del
reclamo. **Recomendación:** límites por actor y, para claim, por origen y contacto
normalizado, con respuesta uniforme y tests de umbral; si existe protección
equivalente de infraestructura, demostrarla antes de cerrar el criterio.

### AI-05 — Un fallo de transporte de correo rompe la respuesta genérica

**Media · BH-064 · D-01 y no enumeración del reclamo · bloquea.** La
[vista](../../bohemiacore/usuarios/walkin_views.py#L211) responde genérico después
de llamar al servicio; [el envío síncrono](../../bohemiacore/usuarios/web_access_claim_services.py#L117)
es `fail_silently=False` y sólo ocurre para una cuenta elegible.

**Reproducción/alcance:** con dos emails sintéticos (elegible/desconocido),
simular `SMTPException` en el transporte y comparar respuestas. No requiere ni
se contactó SMTP real. **Resultado observado:** HTTP 500 para el email elegible
y HTTP 200 para el desconocido; no quedó token para la cuenta elegible
(`probes.log`). El rollback no restaura la indistinguibilidad HTTP.
**Impacto:** caída del reclamo y
distinción entre elegible y desconocido durante la falla. **Recomendación:**
desacoplar entrega/respuesta pública, observar y reintentar la entrega en
servidor sin devolver existencia ni error diferencial; probar caída del proveedor.

### AI-06 — La creación legacy no equivale al recorrido asistido

**Baja · BH-063 · D-02/D-04 y superficie legacy · no bloquea por sí sola.**
[`crear-para-cliente`](../../bohemiacore/gestion/views.py#L2107) sigue montada con
`create_turno_for_client`. [Crea sólo `SOLICITADO`](../../bohemiacore/gestion/turno_creation_services.py#L731),
no `CONFIRMADO` ni `EN_PROCESO`, sin solicitud BH-057/ledger; el alias de
registro de pago legacy devuelve 409. **Reproducción/alcance:** contrato de
`test_turno_creation_api` con Cliente/slot válidos; no es la ruta React actual.
**Impacto:** un consumidor legacy puede crear una fila y ocupar capacidad fuera
de la cadena moderna; no prueba una confirmación gratis. **Recomendación:**
inventariar consumidores y acordar deprecación o publicar la distinción entre
solicitud legacy y reserva BH-063 antes de presentar una frontera única.

## 4. Integridad, permisos y límites de recuperación

- `gestion.0045` depende de `gestion.0044` y `usuarios.0004`: agrega medio y
  registrante, consentimiento, ledger y controles de unicidad. `0046` enlaza
  hold, ajusta el constraint por comando y añade cancelación del operador;
  `0047` agrega el vínculo Intent y forma válida para INTENT; `0048` añade FK
  nullable al ledger BH-064 sin backfill. Se inspeccionó SQL y el grafo se ejecutó
  en PostgreSQL limpio. `usuarios.0003` bloquea emails históricos vacíos/colisiones;
  no se verificó que la base de un despliegue real supere el preflight.
- Concurrencia: se verifican advisory locks y barreras/hilos/`TransactionTestCase`
  de alta por misma clave y por misma identidad, consumo único de claim,
  solicitud por dos actores, capacidad y último equipo, preparación de Intent,
  registro/conciliación/consumo BH-058 y finalización. No confundir estos casos con
  demostrar linealizabilidad de todo interleaving; no se ensayó reemisión de claim
  simultánea a la confirmación ni la carrera DOM entre dos pestañas.
- Recuperación: hay tests de reload con resultado y sin commit visible, 404 de
  raíz, actor distinto, revocación, timeout, doble clic y pago recuperado sin
  segundo POST en Caja. El bloque B5 comprueba estado actual del Turno y expiración sin
  mutación. La UI conserva borrador por actor/pestaña; re-adjunta el comprobante
  original si el Pago no se reconoce. El endpoint de registro manual BH-058
  verifica el contexto del registro. No es una cola multioperador: perder almacenamiento de pestaña
  requiere consulta antes de otro cobro. No se verificó en browser la
  reautenticación real conservando el borrador, ni el handshake completo con una
  transferencia re-adjuntada. Los GET autorizados no prueban por sí solos un flujo
  recuperable para todos los errores (AI-03).
- La separación amplia de Caja (`register_payment` o `confirm_deposit` o
  `view_financial_reports` para lectura) es la publicada, no ownership asistido.
  `register_payment` no autoriza conciliación manual; efectivo se concilia según
  el contrato B2 de BH-058 por su propia semántica. No se cambió el contrato de roles BH-061 v1. No se
  recabaron comprobantes, claves o datos reales.

## 5. Ejecución, logs y reproducción

Las etiquetas se extrajeron de [`.github/workflows/bh060-permisos.yml`](../../.github/workflows/bh060-permisos.yml)
al HEAD auditado. Se enumeraron los IDs con `StablePostgresTestRunner.build_suite`:
**1.281 IDs backend distintos, sin duplicados entre bloques**. Los conteos
nominales de workflow B2/B5 preceden los dos tests de recuperación añadidos a
cada uno; no se tomaron como gate ni se repitieron esas focales. Las suites
BH-063/BH-064 (`test_walkin_client_bh064`, `test_assisted_technical_booking`,
`test_assisted_slot_holds`, `test_assisted_payments` y finalización) están
repartidas íntegramente entre B1/B2/B3/B5/B7. Los probes independientes se cuentan
aparte, no como miembros de la matriz.

| Bloque PostgreSQL | Pruebas aprobadas / ejecutadas | Salida | Log |
|---|---:|---:|---|
| B1 · roles, usuarios y Personal | 443/443 | 0 | `B1.log` |
| B2 · diagnóstico, riesgo y registro técnico | 235/235 | 0 | `B2.log` |
| B3 · agenda, holds y Turnos | 224/224 | 0 | `B3.log` |
| B4 · catálogo, equipamiento e inventario | 79/79 | 0 | `B4.log` |
| B5 · pagos, proveedor y conciliación | 179/179 | 0 | `B5.log` |
| B6 · administración, auditoría y reportes | 43/43 | 0 | `B6.log` |
| B7 · concurrencia PostgreSQL | 78/78 | 0 | `B7.log` |
| **Total backend único** | **1.281/1.281** | **0** | `matrix-results.json`, `matrix-summary.txt` |

No hubo skips ni se omitieron bloques, focales requeridas o carreras incluidas
en la matriz. No se ejecutó discovery backend general fuera de estas etiquetas;
las focales ya cubiertas no se repitieron. En todos los bloques se observó
`staticfiles.W004` por el directorio `static` no versionado, ausente en el
snapshot. **Total de pruebas únicas del repositorio: 1.766 aprobadas** (1.281
Django + 485 Jest). Además se ejecutaron **3 probes independientes**. El éxito
de las suites no invalida los defectos de contrato de la sección 3.

| Validación complementaria | Resultado | Salida |
|---|---|---:|
| Jest completo (`jest.log`) | 485/485 tests, 49/49 suites; avisos de React sobre actualizaciones no envueltas en `act(...)`, sin fallos | 0 |
| Probes PostgreSQL (`probes.log`) | 3/3; reproducen AI-01, AI-02 y AI-05, no certifican cumplimiento | 0 |
| Build estándar (`build-standard.log`) | Compiló con 18 avisos ESLint en 10 archivos | 0 |
| Build `CI=true` (`build-ci.log`) | Falló porque el build convierte esos mismos 18 avisos en errores | 1 |
| Django `check` / drift (`check.log`, `drift.log`) | Sin errores ni drift; `staticfiles.W004` por directorio `static` ausente en el snapshot de `git archive` | 0 / 0 |
| `sqlmigrate gestion 0045–0048` (`sql-*.log`) | SQL generado e inspeccionado para las cuatro migraciones | 0 cada una |
| Revisión de secretos (`secret-review.txt`) | Cero coincidencias en el delta para los patrones inspeccionados; sin scanner dedicado | — |
| Enlaces y diff | 46 enlaces relativos de seis documentos válidos; diff publicado y de trabajo sin errores de espacios; inventario con sólo el informe nuevo, sin stage | 0 |

Los diagnósticos ESLint son idénticos en ambos logs y ninguno de sus 10
archivos ni la configuración/dependencias de lint cambió en
`07e5810..3209dbd`; también consta el fallo previo en la documentación
consolidada. Se clasifican como deuda preexistente, no como regresión del
bloque. `DEP0176` de Node y el aviso de datos desactualizados de Browserslist
son avisos del toolchain; no fueron la causa del fallo estricto.

Comandos equivalentes (cada bloque usa BD nueva con nombre `test_...` y proceso
independiente; nunca `--keepdb` ni `--parallel`):

```text
python -X utf8 manage.py test <etiquetas del bloque> --settings=bohemiacore.test_settings --verbosity 1 --buffer --noinput
python -X utf8 manage.py check --settings=bohemiacore.test_settings
python -X utf8 manage.py makemigrations --check --dry-run --settings=bohemiacore.test_settings
python -X utf8 manage.py sqlmigrate gestion <0045|0046|0047|0048> --settings=bohemiacore.test_settings
CI=true npm test -- --watchAll=false --runInBand
CI=false npm run build
CI=true npm run build
git diff --check 07e5810..3209dbd
```

En la ejecución local sólo se sobreescribió la conexión en memoria para apuntar
al clúster efímero de auditoría (`127.0.0.1:55439`); se conserva el runner y el
resto de `bohemiacore.test_settings`. Los logs y scripts de ejecución están en
`%LOCALAPPDATA%/Temp/opencode/bh063-064-audit-3209dbd/`, incluidos
`audit_runner.py`, `audit_observations.py` y `logs/matrix-labels.json`. Si se
replican fuera de ese clúster, no usar credenciales ni la base de desarrollo.

## 6. Recomendación de cierre

No declarar cierre oficial. Corregir primero los bloqueantes en una fase
separada; preservar las garantías transaccionales ya demostradas y añadir
regresiones para las fronteras de canal, consentimiento y errores definitivos,
además de claim ante fallo de transporte y límites efectivos. Repetir una
verificación independiente del delta y completar E2E controlado de Cliente
existente y alta rápida, incluida reanudación con sesión y continuidad de Caja.
Mantener el cierre documental y el backlog sin cambios hasta ese veredicto.

`BH-063/BH-064 = BLOQUEADOS`
