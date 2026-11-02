import React, { useState, useEffect } from 'react';
import axios from 'axios';
import ConfiguracionAgendaMasiva from './ConfiguracionAgendaMasiva.js';
import { notify } from '../../utils/notificaciones';

// Colores
const COLORS = {
  bg_light: '#F5EBE0',
  bg_white: '#FFFFFF',
  primary_dark: '#817773',
  primary_light: '#AB9A91',
  accent_light: '#D5BDAF',
  accent_very_light: '#E3D5CA',
  success: '#6B9C7A',
  error: '#C73E3E',
};

// Días de la semana
const WEEK_DAYS = [
  { label: 'Lunes', value: 0 },
  { label: 'Martes', value: 1 },
  { label: 'Miércoles', value: 2 },
  { label: 'Jueves', value: 3 },
  { label: 'Viernes', value: 4 },
  { label: 'Sábado', value: 5 }
];

// Iconos SVG
const IconEye = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
  </svg>
);

const IconSunrise = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m6.364 1.636l-.707.707M21 12h-1m-6.364 6.364l.707.707M12 21v1m-6.364-1.636l.707-.707M3 12h1m6.364-6.364l-.707.707M12 6a6 6 0 110 12 6 6 0 010-12z" />
  </svg>
);

const IconSunset = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m6.364 1.636l-.707.707M21 12h-1m-6.364 6.364l.707.707M12 21v1m-6.364-1.636l.707-.707M3 12h1m6.364-6.364l-.707.707M12 8a4 4 0 110 8 4 4 0 010-8z" />
  </svg>
);

const IconUser = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
  </svg>
);

const IconPackage = ({ className = 'w-4 h-4' }) => (
  <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 015.646 5.646 9.001 9.001 0 0020.354 15.354z" />
  </svg>
);

