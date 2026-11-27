# Análisis del flujo actual “Nuevo Usuario”

## Conclusión ejecutiva

El botón **“Nuevo Usuario” no representa una alta de negocio válida**. Es un CRUD técnico genérico que crea únicamente una fila de `Usuario`, clasifica de forma binaria mediante `is_staff` y no crea `Cliente`, no crea `Personal` y no asigna ningún `BusinessRole`.

Por eso puede producir cuentas activas sin perfil ni rol, cuentas marcadas como “Cliente” que no son clientes y cuentas “Profesional / Staff” sin `Personal` ni permisos de negocio coherentes.

No conviene convertir el flujo actual en el mecanismo de un único tipo de persona. La recomendación es **B: reemplazarlo por un menú de tipos de alta**, con operaciones de dominio separadas:

- **Nuevo cliente**: alta administrativa transaccional de `Usuario + Cliente + BusinessRole.CLIENTE`.
- **Nuevo Personal**: alta de `Personal` y, solo si necesita ingresar, `crear-acceso` o `vincular-usuario`.
- **Nuevo administrador**: onboarding dedicado de una cuenta con `BusinessRole.ADMINISTRADOR`, sin exigir `Cliente` ni `Personal`.

Antes de responder `405` en el POST genérico faltan, como mínimo, el alta administrativa de Cliente, una UI para los flujos de acceso de Personal y una decisión/operación explícita para crear administradores sin `Personal`.

---

## 1. Flujo actual en frontend

Archivo analizado: `frontend/src/pages/admin/GestionUsuarios.js`.

### Dónde aparece el botón “Nuevo Usuario”

El botón aparece en el encabezado de la pantalla **“Gestión de Usuarios”**, a la derecha del botón “Volver”. Al presionarlo ejecuta `setModalAbierto(true)` y abre el modal titulado **“Alta de Usuario”**.

La pantalla se presenta como “Administración de Profesionales y Clientes”, aunque el formulario no crea ninguno de esos perfiles de dominio.

### Quién puede verlo actualmente

Hay que distinguir visibilidad frontend de autorización backend:

- El botón no tiene ningún guard propio por rol o permiso.
- La ruta `/admin/usuarios` está envuelta únicamente en `ProtectedRoute`, que comprueba que exista `access_token`; no comprueba `is_staff`, `BusinessRole` ni `usuarios.manage_users`.
- El camino normal desde el login y el dashboard conduce allí a usuarios interpretados como staff, pero cualquier usuario autenticado puede intentar abrir la URL directamente.
- Al cargar la lista, el backend exige `IsAdminUser`. Si el usuario no tiene `is_staff=True`, la pantalla recibe `403`, muestra “Acceso denegado. Solo administradores.” y navega a `/`.
- El POST de creación también queda actualmente bajo `IsAdminUser`, no bajo `usuarios.manage_users`.

En la práctica, **cualquier cuenta con `is_staff=True` puede ver y usar el botón**, incluso si no tiene `BusinessRole.ADMINISTRADOR` ni el permiso `usuarios.manage_users`.

### Campos mostrados

El modal muestra:

1. `first_name`, label **“Nombre”**.
2. `last_name`, label **“Apellido”**.
3. `email`, label **“Email”**.
4. `password`, label **“Contraseña Provisoria”**.
5. `is_staff`, checkbox con label **“¿Es Profesional / Staff?”**.

Debajo del checkbox afirma: **“Si se marca, tendrá acceso al panel de administración.”**

### Campos obligatorios

Por validación HTML del formulario son obligatorios:

- `first_name`
- `last_name`
- `email`
- `password`

El checkbox `is_staff` es opcional.

Esta obligatoriedad corresponde al frontend. El serializer legacy del backend declara `password` como no obligatorio y el modelo permite nombre y apellido vacíos, por lo que el contrato real del backend es más permisivo que el modal.

### Payload enviado

Se envía el estado `form` completo:

```json
{
  "email": "persona@example.com",
  "first_name": "Nombre",
  "last_name": "Apellido",
  "password": "contraseña ingresada",
  "is_staff": false
}
```

El frontend no envía:

- `is_active`
- `is_superuser`
- `role` o `business_role`
- Groups
- permisos
- datos de `Cliente`
- datos de `Personal`

### Endpoint llamado

```text
POST http://127.0.0.1:8000/api/gestion/admin/usuarios/
Authorization: Bearer <access_token>
```

### Valores por defecto

El formulario inicial y el reset posterior al éxito usan:

