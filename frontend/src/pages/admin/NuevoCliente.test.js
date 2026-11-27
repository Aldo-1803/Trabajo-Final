import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import NuevoCliente from './NuevoCliente';


const mockNavigate = jest.fn();

jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn() }
}));
jest.mock('../../context/SessionContext', () => ({ useSession: jest.fn() }));
jest.mock('../../utils/notificaciones', () => ({
    notify: { success: jest.fn(), error: jest.fn() }
}));
jest.mock('react-router-dom', () => ({ useNavigate: () => mockNavigate }), { virtual: true });


const result = {
    created: true,
    recovered: false,
    cliente_id: 41,
    display_name: 'Ana Pérez',
    masked_email: 'a***@test.com',
    masked_phone: null,
    cliente_activo: true,
    web_access_status: 'PENDING_CLAIM',
    operation_id: 'operation-41'
};

const renderNewClient = (permissions = ['usuarios.create_walkin_client']) => {
    useSession.mockReturnValue({
        user: { id: 19 },
        session: {
            status: 'authenticated',
            businessRole: 'EMPLEADO',
            permissions,
            capabilities: {},
            profiles: {
                cliente: { exists: false },
                personal: { exists: false }
            },
            error: null
        },
        hasPermission: (permission) => permissions.includes(permission)
    });
    return render(<NuevoCliente />);
};

const fillForm = () => {
    fireEvent.change(screen.getByLabelText('Nombre *'), { target: { value: 'Ana' } });
    fireEvent.change(screen.getByLabelText('Apellido *'), { target: { value: 'Pérez' } });
    fireEvent.change(screen.getByLabelText('Email (opcional)'), { target: { value: 'ana@test.com' } });
    fireEvent.change(screen.getByLabelText('Motivo *'), { target: { value: 'Alta presencial' } });
};


describe('NuevoCliente independiente', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        sessionStorage.clear();
        axios.post.mockResolvedValue({ data: result });
    });

    test('crea sin contraseña, muestra PENDING_CLAIM y recién finaliza a Operaciones', async () => {
        renderNewClient();
        fillForm();
        expect(screen.queryByLabelText(/Contraseña/)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/usuarios/asistido/clientes/alta-rapida/',
            expect.objectContaining({ email: 'ana@test.com', medio_alta: 'PRESENCIAL' }),
            { headers: { 'Idempotency-Key': expect.any(String) } }
        ));
        expect(await screen.findByText('PENDING_CLAIM')).toBeInTheDocument();
        expect(screen.getByText(/solicitud técnica asistida/i)).toBeInTheDocument();
        expect(mockNavigate).not.toHaveBeenCalled();

        fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
        expect(mockNavigate).toHaveBeenCalledWith('/operaciones', { replace: true });
    });

    test('con view_clients finaliza al listado después de mostrar el resultado', async () => {
        renderNewClient([
            'usuarios.create_walkin_client',
            'usuarios.view_clients'
        ]);
        fillForm();
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));
        await screen.findByText('Cliente creado');
        fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));

        expect(mockNavigate).toHaveBeenCalledWith('/admin/clientes', { replace: true });
    });

    test('recarga el alta ya persistida, sin reenviarla', async () => {
        const first = renderNewClient();
        fillForm();
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));
        await screen.findByText('Cliente creado');
        first.unmount();
        axios.get.mockResolvedValueOnce({ data: result });
        renderNewClient();
        expect(await screen.findByText('Cliente creado')).toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledWith('/api/usuarios/asistido/clientes/alta-rapida/', { params: { operation_id: result.operation_id } });
        expect(axios.post).toHaveBeenCalledTimes(1);
    });

    test('con permiso asistido continúa usando el cliente_id estable', async () => {
        renderNewClient([
            'usuarios.create_walkin_client',
            'gestion.create_turno_for_client'
        ]);
        fillForm();
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));
        await screen.findByText('Cliente creado');
        fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));

        expect(mockNavigate).toHaveBeenCalledWith(
            '/admin/nuevo-turno',
            { replace: true }
        );
        expect(JSON.parse(sessionStorage.getItem('reception.v1.booking.19'))).toEqual({
            clientId: result.cliente_id, altaId: result.operation_id,
        });
    });
});
