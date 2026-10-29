import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import axios from 'axios';

import GestionOrdenes from './GestionOrdenes';
import { notify } from '../../utils/notificaciones';


let mockCanManageStock = true;

jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), post: jest.fn()},
}));
jest.mock('../../context/SessionContext', () => ({
    useSession: () => ({
        hasPermission: (permission) => (
            permission === 'gestion.manage_stock' && mockCanManageStock
        ),
    }),
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
    cliente: 10,
    cliente_nombre: 'Ada Cliente',
    cliente_email: 'ada@example.com',
    estado,
    total: '1500.00',
    creado_at: '2026-10-29T10:00:00Z',
    items: [{
        id: id * 10,
        producto_nombre: 'Cofia',
        producto_marca: 'Bohemia',
        cantidad: 1,
        precio_historico: '1500.00',
    }],
    pagos: [],
    ...extra,
});

const paid = order(1, 'PAGADO');
const pending = order(2, 'ESPERANDO_PAGO');
const completed = order(3, 'COMPLETADO');

const renderOrders = async (orders = [paid, pending, completed]) => {
    axios.get.mockResolvedValue({data: orders});
    render(<GestionOrdenes />);
    await screen.findByText('ORD-1');
};


describe('GestionOrdenes', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        mockCanManageStock = true;
    });

    test('distingue PAGADO de COMPLETADO y sólo habilita la entrega pagada', async () => {
        await renderOrders();

        expect(screen.getByText('Pagada · pendiente de entrega')).toBeInTheDocument();
        expect(screen.getByText('Entregada')).toBeInTheDocument();
        expect(screen.getAllByRole('button', {name: 'Confirmar entrega'})).toHaveLength(1);

        const pendingRow = screen.getByText('ORD-2').closest('tr');
        expect(within(pendingRow).getByText('Pago pendiente')).toBeInTheDocument();
        expect(within(pendingRow).queryByRole('button', {
            name: 'Confirmar entrega',
        })).not.toBeInTheDocument();
    });

    test('sin manage_stock no expone ninguna acción de entrega', async () => {
        mockCanManageStock = false;
        await renderOrders([paid]);

        expect(screen.queryByRole('button', {name: 'Confirmar entrega'})).not.toBeInTheDocument();
        expect(screen.getByText('Pendiente de operador autorizado')).toBeInTheDocument();
    });

    test('evita dobles solicitudes y usa la orden devuelta por F1', async () => {
        let resolveDelivery;
        axios.post.mockReturnValue(new Promise((resolve) => {
            resolveDelivery = resolve;
        }));
        await renderOrders([paid]);
        const button = screen.getByRole('button', {name: 'Confirmar entrega'});

        fireEvent.click(button);
        fireEvent.click(button);

        expect(axios.post).toHaveBeenCalledTimes(1);
        resolveDelivery({data: {orden: {...paid, estado: 'COMPLETADO'}}});

        expect(await screen.findByText('Entrega confirmada')).toBeInTheDocument();
        expect(notify.success).toHaveBeenCalledWith('Entrega confirmada');
    });

    test.each([
        [403, {detail: 'revocado'}, 'No tienes permiso efectivo'],
        [409, {error: 'ORDER_NOT_PAID'}, 'ORDER_NOT_PAID'],
    ])('maneja HTTP %s y resincroniza la orden', async (status, data, message) => {
        axios.get.mockResolvedValue({data: [paid]});
        axios.post.mockRejectedValue({response: {status, data}});
        render(<GestionOrdenes />);
        await screen.findByText('ORD-1');

        fireEvent.click(screen.getByRole('button', {name: 'Confirmar entrega'}));

        expect(await screen.findByRole('alert')).toHaveTextContent(message);
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
        expect(notify.error).toHaveBeenCalled();
    });

    test('permite reintentar después de un conflicto concurrente', async () => {
        axios.get.mockResolvedValue({data: [paid]});
        axios.post
            .mockRejectedValueOnce({
                response: {status: 409, data: {error: 'Conflicto temporal'}},
            })
            .mockResolvedValueOnce({
                data: {orden: {...paid, estado: 'COMPLETADO'}},
            });
        render(<GestionOrdenes />);
        await screen.findByText('ORD-1');

        fireEvent.click(screen.getByRole('button', {name: 'Confirmar entrega'}));
        expect(await screen.findByRole('alert')).toHaveTextContent('Conflicto temporal');
        fireEvent.click(screen.getByRole('button', {name: 'Confirmar entrega'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        expect(await screen.findByText('Entrega confirmada')).toBeInTheDocument();
    });
});
