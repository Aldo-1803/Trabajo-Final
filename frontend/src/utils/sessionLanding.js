import {
    ADMIN_ROUTES,
    AUTH_ROUTES,
    CLIENTE_ROUTES,
    SESSION_ROUTES
} from '../routes/routes';
import {
    CASH_PERMISSIONS,
    CONTENT_MANAGEMENT_CAPABILITIES,
    OPERATIONS_PERMISSIONS,
    PERSONAL_MANAGEMENT_PERMISSIONS,
    PRODUCT_PERMISSIONS,
    REPORT_PERMISSIONS,
    SERVICE_ACCESS,
    sessionHasActiveProfile,
    sessionHasAnyAccess,
    sessionHasAnyCapability,
    sessionHasAnyPermission,
    sessionHasCapability,
    sessionHasPermission,
    sessionHasProfile
} from './accessRules';


const DESTINATIONS = Object.freeze({
    client: {
        path: CLIENTE_ROUTES.PERFIL,
        allowed: (session) => sessionHasProfile(session, 'cliente')
    },
    dashboard: {
        path: ADMIN_ROUTES.DASHBOARD,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.view_reports'
        )
    },
    operations: {
        path: SESSION_ROUTES.OPERACIONES,
        allowed: (session) => sessionHasAnyPermission(
            session,
            OPERATIONS_PERMISSIONS
        )
    },
    workAgenda: {
        path: SESSION_ROUTES.MI_AGENDA_LABORAL,
        allowed: (session) => sessionHasActiveProfile(session, 'personal')
    },
    technicalReview: {
        path: SESSION_ROUTES.REVISION_TECNICA,
        allowed: (session) => sessionHasCapability(
            session,
            'technical_booking.review'
        )
    },
    reports: {
        path: ADMIN_ROUTES.REPORTES,
        allowed: (session) => sessionHasAnyPermission(
            session,
            REPORT_PERMISSIONS
        )
    },
    turnos: {
        path: ADMIN_ROUTES.TURNOS,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.view_global_agenda'
        )
    },
    newTurno: {
        path: ADMIN_ROUTES.NUEVO_TURNO,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.create_turno_for_client'
        )
    },
    routines: {
        path: ADMIN_ROUTES.GESTIONAR_RUTINAS,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.assign_routines'
        )
    },
    services: {
        path: ADMIN_ROUTES.SERVICIOS,
        allowed: (session) => sessionHasAnyAccess(session, SERVICE_ACCESS)
    },
    products: {
        path: ADMIN_ROUTES.PRODUCTOS,
        allowed: (session) => sessionHasAnyPermission(
            session,
            PRODUCT_PERMISSIONS
        )
    },
    users: {
        path: ADMIN_ROUTES.USUARIOS,
        allowed: (session) => sessionHasPermission(
            session,
            'usuarios.manage_users'
        )
    },
    clients: {
        path: ADMIN_ROUTES.CLIENTES,
        allowed: (session) => sessionHasPermission(
            session,
            'usuarios.view_clients'
        )
    },
    newClient: {
        path: ADMIN_ROUTES.NUEVO_CLIENTE,
        allowed: (session) => sessionHasPermission(
            session,
            'usuarios.create_walkin_client'
        )
    },
    personal: {
        path: ADMIN_ROUTES.PERSONAL,
        allowed: (session) => sessionHasAnyPermission(
            session,
            PERSONAL_MANAGEMENT_PERMISSIONS
        )
    },
    agenda: {
        path: ADMIN_ROUTES.AGENDA,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.view_global_agenda'
        )
    },
    configuration: {
        path: ADMIN_ROUTES.CONFIGURACION,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.manage_configuration'
        )
    },
    content: {
        path: ADMIN_ROUTES.CONTENIDO_EDUCATIVO,
        allowed: (session) => sessionHasAnyCapability(
            session,
            CONTENT_MANAGEMENT_CAPABILITIES
        )
    },
    orders: {
        path: ADMIN_ROUTES.ORDENES,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.manage_stock'
        )
    },
    cash: {
        path: ADMIN_ROUTES.CAJA,
        allowed: (session) => sessionHasAnyPermission(
            session,
            CASH_PERMISSIONS
        )
    },
    financialIncidents: {
        path: ADMIN_ROUTES.INCIDENCIAS_FINANCIERAS,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.reconcile_external_payment'
        )
    },
    audit: {
        path: ADMIN_ROUTES.AUDITORIA,
        allowed: (session) => sessionHasPermission(
            session,
            'gestion.view_audit'
        )
    }
});


const ADMIN_PRIORITY = Object.freeze([
    'dashboard',
    'operations',
    'reports',
    'turnos',
    'newTurno',
    'clients',
    'newClient',
    'users',
    'personal',
    'products',
    'orders',
    'cash',
    'financialIncidents',
    'routines',
    'services',
    'content',
    'agenda',
    'configuration',
    'audit',
    'technicalReview',
    'workAgenda',
    'client'
]);

const STAFF_PRIORITY = Object.freeze([
    'operations',
    'workAgenda',
    'technicalReview',
    ...ADMIN_PRIORITY.filter((name) => ![
        'operations',
        'workAgenda',
        'technicalReview',
        'client'
    ].includes(name)),
    'client'
]);

const CLIENT_PRIORITY = Object.freeze([
    'client',
    ...STAFF_PRIORITY.filter((name) => name !== 'client')
]);

const DEFAULT_PRIORITY = Object.freeze([
    ...STAFF_PRIORITY
]);


const priorityFor = (businessRole) => {
    if (businessRole === 'CLIENTE') return CLIENT_PRIORITY;
    if (businessRole === 'ADMINISTRADOR') return ADMIN_PRIORITY;
    if (['EMPLEADO', 'PROFESIONAL'].includes(businessRole)) {
        return STAFF_PRIORITY;
    }
    return DEFAULT_PRIORITY;
};


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

    if (session.status !== 'authenticated') {
        return SESSION_ROUTES.ERROR_ACCESO;
    }

    const destinationName = priorityFor(session.businessRole).find(
        (name) => DESTINATIONS[name].allowed(session)
    );

    return destinationName
        ? DESTINATIONS[destinationName].path
        : SESSION_ROUTES.CUENTA_SIN_ACCESO;
};
