import { render, screen } from '@testing-library/react';

import { useSession } from '../../context/SessionContext';
import Operaciones from './Operaciones';


jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));
jest.mock('react-router-dom', () => ({
    Navigate: ({ to }) => <span>Navegando a {to}</span>
}), { virtual: true });


const sessionForRole = (businessRole) => ({
    session: {
        status: 'authenticated',
        businessRole,
        error: null
    },
    user: {
        first_name: 'Ana',
        email: 'ana@example.com'
    },
    businessRole,
    profiles: {
        cliente: { exists: true },
        personal: { exists: true }
    },
    loading: false
});


const renderOperations = (businessRole) => {
    useSession.mockReturnValue(sessionForRole(businessRole));
    return render(<Operaciones />);
};


describe('Operaciones temporal', () => {
    test.each(['EMPLEADO', 'PROFESIONAL'])(
        'renderiza el panel temporal para %s',
        (businessRole) => {
            renderOperations(businessRole);

            expect(screen.getByRole('heading', { name: 'Hola, Ana' }))
                .toBeInTheDocument();
            expect(screen.getByText(`BusinessRole: ${businessRole}`))
                .toBeInTheDocument();
            expect(screen.getByText('Panel operativo en construcción'))
                .toBeInTheDocument();
        }
    );
});
