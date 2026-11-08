# BH-059 B — Lectura administrativa de roles y capacidades

**Fecha:** 2026-11-03

**Baseline:** `5da7cf4bd74b08e50bd74a2e15c0b207fba2e2e9`

**Alcance:** exclusivamente Incremento B

## 1. Resultado

Se incorporó una consulta administrativa canónica y de sólo lectura para
inspeccionar el BusinessRole, los perfiles vinculados, la función laboral y las
capacidades Django de un Usuario. La proyección diferencia asignaciones de
capacidades efectivas, identifica sus orígenes y presenta anomalías sin reparar
ni modificar el estado observado.

No se agregaron comandos de rol, grants/revokes, edición de grupos, cambios de
estado, migraciones ni auditoría histórica.

## 2. Autoridad y ruta

Ruta:

`GET /api/gestion/admin/usuarios/{id}/resumen-acceso/`

La acción pertenece a `AdminUsuarioViewSet` y conserva sus permisos efectivos:

- requiere autenticación;
- requiere `usuarios.manage_users` mediante `CanManageUsers`;
- el actor debe estar activo;
- `is_staff=True` por sí solo no autoriza la consulta y recibe `403`;
- `is_staff=False` con `manage_users` sí puede consultar.

El listado administrativo no se amplió con una proyección pesada. El resumen se
obtiene sólo al consultar un Usuario concreto.

## 3. Contrato de lectura

La respuesta contiene únicamente:

- `identity`: ID, email, nombre y apellido;
- `account`: `is_active`, `is_staff` e `is_superuser` como estado e indicadores
  técnicos;
- `business_role`: rol único o `null`;
- `business_roles`: todos los grupos canónicos detectados, en orden canónico;
- `role_state`: `VALID`, `NO_ROLE` o `MULTIPLE_ROLES`;
- `profiles.cliente`: existencia, ID y estado;
- `profiles.personal`: existencia, ID, estado y `job_role`, separado del
  BusinessRole;
- `assigned_capabilities`: capacidades explícitamente asignadas por grupos o
  permisos individuales;
- `effective_capabilities`: resultado efectivo de Django limitado a
  `BusinessPermission.ALL`;
- `capabilities`: detalle por capacidad observada;
- `warnings`: anomalías y advertencias deterministas;
- `technical`: sólo indicadores mínimos sobre la evaluación.

Cada elemento de `capabilities` incluye:

```json
{
  "code": "usuarios.manage_users",
  "assigned": true,
  "effective": false,
  "origins": [
    {"type": "TECHNICAL_GROUP", "identifier": "ACCESS_REVIEW"},
    {"type": "INDIVIDUAL", "identifier": null}
  ]
}
```

Los tipos de origen posibles son:

- `BUSINESS_ROLE`;
- `TECHNICAL_GROUP`;
- `INDIVIDUAL`;
- `SUPERUSER`.

Una capacidad puede tener múltiples orígenes. El orden de capacidades, roles,
orígenes, detalles y advertencias es estable.

## 4. Asignación frente a efectividad Django

`assigned` representa asignaciones explícitas observables en los grupos Django
o en `user_permissions`. El bypass de superusuario no se presenta como una
asignación: se representa como origen de una capacidad efectiva.

`effective` se calcula con `Usuario.get_all_permissions()`, que es el contrato
real usado por `has_perm()`, y luego se intersecta con
`BusinessPermission.ALL`.

Esto conserva dos diferencias importantes:

1. una cuenta inactiva puede conservar asignaciones, pero Django devuelve cero
   permisos efectivos, incluso si es superusuario;
2. un superusuario activo obtiene todas las capacidades registradas del
   catálogo canónico aunque no tenga asignaciones explícitas.

Django memoiza permisos en `_perm_cache`, `_user_perm_cache` y
`_group_perm_cache`. El servicio `build_administrative_access_summary` siempre
recarga el Usuario desde la base y consulta nuevamente grupos y permisos; no
confía en la instancia recibida por la vista. Una prueba específica confirma
que una instancia con cache obsoleta no contamina el resumen.

## 5. Anomalías y advertencias

La lectura puede publicar los siguientes códigos:

