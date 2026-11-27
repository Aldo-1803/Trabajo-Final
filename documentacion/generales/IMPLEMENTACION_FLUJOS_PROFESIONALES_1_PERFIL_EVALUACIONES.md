# Flujos profesionales — Incremento 1: perfil y evaluaciones trazables

**Fecha:** 2026-11-11

**Baseline de partida:** `7de385f818b9c4c54f3d7d0fc892b729e8d7b3e9`

**Rama:** `save/work-in-progress`

**Estado:** validado para publicación

## 1. Objetivo y alcance

Este incremento unifica el perfil capilar vigente de `Cliente` con nuevas
evaluaciones y correcciones trazables, sin convertir el perfil mutable en el
historial ni sobrescribir observaciones anteriores.

Incluye:

- procedencia vigente por cada uno de los cinco campos capilares;
- creación semántica de una evaluación profesional;
- corrección explícita con motivo, actor y valores antes/después;
- autorreportes trazables desde registro y edición del perfil;
- registro separado de impactos automáticos post-servicio;
- separación entre texto original y resultado calculado;
- contrato coherente de IDs y nombres en `GET /api/usuarios/perfil/`;
- locks PostgreSQL, atomicidad y pruebas de concurrencia.

No incluye seguimiento periódico, algoritmo de evolución, fichas técnicas del
Incremento 2, consolidación de automatizaciones, UI profesional completa,
BH-063, BH-064, cambios financieros ni cambios de stock.

## 2. Escritores identificados y controlados

La inspección encontró cuatro escritores del perfil capilar:

1. registro público;
2. `PUT /api/usuarios/perfil/`;
3. creación de `DiagnosticoCapilar` profesional;
4. impacto explícito de un único Servicio durante la finalización del
   Incremento 0.

Los cuatro pasan ahora por `gestion/hair_profile_services.py`. El servicio
bloquea el `Cliente` con `select_for_update()`, aplica sólo campos explícitos y
registra el evento y la vigencia dentro de la misma transacción.

## 3. Modelo conceptual implementado

### 3.1 Evaluación histórica

`DiagnosticoCapilar` continúa siendo la observación histórica y agrega:

- `autor`: usuario que registró el dato, sin atribuirle necesariamente autoría
  profesional;
- `campos_evaluados`: lista de dimensiones informadas explícitamente;
- `resultado_calculado` y su estado/fechas de cálculo o invalidación;
- conservación de `observaciones` como texto original.

`profesional` conserva su significado previo. En un autorreporte queda nulo y
`autor` identifica al Cliente. En una evaluación profesional ambos señalan al
actor autorizado.

### 3.2 Ledger del perfil vigente

`CambioPerfilCapilar` es un evento inmutable que registra:

- Cliente y actor;
- operación y procedencia;
- motivo;
- campos sincronizados;
- valores anteriores y nuevos;
- diagnóstico fuente, cuando existe;
- fecha de creación.

`VigenciaCampoPerfilCapilar` mantiene una fila por `Cliente` y campo. La
constraint única `(cliente, campo)` permite explicar de manera independiente
la fuente vigente de tipo, grosor, porosidad, cuero cabelludo y estado general.

### 3.3 Corrección

`CorreccionDiagnosticoCapilar` es un evento inmutable separado. Guarda el
diagnóstico corregido, actor, motivo, campos, antes/después, fecha y el eventual
cambio del perfil vigente.

La corrección modifica la evaluación existente y queda además registrada por
`django-simple-history`; no crea una observación nueva ni cambia su fecha de
evaluación.

## 4. Procedencias

Se conservan sin equivalencias implícitas:

| Procedencia | Significado |
|---|---|
| `AUTORREPORTE` | Dato declarado por el Cliente en registro o perfil. |
| `PROFESIONAL` | Campo observado en una nueva evaluación profesional autorizada. |
| `POST_SERVICIO_AUTOMATICO` | Resultado de un impacto explícito configurado para un Servicio. |
| `MIGRADO` | Reservado para evidencia de migración comprobada. |
| `DESCONOCIDO` | Perfil o diagnóstico previo sin evidencia suficiente. |

No se ejecutó backfill. Los diagnósticos previos mantienen `autor`,
`campos_evaluados` y metadatos de resultado en `null`. Los valores de perfil
preexistentes se exponen como `DESCONOCIDO` hasta que una operación trazable
establezca su fuente. No se inventan autores, observaciones, motivos ni fechas.

