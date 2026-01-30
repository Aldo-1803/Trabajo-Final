import React, { useState, useEffect } from 'react';
import TarjetaContenido from '../../components/TarjetaContenido';
import { contenidoEducativoAPI } from '../../api/contenidoEducativoAPI';

const ContenidoGuardado = () => {
    const [guardados, setGuardados] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [filtroTipo, setFiltroTipo] = useState('');
    const [busqueda, setBusqueda] = useState('');
    const [error, setError] = useState(null);

    // Cargar contenidos guardados
    const cargarGuardados = async () => {
        try {
            setCargando(true);
            setError(null);

            // Construir parámetros
            const params = {};
            if (filtroTipo) params.tipo = filtroTipo;
            if (busqueda) params.search = busqueda;

            // Usar el servicio API centralizado
            const data = await contenidoEducativoAPI.getMisGuardados(params);
            setGuardados(Array.isArray(data) ? data : []);
        } catch (error) {
            console.error('Error cargando guardados:', error);
            setError('Error al cargar tu contenido guardado. Intenta nuevamente.');
        } finally {
            setCargando(false);
        }
    };

    useEffect(() => {
        cargarGuardados();
    }, [filtroTipo, busqueda]);

    // Quitar de guardados
    const handleQuitar = () => {
        cargarGuardados();
    };

    return (
        <div className="max-w-7xl mx-auto px-6 py-8">
            {/* HEADER */}
            <div className="mb-8">
                <h1 className="text-3xl font-bold mb-2" style={{ color: '#817773' }}>
                    🔖 Mi Contenido Guardado
                </h1>
                <p style={{ color: '#8B8682' }}>
                    Tus artículos y posts favoritos de educación capilar
                </p>
            </div>

            {/* ESTADÍSTICA */}
            <div className="bg-white rounded-lg shadow p-4 mb-6 border-l-4" style={{ borderColor: '#817773' }}>
                <p className="text-sm" style={{ color: '#8B8682' }}>Total Guardado</p>
                <p className="text-2xl font-bold" style={{ color: '#817773' }}>🔖 {guardados.length}</p>
            </div>

            {/* FILTROS */}
            <div className="bg-white rounded-lg shadow p-6 mb-6">
                <h3 className="text-lg font-bold mb-4" style={{ color: '#817773' }}>🔍 Filtros</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Búsqueda */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                            Buscar
                        </label>
                        <input
                            type="text"
                            placeholder="Título, autor..."
                            value={busqueda}
                            onChange={(e) => setBusqueda(e.target.value)}
                            className="w-full p-2 border rounded-lg outline-none"
                            style={{ borderColor: '#D5D1CC' }}
                        />
                    </div>

                    {/* Tipo */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                            Tipo de Contenido
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
                </div>
            </div>

            {/* LISTA DE GUARDADOS */}
            {cargando ? (
                <div className="flex justify-center items-center py-12">
                    <div className="animate-spin">
                        <div className="w-12 h-12 border-4 border-gray-300 border-t-amber-600 rounded-full"></div>
                    </div>
                </div>
            ) : guardados.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-lg shadow">
                    <p className="text-lg mb-4" style={{ color: '#8B8682' }}>
                        📭 Aún no tienes contenido guardado
                    </p>
                    <p style={{ color: '#ABA89E' }}>
                        Explora el centro educativo y guarda tus artículos favoritos aquí
                    </p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {guardados.map(contenido => (
                        <TarjetaContenido
                            key={contenido.id}
                            contenido={contenido}
                            esPropio={false}
                            onGuardar={handleQuitar}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export default ContenidoGuardado;
