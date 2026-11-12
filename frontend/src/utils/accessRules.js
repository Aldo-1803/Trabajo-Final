export const OPERATIONS_PERMISSIONS = Object.freeze([
    'gestion.view_global_agenda',
    'usuarios.create_walkin_client',
    'gestion.create_turno_for_client',
    'gestion.register_arrival',
    'gestion.reprogram_any_turno',
    'gestion.cancel_any_turno',
    'gestion.register_payment',
    'gestion.confirm_deposit',
    'gestion.view_financial_reports'
]);

export const CASH_PERMISSIONS = Object.freeze([
    'gestion.register_payment',
    'gestion.confirm_deposit',
    'gestion.view_financial_reports'
]);

export const REPORT_PERMISSIONS = Object.freeze([
    'gestion.view_reports',
    'gestion.view_financial_reports'
]);

export const PRODUCT_PERMISSIONS = Object.freeze([
    'gestion.view_stock',
    'gestion.manage_stock',
    'gestion.manage_products',
    'gestion.manage_prices',
    'gestion.manage_promotions'
]);

export const PERSONAL_MANAGEMENT_PERMISSIONS = Object.freeze([
    'gestion.manage_personal',
    'gestion.manage_skills'
]);

export const CONTENT_MANAGEMENT_CAPABILITIES = Object.freeze([
    'content.author',
    'content.manage_global'
]);

export const SERVICE_ACCESS = Object.freeze({
    permissions: Object.freeze(['gestion.manage_prices']),
    capabilities: Object.freeze(['service_formula.manage'])
});


export const sessionHasPermission = (session, permission) => (
    Array.isArray(session?.permissions)
    && session.permissions.includes(permission)
);


export const sessionHasAnyPermission = (session, permissions) => (
    Array.isArray(permissions)
    && permissions.some((permission) => (
        sessionHasPermission(session, permission)
    ))
);


export const sessionHasCapability = (session, capability) => (
    session?.capabilities?.[capability] === true
);


export const sessionHasAnyCapability = (session, capabilities) => (
    Array.isArray(capabilities)
    && capabilities.some((capability) => (
        sessionHasCapability(session, capability)
    ))
);


export const sessionHasProfile = (session, profile) => (
    session?.profiles?.[profile]?.exists === true
);


export const sessionHasActiveProfile = (session, profile) => (
    sessionHasProfile(session, profile)
    && session?.profiles?.[profile]?.active === true
);


export const sessionHasAnyAccess = (session, access) => {
    if (!access || typeof access !== 'object') {
        return false;
    }

    return (
        sessionHasAnyPermission(session, access.permissions)
        || sessionHasAnyCapability(session, access.capabilities)
    );
};
