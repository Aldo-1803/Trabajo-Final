# Corrección de zona horaria comercial de Posadas

**Fecha:** 2026-11-10

**Baseline:** `628ac4d2423e7db7977192ff618ba843b959277f`

## 1. Corrección de configuración

Bohemia Hair opera en Posadas, Misiones. La configuración anterior era:

```python
TIME_ZONE = 'America/Bogota'
USE_TZ = True
```

La configuración versionada correcta es:

```python
TIME_ZONE = 'America/Argentina/Cordoba'
USE_TZ = True
```

`America/Argentina/Cordoba` representa UTC−03 para Posadas. Se mantuvo
`USE_TZ=True`; no se adoptó la zona del sistema operativo como autoridad.

También se alineó la variable `TZ` del runner CI con la zona comercial. Los
settings de tests importan los settings principales y no existe otro override
de `TIME_ZONE` en desarrollo o despliegue. ASGI, WSGI y `manage.py` cargan
`bohemiacore.settings`.

La modificación local del nombre de base de datos en `settings.py` no pertenece
a esta corrección y se preserva fuera del commit.

## 2. Evaluación de datos persistidos

La inspección de sólo lectura de PostgreSQL/Django confirmó:

- sesión PostgreSQL de Django en `UTC`;
- `CURRENT_TIMESTAMP` devuelto como datetime aware UTC;
- 137 columnas PostgreSQL de tipo `timestamp with time zone`;
- cero columnas `timestamp without time zone` en el esquema público;
- 136 `DateTimeField`, 25 `DateField` y 15 `TimeField` en los modelos cargados;
- cero datetimes naive entre las filas inspeccionadas;
- cero Turnos, SlotHolds y Bloqueos de Agenda en la base local inspeccionada.

Los `DateTimeField` representan instantes. El cambio de zona no modifica sus
valores UTC: sólo cambia su conversión local de UTC−05 a UTC−03. Una marca
histórica `2024-06-15T15:00:00Z`, por ejemplo, conserva exactamente ese instante
y se presenta como 12:00 en Posadas.

Los `DateField` y `TimeField` no reciben conversión de zona. Esto incluye la
fecha y hora civil de `Turno`, horarios laborales y fechas de promociones.

No se ejecutó ninguna conversión masiva, actualización de filas ni migración.

### Consideración para otros entornos

PostgreSQL no permite inferir si un instante histórico fue originado por un
cliente con offset explícito o por un datetime naive. La base inspeccionada no
contiene bloqueos de agenda que requieran revisión. Antes de desplegar sobre una
base distinta, corresponde inventariar bloqueos futuros ingresados antes de
esta corrección; no deben desplazarse automáticamente sin confirmar su hora
civil original.

## 3. Contrato UTC/local

La frontera determinista principal es:

- UTC: `2026-11-11 02:30:00+00:00`;
- Posadas: `2026-11-10 23:30:00-03:00`;
- fecha comercial: `2026-11-10`.

Las decisiones basadas en día civil usan explícitamente:

```python
timezone.localdate(timezone=timezone.get_default_timezone())
```

Cuando ya existe un instante `ahora`, se convierte mediante la misma zona por
defecto. `timezone.now()` continúa utilizándose para comparar instantes,
expiraciones, auditoría y timestamps técnicos.

## 4. Procesos revisados

### Turnos, disponibilidad y recomendaciones

- la fecha comercial de recomendaciones y disponibilidad resuelve ahora a
  Posadas por configuración;
- creación, disponibilidad canónica, horario laboral y bloqueos se probaron en
  frontera UTC/local;
- `Turno.fecha` y `Turno.hora_inicio` permanecen como fecha/hora civiles, sin
  reinterpretación de almacenamiento.

### Procesos programados

- `recordatorios_pendientes` usa la fecha de Posadas y consulta el campo real
  `Notificacion.fecha_envio`;
- `procesar_promos` procesa la fecha comercial de Posadas;
- `limpiar_turnos` compara `DateField`/`TimeField` contra fecha y hora locales,
  evitando cancelar a las 23:30 un turno de las 23:45;
- expiraciones de seña siguen comparándose como instantes aware.

### Promociones y reportes

- creación, vigencia y escaneo de promociones usan fecha comercial;
- dashboard y mes por defecto de reportes usan Posadas;
- consultas históricas por datetime mantienen instantes UTC.

### Frontend

La presentación de `starts_at` y `expires_at` del flujo de reserva/pago usa
`Intl.DateTimeFormat` con `timeZone: 'America/Argentina/Cordoba'`. Ya no depende
de la zona del navegador para mostrar el HOLD y su vencimiento.

Otros componentes legacy que muestran timestamps con la zona del navegador no
se cambiaron de forma masiva; deben migrarse al formateador comercial cuando se
revise cada contrato visual. No participan en el cálculo de disponibilidad ni
en la creación del Turno.

## 5. Pruebas deterministas

Se agregaron o actualizaron casos para:

1. configuración `America/Argentina/Cordoba` con `USE_TZ=True`;
2. conversión `2026-11-11 02:30 UTC` a `2026-11-10 23:30` en Posadas;
3. persistencia y recuperación del mismo instante UTC histórico;
4. creación de Turno cerca de medianoche UTC;
5. recomendación del primer hueco y ausencia de salto semanal;
6. disponibilidad por defecto con fecha comercial distinta de UTC;
7. recordatorios pendientes;
8. procesamiento de promociones;
9. limpieza de Turnos sin cancelar un horario local futuro;
10. mes por defecto de reportes en una frontera UTC/local de fin de mes;
11. presentación frontend del HOLD y su vencimiento en Posadas.

Resultados confirmados hasta la regresión amplia:

- matriz backend temporal inicial: **75/75**;
- regresión backend de agenda, reservas, promociones y reportes: **241/241**;
- frontend focal: **11/11**, 2 suites;
- frontend completo: **293/293**, 35 suites;
- build frontend de producción: completado; conserva warnings legacy ajenos a
  esta corrección.

Matriz backend completa:

- **1.116/1.116** aprobadas;
- 97 módulos explícitos de `usuarios` y `gestion/tests`;
- 2.651,19 s totales;
- PostgreSQL real, ejecución secuencial y sin `--parallel`;
- cero fallos.

Validaciones adicionales:

- Django check: sin issues;
- `makemigrations --check --dry-run`: sin cambios;
- `migrate --check`: sin migraciones pendientes;
- `git diff --check`: sin errores de whitespace;
- enlaces locales del índice: cero rotos.

## 6. Riesgos residuales

- una base externa con bloqueos futuros creados como datetimes naive bajo la
  configuración anterior requiere revisión operativa previa al despliegue;
- vistas frontend legacy aún pueden presentar timestamps según la zona del
  navegador, aunque los flujos temporales críticos cubiertos aquí son
  explícitos;
- no se realizaron smoke tests sobre el entorno desplegado.

Las auditorías históricas y sus cifras no fueron modificadas.

`ZONA HORARIA POSADAS — IMPLEMENTADA Y VALIDADA`
