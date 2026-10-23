import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import Swal from 'sweetalert2';

import GestionUsuarios from './GestionUsuarios';
import { notify } from '../../utils/notificaciones';


const mockNavigate = jest.fn();


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn(),
        patch: jest.fn()
    }
}));
jest.mock('sweetalert2', () => ({
    __esModule: true,
    default: { fire: jest.fn() }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => mockNavigate
}), { virtual: true });
jest.mock('../../utils/notificaciones', () => ({
    notify: {
        success: jest.fn(),
        error: jest.fn()
    }
}));


const activeUser = {
    id: 10,
    email: 'activa@test.com',
    first_name: 'Cuenta',
    last_name: 'Activa',
    is_staff: false,
    is_active: true,
    business_role: 'CLIENTE'
};

const inactiveUser = {
    ...activeUser,
    id: 11,
    email: 'inactiva@test.com',
    is_active: false
};


describe('GestionUsuarios account status actions', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        axios.post.mockResolvedValue({ data: { changed: true } });
    });

    test('ofrece altas de cliente, Personal y administrador', async () => {
        axios.get.mockResolvedValue({ data: [activeUser] });

        render(<GestionUsuarios />);
        await screen.findByText('activa@test.com');

        fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
        expect(mockNavigate).toHaveBeenCalledWith('/admin/clientes');
        fireEvent.click(screen.getByRole('button', { name: 'Nuevo Personal' }));
        expect(mockNavigate).toHaveBeenCalledWith('/admin/personal');
        expect(screen.getByRole('button', { name: /Nuevo administrador/ })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Nuevo Usuario' })).not.toBeInTheDocument();
    });

    test('abre alta de administrador sin checkbox ni controles técnicos', async () => {
        axios.get.mockResolvedValue({ data: [activeUser] });

        render(<GestionUsuarios />);
        fireEvent.click(await screen.findByRole('button', {
            name: /Nuevo administrador/
        }));

        expect(screen.getByRole('heading', { name: 'Nuevo administrador' })).toBeInTheDocument();
        expect(screen.getByLabelText('Nombre')).toBeInTheDocument();
        expect(screen.getByLabelText('Apellido')).toBeInTheDocument();
        expect(screen.getByLabelText('Email')).toBeInTheDocument();
        expect(screen.getByLabelText('Contraseña temporal')).toBeInTheDocument();
        expect(screen.getByLabelText('Motivo')).toBeInTheDocument();
        expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/staff/i)).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/rol/i)).not.toBeInTheDocument();
    });

    test('envía solo el contrato dedicado y actualiza el listado por BusinessRole', async () => {
        const createdAdministrator = {
            id: 20,
            email: 'ana.admin@example.com',
            first_name: 'Ana',
            last_name: 'Pérez',
            is_staff: false,
            is_active: true,
            business_role: 'ADMINISTRADOR'
        };
        axios.get
            .mockResolvedValueOnce({ data: [activeUser] })
            .mockResolvedValueOnce({ data: [activeUser, createdAdministrator] });
        axios.post.mockResolvedValue({
            data: {
                created: true,
                usuario_id: 20,
                email: 'ana.admin@example.com',
                rol: 'ADMINISTRADOR',
                usuario_activo: true
            }
        });

        render(<GestionUsuarios />);
        fireEvent.click(await screen.findByRole('button', {
            name: /Nuevo administrador/
        }));
        fireEvent.change(screen.getByLabelText('Nombre'), {
            target: { value: 'Ana' }
        });
        fireEvent.change(screen.getByLabelText('Apellido'), {
            target: { value: 'Pérez' }
        });
        fireEvent.change(screen.getByLabelText('Email'), {
            target: { value: 'ana.admin@example.com' }
        });
        fireEvent.change(screen.getByLabelText('Contraseña temporal'), {
            target: { value: 'Temporal!Admin2026' }
        });
        fireEvent.change(screen.getByLabelText('Motivo'), {
            target: { value: 'Incorporación como administradora' }
        });
        fireEvent.click(screen.getByRole('button', {
            name: 'Crear administrador'
        }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                'http://127.0.0.1:8000/api/usuarios/admin/administradores/crear/',
                {
                    first_name: 'Ana',
                    last_name: 'Pérez',
                    email: 'ana.admin@example.com',
                    password_temporal: 'Temporal!Admin2026',
                    motivo: 'Incorporación como administradora'
                },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
        const payload = axios.post.mock.calls[0][1];
        expect(payload).not.toHaveProperty('role');
        expect(payload).not.toHaveProperty('business_role');
        expect(payload).not.toHaveProperty('is_staff');
        expect(payload).not.toHaveProperty('is_superuser');
        expect(payload).not.toHaveProperty('is_active');
        expect(payload).not.toHaveProperty('groups');
        expect(payload).not.toHaveProperty('user_permissions');
        expect(payload).not.toHaveProperty('cliente');
        expect(payload).not.toHaveProperty('personal');
        expect(
            axios.post.mock.calls.some(
                ([url]) => url === 'http://127.0.0.1:8000/api/gestion/admin/usuarios/'
            )
        ).toBe(false);
        await waitFor(() => {
            expect(screen.getByText('ana.admin@example.com')).toBeInTheDocument();
            expect(screen.getByText('Administrador')).toBeInTheDocument();
        });
        expect(notify.success).toHaveBeenCalledWith(
            'Administrador creado exitosamente.'
        );
        expect(screen.queryByRole('heading', {
            name: 'Nuevo administrador'
        })).not.toBeInTheDocument();
    });

    test.each([
        ['EMAIL_ALREADY_EXISTS', 'Ya existe una cuenta con ese email.'],
        ['INVALID_PASSWORD', 'La contraseña temporal no cumple los requisitos de seguridad.'],
        ['PERMISSION_DENIED', 'No tenés permisos para crear administradores.']
    ])('muestra error seguro de onboarding %s', async (code, message) => {
        axios.get.mockResolvedValue({ data: [activeUser] });
        axios.post.mockRejectedValue({
            response: { data: { error: { code } } }
        });

        render(<GestionUsuarios />);
        fireEvent.click(await screen.findByRole('button', {
            name: /Nuevo administrador/
        }));
        fireEvent.change(screen.getByLabelText('Nombre'), {
            target: { value: 'Ana' }
        });
        fireEvent.change(screen.getByLabelText('Apellido'), {
            target: { value: 'Pérez' }
        });
        fireEvent.change(screen.getByLabelText('Email'), {
            target: { value: 'ana.admin@example.com' }
        });
        fireEvent.change(screen.getByLabelText('Contraseña temporal'), {
            target: { value: 'Temporal!Admin2026' }
        });
        fireEvent.change(screen.getByLabelText('Motivo'), {
            target: { value: 'Incorporación como administradora' }
        });
        fireEvent.click(screen.getByRole('button', {
            name: 'Crear administrador'
        }));

        await waitFor(() => {
            expect(notify.error).toHaveBeenCalledWith(message);
        });
        expect(screen.getByRole('heading', {
            name: 'Nuevo administrador'
        })).toBeInTheDocument();
    });

    test('desactiva mediante la action semántica y envía motivo', async () => {
        axios.get.mockResolvedValue({ data: [activeUser] });
        Swal.fire.mockResolvedValue({
            isConfirmed: true,
            value: 'Baja administrativa'
        });

        render(<GestionUsuarios />);
        fireEvent.click(await screen.findByRole('button', {
            name: 'Desactivar'
        }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                'http://127.0.0.1:8000/api/gestion/admin/usuarios/10/desactivar-cuenta/',
                { motivo: 'Baja administrativa' },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
        expect(axios.patch).not.toHaveBeenCalled();
        expect(notify.success).toHaveBeenCalledWith(
            'Cuenta desactivada correctamente.'
        );
    });

    test('reactiva mediante la action semántica y actualiza el listado', async () => {
        axios.get.mockResolvedValue({ data: [inactiveUser] });
        Swal.fire.mockResolvedValue({
            isConfirmed: true,
            value: 'Reincorporación aprobada'
        });

        render(<GestionUsuarios />);
        fireEvent.click(await screen.findByRole('button', {
            name: 'Reactivar'
        }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                'http://127.0.0.1:8000/api/gestion/admin/usuarios/11/reactivar-cuenta/',
                { motivo: 'Reincorporación aprobada' },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
        expect(axios.get.mock.calls.length).toBeGreaterThanOrEqual(2);
        expect(axios.patch).not.toHaveBeenCalled();
        expect(notify.success).toHaveBeenCalledWith(
            'Cuenta reactivada correctamente.'
        );
    });

    test('muestra un mensaje comprensible para el último administrador', async () => {
        axios.get.mockResolvedValue({ data: [activeUser] });
        Swal.fire.mockResolvedValue({
            isConfirmed: true,
            value: 'Baja administrativa'
        });
        axios.post.mockRejectedValue({
            response: {
                data: { error: { code: 'LAST_ACTIVE_ADMIN' } }
            }
        });

        render(<GestionUsuarios />);
        fireEvent.click(await screen.findByRole('button', {
            name: 'Desactivar'
        }));

        await waitFor(() => {
            expect(notify.error).toHaveBeenCalledWith(
                'No se puede desactivar al último administrador activo.'
            );
        });
    });
});
