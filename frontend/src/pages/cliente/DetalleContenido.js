import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { contenidoEducativoAPI } from '../../api/contenidoEducativoAPI';
import {
    IconBookmark,
    IconCalendar,
    IconCheckCircle,
    IconHeart,
    IconImage,
    IconInfo,
    IconTag,
    IconText,
    IconUser,
    IconVideo
} from '../../components/common/Icons';

const DetalleContenido = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const [contenido, setContenido] = useState(null);
    const [cargando, setCargando] = useState(true);
    const [meGusta, setMeGusta] = useState(false);
    const [guardado, setGuardado] = useState(false);
    const [totalLikes, setTotalLikes] = useState(0);
    const [cargandoInteracciones, setCargandoInteracciones] = useState(false);
    const [error, setError] = useState(null);

    // Cargar contenido
    useEffect(() => {
        const cargarContenido = async () => {
            try {
                setCargando(true);
                setError(null);
                const data = await contenidoEducativoAPI.getById(parseInt(id));
                setContenido(data);
                setMeGusta(data.ya_le_gusta || false);
                setGuardado(data.ya_esta_guardado || false);
                setTotalLikes(data.total_likes || 0);
            } catch (error) {
                console.error('Error cargando contenido:', error);
                setError('No se pudo cargar el contenido. Intenta nuevamente.');
            } finally {
                setCargando(false);
            }
        };

        if (id) {
            cargarContenido();
        }
    }, [id]);

    // Toggle like
    const handleToggleLike = async () => {
        if (!contenido || cargandoInteracciones) return;
        try {
            setCargandoInteracciones(true);
            const response = await contenidoEducativoAPI.like(contenido.id);
            setMeGusta(!meGusta);
            setTotalLikes(response.total_likes || 0);
        } catch (error) {
            console.error('Error en like:', error);
        } finally {
            setCargandoInteracciones(false);
        }
    };

    // Toggle guardar
    const handleToggleGuardar = async () => {
        if (!contenido || cargandoInteracciones) return;
        try {
            setCargandoInteracciones(true);
            await contenidoEducativoAPI.guardar(contenido.id);
            setGuardado(!guardado);
        } catch (error) {
            console.error('Error en guardar:', error);
        } finally {
            setCargandoInteracciones(false);
        }
    };

    if (cargando) {
        return (
            <div className="flex justify-center items-center h-screen">
                <div className="animate-spin">
                    <div className="w-12 h-12 border-4 border-gray-300 border-t-amber-600 rounded-full"></div>
                </div>
            </div>
        );
    }

    if (!contenido) {
        return (
            <div className="max-w-4xl mx-auto px-6 py-8 text-center">
                <p className="text-lg mb-4" style={{ color: '#8B8682' }}>
                    <span className="inline-flex items-center gap-2">
                        <IconInfo className="h-5 w-5" /> Contenido no encontrado
                    </span>
                </p>
                <button
                    onClick={() => navigate(-1)}
                    className="px-4 py-2 rounded-lg text-white"
                    style={{ background: '#817773' }}
                >
                    ← Volver
                </button>
            </div>
        );
    }

    // Renderizar contenido según tipo
    const renderContenido = () => {
        switch (contenido.tipo) {
            case 'IMAGEN':
                return (
                    <img
                        src={contenido.multimedia_url}
                        alt={contenido.titulo}
                        className="w-full rounded-lg mb-6 object-cover max-h-96"
                        onError={(e) => {
                            e.target.src = 'https://via.placeholder.com/600x400?text=Imagen+no+disponible';
                        }}
                    />
                );
            case 'VIDEO':
                return (
                    <iframe
                        src={contenido.multimedia_url}
                        title={contenido.titulo}
                        className="w-full rounded-lg mb-6 aspect-video"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                    ></iframe>
                );
            case 'TEXTO':
                return null;
            default:
                return null;
        }
    };

    return (
        <div className="max-w-4xl mx-auto px-6 py-8">
            {/* BOTÓN VOLVER */}
            <button
                onClick={() => navigate(-1)}
                className="mb-6 px-4 py-2 rounded-lg flex items-center gap-2"
                style={{ background: '#E8DCC4', color: '#817773' }}
            >
                ← Volver
            </button>

            {/* HEADER */}
            <div className="bg-white rounded-lg shadow p-6 mb-6">
                {/* Estado */}
                <div className="mb-4">
                    <span 
                        className="px-3 py-1 rounded-full text-sm font-bold text-white"
                        style={{ 
                            background: contenido.estado === 'PUBLICADO' ? '#2E7D2E' : '#ABA89E'
                        }}
                    >
                        {contenido.estado === 'PUBLICADO' ? (
                            <span className="inline-flex items-center gap-2">
                                <IconCheckCircle className="h-4 w-4" /> Publicado
                            </span>
                        ) : (
                            contenido.estado
                        )}
                    </span>
                </div>

                {/* Título */}
                <h1 className="text-4xl font-bold mb-4" style={{ color: '#817773' }}>
                    {contenido.titulo}
                </h1>

                {/* Metadatos */}
                <div className="flex flex-wrap items-center gap-4 text-sm mb-6" style={{ color: '#8B8682' }}>
                    <div className="flex items-center gap-2">
                        <IconUser className="h-4 w-4" />
                        <span className="font-semibold">
                            {contenido.autor?.nombre} {contenido.autor?.apellido}
                        </span>
                        {contenido.autor?.rol && (
                            <span className="text-xs opacity-75">({contenido.autor.rol})</span>
                        )}
                    </div>
                    <div>•</div>
                    <div className="flex items-center gap-1">
                        <IconCalendar className="h-4 w-4" /> {new Date(contenido.fecha_publicacion).toLocaleDateString('es-AR')}
                    </div>
                    <div>•</div>
                    <div className="flex items-center gap-1">
                        <IconTag className="h-4 w-4" />
                        {contenido.tipo === 'IMAGEN' ? (
                            <span className="inline-flex items-center gap-1">
                                <IconImage className="h-4 w-4" /> Imagen
                            </span>
                        ) : contenido.tipo === 'VIDEO' ? (
                            <span className="inline-flex items-center gap-1">
                                <IconVideo className="h-4 w-4" /> Video
                            </span>
                        ) : (
                            <span className="inline-flex items-center gap-1">
                                <IconText className="h-4 w-4" /> Texto
                            </span>
                        )}
                    </div>
                </div>

                {/* Descripción */}
                {contenido.descripcion && (
                    <p className="text-lg mb-6" style={{ color: '#8B8682' }}>
                        {contenido.descripcion}
                    </p>
                )}

                {/* Tags */}
                {contenido.tags && contenido.tags.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-6">
                        {contenido.tags.split(',').map((tag, idx) => (
                            <span
                                key={idx}
                                className="px-3 py-1 rounded-full text-sm"
                                style={{ background: '#E8DCC4', color: '#817773' }}
                            >
                                #{tag.trim()}
                            </span>
                        ))}
                    </div>
                )}

                {/* Botones de interacción */}
                <div className="flex gap-4 flex-wrap">
                    <button
                        onClick={handleToggleLike}
                        disabled={cargandoInteracciones}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all"
                        style={{
                            background: meGusta ? '#C73E3E' : '#E8DCC4',
                            color: meGusta ? 'white' : '#817773',
                            opacity: cargandoInteracciones ? 0.6 : 1
                        }}
                    >
                        <IconHeart className="h-4 w-4" /> {totalLikes} Me Gusta
                    </button>

                    <button
                        onClick={handleToggleGuardar}
                        disabled={cargandoInteracciones}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all"
                        style={{
                            background: guardado ? '#2E7D2E' : '#E8DCC4',
                            color: guardado ? 'white' : '#817773',
                            opacity: cargandoInteracciones ? 0.6 : 1
                        }}
                    >
                        <IconBookmark className="h-4 w-4" /> {guardado ? 'Guardado' : 'Guardar'}
                    </button>
                </div>
            </div>

            {/* CONTENIDO PRINCIPAL */}
            <div className="bg-white rounded-lg shadow p-8">
                {/* Multimedia */}
                {renderContenido()}

                {/* Texto */}
                {contenido.contenido_texto && (
                    <div 
                        className="prose max-w-none"
                        style={{ color: '#2E2E2E' }}
                    >
                        <div className="whitespace-pre-wrap text-lg leading-relaxed">
                            {contenido.contenido_texto}
                        </div>
                    </div>
                )}
            </div>

            {/* ESTADÍSTICAS */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-8">
                <div className="bg-white rounded-lg shadow p-4 text-center">
                    <p style={{ color: '#8B8682' }} className="text-sm">Me Gusta</p>
                    <p className="text-2xl font-bold" style={{ color: '#C73E3E' }}>
                        <span className="inline-flex items-center gap-2">
                            <IconHeart className="h-5 w-5" /> {totalLikes}
                        </span>
                    </p>
                </div>
                <div className="bg-white rounded-lg shadow p-4 text-center">
                    <p style={{ color: '#8B8682' }} className="text-sm">Guardados</p>
                    <p className="text-2xl font-bold" style={{ color: '#2E7D2E' }}>
                        <span className="inline-flex items-center gap-2">
                            <IconBookmark className="h-5 w-5" /> {contenido.total_guardados || 0}
                        </span>
                    </p>
                </div>
                <div className="bg-white rounded-lg shadow p-4 text-center">
                    <p style={{ color: '#8B8682' }} className="text-sm">Tipo</p>
                    <p className="text-2xl font-bold" style={{ color: '#817773' }}>
                        {contenido.tipo === 'IMAGEN' ? (
                            <IconImage className="h-6 w-6" />
                        ) : contenido.tipo === 'VIDEO' ? (
                            <IconVideo className="h-6 w-6" />
                        ) : (
                            <IconText className="h-6 w-6" />
                        )}
                    </p>
                </div>
            </div>
        </div>
    );
};

export default DetalleContenido;
