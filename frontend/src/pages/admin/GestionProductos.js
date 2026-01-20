import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';

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
            if (error.response?.status === 403) notify.error("No tienes permisos de administrador.");
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
                notify.success("Producto actualizado correctamente.");
            } else {
                // CREAR (POST)
                await axios.post('http://127.0.0.1:8000/api/gestion/productos/', form, { headers });
                notify.success("Producto creado exitosamente.");
            }
            cerrarModal();
            cargarProductos(); // Recargar tabla
        } catch (error) {
            // Mostramos errores de validación del backend (ej: precio negativo)
            const msg = error.response?.data?.precio || error.response?.data?.nombre || "Error al guardar.";
            notify.error(`${msg}`);
        }
    };

    const eliminarProducto = async (id, nombre) => {
        const result = await confirmarAccion({
            title: "¿Eliminar producto?",
            text: `Se eliminará "${nombre}"`,
            confirmButtonText: "Sí, eliminar"
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/productos/${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success("Producto eliminado.");
            cargarProductos();
        } catch (error) {
            // Aquí capturamos la validación de Stock del backend
            const msg = error.response?.data?.error || "No se pudo eliminar.";
            notify.error(`${msg}`);
        }
    };

    // --- RENDERIZADO ---
    return (
        <div className="max-w-6xl mx-auto p-6 mt-8 min-h-screen" style={{ backgroundColor: '#F5EBE0' }}>
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold" style={{ color: '#817773' }}>Inventario de Productos</h1>
                    <p style={{ color: '#8B8682' }}>Gestión del catálogo de ventas</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => navigate('/admin-dashboard')} className="font-bold transition px-3" style={{ color: '#817773' }} onMouseEnter={(e) => e.target.style.color = '#AB9A91'} onMouseLeave={(e) => e.target.style.color = '#817773'}>
                        ← Volver
                    </button>
                    <button 
                        onClick={() => abrirModal()}
                        className="text-white px-4 py-2 rounded-lg font-bold shadow-md transition"
                        style={{ backgroundColor: '#AB9A91' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#817773'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#AB9A91'}
                    >
                        + Nuevo Producto
                    </button>
                </div>
            </div>

            {/* TABLA DE PRODUCTOS */}
            <div className="shadow-lg rounded-lg overflow-hidden border" style={{ backgroundColor: 'white', borderColor: '#D5D1CC' }}>
                {loading ? (
                    <div className="p-8 text-center" style={{ color: '#8B8682' }}>Cargando inventario...</div>
                ) : productos.length === 0 ? (
                    <div className="p-8 text-center" style={{ color: '#ABA89E' }}>No hay productos registrados.</div>
                ) : (
                    <table className="min-w-full divide-y" style={{ borderColor: '#D5D1CC' }}>
                        <thead style={{ backgroundColor: '#F5EBE0' }}>
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Producto</th>
                                <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Precio</th>
                                <th className="px-6 py-3 text-left text-xs font-bold uppercase" style={{ color: '#817773' }}>Stock</th>
                                <th className="px-6 py-3 text-right text-xs font-bold uppercase" style={{ color: '#817773' }}>Acciones</th>
                            </tr>
                        </thead>
                        <tbody style={{ borderColor: '#D5D1CC' }} className="divide-y">
                            {productos.map((prod) => (
                                <tr key={prod.id} style={{ borderColor: '#E3D5CA' }} onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#F5EBE0'} onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'white'}>
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-bold" style={{ color: '#817773' }}>{prod.nombre}</div>
                                        <div className="text-xs truncate max-w-xs" style={{ color: '#8B8682' }}>{prod.descripcion}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="text-sm font-semibold" style={{ color: '#2E7D2E' }}>
                                            ${parseFloat(prod.precio).toLocaleString()}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {prod.stock > 5 ? (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full" style={{ backgroundColor: '#E8F5E8', color: '#2E7D2E' }}>
                                                {prod.stock} u.
                                            </span>
                                        ) : prod.stock > 0 ? (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full animate-pulse" style={{ backgroundColor: '#F5F1E8', color: '#8B7500' }}>
                                                Bajo: {prod.stock} u.
                                            </span>
                                        ) : (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full" style={{ backgroundColor: '#FFE8E8', color: '#C73E3E' }}>
                                                Sin Stock
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button 
                                            onClick={() => abrirModal(prod)}
                                            className="font-bold transition mr-4"
                                            style={{ color: '#AB9A91' }}
                                            onMouseEnter={(e) => e.target.style.color = '#817773'}
                                            onMouseLeave={(e) => e.target.style.color = '#AB9A91'}
                                        >
                                            Editar
                                        </button>
                                        <button 
                                            onClick={() => eliminarProducto(prod.id, prod.nombre)}
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

            {/* MODAL CREAR / EDITAR */}
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in-up" style={{ backgroundColor: 'white' }}>
                        <h2 className="text-xl font-bold mb-4" style={{ color: '#817773', borderBottom: '2px solid #E3D5CA', paddingBottom: '0.5rem' }}>
                            {modoEdicion ? '✏️ Editar Producto' : '✨ Nuevo Producto'}
                        </h2>
                        
                        <form onSubmit={guardarProducto} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Nombre</label>
                                <input 
                                    type="text" 
                                    name="nombre" 
                                    required
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
                                    rows="2"
                                    className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                    style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                    value={form.descripcion}
                                    onChange={handleChange}
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Precio ($)</label>
                                    <input 
                                        type="number" 
                                        name="precio" 
                                        step="0.01"
                                        required
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.precio}
                                        onChange={handleChange}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium mb-1" style={{ color: '#817773' }}>Stock Inicial</label>
                                    <input 
                                        type="number" 
                                        name="stock" 
                                        required
                                        className="mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-2 outline-none"
                                        style={{ borderColor: '#D5D1CC', '--tw-ring-color': '#AB9A91' }}
                                        value={form.stock}
                                        onChange={handleChange}
                                    />
                                </div>
                            </div>

                            <div className="flex justify-end gap-3 mt-6">
                                <button 
                                    type="button" 
                                    onClick={cerrarModal}
                                    className="px-4 py-2 border rounded-lg font-medium transition"
                                    style={{ borderColor: '#D5BDAF', color: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5EBE0'}
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