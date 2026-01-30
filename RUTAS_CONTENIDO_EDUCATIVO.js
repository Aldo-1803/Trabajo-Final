// ============================================================
// RUTAS PARA CONTENIDO EDUCATIVO
// Agregá estas rutas a tu App.js o Router principal
// ============================================================

import ContenidoEducativoLista from './pages/profesional/ContenidoEducativoLista';
import ContenidoPublico from './pages/cliente/ContenidoPublico';
import ContenidoGuardado from './pages/cliente/ContenidoGuardado';
import ContenidoRecomendado from './pages/cliente/ContenidoRecomendado';
import DetalleContenido from './pages/cliente/DetalleContenido';

// ============================================================
// EN TU ESTRUCTURA DE RUTAS (BrowserRouter)
// ============================================================

{/* ========== PROFESIONAL ========== */}
<Route 
    path="/profesional/contenido-educativo" 
    element={<ContenidoEducativoLista />} 
/>

{/* ========== CLIENTE ========== */}
<Route 
    path="/cliente/contenido-publico" 
    element={<ContenidoPublico />} 
/>

<Route 
    path="/cliente/contenido-guardado" 
    element={<ContenidoGuardado />} 
/>

<Route 
    path="/cliente/contenido-recomendado" 
    element={<ContenidoRecomendado />} 
/>

<Route 
    path="/cliente/contenido/:id" 
    element={<DetalleContenido />} 
/>

// ============================================================
// LINKS PARA NAVEGACIÓN (Agregá en tu Nav o Menu)
// ============================================================

/* Para Profesionales */
<li>
    <a href="/profesional/contenido-educativo" style={{ color: '#817773' }}>
        📚 Mis Artículos Educativos
    </a>
</li>

/* Para Clientes */
<li>
    <a href="/cliente/contenido-publico" style={{ color: '#817773' }}>
        📚 Centro Educativo
    </a>
</li>

<li>
    <a href="/cliente/contenido-recomendado" style={{ color: '#817773' }}>
        ✨ Recomendado para Ti
    </a>
</li>

<li>
    <a href="/cliente/contenido-guardado" style={{ color: '#817773' }}>
        🔖 Mis Guardados
    </a>
</li>

// ============================================================
// INTEGRACIÓN CON EXISTENTES
// ============================================================

// Si usas un componente como TarjetaContenido en otra parte:
import TarjetaContenido from './components/TarjetaContenido';

// Para que sea clickeable en detalle, agregar:
<div onClick={() => navigate(`/cliente/contenido/${contenido.id}`)}>
    <TarjetaContenido 
        contenido={contenido} 
        esPropio={false}
        onLike={handleRefresco}
        onGuardar={handleRefresco}
    />
</div>

// ============================================================
// ENDPOINTS API USADOS
// ============================================================

/*
GET    http://localhost:8000/api/contenido-educativo/
GET    http://localhost:8000/api/contenido-educativo/?estado=PUBLICADO
GET    http://localhost:8000/api/contenido-educativo/?search=...
GET    http://localhost:8000/api/contenido-educativo/?tipo=IMAGEN
GET    http://localhost:8000/api/contenido-educativo/?autor=1
GET    http://localhost:8000/api/contenido-educativo/?ordering=-fecha_publicacion
GET    http://localhost:8000/api/contenido-educativo/{id}/
POST   http://localhost:8000/api/contenido-educativo/
PUT    http://localhost:8000/api/contenido-educativo/{id}/
DELETE http://localhost:8000/api/contenido-educativo/{id}/
POST   http://localhost:8000/api/contenido-educativo/{id}/like/
POST   http://localhost:8000/api/contenido-educativo/{id}/guardar/
GET    http://localhost:8000/api/contenido-educativo/mis-guardados/
GET    http://localhost:8000/api/contenido-educativo/recomendados_por_diagnostico/
*/

// ============================================================
// ESTRUCTURA DE CARPETAS ESPERADA
// ============================================================

/*
frontend/
  src/
    components/
      TarjetaContenido.js ✅
      PanelEditorContenido.js ✅
    pages/
      profesional/
        ContenidoEducativoLista.js ✅
      cliente/
        ContenidoPublico.js ✅
        ContenidoGuardado.js ✅
        ContenidoRecomendado.js ✅
        DetalleContenido.js ✅
*/

// ============================================================
// CONFIGURACIÓN DE HEADERS (YA HECHO EN COMPONENTES)
// ============================================================

const token = localStorage.getItem('token');
const headers = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
};

// Todos los axios.get/post/put/delete incluyen estos headers

// ============================================================
// COLORES A USAR
// ============================================================

const coloresBohe mia = {
    primaryBrown: '#817773',
    secondaryBrown: '#8B8682',
    lightTan: '#E8DCC4',
    successGreen: '#2E7D2E',
    dangerRed: '#C73E3E',
    grayText: '#ABA89E',
    darkText: '#2E2E2E',
};

// Ya están hardcodeados en los componentes

// ============================================================
// VALIDACIONES IMPLEMENTADAS
// ============================================================

/*
Frontend:
- Campo requerido: titulo, descripcion, tipo, estado
- URL válida para multimedia_url
- Multimedia requerido para IMAGEN/VIDEO
- Multimedia prohibido para TEXTO
- Descripción máx 500 caracteres

Backend:
- Model clean() valida multimedia vs tipo
- Serializer valida campos requeridos
- ViewSet solo autor puede editar/eliminar
- unique_together previene duplicados en like/save
*/

// ============================================================
// TESTING MANUAL
// ============================================================

/*
1. Abre navegador en http://localhost:3000
2. Login como profesional
3. Navega a /profesional/contenido-educativo
4. Click "Crear" → llena form → "Guardar"
5. Debería aparecer en list con estado BORRADOR
6. Click "Editar" → cambia estado a PUBLICADO → "Guardar"
7. Logout
8. Login como cliente
9. Navega a /cliente/contenido-publico
10. Debería ver el artículo
11. Click "Guardar" → debería cambiar a verde
12. Navega a /cliente/contenido-guardado → debería estar ahí
13. Click en card → DetalleContenido
14. Click "Me gusta" → contador aumenta
*/

// ============================================================
