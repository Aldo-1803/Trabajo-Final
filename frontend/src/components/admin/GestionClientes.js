import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionClientes = () => {
    // --- ESTADOS ---
    const [clientes, setClientes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
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

    // --- RENDERIZADO ---
    return (
        <div className="max-w-7xl mx-auto p-6 mt-8">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">Cartera de Clientes</h1>
                    <p className="text-gray-500">Visualización de perfiles registrados</p>
                </div>
                <button 
                    onClick={() => navigate('/admin-dashboard')}
                    className="text-gray-500 hover:underline"
                >
                    ← Volver al Dashboard
                </button>
            </div>

            {error && (
                <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4">
                    {error}
                </div>
            )}

            <div className="bg-white shadow-lg rounded-lg overflow-hidden border border-gray-200">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando datos...</div>
                ) : clientes.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No hay clientes registrados aún.</div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Cliente</th>
                                    <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Contacto</th>
                                    <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Ubicación</th>
                                    <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Registro</th>
                                    <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">Acciones</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {clientes.map((cliente) => (
                                    <tr key={cliente.id} className="hover:bg-gray-50 transition-colors">
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="flex items-center">
                                                <div className="flex-shrink-0 h-10 w-10 rounded-full bg-pink-100 flex items-center justify-center text-pink-600 font-bold">
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
                                            <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                                                {cliente.zona || 'No especificada'}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                            {cliente.date_joined ? new Date(cliente.date_joined).toLocaleDateString() : '-'}
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                            <button 
                                                className="text-pink-600 hover:text-pink-900 font-bold hover:underline"
                                                onClick={() => alert(`Ver historial de ${cliente.first_name} (Próximamente)`)}
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
    );
};

// 👇 ESTA LÍNEA ES CRÍTICA. SI FALTA, APARECE EL ERROR "Element type is invalid"
export default GestionClientes;