import React, { useState, useEffect } from 'react';
import axios from 'axios';

const AgendaAdmin = () => {
    // Estado del Calendario
    const [currentDate, setCurrentDate] = useState(new Date());
    
    // Estado de Datos (API)
    const [horariosBase, setHorariosBase] = useState([]);
    const [bloqueos, setBloqueos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // Estado del Modal
    const [mostrarModal, setMostrarModal] = useState(false);
    const [fechaInicio, setFechaInicio] = useState('');
    const [fechaFin, setFechaFin] = useState('');
    const [motivo, setMotivo] = useState('');
    const [bloqueaTodoDia, setBloqueaTodoDia] = useState(true);
    const [horaInicio, setHoraInicio] = useState('09:00');
    const [horaFin, setHoraFin] = useState('17:00');
    const [loadingBloqueo, setLoadingBloqueo] = useState(false);

    // Cargar datos al iniciar
    useEffect(() => {
        fetchAgendaData();
    }, []);

    const fetchAgendaData = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/agenda/general/', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setHorariosBase(res.data.horarios_base);
            setBloqueos(res.data.bloqueos);
            setLoading(false);
        } catch (error) {
            console.error("Error cargando agenda", error);
            setError('Error al cargar la agenda');
            setLoading(false);
        }
    };

    const getHorarioDelDia = (date) => {
        let diaSemanaJS = date.getDay(); 
        let diaSemanaDjango = diaSemanaJS === 0 ? 6 : diaSemanaJS - 1;
        return horariosBase.find(h => h.dia_semana === diaSemanaDjango);
    };

    const getBloqueoDelDia = (date) => {
        return bloqueos.find(b => {
            const bloqueoInicio = new Date(b.fecha_inicio);
            const bloqueoFin = new Date(b.fecha_fin);
            return date >= bloqueoInicio && date <= bloqueoFin;
        });
    };

    const abrirModalBloqueo = (dayNumber) => {
        const fecha = new Date(currentDate.getFullYear(), currentDate.getMonth(), dayNumber);
        const fechaFormato = fecha.toISOString().split('T')[0];
        setFechaInicio(fechaFormato);
        setFechaFin(fechaFormato);
        setMotivo('');
        setBloqueaTodoDia(true);
        setHoraInicio('09:00');
        setHoraFin('17:00');
        setMostrarModal(true);
    };

    const guardarBloqueo = async () => {
        try {
            const token = localStorage.getItem('access_token');
            
            // Lógica para definir horas si es "Todo el día"
            const hInicio = nuevoBloqueo.todoElDia ? '00:00' : nuevoBloqueo.horaInicio;
            const hFin = nuevoBloqueo.todoElDia ? '23:59' : nuevoBloqueo.horaFin;

            const payload = {
                fecha_inicio: `${nuevoBloqueo.fechaInicio}T${hInicio}:00`,
                fecha_fin: `${nuevoBloqueo.fechaFin}T${hFin}:59`,
                motivo: nuevoBloqueo.motivo,
                bloquea_todo_el_dia: nuevoBloqueo.todoElDia
            };

            await axios.post('http://127.0.0.1:8000/api/gestion/agenda/bloquear/', payload, {
                headers: { Authorization: `Bearer ${token}` }
            });
            
            // ÉXITO (Paso 7 del C.U.)
            alert("✅ Bloqueo creado exitosamente.");
            setModalOpen(false);
            fetchAgendaData(); // Refrescar calendario

        } catch (error) {
            // MANEJO DE CONFLICTOS (Excepción 5 del C.U.)
            if (error.response && error.response.status === 409) {
                const data = error.response.data;
                
                // Formateamos el mensaje de error para que sea legible
                let mensaje = `⛔ ${data.mensaje}\n${data.instruccion}\n\n------- CONFLICTOS DETECTADOS -------\n`;
                
                data.turnos_afectados.forEach(t => {
                    mensaje += `• ${t.fecha} a las ${t.hora} | ${t.cliente} (${t.servicio})\n`;
                });
                
                mensaje += `\nVe a la sección "Turnos" para resolverlos antes de bloquear.`;

                alert(mensaje);
                // No cerramos el modal para que pueda corregir las fechas si quiere
            } else {
                // Otros errores (400, 500)
                alert("Error al guardar: " + (error.response?.data?.error || "Error desconocido"));
            }
        }
    };

    const renderCeldaDia = (dayNumber) => {
        const cellDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), dayNumber);
        const hoy = new Date();
        hoy.setHours(0,0,0,0);

        const horario = getHorarioDelDia(cellDate);
        const bloqueo = getBloqueoDelDia(cellDate);

        let bgColor = "#ffffff";
        let borderColor = "#E3D5CA";
        let cursor = "cursor-pointer";
        let contenido = null;
        let textColor = "#817773";

        if (bloqueo) {
            bgColor = "#FFE8E8";
            borderColor = "#C73E3E";
            textColor = "#C73E3E";
            contenido = <span className="text-xs font-bold block truncate" style={{color: textColor}}>{bloqueo.motivo}</span>;
        } else if (!horario) {
            bgColor = "#F5EBE0";
            borderColor = "#D5BDAF";
            cursor = "cursor-not-allowed";
            textColor = "#AB9A91";
            contenido = <span className="text-[10px] block mt-1" style={{color: textColor}}>Cerrado</span>;
        } else {
            contenido = (
                <span className="text-[10px] block mt-1" style={{color: "#6B9C7A"}}>
                    {horario.hora_inicio.slice(0, 5)} - {horario.hora_fin.slice(0, 5)}
                </span>
            );
        }

        return (
            <div 
                key={dayNumber} 
                className={`h-24 p-2 transition flex flex-col justify-between ${cursor}`}
                style={{
                    backgroundColor: bgColor,
                    borderLeft: `4px solid ${borderColor}`,
                    border: `1px solid ${borderColor}`
                }}
                onClick={() => !bloqueo && abrirModalBloqueo(dayNumber)}
            >
                <span className="font-bold" style={{color: dayNumber === hoy.getDate() && currentDate.getMonth() === hoy.getMonth() ? '#817773' : textColor}}>
                    {dayNumber}
                </span>
                {contenido}
            </div>
        );
    };

    const prevMonth = () => {
        setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1));
    };

    const nextMonth = () => {
        setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1));
    };

    const monthNames = [
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
    ];

    const daysInMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0).getDate();
    const firstDay = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1).getDay();

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#F5EBE0' }}>
                <div className="animate-spin rounded-full h-16 w-16 border-4" style={{ borderColor: '#E3D5CA', borderTopColor: '#817773' }}></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-6" style={{ backgroundColor: '#F5EBE0' }}>
            <div className="max-w-6xl mx-auto">
                {/* HEADER */}
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2" style={{ color: '#817773' }}>📅 Gestión de Agenda</h1>
                    <p style={{ color: '#AB9A91' }}>Configura horarios laborales y bloqueos de disponibilidad</p>
                </div>

                {/* ERROR ALERT */}
                {error && (
                    <div className="mb-6 p-4 rounded-lg border-l-4" style={{ backgroundColor: '#FFE8E8', borderColor: '#C73E3E' }}>
                        <p style={{ color: '#C73E3E' }} className="font-medium">⚠️ {error}</p>
                    </div>
                )}

                {/* TARJETA DE CALENDARIO */}
                <div style={{ backgroundColor: 'white', borderLeft: '5px solid #AB9A91' }} className="rounded-xl p-8 shadow-lg">
                    
                    {/* CONTROLES MES */}
                    <div className="flex items-center justify-between mb-6">
                        <button
                            onClick={prevMonth}
                            className="px-4 py-2 rounded-lg font-bold transition transform hover:scale-105"
                            style={{ backgroundColor: '#D5BDAF', color: 'white' }}
                        >
                            ← Anterior
                        </button>
                        
                        <h2 className="text-2xl font-bold" style={{ color: '#817773' }}>
                            {monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}
                        </h2>
                        
                        <button
                            onClick={nextMonth}
                            className="px-4 py-2 rounded-lg font-bold transition transform hover:scale-105"
                            style={{ backgroundColor: '#AB9A91', color: 'white' }}
                        >
                            Siguiente →
                        </button>
                    </div>

                    {/* GRID DE DÍAS */}
                    <div className="grid grid-cols-7 gap-2 mb-6">
                        {['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'].map(d => (
                            <div 
                                key={d} 
                                className="font-bold text-center py-3 rounded-lg"
                                style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                            >
                                {d}
                            </div>
                        ))}
                        
                        {/* Días vacíos del inicio */}
                        {Array.from({ length: firstDay === 0 ? 6 : firstDay - 1 }).map((_, i) => (
                            <div key={`empty-${i}`} className="h-24 bg-gray-50 rounded" />
                        ))}
                        
                        {/* Días del mes */}
                        {Array.from({ length: daysInMonth }, (_, i) => i + 1).map(day => renderCeldaDia(day))}
                    </div>

                    {/* LEYENDA */}
                    <div className="mt-6 pt-6 border-t" style={{ borderColor: '#E3D5CA' }}>
                        <p className="font-bold mb-3" style={{ color: '#817773' }}>📋 Leyenda:</p>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded" style={{ backgroundColor: '#ffffff', border: '2px solid #6B9C7A' }}></div>
                                <span style={{ color: '#817773' }}>Día laboral</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded" style={{ backgroundColor: '#F5EBE0', border: '2px solid #AB9A91' }}></div>
                                <span style={{ color: '#817773' }}>Cerrado</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded" style={{ backgroundColor: '#FFE8E8', border: '2px solid #C73E3E' }}></div>
                                <span style={{ color: '#817773' }}>Bloqueado</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* MODAL DE BLOQUEO */}
            {mostrarModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div style={{ backgroundColor: 'white' }} className="rounded-xl p-8 max-w-md w-full mx-4 shadow-2xl">
                        <h2 className="text-2xl font-bold mb-6" style={{ color: '#817773' }}>🚫 Crear Bloqueo</h2>

                        {/* Rango de Fechas */}
                        <div className="mb-4">
                            <label className="block font-bold mb-2" style={{ color: '#AB9A91' }}>Fecha Inicio</label>
                            <input
                                type="date"
                                value={fechaInicio}
                                onChange={(e) => setFechaInicio(e.target.value)}
                                className="w-full px-4 py-2 border-2 rounded-lg"
                                style={{ borderColor: '#E3D5CA' }}
                            />
                        </div>

                        <div className="mb-4">
                            <label className="block font-bold mb-2" style={{ color: '#AB9A91' }}>Fecha Fin</label>
                            <input
                                type="date"
                                value={fechaFin}
                                onChange={(e) => setFechaFin(e.target.value)}
                                className="w-full px-4 py-2 border-2 rounded-lg"
                                style={{ borderColor: '#E3D5CA' }}
                            />
                        </div>

                        {/* Tipo de Bloqueo */}
                        <div className="mb-4">
                            <label className="flex items-center gap-3 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={bloqueaTodoDia}
                                    onChange={(e) => setBloqueaTodoDia(e.target.checked)}
                                    className="w-5 h-5"
                                />
                                <span style={{ color: '#817773' }} className="font-bold">Bloquear todo el día</span>
                            </label>
                        </div>

                        {/* Horarios Específicos (si no es todo el día) */}
                        {!bloqueaTodoDia && (
                            <>
                                <div className="mb-4">
                                    <label className="block font-bold mb-2" style={{ color: '#AB9A91' }}>Hora Inicio</label>
                                    <input
                                        type="time"
                                        value={horaInicio}
                                        onChange={(e) => setHoraInicio(e.target.value)}
                                        className="w-full px-4 py-2 border-2 rounded-lg"
                                        style={{ borderColor: '#E3D5CA' }}
                                    />
                                </div>

                                <div className="mb-4">
                                    <label className="block font-bold mb-2" style={{ color: '#AB9A91' }}>Hora Fin</label>
                                    <input
                                        type="time"
                                        value={horaFin}
                                        onChange={(e) => setHoraFin(e.target.value)}
                                        className="w-full px-4 py-2 border-2 rounded-lg"
                                        style={{ borderColor: '#E3D5CA' }}
                                    />
                                </div>
                            </>
                        )}

                        {/* Motivo */}
                        <div className="mb-6">
                            <label className="block font-bold mb-2" style={{ color: '#AB9A91' }}>Motivo</label>
                            <textarea
                                value={motivo}
                                onChange={(e) => setMotivo(e.target.value)}
                                placeholder="Ej: Feriado, Médico, Vacaciones..."
                                className="w-full px-4 py-2 border-2 rounded-lg h-20"
                                style={{ borderColor: '#E3D5CA' }}
                            />
                        </div>

                        {/* Botones */}
                        <div className="flex gap-4">
                            <button
                                onClick={() => setMostrarModal(false)}
                                disabled={loadingBloqueo}
                                className="flex-1 px-4 py-2 rounded-lg font-bold transition"
                                style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={guardarBloqueo}
                                disabled={loadingBloqueo}
                                className="flex-1 px-4 py-2 rounded-lg font-bold text-white transition transform hover:scale-105"
                                style={{ 
                                    background: 'linear-gradient(135deg, #D5BDAF 0%, #AB9A91 100%)',
                                    opacity: loadingBloqueo ? 0.5 : 1,
                                    cursor: loadingBloqueo ? 'not-allowed' : 'pointer'
                                }}
                            >
                                {loadingBloqueo ? 'Guardando...' : 'Crear Bloqueo'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AgendaAdmin;