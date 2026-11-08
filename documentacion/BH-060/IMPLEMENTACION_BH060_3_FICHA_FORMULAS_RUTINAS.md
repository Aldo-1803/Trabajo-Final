# BH-060 Incremento 3 — Ficha técnica, fórmulas y rutinas

## Estado

**VALIDADO TÉCNICAMENTE** sobre el baseline publicado
`8d8e6688226ad177e2a51c277ff480c6e88e9ace`.

El incremento reemplaza decisiones basadas en `is_staff`/`IsAdminUser` por
permisos Django efectivos y aplica estado, habilidad y ownership donde el
dominio lo requiere. No incluye cambios de BH-060 Incremento 4.

## Clasificación de operaciones

| Dominio | Operación | Tipo |
|---|---|---|
| Ficha técnica | Listar, detalle, por Turno, por Cliente, propias | Lectura |
| Ficha técnica | Crear y editar datos técnicos | Escritura técnica |
| Ficha técnica | Eliminar | No admitida; preserva historia |
| Fórmulas | Consultar plantilla de Servicio o fórmula de ficha | Lectura técnica sensible |
| Fórmulas | Modificar `plantilla_formula` o `formula` | Escritura de fórmula |
| Rutinas | Consultar catálogo publicado | Lectura autenticada |
| Rutinas | Crear, editar, publicar, obsoletar o eliminar plantilla | Administración |
| Rutinas | Asignar una Rutina a otro Cliente | Asignación administrativa |
| Rutinas | Seleccionar una Rutina publicada para el Cliente actual | Selección propia |
| `RutinaCliente` | Consultar, actualizar desde original o eliminar | Operación sobre copia propia o administración |

## Matriz operación × permiso × ownership

| Operación | Permiso efectivo | Condiciones adicionales | Scope/ownership |
|---|---|---|---|
| Cliente consulta ficha | Ningún permiso técnico | Cuenta y perfil Cliente activos | Sólo fichas de sus Turnos; no recibe `formula` ni `formula_base_servicio` |
| Personal consulta ficha | `gestion.manage_technical_record` | Cuenta, Personal y habilidad `DIAGNOSTICO` activos | Fichas creadas por el actor o de Turnos asignados al actor |
| Personal crea/edita ficha | `gestion.manage_technical_record` | Cuenta, Personal y `DIAGNOSTICO` activos; Turno confirmado/en proceso | Sólo Turno asignado al Personal; autor y `detalle_turno` inmutables |
| Crear/editar `formula` en ficha | `gestion.manage_technical_record` **y** `gestion.manage_formulas` | Mismas condiciones técnicas de ficha | Sólo ficha/Turno dentro del scope del actor |
| Leer `plantilla_formula` de Servicio | `gestion.manage_formulas` | Personal y `DIAGNOSTICO` activos | Lectura técnica; se omite para público y usuarios sin permiso |
| Editar `plantilla_formula` | `gestion.manage_formulas` | Cuenta, Personal y `DIAGNOSTICO` activos | No concede edición de precios u otros campos |
| Editar precio/catálogo de Servicio | `gestion.manage_prices` | Cuenta activa | No concede edición de fórmulas |
| Leer catálogo de Rutinas | Usuario autenticado y activo | — | Sin `assign_routines`, sólo estado `publicada` |
| Administrar plantilla de Rutina | `gestion.assign_routines` | Cuenta activa | Todas las plantillas |
| Seleccionar Rutina propia | Ninguno administrativo | Cuenta y Cliente activos; Rutina publicada | Cliente tomado de la sesión; payload sólo admite `rutina_id` |
| Asignar Rutina a otro Cliente | `gestion.assign_routines` | Cuenta y Cliente destino activos; Rutina publicada | `POST /rutinas-cliente/` con `cliente_id` y `rutina_id` |
| Leer/modificar/eliminar `RutinaCliente` | Cliente propietario o `gestion.assign_routines` | Cuenta activa | Queryset impide resolver IDs ajenos |
| Asignación automática CU-11 | Servicio interno, sin permiso HTTP | Cliente/rutina válidos | Idempotente por Cliente y Rutina original |

`is_staff=True` no concede ninguna de estas capacidades. Los permisos pueden
provenir de rol/grupo o grant individual y funcionan con `is_staff=False`.

## Endpoints y contratos modificados

### Ficha técnica

- `GET/POST /api/gestion/fichas-tecnicas/`
- `GET/PUT/PATCH /api/gestion/fichas-tecnicas/{id}/`
- `GET /api/gestion/fichas-tecnicas/por_turno/?turno_id={id}`
- `GET /api/gestion/fichas-tecnicas/por_cliente/?cliente_id={id}`
- `GET /api/gestion/fichas-tecnicas/mis_fichas/`
- `DELETE` queda deshabilitado para conservar trazabilidad.

