import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { BOOKING_INTENT_STORAGE_KEY } from './BookingPaymentFlow';
import RetornoMercadoPago from './RetornoMercadoPago';


jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn()},
}));

jest.mock('react-router-dom', () => ({
    Link: ({to, children, ...props}) => <a href={to} {...props}>{children}</a>,
}), {virtual: true});

const intentId = '22222222-2222-4222-8222-222222222222';

const renderReturn = (result = 'success') => render(
    <RetornoMercadoPago result={result} />
);

const intentWith = (state, requiresPolling = false) => ({
    public_id: intentId,
    tracking: {
        state,
        code: state,
        requires_polling: requiresPolling,
    },
});


describe('RetornoMercadoPago BOOKING', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        window.sessionStorage.clear();
        window.sessionStorage.setItem(BOOKING_INTENT_STORAGE_KEY, intentId);
    });

    test('un retorno success sin acreditación sigue en verificación backend', async () => {
        axios.get.mockResolvedValue({data: intentWith('PAYMENT_VERIFICATION', true)});
        renderReturn('success');

        expect(await screen.findByRole('heading', {name: 'Pago en verificación'})).toBeInTheDocument();
        expect(screen.getByText(/no acredita el pago/i)).toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledWith(
            `/api/gestion/payment-intents/${intentId}/`
        );
        expect(screen.getByRole('link', {name: 'Volver a mi solicitud'})).toHaveAttribute(
            'href',
            '/solicitudes-tecnicas'
        );
    });

    test('el estado confirmado proviene de la consulta y enlaza al Turno', async () => {
        axios.get.mockResolvedValue({data: intentWith('CONFIRMED')});
        renderReturn('pending');

        expect(await screen.findByRole('heading', {name: 'Reserva confirmada'})).toBeInTheDocument();
        expect(screen.getByText(/backend acreditó el pago/i)).toBeInTheDocument();
        expect(screen.getByRole('link', {name: 'Ver mi Turno'})).toHaveAttribute(
            'href',
            '/mis-turnos'
        );
    });

    test('expone pago rechazado y conciliación sin inferirlos del retorno', async () => {
        axios.get.mockResolvedValueOnce({data: intentWith('PAYMENT_REJECTED')});
        const first = renderReturn('success');
        expect(await screen.findByRole('heading', {name: 'Pago no acreditado'})).toBeInTheDocument();
        first.unmount();

        axios.get.mockResolvedValueOnce({data: intentWith('ADMIN_REVIEW')});
        renderReturn('failure');
        expect(await screen.findByRole('heading', {
            name: 'Pago recibido con revisión necesaria',
        })).toBeInTheDocument();
        expect(screen.getByText(/No vuelvas a pagar/)).toBeInTheDocument();
    });

    test('distingue pago acreditado sin reserva confirmable', async () => {
        axios.get.mockResolvedValue({data: intentWith('PAID_WITHOUT_BOOKING')});
        renderReturn('success');

        expect(await screen.findByRole('heading', {
            name: 'Pago acreditado sin reserva confirmable',
        })).toBeInTheDocument();
        expect(screen.getByText(/dinero fue preservado/i)).toBeInTheDocument();
    });

    test('sin Intent de sesión conserva un retorno informativo para ORDER', async () => {
        window.sessionStorage.removeItem(BOOKING_INTENT_STORAGE_KEY);
        renderReturn('pending');

        await waitFor(() => expect(screen.getByRole('heading', {
            name: 'Operación recibida',
        })).toBeInTheDocument());
        expect(axios.get).not.toHaveBeenCalled();
        expect(screen.getByRole('link', {name: 'Ver mis pedidos'})).toHaveAttribute(
            'href',
            '/mis-pedidos'
        );
    });
});
