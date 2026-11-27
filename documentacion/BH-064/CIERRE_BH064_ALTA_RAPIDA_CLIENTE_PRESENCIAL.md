# Cierre técnico BH-064 — Alta rápida de Cliente presencial

**Veredicto: BH-064 = CERRADO TÉCNICAMENTE.** Baseline funcional reauditado: `6556209e4eea78055962928cbd4e11ec9ff62383`, en `save/work-in-progress`. El cierre no habilita el reclamo en producción ni certifica su infraestructura de entrega.

## Alcance y garantías

- **Identidad presencial.** El alta requiere usuario activo con `usuarios.create_walkin_client`, nombre, apellido, motivo y al menos un contacto válido: email o teléfono argentino. Crea `Usuario` y `Cliente` activos con rol `CLIENTE`, contraseña inutilizable y estado web `PENDING_CLAIM`. El email puede ser nulo en ese estado; no se inventan emails ni se cambia `USERNAME_FIELD=email`. La identidad comercial se puede usar sin acceso web. El alta no genera token, no hace envío y no crea diagnóstico ni perfil capilar ficticio.
- **Búsqueda y coincidencias.** El selector autorizado es paginado y devuelve identidad mínima y contactos enmascarados, sin fichas, diagnósticos ni historial. El email no nulo conserva unicidad insensible a mayúsculas. El teléfono argentino se normaliza a E.164 sin exigir unicidad: un teléfono compartido es una coincidencia, no identidad probada. Se exige revisión humana para reutilizar un Cliente (`USE_EXISTING`) o justificar uno distinto (`CREATE_DISTINCT`); nunca se fusionan identidades automáticamente ni se duplica un email ya ocupado.
- **Idempotencia, concurrencia y auditoría.** `WalkInClientOperation` enlaza actor, comando normalizado y Cliente con UUID, digest de clave y huella. Los locks de PostgreSQL sobre comando y contactos serializan la creación y revalidan candidatos; con la misma intención se recupera el mismo resultado, y una clave con otro payload da conflicto. La identidad, rol, registro de operación y auditoría causal se confirman o revierten juntos. El evento registra motivo y resolución sin contraseña, token ni contacto completo. Cuotas PostgreSQL compartidas por actor para alta y selector se aplican antes de las búsquedas; para reclamo público se aplican por origen y, al solicitar, también por contacto sin cambiar la respuesta pública al agotarse esa cuota.
- **Entrega a recepción.** `NuevoCliente` transfiere sólo referencias autorizadas a `NuevoTurno`. El `cliente_id` es estable y el originador autorizado puede releer su alta. [BH-063](../BH-063/CIERRE_BH063_TURNOS_ASISTIDOS_PRESENCIALES.md) vincula el alta sólo si actor, Cliente y permiso coinciden. Un fallo posterior en la solicitud/Turno no revierte el alta comercial.

La implementación corresponde al [Incremento 1](../generales/IMPLEMENTACION_BH064_1_IDENTIDAD_PRESENCIAL.md) (`c62421f`), con continuidad de recepción en el Incremento 5 (`3209dbd`) y correcciones AI-04–AI-05 en `6556209`. Rigen [D-01, D-07 y contratos A/B/G](../generales/DECISIONES_Y_CONTRATOS_BH063_BH064.md), con el detalle final en el [consolidado](../generales/IMPLEMENTACION_BH063_BH064_CONSOLIDADA.md). D-08 (confirmación sin prepago) está fuera del alcance del bloque y no se implementó.

## Reclamo de acceso: comprobado en código, no en despliegue

El reclamo verificable implementado usa **sólo email**. Sin email el Cliente sigue activo comercialmente y pendiente de reclamo; no hay canal SMS/WhatsApp verificado. Cuando la cuota de origen admite la solicitud, un email válido elegible o desconocido recibe el mismo `200` genérico. El envío no ocurre en el request HTTP: la cola persiste referencia y digest, no email claro ni token. El procesador revalida contacto, elegibilidad y vigencia del trabajo (15 min). El token se persiste como digest, vence 60 min después de emitirse y sólo al consumirse válidamente habilita el acceso `CLAIMED`.

