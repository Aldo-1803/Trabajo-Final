# BH-061 Incremento 4 — Cardinalidad de eventos y concurrencia

**Fecha:** 2026-11-10

**Baseline de inicio:**
`52a10dee667f3919bc922812f4e04e7384885259`

## 1. Alcance

Este incremento completa la evidencia automatizada de integridad y
cardinalidad de los eventos semánticos BH-061 bajo concurrencia PostgreSQL.

El cambio es exclusivamente de pruebas y documentación. No se modificaron
servicios, modelos, permisos, migraciones, APIs ni frontend porque las carreras
no demostraron un defecto productivo.

Las aserciones cuentan eventos mediante la combinación de `tabla` y
`valor_nuevo.event`. Las entradas CRUD producidas por señales genéricas no se
consideran cambios efectivos de BusinessRole, estado de cuenta o habilidad.

## 2. Infraestructura concurrente

Las carreras usan:

- PostgreSQL real mediante `bohemiacore.test_settings`;
- `TransactionTestCase` y `StablePostgresTestRunner`;
- dos conexiones independientes administradas con `close_old_connections()`;
- `ThreadPoolExecutor(max_workers=2)`;
- `threading.Barrier(2)` antes de invocar los comandos;
- ejecución aislada, sin `--parallel`.

No se usan sleeps, retries ni captura genérica de excepciones. Los workers sólo
clasifican el rechazo de dominio esperado del último administrador. Cualquier
deadlock, error de base de datos, timeout o excepción distinta se propaga desde
el `Future` y hace fallar la prueba.

## 3. Escenarios concurrentes y cardinalidad

| Carrera | Resultados confirmados | Estado final | Eventos semánticos exactos |
|---|---|---|---|
| Degradación contra degradación de dos administradores | 1 cambio + 1 `LastActiveAdministratorRoleChange` | Un ADMINISTRADOR activo y un CLIENTE activo | 1 `BUSINESS_ROLE_CHANGED` |
| Degradación contra desactivación | 1 cambio + 1 rechazo de último administrador | Exactamente un ADMINISTRADOR de negocio activo | 1 evento: `BUSINESS_ROLE_CHANGED` **o** `ACCOUNT_DEACTIVATED`, según el orden válido |
| Dos cambios EMPLEADO → PROFESIONAL sobre el mismo Usuario | 1 cambio + 1 no-op | PROFESIONAL | 1 `BUSINESS_ROLE_CHANGED` |
| Dos desactivaciones sobre la misma cuenta CLIENTE | 1 cambio + 1 no-op | Cuenta inactiva | 1 `ACCOUNT_DEACTIVATED` |
| Dos asignaciones de la misma habilidad al mismo Personal | 1 cambio + 1 no-op | Una única asignación activa | 1 `PERSONAL_SKILL_ASSIGNED` |

Las pruebas no fijan qué worker debe ganar. El motivo persistido debe coincidir
con el comando que reportó `changed`; el no-op devuelve `audit_id=None` o
`event=None` según su contrato.

Para cada evento se comprueban actor, objetivo, fuente, motivo, estado anterior
y posterior. Los cambios de rol verifican también:

- `role_contract_version`;
- `previous_role_permissions_fingerprint`;
- `new_role_permissions_fingerprint`.

La habilidad comprueba `source`, `reason`, Personal, habilidad y Usuario
vinculado. Los eventos simples no reciben `operation_id`.

## 4. Último administrador

Las carreras existentes se ampliaron para demostrar conjuntamente que:

1. queda al menos un administrador de negocio activo y coherente;
2. existe exactamente una operación efectiva confirmada;
3. existe exactamente un evento semántico asociado al resultado efectivo;
4. el objetivo rechazado conserva rol, actividad y cero eventos de éxito;
5. el ID retornado por el cambio coincide con el único evento persistido;
6. no hay eventos parciales de la operación rechazada.

En degradación contra desactivación ambos órdenes son válidos. La aserción
deriva el evento esperado del resultado real, sin elegir artificialmente un
ganador.

## 5. Operaciones compuestas BH-061.2

Se reforzaron cuatro contratos representativos:

