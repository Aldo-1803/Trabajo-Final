import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const GestionarServicios = () => {
    const [servicios, setServicios] = useState([]);
    const [categorias, setCategorias] = useState([]);
    
    // Listas para los selectores (Dropdowns)
    const [rutinas, setRutinas] = useState([]);
    const [porosidades, setPorosidades] = useState([]);
    const [estados, setEstados] = useState([]);
    const [tiposEquipamiento, setTiposEquipamiento] = useState([]);

    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [editingId, setEditingId] = useState(null);
    const [showModal, setShowModal] = useState(false);
    
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
        plantilla_formula: {
            rubios: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' },
            mieles: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' },
            beigeCaramelo: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' }
        },
        requisitos_equipamiento: [],
        activo: true
    });

    const navigate = useNavigate();

    // Función para convertir estructura de fórmula a texto
    const formulaToString = (formulaObj) => {
        if (!formulaObj) return '';
        const lines = [];
        
        if (formulaObj.rubios && (formulaObj.rubios.base || formulaObj.rubios.medios)) {
            lines.push(`Rubios:`);
            if (formulaObj.rubios.base) lines.push(`Base: ${formulaObj.rubios.base} oxidante ${formulaObj.rubios.oxidante_base || ''}`);
            if (formulaObj.rubios.medios) lines.push(`Medios/puntas: ${formulaObj.rubios.medios} oxidante ${formulaObj.rubios.oxidante_medios || ''}`);
        }
        
        if (formulaObj.mieles && (formulaObj.mieles.base || formulaObj.mieles.medios)) {
            lines.push(`Mieles:`);
            if (formulaObj.mieles.base) lines.push(`Base: ${formulaObj.mieles.base} oxidante ${formulaObj.mieles.oxidante_base || ''}`);
            if (formulaObj.mieles.medios) lines.push(`Medios/puntas: ${formulaObj.mieles.medios} oxidante ${formulaObj.mieles.oxidante_medios || ''}`);
        }
        
        if (formulaObj.beigeCaramelo && (formulaObj.beigeCaramelo.base || formulaObj.beigeCaramelo.medios)) {
            lines.push(`Beige caramelo/Brown:`);
            if (formulaObj.beigeCaramelo.base) lines.push(`Base: ${formulaObj.beigeCaramelo.base} oxidante ${formulaObj.beigeCaramelo.oxidante_base || ''}`);
            if (formulaObj.beigeCaramelo.medios) lines.push(`Medios/puntas: ${formulaObj.beigeCaramelo.medios} oxidante ${formulaObj.beigeCaramelo.oxidante_medios || ''}`);
        }
        
        return lines.join('\n');
    };

    // Función para parsear texto a estructura de fórmula (intento de parseo simple)
    const stringToFormula = (str) => {
        const formula = {
            rubios: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' },
            mieles: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' },
            beigeCaramelo: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' }
        };
        
        if (!str) return formula;
        
        // Intenta parsear si existe el formato esperado
        const lines = str.split('\n');
        let currentType = null;
        
        for (let line of lines) {
            line = line.trim();
            if (line.includes('Rubios')) currentType = 'rubios';
            else if (line.includes('Mieles')) currentType = 'mieles';
            else if (line.includes('Beige') || line.includes('caramelo')) currentType = 'beigeCaramelo';
            else if (currentType && line.includes('Base:')) {
                const match = line.match(/Base:\s*([^o]+)\s*oxidante\s*(.+)/i);
                if (match) {
                    formula[currentType].base = match[1].trim();
                    formula[currentType].oxidante_base = match[2].trim();
                }
            }
            else if (currentType && line.includes('Medios')) {
                const match = line.match(/Medios[^:]*:\s*([^o]+)\s*oxidante\s*(.+)/i);
                if (match) {
                    formula[currentType].medios = match[1].trim();
                    formula[currentType].oxidante_medios = match[2].trim();
                }
            }
        }
        
        return formula;
    };

    useEffect(() => {
        cargarDatos();
    }, []);

    const cargarDatos = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('access_token');
            const config = { headers: { 'Authorization': `Bearer ${token}` } };

            // Peticiones paralelas
            const [servRes, catRes, rutRes, poroRes, estRes, tipoEquipRes] = await Promise.all([
                axios.get('http://127.0.0.1:8000/api/gestion/servicios/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/categorias-servicio/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/rutinas/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/porosidades-cabello/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/estados-generales/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/tipo-equipamiento/', config)
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
            setPorosidades(getSafeArray(poroRes));
            setEstados(getSafeArray(estRes));
            setTiposEquipamiento(getSafeArray(tipoEquipRes));
            
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
            plantilla_formula: {
                rubios: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' },
                mieles: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' },
                beigeCaramelo: { base: '', medios: '', oxidante_base: '', oxidante_medios: '' }
            },
            requisitos_equipamiento: [],
            activo: true
        });
        setEditingId(null);
        setShowModal(false);
    };

    const handleEdit = (servicio) => {
        setEditingId(servicio.id);
        const parsedFormula = stringToFormula(servicio.plantilla_formula || '');
        setFormData({
            nombre: servicio.nombre,
            descripcion: servicio.descripcion || '',
            precio_base: servicio.precio_base,
            duracion_estimada: servicio.duracion_estimada || '',
            categoria: servicio.categoria || '',
            rutina_recomendada: servicio.rutina_recomendada || '',
            impacto_porosidad: servicio.impacto_porosidad || '',
            impacto_estado: servicio.impacto_estado || '',
            plantilla_formula: parsedFormula,
            requisitos_equipamiento: servicio.requisitos_equipamiento || [],
            activo: servicio.activo !== false
        });
        setShowModal(true);
    };

    // Funciones para manejar requisitos de equipamiento
    const agregarRequisito = () => {
        setFormData({
            ...formData,
            requisitos_equipamiento: [
                ...formData.requisitos_equipamiento,
                { tipo_equipamiento: '', cantidad_minima: 1, obligatorio: true }
            ]
        });
    };

    const eliminarRequisito = (index) => {
        setFormData({
            ...formData,
            requisitos_equipamiento: formData.requisitos_equipamiento.filter((_, i) => i !== index)
        });
    };

    const actualizarRequisito = (index, campo, valor) => {
        const nuevosRequisitos = [...formData.requisitos_equipamiento];
        if (campo === 'cantidad_minima') {
            nuevosRequisitos[index][campo] = parseInt(valor) || 1;
        } else if (campo === 'obligatorio') {
            nuevosRequisitos[index][campo] = valor;
        } else {
            nuevosRequisitos[index][campo] = valor;
        }
        setFormData({ ...formData, requisitos_equipamiento: nuevosRequisitos });
    };

    const handleSave = async (e) => {
        e.preventDefault();
        try {
            const token = localStorage.getItem('access_token');
            const config = { headers: { 'Authorization': `Bearer ${token}` } };
            
            const payload = {
                nombre: formData.nombre,
                descripcion: formData.descripcion,
                precio_base: formData.precio_base,
                duracion_estimada: formData.duracion_estimada || null,
                categoria: formData.categoria ? parseInt(formData.categoria) : null,
                rutina_recomendada: formData.rutina_recomendada ? parseInt(formData.rutina_recomendada) : null,
                impacto_porosidad: formData.impacto_porosidad ? parseInt(formData.impacto_porosidad) : null,
                impacto_estado: formData.impacto_estado ? parseInt(formData.impacto_estado) : null,
                plantilla_formula: formulaToString(formData.plantilla_formula),
                activo: formData.activo
            };

            let servicioId = editingId;

            if (editingId) {
                // ACTUALIZAR SERVICIO
                await axios.patch(`http://127.0.0.1:8000/api/gestion/servicios/${editingId}/`, payload, config);
                
                // Eliminar requisitos anteriores (opcional - no bloquea si falla)
                try {
                    const resRequisitos = await axios.get(`http://127.0.0.1:8000/api/gestion/requisitos-servicio/?servicio_id=${editingId}`, config);
                    
                    // Manejar respuesta con o sin paginación
                    let requisitos = Array.isArray(resRequisitos.data) ? resRequisitos.data : (resRequisitos.data.results || []);
                    
                    if (requisitos.length > 0) {
                        const promesasEliminar = requisitos.map(req =>
                            axios.delete(`http://127.0.0.1:8000/api/gestion/requisitos-servicio/${req.id}/`, config)
                        );
                        await Promise.all(promesasEliminar);
                    }
                } catch (err) {
                    console.warn('Nota: No hay requisitos previos para eliminar');
                }
                
                notify.success('Servicio actualizado correctamente');
            } else {
                // CREAR SERVICIO
                const res = await axios.post('http://127.0.0.1:8000/api/gestion/servicios/', payload, config);
                servicioId = res.data.id;
                notify.success('Servicio creado correctamente');
            }

            // Guardar requisitos de equipamiento (opcional - no bloquea si no hay o falla)
            if (formData.requisitos_equipamiento && Array.isArray(formData.requisitos_equipamiento) && formData.requisitos_equipamiento.length > 0) {
                const requisitosFiltrados = formData.requisitos_equipamiento
                    .filter(req => {
                        // Validar que tenga tipo_equipamiento válido
                        const tipoId = parseInt(req.tipo_equipamiento);
                        return !isNaN(tipoId) && tipoId > 0;
                    })
                    .map(req => ({
                        servicio: servicioId,
                        tipo_equipamiento: parseInt(req.tipo_equipamiento),
                        obligatorio: Boolean(req.obligatorio),
                        cantidad_minima: Math.max(1, parseInt(req.cantidad_minima) || 1)
                    }));
                
                if (requisitosFiltrados.length > 0) {
                    try {
                        const promesasRequisitos = requisitosFiltrados.map(reqPayload =>
                            axios.post('http://127.0.0.1:8000/api/gestion/requisitos-servicio/', reqPayload, config)
                        );
                        await Promise.all(promesasRequisitos);
                        notify.success('Requisitos de equipamiento guardados');
                    } catch (err) {
                        console.warn('Algunos requisitos no se guardaron:', err.response?.data || err.message);
                        // Continuar sin bloquear - el servicio ya se guardó
                    }
                }
            }

            resetForm();
            cargarDatos(); 

        } catch (error) {
            console.error(error);
            notify.error(error.response?.data?.detail || 'No se pudo guardar el servicio');
        }
    };

    const handleDelete = async (servicioId) => {
        const result = await confirmarAccion({ 
            title: "¿Desactivar servicio?",
            text: "Esta acción marcará el servicio como inactivo."
        });
        if (!result.isConfirmed) return;
        
        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/servicios/${servicioId}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success('Servicio desactivado correctamente');
            cargarDatos();
        } catch (error) {
            console.error(error);
            notify.error('Error al desactivar el servicio');
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
            notify.error('Error al cambiar el estado del servicio');
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
                                setShowModal(true);
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

                {/* MODAL PARA CREAR/EDITAR SERVICIO */}
                {showModal && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4 overflow-y-auto">
                        <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full my-8">
                            {/* Header del Modal */}
                            <div className="flex justify-between items-center p-6 border-b" style={{ borderColor: '#D5D1CC' }}>
                                <h3 className="text-2xl font-bold" style={{ color: '#817773' }}>
                                    {editingId ? '✏️ Editar Servicio' : '➕ Crear Nuevo Servicio'}
                                </h3>
                                <button
                                    onClick={() => resetForm()}
                                    className="text-gray-500 hover:text-gray-700 text-2xl font-bold"
                                >
                                    ✕
                                </button>
                            </div>

                            {/* Contenido del Modal */}
                            <div className="p-6 max-h-[70vh] overflow-y-auto">
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

                            {/* Plantilla de Fórmula */}
                            <div className="md:col-span-2">
                                <label className="block text-sm font-bold mb-3" style={{ color: '#817773' }}>Plantilla de Fórmula</label>
                                
                                {/* Rubios */}
                                <div className="mb-4 p-3 border rounded-lg" style={{ backgroundColor: '#FFFBF5', borderColor: '#E3D5CA' }}>
                                    <h4 className="text-sm font-bold mb-2" style={{ color: '#817773' }}>Rubios</h4>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Base:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.rubios.base}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        rubios: { ...formData.plantilla_formula.rubios, base: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 4"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Oxidante Base:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.rubios.oxidante_base}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        rubios: { ...formData.plantilla_formula.rubios, oxidante_base: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 10 vol"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Medios/Puntas:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.rubios.medios}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        rubios: { ...formData.plantilla_formula.rubios, medios: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 9,7 ½ +8.8f ¼"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Oxidante Medios:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.rubios.oxidante_medios}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        rubios: { ...formData.plantilla_formula.rubios, oxidante_medios: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 10 vol"
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Mieles */}
                                <div className="mb-4 p-3 border rounded-lg" style={{ backgroundColor: '#FFFBF5', borderColor: '#E3D5CA' }}>
                                    <h4 className="text-sm font-bold mb-2" style={{ color: '#817773' }}>Mieles</h4>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Base:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.mieles.base}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        mieles: { ...formData.plantilla_formula.mieles, base: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 4"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Oxidante Base:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.mieles.oxidante_base}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        mieles: { ...formData.plantilla_formula.mieles, oxidante_base: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 10 vol"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Medios/Puntas:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.mieles.medios}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        mieles: { ...formData.plantilla_formula.mieles, medios: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 7,8f ½ + 8,7 1/3 + 2cm 0,631"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Oxidante Medios:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.mieles.oxidante_medios}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        mieles: { ...formData.plantilla_formula.mieles, oxidante_medios: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 10 vol"
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Beige Caramelo / Brown */}
                                <div className="p-3 border rounded-lg" style={{ backgroundColor: '#FFFBF5', borderColor: '#E3D5CA' }}>
                                    <h4 className="text-sm font-bold mb-2" style={{ color: '#817773' }}>Beige Caramelo / Brown</h4>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Base:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.beigeCaramelo.base}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        beigeCaramelo: { ...formData.plantilla_formula.beigeCaramelo, base: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 4,3 cm"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Oxidante Base:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.beigeCaramelo.oxidante_base}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        beigeCaramelo: { ...formData.plantilla_formula.beigeCaramelo, oxidante_base: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 10 vol"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Medios/Puntas:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.beigeCaramelo.medios}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        beigeCaramelo: { ...formData.plantilla_formula.beigeCaramelo, medios: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 5.8f ½ + 7,7 ¼ + 2cm 0,631"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-xs font-semibold block mb-1" style={{ color: '#8B8682' }}>Oxidante Medios:</label>
                                            <input 
                                                type="text"
                                                value={formData.plantilla_formula.beigeCaramelo.oxidante_medios}
                                                onChange={e => setFormData({
                                                    ...formData, 
                                                    plantilla_formula: {
                                                        ...formData.plantilla_formula,
                                                        beigeCaramelo: { ...formData.plantilla_formula.beigeCaramelo, oxidante_medios: e.target.value }
                                                    }
                                                })}
                                                className="w-full p-2 border rounded text-xs"
                                                style={{ borderColor: '#D5D1CC' }}
                                                placeholder="Ej: 10 vol"
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Requisitos de Equipamiento */}
                            <div className="md:col-span-2">
                                <div className="p-4 border rounded-lg" style={{ backgroundColor: '#FFFBF5', borderColor: '#E3D5CA' }}>
                                    <div className="flex justify-between items-center mb-3">
                                        <h4 className="text-sm font-bold" style={{ color: '#817773' }}>🔧 Equipamiento Requerido</h4>
                                        <button 
                                            type="button"
                                            onClick={agregarRequisito}
                                            className="text-xs px-3 py-1 rounded font-semibold text-white transition"
                                            style={{ backgroundColor: '#AB9A91' }}
                                            onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                                            onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                                        >
                                            + Agregar
                                        </button>
                                    </div>
                                    
                                    {formData.requisitos_equipamiento.length === 0 ? (
                                        <p className="text-xs text-gray-500 italic">Sin requisitos configurados</p>
                                    ) : (
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-xs">
                                                <thead>
                                                    <tr style={{ backgroundColor: '#E3D5CA' }}>
                                                        <th className="p-2 text-left" style={{ color: '#817773' }}>Equipamiento</th>
                                                        <th className="p-2 text-center" style={{ color: '#817773' }}>Cantidad</th>
                                                        <th className="p-2 text-center" style={{ color: '#817773' }}>Obligatorio</th>
                                                        <th className="p-2 text-center" style={{ color: '#817773' }}>Acción</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {formData.requisitos_equipamiento.map((req, idx) => (
                                                        <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? 'white' : '#F9F7F5', borderBottom: '1px solid #E3D5CA' }}>
                                                            <td className="p-2">
                                                                <select 
                                                                    value={req.tipo_equipamiento || ''}
                                                                    onChange={e => actualizarRequisito(idx, 'tipo_equipamiento', e.target.value)}
                                                                    className="w-full p-1 border rounded text-xs"
                                                                    style={{ borderColor: '#D5D1CC' }}
                                                                >
                                                                    <option value="">-- Seleccionar --</option>
                                                                    {tiposEquipamiento.map(te => (
                                                                        <option key={te.id} value={te.id}>{te.nombre}</option>
                                                                    ))}
                                                                </select>
                                                            </td>
                                                            <td className="p-2">
                                                                <input 
                                                                    type="number" 
                                                                    min="1"
                                                                    value={req.cantidad_minima || 1}
                                                                    onChange={e => actualizarRequisito(idx, 'cantidad_minima', e.target.value)}
                                                                    className="w-full p-1 border rounded text-xs text-center"
                                                                    style={{ borderColor: '#D5D1CC' }}
                                                                />
                                                            </td>
                                                            <td className="p-2 text-center">
                                                                <input 
                                                                    type="checkbox" 
                                                                    checked={req.obligatorio || false}
                                                                    onChange={e => actualizarRequisito(idx, 'obligatorio', e.target.checked)}
                                                                    className="w-4 h-4 cursor-pointer"
                                                                />
                                                            </td>
                                                            <td className="p-2 text-center">
                                                                <button 
                                                                    type="button"
                                                                    onClick={() => eliminarRequisito(idx)}
                                                                    className="text-xs px-2 py-1 rounded font-bold text-white transition"
                                                                    style={{ backgroundColor: '#C73E3E' }}
                                                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#A03030'}
                                                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#C73E3E'}
                                                                >
                                                                    Eliminar
                                                                </button>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
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

                            {/* Footer del Modal */}
                            <div className="p-4 border-t text-right" style={{ borderColor: '#D5D1CC' }}>
                                <button
                                    onClick={() => resetForm()}
                                    className="px-4 py-2 rounded-lg font-bold transition"
                                    style={{ backgroundColor: '#E3D5CA', color: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#D5BDAF'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#E3D5CA'}
                                >
                                    Cerrar
                                </button>
                            </div>
                        </div>
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
                                    {servicio.plantilla_formula && (
                                        <div className="text-xs p-2 rounded mb-2 border-l-2 font-mono whitespace-pre-wrap" style={{ backgroundColor: '#FAFAF8', color: '#5A5451', borderColor: '#AB9A91', lineHeight: '1.4' }}>
                                            {servicio.plantilla_formula}
                                        </div>
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