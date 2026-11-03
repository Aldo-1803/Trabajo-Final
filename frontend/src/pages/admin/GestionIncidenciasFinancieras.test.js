import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';

import GestionIncidenciasFinancieras from './GestionIncidenciasFinancieras';
import {
    closeFinancialCase,
    executeAuthorizedRefund,
    financialApiError,
    getFinancialCase,
    getRefundOperation,
    listFinancialCases,
    recordResolutionDecision,
    recoverRefundOperation,
    requestPaidOrderCancellation,
    submitResolutionRequest,
} from '../../api/financialCasesApi';


let mockCanReconcile = true;

jest.mock('../../context/SessionContext', () => ({
    useSession: () => ({
        hasPermission: (permission) => (
            permission === 'gestion.reconcile_external_payment' && mockCanReconcile
        ),
    }),
}));
jest.mock('../../api/financialCasesApi', () => ({
    listFinancialCases: jest.fn(),
    getFinancialCase: jest.fn(),
    submitResolutionRequest: jest.fn(),
    recordResolutionDecision: jest.fn(),
    executeAuthorizedRefund: jest.fn(),
    getRefundOperation: jest.fn(),
    recoverRefundOperation: jest.fn(),
    closeFinancialCase: jest.fn(),
    requestPaidOrderCancellation: jest.fn(),
    createIdempotencyKey: jest.fn(() => 'f7-6-stable-key'),
    financialApiError: jest.fn((error, fallback) => (
        error.response?.status === 403
            ? 'No tenés el permiso efectivo para gestionar incidencias financieras.'
            : error.response?.status === 409
                ? `Conflicto financiero: ${error.response.data?.code || 'conflicto'}`
                : error.response?.status === 422
                    ? 'La operación no es procesable.'
                    : fallback
    )),
}));


const payment = (overrides = {}) => ({
    public_id: 'payment-1',
    amount: '30.00',
    currency: 'ARS',
    method: 'MERCADO_PAGO',
    purpose: 'CONFIRMATION',
    status: 'RECONCILED',
    provider_code: 'MERCADO_PAGO',
    provider_payment_id: 'MP-PAYMENT-1',
    financial_projection: {
        gross_reconciled: '30.00',
        confirmed_adjustments: '0.00',
        net_reconciled: '30.00',
        refund_pending: '0.00',
        refunds_confirmed: '0.00',
        chargebacks_confirmed: '0.00',
    },
    adjustments: [],
    ...overrides,
});

const caseDetail = (overrides = {}) => ({
    public_id: 'case-1',
    case_type: 'CANCELLATION_WITH_PAYMENT',
    case_type_label: 'Cancelación con pago',
    status: 'OPEN',
    reason_code: 'CANCELLATION_WITH_PAYMENT',
    context: 'BOOKING',
    context_reference: {
        payment_intent_public_id: 'intent-1',
        payment_intent_status: 'APPROVED',
        slot_hold_public_id: 'hold-1',
        turno_id: 18,
        turno_status: 'cancelado',
    },
    customer_reference: {client_id: 7, display_name: 'Ada Cliente'},
    financial_summary: {
        payment_count: 1,
        total_amount: '30.00',
        currencies: ['ARS'],
        gross_reconciled: '30.00',
        confirmed_adjustments: '0.00',
        net_reconciled: '30.00',
        refund_pending: '0.00',
    },
    provider_reference: {provider: 'MERCADO_PAGO'},
    created_at: '2026-10-30T10:00:00Z',
    resolved_at: null,
    age_seconds: 259200,
    payments: [payment()],
    payment_intent: {status: 'APPROVED'},
    turno: {id: 18, estado: 'cancelado'},
    order: null,
    provider_attempt: {status: 'READY'},
    provider_event: {reconciliation_status: 'REVIEW_REQUIRED'},
    resolution_request: null,
    closure: null,
    ...overrides,
});

const listItem = (detail) => ({
    public_id: detail.public_id,
    case_type: detail.case_type,
    case_type_label: detail.case_type_label,
    status: detail.status,
    reason_code: detail.reason_code,
    context: detail.context,
    context_reference: detail.context_reference,
    customer_reference: detail.customer_reference,
    financial_summary: detail.financial_summary,
    created_at: detail.created_at,
    age_seconds: detail.age_seconds,
});

const request = (overrides = {}) => ({
    public_id: 'request-1',
    requested_outcome: 'REFUND',
    reason: 'Cancelación con dinero',
    amount: '30.00',
    currency: 'ARS',
    status: 'PENDING_DECISION',
    decisions: [],
    events: [{public_id: 'event-1', event_type: 'REQUEST_SUBMITTED', created_at: '2026-10-30T10:05:00Z', actor: 'reviewer@test.com'}],
    ...overrides,
});

