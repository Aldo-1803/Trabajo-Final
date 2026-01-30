import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const GestionUsuarios = () => {
    const [usuarios, setUsuarios] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    
    // Filtros
    const [filtroRol, setFiltroRol] = useState(''); // '', 'cliente', 'staff'
    const [filtroEstado, setFiltroEstado] = useState(''); // '', 'activos', 'inactivos'
    const [busqueda, setBusqueda] = useState(''); // Búsqueda global
    
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
            
            // Construir parámetros de query
            const params = new URLSearchParams();
            if (filtroRol) params.append('rol', filtroRol);
            if (filtroEstado) {
                // Convertir valores del filtro a booleano
                const isActiveValue = filtroEstado === 'activos' ? 'true' : 'false';
                params.append('is_active', isActiveValue);
            }
            if (busqueda) params.append('search', busqueda);
            
            const queryString = params.toString();
            const url = queryString 
                ? `http://127.0.0.1:8000/api/gestion/admin/usuarios/?${queryString}`
                : 'http://127.0.0.1:8000/api/gestion/admin/usuarios/';
            
            const res = await axios.get(url, {
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
                notify.error("Acceso denegado. Solo administradores.");
                navigate('/');
            }
        } finally {
            setLoading(false);
        }
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        cargarUsuarios();
    }, [filtroRol, filtroEstado, busqueda]);

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
            notify.success("Usuario creado exitosamente.");
            setModalAbierto(false);
            setForm({ email: '', first_name: '', last_name: '', password: '', is_staff: false }); // Reset
            cargarUsuarios();
        } catch (error) {
            const msg = error.response?.data?.email ? "El email ya existe." : "Error al crear usuario.";
            notify.error(`${msg}`);
        }
    };

    // --- ACCIÓN DE DESACTIVAR (SOFT DELETE) ---
    const toggleEstadoUsuario = async (usuario) => {
        const accion = usuario.is_active ? "desactivar temporalmente" : "reactivar";
        const textoSoftDelete = usuario.is_active 
            ? "El usuario no podrá iniciar sesión, pero sus datos se mantienen en el sistema y podrán ser recuperados." 
            : "El usuario volverá a tener acceso a su cuenta.";
        
        const result = await confirmarAccion({
            title: `¿${accion.charAt(0).toUpperCase() + accion.slice(1)} usuario?`,
            text: `${accion.charAt(0).toUpperCase() + accion.slice(1)} a ${usuario.email}\n\n${textoSoftDelete}`,
            confirmButtonText: `Sí, ${accion}`
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            const userId = usuario.id;
            // Usamos PATCH para cambiar solo el is_active
            await axios.patch(`http://127.0.0.1:8000/api/gestion/admin/usuarios/${userId}/`, 
                { is_active: !usuario.is_active },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            cargarUsuarios();
            const mensajeExito = usuario.is_active 
                ? `Usuario ${accion}do. Sus datos se mantienen en el sistema.`
                : `Usuario reactivado correctamente`;
            notify.success(mensajeExito);
        } catch (error) {
            // Aquí capturamos la validación del backend ("No se puede desactivar si tiene turnos...")
            notify.error(`${JSON.stringify(error.response?.data)}`);
        }
    };

    return (
        <div className="min-h-screen p-8" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-7xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">Gestión de Usuarios</h1>
                    <p className="text-gray-500">Administración de Profesionales y Clientes</p>
                </div>
                <div className="flex gap-3">
                    <button 
                        onClick={() => navigate('/admin-dashboard')} 
                        className="px-4 py-2 rounded-lg font-medium transition-all"
                        style={{ color: '#817773', borderColor: '#C1B4A4', border: '1px solid' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                    >
                        ← Volver
                    </button>
                    <button 
                        onClick={() => setModalAbierto(true)}
                        className="text-white px-4 py-2 rounded-lg font-bold shadow-md flex items-center gap-2 transition-all"
                        style={{ backgroundColor: '#817773' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#6B5F5B'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                    >
                        <span>+</span> Nuevo Usuario
                    </button>
                </div>
            </div>

            {/* BARRA DE FILTROS */}
            <div className="mb-6 p-4 rounded-lg" style={{ backgroundColor: 'white', border: '1px solid #E8DCC4' }}>
                <div className="flex flex-col gap-4">
                    {/* Búsqueda */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                            Búsqueda rápida
                        </label>
                        <input 
                            type="text"
                            placeholder="Busca por nombre, apellido o email..."
                            value={busqueda}
                            onChange={(e) => setBusqueda(e.target.value)}
                            className="w-full px-4 py-2 border rounded-lg"
                            style={{ borderColor: '#D5BDAF' }}
                        />
                    </div>

                    {/* Filtros por Rol y Estado */}
                    <div className="flex gap-4">
                        {/* Filtro Rol */}
                        <div className="flex-1">
                            <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                                Rol
                            </label>
                            <select 
                                value={filtroRol}
                                onChange={(e) => setFiltroRol(e.target.value)}
                                className="w-full px-4 py-2 border rounded-lg"
                                style={{ borderColor: '#D5BDAF' }}
                            >
                                <option value="">Todos los roles</option>
                                <option value="cliente"> Clientes</option>
                                <option value="staff"> Personal / Staff</option>
                            </select>
                        </div>

                        {/* Filtro Estado */}
                        <div className="flex-1">
                            <label className="block text-sm font-medium mb-2" style={{ color: '#817773' }}>
                                Estado
                            </label>
                            <select 
                                value={filtroEstado}
                                onChange={(e) => setFiltroEstado(e.target.value)}
                                className="w-full px-4 py-2 border rounded-lg"
                                style={{ borderColor: '#D5BDAF' }}
                            >
                                <option value="">Todos los estados</option>
                                <option value="activos">Activos</option>
                                <option value="inactivos">Inactivos</option>
                            </select>
                        </div>

                        {/* Botón Limpiar Filtros */}
                        <div className="flex items-end">
                            <button 
                                onClick={() => {
                                    setBusqueda('');
                                    setFiltroRol('');
                                    setFiltroEstado('');
                                }}
                                className="px-4 py-2 rounded-lg font-medium transition-all text-white"
                                style={{ backgroundColor: '#C73E3E' }}
                                onMouseEnter={(e) => e.target.style.opacity = '0.8'}
                                onMouseLeave={(e) => e.target.style.opacity = '1'}
                            >
                                Limpiar
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* TABLA */}
            <div className="bg-white shadow-lg rounded-lg overflow-hidden border" style={{ borderColor: '#E8DCC4' }}>
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando usuarios...</div>
                ) : usuarios.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        <p className="text-lg font-medium">No se encontraron usuarios</p>
                        <p className="text-sm mt-2">Intenta cambiar los filtros o búsqueda</p>
                    </div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="border-b" style={{ backgroundColor: '#E8DCC4' }}>
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-800 uppercase">Usuario</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-800 uppercase">Rol</th>
                                <th className="px-6 py-3 text-left text-xs font-bold text-gray-800 uppercase">Estado</th>
                                <th className="px-6 py-3 text-right text-xs font-bold text-gray-800 uppercase">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {usuarios.map((user) => (
                                <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-bold text-gray-900">
                                            {user.first_name} {user.last_name}
                                        </div>
                                        <div className="text-xs text-gray-500">{user.email}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {user.is_staff ? (
                                            <span className="px-3 py-1 text-xs font-bold rounded-full text-white" style={{ backgroundColor: '#C1B4A4' }}>
                                                Profesional
                                            </span>
                                        ) : (
                                            <span className="px-3 py-1 text-xs font-bold rounded-full text-white" style={{ backgroundColor: '#A89484' }}>
                                                Cliente
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {user.is_active ? (
                                            <span className="px-3 py-1 text-xs font-bold rounded-full text-white" style={{ backgroundColor: '#4CAF50' }}>
                                                Activo
                                            </span>
                                        ) : (
                                            <span className="px-3 py-1 text-xs font-bold rounded-full text-white" style={{ backgroundColor: '#DC2626' }}>
                                                Inactivo
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        <button 
                                            onClick={() => toggleEstadoUsuario(user)}
                                            className="font-semibold transition-all"
                                            style={{ color: user.is_active ? '#DC2626' : '#4CAF50' }}
                                            onMouseEnter={(e) => e.target.style.opacity = '0.7'}
                                            onMouseLeave={(e) => e.target.style.opacity = '1'}
                                            title={user.is_active ? 'Desactivar temporalmente (sin eliminar)' : 'Recuperar acceso'}
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
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" style={{ borderTop: '4px solid #817773' }}>
                        <h2 className="text-xl font-bold mb-4" style={{ color: '#817773' }}>Alta de Usuario</h2>
                        
                        <form onSubmit={crearUsuario} className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium" style={{ color: '#817773' }}>Nombre</label>
                                    <input type="text" name="first_name" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.first_name} onChange={handleChange} />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium" style={{ color: '#817773' }}>Apellido</label>
                                    <input type="text" name="last_name" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.last_name} onChange={handleChange} />
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-medium" style={{ color: '#817773' }}>Email</label>
                                <input type="email" name="email" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.email} onChange={handleChange} />
                            </div>

                            <div>
                                <label className="block text-sm font-medium" style={{ color: '#817773' }}>Contraseña Provisoria</label>
                                <input type="password" name="password" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.password} onChange={handleChange} />
                            </div>

                            <div className="flex items-center mt-2">
                                <input 
                                    id="is_staff"
                                    name="is_staff" 
                                    type="checkbox" 
                                    className="h-4 w-4 rounded border-gray-300"
                                    style={{ accentColor: '#817773' }}
                                    checked={form.is_staff}
                                    onChange={handleChange}
                                />
                                <label htmlFor="is_staff" className="ml-2 block text-sm font-bold" style={{ color: '#817773' }}>
                                    ¿Es Profesional / Staff?
                                </label>
                            </div>
                            <p className="text-xs text-gray-500">Si se marca, tendrá acceso al panel de administración.</p>

                            <div className="flex justify-end gap-3 mt-6 border-t pt-4" style={{ borderColor: '#E8DCC4' }}>
                                <button 
                                    type="button" 
                                    onClick={() => setModalAbierto(false)} 
                                    className="px-4 py-2 border rounded-lg font-medium transition-all"
                                    style={{ borderColor: '#C1B4A4', color: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                >
                                    Cancelar
                                </button>
                                <button 
                                    type="submit" 
                                    className="px-4 py-2 text-white rounded-lg font-bold transition-all"
                                    style={{ backgroundColor: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#6B5F5B'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                                >
                                    Crear Usuario
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
            </div>
        </div>
    );
};

export default GestionUsuarios;