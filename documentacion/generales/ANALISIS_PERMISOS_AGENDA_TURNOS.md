# Análisis de permisos de Agenda y Turnos

## 1. Alcance y conclusión ejecutiva

Este documento analiza exclusivamente la autorización de Agenda y Turnos. No propone migrar en este incremento Diagnóstico, Ficha Técnica, Fórmulas, Productos, Caja u Órdenes.

La implementación actual no puede habilitar correctamente a EMPLEADO, PROFESIONAL o ADMINISTRADOR con `is_staff=False`, aunque tengan permisos canónicos. A la vez, existen escrituras críticas expuestas bajo `IsAuthenticated`:

- un Cliente puede hacer `PATCH` de campos sensibles de su Turno propio y puede borrarlo;
- un Cliente puede invocar `finalizar_turno` sobre su Turno y disparar automatizaciones técnicas;
- cualquier Usuario autenticado puede intentar crear un bloqueo de agenda;
- una lectura de Turnos ejecuta cancelaciones globales como efecto colateral;
- seña, llegada y estados operativos se resuelven mediante `PATCH` genérico, sin autorización ni transición específica.

La migración no debe limitarse a sustituir `is_staff` por un único permiso. `TurnoViewSet` mezcla lectura, creación, edición genérica, ownership, pagos y transiciones. Debe autorizar por acción y separar los scopes Cliente propio, Personal propio y agenda global.

## 2. Autoridades objetivo

### 2.1 Permisos canónicos existentes

| Permiso | Capacidad exacta objetivo |
|---|---|
| `gestion.view_global_agenda` | Leer agenda global y resúmenes operativos de Turnos. No concede escritura, pagos ni finalización. |
| `gestion.create_turno_for_client` | Crear un Turno para un Cliente distinto del actor. |
| `gestion.register_arrival` | Registrar llegada/inicio operativo mediante una transición dedicada. |
| `gestion.reprogram_any_turno` | Reprogramar un Turno ajeno mediante una acción dedicada. |
| `gestion.cancel_any_turno` | Cancelar/rechazar un Turno ajeno mediante una acción dedicada. |
| `gestion.finalize_service` | Finalizar un servicio mediante una acción dedicada. |
| `gestion.confirm_deposit` | Confirmar una seña y la transición correspondiente. No equivale a registrar un movimiento de pago. |
| `gestion.register_payment` | Registrar un `Pago` asociado a un Turno. No concede lectura global de Caja. |

Los permisos base actuales de roles ya reflejan la política solicitada:

- EMPLEADO: todos los anteriores salvo `gestion.finalize_service`;
- PROFESIONAL: hereda EMPLEADO y agrega `gestion.finalize_service`;
- ADMINISTRADOR: accede por permisos efectivos de su Group, nunca por `role`, `is_staff` o `is_superuser`;
- permisos individuales deben producir exactamente el mismo resultado que permisos de Group.

### 2.2 Capacidades para las que falta una autoridad específica

Hay dos acciones que no deben reutilizar permisos de significado diferente:

1. **Aprobar una solicitud** (`solicitado -> esperando_sena`). No existe un permiso canónico para revisar/aprobar solicitudes. `confirm_deposit` no sirve: confirmar una seña es `esperando_sena -> confirmado`.
2. **Configurar horarios y bloqueos globales**. `view_global_agenda` es lectura y no debe habilitar estas escrituras.

Cambio mínimo recomendado:

- usar el permiso existente `gestion.manage_configuration` para CRUD de `HorarioLaboral`, configuración masiva y bloqueos globales, si se acepta que forman parte de la configuración del salón;
- crear `gestion.review_turno_requests` para aprobar solicitudes, o mantener esa acción fuera de EMPLEADO/PROFESIONAL hasta definir su autoridad. No se debe mapear silenciosamente a `confirm_deposit`.

Si se considera que `manage_configuration` es demasiado amplio, la alternativa más precisa es crear `gestion.manage_agenda_configuration`. No debe concederse a EMPLEADO por herencia sin una decisión explícita.

### 2.3 Ownership y scopes explícitos

La relación técnica fiable ya existe:

- `Personal.usuario`: `OneToOneField`, `related_name='perfil_profesional'`;
- `Turno.profesional`: FK a `Personal`;
- `Cliente.usuario`: relación del Cliente autenticado con sus Turnos.

Se proponen tres scopes sin usar `is_staff`:

1. **Cliente propio**: `turno.cliente.usuario == request.user`.
2. **Agenda laboral propia**: `turno.profesional.usuario == request.user`, con `Personal.activo=True` y Usuario activo.
3. **Agenda global**: `request.user.has_perm('gestion.view_global_agenda')`.

No conviene inferir el scope únicamente por “el primer perfil encontrado”: el sistema permite que un Usuario tenga simultáneamente perfiles Cliente y Personal. La API debe usar rutas o parámetros inequívocos, por ejemplo:

- `GET /turnos/mis-turnos/`: ownership Cliente;
- `GET /turnos/mi-agenda-laboral/`: ownership Personal;
- `GET /turnos/`: agenda global con `view_global_agenda`.

Puede preservarse temporalmente `/turnos/` para el Cliente por compatibilidad, pero el frontend debería migrar a un endpoint explícito.

## 3. Inventario backend

### 3.1 `TurnoViewSet`

