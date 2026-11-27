import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import ReclamarAcceso from './ReclamarAcceso';


jest.mock('axios', () => ({
    __esModule: true,
    default: { post: jest.fn() }
}));
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }), { virtual: true });


describe('ReclamarAcceso', () => {
    beforeEach(() => jest.clearAllMocks());

    test('muestra la respuesta genérica sin revelar si existe la cuenta', async () => {
        axios.post.mockResolvedValue({
            data: {
                mensaje: 'Si el email corresponde a un acceso pendiente, recibirás instrucciones.'
            }
        });
        render(<ReclamarAcceso />);
        fireEvent.change(screen.getByLabelText('Email de reclamo'), {
            target: { value: 'pending@example.com' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Enviar enlace de verificación' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/usuarios/access-claim/request/',
            { email: 'pending@example.com' }
        ));
        expect(await screen.findByRole('status')).toHaveTextContent(/Si el email corresponde/);
        expect(screen.getByText(/sin email deberán esperar/i)).toBeInTheDocument();
    });
});
