# BH-060 — Análisis de tests automatizados de permisos por rol

## 1. Alcance, baseline y método

Este análisis se realizó sobre el commit:

```text
9bad62c235a4fa88a6f470664805cf57a9f47af1
```

`HEAD` y `origin/save/work-in-progress` coincidían al iniciar la revisión. No se
modificaron código, tests, migraciones, configuración ni datos de aplicación.

Se inspeccionaron:

- `usuarios/roles.py`, permisos DRF y servicios semánticos de acceso;
- rutas, ViewSets, APIViews y funciones legacy de `usuarios` y `gestion`;
- servicios de turnos, inventario, órdenes, pagos y resolución financiera;
- Django Admin;
- tests de Usuarios, Cliente, Personal, diagnóstico, turnos, habilidades,
  riesgo técnico, inventario, órdenes, pagos, incidencias y auditoría;
- suites representativas ejecutadas secuencialmente sobre PostgreSQL.

### 1.1 Criterio de clasificación

| Estado | Criterio |
|---|---|
| **CUBIERTO** | Hay pruebas positivas y negativas representativas del permiso efectivo y, cuando aplica, ownership/habilidad/estado. Los bypasses principales tienen aserción explícita. |
| **PARCIAL** | Hay tests útiles, pero falta al menos una dimensión relevante: rol, permiso individual, `is_staff`, ownership, inactivo, escalamiento, acción o ruta alternativa. |
| **SIN COBERTURA** | No se localizó una prueba de autorización de la operación, aunque pueda haber tests funcionales del modelo o servicio. |

La clasificación evalúa **cobertura automatizada**, no sólo si el código parece
correcto. Los defectos verificables por inspección se registran por separado.

## 2. Permiso base del rol frente a permiso efectivo

La pertenencia a un `BusinessRole` concede permisos Django mediante grupos. La
decisión real en los flujos canónicos es `user.has_perm(...)`, que combina:

1. permisos del grupo de rol de negocio;
2. permisos individuales;
3. permisos de otros grupos técnicos;
4. la regla especial de superusuario de Django;
5. el estado activo del usuario aplicado por el backend de autenticación.

Por tanto, “rol autorizado por defecto” no significa “única forma de obtener la
capacidad”. Un actor de otro rol puede operar si recibe el permiso efectivo y
cumple los requisitos adicionales. A la inversa, `is_staff=True` no debe
sustituir el permiso de negocio.

### 2.1 Permisos base

| Rol | Permisos base relevantes |
|---|---|
| **CLIENTE** | Ninguno del catálogo de negocio. Conserva operaciones propias por autenticación, perfil y ownership. |
| **EMPLEADO** | Clientes walk-in/lectura, agenda global, turno para cliente, llegada, reprogramación/cancelación, registro de pago y lectura de stock. |
| **PROFESIONAL** | Base de EMPLEADO excepto registro de pago; además diagnóstico, ficha técnica nominal, fórmulas, rutinas, finalización y revisión técnica. |
| **ADMINISTRADOR** | Los 33 permisos de `BusinessPermission.ALL`. |

### 2.2 Matriz rol × operación × prueba

Leyenda: **B** = autorizado por permiso base; **O** = sólo datos propios;
**H** = exige habilidad/perfil activo; **—** = no autorizado por defecto;
**E** = existe evidencia automatizada representativa; **F** = falta evidencia
específica. Una concesión individual puede cambiar **—** a autorizado.

