import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState
} from 'react';
import axios from 'axios';

import { fetchCurrentSession } from '../api/sessionApi';


export const SESSION_STATUS = Object.freeze({
    LOADING: 'loading',
    AUTHENTICATED: 'authenticated',
    ANONYMOUS: 'anonymous',
    ERROR: 'error'
});


const emptyProfiles = () => ({
    cliente: {
        exists: false,
        id: null,
        active: null
    },
    personal: {
        exists: false,
        id: null,
        active: null,
        function_role: null
    }
});


const createEmptySession = (status, error = null) => ({
    status,
    user: null,
    businessRole: null,
    permissions: [],
    profiles: emptyProfiles(),
    error
});


const SessionContext = createContext(undefined);


export const SessionProvider = ({ children }) => {
    const [session, setSession] = useState(() => (
        createEmptySession(
            localStorage.getItem('access_token')
                ? SESSION_STATUS.LOADING
                : SESSION_STATUS.ANONYMOUS
        )
    ));
    const latestRequest = useRef(0);

    const clearStoredSession = useCallback(() => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_info');
        delete axios.defaults.headers.common.Authorization;
    }, []);

    const clearSession = useCallback(() => {
        latestRequest.current += 1;
        clearStoredSession();
        setSession(createEmptySession(SESSION_STATUS.ANONYMOUS));
    }, [clearStoredSession]);

    const refreshSession = useCallback(async () => {
        const accessToken = localStorage.getItem('access_token');
        const requestId = latestRequest.current + 1;
        latestRequest.current = requestId;

        if (!accessToken) {
            setSession(createEmptySession(SESSION_STATUS.ANONYMOUS));
            return null;
        }

        setSession(createEmptySession(SESSION_STATUS.LOADING));

        try {
            const response = await fetchCurrentSession(accessToken);
            if (latestRequest.current !== requestId) {
                return null;
            }

            const data = response.data;
            const nextSession = {
                status: SESSION_STATUS.AUTHENTICATED,
                user: data.user,
                businessRole: data.business_role,
                permissions: Array.isArray(data.permissions)
                    ? data.permissions
                    : [],
                profiles: data.profiles || emptyProfiles(),
                error: null
            };
            setSession(nextSession);
            return nextSession;
        } catch (requestError) {
            if (latestRequest.current !== requestId) {
                return null;
            }

            const status = requestError.response?.status;
            const backendError = requestError.response?.data?.error;

            if (status === 401) {
                clearStoredSession();
                setSession(createEmptySession(SESSION_STATUS.ANONYMOUS));
                return null;
            }

            const error = {
                code: backendError?.code || 'SESSION_CONTEXT_UNAVAILABLE',
                detail: backendError?.detail || 'No se pudo cargar el contexto de sesión.',
                httpStatus: status || null
            };
            setSession(createEmptySession(SESSION_STATUS.ERROR, error));
            return null;
        }
    }, [clearStoredSession]);

    useEffect(() => {
        refreshSession();
    }, [refreshSession]);

    const permissionSet = useMemo(
        () => new Set(session.permissions),
        [session.permissions]
    );

    const hasPermission = useCallback(
        (permission) => permissionSet.has(permission),
        [permissionSet]
    );

    const hasAnyPermission = useCallback(
        (permissions) => (
            Array.isArray(permissions)
            && permissions.some((permission) => permissionSet.has(permission))
        ),
        [permissionSet]
    );

    const hasRole = useCallback(
        (role) => session.businessRole === role,
        [session.businessRole]
    );

    const hasProfile = useCallback(
        (profileName) => session.profiles?.[profileName]?.exists === true,
        [session.profiles]
    );

    const value = useMemo(() => ({
        session,
        user: session.user,
        businessRole: session.businessRole,
        permissions: session.permissions,
        profiles: session.profiles,
        status: session.status,
        error: session.error,
        loading: session.status === SESSION_STATUS.LOADING,
        authenticated: session.status === SESSION_STATUS.AUTHENTICATED,
        anonymous: session.status === SESSION_STATUS.ANONYMOUS,
        refreshSession,
        clearSession,
        hasPermission,
        hasAnyPermission,
        hasRole,
        hasProfile
    }), [
        session,
        refreshSession,
        clearSession,
        hasPermission,
        hasAnyPermission,
        hasRole,
        hasProfile
    ]);

    return (
        <SessionContext.Provider value={value}>
            {children}
        </SessionContext.Provider>
    );
};


export const useSession = () => {
    const context = useContext(SessionContext);
    if (context === undefined) {
        throw new Error('useSession debe utilizarse dentro de SessionProvider.');
    }
    return context;
};


export default SessionContext;
