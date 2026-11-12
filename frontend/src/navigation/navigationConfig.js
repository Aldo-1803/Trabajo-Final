import {
    ADMIN_ROUTES,
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
    SERVICE_ACCESS
} from '../utils/accessRules';


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
        anyPermissions: OPERATIONS_PERMISSIONS
    },
    {
        id: 'in-person-payments',
        label: 'Caja presencial',
        path: ADMIN_ROUTES.CAJA,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        anyPermissions: CASH_PERMISSIONS
    },
    {
        id: 'financial-incidents',
        label: 'Incidencias financieras',
        path: ADMIN_ROUTES.INCIDENCIAS_FINANCIERAS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'gestion.reconcile_external_payment'
    },
    {
        id: 'work-agenda',
        label: 'Mi agenda laboral',
        path: SESSION_ROUTES.MI_AGENDA_LABORAL,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredActiveProfile: 'personal'
    },
    {
        id: 'technical-review',
        label: 'Revisión técnica',
        path: SESSION_ROUTES.REVISION_TECNICA,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredCapability: 'technical_booking.review'
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
        requiredPermission: 'gestion.view_reports'
    },
    {
        id: 'admin-users',
        label: 'Usuarios',
        path: ADMIN_ROUTES.USUARIOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'usuarios.manage_users'
    },
    {
        id: 'admin-personal',
        label: 'Personal',
        path: ADMIN_ROUTES.PERSONAL,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        anyPermissions: PERSONAL_MANAGEMENT_PERMISSIONS
    },
    {
        id: 'clients-management',
        label: 'Clientes',
        path: ADMIN_ROUTES.CLIENTES,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'usuarios.view_clients'
    },
    {
        id: 'client-create',
        label: 'Nuevo cliente',
        path: ADMIN_ROUTES.NUEVO_CLIENTE,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'usuarios.create_walkin_client'
    },
    {
        id: 'admin-products',
        label: 'Productos',
        path: ADMIN_ROUTES.PRODUCTOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        anyPermissions: PRODUCT_PERMISSIONS
    },
    {
        id: 'admin-orders',
        label: 'Órdenes',
        path: ADMIN_ROUTES.ORDENES,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'gestion.manage_stock'
    },
    {
        id: 'admin-reports',
        label: 'Reportes',
        path: ADMIN_ROUTES.REPORTES,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        anyPermissions: REPORT_PERMISSIONS
    },
    {
        id: 'admin-audit',
        label: 'Auditoría',
        path: ADMIN_ROUTES.AUDITORIA,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'gestion.view_audit'
    },
    {
        id: 'admin-agenda',
        label: 'Agenda',
        path: ADMIN_ROUTES.AGENDA,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'gestion.view_global_agenda'
    },
    {
        id: 'admin-routines',
        label: 'Gestionar rutinas',
        path: ADMIN_ROUTES.GESTIONAR_RUTINAS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        requiredPermission: 'gestion.assign_routines'
    },
    {
        id: 'admin-services',
        label: 'Gestionar servicios',
        path: ADMIN_ROUTES.SERVICIOS,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        anyAccess: SERVICE_ACCESS
    },
    {
        id: 'admin-content',
        label: 'Contenido educativo',
        path: ADMIN_ROUTES.CONTENIDO_EDUCATIVO,
        placement: NAVIGATION_PLACEMENT.PRIMARY,
        anyCapabilities: CONTENT_MANAGEMENT_CAPABILITIES
    },
    {
        id: 'admin-equipment',
        label: 'Equipamiento',
        path: ADMIN_ROUTES.EQUIPAMIENTO,
        placement: NAVIGATION_PLACEMENT.ACCOUNT,
        requiredPermission: 'gestion.manage_configuration'
    },
    {
        id: 'admin-rules',
        label: 'Reglas',
        path: ADMIN_ROUTES.REGLAS,
        placement: NAVIGATION_PLACEMENT.ACCOUNT,
        requiredPermission: 'gestion.manage_configuration'
    },
    {
        id: 'admin-configuration',
        label: 'Configuración',
        path: ADMIN_ROUTES.CONFIGURACION,
        placement: NAVIGATION_PLACEMENT.ACCOUNT,
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

    if (
        item.requiredCapability
        && !access.hasCapability?.(item.requiredCapability)
    ) {
        return false;
    }

    if (
        item.anyCapabilities
        && !access.hasAnyCapability?.(item.anyCapabilities)
    ) {
        return false;
    }

    if (item.anyAccess) {
        const canUsePermission = (
            Array.isArray(item.anyAccess.permissions)
            && access.hasAnyPermission(item.anyAccess.permissions)
        );
        const canUseCapability = (
            Array.isArray(item.anyAccess.capabilities)
            && access.hasAnyCapability?.(item.anyAccess.capabilities)
        );

        if (!canUsePermission && !canUseCapability) {
            return false;
        }
    }

    return true;
};


export const getVisibleNavigationItems = (access, placement) => (
    navigationItems.filter((item) => (
        item.placement === placement
        && isNavigationItemVisible(item, access)
    ))
);