| Operación | CLIENTE | EMPLEADO | PROFESIONAL | ADMINISTRADOR | Evidencia |
|---|---:|---:|---:|---:|---|
| Consultar/modificar perfil propio | O | O | O | O | **E** |
| Listar Clientes | — | B | B | B | **E** |
| Administrar usuarios/cuentas | — | — | — | B | **E** |
| Asignar/cambiar BusinessRole | — | — | — | B | **E**; exige también `manage_users` |
| Administrar Personal | — | — | — | B | **E** |
| Gestionar habilidades | — | — | — | B | **E** |
| Leer agenda global | — | B | B | B | **E** en endpoint canónico |
| Leer turnos propios/asignados | O | O | O | B | **E** |
| Reservar turno propio | O | — | — | — | **E** |
| Crear turno para Cliente | — | B | B | B | **E** |
| Llegada/reprogramar/cancelar cualquier turno | — | B | B | B | **E** |
| Crear diagnóstico | — | — | B+H | B+H | **E** |
| Leer historial técnico global | O propio | — | B+H | B+H | **E** |
| Finalizar servicio | — | — | B+H | B+H | **E** |
| Gestionar ficha/fórmula | — | — | B nominal | B nominal | **F**; implementación usa `is_staff` |
| Gestionar rutinas | selección O | — | B nominal | B nominal | **F**; implementación usa `is_staff` |
| Leer stock interno | — | B | B | B | **E** |
| Gestionar producto/precio/stock/promoción | — | — | — | B | **E** |
| Consultar órdenes | O | — | — | B por `manage_stock` | **E** |
| Entregar/cancelar orden operativa | O sólo cancelación válida | — | — | B por `manage_stock` | **E** |
| Registrar cobro manual | — | B | — | B | **E** |
| Conciliar pago/incidencia | — | — | — | B | **E** |
| Reporte financiero | — | — | — | B | **E** |
| Auditoría/reversión | — | — | — | B | **E**; permisos separados |
| Configuración/reportes generales | — | — | — | B nominal | **F**; implementación usa `is_staff` |

La tabla anterior describe defaults. Los tests confirman, entre otros casos,
que un ADMINISTRADOR sin `is_staff`, y un actor de otro rol con permiso
individual, sí funcionan en los recorridos canónicos; también confirman que
`is_staff` sin permiso no funciona allí.

## 3. Matriz detallada de cobertura por operación

Abreviaturas de evidencia: **+** positiva, **−** negativa, **I** inactivo,
**X** escalamiento/bypass.

