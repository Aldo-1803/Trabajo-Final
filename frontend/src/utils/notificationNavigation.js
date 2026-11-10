import {
    ADMIN_ROUTES,
    CLIENTE_ROUTES
} from '../routes/routes';
import {
    sessionHasPermission,
    sessionHasProfile
} from './accessRules';
import { getLandingPath } from './sessionLanding';


const canUseAdministrativeTurnos = (session) => (
    sessionHasPermission(session, 'gestion.view_global_agenda')
);


const canUseAdministrativeOrders = (session) => (
    sessionHasPermission(session, 'gestion.manage_stock')
);


export const getNotificationDestination = (notification, session) => {
    const extra = notification.datos_extra || {};
    const fallback = getLandingPath(session) || '/login';
    const baseState = { notificacionId: notification.id };
    let path = fallback;
    let state = baseState;

    if (
        extra.servicio_id
        && extra.fecha
        && sessionHasProfile(session, 'cliente')
    ) {
        path = CLIENTE_ROUTES.RESERVAR;
        state = {
            ...baseState,
            servicioPreseleccionado: extra.servicio_id,
            fechaSugerida: extra.fecha,
            horaSugerida: extra.hora || null,
            profesionalId: extra.profesional_id || null
        };
    } else if (extra.promo_id && sessionHasProfile(session, 'cliente')) {
        path = CLIENTE_ROUTES.CATALOGO_PRODUCTOS;
        state = { ...baseState, promoId: extra.promo_id };
    } else if (extra.contexto === 'compra_exitosa' || extra.orden_id) {
        if (sessionHasProfile(session, 'cliente')) {
            path = CLIENTE_ROUTES.MIS_PEDIDOS;
            state = { ...baseState, ordenId: extra.orden_id || null };
        } else if (canUseAdministrativeOrders(session)) {
            path = ADMIN_ROUTES.ORDENES;
            state = { ...baseState, ordenId: extra.orden_id || null };
        }
    } else if (extra.turno_id) {
        if (sessionHasProfile(session, 'cliente')) {
            path = CLIENTE_ROUTES.MIS_TURNOS;
            state = { ...baseState, turnoId: extra.turno_id };
        } else if (canUseAdministrativeTurnos(session)) {
            path = ADMIN_ROUTES.TURNOS;
            state = { ...baseState, turnoId: extra.turno_id };
        }
    } else if (['alerta', 'recordatorio'].includes(notification.tipo)) {
        if (sessionHasProfile(session, 'cliente')) {
            path = CLIENTE_ROUTES.MIS_TURNOS;
        } else if (canUseAdministrativeTurnos(session)) {
            path = ADMIN_ROUTES.TURNOS;
        }
    } else if (
        notification.tipo === 'diagnostico'
        && sessionHasProfile(session, 'cliente')
    ) {
        path = CLIENTE_ROUTES.PERFIL;
    } else if (
        notification.tipo === 'promocion'
        && sessionHasProfile(session, 'cliente')
    ) {
        path = CLIENTE_ROUTES.CATALOGO_PRODUCTOS;
    }

    return { path, state };
};
