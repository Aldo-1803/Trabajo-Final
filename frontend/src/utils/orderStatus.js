export const ORDER_STATES = Object.freeze({
    PENDING: 'PENDIENTE',
    AWAITING_PAYMENT: 'ESPERANDO_PAGO',
    PAID: 'PAGADO',
    COMPLETED: 'COMPLETADO',
    REJECTED: 'RECHAZADO',
    CANCELLED: 'CANCELADO',
});

const STATUS_PRESENTATION = Object.freeze({
    [ORDER_STATES.PENDING]: {
        label: 'Pendiente de pago',
        detail: 'La orden fue creada y todavía no registra un pago acreditado.',
        badge: 'bg-yellow-100 text-yellow-800',
    },
    [ORDER_STATES.AWAITING_PAYMENT]: {
        label: 'Pago pendiente',
        detail: 'El checkout puede continuar mientras la orden siga habilitada.',
        badge: 'bg-blue-100 text-blue-800',
    },
    [ORDER_STATES.PAID]: {
        label: 'Pagada · pendiente de entrega',
        detail: 'El pago fue acreditado. Los productos todavía no fueron entregados.',
        badge: 'bg-emerald-100 text-emerald-800',
    },
    [ORDER_STATES.COMPLETED]: {
        label: 'Entregada',
        detail: 'La entrega fue confirmada y la orden está completada.',
        badge: 'bg-green-100 text-green-800',
    },
    [ORDER_STATES.REJECTED]: {
        label: 'Pago rechazado',
        detail: 'El pago no fue acreditado.',
        badge: 'bg-red-100 text-red-800',
    },
    [ORDER_STATES.CANCELLED]: {
        label: 'Cancelada',
        detail: 'La orden fue cancelada.',
        badge: 'bg-slate-200 text-slate-800',
    },
});

const PAYMENT_REVIEW = Object.freeze({
    label: 'Pago en revisión',
    detail: 'El backend registró un pago pendiente de conciliación. No vuelvas a pagar.',
    badge: 'bg-amber-100 text-amber-900',
});


export const hasPaymentUnderReview = (order) => (
    (order?.pagos || []).some(
        (payment) => payment.status === 'PENDING_RECONCILIATION'
    )
);

export const getOrderPresentation = (order) => {
    if (hasPaymentUnderReview(order)) return PAYMENT_REVIEW;
    return STATUS_PRESENTATION[order?.estado] || {
        label: 'Estado no disponible',
        detail: 'Actualiza la orden para consultar su estado vigente.',
        badge: 'bg-gray-100 text-gray-800',
    };
};

export const canContinueOrderCheckout = (order) => {
    if (![ORDER_STATES.PENDING, ORDER_STATES.AWAITING_PAYMENT].includes(
        order?.estado
    )) {
        return false;
    }
    return (order?.pagos || []).every(
        (payment) => ['REJECTED', 'REVERSED'].includes(payment.status)
    );
};

export const canConfirmOrderDelivery = (order, hasManageStock) => (
    hasManageStock === true && order?.estado === ORDER_STATES.PAID
);
