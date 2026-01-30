import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import FichaRecomendacion from '../../components/FichaRecomendacion';
import PromocionesCarte from '../../components/PromocionesCarte';

// ============================================================================
// COMPONENTE PRINCIPAL
// ============================================================================

const Perfil = () => {
    // ========================================================================
    // ESTADO
    // ========================================================================
    const [usuario, setUsuario] = useState(null);
    const [diagnostico, setDiagnostico] = useState(null);
    const [notificaciones, setNotificaciones] = useState([]);
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

            try {
                const notifResponse = await axios.get('/api/gestion/notificaciones/', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                setNotificaciones(notifResponse.data);
            } catch (notifErr) {
                console.error('Error al cargar notificaciones:', notifErr);
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

                {/* BOTONES DE ACCESO RÁPIDO */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                    <button
                        onClick={() => navigate('/catalogo-productos')}
                        className="px-6 py-4 rounded-lg font-bold text-white shadow-md transition-all duration-200 hover:shadow-lg"
                        style={{ backgroundColor: '#817773' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                    >
                        Ver Catálogo de Productos
                    </button>
                    <button
                        onClick={() => navigate('/catalogo-rutinas')}
                        className="px-6 py-4 rounded-lg font-bold text-white shadow-md transition-all duration-200 hover:shadow-lg"
                        style={{ backgroundColor: '#AB9A91' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                    >
                        Explorar Rutinas
                    </button>
                </div>

                {/* GRID DE TARJETAS */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                    <InformacionPersonal usuario={usuario} navigate={navigate} />
                    <PerfilCapilar usuario={usuario} />
                </div>

                {/* DIAGNÓSTICO */}
                {diagnostico && <DiagnosticoCard diagnostico={diagnostico} notificaciones={notificaciones} navigate={navigate} />}
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

const InformacionPersonal = ({ usuario, navigate }) => (
    <div style={{ backgroundColor: 'white', borderLeft: '5px solid #AB9A91' }} className="rounded-xl p-8 shadow-lg">
        <div className="flex justify-between items-center mb-6">
            <h2 style={{ color: '#817773' }} className="text-2xl font-bold">📋 Información Personal</h2>
            <button
                onClick={() => navigate('/editar-perfil')}
                className="px-4 py-2 rounded-lg text-white font-bold shadow-md transform hover:scale-105 transition-all"
                style={{ background: 'linear-gradient(135deg, #AB9A91 0%, #817773 100%)' }}
            >
                ✏️ Editar
            </button>
        </div>
        
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

const DiagnosticoCard = ({ diagnostico, notificaciones, navigate }) => {
    // Obtener la notificación de turno recomendado más reciente
    const turnoNotificacion = notificaciones && notificaciones.length > 0 
        ? notificaciones.find(n => n.tipo === 'alerta' && n.datos_extra?.fecha && n.datos_extra?.hora)
        : null;

    return (
        <div style={{ backgroundColor: 'white', borderLeft: '5px solid #E3D5CA' }} className="rounded-xl p-8 shadow-lg mb-8">
            <h2 style={{ color: '#817773' }} className="text-2xl font-bold mb-6">📋 Diagnóstico Personalizado</h2>
            
            {/* Mensaje Principal - Análisis Profesional */}
            <div className="bg-gradient-to-r from-transparent to-transparent rounded-lg p-6 mb-6 border-l-4" style={{ borderColor: '#AB9A91', backgroundColor: '#F5EBE0' }}>
                <h3 style={{ color: '#817773' }} className="text-lg font-bold mb-2">Tu Análisis Capilar</h3>
                <p style={{ color: '#817773' }} className="text-base leading-relaxed">
                    {diagnostico.mensaje_diagnostico || 'Análisis en proceso...'}
                </p>
            </div>

            {/* FICHA DE RECOMENDACIÓN - Componente Reutilizable */}
            <FichaRecomendacion 
                diagnostico={diagnostico} 
                turnoNotificacion={turnoNotificacion} 
                navigate={navigate}
            />

            {/* PROMOCIONES EXCLUSIVAS - Widget P3 */}
            <PromocionesCarte />

            {/* --- BLOQUE DE RUTINA SUGERIDA --- */}
            {diagnostico.rutina_asignada_nombre && (
                <div className="mt-6 p-6 rounded-xl border-2 border-dashed" style={{ borderColor: '#AB9A91', backgroundColor: '#FAF7F5' }}>
                    <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                        <div>
                            <p className="text-sm font-bold uppercase tracking-wider" style={{ color: '#AB9A91' }}>
                                Rutina Recomendada
                            </p>
                            <h3 className="text-xl font-bold" style={{ color: '#817773' }}>
                                {diagnostico.rutina_asignada_nombre}
                            </h3>
                            <p className="text-sm text-gray-500 mt-1">
                                Revisa los pasos y productos antes de adoptarla.
                            </p>
                        </div>
                        
                        <button
                            onClick={() => navigate(`/rutina/${diagnostico.rutina_asignada_id}`)}
                            className="px-6 py-3 rounded-lg text-white font-bold shadow-md transform hover:scale-105 transition-all flex items-center gap-2"
                            style={{ background: 'linear-gradient(135deg, #AB9A91 0%, #817773 100%)' }}
                        >
                            <span>📖</span> Ver detalle de rutina
                        </button>
                    </div>
                </div>
            )}

            {/* --- BLOQUE DE TURNO RECOMENDADO --- */}
            {turnoNotificacion && turnoNotificacion.datos_extra && (
                <div className="mt-6 p-6 rounded-xl border-2 border-dashed" style={{ borderColor: '#E3D5CA', backgroundColor: '#FAF7F5' }}>
                    <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                        <div>
                            <p className="text-sm font-bold uppercase tracking-wider" style={{ color: '#E3D5CA' }}>
                                Turno Disponible
                            </p>
                            <h3 className="text-lg font-bold" style={{ color: '#817773' }}>
                                {turnoNotificacion.datos_extra.fecha} a las {turnoNotificacion.datos_extra.hora}
                            </h3>
                            <p className="text-sm text-gray-500 mt-1">
                                Hemos reservado un espacio para ti en nuestro salón.
                            </p>
                        </div>
                        
                        <button
                            onClick={() => navigate('/mis-turnos')}
                            className="px-6 py-3 rounded-lg text-white font-bold shadow-md transform hover:scale-105 transition-all flex items-center gap-2"
                            style={{ background: 'linear-gradient(135deg, #E3D5CA 0%, #D5BDAF 100%)' }}
                        >
                            <span>✨</span> Agendar Turno
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
                        onClick={() => navigate('/catalogo-servicios')}
                        className="px-6 py-3 rounded-lg text-white font-bold shadow-md transform hover:scale-105 transition-all flex items-center gap-2"
                        style={{ background: 'linear-gradient(135deg, #D5BDAF 0%, #AB9A91 100%)' }}
                    >
                        <span>🛍️</span> Ver catálogo
                    </button>
                </div>
            </div>
        </div>
    );
};


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

export default Perfil;