Todo el ViewSet hereda actualmente `IsAuthenticated`. El queryset concede acceso global por `request.user.is_staff`, limita al Cliente por ownership y devuelve vacío a un Personal `is_staff=False`.

| Endpoint | Método | View/action | Autorización actual y ownership | Autorización objetivo | Cambio necesario | Riesgo actual |
|---|---:|---|---|---|---|---|
| `/api/gestion/turnos/` | GET | `TurnoViewSet.list` | `IsAuthenticated`; `is_staff` ve global, Cliente ve propios, Personal no staff ve vacío. | `view_global_agenda` para global; ownership Cliente en endpoint propio; ownership `Personal.usuario` en agenda laboral propia. | Separar scopes; eliminar `is_staff`; aplicar serializer mínimo de agenda. | **Crítico**: la lectura llama `_auto_cancel_expired_turnos()` y cualquier autenticado dispara escrituras/cancelaciones globales. Además bloquea usuarios con permiso efectivo y expone datos técnicos/financieros. |
| `/api/gestion/turnos/` | POST | `TurnoViewSet.create` + `TurnoSerializer.create` | `IsAuthenticated`; el serializer decide Turno ajeno vs propio por `user.is_staff`. | Cliente autenticado crea solo para sí; `create_turno_for_client` crea para el Cliente indicado. | Separar serializers/acciones de reserva propia y alta para Cliente; no bifurcar por `is_staff`. | **Alta**: staff sin permiso crea para terceros; ADMINISTRADOR/EMPLEADO no staff con permiso no puede. |
| `/api/gestion/turnos/{id}/` | GET | `retrieve` | `IsAuthenticated` + queryset anterior. | Uno de: ownership Cliente, ownership Personal asignado o `view_global_agenda`. | Object scope explícito y serializer por contexto. | **Alta**: staff es autoridad; Personal asociado no funciona; el serializer expone fórmula, impactos capilares, comprobante e importes. |
| `/api/gestion/turnos/{id}/` | PUT/PATCH | `update` / `partial_update` | `IsAuthenticated`; `perform_update` solo verifica ownership cuando `not is_staff`. | Deshabilitar actualización genérica; usar acciones de campo/transición específicas. Subida de comprobante: ownership Cliente y solo ese campo. | Rechazar campos no permitidos; migrar frontend a acciones dedicadas. | **Crítico**: un Cliente puede cambiar en su Turno propio `estado`, `cliente`, `profesional`, fecha, importes y otros campos escribibles. Staff sin permiso puede modificar cualquiera. |
| `/api/gestion/turnos/{id}/` | DELETE | `destroy` heredado | `IsAuthenticated` + queryset. No hay override. | `405 Method Not Allowed`; las bajas deben ser cancelaciones semánticas. | Deshabilitar `destroy`. | **Crítico**: un Cliente puede borrar físicamente su Turno; staff puede borrar cualquiera. |
| `/api/gestion/turnos/{id}/registrar_pago/` | POST | `registrar_pago` | Hereda `IsAuthenticated`; chequea `request.user.is_staff`; `get_object()` depende del queryset. | `gestion.register_payment`; acceso al objeto por el permiso de acción, no por staff. | Permission class canónica y validación de estado/importe. | **Alta**: staff sin permiso registra pagos; no staff con permiso no puede. No actualiza saldo ni estado del Turno. |
| `/api/gestion/turnos/{id}/reprogramar_cliente/` | POST | `reprogramar_cliente` | `IsAuthenticated`, queryset de Cliente y comprobación explícita de ownership. | Mantener ownership Cliente; no exigir `view_global_agenda`. | Preservar acción propia y reforzar reglas de slot/fecha. | **Media** de autorización: ownership correcto. Tiene inconsistencias de negocio descritas más abajo. |
| `/api/gestion/turnos/consultar_disponibilidad/` | GET | `consultar_disponibilidad` | `IsAuthenticated`; no usa ownership ni permiso global. | Disponibilidad de reserva, separada de agenda global. Puede ser pública con DTO mínimo o autenticada para Cliente. | Unificar política con `/disponibilidad/`; no devolver configuración interna ni motivos de bloqueo. | **Media**: no expone Turnos, pero devuelve nombres e IDs de Personal. La política difiere del otro endpoint público. |
| `/api/gestion/turnos/{id}/verificar-expiracion/` | GET | `verificar_expiracion` | `IsAuthenticated` + queryset. | Mismo scope que la lectura del Turno. | Aplicar ownership/agenda propia/global sin staff. | **Media**: no escribe directamente, pero depende del queryset legacy. |
| `/api/gestion/turnos/{id}/gestionar/` con `CONSULTAR` | POST | `gestionar_cancelacion` | `IsAuthenticated`; Cliente dueño por queryset. Intenta reconocer Personal con `hasattr(usuario, 'personal')`, relación inexistente. | Ownership Cliente para consultar sus reglas; lectura laboral propia o global solo si realmente se necesita. | Separar consulta de las mutaciones. Usar `perfil_profesional`. | **Alta**: autorización mezclada con payload; las comprobaciones de Personal no funcionan. |
| Mismo endpoint con `REPROGRAMAR` | POST | `gestionar_cancelacion` | Misma autorización; `is_staff` evita límites de tiempo. | Cliente dueño según reglas; para ajenos `reprogram_any_turno`. | Sustituir por acciones separadas; eliminar privilegio por staff. | **Alta**: staff sin permiso; relación Personal errónea; no valida disponibilidad del nuevo slot. |
| Mismo endpoint con `CANCELAR` | POST | `gestionar_cancelacion` | Misma autorización; Cliente propio o staff. | Cliente dueño según reglas; para ajenos `cancel_any_turno`. | Acción dedicada y validación de transición. | **Alta**: puede cancelar estados finales; staff sin permiso; autorización depende del tipo de payload. |
| `/api/gestion/turnos/{id}/gestionar-profesional/` con `REPROGRAMAR` | POST | `gestionar_profesional` | `IsAuthenticated`; acepta `is_staff` o `hasattr(usuario, 'profesional')`. Esa relación tampoco existe (`perfil_profesional` es la real). | `gestion.reprogram_any_turno`. | Separar reprogramar/cancelar o comprobar el permiso según acción; validar slot. | **Alta**: staff sin permiso puede; PROFESIONAL no staff con permiso falla y normalmente ni encuentra el objeto. |
| Mismo endpoint con `CANCELAR` | POST | `gestionar_profesional` | Igual al anterior. | `gestion.cancel_any_turno`. | Acción o permiso específico por payload. | **Alta**: mismo bypass por staff y ausencia de validación de estado. |
| `/api/gestion/turnos/{id}/finalizar_turno/` | POST | `finalizar_turno` | Solo `IsAuthenticated` + queryset; únicamente rechaza si ya está `realizado`. | `gestion.finalize_service`. | Permission class canónica; transición válida; desacoplar efectos técnicos. | **Crítico**: un Cliente puede finalizar su Turno propio. Puede finalizar solicitado, cancelado o ausente y dispara diagnóstico, rutinas, cuidados y promociones. |

