# BH-056 — Incremento C: Diagnóstico Capilar con permission + skill

## Resultado

`DiagnosticoCapilarViewSet` dejó de usar `is_staff` como autoridad. Las
acciones técnicas se autorizan con permisos efectivos, perfil `Personal`
activo y la skill canónica `DIAGNOSTICO` activa.

No se implementó BH-057, evaluación de solicitudes ni estados
`APTO/ADVERTENCIA/REQUIERE_REVISION/NO_APTO`. No se modificaron pagos,
Mercado Pago ni HOLD.

## Inventario y clasificación

| Acción / flujo | Clasificación | Regla aplicada |
| --- | --- | --- |
| `list` / `retrieve` | B o C según actor | Cliente: sólo propios. Técnica global: `manage_technical_record` + skill. |
| `mis_diagnosticos` | B | Sólo perfil Cliente propio. |
| `por_cliente` | B o C | Cliente sólo puede consultar su propio ID; lectura ajena requiere capacidad técnica global. |
| `create` | A | `create_diagnosis` + Personal activo + `DIAGNOSTICO`. |
| `update` / `partial_update` | A | Misma capacidad de escritura; sin gestión global sólo registros cuyo autor es el actor. |
| `destroy` | Historial técnico | Cerrado con HTTP 405; no hay borrado físico. |
| motor `_ejecutar_motor_diagnostico` | Motor interno | Reglas existentes sin estados nuevos de BH-057. |
| recomendación de Turno | Efecto asociado | Usa `TurnoAvailabilityService` y compatibilidad canónica de Incremento B. |
| `Turno.finalizar_turno` | Efecto técnico asociado | `finalize_service` + capacidad de crear diagnóstico; registra al actor real. |
| `GET /api/usuarios/diagnostico/` | B | Último diagnóstico del Cliente autenticado, sin skill técnica. |
| diagnóstico inicial de registro público | Automatización Cliente | Se conserva como baseline automático propio, con `profesional=NULL`; no es una acción técnica ni permite elegir Cliente/autor. |

## Helper y permission classes

Se agregó `gestion/technical_skill_access.py`:

- `DIAGNOSIS_SKILL_CODE = 'DIAGNOSTICO'`;
- `user_has_active_skill(user, skill_code)`.

El helper exige conjuntamente:

1. Usuario autenticado, persistido y activo;
2. `Personal` vinculado al Usuario y activo;
3. `Habilidad.code` coincidente y `activa=True`;
4. `PersonalHabilidad.activa=True`.

No consulta `BusinessRole`, `Personal.rol` ni flags `realiza_*`.

En `gestion/permissions.py` se agregaron:

- `CanCreateDiagnosisWithSkill`: `gestion.create_diagnosis` + helper;
- `CanReadOwnedOrManageDiagnosis`: ownership Cliente o
  `gestion.manage_technical_record` + helper;
- `CanFinalizeService`: permiso existente `gestion.finalize_service` para el
  endpoint asociado de finalización.

## Escritura y autoría

- El serializer ya no acepta `profesional` como campo escribible.
- `perform_create()` fuerza `profesional=request.user`.
- `finalizar_turno` también asigna `profesional=request.user` al diagnóstico
  post-servicio.
- Un payload no puede seleccionar arbitrariamente otro Usuario como autor.
- En update/PATCH no puede cambiarse el Cliente.
- Autor, fecha y resultados internos del motor (`regla`, rutinas, servicio y
  Turno sugeridos) son read-only.
- `recomendaciones` y datos capilares siguen siendo editables por un actor
  técnico autorizado.
- Sin `manage_technical_record`, un actor con capacidad de escritura sólo
  puede actualizar diagnósticos creados por él. Con dicho permiso puede
  operar el historial técnico global, siempre conservando permiso de creación
  y skill para escribir.

## Lectura Cliente y técnica

El Cliente no necesita `DIAGNOSTICO` ni `create_diagnosis` para leer su propio
historial. El queryset limita `list/retrieve`; `por_cliente` ya no permite
consultar un `cliente_id` ajeno. El endpoint de perfil de Usuario continúa
devolviendo únicamente el diagnóstico propio más reciente.

La lectura técnica global no se deduce de `create_diagnosis`: exige el permiso
existente `gestion.manage_technical_record` y la capacidad técnica activa. No
se creó un permiso nuevo.

## DELETE

`destroy` responde HTTP 405 para actores autenticados. El historial no se
elimina físicamente.

## Motor y recomendaciones

El motor clínico conserva sus dos niveles y mensajes actuales. No se añadió
evaluación de riesgo de BH-057.