```js
{
    email: '',
    first_name: '',
    last_name: '',
    password: '',
    is_staff: false
}
```

Como `is_active` no se envía, el modelo deja la cuenta activa por defecto. `create_user()` deja `is_superuser=False` por defecto.

### Cómo representa actualmente Cliente, Staff y rol

La pantalla usa una clasificación binaria basada exclusivamente en `is_staff`:

| Valor técnico | Representación en UI |
|---|---|
| `is_staff=false` | “Cliente” |
| `is_staff=true` | “Profesional” / “Profesional / Staff” |

El filtro de rol también traduce “cliente” a `is_staff=false` y “staff” a `is_staff=true`.

Esto no representa los roles reales `CLIENTE`, `EMPLEADO`, `PROFESIONAL` y `ADMINISTRADOR`. Tampoco comprueba que exista un perfil `Cliente` o `Personal`.

### Qué ocurre después de una creación exitosa

1. Muestra `Usuario creado exitosamente.`.
2. Cierra el modal.
3. Restablece todos los campos y `is_staff=false`.
4. Vuelve a cargar el listado de usuarios.
5. Ignora el cuerpo de la respuesta del POST.

### Errores manejados

El manejo es mínimo:

- Si `error.response.data.email` existe, muestra **“El email ya existe.”**.
- Para cualquier otro error muestra **“Error al crear usuario.”**.

No distingue:

- falta de autorización;
- contraseña inválida o débil;
- errores de nombre/apellido;
- conflicto de estado;
- fallo de red;
- errores internos;
- campos inesperados.

El modal permanece abierto al fallar, pero no presenta errores junto a cada campo ni conserva un contrato de errores semánticos.

### Esquema textual actual

```text
Usuario autenticado abre /admin/usuarios
→ la UI intenta listar cuentas
→ si el backend acepta al usuario como is_staff, se muestra la pantalla
→ usuario presiona “Nuevo Usuario”
→ se abre “Alta de Usuario”
→ completa nombre, apellido, email y contraseña
→ opcionalmente marca “Profesional / Staff”
→ el frontend envía email, nombres, password e is_staff
→ POST /api/gestion/admin/usuarios/
→ el backend crea solamente Usuario
→ la UI cierra el modal, limpia el formulario y recarga el listado
```

---

## 2. Flujo actual en backend

Archivos analizados:

- `bohemiacore/gestion/views.py`
- `bohemiacore/gestion/serializers.py`
- `bohemiacore/usuarios/models.py`
- `bohemiacore/gestion/signals.py`
- `bohemiacore/gestion/middleware.py`

### `AdminUsuarioViewSet.create()`

`AdminUsuarioViewSet` **no sobrescribe `create()`**. Usa la implementación estándar heredada de `ModelViewSet`, que:

1. obtiene `UsuarioAdminSerializer` mediante `get_serializer_class()`;
2. valida el payload;
3. llama `serializer.save()`;
4. devuelve `201 Created` con los campos serializables.

Para `create`, `get_permissions()` cae en la rama general y aplica `IsAdminUser`. En DRF eso significa `is_staff=True`; no significa `BusinessRole.ADMINISTRADOR` ni exige `usuarios.manage_users`.

### `UsuarioAdminSerializer.create()`

El serializer legacy expone:

- `id`
- `email`
- `first_name`
- `last_name`
- `is_staff`
- `is_active`
- `password`

Su `create()`:

1. extrae `password` de `validated_data`;
2. llama `Usuario.objects.create_user(**validated_data)` sin el password;
3. si se recibió password, llama `set_password(password)` y guarda nuevamente.

El resultado final tiene la contraseña hasheada correctamente. Sin embargo:

- no usa `validate_password()`;
- no exige confirmación;
- acepta contraseñas que el flujo público o `crear-acceso` podrían rechazar;
- si un consumidor omite `password`, puede crear un usuario con contraseña no utilizable.

El doble guardado también demuestra que no es un servicio transaccional de onboarding, sino una adaptación CRUD.

### Qué entidad crea realmente

Crea exclusivamente:

```text
usuarios.Usuario
```

No crea ninguna otra entidad de dominio.

### Respuestas concretas

