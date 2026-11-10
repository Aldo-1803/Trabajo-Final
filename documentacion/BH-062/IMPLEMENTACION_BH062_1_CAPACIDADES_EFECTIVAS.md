# BH-062 — Incremento 1: capacidades efectivas de sesión

**Fecha:** 2026-11-10

**Baseline:** `e57e9e3fba558c07432404ddf7d6632ec980a06d`

**Rama:** `save/work-in-progress`

## 1. Objetivo y alcance

`GET /api/usuarios/me/` conserva su contrato anterior y agrega una proyección
booleana `capabilities`. Cada valor representa que el usuario satisface los
prerrequisitos globales vigentes de una operación compuesta en backend.

Este incremento no cambia rutas, navegación, landing ni formularios. Tampoco
convierte una capability en autoridad frontend: DRF, servicios, querysets,
ownership y estados de dominio continúan tomando la decisión final en cada
petición.

## 2. Contrato final

La respuesta mantiene:

- `user`;
- `business_role`;
- `permissions`;
- `profiles`.

Y agrega exactamente:

```json
{
  "capabilities": {
    "technical_booking.review": false,
    "diagnosis.create": false,
    "technical_record.read_global": false,
    "technical_record.manage": false,
    "service_formula.manage": false,
    "content.author": false,
    "content.manage_global": false
  }
}
```

En toda respuesta 200, los nombres están siempre presentes y todos los valores
son booleanos. No se publican orígenes de grants ni habilidades.

## 3. Fuente backend de cada booleano

Los predicados canónicos viven en `gestion/effective_access.py` y son usados
tanto por `/me/` como por permisos DRF, serializers o servicios productivos.

| Capability | Condiciones globales obligatorias | Consumidor backend compartido |
|---|---|---|
| `technical_booking.review` | Usuario activo + permiso efectivo `gestion.review_technical_booking` + Personal activo con asignación y habilidad canónica `DIAGNOSTICO` activas. | `CanReviewTechnicalBooking` y `reviewer_personal()`. |
| `diagnosis.create` | Usuario activo + `gestion.create_diagnosis` + `DIAGNOSTICO` efectiva. | `CanCreateDiagnosisWithSkill`. |
| `technical_record.read_global` | Usuario activo + `gestion.manage_technical_record` + `DIAGNOSTICO` efectiva. | Permisos de lectura técnica global y queryset de diagnósticos. |
| `technical_record.manage` | Usuario activo + `gestion.manage_technical_record` + `DIAGNOSTICO` efectiva. | `CanManageTechnicalRecordWithSkill`. |
| `service_formula.manage` | Usuario activo + `gestion.manage_formulas` + `DIAGNOSTICO` efectiva. | `CanManagePricesOrFormulas`, serializers y queryset de Servicios. |
| `content.author` | Usuario activo con relación Personal activa. | Creación y ownership de contenido de BH-062.0. |
| `content.manage_global` | Usuario activo + permiso efectivo `gestion.manage_content`. | Queryset y mutaciones globales de contenido de BH-062.0. |

`user_has_active_skill()` comprueba con datos persistidos que estén activos el
usuario, Personal, la habilidad canónica y su asignación. No se infiere nada de
`BusinessRole`, `is_staff`, `Personal.rol` ni flags legacy.

Los permisos efectivos conservan la semántica Django: pueden proceder del
BusinessRole, de un grupo técnico o de un permiso individual. La respuesta no
revela cuál fue el origen.

## 4. Capability global frente a autorización por objeto

Una capability verdadera no promete que cualquier objeto o transición sea
válida:

- `technical_booking.review` habilita el prerrequisito general; cada solicitud
  aún exige estado permitido y compatibilidad del Personal con los servicios;
- `diagnosis.create` no reemplaza validaciones de payload, Cliente, estado ni
  reglas técnicas;
- `technical_record.read_global` expresa la condición técnica global, pero los
  endpoints de fichas conservan sus querysets y ownership actuales;
- `technical_record.manage` tampoco elimina la asignación al Turno ni las
  validaciones del serializer;
- `service_formula.manage` se limita a fórmulas y no concede gestión de precios
  ni de otros campos del Servicio;
- `content.author` permite crear y gestionar contenido propio, no contenido de
  otro autor;
- `content.manage_global` permite gestionar contenido activo globalmente, pero
  no permite crear si falta un Personal activo que pueda quedar como autor.

La lectura propia de Clientes en diagnósticos o fichas no se representa como
capability global: depende del perfil y del ownership del objeto.

## 5. Endpoint y seguridad del contrato

`CurrentSessionSerializer` agrega sólo el mapa booleano. `CurrentSessionView`
continúa:

- autenticando exclusivamente con JWT;
- fallando cerrado con 409 ante múltiples BusinessRole;
- seleccionando únicamente los perfiles propios;
- limitando `permissions` al catálogo de negocio existente.

