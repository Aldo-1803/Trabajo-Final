# 📦 Módulo de Gestión de Productos - Frontend

## 📋 Descripción General

Sistema completo de gestión de productos con:
- ✅ Catálogo de productos con SKU, marca, categoría
- ✅ Control de inventario con alertas de stock bajo
- ✅ Recomendaciones inteligentes basadas en diagnóstico del cliente
- ✅ Gestión de categorías de productos
- ✅ Compatibilidad de productos con tipo de cabello

---

## 📁 Archivos Implementados

### 1. **Páginas (Pages)**

#### `src/pages/admin/GestionProductos.js`
Panel administrativo completo para gestionar el catálogo de productos.

**Características:**
- Listado de productos con búsqueda por SKU, nombre, marca
- Crear nuevo producto con modal
- Editar producto existente
- Eliminar producto
- Visualizar alertas de stock bajo en tab separado
- Campos incluidos: SKU, nombre, marca, categoría, precio, stock, stock_minimo, compatibilidad, estado_publicacion

**Tabs:**
- 📋 **Catálogo Completo**: Todos los productos activos
- ⚠️ **Stock Bajo**: Productos con stock ≤ stock_minimo

---

#### `src/pages/admin/GestionCategorias.js`
Gestión de categorías de productos.

**Características:**
- Crear nueva categoría
- Editar categoría
- Eliminar categoría
- Activar/desactivar categorías

---

#### `src/pages/cliente/ProductosRecomendados.js`
Página de recomendaciones personalizadas para clientes.

**Características:**
- Muestra productos basados en el último diagnóstico capilar
- Carrito de compra integrado
- Cálculo automático del total
- Sistema de recomendación inteligente:
  - Cabello Dañado → Productos DANADO
  - Cuero Graso → Productos GRASO
  - Cuero Seco → Productos SECO
  - Cabello Rizado/Afro → Productos RIZADO
  - Cabello Lacio → Productos LACIO
  - Default → Productos TODO (todos los tipos)

---

### 2. **Componentes (Components)**

#### `src/components/ProductosSugerenciasCard.js`
Componente card para mostrar sugerencias en el perfil del cliente.

**Uso:**
```jsx
import ProductosSugerenciasCard from '../../components/ProductosSugerenciasCard';

// En tu perfil de cliente
<ProductosSugerenciasCard />
```

**Características:**
- Muestra 6 productos sugeridos en grid
- Botón para ver todos los recomendados
- Se oculta si no hay diagnóstico previo

---

### 3. **API Services**

#### `src/api/productosApi.js`
Servicio centralizado para todas las operaciones con productos.

**Métodos disponibles:**

```javascript
import productosApi from '../../api/productosApi';

// Productos
await productosApi.obtenerProductos()
await productosApi.obtenerProducto(id)
await productosApi.crearProducto(datos)
await productosApi.actualizarProducto(id, datos)
await productosApi.eliminarProducto(id)

// Stock
await productosApi.obtenerStockBajo()

// Recomendaciones
await productosApi.obtenerProductosSugeridos()

// Categorías
await productosApi.obtenerCategorias()
await productosApi.crearCategoria(datos)
await productosApi.actualizarCategoria(id, datos)
await productosApi.eliminarCategoria(id)
```

---

## 🔗 Rutas API Backend (Django)

```
GET    /api/gestion/productos/                      - Listar productos
POST   /api/gestion/productos/                      - Crear producto
GET    /api/gestion/productos/{id}/                 - Obtener producto
PUT    /api/gestion/productos/{id}/                 - Actualizar producto
DELETE /api/gestion/productos/{id}/                 - Eliminar producto

GET    /api/gestion/productos/stock_bajo/           - Alertas de stock bajo
GET    /api/gestion/productos/sugeridos-cliente/    - Recomendaciones personalizadas

GET    /api/gestion/categorias-productos/           - Listar categorías
POST   /api/gestion/categorias-productos/           - Crear categoría
PUT    /api/gestion/categorias-productos/{id}/      - Actualizar categoría
DELETE /api/gestion/categorias-productos/{id}/      - Eliminar categoría
```

---

## 📦 Campos de Producto

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| id | Integer | ✅ | ID único (generado) |
| sku | String | ✅ | Código único del producto |
| nombre | String | ✅ | Nombre del producto |
| marca | String | ❌ | Marca/fabricante |
| categoria | Foreign Key | ❌ | Categoría asociada |
| descripcion | Text | ❌ | Detalles del producto |
| precio | Decimal | ✅ | Precio unitario |
| stock | Integer | ✅ | Stock actual |
| stock_minimo | Integer | ❌ | Nivel para activar alerta |
| imagen_url | URL | ❌ | Link a imagen |
| estado_publicacion | Choice | ✅ | PUBLICADO / BORRADOR / DISCONTINUADO |
| compatibilidad | Choice | ✅ | TODO / LACIO / RIZADO / DANADO / GRASO / SECO |
| activo | Boolean | ✅ | Producto activo/inactivo |

