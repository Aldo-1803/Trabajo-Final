import React from 'react';

import { CONTENT_MANAGEMENT_CAPABILITIES } from '../utils/accessRules';
import ProtectedRoute from './ProtectedRoute';


const ContentManagementRoute = ({ children }) => {
    return (
        <ProtectedRoute
            requiredAnyCapability={CONTENT_MANAGEMENT_CAPABILITIES}
        >
            {children}
        </ProtectedRoute>
    );
};


export default ContentManagementRoute;
