# BH-060 Incremento 6 — Estados, permisos residuales y aliases legacy

Fecha de validación: 2026-11-06

Baseline publicado: `91b27fab2690fdf2f6fcab479d62135b6cd5eb4a`

## 1. Alcance y resultado

Se agregó una matriz focalizada de transiciones de autoridad sobre PostgreSQL:
tokens JWT emitidos antes del cambio, cuenta y Personal inactivos, habilidad,
degradación de `BusinessRole`, caché de permisos Django, grants/revokes
individuales, grupos técnicos y aliases activos.

No se inició el Incremento 7, BH-061 ni BH-062. No se cambió autenticación,
onboarding, agenda, diagnóstico, inventario canónico, PaymentIntent,
conciliación externa ni resolución de incidencias.

## 2. Matriz de rutas canónicas y legacy

| Operación | Ruta canónica | Ruta alternativa/legacy | Autoridad y restricciones | Cobertura previa | Cobertura faltante resuelta |
|---|---|---|---|---|---|
| Administrar cuenta y rol | `/api/gestion/admin/usuarios/{id}/desactivar-cuenta/`, `reactivar-cuenta/`, `cambiar-rol-acceso/` | Acciones semánticas de `/api/gestion/personal/{id}/...` para estado/rol laboral | `manage_users`; para rol también `assign_roles`; actor/objetivo activos, perfiles coherentes, no autoacción/superuser, último admin y residuos administrativos | BH-059 A–D, servicios y API | JWT previo a baja; instancia cargada/nueva; request posterior a degradación; caché Django y preservación de grupo técnico |
| Agenda global y propia | `GET /api/gestion/turnos/`, `GET /api/gestion/turnos/mi-agenda-laboral/` | `GET /api/gestion/agenda/general/`, `GET /api/gestion/obtener_disponibilidad_calendario/` | Global: `view_global_agenda`; propia: ownership; Usuario y Personal activos | BH-060.2 y suites de Turnos | Transición de Personal activo a inactivo usando el mismo JWT en ruta canónica y legacy |
| Crear/leer diagnóstico | `/api/gestion/diagnosticos-capilares/` | `/api/usuarios/diagnostico/` sólo proyecta el diagnóstico propio más reciente; no es writer equivalente | `create_diagnosis` o `manage_technical_record` según acción, Personal activo, habilidad `DIAGNOSTICO` activa y ownership/autor | `test_diagnosis_authorization_api` | Revocación dinámica de habilidad e inactivación de Personal sin perder el grant individual; cero nueva fila |
| Ficha técnica y fórmulas | `/api/gestion/fichas-tecnicas/` y acciones de fórmula | Sin writer legacy activo equivalente | `manage_technical_record`/`manage_formulas`, habilidad, profesional asignado, ownership y estado del Turno | BH-060.3 | Sin hueco dinámico adicional: la combinación estado/habilidad quedó comprobada en diagnóstico y la matriz estática de ficha ya era equivalente |
| Seleccionar Rutina | `POST /api/gestion/rutinas/seleccionar/` | `POST /api/gestion/prueba-rutina/` | Cliente propio activo; sólo Rutina publicada; payload cerrado y duplicado idempotente por conflicto | BH-060.3 | Sin duplicación: ya cubría ownership, payload, estado y ambas rutas |
| Mutar stock | `POST /api/gestion/productos/{id}/stock/receive/` y `adjust/` | Ledger `/api/gestion/stock-movements/`; no existe writer genérico alternativo | `manage_stock`, cuenta activa, cantidad/razón/clave válidas; lock, idempotencia y auditoría | Inventario D3 y BH-060.5 | Token anterior a baja; grant y revoke individual; `is_staff` sin permiso; cero stock/movimiento/evento en rechazo |
| Confirmar/cancelar/entregar orden | Servicios y acciones de `/api/gestion/ordenes-compra/` | `/api/gestion/ordenes-pendientes/{id}/confirmar_pago/` y `cancelar/` | Ownership o `manage_stock`; estado, compromisos, stock e idempotencia | `test_order_inventory` | No se repitió: la delegación y equivalencia ya estaban cubiertas |
| Registrar pago de booking | `POST /api/gestion/payment-intents/{uuid}/payments/` | No hay alias de escritura equivalente | `register_payment`, Intent/HOLD vigentes, policy, saldo, evidencia e idempotencia | `test_manual_payments` | Sin cambio; se preservó íntegro |
| Registrar pago legacy de Orden | Flujo ORDER conciliado por checkout/provider | `POST /api/gestion/ordenes-compra/{id}/registrar_pago/` | `register_payment`, cuenta activa, orden pagable, saldo e `Idempotency-Key`; lock por orden | Sólo permiso efectivo y alta simple | Se reprodujeron estado terminal, retry duplicado y sobrepago; se corrigió sólo este writer |
| Leer pagos | `GET /api/gestion/payments/` | `GET /api/gestion/pagos/` | `view_financial_reports`; sin CRUD genérico | BH-058 B2 | Ambos aliases pierden acceso en requests nuevos tras degradar ADMINISTRADOR a CLIENTE |
| Incidencias financieras | `/api/gestion/payment-reconciliation-cases/` y comandos semánticos | Sin CRUD legacy equivalente | permisos financieros exactos, estado, locks e idempotencia | BH-058 F7 | Regresión acotada; no se modificó el dominio |

