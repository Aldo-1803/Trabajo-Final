import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

import ClienteCreationForm from '../../components/ClienteCreationForm';
import { useSession } from '../../context/SessionContext';
import { getLandingPath } from '../../utils/sessionLanding';


const GestionClientes = () => {
    const [clientes, setClientes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [creating, setCreating] = useState(false);
    const navigate = useNavigate();
    const { session, hasPermission } = useSession();
    const canCreateClient = hasPermission('usuarios.create_walkin_client');
    const landingPath = getLandingPath(session) || '/login';

    const fetchClientes = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(
                'http://127.0.0.1:8000/api/usuarios/clientes/',
                { headers: { Authorization: `Bearer ${token}` } }
            );
            setClientes(response.data);
            setError('');
        } catch (requestError) {
            setClientes([]);
            if (requestError.response?.status === 401) {
                navigate('/login');
            } else if (requestError.response?.status === 403) {
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

    return (
        <main className="min-h-screen p-8" style={{ backgroundColor: '#F5F0EB' }}>
            <div className="max-w-7xl mx-auto">
                <div className="mb-6 flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold text-gray-800">Cartera de Clientes</h1>
                        <p className="text-gray-500">Visualización de perfiles registrados</p>
                    </div>
                    <div className="flex gap-3">
                        {canCreateClient && (
                            <button onClick={() => setCreating(true)} className="rounded-lg px-4 py-2 font-bold text-white" style={{ backgroundColor: '#817773' }}>
                                + Nuevo cliente
                            </button>
                        )}
                        <button onClick={() => navigate(landingPath)} className="rounded-lg border px-4 py-2 font-medium" style={{ color: '#817773', borderColor: '#C1B4A4' }}>
                            ← Volver al inicio
                        </button>
                    </div>
                </div>
                {error && <div className="mb-4 rounded-lg bg-red-50 p-4 font-medium text-red-700">{error}</div>}
                <section className="overflow-hidden rounded-lg border bg-white shadow" style={{ borderColor: '#E8DCC4' }}>
                    {loading ? (
                        <div className="p-8 text-center text-gray-500">Cargando datos...</div>
                    ) : clientes.length === 0 ? (
                        <div className="p-8 text-center text-gray-400">No hay clientes registrados aún.</div>
                    ) : (
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-stone-100"><tr><th className="px-6 py-3 text-left">Cliente</th><th className="px-6 py-3 text-left">Contacto</th><th className="px-6 py-3 text-left">Ubicación</th></tr></thead>
                            <tbody className="divide-y divide-gray-200">
                                {clientes.map((cliente) => (
                                    <tr key={cliente.id}>
                                        <td className="px-6 py-4">{cliente.first_name} {cliente.last_name}</td>
                                        <td className="px-6 py-4">{cliente.email}</td>
                                        <td className="px-6 py-4">{cliente.zona || 'No especificada'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </section>
            </div>
            {creating && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
                    <section className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-2xl">
                        <h2 className="mb-2 text-2xl font-bold text-gray-800">Nuevo cliente</h2>
                        <p className="mb-6 text-sm text-gray-500">Alta presencial con acceso mediante contraseña temporal.</p>
                        <ClienteCreationForm
                            onCreated={async () => {
                                setCreating(false);
                                await fetchClientes();
                            }}
                            onCancel={() => setCreating(false)}
                        />
                    </section>
                </div>
            )}
        </main>
    );
};


export default GestionClientes;
