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

import {
    HTTP_SESSION_EVENT,
    subscribeToHttpSessionEvents
} from '../api/httpSessionEvents';
import { fetchCurrentSession } from '../api/sessionApi';
import { classifyHttpError } from '../utils/httpErrors';


export const SESSION_REFRESH_INTERVAL_MS = 45 * 1000;


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


const normalizeCapabilities = (capabilities) => {
    if (
        capabilities === null
        || typeof capabilities !== 'object'
        || Array.isArray(capabilities)
    ) {
        return {};
    }
    return Object.fromEntries(
        Object.entries(capabilities).map(([name, value]) => [
            name,
            value === true
        ])
    );
};


const createEmptySession = (status, error = null) => ({
    status,
    user: null,
    businessRole: null,
    permissions: [],
    capabilities: {},
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
    const [refreshError, setRefreshError] = useState(null);
    const [sessionNotice, setSessionNotice] = useState(null);
    const sessionRef = useRef(session);
    const requestGeneration = useRef(0);
    const inFlightRefresh = useRef(null);
    const lastSuccessfulRefresh = useRef(0);

    const updateSession = useCallback((nextSession) => {
        sessionRef.current = nextSession;
        setSession(nextSession);
    }, []);

    const clearStoredSession = useCallback(() => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_info');
        delete axios.defaults.headers.common.Authorization;
    }, []);

    const clearSession = useCallback(() => {
        requestGeneration.current += 1;
        inFlightRefresh.current = null;
        lastSuccessfulRefresh.current = 0;
        clearStoredSession();
        setRefreshError(null);
        setSessionNotice(null);
        updateSession(createEmptySession(SESSION_STATUS.ANONYMOUS));
    }, [clearStoredSession, updateSession]);

    const expireSession = useCallback(() => {
        requestGeneration.current += 1;
        inFlightRefresh.current = null;
        lastSuccessfulRefresh.current = 0;
        clearStoredSession();
        setRefreshError(null);
        setSessionNotice('Tu sesión finalizó. Ingresá nuevamente.');
        updateSession(createEmptySession(SESSION_STATUS.ANONYMOUS));
    }, [clearStoredSession, updateSession]);

    const refreshSession = useCallback((options = {}) => {
        const accessToken = localStorage.getItem('access_token');

        if (!accessToken) {
            const anonymousSession = createEmptySession(
                SESSION_STATUS.ANONYMOUS
            );
            updateSession(anonymousSession);
            return Promise.resolve(anonymousSession);
        }

        if (inFlightRefresh.current?.accessToken === accessToken) {
            return inFlightRefresh.current.promise;
        }

        const currentSession = sessionRef.current;
        const silent = options.silent === true || (
            options.silent !== false
            && currentSession.status === SESSION_STATUS.AUTHENTICATED
        );
        const expectedUserId = currentSession.user?.id ?? null;
        const generation = requestGeneration.current + 1;
        requestGeneration.current = generation;

        if (!silent) {
            updateSession(createEmptySession(SESSION_STATUS.LOADING));
        }
        setRefreshError(null);

        const promise = (async () => {
            try {
                const response = await fetchCurrentSession(accessToken);
                if (
                    requestGeneration.current !== generation
                    || localStorage.getItem('access_token') !== accessToken
                    || (
                        expectedUserId !== null
                        && sessionRef.current.user?.id !== expectedUserId
                    )
                ) {
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
                    capabilities: normalizeCapabilities(data.capabilities),
                    profiles: data.profiles || emptyProfiles(),
                    error: null
                };
                lastSuccessfulRefresh.current = Date.now();
                setSessionNotice(null);
                setRefreshError(null);
                updateSession(nextSession);
                return nextSession;
            } catch (requestError) {
                if (
                    requestGeneration.current !== generation
                    || localStorage.getItem('access_token') !== accessToken
                ) {
                    return null;
                }

                const status = requestError.response?.status;
                const backendError = requestError.response?.data?.error;

                if (status === 401) {
                    expireSession();
                    return createEmptySession(SESSION_STATUS.ANONYMOUS);
                }

                const classified = classifyHttpError(requestError);
                const error = {
                    code: backendError?.code || 'SESSION_CONTEXT_UNAVAILABLE',
                    detail: backendError?.detail || 'No se pudo cargar el contexto de sesión.',
                    httpStatus: status || null,
                    kind: classified.kind,
                    retryable: classified.retryable
                };

                if (silent && sessionRef.current.status === SESSION_STATUS.AUTHENTICATED) {
                    setRefreshError(error);
                    return { ...sessionRef.current, refreshError: error };
                }

                const errorSession = createEmptySession(
                    SESSION_STATUS.ERROR,
                    error
                );
                updateSession(errorSession);
                return errorSession;
            } finally {
                if (inFlightRefresh.current?.generation === generation) {
                    inFlightRefresh.current = null;
                }
            }
        })();

        inFlightRefresh.current = { accessToken, generation, promise };
        return promise;
    }, [expireSession, updateSession]);

    useEffect(() => {
        refreshSession();
    }, [refreshSession]);

    useEffect(() => {
        const refreshIfStale = () => {
            if (
                sessionRef.current.status !== SESSION_STATUS.AUTHENTICATED
                || !localStorage.getItem('access_token')
                || Date.now() - lastSuccessfulRefresh.current
                    < SESSION_REFRESH_INTERVAL_MS
            ) {
                return;
            }
            refreshSession({ silent: true });
        };
        const handleVisibility = () => {
            if (document.visibilityState === 'visible') refreshIfStale();
        };
        const unsubscribe = subscribeToHttpSessionEvents((event) => {
            if (
                !event?.accessToken
                || event.accessToken !== localStorage.getItem('access_token')
            ) {
                return;
            }
            if (event.type === HTTP_SESSION_EVENT.UNAUTHORIZED) {
                expireSession();
            } else if (
                event.type === HTTP_SESSION_EVENT.FORBIDDEN
                && sessionRef.current.status === SESSION_STATUS.AUTHENTICATED
            ) {
                refreshSession({ silent: true });
            }
        });

        window.addEventListener('focus', refreshIfStale);
        document.addEventListener('visibilitychange', handleVisibility);
        return () => {
            unsubscribe();
            window.removeEventListener('focus', refreshIfStale);
            document.removeEventListener('visibilitychange', handleVisibility);
        };
    }, [expireSession, refreshSession]);

    useEffect(() => () => {
        requestGeneration.current += 1;
        inFlightRefresh.current = null;
    }, []);

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

    const hasCapability = useCallback(
        (capability) => session.capabilities?.[capability] === true,
        [session.capabilities]
    );

    const hasAnyCapability = useCallback(
        (capabilities) => (
            Array.isArray(capabilities)
            && capabilities.some(
                (capability) => session.capabilities?.[capability] === true
            )
        ),
        [session.capabilities]
    );

    const hasRole = useCallback(
        (role) => session.businessRole === role,
        [session.businessRole]
    );

    const hasProfile = useCallback(
        (profileName) => session.profiles?.[profileName]?.exists === true,
        [session.profiles]
    );

    const hasActiveProfile = useCallback(
        (profileName) => (
            session.profiles?.[profileName]?.exists === true
            && session.profiles?.[profileName]?.active === true
        ),
        [session.profiles]
    );

    const value = useMemo(() => ({
        session,
        user: session.user,
        businessRole: session.businessRole,
        permissions: session.permissions,
        capabilities: session.capabilities,
        profiles: session.profiles,
        status: session.status,
        error: session.error,
        refreshError,
        sessionNotice,
        loading: session.status === SESSION_STATUS.LOADING,
        authenticated: session.status === SESSION_STATUS.AUTHENTICATED,
        anonymous: session.status === SESSION_STATUS.ANONYMOUS,
        refreshSession,
        clearSession,
        hasPermission,
        hasAnyPermission,
        hasCapability,
        hasAnyCapability,
        hasRole,
        hasProfile,
        hasActiveProfile
    }), [
        session,
        refreshError,
        sessionNotice,
        refreshSession,
        clearSession,
        hasPermission,
        hasAnyPermission,
        hasCapability,
        hasAnyCapability,
        hasRole,
        hasProfile,
        hasActiveProfile
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
