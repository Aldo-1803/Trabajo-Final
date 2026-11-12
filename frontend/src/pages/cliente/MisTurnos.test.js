import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { confirmarAccion, notify } from '../../utils/notificaciones';
import MisTurnos from './MisTurnos';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() }
}));
jest.mock('../../utils/notificaciones', () => ({
    confirmarAccion: jest.fn(),
    notify: {
        error: jest.fn(),
        success: jest.fn()
    }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn()
}), { virtual: true });


const ownTurno = {
    id: 21,
    profesional: 4,
    profesional_nombre: 'Julia Díaz',
    fecha: '2099-10-23',
    hora_inicio: '10:00:00',
    estado: 'confirmado',
    servicio_nombre: 'Corte',
    detalles: [{ servicio: 7, servicio_nombre: 'Corte' }],
    comprobante_pago: null
};


describe('MisTurnos mantiene operaciones propias separadas', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'client-token');
        confirmarAccion.mockResolvedValue({ isConfirmed: true });
    });

    test('consulta opciones y cancela por endpoints propios sin gestionar ni PATCH', async () => {
        axios.get
            .mockResolvedValueOnce({ data: [ownTurno] })
            .mockResolvedValueOnce({
                data: {
                    puede_reprogramar: false,
                    puede_cancelar: true,
                    mensaje: 'Seleccioná una operación disponible para tu Turno.',
                    tipo_alerta: 'info',
                    cambios_realizados: 0,
                    limite_cambios: 2
                }
            })
            .mockResolvedValueOnce({
                data: [{ ...ownTurno, estado: 'cancelado' }]
            });
        axios.post.mockResolvedValue({
            data: { mensaje: 'Turno cancelado correctamente.' }
        });

        render(<MisTurnos />);
        fireEvent.click(await screen.findByRole('button', { name: 'Gestionar / Cancelar' }));
        fireEvent.change(await screen.findByLabelText('Motivo de cancelación'), {
            target: { value: 'No podré asistir' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Cancelar Turno' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/turnos/21/cancelar-cliente/',
            { motivo: 'No podré asistir' },
            { headers: { Authorization: 'Bearer client-token' } }
        ));
        expect(axios.get.mock.calls[1][0]).toBe(
            'http://127.0.0.1:8000/api/gestion/turnos/21/opciones-cliente/'
        );
        expect(axios.get.mock.calls.flat().join(' ')).not.toContain('/gestionar/');
        expect(axios.patch).not.toHaveBeenCalled();
        expect(notify.success).toHaveBeenCalledWith('Turno cancelado correctamente.');
    });
});
