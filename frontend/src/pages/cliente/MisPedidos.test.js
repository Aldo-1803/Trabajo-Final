import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import MisPedidos from './MisPedidos';
import { notify } from '../../utils/notificaciones';


jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), post: jest.fn()},
}));
jest.mock('../../utils/notificaciones', () => ({
    notify: {
        success: jest.fn(),
        error: jest.fn(),
    },
}));

const order = (id, estado, extra = {}) => ({
    id,
    codigo: `ORD-${id}`,
    estado,
    total: '1200.00',
    creado_at: '2026-10-29T10:00:00Z',
    items: [{
        id: id * 10,
        producto_nombre: 'Scrunchie',
        producto_marca: 'Bohemia',
        cantidad: 1,
        precio_historico: '1200.00',
    }],
    pagos: [],
    ...extra,
});

const pending = order(1, 'ESPERANDO_PAGO');
const paid = order(2, 'PAGADO');
const completed = order(3, 'COMPLETADO');
const cancelled = order(4, 'CANCELADO');
const review = order(5, 'ESPERANDO_PAGO', {
    pagos: [{status: 'PENDING_RECONCILIATION'}],
});


describe('MisPedidos', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        axios.get.mockResolvedValue({
            data: [pending, paid, completed, cancelled, review],
        });
    });

    test('muestra pago, entrega y revisión como conceptos distintos', async () => {
        render(<MisPedidos />);

        expect(await screen.findByText('Pagada · pendiente de entrega')).toBeInTheDocument();
        expect(screen.getByText('Entregada')).toBeInTheDocument();
        expect(screen.getByText('Cancelada')).toBeInTheDocument();
        expect(screen.getByText('Pago en revisión')).toBeInTheDocument();
        expect(screen.getByText(/Los productos todavía no fueron entregados/)).toBeInTheDocument();
        expect(screen.queryByRole('button', {name: 'Confirmar entrega'})).not.toBeInTheDocument();
    });

    test('continúa C1 sin enviar monto y usa sólo checkout_url del backend', async () => {
        const redirect = jest.fn();
        axios.get.mockResolvedValue({data: [pending]});
        axios.post.mockResolvedValue({
            data: {
                status: 'READY',
                checkout_url: 'https://www.mercadopago.com.ar/checkout/order-f4',
            },
        });
        render(<MisPedidos onRedirect={redirect} />);

        fireEvent.click(await screen.findByRole('button', {
            name: 'Continuar al checkout',
        }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/gestion/ordenes-compra/1/checkout/',
            {channel: 'ONLINE'},
            {headers: {'Idempotency-Key': expect.any(String)}}
        ));
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('amount');
        expect(redirect).toHaveBeenCalledWith(
            'https://www.mercadopago.com.ar/checkout/order-f4'
        );
    });

    test('reintenta resultado incierto con la misma clave', async () => {
        const redirect = jest.fn();
        axios.get.mockResolvedValue({data: [pending]});
        axios.post
            .mockResolvedValueOnce({
                data: {status: 'OUTCOME_UNKNOWN', checkout_url: null},
            })
            .mockResolvedValueOnce({
                data: {
                    status: 'READY',
                    checkout_url: 'https://www.mercadopago.com.ar/checkout/retry-f4',
                },
            });
        render(<MisPedidos onRedirect={redirect} />);
        const button = await screen.findByRole('button', {
            name: 'Continuar al checkout',
        });

        fireEvent.click(button);
        expect(await screen.findByRole('alert')).toHaveTextContent(/incierto/);
        fireEvent.click(button);

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        expect(
            axios.post.mock.calls[1][2].headers['Idempotency-Key']
        ).toBe(axios.post.mock.calls[0][2].headers['Idempotency-Key']);
        expect(redirect).toHaveBeenCalledWith(
            'https://www.mercadopago.com.ar/checkout/retry-f4'
        );
    });

    test('refresca desde backend y muestra PAGADO sin confiar en el retorno', async () => {
        axios.get
            .mockResolvedValueOnce({data: [pending]})
            .mockResolvedValueOnce({data: [{...pending, estado: 'PAGADO'}]});
        render(<MisPedidos />);
        await screen.findByRole('button', {name: 'Continuar al checkout'});

        fireEvent.click(screen.getByRole('button', {name: 'Actualizar pedidos'}));

        expect(await screen.findByText('Pagada · pendiente de entrega')).toBeInTheDocument();
        expect(screen.queryByRole('button', {
            name: 'Continuar al checkout',
        })).not.toBeInTheDocument();
    });

    test('una orden en revisión no ofrece otro checkout', async () => {
        axios.get.mockResolvedValue({data: [review]});
        render(<MisPedidos />);

        expect(await screen.findByText('Pago en revisión')).toBeInTheDocument();
        expect(screen.queryByRole('button', {
            name: 'Continuar al checkout',
        })).not.toBeInTheDocument();
        expect(notify.error).not.toHaveBeenCalled();
    });
});
