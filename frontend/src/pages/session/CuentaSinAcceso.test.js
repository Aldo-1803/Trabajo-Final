import { render, screen } from '@testing-library/react';

import { useSession } from '../../context/SessionContext';
import CuentaSinAcceso from './CuentaSinAcceso';


jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('react-router-dom', () => ({
    Navigate: ({to}) => <span data-testid="redirect">{to}</span>
}), {virtual: true});


const sessionContext = ({session: sessionOverrides = {}, ...overrides} = {}) => ({
    authenticated: true,
    loading: false,
    ...overrides,
    session: {
        status: 'authenticated',
        businessRole: 'ADMINISTRADOR',
        permissions: [],
        capabilities: {},
        profiles: {
            cliente: {exists: false, active: null},
            personal: {exists: false, active: null}
        },
        error: null,
        ...sessionOverrides
    }
});


describe('CuentaSinAcceso', () => {
    test('informa de forma estable cuando no existe superficie autorizada', () => {
        useSession.mockReturnValue(sessionContext());

        render(<CuentaSinAcceso />);

        expect(screen.getByRole('heading', {
            name: 'Cuenta sin acceso disponible'
        })).toBeInTheDocument();
        expect(screen.queryByTestId('redirect')).not.toBeInTheDocument();
    });

    test('no crea un bucle para un rol configurado sin permisos', () => {
        useSession.mockReturnValue(sessionContext({
            session: {businessRole: 'PROFESIONAL'}
        }));

        render(<CuentaSinAcceso />);

        expect(screen.queryByTestId('redirect')).not.toBeInTheDocument();
    });

    test('si aparece una superficie autorizada redirige a ella', () => {
        useSession.mockReturnValue(sessionContext({
            session: {
                permissions: ['usuarios.manage_users']
            }
        }));

        render(<CuentaSinAcceso />);

        expect(screen.getByTestId('redirect')).toHaveTextContent(
            '/admin/usuarios'
        );
    });

    test('una sesión no autenticada vuelve a login', () => {
        useSession.mockReturnValue(sessionContext({authenticated: false}));

        render(<CuentaSinAcceso />);

        expect(screen.getByTestId('redirect')).toHaveTextContent('/login');
    });
});
