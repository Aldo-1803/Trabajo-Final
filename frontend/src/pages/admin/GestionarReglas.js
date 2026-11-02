import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionarReglas = () => {
    const [reglas, setReglas] = useState([]);
    
    // Catálogos para los dropdowns
    const [tipos, setTipos] = useState([]);
    const [grosores, setGrosores] = useState([]);
    const [porosidades, setPorosidades] = useState([]);
    const [cueros, setCueros] = useState([]);
    const [estados, setEstados] = useState([]);
    const [rutinas, setRutinas] = useState([]);
    const [servicios, setServicios] = useState([]);
    const [configDiag, setConfigDiag] = useState(null);
    const [configForm, setConfigForm] = useState({
        umbral_critico: 2,
        umbral_alerta: 6,
        mensaje_critico: '',
        mensaje_alerta: '',
        mensaje_saludable: '',
        rutina_critico: '',
        rutina_alerta: '',
        rutina_saludable: '',
        servicio_critico: '',
        servicio_alerta: '',
        servicio_saludable: ''
    });

    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState(null);

    // Formulario
    const [formData, setFormData] = useState({
        prioridad: 10,
        tipo_cabello: '',
        grosor_cabello: '',
        porosidad_cabello: '',
        cuero_cabelludo: '',
        estado_general: '',
        rutina_sugerida: '',
        servicio_sugerido: '',
        mensaje_resultado: '',
        accion_resultado: ''
    });

    // eslint-disable-next-line no-unused-vars
    const navigate = useNavigate();

    useEffect(() => {
        cargarDatos();
    }, []);

    const cargarDatos = async () => {
        try {
            const token = localStorage.getItem('access_token');
            const config = { headers: { 'Authorization': `Bearer ${token}` } };

            const results = await Promise.allSettled([
                axios.get('http://127.0.0.1:8000/api/gestion/reglas-diagnostico/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/tipos-cabello/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/grosores-cabello/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/porosidades-cabello/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/cueros-cabelludos/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/estados-generales/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/rutinas/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/servicios/', config),
                axios.get('http://127.0.0.1:8000/api/gestion/configuracion-diagnostico/', config)
            ]);

            // Función auxiliar para arrays seguros
            const getSafeArray = (res) => Array.isArray(res.data) ? res.data : (res.data.results || []);

            const getData = (idx) => (results[idx].status === 'fulfilled' ? results[idx].value : null);

            const reglasRes = getData(0);
            const tiposRes = getData(1);
            const grosRes = getData(2);
            const poroRes = getData(3);
            const cueroRes = getData(4);
            const estRes = getData(5);
            const rutRes = getData(6);
            const servRes = getData(7);
            const configRes = getData(8);

            if (reglasRes) setReglas(getSafeArray(reglasRes));
            if (tiposRes) setTipos(getSafeArray(tiposRes));
            if (grosRes) setGrosores(getSafeArray(grosRes));
            if (poroRes) setPorosidades(getSafeArray(poroRes));
            if (cueroRes) setCueros(getSafeArray(cueroRes));
            if (estRes) setEstados(getSafeArray(estRes));
            if (rutRes) setRutinas(getSafeArray(rutRes));
            if (servRes) setServicios(getSafeArray(servRes));

            const configArr = configRes ? getSafeArray(configRes) : [];
            const configItem = configArr[0] || null;
            setConfigDiag(configItem);
            if (configItem) {
                setConfigForm({
                    umbral_critico: configItem.umbral_critico ?? 2,
                    umbral_alerta: configItem.umbral_alerta ?? 6,
                    mensaje_critico: configItem.mensaje_critico || '',
                    mensaje_alerta: configItem.mensaje_alerta || '',
                    mensaje_saludable: configItem.mensaje_saludable || '',
                    rutina_critico: configItem.rutina_critico || '',
                    rutina_alerta: configItem.rutina_alerta || '',
                    rutina_saludable: configItem.rutina_saludable || '',
                    servicio_critico: configItem.servicio_critico || '',
                    servicio_alerta: configItem.servicio_alerta || '',
                    servicio_saludable: configItem.servicio_saludable || ''
                });
            }
            
            setLoading(false);
        } catch (error) {
            console.error("Error cargando datos", error);
            alert("Error de conexión al cargar las reglas.");
            setLoading(false);
        }
    };

    const handleSave = async (e) => {
        e.preventDefault();
        try {
            const token = localStorage.getItem('access_token');
            
            // Convertimos strings vacíos a null para el backend
            const payload = {};
            Object.keys(formData).forEach(key => {
                payload[key] = formData[key] === '' ? null : formData[key];
            });

            if (editingId) {
                await axios.put(`http://127.0.0.1:8000/api/gestion/reglas-diagnostico/${editingId}/`, payload, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
            } else {
                await axios.post('http://127.0.0.1:8000/api/gestion/reglas-diagnostico/', payload, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
            }

            setShowForm(false);
            setEditingId(null);
            resetForm();
            cargarDatos();
            alert("Regla guardada con éxito.");

        } catch (error) {
            console.error(error);
            alert("Error al guardar la regla.");
        }
    };

    const handleSaveConfig = async (e) => {
        e.preventDefault();
        try {
            const token = localStorage.getItem('access_token');
            const payload = { ...configForm };
            Object.keys(payload).forEach(key => {
                if (payload[key] === '') payload[key] = null;
            });

            if (configDiag && configDiag.id) {
                await axios.put(
                    `http://127.0.0.1:8000/api/gestion/configuracion-diagnostico/${configDiag.id}/`,
                    payload,
                    { headers: { 'Authorization': `Bearer ${token}` } }
                );
            }

            cargarDatos();
            alert('Configuración de diagnóstico guardada.');
        } catch (error) {
            console.error(error);
            alert('Error al guardar la configuración del diagnóstico.');
        }
    };

    const handleEdit = (regla) => {
        setEditingId(regla.id);
        setFormData({
            prioridad: regla.prioridad,
            tipo_cabello: regla.tipo_cabello || '',
            grosor_cabello: regla.grosor_cabello || '',
            porosidad_cabello: regla.porosidad_cabello || '',
            cuero_cabelludo: regla.cuero_cabelludo || '',
            estado_general: regla.estado_general || '',
            rutina_sugerida: regla.rutina_sugerida || '',
            servicio_sugerido: regla.servicio_sugerido || '',
            mensaje_resultado: regla.mensaje_resultado,
            accion_resultado: regla.accion_resultado
        });
        setShowForm(true);
    };

    const handleDelete = async (id) => {
        if (!window.confirm("¿Eliminar esta regla?")) return;
        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/reglas-diagnostico/${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            cargarDatos();
        } catch (error) {
            alert("Error al eliminar.");
        }
    };

    const resetForm = () => {
        setFormData({
            prioridad: 10,
            tipo_cabello: '',
            grosor_cabello: '',
            porosidad_cabello: '',
            cuero_cabelludo: '',
            estado_general: '',
            rutina_sugerida: '',
            servicio_sugerido: '',
            mensaje_resultado: '',
            accion_resultado: ''
        });
    };

    if (loading) return <div className="p-10 text-center">Cargando Motor de Reglas...</div>;

    return (
        <div className="p-8 min-h-screen" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-7xl mx-auto">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h1 className="text-3xl font-bold text-gray-800">🧠 Motor de Diagnóstico</h1>
                        <p className="text-gray-500">Configura qué rutina se asigna según el perfil del cliente.</p>
                    </div>
                    {!showForm && (
                        <button 
                            onClick={() => { resetForm(); setShowForm(true); }}
                            className="bg-purple-600 text-white px-6 py-3 rounded-lg font-bold hover:bg-purple-700 shadow-lg"
                        >
                            + Nueva Regla
                        </button>
                    )}
                </div>

                <div className="bg-white p-8 rounded-xl shadow-lg border border-gray-200 mb-8">
                    <h2 className="text-xl font-bold text-gray-800 mb-6 border-b pb-2">Configuración Nivel 2 (Matriz)</h2>
                    <form onSubmit={handleSaveConfig}>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Umbral Crítico (&lt;=)</label>
                                <input
                                    type="number"
                                    className="w-full border p-2 rounded"
                                    value={configForm.umbral_critico}
                                    onChange={e => setConfigForm({ ...configForm, umbral_critico: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Umbral Alerta (&lt;=)</label>
                                <input
                                    type="number"
                                    className="w-full border p-2 rounded"
                                    value={configForm.umbral_alerta}
                                    onChange={e => setConfigForm({ ...configForm, umbral_alerta: e.target.value })}
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Rutina Crítico</label>
                                <select
                                    className="w-full border p-2 rounded"
                                    value={configForm.rutina_critico}
                                    onChange={e => setConfigForm({ ...configForm, rutina_critico: e.target.value })}
                                >
                                    <option value="">-- Sin rutina --</option>
                                    {rutinas.map(r => <option key={r.id} value={r.id}>{r.nombre}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Servicio Crítico</label>
                                <select
                                    className="w-full border p-2 rounded"
                                    value={configForm.servicio_critico}
                                    onChange={e => setConfigForm({ ...configForm, servicio_critico: e.target.value })}
                                >
                                    <option value="">-- Sin servicio --</option>
                                    {servicios.map(s => <option key={s.id} value={s.id}>{s.nombre}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Rutina Alerta</label>
                                <select
                                    className="w-full border p-2 rounded"
                                    value={configForm.rutina_alerta}
                                    onChange={e => setConfigForm({ ...configForm, rutina_alerta: e.target.value })}
                                >
                                    <option value="">-- Sin rutina --</option>
                                    {rutinas.map(r => <option key={r.id} value={r.id}>{r.nombre}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Servicio Alerta</label>
                                <select
                                    className="w-full border p-2 rounded"
                                    value={configForm.servicio_alerta}
                                    onChange={e => setConfigForm({ ...configForm, servicio_alerta: e.target.value })}
                                >
                                    <option value="">-- Sin servicio --</option>
                                    {servicios.map(s => <option key={s.id} value={s.id}>{s.nombre}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Rutina Saludable</label>
                                <select
                                    className="w-full border p-2 rounded"
                                    value={configForm.rutina_saludable}
                                    onChange={e => setConfigForm({ ...configForm, rutina_saludable: e.target.value })}
                                >
                                    <option value="">-- Sin rutina --</option>
                                    {rutinas.map(r => <option key={r.id} value={r.id}>{r.nombre}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-600 mb-1">Servicio Saludable</label>
                                <select
                                    className="w-full border p-2 rounded"
                                    value={configForm.servicio_saludable}
                                    onChange={e => setConfigForm({ ...configForm, servicio_saludable: e.target.value })}
                                >
                                    <option value="">-- Sin servicio --</option>
                                    {servicios.map(s => <option key={s.id} value={s.id}>{s.nombre}</option>)}
                                </select>
                            </div>
                        </div>

                        <div className="mt-4">
                            <label className="block text-xs font-bold text-gray-600 mb-1">Mensaje Crítico</label>
                            <textarea
                                className="w-full border p-2 rounded h-20"
                                value={configForm.mensaje_critico}
                                onChange={e => setConfigForm({ ...configForm, mensaje_critico: e.target.value })}
                                placeholder="Usa {score} y {servicio} si quieres."
                            />
                        </div>
                        <div className="mt-2">
                            <label className="block text-xs font-bold text-gray-600 mb-1">Mensaje Alerta</label>
                            <textarea
                                className="w-full border p-2 rounded h-20"
                                value={configForm.mensaje_alerta}
                                onChange={e => setConfigForm({ ...configForm, mensaje_alerta: e.target.value })}
                                placeholder="Usa {score} y {servicio} si quieres."
                            />
                        </div>
                        <div className="mt-2">
                            <label className="block text-xs font-bold text-gray-600 mb-1">Mensaje Saludable</label>
                            <textarea
                                className="w-full border p-2 rounded h-20"
                                value={configForm.mensaje_saludable}
                                onChange={e => setConfigForm({ ...configForm, mensaje_saludable: e.target.value })}
                                placeholder="Usa {score} y {servicio} si quieres."
                            />
                        </div>

                        <div className="flex justify-end gap-3 mt-4">
                            <button type="submit" className="px-6 py-2 bg-purple-700 text-white rounded font-bold shadow hover:bg-purple-800">Guardar Configuración</button>
                        </div>
                    </form>
                </div>

                {showForm ? (
                    <div className="bg-white p-8 rounded-xl shadow-lg border border-gray-200 mb-8 animate-fade-in-down">
                        <h2 className="text-xl font-bold text-gray-800 mb-6 border-b pb-2">
                            {editingId ? 'Editar Regla' : 'Definir Nueva Regla'}
                        </h2>
                        
                        <form onSubmit={handleSave}>
                            {/* SECCIÓN 1: CONDICIONES (INPUTS) */}
                            <div className="mb-6">
                                <h3 className="text-sm font-bold text-gray-500 uppercase mb-3">Si el cliente tiene... (Deja en blanco para "Cualquiera")</h3>
                                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                                    <select className="border p-2 rounded" value={formData.tipo_cabello} onChange={e => setFormData({...formData, tipo_cabello: e.target.value})}>
                                        <option value="">-- Cualquier Tipo --</option>
                                        {tipos.map(i => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                                    </select>
                                    <select className="border p-2 rounded" value={formData.grosor_cabello} onChange={e => setFormData({...formData, grosor_cabello: e.target.value})}>
                                        <option value="">-- Cualquier Grosor --</option>
                                        {grosores.map(i => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                                    </select>
                                    <select className="border p-2 rounded" value={formData.porosidad_cabello} onChange={e => setFormData({...formData, porosidad_cabello: e.target.value})}>
                                        <option value="">-- Cualquier Porosidad --</option>
                                        {porosidades.map(i => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                                    </select>
                                    <select className="border p-2 rounded bg-yellow-50" value={formData.cuero_cabelludo} onChange={e => setFormData({...formData, cuero_cabelludo: e.target.value})}>
                                        <option value="">-- Cualquier Cuero C. --</option>
                                        {cueros.map(i => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                                    </select>
                                    <select className="border p-2 rounded bg-yellow-50" value={formData.estado_general} onChange={e => setFormData({...formData, estado_general: e.target.value})}>
                                        <option value="">-- Cualquier Estado --</option>
                                        {estados.map(i => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                                    </select>
                                </div>
                            </div>

                            {/* SECCIÓN 2: RESULTADOS (OUTPUTS) */}
                            <div className="mb-6 bg-purple-50 p-6 rounded-lg border border-purple-100">
                                <h3 className="text-sm font-bold text-purple-700 uppercase mb-3">Entonces el sistema debe...</h3>
                                
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div>
                                        <label className="block text-xs font-bold text-gray-600 mb-1">Asignar esta Rutina</label>
                                        <select 
                                            className="w-full border-2 border-purple-300 p-2 rounded bg-white font-bold text-gray-700"
                                            value={formData.rutina_sugerida} 
                                            onChange={e => setFormData({...formData, rutina_sugerida: e.target.value})}
                                        >
                                            <option value="">-- Seleccionar Rutina --</option>
                                            {rutinas.map(r => <option key={r.id} value={r.id}>{r.nombre}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold text-gray-600 mb-1">Recomendar este Servicio</label>
                                        <select 
                                            className="w-full border-2 border-purple-300 p-2 rounded bg-white font-bold text-gray-700"
                                            value={formData.servicio_sugerido} 
                                            onChange={e => setFormData({...formData, servicio_sugerido: e.target.value})}
                                        >
                                            <option value="">-- Seleccionar Servicio --</option>
                                            {servicios.map(s => <option key={s.id} value={s.id}>{s.nombre}</option>)}
                                        </select>
                                    </div>
                                </div>
                                
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
                                    <div>
                                        <label className="block text-xs font-bold text-gray-600 mb-1">Prioridad de Regla</label>
                                        <input 
                                            type="number" 
                                            className="w-full border p-2 rounded"
                                            value={formData.prioridad}
                                            onChange={e => setFormData({...formData, prioridad: e.target.value})}
                                            placeholder="Mayor número = Gana conflicto"
                                        />
                                    </div>
                                </div>

                                <div className="mt-4">
                                    <label className="block text-xs font-bold text-gray-600 mb-1">Mensaje de Diagnóstico</label>
                                    <textarea 
                                        className="w-full border p-2 rounded h-20"
                                        value={formData.mensaje_resultado}
                                        onChange={e => setFormData({...formData, mensaje_resultado: e.target.value})}
                                        placeholder="Ej: Detectamos desequilibrio de PH..."
                                        required
                                    />
                                </div>
                                <div className="mt-2">
                                    <label className="block text-xs font-bold text-gray-600 mb-1">Acción Corta</label>
                                    <input 
                                        type="text" 
                                        className="w-full border p-2 rounded"
                                        value={formData.accion_resultado}
                                        onChange={e => setFormData({...formData, accion_resultado: e.target.value})}
                                        placeholder="Ej: Recomendamos Rutina Detox"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="flex justify-end gap-3">
                                <button type="button" onClick={() => { setShowForm(false); resetForm(); }} className="px-6 py-2 bg-gray-300 rounded font-bold">Cancelar</button>
                                <button type="submit" className="px-6 py-2 bg-purple-700 text-white rounded font-bold shadow hover:bg-purple-800">Guardar Regla</button>
                            </div>
                        </form>
                    </div>
                ) : (
                    /* LISTA DE REGLAS */
                    <div className="bg-white rounded-xl shadow overflow-hidden">
                        <table className="w-full text-left">
                            <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
                                <tr>
                                    <th className="p-4">Prioridad</th>
                                    <th className="p-4">Condiciones (Si...)</th>
                                    <th className="p-4">Acción (Entonces...)</th>
                                    <th className="p-4 text-right">Opciones</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {reglas.map(regla => (
                                    <tr key={regla.id} className="hover:bg-gray-50">
                                        <td className="p-4 font-bold text-gray-500 text-center">{regla.prioridad}</td>
                                        <td className="p-4 text-sm">
                                            {regla.cuero_nombre && <span className="bg-yellow-100 text-yellow-800 px-2 py-1 rounded mr-1">Cuero: {regla.cuero_nombre}</span>}
                                            {regla.estado_nombre && <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded mr-1">Estado: {regla.estado_nombre}</span>}
                                            {!regla.cuero_nombre && !regla.estado_nombre && <span className="text-gray-400 italic">Genérica</span>}
                                        </td>
                                        <td className="p-4">
                                            {regla.rutina_nombre ? (
                                                <div className="font-bold text-purple-700">➜ {regla.rutina_nombre}</div>
                                            ) : (
                                                <div className="text-red-400 italic">Sin rutina</div>
                                            )}
                                            <div className="text-xs text-gray-500 mt-1">{regla.accion_resultado}</div>
                                        </td>
                                        <td className="p-4 text-right">
                                            <button onClick={() => handleEdit(regla)} className="text-blue-600 font-bold mr-3 hover:underline">Editar</button>
                                            <button onClick={() => handleDelete(regla.id)} className="text-red-500 font-bold hover:underline">Borrar</button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};

export default GestionarReglas;