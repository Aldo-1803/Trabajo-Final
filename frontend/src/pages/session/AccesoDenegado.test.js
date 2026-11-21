import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { useSession } from '../../context/SessionContext';
import { getAuthorizedReturnPath } from '../../utils/sessionLanding';
import AccesoDenegado from './AccesoDenegado';


const mockNavigate = jest.fn();


jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('../../utils/sessionLanding', () => ({
    getAuthorizedReturnPath: jest.fn()
}));
jest.mock('react-router-dom', () => ({
    useLocation: () => ({ pathname: '/acceso-denegado' }),
    useNavigate: () => mockNavigate
}), { virtual: true });


const authenticatedSession = {
    status: 'authenticated',
    businessRole: 'CLIENTE',
    permissions: [],
    capabilities: {},
    profiles: {}
};


describe('AccesoDenegado', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        useSession.mockReturnValue({
            session: authenticatedSession,
            refreshError: null,
            refreshSession: jest.fn().mockResolvedValue(authenticatedSession)
        });
        getAuthorizedReturnPath.mockReturnValue('/perfil');
    });

    test('muestra un mensaje 403 estable sin revelar permisos internos', () => {
        render(<AccesoDenegado />);

        expect(screen.getByRole('heading', { name: 'Acceso denegado' }))
            .toBeInTheDocument();
        expect(screen.getByText(
            'No tenés permisos para acceder a esta sección.'
        )).toBeInTheDocument();
        expect(screen.queryByText(/codename|grupo|gestion\./i)).not.toBeInTheDocument();
    });

    test('ofrece el primer destino autorizado seguro', () => {
        render(<AccesoDenegado />);

        fireEvent.click(screen.getByRole('button', {
            name: 'Ir a una sección disponible'
        }));

        expect(mockNavigate).toHaveBeenCalledWith('/perfil', { replace: true });
    });

    test('sin destino no crea un bucle hacia la misma pantalla', () => {
        getAuthorizedReturnPath.mockReturnValue(null);
        render(<AccesoDenegado />);

        expect(screen.queryByRole('button', {
            name: 'Ir a una sección disponible'
        })).not.toBeInTheDocument();
        expect(screen.getByText(/No hay otra sección disponible/i))
            .toBeInTheDocument();
    });

    test('un reintento con error de red no informa revocación', async () => {
        const refreshSession = jest.fn().mockResolvedValue({
            ...authenticatedSession,
            refreshError: { kind: 'network' }
        });
        useSession.mockReturnValue({
            session: authenticatedSession,
            refreshError: null,
            refreshSession
        });
        render(<AccesoDenegado />);

        fireEvent.click(screen.getByRole('button', { name: 'Actualizar acceso' }));

        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(
            'problema de conexión'
        ));
        expect(mockNavigate).not.toHaveBeenCalled();
    });
});
