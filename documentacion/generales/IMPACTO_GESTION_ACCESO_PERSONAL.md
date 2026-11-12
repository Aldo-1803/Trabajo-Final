# Validacion de impacto: gestion de acceso del Personal

**Fecha:** 21 de octubre de 2026
**Modalidad:** analisis estatico del codigo actual
**Alcance:** identidad digital, perfil laboral, vinculacion, rol, baja/reactivacion y contrasena

> Este documento no implementa cambios. No se modificaron modelos, endpoints, frontend ni migraciones. Las operaciones descritas son propuestas para una implementacion posterior.

## 1. ESTADO ACTUAL

### Entidades y relaciones

#### Usuario

`Usuario` hereda de `AbstractUser` y usa `email` unico como identificador de autenticacion (`usuarios/models.py:51-66`). Conserva los campos y relaciones estandar de Django:

- `password`: hash de credencial.
- `is_active`: habilitacion global de la cuenta.
- `is_staff`: acceso tecnico al Django Admin y, por dependencia legacy, a endpoints con `IsAdminUser`.
- `is_superuser`: bypass tecnico global; no forma parte del rol de negocio aprobado.
- `groups`: incluye los Groups de rol y puede incluir Groups tecnicos.
- `user_permissions`: permisos individuales adicionales.

No existe un campo de rol en `Usuario`. El rol de negocio se representa exclusivamente mediante uno de los cuatro Groups definidos en `usuarios/roles.py`.

#### Cliente.usuario

`Cliente.usuario` es un `OneToOneField` obligatorio, clave primaria y con `on_delete=CASCADE` (`usuarios/models.py:70-76`). No declara `related_name`, por lo que el acceso inverso es `usuario.cliente`.

Consecuencias:

- Un Usuario puede tener como maximo un Cliente.
- Un Cliente siempre tiene Usuario.
- El PK de Cliente coincide con `usuario_id`.
- Borrar Usuario borra Cliente.
- Borrar Cliente no borra Usuario.
- `Cliente.activo` y `Usuario.is_active` son estados independientes, aunque algunos flujos actuales los modifican juntos.

#### Personal.usuario

`Personal.usuario` es un `OneToOneField` opcional, nullable, con `on_delete=SET_NULL` y `related_name='perfil_profesional'` (`gestion/models.py:26-43`).

Consecuencias:

- Personal puede existir sin Usuario y sin acceso digital.
- Un Usuario puede estar vinculado como maximo a un Personal.
- Un Usuario puede tener simultaneamente `usuario.cliente` y `usuario.perfil_profesional`.
- Borrar Usuario conserva Personal y deja `Personal.usuario=NULL`.
- Borrar o desvincular Personal conserva Usuario, sus Groups, permisos, password y flags.
- El acceso inverso correcto es `usuario.perfil_profesional`; cualquier uso de `usuario.personal` o `usuario.profesional` es incorrecto.

`PersonalSerializer.usuario` es de solo lectura (`gestion/serializers.py:571-596`). El CRUD generico ya no puede vincular usuarios ni elevar `is_staff`, lo que preserva la contencion implementada en BH-052A.

#### Estados laborales y de cuenta

`Personal.activo` indica disponibilidad o vigencia laboral. `Usuario.is_active` indica si la identidad puede autenticarse y usar requests autenticadas. No existe sincronizacion automatica entre ambos.

| Estado | Significado aprobado | Efecto actual |
|---|---|---|
| `Personal.activo=True` | Perfil laboral vigente | Se usa en algunos filtros, pero no gobierna todas las acciones laborales |
| `Personal.activo=False` | Baja, suspension o perfil no operativo | No desactiva Usuario ni cambia rol |
| `Usuario.is_active=True` | Cuenta digital habilitada | El login propio no lo valida explicitamente antes de emitir JWT |
| `Usuario.is_active=False` | Cuenta digital deshabilitada | No cambia Personal, rol ni password |
| `Cliente.activo` | Estado comercial del perfil Cliente | Algunos flujos lo acoplan incorrectamente a `Usuario.is_active` |

#### Personal.rol

`Personal.rol` admite `colorista`, `asistente` y `administrador` (`gestion/models.py:31-47`). Es un dato laboral legacy y no es el rol de negocio. No asigna Groups, no concede permisos y no modifica flags.

Puede utilizarse como validacion de coherencia temporal:

- `EMPLEADO` normalmente corresponde a `Personal.rol='asistente'`.
- `PROFESIONAL` normalmente corresponde a `Personal.rol='colorista'`.
- `ADMINISTRADOR` no requiere Personal. Si tiene Personal, sus tareas tecnicas dependen de Personal activo y skills, no de `Personal.rol` por si solo.

No debe cambiarse `Personal.rol` automaticamente al asignar un Group.

### Groups y Permissions nuevos

`usuarios/roles.py` centraliza:

- `BusinessRole.CLIENTE`.
- `BusinessRole.EMPLEADO`.
- `BusinessRole.PROFESIONAL`.
- `BusinessRole.ADMINISTRADOR`.
- Los 30 permisos de negocio.
- Las matrices base por rol.
- Helpers de consulta e inconsistencia.
- `assign_business_role()` para reemplazar solo Groups de negocio.

La infraestructura acepta temporalmente:

- Cero Groups de negocio: Usuario legacy/sin rol.
- Un Group de negocio: estado valido.
- Mas de un Group de negocio: estado inconsistente; `get_business_role()` lanza `InconsistentBusinessRoleError`.

`assign_business_role()` ya es atomico, bloquea la fila del Usuario, preserva Groups tecnicos, no modifica perfiles ni flags y limpia caches de permisos (`usuarios/roles.py:149-175`). Todavia no valida coherencia laboral, no recibe actor/motivo y no genera auditoria semantica.

### Esquema textual actual

```text
Usuario (identidad digital)
  email UNIQUE
  password hash
  is_active
  is_staff                  [legacy / Django Admin]
  is_superuser              [fuera del flujo normal]
  groups M2M
    0 BusinessRole          [legacy permitido temporalmente]
    1 BusinessRole          [valido]
    >1 BusinessRole         [inconsistente]
  user_permissions M2M

  |-- usuario.cliente (opcional desde Usuario)
  |     Cliente.usuario OneToOne, obligatorio, PK, CASCADE
  |     Cliente.activo
  |
  `-- usuario.perfil_profesional (opcional)
        Personal.usuario OneToOne, nullable, SET_NULL
        Personal.activo
        Personal.rol         [puesto legacy, no autorizacion]
        skills booleanos
        horarios / bloqueos / turnos asignados

Personal sin Usuario
  valido
  participa en operacion y agenda
  no puede autenticarse

Usuario con Cliente + Personal
  valido
  un solo rol de negocio
  ownership Cliente y capacidades laborales se evaluan por separado
