import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import BookingPaymentFlow, { BOOKING_INTENT_STORAGE_KEY } from './BookingPaymentFlow';


jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), post: jest.fn()},
}));

const request = {
    id: 21,
    servicios: [{id: 4, nombre: 'Color'}],
};

const hold = {
    public_id: '11111111-1111-4111-8111-111111111111',
    solicitud_id: 21,
    starts_at: '2026-12-10T10:00:00-03:00',
    ends_at: '2026-12-10T11:00:00-03:00',
    expires_at: '2026-12-10T09:15:00-03:00',
    effective_state: 'ACTIVE',
    persisted_state: 'ACTIVE',
    countdown: {seconds_remaining: 125, server_now: '2026-12-10T09:12:55-03:00'},
    personal: {id: 8, nombre: 'Ada', apellido: 'Lovelace'},
};

const options = {
    slot_hold_public_id: hold.public_id,
    policy_version: 'F3-POLICY',
    total_amount: '1000.00',
    currency: 'ARS',
    expires_at: hold.expires_at,
    modes: [
        {mode: 'DEPOSIT', required_amount: '250.00'},
        {mode: 'FULL', required_amount: '1000.00'},
    ],
    existing_intent: null,
};

const intent = {
    public_id: '22222222-2222-4222-8222-222222222222',
    slot_hold_public_id: hold.public_id,
    mode: 'DEPOSIT',
    total_amount_snapshot: '1000.00',
    required_amount: '250.00',
    currency: 'ARS',
    effective_status: 'CREATED',
    tracking: {
        state: 'READY_FOR_CHECKOUT',
        code: 'PAYMENT_INTENT_READY',
        requires_polling: false,
    },
    checkout: null,
};

