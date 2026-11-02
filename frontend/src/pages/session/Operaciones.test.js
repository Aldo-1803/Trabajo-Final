import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import Operaciones from './Operaciones';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() }
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
    isStaff = false,
    personalActive = false
} = {}) => ({
    user: {
        first_name: 'Ana',
        email: 'ana@example.com',
        is_staff: isStaff
    },
    businessRole,
    permissions,
    loading: false,
    hasPermission: (permission) => permissions.includes(permission),
    hasActiveProfile: (profile) => profile === 'personal' && personalActive
});


const renderOperations = (context = {}) => {
    useSession.mockReturnValue(sessionContext(context));
    return render(<Operaciones />);
};


const confirmedTurno = {
    id: 10,
    servicio_id: 7,
    cliente_nombre: 'Ana Pérez',
    servicio_nombre: 'Corte',
    hora_inicio: '10:00:00',
    estado: 'confirmado'
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
            .toHaveAttribute('href', '/admin/clientes/nuevo');
        expect(screen.queryByText('Turnos de hoy')).not.toBeInTheDocument();
        expect(axios.get).not.toHaveBeenCalled();
    });

    test('create_turno_for_client muestra Nuevo turno solamente por permiso', () => {
        renderOperations({
            businessRole: 'ADMINISTRADOR',
            permissions: ['gestion.create_turno_for_client'],
            isStaff: false
        });

        expect(screen.getByRole('link', { name: 'Nuevo turno' }))
            .toHaveAttribute('href', '/admin/nuevo-turno');
        expect(screen.queryByText('Turnos de hoy')).not.toBeInTheDocument();
        expect(axios.get).not.toHaveBeenCalled();
    });

    test.each([
        'gestion.register_payment',
        'gestion.confirm_deposit',
        'gestion.view_financial_reports'
    ])('%s habilita Caja presencial sin depender de rol ni is_staff', (permission) => {
        renderOperations({
            businessRole: 'EMPLEADO',
            permissions: [permission],
            isStaff: false
        });

        expect(screen.getByRole('link', { name: 'Abrir caja presencial' }))
            .toHaveAttribute('href', '/admin/caja');
        expect(axios.get).not.toHaveBeenCalled();
    });

    test('BusinessRole e is_staff no habilitan agenda sin permiso', () => {
        renderOperations({
            businessRole: 'ADMINISTRADOR',
            permissions: [],
            isStaff: true
        });

        expect(screen.queryByText('Turnos de hoy')).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Nuevo turno' }))
            .not.toBeInTheDocument();
        expect(screen.getByText('No hay Turnos disponibles para operar con los permisos actuales.'))
            .toBeInTheDocument();
        expect(axios.get).not.toHaveBeenCalled();
    });

    test.each([
        ['EMPLEADO', false],
        ['ADMINISTRADOR', false]
    ])('%s is_staff=%s muestra llegada por permiso efectivo', async (businessRole, isStaff) => {
        axios.get.mockResolvedValue({ data: [confirmedTurno] });

        renderOperations({
            businessRole,
            isStaff,
            permissions: [
                'gestion.view_global_agenda',
                'gestion.register_arrival'
            ]
        });

        expect(await screen.findByRole('button', { name: 'Registrar llegada' }))
            .toBeInTheDocument();
    });

    test('view_global_agenda sin register_arrival no muestra la acción', async () => {
        axios.get.mockResolvedValue({ data: [confirmedTurno] });

        renderOperations({ permissions: ['gestion.view_global_agenda'] });

        expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Registrar llegada' }))
            .not.toBeInTheDocument();
    });

    test('register_arrival solo no concede lectura de Turnos', () => {
        renderOperations({ permissions: ['gestion.register_arrival'] });

        expect(screen.queryByText('Turnos de hoy')).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Registrar llegada' }))
            .not.toBeInTheDocument();
        expect(axios.get).not.toHaveBeenCalled();
    });

    test('Personal activo con llegada aislada usa agenda propia sin consultar la global', async () => {
        axios.get.mockResolvedValue({
            data: [{
                ...confirmedTurno,
                fecha: new Date().toISOString().slice(0, 10)
            }]
        });
        renderOperations({
            permissions: ['gestion.register_arrival'],
            personalActive: true
        });

        expect(await screen.findByRole('heading', { name: 'Mis Turnos de hoy' }))
            .toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/mi-agenda-laboral/',
            { headers: { Authorization: 'Bearer test-token' } }
        );
        expect(await screen.findByRole('button', { name: 'Registrar llegada' }))
            .toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Ver agenda' })).not.toBeInTheDocument();
    });

    test('acción aislada sin Personal activo no consulta agenda global', () => {
        renderOperations({
            businessRole: 'ADMINISTRADOR',
            permissions: ['gestion.cancel_any_turno']
        });

        expect(screen.getByText('No hay Turnos disponibles para operar con los permisos actuales.'))
            .toBeInTheDocument();
        expect(axios.get).not.toHaveBeenCalled();
    });

    test.each([
        ['gestion.reprogram_any_turno', 'Reprogramar', 'Cancelar'],
        ['gestion.cancel_any_turno', 'Cancelar', 'Reprogramar']
    ])('Personal activo con %s ve sólo %s en agenda propia', async (permission, visible, hidden) => {
        axios.get.mockResolvedValue({
            data: [{
                ...confirmedTurno,
                fecha: new Date().toISOString().slice(0, 10)
            }]
        });
        renderOperations({ permissions: [permission], personalActive: true });

        expect(await screen.findByRole('button', { name: visible })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: hidden })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Ver agenda' })).not.toBeInTheDocument();
    });

    test.each(['solicitado', 'esperando_sena', 'en_proceso', 'realizado', 'cancelado', 'ausente'])(
        'no muestra llegada para estado %s',
        async (estado) => {
            axios.get.mockResolvedValue({ data: [{ ...confirmedTurno, estado }] });

            renderOperations({
                permissions: [
                    'gestion.view_global_agenda',
                    'gestion.register_arrival'
                ]
            });

            expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
            expect(screen.queryByRole('button', { name: 'Registrar llegada' }))
                .not.toBeInTheDocument();
        }
    );

    test('usa POST dedicado, recarga y muestra el estado devuelto por la lista', async () => {
        axios.get
            .mockResolvedValueOnce({ data: [confirmedTurno] })
            .mockResolvedValueOnce({
                data: [{ ...confirmedTurno, estado: 'en_proceso' }]
            });
        axios.post.mockResolvedValue({
            data: { changed: true, estado_actual: 'en_proceso' }
        });
        renderOperations({
            permissions: [
                'gestion.view_global_agenda',
                'gestion.register_arrival'
            ]
        });

        fireEvent.click(await screen.findByRole('button', { name: 'Registrar llegada' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/10/registrar-llegada/',
            {},
            { headers: { Authorization: 'Bearer test-token' } }
        ));
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
        expect(await screen.findByText('Estado: en_proceso')).toBeInTheDocument();
        expect(screen.getByText('Llegada registrada correctamente.')).toBeInTheDocument();
        expect(axios.patch).not.toHaveBeenCalled();
    });

    test('un conflicto conserva el estado y muestra un mensaje seguro', async () => {
        axios.get.mockResolvedValue({ data: [confirmedTurno] });
        axios.post.mockRejectedValue({
            response: {
                status: 409,
                data: { detail: 'detalle interno que no debe mostrarse' }
            }
        });
        renderOperations({
            permissions: [
                'gestion.view_global_agenda',
                'gestion.register_arrival'
            ]
        });

        fireEvent.click(await screen.findByRole('button', { name: 'Registrar llegada' }));

        expect(await screen.findByRole('alert')).toHaveTextContent(
            'El Turno no admite registrar llegada en su estado actual.'
        );
        expect(screen.getByText('Estado: confirmado')).toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledTimes(1);
    });

    test.each([
        ['gestion.reprogram_any_turno', 'Reprogramar', 'Cancelar'],
        ['gestion.cancel_any_turno', 'Cancelar', 'Reprogramar']
    ])(
        'permiso %s habilita solo %s',
        async (permission, visibleAction, hiddenAction) => {
            axios.get.mockResolvedValue({ data: [confirmedTurno] });
            renderOperations({
                businessRole: 'EMPLEADO',
                isStaff: false,
                permissions: ['gestion.view_global_agenda', permission]
            });

            expect(await screen.findByRole('button', { name: visibleAction }))
                .toBeInTheDocument();
            expect(screen.queryByRole('button', { name: hiddenAction }))
                .not.toBeInTheDocument();
        }
    );

    test('cancelación usa endpoint dedicado, motivo y recarga', async () => {
        axios.get
            .mockResolvedValueOnce({ data: [confirmedTurno] })
            .mockResolvedValueOnce({
                data: [{ ...confirmedTurno, estado: 'cancelado' }]
            });
        axios.post.mockResolvedValue({ data: { changed: true } });
        renderOperations({
            businessRole: 'ADMINISTRADOR',
            isStaff: false,
            permissions: [
                'gestion.view_global_agenda',
                'gestion.cancel_any_turno'
            ]
        });

        fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
        fireEvent.change(screen.getByLabelText('Motivo de cancelación'), {
            target: { value: 'Cierre excepcional del salón' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar cancelación' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/10/cancelar/',
            { motivo: 'Cierre excepcional del salón' },
            { headers: { Authorization: 'Bearer test-token' } }
        ));
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
        expect(await screen.findByText('Estado: cancelado')).toBeInTheDocument();
        expect(screen.getByText('Turno cancelado correctamente.')).toBeInTheDocument();
        expect(axios.patch).not.toHaveBeenCalled();
    });
});
