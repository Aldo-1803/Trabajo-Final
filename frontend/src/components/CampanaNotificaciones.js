import React, { useState, useEffect } from 'react';
import axios from 'axios';

const CampanaNotificaciones = () => {
    const [notificaciones, setNotificaciones] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [unreadCount, setUnreadCount] = useState(0);
    const [procesando, setProcesando] = useState({});

    const fetchNotificaciones = async () => {
        try {
            const token = localStorage.getItem('access_token');
            
            if (!token) {
                setNotificaciones([]);
                return;
            }

            const response = await axios.get('http://127.0.0.1:8000/api/gestion/notificaciones/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            // AQUÍ: Manejar múltiples formatos de respuesta
            let notifData = Array.isArray(response.data) 
                ? response.data 
                : (response.data?.results || []);
            
            setNotificaciones(notifData);
            setUnreadCount(notifData.filter(n => n.estado === 'pendiente').length);
        } catch (error) {
            console.error("Error cargando notificaciones", error?.message || error);
            setNotificaciones([]);
        }
    };

    // POLLING: Consultar cada 5 segundos para que se actualice solo en el video
    useEffect(() => {
        fetchNotificaciones();
        const interval = setInterval(fetchNotificaciones, 5000); 
        return () => clearInterval(interval);
    }, []);

    const marcarComoLeida = async (id) => {
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(`http://127.0.0.1:8000/api/gestion/notificaciones/${id}/marcar_leida/`, {}, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            // Actualizar estado localmente para que cambie de color al instante
            setNotificaciones(prev => prev.map(n => 
                n.id === id ? { ...n, estado: 'leido' } : n
            ));
            
            // Bajar el contador
            setUnreadCount(prev => Math.max(0, prev - 1));

        } catch (error) {
            console.error("Error al marcar como leída", error);
        }
    };

    // Nueva función: Procesar oferta de adelanto
    const handleAceptarOferta = async (notif) => {
        try {
            // Extraer datos de la notificación
            const { fecha_oferta, hora_oferta, turno_actual_id } = notif.datos_extra;
            
            // Validar datos
            if (!fecha_oferta || !hora_oferta) {
                alert('Datos incompletos en la notificación');
                return;
            }

            // Confirmación visual
            if (!window.confirm(`¿Confirmas adelantar tu turno al ${fecha_oferta} a las ${hora_oferta}?`)) {
                return;
            }

            setProcesando(prev => ({ ...prev, [notif.id]: true }));
            const token = localStorage.getItem('access_token');

            // Opción 1: Si existe endpoint específico de aceptar notificación
            try {
                await axios.post(
                    `http://127.0.0.1:8000/api/gestion/notificaciones/${notif.id}/aceptar/`,
                    {},
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
            } catch (err) {
                // Si no existe ese endpoint, usamos el PATCH directo al turno                
                if (turno_actual_id) {
                    await axios.patch(
                        `http://127.0.0.1:8000/api/gestion/turnos/${turno_actual_id}/`,
                        {
                            fecha: fecha_oferta,
                            hora_inicio: hora_oferta
                        },
                        { headers: { 'Authorization': `Bearer ${token}` } }
                    );
                } else {
                    throw new Error('ID de turno no encontrado en notificación');
                }
            }

            // Si llegamos aquí, el cambio fue exitoso
            alert("¡Turno adelantado correctamente!");
            
            // Marcar notificación como leída
            await marcarComoLeida(notif.id);
            
            // Recargar notificaciones
            await fetchNotificaciones();
            
        } catch (error) {
            console.error('Error al aceptar oferta:', error);
            const errorMsg = error.response?.data?.error 
                || error.response?.data?.detail 
                || error.message 
                || "Error al procesar la solicitud";
            alert(errorMsg);
        } finally {
            setProcesando(prev => ({ ...prev, [notif.id]: false }));
        }
    };

    // Función auxiliar para el color del icono según el tipo
    const getIconoTipo = (tipo) => {
        switch(tipo) {
            case 'alerta': return '🔴'; // Rojo para cancelaciones/urgente
            case 'recordatorio': return '⏰';
            case 'ADELANTO': return '⏩'; // Adelanto rápido
            default: return 'ℹ️'; // Info normal
        }
    };

    return (
        <div className="relative inline-block">
            {/* ÍCONO CAMPANA */}
            <button 
                onClick={() => setShowDropdown(!showDropdown)} 
                className="relative p-2 text-gray-600 hover:text-pink-600 transition-colors focus:outline-none"
            >
                {/* SVG de Campana */}
                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
                
                {/* Badge Rojo (Contador) */}
                {unreadCount > 0 && (
                    <span className="absolute top-0 right-0 inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-white transform translate-x-1/4 -translate-y-1/4 bg-red-600 rounded-full shadow-sm animate-bounce">
                        {unreadCount}
                    </span>
                )}
            </button>

            {/* LISTA DESPLEGABLE */}
            {showDropdown && (
                <div className="absolute right-0 mt-2 w-80 md:w-96 bg-white rounded-xl shadow-2xl overflow-hidden z-50 border border-gray-100 ring-1 ring-black ring-opacity-5">
                    <div className="py-3 bg-gradient-to-r from-pink-600 to-rose-500 text-white px-4 font-bold text-sm flex justify-between items-center">
                        <span>Notificaciones</span>
                        <span className="text-xs font-normal bg-pink-700 px-2 py-0.5 rounded-full">{unreadCount} nuevas</span>
                    </div>
                    
                    <div className="max-h-80 overflow-y-auto">
                        {notificaciones.length === 0 ? (
                            <div className="p-8 text-center text-gray-400">
                                <p className="text-2xl mb-2">🔕</p>
                                <p className="text-sm">No tienes notificaciones.</p>
                            </div>
                        ) : (
                            notificaciones.map((notif) => (
                                <div 
                                    key={notif.id} 
                                    className={`p-4 border-b border-gray-50 transition-colors 
                                        ${notif.estado === 'pendiente' ? 'bg-blue-50 border-l-4 border-l-pink-500' : 'bg-white opacity-80'}`}
                                >
                                    {/* Título y Mensaje */}
                                    <div className="flex justify-between items-start mb-1">
                                        <h4 className={`text-sm ${notif.estado === 'pendiente' ? 'font-bold text-gray-900' : 'font-semibold text-gray-600'}`}>
                                            {getIconoTipo(notif.tipo)} {notif.titulo}
                                        </h4>
                                        <span className="text-xs text-gray-400 whitespace-nowrap ml-2">
                                            {new Date(notif.fecha_envio).toLocaleDateString()}
                                        </span>
                                    </div>
                                    
                                    <p className={`text-xs mb-3 ${notif.estado === 'pendiente' ? 'text-gray-800' : 'text-gray-500'}`}>
                                        {notif.mensaje}
                                    </p>
                                    
                                    {/* --- LÓGICA CONDICIONAL PARA INTERACCIÓN --- */}
                                    
                                    {/* Si es tipo ADELANTO y aún está pendiente (no aceptada) */}
                                    {notif.tipo === 'ADELANTO' && notif.datos_extra && notif.estado === 'pendiente' && (
                                        <div className="mt-3 bg-gradient-to-r from-blue-50 to-indigo-50 p-3 rounded border-2 border-blue-200">
                                            <p className="text-xs text-blue-800 mb-3 font-bold">
                                                📅 Nueva fecha: <span className="text-blue-900">{notif.datos_extra.fecha_oferta}</span> a las <span className="text-blue-900">{notif.datos_extra.hora_oferta}</span>
                                            </p>
                                            
                                            <div className="flex gap-2">
                                                <button 
                                                    onClick={() => handleAceptarOferta(notif)}
                                                    disabled={procesando[notif.id]}
                                                    className="flex-1 bg-green-600 text-white text-xs font-bold py-2 rounded hover:bg-green-700 shadow-sm transition disabled:bg-gray-400 disabled:cursor-not-allowed"
                                                >
                                                    {procesando[notif.id] ? '⏳ Procesando...' : '✅ ACEPTAR'}
                                                </button>
                                                <button 
                                                    onClick={() => marcarComoLeida(notif.id)}
                                                    disabled={procesando[notif.id]}
                                                    className="px-3 py-2 border border-gray-300 rounded text-gray-500 text-xs hover:bg-gray-100 transition disabled:bg-gray-100 disabled:cursor-not-allowed"
                                                >
                                                    Ignorar
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                    
                                    {/* Si es ADELANTO pero ya fue aceptada/leída */}
                                    {notif.tipo === 'ADELANTO' && notif.estado === 'leido' && (
                                        <div className="mt-3 bg-green-50 p-3 rounded border-2 border-green-200">
                                            <p className="text-xs text-green-700 font-bold">
                                                ✅ Turno adelantado correctamente
                                            </p>
                                        </div>
                                    )}

                                    {/* Si no es ADELANTO, solo click para marcar como leído */}
                                    {notif.tipo !== 'ADELANTO' && notif.estado === 'pendiente' && (
                                        <div className="mt-2 flex justify-end">
                                            <button
                                                onClick={() => marcarComoLeida(notif.id)}
                                                className="text-[10px] text-pink-600 font-bold uppercase tracking-wide hover:text-pink-700 transition"
                                            >
                                                Marcar como leída →
                                            </button>
                                        </div>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                    
                    {/* Footer del dropdown */}
                    <div className="bg-gray-50 p-2 text-center border-t border-gray-100">
                        <button 
                            onClick={() => setShowDropdown(false)}
                            className="text-xs text-gray-500 hover:text-gray-800 font-medium"
                        >
                            Cerrar
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default CampanaNotificaciones;