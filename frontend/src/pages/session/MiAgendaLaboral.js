import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

import TurnoSemanticActions from '../../components/TurnoSemanticActions';
import { useSession } from '../../context/SessionContext';


const TURNOS_URL = 'http://127.0.0.1:8000/api/gestion/turnos/';


const MiAgendaLaboral = () => {
    const { loading, hasPermission } = useSession();
    const [turnos, setTurnos] = useState([]);
    const [loadingTurnos, setLoadingTurnos] = useState(false);
    const [error, setError] = useState('');
    const [arrivalTurnoId, setArrivalTurnoId] = useState(null);

    const canRegisterArrival = hasPermission('gestion.register_arrival');
    const canReprogram = hasPermission('gestion.reprogram_any_turno');
    const canCancel = hasPermission('gestion.cancel_any_turno');

    const loadAgenda = useCallback(async () => {
        setLoadingTurnos(true);
        setError('');
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(`${TURNOS_URL}mi-agenda-laboral/`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setTurnos(Array.isArray(response.data) ? response.data : []);
        } catch (requestError) {
            setTurnos([]);
            setError('No se pudo cargar tu agenda laboral.');
        } finally {
            setLoadingTurnos(false);
        }
    }, []);

    useEffect(() => {
        loadAgenda();
    }, [loadAgenda]);

    const registerArrival = async (turnoId) => {
        setArrivalTurnoId(turnoId);
        setError('');
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(`${TURNOS_URL}${turnoId}/registrar-llegada/`, {}, {
                headers: { Authorization: `Bearer ${token}` }
            });
            await loadAgenda();
        } catch (requestError) {
            setError(
                requestError.response?.status === 409
                    ? 'El Turno no admite registrar llegada en su estado actual.'
                    : 'No se pudo registrar la llegada.'
            );
        } finally {
            setArrivalTurnoId(null);
        }
    };

    if (loading) {
        return <div className="mt-20 text-center" role="status">Cargando sesión...</div>;
    }

    return (
        <main className="min-h-screen bg-stone-50 px-4 py-10">
            <section className="mx-auto max-w-5xl">
                <h1 className="mb-2 text-3xl font-bold text-stone-700">Mi agenda laboral</h1>
                <p className="mb-8 text-stone-500">Turnos asignados a tu perfil de Personal.</p>
                {error && <p role="alert" className="mb-4 rounded bg-red-50 p-4 text-red-700">{error}</p>}
                <section className="rounded-xl bg-white p-6 shadow" aria-label="Agenda laboral propia">
                    {loadingTurnos ? (
                        <p role="status" className="text-stone-500">Cargando turnos...</p>
                    ) : turnos.length === 0 ? (
                        <p className="text-stone-500">No tenés Turnos asignados.</p>
                    ) : (
                        <ul className="divide-y divide-stone-200">
                            {turnos.map((turno) => (
                                <li key={turno.id} className="flex justify-between gap-4 py-4">
                                    <div>
                                        <p className="font-semibold text-stone-700">{turno.cliente_nombre}</p>
                                        <p className="text-sm text-stone-500">{turno.servicio_nombre}</p>
                                        <p className="text-sm text-stone-600">{turno.fecha} · {turno.hora_inicio}</p>
                                        <p className="text-sm font-medium text-stone-600">Estado: {turno.estado}</p>
                                    </div>
                                    <div className="flex flex-col items-end gap-2">
                                        {canRegisterArrival && turno.estado === 'confirmado' && (
                                            <button type="button" onClick={() => registerArrival(turno.id)} disabled={arrivalTurnoId === turno.id} className="rounded-lg bg-rose-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60">
                                                {arrivalTurnoId === turno.id ? 'Registrando...' : 'Registrar llegada'}
                                            </button>
                                        )}
                                        <TurnoSemanticActions turno={turno} canReprogram={canReprogram} canCancel={canCancel} onCompleted={loadAgenda} onError={setError} />
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
            </section>
        </main>
    );
};


export default MiAgendaLaboral;
