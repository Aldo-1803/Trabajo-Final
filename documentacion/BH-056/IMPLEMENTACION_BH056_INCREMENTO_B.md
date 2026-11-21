# BH-056 — Incremento B: compatibilidad canónica de Turnos

## Resultado

Disponibilidad, creación y reprogramación usan como única autoridad técnica:

1. `ServicioHabilidad` de todos los Servicios del Turno;
2. `Habilidad.activa=True` para cada requisito;
3. `PersonalHabilidad.activa=True` para el mismo Personal;
4. semántica AND sobre la unión de requisitos.

Los flags `Personal.realiza_diagnostico`, `realiza_lavado` y `realiza_color`
siguen en el esquema como **LEGACY - compatibility only**, pero
`realiza_lavado` y `realiza_color` ya no intervienen en Turnos.

## Fuente centralizada

`gestion/service_skill_compatibility.py` contiene:

- `ServiceSkillPolicy`, que resuelve requisitos, configuración inválida y
  filtrado eficiente de Personal;
- `personal_can_perform_service()`;
- `personal_can_perform_services()` para la unión multiservicio;
- la equivalencia temporal entre códigos canónicos y flags de agenda.

`TurnoAvailabilityService.matching_schedules()` y `validate_slot()` consumen
esta política. `TurnoCreationService`, reserva Cliente, creación para tercero y
reprogramación administrativa/Cliente ya convergían en `validate_slot`, por lo
que no se duplicó la validación.

## Reglas resultantes

- Servicio sin skills: no agrega restricción técnica.
- Personal inactivo: nunca elegible.
- Asignación ausente o `PersonalHabilidad.activa=False`: incompatible.
- Requisito con `Habilidad.activa=False`: fail-closed con código estable
  `INACTIVE_REQUIRED_SKILL`; disponibilidad no ofrece slots.
- Personal sin todos los requisitos: `PERSONAL_SKILL_MISMATCH`.
- Varios requisitos de un Servicio: AND.
- Turno multiservicio: AND sobre la unión de skills de todos los Servicios,
  para el único Personal asignado al Turno.
- Un `realiza_color=True` no sustituye una asignación canónica ausente.
- Un `realiza_color=False` no bloquea una asignación canónica activa.

## Clasificación textual y horarios

`TurnoAvailabilityService` ya no lee nombres de categorías ni infiere skills
en runtime. La clasificación `diseño/color` y `complemento` queda limitada al
backfill `0021` y a su comparación diagnóstica en tests.

`HorarioLaboral.permite_diseno_color` y `permite_complemento` permanecen como
restricciones temporales de agenda, no como skills:

- requisito `COLORACION` exige también `permite_diseno_color=True`;
- requisito `LAVADO` exige también `permite_complemento=True`;
- otros códigos no reciben una inferencia temporal nueva;
- Servicio sin requisitos no queda restringido por esos flags.

Esta equivalencia usa `Habilidad.code`, nunca texto visible. El rediseño o
retiro de esos campos de horario queda como deuda posterior.

Por instrucción de alcance, no se modificó `DiagnosticoCapilarViewSet`; su
recomendador conserva temporalmente su clasificación propia y debe migrarse en
un incremento separado.

## Selector y frontend

`GET /turnos/selector-personal/` conserva su contrato genérico. Cuando recibe
`servicio_ids` (repetido o separado por comas), devuelve sólo Personal activo
compatible con la unión de requisitos. IDs inexistentes/inactivos se rechazan.

Los flujos frontend continúan confiando en la disponibilidad backend. No se
agregó lógica de skills en JavaScript.

## Performance

- Los Servicios se cargan con prefetch de
  `requisitos_habilidad__habilidad` en disponibilidad, creación y
  reprogramación.
- La lista de Personal compatible se filtra en SQL mediante `Count` filtrado
  de asignaciones activas, evitando N+1 y exigiendo todos los IDs requeridos.
- La política reutiliza el snapshot de requisitos y cachea por Personal el
  resultado durante la generación de múltiples slots.
- No se introdujeron cachés globales ni infraestructura compleja.

## Comparación legacy vs skills

Un test diagnóstico compara ambos resultados para fixtures equivalentes al
backfill:

- `Diseño/Color` ↔ `COLORACION`;
- `Complemento` ↔ `LAVADO`;
- otra categoría ↔ sin requisito.

La comparación coincide. No existe fallback u OR en runtime.

## Datos locales

Se aplicó `gestion.0021` correctamente en la base local. Resultado:

- skills: `DIAGNOSTICO`, `LAVADO`, `COLORACION`, todas activas;
- Personal 2: `LAVADO` activa;
- Personal 3: `DIAGNOSTICO` y `LAVADO` activas;
- Personal 4: sin asignaciones;
- los flags legacy permanecieron sin cambios;
- categorías: 0;
- Servicios: 0;
- requisitos de Servicio: 0.

Por no existir Servicios locales, la validación de categorías y multiservicio
se realizó exclusivamente con fixtures/tests; no se inventaron registros.

## Validación

Siempre se utilizó `venv\Scripts\python.exe` con salida UTF-8.

- `manage.py check`: OK.
- `manage.py makemigrations --check`: sin cambios; Incremento B no crea
  migraciones.
- Compatibilidad canónica nueva: **21/21**.
- Skills A, migración/backfill, disponibilidad, creación y reprogramación:
  **71/71** en ejecución combinada equivalente.
- Lectura y llegada de Turnos: **36/36**.
- Personal access/status, roles y `/me/`: **59/59**.
- Frontend ReservaCliente, NuevoTurno, Gestión/Reprogramación y MisTurnos:
  **15/15**.
- `git diff --check`: OK (sólo advertencias de normalización de fin de línea).

## Siguiente paso recomendado

Validar el switch con Servicios reales cuando existan datos locales y abordar
`DiagnosticoCapilarViewSet` en un incremento expresamente autorizado. Los flags
legacy no deben retirarse hasta completar ese trabajo y auditar consumidores.

**BH-056 B = VALIDADO**