| Código | Significado |
|---|---|
| `NO_ROLE` | No existe ningún grupo de BusinessRole canónico. |
| `MULTIPLE_ROLES` | Existen varios BusinessRoles canónicos. |
| `MISSING_CLIENT_PROFILE` | El rol `CLIENTE` no tiene perfil Cliente. |
| `MISSING_PERSONAL_PROFILE` | Un rol laboral no tiene Personal vinculado. |
| `INACTIVE_PERSONAL_FOR_LABOR_ROLE` | El rol laboral está asociado a Personal inactivo. |
| `ROLE_CAPABILITY_DRIFT` | Los permisos reales del grupo de rol difieren de `ROLE_BASE_PERMISSIONS`. |
| `ADMIN_CAPABILITIES_OUTSIDE_ROLE` | Existen capacidades de administración de acceso no previstas por el rol. |
| `INDIVIDUAL_BUSINESS_PERMISSIONS` | Hay capacidades canónicas asignadas individualmente. |
| `TECHNICAL_GROUP_BUSINESS_PERMISSIONS` | Un grupo no canónico aporta capacidades de negocio. |
| `PERMISSIONS_OUTSIDE_BUSINESS_CATALOG` | Hay permisos Django asignados fuera de `BusinessPermission.ALL`. |
| `INACTIVE_ACCOUNT_CAPABILITIES_NOT_EFFECTIVE` | La cuenta inactiva conserva asignaciones que Django suprime. |
| `SUPERUSER_ACCOUNT` | La cuenta usa el bypass técnico de superusuario. |

Los permisos fuera del catálogo nunca se publican por código: sólo se informa
su cantidad y los tipos de fuente. Ninguna advertencia dispara limpieza,
reasignación o reparación automática.

## 6. Frontend mínimo

`GestionUsuarios` incorpora el botón `Ver accesos`. Al seleccionarlo consulta la
ruta de detalle y abre un modal de sólo lectura con:

- estado de cuenta y BusinessRole;
- perfiles Cliente y Personal;
- función laboral;
- capacidades asignadas/efectivas y sus orígenes;
- anomalías y advertencias.

El modal no contiene inputs, selects, checkboxes, grants, revokes, cambio de rol
ni edición de grupos. `is_staff` e `is_superuser` se muestran sólo como
indicadores técnicos cuando corresponden.

## 7. Seguridad y minimización

- No se serializan contraseña, hash, tokens, credenciales ni secretos.
- No se exponen IDs de Permission ni permisos externos por código.
- Los grupos técnicos sólo aparecen como origen de capacidades canónicas
  observadas; no se ofrecen como catálogo editable.
- La lectura no escribe Usuario, Cliente, Personal, grupos ni permisos.
- No se infiere autoridad desde `Personal.rol`, perfiles o `is_staff`.
- No se modifica el contrato de `/api/usuarios/me/`.

## 8. Pruebas

Cobertura focalizada backend:

- autorización por `manage_users` y rechazo de staff sin permiso;
- rol único, ausencia y multiplicidad de roles;
- perfiles Cliente y Personal simultáneos;
- función laboral separada;
- cuentas inactivas y superusuarios activos/inactivos;
- equivalencia con `has_perm()` dentro de `BusinessPermission.ALL`;
- permisos individuales, grupos técnicos y múltiples orígenes;
- drift del rol, perfiles ausentes y Personal inactivo;
- permisos externos sin publicar sus códigos;
- cache de permisos obsoleta en la instancia recibida;
- determinismo, ausencia de secretos y ausencia de mutaciones.

Resultado focalizado: **9/9**.

Cobertura frontend del panel afectado: **10/10**. Regresión frontend ampliada de
BH-054/BH-055 y superficies administrativas: **12 suites, 153/153**.

La regresión backend ampliada de roles, cuentas, Personal, usuarios, `/me/` y
turnos ejecutó **450 pruebas**: 447 pasaron y tres tests heredados terminaron en
error al esperar `error.code` en los rechazos de `desactivar-cuenta` y
`reactivar-cuenta`. Las operaciones sí devolvieron `403`, pero el
`AdminUsuarioViewSet.get_permissions()` del baseline intercepta las acciones y
produce el envelope estándar `detail` antes de llegar al servicio. El diff de B
en `gestion/views.py` sólo agrega el import y la acción `resumen-acceso`; no
modifica esas acciones ni su autorización. Corregir ese contrato corresponde al
incremento A/baseline y queda fuera de B.

Validación final adicional:

- roles, `/me/`, contención BH-059 A y lectura B: **61/61**;
- `python manage.py check`: sin observaciones;
- compilación Python de los archivos alcanzados: sin errores;
- build productivo frontend: completado con warnings preexistentes en módulos
  ajenos a B; con `CI=true` esos warnings globales se tratan como errores;
- `git diff --check`: sin errores de whitespace (sólo avisos de finales de línea
  del entorno Windows).

## 9. Límites confirmados

No se implementó:

- cambio de BusinessRole;
- grant o revoke individual;
- edición de grupos técnicos;
- activación o desactivación nueva;
- reparación automática de anomalías;
- auditoría histórica BH-061;
- editor o matriz avanzada BH-062;
- ninguna parte de BH-059 C.
