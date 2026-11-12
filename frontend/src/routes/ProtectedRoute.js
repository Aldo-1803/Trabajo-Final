import React from 'react';
import { Navigate } from 'react-router-dom';

import { SESSION_STATUS, useSession } from '../context/SessionContext';
import { AUTH_ROUTES, SESSION_ROUTES } from './routes';


const ProtectedRoute = ({
    children,
    requiredProfile,
    requiredActiveProfile,
    requiredPermission,
    requiredAnyPermission,
    requiredCapability,
    requiredAnyCapability,
    requiredAnyAccess,
    allowedRoles
}) => {
    const {
        status,
        loading,
        hasPermission,
        hasAnyPermission,
        hasCapability,
        hasAnyCapability,
        hasRole,
        hasProfile,
        hasActiveProfile
    } = useSession();

    if (loading || status === SESSION_STATUS.LOADING) {
        return (
            <div className="text-center mt-20" role="status">
                Cargando sesión...
            </div>
        );
    }

    if (status === SESSION_STATUS.ANONYMOUS) {
        return <Navigate to={AUTH_ROUTES.LOGIN} replace />;
    }

    if (status === SESSION_STATUS.ERROR) {
        return <Navigate to={SESSION_ROUTES.ERROR_ACCESO} replace />;
    }

    if (status !== SESSION_STATUS.AUTHENTICATED) {
        return <Navigate to={SESSION_ROUTES.ERROR_ACCESO} replace />;
    }

    if (requiredProfile && !hasProfile(requiredProfile)) {
        return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
    }

    if (requiredActiveProfile && !hasActiveProfile(requiredActiveProfile)) {
        return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
    }

    if (requiredPermission && !hasPermission(requiredPermission)) {
        return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
    }

    if (
        requiredAnyPermission
        && !hasAnyPermission(requiredAnyPermission)
    ) {
        return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
    }

    if (requiredCapability && !hasCapability(requiredCapability)) {
        return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
    }

    if (
        requiredAnyCapability
        && !hasAnyCapability(requiredAnyCapability)
    ) {
        return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
    }

    if (requiredAnyAccess) {
        const canUsePermission = (
            Array.isArray(requiredAnyAccess.permissions)
            && hasAnyPermission(requiredAnyAccess.permissions)
        );
        const canUseCapability = (
            Array.isArray(requiredAnyAccess.capabilities)
            && hasAnyCapability(requiredAnyAccess.capabilities)
        );

        if (!canUsePermission && !canUseCapability) {
            return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
        }
    }

    if (allowedRoles && !allowedRoles.some((role) => hasRole(role))) {
        return <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />;
    }

    return children;
};

export default ProtectedRoute;