#### Efectos adicionales del serializer actual

`TurnoSerializer` no es un contrato seguro para todos los scopes:

- `estado`, `cliente`, `profesional`, `equipamiento`, `tipo_pago_registro` y `monto_abonado` son escribibles;
- `DetalleTurnoSerializer` expone `servicio_plantilla_formula` e impactos de diagnóstico;
- lista y detalle incluyen `comprobante_pago`, importes y saldo.

Por tanto, `view_global_agenda` debe usar un serializer operativo mínimo: identificación del Turno, Cliente necesario para atención, servicio visible, profesional, fecha/hora y estado. No debe conceder por sí solo fórmulas, ficha técnica, diagnóstico ni historia financiera.

### 3.2 Agenda, disponibilidad, horarios y bloqueos

| Endpoint | Método | View/action | Autorización actual | Autorización objetivo | Cambio necesario | Riesgo actual |
|---|---:|---|---|---|---|---|
| `/api/gestion/disponibilidad/` | GET | `DisponibilidadTurnosView` | `AllowAny`. | Mantener público si es el endpoint de reserva; respuesta mínima de slots. No requiere `view_global_agenda`. | Unificar cálculo con el endpoint de disponibilidad usado por Cliente; no exponer agenda interna. | **Media**: la apertura puede ser legítima, pero hay dos algoritmos/políticas diferentes y este no aplica de forma clara todos los bloqueos/profesionales. |
| `/api/gestion/obtener_disponibilidad_calendario/` | GET | `obtener_disponibilidad_calendario` | `AllowAny`. Devuelve todas las reglas y bloqueos si no hay `personal_id`. | Vista interna: `view_global_agenda`; vista propia: `Personal.usuario`; si se necesita una vista pública, crear DTO distinto sin motivos ni configuración. | Cerrar endpoint interno y separar disponibilidad pública. | **Alta**: anónimo obtiene horarios laborales, IDs de Personal, rangos y motivos de bloqueos/ausencias. |
| `/api/gestion/agenda/general/` | GET | `obtener_agenda_general` | `IsAuthenticated`; permite cualquier `personal_id` y, sin ID, usa el primer Personal activo. | Propia por `request.user.perfil_profesional`; otra/global con `view_global_agenda`. | Validar scope; eliminar fallback al “primer profesional”. | **Alta**: cualquier autenticado consulta horarios y motivos de bloqueo de cualquier Personal. |
| `/api/gestion/agenda/bloquear/` | POST | `crear_bloqueo` | Solo `IsAuthenticated`; ignora actor y siempre selecciona el primer colorista activo. | `gestion.manage_configuration` (o nuevo `manage_agenda_configuration`). | Autorización canónica y Personal objetivo explícito; nunca hardcodear rol/colorista. | **Crítico**: cualquier Cliente autenticado puede bloquear la agenda del colorista. |
| `/api/gestion/horariolaboral/` | GET | `HorarioLaboralViewSet.list` | `IsAdminUser`. | `view_global_agenda` para lectura global; agenda propia por ownership si hace falta. | Permisos por acción. | **Alta**: staff sin permiso entra; usuarios efectivos no staff reciben 403. |
| `/api/gestion/horariolaboral/{id}/` | GET | `retrieve` | `IsAdminUser`. | Igual que lectura anterior, con object scope. | Permisos por acción. | **Alta** por autoridad legacy. |
| `/api/gestion/horariolaboral/` | POST | `create` | `IsAdminUser`. | `gestion.manage_configuration` o permiso específico de agenda. | Permiso de escritura distinto de `view_global_agenda`. | **Alta**: staff decide; no staff autorizado no puede. |
| `/api/gestion/horariolaboral/{id}/` | PUT/PATCH/DELETE | CRUD heredado | `IsAdminUser`. | `gestion.manage_configuration` o permiso específico de agenda. | Permission class canónica. | **Alta** por bypass/bloqueo basado en staff. |
| `/api/gestion/horariolaboral/configurar_rango/` | POST | `configurar_rango` | `IsAdminUser`. Puede aplicar a todo el Personal. | `gestion.manage_configuration` o permiso específico de agenda. | Permiso canónico; validar payload y alcance. | **Alta**: operación masiva gobernada por staff. |
| `/api/gestion/horariolaboral/limpiar_agenda/?personal_id=` | DELETE | `limpiar_agenda` | `IsAdminUser`. | `gestion.manage_configuration` o permiso específico de agenda. | Permiso canónico y auditoría. | **Alta**: borrado masivo gobernado por staff. |
| `/api/gestion/admin-dashboard/stats/` | GET | `AdminDashboardStatsView` | `IsAdminUser`; consulta Turnos globales y nombres de Clientes. | `gestion.view_global_agenda` para la parte operativa. Otros KPIs deben tener permisos propios. | No reutilizar un dashboard heterogéneo para `/operaciones`; crear resumen operativo mínimo o reducir este contrato. | **Alta**: ADMINISTRADOR no staff falla y staff sin permiso ve datos globales. |
| `/api/gestion/mi-agenda/` | GET | `MiAgendaCuidadosView` | `IsAuthenticated`; filtra `AgendaCuidados` por `request.user.cliente`. | Mantener ownership Cliente. No pertenece a agenda de Turnos. | Excluir de la migración operativa salvo tests de regresión. | **Baja** de autorización; puede fallar para autenticados sin perfil Cliente, pero no filtra datos ajenos. |

