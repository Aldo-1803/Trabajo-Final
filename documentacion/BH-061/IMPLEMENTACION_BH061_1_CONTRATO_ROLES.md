# BH-061 Incremento 1 — Semántica no-op y contrato versionado de roles

**Fecha:** 2026-11-08

**Baseline de inicio:**
`c0f70cdc7dbb812a9cf269ddde55acbf3da9524e`

## 1. Alcance

Este incremento corrige exclusivamente el falso evento del no-op inicial de
CLIENTE y publica una referencia verificable para las capacidades canónicas de
cada `BusinessRole`.

No incorpora correlación con `operation_id`, auditoría adicional de
habilidades, edición de permisos, grants individuales, migración de eventos
históricos ni cambios en las capacidades otorgadas a los roles.

## 2. Causa y corrección del evento falso

`assign_initial_client_role()` ya calculaba correctamente `changed=False`
cuando el Usuario tenía exactamente el rol `CLIENTE`, pero la creación de
`INITIAL_CLIENT_ROLE_ASSIGNED` era incondicional. Por eso una segunda llamada
producía evidencia de una asignación inexistente.

El servicio ahora retorna inmediatamente en ese estado final con:

- `changed=False`;
- `audit_id=None`;
- el mismo Usuario, Cliente y rol;
- cero escrituras sobre grupos, permisos, perfiles o flags de cuenta;
- cero eventos semánticos adicionales.

La primera asignación efectiva conserva la transacción, valida el perfil
Cliente, deja exactamente un BusinessRole y escribe el evento dentro de la
misma transacción. `InitialClientRoleAssignmentResult.audit_id` pasó a aceptar
`None` como resultado legítimo del no-op. El registro público continúa usando
el mismo contrato y respuesta HTTP.

## 3. Contrato de capacidades publicado

La versión activa es:

`bh061-role-capabilities-v1`

`usuarios.roles.ROLE_CAPABILITY_CONTRACTS` conserva snapshots de sólo lectura:
el mapa exterior e interior usa `MappingProxyType` y cada conjunto canónico se
representa mediante una tupla. `ROLE_BASE_PERMISSIONS` referencia el snapshot
activo, por lo que no se alteraron los permisos efectivos actuales.

Los fingerprints publicados son:

| BusinessRole | SHA-256 |
|---|---|
| `CLIENTE` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `EMPLEADO` | `50e04a16d3ae0b6bd98b4b2ca2febb3f57d00165bb7e75fb7e890f16e579e58f` |
| `PROFESIONAL` | `1af6d25083401d4b4624047fc4674eea00a4b6fd2540f3e35c941382cb51fb4a` |
| `ADMINISTRADOR` | `8d700df9707ad7c16d82cf01ca310e6da43a3bb57af6dd26ec95aef265a4b3da` |

El módulo valida los fingerprints publicados al importarse. Modificar el
snapshot v1 sin publicar otra versión provoca un error explícito. Un cambio
futuro de capacidades debe agregar un snapshot y fingerprints nuevos y mover
la versión activa; no debe reescribir v1.

## 4. Algoritmo de fingerprint

El identificador de codificación es:

`json-utf8-sorted-unique-v1`

Para cada rol:

1. se eliminan permisos duplicados;
2. los códigos se ordenan lexicográficamente;
3. se serializa la colección como JSON sin espacios, con `ensure_ascii=True`;
4. el JSON se codifica como UTF-8;
5. se calcula SHA-256 y se guarda su representación hexadecimal minúscula.

El resultado no depende del orden de tuplas, sets o diccionarios ni consulta
estado de base de datos. Cuando no existe un rol anterior válido, el
fingerprint anterior es `None`; no se inventa un rol vacío.

## 5. Metadata incorporada

`build_business_role_audit_metadata()` centraliza estos campos:

- `role_contract_version`;
- `previous_role_permissions_fingerprint`;
- `new_role_permissions_fingerprint`.

Se agregan únicamente cuando existe una mutación efectiva en:

- `INITIAL_CLIENT_ROLE_ASSIGNED`;
- `BUSINESS_ROLE_CHANGED`;
- `CLIENT_ACCOUNT_CREATED_BY_STAFF`;
- `ADMINISTRATOR_ACCOUNT_CREATED`;
- `PERSONAL_BUSINESS_ROLE_CHANGED`;
- `PERSONAL_ACCESS_CREATED`;
- `WORK_ACCESS_REVOKED_KEEP_CLIENT`, cuando realmente cambia el rol.

Los eventos conservan actor, objetivo, fuente, motivo, roles, grupos canónicos
y referencias subordinadas existentes. No copian listas completas de permisos
ni presentan permisos individuales o grupos técnicos preservados como parte
del delta del BusinessRole.

## 6. Compatibilidad histórica

No se modificó `gestion.Auditoria`, no hay migración y no se actualizaron filas
existentes. Los campos nuevos viven en el JSON de los eventos nuevos.

Las APIs y serializers de lectura continúan tratando `valor_anterior` y
`valor_nuevo` como JSON libre. Una prueba de regresión consulta por API un
evento histórico sin `role_contract_version` y confirma que sigue siendo
legible.

## 7. Pruebas y regresiones

La matriz focal se ejecutó sobre PostgreSQL mediante
`bohemiacore.test_settings` y su runner estable:

- **251 tests ejecutados, 251 aprobados**;
- asignación inicial y segundo no-op de CLIENTE;
- cardinalidad exacta y `audit_id=None`;
- fingerprints publicados, determinismo e independencia del orden;
- promoción a ADMINISTRADOR y degradación válida;
- cambios EMPLEADO ↔ PROFESIONAL;
- altas de Cliente, Administrador y acceso laboral;
- rollback de grupo y operación compuesta ante fallo de auditoría;
- rechazo sin evento de éxito;
- preservación de permisos individuales y grupos técnicos;
- ausencia de passwords, hashes y tokens en payloads;
- lectura de eventos históricos sin metadata;
- infraestructura de roles, sesión y capacidades;
- bloques BH-060 afectados de catálogos, agenda, ficha técnica, configuración,
  Django Admin, estados residuales y cierre de autorizaciones.

Comprobaciones adicionales:

- `manage.py check`: sin observaciones;
- `makemigrations --check --dry-run`: sin cambios;
- `migrate --check`: sin migraciones pendientes;
- compilación Python focal: correcta.

Una repetición aislada con el runner Django por defecto encontró grupos
canónicos ausentes después de un `flush` previo de `TransactionTestCase`. Se
clasificó como estado del test harness: al usar el runner oficial
`StablePostgresTestRunner`, que restaura seeds, la matriz conjunta pasó
completa. No se modificó código para ocultar esa diferencia de configuración.

Después de separar la clave inmutable v1 del puntero de versión activa, se
repitieron las cinco pruebas del contrato junto con una prueba transaccional:
**6/6 aprobadas**. Ejecutar únicamente `SimpleTestCase` con el runner estable
no abre una base de test y activa correctamente su protección contra restaurar
seeds en una conexión no aislada; se clasificó también como limitación del
harness, no como fallo de aserción.

## 8. Riesgos y trabajo pendiente

Permanecen fuera de este incremento:

- correlación uniforme de operaciones compuestas mediante `operation_id`;
- fuente y motivo en auditoría de habilidades;
- cardinalidad de eventos en carreras PostgreSQL adicionales;
- grants/revokes individuales y grupos técnicos, que siguen sin ser una
  superficie de producto;
- protección forense o append-only a nivel de base de datos.

No se inició BH-061 Incremento 2 ni BH-062.

`BH-061 INCREMENTO 1 — IMPLEMENTADO Y VALIDADO`