| Pregunta | Respuesta actual |
|---|---|
| ¿Crea `Usuario`? | Sí. |
| ¿Crea `Cliente`? | No. |
| ¿Crea `Personal`? | No. |
| ¿Asigna `BusinessRole`? | No. No agrega ningún Group. |
| ¿Modifica `is_staff`? | Sí. Usa el booleano enviado; el frontend permite elegirlo. |
| ¿Crea password correctamente? | La hashea con `set_password()`, pero no aplica validadores de seguridad ni confirmación. Si se omite, queda no utilizable. |
| ¿Deja `Usuario.is_active=True`? | Sí en el flujo frontend, porque no envía el campo y el modelo usa `True`. La API legacy también permite enviar `is_active=false`. |
| ¿Puede crear superuser? | No mediante los campos declarados: `is_superuser` no está expuesto y `create_user()` fija `False` por defecto. |
| ¿Puede crear staff privilegiado? | Sí. Puede crear `is_staff=True`, suficiente para rutas legacy protegidas con `IsAdminUser` y para que el frontend lo trate como administrador. No obtiene por ello los permisos de negocio del Group `ADMINISTRADOR`. |
| ¿Puede crear una cuenta sin perfil? | Sí; es el resultado normal. |

### Auditoría generada

`gestion.signals` registra un signal genérico de auditoría para `Usuario`.

La primera creación genera una entrada aproximada a:

```text
tabla: Usuario
acción: ALTA
registro_id: nuevo usuario
usuario: actor recuperado por AuditoriaMiddleware
valor_nuevo: campos persistidos, excepto password
ip_address: IP de la request cuando está disponible
```

La contraseña está excluida del valor auditado. El segundo `save()` cambia el hash, pero como `password` está excluido, no produce una auditoría semántica útil sobre la asignación de credenciales.

No se genera:

- evento semántico de “cliente creado”, “acceso laboral creado” o “administrador incorporado”;
- motivo;
- auditoría de asignación de BusinessRole;
- auditoría de vínculo con `Cliente` o `Personal`, porque esos objetos no se crean.

### Estados incoherentes que puede generar

Sí, puede generar varios:

1. `is_staff=false`, mostrado como “Cliente”, pero sin `Cliente` y sin Group `CLIENTE`.
2. `is_staff=true`, mostrado como “Profesional”, pero sin `Personal` y sin Group `EMPLEADO` o `PROFESIONAL`.
3. `is_staff=true` sin `BusinessRole.ADMINISTRADOR`, pero con acceso a rutas legacy basadas en `IsAdminUser`.
4. Usuario activo sin ningún BusinessRole.
5. Usuario inactivo sin BusinessRole si un consumidor API envía `is_active=false`; después la reactivación semántica puede rechazarlo por falta de rol.
6. Cuenta con contraseña débil que no habría pasado `validate_password()`.
7. Cuenta sin contraseña utilizable si otro consumidor omite el campo.
8. Cuenta huérfana que no aparece en la cartera de clientes y no puede participar correctamente en operaciones que exigen `Cliente` o `Personal`.

---

## 3. Qué tipo de persona representa realmente

### Evidencia observada

- El título dice “Administración de Profesionales y Clientes”.
- El checkbox pregunta “¿Es Profesional / Staff?”.
- La tabla llama “Cliente” a todo `is_staff=false` y “Profesional” a todo `is_staff=true`.
- El dashboard describe la pantalla como “Permisos y cuentas de staff”.
- El payload no contiene campos de Cliente, Personal ni BusinessRole.
- El backend crea únicamente `Usuario`.
- No hay navegación desde el modal hacia un flujo de Cliente o Personal.

### Determinación

| Posible significado | Determinación |
|---|---|
| Alta real de Cliente | No. Solo parece Cliente por `is_staff=false`; no crea el perfil. |
| Alta real de empleado/profesional | No. Solo puede fijar `is_staff=true`; no crea ni vincula Personal. |
| Alta real de administrador | No. No asigna `BusinessRole.ADMINISTRADOR`; únicamente puede habilitar el flag técnico `is_staff`. |
| CRUD técnico genérico | **Sí. Es la descripción que coincide con su comportamiento real.** |

No hay evidencia en código que permita atribuirle un único significado de negocio. Es una interfaz genérica que mezcla identidad, contraseña y acceso técnico.

---

## 4. Comparación con los flujos nuevos