```

## 2. FLUJOS EXISTENTES RELACIONADOS

| Flujo actual | Archivo / clase | Que hace hoy | Riesgo / limitacion |
|---|---|---|---|
| Registro publico | `usuarios/views.py:66-86`, `RegistroView`; `usuarios/serializers.py:194-316`, `RegistroSerializer` | Crea Usuario y Cliente en transaccion, hashea password y puede crear diagnostico | No asigna Group CLIENTE; `usuario.es_cliente=True` no es un campo persistido |
| Alta REST de Usuario | `gestion/serializers.py:634-651`, `UsuarioAdminSerializer.create`; `gestion/views.py:2512-2528`, `AdminUsuarioViewSet` | Crea Usuario; permite password, `is_staff` e `is_active` | No crea Cliente/Personal/rol; password sin politica; cualquier staff puede crear/promover staff |
| Edicion REST de Usuario | `gestion/serializers.py:653-661` | Edita email, nombres, `is_staff`, `is_active` y password | PATCH generico mezcla identidad, acceso y privilegios; no audita una operacion semantica |
| Baja REST de Usuario | `gestion/views.py:2530-2553` | DELETE hace soft delete de Usuario y tambien desactiva Cliente | Acopla cuenta y Cliente; no cambia Personal; validacion de turnos futuros no se limita al Usuario objetivo |
| Alta/edicion en Django Admin | `usuarios/admin.py:6-35`, `UsuarioAdmin` | Permite password, flags, Groups y permisos individuales | Puede asignar multiples roles, superuser o Groups sin pasar por helpers ni auditoria M2M |
| Activacion masiva | `usuarios/admin.py:60-84` | Usa `queryset.update()` sobre `is_active` y sincroniza Cliente | Bypassea senales de `Usuario`; reactiva/desactiva Cliente como efecto colateral; no toca Personal |
| Edicion de perfil propio | `usuarios/views.py:110-149`; `usuarios/serializers.py:94-185` | Edita nombres y datos de Cliente | Asume `usuario.cliente`; falla conceptualmente para Usuario laboral sin Cliente |
| CRUD REST de Personal | `gestion/views.py:417-461`, `PersonalViewSet`; `gestion/serializers.py:571-596` | Crea/edita Personal sin poder escribir `usuario`; escribe `activo`, `rol` y skills | Escrituras todavia dependen de `IsAdminUser`; DELETE puede borrar Personal; no gestiona acceso |
| Vinculacion desde Django Admin | `gestion/admin.py:330-358`, `PersonalAdmin` | Permite elegir, cambiar o quitar `Personal.usuario` | No valida rol, estado, Cliente, doble rol ni motivo; no cambia privilegios, pero tampoco audita semantica |
| Creacion implicita de Personal | `gestion/views.py:4678-4701`, `ContenidoEducativoViewSet.perform_create` | Si un staff/superuser sin Personal crea contenido, crea Personal `administrador` y lo vincula | Efecto colateral no aprobado; confunde autoria con alta laboral; reactiva conceptualmente sin confirmacion |
| Script legacy de staff | `gestion/fix_personal_staff.py` | Recorre Personal vinculados y marca Usuario `is_staff=True` | Elevacion masiva incompatible con el nuevo diseno; no debe volver a ejecutarse |
| Edicion de Cliente | `usuarios/admin.py:87-136`, `ClienteAdmin` | Edita datos y `Cliente.activo`; `usuario` es read-only | No es un flujo de creacion consistente; oculta clientes cuyo Usuario esta inactivo |
| Listado REST de Cliente | `usuarios/views.py:309-333`, `ClienteViewSet` | Solo lectura, filtra por `Usuario.is_active=True` | No filtra `Cliente.activo`; usa `IsAdminUser`, no el permiso nuevo |
| Creacion de password en manager | `usuarios/models.py:23-47`, `UsuarioManager` | Normaliza email, llama `set_password()` y guarda | Reutilizable; `create_user(password=None)` crea password inutilizable |
| Cambio de password REST admin | `gestion/serializers.py:638-660` | `set_password()` en create/update | Sin `validate_password`, confirmacion, motivo ni evento de seguridad |
| Solicitud de recuperacion | `usuarios/views.py:151-228` | Genera UID/token y envia email | URL localhost/HTTP; sin throttling; errores SMTP pueden revelar diferencias |
| Confirmacion de recuperacion | `usuarios/views.py:234-277`; `usuarios/serializers.py:319-329` | Valida token, llama `set_password()` | No revoca JWT existentes; no reactiva cuenta; password se excluye de auditoria y no hay evento semantico |
| Login propio | `usuarios/views.py:88-108`, `LoginView` | Busca email, usa `check_password()` y emite JWT | No comprueba explicitamente `is_active`; politica distinta de `/api/token/` |

No existe actualmente un flujo atomico y dedicado que cree acceso para Personal, vincule un Usuario existente, cambie un rol con auditoria o ejecute una baja laboral coherente.

## 3. CREAR ACCESO PARA PERSONAL

### Piezas reutilizables

| Necesidad | Pieza actual reutilizable | Observacion |
|---|---|---|
| Crear Usuario | `Usuario.objects.create_user()` | Normaliza email, llama `set_password()` y deja staff/superuser en false por defecto |
| Hashear password | `Usuario.set_password()` | Nunca persiste el texto claro |
| Vincular Usuario | `Personal.usuario` | OneToOne ya garantiza un Usuario por Personal y un Personal por Usuario |
| Asignar rol | `assign_business_role()` | Reemplaza solo Groups de negocio, preserva Groups tecnicos y flags |
| Transaccion | `transaction.atomic` y `select_for_update()` | El patron ya existe en registro y en `assign_business_role()` |
| Auditoria base | `Auditoria` | Puede almacenar actor, objetivo, antes/despues y motivo en JSON, pero debe escribirse explicitamente |

### Cambios de modelo

No se requiere un cambio obligatorio de modelo para crear acceso:

- Usuario ya tiene email, password, flags, Groups y permisos.
- Personal ya tiene el enlace nullable a Usuario.
- Cliente puede coexistir sin cambios.
- El rol ya se representa con Groups.

Una restriccion case-insensitive de email seria una mejora separada. `EmailField(unique=True)` y `normalize_email()` no garantizan por si solos unicidad ignorando mayusculas en toda la direccion. Para esta fase puede usarse busqueda `email__iexact`, normalizacion y captura de `IntegrityError`; una garantia absoluta case-insensitive requeriria una constraint de base de datos y, por tanto, una migracion posterior.

### Forma apropiada

El endpoint futuro mas natural es una accion dedicada sobre Personal:

```text
POST /api/gestion/personal/{personal_id}/crear-acceso/
```

Debe usar un serializer de comando, no `PersonalSerializer` ni `UsuarioAdminSerializer`:

```text
PersonalAccessCreateSerializer
  email
  password_temporal (write_only)
  role: EMPLEADO | PROFESIONAL | ADMINISTRADOR
  motivo
