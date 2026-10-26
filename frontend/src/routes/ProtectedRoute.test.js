import { render, screen } from '@testing-library/react';

import { useSession } from '../context/SessionContext';
import ProtectedRoute from './ProtectedRoute';


jest.mock('../context/SessionContext', () => ({
    SESSION_STATUS: {
        LOADING: 'loading',
        AUTHENTICATED: 'authenticated',
        ANONYMOUS: 'anonymous',
        ERROR: 'error'
    },
    useSession: jest.fn()
}));
jest.mock('react-router-dom', () => ({
    Navigate: ({ to }) => <span data-testid="redirect">{to}</span>
}), { virtual: true });


const protectedContent = <div>Contenido protegido</div>;


const sessionContext = ({
    status = 'authenticated',
    businessRole = 'CLIENTE',
    permissions = [],
    clientProfile = false,
    personalProfile = false,
    personalActive = false
} = {}) => {
    const profiles = {
        cliente: { exists: clientProfile },
        personal: { exists: personalProfile || businessRole === 'PROFESIONAL', active: personalActive }
    };

    return {
        status,
        businessRole,
        loading: status === 'loading',
        hasPermission: (permission) => permissions.includes(permission),
        hasAnyPermission: (required) => (
            required.some((permission) => permissions.includes(permission))
        ),
        hasRole: (role) => businessRole === role,
        hasProfile: (profile) => profiles[profile]?.exists === true,
        hasActiveProfile: (profile) => (
            profiles[profile]?.exists === true && profiles[profile]?.active === true
        )
    };
};


const renderDirectUrl = (path, routeProps = {}, context = {}) => {
    window.history.replaceState({}, '', path);
    useSession.mockReturnValue(sessionContext(context));

    return render(
        <ProtectedRoute {...routeProps}>
            {protectedContent}
        </ProtectedRoute>
    );
};


const expectRedirect = (path) => {
    expect(screen.getByTestId('redirect')).toHaveTextContent(path);
    expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
};


