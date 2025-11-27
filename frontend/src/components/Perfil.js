import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const Perfil = () => {
    const [usuario, setUsuario] = useState(null);
    const [diagnostico, setDiagnostico] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    useEffect(() => {
        const fetchDatos = async () => {
            try {
                setLoading(true);
                const token = localStorage.getItem('access_token');
                
                if (!token) {
                    navigate('/login');
                    return;
                }

                // 1. Obtener perfil del usuario
                const perfilResponse = await axios.get('/api/usuarios/perfil/', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                setUsuario(perfilResponse.data);

                // 2. Obtener diagnóstico
                try {
                    const diagResponse = await axios.get('/api/usuarios/diagnostico/', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    setDiagnostico(diagResponse.data);
                } catch (diagErr) {
                    console.error('Error al cargar diagnóstico:', diagErr);
                }
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

        fetchDatos();
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

                {/* Información Personal */}
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

                {/* Diagnóstico */}
                {diagnostico && (
                    <div className="bg-gradient-to-r from-rose-50 to-amber-50 rounded-2xl p-8 shadow-lg border-l-4 border-rose-400 mb-8">
                        <h2 className="text-2xl font-bold mb-4 text-rose-900">🔍 Tu Diagnóstico Personalizado</h2>
                        
                        <div className="bg-white rounded-lg p-6 mb-4">
                            <p className="text-lg text-gray-700 leading-relaxed">
                                {diagnostico.mensaje_diagnostico}
                            </p>
                        </div>

                        <div className="bg-white rounded-lg p-4 mb-4">
                            <p className="text-sm font-semibold text-rose-700 mb-2">💡 Recomendación:</p>
                            <p className="text-gray-700 font-medium">{diagnostico.accion}</p>
                        </div>

                        {diagnostico.puntaje_final !== undefined && (
                            <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                                <p className="text-sm font-semibold text-gray-700">Puntaje de Salud: 
                                    <span className="text-lg font-bold text-rose-600 ml-2">{diagnostico.puntaje_final}/10</span>
                                </p>
                            </div>
                        )}
                    </div>
                )}

                {/* Perfil Capilar */}
                <div className="bg-white rounded-2xl p-8 shadow-lg border-l-4 mb-8" style={{ borderColor: '#7a5c3c' }}>
                    <h2 className="text-2xl font-bold mb-6" style={{ color: '#7a5c3c' }}>💇 Tu Perfil Capilar</h2>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Tipo de Cabello</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.tipo_cabello || 'No especificado'}
                            </p>
                        </div>
                        
                        <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Grosor</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.grosor_cabello || 'No especificado'}
                            </p>
                        </div>

                        <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Porosidad</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.porosidad_cabello || 'No especificado'}
                            </p>
                        </div>

                        <div className="p-4 rounded-lg" style={{ backgroundColor: '#f5e1ce' }}>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Cuero Cabelludo</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.cuero_cabelludo || 'No especificado'}
                            </p>
                        </div>

                        <div className="p-4 rounded-lg col-span-1 md:col-span-2" style={{ backgroundColor: '#f5e1ce' }}>
                            <p className="text-sm font-semibold" style={{ color: '#7a5c3c' }}>Estado General</p>
                            <p className="text-lg font-bold mt-2" style={{ color: '#b08e6b' }}>
                                {usuario?.estado_general || 'No especificado'}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Botones de Acción */}
                <div className="mt-8 flex gap-4">
                    <button
                        onClick={() => navigate('/editar-perfil')}
                        className="flex-1 font-bold py-3 px-6 rounded-lg text-white transition duration-200 transform hover:scale-105"
                        style={{ background: 'linear-gradient(135deg, #7a5c3c 0%, #b08e6b 100%)' }}
                    >
                        Editar Perfil
                    </button>

                    <button
                        onClick={logout}
                        className="flex-1 font-bold py-3 px-6 rounded-lg transition duration-200 transform hover:scale-105"
                        style={{
                            background: 'linear-gradient(135deg, #e8c39e 0%, #f5e1ce 100%)',
                            color: '#7a5c3c'
                        }}
                    >
                        Cerrar Sesión
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