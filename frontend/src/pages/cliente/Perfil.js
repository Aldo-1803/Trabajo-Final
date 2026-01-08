import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
// import CampanaNotificaciones from '../../components/CampanaNotificaciones';  // No usada

// ============================================================================
// COMPONENTE PRINCIPAL
// ============================================================================

const Perfil = () => {
    // ========================================================================
    // ESTADO
    // ========================================================================
    const [usuario, setUsuario] = useState(null);
    const [diagnostico, setDiagnostico] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    // ========================================================================
    // EFECTOS
    // ========================================================================
    useEffect(() => {
        fetchDatos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [navigate]);

    // ========================================================================
    // FUNCIONES
    // ========================================================================
    const fetchDatos = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('access_token');
            
            if (!token) {
                navigate('/login');
                return;
            }

            const perfilResponse = await axios.get('/api/usuarios/perfil/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setUsuario(perfilResponse.data);

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

    // const logout = () => {
    //     localStorage.removeItem('access_token');
    //     localStorage.removeItem('refresh_token');
    //     axios.defaults.headers.common['Authorization'] = null;
    //     navigate('/login');
    // };

    // ========================================================================
    // RENDER - LOADING
    // ========================================================================
    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#F5EBE0' }}>
                <div className="animate-spin rounded-full h-16 w-16 border-4" style={{ borderColor: '#E3D5CA', borderTopColor: '#817773' }}></div>
            </div>
        );
    }

    // ========================================================================
    // RENDER - MAIN
    // ========================================================================
    return (
        <div style={{ backgroundColor: '#F5EBE0' }} className="min-h-screen">
            {/* CONTENIDO PRINCIPAL */}
            <div className="max-w-5xl mx-auto px-4 py-12">
                {/* ALERTA DE ERROR */}
                {error && <ErrorAlert error={error} />}

                {/* GRID DE TARJETAS */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                    <InformacionPersonal usuario={usuario} />
                    <PerfilCapilar usuario={usuario} />
                </div>

                {/* DIAGNÓSTICO */}
                {diagnostico && <DiagnosticoCard diagnostico={diagnostico} navigate={navigate} />}
            </div>
        </div>
    );
};

// ============================================================================
// COMPONENTES SECUNDARIOS
// ============================================================================

const ErrorAlert = ({ error }) => (
    <div className="mb-8 p-4 rounded-lg border-l-4" style={{ backgroundColor: '#FFE8E8', borderColor: '#C73E3E' }}>
        <p style={{ color: '#C73E3E' }} className="font-medium">⚠️ {error}</p>
    </div>
);

const InformacionPersonal = ({ usuario }) => (
    <div style={{ backgroundColor: 'white', borderLeft: '5px solid #AB9A91' }} className="rounded-xl p-8 shadow-lg">
        <h2 style={{ color: '#817773' }} className="text-2xl font-bold mb-6">📋 Información Personal</h2>
        
        <div className="space-y-4">
            <InfoRow label="Nombre Completo" value={`${usuario?.first_name} ${usuario?.last_name}`} />
            <InfoRow label="Teléfono" value={usuario?.numero || 'No especificado'} />
            <InfoRow label="Zona" value={usuario?.zona || 'No especificada'} />
        </div>
    </div>
);

const PerfilCapilar = ({ usuario }) => (
    <div style={{ backgroundColor: 'white', borderLeft: '5px solid #D5BDAF' }} className="rounded-xl p-8 shadow-lg">
        <h2 style={{ color: '#817773' }} className="text-2xl font-bold mb-6">Tu Perfil Capilar</h2>
        
        <div className="space-y-3">
            <AtributoRow label="Tipo de Cabello:" value={usuario?.tipo_cabello || '—'} />
            <AtributoRow label="Grosor:" value={usuario?.grosor_cabello || '—'} />
            <AtributoRow label="Porosidad:" value={usuario?.porosidad_cabello || '—'} />
            <AtributoRow label="Cuero Cabelludo:" value={usuario?.cuero_cabelludo || '—'} />
            <AtributoRow label="Estado General:" value={usuario?.estado_general || '—'} />
        </div>
    </div>
);

const DiagnosticoCard = ({ diagnostico, navigate }) => (
    <div style={{ backgroundColor: 'white', borderLeft: '5px solid #E3D5CA' }} className="rounded-xl p-8 shadow-lg mb-8">
        <h2 style={{ color: '#817773' }} className="text-2xl font-bold mb-6">Diagnóstico Personalizado</h2>
        
        {/* Mensaje Principal */}
        <div className="bg-gradient-to-r from-transparent to-transparent rounded-lg p-6 mb-4 border-l-4" style={{ borderColor: '#AB9A91', backgroundColor: '#F5EBE0' }}>
            <p style={{ color: '#817773' }} className="text-lg leading-relaxed font-medium">
                {diagnostico.mensaje_diagnostico}
            </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* Acción Recomendada */}
            <div style={{ backgroundColor: '#F5EBE0' }} className="rounded-lg p-4">
                <p style={{ color: '#AB9A91' }} className="text-sm font-semibold">Acción Sugerida:</p>
                <p style={{ color: '#817773' }} className="font-medium mt-2">{diagnostico.accion}</p>
            </div>

            {/* Puntaje */}
            {diagnostico.puntaje_final !== undefined && (
                <div style={{ backgroundColor: '#E3D5CA' }} className="rounded-lg p-4 flex items-center justify-center">
                    <div className="text-center">
                        <p style={{ color: '#817773' }} className="text-sm font-semibold mb-2">Puntaje de Salud</p>
                        <p style={{ color: '#817773' }} className="text-4xl font-bold">{diagnostico.puntaje_final}/10</p>
                    </div>
                </div>
            )}
        </div>

        {/* --- BLOQUE DE RUTINA SUGERIDA --- */}
        {diagnostico.rutina_nombre && (
            <div className="mt-6 p-6 rounded-xl border-2 border-dashed" style={{ borderColor: '#AB9A91', backgroundColor: '#FAF7F5' }}>
                <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                    <div>
                        <p className="text-sm font-bold uppercase tracking-wider" style={{ color: '#AB9A91' }}>
                             Recomendación para ti
                        </p>
                        <h3 className="text-xl font-bold" style={{ color: '#817773' }}>
                            {diagnostico.rutina_nombre}
                        </h3>
                        <p className="text-sm text-gray-500 mt-1">
                            Revisa los pasos y productos antes de adoptarla.
                        </p>
                    </div>
                    
                    <button
                        // Redirige a la vista de detalle (ej: /rutina/5)
                        onClick={() => navigate(`/rutina/${diagnostico.rutina_id}`)}
                        className="px-6 py-3 rounded-lg text-white font-bold shadow-md transform hover:scale-105 transition-all flex items-center gap-2"
                        style={{ background: 'linear-gradient(135deg, #AB9A91 0%, #817773 100%)' }}
                    >
                        <span></span> Ver detalle de rutina
                    </button>
                </div>
            </div>
        )}

        {/* --- BLOQUE DE SERVICIOS DISPONIBLES --- */}
        <div className="mt-6 p-6 rounded-xl border-2" style={{ borderColor: '#E3D5CA', backgroundColor: '#FAF7F5' }}>
            <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                <div>
                    <p className="text-sm font-bold uppercase tracking-wider" style={{ color: '#E3D5CA' }}>
                        ✨ Servicios Disponibles
                    </p>
                    <h3 className="text-xl font-bold" style={{ color: '#817773' }}>
                        Explora nuestros tratamientos
                    </h3>
                    <p className="text-sm text-gray-500 mt-1">
                        Descubre todos los servicios que ofrece nuestro salón.
                    </p>
                </div>
                
                <button
                    onClick={() => navigate('/catalogo-rutinas')}
                    className="px-6 py-3 rounded-lg text-white font-bold shadow-md transform hover:scale-105 transition-all flex items-center gap-2"
                    style={{ background: 'linear-gradient(135deg, #D5BDAF 0%, #AB9A91 100%)' }}
                >
                    <span></span> Ver catálogo
                </button>
            </div>
        </div>
    </div>
);


const InfoRow = ({ label, value }) => (
    <div>
        <p style={{ color: '#AB9A91' }} className="text-sm font-semibold">{label}</p>
        <p style={{ color: '#817773' }} className="text-lg font-bold mt-1">{value}</p>
    </div>
);

const AtributoRow = ({ label, value }) => (
    <div className="flex justify-between items-center p-3 rounded" style={{ backgroundColor: '#F5EBE0' }}>
        <span style={{ color: '#AB9A91' }} className="font-semibold">{label}</span>
        <span style={{ color: '#817773' }} className="font-bold">{value}</span>
    </div>
);

// ============================================================================
// INTERCEPTOR AXIOS - REFRESH TOKEN
// ============================================================================
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
                window.location.href = '/login';
            }
        }

        return Promise.reject(error);
    }
);

export default Perfil;
