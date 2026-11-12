import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import { notify } from '../../utils/notificaciones';
import {
    canConfirmOrderDelivery,
    getOrderPresentation,
    ORDER_STATES,
} from '../../utils/orderStatus';


const FILTERS = [
    {value: 'TODOS', label: 'Todas'},
    {value: ORDER_STATES.PENDING, label: 'Pendientes'},
    {value: ORDER_STATES.AWAITING_PAYMENT, label: 'Pago pendiente'},
    {value: ORDER_STATES.PAID, label: 'Pagadas por entregar'},
    {value: ORDER_STATES.COMPLETED, label: 'Entregadas'},
    {value: ORDER_STATES.REJECTED, label: 'Rechazadas'},
    {value: ORDER_STATES.CANCELLED, label: 'Canceladas'},
];


const GestionOrdenes = () => {
    const { hasPermission } = useSession();
    const canManageStock = hasPermission('gestion.manage_stock');
    const [orders, setOrders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [processing, setProcessing] = useState({});
    const [actionErrors, setActionErrors] = useState({});
    const [filter, setFilter] = useState('TODOS');
    const [modalOrder, setModalOrder] = useState(null);
    const inFlight = useRef(new Set());

    const loadOrders = useCallback(async ({silent = false} = {}) => {
        if (!silent) setLoading(true);
        try {
            const params = filter === 'TODOS' ? {} : {estado: filter};
            const response = await axios.get('/api/gestion/ordenes-compra/', {
                params,
            });
            setOrders(response.data.results || response.data);
        } catch (error) {
            console.error('Error cargando órdenes:', error);
            notify.error('Error al cargar las órdenes');
        } finally {
            if (!silent) setLoading(false);
        }
    }, [filter]);

    useEffect(() => {
        loadOrders();
    }, [loadOrders]);

    const runAction = async (orderId, action, request) => {
        const actionKey = `${action}:${orderId}`;
        if (inFlight.current.has(actionKey)) return;
        inFlight.current.add(actionKey);
        setProcessing((current) => ({...current, [orderId]: action}));
        setActionErrors((current) => ({...current, [orderId]: ''}));
        try {
            const response = await request();
            const updated = response.data?.orden;
            if (updated) {
                setOrders((current) => current.map(
                    (order) => order.id === orderId ? updated : order
                ));
            }
            return response;
        } catch (error) {
            const status = error.response?.status;
            const backendMessage = error.response?.data?.detail
                || error.response?.data?.error;
            const message = status === 403
                ? 'No tienes permiso efectivo para gestionar la entrega.'
                : status === 409
                    ? backendMessage || 'La orden cambió y ya no admite esta acción.'
                    : backendMessage || 'No pudimos actualizar la orden.';
            setActionErrors((current) => ({...current, [orderId]: message}));
            notify.error(message);
            if ([403, 409].includes(status)) {
                await loadOrders({silent: true});
            }
            return null;
        } finally {
            inFlight.current.delete(actionKey);
            setProcessing((current) => ({...current, [orderId]: null}));
        }
    };

    const confirmDelivery = async (order) => {
        if (!canConfirmOrderDelivery(order, canManageStock)) return;
        const response = await runAction(order.id, 'delivery', () => axios.post(
            `/api/gestion/ordenes-compra/${order.id}/confirmar_entrega/`,
            {}
        ));
        if (response) notify.success('Entrega confirmada');
    };

    const cancelOrder = async (order) => {
        if (order.estado !== ORDER_STATES.PENDING) return;
        const response = await runAction(order.id, 'cancel', () => axios.post(
            `/api/gestion/ordenes-compra/${order.id}/cancelar/`,
            {}
        ));
        if (response) notify.success('Orden cancelada');
    };

    if (loading) {
        return <div className="p-6 text-center">Cargando órdenes...</div>;
    }

    return (
        <main className="p-6 bg-white rounded-lg">
            <h1 className="text-3xl font-bold mb-2">Gestión de Órdenes de Venta</h1>
            <p className="mb-6 text-gray-600">
                Un pago acreditado habilita la entrega, pero no la confirma automáticamente.
            </p>

            <div className="mb-6 flex flex-wrap gap-2" aria-label="Filtros de órdenes">
                {FILTERS.map((item) => (
                    <button
                        key={item.value}
                        type="button"
                        onClick={() => setFilter(item.value)}
                        className={`px-4 py-2 rounded ${
                            filter === item.value
                                ? 'bg-gray-800 text-white'
                                : 'bg-gray-200'
                        }`}
                    >
                        {item.label}
                    </button>
                ))}
            </div>

            <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                    <thead>
                        <tr style={{backgroundColor: '#E8DCC4'}}>
                            <th className="p-3 text-left">Orden</th>
                            <th className="p-3 text-left">Cliente</th>
                            <th className="p-3 text-right">Total</th>
                            <th className="p-3 text-center">Estado comercial</th>
                            <th className="p-3 text-center">Fecha</th>
                            <th className="p-3 text-center">Productos</th>
                            <th className="p-3 text-center">Acciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {orders.length === 0 ? (
                            <tr>
                                <td colSpan="7" className="p-4 text-center text-gray-500">
                                    No hay órdenes
                                </td>
                            </tr>
                        ) : orders.map((order) => {
                            const presentation = getOrderPresentation(order);
                            const isProcessing = Boolean(processing[order.id]);
                            return (
                                <tr key={order.id} className="border-b hover:bg-gray-50">
                                    <td className="p-3 font-bold">{order.codigo || `#${order.id}`}</td>
                                    <td className="p-3">
                                        <p className="font-semibold">
                                            {order.cliente_nombre || `Cliente #${order.cliente}`}
                                        </p>
                                        <p className="text-sm text-gray-500">{order.cliente_email}</p>
                                    </td>
                                    <td className="p-3 text-right font-bold text-green-800">
                                        ${Number(order.total).toFixed(2)}
                                    </td>
                                    <td className="p-3 text-center">
                                        <span className={`px-3 py-1 rounded-full text-sm font-semibold ${presentation.badge}`}>
                                            {presentation.label}
                                        </span>
                                        <p className="mt-2 text-xs text-gray-600">{presentation.detail}</p>
                                    </td>
                                    <td className="p-3 text-center text-sm">
                                        {new Date(order.creado_at).toLocaleDateString('es-AR')}
                                    </td>
                                    <td className="p-3 text-center">
                                        <button
                                            type="button"
                                            onClick={() => setModalOrder(order)}
                                            className="text-blue-600 hover:underline"
                                        >
                                            Ver productos
                                        </button>
                                    </td>
                                    <td className="p-3 text-center">
                                        {canConfirmOrderDelivery(order, canManageStock) && (
                                            <button
                                                type="button"
                                                onClick={() => confirmDelivery(order)}
                                                disabled={isProcessing}
                                                className="px-4 py-2 rounded bg-emerald-700 text-white font-semibold disabled:opacity-50"
                                            >
                                                {processing[order.id] === 'delivery'
                                                    ? 'Confirmando…'
                                                    : 'Confirmar entrega'}
                                            </button>
                                        )}
                                        {order.estado === ORDER_STATES.PENDING && canManageStock && (
                                            <button
                                                type="button"
                                                onClick={() => cancelOrder(order)}
                                                disabled={isProcessing}
                                                className="ml-2 px-4 py-2 rounded bg-red-700 text-white font-semibold disabled:opacity-50"
                                            >
                                                {processing[order.id] === 'cancel'
                                                    ? 'Cancelando…'
                                                    : 'Cancelar'}
                                            </button>
                                        )}
                                        {order.estado === ORDER_STATES.COMPLETED && (
                                            <span className="text-green-700 font-semibold">Entrega confirmada</span>
                                        )}
                                        {order.estado === ORDER_STATES.PAID && !canManageStock && (
                                            <span className="text-gray-600">Pendiente de operador autorizado</span>
                                        )}
                                        {actionErrors[order.id] && (
                                            <p role="alert" className="mt-2 text-sm text-red-700">
                                                {actionErrors[order.id]}
                                            </p>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {modalOrder && (
                <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center p-4 z-50">
                    <section className="bg-white rounded-xl shadow-xl w-full max-w-lg" aria-label="Productos de la orden">
                        <header className="flex items-center justify-between px-6 py-4 border-b">
                            <h2 className="text-lg font-bold">Productos del pedido {modalOrder.codigo}</h2>
                            <button
                                type="button"
                                onClick={() => setModalOrder(null)}
                                className="text-gray-500 hover:text-gray-700"
                                aria-label="Cerrar"
                            >
                                ✕
                            </button>
                        </header>
                        <div className="p-6 max-h-[60vh] overflow-y-auto">
                            {(modalOrder.items || []).length === 0 ? (
                                <p className="text-sm text-gray-500">No hay productos en esta orden.</p>
                            ) : (
                                <div className="divide-y">
                                    {modalOrder.items.map((item) => (
                                        <div key={item.id} className="py-3 flex items-center justify-between">
                                            <div>
                                                <p className="font-semibold text-gray-800">{item.producto_nombre}</p>
                                                <p className="text-xs text-gray-500">{item.producto_marca}</p>
                                            </div>
                                            <p className="text-sm text-gray-700">
                                                {item.cantidad} x ${Number(item.precio_historico).toFixed(2)}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </section>
                </div>
            )}
        </main>
    );
};

export default GestionOrdenes;
