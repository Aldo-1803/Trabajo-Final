import { act, render, screen, waitFor } from '@testing-library/react';

import { fetchCurrentSession } from '../api/sessionApi';
import {
    emitHttpSessionEvent,
    HTTP_SESSION_EVENT
} from '../api/httpSessionEvents';
import {
    SESSION_REFRESH_INTERVAL_MS,
    SESSION_STATUS,
    SessionProvider,
    useSession
} from './SessionContext';


jest.mock('../api/sessionApi', () => ({
    fetchCurrentSession: jest.fn()
}));
jest.mock('axios', () => ({
    __esModule: true,
    default: {
        defaults: {
            headers: { common: {} }
        }
    }
}));


const validSession = {
    user: {
        id: 42,
        email: 'ana@example.com',
        first_name: 'Ana',
        last_name: 'Pérez',
        is_active: true
    },
    business_role: 'PROFESIONAL',
    permissions: [
        'gestion.create_diagnosis',
        'gestion.manage_stock',
        'gestion.view_global_agenda'
    ],
    capabilities: {
        'technical_booking.review': true,
        'diagnosis.create': true,
        'technical_record.read_global': true,
        'technical_record.manage': true,
        'service_formula.manage': true,
        'content.author': true,
        'content.manage_global': false
    },
    profiles: {
        cliente: {
            exists: true,
            id: 42,
            active: true
        },
        personal: {
            exists: true,
            id: 17,
            active: true,
            function_role: 'colorista'
        }
    }
};


let currentSession;


const SessionConsumer = () => {
    currentSession = useSession();
    return <span data-testid="status">{currentSession.status}</span>;
};


const renderProvider = () => render(
    <SessionProvider>
        <SessionConsumer />
    </SessionProvider>
);


const mockAuthenticatedSession = (data = validSession) => {
    localStorage.setItem('access_token', 'access-token');
    fetchCurrentSession.mockResolvedValue({ data });
};


const deferred = () => {
    let resolve;
    let reject;
    const promise = new Promise((promiseResolve, promiseReject) => {
        resolve = promiseResolve;
        reject = promiseReject;
    });
    return { promise, resolve, reject };
};


