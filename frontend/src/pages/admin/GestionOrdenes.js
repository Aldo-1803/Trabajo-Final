import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { notify } from '../../utils/notificaciones';
import PagoModal from '../../components/admin/PagoModal';

const GestionOrdenes = () => {
    const [ordenes, setOrdenes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [procesando, setProcesando] = useState({});
    const [filtro, setFiltro] = useState('TODOS');
    const [modalOrden, setModalOrden] = useState(null);
    const [modalPagoAbierto, setModalPagoAbierto] = useState(false);
    const [ordenPago, setOrdenPago] = useState(null);

    const cargarOrdenes = useCallback(async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const params = filtro === 'TODOS' ? '' : `?estado=${filtro}`;
            const res = await axios.get(`http://127.0.0.1:8000/api/gestion/ordenes-compra/${params}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setOrdenes(res.data.results || res.data);
        } catch (error) {
            console.error('Error cargando órdenes:', error);
            notify.error('Error al cargar las órdenes');
        } finally {
            setLoading(false);
        }
    }, [filtro]);

    useEffect(() => {
        cargarOrdenes();
    }, [cargarOrdenes]);

    const confirmarEntrega = async (ordenId) => {
        setProcesando(prev => ({ ...prev, [ordenId]: true }));
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.post(
                `http://127.0.0.1:8000/api/gestion/ordenes-compra/${ordenId}/confirmar_entrega/`,
                {},
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            notify.success('Entrega confirmada');
            console.log('Respuesta:', res.data);
            
            // Actualizar la orden localmente
            setOrdenes(ordenes.map(o => 
                o.id === ordenId ? { ...o, estado: 'COMPLETADO' } : o
            ));
        } catch (error) {
            console.error('Error confirmando entrega:', error);
            notify.error(error.response?.data?.error || 'Error al confirmar entrega');
        } finally {
            setProcesando(prev => ({ ...prev, [ordenId]: false }));
        }
    };

    const abrirModalPago = (orden) => {
        setOrdenPago(orden);
        setModalPagoAbierto(true);
    };

    const cerrarModalPago = () => {
        setOrdenPago(null);
        setModalPagoAbierto(false);
    };

    const cancelarOrden = async (ordenId) => {
        setProcesando(prev => ({ ...prev, [ordenId]: true }));
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.post(
                `http://127.0.0.1:8000/api/gestion/ordenes-compra/${ordenId}/cancelar/`,
                {},
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            notify.success('Orden cancelada');
            console.log('Respuesta:', res.data);

            setOrdenes(ordenes.map(o =>
                o.id === ordenId ? { ...o, estado: 'CANCELADO' } : o
            ));
        } catch (error) {
            console.error('Error cancelando orden:', error);
            notify.error(error.response?.data?.error || 'Error al cancelar la orden');
        } finally {
            setProcesando(prev => ({ ...prev, [ordenId]: false }));
        }
    };

    if (loading) {
        return <div className="p-6 text-center">Cargando órdenes...</div>;
    }

    return (
        <div className="p-6 bg-white rounded-lg">
            <h1 className="text-3xl font-bold mb-6">Gestión de Órdenes de Venta</h1>

            {/* Filtros */}
            <div className="mb-6 flex flex-wrap gap-4">
                <button
                    onClick={() => setFiltro('TODOS')}
                    className={`px-4 py-2 rounded ${filtro === 'TODOS' ? 'bg-gray-800 text-white' : 'bg-gray-200'}`}
                >
                    Todas
                </button>
                <button
                    onClick={() => setFiltro('ESPERANDO_PAGO')}
                    className={`px-4 py-2 rounded ${filtro === 'ESPERANDO_PAGO' ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
                >
                    Esperando pago
                </button>
                <button
                    onClick={() => setFiltro('COMPLETADO')}
                    className={`px-4 py-2 rounded ${filtro === 'COMPLETADO' ? 'bg-green-600 text-white' : 'bg-gray-200'}`}
                >
                    Completadas
                </button>
                <button
                    onClick={() => setFiltro('RECHAZADO')}
                    className={`px-4 py-2 rounded ${filtro === 'RECHAZADO' ? 'bg-red-600 text-white' : 'bg-gray-200'}`}
                >
                    Rechazadas
                </button>
                <button
                    onClick={() => setFiltro('CANCELADO')}
                    className={`px-4 py-2 rounded ${filtro === 'CANCELADO' ? 'bg-red-600 text-white' : 'bg-gray-200'}`}
                >
                    Canceladas
                </button>
            </div>

            {/* Tabla de órdenes */}
            <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                    <thead>
                        <tr style={{ backgroundColor: '#E8DCC4' }}>
                            <th className="p-3 text-left">ID</th>
                            <th className="p-3 text-left">Cliente</th>
                            <th className="p-3 text-right">Total</th>
                            <th className="p-3 text-center">Estado</th>
                            <th className="p-3 text-center">Fecha</th>
                            <th className="p-3 text-center">Productos</th>
                            <th className="p-3 text-center">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {ordenes.length === 0 ? (
                            <tr>
                                <td colSpan="7" className="p-4 text-center text-gray-500">
                                    No hay órdenes
                                </td>
                            </tr>
                        ) : (
                            ordenes.map(orden => (
                                <tr key={orden.id} className="border-b hover:bg-gray-50">
                                    <td className="p-3 font-bold">#{orden.id}</td>
                                    <td className="p-3">
                                        {orden.cliente ? (
                                            <div>
                                                <p className="font-semibold">
                                                    {orden.cliente_nombre || `Cliente #${orden.cliente}`}
                                                </p>
                                                <p className="text-sm text-gray-500">{orden.cliente_email}</p>
                                            </div>
                                        ) : (
                                            <span className="text-gray-400">Anónimo</span>
                                        )}
                                    </td>
                                    <td className="p-3 text-right font-bold" style={{ color: '#2E7D2E' }}>
                                        ${parseFloat(orden.total).toFixed(2)}
                                    </td>
                                    <td className="p-3 text-center">
                                        <span
                                            className={`px-3 py-1 rounded-full text-sm font-semibold ${
                                                orden.estado === 'PENDIENTE'
                                                    ? 'bg-yellow-100 text-yellow-800'
                                                    : orden.estado === 'ESPERANDO_PAGO'
                                                    ? 'bg-blue-100 text-blue-800'
                                                    : orden.estado === 'COMPLETADO'
                                                    ? 'bg-green-100 text-green-800'
                                                    : 'bg-red-100 text-red-800'
                                            }`}
                                        >
                                            {orden.estado}
                                        </span>
                                    </td>
                                    <td className="p-3 text-center text-sm">
                                        {new Date(orden.creado_at).toLocaleDateString('es-AR')}
                                    </td>
                                    <td className="p-3 text-center">
                                        <button
                                            onClick={() => setModalOrden(orden)}
                                            className="text-blue-600 hover:underline"
                                        >
                                            Ver productos
                                        </button>
                                    </td>
                                    <td className="p-3 text-center">
                                        {orden.estado === 'PENDIENTE' && (
                                            <div className="flex flex-col sm:flex-row gap-2 justify-center">
                                                <button
                                                    onClick={() => abrirModalPago(orden)}
                                                    disabled={procesando[orden.id]}
                                                    className={`px-4 py-2 rounded text-white font-semibold ${
                                                        procesando[orden.id]
                                                            ? 'bg-gray-400 cursor-not-allowed'
                                                            : 'bg-green-600 hover:bg-green-700'
                                                    }`}
                                                >
                                                    {procesando[orden.id] ? 'Procesando...' : 'Confirmar Entrega'}
                                                </button>
                                                <button
                                                    onClick={() => cancelarOrden(orden.id)}
                                                    disabled={procesando[orden.id]}
                                                    className={`px-4 py-2 rounded text-white font-semibold ${
                                                        procesando[orden.id]
                                                            ? 'bg-gray-400 cursor-not-allowed'
                                                            : 'bg-red-600 hover:bg-red-700'
                                                    }`}
                                                >
                                                    {procesando[orden.id] ? 'Procesando...' : '✕ Cancelar'}
                                                </button>
                                            </div>
                                        )}
                                        {orden.estado === 'COMPLETADO' && (
                                            <span className="text-green-600 font-semibold">✓ Completada</span>
                                        )}
                                        {orden.estado === 'ESPERANDO_PAGO' && (
                                            <span className="text-blue-600 font-semibold">Esperando pago</span>
                                        )}
                                        {orden.estado === 'RECHAZADO' && (
                                            <span className="text-red-600 font-semibold">Pago rechazado</span>
                                        )}
                                        {orden.estado === 'CANCELADO' && (
                                            <span className="text-red-600 font-semibold">✕ Cancelada</span>
                                        )}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {modalOrden && (
                <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
                        <div className="flex items-center justify-between px-6 py-4 border-b">
                            <h3 className="text-lg font-bold">Productos del pedido {modalOrden.codigo}</h3>
                            <button
                                onClick={() => setModalOrden(null)}
                                className="text-gray-500 hover:text-gray-700"
                                aria-label="Cerrar"
                            >
                                ✕
                            </button>
                        </div>
                        <div className="p-6 max-h-[60vh] overflow-y-auto">
                            {(modalOrden.items || []).length === 0 ? (
                                <p className="text-sm text-gray-500">No hay productos en esta orden.</p>
                            ) : (
                                <div className="divide-y">
                                    {modalOrden.items.map((item) => (
                                        <div key={item.id} className="py-3 flex items-center justify-between">
                                            <div>
                                                <p className="font-semibold text-gray-800">{item.producto_nombre}</p>
                                                <p className="text-xs text-gray-500">{item.producto_marca}</p>
                                            </div>
                                            <div className="text-sm text-gray-700">
                                                {item.cantidad} x ${parseFloat(item.precio_historico).toFixed(2)}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                        <div className="px-6 py-4 border-t flex justify-end">
                            <button
                                onClick={() => setModalOrden(null)}
                                className="px-4 py-2 rounded bg-gray-800 text-white hover:bg-gray-900"
                            >
                                Cerrar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <PagoModal
                isOpen={modalPagoAbierto}
                onClose={cerrarModalPago}
                origen={ordenPago}
                origenTipo="orden"
                onPagoRegistrado={() => {
                    if (ordenPago) {
                        confirmarEntrega(ordenPago.id);
                    }
                }}
            />
        </div>
    );
};

export default GestionOrdenes;