Un fallo de transporte conocido revierte la emisión y conserva el token anterior si seguía vigente, elimina el trabajo y registra un evento sin credenciales ni datos de contacto; no hay reintento automático de ese fallo. Una interrupción previa al commit puede dejar el trabajo disponible para reanudación dentro del TTL. El envío y el commit no son atómicos: no se garantiza entrega exactamente una vez. El acuse público y la métrica de trabajos procesados no acreditan entrega. Latencia constante y resistencia bajo abuso distribuido no fueron verificadas.

**Worker/scheduler desplegado, SMTP real, proxy y logs del entorno: NO VERIFICADOS.** Antes de habilitar tráfico operativo:

1. Aplicar la cadena de migraciones pendiente respetando dependencias, incluidas `usuarios.0005` (cuotas) y `usuarios.0006` (cola). Verificar preflight histórico de `usuarios.0003` si corresponde; no inferir compatibilidad de los datos de destino por el éxito en pruebas aisladas. HTTP y worker deben compartir primaria PostgreSQL y la misma `SECRET_KEY`; coordinar rotaciones.
2. Programar y supervisar `process_web_access_claims --limit 50`, dimensionando frecuencia y lote para procesar antes de 15 min. Programar `prune_walkin_rate_buckets` y alertar por antigüedad/tamaño de cola, última ejecución y `web_access_claim_delivery_failed`.
3. Verificar que el proxy transmita un origen confiable a `REMOTE_ADDR` y no confíe en `X-Forwarded-For` aportado por el cliente. Confirmar cómo se aplican cuotas anónimas por origen sin agrupar indebidamente todo el tráfico del proxy.
4. En preproducción, hacer una entrega real a un contacto controlado y comprobar el consumo único. Verificar remitente, URL HTTPS, expiración, reintentos y fallos, incluida la invariancia de la respuesta pública. Revisar que logs, trazas y proxy no registren tokens, enlaces de reclamo, cuerpos ni contactos claros.

El cierre documental no aplica migraciones, no configura ni inicia el worker y no realiza envíos.

## Evidencia y estados

- [Auditoría original](../generales/AUDITORIA_INDEPENDIENTE_BH063_BH064.md), `3209dbd0ea5d6dae26245c2967a43a2bc79dd1fb`: **BLOQUEADO** por AI-04 y AI-05. [Reauditoría diferencial](../generales/REAUDITORIA_BH063_BH064_POST_AI01_AI05.md), `6556209e4eea78055962928cbd4e11ec9ff62383`: cuotas corregidas; reclamo corregido en código y probado con correo en memoria; **listo para cierre técnico**. Ambos informes conservan sus veredictos.
- Regresión independiente común: **1.292/1.292** en PostgreSQL B1–B7 y **488/488** en Jest (49 suites), más tres probes de worker, contabilizados aparte: ciclo HTTP/entrega en memoria/consumo único, rollback y reanudación ante interrupción, y otra conexión que salta el job bloqueado y permite drenar la cola. Django `check`, drift y SQL de migraciones aprobados en auditoría. Este cierre no repitió las suites.
- E2E en Edge aislado: alta única comprobada en BD, selección/handoff y regreso a selección tras 404 en la misma pestaña; el recorrido siguió hasta el hold. Los escenarios funcionales y la BD se observaron favorables; el proceso agotó el timeout **al salir**, sin exit 0 verificado. No hubo envío de correo real ni cobros.

| Estado | Condición |
|---|---|
| Cierre técnico | Aprobado para el alcance reauditado. |
| Preparación para despliegue | Pendiente de las comprobaciones operativas anteriores y del entorno. |
| Pruebas manuales integrales | Pendientes: altas con ambos tipos de contacto, coincidencias y teléfonos compartidos, flujo de recepción y reclamo con canal operativo controlado. |
| Build React | Estándar aprobado. `CI=true` falla por avisos ESLint preexistentes (18 en 10 archivos) y un aviso Webpack también preexistente; si es gate, sigue impidiendo desplegar. CI remoto **NO VERIFICADO**. |

El propietario debe actualizar manualmente BH-064 en el backlog oficial externo. Este cierre no modifica ni sustituye `BACKLOH.xlsx`.
