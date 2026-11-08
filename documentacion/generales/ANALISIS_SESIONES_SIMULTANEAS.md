# Análisis de sesiones simultáneas

## Alcance

Este documento analiza el comportamiento actual sin proponer ni implementar
cambios. Se revisaron:

- `usuarios.views.LoginView` y `LogoutView`;
- `TokenObtainPairView` y `TokenRefreshView` de SimpleJWT;
- `frontend/src/pages/auth/Login.js`;
- `frontend/src/api/axiosConfig.js`;
- almacenamiento y eliminación de tokens en el frontend;
- modelos, signals y middleware;
- configuración `SIMPLE_JWT`;
- comportamiento real mediante llamadas API directas.

## Conclusión ejecutiva

El backend **sí permite múltiples sesiones simultáneas**, tanto para usuarios
distintos como para un mismo Usuario. Un login nuevo no invalida access tokens
ni refresh tokens anteriores.

El reemplazo observado ocurre en el frontend cuando ambas ventanas comparten
el mismo almacenamiento del navegador:

1. solo existen las claves globales `access_token` y `refresh_token` en
   `localStorage`;
2. el login de B sobrescribe los tokens de A;
3. el interceptor Axios consulta `localStorage` en cada request y reemplaza el
   header `Authorization` con el token que esté almacenado en ese momento;
4. todas las pestañas/ventanas del mismo perfil y origen pasan a enviar el
   token de B.

Además, cualquier respuesta `401` interceptada globalmente elimina access,
refresh e información de usuario y redirige a `/login`. Esto incluye un login
fallido y no solamente un JWT vencido.

Este comportamiento explica dos usuarios en pestañas o ventanas normales del
mismo perfil y origen. **No explica que una sesión normal afecte una ventana de
incógnito realmente aislada ni otro navegador realmente independiente.** Las
llamadas API directas confirman que el backend no reproduce ese efecto.

## A. Backend

### 1. Login personalizado

`usuarios.views.LoginView` valida email, password e `is_active`, y luego hace:

```python
refresh = RefreshToken.for_user(usuario)
```

Cada ejecución genera un JWT nuevo con un `jti` nuevo. No consulta tokens
anteriores, no los elimina y no los agrega a blacklist.

El endpoint usado actualmente por el frontend es:

```text
POST /api/usuarios/login/
```

### 2. Endpoint estándar de SimpleJWT

También existe:

```text
POST /api/token/
POST /api/token/refresh/
```

`TokenObtainPairView` tampoco aplica una política de sesión única. Emite un
nuevo par sin invalidar los pares anteriores.

### 3. Configuración SimpleJWT

