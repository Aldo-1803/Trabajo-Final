import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import GestionTurnos from './GestionTurnos';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() }
}));
jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn()
}), { virtual: true });


describe('GestionTurnos', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        useSession.mockReturnValue({
            hasPermission: () => false
        });
        axios.get.mockResolvedValue({
            data: [{
                id: 10,
                servicio_id: 7,
                cliente: 2,
                cliente_nombre: 'Ana Pérez',
                profesional: 4,
                profesional_nombre: 'Julia Díaz',
                servicio_nombre: 'Corte',
                fecha: '2026-10-23',
                hora_inicio: '10:00:00',
                estado: 'confirmado'
            }]
        });
    });

    test('lista el contrato global seguro', async () => {
        render(<GestionTurnos />);

        expect(await screen.findByText('Ana Pérez')).toBeInTheDocument();
        expect(screen.getAllByText('Julia Díaz')).toHaveLength(2);
        expect(screen.getByText('Corte')).toBeInTheDocument();
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));
        expect(axios.get.mock.calls[0][0])
            .toBe('http://127.0.0.1:8000/api/gestion/turnos/');
    });

    test('no muestra acciones legacy de escritura', async () => {
        render(<GestionTurnos />);

        await screen.findByText('Ana Pérez');
        [
            'Gestionar profesional',
            'Finalizar',
            'Registrar pago',
            'Cambiar estado',
            'Eliminar',
            'Cancelar',
            'Reprogramar'
        ].forEach((label) => {
            expect(screen.queryByRole('button', { name: new RegExp(label, 'i') }))
                .not.toBeInTheDocument();
        });
    });

    test('muestra Registrar llegada solo con permiso y estado confirmado', async () => {
        useSession.mockReturnValue({
            hasPermission: (permission) => permission === 'gestion.register_arrival'
        });

        render(<GestionTurnos />);

        expect(await screen.findByRole('button', { name: 'Registrar llegada' }))
            .toBeInTheDocument();
    });

    test('no muestra Registrar llegada con view_global_agenda solamente', async () => {
        useSession.mockReturnValue({
            hasPermission: (permission) => permission === 'gestion.view_global_agenda'
        });

        render(<GestionTurnos />);

        await screen.findByText('Ana Pérez');
        expect(screen.queryByRole('button', { name: 'Registrar llegada' }))
            .not.toBeInTheDocument();
    });

    test('no muestra Registrar llegada en estados no válidos', async () => {
        useSession.mockReturnValue({ hasPermission: () => true });
        axios.get.mockResolvedValue({
            data: [{
                id: 10,
                cliente_nombre: 'Ana Pérez',
                fecha: '2026-10-23',
                hora_inicio: '10:00:00',
                estado: 'cancelado'
            }]
        });

        render(<GestionTurnos />);

        await screen.findByText('Ana Pérez');
        expect(screen.queryByRole('button', { name: 'Registrar llegada' }))
            .not.toBeInTheDocument();
    });

    test('registra con POST dedicado y recarga sin usar PATCH', async () => {
        useSession.mockReturnValue({ hasPermission: () => true });
        axios.post.mockResolvedValue({ data: { changed: true } });

        render(<GestionTurnos />);

        fireEvent.click(await screen.findByRole('button', { name: 'Registrar llegada' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/10/registrar-llegada/',
            {},
            { headers: { Authorization: 'Bearer test-token' } }
        ));
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
        expect(screen.getByText('Llegada registrada correctamente.')).toBeInTheDocument();
        expect(axios.patch).not.toHaveBeenCalled();
    });

    test('muestra mensaje seguro ante transición inválida', async () => {
        useSession.mockReturnValue({ hasPermission: () => true });
        axios.post.mockRejectedValue({
            response: { status: 409, data: { detail: 'detalle interno' } }
        });

        render(<GestionTurnos />);
        fireEvent.click(await screen.findByRole('button', { name: 'Registrar llegada' }));

        expect(await screen.findByRole('alert')).toHaveTextContent(
            'El Turno no admite registrar llegada en su estado actual.'
        );
        expect(axios.get).toHaveBeenCalledTimes(1);
    });

    test.each([
        ['gestion.reprogram_any_turno', 'Reprogramar', 'Cancelar'],
        ['gestion.cancel_any_turno', 'Cancelar', 'Reprogramar']
    ])(
        'permiso %s habilita solo la acción %s',
        async (permission, visibleAction, hiddenAction) => {
            useSession.mockReturnValue({
                user: { is_staff: false },
                businessRole: 'EMPLEADO',
                hasPermission: (candidate) => candidate === permission
            });

            render(<GestionTurnos />);

            expect(await screen.findByRole('button', { name: visibleAction }))
                .toBeInTheDocument();
            expect(screen.queryByRole('button', { name: hiddenAction }))
                .not.toBeInTheDocument();
            expect(screen.queryByRole('button', { name: 'Registrar llegada' }))
                .not.toBeInTheDocument();
        }
    );

    test('ADMINISTRADOR is_staff=false reprograma con disponibilidad canónica y POST dedicado', async () => {
        useSession.mockReturnValue({
            user: { is_staff: false },
            businessRole: 'ADMINISTRADOR',
            hasPermission: (permission) => permission === 'gestion.reprogram_any_turno'
        });
        const turno = {
            id: 10,
            servicio_id: 7,
            cliente_nombre: 'Ana Pérez',
            profesional_nombre: 'Julia Díaz',
            servicio_nombre: 'Corte',
            fecha: '2026-10-23',
            hora_inicio: '10:00:00',
            estado: 'confirmado'
        };
        axios.get
            .mockResolvedValueOnce({ data: [turno] })
            .mockResolvedValueOnce({
                data: {
                    disponibilidad: [{
                        fecha: '2026-10-24',
                        profesionales: [{
                            id: 4,
                            nombre: 'Julia Díaz',
                            slots: [{ hora: '11:00', profesional_id: 4 }]
                        }]
                    }]
                }
            })
            .mockResolvedValueOnce({
                data: [{ ...turno, fecha: '2026-10-24', hora_inicio: '11:00:00' }]
            });
        axios.post.mockResolvedValue({ data: { turno_id: 10 } });

        render(<GestionTurnos />);
        fireEvent.click(await screen.findByRole('button', { name: 'Reprogramar' }));
        await screen.findByRole('option', { name: /2026-10-24 11:00/ });
        fireEvent.change(screen.getByLabelText('Nueva fecha y hora'), {
            target: { value: '0' }
        });
        fireEvent.change(screen.getByLabelText('Motivo de reprogramación'), {
            target: { value: 'Cambio operativo' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar reprogramación' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/10/reprogramar/',
            {
                fecha: '2026-10-24',
                hora: '11:00',
                profesional_id: 4,
                motivo: 'Cambio operativo'
            },
            { headers: { Authorization: 'Bearer test-token' } }
        ));
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(3));
        expect(screen.getByText('Turno reprogramado correctamente.')).toBeInTheDocument();
        expect(axios.patch).not.toHaveBeenCalled();
    });

    test('error semántico de cancelación muestra mensaje seguro y no recarga', async () => {
        useSession.mockReturnValue({
            hasPermission: (permission) => permission === 'gestion.cancel_any_turno'
        });
        axios.post.mockRejectedValue({
            response: {
                status: 409,
                data: { detail: 'detalle interno que no debe mostrarse' }
            }
        });

        render(<GestionTurnos />);
        fireEvent.click(await screen.findByRole('button', { name: 'Cancelar' }));
        fireEvent.change(screen.getByLabelText('Motivo de cancelación'), {
            target: { value: 'Motivo válido' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar cancelación' }));

        expect(await screen.findByRole('alert')).toHaveTextContent(
            'El Turno no admite cancelación en su estado actual.'
        );
        expect(axios.get).toHaveBeenCalledTimes(1);
    });
});
