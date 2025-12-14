import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import CampanaNotificaciones from '../CampanaNotificaciones';
import Calendario from './Calendario';

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

    if (loading) return <div className="text-center mt-20" style={{ color: '#8B8682' }}>Cargando Panel de Control...</div>;

    return (
        <div className="min-h-screen" style={{ backgroundColor: '#F5EBE0' }}>
            {/* --- CONTENIDO PRINCIPAL --- */}
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
                
                <h2 className="text-3xl font-bold mb-8" style={{ color: '#817773' }}>Hola, Yani</h2>

                {/* --- TARJETAS DE ESTADÍSTICAS (KPIs) --- */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
                    {/* Tarjeta 1: Hoy */}
                    <div className="p-6 rounded-xl shadow-md border-l-4" style={{ backgroundColor: 'white', borderColor: '#D5BDAF' }}>
                        <div className="flex justify-between items-center">
                            <div>
                                <p className="text-sm uppercase font-bold" style={{ color: '#8B8682' }}>Turnos para Hoy</p>
                                <p className="text-4xl font-bold mt-2" style={{ color: '#817773' }}>{stats.turnos_hoy}</p>
                            </div>
                            <div className="p-3 rounded-full" style={{ backgroundColor: '#E3D5CA', color: '#AB9A91' }}>
                                📅
                            </div>
                        </div>
                    </div>

                    {/* Tarjeta 2: Solicitudes */}
                    <div className="p-6 rounded-xl shadow-md border-l-4 cursor-pointer hover:shadow-lg transition-shadow" 
                         onClick={() => navigate('/admin/turnos')}
                         style={{ backgroundColor: 'white', borderColor: '#D5BDAF' }}>
                        <div className="flex justify-between items-center">
                            <div>
                                <p className="text-sm uppercase font-bold" style={{ color: '#8B8682' }}>Solicitudes Nuevas</p>
                                <p className="text-4xl font-bold mt-2" style={{ color: '#817773' }}>{stats.pendientes_accion}</p>
                            </div>
                            <div className="p-3 rounded-full animate-pulse" style={{ backgroundColor: '#E8D5CA', color: '#AB9A91' }}>
                                ⚠️
                            </div>
                        </div>
                        <p className="text-xs mt-2 font-semibold" style={{ color: '#AB9A91' }}>Requieren tu aprobación</p>
                    </div>

                    {/* Tarjeta 3: Señas */}
                    <div className="p-6 rounded-xl shadow-md border-l-4" style={{ backgroundColor: 'white', borderColor: '#D5BDAF' }}>
                        <div className="flex justify-between items-center">
                            <div>
                                <p className="text-sm uppercase font-bold" style={{ color: '#8B8682' }}>Esperando Pago</p>
                                <p className="text-4xl font-bold mt-2" style={{ color: '#817773' }}>{stats.esperando_sena}</p>
                            </div>
                            <div className="p-3 rounded-full" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>
                                💰
                            </div>
                        </div>
                    </div>
                </div>

                {/* --- SECCIÓN DE ACCESOS RÁPIDOS Y AGENDA --- */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    
                    {/* COLUMNA IZQUIERDA: MENÚ RÁPIDO */}
                    <div className="lg:col-span-1 space-y-4">
                        <h3 className="text-xl font-bold mb-4" style={{ color: '#817773' }}>Gestión Rápida</h3>
                        
                        <button 
                            onClick={() => navigate('/admin/gestionar-rutinas')}
                            className="w-full p-4 rounded-lg shadow hover:shadow-md flex items-center gap-4 transition-all"
                            style={{ backgroundColor: 'white' }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                        >
                            <span className="p-2 rounded-lg" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>💅</span>
                            <div className="text-left">
                                <h4 className="font-bold" style={{ color: '#817773' }}>Gestionar Rutinas</h4>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Crear o editar recomendaciones</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/clientes')}
                            className="w-full p-4 rounded-lg shadow hover:shadow-md flex items-center gap-4 transition-all"
                            style={{ backgroundColor: 'white' }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                        >
                            <span className="p-2 rounded-lg" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>👥</span>
                            <div className="text-left">
                                <h4 className="font-bold" style={{ color: '#817773' }}>Clientes</h4>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Ver base de datos y perfiles</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/usuarios')}
                            className="w-full p-4 rounded-lg shadow hover:shadow-md flex items-center gap-4 transition-all"
                            style={{ backgroundColor: 'white' }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                        >
                            <span className="p-2 rounded-lg" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>👤</span>
                            <div className="text-left">
                                <h4 className="font-bold" style={{ color: '#817773' }}>Gestionar Usuarios</h4>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Permisos y cuentas de staff</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/servicios')}
                            className="w-full p-4 rounded-lg shadow hover:shadow-md flex items-center gap-4 transition-all"
                            style={{ backgroundColor: 'white' }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                        >
                            <span className="p-2 rounded-lg" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>⚙️</span>
                            <div className="text-left">
                                <h4 className="font-bold" style={{ color: '#817773' }}>Servicios & Impacto</h4>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Configurar precios y reglas</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/productos')}
                            className="w-full p-4 rounded-lg shadow hover:shadow-md flex items-center gap-4 transition-all"
                            style={{ backgroundColor: 'white' }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                        >
                            <span className="p-2 rounded-lg" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>🛍️</span>
                            <div className="text-left">
                                <h4 className="font-bold" style={{ color: '#817773' }}>Gestionar Productos</h4>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Inventario y catálogo</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/equipamiento')}
                            className="w-full p-4 rounded-lg shadow hover:shadow-md flex items-center gap-4 transition-all"
                            style={{ backgroundColor: 'white' }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                        >
                            <span className="p-2 rounded-lg" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>🔧</span>
                            <div className="text-left">
                                <h4 className="font-bold" style={{ color: '#817773' }}>Gestionar Equipamiento</h4>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Herramientas y estado</p>
                            </div>
                        </button>

                        <button 
                            onClick={() => navigate('/admin/reglas')}
                            className="w-full p-4 rounded-lg shadow hover:shadow-md flex items-center gap-4 transition-all"
                            style={{ backgroundColor: 'white' }}
                            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'}
                            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}
                        >
                            <span className="p-2 rounded-lg" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>🧠</span>
                            <div className="text-left">
                                <h4 className="font-bold" style={{ color: '#817773' }}>Motor de Diagnóstico</h4>
                                <p className="text-xs" style={{ color: '#8B8682' }}>Reglas para asignar rutinas</p>
                            </div>
                        </button>
                    </div>

                    {/* COLUMNA DERECHA: PRÓXIMOS TURNOS CON CALENDARIO */}
                    <div className="lg:col-span-2">
                        <Calendario turnos={stats.proximos_turnos} />
                    </div>
                </div>
            </div>
        </div>
    );
};

export default DashboardAdmin;