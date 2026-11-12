export const REQUEST_OUTCOME_LABELS = Object.freeze({
    REFUND: 'Devolución',
    CANCEL_AND_REFUND: 'Cancelar y revisar devolución',
    REVIEW_PAYMENT: 'Revisar pago',
    REVIEW_EXTERNAL_ADJUSTMENT: 'Revisar ajuste externo',
    NO_FINANCIAL_CHANGE: 'Sin cambio financiero',
});

export const DECISION_LABELS = Object.freeze({
    APPROVE_REFUND: 'Aprobar devolución',
    DENY_REFUND: 'Denegar devolución',
    REQUIRE_MORE_EVIDENCE: 'Requerir más evidencia',
    ACKNOWLEDGE_EXTERNAL_ADJUSTMENT: 'Reconocer ajuste externo',
    NO_FINANCIAL_CHANGE: 'Resolver sin cambio financiero',
});

export const OPERATION_STATUS_LABELS = Object.freeze({
    PENDING: 'Pendiente de envío',
    SUBMITTED: 'Enviada; confirmación pendiente',
    UNKNOWN: 'Resultado desconocido',
    FAILED: 'Fallida',
    CONFIRMED: 'Confirmada financieramente',
});

export const CASE_TYPE_LABELS = Object.freeze({
    LATE_PAYMENT: 'Pago tardío',
    BOOKING_CONFIRMATION_FAILED: 'Confirmación de turno fallida',
    EXTERNAL_PAYMENT_REVIEW: 'Revisión de pago externo',
    ORDER_FULFILLMENT_FAILED: 'Orden no entregable',
    POST_PAYMENT_CHANGE: 'Novedad posterior al pago',
    CANCELLATION_WITH_PAYMENT: 'Cancelación con pago',
});

export const REQUEST_OUTCOMES = Object.freeze([
    'REFUND',
    'CANCEL_AND_REFUND',
    'REVIEW_PAYMENT',
    'REVIEW_EXTERNAL_ADJUSTMENT',
    'NO_FINANCIAL_CHANGE',
]);

const FINAL_ACTIONS = new Set([
    'APPROVE_REFUND',
    'DENY_REFUND',
    'ACKNOWLEDGE_EXTERNAL_ADJUSTMENT',
    'NO_FINANCIAL_CHANGE',
]);

const REFUNDABLE_OUTCOMES = new Set([
    'REFUND',
    'CANCEL_AND_REFUND',
    'REVIEW_PAYMENT',
]);


export const getFinalDecision = (financialCase) => {
    const decisions = financialCase?.resolution_request?.decisions || [];
    return [...decisions]
        .sort((left, right) => Number(right.sequence) - Number(left.sequence))
        .find((decision) => FINAL_ACTIONS.has(decision.action)) || null;
};


export const getDecisionOptions = (financialCase) => {
    const request = financialCase?.resolution_request;
    if (
        financialCase?.status !== 'OPEN'
        || !request
        || request.status === 'DECIDED'
    ) return [];

    const actions = ['REQUIRE_MORE_EVIDENCE', 'NO_FINANCIAL_CHANGE'];
    if (REFUNDABLE_OUTCOMES.has(request.requested_outcome)) {
        actions.unshift('APPROVE_REFUND', 'DENY_REFUND');
    }
    if (
        ['POST_PAYMENT_CHANGE', 'EXTERNAL_PAYMENT_REVIEW'].includes(
            financialCase.case_type,
        )
        && ['REVIEW_EXTERNAL_ADJUSTMENT', 'REVIEW_PAYMENT'].includes(
            request.requested_outcome,
        )
    ) {
        actions.unshift('ACKNOWLEDGE_EXTERNAL_ADJUSTMENT');
    }
    return [...new Set(actions)];
};


export const getEligibleRefundPayments = (financialCase) => (
    (financialCase?.payments || []).filter((payment) => (
        payment.status === 'RECONCILED'
        && payment.provider_code === 'MERCADO_PAGO'
        && Number(payment.financial_projection?.net_reconciled) > 0
    ))
);


export const canExecuteRefund = (financialCase, refundOperation) => (
    financialCase?.status === 'OPEN'
    && getFinalDecision(financialCase)?.action === 'APPROVE_REFUND'
    && !refundOperation
    && getEligibleRefundPayments(financialCase).length > 0
);


export const closureResultFor = (financialCase, refundOperation) => {
    if (financialCase?.status !== 'OPEN') return null;
    const action = getFinalDecision(financialCase)?.action;
    if (action === 'APPROVE_REFUND') {
        if (refundOperation?.status !== 'CONFIRMED') return null;
        return financialCase.order?.estado === 'COMPLETADO'
            ? 'PHYSICAL_RETURN_DEFERRED'
            : 'REFUND_CONFIRMED';
    }
    return {
        DENY_REFUND: 'REFUND_DENIED',
        ACKNOWLEDGE_EXTERNAL_ADJUSTMENT: 'EXTERNAL_ADJUSTMENT_ACKNOWLEDGED',
        NO_FINANCIAL_CHANGE: 'NO_FINANCIAL_CHANGE',
    }[action] || null;
};


export const ageLabel = (ageSeconds) => {
    const seconds = Math.max(0, Number(ageSeconds) || 0);
    const days = Math.floor(seconds / 86400);
    if (days > 0) return `${days} día${days === 1 ? '' : 's'}`;
    const hours = Math.floor(seconds / 3600);
    if (hours > 0) return `${hours} h`;
    return `${Math.floor(seconds / 60)} min`;
};


export const isAgedCase = (financialCase, thresholdHours = 48) => (
    financialCase?.status === 'OPEN'
    && Number(financialCase.age_seconds) >= thresholdHours * 3600
);
