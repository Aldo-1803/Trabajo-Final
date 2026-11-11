import axios from 'axios';

import {
    emitHttpSessionEvent,
    HTTP_SESSION_EVENT
} from './httpSessionEvents';

// Configurar la URL base de axios
axios.defaults.baseURL = 'http://127.0.0.1:8000';
axios.defaults.withCredentials = false;

const getStoredToken = () => localStorage.getItem('access_token');

const PUBLIC_AUTH_PATHS = [
    '/api/usuarios/login/',
    '/api/usuarios/registro/',
    '/api/usuarios/recuperar-contrasena/',
    '/api/usuarios/resetear-clave/'
];


export const isPublicAuthRequest = (url = '') => (
    PUBLIC_AUTH_PATHS.some((path) => url.includes(path))
);

// Interceptor de Request - Agregar token a cada petición
axios.interceptors.request.use(
    (config) => {
        config.headers = config.headers || {};

        const token = getStoredToken();
        const publicAuthRequest = isPublicAuthRequest(config.url);
        if (token && !publicAuthRequest) {
            config.headers['Authorization'] = `Bearer ${token}`;
        } else {
            delete config.headers['Authorization'];
        }
        config.__sessionAccessToken = publicAuthRequest ? null : token;
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// El contexto React decide cómo actualizar la sesión; no se reenvían requests.
axios.interceptors.response.use(
    (response) => response,
    (error) => {
        const status = error.response?.status;
        const accessToken = error.config?.__sessionAccessToken;

        if (status === 401 && accessToken) {
            emitHttpSessionEvent({
                type: HTTP_SESSION_EVENT.UNAUTHORIZED,
                accessToken
            });
        } else if (status === 403 && accessToken) {
            emitHttpSessionEvent({
                type: HTTP_SESSION_EVENT.FORBIDDEN,
                accessToken
            });
        }
        return Promise.reject(error);
    }
);

export default axios;

