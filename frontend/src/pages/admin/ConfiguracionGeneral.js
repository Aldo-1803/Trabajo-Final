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
            
            // Validar campos numéricos
            const camposNumericos = [
                'intervalo_turnos',
                'max_dias_anticipacion',
                'monto_sena',
                'tiempo_limite_pago_sena',
                'max_reprogramaciones',
                'horas_limite_cancelacion',
                'adelanto_min_horas_anticipacion',
                'adelanto_rango_dias_busqueda',
                'adelanto_max_candidatos',
                'adelanto_expira_horas',
                'promo_descuento_combo_x2',
                'promo_descuento_combo_x3',
                'combo_min_similitud',
                'combo_max_productos',
                'combo_min_stock',
                'combo_dias_vigencia'
            ];
            
            // Validar campos de texto
            const camposTexto = [
                'whatsapp_numero',
                'empresa_nombre',
                'comprobante_razon_social',
                'comprobante_cuil',
                'whatsapp_saludo',
                'whatsapp_cierre',
                'whatsapp_formato_producto'
            ];

            const camposFecha = [
                'comprobante_fecha_inicio_actividad'
            ];
            
            // Validar campos numéricos
            const campoNumericoVacio = camposNumericos.find(campo => {
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
            
            if (campoNumericoVacio) {
                setError(`❌ El campo "${campoNumericoVacio.replace(/_/g, ' ')}" no puede estar vacío o contener un valor inválido`);
                return;
            }
            
            // Validar campos de texto (solo no-vacío)
            const campoTextoVacio = camposTexto.find(campo => {
                const valor = formData[campo];
                return !valor || valor.trim() === '';
            });
            
            if (campoTextoVacio) {
                setError(`❌ El campo "${campoTextoVacio.replace(/_/g, ' ')}" no puede estar vacío`);
                return;
            }

            const campoFechaVacio = camposFecha.find(campo => {
                const valor = formData[campo];
                return !valor || String(valor).trim() === '';
            });

            if (campoFechaVacio) {
                setError(`❌ El campo "${campoFechaVacio.replace(/_/g, ' ')}" no puede estar vacío`);
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
                        {/* Descuento Combo x2 */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Descuento Combo x2 (%)
                            </label>
                            <input
                                type="number"
                                name="promo_descuento_combo_x2"
                                min="0"
                                max="100"
                                value={formData.promo_descuento_combo_x2 ?? 10}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Porcentaje aplicado a combos de 2 productos</p>
                        </div>

                        {/* Descuento Combo x3 */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Descuento Combo x3 (%)
                            </label>
                            <input
                                type="number"
                                name="promo_descuento_combo_x3"
                                min="0"
                                max="100"
                                value={formData.promo_descuento_combo_x3 ?? 15}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Porcentaje aplicado a combos de 3 productos</p>
                        </div>

                        {/* Combos automáticos */}
                        <div className="md:col-span-2">
                            <h3 className="text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Combos Automáticos
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <label className="flex items-center gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        name="combo_auto_activo"
                                        checked={formData.combo_auto_activo ?? true}
                                        onChange={manejarCambio}
                                        disabled={!editando}
                                    />
                                    Habilitar creación automática de combos
                                </label>
                                <label className="flex items-center gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        name="combo_usar_marca"
                                        checked={formData.combo_usar_marca ?? true}
                                        onChange={manejarCambio}
                                        disabled={!editando}
                                    />
                                    Considerar marca para similitud
                                </label>
                                <label className="flex items-center gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        name="combo_usar_proposito"
                                        checked={formData.combo_usar_proposito ?? true}
                                        onChange={manejarCambio}
                                        disabled={!editando}
                                    />
                                    Considerar propósito de uso
                                </label>
                                <label className="flex items-center gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        name="combo_usar_material"
                                        checked={formData.combo_usar_material ?? false}
                                        onChange={manejarCambio}
                                        disabled={!editando}
                                    />
                                    Considerar material principal
                                </label>
                                <label className="flex items-center gap-2 text-sm">
                                    <input
                                        type="checkbox"
                                        name="combo_usar_compatibilidad"
                                        checked={formData.combo_usar_compatibilidad ?? true}
                                        onChange={manejarCambio}
                                        disabled={!editando}
                                    />
                                    Considerar compatibilidad capilar
                                </label>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Combo: Mínimo de Similitud
                            </label>
                            <input
                                type="number"
                                name="combo_min_similitud"
                                value={formData.combo_min_similitud ?? 2}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Cantidad de criterios que deben coincidir</p>
                        </div>

                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Combo: Máximo de Productos
                            </label>
                            <input
                                type="number"
                                name="combo_max_productos"
                                value={formData.combo_max_productos ?? 3}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Cantidad máxima de productos por combo</p>
                        </div>

                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Combo: Stock Mínimo por Producto
                            </label>
                            <input
                                type="number"
                                name="combo_min_stock"
                                value={formData.combo_min_stock ?? 1}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Evita combos con stock bajo</p>
                        </div>

                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Combo: Días de Vigencia
                            </label>
                            <input
                                type="number"
                                name="combo_dias_vigencia"
                                value={formData.combo_dias_vigencia ?? 15}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Duración del combo automático</p>
                        </div>
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

                        {/* Adelanto: Mínimo de horas para disparar */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Adelanto: Mínimo de Horas de Anticipación
                            </label>
                            <input
                                type="number"
                                name="adelanto_min_horas_anticipacion"
                                value={formData.adelanto_min_horas_anticipacion ?? 24}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Si el turno se cancela con menos horas, no se busca adelanto</p>
                        </div>

                        {/* Adelanto: Rango de días */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Adelanto: Rango de Días a Considerar
                            </label>
                            <input
                                type="number"
                                name="adelanto_rango_dias_busqueda"
                                value={formData.adelanto_rango_dias_busqueda ?? 7}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Días posteriores a buscar candidatos con turnos confirmados</p>
                        </div>

                        {/* Adelanto: Máximo de candidatos */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Adelanto: Máximo de Candidatos
                            </label>
                            <input
                                type="number"
                                name="adelanto_max_candidatos"
                                value={formData.adelanto_max_candidatos ?? 5}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Límite de clientes notificados por cancelación</p>
                        </div>

                        {/* Adelanto: Expiración de oferta */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Adelanto: Expiración de Oferta (horas)
                            </label>
                            <input
                                type="number"
                                name="adelanto_expira_horas"
                                value={formData.adelanto_expira_horas ?? 6}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Tiempo máximo para aceptar el adelanto</p>
                        </div>

                        {/* Número de WhatsApp */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                🔗 Número de WhatsApp
                            </label>
                            <input
                                type="text"
                                name="whatsapp_numero"
                                value={formData.whatsapp_numero || ''}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                placeholder="549112233445"
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Número completo con código de país (ej: 549112233445). Sin espacios ni símbolos</p>
                        </div>

                        {/* Nombre de la empresa */}
                        <div>
                            <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Nombre de la Empresa
                            </label>
                            <input
                                type="text"
                                name="empresa_nombre"
                                value={formData.empresa_nombre || ''}
                                onChange={manejarCambio}
                                onFocus={(e) => e.target.select()}
                                disabled={!editando}
                                placeholder="Bohemia Hair"
                                className="w-full px-4 py-2 border rounded-lg transition-all"
                                style={{
                                    borderColor: editando ? '#E8DCC4' : '#ddd',
                                    backgroundColor: editando ? '#fff' : '#f5f5f5'
                                }}
                            />
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Nombre comercial que se mostrará en reportes y comprobantes</p>
                        </div>

                        {/* Datos fiscales para comprobantes */}
                        <div className="md:col-span-2">
                            <h3 className="text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                Datos fiscales para comprobantes
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div>
                                    <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                        Razón Social
                                    </label>
                                    <input
                                        type="text"
                                        name="comprobante_razon_social"
                                        value={formData.comprobante_razon_social || ''}
                                        onChange={manejarCambio}
                                        onFocus={(e) => e.target.select()}
                                        disabled={!editando}
                                        placeholder="Bohemia Hair S.R.L."
                                        className="w-full px-4 py-2 border rounded-lg transition-all"
                                        style={{
                                            borderColor: editando ? '#E8DCC4' : '#ddd',
                                            backgroundColor: editando ? '#fff' : '#f5f5f5'
                                        }}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                        CUIL
                                    </label>
                                    <input
                                        type="text"
                                        name="comprobante_cuil"
                                        value={formData.comprobante_cuil || ''}
                                        onChange={manejarCambio}
                                        onFocus={(e) => e.target.select()}
                                        disabled={!editando}
                                        placeholder="20-00000000-0"
                                        className="w-full px-4 py-2 border rounded-lg transition-all"
                                        style={{
                                            borderColor: editando ? '#E8DCC4' : '#ddd',
                                            backgroundColor: editando ? '#fff' : '#f5f5f5'
                                        }}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                        Inicio de Actividad
                                    </label>
                                    <input
                                        type="date"
                                        name="comprobante_fecha_inicio_actividad"
                                        value={formData.comprobante_fecha_inicio_actividad || ''}
                                        onChange={manejarCambio}
                                        disabled={!editando}
                                        className="w-full px-4 py-2 border rounded-lg transition-all"
                                        style={{
                                            borderColor: editando ? '#E8DCC4' : '#ddd',
                                            backgroundColor: editando ? '#fff' : '#f5f5f5'
                                        }}
                                    />
                                </div>
                            </div>
                            <p className="text-xs mt-1" style={{ color: '#8B8682' }}>
                                Estos datos se imprimen en los comprobantes de pago.
                            </p>
                        </div>
                    </div>

                    {/* Formato del Mensaje de WhatsApp */}
                    <div className="mt-8 pt-8 border-t" style={{ borderColor: '#E8DCC4' }}>
                        <h3 className="text-lg font-bold mb-6" style={{ color: '#817773' }}>
                            💬 Formato del Mensaje de WhatsApp
                        </h3>
                        
                        <div className="grid grid-cols-1 gap-6">
                            {/* Saludo Inicial */}
                            <div>
                                <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                    Saludo Inicial
                                </label>
                                <input
                                    type="text"
                                    name="whatsapp_saludo"
                                    value={formData.whatsapp_saludo || ''}
                                    onChange={manejarCambio}
                                    disabled={!editando}
                                    className="w-full px-4 py-2 border rounded-lg transition-all"
                                    style={{
                                        borderColor: editando ? '#E8DCC4' : '#ddd',
                                        backgroundColor: editando ? '#fff' : '#f5f5f5'
                                    }}
                                />
                                <p className="text-xs mt-1" style={{ color: '#8B8682' }}>Texto que aparece al inicio del mensaje</p>
                            </div>

                            {/* Formato de Producto */}
                            <div>
                                <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                    Formato de Cada Producto
                                </label>
                                <textarea
                                    name="whatsapp_formato_producto"
                                    value={formData.whatsapp_formato_producto || ''}
                                    onChange={manejarCambio}
                                    disabled={!editando}
                                    rows="3"
                                    className="w-full px-4 py-2 border rounded-lg transition-all font-mono text-xs"
                                    style={{
                                        borderColor: editando ? '#E8DCC4' : '#ddd',
                                        backgroundColor: editando ? '#fff' : '#f5f5f5'
                                    }}
                                />
                                <p className="text-xs mt-1" style={{ color: '#8B8682' }}>
                                    Variables: {'{nombre}'}, {'{cantidad}'}, {'{precio}'}, {'{subtotal}'}
                                </p>
                            </div>

                            {/* Cierre del Mensaje */}
                            <div>
                                <label className="block text-sm font-bold mb-2" style={{ color: '#817773' }}>
                                    Cierre del Mensaje
                                </label>
                                <textarea
                                    name="whatsapp_cierre"
                                    value={formData.whatsapp_cierre || ''}
                                    onChange={manejarCambio}
                                    disabled={!editando}
                                    rows="3"
                                    className="w-full px-4 py-2 border rounded-lg transition-all"
                                    style={{
                                        borderColor: editando ? '#E8DCC4' : '#ddd',
                                        backgroundColor: editando ? '#fff' : '#f5f5f5'
                                    }}
                                />
                                <p className="text-xs mt-1" style={{ color: '#8B8682' }}>
                                    Variable disponible: {'{total}'} para el monto total
                                </p>
                            </div>
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