### 3.3 Pagos y seña

| Endpoint/operación | Método | Autorización actual | Objetivo | Observación |
|---|---:|---|---|---|
| `/turnos/{id}/registrar_pago/` | POST | `IsAuthenticated` + `is_staff` | `gestion.register_payment` | Registrar movimiento. No debe confirmar por sí solo la seña salvo regla transaccional explícita. |
| Confirmar seña en Turno | PATCH genérico a `estado=confirmado` | `IsAuthenticated` + queryset/`is_staff` | Acción dedicada con `gestion.confirm_deposit` | Hoy no existe endpoint dedicado ni validación de estado/comprobante. |
| Subir comprobante propio | PATCH genérico | Ownership indirecto, pero permite todos los demás campos | Acción/campo dedicado por ownership Cliente | No requiere `confirm_deposit`; subir evidencia no es confirmarla. |
| `/api/gestion/pagos/` y `/pagos/{id}/` | GET | `IsAdminUser` | `gestion.view_financial_reports` o un futuro permiso de lectura de pagos | Es Caja/historial, no debe abrirse por `register_payment`. Mantener fuera del primer incremento operativo. |

`confirm_deposit`, `register_arrival` y los demás permisos canónicos aparecen en modelos/roles, pero no están aplicados a acciones de Turno. En particular, **no existe una acción backend de llegada**; hoy solo sería posible enviar un estado por `PATCH` genérico.

### 3.4 Dependencias auxiliares

- `GET /api/gestion/personal/` usa `IsAuthenticated` y devuelve el listado general de Personal. `GestionTurnos` y Agenda lo usan como selector. No se debe abrir todo `PersonalViewSet` como efecto colateral de Agenda. Conviene un selector mínimo de Personal activo autorizado por `view_global_agenda` o `create_turno_for_client`, y un DTO público todavía más reducido si reserva permite elegir profesional.
- El selector de Clientes de Nuevo Turno debe ser un contrato interno del flujo Turnos. Puede exigir `create_turno_for_client` y devolver solo identificación mínima, o exigir además `usuarios.view_clients`. No debe depender de `is_staff` ni ampliar el módulo Clientes.

## 4. Autorización versus reglas de negocio/estado

Tener permiso responde **quién puede intentar la acción**. La transición de estado responde **si esa acción es válida para ese Turno**. Ambas comprobaciones son obligatorias y separadas.