const approved = (amount = '30.00') => request({
    status: 'DECIDED',
    decisions: [{
        public_id: 'decision-1',
        sequence: 1,
        action: 'APPROVE_REFUND',
        rationale: 'Política aplicable',
        authorized_amount: amount,
        currency: 'ARS',
        policy_reference: 'POLICY-F7',
    }],
});

const operation = (status, overrides = {}) => ({
    public_id: 'operation-1',
    payment_public_id: 'payment-1',
    amount: '30.00',
    currency: 'ARS',
    status,
    provider_call_count: 1,
    last_recovery_at: null,
    events: [{public_id: 'operation-event-1', event_type: 'SUBMISSION_STARTED', created_at: '2026-10-30T10:10:00Z'}],
    ...overrides,
});

const renderCase = async (detail, refund = null) => {
    listFinancialCases.mockResolvedValue({
        data: {count: 1, next: null, previous: null, results: [listItem(detail)]},
    });
    getFinancialCase.mockResolvedValue({data: detail});
    if (refund) {
        getRefundOperation.mockResolvedValue({data: refund});
    } else {
        getRefundOperation.mockRejectedValue({response: {status: 404}});
    }
    render(<GestionIncidenciasFinancieras />);
    const row = await screen.findByRole('button', {name: new RegExp(detail.case_type_label)});
    fireEvent.click(row);
    await screen.findByRole('heading', {name: detail.case_type_label});
};


