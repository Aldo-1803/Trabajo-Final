import axios from 'axios';

// Configurar la URL base de axios
axios.defaults.baseURL = 'http://127.0.0.1:8000';

// Interceptor de Request - Agregar token a cada petición
axios.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
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
            delete axios.defaults.headers.common['Authorization'];
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

export default axios;

