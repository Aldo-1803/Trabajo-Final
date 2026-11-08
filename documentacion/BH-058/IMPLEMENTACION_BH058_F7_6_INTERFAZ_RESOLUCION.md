# BH-058 F7.6 — Interfaz y validación operativa

**Fecha:** 2026-11-02

**Base validada:** F7.1–F7.5, commit `58f39dae0529fb52f914881a65567aae9b82638a`

**Alcance:** exclusivamente F7.6. BH-058 no se declara cerrado y BH-059 no se inicia.

## 1. Resultado implementado

Se incorporó la bandeja administrativa independiente
`/admin/incidencias-financieras`. La ruta, la navegación y la propia pantalla
exigen el permiso efectivo `gestion.reconcile_external_payment`; un rol nominal
o un perfil de cliente no lo reemplazan.

La interfaz consume las autoridades ya disponibles en F7.1–F7.5 para:

- listar casos abiertos o resueltos y filtrar por tipo, contexto, estado y
  antigüedad;
- consultar obligación, referencia mínima de cliente, pagos, importes,
  ajustes confirmados, neto e historial;
- presentar solicitudes y registrar decisiones compatibles con el estado;
- consultar el reversible y solicitar un refund ya autorizado;
- seguir operaciones `PENDING`, `SUBMITTED`, `UNKNOWN`, `FAILED` y
  `CONFIRMED`;
- recuperar `SUBMITTED`/`UNKNOWN` consultando la Order oficial sin reenviar el
  refund;
- solicitar revisión de cancelación para una orden `PAGADO` sin cancelarla;
- aplicar el efecto comercial y cerrar únicamente cuando el backend puede
  verificarlo.

No se agregó una nueva acción backend. El único agregado de lectura es
`customer_reference`, allowlisted como `client_id` y `display_name`. No expone
email, teléfono, tokens, comprobantes ni snapshots completos.

## 2. Autoridad y garantías

- El frontend deriva qué controles mostrar, pero el backend conserva toda la
  autoridad y vuelve a validar permisos, estados, eventos, importes, moneda,
  ajustes, stock e idempotencia.
- `APPROVE_REFUND` no significa ejecución ni confirmación y no habilita cierre
  por sí solo.
- Una respuesta HTTP exitosa tampoco se presenta como refund confirmado.
- Los comandos usan una clave idempotente estable por tipo y fingerprint
  mientras la operación está activa. El backend mantiene además sus
  constraints e identidades durables.
- Un lock síncrono, sumado al estado deshabilitado, evita dobles envíos incluso
  ante dos clics en el mismo ciclo de render.
- Toda acción sensible exige confirmación explícita. Antes de ejecutar un
  refund se muestran importe autorizado, moneda y obligación.
- Después de cada comando se vuelven a consultar lista, detalle y, cuando
  corresponde, operación de refund.
- Los errores de comando se preservan durante esa resincronización. Se
  distinguen 403, 409, 422 y red/resultado desconocido.

## 3. Guía operativa breve

### Revisar y clasificar

1. Ingresar a **Incidencias financieras**, no a **Caja presencial**.
2. Filtrar inicialmente por `OPEN` y ordenar los más antiguos primero.
3. Priorizar los casos señalados como envejecidos (48 horas o más).
4. Verificar cliente, obligación, estado comercial, bruto conciliado, ajustes
   confirmados, neto, refund pendiente e historial.
5. No inferir un hecho financiero desde una solicitud, una decisión o una
   respuesta HTTP.

### Solicitud y decisión

1. Si el caso no tiene solicitud, registrar resultado solicitado, motivo,
   importe si aplica y referencias de evidencia sanitizadas.
2. Si está pendiente de decisión, elegir sólo una acción disponible en la
   pantalla. Para aprobar o denegar un refund se debe registrar política y
   fundamento; para pedir evidencia, describir exactamente lo faltante.
3. Ante 409, releer el caso resincronizado y no insistir con una decisión
   incompatible. Ante 403, solicitar la capacidad efectiva; cambiar el rol
   visual no la concede. Ante 422, completar o corregir la evidencia indicada.

### Refund autorizado

1. Confirmar que la decisión final sea `APPROVE_REFUND`.
2. Verificar el pago Mercado Pago conciliado, reversible positivo, importe,
   moneda y obligación mostrados en la confirmación.
3. Solicitar una sola vez. `PENDING` o `SUBMITTED` siguen pendientes;
   `FAILED` no equivale a devolución; sólo `CONFIRMED`, respaldado por F7.4,
   constituye confirmación financiera.
4. No cerrar hasta que operación, ajuste y neto sean consistentes.

### Manejo de `UNKNOWN`

1. **No reenviar el refund.**
2. Usar **Recuperar sin reenviar** para consultar la Order oficial.
3. Si no hay coincidencia única, conservar `UNKNOWN`, escalar con la identidad
   de la operación y esperar evidencia oficial.
4. Resincronizar después del procesamiento de eventos. Sólo un evento terminal
   verificado puede materializar el ajuste y permitir `CONFIRMED`.

### Cierre y efectos comerciales

- El resultado de cierre se deriva del estado real; no se elige libremente.
- Refund confirmado, denegación fundada, ajuste externo reconocido y decisión
  sin cambio financiero tienen caminos distintos.
- Una orden ya completada usa `PHYSICAL_RETURN_DEFERRED`; la interfaz no
  repone stock ni revierte una entrega.
- El cierre llama a F7.5, que aplica efectos bajo locks y registra el hecho
  inmutable. La interfaz no modifica directamente Pago, Turno, Orden ni stock.

