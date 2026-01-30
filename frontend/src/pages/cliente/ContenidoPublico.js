import React, { useState, useEffect } from 'react';
import TarjetaContenido from '../../components/TarjetaContenido';
import { contenidoEducativoAPI } from '../../api/contenidoEducativoAPI';

const ContenidoPublico = () => {
    const [contenidos, setContenidos] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [filtroTipo, setFiltroTipo] = useState('');
    const [filtroAutor, setFiltroAutor] = useState('');
    const [busqueda, setBusqueda] = useState('');
    const [ordenar, setOrdenar] = useState('-fecha_publicacion');
    const [autores, setAutores] = useState([]);
    const [error, setError] = useState(null);

    // Cargar contenidos publicados
    const cargarContenidos = async () => {
        try {
            setCargando(true);
            setError(null);

            // Construir parámetros de filtrado
            const params = {};
            if (filtroTipo) params.tipo = filtroTipo;
            if (filtroAutor) params.autor = filtroAutor;
            if (busqueda) params.search = busqueda;
            if (ordenar) params.ordering = ordenar;

            // Usar el servicio API centralizado
            const data = await contenidoEducativoAPI.getPublicados(params);
            setContenidos(Array.isArray(data) ? data : []);

            // Extraer autores únicos para el filtro
            if (Array.isArray(data)) {
                const autoresUnicos = [...new Set(data.map(c => c.autor?.id))].filter(Boolean);
                const nombresAutores = data.filter(c => c.autor && autoresUnicos.includes(c.autor.id));
                setAutores([...new Map(nombresAutores.map(c => [c.autor.id, c.autor])).values()]);
            }
        } catch (error) {
            console.error('Error cargando contenidos:', error);
            setError('Error al cargar el contenido educativo. Intenta nuevamente.');
            setContenidos([]);
        } finally {
            setCargando(false);
        }
    };

    useEffect(() => {
        cargarContenidos();
    }, [filtroTipo, filtroAutor, busqueda, ordenar]);

    // Actualizar al guardar/desguardar
    const handleGuardarCambio = () => {
        cargarContenidos();
    };

    return (
        <div className="max-w-7xl mx-auto px-6 py-8">
            {/* HEADER */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold mb-2" style={{ color: '#817773' }}>
                    📚 Centro Educativo
                </h1>
                <p style={{ color: '#8B8682' }}>
                    Aprende todo sobre cuidado capilar con nuestros expertos
                </p>
            </div>

            {/* ESTADÍSTICA */}
            <div className="bg-gradient-to-r rounded-lg shadow p-6 mb-6 text-white" style={{ background: 'linear-gradient(135deg, #817773, #8B8682)' }}>
                <div className="flex justify-between items-center">
                    <div>
                        <p className="text-sm opacity-90">Artículos Disponibles</p>
                        <p className="text-3xl font-bold">📖 {contenidos.length}</p>
                    </div>
                    <div>
                        <p className="text-sm opacity-90">Expertos Colaborando</p>
                        <p className="text-3xl font-bold">👨‍⚕️ {autores.length}</p>
                    </div>
                </div>
            </div>

            {/* FILTROS */}
            <div className="bg-white rounded-lg shadow p-6 mb-6">
                <h3 className="text-lg font-bold mb-4" style={{ color: '#817773' }}>🔍 Filtros y Ordenamiento</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {/* Búsqueda */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                            Buscar
                        </label>
                        <input
                            type="text"
                            placeholder="Título, tema..."
                            value={busqueda}
                            onChange={(e) => setBusqueda(e.target.value)}
                            className="w-full p-2 border rounded-lg outline-none text-sm"
                            style={{ borderColor: '#D5D1CC' }}
                        />
                    </div>

                    {/* Tipo */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                            Tipo
                        </label>
                        <select
                            value={filtroTipo}
                            onChange={(e) => setFiltroTipo(e.target.value)}
                            className="w-full p-2 border rounded-lg outline-none text-sm"
                            style={{ borderColor: '#D5D1CC' }}
                        >
                            <option value="">Todos</option>
                            <option value="IMAGEN">📷 Imagen</option>
                            <option value="VIDEO">🎥 Video</option>
                            <option value="TEXTO">📝 Texto</option>
                        </select>
                    </div>

                    {/* Autor */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                            Experto
                        </label>
                        <select
                            value={filtroAutor}
                            onChange={(e) => setFiltroAutor(e.target.value)}
                            className="w-full p-2 border rounded-lg outline-none text-sm"
                            style={{ borderColor: '#D5D1CC' }}
                        >
                            <option value="">Todos</option>
                            {autores.map(autor => (
                                <option key={autor.id} value={autor.id}>
                                    👤 {autor.nombre} {autor.apellido}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Ordenamiento */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                            Ordenar
                        </label>
                        <select
                            value={ordenar}
                            onChange={(e) => setOrdenar(e.target.value)}
                            className="w-full p-2 border rounded-lg outline-none text-sm"
                            style={{ borderColor: '#D5D1CC' }}
                        >
                            <option value="-fecha_publicacion">🆕 Más Recientes</option>
                            <option value="fecha_publicacion">🕰️ Más Antiguos</option>
                            <option value="-total_likes">❤️ Más Populares</option>
                            <option value="titulo">🔤 A-Z</option>
                        </select>
                    </div>
                </div>
            </div>

            {/* LISTA DE CONTENIDOS */}
            {cargando ? (
                <div className="flex justify-center items-center py-16">
                    <div className="animate-spin">
                        <div className="w-12 h-12 border-4 border-gray-300 border-t-amber-600 rounded-full"></div>
                    </div>
                </div>
            ) : contenidos.length === 0 ? (
                <div className="text-center py-16 bg-white rounded-lg shadow">
                    <p className="text-lg mb-4" style={{ color: '#8B8682' }}>
                        📭 No hay artículos disponibles con esos filtros
                    </p>
                    <p style={{ color: '#ABA89E' }}>
                        Intenta cambiar tus filtros o revisa luego
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {contenidos.map(contenido => (
                        <TarjetaContenido
                            key={contenido.id}
                            contenido={contenido}
                            esPropio={false}
                            onGuardar={handleGuardarCambio}
                            onLike={handleGuardarCambio}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export default ContenidoPublico;
