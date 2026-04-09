import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { IconCheckCircle, IconPencil, IconPlus, IconX } from './common/Icons';

const PanelEditorContenido = ({ contenidoEditar = null, onGuardar, onCancelar }) => {
    const [formulario, setFormulario] = useState({
        titulo: '',
        descripcion: '',
        contenido_texto: '',
        multimedia_url: '',
        tipo: 'TEXTO',
        tags: '',
        estado: 'BORRADOR'
    });

    const [cargando, setCargando] = useState(false);
    const [errores, setErrores] = useState({});
    const [preview, setPreview] = useState('');

    // Cargar datos si está editando
    useEffect(() => {
        if (contenidoEditar) {
            setFormulario({
                titulo: contenidoEditar.titulo,
                descripcion: contenidoEditar.descripcion,
                contenido_texto: contenidoEditar.contenido_texto,
                multimedia_url: contenidoEditar.multimedia_url || '',
                tipo: contenidoEditar.tipo,
                tags: contenidoEditar.tags || '',
                estado: contenidoEditar.estado
            });
            if (contenidoEditar.multimedia_url) {
                setPreview(contenidoEditar.multimedia_url);
            }
        }
    }, [contenidoEditar]);

    // Manejar cambios
    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormulario(prev => ({
            ...prev,
            [name]: value
        }));
        // Limpiar error del campo
        if (errores[name]) {
            setErrores(prev => {
                const newErrores = { ...prev };
                delete newErrores[name];
                return newErrores;
            });
        }
    };

    // Validar formulario
    const validar = () => {
        const newErrores = {};
        
        if (!formulario.titulo.trim()) newErrores.titulo = 'El título es requerido';
        if (!formulario.descripcion.trim()) newErrores.descripcion = 'La descripción es requerida';
        if (!formulario.contenido_texto.trim()) newErrores.contenido_texto = 'El contenido es requerido';
        
        if (formulario.tipo !== 'TEXTO' && !formulario.multimedia_url.trim()) {
            newErrores.multimedia_url = 'La URL de multimedia es requerida para imagen o video';
        }
        if (formulario.tipo === 'TEXTO' && formulario.multimedia_url.trim()) {
            newErrores.multimedia_url = 'No incluir multimedia en contenido de TEXTO';
        }

        setErrores(newErrores);
        return Object.keys(newErrores).length === 0;
    };

    // Guardar
    const handleSubmit = async (e) => {
        e.preventDefault();

        if (!validar()) return;

        try {
            setCargando(true);
            const token = localStorage.getItem('token');

            const config = {
                headers: { 'Authorization': `Bearer ${token}` }
            };

            if (contenidoEditar) {
                // Editar
                await axios.put(
                    `http://localhost:8000/api/gestion/contenido-educativo/${contenidoEditar.id}/`,
                    formulario,
                    config
                );
            } else {
                // Crear
                await axios.post(
                    'http://localhost:8000/api/gestion/contenido-educativo/',
                    formulario,
                    config
                );
            }

            // Notificar al padre
            onGuardar();
            
            // Resetear formulario
            setFormulario({
                titulo: '',
                descripcion: '',
                contenido_texto: '',
                multimedia_url: '',
                tipo: 'IMAGEN',
                tags: '',
                estado: 'BORRADOR'
            });
            setPreview('');
        } catch (error) {
            console.error('Error guardando:', error);
            setErrores({ general: 'Error al guardar el contenido' });
        } finally {
            setCargando(false);
        }
    };

    return (
        <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
            <h2 className="text-2xl font-bold mb-6" style={{ color: '#817773' }}>
                {contenidoEditar ? (
                    <span className="inline-flex items-center gap-2">
                        <IconPencil className="h-5 w-5" /> Editar Contenido
                    </span>
                ) : (
                    <span className="inline-flex items-center gap-2">
                        <IconPlus className="h-5 w-5" /> Crear Contenido Educativo
                    </span>
                )}
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
                {/* ERROR GENERAL */}
                {errores.general && (
                    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
                        {errores.general}
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* TIPO DE CONTENIDO */}
                    <div>
                        <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                            Tipo de Contenido
                        </label>
                        <select
                            name="tipo"
                            value={formulario.tipo}
                            onChange={handleChange}
                            className="w-full p-2 border rounded-lg outline-none"
                            style={{ borderColor: '#D5D1CC' }}
                        >
                            <option value="IMAGEN">Imagen</option>
                            <option value="VIDEO">Video</option>
                            <option value="TEXTO">Texto</option>
                        </select>
                    </div>

                    {/* ESTADO */}
                    <div>
                        <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                            Estado
                        </label>
                        <select
                            name="estado"
                            value={formulario.estado}
                            onChange={handleChange}
                            className="w-full p-2 border rounded-lg outline-none"
                            style={{ borderColor: '#D5D1CC' }}
                        >
                            <option value="BORRADOR">Borrador</option>
                            <option value="PUBLICADO">Publicado</option>
                            <option value="ARCHIVADO">Archivado</option>
                        </select>
                    </div>
                </div>

                {/* TÍTULO */}
                <div>
                    <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                        Título *
                    </label>
                    <input
                        type="text"
                        name="titulo"
                        value={formulario.titulo}
                        onChange={handleChange}
                        placeholder="Ej: Tips para cabello dañado"
                        className="w-full p-2 border rounded-lg outline-none"
                        style={{ borderColor: errores.titulo ? '#C73E3E' : '#D5D1CC' }}
                    />
                    {errores.titulo && <p className="text-red-600 text-xs mt-1">{errores.titulo}</p>}
                </div>

                {/* DESCRIPCIÓN */}
                <div>
                    <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                        Descripción Breve *
                    </label>
                    <input
                        type="text"
                        name="descripcion"
                        value={formulario.descripcion}
                        onChange={handleChange}
                        placeholder="Resumen que aparecerá en la lista (máx 500 caracteres)"
                        maxLength="500"
                        className="w-full p-2 border rounded-lg outline-none"
                        style={{ borderColor: errores.descripcion ? '#C73E3E' : '#D5D1CC' }}
                    />
                    <p className="text-xs mt-1" style={{ color: '#8B8682' }}>
                        {formulario.descripcion.length}/500
                    </p>
                    {errores.descripcion && <p className="text-red-600 text-xs mt-1">{errores.descripcion}</p>}
                </div>

                {/* CONTENIDO TEXTO */}
                <div>
                    <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                        Contenido Completo *
                    </label>
                    <textarea
                        name="contenido_texto"
                        value={formulario.contenido_texto}
                        onChange={handleChange}
                        placeholder="Escribe el contenido educativo completo..."
                        rows="6"
                        className="w-full p-3 border rounded-lg outline-none resize-none"
                        style={{ borderColor: errores.contenido_texto ? '#C73E3E' : '#D5D1CC' }}
                    />
                    {errores.contenido_texto && <p className="text-red-600 text-xs mt-1">{errores.contenido_texto}</p>}
                </div>

                {/* URL MULTIMEDIA */}
                {formulario.tipo !== 'TEXTO' && (
                    <div>
                        <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                            URL de Multimedia ({formulario.tipo === 'IMAGEN' ? 'Imagen' : 'Video'}) *
                        </label>
                        <input
                            type="url"
                            name="multimedia_url"
                            value={formulario.multimedia_url}
                            onChange={handleChange}
                            placeholder={
                                formulario.tipo === 'IMAGEN'
                                    ? 'https://ejemplo.com/imagen.jpg'
                                    : 'https://youtube.com/embed/... o https://vimeo.com/...'
                            }
                            className="w-full p-2 border rounded-lg outline-none"
                            style={{ borderColor: errores.multimedia_url ? '#C73E3E' : '#D5D1CC' }}
                        />
                        {errores.multimedia_url && <p className="text-red-600 text-xs mt-1">{errores.multimedia_url}</p>}

                        {/* PREVIEW */}
                        {formulario.multimedia_url && (
                            <div className="mt-3 p-3 bg-gray-100 rounded-lg">
                                {formulario.tipo === 'IMAGEN' ? (
                                    <>
                                        <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Preview:</p>
                                        <img
                                            src={formulario.multimedia_url}
                                            alt="preview"
                                            className="max-h-48 rounded"
                                            onError={() => setErrores(prev => ({
                                                ...prev,
                                                multimedia_url: 'No se pudo cargar la imagen'
                                            }))}
                                        />
                                    </>
                                ) : (
                                    <iframe
                                        width="100%"
                                        height="200"
                                        src={formulario.multimedia_url}
                                        frameBorder="0"
                                        allowFullScreen
                                        title="preview"
                                    ></iframe>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* TAGS */}
                <div>
                    <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                        Tags (opcional)
                    </label>
                    <input
                        type="text"
                        name="tags"
                        value={formulario.tags}
                        onChange={handleChange}
                        placeholder="Separar con comas: hidratacion, secado, color"
                        className="w-full p-2 border rounded-lg outline-none"
                        style={{ borderColor: '#D5D1CC' }}
                    />
                    <p className="text-xs mt-1" style={{ color: '#8B8682' }}>
                        Etiquetas para ayudar a los clientes a encontrar tu contenido
                    </p>
                </div>

                {/* BOTONES */}
                <div className="flex gap-3 pt-4 border-t" style={{ borderColor: '#E8DCC4' }}>
                    <button
                        type="submit"
                        disabled={cargando}
                        className="flex-1 py-3 px-4 rounded-lg font-bold transition"
                        style={{ backgroundColor: '#2E7D2E', color: '#fff' }}
                        onMouseEnter={(e) => !cargando && (e.target.style.backgroundColor = '#22652E')}
                        onMouseLeave={(e) => !cargando && (e.target.style.backgroundColor = '#2E7D2E')}
                    >
                        {cargando ? 'Guardando...' : (
                            <span className="inline-flex items-center gap-2">
                                <IconCheckCircle className="h-4 w-4" /> {contenidoEditar ? 'Actualizar' : 'Publicar'}
                            </span>
                        )}
                    </button>

                    <button
                        type="button"
                        onClick={onCancelar}
                        className="flex-1 py-3 px-4 rounded-lg font-bold transition"
                        style={{ backgroundColor: '#8B8682', color: '#fff' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#8B8682'}
                    >
                        <span className="inline-flex items-center gap-2">
                            <IconX className="h-4 w-4" /> Cancelar
                        </span>
                    </button>
                </div>
            </form>
        </div>
    );
};

export default PanelEditorContenido;
