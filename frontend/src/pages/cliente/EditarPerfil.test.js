import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import EditarPerfil from './EditarPerfil';


const mockNavigate = jest.fn();

jest.mock('axios', () => ({
    __esModule: true,
    default: {get: jest.fn(), put: jest.fn()},
}));

jest.mock('react-router-dom', () => ({
    useNavigate: () => mockNavigate,
}), {virtual: true});


const catalogs = {
    '/api/gestion/tipos-cabello/': [{id: 11, nombre: 'Ondulado'}],
    '/api/gestion/porosidades-cabello/': [{id: 22, nombre: 'Media'}],
    '/api/gestion/grosores-cabello/': [{id: 33, nombre: 'Fino'}],
    '/api/gestion/cueros-cabelludos/': [{id: 44, nombre: 'Normal'}],
    '/api/gestion/estados-generales/': [{id: 55, nombre: 'Saludable'}],
};

const profile = {
    first_name: 'Ana',
    last_name: 'Pérez',
    email: 'ana@test.com',
    tipo_cabello: 'Ondulado',
    tipo_cabello_id: 11,
    porosidad_cabello: 'Media',
    porosidad_cabello_id: 22,
    grosor_cabello: 'Fino',
    grosor_cabello_id: 33,
    cuero_cabelludo: 'Normal',
    cuero_cabelludo_id: 44,
    estado_general: 'Saludable',
    estado_general_id: 55,
};


describe('EditarPerfil', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        axios.get.mockImplementation((url) => Promise.resolve({
            data: url === '/api/usuarios/perfil/'
                ? profile
                : {results: catalogs[url]},
        }));
        axios.put.mockResolvedValue({data: profile});
    });

    test('carga IDs coherentes y conserva las selecciones guardadas', async () => {
        render(<EditarPerfil />);

        expect(await screen.findByDisplayValue('Ondulado')).toHaveValue('11');
        expect(screen.getByDisplayValue('Media')).toHaveValue('22');
        expect(screen.getByDisplayValue('Fino')).toHaveValue('33');
        expect(screen.getByDisplayValue('Normal')).toHaveValue('44');
        expect(screen.getByDisplayValue('Saludable')).toHaveValue('55');
    });

    test('envía IDs y no los nombres devueltos para lectura', async () => {
        render(<EditarPerfil />);
        await screen.findByDisplayValue('Ondulado');

        fireEvent.click(screen.getByRole('button', {name: 'Guardar Cambios'}));

        await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
            '/api/usuarios/perfil/',
            expect.objectContaining({
                tipo_cabello: 11,
                porosidad: 22,
                grosor: 33,
                cuero_cabelludo: 44,
                estado_general: 55,
            }),
        ));
    });
});
