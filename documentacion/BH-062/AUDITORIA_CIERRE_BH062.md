# BH-062 — Auditoría independiente de cierre técnico

**Fecha:** 2026-11-11
**Rama:** `save/work-in-progress`
**Baseline auditado:** `fa2a027dd7a8f4fd8b142f0cd54b87317d720406`

## 1. Resultado ejecutivo

La auditoría independiente obtiene:

- **9 criterios CUMPLE**;
- **3 criterios CUMPLE PARCIAL**;
- **0 criterios NO CUMPLE**;
- **0 criterios NO VERIFICADO**.

Los tres parciales corresponden a diagnóstico profesional, fichas técnicas y
finalización de servicios. Tienen autoridad backend, pero no una superficie
React productiva. No se convirtieron en `CUMPLE` ni se tomó la validación de los
Incrementos 0–5 como sustituto de evidencia.

Esta ausencia es **funcionalidad pendiente independiente y diferible**, no un
bloqueante de BH-062, por estas razones verificables:

1. `frontend/src/routes/index.js`, `routes/routes.js` y
   `navigation/navigationConfig.js` no publican rutas ni navegación para esos
   tres flujos; tampoco existe una acción de finalización en las pantallas
   productivas de Turnos;
2. el análisis original ordenó integrar esos flujos **“sólo si se confirma el
   flujo existente, sin inventar CRUD genérico ni nuevas funciones de negocio”**
   (`ANALISIS_BH062_UI_SEGUN_PERMISOS.md`, líneas 580–589);
3. el mismo análisis advirtió que los componentes legacy de fichas no debían
   exponerse hasta integrarlos al flujo semántico vigente (líneas 719–722);
4. no se confirmó un flujo React profesional existente que BH-062 hubiera
   degradado: diagnóstico no tiene componente profesional, finalización no
   tiene consumidor y los dos componentes de ficha nunca son importados;
5. las superficies React que sí están publicadas separan autoridad efectiva,
   lectura, mutaciones, URL, menú, landing, revocación y errores.

Por lo tanto, los parciales limitan el alcance funcional disponible, pero no
invalidan la representación de permisos de las superficies productivas. Esto
es cierre técnico de BH-062, **no certificación de aptitud general para
producción** ni aprobación para publicar esos tres flujos.

> **Veredicto:** `BH-062 = LISTO PARA CIERRE TÉCNICO`.

## 2. Baseline y preservación del entorno

Al iniciar y al cerrar la auditoría se verificó que `HEAD`, upstream y el remoto
de la rama coinciden en:

```text
fa2a027dd7a8f4fd8b142f0cd54b87317d720406
```

Se preservaron sin modificación los cambios locales ajenos preexistentes:

- `bohemiacore/bohemiacore/settings.py`;
- archivos bajo `bohemiacore/media/`;
- `bohemiacore/show_urls.py`;
- `frontend/cypress.config.js` y `frontend/cypress/`.

La auditoría no modificó implementación, tests, configuración, backlog ni
documentos históricos. El único archivo agregado es este informe. No se hizo
commit ni push.

## 3. Metodología

La revisión combinó:

1. recuperación literal de los 12 criterios de la sección 13 del análisis;
2. inspección de código productivo backend y frontend;
3. lectura de las aserciones, no sólo de resultados reportados;
4. trazabilidad de `/me/`, siete capabilities, permissions DRF, ownership,
   estado, rutas, menú, landing, notificaciones, acciones y errores;
5. búsqueda de consumidores React reales de diagnóstico, ficha y
   `finalizar_turno`;
6. pruebas focales independientes;
7. regresión completa backend sobre PostgreSQL con 99 módulos explícitos;
8. suite frontend completa y build React de producción.

Las corridas focales son subconjuntos y no se suman a las matrices completas.

## 4. Matriz literal de los 12 criterios