| Operación | Autorización objetivo | Validación de estado actual | Regla objetivo mínima |
|---|---|---|---|
| Aprobar solicitud | Nuevo `review_turno_requests` (decisión pendiente) | `PATCH` acepta cualquier cambio; no hay transición dedicada. | Solo `solicitado -> esperando_sena`; calcular una vez `fecha_limite_pago`. |
| Registrar llegada | `register_arrival` | No existe acción; `PATCH` puede escribir `en_proceso` desde cualquier estado. | Acción dedicada; normalmente `confirmado -> en_proceso`; impedir repetición/finales. |
| Reprogramar propio | Ownership Cliente | `reprogramar_cliente` acepta solo `solicitado` y `esperando_sena`; el bloque para `confirmado` es código inalcanzable. Valida conflictos, pero no demuestra de forma completa horario laboral/futuro. | Definir expresamente estados permitidos; validar futuro, regla laboral, bloqueo, profesional, equipamiento y duplicados de forma atómica. |
| Reprogramar ajeno | `reprogram_any_turno` | `gestionar-profesional` no valida estado ni disponibilidad; `gestionar` tiene validaciones distintas. | Estados permitidos explícitos; slot disponible; bloqueo/recursos; auditoría y motivo. |
| Cancelar propio | Ownership Cliente | `gestionar` aplica ventana temporal, pero no impide cancelar `realizado`, `cancelado` u otros finales. | Estados cancelables explícitos, ventana temporal y operación idempotente. |
| Cancelar ajeno/rechazar | `cancel_any_turno` | Acción profesional no valida estado; el `PATCH` genérico tampoco. | Transiciones permitidas y motivo; no borrar físicamente. |
| Subir comprobante | Ownership Cliente | No se limita el PATCH al archivo ni al estado. | Solo campo `comprobante_pago`, solo Turno propio y estado permitido. |
| Confirmar seña | `confirm_deposit` | Se hace por `PATCH estado=confirmado`; sin comprobar estado, evidencia o pago. | Solo `esperando_sena -> confirmado`; verificar comprobante o Pago válido según política. |
| Registrar pago | `register_payment` | Solo valida monto positivo en frontend y comprobante para transferencia en serializer; no valida estado ni saldo. | Monto > 0, no exceder política/saldo, estado compatible, transacción atómica y auditoría. |
| Finalizar | `finalize_service` | Solo evita finalizar dos veces por la acción; el PATCH genérico puede marcar `realizado` directamente. | Solo desde estado operativo definido (`en_proceso` o el acordado), una vez, con efectos idempotentes. |

### Acoplamiento técnico de finalización

`finalizar_turno` no es hoy una simple transición. También crea Diagnóstico, asigna Rutinas/cuidados y genera Promociones. Además, señales `post_save` sobre `Turno` vuelven a ejecutar automatizaciones mientras el estado sea `realizado`, no solo en la transición.

Para esta migración:

- el botón operativo de finalizar debe depender únicamente de `finalize_service`;
- Ficha Técnica, Fórmulas y Diagnóstico deben conservar sus permisos propios y no ser requisito implícito para autorizar la transición;
- los efectos post-servicio deben moverse a un servicio de dominio idempotente o detectar cambio real de estado;
- el frontend no debe obligar a abrir `RegistroFichaTecnica` para poder invocar la finalización si el actor solo tiene `finalize_service`.

## 5. Inventario frontend y permiso objetivo

| Pantalla/acción | Estado actual | Permiso/ownership objetivo |
|---|---|---|
| `/operaciones` (`Operaciones.js`) | Protegida por `allowedRoles=['EMPLEADO','PROFESIONAL']`; componente también compara BusinessRole. Está vacía. | Quitar autorización por rol. Mostrar cada tarjeta/acción por permisos efectivos. ADMINISTRADOR con permisos también debe poder entrar. |
| `/admin/turnos` (`GestionTurnos.js`) | Ruta solo autenticada. Carga agenda global y presenta todos los botones sin revisar permisos. | Ruta/lectura: `view_global_agenda`. Cada botón debe tener su permiso propio. |
| Listado, búsqueda y filtros de Turnos | Depende de backend `is_staff`; Personal no staff recibe lista vacía. | `view_global_agenda`; agenda propia en vista separada por `Personal.usuario`. |
| Rechazar/“No pagó” | `PATCH estado=cancelado`. | `cancel_any_turno`; acción backend dedicada. |
| Aprobar solicitud | `PATCH estado=esperando_sena`. | Nuevo `review_turno_requests`; no reutilizar `confirm_deposit`. |
| Confirmar Pago/Seña | `PATCH estado=confirmado`; si es efectivo, primero abre PagoModal. | `confirm_deposit`; el flujo efectivo requiere además `register_payment`. |
| Reprogramar Turno ajeno | `gestionar-profesional` sin guard frontend. | `reprogram_any_turno`. |
| Cancelar Turno ajeno | Misma acción multiplexada. | `cancel_any_turno`. |
| Registrar Pago (`PagoModal`) | Siempre disponible en estado confirmado; POST a `registrar_pago`. Después puede marcar realizado por PATCH. | `register_payment`. Registrar pago no debe finalizar automáticamente. |
| Registrar llegada | No existe botón/componente ni endpoint dedicado. | `register_arrival`; agregar acción dedicada después del backend. |
| Finalizar Servicio | Abre Ficha Técnica y luego `finalizar_turno`; también existe PATCH directo a `realizado`. | `finalize_service`; eliminar PATCH directo. Ficha/fórmula se muestran solo con permisos técnicos y como flujo separado. |
| `/admin/nuevo-turno` (`NuevoTurno.js`) | Ruta solo autenticada; POST sin header explícito, depende del interceptor; backend bifurca por staff. | `create_turno_for_client`. Selector mínimo de Cliente; disponibilidad no requiere `view_global_agenda`. |
| `/admin/agenda` (`AgendaAdmin.js`) | Ruta solo autenticada. Lee endpoint público y permite configurar/bloquear a cualquiera que llegue a la pantalla. | Vista: `view_global_agenda`; botones de configurar horarios y bloqueo: `manage_configuration` o permiso específico. |
| `ConfiguracionAgendaMasiva.js` | Lee endpoint público; POST/DELETE requieren `IsAdminUser`. | `manage_configuration` o permiso específico; ocultar modal/botones sin ese permiso. |
| `Calendario.js` | Componente presentacional; no autoriza. | Hereda permiso de la fuente de datos. Si recibe Turnos globales, `view_global_agenda`. |
| `/admin-dashboard` (`DashboardAdmin.js`) | Ruta autenticada; backend `IsAdminUser`; accesos rápidos no se filtran por permiso. | La sección Turnos/calendario requiere `view_global_agenda`. No usar este dashboard heterogéneo como backend de `/operaciones`. |
| `/mis-turnos` (`MisTurnos.js`) | Ruta exige perfil Cliente. Usa listado, PATCH de comprobante y acciones propias. | Ownership Cliente. Nunca `view_global_agenda`. Migrar a endpoints propios explícitos. |
| `/reservar` (`ReservaCliente.js`) | Ruta exige perfil Cliente; disponibilidad y POST de Turno propio. | Ownership/perfil Cliente. Nunca `create_turno_for_client` ni `view_global_agenda`. |

