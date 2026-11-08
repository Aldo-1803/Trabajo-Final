# BH-060 F1 — Cierre de autorizaciones residuales

## 1. Estado y alcance

**Fecha de validación:** 2026-11-07
**Baseline:** `1531f692b11bfae25817ef94d1e9822b4c782102`
**Resultado:** **BH-060 F1 = VALIDADO**

Este incremento cierra exclusivamente las tres superficies activas identificadas
por `AUDITORIA_CIERRE_BH060.md`:

1. `HorarioLaboralViewSet`;
2. `RequisitoServicioViewSet`;
3. `upload_imagen`.

No se implementó CI, BH-061 ni BH-062. La auditoría original se preservó sin
cambios. Tampoco se modificaron modelos, migraciones, settings, credenciales,
storage, contratos frontend ni datos de aplicación.

## 2. Inspección de contratos y consumidores

### 2.1 HorarioLaboral

- Ruta router: `/api/gestion/horariolaboral/`.
- CRUD estándar: list, retrieve, create, update, partial update y destroy.
- Acciones masivas:
  - `POST /api/gestion/horariolaboral/configurar_rango/`;
  - `DELETE /api/gestion/horariolaboral/limpiar_agenda/?personal_id=...`.
- Consumidor frontend: `ConfiguracionAgendaMasiva.js` usa las dos acciones
  masivas con JWT. Para visualizar el patrón vigente usa la ruta legacy de
  calendario, cuya autorización global/propia no se cambió.
- Agenda propia, agenda legacy, disponibilidad, Turnos y CU-27 son superficies
  separadas y se preservaron.

### 2.2 RequisitoServicio

- Ruta router: `/api/gestion/requisitos-servicio/`.
- CRUD estándar completo y filtro `?servicio_id=...`.
- Consumidor frontend: `GestionarServicios.js` lista, elimina y crea requisitos
  durante la edición de un Servicio. El consumidor ADMINISTRADOR conserva
  `manage_configuration`; no depende de `is_staff`.
- Se preservan las relaciones con Servicio, TipoEquipamiento y Equipamiento
  activo, incluida la restricción de no asignar un tipo sin una instancia activa.

### 2.3 Upload legacy

- Ruta activa: `POST /api/gestion/upload-imagen/`.
- No tiene consumidor frontend actual. `GestionProductos.js` usa el ViewSet
  canónico `/api/gestion/imagenes-productos/`, ya protegido por
  `manage_products`.
- La ruta se conserva por compatibilidad, ahora con la misma autoridad de
  productos.

## 3. Política de autoridad implementada

No se consulta el nombre nominal de BusinessRole ni se usa `is_staff` como
autoridad de negocio.

| Superficie | Operación | Autenticación | Autoridad efectiva |
|---|---|---|---|
| HorarioLaboral | list/retrieve | Requerida | `view_global_agenda` **o** `manage_configuration` |
| HorarioLaboral | POST/PUT/PATCH/DELETE | Requerida | `manage_configuration` |
| HorarioLaboral | `configurar_rango` y `limpiar_agenda` | Requerida | `manage_configuration` |
| RequisitoServicio | list/retrieve/POST/PUT/PATCH/DELETE | Requerida | `manage_configuration` |
| `upload_imagen` | POST | Requerida | `manage_products` |

Se agregó `CanViewGlobalAgendaOrManageConfiguration` como composición de dos
permisos Django existentes. No se creó un permiso de modelo nuevo ni una
migración. La lectura directa de horarios queda disponible para EMPLEADO y
PROFESIONAL por su grant efectivo de agenda global, pero eso no les concede
ninguna mutación.

## 4. Cambios de implementación

### 4.1 HorarioLaboral

- `get_permissions()` separa lectura de administración.
- Un ADMINISTRADOR efectivo sin staff puede administrar.
- Un staff sin `manage_configuration` no puede escribir.
- Un grant individual de `manage_configuration` funciona sin staff.
- `configurar_rango` exige un patrón no vacío y pre-valida todos los Personal
  explícitos antes de abrir la fase de escritura. Esto evita que un target válido
  se persista si un target posterior es inexistente o inactivo y la respuesta es
  400.
- Las conversiones y altas siguen dentro de `transaction.atomic`; una excepción
  conserva rollback total.
- No se modificaron horarios propios, bloqueos, disponibilidad ni servicios de
  Turno.

### 4.2 RequisitoServicio

- Todo el ViewSet exige `manage_configuration`.
- El PATCH conserva Servicio y TipoEquipamiento cuando no vienen en el payload,
  en lugar de asumir que ambos están presentes.
- Create y update exigen al menos un Equipamiento activo del tipo seleccionado.
- La validación de update ocurre antes de `serializer.save()`, por lo que un 400
  no cambia tipo ni cantidad.

### 4.3 Upload de imágenes

- Exige `IsAuthenticated + CanManageProducts`.
- Conserva los MIME admitidos: JPEG, PNG, GIF y WebP.
- Conserva el máximo de 5 MiB.
- El nombre persistido siempre es `productos/<uuid>` y la extensión se deriva
  del MIME admitido, no del nombre enviado. No se aceptan rutas ni extensiones
  controladas por el cliente.
- Si el archivo fue guardado pero falla la obtención de su URL, se intenta
  eliminarlo antes de responder 500.
