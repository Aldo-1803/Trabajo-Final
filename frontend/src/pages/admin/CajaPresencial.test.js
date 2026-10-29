import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import { useSession } from '../../context/SessionContext';
import CajaPresencial from './CajaPresencial';


jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), post: jest.fn()},
}));
jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn(),
}));

const intent = {
    public_id: '11111111-1111-4111-8111-111111111111',
    cliente_id: 8,
    cliente_nombre: 'Ada Lovelace',
    cliente_email: 'ada@example.com',
    context: 'BOOKING',
    total_amount_snapshot: '1000.00',
    required_amount: '250.00',
    currency: 'ARS',
    status: 'CREATED',
    effective_status: 'CREATED',
    paid_reconciled: '0.00',
    confirmation_due: '250.00',
    balance: '1000.00',
    confirmed_turno_id: null,
    enabled_manual_methods: ['CASH', 'BANK_TRANSFER'],
    allows_partial_payments: true,
    checkout: null,
};

const pendingPayment = {
    public_id: '22222222-2222-4222-8222-222222222222',
    amount: '200.00',
    currency: 'ARS',
    method: 'BANK_TRANSFER',
    purpose: 'CONFIRMATION',
    status: 'PENDING_RECONCILIATION',
    recorded_by: 'caja@example.com',
    receipt_download: `/api/gestion/payments/22222222-2222-4222-8222-222222222222/receipt/`,
};

const financial = (overrides = {}) => ({
    paid_reconciled: '0.00',
    confirmation_due: '250.00',
    balance: '1000.00',
    financial_threshold_reached: false,
    ...overrides,
});

let paymentRows;
let currentFinancial;

const setPermissions = (permissions) => {
    useSession.mockReturnValue({
        hasPermission: (permission) => permissions.includes(permission),
    });
};

const mockReads = () => {
    axios.get.mockImplementation((url) => {
        if (url === '/api/gestion/payment-intents/') {
            return Promise.resolve({data: [intent]});
        }
        if (url.endsWith('/payments/')) {
            return Promise.resolve({
                data: {results: paymentRows, financial: currentFinancial},
            });
        }
        if (url.endsWith('/receipt/')) {
            return Promise.resolve({data: new Blob(['receipt'])});
        }
        return Promise.reject(new Error(`Unexpected GET ${url}`));
    });
};

const selectIntent = async () => {
    fireEvent.click(await screen.findByRole('button', {
        name: 'Gestionar obligación',
    }));
    await screen.findByRole('heading', {name: 'Ada Lovelace', level: 2});
};