| # | Criterio original literal | Clasificación | Evidencia principal |
|---|---|---|---|
| 1 | “contenido educativo niega lectura administrativa y mutaciones no autorizadas incluso por petición HTTP directa” | **CUMPLE** | Querysets por publicación/autor/gestor, autor impuesto por backend, destroy lógico protegido y viewsets de interacción sólo lectura; pruebas HTTP y React negativas. |
| 2 | “`/me/` sigue siendo mínimo y representa todas las capacidades compuestas que React necesita, sin exponer flags ni estructura administrativa” | **CUMPLE** | `CurrentSessionSerializer`, `effective_access.py`, respuesta `no-store`, catálogo limitado y siete booleanos estrictos; no expone grupos, grants, skills, `is_staff` ni `is_superuser`. |
| 3 | “menú, landing, notificaciones y rutas directas toman decisiones consistentes por permisos/capacidades efectivos” | **CUMPLE** | `navigationConfig.js`, `sessionLanding.js`, `notificationNavigation.js`, `ProtectedRoute.js` e integración Router/sesión/HTTP para rol, grupo técnico y permiso individual. |
| 4 | “no se usa `is_staff`, `is_superuser`, `Personal.rol` ni nombre de BusinessRole como sustituto de una capacidad” | **CUMPLE** | La SPA decide por permisos, capabilities y perfiles. BusinessRole sólo prioriza experiencia/etiqueta; `function_role` es contexto laboral. Los flags no forman parte de `/me/` ni habilitan ruta/acción. |
| 5 | “cada pantalla parcial separa lectura, creación, edición, eliminación/desactivación y acciones especiales” | **CUMPLE PARCIAL** | Usuarios, Personal, Productos, Servicios, Contenido, Caja, Reportes y Turnos separan operaciones. Diagnóstico, fichas y finalización no tienen pantalla React productiva que permita completar la verificación. |
| 6 | “acciones de rol requieren simultáneamente los permisos que exige el backend” | **CUMPLE** | Alta de administrador y cambio de BusinessRole exigen `manage_users + assign_roles`; acceso/rol de Personal exige `manage_personal + assign_roles`, tanto en botón/handler como API. |
| 7 | “condiciones técnicas no cumplidas se detectan antes de ofrecer la acción y se explican sin revelar detalles administrativos” | **CUMPLE PARCIAL** | Revisión técnica y fórmula usan capabilities compuestas; mensajes y errores son seguros. No existe UI productiva para anticipar skill/estado en diagnóstico, ficha o finalización. |
| 8 | “URL directa sin acceso no monta la pantalla ni consulta datos protegidos” | **CUMPLE** | Guards fallan cerrado antes de montar hijos; tests verifican ausencia de fetch, desmontaje tras revocación y redirección segura. |
| 9 | “un cambio de rol, permiso, estado de cuenta/Personal o habilidad se refleja durante la sesión mediante la política de refresco acordada” | **CUMPLE** | Refresh por foco/visibilidad tras 45 s, refresh ante 403, deduplicación e invalidación de respuestas obsoletas; backend niega de inmediato. |
| 10 | “401, 403, 409, validación, red y 5xx tienen tratamientos diferenciados” | **CUMPLE** | `httpErrors.js`, interceptor global, `SessionContext` y pantallas focales: 401 limpia, 403 refresca sin logout automático, conflicto/validación/red/servidor conservan semántica diferenciada. |
| 11 | “las pruebas cubren rol, grupo técnico, permiso individual, lectura sin escritura, capacidades compuestas, revocación en sesión y no filtración” | **CUMPLE PARCIAL** | Todas las categorías exigidas están cubiertas en superficies productivas y backend. No hay prueba React integrada de los tres flujos no publicados. |
| 12 | “el backend continúa siendo autoridad y no se incorporan roles, grants, editor genérico, cambios financieros ni rediseño visual fuera de alcance” | **CUMPLE** | DRF/servicios revalidan cada request; no se agregaron roles, grants arbitrarios, editor genérico, WebSocket, cambios financieros ni rediseño para cerrar BH-062. |

## 5. Evidencia detallada por criterio

### 5.1 Contenido educativo y no filtración

`ContenidoEducativoViewSet` distingue tres alcances:

