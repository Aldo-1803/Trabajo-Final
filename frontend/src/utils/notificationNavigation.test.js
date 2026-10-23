import { getNotificationDestination } from './notificationNavigation';


const session = ({
    businessRole = 'CLIENTE',
    permissions = [],
    clientProfile = false
} = {}) => ({
    status: 'authenticated',
    businessRole,
    permissions,
    profiles: {
        cliente: { exists: clientProfile },
        personal: { exists: businessRole !== 'CLIENTE' }
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

    test('una compra administrativa requiere capacidad efectiva', () => {
        const destination = getNotificationDestination({
            id: 2,
            datos_extra: { orden_id: 21 }
        }, session({
            businessRole: 'ADMINISTRADOR',
            permissions: ['gestion.register_payment']
        }));

        expect(destination.path).toBe('/admin/ordenes');
    });

    test('PROFESIONAL con Cliente abre su turno propio, no una ruta administrativa', () => {
        const destination = getNotificationDestination({
            id: 3,
            datos_extra: { turno_id: 30 }
        }, session({
            businessRole: 'PROFESIONAL',
            permissions: ['gestion.view_global_agenda'],
            clientProfile: true
        }));

        expect(destination.path).toBe('/mis-turnos');
    });

    test('personal sin perfil Cliente recibe el destino operativo seguro', () => {
        const destination = getNotificationDestination({
            id: 4,
            datos_extra: { turno_id: 31 }
        }, session({
            businessRole: 'EMPLEADO',
            permissions: ['gestion.view_global_agenda']
        }));

        expect(destination.path).toBe('/operaciones');
    });

    test('una notificación ambigua conserva el landing seguro', () => {
        const destination = getNotificationDestination(
            { id: 5, datos_extra: {} },
            session({ businessRole: 'PROFESIONAL' })
        );

        expect(destination.path).toBe('/operaciones');
    });
});
