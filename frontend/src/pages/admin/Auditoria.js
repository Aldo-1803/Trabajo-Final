import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const Auditoria = () => {
    const [auditorias, setAuditorias] = useState([]);
    const [loading, setLoading] = useState(false);
    const [selectedAuditoria, setSelectedAuditoria] = useState(null);
    const [detalleAbierto, setDetalleAbierto] = useState(false);
    const navigate = useNavigate();

    // Estados para filtros
    const [filtroTabla, setFiltroTabla] = useState('');
    const [filtroAccion, setFiltroAccion] = useState('');
    const [filtroUsuario, setFiltroUsuario] = useState('');
    const [busqueda, setBusqueda] = useState('');
    const [ordenamiento, setOrdenamiento] = useState('-fecha_hora');
    const [fuente, setFuente] = useState('sistema');

    // Cargar auditorías
    const cargarAuditorias = useCallback(async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('access_token');
            
            // Construir query params
            const params = new URLSearchParams();
            if (filtroTabla) params.append('tabla', filtroTabla);
            if (filtroAccion) params.append('accion', filtroAccion);
            if (filtroUsuario) params.append('usuario', filtroUsuario);
            if (busqueda) params.append('search', busqueda);
            if (ordenamiento) params.append('ordering', ordenamiento);

            const endpoint = fuente === 'historial'
                ? 'http://127.0.0.1:8000/api/gestion/auditoria-historial/'
                : 'http://127.0.0.1:8000/api/gestion/auditoria/';

            const res = await axios.get(
                `${endpoint}?${params.toString()}`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            
            setAuditorias(res.data.results || res.data);
        } catch (error) {
            console.error('Error cargando auditorías:', error);
            if (error.response?.status === 403) {
                notify.error('Solo administradores pueden ver la auditoría');
                navigate('/admin-dashboard');
            } else {
                notify.error('Error al cargar auditorías');
            }
        } finally {
            setLoading(false);
        }
    }, [filtroTabla, filtroAccion, filtroUsuario, busqueda, ordenamiento, fuente, navigate]);

    useEffect(() => {
        cargarAuditorias();
    }, [cargarAuditorias]);

    const obtenerColorAccion = (accion) => {
        switch (accion) {
            case 'ALTA':
                return 'bg-green-100 text-green-800';
            case 'MODIFICACION':
                return 'bg-yellow-100 text-yellow-800';
            case 'BAJA':
                return 'bg-red-100 text-red-800';
            default:
                return 'bg-gray-100 text-gray-800';
        }
    };

    const obtenerIconoAccion = (accion) => {
        switch (accion) {
            case 'ALTA':
                return '✚';
            case 'MODIFICACION':
                return '✎';
            case 'BAJA':
                return '✕';
            default:
                return '○';
        }
    };

    const formatValueText = (value) => {
        if (value === null || value === undefined || value === '') return '—';
        if (typeof value === 'boolean') return value ? 'Sí' : 'No';
        if (Array.isArray(value)) {
            if (value.length === 0) return '—';
            const allPrimitive = value.every(
                (item) => item === null || ['string', 'number', 'boolean'].includes(typeof item)
            );
            return allPrimitive ? value.join(', ') : `${value.length} items`;
        }
        if (typeof value === 'object') return null;
        return String(value);
    };

    const renderValue = (value) => {
        const text = formatValueText(value);
        if (text !== null) {
            return <span className="text-sm text-gray-700">{text}</span>;
        }

        const entries = Object.entries(value || {});
        if (entries.length === 0) {
            return <span className="text-sm text-gray-400">—</span>;
        }

        return (
            <div className="space-y-1">
                {entries.map(([key, val]) => {
                    const innerText = formatValueText(val);
                    return (
                        <div key={key} className="text-xs text-gray-600">
                            <span className="font-semibold" style={{ color: '#817773' }}>{key}:</span>{' '}
                            <span>{innerText !== null ? innerText : '[obj]'}</span>
                        </div>
                    );
                })}
            </div>
        );
    };

    const renderObjectTable = (data) => {
        const entries = Object.entries(data || {});
        if (entries.length === 0) {
            return <p className="text-sm text-gray-400">—</p>;
        }

        return (
            <div className="overflow-x-auto border rounded-lg">
                <table className="w-full">
                    <thead style={{ backgroundColor: '#F5EBE0' }}>
                        <tr>
                            <th className="px-4 py-3 text-left font-semibold" style={{ color: '#817773' }}>Campo</th>
                            <th className="px-4 py-3 text-left font-semibold" style={{ color: '#817773' }}>Valor</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y">
                        {entries.map(([campo, valor]) => (
                            <tr key={campo} className="hover:bg-gray-50">
                                <td className="px-4 py-3 font-medium" style={{ color: '#817773' }}>{campo}</td>
                                <td className="px-4 py-3">{renderValue(valor)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    };

    const abrirDetalle = async (auditoria) => {
        try {
            if (auditoria?.cambios || fuente === 'historial') {
                setSelectedAuditoria(auditoria);
                setDetalleAbierto(true);
                return;
            }

            const token = localStorage.getItem('access_token');
            const res = await axios.get(
                `http://127.0.0.1:8000/api/gestion/auditoria/${auditoria.id}/`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setSelectedAuditoria(res.data);
            setDetalleAbierto(true);
        } catch (error) {
            console.error('Error cargando detalle de auditoría:', error);
            notify.error('No se pudo cargar el detalle de auditoría');
        }
    };

    const cerrarDetalle = () => {
        setDetalleAbierto(false);
        setSelectedAuditoria(null);
    };

    const revertirCambio = async () => {
        if (!selectedAuditoria) return;

        const result = await confirmarAccion({
            title: '¿Revertir este cambio?',
            text: 'Se restaurará el registro a esta versión. Esta acción puede afectar datos relacionados.',
            confirmButtonText: 'Sí, revertir'
        });

        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                `http://127.0.0.1:8000/api/gestion/auditoria-historial/${selectedAuditoria.id}/revertir/`,
                {},
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            notify.success('Reversión aplicada correctamente');
            cerrarDetalle();
            cargarAuditorias();
        } catch (error) {
            console.error('Error al revertir:', error);
            const msg = error.response?.data?.detail || 'No se pudo revertir el cambio';
            notify.error(msg);
        }
    };

    return (
        <div style={{ backgroundColor: '#F5EBE0' }} className="min-h-screen p-6">
            <div className="max-w-7xl mx-auto">
                {/* HEADER */}
                <div className="flex justify-between items-center mb-8">
                    <h1 style={{ color: '#817773' }} className="text-4xl font-bold">
                        📋 Log de Auditoría
                    </h1>
                    <button 
                        onClick={() => navigate('/admin-dashboard')}
                        className="text-gray-500 hover:underline"
                    >
                        ← Volver al Dashboard
                    </button>
                </div>

                {/* FILTROS */}
                <div style={{ backgroundColor: 'white' }} className="rounded-lg shadow-md p-6 mb-8">
                    <h2 style={{ color: '#817773' }} className="text-xl font-bold mb-4">Filtros y Búsqueda</h2>
                    
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4">
                        {/* Búsqueda por tabla */}
                        <input
                            type="text"
                            placeholder="Buscar por tabla..."
                            value={filtroTabla}
                            onChange={(e) => setFiltroTabla(e.target.value)}
                            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
                        />

                        {/* Filtro por acción */}
                        <select
                            value={filtroAccion}
                            onChange={(e) => setFiltroAccion(e.target.value)}
                            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
                        >
                            <option value="">Todas las acciones</option>
                            <option value="ALTA">✚ ALTA (Creación)</option>
                            <option value="MODIFICACION">✎ MODIFICACION</option>
                            <option value="BAJA">✕ BAJA (Eliminación)</option>
                        </select>

                        {/* Fuente */}
                        <select
                            value={fuente}
                            onChange={(e) => setFuente(e.target.value)}
                            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
                        >
                            <option value="sistema">Auditoría del Sistema</option>
                            <option value="historial">Historial (simple-history)</option>
                        </select>

                        {/* Búsqueda por usuario/email */}
                        <input
                            type="text"
                            placeholder="Buscar por usuario..."
                            value={busqueda}
                            onChange={(e) => setBusqueda(e.target.value)}
                            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
                        />

                        {/* Ordenamiento */}
                        <select
                            value={ordenamiento}
                            onChange={(e) => setOrdenamiento(e.target.value)}
                            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-rose-500"
                        >
                            <option value="-fecha_hora">Más reciente primero</option>
                            <option value="fecha_hora">Más antiguo primero</option>
                            <option value="tabla">Por tabla (A-Z)</option>
                            <option value="-tabla">Por tabla (Z-A)</option>
                            <option value="usuario">Por usuario</option>
                        </select>
                    </div>

                    {/* Botón limpiar filtros */}
                    <button
                        onClick={() => {
                            setFiltroTabla('');
                            setFiltroAccion('');
                            setFiltroUsuario('');
                            setBusqueda('');
                            setOrdenamiento('-fecha_hora');
                            setFuente('sistema');
                        }}
                        className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 text-sm font-medium"
                    >
                        Limpiar Filtros
                    </button>
                </div>

                {/* TABLA DE AUDITORÍAS */}
                {loading ? (
                    <div className="text-center py-8">
                        <div className="inline-block animate-spin rounded-full h-8 w-8 border-t-2 border-b-2" style={{ borderColor: '#817773' }}></div>
                        <p className="mt-4 text-gray-500">Cargando auditorías...</p>
                    </div>
                ) : auditorias.length === 0 ? (
                    <div style={{ backgroundColor: 'white' }} className="rounded-lg shadow-md p-8 text-center">
                        <p className="text-gray-500 text-lg">No hay registros de auditoría</p>
                    </div>
                ) : (
                    <div style={{ backgroundColor: 'white' }} className="rounded-lg shadow-md overflow-hidden">
                        <table className="w-full">
                            <thead style={{ backgroundColor: '#F5EBE0' }}>
                                <tr>
                                    <th className="px-6 py-3 text-left text-sm font-semibold" style={{ color: '#817773' }}>Acción</th>
                                    <th className="px-6 py-3 text-left text-sm font-semibold" style={{ color: '#817773' }}>Tabla</th>
                                    <th className="px-6 py-3 text-left text-sm font-semibold" style={{ color: '#817773' }}>Registro ID</th>
                                    <th className="px-6 py-3 text-left text-sm font-semibold" style={{ color: '#817773' }}>Usuario</th>
                                    <th className="px-6 py-3 text-left text-sm font-semibold" style={{ color: '#817773' }}>Fecha y Hora</th>
                                    <th className="px-6 py-3 text-left text-sm font-semibold" style={{ color: '#817773' }}>Cambios</th>
                                    <th className="px-6 py-3 text-left text-sm font-semibold" style={{ color: '#817773' }}>Acción</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200">
                                {auditorias.map((auditoria) => (
                                    <tr key={auditoria.id} className="hover:bg-gray-50 transition-colors">
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className={`px-3 py-1 rounded-full text-sm font-bold ${obtenerColorAccion(auditoria.accion)}`}>
                                                {obtenerIconoAccion(auditoria.accion)} {auditoria.accion}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="font-medium" style={{ color: '#817773' }}>{auditoria.tabla}</span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-gray-600">#{auditoria.registro_id}</span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-sm text-gray-600">{auditoria.usuario_nombre}</span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <span className="text-sm text-gray-500">
                                                {new Date(auditoria.fecha_hora).toLocaleString('es-AR')}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            {auditoria.cambios_count > 0 ? (
                                                <span className="text-sm font-medium" style={{ color: '#AB9A91' }}>
                                                    {auditoria.cambios_count} campo{auditoria.cambios_count !== 1 ? 's' : ''}
                                                </span>
                                            ) : (
                                                <span className="text-sm text-gray-400">—</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <button
                                                onClick={() => abrirDetalle(auditoria)}
                                                className="text-blue-600 hover:text-blue-900 font-medium text-sm"
                                            >
                                                Ver Detalle →
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* MODAL DE DETALLE */}
            {detalleAbierto && selectedAuditoria && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div style={{ backgroundColor: 'white' }} className="rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
                        {/* Header del modal */}
                        <div style={{ backgroundColor: '#F5EBE0' }} className="sticky top-0 px-6 py-4 border-b flex justify-between items-center">
                            <h2 style={{ color: '#817773' }} className="text-2xl font-bold">
                                Detalle de Auditoría
                            </h2>
                            <button
                                onClick={cerrarDetalle}
                                className="text-gray-500 hover:text-gray-700 text-2xl"
                            >
                                ✕
                            </button>
                        </div>

                        {/* Contenido del modal */}
                        <div className="p-6 space-y-6">
                            {/* Información básica */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <p className="text-sm font-semibold text-gray-600">Acción</p>
                                    <p className={`text-lg font-bold px-3 py-2 rounded-lg w-fit ${obtenerColorAccion(selectedAuditoria.accion)}`}>
                                        {obtenerIconoAccion(selectedAuditoria.accion)} {selectedAuditoria.accion}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-gray-600">Tabla</p>
                                    <p className="text-lg font-bold" style={{ color: '#817773' }}>{selectedAuditoria.tabla}</p>
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-gray-600">ID del Registro</p>
                                    <p className="text-lg font-bold text-gray-600">#{selectedAuditoria.registro_id}</p>
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-gray-600">Usuario</p>
                                    <p className="text-lg font-bold text-gray-600">{selectedAuditoria.usuario_nombre}</p>
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-gray-600">Fecha y Hora</p>
                                    <p className="text-lg font-bold text-gray-600">
                                        {new Date(selectedAuditoria.fecha_hora).toLocaleString('es-AR')}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-gray-600">IP Address</p>
                                    <p className="text-lg font-bold text-gray-600">{selectedAuditoria.ip_address || 'N/A'}</p>
                                </div>
                            </div>

                            {/* Cambios detectados */}
                            {selectedAuditoria.cambios && Object.keys(selectedAuditoria.cambios).length > 0 && (
                                <div>
                                    <h3 style={{ color: '#817773' }} className="text-xl font-bold mb-4">
                                        📊 Cambios Detectados
                                    </h3>
                                    
                                    {selectedAuditoria.accion === 'MODIFICACION' ? (
                                        <div className="overflow-x-auto border rounded-lg">
                                            <table className="w-full">
                                                <thead style={{ backgroundColor: '#F5EBE0' }}>
                                                    <tr>
                                                        <th className="px-4 py-3 text-left font-semibold" style={{ color: '#817773' }}>Campo</th>
                                                        <th className="px-4 py-3 text-left font-semibold" style={{ color: '#817773' }}>Valor Anterior</th>
                                                        <th className="px-4 py-3 text-left font-semibold" style={{ color: '#817773' }}>Valor Nuevo</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y">
                                                    {Object.entries(selectedAuditoria.cambios).map(([campo, cambio]) => (
                                                        <tr key={campo} className="hover:bg-gray-50">
                                                            <td className="px-4 py-3 font-medium" style={{ color: '#817773' }}>{campo}</td>
                                                            <td className="px-4 py-3 bg-red-50">
                                                                {renderValue(cambio.antes)}
                                                            </td>
                                                            <td className="px-4 py-3 bg-green-50">
                                                                {renderValue(cambio.ahora)}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    ) : (
                                        <div className="bg-gray-50 rounded-lg p-4 max-h-96 overflow-y-auto">
                                            {selectedAuditoria.cambios?.valores
                                                ? renderObjectTable(selectedAuditoria.cambios.valores)
                                                : renderObjectTable(selectedAuditoria.cambios)
                                            }
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Valores anteriores completos */}
                            {selectedAuditoria.valor_anterior && (
                                <div>
                                    <h3 style={{ color: '#817773' }} className="text-xl font-bold mb-4">
                                        ← Todos los Valores Anteriores
                                    </h3>
                                    <div className="bg-red-50 rounded-lg p-4 max-h-96 overflow-y-auto border-l-4 border-red-500">
                                        {renderObjectTable(selectedAuditoria.valor_anterior)}
                                    </div>
                                </div>
                            )}

                            {/* Valores nuevos completos */}
                            {selectedAuditoria.valor_nuevo && (
                                <div>
                                    <h3 style={{ color: '#817773' }} className="text-xl font-bold mb-4">
                                        → Todos los Valores Nuevos
                                    </h3>
                                    <div className="bg-green-50 rounded-lg p-4 max-h-96 overflow-y-auto border-l-4 border-green-500">
                                        {renderObjectTable(selectedAuditoria.valor_nuevo)}
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Footer del modal */}
                        <div style={{ backgroundColor: '#F5EBE0' }} className="sticky bottom-0 px-6 py-4 border-t flex justify-between items-center gap-3">
                            <div className="text-xs text-gray-500">
                                {fuente === 'historial' && selectedAuditoria.revert_disabled_reason && (
                                    <span>Reversión no disponible: {selectedAuditoria.revert_disabled_reason}</span>
                                )}
                            </div>
                            <button
                                onClick={cerrarDetalle}
                                className="px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 font-medium"
                            >
                                Cerrar
                            </button>
                            {fuente === 'historial' && (
                                <button
                                    onClick={revertirCambio}
                                    className="px-4 py-2 text-white rounded-lg font-bold transition"
                                    style={{ backgroundColor: selectedAuditoria.can_revert ? '#C73E3E' : '#D5D1CC' }}
                                    disabled={!selectedAuditoria.can_revert}
                                >
                                    Revertir cambio
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Auditoria;
