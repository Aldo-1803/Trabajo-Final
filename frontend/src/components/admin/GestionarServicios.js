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

    if (loading) return <div className="p-8 text-center" style={{ color: '#8B8682' }}>Cargando configuración...</div>;
    if (error) return <div className="p-8 text-center" style={{ color: '#C73E3E' }}>Error: {error}</div>;

    return (
        <div className="p-8 min-h-screen" style={{ backgroundColor: '#F5EBE0' }}>
            <div className="max-w-6xl mx-auto">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Gestión de Servicios</h1>
                        <p style={{ color: '#8B8682' }}>Define precios, rutinas automáticas e impacto en el cabello.</p>
                    </div>
                    <div className="flex gap-2">
                        <button 
                            onClick={() => {
                                resetForm();
                                setShowNewForm(true);
                            }}
                            className="text-white px-4 py-2 rounded-lg font-bold transition"
                            style={{ backgroundColor: '#AB9A91' }}
                            onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                            onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                        >
                            + Nuevo Servicio
                        </button>
                        <button onClick={() => navigate('/admin-dashboard')} className="font-bold transition" style={{ color: '#817773' }} onMouseEnter={(e) => e.target.style.color = '#AB9A91'} onMouseLeave={(e) => e.target.style.color = '#817773'}>
                            ← Volver
                        </button>
                    </div>
                </div>

                {/* FORMULARIO DE CREAR/EDITAR */}
                {(showNewForm || editingId) && (
                    <div className="p-6 rounded-xl shadow-lg mb-8 border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
                        <h3 className="text-xl font-bold mb-4" style={{ color: '#817773', borderBottom: '2px solid #E3D5CA', paddingBottom: '0.5rem' }}>
                            {editingId ? '✏️ Editar Servicio' : '➕ Crear Nuevo Servicio'}
                        </h3>
                        <form onSubmit={handleSave} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Nombre */}
                            <div>
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Nombre *</label>
                                <input 
                                    type="text" 
                                    required
                                    value={formData.nombre}
                                    onChange={e => setFormData({...formData, nombre: e.target.value})}
                                    className="w-full p-2 border rounded-lg focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    placeholder="Ej: Corte de cabello"
                                />
                            </div>

                            {/* Categoría */}
                            <div>
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Categoría</label>
                                <select 
                                    value={formData.categoria}
                                    onChange={e => setFormData({...formData, categoria: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                    style={{ borderColor: '#D5D1CC', backgroundColor: '#F5EBE0', color: '#817773' }}
                                >
                                    <option value="">-- Seleccionar --</option>
                                    {categorias.map(c => (
                                        <option key={c.id} value={c.id}>{c.nombre}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Precio */}
                            <div>
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Precio Base *</label>
                                <input 
                                    type="number" 
                                    step="0.01"
                                    required
                                    value={formData.precio_base}
                                    onChange={e => setFormData({...formData, precio_base: e.target.value})}
                                    className="w-full p-2 border rounded-lg focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    placeholder="0.00"
                                />
                            </div>

                            {/* Duración */}
                            <div>
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Duración (minutos)</label>
                                <input 
                                    type="number" 
                                    value={formData.duracion_estimada}
                                    onChange={e => setFormData({...formData, duracion_estimada: e.target.value})}
                                    className="w-full p-2 border rounded-lg focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    placeholder="60"
                                />
                            </div>

                            {/* Descripción */}
                            <div className="md:col-span-2">
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Descripción</label>
                                <textarea 
                                    value={formData.descripcion}
                                    onChange={e => setFormData({...formData, descripcion: e.target.value})}
                                    className="w-full p-2 border rounded-lg h-20 focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    placeholder="Describe el servicio..."
                                />
                            </div>

                            {/* Rutina Automática */}
                            <div>
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Rutina Automática</label>
                                <select 
                                    value={formData.rutina_recomendada}
                                    onChange={e => setFormData({...formData, rutina_recomendada: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                    style={{ borderColor: '#D5D1CC', backgroundColor: '#F5EBE0', color: '#817773' }}
                                >
                                    <option value="">-- Sin Rutina --</option>
                                    {rutinas.map(r => (
                                        <option key={r.id} value={r.id}>{r.nombre}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Impacto Porosidad */}
                            <div>
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Impacto Porosidad</label>
                                <select 
                                    value={formData.impacto_porosidad}
                                    onChange={e => setFormData({...formData, impacto_porosidad: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                    style={{ borderColor: '#D5D1CC', backgroundColor: '#F5EBE0', color: '#817773' }}
                                >
                                    <option value="">-- Sin Cambio --</option>
                                    {porosidades.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                                </select>
                            </div>

                            {/* Impacto Estado */}
                            <div>
                                <label className="block text-sm font-bold mb-1" style={{ color: '#817773' }}>Impacto Estado</label>
                                <select 
                                    value={formData.impacto_estado}
                                    onChange={e => setFormData({...formData, impacto_estado: e.target.value})}
                                    className="w-full p-2 border rounded-lg"
                                    style={{ borderColor: '#D5D1CC', backgroundColor: '#F5EBE0', color: '#817773' }}
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
                                <label htmlFor="activo" className="text-sm font-bold" style={{ color: '#817773' }}>Servicio Activo</label>
                            </div>

                            {/* Botones */}
                            <div className="md:col-span-2 flex gap-2">
                                <button type="submit" className="flex-1 text-white py-2 rounded-lg font-bold transition" style={{ backgroundColor: '#817773' }} onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'} onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}>
                                    {editingId ? 'Actualizar' : 'Crear'}
                                </button>
                                <button type="button" onClick={resetForm} className="flex-1 py-2 rounded-lg font-bold transition" style={{ backgroundColor: '#E3D5CA', color: '#817773' }} onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'} onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}>
                                    Cancelar
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* LISTA DE SERVICIOS */}
                <div className="grid gap-6">
                    {servicios.length === 0 ? (
                        <div className="p-8 rounded-xl shadow text-center" style={{ backgroundColor: 'white', color: '#8B8682' }}>
                            No hay servicios registrados. ¡Crea el primero!
                        </div>
                    ) : (
                        servicios.map(servicio => (
                            <div key={servicio.id} className="p-6 rounded-xl shadow-md border-l-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 hover:shadow-lg transition-shadow" style={{ backgroundColor: 'white', borderColor: '#D5BDAF', opacity: servicio.activo ? 1 : 0.7 }}>
                                
                                {/* INFO BÁSICA */}
                                <div className="flex-1">
                                    <div className="flex items-center gap-3 mb-2">
                                        <h3 className="text-xl font-bold" style={{ color: '#817773' }}>{servicio.nombre}</h3>
                                        <span className="text-xs px-2 py-1 rounded font-bold" style={{ backgroundColor: servicio.activo ? '#E8F5E8' : '#FFE8E8', color: servicio.activo ? '#2E7D2E' : '#C73E3E' }}>
                                            {servicio.activo ? 'Activo' : 'Inactivo'}
                                        </span>
                                    </div>
                                    {servicio.categoria_nombre && (
                                        <span className="inline-block text-xs px-2 py-1 rounded font-bold mb-2" style={{ backgroundColor: '#E3D5CA', color: '#817773' }}>
                                            {servicio.categoria_nombre}
                                        </span>
                                    )}
                                    {servicio.descripcion && (
                                        <p className="text-sm mb-2" style={{ color: '#5A5451' }}>{servicio.descripcion}</p>
                                    )}
                                    <div className="flex gap-4 text-sm font-semibold" style={{ color: '#8B8682' }}>
                                        <span>Precio: ${servicio.precio_base}</span>
                                        {servicio.duracion_estimada && <span>Duración: {servicio.duracion_estimada} min</span>}
                                    </div>
                                </div>

                                {/* BOTONES DE ACCIÓN */}
                                <div className="flex gap-2 w-full md:w-auto">
                                    <button 
                                        onClick={() => handleEdit(servicio)}
                                        className="flex-1 md:flex-none px-4 py-2 rounded-lg font-bold text-sm transition"
                                        style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                                        onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                                        onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                                    >
                                        Editar
                                    </button>
                                    <button 
                                        onClick={() => toggleActive(servicio)}
                                        className="flex-1 md:flex-none px-4 py-2 rounded-lg font-bold text-sm text-white transition"
                                        style={{ backgroundColor: servicio.activo ? '#AB9A91' : '#2E7D2E' }}
                                        onMouseEnter={(e) => e.target.style.backgroundColor = servicio.activo ? '#817773' : '#1E5C1E'}
                                        onMouseLeave={(e) => e.target.style.backgroundColor = servicio.activo ? '#AB9A91' : '#2E7D2E'}
                                    >
                                        {servicio.activo ? 'Desactivar' : 'Activar'}
                                    </button>
                                    <button 
                                        onClick={() => handleDelete(servicio.id)}
                                        className="flex-1 md:flex-none px-4 py-2 rounded-lg font-bold text-sm text-white transition"
                                        style={{ backgroundColor: '#AB9A91' }}
                                        onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                                        onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
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