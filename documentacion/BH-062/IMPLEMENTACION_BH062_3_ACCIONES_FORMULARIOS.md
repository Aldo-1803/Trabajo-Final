# BH-062 — Incremento 3: acciones y formularios por acceso efectivo

## Resultado

El frontend representa los prerrequisitos globales conocidos para cada acción,
sin sustituir las comprobaciones de ownership, estado, concurrencia y validación
que siguen perteneciendo al backend.

Este incremento sólo modifica React, tests y documentación. No cambia permisos,
roles, serializers, viewsets ni servicios backend.

## Pantallas y acciones modificadas

### Gestión de Usuarios

- `Nuevo administrador` exige simultáneamente
  `usuarios.manage_users` y `usuarios.assign_roles`.
- La pantalla y las operaciones ordinarias de cuentas siguen disponibles con
  `usuarios.manage_users` solamente.
- El handler de creación repite el guard antes de ejecutar el `POST`; ocultar el
  botón no es la única barrera frontend.

### Gestión de Personal

- Crear acceso, vincular una cuenta y cambiar el BusinessRole laboral exigen
  `gestion.manage_personal` y `usuarios.assign_roles`.
- Los handlers, la carga de usuarios elegibles y la apertura de modales repiten
  el guard compuesto.
- Crear/editar Personal y sus acciones semánticas de estado permanecen bajo
  `gestion.manage_personal`.
- El modo limitado de `gestion.manage_skills` conserva el directorio mínimo y no
  muestra contacto, función laboral ni datos de acceso.

### Servicios y fórmulas

- La fórmula usa exclusivamente `service_formula.manage`; el permiso simple
  `gestion.manage_formulas` no habilita controles.
- `gestion.manage_prices` habilita metadata, precio, estado, equipamiento,
  creación y baja del Servicio.
- Con sólo fórmula, la metadata se presenta deshabilitada y con explicación;
  sólo se envía `plantilla_formula`.
- Con sólo precios, la fórmula no se proyecta como campo editable y no aparece
  en el payload.
- Sin ninguna autoridad mutadora, el listado permanece legible y no se ofrecen
  acciones de escritura.

### Contenido educativo

- Crear depende de `content.author`, que representa un Personal activo. Un
  gestor global sin identidad de autor no recibe el control de creación.
- Editar, cambiar estado y eliminar se ofrecen sólo cuando el elemento pertenece
  a `profiles.personal.id` activo o existe `content.manage_global`.
- `content.author=true` no se interpreta como autoridad sobre contenido ajeno.
- La comparación usa `autor.id` proyectado por el serializer; no infiere
  ownership por nombre, BusinessRole ni flags técnicos.
- La transición visible respeta el estado actual:
  `BORRADOR → PUBLICADO`, `PUBLICADO → ARCHIVADO` y
  `ARCHIVADO → BORRADOR`.
- El editor de contenido ajeno publicado queda en modo lectura para un autor sin
  gestión global: campos deshabilitados, explicación visible y ausencia de
  `PUT`.
- La eliminación continúa siendo lógica en backend (`DELETE` marca `activo`
  falso).

### Retornos internos

Se agregó `getAuthorizedReturnPath()`, derivado de `getLandingPath()`, para no
duplicar la matriz de acceso. Configuración, Servicios, Equipamiento, Productos y
Auditoría sólo muestran `Volver` cuando el primer destino efectivo es distinto
de la pantalla actual. Gestión de Usuarios conserva sus accesos rápidos
condicionados por el permiso propio del destino. Los accesos rápidos del
Dashboard ya estaban alineados por BH-062.2 y no se reescribieron.

## Matriz acción × autoridad × endpoint

