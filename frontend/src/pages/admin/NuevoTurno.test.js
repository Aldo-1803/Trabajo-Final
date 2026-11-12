import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import NuevoTurno from './NuevoTurno';


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn()
    }
}));
jest.mock('../../utils/notificaciones', () => ({
    notify: {
        error: jest.fn()
    }
}));


describe('NuevoTurno con creación explícita para Cliente', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        axios.get.mockImplementation((url) => {
            if (url.endsWith('/servicios/')) {
                return Promise.resolve({
                    data: [{ id: 7, nombre: 'Corte', duracion_estimada: 60 }]
                });
            }
            if (url.endsWith('/turnos/selector-clientes/')) {
                return Promise.resolve({
                    data: [{
                        id: 11,
                        nombre: 'Laura',
                        apellido: 'Gómez',
                        email: 'laura@test.com'
                    }]
                });
            }
            if (url.endsWith('/turnos/consultar_disponibilidad/')) {
                return Promise.resolve({
                    data: {
                        disponibilidad: [{
                            fecha: '2026-11-10',
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
            data: { mensaje: 'Turno solicitado para el Cliente correctamente.' }
        });
    });

    test('usa selectores mínimos y envía el Cliente elegido al endpoint operativo', async () => {
        render(<NuevoTurno />);

        await screen.findByRole('option', { name: /Laura Gómez/ });
        fireEvent.change(screen.getByLabelText('Cliente'), {
            target: { value: '11' }
        });
        fireEvent.change(screen.getByLabelText('Servicio'), {
            target: { value: '7' }
        });
        fireEvent.change(screen.getByLabelText('Fecha'), {
            target: { value: '2026-11-10' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Ver horarios disponibles' }));
        fireEvent.click(await screen.findByRole('button', { name: '10:00 — Julia' }));
        fireEvent.click(screen.getByRole('button', { name: 'Crear Turno solicitado' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
        expect(axios.post.mock.calls[0][0])
            .toBe('http://127.0.0.1:8000/api/gestion/turnos/crear-para-cliente/');
        expect(axios.post.mock.calls[0][1]).toEqual({
            cliente_id: 11,
            servicio: 7,
            profesional: 3,
            fecha: '2026-11-10',
            hora_inicio: '10:00'
        });
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('estado');
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('monto_abonado');
    });

    test('no contiene decisiones por is_staff', async () => {
        render(<NuevoTurno />);

        await screen.findByRole('option', { name: /Laura Gómez/ });
        expect(screen.getByRole('heading', { name: 'Nuevo Turno' }))
            .toBeInTheDocument();
    });
});
