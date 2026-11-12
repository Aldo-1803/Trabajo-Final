import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import axios from 'axios';

import GestionContenidoEducativo from './GestionContenidoEducativo';
import { useSession } from '../../context/SessionContext';


jest.mock('axios', () => ({
    __esModule: true,
    default: {
        get: jest.fn(),
        patch: jest.fn(),
        delete: jest.fn()
    }
}));
jest.mock('react-router-dom', () => ({
    Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>
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


const ownDraft = {
    id: 1,
    titulo: 'Contenido propio',
    descripcion: 'Borrador del autor',
    contenido_texto: 'Texto',
    tipo: 'TEXTO',
    estado: 'BORRADOR',
    autor: { id: 10, nombre: 'Ana', apellido: 'Autora' },
    total_likes: 0,
    total_guardados: 0,
    fecha_actualizacion: '2026-11-10T10:00:00Z'
};

const foreignPublished = {
    ...ownDraft,
    id: 2,
    titulo: 'Contenido ajeno',
    descripcion: 'Publicado por otra persona',
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

const renderLoaded = async () => {
    render(<GestionContenidoEducativo />);
    await screen.findByText('Contenido propio');
};

const cardFor = (title) => screen.getByText(title).closest('.bg-white');


describe('GestionContenidoEducativo por autoría y gestión global', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.setItem('access_token', 'test-token');
        axios.get.mockResolvedValue({
            data: { results: [ownDraft, foreignPublished] }
        });
        axios.patch.mockResolvedValue({ data: {} });
        axios.delete.mockResolvedValue({ data: {} });
        jest.spyOn(window, 'confirm').mockReturnValue(true);
    });

    afterEach(() => window.confirm.mockRestore());

    test('autor puede operar contenido propio pero no publicado ajeno', async () => {
        access({ author: true, personalId: 10 });
        await renderLoaded();

        expect(screen.getByRole('link', { name: '+ Crear Contenido' })).toBeInTheDocument();
        expect(within(cardFor('Contenido propio')).getByRole('link', { name: 'Editar' }))
            .toBeInTheDocument();
        expect(within(cardFor('Contenido propio')).getByRole('button', { name: 'Publicar' }))
            .toBeInTheDocument();
        expect(within(cardFor('Contenido propio')).queryByRole('button', { name: 'Archivar' }))
            .not.toBeInTheDocument();
        expect(within(cardFor('Contenido ajeno')).queryByRole('link', { name: 'Editar' }))
            .not.toBeInTheDocument();
        expect(within(cardFor('Contenido ajeno')).queryByRole('button', { name: 'Archivar' }))
            .not.toBeInTheDocument();

        fireEvent.click(within(cardFor('Contenido propio')).getByRole('button', { name: 'Publicar' }));
        await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/contenido-educativo/1/',
            { estado: 'PUBLICADO' },
            { headers: { Authorization: 'Bearer test-token' } }
        ));
    });

    test('autor puede solicitar la eliminación lógica de contenido propio', async () => {
        access({ author: true, personalId: 10 });
        await renderLoaded();

        fireEvent.click(within(cardFor('Contenido propio')).getByRole('button', {
            name: 'Eliminar'
        }));

        await waitFor(() => expect(axios.delete).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/contenido-educativo/1/',
            { headers: { Authorization: 'Bearer test-token' } }
        ));
    });

    test('gestor global opera contenido ajeno pero sin autor activo no puede crear', async () => {
        access({ global: true });
        await renderLoaded();

        expect(screen.queryByRole('link', { name: '+ Crear Contenido' })).not.toBeInTheDocument();
        expect(within(cardFor('Contenido ajeno')).getByRole('link', { name: 'Editar' }))
            .toBeInTheDocument();
        fireEvent.click(within(cardFor('Contenido ajeno')).getByRole('button', { name: 'Archivar' }));

        await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(
            'http://127.0.0.1:8000/api/gestion/contenido-educativo/2/',
            { estado: 'ARCHIVADO' },
            { headers: { Authorization: 'Bearer test-token' } }
        ));
    });

    test('lector sin capability conserva lectura sin acciones mutadoras', async () => {
        access();
        await renderLoaded();

        expect(screen.queryByRole('link', { name: /Crear Contenido/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Editar' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Publicar|Archivar|Eliminar|Reabrir/ }))
            .not.toBeInTheDocument();
        expect(axios.patch).not.toHaveBeenCalled();
        expect(axios.delete).not.toHaveBeenCalled();
    });
});
