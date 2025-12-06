import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionProductos = () => {
    // --- ESTADOS ---
    const [productos, setProductos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false); // false = Crear, true = Editar
    
    // Estado del Formulario
    const [form, setForm] = useState({
        id: null,
        nombre: '',
        descripcion: '',
        precio: '',
        stock: ''
    });

    const navigate = useNavigate();

    // --- CARGA INICIAL ---
    const cargarProductos = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/productos/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setProductos(res.data);
        } catch (error) {
            console.error("Error al cargar productos", error);
            if (error.response?.status === 403) alert("No tienes permisos de administrador.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        cargarProductos();
    }, []);

    // --- MANEJADORES DEL FORMULARIO ---
    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value });
    };

    const abrirModal = (producto = null) => {
        if (producto) {
            // Modo Edición
            setModoEdicion(true);
            setForm(producto);
        } else {
            // Modo Creación
            setModoEdicion(false);
            setForm({ id: null, nombre: '', descripcion: '', precio: '', stock: '' });
        }
        setModalAbierto(true);
    };

    const cerrarModal = () => {
        setModalAbierto(false);
        setForm({ id: null, nombre: '', descripcion: '', precio: '', stock: '' });
    };

    // --- ACCIONES CRUD ---
    const guardarProducto = async (e) => {
        e.preventDefault();
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };

        try {
            if (modoEdicion) {
                // EDITAR (PUT)
                await axios.put(`http://127.0.0.1:8000/api/gestion/productos/${form.id}/`, form, { headers });
                alert("Producto actualizado correctamente.");
            } else {
                // CREAR (POST)
                await axios.post('http://127.0.0.1:8000/api/gestion/productos/', form, { headers });
                alert("Producto creado exitosamente.");
            }
            cerrarModal();
            cargarProductos(); // Recargar tabla
        } catch (error) {
            // Mostramos errores de validación del backend (ej: precio negativo)
            const msg = error.response?.data?.precio || error.response?.data?.nombre || "Error al guardar.";
            alert(`⚠️ Error: ${msg}`);
        }
    };

    const eliminarProducto = async (id, nombre) => {
        if (!window.confirm(`¿Estás segura de eliminar "${nombre}"?`)) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/productos/${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            alert("Producto eliminado.");
            cargarProductos();
        } catch (error) {
            // Aquí capturamos la validación de Stock del backend
            const msg = error.response?.data?.error || "No se pudo eliminar.";
            alert(`⛔ ${msg}`);
        }
    };

    // --- RENDERIZADO ---
    return (
        <div className="max-w-6xl mx-auto p-6 mt-8">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">Inventario de Productos</h1>
                    <p className="text-gray-500">Gestión del catálogo de ventas</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => navigate('/admin-dashboard')} className="text-gray-500 hover:underline px-3">
                        ← Volver
                    </button>
                    <button 
                        onClick={() => abrirModal()}
                        className="bg-rose-500 text-white px-4 py-2 rounded-lg hover:bg-rose-600 font-bold shadow-md"
                    >
                        + Nuevo Producto
                    </button>
                </div>
            </div>

            {/* TABLA DE PRODUCTOS */}
            <div className="bg-white shadow-lg rounded-lg overflow-hidden border border-gray-200">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando inventario...</div>
                ) : productos.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No hay productos registrados.</div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Producto</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Precio</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Stock</th>
                                <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {productos.map((prod) => (
                                <tr key={prod.id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-bold text-gray-900">{prod.nombre}</div>
                                        <div className="text-xs text-gray-500 truncate max-w-xs">{prod.descripcion}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="text-sm font-semibold text-green-700">
                                            ${parseFloat(prod.precio).toLocaleString()}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {prod.stock > 5 ? (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full bg-green-100 text-green-800">
                                                {prod.stock} u.
                                            </span>
                                        ) : prod.stock > 0 ? (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full bg-yellow-100 text-yellow-800 animate-pulse">
                                                Bajo: {prod.stock} u.
                                            </span>
                                        ) : (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full bg-red-100 text-red-800">
                                                Sin Stock
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button 
                                            onClick={() => abrirModal(prod)}
                                            className="text-blue-600 hover:text-blue-900 mr-4 font-bold"
                                        >
                                            Editar
                                        </button>
                                        <button 
                                            onClick={() => eliminarProducto(prod.id, prod.nombre)}
                                            className="text-red-600 hover:text-red-900 font-bold"
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

            {/* MODAL CREAR / EDITAR */}
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in-up">
                        <h2 className="text-xl font-bold text-gray-800 mb-4">
                            {modoEdicion ? '✏️ Editar Producto' : '✨ Nuevo Producto'}
                        </h2>
                        
                        <form onSubmit={guardarProducto} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Nombre</label>
                                <input 
                                    type="text" 
                                    name="nombre" 
                                    required
                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                                    value={form.nombre}
                                    onChange={handleChange}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Descripción</label>
                                <textarea 
                                    name="descripcion" 
                                    rows="2"
                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                                    value={form.descripcion}
                                    onChange={handleChange}
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Precio ($)</label>
                                    <input 
                                        type="number" 
                                        name="precio" 
                                        step="0.01"
                                        required
                                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                                        value={form.precio}
                                        onChange={handleChange}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Stock Inicial</label>
                                    <input 
                                        type="number" 
                                        name="stock" 
                                        required
                                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                                        value={form.stock}
                                        onChange={handleChange}
                                    />
                                </div>
                            </div>

                            <div className="flex justify-end gap-3 mt-6">
                                <button 
                                    type="button" 
                                    onClick={cerrarModal}
                                    className="px-4 py-2 border rounded-lg text-gray-600 hover:bg-gray-100"
                                >
                                    Cancelar
                                </button>
                                <button 
                                    type="submit" 
                                    className="px-4 py-2 bg-rose-600 text-white rounded-lg hover:bg-rose-700 font-bold"
                                >
                                    {modoEdicion ? 'Guardar Cambios' : 'Crear Producto'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default GestionProductos;