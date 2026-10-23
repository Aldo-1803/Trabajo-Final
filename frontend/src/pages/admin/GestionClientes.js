import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { notify } from '../../utils/notificaciones';
import { getLandingPath } from '../../utils/sessionLanding';

const GestionClientes = () => {
    // --- ESTADOS ---
    const [clientes, setClientes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [modalNuevoClienteAbierto, setModalNuevoClienteAbierto] = useState(false);
    const [creandoCliente, setCreandoCliente] = useState(false);
    const [nuevoCliente, setNuevoCliente] = useState({
        first_name: '',
        last_name: '',
        email: '',
        telefono: '',
        zona: '',
        password_temporal: '',
        motivo: ''
    });
    const navigate = useNavigate();
    const { session, hasPermission } = useSession();
    const canCreateClient = hasPermission('usuarios.create_walkin_client');
    const landingPath = getLandingPath(session) || '/login';

    // --- CARGA DE DATOS ---
    const fetchClientes = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                navigate('/login');
                return;
            }

            const response = await axios.get('http://127.0.0.1:8000/api/usuarios/clientes/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            setClientes(response.data);
            setError('');
        } catch (err) {
            console.error("Error cargando clientes:", err);
            setClientes([]);

            if (err.response?.status === 401) {
                navigate('/login');
            } else if (err.response?.status === 403) {
                setError('No tenés permisos para consultar clientes.');
            } else {
                setError('No se pudo cargar la lista de clientes.');
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchClientes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const limpiarNuevoCliente = () => {
        setNuevoCliente({
            first_name: '',
            last_name: '',
            email: '',
            telefono: '',
            zona: '',
            password_temporal: '',
            motivo: ''
        });
    };

    const handleNuevoClienteChange = (event) => {
        const { name, value } = event.target;
        setNuevoCliente((current) => ({ ...current, [name]: value }));
    };

    const crearCliente = async (event) => {
        event.preventDefault();
        setCreandoCliente(true);
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                'http://127.0.0.1:8000/api/usuarios/admin/clientes/crear/',
                nuevoCliente,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setModalNuevoClienteAbierto(false);
            limpiarNuevoCliente();
            await fetchClientes();
            notify.success('Cliente creado correctamente.');
        } catch (err) {
            const errorCode = err.response?.data?.error?.code;
            const errorMessages = {
                EMAIL_ALREADY_EXISTS: 'Ya existe una cuenta con ese email.',
                INVALID_PASSWORD: 'La contraseña temporal no cumple los requisitos de seguridad.',
                PERMISSION_DENIED: 'No tenés permisos para crear clientes.'
            };
            notify.error(
                errorMessages[errorCode]
                || 'No se pudo crear el cliente. Revisá los datos e intentá nuevamente.'
            );
        } finally {
            setCreandoCliente(false);
        }
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
                    <div className="flex gap-3">
                        {canCreateClient && (
                            <button
                                onClick={() => setModalNuevoClienteAbierto(true)}
                                className="px-4 py-2 rounded-lg font-bold text-white transition-all"
                                style={{ backgroundColor: '#817773' }}
                            >
                                + Nuevo cliente
                            </button>
                        )}
                        <button
                            onClick={() => navigate(landingPath)}
                            className="px-4 py-2 rounded-lg font-medium transition-all"
                            style={{ color: '#817773', borderColor: '#C1B4A4', border: '1px solid' }}
                            onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F0EB'}
                            onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                        >
                            ← Volver al inicio
                        </button>
                    </div>
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
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
            {modalNuevoClienteAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto" style={{ borderTop: '4px solid #817773' }}>
                        <h2 className="text-2xl font-bold text-gray-800 mb-2">Nuevo cliente</h2>
                        <p className="text-sm text-gray-500 mb-6">Alta presencial con acceso mediante contraseña temporal.</p>
                        <form onSubmit={crearCliente} className="space-y-4">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="new-client-first-name" className="block text-sm font-medium text-gray-700 mb-1">Nombre *</label>
                                    <input
                                        id="new-client-first-name"
                                        type="text"
                                        name="first_name"
                                        value={nuevoCliente.first_name}
                                        onChange={handleNuevoClienteChange}
                                        required
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="new-client-last-name" className="block text-sm font-medium text-gray-700 mb-1">Apellido *</label>
                                    <input
                                        id="new-client-last-name"
                                        type="text"
                                        name="last_name"
                                        value={nuevoCliente.last_name}
                                        onChange={handleNuevoClienteChange}
                                        required
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                            </div>
                            <div>
                                <label htmlFor="new-client-email" className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                                <input
                                    id="new-client-email"
                                    type="email"
                                    name="email"
                                    value={nuevoCliente.email}
                                    onChange={handleNuevoClienteChange}
                                    required
                                    className="w-full border border-gray-300 rounded-lg p-2"
                                />
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="new-client-phone" className="block text-sm font-medium text-gray-700 mb-1">Teléfono</label>
                                    <input
                                        id="new-client-phone"
                                        type="tel"
                                        name="telefono"
                                        value={nuevoCliente.telefono}
                                        onChange={handleNuevoClienteChange}
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="new-client-zone" className="block text-sm font-medium text-gray-700 mb-1">Zona</label>
                                    <input
                                        id="new-client-zone"
                                        type="text"
                                        name="zona"
                                        value={nuevoCliente.zona}
                                        onChange={handleNuevoClienteChange}
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                            </div>
                            <div>
                                <label htmlFor="new-client-password" className="block text-sm font-medium text-gray-700 mb-1">Contraseña temporal *</label>
                                <input
                                    id="new-client-password"
                                    type="password"
                                    name="password_temporal"
                                    value={nuevoCliente.password_temporal}
                                    onChange={handleNuevoClienteChange}
                                    required
                                    className="w-full border border-gray-300 rounded-lg p-2"
                                />
                                <p className="text-xs text-gray-500 mt-1">El cliente podrá cambiarla mediante recuperación de contraseña.</p>
                            </div>
                            <div>
                                <label htmlFor="new-client-reason" className="block text-sm font-medium text-gray-700 mb-1">Motivo *</label>
                                <textarea
                                    id="new-client-reason"
                                    name="motivo"
                                    value={nuevoCliente.motivo}
                                    onChange={handleNuevoClienteChange}
                                    required
                                    minLength={3}
                                    maxLength={500}
                                    rows={3}
                                    className="w-full border border-gray-300 rounded-lg p-2"
                                    placeholder="Ej.: Alta presencial en recepción"
                                />
                            </div>
                            <div className="flex justify-end gap-3 pt-4 border-t">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setModalNuevoClienteAbierto(false);
                                        limpiarNuevoCliente();
                                    }}
                                    disabled={creandoCliente}
                                    className="px-4 py-2 border rounded-lg font-medium"
                                    style={{ borderColor: '#C1B4A4', color: '#817773' }}
                                >
                                    Cancelar
                                </button>
                                <button
                                    type="submit"
                                    disabled={creandoCliente}
                                    className="px-4 py-2 rounded-lg font-bold text-white disabled:opacity-60"
                                    style={{ backgroundColor: '#817773' }}
                                >
                                    {creandoCliente ? 'Creando...' : 'Crear cliente'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

// 👇 ESTA LÍNEA ES CRÍTICA. SI FALTA, APARECE EL ERROR "Element type is invalid"
export default GestionClientes;