describe('SessionProvider', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.clear();
        currentSession = undefined;
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    test('sin access_token representa una sesión anónima', async () => {
        localStorage.setItem('user_info', JSON.stringify({ is_staff: true }));

        renderProvider();

        await waitFor(() => {
            expect(screen.getByTestId('status')).toHaveTextContent(
                SESSION_STATUS.ANONYMOUS
            );
        });
        expect(currentSession.anonymous).toBe(true);
        expect(currentSession.authenticated).toBe(false);
        expect(fetchCurrentSession).not.toHaveBeenCalled();
    });

    test('token y respuesta válida producen una sesión autenticada', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(fetchCurrentSession).toHaveBeenCalledWith('access-token');
        expect(currentSession.loading).toBe(false);
    });

    test('mantiene loading mientras espera el contexto del backend', async () => {
        let resolveRequest;
        localStorage.setItem('access_token', 'access-token');
        fetchCurrentSession.mockReturnValue(new Promise((resolve) => {
            resolveRequest = resolve;
        }));

        renderProvider();

        expect(currentSession.loading).toBe(true);
        await act(async () => {
            resolveRequest({ data: validSession });
        });
        expect(currentSession.authenticated).toBe(true);
    });

    test('expone user, BusinessRole, permisos, capacidades y perfiles', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.user).toEqual(validSession.user);
        expect(currentSession.businessRole).toBe('PROFESIONAL');
        expect(currentSession.permissions).toEqual(validSession.permissions);
        expect(currentSession.capabilities).toEqual(validSession.capabilities);
        expect(currentSession.profiles).toEqual(validSession.profiles);
    });

    test('hasPermission usa coincidencia exacta sobre permisos efectivos', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasPermission('gestion.create_diagnosis')).toBe(true);
        expect(currentSession.hasPermission('create_diagnosis')).toBe(false);
    });

    test('un permiso individual funciona sin reinterpretar el rol', async () => {
        mockAuthenticatedSession({
            ...validSession,
            business_role: 'EMPLEADO',
            permissions: ['gestion.manage_stock']
        });

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.businessRole).toBe('EMPLEADO');
        expect(currentSession.hasPermission('gestion.manage_stock')).toBe(true);
    });

    test('hasAnyPermission requiere al menos una coincidencia', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasAnyPermission([
            'gestion.view_reports',
            'gestion.manage_stock'
        ])).toBe(true);
        expect(currentSession.hasAnyPermission(['gestion.view_reports'])).toBe(false);
        expect(currentSession.hasAnyPermission([])).toBe(false);
    });

    test('hasCapability y hasAnyCapability exigen booleano true', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasCapability('diagnosis.create')).toBe(true);
        expect(currentSession.hasCapability('content.manage_global')).toBe(false);
        expect(currentSession.hasCapability('unknown.capability')).toBe(false);
        expect(currentSession.hasAnyCapability([
            'content.manage_global',
            'content.author'
        ])).toBe(true);
        expect(currentSession.hasAnyCapability(['content.manage_global'])).toBe(false);
        expect(currentSession.hasAnyCapability([])).toBe(false);
        expect(currentSession.hasAnyCapability('content.author')).toBe(false);
    });

    test('capabilities ausentes fallan cerrado sin romper el contrato anterior', async () => {
        const { capabilities, ...legacySession } = validSession;
        mockAuthenticatedSession(legacySession);

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.capabilities).toEqual({});
        expect(currentSession.hasCapability('diagnosis.create')).toBe(false);
        expect(currentSession.hasAnyCapability(['diagnosis.create'])).toBe(false);
        expect(currentSession.permissions).toEqual(validSession.permissions);
    });

    test('valores no booleanos de capabilities se normalizan a false', async () => {
        mockAuthenticatedSession({
            ...validSession,
            capabilities: {
                'diagnosis.create': 'true',
                'content.author': 1,
                'content.manage_global': null,
                'service_formula.manage': true
            }
        });

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasCapability('diagnosis.create')).toBe(false);
        expect(currentSession.hasCapability('content.author')).toBe(false);
        expect(currentSession.hasCapability('content.manage_global')).toBe(false);
        expect(currentSession.hasCapability('service_formula.manage')).toBe(true);
    });

    test('BusinessRole o permiso simple no inventan una capability falsa', async () => {
        mockAuthenticatedSession({
            ...validSession,
            business_role: 'ADMINISTRADOR',
            permissions: ['gestion.create_diagnosis'],
            capabilities: {'diagnosis.create': false}
        });

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasRole('ADMINISTRADOR')).toBe(true);
        expect(currentSession.hasPermission('gestion.create_diagnosis')).toBe(true);
        expect(currentSession.hasCapability('diagnosis.create')).toBe(false);
    });

    test('hasRole compara únicamente el BusinessRole recibido', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasRole('PROFESIONAL')).toBe(true);
        expect(currentSession.hasRole('ADMINISTRADOR')).toBe(false);
    });

    test('hasProfile informa Cliente y Personal coexistentes', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasProfile('cliente')).toBe(true);
        expect(currentSession.hasProfile('personal')).toBe(true);
        expect(currentSession.hasProfile('otro')).toBe(false);
    });

    test('hasActiveProfile requiere existencia y actividad del perfil', async () => {
        mockAuthenticatedSession({
            ...validSession,
            profiles: {
                ...validSession.profiles,
                personal: { ...validSession.profiles.personal, active: false }
            }
        });

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.hasActiveProfile('personal')).toBe(false);
        expect(currentSession.hasActiveProfile('cliente')).toBe(true);
    });

    test('refreshSession reemplaza el contexto en memoria', async () => {
        const updatedSession = {
            ...validSession,
            business_role: 'ADMINISTRADOR',
            permissions: ['usuarios.manage_users'],
            capabilities: {
                ...validSession.capabilities,
                'diagnosis.create': false,
                'content.manage_global': true
            }
        };
        localStorage.setItem('access_token', 'access-token');
        fetchCurrentSession
            .mockResolvedValueOnce({ data: validSession })
            .mockResolvedValueOnce({ data: updatedSession });
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));

        await act(async () => {
            await currentSession.refreshSession();
        });

        expect(currentSession.businessRole).toBe('ADMINISTRADOR');
        expect(currentSession.permissions).toEqual(['usuarios.manage_users']);
        expect(currentSession.hasCapability('diagnosis.create')).toBe(false);
        expect(currentSession.hasCapability('content.manage_global')).toBe(true);
        expect(fetchCurrentSession).toHaveBeenCalledTimes(2);
    });

    test('401 limpia credenciales y deja la sesión anónima', async () => {
        localStorage.setItem('access_token', 'expired-token');
        localStorage.setItem('refresh_token', 'refresh-token');
        localStorage.setItem('user_info', JSON.stringify({ is_staff: true }));
        fetchCurrentSession.mockRejectedValue({ response: { status: 401 } });

        renderProvider();

        await waitFor(() => expect(currentSession.anonymous).toBe(true));
        expect(localStorage.getItem('access_token')).toBeNull();
        expect(localStorage.getItem('refresh_token')).toBeNull();
        expect(localStorage.getItem('user_info')).toBeNull();
        expect(currentSession.permissions).toEqual([]);
        expect(currentSession.capabilities).toEqual({});
        expect(currentSession.hasCapability('diagnosis.create')).toBe(false);
    });

    test('409 por múltiples roles falla cerrado y conserva el error estable', async () => {
        localStorage.setItem('access_token', 'access-token');
        fetchCurrentSession.mockRejectedValue({
            response: {
                status: 409,
                data: {
                    error: {
                        code: 'MULTIPLE_BUSINESS_ROLES',
                        detail: 'El Usuario tiene múltiples roles de negocio.'
                    }
                }
            }
        });

        renderProvider();

        await waitFor(() => {
            expect(currentSession.status).toBe(SESSION_STATUS.ERROR);
        });
        expect(currentSession.error.code).toBe('MULTIPLE_BUSINESS_ROLES');
        expect(currentSession.error.httpStatus).toBe(409);
        expect(currentSession.authenticated).toBe(false);
        expect(currentSession.businessRole).toBeNull();
        expect(currentSession.permissions).toEqual([]);
        expect(currentSession.capabilities).toEqual({});
        expect(localStorage.getItem('access_token')).toBe('access-token');
    });

    test('un error de red no borra el token ni inventa capacidades', async () => {
        localStorage.setItem('access_token', 'access-token');
        fetchCurrentSession.mockRejectedValue(new Error('network offline'));

        renderProvider();

        await waitFor(() => {
            expect(currentSession.status).toBe(SESSION_STATUS.ERROR);
        });
        expect(currentSession.error.code).toBe('SESSION_CONTEXT_UNAVAILABLE');
        expect(currentSession.user).toBeNull();
        expect(currentSession.businessRole).toBeNull();
        expect(currentSession.permissions).toEqual([]);
        expect(currentSession.capabilities).toEqual({});
        expect(localStorage.getItem('access_token')).toBe('access-token');
    });

    test('ignora is_staff de user_info para toda decisión de autorización', async () => {
        localStorage.setItem('access_token', 'access-token');
        localStorage.setItem('user_info', JSON.stringify({
            is_staff: true,
            business_role: 'ADMINISTRADOR'
        }));
        fetchCurrentSession.mockResolvedValue({
            data: {
                ...validSession,
                business_role: 'CLIENTE',
                permissions: []
            }
        });

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.businessRole).toBe('CLIENTE');
        expect(currentSession.hasRole('ADMINISTRADOR')).toBe(false);
        expect(currentSession.permissions).toEqual([]);
    });

    test('clearSession ofrece limpieza local coherente con logout', async () => {
        mockAuthenticatedSession();
        localStorage.setItem('refresh_token', 'refresh-token');
        localStorage.setItem('user_info', '{}');
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));

        act(() => currentSession.clearSession());

        expect(currentSession.anonymous).toBe(true);
        expect(currentSession.permissions).toEqual([]);
        expect(currentSession.capabilities).toEqual({});
        expect(localStorage.getItem('access_token')).toBeNull();
        expect(localStorage.getItem('refresh_token')).toBeNull();
        expect(localStorage.getItem('user_info')).toBeNull();
    });

    test('refresca al recuperar foco sólo después de 45 segundos', async () => {
        let now = 1000;
        jest.spyOn(Date, 'now').mockImplementation(() => now);
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));

        act(() => window.dispatchEvent(new Event('focus')));
        expect(fetchCurrentSession).toHaveBeenCalledTimes(1);

        now += SESSION_REFRESH_INTERVAL_MS + 1;
        act(() => window.dispatchEvent(new Event('focus')));
        await waitFor(() => expect(fetchCurrentSession).toHaveBeenCalledTimes(2));
    });

    test('refresca cuando la pestaña vuelve a estar visible', async () => {
        let now = 5000;
        jest.spyOn(Date, 'now').mockImplementation(() => now);
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        now += SESSION_REFRESH_INTERVAL_MS + 1;
        Object.defineProperty(document, 'visibilityState', {
            configurable: true,
            value: 'visible'
        });

        act(() => document.dispatchEvent(new Event('visibilitychange')));

        await waitFor(() => expect(fetchCurrentSession).toHaveBeenCalledTimes(2));
    });

    test('deduplica eventos de foco simultáneos', async () => {
        let now = 1000;
        jest.spyOn(Date, 'now').mockImplementation(() => now);
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        const pending = deferred();
        fetchCurrentSession.mockReturnValueOnce(pending.promise);
        now += SESSION_REFRESH_INTERVAL_MS + 1;

        act(() => {
            window.dispatchEvent(new Event('focus'));
            window.dispatchEvent(new Event('focus'));
        });

        expect(fetchCurrentSession).toHaveBeenCalledTimes(2);
        await act(async () => pending.resolve({ data: validSession }));
    });

    test('varios 403 autenticados comparten un refresh y no reenvían la operación', async () => {
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        const pending = deferred();
        fetchCurrentSession.mockReturnValueOnce(pending.promise);

        act(() => {
            emitHttpSessionEvent({
                type: HTTP_SESSION_EVENT.FORBIDDEN,
                accessToken: 'access-token'
            });
            emitHttpSessionEvent({
                type: HTTP_SESSION_EVENT.FORBIDDEN,
                accessToken: 'access-token'
            });
        });

        expect(fetchCurrentSession).toHaveBeenCalledTimes(2);
        await act(async () => pending.resolve({ data: validSession }));
        expect(currentSession.authenticated).toBe(true);
    });

    test('un 403 por ownership conserva la sesión si la autoridad no cambió', async () => {
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        fetchCurrentSession.mockResolvedValueOnce({ data: validSession });

        await act(async () => emitHttpSessionEvent({
            type: HTTP_SESSION_EVENT.FORBIDDEN,
            accessToken: 'access-token'
        }));

        await waitFor(() => expect(fetchCurrentSession).toHaveBeenCalledTimes(2));
        expect(currentSession.authenticated).toBe(true);
        expect(currentSession.permissions).toEqual(validSession.permissions);
    });

    test('un refresh retira permisos, capabilities y actividad laboral revocados', async () => {
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        fetchCurrentSession.mockResolvedValueOnce({
            data: {
                ...validSession,
                business_role: 'CLIENTE',
                permissions: [],
                capabilities: {
                    ...validSession.capabilities,
                    'technical_booking.review': false,
                    'service_formula.manage': false
                },
                profiles: {
                    ...validSession.profiles,
                    personal: {
                        ...validSession.profiles.personal,
                        active: false
                    }
                }
            }
        });

        await act(async () => currentSession.refreshSession());

        expect(currentSession.businessRole).toBe('CLIENTE');
        expect(currentSession.hasPermission('gestion.manage_stock')).toBe(false);
        expect(currentSession.hasCapability('service_formula.manage')).toBe(false);
        expect(currentSession.hasActiveProfile('personal')).toBe(false);
    });

    test('un 401 global autenticado limpia la sesión y comunica su finalización', async () => {
        mockAuthenticatedSession();
        localStorage.setItem('refresh_token', 'refresh-token');
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));

        act(() => emitHttpSessionEvent({
            type: HTTP_SESSION_EVENT.UNAUTHORIZED,
            accessToken: 'access-token'
        }));

        expect(currentSession.anonymous).toBe(true);
        expect(currentSession.sessionNotice).toMatch(/sesión finalizó/i);
        expect(localStorage.getItem('access_token')).toBeNull();
        expect(localStorage.getItem('refresh_token')).toBeNull();
    });

    test('logout durante refresh ignora la respuesta antigua', async () => {
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        const pending = deferred();
        fetchCurrentSession.mockReturnValueOnce(pending.promise);

        let refreshPromise;
        act(() => {
            refreshPromise = currentSession.refreshSession();
            currentSession.clearSession();
        });
        await act(async () => pending.resolve({ data: validSession }));
        await refreshPromise;

        expect(currentSession.anonymous).toBe(true);
        expect(localStorage.getItem('access_token')).toBeNull();
    });

    test('cambio de usuario descarta el refresh de la identidad anterior', async () => {
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        const oldRequest = deferred();
        const newRequest = deferred();
        fetchCurrentSession
            .mockReturnValueOnce(oldRequest.promise)
            .mockReturnValueOnce(newRequest.promise);

        let oldPromise;
        let newPromise;
        act(() => {
            oldPromise = currentSession.refreshSession();
            localStorage.setItem('access_token', 'new-token');
            newPromise = currentSession.refreshSession();
        });
        await act(async () => newRequest.resolve({
            data: {
                ...validSession,
                user: { ...validSession.user, id: 99, email: 'otra@example.com' }
            }
        }));
        await newPromise;
        await act(async () => oldRequest.resolve({ data: validSession }));
        await oldPromise;

        expect(currentSession.user.id).toBe(99);
        expect(currentSession.user.email).toBe('otra@example.com');
    });

    test('error de red en refresh silencioso conserva la proyección', async () => {
        mockAuthenticatedSession();
        renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        fetchCurrentSession.mockRejectedValueOnce(new Error('offline'));

        await act(async () => currentSession.refreshSession());

        expect(currentSession.authenticated).toBe(true);
        expect(currentSession.permissions).toEqual(validSession.permissions);
        expect(currentSession.refreshError).toMatchObject({
            kind: 'network',
            retryable: true
        });
    });

    test('elimina listeners al desmontar', async () => {
        const removeWindow = jest.spyOn(window, 'removeEventListener');
        const removeDocument = jest.spyOn(document, 'removeEventListener');
        mockAuthenticatedSession();
        const view = renderProvider();
        await waitFor(() => expect(currentSession.authenticated).toBe(true));

        view.unmount();

        expect(removeWindow).toHaveBeenCalledWith('focus', expect.any(Function));
        expect(removeDocument).toHaveBeenCalledWith(
            'visibilitychange',
            expect.any(Function)
        );
    });
});
