import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionClientes = () => {
    // --- ESTADOS ---
    const [clientes, setClientes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [modalAbierto, setModalAbierto] = useState(false);
    const [clienteSeleccionado, setClienteSeleccionado] = useState(null);
    const [fichasCliente, setFichasCliente] = useState([]);
    const [cargandoFichas, setCargandoFichas] = useState(false);
    const navigate = useNavigate();

    // --- CARGA DE DATOS ---
    const fetchClientes = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                navigate('/login');
                return;
            }

            // Llamamos al endpoint que arreglamos (ClienteViewSet)
            const response = await axios.get('http://127.0.0.1:8000/api/usuarios/clientes/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            setClientes(response.data);
            setError('');
        } catch (err) {
            console.error("Error cargando clientes:", err);
            setError('No se pudo cargar la lista de clientes.');
            
            if (err.response?.status === 401) navigate('/login');
            if (err.response?.status === 403) alert("No tienes permisos de administrador.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchClientes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const abrirModalFicha = async (cliente) => {
        setClienteSeleccionado(cliente);
        setModalAbierto(true);
        setCargandoFichas(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get(
                `http://127.0.0.1:8000/api/gestion/fichas-tecnicas/por_cliente/?cliente_id=${cliente.id}`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setFichasCliente(res.data || []);
        } catch (err) {
            console.error('Error cargando fichas del cliente:', err);
            setFichasCliente([]);
        } finally {
            setCargandoFichas(false);
        }
    };

    const cerrarModalFicha = () => {
        setModalAbierto(false);
        setClienteSeleccionado(null);
        setFichasCliente([]);
    };

    // --- RENDERIZADO ---
    return (
        <div className="min-h-screen p-8" style={{ backgroundColor: '#F5F0EB' }}>
            <div className="max-w-7xl mx-auto">
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <h1 className="text-3xl font-bold text-gray-800">Cartera de Clientes</h1>
                        <p className="text-gray-500">Visualización de perfiles registrados</p>
                    </div>
                    <button 
                        onClick={() => navigate('/admin-dashboard')}
                        className="px-4 py-2 rounded-lg font-medium transition-all"
                        style={{ color: '#817773', borderColor: '#C1B4A4', border: '1px solid' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F0EB'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                    >
                        ← Volver al Dashboard
                    </button>
                </div>

                {error && (
                    <div className="p-4 mb-4 rounded-lg font-medium text-red-700" style={{ backgroundColor: '#FEE2E2', borderLeft: '4px solid #DC2626' }}>
                        {error}
                    </div>
                )}

                <div className="bg-white shadow-lg rounded-lg overflow-hidden border" style={{ borderColor: '#E8DCC4' }}>
                    {loading ? (
                        <div className="p-8 text-center text-gray-500">Cargando datos...</div>
                    ) : clientes.length === 0 ? (
                        <div className="p-8 text-center text-gray-400">No hay clientes registrados aún.</div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="min-w-full divide-y divide-gray-200">
                                <thead className="border-b" style={{ backgroundColor: '#E8DCC4' }}>
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-bold text-gray-800 uppercase tracking-wider">Cliente</th>
                                        <th className="px-6 py-3 text-left text-xs font-bold text-gray-800 uppercase tracking-wider">Contacto</th>
                                        <th className="px-6 py-3 text-left text-xs font-bold text-gray-800 uppercase tracking-wider">Ubicación</th>
                                        <th className="px-6 py-3 text-left text-xs font-bold text-gray-800 uppercase tracking-wider">Registro</th>
                                        <th className="px-6 py-3 text-right text-xs font-bold text-gray-800 uppercase tracking-wider">Acciones</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {clientes.map((cliente) => (
                                        <tr key={cliente.id} className="hover:bg-gray-50 transition-colors">
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="flex items-center">
                                                    <div className="flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center text-white font-bold" style={{ backgroundColor: '#817773' }}>
                                                        {cliente.first_name?.[0] || 'U'}
                                                    </div>
                                                    <div className="ml-4">
                                                        <div className="text-sm font-bold text-gray-900">
                                                            {cliente.first_name} {cliente.last_name}
                                                        </div>
                                                        <div className="text-xs text-gray-500">{cliente.email}</div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <div className="text-sm text-gray-900">{cliente.numero || '-'}</div>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap">
                                                <span className="px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full text-white" style={{ backgroundColor: '#C1B4A4' }}>
                                                    {cliente.zona || 'No especificada'}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                {cliente.date_joined ? new Date(cliente.date_joined).toLocaleDateString() : '-'}
                                            </td>
                                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                <button 
                                                    className="font-semibold transition-all"
                                                    style={{ color: '#817773' }}
                                                    onMouseEnter={(e) => e.target.style.color = '#6B5F5B'}
                                                    onMouseLeave={(e) => e.target.style.color = '#817773'}
                                                    onClick={() => abrirModalFicha(cliente)}
                                                >
                                                    Ver Ficha
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
            {modalAbierto && clienteSeleccionado && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
                        <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
                            <div>
                                <h2 className="text-xl font-bold text-gray-800">Historial Técnico</h2>
                                <p className="text-sm text-gray-500">{clienteSeleccionado.first_name} {clienteSeleccionado.last_name}</p>
                            </div>
                            <button
                                onClick={cerrarModalFicha}
                                className="text-gray-500 hover:text-gray-700 text-2xl"
                            >
                                ✕
                            </button>
                        </div>
                        <div className="p-6 space-y-4">
                            {cargandoFichas ? (
                                <div className="text-center text-gray-500">Cargando historial...</div>
                            ) : fichasCliente.length === 0 ? (
                                <div className="text-center text-gray-500">No hay fichas técnicas registradas.</div>
                            ) : (
                                fichasCliente.map((ficha) => (
                                    <div key={ficha.id} className="border rounded-lg p-4 shadow-sm bg-gray-50">
                                        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                                            <div className="font-semibold text-gray-800">
                                                {ficha.servicio_nombre} · {new Date(ficha.turno_fecha).toLocaleDateString('es-AR')}
                                            </div>
                                            <div className="text-xs text-gray-500">Profesional: {ficha.profesional_nombre || '—'}</div>
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div>
                                                <p className="text-xs font-semibold text-gray-500">Fórmula</p>
                                                <p className="text-sm text-gray-700 whitespace-pre-wrap">{ficha.formula || '—'}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold text-gray-500">Comentario al cliente</p>
                                                <p className="text-sm text-gray-700 whitespace-pre-wrap">{ficha.comentario_cliente || '—'}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold text-gray-500">Observaciones internas</p>
                                                <p className="text-sm text-gray-700 whitespace-pre-wrap">{ficha.observaciones_proceso || '—'}</p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-semibold text-gray-500">Rutina recomendada</p>
                                                <p className="text-sm text-gray-700">{ficha.rutina_recomendada_nombre || '—'}</p>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

// 👇 ESTA LÍNEA ES CRÍTICA. SI FALTA, APARECE EL ERROR "Element type is invalid"
export default GestionClientes;