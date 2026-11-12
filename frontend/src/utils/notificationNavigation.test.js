import { getNotificationDestination } from './notificationNavigation';


const session = ({
    businessRole = 'CLIENTE',
    permissions = [],
    capabilities = {},
    clientProfile = false,
    personalActive = false
} = {}) => ({
    status: 'authenticated',
    businessRole,
    permissions,
    capabilities,
    profiles: {
        cliente: { exists: clientProfile, active: clientProfile },
        personal: {
            exists: personalActive,
            active: personalActive
        }
    },
    error: null
});


describe('getNotificationDestination', () => {
    test('una compra propia usa Mis Pedidos por perfil Cliente', () => {
        const destination = getNotificationDestination({
            id: 1,
            datos_extra: { orden_id: 20 }
        }, session({ clientProfile: true }));

        expect(destination.path).toBe('/mis-pedidos');
        expect(destination.state.ordenId).toBe(20);
    });

    test('una orden administrativa requiere exactamente manage_stock', () => {
        const destination = getNotificationDestination({
            id: 2,
            datos_extra: { orden_id: 21 }
        }, session({
            businessRole: null,
            permissions: ['gestion.manage_stock']
        }));

        expect(destination.path).toBe('/admin/ordenes');
        expect(destination.state.ordenId).toBe(21);
    });

    test('register_payment no se confunde con acceso a Órdenes', () => {
        const destination = getNotificationDestination({
            id: 3,
            datos_extra: { orden_id: 22 }
        }, session({
            businessRole: 'ADMINISTRADOR',
            permissions: ['gestion.register_payment']
        }));

        expect(destination.path).toBe('/operaciones');
        expect(destination.state).toEqual({notificacionId: 3});
    });

    test('un perfil Cliente coexistente prioriza su orden propia', () => {
        const destination = getNotificationDestination({
            id: 4,
            datos_extra: { orden_id: 23 }
        }, session({
            businessRole: 'PROFESIONAL',
            permissions: ['gestion.manage_stock'],
            clientProfile: true
        }));

        expect(destination.path).toBe('/mis-pedidos');
    });

    test('PROFESIONAL con Cliente abre su turno propio', () => {
        const destination = getNotificationDestination({
            id: 5,
            datos_extra: { turno_id: 30 }
        }, session({
            businessRole: 'PROFESIONAL',
            permissions: ['gestion.view_global_agenda'],
            clientProfile: true
        }));

        expect(destination.path).toBe('/mis-turnos');
        expect(destination.state.turnoId).toBe(30);
    });

    test('view_global_agenda abre Turnos sin exigir BusinessRole administrador', () => {
        const destination = getNotificationDestination({
            id: 6,
            datos_extra: { turno_id: 31 }
        }, session({
            businessRole: null,
            permissions: ['gestion.view_global_agenda']
        }));

        expect(destination.path).toBe('/admin/turnos');
        expect(destination.state.turnoId).toBe(31);
    });

    test('un Turno no autorizado usa landing seguro y no propaga el id', () => {
        const destination = getNotificationDestination({
            id: 7,
            datos_extra: { turno_id: 32 }
        }, session({
            businessRole: 'PROFESIONAL',
            personalActive: true
        }));

        expect(destination.path).toBe('/mi-agenda-laboral');
        expect(destination.state).toEqual({notificacionId: 7});
    });

    test('una alerta administrativa usa el mismo guard de Turnos', () => {
        const destination = getNotificationDestination({
            id: 8,
            tipo: 'alerta',
            datos_extra: {}
        }, session({permissions: ['gestion.view_global_agenda']}));

        expect(destination.path).toBe('/admin/turnos');
    });

    test('una notificación ambigua conserva el landing seguro', () => {
        const destination = getNotificationDestination(
            { id: 9, datos_extra: {} },
            session({
                businessRole: 'PROFESIONAL',
                personalActive: true
            })
        );

        expect(destination.path).toBe('/mi-agenda-laboral');
    });
});
