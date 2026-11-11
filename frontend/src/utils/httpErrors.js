export const HTTP_ERROR_KIND = Object.freeze({
    SESSION: 'session',
    FORBIDDEN: 'forbidden',
    CONFLICT: 'conflict',
    VALIDATION: 'validation',
    NETWORK: 'network',
    SERVER: 'server',
    UNKNOWN: 'unknown'
});


const firstValidationDetail = (data) => {
    if (!data || typeof data !== 'object') return null;

    return Object.values(data).find((value) => (
        typeof value === 'string'
        || (Array.isArray(value) && typeof value[0] === 'string')
    ));
};


export const classifyHttpError = (error) => {
    const status = error?.response?.status || null;
    const data = error?.response?.data;
    const backendError = data?.error;
    const validationDetail = firstValidationDetail(data);
    const detail = backendError?.detail
        || data?.detail
        || (Array.isArray(validationDetail) ? validationDetail[0] : validationDetail)
        || null;

    let kind = HTTP_ERROR_KIND.UNKNOWN;
    if (!error?.response) kind = HTTP_ERROR_KIND.NETWORK;
    else if (status === 401) kind = HTTP_ERROR_KIND.SESSION;
    else if (status === 403) kind = HTTP_ERROR_KIND.FORBIDDEN;
    else if (status === 409) kind = HTTP_ERROR_KIND.CONFLICT;
    else if (status === 400 || status === 422) kind = HTTP_ERROR_KIND.VALIDATION;
    else if (status >= 500) kind = HTTP_ERROR_KIND.SERVER;

    return {
        kind,
        status,
        code: backendError?.code || null,
        detail,
        timeout: ['ECONNABORTED', 'ETIMEDOUT'].includes(error?.code),
        retryable: kind === HTTP_ERROR_KIND.NETWORK || kind === HTTP_ERROR_KIND.SERVER
    };
};


const DEFAULT_MESSAGES = Object.freeze({
    [HTTP_ERROR_KIND.SESSION]: 'Tu sesión finalizó. Ingresá nuevamente.',
    [HTTP_ERROR_KIND.FORBIDDEN]: 'No tenés autorización para completar esta operación.',
    [HTTP_ERROR_KIND.CONFLICT]: 'La operación entra en conflicto con el estado actual.',
    [HTTP_ERROR_KIND.VALIDATION]: 'Revisá los datos ingresados.',
    [HTTP_ERROR_KIND.NETWORK]: 'No pudimos comunicarnos con el servidor. Intentá nuevamente.',
    [HTTP_ERROR_KIND.SERVER]: 'El servidor no pudo completar la operación. Intentá nuevamente.',
    [HTTP_ERROR_KIND.UNKNOWN]: 'No se pudo completar la operación.'
});


export const getHttpErrorMessage = (error, messages = {}) => {
    const classified = classifyHttpError(error);
    if (
        classified.detail
        && [HTTP_ERROR_KIND.VALIDATION, HTTP_ERROR_KIND.CONFLICT].includes(
            classified.kind
        )
    ) {
        return classified.detail;
    }
    return messages[classified.kind]
        || DEFAULT_MESSAGES[classified.kind];
};
