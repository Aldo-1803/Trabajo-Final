import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useNavigate, useLocation } from 'react-router-dom';
import { notify, confirmarAccion } from '../../utils/notificaciones';
import { IconCheckCircle, IconSparkles, IconWarning } from '../../components/common/Icons';

const ReservaCliente = () => {
    const navigate = useNavigate();
    const location = useLocation();

    // Estados
    const [servicios, setServicios] = useState([]);
    const [servicioSeleccionado, setServicioSeleccionado] = useState('');
    const [disponibilidad, setDisponibilidad] = useState([]);
    const [fechaSeleccionada, setFechaSeleccionada] = useState(null);
    const [fechaSugerida, setFechaSugerida] = useState(null); // Para marcar la fecha sugerida
    const [profesionalSeleccionado, setProfesionalSeleccionado] = useState(null);
    const [horariosDelDia, setHorariosDelDia] = useState([]);
    const [horarioSeleccionado, setHorarioSeleccionado] = useState(null);
    const [horarioSugerido, setHorarioSugerido] = useState(null); // Para marcar el horario sugerido
    
    // UI States
    const [loadingServicios, setLoadingServicios] = useState(false);
    const [loadingDisponibilidad, setLoadingDisponibilidad] = useState(false);
    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState('');
    const [bloqueoSaludCapilar, setBloqueoSaludCapilar] = useState(null);
    const [mostrarModalAlertaCapilar, setMostrarModalAlertaCapilar] = useState(false);
    const [mensajeAdvertenciaCapilar, setMensajeAdvertenciaCapilar] = useState('');
    const [paso, setPaso] = useState(1); // 1: Servicio, 2: Fecha, 3: Horario
    const [servicioInfo, setServicioInfo] = useState(null); // Guardar nombre y duración del servicio seleccionado
    const [esDesdeRecomendacion, setEsDesdeRecomendacion] = useState(false); // Rastrear si viene de sugerencia

    // Cargar Servicios al iniciar
    useEffect(() => {
        const fetchServicios = async () => {
            try {
                setLoadingServicios(true);
                const res = await axios.get('http://127.0.0.1:8000/api/gestion/servicios/');
                
                // Filtrar solo servicios que tengan equipamiento configurado
                const serviciosConEquipamiento = res.data.filter(s => 
                    s.requisitos_equipamiento && s.requisitos_equipamiento.length > 0
                );
                
                setServicios(serviciosConEquipamiento);
                
                // Manejo de datos desde notificación (location.state)
                const stateData = location.state || {};
                
                // Si viene desde una notificación con servicio preseleccionado
                if (stateData.servicioPreseleccionado) {
                    setEsDesdeRecomendacion(true);
                    setServicioSeleccionado(stateData.servicioPreseleccionado);
                    
                    // Guardar sugerencias para marcar visualmente después
                    if (stateData.fechaSugerida) {
                        setFechaSugerida(stateData.fechaSugerida);
                    }
                    if (stateData.horaSugerida) {
                        setHorarioSugerido(stateData.horaSugerida);
                    }
                    if (stateData.profesionalId) {
                        setProfesionalSeleccionado(stateData.profesionalId);
                    }
                }
                // Fallback a formato antiguo de FichaRecomendacion
                else if (stateData.servicio_id) {
                    setEsDesdeRecomendacion(true);
                    setServicioSeleccionado(stateData.servicio_id);
                    
                    if (stateData.fecha) {
                        setFechaSugerida(stateData.fecha);
                    }
                    if (stateData.hora) {
                        setHorarioSugerido(stateData.hora);
                    }
                }
            } catch (err) {
                console.error(err);
                notify.error('No pudimos cargar los servicios. Intenta luego.');
            } finally {
                setLoadingServicios(false);
            }
        };
        fetchServicios();
    }, [location]);

    // Cuando selecciona una fecha, mostrar profesionales y horarios disponibles
    const seleccionarFecha = useCallback((fechaDisponible) => {
        setFechaSeleccionada(fechaDisponible);
        setHorarioSeleccionado(null);
        
        // Si solo hay un profesional, auto-seleccionarlo
        if (fechaDisponible.profesionales.length === 1) {
            const prof = fechaDisponible.profesionales[0];
            setProfesionalSeleccionado(prof);
            setHorariosDelDia(prof.slots);
            
            // Si viene de recomendación y hay horario sugerido, intentar auto-seleccionarlo
            if (esDesdeRecomendacion && horarioSugerido) {
                const slotSugerido = prof.slots.find(s => s.hora === horarioSugerido);
                if (slotSugerido) {
                    setTimeout(() => {
                        setHorarioSeleccionado(slotSugerido);
                        notify.info('También pre-cargamos la hora sugerida. Puedes cambiarla cuando quieras.');
                    }, 500);
                }
            }
        } else {
            // Múltiples profesionales, resetear selección
            setProfesionalSeleccionado(null);
            setHorariosDelDia([]);
        }
        
        setPaso(3);
    }, [esDesdeRecomendacion, horarioSugerido]);

    // Consultar disponibilidad para un servicio
    const consultarDisponibilidad = useCallback(async (servicioId) => {
        setLoadingDisponibilidad(true);
        setError('');
        setBloqueoSaludCapilar(null);
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
                
                // Si viene de una recomendación y hay fecha sugerida, intentar auto-seleccionarla
                if (esDesdeRecomendacion && fechaSugerida) {
                    const diaConFecha = res.data.disponibilidad.find(d => d.fecha === fechaSugerida);
                    if (diaConFecha) {
                        setTimeout(() => {
                            seleccionarFecha(diaConFecha);
                            notify.info('Hemos pre-cargado la fecha sugerida. Puedes cambiarla si lo deseas.');
                        }, 500);
                    }
                }
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
    }, [esDesdeRecomendacion, fechaSugerida, seleccionarFecha]);

    // DISPARADOR AUTOMÁTICO: Consultar disponibilidad cuando selecciona servicio
    useEffect(() => {
        if (servicioSeleccionado) {
            consultarDisponibilidad(servicioSeleccionado);
        }
    }, [servicioSeleccionado, consultarDisponibilidad]);

    // Cuando selecciona un profesional, mostrar sus horarios
    const seleccionarProfesional = (profesional) => {
        setProfesionalSeleccionado(profesional);
        setHorariosDelDia(profesional.slots);
        setHorarioSeleccionado(null);
        
        // Si viene de recomendación y hay horario sugerido, intentar auto-seleccionarlo
        if (esDesdeRecomendacion && horarioSugerido) {
            const slotSugerido = profesional.slots.find(s => s.hora === horarioSugerido);
            if (slotSugerido) {
                setTimeout(() => {
                    setHorarioSeleccionado(slotSugerido);
                }, 300);
            }
        }
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

            const response = await axios.post('http://127.0.0.1:8000/api/gestion/turnos/reservar/', payload, config);
            const alertaDanoCapilar = response.data?.alerta_daño_capilar;
            const advertenciaCapilar = response.data?.advertencia;
             
            notify.success(response.data?.mensaje || "¡Solicitud enviada! Yani revisará tu perfil y te confirmará pronto.");
            setError('');
            setBloqueoSaludCapilar(null);

            if (alertaDanoCapilar) {
                setMensajeAdvertenciaCapilar(
                    advertenciaCapilar || 'Este turno requiere evaluación profesional por posible riesgo capilar.'
                );
                setMostrarModalAlertaCapilar(true);
                return;
            }
            
            // Resetear el formulario
            setServicioSeleccionado('');
            setDisponibilidad([]);
            setFechaSeleccionada(null);
            setProfesionalSeleccionado(null);
            setHorarioSeleccionado(null);
            setPaso(1);
            
            navigate('/mis-turnos');

        } catch (err) {
            console.error(err);
            const data = err.response?.data;

            if (err.response?.status === 400 && data?.bloqueo_salud_capilar) {
                setBloqueoSaludCapilar(data.bloqueo_salud_capilar);
                const mensaje = Array.isArray(data.non_field_errors)
                    ? data.non_field_errors[0]
                    : data.non_field_errors || "Por ahora no puedes solicitar este turno.";
                setError(mensaje);
                notify.error(mensaje);
                return;
            }

            const msgError =
                data?.error ||
                (Array.isArray(data?.non_field_errors) ? data.non_field_errors[0] : data?.non_field_errors) ||
                "Hubo un problema al enviar la solicitud.";

            setError(msgError);
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
            {mostrarModalAlertaCapilar && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="alerta-capilar-title"
                >
                    <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl border border-amber-200 overflow-hidden">
                        <div className="bg-gradient-to-r from-amber-100 to-orange-100 px-6 py-5">
                            <div className="flex items-center gap-3">
                                <div className="flex h-11 w-11 items-center justify-center rounded-full bg-amber-200 text-amber-800">
                                    <IconWarning className="h-6 w-6" />
                                </div>
                                <div>
                                    <h3 id="alerta-capilar-title" className="text-lg font-bold text-amber-950">
                                        Advertencia de seguridad capilar
                                    </h3>
                                    <p className="text-xs text-amber-800">Tu turno fue solicitado correctamente.</p>
                                </div>
                            </div>
                        </div>

                        <div className="px-6 py-5">
                            <p className="text-sm leading-6 text-gray-800 mb-3">
                                {mensajeAdvertenciaCapilar}
                            </p>
                            <p className="text-sm leading-6 text-gray-600 bg-amber-50 border border-amber-100 rounded-lg p-3">
                                Yanina evaluará el estado de tu fibra capilar basándose en tus servicios recientes antes de la confirmación final. Te avisaremos por las notificaciones del sistema.
                            </p>
                        </div>

                        <div className="px-6 py-4 bg-gray-50 flex justify-end">
                            <button
                                type="button"
                                onClick={() => navigate('/mis-turnos')}
                                className="rounded-lg bg-amber-600 px-5 py-2.5 text-sm font-bold text-white shadow hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2"
                            >
                                Entendido, ir a Mis Turnos
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <h2 className="text-2xl font-bold text-gray-800 mb-2 text-center">Reserva tu Cita</h2>
            <p className="text-gray-500 text-center mb-6 text-sm">Diseñemos juntos tu mejor look.</p>

            {/* PASO 1: SELECCIÓN DE SERVICIO */}
            {paso === 1 && (
                <div className="animate-fade-in">
                    {esDesdeRecomendacion && (
                        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-2">
                            <IconSparkles className="h-5 w-5 text-blue-600" />
                            <p className="text-blue-800 text-sm">
                                <strong>Venes de una recomendación:</strong> El servicio ya está pre-seleccionado. Puedes cambiar si lo prefieres.
                            </p>
                        </div>
                    )}
                    <label className="block text-sm font-medium text-gray-700 mb-2">¿Qué te gustaría hacerte?</label>
                    
                    {!loadingServicios && servicios.length === 0 && (
                        <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                            <p className="text-amber-800 text-sm">
                                <strong className="inline-flex items-center gap-2">
                                    <IconWarning className="h-4 w-4" /> Servicios no disponibles
                                </strong><br/>
                                Por el momento no hay servicios disponibles para reservar. Por favor, contáctanos para más información.
                            </p>
                        </div>
                    )}
                    
                    <select 
                        className="w-full p-3 border border-gray-300 rounded-lg mb-6 focus:ring-2 focus:ring-rose-500 outline-none"
                        value={servicioSeleccionado}
                        onChange={(e) => {
                            setBloqueoSaludCapilar(null);
                            setError('');
                            setServicioSeleccionado(e.target.value);
                        }}
                        disabled={loadingServicios || servicios.length === 0}
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
                                    className={`p-3 rounded-lg text-sm font-medium border transition relative
                                        ${fechaSeleccionada?.fecha === dia.fecha 
                                            ? 'bg-rose-500 text-white border-rose-600 ring-2 ring-rose-300' 
                                            : 'bg-white text-gray-600 border-gray-200 hover:border-rose-300'}`}
                                >
                                    <div className="font-bold">{dia.dia_semana}</div>
                                    <div className="text-xs">{dia.fecha}</div>
                                    {/* Badge de sugerencia */}
                                    {esDesdeRecomendacion && fechaSugerida === dia.fecha && (
                                        <div className="absolute top-0 right-0 bg-yellow-400 text-yellow-900 text-xs px-2 py-1 rounded-bl-lg rounded-tr-lg font-bold inline-flex items-center gap-1">
                                            <IconCheckCircle className="h-3 w-3" /> Sugerida
                                        </div>
                                    )}
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
                                            className={`py-2 rounded-lg text-sm font-medium border transition relative
                                                ${horarioSeleccionado?.hora === slot.hora 
                                                    ? 'bg-rose-500 text-white border-rose-600 ring-2 ring-rose-300' 
                                                    : 'bg-white text-gray-600 border-gray-200 hover:border-rose-300'}`}
                                        >
                                            {slot.hora}
                                            {/* Badge de sugerencia */}
                                            {esDesdeRecomendacion && horarioSugerido === slot.hora && (
                                                <div className="absolute -top-2 -right-2 bg-yellow-400 text-yellow-900 text-xs px-1 py-0 rounded-full font-bold flex items-center justify-center w-5 h-5">
                                                    <IconCheckCircle className="h-3 w-3" />
                                                </div>
                                            )}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {horarioSeleccionado && profesionalSeleccionado && (
                        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
                            <p className="text-green-800 text-sm font-medium inline-flex items-center gap-2">
                                <IconCheckCircle className="h-4 w-4" /> {fechaSeleccionada.dia_semana}, {fechaSeleccionada.fecha} a las {horarioSeleccionado.hora}
                            </p>
                            <p className="text-green-700 text-sm">
                                Con {profesionalSeleccionado.nombre}
                            </p>
                        </div>
                    )}

                    {bloqueoSaludCapilar && (
                        <div className="mb-4 p-4 rounded-xl border border-rose-200 bg-gradient-to-r from-rose-50 via-white to-orange-50 shadow-sm">
                            <div className="flex items-start gap-3">
                                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-100 text-rose-600 font-bold text-lg">
                                    ✨
                                </div>
                                <div className="flex-1">
                                    <p className="text-rose-900 font-semibold text-sm mb-1">
                                        Cuidemos primero la salud de tu cabello
                                    </p>
                                    <p className="text-rose-800 text-sm leading-6">
                                        Tu último proceso químico fue <strong>{bloqueoSaludCapilar.servicio_previo}</strong> y aún faltan{' '}
                                        <strong>{bloqueoSaludCapilar.dias_restantes} días</strong> para poder agendar{' '}
                                        <strong>{bloqueoSaludCapilar.servicio_solicitado}</strong> con seguridad.
                                    </p>
                                    <p className="text-rose-700 text-xs mt-2">
                                        Fecha del último servicio: {bloqueoSaludCapilar.fecha_ultimo_servicio} · Reposo mínimo: {bloqueoSaludCapilar.dias_espera} días
                                    </p>
                                </div>
                            </div>
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
