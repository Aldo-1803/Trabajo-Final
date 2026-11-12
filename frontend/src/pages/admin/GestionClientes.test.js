import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import GestionClientes from './GestionClientes';
import { notify } from '../../utils/notificaciones';


const mockHasPermission = jest.fn();


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn()
    }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn()
}), { virtual: true });
jest.mock('../../utils/notificaciones', () => ({
    notify: {
        success: jest.fn(),
        error: jest.fn()
    }
}));
jest.mock('../../context/SessionContext', () => ({
    useSession: () => ({
        session: {
            status: 'authenticated',
            businessRole: 'EMPLEADO',
            error: null
        },
        hasPermission: mockHasPermission
    })
}));


const fillRequiredFields = () => {
    fireEvent.change(screen.getByLabelText('Nombre *'), {
        target: { value: 'Ana' }
    });
    fireEvent.change(screen.getByLabelText('Apellido *'), {
        target: { value: 'Pérez' }
    });
    fireEvent.change(screen.getByLabelText('Email *'), {
        target: { value: 'ana@test.com' }
    });
    fireEvent.change(screen.getByLabelText('Teléfono'), {
        target: { value: '1122334455' }
    });
    fireEvent.change(screen.getByLabelText('Zona'), {
        target: { value: 'Centro' }
    });
    fireEvent.change(screen.getByLabelText('Contraseña temporal *'), {
        target: { value: 'Temporal!Cliente2026' }
    });
    fireEvent.change(screen.getByLabelText('Motivo *'), {
        target: { value: 'Alta presencial en recepción' }
    });
};

const renderAndOpenCreateModal = async () => {
    render(<GestionClientes />);
    await screen.findByText('No hay clientes registrados aún.');
    fireEvent.click(screen.getByRole('button', { name: /nuevo cliente/i }));
};


describe('GestionClientes administrative creation', () => {
    let consoleError;

    beforeEach(() => {
        jest.clearAllMocks();
        consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
        localStorage.setItem('access_token', 'test-token');
        mockHasPermission.mockImplementation(
            (permission) => permission === 'usuarios.create_walkin_client'
        );
        axios.get.mockResolvedValue({ data: [] });
        axios.post.mockResolvedValue({ data: { created: true } });
    });

    afterEach(() => consoleError.mockRestore());

    test('abre el modal Nuevo cliente', async () => {
        await renderAndOpenCreateModal();

        expect(screen.getByRole('heading', { name: 'Nuevo cliente' })).toBeInTheDocument();
        expect(screen.getByLabelText('Contraseña temporal *')).toBeInTheDocument();
        expect(screen.queryByLabelText(/is_staff/i)).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/^rol/i)).not.toBeInTheDocument();
    });

    test('oculta Nuevo cliente sin create_walkin_client', async () => {
        mockHasPermission.mockReturnValue(false);

        render(<GestionClientes />);

        await screen.findByText('No hay clientes registrados aún.');
        expect(screen.queryByRole('button', { name: /nuevo cliente/i }))
            .not.toBeInTheDocument();
    });

    test('maneja un 403 del listado sin asumir rol administrador', async () => {
        axios.get.mockRejectedValue({ response: { status: 403 } });

        render(<GestionClientes />);

        expect(await screen.findByText(
            'No tenés permisos para consultar clientes.'
        )).toBeInTheDocument();
        expect(screen.queryByText(/permisos de administrador/i))
            .not.toBeInTheDocument();
    });

    test('envía solo el contrato permitido y maneja el éxito', async () => {
        await renderAndOpenCreateModal();
        fillRequiredFields();

        fireEvent.click(screen.getByRole('button', { name: 'Crear cliente' }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                'http://127.0.0.1:8000/api/usuarios/admin/clientes/crear/',
                {
                    first_name: 'Ana',
                    last_name: 'Pérez',
                    email: 'ana@test.com',
                    telefono: '1122334455',
                    zona: 'Centro',
                    password_temporal: 'Temporal!Cliente2026',
                    motivo: 'Alta presencial en recepción'
                },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
        const payload = axios.post.mock.calls[0][1];
        expect(payload).not.toHaveProperty('is_staff');
        expect(payload).not.toHaveProperty('is_active');
        expect(payload).not.toHaveProperty('role');
        await waitFor(() => {
            expect(notify.success).toHaveBeenCalledWith(
                'Cliente creado correctamente.'
            );
        });
        expect(screen.queryByRole('heading', { name: 'Nuevo cliente' })).not.toBeInTheDocument();
        expect(axios.get.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    test('muestra un mensaje comprensible si el email ya existe', async () => {
        axios.post.mockRejectedValue({
            response: {
                data: { error: { code: 'EMAIL_ALREADY_EXISTS' } }
            }
        });
        await renderAndOpenCreateModal();
        fillRequiredFields();

        fireEvent.click(screen.getByRole('button', { name: 'Crear cliente' }));

        await waitFor(() => {
            expect(notify.error).toHaveBeenCalledWith(
                'Ya existe una cuenta con ese email.'
            );
        });
    });

    test('muestra un mensaje comprensible para password inválida', async () => {
        axios.post.mockRejectedValue({
            response: {
                data: { error: { code: 'INVALID_PASSWORD' } }
            }
        });
        await renderAndOpenCreateModal();
        fillRequiredFields();

        fireEvent.click(screen.getByRole('button', { name: 'Crear cliente' }));

        await waitFor(() => {
            expect(notify.error).toHaveBeenCalledWith(
                'La contraseña temporal no cumple los requisitos de seguridad.'
            );
        });
    });
});