| Pantalla / acción | Autoridad frontend | Restricción adicional | Endpoint |
|---|---|---|---|
| Usuarios: listar, resumen, estado | `usuarios.manage_users` | Reglas semánticas backend | `GET /api/gestion/admin/usuarios/`; acciones de cuenta |
| Crear administrador | `usuarios.manage_users` + `usuarios.assign_roles` | Contrato dedicado, motivo y contraseña válida | `POST /api/usuarios/admin/administradores/crear/` |
| Cambiar BusinessRole de Usuario | `usuarios.manage_users` + `usuarios.assign_roles` | Perfiles compatibles, cuenta protegida, último admin y autoridad residual | `POST /api/gestion/admin/usuarios/{id}/cambiar-rol-negocio/` |
| Personal: CRUD laboral | `gestion.manage_personal` | Estado vigente | `/api/gestion/personal/` |
| Personal: crear acceso | `gestion.manage_personal` + `usuarios.assign_roles` | Personal activo, sin cuenta, rol laboral permitido | `POST /api/gestion/personal/{id}/crear-acceso/` |
| Personal: vincular cuenta | `gestion.manage_personal` + `usuarios.assign_roles` | Cuenta elegible y vínculos únicos | `POST /api/gestion/personal/{id}/vincular-usuario/` |
| Personal: cambiar rol de acceso | `gestion.manage_personal` + `usuarios.assign_roles` | Personal activo, cuenta vinculada, `EMPLEADO` o `PROFESIONAL` | `POST /api/gestion/personal/{id}/cambiar-rol-acceso/` |
| Personal: skills | `gestion.manage_skills` | Motivo, habilidad y asignación vigentes | directorio, catálogo y acciones `/habilidades/` |
| Servicio: crear/desactivar/eliminar | `gestion.manage_prices` | Validaciones de catálogo y estado | `POST/DELETE/PATCH /api/gestion/servicios/` |
| Servicio: precio y metadata | `gestion.manage_prices` | Payload sin fórmula si falta capability | `PATCH /api/gestion/servicios/{id}/` |
| Servicio: fórmula | `service_formula.manage` | Permiso `manage_formulas` y skill `DIAGNOSTICO` ya compuestos por backend | `PATCH /api/gestion/servicios/{id}/` |
| Contenido: crear propio | `content.author` | Personal activo; backend fija `autor` | `POST /api/gestion/contenido-educativo/` |
| Contenido: editar | autor concreto o `content.manage_global` | Queryset, ownership y contenido activo | `PUT /api/gestion/contenido-educativo/{id}/` |
| Contenido: publicar/archivar/reabrir | autor concreto o `content.manage_global` | Estado actual visible; backend revalida ownership | `PATCH /api/gestion/contenido-educativo/{id}/` |
| Contenido: eliminación lógica | autor concreto o `content.manage_global` | Contenido activo y ownership | `DELETE /api/gestion/contenido-educativo/{id}/` |

## Lectura sin escritura

- Servicios conserva el catálogo cuando no existe autoridad mutadora. Un gestor
  de fórmula ve metadata deshabilitada y un gestor de precios no recibe la
  fórmula protegida.
- Personal con `manage_skills` consulta sólo el directorio mínimo y skills.
- Un autor puede leer contenido publicado ajeno devuelto por el queryset, pero
  no recibe acciones sobre ese objeto.
- El editor mantiene visibles los datos autorizados en modo lectura cuando falta
  ownership, sin construir un payload mutador.

## Revisión de flujos técnicos

- **Revisión técnica:** ya está integrada en `/revision-tecnica` y protegida por
  `technical_booking.review`; se mantuvo sin cambios.
- **Diagnóstico profesional:** existe autorización backend compuesta
  (`diagnosis.create`), pero no hay una pantalla React productiva que complete
  selección de Cliente/Turno, ownership y estados.
- **Ficha técnica:** `RegistroFichaTecnica` y `VisualizadorFichas` permanecen
  aislados. Usan un flujo legacy que mezcla lectura global, borrado y carga por
  Turno sin resolver todavía alcance por objeto y estados.
- **Finalización de Servicio:** el endpoint exige `gestion.finalize_service` más
  la capacidad efectiva de diagnóstico y ejecuta efectos de negocio amplios; no
  existe un flujo React completo y validado para reunir su payload.

No se publicaron rutas ni se conectaron esos componentes aislados. Integrarlos
requiere una decisión posterior y no forma parte del Incremento 3.

## Pruebas y regresiones

Ejecuciones realizadas:

1. Primera ejecución focal: detectó dos aserciones de selector y dos mocks de
   router incompletos en los tests nuevos. No evidenció defectos productivos; se
   corrigió el harness antes de validar.
2. Repetición focal de Usuarios, Personal, Servicios, listado/editor de
   Contenido y landing: **6 suites, 67 tests, todos aprobados**.
3. Suite frontend completa final, que además incluye la prueba de eliminación
   lógica propia agregada después de la repetición focal: **39 suites, 363 tests,
   todos aprobados**.
4. Build React de producción: se ejecutó una vez durante la implementación y se
   repitió tras corregir dependencias de hooks. Ambas ejecuciones aprobaron; el
   build final conserva sólo advertencias históricas de dependencias y lint
   ajenas a este incremento.

Los tests nuevos verifican controles y ausencia de peticiones mutadoras, los
cuatro cruces de autoridad de Servicios, payloads parciales, autoría propia y
ajena, gestión global, lectura sin escritura, restricciones de estado y retorno
a un destino autorizado.

No se ejecutaron tests backend porque no hubo cambios de contrato ni código
backend.

## Limitaciones pendientes

- El backend sigue siendo la autoridad ante revocaciones concurrentes y cambios
  de estado posteriores al render.
- El refresco por foco/visibilidad y la reacción global a `403` pertenecen al
  Incremento 4 y no se implementaron.
- Diagnóstico, ficha técnica y finalización permanecen pendientes de un flujo
  integral con ownership, estados y contrato de datos definidos.
- No se inició la matriz final del Incremento 5.
