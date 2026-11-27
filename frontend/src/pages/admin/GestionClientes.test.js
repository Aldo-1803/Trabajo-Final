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
    fireEvent.change(screen.getByLabelText('Email (opcional)'), {
        target: { value: 'ana@test.com' }
    });
    fireEvent.change(screen.getByLabelText('Teléfono (opcional)'), {
        target: { value: '1122334455' }
    });
    fireEvent.change(screen.getByLabelText('Zona'), {
        target: { value: 'Centro' }
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
        axios.post.mockResolvedValue({
            data: {
                created: true,
                recovered: false,
                cliente_id: 31,
                display_name: 'Ana Pérez',
                masked_email: 'a**@test.com',
                masked_phone: '***4455',
                cliente_activo: true,
                web_access_status: 'PENDING_CLAIM',
                operation_id: 'operation-31'
            }
        });
    });

    afterEach(() => consoleError.mockRestore());

    test('abre el modal Nuevo cliente', async () => {
        await renderAndOpenCreateModal();

        expect(screen.getByRole('heading', { name: 'Alta rápida presencial' })).toBeInTheDocument();
        expect(screen.queryByLabelText(/Contraseña/)).not.toBeInTheDocument();
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

        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                '/api/usuarios/asistido/clientes/alta-rapida/',
                {
                    first_name: 'Ana',
                    last_name: 'Pérez',
                    email: 'ana@test.com',
                    telefono: '1122334455',
                    zona: 'Centro',
                    motivo: 'Alta presencial en recepción',
                    medio_alta: 'PRESENCIAL'
                },
                { headers: { 'Idempotency-Key': expect.any(String) } }
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
        expect(await screen.findByText('PENDING_CLAIM')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
        expect(screen.queryByRole('heading', { name: 'Alta rápida presencial' })).not.toBeInTheDocument();
        expect(axios.get.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    test('muestra un conflicto de identidad comprensible', async () => {
        axios.post.mockRejectedValue({
            response: {
                status: 409,
                data: {
                    error: {
                        code: 'EMAIL_ALREADY_EXISTS',
                        detail: 'El email ya pertenece a otra identidad.'
                    }
                }
            }
        });
        await renderAndOpenCreateModal();
        fillRequiredFields();

        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));

        await waitFor(() => {
            expect(notify.error).toHaveBeenCalledWith(
                'El email ya pertenece a otra identidad.'
            );
        });
    });

    test('muestra un mensaje comprensible para teléfono inválido', async () => {
        axios.post.mockRejectedValue({
            response: {
                status: 400,
                data: {
                    error: {
                        code: 'INVALID_PHONE',
                        detail: 'El teléfono es inválido.'
                    }
                }
            }
        });
        await renderAndOpenCreateModal();
        fillRequiredFields();

        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));

        await waitFor(() => {
            expect(notify.error).toHaveBeenCalledWith(
                'El teléfono es inválido.'
            );
        });
    });
});
