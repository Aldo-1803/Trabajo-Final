import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { confirmarAccion, notify } from '../../utils/notificaciones';

const GestionPersonal = () => {
    const [personal, setPersonal] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false);
    const [mensaje, setMensaje] = useState('');
    
    const [form, setForm] = useState({
        nombre: '',
        apellido: '',
        email: '',
        telefono: '',
        color_calendario: '#E11D48',
        rol: 'asistente',
        activo: true,
        realiza_diagnostico: false,
        realiza_lavado: true,
        realiza_color: false
    });

    const ROL_CHOICES = [
        { value: 'colorista', label: 'Colorista / Principal' },
        { value: 'asistente', label: 'Asistente / Lavado' },
        { value: 'administrador', label: 'Administrador' }
    ];

    useEffect(() => {
        cargarPersonal();
    }, []);

    const cargarPersonal = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get('http://127.0.0.1:8000/api/gestion/personal/', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setPersonal(Array.isArray(res.data) ? res.data : res.data.results || []);
        } catch (error) {
            console.error('Error al cargar personal:', error);
            setMensaje('❌ Error al cargar personal');
        } finally {
            setLoading(false);
        }
    };

    const handleChange = (e) => {
        const { name, value, type, checked } = e.target;
        setForm({
            ...form,
            [name]: type === 'checkbox' ? checked : value
        });
    };

    const abrirModal = (item = null) => {
        if (item) {
            setModoEdicion(true);
            setForm(item);
        } else {
            setModoEdicion(false);
            setForm({
                nombre: '',
                apellido: '',
                email: '',
                telefono: '',
                color_calendario: '#E11D48',
                rol: 'asistente',
                activo: true,
                realiza_diagnostico: false,
                realiza_lavado: true,
                realiza_color: false
            });
        }
        setModalAbierto(true);
        setMensaje('');
    };

    const guardarPersonal = async (e) => {
        e.preventDefault();
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };

        try {
            if (modoEdicion) {
                await axios.put(`http://127.0.0.1:8000/api/gestion/personal/${form.id}/`, form, { headers });
                setMensaje('✅ Personal actualizado');
            } else {
                await axios.post('http://127.0.0.1:8000/api/gestion/personal/', form, { headers });
                setMensaje('✅ Personal creado');
            }
            setModalAbierto(false);
            cargarPersonal();
        } catch (error) {
            console.error('Error al guardar:', error);
            const errorMsg = error.response?.data?.nombre?.[0] || 'No se pudo guardar';
            setMensaje(`❌ Error: ${errorMsg}`);
        }
    };

    const eliminarPersonal = async (id, nombre) => {
        const result = await confirmarAccion({
            title: "¿Eliminar personal?",
            text: `Se eliminará a ${nombre}`,
            confirmButtonText: "Sí, eliminar"
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            await axios.delete(`http://127.0.0.1:8000/api/gestion/personal/${id}/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success('Personal eliminado');
            cargarPersonal();
        } catch (error) {
            console.error('Error al eliminar:', error);
            notify.error('No se pudo eliminar');
        }
    };

    return (
        <div className="min-h-screen bg-gray-100 p-8">
            <div className="max-w-6xl mx-auto">
                {/* ENCABEZADO */}
                <div className="mb-8 flex justify-between items-center">
                    <div>
                        <h1 className="text-4xl font-bold text-gray-800">Gestión de Personal</h1>
                        <p className="text-gray-600 mt-2">Administra el equipo de profesionales del salón</p>
                    </div>
                    <button
                        onClick={() => abrirModal()}
                        className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 font-bold"
                    >
                        + Nuevo Personal
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
                ) : personal.length === 0 ? (
                    <div className="text-center py-8 text-gray-400">No hay personal registrado</div>
                ) : (
                    <div className="bg-white shadow-lg rounded-lg overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-gray-200 border-b">
                                <tr>
                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Nombre</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Email</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Teléfono</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Rol</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-700">Habilidades</th>
                                    <th className="px-4 py-3 text-center font-bold text-gray-700">Activo</th>
                                    <th className="px-4 py-3 text-right font-bold text-gray-700">Acciones</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y">
                                {personal.map((p) => (
                                    <tr key={p.id} className="hover:bg-gray-50">
                                        <td className="px-4 py-3 font-semibold text-gray-800">
                                            {p.nombre} {p.apellido}
                                        </td>
                                        <td className="px-4 py-3 text-gray-600">{p.email || '-'}</td>
                                        <td className="px-4 py-3 text-gray-600">{p.telefono || '-'}</td>
                                        <td className="px-4 py-3">
                                            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
                                                {ROL_CHOICES.find(r => r.value === p.rol)?.label}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-600">
                                            <div className="flex gap-2">
                                                {p.realiza_diagnostico && <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded text-xs">Diagnóstico</span>}
                                                {p.realiza_lavado && <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">Lavado</span>}
                                                {p.realiza_color && <span className="bg-pink-100 text-pink-800 px-2 py-1 rounded text-xs">Color</span>}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            {p.activo ? <span className="text-green-600 font-bold">✓</span> : <span className="text-red-600 font-bold">✗</span>}
                                        </td>
                                        <td className="px-4 py-3 text-right space-x-2">
                                            <button
                                                onClick={() => abrirModal(p)}
                                                className="text-blue-600 hover:text-blue-900 font-semibold"
                                            >
                                                Editar
                                            </button>
                                            <button
                                                onClick={() => eliminarPersonal(p.id, `${p.nombre} ${p.apellido}`)}
                                                className="text-red-600 hover:text-red-900 font-semibold"
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
                        <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
                            <h2 className="text-2xl font-bold text-gray-800 mb-6">
                                {modoEdicion ? 'Editar Personal' : 'Crear Personal'}
                            </h2>

                            <form onSubmit={guardarPersonal} className="space-y-5">
                                <div className="grid grid-cols-2 gap-4">
                                    {/* Nombre */}
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Nombre *
                                        </label>
                                        <input
                                            type="text"
                                            name="nombre"
                                            value={form.nombre}
                                            onChange={handleChange}
                                            className="w-full border border-gray-300 rounded p-2"
                                            required
                                        />
                                    </div>

                                    {/* Apellido */}
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Apellido *
                                        </label>
                                        <input
                                            type="text"
                                            name="apellido"
                                            value={form.apellido}
                                            onChange={handleChange}
                                            className="w-full border border-gray-300 rounded p-2"
                                            required
                                        />
                                    </div>

                                    {/* Email */}
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Email
                                        </label>
                                        <input
                                            type="email"
                                            name="email"
                                            value={form.email}
                                            onChange={handleChange}
                                            className="w-full border border-gray-300 rounded p-2"
                                        />
                                    </div>

                                    {/* Teléfono */}
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Teléfono
                                        </label>
                                        <input
                                            type="tel"
                                            name="telefono"
                                            value={form.telefono}
                                            onChange={handleChange}
                                            className="w-full border border-gray-300 rounded p-2"
                                        />
                                    </div>

                                    {/* Rol */}
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Rol *
                                        </label>
                                        <select
                                            name="rol"
                                            value={form.rol}
                                            onChange={handleChange}
                                            className="w-full border border-gray-300 rounded p-2"
                                        >
                                            {ROL_CHOICES.map(rol => (
                                                <option key={rol.value} value={rol.value}>
                                                    {rol.label}
                                                </option>
                                            ))}
                                        </select>
                                    </div>

                                    {/* Color Calendario */}
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Color Calendario
                                        </label>
                                        <div className="flex gap-2">
                                            <input
                                                type="color"
                                                name="color_calendario"
                                                value={form.color_calendario}
                                                onChange={handleChange}
                                                className="w-12 h-10 border border-gray-300 rounded cursor-pointer"
                                            />
                                            <input
                                                type="text"
                                                value={form.color_calendario}
                                                onChange={handleChange}
                                                name="color_calendario"
                                                className="flex-1 border border-gray-300 rounded p-2 text-sm"
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Habilidades Técnicas */}
                                <div className="border-t pt-4">
                                    <h3 className="font-semibold text-gray-700 mb-3">Habilidades Técnicas</h3>
                                    <div className="space-y-3">
                                        <label className="flex items-center gap-3 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                name="realiza_diagnostico"
                                                checked={form.realiza_diagnostico}
                                                onChange={handleChange}
                                                className="w-4 h-4"
                                            />
                                            <span className="text-sm text-gray-700">Realiza Diagnóstico</span>
                                        </label>
                                        <label className="flex items-center gap-3 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                name="realiza_lavado"
                                                checked={form.realiza_lavado}
                                                onChange={handleChange}
                                                className="w-4 h-4"
                                            />
                                            <span className="text-sm text-gray-700">Realiza Lavado</span>
                                        </label>
                                        <label className="flex items-center gap-3 cursor-pointer">
                                            <input
                                                type="checkbox"
                                                name="realiza_color"
                                                checked={form.realiza_color}
                                                onChange={handleChange}
                                                className="w-4 h-4"
                                            />
                                            <span className="text-sm text-gray-700">Realiza Color</span>
                                        </label>
                                    </div>
                                </div>

                                {/* Activo */}
                                <div className="border-t pt-4 flex items-center gap-3">
                                    <input
                                        type="checkbox"
                                        name="activo"
                                        checked={form.activo}
                                        onChange={handleChange}
                                        className="w-5 h-5 cursor-pointer"
                                    />
                                    <label className="text-sm font-medium text-gray-700">
                                        Activo
                                    </label>
                                </div>

                                {/* Botones */}
                                <div className="flex gap-3 justify-end mt-6 border-t pt-4">
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
        </div>
    );
};

export default GestionPersonal;