Además, toda respuesta de `/api/usuarios/me/` lleva `Cache-Control: no-store`
mediante `never_cache`.

No se exponen:

- `is_staff` ni `is_superuser`;
- grupos o grants individuales;
- listado de habilidades;
- fuentes de permisos;
- datos de terceros;
- información administrativa o de auditoría.

No se agregaron permisos Django, BusinessRole ni migraciones.

## 6. Consumo en SessionContext

`SessionContext` incorpora:

- `capabilities` en el estado y valor público;
- `hasCapability(name)`;
- `hasAnyCapability(names)`.

El consumo falla cerrado:

- campo ausente, `null`, array u otro tipo inválido: `{}`;
- capability ausente: `false`;
- cualquier valor distinto del booleano estricto `true`: `false`;
- BusinessRole o permiso simple no se reinterpretan como capability;
- refresh exitoso reemplaza permisos y capabilities en una sola sesión nueva;
- 401, logout, 409, error de autorización o red eliminan ambas proyecciones en
  memoria, evitando conservar autoridad obsoleta.

Los helpers existentes de permisos, roles y perfiles no cambian. Payloads
anteriores sin `capabilities` siguen produciendo una sesión válida, pero todas
las capacidades compuestas quedan denegadas.

## 7. Pruebas y paridad

### 7.1 Backend PostgreSQL

`usuarios/test_current_session_capabilities_api.py` usa usuarios, permisos,
grupos, Personal, habilidades y asignaciones persistidas. Cubre:

- permiso técnico sin habilidad y habilidad sin permiso;
- habilidad o asignación inactiva;
- Personal inactivo;
- permisos heredados de BusinessRole;
- grant mediante grupo técnico y grant individual;
- `is_staff` sin autoridad de negocio;
- paridad con las clases DRF de revisión, diagnóstico, lectura y gestión
  técnica, y fórmulas;
- paridad con `reviewer_personal()`;
- autoría de contenido, gestión global y separación de ownership;
- gestor global sin autor válido;
- contrato booleano completo, compatibilidad y ausencia de filtraciones;
- `Cache-Control: no-store`, incluso en el error estable de múltiples roles.

La primera matriz focal de `/me/`, capabilities y BH-062.0 ejecutó **45 tests
OK**.

### 7.2 Frontend

`SessionContext.test.js` prueba almacenamiento, helpers exactos, ausencia del
campo, valores inválidos, refresh coherente, 401, logout, errores, BusinessRole
sin capability y permiso simple con capability falsa.

La matriz focal de `SessionContext`, Login y `ProtectedRoute` ejecutó **63 tests
OK**. No se cambiaron expectativas de rutas o botones.

## 8. Regresiones

La matriz backend relacionada ejecutó **180 tests OK** y cubrió:

- `/me/`, roles y permisos efectivos BH-059/BH-060;
- revisión técnica y habilidades;
- diagnósticos, fichas técnicas y fórmulas;
- contención de contenido BH-062.0;
- permisos heredados, técnicos e individuales de BH-059/BH-060.

La suite frontend completa ejecutó **35 suites y 301 tests OK**, incluidos
`SessionContext`, Login, `ProtectedRoute` y todos los consumidores actuales.

Validaciones adicionales:

- `python manage.py check --settings=bohemiacore.test_settings`: **OK**;
- `makemigrations --check --dry-run`: **sin cambios**;
- `npm run build`: **compiló correctamente**.

El build y suites existentes conservan advertencias legacy de ESLint,
paginación y `act(...)`; no corresponden al contrato agregado y no causaron
fallos.

## 9. Riesgos residuales

1. **Incremento 2 todavía pendiente.** Rutas, landing y navegación aún usan sus
   condiciones anteriores. Ninguna consume estas capabilities en este cambio.
2. **Autorización contextual.** Ownership, estado, compatibilidad de servicios y
   validaciones de payload sólo pueden resolverse al operar un objeto. No deben
   proyectarse como autorización universal a partir de estos booleanos.
3. **Acciones y formularios.** La visibilidad por acción corresponde al
   Incremento 3; una capability global no reemplaza los estados de dominio.
4. **Revocación durante sesión abierta.** No hay polling ni refresh por foco.
   El backend aplica el estado vigente en cada petición; la sincronización
   dinámica corresponde al Incremento 4.
5. **Evolución del catálogo.** Agregar o cambiar una capability exige mantener
   juntos su predicado canónico, consumidor backend, contrato y pruebas de
   paridad.

## 10. Veredicto

El backend publica una proyección mínima, booleana y derivada de la misma
autoridad que protege las operaciones reales. El frontend puede consumirla sin
inferir permisos ni ampliar autoridad.

`BH-062 INCREMENTO 1 = VALIDADO`
