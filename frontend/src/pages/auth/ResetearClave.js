import React, { useState } from 'react';
import axios from 'axios';
import { useParams, useNavigate } from 'react-router-dom';
import { IconCheckCircle, IconInfo, IconKey, IconLock, IconWarning } from '../../components/common/Icons';

// Paleta de colores Bohemia Hair
const COLORS = {
    bg_light: '#F5EBE0',
    bg_white: '#FFFFFF',
    primary_dark: '#817773',
    primary_light: '#AB9A91',
    accent_light: '#D5BDAF',
    accent_very_light: '#E3D5CA',
    success: '#6B9C7A',
    error: '#C73E3E',
    error_bg: '#FFE8E8',
    text_dark: '#2C2C2C',
    text_light: '#8B8682'
};

const ResetearClave = () => {
    const { uid, token } = useParams();
    const navigate = useNavigate();
    
    const [password, setPassword] = useState('');
    const [password2, setPassword2] = useState('');
    const [mensaje, setMensaje] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setMensaje('');

        // Validación
        if (password !== password2) {
            setError('Las contraseñas no coinciden.');
            return;
        }

        if (password.length < 8) {
            setError('La contraseña debe tener al menos 8 caracteres.');
            return;
        }

        try {
            setLoading(true);
            const response = await axios.post(
                'http://127.0.0.1:8000/api/usuarios/password-reset/confirm/',
                {
                    uid: uid,
                    token: token,
                    password: password,
                    password2: password2
                }
            );

            setMensaje(response.data.mensaje);
            setTimeout(() => {
                navigate('/login');
            }, 3000);

        } catch (err) {
            console.error('Error al resetear la clave:', err);
            setError(err.response?.data?.error || 'Error al procesar la solicitud. Verifica el enlace e intenta de nuevo.');
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
                    className="rounded-3xl shadow-2xl overflow-hidden"
                    style={{ backgroundColor: COLORS.bg_white }}
                >
                    {/* Header decorativo */}
                    <div 
                        className="px-6 sm:px-8 py-10 sm:py-12"
                        style={{ backgroundColor: COLORS.primary_dark }}
                    >
                        <h1 className="text-3xl sm:text-4xl font-bold text-white mb-2">
                            <span className="inline-flex items-center gap-2">
                                <IconKey className="h-6 w-6" /> Crear Nueva Contraseña
                            </span>
                        </h1>
                        <p className="text-base sm:text-lg" style={{ color: COLORS.accent_light }}>
                            Establece una contraseña segura para tu cuenta
                        </p>
                    </div>

                    {/* Contenido del formulario */}
                    <form onSubmit={handleSubmit} className="px-6 sm:px-8 py-8">
                        
                        {/* Mensaje de error */}
                        {error && (
                            <div 
                                className="mb-6 p-4 border-l-4 rounded-lg"
                                style={{ 
                                    backgroundColor: COLORS.error_bg,
                                    borderColor: COLORS.error
                                }}
                            >
                                <p style={{ color: COLORS.error }} className="font-medium flex items-center gap-2">
                                    <IconWarning className="h-4 w-4" /> {error}
                                </p>
                            </div>
                        )}
                        
                        {/* Mensaje de éxito */}
                        {mensaje && (
                            <div 
                                className="mb-6 p-4 rounded-lg"
                                style={{ 
                                    backgroundColor: '#E8F5E8',
                                    borderLeft: `4px solid ${COLORS.success}`
                                }}
                            >
                                <p style={{ color: COLORS.success }} className="font-medium flex items-center gap-2">
                                    <IconCheckCircle className="h-4 w-4" /> {mensaje}
                                </p>
                                <p style={{ color: COLORS.text_light }} className="text-sm mt-2">
                                    Serás redirigido al login en 3 segundos...
                                </p>
                            </div>
                        )}

                        {/* Campo contraseña nueva */}
                        <div className="mb-5">
                            <label 
                                className="block text-sm font-semibold mb-2"
                                style={{ color: COLORS.primary_dark }}
                            >
                                Nueva Contraseña
                                <span style={{ color: COLORS.error }}>*</span>
                            </label>
                            <input 
                                type="password" 
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                disabled={loading || !!mensaje}
                                required
                                className="w-full px-4 py-3 rounded-lg border-2 transition duration-200 focus:outline-none focus:ring-2 disabled:opacity-60 disabled:cursor-not-allowed"
                                style={{ 
                                    backgroundColor: COLORS.bg_light,
                                    borderColor: COLORS.accent_very_light,
                                    color: COLORS.text_dark
                                }}
                                placeholder="Mínimo 8 caracteres"
                                onFocus={(e) => {
                                    e.target.style.borderColor = COLORS.primary_dark;
                                }}
                                onBlur={(e) => {
                                    e.target.style.borderColor = COLORS.accent_very_light;
                                }}
                            />
                        </div>

                        {/* Campo confirmar contraseña */}
                        <div className="mb-6">
                            <label 
                                className="block text-sm font-semibold mb-2"
                                style={{ color: COLORS.primary_dark }}
                            >
                                Confirmar Contraseña
                                <span style={{ color: COLORS.error }}>*</span>
                            </label>
                            <input 
                                type="password" 
                                value={password2}
                                onChange={(e) => setPassword2(e.target.value)}
                                disabled={loading || !!mensaje}
                                required
                                className="w-full px-4 py-3 rounded-lg border-2 transition duration-200 focus:outline-none focus:ring-2 disabled:opacity-60 disabled:cursor-not-allowed"
                                style={{ 
                                    backgroundColor: COLORS.bg_light,
                                    borderColor: COLORS.accent_very_light,
                                    color: COLORS.text_dark
                                }}
                                placeholder="Repite la contraseña"
                                onFocus={(e) => {
                                    e.target.style.borderColor = COLORS.primary_dark;
                                }}
                                onBlur={(e) => {
                                    e.target.style.borderColor = COLORS.accent_very_light;
                                }}
                            />
                            <p 
                                className="text-xs sm:text-sm mt-2"
                                style={{ color: COLORS.text_light }}
                            >
                                <span className="inline-flex items-center gap-2">
                                    <IconInfo className="h-4 w-4" /> Usa mayúsculas, números y caracteres especiales para mayor seguridad
                                </span>
                            </p>
                        </div>

                        {/* Botón de envío */}
                        <button 
                            type="submit" 
                            disabled={loading || !!mensaje}
                            className="w-full font-bold py-3 px-6 rounded-lg shadow-lg transition duration-200 transform disabled:opacity-60 disabled:cursor-not-allowed"
                            style={{ 
                                backgroundColor: loading ? COLORS.accent_light : COLORS.primary_dark,
                                color: COLORS.bg_white,
                                cursor: loading ? 'not-allowed' : 'pointer'
                            }}
                            onMouseEnter={(e) => !loading && !mensaje && (e.target.style.opacity = '0.9')}
                            onMouseLeave={(e) => !loading && !mensaje && (e.target.style.opacity = '1')}
                        >
                            {loading ? 'Guardando...' : (
                                <span className="inline-flex items-center gap-2">
                                    <IconCheckCircle className="h-4 w-4" /> Guardar Nueva Contraseña
                                </span>
                            )}
                        </button>

                        {/* Separador */}
                        <div 
                            className="my-6 h-px"
                            style={{ backgroundColor: COLORS.accent_very_light }}
                        />

                        {/* Volver a login */}
                        <button 
                            type="button" 
                            onClick={() => navigate('/login')}
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
                            ← Volver a Iniciar Sesión
                        </button>
                    </form>
                </div>

                {/* Nota de seguridad */}
                <div className="mt-6 text-center text-xs sm:text-sm" style={{ color: COLORS.text_light }}>
                    <p className="inline-flex items-center gap-2">
                        <IconLock className="h-4 w-4" /> Tu contraseña está protegida con encriptación segura
                    </p>
                </div>
            </div>
        </div>
    );
};

export default ResetearClave;