- Los detalles internos de la excepción no se devuelven al cliente y quedan en
  logging con traceback.

## 5. Matriz de pruebas PostgreSQL

Archivo agregado:

`gestion/tests/test_residual_authorization_closure_bh060_f1.py`

| Actor/condición | Horario lectura | Horario escritura/masivas | RequisitoServicio CRUD | Upload | Resultado |
|---|---|---|---|---|---|
| Anónimo | 401 | 401 | 401 | 401, cero storage | Cubierto |
| CLIENTE | 403 | 403, cero mutación | 403, cero mutación | 403, cero storage | Cubierto |
| EMPLEADO | 200 por `view_global_agenda` | 403, cero mutación | 403 | 403 | Cubierto |
| PROFESIONAL | 200 por `view_global_agenda` | 403, cero mutación | 403 | 403 | Cubierto |
| ADMINISTRADOR, `is_staff=False` | 200 | Permitido | Permitido | Permitido | Cubierto |
| `is_staff=True`, sin permiso | 403 | 403, cero mutación | 403, cero mutación | 403, cero storage | Cubierto |
| Cuenta inactiva con grants | 403 | 403, cero mutación | 403, cero mutación | 403, cero storage | Cubierto |
| Grant individual `manage_configuration`, no staff | 200 | CRUD y masivas permitidos | CRUD y filtro permitidos | 403 | Cubierto |
| Grant individual `manage_products`, no staff | 403 | 403 | 403 | Permitido | Cubierto |

Contratos adicionales comprobados:

- list/detail, POST, PUT, PATCH y DELETE de HorarioLaboral;
- `configurar_rango` y `limpiar_agenda`;
- prevalidación masiva y cero altas parciales ante un Personal inválido;
- list filtrado, detail, POST, PUT, PATCH y DELETE de RequisitoServicio;
- PATCH sin relaciones explícitas;
- rechazo de TipoEquipamiento sin instancia activa y cero mutación;
- payloads con `is_staff`, `is_superuser` y `user_permissions` no escalan;
- ningún rechazo crea Auditoria de éxito;
- rechazo de MIME y tamaño sin invocar storage;
- nombre/ruta generados por servidor;
- limpieza del archivo cuando falla `storage.url()`.

## 6. Resultados de validación

Todos los comandos backend usaron PostgreSQL real, base de test creada y
destruida por Django, y `--settings=bohemiacore.test_settings`.

| Ejecución | Resultado | Duración pared | Observaciones |
|---|---:|---:|---|
| Suite F1 final | **11/11 OK** | 90,07 s | Exit 0; 0 issues. |
| Regresión backend focalizada | **217/217 OK** | 571,28 s | Incluye F1, configuración/reportes, catálogos/equipamiento, inventario/permisos, roles, estados/aliases, agenda, HOLD, Turnos y CU-27. |
| Frontend `GestionProductos.test.js` | **8/8 OK** | 24,93 s | Contrato canónico de productos sin cambios. |
| `manage.py check` | **0 issues** | 5,35 s | Conforme. |
| `makemigrations --check --dry-run` | **No changes detected** | 6,61 s | Sin migraciones nuevas. |
| Build frontend | **OK** | 99,83 s | Warnings preexistentes de Browserslist, dependencia dinámica y ESLint. |

La primera ejecución focalizada obtuvo 10/11 porque el test nuevo asumía una
respuesta no paginada para RequisitoServicio. El endpoint devolvió correctamente
el envelope paginado; se corrigió únicamente la aserción. La repetición final
obtuvo 11/11 y la regresión posterior 217/217.

No se ejecutaron innecesariamente los 1.068 casos. La matriz integral queda para
la validación final posterior a F2.

## 7. Archivos F1

- `bohemiacore/gestion/permissions.py`;
- `bohemiacore/gestion/views.py`;
- `bohemiacore/gestion/tests/test_residual_authorization_closure_bh060_f1.py`;
- `IMPLEMENTACION_BH060_F1_CIERRE_AUTORIZACIONES.md`.

## 8. Riesgos residuales y fuera de alcance

- CI sigue pendiente de **BH-060 F2**; F1 no cierra por sí solo el criterio 14 de
  la auditoría.
- La validación de tipo del upload conserva el contrato previo basado en MIME
  declarado. Inspección de firma binaria, antivirus y políticas avanzadas de
  contenido pertenecen al hardening de storage/producción.
- Si `storage.save()` falla después de producir un efecto remoto pero antes de
  devolver el nombre, el backend de storage debe garantizar su propia atomicidad;
  sólo puede limpiarse de forma portable cuando se conoce la ruta retornada.
- Las acciones de estas superficies no generan un evento nuevo de Auditoria;
  F1 preserva ese contrato y demuestra que los rechazos tampoco generan eventos
  de éxito falsos.
- Los warnings globales del build no fueron introducidos por F1.
- Se mantiene el riesgo histórico de access tokens previos tras reactivación;
  F1 no modifica autenticación.

## 9. Veredicto

Las tres rutas activas dejaron de depender de `IsAdminUser`, los grants efectivos
funcionan sin staff, staff por sí solo no autoriza y los rechazos no mutan base ni
storage.

> **BH-060 F1 = VALIDADO**