```

La accion pertenece a `PersonalViewSet` porque el recurso objetivo es un Personal existente. La logica no debe vivir en la view ni en `Serializer.create()`: debe delegarse a un servicio dedicado que coordine `gestion` y `usuarios`.

No conviene reutilizar `RegistroSerializer`: crea Cliente, puede crear Diagnostico y ejecuta logica de gestion. El alta de acceso laboral no debe crear ni modificar Cliente.

### Validaciones obligatorias

1. El actor tiene `gestion.manage_personal` y `usuarios.assign_roles`.
2. El Personal existe y se bloquea con `select_for_update()`.
3. El Personal esta activo para otorgar acceso laboral inmediato.
4. El Personal no tiene Usuario vinculado.
5. El email esta normalizado y no existe, incluyendo busqueda case-insensitive.
6. Si el email existe, no crear: devolver conflicto y dirigir al flujo de vinculacion.
7. El rol solicitado es EMPLEADO, PROFESIONAL o ADMINISTRADOR; nunca CLIENTE en esta accion.
8. EMPLEADO es coherente con el puesto laboral definido para asistentes.
9. PROFESIONAL es coherente con el puesto tecnico definido para coloristas.
10. ADMINISTRADOR puede vincularse al Personal sin adquirir bypass tecnico.
11. Password cumple validadores y nunca aparece en respuesta, auditoria o logs.
12. El payload no acepta `is_staff`, `is_superuser`, `groups`, `user_permissions`, `is_active` ni datos de Cliente.
13. Usuario se crea explicitamente con `is_staff=False`, `is_superuser=False`, `is_active=True`.
14. Vinculacion, rol y auditoria se confirman o revierten juntos.

### Resultado esperado

```text
Usuario nuevo
  password hasheado
  is_active=True
  is_staff=False
  is_superuser=False
  un unico Group laboral

Personal existente
  usuario=<nuevo Usuario>
  activo sin cambio
  rol/skills sin cambio

Cliente
  no creado
  no modificado si ya existiera por otra ruta