const AgendaAdmin = () => {
    const agendaWriteActionsEnabled = false;
    // Estado del Calendario
    const [currentDate, setCurrentDate] = useState(new Date());
    
    // Estado de Datos (API)
    const [horariosBase, setHorariosBase] = useState([]);
    const [bloqueos, setBloqueos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // Estado del Modal
    const [mostrarModal, setMostrarModal] = useState(false);
    const [mostrarConfiguracion, setMostrarConfiguracion] = useState(false);
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
            const ahora = new Date();
            const mes = ahora.getMonth() + 1;
            const anio = ahora.getFullYear();
            
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/obtener_disponibilidad_calendario/', {
                params: { mes, anio },
                headers: { Authorization: `Bearer ${token}` }
            });
            setHorariosBase(res.data.reglas);
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
        setLoadingBloqueo(true);
        try {
            const token = localStorage.getItem('access_token');
            
            // Lógica para definir horas si es "Todo el día"
            const hInicio = bloqueaTodoDia ? '00:00' : horaInicio;
            const hFin = bloqueaTodoDia ? '23:59' : horaFin;

            const payload = {
                fecha_inicio: `${fechaInicio}T${hInicio}:00`,
                fecha_fin: `${fechaFin}T${hFin}:59`,
                motivo: motivo,
                bloquea_todo_el_dia: bloqueaTodoDia
            };

            await axios.post('http://127.0.0.1:8000/api/gestion/agenda/bloquear/', payload, {
                headers: { Authorization: `Bearer ${token}` }
            });
            
            // ÉXITO (Paso 7 del C.U.)
            notify.success('Bloqueo creado exitosamente');
            setMostrarModal(false);
            fetchAgendaData(); // Refrescar calendario

        } catch (error) {
            // MANEJO DE CONFLICTOS (Excepción 5 del C.U.)
            if (error.response && error.response.status === 409) {
                const data = error.response.data;
                
                // Formateamos el mensaje de error para que sea legible
                let mensaje = `${data.mensaje}\n${data.instruccion}\n\n------- CONFLICTOS DETECTADOS -------\n`;
                
                data.turnos_afectados.forEach(t => {
                    mensaje += `• ${t.fecha} a las ${t.hora} | ${t.cliente} (${t.servicio})\n`;
                });
                
                mensaje += `\nVe a la sección "Turnos" para resolverlos antes de bloquear.`;

                notify.error(mensaje);
                // No cerramos el modal para que pueda corregir las fechas si quiere
            } else {
                // Otros errores (400, 500)
                notify.error('Error al guardar: ' + (error.response?.data?.error || 'Error desconocido'));
            }
        } finally {
            setLoadingBloqueo(false);
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
            bgColor = "#F5F5EB";
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
                onClick={() => agendaWriteActionsEnabled && !bloqueo && abrirModalBloqueo(dayNumber)}
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
            <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#F5F5EB' }}>
                <div className="animate-spin rounded-full h-16 w-16 border-4" style={{ borderColor: '#E3D5CA', borderTopColor: '#817773' }}></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen p-6" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-6xl mx-auto">
                {/* HEADER */}
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2" style={{ color: '#817773' }}>Gestión de Agenda</h1>
                    <p style={{ color: '#AB9A91' }}>Configura horarios laborales y bloqueos de disponibilidad</p>
                </div>

                {/* CONFIGURACIÓN MASIVA: Botón para abrir modal */}
                {agendaWriteActionsEnabled && <div className="mb-6">
                    <button
                        onClick={() => setMostrarConfiguracion(true)}
                        className="px-4 py-2 rounded-lg font-bold transition transform hover:scale-105"
                        style={{ backgroundColor: '#D5BDAF', color: 'white' }}
                    >
                         Configurar horarios
                    </button>
                </div>}

                {/* Vista Previa de Horarios Base */}
                <div className="mb-6 rounded-xl p-4" style={{ backgroundColor: COLORS.bg_light, borderLeft: `5px solid ${COLORS.primary_light}` }}>
                    <h3 className="text-lg font-bold mb-4 flex items-center gap-2" style={{ color: COLORS.primary_dark }}>
                        <IconEye className="w-5 h-5" style={{ color: COLORS.primary_dark }} />
                        Horarios Configurados
                    </h3>
                    
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                        {WEEK_DAYS.map((dia) => {
                            const horario = horariosBase.find(h => h.dia_semana === dia.value);
                            const hayTrabajo = horario && horario.activo;
                            
                            return (
                                <div
                                    key={dia.value}
                                    className="p-3 rounded-lg border-2 transition"
                                    style={{
                                        backgroundColor: hayTrabajo ? COLORS.bg_white : '#F0F0F0',
                                        borderColor: hayTrabajo ? COLORS.success : COLORS.accent_very_light,
                                        opacity: hayTrabajo ? 1 : 0.6
                                    }}
                                >
                                    <div className="font-bold text-sm mb-2" style={{ color: COLORS.primary_dark }}>
                                        {dia.label}
                                    </div>
                                    
                                    {hayTrabajo ? (
                                        <div className="space-y-2 text-xs">
                                            <div className="flex items-center gap-1" style={{ color: COLORS.primary_light }}>
                                                <IconSunrise className="w-3 h-3" />
                                                <span className="font-bold">{horario.hora_inicio.slice(0, 5)}</span>
                                            </div>
                                            <div className="flex items-center gap-1" style={{ color: COLORS.primary_light }}>
                                                <IconSunset className="w-3 h-3" />
                                                <span className="font-bold">{horario.hora_fin.slice(0, 5)}</span>
                                            </div>
                                            
                                            {horario.personal && (
                                                <div className="flex items-start gap-1 pt-1 border-t" style={{ borderColor: COLORS.accent_very_light }}>
                                                    <IconUser className="w-3 h-3 mt-0.5 flex-shrink-0" style={{ color: COLORS.success }} />
                                                    <div className="leading-tight">
                                                        <div className="font-bold" style={{ color: COLORS.success }}>
                                                            {Array.isArray(horario.personal) 
                                                                ? horario.personal.map(p => typeof p === 'string' ? p : p.nombre || p.name).join(', ')
                                                                : horario.personal.nombre || horario.personal.name || horario.personal
                                                            }
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {horario.servicios && (
                                                <div className="flex items-start gap-1 pt-1 border-t" style={{ borderColor: COLORS.accent_very_light }}>
                                                    <IconPackage className="w-3 h-3 mt-0.5 flex-shrink-0" style={{ color: COLORS.primary_light }} />
                                                    <div className="leading-tight text-[10px]">
                                                        <div style={{ color: COLORS.primary_light }}>
                                                            {Array.isArray(horario.servicios)
                                                                ? horario.servicios.map(s => typeof s === 'string' ? s : s.nombre || s.name).join(', ')
                                                                : horario.servicios.nombre || horario.servicios.name || horario.servicios
                                                            }
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div style={{ color: '#999', fontSize: '11px', fontStyle: 'italic' }}>
                                            Cerrado
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Modal de Configuración */}
                {agendaWriteActionsEnabled && <ConfiguracionAgendaMasiva
                    isOpen={mostrarConfiguracion}
                    onClose={() => setMostrarConfiguracion(false)}
                    fetchPersonal={async () => {
                        try {
                            const token = localStorage.getItem('access_token');
                            const res = await axios.get('http://127.0.0.1:8000/api/gestion/personal/', { headers: { Authorization: `Bearer ${token}` } });
                            // Normalizar datos: esperar {id, nombre} o {id, usuario}
                            return res.data.map(p => ({ id: p.id, nombre: p.nombre || (p.usuario?.first_name ? `${p.usuario.first_name} ${p.usuario.last_name}` : p.email) }))
                        } catch (e) {
                            console.error('No se pudo cargar personal', e);
                            return []
                        }
                    }} 
                />}

                {/* ERROR ALERT */}
                {error && (
                    <div className="mb-6 p-4 rounded-lg border-l-4" style={{ backgroundColor: '#FFE8E8', borderColor: '#C73E3E' }}>
                        <p style={{ color: '#C73E3E' }} className="font-medium">{error}</p>
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
                        <p className="font-bold mb-3" style={{ color: '#817773' }}>Leyenda:</p>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded" style={{ backgroundColor: '#ffffff', border: '2px solid #6B9C7A' }}></div>
                                <span style={{ color: '#817773' }}>Día laboral</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="w-6 h-6 rounded" style={{ backgroundColor: '#F5F5EB', border: '2px solid #AB9A91' }}></div>
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
            {agendaWriteActionsEnabled && mostrarModal && (
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
