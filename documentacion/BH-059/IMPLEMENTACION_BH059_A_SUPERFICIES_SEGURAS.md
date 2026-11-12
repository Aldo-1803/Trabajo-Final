# BH-059 A — Cierre de superficies inseguras de acceso

**Fecha:** 2026-11-03

**Baseline:** `21a30fb17a54e87b1190810badba2b6a37b55fc2`

**Alcance:** exclusivamente Incremento A

## 1. Resultado

Se cerraron las superficies genéricas que permitían consultar o modificar
identidad, estado, privilegios o vínculos sin pasar por permisos Django
efectivos y operaciones semánticas. `is_staff` queda como atributo técnico de
acceso al sitio Django Admin y deja de ser autoridad en las APIs de Usuario,
Personal y auditoría alcanzadas por este incremento.

No se agregaron permisos, modelos ni migraciones.

## 2. Contratos y rutas

### 2.1 Usuarios

Ruta base: `/api/gestion/admin/usuarios/`.

| Operación | Autoridad | Resultado |
|---|---|---|
| `GET` lista/detalle | `usuarios.manage_users` | Reemplaza `IsAdminUser`; funciona con `is_staff=False`. |
| `PUT` / `PATCH` | `usuarios.manage_users` | Sólo acepta `email`, `first_name` y `last_name`. |
| `POST` genérico | Ninguna | Continúa cerrado con `405`; se conservan las altas semánticas dedicadas. |
| `DELETE` genérico | `usuarios.manage_users` para alcanzar la ruta | Responde `405` y no cambia Usuario ni Cliente. |
| `desactivar-cuenta` / `reactivar-cuenta` | `usuarios.manage_users` | Conserva los servicios semánticos existentes. |

El serializer de escritura rechaza expresamente campos inesperados. No admite
`password`, `groups`, `user_permissions`, BusinessRole, `is_active`,
`is_staff`, `is_superuser` ni vínculos de perfil.

### 2.2 Personal y habilidades

Ruta completa: `/api/gestion/personal/`.

- lista, detalle y CRUD genérico requieren `gestion.manage_personal`;
- el borrado físico continúa cerrado con `405`;
- el serializer genérico permite únicamente datos laborales de dominio:
  `nombre`, `apellido`, `rol`, `email`, `telefono` y `color_calendario`;
- `Personal.usuario`, `Personal.activo`, resúmenes de cuenta y flags legacy de
  habilidades son de sólo lectura y una escritura que los incluya se rechaza;
- las acciones de vínculo, estado, rol y revocación conservan la autorización,
  locks, invariantes y auditoría de sus servicios semánticos.

Nueva proyección para skills:

`GET /api/gestion/personal/directorio-habilidades/`

- requiere `gestion.manage_skills`;
- devuelve sólo `id`, `nombre`, `apellido` y `activo`;
- no expone teléfono, email, Usuario vinculado, estado de cuenta, BusinessRole
  ni controles administrativos.

La administración canónica de habilidades de BH-056 conserva sus endpoints y
servicios. `GestionPersonal` usa la proyección mínima cuando el actor tiene
`manage_skills` pero no `manage_personal`, y oculta columnas de contacto y
acceso.

### 2.3 Alta laboral

La creación de acceso desde Personal acepta exclusivamente:

- `EMPLEADO`;
- `PROFESIONAL`.

`ADMINISTRADOR` y `CLIENTE` producen `INVALID_ROLE` sin crear ni vincular una
cuenta. La opción Administrador fue retirada de `GestionPersonal`.

El alta administrativa dedicada se preserva sin cambios y continúa siendo la
única vía para crear un BusinessRole `ADMINISTRADOR`.

### 2.4 Auditoría y reversión

| Superficie | Autoridad efectiva |
|---|---|
| `/api/gestion/auditoria/` | `gestion.view_audit` |
| historial simple-history, lectura | `gestion.view_audit` |
| historial simple-history, `revertir` | `gestion.revert_audit` |

La reversión genérica de `Personal` no puede restaurar `usuario`, `rol` ni
`activo`. Si la versión histórica difiere en cualquiera de esos campos, la
operación responde `403`, informa `blocked_fields` y no aplica cambios. Los
campos protegidos tampoco forman parte del conjunto copiable de una reversión.

