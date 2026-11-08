# BH-060 Incremento 4 — Configuración y reportes

Fecha de validación: 2026-11-06
Baseline: `e3f5e9b0b6181f18ee12ed79a79a01519e73b73e`

## Alcance

Se reemplazaron decisiones de autorización basadas en `IsAdminUser`/`is_staff`
por permisos Django efectivos en las superficies activas de configuración,
dashboard operativo y reportes generales. No se modificaron `Pago`,
`PaymentIntent`, refunds, conciliación ni lógica del Incremento 5.

## Matriz de autoridad

| Endpoint | Operación | Autoridad efectiva | Proyección |
|---|---|---|---|
| `/api/gestion/configuracion/publica/` | `GET` | Pública | Sólo `empresa_nombre`; no crea el singleton |
| `/api/gestion/configuracion/` | `GET`, `POST` | `gestion.manage_configuration` | Configuración administrativa completa |
| `/api/gestion/configuracion/{id}/` | `GET`, `PUT`, `PATCH`, `DELETE` | `gestion.manage_configuration` | Configuración administrativa completa |
| `/api/gestion/configuracion/comprobante/` | `GET` | `gestion.view_financial_reports` | Nombre y datos fiscales mínimos para comprobantes |
| `/api/gestion/configuracion-diagnostico/` y detalle | Todas | `gestion.manage_configuration` | Configuración del motor de diagnóstico |
| `/api/gestion/reglas-diagnostico/` y detalle | Todas | `gestion.manage_configuration` | Reglas expertas de diagnóstico |
| `/api/gestion/admin-dashboard/stats/` | `GET` | `gestion.view_reports` | Operación y agenda, sin cifras financieras |
| `/api/gestion/stats/` | `GET` | `view_reports` o `view_financial_reports` | Proyección independiente según permisos efectivos |

Las operaciones no indicadas en las acciones públicas conservan el control del
ViewSet. Un `is_staff=True` sin permiso efectivo no obtiene autoridad y un
usuario `is_staff=False` con grant individual o de grupo sí puede operar.

## Contratos anteriores y nuevos

### Configuración

- Antes, los ViewSets administrativos dependían de `IsAdminUser`.
- Ahora, configuración general, configuración diagnóstica y reglas de
  diagnóstico requieren `gestion.manage_configuration` para lectura y
  escritura.
- La lectura pública conserva el contrato mínimo `empresa_nombre`, pero deja de
  mutar la base de datos mediante creación implícita del singleton.
- Se agregó `configuracion/comprobante/` para que el historial financiero no
  necesite leer la configuración administrativa completa.

### Dashboard operativo

- `/admin-dashboard/stats/` requiere `gestion.view_reports`.
- Mantiene contadores y próximos turnos; no incorpora ingresos, montos ni email
  del Cliente.

### Reportes combinados

`/stats/` conserva un único endpoint por compatibilidad, pero la respuesta se
construye por capacidad:

| Permisos | Campos disponibles |
|---|---|
| Sólo `view_reports` | `rango`, `productos`, `rutinas`, `ordenes_count`, `cliente_mes` |
| Sólo `view_financial_reports` | `rango`, `servicios`, `total_ingresos` |
| Ambos | Unión de ambas proyecciones, compatible con el contrato combinado anterior |

`cliente_mes` no expone email. Cuando no existe nombre visible utiliza un
identificador genérico. El permiso general no revela montos y el permiso
financiero aislado no revela identidad, tendencias generales ni cantidad de
órdenes.

## Compatibilidad frontend

- Navegación, guards de rutas y accesos rápidos consumen las capacidades
  efectivas publicadas por `/me/`.
- Dashboard requiere `gestion.view_reports`.
- Reportes admite cualquiera de `view_reports` o `view_financial_reports` y
  renderiza/exporta sólo la proyección autorizada.
- Configuración y reglas requieren `gestion.manage_configuration`.
- `HistorialPagos` consume la nueva proyección fiscal mínima protegida por
  `gestion.view_financial_reports`.
- No se usa `is_staff` ni el nombre de `BusinessRole` como autoridad de negocio.
- No se realizó rediseño visual.

## Pruebas positivas y negativas

Suite PostgreSQL nueva:
`gestion.tests.test_configuration_reports_permissions_bh060_4`

- **15/15 OK**.
- Cubre CLIENTE, EMPLEADO, PROFESIONAL, ADMINISTRADOR, anónimo, cuenta
  inactiva, staff sin permiso y no-staff con permiso.
- Cubre grants individuales y grants del grupo técnico ADMINISTRADOR.
- Cubre permisos general, financiero y configuración de forma aislada y
  combinada.
- Cubre `POST`, `PATCH`, `DELETE`, acciones personalizadas y rutas alternativas.
- Verifica privacidad de campos y cero mutaciones ante `401`/`403`.

Regresiones ejecutadas:

- Roles, sesión, capacidades previas, configuración, agenda y pagos:
  **90/90 OK**.
- Diagnóstico/autorización: **25/26 conformes**. El único fallo es la
  expectativa legacy conocida
  `test_legacy_flags_are_read_only_in_personal_serializer`, que espera aceptar
  silenciosamente tres flags técnicos. `PersonalSerializer` mantiene el rechazo
  seguro `Este campo no está permitido.` y no fue debilitado.
- Frontend relevante: **83/83 OK**.
- `manage.py check`: OK.
- `manage.py makemigrations --check --dry-run`: sin cambios.
- `npm run build`: compilación correcta con advertencias preexistentes fuera del
  alcance.
- `git diff --check`: OK.

## Rutas alternativas revisadas

- La ruta activa de `/stats/` importa
  `bohemiacore/gestion/stats_views.py` desde `gestion/urls.py`.
- `bohemiacore/gestion/views/stats_views.py` es un duplicado legacy sin
  importaciones ni rutas activas; se preservó sin cambios.
- No se encontraron otros consumidores activos de los contratos modificados.

## Riesgos residuales

- El duplicado legacy de stats conserva código basado en `IsAdminUser`, pero no
  está conectado al URLConf. Si se reutiliza en el futuro deberá eliminarse o
  migrarse antes de exponerlo.
- El endpoint combinado mantiene nombres legacy (`servicios` representa el
  agregado monetario por producto) para evitar romper consumidores existentes.
- Las advertencias del build corresponden a archivos no modificados y no
  bloquean la compilación.
- La expectativa legacy de `PersonalSerializer` permanece pendiente fuera de
  este incremento.