const mockReads = ({optionData = options, refreshedHold = hold, intentData = intent} = {}) => {
    axios.get.mockImplementation((url) => {
        if (url.includes('/payment-intents/options/')) {
            return Promise.resolve({data: optionData});
        }
        if (url.includes('/slot-holds/')) {
            return Promise.resolve({data: refreshedHold});
        }
        if (url.includes('/payment-intents/')) {
            return Promise.resolve({data: intentData});
        }
        return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
};

const renderFlow = (props = {}) => render(
    <BookingPaymentFlow
        request={request}
        initialHold={hold}
        onError={jest.fn()}
        onHoldUpdate={jest.fn()}
        onAvailabilityRefresh={jest.fn()}
        onRelease={jest.fn()}
        {...props}
    />
);


describe('BookingPaymentFlow', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        window.sessionStorage.clear();
        mockReads();
    });

    test('muestra HOLD, countdown y opciones calculadas por backend', async () => {
        renderFlow();

        expect(screen.getByText(/Tiempo disponible: 02:05/)).toBeInTheDocument();
        expect(await screen.findByRole('radio', {name: /Pagar seña/})).toBeChecked();
        expect(screen.getByRole('radio', {name: /Pagar total/})).toBeInTheDocument();
        expect(screen.getByText(/El importe lo calcula el backend/)).toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledWith(
            '/api/gestion/payment-intents/options/',
            {params: {slot_hold_public_id: hold.public_id}}
        );
    });

    test.each([
        ['DEPOSIT', /Pagar seña/, '250.00'],
        ['FULL', /Pagar total/, '1000.00'],
    ])('crea Intent %s sin enviar un importe', async (mode, label, required) => {
        axios.post.mockResolvedValue({
            data: {...intent, mode, required_amount: required},
        });
        renderFlow();
        const radio = await screen.findByRole('radio', {name: label});
        fireEvent.click(radio);
        fireEvent.click(screen.getByRole('button', {name: 'Continuar con esta modalidad'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/payment-intents/',
            {slot_hold_public_id: hold.public_id, mode},
            {headers: {'Idempotency-Key': expect.any(String)}}
        ));
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('amount');
        expect(window.sessionStorage.getItem(BOOKING_INTENT_STORAGE_KEY)).toBe(intent.public_id);
    });

    test('reintenta la creación con la misma clave idempotente', async () => {
        axios.post
            .mockRejectedValueOnce({response: {data: {detail: 'Error temporal'}}})
            .mockResolvedValueOnce({data: intent});
        renderFlow();
        const button = await screen.findByRole('button', {
            name: 'Continuar con esta modalidad',
        });
        fireEvent.click(button);
        expect(await screen.findByRole('alert')).toHaveTextContent('Error temporal');
        fireEvent.click(button);

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        const firstKey = axios.post.mock.calls[0][2].headers['Idempotency-Key'];
        const secondKey = axios.post.mock.calls[1][2].headers['Idempotency-Key'];
        expect(secondKey).toBe(firstKey);
    });

    test('usa exclusivamente checkout_url devuelta por C1', async () => {
        const redirect = jest.fn();
        mockReads({optionData: {...options, existing_intent: intent}});
        axios.post.mockResolvedValue({
            data: {
                status: 'READY',
                checkout_url: 'https://www.mercadopago.com.ar/checkout/f3',
                financial_authority: false,
            },
        });
        renderFlow({onRedirect: redirect});
        fireEvent.click(await screen.findByRole('button', {name: 'Ir a Mercado Pago'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            `/api/gestion/payment-intents/${intent.public_id}/checkout/`,
            {channel: 'ONLINE'},
            {headers: {'Idempotency-Key': expect.any(String)}}
        ));
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('amount');
        expect(redirect).toHaveBeenCalledWith(
            'https://www.mercadopago.com.ar/checkout/f3'
        );
    });

    test('recupera el mismo checkout persistido después de recargar', async () => {
        const redirect = jest.fn();
        const resumableIntent = {
            ...intent,
            tracking: {
                state: 'PAYMENT_VERIFICATION',
                code: 'AWAITING_PROVIDER_VERIFICATION',
                requires_polling: true,
            },
            checkout: {
                checkout_url: 'https://www.mercadopago.com.ar/checkout/persisted',
            },
        };
        mockReads({optionData: {...options, existing_intent: resumableIntent}});
        axios.post.mockResolvedValue({
            data: {
                status: 'READY',
                checkout_url: 'https://www.mercadopago.com.ar/checkout/persisted',
                financial_authority: false,
            },
        });
        renderFlow({onRedirect: redirect});

        fireEvent.click(await screen.findByRole('button', {
            name: 'Continuar en Mercado Pago',
        }));

        await waitFor(() => expect(redirect).toHaveBeenCalledWith(
            'https://www.mercadopago.com.ar/checkout/persisted'
        ));
        expect(axios.post).toHaveBeenCalledTimes(1);
    });

    test('un HOLD vencido según backend impide iniciar checkout', async () => {
        const expired = {
            ...hold,
            effective_state: 'EXPIRED',
            persisted_state: 'ACTIVE',
            countdown: {...hold.countdown, seconds_remaining: 0},
        };
        mockReads({
            optionData: {...options, existing_intent: intent},
            refreshedHold: expired,
        });
        renderFlow();
        fireEvent.click(await screen.findByRole('button', {name: 'Ir a Mercado Pago'}));

        expect(await screen.findByRole('alert')).toHaveTextContent(/HOLD venció/);
        expect(axios.post).not.toHaveBeenCalled();
        expect(screen.getByRole('button', {
            name: 'Consultar disponibilidad nuevamente',
        })).toBeInTheDocument();
    });

    test('resultado incierto no crea otra obligación y queda en seguimiento', async () => {
        const uncertainIntent = {
            ...intent,
            tracking: {
                state: 'CHECKOUT_UNCERTAIN',
                code: 'PROVIDER_OUTCOME_UNKNOWN',
                requires_polling: true,
            },
        };
        mockReads({
            optionData: {...options, existing_intent: intent},
            intentData: uncertainIntent,
        });
        axios.post.mockResolvedValue({
            data: {
                status: 'OUTCOME_UNKNOWN',
                checkout_url: null,
                financial_authority: false,
            },
        });
        renderFlow();
        fireEvent.click(await screen.findByRole('button', {name: 'Ir a Mercado Pago'}));

        expect(await screen.findByRole('alert')).toHaveTextContent(/resultado del checkout es incierto/i);
        expect(axios.post).toHaveBeenCalledTimes(1);
        expect(await screen.findByText(/El mismo Intent puede reintentarse|resultado del checkout/i)).toBeInTheDocument();
    });
});
