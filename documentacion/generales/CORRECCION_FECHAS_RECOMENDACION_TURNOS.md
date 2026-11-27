# Corrección de fechas en recomendaciones de Turnos

**Fecha:** 2026-11-10

**Baseline de inicio:**
`e396d5d6918d8a923899228fee0f1b64b550cabc`

**Alcance:** recomendación automática del primer Turno disponible y fecha por
defecto de la disponibilidad canónica. No se modificaron reglas comerciales,
roles, permisos, auditoría, pagos, stock, integraciones ni configuración.

## 1. Defecto original

La auditoría de cierre BH-061 registró un fallo intermitente en
`DiagnosisAuthorizationApiTests.test_diagnosis_recommendation_uses_canonical_availability_not_category_text`:
la fecha esperada podía desplazarse al mismo día de la semana siguiente cuando
la ejecución ocurría alrededor de medianoche.

`DiagnosticoCapilarViewSet._recomendar_primer_hueco_disponible()` iniciaba la
búsqueda con `date.today() + 1`. `date.today()` toma la fecha civil del sistema
operativo, mientras el resto del contrato de Turnos usa las utilidades timezone
de Django. La misma mezcla aparecía en la fecha por defecto y en las
comparaciones de `TurnoViewSet.consultar_disponibilidad()`, que usaban
`timezone.now().date()`: con `USE_TZ=True`, esa fecha es UTC.

Si UTC ya había avanzado al día siguiente pero la fecha comercial aún era la
anterior, la búsqueda empezaba un día tarde. Como `HorarioLaboral` es semanal,
la primera regla compatible podía encontrarse siete días después.

## 2. Causa raíz y zona horaria

La configuración vigente declara:

```python
TIME_ZONE = 'America/Bogota'
USE_TZ = True
```

No existe middleware ni otro código que active una zona horaria por solicitud.
La zona por defecto configurada representa, por tanto, la fecha comercial
vigente del salón. No se asumió la zona del sistema operativo ni se agregó una
zona fija nueva.

La causa raíz fue combinar tres conceptos distintos:

- fecha civil del sistema operativo (`date.today()`);
- fecha UTC de un datetime aware (`timezone.now().date()`);
- fecha local comercial de Django (`timezone.localdate()`).

Para impedir que una eventual zona activa de usuario cambie el calendario del
salón, la corrección obtiene explícitamente la zona por defecto configurada:

```python
timezone.localdate(timezone=timezone.get_default_timezone())
```

## 3. Reproducción determinista

Las pruebas fijan el reloj sin sleeps ni dependencias externas mediante
`unittest.mock`:

- instante UTC: `2030-01-02 02:30:00+00:00`;
- fecha UTC: 2030-01-02;
- hora local en `America/Bogota`: 2030-01-01 21:30;
- fecha comercial esperada: 2030-01-01.

Se fija también el reloj autoritativo de disponibilidad para que validaciones de
slots, holds y pasado/futuro utilicen el mismo instante. Las fechas 2030 hacen
que la prueba sea independiente del día y hora reales del runner.

### Evidencia antes de la corrección

- cinco pruebas focales de recomendación: **1 aprobada y 4 fallidas**; sólo el
  caso sin disponibilidad era correcto;
- disponibilidad canónica: **1 fallo de 1**; devolvió `2030-01-08` en lugar de
  `2030-01-01`, reproduciendo exactamente el salto semanal.

No se alteró el reloj real ni se usaron esperas.

## 4. Corrección aplicada

En `gestion/views.py`:

1. la recomendación inicia en el día siguiente a la fecha comercial configurada;
2. `consultar_disponibilidad()` calcula una sola vez `business_today` con esa
   misma fuente;
3. fecha por defecto, horizonte y comparaciones de pasado reutilizan
   `business_today`.

No cambiaron:

- duración, intervalo ni horizonte comercial;
- selección de Servicio o Personal;
- reglas recurrentes de `HorarioLaboral`;
- excepciones de `BloqueoAgenda`;
- validación de skills, equipamiento, Turnos o holds;
- persistencia de Turno/DetalleTurno/Notificación.

