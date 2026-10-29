import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { fetchCurrentSession } from '../../api/sessionApi';
import { SessionProvider } from '../../context/SessionContext';
import Login from './Login';


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        post: jest.fn(),
        get: jest.fn(),
        defaults: {
            headers: { common: {} }
        }
    }
}));
jest.mock('../../api/sessionApi', () => ({
    fetchCurrentSession: jest.fn()
}));


const mockNavigate = jest.fn();


jest.mock('react-router-dom', () => ({
    useNavigate: () => mockNavigate
}), { virtual: true });


const sessionPayload = (businessRole, overrides = {}) => ({
    user: {
        id: 42,
        email: 'ana@example.com',
        first_name: 'Ana',
        last_name: 'Pérez',
        is_active: true
    },
    business_role: businessRole,
    permissions: [],
    profiles: {
        cliente: { exists: false, id: null, active: null },
        personal: {
            exists: false,
            id: null,
            active: null,
            function_role: null
        }
    },
    ...overrides
});


const renderLogin = () => render(
    <SessionProvider>
        <Login />
    </SessionProvider>
);


const submitLogin = async () => {
    fireEvent.change(screen.getByPlaceholderText('ejemplo@correo.com'), {
        target: { value: 'ana@example.com' }
    });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), {
        target: { value: 'secret' }
    });
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar Sesión' }));
};


describe('Login con contexto de sesión', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.clear();
        axios.post.mockResolvedValue({
            data: { access: 'new-access', refresh: 'new-refresh' }
        });
    });

    test('consulta /me mediante refreshSession antes de navegar', async () => {
        fetchCurrentSession.mockResolvedValue({
            data: sessionPayload('ADMINISTRADOR', {
                user: {
                    ...sessionPayload('ADMINISTRADOR').user,
                    is_staff: false
                }
            })
        });
        renderLogin();

        await submitLogin();

        await waitFor(() => {
            expect(mockNavigate).toHaveBeenCalledWith(
                '/admin-dashboard',
                { replace: true }
            );
        });
        expect(fetchCurrentSession).toHaveBeenCalledWith('new-access');
        expect(axios.post.mock.invocationCallOrder[0]).toBeLessThan(
            fetchCurrentSession.mock.invocationCallOrder[0]
        );
        expect(axios.get).not.toHaveBeenCalled();
    });

    test('deriva user_info de /me sin persistir is_staff como autoridad', async () => {
        fetchCurrentSession.mockResolvedValue({
            data: sessionPayload('CLIENTE')
        });
        renderLogin();

        await submitLogin();

        await waitFor(() => {
            expect(mockNavigate).toHaveBeenCalledWith(
                '/perfil',
                { replace: true }
            );
        });
        const userInfo = JSON.parse(localStorage.getItem('user_info'));
        expect(userInfo.email).toBe('ana@example.com');
        expect(userInfo).not.toHaveProperty('is_staff');
        expect(userInfo).not.toHaveProperty('business_role');
    });

    test('una sesión existente usa SessionContext para resolver el landing', async () => {
        localStorage.setItem('access_token', 'existing-access');
        fetchCurrentSession.mockResolvedValue({
            data: sessionPayload('PROFESIONAL')
        });

        renderLogin();

        await waitFor(() => {
            expect(mockNavigate).toHaveBeenCalledWith(
                '/operaciones',
                { replace: true }
            );
        });
        expect(fetchCurrentSession).toHaveBeenCalledWith('existing-access');
        expect(axios.get).not.toHaveBeenCalled();
    });

    test('múltiples BusinessRole navegan al error seguro sin fallback Cliente', async () => {
        localStorage.setItem('access_token', 'existing-access');
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

        renderLogin();

        await waitFor(() => {
            expect(mockNavigate).toHaveBeenCalledWith(
                '/error-acceso',
                { replace: true }
            );
        });
        expect(mockNavigate).not.toHaveBeenCalledWith(
            '/perfil',
            expect.anything()
        );
    });

    test('un rol null navega a cuenta sin acceso', async () => {
        localStorage.setItem('access_token', 'existing-access');
        fetchCurrentSession.mockResolvedValue({
            data: sessionPayload(null)
        });

        renderLogin();

        await waitFor(() => {
            expect(mockNavigate).toHaveBeenCalledWith(
                '/cuenta-sin-acceso',
                { replace: true }
            );
        });
    });
});
