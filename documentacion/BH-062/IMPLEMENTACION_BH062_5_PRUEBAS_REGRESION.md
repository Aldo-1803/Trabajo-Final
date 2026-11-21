# BH-062 — Incremento 5: pruebas y regresión integral

**Fecha:** 2026-11-11

**Baseline publicado:** `a4d2c3a8b58f23f170c1249cbed94e0b7e51562c`

**Rama:** `save/work-in-progress`

## 1. Resultado y alcance

Este incremento completa la evidencia automatizada y la regresión integral de
BH-062. No agrega permisos, roles, endpoints ni lógica productiva. El backend
continúa siendo la autoridad sobre permisos, habilidades, ownership, estado y
validaciones de cada objeto.

Se agregaron exclusivamente:

- una prueba backend de paridad de `service_formula.manage` cuando
  `gestion.manage_formulas` proviene de BusinessRole, grupo técnico o permiso
  individual;
- cuatro recorridos frontend con Router, `SessionContext`, `/me/`, `Header`,
  `ProtectedRoute` y cliente HTTP: tres orígenes de autoridad y una revocación
  por foco después del umbral de 45 segundos;
- esta matriz y su evaluación preliminar.

No se detectó un defecto productivo ni una vulnerabilidad crítica. Esta
validación corresponde al Incremento 5 y **no constituye el cierre técnico de
BH-062**; el veredicto final queda reservado para una auditoría independiente.

## 2. Inventario y matriz de cobertura

La clasificación se aplica al contrato completo disponible después de los
Incrementos 0 a 4. Una fila `Parcialmente cubierto` identifica una integración
que no existe en la aplicación productiva; no se transforma evidencia backend
en evidencia React.

