import React from 'react';
import { Navigate } from 'react-router-dom';

import { useSession } from '../context/SessionContext';
import ProtectedRoute from './ProtectedRoute';
import { SESSION_ROUTES } from './routes';


const ContentManagementRoute = ({ children }) => {
    const { hasPermission, hasActiveProfile } = useSession();
    const canManageContent = (
        hasPermission('gestion.manage_content')
        || hasActiveProfile('personal')
    );

    return (
        <ProtectedRoute>
            {canManageContent
                ? children
                : <Navigate to={SESSION_ROUTES.ACCESO_DENEGADO} replace />}
        </ProtectedRoute>
    );
};


export default ContentManagementRoute;