La finalización no crea `DiagnosticoCapilar` y no presenta un efecto cosmético
como mejoría observada. Sólo registra `POST_SERVICIO_AUTOMATICO` para impactos
explícitos ya admitidos por la política del Incremento 0.

## 5. Evaluación nueva frente a corrección

### 5.1 Nueva evaluación

```text
POST /api/gestion/diagnosticos-capilares/
```

La operación:

1. exige `diagnosis.create`, cuenta activa, `Personal` activo y habilidad
   `DIAGNOSTICO` activa;
2. fija `autor`, `profesional` y `PROFESIONAL` en servidor;
3. crea un nuevo diagnóstico sin tocar los anteriores;
4. promueve sólo campos capilares no nulos realmente informados;
5. conserva los campos omitidos del perfil;
6. ejecuta el motor sólo si existe al menos un campo capilar evaluado.

Los campos de autoría y procedencia enviados por el consumidor no pueden
falsificar los valores fijados por servidor.

### 5.2 Corrección

```text
POST /api/gestion/diagnosticos-capilares/{id}/corregir/
```

Requiere un motivo de al menos diez caracteres y uno o más campos corregibles.
No permite agregar como corrección una dimensión que no formaba parte de la
evaluación original; eso requeriría una nueva evaluación. Para registros legacy
sin `campos_evaluados`, sólo admite corregir una dimensión que ya tenía valor.
Puede ejecutarla el autor profesional de la evaluación o un actor con alcance
global `manage_technical_record`, siempre que también conserve la capacidad
efectiva de crear diagnóstico. Un actor sin ownership recibe 404 para no
exponer el objeto.

Si el diagnóstico corregido continúa siendo la fuente vigente de un campo, el
perfil se corrige en la misma transacción. Si un autorreporte u otra evaluación
posterior ya reemplazó esa fuente, se corrige sólo la historia y no se pisa el
perfil más nuevo.

`PUT` y `PATCH` genéricos de diagnósticos responden 405. La eliminación física
continúa deshabilitada.

## 6. Política de sincronización

- No existe una jerarquía absoluta entre fuentes.
- Cada operación explícita establece vigencia sólo en los campos informados.
- Una actualización parcial nunca borra campos omitidos.
- Un autorreporte sólo crea diagnóstico y ledger si cambia al menos un valor
  capilar; cambios personales solos no crean historia capilar ficticia.
- Una nueva evaluación profesional puede establecer una fuente aun cuando el
  valor observado coincida con el vigente, porque existe nueva evidencia.
- Una corrección sólo actualiza campos cuyo diagnóstico corregido sigue siendo
  fuente vigente.
- Un impacto automático conserva su procedencia y no recibe autoría
  profesional.

El lock del `Cliente` serializa escritores concurrentes. Las pruebas con dos
conexiones PostgreSQL demuestran que dos evaluaciones parciales simultáneas en
campos diferentes conservan ambas actualizaciones.

## 7. Motor, recomendaciones y efectos derivados

El motor ya no reemplaza `observaciones`. Guarda el mensaje generado en
`resultado_calculado`, junto con estado y fecha. `mensaje_diagnostico` mantiene
compatibilidad: devuelve primero el resultado separado y, para registros
legacy, usa `observaciones` como fallback.

Una corrección de campo capilar:

- invalida el resultado calculado;
- limpia referencias derivadas del diagnóstico a regla, rutina, Servicio y
  Turno sugeridos;
- registra fecha y motivo de invalidación;
- no recalcula automáticamente;
- no crea rutinas, Turnos sugeridos ni notificaciones adicionales.

El recálculo con efectos se difiere porque todavía requiere una política
funcional para impedir duplicados y decidir cómo reemplazar recomendaciones ya
consumidas.

## 8. Perfil del Cliente y React

`GET /api/usuarios/perfil/` conserva los nombres legacy y agrega:

- `tipo_cabello_id`;
- `grosor_cabello_id`;
- `porosidad_cabello_id`;
- `cuero_cabelludo_id`;
- `estado_general_id`;
- `perfil_capilar`, con `id`, `nombre`, `procedencia`, diagnóstico fuente y
  fecha por campo.

