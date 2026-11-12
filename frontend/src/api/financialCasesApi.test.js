import axios from 'axios';

import {
    closeFinancialCase,
    executeAuthorizedRefund,
    financialApiError,
    getFinancialCase,
    getRefundOperation,
    listFinancialCases,
    recordResolutionDecision,
    recoverRefundOperation,
    requestPaidOrderCancellation,
    submitResolutionRequest,
} from './financialCasesApi';


jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), post: jest.fn()},
}));


describe('financialCasesApi', () => {
    beforeEach(() => jest.clearAllMocks());

    test('usa los endpoints de lectura con filtros y UUID público', async () => {
        axios.get.mockResolvedValue({data: {results: []}});

        await listFinancialCases({status: 'OPEN', context: 'ORDER'});
        await getFinancialCase('case-1');
        await getRefundOperation('case-1');

        expect(axios.get).toHaveBeenNthCalledWith(
            1,
            '/api/gestion/payment-reconciliation-cases/',
            {params: {status: 'OPEN', context: 'ORDER'}},
        );
        expect(axios.get).toHaveBeenNthCalledWith(
            2,
            '/api/gestion/payment-reconciliation-cases/case-1/',
        );
        expect(axios.get).toHaveBeenNthCalledWith(
            3,
            '/api/gestion/payment-reconciliation-cases/case-1/refund-operation/',
        );
    });

    test('envía Idempotency-Key en todos los comandos mutables', async () => {
        axios.post.mockResolvedValue({data: {}});
        const config = {headers: {'Idempotency-Key': 'stable-key'}};

        await submitResolutionRequest('case-1', {reason: 'R'}, 'stable-key');
        await recordResolutionDecision('case-1', {action: 'NO_FINANCIAL_CHANGE'}, 'stable-key');
        await executeAuthorizedRefund('case-1', 'payment-1', 'stable-key');
        await recoverRefundOperation('case-1', 'stable-key');
        await closeFinancialCase('case-1', {result: 'NO_FINANCIAL_CHANGE'}, 'stable-key');
        await requestPaidOrderCancellation({order_id: 9}, 'stable-key');

        expect(axios.post).toHaveBeenNthCalledWith(1, expect.stringContaining('submit-resolution-request'), {reason: 'R'}, config);
        expect(axios.post).toHaveBeenNthCalledWith(2, expect.stringContaining('record-decision'), {action: 'NO_FINANCIAL_CHANGE'}, config);
        expect(axios.post).toHaveBeenNthCalledWith(3, expect.stringContaining('execute-authorized-refund'), {payment_public_id: 'payment-1'}, config);
        expect(axios.post).toHaveBeenNthCalledWith(4, expect.stringContaining('recover-refund-operation'), {}, config);
        expect(axios.post).toHaveBeenNthCalledWith(5, expect.stringContaining('close-financial-case'), {result: 'NO_FINANCIAL_CHANGE'}, config);
        expect(axios.post).toHaveBeenNthCalledWith(6, expect.stringContaining('request-paid-order-cancellation'), {order_id: 9}, config);
    });

    test.each([
        [403, {code: 'DENIED'}, 'permiso efectivo'],
        [409, {code: 'STATE_CHANGED', errors: {non_field_errors: ['Cambió.']}}, 'Conflicto financiero: Cambió.'],
        [422, {detail: 'Evidencia insuficiente'}, 'no es procesable'],
    ])('normaliza HTTP %s sin ocultar el resultado', (status, data, expected) => {
        expect(financialApiError({response: {status, data}}, 'fallback')).toContain(expected);
    });

    test('un fallo de red se presenta como resultado desconocido', () => {
        expect(financialApiError(new Error('offline'), 'fallback')).toContain(
            'resultado es desconocido',
        );
    });
});
