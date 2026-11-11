import React, { useEffect, useState } from 'react';
import {
    act,
    fireEvent,
    render,
    screen,
    waitFor
} from '@testing-library/react';
import axios from 'axios';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { fetchCurrentSession } from '../api/sessionApi';
import Header from '../components/Header';
import {
    SESSION_REFRESH_INTERVAL_MS,
    SessionProvider,
    useSession
} from '../context/SessionContext';
import ProtectedRoute from '../routes/ProtectedRoute';
import { getNotificationDestination } from '../utils/notificationNavigation';
import { getLandingPath } from '../utils/sessionLanding';


// CRA/Jest 27 no interpreta los exports condicionales de React Router 7.
// Estos aliases cargan sus builds CommonJS reales sin reemplazar su conducta.
jest.mock('react-router', () => {
    const { TextDecoder, TextEncoder } = jest.requireActual('util');
    global.TextDecoder = global.TextDecoder || TextDecoder;
    global.TextEncoder = global.TextEncoder || TextEncoder;
    return jest.requireActual(
        '../../node_modules/react-router/dist/development/index.js'
    );
}, { virtual: true });
jest.mock('react-router/dom', () => jest.requireActual(
    '../../node_modules/react-router/dist/development/dom-export.js'
), { virtual: true });
jest.mock('react-router-dom', () => jest.requireActual(
    '../../node_modules/react-router-dom/dist/index.js'
), { virtual: true });
jest.mock('axios', () => ({
    __esModule: true,
    default: {
        defaults: { headers: { common: {} } },
        get: jest.fn(),
        post: jest.fn()
    }
}));
jest.mock('../api/sessionApi', () => ({
    fetchCurrentSession: jest.fn()
}));
jest.mock('../components/CampanaNotificaciones', () => () => (
    <span aria-label="Notificaciones disponibles" />
));


const sessionPayload = ({ businessRole = null, permissions = [] } = {}) => ({
    user: {
        id: 42,
        email: 'integration@example.com',
        first_name: 'Integración',
        last_name: 'BH062',
        is_active: true
    },
    business_role: businessRole,
    permissions,
    capabilities: {},
    profiles: {
        cliente: { exists: false, id: null, active: null },
        personal: {
            exists: false,
            id: null,
            active: null,
            function_role: null
        }
    }
});


const ProtectedUsersProbe = () => {
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        axios.get('/api/integration/protected-users/').then(() => {
            setLoaded(true);
        });
    }, []);

    return (
        <section>
            <h1>Usuarios protegidos</h1>
            {loaded && <p>Datos autorizados cargados</p>}
            <button
                type="button"
                onClick={() => axios.post('/api/integration/protected-users/action/')}
            >
                Ejecutar acción protegida
            </button>
        </section>
    );
};


const SessionEvidence = () => {
    const { session } = useSession();
    if (session.status !== 'authenticated') return null;

    const notification = getNotificationDestination({
        id: 90,
        datos_extra: { orden_id: 15 }
    }, session);
    return (
        <aside>
            <span data-testid="landing">{getLandingPath(session)}</span>
            <span data-testid="notification">{notification.path}</span>
        </aside>
    );
};


const IntegratedApp = () => (
    <SessionProvider>
        <Header />
        <SessionEvidence />
        <Routes>
            <Route
                path="/admin/usuarios"
                element={(
                    <ProtectedRoute requiredPermission="usuarios.manage_users">
                        <ProtectedUsersProbe />
                    </ProtectedRoute>
                )}
            />
            <Route
                path="/acceso-denegado"
                element={<h1>Acceso denegado integrado</h1>}
            />
            <Route path="/login" element={<h1>Login integrado</h1>} />
        </Routes>
    </SessionProvider>
);


const renderIntegratedApp = () => render(
    <MemoryRouter initialEntries={['/admin/usuarios']}>
        <IntegratedApp />
    </MemoryRouter>
);


describe('integración de autoridad efectiva en UI', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        localStorage.clear();
        localStorage.setItem('access_token', 'integration-token');
        axios.get.mockImplementation((url) => Promise.resolve({
            data: url.includes('/configuracion/publica/')
                ? { empresa_nombre: 'Bohemia Hair' }
                : { results: [] }
        }));
        axios.post.mockResolvedValue({ data: { changed: true } });
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    test.each([
        ['BusinessRole', 'ADMINISTRADOR'],
        ['grupo técnico', null],
        ['permiso individual', null]
    ])(
        'el snapshot efectivo de %s alinea URL, menú, landing, notificación y acción',
        async (origin, businessRole) => {
            fetchCurrentSession.mockResolvedValue({
                data: sessionPayload({
                    businessRole,
                    permissions: [
                        'usuarios.manage_users',
                        'gestion.manage_stock'
                    ]
                })
            });

            renderIntegratedApp();

            expect(await screen.findByRole('heading', {
                name: 'Usuarios protegidos'
            })).toBeInTheDocument();
            expect(await screen.findByText('Datos autorizados cargados'))
                .toBeInTheDocument();
            expect(screen.getByRole('link', { name: 'Usuarios' }))
                .toHaveAttribute('href', '/admin/usuarios');
            expect(screen.getByTestId('landing')).toHaveTextContent('/admin/usuarios');
            expect(screen.getByTestId('notification'))
                .toHaveTextContent('/admin/ordenes');
            expect(axios.get).toHaveBeenCalledWith(
                '/api/integration/protected-users/'
            );

            fireEvent.click(screen.getByRole('button', {
                name: 'Ejecutar acción protegida'
            }));

            expect(axios.post).toHaveBeenCalledWith(
                '/api/integration/protected-users/action/'
            );
        }
    );

    test('foco posterior al intervalo retira ruta y acción sin repetir el fetch', async () => {
        let now = 1000;
        jest.spyOn(Date, 'now').mockImplementation(() => now);
        fetchCurrentSession
            .mockResolvedValueOnce({
                data: sessionPayload({
                    businessRole: 'ADMINISTRADOR',
                    permissions: ['usuarios.manage_users']
                })
            })
            .mockResolvedValueOnce({
                data: sessionPayload({ businessRole: 'CLIENTE' })
            });
        renderIntegratedApp();
        expect(await screen.findByText('Datos autorizados cargados'))
            .toBeInTheDocument();
        expect(axios.get.mock.calls.filter(
            ([url]) => url === '/api/integration/protected-users/'
        )).toHaveLength(1);

        now += SESSION_REFRESH_INTERVAL_MS + 1;
        act(() => window.dispatchEvent(new Event('focus')));

        expect(await screen.findByRole('heading', {
            name: 'Acceso denegado integrado'
        })).toBeInTheDocument();
        await waitFor(() => expect(screen.queryByRole('link', {
            name: 'Usuarios'
        })).not.toBeInTheDocument());
        expect(screen.queryByRole('button', {
            name: 'Ejecutar acción protegida'
        })).not.toBeInTheDocument();
        expect(axios.get.mock.calls.filter(
            ([url]) => url === '/api/integration/protected-users/'
        )).toHaveLength(1);
        expect(axios.post).not.toHaveBeenCalled();
    });
});
