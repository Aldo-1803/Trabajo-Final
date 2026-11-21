import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import NuevoTurno from './NuevoTurno';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn() }
}));
jest.mock('../../context/SessionContext', () => ({ useSession: jest.fn() }));
let mockLocationState = null;
jest.mock('react-router-dom', () => ({
    useLocation: () => ({ state: mockLocationState }),
    Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>
}), { virtual: true });


const client = {
    cliente_id: 11,
    display_name: 'Laura Gómez',
    masked_email: 'l***@test.com',
    active: true
};
const services = [
    { id: 7, nombre: 'Color', activo: true },
    { id: 8, nombre: 'Nutrición', activo: true }
];
const baseResult = (outcome, overrides = {}) => ({
    id: 91,
    estado: outcome === 'APTO'
        ? 'APROBADA_TECNICAMENTE'
        : outcome === 'ADVERTENCIA'
            ? 'ADVERTENCIA_PENDIENTE'
            : outcome === 'REQUIERE_REVISION'
                ? 'EN_REVISION'
                : 'RECHAZADA_TECNICAMENTE',
    outcome_publico: outcome,
    servicios: services,
    advertencias: outcome === 'ADVERTENCIA' ? ['Comunicar cuidado permitido.'] : [],
    consentimiento: null,
    siguiente_accion: {
        code: outcome === 'APTO'
            ? 'PENDING_SLOT_SELECTION_AND_CONFIRMATION'
            : outcome === 'ADVERTENCIA'
                ? 'REGISTER_ASSISTED_CONSENT'
                : outcome === 'REQUIERE_REVISION'
                    ? 'WAIT_FOR_TECHNICAL_REVIEW'
                    : 'TECHNICALLY_BLOCKED',
        detail: 'Acción segura siguiente.',
        can_continue_to_future_hold: outcome === 'APTO'
    },
    aviso_reserva: 'Esta solicitud técnica aún no reserva un Turno.',
    ...overrides
});


const renderPage = ({ permission = true, routeState = null } = {}) => {
    mockLocationState = routeState;
    useSession.mockReturnValue({
        hasPermission: (value) => (
            permission && value === 'gestion.create_turno_for_client'
        )
    });
    return render(<NuevoTurno />);
};