| Módulo y operación | Endpoint o servicio | Autoridad efectiva y requisitos | Roles base | Evidencia actual | Estado |
|---|---|---|---|---|---|
| Sesión y capacidades | `GET /api/usuarios/me/` | Autenticado; proyecta permisos Django efectivos limitados al catálogo y rol único | Todos | + por 4 roles y grants; − roles múltiples; I perfil; X `is_staff`, superuser y permisos ajenos | **CUBIERTO** |
| Perfil propio | `/api/usuarios/perfil/` | Autenticación y usuario actual | Todos | + lectura/edición propia; − campos sensibles | **PARCIAL**: no hay matriz de cuenta inactiva por endpoint |
| Clientes | `/api/usuarios/clientes/` | `view_clients`; excepción controlada para perfil propio | E/P/A | + roles sin staff y grant individual; − CLIENTE, anónimo y staff sin permiso; X detalle ajeno/escritura | **CUBIERTO** |
| Alta de Cliente/administrador | endpoints `admin/*/crear/`; servicios de onboarding | permisos conjuntos de alta/usuarios/roles según destino; actor y target activos/coherentes | A | +/−, payload estricto, rollback y secretos; X permisos parciales | **CUBIERTO** |
| CRUD administrativo de Usuario | `AdminUsuarioViewSet` | `manage_users`; cambio de rol exige además `assign_roles` | A | +/−; I; X `is_staff`, campos de privilegio, PUT/PATCH/DELETE y bulk | **CUBIERTO** |
| Cambio de BusinessRole | `change_administrative_business_role` | ambos permisos; no autoacción; perfil/estado coherente; último admin; capacidades residuales administrativas | A | + cada transición; − permisos parciales; I actor/Personal; X último admin, residual individual/grupo; concurrencia | **CUBIERTO** |
| Baja/reactivación | servicios y actions de Usuario | `manage_users`, cuenta activa del actor, no autoacción/superuser; protección de último admin | A | +/−; I; X rutas CRUD/DELETE, tokens y concurrencia | **CUBIERTO** |
| Personal | `PersonalViewSet` y servicios semánticos | `manage_personal`; directorio mínimo separado; perfil y estado coherentes | A | + sin staff; − staff/CLIENTE; I; X vínculo, rol, estado, flags legacy y delete | **CUBIERTO** |
| Habilidades | actions de `PersonalViewSet`, `HabilidadViewSet` | `manage_skills`; Personal/Habilidad activos | A | + CRUD semántico y reactivación; − staff, CLIENTE, `manage_personal` aislado; I catálogo; rollback | **CUBIERTO** |
| Diagnóstico: crear/editar | `DiagnosticoCapilarViewSet` | `create_diagnosis` + Personal activo + habilidad `DIAGNOSTICO` activa; autor fijado por servidor | P/A | + P, A sin staff y grant individual a E; − permiso sin skill, skill sin permiso, Personal/skill/user inactivos; X autor/Cliente | **CUBIERTO** |
| Diagnóstico: leer | list/detail/`por_cliente`/`mis_diagnosticos` | owner Cliente o `manage_technical_record` + skill activa | P/A global; C propio | + global/propio; − tercero, permiso sin skill; I; X query `cliente_id` | **CUBIERTO** |
| Ficha técnica y fórmula | `FichaTecnicaViewSet` | En código: `IsAdminUser`; ownership por `is_staff`; no usa `manage_technical_record`/`manage_formulas` | Staff real, no BusinessRole | No se localizó suite de autorización | **SIN COBERTURA** |
| Agenda global canónica | `GET /turnos/` | `view_global_agenda` | E/P/A | + roles y grant sin staff; − C/anónimo/staff sin permiso; X serialización sensible | **CUBIERTO** |
| Turnos propios/asignados | `mis_turnos`, detail, `mi_agenda_laboral` | ownership Cliente o Personal activo asignado | C propio; Personal asignado | +/− terceros; I Personal; X separación de scopes y comprobante | **CUBIERTO** |
| Crear turno | `reservar`, `crear-para-cliente` | owner Cliente o `create_turno_for_client`; estado/slot/Personal/equipamiento válidos | C propio; E/P/A para tercero | +/− roles/grant/staff; X `cliente_id`, estado y finanzas; recursos/slots | **CUBIERTO** |
| Llegada/reprogramación/cancelación | actions semánticas de `TurnoViewSet` | permisos independientes; estados y agenda válidos | E/P/A | + cada permiso; − permisos cruzados, staff, C; X endpoints multiplexados; auditoría/rollback | **CUBIERTO** |
| Finalizar servicio | `finalizar_turno` | `finalize_service` + `create_diagnosis` + skill DIAGNOSTICO activa | P/A | + y − sin skill; actor real | **PARCIAL**: falta matriz completa de rol/inactivo/ownership |
| Agenda legacy: lectura | `obtener_agenda_general` | Sólo `IsAuthenticated`; permite elegir `personal_id` | Todos autenticados | Sin tests de autorización localizados | **SIN COBERTURA** |
| Agenda legacy: bloqueo | `crear_bloqueo` | Sólo `IsAuthenticated`; selecciona colorista global | Todos autenticados | Sin tests de autorización localizados | **SIN COBERTURA** |
| Horarios | `HorarioLaboralViewSet` | `IsAdminUser`, no `manage_configuration` ni permiso de agenda | Sólo `is_staff` | Tests funcionales indirectos, no matriz de autorización | **SIN COBERTURA** |
| Servicios y precios | `ServicioViewSet` final | lectura pública; escritura `manage_prices` | A para escritura | + grant de precio sin staff; − staff sin permiso | **PARCIAL**: faltan CRUD, inactivo y escalamiento por campos |
| Catálogos capilares/categorías | cinco ViewSets y `CategoriaServicioViewSet` | `AllowAny` para `ModelViewSet` completo | Cualquiera, incluso anónimo | No se localizaron negativos de escritura | **SIN COBERTURA** |
| Riesgo técnico | ViewSets de política/reglas | `manage_technical_risk_policy`; publicados inmutables | A | + grant individual; − staff sin permiso y endpoints completos; X publicación/inmutabilidad | **CUBIERTO** |
| Revisión técnica previa | solicitudes/cola/revisión | `review_technical_booking` + Personal/skill DIAGNOSTICO activos; owner en solicitud | P/A | +/− permiso, skill, owner y payload; datos técnicos no expuestos | **CUBIERTO** |
| Fórmulas | campo en ficha técnica | Permiso `manage_formulas` existe pero no se encontró enforcement dedicado | P/A nominal | Sólo catálogo/proyección y pruebas de no exposición | **SIN COBERTURA** |
| Rutinas | `RutinaViewSet`, `RutinaClienteViewSet`, `SeleccionarRutinaView` | Escritura por `IsAdminUser`; selección/ownership autenticado; `assign_routines` no se aplica | P/A nominal, C propio | No se localizaron tests de autorización de rutas | **SIN COBERTURA** |
| Equipamiento | `TipoEquipamientoViewSet`, `EquipamientoViewSet` | Tipo: cualquier autenticado; Equipamiento: defaults globales, efectivamente autenticado | Todos autenticados | Tests de disponibilidad, no de autorización CRUD | **SIN COBERTURA** |
| Requisitos de servicio | `RequisitoServicioViewSet` | `IsAdminUser` | Sólo `is_staff` | Tests funcionales indirectos, no matriz | **SIN COBERTURA** |
| Productos | `ProductoViewSet`, imágenes/categorías | permisos separados `manage_products`/`manage_prices`; creación exige ambos | A | + permisos independientes; − staff/C; X mezcla atómica de campos y stock | **CUBIERTO** |
| Stock | acciones y `StockMovementCommandViewSet` | `view_stock` o `manage_stock`; comandos validan también servicio | E/P/A lectura; A gestión | +/−, staff sin permiso, C sin cantidades, ledger inmutable y concurrencia | **CUBIERTO** |
| Promociones | `PromocionViewSet` | lectura pública; escritura `manage_promotions` | A | + permiso individual; − staff sin permiso y separación de stock | **PARCIAL**: faltan inactivo y todas las acciones |
| Órdenes: lectura/checkout | `OrdenCompraViewSet` y servicios | owner Cliente; lectura global por `manage_stock`; checkout owner | C propio; A global | + ownership, ocultamiento y estados; − tercero; idempotencia | **CUBIERTO** |
| Entrega/cancelación | actions de órdenes y servicios canónicos | `manage_stock` para entrega; cancelación por owner o permiso según estado; pagos resueltos | C/A según acción | +/− C, staff, permiso, estados pagados; X aliases legacy; concurrencia | **CUBIERTO** |
| Política de pagos | `PaymentIntent` options/policy | `manage_payment_configuration` para publicar; lectura pública segura de opción vigente | A | + permiso exacto; − configuración inválida/inmutable; concurrencia | **CUBIERTO** |
| Cobro manual | endpoints de PaymentIntent y orden legacy | `register_payment`; conciliación separada por `confirm_deposit`/`reconcile_external_payment`; ownership de historial | E/A registro; A conciliación | + actor con permiso sin staff; − staff y PROFESIONAL; X permisos cruzados, owner, CRUD | **CUBIERTO** |
| Pagos/reportes/comprobante | `PagoViewSet` | `view_financial_reports` para lista; owner o capacidades financieras para comprobante; conciliación en servicio | A; C owner parcial | +/− permiso exacto y privacidad; X URL de storage/CRUD | **CUBIERTO** |
| Incidencias financieras | `PaymentReconciliationCaseViewSet` | `reconcile_external_payment`; algunas solicitudes públicas sólo para owner y servicios validan actor | A; C sólo solicitud propia | +/− staff, permiso individual, owner, transición, cierre/refund; concurrencia | **CUBIERTO** |
| Auditoría | `AuditoriaViewSet`, `HistorialAuditoriaViewSet` | `view_audit`; reversión separada `revert_audit`; campos de acceso excluidos | A | + sin staff; − staff/permiso parcial; I por clase; X reversión de acceso | **CUBIERTO** |
| Configuración | ViewSets de configuración | `IsAdminUser`; `manage_configuration` existe pero no se usa | Sólo `is_staff` | No se localizaron tests de autorización | **SIN COBERTURA** |
| Dashboards/reportes generales | dos `DashboardStatsViewSet`/`AdminDashboardStatsView` | `IsAdminUser`; `view_reports` no se usa | Sólo `is_staff` | No se localizaron tests de autorización | **SIN COBERTURA** |
| Django Admin: acceso | `/admin/` | Django exige `is_staff`; luego permisos de modelo/superuser | No coincide directamente con BusinessRole | Sin test de login/navegación por rol efectivo | **SIN COBERTURA** |
| Django Admin: Usuario/Cliente/Personal | ModelAdmin | campos de acceso readonly; altas/bajas genéricas deshabilitadas | Staff con acceso al Admin | Tests unitarios de contención de campos, add/delete y acciones | **PARCIAL**: falta integración HTTP y cobertura de todos los modelos |
| Django Admin: Producto/stock | `ProductoAdmin`, ledger | permisos efectivos para módulo/campos; stock readonly y comandos fuera del Admin | Según grants + `is_staff` de acceso | Código alineado; no se localizó suite dedicada de integración | **PARCIAL** |

