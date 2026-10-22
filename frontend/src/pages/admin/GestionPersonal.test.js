import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import axios from 'axios';

import GestionPersonal from './GestionPersonal';
import { notify } from '../../utils/notificaciones';


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn(),
        put: jest.fn()
    }
}));
jest.mock('../../utils/notificaciones', () => ({
    notify: {
        success: jest.fn(),
        error: jest.fn(),
        info: jest.fn()
    }
}));


const personalSinUsuario = {
    id: 10,
    nombre: 'Sin',
    apellido: 'Acceso',
    rol: 'asistente',
    email: 'contacto-personal@test.com',
    telefono: '111',
    activo: true,
    usuario: null,
    usuario_email: null,
    usuario_activo: null,
    usuario_business_role: null,
    realiza_diagnostico: false,
    realiza_lavado: true,
    realiza_color: false
};

const personalConUsuario = {
    id: 20,
    nombre: 'Con',
    apellido: 'Cuenta',
    rol: 'colorista',
    email: 'contacto-vinculado@test.com',
    telefono: '222',
    activo: false,
    usuario: 50,
    usuario_email: 'cuenta@test.com',
    usuario_activo: false,
    usuario_business_role: 'PROFESIONAL',
    realiza_diagnostico: true,
    realiza_lavado: false,
    realiza_color: true
};

const usuarios = [
    {
        id: 50,
        email: 'cuenta@test.com',
        first_name: 'Ya',
        last_name: 'Vinculado',
        business_role: 'PROFESIONAL',
        is_active: true
    },
    {
        id: 88,
        email: 'cliente@test.com',
        first_name: 'Cliente',
        last_name: 'Disponible',
        business_role: 'CLIENTE',
        is_active: true
    }
];

const setupApi = () => {
    axios.get.mockImplementation((url) => {
        if (url.includes('/admin/usuarios/')) {
            return Promise.resolve({ data: { results: usuarios } });
        }
        return Promise.resolve({
            data: [personalSinUsuario, personalConUsuario]
        });
    });
    axios.post.mockResolvedValue({ data: {} });
};

const renderLoaded = async () => {
    render(<GestionPersonal />);
    await screen.findByText('Sin Acceso');
};

const openCreateAccess = async () => {
    await renderLoaded();
    const row = screen.getByText('Sin Acceso').closest('tr');
    fireEvent.click(within(row).getByRole('button', { name: 'Crear acceso' }));
};

const fillCreateAccess = () => {
    fireEvent.change(screen.getByLabelText('Email *'), {
        target: { value: 'nuevo-acceso@test.com' }
    });
    fireEvent.change(screen.getByLabelText('Contraseña temporal *'), {
        target: { value: 'Temporary!Access2026' }
    });
    fireEvent.change(screen.getByLabelText('Rol de acceso *'), {
        target: { value: 'ADMINISTRADOR' }
    });
    fireEvent.change(screen.getByLabelText('Motivo *'), {
        target: { value: 'Alta de acceso laboral' }
    });
};