### 2.5 Django Admin y vínculo indirecto

- `UsuarioAdmin` deja `is_active`, `is_staff`, `is_superuser`, `groups` y
  `user_permissions` en sólo lectura;
- se deshabilitan alta, baja y acciones masivas de Usuario;
- el `GroupAdmin` estándar se retira para impedir edición arbitraria de los
  permisos de BusinessRole o grupos técnicos;
- `Cliente.usuario` y `Cliente.activo` quedan en sólo lectura, y se deshabilitan
  alta, baja y acciones masivas de Cliente;
- `Personal.usuario` y `Personal.activo` quedan en sólo lectura, y se
  deshabilitan baja y acciones masivas de Personal;
- nombre, contacto, función laboral y otros datos de dominio no sensibles de
  Personal/Cliente siguen siendo administrables;
- el flujo de contenido educativo ya no crea un `Personal` vinculado por tener
  `is_staff`; la visibilidad administrativa usa `gestion.manage_content` y un
  autor debe contar previamente con un vínculo de Personal válido.

## 3. Compatibilidad

- `GestionUsuarios` conserva la proyección de lectura que utiliza actualmente,
  incluidos `is_staff`, `is_active` y `business_role`; estos campos no son
  escribibles.
- Las operaciones semánticas de cuenta y Personal conservan sus respuestas y
  códigos de dominio.
- No cambian URLs de habilidades existentes; sólo se agrega el directorio
  mínimo.
- No cambia el modelo `Personal.rol`: sigue siendo función laboral y no
  BusinessRole.
- No hay cambios de esquema, seeds ni migraciones.
- No se modificó lógica financiera de BH-058. El test de referencia obsoleta de
  Usuario usa limpieza directa de fixture para no invocar el recolector de
  borrado sobre querysets financieros deliberadamente inmutables.

## 4. Pruebas cubiertas

- `is_staff=True` sin permiso efectivo recibe `403` en Usuarios, Personal y
  auditoría;
- permiso efectivo con `is_staff=False` autoriza cada lectura correspondiente;
- `DELETE` genérico de Usuario devuelve `405` sin alterar cuenta ni Cliente;
- payloads maliciosos de privilegios, estados y vínculos son rechazados;
- `manage_skills` sólo obtiene la proyección mínima;
- `ADMINISTRADOR` se rechaza en alta laboral backend y no aparece en frontend;
- reversión histórica de acceso se rechaza;
- Django Admin no ofrece campos, acciones, altas/bajas o grupos que eludan los
  servicios semánticos;
- el flujo de contenido no puede autogenerar un vínculo de Personal por
  `is_staff`;
- regresiones de roles, usuarios, Personal, skills y auditoría.

Validación ejecutada:

- backend focalizado: `71/71`;
- backend ampliado de usuarios, roles, Personal, skills y auditoría: `259/259`;
- frontend (`GestionPersonal`, `GestionUsuarios`, `ProtectedRoute`,
  `SessionContext`): `75/75`;
- compilación Python: sin errores;
- `git diff --check`: sin errores (sólo advertencias de finales de línea del
  entorno Windows).

## 5. Riesgos y trabajo pendiente fuera de A

1. **BH-059 B:** aún no existe una lectura administrativa canónica del origen
   de capacidades efectivas.
2. **BH-059 C:** no se implementó cambio general de BusinessRole, protección de
   último administrador para esa transición ni tratamiento de privilegios
   residuales.
3. **BH-059 D:** no se modificó el ciclo de reactivación o preparación de
   cuentas.
4. No se habilitó editor de permisos individuales o grupos técnicos.
5. Los usos legacy de `IsAdminUser` en APIs puramente de dominio no alcanzadas
   por este incremento no se migraron en bloque. No pueden escribir los campos
   de acceso cerrados aquí; su migración requiere definir la autoridad de cada
   dominio y no debe mezclarse con BH-059 A.
6. BH-061 y BH-062 permanecen fuera de alcance.

## 6. Frontera confirmada

No se implementaron BH-059 B/C/D, permisos individuales, historial avanzado,
rediseño administrativo ni cambios financieros.
