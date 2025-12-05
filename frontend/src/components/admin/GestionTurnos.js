import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionTurnos = () => {
    const [turnos, setTurnos] = useState([]);
    const navigate = useNavigate();
    const [filtroEstado, setFiltroEstado] = useState('solicitado'); // Tab activa por defecto
    const [loading, setLoading] = useState(false);
    const [procesandoId, setProcesandoId] = useState(null); // Para bloquear botones individualmente

    // Cargar turnos cada vez que cambiamos de pestaña
    useEffect(() => {
        cargarTurnos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filtroEstado]);

    const cargarTurnos = async () => {
        setLoading(true);
        try {
            // Usamos el filtro que creamos en el backend
            const res = await axios.get(`http://127.0.0.1:8000/api/gestion/turnos/?estado=${filtroEstado}`);
            setTurnos(res.data);
        } catch (error) {
            console.error("Error cargando turnos", error);
        } finally {
            setLoading(false);
        }
    };

    // Función genérica para cambiar el estado de un turno
    const cambiarEstado = async (id, nuevoEstado) => {
        if (!window.confirm(`¿Estás segura de cambiar el estado a: ${nuevoEstado}?`)) return;

        setProcesandoId(id);
        try {
            await axios.patch(`http://127.0.0.1:8000/api/gestion/turnos/${id}/`, {
                estado: nuevoEstado
            });
            // Recargamos la lista para quitar el turno de esta pestaña
            cargarTurnos();
        } catch (error) {
            alert("Error al actualizar el turno");
            console.error(error);
        } finally {
            setProcesandoId(null);
        }
    };

    // Componente visual para las Tabs
    const TabButton = ({ estado, label }) => (
        <button
            onClick={() => setFiltroEstado(estado)}
            className={`px-4 py-2 font-medium rounded-t-lg border-b-2 transition-colors ${
                filtroEstado === estado
                    ? 'border-rose-500 text-rose-600 bg-rose-50'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
        >
            {label}
        </button>
    );

    return (
        <div className="max-w-6xl mx-auto p-6 mt-8">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-3xl font-bold text-gray-800">Gestión de Turnos</h1>
                <button 
                    onClick={() => navigate('/admin-dashboard')}
                    className="text-gray-500 hover:underline"
                >
                    ← Volver al Dashboard
                </button>
            </div>

            {/* TABS DE NAVEGACIÓN */}
            <div className="flex border-b border-gray-200 mb-6">
                <TabButton estado="solicitado" label="Solicitudes (Análisis)" />
                <TabButton estado="esperando_sena" label="Esperando Seña" />
                <TabButton estado="confirmado" label="Agenda Confirmada" />
                <TabButton estado="realizado" label="Realizados" />
                <TabButton estado="cancelado" label="Cancelados" />
            </div>

            {/* TABLA DE TURNOS */}
            <div className="bg-white shadow rounded-lg overflow-hidden">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando turnos...</div>
                ) : turnos.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No hay turnos en esta sección.</div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Fecha/Hora</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cliente</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Servicio</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Comprobante</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {turnos.map((turno) => (
                                <tr key={turno.id}>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-bold text-gray-900">{turno.fecha}</div>
                                        <div className="text-sm text-gray-500">{turno.hora_inicio} hs</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-medium text-gray-900">{turno.cliente_nombre || `ID: ${turno.cliente}`}</div>
                                        <div className="text-xs text-blue-500 cursor-pointer hover:underline">Ver Perfil Capilar</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                                            {turno.servicio_nombre}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {turno.comprobante_pago ? (
                                            <a 
                                                href={turno.comprobante_pago} 
                                                target="_blank" 
                                                rel="noopener noreferrer"
                                                className="text-blue-500 underline hover:text-blue-700"
                                            >
                                                Ver Comprobante
                                            </a>
                                        ) : <span className="text-gray-400 text-sm">Sin comprobante</span>}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        {/* BOTONES DE ACCIÓN SEGÚN EL ESTADO ACTUAL */}
                                        
                                        {filtroEstado === 'solicitado' && (
                                            <div className="flex justify-end gap-2">
                                                <button 
                                                    onClick={() => cambiarEstado(turno.id, 'cancelado')}
                                                    className="text-red-600 hover:text-red-900 border border-red-200 px-3 py-1 rounded hover:bg-red-50"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Rechazar
                                                </button>
                                                <button 
                                                    onClick={() => cambiarEstado(turno.id, 'esperando_sena')}
                                                    className="bg-rose-500 text-white px-3 py-1 rounded hover:bg-rose-600 shadow-sm"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Aprobar
                                                </button>
                                            </div>
                                        )}

                                        {filtroEstado === 'esperando_sena' && (
                                            <div className="flex justify-end gap-2">
                                                <button 
                                                    onClick={() => cambiarEstado(turno.id, 'cancelado')}
                                                    className="text-gray-500 hover:text-gray-700"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    No pagó
                                                </button>
                                                <button 
                                                    onClick={() => cambiarEstado(turno.id, 'confirmado')}
                                                    className="bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 shadow-sm"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Confirmar Pago
                                                </button>
                                            </div>
                                        )}

                                        {filtroEstado === 'confirmado' && (
                                            <button 
                                                onClick={() => cambiarEstado(turno.id, 'realizado')}
                                                className="bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 shadow-sm"
                                                disabled={procesandoId === turno.id}
                                            >
                                                Marcar como Realizado
                                            </button>
                                        )}

                                        {filtroEstado === 'realizado' && (
                                            <span className="text-green-600 text-xs italic font-semibold">✓ Completado</span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
};

export default GestionTurnos;