## 4. Cobertura actual por módulo

| Módulo | Evaluación | Síntesis |
|---|---|---|
| Usuarios, Cliente y Personal | **Alta** | Es el dominio más completo: permisos efectivos, `is_staff`, grants individuales, estado, último admin, residuos y rutas alternativas. |
| Diagnóstico | **Alta** | Permiso + habilidad + Personal activo + ownership están probados. Conserva una expectativa legacy incorrecta ajena a la seguridad. |
| Ficha técnica/fórmulas | **Baja** | Sin suite dedicada y con autoridad legacy basada en staff. |
| Turnos canónicos | **Alta** | Lectura, creación, llegada, gestión, ownership, skills y payloads están cubiertos. |
| Agenda/horarios legacy | **Baja** | Lectura y bloqueo sólo autenticados; horarios por `IsAdminUser`; no hay negativos dedicados. |
| Habilidades/riesgo técnico | **Alta** | Permisos efectivos y bypass de staff probados. |
| Servicios/rutinas/equipamiento | **Baja** | Precio de servicio tiene evidencia parcial; rutinas, catálogos y equipamiento presentan vacíos relevantes. |
| Productos/precios/stock | **Alta** | Matriz granular, atomicidad, privacidad y comandos semánticos. |
| Órdenes/entregas | **Alta** | Ownership, permiso de stock, estados financieros, aliases legacy e idempotencia. |
| Caja/pagos | **Alta** | Registro, conciliación, configuración, reportes y privacidad con permisos separados. |
| Incidencias financieras | **Alta** | Lectura, solicitudes, decisión, refund, ajustes, cierre y carreras. |
| Auditoría | **Alta** | Lectura y reversión separadas; contención de campos de acceso. |
| Configuración/reportes/Admin | **Baja-media** | Contención puntual de acceso en Admin, pero siguen superficies `IsAdminUser` y falta integración completa. |

