import { render, screen } from '@testing-library/react';

import AccesoDenegado from './AccesoDenegado';


describe('AccesoDenegado', () => {
    test('muestra un mensaje 403 estable sin revelar permisos internos', () => {
        render(<AccesoDenegado />);

        expect(screen.getByRole('heading', { name: 'Acceso denegado' }))
            .toBeInTheDocument();
        expect(screen.getByText(
            'No tenés permisos para acceder a esta sección.'
        )).toBeInTheDocument();
    });
});
