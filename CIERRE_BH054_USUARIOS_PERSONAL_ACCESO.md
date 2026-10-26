# Cierre BH-054 — Usuarios / Personal / Acceso

**Fecha de auditoría:** 2026-10-22  
**Alcance:** estado actual de Usuarios, Personal, acceso, registro público, Django Admin y la dependencia puntual de Contenido Educativo.  
**Fuera de alcance:** implementar cambios, migraciones, backfill, Turnos/Agenda y demás módulos.

## 1. Conclusión ejecutiva

El subbloque todavía **no puede considerarse cerrado**. Los servicios semánticos nuevos existen y cubren correctamente asignación de rol, vínculo Usuario–Personal, creación de acceso, estados de Personal, revocaciones y estado de cuenta. Sin embargo, siguen abiertas rutas legacy que permiten evitar esas garantías.

Los cuatro riesgos principales son:

1. **CRUD genérico de Usuario — crítico.** Cualquier cuenta con `is_staff=True` puede crear otras cuentas staff, cambiar `is_staff`, cambiar `is_active` y reemplazar la contraseña de cualquier Usuario alcanzable por el ViewSet, incluso un superuser. Esto evita permisos de negocio, validaciones, locks, motivos y auditoría semántica.
2. **Django Admin de Usuario — crítico.** Permite editar `is_staff`, `is_superuser`, `is_active`, Groups, permisos individuales y contraseña. También permite formar múltiples BusinessRole y contiene acciones masivas que escriben estados directamente.
3. **DELETE de Personal — crítico.** Puede eliminar físicamente Personal sin revocar el Usuario ni su BusinessRole. El resultado posible es una cuenta laboral activa sin Personal, además de pérdida o desvinculación de relaciones históricas.
4. **`fix_personal_staff.py` — crítico.** Es un script manual todavía ejecutable que eleva masivamente a `is_staff` todos los Usuarios vinculados a Personal.

También deben cerrarse la creación implícita de Personal desde Contenido Educativo, la edición directa de Personal desde Django Admin y la creación de Clientes públicos sin Group `CLIENTE`.

No hace falta rediseñar modelos ni crear migraciones para el cierre mínimo propuesto. La única excepción es que un rediseño futuro del autor de Contenido Educativo sí requeriría migración, pero **no se recomienda para este cierre**.

## 2. Frontera de seguridad ya disponible

La solución debe reutilizar, no duplicar, estas piezas existentes:

- `usuarios.roles.assign_business_role()` como primitiva interna de exclusividad de BusinessRole.
- `usuarios.access_services.assign_validated_business_role()` para cambios administrativos de rol.
- `usuarios.access_services.deactivate_account()` y `reactivate_account()` para `Usuario.is_active`.
- `gestion.personal_access_services.link_user_to_personal()` para `Personal.usuario`.
- `gestion.personal_access_services.create_access_for_personal()` para alta laboral con contraseña temporal.
- `gestion.personal_access_services.deactivate_personal()` y `reactivate_personal()` para `Personal.activo`.
- Servicios de revocación laboral y baja total ya existentes.
- Permisos `usuarios.manage_users`, `usuarios.assign_roles`, `gestion.manage_personal`, `gestion.manage_skills` y `gestion.manage_content`.

Las actions nuevas de Personal y reactivación de cuenta usan `IsAuthenticated` y delegan la autorización al servicio. Esas actions **no dependen de `is_staff`**. El problema está en las rutas genéricas y en Django Admin.

## 3. Inventario de rutas y flujos legacy

