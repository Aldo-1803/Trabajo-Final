import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';

import { IconBag, IconReceipt } from '../../components/common/Icons';
import { notify } from '../../utils/notificaciones';
import {
    canContinueOrderCheckout,
    getOrderPresentation,
    hasPaymentUnderReview,
    ORDER_STATES,
} from '../../utils/orderStatus';


const FILTERS = [
    {value: 'TODOS', label: 'Todos'},
    {value: ORDER_STATES.PENDING, label: 'Pendientes'},
    {value: ORDER_STATES.AWAITING_PAYMENT, label: 'Pago pendiente'},
    {value: ORDER_STATES.PAID, label: 'Pagados'},
    {value: ORDER_STATES.COMPLETED, label: 'Entregados'},
    {value: ORDER_STATES.REJECTED, label: 'Rechazados'},
    {value: ORDER_STATES.CANCELLED, label: 'Cancelados'},
];

const newCheckoutKey = () => (
    window.crypto?.randomUUID?.()
    || `order-checkout-${Date.now()}-${Math.random().toString(16).slice(2)}`
);


const MisPedidos = ({onRedirect = (url) => window.location.assign(url)}) => {
    const [orders, setOrders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [filter, setFilter] = useState('TODOS');
    const [checkoutOrderId, setCheckoutOrderId] = useState(null);
    const [checkoutErrors, setCheckoutErrors] = useState({});
    const checkoutKeys = useRef({});

    const loadOrders = useCallback(async ({silent = false} = {}) => {
        if (!silent) setLoading(true);
        try {
            const response = await axios.get('/api/gestion/ordenes-compra/');
            setOrders(response.data.results || response.data);
        } catch (error) {
            console.error('Error cargando pedidos:', error);
            notify.error('Error al cargar tus pedidos');
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadOrders();
    }, [loadOrders]);

    const requiresRefresh = orders.some((order) => (
        canContinueOrderCheckout(order) || hasPaymentUnderReview(order)
    ));

    useEffect(() => {
        if (!requiresRefresh) return undefined;
        const timer = window.setInterval(
            () => loadOrders({silent: true}),
            5000
        );
        return () => window.clearInterval(timer);
    }, [loadOrders, requiresRefresh]);

    useEffect(() => {
        const refreshOnFocus = () => loadOrders({silent: true});
        window.addEventListener('focus', refreshOnFocus);
        return () => window.removeEventListener('focus', refreshOnFocus);
    }, [loadOrders]);

    const refreshOrders = async () => {
        setRefreshing(true);
        await loadOrders({silent: true});
        setRefreshing(false);
    };

    const startCheckout = async (order) => {
        if (!canContinueOrderCheckout(order) || checkoutOrderId !== null) return;
        const key = checkoutKeys.current[order.id] || newCheckoutKey();
        checkoutKeys.current[order.id] = key;
        setCheckoutOrderId(order.id);
        setCheckoutErrors((current) => ({...current, [order.id]: ''}));
        try {
            const response = await axios.post(
                `/api/gestion/ordenes-compra/${order.id}/checkout/`,
                {channel: 'ONLINE'},
                {headers: {'Idempotency-Key': key}}
            );
            if (response.data?.checkout_url) {
                onRedirect(response.data.checkout_url);
                return;
            }
            const uncertain = response.data?.status === 'OUTCOME_UNKNOWN';
            const message = uncertain
                ? 'El resultado del checkout es incierto. Reintenta: se conservará la misma solicitud.'
                : response.data?.error_detail
                    || 'Mercado Pago no devolvió un enlace utilizable.';
            if (!uncertain) delete checkoutKeys.current[order.id];
            setCheckoutErrors((current) => ({...current, [order.id]: message}));
            notify.error(message);
        } catch (error) {
            const data = error.response?.data || {};
            const retryable = data.status === 'OUTCOME_UNKNOWN'
                || ['PROVIDER_CONFIGURATION_ERROR', 'PROVIDER_REQUEST_IN_PROGRESS']
                    .includes(data.error_code || data.code);
            if (!retryable) delete checkoutKeys.current[order.id];
            const message = data.detail || data.error || data.error_detail
                || 'No pudimos iniciar el checkout.';
            setCheckoutErrors((current) => ({...current, [order.id]: message}));
            notify.error(message);
            if ([403, 409].includes(error.response?.status)) {
                await loadOrders({silent: true});
            }
        } finally {
            setCheckoutOrderId(null);
        }
    };

    const filteredOrders = useMemo(() => {
        if (filter === 'TODOS') return orders;
        return orders.filter((order) => order.estado === filter);
    }, [orders, filter]);

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4" />
                    <p style={{color: '#817773'}}>Cargando pedidos...</p>
                </div>
            </div>
        );
    }

    return (
        <main className="min-h-screen p-4 md:p-8" style={{backgroundColor: '#F5F5EB'}}>
            <div className="max-w-5xl mx-auto">
                <header className="mb-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
                    <div>
                        <h1 className="text-3xl md:text-4xl font-bold mb-2" style={{color: '#817773'}}>
                            <span className="inline-flex items-center gap-2">
                                <IconReceipt className="h-7 w-7" />
                                Mis Pedidos
                            </span>
                        </h1>
                        <p style={{color: '#8B8682'}}>
                            Consulta por separado el pago y la entrega de tus productos.
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={refreshOrders}
                        disabled={refreshing}
                        className="rounded-lg border border-gray-400 bg-white px-4 py-2 disabled:opacity-50"
                    >
                        {refreshing ? 'Actualizando…' : 'Actualizar pedidos'}
                    </button>
                </header>

                <div className="mb-6 flex flex-wrap gap-2" aria-label="Filtros de pedidos">
                    {FILTERS.map((item) => (
                        <button
                            key={item.value}
                            type="button"
                            onClick={() => setFilter(item.value)}
                            className={`px-4 py-2 rounded-full text-sm font-semibold transition ${
                                filter === item.value
                                    ? 'bg-gray-800 text-white'
                                    : 'bg-white text-gray-700'
                            }`}
                        >
                            {item.label}
                        </button>
                    ))}
                </div>

                {filteredOrders.length === 0 ? (
                    <section className="bg-white rounded-xl shadow-lg p-10 text-center">
                        <div className="flex justify-center mb-4">
                            <IconBag className="h-12 w-12 text-gray-400" />
                        </div>
                        <h2 className="text-xl font-bold mb-2" style={{color: '#817773'}}>
                            No tienes pedidos aún
                        </h2>
                        <p className="text-sm" style={{color: '#8B8682'}}>
                            Cuando realices una compra, aparecerá aquí con su estado.
                        </p>
                    </section>
                ) : (
                    <div className="space-y-4">
                        {filteredOrders.map((order) => {
                            const presentation = getOrderPresentation(order);
                            const canCheckout = canContinueOrderCheckout(order);
                            return (
                                <article key={order.id} className="bg-white rounded-xl shadow-md p-4 md:p-6">
                                    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                                        <div>
                                            <p className="text-sm text-gray-500">Pedido</p>
                                            <h2 className="text-lg font-bold" style={{color: '#817773'}}>
                                                {order.codigo}
                                            </h2>
                                            <p className="text-xs text-gray-500">
                                                {new Date(order.creado_at).toLocaleDateString('es-AR')}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <span className={`px-3 py-1 rounded-full text-xs font-semibold ${presentation.badge}`}>
                                                {presentation.label}
                                            </span>
                                            <span className="text-lg font-bold text-green-800">
                                                ${Number(order.total).toFixed(2)}
                                            </span>
                                        </div>
                                    </div>

                                    <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                                        {presentation.detail}
                                    </p>

                                    {canCheckout && (
                                        <button
                                            type="button"
                                            onClick={() => startCheckout(order)}
                                            disabled={checkoutOrderId !== null}
                                            className="mt-3 rounded-lg bg-sky-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
                                        >
                                            {checkoutOrderId === order.id
                                                ? 'Conectando…'
                                                : 'Continuar al checkout'}
                                        </button>
                                    )}
                                    {checkoutErrors[order.id] && (
                                        <p role="alert" className="mt-2 text-sm text-red-700">
                                            {checkoutErrors[order.id]}
                                        </p>
                                    )}

                                    <div className="mt-4">
                                        <h3 className="text-sm font-semibold text-gray-700 mb-2">Productos</h3>
                                        <div className="divide-y">
                                            {(order.items || []).map((item) => (
                                                <div key={item.id} className="py-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                                                    <div>
                                                        <p className="text-sm font-medium text-gray-800">{item.producto_nombre}</p>
                                                        <p className="text-xs text-gray-500">{item.producto_marca}</p>
                                                    </div>
                                                    <p className="text-sm text-gray-700">
                                                        {item.cantidad} x ${Number(item.precio_historico).toFixed(2)}
                                                    </p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </article>
                            );
                        })}
                    </div>
                )}
            </div>
        </main>
    );
};

export default MisPedidos;
