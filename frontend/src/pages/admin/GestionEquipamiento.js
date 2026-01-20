import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const GestionEquipamiento = () => {
    // --- ESTADOS ---
    const [equipos, setEquipos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false);
    
    const [form, setForm] = useState({
        id: null,
        codigo: '',
        nombre: '',
        tipo: '',
        estado: 'DISPONIBLE',
        ubicacion: '',
        observaciones: '',
        fecha_adquisicion: new Date().toISOString().split('T')[0]
    });
    const [tipos, setTipos] = useState([]);

    const navigate = useNavigate();

    // --- DICCIONARIO DE ESTADOS (Para visualización bonita) ---
    const ESTADOS = {
        'DISPONIBLE': { label: 'Disponible', color: 'bg-green-100 text-green-800' },
        'EN_USO': { label: 'En Uso', color: 'bg-blue-100 text-blue-800' },
        'MANTENIMIENTO': { label: 'En Mantenimiento', color: 'bg-orange-100 text-orange-800' },
        'FUERA_SERVICIO': { label: 'Fuera de Servicio / Roto', color: 'bg-red-100 text-red-800' },
    };

    // --- CARGA DE DATOS ---
    const cargarEquipos = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/equipamiento/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            // Maneja tanto arrays como objetos con estructura results
            const datos = Array.isArray(res.data) ? res.data : res.data.results || [];
            setEquipos(datos);
        } catch (error) {
            console.error("Error al cargar equipamiento:", error);
            if (error.response?.status === 403) navigate('/');
        } finally {
            setLoading(false);
        }
    };

    // --- CARGA DE TIPOS DE EQUIPAMIENTO ---
    const cargarTipos = async () => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/tipo-equipamiento/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const datos = Array.isArray(res.data) ? res.data : res.data.results || [];
            setTipos(datos);
        } catch (error) {
            console.error("Error al cargar tipos de equipamiento:", error);
        }
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        cargarEquipos();
        cargarTipos();
    }, []);

    // --- MANEJADORES DEL FORMULARIO ---
    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value });
    };

    const abrirModal = (equipo = null) => {
        if (equipo) {
            setModoEdicion(true);
            setForm(equipo);
        } else {
            setModoEdicion(false);
            setForm({ 
                id: null, 
                codigo: '', 
                nombre: '', 
                tipo: '', 
                estado: 'DISPONIBLE',
                ubicacion: '',
                observaciones: '',
                fecha_adquisicion: new Date().toISOString().split('T')[0]
            });
        }
        setModalAbierto(true);
    };

    // --- ACCIONES CRUD ---
    const guardarEquipo = async (e) => {
        e.preventDefault();
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };

        try {
            if (modoEdicion) {
                await axios.put(`http://127.0.0.1:8000/api/gestion/equipamiento/${form.id}/`, form, { headers });
                notify.success("Equipo actualizado correctamente.");
            } else {
                await axios.post('http://127.0.0.1:8000/api/gestion/equipamiento/', form, { headers });
                notify.success("Nuevo equipo registrado.");
            }
            setModalAbierto(false);
            cargarEquipos();
        } catch (error) {
            // Manejo de errores (ej: código duplicado)
            const msg = error.response?.data?.codigo ? "El código ya existe." : "Error al guardar.";
            notify.error(`${msg}`);
        }
    };

    const eliminarEquipo = async (id, nombre) => {
        const result = await confirmarAccion({
            title: "¿Dar de baja equipamiento?",
            text: `Se eliminará "${nombre}". Esta acción es permanente.`,
            confirmButtonText: "Sí, eliminar"
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/equipamiento/${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success("Equipo eliminado del inventario.");
            cargarEquipos();
        } catch (error) {
            // Aquí el backend valida si hay turnos en las próximas 24hs
            const msg = error.response?.data?.error || "No se puede eliminar (¿Está en uso?).";
            notify.error(`${msg}`);
        }
    };

    // --- RENDERIZADO ---
    return (
        <div className="max-w-6xl mx-auto p-6 mt-8">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">Gestión de Equipamiento</h1>
                    <p className="text-gray-500">Control de mobiliario y herramientas</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => navigate('/admin-dashboard')} className="text-gray-500 hover:underline px-3">
                        ← Volver
                    </button>
                    <button 
                        onClick={() => abrirModal()}
                        className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-bold shadow-md"
                    >
                        + Registrar Equipo
                    </button>
                </div>
            </div>

            {/* TABLA */}
            <div className="bg-white shadow-lg rounded-lg overflow-hidden border border-gray-200">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando equipos...</div>
                ) : equipos.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No hay equipamiento registrado.</div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Código</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Nombre</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Tipo</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Estado</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Ubicación</th>
                                <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {equipos.map((eq) => (
                                <tr key={eq.id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono font-bold text-gray-600">
                                        {eq.codigo}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                        {eq.nombre}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                        {eq.tipo_nombre || '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={`px-2 py-1 text-xs font-bold rounded-full ${ESTADOS[eq.estado]?.color || 'bg-gray-100'}`}>
                                            {ESTADOS[eq.estado]?.label || eq.estado}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                        {eq.ubicacion || '-'}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button 
                                            onClick={() => abrirModal(eq)}
                                            className="text-blue-600 hover:text-blue-900 mr-4 font-bold"
                                        >
                                            Editar
                                        </button>
                                        <button 
                                            onClick={() => eliminarEquipo(eq.id, eq.nombre)}
                                            className="text-red-600 hover:text-red-900 font-bold"
                                        >
                                            Baja
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* MODAL */}
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in-up">
                        <h2 className="text-xl font-bold text-gray-800 mb-4">
                            {modoEdicion ? '🛠️ Editar Equipo' : '📦 Nuevo Equipo'}
                        </h2>
                        
                        <form onSubmit={guardarEquipo} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Código ID</label>
                                <input 
                                    type="text" 
                                    name="codigo" 
                                    required
                                    placeholder="Ej: LAV-01"
                                    className="mt-1 block w-full border border-gray-300 rounded p-2"
                                    value={form.codigo}
                                    onChange={handleChange}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Nombre</label>
                                <input 
                                    type="text" 
                                    name="nombre" 
                                    required
                                    placeholder="Ej: Lavacabezas Principal"
                                    className="mt-1 block w-full border border-gray-300 rounded p-2"
                                    value={form.nombre}
                                    onChange={handleChange}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Tipo de Equipamiento</label>
                                <select 
                                    name="tipo" 
                                    required
                                    className="mt-1 block w-full border border-gray-300 rounded p-2 bg-white"
                                    value={form.tipo}
                                    onChange={handleChange}
                                >
                                    <option value="">-- Selecciona un tipo --</option>
                                    {tipos.map((tipo) => (
                                        <option key={tipo.id} value={tipo.id}>{tipo.nombre}</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Ubicación</label>
                                <input 
                                    type="text" 
                                    name="ubicacion" 
                                    placeholder="Ej: Salón principal, estante derecho"
                                    className="mt-1 block w-full border border-gray-300 rounded p-2"
                                    value={form.ubicacion}
                                    onChange={handleChange}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Observaciones</label>
                                <textarea 
                                    name="observaciones" 
                                    placeholder="Notas adicionales"
                                    className="mt-1 block w-full border border-gray-300 rounded p-2"
                                    rows="2"
                                    value={form.observaciones}
                                    onChange={handleChange}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Fecha de Adquisición</label>
                                <input 
                                    type="date" 
                                    name="fecha_adquisicion" 
                                    required
                                    className="mt-1 block w-full border border-gray-300 rounded p-2"
                                    value={form.fecha_adquisicion}
                                    onChange={handleChange}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Estado Actual</label>
                                <select 
                                    name="estado" 
                                    className="mt-1 block w-full border border-gray-300 rounded p-2 bg-white"
                                    value={form.estado}
                                    onChange={handleChange}
                                >
                                    <option value="DISPONIBLE">🟢 Disponible</option>
                                    <option value="EN_USO">🔵 En Uso</option>
                                    <option value="MANTENIMIENTO">🟠 En Mantenimiento</option>
                                    <option value="FUERA_SERVICIO">🔴 Fuera de Servicio / Roto</option>
                                </select>
                            </div>

                            <div className="flex justify-end gap-3 mt-6">
                                <button type="button" onClick={() => setModalAbierto(false)} className="px-4 py-2 border rounded-lg text-gray-600 hover:bg-gray-100">
                                    Cancelar
                                </button>
                                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-bold">
                                    Guardar
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default GestionEquipamiento;