```

## 4. VINCULAR USUARIO EXISTENTE

### Unicidad y resolucion por email

`Usuario.email` es unico y es `USERNAME_FIELD` (`usuarios/models.py:51-55`). El flujo debe buscar por email normalizado con comparacion case-insensitive. No debe intentar crear primero y resolver el choque despues como flujo normal; aun asi debe capturar `IntegrityError` por concurrencia.

Se recomienda separar claramente:

```text
POST /api/gestion/personal/{id}/vincular-usuario/
```

Entrada: `usuario_id` o email, confirmacion administrativa y motivo. Si se usa email, la respuesta no debe exponer datos de cuentas a actores sin permisos.

### Comportamiento exacto propuesto

| Situacion | Comportamiento | Codigo |
|---|---|---:|
| Personal y Usuario existen, ambos libres | Vincular solamente; no cambiar flags, password, rol ni perfiles | 200 |
| Ya existe exactamente el mismo vinculo | Respuesta idempotente `changed=false` | 200 |
| Personal ya tiene otro Usuario | Rechazar `PERSONAL_ALREADY_LINKED` | 409 |
| Usuario ya esta vinculado a otro Personal | Rechazar `USER_ALREADY_LINKED_TO_PERSONAL` | 409 |
| Email no existe | Rechazar `USER_NOT_FOUND`; usar crear acceso si corresponde | 404 |
| Personal no existe | Rechazar `PERSONAL_NOT_FOUND` | 404 |
| Usuario tiene Cliente | Conservar Cliente sin modificaciones | 200 |
| Usuario inactivo | Permitir preparar el vinculo, pero conservar `is_active=False` y devolver advertencia; reactivacion debe ser otra accion | 200 |
| Usuario sin rol | Vincular y mantenerlo sin rol hasta la accion dedicada de asignacion | 200 |
| Usuario con CLIENTE | Vincular y conservar CLIENTE hasta un cambio de rol explicito | 200 |
| Usuario con EMPLEADO/PROFESIONAL coherente con el Personal | Permitir vinculo; no reescribir rol | 200 |
| Usuario con rol laboral incompatible con Personal | Rechazar `ROLE_PERSONAL_MISMATCH` | 409 |
| Usuario con ADMINISTRADOR | Permitir; Personal sigue siendo opcional para administracion | 200 |
| Usuario con mas de un rol de negocio | Rechazar `INCONSISTENT_BUSINESS_ROLES` | 409 |
| Usuario es superuser | Rechazar su gestion por esta API normal; requiere procedimiento tecnico separado | 403 |

### Confirmacion administrativa

La vinculacion debe requerir una confirmacion explicita en el payload o en la UI futura, pero la seguridad real es backend:

- Actor con `gestion.manage_personal`.
- Para vincular una identidad con privilegios existentes, tambien `usuarios.assign_roles` o una politica equivalente.
- Motivo obligatorio.
- Bloqueo de Usuario y Personal en la misma transaccion.
- Auditoria semantica antes/despues.

Vincular no debe activar automaticamente Usuario ni Personal. Tampoco debe asignar un rol. Esas operaciones separadas evitan reactivaciones silenciosas y hacen cada cambio auditable.

## 5. CAMBIO DE ROL

### Infraestructura reutilizable

Puede reutilizarse directamente:

- `BusinessRole.ALL` para validar nombres.
- `get_business_roles()` para leer todos los roles actuales.
- `get_business_role()` para obtener cero/uno y fallar ante multiples.
- `has_inconsistent_business_roles()` para diagnostico explicito.
- `assign_business_role()` como primitiva de reemplazo atomico.

`assign_business_role()` ya garantiza que:

- Queda un unico Group de negocio.
- Se conservan Groups tecnicos.
- No cambia `is_staff`, `is_superuser`, Cliente ni Personal.
- Se limpian caches de permisos en la instancia recibida.

### Validaciones faltantes

La primitiva actual valida solamente que el nombre pertenezca al catalogo. Una capa de aplicacion debe agregar:

| Rol destino | Validacion propuesta |
|---|---|
| CLIENTE | El Usuario tiene `usuario.cliente`; Personal puede seguir vinculado, pero las capacidades laborales dejan de provenir del rol |
| EMPLEADO | Existe `usuario.perfil_profesional`, esta vinculado al Usuario y el puesto es coherente con funcion de asistente; para acceso laboral efectivo debe estar activo |
| PROFESIONAL | Existe `usuario.perfil_profesional`, esta vinculado al Usuario y el puesto es coherente con funcion tecnica/colorista; para acciones debe estar activo |
| ADMINISTRADOR | Personal no es obligatorio; si realiza tareas tecnicas, las acciones posteriores deben exigir Personal activo, asignacion y skill |

Ademas:

- Actor debe tener `usuarios.assign_roles`.
- Superusuarios no deben administrarse por el flujo normal.
- Motivo obligatorio.
- Debe protegerse la ultima cuenta administrativa efectiva cuando se implemente la operacion real.
- Cambiar al mismo rol debe ser idempotente y no generar remove/add innecesario.
- Un Usuario inactivo puede recibir un rol preparado, pero esto no debe reactivarlo.

### API futura

```text
POST /api/gestion/admin/usuarios/{id}/asignar-rol/
```

La operacion debe cambiar solo el Group de negocio. Debe preservar:

- Password.
- `is_staff`.
- `is_superuser`.
- `is_active`.
- Cliente.
- Personal.
- `Personal.activo`, `Personal.rol` y skills.
- Groups tecnicos y permisos individuales.

### Auditoria M2M

La auditoria actual no captura cambios de Groups:

- Los snapshots recorren `instance._meta.fields`, no M2M (`gestion/signals.py:19-60`).
- Cambiar `user.groups` no ejecuta `Usuario.save()`.
- No existe receptor `m2m_changed`.
- Usuario no tiene `HistoricalRecords`.

No se recomienda depender solo de `m2m_changed`: una asignacion produce remove/add separados y la senal no conoce necesariamente actor, motivo ni intencion. La accion dedicada debe registrar un unico evento semantico dentro de la misma transaccion:

```text
tipo: BUSINESS_ROLE_CHANGED
actor
target_user
previous_role
new_role
removed_groups
added_group
reason
source
timestamp / ip / correlation_id cuando exista
```

La edicion directa de Groups en Django Admin debe restringirse o delegar a la misma operacion; de lo contrario seguira siendo una via de bypass.

## 6. DESACTIVACION Y BAJA LABORAL

### Diferencia de estados

- `Personal.activo=False`: no trabaja o no esta habilitado para tareas laborales. No implica perder identidad digital.
- `Usuario.is_active=False`: no debe autenticarse ni renovar/usar acceso. No implica borrar perfil laboral o comercial.
- `Cliente.activo`: estado comercial del Cliente; no debe cambiar automaticamente por una baja laboral.

### Reglas propuestas

#### A. Deja de trabajar pero sigue como Cliente

En una unica operacion de revocacion laboral:

1. Exigir que exista Cliente.
2. Bloquear Usuario y Personal.
3. Establecer `Personal.activo=False`.
4. Mantener `Personal.usuario` para trazabilidad.
5. Asignar rol CLIENTE.
6. Mantener `Usuario.is_active=True`.
7. No cambiar `Cliente.activo`, password, `is_staff` ni `is_superuser`.
8. Registrar motivo, rol anterior y estado anterior/nuevo.

El Usuario conserva ownership de Cliente y pierde permisos base laborales.

#### B. Deja de trabajar y pierde todo acceso

1. Establecer `Personal.activo=False`.
2. Mantener el vinculo para historial.
3. Establecer `Usuario.is_active=False`.
4. No borrar perfiles ni password.
5. No reactivar/desactivar Cliente como efecto colateral.
6. Conservar el rol actual como estado dormido o cambiarlo mediante una accion de rol separada, segun la politica final; la seguridad inmediata proviene de `is_active=False`.
7. Invalidar o poner en blacklist refresh tokens cuando se implemente.

Conservar temporalmente el rol facilita una futura reactivacion y mantiene contexto, pero la reactivacion de la cuenta debe volver a validar coherencia. Si se decide exigir coherencia absoluta aun para cuentas inactivas, entonces la misma operacion debera demover a CLIENTE cuando exista Cliente o dejar cero roles de manera explicita y auditada. No debe decidirse silenciosamente.

#### C. Personal sin Usuario

- Establecer solo `Personal.activo=False`.
- No crear Usuario para ejecutar una baja.
- Conservar horarios, asignaciones e historicos.
- Reactivar Personal no crea acceso digital.

#### D. Usuario laboral sin Cliente

- Si deja de trabajar y pierde acceso: `Personal.activo=False`, `Usuario.is_active=False`.
- No puede cambiarse a CLIENTE porque no existe Cliente.
- No crear Cliente como efecto colateral de la baja.
- Si solo cambia de funcion, usar cambio de rol y conservar cuenta activa cuando corresponda.

#### E. Reactivacion posterior

La reactivacion debe dividirse en acciones explicitas:

- Reactivar Personal: cambia solo `Personal.activo=True`.
- Reactivar Usuario: cambia solo `Usuario.is_active=True`, despues de validar el rol actual.
- Restaurar rol laboral: accion de rol dedicada si fue cambiado o retirado.

Reglas:

- Reactivar Personal no reactiva Usuario.
- Reactivar Usuario no reactiva Personal.
- Si Usuario tiene EMPLEADO/PROFESIONAL y Personal sigue inactivo o ausente, reactivar cuenta debe responder 409 hasta corregir la coherencia o elegir otro rol.
- Si Usuario tiene CLIENTE, debe existir Cliente.
- Ningun `save()` de otra entidad debe reactivar silenciosamente estos estados.

### Riesgo de borrar Personal

El DELETE actual puede hacer hard delete cuando no hay turnos activos (`gestion/views.py:437-461`). Esto es incompatible con una baja laboral conservadora:

- `Turno.profesional` usa `SET_NULL`; los turnos historicos pierden la referencia viva al profesional (`gestion/models.py:1354-1360`).
- `HorarioLaboral.personal` usa `CASCADE`; se eliminan horarios (`gestion/models.py:1245-1255`).
- `BloqueoAgenda.personal` usa `CASCADE`; se eliminan bloqueos (`gestion/models.py:1288-1298`).
- `ContenidoEducativo.autor` usa `PROTECT`; contenido existente puede impedir la eliminacion (`gestion/models.py:1627-1633`).
- Simple History conserva snapshots de Personal, pero no reemplaza relaciones vivas ni consultas operativas.

La baja laboral futura debe usar `Personal.activo=False` y no DELETE. La eliminacion fisica debe reservarse, si se mantiene, para datos creados por error y sin relaciones, mediante procedimiento excepcional.

## 7. CONTRASENA TEMPORAL

### Flujo actual reutilizable

- `UsuarioManager.create_user()` llama `set_password()` y guarda un hash (`usuarios/models.py:23-36`).
- `Usuario.set_password()` puede utilizarse para una contrasena inicial administrada.
- `RegistroSerializer` muestra como aplicar `validate_password()` antes de crear.
- La recuperacion actual genera token Django y permite establecer una nueva contrasena (`usuarios/views.py:151-277`).
- Los serializers de password usan `write_only`.

### Implementacion segura sin texto claro persistido

1. El admin envia la contrasena temporal por un campo `write_only` en la accion de crear acceso.
2. El backend valida fortaleza con `validate_password(password, user)` usando contexto del Usuario.
3. Se llama `set_password()` o `create_user(password=...)`.
4. El texto claro no se guarda en ningun modelo.
5. La respuesta no devuelve password, ni siquiera parcialmente.
6. La auditoria registra `credential_initialized=true`, nunca valor ni hash.
7. No incluir `request.data`, serializers completos o excepciones con payload en logs.
8. La entrega al usuario ocurre por un canal administrativo seguro; si el sistema la genera, debe mostrarse/enviarse una sola vez fuera de la persistencia.

### Hace falta `must_change_password` ahora

**No es obligatorio para el primer flujo aprobado.** Puede crearse una contrasena inicial hasheada y el usuario puede cambiarla mediante recuperacion. Sin campo adicional, sin embargo, "temporal" es una convencion operativa: la contrasena seguira funcionando hasta que el usuario la cambie.

Si el requisito futuro pasa a ser "forzar cambio en el primer login" o "expirar la contrasena", entonces si harian falta estado adicional y flujo propio, por ejemplo:

- `must_change_password`.
- Opcionalmente `temporary_password_expires_at`.
- Endpoint autenticado de cambio de password.
- Restriccion de navegacion hasta completar el cambio.

No conviene agregar esos campos en la primera implementacion si la obligacion de cambio forzado no esta aprobada.

### Sirve la recuperacion actual

Sirve como base funcional porque usa tokens Django y `set_password()`, pero debe endurecerse antes de considerarla un flujo completo de seguridad:

- URL de frontend configurable y HTTPS, no `http://localhost:3000`.
- Throttling para solicitud y confirmacion.
- Politica explicita para Usuario inactivo.
- Mensajes que no filtren excepciones SMTP.
- Revocacion/blacklist de tokens JWT despues del cambio.
- Validacion de password con contexto del Usuario.
- Evento de auditoria de cambio de credencial sin valor sensible.

