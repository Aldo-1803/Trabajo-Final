// frontend/src/components/Perfil.js
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const DiagnosticoCard = ({ diagnostico, loading }) => {
    if (loading) {
        return (
            <div className="bg-white rounded-2xl p-8 shadow-lg">
                <div className="animate-pulse">
                    <div className="h-8 bg-amber-200 rounded w-3/4 mb-4"></div>
                    <div className="space-y-3">
                        <div className="h-4 bg-amber-100 rounded w-full"></div>
                        <div className="h-4 bg-amber-100 rounded w-5/6"></div>
                    </div>
                </div>
            </div>
        );
    }

    if (!diagnostico) {
        return (
            <div className="bg-white rounded-2xl p-8 shadow-lg border-2 border-amber-200">
                <p className="text-center text-amber-900">No hay datos de diagnóstico disponibles</p>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-2xl p-8 shadow-lg border-l-4" style={{ borderColor: '#7a5c3c' }}>
            <h2 className="text-2xl font-bold mb-6" style={{ color: '#7a5c3c' }}>💇 Tu Diagnóstico</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                    <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Tipo de Cabello</p>
                    <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                        {diagnostico.tipo_cabello?.nombre || 'No especificado'}
                    </p>
                </div>
                
                <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                    <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Grosor</p>
                    <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                        {diagnostico.grosor_cabello?.nombre || 'No especificado'}
                    </p>
                </div>

                <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                    <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Porosidad</p>
                    <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                        {diagnostico.porosidad_cabello?.nombre || 'No especificado'}
                    </p>
                </div>

                <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                    <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Cuero Cabelludo</p>
                    <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                        {diagnostico.cuero_cabelludo?.nombre || 'No especificado'}
                    </p>
                </div>

                <div className="p-4 rounded-lg col-span-1 md:col-span-2" style={{ backgroundColor: '#f5e1ce' }}>
                    <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Estado General</p>
                    <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                        {diagnostico.estado_general?.nombre || 'No especificado'}
                    </p>
                </div>
            </div>
        </div>
    );
};

const Perfil = () => {
    const [usuario, setUsuario] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        const fetchPerfil = async () => {
            try {
                setLoading(true);
                const token = localStorage.getItem('access_token');
                
                if (!token) {
                    navigate('/login');
                    return;
                }

                const response = await axios.get('/api/usuarios/perfil/', {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });

                setUsuario(response.data);
            } catch (err) {
                console.error('Error al cargar perfil:', err);
                setError('Error al cargar tu perfil');
                if (err.response?.status === 401) {
                    navigate('/login');
                }
            } finally {
                setLoading(false);
            }
        };

        fetchPerfil();
    }, [navigate]);

    const logout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        axios.defaults.headers.common['Authorization'] = null;
        navigate('/login');
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #e8c39e 0%, #ffffff 100%)' }}>
                <div className="animate-spin rounded-full h-16 w-16 border-4" style={{ borderColor: '#e8c39e', borderTopColor: '#7a5c3c' }}></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen" style={{ background: 'linear-gradient(135deg, #e8c39e 0%, #ffffff 100%)' }}>
            {/* Header */}
            <div className="px-6 sm:px-8 py-12 text-white" style={{ background: 'linear-gradient(135deg, #7a5c3c 0%, #b08e6b 100%)' }}>
                <div className="max-w-4xl mx-auto">
                    <h1 className="text-4xl font-bold mb-2">Mi Perfil</h1>
                    <p className="text-amber-50">Bienvenido, {usuario?.first_name || 'Usuario'}</p>
                </div>
            </div>

            {/* Contenido */}
            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                {error && (
                    <div className="mb-6 p-4 rounded-lg border-l-4" style={{ backgroundColor: '#ffe8e8', borderColor: '#c73e3e' }}>
                        <p style={{ color: '#c73e3e' }} className="font-medium">⚠️ {error}</p>
                    </div>
                )}

                {/* Datos del Usuario */}
                <div className="bg-white rounded-2xl p-8 shadow-lg mb-8">
                    <h2 className="text-2xl font-bold mb-6" style={{ color: '#7a5c3c' }}>👤 Información Personal</h2>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Nombre</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.first_name} {usuario?.last_name}
                            </p>
                        </div>

                        <div>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Email</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>{usuario?.email}</p>
                        </div>

                        <div>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Teléfono</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.numero || 'No especificado'}
                            </p>
                        </div>

                        <div>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Zona</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.zona || 'No especificada'}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Diagnóstico de Cabello */}
                <DiagnosticoCard diagnostico={usuario?.cliente} loading={loading} />

                {/* Botones de Acción */}
                <div className="mt-8 flex gap-4">
                    <button
                        onClick={() => navigate('/editar-perfil')}
                        className="flex-1 font-bold py-3 px-6 rounded-lg text-white transition duration-200 transform hover:scale-105"
                        style={{ background: 'linear-gradient(135deg, #7a5c3c 0%, #b08e6b 100%)' }}
                    >
                        ✏️ Editar Perfil
                    </button>

                    <button
                        onClick={logout}
                        className="flex-1 font-bold py-3 px-6 rounded-lg transition duration-200 transform hover:scale-105"
                        style={{
                            background: 'linear-gradient(135deg, #e8c39e 0%, #f5e1ce 100%)',
                            color: '#7a5c3c'
                        }}
                    >
                        🚪 Cerrar Sesión
                    </button>
                </div>
            </div>
        </div>
    );
};

export default Perfil;

// Interceptor para manejar el refresh token
axios.interceptors.response.use(
    response => response,
    async (error) => {
        const originalRequest = error.config;

        // --- ¡AQUÍ ESTÁ LA CORRECCIÓN! ---
        // Verificamos primero que 'error.response' exista.
        // Si no existe (ej. ERR_CONNECTION_REFUSED), simplemente 
        // rechazamos el error y dejamos que el .catch() del componente (Login.js) lo maneje.
        if (error.response && 
            error.response.status === 401 && 
            error.response.data.code === 'token_not_valid' && 
            !originalRequest._retry) {
            
            originalRequest._retry = true;
            const refreshToken = localStorage.getItem('refresh_token');

            if (refreshToken) {
                try {
                    const response = await axios.post('/api/token/refresh/', {
                        refresh: refreshToken
                    });

                    localStorage.setItem('access_token', response.data.access);
                    axios.defaults.headers.common['Authorization'] = `Bearer ${response.data.access}`;
                    originalRequest.headers['Authorization'] = `Bearer ${response.data.access}`;
                    
                    return axios(originalRequest);

                } catch (refreshError) {
                    console.error("Fallo al refrescar el token:", refreshError);
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    axios.defaults.headers.common['Authorization'] = null;
                    window.location.href = '/login'; 
                    return Promise.reject(refreshError);
                }
            } else {
                console.log("No hay refresh token, redirigiendo a login");
                window.location.href = '/login';
            }
        }

        // 6. Para cualquier otro error (incluyendo el de conexión), simplemente lo devolvemos.
        return Promise.reject(error);
    }
);