# BH-061 Incremento 2 — Correlación uniforme de eventos compuestos

**Fecha:** 2026-11-08

**Baseline de inicio:**
`c21f3ea8f9fa85d7f8ad0ca11eb9e74b0723139a`

## 1. Alcance

Este incremento correlaciona los eventos semánticos emitidos por una misma
operación administrativa compuesta de acceso. No agrega modelos, columnas,
migraciones, interfaces, estado global ni auditorías de otros dominios.

Las composiciones alcanzadas son:

| Operación | Orquestador | Eventos correlacionados |
|---|---|---|
| Cambio laboral de BusinessRole | `change_personal_business_role()` | `BUSINESS_ROLE_CHANGED` y `PERSONAL_BUSINESS_ROLE_CHANGED` |
| Creación de acceso para Personal | `create_access_for_personal()` | `PERSONAL_USER_LINKED`, `BUSINESS_ROLE_CHANGED` y `PERSONAL_ACCESS_CREATED` |
| Revocación conservando Cliente | `revoke_work_access_keep_client()` | `PERSONAL_DEACTIVATED` y/o `BUSINESS_ROLE_CHANGED`, más `WORK_ACCESS_REVOKED_KEEP_CLIENT` |
| Revocación desactivando la cuenta | `revoke_work_access_and_disable_account()` | `ACCOUNT_DEACTIVATED` y/o `PERSONAL_DEACTIVATED`, más `WORK_ACCESS_REVOKED_ACCOUNT_DISABLED` |

No se incorporaron altas de Cliente o Administrador ni registro público porque
actualmente producen un único evento semántico de acceso y no constituyen una
composición padre/hijos. Tampoco se amplió el alcance a pagos, inventario,
habilidades o eventos genéricos de modelos.

## 2. Contrato de `operation_id`

Cada ejecución efectiva de uno de los cuatro orquestadores crea una sola vez
un UUID versión 4 mediante `uuid4().hex`. El valor persistido:

- es una cadena opaca de 32 caracteres hexadecimales en minúscula;
- se genera aleatoriamente, sin derivarse de email, nombre, contraseña, token,
  IDs de negocio ni otros datos personales;
- es independiente de la clave primaria de cada fila de `Auditoria`;
- se reutiliza exactamente en todos los eventos semánticos de la composición;
- es distinto para operaciones administrativas independientes.

El campo se guarda en `valor_nuevo['operation_id']`. No se agregó una columna a
`gestion.Auditoria` porque su JSON permite correlacionar desde cualquiera de
los componentes sin alterar el esquema.

Los no-op y rechazos no escriben eventos y, por lo tanto, no dejan un
`operation_id` persistido. Un identificador generado durante una ejecución que
termina en error tampoco sobrevive al rollback.

## 3. Propagación transaccional

El orquestador genera el valor y lo pasa mediante un parámetro interno,
explícito y sólo por palabra clave a los servicios subordinados existentes:

- `assign_validated_business_role(..., operation_id=...)`;
- `deactivate_account(..., operation_id=...)`;
- `deactivate_personal(..., operation_id=...)`;
- `link_user_to_personal(..., operation_id=...)`.

Los servicios hijos no crean identificadores. Cuando se invocan de forma
independiente y no reciben uno, mantienen su comportamiento histórico y no
agregan el campo al evento simple.

Cada orquestador conserva su `transaction.atomic`. Si falla el evento padre o
cualquier componente, se revierten la mutación y todos los eventos hijos; no
quedan eventos huérfanos. Las validaciones y detecciones de no-op continúan
ocurriendo antes de escribir el evento de éxito.

## 4. Relación padre/hijos

Ejemplo conceptual de una creación de acceso, sin información sensible:

```json
{
  "operation_id": "7c8a4e8da1f54167a79a147a7de72920",
  "parent": {
    "event": "PERSONAL_ACCESS_CREATED",
    "audit_id": 903,
    "link_audit_id": 901,
    "role_audit_id": 902
  },
  "children": [
    {"audit_id": 901, "event": "PERSONAL_USER_LINKED"},
    {"audit_id": 902, "event": "BUSINESS_ROLE_CHANGED"}
  ]
}
```

Cada una de las tres filas guarda el mismo `operation_id` en `valor_nuevo`.
Los IDs del ejemplo son ilustrativos y no forman parte del identificador de
operación.

## 5. Compatibilidad preservada

Se conservaron sin cambios las referencias existentes:

- `link_audit_id`;
- `role_audit_id`;
- `status_audit_id`;
- `account_audit_id`;
- los IDs de evento padre retornados por cada resultado.

También permanecen actor, objetivo, fuente, motivo, estados anterior/posterior
y las garantías de preservación de perfiles. Los eventos que contienen una
mutación de BusinessRole conservan `role_contract_version`,
`previous_role_permissions_fingerprint` y
`new_role_permissions_fingerprint` de BH-061 Incremento 1.

No se reescribieron auditorías históricas. La lectura por API sigue aceptando
eventos sin `operation_id` ni metadata de contrato.

## 6. Pruebas PostgreSQL

Se ejecutaron con `bohemiacore.test_settings` y
`StablePostgresTestRunner`:

- **158/158** pruebas focales aprobadas;
- **232/232** pruebas de regresión afectada aprobadas;
- total de ejecuciones en ambas pasadas finales: **390/390**.

La cobertura verifica:

1. dos eventos correlacionados en el cambio laboral;
2. tres eventos padre/hijos en la creación de acceso;
3. dos o tres eventos en cada variante de revocación;
4. igualdad exacta y formato UUIDv4 del `operation_id`;
5. valores distintos entre operaciones independientes;
6. conservación de IDs subordinados;
7. actor, objetivo, motivo, fuente y before/after;
8. no-op sin eventos nuevos;
9. rechazo sin evento de éxito;
10. rollback completo sin eventos hijos huérfanos;
11. lectura histórica sin `operation_id`;
12. ausencia de contraseñas, hashes, JWT y tokens en payloads;
13. preservación de versión y fingerprints del contrato de roles.

La regresión incluyó BH-061 Incremento 1, cambios de BusinessRole de BH-059,
servicios y APIs de creación/revocación laboral, estados de Usuario/Personal,
lectura de auditoría y el bloque BH-060 afectado de estados residuales. Los
trazos de excepciones observados corresponden a escenarios deliberados de
rollback y terminaron aprobados.

Comprobaciones adicionales:

- `manage.py check`: sin observaciones;
- `makemigrations --check --dry-run`: sin cambios;
- `migrate --check`: sin migraciones pendientes;
- `git diff --check`: correcto.

## 7. Riesgos residuales

- El campo vive en JSON y no tiene índice dedicado; este incremento no añade
  filtros ni una interfaz de búsqueda por `operation_id`.
- Los eventos históricos anteriores permanecen sin correlación retroactiva.
- La unicidad depende de UUIDv4; una colisión es teóricamente posible pero
  operacionalmente despreciable.
- La auditoría adicional de habilidades continúa reservada para BH-061
  Incremento 3.
- No se implementaron retención, exportación ni protección forense append-only.

`BH-061 INCREMENTO 2 — IMPLEMENTADO Y VALIDADO`