describe('ProtectedRoute declarativo con acceso por URL directa', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.clear();
    });

    test('anonymous redirige a login aunque exista información local legacy', () => {
        localStorage.setItem('access_token', 'stale-token');
        localStorage.setItem('user_info', JSON.stringify({ is_staff: true }));

        renderDirectUrl('/admin/usuarios', {
            requiredPermission: 'usuarios.manage_users'
        }, { status: 'anonymous' });

        expectRedirect('/login');
    });

    test('loading no renderiza contenido protegido', () => {
        renderDirectUrl('/admin/usuarios', {
            requiredPermission: 'usuarios.manage_users'
        }, {
            status: 'loading',
            permissions: ['usuarios.manage_users']
        });

        expect(screen.getByRole('status')).toHaveTextContent('Cargando sesión...');
        expect(screen.queryByText('Contenido protegido')).not.toBeInTheDocument();
        expect(screen.queryByTestId('redirect')).not.toBeInTheDocument();
    });

    test.each(['EMPLEADO', 'PROFESIONAL', 'ADMINISTRADOR'])(
        '%s con permiso efectivo entra directamente a /operaciones',
        (businessRole) => {
            renderDirectUrl('/operaciones', {
                requiredAnyPermission: [
                    'gestion.view_global_agenda',
                    'usuarios.create_walkin_client',
                    'gestion.create_turno_for_client'
                ]
            }, {
                businessRole,
                permissions: ['gestion.view_global_agenda']
            });

            expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
        }
    );

    test('sin permisos efectivos no entra directamente a /operaciones', () => {
        renderDirectUrl('/operaciones', {
            requiredAnyPermission: [
                'gestion.view_global_agenda',
                'usuarios.create_walkin_client',
                'gestion.create_turno_for_client'
            ]
        }, { businessRole: 'PROFESIONAL' });

        expectRedirect('/acceso-denegado');
    });

    test('un perfil Cliente permite entrar directamente a /perfil', () => {
        renderDirectUrl('/perfil', {
            requiredProfile: 'cliente'
        }, { businessRole: 'CLIENTE', clientProfile: true });

        expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });

    test('PROFESIONAL con perfil Cliente también entra a /perfil', () => {
        renderDirectUrl('/perfil', {
            requiredProfile: 'cliente'
        }, { businessRole: 'PROFESIONAL', clientProfile: true });

        expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });

    test('Personal activo entra directamente a mi agenda laboral sin agenda global', () => {
        renderDirectUrl('/mi-agenda-laboral', {
            requiredActiveProfile: 'personal'
        }, {
            businessRole: 'PROFESIONAL',
            personalProfile: true,
            personalActive: true
        });

        expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });

    test('Personal inactivo no entra a mi agenda laboral', () => {
        renderDirectUrl('/mi-agenda-laboral', {
            requiredActiveProfile: 'personal'
        }, {
            businessRole: 'PROFESIONAL',
            personalProfile: true,
            personalActive: false
        });

        expectRedirect('/acceso-denegado');
    });

    test('Cliente sin perfil Personal no entra a mi agenda laboral', () => {
        renderDirectUrl('/mi-agenda-laboral', {
            requiredActiveProfile: 'personal'
        }, {
            businessRole: 'CLIENTE',
            clientProfile: true
        });

        expectRedirect('/acceso-denegado');
    });

    test('PROFESIONAL con Cliente y Personal activos conserva agenda laboral', () => {
        renderDirectUrl('/mi-agenda-laboral', {
            requiredActiveProfile: 'personal'
        }, {
            businessRole: 'PROFESIONAL',
            clientProfile: true,
            personalProfile: true,
            personalActive: true
        });

        expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });

    test('manage_users permite entrar directamente a Usuarios', () => {
        renderDirectUrl('/admin/usuarios', {
            requiredPermission: 'usuarios.manage_users'
        }, {
            businessRole: 'ADMINISTRADOR',
            permissions: ['usuarios.manage_users']
        });

        expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });

    test('sin manage_users redirige a acceso denegado', () => {
        renderDirectUrl('/admin/usuarios', {
            requiredPermission: 'usuarios.manage_users'
        }, { businessRole: 'ADMINISTRADOR' });

        expectRedirect('/acceso-denegado');
    });

    test.each(['EMPLEADO', 'PROFESIONAL'])(
        '%s con view_clients entra directamente a Gestión de Clientes',
        (businessRole) => {
            renderDirectUrl('/admin/clientes', {
                requiredPermission: 'usuarios.view_clients'
            }, {
                businessRole,
                permissions: ['usuarios.view_clients']
            });

            expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
        }
    );

    test('sin view_clients no entra directamente a Gestión de Clientes', () => {
        renderDirectUrl('/admin/clientes', {
            requiredPermission: 'usuarios.view_clients'
        }, { businessRole: 'EMPLEADO' });

        expectRedirect('/acceso-denegado');
    });

    test.each(['EMPLEADO', 'PROFESIONAL', 'ADMINISTRADOR'])(
        '%s con view_global_agenda entra directamente a Gestión de Turnos',
        (businessRole) => {
            renderDirectUrl('/admin/turnos', {
                requiredPermission: 'gestion.view_global_agenda'
            }, {
                businessRole,
                permissions: ['gestion.view_global_agenda']
            });

            expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
        }
    );

    test('sin view_global_agenda no entra directamente a Gestión de Turnos', () => {
        renderDirectUrl('/admin/turnos', {
            requiredPermission: 'gestion.view_global_agenda'
        }, { businessRole: 'ADMINISTRADOR' });

        expectRedirect('/acceso-denegado');
    });

    test.each(['EMPLEADO', 'PROFESIONAL', 'ADMINISTRADOR'])(
        '%s con create_turno_for_client entra a Nuevo Turno',
        (businessRole) => {
            renderDirectUrl('/admin/nuevo-turno', {
                requiredPermission: 'gestion.create_turno_for_client'
            }, {
                businessRole,
                permissions: ['gestion.create_turno_for_client']
            });

            expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
        }
    );

    test('is_staff conceptual sin create_turno_for_client no entra a Nuevo Turno', () => {
        renderDirectUrl('/admin/nuevo-turno', {
            requiredPermission: 'gestion.create_turno_for_client'
        }, { businessRole: 'ADMINISTRADOR' });

        expectRedirect('/acceso-denegado');
    });

    test('un permiso individual habilita la ruta sin inferir el rol', () => {
        renderDirectUrl('/modulo-preparado', {
            requiredPermission: 'gestion.view_reports'
        }, {
            businessRole: 'PROFESIONAL',
            permissions: ['gestion.view_reports']
        });

        expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });

    test.each([
        'gestion.view_reports',
        'gestion.view_financial_reports'
    ])('requiredAnyPermission acepta %s', (permission) => {
        renderDirectUrl('/admin/reportes', {
            requiredAnyPermission: [
                'gestion.view_reports',
                'gestion.view_financial_reports'
            ]
        }, {
            businessRole: 'ADMINISTRADOR',
            permissions: [permission]
        });

        expect(screen.getByText('Contenido protegido')).toBeInTheDocument();
    });

    test('ADMINISTRADOR sin permiso no atraviesa una ruta con permiso requerido', () => {
        renderDirectUrl('/admin/auditoria', {
            requiredPermission: 'gestion.view_audit'
        }, { businessRole: 'ADMINISTRADOR' });

        expectRedirect('/acceso-denegado');
    });

    test('businessRole null falla cerrado', () => {
        renderDirectUrl('/perfil', {
            requiredProfile: 'cliente'
        }, { businessRole: null, clientProfile: true });

        expectRedirect('/cuenta-sin-acceso');
    });

    test('MULTIPLE_BUSINESS_ROLES redirige al error de acceso', () => {
        renderDirectUrl('/admin/usuarios', {
            requiredPermission: 'usuarios.manage_users'
        }, {
            status: 'error',
            businessRole: null,
            permissions: ['usuarios.manage_users']
        });

        expectRedirect('/error-acceso');
    });
});
