import React from 'react';
import ReactDOM from 'react-dom/client'; // <-- Faltaba esta importación
import './index.css';
import App from './App'; // <-- Faltaba esta importación
import reportWebVitals from './reportWebVitals'; // <-- Faltaba esta importación
import { BrowserRouter } from 'react-router-dom'; // <-- Esto va aquí
import axios from 'axios'; // <-- Faltaba esta importación

// --- Configuración Global de Axios ---
axios.defaults.baseURL = 'http://127.0.0.1:8000';
const token = localStorage.getItem('access_token');

if (token) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
}

axios.interceptors.response.use(
    // 1. Si la respuesta es exitosa (ej. 200 OK), simplemente la dejamos pasar.
    (response) => response,
    
    // 2. Si la respuesta falla (ej. 401 Unauthorized)...
    async (error) => {
        const originalRequest = error.config;

        // Verificamos si es el error 401, si el token está vencido,
        // y si no es un reintento (para evitar bucles infinitos).
        if (error.response.status === 401 && 
            error.response.data.code === 'token_not_valid' && 
            !originalRequest._retry) {
            
            originalRequest._retry = true; // Marcamos esta petición como un reintento.

            const refreshToken = localStorage.getItem('refresh_token');

            if (refreshToken) {
                try {
                    // 3. Intentamos obtener un nuevo token de acceso usando el token de refresco.
                    const response = await axios.post('/api/token/refresh/', {
                        refresh: refreshToken
                    });

                    // 4. Si tenemos éxito:
                    const newAccessToken = response.data.access;
                    
                    // 4a. Actualizamos el localStorage
                    localStorage.setItem('access_token', newAccessToken);
                    
                    // 4b. Actualizamos la cabecera por defecto de axios
                    axios.defaults.headers.common['Authorization'] = `Bearer ${newAccessToken}`;
                    
                    // 4c. Actualizamos la cabecera de la petición original que falló
                    originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`;
                    
                    // 4d. Reintentamos la petición original (ej. GET /perfil)
                    return axios(originalRequest);

                } catch (refreshError) {
                    // 5. Si el refresh token también falla (ej. está vencido o es inválido):
                    console.error("Fallo al refrescar el token:", refreshError);
                    
                    // 5a. Borramos todo
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    axios.defaults.headers.common['Authorization'] = null;
                    
                    // 5b. Enviamos al usuario a la pantalla de login.
                    window.location.href = '/login'; 
                    return Promise.reject(refreshError);
                }
            } else {
                // No hay refresh token, redirigir a login
                window.location.href = '/login';
            }
        }

        // 6. Para cualquier otro error, simplemente lo devolvemos.
        return Promise.reject(error);
    }
);

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <React.StrictMode>
        {/* El <BrowserRouter> envuelve a <App> aquí, una sola vez */}
        <BrowserRouter>
            <App />
        </BrowserRouter>
    </React.StrictMode>
);

reportWebVitals();