Las rutas de Usuarios/Personal son superficies relacionadas pero no aliases
intercambiables: una administra la cuenta y otra el vínculo laboral. La matriz
las trata juntas para comprobar que ninguna transición deje autoridad residual.

## 3. Cobertura agregada

Archivos nuevos:

- `gestion/tests/test_state_residual_aliases_bh060_6.py`;
- `gestion/tests/test_legacy_order_payment_concurrency_bh060_6.py`.

Casos agregados:

1. Un access token real emitido antes de desactivar la cuenta deja de autenticar
   para una recepción de stock. No cambia stock, no crea movimiento y no emite
   `STOCK_MOVEMENT_CREATED`.
2. Un grant individual de `manage_stock` funciona con `is_staff=False`; el
   revoke bloquea requests posteriores con el mismo JWT. `is_staff=True` sin el
   permiso sigue rechazado.
3. La degradación ADMINISTRADOR → CLIENTE elimina
   `view_financial_reports` en la instancia suministrada, una instancia nueva y
   requests nuevos a `payments` y `pagos`.
4. La transición limpia `_perm_cache`; el JWT no contiene autoridad de negocio
   y cada request recarga al Usuario. No se confundió caché de Django con sesión
   o autorización real del servidor.
5. El grupo técnico no canónico de lectura de stock se conserva y continúa
   autorizando `/stock-movements/`, conforme al contrato.
6. Personal activo → inactivo cierra agenda laboral propia canónica y legacy.
7. Un permiso individual de diagnóstico no elude habilidad inactiva ni Personal
   inactivo; después de cada rechazo permanece una sola fila legítima.
8. El pago legacy de Orden rechaza estado terminal y sobrepago, y un retry con
   la misma clave devuelve el mismo Pago sin un segundo evento.
9. Dos carreras PostgreSQL prueban un único ganador para sobrepago y un único
   Pago/evento para la misma clave idempotente.

La matriz existente de BH-060.2/BH-060.3 sigue aportando CLIENTE, EMPLEADO,
PROFESIONAL y ADMINISTRADOR, ownership propio/ajeno, aliases de agenda y Rutina,
payloads cerrados y ausencia de mutación. No se duplicaron esos casos.

## 4. Bypass encontrado y corrección mínima

### Evidencia reproducida

Antes de la corrección, `OrdenCompraViewSet.registrar_pago`:

- devolvía `201` y creaba un Pago para una Orden `CANCELADO`;
- devolvía otro `201` al repetir exactamente el comando;
- no validaba el saldo y permitía sobrepago;
- creaba directamente con `Pago.objects.create`, sin lock de Orden ni evento
  semántico idempotente.

### Corrección acotada

La acción ahora delega en `register_legacy_order_payment` y conserva su URL y
payload legacy. El servicio:

- recarga al actor activo y exige exactamente `register_payment`;
- exige `Idempotency-Key` y sólo persiste su hash en auditoría;
- bloquea la Orden y sus Pagos con `select_for_update`;
- admite únicamente `PENDIENTE` y `ESPERANDO_PAGO`;
- rechaza importes no positivos y sobrepago;
- devuelve `201` para alta y `200` para retry idéntico;
- emite una sola vez `ORDER_MANUAL_PAYMENT_REGISTERED`;
- no marca la Orden como `PAGADO`, preservando el contrato financiero previo.

`PagoModal` genera una clave por apertura del comando y la reutiliza ante un
retry de red. No se alteraron PaymentIntent, proveedor, refunds, ajustes,
incidencias ni entrega de stock.

## 5. Resultados PostgreSQL y regresiones

Backend confirmado: `django.db.backends.postgresql`.

| Bloque | Resultado |
|---|---:|
| Suite focalizada de estados/residuos/aliases | **7/7 OK** |
| Concurrencia legacy ORDER aislada | **2/2 OK** |
| Suite focalizada + API de pagos manuales | **16/16 OK** |
| BH-059 roles, cuentas, tokens y superficies A–C | **109/109 OK** |
| BH-060 Incrementos 1–5 | **80/80 OK** |
| Lectura, creación, gestión, llegada y habilidades de Turnos | **94/94 OK** sobre base limpia |
| Inventario, órdenes, pagos, checkout y conciliación | **107/107 OK** |
| Lectura y resolución de incidencias financieras | **22/22 OK** |
| Diagnóstico aislado | **25/26 conformes; 1 fallo legacy conocido** |
| `manage.py check` | **OK**, 0 issues |
| `makemigrations --check --dry-run` | **OK**, sin cambios |
| Build frontend normal | **OK**, con warnings globales preexistentes |
| `git diff --check` | **OK** |

Los tests concurrentes se ejecutaron en un comando separado, con conexiones
PostgreSQL independientes. Un intento de reutilizar `--keepdb` entre bloques
que contienen `TransactionTestCase` perdió datos semilla del harness; se repitió
el bloque afectado sobre base limpia y obtuvo 94/94. Corregir esa estabilización
pertenece al Incremento 7 y no se abordó aquí.

### Fallo legacy separado

`test_legacy_flags_are_read_only_in_personal_serializer` continúa siendo el
único fallo conocido: espera aceptar e ignorar flags técnicos legacy, mientras
el serializer seguro los rechaza con `Este campo no está permitido.`. Resultado
aislado: **25/26**. No se debilitó `PersonalSerializer`.

## 6. Riesgos pendientes para Incremento 7 y producción

- Reactivar una cuenta puede volver temporalmente utilizable un access token
  previo aún no vencido. El servicio informa
  `PREEXISTING_ACCESS_TOKENS_MAY_REGAIN_VALIDITY`; cambiar autenticación queda
  fuera de este incremento.
- El harness conserva prints y estado thread-local de middleware/señales, y una
  base `--keepdb` compartida con suites transaccionales no es una partición
  confiable. Son temas explícitos del Incremento 7.
- El writer legacy de Orden queda endurecido, pero sigue separado del grafo
  PaymentIntent por compatibilidad. Antes de producción debe confirmarse su
  consumidor y planificar retiro controlado si deja de ser necesario.
- Los warnings globales del build frontend y la configuración productiva de
  proxy, CORS, secretos, storage y callbacks permanecen fuera de BH-060.6.

## Estado

**BH-060 INCREMENTO 6 = VALIDADO**