| Ruta / flujo | Archivo / clase | Qué modifica | Bypass actual | Riesgo | Acción recomendada |
|---|---|---|---|---|---|
| `POST /api/gestion/admin/usuarios/` | `gestion/serializers.py::UsuarioAdminSerializer`; `gestion/views.py::AdminUsuarioViewSet` | Usuario, contraseña, `is_staff`, `is_active` | `IsAdminUser` solo exige `is_staff`; crea cuentas sin BusinessRole/perfil y puede propagar staff | **Crítico** | Retirar el alta genérica. Cliente por registro/servicio de Cliente; Personal por `crear-acceso`; alta ADMINISTRADOR solo mediante operación dedicada futura |
| `PUT/PATCH /api/gestion/admin/usuarios/{id}/` | Mismas clases | Identidad, contraseña, `is_staff`, `is_active` | Cambia privilegios, estado y credenciales sin servicio ni motivo; alcanza superusers | **Crítico** | Limitar a email/nombre/apellido; rechazar campos sensibles; proteger targets superuser |
| `DELETE /api/gestion/admin/usuarios/{id}/` | `AdminUsuarioViewSet.perform_destroy()` | `Usuario.is_active=False`; también `Cliente.activo=False` | Evita `deactivate_account()`, último admin, superuser, auto-baja, lock y auditoría; acopla Cliente | **Crítico** | Deshabilitar DELETE y agregar/usar action `desactivar-cuenta` dedicada |
| Permisos del CRUD genérico de Usuario | `AdminUsuarioViewSet.get_permissions()` | Autoriza todas las operaciones genéricas | `IsAdminUser` convierte el flag técnico `is_staff` en permiso de negocio | **Crítico** | Usar `usuarios.manage_users` en la capa de servicio/permiso; no `is_staff` |
| Filtro/listado de “rol” por staff | `usuarios/filters.py::UsuarioFilter`; `GestionUsuarios.js` | Clasificación de lectura | Presenta `is_staff` como rol y oculta BusinessRole real | **Medio** | Exponer BusinessRole de solo lectura y filtrar por Group de negocio; compatibilidad temporal solo de lectura |
| Alta/edición de Usuario en Django Admin | `usuarios/admin.py::UsuarioAdmin` | `is_active`, `is_staff`, `is_superuser`, Groups, permisos y contraseña | Puede elevar privilegios, crear múltiples BusinessRole y evitar servicios | **Crítico** | Quitar campos sensibles del formulario ordinario; BusinessRole solo por servicio; excepción técnica explícita para superuser |
| Acciones masivas activar/desactivar | `UsuarioAdmin.activar_usuarios()` / `desactivar_usuarios()` | Usuario y Cliente activos | `queryset.update()` evita signals; no motivo, locks ni protecciones; acopla estados | **Crítico** | Eliminar acciones masivas; acciones semánticas individuales o flujo batch dedicado futuro |
| Cambio de contraseña desde Django Admin | `UsuarioAdmin` / `BaseUserAdmin` | Hash de contraseña | No usa política semántica de acceso; el campo password se excluye de la auditoría genérica | **Alto** | Restringir a superuser técnico como break-glass; operación administrativa dedicada si se confirma necesidad |
| `POST/PUT/PATCH /api/gestion/personal/` | `PersonalViewSet`; `PersonalSerializer` | Identidad, `rol` legacy, `activo`, skills | Escrituras genéricas autorizadas por `IsAdminUser`; `activo` evita servicio; skills evitan `manage_skills` | **Alto** | `usuario` ya es read-only; hacer `activo` read-only, separar permisos de Personal/skills y usar actions de estado |
| `DELETE /api/gestion/personal/{id}/` | `PersonalViewSet.perform_destroy()` | Soft delete directo o hard delete | No usa servicios; puede dejar Usuario/rol laboral activos y borrar relaciones | **Crítico** | Migrar frontend a `desactivar`; después responder 405. Eliminación física solo por corrección excepcional controlada |
| Edición de Personal en Django Admin | `gestion/admin.py::PersonalAdmin` | `usuario`, `activo`, `rol`, skills | Reasigna vínculo y estado sin servicios; una auditoría CRUD genérica no sustituye auditoría semántica | **Alto** | `usuario` y `activo` read-only; skills según `manage_skills`; vínculo/estado mediante servicios |
| Script `fix_personal_staff.py` | `gestion/fix_personal_staff.py` | `Usuario.is_staff=True` para todo Personal vinculado | Elevación masiva, sin rol, autorización, transacción global ni auditoría semántica | **Crítico** | Eliminar el Python ejecutable; si hace falta memoria histórica, conservar descripción no ejecutable en documentación |
| Creación de Contenido Educativo | `ContenidoEducativoViewSet.perform_create()` | Puede crear Personal implícito y vincularlo al Usuario | `get_or_create()` inventa Personal `administrador` por ser staff/superuser | **Alto** | Exigir Personal explícito existente; no crear perfiles como side effect; autorizar con `manage_content` |
| Lectura/edición de Contenido por staff | `ContenidoEducativoViewSet.get_queryset()/perform_update()` | Visibilidad y modificación de contenido | Usa `is_staff` como autorización global | **Alto** | Reemplazar por `gestion.manage_content` y conservar regla explícita de autoría donde corresponda |
| Autor editable en Django Admin | `ContenidoEducativoAdmin` | `ContenidoEducativo.autor` | Reatribución directa de contenido, aunque no crea Personal | **Medio** | Autor read-only tras creación; alta solo con Personal elegido explícitamente y validado |
| Registro público | `RegistroSerializer.create()`; `RegistroView.post()` | Crea Usuario + Cliente, pero no Group | `usuario.es_cliente=True` es un atributo transitorio, no un BusinessRole persistido | **Alto** | Asignar `CLIENTE` dentro de la misma transacción mediante servicio de alta pública |
| `ClienteAdmin.activo` | `usuarios/admin.py::ClienteAdmin` | Estado de dominio de Cliente | Edición directa y acciones de Usuario lo acoplan a cuenta | **Medio** | Mantenerlo separado de `Usuario.is_active`; definir permiso/operación explícita si el estado sigue teniendo uso de negocio |
| Password reset con token | `usuarios/views.py::PasswordResetConfirmView` | Contraseña del propio Usuario validado por token | Es un flujo dedicado, no un PATCH genérico | **Bajo / aceptado** | Mantener; agregar pruebas de política de password si faltan |
| Alta laboral `crear-acceso` | `PersonalViewSet.crear_acceso`; `create_access_for_personal()` | Usuario, contraseña temporal, vínculo y rol | No se detectó bypass: valida permisos, password, rol, perfil y audita | **Bajo / control existente** | Reutilizar como reemplazo del POST genérico para Personal |

