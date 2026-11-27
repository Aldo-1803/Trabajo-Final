# BH-062 — Incremento 0: contención de contenido educativo

**Fecha:** 2026-11-10

**Baseline:** `2ce3aaff24bfd43cfc56f196748b0b69fb634a1b`

**Rama:** `save/work-in-progress`

## 1. Objetivo y vulnerabilidad original

El módulo de contenido educativo exigía autenticación, pero no aplicaba una
política uniforme de autorización:

- cualquier usuario con una relación `Personal`, incluso inactiva, recibía
  todos los borradores y archivados;
- un Cliente autenticado podía ejecutar `DELETE` directo sobre contenido
  publicado;
- `perform_destroy()` no comprobaba autoría ni permiso global;
- las comprobaciones de edición eran parciales y la creación no exigía que el
  vínculo `Personal` estuviera activo;
- las acciones de interacción podían operar contenido visible por un queryset
  administrativo, aunque no estuviera publicado;
- las rutas CRUD directas de likes y guardados permitían una superficie de
  mutación redundante;
- las tres rutas React administrativas exigían sólo una sesión autenticada.

El backend es ahora la autoridad de la contención. El guard React incorporado
es una defensa de navegación y no reemplaza los controles HTTP.

## 2. Superficie HTTP afectada

Se protegieron o acotaron las siguientes rutas bajo `/api/gestion/`:

| Ruta | Operaciones | Regla efectiva |
|---|---|---|
| `contenido-educativo/` | `GET`, `POST` | Lectura filtrada; creación sólo por Personal activo. |
| `contenido-educativo/{id}/` | `GET`, `PUT`, `PATCH`, `DELETE` | Queryset por visibilidad y mutación por ownership o permiso global. |
| `contenido-educativo/{id}/like/` | `POST` | Sólo contenido activo y `PUBLICADO`; además requiere perfil Cliente. |
| `contenido-educativo/{id}/guardar/` | `POST` | Sólo contenido activo y `PUBLICADO`; además requiere perfil Cliente. |
| `contenido-educativo/mis-guardados/` | `GET` | Omite contenido archivado, borrador o eliminado lógicamente. |
| `contenido-educativo/recomendados/` | `GET` | Conserva el filtro previo de activo y publicado. |
| `me-gusta/` y `me-gusta/{id}/` | `GET` | Sólo interacciones propias cuyo contenido siga activo y publicado. |
| `contenido-guardado/` y `contenido-guardado/{id}/` | `GET` | Sólo guardados propios cuyo contenido siga activo y publicado. |

`me-gusta` y `contenido-guardado` pasaron a `ReadOnlyModelViewSet`. Sus `POST`
y `DELETE` directos ya no son válidos; las mutaciones legítimas se concentran
en las acciones `like` y `guardar`, que aplican la condición de publicación.

No se encontraron acciones separadas para publicar o archivar. Ambas
transiciones continúan realizándose mediante `PUT/PATCH` del campo `estado`.

## 3. Política de autoría y gestión global

### 3.1 Autor válido

Un actor ejerce autoría únicamente cuando:

1. su usuario está vinculado a un registro `Personal`; y
2. ese `Personal` tiene `activo=True`.

No se infiere autoría desde `BusinessRole`, `Personal.rol`, `is_staff` ni desde
la existencia de una sesión. Un Personal inactivo pierde las facultades de
autor, aunque sigue pudiendo leer contenido publicado como cualquier usuario
autenticado.

La creación siempre exige un autor válido. Incluso un gestor global sin
`Personal` activo recibe 403 al crear, porque el modelo requiere una autoría
real. El autor se asigna desde la sesión y el campo `autor` recibido en el
payload se ignora por ser de sólo lectura.

### 3.2 Gestión global

La gestión global se concede exclusivamente mediante el permiso Django
efectivo `gestion.manage_content`, con independencia de su origen:

- grupo canónico de administrador;
- otro grupo autorizado;
- permiso individual.

`is_staff` por sí solo no concede autoridad. Un usuario con un BusinessRole
distinto conserva el permiso cuando éste es efectivo.

## 4. Lectura y ocultamiento

El queryset aplica esta jerarquía:

1. `gestion.manage_content`: todo el contenido con `activo=True`;
2. Personal activo sin permiso global: contenido activo y publicado, más todo
   el contenido activo de su propia autoría;
3. resto de usuarios autenticados: sólo contenido activo y `PUBLICADO`.

La misma regla protege listado y detalle. Un borrador ajeno queda fuera del
queryset y un ID conocido responde 404, sin confirmar su existencia. Los
objetos con `activo=False` permanecen fuera de todas las consultas, incluido el
gestor global.

Las respuestas siguen las convenciones DRF:

- **401** para una petición sin autenticación;
- **403** para una mutación no autorizada sobre un objeto publicado que sí es
  legítimamente visible;
- **404** para borradores, archivados ajenos u objetos eliminados que el actor
  no puede consultar.

## 5. Modificación, publicación, archivo y eliminación

`PUT`, `PATCH` y `DELETE` exigen una de estas condiciones:

- Personal activo y autor del objeto; o
- permiso efectivo `gestion.manage_content`.

La autorización de creación y de objeto se evalúa antes de validar el payload,
de modo que un actor sin autoridad recibe 403 incluso si envía datos
malformados y no obtiene primero detalles del contrato de escritura.

El autor activo puede editar, publicar y archivar su contenido propio. El
gestor global puede realizar esas operaciones sobre cualquier contenido
activo. Esta decisión conserva la semántica previa de update genérico sin
crear nuevas acciones ni permisos.