| Pantalla o superficie | Operación | Permiso/capability efectiva | Endpoint | Evidencia automatizada | Estado |
|---|---|---|---|---|---|
| Sesión | Proyectar identidad, perfiles, permisos y siete capabilities | Autoridad Django efectiva y condiciones persistidas | `GET /api/usuarios/me/` | `usuarios/test_current_session_api.py`, `usuarios/test_current_session_capabilities_api.py`, `SessionContext.test.js` | Cubierto |
| Sesión | Fallar cerrado ante capability ausente, falsa, inválida o desconocida | Booleano estricto `true` | `GET /api/usuarios/me/` | `SessionContext.test.js`, `ProtectedRoute.test.js` | Cubierto |
| Usuarios | URL directa, menú, landing, carga y acción | `usuarios.manage_users` | `/api/gestion/admin/usuarios/` y acciones semánticas | `ProtectedRoute.test.js`, `navigationConfig.test.js`, `Header.test.js`, `sessionLanding.test.js`, `GestionUsuarios.test.js`, `PermissionUiIntegration.test.js` | Cubierto |
| Usuarios | Crear administrador | `usuarios.manage_users` + `usuarios.assign_roles` | `POST /api/usuarios/admin/administradores/crear/` | `usuarios/test_administrator_account_creation_api.py`, `GestionUsuarios.test.js` | Cubierto |
| Usuarios | Cambiar BusinessRole | `usuarios.manage_users` + `usuarios.assign_roles` | `POST /api/gestion/admin/usuarios/{id}/cambiar-rol-negocio/` | `usuarios/test_bh059_c_role_change_services.py`, tests de API de cambio de rol, `GestionUsuarios.test.js` | Cubierto |
| Personal | CRUD y estado laboral | `gestion.manage_personal` | `/api/gestion/personal/` y acciones de estado | `test_personal_access_api.py`, `test_personal_status_api.py`, `GestionPersonal.test.js` | Cubierto |
| Personal | Crear/vincular acceso o cambiar rol laboral | `gestion.manage_personal` + `usuarios.assign_roles` | acciones `/crear-acceso/`, `/vincular-usuario/` y `/cambiar-rol-acceso/` | `test_personal_access_creation_api.py`, suites de acceso Personal, `GestionPersonal.test.js` | Cubierto |
| Personal | Gestionar habilidades sin exponer datos laborales reservados | `gestion.manage_skills` | directorio, catálogo y acciones `/habilidades/` | `test_skills_api.py`, `GestionPersonal.test.js` | Cubierto |
| Contenido educativo | Listar y consultar contenido visible | Cliente: publicado; autor: publicado + propio; gestor: activo global | `GET /api/gestion/contenido-educativo/` y `/{id}/` | `test_content_authorization_bh062_0.py`, `GestionContenidoEducativo.test.js`, `EditorContenidoEducativo.test.js` | Cubierto |
| Contenido educativo | Crear | `content.author` | `POST /api/gestion/contenido-educativo/` | `test_content_authorization_bh062_0.py`, `EditorContenidoEducativo.test.js` | Cubierto |
| Contenido educativo | Editar, publicar, archivar o reabrir | Autor concreto o `content.manage_global` | `PUT/PATCH /api/gestion/contenido-educativo/{id}/` | mismos tests de contenido; incluyen payload sin cambio de autor y lectura de contenido ajeno | Cubierto |
| Contenido educativo | Eliminación lógica | Autor concreto o `content.manage_global` | `DELETE /api/gestion/contenido-educativo/{id}/` | mismos tests backend y `GestionContenidoEducativo.test.js`; verifican ausencia de mutación rechazada | Cubierto |
| Contenido educativo | Like, guardado y consulta de interacciones | Perfil Cliente y contenido activo/publicado | acciones `/like/`, `/guardar/`, `/mis-guardados/`; viewsets de interacciones sólo lectura | `test_content_authorization_bh062_0.py` | Cubierto |
| Revisión técnica | Entrar, consultar cola y decidir | `technical_booking.review` | `GET .../solicitudes-tecnicas/cola/`; `POST .../{id}/revisar/` | `test_technical_booking_requests.py`, `test_current_session_capabilities_api.py`, `ProtectedRoute.test.js`, `RevisionTecnica.test.js` | Cubierto |
| Servicios | Leer catálogo | Lectura permitida por contrato del endpoint | `GET /api/gestion/servicios/` | suites BH-060.3 y `GestionarServicios.test.js` | Cubierto |
| Servicios | Crear, editar metadata/precio y desactivar | `gestion.manage_prices` | `POST/PATCH/DELETE /api/gestion/servicios/` | `test_technical_record_formula_routine_permissions_bh060_3.py`, `GestionarServicios.test.js` | Cubierto |
| Servicios | Editar fórmula sin ampliar acceso a precios | `service_formula.manage` | `PATCH /api/gestion/servicios/{id}/` | suite BH-060.3, nueva paridad de origen y `GestionarServicios.test.js` | Cubierto |
| Diagnóstico profesional | Crear y consultar según autoridad/ownership | `diagnosis.create`; lectura propia o `technical_record.read_global` | CRUD `/api/gestion/diagnosticos-capilares/` | `test_diagnosis_authorization_api.py` y paridad `/me/`/DRF; no existe flujo React productivo | Parcialmente cubierto |
| Ficha técnica | Leer y gestionar | lectura propia o `technical_record.read_global`; escritura `technical_record.manage` | CRUD `/api/gestion/fichas-tecnicas/` | suite BH-060.3 y paridad `/me/`/DRF; componentes legacy no están enrutados | Parcialmente cubierto |
| Finalización técnica | Finalizar Turno/Servicio | `gestion.finalize_service` + diagnóstico efectivo y reglas de objeto | `POST .../turnos/{id}/finalizar_turno/` | `test_diagnosis_authorization_api.py` y suite BH-060.3; no existe flujo React productivo validado | Parcialmente cubierto |
| Navegación general | Menú, URL, landing y retorno seguro | Permisos, capabilities y perfiles del mismo snapshot | `/me/`; endpoint de la pantalla elegida | `navigationConfig.test.js`, `Header.test.js`, `ProtectedRoute.test.js`, `sessionLanding.test.js`, integración nueva | Cubierto |
| Notificaciones | Resolver destino autorizado o fallback sin ID sensible | Permiso exacto del destino o perfil propio | Sin request protegido hasta navegar | `notificationNavigation.test.js` e integración nueva | Cubierto |
| Agenda propia | Acceder con única superficie Personal | Personal activo | endpoints de agenda laboral propia | `ProtectedRoute.test.js`, `sessionLanding.test.js`, `MiAgendaLaboral.test.js` | Cubierto |
| Sin superficies | Llegar a `/cuenta-sin-acceso` sin bucle | Ninguna superficie efectiva | No aplica | `sessionLanding.test.js`, `CuentaSinAcceso.test.js`, `AccesoDenegado.test.js` | Cubierto |
| Sesión activa | Refrescar por foco/visibilidad y retirar autoridad | Snapshot nuevo de `/me/` | `GET /api/usuarios/me/` | `SessionContext.test.js`, `ProtectedRoute.test.js` e integración nueva | Cubierto |
| Errores | Diferenciar 400/422, 401, 403, 409, red/timeout y 5xx | Estado HTTP y sesión autenticada | Endpoints de cada pantalla y `/me/` | `httpErrors.test.js`, `SessionContext.test.js`, `AccesoDenegado.test.js` y tests de pantallas | Cubierto |
| Editor genérico de grants y permisos | Conceder grants arbitrarios | No permitido por alcance | No existe | Se usaron fixtures controladas; no se creó API | Fuera del alcance |
| Consistencia push | Revocación en tiempo real | No existe WebSocket/polling | No aplica | Se prueba la política acordada de foco/visibilidad/403, no tiempo real estricto | Fuera del alcance |