### Riesgos actuales de seguridad y logging

- `UsuarioAdminSerializer` no aplica `validate_password()`.
- Password admin omitida crea una cuenta con password inutilizable, sin comunicarlo claramente.
- Login propio no comprueba `is_active` antes de emitir tokens.
- Cambiar password no revoca JWT existentes.
- La auditoria excluye correctamente `password`, pero por eso tampoco produce un evento claro de cambio de credencial.
- El frontend registra objetos Axios de error; estos pueden contener payloads con passwords o tokens.
- Login imprime fragmentos de JWT en consola.
- El reset token viaja en URL y puede quedar en historial/referrers.
- Existen credenciales de pruebas/configuracion en el workspace; no deben reutilizarse ni documentarse en este archivo.

## 8. OPERACIONES/API PROPUESTAS

Estas operaciones deben ser acciones dedicadas. Los cambios sensibles no deben exponerse mediante PATCH generico.

| Accion | Actor autorizado | Precondiciones | Cambios de datos | Auditoria | Errores posibles |
|---|---|---|---|---|---|
| Crear acceso para Personal | `manage_personal` + `assign_roles` | Personal activo, sin Usuario; email nuevo; rol laboral/admin valido; password valida | Crear Usuario no staff/no superuser; vincular; asignar rol | Actor, Personal, Usuario, rol, motivo; nunca password | 400 payload/password/rol; 403; 404 Personal; 409 email o vinculo |
| Vincular Usuario existente | `manage_personal` + `assign_roles` | Ambos existen; ninguno vinculado a otro; roles consistentes | Solo `Personal.usuario`; no activar ni cambiar rol | IDs, email snapshot, antes/despues, motivo | 403; 404; 409 doble vinculo/roles multiples/mismatch |
| Asignar o cambiar rol | `assign_roles` | Rol valido; perfiles coherentes; no superuser normal; motivo | Solo Group de negocio mediante helper | Rol anterior/nuevo, Groups removidos/agregado, actor, motivo | 400; 403; 404; 409 perfil/inconsistencia/ultimo admin |
| Desactivar Personal | `manage_personal` | Personal activo; politica de trabajo pendiente resuelta posteriormente | `Personal.activo=False` | Estado anterior/nuevo y motivo | 403; 404; 409 ya inactivo o dependencias operativas |
| Revocar acceso laboral y conservar Cliente | `manage_personal` + `assign_roles` | Personal y Cliente existentes | Personal inactivo; rol CLIENTE; Usuario activo | Evento compuesto unico | 403; 404; 409 falta Cliente/inconsistencia |
| Desactivar cuenta | `manage_users` | Usuario activo; no superuser normal; proteccion de ultimo admin | `Usuario.is_active=False`; blacklist de refresh tokens | Actor, objetivo, motivo, estado | 403; 404; 409 ya inactivo/ultimo admin |
| Reactivar Personal | `manage_personal` | Personal inactivo | Solo `Personal.activo=True` | Antes/despues, motivo | 403; 404; 409 ya activo |
| Reactivar cuenta | `manage_users` | Usuario inactivo; rol/perfiles coherentes | Solo `Usuario.is_active=True`; no restaura tokens | Antes/despues, motivo | 403; 404; 409 rol incoherente |
| Desvincular Usuario | `manage_personal` + `assign_roles` | Personal inactivo; sin rol laboral activo o cuenta desactivada; confirmacion | `Personal.usuario=NULL` | Usuario/Personal, razon, estado previo | 403; 404; 409 estado laboral o trabajo pendiente |
| Inicializar/cambiar password administrativo | `manage_users` y politica reforzada | Usuario valido; password fuerte; reautorizacion del actor si se exige | Solo hash de password; revocar tokens | Evento sin password/hash | 400; 403; 404; 409 cuenta protegida |

Recomendacion de nombres de acciones DRF futuras:

```text
PersonalViewSet.crear_acceso
PersonalViewSet.vincular_usuario
PersonalViewSet.desvincular_usuario
PersonalViewSet.desactivar
PersonalViewSet.reactivar
PersonalViewSet.revocar_acceso_laboral

AdminUsuarioViewSet.asignar_rol
AdminUsuarioViewSet.desactivar_cuenta
AdminUsuarioViewSet.reactivar_cuenta
```

Las respuestas deben exponer estado, IDs, rol y warnings, pero nunca password, hash, tokens ajenos ni permisos no necesarios.

## 9. SERVICIOS INTERNOS

### Division recomendada

`usuarios/roles.py` debe permanecer como vocabulario y primitiva de bajo nivel:

- Consulta de roles.
- Deteccion de inconsistencia.
- Reemplazo atomico de Group.

Se recomienda una capa de aplicacion por encima.

#### `usuarios/access_services.py`

Responsabilidades propuestas:

```text
assign_validated_business_role(actor, user, role, reason)
deactivate_account(actor, user, reason)
reactivate_account(actor, user, reason)
initialize_password(actor, user, raw_password, reason)
revoke_user_tokens(user)
```

Debe validar perfiles/rol, proteger superusers/ultimo admin, coordinar auditoria y no depender de DRF.

#### `gestion/personal_access_services.py`

Responsabilidades propuestas:

