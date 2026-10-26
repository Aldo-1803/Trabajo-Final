import {
    ADMIN_ROUTES,
    CLIENTE_ROUTES,
    SESSION_ROUTES
} from '../routes/routes';


export const NAVIGATION_PLACEMENT = Object.freeze({
    PRIMARY: 'primary',
    ACCOUNT: 'account',
    ACTION: 'action'
});


export const navigationItems = [
    {
        id: 'operations',
        label: 'Operaciones',
        path: SESSION_ROUTES.OPERACIONES,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        anyPermissions: [
            'gestion.view_global_agenda',
            'usuarios.create_walkin_client',
            'gestion.create_turno_for_client'
        ]
    },
    {
        id: 'technical-review',
        label: 'Revisión técnica',
        path: SESSION_ROUTES.REVISION_TECNICA,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'gestion.review_technical_booking',
        requiredActiveProfile: 'personal'
    },
    {
        id: 'client-turnos',
        label: 'Mis Turnos',
        path: CLIENTE_ROUTES.MIS_TURNOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-pedidos',
        label: 'Mis Pedidos',
        path: CLIENTE_ROUTES.MIS_PEDIDOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-reservar',
        label: 'Reservar',
        path: CLIENTE_ROUTES.RESERVAR,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-technical-requests',
        label: 'Solicitudes técnicas',
        path: CLIENTE_ROUTES.SOLICITUDES_TECNICAS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-routines',
        label: 'Rutinas',
        path: CLIENTE_ROUTES.CATALOGO_RUTINAS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-services',
        label: 'Servicios',
        path: CLIENTE_ROUTES.CATALOGO_SERVICIOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-profile',
        label: 'Mi Perfil',
        path: CLIENTE_ROUTES.PERFIL,
        placement: NAVIGATION_PLACEMENT.ACCOUNT,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-agenda',
        label: 'Mi Agenda',
        path: CLIENTE_ROUTES.MI_AGENDA,
        placement: NAVIGATION_PLACEMENT.ACCOUNT,
        requiredProfile: 'cliente'
    },
    {
        id: 'client-cart',
        label: 'Carrito',
        path: CLIENTE_ROUTES.CARRITO,
        placement: NAVIGATION_PLACEMENT.ACTION,
        requiredProfile: 'cliente'
    },
    {
        id: 'admin-dashboard',
        label: 'Dashboard',
        path: ADMIN_ROUTES.DASHBOARD,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        allowedRoles: ['ADMINISTRADOR']
    },
    {
        id: 'admin-users',
        label: 'Usuarios',
        path: ADMIN_ROUTES.USUARIOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        allowedRoles: ['ADMINISTRADOR'],
        requiredPermission: 'usuarios.manage_users'
    },
    {
        id: 'admin-personal',
        label: 'Personal',
        path: ADMIN_ROUTES.PERSONAL,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        allowedRoles: ['ADMINISTRADOR'],
        requiredPermission: 'gestion.manage_personal'
    },
    {
        id: 'clients-management',
        label: 'Clientes',
        path: ADMIN_ROUTES.CLIENTES,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'usuarios.view_clients'
    },
    {
        id: 'admin-products',
        label: 'Productos',
        path: ADMIN_ROUTES.PRODUCTOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        allowedRoles: ['ADMINISTRADOR'],
        anyPermissions: [
            'gestion.view_stock',
            'gestion.manage_products'
        ]
    },
    {
        id: 'admin-reports',
        label: 'Reportes',
        path: ADMIN_ROUTES.REPORTES,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        allowedRoles: ['ADMINISTRADOR'],
        anyPermissions: [
            'gestion.view_reports',
            'gestion.view_financial_reports'
        ]
    },
    {
        id: 'admin-audit',
        label: 'Auditoría',
        path: ADMIN_ROUTES.AUDITORIA,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        allowedRoles: ['ADMINISTRADOR'],
        requiredPermission: 'gestion.view_audit'
    },
    {
        id: 'admin-configuration',
        label: 'Configuración',
        path: ADMIN_ROUTES.CONFIGURACION,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        allowedRoles: ['ADMINISTRADOR'],
        requiredPermission: 'gestion.manage_configuration'
    }
];


export const isNavigationItemVisible = (item, access) => {
    if (!access.authenticated || access.loading || access.error) {
        return false;
    }

    if (
        item.allowedRoles
        && !item.allowedRoles.includes(access.businessRole)
    ) {
        return false;
    }

    if (
        item.requiredProfile
        && !access.hasProfile(item.requiredProfile)
    ) {
        return false;
    }

    if (
        item.requiredActiveProfile
        && !access.hasActiveProfile?.(item.requiredActiveProfile)
    ) {
        return false;
    }

    if (
        item.requiredPermission
        && !access.hasPermission(item.requiredPermission)
    ) {
        return false;
    }

    if (
        item.anyPermissions
        && !access.hasAnyPermission(item.anyPermissions)
    ) {
        return false;
    }

    return true;
};


export const getVisibleNavigationItems = (access, placement) => (
    navigationItems.filter((item) => (
        item.placement === placement
        && isNavigationItemVisible(item, access)
    ))
);
