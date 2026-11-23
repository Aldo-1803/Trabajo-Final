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
const availability = {
    solicitud_id: 91,
    fecha: '2026-12-10',
    duration_minutes: 90,
    interval_minutes: 30,
    hold_ttl_minutes: 15,
    authoritative: false,
    profesionales: [{
        id: 4,
        display_name: 'Ada Lovelace',
        slots: [{
            starts_at: '2026-12-10T10:30:00-03:00',
            ends_at: '2026-12-10T12:00:00-03:00'
        }]
    }]
};
const activeHold = {
    public_id: '5f3b92c4-b158-4f64-8eed-889b4c9a5fe1',
    starts_at: '2026-12-10T10:30:00-03:00',
    ends_at: '2026-12-10T12:00:00-03:00',
    expires_at: '2026-12-10T10:15:00-03:00',
    persisted_state: 'ACTIVE',
    effective_state: 'ACTIVE',
    countdown: { seconds_remaining: 125, server_now: '2026-12-10T10:12:55-03:00' },
    personal: { id: 4, nombre: 'Ada', apellido: 'Lovelace' },
    hold_notice: 'Este hold no equivale a un Turno confirmado.',
    next_action: { code: 'HOLD_ACTIVE_PENDING_PAYMENT', can_confirm_turno: false }
};
const paymentOptions = {
    slot_hold_public_id: activeHold.public_id,
    policy_version: 'BH063-I4-T1',
    total_amount: '1500.00',
    currency: 'ARS',
    expires_at: '2026-12-10T10:15:00-03:00',
    modes: [
        { mode: 'DEPOSIT', required_amount: '300.00' },
        { mode: 'FULL', required_amount: '1500.00' }
    ],
    existing_intent: null
};
const pendingIntent = {
    public_id: 'bb0fdce0-d70b-4a3a-9719-a7fa2cb40a4a',
    operation_id: '38fdb0c1-2a2f-4cbd-b26e-1dbec8bf7c53',
    slot_hold_public_id: activeHold.public_id,
    policy_version: 'BH063-I4-T1',
    mode: 'DEPOSIT',
    required_amount: '300.00',
    total_amount_snapshot: '1500.00',
    currency: 'ARS',
    paid_reconciled: '0.00',
    confirmation_due: '300.00',
    financial_threshold_reached: false,
    confirmed_turno_id: null,
    effective_status: 'CREATED',
    expires_at: '2026-12-10T10:15:00-03:00',
    tracking: { state: 'READY_FOR_CHECKOUT', requires_polling: false }
};
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


