import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { notify } from '../../utils/notificaciones';

const GestionPersonal = () => {
    const [personal, setPersonal] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [modoEdicion, setModoEdicion] = useState(false);
    const [mensaje, setMensaje] = useState('');
    const [personalAcceso, setPersonalAcceso] = useState(null);
    const [modalCrearAcceso, setModalCrearAcceso] = useState(false);
    const [creandoAcceso, setCreandoAcceso] = useState(false);
    const [formAcceso, setFormAcceso] = useState({
        email: '',
        password_temporal: '',
        role: 'EMPLEADO',
        motivo: ''
    });
    const [modalVincular, setModalVincular] = useState(false);
    const [usuariosElegibles, setUsuariosElegibles] = useState([]);
    const [cargandoUsuarios, setCargandoUsuarios] = useState(false);
    const [vinculandoUsuario, setVinculandoUsuario] = useState(false);
    const [busquedaUsuario, setBusquedaUsuario] = useState('');
    const [usuarioSeleccionado, setUsuarioSeleccionado] = useState('');
    const [motivoVinculo, setMotivoVinculo] = useState('');
    const [accionSemantica, setAccionSemantica] = useState(null);
    const [motivoAccion, setMotivoAccion] = useState('');
    const [procesandoAccion, setProcesandoAccion] = useState(false);
    
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

    const ACCESS_ROLE_CHOICES = [
        { value: 'EMPLEADO', label: 'Empleado' },
        { value: 'PROFESIONAL', label: 'Profesional' },
        { value: 'ADMINISTRADOR', label: 'Administrador' }
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

    const ACCIONES_SEMANTICAS = {
        desactivar: {
            titulo: 'Desactivar Personal',
            endpoint: 'desactivar',
            exito: 'Personal desactivado correctamente.'
        },
        reactivar: {
            titulo: 'Reactivar Personal',
            endpoint: 'reactivar',
            exito: 'Personal reactivado correctamente.'
        },
        revocarLaboral: {
            titulo: 'Revocar acceso laboral',
            endpoint: 'revocar-acceso-laboral',
            exito: 'Acceso laboral revocado correctamente.'
        },
        revocarTotal: {
            titulo: 'Revocar acceso total',
            endpoint: 'revocar-acceso-total',
            exito: 'Acceso total revocado correctamente.'
        }
    };

    const abrirAccionSemantica = (tipo, item) => {
        setAccionSemantica({ tipo, personal: item });
        setMotivoAccion('');
    };

    const cerrarAccionSemantica = () => {
        if (procesandoAccion) return;
        setAccionSemantica(null);
        setMotivoAccion('');
    };

    const ejecutarAccionSemantica = async (event) => {
        event.preventDefault();
        if (!accionSemantica) return;

        const config = ACCIONES_SEMANTICAS[accionSemantica.tipo];
        setProcesandoAccion(true);
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                `http://127.0.0.1:8000/api/gestion/personal/${accionSemantica.personal.id}/${config.endpoint}/`,
                { motivo: motivoAccion },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setAccionSemantica(null);
            setMotivoAccion('');
            await cargarPersonal();
            notify.success(config.exito);
        } catch (error) {
            const message = error.response?.data?.error?.message;
            notify.error(message || `No se pudo completar: ${config.titulo.toLowerCase()}.`);
        } finally {
            setProcesandoAccion(false);
        }
    };

    const limpiarFormAcceso = () => {
        setFormAcceso({
            email: '',
            password_temporal: '',
            role: 'EMPLEADO',
            motivo: ''
        });
    };

    const abrirCrearAcceso = (item) => {
        setPersonalAcceso(item);
        limpiarFormAcceso();
        setModalCrearAcceso(true);
    };

    const cerrarCrearAcceso = () => {
        setModalCrearAcceso(false);
        setPersonalAcceso(null);
        limpiarFormAcceso();
    };

    const handleAccesoChange = (event) => {
        const { name, value } = event.target;
        setFormAcceso((current) => ({ ...current, [name]: value }));
    };

    const crearAcceso = async (event) => {
        event.preventDefault();
        if (!personalAcceso) return;
        setCreandoAcceso(true);
        const emailCreado = formAcceso.email;
        try {
            const token = localStorage.getItem('access_token');
            await axios.post(
                `http://127.0.0.1:8000/api/gestion/personal/${personalAcceso.id}/crear-acceso/`,
                formAcceso,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            cerrarCrearAcceso();
            await cargarPersonal();
            notify.success(`Acceso creado correctamente para ${emailCreado}.`);
        } catch (error) {
            const errorCode = error.response?.data?.error?.code;
            const messages = {
                EMAIL_ALREADY_EXISTS: 'Ya existe una cuenta con ese email. Puede usar Vincular cuenta existente.',
                PERSONAL_ALREADY_HAS_ACCESS: 'Este Personal ya tiene acceso al sistema.',
                PERSONAL_INACTIVE: 'Debe reactivar el Personal antes de crear su acceso.',
                INVALID_PASSWORD: 'La contraseña temporal no cumple los requisitos de seguridad.',
                INVALID_ROLE: 'El rol de acceso seleccionado no está permitido.',
                PERMISSION_DENIED: 'No tiene permisos para crear accesos de Personal.'
            };
            notify.error(
                messages[errorCode]
                || 'No se pudo crear el acceso. Revise los datos e intente nuevamente.'
            );
        } finally {
            setCreandoAcceso(false);
        }
    };

    const cargarUsuariosElegibles = async (search = '') => {
        setCargandoUsuarios(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(
                'http://127.0.0.1:8000/api/gestion/admin/usuarios/',
                {
                    headers: { 'Authorization': `Bearer ${token}` },
                    params: search.trim()
                        ? { search: search.trim(), ordering: 'email' }
                        : { ordering: 'email' }
                }
            );
            const users = Array.isArray(response.data)
                ? response.data
                : response.data.results || [];
            const linkedUserIds = new Set(
                personal
                    .filter((item) => item.usuario !== null && item.usuario !== undefined)
                    .map((item) => Number(item.usuario))
            );
            setUsuariosElegibles(
                users.filter((user) => !linkedUserIds.has(Number(user.id)))
            );
        } catch (error) {
            notify.error(
                error.response?.status === 403
                    ? 'No tiene permisos para consultar las cuentas existentes.'
                    : 'No se pudieron cargar las cuentas existentes.'
            );
            setUsuariosElegibles([]);
        } finally {
            setCargandoUsuarios(false);
        }
    };

    const abrirVincularUsuario = (item) => {
        setPersonalAcceso(item);
        setBusquedaUsuario('');
        setUsuarioSeleccionado('');
        setMotivoVinculo('');
        setModalVincular(true);
        cargarUsuariosElegibles();
    };

    const cerrarVincularUsuario = () => {
        setModalVincular(false);
        setPersonalAcceso(null);
        setUsuariosElegibles([]);
        setBusquedaUsuario('');
        setUsuarioSeleccionado('');
        setMotivoVinculo('');
    };

    const buscarUsuarios = (event) => {
        event.preventDefault();
        setUsuarioSeleccionado('');
        cargarUsuariosElegibles(busquedaUsuario);
    };

    const vincularUsuario = async (event) => {
        event.preventDefault();
        if (!personalAcceso || !usuarioSeleccionado) return;
        setVinculandoUsuario(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.post(
                `http://127.0.0.1:8000/api/gestion/personal/${personalAcceso.id}/vincular-usuario/`,
                {
                    usuario_id: Number(usuarioSeleccionado),
                    motivo: motivoVinculo
                },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            const linkedRole = response.data?.rol;
            cerrarVincularUsuario();
            await cargarPersonal();
            if (linkedRole === 'CLIENTE') {
                notify.info('La cuenta fue vinculada correctamente. El rol de acceso todavía es CLIENTE.');
            } else {
                notify.success('Cuenta vinculada correctamente.');
            }
        } catch (error) {
            const errorCode = error.response?.data?.error?.code;
            const messages = {
                PERSONAL_ALREADY_LINKED: 'Este Personal ya tiene una cuenta vinculada.',
                USER_ALREADY_LINKED_TO_PERSONAL: 'La cuenta seleccionada ya está vinculada a otro Personal.',
                USER_NOT_FOUND: 'La cuenta seleccionada ya no existe.',
                INCONSISTENT_BUSINESS_ROLES: 'La cuenta tiene un estado de roles inconsistente.',
                PROTECTED_SUPERUSER: 'La cuenta protegida no puede vincularse desde esta pantalla.',
                PERMISSION_DENIED: 'No tiene permisos para vincular cuentas de Personal.'
            };
            notify.error(
                messages[errorCode]
                || 'No se pudo vincular la cuenta seleccionada.'
            );
        } finally {
            setVinculandoUsuario(false);
        }
    };

    return (
        <div className="min-h-screen p-8" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-6xl mx-auto">
                {/* ENCABEZADO */}
                <div className="mb-8 flex justify-between items-center">
                    <div>
                        <h1 className="text-4xl font-bold text-gray-800">Gestión de Personal</h1>
                        <p className="text-gray-600 mt-2">Administra el equipo de profesionales del salón</p>
                    </div>
                    <button
                        onClick={() => abrirModal()}
                        className="text-white px-6 py-3 rounded-lg font-bold transition-all"
                        style={{ backgroundColor: '#817773' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#6B5F5B'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                    >
                        + Nuevo Personal
                    </button>
                </div>

                {/* MENSAJE */}
                {mensaje && (
                    <div className={`mb-4 p-4 rounded-lg font-medium ${mensaje.includes('✅') ? 'text-green-700' : 'text-red-700'}`} style={{ backgroundColor: mensaje.includes('✅') ? '#D1FAE5' : '#FEE2E2' }}>
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
                            <thead className="border-b" style={{ backgroundColor: '#E8DCC4' }}>
                                <tr>
                                    <th className="px-4 py-3 text-left font-bold text-gray-800">Nombre</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-800">Contacto</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-800">Teléfono</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-800">Función laboral</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-800">Habilidades</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-800">Estado laboral</th>
                                    <th className="px-4 py-3 text-left font-bold text-gray-800">Acceso al sistema</th>
                                    <th className="px-4 py-3 text-right font-bold text-gray-800">Acciones</th>
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
                                            <span className="px-3 py-1 rounded-full text-xs font-semibold text-white" style={{ backgroundColor: '#C1B4A4' }}>
                                                {ROL_CHOICES.find(r => r.value === p.rol)?.label}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-600">
                                            <div className="flex gap-2 flex-wrap">
                                                {p.realiza_diagnostico && <span className="px-2 py-1 rounded text-xs font-medium text-white" style={{ backgroundColor: '#817773' }}>Diagnóstico</span>}
                                                {p.realiza_lavado && <span className="px-2 py-1 rounded text-xs font-medium text-white" style={{ backgroundColor: '#C1B4A4' }}>Lavado</span>}
                                                {p.realiza_color && <span className="px-2 py-1 rounded text-xs font-medium text-white" style={{ backgroundColor: '#A89484' }}>Color</span>}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={p.activo ? 'text-green-700 font-bold' : 'text-red-700 font-bold'}>
                                                Personal: {p.activo ? 'Activo' : 'Inactivo'}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 min-w-[230px]">
                                            {p.usuario !== null && p.usuario !== undefined ? (
                                                <div className="space-y-1 text-xs">
                                                    <div><strong>Acceso al sistema:</strong> Sí</div>
                                                    <div><strong>Usuario vinculado:</strong> Sí</div>
                                                    <div><strong>Email:</strong> {p.usuario_email || '-'}</div>
                                                    <div>
                                                        <strong>Cuenta:</strong>{' '}
                                                        <span className={p.usuario_activo ? 'text-green-700 font-semibold' : 'text-red-700 font-semibold'}>
                                                            {p.usuario_activo ? 'Activa' : 'Inactiva'}
                                                        </span>
                                                    </div>
                                                    <div><strong>Rol:</strong> {p.usuario_business_role || 'Sin rol asignado'}</div>
                                                </div>
                                            ) : (
                                                <div className="space-y-2">
                                                    <div className="text-xs"><strong>Acceso al sistema:</strong> No</div>
                                                    <div className="text-xs"><strong>Usuario vinculado:</strong> No</div>
                                                    <div className="flex flex-wrap gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={() => abrirCrearAcceso(p)}
                                                            className="px-2 py-1 rounded text-xs font-semibold text-white"
                                                            style={{ backgroundColor: '#817773' }}
                                                        >
                                                            Crear acceso
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => abrirVincularUsuario(p)}
                                                            className="px-2 py-1 rounded text-xs font-semibold border"
                                                            style={{ borderColor: '#817773', color: '#817773' }}
                                                        >
                                                            Vincular cuenta existente
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            <div className="flex flex-wrap justify-end gap-2">
                                                <button
                                                    onClick={() => abrirModal(p)}
                                                    className="font-semibold transition-all"
                                                    style={{ color: '#817773' }}
                                                    onMouseEnter={(e) => e.target.style.color = '#6B5F5B'}
                                                    onMouseLeave={(e) => e.target.style.color = '#817773'}
                                                >
                                                    Editar
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => abrirAccionSemantica(p.activo ? 'desactivar' : 'reactivar', p)}
                                                    className="font-semibold transition-all"
                                                    style={{ color: p.activo ? '#B45309' : '#047857' }}
                                                >
                                                    {p.activo ? 'Desactivar' : 'Reactivar'}
                                                </button>
                                                {p.usuario !== null && p.usuario !== undefined && (
                                                    <>
                                                        <button
                                                            type="button"
                                                            onClick={() => abrirAccionSemantica('revocarLaboral', p)}
                                                            className="font-semibold transition-all text-amber-700 hover:text-amber-900"
                                                        >
                                                            Revocar acceso laboral
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => abrirAccionSemantica('revocarTotal', p)}
                                                            className="font-semibold transition-all text-red-700 hover:text-red-900"
                                                        >
                                                            Revocar acceso total
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {modalCrearAcceso && personalAcceso && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                        <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6" style={{ borderTop: '4px solid #817773' }}>
                            <h2 className="text-2xl font-bold text-gray-800 mb-2">Crear acceso</h2>
                            <p className="text-sm text-gray-600 mb-6">
                                {personalAcceso.nombre} {personalAcceso.apellido}
                            </p>
                            <form onSubmit={crearAcceso} className="space-y-4">
                                <div>
                                    <label htmlFor="access-email" className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                                    <input
                                        id="access-email"
                                        type="email"
                                        name="email"
                                        value={formAcceso.email}
                                        onChange={handleAccesoChange}
                                        required
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="access-password" className="block text-sm font-medium text-gray-700 mb-1">Contraseña temporal *</label>
                                    <input
                                        id="access-password"
                                        type="password"
                                        name="password_temporal"
                                        value={formAcceso.password_temporal}
                                        onChange={handleAccesoChange}
                                        required
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="access-role" className="block text-sm font-medium text-gray-700 mb-1">Rol de acceso *</label>
                                    <select
                                        id="access-role"
                                        name="role"
                                        value={formAcceso.role}
                                        onChange={handleAccesoChange}
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    >
                                        {ACCESS_ROLE_CHOICES.map((role) => (
                                            <option key={role.value} value={role.value}>{role.label}</option>
                                        ))}
                                    </select>
                                    <p className="text-xs text-gray-500 mt-1">Este rol es independiente de la función laboral legacy.</p>
                                </div>
                                <div>
                                    <label htmlFor="access-reason" className="block text-sm font-medium text-gray-700 mb-1">Motivo *</label>
                                    <textarea
                                        id="access-reason"
                                        name="motivo"
                                        value={formAcceso.motivo}
                                        onChange={handleAccesoChange}
                                        required
                                        minLength={3}
                                        maxLength={500}
                                        rows={3}
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                                <div className="flex justify-end gap-3 pt-4 border-t">
                                    <button
                                        type="button"
                                        onClick={cerrarCrearAcceso}
                                        disabled={creandoAcceso}
                                        className="px-4 py-2 border rounded-lg font-medium"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={creandoAcceso}
                                        className="px-4 py-2 rounded-lg font-bold text-white disabled:opacity-60"
                                        style={{ backgroundColor: '#817773' }}
                                    >
                                        {creandoAcceso ? 'Creando...' : 'Crear acceso'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {accionSemantica && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                        <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6" style={{ borderTop: '4px solid #817773' }}>
                            <h2 className="text-2xl font-bold text-gray-800 mb-2">
                                {ACCIONES_SEMANTICAS[accionSemantica.tipo].titulo}
                            </h2>
                            <p className="text-sm text-gray-600 mb-5">
                                {accionSemantica.personal.nombre} {accionSemantica.personal.apellido}
                            </p>
                            <form onSubmit={ejecutarAccionSemantica} className="space-y-4">
                                <div>
                                    <label htmlFor="semantic-action-reason" className="block text-sm font-medium text-gray-700 mb-1">
                                        Motivo *
                                    </label>
                                    <textarea
                                        id="semantic-action-reason"
                                        value={motivoAccion}
                                        onChange={(event) => setMotivoAccion(event.target.value)}
                                        required
                                        minLength={3}
                                        maxLength={500}
                                        rows={3}
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                                <div className="flex justify-end gap-3 pt-4 border-t">
                                    <button
                                        type="button"
                                        onClick={cerrarAccionSemantica}
                                        disabled={procesandoAccion}
                                        className="px-4 py-2 border rounded-lg font-medium"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={procesandoAccion}
                                        className="px-4 py-2 rounded-lg font-bold text-white disabled:opacity-60"
                                        style={{ backgroundColor: '#817773' }}
                                    >
                                        {procesandoAccion ? 'Procesando...' : 'Confirmar'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {modalVincular && personalAcceso && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                        <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto" style={{ borderTop: '4px solid #817773' }}>
                            <h2 className="text-2xl font-bold text-gray-800 mb-2">Vincular cuenta existente</h2>
                            <p className="text-sm text-gray-600 mb-5">
                                Seleccione explícitamente la cuenta para {personalAcceso.nombre} {personalAcceso.apellido}.
                            </p>
                            <form onSubmit={buscarUsuarios} className="flex gap-2 mb-4">
                                <label htmlFor="user-search" className="sr-only">Buscar usuario por email o nombre</label>
                                <input
                                    id="user-search"
                                    type="search"
                                    value={busquedaUsuario}
                                    onChange={(event) => setBusquedaUsuario(event.target.value)}
                                    placeholder="Buscar por email, nombre o apellido"
                                    className="flex-1 border border-gray-300 rounded-lg p-2"
                                />
                                <button type="submit" className="px-4 py-2 border rounded-lg font-semibold" style={{ borderColor: '#817773', color: '#817773' }}>
                                    Buscar
                                </button>
                            </form>

                            <form onSubmit={vincularUsuario} className="space-y-4">
                                <fieldset>
                                    <legend className="text-sm font-semibold text-gray-700 mb-2">Cuenta existente *</legend>
                                    <div className="border rounded-lg divide-y max-h-60 overflow-y-auto">
                                        {cargandoUsuarios ? (
                                            <div className="p-4 text-gray-500">Cargando cuentas...</div>
                                        ) : usuariosElegibles.length === 0 ? (
                                            <div className="p-4 text-gray-500">No se encontraron cuentas disponibles.</div>
                                        ) : usuariosElegibles.map((user) => (
                                            <label key={user.id} className="flex items-start gap-3 p-3 cursor-pointer hover:bg-gray-50">
                                                <input
                                                    type="radio"
                                                    name="usuario_id"
                                                    value={user.id}
                                                    checked={String(usuarioSeleccionado) === String(user.id)}
                                                    onChange={(event) => setUsuarioSeleccionado(event.target.value)}
                                                    required
                                                    className="mt-1"
                                                />
                                                <span className="text-sm">
                                                    <span className="block font-semibold text-gray-800">
                                                        {user.first_name || '-'} {user.last_name || ''}
                                                    </span>
                                                    <span className="block text-gray-600">{user.email}</span>
                                                    <span className="block text-xs text-gray-500">
                                                        Rol: {user.business_role || 'Sin rol asignado'} · Cuenta: {user.is_active ? 'Activa' : 'Inactiva'}
                                                    </span>
                                                </span>
                                            </label>
                                        ))}
                                    </div>
                                </fieldset>
                                <p className="text-sm p-3 rounded-lg bg-amber-50 text-amber-800">
                                    Vincular una cuenta no cambia su BusinessRole actual.
                                </p>
                                <div>
                                    <label htmlFor="link-reason" className="block text-sm font-medium text-gray-700 mb-1">Motivo *</label>
                                    <textarea
                                        id="link-reason"
                                        value={motivoVinculo}
                                        onChange={(event) => setMotivoVinculo(event.target.value)}
                                        required
                                        minLength={3}
                                        maxLength={500}
                                        rows={3}
                                        className="w-full border border-gray-300 rounded-lg p-2"
                                    />
                                </div>
                                <div className="flex justify-end gap-3 pt-4 border-t">
                                    <button
                                        type="button"
                                        onClick={cerrarVincularUsuario}
                                        disabled={vinculandoUsuario}
                                        className="px-4 py-2 border rounded-lg font-medium"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={vinculandoUsuario || !usuarioSeleccionado}
                                        className="px-4 py-2 rounded-lg font-bold text-white disabled:opacity-60"
                                        style={{ backgroundColor: '#817773' }}
                                    >
                                        {vinculandoUsuario ? 'Vinculando...' : 'Confirmar vínculo'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {/* MODAL DE EDICIÓN DE PERSONAL */}
                {modalAbierto && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                        <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto" style={{ borderTop: '4px solid #817773' }}>
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
                                <div className="border-t pt-4" style={{ borderColor: '#E8DCC4' }}>
                                    <h3 className="font-semibold mb-3" style={{ color: '#817773' }}>Habilidades Técnicas</h3>
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
                                <div className="border-t pt-4 flex items-center gap-3" style={{ borderColor: '#E8DCC4' }}>
                                    <input
                                        type="checkbox"
                                        name="activo"
                                        checked={form.activo}
                                        onChange={handleChange}
                                        className="w-5 h-5 cursor-pointer"
                                        style={{ accentColor: '#817773' }}
                                    />
                                    <label className="text-sm font-medium" style={{ color: '#817773' }}>
                                        Activo
                                    </label>
                                </div>

                                {/* Botones */}
                                <div className="flex gap-3 justify-end mt-6 border-t pt-4" style={{ borderColor: '#E8DCC4' }}>
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