## 4. Análisis por componente

### 4.1 `UsuarioAdminSerializer`

#### Estado actual

Expone como campos escribibles:

- `email`
- `first_name`
- `last_name`
- `is_staff`
- `is_active`
- `password`

No expone `is_superuser`, Groups ni `user_permissions`. Por tanto, la API genérica no asigna BusinessRole directamente, pero sí puede elevar `is_staff`, que basta para superar `IsAdminUser` en múltiples rutas legacy.

Riesgos adicionales:

- `update()` permite reemplazar la contraseña de cualquier target del queryset, incluido un superuser.
- No invoca `validate_password()` para esa contraseña administrativa.
- `create()` puede producir un Usuario activo sin Cliente, sin Personal y sin BusinessRole.
- `is_active` evita las reglas de último administrador, superuser, auto-baja y coherencia de perfiles.
- El serializer no distingue identidad de operaciones de seguridad.

#### Forma propuesta

Separar lectura, identidad y comandos:

1. **Serializer de lectura**
   - `id`, `email`, `first_name`, `last_name`.
   - `is_active` como solo lectura.
   - `business_role` como solo lectura, obtenido de Groups.
   - Indicadores de perfil (`has_cliente`, `has_personal`) solo si la UI los necesita.
   - `is_staff` solo como dato técnico de diagnóstico si existe una necesidad real; no presentarlo como rol.

2. **Serializer de actualización de identidad**
   - Únicamente `email`, `first_name`, `last_name`.
   - Rechazo estricto de campos desconocidos o sensibles. No ignorarlos silenciosamente.

3. **Sin serializer genérico de creación de cuenta**
   - Cliente: registro público o alta de Cliente dedicada.
   - Personal: `crear-acceso`.
   - Administrador: operación de onboarding específica, si el negocio la necesita.

4. **Comandos separados**
   - Rol: `assign_validated_business_role()`.
   - Baja: `deactivate_account()`.
   - Reactivación: `reactivate_account()`.
   - Contraseña: alta laboral o reset. Una intervención administrativa futura debe ser dedicada.

Los campos `is_staff`, `is_superuser`, Groups, `user_permissions`, `is_active` y `password` no deben ser escribibles desde el serializer de identidad.

### 4.2 `AdminUsuarioViewSet`

#### Separación conceptual definitiva

| Responsabilidad | Operación recomendada |
|---|---|
| Listar/consultar identidad | `GET`, con `usuarios.manage_users` |
| Corregir email/nombre/apellido | `PATCH` de identidad, con `usuarios.manage_users` |
| Crear Cliente | Registro/servicio de alta de Cliente |
| Crear acceso laboral | `POST personal/{id}/crear-acceso/` |
| Vincular Usuario existente | `POST personal/{id}/vincular-usuario/` |
| Asignar/cambiar BusinessRole | Action dedicada que llame `assign_validated_business_role()` |
| Desactivar cuenta | Nueva action `desactivar-cuenta` que llame `deactivate_account()` |
| Reactivar cuenta | Action existente `reactivar-cuenta` |
| Password inicial laboral | `crear-acceso` |
| Recuperar password | Flujo de reset con token |
| Cambio administrativo futuro | Action dedicada, permiso, motivo y auditoría; no PATCH genérico |

#### Métodos genéricos a limitar

- `POST`: devolver 405 una vez migrada/eliminada la creación genérica del frontend.
- `PUT/PATCH`: solo identidad básica; nunca flags, rol o contraseña.
- `DELETE`: devolver 405; la baja debe ser un comando con motivo.
- `GET`: puede permanecer, pero debe dejar de clasificar rol por `is_staff`.

La validación actual de DELETE sobre turnos no compensa el problema de seguridad: además de no usar el servicio, consulta turnos confirmados sin vincular la consulta al Usuario/Personal target. No debe trasladarse tal cual al nuevo comando; cualquier política operativa futura debe validarse en su servicio correspondiente.

### 4.3 Django Admin de Usuario

La solución mínima y segura no requiere reescribir el Admin:

1. Quitar del formulario ordinario `is_active`, `is_staff`, `is_superuser`, `groups` y `user_permissions`.
2. Mostrar BusinessRole calculado como read-only.
3. Eliminar las acciones masivas `activar_usuarios` y `desactivar_usuarios`.
4. Deshabilitar alta ordinaria desde Django Admin, porque crea Usuarios sin perfil/rol coherente.
5. Restringir el cambio de contraseña administrativo a superuser técnico y tratarlo como break-glass hasta que exista un comando dedicado.
6. Si se deben conservar Groups técnicos:
   - solo un superuser técnico puede gestionarlos;
   - el queryset debe excluir `CLIENTE`, `EMPLEADO`, `PROFESIONAL` y `ADMINISTRADOR`;
   - la validación debe rechazar cualquier BusinessRole recibido por manipulación del formulario.