```text
create_access_for_personal(actor, personal, email, raw_password, role, reason)
link_user_to_personal(actor, personal, user, reason)
unlink_user_from_personal(actor, personal, reason)
revoke_work_access(actor, personal, keep_client_access, reason)
deactivate_personal(actor, personal, reason)
reactivate_personal(actor, personal, reason)
```

Debe coordinar modelos de `gestion` con las primitivas de `usuarios`.

### Por que no en views/serializers

- Una view debe autenticar, autorizar, invocar el servicio y traducir excepciones a HTTP.
- Un serializer de comando debe validar forma/tipos, no decidir estados de negocio ni ejecutar varias escrituras sensibles.
- El mismo servicio debe poder reutilizarse desde API, Django Admin o futuros comandos sin duplicar reglas.
- La auditoria obligatoria y los locks deben vivir cerca de la mutacion, no depender del caller.

### Modulo existente

`gestion/services.py` ya agrupa disponibilidad, salud capilar y Mercado Pago. Agregar alli gestion de identidad aumentaria el acoplamiento. Un modulo pequeno `personal_access_services.py` es mas claro y evita refactorizar el archivo grande.

Las excepciones deben ser de dominio, por ejemplo:

```text
PersonalAlreadyLinked
UserAlreadyLinked
EmailAlreadyExists
InvalidBusinessRoleState
RolePersonalMismatch
ProtectedSuperuser
AccountStateConflict
```

Las views traducen esas excepciones a 400/403/404/409.

## 10. TRANSACCIONES E INTEGRIDAD

### Operaciones que requieren `transaction.atomic`

| Operacion | Filas a bloquear | Motivo |
|---|---|---|
| Crear acceso | Personal; comprobacion/creacion de Usuario; Groups | Evitar Usuario huerfano, doble vinculo o rol parcial |
| Vincular existente | Personal y Usuario | Evitar dos administradores vinculando simultaneamente |
| Cambiar rol | Usuario y, para rol laboral, Personal | Validar y reemplazar contra un estado estable |
| Revocar acceso laboral | Usuario y Personal | Coordinar estado laboral, rol y cuenta con un evento unico |
| Desactivar/reactivar cuenta | Usuario; posiblemente rol/Personal para validar | Evitar reactivar una combinacion incoherente |
| Desvincular | Usuario y Personal | Evitar unlink mientras cambia rol o estado |
| Inicializar password + crear cuenta | Usuario/Personal en transaccion exterior | Evitar cuenta activa incompleta |

Las filas deben bloquearse en orden consistente para reducir deadlocks. Una regla viable es bloquear primero Usuario cuando existe y luego Personal; en creacion, bloquear Personal antes de crear Usuario y documentar ese orden para todos los servicios.

Emails y notificaciones externas deben enviarse con `transaction.on_commit()`. Nunca deben mantener abierta la transaccion esperando SMTP.

### Riesgos concretos

#### Crear Usuario y fallar al vincular

Sin atomicidad queda una cuenta activa sin Personal o rol. La transaccion debe revertir Usuario, vinculo, Group y auditoria juntos.

#### Asignar rol parcialmente

`assign_business_role()` ya encapsula remove/add. La capa superior debe incluir captura de rol anterior, validacion y auditoria en una transaccion exterior comun.

#### Duplicar email

Dos requests pueden superar una comprobacion previa. Debe existir `unique=True`, captura de `IntegrityError` y respuesta 409. Para igualdad case-insensitive estricta se necesita una constraint futura.

#### Doble vinculacion

El OneToOne protege en base de datos, pero la experiencia requiere locks y errores 409 estables, no exponer un `IntegrityError`.

#### Desactivar Personal sin ajustar rol

No siempre es un error: una cuenta tambien puede quedar inactiva. La invariante debe distinguir capacidad potencial de capacidad efectiva. Ninguna accion laboral debe autorizarse si `Personal.activo=False`, aunque el Group siga presente.

#### Reactivar cuenta incoherente

Antes de `Usuario.is_active=True`:

- CLIENTE requiere Cliente.
- EMPLEADO/PROFESIONAL requieren Personal vinculado y activo.
- ADMINISTRADOR puede no tener Personal.
- Multiples roles impiden reactivacion.

### Invariantes propuestas

1. Un Personal tiene cero o un Usuario; un Usuario tiene cero o un Personal.
2. Cliente y Personal pueden coexistir en el mismo Usuario.
3. Vincular/desvincular nunca cambia privilegios por si solo.
4. Todo Usuario gestionado por el sistema nuevo tiene como maximo un rol de negocio.
5. EMPLEADO/PROFESIONAL activos requieren Personal vinculado y activo para operar laboralmente.
6. ADMINISTRADOR puede existir sin Personal; acciones tecnicas requieren Personal activo/asignacion/skill.
7. CLIENTE requiere perfil Cliente cuando se asigne como rol normal.
8. `is_staff` e `is_superuser` no cambian en flujos de negocio.
9. Personal no se borra para una baja laboral.
10. Reactivaciones son explicitas y no se encadenan por side effects.
11. Password nunca aparece en respuestas, auditoria o logs.
12. Toda mutacion sensible y su auditoria se confirman o revierten juntas.

No existe una constraint SQL simple que limite una M2M a uno de cuatro Groups. La garantia depende de canalizar todas las escrituras por servicios y restringir edicion directa en Django Admin.

## 11. AUDITORIA

### Cobertura actual

La auditoria generica registra altas, modificaciones y bajas de Usuario, Cliente y Personal mediante `pre_save`, `post_save` y `pre_delete` (`gestion/signals.py:85-229`). Excluye `password` y `refresh_token` de snapshots (`gestion/signals.py:19-33`). Personal tambien usa Simple History.

Limitaciones:

- No captura Groups ni `user_permissions` M2M.
- `queryset.update()` del Django Admin no dispara `save()`.
- Un cambio solo de password no deja un evento semantico porque password se excluye.
- `registrar_auditoria()` atrapa errores y permite que la operacion principal continue sin auditoria (`gestion/signals.py:63-79`).
- El cache global de valores anteriores no es seguro frente a concurrencia sobre el mismo registro.
- El middleware thread-local no limpia contexto en `finally` (`gestion/middleware.py:44-76`).
- Django Admin puede editar Groups directamente sin pasar por servicios.

### Eventos requeridos

| Evento | Datos minimos |
|---|---|
| Creacion de acceso | Actor, Usuario creado, Personal vinculado, rol inicial, estado de cuenta, motivo |
| Vinculacion | Actor, Usuario, Personal, vinculo anterior/nuevo, motivo |
| Cambio de rol | Actor, objetivo, rol anterior/nuevo, Groups removidos/agregado, motivo |
| Baja laboral | Actor, Personal, `activo` anterior/nuevo, decision sobre cuenta/rol, motivo |
| Desactivacion de cuenta | Actor, Usuario, `is_active` anterior/nuevo, revocacion de tokens, motivo |
| Reactivacion | Actor, entidad, estado anterior/nuevo, validaciones superadas, motivo |
| Cambio de credencial | Actor o autoservicio, Usuario, tipo de operacion y resultado; nunca password/hash/token |