| Necesidad | Flujo correcto nuevo | ¿“Nuevo Usuario” lo duplica? | ¿Qué falta? |
|---|---|---:|---|
| A. Registro público de Cliente | `POST /api/usuarios/registro/`, creando `Usuario + Cliente` | Duplica solo la creación básica de Usuario y contraseña; no crea Cliente | El registro público todavía no persiste el Group `CLIENTE`: `usuario.es_cliente=True` es un atributo transitorio. Debe asignarse el rol dentro de la transacción. |
| B. Personal sin acceso | `POST /api/gestion/personal/` desde Gestión de Personal | No | El flujo ya existe y crea `Personal` sin Usuario porque `usuario` es read-only. Sus permisos genéricos siguen siendo legacy, pero no depende del POST de Usuario. |
| C. Personal → crear acceso | `POST /api/gestion/personal/{id}/crear-acceso/` → `create_access_for_personal()` | Duplica parcialmente Usuario/password, pero omite vínculo, rol, validaciones y auditoría semántica | El backend existe. Falta UI en `GestionPersonal.js` para invocarlo y presentar roles laborales permitidos. |
| D. Vincular Usuario existente a Personal | `POST /api/gestion/personal/{id}/vincular-usuario/` → `link_user_to_personal()` | No; crear otra cuenta sería incorrecto | El backend existe. Falta UI de búsqueda/selección, motivo y manejo de conflictos. Vincular no cambia el BusinessRole. |
| E. Futuro onboarding de ADMINISTRADOR | Operación dedicada que cree Usuario y asigne `BusinessRole.ADMINISTRADOR` | El POST legacy aparenta cubrirlo mediante `is_staff`, pero no lo hace correctamente | Falta servicio, serializer/action, política de contraseña o invitación, auditoría semántica y UI. Debe permitir administrador sin Personal. |

Observación adicional: `crear-acceso` admite `ADMINISTRADOR`, pero exige un `Personal` existente. Sirve para una persona del salón que además será administradora; no reemplaza el onboarding de un administrador puramente administrativo.

---

## 5. Casos de negocio reales

### 1. Quiero registrar un cliente nuevo presencialmente

- **¿Debe resolverse desde “Nuevo Usuario”?** No en su forma actual.
- **Flujo correcto:** alta administrativa de Cliente que cree transaccionalmente `Usuario + Cliente + BusinessRole.CLIENTE`.
- **¿Falta alguna operación?** Sí. No existe hoy esa action/servicio administrativo.

### 2. Quiero crear un empleado nuevo

- **¿Debe resolverse desde “Nuevo Usuario”?** No.
- **Flujo correcto:** crear primero `Personal` desde Gestión de Personal con su información laboral. Si necesita login, ejecutar después `crear-acceso` con rol `EMPLEADO`.
- **¿Falta alguna operación?** El backend de ambas etapas existe. Falta integrar `crear-acceso` en la UI.

### 3. Quiero crear un profesional nuevo

- **¿Debe resolverse desde “Nuevo Usuario”?** No.
- **Flujo correcto:** crear `Personal` con puesto/habilidades operativas y luego `crear-acceso` con `BusinessRole.PROFESIONAL` si necesita ingresar.
- **¿Falta alguna operación?** Falta la UI para creación de acceso; también debe mantenerse clara la diferencia entre `Personal.rol` operativo y `BusinessRole.PROFESIONAL`.

### 4. Quiero darle acceso a un Personal ya existente

- **¿Debe resolverse desde “Nuevo Usuario”?** No.
- **Flujo correcto:** `personal/{id}/crear-acceso/` si el email no existe, o `personal/{id}/vincular-usuario/` si ya existe una cuenta apropiada.
- **¿Falta alguna operación?** Las actions y servicios existen. Falta UI administrativa para ambas.

### 5. Un Cliente existente empieza a trabajar

- **¿Debe resolverse desde “Nuevo Usuario”?** No; no debe crearse una segunda cuenta.
- **Flujo correcto:** crear un `Personal`, vincular el Usuario existente con `vincular-usuario` y asignar explícitamente el rol laboral correcto.
- **¿Falta alguna operación?** Sí en la capa API/UI: la vinculación existe, pero deliberadamente no cambia el BusinessRole. No se encontró una action pública dedicada para cambiar a `EMPLEADO` o `PROFESIONAL`, aunque existe el servicio interno `assign_validated_business_role()`.

El perfil `Cliente` puede conservarse como perfil de dominio aunque el único BusinessRole de acceso pase a ser laboral.

### 6. Quiero crear otro ADMINISTRADOR

- **¿Debe resolverse desde “Nuevo Usuario”?** No.
- **Flujo correcto:** onboarding administrativo dedicado, con rol fijado por servidor en `ADMINISTRADOR`.
- **¿Falta alguna operación?** Sí. No existe un flujo seguro completo para administrador sin Personal. Crear `is_staff=true` no equivale a asignar el rol de negocio.

