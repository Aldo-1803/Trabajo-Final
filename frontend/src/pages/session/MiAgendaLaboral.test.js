import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import MiAgendaLaboral from './MiAgendaLaboral';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn() }
}));
jest.mock('../../context/SessionContext', () => ({ useSession: jest.fn() }));


const ownTurno = {
    id: 8,
    servicio_id: 3,
    cliente_nombre: 'Cliente Propio',
    servicio_nombre: 'Corte',
    fecha: '2026-10-23',
    hora_inicio: '10:00:00',
    estado: 'confirmado'
};

const renderAgenda = (permissions = []) => {
    useSession.mockReturnValue({
        loading: false,
        hasPermission: (permission) => permissions.includes(permission)
    });
    return render(<MiAgendaLaboral />);
};


describe('MiAgendaLaboral', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'personal-token');
        axios.get.mockResolvedValue({ data: [ownTurno] });
    });

    test('consume exclusivamente la agenda laboral propia', async () => {
        renderAgenda();

        expect(await screen.findByText('Cliente Propio')).toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/mi-agenda-laboral/',
            { headers: { Authorization: 'Bearer personal-token' } }
        );
    });

    test('register_arrival aislado muestra sólo llegada y usa el endpoint semántico', async () => {
        axios.post.mockResolvedValue({ data: { changed: true } });
        renderAgenda(['gestion.register_arrival']);

        fireEvent.click(await screen.findByRole('button', { name: 'Registrar llegada' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/8/registrar-llegada/',
            {},
            { headers: { Authorization: 'Bearer personal-token' } }
        ));
        expect(screen.queryByRole('button', { name: 'Reprogramar' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Cancelar' })).not.toBeInTheDocument();
    });

    test.each([
        ['gestion.reprogram_any_turno', 'Reprogramar', 'Cancelar'],
        ['gestion.cancel_any_turno', 'Cancelar', 'Reprogramar']
    ])('permiso aislado %s muestra sólo %s', async (permission, visible, hidden) => {
        renderAgenda([permission]);

        expect(await screen.findByRole('button', { name: visible })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: hidden })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Registrar llegada' })).not.toBeInTheDocument();
    });
});
