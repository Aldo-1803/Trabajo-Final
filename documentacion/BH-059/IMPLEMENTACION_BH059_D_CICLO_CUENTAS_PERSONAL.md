# Implementación BH-059 D — Ciclo de cuentas y acceso laboral

## 1. Alcance y baseline

Incremento implementado sobre
`ca967220ad6c45eac6d46171d0901f4487947a57`, sin adelantar BH-059 E,
BH-060, BH-061 ni BH-062.

Se reutilizaron exclusivamente los comandos existentes:

- `usuarios.access_services.deactivate_account`;
- `usuarios.access_services.reactivate_account`;
- operaciones de `gestion.personal_access_services` para estado, vínculo,
  alta y revocación de acceso laboral.

No se agregó CRUD genérico de permisos, grupos o `BusinessRole`, ni otro
sistema de autenticación.

## 2. Diagnóstico previo a los cambios

La inspección inicial confirmó estas incompatibilidades reales:

1. Los tres errores heredados de BH-059 A eran reproducibles. Las actions de
   desactivación/reactivación declaraban `IsAuthenticated`, pero el override
   `AdminUsuarioViewSet.get_permissions()` aplicaba antes `CanManageUsers` y
   DRF respondía `{"detail": ...}`. El contrato público esperado por las
   actions era `403 {"error":{"code":"PERMISSION_DENIED", ...}}`.
2. La arquitectura usa SimpleJWT 5.5.1 por header `Authorization`, con la app
   `token_blacklist`, access de 7 días y refresh de 30 días. La baja hacía que
   `JWTAuthentication` y `TokenRefreshSerializer` rechazaran temporalmente al
   usuario inactivo, pero no registraba revocación persistente.
3. Al reactivar, un access anterior volvía a autenticarse hasta vencer. Un
   refresh anterior también podía volver a utilizarse porque no estaba en
   blacklist.
4. La revocación “conservar Cliente” aceptaba cuentas sin rol o con
   `ADMINISTRADOR` y las convertía a `CLIENTE`. Eso otorgaba un rol implícito
   al estado sin rol y permitía degradar administradores por una vía que no
   aplicaba la protección del último administrador.
5. El vínculo de cuenta y Personal preservaba correctamente los estados, pero
   sólo advertía cuenta inactiva, Personal inactivo o ausencia de rol; no
   identificaba de forma estable un rol existente incompatible con acceso
   laboral.

La separación entre `Usuario.is_active`, `Cliente.activo` y `Personal.activo`,
la preservación de ownership/perfiles y los locks principales ya eran
correctos y se conservaron.

## 3. Contrato de estados

- Desactivar/reactivar una cuenta modifica sólo `Usuario.is_active`.
- Desactivar/reactivar Personal modifica sólo `Personal.activo`.
- `Cliente.activo` nunca cambia como efecto lateral de una operación de cuenta
  o Personal.
- Reactivar `CLIENTE` con perfil inactivo conserva `Cliente.activo=False` y
  devuelve `CLIENT_PROFILE_INACTIVE`.
- Reactivar `EMPLEADO` o `PROFESIONAL` exige Personal vinculado y activo.
- Vincular no activa cuenta o Personal, no asigna rol y no corrige estados.
- Un vínculo con `CLIENTE` o `ADMINISTRADOR` devuelve
  `BUSINESS_ROLE_INCOMPATIBLE`; un vínculo sin rol devuelve
  `NO_BUSINESS_ROLE`.

## 4. Operaciones seguras

Los comandos siguen exigiendo permisos Django efectivos y motivo de 3 a 500
caracteres. Mantienen transacciones y `select_for_update()` sobre las filas que
mutan, auditoría semántica, idempotencia, rollback, protección de
superusuarios, autoacción y último administrador donde corresponde.

La revocación laboral conservando Cliente ahora:

- acepta como origen sólo `EMPLEADO`, `PROFESIONAL` o el estado final
  idempotente `CLIENTE`;
