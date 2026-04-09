import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { notify } from '../../utils/notificaciones';
import { IconSearch, IconX } from '../../components/common/Icons';
import SmartSuggestions from '../../components/SmartSuggestions';

const CatalogoProductos = () => {
    const [productos, setProductos] = useState([]);
    const [categorias, setCategorias] = useState([]);
    const [combos, setCombos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busqueda, setBusqueda] = useState('');
    const [categoriaSeleccionada, setCategoriaSeleccionada] = useState('');
    const [compatibilidadSeleccionada, setCompatibilidadSeleccionada] = useState('');
    const [productoSeleccionado, setProductoSeleccionado] = useState(null);
    const [cantidadSeleccionada, setCantidadSeleccionada] = useState(1);
    const [agregandoAlCarrito, setAgregandoAlCarrito] = useState(false);
    const [agregandoComboId, setAgregandoComboId] = useState(null);
    const [imagenZoom, setImagenZoom] = useState(null);
    const navigate = useNavigate();

    const opcionesCompatibilidad = [
        { value: 'TODO', label: 'Todos los tipos' },
        { value: 'LACIO', label: 'Cabello Lacio' },
        { value: 'RIZADO', label: 'Cabello Rizado/Afro' },
        { value: 'DANADO', label: 'Cabello Dañado' },
        { value: 'GRASO', label: 'Cuero Cabelludo Graso' },
        { value: 'SECO', label: 'Cuero Cabelludo Seco' },
    ];

    useEffect(() => {
        cargarProductos();
        cargarCategorias();
        cargarCombos();
        
        // Agregar listener para ESC en modal de zoom
        const handleKeyPress = (e) => {
            if (e.key === 'Escape' && imagenZoom) {
                setImagenZoom(null);
            }
        };
        window.addEventListener('keydown', handleKeyPress);
        return () => window.removeEventListener('keydown', handleKeyPress);
    }, [imagenZoom]);

    const cargarProductos = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/productos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            // Filtrar solo productos publicados y activos
            const productosActivos = res.data.filter(p => p.estado_publicacion === 'PUBLICADO' && p.activo);
            setProductos(productosActivos);
        } catch (error) {
            console.error("Error al cargar productos", error);
            notify.error("Error al cargar el catálogo");
        } finally {
            setLoading(false);
        }
    };

    const cargarCategorias = async () => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/categorias-productos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setCategorias(res.data.filter(c => c.activo));
        } catch (error) {
            console.error("Error al cargar categorías", error);
        }
    };

    const cargarCombos = async () => {
        try {
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/promociones/');
            const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
            const combosActivos = data.filter(
                (promo) => promo.tipo === 'COMBO' && promo.is_active && promo.estado_sugerencia !== 'PENDIENTE'
            );
            setCombos(combosActivos);
        } catch (error) {
            console.error('Error al cargar combos', error);
        }
    };

    // Agregar producto al carrito
    const agregarAlCarrito = async () => {
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            notify.error('Debes iniciar sesión para agregar productos');
            return;
        }

        try {
            setAgregandoAlCarrito(true);
            await axios.post(
                'http://127.0.0.1:8000/api/gestion/carrito/agregar-producto/',
                {
                    producto_id: productoSeleccionado.id,
                    cantidad: cantidadSeleccionada
                },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            notify.success(`${cantidadSeleccionada} unidad/es agregada/s al carrito`);
            setProductoSeleccionado(null);
            setCantidadSeleccionada(1);
            cargarProductos();
        } catch (error) {
            console.error('Error al agregar al carrito:', error);
            if (error.response?.status === 400) {
                notify.error(error.response.data.error || 'No hay suficiente stock');
            } else {
                notify.error('Error al agregar al carrito');
            }
        } finally {
            setAgregandoAlCarrito(false);
        }
    };

    // Filtrado de productos
    const productosFiltrados = productos.filter(p => {
        const coincideBusqueda = p.nombre.toLowerCase().includes(busqueda.toLowerCase()) || 
                               p.marca.toLowerCase().includes(busqueda.toLowerCase());
        const coincideCategoria = !categoriaSeleccionada || p.categoria === parseInt(categoriaSeleccionada);
        const coincideCompatibilidad = !compatibilidadSeleccionada || 
                                      p.compatibilidad === compatibilidadSeleccionada || 
                                      p.compatibilidad === 'TODO';
        return coincideBusqueda && coincideCategoria && coincideCompatibilidad;
    });

    const getNombreCategoria = (id) => {
        const cat = categorias.find(c => c.id === id);
        return cat ? cat.nombre : 'Sin categoría';
    };

    const getEtiquetaCompatibilidad = (valor) => {
        const opt = opcionesCompatibilidad.find(o => o.value === valor);
        return opt ? opt.label : valor;
    };

    const getNombreProducto = (id) => {
        const prod = productos.find((p) => p.id === id);
        return prod ? prod.nombre : 'Producto';
    };

    const getStockDisponible = (prod) => {
        const stockDisponible = Number(prod?.stock_disponible);
        if (Number.isFinite(stockDisponible)) {
            return stockDisponible;
        }
        const stockReal = Number(prod?.stock_real || 0);
        const stockComprometido = Number(prod?.stock_comprometido || 0);
        return Math.max(0, stockReal - stockComprometido);
    };

    const getProductosCombo = (combo) => {
        const ids = Array.isArray(combo?.productos) ? combo.productos : [];
        return ids.map((id) => productos.find((p) => p.id === id)).filter(Boolean);
    };

    const agregarComboAlCarrito = async (combo) => {
        const token = localStorage.getItem('access_token');

        if (!token) {
            notify.error('Debes iniciar sesión para agregar combos');
            return;
        }

        const productosCombo = getProductosCombo(combo);
        if (productosCombo.length === 0) {
            notify.error('No se encontraron productos para este combo');
            return;
        }

        const productoSinStock = productosCombo.find((prod) => getStockDisponible(prod) < 1);
        if (productoSinStock) {
            notify.error(`Sin stock para: ${productoSinStock.nombre}`);
            return;
        }

        try {
            setAgregandoComboId(combo.id);
            for (const prod of productosCombo) {
                await axios.post(
                    'http://127.0.0.1:8000/api/gestion/carrito/agregar-producto/',
                    { producto_id: prod.id, cantidad: 1 },
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
            }
            notify.success('Combo agregado al carrito');
            cargarProductos();
        } catch (error) {
            console.error('Error al agregar combo al carrito:', error);
            if (error.response?.status === 400) {
                notify.error(error.response.data.error || 'No hay suficiente stock');
            } else {
                notify.error('Error al agregar combo');
            }
        } finally {
            setAgregandoComboId(null);
        }
    };

    const stockDisponibleSeleccionado = productoSeleccionado
        ? getStockDisponible(productoSeleccionado)
        : 0;

    return (
        <div className="min-h-screen" style={{ backgroundColor: '#F5F5EB' }}>
            {/* HEADER */}
            <div className="bg-white shadow-md border-b" style={{ borderColor: '#E8DCC4' }}>
                <div className="max-w-7xl mx-auto p-6">
                    <div className="flex justify-between items-center">
                        <div>
                            <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Catálogo de Productos</h1>
                            <p className="text-xs mt-1 font-medium" style={{ color: '#8B8682' }}>Descubre nuestros productos recomendados</p>
                        </div>
                        <button 
                            onClick={() => navigate('/perfil')}
                            className="px-4 py-2 rounded-lg font-bold transition"
                            style={{ backgroundColor: '#E8DCC4', color: '#817773' }}
                            onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                            onMouseLeave={(e) => e.target.style.backgroundColor = '#E8DCC4'}
                        >
                            Volver
                        </button>
                    </div>
                </div>
            </div>

            {/* CONTENIDO */}
            <div className="max-w-7xl mx-auto p-6">
                {combos.length > 0 && (
                    <div className="mb-8 bg-white rounded-lg shadow-md p-6 border" style={{ borderColor: '#E8DCC4' }}>
                        <h2 className="text-lg font-bold mb-4" style={{ color: '#817773' }}>Combos Publicados</h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {combos.map((combo) => {
                                const productosCombo = getProductosCombo(combo);
                                const totalCombo = productosCombo.reduce(
                                    (sum, prod) => sum + Number(prod.precio || 0),
                                    0
                                );
                                const totalConDescuento = totalCombo * (1 - Number(combo.descuento_porcentaje || 0) / 100);
                                const sinStock = productosCombo.some((prod) => getStockDisponible(prod) < 1);

                                return (
                                    <div
                                        key={combo.id}
                                        className="rounded-lg border p-4 shadow-sm"
                                        style={{ borderColor: '#E8DCC4', backgroundColor: '#FAF7F5' }}
                                    >
                                        <h3 className="text-lg font-bold" style={{ color: '#817773' }}>{combo.nombre}</h3>
                                        <p className="text-sm mt-1" style={{ color: '#8B8682' }}>{combo.descripcion}</p>
                                        <div className="mt-3 text-sm font-semibold" style={{ color: '#2E7D2E' }}>
                                            {combo.descuento_porcentaje}% de descuento
                                        </div>
                                        <div className="mt-3 text-xs" style={{ color: '#5A5451' }}>
                                            {(combo.productos || []).map(getNombreProducto).join(', ')}
                                        </div>
                                        {productosCombo.length > 0 && (
                                            <div className="mt-4 text-sm" style={{ color: '#817773' }}>
                                                <div>
                                                    Total: <strong>${totalCombo.toLocaleString()}</strong>
                                                </div>
                                                <div style={{ color: '#2E7D2E' }}>
                                                    Con descuento: <strong>${Math.round(totalConDescuento).toLocaleString()}</strong>
                                                </div>
                                            </div>
                                        )}
                                        <button
                                            disabled={sinStock || agregandoComboId === combo.id}
                                            className="mt-4 w-full px-4 py-2 rounded-lg font-bold text-white transition disabled:opacity-50"
                                            style={{ backgroundColor: sinStock ? '#ABA89E' : '#817773' }}
                                            onMouseEnter={(e) => {
                                                if (!sinStock && agregandoComboId !== combo.id) e.target.style.backgroundColor = '#5A5451';
                                            }}
                                            onMouseLeave={(e) => {
                                                if (!sinStock) e.target.style.backgroundColor = '#817773';
                                            }}
                                            onClick={() => agregarComboAlCarrito(combo)}
                                        >
                                            {agregandoComboId === combo.id
                                                ? 'Agregando...'
                                                : sinStock
                                                    ? 'Sin Stock'
                                                    : 'Agregar combo al carrito'}
                                        </button>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
                {/* FILTROS */}
                <div className="bg-white rounded-lg shadow-md p-6 mb-6 border" style={{ borderColor: '#E8DCC4' }}>
                    <h2 className="text-lg font-bold mb-4" style={{ color: '#817773' }}>Filtrar Productos</h2>
                    
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        {/* Búsqueda */}
                        <div>
                            <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>Buscar</label>
                            <input 
                                type="text"
                                placeholder="Producto o marca..."
                                className="w-full p-2 border rounded-lg outline-none transition"
                                style={{ borderColor: '#D5D1CC' }}
                                value={busqueda}
                                onChange={(e) => setBusqueda(e.target.value)}
                                onFocus={(e) => e.target.style.borderColor = '#817773'}
                                onBlur={(e) => e.target.style.borderColor = '#D5D1CC'}
                            />
                        </div>

                        {/* Categoría */}
                        <div>
                            <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>Categoría</label>
                            <select 
                                className="w-full p-2 border rounded-lg outline-none"
                                style={{ borderColor: '#D5D1CC' }}
                                value={categoriaSeleccionada}
                                onChange={(e) => setCategoriaSeleccionada(e.target.value)}
                            >
                                <option value="">Todas</option>
                                {categorias.map(cat => (
                                    <option key={cat.id} value={cat.id}>{cat.nombre}</option>
                                ))}
                            </select>
                        </div>

                        {/* Compatibilidad */}
                        <div>
                            <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>Compatibilidad</label>
                            <select 
                                className="w-full p-2 border rounded-lg outline-none"
                                style={{ borderColor: '#D5D1CC' }}
                                value={compatibilidadSeleccionada}
                                onChange={(e) => setCompatibilidadSeleccionada(e.target.value)}
                            >
                                <option value="">Todas</option>
                                {opcionesCompatibilidad.map(opt => (
                                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                            </select>
                        </div>

                        {/* Limpiar filtros */}
                        <div className="flex items-end">
                            <button 
                                onClick={() => {
                                    setBusqueda('');
                                    setCategoriaSeleccionada('');
                                    setCompatibilidadSeleccionada('');
                                }}
                                className="w-full px-4 py-2 rounded-lg font-bold transition"
                                style={{ backgroundColor: '#E8DCC4', color: '#817773' }}
                                onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                                onMouseLeave={(e) => e.target.style.backgroundColor = '#E8DCC4'}
                            >
                                Limpiar Filtros
                            </button>
                        </div>
                    </div>
                </div>

                {/* RESULTADOS */}
                {loading ? (
                    <div className="text-center py-12" style={{ color: '#8B8682' }}>
                        <p className="text-lg font-medium">Cargando catálogo...</p>
                    </div>
                ) : productosFiltrados.length === 0 ? (
                    <div className="text-center py-12 bg-white rounded-lg shadow-md">
                        <p className="text-lg font-medium" style={{ color: '#8B8682' }}>No se encontraron productos</p>
                        <p className="text-sm mt-2" style={{ color: '#ABA89E' }}>Intenta con otros filtros</p>
                    </div>
                ) : (
                    <>
                        <p className="mb-4 font-medium" style={{ color: '#8B8682' }}>
                            Mostrando {productosFiltrados.length} producto{productosFiltrados.length !== 1 ? 's' : ''}
                        </p>

                        {/* GRID DE PRODUCTOS */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {productosFiltrados.map((producto) => (
                                <div 
                                    key={producto.id} 
                                    className="bg-white rounded-lg shadow-md overflow-hidden border transition-all duration-300 hover:shadow-lg cursor-pointer"
                                    style={{ borderColor: '#E8DCC4' }}
                                    onClick={() => setProductoSeleccionado(producto)}
                                >
                                    {/* Imagen */}
                                    <div 
                                        className="w-full h-48 flex items-center justify-center overflow-hidden"
                                        style={{ backgroundColor: '#F5F5EB' }}
                                    >
                                        {producto.imagen_url ? (
                                            <img 
                                                src={producto.imagen_url} 
                                                alt={producto.nombre}
                                                className="w-full h-full object-cover hover:scale-105 transition-transform"
                                            />
                                        ) : (
                                            <div className="text-center py-8" style={{ color: '#ABA89E' }}>
                                                <p className="text-sm">Sin imagen</p>
                                            </div>
                                        )}
                                    </div>

                                    {/* Contenido */}
                                    <div className="p-4">
                                        <h3 className="text-lg font-bold mb-1" style={{ color: '#817773' }}>{producto.nombre}</h3>
                                        <p className="text-xs mb-2" style={{ color: '#8B8682' }}>{producto.marca}</p>
                                        
                                        {/* Categoría */}
                                        <div className="mb-3">
                                            <span className="inline-block px-2 py-1 text-xs rounded-full" style={{ backgroundColor: '#E8DCC4', color: '#817773' }}>
                                                {getNombreCategoria(producto.categoria)}
                                            </span>
                                        </div>

                                        {/* Compatibilidad */}
                                        <p className="text-xs mb-3" style={{ color: '#8B8682' }}>
                                            <strong>Compatible:</strong> {getEtiquetaCompatibilidad(producto.compatibilidad)}
                                        </p>

                                        {/* Stock */}
                                        <div className="mb-4">
                                            {getStockDisponible(producto) > 0 ? (
                                                <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}>
                                                    En Stock ({getStockDisponible(producto)})
                                                </span>
                                            ) : (
                                                <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: '#FFE8E8', color: '#C73E3E' }}>
                                                    Agotado
                                                </span>
                                            )}
                                        </div>

                                        {/* Precio */}
                                        <div className="flex justify-between items-center pt-3 border-t" style={{ borderColor: '#E8DCC4' }}>
                                            <span className="text-2xl font-bold" style={{ color: '#2E7D2E' }}>
                                                ${parseFloat(producto.precio).toLocaleString()}
                                            </span>
                                            <button 
                                                disabled={getStockDisponible(producto) === 0}
                                                className="px-4 py-2 rounded-lg font-bold transition disabled:opacity-50"
                                                style={{ backgroundColor: getStockDisponible(producto) > 0 ? '#817773' : '#ABA89E', color: '#fff' }}
                                                onMouseEnter={(e) => {
                                                    if (getStockDisponible(producto) > 0) e.target.style.backgroundColor = '#5A5451';
                                                }}
                                                onMouseLeave={(e) => {
                                                    if (getStockDisponible(producto) > 0) e.target.style.backgroundColor = '#817773';
                                                }}
                                            >
                                                Ver
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </>
                )}

                {/* SMART SUGGESTIONS */}
                <SmartSuggestions onProductAdded={cargarProductos} />
            </div>

            {/* MODAL DETALLE */}
            {productoSeleccionado && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start md:items-center justify-center p-2 md:p-4 z-50 overflow-y-auto">
                    <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full my-auto md:my-8 max-h-[95vh] md:max-h-[90vh] overflow-y-auto">
                        <div className="p-4 md:p-8">
                            {/* Cerrar */}
                            <button 
                                onClick={() => {
                                    setProductoSeleccionado(null);
                                    setImagenZoom(null);
                                }}
                                className="float-right text-2xl font-bold transition sticky top-0 right-0 z-10"
                                style={{ color: '#8B8682' }}
                                onMouseEnter={(e) => e.target.style.color = '#817773'}
                                onMouseLeave={(e) => e.target.style.color = '#8B8682'}
                            >
                                <IconX className="h-5 w-5" />
                            </button>

                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-8 clear-right">
                                {/* Imagen - Responsiva */}
                                <div className="lg:col-span-2">
                                    {/* Imagen Principal con Zoom */}
                                    <div className="flex items-center justify-center p-2 md:p-4 mb-3 rounded-lg relative group cursor-zoom-in" 
                                        style={{ backgroundColor: '#F5F5EB', minHeight: '250px', maxHeight: '400px' }}
                                        onClick={() => productoSeleccionado.imagen_url && setImagenZoom(productoSeleccionado.imagen_url)}>
                                        {productoSeleccionado.imagen_url ? (
                                            <>
                                                <img 
                                                    src={productoSeleccionado.imagen_url} 
                                                    alt={productoSeleccionado.nombre}
                                                    className="max-w-full h-auto max-h-72 md:max-h-96 rounded-lg"
                                                />
                                                <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-20 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <span className="text-white text-center">
                                                        <div className="flex items-center justify-center mb-2">
                                                            <IconSearch className="h-6 w-6" />
                                                        </div>
                                                        <div className="text-sm">Click para ampliar</div>
                                                    </span>
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: '#ABA89E' }}>Sin imagen</div>
                                        )}
                                    </div>
                                    
                                    {/* Galería de imágenes adicionales - Responsive */}
                                    {productoSeleccionado.imagenes && productoSeleccionado.imagenes.length > 1 && (
                                        <div className="mt-2 md:mt-4">
                                            <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>
                                                Galería ({productoSeleccionado.imagenes.length} imagen{productoSeleccionado.imagenes.length > 1 ? 'es' : ''})
                                            </p>
                                            <div className="grid grid-cols-4 md:grid-cols-5 gap-2">
                                                {productoSeleccionado.imagenes.map((img, idx) => (
                                                    <div
                                                        key={img.id}
                                                        className="cursor-pointer border-2 p-1 rounded-lg transition hover:border-opacity-100 hover:scale-105"
                                                        style={{
                                                            borderColor: productoSeleccionado.imagen_url === img.imagen_url ? '#817773' : '#E8DCC4'
                                                        }}
                                                        onClick={() => {
                                                            setProductoSeleccionado({
                                                                ...productoSeleccionado,
                                                                imagen_url: img.imagen_url
                                                            });
                                                        }}
                                                    >
                                                        <img
                                                            src={img.imagen_url}
                                                            alt={`${productoSeleccionado.nombre} ${idx + 1}`}
                                                            className="w-full h-16 object-cover rounded"
                                                        />
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Detalles - Responsivo */}
                                <div className="lg:col-span-1">
                                    <h2 className="text-xl md:text-2xl font-bold mb-2" style={{ color: '#817773' }}>
                                        {productoSeleccionado.nombre}
                                    </h2>
                                    <p className="text-xs md:text-sm mb-4" style={{ color: '#8B8682' }}>
                                        {productoSeleccionado.marca}
                                    </p>

                                    {/* SKU */}
                                    <p className="text-xs mb-4" style={{ color: '#ABA89E' }}>
                                        <strong>SKU:</strong> {productoSeleccionado.sku}
                                    </p>

                                    {/* Descripción */}
                                    {productoSeleccionado.descripcion && (
                                        <div className="mb-4 max-h-24 overflow-y-auto">
                                            <p className="text-xs md:text-sm" style={{ color: '#5A5451' }}>
                                                {productoSeleccionado.descripcion}
                                            </p>
                                        </div>
                                    )}

                                    {/* Categoría */}
                                    <div className="mb-3">
                                        <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Categoría</p>
                                        <span className="inline-block px-3 py-1 text-xs rounded-full" style={{ backgroundColor: '#E8DCC4', color: '#817773' }}>
                                            {getNombreCategoria(productoSeleccionado.categoria)}
                                        </span>
                                    </div>

                                    {/* Compatibilidad */}
                                    <div className="mb-3">
                                        <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Compatible con</p>
                                        <p className="text-xs md:text-sm" style={{ color: '#8B8682' }}>
                                            {getEtiquetaCompatibilidad(productoSeleccionado.compatibilidad)}
                                        </p>
                                    </div>

                                    {/* Stock y Precio */}
                                    <div className="border-t pt-4 mb-4" style={{ borderColor: '#E8DCC4' }}>
                                        <div className="mb-4">
                                            <p className="text-xs font-bold mb-1" style={{ color: '#817773' }}>Disponibilidad</p>
                                            {stockDisponibleSeleccionado > 0 ? (
                                                <>
                                                    <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}>
                                                        En Stock
                                                    </span>
                                                    <p className="text-xs mt-2" style={{ color: '#8B8682' }}>
                                                        {stockDisponibleSeleccionado} unidades disponibles
                                                    </p>
                                                </>
                                            ) : (
                                                <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: '#FFE8E8', color: '#C73E3E' }}>
                                                    Agotado
                                                </span>
                                            )}
                                        </div>
                                        <div>
                                            <p className="text-xs font-bold mb-1" style={{ color: '#817773' }}>Precio</p>
                                            <p className="text-2xl md:text-3xl font-bold" style={{ color: '#2E7D2E' }}>
                                                ${parseFloat(productoSeleccionado.precio).toLocaleString()}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Cantidad */}
                                    {stockDisponibleSeleccionado > 0 && (
                                        <div className="mb-4">
                                            <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Cantidad</p>
                                            <div className="flex items-center gap-2">
                                                <button
                                                    onClick={() => setCantidadSeleccionada(Math.max(1, cantidadSeleccionada - 1))}
                                                    className="px-3 py-2 border rounded-lg font-bold transition text-sm"
                                                    style={{ borderColor: '#E8DCC4', color: '#817773' }}
                                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                                >
                                                    −
                                                </button>
                                                <input
                                                    type="number"
                                                    min="1"
                                                    max={stockDisponibleSeleccionado}
                                                    value={cantidadSeleccionada}
                                                    onChange={(e) => {
                                                        const valor = parseInt(e.target.value) || 1;
                                                        setCantidadSeleccionada(Math.min(Math.max(valor, 1), stockDisponibleSeleccionado));
                                                    }}
                                                    className="w-16 px-2 py-2 border text-center rounded-lg outline-none text-sm"
                                                    style={{ borderColor: '#E8DCC4' }}
                                                />
                                                <button
                                                    onClick={() => setCantidadSeleccionada(Math.min(stockDisponibleSeleccionado, cantidadSeleccionada + 1))}
                                                    className="px-3 py-2 border rounded-lg font-bold transition text-sm"
                                                    style={{ borderColor: '#E8DCC4', color: '#817773' }}
                                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                                >
                                                    +
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Botón Agregar al Carrito */}
                                    <button 
                                        disabled={stockDisponibleSeleccionado === 0 || agregandoAlCarrito}
                                        className="w-full px-6 py-3 rounded-lg font-bold text-white transition disabled:opacity-50 text-sm md:text-base"
                                        style={{ backgroundColor: stockDisponibleSeleccionado > 0 ? '#817773' : '#ABA89E' }}
                                        onMouseEnter={(e) => {
                                            if (stockDisponibleSeleccionado > 0 && !agregandoAlCarrito) e.target.style.backgroundColor = '#5A5451';
                                        }}
                                        onMouseLeave={(e) => {
                                            if (stockDisponibleSeleccionado > 0) e.target.style.backgroundColor = '#817773';
                                        }}
                                        onClick={agregarAlCarrito}
                                    >
                                        {agregandoAlCarrito ? 'Agregando...' : stockDisponibleSeleccionado > 0 ? 'Agregar al Carrito' : 'Sin Stock'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* MODAL ZOOM IMAGEN */}
            {imagenZoom && (
                <div className="fixed inset-0 bg-black bg-opacity-90 flex items-center justify-center p-4 z-50" onClick={() => setImagenZoom(null)}>
                    <div className="relative max-w-4xl max-h-[90vh] flex items-center justify-center">
                        <img 
                            src={imagenZoom} 
                            alt="Zoom"
                            className="max-w-full max-h-[85vh] object-contain rounded-lg"
                            onClick={(e) => e.stopPropagation()}
                        />
                        <button 
                            onClick={() => setImagenZoom(null)}
                            className="absolute top-4 right-4 text-3xl font-bold text-white transition hover:scale-110"
                            title="Cerrar (ESC)"
                        >
                            <IconX className="h-6 w-6" />
                        </button>
                        <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 text-white text-sm bg-black bg-opacity-50 px-4 py-2 rounded-lg">
                            Click para cerrar o presiona ESC
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default CatalogoProductos;
