import {
    ADMIN_ROUTES,
    AUTH_ROUTES,
    CLIENTE_ROUTES,
    SESSION_ROUTES
} from '../routes/routes';


export const getLandingPath = (session) => {
    if (!session || session.status === 'loading') {
        return null;
    }

    if (session.status === 'error' || session.error) {
        return SESSION_ROUTES.ERROR_ACCESO;
    }

    if (session.status === 'anonymous') {
        return AUTH_ROUTES.LOGIN;
    }

    switch (session.businessRole) {
        case 'CLIENTE':
            return CLIENTE_ROUTES.PERFIL;
        case 'EMPLEADO':
        case 'PROFESIONAL':
            return SESSION_ROUTES.OPERACIONES;
        case 'ADMINISTRADOR':
            return ADMIN_ROUTES.DASHBOARD;
        case null:
        case undefined:
            return SESSION_ROUTES.CUENTA_SIN_ACCESO;
        default:
            return SESSION_ROUTES.ERROR_ACCESO;
    }
};