- rechaza cuenta sin rol o `ADMINISTRADOR` con
  `INVALID_WORK_ACCESS_STATE`;
- rechaza auto-revocación con `SELF_REVOCATION_NOT_ALLOWED`;
- nunca crea un Cliente ni habilita `Cliente.activo`;
- preserva cuenta, perfil Cliente, ownership, relaciones e historial.

La revocación total continúa delegando la baja de cuenta en
`deactivate_account` y luego desactiva Personal dentro de la misma transacción.
No cambia roles ni perfiles.

## 5. SimpleJWT y revocación comprobable

En una baja efectiva, `deactivate_account` bloquea y agrega a
`BlacklistedToken` todos los `OutstandingToken` no vencidos del usuario. La
reactivación repite la barrera antes de activar la cuenta, para cubrir refresh
pendientes registrados durante el período inactivo. Todo ocurre dentro de la
transacción del comando: si falla la blacklist o la auditoría, se revierte
también el cambio de estado.

Las respuestas y auditorías exponen sólo el contador
`refresh_tokens_revoked`, nunca el JWT ni su JTI. Repetir una baja final no
duplica blacklist ni auditoría.

### Riesgo residual

SimpleJWT no consulta `token_blacklist` para access tokens normales. Por eso:

- un access previo se rechaza mientras `is_active=False`;
- puede recuperar validez tras reactivar y hasta su expiración;
- la API devuelve `PREEXISTING_ACCESS_TOKENS_MAY_REGAIN_VALIDITY` y la UI lo
  muestra explícitamente;
- un refresh revocado permanece inutilizable después de reactivar.

Antes de producción debe aceptarse formalmente esta ventana o reducir
significativamente `ACCESS_TOKEN_LIFETIME`. Si se exige revocación completa e
inmediata, hace falta un incremento separado y revisado que incorpore una
versión/epoch de credenciales en los access tokens y la valide en cada request;
no se introdujo esa infraestructura en D.

## 6. Contratos HTTP y frontend

Las actions de cuenta pasan sólo por `IsAuthenticated` a nivel DRF y dejan la
autorización efectiva al servicio semántico. Así se conserva 401 para anónimos,
403 para falta de permiso, cero mutaciones denegadas y el envelope estable
`error.code` para los tres casos heredados.

`GestionUsuarios` diferencia cuenta de perfiles, exige confirmación y motivo,
recarga el listado y muestra advertencias de Cliente inactivo, access previos y
refresh revocados.

`GestionPersonal` describe qué estado modifica cada action, mantiene motivo y
confirmación, recarga tras éxito, muestra todas las advertencias de vínculos y
trata de forma estable los 403/409 de dominio. No se rediseñó la pantalla.

## 7. Cobertura

Pruebas sobre PostgreSQL cubren:

- baja/reactivación, perfiles preservados y Cliente inactivo;
- Personal inactivo para roles laborales;
- ownership, revocación laboral y total;
- superusuario, autoacción y último administrador;
- cuenta sin rol, rol incompatible y múltiples roles;
- access/refresh antes, durante y después del ciclo;
- blacklist, idempotencia y rollback transaccional;
- los tres envelopes 403 heredados sin mutación;
- concurrencia con cambio de rol BH-059 C.

Validaciones ejecutadas:

- suite focalizada D sobre una base PostgreSQL nueva: **177/177**;
- regresión focalizada de BH-059 A/B/C y módulos relacionados sobre una base
  PostgreSQL nueva: **163/163**;
- concurrencia PostgreSQL C: **2/2**;
- paneles afectados: **32/32**;
- frontend completo: **33 suites, 283/283**;
- build productivo frontend: correcto; conserva únicamente warnings legacy en
  archivos ajenos a D, además de Browserslist y la dependencia dinámica;
- `manage.py check`: correcto;
- `git diff --check`: sin errores (sólo avisos CRLF/LF del entorno Windows).