describe('CajaPresencial', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
        localStorage.setItem('access_token', 'financial-token');
        paymentRows = [];
        currentFinancial = financial();
        setPermissions(['gestion.register_payment']);
        mockReads();
        Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: {writeText: jest.fn().mockResolvedValue(undefined)},
        });
    });

    test('lectura financiera muestra obligación verificable y oculta mutaciones', async () => {
        setPermissions(['gestion.view_financial_reports']);
        render(<CajaPresencial />);
        await selectIntent();

        expect(screen.getAllByText('ada@example.com')).toHaveLength(2);
        expect(screen.getByText(/Contexto:/)).toHaveTextContent('BOOKING');
        expect(screen.getByText(/B2 admite pagos parciales/)).toBeInTheDocument();
        expect(screen.queryByRole('button', {name: 'Registrar efectivo'})).not.toBeInTheDocument();
        expect(screen.queryByRole('button', {name: 'Generar o recuperar enlace'})).not.toBeInTheDocument();
        expect(axios.get).toHaveBeenCalledWith(
            '/api/gestion/payment-intents/',
            {
                headers: {Authorization: 'Bearer financial-token'},
                params: {},
            }
        );
    });

    test('registra CASH por B2 sin enviar ni modificar el total y actualiza saldo', async () => {
        axios.post.mockImplementation(async () => {
            currentFinancial = financial({
                paid_reconciled: '250.00',
                confirmation_due: '0.00',
                balance: '750.00',
                financial_threshold_reached: true,
            });
            return {data: {...pendingPayment, method: 'CASH', status: 'RECONCILED', financial: currentFinancial}};
        });
        render(<CajaPresencial />);
        await selectIntent();
        fireEvent.change(screen.getByLabelText('Importe efectivo'), {
            target: {value: '250.00'},
        });
        fireEvent.click(screen.getByRole('button', {name: 'Registrar efectivo'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
        const [url, payload, config] = axios.post.mock.calls[0];
        expect(url).toBe(`/api/gestion/payment-intents/${intent.public_id}/payments/`);
        expect(payload).toMatchObject({
            amount: '250.00',
            currency: 'ARS',
            method: 'CASH',
            purpose: 'CONFIRMATION',
            occurred_at: expect.any(String),
        });
        expect(payload).not.toHaveProperty('total');
        expect(config.headers).toMatchObject({
            Authorization: 'Bearer financial-token',
            'Idempotency-Key': expect.any(String),
        });
        expect(await screen.findByRole('status')).toHaveTextContent(/conciliado por B2/);
        expect(screen.getAllByText(/750/).length).toBeGreaterThan(0);
    });

    test('transferencia usa FormData, queda pendiente y conserva evidencia privada', async () => {
        axios.post.mockImplementation(async () => {
            paymentRows = [pendingPayment];
            return {data: {...pendingPayment, financial: currentFinancial}};
        });
        render(<CajaPresencial />);
        await selectIntent();
        fireEvent.change(screen.getByLabelText('Importe transferencia'), {
            target: {value: '200.00'},
        });
        fireEvent.change(screen.getByLabelText('Referencia transferencia'), {
            target: {value: 'TRX-2026-10'},
        });
        const receipt = new File(['evidence'], 'transfer.pdf', {type: 'application/pdf'});
        fireEvent.change(screen.getByLabelText('Comprobante transferencia'), {
            target: {files: [receipt]},
        });
        fireEvent.click(screen.getByRole('button', {name: 'Registrar transferencia'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
        const [, data, config] = axios.post.mock.calls[0];
        expect(data).toBeInstanceOf(FormData);
        expect(data.get('amount')).toBe('200.00');
        expect(data.get('method')).toBe('BANK_TRANSFER');
        expect(data.get('manual_reference')).toBe('TRX-2026-10');
        expect(data.get('receipt')).toBe(receipt);
        expect(config.headers['Idempotency-Key']).toEqual(expect.any(String));
        expect(await screen.findByText('Estado: Pendiente de conciliación')).toBeInTheDocument();
        expect(screen.getByRole('status')).toHaveTextContent(/pendiente de conciliación/);
    });

    test('confirm_deposit concilia evidencia y descarga el archivo con autenticación', async () => {
        setPermissions(['gestion.confirm_deposit']);
        paymentRows = [pendingPayment];
        const createObjectURL = jest.fn(() => 'blob:private-receipt');
        const revokeObjectURL = jest.fn();
        Object.defineProperty(window.URL, 'createObjectURL', {configurable: true, value: createObjectURL});
        Object.defineProperty(window.URL, 'revokeObjectURL', {configurable: true, value: revokeObjectURL});
        axios.post.mockImplementation(async (url) => {
            if (url.endsWith('/reconcile/')) {
                paymentRows = [{...pendingPayment, status: 'RECONCILED'}];
                currentFinancial = financial({
                    paid_reconciled: '200.00',
                    confirmation_due: '50.00',
                    balance: '800.00',
                });
                return {data: {...paymentRows[0], financial: currentFinancial}};
            }
            throw new Error(`Unexpected POST ${url}`);
        });
        render(<CajaPresencial />);
        await selectIntent();

        expect(screen.queryByRole('button', {name: 'Registrar efectivo'})).not.toBeInTheDocument();
        fireEvent.click(await screen.findByRole('button', {name: 'Conciliar'}));
        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            `/api/gestion/payments/${pendingPayment.public_id}/reconcile/`,
            {decision: 'ACCEPT', reason: ''},
            {headers: {Authorization: 'Bearer financial-token'}}
        ));
        expect(await screen.findByText('Estado: Reconciliado')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', {name: 'Descargar comprobante privado'}));
        await waitFor(() => expect(axios.get).toHaveBeenCalledWith(
            pendingPayment.receipt_download,
            {
                headers: {Authorization: 'Bearer financial-token'},
                responseType: 'blob',
            }
        ));
        expect(createObjectURL).toHaveBeenCalled();
    });

    test('genera C1 IN_PERSON, no acredita y permite copiar el enlace', async () => {
        const checkout = 'https://www.mercadopago.com.ar/checkout/presencial';
        axios.post.mockResolvedValue({
            data: {
                status: 'READY',
                checkout_url: checkout,
                financial_authority: false,
            },
        });
        render(<CajaPresencial />);
        await selectIntent();
        fireEvent.click(screen.getByRole('button', {name: 'Generar o recuperar enlace'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            `/api/gestion/payment-intents/${intent.public_id}/checkout/`,
            {channel: 'IN_PERSON'},
            {headers: {
                Authorization: 'Bearer financial-token',
                'Idempotency-Key': expect.any(String),
            }}
        ));
        expect(axios.post.mock.calls[0][1]).not.toHaveProperty('amount');
        expect(await screen.findByRole('status')).toHaveTextContent(/no acredita ningún pago/);
        fireEvent.click(screen.getByRole('button', {name: 'Copiar enlace'}));
        await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(checkout));
    });

    test('retry 409 reutiliza clave y payload sin crear un envío distinto', async () => {
        axios.post
            .mockRejectedValueOnce({
                response: {status: 409, data: {detail: 'Conflicto temporal de idempotencia.'}},
            })
            .mockResolvedValueOnce({
                data: {...pendingPayment, method: 'CASH', status: 'RECONCILED', financial: currentFinancial},
            });
        render(<CajaPresencial />);
        await selectIntent();
        fireEvent.change(screen.getByLabelText('Importe efectivo'), {target: {value: '100.00'}});
        fireEvent.click(screen.getByRole('button', {name: 'Registrar efectivo'}));
        expect(await screen.findByRole('alert')).toHaveTextContent('Conflicto temporal de idempotencia.');
        fireEvent.click(screen.getByRole('button', {name: 'Registrar efectivo'}));

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        const first = axios.post.mock.calls[0];
        const second = axios.post.mock.calls[1];
        expect(second[2].headers['Idempotency-Key']).toBe(first[2].headers['Idempotency-Key']);
        expect(second[1].occurred_at).toBe(first[1].occurred_at);
        expect(second[1]).toEqual(first[1]);
    });

    test('403 de dominio se muestra y no duplica un envío en curso', async () => {
        let rejectRequest;
        axios.post.mockImplementation(() => new Promise((_resolve, reject) => {
            rejectRequest = reject;
        }));
        render(<CajaPresencial />);
        await selectIntent();
        const button = screen.getByRole('button', {name: 'Registrar efectivo'});
        fireEvent.click(button);
        fireEvent.click(button);
        expect(axios.post).toHaveBeenCalledTimes(1);

        rejectRequest({response: {status: 403, data: {}}});
        expect(await screen.findByRole('alert')).toHaveTextContent(/No tenés permiso/);
    });

    test('rechazo exige motivo antes de llamar al backend', async () => {
        setPermissions(['gestion.confirm_deposit']);
        paymentRows = [pendingPayment];
        render(<CajaPresencial />);
        await selectIntent();
        fireEvent.click(await screen.findByRole('button', {name: 'Rechazar'}));

        expect(await screen.findByRole('alert')).toHaveTextContent(/Informá una razón/);
        expect(axios.post).not.toHaveBeenCalled();
    });
});
