import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';

import EditorContenidoEducativo from './EditorContenidoEducativo';
import { useSession } from '../../context/SessionContext';


let mockRouteId;
const mockNavigate = jest.fn();

jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        put: jest.fn(),
        post: jest.fn()
    }
}));
jest.mock('react-router-dom', () => ({
    useParams: () => ({ id: mockRouteId }),
    useNavigate: () => mockNavigate
}), { virtual: true });
jest.mock('react-hot-toast', () => ({
    __esModule: true,
    default: {
        success: jest.fn(),
        error: jest.fn()
    }
}));
jest.mock('../../context/SessionContext', () => ({
    useSession: jest.fn()
}));


const content = {
    id: 2,
    titulo: 'Contenido ajeno',
    descripcion: 'Descripción completa',
    contenido_texto: 'Texto educativo',
    multimedia_url: '',
    tipo: 'TEXTO',
    estado: 'PUBLICADO',
    autor: { id: 20, nombre: 'Otra', apellido: 'Autora' }
};

const access = ({ author = false, global = false, personalId = null } = {}) => {
    useSession.mockReturnValue({
        hasCapability: (capability) => (
            (capability === 'content.author' && author)
            || (capability === 'content.manage_global' && global)
        ),
        profiles: {
            personal: {
                exists: personalId !== null,
                active: personalId !== null,
                id: personalId
            }
        }
    });
};

const renderEditor = (id = undefined) => {
    mockRouteId = id;
    return render(<EditorContenidoEducativo />);
};


describe('EditorContenidoEducativo por ownership', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        mockRouteId = undefined;
        localStorage.setItem('access_token', 'test-token');
        axios.get.mockResolvedValue({ data: content });
        axios.put.mockResolvedValue({ data: content });
        axios.post.mockResolvedValue({ data: { id: 3 } });
    });

    test('autor ve contenido ajeno publicado en modo lectura y no puede enviar PUT', async () => {
        access({ author: true, personalId: 10 });
        renderEditor('2');

        expect(await screen.findByRole('alert')).toHaveTextContent('sólo para lectura');
        expect(screen.getByDisplayValue('Contenido ajeno')).toBeDisabled();
        expect(screen.queryByRole('button', { name: 'Actualizar' })).not.toBeInTheDocument();
        expect(axios.put).not.toHaveBeenCalled();
    });

    test('gestor global puede actualizar contenido ajeno', async () => {
        access({ global: true });
        renderEditor('2');

        const title = await screen.findByDisplayValue('Contenido ajeno');
        fireEvent.change(title, { target: { value: 'Actualizado globalmente' } });
        fireEvent.click(screen.getByRole('button', { name: 'Actualizar' }));

        await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/contenido-educativo/2/',
            expect.objectContaining({ titulo: 'Actualizado globalmente' }),
            { headers: { Authorization: 'Bearer test-token' } }
        ));
    });

    test('gestión global sin identidad de autor no puede crear ni enviar POST', () => {
        access({ global: true });
        renderEditor();

        expect(screen.getByRole('alert')).toHaveTextContent('no asigna una identidad de autor');
        expect(screen.queryByRole('button', { name: 'Crear' })).not.toBeInTheDocument();
        expect(axios.post).not.toHaveBeenCalled();
    });
});
