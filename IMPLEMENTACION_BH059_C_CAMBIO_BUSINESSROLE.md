# BH-059 C — Cambio seguro de BusinessRole

**Fecha:** 2026-11-04

**Baseline publicado:** `4e031821165a87acca6a25370ca2c502eab8e327`

**Alcance:** exclusivamente Incremento C

## 1. Resultado

Se incorporó una operación administrativa acotada para cambiar el
`BusinessRole` de un Usuario entre `CLIENTE`, `EMPLEADO`, `PROFESIONAL` y
`ADMINISTRADOR`.

La operación reutiliza `assign_validated_business_role` como única primitiva de
mutación y auditoría. La nueva orquestación
`change_administrative_business_role` agrega la política general de autoridad,
la protección concurrente del último administrador y el control de privilegios
residuales. Los cambios laborales acotados de Personal mantienen sus servicios
y autoridades existentes.

No se agregaron modelos, migraciones, grants/revokes genéricos ni edición de
grupos o permisos.

## 2. Autoridad

El cambio general requiere conjuntamente los permisos Django efectivos:

- `usuarios.manage_users`;
- `usuarios.assign_roles`.

La API verifica la conjunción para devolver un error estable y el servicio la
vuelve a verificar después de recargar el actor desde base. El actor debe estar
activo. `is_staff`, `Personal.rol` y el rol indicado por el frontend no conceden
autoridad.

Se rechazan:

- autoacción;
- objetivos superusuario;
- BusinessRoles desconocidos;
- objetivos con múltiples BusinessRoles;
- perfiles o estados de destino incompatibles.

## 3. Perfiles y estado preservado

| Destino | Regla aplicada |
|---|---|
| `CLIENTE` | Requiere un perfil Cliente existente. El estado `Cliente.activo` conserva la decisión vigente y no se modifica. |
| `EMPLEADO` | Requiere Personal vinculado y activo. |
| `PROFESIONAL` | Requiere Personal vinculado y activo. |
| `ADMINISTRADOR` | No exige perfil; rechaza superusuario y aplica la política administrativa dedicada. |

El comando cambia exclusivamente la membresía de BusinessRole. Preserva:

- perfiles Cliente y Personal, IDs y ownership;
- grupos técnicos legítimos;
- permisos individuales;
- contraseña y credenciales;
- `is_active`, `is_staff` e `is_superuser`.

No crea, elimina, activa, desactiva ni reasigna perfiles implícitamente.

## 4. Último administrador y concurrencia

La degradación de un `ADMINISTRADOR` bloquea la fila del Usuario objetivo y el
grupo canónico `ADMINISTRADOR` dentro de la misma transacción que valida y
aplica el cambio. La desactivación de cuentas usa el mismo helper y el mismo
lock de serialización.

El respaldo debe ser otro Usuario:

- activo;
- no superusuario;
- con exactamente el BusinessRole `ADMINISTRADOR`.

No cuentan `is_staff`, permisos individuales, administradores inactivos,
superusuarios ni cuentas con múltiples BusinessRoles.

Dos pruebas `TransactionTestCase` sobre PostgreSQL real cubren:

1. degradación concurrente de los dos últimos administradores;
2. degradación de uno y desactivación concurrente del otro.

En ambas carreras exactamente una operación cambia estado y la otra recibe la
protección de último administrador; siempre queda un administrador de negocio
activo.

## 5. Privilegios residuales

Antes de degradar un administrador,
`project_role_transition_access_capabilities` proyecta el estado posterior:

- retira conceptualmente todos los BusinessRoles actuales;
- incorpora el rol destino;
- conserva grupos técnicos y permisos individuales;
- inspecciona `manage_users`, `assign_roles` y `manage_personal` con sus
  orígenes canónicos de B.

Si una fuente individual o técnica conservaría autoridad de administración de
accesos, la transición responde `RESIDUAL_ADMIN_CAPABILITIES` y publica el
detalle de capacidades/orígenes. No se limpia ninguna excepción en silencio.
Permisos técnicos no escalantes, por ejemplo `gestion.view_stock`, se conservan
y no bloquean la transición.

## 6. API

Ruta:

`POST /api/gestion/admin/usuarios/{id}/cambiar-rol-negocio/`

Payload estricto:

```json
{
  "role": "CLIENTE",
  "motivo": "Cambio administrativo aprobado"
}
```

No se admiten campos inesperados. La respuesta incluye `changed`, rol anterior,
`business_role` efectivo, ID de auditoría y el `access_summary` canónico
actualizado.

Errores estables:

| Código | HTTP | Significado |
|---|---:|---|
| `PERMISSION_DENIED` | 403 | Falta autoridad conjunta o el actor está inactivo. |
| `SELF_ROLE_CHANGE_NOT_ALLOWED` | 403 | Autoacción. |
| `PROTECTED_SUPERUSER` | 403 | Objetivo técnico protegido. |
| `INVALID_ROLE` | 400 | Rol desconocido o ausente. |
| `INVALID_REASON` | 400 | Motivo inválido. |
| `INVALID_PAYLOAD` | 400 | Campos inesperados o combinación inválida. |
| `INCONSISTENT_BUSINESS_ROLES` | 409 | El objetivo tiene múltiples roles. |
| `CLIENT_PROFILE_REQUIRED` | 409 | Falta Cliente. |
| `PERSONAL_PROFILE_REQUIRED` | 409 | Falta Personal. |
| `PERSONAL_INACTIVE` | 409 | Personal inactivo. |
| `LAST_ACTIVE_ADMIN` | 409 | La degradación dejaría cero administradores activos. |
| `RESIDUAL_ADMIN_CAPABILITIES` | 409 | Persistiría autoridad administrativa por otra fuente. |
| `USER_NOT_FOUND` | 404 | Objetivo inexistente. |

Un no-op válido devuelve `changed=false`, no crea una segunda auditoría y
mantiene el resumen actualizado.

## 7. Auditoría y atomicidad

La mutación delega en `assign_validated_business_role`, que conserva el evento
semántico `BUSINESS_ROLE_CHANGED` con actor, objetivo, rol anterior, rol nuevo,
motivo, grupos retirados y grupo incorporado.

Validación, locks, cambio y auditoría comparten transacción. Una falla de
auditoría revierte la membresía; los conflictos de perfil, último administrador
o autoridad residual no escriben rol ni auditoría. La primitiva invalida las
caches Django de permisos de la instancia recibida.

## 8. Interfaz mínima

`GestionUsuarios` muestra `Cambiar rol` sólo cuando la sesión publica ambos
permisos requeridos. El backend sigue siendo la autoridad.

El modal presenta:

- rol actual y destino;
- perfiles Cliente y Personal vinculados;
- advertencias por perfil ausente/inactivo;
- advertencia de autoridad residual individual o técnica;
- motivo obligatorio;
- confirmación explícita;
- resultado con transición aplicada.

Al completar el comando, el listado se actualiza desde la respuesta canónica.
Los códigos 403/409 tienen mensajes seguros. No se incorporó un editor avanzado
de permisos, grupos o excepciones.

## 9. Pruebas y validación

Suites nuevas de C:

- servicio: 8 pruebas;
- API: 8 pruebas;
- concurrencia PostgreSQL: 2 pruebas;
- panel afectado: 15/15, incluidas 5 coberturas nuevas de cambio de rol.

Regresión focalizada de A/B, roles, `/me/`, cuentas y Personal:
**267/267**.

Frontend completo: **33 suites, 282/282**.

Validaciones adicionales:

- `python manage.py check`: sin observaciones;
- compilación Python de los archivos alcanzados: sin errores;
- build productivo frontend: correcto; sólo warnings preexistentes en archivos
  ajenos a C;
- `git diff --check`: sin errores de whitespace; el entorno Windows informa
  únicamente normalización CRLF/LF.

La autodetección por defecto del proyecto ejecutó adicionalmente **150/150**.
La etiqueta `usuarios gestion.tests` resuelve el módulo legacy
`gestion/tests.py`, no el directorio homónimo, y por eso sólo ejecuta
**153/153**; no se usa para inflar la cobertura ampliada informada arriba.

Una corrida exhaustiva adicional con etiquetas de apps descubrió 965 pruebas,
incluidas suites legacy ajenas a BH-059, y agotó el límite de 30 minutos antes
de terminar. No produjo un resultado utilizable y no sustituye las regresiones
focalizadas completas enumeradas arriba.

## 10. Tres errores heredados separados

Se reprodujeron sin modificar sus contratos:

1. `AccountDeactivationActionTests.test_manage_users_is_required_without_staff_shortcut`, actor sin permiso;
2. el mismo test, subcaso actor sólo `is_staff`;
3. `AccountReactivationActionTests.test_manage_users_is_required_without_staff_shortcut`.

Los tres esperan:

```json
{"error": {"code": "PERMISSION_DENIED"}}
```

y reciben un `403` DRF con:

```json
{"detail": "No tiene permisos para administrar usuarios."}
```

El origen es BH-059 A: `AdminUsuarioViewSet.get_permissions()` aplica
`CanManageUsers` antes de que las actions alcancen sus servicios semánticos y
anula el `permission_classes=[IsAuthenticated]` declarado en ellas. Seguridad y
persistencia son correctas; no se produce mutación. El frontend cae en su
mensaje genérico en lugar del mensaje por código.

Es una regresión heredada de envelope, no un bloqueo funcional de C. Debe
resolverse en una corrección acotada separada que unifique el contrato de A.

## 11. Límites confirmados y pendientes

No se implementó:

- BH-059 D;
- grant/revoke o editor de permisos individuales;
- edición o revocación automática de grupos técnicos;
- historial avanzado BH-061;
- rediseño BH-062;
- cambios financieros BH-058;
- corrección oportunista de los tres envelopes heredados.

Pendiente fuera de C: corregir el envelope heredado de desactivación/reactivación
en un cambio separado y volver a dejar esa regresión global completamente
verde.
