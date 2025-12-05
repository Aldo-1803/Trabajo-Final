import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionarServicios = () => {
    const [servicios, setServicios] = useState([]);
    
    // Listas para los selectores (Dropdowns)
    const [rutinas, setRutinas] = useState([]);
    const [porosidades, setPorosidades] = useState([]);
    const [estados, setEstados] = useState([]);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [editingId, setEditingId] = useState(null);
    
    // Formulario
    const [formData, setFormData] = useState({
        nombre: '',
        precio_base: '',
        rutina_recomendada: '',
        impacto_porosidad: '',
        impacto_estado: ''
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
            const [servRes, rutRes, poroRes, estRes] = await Promise.all([
                axios.get('http://127.0.0.1:8000/api/gestion/servicios/', config),
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

    const handleEdit = (servicio) => {
        setEditingId(servicio.id);
        setFormData({
            nombre: servicio.nombre,
            precio_base: servicio.precio_base,
            rutina_recomendada: servicio.rutina_recomendada || '',
            impacto_porosidad: servicio.impacto_porosidad || '',
            impacto_estado: servicio.impacto_estado || ''
        });
    };

    const handleSave = async (e) => {
        e.preventDefault();
        try {
            const token = localStorage.getItem('access_token');
            
            // Convertimos strings vacíos a null para que el backend no falle
            const payload = {
                ...formData,
                rutina_recomendada: formData.rutina_recomendada || null,
                impacto_porosidad: formData.impacto_porosidad || null,
                impacto_estado: formData.impacto_estado || null
            };

            await axios.patch(`http://127.0.0.1:8000/api/gestion/servicios/${editingId}/`, payload, {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            alert('Servicio configurado correctamente');
            setEditingId(null);
            cargarDatos(); 

        } catch (error) {
            console.error(error);
            alert('Error al guardar cambios.');
        }
    };

    if (loading) return <div className="p-8 text-center">Cargando configuración...</div>;
    if (error) return <div className="p-8 text-center text-red-600">Error: {error}</div>;

    return (
        <div className="p-8 bg-gray-50 min-h-screen">
            <div className="max-w-6xl mx-auto">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h1 className="text-3xl font-bold text-gray-800">Configuración de Servicios</h1>
                        <p className="text-gray-500">Define precios, rutinas automáticas e impacto en el cabello.</p>
                    </div>
                    <button onClick={() => navigate('/admin-dashboard')} className="text-gray-500 hover:underline">
                        ← Volver
                    </button>
                </div>

                <div className="grid gap-6">
                    {servicios.map(servicio => (
                        <div key={servicio.id} className="bg-white p-6 rounded-xl shadow-md border border-gray-100 flex flex-col md:flex-row gap-6">
                            
                            {/* INFO BÁSICA (Izquierda) */}
                            <div className="flex-1">
                                <h3 className="text-xl font-bold text-gray-800 mb-1">{servicio.nombre}</h3>
                                <span className="inline-block bg-pink-100 text-pink-700 text-xs px-2 py-1 rounded font-bold mb-2">
                                    {servicio.categoria_nombre}
                                </span>
                                <p className="text-gray-500 text-sm mb-2">{servicio.descripcion}</p>
                                <p className="font-bold text-gray-700">$ {servicio.precio_base}</p>
                            </div>

                            {/* FORMULARIO DE EDICIÓN RÁPIDA (Derecha) */}
                            <div className="flex-1 bg-gray-50 p-4 rounded-lg border border-gray-200">
                                {editingId === servicio.id ? (
                                    <form onSubmit={handleSave} className="space-y-3">
                                        <div>
                                            <label className="block text-xs font-bold text-gray-500 uppercase">Rutina Automática</label>
                                            <select 
                                                className="w-full p-2 border rounded text-sm"
                                                value={formData.rutina_recomendada}
                                                onChange={e => setFormData({...formData, rutina_recomendada: e.target.value})}
                                            >
                                                <option value="">-- Sin Rutina Automática --</option>
                                                {rutinas.map(r => (
                                                    <option key={r.id} value={r.id}>{r.nombre}</option>
                                                ))}
                                            </select>
                                        </div>

                                        <div className="grid grid-cols-2 gap-2">
                                            <div>
                                                <label className="block text-xs font-bold text-gray-500 uppercase">Impacto Porosidad</label>
                                                <select 
                                                    className="w-full p-2 border rounded text-sm"
                                                    value={formData.impacto_porosidad}
                                                    onChange={e => setFormData({...formData, impacto_porosidad: e.target.value})}
                                                >
                                                    <option value="">-- Sin Cambio --</option>
                                                    {porosidades.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-gray-500 uppercase">Impacto Estado</label>
                                                <select 
                                                    className="w-full p-2 border rounded text-sm"
                                                    value={formData.impacto_estado}
                                                    onChange={e => setFormData({...formData, impacto_estado: e.target.value})}
                                                >
                                                    <option value="">-- Sin Cambio --</option>
                                                    {estados.map(e => <option key={e.id} value={e.id}>{e.nombre}</option>)}
                                                </select>
                                            </div>
                                        </div>

                                        <div className="flex gap-2 mt-2">
                                            <button type="submit" className="flex-1 bg-green-600 text-white py-2 rounded font-bold text-sm hover:bg-green-700">Guardar</button>
                                            <button type="button" onClick={() => setEditingId(null)} className="flex-1 bg-gray-300 text-gray-700 py-2 rounded font-bold text-sm">Cancelar</button>
                                        </div>
                                    </form>
                                ) : (
                                    /* VISTA DE SOLO LECTURA (Resumen de configuración) */
                                    <div className="space-y-2">
                                        <div className="flex justify-between items-center border-b pb-2">
                                            <span className="text-xs text-gray-500">Rutina vinculada:</span>
                                            <span className={`text-xs font-bold ${servicio.rutina_recomendada ? 'text-purple-600' : 'text-gray-400'}`}>
                                                {servicio.rutina_nombre || 'Ninguna'}
                                            </span>
                                        </div>
                                        <div className="flex justify-between items-center border-b pb-2">
                                            <span className="text-xs text-gray-500">Impacto Automático:</span>
                                            <span className="text-xs font-bold text-gray-700">
                                                {servicio.impacto_porosidad || servicio.impacto_estado ? 'Activo' : 'Inactivo'}
                                            </span>
                                        </div>
                                        <button 
                                            onClick={() => handleEdit(servicio)}
                                            className="w-full bg-white border border-blue-500 text-blue-600 py-2 rounded font-bold text-sm hover:bg-blue-50 mt-2"
                                        >
                                            Configurar Inteligencia
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default GestionarServicios;