import { fireEvent, render, screen } from '@testing-library/react';
import axios from 'axios';

import DashboardAdmin from './DashboardAdmin';
import { useSession } from '../../context/SessionContext';


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
jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));


describe('DashboardAdmin con backend legacy', () => {
    let consoleError;

    beforeEach(() => {
        jest.clearAllMocks();
        useSession.mockReturnValue({
            hasPermission: () => false,
            hasAnyPermission: () => false,
            hasCapability: () => false
        });
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

    test('view_reports no muestra accesos rápidos sin sus permisos propios', async () => {
        axios.get.mockResolvedValue({
            data: {
                turnos_hoy: 0,
                pendientes_accion: 0,
                esperando_sena: 0,
                proximos_turnos: []
            }
        });

        render(<DashboardAdmin />);

        expect(await screen.findByText('Gestión Rápida')).toBeInTheDocument();
        expect(screen.queryByText('Configuración del Sistema')).not.toBeInTheDocument();
        expect(screen.queryByText('Gestionar Rutinas')).not.toBeInTheDocument();
        expect(screen.queryByText('Alertas')).not.toBeInTheDocument();
    });

    test('la tarjeta de solicitudes no navega a Turnos sin view_global_agenda', async () => {
        axios.get.mockResolvedValue({
            data: {
                turnos_hoy: 0,
                pendientes_accion: 2,
                esperando_sena: 0,
                proximos_turnos: []
            }
        });

        render(<DashboardAdmin />);
        fireEvent.click(await screen.findByText('Solicitudes Nuevas'));

        expect(mockNavigate).not.toHaveBeenCalled();
    });

    test('capability de fórmulas muestra el acceso parcial a Servicios', async () => {
        useSession.mockReturnValue({
            hasPermission: () => false,
            hasAnyPermission: () => false,
            hasCapability: (capability) => (
                capability === 'service_formula.manage'
            )
        });
        axios.get.mockResolvedValue({
            data: {
                turnos_hoy: 0,
                pendientes_accion: 0,
                esperando_sena: 0,
                proximos_turnos: []
            }
        });

        render(<DashboardAdmin />);

        expect(await screen.findByText('Servicios & Impacto'))
            .toBeInTheDocument();
    });
});