describe('GestionPersonal access UI', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        setupApi();
    });

    test('separa el estado laboral del digital y muestra acciones solo sin Usuario', async () => {
        await renderLoaded();

        const unlinkedRow = screen.getByText('Sin Acceso').closest('tr');
        expect(unlinkedRow).toHaveTextContent('Personal: Activo');
        expect(unlinkedRow).toHaveTextContent('Acceso al sistema: No');
        expect(within(unlinkedRow).getByRole('button', { name: 'Crear acceso' })).toBeInTheDocument();
        expect(within(unlinkedRow).getByRole('button', { name: 'Vincular cuenta existente' })).toBeInTheDocument();
        expect(within(unlinkedRow).getByRole('button', { name: 'Desactivar' })).toBeInTheDocument();
        expect(within(unlinkedRow).queryByRole('button', { name: 'Reactivar' })).not.toBeInTheDocument();
        expect(within(unlinkedRow).queryByRole('button', { name: 'Revocar acceso laboral' })).not.toBeInTheDocument();
        expect(within(unlinkedRow).queryByRole('button', { name: 'Revocar acceso total' })).not.toBeInTheDocument();

        const linkedRow = screen.getByText('Con Cuenta').closest('tr');
        expect(linkedRow).toHaveTextContent('Personal: Inactivo');
        expect(linkedRow).toHaveTextContent('Acceso al sistema: Sí');
        expect(linkedRow).toHaveTextContent('cuenta@test.com');
        expect(linkedRow).toHaveTextContent('Cuenta: Inactiva');
        expect(linkedRow).toHaveTextContent('Rol: PROFESIONAL');
        expect(within(linkedRow).queryByRole('button', { name: 'Crear acceso' })).not.toBeInTheDocument();
        expect(within(linkedRow).queryByRole('button', { name: 'Vincular cuenta existente' })).not.toBeInTheDocument();
        expect(within(linkedRow).getByRole('button', { name: 'Reactivar' })).toBeInTheDocument();
        expect(within(linkedRow).getByRole('button', { name: 'Revocar acceso laboral' })).toBeInTheDocument();
        expect(within(linkedRow).getByRole('button', { name: 'Revocar acceso total' })).toBeInTheDocument();
    });

    test('no ofrece Eliminar ni dispone de un consumidor axios.delete', async () => {
        await renderLoaded();

        expect(screen.queryByRole('button', { name: /eliminar/i })).not.toBeInTheDocument();
        expect(axios.delete).toBeUndefined();
    });

    test('Desactivar usa el endpoint semántico con motivo y nunca DELETE', async () => {
        await renderLoaded();
        const row = screen.getByText('Sin Acceso').closest('tr');
        fireEvent.click(within(row).getByRole('button', { name: 'Desactivar' }));

        expect(screen.getByRole('heading', { name: 'Desactivar Personal' })).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText('Motivo *'), {
            target: { value: 'Fin temporal de actividad' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                'http://127.0.0.1:8000/api/gestion/personal/10/desactivar/',
                { motivo: 'Fin temporal de actividad' },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
        expect(axios.delete).toBeUndefined();
    });

    test.each([
        ['Reactivar', 'reactivar'],
        ['Revocar acceso laboral', 'revocar-acceso-laboral'],
        ['Revocar acceso total', 'revocar-acceso-total']
    ])('%s usa su endpoint POST explícito', async (buttonName, endpoint) => {
        await renderLoaded();
        const row = screen.getByText('Con Cuenta').closest('tr');
        fireEvent.click(within(row).getByRole('button', { name: buttonName }));
        fireEvent.change(screen.getByLabelText('Motivo *'), {
            target: { value: 'Decisión administrativa explícita' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                `http://127.0.0.1:8000/api/gestion/personal/20/${endpoint}/`,
                { motivo: 'Decisión administrativa explícita' },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
    });

    test('Crear acceso abre modal y envía exclusivamente el contrato laboral', async () => {
        await openCreateAccess();

        expect(screen.getByRole('heading', { name: 'Crear acceso' })).toBeInTheDocument();
        expect(screen.queryByRole('option', { name: 'Cliente' })).not.toBeInTheDocument();
        fillCreateAccess();
        fireEvent.click(screen.getAllByRole('button', { name: 'Crear acceso' }).at(-1));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                'http://127.0.0.1:8000/api/gestion/personal/10/crear-acceso/',
                {
                    email: 'nuevo-acceso@test.com',
                    password_temporal: 'Temporary!Access2026',
                    role: 'ADMINISTRADOR',
                    motivo: 'Alta de acceso laboral'
                },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
        const payload = axios.post.mock.calls[0][1];
        expect(payload).not.toHaveProperty('is_staff');
        expect(payload).not.toHaveProperty('is_superuser');
        expect(payload).not.toHaveProperty('is_active');
        expect(payload).not.toHaveProperty('groups');
        expect(payload).not.toHaveProperty('user_permissions');
        expect(payload).not.toHaveProperty('rol');
    });

    test('éxito de Crear acceso recarga, limpia y no vuelve a mostrar la contraseña', async () => {
        await openCreateAccess();
        fillCreateAccess();
        fireEvent.click(screen.getAllByRole('button', { name: 'Crear acceso' }).at(-1));

        await waitFor(() => {
            expect(notify.success).toHaveBeenCalledWith(
                'Acceso creado correctamente para nuevo-acceso@test.com.'
            );
        });
        expect(axios.get.mock.calls.filter(([url]) => url.includes('/personal/'))).toHaveLength(2);
        expect(screen.queryByLabelText('Contraseña temporal *')).not.toBeInTheDocument();

        const row = screen.getByText('Sin Acceso').closest('tr');
        fireEvent.click(within(row).getByRole('button', { name: 'Crear acceso' }));
        expect(screen.getByLabelText('Contraseña temporal *')).toHaveValue('');
    });

    test('EMAIL_ALREADY_EXISTS sugiere vincular sin cambiar automáticamente de flujo', async () => {
        axios.post.mockRejectedValue({
            response: { data: { error: { code: 'EMAIL_ALREADY_EXISTS' } } }
        });
        await openCreateAccess();
        fillCreateAccess();
        fireEvent.click(screen.getAllByRole('button', { name: 'Crear acceso' }).at(-1));

        await waitFor(() => {
            expect(notify.error).toHaveBeenCalledWith(
                'Ya existe una cuenta con ese email. Puede usar Vincular cuenta existente.'
            );
        });
        expect(screen.getByRole('heading', { name: 'Crear acceso' })).toBeInTheDocument();
        expect(screen.queryByRole('heading', { name: 'Vincular cuenta existente' })).not.toBeInTheDocument();
    });

    test('Vincular cuenta muestra selector seguro y excluye usuarios ya asociados', async () => {
        await renderLoaded();
        const row = screen.getByText('Sin Acceso').closest('tr');
        fireEvent.click(within(row).getByRole('button', { name: 'Vincular cuenta existente' }));

        expect(await screen.findByRole('heading', { name: 'Vincular cuenta existente' })).toBeInTheDocument();
        expect(await screen.findByText('cliente@test.com')).toBeInTheDocument();
        expect(screen.queryByText('Ya Vinculado')).not.toBeInTheDocument();
        expect(screen.getByText(/Rol: CLIENTE/)).toBeInTheDocument();
        expect(screen.getByText(/Cuenta: Activa/)).toBeInTheDocument();
    });

    test('vincula con usuario_id y motivo, conserva CLIENTE y muestra advertencia', async () => {
        axios.post.mockResolvedValue({
            data: { changed: true, usuario_id: 88, rol: 'CLIENTE' }
        });
        await renderLoaded();
        const row = screen.getByText('Sin Acceso').closest('tr');
        fireEvent.click(within(row).getByRole('button', { name: 'Vincular cuenta existente' }));
        const radio = await screen.findByRole('radio', { name: /Cliente Disponible/ });
        fireEvent.click(radio);
        fireEvent.change(screen.getByLabelText('Motivo *'), {
            target: { value: 'Vinculación confirmada en recepción' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar vínculo' }));

        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith(
                'http://127.0.0.1:8000/api/gestion/personal/10/vincular-usuario/',
                {
                    usuario_id: 88,
                    motivo: 'Vinculación confirmada en recepción'
                },
                { headers: { Authorization: 'Bearer test-token' } }
            );
        });
        expect(axios.post).toHaveBeenCalledTimes(1);
        await waitFor(() => {
            expect(notify.info).toHaveBeenCalledWith(
                'La cuenta fue vinculada correctamente. El rol de acceso todavía es CLIENTE.'
            );
        });
        expect(notify.success).not.toHaveBeenCalledWith(expect.stringContaining('rol'));
    });
});
