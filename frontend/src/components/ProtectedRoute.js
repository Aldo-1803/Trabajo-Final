import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import axios from 'axios';

const ProtectedRoute = ({ children }) => {
    const [isAuthenticated, setIsAuthenticated] = useState(null);
    const token = localStorage.getItem('access_token');

    useEffect(() => {
        const verifyToken = async () => {
            if (!token) {
                setIsAuthenticated(false);
                return;
            }

            try {
                // Verificar si el token es válido haciendo una petición al endpoint de perfil
                await axios.get('http://127.0.0.1:8000/api/usuarios/perfil/', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                setIsAuthenticated(true);
            } catch (error) {
                // Token inválido o expirado
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                delete axios.defaults.headers.common['Authorization'];
                setIsAuthenticated(false);
            }
        };

        verifyToken();
    }, [token]);

    // Mientras verifica la autenticación, mostrar loading
    if (isAuthenticated === null) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-lg text-gray-600">Verificando sesión...</div>
            </div>
        );
    }

    // Si no está autenticado, redirigir al login
    if (!isAuthenticated) {
        return <Navigate to="/login" />;
    }

    return children;
};

export default ProtectedRoute;