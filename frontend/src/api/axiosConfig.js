import axios from 'axios';

// Configurar la URL base de axios
axios.defaults.baseURL = 'http://127.0.0.1:8000';
axios.defaults.withCredentials = false;

const getStoredToken = () => localStorage.getItem('access_token');

// Interceptor de Request - Agregar token a cada petición
axios.interceptors.request.use(
    (config) => {
        config.headers = config.headers || {};

        const token = getStoredToken();
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        } else {
            delete config.headers['Authorization'];
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Interceptor de Response - Solo manejar errores críticos
axios.interceptors.response.use(
    (response) => response,
    (error) => {
        // Si es 401, limpiar y redirigir al login
        if (error.response && error.response.status === 401) {
            console.error('Token no válido, redirigiendo al login...');
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user_info');
            delete axios.defaults.headers.common['Authorization'];
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

export default axios;