### 2.1 Ausencias de duplicación

No se repitieron los contratos HTTP exhaustivos de contenido, las combinaciones
de skills/capabilities, los guards unitarios ni los payloads parciales ya
cubiertos. La nueva prueba backend toma una sola capability representativa para
cerrar la paridad explícita de los tres orígenes. La integración frontend usa un
único recorrido representativo de `manage_users`; las matrices unitarias siguen
siendo responsables del resto de rutas y acciones.

## 3. Casos de integración agregados

`frontend/src/integration/PermissionUiIntegration.test.js` ejecuta cuatro casos:

1. autoridad proveniente de BusinessRole;
2. la misma autoridad proveniente de un grupo técnico, sin BusinessRole;
3. la misma autoridad proveniente de permiso individual, sin BusinessRole;
4. revocación observada al recuperar foco después de
   `SESSION_REFRESH_INTERVAL_MS`.

En los tres primeros, un mismo snapshot de `/me/` habilita simultáneamente:

- acceso directo a `/admin/usuarios` mediante Router y `ProtectedRoute` reales;
- enlace `Usuarios` en `Header`;
- landing `/admin/usuarios`;
- destino permitido de una notificación administrativa;
- montaje de la pantalla y su `GET` protegido;
- ejecución de una acción `POST` sólo después de pulsar el control autorizado.

El cuarto caso comprueba que el snapshot inicial puede permanecer visible hasta
el umbral acordado, que el foco provoca un único refresh, que la ruta cambia a
acceso denegado y que desaparecen menú y acción. El hijo se desmonta, el `GET`
protegido no se repite y no se ejecuta ningún `POST`.

Jest 27/CRA no resuelve los exports condicionales de React Router 7. El test
carga los builds CommonJS reales mediante aliases virtuales; no sustituye ni
simula la conducta del Router.

## 4. Autoridad efectiva y capabilities compuestas

La prueba nueva
`test_service_formula_capability_has_origin_parity` crea datos persistidos para
tres usuarios con Personal y habilidad `DIAGNOSTICO` activos. El permiso
`gestion.manage_formulas` procede respectivamente del grupo canónico del
BusinessRole `PROFESIONAL`, de un grupo técnico y de `user_permissions`.

Para los tres orígenes verifica:

- permiso efectivo presente en `/me/`;
- `service_formula.manage=true`;
- BusinessRole no inventado para los grants técnico e individual;
- paridad con `CanManagePricesOrFormulas`.

La matriz preexistente conserva las combinaciones negativas y de estado para
las siete capabilities: permiso sin habilidad, habilidad sin permiso, Personal
inactivo, habilidad o asignación inactiva, `is_staff` sin autoridad, contenido
propio frente a gestión global y contrato booleano sin filtraciones. Una
capability global no se documenta como autorización universal sobre objetos.

## 5. Revocación durante una sesión

| Cambio externo | Autoridad backend | Evidencia de actualización React | Resultado |
|---|---|---|---|
| A. Revocar permiso | Django deja de autorizar la siguiente petición | `SessionContext.test.js` y la integración nueva retiran permiso, ruta, menú y acción tras refresh | Cubierto |
| B. Cambiar BusinessRole | Servicios y APIs de cambio revalidan ambos permisos y el estado vigente | El reemplazo atómico del snapshot retira permisos heredados; las respuestas antiguas se ignoran | Cubierto |
| C. Desactivar Personal | Predicados efectivos dejan de reconocer autoría/skills inmediatamente | El refresh retira actividad, capabilities y superficies de Personal | Cubierto |
| D. Revocar `DIAGNOSTICO` | Clases DRF y predicados rechazan revisión, diagnóstico, fichas y fórmula | El refresh retira capabilities; guards y acciones integradas reaccionan declarativamente | Cubierto; los flujos React legacy no publicados siguen fuera |
| E. Desactivar cuenta | JWT/API rechaza la cuenta no vigente | Un `401` legítimo limpia tokens, proyección y ruta; no se confunde con un login fallido | Cubierto |

