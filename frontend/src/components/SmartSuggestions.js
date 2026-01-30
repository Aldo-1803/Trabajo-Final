import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { notify } from '../utils/notificaciones';

const SmartSuggestions = ({ onProductAdded = null }) => {
    const [sugerencias, setSugerencias] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [agreguandoProducto, setAgreguandoProducto] = useState(null);
    const carruselRef = useRef(null);

    // Cargar sugerencias al montar el componente
    useEffect(() => {
        cargarSugerencias();
    }, []);

    const cargarSugerencias = async () => {
        try {
            setLoading(true);
            setError('');

            const token = localStorage.getItem('access_token');
            const res = await axios.get(
                'http://127.0.0.1:8000/api/carrito/sugerencias_inteligentes/',
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            setSugerencias(res.data.sugerencias || []);

            if (res.data.sugerencias?.length === 0) {
                console.log('Sin sugerencias:', res.data.mensaje);
            }
        } catch (err) {
            console.error('Error cargando sugerencias:', err);
            // No mostrar error si simplemente no hay diagnóstico
            setError('');
        } finally {
            setLoading(false);
        }
    };

    const agregarAlCarrito = async (producto) => {
        try {
            setAgreguandoProducto(producto.id);

            const token = localStorage.getItem('access_token');
            await axios.post(
                'http://127.0.0.1:8000/api/carrito/agregar_producto/',
                {
                    producto_id: producto.id,
                    cantidad: 1
                },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            notify.success(`${producto.nombre} agregado al carrito 🛍️`);

            // Callback opcional para actualizar carrito en componente padre
            if (onProductAdded) {
                onProductAdded();
            }

            // Recargar sugerencias
            await cargarSugerencias();
        } catch (err) {
            console.error('Error al agregar:', err);
            notify.error('No pudimos agregar el producto');
        } finally {
            setAgreguandoProducto(null);
        }
    };

    const scroll = (direction) => {
        if (carruselRef.current) {
            const scrollAmount = 300;
            if (direction === 'left') {
                carruselRef.current.scrollBy({ left: -scrollAmount, behavior: 'smooth' });
            } else {
                carruselRef.current.scrollBy({ left: scrollAmount, behavior: 'smooth' });
            }
        }
    };

    // No mostrar si no hay sugerencias
    if (!loading && sugerencias.length === 0) {
        return null;
    }

    return (
        <div className="mt-8 bg-gradient-to-r from-amber-50 to-orange-50 rounded-xl shadow-lg p-6 border border-amber-200">
            {/* Header */}
            <div className="mb-6">
                <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                    ✨ ¡Completa tu rutina personalizada!
                </h2>
                <p className="text-sm text-gray-600 mt-1">
                    Productos recomendados según tu diagnóstico capilar
                </p>
            </div>

            {/* Loading State */}
            {loading && (
                <div className="flex justify-center items-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-amber-600"></div>
                    <span className="ml-2 text-gray-600">Cargando sugerencias...</span>
                </div>
            )}

            {/* Error State */}
            {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
                    {error}
                </div>
            )}

            {/* Carrusel de Productos */}
            {!loading && sugerencias.length > 0 && (
                <div className="relative">
                    {/* Botones de navegación */}
                    {sugerencias.length > 3 && (
                        <>
                            <button
                                onClick={() => scroll('left')}
                                className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-white rounded-full p-2 shadow-lg hover:bg-gray-100 transition -ml-4"
                                aria-label="Desplazar izquierda"
                            >
                                <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                                </svg>
                            </button>

                            <button
                                onClick={() => scroll('right')}
                                className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-white rounded-full p-2 shadow-lg hover:bg-gray-100 transition -mr-4"
                                aria-label="Desplazar derecha"
                            >
                                <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                </svg>
                            </button>
                        </>
                    )}

                    {/* Contenedor del carrusel */}
                    <div
                        ref={carruselRef}
                        className="flex gap-4 overflow-x-auto scroll-smooth pb-2 px-2"
                        style={{ scrollBehavior: 'smooth' }}
                    >
                        {sugerencias.map((producto) => (
                            <div
                                key={producto.id}
                                className="flex-shrink-0 w-72 bg-white rounded-lg shadow-md hover:shadow-lg transition overflow-hidden border border-gray-100"
                            >
                                {/* Imagen */}
                                {producto.imagen_url ? (
                                    <img
                                        src={producto.imagen_url}
                                        alt={producto.nombre}
                                        className="w-full h-40 object-cover"
                                    />
                                ) : (
                                    <div className="w-full h-40 bg-gradient-to-br from-amber-100 to-orange-100 flex items-center justify-center">
                                        <span className="text-4xl">🧴</span>
                                    </div>
                                )}

                                {/* Contenido */}
                                <div className="p-4">
                                    {/* Marca y nombre */}
                                    <p className="text-xs text-amber-600 font-semibold uppercase tracking-wide">
                                        {producto.marca || 'Bohemia'}
                                    </p>
                                    <h3 className="text-sm font-bold text-gray-900 mt-1 line-clamp-2">
                                        {producto.nombre}
                                    </h3>

                                    {/* Descripción */}
                                    {producto.descripcion && (
                                        <p className="text-xs text-gray-600 mt-2 line-clamp-2">
                                            {producto.descripcion}
                                        </p>
                                    )}

                                    {/* Precio y stock */}
                                    <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
                                        <div>
                                            <p className="text-lg font-bold text-amber-600">
                                                ${producto.precio}
                                            </p>
                                            <p className="text-xs text-gray-500">
                                                Stock: {producto.stock}
                                            </p>
                                        </div>

                                        {/* Botón Agregar */}
                                        <button
                                            onClick={() => agregarAlCarrito(producto)}
                                            disabled={agreguandoProducto === producto.id || producto.stock === 0}
                                            className={`px-3 py-2 rounded-lg font-semibold text-sm transition whitespace-nowrap ${
                                                producto.stock === 0
                                                    ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                                                    : agreguandoProducto === producto.id
                                                    ? 'bg-gray-400 text-white cursor-wait'
                                                    : 'bg-gradient-to-r from-amber-500 to-orange-500 text-white hover:from-amber-600 hover:to-orange-600 shadow-md'
                                            }`}
                                        >
                                            {agreguandoProducto === producto.id ? (
                                                <>
                                                    <span className="inline-block animate-spin mr-1">⏳</span>
                                                    Agregando...
                                                </>
                                            ) : producto.stock === 0 ? (
                                                'Sin stock'
                                            ) : (
                                                '+ Agregar'
                                            )}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default SmartSuggestions;