---

## 🎨 Opciones de Compatibilidad

```javascript
const opcionesCompatibilidad = [
    { value: 'TODO', label: 'Todos los tipos' },
    { value: 'LACIO', label: 'Cabello Lacio' },
    { value: 'RIZADO', label: 'Cabello Rizado/Afro' },
    { value: 'DANADO', label: 'Cabello Dañado' },
    { value: 'GRASO', label: 'Cuero Cabelludo Graso' },
    { value: 'SECO', label: 'Cuero Cabelludo Seco' },
];

const opcionesEstadoPublicacion = [
    { value: 'PUBLICADO', label: '🌐 Publicado' },
    { value: 'BORRADOR', label: '📝 Borrador' },
    { value: 'DISCONTINUADO', label: '⛔ Discontinuado' },
];
```

---

## 🔄 Flujo de Recomendaciones Inteligentes

```
Cliente realiza Diagnóstico Capilar
         ↓
Sistema analiza último diagnóstico
         ↓
Mapea: estado_general, cuero_cabelludo, tipo_cabello
         ↓
Selecciona tag de compatibilidad (DANADO, GRASO, etc)
         ↓
Busca productos que coincidan + stock > 0
         ↓
Devuelve hasta 5 productos sugeridos
         ↓
Cliente ve recomendaciones personalizadas
```

---

## 📍 Integración en el Dashboard Admin

Para añadir acceso a gestión de productos en el menu:

```jsx
// En tu DashboardAdmin.js o menu de navegación
import GestionProductos from '../admin/GestionProductos';
import GestionCategorias from '../admin/GestionCategorias';

// Añadir links en el menu
<Link to="/admin-productos">📦 Gestionar Productos</Link>
<Link to="/admin-categorias">📂 Categorías</Link>

// En tu router
<Route path="/admin-productos" element={<GestionProductos />} />
<Route path="/admin-categorias" element={<GestionCategorias />} />
```

---

## 📍 Integración en Perfil de Cliente

Para mostrar sugerencias en el perfil del cliente:

```jsx
import ProductosSugerenciasCard from '../../components/ProductosSugerenciasCard';

// En tu página de perfil
<section className="mt-8">
    <ProductosSugerenciasCard />
</section>
```

O usar la página completa:
```jsx
import ProductosRecomendados from '../cliente/ProductosRecomendados';

// En tu router
<Route path="/mis-productos-sugeridos" element={<ProductosRecomendados />} />
```

---

## 🎯 Casos de Uso Implementados

1. ✅ **CU: Gestionar Catálogo de Productos**
   - Admin crea, edita, elimina productos
   - Control de stock e inventario
   - Alertas de stock bajo

2. ✅ **CU: Recomendar Productos**
   - Sistema analiza diagnóstico del cliente
   - Sugiere 5 productos compatibles
   - Filtra por stock disponible

3. ✅ **CU: Gestionar Categorías**
   - Admin organiza productos en categorías
   - Crear, editar, eliminar categorías

4. ✅ **CU: Ver Carrito de Compra**
   - Cliente agrega productos sugeridos al carrito
   - Calcula total automáticamente
   - Ready para checkout (fase 2)

---

## 🚀 Próximas Mejoras (Fase 2)

- [ ] Integración de checkout
- [ ] Pasarela de pagos
- [ ] Historial de compras
- [ ] Valoraciones de productos
- [ ] Búsqueda y filtrado avanzado
- [ ] Gestión de proveedores
- [ ] Reportes de ventas
- [ ] Integración con WhatsApp para notificaciones

---

## ⚙️ Notas de Implementación

- **Autenticación**: Todos los endpoints requieren JWT token
- **Permisos**: GestionProductos requiere IsAdminUser (implementar según necesidad)
- **Recomendaciones**: Requiere que el cliente tenga al menos 1 diagnóstico
- **Stock**: El sistema verifica automáticamente stock > 0 para mostrar botones

---

## 📞 Soporte

Para problemas:
1. Verificar que backend esté en `http://127.0.0.1:8000`
2. Verificar que JWT token sea válido
3. Revisar console del navegador para errores específicos
4. Verificar que los modelos del backend estén migrados correctamente
