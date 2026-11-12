import axios from 'axios';


export const FINANCIAL_CASES_URL = '/api/gestion/payment-reconciliation-cases/';


export const createIdempotencyKey = (prefix = 'financial-case') => (
    window.crypto?.randomUUID?.()
    || `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
);


const commandConfig = (idempotencyKey) => ({
    headers: {'Idempotency-Key': idempotencyKey},
});


export const listFinancialCases = (params = {}) => (
    axios.get(FINANCIAL_CASES_URL, {params})
);


export const getFinancialCase = (publicId) => (
    axios.get(`${FINANCIAL_CASES_URL}${publicId}/`)
);


export const submitResolutionRequest = (publicId, payload, idempotencyKey) => (
    axios.post(
        `${FINANCIAL_CASES_URL}${publicId}/submit-resolution-request/`,
        payload,
        commandConfig(idempotencyKey),
    )
);


export const requestPaidOrderCancellation = (payload, idempotencyKey) => (
    axios.post(
        `${FINANCIAL_CASES_URL}request-paid-order-cancellation/`,
        payload,
        commandConfig(idempotencyKey),
    )
);


export const recordResolutionDecision = (publicId, payload, idempotencyKey) => (
    axios.post(
        `${FINANCIAL_CASES_URL}${publicId}/record-decision/`,
        payload,
        commandConfig(idempotencyKey),
    )
);


export const executeAuthorizedRefund = (publicId, paymentPublicId, idempotencyKey) => (
    axios.post(
        `${FINANCIAL_CASES_URL}${publicId}/execute-authorized-refund/`,
        {payment_public_id: paymentPublicId},
        commandConfig(idempotencyKey),
    )
);


export const getRefundOperation = (publicId) => (
    axios.get(`${FINANCIAL_CASES_URL}${publicId}/refund-operation/`)
);


export const recoverRefundOperation = (publicId, idempotencyKey) => (
    axios.post(
        `${FINANCIAL_CASES_URL}${publicId}/recover-refund-operation/`,
        {},
        commandConfig(idempotencyKey),
    )
);


export const closeFinancialCase = (publicId, payload, idempotencyKey) => (
    axios.post(
        `${FINANCIAL_CASES_URL}${publicId}/close-financial-case/`,
        payload,
        commandConfig(idempotencyKey),
    )
);


const firstError = (errors) => {
    if (!errors || typeof errors !== 'object') return '';
    for (const [field, messages] of Object.entries(errors)) {
        const detail = Array.isArray(messages) ? messages.join(' ') : String(messages);
        if (detail) return field === 'non_field_errors' ? detail : `${field}: ${detail}`;
    }
    return '';
};


export const financialApiError = (error, fallback) => {
    if (!error?.response) {
        return 'No se pudo contactar al servidor. El resultado es desconocido; recargá el caso antes de reintentar.';
    }
    const {status, data = {}} = error.response;
    const detail = firstError(data.errors)
        || firstError(data)
        || data.detail
        || data.error
        || data.code;
    if (status === 403) {
        return 'No tenés el permiso efectivo para gestionar incidencias financieras.';
    }
    if (status === 409) {
        return detail
            ? `Conflicto financiero: ${detail}`
            : 'El caso cambió o la acción no es compatible con su estado actual.';
    }
    if (status === 422) {
        return detail
            ? `La operación no es procesable: ${detail}`
            : 'La operación no es procesable con la evidencia actual.';
    }
    return detail || fallback;
};
