import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { notify } from '../../utils/notificaciones';

const ProductosRecomendados = () => {
    const [productos, setProductos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [motivoSugerencia, setMotivoSugerencia] = useState('');
    const [diagnosticoInfo, setDiagnosticoInfo] = useState(null);
    const [carroCompra, setCarroCompra] = useState([]);

    useEffect(() => {
        cargarProductosRecomendados();
    }, []);

    const cargarProductosRecomendados = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/productos/sugeridos-cliente/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            setProductos(res.data.productos_sugeridos || []);
            setMotivoSugerencia(res.data.motivo_sugerencia);
            setDiagnosticoInfo({
                id: res.data.diagnostico_id,
                fecha: new Date(res.data.fecha_diagnostico).toLocaleDateString('es-AR')
            });
        } catch (error) {
            if (error.response?.status === 404) {
                setProductos([]);
                setMotivoSugerencia("No tienes diagnósticos previos");
            } else {
                console.error("Error al cargar recomendaciones", error);
                notify.error("Error al cargar productos recomendados");
            }
        } finally {
            setLoading(false);
        }
    };

    const agregarAlCarro = (producto) => {
        const existe = carroCompra.find(p => p.id === producto.id);
        if (existe) {
            setCarroCompra(carroCompra.map(p => 
                p.id === producto.id 
                    ? { ...p, cantidad: p.cantidad + 1 }
                    : p
            ));
        } else {
            setCarroCompra([...carroCompra, { ...producto, cantidad: 1 }]);
        }
        notify.success(`✅ ${producto.nombre} agregado al carrito`);
    };

    const removerDelCarro = (productoId) => {
        setCarroCompra(carroCompra.filter(p => p.id !== productoId));
    };

    const calcularTotal = () => {
        return carroCompra.reduce((total, p) => total + (parseFloat(p.precio) * p.cantidad), 0);
    };

    if (loading) {
        return (
            <div className="max-w-6xl mx-auto p-6 mt-8 min-h-screen" style={{ backgroundColor: '#F5EBE0' }}>
                <div className="text-center" style={{ color: '#8B8682' }}>
                    Cargando recomendaciones personalizadas...
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-6xl mx-auto p-6 mt-8 min-h-screen" style={{ backgroundColor: '#F5EBE0' }}>
            {/* HEADER */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold mb-2" style={{ color: '#817773' }}>
                    🛍️ Productos Recomendados para Ti
                </h1>
                {diagnosticoInfo && (
                    <p style={{ color: '#8B8682' }} className="text-sm">
                        Basado en tu diagnóstico del {diagnosticoInfo.fecha}
                    </p>
                )}
            </div>

            {/* SUGERENCIA INTELIGENTE */}
            {motivoSugerencia && (
                <div className="mb-6 p-4 rounded-lg border-l-4" style={{ backgroundColor: '#F0F5FF', borderColor: '#3E5B8E' }}>
                    <p style={{ color: '#3E5B8E' }} className="font-semibold">
                        💡 {motivoSugerencia}
                    </p>
                    <p style={{ color: '#5A7BA8' }} className="text-sm mt-1">
                        Estos productos fueron seleccionados especialmente basándose en los resultados de tu diagnóstico capilar.
                    </p>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* PRODUCTOS */}
                <div className="lg:col-span-2">
                    {productos.length === 0 ? (
                        <div className="p-8 text-center rounded-lg border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
                            <p style={{ color: '#8B8682' }} className="mb-2">
                                📋 No hay productos disponibles en este momento
                            </p>
                            <p style={{ color: '#ABA89E' }} className="text-sm">
                                Por favor realiza un diagnóstico capilar para recibir recomendaciones personalizadas
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            {productos.map((producto) => (
                                <div 
                                    key={producto.id}
                                    className="rounded-lg shadow-md overflow-hidden transition transform hover:shadow-lg hover:scale-105"
                                    style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}
                                >
                                    {/* Imagen */}
                                    {producto.imagen_url && (
                                        <img 
                                            src={producto.imagen_url} 
                                            alt={producto.nombre}
                                            className="w-full h-48 object-cover"
                                        />
                                    )}
                                    
                                    {/* Contenido */}
                                    <div className="p-4">
                                        <div className="flex justify-between items-start mb-2">
                                            <div>
                                                <h3 className="font-bold" style={{ color: '#817773' }}>
                                                    {producto.nombre}
                                                </h3>
                                                <p style={{ color: '#8B8682' }} className="text-xs">
                                                    {producto.marca}
                                                </p>
                                            </div>
                                        </div>

                                        {/* Compatibilidad */}
                                        <div className="mb-3">
                                            <span className="px-2 py-1 text-xs rounded-full" style={{ backgroundColor: '#E8EBF5', color: '#3E5B8E' }}>
                                                ✓ Compatible
                                            </span>
                                        </div>

                                        {/* Stock */}
                                        <div className="mb-3">
                                            {producto.stock > 5 ? (
                                                <span className="text-xs font-semibold" style={{ color: '#2E7D2E' }}>
                                                    ✅ En Stock ({producto.stock} disponibles)
                                                </span>
                                            ) : producto.stock > 0 ? (
                                                <span className="text-xs font-semibold" style={{ color: '#8B7500' }}>
                                                    ⚠️ Stock limitado ({producto.stock})
                                                </span>
                                            ) : (
                                                <span className="text-xs font-semibold" style={{ color: '#C73E3E' }}>
                                                    ❌ Sin stock
                                                </span>
                                            )}
                                        </div>

                                        {/* Precio */}
                                        <div className="flex justify-between items-center">
                                            <div>
                                                <p style={{ color: '#2E7D2E' }} className="text-xl font-bold">
                                                    ${parseFloat(producto.precio).toLocaleString()}
                                                </p>
                                            </div>
                                            <button
                                                onClick={() => agregarAlCarro(producto)}
                                                disabled={producto.stock <= 0}
                                                className="px-3 py-2 rounded-lg font-bold text-sm transition disabled:opacity-50"
                                                style={{ 
                                                    backgroundColor: producto.stock > 0 ? '#AB9A91' : '#D5D1CC',
                                                    color: 'white'
                                                }}
                                                onMouseEnter={(e) => {
                                                    if (producto.stock > 0) {
                                                        e.target.style.backgroundColor = '#817773';
                                                    }
                                                }}
                                                onMouseLeave={(e) => {
                                                    if (producto.stock > 0) {
                                                        e.target.style.backgroundColor = '#AB9A91';
                                                    }
                                                }}
                                            >
                                                🛒 Agregar
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* CARRITO LATERAL */}
                <div className="rounded-lg shadow-lg p-6" style={{ backgroundColor: 'white', height: 'fit-content' }}>
                    <h2 className="text-lg font-bold mb-4" style={{ color: '#817773', borderBottom: '2px solid #E3D5CA', paddingBottom: '0.5rem' }}>
                        🛒 Tu Carrito
                    </h2>

                    {carroCompra.length === 0 ? (
                        <p style={{ color: '#ABA89E' }} className="text-center py-4">
                            Tu carrito está vacío
                        </p>
                    ) : (
                        <>
                            <div className="space-y-3 mb-4 max-h-48 overflow-y-auto">
                                {carroCompra.map((producto) => (
                                    <div 
                                        key={producto.id}
                                        className="flex justify-between items-center p-3 rounded border"
                                        style={{ backgroundColor: '#F5EBE0', borderColor: '#D5D1CC' }}
                                    >
                                        <div className="flex-1">
                                            <p className="text-sm font-semibold" style={{ color: '#817773' }}>
                                                {producto.nombre}
                                            </p>
                                            <p style={{ color: '#8B8682' }} className="text-xs">
                                                ${parseFloat(producto.precio).toLocaleString()} x {producto.cantidad}
                                            </p>
                                        </div>
                                        <button
                                            onClick={() => removerDelCarro(producto.id)}
                                            className="text-red-500 hover:text-red-700 font-bold"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>

                            <div className="border-t pt-4" style={{ borderColor: '#D5D1CC' }}>
                                <div className="flex justify-between items-center mb-4">
                                    <span className="font-bold" style={{ color: '#817773' }}>Total:</span>
                                    <span className="text-2xl font-bold" style={{ color: '#2E7D2E' }}>
                                        ${calcularTotal().toLocaleString()}
                                    </span>
                                </div>
                                <button
                                    className="w-full py-2 rounded-lg font-bold text-white transition"
                                    style={{ backgroundColor: '#AB9A91' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                                >
                                    Continuar Compra
                                </button>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ProductosRecomendados;