### 7. Quiero crear una cuenta técnica sin Cliente ni Personal

- **¿Debe resolverse desde “Nuevo Usuario”?** No.
- **Flujo correcto:** no crearla salvo una necesidad técnica explícita y gobernada. Un administrador de negocio sin perfiles debe usar onboarding `ADMINISTRADOR`; un superuser técnico debe administrarse como cuenta break-glass fuera del flujo cotidiano.
- **¿Falta alguna operación?** No se encontró una necesidad de negocio codificada para cuentas genéricas huérfanas. Por tanto, no hace falta conservar una API general para este caso.

---

## 6. Alta presencial de Cliente

### ¿“Nuevo Usuario” cubre de facto esa necesidad?

Solo la **simula visualmente**:

- con `is_staff=false`, la tabla muestra “Cliente”;
- solicita nombre, apellido, email y contraseña, campos parecidos a un alta rápida.

Pero no la cubre realmente:

- no crea `Cliente`;
- no asigna `BusinessRole.CLIENTE`;
- la cuenta no aparece en `GestionClientes`, cuyo queryset parte de `Cliente`;
- no puede ser seleccionada con seguridad por operaciones que requieren perfil Cliente;
- puede quedar activa y autenticable sin perfil de dominio.

Por tanto, retirar el botón no elimina una alta presencial funcional; elimina un atajo defectuoso que puede haber sido usado creyendo que daba de alta clientes.

### ¿Existe hoy alta administrativa `Usuario + Cliente`?

**No.**

- `ClienteViewSet` es `ReadOnlyModelViewSet`.
- `AdminUsuarioViewSet` crea solo `Usuario`.
- `GestionClientes.js` lista y consulta fichas, pero no ofrece alta.
- El único flujo que crea `Usuario + Cliente` es el registro público `POST /api/usuarios/registro/`, con `AllowAny` y orientado al autoservicio del cliente.

Además, el frontend público obliga a completar cinco campos capilares en el paso 2, aunque el serializer backend los admite como opcionales. Ese formulario no es adecuado como alta rápida de mostrador.

### ¿Se necesita `create_client_account_by_staff(...)` o equivalente?

**Sí, antes de retirar definitivamente el POST genérico si se quiere mantener la capacidad de alta presencial.**

La operación debería:

- exigir `usuarios.create_walkin_client`;
- crear `Usuario`, `Cliente` y Group `CLIENTE` en una transacción;
- fijar `is_staff=False` e `is_superuser=False` en servidor;
- dejar `is_active` bajo una política explícita;
- validar email duplicado sin reemplazar cuentas silenciosamente;
- no aceptar `role`, Groups, permisos ni flags privilegiados;
- registrar actor, motivo/source y resultado mediante auditoría semántica;
- no exigir diagnóstico, rutina ni datos capilares;
- definir si la cuenta recibe invitación, contraseña temporal validada o contraseña no utilizable hasta activación.

Con el modelo actual, el email es obligatorio y único. No debe resolverse el caso walk-in inventando emails falsos. Si se necesitan clientes sin email, eso es una decisión de identidad separada que sí podría requerir cambios de modelo.

---

## 7. Administrador nuevo

### Estado actual

No existe un flujo seguro que, en una única operación de negocio:

1. cree `Usuario`;
2. asigne `BusinessRole.ADMINISTRADOR`;
3. configure una credencial inicial segura;
4. no exija `Cliente`;
5. no exija `Personal`.

Las alternativas actuales no son equivalentes:

- El POST genérico crea `is_staff`, pero no Group `ADMINISTRADOR`.
- `create_access_for_personal()` puede asignar `ADMINISTRADOR`, pero obliga a partir de un `Personal` activo.
- `assign_validated_business_role()` existe como servicio interno, pero no se encontró una action genérica de onboarding que cree primero la cuenta.
- Django Admin puede manipular usuarios y Groups, pero es una vía técnica que evita el contrato semántico y no debe ser el flujo normal de negocio.

Por ello, retirar el POST genérico sin reemplazo no elimina un onboarding administrativo correcto —porque hoy no existe—, pero sí cerraría el atajo actual usado potencialmente para crear cuentas con acceso legacy al panel.

### Onboarding conceptual propuesto

Servicio conceptual:

```text
create_administrator_account(
    actor,
    email,
    first_name,
    last_name,
    credential_strategy,
    reason,
)
```

Responsabilidades:

- exigir `usuarios.manage_users` y `usuarios.assign_roles`;
- impedir auto-onboarding y targets duplicados;
- crear `Usuario` activo según política explícita;
- fijar `is_superuser=False`;
- mantener `is_staff=False` salvo una operación técnica separada para Django Admin;
- asignar exclusivamente `BusinessRole.ADMINISTRADOR` usando la primitiva validada existente;
- no crear `Cliente` ni `Personal`;
- validar contraseña temporal o emitir invitación/reset seguro;
- auditar creación, actor, motivo y rol sin guardar secretos;
- hacer rollback completo ante cualquier fallo.

La UI no debería permitir elegir arbitrariamente el rol dentro de esta operación: el endpoint es de onboarding de administrador y el servidor fija `ADMINISTRADOR`.

---

## 8. Cuentas técnicas

Hay tres conceptos distintos:

| Tipo | Cliente requerido | Personal requerido | BusinessRole | Uso |
|---|---:|---:|---|---|
| Administrador puramente administrativo | No | No | `ADMINISTRADOR` | Operación cotidiana de la SPA con permisos de negocio. |
| Superuser técnico Django | No | No | No debe inferirse automáticamente | Emergencia, mantenimiento o Django Admin; fuera del onboarding normal. |
| Cuenta técnica/servicio genérica | No | No | Depende de una necesidad explícita | No se encontró una necesidad real en el flujo analizado. |

Un administrador sin `Cliente` ni `Personal` **sí puede ser una cuenta legítima de negocio**. No debe llamarse superuser ni necesitar `is_superuser=True`.

En cambio, una cuenta huérfana creada “por si acaso”, sin rol ni perfil, no tiene significado de negocio y no justifica mantener el POST genérico.

---

## 9. Decisión sobre el botón

### Recomendación elegida: B. Reemplazarlo por un menú de tipos de alta

Etiqueta recomendada:

```text
[+ Agregar persona]
```

Opciones:

```text
Nuevo cliente
Nuevo Personal
Nuevo administrador
```

### Justificación

- **Claridad para Yanina:** la pregunta pasa a ser qué persona necesita incorporar, no qué flags técnicos debe marcar.
- **Evita estados genéricos:** cada opción crea el perfil y rol que corresponden.
- **Reutiliza dominio:** Personal sigue administrándose desde su módulo y el acceso usa actions existentes.
- **Mínimo alcance:** el menú puede navegar a pantallas existentes; no exige rediseñar toda Gestión de Usuarios.
- **Escalable a otros salones:** “cliente”, “personal” y “administrador” son conceptos transferibles; `is_staff` y “usuario genérico” son detalles técnicos del sistema.

No se recomienda:

- mantener el checkbox `is_staff`;
- convertir el modal actual directamente en alta de Personal;
- dejarlo solo para administradores usando el mismo serializer;
- ofrecer una opción “cuenta técnica” en la UI cotidiana.

---

## 10. Propuesta de UX

### Menú principal

```text
[+ Agregar persona]
   ├── Nuevo cliente
   ├── Nuevo Personal
   └── Nuevo administrador
```

### Nuevo cliente

Abrir un modal corto desde Gestión de Clientes o navegar a una pantalla específica.

Campos mínimos con el modelo actual:

- nombre;
- apellido;
- email;
- teléfono opcional;
- zona opcional.

Decisión de credencial visible y comprensible:

- “Enviar invitación”, preferido; o
- contraseña temporal con política segura, si todavía no hay invitaciones.

API/servicio: `create_client_account_by_staff(...)` o equivalente.

No pedir:

- `is_staff`;
- `is_active` como checkbox libre;
- BusinessRole;
- Groups o permisos;
- diagnóstico capilar obligatorio;
- `is_superuser`.

### Nuevo Personal

Navegar a `/admin/personal` y abrir el modal existente de “Crear Personal”. Después del alta:

```text
¿Esta persona necesita ingresar al sistema?
[No por ahora] [Crear acceso] [Vincular cuenta existente]
```

- **Crear acceso** usa `personal/{id}/crear-acceso/`.
- **Vincular cuenta existente** usa `personal/{id}/vincular-usuario/`.

No pedir `is_staff`. El rol de acceso debe limitarse a los roles laborales permitidos y diferenciarse del puesto/skills de `Personal`.

### Nuevo administrador

Abrir un modal dedicado, visible solo para quien tenga permisos de gestión y asignación de roles.

Campos:

- nombre;
- apellido;
- email;
- motivo;
- estrategia de credencial: invitación o contraseña temporal validada.