El recomendador eliminó su prefiltrado por texto de categoría
`Diseño/Color/Complemento`. Ahora obtiene horarios con
`TurnoAvailabilityService.matching_schedules()` y genera slots con el mismo
servicio, por lo que respeta:

- `ServicioHabilidad`;
- `PersonalHabilidad` activa;
- `Habilidad` activa;
- restricciones temporales de horario;
- bloqueos, solapamientos y equipamiento de la disponibilidad canónica.

Una prueba funcional confirma que el texto de categoría no actúa como
autoridad.

## Finalización de Turnos

`finalizar_turno` era un bypass porque cualquier actor que alcanzara el Turno
podía producir un diagnóstico sin autor. Ahora requiere:

- `gestion.finalize_service`;
- `gestion.create_diagnosis`;
- Personal activo;
- skill `DIAGNOSTICO` activa.

El queryset de esta acción ya no depende de `is_staff` y el diagnóstico
post-servicio registra al Usuario actor.

## Frontend

No existe actualmente una pantalla frontend de creación/edición de
`DiagnosticoCapilar`; por seguridad no se inventó una ruta ni una autoridad de
skills en JavaScript. En consecuencia:

- no hay acción técnica existente que pueda quedar visible por `is_staff` o
  `BusinessRole`;
- `SessionContext` ya expone `hasPermission()` y
  `hasActiveProfile('personal')`, que es el contrato requerido cuando se
  incorpore esa pantalla;
- la skill permanece exclusivamente como autoridad backend;
- el Cliente conserva la lectura propia desde Perfil;
- el test de Header confirma que `create_diagnosis` por sí solo no habilita un
  módulo pendiente.

No hay consumidor frontend técnico donde mostrar un 403 por falta de skill;
el backend devuelve un mensaje seguro y falla cerrado. No se añadió código
muerto sólo para simular esa pantalla.

## ADMINISTRADOR, EMPLEADO y PROFESIONAL

Los tests demuestran que el `BusinessRole` no autoriza por sí mismo:

- ADMINISTRADOR `is_staff=False`, con permiso pero sin skill: 403;
- ADMINISTRADOR con Personal activo, permiso y skill: permitido;
- EMPLEADO con permiso individual y skill: permitido;
- PROFESIONAL con permiso efectivo y skill: permitido;
- permiso sin skill, skill sin permiso, Personal inactivo o Usuario sin
  Personal: 403.

## Flags legacy

`realiza_diagnostico`, `realiza_lavado` y `realiza_color` permanecen en el
modelo por compatibilidad, pero ya no son autoridad de Turnos ni Diagnóstico.
Se dejaron read-only en:

- `PersonalSerializer` (API);
- Django Admin;
- `GestionPersonal` (frontend).

Los tests prueban ambos sentidos del switch:

- `realiza_diagnostico=True` sin `PersonalHabilidad`: 403;
- `realiza_diagnostico=False` con asignación canónica activa: permitido.

La migración `0021` conserva el único uso legítimo de esos flags para backfill
histórico. Tests de compatibilidad y servicios de acceso también los leen para
verificar preservación de datos, no para autorizar Diagnóstico.

## Coincidencias `is_staff` restantes

- Dentro de `DiagnosticoCapilarViewSet`: **0**.
- En el flujo asociado de lectura propia, motor, recomendación y finalización:
  **0** como autoridad de diagnóstico.
- `gestion/views.py` todavía contiene **24** coincidencias en módulos no
  migrados por este incremento (Servicios, acciones legacy de Turnos,
  Rutinas, Ficha Técnica, promociones, contenido y otros). No se modificaron
  fuera del alcance solicitado.

## Tests y validación

Siempre se usó `venv\Scripts\python.exe` y UTF-8 para backend.

- Suite nueva de autorización de Diagnóstico: **26/26**.
- Skills, disponibilidad, creación/reprogramación, lectura/llegada de Turnos y
  Diagnóstico en ejecución combinada: **131/131** antes de dos casos
  adicionales; el conjunto de regresión previo aporta **107/107** y la suite
  final de Diagnóstico **26/26**.
- Personal security/access/status tras hacer flags read-only: **34/34**.
- Personal, roles, `/me/`, registro público y creación Cliente: **77/77**.
- Frontend `SessionContext`, Header, `GestionPersonal`, Operaciones y flujos
  Cliente relevantes: **79/79**.
- `manage.py check`: OK.
- `manage.py makemigrations --check`: sin cambios; Incremento C no crea
  migraciones.
- `compileall`: OK.
- `git diff --check`: OK, salvo advertencias informativas de normalización de
  fin de línea.

## Alcance excluido

- BH-057 no iniciado.
- Sin estados nuevos de evaluación.
- Sin cambios en Mercado Pago, pagos ni HOLD.

**BH-056 C = VALIDADO**