La escritura valida el vínculo real
`Usuario -> Personal activo -> PersonalHabilidad DIAGNOSTICO activa` y que el
Personal sea el profesional asignado al Turno. `profesional_autor` se obtiene
de la sesión y no se acepta como autoridad del payload.

### Fórmulas

- `GET/PATCH /api/gestion/servicios/{id}/`
- Campos `formula` y `formula_base_servicio` de ficha.
- Campo `servicio_plantilla_formula` en detalles de Turno.

`ServicioSerializer` separa `plantilla_formula` del resto del catálogo:
`manage_prices` administra los campos comerciales y `manage_formulas` la
plantilla técnica. Un payload mixto sin ambos permisos se rechaza completo,
sin mutación parcial.

### Rutinas

- CRUD y acciones de `/api/gestion/rutinas/` usan `assign_routines` para
  administración.
- `POST /api/gestion/rutinas/seleccionar/` conserva selección propia.
- `POST /api/gestion/prueba-rutina/` conserva compatibilidad y usa el mismo
  servicio seguro de selección propia.
- `POST /api/gestion/rutinas-cliente/` realiza asignación administrativa.
- `/api/gestion/rutinas-cliente/{id}/` queda protegido por queryset de
  ownership; `PUT/PATCH` genéricos están deshabilitados.

Los serializers de comando rechazan campos adicionales. Las copias se crean
en transacción, conservan nombre, objetivo, descripción, archivo y versión, y
evitan duplicados para un mismo Cliente y Rutina original.

## Compatibilidad con CU-11

Los caminos automáticos de finalización, motor de diagnóstico y señales usan
`ensure_internal_routine_assignment()`. Esta entrada representa una operación
interna de dominio: no deriva autoridad de `is_staff` ni exige el permiso HTTP
`assign_routines` al actor que dispara legítimamente CU-11.

La operación es transaccional e idempotente. Puede conservar la Rutina
recomendada aunque aún no esté publicada, porque la selección fue realizada
por el motor interno; la selección manual y la asignación administrativa sólo
aceptan Rutinas publicadas.

## Frontend

- Las rutas administrativas de Rutinas exigen `gestion.assign_routines`.
- Servicios admite entrada con `manage_prices` o `manage_formulas`.
- `GestionarServicios` proyecta controles y payloads por capacidad: no envía
  la fórmula al guardar precios ni campos comerciales al guardar sólo fórmula.

## Pruebas y resultados

### Suite PostgreSQL focalizada

Archivo:
`gestion/tests/test_technical_record_formula_routine_permissions_bh060_3.py`

Resultado: **24/24 OK**.

Cobertura incluida:

- CLIENTE, EMPLEADO, PROFESIONAL y ADMINISTRADOR;
- anónimo, cuenta inactiva, Personal/Cliente inactivos;
- `is_staff=True` sin permiso y grants efectivos con `is_staff=False`;
- permisos por grupo de rol e individuales;
- habilidad ausente o inactiva;
- ficha propia/ajena, Cliente propio/tercero y profesional asignado/ajeno;
- lectura frente a escritura;
- `manage_technical_record` sin `manage_formulas`;
- `manage_formulas` sin `manage_prices` ni `assign_routines`;
- catálogo, selección propia y asignación a terceros;
- payloads con IDs/campos ajenos, duplicados y Rutinas no publicadas;
- persistencia y ausencia de mutación ante 401/403/404/409 y errores de dominio;
- preservación de autor, Detalle de Turno, fórmula histórica y copia de Rutina;
- CU-11 sin `assign_routines` en el actor.

### Regresiones backend

Suites de diagnóstico, habilidades, compatibilidad de Turnos, gestión/creación
de Turnos, bloqueos técnicos y roles: **124 conformes de 125**.

El único fallo se clasifica aparte como expectativa legacy conocida:
`test_legacy_flags_are_read_only_in_personal_serializer` espera que
`PersonalSerializer` ignore flags técnicos. La política vigente los rechaza
con `Este campo no está permitido.`. No se debilitó ese rechazo.

### Frontend y checks

- Frontend relacionado: **49/49 OK**.
- `python manage.py check`: OK.
- `python manage.py makemigrations --check --dry-run`: sin cambios.
- `npm run build`: OK con warnings preexistentes.
- `git diff --check`: OK; sólo advertencias de normalización CRLF/LF.

## Riesgos pendientes

- El endpoint legacy `/prueba-rutina/` se conserva por compatibilidad; debe
  retirarse sólo cuando sus consumidores migren al endpoint canónico.
- La expectativa legacy de `PersonalSerializer` debe actualizarse en un
  incremento separado para reflejar el rechazo explícito de flags técnicos.
- No se modificaron datos históricos existentes ni se agregó migración; el
  endurecimiento aplica a nuevas operaciones y a la exposición por API.
