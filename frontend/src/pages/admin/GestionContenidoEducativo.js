import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import { ADMIN_ROUTES } from '../../routes/routes';
import toast from 'react-hot-toast';

const GestionContenidoEducativo = () => {
    const [contenidos, setContenidos] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(null);
    const [filtroEstado, setFiltroEstado] = useState('');
    const [filtroTipo, setFiltroTipo] = useState('');
    const [busqueda, setBusqueda] = useState('');
    const navigate = useNavigate();

    const tipos = ['blog', 'video', 'tutorial', 'consejo', 'caso_estudio'];
    const estados = ['BORRADOR', 'PUBLICADO', 'ARCHIVADO'];

    useEffect(() => {
        cargarContenidos();
    }, [filtroEstado, filtroTipo, busqueda]);

    const cargarContenidos = async () => {
        const token = localStorage.getItem('access_token');
        
        try {
            setCargando(true);
            let url = 'http://127.0.0.1:8000/api/gestion/contenido-educativo/?limit=100';
            
            if (filtroEstado) {
                url += `&estado=${filtroEstado}`;
            }
            if (filtroTipo) {
                url += `&tipo=${filtroTipo}`;
            }
            if (busqueda) {
                url += `&search=${busqueda}`;
            }

            const res = await axios.get(url, {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            setContenidos(res.data.results || []);
            setError(null);
        } catch (err) {
            console.error('Error cargando contenidos:', err);
            setError('Error al cargar el contenido educativo');
            toast.error('Error al cargar el contenido');
        } finally {
            setCargando(false);
        }
    };

    const handleEliminar = async (id) => {
        if (window.confirm('¿Estás seguro que deseas eliminar este contenido?')) {
            const token = localStorage.getItem('access_token');
            
            try {
                await axios.delete(`http://127.0.0.1:8000/api/gestion/contenido-educativo/${id}/`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                
                toast.success('Contenido eliminado correctamente');
                cargarContenidos();
            } catch (err) {
                console.error('Error eliminando contenido:', err);
                toast.error('Error al eliminar el contenido');
            }
        }
    };

    const handleCambiarEstado = async (id, nuevoEstado) => {
        const token = localStorage.getItem('access_token');
        
        try {
            await axios.patch(
                `http://127.0.0.1:8000/api/gestion/contenido-educativo/${id}/`,
                { estado: nuevoEstado },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            
            toast.success(`Estado actualizado a ${nuevoEstado}`);
            cargarContenidos();
        } catch (err) {
            console.error('Error actualizando estado:', err);
            toast.error('Error al actualizar el estado');
        }
    };

    const obtenerColorTipo = (tipo) => {
        const colores = {
            blog: 'bg-blue-100 text-blue-800',
            video: 'bg-red-100 text-red-800',
            tutorial: 'bg-green-100 text-green-800',
            consejo: 'bg-yellow-100 text-yellow-800',
            caso_estudio: 'bg-purple-100 text-purple-800',
        };
        return colores[tipo] || 'bg-gray-100 text-gray-800';
    };

    const obtenerColorEstado = (estado) => {
        const colores = {
            BORRADOR: 'bg-gray-100 text-gray-800',
            PUBLICADO: 'bg-green-100 text-green-800',
            ARCHIVADO: 'bg-red-100 text-red-800',
        };
        return colores[estado] || 'bg-gray-100 text-gray-800';
    };

    return (
        <div className="min-h-screen" style={{ backgroundColor: '#F5F0EB' }}>
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Encabezado */}
                <div className="mb-8">
                    <div className="flex justify-between items-center">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">Contenido Educativo</h1>
                            <p className="text-gray-600 mt-2">Gestiona el contenido educativo para clientes</p>
                        </div>
                        <Link
                            to={ADMIN_ROUTES.CREAR_CONTENIDO}
                            className="px-6 py-3 rounded-lg font-semibold text-white transition-colors"
                            style={{ backgroundColor: '#817773' }}
                        >
                            + Crear Contenido
                        </Link>
                    </div>
                </div>

                {/* Filtros */}
                <div className="bg-white rounded-lg shadow-md p-6 mb-8">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        {/* Búsqueda */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Buscar por título o descripción
                            </label>
                            <input
                                type="text"
                                placeholder="Buscar..."
                                value={busqueda}
                                onChange={(e) => setBusqueda(e.target.value)}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                style={{ outlineColor: '#817773' }}
                            />
                        </div>

                        {/* Filtro Estado */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Estado
                            </label>
                            <select
                                value={filtroEstado}
                                onChange={(e) => setFiltroEstado(e.target.value)}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                style={{ outlineColor: '#817773' }}
                            >
                                <option value="">Todos</option>
                                {estados.map((estado) => (
                                    <option key={estado} value={estado}>
                                        {estado}
                                    </option>
                                ))}
                            </select>
                        </div>

                        {/* Filtro Tipo */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Tipo
                            </label>
                            <select
                                value={filtroTipo}
                                onChange={(e) => setFiltroTipo(e.target.value)}
                                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2"
                                style={{ outlineColor: '#817773' }}
                            >
                                <option value="">Todos</option>
                                {tipos.map((tipo) => (
                                    <option key={tipo} value={tipo}>
                                        {tipo.replace(/_/g, ' ').toUpperCase()}
                                    </option>
                                ))}
                            </select>
                        </div>

                        {/* Limpiar Filtros */}
                        <div className="flex items-end">
                            <button
                                onClick={() => {
                                    setBusqueda('');
                                    setFiltroEstado('');
                                    setFiltroTipo('');
                                }}
                                className="w-full px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 transition-colors font-medium"
                            >
                                Limpiar Filtros
                            </button>
                        </div>
                    </div>
                </div>

                {/* Lista de Contenidos */}
                {cargando ? (
                    <div className="text-center py-12">
                        <div className="inline-block">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2" style={{ borderColor: '#817773' }}></div>
                        </div>
                        <p className="text-gray-600 mt-4">Cargando contenido...</p>
                    </div>
                ) : error ? (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
                        {error}
                    </div>
                ) : contenidos.length === 0 ? (
                    <div className="bg-white rounded-lg shadow-md p-12 text-center">
                        <div className="text-gray-400 text-5xl mb-4">📝</div>
                        <h3 className="text-xl font-semibold text-gray-700 mb-2">Sin contenido aún</h3>
                        <p className="text-gray-600 mb-6">Comienza a crear contenido educativo para tus clientes</p>
                        <Link
                            to={ADMIN_ROUTES.CREAR_CONTENIDO}
                            className="inline-block px-6 py-3 rounded-lg font-semibold text-white transition-colors"
                            style={{ backgroundColor: '#817773' }}
                        >
                            Crear Primer Contenido
                        </Link>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {contenidos.map((contenido) => (
                            <div
                                key={contenido.id}
                                className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow overflow-hidden"
                            >
                                {/* Thumbnail */}
                                {contenido.multimedia_url && (
                                    <div className="h-40 bg-gray-200 overflow-hidden">
                                        <img
                                            src={contenido.multimedia_url}
                                            alt={contenido.titulo}
                                            className="w-full h-full object-cover"
                                        />
                                    </div>
                                )}

                                {/* Contenido */}
                                <div className="p-4">
                                    <div className="flex justify-between items-start mb-3">
                                        <h3 className="text-lg font-semibold text-gray-900 flex-1">
                                            {contenido.titulo}
                                        </h3>
                                    </div>

                                    {/* Badges */}
                                    <div className="flex gap-2 mb-3 flex-wrap">
                                        <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${obtenerColorTipo(contenido.tipo)}`}>
                                            {contenido.tipo.replace(/_/g, ' ')}
                                        </span>
                                        <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${obtenerColorEstado(contenido.estado)}`}>
                                            {contenido.estado}
                                        </span>
                                    </div>

                                    {/* Descripción */}
                                    <p className="text-gray-600 text-sm line-clamp-2 mb-3">
                                        {contenido.descripcion}
                                    </p>

                                    {/* Estadísticas */}
                                    <div className="flex justify-between text-sm text-gray-500 mb-4 py-2 border-t border-b border-gray-200">
                                        <div className="text-center flex-1">
                                            <div className="font-semibold text-gray-900">{contenido.total_likes}</div>
                                            <div className="text-xs">👍</div>
                                        </div>
                                        <div className="text-center flex-1">
                                            <div className="font-semibold text-gray-900">{contenido.total_guardados}</div>
                                            <div className="text-xs">💾</div>
                                        </div>
                                        <div className="text-center flex-1">
                                            <div className="font-semibold text-gray-900">
                                                {new Date(contenido.fecha_publicacion || contenido.fecha_actualizacion).toLocaleDateString('es-AR')}
                                            </div>
                                            <div className="text-xs">📅</div>
                                        </div>
                                    </div>

                                    {/* Botones de Acción */}
                                    <div className="flex gap-2">
                                        <Link
                                            to={`${ADMIN_ROUTES.EDITAR_CONTENIDO.replace(':id', contenido.id)}`}
                                            className="flex-1 px-3 py-2 text-center rounded-lg font-medium text-white transition-colors"
                                            style={{ backgroundColor: '#817773' }}
                                        >
                                            Editar
                                        </Link>
                                        
                                        {contenido.estado === 'BORRADOR' ? (
                                            <button
                                                onClick={() => handleCambiarEstado(contenido.id, 'PUBLICADO')}
                                                className="flex-1 px-3 py-2 rounded-lg font-medium text-green-700 bg-green-100 hover:bg-green-200 transition-colors"
                                            >
                                                Publicar
                                            </button>
                                        ) : (
                                            <button
                                                onClick={() => handleCambiarEstado(contenido.id, 'BORRADOR')}
                                                className="flex-1 px-3 py-2 rounded-lg font-medium text-yellow-700 bg-yellow-100 hover:bg-yellow-200 transition-colors"
                                            >
                                                Borrador
                                            </button>
                                        )}

                                        <button
                                            onClick={() => handleEliminar(contenido.id)}
                                            className="flex-1 px-3 py-2 rounded-lg font-medium text-red-700 bg-red-100 hover:bg-red-200 transition-colors"
                                        >
                                            Eliminar
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default GestionContenidoEducativo;
