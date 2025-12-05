import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const MisTurnos = () => {
    // --- ESTADOS ---
    const [turnos, setTurnos] = useState([]);
    const [loading, setLoading] = useState(true);
    
    // Estados para Subida de Archivos
    const [archivo, setArchivo] = useState(null);
    const [turnoIdSubida, setTurnoIdSubida] = useState(null);
    
    // Estados para GESTIÓN INTELIGENTE (Modal)
    const [modalAbierto, setModalAbierto] = useState(false);
    const [turnoSeleccionado, setTurnoSeleccionado] = useState(null);
    const [datosPolitica, setDatosPolitica] = useState(null);
    const [nuevaFecha, setNuevaFecha] = useState('');
    const [nuevaHora, setNuevaHora] = useState('');
    const [horasDisponibles, setHorasDisponibles] = useState([]);
    const [cargandoHoras, setCargandoHoras] = useState(false);

    const navigate = useNavigate();

    // --- CARGA INICIAL ---
    const fetchTurnos = async () => {
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get('http://127.0.0.1:8000/api/gestion/turnos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setTurnos(response.data); 
        } catch (err) {
            console.error(err);
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
                alert("Formato incorrecto. Solo JPG, PNG o PDF.");
                return;
            }
            if (file.size > 5 * 1024 * 1024) {
                alert("Máximo permitido: 5MB.");
                return;
            }
            setArchivo(file);
            setTurnoIdSubida(turnoId);
        }
    };

    const subirComprobante = async (turnoId) => {
        if (!archivo) return alert("Selecciona un archivo");
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
            alert("¡Comprobante subido con éxito!");
            setArchivo(null);
            setTurnoIdSubida(null);
            fetchTurnos(); 
        } catch (error) {
            console.error("Error subida:", error);
            alert("Error al subir comprobante.");
        }
    };

    // ========================================================================
    // FUNCIÓN: CONSULTAR DISPONIBILIDAD POR FECHA Y SERVICIO
    // ========================================================================
    const consultarDisponibilidad = async (fecha, servicioId) => {
        if (!fecha || !servicioId) {
            setHorasDisponibles([]);
            return;
        }

        // Validar formato de fecha (debe ser YYYY-MM-DD)
        if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha)) {
            console.error('Formato de fecha inválido:', fecha);
            setHorasDisponibles([]);
            return;
        }

        setCargandoHoras(true);
        try {
            const token = localStorage.getItem('access_token');
            const url = `http://127.0.0.1:8000/api/gestion/disponibilidad/?fecha=${fecha}&servicio_id=${servicioId}`;
            console.log('Consultando disponibilidad:', url); // Debug
            const response = await axios.get(url, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            console.log('Respuesta disponibilidad:', response.data); // Debug
            setHorasDisponibles(response.data.horarios_disponibles || []);
        } catch (error) {
            console.error('Error consultando disponibilidad:', error);
            setHorasDisponibles([]);
        } finally {
            setCargandoHoras(false);
        }
    };

    // Obtener fecha mínima (hoy)
    const getMinDate = () => {
        const today = new Date();
        return today.toISOString().split('T')[0]; // Formato YYYY-MM-DD
    };

    // Cuando cambie la fecha, consultar horas disponibles
    const handleFechaChange = (e) => {
        const valorFecha = e.target.value;
        setNuevaFecha(valorFecha); // Actualizamos el estado visual siempre

        // 1. VALIDACIÓN: ¿La fecha tiene una longitud lógica? (YYYY-MM-DD son 10 chars)
        if (!valorFecha || valorFecha.length < 10) return;

        // 2. VALIDACIÓN: Evitar años absurdos (Ej: 0002, 0202)
        const anio = parseInt(valorFecha.split('-')[0]);
        const anioActual = new Date().getFullYear();

        // Si el año es menor al actual, NI SIQUIERA LLAMAMOS A LA API
        if (anio < anioActual) {
            console.log("Año inválido detectado, esperando input completo...");
            return;
        }

        // 3. VALIDACIÓN: No permitir fechas pasadas
        if (esTurnoPasado(valorFecha, '23:59')) { // Usamos tu helper existente
             // Opcional: Podrías limpiar los horarios aquí
             setHorasDisponibles([]); 
             return;
        }

        // Si pasa los filtros, recién ahí molestamos al Backend
        console.log(`Fecha válida detectada (${valorFecha}), consultando API...`);
        
        // Asumiendo que turnoSeleccionado tiene el servicio_id
        if (turnoSeleccionado && turnoSeleccionado.servicio) {
             consultarDisponibilidad(valorFecha, turnoSeleccionado.servicio);
        } else {
             console.error("No hay servicio asociado al turno seleccionado");
        }
    };

    // ========================================================================
    // LÓGICA 2: GESTIÓN INTELIGENTE
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
            setNuevaFecha('');
            setNuevaHora('');
            setHorasDisponibles([]);
            setModalAbierto(true);
        } catch (error) {
            // Manejo especial para bloqueo de 48hs (Error 400)
            if (error.response && error.response.status === 400 && error.response.data.mensaje_bloqueo) {
                alert(`${error.response.data.mensaje_bloqueo}\nContacto: ${error.response.data.contacto}`);
            } else {
                alert("Error al consultar opciones del turno.");
            }
        }
    };

    const ejecutarAccion = async (tipoAccion) => {
        try {
            const token = localStorage.getItem('access_token');
            const payload = { accion: tipoAccion };

            if (tipoAccion === 'REPROGRAMAR') {
                if (!nuevaFecha || !nuevaHora) return alert("Selecciona fecha y hora nueva.");
                payload.nueva_fecha = nuevaFecha;
                payload.nueva_hora = nuevaHora;
            } else if (tipoAccion === 'CANCELAR') {
                if (!window.confirm("¿Estás segura? Esta acción es irreversible.")) return;
            }

            const res = await axios.post(
                `http://127.0.0.1:8000/api/gestion/turnos/${turnoSeleccionado.id}/gestionar/`,
                payload,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            alert(res.data.mensaje);
            cerrarModal();
            fetchTurnos();

        } catch (error) {
            alert(error.response?.data?.error || "Error al procesar la solicitud");
        }
    };

    const cerrarModal = () => {
        setModalAbierto(false);
        setTurnoSeleccionado(null);
        setDatosPolitica(null);
        setNuevaFecha('');
        setNuevaHora('');
    };

    if (loading) return <div className="text-center mt-10">Cargando turnos...</div>;

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-4xl mx-auto">
                <button onClick={() => navigate('/perfil')} className="mb-4 text-blue-600 hover:underline">← Volver al Perfil</button>
                <h1 className="text-3xl font-bold text-gray-800 mb-6">Mis Turnos</h1>

                {turnos.length === 0 ? (
                    <p className="text-gray-500">No tienes turnos activos.</p>
                ) : (
                    <div className="space-y-4">
                        {turnos.map((turno) => {
                            // 1. Calculamos si el turno ya pasó
                            const vencido = esTurnoPasado(turno.fecha, turno.hora_inicio);
                            const estadoFinal = turno.estado === 'realizado' || turno.estado === 'cancelado';
                            
                            // 2. Definimos estilos condicionales (Grisado si vencido)
                            const cardStyle = vencido && !estadoFinal
                                ? "bg-gray-100 border-l-4 border-gray-400 opacity-75" 
                                : "bg-white border-l-4 border-pink-500 shadow-md";

                            return (
                                <div key={turno.id} className={`p-6 rounded-lg ${cardStyle} relative transition-all`}>
                                    <div className="flex flex-col md:flex-row justify-between items-start gap-4">
                                        
                                        {/* INFO DEL TURNO */}
                                        <div className="flex-1">
                                            <h3 className={`text-xl font-bold ${vencido ? 'text-gray-500' : 'text-gray-800'}`}>
                                                {turno.servicio_nombre || "Servicio Capilar"}
                                            </h3>
                                            <p className="text-gray-600 text-lg">📅 {turno.fecha} - 🕒 {turno.hora_inicio}</p>
                                            
                                            <div className="mt-2 flex items-center gap-2">
                                                {/* Badge de Estado */}
                                                <span className={`px-2 py-1 rounded text-sm font-bold ${
                                                    turno.estado === 'confirmado' ? 'bg-green-100 text-green-800' :
                                                    turno.estado === 'cancelado' ? 'bg-red-100 text-red-800' :
                                                    'bg-yellow-100 text-yellow-800'
                                                }`}>
                                                    {turno.estado.toUpperCase()}
                                                </span>

                                                {/* Badge de VENCIDO (Solo si pasó fecha y no está en estado final) */}
                                                {vencido && !estadoFinal && (
                                                    <span className="px-2 py-1 rounded text-sm font-bold bg-gray-300 text-gray-700">
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
                                                    className="bg-gray-100 text-gray-700 hover:bg-gray-200 px-4 py-2 rounded-lg text-sm font-bold border border-gray-300 w-full md:w-auto shadow-sm"
                                                >
                                                    Gestionar / Cancelar
                                                </button>
                                            )}

                                            {/* MENSAJE SI ESTÁ VENCIDO */}
                                            {vencido && !estadoFinal && (
                                                <p className="text-xs text-gray-500 italic text-right max-w-[200px]">
                                                    Este turno ya pasó. Si asististe, pronto se marcará como realizado.
                                                </p>
                                            )}

                                            {/* LOGICA DE COMPROBANTE (Solo si NO vencido) */}
                                            {!vencido && turno.estado === 'esperando_sena' && (
                                                <div className="w-full bg-pink-50 p-3 rounded border border-pink-200">
                                                    <p className="text-xs text-pink-700 font-bold mb-2">Subir Comprobante:</p>
                                                    <input 
                                                        type="file" 
                                                        accept="image/*,.pdf"
                                                        onChange={(e) => handleFileChange(e, turno.id)} 
                                                        className="block w-full text-xs text-slate-500 file:mr-2 file:py-1 file:px-2 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-pink-100 file:text-pink-700 hover:file:bg-pink-200"
                                                    />
                                                    {turnoIdSubida === turno.id && archivo && (
                                                        <button onClick={() => subirComprobante(turno.id)} className="mt-2 w-full bg-pink-600 text-white text-xs font-bold py-1 rounded">
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
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in-up">
                        <div className="flex justify-between items-center mb-4">
                            <h2 className="text-xl font-bold text-gray-800">Gestionar Turno</h2>
                            <button onClick={cerrarModal} className="text-gray-400 hover:text-gray-600">✕</button>
                        </div>

                        <div className={`p-4 rounded-lg mb-6 border-l-4 ${
                            datosPolitica.tipo_alerta === 'info' 
                                ? 'bg-blue-50 border-blue-500 text-blue-800' 
                                : 'bg-orange-50 border-orange-500 text-orange-800'
                        }`}>
                            <p className="font-medium">{datosPolitica.mensaje}</p>
                            <p className="text-xs mt-1 opacity-80">
                                Cambios realizados: {datosPolitica.cambios_realizados}/{datosPolitica.limite_cambios}
                            </p>
                        </div>

                        {datosPolitica.puede_reprogramar && (
                            <div className="mb-6">
                                <h3 className="font-bold text-gray-700 mb-4">Reprogramar Turno</h3>
                                
                                {/* Selector de Fecha */}
                                <div className="mb-4">
                                    <label className="block text-sm font-semibold text-gray-600 mb-2">Selecciona Nueva Fecha</label>
                                    <input 
                                        type="date" 
                                        className="w-full border border-gray-300 p-3 rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                        value={nuevaFecha} 
                                        onChange={handleFechaChange}
                                        min={getMinDate()}
                                    />
                                </div>

                                {/* Selector de Hora (Dinámico) */}
                                {nuevaFecha && (
                                    <div className="mb-4">
                                        <label className="block text-sm font-semibold text-gray-600 mb-2">
                                            Selecciona Nueva Hora
                                            {cargandoHoras && <span className="text-blue-600 ml-2">Cargando...</span>}
                                        </label>
                                        {horasDisponibles.length > 0 ? (
                                            <select 
                                                className="w-full border border-gray-300 p-3 rounded focus:ring-2 focus:ring-blue-500 outline-none"
                                                value={nuevaHora}
                                                onChange={(e) => setNuevaHora(e.target.value)}
                                            >
                                                <option value="">-- Selecciona una hora --</option>
                                                {horasDisponibles.map((hora, idx) => (
                                                    <option key={idx} value={hora}>
                                                        {hora}
                                                    </option>
                                                ))}
                                            </select>
                                        ) : (
                                            <p className="text-red-600 text-sm">No hay horarios disponibles para esta fecha</p>
                                        )}
                                    </div>
                                )}

                                {/* Botón Confirmar */}
                                <button 
                                    onClick={() => ejecutarAccion('REPROGRAMAR')} 
                                    disabled={!nuevaFecha || !nuevaHora}
                                    className="w-full bg-blue-600 text-white font-bold py-3 rounded hover:bg-blue-700 transition disabled:bg-gray-400 disabled:cursor-not-allowed"
                                >
                                    Confirmar Nueva Fecha
                                </button>
                            </div>
                        )}

                        <hr className="my-4 border-gray-200" />

                        <div>
                            <h3 className="font-bold text-gray-700 mb-2">Cancelar Definitivamente</h3>
                            <button onClick={() => ejecutarAccion('CANCELAR')} className="w-full bg-white border-2 border-red-500 text-red-600 font-bold py-2 rounded hover:bg-red-50 transition">
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