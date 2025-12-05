import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const MisTurnos = () => {
    const [turnos, setTurnos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [archivo, setArchivo] = useState(null);
    const [turnoIdSubida, setTurnoIdSubida] = useState(null);
    const navigate = useNavigate();

    const fetchTurnos = async () => {
        try {
            const token = localStorage.getItem('access_token');
            // Asegúrate que tu viewset permita filtrar o devuelva solo los del usuario
            const response = await axios.get('http://127.0.0.1:8000/api/gestion/turnos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            // Filtramos en el cliente por si acaso la API devuelve todos (aunque debería filtrar el backend)
            // Si tu backend ya filtra por usuario, quita el .filter
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

    const handleFileChange = (e, turnoId) => {
        const file = e.target.files[0];
        
        if (file) {
            // 1. Validar Tipo de Archivo (MIME Type)
            const validTypes = ['image/jpeg', 'image/png', 'application/pdf'];
            if (!validTypes.includes(file.type)) {
                alert("Formato incorrecto.\nSolo se permiten imágenes (JPG, PNG) o documentos PDF.");
                e.target.value = ''; // Limpia el input para que no quede seleccionado
                setArchivo(null);
                setTurnoIdSubida(null);
                return;
            }

            // 2. Validar Tamaño (Opcional, ej: 5MB)
            const maxSize = 5 * 1024 * 1024; // 5MB
            if (file.size > maxSize) {
                alert("El archivo es muy pesado.\nMáximo permitido: 5MB.");
                e.target.value = '';
                setArchivo(null);
                setTurnoIdSubida(null);
                return;
            }

            // Si pasa las validaciones, lo guardamos en el estado
            setArchivo(file);
            setTurnoIdSubida(turnoId);
        }
    };

    const subirComprobante = async (turnoId) => {
        if (!archivo) return alert("Selecciona un archivo primero");

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
            
            // ÉXITO
            alert("¡Comprobante subido con éxito!");
            setArchivo(null);
            setTurnoIdSubida(null);
            fetchTurnos(); 
            
        } catch (error) {
            console.error("Error al subir:", error);

            // --- VALIDACIÓN VISUAL PARA EL VIDEO (ITEM 4) ---
            if (error.response && error.response.data) {
                // El backend devuelve algo como: { "comprobante_pago": ["Formato no soportado..."] }
                // O a veces: { "detail": "..." } o { "non_field_errors": [...] }
                
                const data = error.response.data;
                let mensajeError = "Error al subir el archivo.";

                if (data.comprobante_pago) {
                    mensajeError = data.comprobante_pago[0]; // Tomamos el primer error específico del campo
                } else if (data.detail) {
                    mensajeError = data.detail;
                }

                // Mostramos el mensaje exacto del backend (El profesor verá esto)
                alert(`⚠️ ERROR DE VALIDACIÓN:\n${mensajeError}`);
            } else {
                alert("Error de conexión al subir el comprobante.");
            }
        }
    };

    if (loading) return <div className="text-center mt-10">Cargando turnos...</div>;

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-4xl mx-auto">
                <button onClick={() => navigate('/perfil')} className="mb-4 text-blue-600 hover:underline">← Volver al Perfil</button>
                <h1 className="text-3xl font-bold text-gray-800 mb-6">Mis Turnos</h1>

                {turnos.length === 0 ? (
                    <p>No tienes turnos solicitados.</p>
                ) : (
                    <div className="space-y-4">
                        {turnos.map((turno) => (
                            <div key={turno.id} className="bg-white p-6 rounded-lg shadow-md border-l-4 border-pink-500">
                                <div className="flex justify-between items-start">
                                    <div>
                                        <h3 className="text-xl font-bold text-gray-800">{turno.servicio_nombre || "Servicio"}</h3>
                                        <p className="text-gray-600">📅 {turno.fecha} - 🕒 {turno.hora_inicio}</p>
                                        <p className="mt-2 font-semibold">
                                            Estado: 
                                            <span className={`ml-2 px-2 py-1 rounded text-sm ${
                                                turno.estado === 'confirmado' ? 'bg-green-100 text-green-800' :
                                                turno.estado === 'cancelado' ? 'bg-red-100 text-red-800' :
                                                'bg-yellow-100 text-yellow-800'
                                            }`}>
                                                {turno.estado.toUpperCase()}
                                            </span>
                                        </p>
                                    </div>
                                    
                                    {/* LÓGICA DE COMPROBANTE */}
                                    <div className="text-right">
                                        {/* CASO 1: Turno recién solicitado (Esperando aceptación) */}
                                        {turno.estado === 'solicitado' && (
                                            <span className="text-yellow-600 text-sm font-semibold animate-pulse">
                                                ⏳ Esperando aprobación del profesional...
                                            </span>
                                        )}

                                        {/* CASO 2: Turno aceptado (Habilitar pago) */}
                                        {turno.estado === 'esperando_sena' && (
                                            <div className="mt-2 p-3 bg-pink-50 border border-pink-200 rounded-lg">
                                                <p className="text-sm text-pink-700 font-bold mb-1">¡Turno Aceptado!</p>
                                                <p className="text-xs text-gray-500 mb-2">Por favor abona la seña y sube el comprobante.</p>
                                                
                                                <input 
                                                    type="file" 
                                                    accept="image/jpeg, image/png, application/pdf"
                                                    onChange={(e) => handleFileChange(e, turno.id)} 
                                                    className="block w-full text-xs text-slate-500 file:mr-2 file:py-1 file:px-2 file:rounded-full file:border-0 file:text-xs file:font-semibold file:bg-pink-100 file:text-pink-700 hover:file:bg-pink-200"
                                                />
                                                {turnoIdSubida === turno.id && archivo && (
                                                    <button 
                                                        onClick={() => subirComprobante(turno.id)}
                                                        className="mt-2 w-full bg-pink-600 text-white px-4 py-1.5 rounded hover:bg-pink-700 text-xs font-bold transition-colors"
                                                    >
                                                        ENVIAR COMPROBANTE
                                                    </button>
                                                )}
                                            </div>
                                        )}

                                        {/* CASO 3: Comprobante subido (Esperando revisión final) */}
                                        {turno.comprobante_pago && turno.estado !== 'esperando_sena' && (
                                            <span className="text-green-600 text-sm font-bold">✓ Comprobante Enviado</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default MisTurnos;