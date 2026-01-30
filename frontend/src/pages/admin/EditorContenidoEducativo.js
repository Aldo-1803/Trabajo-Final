import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import toast from 'react-hot-toast';
import { ADMIN_ROUTES } from '../../routes/routes';

const EditorContenidoEducativo = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    
    const [cargando, setCargando] = useState(id ? true : false);
    const [guardando, setGuardando] = useState(false);
    const [formData, setFormData] = useState({
        titulo: '',
        descripcion: '',
        contenido_texto: '',
        multimedia_url: '',
        tipo: 'blog',
        estado: 'BORRADOR',
        activo: true,
    });

    const tipos = ['blog', 'video', 'tutorial', 'consejo', 'caso_estudio'];
    const estados = ['BORRADOR', 'PUBLICADO', 'ARCHIVADO'];

    useEffect(() => {
        if (id) {
            cargarContenido();
        }
    }, [id]);

    const cargarContenido = async () => {
        const token = localStorage.getItem('access_token');
        
        try {
            const res = await axios.get(
                `http://127.0.0.1:8000/api/contenido-educativo/${id}/`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            
            setFormData({
                titulo: res.data.titulo || '',
                descripcion: res.data.descripcion || '',
                contenido_texto: res.data.contenido_texto || '',
                multimedia_url: res.data.multimedia_url || '',
                tipo: res.data.tipo || 'blog',
                estado: res.data.estado || 'BORRADOR',
                activo: res.data.activo !== false,
            });
        } catch (error) {
            console.error('Error al cargar contenido:', error);
            toast.error('Error al cargar el contenido');
            navigate(ADMIN_ROUTES.CONTENIDO_EDUCATIVO);
        } finally {
            setCargando(false);
        }
    };

    const handleInputChange = (e) => {
        const { name, value, type, checked } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value
        }));
    };

    const handleGuardar = async () => {
        if (!formData.titulo.trim()) {
            toast.error('El título es requerido');
            return;
        }
        
        if (!formData.descripcion.trim()) {
            toast.error('La descripción es requerida');
            return;
        }
        
        if (!formData.contenido_texto.trim()) {
            toast.error('El contenido es requerido');
            return;
        }

        const token = localStorage.getItem('access_token');
        
        try {
            setGuardando(true);
            
            if (id) {
                // Actualizar contenido existente
                await axios.put(
                    `http://127.0.0.1:8000/api/contenido-educativo/${id}/`,
                    formData,
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
                toast.success('Contenido actualizado correctamente');
            } else {
                // Crear nuevo contenido
                await axios.post(
                    'http://127.0.0.1:8000/api/contenido-educativo/',
                    formData,
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
                toast.success('Contenido creado correctamente');
            }
            
            navigate(ADMIN_ROUTES.CONTENIDO_EDUCATIVO);
        } catch (error) {
            console.error('Error al guardar:', error);
            toast.error('Error al guardar el contenido');
        } finally {
            setGuardando(false);
        }
    };

    const handleCancelar = () => {
        navigate(ADMIN_ROUTES.CONTENIDO_EDUCATIVO);
    };

    if (cargando) {
        return (
            <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#F5F0EB' }}>
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto mb-4" style={{ borderColor: '#817773' }}></div>
                    <p className="text-gray-600">Cargando contenido...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen" style={{ backgroundColor: '#F5F0EB' }}>
            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Encabezado */}
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">
                        {id ? 'Editar Contenido' : 'Crear Nuevo Contenido'}
                    </h1>
                    <p className="text-gray-600 mt-2">
                        {id ? 'Actualiza tu contenido educativo' : 'Comparte conocimiento con tus clientes'}
                    </p>
                </div>

                {/* Formulario */}
                <div className="bg-white rounded-lg shadow-md p-8">
                    <div className="space-y-6">
                        {/* Título */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Título *
                            </label>
                            <input
                                type="text"
                                name="titulo"
                                value={formData.titulo}
                                onChange={handleInputChange}
                                placeholder="Ej: Los 5 mejores tratamientos para cabello seco"
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                style={{ outlineColor: '#817773' }}
                                maxLength={200}
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                {formData.titulo.length}/200 caracteres
                            </p>
                        </div>

                        {/* Descripción */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Descripción *
                            </label>
                            <textarea
                                name="descripcion"
                                value={formData.descripcion}
                                onChange={handleInputChange}
                                placeholder="Resumen breve del contenido (aparecerá en listados)"
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                style={{ outlineColor: '#817773' }}
                                rows={3}
                                maxLength={500}
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                {formData.descripcion.length}/500 caracteres
                            </p>
                        </div>

                        {/* Contenido Texto */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Contenido *
                            </label>
                            <textarea
                                name="contenido_texto"
                                value={formData.contenido_texto}
                                onChange={handleInputChange}
                                placeholder="Escribe el contenido principal aquí. Puedes usar saltos de línea para organizar el texto."
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 font-mono text-sm"
                                style={{ outlineColor: '#817773' }}
                                rows={10}
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                {formData.contenido_texto.length} caracteres
                            </p>
                        </div>

                        {/* URL Multimedia */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                URL de Imagen/Video
                            </label>
                            <input
                                type="url"
                                name="multimedia_url"
                                value={formData.multimedia_url}
                                onChange={handleInputChange}
                                placeholder="https://ejemplo.com/imagen.jpg"
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                style={{ outlineColor: '#817773' }}
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                Sube tu imagen a un servicio como Cloudinary y pega la URL aquí
                            </p>
                            {formData.multimedia_url && (
                                <div className="mt-3">
                                    <p className="text-xs font-medium text-gray-700 mb-2">Vista previa:</p>
                                    <img
                                        src={formData.multimedia_url}
                                        alt="Preview"
                                        className="max-w-xs max-h-48 rounded-lg"
                                        onError={(e) => {
                                            e.target.style.display = 'none';
                                            toast.error('No se pudo cargar la imagen');
                                        }}
                                    />
                                </div>
                            )}
                        </div>

                        {/* Tipo y Estado */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Tipo de Contenido
                                </label>
                                <select
                                    name="tipo"
                                    value={formData.tipo}
                                    onChange={handleInputChange}
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                    style={{ outlineColor: '#817773' }}
                                >
                                    {tipos.map(tipo => (
                                        <option key={tipo} value={tipo}>
                                            {tipo.replace(/_/g, ' ').charAt(0).toUpperCase() + tipo.replace(/_/g, ' ').slice(1)}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Estado
                                </label>
                                <select
                                    name="estado"
                                    value={formData.estado}
                                    onChange={handleInputChange}
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                    style={{ outlineColor: '#817773' }}
                                >
                                    {estados.map(estado => (
                                        <option key={estado} value={estado}>
                                            {estado}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        {/* Checkbox Activo */}
                        <div className="flex items-center">
                            <input
                                type="checkbox"
                                id="activo"
                                name="activo"
                                checked={formData.activo}
                                onChange={handleInputChange}
                                className="rounded"
                                style={{ accentColor: '#817773' }}
                            />
                            <label htmlFor="activo" className="ml-3 text-sm font-medium text-gray-700">
                                Contenido activo (visible para clientes)
                            </label>
                        </div>

                        {/* Botones de Acción */}
                        <div className="flex gap-4 pt-6 border-t border-gray-200">
                            <button
                                onClick={handleCancelar}
                                disabled={guardando}
                                className="flex-1 px-6 py-3 rounded-lg font-semibold text-gray-700 bg-gray-200 hover:bg-gray-300 transition-colors disabled:opacity-50"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleGuardar}
                                disabled={guardando}
                                className="flex-1 px-6 py-3 rounded-lg font-semibold text-white transition-colors disabled:opacity-50"
                                style={{ backgroundColor: '#817773' }}
                            >
                                {guardando ? 'Guardando...' : (id ? 'Actualizar' : 'Crear')}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Consejos */}
                <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
                    <h3 className="font-semibold text-blue-900 mb-3">💡 Consejos para mejor contenido</h3>
                    <ul className="text-sm text-blue-800 space-y-2">
                        <li>✓ Usa títulos claros y descriptivos</li>
                        <li>✓ Escribe descripciones que resuman el tema principal</li>
                        <li>✓ Organiza el contenido en párrafos cortos y legibles</li>
                        <li>✓ Agrega imágenes para hacer más atractivo el contenido</li>
                        <li>✓ Guarda como borrador primero si necesitas revisar después</li>
                    </ul>
                </div>
            </div>
        </div>
    );
};

export default EditorContenidoEducativo;