`EditarPerfil.js` carga los selects con esos IDs, admite catálogos paginados o
listas directas y continúa enviando los aliases `porosidad` y `grosor` que el
backend normaliza sin mutar `request.data`.

Los cinco datos capilares siguen siendo opcionales en registro y perfil. Esto
preserva la posibilidad futura de crear Clientes presenciales sin diagnóstico,
sin implementar BH-064.

## 9. Autorización y ownership

Se conserva el modelo de permisos efectivos BH-062:

- crear y corregir exige `gestion.create_diagnosis`, `Personal` activo y
  `DIAGNOSTICO` activa;
- el Cliente sólo lee y modifica su perfil y lee sus diagnósticos;
- lectura técnica global requiere `manage_technical_record` y habilidad activa;
- un creador sin gestión global sólo corrige sus propias evaluaciones;
- no existe bypass por BusinessRole nominal ni por `is_staff`;
- actor, autor y procedencia se fijan en servidor.

No se publicó una pantalla profesional nueva.

## 10. Migración

`gestion/migrations/0042_hair_profile_evaluations_increment1.py`:

- agrega campos nullable a diagnóstico e histórico;
- crea los tres modelos de trazabilidad;
- agrega la constraint de vigencia única por campo;
- no incluye `RunPython` ni backfill;
- no modifica valores capilares existentes;
- es reversible mediante las operaciones de esquema generadas por Django.

`check`, `makemigrations --check --dry-run`, `sqlmigrate 0042`, compilación
Python y parseo del workflow YAML finalizaron correctamente.

## 11. Pruebas y regresiones

### 11.1 Cobertura focal nueva

`gestion/tests/test_hair_profile_evaluations_increment1.py` agrega 18 pruebas:

- perfiles completo, parcial y sin diagnóstico;
- evaluación profesional e historia preservada;
- autorreporte parcial sin pérdida;
- corrección con motivo, ownership y habilidad efectiva;
- autor/procedencia no falsificables;
- IDs y nombres coherentes;
- texto profesional y resultado calculado separados;
- invalidación sin duplicar efectos;
- rollback de sincronización;
- concurrencia PostgreSQL real;
- compatibilidad con finalización;
- registros históricos sin metadata ficticia.

`EditarPerfil.test.js` agrega dos pruebas de carga y envío de IDs.

### 11.2 Resultados ejecutados

| Suite | Resultado |
|---|---:|
| Focal backend ampliada | 91/91 |
| B1 — roles, usuarios y Personal | 416/416 |
| B2 — diagnóstico, ficha y rutinas | 187/187 |
| B3 — agenda, Turnos y CU-27 | 176/176 |
| B4 — catálogos, inventario y órdenes | 79/79 |
| B5 — Caja, pagos e incidencias | 170/170 |
| B6 — Django Admin y auditoría | 43/43 |
| B7 — concurrencia PostgreSQL | 68/68 |
| Frontend completo | 43 suites, 399/399 |
| Build React | exitoso con warnings preexistentes |

La matriz B1–B7 enumera **1.139 pruebas backend únicas**; sus labels no se
solapan. La suite focal de 91 pruebas y la prueba aislada usada para diagnosticar
B1 son repeticiones intencionales y no se suman al total único. El frontend
ejecutó 399 pruebas únicas en una única corrida completa.

No se ejecutaron navegadores Cypress/E2E ni pruebas contra servicios externos
reales. Esas carpetas locales son trabajo ajeno y no forman parte del
Incremento 1.

## 12. Riesgos y decisiones pendientes

1. Los perfiles preexistentes muestran fuente `DESCONOCIDO`; sólo una migración
   futura basada en evidencia podría reclasificarlos.
2. No existe todavía una política aprobada para recalcular tras corrección sin
   duplicar o reemplazar efectos ya consumidos.
3. No se definió precedencia permanente entre autorreporte y observación
   profesional; la vigencia se decide por campo y operación explícita bajo
   lock.
4. El ledger explica cambios nuevos, pero no reconstruye retrospectivamente
   escritores anteriores al incremento.
5. La UI profesional de evaluación/corrección permanece fuera de alcance.

## 13. Publicación

El cambio se publica en `save/work-in-progress` con el mensaje:

```text
feat(hair): trazar evaluaciones y cambios del perfil capilar
```

No se inicia el Incremento 2.
