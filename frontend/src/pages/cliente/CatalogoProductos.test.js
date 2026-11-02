import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import CatalogoProductos from './CatalogoProductos';


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        post: jest.fn()
    }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn()
}), { virtual: true });
jest.mock('../../components/SmartSuggestions', () => () => null);
jest.mock('../../components/common/Icons', () => ({
    IconSearch: () => <span>buscar</span>,
    IconX: () => <span>cerrar</span>
}));
jest.mock('../../utils/notificaciones', () => ({
    notify: {
        success: jest.fn(),
        error: jest.fn()
    }
}));


const publicProduct = {
    id: 1,
    sku: 'PUBLICO-1',
    nombre: 'Producto público',
    marca: 'Marca',
    categoria: 1,
    descripcion: 'Visible sin cantidades internas',
    precio: '120.00',
    available: true,
    estado_publicacion: 'PUBLICADO',
    compatibilidad: 'TODO',
    activo: true,
    imagen_url: null,
    imagenes: []
};

describe('catálogo público de productos', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'cliente-token');
        axios.get.mockImplementation((url) => {
            if (url.includes('categorias-productos')) {
                return Promise.resolve({
                    data: [{ id: 1, nombre: 'Accesorios', activo: true }]
                });
            }
            if (url.includes('promociones')) return Promise.resolve({ data: [] });
            return Promise.resolve({ data: [publicProduct] });
        });
        axios.post.mockResolvedValue({ data: {} });
    });

    test('usa disponibilidad booleana sin mostrar cantidades internas', async () => {
        render(<CatalogoProductos />);

        expect(await screen.findByText('Producto público')).toBeInTheDocument();
        expect(screen.getByText('En Stock')).toBeInTheDocument();
        expect(screen.queryByText(/stock real/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/comprometido/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/disponible:/i)).not.toBeInTheDocument();
        expect(axios.post).not.toHaveBeenCalled();
    });

    test('agregar al carrito no llama endpoints de mutación de inventario', async () => {
        render(<CatalogoProductos />);

        fireEvent.click(await screen.findByText('Producto público'));
        fireEvent.click(screen.getByRole('button', { name: 'Agregar al Carrito' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
        expect(axios.post.mock.calls[0][0]).toBe(
            'http://127.0.0.1:8000/api/gestion/carrito/agregar-producto/'
        );
        expect(axios.post.mock.calls.some(([url]) => url.includes('/stock/'))).toBe(false);
        expect(axios.post.mock.calls.some(([url]) => url.includes('stock-movements'))).toBe(false);
    });
});
