import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { notify } from '../../utils/notificaciones';

const NuevoTurno = () => {
    // Estados para los datos del formulario
    const [servicios, setServicios] = useState([]);
    const [servicioSeleccionado, setServicioSeleccionado] = useState('');
    const [clienteSeleccionado, setClienteSeleccionado] = useState('');
    const [fecha, setFecha] = useState('');
    const [horariosDisponibles, setHorariosDisponibles] = useState([]);
    const [horarioSeleccionado, setHorarioSeleccionado] = useState(null);
    
    // Estados de carga y error
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);
    const [mensajeExito, setMensajeExito] = useState('');

    // 1. Cargar servicios al montar el componente
    useEffect(() => {
        const fetchServicios = async () => {
            try {
                // Ajusta la URL si tu puerto es diferente
                const res = await axios.get('http://127.0.0.1:8000/api/gestion/servicios/');
                setServicios(res.data.results || res.data);
            } catch (err) {
                setError('Error al cargar servicios.');
                console.error(err);
            }
        };
        fetchServicios();
    }, []);

    // 2. Función para consultar disponibilidad (Llama a tu nuevo algoritmo)
    const consultarDisponibilidad = async () => {
        if (!fecha || !servicioSeleccionado) {
            notify.error("Por favor selecciona fecha y servicio.");
            return;
        }
        
        setLoading(true);
        setError('');
        setHorariosDisponibles([]);
        setHorarioSeleccionado(null);

        try {
            const url = `http://127.0.0.1:8000/api/gestion/disponibilidad/?fecha=${fecha}&servicio_id=${servicioSeleccionado}`;
            const res = await axios.get(url);
            setHorariosDisponibles(res.data.horarios_disponibles);
        } catch (err) {
            console.error(err);
            setError('No se pudo calcular la disponibilidad. Revisa si la fecha es válida.');
        } finally {
            setLoading(false);
        }
    };

    // 3. Función para confirmar turno
    const confirmarTurno = async () => {
        if (!clienteSeleccionado) {
            notify.error("¡Falta seleccionar el cliente!");
            return;
        }

        setGuardando(true);
        try {
            const payload = {
                cliente: clienteSeleccionado,
                servicio: servicioSeleccionado,
                fecha: fecha,
                hora_inicio: horarioSeleccionado,
                
                // LÓGICA DE NEGOCIO ADMIN:
                // Al crearlo Yani, saltamos la etapa de "Solicitado" (análisis).
                // El turno nace pre-aprobado, esperando el pago.
                estado: 'esperando_sena' 
            };

            await axios.post('http://127.0.0.1:8000/api/gestion/turnos/', payload);
            
            setMensajeExito("¡Turno creado! Estado: Esperando Seña.");
            // Limpiar formulario
            setClienteSeleccionado('');
            setServicioSeleccionado('');
            setFecha('');
            setHorarioSeleccionado(null);
            setHorariosDisponibles([]);
        } catch (err) {
            console.error(err);
            setError('Error al crear el turno: ' + (err.response?.data?.detail || err.message));
        } finally {
            setGuardando(false);
        }
    };

    return (
        <div className="max-w-2xl mx-auto p-6 bg-white shadow-md rounded-lg mt-10">
            <h2 className="text-2xl font-bold mb-6 text-gray-800">Nuevo Turno (Panel Profesional)</h2>

            {/* SELECCIÓN DE CLIENTE */}
            <div className="mb-4">
                <label className="block text-gray-700 font-medium mb-2">0. Seleccionar Cliente</label>
                <input 
                    type="text" 
                    placeholder="ID del cliente"
                    className="w-full border p-2 rounded"
                    value={clienteSeleccionado}
                    onChange={(e) => setClienteSeleccionado(e.target.value)}
                />
            </div>

            {/* SELECCIÓN DE SERVICIO */}
            <div className="mb-4">
                <label className="block text-gray-700 font-medium mb-2">1. Seleccionar Servicio</label>
                <select 
                    className="w-full border p-2 rounded"
                    value={servicioSeleccionado}
                    onChange={(e) => setServicioSeleccionado(e.target.value)}
                >
                    <option value="">-- Elige un servicio --</option>
                    {servicios.map(s => (
                        <option key={s.id} value={s.id}>
                            {s.nombre} ({s.duracion_estimada} min)
                        </option>
                    ))}
                </select>
            </div>

            {/* SELECCIÓN DE FECHA */}
            <div className="mb-4">
                <label className="block text-gray-700 font-medium mb-2">2. Seleccionar Fecha</label>
                <input 
                    type="date" 
                    className="w-full border p-2 rounded"
                    value={fecha}
                    onChange={(e) => setFecha(e.target.value)}
                />
            </div>

            {/* BOTÓN BUSCAR */}
            <button 
                onClick={consultarDisponibilidad}
                disabled={loading}
                className="w-full bg-rose-500 text-white py-2 px-4 rounded hover:bg-rose-600 transition disabled:bg-gray-300"
            >
                {loading ? 'Buscando huecos...' : 'Ver Horarios Disponibles'}
            </button>

            {/* RESULTADOS (GRILLA DE HORARIOS) */}
            {error && <p className="text-red-500 mt-4">{error}</p>}
            {mensajeExito && <p className="text-green-600 mt-4 font-semibold">{mensajeExito}</p>}

            {horariosDisponibles.length > 0 && (
                <div className="mt-6 animate-fade-in">
                    <h3 className="text-lg font-semibold mb-3">Horarios Disponibles:</h3>
                    <div className="grid grid-cols-3 gap-3">
                        {horariosDisponibles.map((hora) => (
                            <button
                                key={hora}
                                onClick={() => setHorarioSeleccionado(hora)}
                                className={`py-2 px-4 rounded border text-center transition
                                    ${horarioSeleccionado === hora 
                                        ? 'bg-green-500 text-white border-green-600' 
                                        : 'bg-gray-50 hover:bg-gray-100 text-gray-800'
                                    }`}
                            >
                                {hora}
                            </button>
                        ))}
                    </div>
                    
                    {horarioSeleccionado && (
                        <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded">
                            <p className="text-green-800 font-medium">
                                Resumen: Servicio ID {servicioSeleccionado} el {fecha} a las {horarioSeleccionado} hs.
                            </p>
                            <button 
                                onClick={confirmarTurno}
                                disabled={guardando}
                                className="mt-2 w-full bg-green-600 text-white py-2 rounded hover:bg-green-700 disabled:bg-gray-300"
                            >
                                {guardando ? 'Guardando...' : 'Confirmar Turno'}
                            </button>
                        </div>
                    )}
                </div>
            )}
            
            {!loading && horariosDisponibles.length === 0 && fecha && !error && (
                <p className="mt-4 text-gray-500 text-center">No hay horarios disponibles para esta fecha. Intenta otro día.</p>
            )}
        </div>
    );
};

export default NuevoTurno;