import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import ConfirmarReclamoAcceso from './ConfirmarReclamoAcceso';


jest.mock('axios', () => ({
    __esModule: true,
    default: { post: jest.fn() }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => jest.fn(),
    useParams: () => ({ token: 'raw-one-use-token' })
}), { virtual: true });


describe('ConfirmarReclamoAcceso', () => {
    beforeEach(() => jest.clearAllMocks());

    test('verifica el token y establece la contraseña sin exponerlo en pantalla', async () => {
        axios.post.mockResolvedValue({ data: { web_access_status: 'CLAIMED' } });
        render(<ConfirmarReclamoAcceso />);
        fireEvent.change(screen.getByLabelText('Nueva contraseña de acceso'), {
            target: { value: 'ClaimedAccess!2026' }
        });
        fireEvent.change(screen.getByLabelText('Repetir contraseña de acceso'), {
            target: { value: 'ClaimedAccess!2026' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Verificar y establecer contraseña' }));

        await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
            '/api/usuarios/access-claim/confirm/',
            {
                token: 'raw-one-use-token',
                password: 'ClaimedAccess!2026',
                password2: 'ClaimedAccess!2026'
            }
        ));
        expect(await screen.findByRole('status')).toHaveTextContent(/no puede volver a utilizarse/i);
        expect(screen.queryByText('raw-one-use-token')).not.toBeInTheDocument();
    });

    test('no envía contraseñas diferentes', () => {
        render(<ConfirmarReclamoAcceso />);
        fireEvent.change(screen.getByLabelText('Nueva contraseña de acceso'), {
            target: { value: 'ClaimedAccess!2026' }
        });
        fireEvent.change(screen.getByLabelText('Repetir contraseña de acceso'), {
            target: { value: 'DifferentAccess!2026' }
        });
        fireEvent.click(screen.getByRole('button', { name: 'Verificar y establecer contraseña' }));
        expect(screen.getByRole('alert')).toHaveTextContent('no coinciden');
        expect(axios.post).not.toHaveBeenCalled();
    });
});