## 6. Diseño mínimo de `/operaciones`

### 6.1 Backend mínimo para la experiencia solicitada

| Elemento en `/operaciones` | Contrato backend mínimo | Autoridad |
|---|---|---|
| Turnos de hoy | `GET` global filtrable por fecha, con serializer operativo mínimo | `view_global_agenda` |
| Agenda | Mismo contrato por rango o endpoint de agenda operativo | `view_global_agenda` |
| Nuevo Turno | Acción de creación para tercero + disponibilidad + selector mínimo de Cliente | `create_turno_for_client`; disponibilidad separada; selector acotado |
| Nuevo Cliente | Ya disponible por el trabajo de Clientes | `usuarios.create_walkin_client` |
| Registrar llegada | Nueva acción `POST /turnos/{id}/registrar-llegada/` | `register_arrival` |

No hace falta migrar DashboardAdmin, diagnósticos, ficha, fórmulas, Caja ni finalización para entregar este panel inicial.

### 6.2 Primer incremento útil recomendado

El primer incremento debe combinar **contención crítica y lectura canónica**:

1. eliminar el efecto global `_auto_cancel_expired_turnos()` de los `GET` y dejar el vencimiento en tarea/command autorizado;
2. impedir `PUT/PATCH/DELETE` genéricos inseguros, preservando la subida de comprobante mediante contrato acotado;
3. implementar lectura global con `gestion.view_global_agenda`, agenda propia por `Personal.usuario` y ownership Cliente en rutas inequívocas;
4. usar serializer operativo sin fórmulas, diagnóstico ni datos financieros;
5. migrar la ruta frontend de lectura a `requiredPermission="gestion.view_global_agenda"` y quitar checks de rol/staff.

Después de ese primer incremento, `/operaciones` podrá mostrar de forma segura **Turnos de hoy y agenda de solo lectura** a EMPLEADO, PROFESIONAL y ADMINISTRADOR por permisos efectivos. También podrá mostrar el acceso a **Nuevo Cliente**, ya migrado, si existe `usuarios.create_walkin_client`. Nuevo Turno y Registrar llegada deben esperar sus incrementos de escritura dedicados.

## 7. Endpoints demasiado abiertos

### Prioridad crítica

1. `PUT/PATCH/DELETE /turnos/{id}/`: escritura y borrado genéricos para Cliente dueño; staff sin permisos específicos.
2. `POST /turnos/{id}/finalizar_turno/`: Cliente dueño puede finalizar y activar efectos técnicos.
3. `POST /agenda/bloquear/`: cualquier autenticado puede bloquear agenda.
4. `GET /turnos/`: cualquier autenticado dispara la cancelación automática global desde una lectura.

### Prioridad alta

1. `POST /turnos/{id}/gestionar/`: acción multiplexada, checks de Personal incorrectos y estados insuficientes.
2. `POST /turnos/{id}/gestionar-profesional/`: staff sustituye permisos; relación Personal incorrecta.
3. `POST /turnos/{id}/registrar_pago/`: staff sustituye `register_payment`.
4. `POST /turnos/`: staff sustituye `create_turno_for_client`.
5. `GET /agenda/general/`: cualquier autenticado puede leer agenda/bloqueos de otro Personal.
6. `GET /obtener_disponibilidad_calendario/`: anónimo ve configuración y motivos de bloqueos.
7. `HorarioLaboralViewSet`, dashboard y pagos: `IsAdminUser` permite staff sin permiso y bloquea permisos efectivos.

### Prioridad media

1. `GET /turnos/consultar_disponibilidad/`: política duplicada y exposición de nombres/IDs de Personal; no equivale a agenda global.
2. `GET /turnos/{id}/verificar-expiracion/`: depende del queryset legacy, aunque el objeto queda acotado.
3. `GET /disponibilidad/`: apertura pública probablemente válida, pero debe unificarse y minimizarse.

## 8. Orden de implementación recomendado

### Incremento 0 — Contención

- sacar cancelaciones automáticas de los `GET`;
- deshabilitar borrado físico;
- limitar o retirar actualización genérica;
- asegurar que Cliente solo pueda subir comprobante propio mediante un contrato de campo único;
- introducir helpers/permission classes reutilizables basadas en `user.has_perm(...)`, nunca `is_staff`.

### Incremento A — Lectura y scopes

- `view_global_agenda` para global;
- agenda propia con `Personal.usuario`;
- Turnos propios con ownership Cliente;
- serializer operativo mínimo;
- resumen de Turnos de hoy para `/operaciones`.

### Incremento B — Creación

