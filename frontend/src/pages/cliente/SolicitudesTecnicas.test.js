import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import SolicitudesTecnicas from './SolicitudesTecnicas';


jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), post: jest.fn()}
}));


const warningRequest = {
    id: 12,
    estado: 'ADVERTENCIA_PENDIENTE',
    servicios: [{id: 4, nombre: 'Color'}],
    fecha_preferida: '2026-12-10',
    hora_preferida: '10:00:00',
    advertencias: ['Requiere cuidado previo.'],
    faltantes: [],
    alternativas: [],
    mensaje_cliente: '',
    fecha_minima: '2026-12-15'
};

const approvedRequest = {
    ...warningRequest,
    id: 21,
    estado: 'APROBADA_TECNICAMENTE',
    personal_preferido: {id: 8, nombre: 'Ada', apellido: 'Lovelace'}
};

const activeHold = {
    public_id: '11111111-1111-4111-8111-111111111111',
    starts_at: '2026-12-10T10:00:00-03:00',
    ends_at: '2026-12-10T11:00:00-03:00',
    expires_at: '2026-12-10T09:15:00-03:00',
    persisted_state: 'ACTIVE',
    effective_state: 'ACTIVE',
    countdown: {
        server_now: '2026-12-10T09:12:55-03:00',
        seconds_remaining: 125,
        authoritative: false
    },
    personal: approvedRequest.personal_preferido
};

const paymentOptions = {
    slot_hold_public_id: activeHold.public_id,
    policy_version: 'F3-POLICY',
    total_amount: '1000.00',
    currency: 'ARS',
    expires_at: activeHold.expires_at,
    modes: [
        {mode: 'DEPOSIT', required_amount: '250.00'},
        {mode: 'FULL', required_amount: '1000.00'},
    ],
    existing_intent: null,
};


describe('SolicitudesTecnicas', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        axios.get.mockImplementation((url) => Promise.resolve({
            data: url.includes('/servicios/')
                ? [{id: 4, nombre: 'Color'}]
                : url.includes('/personal/')
                    ? [{id: 8, nombre: 'Ada', apellido: 'Lovelace'}]
                    : url.includes('/slot-holds/')
                        ? []
                        : [warningRequest]
        }));
    });

    test('explica que no reserva y permite aceptar una advertencia', async () => {
        axios.post.mockResolvedValue({
            data: {...warningRequest, estado: 'APROBADA_TECNICAMENTE'}
        });
        render(<SolicitudesTecnicas />);

        expect(screen.getByText(/esto aún no reserva el turno/i)).toBeInTheDocument();
        const button = await screen.findByRole('button', {name: 'Aceptar advertencia'});
        fireEvent.click(button);

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/solicitudes-tecnicas/12/aceptar-advertencia/',
            {}
        ));
        expect(await screen.findByText('Aprobada técnicamente')).toBeInTheDocument();
    });

    test('envía servicios y preferencia sin cliente_id', async () => {
        axios.post.mockResolvedValue({
            data: {...warningRequest, id: 13, estado: 'EN_REVISION'}
        });
        render(<SolicitudesTecnicas />);
        const checkbox = await screen.findByRole('checkbox', {name: 'Color'});
        fireEvent.click(checkbox);
        fireEvent.change(screen.getByLabelText('Fecha preferida'), {
            target: {value: '2026-12-10'}
        });
        fireEvent.change(screen.getByLabelText('Hora preferida'), {
            target: {value: '11:00'}
        });
        fireEvent.click(screen.getByRole('button', {name: 'Enviar solicitud técnica'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/solicitudes-tecnicas/reservar/',
            {
                servicio_ids: [4],
                fecha_preferida: '2026-12-10',
                hora_preferida: '11:00'
            }
        ));
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('cliente_id');
    });

    test('crea un HOLD, muestra countdown informativo y permite liberarlo', async () => {
        axios.get.mockImplementation((url) => Promise.resolve({
            data: url.includes('/servicios/')
                ? [{id: 4, nombre: 'Color'}]
                : url.includes('/personal/')
                    ? [{id: 8, nombre: 'Ada', apellido: 'Lovelace'}]
                    : url.includes('/slot-holds/')
                        ? []
                        : url.includes('/payment-intents/options/')
                            ? paymentOptions
                            : [approvedRequest]
        }));
        axios.post
            .mockResolvedValueOnce({data: activeHold})
            .mockResolvedValueOnce({
                data: {
                    ...activeHold,
                    persisted_state: 'RELEASED',
                    effective_state: 'RELEASED',
                    countdown: {...activeHold.countdown, seconds_remaining: 0}
                }
            });

        render(<SolicitudesTecnicas />);
        fireEvent.click(await screen.findByRole('button', {
            name: 'Reservar temporalmente este horario'
        }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/solicitudes-tecnicas/21/hold/',
            {
                personal_id: 8,
                starts_at: '2026-12-10T10:00:00'
            },
            {headers: {'Idempotency-Key': expect.any(String)}}
        ));
        expect(await screen.findByText(/Tiempo disponible: 02:05/)).toBeInTheDocument();
        expect(screen.getByText(/el servidor verifica nuevamente la vigencia/i)).toBeInTheDocument();
        expect(await screen.findByText(/Total:/)).toHaveTextContent('$ 1.000,00');
        expect(screen.queryByText(/Turno confirmado/i)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Liberar reserva temporal'}));
        await waitFor(() => expect(axios.post).toHaveBeenLastCalledWith(
            `/api/gestion/slot-holds/${activeHold.public_id}/release/`,
            {}
        ));
        expect(await screen.findByText(/HOLD está vencido o liberado/)).toBeInTheDocument();
    });
});
