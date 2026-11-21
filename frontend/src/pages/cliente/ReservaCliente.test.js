import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import ReservaCliente from './ReservaCliente';
import { confirmarAccion } from '../../utils/notificaciones';


const mockNavigate = jest.fn();


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn()
    }
}));
jest.mock('../../utils/notificaciones', () => ({
    notify: {
        error: jest.fn(),
        success: jest.fn(),
        info: jest.fn()
    },
    confirmarAccion: jest.fn()
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => mockNavigate,
    useLocation: () => ({ state: null })
}), { virtual: true });


describe('ReservaCliente con endpoint propio', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'client-token');
        confirmarAccion.mockResolvedValue({ isConfirmed: true });
        axios.get.mockImplementation((url) => {
            if (url.endsWith('/servicios/')) {
                return Promise.resolve({
                    data: [{
                        id: 7,
                        nombre: 'Corte',
                        duracion_estimada: 60,
                        requisitos_equipamiento: [{ id: 1 }]
                    }]
                });
            }
            if (url.includes('/turnos/consultar_disponibilidad/')) {
                return Promise.resolve({
                    data: {
                        servicio_nombre: 'Corte',
                        duracion_minutos: 60,
                        disponibilidad: [{
                            fecha: '2026-11-10',
                            dia_semana: 'Martes',
                            profesionales: [{
                                id: 3,
                                nombre: 'Julia',
                                slots: [{ hora: '10:00', profesional_id: 3 }]
                            }]
                        }]
                    }
                });
            }
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post.mockResolvedValue({
            data: { mensaje: 'Turno solicitado correctamente.' }
        });
    });

    test('reserva sin enviar un Cliente arbitrario', async () => {
        render(<ReservaCliente />);

        await screen.findByRole('option', { name: /Corte/ });
        const serviceSelect = screen.getByRole('combobox');
        fireEvent.change(serviceSelect, { target: { value: '7' } });
        fireEvent.click(await screen.findByRole('button', { name: /Martes/ }));
        fireEvent.click(screen.getByRole('button', { name: /10:00/ }));
        fireEvent.click(screen.getByRole('button', { name: /Solicitar Turno/i }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
        expect(axios.post.mock.calls[0][0])
            .toBe('http://127.0.0.1:8000/api/gestion/turnos/reservar/');
        expect(axios.post.mock.calls[0][1]).toEqual({
            servicio: '7',
            profesional: 3,
            fecha: '2026-11-10',
            hora_inicio: '10:00'
        });
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('cliente');
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('cliente_id');
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('estado');
    });
});