const selectRequestData = async ({ useSearch = true } = {}) => {
    await screen.findByLabelText('Color');
    if (useSearch) {
        fireEvent.change(screen.getByLabelText('Buscar Cliente'), {
            target: { value: 'Laura' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));
        const results = await screen.findByLabelText('Resultados de Clientes');
        fireEvent.click(within(results).getByRole('button', { name: 'Seleccionar' }));
    }
    fireEvent.click(screen.getByLabelText('Color'));
    fireEvent.click(screen.getByLabelText('Nutrición'));
    fireEvent.change(screen.getByLabelText('Fecha preferida'), {
        target: { value: '2026-12-10' }
    });
    fireEvent.change(screen.getByLabelText('Hora preferida'), {
        target: { value: '10:30' }
    });
    fireEvent.change(screen.getByLabelText('Medio de solicitud'), {
        target: { value: 'TELEFONO' }
    });
};


describe('Solicitud técnica asistida', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') {
                return Promise.resolve({ data: services });
            }
            if (url === '/api/usuarios/asistido/clientes/selector/') {
                return Promise.resolve({ data: { results: [client] } });
            }
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post.mockResolvedValue({ data: baseResult('APTO') });
    });

    test('sin permiso no monta ni consulta recursos protegidos', () => {
        renderPage({ permission: false });
        expect(screen.getByRole('alert')).toHaveTextContent(/No tenés autorización/);
        expect(axios.get).not.toHaveBeenCalled();
        expect(axios.post).not.toHaveBeenCalled();
    });

    test('selecciona Cliente minimizado, multiservicio y registra intención sin Turno', async () => {
        renderPage();
        await selectRequestData();
        fireEvent.click(screen.getByRole('button', {
            name: 'Registrar y evaluar solicitud'
        }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
        expect(axios.post.mock.calls[0][0])
            .toBe('/api/gestion/solicitudes-tecnicas-asistidas/');
        expect(axios.post.mock.calls[0][1]).toEqual(expect.objectContaining({
            cliente_id: 11,
            servicio_ids: [7, 8],
            fecha_preferida: '2026-12-10',
            hora_preferida: '10:30',
            medio_solicitud: 'TELEFONO',
            operation_id: expect.any(String)
        }));
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('estado');
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('outcome');
        expect(axios.post.mock.calls[0][2]).toEqual({
            headers: { 'Idempotency-Key': expect.any(String) }
        });
        expect(await screen.findByText(/Pendiente de selección de horario/))
            .toBeInTheDocument();
        expect(screen.queryByText(/turno reservado/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/pago/i)).not.toBeInTheDocument();
    });

    test('reutiliza el cliente recién creado por BH-064', async () => {
        renderPage({ routeState: { cliente: {
            cliente_id: 41,
            display_name: 'Ana Pérez',
            cliente_activo: true
        } } });
        await selectRequestData({ useSearch: false });
        expect(screen.getByText(/Ana Pérez/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {
            name: 'Registrar y evaluar solicitud'
        }));
        await waitFor(() => expect(axios.post).toHaveBeenCalled());
        expect(axios.post.mock.calls[0][1].cliente_id).toBe(41);
    });

    test.each([
        ['APTO', /Pendiente de selección de horario y confirmación/],
        ['REQUIERE_REVISION', /no puede aprobarla/],
        ['NO_APTO', /no puede continuar hacia la selección de horario/]
    ])('proyecta %s sin acciones de incrementos futuros', async (outcome, text) => {
        axios.post.mockResolvedValueOnce({ data: baseResult(outcome) });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await selectRequestData({ useSearch: false });
        fireEvent.click(screen.getByRole('button', {
            name: 'Registrar y evaluar solicitud'
        }));
        expect(await screen.findByText(text)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /aprobar/i })).not.toBeInTheDocument();
        expect(screen.queryByText(/confirmación de pago/i)).not.toBeInTheDocument();
    });

    test.each([
        ['ACEPTA', '', 'Acepta'],
        ['RECHAZA', 'Cliente rechaza', 'Rechaza'],
        ['NO_OBTENIDO', 'No fue posible obtenerlo', 'No obtenido']
    ])('ADVERTENCIA registra consentimiento %s con identidad propia', async (
        decision, reason, optionLabel
    ) => {
        axios.post
            .mockResolvedValueOnce({ data: baseResult('ADVERTENCIA') })
            .mockResolvedValueOnce({ data: baseResult('ADVERTENCIA', {
                consentimiento: { decision, mensajes_comunicados: ['Permitido'] },
                siguiente_accion: {
                    code: decision === 'ACEPTA'
                        ? 'PENDING_SLOT_SELECTION_AND_CONFIRMATION'
                        : 'CONSENT_NOT_ACCEPTED',
                    detail: 'Decisión registrada.',
                    can_continue_to_future_hold: decision === 'ACEPTA'
                }
            }) });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await selectRequestData({ useSearch: false });
        fireEvent.click(screen.getByRole('button', {
            name: 'Registrar y evaluar solicitud'
        }));
        await screen.findByText('Comunicar cuidado permitido.');
        fireEvent.change(screen.getByLabelText('Decisión de consentimiento'), {
            target: { value: decision }
        });
        expect(screen.getByText(optionLabel, { selector: 'option' })).toBeInTheDocument();
        if (reason) {
            fireEvent.change(screen.getByLabelText('Motivo de consentimiento'), {
                target: { value: reason }
            });
        }
        fireEvent.click(screen.getByRole('button', {
            name: 'Registrar consentimiento asistido'
        }));
        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        expect(axios.post.mock.calls[1][0]).toBe(
            '/api/gestion/solicitudes-tecnicas-asistidas/91/consentimiento/'
        );
        expect(axios.post.mock.calls[1][1]).toEqual({
            operation_id: expect.any(String),
            decision,
            motivo: reason
        });
        expect(await screen.findByText(`Consentimiento registrado: ${decision}.`))
            .toBeInTheDocument();
    });

    test('timeout conserva payload e Idempotency-Key para retry y evita doble submit', async () => {
        const timeout = Object.assign(new Error('timeout'), { code: 'ECONNABORTED' });
        axios.post.mockRejectedValueOnce(timeout).mockResolvedValueOnce({
            data: baseResult('APTO', { recovered: true })
        });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await selectRequestData({ useSearch: false });
        const submit = screen.getByRole('button', {
            name: 'Registrar y evaluar solicitud'
        });
        fireEvent.click(submit);
        fireEvent.click(submit);
        await screen.findByRole('button', {
            name: 'Reintentar solicitud con la misma clave'
        });
        expect(axios.post).toHaveBeenCalledTimes(1);
        const first = axios.post.mock.calls[0];
        fireEvent.click(screen.getByRole('button', {
            name: 'Reintentar solicitud con la misma clave'
        }));
        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        expect(axios.post.mock.calls[1][1]).toEqual(first[1]);
        expect(axios.post.mock.calls[1][2]).toEqual(first[2]);
    });

    test.each([400, 401, 403, 404, 409])(
        'expone estado de error HTTP %s sin datos técnicos',
        async (httpStatus) => {
            axios.post.mockRejectedValueOnce({
                response: {
                    status: httpStatus,
                    data: { error: {
                        code: `SAFE_${httpStatus}`,
                        detail: `Error seguro ${httpStatus}`
                    } }
                }
            });
            renderPage({ routeState: { cliente: {
                cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
            } } });
            await selectRequestData({ useSearch: false });
            fireEvent.click(screen.getByRole('button', {
                name: 'Registrar y evaluar solicitud'
            }));
            const alert = await screen.findByRole('alert');
            expect(alert).toBeInTheDocument();
            expect(alert).not.toHaveTextContent(/diagnóstico|formula|historial/i);
        }
    );
});
