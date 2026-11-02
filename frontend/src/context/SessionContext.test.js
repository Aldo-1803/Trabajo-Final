import { act, render, screen, waitFor } from '@testing-library/react';

import { fetchCurrentSession } from '../api/sessionApi';
import {
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


describe('SessionProvider', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.clear();
        currentSession = undefined;
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

    test('expone user, BusinessRole, permisos y perfiles del backend', async () => {
        mockAuthenticatedSession();

        renderProvider();

        await waitFor(() => expect(currentSession.authenticated).toBe(true));
        expect(currentSession.user).toEqual(validSession.user);
        expect(currentSession.businessRole).toBe('PROFESIONAL');
        expect(currentSession.permissions).toEqual(validSession.permissions);
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
            permissions: ['usuarios.manage_users']
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
        expect(localStorage.getItem('access_token')).toBeNull();
        expect(localStorage.getItem('refresh_token')).toBeNull();
        expect(localStorage.getItem('user_info')).toBeNull();
    });
});
