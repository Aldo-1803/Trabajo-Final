import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import ClienteCreationForm from './ClienteCreationForm';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn(), post: jest.fn() }
}));
jest.mock('../utils/notificaciones', () => ({
    notify: { success: jest.fn(), error: jest.fn() }
}));

const createdResult = {
    created: true,
    recovered: false,
    cliente_id: 15,
    display_name: 'Ana Pérez',
    masked_email: null,
    masked_phone: '***4567',
    cliente_activo: true,
    web_access_status: 'PENDING_CLAIM',
    operation_id: 'operation-15'
};

const fillNewClient = ({ email = '', phone = '+54 9 11 6123-4567' } = {}) => {
    fireEvent.change(screen.getByLabelText('Nombre *'), { target: { value: 'Ana' } });
    fireEvent.change(screen.getByLabelText('Apellido *'), { target: { value: 'Pérez' } });
    if (email) {
        fireEvent.change(screen.getByLabelText('Email (opcional)'), { target: { value: email } });
    }
    if (phone) {
        fireEvent.change(screen.getByLabelText('Teléfono (opcional)'), { target: { value: phone } });
    }
    fireEvent.change(screen.getByLabelText('Motivo *'), { target: { value: 'Alta presencial' } });
};


describe('ClienteCreationForm BH-064', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        sessionStorage.clear();
    });

    test('busca y selecciona un Cliente existente sin descargar la cartera ni crear otro', async () => {
        axios.get.mockResolvedValue({
            data: {
                results: [{
                    cliente_id: 8,
                    display_name: 'Eva Existente',
                    masked_email: 'e***@example.com',
                    masked_phone: '***4567',
                    active: true,
                    web_access_status: 'CLAIMED'
                }],
                total: 1
            }
        });
        render(<ClienteCreationForm />);
        fireEvent.change(screen.getByLabelText('Buscar Cliente existente'), {
            target: { value: 'Eva' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Buscar' }));

        await waitFor(() => expect(axios.get).toHaveBeenCalledWith(
            '/api/usuarios/asistido/clientes/selector/',
            { params: { q: 'Eva', page: 1, page_size: 10 } }
        ));
        fireEvent.click(await screen.findByRole('button', { name: 'Usar este Cliente' }));
        expect(screen.getByText('Cliente existente seleccionado')).toBeInTheDocument();
        expect(screen.getByText('CLAIMED')).toBeInTheDocument();
        expect(axios.post).not.toHaveBeenCalled();
    });

    test('admite email opcional, no muestra contraseña y bloquea doble submit', async () => {
        let resolveRequest;
        axios.post.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
        render(<ClienteCreationForm />);
        fillNewClient();
        expect(screen.queryByLabelText(/Contraseña/)).not.toBeInTheDocument();

        const submit = screen.getByRole('button', { name: 'Confirmar alta' });
        fireEvent.click(submit);
        fireEvent.click(submit);
        expect(axios.post).toHaveBeenCalledTimes(1);
        resolveRequest({ data: createdResult });
        expect(await screen.findByText('Cliente creado')).toBeInTheDocument();
        expect(screen.getByText('PENDING_CLAIM')).toBeInTheDocument();
    });

    test('un timeout conserva exactamente la clave y el payload para recuperar resultado', async () => {
        axios.post
            .mockRejectedValueOnce(new Error('Network timeout'))
            .mockResolvedValueOnce({ data: { ...createdResult, recovered: true } });
        render(<ClienteCreationForm />);
        fillNewClient({ email: 'ana@example.com', phone: '' });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));

        const retry = await screen.findByRole('button', { name: 'Reintentar la misma operación' });
        const firstCall = axios.post.mock.calls[0];
        expect(screen.getByLabelText('Nombre *')).toBeDisabled();
        fireEvent.click(retry);

        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        const secondCall = axios.post.mock.calls[1];
        expect(secondCall[1]).toEqual(firstCall[1]);
        expect(secondCall[2].headers['Idempotency-Key']).toBe(
            firstCall[2].headers['Idempotency-Key']
        );
        expect(await screen.findByText('Cliente creado')).toBeInTheDocument();
        expect(sessionStorage.getItem('bh064.walkin.uncertain-operation')).toBeNull();
    });

    test('exige revisión y justificación real para CREATE_DISTINCT', async () => {
        const candidate = {
            cliente_id: 21,
            display_name: 'Ana Similar',
            masked_email: 'a***@example.com',
            masked_phone: '***4567',
            active: true,
            web_access_status: 'CLAIMED'
        };
        axios.post
            .mockRejectedValueOnce({
                response: {
                    status: 409,
                    data: {
                        error: {
                            code: 'DUPLICATE_REVIEW_REQUIRED',
                            detail: 'Debe revisar.',
                            candidates: [candidate]
                        }
                    }
                }
            })
            .mockResolvedValueOnce({ data: createdResult });
        render(<ClienteCreationForm />);
        fillNewClient({ email: 'other@example.com' });
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));

        const createDistinct = await screen.findByRole('button', { name: 'Crear como persona distinta' });
        expect(createDistinct).toBeDisabled();
        fireEvent.click(screen.getByRole('checkbox', { name: /Revisé esta coincidencia/ }));
        expect(createDistinct).toBeEnabled();
        fireEvent.click(createDistinct);
        expect(await screen.findByRole('alert')).toHaveTextContent(/Justificá/);

        fireEvent.change(screen.getByLabelText('Justificación de identidad distinta'), {
            target: { value: 'Son familiares que comparten el teléfono' }
        });
        fireEvent.click(createDistinct);
        await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
        expect(axios.post.mock.calls[1][1]).toEqual(expect.objectContaining({
            duplicate_resolution: 'CREATE_DISTINCT',
            reviewed_candidate_ids: [21],
            duplicate_reason: 'Son familiares que comparten el teléfono'
        }));
    });

    test.each([
        [401, 'La sesión expiró'],
        [403, 'Ya no tenés permiso'],
        [400, 'Teléfono inválido'],
        [409, 'Conflicto de identidad']
    ])('presenta el error HTTP %s sin inventar un destino', async (status, detail) => {
        axios.post.mockRejectedValue({
            response: {
                status,
                data: { error: { code: 'TEST', detail } }
            }
        });
        render(<ClienteCreationForm />);
        fillNewClient();
        fireEvent.click(screen.getByRole('button', { name: 'Confirmar alta' }));
        expect(await screen.findByRole('alert')).toHaveTextContent(
            status === 401
                ? 'La sesión expiró'
                : status === 403
                    ? 'Ya no tenés permiso'
                    : detail
        );
        expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });
});
