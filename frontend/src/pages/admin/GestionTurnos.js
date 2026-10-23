import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

import TurnoSemanticActions from '../../components/TurnoSemanticActions';
import { useSession } from '../../context/SessionContext';


const TURNOS_URL = 'http://127.0.0.1:8000/api/gestion/turnos/';


const GestionTurnos = () => {
    const navigate = useNavigate();
    const { hasPermission } = useSession();
    const [turnos, setTurnos] = useState([]);
    const [filtroEstado, setFiltroEstado] = useState('solicitado');
    const [busqueda, setBusqueda] = useState('');
    const [filtroProfesional, setFiltroProfesional] = useState('');
    const [filtroFecha, setFiltroFecha] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [arrivalTurnoId, setArrivalTurnoId] = useState(null);
    const [arrivalMessage, setArrivalMessage] = useState('');

    const canRegisterArrival = hasPermission('gestion.register_arrival');
    const canReprogramTurno = hasPermission('gestion.reprogram_any_turno');
    const canCancelTurno = hasPermission('gestion.cancel_any_turno');
    const hasTurnoActions = (
        canRegisterArrival || canReprogramTurno || canCancelTurno
    );

    const cargarTurnos = useCallback(async () => {
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
    }, [filtroEstado, busqueda, filtroProfesional, filtroFecha]);

    useEffect(() => {
        cargarTurnos();
    }, [cargarTurnos]);

    const registrarLlegada = async (turnoId) => {
        setArrivalTurnoId(turnoId);
        setArrivalMessage('');
        setError('');

        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                `${TURNOS_URL}${turnoId}/registrar-llegada/`,
                {},
                { headers: { Authorization: `Bearer ${token}` } }
            );
            await cargarTurnos();
            setArrivalMessage('Llegada registrada correctamente.');
        } catch (requestError) {
            console.error('Error registrando llegada', requestError);
            setError(
                requestError.response?.status === 409
                    ? 'El Turno no admite registrar llegada en su estado actual.'
                    : 'No se pudo registrar la llegada.'
            );
        } finally {
            setArrivalTurnoId(null);
        }
    };

    const operationCompleted = async (message) => {
        await cargarTurnos();
        setError('');
        setArrivalMessage(message);
    };

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
                        Consulta de agenda y registro de llegada
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

            {arrivalMessage && (
                <div role="status" className="mb-6 rounded-lg bg-green-50 p-4 text-green-700">
                    {arrivalMessage}
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
                                {hasTurnoActions && (
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Acciones</th>
                                )}
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
                                    {hasTurnoActions && (
                                        <td className="px-6 py-4 text-sm">
                                            {canRegisterArrival && turno.estado === 'confirmado' && (
                                                <button
                                                    type="button"
                                                    onClick={() => registrarLlegada(turno.id)}
                                                    disabled={arrivalTurnoId === turno.id}
                                                    className="rounded-md bg-rose-700 px-3 py-2 font-semibold text-white disabled:opacity-60"
                                                >
                                                    {arrivalTurnoId === turno.id
                                                        ? 'Registrando...'
                                                        : 'Registrar llegada'}
                                                </button>
                                            )}
                                            <TurnoSemanticActions
                                                turno={turno}
                                                canReprogram={canReprogramTurno}
                                                canCancel={canCancelTurno}
                                                onCompleted={operationCompleted}
                                                onError={setError}
                                            />
                                        </td>
                                    )}
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
