import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import GestionTurnos from './GestionTurnos';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn() }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn()
}), { virtual: true });


describe('GestionTurnos de solo lectura', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        axios.get.mockResolvedValue({
            data: [{
                id: 10,
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
});