describe('GestionIncidenciasFinancieras', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        mockCanReconcile = true;
        window.confirm = jest.fn(() => true);
        financialApiError.mockImplementation((error, fallback) => (
            error.response?.status === 403
                ? 'No tenés el permiso efectivo para gestionar incidencias financieras.'
                : error.response?.status === 409
                    ? `Conflicto financiero: ${error.response.data?.code || 'conflicto'}`
                    : error.response?.status === 422
                        ? 'La operación no es procesable.'
                        : fallback
        ));
        submitResolutionRequest.mockResolvedValue({data: {}});
        recordResolutionDecision.mockResolvedValue({data: {}});
        executeAuthorizedRefund.mockResolvedValue({data: operation('SUBMITTED')});
        recoverRefundOperation.mockResolvedValue({data: operation('UNKNOWN')});
        closeFinancialCase.mockResolvedValue({data: {result: 'REFUND_CONFIRMED'}});
        requestPaidOrderCancellation.mockResolvedValue({
            data: {order_id: 91, order_status: 'PAGADO'},
        });
    });

    test('una clienta sin permiso efectivo no consulta ni ejecuta acciones', () => {
        mockCanReconcile = false;
        render(<GestionIncidenciasFinancieras />);

        expect(screen.getByRole('alert')).toHaveTextContent('reconcile_external_payment');
        expect(listFinancialCases).not.toHaveBeenCalled();
    });

    test.each([
        ['Cancelación de turno con seña', '30.00'],
        ['Cancelación de turno pagado totalmente', '100.00'],
    ])('%s presenta solicitud sin declarar refund', async (_scenario, amount) => {
        const detail = caseDetail({
            financial_summary: {
                ...caseDetail().financial_summary,
                gross_reconciled: amount,
                net_reconciled: amount,
            },
            payments: [payment({
                amount,
                financial_projection: {
                    ...payment().financial_projection,
                    gross_reconciled: amount,
                    net_reconciled: amount,
                },
            })],
        });
        await renderCase(detail);
        const form = screen.getByRole('form', {name: 'Presentar solicitud de resolución'});
        fireEvent.change(within(form).getByLabelText('Motivo'), {target: {value: 'Revisar cancelación'}});
        fireEvent.change(within(form).getByLabelText('Importe (opcional)'), {target: {value: amount}});
        fireEvent.click(within(form).getByRole('button', {name: 'Registrar solicitud'}));

        await waitFor(() => expect(submitResolutionRequest).toHaveBeenCalledTimes(1));
        expect(submitResolutionRequest.mock.calls[0][1]).toEqual(expect.objectContaining({
            reason: 'Revisar cancelación',
            amount,
            currency: 'ARS',
        }));
        expect(await screen.findByRole('status')).toHaveTextContent('no implica devolución');
    });

    test('pago tardío sin Turno se identifica sin ofrecer reservas ni B3', async () => {
        const detail = caseDetail({
            case_type: 'LATE_PAYMENT',
            case_type_label: 'Pago tardío',
            context_reference: {
                payment_intent_public_id: 'intent-late',
                payment_intent_status: 'EXPIRED',
                slot_hold_public_id: 'hold-late',
                turno_id: null,
                turno_status: null,
            },
            turno: null,
            payment_intent: {status: 'EXPIRED'},
        });
        await renderCase(detail);

        expect(screen.getAllByText('Pago de reserva sin Turno').length).toBeGreaterThan(0);
        expect(screen.queryByRole('button', {name: /crear turno|confirmar reserva/i})).not.toBeInTheDocument();
    });

    test('orden PAGADO no entregable muestra obligación y revisión, no entrega', async () => {
        const detail = caseDetail({
            case_type: 'ORDER_FULFILLMENT_FAILED',
            case_type_label: 'Orden no entregable',
            context: 'ORDER',
            context_reference: {order_id: 91, order_code: 'ORD-91', order_status: 'PAGADO'},
            payment_intent: null,
            turno: null,
            order: {id: 91, codigo: 'ORD-91', estado: 'PAGADO', total: '30.00'},
        });
        await renderCase(detail);

        expect(screen.getAllByText('Orden ORD-91').length).toBeGreaterThan(0);
        expect(screen.queryByRole('button', {name: /entregar/i})).not.toBeInTheDocument();
        expect(screen.getByRole('form', {name: 'Presentar solicitud de resolución'})).toBeInTheDocument();
    });

    test('solicita cancelación de orden PAGADO sin asumir cancelación', async () => {
        const detail = caseDetail();
        listFinancialCases.mockResolvedValue({data: {count: 0, next: null, previous: null, results: []}});
        render(<GestionIncidenciasFinancieras />);
        await screen.findByText('No hay casos para estos filtros.');
        fireEvent.click(screen.getByRole('button', {name: 'Solicitar cancelación de orden pagada'}));
        const form = screen.getByRole('form', {name: 'Solicitar cancelación de orden pagada'});
        fireEvent.change(within(form).getByLabelText('ID de Orden'), {target: {value: '91'}});
        fireEvent.change(within(form).getByLabelText('Motivo'), {target: {value: 'Cliente solicita cancelación'}});
        fireEvent.click(within(form).getByRole('button', {name: 'Registrar solicitud sin cancelar'}));

        await waitFor(() => expect(requestPaidOrderCancellation).toHaveBeenCalledTimes(1));
        expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('no cancela ni devuelve dinero'));
        expect(await screen.findByRole('status')).toHaveTextContent('conserva estado PAGADO');
        expect(detail.status).toBe('OPEN');
    });

    test('refund total confirmado habilita efecto y cierre sólo con confirmación explícita', async () => {
        const detail = caseDetail({resolution_request: approved('30.00')});
        await renderCase(detail, operation('CONFIRMED'));
        const section = screen.getByRole('region', {name: 'Aplicar resolución y cerrar'});
        fireEvent.change(within(section).getByLabelText('Fundamento de cierre'), {target: {value: 'Confirmación externa verificada'}});
        fireEvent.click(within(section).getByRole('button', {name: 'Aplicar resolución y cerrar'}));

        await waitFor(() => expect(closeFinancialCase).toHaveBeenCalledTimes(1));
        expect(closeFinancialCase.mock.calls[0][1]).toEqual({
            rationale: 'Confirmación externa verificada',
            result: 'REFUND_CONFIRMED',
        });
        expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Aplicar el efecto comercial verificable'));
    });

    test('refund parcial confirmado muestra neto y ajuste sin afirmar cancelación total', async () => {
        const partialPayment = payment({
            financial_projection: {
                ...payment().financial_projection,
                confirmed_adjustments: '10.00',
                net_reconciled: '20.00',
                refunds_confirmed: '10.00',
            },
            adjustments: [{
                public_id: 'adjustment-1',
                adjustment_type: 'REFUND',
                amount: '10.00',
                currency: 'ARS',
                provider_status: 'processed',
            }],
        });
        const detail = caseDetail({
            financial_summary: {...caseDetail().financial_summary, confirmed_adjustments: '10.00', net_reconciled: '20.00'},
            payments: [partialPayment],
            resolution_request: approved('10.00'),
        });
        await renderCase(detail, operation('CONFIRMED', {amount: '10.00'}));

        expect(screen.getAllByText(/REFUND/).some((node) => (
            node.textContent.includes('10')
        ))).toBe(true);
        expect(screen.getByText('Neto confirmado').parentElement).toHaveTextContent('20');
        expect(screen.queryByText(/orden cancelada/i)).not.toBeInTheDocument();
        expect(screen.getByRole('button', {name: 'Aplicar resolución y cerrar'})).toBeInTheDocument();
    });

    test('contracargo confirmado ofrece reconocer ajuste, no ejecutar refund', async () => {
        const detail = caseDetail({
            case_type: 'POST_PAYMENT_CHANGE',
            case_type_label: 'Novedad posterior al pago',
            payments: [payment({
                financial_projection: {...payment().financial_projection, chargebacks_confirmed: '30.00', net_reconciled: '0.00'},
                adjustments: [{public_id: 'chargeback-1', adjustment_type: 'CHARGEBACK', amount: '30.00', currency: 'ARS', provider_status: 'processed'}],
            })],
            resolution_request: request({
                requested_outcome: 'REVIEW_EXTERNAL_ADJUSTMENT',
                amount: null,
                currency: '',
            }),
        });
        await renderCase(detail);
        const form = screen.getByRole('form', {name: 'Registrar decisión financiera'});
        const options = within(form).getByLabelText('Acción');

        expect(within(options).getByRole('option', {name: 'Reconocer ajuste externo'})).toBeInTheDocument();
        expect(within(options).queryByRole('option', {name: 'Aprobar devolución'})).not.toBeInTheDocument();
        expect(screen.queryByRole('button', {name: 'Solicitar refund autorizado'})).not.toBeInTheDocument();
    });

    test('duplicación o discrepancia 409 muestra conflicto y resincroniza sin doble envío', async () => {
        const detail = caseDetail({resolution_request: request()});
        recordResolutionDecision.mockRejectedValue({
            response: {status: 409, data: {code: 'FINANCIAL_STATE_CHANGED'}},
        });
        await renderCase(detail);
        const form = screen.getByRole('form', {name: 'Registrar decisión financiera'});
        fireEvent.change(within(form).getByLabelText('Acción'), {target: {value: 'NO_FINANCIAL_CHANGE'}});
        fireEvent.change(within(form).getByLabelText('Fundamento'), {target: {value: 'Revisión manual'}});
        const button = within(form).getByRole('button', {name: 'Registrar decisión'});
        fireEvent.click(button);
        fireEvent.click(button);

        await waitFor(() => expect(financialApiError).toHaveBeenCalledTimes(1));
        expect(financialApiError.mock.results[0].value).toContain(
            'FINANCIAL_STATE_CHANGED',
        );
        expect(await screen.findByRole('alert')).toHaveTextContent('FINANCIAL_STATE_CHANGED');
        expect(recordResolutionDecision).toHaveBeenCalledTimes(1);
        expect(getFinancialCase.mock.calls.length).toBeGreaterThan(1);
    });

    test('APPROVE_REFUND sin operación exige importe y confirmación antes del envío', async () => {
        const detail = caseDetail({resolution_request: approved('30.00')});
        await renderCase(detail);
        fireEvent.click(screen.getByRole('button', {name: 'Solicitar refund autorizado'}));

        await waitFor(() => expect(executeAuthorizedRefund).toHaveBeenCalledTimes(1));
        expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Importe autorizado'));
        expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Turno #18'));
        expect(await screen.findByRole('status')).toHaveTextContent('confirmación pendiente');
    });

    test('UNKNOWN se destaca y sólo permite recuperar sin reenviar', async () => {
        const detail = caseDetail({resolution_request: approved('30.00')});
        await renderCase(detail, operation('UNKNOWN'));

        expect(screen.getAllByText(/resultado desconocido/i).length).toBeGreaterThan(0);
        expect(screen.queryByRole('button', {name: 'Solicitar refund autorizado'})).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', {name: 'Recuperar sin reenviar'}));
        await waitFor(() => expect(recoverRefundOperation).toHaveBeenCalledTimes(1));
        expect(executeAuthorizedRefund).not.toHaveBeenCalled();
        expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('sin reenviar'));
    });

    test.each([403, 422])('maneja HTTP %s y recupera estado desde backend', async (status) => {
        const detail = caseDetail();
        submitResolutionRequest.mockRejectedValue({response: {status, data: {code: 'DENIED'}}});
        await renderCase(detail);
        const form = screen.getByRole('form', {name: 'Presentar solicitud de resolución'});
        fireEvent.change(within(form).getByLabelText('Motivo'), {target: {value: 'Revisar'}});
        fireEvent.click(within(form).getByRole('button', {name: 'Registrar solicitud'}));

        await waitFor(() => expect(financialApiError).toHaveBeenCalledTimes(1));
        expect(await screen.findByRole('alert')).toBeInTheDocument();
        expect(getFinancialCase.mock.calls.length).toBeGreaterThan(1);
    });
});