const renderPage = ({
    permission = true,
    paymentPermission = false,
    routeState = null
} = {}) => {
    mockLocationState = routeState;
    useSession.mockReturnValue({
        hasPermission: (value) => (
            permission && (
                value === 'gestion.create_turno_for_client'
                || paymentPermission && value === 'gestion.register_payment'
            )
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


const submitApprovedRequest = async () => {
    await selectRequestData({ useSearch: false });
    fireEvent.click(screen.getByRole('button', {
        name: 'Registrar y evaluar solicitud'
    }));
    await screen.findByRole('button', { name: 'Consultar disponibilidad' });
};


const chooseAvailableSlot = async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
    const professional = await screen.findByLabelText('Profesional disponible');
    fireEvent.change(professional, { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Intervalo disponible'), {
        target: { value: availability.profesionales[0].slots[0].starts_at }
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

    test('consulta disponibilidad, selecciona profesional y crea un hold sin confirmación ni pago', async () => {
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post.mockImplementation((url) => {
            if (url === '/api/gestion/solicitudes-tecnicas-asistidas/') {
                return Promise.resolve({ data: baseResult('APTO') });
            }
            if (url.endsWith('/hold/')) return Promise.resolve({ data: activeHold });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await submitApprovedRequest();
        await chooseAvailableSlot();
        const create = screen.getByRole('button', { name: 'Crear hold temporal' });
        fireEvent.click(create);
        fireEvent.click(create);

        expect(await screen.findByText('Hold activo')).toBeInTheDocument();
        const holdCalls = axios.post.mock.calls.filter(([url]) => url.endsWith('/hold/'));
        expect(holdCalls).toHaveLength(1);
        expect(holdCalls[0][0]).toBe(
            '/api/gestion/solicitudes-tecnicas-asistidas/91/hold/'
        );
        expect(holdCalls[0][1]).toEqual({
            operation_id: expect.any(String),
            personal_id: 4,
            starts_at: '2026-12-10T10:30:00-03:00'
        });
        expect(holdCalls[0][2]).toEqual({
            headers: { 'Idempotency-Key': expect.any(String) }
        });
        expect(screen.getByText(/no equivale a un Turno confirmado/i)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /confirmar|pagar/i })).not.toBeInTheDocument();
    });

    test('atención inmediata selecciona el primer intervalo devuelto por el servidor', async () => {
        axios.get.mockImplementation((url, config) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/proximo-intervalo/')) {
                expect(config).toBeUndefined();
                return Promise.resolve({ data: {
                    solicitud_id: 91,
                    slot: {
                        personal: { id: 4, display_name: 'Ada Lovelace' },
                        ...availability.profesionales[0].slots[0]
                    }
                } });
            }
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await submitApprovedRequest();
        fireEvent.click(screen.getByRole('button', { name: 'Buscar atención inmediata' }));
        expect(await screen.findByDisplayValue('Ada Lovelace')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Crear hold temporal' })).toBeEnabled();
    });

    test('hold vencido se muestra claramente y puede actualizarse sin confirmar disponibilidad', async () => {
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/hold/')) return Promise.resolve({ data: {
                ...activeHold,
                effective_state: 'EXPIRED',
                countdown: { ...activeHold.countdown, seconds_remaining: 0 }
            } });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await submitApprovedRequest();
        // El estado se consulta explícitamente; nunca se infiere disponibilidad local.
        axios.post.mockResolvedValueOnce({ data: activeHold });
        axios.get.mockResolvedValueOnce({ data: availability });
        await chooseAvailableSlot();
        fireEvent.click(screen.getByRole('button', { name: 'Crear hold temporal' }));
        await screen.findByText('Hold activo');
        fireEvent.click(screen.getByRole('button', { name: 'Actualizar estado' }));
        expect(await screen.findByText('Hold no activo')).toBeInTheDocument();
        expect(screen.getByText(/Debe seleccionar un nuevo intervalo/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Liberar hold' })).not.toBeInTheDocument();
    });

    test('timeout de hold conserva payload y clave, y evita doble submit', async () => {
        const timeout = Object.assign(new Error('timeout'), { code: 'ECONNABORTED' });
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post
            .mockResolvedValueOnce({ data: baseResult('APTO') })
            .mockRejectedValueOnce(timeout)
            .mockResolvedValueOnce({ data: { ...activeHold, recovered: true } });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await submitApprovedRequest();
        await chooseAvailableSlot();
        const create = screen.getByRole('button', { name: 'Crear hold temporal' });
        fireEvent.click(create);
        fireEvent.click(create);
        const retry = await screen.findByRole('button', {
            name: 'Reintentar hold con la misma clave'
        });
        const holdCallsBeforeRetry = axios.post.mock.calls.filter(
            ([url]) => url.endsWith('/hold/')
        );
        expect(holdCallsBeforeRetry).toHaveLength(1);
        fireEvent.click(retry);
        await screen.findByText('Hold activo');
        const holdCalls = axios.post.mock.calls.filter(([url]) => url.endsWith('/hold/'));
        expect(holdCalls).toHaveLength(2);
        expect(holdCalls[1][1]).toEqual(holdCalls[0][1]);
        expect(holdCalls[1][2]).toEqual(holdCalls[0][2]);
    });

    test.each([401, 403, 409])('maneja %s en disponibilidad/hold sin exponer acciones futuras', async (httpStatus) => {
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.reject({
                response: { status: httpStatus, data: { error: {
                    code: `SAFE_${httpStatus}`,
                    detail: `Error seguro ${httpStatus}`
                } } }
            });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await submitApprovedRequest();
        fireEvent.click(screen.getByRole('button', { name: 'Consultar disponibilidad' }));
        const alert = await screen.findByRole('alert');
        expect(alert).not.toHaveTextContent(/diagnóstico|formula|snapshot/i);
        expect(screen.queryByRole('button', { name: /confirmar|pagar/i })).not.toBeInTheDocument();
    });

    test('revocación de permiso desmonta acciones y no realiza nuevas consultas', async () => {
        const view = renderPage();
        await screen.findByLabelText('Color');
        const callsBeforeRevocation = axios.get.mock.calls.length;
        useSession.mockReturnValue({ hasPermission: () => false });
        view.rerender(<NuevoTurno />);
        expect(screen.getByRole('alert')).toHaveTextContent(/No tenés autorización/);
        expect(screen.queryByRole('button', { name: 'Consultar disponibilidad' })).not.toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledTimes(callsBeforeRevocation);
    });

    test('autoridad compuesta prepara Intent sin enviar monto, policy ni estado', async () => {
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
            if (url.endsWith('/pago/opciones/')) return Promise.resolve({ data: paymentOptions });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post.mockImplementation((url) => {
            if (url === '/api/gestion/solicitudes-tecnicas-asistidas/') {
                return Promise.resolve({ data: baseResult('APTO') });
            }
            if (url.endsWith('/hold/')) return Promise.resolve({ data: activeHold });
            if (url.endsWith('/pago/intent/')) return Promise.resolve({ data: pendingIntent });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        renderPage({
            paymentPermission: true,
            routeState: { cliente: {
                cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
            } }
        });
        await submitApprovedRequest();
        await chooseAvailableSlot();
        fireEvent.click(screen.getByRole('button', { name: 'Crear hold temporal' }));
        await screen.findByText('Hold activo');
        fireEvent.click(screen.getByRole('button', { name: 'Consultar condiciones de pago' }));
        expect(await screen.findByText(/Policy: BH063-I4-T1/)).toBeInTheDocument();
        const prepare = screen.getByRole('button', {
            name: 'Preparar obligación financiera'
        });
        fireEvent.click(prepare);
        fireEvent.click(prepare);
        expect(await screen.findByText('Pago pendiente')).toBeInTheDocument();
        const intentCalls = axios.post.mock.calls.filter(
            ([url]) => url.endsWith('/pago/intent/')
        );
        expect(intentCalls).toHaveLength(1);
        expect(intentCalls[0][1]).toEqual({
            operation_id: expect.any(String),
            hold_public_id: activeHold.public_id,
            mode: 'DEPOSIT'
        });
        expect(intentCalls[0][1]).not.toHaveProperty('amount');
        expect(intentCalls[0][1]).not.toHaveProperty('policy_version');
        expect(intentCalls[0][1]).not.toHaveProperty('status');
        expect(screen.getByRole('link', { name: 'Continuar en Caja' }))
            .toHaveAttribute('href', `/admin/caja?search=${pendingIntent.public_id}`);
        expect(screen.queryByText(/Turno confirmado #/)).not.toBeInTheDocument();
    });

    test('timeout al preparar conserva identidad y recupera con la misma clave', async () => {
        const timeout = Object.assign(new Error('timeout'), { code: 'ECONNABORTED' });
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
            if (url.endsWith('/pago/opciones/')) return Promise.resolve({ data: paymentOptions });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post
            .mockResolvedValueOnce({ data: baseResult('APTO') })
            .mockResolvedValueOnce({ data: activeHold })
            .mockRejectedValueOnce(timeout)
            .mockResolvedValueOnce({ data: { ...pendingIntent, recovered: true } });
        renderPage({
            paymentPermission: true,
            routeState: { cliente: {
                cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
            } }
        });
        await submitApprovedRequest();
        await chooseAvailableSlot();
        fireEvent.click(screen.getByRole('button', { name: 'Crear hold temporal' }));
        await screen.findByText('Hold activo');
        fireEvent.click(screen.getByRole('button', { name: 'Consultar condiciones de pago' }));
        await screen.findByText(/Policy: BH063-I4-T1/);
        fireEvent.click(screen.getByRole('button', { name: 'Preparar obligación financiera' }));
        const retry = await screen.findByRole('button', {
            name: 'Recuperar Intent con la misma clave'
        });
        const first = axios.post.mock.calls.find(([url]) => url.endsWith('/pago/intent/'));
        fireEvent.click(retry);
        await screen.findByText('Pago pendiente');
        const intentCalls = axios.post.mock.calls.filter(
            ([url]) => url.endsWith('/pago/intent/')
        );
        expect(intentCalls).toHaveLength(2);
        expect(intentCalls[1][1]).toEqual(first[1]);
        expect(intentCalls[1][2]).toEqual(first[2]);
    });

    test('recupera estado confirmado y sólo entonces muestra referencia de Turno', async () => {
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
            if (url.endsWith('/pago/opciones/')) return Promise.resolve({ data: paymentOptions });
            if (url.endsWith('/pago/intent/')) return Promise.resolve({ data: {
                ...pendingIntent,
                paid_reconciled: '300.00',
                confirmation_due: '0.00',
                financial_threshold_reached: true,
                confirmed_turno_id: 721,
                effective_status: 'APPROVED',
                tracking: { state: 'CONFIRMED', requires_polling: false }
            } });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post
            .mockResolvedValueOnce({ data: baseResult('APTO') })
            .mockResolvedValueOnce({ data: activeHold })
            .mockResolvedValueOnce({ data: pendingIntent });
        renderPage({
            paymentPermission: true,
            routeState: { cliente: {
                cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
            } }
        });
        await submitApprovedRequest();
        await chooseAvailableSlot();
        fireEvent.click(screen.getByRole('button', { name: 'Crear hold temporal' }));
        await screen.findByText('Hold activo');
        fireEvent.click(screen.getByRole('button', { name: 'Consultar condiciones de pago' }));
        await screen.findByText(/Policy: BH063-I4-T1/);
        fireEvent.click(screen.getByRole('button', { name: 'Preparar obligación financiera' }));
        await screen.findByText('Pago pendiente');
        expect(screen.queryByText('Turno confirmado #721')).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Actualizar estado financiero' }));
        expect(await screen.findByText('Turno confirmado #721')).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Continuar en Caja' }))
            .not.toBeInTheDocument();
    });

    test('sin register_payment no consulta ni expone datos financieros', async () => {
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post.mockImplementation((url) => {
            if (url === '/api/gestion/solicitudes-tecnicas-asistidas/') {
                return Promise.resolve({ data: baseResult('APTO') });
            }
            if (url.endsWith('/hold/')) return Promise.resolve({ data: activeHold });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        renderPage({ routeState: { cliente: {
            cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
        } } });
        await submitApprovedRequest();
        await chooseAvailableSlot();
        fireEvent.click(screen.getByRole('button', { name: 'Crear hold temporal' }));
        expect(await screen.findByText(/Se requiere además el permiso efectivo/))
            .toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Consultar condiciones de pago' }))
            .not.toBeInTheDocument();
        expect(axios.get.mock.calls.some(([url]) => url.includes('/pago/'))).toBe(false);
    });

    test.each([401, 403, 409])(
        'preparación financiera maneja %s sin inventar confirmación',
        async (httpStatus) => {
            axios.get.mockImplementation((url) => {
                if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
                if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
                if (url.endsWith('/pago/opciones/')) return Promise.resolve({ data: paymentOptions });
                return Promise.reject(new Error(`Unexpected URL: ${url}`));
            });
            axios.post.mockImplementation((url) => {
                if (url === '/api/gestion/solicitudes-tecnicas-asistidas/') {
                    return Promise.resolve({ data: baseResult('APTO') });
                }
                if (url.endsWith('/hold/')) return Promise.resolve({ data: activeHold });
                if (url.endsWith('/pago/intent/')) return Promise.reject({
                    response: { status: httpStatus, data: { error: {
                        code: `SAFE_FINANCIAL_${httpStatus}`,
                        detail: `Estado financiero seguro ${httpStatus}`
                    } } }
                });
                return Promise.reject(new Error(`Unexpected URL: ${url}`));
            });
            renderPage({
                paymentPermission: true,
                routeState: { cliente: {
                    cliente_id: 11,
                    display_name: 'Laura Gómez',
                    cliente_activo: true
                } }
            });
            await submitApprovedRequest();
            await chooseAvailableSlot();
            fireEvent.click(screen.getByRole('button', { name: 'Crear hold temporal' }));
            await screen.findByText('Hold activo');
            fireEvent.click(screen.getByRole('button', { name: 'Consultar condiciones de pago' }));
            await screen.findByText(/Policy: BH063-I4-T1/);
            fireEvent.click(screen.getByRole('button', {
                name: 'Preparar obligación financiera'
            }));
            expect(await screen.findByRole('alert')).toHaveTextContent({
                401: 'Tu sesión finalizó',
                403: 'No tenés autorización',
                409: 'Estado financiero seguro 409'
            }[httpStatus]);
            expect(screen.queryByText(/Turno confirmado #/)).not.toBeInTheDocument();
            expect(screen.queryByRole('link', { name: 'Continuar en Caja' }))
                .not.toBeInTheDocument();
        }
    );

    test('revocar register_payment oculta la proyección financiera ya cargada', async () => {
        axios.get.mockImplementation((url) => {
            if (url === '/api/gestion/servicios/') return Promise.resolve({ data: services });
            if (url.endsWith('/disponibilidad/')) return Promise.resolve({ data: availability });
            if (url.endsWith('/pago/opciones/')) return Promise.resolve({ data: paymentOptions });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        axios.post.mockImplementation((url) => {
            if (url === '/api/gestion/solicitudes-tecnicas-asistidas/') {
                return Promise.resolve({ data: baseResult('APTO') });
            }
            if (url.endsWith('/hold/')) return Promise.resolve({ data: activeHold });
            if (url.endsWith('/pago/intent/')) return Promise.resolve({ data: pendingIntent });
            return Promise.reject(new Error(`Unexpected URL: ${url}`));
        });
        const view = renderPage({
            paymentPermission: true,
            routeState: { cliente: {
                cliente_id: 11, display_name: 'Laura Gómez', cliente_activo: true
            } }
        });
        await submitApprovedRequest();
        await chooseAvailableSlot();
        fireEvent.click(screen.getByRole('button', { name: 'Crear hold temporal' }));
        await screen.findByText('Hold activo');
        fireEvent.click(screen.getByRole('button', { name: 'Consultar condiciones de pago' }));
        await screen.findByText(/Policy: BH063-I4-T1/);
        fireEvent.click(screen.getByRole('button', { name: 'Preparar obligación financiera' }));
        await screen.findByText('Pago pendiente');
        expect(screen.getByText(new RegExp(pendingIntent.public_id)))
            .toBeInTheDocument();

        useSession.mockReturnValue({
            hasPermission: (value) => value === 'gestion.create_turno_for_client'
        });
        view.rerender(<NuevoTurno />);

        expect(screen.getByText(/Se requiere además el permiso efectivo/))
            .toBeInTheDocument();
        expect(screen.queryByText(new RegExp(pendingIntent.public_id)))
            .not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Continuar en Caja' }))
            .not.toBeInTheDocument();
    });
});
