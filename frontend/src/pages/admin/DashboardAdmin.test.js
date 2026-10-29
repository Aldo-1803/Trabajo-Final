import { render, screen } from '@testing-library/react';
import axios from 'axios';

import DashboardAdmin from './DashboardAdmin';


const mockNavigate = jest.fn();


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn() }
}));
jest.mock('react-router-dom', () => ({
    useNavigate: () => mockNavigate
}), { virtual: true });
jest.mock('./Calendario', () => () => <div>Calendario</div>);
jest.mock('../../components/AlertasCriticas', () => () => <div>Alertas</div>);


describe('DashboardAdmin con backend legacy', () => {
    let consoleError;

    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'access-token');
        consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
    });

    afterEach(() => consoleError.mockRestore());

    test('un 403 muestra un error temporal y no redirige a perfil', async () => {
        axios.get.mockRejectedValue({ response: { status: 403 } });

        render(<DashboardAdmin />);

        expect(await screen.findByRole('heading', {
            name: 'Panel administrativo no disponible'
        })).toBeInTheDocument();
        expect(screen.getByText(
            'El dashboard administrativo todavía no está disponible para esta cuenta.'
        )).toBeInTheDocument();
        expect(mockNavigate).not.toHaveBeenCalledWith('/perfil');
    });
});
