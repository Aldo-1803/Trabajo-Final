import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { notify } from '../../utils/notificaciones';
import { IconBag, IconCart } from '../../components/common/Icons';

const Carrito = () => {
    const [carrito, setCarrito] = useState(null);
    const [loading, setLoading] = useState(true);
    const [cargandoPago, setCargandoPago] = useState(false);
    const [errorPago, setErrorPago] = useState('');
    const checkoutKeyRef = useRef(null);
    const navigate = useNavigate();

    useEffect(() => {
        cargarCarrito();
    }, []);

    // Debug: Verifica que los items tengan el ID correcto
    useEffect(() => {
        if (carrito?.items) {
            console.log('Items en carrito:', carrito.items.map(item => ({
                id: item.id,
                producto: item.producto,
                nombre: item.producto_nombre,
                cantidad: item.cantidad
            })));
        }
    }, [carrito]);

    const cargarCarrito = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/carrito/mi-carrito/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            setCarrito(res.data);
        } catch (error) {
            console.error('Error cargando carrito:', error);
            notify.error('Error al cargar el carrito');
        } finally {
            setLoading(false);
        }
    };

    const eliminarProducto = async (itemId) => {
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                'http://127.0.0.1:8000/api/gestion/carrito/eliminar-producto/',
                { carrito_item_id: itemId },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            notify.success('Producto eliminado del carrito');
            await cargarCarrito();
        } catch (error) {
            console.error('Error eliminando producto:', error);
            notify.error('Error al eliminar el producto');
        }
    };

    const vaciarCarrito = async () => {
        if (window.confirm('¿Estás seguro de que deseas vaciar el carrito?')) {
            try {
                const token = localStorage.getItem('access_token');
                await axios.delete(
                    'http://127.0.0.1:8000/api/gestion/carrito/vaciar/',
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
                notify.success('Carrito vaciado');
                await cargarCarrito();
            } catch (error) {
                console.error('Error vaciando carrito:', error);
                notify.error('Error al vaciar el carrito');
            }
        }
    };

    const actualizarCantidad = async (itemId, productoId, nuevaCantidad) => {
        // Validar que tenemos datos válidos
        if (!itemId || !productoId) {
            notify.error('Error: datos inválidos');
            return;
        }

        if (nuevaCantidad < 1) {
            // Si la cantidad es 0 o negativa, eliminar el producto
            setCarrito(prevCarrito => ({
                ...prevCarrito,
                items: prevCarrito.items.filter(i => i.id !== itemId)
            }));
            
            try {
                const token = localStorage.getItem('access_token');
                await axios.post(
                    'http://127.0.0.1:8000/api/gestion/carrito/eliminar-producto/',
                    { carrito_item_id: itemId },
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
            } catch (error) {
                console.error('Error eliminando producto:', error);
                await cargarCarrito();
            }
            return;
        }

        try {
            const token = localStorage.getItem('access_token');
            
            // Actualizar localmente primero para evitar parpadeo
            setCarrito(prevCarrito => ({
                ...prevCarrito,
                items: prevCarrito.items.map(i =>
                    i.id === itemId ? { ...i, cantidad: nuevaCantidad } : i
                )
            }));

            // Eliminar el item viejo
            await axios.post(
                'http://127.0.0.1:8000/api/gestion/carrito/eliminar-producto/',
                { carrito_item_id: itemId },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            
            // Agregar con la nueva cantidad y capturar el response
            const response = await axios.post(
                'http://127.0.0.1:8000/api/gestion/carrito/agregar-producto/',
                {
                    producto_id: productoId,
                    cantidad: nuevaCantidad
                },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            
            // Actualizar estado con los datos del servidor para sincronizar IDs
            // (sin parpadeo porque ya hicimos update local)
            if (response.data && response.data.items) {
                setCarrito(response.data);
            }
        } catch (error) {
            console.error('Error actualizando cantidad:', error);
            notify.error('Error al actualizar cantidad');
            // Recargar solo en caso de error para revertir UI
            await cargarCarrito();
        }
    };

    const iniciarPagoMercadoPago = async () => {
        if (!carrito?.items?.length) {
            notify.warning('El carrito está vacío');
            return;
        }

        setCargandoPago(true);
        setErrorPago('');

        try {
            const token = localStorage.getItem('access_token');
            if (!checkoutKeyRef.current) {
                checkoutKeyRef.current = window.crypto?.randomUUID?.()
                    || `checkout-${Date.now()}-${Math.random().toString(16).slice(2)}`;
            }

            const response = await axios.post(
                'http://127.0.0.1:8000/api/gestion/checkout/iniciar-pago/',
                {},
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Idempotency-Key': checkoutKeyRef.current,
                    },
                }
            );

            const urlMercadoPago = response.data?.init_point;

            if (!urlMercadoPago) {
                const uncertain = response.data?.status === 'OUTCOME_UNKNOWN';
                throw new Error(uncertain
                    ? 'El resultado todavía es incierto. Reintenta con la misma clave; no se creará otro checkout.'
                    : 'Mercado Pago no devolvió una URL válida de pago.');
            }

            checkoutKeyRef.current = null;
            window.location.href = urlMercadoPago;
        } catch (error) {
            console.error('Error en el checkout:', error);
            const retryableStatus = error.response?.data?.status === 'OUTCOME_UNKNOWN';
            const retryableConfig = error.response?.data?.error_code === 'PROVIDER_CONFIGURATION_ERROR';
            if (!retryableStatus && !retryableConfig) {
                checkoutKeyRef.current = null;
            }

            const mensajeError =
                error.response?.data?.error ||
                error.response?.data?.detail ||
                error.response?.data?.error_detail ||
                error.message ||
                'Ocurrió un error al procesar el carrito.';

            setErrorPago(mensajeError);
            notify.error(mensajeError);
        } finally {
            setCargandoPago(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
                    <p style={{ color: '#817773' }}>Cargando carrito...</p>
                </div>
            </div>
        );
    }

    const total = carrito?.items?.reduce((sum, item) => sum + (item.producto_precio * item.cantidad), 0) || 0;
    const cantidadItems = carrito?.items?.length || 0;

    return (
        <div className="min-h-screen p-4 md:p-8" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-6xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-3xl md:text-4xl font-bold mb-2" style={{ color: '#817773' }}>
                        <span className="inline-flex items-center gap-2">
                            <IconCart className="h-6 w-6" /> Tu Carrito de Compras
                        </span>
                    </h1>
                    <p style={{ color: '#8B8682' }}>
                        {cantidadItems === 0 ? 'Tu carrito está vacío' : `${cantidadItems} producto${cantidadItems !== 1 ? 's' : ''} en el carrito`}
                    </p>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* Lista de productos */}
                    <div className="lg:col-span-2">
                        {cantidadItems === 0 ? (
                            <div className="bg-white rounded-xl shadow-lg p-12 text-center">
                                <div className="flex justify-center mb-4">
                                    <IconBag className="h-12 w-12" />
                                </div>
                                <h2 className="text-2xl font-bold mb-2" style={{ color: '#817773' }}>
                                    Carrito Vacío
                                </h2>
                                <p className="mb-6" style={{ color: '#8B8682' }}>
                                    No tienes productos en tu carrito aún
                                </p>
                                <button
                                    onClick={() => navigate('/catalogo-productos')}
                                    className="px-6 py-3 rounded-lg font-bold text-white transition"
                                    style={{ backgroundColor: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                                >
                                    Explorar Productos
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {carrito?.items?.map((item) => (
                                    <div key={item.id} className="bg-white rounded-xl shadow-md p-4 md:p-6 flex gap-4">
                                        {/* Imagen */}
                                        <div className="flex-shrink-0 w-20 h-20 md:w-24 md:h-24 rounded-lg overflow-hidden" style={{ backgroundColor: '#F5F5EB' }}>
                                            {item.producto_imagen_url ? (
                                                <img
                                                    src={item.producto_imagen_url}
                                                    alt={item.producto_nombre}
                                                    className="w-full h-full object-cover"
                                                />
                                            ) : (
                                                <div className="w-full h-full flex items-center justify-center" style={{ color: '#ABA89E' }}>
                                                    Sin imagen
                                                </div>
                                            )}
                                        </div>

                                        {/* Detalles */}
                                        <div className="flex-grow">
                                            <h3 className="font-bold text-lg mb-1" style={{ color: '#817773' }}>
                                                {item.producto_nombre}
                                            </h3>
                                            <p className="text-sm mb-2" style={{ color: '#8B8682' }}>
                                                {item.producto_marca}
                                            </p>
                                            <p className="font-bold" style={{ color: '#2E7D2E' }}>
                                                ${parseFloat(item.producto_precio).toLocaleString()}
                                            </p>
                                        </div>

                                        {/* Cantidad y Total */}
                                        <div className="flex flex-col items-end justify-between">
                                            <div className="flex items-center gap-2 mb-2">
                                                <button
                                                    onClick={async () => {
                                                        if (item.cantidad > 1) {
                                                            // Actualizar localmente primero para evitar parpadeo
                                                            setCarrito({
                                                                ...carrito,
                                                                items: carrito.items.map(i =>
                                                                    i.id === item.id ? { ...i, cantidad: i.cantidad - 1 } : i
                                                                )
                                                            });
                                                            await actualizarCantidad(item.id, item.producto, item.cantidad - 1);
                                                        } else {
                                                            await eliminarProducto(item.id);
                                                        }
                                                    }}
                                                    className="px-2 py-1 border rounded transition"
                                                    style={{ borderColor: '#E8DCC4', color: '#817773' }}
                                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                                >
                                                    −
                                                </button>
                                                <input
                                                    type="number"
                                                    min="1"
                                                    value={item.cantidad}
                                                    onChange={async (e) => {
                                                        const nuevaCantidad = parseInt(e.target.value);
                                                        if (nuevaCantidad && nuevaCantidad > 0) {
                                                            // Actualizar localmente primero
                                                            setCarrito({
                                                                ...carrito,
                                                                items: carrito.items.map(i =>
                                                                    i.id === item.id ? { ...i, cantidad: nuevaCantidad } : i
                                                                )
                                                            });
                                                            await actualizarCantidad(item.id, item.producto, nuevaCantidad);
                                                        }
                                                    }}
                                                    className="w-12 px-2 py-1 border text-center rounded outline-none text-sm"
                                                    style={{ borderColor: '#E8DCC4' }}
                                                />
                                                <button
                                                    onClick={async () => {
                                                        // Actualizar localmente primero
                                                        setCarrito({
                                                            ...carrito,
                                                            items: carrito.items.map(i =>
                                                                i.id === item.id ? { ...i, cantidad: i.cantidad + 1 } : i
                                                            )
                                                        });
                                                        await actualizarCantidad(item.id, item.producto, item.cantidad + 1);
                                                    }}
                                                    className="px-2 py-1 border rounded transition"
                                                    style={{ borderColor: '#E8DCC4', color: '#817773' }}
                                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                                >
                                                    +
                                                </button>
                                            </div>
                                            <p className="font-bold text-lg mb-2" style={{ color: '#2E7D2E' }}>
                                                ${(item.producto_precio * item.cantidad).toLocaleString()}
                                            </p>
                                            <button
                                                onClick={() => eliminarProducto(item.id)}
                                                className="text-xs px-3 py-1 rounded transition text-white"
                                                style={{ backgroundColor: '#E74C3C' }}
                                                onMouseEnter={(e) => e.target.style.backgroundColor = '#C0392B'}
                                                onMouseLeave={(e) => e.target.style.backgroundColor = '#E74C3C'}
                                            >
                                                Eliminar
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Resumen */}
                    {cantidadItems > 0 && (
                        <div className="lg:col-span-1">
                            <div className="bg-white rounded-xl shadow-lg p-6 sticky top-24">
                                <h2 className="text-2xl font-bold mb-4" style={{ color: '#817773' }}>
                                    Resumen
                                </h2>

                                <div className="space-y-3 mb-6 pb-6" style={{ borderBottom: '1px solid #E8DCC4' }}>
                                    <div className="flex justify-between text-sm">
                                        <span style={{ color: '#8B8682' }}>Subtotal</span>
                                        <span>${total.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                                    </div>
                                    <div className="flex justify-between text-sm">
                                        <span style={{ color: '#8B8682' }}>Envío</span>
                                        <span>Gratis</span>
                                    </div>
                                </div>

                                <div className="flex justify-between mb-6 text-lg font-bold">
                                    <span style={{ color: '#817773' }}>Total</span>
                                    <span style={{ color: '#2E7D2E' }}>
                                        ${total.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                    </span>
                                </div>

                                {errorPago && (
                                    <div className="mb-4 p-3 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm">
                                        {errorPago}
                                    </div>
                                )}

                                <button
                                    onClick={iniciarPagoMercadoPago}
                                    disabled={cargandoPago}
                                    className="w-full px-6 py-3 rounded-lg font-bold text-white transition disabled:opacity-50 mb-3 flex items-center justify-center gap-2"
                                    style={{ backgroundColor: '#009EE3' }}
                                    onMouseEnter={(e) => !cargandoPago && (e.target.style.backgroundColor = '#0086C4')}
                                    onMouseLeave={(e) => !cargandoPago && (e.target.style.backgroundColor = '#009EE3')}
                                >
                                    <span>{cargandoPago ? 'Conectando con Mercado Pago...' : 'Pagar con Mercado Pago'}</span>
                                </button>

                                <button
                                    onClick={vaciarCarrito}
                                    className="w-full px-6 py-2 rounded-lg font-bold transition text-sm"
                                    style={{ backgroundColor: '#FFE8E8', color: '#C73E3E' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#FFD6D6'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#FFE8E8'}
                                >
                                    Vaciar Carrito
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Carrito;