## 4. Recuperación tras reinicios y worker

Solicitudes, decisiones, operaciones, ajustes y cierres son durables. Después
de reiniciar frontend o backend:

1. iniciar el backend y volver a abrir la bandeja;
2. seleccionar el caso para recargar detalle y operación desde base de datos;
3. si está `UNKNOWN`, usar recuperación oficial; nunca recrear manualmente la
   operación;
4. comprobar que el worker de eventos esté procesando verificaciones y
   conciliaciones antes de evaluar el cierre.

Comando existente del worker:

```powershell
python manage.py process_provider_events --watch
```

Variables disponibles:

```text
PROVIDER_EVENT_WORKER_LIMIT=100
PROVIDER_EVENT_WORKER_STALE_MINUTES=10
PROVIDER_EVENT_WORKER_RETRY_SECONDS=60
PROVIDER_EVENT_WORKER_POLL_SECONDS=5
```

Los valores deben ajustarse al entorno, con credenciales en un mecanismo de
secretos externo al repositorio. Instalación, reinicio automático y logs bajo
systemd: **NO VERIFICADO** en este entorno Windows.

## 5. Escenarios funcionales automatizados

La suite de página usa mocks controlados; no llama al proveedor ni devuelve
dinero real. Cubre:

1. cancelación de turno con seña;
2. cancelación de turno pagado totalmente;
3. pago tardío sin turno;
4. orden `PAGADO` no entregable;
5. solicitud de cancelación de orden `PAGADO` sin mutación comercial;
6. refund total confirmado;
7. refund parcial confirmado con neto remanente;
8. contracargo confirmado sin ofrecer un refund incompatible;
9. duplicación/discrepancia 409 con resincronización y un único envío.

También verifica permiso denegado, importes, confirmaciones, historial,
antigüedad, cierre no elegible, todos los estados de operación, recuperación
`UNKNOWN`, 403, 422 y ausencia de acciones indebidas.

Validación real con credenciales y fondos de sandbox: **NO VERIFICADO**. No se
efectuaron refunds reales.

## 6. Evidencia de pruebas

### Resultado final

| Control | Resultado |
|---|---:|
| Frontend focalizado: 5 suites | **81/81 OK** |
| Página y nueve escenarios funcionales | **14/14 OK** |
| Regresiones backend F7.1–F7.5, adaptador y concurrencia | **71/71 OK** |
| `python manage.py check` | **OK, 0 issues** |
| `makemigrations --check --dry-run` | **OK, sin cambios** |
| `migrate --check` | **OK, sin migraciones pendientes** |
| `python -m compileall gestion` | **OK** |
| `npm run build` | **OK con warnings preexistentes** |
| `git diff --check` y staged diff check | **OK** |
| Escaneo de patrones de secretos sobre líneas agregadas | **Sin coincidencias** |

Las 71 pruebas backend se ejecutaron sobre PostgreSQL e incluyen las suites de
lectura, solicitudes/decisiones, refund, adaptador, ajustes, cierre y sus
pruebas de concurrencia. Usan mocks para proveedor; no hubo llamadas de red ni
refunds reales.

### Fallos observados y corregidos

- La primera carga de la suite de página falló porque el factory de
  `jest.mock` referenciaba `canReconcile` fuera de alcance. Se renombró a
  `mockCanReconcile`.
- En una ejecución intermedia hubo 5 fallos de 14: dos eran consultas/esperas
  ambiguas de Testing Library y tres correspondían a 409/403/422 cuyo alert no
  permanecía visible después de resincronizar. Se separó el error de comando
  del error de carga, se agregó el lock síncrono y se restauró explícitamente
  el normalizador del mock en cada prueba. Resultado final: 14/14.
- El primer comando de regresión backend no ejecutó tests: la base
  `test_bohemia_hair_clean` ya existía y Django pidió confirmación interactiva,
  terminando con `EOFError`. Se preservó la base y se repitió con `--keepdb`:
  71/71 OK.

El build conserva warnings preexistentes fuera de F7.6 (imports sin uso,
dependencias faltantes de hooks, export anónimo, dependencia dinámica) y aviso
de Browserslist desactualizado. No se ocultaron ni se modificaron como parte de
este incremento.

## 7. Operación y despliegue pendientes

- Sandbox Mercado Pago con credenciales de prueba y observación completa de
  webhook/worker: **NO VERIFICADO**.
- Servicio systemd, política de reinicio, usuario del proceso, archivo de
  entorno, rotación de logs y alertas: **NO VERIFICADO**.
- Despliegue detrás del proxy/origen definitivo, incluida la configuración de
  URL base de Axios existente: **NO VERIFICADO**.
- Prueba E2E de navegador contra un backend desplegado: **NO VERIFICADO**; la
  matriz frontend es automatizada con mocks y las API se validaron por separado
  en Django.
- Los tests locales no constituyen por sí solos autorización para producción.

## 8. Archivos principales

- `frontend/src/pages/admin/GestionIncidenciasFinancieras.js` y su suite;
- `frontend/src/api/financialCasesApi.js` y su suite;
- `frontend/src/utils/financialCaseWorkflow.js` y su suite;
- ruta protegida y navegación en `frontend/src/routes/` y
  `frontend/src/navigation/`;
- referencia mínima de cliente en
  `bohemiacore/gestion/financial_case_serializers.py`, con precarga en la vista
  y regresión de API.

F7.6 no agrega modelos ni migraciones, no duplica servicios de pagos, refunds,
ajustes o stock y no inicia BH-059.