El campo `autor` continúa siendo de sólo lectura, por lo que ni el autor ni el
gestor pueden transferir autoría mediante el payload genérico.

`DELETE` conserva el comportamiento de dominio existente: no elimina la fila,
sino que cambia `activo` a `False`. La comprobación de autoridad ocurre antes
de esa mutación.

## 6. Contención frontend mínima

Las tres rutas administrativas usan ahora `ContentManagementRoute`:

- `/admin/contenido-educativo`;
- `/admin/contenido-educativo/crear`;
- `/admin/contenido-educativo/:id/editar`.

El guard combina únicamente condiciones ya publicadas por la sesión:

- permiso efectivo `gestion.manage_content`; o
- perfil `Personal` existente y activo.

Una cuenta Cliente deja de entrar por el solo hecho de estar autenticada. Se
preservan tanto autores activos como gestores globales. No se agregó un
contrato `capabilities`, no se alteró `/api/usuarios/me/` y no se infirieron
permisos desde roles nominales.

## 7. Pruebas positivas y negativas

Se agregó
`gestion/tests/test_content_authorization_bh062_0.py`, con 16 pruebas HTTP que
cubren:

- 401 sin autenticación;
- Cliente autenticado;
- usuario sin `Personal`;
- autor con Personal activo;
- Personal activo ajeno;
- Personal inactivo;
- gestor por rol administrador y permiso efectivo;
- `is_staff` sin permiso de negocio;
- BusinessRole `EMPLEADO` con grant efectivo `manage_content`;
- listados y detalles propios, públicos y ocultos;
- creación permitida y rechazada;
- `PUT`, `PATCH`, publicación y archivo;
- conservación del autor ante payloads manipulados;
- 403 y 404 sin cambios de título, estado, autor o flag activo;
- eliminación lógica propia y global;
- like, guardado y sus listados frente a borradores, archivados y soft delete;
- cierre de mutaciones CRUD directas en likes y guardados.

El frontend agregó cuatro casos al test de rutas: Cliente rechazado, Personal
activo admitido, Personal inactivo rechazado y grant efectivo admitido sin
perfil Personal.

## 8. Validaciones y regresiones

Resultados ejecutados desde el árbol de trabajo:

- focal backend BH-062.0: **16 tests OK**;
- matriz relacionada de contenido, superficies BH-059, estado/revocación de
  Personal, roles y sesión efectiva: **81 tests OK**;
- descubrimiento backend general: **163 tests OK**;
- `ProtectedRoute.test.js`: **38 tests OK**;
- `python manage.py check --settings=bohemiacore.test_settings`: **OK**;
- `makemigrations --check --dry-run`: **sin cambios**;
- `npm run build`: **compiló correctamente**.

El build conserva advertencias ESLint y de dependencias preexistentes en
pantallas legacy; ninguna corresponde a los archivos nuevos de autorización.

La matriz exhaustiva de 95 módulos no se repitió localmente: la última
ejecución documentada contiene 1.108 pruebas y requirió 2.619,64 segundos en
PostgreSQL secuencial. Para este incremento acotado se priorizó la matriz de 81
casos directamente relacionada, además de la corrida de descubrimiento general
indicada arriba.

## 9. Cambios deliberadamente excluidos

Este incremento no implementa:

- BH-062 Incrementos 1 a 5;
- contrato general de `capabilities`;
- cambios en `/api/usuarios/me/`;
- nuevos permisos, grants o BusinessRoles;
- servicios separados de publicación o archivo;
- rediseño del editor o del listado;
- cambios financieros ni migraciones.

## 10. Riesgos residuales para Incrementos 1 y 2

1. **Acciones visibles en listados compartidos.** Un autor activo puede leer
   contenido publicado ajeno desde la API Cliente y la pantalla administrativa
   todavía no representa ownership por botón. El backend rechaza editar o
   borrar esos objetos, pero Incremento 3 debe evitar controles que terminarán
   en 403.
2. **Creación para gestores sin Personal.** Un gestor global puede entrar a la
   pantalla por su permiso, pero no puede crear si carece de autoría activa. La
   UI general aún no expresa esta condición compuesta por acción.
3. **Contrato compuesto temporal para Incremento 1.**
   `ContentManagementRoute` combina `manage_content` y perfil Personal activo
   con helpers existentes. Debe
   migrarse al contrato general de capacidades cuando se implemente BH-062.1,
   evitando duplicar lógica en más módulos.
4. **Alineación de navegación en Incremento 2.** Este cambio cierra las URLs de
   contenido, pero no modifica landing, menú ni navegación global de otros
   módulos. Esas superficies deben consumir el contrato del Incremento 1 sin
   volver a inferir autoridad desde BusinessRole.
5. **Revocación durante una sesión abierta.** La UI no refresca automáticamente
   permisos o estado de Personal; el backend sí aplica el estado vigente en
   cada petición. El incremento de actualización dinámica debe resolver la
   sincronización y UX de 403.
6. **Transiciones de estado genéricas.** Publicar y archivar siguen siendo
   updates ordinarios. No se introdujo un workflow nuevo en este incremento.

## 11. Veredicto

La exposición de borradores y las mutaciones administrativas sin autoridad
quedaron contenidas en backend. Los accesos legítimos de autores activos,
Clientes sobre contenido publicado y gestores con permiso efectivo se
preservaron.

`BH-062 INCREMENTO 0 = VALIDADO`
