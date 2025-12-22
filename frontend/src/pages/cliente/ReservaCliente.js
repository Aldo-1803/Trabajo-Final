import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const ReservarCliente = () => {
    const navigate = useNavigate();

    // Estados
    const [servicios, setServicios] = useState([]);
    const [servicioSeleccionado, setServicioSeleccionado] = useState('');
    const [fecha, setFecha] = useState('');
    const [horariosDisponibles, setHorariosDisponibles] = useState([]);
    const [horarioSeleccionado, setHorarioSeleccionado] = useState(null);
    
    // UI States
    const [loading, setLoading] = useState(false);
    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState('');
    const [paso, setPaso] = useState(1); // 1: Servicio/Fecha, 2: Horario, 3: Confirmación

    // Cargar Servicios al iniciar
    useEffect(() => {
        const fetchServicios = async () => {
            try {
                const res = await axios.get('http://127.0.0.1:8000/api/gestion/servicios/');
                setServicios(res.data);
            } catch (err) {
                console.error(err);
                setError('No pudimos cargar los servicios. Intenta luego.');
            }
        };
        fetchServicios();
    }, []);

    const consultarDisponibilidad = async () => {
        if (!fecha || !servicioSeleccionado) {
            alert("Completa los campos primero.");
            return;
        }
        setLoading(true);
        setError('');
        try {
            const url = `http://127.0.0.1:8000/api/gestion/disponibilidad/?fecha=${fecha}&servicio_id=${servicioSeleccionado}`;
            const res = await axios.get(url);
            setHorariosDisponibles(res.data.horarios_disponibles);
            setPaso(2); // Avanzamos al paso de horarios
        } catch (err) {
            setError('Error consultando disponibilidad. Verifica la fecha (no domingos/feriados).');
        } finally {
            setLoading(false);
        }
    };

    const solicitarTurno = async () => {
        setGuardando(true);
        // IMPORTANTE: Obtenemos el token del localStorage para saber quién es
        const token = localStorage.getItem('access_token'); 

        try {
            const payload = {
                servicio: servicioSeleccionado,
                fecha: fecha,
                hora_inicio: horarioSeleccionado,
                // No enviamos 'cliente' ni 'estado', el backend lo pone solo
            };

            const config = {
                headers: { Authorization: `Bearer ${token}` }
            };

            await axios.post('http://127.0.0.1:8000/api/gestion/turnos/', payload, config);
            
            // Éxito: Redirigir al perfil o mostrar mensaje
            alert("¡Solicitud enviada! Yani revisará tu perfil y te confirmará pronto.");
            navigate('/perfil');

        } catch (err) {
            console.error(err);
            setError("Hubo un problema al enviar la solicitud.");
        } finally {
            setGuardando(false);
        }
    };

    return (
        <div className="max-w-lg mx-auto p-6 bg-white shadow-lg rounded-xl mt-8 border border-gray-100">
            <h2 className="text-2xl font-bold text-gray-800 mb-2 text-center">Reserva tu Cita</h2>
            <p className="text-gray-500 text-center mb-6 text-sm">Diseñemos juntos tu mejor look.</p>

            {/* PASO 1: SELECCIÓN */}
            <div className={paso === 1 ? 'block' : 'hidden'}>
                <label className="block text-sm font-medium text-gray-700 mb-1">¿Qué te gustaría hacerte?</label>
                <select 
                    className="w-full p-3 border border-gray-300 rounded-lg mb-4 focus:ring-2 focus:ring-rose-500 outline-none"
                    value={servicioSeleccionado}
                    onChange={(e) => setServicioSeleccionado(e.target.value)}
                >
                    <option value="">-- Selecciona un servicio --</option>
                    {servicios.map(s => (
                        <option key={s.id} value={s.id}>{s.nombre} (aprox {s.duracion_estimada} min)</option>
                    ))}
                </select>

                <label className="block text-sm font-medium text-gray-700 mb-1">¿Cuándo?</label>
                <input 
                    type="date" 
                    className="w-full p-3 border border-gray-300 rounded-lg mb-6 focus:ring-2 focus:ring-rose-500 outline-none"
                    value={fecha}
                    onChange={(e) => setFecha(e.target.value)}
                />

                <button 
                    onClick={consultarDisponibilidad}
                    disabled={loading}
                    className="w-full bg-rose-500 text-white py-3 rounded-lg font-bold hover:bg-rose-600 transition shadow-md"
                >
                    {loading ? 'Buscando huecos...' : 'Ver Horarios'}
                </button>
            </div>

            {/* PASO 2: HORARIOS */}
            {paso === 2 && (
                <div className="animate-fade-in">
                    <button onClick={() => setPaso(1)} className="text-sm text-gray-500 mb-4 hover:underline">← Volver</button>
                    
                    <h3 className="font-semibold text-gray-800 mb-3">Horarios disponibles para el {fecha}:</h3>
                    
                    {horariosDisponibles.length === 0 ? (
                        <div className="text-center py-8 bg-gray-50 rounded-lg">
                            <p className="text-gray-500">Lo sentimos, no quedan turnos para este día.</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-3 gap-3 mb-6">
                            {horariosDisponibles.map(hora => (
                                <button
                                    key={hora}
                                    onClick={() => setHorarioSeleccionado(hora)}
                                    className={`py-2 rounded-lg text-sm font-medium border transition
                                        ${horarioSeleccionado === hora 
                                            ? 'bg-rose-500 text-white border-rose-600 ring-2 ring-rose-300' 
                                            : 'bg-white text-gray-600 border-gray-200 hover:border-rose-300'}`}
                                >
                                    {hora}
                                </button>
                            ))}
                        </div>
                    )}

                    {horarioSeleccionado && (
                        <button 
                            onClick={solicitarTurno}
                            disabled={guardando}
                            className="w-full bg-green-600 text-white py-3 rounded-lg font-bold hover:bg-green-700 transition shadow-md"
                        >
                            {guardando ? 'Enviando...' : 'Solicitar Turno'}
                        </button>
                    )}
                </div>
            )}

            {error && <p className="text-red-500 text-center mt-4 text-sm bg-red-50 p-2 rounded">{error}</p>}
        </div>
    );
};

export default ReservarCliente;