Configuración actual:

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
}
```

Consecuencias:

- un access token dura 7 días;
- un refresh token dura 30 días;
- refrescar no rota el refresh token;
- refrescar no agrega el token anterior a blacklist;
- no hay configuración de sesión única.

La aplicación `rest_framework_simplejwt.token_blacklist` está instalada. Su
modelo `OutstandingToken` mantiene múltiples filas relacionadas con un mismo
Usuario; no es un campo único dentro de `Usuario`.

### 4. Persistencia de refresh tokens

No existe ningún campo `refresh_token` ni `access_token` en `Usuario` o en los
modelos de negocio revisados.

La única persistencia backend es la infraestructura estándar de SimpleJWT:

- `OutstandingToken`: un registro por refresh emitido;
- `BlacklistedToken`: referencia individual al refresh revocado.

Por tanto, **no existe persistencia de “un único refresh token por Usuario”**.

La mención de `refresh_token` en `gestion/signals.py` solo forma parte de una
lista defensiva de campos excluidos de auditoría. No representa un campo real
ni lógica de sesión.

### 5. Logout backend

`POST /api/usuarios/logout/` recibe un refresh token concreto y ejecuta:

```python
RefreshToken(refresh_token).blacklist()
```

Esto invalida únicamente ese refresh token:

- no invalida otros refresh tokens del mismo Usuario;
- no invalida tokens de otros Usuarios;
- no revoca el access token asociado, que sigue siendo válido hasta vencer o
  hasta que el Usuario quede inactivo.

El endpoint requiere un access token válido por `IsAuthenticated`.

### 6. Signals y middleware

`AuditoriaMiddleware` autentica el request para obtener el actor de auditoría y
lo guarda en un `threading.local`. No guarda tokens, no compara sesiones y no
ejecuta logout o blacklist.

Los signals de auditoría tampoco invalidan tokens.

No se encontró lógica que:

- borre tokens al iniciar sesión;
- invalide todos los tokens de un Usuario;
- conserve un único refresh por Usuario;
- cierre otras sesiones tras un login.

### 7. Excepción no relacionada con un login nuevo

Si `Usuario.is_active` pasa a `False`, la autenticación JWT rechaza access y
refresh existentes. Esto sí afecta todas las sesiones de ese Usuario, pero es
una operación semántica de desactivación de cuenta, no una consecuencia de que
otro Usuario inicie sesión.

## B. Frontend

### 1. Un único par de tokens por origen y perfil

`Login.js` guarda:

```javascript
localStorage.setItem('access_token', access);
localStorage.setItem('refresh_token', refresh);
```

No hay un namespace por Usuario, pestaña o ventana. Solo existe un par actual.

`localStorage` se comparte entre pestañas y ventanas que usan:

- el mismo perfil de navegador;
- el mismo origen, incluyendo protocolo, host y puerto.

Por eso, en dos ventanas normales del mismo perfil:

```text
login A -> access_token=A, refresh_token=A
login B -> access_token=B, refresh_token=B
```

Los JWT de A siguen siendo válidos en backend, pero sus cadenas ya no están
disponibles en el `localStorage` compartido.

### 2. El interceptor siempre toma el token almacenado más reciente

`axiosConfig.js` registra globalmente:

```javascript
const token = localStorage.getItem('access_token');
config.headers['Authorization'] = `Bearer ${token}`;
```

Esto se ejecuta para cada request. También sobrescribe cualquier header
`Authorization` colocado previamente por una pantalla con el valor actual de
`localStorage`.

Después del login de B, una pestaña que visualmente todavía parece pertenecer a
A empieza a enviar el token de B en su siguiente request. Puede mostrar datos
de B, redirigir según B o parecer que A fue reemplazado.

No existe un listener de `storage`, `BroadcastChannel`, cookie de autenticación
o service worker que sincronice sesiones por otra vía. La sincronización entre
ventanas normales se produce directamente por compartir `localStorage`.

### 3. Cualquier 401 elimina la sesión frontend

El interceptor global de respuesta hace lo siguiente ante cualquier `401`:

```javascript
localStorage.removeItem('access_token');
localStorage.removeItem('refresh_token');
localStorage.removeItem('user_info');
window.location.href = '/login';
```

No distingue entre:

- access token vencido;
- credenciales incorrectas en `/api/usuarios/login/`;
- Usuario inactivo;
- un endpoint que responde 401 por otra causa.

Por ello, en un contexto con almacenamiento compartido, un intento fallido de
login de B también elimina los tokens guardados de A.

`contenidoEducativoAPI.js` contiene otra limpieza y redirección ante 401.

### 4. El refresh token se almacena pero no se utiliza

No se encontró ninguna llamada frontend a `/api/token/refresh/`. Tampoco existe
una cola de renovación ni un reintento de requests.

Aunque los comentarios de `Login.js` dicen que el interceptor “mantendrá válido”
el token, el interceptor no renueva nada. Al primer 401 elimina también el
refresh token, por lo que el refresh de 30 días no se aprovecha.

### 5. Logout frontend

Los logout de `Login.js` y `Header.js` únicamente eliminan datos locales. No
llaman a `/api/usuarios/logout/`.

Consecuencias:

- el refresh token no entra en blacklist al usar la UI;
- el access y refresh continúan criptográficamente válidos si alguien conservó
  sus cadenas;
- en ventanas que comparten `localStorage`, borrar las claves afecta el estado
  disponible para todas ellas;
- no afecta el almacenamiento de un navegador o perfil realmente aislado.

### 6. ProtectedRoute

`ProtectedRoute` solo comprueba que exista `access_token` en `localStorage`. No
valida a qué Usuario pertenece ni comprueba expiración. Por eso, tras la
sobrescritura, considera autenticadas todas las pestañas con el token de B.

## C. Interacción backend/frontend

La secuencia problemática en almacenamiento compartido es:

```text
Pestaña 1: Usuario A inicia sesión
-> backend emite token A
-> frontend guarda token A

Pestaña 2: Usuario B inicia sesión
-> backend emite token B sin invalidar token A
-> frontend sobrescribe las mismas claves con token B

