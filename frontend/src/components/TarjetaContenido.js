import React, { useState } from 'react';
import { contenidoEducativoAPI } from '../api/contenidoEducativoAPI';

const TarjetaContenido = ({ 
    contenido, 
    onEditar, 
    onEliminar,
    esPropio = false,
    onLike,
    onGuardar 
}) => {
    const [cargando, setCargando] = useState(false);
    const [meGusta, setMeGusta] = useState(contenido.ya_le_gusta || false);
    const [guardado, setGuardado] = useState(contenido.ya_esta_guardado || false);
    const [totalLikes, setTotalLikes] = useState(contenido.total_likes || 0);

    // Dar/quitar like
    const handleToggleLike = async () => {
        try {
            setCargando(true);
            const response = await contenidoEducativoAPI.like(contenido.id);
            setMeGusta(!meGusta);
            setTotalLikes(response.total_likes || totalLikes + (meGusta ? -1 : 1));
            if (onLike) onLike();
        } catch (err) {
            console.error('Error al dar like:', err);
        } finally {
            setCargando(false);
        }
    };

    // Guardar/quitar de guardados
    const handleToggleGuardar = async () => {
        try {
            setCargando(true);
            await contenidoEducativoAPI.guardar(contenido.id);
            setGuardado(!guardado);
            if (onGuardar) onGuardar();
        } catch (err) {
            console.error('Error al guardar:', err);
        } finally {
            setCargando(false);
        }
    };

    // Obtener color para badge de tipo
    const getBadgeColor = (tipo) => {
        const colores = {
            'articulo': { bg: '#E3F2FD', text: '#1565C0' },
            'video': { bg: '#FCE4EC', text: '#C2185B' },
            'tutorial': { bg: '#E8F5E9', text: '#2E7D32' },
            'consejo': { bg: '#FFF3E0', text: '#E65100' },
        };
        return colores[(tipo || 'articulo').toLowerCase()] || { bg: '#F5F5F5', text: '#616161' };
    };

    return (
        <div className="bg-white rounded-lg shadow-md overflow-hidden border" style={{ borderColor: '#E8DCC4' }}>
            {/* HEADER CON AUTOR Y FECHA */}
            <div className="p-4 border-b" style={{ borderColor: '#E8DCC4' }}>
                <div className="flex justify-between items-start">
                    <div>
                        <h3 className="text-sm font-bold" style={{ color: '#817773' }}>
                            {contenido.autor.nombre} {contenido.autor.apellido}
                        </h3>
                        <p className="text-xs" style={{ color: '#8B8682' }}>
                            {new Date(contenido.fecha_publicacion).toLocaleDateString('es-AR')}
                        </p>
                    </div>
                    <span className="inline-block px-2 py-1 text-xs rounded-full" style={{
                        backgroundColor: contenido.estado === 'PUBLICADO' ? '#E8F5E8' : '#FFF3CD',
                        color: contenido.estado === 'PUBLICADO' ? '#2E7D2E' : '#856404'
                    }}>
                        {contenido.estado}
                    </span>
                </div>
            </div>

            {/* IMAGEN/VIDEO */}
            {contenido.multimedia_url && contenido.tipo !== 'TEXTO' && (
                <div className="w-full h-48 overflow-hidden" style={{ backgroundColor: '#F5F5EB' }}>
                    {contenido.tipo === 'IMAGEN' ? (
                        <img
                            src={contenido.multimedia_url}
                            alt={contenido.titulo}
                            className="w-full h-full object-cover hover:scale-105 transition-transform"
                        />
                    ) : (
                        <div className="w-full h-full flex items-center justify-center">
                            <iframe
                                width="100%"
                                height="100%"
                                src={contenido.multimedia_url}
                                frameBorder="0"
                                allowFullScreen
                                title={contenido.titulo}
                            ></iframe>
                        </div>
                    )}
                </div>
            )}

            {/* CONTENIDO */}
            <div className="p-4">
                {/* TÍTULO */}
                <h2 className="text-lg font-bold mb-2" style={{ color: '#817773' }}>
                    {contenido.titulo}
                </h2>

                {/* DESCRIPCIÓN */}
                <p className="text-sm mb-3 line-clamp-2" style={{ color: '#8B8682' }}>
                    {contenido.descripcion}
                </p>

                {/* TAGS */}
                {contenido.tags && (
                    <div className="mb-3 flex flex-wrap gap-2">
                        {contenido.tags.split(',').map((tag, idx) => (
                            <span 
                                key={idx}
                                className="text-xs px-2 py-1 rounded-full" 
                                style={{ backgroundColor: '#E8DCC4', color: '#817773' }}
                            >
                                #{tag.trim()}
                            </span>
                        ))}
                    </div>
                )}

                {/* STATS */}
                <div className="flex gap-4 mb-4 text-xs" style={{ color: '#8B8682' }}>
                    <span>❤️ {totalLikes} likes</span>
                    <span>🔖 {contenido.total_guardados} guardados</span>
                </div>

                {/* ACCIONES */}
                <div className="flex gap-2">
                    {!esPropio && (
                        <>
                            <button
                                onClick={handleToggleLike}
                                disabled={cargando}
                                className="flex-1 py-2 px-3 rounded-lg transition text-sm font-bold"
                                style={{
                                    backgroundColor: meGusta ? '#2E7D2E' : '#E8DCC4',
                                    color: meGusta ? '#fff' : '#817773'
                                }}
                                onMouseEnter={(e) => {
                                    if (!meGusta) e.target.style.backgroundColor = '#D5C4B0';
                                }}
                                onMouseLeave={(e) => {
                                    if (!meGusta) e.target.style.backgroundColor = '#E8DCC4';
                                }}
                            >
                                {meGusta ? '❤️ Liked' : '🤍 Like'}
                            </button>

                            <button
                                onClick={handleToggleGuardar}
                                disabled={cargando}
                                className="flex-1 py-2 px-3 rounded-lg transition text-sm font-bold"
                                style={{
                                    backgroundColor: guardado ? '#817773' : '#F5F5EB',
                                    color: guardado ? '#fff' : '#817773'
                                }}
                                onMouseEnter={(e) => {
                                    if (!guardado) e.target.style.backgroundColor = '#E8DCC4';
                                }}
                                onMouseLeave={(e) => {
                                    if (!guardado) e.target.style.backgroundColor = '#F5F5EB';
                                }}
                            >
                                {guardado ? '🔖 Guardado' : '📌 Guardar'}
                            </button>
                        </>
                    )}

                    {esPropio && (
                        <>
                            <button
                                onClick={() => onEditar(contenido)}
                                className="flex-1 py-2 px-3 rounded-lg font-bold text-sm transition"
                                style={{ backgroundColor: '#817773', color: '#fff' }}
                                onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                                onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                            >
                                ✏️ Editar
                            </button>

                            <button
                                onClick={() => onEliminar(contenido.id)}
                                className="flex-1 py-2 px-3 rounded-lg font-bold text-sm transition"
                                style={{ backgroundColor: '#C73E3E', color: '#fff' }}
                                onMouseEnter={(e) => e.target.style.backgroundColor = '#A03030'}
                                onMouseLeave={(e) => e.target.style.backgroundColor = '#C73E3E'}
                            >
                                🗑️ Eliminar
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default TarjetaContenido;
