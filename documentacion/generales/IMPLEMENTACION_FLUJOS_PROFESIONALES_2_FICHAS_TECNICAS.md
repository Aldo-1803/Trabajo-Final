# Flujos profesionales — Incremento 2: fichas técnicas trazables

**Fecha:** 2026-11-17

**Baseline de partida:** `cf7d49a53c7fa0727d3ed0843897c38310cccba6`

**Rama:** `save/work-in-progress`

**Estado:** validado para publicación

## 1. Objetivo y alcance

Este incremento implementa el ciclo backend de una `FichaTecnica` por cada
`DetalleTurno`, con borrador, completitud verificable, correcciones auditadas y
control de concurrencia. Un Turno multiservicio conserva una ficha independiente
por cada detalle.

No publica la UI React profesional, no enruta los componentes legacy
`RegistroFichaTecnica.js` o `VisualizadorFichas.js`, no usa su cliente Axios y no
inicia los Incrementos 3 o 4. Tampoco consume stock, modifica finanzas, crea
diagnósticos ni sobrescribe el perfil capilar vigente.

## 2. Contraste de UC-17 y decisiones

UC-17 pide partir de una fórmula base, registrar fórmula final, comentarios,
fotografía y estado del cabello, y menciona una edición durante 24 horas. El
contrato previo sólo tenía campos opcionales y una plantilla de fórmula; no
declaraba por Servicio cuándo una ficha, fórmula, fotografía u otro campo era
obligatorio.

Se adoptaron estas decisiones seguras:

1. no se infiere un Servicio químico por nombre, categoría ni
   `es_quimico_agresivo`;
2. los requisitos se expresan exclusivamente en `PerfilTecnicoServicio`;
3. todos los Servicios existentes quedan con política `PENDIENTE`, sin backfill
   especulativo;
4. una política pendiente permite guardar borradores y conserva la semántica
   previa de finalización, pero nunca permite declarar una ficha `COMPLETA`;
5. la ventana posterior de 24 horas no se implementa porque faltan reglas de
   zona horaria, campos corregibles, excepción de supervisión y efectos ya
   ejecutados; después de finalizar se rechaza toda corrección con un conflicto
   explícito;
6. no se agregan productos utilizados: el modelo vigente de producto/stock no
   los relaciona con `FichaTecnica`, y crear esa relación excedería el contrato
   verificable.

## 3. Matriz de campos y políticas por Servicio

La matriz no clasifica nombres comerciales. Cada fila se determina por la
configuración explícita del perfil técnico del Servicio.

| Política explícita | Datos comunes | Fórmula aplicada | Campos condicionales | Fotografía | Completar | Finalizar Turno |
|---|---|---|---|---|---|---|
| `PENDIENTE` o perfil inexistente/inactivo | Todos opcionales en borrador | No se presume aplicabilidad | Ninguno inferido | No se exige | No permitido | Conserva comportamiento previo |
| `NO_REQUERIDA` + `NO_APLICA` | Opcionales | Debe permanecer vacía | No admite campos obligatorios | Opcional | Posible sólo con contenido real | Permitido sin ficha |
| `NO_REQUERIDA` + `OPCIONAL` | Opcionales | Opcional y protegida | No admite campos obligatorios | Opcional | Posible sólo con contenido real | Permitido sin ficha |
| `NO_REQUERIDA` + `REQUERIDA` | Opcionales | Obligatoria si se decide completar una ficha | No admite otros campos obligatorios | Opcional | Exige fórmula aplicada | Permitido sin ficha |
| `REQUERIDA` + `NO_APLICA` | Según lista configurada | Debe permanecer vacía | Al menos uno obligatorio | Sólo si se configura | Exige todos los campos configurados | Exige ficha completa |
| `REQUERIDA` + `OPCIONAL` | Según lista configurada | Opcional y protegida | Al menos uno obligatorio | Sólo si se configura | Exige todos los campos configurados | Exige ficha completa |
| `REQUERIDA` + `REQUERIDA` | Según lista configurada | Obligatoria y protegida | Lista adicional opcional | Sólo si se configura | Exige fórmula y lista configurada | Exige ficha completa |

Los campos configurables son:

