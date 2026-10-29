import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

import { SESSION_STATUS, useSession } from '../../context/SessionContext';
import { getLandingPath } from '../../utils/sessionLanding';

const Login = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const {
        session,
        loading: sessionLoading,
        refreshSession
    } = useSession();

    useEffect(() => {
        if (
            session.status !== SESSION_STATUS.AUTHENTICATED
            && session.status !== SESSION_STATUS.ERROR
        ) {
            return;
        }

        const landingPath = getLandingPath(session);
        if (landingPath) {
            navigate(landingPath, { replace: true });
        }
    }, [navigate, session]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            // 1. LOGIN: Obtenemos los tokens
            const response = await axios.post('http://127.0.0.1:8000/api/usuarios/login/', {
                email,
                password
            });

            const { access, refresh } = response.data;

            localStorage.setItem('access_token', access);
            localStorage.setItem('refresh_token', refresh);

            const refreshedSession = await refreshSession();

            if (refreshedSession?.status === SESSION_STATUS.AUTHENTICATED) {
                const usuario = refreshedSession.user;
                localStorage.setItem('user_info', JSON.stringify({
                    id: usuario.id,
                    email: usuario.email,
                    first_name: usuario.first_name,
                    last_name: usuario.last_name
                }));
            } else if (refreshedSession?.status !== SESSION_STATUS.ERROR) {
                setError('No se pudo validar la sesión iniciada. Intenta nuevamente.');
            }
        } catch (err) {
            setError(err.response?.data?.detail || 'Error al iniciar sesión. Verifique sus credenciales.');
            console.error('Error de login:', err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center px-4" 
             style={{ background: 'var(--gradient-light)' }}>
            
            <div className="w-full max-w-md bg-white rounded-2xl overflow-hidden shadow-xl">
                {/* Header del Formulario */}
                <div className="px-6 sm:px-8 py-8" style={{ backgroundColor: '#7a5c3c' }}>
                    <h2 className="text-3xl font-bold text-center text-white mb-2">Bohemia Hair</h2>
                    <p className="text-center text-amber-100 text-sm">
                        {sessionLoading ? 'Verificando sesión...' : 'Ingresa a tu cuenta'}
                    </p>
                </div>

                {sessionLoading ? (
                    <div className="px-6 sm:px-8 py-12 text-center text-gray-600">
                        Cargando contexto de sesión...
                    </div>
                ) : (
                    <>
                        {/* Formulario de Login */}
                        <form onSubmit={handleSubmit} className="px-6 sm:px-8 py-8 space-y-6">
                            {error && (
                                <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded animate-pulse">
                                    <p className="text-red-700 text-sm font-medium">{error}</p>
                                </div>
                            )}

                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-2">Correo Electrónico</label>
                                <input 
                                    type="email" 
                                    className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-amber-500 focus:border-transparent transition duration-200 outline-none"
                                    placeholder="ejemplo@correo.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required 
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-2">Contraseña</label>
                                <input 
                                    type="password" 
                                    className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-amber-500 focus:border-transparent transition duration-200 outline-none"
                                    placeholder="••••••••"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required 
                                />
                            </div>

                            <button 
                                type="submit" 
                                disabled={loading}
                                className="w-full font-bold py-3 px-6 rounded-lg text-white transition duration-200 transform hover:scale-[1.02] active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                                style={{ background: 'linear-gradient(135deg, #7a5c3c 0%, #b08e6b 100%)' }}
                            >
                                {loading ? (
                                    <span className="flex items-center justify-center gap-2">
                                        <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        Iniciando...
                                    </span>
                                ) : 'Iniciar Sesión'}
                            </button>
                        </form>

                        {/* Footer del Formulario */}
                        <div className="px-6 sm:px-8 py-4 bg-gray-50 border-t border-gray-100">
                            <p className="text-center text-sm font-medium text-gray-600 mb-4">
                                ¿No tienes cuenta?
                            </p>
                            
                            <div className="space-y-3">
                                <button 
                                    type="button"
                                    onClick={() => navigate('/registro')}
                                    className="w-full font-bold py-3 px-6 rounded-lg text-amber-900 border border-amber-200 bg-amber-50 hover:bg-amber-100 transition duration-200"
                                >
                                    Crear Cuenta Nueva
                                </button>

                                <button 
                                    type="button"
                                    onClick={() => navigate('/recuperar-contrasena')}
                                    className="w-full text-sm font-semibold text-gray-500 hover:text-amber-700 transition py-2"
                                >
                                    ¿Olvidaste tu contraseña?
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};

export default Login;
