import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Swal from 'sweetalert2';
import { useNavigate } from 'react-router-dom';
import { notify } from '../../utils/notificaciones';
import { ADMIN_ROUTES } from '../../routes/routes';
import { useSession } from '../../context/SessionContext';


const EMPTY_ADMIN_FORM = {
    email: '',
    first_name: '',
    last_name: '',
    password_temporal: '',
    motivo: ''
};

const BUSINESS_ROLE_LABELS = {
    CLIENTE: 'Cliente',
    EMPLEADO: 'Empleado',
    PROFESIONAL: 'Profesional',
    ADMINISTRADOR: 'Administrador'
};

const ROLE_STATE_LABELS = {
    VALID: 'Rol válido',
    NO_ROLE: 'Sin rol',
    MULTIPLE_ROLES: 'Múltiples roles'
};

const BUSINESS_ROLES = [
    'CLIENTE',
    'EMPLEADO',
    'PROFESIONAL',
    'ADMINISTRADOR'
];

const ACCESS_MANAGEMENT_CAPABILITIES = new Set([
    'usuarios.manage_users',
    'usuarios.assign_roles',
    'gestion.manage_personal'
]);

const ACCOUNT_WARNING_MESSAGES = {
    CLIENT_PROFILE_INACTIVE: 'La cuenta se reactivó, pero el perfil Cliente permanece inactivo.',
    PREEXISTING_ACCESS_TOKENS_MAY_REGAIN_VALIDITY: 'Los access tokens emitidos antes de la baja pueden recuperar validez hasta vencer. Los refresh tokens pendientes fueron revocados.',
    INCONSISTENT_BUSINESS_ROLES: 'La cuenta conserva múltiples BusinessRoles y requiere revisión.'
};

const buildRoleChangeWarnings = (summary, targetRole) => {
    if (!summary || !targetRole) return [];

    const warnings = [];
    if (targetRole === 'CLIENTE' && !summary.profiles?.cliente?.exists) {
        warnings.push('El rol Cliente requiere un perfil Cliente existente.');
    }
    if (['EMPLEADO', 'PROFESIONAL'].includes(targetRole)) {
        if (!summary.profiles?.personal?.exists) {
            warnings.push('El rol laboral requiere un perfil Personal vinculado.');
        } else if (!summary.profiles.personal.active) {
            warnings.push('El rol laboral requiere que el perfil Personal esté activo.');
        }
    }
    if (
        summary.business_role === 'ADMINISTRADOR'
        && targetRole !== 'ADMINISTRADOR'
    ) {
        const residualCapabilities = (summary.capabilities || []).filter(
            (capability) => (
                ACCESS_MANAGEMENT_CAPABILITIES.has(capability.code)
                && (capability.origins || []).some((origin) => (
                    ['INDIVIDUAL', 'TECHNICAL_GROUP'].includes(origin.type)
                ))
            )
        );
        if (residualCapabilities.length > 0) {
            warnings.push(
                `La degradación conservaría autoridad residual: ${residualCapabilities.map((item) => item.code).join(', ')}.`
            );
        }
    }
    if (summary.role_state === 'MULTIPLE_ROLES') {
        warnings.push('La cuenta tiene múltiples BusinessRoles y requiere revisión.');
    }
    return warnings;
};

const formatCapabilityOrigin = (origin) => {
    if (origin.type === 'BUSINESS_ROLE') {
        return `Rol ${BUSINESS_ROLE_LABELS[origin.identifier] || origin.identifier}`;
    }
    if (origin.type === 'TECHNICAL_GROUP') {
        return `Grupo técnico ${origin.identifier}`;
    }
    if (origin.type === 'INDIVIDUAL') return 'Permiso individual';
    if (origin.type === 'SUPERUSER') return 'Superusuario';
    return origin.type;
};