- `observaciones_proceso`;
- `comentario_cliente`;
- `rutina_recomendada`;
- `porosidad_final`;
- `estado_general_final`;
- `resultado_post_servicio`;
- `foto_resultado`.

`formula` se configura exclusivamente mediante `modo_formula_ficha`; no se
duplica en la lista. Una ficha completa exige además al menos un dato técnico
real, para impedir registros vacíos aun cuando la configuración sea opcional.

## 4. Contrato de ficha y estados

`FichaTecnica.detalle_turno` continúa siendo `OneToOneField`; por tanto, la
unidad es una ficha por Servicio reservado, no una ficha por Turno.

El modelo agrega:

- `estado`: `BORRADOR` o `COMPLETA`;
- `version`: versión optimista iniciada en 1;
- `formula_estandar_referencia`: snapshot de catálogo al crear el borrador;
- `completada_por` y `completada_en`;
- `actualizada_en`;
- `HistoricalRecords`.

Los campos conservan significados separados:

| Campo | Significado |
|---|---|
| `formula_estandar_referencia` | Copia de la fórmula estándar al crear la ficha. |
| `formula` | Fórmula efectivamente aplicada. |
| `observaciones_proceso` | Procedimiento y observaciones de ejecución. |
| `resultado_post_servicio` | Resultado observado, sin afirmar mejoría automática. |
| `porosidad_final`, `estado_general_final` | Estado final informado en la ficha; no muta el perfil. |
| `foto_resultado` | Evidencia opcional u obligatoria sólo por configuración. |

Guardar o completar una ficha no modifica el estado del Turno. La finalización
continúa siendo una operación semántica separada.

## 5. API semántica y contexto técnico

Las mutaciones son:

```text
POST /api/gestion/fichas-tecnicas/
POST /api/gestion/fichas-tecnicas/{id}/guardar-borrador/
POST /api/gestion/fichas-tecnicas/{id}/completar/
POST /api/gestion/fichas-tecnicas/{id}/corregir/
```

Crear fija `profesional_autor` en servidor. Guardar, completar y corregir exigen
la `version` esperada. `PUT` y `PATCH` genéricos responden 405; `DELETE` también
permanece denegado.

El contrato mínimo autorizado es:

```text
GET /api/gestion/fichas-tecnicas/contexto-turno/?turno_id={id}
```

Devuelve detalles, Servicio, política, ficha, estado, versión, errores de
completitud y restricciones de edición. Sólo admite al Cliente propietario o al
Personal asignado con lectura técnica efectiva. No crea lectura global ni
amplía `technical_record.read_global`.

## 6. Completitud y finalización

La completitud se calcula exclusivamente en backend:

1. la política debe estar activa y totalmente definida;
2. deben existir todos los campos configurados;
3. `formula` debe existir si el modo es `REQUERIDA` y debe estar vacía si el
   modo es `NO_APLICA`;
4. la ficha no puede estar vacía.

`finalize_turno()` bloquea en orden Turno, detalles y fichas. Dentro de la misma
transacción:

- una política `REQUERIDA` rechaza finalizar si falta una ficha completa;
- `NO_REQUERIDA` permite finalizar sin ficha;
- `PENDIENTE` conserva la finalización anterior y registra esa condición en los
  efectos, sin afirmar que exista una ficha completa.

La validación sucede antes de cambiar el Turno o crear efectos. Se preservan
atomicidad, idempotencia, ownership y las garantías del Incremento 0.

## 7. Fórmulas y seguridad

Modificar o consultar fórmula estándar/aplicada requiere la capacidad efectiva
adicional `service_formula.manage`, que combina permiso, cuenta activa,
`Personal` activo y habilidad `DIAGNOSTICO` activa.

Gestionar la ficha requiere de igual modo `technical_record.manage`. Además, el
actor debe ser el Personal asignado al Turno. No existe bypass por BusinessRole
nominal ni `is_staff`.

Los serializers retiran `formula` y `formula_base_servicio` cuando falta la
capacidad de fórmula. Por ello, el Cliente puede leer su propia ficha y contexto
sin recibir datos sensibles. El autor y detalle no son campos mutables del
comando.

## 8. Correcciones, auditoría y concurrencia

Una ficha completa no acepta edición ordinaria. `corregir` exige:

