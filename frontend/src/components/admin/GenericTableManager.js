import React, { useState, useEffect } from 'react';
import axios from 'axios';

const GenericTableManager = ({ apiUrl, titulo, campos = [] }) => {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false);
    const [form, setForm] = useState({});
    const [mensaje, setMensaje] = useState('');

    // Cargar datos de la API
    const cargarDatos = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get(`http://127.0.0.1:8000${apiUrl}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const datos = Array.isArray(res.data) ? res.data : res.data.results || [];
            setItems(datos);
        } catch (error) {
            console.error(`Error al cargar ${titulo}:`, error);
            setMensaje(`❌ Error al cargar ${titulo}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        cargarDatos();
    }, [apiUrl, cargarDatos]);

    // Manejo del formulario
    const handleChange = (e) => {
        const { name, value, type, checked } = e.target;
        let nuevoValor;
        
        if (type === 'checkbox') {
            nuevoValor = checked; // Booleano puro
        } else if (type === 'number') {
            // Permitir campo vacío durante edición, sino convertir a número
            nuevoValor = value === '' ? '' : (parseFloat(value) || 0);
        } else {
            nuevoValor = value;
        }
        
        setForm({ 
            ...form, 
            [name]: nuevoValor
        });
    };

    // Abrir modal para crear o editar
    const abrirModal = (item = null) => {
        if (item) {
            setModoEdicion(true);
            setForm(item);
        } else {
            setModoEdicion(false);
            // Inicializar con valores por defecto
            const newForm = {};
            campos.forEach(campo => {
                if (campo.tipo === 'boolean') newForm[campo.nombre] = false;
                else if (campo.tipo === 'number') newForm[campo.nombre] = 0;
                else newForm[campo.nombre] = '';
            });
            setForm(newForm);
        }
        setModalAbierto(true);
        setMensaje('');
    };

    // Guardar (crear o actualizar)
    const guardarItem = async (e) => {
        e.preventDefault();
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };

        // Normalizar valores booleanos antes de enviar
        const datosNormalizados = { ...form };
        campos.forEach(campo => {
            if (campo.tipo === 'boolean') {
                datosNormalizados[campo.nombre] = Boolean(datosNormalizados[campo.nombre]);
            }
        });

        try {
            if (modoEdicion) {
                await axios.put(`http://127.0.0.1:8000${apiUrl}${form.id}/`, datosNormalizados, { headers });
                setMensaje(`✅ ${titulo} actualizado`);
            } else {
                await axios.post(`http://127.0.0.1:8000${apiUrl}`, datosNormalizados, { headers });
                setMensaje(`✅ ${titulo} creado`);
            }
            setModalAbierto(false);
            cargarDatos();
        } catch (error) {
            console.error('Error al guardar:', error);
            const errorMsg = error.response?.data?.nombre?.[0] || error.response?.data?.detail || 'No se pudo guardar';
            setMensaje(`❌ Error: ${errorMsg}`);
        }
    };

    // Eliminar
    const eliminarItem = async (id, nombre) => {
        if (!window.confirm(`¿Eliminar "${nombre}"?`)) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000${apiUrl}${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setMensaje('✅ Eliminado correctamente');
            cargarDatos();
        } catch (error) {
            console.error('Error al eliminar:', error);
            setMensaje(`❌ No se pudo eliminar`);
        }
    };

    // Obtener columnas para mostrar en tabla (excluyendo ID)
    const columnasVisibles = campos.filter(c => c.nombre !== 'id');

    return (
        <div className="bg-white shadow-lg rounded-lg p-6">
            {/* ENCABEZADO */}
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-gray-800">{titulo}</h2>
                <button
                    onClick={() => abrirModal()}
                    className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 font-bold"
                >
                    + Nuevo
                </button>
            </div>

            {/* MENSAJE */}
            {mensaje && (
                <div className={`mb-4 p-3 rounded ${mensaje.includes('✅') ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                    {mensaje}
                </div>
            )}

            {/* TABLA */}
            {loading ? (
                <div className="text-center py-8 text-gray-500">Cargando...</div>
            ) : items.length === 0 ? (
                <div className="text-center py-8 text-gray-400">No hay datos</div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-100 border-b">
                            <tr>
                                {columnasVisibles.map((col) => (
                                    <th key={col.nombre} className="px-4 py-2 text-left font-bold text-gray-700">
                                        {col.label || col.nombre}
                                    </th>
                                ))}
                                <th className="px-4 py-2 text-right font-bold text-gray-700">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y">
                            {items.map((item) => (
                                <tr key={item.id} className="hover:bg-gray-50">
                                    {columnasVisibles.map((col) => (
                                        <td key={`${item.id}-${col.nombre}`} className="px-4 py-3 text-gray-700">
                                            {col.tipo === 'boolean' ? (
                                                item[col.nombre] ? '✓' : '✗'
                                            ) : col.tipo === 'number' ? (
                                                item[col.nombre] || '0'
                                            ) : (
                                                item[col.nombre] || '-'
                                            )}
                                        </td>
                                    ))}
                                    <td className="px-4 py-3 text-right space-x-2">
                                        <button
                                            onClick={() => abrirModal(item)}
                                            className="text-blue-600 hover:text-blue-900 font-semibold text-sm"
                                        >
                                            Editar
                                        </button>
                                        <button
                                            onClick={() => eliminarItem(item.id, item.nombre || item.id)}
                                            className="text-red-600 hover:text-red-900 font-semibold text-sm"
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

            {/* MODAL */}
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
                        <h3 className="text-xl font-bold text-gray-800 mb-4">
                            {modoEdicion ? `Editar ${titulo}` : `Crear ${titulo}`}
                        </h3>
                        
                        <form onSubmit={guardarItem} className="space-y-4">
                            {campos.map((campo) => {
                                if (campo.nombre === 'id') return null;
                                
                                return (
                                    <div key={campo.nombre}>
                                        <label className="block text-sm font-medium text-gray-700">
                                            {campo.label || campo.nombre}
                                        </label>
                                        
                                        {campo.tipo === 'textarea' ? (
                                            <textarea
                                                name={campo.nombre}
                                                value={form[campo.nombre] || ''}
                                                onChange={handleChange}
                                                className="mt-1 w-full border border-gray-300 rounded p-2"
                                                rows="3"
                                            />
                                        ) : campo.tipo === 'boolean' ? (
                                            <div className="mt-2 flex items-center gap-3">
                                                <input
                                                    type="checkbox"
                                                    name={campo.nombre}
                                                    checked={form[campo.nombre] === true || form[campo.nombre] === 'true'}
                                                    onChange={handleChange}
                                                    className="w-5 h-5 text-blue-600 cursor-pointer"
                                                />
                                                <label className="text-sm font-medium text-gray-700">
                                                    {form[campo.nombre] === true || form[campo.nombre] === 'true' ? '✓ Activado' : '✗ Desactivado'}
                                                </label>
                                            </div>
                                        ) : campo.tipo === 'number' ? (
                                            <input
                                                type="number"
                                                name={campo.nombre}
                                                value={form[campo.nombre] ?? ''}
                                                onChange={handleChange}
                                                className="mt-1 w-full border border-gray-300 rounded p-2"
                                                step="0.1"
                                            />
                                        ) : (
                                            <input
                                                type="text"
                                                name={campo.nombre}
                                                value={form[campo.nombre] || ''}
                                                onChange={handleChange}
                                                className="mt-1 w-full border border-gray-300 rounded p-2"
                                                required={!campo.optional}
                                            />
                                        )}
                                    </div>
                                );
                            })}

                            <div className="flex gap-3 justify-end mt-6">
                                <button
                                    type="button"
                                    onClick={() => setModalAbierto(false)}
                                    className="px-4 py-2 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50"
                                >
                                    Cancelar
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-bold"
                                >
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

export default GenericTableManager;