## 5. Revisión de casos críticos solicitados

| Caso | Resultado |
|---|---|
| `is_staff` sin permiso | **Cubierto** en Usuarios, Personal, Clientes, turnos, skills, inventario, órdenes, pagos, riesgo, finanzas y auditoría. **No aplica correctamente** en ficha, rutinas, horarios, configuración y dashboards, que usan `IsAdminUser`. |
| Permiso efectivo sin `is_staff` | **Cubierto** en los flujos canónicos anteriores. Django Admin sigue exigiendo staff como puerta de entrada. |
| CLIENTE accede a terceros | **Cubierto** en Cliente, diagnóstico, turnos, órdenes, intents, pagos y casos financieros. Faltan rutinas/equipamiento/agenda legacy. |
| EMPLEADO administra usuarios o precios | Usuarios: **cubierto negativo**. Precios: staff sin permiso y permiso exacto cubiertos; falta un caso nombrado explícitamente como EMPLEADO con su base completa. |
| PROFESIONAL registra cobro sin permiso | **Cubierto negativo** en pagos manuales; su rol base excluye `register_payment`. |
| Diagnóstico sin habilidad | **Cubierto** para ausencia, asignación inactiva, catálogo inactivo, Personal inactivo y usuario inactivo. |
| Cuenta desactivada | Login, servicios de acceso, diagnósticos y permisos administrativos tienen evidencia. No existe matriz de usuario inactivo para cada endpoint legacy. |
| Cambio de rol y pérdida de capacidades | **Cubierto**, incluida invalidación de caché y dos carreras PostgreSQL. |
| Último administrador activo | **Cubierto** en cambio de rol y baja; incluye concurrencia y exclusión de backups inactivos/técnicos/superuser. |
| Permisos residuales | **Cubierto** para capacidades administrativas residuales individuales y por grupo: la degradación se bloquea. Permisos técnicos no escalantes se conservan deliberadamente. |
| Caja/pagos/resoluciones | **Cubierto** y con separación de permisos, ownership e idempotencia. |
| Django Admin | **Parcial**: acceso sensible readonly/deshabilitado y Producto alineado por código; falta prueba HTTP integral y varios ModelAdmin conservan permisos Django genéricos. |
| Endpoints legacy | **Mixto**: aliases de turnos/órdenes/pagos están cerrados o delegan a servicios; agenda, catálogos, equipamiento, rutinas y dashboards conservan brechas. |

