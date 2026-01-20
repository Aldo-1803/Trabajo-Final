import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { notify, confirmarAccion } from '../../utils/notificaciones';

const ReservaCliente = () => {
    const navigate = useNavigate();

    // Estados
    const [servicios, setServicios] = useState([]);
    const [servicioSeleccionado, setServicioSeleccionado] = useState('');
    const [disponibilidad, setDisponibilidad] = useState([]);
    const [fechaSeleccionada, setFechaSeleccionada] = useState(null);
    const [profesionalSeleccionado, setProfesionalSeleccionado] = useState(null);
    const [horariosDelDia, setHorariosDelDia] = useState([]);
    const [horarioSeleccionado, setHorarioSeleccionado] = useState(null);
    
    // UI States
    const [loadingServicios, setLoadingServicios] = useState(false);
    const [loadingDisponibilidad, setLoadingDisponibilidad] = useState(false);
    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState('');
    const [paso, setPaso] = useState(1); // 1: Servicio, 2: Fecha, 3: Horario
    const [servicioInfo, setServicioInfo] = useState(null); // Guardar nombre y duración del servicio seleccionado

    // Cargar Servicios al iniciar
    useEffect(() => {
        const fetchServicios = async () => {
            try {
                setLoadingServicios(true);
                const res = await axios.get('http://127.0.0.1:8000/api/gestion/servicios/');
                setServicios(res.data);
            } catch (err) {
                console.error(err);
                notify.error('No pudimos cargar los servicios. Intenta luego.');
            } finally {
                setLoadingServicios(false);
            }
        };
        fetchServicios();
    }, []);

    // DISPARADOR AUTOMÁTICO: Consultar disponibilidad cuando selecciona servicio
    useEffect(() => {
        if (servicioSeleccionado) {
            consultarDisponibilidad(servicioSeleccionado);
        }
    }, [servicioSeleccionado]);

    // Consultar disponibilidad para un servicio
    const consultarDisponibilidad = async (servicioId) => {
        setLoadingDisponibilidad(true);
        setError('');
        setDisponibilidad([]);
        setFechaSeleccionada(null);
        setProfesionalSeleccionado(null);
        setHorarioSeleccionado(null);
        
        try {
            const url = `http://127.0.0.1:8000/api/gestion/turnos/consultar_disponibilidad/?servicio_id=${servicioId}`;
            const res = await axios.get(url);
            
            // Guardar info del servicio
            setServicioInfo({
                id: servicioId,
                nombre: res.data.servicio_nombre,
                duracion: res.data.duracion_minutos
            });
            
            setDisponibilidad(res.data.disponibilidad || []);
            
            if (res.data.disponibilidad && res.data.disponibilidad.length > 0) {
                setPaso(2); // Avanzamos a seleccionar fecha
            } else {
                // Si no hay disponibilidad, mostrar mensaje
                const mensaje = res.data.mensaje || 'No hay disponibilidad en este momento.';
                notify.error(mensaje);
            }
        } catch (err) {
            console.error(err);
            const msgError = err.response?.data?.error || 'Error consultando disponibilidad. Intenta más tarde.';
            notify.error(msgError);
        } finally {
            setLoadingDisponibilidad(false);
        }
    };

    // Cuando selecciona una fecha, mostrar profesionales y horarios disponibles
    const seleccionarFecha = (fechaDisponible) => {
        setFechaSeleccionada(fechaDisponible);
        setHorarioSeleccionado(null);
        
        // Si solo hay un profesional, auto-seleccionarlo
        if (fechaDisponible.profesionales.length === 1) {
            const prof = fechaDisponible.profesionales[0];
            setProfesionalSeleccionado(prof);
            setHorariosDelDia(prof.slots);
        } else {
            // Múltiples profesionales, resetear selección
            setProfesionalSeleccionado(null);
            setHorariosDelDia([]);
        }
        
        setPaso(3);
    };

    // Cuando selecciona un profesional, mostrar sus horarios
    const seleccionarProfesional = (profesional) => {
        setProfesionalSeleccionado(profesional);
        setHorariosDelDia(profesional.slots);
        setHorarioSeleccionado(null);
    };

    const solicitarTurno = async () => {
        if (!horarioSeleccionado || !profesionalSeleccionado || !fechaSeleccionada) {
            notify.error("Por favor completa todos los datos.");
            return;
        }

        // Mostrar confirmación con SweetAlert2
        try {
            const result = await confirmarAccion({
                title: "Confirmar Solicitud de Turno",
                html: `
                    <div style="text-align: left; font-size: 14px;">
                        <p><strong>Servicio:</strong> ${servicioInfo?.nombre}</p>
                        <p><strong>Fecha:</strong> ${fechaSeleccionada.dia_semana}, ${fechaSeleccionada.fecha}</p>
                        <p><strong>Hora:</strong> ${horarioSeleccionado.hora}</p>
                        <p><strong>Profesional:</strong> ${profesionalSeleccionado.nombre}</p>
                    </div>
                `,
                confirmButtonText: "Solicitar Turno"
            });
            
            if (!result.isConfirmed) return;
        } catch (err) {
            console.error("Error en confirmación:", err);
            return;
        }

        setGuardando(true);
        const token = localStorage.getItem('access_token'); 

        try {
            // Capturar profesional_id del slot seleccionado
            const profesionalIdDelSlot = horarioSeleccionado.profesional_id;
            
            const payload = {
                servicio: servicioSeleccionado,
                fecha: fechaSeleccionada.fecha, // Ya viene en formato YYYY-MM-DD
                hora_inicio: horarioSeleccionado.hora,
                profesional: profesionalIdDelSlot, // Usar el ID del slot
            };

            const config = {
                headers: { Authorization: `Bearer ${token}` }
            };

            await axios.post('http://127.0.0.1:8000/api/gestion/turnos/', payload, config);
            
            notify.success("¡Solicitud enviada! Yani revisará tu perfil y te confirmará pronto.");
            
            // Resetear el formulario
            setServicioSeleccionado('');
            setDisponibilidad([]);
            setFechaSeleccionada(null);
            setProfesionalSeleccionado(null);
            setHorarioSeleccionado(null);
            setPaso(1);
            
            navigate('/perfil');

        } catch (err) {
            console.error(err);
            const msgError = err.response?.data?.error || "Hubo un problema al enviar la solicitud.";
            notify.error(msgError);
        } finally {
            setGuardando(false);
        }
    };

    // Skeleton Loading
    const SkeletonSlot = () => (
        <div className="p-3 rounded-lg bg-gray-200 animate-pulse h-10"></div>
    );

    const SkeletonFecha = () => (
        <div className="p-3 rounded-lg bg-gray-200 animate-pulse h-16"></div>
    );

    return (
        <div className="max-w-lg mx-auto p-6 bg-white shadow-lg rounded-xl mt-8 border border-gray-100">
            <h2 className="text-2xl font-bold text-gray-800 mb-2 text-center">Reserva tu Cita</h2>
            <p className="text-gray-500 text-center mb-6 text-sm">Diseñemos juntos tu mejor look.</p>

            {/* PASO 1: SELECCIÓN DE SERVICIO */}
            {paso === 1 && (
                <div className="animate-fade-in">
                    <label className="block text-sm font-medium text-gray-700 mb-2">¿Qué te gustaría hacerte?</label>
                    <select 
                        className="w-full p-3 border border-gray-300 rounded-lg mb-6 focus:ring-2 focus:ring-rose-500 outline-none"
                        value={servicioSeleccionado}
                        onChange={(e) => setServicioSeleccionado(e.target.value)}
                        disabled={loadingServicios}
                    >
                        <option value="">-- Selecciona un servicio --</option>
                        {servicios.map(s => (
                            <option key={s.id} value={s.id}>
                                {s.nombre} (aprox {s.duracion_estimada} min)
                            </option>
                        ))}
                    </select>
                    
                    {loadingDisponibilidad && (
                        <div className="text-center">
                            <p className="text-gray-500 text-sm mb-3">Buscando disponibilidad...</p>
                            <div className="space-y-2">
                                <SkeletonFecha />
                                <SkeletonFecha />
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* PASO 2: SELECCIÓN DE FECHA */}
            {paso === 2 && (
                <div className="animate-fade-in">
                    <button 
                        onClick={() => { setPaso(1); setServicioSeleccionado(''); setDisponibilidad([]); }} 
                        className="text-sm text-gray-500 mb-4 hover:underline flex items-center gap-1"
                    >
                        ← Cambiar servicio
                    </button>
                    
                    <h3 className="font-semibold text-gray-800 mb-4">
                        Fechas disponibles para {servicioInfo?.nombre}:
                    </h3>
                    
                    {loadingDisponibilidad ? (
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-6">
                            <SkeletonFecha />
                            <SkeletonFecha />
                            <SkeletonFecha />
                        </div>
                    ) : disponibilidad.length === 0 ? (
                        <div className="text-center py-8 bg-gray-50 rounded-lg">
                            <p className="text-gray-500">No hay disponibilidad en este momento.</p>
                            <button 
                                onClick={() => setServicioSeleccionado('')}
                                className="mt-4 text-rose-500 hover:underline text-sm font-medium"
                            >
                                Intenta otro servicio
                            </button>
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-6">
                            {disponibilidad.map((dia, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => seleccionarFecha(dia)}
                                    className={`p-3 rounded-lg text-sm font-medium border transition
                                        ${fechaSeleccionada?.fecha === dia.fecha 
                                            ? 'bg-rose-500 text-white border-rose-600 ring-2 ring-rose-300' 
                                            : 'bg-white text-gray-600 border-gray-200 hover:border-rose-300'}`}
                                >
                                    <div className="font-bold">{dia.dia_semana}</div>
                                    <div className="text-xs">{dia.fecha}</div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* PASO 3: SELECCIÓN DE PROFESIONAL Y HORARIO */}
            {paso === 3 && fechaSeleccionada && (
                <div className="animate-fade-in">
                    <button 
                        onClick={() => setPaso(2)} 
                        className="text-sm text-gray-500 mb-4 hover:underline flex items-center gap-1"
                    >
                        ← Cambiar fecha
                    </button>
                    
                    <h3 className="font-semibold text-gray-800 mb-4">
                        {fechaSeleccionada.dia_semana}, {fechaSeleccionada.fecha}
                    </h3>

                    {/* Selector de Profesional - Solo mostrar si hay múltiples */}
                    {fechaSeleccionada.profesionales.length > 1 && (
                        <div className="mb-6">
                            <label className="block text-sm font-medium text-gray-700 mb-3">
                                ¿Con quién te gustaría?
                            </label>
                            <div className="grid grid-cols-2 gap-2 mb-4">
                                {fechaSeleccionada.profesionales.map(prof => (
                                    <button
                                        key={prof.id}
                                        onClick={() => seleccionarProfesional(prof)}
                                        className={`p-3 rounded-lg text-sm font-medium border transition
                                            ${profesionalSeleccionado?.id === prof.id 
                                                ? 'bg-rose-500 text-white border-rose-600 ring-2 ring-rose-300' 
                                                : 'bg-white text-gray-600 border-gray-200 hover:border-rose-300'}`}
                                    >
                                        {prof.nombre}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Selector de Horario */}
                    {profesionalSeleccionado && (
                        <div className="mb-6">
                            <label className="block text-sm font-medium text-gray-700 mb-3">
                                ¿Qué hora te viene bien?
                            </label>
                            
                            {loadingDisponibilidad ? (
                                <div className="grid grid-cols-3 gap-2">
                                    <SkeletonSlot />
                                    <SkeletonSlot />
                                    <SkeletonSlot />
                                </div>
                            ) : horariosDelDia.length === 0 ? (
                                <p className="text-gray-500 text-sm">Este profesional no tiene horarios disponibles.</p>
                            ) : (
                                <div className="grid grid-cols-3 gap-2">
                                    {horariosDelDia.map((slot, idx) => (
                                        <button
                                            key={idx}
                                            onClick={() => setHorarioSeleccionado(slot)}
                                            className={`py-2 rounded-lg text-sm font-medium border transition
                                                ${horarioSeleccionado?.hora === slot.hora 
                                                    ? 'bg-rose-500 text-white border-rose-600 ring-2 ring-rose-300' 
                                                    : 'bg-white text-gray-600 border-gray-200 hover:border-rose-300'}`}
                                        >
                                            {slot.hora}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {horarioSeleccionado && profesionalSeleccionado && (
                        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
                            <p className="text-green-800 text-sm font-medium">
                                ✓ {fechaSeleccionada.dia_semana}, {fechaSeleccionada.fecha} a las {horarioSeleccionado.hora}
                            </p>
                            <p className="text-green-700 text-sm">
                                Con {profesionalSeleccionado.nombre}
                            </p>
                        </div>
                    )}

                    <button 
                        onClick={solicitarTurno}
                        disabled={guardando || !horarioSeleccionado || !profesionalSeleccionado}
                        className="w-full bg-green-600 text-white py-3 rounded-lg font-bold hover:bg-green-700 transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {guardando ? 'Enviando...' : 'Solicitar Turno'}
                    </button>
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