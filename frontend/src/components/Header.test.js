import { fireEvent, render, screen } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../context/SessionContext';
import { isNavigationItemVisible } from '../navigation/navigationConfig';
import Header from './Header';


const mockNavigate = jest.fn();


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn() }
}));
jest.mock('../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('./CampanaNotificaciones', () => () => (
    <span data-testid="notification-bell">Notificaciones</span>
));
jest.mock('react-router-dom', () => ({
    Link: ({ to, children, ...props }) => (
        <a href={to} {...props}>{children}</a>
    ),
    useNavigate: () => mockNavigate,
    useLocation: () => ({ pathname: '/' })
}), { virtual: true });


const sessionContext = ({
    businessRole = 'CLIENTE',
    permissions = [],
    clientProfile = false,
    personalProfile = false,
    loading = false,
    status = 'authenticated',
    user = {}
} = {}) => {
    const profiles = {
        cliente: { exists: clientProfile },
        personal: { exists: personalProfile }
    };

    return {
        session: {
            status,
            businessRole,
            permissions,
            profiles,
            error: status === 'error' ? { code: 'ACCESS_ERROR' } : null
        },
        user: {
            id: 1,
            email: 'ana@example.com',
            first_name: 'Ana',
            ...user
        },
        businessRole,
        permissions,
        profiles,
        loading,
        authenticated: status === 'authenticated',
        error: status === 'error' ? { code: 'ACCESS_ERROR' } : null,
        clearSession: jest.fn(),
        hasPermission: (permission) => permissions.includes(permission),
        hasAnyPermission: (required) => (
            required.some((permission) => permissions.includes(permission))
        ),
        hasProfile: (profile) => profiles[profile]?.exists === true
    };
};


const renderHeader = (context) => {
    useSession.mockReturnValue(sessionContext(context));
    return render(<Header />);
};


describe('Header basado en SessionContext', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        axios.get.mockResolvedValue({
            data: { empresa_nombre: '' }
        });
    });

    test('CLIENTE con perfil ve navegación propia de Cliente', () => {
        renderHeader({ businessRole: 'CLIENTE', clientProfile: true });

        expect(screen.getByRole('link', { name: 'Mis Turnos' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Mis Pedidos' })).toBeInTheDocument();
        expect(screen.getByTitle('Carrito de compras')).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument();
    });

    test('EMPLEADO ve Operaciones y no el menú administrativo', () => {
        renderHeader({ businessRole: 'EMPLEADO' });

        expect(screen.getByRole('link', { name: 'Operaciones' })).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Reportes' })).not.toBeInTheDocument();
    });

    test('PROFESIONAL comparte la navegación operativa', () => {
        renderHeader({ businessRole: 'PROFESIONAL' });

        expect(screen.getByRole('link', { name: 'Operaciones' })).toBeInTheDocument();
    });

    test.each(['EMPLEADO', 'PROFESIONAL'])(
        '%s con view_clients ve Gestión de Clientes',
        (businessRole) => {
            renderHeader({
                businessRole,
                permissions: ['usuarios.view_clients']
            });

            expect(screen.getByRole('link', { name: 'Clientes' }))
                .toHaveAttribute('href', '/admin/clientes');
        }
    );

    test('ADMINISTRADOR no depende de is_staff y filtra por permisos', () => {
        renderHeader({
            businessRole: 'ADMINISTRADOR',
            permissions: ['usuarios.manage_users'],
            user: { is_staff: false }
        });

        expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Usuarios' })).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Personal' })).not.toBeInTheDocument();
    });

    test('Usuarios requiere usuarios.manage_users', () => {
        const { rerender } = renderHeader({ businessRole: 'ADMINISTRADOR' });
        expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument();

        useSession.mockReturnValue(sessionContext({
            businessRole: 'ADMINISTRADOR',
            permissions: ['usuarios.manage_users']
        }));
        rerender(<Header />);

        expect(screen.getByRole('link', { name: 'Usuarios' })).toBeInTheDocument();
    });

    test('Personal requiere gestion.manage_personal', () => {
        renderHeader({
            businessRole: 'ADMINISTRADOR',
            permissions: ['gestion.manage_personal']
        });

        expect(screen.getByRole('link', { name: 'Personal' })).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument();
    });

    test.each([
        'gestion.view_reports',
        'gestion.view_financial_reports'
    ])('Reportes aparece con %s para el módulo habilitado', (permission) => {
        renderHeader({
            businessRole: 'ADMINISTRADOR',
            permissions: [permission]
        });

        expect(screen.getByRole('link', { name: 'Reportes' })).toBeInTheDocument();
    });

    test('un permiso efectivo habilita una entrada sin reinterpretar el rol', () => {
        const access = sessionContext({
            businessRole: 'PROFESIONAL',
            permissions: ['gestion.view_reports']
        });

        expect(isNavigationItemVisible({
            requiredPermission: 'gestion.view_reports'
        }, access)).toBe(true);
        expect(access.businessRole).toBe('PROFESIONAL');
    });

    test('PROFESIONAL con perfil Cliente conserva ambas experiencias', () => {
        renderHeader({
            businessRole: 'PROFESIONAL',
            clientProfile: true,
            personalProfile: true
        });

        expect(screen.getByRole('link', { name: 'Operaciones' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Mis Turnos' })).toBeInTheDocument();
        expect(screen.getByTitle('Carrito de compras')).toBeInTheDocument();
    });

    test('la etiqueta muestra el BusinessRole real', () => {
        renderHeader({ businessRole: 'PROFESIONAL' });

        fireEvent.click(screen.getByRole('button', { name: /Ana/ }));

        expect(screen.getByText('PROFESIONAL')).toBeInTheDocument();
    });

    test('un usuario sin rol no recibe navegación privilegiada', () => {
        renderHeader({ businessRole: null });

        expect(screen.queryByRole('link', { name: 'Operaciones' })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument();
    });

    test('loading no muestra navegación ni controles privilegiados', () => {
        renderHeader({
            businessRole: 'ADMINISTRADOR',
            permissions: ['usuarios.manage_users'],
            loading: true,
            status: 'loading'
        });

        expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument();
        expect(screen.queryByTestId('notification-bell')).not.toBeInTheDocument();
    });

    test('el logo usa el landing central de la sesión', () => {
        renderHeader({ businessRole: 'PROFESIONAL' });

        expect(screen.getByRole('link', {
            name: 'Ir al inicio de la sesión'
        })).toHaveAttribute('href', '/operaciones');
    });

    test('permisos técnicos legacy no habilitan módulos pendientes', () => {
        renderHeader({
            businessRole: 'PROFESIONAL',
            permissions: [
                'gestion.create_diagnosis',
                'gestion.view_reports'
            ]
        });

        expect(screen.queryByRole('link', { name: 'Reportes' })).not.toBeInTheDocument();
        expect(screen.queryByText('Diagnóstico')).not.toBeInTheDocument();
    });
});