## 6. Riesgos sin cobertura y defectos reales

### 6.1 Defectos reales de autorización observados

1. **CRUD anónimo de catálogos.** `TipoCabelloViewSet`,
   `GrosorCabelloViewSet`, `PorosidadCabelloViewSet`,
   `CueroCabelludoViewSet`, `EstadoGeneralViewSet` y
   `CategoriaServicioViewSet` son `ModelViewSet` con `AllowAny`. No sólo exponen
   lectura: también aceptan rutas de alta, edición y borrado sin permiso de
   negocio.
2. **Equipamiento modificable por cualquier autenticado.**
   `TipoEquipamientoViewSet` declara sólo `IsAuthenticated` y
   `EquipamientoViewSet` hereda los defaults globales, equivalentes aquí a
   requerir autenticación. Un CLIENTE autenticado alcanza CRUD.
3. **Bloqueos de agenda con autenticación insuficiente.** `crear_bloqueo`
   exige únicamente `IsAuthenticated` y crea el bloqueo para el primer
   colorista activo.
4. **Agenda general legacy expuesta a cualquier autenticado.**
   `obtener_agenda_general` permite seleccionar `personal_id` y devuelve
   horarios, bloqueos y configuración sin `view_global_agenda` ni ownership.
5. **Permisos nominales sin enforcement.** `manage_formulas`,
   `assign_routines`, `view_reports` y `manage_configuration` existen y son
   proyectados por rol, pero las superficies encontradas usan `IsAdminUser` o
   no aplican esos permisos.
6. **Ficha técnica desacoplada de la arquitectura efectiva.** Un staff sin
   `manage_technical_record` puede entrar, mientras un PROFESIONAL con permisos
   base pero `is_staff=False` queda fuera. El scope también se decide por
   `is_superuser`/`is_staff`.

Estos hallazgos no nacen de una expectativa de test desactualizada: son
divergencias entre el catálogo de autoridad y las permission classes efectivas.

### 6.2 Riesgos altos sin prueba concluyente

- Rutinas y copias de Cliente: `assign_routines` no gobierna las mutaciones y
  no hay suite de ownership/escalamiento dedicada.
- Django Admin: sólo se probaron métodos de contención puntuales; falta demostrar
  por HTTP que grupos/permisos/flags/estados no tienen otra ruta editable.
- `HorarioLaboral`, requisitos de servicio, configuración y dashboards mezclan
  administración técnica (`is_staff`) con autoridad de negocio.
- La configuración global de DRF contiene simultáneamente `AllowAny` e
  `IsAuthenticated`. En clases sin override el resultado práctico es
  autenticado, pero es una política confusa y fácil de interpretar o modificar
  incorrectamente.
- Las acciones de contenido educativo tienen controles ad hoc de perfil/autor;
  no existe una matriz equivalente a la de inventario y pagos.

## 7. Casos negativos prioritarios

Orden recomendado para agregar tests, sin implementarlos en esta tarea:

1. Anónimo y CLIENTE intentan POST/PATCH/DELETE en cada catálogo capilar y en
   categorías de servicio; el estado de base debe permanecer idéntico.
2. CLIENTE y EMPLEADO intentan crear, editar y desactivar tipos/equipamiento;
   `is_staff` sin permiso también debe fallar y grant efectivo sin staff debe
   seguir la política que se defina.
3. CLIENTE intenta `crear_bloqueo` y consultar la agenda de otro Personal;
   usuario inactivo y actor sin `view_global_agenda` deben fallar.
4. PROFESIONAL con `manage_technical_record`/`manage_formulas` y skill activa,
   pero sin staff, opera ficha propia; staff sin esos permisos falla; acceso a
   ficha de otro profesional o Cliente no relacionado falla.
5. EMPLEADO/PROFESIONAL/ADMINISTRADOR sin staff y staff sin permiso prueban
   rutinas, fórmulas, configuración, horarios, requisitos y dashboards.
6. PROFESIONAL intenta registrar cobro en todos los aliases legacy, no sólo en
   la API canónica; no debe aparecer `Pago` ni auditoría de éxito.
