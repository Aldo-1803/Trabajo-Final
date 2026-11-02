import {
    ADMIN_ROUTES,
    CLIENTE_ROUTES,
    SESSION_ROUTES
} from '../routes/routes';
import { getLandingPath } from './sessionLanding';


const hasPermission = (session, permission) => (
    Array.isArray(session.permissions)
    && session.permissions.includes(permission)
);


const hasClientProfile = (session) => (
    session.profiles?.cliente?.exists === true
);


const canUseAdministrativeTurnos = (session) => (
    session.businessRole === 'ADMINISTRADOR'
    && hasPermission(session, 'gestion.view_global_agenda')
);


const canUseAdministrativeOrders = (session) => (
    session.businessRole === 'ADMINISTRADOR'
    && (
        hasPermission(session, 'gestion.register_payment')
        || hasPermission(session, 'gestion.manage_stock')
    )
);


export const getNotificationDestination = (notification, session) => {
    const extra = notification.datos_extra || {};
    const fallback = getLandingPath(session) || '/login';
    let path = fallback;
    let state = { notificacionId: notification.id };

    if (extra.servicio_id && extra.fecha && hasClientProfile(session)) {
        path = CLIENTE_ROUTES.RESERVAR;
        state = {
            ...state,
            servicioPreseleccionado: extra.servicio_id,
            fechaSugerida: extra.fecha,
            horaSugerida: extra.hora || null,
            profesionalId: extra.profesional_id || null
        };
    } else if (extra.promo_id && hasClientProfile(session)) {
        path = CLIENTE_ROUTES.CATALOGO_PRODUCTOS;
        state = { ...state, promoId: extra.promo_id };
    } else if (extra.contexto === 'compra_exitosa' || extra.orden_id) {
        if (canUseAdministrativeOrders(session)) {
            path = ADMIN_ROUTES.ORDENES;
        } else if (hasClientProfile(session)) {
            path = CLIENTE_ROUTES.MIS_PEDIDOS;
        }
        state = { ...state, ordenId: extra.orden_id || null };
    } else if (extra.turno_id) {
        if (canUseAdministrativeTurnos(session)) {
            path = ADMIN_ROUTES.TURNOS;
        } else if (hasClientProfile(session)) {
            path = CLIENTE_ROUTES.MIS_TURNOS;
        } else if (['EMPLEADO', 'PROFESIONAL'].includes(session.businessRole)) {
            path = SESSION_ROUTES.OPERACIONES;
        }
        state = { ...state, turnoId: extra.turno_id };
    } else if (['alerta', 'recordatorio'].includes(notification.tipo)) {
        if (canUseAdministrativeTurnos(session)) {
            path = ADMIN_ROUTES.TURNOS;
        } else if (hasClientProfile(session)) {
            path = CLIENTE_ROUTES.MIS_TURNOS;
        }
    } else if (notification.tipo === 'diagnostico' && hasClientProfile(session)) {
        path = CLIENTE_ROUTES.PERFIL;
    } else if (notification.tipo === 'promocion' && hasClientProfile(session)) {
        path = CLIENTE_ROUTES.CATALOGO_PRODUCTOS;
    }

    return { path, state };
};
