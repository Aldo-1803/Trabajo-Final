import {
    HTTP_SESSION_EVENT,
    subscribeToHttpSessionEvents
} from './httpSessionEvents';


let requestHandler;
let responseErrorHandler;


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        defaults: { headers: { common: {} } },
        interceptors: {
            request: {
                use: jest.fn((success) => {
                    requestHandler = success;
                })
            },
            response: {
                use: jest.fn((success, error) => {
                    responseErrorHandler = error;
                })
            }
        }
    }
}));


require('./axiosConfig');


describe('axiosConfig', () => {
    beforeEach(() => {
        localStorage.clear();
    });

    test('agrega identidad de sesión sólo a requests protegidos', () => {
        localStorage.setItem('access_token', 'active-token');

        const protectedConfig = requestHandler({
            url: '/api/gestion/servicios/',
            headers: {}
        });
        const loginConfig = requestHandler({
            url: '/api/usuarios/login/',
            headers: { Authorization: 'anterior' }
        });

        expect(protectedConfig.headers.Authorization).toBe('Bearer active-token');
        expect(protectedConfig.__sessionAccessToken).toBe('active-token');
        expect(loginConfig.headers.Authorization).toBeUndefined();
        expect(loginConfig.__sessionAccessToken).toBeNull();
    });

    test.each([
        [401, HTTP_SESSION_EVENT.UNAUTHORIZED],
        [403, HTTP_SESSION_EVENT.FORBIDDEN]
    ])('publica %s autenticado sin reenviar la operación', async (status, type) => {
        const listener = jest.fn();
        const unsubscribe = subscribeToHttpSessionEvents(listener);
        const error = {
            response: { status },
            config: { __sessionAccessToken: 'active-token' }
        };

        await expect(responseErrorHandler(error)).rejects.toBe(error);

        expect(listener).toHaveBeenCalledTimes(1);
        expect(listener).toHaveBeenCalledWith({
            type,
            accessToken: 'active-token'
        });
        unsubscribe();
    });

    test('un 401 de login no se interpreta como sesión expirada', async () => {
        const listener = jest.fn();
        const unsubscribe = subscribeToHttpSessionEvents(listener);
        const error = {
            response: { status: 401 },
            config: { __sessionAccessToken: null }
        };

        await expect(responseErrorHandler(error)).rejects.toBe(error);
        expect(listener).not.toHaveBeenCalled();
        unsubscribe();
    });
});