7. Usuario desactivado con token previamente emitido intenta cada familia de
   endpoint owner y cada permiso individual; debe recibir una respuesta estable
   y no mutar datos.
8. Django Admin mediante `Client`: login de business admin sin staff, staff sin
   permiso, staff con permiso exacto y superuser; verificar cada formulario y
   POST sensible, no sólo `readonly_fields`.
9. Tras degradación de ADMINISTRADOR, repetir requests con la misma instancia de
   usuario y con una nueva para detectar caché residual en APIs, Admin y
   servicios.
10. Rutas legacy y canónicas de una misma operación deben compartir resultado,
    invariantes, ownership y permiso efectivo.

## 8. Ejecución representativa sobre PostgreSQL

Todas las corridas se ejecutaron secuencialmente con el intérprete del entorno
virtual, `python -X utf8 manage.py test ... --noinput`, sin `--keepdb`. Cada
bloque creó y destruyó una base PostgreSQL nueva.

| Bloque | Casos | Resultado | Tiempo |
|---|---:|---:|---:|
| Roles, sesión, acceso, Usuario, Personal, baja/reactivación | 161 | **161 OK** | 357.795 s |
| Diagnóstico, turnos, skills, riesgo y solicitud técnica | 175 | **174 OK + 1 expectativa legacy** | 343.910 s |
| Productos, stock, órdenes y entregas | 65 | **65 OK** | 92.840 s |
| Pagos manuales, intents e incidencias/resolución | 80 | **80 OK** | 537.323 s |
| Auditoría, capacidades y altas administrativas | 35 | **35 OK** | 81.312 s |
| Concurrencia de rol, resolución financiera y pago manual | 9 | **9 OK** | 91.363 s |
| **Total** | **525** | **524 conformes + 1 legacy** | **1504.543 s** |

### 8.1 Clasificación de resultados

| Categoría | Resultado |
|---|---|
| Tests correctos | **524** casos conformes en los bloques ejecutados. |
| Expectativa legacy desactualizada | **1**: `DiagnosisAuthorizationApiTests.test_legacy_flags_are_read_only_in_personal_serializer`. Espera aceptar silenciosamente flags legacy; el serializer estricto los rechaza con 400. El comportamiento seguro es el actual. |
| Faltantes de cobertura | Ficha/fórmulas, agenda legacy, horarios, rutinas, equipamiento, catálogos, configuración, dashboards y Django Admin integral. |
| Defectos reales | Los seis enumerados en 6.1, especialmente CRUD `AllowAny` y mutaciones sólo autenticadas. |
| Fixtures/migraciones | Sin fallos en bases nuevas. Las migraciones sembraron roles, permisos y habilidades correctamente. |
| Fechas/reloj | No hubo fallo en esta ejecución. Persisten usos de `date.today()` y fechas relativas que merecen reloj controlado. |
| `--keepdb` | No se usó como evidencia. Está documentado un problema previo: una base preservada sin datos de `Habilidad` generó errores de setup porque la migración de datos no se reaplicó. |
| Concurrencia | 9/9 en el bloque aislado. No se ejecutaron bloques en paralelo. |
| Logging/duración | Problema confirmado: signals y middleware imprimen miles de líneas; 525 casos consumieron 25 min 4.543 s. El bloque financiero de 80 casos tardó 537.323 s. |

## 9. Propuesta de incrementos pequeños

No se implementa ninguno en BH-060 análisis.

### Incremento 1 — Catálogos y equipamiento

- definir lectura pública explícita y escritura con un permiso efectivo;
- agregar matriz anónimo/CLIENTE/EMPLEADO/staff sin permiso/grant sin staff/A;
- cubrir todas las acciones CRUD y no mutación ante 401/403.

### Incremento 2 — Agenda legacy

- hacer que lectura global y bloqueos usen permisos de agenda/configuración;
- definir ownership para agenda laboral;
- cerrar selección arbitraria de `personal_id`;
- probar usuario/Personal inactivo.

### Incremento 3 — Ficha, fórmulas y rutinas

- reemplazar `IsAdminUser` por permisos efectivos ya catalogados;
- conservar skill, Personal activo, autoría y ownership como condiciones
  independientes;
- agregar positivos por grant sin staff y negativos por staff sin permiso.

### Incremento 4 — Configuración y reportes

- aplicar `manage_configuration` y `view_reports` a sus superficies;
- mantener `view_financial_reports` separado;
- probar que un permiso no implica el otro.