### Uso posible del modelo actual

No es obligatorio crear un modelo nuevo en la primera fase. `Auditoria` puede almacenar eventos semanticos usando:

```text
tabla = "PersonalAccess" o "UsuarioBusinessRole"
registro_id = id del objetivo principal
usuario = actor
accion = MODIFICACION / ALTA segun corresponda
valor_anterior = snapshot de estado relevante
valor_nuevo = snapshot + reason + source + actor_email_snapshot
```

Para operaciones de seguridad, la escritura debe hacerse directamente en el servicio y no mediante `registrar_auditoria()` mientras este silencie excepciones. Si la auditoria falla, la mutacion debe hacer rollback.

No deben auditarse:

- Password en claro.
- Hash de password.
- Token de reset.
- Access/refresh JWT.
- Payload HTTP completo.

Un `m2m_changed` puede servir como detector de bypass, pero no reemplaza el evento semantico de la operacion dedicada.

## 12. IMPACTO EN FRONTEND FUTURO

### GestionPersonal

Hoy crea/edita Personal sin Usuario y permite DELETE (`frontend/src/pages/admin/GestionPersonal.js:12-125`). Futuramente necesitara:

- Mostrar si existe Usuario vinculado.
- Mostrar email, rol de negocio, `Usuario.is_active` y `Personal.activo` como estados distintos.
- Accion "Crear acceso".
- Accion "Vincular cuenta existente" con confirmacion.
- Accion "Cambiar rol" separada.
- Acciones "Desactivar Personal" y "Reactivar Personal".
- Accion compuesta "Deja de trabajar, conserva acceso Cliente".
- Eliminar o esconder DELETE normal para bajas laborales.
- No enviar `usuario`, Groups ni flags por el formulario generico.

### GestionUsuarios

Hoy filtra y edita por `is_staff`, crea passwords y cambia `is_active` con PATCH (`frontend/src/pages/admin/GestionUsuarios.js:12-140`). Futuramente necesitara:

- Sustituir Cliente/Staff por rol Group.
- Eliminar checkbox `is_staff` del flujo de negocio.
- Mostrar perfiles Cliente/Personal coexistentes.
- Usar acciones dedicadas para rol, desactivacion y reactivacion.
- Mostrar advertencias de coherencia sin permitir PATCH generico.
- No volver a mostrar una contrasena temporal despues del envio.

### Login

Hoy redirige segun `is_staff` y almacena tokens antes de validar perfil (`frontend/src/pages/auth/Login.js:49-110`). Futuramente necesitara:

- Redirigir por rol/capacidades del contrato `/me`, no por staff.
- Mostrar estado de cuenta desactivada de forma segura.
- Manejar recuperacion/cambio de password inicial.
- Eliminar logs de fragmentos de tokens y errores que puedan contener credenciales.

### Recuperacion de contrasena

`RecuperarContrasena.js` y `ResetearClave.js` pueden conservar su objetivo, pero requeriran:

- URLs configurables.
- Manejo correcto de errores de validacion.
- Limpieza/revocacion de sesiones despues del cambio.
- Mensajes de enlace vencido y cuenta inactiva.
- Evitar logs de objetos Axios completos.

### Seguridad backend frente a UX

- Backend debe validar actor, estado, rol, vinculo, transaccion y auditoria.
- Frontend solo muestra capacidades y confirmaciones.
- Ocultar botones no protege endpoints.
- Manipular `localStorage`, `is_staff` o estado React nunca debe conceder una operacion.

## 13. CAMBIOS DE MODELO NECESARIOS

### Usuario

**No hace falta modificar Usuario para la primera implementacion.** Ya dispone de:

- Email unico.
- Password hasheado.
- `is_active`.
- Groups y permisos individuales.
- Flags tecnicos existentes que deben preservarse.

Mejoras opcionales posteriores:

- Constraint de email case-insensitive.
- Campos de cambio forzado/expiracion solo si se aprueba ese requisito.

### Personal

**No hace falta modificar Personal.** Ya permite:

- Existir sin Usuario.
- Vincular un Usuario con OneToOne.
- Expresar actividad laboral.
- Conservar puesto y skills actuales.
- Historial mediante Simple History.

### Campos adicionales

**No se necesita agregar campos obligatorios** para crear/vincular acceso, asignar rol, dar de baja o reactivar.

### `must_change_password`

**No hace falta ahora** si la politica aceptada es contrasena inicial + recuperacion voluntaria. Si se exige cambio forzado en primer login, entonces debe agregarse junto con un flujo completo; agregar solo el booleano produciria cuentas bloqueadas sin una salida segura.

### Historial adicional

**No hace falta una tabla historica nueva para comenzar**, siempre que las operaciones dedicadas creen eventos semanticos obligatorios en `Auditoria`. La auditoria generica y Simple History no son suficientes por si solas para Groups M2M.

### Resumen

| Pregunta | Respuesta |
|---|---|
| Modificar Usuario | No para el alcance base |
| Modificar Personal | No |
| Agregar campos | No obligatoriamente |
| Agregar `must_change_password` | No ahora; solo con cambio forzado aprobado |
| Agregar historial | No tabla nueva inicialmente; si auditoria semantica explicita |
| Agregar migraciones | No para los primeros servicios/API; solo para mejoras opcionales |

## 14. ORDEN DE IMPLEMENTACION RECOMENDADO

| Paso | Archivos probables | Riesgo | Dependencia | Criterio de terminado |
|---|---|---|---|---|
| 1. Wrapper validado y auditado de rol | Nuevo `usuarios/access_services.py`, `usuarios/roles.py` solo si se requiere ajustar retorno/no-op, tests de usuarios | Medio por privilegios | Infraestructura de Groups existente | Cambia solo un Group, valida perfiles, preserva flags/perfiles, crea un evento atomico y cubre multiples roles/no-op |
| 2. Servicio de vinculacion existente | Nuevo `gestion/personal_access_services.py`, tests | Medio | Paso 1 para validar estado de rol | Locks de Usuario/Personal, conserva Cliente, rechaza doble vinculo, no cambia privilegios y audita |
| 3. Accion API de vinculacion | `gestion/serializers.py` con serializer de comando pequeno, `PersonalViewSet`, tests API | Medio | Paso 2 | Actor autorizado, contratos 200/403/404/409, sin PATCH de `usuario` |
| 4. Servicio de crear acceso | `personal_access_services.py`, serializer de comando, tests | Alto acotado | Pasos 1-2 | Usuario+vinculo+rol+auditoria atomicos; password write-only; email existente no duplica; sin Cliente/flags |
| 5. Accion API crear acceso | `PersonalViewSet`, tests API | Medio | Paso 4 | Endpoint dedicado funciona para EMPLEADO/PROFESIONAL/ADMINISTRADOR y rechaza campos sensibles |
| 6. Baja/reactivacion de Personal | Servicio, acciones `desactivar/reactivar/revocar_acceso_laboral`, tests | Alto por estados | Pasos 1-2 | No hay DELETE laboral; escenarios Cliente/no Cliente quedan coherentes; reactivacion no tiene side effects |
| 7. Estado de cuenta y credenciales | `usuarios/access_services.py`, `AdminUsuarioViewSet`, login/reset, tests | Alto | Auditoria del paso 1 | Acciones dedicadas reemplazan PATCH de `is_active/password`; login rechaza inactivos; tokens se revocan donde corresponda |
| 8. Cerrar vias de bypass backend | `UsuarioAdmin`, `PersonalAdmin`, serializers genericos, script legacy | Alto | Servicios y APIs estables | Django Admin delega/restringe Groups; no se escribe staff/rol/vinculo por rutas genericas; script no se usa |
| 9. Integracion frontend puntual | `GestionPersonal`, `GestionUsuarios`, Login y recuperacion | Medio | Endpoints y `/me` estables | UI usa acciones dedicadas y estados separados; no decide seguridad |

