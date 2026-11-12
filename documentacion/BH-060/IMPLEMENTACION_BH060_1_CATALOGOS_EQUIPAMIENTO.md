# BH-060 Incremento 1 — Catálogos y equipamiento

## Estado

**BH-060 INCREMENTO 1 = VALIDADO**

- Baseline: `9bad62c235a4fa88a6f470664805cf57a9f47af1`.
- Alcance: autorización de escritura, borrado seguro y pruebas de catálogos
  capilares, categorías de servicio y equipamiento.
- Fuera de alcance: BH-060 Incremento 2, lógica financiera y cambios de otros
  dominios.

## Endpoints revisados

| Recurso | Endpoint | Lectura | Escritura |
| --- | --- | --- | --- |
| TipoCabello | `/api/gestion/tipos-cabello/` | Pública | `gestion.manage_configuration` |
| GrosorCabello | `/api/gestion/grosores-cabello/` | Pública | `gestion.manage_configuration` |
| PorosidadCabello | `/api/gestion/porosidades-cabello/` | Pública | `gestion.manage_configuration` |
| CueroCabelludo | `/api/gestion/cueros-cabelludos/` | Pública | `gestion.manage_configuration` |
| EstadoGeneral | `/api/gestion/estados-generales/` | Pública | `gestion.manage_configuration` |
| CategoriaServicio | `/api/gestion/categorias-servicio/` | Pública | `gestion.manage_configuration` |
| TipoEquipamiento | `/api/gestion/tipo-equipamiento/` | Autenticada | `gestion.manage_configuration` |
| Equipamiento | `/api/gestion/equipamiento/` | Autenticada | `gestion.manage_configuration` |
| Opciones de equipamiento | `/api/gestion/equipamiento/opciones/` | Autenticada | No aplica (`GET`) |

`POST`, `PUT`, `PATCH` y `DELETE` requieren simultáneamente una sesión
autenticada, una cuenta activa y el permiso Django efectivo. No se concede
autoridad por `is_staff` ni por el nombre del BusinessRole.

## Permiso elegido

Se reutiliza `gestion.manage_configuration` porque:

1. ya existe en el dominio y representa la administración de parámetros y
   catálogos;
2. el rol ADMINISTRADOR lo recibe en la matriz de permisos existente;
3. la pantalla frontend `/admin/configuracion` ya exige ese permiso;
4. evita introducir un permiso nuevo o inferir autoridad por rol nominal.

La clase `CanManageConfiguration` aplica `user.has_perm()` y rechaza cuentas
inactivas. Los ViewSets separan permisos de lectura y escritura mediante
mixins comunes.

## Política de borrado e integridad

- Los cinco catálogos capilares y `CategoriaServicio` usan baja lógica
  (`activo=False`). Así se preservan diagnósticos, reglas, servicios y turnos
  históricos.
- `Equipamiento` conserva su baja lógica (`is_active=False`) y no rompe la
  referencia histórica de turnos.
- `TipoEquipamiento` sin referencias se puede eliminar físicamente.
- `TipoEquipamiento` referenciado por equipos o requisitos de servicios no se
  elimina y responde `409` con el código `EQUIPMENT_TYPE_IN_USE`.

La acción `equipamiento/opciones` sigue siendo de lectura autenticada. Durante
la prueba se detectó que referenciaba el atributo inexistente
`Equipamiento.TipoRecurso`; ahora obtiene los tipos persistidos desde
`TipoEquipamiento`.

## Matriz automatizada

La suite
`bohemiacore/gestion/tests/test_catalog_equipment_permissions_bh060_1.py`
recorre los ocho recursos y valida código HTTP y estado persistido.

| Actor / condición | GET público de catálogos | GET equipamiento | POST/PUT/PATCH/DELETE |
| --- | --- | --- | --- |
| Anónimo | Permitido | `401` | `401`, sin mutación |
| CLIENTE | Permitido | Permitido | `403`, sin mutación |
| EMPLEADO sin permiso | Permitido | Permitido | `403`, sin mutación |
| PROFESIONAL sin permiso | Permitido | Permitido | `403`, sin mutación |
| ADMINISTRADOR con permiso efectivo | Permitido | Permitido | Permitido |
| `is_staff=True` sin permiso | Permitido | Permitido | `403`, sin mutación |
| No-staff con permiso individual | Permitido | Permitido | Permitido |
| Cuenta inactiva con permiso asignado | Permitido como lectura pública | No habilita escritura | `403`, sin mutación |

También se comprueban:

- payloads con campos de escalamiento (`is_staff`, `is_superuser` y
  `user_permissions`) enviados por actores no autorizados;
- ausencia de altas, cambios, bajas lógicas o borrados ante denegación;
- los cuatro verbos de escritura para cada recurso;
- persistencia de diagnósticos, reglas, servicios y turnos tras bajas lógicas;
- conflicto y no mutación al eliminar tipos de equipamiento referenciados;
- preservación de turnos al dar de baja equipamiento.

## Compatibilidad frontend

- `ConfiguracionAdmin` ya consume los catálogos y tipos de equipamiento bajo
  una ruta protegida por `gestion.manage_configuration`.
- `/admin/equipamiento` ahora exige el mismo permiso efectivo antes de montar
  `GestionEquipamiento`.
- Las lecturas públicas usadas por registro y edición de perfil se conservan.
- Las lecturas autenticadas usadas para equipamiento y sus tipos se conservan.
- No se cambian URLs ni formatos de serializers. `opciones.tipos` mantiene
  objetos `{id, label}`, ahora respaldados por datos reales.

## Resultados de validación

Entorno confirmado: `django.db.backends.postgresql` (`connection.vendor =
postgresql`).

| Validación | Resultado |
| --- | --- |
| Suite focalizada BH-060.1 | **9/9 OK**; matriz completa por subtests |
| Roles, sesión, servicios/precios, turnos, skills, slot holds y blockers técnicos | **121/121 OK** |
| Diagnóstico (`test_diagnosis_authorization_api`) | **25/26 OK**; único fallo legacy conocido, ajeno al diff |
| `manage.py check` | **OK**, 0 issues |
| `makemigrations --check --dry-run` | **OK**, sin cambios |
| `ProtectedRoute.test.js` | **34/34 OK** |
| Build frontend normal | **OK**, compila con warnings preexistentes |
| `git diff --check` | **OK** |

El fallo legacy es
`test_legacy_flags_are_read_only_in_personal_serializer`: espera que el
serializer acepte `realiza_color`, `realiza_diagnostico` y `realiza_lavado`,
pero el contrato seguro vigente los rechaza como campos no permitidos. Este
incremento no modifica ese serializer ni su test.

El build con `CI=true` convierte en error warnings ESLint ya existentes en
archivos de contenido, rutinas, agenda y notificaciones no modificados por
BH-060.1. El build normal finaliza correctamente. No se alteraron esos archivos
para obtener un verde artificial.

## Riesgos pendientes

- `TipoEquipamiento` no tiene campo de activación; por eso sólo se borra cuando
  no posee referencias. Incorporar una baja lógica requeriría una decisión de
  producto y una migración fuera de este incremento.
- Los warnings ESLint globales y el test legacy de flags de Personal siguen
  como deuda previa del repositorio.
- El backend es la autoridad final. La protección de ruta frontend mejora la
  experiencia, pero no sustituye `has_perm()` en la API.