7. Nunca permitir que el formulario genere dos BusinessRole. La validación debe estar también del lado servidor, no solo ocultada en HTML.

La auditoría CRUD de `gestion.signals` no es suficiente:

- no expresa motivo ni evento de negocio;
- captura campos directos, pero no los cambios M2M de Groups/permisos;
- las acciones con `queryset.update()` no disparan `save()` ni signals;
- `registrar_auditoria()` atrapa errores y no hace rollback;
- la contraseña está deliberadamente excluida del snapshot.

El `LogEntry` propio de Django Admin tampoco sustituye la auditoría semántica requerida.

### 4.4 Personal: API y Django Admin

#### API

`PersonalSerializer.usuario` ya es read-only. Este bypass fue correctamente cerrado en la API genérica y debe mantenerse así.

Siguen escribibles:

- `activo`: debe pasar a read-only y cambiarse solo mediante `desactivar`/`reactivar`.
- `realiza_diagnostico`, `realiza_lavado`, `realiza_color`: requieren `gestion.manage_skills`.
- identidad laboral y `rol` legacy: requieren `gestion.manage_personal`.

`Personal.rol` no es BusinessRole. Es una clasificación laboral (`colorista`, `asistente`, `administrador`) y no debe conceder permisos, cambiar Groups ni inferir `is_staff`. Puede mantenerse por ahora, claramente documentado como atributo legacy/operativo.

#### Django Admin

- `usuario`: siempre read-only después de crear el Personal; vincular solo mediante `link_user_to_personal()`.
- `activo`: read-only; usar servicios de estado.
- skills: editables solo para quien tenga `gestion.manage_skills`.
- identidad y `rol` legacy: editables solo con `gestion.manage_personal`.
- no usar `save_model()` para imitar parcialmente los servicios sin motivo. Es preferible bloquear el campo y dirigir al flujo dedicado.

### 4.5 `fix_personal_staff.py`

#### Uso real

- No está importado por código de producción.
- No es management command.
- Solo aparecen referencias documentales y el propio archivo.
- Se ejecuta manualmente con `python manage.py shell < gestion/fix_personal_staff.py`.

#### Efecto si se ejecuta hoy

Recorre todos los Personal, y para cada vínculo existente fija `personal.usuario.is_staff=True`. No verifica BusinessRole, estado de Usuario/Personal, permisos del actor ni propósito técnico. Tampoco genera auditoría semántica.

Esto es especialmente grave porque `is_staff=True` permite superar `IsAdminUser` en los CRUD legacy todavía abiertos.

#### Recomendación

**Eliminar el archivo Python ejecutable.** Git ya conserva el historial. Si se necesita contexto operativo, mover únicamente una explicación a `docs/legacy/` en formato Markdown, con la advertencia “NO EJECUTAR”. No conservar una copia `.py` importable ni convertirlo en un comando funcional.

Reemplazarlo por un comando que solo lance un error explícito sería aceptable durante una ventana corta si existen runbooks externos que aún lo invoquen, pero no debe ser el estado final.

### 4.6 Contenido Educativo

#### Dependencia exacta

- `ContenidoEducativo.autor` es `ForeignKey` a `Personal`.
- No admite `null` ni `blank`.
- Usa `on_delete=PROTECT`.
- El serializer presenta datos de Personal (`id`, nombre, apellido y `rol`).

Por ello, todo contenido actual necesita un Personal y el contenido histórico impide borrar físicamente a su autor. Cambiar `autor` a Usuario afectaría modelo, migración, serializer, filtros, Admin, frontend e históricos.

#### Administrador sin Personal

La infraestructura otorga `gestion.manage_content` al BusinessRole ADMINISTRADOR, pero el modelo actual no puede persistir un autor que no sea Personal. La implementación legacy resuelve esa contradicción inventando un Personal con `rol='administrador'`.

Para este cierre, un ADMINISTRADOR sin Personal **no debe crear contenido automáticamente**. Debe recibir un error estable, por ejemplo `AUTHOR_PERSONAL_REQUIRED`. Si necesita autoría operativa, el Personal debe crearse y vincularse explícitamente por el flujo de Personal.

#### Solución de menor impacto

1. Mantener `autor -> Personal`, obligatorio y con `PROTECT`.
2. Eliminar `Personal.objects.get_or_create()` de `perform_create()`.
3. Exigir un Personal previamente vinculado; preferentemente activo.
4. Autorizar la gestión global con `gestion.manage_content`, no con `is_staff`.
5. Mantener la regla de autoría para quien no tenga permiso global.
6. No permitir cambiar `autor` durante update ni desde Django Admin ordinario.

No se recomienda cambiar ahora `autor` a Usuario ni agregar `created_by`, porque eso amplía el subbloque y requiere migración. Si a futuro el negocio confirma que administradores no laborales publican contenido, la opción más expresiva sería conservar `autor` Personal nullable para la firma pública y agregar `created_by` Usuario para trazabilidad; queda fuera de este cierre.

