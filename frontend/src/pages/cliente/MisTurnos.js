import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const MisTurnos = () => {
    // --- ESTADOS ---
    const [turnos, setTurnos] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // Estados para Subida de Archivos
    const [archivo, setArchivo] = useState(null);
    const [turnoIdSubida, setTurnoIdSubida] = useState(null);
    
    // --- ESTADOS PARA REPROGRAMACIÓN ---
    const [modalAbierto, setModalAbierto] = useState(false);
    const [turnoSeleccionado, setTurnoSeleccionado] = useState(null);
    const [datosPolitica, setDatosPolitica] = useState(null);
    const [disponibilidadReprogramacion, setDisponibilidadReprogramacion] = useState([]);
    const [fechaSeleccionada, setFechaSeleccionada] = useState(null);
    const [horariosDelDia, setHorariosDelDia] = useState([]);
    const [horarioSeleccionado, setHorarioSeleccionado] = useState(null);
    const [cargandoDisponibilidad, setCargandoDisponibilidad] = useState(false);

    const navigate = useNavigate();

    // --- CARGA INICIAL ---
    const fetchTurnos = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('access_token');
            const response = await axios.get('http://127.0.0.1:8000/api/gestion/turnos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setTurnos(response.data); 
            console.log('Turnos cargados:', response.data);
        } catch (err) {
            console.error('Error cargando turnos:', err);
            notify.error('Error al cargar tus turnos');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTurnos();
    }, []);

    // ========================================================================
    // HELPER: DETECTAR SI EL TURNO YA PASÓ (VENCIDO)
    // ========================================================================
    const esTurnoPasado = (fechaStr, horaStr) => {
        if (!fechaStr || !horaStr) return false;
        
        // Crear fecha del turno (Asumiendo formato YYYY-MM-DD y HH:MM)
        const fechaTurno = new Date(`${fechaStr}T${horaStr}`);
        const ahora = new Date();
        
        // Retorna true si la fecha del turno es menor a "ahora"
        return fechaTurno < ahora;
    };

    // ========================================================================
    // LÓGICA 1: SUBIDA DE COMPROBANTES
    // ========================================================================
    const handleFileChange = (e, turnoId) => {
        const file = e.target.files[0];
        if (file) {
            const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
            if (!validTypes.includes(file.type)) {
                notify.error("Formato incorrecto. Solo JPG, PNG o PDF.");
                return;
            }
            if (file.size > 5 * 1024 * 1024) {
                notify.error("Máximo permitido: 5MB.");
                return;
            }
            setArchivo(file);
            setTurnoIdSubida(turnoId);
        }
    };

    const subirComprobante = async (turnoId) => {
        if (!archivo) {
            notify.error("Selecciona un archivo");
            return;
        }
        const formData = new FormData();
        formData.append('comprobante_pago', archivo);

        try {
            const token = localStorage.getItem('access_token');
            await axios.patch(`http://127.0.0.1:8000/api/gestion/turnos/${turnoId}/`, formData, {
                headers: { 
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'multipart/form-data'
                }
            });
            notify.success("¡Comprobante subido con éxito!");
            setArchivo(null);
            setTurnoIdSubida(null);
            fetchTurnos(); 
        } catch (error) {
            console.error("Error subida:", error);
            notify.error("Error al subir comprobante.");
        }
    };

    // ========================================================================
    // LÓGICA 2: GESTIÓN INTELIGENTE - Abrir Modal y Cargar Disponibilidad
    // ========================================================================
    const abrirGestion = async (turno) => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.post(
                `http://127.0.0.1:8000/api/gestion/turnos/${turno.id}/gestionar/`,
                { accion: 'CONSULTAR' },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setDatosPolitica(res.data);
            setTurnoSeleccionado(turno);
            
            // Limpiar estados del modal
            setFechaSeleccionada(null);
            setHorarioSeleccionado(null);
            setHorariosDelDia([]);
            setDisponibilidadReprogramacion([]);
            
            // Cargar disponibilidad para reprogramación si puede reprogramar
            if (res.data.puede_reprogramar && turno.detalles && turno.detalles.length > 0) {
                const servicioId = turno.detalles[0].servicio;
                await cargarDisponibilidadReprogramacion(servicioId);
            }
            
            setModalAbierto(true);
        } catch (error) {
            // Manejo especial para bloqueo de 48hs (Error 400)
            if (error.response && error.response.status === 400 && error.response.data.mensaje_bloqueo) {
                notify.error(`${error.response.data.mensaje_bloqueo}\nContacto: ${error.response.data.contacto}`);
            } else {
                notify.error("Error al consultar opciones del turno.");
            }
        }
    };

    // Cargar disponibilidad para reprogramación
    const cargarDisponibilidadReprogramacion = async (servicioId) => {
        setCargandoDisponibilidad(true);
        try {
            const token = localStorage.getItem('access_token');
            const url = `http://127.0.0.1:8000/api/gestion/turnos/consultar_disponibilidad/?servicio_id=${servicioId}`;
            const res = await axios.get(url, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setDisponibilidadReprogramacion(res.data.disponibilidad || []);
        } catch (error) {
            console.error('Error cargando disponibilidad:', error);
            notify.error("Error al cargar disponibilidad para reprogramación");
        } finally {
            setCargandoDisponibilidad(false);
        }
    };

    // Seleccionar fecha disponible
    const seleccionarFechaDisponible = (fechaDisponible) => {
        setFechaSeleccionada(fechaDisponible);
        setHorarioSeleccionado(null);
        
        // Si solo hay un profesional, auto-seleccionar y mostrar sus horarios
        if (fechaDisponible.profesionales && fechaDisponible.profesionales.length === 1) {
            const prof = fechaDisponible.profesionales[0];
            setHorariosDelDia(prof.slots || []);
        } else {
            // Múltiples profesionales, limpiar horarios hasta seleccionar uno
            setHorariosDelDia([]);
        }
    };

    const ejecutarAccion = async (tipoAccion) => {
        try {
            const token = localStorage.getItem('access_token');

            if (tipoAccion === 'REPROGRAMAR') {
                if (!fechaSeleccionada || !horarioSeleccionado) {
                    notify.error("Selecciona fecha y hora nueva.");
                    return;
                }

                console.log('Enviando reprogramación:', {
                    turnoId: turnoSeleccionado.id,
                    fecha: fechaSeleccionada.fecha,
                    hora: horarioSeleccionado.hora
                });

                // Usar el nuevo endpoint específico: reprogramar_cliente
                const res = await axios.post(
                    `http://127.0.0.1:8000/api/gestion/turnos/${turnoSeleccionado.id}/reprogramar_cliente/`,
                    { 
                        fecha: fechaSeleccionada.fecha,
                        hora_inicio: horarioSeleccionado.hora
                    },
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );

                console.log('Respuesta reprogramación:', res.data);
                notify.success(res.data.mensaje);
                cerrarModal();
                
                // Pequeño delay para asegurar que los datos se propagaron
                setTimeout(() => {
                    fetchTurnos();
                }, 500);
                
            } else if (tipoAccion === 'CANCELAR') {
                // Mantener la lógica existente de gestionar para cancelación
                const result = await confirmarAccion({
                    title: "¿Cancelar turno?",
                    text: "Esta acción es irreversible.",
                    confirmButtonText: "Sí, cancelar"
                });
                if (!result.isConfirmed) return;

                const res = await axios.post(
                    `http://127.0.0.1:8000/api/gestion/turnos/${turnoSeleccionado.id}/gestionar/`,
                    { accion: 'CANCELAR' },
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );

                notify.success(res.data.mensaje);
                cerrarModal();
                fetchTurnos();
            }

        } catch (error) {
            console.error("Error completo:", error);
            console.error("Response data:", error.response?.data);
            const mensaje = error.response?.data?.error || 
                           error.response?.data?.mensaje ||
                           error.response?.data?.detail ||
                           error.message ||
                           "Error al procesar la solicitud";
            notify.error(mensaje);
        }
    };

    const cerrarModal = () => {
        setModalAbierto(false);
        setTurnoSeleccionado(null);
        setDatosPolitica(null);
        setFechaSeleccionada(null);
        setHorarioSeleccionado(null);
        setHorariosDelDia([]);
        setDisponibilidadReprogramacion([]);
    };

    if (loading) return <div className="text-center mt-10" style={{ color: '#8B8682' }}>Cargando turnos...</div>;

    return (
        <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
            <div className="max-w-4xl mx-auto">
                <button onClick={() => navigate('/perfil')} className="mb-4 font-bold transition" style={{ color: '#817773' }} onMouseEnter={(e) => e.target.style.color = '#AB9A91'} onMouseLeave={(e) => e.target.style.color = '#817773'}>← Volver al Perfil</button>
                <h1 className="text-3xl font-bold mb-6" style={{ color: '#817773' }}>Mis Turnos</h1>

                {turnos.length === 0 ? (
                    <p style={{ color: '#8B8682' }}>No tienes turnos activos.</p>
                ) : (
                    <div className="space-y-4">
                        {turnos.map((turno) => {
                            // 1. Calculamos si el turno ya pasó
                            const vencido = esTurnoPasado(turno.fecha, turno.hora_inicio);
                            const estadoFinal = turno.estado === 'realizado' || turno.estado === 'cancelado';
                            
                            // 2. Definimos estilos condicionales (Grisado si vencido)
                            const cardStyle = vencido && !estadoFinal
                                ? { backgroundColor: '#E8E8E8', borderColor: '#ABA89E', opacity: 0.75 } 
                                : { backgroundColor: 'white', borderColor: '#D5BDAF' };

                            return (
                                <div key={turno.id} className="p-6 rounded-lg border-l-4 shadow-md relative transition-all hover:shadow-lg" style={cardStyle}>
                                    <div className="flex flex-col md:flex-row justify-between items-start gap-4">
                                        
                                        {/* INFO DEL TURNO */}
                                        <div className="flex-1">
                                            <h3 className="text-xl font-bold" style={{ color: vencido ? '#8B8682' : '#817773' }}>
                                                {turno.servicio_nombre || "Servicio Capilar"}
                                            </h3>
                                            <p className="text-lg" style={{ color: '#8B8682' }}>📅 {turno.fecha} - 🕒 {turno.hora_inicio}</p>
                                            
                                            <div className="mt-2 flex items-center gap-2">
                                                {/* Badge de Estado */}
                                                <span className="px-2 py-1 rounded text-sm font-bold" style={{ 
                                                    backgroundColor: turno.estado === 'confirmado' ? '#E8F5E8' :
                                                                    turno.estado === 'cancelado' ? '#FFE8E8' :
                                                                    '#F5F1E8',
                                                    color: turno.estado === 'confirmado' ? '#2E7D2E' :
                                                           turno.estado === 'cancelado' ? '#C73E3E' :
                                                           '#8B7500'
                                                }}>
                                                    {turno.estado.toUpperCase()}
                                                </span>

                                                {/* Badge de VENCIDO (Solo si pasó fecha y no está en estado final) */}
                                                {vencido && !estadoFinal && (
                                                    <span className="px-2 py-1 rounded text-sm font-bold" style={{ backgroundColor: '#ABA89E', color: 'white' }}>
                                                        VENCIDO / PENDIENTE CIERRE
                                                    </span>
                                                )}
                                            </div>
                                        </div>

                                        {/* ACCIONES */}
                                        <div className="flex flex-col items-end gap-3 w-full md:w-auto">
                                            
                                            {/* BOTÓN GESTIONAR: Solo si NO está vencido y NO es estado final */}
                                            {!vencido && ['solicitado', 'esperando_sena', 'confirmado'].includes(turno.estado) && (
                                                <button 
                                                    onClick={() => abrirGestion(turno)}
                                                    className="px-4 py-2 rounded-lg text-sm font-bold w-full md:w-auto shadow-sm transition"
                                                    style={{ backgroundColor: '#E3D5CA', color: '#817773', borderColor: '#D5BDAF', border: '1px solid #D5BDAF' }}
                                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                                                >
                                                    Gestionar / Cancelar
                                                </button>
                                            )}

                                            {/* MENSAJE SI ESTÁ VENCIDO */}
                                            {vencido && !estadoFinal && (
                                                <p className="text-xs italic text-right max-w-[200px]" style={{ color: '#8B8682' }}>
                                                    Este turno ya pasó. Si asististe, pronto se marcará como realizado.
                                                </p>
                                            )}

                                            {/* LOGICA DE COMPROBANTE (Solo si NO vencido) */}
                                            {!vencido && turno.estado === 'esperando_sena' && (
                                                <div className="w-full p-3 rounded border" style={{ backgroundColor: '#E3D5CA', borderColor: '#D5BDAF' }}>
                                                    <p className="text-xs font-bold mb-2" style={{ color: '#817773' }}>Subir Comprobante:</p>
                                                    <input 
                                                        type="file" 
                                                        accept="image/*,.pdf"
                                                        onChange={(e) => handleFileChange(e, turno.id)} 
                                                        className="block w-full text-xs"
                                                        style={{ color: '#8B8682' }}
                                                    />
                                                    {turnoIdSubida === turno.id && archivo && (
                                                        <button onClick={() => subirComprobante(turno.id)} className="mt-2 w-full text-white text-xs font-bold py-1 rounded transition" style={{ backgroundColor: '#AB9A91' }} onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'} onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}>
                                                            ENVIAR
                                                        </button>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* MODAL (Sin cambios significativos, se mantiene igual) */}
            {modalAbierto && datosPolitica && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in-up" style={{ backgroundColor: 'white' }}>
                        <div className="flex justify-between items-center mb-4">
                            <h2 className="text-xl font-bold" style={{ color: '#817773' }}>Gestionar Turno</h2>
                            <button onClick={cerrarModal} className="transition" style={{ color: '#8B8682' }} onMouseEnter={(e) => e.target.style.color = '#5A5451'} onMouseLeave={(e) => e.target.style.color = '#8B8682'}>✕</button>
                        </div>

                        <div className="p-4 rounded-lg mb-6 border-l-4" style={{ 
                            backgroundColor: datosPolitica.tipo_alerta === 'info' ? '#E8F0F5' : '#F5F1E8',
                            borderColor: datosPolitica.tipo_alerta === 'info' ? '#AB9A91' : '#D5BDAF',
                            color: datosPolitica.tipo_alerta === 'info' ? '#0D47A1' : '#8B7500'
                        }}>
                            <p className="font-medium">{datosPolitica.mensaje}</p>
                            <p className="text-xs mt-1 opacity-80">
                                Cambios realizados: {datosPolitica.cambios_realizados}/{datosPolitica.limite_cambios}
                            </p>
                        </div>

                        {datosPolitica.puede_reprogramar && (
                            <div className="mb-6">
                                <h3 className="font-bold mb-4" style={{ color: '#817773' }}>Reprogramar Turno</h3>
                                
                                {cargandoDisponibilidad ? (
                                    <p style={{ color: '#8B8682' }} className="text-center py-4">Cargando disponibilidad...</p>
                                ) : disponibilidadReprogramacion.length === 0 ? (
                                    <p style={{ color: '#C73E3E' }} className="text-sm text-center py-4">No hay disponibilidad para reprogramar en este momento</p>
                                ) : (
                                    <>
                                        {/* SELECTOR DE FECHAS */}
                                        <div className="mb-4">
                                            <label className="block text-sm font-semibold mb-3" style={{ color: '#817773' }}>
                                                Selecciona Nueva Fecha
                                            </label>
                                            <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                                                {disponibilidadReprogramacion.map((dia, idx) => (
                                                    <button
                                                        key={idx}
                                                        onClick={() => seleccionarFechaDisponible(dia)}
                                                        className="p-3 rounded border-2 text-left transition"
                                                        style={{
                                                            borderColor: fechaSeleccionada?.fecha === dia.fecha ? '#817773' : '#D5D1CC',
                                                            backgroundColor: fechaSeleccionada?.fecha === dia.fecha ? '#E3D5CA' : '#F5EBE0',
                                                            color: '#817773',
                                                            fontWeight: fechaSeleccionada?.fecha === dia.fecha ? 'bold' : 'normal'
                                                        }}
                                                    >
                                                        <div className="text-xs font-semibold">{dia.dia_semana}</div>
                                                        <div className="text-sm">{dia.fecha}</div>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        {/* SELECTOR DE HORARIOS */}
                                        {fechaSeleccionada && (
                                            <div className="mb-4">
                                                <label className="block text-sm font-semibold mb-3" style={{ color: '#817773' }}>
                                                    Selecciona Nueva Hora
                                                </label>
                                                
                                                {fechaSeleccionada.profesionales && fechaSeleccionada.profesionales.length > 1 ? (
                                                    <>
                                                        {/* MÚLTIPLES PROFESIONALES */}
                                                        <div className="mb-3">
                                                            <label className="block text-xs font-semibold mb-2" style={{ color: '#AB9A91' }}>
                                                                Selecciona Profesional:
                                                            </label>
                                                            <div className="flex flex-wrap gap-2">
                                                                {fechaSeleccionada.profesionales.map((prof, idx) => (
                                                                    <button
                                                                        key={idx}
                                                                        onClick={() => setHorariosDelDia(prof.slots || [])}
                                                                        className="px-3 py-1 rounded text-sm transition border"
                                                                        style={{
                                                                            borderColor: '#D5BDAF',
                                                                            backgroundColor: horariosDelDia === prof.slots ? '#AB9A91' : '#F5EBE0',
                                                                            color: horariosDelDia === prof.slots ? 'white' : '#817773'
                                                                        }}
                                                                    >
                                                                        {prof.nombre}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    </>
                                                ) : null}

                                                {/* GRID DE HORARIOS */}
                                                {horariosDelDia.length > 0 ? (
                                                    <div className="grid grid-cols-4 gap-2">
                                                        {horariosDelDia.map((slot, idx) => (
                                                            <button
                                                                key={idx}
                                                                onClick={() => setHorarioSeleccionado(slot)}
                                                                className="p-2 rounded border-2 text-sm font-semibold transition"
                                                                style={{
                                                                    borderColor: horarioSeleccionado?.hora === slot.hora ? '#817773' : '#D5D1CC',
                                                                    backgroundColor: horarioSeleccionado?.hora === slot.hora ? '#817773' : '#F5EBE0',
                                                                    color: horarioSeleccionado?.hora === slot.hora ? 'white' : '#817773'
                                                                }}
                                                            >
                                                                {slot.hora}
                                                            </button>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p style={{ color: '#C73E3E' }} className="text-sm">Selecciona un profesional para ver sus horarios</p>
                                                )}
                                            </div>
                                        )}

                                        {/* Botón Confirmar */}
                                        <button 
                                            onClick={() => ejecutarAccion('REPROGRAMAR')} 
                                            disabled={!fechaSeleccionada || !horarioSeleccionado}
                                            className="w-full text-white font-bold py-3 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
                                            style={{ backgroundColor: '#817773' }}
                                            onMouseEnter={(e) => !(!fechaSeleccionada || !horarioSeleccionado) && (e.target.style.backgroundColor = '#5A5451')}
                                            onMouseLeave={(e) => !(!fechaSeleccionada || !horarioSeleccionado) && (e.target.style.backgroundColor = '#817773')}
                                        >
                                            Confirmar Nueva Fecha y Hora
                                        </button>
                                    </>
                                )}
                            </div>
                        )}

                        <hr className="my-4" style={{ borderColor: '#D5D1CC' }} />

                        <div>
                            <h3 className="font-bold mb-2" style={{ color: '#817773' }}>Cancelar Definitivamente</h3>
                            <button onClick={() => ejecutarAccion('CANCELAR')} className="w-full border-2 font-bold py-2 rounded transition" style={{ borderColor: '#C73E3E', color: '#C73E3E', backgroundColor: 'white' }} onMouseEnter={(e) => e.target.style.backgroundColor = '#FFE8E8'} onMouseLeave={(e) => e.target.style.backgroundColor = 'white'}>
                                Cancelar Turno
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MisTurnos;