- Turno aún `CONFIRMADO` o `EN_PROCESO`;
- actor asignado y capacidades efectivas;
- motivo de al menos diez caracteres;
- al menos un cambio real;
- conservación de la completitud;
- versión esperada vigente.

`CorreccionFichaTecnica` es un evento inmutable con autor original conservado en
la ficha, actor de corrección, motivo, fecha, campos, valores anteriores/nuevos y
versiones anterior/nueva. `HistoricalFichaTecnica` conserva además cada estado
persistido.

Las operaciones bloquean Turno, detalle y ficha con `select_for_update()` en un
orden común. Luego comparan la versión esperada. Un escritor obsoleto recibe
`409 TECHNICAL_RECORD_VERSION_CONFLICT`; nunca se acepta el último guardado de
forma silenciosa. Una prueba con dos conexiones PostgreSQL demuestra un único
ganador y un conflicto.

## 9. Migración

`gestion/migrations/0043_fichatecnica_actualizada_en_and_more.py`:

- agrega política explícita a `PerfilTecnicoServicio` con defaults pendientes;
- agrega estado, versión, snapshot, autor/fecha de completitud e historia a la
  ficha;
- protege la referencia al autor original;
- crea `CorreccionFichaTecnica` e `HistoricalFichaTecnica`;
- no incluye `RunPython`, no reclasifica Servicios y no marca fichas previas
  como completas.

Los registros de ficha existentes migran a `BORRADOR`, versión 1 y sin autor de
completitud. Es la única interpretación segura ante la ausencia de evidencia de
completitud histórica.

## 10. Pruebas y regresiones

`gestion/tests/test_technical_records_increment2.py` agrega 20 pruebas: 19 de
API/dominio y una carrera PostgreSQL. Cubren los 22 escenarios solicitados,
incluidos Turnos multiservicio, campos condicionales, fórmula estándar/aplicada,
autor impuesto, permisos y actividad efectiva, ocultamiento al Cliente,
correcciones, historia, versión 409, política posfinalización y relación atómica
con finalización.

La regresión BH-060 se adaptó para afirmar que `PUT/PATCH` genéricos responden
405; las capacidades y acciones semánticas mantienen pruebas propias.

| Suite | Resultado |
|---|---:|
| Focal: Incremento 2 + BH-060 + Incrementos 0 y 1 | 76/76 |
| Concurrencia PostgreSQL nueva | 1/1 |
| B1 — roles, usuarios y Personal | 416/416 |
| B2 — diagnóstico, ficha y rutinas | 206/206 |
| B3 — agenda, Turnos y CU-27 | 176/176 |
| B4 — catálogos, inventario y órdenes | 79/79 |
| B5 — Caja, pagos e incidencias | 170/170 |
| B6 — Django Admin y auditoría | 43/43 |
| B7 — concurrencia PostgreSQL | 69/69 |

El workflow incorpora las 19 pruebas API en B2 (`206` esperadas) y la prueba de
concurrencia en B7 (`69` esperadas). La matriz enumera ahora 1.159 pruebas
backend únicas.

La matriz B1–B7 ejecutó **1.159 pruebas backend únicas**. La corrida focal de
76 pruebas y la ejecución aislada de la carrera nueva son repeticiones
intencionales y no se suman al total. B3 se repitió completo porque el primer
comando manual transcribió incorrectamente un label; la repetición versionada
finalizó 176/176. No se ejecutó frontend porque este incremento no modifica
archivos React ni publica rutas.

## 11. Decisiones funcionales pendientes

1. clasificar cada Servicio real y aprobar sus campos/fotografía obligatorios;
2. definir la ventana de corrección posfinalización, zona horaria comercial,
   campos corregibles y excepción de supervisión sin recurrir a `is_staff`;
3. definir el tratamiento de efectos automáticos ya consumidos ante una futura
   corrección posterior;
4. decidir si el salón necesita registrar productos utilizados y, en tal caso,
   diseñar una relación sin consumir stock automáticamente;
5. publicar el recorrido React integrado recién en el Incremento 4.

## 12. Publicación

El cambio se publica en `save/work-in-progress` con el mensaje:

```text
feat(technical): completar ciclo trazable de fichas
```

No se inicia el Incremento 3.