| Operación | Padre | Hijos esperados en el caso completo | Cardinalidad |
|---|---|---|---:|
| Cambio laboral | `PERSONAL_BUSINESS_ROLE_CHANGED` | `BUSINESS_ROLE_CHANGED` | 2 |
| Creación de acceso Personal | `PERSONAL_ACCESS_CREATED` | `PERSONAL_USER_LINKED`, `BUSINESS_ROLE_CHANGED` | 3 |
| Revocación conservando Cliente | `WORK_ACCESS_REVOKED_KEEP_CLIENT` | `PERSONAL_DEACTIVATED`, `BUSINESS_ROLE_CHANGED` | 3 |
| Revocación desactivando cuenta | `WORK_ACCESS_REVOKED_ACCOUNT_DISABLED` | `PERSONAL_DEACTIVATED`, `ACCOUNT_DEACTIVATED` | 3 |

Para cada caso completo se consulta el conjunto total por `operation_id` y se
afirma igualdad exacta entre sus IDs y los IDs padre/hijos retornados. El padre
referencia los hijos existentes y todos comparten un UUIDv4 común.

Las variantes ya parcialmente finalizadas siguen produciendo sólo los hijos
efectivamente necesarios. La invocación repetida en estado final es no-op o
rechazo coherente y no agrega eventos. Si falla la escritura del evento padre,
la transacción revierte estado, padre e hijos; las consultas por tabla y evento
demuestran que no quedan auditorías huérfanas.

Los eventos hijos no se cuentan como cambios independientes adicionales: son
componentes de la cardinalidad de una única operación compuesta.

## 6. Rechazos, rollback y confidencialidad

La evidencia focal cubre explícitamente:

- último administrador;
- capacidades administrativas residuales individuales o por grupo;
- actor sin permisos efectivos;
- motivo nulo, vacío, corto o excesivo;
- fallo forzado de `Auditoria.objects.create` o del escritor padre.

En todos esos casos se comprueban cero eventos semánticos de éxito para el
objetivo, cero mutaciones persistidas y conservación del estado anterior.

Los payloads producidos se revisan contra claves y valores sensibles. No
contienen contraseñas, hashes de contraseña, JWT, JTI, access tokens, refresh
tokens ni secretos de los fixtures. `refresh_tokens_revoked` es únicamente un
contador operativo, no un token.

No se modificaron eventos históricos.

## 7. Resultados y estabilidad

Ejecuciones finales sobre PostgreSQL, sin paralelismo:

- bloque focal de concurrencia, cardinalidad, compuestos y rechazos:
  **115/115**, 268,608 s;
- regresión de BH-059, BH-061.1–3, auditoría, acceso laboral y permisos BH-060
  relevantes: **221/221**, 359,740 s;
- total de pruebas únicas focales y de regresión: **336/336**.

El bloque de cinco carreras críticas se repitió tres veces de forma controlada:

- repetición 1: **5/5**, 49,277 s;
- repetición 2: **5/5**, 53,640 s;
- repetición 3: **5/5**, 49,208 s;
- estabilidad acumulada: **15/15** ejecuciones concurrentes adicionales.

No se observaron deadlocks, errores de infraestructura ni violaciones de
invariantes.

Durante el desarrollo, crear una `Habilidad` nueva con
`reset_sequences=True` produjo una colisión de PK porque el runner restaura las
habilidades canónicas después del `flush`. Se clasificó como configuración del
fixture, no como error concurrente ni defecto del servicio. La prueba reutiliza
el seed activo `DIAGNOSTICO`, igual que el entorno estable documentado; no se
añadieron retries ni se cambió producción.

## 8. Riesgos residuales

- La evidencia cubre carreras representativas, no todas las combinaciones
  posibles entre comandos administrativos.
- `operation_id` continúa almacenado en JSON sin índice dedicado.
- La auditoría no incorpora todavía protección forense append-only a nivel de
  base de datos.
- Exportación, retención y filtros avanzados permanecen fuera de alcance.

No se implementó BH-062, no se modificaron permisos y BH-061 no se declara
cerrado todavía.

`BH-061 INCREMENTO 4 — IMPLEMENTADO Y VALIDADO`
