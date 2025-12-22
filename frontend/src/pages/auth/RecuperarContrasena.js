// frontend/src/components/RecuperarContrasena.js

import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const RecuperarContrasena = () => {
    const [email, setEmail] = useState('');
    const [mensaje, setMensaje] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleChange = (e) => {
        setEmail(e.target.value);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        setMensaje('');

        try {
            const response = await axios.post('/api/usuarios/recuperar-contrasena/', {
                email: email,
            });
            
            setMensaje(response.data.mensaje || 'Se ha enviado un correo de recuperación.');
            setEmail('');
        } catch (error) {
            console.error('Error al recuperar contraseña:', error);
            setError(error.response?.data?.error || 'Error al recuperar contraseña. Intenta más tarde.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-rose-50 via-amber-50 to-orange-50 flex items-center justify-center px-4 sm:px-6 lg:px-8">
            <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden">
                
                {/* Header */}
                <div className="bg-gradient-to-r from-rose-300 via-amber-200 to-orange-200 px-6 py-10">
                    <h1 className="text-4xl font-bold text-rose-900">Recuperar Contraseña</h1>
                    <p className="text-rose-700 mt-2 text-lg">Te ayudaremos a recuperar tu acceso</p>
                </div>

                {/* Contenido del formulario */}
                <form onSubmit={handleSubmit} className="px-6 py-8">
                    
                    {/* Mensaje de error */}
                    {error && (
                        <div className="mb-6 p-4 bg-red-50 border-l-4 border-red-400 rounded-lg">
                            <p className="text-red-700 font-medium">{error}</p>
                        </div>
                    )}
                    
                    {/* Mensaje de éxito */}
                    {mensaje && (
                        <div className="mb-6 p-4 bg-green-50 border-l-4 border-green-400 rounded-lg">
                            <p className="text-green-700 font-medium">✓ {mensaje}</p>
                        </div>
                    )}

                    {/* Campo de correo */}
                    <div className="mb-6">
                        <label className="block text-sm font-semibold text-rose-700 mb-3">
                            Correo electrónico
                            <span className="text-rose-500">*</span>
                        </label>
                        <input 
                            type="email" 
                            name="email" 
                            value={email}
                            onChange={handleChange}
                            required
                            className="w-full px-4 py-3 border-2 border-rose-200 rounded-lg bg-rose-50 text-gray-700 focus:outline-none focus:ring-2 focus:ring-rose-400 focus:border-transparent transition duration-200 placeholder-gray-400"
                            placeholder="tu@email.com"
                        />
                        <p className="text-gray-600 text-xs mt-3 bg-amber-50 p-3 rounded-lg border border-amber-200">
                            Ingresa el correo asociado a tu cuenta y te enviaremos instrucciones para recuperar tu contraseña.
                        </p>
                    </div>

                    {/* Botón de envío */}
                    <button 
                        type="submit" 
                        disabled={loading}
                        className={`w-full font-bold py-3 px-6 rounded-lg shadow-lg transition duration-200 transform mb-4 ${
                            loading 
                                ? 'bg-rose-300 text-gray-500 cursor-not-allowed opacity-50' 
                                : 'bg-gradient-to-r from-rose-400 to-orange-400 hover:from-rose-500 hover:to-orange-500 text-white hover:scale-105'
                        }`}
                    >
                        {loading ? '⏳ Enviando...' : '✉️ Enviar enlace de recuperación'}
                    </button>
                </form>

                {/* Separador */}
                <div className="px-6 py-4 bg-gradient-to-r from-rose-50 to-orange-50 border-t border-rose-100">
                    <p className="text-center text-gray-600 text-sm font-medium">¿Necesitas ayuda adicional?</p>
                </div>

                {/* Enlaces de navegación */}
                <div className="px-6 py-6 space-y-3 bg-white">
                    <button 
                        type="button" 
                        onClick={() => navigate('/login')}
                        className="w-full bg-gradient-to-r from-amber-200 to-orange-200 hover:from-amber-300 hover:to-orange-300 text-amber-900 font-bold py-3 px-6 rounded-lg shadow-md transition duration-200 transform hover:scale-105"
                    >
                        Volver a Iniciar Sesión
                    </button>

                    <button 
                        type="button" 
                        onClick={() => navigate('/registro')}
                        className="w-full text-rose-600 hover:text-rose-700 font-semibold py-2 px-6 rounded-lg transition duration-200 underline hover:no-underline"
                    >
                        ¿No tienes cuenta? Regístrate
                    </button>
                </div>
            </div>
        </div>
    );
};

export default RecuperarContrasena;