### 4.7 DELETE de Personal

#### Comportamiento actual

- Si encuentra turnos en estados activos, escribe `Personal.activo=False` directamente.
- En otro caso, llama `instance.delete()`.
- La ruta exige `IsAdminUser`, no `gestion.manage_personal`.
- El frontend `GestionPersonal.js` llama directamente al DELETE.

Consecuencias del hard delete:

- El Usuario vinculado no se desactiva ni pierde su BusinessRole.
- Puede quedar una cuenta EMPLEADO/PROFESIONAL activa sin Personal, estado que otros servicios consideran inconsistente.
- Los turnos apuntan a Personal con `SET_NULL`, por lo que se pierde atribución del profesional.
- Horarios y bloqueos usan `CASCADE` y pueden eliminarse.
- Contenido Educativo usa `PROTECT`, por lo que algunos deletes fallarán según los datos relacionados.
- El test actual confirma explícitamente que borrar Personal no cambia privilegios del Usuario; esa propiedad es segura frente a elevación implícita, pero demuestra que DELETE no implementa una baja laboral.

#### Política definitiva

- **Baja laboral normal:** siempre `deactivate_personal()` o una revocación laboral/total, según el resultado deseado.
- **Eliminación física:** solo para registros creados por error y nunca como baja laboral.
- **API ordinaria:** DELETE debe terminar en 405.
- **Excepción técnica:** comando/servicio separado, solo superuser técnico o permiso excepcional, con motivo, transacción y auditoría.

Validaciones mínimas para eliminación excepcional:

- Personal sin Usuario vinculado.
- Sin turnos de ningún estado, no solo activos.
- Sin contenido educativo.
- Sin horarios/bloqueos u otras dependencias que deban conservarse.
- Confirmación explícita del borrado de relaciones auxiliares.
- Auditoría obligatoria y rollback si falla.

#### Transición

No puede devolverse 405 sin impacto: `frontend/src/pages/admin/GestionPersonal.js` depende del DELETE. Primero debe reemplazarse el botón por la action `desactivar` con motivo; después se bloquea DELETE. Como contención previa, puede restringirse temporalmente DELETE a superuser técnico, aceptando que el botón legacy responderá 403 hasta ser migrado.

### 4.8 Registro público y rol CLIENTE

#### Estado actual

`RegistroSerializer.create()` ya es atómico para:

1. crear Usuario;
2. crear Cliente;
3. crear diagnóstico inicial opcional.

No asigna BusinessRole. `RegistroView` escribe `usuario.es_cliente=True`, pero `Usuario` no define ese campo; es solo un atributo Python transitorio y `save()` no lo persiste.

#### ¿Es seguro asignar CLIENTE ahora?

**Sí, para nuevos registros.** Las migraciones ya crean el Group `CLIENTE`; el rol no agrega permisos base; Usuario y Cliente ya se crean dentro de una transacción; y el nuevo Usuario no tiene un rol previo que deba reemplazarse.

No debe hacerse backfill como parte de este cambio. Los Usuarios legacy siguen siendo una tarea de datos separada.

#### Implementación futura recomendada

No llamar directamente desde la View a `assign_validated_business_role()`, porque el registro es anónimo y ese servicio exige actor autorizado. Crear un servicio pequeño de alta pública, por ejemplo `register_client_account(...)` o `assign_initial_client_role(...)`, que:

- solo acepte el rol fijo `CLIENTE`;
- opere en la misma `transaction.atomic` que Usuario y Cliente;
- reutilice internamente `assign_business_role()`;
- valide que el Cliente existe y que no hay otro BusinessRole;
- escriba evento semántico con `actor=None` y `source='public_registration'`;
- haga rollback de Usuario, Cliente, rol y auditoría ante cualquier fallo.

Impacto esperado: positivo. Los nuevos clientes empezarán a ser reconocidos por código basado en BusinessRole. El código legacy que usa la relación `cliente` o `is_staff=False` no debería romperse. Deben agregarse tests porque hoy no hay cobertura específica del registro encontrada en `usuarios/test*.py`.

### 4.9 Contraseña administrativa

Política propuesta:

- Alta laboral: contraseña temporal validada mediante `crear-acceso`.
- Cliente: contraseña elegida en registro público con validadores.
- Recuperación: reset por token existente.
- Cambio autenticado por el propio usuario: flujo dedicado futuro, si se necesita.
- Cambio administrativo: solo action dedicada futura con permiso, motivo, validación de password, protección de superuser, auditoría sin secretos y política de notificación/forzado de cambio.

El PATCH genérico de password **puede cerrarse ya**: el frontend revisado solo envía password en el POST de creación, no en updates. Cerrar password en PUT/PATCH no rompe el consumidor actual y elimina la vía más directa de toma de cuentas. El POST genérico debe retirarse después de migrar su creación a los flujos de dominio.

## 5. Qué puede cerrarse ahora y dependencias

