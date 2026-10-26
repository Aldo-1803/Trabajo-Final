import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import NuevoCliente from './NuevoCliente';


const mockNavigate = jest.fn();

jest.mock('axios', () => ({
    __esModule: true,
    default: { post: jest.fn() }
}));
jest.mock('../../context/SessionContext', () => ({ useSession: jest.fn() }));
jest.mock('../../utils/notificaciones', () => ({
    notify: { success: jest.fn(), error: jest.fn() }
}));
jest.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }), { virtual: true });


const renderNewClient = (permissions = ['usuarios.create_walkin_client']) => {
    useSession.mockReturnValue({
        session: { status: 'authenticated', businessRole: 'EMPLEADO', error: null },
        hasPermission: (permission) => permissions.includes(permission)
    });
    return render(<NuevoCliente />);
};

const fillForm = () => {
    fireEvent.change(screen.getByLabelText('Nombre *'), { target: { value: 'Ana' } });
    fireEvent.change(screen.getByLabelText('Apellido *'), { target: { value: 'Pérez' } });
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'ana@test.com' } });
    fireEvent.change(screen.getByLabelText('Contraseña temporal *'), { target: { value: 'Temporal!Cliente2026' } });
    fireEvent.change(screen.getByLabelText('Motivo *'), { target: { value: 'Alta presencial' } });
};


describe('NuevoCliente independiente', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'create-token');
        axios.post.mockResolvedValue({ data: { created: true } });
    });

    test('create_walkin_client sin view_clients crea y vuelve a Operaciones', async () => {
        renderNewClient();
        fillForm();
        fireEvent.click(screen.getByRole('button', { name: 'Crear cliente' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/usuarios/admin/clientes/crear/',
            expect.objectContaining({ email: 'ana@test.com' }),
            { headers: { Authorization: 'Bearer create-token' } }
        ));
        expect(mockNavigate).toHaveBeenCalledWith('/operaciones', { replace: true });
    });

    test('con view_clients vuelve al listado después del alta', async () => {
        renderNewClient([
            'usuarios.create_walkin_client',
            'usuarios.view_clients'
        ]);
        fillForm();
        fireEvent.click(screen.getByRole('button', { name: 'Crear cliente' }));

        await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith(
            '/admin/clientes',
            { replace: true }
        ));
    });
});