const GestionUsuarios = () => {
    const [usuarios, setUsuarios] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modalAbierto, setModalAbierto] = useState(false);
    const [creandoAdministrador, setCreandoAdministrador] = useState(false);
    const [resumenAcceso, setResumenAcceso] = useState(null);
    const [cargandoResumen, setCargandoResumen] = useState(false);
    const [cambioRol, setCambioRol] = useState(null);
    const [cambiandoRol, setCambiandoRol] = useState(false);
    
    // Filtros
    const [filtroRol, setFiltroRol] = useState('');
    const [filtroEstado, setFiltroEstado] = useState(''); // '', 'activos', 'inactivos'
    const [busqueda, setBusqueda] = useState(''); // Búsqueda global
    
    // Estado del Formulario
    const [form, setForm] = useState(EMPTY_ADMIN_FORM);

    const navigate = useNavigate();
    const { hasPermission } = useSession();
    const puedeCambiarRol = (
        hasPermission('usuarios.manage_users')
        && hasPermission('usuarios.assign_roles')
    );
    const puedeVerDashboard = hasPermission('gestion.view_reports');
    const puedeVerClientes = hasPermission('usuarios.view_clients');
    const puedeVerPersonal = (
        hasPermission('gestion.manage_personal')
        || hasPermission('gestion.manage_skills')
    );

    // --- CARGA DE DATOS ---
    const cargarUsuarios = useCallback(async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            
            // Construir parámetros de query
            const params = new URLSearchParams();
            
            // Filtro por estado (is_active)
            if (filtroEstado) {
                const isActiveValue = filtroEstado === 'activos' ? 'true' : 'false';
                params.append('is_active', isActiveValue);
            }
            
            // Búsqueda global
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
    }, [filtroEstado, busqueda, navigate]);

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        cargarUsuarios();
    }, [cargarUsuarios]);

    // --- ACCIONES DEL FORMULARIO ---
    const handleChange = (e) => {
        setForm({ ...form, [e.target.name]: e.target.value });
    };

    const crearAdministrador = async (e) => {
        e.preventDefault();
        setCreandoAdministrador(true);
        try {
            const token = localStorage.getItem('access_token');
            await axios.post('http://127.0.0.1:8000/api/usuarios/admin/administradores/crear/', form, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            notify.success('Administrador creado exitosamente.');
            setModalAbierto(false);
            setForm(EMPTY_ADMIN_FORM);
            await cargarUsuarios();
        } catch (error) {
            const errorCode = error.response?.data?.error?.code;
            const messages = {
                EMAIL_ALREADY_EXISTS: 'Ya existe una cuenta con ese email.',
                INVALID_PASSWORD: 'La contraseña temporal no cumple los requisitos de seguridad.',
                INVALID_REASON: 'El motivo debe tener entre 3 y 500 caracteres.',
                PERMISSION_DENIED: 'No tenés permisos para crear administradores.'
            };
            notify.error(
                messages[errorCode]
                || 'No se pudo crear el administrador. Intentá nuevamente.'
            );
        } finally {
            setCreandoAdministrador(false);
        }
    };

    // --- ACCIONES SEMÁNTICAS DE ESTADO DE CUENTA ---
    const toggleEstadoUsuario = async (usuario) => {
        const desactivar = usuario.is_active;
        const accion = desactivar ? 'desactivar' : 'reactivar';
        const textoAccion = desactivar
            ? 'Se desactivará sólo la cuenta. Los perfiles Cliente y Personal conservarán su estado.'
            : 'Se reactivará sólo la cuenta. Los perfiles Cliente y Personal conservarán su estado.';

        const result = await Swal.fire({
            title: `¿${desactivar ? 'Desactivar' : 'Reactivar'} cuenta?`,
            text: `${usuario.email}. ${textoAccion}`,
            icon: 'warning',
            input: 'textarea',
            inputLabel: 'Motivo',
            inputPlaceholder: `Ingresá el motivo para ${accion} la cuenta`,
            inputAttributes: { maxlength: 500 },
            inputValidator: (value) => {
                const motivo = value?.trim() || '';
                if (motivo.length < 3) {
                    return 'El motivo debe tener al menos 3 caracteres.';
                }
                return null;
            },
            showCancelButton: true,
            confirmButtonColor: '#817773',
            cancelButtonColor: '#D5D1CC',
            confirmButtonText: `Sí, ${accion}`,
            cancelButtonText: 'Cancelar',
            allowOutsideClick: false
        });
        if (!result.isConfirmed) return;

        try {
            const token = localStorage.getItem('access_token');
            const userId = usuario.id;
            const actionPath = desactivar
                ? 'desactivar-cuenta'
                : 'reactivar-cuenta';
            const response = await axios.post(
                `http://127.0.0.1:8000/api/gestion/admin/usuarios/${userId}/${actionPath}/`,
                { motivo: result.value.trim() },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            await cargarUsuarios();
            notify.success(
                desactivar
                    ? 'Cuenta desactivada correctamente.'
                    : 'Cuenta reactivada correctamente.'
            );
            (response.data?.warnings || []).forEach((warning) => {
                notify.info(ACCOUNT_WARNING_MESSAGES[warning] || warning);
            });
            if (response.data?.refresh_tokens_revoked > 0) {
                notify.info(
                    `Refresh tokens revocados: ${response.data.refresh_tokens_revoked}.`
                );
            }
        } catch (error) {
            const errorCode = error.response?.data?.error?.code;
            const errorMessages = {
                LAST_ACTIVE_ADMIN: 'No se puede desactivar al último administrador activo.',
                SELF_DEACTIVATION_NOT_ALLOWED: 'No podés desactivar tu propia cuenta.',
                PROTECTED_SUPERUSER: 'La cuenta técnica protegida no puede gestionarse desde esta pantalla.',
                PERMISSION_DENIED: 'No tenés permisos para gestionar cuentas de usuario.',
                USER_HAS_NO_BUSINESS_ROLE: 'La cuenta no tiene un rol de negocio válido para reactivarse.',
                INCONSISTENT_BUSINESS_ROLES: 'La cuenta tiene roles incompatibles y debe ser revisada.',
                CLIENT_PROFILE_REQUIRED: 'La cuenta requiere un perfil de cliente antes de reactivarse.',
                PERSONAL_PROFILE_REQUIRED: 'La cuenta requiere un perfil de personal antes de reactivarse.',
                PERSONAL_INACTIVE: 'Primero debe reactivarse el perfil de personal.',
                ACCOUNT_REACTIVATION_CONFLICT: 'La cuenta cambió durante la operación. Intentá nuevamente.'
            };
            const fallbackMessage = desactivar
                ? 'No se pudo desactivar la cuenta.'
                : 'No se pudo reactivar la cuenta por un estado incoherente.';
            notify.error(errorMessages[errorCode] || fallbackMessage);
        }
    };

    const consultarResumenAcceso = async (usuario) => {
        setCargandoResumen(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(
                `http://127.0.0.1:8000/api/gestion/admin/usuarios/${usuario.id}/resumen-acceso/`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setResumenAcceso(response.data);
        } catch (error) {
            notify.error(
                error.response?.status === 403
                    ? 'No tenés permisos para consultar capacidades.'
                    : 'No se pudo cargar el resumen de acceso.'
            );
        } finally {
            setCargandoResumen(false);
        }
    };

    const abrirCambioRol = async (usuario) => {
        setCargandoResumen(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.get(
                `http://127.0.0.1:8000/api/gestion/admin/usuarios/${usuario.id}/resumen-acceso/`,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            const currentRole = response.data.business_role;
            const defaultTarget = BUSINESS_ROLES.find(
                (role) => role !== currentRole
            ) || currentRole;
            setCambioRol({
                usuario,
                summary: response.data,
                targetRole: defaultTarget,
                reason: '',
                confirmed: false,
                result: null,
                error: null
            });
        } catch (error) {
            notify.error(
                error.response?.status === 403
                    ? 'No tenés permisos para cambiar roles de negocio.'
                    : 'No se pudo preparar el cambio de BusinessRole.'
            );
        } finally {
            setCargandoResumen(false);
        }
    };

    const enviarCambioRol = async (event) => {
        event.preventDefault();
        if (!cambioRol) return;

        const motivo = cambioRol.reason.trim();
        if (motivo.length < 3) {
            notify.error('El motivo debe tener al menos 3 caracteres.');
            return;
        }
        if (!cambioRol.confirmed) {
            notify.error('Confirmá el cambio de BusinessRole antes de continuar.');
            return;
        }

        setCambiandoRol(true);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.post(
                `http://127.0.0.1:8000/api/gestion/admin/usuarios/${cambioRol.usuario.id}/cambiar-rol-negocio/`,
                {
                    role: cambioRol.targetRole,
                    motivo
                },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            setUsuarios((currentUsers) => currentUsers.map((user) => (
                user.id === cambioRol.usuario.id
                    ? { ...user, business_role: response.data.business_role }
                    : user
            )));
            setCambioRol((current) => ({
                ...current,
                summary: response.data.access_summary,
                targetRole: response.data.business_role,
                result: response.data,
                error: null
            }));
            notify.success('BusinessRole actualizado correctamente.');
        } catch (error) {
            const errorCode = error.response?.data?.error?.code;
            const messages = {
                PERMISSION_DENIED: 'No tenés permisos para cambiar roles de negocio.',
                SELF_ROLE_CHANGE_NOT_ALLOWED: 'No podés cambiar tu propio BusinessRole.',
                PROTECTED_SUPERUSER: 'La cuenta técnica protegida no puede gestionarse desde esta pantalla.',
                INCONSISTENT_BUSINESS_ROLES: 'La cuenta tiene múltiples BusinessRoles y requiere revisión.',
                CLIENT_PROFILE_REQUIRED: 'El rol Cliente requiere un perfil Cliente existente.',
                PERSONAL_PROFILE_REQUIRED: 'El rol laboral requiere un perfil Personal vinculado.',
                PERSONAL_INACTIVE: 'El rol laboral requiere un perfil Personal activo.',
                LAST_ACTIVE_ADMIN: 'No se puede degradar al último administrador activo.',
                RESIDUAL_ADMIN_CAPABILITIES: 'La cuenta conservaría autoridad administrativa residual.'
            };
            const fallback = error.response?.status === 403
                ? messages.PERMISSION_DENIED
                : error.response?.status === 409
                    ? 'El cambio entra en conflicto con el estado actual de la cuenta.'
                    : 'No se pudo cambiar el BusinessRole.';
            const message = messages[errorCode] || fallback;
            setCambioRol((current) => ({ ...current, error: message }));
            notify.error(message);
        } finally {
            setCambiandoRol(false);
        }
    };

    const usuariosVisibles = filtroRol
        ? usuarios.filter((user) => user.business_role === filtroRol)
        : usuarios;
    const advertenciasCambioRol = cambioRol?.result
        ? []
        : buildRoleChangeWarnings(
            cambioRol?.summary,
            cambioRol?.targetRole
        );

    return (
        <div className="min-h-screen p-8" style={{ backgroundColor: '#F5F5EB' }}>
            <div className="max-w-7xl mx-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-800">Gestión de Usuarios</h1>
                    <p className="text-gray-500">Administración de cuentas y accesos</p>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                    {puedeVerDashboard && <button
                        onClick={() => navigate(ADMIN_ROUTES.DASHBOARD)}
                        className="px-4 py-2 rounded-lg font-medium transition-all"
                        style={{ color: '#817773', borderColor: '#C1B4A4', border: '1px solid' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                    >
                        ← Volver
                    </button>}
                    {puedeVerClientes && <button
                        onClick={() => navigate(ADMIN_ROUTES.CLIENTES)}
                        className="px-4 py-2 rounded-lg font-medium border"
                        style={{ borderColor: '#817773', color: '#817773' }}
                    >
                        Nuevo cliente
                    </button>}
                    {puedeVerPersonal && <button
                        onClick={() => navigate(ADMIN_ROUTES.PERSONAL)}
                        className="px-4 py-2 rounded-lg font-medium border"
                        style={{ borderColor: '#817773', color: '#817773' }}
                    >
                        Nuevo Personal
                    </button>}
                    <button 
                        onClick={() => setModalAbierto(true)}
                        className="text-white px-4 py-2 rounded-lg font-bold shadow-md flex items-center gap-2 transition-all"
                        style={{ backgroundColor: '#817773' }}
                        onMouseEnter={(e) => e.target.style.backgroundColor = '#6B5F5B'}
                        onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                    >
                        <span>+</span> Nuevo administrador
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
                                <option value="CLIENTE">Clientes</option>
                                <option value="EMPLEADO">Empleados</option>
                                <option value="PROFESIONAL">Profesionales</option>
                                <option value="ADMINISTRADOR">Administradores</option>
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
                ) : usuariosVisibles.length === 0 ? (
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
                            {usuariosVisibles.map((user) => (
                                <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-bold text-gray-900">
                                            {user.first_name} {user.last_name}
                                        </div>
                                        <div className="text-xs text-gray-500">{user.email}</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="px-3 py-1 text-xs font-bold rounded-full text-white" style={{ backgroundColor: '#A89484' }}>
                                            {BUSINESS_ROLE_LABELS[user.business_role] || 'Sin rol'}
                                        </span>
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
                                        <div className="flex justify-end gap-3">
                                            <button
                                                type="button"
                                                onClick={() => consultarResumenAcceso(user)}
                                                disabled={cargandoResumen}
                                                className="font-semibold transition-all disabled:opacity-50"
                                                style={{ color: '#817773' }}
                                            >
                                                 Ver accesos
                                             </button>
                                            {puedeCambiarRol && (
                                                <button
                                                    type="button"
                                                    onClick={() => abrirCambioRol(user)}
                                                    disabled={cargandoResumen}
                                                    className="font-semibold transition-all disabled:opacity-50"
                                                    style={{ color: '#6B5F5B' }}
                                                    aria-label={`Cambiar rol de ${user.email}`}
                                                >
                                                    Cambiar rol
                                                </button>
                                            )}
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
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {resumenAcceso && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="access-summary-title"
                        className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6"
                        style={{ borderTop: '4px solid #817773' }}
                    >
                        <div className="flex justify-between gap-4 mb-5">
                            <div>
                                <h2 id="access-summary-title" className="text-2xl font-bold text-gray-800">Resumen de acceso</h2>
                                <p className="text-sm text-gray-500">{resumenAcceso.identity.email}</p>
                                <p className="text-xs text-gray-400 mt-1">Consulta de sólo lectura</p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setResumenAcceso(null)}
                                className="text-gray-500 font-bold self-start"
                                aria-label="Cerrar resumen de acceso"
                            >
                                ✕
                            </button>
                        </div>

                        <div className="grid md:grid-cols-3 gap-3 mb-5 text-sm">
                            <section className="border rounded-lg p-3">
                                <h3 className="font-bold text-gray-700">Cuenta</h3>
                                <p>{resumenAcceso.account.is_active ? 'Activa' : 'Inactiva'}</p>
                                {resumenAcceso.account.is_staff && <p>Indicador técnico: staff</p>}
                                {resumenAcceso.account.is_superuser && <p>Indicador técnico: superusuario</p>}
                            </section>
                            <section className="border rounded-lg p-3">
                                <h3 className="font-bold text-gray-700">BusinessRole</h3>
                                <p>{BUSINESS_ROLE_LABELS[resumenAcceso.business_role] || ROLE_STATE_LABELS[resumenAcceso.role_state]}</p>
                                {resumenAcceso.business_roles.length > 1 && (
                                    <p className="text-xs text-gray-500 mt-1">
                                        {resumenAcceso.business_roles.map((role) => BUSINESS_ROLE_LABELS[role] || role).join(', ')}
                                    </p>
                                )}
                            </section>
                            <section className="border rounded-lg p-3">
                                <h3 className="font-bold text-gray-700">Evaluación Django</h3>
                                <p>
                                    {resumenAcceso.technical.permission_evaluation === 'EFFECTIVE'
                                        ? 'Permisos efectivos habilitados'
                                        : 'Asignaciones no efectivas por cuenta inactiva'}
                                </p>
                            </section>
                        </div>

                        <section className="mb-5">
                            <h3 className="font-bold text-gray-800 mb-2">Perfiles vinculados</h3>
                            <div className="grid md:grid-cols-2 gap-3 text-sm">
                                <div className="border rounded-lg p-3">
                                    <strong>Cliente:</strong>{' '}
                                    {resumenAcceso.profiles.cliente.exists
                                        ? `#${resumenAcceso.profiles.cliente.id} · ${resumenAcceso.profiles.cliente.active ? 'Activo' : 'Inactivo'}`
                                        : 'No vinculado'}
                                </div>
                                <div className="border rounded-lg p-3">
                                    <strong>Personal:</strong>{' '}
                                    {resumenAcceso.profiles.personal.exists
                                        ? `#${resumenAcceso.profiles.personal.id} · ${resumenAcceso.profiles.personal.active ? 'Activo' : 'Inactivo'} · Función ${resumenAcceso.profiles.personal.job_role}`
                                        : 'No vinculado'}
                                </div>
                            </div>
                        </section>

                        <section className="mb-5">
                            <h3 className="font-bold text-gray-800 mb-2">Capacidades</h3>
                            {resumenAcceso.capabilities.length === 0 ? (
                                <p className="text-sm text-gray-500">Sin capacidades asignadas ni efectivas.</p>
                            ) : (
                                <div className="space-y-2">
                                    {resumenAcceso.capabilities.map((capability) => (
                                        <div key={capability.code} className="border rounded-lg p-3 text-sm">
                                            <div className="flex flex-wrap justify-between gap-2">
                                                <code className="font-semibold text-gray-800">{capability.code}</code>
                                                <span className={capability.effective ? 'text-green-700 font-bold' : 'text-amber-700 font-bold'}>
                                                    {capability.effective ? 'Efectiva' : 'Asignada, no efectiva'}
                                                </span>
                                            </div>
                                            <p className="text-xs text-gray-500 mt-1">
                                                Origen: {capability.origins.map(formatCapabilityOrigin).join(' · ')}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </section>

                        <section>
                            <h3 className="font-bold text-gray-800 mb-2">Anomalías y advertencias</h3>
                            {resumenAcceso.warnings.length === 0 ? (
                                <p className="text-sm text-green-700">Sin advertencias detectadas.</p>
                            ) : (
                                <ul className="space-y-2">
                                    {resumenAcceso.warnings.map((warning) => (
                                        <li key={warning.code} className="border border-amber-200 bg-amber-50 rounded-lg p-3 text-sm">
                                            <strong>{warning.code}</strong>: {warning.message}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </section>

                        <div className="flex justify-end mt-6">
                            <button
                                type="button"
                                onClick={() => setResumenAcceso(null)}
                                className="px-4 py-2 rounded-lg text-white font-semibold"
                                style={{ backgroundColor: '#817773' }}
                            >
                                Cerrar
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {cambioRol && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="business-role-change-title"
                        className="bg-white rounded-xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6"
                        style={{ borderTop: '4px solid #817773' }}
                    >
                        <h2 id="business-role-change-title" className="text-xl font-bold text-gray-800">
                            Cambiar BusinessRole
                        </h2>
                        <p className="text-sm text-gray-500 mb-4">{cambioRol.usuario.email}</p>

                        {cambioRol.result ? (
                            <div>
                                <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                                    <h3 className="font-bold text-green-800">Rol actualizado</h3>
                                    <p>
                                        {BUSINESS_ROLE_LABELS[cambioRol.result.previous_role] || 'Sin rol'}
                                        {' → '}
                                        {BUSINESS_ROLE_LABELS[cambioRol.result.business_role]}
                                    </p>
                                </div>
                                <div className="flex justify-end mt-5">
                                    <button
                                        type="button"
                                        onClick={() => setCambioRol(null)}
                                        className="px-4 py-2 rounded-lg text-white font-semibold"
                                        style={{ backgroundColor: '#817773' }}
                                    >
                                        Cerrar
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <form onSubmit={enviarCambioRol} className="space-y-4">
                                <div className="rounded-lg border p-3 text-sm">
                                    <strong>Rol actual:</strong>{' '}
                                    {BUSINESS_ROLE_LABELS[cambioRol.summary.business_role]
                                        || ROLE_STATE_LABELS[cambioRol.summary.role_state]}
                                </div>

                                <div>
                                    <label htmlFor="business-role-target" className="block text-sm font-medium text-gray-700">
                                        Rol destino
                                    </label>
                                    <select
                                        id="business-role-target"
                                        value={cambioRol.targetRole}
                                        onChange={(event) => setCambioRol((current) => ({
                                            ...current,
                                            targetRole: event.target.value,
                                            error: null
                                        }))}
                                        className="mt-1 w-full border rounded-lg p-2"
                                    >
                                        {BUSINESS_ROLES.map((role) => (
                                            <option key={role} value={role}>
                                                {BUSINESS_ROLE_LABELS[role]}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div className="grid grid-cols-2 gap-3 text-sm">
                                    <div className="border rounded-lg p-3">
                                        <strong>Cliente:</strong>{' '}
                                        {cambioRol.summary.profiles.cliente.exists
                                            ? `#${cambioRol.summary.profiles.cliente.id}`
                                            : 'No vinculado'}
                                    </div>
                                    <div className="border rounded-lg p-3">
                                        <strong>Personal:</strong>{' '}
                                        {cambioRol.summary.profiles.personal.exists
                                            ? `#${cambioRol.summary.profiles.personal.id} · ${cambioRol.summary.profiles.personal.active ? 'Activo' : 'Inactivo'}`
                                            : 'No vinculado'}
                                    </div>
                                </div>

                                {advertenciasCambioRol.length > 0 && (
                                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                                        <strong>Advertencias</strong>
                                        <ul className="list-disc pl-5 mt-1">
                                            {advertenciasCambioRol.map((warning) => (
                                                <li key={warning}>{warning}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {cambioRol.error && (
                                    <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                                        {cambioRol.error}
                                    </p>
                                )}

                                <div>
                                    <label htmlFor="business-role-reason" className="block text-sm font-medium text-gray-700">
                                        Motivo del cambio
                                    </label>
                                    <textarea
                                        id="business-role-reason"
                                        required
                                        minLength={3}
                                        maxLength={500}
                                        rows={3}
                                        value={cambioRol.reason}
                                        onChange={(event) => setCambioRol((current) => ({
                                            ...current,
                                            reason: event.target.value,
                                            error: null
                                        }))}
                                        className="mt-1 w-full border rounded-lg p-2"
                                    />
                                </div>

                                <label className="flex items-start gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        checked={cambioRol.confirmed}
                                        onChange={(event) => setCambioRol((current) => ({
                                            ...current,
                                            confirmed: event.target.checked
                                        }))}
                                    />
                                    <span>Confirmo el cambio de BusinessRole y la conservación de los perfiles vinculados.</span>
                                </label>

                                <div className="flex justify-end gap-3 border-t pt-4">
                                    <button
                                        type="button"
                                        onClick={() => setCambioRol(null)}
                                        disabled={cambiandoRol}
                                        className="px-4 py-2 border rounded-lg font-medium"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={cambiandoRol}
                                        className="px-4 py-2 rounded-lg text-white font-bold disabled:opacity-50"
                                        style={{ backgroundColor: '#817773' }}
                                    >
                                        {cambiandoRol ? 'Cambiando...' : 'Confirmar cambio'}
                                    </button>
                                </div>
                            </form>
                        )}
                    </div>
                </div>
            )}

            {/* MODAL NUEVO ADMINISTRADOR */}
            {modalAbierto && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" style={{ borderTop: '4px solid #817773' }}>
                        <h2 className="text-xl font-bold mb-2" style={{ color: '#817773' }}>Nuevo administrador</h2>
                        <p className="text-sm text-gray-500 mb-4">
                            Se creará una cuenta administrativa para la SPA, sin acceso a Django Admin.
                        </p>

                        <form onSubmit={crearAdministrador} className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="admin-first-name" className="block text-sm font-medium" style={{ color: '#817773' }}>Nombre</label>
                                    <input id="admin-first-name" type="text" name="first_name" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.first_name} onChange={handleChange} />
                                </div>
                                <div>
                                    <label htmlFor="admin-last-name" className="block text-sm font-medium" style={{ color: '#817773' }}>Apellido</label>
                                    <input id="admin-last-name" type="text" name="last_name" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.last_name} onChange={handleChange} />
                                </div>
                            </div>

                            <div>
                                <label htmlFor="admin-email" className="block text-sm font-medium" style={{ color: '#817773' }}>Email</label>
                                <input id="admin-email" type="email" name="email" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.email} onChange={handleChange} />
                            </div>

                            <div>
                                <label htmlFor="admin-temporary-password" className="block text-sm font-medium" style={{ color: '#817773' }}>Contraseña temporal</label>
                                <input id="admin-temporary-password" type="password" name="password_temporal" required className="mt-1 block w-full border rounded p-2" style={{ borderColor: '#E8DCC4' }} value={form.password_temporal} onChange={handleChange} />
                            </div>

                            <div>
                                <label htmlFor="admin-creation-reason" className="block text-sm font-medium" style={{ color: '#817773' }}>Motivo</label>
                                <textarea
                                    id="admin-creation-reason"
                                    name="motivo"
                                    required
                                    minLength={3}
                                    maxLength={500}
                                    rows={3}
                                    className="mt-1 block w-full border rounded p-2"
                                    style={{ borderColor: '#E8DCC4' }}
                                    value={form.motivo}
                                    onChange={handleChange}
                                />
                            </div>

                            <div className="flex justify-end gap-3 mt-6 border-t pt-4" style={{ borderColor: '#E8DCC4' }}>
                                <button 
                                    type="button" 
                                    onClick={() => {
                                        setModalAbierto(false);
                                        setForm(EMPTY_ADMIN_FORM);
                                    }}
                                    disabled={creandoAdministrador}
                                    className="px-4 py-2 border rounded-lg font-medium transition-all"
                                    style={{ borderColor: '#C1B4A4', color: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                >
                                    Cancelar
                                </button>
                                <button 
                                    type="submit" 
                                    disabled={creandoAdministrador}
                                    className="px-4 py-2 text-white rounded-lg font-bold transition-all"
                                    style={{ backgroundColor: '#817773' }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#6B5F5B'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                                >
                                    {creandoAdministrador ? 'Creando...' : 'Crear administrador'}
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
