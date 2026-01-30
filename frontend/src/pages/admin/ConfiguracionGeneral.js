import React, { useState, useEffect } from 'react';
import axios from 'axios';

const ConfiguracionGeneral = () => {
    const [configuracion, setConfiguracion] = useState(null);
    const [editando, setEditando] = useState(false);
    const [formData, setFormData] = useState({});
    const [cargando, setCargando] = useState(true);
    const [mensaje, setMensaje] = useState('');
    const [error, setError] = useState('');

    // Cargar configuración al montar el componente
    useEffect(() => {
        cargarConfiguracion();
    }, []);

    const cargarConfiguracion = async () => {
        try {
            setCargando(true);
            setError('');
            const response = await axios.get('/api/gestion/configuracion/');
            
            let configData = null;
            
            // Intentar extraer la configuración de diferentes formatos posibles
            if (response.data.results && response.data.results.length > 0) {
                configData = response.data.results[0];
            } else if (Array.isArray(response.data) && response.data.length > 0) {
                configData = response.data[0];
            } else if (response.data && typeof response.data === 'object' && response.data.id) {
                configData = response.data;
            }
            
            if (!configData) {
                setError('No se pudo cargar la configuración del servidor');
                setCargando(false);
                return;
            }
            
            setConfiguracion(configData);
            setFormData(configData);
        } catch (err) {
            console.error('Error cargando configuración:', err);
            setError('Error al cargar la configuración: ' + err.message);
        } finally {
            setCargando(false);
        }
    };

    const manejarCambio = (e) => {
        const { name, value, type } = e.target;
        
        let nuevoValor;
        if (type === 'number') {
            // Si está vacío, guardar como string vacío
            // Si tiene valor, convertir a número
            nuevoValor = value === '' ? '' : Number(value);
        } else if (type === 'checkbox') {
            nuevoValor = e.target.checked;
        } else {
            nuevoValor = value;
        }
        
        setFormData({
            ...formData,
            [name]: nuevoValor
        });
    };

    const guardarConfiguracion = async () => {
        try {
            setError('');
            setMensaje('');
            
            // Validar que configuracion esté cargada
            if (!configuracion || !configuracion.id) {
                setError('❌ Error: No se cargó la configuración correctamente');
                return;
            }
            
            // Validar que todos los campos numéricos estén llenos y sean números válidos
            const camposRequeridos = [
                'intervalo_turnos',
                'max_dias_anticipacion',
                'monto_sena',
                'tiempo_limite_pago_sena',
                'max_reprogramaciones',
                'horas_limite_cancelacion'
            ];
            
            const campoVacio = camposRequeridos.find(campo => {
                const valor = formData[campo];
                
                // String vacío, null, undefined = inválido
                if (valor === '' || valor === null || valor === undefined) return true;
                
                // Si es número, válido (incluso 0)
                if (typeof valor === 'number' && !isNaN(valor)) return false;
                
                // Si es string con contenido y se puede convertir a número válido, está bien
                if (typeof valor === 'string' && valor.trim() !== '' && !isNaN(Number(valor))) return false;
                
                // Cualquier otra cosa es inválida
                return true;
            });
            
            if (campoVacio) {
                setError(`❌ El campo "${campoVacio.replace(/_/g, ' ')}" no puede estar vacío o contener un valor inválido`);
                return;
            }
            
            const configId = configuracion.id;
            const response = await axios.put(
                `/api/gestion/configuracion/${configId}/`,
                formData
            );
            
            setConfiguracion(response.data);
            setEditando(false);
            setMensaje('✅ Configuración guardada exitosamente');
            setTimeout(() => setMensaje(''), 3000);
        } catch (err) {
            setError('Error al guardar: ' + (err.response?.data?.detail || err.message));
        }
    };

    const cancelarEdicion = () => {
        if (configuracion) {
            setFormData(configuracion);
        }
        setEditando(false);
        setError('');
    };

    if (cargando) {
        return (
            <div className="flex justify-center items-center h-64">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto mb-4" style={{ borderColor: '#817773' }}></div>
                    <p style={{ color: '#817773' }}>Cargando configuración...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="p-6">
            {/* Mensajes */}
            {mensaje && (
                <div className="mb-4 p-4 rounded-lg" style={{ backgroundColor: '#E8F5E9', color: '#2E7D32', border: '1px solid #4CAF50' }}>
                    {mensaje}
                </div>
            )}
            
            {error && (
                <div className="mb-4 p-4 rounded-lg" style={{ backgroundColor: '#FFEBEE', color: '#C62828', border: '1px solid #EF5350' }}>
                    {error}
                </div>
            )}

            {/* Tarjeta de Configuración */}
            <div className="bg-white rounded-lg shadow-md border" style={{ borderColor: '#E8DCC4' }}>
                <div className="px-6 py-6 border-b" style={{ borderColor: '#E8DCC4' }}>
                    <h2 className="text-2xl font-bold" style={{ color: '#817773' }}>
                        Configuración General del Sistema
                    </h2>
                    <p className="text-sm mt-2" style={{ color: '#8B8682' }}>
                        Gestiona los parámetros principales que rigen el funcionamiento de Bohemia Hair
                    </p>
                </div>

                <div className="p-6">
                    {/* Grid de campos */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Intervalo de Turnos */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Intervalo de Turnos (minutos)
                            </label>
                            <input
                                type="number"
                                name="intervalo_turnos"
                                value={formData.intervalo_turnos ?? 30}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Tamaño de cada bloque en la agenda</p>
                        </div>

                        {/* Días de Anticipación */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Máximo de Días de Anticipación
                            </label>
                            <input
                                type="number"
                                name="max_dias_anticipacion"
                                value={formData.max_dias_anticipacion ?? 60}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Cuánto tiempo antes se puede reservar</p>
                        </div>

                        {/* Monto de Seña */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Monto de Seña (ARS)
                            </label>
                            <input
                                type="number"
                                name="monto_sena"
                                value={formData.monto_sena || 5000}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                step="100"
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Depósito requerido para confirmar turno</p>
                        </div>

                        {/* Tiempo Límite Pago Seña */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Tiempo Límite Pago Seña (horas)
                            </label>
                            <input
                                type="number"
                                name="tiempo_limite_pago_sena"
                                value={formData.tiempo_limite_pago_sena ?? 24}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Horas para pagar antes de cancelar automáticamente</p>
                        </div>

                        {/* Máximo Reprogramaciones */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Máximo de Reprogramaciones
                            </label>
                            <input
                                type="number"
                                name="max_reprogramaciones"
                                value={formData.max_reprogramaciones ?? 2}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Cambios permitidos por cliente</p>
                        </div>

                        {/* Horas Límite Cancelación */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Horas Límite de Cancelación
                            </label>
                            <input
                                type="number"
                                name="horas_limite_cancelacion"
                                value={formData.horas_limite_cancelacion ?? 48}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Horas antes del turno donde NO se puede cancelar</p>
                        </div>
                    </div>

                    {/* Botones de Acción */}
                    <div className="mt-8 flex gap-4 justify-end">
                        {!editando ? (
                            <button
                                onClick={() => setEditando(true)}
                                className="px-6 py-3 rounded-lg font-bold transition-all"
                                style={{
                                    backgroundColor: '#817773',
                                    color: 'white'
                                }}
                                onMouseEnter={(e) => e.target.style.backgroundColor = '#6B6B65'}
                                onMouseLeave={(e) => e.target.style.backgroundColor = '#817773'}
                            >
                                Editar Configuración
                            </button>
                        ) : (
                            <>
                                <button
                                    onClick={cancelarEdicion}
                                    className="px-6 py-3 rounded-lg font-bold transition-all border-2"
                                    style={{
                                        borderColor: '#817773',
                                        color: '#817773',
                                        backgroundColor: 'transparent'
                                    }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#F5F5EB'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
                                >
                                    Cancelar
                                </button>
                                <button
                                    onClick={guardarConfiguracion}
                                    className="px-6 py-3 rounded-lg font-bold transition-all"
                                    style={{
                                        backgroundColor: '#4CAF50',
                                        color: 'white'
                                    }}
                                    onMouseEnter={(e) => e.target.style.backgroundColor = '#388E3C'}
                                    onMouseLeave={(e) => e.target.style.backgroundColor = '#4CAF50'}
                                >
                                    Guardar Cambios
                                </button>
                            </>
                        )}
                    </div>
                </div>
            </div>

            {/* Información de auditoría */}
            {configuracion && (
                <div className="mt-6 p-4 rounded-lg border" style={{ backgroundColor: '#FAFAFA', borderColor: '#E8DCC4' }}>
                    <p className="text-xs font-bold" style={{ color: '#817773' }}>INFORMACIÓN DEL SISTEMA</p>
                    <p className="text-xs mt-2" style={{ color: '#8B8682' }}>
                        Configuración ID: <span className="font-mono">{configuracion.id}</span>
                    </p>
                </div>
            )}
        </div>
    );
};

export default ConfiguracionGeneral;
