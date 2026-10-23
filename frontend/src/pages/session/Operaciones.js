import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';


const TURNOS_URL = 'http://127.0.0.1:8000/api/gestion/turnos/';


const localDate = () => {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
};


const Operaciones = () => {
    const { user, loading, hasPermission } = useSession();
    const [turnosHoy, setTurnosHoy] = useState([]);
    const [loadingTurnos, setLoadingTurnos] = useState(false);
    const [errorTurnos, setErrorTurnos] = useState('');

    const canViewAgenda = hasPermission('gestion.view_global_agenda');
    const canCreateWalkinClient = hasPermission('usuarios.create_walkin_client');
    const canCreateTurno = hasPermission('gestion.create_turno_for_client');

    useEffect(() => {
        if (!canViewAgenda) return;

        const cargarTurnosHoy = async () => {
            setLoadingTurnos(true);
            setErrorTurnos('');
            try {
                const token = localStorage.getItem('access_token');
                const response = await axios.get(TURNOS_URL, {
                    params: { fecha: localDate() },
                    headers: { Authorization: `Bearer ${token}` }
                });
                setTurnosHoy(Array.isArray(response.data) ? response.data : []);
            } catch (requestError) {
                console.error('Error cargando turnos de hoy', requestError);
                setTurnosHoy([]);
                setErrorTurnos('No se pudieron cargar los turnos de hoy.');
            } finally {
                setLoadingTurnos(false);
            }
        };

        cargarTurnosHoy();
    }, [canViewAgenda]);

    if (loading) {
        return <div className="text-center mt-20" role="status">Cargando sesión...</div>;
    }

    const displayName = user?.first_name || user?.email || 'Usuario';

    return (
        <main className="min-h-screen px-4 py-10 bg-stone-50">
            <section className="w-full max-w-5xl mx-auto">
                <h1 className="text-3xl font-bold text-stone-700 mb-2">
                    Hola, {displayName}
                </h1>
                <p className="text-stone-500 mb-8">Panel operativo</p>

                {!canViewAgenda && !canCreateWalkinClient && !canCreateTurno && (
                    <div className="rounded-xl bg-white p-6 shadow text-stone-600">
                        No hay operaciones habilitadas para esta cuenta.
                    </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {canViewAgenda && (
                        <section className="lg:col-span-2 rounded-xl bg-white p-6 shadow" aria-labelledby="turnos-hoy-title">
                            <div className="flex items-center justify-between gap-4 mb-5">
                                <h2 id="turnos-hoy-title" className="text-2xl font-bold text-stone-700">
                                    Turnos de hoy
                                </h2>
                                <Link
                                    to="/admin/turnos"
                                    className="font-semibold text-rose-700 hover:underline"
                                >
                                    Ver agenda
                                </Link>
                            </div>

                            {loadingTurnos ? (
                                <p role="status" className="text-stone-500">Cargando turnos...</p>
                            ) : errorTurnos ? (
                                <p role="alert" className="text-red-700">{errorTurnos}</p>
                            ) : turnosHoy.length === 0 ? (
                                <p className="text-stone-500">No hay turnos para hoy.</p>
                            ) : (
                                <ul className="divide-y divide-stone-200">
                                    {turnosHoy.map((turno) => (
                                        <li key={turno.id} className="py-3 flex justify-between gap-4">
                                            <div>
                                                <p className="font-semibold text-stone-700">{turno.cliente_nombre}</p>
                                                <p className="text-sm text-stone-500">{turno.servicio_nombre}</p>
                                            </div>
                                            <span className="font-semibold text-stone-600">{turno.hora_inicio}</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </section>
                    )}

                    {canCreateWalkinClient && (
                        <section className="rounded-xl bg-white p-6 shadow">
                            <h2 className="text-xl font-bold text-stone-700 mb-3">Clientes</h2>
                            <p className="text-sm text-stone-500 mb-5">
                                Registrá un Cliente presencial desde la gestión existente.
                            </p>
                            <Link
                                to="/admin/clientes"
                                className="inline-flex rounded-lg bg-stone-700 px-4 py-2 font-semibold text-white hover:bg-stone-800"
                            >
                                Nuevo cliente
                            </Link>
                        </section>
                    )}

                    {canCreateTurno && (
                        <section className="rounded-xl bg-white p-6 shadow">
                            <h2 className="text-xl font-bold text-stone-700 mb-3">Turnos</h2>
                            <p className="text-sm text-stone-500 mb-5">
                                Registrá una nueva solicitud para un Cliente.
                            </p>
                            <Link
                                to="/admin/nuevo-turno"
                                className="inline-flex rounded-lg bg-rose-700 px-4 py-2 font-semibold text-white hover:bg-rose-800"
                            >
                                Nuevo turno
                            </Link>
                        </section>
                    )}
                </div>
            </section>
        </main>
    );
};


export default Operaciones;