El servidor fija `BusinessRole.ADMINISTRADOR`.

No pedir:

- `Cliente`;
- `Personal`;
- `is_staff`;
- `is_superuser`;
- selector de rol arbitrario;
- permisos individuales.

Si la persona también trabaja en el salón, el perfil `Personal` debe crearse explícitamente como una decisión separada.

---

## 11. Dependencias para retirar el POST genérico

Estado previo requerido para cambiar:

```text
POST /api/gestion/admin/usuarios/
→ 405 Method Not Allowed
```

| Dependencia | Estado | Clasificación | Observación |
|---|---|---|---|
| Crear `Personal` sin acceso | Existe | Ya existe | `POST /api/gestion/personal/`; `usuario` es read-only. |
| Servicio/action `crear-acceso` para Personal | Existe | Ya existe | Crea Usuario, vínculo, rol y auditoría. |
| Servicio/action `vincular-usuario` | Existe | Ya existe | Vincula sin cambiar acceso ni rol. |
| Servicios de roles y permisos | Existe | Ya existe | `assign_validated_business_role()` y Groups sembrados. |
| Desactivar/reactivar cuenta | Existe | Ya existe | Ya no depende del PATCH legacy. |
| Registro público `Usuario + Cliente` | Existe parcialmente | Falta completar | Crea ambos, pero no persiste Group `CLIENTE`; usa `es_cliente` transitorio. |
| Alta administrativa/walk-in `Usuario + Cliente + CLIENTE` | No existe | **Falta — bloqueante** | Necesaria para recepción y turnos presenciales. |
| UI para `crear-acceso` de Personal | No existe en `GestionPersonal.js` | **Falta — bloqueante operativa** | El backend solo no reemplaza el uso cotidiano del modal legacy. |
| UI para `vincular-usuario` | No existe en `GestionPersonal.js` | **Falta — bloqueante para cuentas existentes** | Debe buscar/seleccionar cuentas elegibles y pedir motivo. |
| Cambio de BusinessRole para Cliente que empieza a trabajar | Servicio interno existe; action/UI no encontrada | **Falta** | Vincular Personal no cambia el rol. |
| Onboarding de administrador sin Personal | No existe | **Falta — bloqueante si se preserva esa capacidad** | Debe crear cuenta y asignar `ADMINISTRADOR` semánticamente. |
| Reemplazo del botón “Nuevo Usuario” | No existe | **Falta — bloqueante** | Debe eliminar toda llamada frontend al POST genérico. |
| POST genérico responde 405 y serializer legacy de creación se retira | No | **Falta — cambio final** | Debe hacerse solo después de migrar consumidores. |
| Tests de contratos de alta por dominio | Parciales | **Falta** | Cliente administrativo y administrador necesitan pruebas nuevas. |
| Política de invitación/contraseña inicial | No está unificada | **Falta decidir** | No debe conservarse una contraseña arbitraria sin validadores. |
| Mostrar/filtrar por BusinessRole real en Gestión de Usuarios | Parcial | Opcional para retirar POST | Mejora claridad, pero no es requisito técnico para devolver 405. |
| Menú único “Agregar persona” | No existe | Opcional | Recomendado para UX; también puede distribuirse por módulos. |
| Remediación de usuarios legacy sin rol/perfil | No forma parte del alta | Opcional/operativa | Debe auditarse aparte; no justifica mantener nuevas altas incoherentes. |
| Soporte para Cliente sin email | No existe | Opcional y fuera de alcance | Requiere una decisión de identidad potencialmente mayor. |

---

## 12. Primer cambio recomendado

### Cambio mínimo siguiente

**Implementar el alta administrativa de Cliente**, sin retirar todavía el POST genérico.

### Motivo de prioridad

- Es una necesidad de negocio explícita para recepción, turnos presenciales y walk-ins.
- No existe ninguna alternativa administrativa correcta.
- El botón legacy parece cubrirla visualmente, pero crea cuentas defectuosas.
- Personal ya cuenta con servicios backend de acceso; Cliente no tiene equivalente.
- Es una capacidad reusable por otros salones.

### Alcance conceptual

1. Servicio transaccional `create_client_account_by_staff(...)` o equivalente.
2. Serializer de comando estricto.
3. Action/endpoint protegido por `usuarios.create_walkin_client`.
4. Creación atómica de:
   - `Usuario`;
   - `Cliente`;
   - único Group `CLIENTE`;
   - auditoría semántica.
