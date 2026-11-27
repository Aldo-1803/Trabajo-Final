import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import GestionarServicios from './GestionarServicios';
import { useSession } from '../../context/SessionContext';
import { notify } from '../../utils/notificaciones';


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        patch: jest.fn(),
        post: jest.fn(),
        delete: jest.fn()
    }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn()
}), { virtual: true });
jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('../../utils/notificaciones', () => ({
    confirmarAccion: jest.fn().mockResolvedValue({ isConfirmed: true }),
    notify: {
        success: jest.fn(),
        error: jest.fn()
    }
}));


const service = {
    id: 7,
    nombre: 'Color técnico',
    descripcion: 'Servicio de color',
    precio_base: '15000.00',
    duracion_estimada: 90,
    categoria: null,
    rutina_recomendada: null,
    impacto_porosidad: null,
    impacto_estado: null,
    plantilla_formula: 'Rubios:\nBase: 4 oxidante 10 vol',
    requisitos_equipamiento: [],
    activo: true
};

const grant = ({ prices = false, formula = false, simpleFormula = false } = {}) => {
    useSession.mockReturnValue({
        session: undefined,
        hasPermission: (permission) => (
            (permission === 'gestion.manage_prices' && prices)
            || (permission === 'gestion.manage_formulas' && simpleFormula)
        ),
        hasCapability: (capability) => (
            capability === 'service_formula.manage' && formula
        )
    });
};

const renderLoaded = async () => {
    render(<GestionarServicios />);
    await screen.findByText('Color técnico');
};

const openEditor = async () => {
    await renderLoaded();
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
};


describe('GestionarServicios por permisos y capability efectiva', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        axios.get.mockImplementation((url) => Promise.resolve({
            data: url.includes('/servicios/') && !url.includes('requisitos-servicio')
                ? [service]
                : []
        }));
        axios.patch.mockResolvedValue({ data: service });
        axios.post.mockResolvedValue({ data: { id: 8 } });
        axios.delete.mockResolvedValue({ data: {} });
    });

    test('permiso simple de fórmulas con capability falsa queda en lectura', async () => {
        grant({ simpleFormula: true });

        await renderLoaded();

        expect(screen.getByText(/Precio: \$15000\.00/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: '+ Nuevo Servicio' })).not.toBeInTheDocument();
        expect(axios.patch).not.toHaveBeenCalled();
        expect(axios.post).not.toHaveBeenCalled();
        expect(axios.delete).not.toHaveBeenCalled();
    });

    test('manage_prices edita metadata sin enviar fórmula', async () => {
        grant({ prices: true });
        await openEditor();

        expect(screen.queryByText('Plantilla de Fórmula')).not.toBeInTheDocument();
        fireEvent.change(screen.getByPlaceholderText('0.00'), {
            target: { value: '17500' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Actualizar' }));

        await waitFor(() => expect(axios.patch).toHaveBeenCalled());
        const payload = axios.patch.mock.calls[0][1];
        expect(payload.precio_base).toBe('17500');
        expect(payload).not.toHaveProperty('plantilla_formula');
    });

    test('service_formula.manage edita sólo fórmula y deja metadata deshabilitada', async () => {
        grant({ formula: true });
        await openEditor();

        expect(screen.getByRole('heading', { name: 'Editar Fórmula' })).toBeInTheDocument();
        expect(screen.getByPlaceholderText('0.00')).toBeDisabled();
        expect(screen.getByText(/catálogo se muestra en modo lectura/i)).toBeInTheDocument();
        fireEvent.change(screen.getAllByPlaceholderText('Ej: 4')[0], {
            target: { value: '5' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Actualizar' }));

        await waitFor(() => expect(axios.patch).toHaveBeenCalled());
        expect(axios.patch.mock.calls[0][1]).toEqual({
            plantilla_formula: expect.stringContaining('Base: 5')
        });
        expect(axios.post).not.toHaveBeenCalled();
        expect(axios.delete).not.toHaveBeenCalled();
    });

    test('ambas autoridades envían metadata y fórmula, sin campos extra', async () => {
        grant({ prices: true, formula: true });
        await openEditor();

        fireEvent.change(screen.getByPlaceholderText('0.00'), {
            target: { value: '18000' }
        });
        fireEvent.change(screen.getAllByPlaceholderText('Ej: 4')[0], {
            target: { value: '6' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Actualizar' }));

        await waitFor(() => expect(axios.patch).toHaveBeenCalled());
        const payload = axios.patch.mock.calls[0][1];
        expect(payload.precio_base).toBe('18000');
        expect(payload.plantilla_formula).toContain('Base: 6');
        expect(payload).not.toHaveProperty('requisitos_equipamiento');
    });

    test('validación del backend conserva el formulario y muestra su detalle', async () => {
        const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
        grant({ prices: true });
        await openEditor();
        const priceInput = screen.getByPlaceholderText('0.00');
        fireEvent.change(priceInput, { target: { value: '17000' } });
        axios.patch.mockRejectedValueOnce({
            response: {
                status: 400,
                data: { precio_base: ['Ingresá un precio válido.'] }
            }
        });

        fireEvent.click(screen.getByRole('button', { name: 'Actualizar' }));

        await waitFor(() => expect(notify.error).toHaveBeenCalledWith(
            'Ingresá un precio válido.'
        ));
        expect(screen.getByRole('heading', { name: 'Editar Servicio' }))
            .toBeInTheDocument();
        expect(priceInput).toHaveValue(17000);
        consoleError.mockRestore();
    });
});