Cada paso debe incluir pruebas negativas de privilegios y rollback. No debe mezclarse con turnos, stock, pagos o nuevos skills.

## 15. PRIMER CAMBIO RECOMENDADO

La primera implementacion real debe ser un **servicio interno de asignacion de rol validada y auditada**, sin endpoint ni frontend:

```text
assign_validated_business_role(
    actor,
    target_user,
    target_role,
    reason,
)
```

### Alcance

- Reutiliza `assign_business_role()`.
- Bloquea Usuario y lee rol anterior dentro de `transaction.atomic`.
- Rechaza multiples roles actuales.
- Valida Cliente para CLIENTE.
- Valida Personal vinculado/coherente para EMPLEADO y PROFESIONAL.
- Permite ADMINISTRADOR sin Personal.
- No cambia flags, password ni perfiles.
- Registra un unico evento semantico M2M en la misma transaccion.
- Es idempotente cuando el rol ya coincide.

### Por que primero

- Crear acceso, vincular con rol, baja Cliente y reactivacion dependen de una transicion de rol segura.
- Cierra la brecha de auditoria M2M antes de exponer nuevas APIs.
- Es pequena y comprobable solo con tests de servicio.
- No toca frontend, turnos ni el CRUD generico.
- Permite que los pasos siguientes compongan una primitiva comun en vez de duplicar validaciones.

### Tests minimos

- EMPLEADO/PROFESIONAL sin Personal: rechazo y sin cambios.
- Personal incompatible/inactivo: rechazo segun politica final.
- ADMINISTRADOR sin Personal: permitido.
- CLIENTE sin Cliente: rechazo.
- Groups tecnicos, `user_permissions`, flags y perfiles: preservados.
- Dos roles actuales: rechazo.
- Cambio valido: un solo rol y un evento de auditoria.
- Fallo de auditoria: rollback del Group.
- Mismo rol: no-op controlado.

## 16. FUERA DE ALCANCE

- Nuevo catalogo `Habilidad`.
- Cambios de skills booleanos actuales.
- Reglas de asignacion tecnica a turnos.
- Refactor de `TurnoViewSet`.
- Disponibilidad, horarios o algoritmo de agenda, salvo preservar relaciones.
- Pagos, senas y caja.
- Mercado Pago, webhooks, checkout o URLs de retorno.
- Stock, productos, precios y promociones.
- Diagnosticos, fichas tecnicas, formulas y rutinas.
- Contenido educativo, salvo documentar su side effect actual.
- Migracion general de endpoints desde `IsAdminUser`.
- Eliminacion de `is_staff` o `is_superuser`.
- Backfill de usuarios legacy.
- Inferencia de rol desde `Personal.rol`.
- Asignacion automatica de ADMINISTRADOR a staff.
- Rediseno completo del frontend.
- Nuevo contrato `/me`, salvo como dependencia futura de UI.
- Cambio completo de estrategia JWT/localStorage.
- Refactor general de auditoria o middleware fuera de los eventos de acceso.
- Hard delete o limpieza de datos historicos existentes.
- Cambio de identidad por email o soporte de cuentas sin email.

## 17. CONCLUSION

### Parte reutilizable

- `Usuario` como identidad digital con password hasheado e `is_active`.
- `Cliente.usuario` para ownership y coexistencia con perfil laboral.
- `Personal.usuario` nullable para acceso opcional.
- `Personal.activo` como estado laboral.
- Groups y Permissions ya creados.
- `assign_business_role()` como primitiva atomica de reemplazo.
- `UsuarioManager.create_user()` y `set_password()`.
- Recuperacion de password basada en tokens Django, despues de endurecerla.
- `Auditoria` y Simple History como bases parciales de trazabilidad.
- BH-052A, que impide vincular/elevacion desde el CRUD generico.

### Lo que falta realmente

- Servicios de aplicacion para crear, vincular, revocar y reactivar acceso.
- Validaciones de coherencia entre rol y perfiles.
- Acciones API dedicadas con permisos nuevos.
- Auditoria semantica de Groups M2M.
- Separar totalmente baja laboral, cuenta digital y estado Cliente.
- Cerrar vias de bypass de Django Admin y serializers genericos.
- Politica coherente de login/reset para `is_active` y revocacion de tokens.

### Cambios de modelo

No hacen falta cambios obligatorios de Usuario o Personal para implementar el flujo base. Tampoco hace falta `must_change_password` si no se exige cambio forzado. Las mejoras de email case-insensitive, expiracion de password o un log de seguridad especializado pueden evaluarse despues y no deben bloquear la primera fase.

### Mayor riesgo

El mayor riesgo es crear endpoints de acceso antes de tener una transicion de rol atomica, validada y auditada. Eso permitiria estados parciales: Usuario creado sin vinculo, rol laboral sin Personal, doble rol, reactivacion silenciosa o cambios M2M sin trazabilidad.

El segundo riesgo es mantener vias paralelas que bypassen los nuevos servicios: Django Admin editando Groups/Personal.usuario, `UsuarioAdminSerializer` escribiendo `is_staff/is_active/password`, el script `fix_personal_staff.py` y la creacion implicita de Personal desde contenido.

### Secuencia final recomendada

```text
servicio de rol validado + auditoria atomica
-> servicio de vinculacion existente
-> accion API de vinculacion
-> servicio y accion de crear acceso
-> baja/reactivacion explicita de Personal
-> desactivacion/reactivacion explicita de Usuario
-> endurecer password/login/reset
-> cerrar vias genericas y Django Admin
-> integrar frontend por capacidades
```

La primera entrega no debe intentar resolver todo el ciclo de vida. Debe establecer una unica transicion de rol validada y auditada; sobre esa base pueden construirse la vinculacion y el alta de acceso sin repetir reglas ni introducir side effects.
