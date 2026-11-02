import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import GestionProductos from './GestionProductos';
import { notify } from '../../utils/notificaciones';


let mockPermissions = [];

jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn(),
        patch: jest.fn(),
        delete: jest.fn()
    }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn()
}), { virtual: true });
jest.mock('../../context/SessionContext', () => ({
    useSession: () => ({
        hasPermission: (permission) => mockPermissions.includes(permission)
    })
}));
jest.mock('../../utils/notificaciones', () => ({
    confirmarAccion: jest.fn().mockResolvedValue({ isConfirmed: true }),
    notify: {
        success: jest.fn(),
        error: jest.fn(),
        warning: jest.fn()
    }
}));


const product = {
    id: 1,
    sku: 'PROD-1',
    nombre: 'Producto Uno',
    marca: 'Marca',
    categoria: 1,
    categoria_nombre: 'Accesorios',
    descripcion: 'Descripción',
    material_principal: 'SATEN',
    proposito_uso: 'DORMIR',
    precio: '100.00',
    stock_real: 8,
    stock_comprometido: 3,
    stock_minimo: 2,
    stock_disponible: 5,
    available: true,
    imagenes: [],
    estado_publicacion: 'PUBLICADO',
    compatibilidad: 'TODO',
    activo: true
};

const mockGet = (url) => {
    if (url.includes('stock-movements')) {
        return Promise.resolve({
            data: {
                results: [{
                    id: 11,
                    tipo: 'RECEIPT_IN',
                    delta: 8,
                    stock_before: 0,
                    stock_after: 8,
                    created_at: '2026-10-27T10:00:00Z'
                }]
            }
        });
    }
    if (url.includes('stock_bajo')) return Promise.resolve({ data: { productos: [] } });
    if (url.includes('categorias-productos')) {
        return Promise.resolve({
            data: [{ id: 1, nombre: 'Accesorios', descripcion: '', activo: true }]
        });
    }
    if (url.includes('promociones/sugerencias')) return Promise.resolve({ data: [] });
    if (url.endsWith('/productos/1/')) return Promise.resolve({ data: product });
    if (url.includes('/productos/')) return Promise.resolve({ data: [product] });
    return Promise.resolve({ data: [] });
};

describe('GestionProductos por capacidades efectivas', () => {
    let consoleError;

    beforeEach(() => {
        jest.clearAllMocks();
        mockPermissions = [];
        localStorage.setItem('access_token', 'test-token');
        axios.get.mockImplementation(mockGet);
        axios.post.mockResolvedValue({ data: { id: 12 } });
        axios.patch.mockResolvedValue({ data: product });
        axios.delete.mockResolvedValue({ data: {} });
        consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
    });

    afterEach(() => consoleError.mockRestore());

    test('view_stock muestra cantidades y movimientos en modo sólo lectura', async () => {
        mockPermissions = ['gestion.view_stock'];
        render(<GestionProductos />);

        expect(await screen.findByText(/Real:/)).toBeInTheDocument();
        expect(screen.getByText(/Comprometido:/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Inventario' }));

        expect(await screen.findByText('Movimientos físicos')).toBeInTheDocument();
        expect(screen.getByText('RECEIPT_IN')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Recibir stock' })).not.toBeInTheDocument();
    });

    test('manage_stock usa recepción semántica y no habilita edición de precio', async () => {
        mockPermissions = ['gestion.manage_stock'];
        render(<GestionProductos />);

        fireEvent.click(await screen.findByRole('button', { name: 'Inventario' }));
        expect(screen.getByRole('button', { name: 'Ajustar stock' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Solicitar corrección' })).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText('Cantidad recibida'), {
            target: { value: '4' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Recibir stock' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/productos/1/stock/receive/',
            expect.objectContaining({ quantity: 4, reason_code: 'MANUAL_D3' }),
            expect.any(Object)
        ));
        expect(screen.queryByRole('button', { name: /editar precio/i })).not.toBeInTheDocument();
    });

    test('manage_products edita metadata sin enviar precio', async () => {
        mockPermissions = ['gestion.manage_products'];
        render(<GestionProductos />);

        fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
        expect(screen.getByLabelText('Precio ($) *')).toBeDisabled();
        fireEvent.change(screen.getByLabelText('Nombre *'), {
            target: { value: 'Metadata nueva' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar Cambios' }));

        await waitFor(() => expect(axios.patch).toHaveBeenCalled());
        const payload = axios.patch.mock.calls[0][1];
        expect(payload.get('nombre')).toBe('Metadata nueva');
        expect(payload.has('precio')).toBe(false);
    });

    test('manage_prices edita sólo precio', async () => {
        mockPermissions = ['gestion.manage_prices'];
        render(<GestionProductos />);

        fireEvent.click(await screen.findByRole('button', { name: 'Editar precio' }));
        expect(screen.getByLabelText('Nombre *')).toBeDisabled();
        fireEvent.change(screen.getByLabelText('Precio ($) *'), {
            target: { value: '150.00' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Guardar Cambios' }));

        await waitFor(() => expect(axios.patch).toHaveBeenCalled());
        const payload = axios.patch.mock.calls[0][1];
        expect(payload.get('precio')).toBe('150');
        expect(payload.has('nombre')).toBe(false);
    });

    test('manage_products habilita administración de categorías', async () => {
        mockPermissions = ['gestion.manage_products'];
        render(<GestionProductos />);

        fireEvent.click(await screen.findByRole('button', { name: 'Categorías' }));
        expect(screen.getByRole('button', { name: 'Guardar categoría' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Recibir stock' })).not.toBeInTheDocument();
    });

    test('manage_promotions habilita combos sin controles de inventario', async () => {
        mockPermissions = ['gestion.manage_promotions'];
        render(<GestionProductos />);

        fireEvent.click(await screen.findByRole('button', { name: 'Combos' }));
        expect(screen.getByRole('button', { name: 'Publicar Combo' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Inventario' })).not.toBeInTheDocument();
    });

    test('muestra errores 403 y de dominio sin inventar saldos', async () => {
        mockPermissions = ['gestion.manage_stock'];
        axios.post.mockRejectedValue({
            response: { status: 409, data: { error: { detail: 'Stock reservado por órdenes activas.' } } }
        });
        render(<GestionProductos />);

        fireEvent.click(await screen.findByRole('button', { name: 'Inventario' }));
        fireEvent.change(screen.getByLabelText('Delta de ajuste'), {
            target: { value: '-1' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Ajustar stock' }));
        await waitFor(() => expect(notify.error).toHaveBeenCalledWith(
            'Stock reservado por órdenes activas.'
        ));

        axios.post.mockRejectedValue({ response: { status: 403, data: {} } });
        fireEvent.change(screen.getByLabelText('Cantidad recibida'), {
            target: { value: '1' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Recibir stock' }));
        await waitFor(() => expect(notify.error).toHaveBeenCalledWith(
            'No tienes permiso para realizar esta operación.'
        ));
    });

    test('sin capacidades no expone cantidades ni acciones de inventario', async () => {
        render(<GestionProductos />);
        await screen.findByText('Producto Uno');

        expect(screen.queryByText(/Real:/)).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Inventario' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /nuevo producto/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /publicar combo/i })).not.toBeInTheDocument();
    });
});