| Bypass | ¿Cierre inmediato sin romper uso observado? | Servicio / endpoint | Dependencia frontend | Excepción temporal |
|---|---|---|---|---|
| PATCH/PUT genérico de password | **Sí** | Ninguno; rechazarlo | No se observó PATCH de password | Cambio técnico por superuser fuera del API, documentado |
| Target superuser en escrituras genéricas | **Sí** | Rechazo explícito | Ninguna legítima identificada | Gestión técnica break-glass |
| `fix_personal_staff.py` | **Sí** | Eliminar/fallar explícitamente | Ninguna | Solo documentación no ejecutable |
| Registro sin `CLIENTE` | **Sí** para nuevos registros | Nuevo servicio de alta pública; primitiva `assign_business_role()` | Sin cambio de payload | Legacy existentes sin rol, hasta remediación separada |
| Creación implícita de Personal en contenido | **Sí técnicamente**, con impacto en admins sin Personal | Exigir Personal; `manage_content` | Editor admin puede recibir 409 para ese caso | Provisionar Personal explícito |
| Escritura genérica de `is_active` de Usuario | **No sin migrar UI** | `deactivate_account()` / `reactivate_account()` | `GestionUsuarios.js` usa PATCH | Ventana corta y fechada; no estado final |
| POST genérico Usuario con `is_staff` y password | **No sin retirar/migrar UI** | Registro Cliente / `crear-acceso` / onboarding admin | Botón “Nuevo Usuario” usa POST | No permitir nuevas altas legacy tras migración |
| DELETE Usuario | No se observó consumidor directo, pero validar operación | Action `desactivar-cuenta` | UI usa PATCH, no DELETE | Puede bloquearse temprano |
| `Personal.activo` en PUT/POST | **No sin ajustar UI** | `desactivar` / `reactivar` | El formulario envía `activo` | Campo read-only tras migración |
| DELETE Personal | **No sin ajustar UI** | `desactivar` o revocaciones | `GestionPersonal.js` usa DELETE | Restringir temporalmente a superuser |
| Personal.usuario en API | **Ya cerrado** | `vincular-usuario` | Ninguna | Mantener read-only |
| Personal.usuario/activo en Django Admin | Posible, pero confirmar operación interna | Servicios existentes | No frontend | Superuser técnico solo para recuperación excepcional |
| Groups/flags en Django Admin | Posible con preparación operativa | Servicio de rol y cuenta | No frontend | Groups técnicos solo para superuser |

## 6. Orden de cierre propuesto

### Paso 1 — Contención inmediata del CRUD de Usuario

**Riesgo:** crítico.  
**Archivos:** `gestion/serializers.py`, `gestion/views.py`, tests API nuevos.  
**Cambio futuro:** prohibir password en PUT/PATCH; rechazar escrituras genéricas sobre superusers; agregar pruebas que demuestren que un mero staff no puede gestionar seguridad.  
**Dependencia:** no se observó frontend que cambie passwords; revisar antes de cambiar el permiso global del ViewSet.  
**Tests:** payloads con password/flags; targets superuser; actor `is_staff` sin `manage_users`; preservación de hash/flags/Groups.  
**Terminado cuando:** ningún PUT/PATCH puede tomar una cuenta por password ni alterar un superuser.

### Paso 2 — Inutilizar `fix_personal_staff.py`

**Riesgo:** crítico, probabilidad operativa menor que la API pero cierre sin dependencias.  
**Archivos:** eliminar `gestion/fix_personal_staff.py`; documentación legacy opcional.  
**Dependencia:** ninguna referencia de código encontrada.  
**Tests:** búsqueda del archivo/import; si hay stub transitorio, ejecución debe fallar antes de consultar o escribir DB.  
**Terminado cuando:** no existe una instrucción ejecutable que eleve Personal a staff masivamente.

### Paso 3 — Sustituir estado de cuenta genérico por comandos

**Riesgo:** crítico.  
**Archivos:** `gestion/views.py`, serializers de comando, `GestionUsuarios.js`, tests API/servicio.  
**Cambio futuro:** añadir `desactivar-cuenta`; migrar toggle frontend a las actions de desactivar/reactivar; hacer `is_active` read-only; DELETE 405.  
**Servicio:** `deactivate_account()` y `reactivate_account()`.  
**Dependencia:** frontend usa PATCH para ambos estados.  
**Tests:** permisos, motivo estricto, último admin, auto-baja, superuser, idempotencia, auditoría/rollback y respuesta sin secretos.  
**Terminado cuando:** toda transición de `Usuario.is_active` de la API pasa por un servicio semántico.

### Paso 4 — Retirar alta genérica y `is_staff` del contrato de Usuario

**Riesgo:** crítico.  
**Archivos:** `gestion/serializers.py`, `gestion/views.py`, `GestionUsuarios.js`, tests.  
**Cambio futuro:** POST genérico 405; serializer de identidad estricto; listar BusinessRole real; usar `usuarios.manage_users`.  
**Dependencia:** el modal “Nuevo Usuario” usa POST con password e `is_staff`. Debe reemplazarse por acceso a registro Cliente, flujo Personal o onboarding administrador explícito.  
**Tests:** POST 405; identidad sí actualizable; todos los campos sensibles rechazados; actor staff sin permiso recibe 403.  
**Terminado cuando:** el CRUD genérico no crea cuentas ni eleva privilegios.

