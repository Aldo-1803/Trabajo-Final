import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';


const TURNOS_URL = 'http://127.0.0.1:8000/api/gestion/turnos/';


const GestionTurnos = () => {
    const navigate = useNavigate();
    const [turnos, setTurnos] = useState([]);
    const [filtroEstado, setFiltroEstado] = useState('solicitado');
    const [busqueda, setBusqueda] = useState('');
    const [filtroProfesional, setFiltroProfesional] = useState('');
    const [filtroFecha, setFiltroFecha] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        const cargarTurnos = async () => {
            setLoading(true);
            setError('');

            try {
                const token = localStorage.getItem('access_token');
                const response = await axios.get(TURNOS_URL, {
                    params: {
                        estado: filtroEstado || undefined,
                        search: busqueda || undefined,
                        profesional: filtroProfesional || undefined,
                        fecha: filtroFecha || undefined
                    },
                    headers: { Authorization: `Bearer ${token}` }
                });
                setTurnos(Array.isArray(response.data) ? response.data : []);
            } catch (requestError) {
                console.error('Error cargando turnos', requestError);
                setTurnos([]);
                setError(
                    requestError.response?.status === 403
                        ? 'No tenés permisos para consultar la agenda global.'
                        : 'No se pudo cargar la agenda.'
                );
            } finally {
                setLoading(false);
            }
        };

        cargarTurnos();
    }, [filtroEstado, busqueda, filtroProfesional, filtroFecha]);

    const profesionales = Array.from(
        new Map(
            turnos
                .filter((turno) => turno.profesional)
                .map((turno) => [
                    String(turno.profesional),
                    turno.profesional_nombre || `Personal ${turno.profesional}`
                ])
        )
    );

    const TabButton = ({ estado, label }) => (
        <button
            type="button"
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
        <main className="max-w-6xl mx-auto p-6 mt-8">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">Gestión de Turnos</h1>
                    <p className="mt-1 text-sm text-gray-500">
                        Agenda global en modo solo lectura
                    </p>
                </div>
                <button
                    type="button"
                    onClick={() => navigate('/operaciones')}
                    className="text-gray-500 hover:underline"
                >
                    ← Volver a Operaciones
                </button>
            </div>

            <div className="flex border-b border-gray-200 mb-6 overflow-x-auto">
                <TabButton estado="solicitado" label="Solicitudes" />
                <TabButton estado="esperando_sena" label="Esperando Seña" />
                <TabButton estado="confirmado" label="Confirmados" />
                <TabButton estado="en_proceso" label="En proceso" />
                <TabButton estado="realizado" label="Realizados" />
                <TabButton estado="cancelado" label="Cancelados" />
            </div>

            <section className="bg-white shadow rounded-lg p-4 mb-6" aria-label="Filtros de agenda">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                        <label htmlFor="buscar-turno" className="block text-sm font-medium text-gray-700 mb-2">
                            Buscar Cliente
                        </label>
                        <input
                            id="buscar-turno"
                            type="text"
                            value={busqueda}
                            onChange={(event) => setBusqueda(event.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md"
                        />
                    </div>

                    <div>
                        <label htmlFor="filtrar-profesional" className="block text-sm font-medium text-gray-700 mb-2">
                            Personal
                        </label>
                        <select
                            id="filtrar-profesional"
                            value={filtroProfesional}
                            onChange={(event) => setFiltroProfesional(event.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md"
                        >
                            <option value="">Todo el personal</option>
                            {profesionales.map(([id, nombre]) => (
                                <option key={id} value={id}>{nombre}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label htmlFor="filtrar-fecha" className="block text-sm font-medium text-gray-700 mb-2">
                            Fecha
                        </label>
                        <input
                            id="filtrar-fecha"
                            type="date"
                            value={filtroFecha}
                            onChange={(event) => setFiltroFecha(event.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md"
                        />
                    </div>

                    <div className="flex items-end">
                        <button
                            type="button"
                            onClick={() => {
                                setBusqueda('');
                                setFiltroProfesional('');
                                setFiltroFecha('');
                            }}
                            className="w-full px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
                        >
                            Limpiar filtros
                        </button>
                    </div>
                </div>
            </section>

            {error && (
                <div role="alert" className="mb-6 rounded-lg bg-red-50 p-4 text-red-700">
                    {error}
                </div>
            )}

            <section className="bg-white shadow rounded-lg overflow-hidden" aria-label="Agenda global">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando turnos...</div>
                ) : turnos.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No hay turnos en esta sección.</div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Fecha/Hora</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cliente</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Servicio</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Personal</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Estado</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                            {turnos.map((turno) => (
                                <tr key={turno.id}>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-bold text-gray-900">{turno.fecha}</div>
                                        <div className="text-sm text-gray-500">{turno.hora_inicio} hs</div>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-900">{turno.cliente_nombre}</td>
                                    <td className="px-6 py-4 text-sm text-gray-700">{turno.servicio_nombre}</td>
                                    <td className="px-6 py-4 text-sm text-gray-700">{turno.profesional_nombre || 'Sin asignar'}</td>
                                    <td className="px-6 py-4 text-sm font-semibold text-gray-700">{turno.estado}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </section>
        </main>
    );
};


export default GestionTurnos;