No fue necesaria ninguna migración.

## 5. Cobertura temporal agregada

Las pruebas deterministas cubren:

1. fecha UTC distinta de la fecha local comercial;
2. instante próximo a medianoche;
3. control en horario normal;
4. siguiente día de semana configurado;
5. ausencia de salto semanal indebido;
6. ausencia total de disponibilidad;
7. horario laboral y bloqueo de agenda, usando la recurrencia siguiente sólo
   cuando la primera está realmente bloqueada;
8. uso de `America/Bogota` desde `settings.TIME_ZONE`, incluso si existe otra
   zona activa en el contexto de la recomendación;
9. independencia de la fecha real de ejecución;
10. fecha por defecto del endpoint canónico durante la frontera UTC/local.

Después de la corrección, los seis casos focales aprobaron **6/6**.

## 6. Regresiones

Matriz focal PostgreSQL de diagnóstico, agenda, disponibilidad, bloqueos,
reservas, holds y booking técnico:

- **192/192** aprobadas;
- 10 módulos explícitos;
- 314,77 s totales;
- sin `--parallel` y con `StablePostgresTestRunner`.

Matriz backend completa por los 95 módulos `test*.py` de `usuarios` y
`gestion/tests`:

- **1.108/1.108** aprobadas;
- 2.619,64 s totales;
- PostgreSQL real, ejecución secuencial y sin `--parallel`;
- cero fallos, incluido el caso temporal que había fallado durante la auditoría
  de BH-061.

Las ejecuciones rojo/verde y las repeticiones focales no se suman como tests
únicos a la matriz completa.

Validaciones adicionales:

- Django check: sin issues;
- `makemigrations --check --dry-run`: sin cambios;
- `migrate --check`: sin migraciones pendientes;
- `git diff --check`: sin errores de whitespace.

## 7. Revisión acotada de usos similares

### Correctos en el contrato vigente

- disponibilidad pública y validaciones de solicitudes técnicas usan
  `timezone.localdate()`;
- el horizonte de `TurnoCreationService` usa fecha local Django;
- serializers de fechas de reserva comparan contra `timezone.localdate()`;
- datetimes de slots y bloqueos se construyen como aware con la zona Django.

No hay activación de zonas por usuario, por lo que esos usos resuelven hoy a la
zona configurada del salón.

### Defectos confirmados y corregidos aquí

- inicio de `_recomendar_primer_hueco_disponible()` con `date.today()`;
- fecha por defecto/comparaciones de `consultar_disponibilidad()` con
  `timezone.now().date()`.

Ambos pertenecen al mismo flujo de selección del primer hueco y tienen pruebas
de frontera UTC/local.

### Potencialmente inconsistentes, fuera de este alcance

Se localizaron otros usos de `date.today()` o `timezone.now().date()` en:

- programación de promociones de retoque;
- dashboard administrativo;
- filtrado de promociones activas;
- promociones Last Minute;
- sugerencias de combos por señales;
- módulos legacy de estadísticas con `datetime.now()`.

No se demostró aquí un fallo contractual en esos flujos y no participan en la
recomendación del primer Turno. No se modificaron silenciosamente; requieren
análisis y pruebas propias si se decide unificar toda la aplicación a fecha
comercial.

## 8. Riesgos residuales

- `TIME_ZONE='America/Bogota'` se respetó como fuente vigente. Si la sede cambia
  de zona, debe cambiarse la configuración operativa y revalidarse la matriz
  temporal.
- Otros módulos aún mezclan fuentes de fecha; están inventariados arriba, pero
  no deben corregirse sin definir primero su contrato comercial.
- La lógica de recomendación conserva captura amplia de excepciones y logging
  legacy; no se cambió porque es independiente del defecto temporal.
- Continúan pendientes los smoke tests del entorno desplegado.

La auditoría histórica de BH-061 no fue modificada y conserva su resultado
original **1.102/1.103**.

`CORRECCIÓN DE FECHAS — IMPLEMENTADA Y VALIDADA`
