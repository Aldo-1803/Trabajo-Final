import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { notify } from '../../utils/notificaciones';
import SmartSuggestions from '../../components/SmartSuggestions';

const CatalogoProductos = () => {
    const [productos, setProductos] = useState([]);
    const [categorias, setCategorias] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busqueda, setBusqueda] = useState('');
    const [categoriaSeleccionada, setCategoriaSeleccionada] = useState('');
    const [compatibilidadSeleccionada, setCompatibilidadSeleccionada] = useState('');
    const [productoSeleccionado, setProductoSeleccionado] = useState(null);
    const [cantidadSeleccionada, setCantidadSeleccionada] = useState(1);
    const [agregandoAlCarrito, setAgregandoAlCarrito] = useState(false);
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
    }, []);

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

    // Agregar producto al carrito
    const agregarAlCarrito = async () => {
        const token = localStorage.getItem('access_token');
        
        if (!token) {
            notify.error('Debes iniciar sesión para agregar productos');
            return;
        }

        try {
            setAgregandoAlCarrito(true);
            const res = await axios.post(
                'http://127.0.0.1:8000/api/carrito/agregar/',
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
                                            {producto.stock > 0 ? (
                                                <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}>
                                                    En Stock
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
                                                disabled={producto.stock === 0}
                                                className="px-4 py-2 rounded-lg font-bold transition disabled:opacity-50"
                                                style={{ backgroundColor: producto.stock > 0 ? '#817773' : '#ABA89E', color: '#fff' }}
                                                onMouseEnter={(e) => {
                                                    if (producto.stock > 0) e.target.style.backgroundColor = '#5A5451';
                                                }}
                                                onMouseLeave={(e) => {
                                                    if (producto.stock > 0) e.target.style.backgroundColor = '#817773';
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
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 overflow-y-auto">
                    <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full my-8">
                        <div className="p-6">
                            {/* Cerrar */}
                            <button 
                                onClick={() => setProductoSeleccionado(null)}
                                className="float-right text-xl font-bold transition"
                                style={{ color: '#8B8682' }}
                                onMouseEnter={(e) => e.target.style.color = '#817773'}
                                onMouseLeave={(e) => e.target.style.color = '#8B8682'}
                            >
                                ✕
                            </button>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 clear-right">
                                {/* Imagen */}
                                <div className="flex items-center justify-center p-4" style={{ backgroundColor: '#F5F5EB' }}>
                                    {productoSeleccionado.imagen_url ? (
                                        <img 
                                            src={productoSeleccionado.imagen_url} 
                                            alt={productoSeleccionado.nombre}
                                            className="max-w-full h-auto max-h-96"
                                        />
                                    ) : (
                                        <div style={{ color: '#ABA89E' }}>Sin imagen</div>
                                    )}
                                </div>

                                {/* Detalles */}
                                <div>
                                    <h2 className="text-2xl font-bold mb-2" style={{ color: '#817773' }}>
                                        {productoSeleccionado.nombre}
                                    </h2>
                                    <p className="text-sm mb-4" style={{ color: '#8B8682' }}>
                                        {productoSeleccionado.marca}
                                    </p>

                                    {/* SKU */}
                                    <p className="text-xs mb-4" style={{ color: '#ABA89E' }}>
                                        <strong>SKU:</strong> {productoSeleccionado.sku}
                                    </p>

                                    {/* Descripción */}
                                    {productoSeleccionado.descripcion && (
                                        <div className="mb-4">
                                            <p className="text-sm" style={{ color: '#5A5451' }}>
                                                {productoSeleccionado.descripcion}
                                            </p>
                                        </div>
                                    )}

                                    {/* Categoría */}
                                    <div className="mb-4">
                                        <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Categoría</p>
                                        <span className="inline-block px-3 py-1 text-xs rounded-full" style={{ backgroundColor: '#E8DCC4', color: '#817773' }}>
                                            {getNombreCategoria(productoSeleccionado.categoria)}
                                        </span>
                                    </div>

                                    {/* Compatibilidad */}
                                    <div className="mb-4">
                                        <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Compatible con</p>
                                        <p className="text-sm" style={{ color: '#8B8682' }}>
                                            {getEtiquetaCompatibilidad(productoSeleccionado.compatibilidad)}
                                        </p>
                                    </div>

                                    {/* Stock y Precio */}
                                    <div className="border-t pt-4 mb-4" style={{ borderColor: '#E8DCC4' }}>
                                        <div className="flex justify-between items-center mb-4">
                                            <div>
                                                <p className="text-xs font-bold mb-1" style={{ color: '#817773' }}>Disponibilidad</p>
                                                {productoSeleccionado.stock > 0 ? (
                                                    <>
                                                        <span className="text-xs font-bold px-2 py-1 rounded-full" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}>
                                                            En Stock
                                                        </span>
                                                        <p className="text-xs mt-2" style={{ color: '#8B8682' }}>
                                                            {productoSeleccionado.stock} unidades disponibles
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
                                                <p className="text-3xl font-bold" style={{ color: '#2E7D2E' }}>
                                                    ${parseFloat(productoSeleccionado.precio).toLocaleString()}
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Cantidad */}
                                    {productoSeleccionado.stock > 0 && (
                                        <div className="mb-4">
                                            <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Cantidad</p>
                                            <div className="flex items-center gap-2">
                                                <button
                                                    onClick={() => setCantidadSeleccionada(Math.max(1, cantidadSeleccionada - 1))}
                                                    className="px-3 py-2 border rounded-lg font-bold transition"
                                                    style={{ borderColor: '#E8DCC4', color: '#817773' }}
                                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                                >
                                                    −
                                                </button>
                                                <input
                                                    type="number"
                                                    min="1"
                                                    max={productoSeleccionado.stock}
                                                    value={cantidadSeleccionada}
                                                    onChange={(e) => {
                                                        const valor = parseInt(e.target.value) || 1;
                                                        setCantidadSeleccionada(Math.min(Math.max(valor, 1), productoSeleccionado.stock));
                                                    }}
                                                    className="w-16 px-2 py-2 border text-center rounded-lg outline-none"
                                                    style={{ borderColor: '#E8DCC4' }}
                                                />
                                                <button
                                                    onClick={() => setCantidadSeleccionada(Math.min(productoSeleccionado.stock, cantidadSeleccionada + 1))}
                                                    className="px-3 py-2 border rounded-lg font-bold transition"
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
                                        disabled={productoSeleccionado.stock === 0 || agregandoAlCarrito}
                                        className="w-full px-6 py-3 rounded-lg font-bold text-white transition disabled:opacity-50"
                                        style={{ backgroundColor: productoSeleccionado.stock > 0 ? '#817773' : '#ABA89E' }}
                                        onMouseEnter={(e) => {
                                            if (productoSeleccionado.stock > 0 && !agregandoAlCarrito) e.target.style.backgroundColor = '#5A5451';
                                        }}
                                        onMouseLeave={(e) => {
                                            if (productoSeleccionado.stock > 0) e.target.style.backgroundColor = '#817773';
                                        }}
                                        onClick={agregarAlCarrito}
                                    >
                                        {agregandoAlCarrito ? 'Agregando...' : productoSeleccionado.stock > 0 ? 'Agregar al Carrito' : 'Sin Stock'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default CatalogoProductos;
