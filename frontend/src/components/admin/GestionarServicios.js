import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionarServicios = () => {
    const [servicios, setServicios] = useState([]);
    const [categorias, setCategorias] = useState([]);
    
    // Listas para los selectores (Dropdowns)
    const [rutinas, setRutinas] = useState([]);
    const [porosidades, setPorosidades] = useState([]);
    const [estados, setEstados] = useState([]);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [editingId, setEditingId] = useState(null);
    const [showNewForm, setShowNewForm] = useState(false);
    
    // Formulario para crear/editar
    const [formData, setFormData] = useState({
        nombre: '',
        descripcion: '',
        precio_base: '',
        duracion_estimada: '',
        categoria: '',
        rutina_recomendada: '',
        impacto_porosidad: '',
        impacto_estado: '',
        activo: true
    });

    const navigate = useNavigate();

    useEffect(() => {
        cargarDatos();
    }, []);

    const cargarDatos = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('access_token');
            const config = { headers: { 'Authorization': `Bearer ${token}` } };

            // Peticiones paralelas
            const [servRes, catRes, rutRes, poroRes, estRes] = await Promise.all([
                axios.get('http://127.0.0.1:8000/api/gestion/servicios/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/categorias-servicio/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/rutinas/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/porosidades-cabello/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/estados-generales/', config)
            ]);

            // --- FUNCIÓN AUXILIAR PARA CORREGIR EL ERROR ---
            // Detecta si Django devolvió una lista simple o un objeto paginado
            const getSafeArray = (response) => {
                if (Array.isArray(response.data)) return response.data;
                if (response.data && Array.isArray(response.data.results)) return response.data.results;
                return [];
            };

            // Aplicamos la corrección a TODAS las variables
            setServicios(getSafeArray(servRes));
            setCategorias(getSafeArray(catRes));
            setRutinas(getSafeArray(rutRes));
            setPorosidades(getSafeArray(poroRes)); // <--- AQUÍ ESTABA EL ERROR
            setEstados(getSafeArray(estRes));      // <--- Y AQUÍ TAMBIÉN
            
        } catch (err) {
            console.error("Error cargando datos:", err);
            setError("No se pudieron cargar los datos de configuración.");
        } finally {
            setLoading(false);
        }
    };

    const resetForm = () => {
        setFormData({
            nombre: '',
            descripcion: '',
            precio_base: '',
            duracion_estimada: '',
            categoria: '',
            rutina_recomendada: '',
            impacto_porosidad: '',
            impacto_estado: '',
            activo: true
        });
        setEditingId(null);
        setShowNewForm(false);
    };

    const handleEdit = (servicio) => {
        setShowNewForm(false);
        setEditingId(servicio.id);
        setFormData({
            nombre: servicio.nombre,
            descripcion: servicio.descripcion || '',
            precio_base: servicio.precio_base,
            duracion_estimada: servicio.duracion_estimada || '',
            categoria: servicio.categoria || '',
            rutina_recomendada: servicio.rutina_recomendada || '',
            impacto_porosidad: servicio.impacto_porosidad || '',
            impacto_estado: servicio.impacto_estado || '',
            activo: servicio.activo !== false
        });
    };

    const handleSave = async (e) => {
        e.preventDefault();
        try {
            const token = localStorage.getItem('access_token');
            
            const payload = {
                nombre: formData.nombre,
                descripcion: formData.descripcion,
                precio_base: formData.precio_base,
                duracion_estimada: formData.duracion_estimada || null,
                categoria: formData.categoria ? parseInt(formData.categoria) : null,
                rutina_recomendada: formData.rutina_recomendada ? parseInt(formData.rutina_recomendada) : null,
                impacto_porosidad: formData.impacto_porosidad ? parseInt(formData.impacto_porosidad) : null,
                impacto_estado: formData.impacto_estado ? parseInt(formData.impacto_estado) : null,
                activo: formData.activo
            };

            if (editingId) {
                // ACTUALIZAR
                await axios.patch(`http://127.0.0.1:8000/api/gestion/servicios/${editingId}/`, payload, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                alert('Servicio actualizado correctamente');
            } else {
                // CREAR
                await axios.post('http://127.0.0.1:8000/api/gestion/servicios/', payload, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                alert('Servicio creado correctamente');
            }

            resetForm();
            cargarDatos(); 

        } catch (error) {
            console.error(error);
            alert('Error: ' + (error.response?.data?.detail || 'No se pudo guardar el servicio'));
        }
    };

    const handleDelete = async (servicioId) => {
        if (!window.confirm('¿Estás seguro de que deseas desactivar este servicio?')) return;
        
        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/servicios/${servicioId}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            alert('Servicio desactivado correctamente');
            cargarDatos();
        } catch (error) {
            console.error(error);
            alert('Error al desactivar el servicio');
        }
    };

    const toggleActive = async (servicio) => {
        try {
            const token = localStorage.getItem('access_token');
            await axios.patch(`http://127.0.0.1:8000/api/gestion/servicios/${servicio.id}/`, 
                { activo: !servicio.activo },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            cargarDatos();
        } catch (error) {
            console.error(error);
            alert('Error al cambiar el estado del servicio');
        }
    };

    if (loading) return <div className="p-8 text-center">Cargando configuración...</div>;
    if (error) return <div className="p-8 text-center text-red-600">Error: {error}</div>;

    return (
        <div className="p-8 bg-gray-50 min-h-screen">
            <div className="max-w-6xl mx-auto">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h1 className="text-3xl font-bold text-gray-800">Gestión de Servicios</h1>
                        <p className="text-gray-500">Define precios, rutinas automáticas e impacto en el cabello.</p>
                    </div>
                    <div className="flex gap-2">
                        <button 
                            onClick={() => {
                                resetForm();
                                setShowNewForm(true);
                            }}
                            className="bg-green-600 text-white px-4 py-2 rounded-lg font-bold hover:bg-green-700"
                        >
                            + Nuevo Servicio
                        </button>
                        <button onClick={() => navigate('/admin-dashboard')} className="text-gray-500 hover:underline">
                            ← Volver
                        </button>
                    </div>
                </div>

                {/* FORMULARIO DE CREAR/EDITAR */}
                {(showNewForm || editingId) && (
                    <div className="bg-white p-6 rounded-xl shadow-lg mb-8 border border-blue-300">
                        <h3 className="text-xl font-bold mb-4 text-gray-800">
                            {editingId ? 'Editar Servicio' : 'Crear Nuevo Servicio'}
                        </h3>
                        <form onSubmit={handleSave} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Nombre */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-1">Nombre *</label>
                                <input 
                                    type="text" 
                                    required
                                    value={formData.nombre}
                                    onChange={e => setFormData({...formData, nombre: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                    placeholder="Ej: Corte de cabello"
                                />
                            </div>

                            {/* Categoría */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-1">Categoría</label>
                                <select 
                                    value={formData.categoria}
                                    onChange={e => setFormData({...formData, categoria: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                >
                                    <option value="">-- Seleccionar --</option>
                                    {categorias.map(c => (
                                        <option key={c.id} value={c.id}>{c.nombre}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Precio */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-1">Precio Base *</label>
                                <input 
                                    type="number" 
                                    step="0.01"
                                    required
                                    value={formData.precio_base}
                                    onChange={e => setFormData({...formData, precio_base: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                    placeholder="0.00"
                                />
                            </div>

                            {/* Duración */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-1">Duración (minutos)</label>
                                <input 
                                    type="number" 
                                    value={formData.duracion_estimada}
                                    onChange={e => setFormData({...formData, duracion_estimada: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                    placeholder="60"
                                />
                            </div>

                            {/* Descripción */}
                            <div className="md:col-span-2">
                                <label className="block text-sm font-bold text-gray-700 mb-1">Descripción</label>
                                <textarea 
                                    value={formData.descripcion}
                                    onChange={e => setFormData({...formData, descripcion: e.target.value})}
                                    className="w-full p-2 border rounded-lg h-20"
                                    placeholder="Describe el servicio..."
                                />
                            </div>

                            {/* Rutina Automática */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-1">Rutina Automática</label>
                                <select 
                                    value={formData.rutina_recomendada}
                                    onChange={e => setFormData({...formData, rutina_recomendada: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                >
                                    <option value="">-- Sin Rutina --</option>
                                    {rutinas.map(r => (
                                        <option key={r.id} value={r.id}>{r.nombre}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Impacto Porosidad */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-1">Impacto Porosidad</label>
                                <select 
                                    value={formData.impacto_porosidad}
                                    onChange={e => setFormData({...formData, impacto_porosidad: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                >
                                    <option value="">-- Sin Cambio --</option>
                                    {porosidades.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                                </select>
                            </div>

                            {/* Impacto Estado */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-1">Impacto Estado</label>
                                <select 
                                    value={formData.impacto_estado}
                                    onChange={e => setFormData({...formData, impacto_estado: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                >
                                    <option value="">-- Sin Cambio --</option>
                                    {estados.map(e => <option key={e.id} value={e.id}>{e.nombre}</option>)}
                                </select>
                            </div>

                            {/* Estado Activo/Inactivo */}
                            <div className="flex items-center gap-2">
                                <input 
                                    type="checkbox" 
                                    checked={formData.activo}
                                    onChange={e => setFormData({...formData, activo: e.target.checked})}
                                    className="w-4 h-4"
                                    id="activo"
                                />
                                <label htmlFor="activo" className="text-sm font-bold text-gray-700">Servicio Activo</label>
                            </div>

                            {/* Botones */}
                            <div className="md:col-span-2 flex gap-2">
                                <button type="submit" className="flex-1 bg-blue-600 text-white py-2 rounded-lg font-bold hover:bg-blue-700">
                                    {editingId ? 'Actualizar' : 'Crear'}
                                </button>
                                <button type="button" onClick={resetForm} className="flex-1 bg-gray-400 text-white py-2 rounded-lg font-bold hover:bg-gray-500">
                                    Cancelar
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* LISTA DE SERVICIOS */}
                <div className="grid gap-6">
                    {servicios.length === 0 ? (
                        <div className="bg-white p-8 rounded-xl shadow text-center text-gray-500">
                            No hay servicios registrados. ¡Crea el primero!
                        </div>
                    ) : (
                        servicios.map(servicio => (
                            <div key={servicio.id} className={`bg-white p-6 rounded-xl shadow-md border-l-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 ${
                                servicio.activo ? 'border-green-500' : 'border-red-500 opacity-75'
                            }`}>
                                
                                {/* INFO BÁSICA */}
                                <div className="flex-1">
                                    <div className="flex items-center gap-3 mb-2">
                                        <h3 className="text-xl font-bold text-gray-800">{servicio.nombre}</h3>
                                        <span className={`text-xs px-2 py-1 rounded font-bold ${
                                            servicio.activo ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                                        }`}>
                                            {servicio.activo ? 'Activo' : 'Inactivo'}
                                        </span>
                                    </div>
                                    {servicio.categoria_nombre && (
                                        <span className="inline-block bg-pink-100 text-pink-700 text-xs px-2 py-1 rounded font-bold mb-2">
                                            {servicio.categoria_nombre}
                                        </span>
                                    )}
                                    {servicio.descripcion && (
                                        <p className="text-gray-600 text-sm mb-2">{servicio.descripcion}</p>
                                    )}
                                    <div className="flex gap-4 text-sm font-semibold text-gray-700">
                                        <span>Precio: ${servicio.precio_base}</span>
                                        {servicio.duracion_estimada && <span>Duración: {servicio.duracion_estimada} min</span>}
                                    </div>
                                </div>

                                {/* BOTONES DE ACCIÓN */}
                                <div className="flex gap-2 w-full md:w-auto">
                                    <button 
                                        onClick={() => handleEdit(servicio)}
                                        className="flex-1 md:flex-none bg-blue-600 text-white px-4 py-2 rounded-lg font-bold hover:bg-blue-700 text-sm"
                                    >
                                        Editar
                                    </button>
                                    <button 
                                        onClick={() => toggleActive(servicio)}
                                        className={`flex-1 md:flex-none px-4 py-2 rounded-lg font-bold text-sm ${
                                            servicio.activo 
                                                ? 'bg-yellow-500 text-white hover:bg-yellow-600' 
                                                : 'bg-green-600 text-white hover:bg-green-700'
                                        }`}
                                    >
                                        {servicio.activo ? 'Desactivar' : 'Activar'}
                                    </button>
                                    <button 
                                        onClick={() => handleDelete(servicio.id)}
                                        className="flex-1 md:flex-none bg-red-600 text-white px-4 py-2 rounded-lg font-bold hover:bg-red-700 text-sm"
                                    >
                                        Eliminar
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
};

export default GestionarServicios;