- reserva propia de Cliente separada;
- creación para tercero con `create_turno_for_client`;
- selector mínimo de Cliente y Personal;
- eliminar bifurcación por `is_staff` del serializer.

### Incremento C — Llegada

- acción dedicada con `register_arrival`;
- transición de estado y tests;
- botón en `/operaciones` condicionado por permiso.

### Incremento D — Reprogramación y cancelación

- conservar ownership Cliente y reglas propias;
- acciones ajenas con `reprogram_any_turno` y `cancel_any_turno`;
- retirar `gestionar-profesional` multiplexado y checks de relaciones inexistentes.

### Incremento E — Solicitudes, seña y pagos

- decidir/agregar `review_turno_requests`;
- acción `confirmar-sena` con `confirm_deposit`;
- `registrar_pago` con `register_payment`;
- no abrir historial de Caja con `register_payment`.

### Incremento F — Finalización

- `finalize_service`;
- transición válida e idempotente;
- desacoplar Ficha/Diagnóstico/Fórmulas y automatizaciones post-servicio.

### Incremento G — Configuración de agenda

- migrar HorarioLaboral, configuración masiva y bloqueos a `manage_configuration` o al permiso específico acordado;
- mantener `view_global_agenda` como solo lectura.

## 9. Matriz de pruebas requerida

### 9.1 Autorización transversal

| Actor/condición | Lectura global | Propios Cliente | Agenda propia Personal | Crear para Cliente | Llegada | Reprogramar/cancelar ajeno | Confirmar seña/pago | Finalizar |
|---|---|---|---|---|---|---|---|---|
| Anónimo | 401 | 401 | 401 | 401 | 401 | 401 | 401 | 401 |
| CLIENTE normal | 403 global | 200 solo propios | 403 | 403; reserva propia sí | 403 | 403; propias según reglas | subir comprobante propio sí; confirmar/registrar no | 403 |
| EMPLEADO `is_staff=False` con permisos base | 200 | Según perfil Cliente en endpoint propio | 200 si Personal vinculado | 201 | 200 | 200 | 200 | 403 |
| PROFESIONAL `is_staff=False` | 200 | Según perfil Cliente | 200 si Personal vinculado | 201 | 200 | 200 | 200 | 200 |
| ADMINISTRADOR `is_staff=False` con permisos efectivos | 200 | Según perfil Cliente | Según vínculo, no necesario para global | 201 | 200 | 200 | 200 | 200 |
| Usuario con permiso individual | Solo la acción concedida | Ownership independiente | Ownership independiente | Solo si tiene el permiso exacto | Ídem | Ídem | Ídem | Ídem |
| Staff sin permiso canónico | 403 | Solo ownership real si además es Cliente | Solo agenda propia si Personal vinculado | 403 | 403 | 403 | 403 | 403 |
| Personal vinculado sin `view_global_agenda` | 403 global | Según perfil Cliente | 200 solo Turnos asignados | 403 | Según permiso | Según permiso | Según permiso | Según permiso |
| Personal inactivo o Usuario inactivo | Sin agenda laboral propia | Según política de cuenta activa | 403 | 403 | 403 | 403 | 403 | 403 |

Para objetos fuera del ownership se recomienda `404` para evitar enumeración; la falta de permiso global/acción debe devolver `403`. Sin autenticación, `401`. La disponibilidad pública es la excepción deliberada y debe devolver solo slots mínimos.

### 9.2 Casos backend por acción

1. Lista global con EMPLEADO/PROFESIONAL/ADMINISTRADOR `is_staff=False` y permiso: 200.
2. Staff sin `view_global_agenda`: 403.
3. Cliente lista solo sus Turnos; no obtiene Turnos ajenos al adivinar ID.
4. Personal sin permiso global obtiene solo `Turno.profesional.usuario == actor` en agenda propia.
5. Usuario con perfiles Cliente y Personal obtiene cada scope por endpoint explícito, sin unión accidental.
6. `GET` de Turnos no modifica estados ni crea notificaciones.
7. Serializer de agenda no contiene fórmula, impactos diagnósticos, comprobante, importes ni saldo.
8. Reserva propia ignora/rechaza `cliente` ajeno y campos administrativos.
9. Creación para tercero exige `create_turno_for_client`, incluido permiso individual.
10. `PUT/PATCH/DELETE` genéricos devuelven 405 o rechazan todos los campos fuera del contrato mínimo.
11. Cliente puede subir comprobante solo a Turno propio y en estado permitido.
12. Llegada exige `register_arrival` y solo permite transición acordada.
13. Reprogramación/cancelación ajena prueba permisos por separado; tener uno no concede el otro.
14. `confirm_deposit` no concede `register_payment`, y viceversa.
15. Registrar pago valida monto, saldo, método, comprobante y estado; es atómico.
16. Finalizar exige `finalize_service`; EMPLEADO base recibe 403 y PROFESIONAL 200.
17. Finalización desde estado inválido falla aunque el actor tenga permiso.
18. Reintento de finalizar no duplica cuidados, diagnósticos, rutinas, promociones ni notificaciones.
19. `view_global_agenda` solo no permite crear, reprogramar, cancelar, cobrar, confirmar ni finalizar.
20. Bloqueos/horarios requieren el permiso de configuración acordado; `view_global_agenda` solo recibe 403 en escritura.
21. Anónimo no recibe reglas internas ni motivos de bloqueos; solo disponibilidad pública mínima.

