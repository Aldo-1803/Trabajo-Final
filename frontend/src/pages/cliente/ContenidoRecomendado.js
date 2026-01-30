import React, { useState, useEffect } from 'react';
import axios from 'axios';
import TarjetaContenido from '../../components/TarjetaContenido';
import { contenidoEducativoAPI } from '../../api/contenidoEducativoAPI';

const ContenidoRecomendado = () => {
    const [recomendados, setRecomendados] = useState([]);
    const [diagnostico, setDiagnostico] = useState(null);
    const [cargando, setCargando] = useState(true);
    const [filtroTipo, setFiltroTipo] = useState('');
    const [error, setError] = useState(null);

    // Cargar diagnóstico y recomendaciones
    const cargarRecomendados = async () => {
        try {
            setCargando(true);
            setError(null);

            // Construir parámetros
            const params = {};
            if (filtroTipo) params.tipo = filtroTipo;

            // Usar el servicio API centralizado
            const data = await contenidoEducativoAPI.getPublicados(params);
            setRecomendados(Array.isArray(data) ? data : []);

            // Obtener diagnóstico si existe (esto podrías agregarlo al servicio API también)
            try {
                const token = localStorage.getItem('access_token');
                const diagResponse = await axios.get(
                    'http://127.0.0.1:8000/api/diagnosticos/?ordering=-fecha',
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
                
                const diagnosticos = diagResponse.data.results || diagResponse.data;
                if (diagnosticos && diagnosticos.length > 0) {
                    setDiagnostico(diagnosticos[0]);
                }
            } catch (err) {
                console.log('No hay diagnóstico disponible');
            }
        } catch (error) {
            console.error('Error cargando recomendados:', error);
            setError('Error al cargar contenido recomendado. Intenta nuevamente.');
            setRecomendados([]);
        } finally {
            setCargando(false);
        }
    };

    useEffect(() => {
        cargarRecomendados();
    }, [filtroTipo]);

    // Actualizar al guardar
    const handleGuardarCambio = () => {
        cargarRecomendados();
    };

    return (
        <div className="max-w-7xl mx-auto px-6 py-8">
            {/* HEADER */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold mb-2" style={{ color: '#817773' }}>
                    ✨ Contenido Recomendado para Ti
                </h1>
                <p style={{ color: '#8B8682' }}>
                    Artículos seleccionados según tu tipo de cabello y necesidades
                </p>
            </div>

            {/* DIAGNÓSTICO ACTUAL */}
            {diagnostico && (
                <div 
                    className="rounded-lg shadow p-6 mb-6 text-white"
                    style={{ background: 'linear-gradient(135deg, #2E7D2E, #3A9A3A)' }}
                >
                    <h3 className="text-lg font-bold mb-4">🔍 Tu Diagnóstico Actual</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                        <div>
                            <p className="opacity-90">Estado General</p>
                            <p className="text-xl font-bold">
                                {diagnostico.estado_general?.nombre || 'N/A'}
                            </p>
                        </div>
                        <div>
                            <p className="opacity-90">Tipo de Cabello</p>
                            <p className="text-xl font-bold">
                                {diagnostico.tipo_cabello?.nombre || 'N/A'}
                            </p>
                        </div>
                        {diagnostico.porosidad && (
                            <div>
                                <p className="opacity-90">Porosidad</p>
                                <p className="text-xl font-bold">
                                    {diagnostico.porosidad?.nombre || 'N/A'}
                                </p>
                            </div>
                        )}
                        {diagnostico.sensibilidad_cuero_cabelludo && (
                            <div>
                                <p className="opacity-90">Sensibilidad</p>
                                <p className="text-xl font-bold">
                                    {diagnostico.sensibilidad_cuero_cabelludo?.nombre || 'N/A'}
                                </p>
                            </div>
                        )}
                    </div>
                    <p className="text-xs opacity-75 mt-4">
                        📅 Diagnóstico del {new Date(diagnostico.fecha).toLocaleDateString('es-AR')}
                    </p>
                </div>
            )}

            {/* INFO SIN DIAGNÓSTICO */}
            {!diagnostico && !cargando && (
                <div 
                    className="rounded-lg shadow p-6 mb-6 border-l-4"
                    style={{ borderColor: '#C73E3E' }}
                >
                    <p style={{ color: '#8B8682' }}>
                        💡 Completa tu diagnóstico capilar para obtener recomendaciones personalizadas específicas para ti
                    </p>
                </div>
            )}

            {/* FILTRO POR TIPO */}
            <div className="bg-white rounded-lg shadow p-4 mb-6">
                <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                    Filtrar por Tipo de Contenido
                </label>
                <select
                    value={filtroTipo}
                    onChange={(e) => setFiltroTipo(e.target.value)}
                    className="w-full p-2 border rounded-lg outline-none"
                    style={{ borderColor: '#D5D1CC' }}
                >
                    <option value="">Todos</option>
                    <option value="IMAGEN">📷 Imagen</option>
                    <option value="VIDEO">🎥 Video</option>
                    <option value="TEXTO">📝 Texto</option>
                </select>
            </div>

            {/* LISTA DE RECOMENDADOS */}
            {cargando ? (
                <div className="flex justify-center items-center py-16">
                    <div className="animate-spin">
                        <div className="w-12 h-12 border-4 border-gray-300 border-t-amber-600 rounded-full"></div>
                    </div>
                </div>
            ) : recomendados.length === 0 ? (
                <div className="text-center py-16 bg-white rounded-lg shadow">
                    <p className="text-lg mb-4" style={{ color: '#8B8682' }}>
                        📚 Explora nuestro centro educativo
                    </p>
                    <p style={{ color: '#ABA89E' }}>
                        No hay artículos disponibles en este momento, pero puedes ver todo nuestro contenido
                    </p>
                </div>
            ) : (
                <>
                    <div className="mb-4 text-center">
                        <p className="text-sm" style={{ color: '#8B8682' }}>
                            ✨ {recomendados.length} artículo{recomendados.length !== 1 ? 's' : ''} recomendado{recomendados.length !== 1 ? 's' : ''} para ti
                        </p>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {recomendados.map(contenido => (
                            <TarjetaContenido
                                key={contenido.id}
                                contenido={contenido}
                                esPropio={false}
                                onGuardar={handleGuardarCambio}
                                onLike={handleGuardarCambio}
                            />
                        ))}
                    </div>
                </>
            )}

            {/* BOTÓN CTA */}
            {recomendados.length > 0 && (
                <div className="text-center mt-8">
                    <a
                        href="/cliente/contenido-publico"
                        className="inline-block px-6 py-3 rounded-lg text-white font-bold"
                        style={{ background: '#2E7D2E' }}
                    >
                        Ver Todo el Centro Educativo →
                    </a>
                </div>
            )}
        </div>
    );
};

export default ContenidoRecomendado;
