import { render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import DashboardStats from './DashboardStats';
import { useSession } from '../../context/SessionContext';


jest.mock('axios', () => ({
    __esModule: true,
    default: { get: jest.fn() }
}));
jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('recharts', () => ({
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
    BarChart: () => <div />,
    Bar: () => <div />,
    XAxis: () => <div />,
    YAxis: () => <div />,
    CartesianGrid: () => <div />,
    Tooltip: () => <div />,
    PieChart: () => <div />,
    Pie: () => <div />,
    Cell: () => <div />,
    Legend: () => <div />
}));


const setPermissions = (permissions) => {
    useSession.mockReturnValue({
        hasPermission: (permission) => permissions.includes(permission)
    });
};


describe('DashboardStats por capacidades efectivas', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'access-token');
    });

    test('view_reports muestra tendencias pero no cifras financieras', async () => {
        setPermissions(['gestion.view_reports']);
        axios.get.mockResolvedValue({
            data: {
                productos: [{ producto__nombre: 'Cofia', valor: 2 }],
                rutinas: [],
                ordenes_count: 1,
                cliente_mes: { nombre: 'Cliente Uno' }
            }
        });

        render(<DashboardStats />);

        expect(await screen.findByText('Cliente Uno')).toBeInTheDocument();
        expect(screen.getAllByText('Cofia').length).toBeGreaterThan(0);
        expect(screen.queryByText('Total Ingresos')).not.toBeInTheDocument();
        expect(screen.queryByText('Ticket Promedio')).not.toBeInTheDocument();
    });

    test('view_financial_reports muestra montos pero no identidad general', async () => {
        setPermissions(['gestion.view_financial_reports']);
        axios.get.mockResolvedValue({
            data: {
                servicios: [{ producto__nombre: 'Cofia', valor: '250.00' }],
                total_ingresos: 250
            }
        });

        render(<DashboardStats />);

        expect(await screen.findByText('Total Ingresos')).toBeInTheDocument();
        expect(screen.queryByText('Cliente del Mes')).not.toBeInTheDocument();
        expect(screen.queryByText('Productos mas vendidos')).not.toBeInTheDocument();
        await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));
    });
});
