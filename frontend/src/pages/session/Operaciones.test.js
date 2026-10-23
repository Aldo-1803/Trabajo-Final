import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import Operaciones from './Operaciones';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn() }
}));
jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('react-router-dom', () => ({
    Link: ({ to, children, ...props }) => (
        <a href={to} {...props}>{children}</a>
    )
}), { virtual: true });


const sessionContext = ({
    businessRole = 'EMPLEADO',
    permissions = [],
    isStaff = false
} = {}) => ({
    user: {
        first_name: 'Ana',
        email: 'ana@example.com',
        is_staff: isStaff
    },
    businessRole,
    permissions,
    loading: false,
    hasPermission: (permission) => permissions.includes(permission)
});


const renderOperations = (context = {}) => {
    useSession.mockReturnValue(sessionContext(context));
    return render(<Operaciones />);
};


describe('Operaciones por permisos efectivos', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        axios.get.mockResolvedValue({ data: [] });
    });

    test.each(['EMPLEADO', 'PROFESIONAL'])(
        '%s con view_global_agenda ve Turnos de hoy y Ver agenda',
        async (businessRole) => {
            renderOperations({
                businessRole,
                permissions: ['gestion.view_global_agenda']
            });

            expect(screen.getByRole('heading', { name: 'Turnos de hoy' }))
                .toBeInTheDocument();
            expect(screen.getByRole('link', { name: 'Ver agenda' }))
                .toHaveAttribute('href', '/admin/turnos');
            await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));
            expect(axios.get.mock.calls[0][1].params).toHaveProperty('fecha');
        }
    );

    test('ADMINISTRADOR is_staff=false usa view_global_agenda', async () => {
        renderOperations({
            businessRole: 'ADMINISTRADOR',
            permissions: ['gestion.view_global_agenda'],
            isStaff: false
        });

        expect(screen.getByRole('heading', { name: 'Turnos de hoy' }))
            .toBeInTheDocument();
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));
    });

    test('create_walkin_client muestra Nuevo cliente sin consultar agenda', () => {
        renderOperations({
            businessRole: 'EMPLEADO',
            permissions: ['usuarios.create_walkin_client']
        });

        expect(screen.getByRole('link', { name: 'Nuevo cliente' }))
            .toHaveAttribute('href', '/admin/clientes');
        expect(screen.queryByText('Turnos de hoy')).not.toBeInTheDocument();
        expect(axios.get).not.toHaveBeenCalled();
    });

    test('BusinessRole e is_staff no habilitan agenda sin permiso', () => {
        renderOperations({
            businessRole: 'ADMINISTRADOR',
            permissions: [],
            isStaff: true
        });

        expect(screen.queryByText('Turnos de hoy')).not.toBeInTheDocument();
        expect(screen.getByText('No hay operaciones habilitadas para esta cuenta.'))
            .toBeInTheDocument();
        expect(axios.get).not.toHaveBeenCalled();
    });
});