También quedan verificados:

- refresh deduplicado ante varios `403`;
- un `403` por ownership no cierra sesión si `/me/` no cambió;
- una mutación rechazada no se reenvía;
- logout, cambio de token o cambio de identidad invalidan respuestas anteriores;
- no se usan sleeps reales: `Date.now`, eventos y promesas son controlados;
- no se promete consistencia estrictamente en tiempo real.

## 6. Ejecución backend sobre PostgreSQL

Se usó `bohemiacore.test_settings` y
`StablePostgresTestRunner`, con una base PostgreSQL de pruebas cuyo nombre está
obligado a comenzar con `test_`. Las corridas fueron secuenciales, sin
`--parallel`, y conservaron la base mediante `--keepdb`.

### 6.1 Matriz focal explícita

La matriz de contenido, `/me/`, capabilities, permisos técnicos, roles,
Personal, diagnósticos, fichas, revisión y permisos BH-060 relevantes ejecutó:

- **265/265 tests aprobados**;
- **0 fallos**;
- 354,193 segundos.

### 6.2 Matriz completa explícita

La matriz completa se construyó enumerando todos los `test*.py` ubicados
directamente en `usuarios` y `gestion/tests`:

```powershell
$labels = @(
  Get-ChildItem "usuarios" -File -Filter "test*.py" |
    ForEach-Object { "usuarios.$($_.BaseName)" }
  Get-ChildItem "gestion\tests" -File -Filter "test*.py" |
    ForEach-Object { "gestion.tests.$($_.BaseName)" }
) | Sort-Object
python manage.py test @labels `
  --settings=bohemiacore.test_settings --keepdb --noinput -v 1
