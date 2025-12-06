import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const GestionUsuarios = () => {
    const [usuarios, setUsuarios] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [filtroRol, setFiltroRol] = useState('todos'); // 'todos', 'staff', 'cliente'
    
    // Estado del Formulario
    const [form, setForm] = useState({
        email: '',
        first_name: '',
        last_name: '',
        password: '',
        is_staff: false
    });

    const navigate = useNavigate();

    // --- CARGA DE DATOS ---
    const cargarUsuarios = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/admin/usuarios/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            const datosLista = res.data.results ? res.data.results : res.data;
            
            // Validación de seguridad extra: Asegurar que sea array
            if (Array.isArray(datosLista)) {
                setUsuarios(datosLista);
            } else {
                console.error("Formato inesperado:", datosLista);
                setUsuarios([]); 
            }

        } catch (error) {
            console.error("Error cargando usuarios:", error);
            if (error.response?.status === 403) {
                alert("Acceso denegado. Solo administradores.");
                navigate('/');
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        cargarUsuarios();
    }, []);

    // --- ACCIONES DEL FORMULARIO ---
    const handleChange = (e) => {
        const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
        setForm({ ...form, [e.target.name]: value });
    };

    const crearUsuario = async (e) => {
        e.preventDefault();
        try {
            const token = localStorage.getItem('access_token');
            await axios.post('http://127.0.0.1:8000/api/gestion/admin/usuarios/', form, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            alert("Usuario creado exitosamente.");
            setModalAbierto(false);
            setForm({ email: '', first_name: '', last_name: '', password: '', is_staff: false }); // Reset
            cargarUsuarios();
        } catch (error) {
            const msg = error.response?.data?.email ? "El email ya existe." : "Error al crear usuario.";
            alert(`⚠️ ${msg}`);
        }
    };

    // --- ACCIÓN DE DESACTIVAR (SOFT DELETE) ---
    const toggleEstadoUsuario = async (usuario) => {
        const accion = usuario.is_active ? "desactivar" : "reactivar";
        if (!window.confirm(`¿Seguro que deseas ${accion} a ${usuario.email}?`)) return;

        try {
            const token = localStorage.getItem('access_token');
            // Usamos PATCH para cambiar solo el is_active
            await axios.patch(`http://127.0.0.1:8000/api/gestion/admin/usuarios/${usuario.id}/`, 
                { is_active: !usuario.is_active },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            cargarUsuarios();
        } catch (error) {
            // Aquí capturamos la validación del backend ("No se puede desactivar si tiene turnos...")
            alert(`⛔ Error: ${JSON.stringify(error.response?.data)}`);
        }
    };

    // --- FILTRADO VISUAL ---
    const usuariosFiltrados = usuarios.filter(u => {
        if (filtroRol === 'staff') return u.is_staff;
        if (filtroRol === 'cliente') return !u.is_staff;
        return true;
    });

    return (
        <div className="max-w-7xl mx-auto p-6 mt-8">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">Gestión de Usuarios</h1>
                    <p className="text-gray-500">Administración de Profesionales y Clientes</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => navigate('/admin-dashboard')} className="text-gray-500 hover:underline px-3">
                        ← Volver
                    </button>
                    <button 
                        onClick={() => setModalAbierto(true)}
                        className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 font-bold shadow-md flex items-center gap-2"
                    >
                        <span>+</span> Nuevo Usuario
                    </button>
                </div>
            </div>

            {/* BARRA DE FILTROS */}
            <div className="flex gap-4 mb-6 border-b border-gray-200 pb-2">
                <button onClick={() => setFiltroRol('todos')} className={`px-4 py-2 rounded-lg ${filtroRol === 'todos' ? 'bg-gray-200 font-bold' : 'text-gray-500'}`}>Todos</button>
                <button onClick={() => setFiltroRol('staff')} className={`px-4 py-2 rounded-lg ${filtroRol === 'staff' ? 'bg-purple-100 text-purple-700 font-bold' : 'text-gray-500'}`}>Staff / Profesionales</button>
                <button onClick={() => setFiltroRol('cliente')} className={`px-4 py-2 rounded-lg ${filtroRol === 'cliente' ? 'bg-blue-100 text-blue-700 font-bold' : 'text-gray-500'}`}>Clientes</button>
            </div>

            {/* TABLA */}
            <div className="bg-white shadow-lg rounded-lg overflow-hidden border border-gray-200">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando usuarios...</div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Usuario</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Rol</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase">Estado</th>
                                <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {usuariosFiltrados.map((user) => (
                                <tr key={user.id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-bold text-gray-900">
                                            {user.first_name} {user.last_name}
                                        </div>
                                        <div className="text-xs text-gray-500">{user.email}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {user.is_staff ? (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full bg-purple-100 text-purple-800">
                                                Profesional
                                            </span>
                                        ) : (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full bg-blue-100 text-blue-800">
                                                Cliente
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {user.is_active ? (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full bg-green-100 text-green-800">
                                                Activo
                                            </span>
                                        ) : (
                                            <span className="px-2 py-1 text-xs font-bold rounded-full bg-red-100 text-red-800">
                                                Inactivo
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button 
                                            onClick={() => toggleEstadoUsuario(user)}
                                            className={`${user.is_active ? 'text-red-600 hover:text-red-900' : 'text-green-600 hover:text-green-900'} font-bold`}
                                        >
                                            {user.is_active ? 'Desactivar' : 'Reactivar'}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* MODAL NUEVO USUARIO */}
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in-up">
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Alta de Usuario</h2>
                        
                        <form onSubmit={crearUsuario} className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Nombre</label>
                                    <input type="text" name="first_name" required className="mt-1 block w-full border border-gray-300 rounded p-2" value={form.first_name} onChange={handleChange} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700">Apellido</label>
                                    <input type="text" name="last_name" required className="mt-1 block w-full border border-gray-300 rounded p-2" value={form.last_name} onChange={handleChange} />
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Email</label>
                                <input type="email" name="email" required className="mt-1 block w-full border border-gray-300 rounded p-2" value={form.email} onChange={handleChange} />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Contraseña Provisoria</label>
                                <input type="password" name="password" required className="mt-1 block w-full border border-gray-300 rounded p-2" value={form.password} onChange={handleChange} />
                            </div>

                            <div className="flex items-center mt-2">
                                <input 
                                    id="is_staff"
                                    name="is_staff" 
                                    type="checkbox" 
                                    className="h-4 w-4 text-purple-600 focus:ring-purple-500 border-gray-300 rounded"
                                    checked={form.is_staff}
                                    onChange={handleChange}
                                />
                                <label htmlFor="is_staff" className="ml-2 block text-sm text-gray-900 font-bold">
                                    ¿Es Profesional / Staff?
                                </label>
                            </div>
                            <p className="text-xs text-gray-500">Si se marca, tendrá acceso al panel de administración.</p>

                            <div className="flex justify-end gap-3 mt-6">
                                <button type="button" onClick={() => setModalAbierto(false)} className="px-4 py-2 border rounded-lg text-gray-600 hover:bg-gray-100">
                                    Cancelar
                                </button>
                                <button type="submit" className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-bold">
                                    Crear Usuario
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default GestionUsuarios;