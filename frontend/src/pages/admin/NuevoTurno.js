import React, { useEffect, useState } from 'react';
import axios from 'axios';

import { notify } from '../../utils/notificaciones';


const API_ROOT = 'http://127.0.0.1:8000/api/gestion';


const NuevoTurno = () => {
    const [servicios, setServicios] = useState([]);
    const [clientes, setClientes] = useState([]);
    const [servicioSeleccionado, setServicioSeleccionado] = useState('');
    const [clienteSeleccionado, setClienteSeleccionado] = useState('');
    const [fecha, setFecha] = useState('');
    const [slots, setSlots] = useState([]);
    const [slotSeleccionado, setSlotSeleccionado] = useState(null);
    const [loading, setLoading] = useState(false);
    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState('');
    const [mensajeExito, setMensajeExito] = useState('');

    useEffect(() => {
        const cargarSelectores = async () => {
            const token = localStorage.getItem('access_token');
            const headers = { Authorization: `Bearer ${token}` };
            try {
                const [serviciosResponse, clientesResponse] = await Promise.all([
                    axios.get(`${API_ROOT}/servicios/`),
                    axios.get(`${API_ROOT}/turnos/selector-clientes/`, { headers })
                ]);
                setServicios(serviciosResponse.data.results || serviciosResponse.data || []);
                setClientes(clientesResponse.data || []);
            } catch (requestError) {
                console.error(requestError);
                setError('No se pudieron cargar los datos necesarios para crear el Turno.');
            }
        };

        cargarSelectores();
    }, []);

    const consultarDisponibilidad = async () => {
        if (!fecha || !servicioSeleccionado) {
            notify.error('Seleccioná una fecha y un Servicio.');
            return;
        }

        setLoading(true);
        setError('');
        setSlots([]);
        setSlotSeleccionado(null);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(
                `${API_ROOT}/turnos/consultar_disponibilidad/`,
                {
                    params: {
                        fecha,
                        servicio_id: servicioSeleccionado
                    },
                    headers: { Authorization: `Bearer ${token}` }
                }
            );
            const selectedDay = (response.data.disponibilidad || [])
                .find((day) => day.fecha === fecha);
            const availableSlots = (selectedDay?.profesionales || []).flatMap(
                (professional) => professional.slots.map((slot) => ({
                    ...slot,
                    profesional_nombre: professional.nombre
                }))
            );
            setSlots(availableSlots);
        } catch (requestError) {
            console.error(requestError);
            setError(
                requestError.response?.data?.error
                || 'No se pudo consultar la disponibilidad.'
            );
        } finally {
            setLoading(false);
        }
    };

    const confirmarTurno = async () => {
        if (!clienteSeleccionado || !slotSeleccionado) {
            notify.error('Seleccioná Cliente y horario.');
            return;
        }

        setGuardando(true);
        setError('');
        setMensajeExito('');
        try {
            const token = localStorage.getItem('access_token');
            const payload = {
                cliente_id: Number(clienteSeleccionado),
                servicio: Number(servicioSeleccionado),
                profesional: slotSeleccionado.profesional_id,
                fecha,
                hora_inicio: slotSeleccionado.hora
            };
            const response = await axios.post(
                `${API_ROOT}/turnos/crear-para-cliente/`,
                payload,
                { headers: { Authorization: `Bearer ${token}` } }
            );

            setMensajeExito(response.data?.mensaje || 'Turno solicitado correctamente.');
            setClienteSeleccionado('');
            setServicioSeleccionado('');
            setFecha('');
            setSlots([]);
            setSlotSeleccionado(null);
        } catch (requestError) {
            console.error(requestError);
            const data = requestError.response?.data;
            const fieldError = Object.values(data || {}).find(Array.isArray)?.[0];
            setError(fieldError || data?.detail || 'No se pudo crear el Turno.');
        } finally {
            setGuardando(false);
        }
    };

    return (
        <main className="max-w-2xl mx-auto p-6 bg-white shadow-md rounded-lg mt-10">
            <h1 className="text-2xl font-bold mb-2 text-gray-800">Nuevo Turno</h1>
            <p className="mb-6 text-sm text-gray-500">
                El Turno se registra como solicitado y queda pendiente de aprobación.
            </p>

            <div className="mb-4">
                <label htmlFor="turno-cliente" className="block text-gray-700 font-medium mb-2">
                    Cliente
                </label>
                <select
                    id="turno-cliente"
                    className="w-full border p-2 rounded"
                    value={clienteSeleccionado}
                    onChange={(event) => setClienteSeleccionado(event.target.value)}
                >
                    <option value="">-- Seleccioná un Cliente --</option>
                    {clientes.map((cliente) => (
                        <option key={cliente.id} value={cliente.id}>
                            {[cliente.nombre, cliente.apellido].filter(Boolean).join(' ') || cliente.email}
                            {cliente.email ? ` — ${cliente.email}` : ''}
                        </option>
                    ))}
                </select>
            </div>

            <div className="mb-4">
                <label htmlFor="turno-servicio" className="block text-gray-700 font-medium mb-2">
                    Servicio
                </label>
                <select
                    id="turno-servicio"
                    className="w-full border p-2 rounded"
                    value={servicioSeleccionado}
                    onChange={(event) => {
                        setServicioSeleccionado(event.target.value);
                        setSlots([]);
                        setSlotSeleccionado(null);
                    }}
                >
                    <option value="">-- Seleccioná un Servicio --</option>
                    {servicios.map((servicio) => (
                        <option key={servicio.id} value={servicio.id}>
                            {servicio.nombre} ({servicio.duracion_estimada || 60} min)
                        </option>
                    ))}
                </select>
            </div>

            <div className="mb-4">
                <label htmlFor="turno-fecha" className="block text-gray-700 font-medium mb-2">
                    Fecha
                </label>
                <input
                    id="turno-fecha"
                    type="date"
                    className="w-full border p-2 rounded"
                    value={fecha}
                    onChange={(event) => {
                        setFecha(event.target.value);
                        setSlots([]);
                        setSlotSeleccionado(null);
                    }}
                />
            </div>

            <button
                type="button"
                onClick={consultarDisponibilidad}
                disabled={loading}
                className="w-full bg-rose-500 text-white py-2 px-4 rounded hover:bg-rose-600 disabled:bg-gray-300"
            >
                {loading ? 'Buscando horarios...' : 'Ver horarios disponibles'}
            </button>

            {error && <p role="alert" className="text-red-600 mt-4">{error}</p>}
            {mensajeExito && <p className="text-green-700 mt-4 font-semibold">{mensajeExito}</p>}

            {slots.length > 0 && (
                <section className="mt-6" aria-labelledby="available-slots-title">
                    <h2 id="available-slots-title" className="text-lg font-semibold mb-3">
                        Horarios disponibles
                    </h2>
                    <div className="grid grid-cols-2 gap-3">
                        {slots.map((slot) => {
                            const key = `${slot.profesional_id}-${slot.hora}`;
                            const selected = (
                                slotSeleccionado?.profesional_id === slot.profesional_id
                                && slotSeleccionado?.hora === slot.hora
                            );
                            return (
                                <button
                                    key={key}
                                    type="button"
                                    onClick={() => setSlotSeleccionado(slot)}
                                    className={`py-2 px-3 rounded border ${
                                        selected
                                            ? 'bg-green-600 text-white'
                                            : 'bg-gray-50 text-gray-800'
                                    }`}
                                >
                                    {slot.hora} — {slot.profesional_nombre}
                                </button>
                            );
                        })}
                    </div>
                </section>
            )}

            {slotSeleccionado && (
                <button
                    type="button"
                    onClick={confirmarTurno}
                    disabled={guardando}
                    className="mt-6 w-full bg-green-600 text-white py-2 rounded hover:bg-green-700 disabled:bg-gray-300"
                >
                    {guardando ? 'Guardando...' : 'Crear Turno solicitado'}
                </button>
            )}
        </main>
    );
};


export default NuevoTurno;