```

Resultado reproducible:

- **99 módulos explícitos**;
- **1.143/1.143 pruebas únicas aprobadas**;
- **0 fallos**.

Los 265 casos focales son un subconjunto y no se suman al total de 1.143. Los
trazados de fallos forzados de storage, proveedor o auditoría pertenecen a casos
negativos que aprobaron. La advertencia de paginación sin orden también era
preexistente. El descubrimiento Django parcial no se presenta como matriz.

Validaciones adicionales:

- `manage.py check`: aprobado;
- `makemigrations --check --dry-run`: sin cambios;
- `migrate --check`: sin migraciones pendientes.

## 7. Ejecución frontend

| Ejecución | Resultado |
|---|---|
| Integración nueva | **1 suite, 4/4 tests aprobados** |
| Suite completa | **42 suites, 397/397 pruebas únicas aprobadas** |
| Build React de producción | **Aprobado** |

Los cuatro casos nuevos ya están incluidos en los 397 y no se suman nuevamente.
La suite verifica ausencia de requests después de denegación, handlers
mutadores sin autoridad, navegación prohibida, datos no autorizados en DOM y
respuestas de sesión obsoletas.

Persisten advertencias históricas de `act(...)`, Browserslist, una dependencia
dinámica, lint y mensajes de errores intencionalmente provocados. No fueron
ocultadas y no corresponden a una regresión de este incremento.

## 8. Resultados y fallos encontrados

No hubo fallos finales ni defectos productivos.

Durante la creación de la integración se corrigieron dos problemas del harness:

1. Jest 27 inicialmente no encontró `react-router-dom` por sus exports
   condicionales de versión 7; se cargaron sus distribuciones CommonJS reales y
   se agregó el polyfill de `TextEncoder` requerido por el entorno de prueba.
2. La expectativa inicial suponía landing `/operaciones`; el algoritmo vigente
   selecciona correctamente `/admin/usuarios` cuando ésa es la primera
   superficie autorizada del snapshot. Se corrigió la expectativa, no el código
   productivo.

## 9. Evaluación preliminar de los 12 criterios

Esta clasificación es evidencia para auditoría y no un veredicto de cierre.

| # | Criterio resumido | Tests existentes | Tests nuevos | Evidencia y resultado preliminar |
|---|---|---|---|---|
| 1 | Contenido niega lectura administrativa y mutaciones HTTP no autorizadas | `test_content_authorization_bh062_0.py` y tests React de contenido | Ninguno; contrato ya exhaustivo | Datos, DOM, ownership, DELETE, autor inmutable e interacciones verificados. **CUMPLE** |
| 2 | `/me/` mínimo representa capabilities sin estructura administrativa | tests de sesión/capabilities y `SessionContext.test.js` | Paridad de fórmula por tres orígenes | Siete booleanos, `no-store`, catálogo limitado y ausencia de flags/grupos/grants. **CUMPLE** |
| 3 | Menú, landing, notificaciones y URL son consistentes | suites de navegación, Header, landing y guards | Tres recorridos integrados de autoridad | Mismo snapshot gobierna todas las superficies. **CUMPLE** |
| 4 | Flags o nombres nominales no sustituyen capabilities | sesión, capabilities, guards y creación de cuentas | Casos sin BusinessRole en integración | `is_staff`, `is_superuser`, `Personal.rol` y rol nominal no amplían la SPA. **CUMPLE** |
| 5 | Pantallas parciales separan lectura y operaciones mutadoras | Usuarios, Personal, Servicios y Contenido | Integración de lectura/acción autorizada | Las pantallas publicadas cumplen; diagnóstico, fichas y finalización carecen de integración React productiva. **CUMPLE PARCIAL** |
| 6 | Acciones de rol requieren ambos permisos backend | creación de administrador, cambio de rol y acceso Personal en backend/frontend | Ninguno; contrato ya cubierto | Botón, handler, payload y API exigen la conjunción. **CUMPLE** |
| 7 | Condiciones técnicas se detectan antes de ofrecer acciones | capabilities, revisión técnica y Servicios | Paridad `service_formula.manage` | Revisión y fórmula cumplen; diagnóstico, fichas y finalización no tienen flujo React integrado que auditar. **CUMPLE PARCIAL** |
| 8 | URL denegada no monta ni consulta | `ProtectedRoute.test.js` | Revocación integrada confirma desmontaje y no repetición de `GET` | El hijo y sus efectos quedan fuera. **CUMPLE** |
| 9 | Cambios de rol, permiso, cuenta, Personal o habilidad se reflejan en sesión | backend semántico, capabilities y `SessionContext.test.js` | Recorrido real de Router tras foco >45 s | Backend cambia inmediatamente; React converge por foco/visibilidad o `403`, sin tiempo real prometido. **CUMPLE** |
| 10 | Errores HTTP y red tienen tratamientos distintos | `httpErrors`, contexto, acceso denegado y pantallas | La integración conserva denegación sin mutación | 401 limpia; 403 refresca sin logout; 409/validación/red/5xx conservan su semántica. **CUMPLE** |
| 11 | Tests cubren orígenes, lectura, capabilities, revocación y no filtración | matrices backend/frontend de Incrementos 0–4 | Cinco pruebas nuevas | Las categorías requeridas están cubiertas, pero no hay integración React de diagnóstico/fichas/finalización. **CUMPLE PARCIAL** |
| 12 | Backend sigue siendo autoridad y no se amplía alcance | regresión HTTP y permisos DRF | Sólo tests; cero lógica productiva | No se añadieron roles, grants, finanzas, WebSockets ni rediseño. **CUMPLE** |

Resumen preliminar: **9 CUMPLE, 3 CUMPLE PARCIAL, 0 NO CUMPLE y 0 NO
VERIFICADO**.

## 10. Riesgos residuales

1. Diagnóstico profesional, fichas técnicas y finalización tienen autorización
   backend probada, pero no un flujo React productivo integrado. No deben
   publicarse componentes legacy aislados basándose sólo en una capability.
2. Sin canal push, una revocación puede permanecer en el snapshot React hasta
   foco/visibilidad posterior al umbral o hasta un `403`; el backend la aplica
   inmediatamente en cada request.
3. Una capability positiva sólo expresa prerrequisitos globales. Ownership,
   estado, compatibilidad, validación y concurrencia siguen resolviéndose al
   operar el objeto.
4. `is_superuser` conserva el bypass técnico propio de Django y requiere control
   operacional fuera de la UX normal; `/me/` no lo expone ni lo interpreta como
   BusinessRole.
5. Las advertencias legacy de test/build y la paginación sin orden no bloquearon
   esta regresión, pero continúan como deuda independiente.

## 11. Veredicto del incremento

La evidencia nueva cierra el hueco de integración entre autoridad efectiva,
sesión, Router, navegación, requests y revocación. Las matrices completas de
backend y frontend no presentan regresiones. Los límites legacy permanecen
explícitos para la auditoría posterior.

`BH-062 INCREMENTO 5 = VALIDADO`
