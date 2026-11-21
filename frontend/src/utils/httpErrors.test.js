import {
    classifyHttpError,
    getHttpErrorMessage,
    HTTP_ERROR_KIND
} from './httpErrors';


describe('clasificación HTTP', () => {
    test.each([
        [401, HTTP_ERROR_KIND.SESSION],
        [403, HTTP_ERROR_KIND.FORBIDDEN],
        [409, HTTP_ERROR_KIND.CONFLICT],
        [400, HTTP_ERROR_KIND.VALIDATION],
        [422, HTTP_ERROR_KIND.VALIDATION],
        [503, HTTP_ERROR_KIND.SERVER]
    ])('clasifica %s como %s', (status, kind) => {
        expect(classifyHttpError({ response: { status } }).kind).toBe(kind);
    });

    test('distingue red y timeout como recuperables', () => {
        expect(classifyHttpError(new Error('offline'))).toMatchObject({
            kind: HTTP_ERROR_KIND.NETWORK,
            retryable: true,
            timeout: false
        });
        expect(classifyHttpError({ code: 'ECONNABORTED' })).toMatchObject({
            kind: HTTP_ERROR_KIND.NETWORK,
            retryable: true,
            timeout: true
        });
    });

    test('conserva detalles de validación y conflicto', () => {
        expect(getHttpErrorMessage({
            response: { status: 400, data: { email: ['Email inválido.'] } }
        })).toBe('Email inválido.');
        expect(getHttpErrorMessage({
            response: {
                status: 409,
                data: { error: { detail: 'El registro cambió.' } }
            }
        })).toBe('El registro cambió.');
    });
});
