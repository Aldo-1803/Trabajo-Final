import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { notify } from '../../utils/notificaciones';
import { IconBag, IconReceipt } from '../../components/common/Icons';

const MisPedidos = () => {
    const [ordenes, setOrdenes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filtro, setFiltro] = useState('TODOS');

    const cargarOrdenes = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/ordenes-compra/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setOrdenes(res.data.results || res.data);
        } catch (error) {
            console.error('Error cargando pedidos:', error);
            notify.error('Error al cargar tus pedidos');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        cargarOrdenes();
    }, []);

    const ordenesFiltradas = useMemo(() => {
        if (filtro === 'TODOS') return ordenes;
        return ordenes.filter((orden) => orden.estado === filtro);
    }, [ordenes, filtro]);

    const badgeClasses = (estado) => {
        if (estado === 'PENDIENTE') return 'bg-yellow-100 text-yellow-800';
        if (estado === 'ESPERANDO_PAGO') return 'bg-blue-100 text-blue-800';
        if (estado === 'COMPLETADO') return 'bg-green-100 text-green-800';
        if (estado === 'CANCELADO' || estado === 'RECHAZADO') return 'bg-red-100 text-red-800';
        return 'bg-gray-100 text-gray-800';
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
                    <p style={{ color: '#817773' }}>Cargando pedidos...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-4 md:p-8" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-5xl mx-auto">
                <div className="mb-8">
                    <h1 className="text-3xl md:text-4xl font-bold mb-2" style={{ color: '#817773' }}>
                        <span className="inline-flex items-center gap-2">
                            <IconReceipt className="h-7 w-7" />
                            Mis Pedidos
                        </span>
                    </h1>
                    <p style={{ color: '#8B8682' }}>
                        Seguimiento de tus pedidos y estado de confirmacion
                    </p>
                </div>

                <div className="mb-6 flex flex-wrap gap-2">
                    {['TODOS', 'ESPERANDO_PAGO', 'COMPLETADO', 'RECHAZADO', 'CANCELADO'].map((estado) => (
                        <button
                            key={estado}
                            onClick={() => setFiltro(estado)}
                            className={`px-4 py-2 rounded-full text-sm font-semibold transition ${
                                filtro === estado ? 'bg-gray-800 text-white' : 'bg-white text-gray-700'
                            }`}
                        >
                            {estado === 'TODOS' ? 'Todos' : estado}
                        </button>
                    ))}
                </div>

                {ordenesFiltradas.length === 0 ? (
                    <div className="bg-white rounded-xl shadow-lg p-10 text-center">
                        <div className="flex justify-center mb-4">
                            <IconBag className="h-12 w-12 text-gray-400" />
                        </div>
                        <h2 className="text-xl font-bold mb-2" style={{ color: '#817773' }}>
                            No tienes pedidos aun
                        </h2>
                        <p className="text-sm" style={{ color: '#8B8682' }}>
                            Cuando realices una compra, aparecera aqui con su estado.
                        </p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {ordenesFiltradas.map((orden) => (
                            <div key={orden.id} className="bg-white rounded-xl shadow-md p-4 md:p-6">
                                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                                    <div>
                                        <p className="text-sm text-gray-500">Pedido</p>
                                        <p className="text-lg font-bold" style={{ color: '#817773' }}>{orden.codigo}</p>
                                        <p className="text-xs text-gray-500">
                                            {new Date(orden.creado_at).toLocaleDateString('es-AR')}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${badgeClasses(orden.estado)}`}>
                                            {orden.estado}
                                        </span>
                                        <span className="text-lg font-bold" style={{ color: '#2E7D2E' }}>
                                            ${parseFloat(orden.total).toFixed(2)}
                                        </span>
                                    </div>
                                </div>

                                {orden.estado === 'PENDIENTE' && (
                                    <div className="mt-4 rounded-lg p-3 text-sm" style={{ backgroundColor: '#FFF7E6', color: '#8A6D3B' }}>
                                        Esperando confirmacion del profesional.
                                    </div>
                                )}

                                {orden.estado === 'ESPERANDO_PAGO' && (
                                    <div className="mt-4 rounded-lg p-3 text-sm bg-blue-50 text-blue-800">
                                        Esperando confirmacion de Mercado Pago.
                                    </div>
                                )}

                                <div className="mt-4">
                                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Productos</h3>
                                    <div className="divide-y">
                                        {(orden.items || []).map((item) => (
                                            <div key={item.id} className="py-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                                                <div>
                                                    <p className="text-sm font-medium text-gray-800">{item.producto_nombre}</p>
                                                    <p className="text-xs text-gray-500">{item.producto_marca}</p>
                                                </div>
                                                <div className="text-sm text-gray-700">
                                                    {item.cantidad} x ${parseFloat(item.precio_historico).toFixed(2)}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default MisPedidos;