5. Modal “Nuevo cliente” en `GestionClientes.js`.
6. Política explícita de credencial inicial.

No incluir en ese cambio:

- Personal;
- ADMINISTRADOR;
- `is_staff`;
- superuser;
- diagnóstico obligatorio;
- migraciones de modelo;
- retirada del POST genérico todavía.

### Riesgo

**Medio**.

El riesgo principal es identidad duplicada por email y rollback incompleto entre Usuario, Cliente, rol y auditoría. Debe resolverse con transacción, locks/constraints existentes y errores estables.

### Archivos probables

- `bohemiacore/usuarios/` — servicio nuevo de alta de Cliente.
- `bohemiacore/usuarios/serializers.py` — serializer de comando.
- `bohemiacore/usuarios/views.py` y posiblemente `urls.py` — action/endpoint.
- `frontend/src/pages/admin/GestionClientes.js` — modal/acción administrativa.
- tests backend de servicio y API.
- test frontend focalizado de Gestión de Clientes.

No debería requerir migraciones.

### Tests mínimos

1. actor con `create_walkin_client` crea `Usuario + Cliente + CLIENTE`;
2. actor sin permiso recibe `403`;
3. `is_staff` solo no autoriza;
4. email duplicado devuelve conflicto estable y no crea nada;
5. payload rechaza `is_staff`, `is_superuser`, `is_active`, role, Groups y permisos;
6. contraseña/invitación cumple la política elegida;
7. rollback completo si falla Cliente, rol o auditoría;
8. el nuevo usuario queda con exactamente un BusinessRole;
9. no se crea diagnóstico automáticamente salvo decisión expresa;
10. frontend envía solo el contrato permitido, actualiza la lista y muestra errores comprensibles.

### Criterio de terminado del primer cambio

Una persona autorizada puede crear desde la UI administrativa un cliente mínimo y obtener, en una única operación coherente, un `Usuario`, un `Cliente` y `BusinessRole.CLIENTE`, sin tocar flags técnicos ni usar el POST genérico de Usuario.

---

## 13. Criterio de cierre

Se podrá afirmar **“El POST genérico de Usuario puede eliminarse definitivamente”** cuando se cumpla todo lo siguiente:

1. No existe ningún `axios.post` ni otro consumidor frontend hacia `/api/gestion/admin/usuarios/` para crear cuentas.
2. El botón “Nuevo Usuario” fue eliminado o reemplazado por altas semánticas.
3. Existe alta administrativa de Cliente que crea `Usuario + Cliente + CLIENTE` atómicamente.
4. El registro público también deja al Cliente con Group `CLIENTE` persistido.
5. Gestión de Personal permite desde la UI:
   - crear Personal sin acceso;
   - crear acceso para Personal;
   - vincular una cuenta existente.
6. Existe una operación explícita para el caso “Cliente existente empieza a trabajar”, incluido el cambio autorizado de BusinessRole cuando corresponda.
7. Existe onboarding de `ADMINISTRADOR` sin Cliente ni Personal, o el negocio decide formalmente que esa capacidad no estará disponible desde la aplicación.
8. Ninguno de esos flujos acepta `is_staff`, `is_superuser`, Groups, permisos o `is_active` como decisiones libres del formulario.
9. Las contraseñas iniciales usan validadores o una estrategia segura de invitación/reset.
10. Cada flujo exige permisos de negocio, no `is_staff` como autorización.
11. Cada alta genera auditoría semántica con actor, fuente y motivo cuando corresponda.
12. Los tests prueban éxito, permisos, duplicados, payload estricto, rollback y ausencia de estados huérfanos.
13. `POST /api/gestion/admin/usuarios/` responde `405 Method Not Allowed`.
14. `UsuarioAdminSerializer` deja de existir como serializer genérico de creación; permanecen únicamente lectura, identidad y comandos explícitos.
15. Una búsqueda estática confirma que no se crean cuentas de Cliente, Personal o Administrador por el CRUD genérico.

La existencia de usuarios legacy sin rol o perfil debe tratarse mediante auditoría/remediación separada. No debe usarse como razón para mantener abierta la creación de nuevos estados incoherentes.

---

## 14. Salida

Este documento es exclusivamente de análisis y decisión.

- No se modificó el flujo.
- No se implementaron endpoints ni servicios.
- No se modificaron otros módulos.
- No se crearon migraciones.
- El siguiente paso recomendado es la alta administrativa de Cliente, no la retirada inmediata del POST genérico.
