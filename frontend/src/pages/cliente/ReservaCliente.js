import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import DatePicker from 'react-datepicker';
import { format, getDay } from 'date-fns';
import es from 'date-fns/locale/es';
import 'react-datepicker/dist/react-datepicker.css';

const ReservaCliente = () => {
    const navigate = useNavigate();

    // Estados
    const [servicios, setServicios] = useState([]);
    const [servicioSeleccionado, setServicioSeleccionado] = useState('');
    const [fechaSeleccionada, setFechaSeleccionada] = useState(null);
    const [horariosDisponibles, setHorariosDisponibles] = useState([]);
    const [horarioSeleccionado, setHorarioSeleccionado] = useState(null);
    
    // UI States
    const [loadingHorarios, setLoadingHorarios] = useState(false);
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

    // Filtro de fechas permitidas: Excluye domingos (0) y miércoles (3)
    const filtrarDiasLaborales = (date) => {
        const day = getDay(date);
        return day !== 0 && day !== 3; // Solo lunes, martes, jueves, viernes, sábado
    };

    // Consultar disponibilidad de horarios
    const consultarDisponibilidad = async () => {
        if (!fechaSeleccionada || !servicioSeleccionado) {
            alert("Completa los campos primero.");
            return;
        }
        
        setLoadingHorarios(true);
        setError('');
        
        try {
            const fechaFormato = format(fechaSeleccionada, 'yyyy-MM-dd');
            const url = `http://127.0.0.1:8000/api/gestion/disponibilidad/?fecha=${fechaFormato}&servicio_id=${servicioSeleccionado}`;
            const res = await axios.get(url);
            setHorariosDisponibles(res.data.horarios_disponibles);
            setPaso(2); // Avanzamos al paso de horarios
        } catch (err) {
            console.error(err);
            setError('Error consultando disponibilidad. Verifica la fecha (no domingos/miércoles/feriados).');
        } finally {
            setLoadingHorarios(false);
        }
    };

    const solicitarTurno = async () => {
        setGuardando(true);
        const token = localStorage.getItem('access_token'); 

        try {
            const fechaFormato = format(fechaSeleccionada, 'yyyy-MM-dd');
            const payload = {
                servicio: servicioSeleccionado,
                fecha: fechaFormato,
                hora_inicio: horarioSeleccionado,
            };

            const config = {
                headers: { Authorization: `Bearer ${token}` }
            };

            await axios.post('http://127.0.0.1:8000/api/gestion/turnos/', payload, config);
            
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

            {/* PASO 1: SELECCIÓN DE SERVICIO Y FECHA */}
            {paso === 1 && (
                <div className="animate-fade-in">
                    {/* Selector de Servicio */}
                    <label className="block text-sm font-medium text-gray-700 mb-2">¿Qué te gustaría hacerte?</label>
                    <select 
                        className="w-full p-3 border border-gray-300 rounded-lg mb-6 focus:ring-2 focus:ring-rose-500 outline-none"
                        value={servicioSeleccionado}
                        onChange={(e) => setServicioSeleccionado(e.target.value)}
                    >
                        <option value="">-- Selecciona un servicio --</option>
                        {servicios.map(s => (
                            <option key={s.id} value={s.id}>
                                {s.nombre} (aprox {s.duracion_estimada} min)
                            </option>
                        ))}
                    </select>

                    {/* DatePicker para Selección de Fecha */}
                    <label className="block text-sm font-medium text-gray-700 mb-2">¿Cuándo?</label>
                    <DatePicker
                        selected={fechaSeleccionada}
                        onChange={setFechaSeleccionada}
                        filterDate={filtrarDiasLaborales}
                        minDate={new Date()}
                        dateFormat="dd/MM/yyyy"
                        placeholderText="Selecciona una fecha"
                        locale={es}
                        className="w-full p-3 border border-gray-300 rounded-lg mb-6 focus:ring-2 focus:ring-rose-500 outline-none"
                        inline={false}
                    />
                    <p className="text-xs text-gray-500 mb-6">🗓️ No atendemos domingos ni miércoles</p>

                    <button 
                        onClick={consultarDisponibilidad}
                        disabled={loadingHorarios || !fechaSeleccionada || !servicioSeleccionado}
                        className="w-full bg-rose-500 text-white py-3 rounded-lg font-bold hover:bg-rose-600 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {loadingHorarios ? 'Buscando huecos...' : 'Ver Horarios'}
                    </button>
                </div>
            )}

            {/* PASO 2: SELECCIÓN DE HORARIO */}
            {paso === 2 && (
                <div className="animate-fade-in">
                    <button 
                        onClick={() => setPaso(1)} 
                        className="text-sm text-gray-500 mb-4 hover:underline flex items-center gap-1"
                    >
                        ← Cambiar fecha/servicio
                    </button>
                    
                    <h3 className="font-semibold text-gray-800 mb-3">
                        Horarios disponibles para el {fechaSeleccionada ? format(fechaSeleccionada, "dd 'de' MMMM", { locale: es }) : ''}:
                    </h3>
                    
                    {horariosDisponibles.length === 0 ? (
                        <div className="text-center py-8 bg-gray-50 rounded-lg">
                            <p className="text-gray-500">Lo sentimos, no quedan turnos para este día.</p>
                            <button 
                                onClick={() => { setPaso(1); setHorariosDisponibles([]); }}
                                className="mt-4 text-rose-500 hover:underline text-sm font-medium"
                            >
                                Intenta otra fecha
                            </button>
                        </div>
                    ) : (
                        <div>
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

                            {horarioSeleccionado && (
                                <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
                                    <p className="text-green-800 text-sm font-medium">
                                        ✓ Turno seleccionado: {horarioSeleccionado}
                                    </p>
                                </div>
                            )}

                            <button 
                                onClick={solicitarTurno}
                                disabled={guardando || !horarioSeleccionado}
                                className="w-full bg-green-600 text-white py-3 rounded-lg font-bold hover:bg-green-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {guardando ? 'Enviando...' : 'Solicitar Turno'}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* Mensaje de Error */}
            {error && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                    <p className="text-red-700 text-sm font-medium">{error}</p>
                </div>
            )}
        </div>
    );
};

export default ReservaCliente;