### Paso 5 — Asignar CLIENTE en registro público

**Riesgo:** alto por incoherencia, bajo riesgo de compatibilidad.  
**Archivos:** servicio de alta en `usuarios`, `usuarios/serializers.py`, `usuarios/views.py`, tests de registro.  
**Dependencia:** Groups sembrados por migración `gestion.0020_seed_business_roles`; no requiere frontend ni backfill.  
**Tests:** Usuario+Cliente+único Group CLIENTE; rollback si falla Group/auditoría/Cliente; no acepta otro rol; registro duplicado; diagnóstico opcional dentro de transacción.  
**Terminado cuando:** todo nuevo Cliente público nace con exactamente un BusinessRole `CLIENTE` y no existe `es_cliente` transitorio.

### Paso 6 — Cerrar estados, permisos y DELETE legacy de Personal

**Riesgo:** crítico para DELETE; alto para update.  
**Archivos:** `gestion/serializers.py`, `gestion/views.py`, `GestionPersonal.js`, tests de seguridad/estado.  
**Cambio futuro:** `activo` read-only; `manage_personal` para identidad/rol legacy; `manage_skills` para skills; frontend usa desactivar/reactivar; DELETE 405.  
**Servicio:** servicios de estado y revocación existentes.  
**Dependencia:** formulario PUT envía `activo` y botón borrar usa DELETE.  
**Tests:** staff sin permisos rechazado; activo no cambia por PUT; skills requieren permiso; DELETE 405; desactivar conserva Usuario/rol según contrato; revocaciones mantienen sus contratos.  
**Terminado cuando:** baja laboral normal nunca elimina Personal ni deja una cuenta laboral huérfana.

### Paso 7 — Endurecer Django Admin de Usuario y Personal

**Riesgo:** crítico/alto.  
**Archivos:** `usuarios/admin.py`, `gestion/admin.py`, tests de formularios/actions de Admin.  
**Dependencia:** confirmar si existe runbook operativo basado en estos campos. No hay dependencia frontend.  
**Tests:** usuario no superuser no ve ni puede forzar campos; BusinessRole no aparece en Groups editables; acciones masivas ausentes; Personal.usuario/activo read-only; permisos de skills.  
**Terminado cuando:** Django Admin no puede crear estados inválidos por formularios ordinarios y la excepción técnica está documentada.

### Paso 8 — Eliminar el side effect de Contenido Educativo

**Riesgo:** alto.  
**Archivos:** `gestion/views.py`, posiblemente serializer de comando/error, `gestion/admin.py`, tests de contenido.  
**Dependencia:** administradores que hoy publican sin Personal dejarán de poder hacerlo hasta provisionar uno explícitamente. El frontend no envía autor.  
**Tests:** admin con permiso y Personal crea; admin sin Personal recibe error y no crea Personal; actor sin `manage_content` no administra contenido ajeno; autor no cambia; histórico sigue legible.  
**Terminado cuando:** crear contenido nunca crea ni vincula Personal.

### Paso 9 — Retirar clasificación de rol por `is_staff`

**Riesgo:** medio, pero necesario para consistencia.  
**Archivos:** `usuarios/filters.py`, serializer de lectura, `GestionUsuarios.js`; únicamente dentro del alcance Usuarios.  
**Dependencia:** filtros actuales del frontend.  
**Tests:** filtros por los cuatro BusinessRole; usuarios sin rol/múltiples roles visibles como inconsistentes; ningún rol se infiere de staff.  
**Terminado cuando:** las pantallas de Usuarios muestran BusinessRole real y `is_staff` queda como flag técnico.

## 7. Criterios objetivos de cierre del subbloque

BH-054 / Usuarios–Personal–Acceso puede marcarse cerrado cuando se verifique todo lo siguiente:

### API y servicios

- [ ] Ninguna ruta de escritura del alcance autoriza negocio mediante `IsAdminUser` o `is_staff`.
- [ ] Un Usuario con `is_staff=True` pero sin permisos de negocio no puede administrar Usuarios, Personal, roles, skills ni contenido.
- [ ] El serializer genérico de Usuario solo escribe identidad básica.
- [ ] `is_staff`, `is_superuser`, BusinessRole/Groups, `user_permissions`, `is_active` y password son rechazados en escritura genérica.
- [ ] Ningún POST genérico puede crear una cuenta staff, privilegiada o sin flujo de dominio.
- [ ] BusinessRole solo cambia mediante servicio dedicado y siempre queda como máximo uno.
- [ ] `Personal.usuario` solo cambia mediante `link_user_to_personal()` o alta laboral compuesta.
- [ ] `Usuario.is_active` solo cambia mediante baja/reactivación semántica, salvo tooling técnico explícito.
- [ ] `Personal.activo` solo cambia mediante sus actions/servicios.
- [ ] La baja laboral normal no usa DELETE.
- [ ] DELETE genérico de Usuario y Personal responde 405.
- [ ] No existe PATCH genérico de password.

