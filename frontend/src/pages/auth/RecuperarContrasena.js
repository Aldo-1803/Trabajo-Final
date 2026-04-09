import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { IconCheckCircle } from '../../components/common/Icons';

// Paleta de colores Bohemia Hair
const COLORS = {
    bg_light: '#F5EBE0',        // Fondo muy claro
    bg_white: '#FFFFFF',         // Blanco
    primary_dark: '#817773',     // Marrón oscuro principal
    primary_light: '#AB9A91',    // Marrón claro
    accent_light: '#D5BDAF',     // Beige saturado
    accent_very_light: '#E3D5CA', // Beige medio
    success: '#6B9C7A',          // Verde éxito
    error: '#C73E3E',            // Rojo error
    error_bg: '#FFE8E8',         // Fondo rojo claro
    text_dark: '#2C2C2C',        // Texto oscuro
    text_light: '#8B8682'        // Texto claro
};

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
            const response = await axios.post('http://127.0.0.1:8000/api/usuarios/password-reset/request/', {
                email: email,
            });
            
            setMensaje(response.data.mensaje || 'Se ha enviado un enlace de recuperación a tu correo.');
            setEmail('');
        } catch (error) {
            console.error('Error al recuperar contraseña:', error);
            setError(error.response?.data?.error || 'Error al recuperar contraseña. Verifica el correo e intenta de nuevo.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div 
            className="min-h-screen flex items-center justify-center px-4 sm:px-6 lg:px-8 py-12"
            style={{ backgroundColor: COLORS.bg_light }}
        >
            {/* Contenedor principal */}
            <div className="w-full max-w-md">
                {/* Card principal */}
                <div 
                    className="rounded-3xl shadow-2xl overflow-hidden backdrop-blur-sm"
                    style={{ backgroundColor: COLORS.bg_white }}
                >
                    {/* Header decorativo */}
                    <div 
                        className="px-6 sm:px-8 py-10 sm:py-12"
                        style={{ backgroundColor: COLORS.primary_dark }}
                    >
                        <h1 className="text-3xl sm:text-4xl font-bold text-white mb-2">
                            Recuperar Contraseña
                        </h1>
                        <p className="text-base sm:text-lg" style={{ color: COLORS.accent_light }}>
                            Te ayudaremos a recuperar tu acceso
                        </p>
                    </div>

                    {/* Contenido del formulario */}
                    <form onSubmit={handleSubmit} className="px-6 sm:px-8 py-8">
                        
                        {/* Mensaje de error */}
                        {error && (
                            <div 
                                className="mb-6 p-4 border-l-4 rounded-lg animate-pulse"
                                style={{ 
                                    backgroundColor: COLORS.error_bg,
                                    borderColor: COLORS.error
                                }}
                            >
                                <p style={{ color: COLORS.error }} className="font-medium flex items-center gap-2">
                                    {error}
                                </p>
                            </div>
                        )}
                        
                        {/* Mensaje de éxito */}
                        {mensaje && (
                            <div 
                                className="mb-6 p-4 rounded-lg animate-pulse"
                                style={{ 
                                    backgroundColor: '#E8F5E8',
                                    borderLeft: `4px solid ${COLORS.success}`
                                }}
                            >
                                <p style={{ color: COLORS.success }} className="font-medium flex items-center gap-2">
                                    <IconCheckCircle className="h-4 w-4" /> {mensaje}
                                </p>
                            </div>
                        )}

                        {/* Campo de correo */}
                        <div className="mb-6">
                            <label 
                                className="block text-sm font-semibold mb-3"
                                style={{ color: COLORS.primary_dark }}
                            >
                                Correo electrónico
                                <span style={{ color: COLORS.error }}>*</span>
                            </label>
                            <input 
                                type="email" 
                                name="email" 
                                value={email}
                                onChange={handleChange}
                                required
                                disabled={loading}
                                className="w-full px-4 py-3 rounded-lg border-2 transition duration-200 focus:outline-none focus:ring-2 focus:ring-offset-0 disabled:opacity-60 disabled:cursor-not-allowed"
                                style={{ 
                                    backgroundColor: COLORS.bg_light,
                                    borderColor: COLORS.accent_very_light,
                                    color: COLORS.text_dark,
                                    focusColor: COLORS.primary_dark
                                }}
                                placeholder="correo@ejemplo.com"
                                onFocus={(e) => {
                                    e.target.style.borderColor = COLORS.primary_dark;
                                    e.target.style.boxShadow = `0 0 0 2px ${COLORS.accent_light}`;
                                }}
                                onBlur={(e) => {
                                    e.target.style.borderColor = COLORS.accent_very_light;
                                    e.target.style.boxShadow = 'none';
                                }}
                            />
                            <p 
                                className="text-xs sm:text-sm mt-3 p-3 rounded-lg border"
                                style={{ 
                                    backgroundColor: COLORS.bg_light,
                                    borderColor: COLORS.accent_very_light,
                                    color: COLORS.text_light
                                }}
                            >
                                Ingresa el correo asociado a tu cuenta y te enviaremos un enlace para recuperar tu contraseña.
                            </p>
                        </div>

                        {/* Botón de envío */}
                        <button 
                            type="submit" 
                            disabled={loading}
                            className="w-full font-bold py-3 px-6 rounded-lg shadow-lg transition duration-200 transform hover:shadow-xl disabled:opacity-60 disabled:cursor-not-allowed mb-4"
                            style={{ 
                                backgroundColor: loading ? COLORS.accent_light : COLORS.primary_dark,
                                color: COLORS.bg_white,
                                transform: loading ? 'scale(1)' : 'scale(1)',
                                cursor: loading ? 'not-allowed' : 'pointer'
                            }}
                            onMouseEnter={(e) => !loading && (e.target.style.opacity = '0.9')}
                            onMouseLeave={(e) => !loading && (e.target.style.opacity = '1')}
                        >
                            {loading ? 'Enviando...' : 'Enviar enlace de recuperación'}
                        </button>

                        {/* Separador */}
                        <div 
                            className="my-6 h-px"
                            style={{ backgroundColor: COLORS.accent_very_light }}
                        />

                        {/* Enlaces de navegación */}
                        <div className="space-y-3">
                            <button 
                                type="button" 
                                onClick={() => navigate('/login')}
                                className="w-full font-semibold py-3 px-6 rounded-lg transition duration-200"
                                style={{ 
                                    backgroundColor: COLORS.accent_light,
                                    color: COLORS.primary_dark
                                }}
                                onMouseEnter={(e) => e.target.style.opacity = '0.9'}
                                onMouseLeave={(e) => e.target.style.opacity = '1'}
                            >
                                ← Volver a Iniciar Sesión
                            </button>

                            <button 
                                type="button" 
                                onClick={() => navigate('/registro')}
                                className="w-full font-semibold py-3 px-6 rounded-lg border-2 transition duration-200"
                                style={{ 
                                    borderColor: COLORS.primary_dark,
                                    color: COLORS.primary_dark,
                                    backgroundColor: 'transparent'
                                }}
                                onMouseEnter={(e) => (
                                    e.target.style.backgroundColor = COLORS.bg_light
                                )}
                                onMouseLeave={(e) => (
                                    e.target.style.backgroundColor = 'transparent'
                                )}
                            >
                                ¿No tienes cuenta? Regístrate
                            </button>
                        </div>
                    </form>
                </div>

                {/* Nota de seguridad */}
                <div className="mt-6 text-center text-xs sm:text-sm" style={{ color: COLORS.text_light }}>
                    <p>Tu información está protegida y segura</p>
                </div>
            </div>
        </div>
    );
};

export default RecuperarContrasena;