- Cliente/no Personal: sólo contenido `PUBLICADO` y activo;
- autor: publicado más contenido propio;
- `content.manage_global`: contenido activo global.

La creación exige `content.author`, ignora cualquier autor enviado y usa el
Personal activo del request. Update y destroy exigen autoría concreta o gestión
global; destroy hace desactivación lógica. Like/guardado requieren Cliente y
contenido activo/publicado, y los viewsets de `MeGusta`/`ContenidoGuardado` no
admiten CRUD directo.

`test_content_authorization_bh062_0.py` demuestra, entre otros casos:

- Cliente sin acceso administrativo ni borradores;
- Personal ajeno sin borradores ni mutaciones;
- Personal inactivo sin autoría;
- autor propio con acceso limitado;
- gestor global con lectura/mutación global pero sin identidad de autor
  inventada;
- autor inmutable frente a spoofing;
- `PUT`, `PATCH` y `DELETE` rechazados sin cambio persistido;
- registros de interacción preservados frente a mutaciones directas.

`GestionContenidoEducativo.test.js` y `EditorContenidoEducativo.test.js`
verifican que contenido ajeno sea sólo lectura, que no existan controles
mutadores sin autoridad y que no se emitan requests mutadoras.

### 5.2 `/me/`, capabilities y autoridad efectiva

`CurrentSessionSerializer` proyecta únicamente:

- identidad mínima activa;
- un BusinessRole consistente;
- permisos efectivos incluidos en `BusinessPermission.ALL`;
- existencia/actividad de perfiles;
- siete capabilities booleanas.

Las capabilities canónicas son:

1. `technical_booking.review`;
2. `diagnosis.create`;
3. `technical_record.read_global`;
4. `technical_record.manage`;
5. `service_formula.manage`;
6. `content.author`;
7. `content.manage_global`.

Los predicados de `effective_access.py` son reutilizados por `/me/` y las
permission classes DRF. Las pruebas cubren permiso heredado de BusinessRole,
grupo técnico y grant individual, más combinaciones negativas de cuenta,
Personal, habilidad y asignación. `SessionContext` sólo acepta `true` booleano;
valores ausentes, desconocidos o con tipo incorrecto fallan cerrado.

Una capability positiva expresa prerrequisitos globales y no elimina ownership,
estado o concurrencia por objeto. En particular, aunque la capability se llama
`technical_record.read_global`, `FichaTecnicaViewSet.get_queryset()` conserva
alcance propio/asignado. Esta diferencia debe resolverse semánticamente antes de
crear un visor global, pero no filtra datos ni afecta una ruta React actual.

### 5.3 Rutas, menú, landing y notificaciones

- `ProtectedRoute` permite permiso, cualquiera de varios permisos, capability,
  cualquiera de varias capabilities, perfil y perfil activo; ante denegación no
  monta el hijo.
- `ContentManagementRoute` aplica `content.author OR
  content.manage_global`.
- `navigationConfig.js` usa el mismo contrato efectivo que las rutas.
- `sessionLanding.js` selecciona el primer destino permitido; BusinessRole sólo
  ordena prioridades de experiencia y no concede autoridad.
- `notificationNavigation.js` exige el permiso exacto del destino o perfil
  propio, y usa landing seguro como fallback sin propagar identificadores a una
  ruta no autorizada.

La integración `PermissionUiIntegration.test.js` verifica con Router,
`SessionContext`, `/me/`, Header, guard y cliente HTTP reales que BusinessRole,
grupo técnico y permiso individual producen la misma decisión de ruta, menú,
landing, notificación, fetch y acción.

La compatibilidad genérica `allowedRoles` aún existe en los helpers, pero ninguna
ruta o entrada de navegación productiva la usa como sustituto de permiso o
capability.

### 5.4 Pantallas parciales y acciones compuestas

Las superficies publicadas separan, según corresponda:

