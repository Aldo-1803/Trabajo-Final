import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import CampanaNotificaciones from '../CampanaNotificaciones';

const DashboardAdmin = () => {
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const token = localStorage.getItem('access_token');
                const response = await axios.get('http://127.0.0.1:8000/api/gestion/admin-dashboard/stats/', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                setStats(response.data);
                setLoading(false);
            } catch (error) {
                console.error("Error cargando dashboard", error);
                // Si falla (ej: no es admin), redirigir o mostrar error
                if (error.response && error.response.status === 403) {
                    navigate('/perfil'); // No es admin, volver a perfil cliente
                }
            }
        };
        fetchStats();
    }, [navigate]);

    if (loading) return <div className="text-center mt-20">Cargando Panel de Control...</div>;

    return (
        <div className="min-h-screen bg-gray-50">
            {/* --- HEADER ADMIN --- */}
            <div className="bg-gray-900 text-white shadow-lg">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
                    <div className="flex items-center gap-4">
                        <h1 className="text-2xl font-bold tracking-wider text-pink-500">BOHEMIA ADMIN</h1>
                        <span className="bg-gray-700 text-xs px-2 py-1 rounded text-gray-300">Modo Profesional</span>
                    </div>
                    <div className="flex items-center gap-6">
                        <CampanaNotificaciones />
                        <button 
                            onClick={() => {
                                localStorage.removeItem('access_token');
                                navigate('/login');
                            }}
                            className="text-sm font-semibold hover:text-pink-400"
                        >
                            Salir
                        </button>
                    </div>
                </div>
            </div>

            {/* --- CONTENIDO PRINCIPAL --- */}
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
                
                <h2 className="text-3xl font-bold text-gray-800 mb-8">Hola, Yani</h2>

                {/* --- TARJETAS DE ESTADÍSTICAS (KPIs) --- */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
                    {/* Tarjeta 1: Hoy */}
                    <div className="bg-white p-6 rounded-xl shadow-md border-l-4 border-pink-500">
                        <div className="flex justify-between items-center">
                            <div>
                                <p className="text-gray-500 text-sm uppercase font-bold">Turnos para Hoy</p>
                                <p className="text-4xl font-bold text-gray-800 mt-2">{stats.turnos_hoy}</p>
                            </div>
                            <div className="p-3 bg-pink-100 rounded-full text-pink-600">
                                
                            </div>
                        </div>
                    </div>

                    {/* Tarjeta 2: Solicitudes */}
                    <div className="bg-white p-6 rounded-xl shadow-md border-l-4 border-yellow-500 cursor-pointer hover:shadow-lg transition-shadow"
                         onClick={() => navigate('/admin/turnos')}>
                        <div className="flex justify-between items-center">
                            <div>
                                <p className="text-gray-500 text-sm uppercase font-bold">Solicitudes Nuevas</p>
                                <p className="text-4xl font-bold text-gray-800 mt-2">{stats.pendientes_accion}</p>
                            </div>
                            <div className="p-3 bg-yellow-100 rounded-full text-yellow-600 animate-pulse">
                                
                            </div>
                        </div>
                        <p className="text-xs text-yellow-600 mt-2 font-semibold">Requieren tu aprobación</p>
                    </div>

                    {/* Tarjeta 3: Señas */}
                    <div className="bg-white p-6 rounded-xl shadow-md border-l-4 border-blue-500">
                        <div className="flex justify-between items-center">
                            <div>
                                <p className="text-gray-500 text-sm uppercase font-bold">Esperando Pago</p>
                                <p className="text-4xl font-bold text-gray-800 mt-2">{stats.esperando_sena}</p>
                            </div>
                            <div className="p-3 bg-blue-100 rounded-full text-blue-600">
                                
                            </div>
                        </div>
                    </div>
                </div>

                {/* --- SECCIÓN DE ACCESOS RÁPIDOS Y AGENDA --- */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    
                    {/* COLUMNA IZQUIERDA: MENÚ RÁPIDO */}
                    <div className="lg:col-span-1 space-y-4">
                        <h3 className="text-xl font-bold text-gray-700 mb-4">Gestión Rápida</h3>
                        
                        <button 
                            onClick={() => navigate('/admin/gestionar-rutinas')}
                            className="w-full bg-white p-4 rounded-lg shadow hover:bg-gray-50 flex items-center gap-4 transition-colors text-left group"
                        >
                            <span className="p-2 bg-purple-100 text-purple-600 rounded-lg group-hover:bg-purple-200">💅</span>
                            <div>
                                <h4 className="font-bold text-gray-800">Gestionar Rutinas</h4>
                                <p className="text-xs text-gray-500">Crear o editar recomendaciones</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/clientes')}
                            className="w-full bg-white p-4 rounded-lg shadow hover:bg-gray-50 flex items-center gap-4 transition-colors text-left group"
                        >
                            <span className="p-2 bg-green-100 text-green-600 rounded-lg group-hover:bg-green-200">👥</span>
                            <div>
                                <h4 className="font-bold text-gray-800">Clientes</h4>
                                <p className="text-xs text-gray-500">Ver base de datos y perfiles</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/usuarios')}
                            className="w-full bg-white p-4 rounded-lg shadow hover:bg-gray-50 flex items-center gap-4 transition-colors text-left group"
                        >
                            <span className="p-2 bg-red-100 text-red-600 rounded-lg group-hover:bg-red-200">👤</span>
                            <div>
                                <h4 className="font-bold text-gray-800">Gestionar Usuarios</h4>
                                <p className="text-xs text-gray-500">Permisos y cuentas de staff</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/servicios')}
                            className="w-full bg-white p-4 rounded-lg shadow hover:bg-gray-50 flex items-center gap-4 transition-colors text-left group"
                        >
                            <span className="p-2 bg-blue-100 text-blue-600 rounded-lg group-hover:bg-blue-200">⚙️</span>
                            <div>
                                <h4 className="font-bold text-gray-800">Servicios & Impacto</h4>
                                <p className="text-xs text-gray-500">Configurar precios y reglas</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/productos')}
                            className="w-full bg-white p-4 rounded-lg shadow hover:bg-gray-50 flex items-center gap-4 transition-colors text-left group"
                        >
                            <span className="p-2 bg-orange-100 text-orange-600 rounded-lg group-hover:bg-orange-200">🛍️</span>
                            <div>
                                <h4 className="font-bold text-gray-800">Gestionar Productos</h4>
                                <p className="text-xs text-gray-500">Inventario y catálogo</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/equipamiento')}
                            className="w-full bg-white p-4 rounded-lg shadow hover:bg-gray-50 flex items-center gap-4 transition-colors text-left group"
                        >
                            <span className="p-2 bg-indigo-100 text-indigo-600 rounded-lg group-hover:bg-indigo-200">🔧</span>
                            <div>
                                <h4 className="font-bold text-gray-800">Gestionar Equipamiento</h4>
                                <p className="text-xs text-gray-500">Herramientas y estado</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/reglas')}
                            className="w-full bg-white p-4 rounded-lg shadow hover:bg-gray-50 flex items-center gap-4 transition-colors text-left group"
                        >
                            <span className="p-2 bg-purple-100 text-purple-600 rounded-lg group-hover:bg-purple-200">🧠</span>
                            <div>
                                <h4 className="font-bold text-gray-800">Motor de Diagnóstico</h4>
                                <p className="text-xs text-gray-500">Reglas para asignar rutinas</p>
                            </div>
                        </button>
                    </div>

                    {/* COLUMNA DERECHA: PRÓXIMOS TURNOS */}
                    <div className="lg:col-span-2 bg-white rounded-xl shadow-lg p-6">
                        <h3 className="text-xl font-bold text-gray-700 mb-6 flex items-center gap-2">
                            Agenda Inmediata
                        </h3>

                        {stats.proximos_turnos.length === 0 ? (
                            <p className="text-gray-500">No hay turnos próximos agendados.</p>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead>
                                        <tr className="border-b border-gray-200 text-gray-400 text-sm uppercase">
                                            <th className="py-2">Hora</th>
                                            <th className="py-2">Cliente</th>
                                            <th className="py-2">Servicio</th>
                                            <th className="py-2">Estado</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                        {stats.proximos_turnos.map((turno) => (
                                            <tr key={turno.id} className="hover:bg-gray-50 transition-colors">
                                                <td className="py-4 font-bold text-gray-800">
                                                    {turno.fecha} <span className="text-pink-600">{turno.hora}</span>
                                                </td>
                                                <td className="py-4 text-gray-700 font-medium">{turno.cliente}</td>
                                                <td className="py-4 text-gray-600 text-sm">{turno.servicio}</td>
                                                <td className="py-4">
                                                    <span className={`px-2 py-1 rounded text-xs font-bold ${
                                                        turno.estado === 'confirmado' ? 'bg-green-100 text-green-700' : 
                                                        'bg-yellow-100 text-yellow-700'
                                                    }`}>
                                                        {turno.estado.toUpperCase()}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                        <div className="mt-4 text-right">
                             <button className="text-pink-600 text-sm font-bold hover:underline">Ver agenda completa →</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DashboardAdmin;