Pestaña 1 realiza otra petición
-> interceptor lee token B
-> backend autentica correctamente como B
```

Por tanto:

- el backend conserva ambas sesiones;
- el frontend solo conserva una identidad por área de `localStorage`;
- el comportamiento visible parece una sesión reemplazada, aunque el JWT de A
  nunca fue invalidado.

Si cualquiera de esas pestañas recibe un 401, el interceptor borra el único par
almacenado, lo que hace que todas las pestañas del mismo origen parezcan cerrar
sesión.

## Aislamiento por navegador

### Comparten almacenamiento

- pestañas normales del mismo perfil y origen;
- ventanas normales del mismo perfil y origen;
- normalmente, distintas ventanas privadas pertenecientes a una misma sesión
  privada del navegador.

### No deberían compartir almacenamiento

- ventana normal frente a incógnito realmente aislado;
- perfiles de navegador distintos;
- navegadores distintos;
- orígenes distintos, por ejemplo `localhost:3000` y `127.0.0.1:3000`.

La reproducción directa demuestra que un login no invalida tokens en backend.
Si el efecto ocurre realmente entre dos navegadores independientes, esta base
de código no contiene un mecanismo que lo explique. En ese caso debe
verificarse durante la reproducción:

1. que ambos contextos usan realmente almacenamientos distintos;
2. qué token exacto envía cada request en Network;
3. qué request devuelve el primer 401;
4. si la cuenta fue desactivada entre requests;
5. si se está probando la misma instancia y configuración del backend.

## Reproducción API directa

Se ejecutó una reproducción transaccional contra los endpoints reales. Los
usuarios y tokens de prueba se revirtieron al finalizar.

### Secuencia mínima solicitada

```text
Usuario A login -> token A                 200
Usuario B login -> token B                 200
GET /api/usuarios/perfil/ con access A     200
GET /api/usuarios/perfil/ con access B     200
POST /api/token/refresh/ con refresh A     200
POST /api/token/refresh/ con refresh B     200
```

Ningún token deja de funcionar después del segundo login.

### Segunda sesión del mismo Usuario

También se inició sesión dos veces con el Usuario A:

```text
login A1                                    200
login A2                                    200
access A1 después de A2                     200
refresh A1 después de A2                    200
refresh A2                                  200
OutstandingToken de A                       2
```

Esto confirma que tampoco existe sesión única por Usuario.

### Logout selectivo

Se envió únicamente `refresh A1` a `/api/usuarios/logout/`:

```text
logout A1                                   205
access A1 después del logout                200
refresh A1 después del logout               401
refresh A2 del mismo Usuario                200
refresh B                                   200
BlacklistedToken de A                       1
BlacklistedToken de B                       0
```

El único elemento que deja de funcionar es el refresh token enviado al logout,
y lo hace en ese momento. El access asociado y las demás sesiones permanecen
válidos.

## Respuestas directas

### ¿El backend permite múltiples access/refresh tokens por Usuario?

Sí. Fue confirmado con dos pares simultáneos para el mismo Usuario.

### ¿Existe persistencia de un único refresh token?

No. No hay un campo en `Usuario`; `OutstandingToken` admite múltiples registros
por Usuario.

### ¿Un login nuevo invalida el anterior?

No en backend. En frontend sobrescribe las claves si comparte `localStorage`.

### ¿El logout de una sesión invalida todas?

No. El logout backend invalida solo el refresh recibido. El logout frontend ni
siquiera llama al backend y solo limpia el almacenamiento local compartido.

### ¿Axios limpia el almacenamiento ante cualquier 401?

Sí. El interceptor global elimina access, refresh y `user_info`, y redirige al
login. No intenta refresh ni diferencia la causa del 401.

### ¿Por qué otra ventana se ve afectada?

Porque ventanas del mismo perfil y origen comparten `localStorage`, y Axios lee
el valor compartido en cada request. No debería ocurrir entre contextos
realmente aislados.

### ¿El problema reproduce con llamadas API directas?

No. Los tokens A y B, y dos tokens del mismo Usuario A, permanecieron válidos
simultáneamente. Solo falló el refresh revocado explícitamente mediante logout.

## Diagnóstico final

**Problema backend:** no se encontró una política accidental de sesión única.
El backend soporta sesiones simultáneas. La única invalidación global esperada
es la desactivación de la cuenta.

**Problema frontend:** existe una única sesión por origen/perfil debido al uso
de claves únicas en `localStorage`. El interceptor convierte esa sobrescritura
en cambio efectivo de identidad para todas las pestañas compartidas y elimina
la sesión completa ante cualquier 401.

**Interacción:** el frontend hace parecer que el backend reemplazó o cerró una
sesión, pero los JWT anteriores continúan válidos si se conservan y se prueban
directamente.
