import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { confirmarAccion, notify } from '../../utils/notificaciones';
import PagoModal from '../../components/admin/PagoModal';
import RegistroFichaTecnica from './RegistroFichaTecnica';

const GestionTurnos = () => {
    const [turnos, setTurnos] = useState([]);
    const navigate = useNavigate();
    const [filtroEstado, setFiltroEstado] = useState('solicitado'); // Tab activa por defecto
    const [loading, setLoading] = useState(false);
    const [procesandoId, setProcesandoId] = useState(null); // Para bloquear botones individualmente
    
    // Estados para búsqueda y filtros
    const [busqueda, setBusqueda] = useState('');
    const [filtroProfesional, setFiltroProfesional] = useState('');
    const [filtroFecha, setFiltroFecha] = useState('');
    const [profesionales, setProfesionales] = useState([]);
    
    // Estados para modal de reprogramación/cancelación profesional
    const [modalReprogramacionAbierto, setModalReprogramacionAbierto] = useState(false);
    const [turnoSeleccionado, setTurnoSeleccionado] = useState(null);
    const [accionProfesional, setAccionProfesional] = useState(null); // 'REPROGRAMAR' o 'CANCELAR'
    const [nuevaFecha, setNuevaFecha] = useState('');
    const [nuevaHora, setNuevaHora] = useState('');
    const [motivoCancelacion, setMotivoCancelacion] = useState('');

    // Estados para modal de pago
    const [modalPagoAbierto, setModalPagoAbierto] = useState(false);
    const [turnoPago, setTurnoPago] = useState(null);
    const [pagoPreset, setPagoPreset] = useState(null);
    const [confirmarTrasPago, setConfirmarTrasPago] = useState(null);

    // Estados para modal de ficha técnica
    const [modalFichaAbierto, setModalFichaAbierto] = useState(false);
    const [turnoFicha, setTurnoFicha] = useState(null);

    // Cargar profesionales al montar
    useEffect(() => {
        cargarProfesionales();
    }, []);

    // Cargar turnos cada vez que cambiamos de pestaña, búsqueda o filtros
    useEffect(() => {
        cargarTurnos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filtroEstado, busqueda, filtroProfesional, filtroFecha]);

    const cargarProfesionales = async () => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.get(
                'http://127.0.0.1:8000/api/gestion/personal/',
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
            setProfesionales(data);
        } catch (error) {
            console.error("Error cargando profesionales", error);
        }
    };

    const cargarTurnos = async () => {
        setLoading(true);
        try {
            // Construir URL con parámetros
            const token = localStorage.getItem('access_token');
            let url = `http://127.0.0.1:8000/api/gestion/turnos/?estado=${filtroEstado}`;
            
            if (busqueda) {
                url += `&search=${encodeURIComponent(busqueda)}`;
            }
            if (filtroProfesional) {
                url += `&profesional=${filtroProfesional}`;
            }
            if (filtroFecha) {
                url += `&fecha=${filtroFecha}`;
            }

            const res = await axios.get(url, { headers: { 'Authorization': `Bearer ${token}` } });
            setTurnos(res.data);
        } catch (error) {
            console.error("Error cargando turnos", error);
        } finally {
            setLoading(false);
        }
    };

    // ========================================================================
    // FUNCIONES PARA GESTIÓN PROFESIONAL (Reprogramar/Cancelar sin restricción)
    // ========================================================================
    const abrirModalReprogramacion = (turno) => {
        setTurnoSeleccionado(turno);
        setAccionProfesional('REPROGRAMAR');
        setModalReprogramacionAbierto(true);
    };

    const abrirModalCancelacion = (turno) => {
        setTurnoSeleccionado(turno);
        setAccionProfesional('CANCELAR');
        setModalReprogramacionAbierto(true);
    };

    const cerrarModal = () => {
        setModalReprogramacionAbierto(false);
        setTurnoSeleccionado(null);
        setAccionProfesional(null);
        setNuevaFecha('');
        setNuevaHora('');
        setMotivoCancelacion('');
    };

    const abrirModalPago = (turno, preset = null) => {
        setTurnoPago(turno);
        setPagoPreset(preset);
        setModalPagoAbierto(true);
    };

    const cerrarModalPago = () => {
        setTurnoPago(null);
        setPagoPreset(null);
        setConfirmarTrasPago(null);
        setModalPagoAbierto(false);
    };

    const abrirModalFicha = (turno) => {
        setTurnoFicha(turno);
        setModalFichaAbierto(true);
    };

    const cerrarModalFicha = () => {
        setTurnoFicha(null);
        setModalFichaAbierto(false);
    };

    const ejecutarAccionProfesional = async () => {
        if (!turnoSeleccionado) return;

        try {
            const token = localStorage.getItem('access_token');
            const payload = {
                accion: accionProfesional
            };

            if (accionProfesional === 'REPROGRAMAR') {
                if (!nuevaFecha || !nuevaHora) {
                    notify.error("Ingresa fecha y hora");
                    return;
                }
                payload.nueva_fecha = nuevaFecha;
                payload.nueva_hora = nuevaHora;
            } else if (accionProfesional === 'CANCELAR') {
                payload.motivo = motivoCancelacion || 'Cancelado por el salón';
            }

            setProcesandoId(turnoSeleccionado.id);
            const res = await axios.post(
                `http://127.0.0.1:8000/api/gestion/turnos/${turnoSeleccionado.id}/gestionar-profesional/`,
                payload,
                { headers: { 'Authorization': `Bearer ${token}` } }
            );

            notify.success(res.data.mensaje);
            cerrarModal();
            cargarTurnos();
        } catch (error) {
            console.error("Error:", error.response?.data);
            const mensaje = error.response?.data?.error || 'Error al procesar la solicitud';
            notify.error(mensaje);
        } finally {
            setProcesandoId(null);
        }
    };

    // Función genérica para cambiar el estado de un turno
    const cambiarEstado = async (id, nuevoEstado, { skipConfirm = false } = {}) => {
        if (!skipConfirm) {
            const result = await confirmarAccion({
                title: "¿Cambiar estado del turno?",
                text: `Nuevo estado: ${nuevoEstado}`,
                confirmButtonText: "Sí, cambiar"
            });
            if (!result.isConfirmed) return;
        }

        setProcesandoId(id);
        try {
            const token = localStorage.getItem('access_token');
            const response = await axios.patch(
                `http://127.0.0.1:8000/api/gestion/turnos/${id}/`,
                { estado: nuevoEstado },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            console.log('Respuesta exitosa:', response.data);
            // Recargamos la lista para quitar el turno de esta pestaña
            cargarTurnos();
            notify.success(`Turno actualizado a ${nuevoEstado}`);
        } catch (error) {
            console.error("Error completo:", error.response?.data || error);
            const mensaje = error.response?.data?.estado?.[0] || 
                           error.response?.data?.error || 
                           error.response?.data?.detail ||
                           JSON.stringify(error.response?.data) ||
                           "Error al actualizar el turno";
            notify.error(mensaje);
        } finally {
            setProcesandoId(null);
        }
    };

    const marcarRealizadoDirecto = async (turnoId) => {
        setProcesandoId(turnoId);
        try {
            const token = localStorage.getItem('access_token');
            await axios.patch(
                `http://127.0.0.1:8000/api/gestion/turnos/${turnoId}/`,
                { estado: 'realizado' },
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            cargarTurnos();
            notify.success('Turno marcado como realizado');
        } catch (error) {
            console.error('Error marcando realizado:', error.response?.data || error);
            notify.error('Error al marcar el turno como realizado');
        } finally {
            setProcesandoId(null);
        }
    };

    const confirmarPago = async (turno) => {
        if (turno.comprobante_pago) {
            await cambiarEstado(turno.id, 'confirmado');
            return;
        }

        const result = await confirmarAccion({
            title: 'Sin comprobante cargado',
            text: 'Este turno no tiene comprobante. Si la seña fue en efectivo, registrala en caja para poder confirmar el pago.',
            confirmButtonText: 'Registrar seña en efectivo',
            cancelButtonText: 'Volver'
        });

        if (!result.isConfirmed) return;

        setConfirmarTrasPago(turno);
        abrirModalPago(turno, {
            metodoPago: 'EFECTIVO',
            esSena: true,
            lockMetodoPago: true,
            lockEsSena: true
        });
    };

    const finalizarTurnoConFicha = async (turnoId) => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await axios.post(
                `http://127.0.0.1:8000/api/gestion/turnos/${turnoId}/finalizar_turno/`,
                {},
                { headers: { 'Authorization': `Bearer ${token}` } }
            );
            notify.success(res.data.mensaje || 'Turno finalizado');
        } catch (error) {
            console.error('Error finalizando turno:', error.response?.data || error);
            notify.error(error.response?.data?.error || 'Error al finalizar el turno');
        }
    };

    // Componente visual para las Tabs
    const TabButton = ({ estado, label }) => (
        <button
            onClick={() => setFiltroEstado(estado)}
            className={`px-4 py-2 font-medium rounded-t-lg border-b-2 transition-colors ${
                filtroEstado === estado
                    ? 'border-rose-500 text-rose-600 bg-rose-50'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
        >
            {label}
        </button>
    );

    return (
        <div className="max-w-6xl mx-auto p-6 mt-8">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-3xl font-bold text-gray-800">Gestión de Turnos</h1>
                <button 
                    onClick={() => navigate('/admin-dashboard')}
                    className="text-gray-500 hover:underline"
                >
                    ← Volver al Dashboard
                </button>
            </div>

            {/* TABS DE NAVEGACIÓN */}
            <div className="flex border-b border-gray-200 mb-6">
                <TabButton estado="solicitado" label="Solicitudes (Análisis)" />
                <TabButton estado="esperando_sena" label="Esperando Seña" />
                <TabButton estado="confirmado" label="Agenda Confirmada" />
                <TabButton estado="realizado" label="Realizados" />
                <TabButton estado="cancelado" label="Cancelados" />
            </div>

            {/* BARRA DE BÚSQUEDA Y FILTROS */}
            <div className="bg-white shadow rounded-lg p-4 mb-6">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Buscar Cliente/Servicio</label>
                        <input
                            type="text"
                            placeholder="Nombre cliente, servicio..."
                            value={busqueda}
                            onChange={(e) => setBusqueda(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Profesional</label>
                        <select
                            value={filtroProfesional}
                            onChange={(e) => setFiltroProfesional(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                        >
                            <option value="">Todos los profesionales</option>
                            {profesionales.map((prof) => (
                                <option key={prof.id} value={prof.id}>
                                    {prof.nombre}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Fecha</label>
                        <input
                            type="date"
                            value={filtroFecha}
                            onChange={(e) => setFiltroFecha(e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                        />
                    </div>

                    <div className="flex items-end">
                        <button
                            onClick={() => {
                                setBusqueda('');
                                setFiltroProfesional('');
                                setFiltroFecha('');
                            }}
                            className="w-full px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300 font-medium"
                        >
                            Limpiar Filtros
                        </button>
                    </div>
                </div>
            </div>

            {/* TABLA DE TURNOS */}
            <div className="bg-white shadow rounded-lg overflow-hidden">
                {loading ? (
                    <div className="p-8 text-center text-gray-500">Cargando turnos...</div>
                ) : turnos.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">No hay turnos en esta sección.</div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Fecha/Hora</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cliente</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Servicio</th>
                                {filtroEstado === 'cancelado' && (
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Cancelado Por</th>
                                )}
                                {filtroEstado === 'cancelado' && (
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Motivo</th>
                                )}
                                {filtroEstado !== 'cancelado' && (
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Comprobante</th>
                                )}
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {turnos.map((turno) => (
                                <tr key={turno.id}>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-bold text-gray-900">{turno.fecha}</div>
                                        <div className="text-sm text-gray-500">{turno.hora_inicio} hs</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-medium text-gray-900">{turno.cliente_nombre || `ID: ${turno.cliente}`}</div>
                                        <div className="text-xs text-blue-500 cursor-pointer hover:underline">Ver Perfil Capilar</div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                                            {turno.servicio_nombre}
                                        </span>
                                    </td>
                                    {filtroEstado === 'cancelado' && (
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            <div className="text-sm font-medium text-gray-900">
                                                {turno.cancelado_por_nombre || 'Desconocido'}
                                            </div>
                                        </td>
                                    )}
                                    {filtroEstado === 'cancelado' && (
                                        <td className="px-6 py-4">
                                            <div className="text-sm text-gray-700 max-w-xs truncate" title={turno.motivo_cancelacion}>
                                                {turno.motivo_cancelacion || '-'}
                                            </div>
                                        </td>
                                    )}
                                    {filtroEstado !== 'cancelado' && (
                                        <td className="px-6 py-4 whitespace-nowrap">
                                            {turno.comprobante_pago ? (
                                                <a 
                                                    href={turno.comprobante_pago} 
                                                    target="_blank" 
                                                    rel="noopener noreferrer"
                                                    className="text-blue-500 underline hover:text-blue-700"
                                                >
                                                    Ver Comprobante
                                                </a>
                                            ) : <span className="text-gray-400 text-sm">Sin comprobante</span>}
                                        </td>
                                    )}
                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                        {/* BOTONES DE ACCIÓN SEGÚN EL ESTADO ACTUAL */}
                                        
                                        {filtroEstado === 'solicitado' && (
                                            <div className="flex justify-end gap-2">
                                                <button 
                                                    onClick={() => cambiarEstado(turno.id, 'cancelado')}
                                                    className="text-red-600 hover:text-red-900 border border-red-200 px-3 py-1 rounded hover:bg-red-50"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Rechazar
                                                </button>
                                                <button 
                                                    onClick={() => cambiarEstado(turno.id, 'esperando_sena')}
                                                    className="bg-rose-500 text-white px-3 py-1 rounded hover:bg-rose-600 shadow-sm"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Aprobar
                                                </button>
                                            </div>
                                        )}

                                        {filtroEstado === 'esperando_sena' && (
                                            <div className="flex justify-end gap-2">
                                                <button 
                                                    onClick={() => cambiarEstado(turno.id, 'cancelado')}
                                                    className="text-gray-500 hover:text-gray-700"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    No pagó
                                                </button>
                                                <button 
                                                    onClick={() => confirmarPago(turno)}
                                                    className="bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 shadow-sm"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Confirmar Pago
                                                </button>
                                            </div>
                                        )}

                                        {filtroEstado === 'confirmado' && (
                                            <div className="flex justify-end gap-2">
                                                <button 
                                                    onClick={() => abrirModalReprogramacion(turno)}
                                                    className="text-blue-600 hover:text-blue-900 border border-blue-200 px-3 py-1 rounded hover:bg-blue-50 text-xs"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Reprogramar
                                                </button>
                                                <button 
                                                    onClick={() => abrirModalCancelacion(turno)}
                                                    className="text-red-600 hover:text-red-900 border border-red-200 px-3 py-1 rounded hover:bg-red-50 text-xs"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Cancelar
                                                </button>
                                                <button 
                                                    onClick={() => abrirModalPago(turno)}
                                                    className="text-indigo-600 hover:text-indigo-900 border border-indigo-200 px-3 py-1 rounded hover:bg-indigo-50 text-xs"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Registrar Pago
                                                </button>
                                                <button 
                                                    onClick={() => abrirModalFicha(turno)}
                                                    className="bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 shadow-sm text-xs"
                                                    disabled={procesandoId === turno.id}
                                                >
                                                    Finalizar Servicio
                                                </button>
                                            </div>
                                        )}

                                        {filtroEstado === 'realizado' && (
                                            <span className="text-green-600 text-xs italic font-semibold">✓ Completado</span>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* MODAL PARA REPROGRAMAR/CANCELAR TURNOS (PROFESIONAL) */}
            {modalReprogramacionAbierto && turnoSeleccionado && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
                        <h2 className="text-2xl font-bold mb-4 text-gray-800">
                            {accionProfesional === 'REPROGRAMAR' ? 'Reprogramar Turno' : 'Cancelar Turno'}
                        </h2>
                        
                        <div className="mb-4 text-sm text-gray-600">
                            <p><strong>Cliente:</strong> {turnoSeleccionado.cliente_nombre}</p>
                            <p><strong>Fecha actual:</strong> {turnoSeleccionado.fecha} a las {turnoSeleccionado.hora_inicio}</p>
                            <p><strong>Servicio:</strong> {turnoSeleccionado.servicio_nombre}</p>
                        </div>

                        {accionProfesional === 'REPROGRAMAR' && (
                            <>
                                <div className="mb-4">
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Nueva Fecha</label>
                                    <input
                                        type="date"
                                        value={nuevaFecha}
                                        onChange={(e) => setNuevaFecha(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                                    />
                                </div>
                                <div className="mb-4">
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Nueva Hora</label>
                                    <input
                                        type="time"
                                        value={nuevaHora}
                                        onChange={(e) => setNuevaHora(e.target.value)}
                                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500"
                                    />
                                </div>
                            </>
                        )}

                        {accionProfesional === 'CANCELAR' && (
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 mb-2">Motivo de Cancelación (opcional)</label>
                                <textarea
                                    value={motivoCancelacion}
                                    onChange={(e) => setMotivoCancelacion(e.target.value)}
                                    placeholder="Ej: Cliente solicitó cancelación, error de agendamiento, etc."
                                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-rose-500 h-24"
                                />
                            </div>
                        )}

                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={cerrarModal}
                                className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300"
                                disabled={procesandoId === turnoSeleccionado?.id}
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={ejecutarAccionProfesional}
                                className={`px-4 py-2 text-white rounded-md ${
                                    accionProfesional === 'REPROGRAMAR' 
                                        ? 'bg-blue-600 hover:bg-blue-700' 
                                        : 'bg-red-600 hover:bg-red-700'
                                }`}
                                disabled={procesandoId === turnoSeleccionado?.id}
                            >
                                {accionProfesional === 'REPROGRAMAR' ? 'Reprogramar' : 'Cancelar'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <PagoModal
                isOpen={modalPagoAbierto}
                onClose={cerrarModalPago}
                origen={turnoPago}
                origenTipo="turno"
                defaultMetodoPago={pagoPreset?.metodoPago}
                defaultEsSena={pagoPreset?.esSena}
                defaultMonto={pagoPreset?.monto}
                lockMetodoPago={pagoPreset?.lockMetodoPago}
                lockEsSena={pagoPreset?.lockEsSena}
                lockMonto={pagoPreset?.lockMonto}
                onPagoRegistrado={async () => {
                    if (confirmarTrasPago) {
                        const turnoId = confirmarTrasPago.id;
                        setConfirmarTrasPago(null);
                        await cambiarEstado(turnoId, 'confirmado', { skipConfirm: true });
                        return;
                    }
                    if (turnoPago) {
                        marcarRealizadoDirecto(turnoPago.id);
                    }
                }}
            />

            {modalFichaAbierto && turnoFicha && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
                        <RegistroFichaTecnica
                            turnoId={turnoFicha.id}
                            onExito={async () => {
                                await finalizarTurnoConFicha(turnoFicha.id);
                                cerrarModalFicha();
                                cargarTurnos();
                            }}
                            onCancelar={cerrarModalFicha}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};

export default GestionTurnos;