- agenda, alta, llegada, reprogramación, cancelación y lectura propia;
- lectura y mutación de stock, precios, metadata y promociones;
- lectura de servicio, gestión de precio y gestión de fórmula;
- CRUD/estado laboral de Personal, skills y acceso digital;
- lectura general y montos financieros;
- consulta, registro y conciliación de pagos;
- autoría propia y gestión global de contenido.

`GestionUsuarios` y `GestionPersonal` comprueban las conjunciones de permisos
antes de mostrar y ejecutar acciones de rol/acceso. Sus handlers vuelven a
fallar cerrado y envían contratos dedicados, sin flags técnicos ni grants
arbitrarios. El backend repite la conjunción y conserva la autoridad final.

Los tres flujos sin UI impiden elevar los criterios 5, 7 y 11 a `CUMPLE`; no
impiden afirmar que las pantallas realmente publicadas cumplen.

### 5.5 Revocación durante sesión

`SessionContext.js` implementa:

- umbral `SESSION_REFRESH_INTERVAL_MS = 45 * 1000`;
- refresh por `focus` y `visibilitychange` cuando vence el umbral;
- deduplicación mediante la promesa en vuelo;
- reemplazo atómico del snapshot;
- secuencia/generación para ignorar respuestas antiguas después de logout,
  cambio de token o identidad;
- un único refresh silencioso ante ráfagas de 403;
- limpieza de tokens y sesión ante 401 autenticado;
- conservación de sesión ante 403 de ownership si `/me/` no cambió.

La integración confirma que revocar autoridad y recuperar foco después del
umbral retira ruta, menú y acción, desmonta el hijo y no repite el GET protegido
ni emite POST. No existe reenvío automático de una mutación rechazada.

Sin push, React puede conservar un snapshot hasta el siguiente foco/visibilidad
elegible o 403. El backend revalida y niega inmediatamente cada request; ésa es
la autoridad de seguridad.

### 5.6 Errores

`classifyHttpError()` distingue sesión (401), prohibición (403), conflicto
(409), validación (400/422), red/timeout, servidor (5xx) y desconocido. El
interceptor global emite eventos de sesión, no reintenta mutaciones y excluye
los endpoints públicos de autenticación.

Las pantallas focales muestran mensajes seguros para conflicto, validación y
falta de acceso; `AccesoDenegado` permite refrescar autoridad y volver sólo a un
destino autorizado. No revela nombres de permisos, grupos o habilidades.

## 6. Evaluación de los tres flujos parciales

### 6.1 A. Diagnóstico profesional

| Aspecto | Resultado |
|---|---|
| Backend | CRUD disponible en `/api/gestion/diagnosticos-capilares/`; DELETE devuelve 405. |
| Autoridad | Escritura: `diagnosis.create` (`create_diagnosis` + cuenta/Personal/habilidad `DIAGNOSTICO` activos). Lectura: Cliente propio o `technical_record.read_global`. |
| Ownership/estado | Backend impone `profesional=request.user`; un escritor sin gestión global sólo alcanza diagnósticos propios; Cliente sólo los propios. |
| React | No existe componente profesional ni ruta/menú/acción productiva. El consumo Cliente de información capilar no constituye un editor profesional. |
| Tests | `test_diagnosis_authorization_api.py`, tests de capabilities y paridad DRF; cubren skill/permiso/estado, spoofing, lectura propia/global, escritura ajena y DELETE 405. |
| Riesgo al publicar | Reconstruir permiso simple en React, omitir ownership, mezclar lectura global con escritura o mostrar detalles administrativos del 403. |
| Trabajo mínimo seguro | Confirmar el recorrido de negocio; crear ruta y navegación por capability; separar visor/alta/edición; usar Axios global y taxonomía de errores; comprobar estado/ownership por objeto; agregar tests de URL, lectura sin escritura, revocación y DOM. |

**Clasificación:** funcionalidad pendiente independiente, **no bloqueante de
BH-062**. No había flujo profesional React confirmado que BH-062 debiera
adaptar.

### 6.2 B. Fichas técnicas

