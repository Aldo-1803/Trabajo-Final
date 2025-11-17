import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const Login = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const response = await axios.post('/api/usuarios/login/', {
                email,
                password
            });

            localStorage.setItem('access_token', response.data.access);
            localStorage.setItem('refresh_token', response.data.refresh);
            axios.defaults.headers.common['Authorization'] = `Bearer ${response.data.access}`;
            
            navigate('/perfil');
        } catch (err) {
            setError(err.response?.data?.detail || 'Error al iniciar sesión');
            console.error('Error:', err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center px-4" 
             style={{ background: 'var(--gradient-light)' }}>
            
            <div className="w-full max-w-md bg-white rounded-2xl overflow-hidden" 
                 style={{ boxShadow: 'var(--shadow-lg)' }}>
                
                {/* Header */}
                <div style={{ background: 'var(--gradient-primary)' }} 
                     className="px-6 sm:px-8 py-12">
                    <h1 className="text-4xl font-bold text-white mb-2">Bohemia Hair</h1>
                    <p className="text-amber-50">Descubre tu mejor versión capilar</p>
                </div>

                {/* Contenido */}
                <form onSubmit={handleSubmit} className="px-6 sm:px-8 py-8">
                    
                    {error && (
                        <div className="mb-6 p-4 rounded-lg border-l-4" 
                             style={{ backgroundColor: '#ffe8e8', borderColor: '#c73e3e' }}>
                            <p style={{ color: '#c73e3e' }} className="font-medium">⚠️ {error}</p>
                        </div>
                    )}

                    {/* Email */}
                    <div className="mb-6">
                        <label className="block text-sm font-semibold mb-3" 
                               style={{ color: 'var(--primary-dark)' }}>
                            Correo Electrónico
                        </label>
                        <input 
                            type="email" 
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            className="w-full px-4 py-3 border-2 rounded-lg focus:outline-none focus:ring-2 transition"
                            style={{
                                borderColor: '#e8c39e',
                                backgroundColor: '#f5e1ce',
                                color: '#7a5c3c',
                                '--tw-ring-color': '#b08e6b'
                            }}
                            placeholder="tu@email.com"
                        />
                    </div>

                    {/* Contraseña */}
                    <div className="mb-8">
                        <label className="block text-sm font-semibold mb-3" 
                               style={{ color: 'var(--primary-dark)' }}>
                            Contraseña
                        </label>
                        <input 
                            type="password" 
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            className="w-full px-4 py-3 border-2 rounded-lg focus:outline-none focus:ring-2 transition"
                            style={{
                                borderColor: '#e8c39e',
                                backgroundColor: '#f5e1ce',
                                color: '#7a5c3c',
                            }}
                            placeholder="Ingresa tu contraseña"
                        />
                    </div>

                    {/* Botón Login */}
                    <button 
                        type="submit"
                        disabled={loading}
                        className="w-full font-bold py-3 px-6 rounded-lg text-white transition duration-200 transform hover:scale-105 disabled:opacity-50"
                        style={{
                            background: loading ? '#b08e6b' : 'var(--gradient-primary)',
                            cursor: loading ? 'not-allowed' : 'pointer',
                            boxShadow: 'var(--shadow-md)'
                        }}
                    >
                        {loading ? '⏳ Iniciando sesión...' : '🔐 Iniciar Sesión'}
                    </button>
                </form>

                {/* Separador */}
                <div className="px-6 sm:px-8 py-4" style={{ backgroundColor: '#f5e1ce', borderTop: '1px solid #e8c39e' }}>
                    <p className="text-center text-sm font-medium" style={{ color: '#7a5c3c' }}>
                        ¿No tienes cuenta?
                    </p>
                </div>

                {/* Enlaces */}
                <div className="px-6 sm:px-8 py-6 space-y-3 bg-white">
                    <button 
                        type="button"
                        onClick={() => navigate('/registro')}
                        className="w-full font-bold py-3 px-6 rounded-lg transition duration-200 transform hover:scale-105"
                        style={{
                            background: 'var(--gradient-light)',
                            color: '#7a5c3c',
                            boxShadow: 'var(--shadow-sm)'
                        }}
                    >
                        📝 Crear Cuenta
                    </button>

                    <button 
                        type="button"
                        onClick={() => navigate('/recuperar-contrasena')}
                        className="w-full font-semibold py-2 px-6 rounded-lg transition"
                        style={{ color: '#b08e6b' }}
                    >
                        🔑 ¿Olvidaste tu contraseña?
                    </button>
                </div>
            </div>
        </div>
    );
};

export default Login;