### Incremento 5 — Django Admin integral

- usar tests HTTP de login/changelist/change POST;
- enumerar ModelAdmin sensibles;
- probar BusinessRole, staff y permisos de modelo/effectivos por separado;
- impedir bypass de servicios semánticos de acceso y stock.

### Incremento 6 — Estado, residuos y aliases

- parametrizar usuario inactivo, permiso individual, grupo técnico, cache de
  permisos y cambio de rol para cada familia crítica;
- exigir equivalencia entre ruta canónica y legacy.

### Incremento 7 — Estabilización del harness

- silenciar/capturar prints de signals y middleware en tests;
- documentar partición oficial y presupuesto de tiempo;
- crear estrategia reproducible de base limpia y `--keepdb` validado;
- fijar reloj/zona horaria en suites sensibles;
- mantener concurrencia PostgreSQL en bloque aislado y nunca paralelo con otras
  suites que compartan nombre de base.

## 10. Criterios verificables de cierre futuro

La implementación posterior de cobertura podrá cerrarse cuando:

1. cada operación de la matriz tenga al menos un positivo por permiso efectivo,
   un negativo sin permiso y un caso `is_staff` contrario al permiso;
2. toda operación con ownership pruebe owner y tercero, usando list, detail y
   acciones personalizadas;
3. toda operación técnica pruebe habilidad ausente, inactiva, Personal inactivo
   y cuenta inactiva;
4. cambio de rol pruebe pérdida inmediata, caché, permiso residual individual y
   grupo técnico;
5. último administrador conserve pruebas secuenciales y concurrentes;
6. caja, pagos, refunds, ajustes y cierres mantengan permisos separados y cero
   mutación ante rechazo;
7. ninguna escritura de catálogo, agenda, equipamiento, configuración, rutina,
   ficha o fórmula dependa sólo de `AllowAny`, `IsAuthenticated` o `is_staff`;
8. Django Admin tenga pruebas HTTP de contención para todos los campos y modelos
   que alteran acceso, inventario o finanzas;
9. aliases legacy estén cerrados o deleguen en el mismo servicio canónico;
10. la suite oficial pase en PostgreSQL desde base limpia y con el modo
    `--keepdb` documentado, sin contaminación de fixtures;
11. concurrencia se ejecute aislada con resultados deterministas;
12. el test legacy de flags exija rechazo estricto sin debilitar el serializer;
13. la salida no incluya logging masivo y cada bloque tenga timeout/presupuesto;
14. la matriz quede automatizada en CI y no dependa de ejecución manual.

## 11. Separación de BH-061 y BH-062

### BH-061 — Historial y forense

Quedan fuera de BH-060:

- historial visual unificado por actor/objetivo;
- consultas temporales, exportación, retención y correlación avanzada;
- análisis forense de cambios de acceso.

BH-060 sólo exige comprobar quién puede leer/revertir auditoría y que no exista
escalamiento; no diseña el producto forense.

### BH-062 — UX administrativa avanzada

Quedan fuera de BH-060:

- matrices visuales y comparación interactiva de roles/capacidades;
- acciones masivas, aprobaciones y mejoras amplias de accesibilidad;
- editor o diseñador libre de permisos/grupos;
- UX de diagnóstico y revocación de excepciones.

BH-060 define evidencia automatizada y riesgos. No habilita edición genérica de
permisos Django ni inicia cambios de interfaz.

## 12. Conclusión

La autorización automatizada es fuerte en los recorridos canónicos construidos
o endurecidos por BH-058/BH-059: acceso administrativo, Personal, diagnóstico,
turnos, skills, riesgo técnico, inventario, órdenes, pagos, incidencias y
auditoría. Allí los tests distinguen correctamente BusinessRole, permiso
efectivo, `is_staff`, ownership, habilidad, estado y, en puntos críticos,
concurrencia.

La deuda se concentra en superficies legacy. Catálogos públicos con CRUD,
equipamiento y bloqueos sólo autenticados, y ficha/rutinas/configuración basadas
en staff no sólo carecen de cobertura: varias contradicen el modelo de permisos
efectivos. Deben abordarse en incrementos pequeños, empezando por los endpoints
con mutación no autorizada.

BH-060 — ANÁLISIS COMPLETADO
