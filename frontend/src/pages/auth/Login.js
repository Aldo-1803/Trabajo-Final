import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const Login = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const [currentUser, setCurrentUser] = useState(null);
    const [showLoginForm, setShowLoginForm] = useState(true);

    // Verificar si ya hay una sesión activa al cargar el componente
    useEffect(() => {
        const checkExistingSession = async () => {
            const token = localStorage.getItem('access_token');
            if (token) {
                try {
                    // Verificar si el token es válido
                    const response = await axios.get('http://127.0.0.1:8000/api/usuarios/perfil/', {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    
                    const usuario = response.data;
                    setCurrentUser(usuario);
                    setShowLoginForm(false);
                } catch (error) {
                    // Si el token no es válido, limpiarlo
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    delete axios.defaults.headers.common['Authorization'];
                    setShowLoginForm(true);
                }
            }
        };

        checkExistingSession();
    }, [navigate]);

    const handleLogout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        delete axios.defaults.headers.common['Authorization'];
        setCurrentUser(null);
        setShowLoginForm(true);
    };

    const handleGoToDashboard = () => {
        if (currentUser.is_staff) {
            navigate('/admin-dashboard');
        } else {
            navigate('/perfil');
        }
    };

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

            // 2. GUARDADO: Persistimos sesión
            localStorage.setItem('access_token', access);
            localStorage.setItem('refresh_token', refresh);
            axios.defaults.headers.common['Authorization'] = `Bearer ${access}`;

            // 3. VERIFICACIÓN DE ROL (El paso nuevo)
            try {
                // Usamos el token recién obtenido para pedir el perfil
                const perfilResponse = await axios.get('http://127.0.0.1:8000/api/usuarios/perfil/', {
                    headers: { 'Authorization': `Bearer ${access}` }
                });

                const usuario = perfilResponse.data;

                // 4. REDIRECCIÓN INTELIGENTE
                if (usuario.is_staff) {
                    navigate('/admin-dashboard');
                } else {
                    navigate('/perfil');
                }

            } catch (perfilError) {
                console.error("Error obteniendo perfil:", perfilError);
                // Si falla la verificación, por seguridad mandamos al perfil de cliente
                navigate('/perfil');
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
                        {currentUser ? 'Sesión Activa' : 'Ingresa a tu cuenta'}
                    </p>
                </div>

                {/* Mostrar información del usuario actual si ya está logueado */}
                {currentUser && !showLoginForm ? (
                    <div className="px-6 sm:px-8 py-8 space-y-6">
                        <div className="text-center">
                            <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                                <div className="flex items-center justify-center mb-3">
                                    <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center">
                                        <span className="text-2xl font-bold text-green-600">
                                            {currentUser.first_name ? currentUser.first_name[0].toUpperCase() : currentUser.email[0].toUpperCase()}
                                        </span>
                                    </div>
                                </div>
                                <h3 className="text-lg font-semibold text-gray-800 mb-1">
                                    {currentUser.first_name && currentUser.last_name 
                                        ? `${currentUser.first_name} ${currentUser.last_name}`
                                        : currentUser.email
                                    }
                                </h3>
                                <p className="text-sm text-gray-600 mb-2">{currentUser.email}</p>
                                <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                                    currentUser.is_staff 
                                        ? 'bg-purple-100 text-purple-800' 
                                        : 'bg-blue-100 text-blue-800'
                                }`}>
                                    {currentUser.is_staff ? 'Administrador' : 'Cliente'}
                                </span>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <button 
                                onClick={handleGoToDashboard}
                                className="w-full font-bold py-3 px-6 rounded-lg text-white transition duration-200 transform hover:scale-[1.02] active:scale-95"
                                style={{ background: 'linear-gradient(135deg, #7a5c3c 0%, #b08e6b 100%)' }}
                            >
                                {currentUser.is_staff ? 'Ir al Panel de Admin' : 'Ir a Mi Perfil'}
                            </button>
                            
                            <button 
                                onClick={() => setShowLoginForm(true)}
                                className="w-full font-bold py-3 px-6 rounded-lg text-amber-900 border border-amber-200 bg-amber-50 hover:bg-amber-100 transition duration-200"
                            >
                                Cambiar de Usuario
                            </button>
                            
                            <button 
                                onClick={handleLogout}
                                className="w-full font-bold py-3 px-6 rounded-lg text-red-600 border border-red-200 bg-red-50 hover:bg-red-100 transition duration-200"
                            >
                                Cerrar Sesión
                            </button>
                        </div>
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