### Registro y perfiles

- [ ] Todo nuevo registro público crea atómicamente Usuario, Cliente y exactamente un Group `CLIENTE`.
- [ ] Fallar rol o auditoría revierte el registro completo.
- [ ] No se crean Cliente ni Personal implícitamente para reparar incoherencias.
- [ ] Contenido Educativo no ejecuta `Personal.objects.get_or_create()` ni otra creación de Personal.

### Django Admin y scripts

- [ ] El Admin ordinario no edita BusinessRole Groups, `is_active`, `is_staff`, `is_superuser` ni permisos individuales.
- [ ] El Admin no permite formar múltiples BusinessRole, incluso con un POST manipulado.
- [ ] No existen acciones masivas directas de activar/desactivar Usuarios.
- [ ] `Personal.usuario` y `Personal.activo` son read-only en Admin.
- [ ] Skills respetan `gestion.manage_skills`.
- [ ] `fix_personal_staff.py` no es ejecutable ni existe como script Python operativo.
- [ ] Toda excepción de superuser técnico está documentada como break-glass y no como flujo de negocio.

### Pruebas y verificación estática

- [ ] Tests negativos prueban que `is_staff` por sí solo no concede operaciones del subbloque.
- [ ] Tests de API prueban rechazo de todos los campos sensibles, no solo que sean ignorados.
- [ ] Tests de Admin cubren forms y POST manipulados.
- [ ] Tests de registro cubren atomicidad y Group CLIENTE.
- [ ] Tests de contenido prueban que no aparece un Personal como side effect.
- [ ] Tests de DELETE prueban 405 y preservación histórica.
- [ ] Regresiones existentes de roles, acceso, estados, revocaciones, login y seguridad de Personal siguen pasando.
- [ ] `makemigrations --check` no detecta cambios para este cierre mínimo.
- [ ] Una búsqueda de producción no encuentra escrituras directas no justificadas de `Usuario.is_active`, `Usuario.is_staff`, Groups o `Personal.usuario` fuera de los servicios aprobados.

## 8. Excepciones legacy temporales admisibles

Solo deberían quedar, con responsable y fecha de retiro:

1. **Usuarios históricos sin BusinessRole.** No se corrigen en este cierre porque requiere remediación/backfill separado. No deben crearse nuevos.
2. **`Personal.rol` legacy.** Puede permanecer como etiqueta laboral, siempre que no autorice ni modifique Groups/flags.
3. **`is_staff` técnico.** Puede seguir existiendo para acceso al Django Admin, pero no como permiso de negocio ni como rol mostrado al usuario.
4. **Superuser técnico break-glass.** Puede usar tooling restringido para recuperación de credenciales/flags técnicos; debe quedar fuera del flujo administrativo ordinario y auditado por procedimiento.
5. **`ContenidoEducativo.autor -> Personal`.** Se conserva para evitar migración y proteger históricos. La excepción no habilita creación implícita de Personal.
6. **Clasificación read-only por staff durante la migración del frontend.** Solo como ventana corta; no puede autorizar escrituras.

No son excepciones aceptables al cierre final:

- PATCH genérico de `is_active` o password.
- POST genérico con `is_staff`.
- edición ordinaria de BusinessRole Groups en Admin.
- DELETE ordinario de Personal.
- ejecución de `fix_personal_staff.py`.
- `get_or_create(Personal)` desde Contenido Educativo.

## 9. Primer cambio recomendado

El primer cambio debe ser un PR pequeño de **contención del CRUD de Usuario**, porque es la superficie remota de mayor impacto:

1. Usar serializer por action.
2. En PUT/PATCH permitir solo email, nombre y apellido.
3. Rechazar explícitamente password, `is_staff`, `is_superuser`, `is_active`, Groups, permisos y rol.
4. Rechazar cualquier escritura genérica sobre superusers.
5. Añadir tests donde un actor que solo tiene `is_staff` no puede cambiar seguridad.

Este primer PR puede cerrar password y superuser sin cambio frontend observado. La transición de `is_active` debe completarse inmediatamente después con `desactivar-cuenta` + migración del toggle frontend, y la creación genérica debe retirarse al migrar el botón “Nuevo Usuario” a flujos de Cliente/Personal.

En paralelo o como segundo PR independiente, debe eliminarse `fix_personal_staff.py`, ya que no tiene consumidor de código y su retiro no requiere coordinación funcional.

---

## Dictamen

La arquitectura nueva es suficiente para cerrar el subbloque sin ampliarlo a Turnos/Agenda ni rediseñar modelos. El trabajo pendiente consiste principalmente en **eliminar puertas paralelas**: serializers genéricos, `IsAdminUser`, Django Admin, scripts y DELETE. Una vez cumplidos los criterios anteriores, podrá afirmarse que los cambios de rol, acceso, vínculo y estados pasan por operaciones semánticas, autorizadas y auditadas.