| Aspecto | Resultado |
|---|---|
| Backend | `FichaTecnicaViewSet` separa lectura y escritura; DELETE devuelve 405 para preservar historia. |
| Autoridad | Lectura: Cliente propio o `technical_record.read_global`; escritura: `technical_record.manage`. Las capabilities técnicas requieren cuenta/Personal/habilidad activos. |
| Ownership/estado | Cliente sólo ve lo propio y sin fórmulas; Personal sólo fichas redactadas por sí o Turnos asignados; serializer impone autor y detalle operable. |
| React | Existen `RegistroFichaTecnica.js` y `VisualizadorFichas.js`, pero no están importados, enrutados ni incluidos en navegación. |
| Tests | Suite BH-060.3 cubre lectura Cliente, fórmula oculta, escritura propia/ajena, preservación de autor/detalle, skill/estado y DELETE 405. |
| Riesgo al publicar | `fichasTecnicasApi.js` crea Axios propio fuera del coordinador global 401/403; controles legacy son incondicionales; `VisualizadorFichas` ofrece DELETE que backend rechaza; textos/comments hablan de admin/staff; el nombre `read_global` no coincide con el queryset propio/asignado. |
| Trabajo mínimo seguro | No enrutar los componentes actuales. Definir alcance de lectura; migrar al cliente HTTP global; separar lectura/creación/edición y eliminar DELETE; guard por capability más ownership/estado; mensajes seguros y pruebas integradas. |

**Clasificación:** funcionalidad pendiente independiente y componente legacy no
publicable, **no bloqueante de BH-062** mientras siga aislado.

### 6.3 C. Finalización de servicios

| Aspecto | Resultado |
|---|---|
| Backend | `POST /api/gestion/turnos/{id}/finalizar_turno/` marca realizado, puede crear diagnóstico post-servicio, asigna cuidados/rutinas y programa retoques. |
| Autoridad | Conjunción backend `gestion.finalize_service` + `diagnosis.create` efectiva (incluye Personal y habilidad `DIAGNOSTICO` activos). |
| Ownership/estado | Es una acción global autorizada; rechaza repetición si ya está `REALIZADO`. No se observó validación de una transición origen más estricta. |
| React | No hay consumidor de `finalizar_turno`, botón, ruta ni navegación productiva. |
| Tests | `test_diagnosis_authorization_api.py` prueba denegación sin skill y éxito con ambos permisos; BH-060.3 prueba asignación interna de rutina sin exigir un permiso adicional. |
| Riesgo al publicar | La UI podría ofrecer la acción por un solo permiso o en estado inválido. El endpoint sólo rechaza `REALIZADO` y no se observó una transacción atómica que envuelva todos los efectos secundarios; una falla intermedia requiere análisis antes de producción. |
| Trabajo mínimo seguro | Definir estados origen y actor/objeto operable; hacer explícita la atomicidad/idempotencia; proyectar una capability compuesta si React necesita una sola decisión; integrar la acción en Turnos con explicación previa, confirmación, estado en vuelo, errores diferenciados y tests de no reintento. |

**Clasificación:** funcionalidad pendiente independiente y riesgo de despliegue
si se publica sin endurecimiento, **no bloqueante de la UI BH-062 actual**.

## 7. Pruebas ejecutadas

### 7.1 Backend PostgreSQL

Configuración comprobada:

- engine `django.db.backends.postgresql`;
- `bohemiacore.test_settings`;
- base obligatoriamente prefijada `test_`;
- `StablePostgresTestRunner`;
- ejecución secuencial con módulos explícitos y `--keepdb --noinput`.

| Ejecución | Alcance | Resultado |
|---|---|---|
| Focal independiente | 17 módulos de contenido, sesión, capabilities, roles, Personal, skills, diagnóstico, fichas, revisión técnica y permisos BH-060 relevantes | **265/265 tests aprobados; 0 fallos; 302,730 s** |
| Completa independiente | 99 módulos `test*.py` enumerados directamente en `usuarios` y `gestion/tests` | **1.143/1.143 tests únicos aprobados; 0 fallos; 2.577,469 s** |

