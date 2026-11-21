import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const GestionCategorias = () => {
    const [categorias, setCategorias] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false);
    
    const [form, setForm] = useState({
        id: null,
        nombre: '',
        descripcion: '',
        activo: true
    });

    useEffect(() => {
        cargarCategorias();
    }, []);

    const cargarCategorias = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/categorias-productos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setCategorias(res.data);
        } catch (error) {
            console.error("Error al cargar categorías", error);
            notify.error("Error al cargar categorías");
        } finally {
            setLoading(false);
        }
    };

    const handleChange = (e) => {
        const { name, type, checked, value } = e.target;
        setForm({
            ...form,
            [name]: type === 'checkbox' ? checked : value
        });
    };

    const abrirModal = (categoria = null) => {
        if (categoria) {
            setModoEdicion(true);
            setForm(categoria);
        } else {
            setModoEdicion(false);
            setForm({ id: null, nombre: '', descripcion: '', activo: true });
        }
        setModalAbierto(true);
    };

    const cerrarModal = () => {
        setModalAbierto(false);
    };

    const guardarCategoria = async (e) => {
        e.preventDefault();
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };

        if (!form.nombre.trim()) {
            notify.error("El nombre es requerido");
            return;
        }

        try {
            if (modoEdicion) {
                await axios.put(`http://127.0.0.1:8000/api/gestion/categorias-productos/${form.id}/`, form, { headers });
                notify.success("✅ Categoría actualizada correctamente.");
            } else {
                await axios.post('http://127.0.0.1:8000/api/gestion/categorias-productos/', form, { headers });
                notify.success("✅ Categoría creada exitosamente.");
            }
            cerrarModal();
            cargarCategorias();
        } catch (error) {
            const msg = error.response?.data?.detail || error.response?.data?.nombre || "Error al guardar.";
            notify.error(`❌ ${msg}`);
        }
    };

    const eliminarCategoria = async (id, nombre) => {
        const result = await confirmarAccion({
            title: "¿Eliminar categoría?",
            text: `Se eliminará "${nombre}" y sus productos asociados`,
            confirmButtonText: "Sí, eliminar"
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/categorias-productos/${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success("🗑️ Categoría eliminada.");
            cargarCategorias();
        } catch (error) {
            const msg = error.response?.data?.error || "No se pudo eliminar.";
            notify.error(`❌ ${msg}`);
        }
    };

    return (
        <div className="max-w-4xl mx-auto p-6 mt-8 min-h-screen" style={{ backgroundColor: '#F5F5EB' }}>
            {/* HEADER */}
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>📂 Categorías de Productos</h1>
                    <p style={{ color: '#8B8682' }}>Organiza el catálogo en categorías</p>
                </div>
                <button 
                    onClick={() => abrirModal()}
                    className="text-white px-4 py-2 rounded-lg font-bold shadow-md transition"
                    style={{ backgroundColor: '#AB9A91' }}
                    onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                    onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                >
                    + Nueva Categoría
                </button>
            </div>

            {/* TABLA */}
            <div className="shadow-lg rounded-lg overflow-hidden border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
                {loading ? (
                    <div className="p-8 text-center" style={{ color: '#8B8682' }}>Cargando categorías...</div>
                ) : categorias.length === 0 ? (
                    <div className="p-8 text-center" style={{ color: '#ABA89E' }}>No hay categorías registradas.</div>
                ) : (
                    <table className="min-w-full divide-y" style={{ borderColor: '#D5D1CC' }}>
                        <thead style={{ backgroundColor: '#F5F5EB' }}>
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Nombre</th>
                                <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Descripción</th>
                                <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Estado</th>
                                <th className="px-6 py-3 text-right text-xs font-bold uppercase" style={{ color: '#817773' }}>Acciones</th>
                            </tr>
                        </thead>
                        <tbody style={{ borderColor: '#D5D1CC' }} className="divide-y">
                            {categorias.map((cat) => (
                                <tr key={cat.id} style={{ borderColor: '#E3D5CA' }} onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5F5EB'} onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}>
                                    <td className="px-6 py-4">
                                        <p className="font-bold" style={{ color: '#817773' }}>{cat.nombre}</p>
                                    </td>
                                    <td className="px-6 py-4">
                                        <p className="text-sm" style={{ color: '#8B8682' }}>{cat.descripcion || '-'}</p>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {cat.activo ? (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}>
                                                ✅ Activa
                                            </span>
                                        ) : (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full" style={{ backgroundColor: '#FFE8E8', color: '#C73E3E' }}>
                                                ❌ Inactiva
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button 
                                            onClick={() => abrirModal(cat)}
                                            className="font-bold transition mr-4"
                                            style={{ color: '#AB9A91' }}
                                            onMouseEnter={(e) => e.target.style.color = '#817773'}
                                            onMouseLeave={(e) => e.target.style.color = '#AB9A91'}
                                        >
                                            Editar
                                        </button>
                                        <button 
                                            onClick={() => eliminarCategoria(cat.id, cat.nombre)}
                                            className="font-bold transition"
                                            style={{ color: '#C73E3E' }}
                                            onMouseEnter={(e) => e.target.style.color = '#8B3E3E'}
                                            onMouseLeave={(e) => e.target.style.color = '#C73E3E'}
                                        >
                                            Eliminar
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
                    <div className="rounded-xl shadow-2xl max-w-md w-full p-6" style={{ backgroundColor: 'white' }}>
                        <h2 className="text-xl font-bold mb-4" style={{ color: '#817773', borderBottom: '2px solid #E3D5CA', paddingBottom: '0.5rem' }}>
                            {modoEdicion ? '✏️ Editar Categoría' : '✨ Nueva Categoría'}
                        </h2>
                        
                        <form onSubmit={guardarCategoria} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Nombre *</label>
                                <input 
                                    type="text" 
                                    name="nombre" 
                                    required
                                    placeholder="Ej: Shampoos"
                                    className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    value={form.nombre}
                                    onChange={handleChange}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Descripción</label>
                                <textarea 
                                    name="descripcion"
                                    rows="3"
                                    placeholder="Detalles sobre esta categoría..."
                                    className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    value={form.descripcion}
                                    onChange={handleChange}
                                />
                            </div>

                            <div className="flex items-center">
                                <input 
                                    type="checkbox" 
                                    name="activo"
                                    id="activo"
                                    className="h-4 w-4 rounded"
                                    style={{ accentColor: '#817773' }}
                                    checked={form.activo}
                                    onChange={handleChange}
                                />
                                <label htmlFor="activo" className="ml-2 text-sm font-medium" style={{ color: '#817773' }}>
                                    Categoría activa
                                </label>
                            </div>

                            <div className="flex justify-end gap-3 mt-6 pt-4 border-t" style={{ borderColor: '#D5D1CC' }}>
                                <button 
                                    type="button" 
                                    onClick={cerrarModal}
                                    className="px-4 py-2 border rounded-lg font-medium transition"
                                    style={{ borderColor: '#D5BDAF', color: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                >
                                    Cancelar
                                </button>
                                <button 
                                    type="submit" 
                                    className="px-4 py-2 text-white rounded-lg font-bold transition"
                                    style={{ backgroundColor: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#5A5451'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                                >
                                    {modoEdicion ? 'Guardar Cambios' : 'Crear Categoría'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default GestionCategorias;