### 9.3 Casos frontend

1. `/operaciones`, `/admin/turnos`, `/admin/nuevo-turno` y `/admin/agenda` no usan `allowedRoles`, BusinessRole ni `is_staff` para acciones migradas.
2. ADMINISTRADOR con permisos y `is_staff=False` ve las mismas capacidades efectivas.
3. Gestión de Turnos requiere `view_global_agenda`; URL directa sin permiso termina en acceso denegado.
4. Botones se muestran independientemente para `register_arrival`, `reprogram_any_turno`, `cancel_any_turno`, `confirm_deposit`, `register_payment` y `finalize_service`.
5. EMPLEADO no ve Finalizar; PROFESIONAL sí.
6. PagoModal requiere `register_payment`; Confirmar Seña requiere `confirm_deposit`; el flujo en efectivo comprueba ambos.
7. Nuevo Turno requiere `create_turno_for_client`; Nuevo Cliente conserva `usuarios.create_walkin_client`.
8. Configurar horarios/bloqueos no aparece solo por `view_global_agenda`.
9. MisTurnos y ReservaCliente siguen funcionando por perfil/ownership sin `view_global_agenda`.
10. Respuestas 401 cierran/redirigen sesión según contrato; 403 muestran mensaje seguro y no habilitan fallback por rol.

## 10. Archivos afectados en una implementación posterior

### Backend

- `bohemiacore/gestion/views.py`: permisos por acción, scopes, acciones dedicadas, dashboard operativo y eliminación de efectos en GET.
- `bohemiacore/gestion/serializers.py`: serializers separados para agenda, reserva propia, creación interna, comprobante y transiciones.
- `bohemiacore/gestion/models.py`: solo si se agrega `review_turno_requests` o permiso específico de configuración de agenda.
- `bohemiacore/gestion/urls.py`: si se crean endpoints explícitos fuera de actions/router.
- `bohemiacore/gestion/services.py`: validación única de disponibilidad y servicio transaccional/idempotente de estados.
- `bohemiacore/gestion/signals.py`: evitar automatizaciones repetidas y desacoplar finalización técnica.
- `bohemiacore/gestion/filters.py`: filtros de agenda global sobre queryset ya autorizado.
- `bohemiacore/usuarios/roles.py`: catálogo/asignación solo si se agrega un permiso nuevo.
- tests nuevos de autorización de Turnos/Agenda; actualmente no hay cobertura API específica de estos permisos.

### Frontend

- `frontend/src/routes/index.js`: guards declarativos por permiso, sin roles.
- `frontend/src/pages/session/Operaciones.js`: panel incremental por capacidades.
- `frontend/src/pages/admin/GestionTurnos.js`: botones por permiso y endpoints dedicados.
- `frontend/src/pages/admin/NuevoTurno.js`: guard, autenticación y contrato de creación interna.
- `frontend/src/pages/admin/AgendaAdmin.js`: separar lectura de configuración/bloqueos.
- `frontend/src/pages/admin/ConfiguracionAgendaMasiva.js`: permiso de configuración.
- `frontend/src/pages/admin/DashboardAdmin.js`: guard de datos operativos o dejarlo fuera de `/operaciones`.
- `frontend/src/pages/admin/Calendario.js`: sin autorización propia; consumir solo datos ya autorizados.
- `frontend/src/components/admin/PagoModal.js`: `register_payment`, sin transición automática a realizado.
- `frontend/src/pages/cliente/MisTurnos.js` y `ReservaCliente.js`: endpoints explícitos de ownership.
- `frontend/src/navigation/navigationConfig.js`: visibilidad por permisos efectivos.

## 11. Cierre

### Brechas críticas

- CRUD genérico de Turno permite escritura sensible y borrado bajo `IsAuthenticated`.
- `finalizar_turno` permite que un Cliente finalice su propio Turno y active módulos técnicos.
- cualquier autenticado puede crear bloqueos de agenda.
- leer Turnos provoca cancelaciones globales.
- seña y estados operativos se cambian por PATCH sin permisos ni transiciones dedicadas.
- `is_staff` es autoridad de agenda global, creación, pagos y acciones profesionales; los permisos canónicos existentes todavía no gobiernan esos endpoints.

### Primer cambio recomendado

Implementar primero contención más lectura canónica: retirar efectos de escritura del GET, cerrar CRUD genérico inseguro, separar scopes Cliente/Personal/global y aplicar `gestion.view_global_agenda` con un serializer operativo mínimo.

### Permisos exactos del primer cambio

- `gestion.view_global_agenda` para lectura global;
- ownership `Cliente.usuario` para Turnos propios;
- ownership `Personal.usuario` para agenda laboral propia;
- ningún permiso de lectura concede escritura;
- `usuarios.create_walkin_client` permanece como capacidad independiente ya disponible para el acceso “Nuevo Cliente”.

### Resultado visible en `/operaciones`

Tras el primer incremento, `/operaciones` podrá mostrar Turnos de hoy y agenda de solo lectura a EMPLEADO, PROFESIONAL y ADMINISTRADOR por permisos efectivos, además del acceso a Nuevo Cliente cuando corresponda. Los botones Nuevo Turno y Registrar llegada se incorporarán en los siguientes incrementos con `create_turno_for_client` y `register_arrival`, sin abrir pagos, finalización ni módulos técnicos.