La matriz focal es subconjunto de la completa y no se suma a sus pruebas
únicas. Los trazados de storage, proveedor y auditoría corresponden a fallos
forzados por casos negativos que aprobaron; no son fallos de la ejecución.

### 7.2 Frontend

| Ejecución | Resultado |
|---|---|
| Focal independiente (14 suites) | **14/14 suites; 208/208 tests aprobados** |
| Completa | **42/42 suites; 397/397 tests únicos aprobados** |
| Build React de producción | **Aprobado**, compilado con advertencias preexistentes |

Las 208 pruebas focales están contenidas en las 397 y no se suman. Persisten
warnings históricos de `act(...)`, Browserslist, dependencia dinámica y lint;
no produjeron fallos ni se ocultaron.

## 8. Hallazgos y severidad

| ID | Clasificación | Hallazgo | Decisión |
|---|---|---|---|
| H-1 | No bloqueante de BH-062 / funcionalidad pendiente independiente | Diagnóstico profesional no tiene flujo React productivo. | Diferir a una tarea funcional con integración segura. |
| H-2 | No bloqueante de BH-062 / funcionalidad pendiente independiente | Fichas no están publicadas y sus componentes legacy no cumplen el contrato actual de sesión/acciones. | Mantener aislados; no enrutar directamente. |
| H-3 | No bloqueante de BH-062 / funcionalidad pendiente independiente | Finalización no tiene acción React. | Integrar sólo tras definir transición, atomicidad y UX. |
| H-4 | Riesgo de despliegue | Finalización sólo bloquea repetición `REALIZADO`; no se observó envolvente atómica explícita para todos los efectos. | Revisar antes de habilitar el flujo en producción. |
| H-5 | Riesgo semántico | `technical_record.read_global` habilita el endpoint, pero fichas filtra a autor/Turno asignado. | Definir si el nombre o el alcance es el contrato correcto antes de un visor. |
| H-6 | Riesgo residual aceptado | React no tiene push; puede tardar hasta foco/visibilidad elegible o 403 en retirar UI. | Backend niega inmediatamente; mantener política documentada. |
| H-7 | Mejora futura fuera de alcance | Warnings históricos de tests/build y paginación de fichas sin orden. | Tratar como deuda separada. |

**No se encontró un bloqueante real de BH-062.**

## 9. Riesgos residuales

1. Una capability global no garantiza que un objeto concreto sea operable;
   ownership, estado, concurrencia e idempotencia siguen en backend.
2. `is_superuser` conserva el bypass técnico de Django. `/me/` no lo expone ni
   lo transforma en BusinessRole; su control es operacional.
3. Persisten referencias legacy a `is_staff` en código backend de Turnos, pero
   las escrituras genéricas están deshabilitadas y la SPA no las usa como
   autoridad. Deben evitarse en nuevas funcionalidades.
4. Publicar los componentes legacy de ficha abriría 403/405 predecibles y
   desacoplaría la revocación del coordinador HTTP global.
5. El cierre no certifica el resto del producto ni reemplaza pruebas E2E en un
   entorno de despliegue real.

## 10. Recomendación

Cerrar técnicamente BH-062 en el baseline auditado. No es necesario un
incremento adicional de BH-062 porque el objetivo específico —representar la
autoridad efectiva en las superficies React productivas, sin depender de ocultar
links y manteniendo al backend como autoridad— está satisfecho.

Crear, fuera del cierre, una tarea funcional focal para diagnóstico, fichas y
finalización si el producto decide publicarlos. Esa tarea debe comenzar por
confirmar el recorrido de negocio y endurecer los riesgos indicados; no debe
consistir en enrutar componentes legacy ni en inventar un CRUD genérico.

La recomendación cambia a bloqueo sólo si se redefine el alcance para exigir
que esos tres flujos formen parte del producto React entregable. Esa exigencia
no figura como incondicional en el análisis original y contradice la condición
explícita de integrar únicamente un flujo existente confirmado.

---

`BH-062 = LISTO PARA CIERRE TÉCNICO`
